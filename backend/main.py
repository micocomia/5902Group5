import ast
import json
import time
import uvicorn
import hydra
from omegaconf import DictConfig, OmegaConf
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, HTTPException, UploadFile, File, Header
from io import BytesIO
import pdfplumber
from base.llm_factory import LLMFactory
from base.searcher_factory import SearchRunner
from base.search_rag import SearchRagManager
from fastapi.responses import JSONResponse
from modules.skill_gap_identification import *
from modules.adaptive_learner_modeling import *
from modules.personalized_resource_delivery import *
from modules.personalized_resource_delivery.agents.learning_path_scheduler import refine_learning_path_with_llm
from modules.ai_chatbot_tutor import chat_with_tutor_with_llm
from api_schemas import *
from config import load_config
from utils import store
from utils import auth_store, auth_jwt

app_config = load_config(config_name="main")
search_rag_manager = SearchRagManager.from_config(app_config)

app = FastAPI()
from pydantic import BaseModel
from typing import Any, Dict, List, Optional
from datetime import datetime


@app.on_event("startup")
def _load_stores():
    store.load()
    auth_store.load()

class BehaviorEvent(BaseModel):
    user_id: str
    event_type: str
    payload: Dict[str, Any] = {}
    ts: Optional[str] = None

@app.post("/events/log")
async def log_event(evt: BehaviorEvent):
    e = evt.dict() if hasattr(evt, "dict") else evt.model_dump()
    e["ts"] = e["ts"] or datetime.utcnow().isoformat()
    store.append_event(evt.user_id, e)
    return {"ok": True, "event_count": len(store.get_events(evt.user_id))}

class AutoProfileUpdateRequest(BaseModel):
    user_id: str
    goal_id: int = 0

    # optional overrides (otherwise uses app_config defaults via get_llm)
    model_provider: Optional[str] = None
    model_name: Optional[str] = None

    # only needed if this is the FIRST time we create the profile
    learning_goal: Optional[str] = None
    learner_information: Optional[Any] = None
    skill_gaps: Optional[Any] = None

    # optional session metadata
    session_information: Optional[Dict[str, Any]] = None


@app.post("/profile/auto-update")
async def auto_update_profile(request: AutoProfileUpdateRequest):
    """
    If profile doesn't exist: initialize it (needs learning_goal + learner_information + skill_gaps).
    If profile exists: update it using EVENT_STORE[user_id] as learner_interactions.
    """
    try:
        user_id = request.user_id
        llm = get_llm(request.model_provider, request.model_name)  # uses defaults if None

        goal_id = request.goal_id

        # grab recent events for this user (can be empty)
        interactions = store.get_events(user_id)

        # Normalize optional structured fields (match style used in /create-learner-profile-with-info)
        learner_info = request.learner_information
        if isinstance(learner_info, str):
            try:
                learner_info = ast.literal_eval(learner_info)
            except Exception:
                learner_info = {"raw": learner_info}

        skill_gaps = request.skill_gaps
        if isinstance(skill_gaps, str):
            try:
                skill_gaps = ast.literal_eval(skill_gaps)
            except Exception:
                skill_gaps = {"raw": skill_gaps}

        # CASE A: first-time user => create profile
        if store.get_profile(user_id, goal_id) is None:
            if not (request.learning_goal and learner_info is not None and skill_gaps is not None):
                raise HTTPException(
                    status_code=400,
                    detail="No profile found for this user_id. Provide learning_goal, learner_information, and skill_gaps to initialize."
                )

            profile = initialize_learner_profile_with_llm(
                llm,
                request.learning_goal,
                learner_info,
                skill_gaps,
            )

            store.upsert_profile(user_id, goal_id, profile)
            return {
                "ok": True,
                "mode": "initialized",
                "user_id": user_id,
                "goal_id": goal_id,
                "event_count_used": len(interactions),
                "learner_profile": profile,
            }

        # CASE B: existing user => update profile from events
        current_profile = store.get_profile(user_id, goal_id)

        session_info = request.session_information or {}
        session_info = {
            **session_info,
            "updated_at": datetime.utcnow().isoformat(),
            "event_count": len(interactions),
            "source": "EVENT_STORE",
        }

        updated_profile = update_learner_profile_with_llm(
            llm,
            current_profile,
            interactions,
            learner_info if learner_info is not None else "",
            session_info,
        )

        store.upsert_profile(user_id, goal_id, updated_profile)

        return {
            "ok": True,
            "mode": "updated",
            "user_id": user_id,
            "goal_id": goal_id,
            "event_count_used": len(interactions),
            "learner_profile": updated_profile,
        }

    except HTTPException:
        raise
    except Exception as e:
        # Make Swagger show the real exception message
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/profile/{user_id}")
async def get_profile(user_id: str, goal_id: Optional[int] = None):
    if goal_id is not None:
        profile = store.get_profile(user_id, goal_id)
        if not profile:
            raise HTTPException(status_code=404, detail="No profile found for this user_id and goal_id")
        return {"user_id": user_id, "goal_id": goal_id, "learner_profile": profile}
    profiles = store.get_all_profiles_for_user(user_id)
    if not profiles:
        raise HTTPException(status_code=404, detail="No profile found for this user_id")
    return {"user_id": user_id, "profiles": profiles}

@app.get("/events/{user_id}")
async def get_events(user_id: str):
    return {"user_id": user_id, "events": store.get_events(user_id)}


@app.get("/user-state/{user_id}")
async def get_user_state(user_id: str):
    state = store.get_user_state(user_id)
    if state is None:
        raise HTTPException(status_code=404, detail="No state found for this user_id")
    return {"state": state}


@app.put("/user-state/{user_id}")
async def put_user_state(user_id: str, body: UserStateRequest):
    store.put_user_state(user_id, body.state)
    return {"ok": True}


@app.delete("/user-state/{user_id}")
async def delete_user_state(user_id: str):
    store.delete_user_state(user_id)
    return {"ok": True}


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/auth/register")
async def auth_register(request: AuthRegisterRequest):
    if len(request.username) < 3:
        raise HTTPException(status_code=400, detail="Username must be at least 3 characters")
    if len(request.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
    try:
        auth_store.create_user(request.username, request.password)
    except ValueError:
        raise HTTPException(status_code=409, detail="Username already exists")
    token = auth_jwt.create_token(request.username)
    return {"token": token, "username": request.username}


@app.post("/auth/login")
async def auth_login(request: AuthLoginRequest):
    if not auth_store.verify_password(request.username, request.password):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    token = auth_jwt.create_token(request.username)
    return {"token": token, "username": request.username}


@app.get("/auth/me")
async def auth_me(authorization: str = Header("")):
    token = authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization
    username = auth_jwt.verify_token(token)
    if not username:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return {"username": username}


def get_llm(model_provider: str | None = None, model_name: str | None = None, **kwargs):
    model_provider = model_provider or app_config.llm.provider
    model_name = model_name or app_config.llm.model_name
    return LLMFactory.create(model=model_name, model_provider=model_provider, **kwargs)

@app.post("/extract-pdf-text")
async def extract_pdf_text(file: UploadFile = File(...)):
    """Extract text from an uploaded PDF file."""
    try:
        contents = await file.read()
        with pdfplumber.open(BytesIO(contents)) as pdf:
            text = "\n".join(page.extract_text() or "" for page in pdf.pages)
        return {"text": text}
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": str(e)})

@app.get("/list-llm-models")
async def list_llm_models():
    try:
        return {"models": [
            {
                "model_name": app_config.llm.model_name, 
                "model_provider": app_config.llm.provider
            }
        ]}
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": str(e)})

@app.post("/chat-with-tutor")
async def chat_with_autor(request: ChatWithAutorRequest):
    llm = get_llm(request.model_provider, request.model_name)
    learner_profile = request.learner_profile
    try:
        if isinstance(request.messages, str) and request.messages.strip().startswith("["):
            converted_messages = ast.literal_eval(request.messages)
        else:
            return JSONResponse(status_code=400, content={"detail": "messages must be a JSON array string"})
        response = chat_with_tutor_with_llm(
            llm,
            converted_messages,
            learner_profile,
            search_rag_manager=search_rag_manager,
            use_search=True,
        )
        return {"response": response}
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": str(e)})

@app.post("/refine-learning-goal")
async def refine_learning_goal(request: LearningGoalRefinementRequest):
    llm = get_llm(request.model_provider, request.model_name)
    try:
        refined_learning_goal = refine_learning_goal_with_llm(llm, request.learning_goal, request.learner_information)
        return refined_learning_goal
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": str(e)})

@app.post("/identify-skill-gap-with-info")
async def identify_skill_gap_with_info(request: SkillGapIdentificationRequest):
    llm = get_llm(request.model_provider, request.model_name)
    learning_goal = request.learning_goal
    learner_information = request.learner_information
    skill_requirements = request.skill_requirements
    try:
        if isinstance(skill_requirements, str) and skill_requirements.strip():
            skill_requirements = ast.literal_eval(skill_requirements)
        if not isinstance(skill_requirements, dict):
            skill_requirements = None
        skill_gaps, skill_requirements = identify_skill_gap_with_llm(
            llm, learning_goal, learner_information, skill_requirements
        )
        results = {**skill_gaps, **skill_requirements}
        return results
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": str(e)})


@app.post("/create-learner-profile-with-info")
async def create_learner_profile_with_info(request: LearnerProfileInitializationWithInfoRequest):
    llm = get_llm(request.model_provider, request.model_name)
    learner_information = request.learner_information
    learning_goal = request.learning_goal
    skill_gaps = request.skill_gaps
    try:
        if isinstance(learner_information, str):
            try:
                learner_information = ast.literal_eval(learner_information)
            except Exception:
                learner_information = {"raw": learner_information}
        if isinstance(skill_gaps, str):
            try:
                skill_gaps = ast.literal_eval(skill_gaps)
            except Exception:
                skill_gaps = {"raw": skill_gaps}
        learner_profile = initialize_learner_profile_with_llm(
            llm, learning_goal, learner_information, skill_gaps
        )
        if request.user_id is not None and request.goal_id is not None:
            store.upsert_profile(request.user_id, request.goal_id, learner_profile)
        return {"learner_profile": learner_profile}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/update-learner-profile")
async def update_learner_profile(request: LearnerProfileUpdateRequest):
    llm = get_llm(request.model_provider, request.model_name)
    learner_profile = request.learner_profile
    learner_interactions = request.learner_interactions
    learner_information = request.learner_information
    session_information = request.session_information
    try:
        for name in ("learner_profile", "learner_interactions", "learner_information", "session_information"):
            val = locals()[name]
            if isinstance(val, str) and val.strip():
                try:
                    locals()[name] = ast.literal_eval(val)
                except Exception:
                    if name != "session_information":
                        locals()[name] = {"raw": val}
        learner_profile = update_learner_profile_with_llm(
            llm,
            locals()["learner_profile"],
            locals()["learner_interactions"],
            locals()["learner_information"],
            locals()["session_information"],
        )
        if request.user_id is not None and request.goal_id is not None:
            store.upsert_profile(request.user_id, request.goal_id, learner_profile)
        return {"learner_profile": learner_profile}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/schedule-learning-path")
async def schedule_learning_path(request: LearningPathSchedulingRequest):
    llm = get_llm(request.model_provider, request.model_name)
    learner_profile = request.learner_profile
    session_count = request.session_count
    try:
        if isinstance(learner_profile, str) and learner_profile.strip():
            learner_profile = ast.literal_eval(learner_profile)
        if not isinstance(learner_profile, dict):
            learner_profile = {}
        learning_path = schedule_learning_path_with_llm(llm, learner_profile, session_count)
        return learning_path
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/reschedule-learning-path")
async def reschedule_learning_path(request: LearningPathReschedulingRequest):
    llm = get_llm(request.model_provider, request.model_name)
    learner_profile = request.learner_profile
    learning_path = request.learning_path
    session_count = request.session_count
    other_feedback = request.other_feedback
    try:
        if isinstance(learner_profile, str) and learner_profile.strip():
            learner_profile = ast.literal_eval(learner_profile)
        if not isinstance(learner_profile, dict):
            learner_profile = {}
        if isinstance(learning_path, str) and learning_path.strip():
            learning_path = ast.literal_eval(learning_path)
        if isinstance(other_feedback, str) and other_feedback.strip():
            try:
                other_feedback = ast.literal_eval(other_feedback)
            except Exception:
                pass
        learning_path = reschedule_learning_path_with_llm(
            llm, learning_path, learner_profile, session_count, other_feedback
        )
        return learning_path
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/explore-knowledge-points")
async def explore_knowledge_points(request: KnowledgePointExplorationRequest):
    llm = get_llm()
    learner_profile = request.learner_profile
    learning_path = request.learning_path
    learning_session = request.learning_session
    if isinstance(learner_profile, str) and learner_profile.strip():
        learner_profile = ast.literal_eval(learner_profile)
    if isinstance(learning_path, str) and learning_path.strip():
        learning_path = ast.literal_eval(learning_path)
    if isinstance(learning_session, str) and learning_session.strip():
        learning_session = ast.literal_eval(learning_session)
    try:
        knowledge_points = explore_knowledge_points_with_llm(llm, learner_profile, learning_path, learning_session)
        return knowledge_points
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/draft-knowledge-point")
async def draft_knowledge_point(request: KnowledgePointDraftingRequest):
    llm = get_llm()
    learner_profile = request.learner_profile
    learning_path = request.learning_path
    learning_session = request.learning_session
    knowledge_points = request.knowledge_points
    knowledge_point = request.knowledge_point
    use_search = request.use_search
    try:
        knowledge_draft = draft_knowledge_point_with_llm(llm, learner_profile, learning_path, learning_session, knowledge_points, knowledge_point, use_search)
        return {"knowledge_draft": knowledge_draft}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/draft-knowledge-points")
async def draft_knowledge_points(request: KnowledgePointsDraftingRequest):
    llm = get_llm()
    learner_profile = request.learner_profile
    learning_path = request.learning_path
    learning_session = request.learning_session
    knowledge_points = request.knowledge_points
    use_search = request.use_search
    allow_parallel = request.allow_parallel
    try:
        knowledge_drafts = draft_knowledge_points_with_llm(llm, learner_profile, learning_path, learning_session, knowledge_points, allow_parallel, use_search)
        return {"knowledge_drafts": knowledge_drafts}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/integrate-learning-document")
async def integrate_learning_document(request: LearningDocumentIntegrationRequest):
    llm = get_llm()
    learner_profile = request.learner_profile
    learning_path = request.learning_path
    learning_session = request.learning_session
    knowledge_points = request.knowledge_points
    knowledge_drafts = request.knowledge_drafts
    output_markdown = request.output_markdown
    try:
        learning_document = integrate_learning_document_with_llm(llm, learner_profile, learning_path, learning_session, knowledge_points, knowledge_drafts, output_markdown)
        return {"learning_document": learning_document}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/generate-document-quizzes")
async def generate_document_quizzes(request: KnowledgeQuizGenerationRequest):
    llm = get_llm()
    learner_profile = request.learner_profile
    learning_document = request.learning_document
    single_choice_count = request.single_choice_count
    multiple_choice_count = request.multiple_choice_count
    true_false_count = request.true_false_count
    short_answer_count = request.short_answer_count
    try:
        document_quiz = generate_document_quizzes_with_llm(llm, learner_profile, learning_document, single_choice_count, multiple_choice_count, true_false_count, short_answer_count)
        return {"document_quiz": document_quiz}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/tailor-knowledge-content")
async def tailor_knowledge_content(request: TailoredContentGenerationRequest):
    llm = get_llm()
    learning_path = request.learning_path
    learner_profile = request.learner_profile
    learning_session = request.learning_session
    use_search = request.use_search
    allow_parallel = request.allow_parallel
    with_quiz = request.with_quiz
    try:
        tailored_content = create_learning_content_with_llm(
            llm, learner_profile, learning_path, learning_session, allow_parallel=allow_parallel, with_quiz=with_quiz, use_search=use_search
        )
        return {"tailored_content": tailored_content}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/simulate-path-feedback")
async def simulate_path_feedback(request: LearningPathFeedbackRequest):
    llm = get_llm(request.model_provider, request.model_name)
    learner_profile = request.learner_profile
    learning_path = request.learning_path
    try:
        if isinstance(learner_profile, str) and learner_profile.strip():
            learner_profile = ast.literal_eval(learner_profile)
        if isinstance(learning_path, str) and learning_path.strip():
            learning_path = ast.literal_eval(learning_path)
        feedback = simulate_path_feedback_with_llm(llm, learner_profile, learning_path)
        return {"feedback": feedback}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/simulate-content-feedback")
async def simulate_content_feedback(request: LearningContentFeedbackRequest):
    llm = get_llm(request.model_provider, request.model_name)
    learner_profile = request.learner_profile
    learning_content = request.learning_content
    try:
        if isinstance(learner_profile, str) and learner_profile.strip():
            learner_profile = ast.literal_eval(learner_profile)
        if isinstance(learning_content, str) and learning_content.strip():
            learning_content = ast.literal_eval(learning_content)
        feedback = simulate_content_feedback_with_llm(llm, learner_profile, learning_content)
        return {"feedback": feedback}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/refine-learning-path")
async def refine_learning_path(request: LearningPathRefinementRequest):
    llm = get_llm(request.model_provider, request.model_name)
    learning_path = request.learning_path
    feedback = request.feedback
    try:
        if isinstance(learning_path, str) and learning_path.strip():
            learning_path = ast.literal_eval(learning_path)
        if isinstance(feedback, str) and feedback.strip():
            feedback = ast.literal_eval(feedback)
        refined_path = refine_learning_path_with_llm(llm, learning_path, feedback)
        return {"refined_learning_path": refined_path}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/iterative-refine-path")
async def iterative_refine_path(request: IterativeRefinementRequest):
    llm = get_llm(request.model_provider, request.model_name)
    learner_profile = request.learner_profile
    learning_path = request.learning_path
    max_iterations = min(request.max_iterations, 5)  # Cap at 5 iterations
    try:
        if isinstance(learner_profile, str) and learner_profile.strip():
            learner_profile = ast.literal_eval(learner_profile)
        if isinstance(learning_path, str) and learning_path.strip():
            learning_path = ast.literal_eval(learning_path)

        iterations = []
        current_path = learning_path

        for i in range(max_iterations):
            # Simulate feedback for current path
            feedback = simulate_path_feedback_with_llm(llm, learner_profile, current_path)
            iterations.append({
                "iteration": i + 1,
                "feedback": feedback
            })
            # Refine path based on feedback
            refined_result = refine_learning_path_with_llm(llm, current_path, feedback)
            current_path = refined_result.get("learning_path", current_path)

        return {
            "final_learning_path": current_path,
            "iterations": iterations
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    server_cfg = app_config.get("server", {})
    host = app_config.get("server", {}).get("host", "127.0.0.1")
    port = int(app_config.get("server", {}).get("port", 5000))
    log_level = str(app_config.get("log_level", "debug")).lower()
    uvicorn.run(app, host=host, port=port, log_level=log_level)
