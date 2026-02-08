import math
import streamlit as st
from utils.request_api import create_learner_profile, update_learner_profile
from components.skill_info import render_skill_info
from components.navigation import render_navigation
from utils.pdf import extract_text_from_pdf
from streamlit_extras.tags import tagger_component 
from utils.state import save_persistent_state, delete_persistent_state


def render_learner_profile():
    # Title and introduction
    goal = st.session_state["goals"][st.session_state["selected_goal_id"]]

    st.title("Learner Profile")
    st.write("An overview of the learner's background, goals, progress, preferences, and behavioral patterns.")
    if not goal["learner_profile"]:
        with st.spinner('Identifying Skill Gap ...'):
            st.info("Please complete the onboarding process to view the learner profile.")
    else:
        try:
            render_learner_profile_info(goal)
        except Exception as e:
            st.error("An error occurred while rendering the learner profile.")
            # re generate the learner profile
            with st.spinner("Re-prepare your profile ..."):
                learner_profile = create_learner_profile(goal["learning_goal"], st.session_state["learner_information"], goal["skill_gaps"], st.session_state["llm_type"], user_id=st.session_state.get("userId"), goal_id=st.session_state.get("selected_goal_id"))
            goal["learner_profile"] = learner_profile
            try:
                save_persistent_state()
            except Exception:
                pass
            st.rerun()

def render_learner_profile_info(goal):
    st.markdown("""
        <style>
        .section {
            background-color: #f8f9fa;
            padding: 15px;
            margin: 10px 0;
            border-radius: 8px;
        }
        .progress-indicator {
            color: #28a745;
            font-weight: bold;
        }
        .skill-in-progress {
            color: #ffc107;
        }
        .skill-required {
            color: #dc3545;
        }
        </style>
    """, unsafe_allow_html=True)
    learner_profile = goal["learner_profile"]
    with st.container(border=True):
        # Learner Information
        st.markdown("#### 👤 Learner Information")
        st.markdown(f"<div class='section'>{learner_profile['learner_information']}</div>", unsafe_allow_html=True)

        # Learning Goal
        st.markdown("#### 🎯 Learning Goal")
        st.markdown(f"<div class='section'>{learner_profile['learning_goal']}</div>", unsafe_allow_html=True)

    with st.container(border=True):
        render_cognitive_status(goal)
    with st.container(border=True):
        render_learning_preferences(goal)
    with st.container(border=True):
        render_behavioral_patterns(goal)

    render_additional_info_form(goal)


def render_cognitive_status(goal):
    learner_profile = goal["learner_profile"]
    # Cognitive Status
    st.markdown("#### 🧠 Cognitive Status")
    st.write("**Overall Progress:**")
    st.progress(learner_profile["cognitive_status"]["overall_progress"])
    st.markdown(f"<p class='progress-indicator'>{learner_profile['cognitive_status']['overall_progress']}% completed</p>", unsafe_allow_html=True)
    render_skill_info(learner_profile)

def render_learning_preferences(goal):
    learner_profile = goal["learner_profile"]
    prefs = learner_profile['learning_preferences']
    st.markdown("#### 📚 Learning Preferences")

    # Display FSLSM dimensions
    st.write("**FSLSM Learning Style Dimensions:**")
    dims = prefs.get('fslsm_dimensions', {})
    dimension_labels = [
        ("fslsm_processing", "Active", "Reflective"),
        ("fslsm_perception", "Sensing", "Intuitive"),
        ("fslsm_input", "Visual", "Verbal"),
        ("fslsm_understanding", "Sequential", "Global"),
    ]
    for key, left_label, right_label in dimension_labels:
        value = dims.get(key, 0.0)
        col1, col2, col3 = st.columns([1, 3, 1])
        with col1:
            st.markdown(f"**{left_label}**")
        with col2:
            st.slider(
                label=key,
                min_value=-1.0,
                max_value=1.0,
                value=float(value),
                step=0.1,
                disabled=True,
                label_visibility="collapsed",
                key=f"fslsm_{key}",
            )
        with col3:
            st.markdown(f"**{right_label}**")

    # Display computed summaries derived from FSLSM dimensions
    perception = dims.get("fslsm_perception", 0.0)
    understanding = dims.get("fslsm_understanding", 0.0)
    processing = dims.get("fslsm_processing", 0.0)
    inp = dims.get("fslsm_input", 0.0)

    if perception <= -0.3:
        cs_part1 = "Concrete examples and practical applications"
    elif perception >= 0.3:
        cs_part1 = "Conceptual and theoretical explanations"
    else:
        cs_part1 = "A mix of practical and conceptual content"
    if understanding <= -0.3:
        cs_part2 = "presented in step-by-step sequences"
    elif understanding >= 0.3:
        cs_part2 = "with big-picture overviews first"
    else:
        cs_part2 = "balancing sequential detail and big-picture context"
    content_style = f"{cs_part1}, {cs_part2}"

    if processing <= -0.3:
        at_part1 = "Hands-on and interactive activities"
    elif processing >= 0.3:
        at_part1 = "Reading and observation-based learning"
    else:
        at_part1 = "A balance of interactive and reflective activities"
    if inp <= -0.3:
        at_part2 = "with diagrams, charts, and videos"
    elif inp >= 0.3:
        at_part2 = "with text-based materials and lectures"
    else:
        at_part2 = "using both visual and verbal materials"
    activity_type = f"{at_part1}, {at_part2}"

    st.write(f"**Content Style:** {content_style}")
    st.write(f"**Preferred Activity Type:** {activity_type}")

    st.write("**Additional Notes:**")
    st.info(prefs.get('additional_notes', 'None'))

def render_behavioral_patterns(goal):
    learner_profile = goal["learner_profile"]
    st.markdown("#### 📊 Behavioral Patterns")
    st.write(f"**System Usage Frequency:**")
    st.info(learner_profile['behavioral_patterns']['system_usage_frequency'])
    st.write(f"**Session Duration and Engagement:**")
    st.info(learner_profile['behavioral_patterns']['session_duration_engagement'])
    st.write(f"**Motivational Triggers:**")
    st.info(learner_profile['behavioral_patterns']['motivational_triggers'])
    st.write(f"**Additional Notes:**")
    st.info(learner_profile['behavioral_patterns']['additional_notes'])


def render_additional_info_form(goal):
    with st.form(key="additional_info_form"):
        st.markdown("#### Value Your Feedback")
        st.info("Help us improve your learning experience by providing your feedback below.")
        st.write("How much do you agree with the current profile?")
        agreement_star = st.feedback("stars", key="agreement_star")
        st.write("Do you have any suggestions or corrections?")
        suggestions = st.text_area("Provide your suggestions here.", label_visibility="collapsed")
        st.write("Do you have any additional information to add?")
        additional_info = st.text_area("Provide any additional information or feedback here.", label_visibility="collapsed")
        pdf_file = st.file_uploader("Upload a PDF with additional information (e.g., resume)", type="pdf")
        if pdf_file is not None:
            with st.spinner("Extracting text from PDF..."):
                additional_info_pdf = extract_text_from_pdf(pdf_file)
                st.toast("✅ PDF uploaded successfully.")
        else:
            additional_info_pdf = ""
        st.session_state["additional_info"] = {
            "agreement_star": agreement_star,
            "suggestions": suggestions,
            "additional_info": additional_info + additional_info_pdf
        }
        try:
            save_persistent_state()
        except Exception:
            pass
        submit_button = st.form_submit_button("Update Profile", on_click=update_learner_profile_with_additional_info, 
                                              kwargs={"goal": goal, "additional_info": additional_info, }, type="primary")
        
def update_learner_profile_with_additional_info(goal, additional_info):
    additional_info = st.session_state["additional_info"]
    new_learner_profile = update_learner_profile(goal["learner_profile"], additional_info, user_id=st.session_state.get("userId"), goal_id=st.session_state.get("selected_goal_id"))
    if new_learner_profile is not None:
        goal["learner_profile"] = new_learner_profile
        try:
            save_persistent_state()
        except Exception:
            pass
        st.toast("🎉 Successfully updated your profile!")
    else:
        st.toast("❌ Failed to update your profile. Please try again.")


@st.dialog("Confirm Restart Onboarding")
def show_restart_onboarding_dialog():
    st.warning("All your progress will be cleared and you will be taken back to onboarding.")
    st.divider()
    col_confirm, _space, col_cancel = st.columns([1, 2, 0.7])
    with col_confirm:
        if st.button("Confirm", type="primary"):
            # Keep the user logged in after clearing progress
            user_id = st.session_state.get("userId", "default")
            backend_ep = st.session_state.get("backend_endpoint")
            try:
                st.session_state["_autosave_enabled"] = False
            except Exception:
                pass
            try:
                delete_persistent_state()
            except Exception:
                pass
            try:
                st.session_state.clear()
            except Exception:
                pass
            st.session_state["logged_in"] = True
            st.session_state["userId"] = user_id
            if backend_ep:
                st.session_state["backend_endpoint"] = backend_ep
            try:
                st.switch_page("pages/onboarding.py")
            except Exception:
                st.rerun()
    with col_cancel:
        if st.button("Cancel"):
            try:
                st.rerun()
            except Exception:
                pass


render_learner_profile()

st.divider()
if st.button("Restart Onboarding", icon=":material/restart_alt:", help="Clear all progress and start onboarding from scratch (keeps a backup)"):
    show_restart_onboarding_dialog()