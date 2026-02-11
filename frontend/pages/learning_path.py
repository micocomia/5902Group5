import time
import math
import streamlit as st
from components.skill_info import render_skill_info
from utils.request_api import (
    schedule_learning_path,
    reschedule_learning_path,
    simulate_path_feedback,
    refine_learning_path_with_feedback,
    iterative_refine_learning_path,
)
from components.navigation import render_navigation
from utils.state import save_persistent_state


def _store_agent_reasoning(result, context: str = ""):
    """Store any agent reasoning/trace returned by backend into Streamlit session_state.

    This enables the main sidebar 'Agent reasoning' panel (or any page) to display it.
    Safe for string/dict/list responses.
    """
    if result is None:
        return

    payload = None
    raw = None

    if isinstance(result, dict):
        raw = result
        # Common keys teams use
        for k in ("reasoning", "rationale", "explanation", "agent_reasoning"):
            v = result.get(k)
            if v:
                payload = v
                break

        # Fallback: trace-like structures
        if payload is None:
            for k in ("trace", "traces", "debug_trace", "steps", "chain", "log"):
                v = result.get(k)
                if v:
                    payload = v
                    break

    # If backend returns list/string directly
    elif isinstance(result, (list, str)):
        payload = result

    if payload is not None:
        st.session_state["agent_reasoning"] = payload
        if context:
            st.session_state["agent_reasoning_context"] = context
        if raw is not None:
            st.session_state["agent_reasoning_raw_response"] = raw

def render_learning_path():
    if not st.session_state.get("if_complete_onboarding"):
        st.switch_page("pages/onboarding.py")

    goal = st.session_state["goals"][st.session_state["selected_goal_id"]]
    save_persistent_state()
    if not goal["learning_goal"] or not st.session_state["learner_information"]:
        st.switch_page("pages/onboarding.py")
    else:
        if not goal["skill_gaps"]:
            st.switch_page("pages/skill_gap.py")

    st.title("Learning Path")
    st.write("Track your learning progress through the sessions below.")

    st.markdown("""
        <style>
        .card-header {
            color: #333;
            font-weight: bold;
            margin-bottom: 10px;
        }
        </style>
    """, unsafe_allow_html=True)
    if not goal["learning_path"]:
        with st.spinner('Scheduling Learning Path ...'):
            result = schedule_learning_path(goal["learner_profile"], session_count=8)
            _store_agent_reasoning(result, "schedule_learning_path")
            goal["learning_path"] = result.get("learning_path", result) if isinstance(result, dict) else result
            save_persistent_state()
            st.toast("🎉 Successfully schedule learning path!")
            st.rerun()
    else:
        render_overall_information(goal)
        render_path_feedback_section(goal)
        render_learning_sessions(goal)


def render_overall_information(goal):
    with st.container(border=True):
        st.write("#### 🎯 Current Goal")
        st.text_area("In-progress Goal", value=goal["learning_goal"], disabled=True, help="Change this in the Goal Management section.")
        learned_sessions = sum(1 for s in goal["learning_path"] if s["if_learned"])
        total_sessions = len(goal["learning_path"])
        if total_sessions == 0:
            st.warning("No learning sessions found.")
            progress = 0
        else:
            progress = int((learned_sessions / total_sessions) * 100)
        st.write("#### 📊 Overall Progress")
        with st.container():
            st.progress(progress)
            st.write(f"{learned_sessions}/{total_sessions} sessions completed ({progress}%)")

            if learned_sessions == total_sessions:
                st.success("🎉 Congratulations! All sessions are complete.")
                st.balloons()
            else:
                st.info("🚀 Keep going! You’re making great progress.")
        with st.expander("View Skill Details", expanded=False):
            render_skill_info(goal["learner_profile"])

def render_path_feedback_section(goal):
    goal_id = st.session_state["selected_goal_id"]
    cache_key = f"feedback_{goal_id}"

    with st.expander("AI Path Evaluation & Refinement", expanded=False):
        st.info("Get AI-simulated learner feedback on your learning path and refine it before starting.")

        col1, col2, col3 = st.columns([2, 2, 2])
        with col1:
            if st.button("Simulate Feedback", type="primary", use_container_width=True):
                st.session_state["if_simulating_feedback"] = True
                save_persistent_state()
                st.rerun()

        with col2:
            if st.button("Refine Path", type="secondary", use_container_width=True,
                        disabled=cache_key not in st.session_state.get("path_feedback_cache", {})):
                st.session_state["if_refining_path"] = True
                save_persistent_state()
                st.rerun()

        with col3:
            iteration_count = st.selectbox("Iterations", options=[1, 2, 3, 4, 5], index=1, key="auto_refine_iterations")
            if st.button("Auto-Refine", type="secondary", use_container_width=True):
                with st.spinner(f'Auto-refining path ({iteration_count} iterations)...'):
                    result = iterative_refine_learning_path(
                        goal["learner_profile"],
                        goal["learning_path"],
                        max_iterations=iteration_count
                    )
                    _store_agent_reasoning(result, 'iterative_refine_learning_path')
                    if result and result.get("final_learning_path"):
                        goal["learning_path"] = result["final_learning_path"]
                        # Clear feedback cache after refinement
                        if cache_key in st.session_state.get("path_feedback_cache", {}):
                            del st.session_state["path_feedback_cache"][cache_key]
                        save_persistent_state()
                        st.toast(f"Path refined through {iteration_count} iterations!")
                        # Display iteration history
                        for iteration in result.get("iterations", []):
                            st.write(f"**Iteration {iteration['iteration']}:**")
                            feedback = iteration.get("feedback", {})
                            if isinstance(feedback, dict):
                                fb = feedback.get("feedback", {})
                                st.write(f"- Progression: {fb.get('progression', 'N/A')}")
                                st.write(f"- Engagement: {fb.get('engagement', 'N/A')}")
                        st.rerun()
                    else:
                        st.error("Failed to auto-refine path.")

        # Handle simulating feedback
        if st.session_state.get("if_simulating_feedback"):
            with st.spinner('Simulating learner feedback...'):
                feedback = simulate_path_feedback(goal["learner_profile"], goal["learning_path"])
                _store_agent_reasoning(feedback, 'simulate_path_feedback')
                if feedback:
                    if "path_feedback_cache" not in st.session_state:
                        st.session_state["path_feedback_cache"] = {}
                    st.session_state["path_feedback_cache"][cache_key] = feedback
                    st.session_state["if_simulating_feedback"] = False
                    save_persistent_state()
                    st.toast("Feedback simulated successfully!")
                    st.rerun()
                else:
                    st.session_state["if_simulating_feedback"] = False
                    st.error("Failed to simulate feedback.")

        # Handle refining path
        if st.session_state.get("if_refining_path"):
            cached_feedback = st.session_state.get("path_feedback_cache", {}).get(cache_key)
            if cached_feedback:
                with st.spinner('Refining learning path...'):
                    refined_path = refine_learning_path_with_feedback(goal["learning_path"], cached_feedback)
                    _store_agent_reasoning(refined_path, 'refine_learning_path_with_feedback')
                    if refined_path:
                        goal["learning_path"] = refined_path.get("learning_path", refined_path)
                        # Clear feedback cache after refinement
                        del st.session_state["path_feedback_cache"][cache_key]
                        st.session_state["if_refining_path"] = False
                        save_persistent_state()
                        st.toast("Learning path refined successfully!")
                        st.rerun()
                    else:
                        st.session_state["if_refining_path"] = False
                        st.error("Failed to refine path.")
            else:
                st.session_state["if_refining_path"] = False

        # Display cached feedback if available
        cached_feedback = st.session_state.get("path_feedback_cache", {}).get(cache_key)
        if cached_feedback:
            st.write("---")
            st.write("**Simulated Feedback:**")

            feedback_data = cached_feedback.get("feedback", cached_feedback) if isinstance(cached_feedback, dict) else {}
            suggestions_data = cached_feedback.get("suggestions", {}) if isinstance(cached_feedback, dict) else {}

            # 3-column layout for feedback
            fb_col1, fb_col2, fb_col3 = st.columns(3)
            with fb_col1:
                st.metric("Progression", "")
                progression_fb = feedback_data.get("progression", "N/A") if isinstance(feedback_data, dict) else "N/A"
                st.write(progression_fb)
            with fb_col2:
                st.metric("Engagement", "")
                engagement_fb = feedback_data.get("engagement", "N/A") if isinstance(feedback_data, dict) else "N/A"
                st.write(engagement_fb)
            with fb_col3:
                st.metric("Personalization", "")
                personalization_fb = feedback_data.get("personalization", "N/A") if isinstance(feedback_data, dict) else "N/A"
                st.write(personalization_fb)

            # Display suggestions
            if suggestions_data and isinstance(suggestions_data, dict):
                st.write("---")
                st.write("**Improvement Suggestions:**")
                for key, suggestion in suggestions_data.items():
                    if suggestion:
                        st.info(f"**{key.title()}:** {suggestion}")


def render_learning_sessions(goal):
    st.write("#### 📖 Learning Sessions")
    total_sessions = len(goal["learning_path"])
    with st.expander("Re-schedule Learning Path", expanded=False):
        st.info("Customize your learning path by re-scheduling sessions or marking them as complete.")
        expected_session_count = st.number_input("Expected Sessions", min_value=0, max_value=10, value=total_sessions)
        st.session_state["expected_session_count"] = expected_session_count
        try:
            save_persistent_state()
        except Exception:
            pass
        if st.button("Re-schedule Learning Path", type="primary"):
            st.session_state["if_rescheduling_learning_path"] = True
            try:
                save_persistent_state()
            except Exception:
                pass
            st.rerun()
        if st.session_state.get("if_rescheduling_learning_path"):
            with st.spinner('Re-scheduling Learning Path ...'):
                result = reschedule_learning_path(goal["learning_path"], goal["learner_profile"], expected_session_count)
                _store_agent_reasoning(result, 'reschedule_learning_path')
                goal["learning_path"] = result.get('learning_path', result) if isinstance(result, dict) else result
                st.session_state["if_rescheduling_learning_path"] = False
                try:
                    save_persistent_state()
                except Exception:
                    pass
                st.toast("🎉 Successfully re-schedule learning path!")
                st.rerun()
    save_persistent_state()
    columns_spec = 2
    num_columns = math.ceil(len(goal["learning_path"]) / columns_spec)  
    columns_list = [st.columns(columns_spec, gap="large") for _ in range(num_columns)]
    for sid, session in enumerate(goal["learning_path"]):
        session_column = columns_list[sid // columns_spec]
        with session_column[sid % columns_spec]:
            with st.container(border=True):
                text_color = "#5ecc6b" if session["if_learned"] else "#fc7474"

                st.markdown(f"<div class='card'><div class='card-header' style='color: {text_color};'>{sid+1}: {session['title']}</div>", unsafe_allow_html=True)

                with st.expander("View Session Details", expanded=False):
                    st.info(session["abstract"])
                    st.write("**Associated Skills & Desired Proficiency:**")
                    for skill_outcome in session["desired_outcome_when_completed"]:
                        st.write(f"- {skill_outcome['name']} (`{skill_outcome['level']}`)")

                col1, col2 = st.columns([5, 3])
                with col1:
                    if_learned_key = f"if_learned_{session['id']}"
                    old_if_learned = session["if_learned"]
                    session_status_hint = "Keep Learning" if not session["if_learned"] else "Completed"
                    session_if_learned = st.toggle(session_status_hint, value=session["if_learned"], key=if_learned_key, disabled=True)
                    goal["learning_path"][sid]["if_learned"] = session_if_learned
                    save_persistent_state()
                    if session_if_learned != old_if_learned:
                        st.rerun()

                with col2:
                    if not session["if_learned"]:
                        start_key = f"start_{session['id']}_{session['if_learned']}"
                        if st.button("Learning", key=start_key, use_container_width=True, type="primary", icon=":material/local_library:"):
                            st.session_state["selected_session_id"] = sid
                            st.session_state["selected_point_id"] = 0
                            st.session_state["selected_page"] = "Knowledge Document"
                            save_persistent_state()
                            st.switch_page("pages/knowledge_document.py")
                    else:
                        start_key = f"start_{session['id']}_{session['if_learned']}"
                        if st.button("Completed", key=start_key, use_container_width=True, type="secondary", icon=":material/done_outline:"):
                            st.session_state["selected_session_id"] = sid
                            st.session_state["selected_point_id"] = 0
                            st.session_state["selected_page"] = "Knowledge Document"
                            save_persistent_state()
                            st.switch_page("pages/knowledge_document.py")


render_learning_path()