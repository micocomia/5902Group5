import streamlit as st

import time
import asyncio
from components.goal_refinement import render_goal_refinement
from utils.pdf import extract_text_from_pdf
from utils.state import save_persistent_state, reset_to_add_goal
from components.topbar import render_topbar
from utils.personas import PERSONAS


def on_refine_click():
    st.session_state["if_refining_learning_goal"] = True
    try:
        save_persistent_state()
    except Exception:
        pass


def _init_onboarding_state():
    """Ensure required session_state keys exist to avoid KeyErrors."""
    st.session_state.setdefault("onboarding_card_index", 0)  # 0: info, 1: goal
    st.session_state.setdefault("if_refining_learning_goal", False)
    st.session_state.setdefault("learner_persona", "")
    st.session_state.setdefault("learner_information_text", "")
    st.session_state.setdefault("learner_information", "")
    if "to_add_goal" not in st.session_state:
        reset_to_add_goal()
    try:
        save_persistent_state()
    except Exception:
        pass


def _inject_card_css():
    """Inject lightweight CSS to make sections look like cards and style nav buttons."""
    st.markdown(
        """
        <style>
        .gm-card { 
            background: #ffffff; 
            border: 1px solid rgba(0,0,0,0.08);
            border-radius: 14px; 
            box-shadow: 0 8px 24px rgba(0,0,0,0.06);
            padding: 24px 22px; 
        }
        .gm-side { position: sticky; top: 160px; }
        .gm-side .gm-side-btn {
            border: 1px solid rgba(0,0,0,0.12);
            background: #ffffff;
            color: #111827;
            padding: 6px 10px; 
            border-radius: 10px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.06);
            font-weight: 700;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

def render_onboard():
    _init_onboarding_state()
    _inject_card_css()
    left, center, right = st.columns([1, 5, 1])
    goal = st.session_state["to_add_goal"]
    if "refined_learning_goal" not in st.session_state:
        st.session_state["refined_learning_goal"] = goal["learning_goal"]
        try:
            save_persistent_state()
        except Exception:
            pass
    with center:
        render_topbar()
        st.title("Onboarding GenMentor")
        st.write("Start Your Goal-oriented and Personalized Learning Journey!")
        render_cards_with_nav(goal)
        

def render_goal(goal):
    idx = st.session_state.get("onboarding_card_index", 0)
    with st.container(border=True):
        st.subheader("Set Learning Goal")
        st.info("🚀 Please enter your role and specific learning goal. You can also refine it with AI suggestions.")
        learning_goal = st.text_area("* Enter your learning goal", value=goal["learning_goal"], label_visibility="visible", disabled=st.session_state["if_refining_learning_goal"])
        goal["learning_goal"] = learning_goal
        button_col, hint_col, _ = st.columns([3, 10, 3])
        render_goal_refinement(goal, button_col, hint_col)
        save_persistent_state()
        with hint_col:
            if st.session_state["if_refining_learning_goal"]:
                st.write("**✨ Refining learning goal...**")
        prev_col, space_col, continue_col = st.columns([3, 10, 3])
        with prev_col:
            if st.button("Previous", key="gm_nav_prev", use_container_width=True):
                st.session_state["onboarding_card_index"] = max(0, idx - 1)
                try:
                    save_persistent_state()
                except Exception:
                    pass
                st.rerun()
        with continue_col:
            render_continue_button(goal)
        



def render_information(goal):
    idx = st.session_state.get("onboarding_card_index", 0)
    with st.container(border=True):
        st.subheader("Share Your Information")
        st.info("🧠 Please provide your information (Text or PDF) to enhance personalized experience")

        persona_names = list(PERSONAS.keys())
        current_persona = st.session_state.get("learner_persona", "")
        try:
            persona_index = persona_names.index(current_persona)
        except ValueError:
            persona_index = None
        selected_persona = st.selectbox(
            "Select your learning persona",
            persona_names,
            index=persona_index,
            format_func=lambda name: f"{name} — {PERSONAS[name]['description']}",
        )
        if selected_persona is not None:
            st.session_state["learner_persona"] = selected_persona
        else:
            st.session_state["learner_persona"] = ""
        try:
            save_persistent_state()
        except Exception:
            pass
        upload_col, information_col = st.columns([1, 1])
        with upload_col:
            uploaded_file = st.file_uploader("[Optional] Upload a PDF with your information (e.g., resume)", type="pdf")
            if uploaded_file is not None:
                with st.spinner("Extracting text from PDF..."):
                    learner_information_pdf = extract_text_from_pdf(uploaded_file)
                    st.toast("✅ PDF uploaded successfully.")
            else:
                learner_information_pdf = ""
        with information_col:
            learner_information_text = st.text_area("[Optional] Enter your learning perferences and style", value=st.session_state["learner_information_text"], label_visibility="visible", height=77)
            persona_name = st.session_state.get("learner_persona", "")
            if persona_name and persona_name in PERSONAS:
                dims = PERSONAS[persona_name]["fslsm_dimensions"]
                persona_prefix = (
                    f"Learning Persona: {persona_name} "
                    f"(initial FSLSM: processing={dims['fslsm_processing']}, "
                    f"perception={dims['fslsm_perception']}, "
                    f"input={dims['fslsm_input']}, "
                    f"understanding={dims['fslsm_understanding']}). "
                )
            else:
                persona_prefix = ""
            st.session_state["learner_information"] = persona_prefix + learner_information_text + learner_information_pdf
            try:
                save_persistent_state()
            except Exception:
                pass
        # st.divider()
        space_col, next_button_col = st.columns([13, 3])
        save_persistent_state()
        with next_button_col:
            if st.button("Next", key="gm_nav_next", use_container_width=True, type="primary"):
                st.session_state["onboarding_card_index"] = min(1, idx + 1)
                try:
                    save_persistent_state()
                except Exception:
                    pass
                st.rerun()

def render_continue_button(goal):
    if st.button("Save & Continue", type="primary"):
        if not goal["learning_goal"] or not st.session_state.get("learner_persona"):
            st.warning("Please provide both a learning goal and select a learning persona before continuing.")
        else:
            st.session_state["selected_page"] = "Skill Gap"
            try:
                save_persistent_state()
            except Exception:
                pass
            st.switch_page("pages/skill_gap.py")


def render_cards_with_nav(goal):
    """Show either the Information or Goal section as a card with nav buttons."""
    idx = st.session_state.get("onboarding_card_index", 0)

    if idx == 0:
        render_information(goal)
    else:
        render_goal(goal)

render_onboard()