import time
import json
import httpx
import streamlit as st

from components.topbar import render_topbar
from config import backend_endpoint, use_mock_data
from components.gap_identification import render_identifying_skill_gap, render_identified_skill_gap
from utils.state import add_new_goal, get_new_goal_uid, reset_to_add_goal, save_persistent_state
from utils.request_api import identify_skill_gap, create_learner_profile


def render_skill_gap():
    # ✅ Guard: users can refresh or land directly on this page, so session keys may be missing
    goal = st.session_state.get("to_add_goal")
    if not goal:
        st.warning("No active goal found in session. Redirecting to onboarding...")
        st.switch_page("pages/onboarding.py")
        return

    if not goal.get("learning_goal") or not st.session_state.get("learner_information"):
        st.switch_page("pages/onboarding.py")
        return

    # ---------------------------
    # DEBUG SIDEBAR (PATCH)
    # ---------------------------
    st.session_state.setdefault("debug_api", False)
    with st.sidebar:
        with st.expander("Debug (API)", expanded=False):
            st.session_state["debug_api"] = st.checkbox(
                "Enable API debug mode",
                value=st.session_state["debug_api"],
                help="Shows endpoint/payload preview and enables deeper error visibility (requires small patch in request_api/component to print raw response)."
            )
            st.write("Backend endpoint:", backend_endpoint)
            st.write("UserId:", st.session_state.get("userId"))
            st.write("Goal UID (new):", get_new_goal_uid())
            st.write("Learning goal:", goal.get("learning_goal"))

            # Payload previews (so you can verify contract quickly)
            st.subheader("Payload preview: identify_skill_gap")
            st.json({
                "learning_goal": goal.get("learning_goal"),
                "learner_information": st.session_state.get("learner_information"),
                "user_id": st.session_state.get("userId"),
                "goal_id": get_new_goal_uid(),
            })

            st.subheader("Payload preview: create_learner_profile")
            st.json({
                "learning_goal": goal.get("learning_goal"),
                "learner_information": st.session_state.get("learner_information"),
                "skill_gaps": goal.get("skill_gaps", []),
                "user_id": st.session_state.get("userId"),
                "goal_id": get_new_goal_uid(),
            })

        with st.sidebar.expander("Debug (API) — Last request/response", expanded=True):
            last = st.session_state.get("api_debug_last")
            if not last:
                st.info("No API calls captured yet.")
            else:
                st.write("Time:", last.get("ts"))
                st.write("URL:", last.get("url"))
                st.write("Status:", last.get("status"))
                st.caption("Request JSON")
                st.json(last.get("request_json"))
                st.caption("Response")
                st.code(last.get("response_text", ""))


    left, center, right = st.columns([1, 5, 1])
    with center:
        # render_topbar()
        st.title("Skill Gap")
        st.write("Review and confirm your skill gaps.")

        skill_gaps = goal.get("skill_gaps") or []
        if not skill_gaps:
            # ---------------------------
            # TRY/CATCH around the component call (PATCH)
            # ---------------------------
            try:
                render_identifying_skill_gap(goal)
            except Exception as e:
                st.error("Skill gap UI crashed while identifying skill gaps.")
                st.exception(e)
                st.stop()
        else:
            num_skills = len(skill_gaps)
            num_gaps = sum(1 for skill in skill_gaps if skill["is_gap"])
            st.info(f"There are {num_skills} skills in total, with {num_gaps} skill gaps identified.")
            render_identified_skill_gap(goal)

            if_schedule_learning_path_ready = skill_gaps
            space_col, continue_button_col = st.columns([1, 0.27])
            with continue_button_col:
                if st.button("Schedule Learning Path", type="primary", disabled=not if_schedule_learning_path_ready):
                    if skill_gaps and not goal.get("learner_profile"):
                        with st.spinner('Creating your profile ...'):
                            # ---------------------------
                            # TRY/CATCH around backend call (PATCH)
                            # ---------------------------
                            try:
                                learner_profile = create_learner_profile(
                                    goal["learning_goal"],
                                    st.session_state["learner_information"],
                                    skill_gaps,
                                    user_id=st.session_state.get("userId"),
                                    goal_id=get_new_goal_uid()
                                )
                            except Exception as e:
                                st.error("Backend call failed while creating learner profile.")
                                st.exception(e)
                                st.stop()

                            if learner_profile is None:
                                st.rerun()
                            goal["learner_profile"] = learner_profile
                            st.toast("🎉 Your profile has been created!")

                    new_goal_id = add_new_goal(**goal)
                    st.session_state["selected_goal_id"] = new_goal_id
                    st.session_state["if_complete_onboarding"] = True
                    st.session_state["selected_page"] = "Learning Path"
                    save_persistent_state()
                    st.switch_page("pages/learning_path.py")


render_skill_gap()