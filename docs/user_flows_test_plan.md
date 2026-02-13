# GenMentor — User Flows, Backend Tests & Frontend Verification Plan

> **Purpose:** This document lists each user flow's **user story**, the **backend test script** that covers it, and the **Streamlit frontend test steps** to manually verify the flow end-to-end.
>
> **How to use:** Copy this into a Google Doc so your team can check off steps and leave comments on possible bugs.

---

## Table of Contents

1. [Flow 1 — User Login / Logout](#flow-1--user-login--logout)
2. [Flow 2A — Picking a Persona](#flow-2a--picking-a-persona)
3. [Flow 2B — Uploading a Resume](#flow-2b--uploading-a-resume)
4. [Flow 2C — Setting a Learning Goal](#flow-2c--setting-a-learning-goal)
5. [Flow 2D — Refining a Learning Goal](#flow-2d--refining-a-learning-goal)
6. [Flow 2E — Determining Skill Gap & Identifying Current Level](#flow-2e--determining-skill-gap--identifying-current-level)
7. [Flow 3 — User Account Deletion](#flow-3--user-account-deletion)

---

## Flow 1 — User Login / Logout

### User Story

> **As a** learner,
> **I want to** register a new account, log in with my credentials, and log out,
> **so that** my learning progress is saved to my personal account and I can securely access it across sessions.

### Backend Test Scripts

| Test file | Class / Tests | What it covers |
|---|---|---|
| `backend/tests/test_store_and_auth.py` | `TestAuthStore` (10 tests) | User creation, password hashing (bcrypt), password verification, duplicate detection, user deletion, disk persistence |
| `backend/tests/test_store_and_auth.py` | `TestAuthJWT` (5 tests) | JWT token creation, verification, different users get different tokens, invalid/tampered/expired tokens return `None` |
| `backend/tests/test_auth_api.py` | `TestRegisterEndpoint` (6 tests) | `POST /auth/register` — success, returns valid JWT, rejects short username (<3 chars), rejects short password (<6 chars), rejects duplicate username (409), creates user in store |
| `backend/tests/test_auth_api.py` | `TestLoginEndpoint` (5 tests) | `POST /auth/login` — success, returns valid JWT, wrong password (401), nonexistent user (401), login after register |
| `backend/tests/test_auth_api.py` | `TestAuthMeEndpoint` (4 tests) | `GET /auth/me` — valid token returns username, invalid token (401), no token (401), works with login token |
| `backend/tests/test_auth_api.py` | `TestFullAuthLifecycle` (1 test) | End-to-end: register → login → verify token → create data → delete → verify gone |

**Run command:**
```bash
python -m pytest backend/tests/test_store_and_auth.py backend/tests/test_auth_api.py -v
```

### Streamlit Frontend Test Steps

#### 1.1 — Register a new account

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Start the app (`streamlit run frontend/main.py`). Ensure backend is running. | App loads, shows the Onboarding page with a top bar |
| 2 | Click the **account icon** (top-right) | "Login / Register" dialog opens |
| 3 | Click the **Register** tab | Registration form is shown with username, password, confirm password fields |
| 4 | Enter a username shorter than 3 characters, fill password fields, click **Register** | Error: "Username must be at least 3 characters." |
| 5 | Enter a valid username, enter a password shorter than 6 characters, click **Register** | Error: "Password must be at least 6 characters." |
| 6 | Enter valid username, enter mismatched passwords, click **Register** | Error: "Passwords do not match." |
| 7 | Enter valid username (e.g., `testuser1`), matching passwords (e.g., `pass123456`), click **Register** | Dialog closes, app reruns, user is now logged in (account icon shows popover with "Signed in as **testuser1**") |
| 8 | Try registering again with the same username | Error: "Username already exists. Please choose another." |

#### 1.2 — Log in with existing account

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | If logged in, click account icon → **Log-out** | App returns to logged-out state |
| 2 | Click account icon → **Login** tab | Login form shown with username and password fields |
| 3 | Enter wrong password, click **Login** | Error: "Invalid username or password." |
| 4 | Enter correct credentials (the user you just registered), click **Login** | Dialog closes, app reruns, user is logged in. If user has previous progress, it is restored |
| 5 | Click account icon | Popover shows "Signed in as **testuser1**" |

#### 1.3 — Log out

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | While logged in, click the account icon (top-right) | Popover with username and "Log-out" button appears |
| 2 | Click **Log-out** | App reruns. Login/Register button is visible again. Onboarding page shown (no user-specific data visible) |
| 3 | Click account icon | Should show login dialog again (not the logged-in popover) |

---

## Flow 2A — Picking a Persona

### User Story

> **As a** new learner going through onboarding,
> **I want to** select a learning persona that matches my learning style,
> **so that** the platform adapts its content and teaching style to how I learn best.

### Backend Test Scripts

Persona selection happens entirely on the frontend — the selected persona's FSLSM dimensions are embedded into the `learner_information` string and persisted via the user-state endpoints.

| Test file | Class / Tests | What it covers |
|---|---|---|
| `backend/tests/test_user_state.py` | `TestUserStateStore` (11 tests) | `put_user_state` / `get_user_state` — the mechanism that persists persona selection (stored as part of `learner_persona` and `learner_information` keys) |
| `backend/tests/test_user_state.py` | `TestUserStateAPI` (8 tests) | `PUT /user-state/{user_id}` and `GET /user-state/{user_id}` API endpoints — verifies the persona and all session state roundtrips correctly |

**Run command:**
```bash
python -m pytest backend/tests/test_user_state.py -v
```

### Streamlit Frontend Test Steps

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Log in (or register). Ensure onboarding is not yet completed. | Onboarding page loads, "Share Your Information" card is visible |
| 2 | Observe the **"Select your learning persona"** dropdown | Dropdown lists 5 personas: "Hands-on Explorer", "Reflective Reader", "Visual Learner", "Conceptual Thinker", "Balanced Learner" — each with a description |
| 3 | Select **"Hands-on Explorer"** | Dropdown updates to show the selection. Session state `learner_persona` is set to "Hands-on Explorer" |
| 4 | Change selection to **"Reflective Reader"** | Dropdown updates. The `learner_information` string should now contain "Learning Persona: Reflective Reader (initial FSLSM: processing=0.7, perception=0.5, input=0.7, understanding=0.5)" |
| 5 | Click **Next** to go to the Goal card, then click **Previous** to come back | Persona selection should be preserved (still shows "Reflective Reader") |
| 6 | Log out, then log back in | Persona selection should be restored from backend persistence |
| 7 | Attempt to click **Save & Continue** on the goal page without selecting a persona | Warning: "Please provide both a learning goal and select a learning persona before continuing." |

---

## Flow 2B — Uploading a Resume

### User Story

> **As a** learner during onboarding,
> **I want to** upload my resume or relevant PDF document,
> **so that** the platform can understand my background, skills, and experience to better personalize my learning path.

### Backend Test Scripts

| Test file | Class / Tests | What it covers |
|---|---|---|
| `backend/tests/test_onboarding_api.py` | `TestExtractPdfText` (3 tests) | `POST /extract-pdf-text` — valid PDF returns extracted text, multi-page PDF concatenates all pages, missing file returns 422 |
| `backend/tests/test_user_state.py` | `TestUserStateStore` | Verifies that the extracted PDF text (stored in `learner_information_pdf` key) persists correctly via user-state |

**Run command:**
```bash
python -m pytest backend/tests/test_onboarding_api.py::TestExtractPdfText backend/tests/test_user_state.py -v
```

### Streamlit Frontend Test Steps

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Navigate to Onboarding → "Share Your Information" card | PDF upload area is visible: "[Optional] Upload a PDF with your information (e.g., resume)" |
| 2 | Click the upload area and select a valid PDF file (e.g., a resume) | Spinner appears: "Extracting text from PDF...". After a moment, toast message: "PDF uploaded successfully." |
| 3 | Observe the `learner_information` value (visible in debug sidebar or by checking state) | The extracted PDF text is appended to the `learner_information` string after the persona prefix and any manual text |
| 4 | Try uploading a non-PDF file (e.g., a .docx or .txt) | File uploader rejects it — only `.pdf` files accepted |
| 5 | Upload a multi-page PDF | All pages' text should be extracted and included |
| 6 | Continue through onboarding to the skill gap step | The `learner_information` passed to `POST /identify-skill-gap-with-info` should include the resume text, which means the AI should reference your background when identifying skill gaps |
| 7 | Do NOT upload a PDF (leave it empty), proceed through onboarding | Flow should work normally — PDF is optional. `learner_information_pdf` should be empty string |

---

## Flow 2C — Setting a Learning Goal

### User Story

> **As a** learner during onboarding,
> **I want to** enter my learning goal (e.g., "Become an HR Manager" or "Learn Python for data science"),
> **so that** the platform can create a personalized learning path tailored to my specific objective.

### Backend Test Scripts

Goal setting is a frontend-only action that stores the goal text in session state. The goal is sent to the backend when the skill gap identification or profile creation endpoint is called.

| Test file | Class / Tests | What it covers |
|---|---|---|
| `backend/tests/test_user_state.py` | `TestUserStateStore`, `TestUserStateAPI` | Verifies the `goals` list and `to_add_goal` state persist correctly via the user-state mechanism |
| `backend/tests/test_onboarding_api.py` | `TestIdentifySkillGapEndpoint` | Verifies the `learning_goal` string is correctly passed to and processed by `POST /identify-skill-gap-with-info` |
| `backend/tests/test_onboarding_api.py` | `TestCreateLearnerProfileEndpoint` | Verifies the `learning_goal` is included in the profile created by `POST /create-learner-profile-with-info` |

**Run command:**
```bash
python -m pytest backend/tests/test_user_state.py backend/tests/test_onboarding_api.py -v
```

### Streamlit Frontend Test Steps

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | On the Onboarding page, complete "Share Your Information" card and click **Next** | "Set Learning Goal" card appears with a text area and AI Refinement button |
| 2 | Leave the goal text area empty and click **Save & Continue** | Warning: "Please provide both a learning goal and select a learning persona before continuing." |
| 3 | Enter a learning goal (e.g., "I want to become an HR Manager with expertise in HRIS systems") | Text area updates, goal is stored in `to_add_goal["learning_goal"]` |
| 4 | Click **Save & Continue** (with persona already selected) | App navigates to the Skill Gap page. The goal text is used for skill gap identification |
| 5 | Click **Previous** before saving | Returns to "Share Your Information" card. Goal text should be preserved |
| 6 | Log out and log back in (after entering a goal but before saving) | Goal text should be restored from persisted state |

---

## Flow 2D — Refining a Learning Goal

### User Story

> **As a** learner setting up my learning goal,
> **I want to** use AI to refine and improve my initial goal description,
> **so that** my goal is clearer, more actionable, and better suited for generating an effective learning path.

### Backend Test Scripts

| Test file | Class / Tests | What it covers |
|---|---|---|
| `backend/tests/test_onboarding_api.py` | `TestRefineGoalEndpoint` (4 tests) | `POST /refine-learning-goal` — success (mocked LLM), verifies `learner_information` is forwarded, works with empty learner info, LLM failure returns 500 |

**Run command:**
```bash
python -m pytest backend/tests/test_onboarding_api.py::TestRefineGoalEndpoint -v
```

### Streamlit Frontend Test Steps

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Navigate to Onboarding → "Set Learning Goal" card | Goal text area and **"✨ AI Refinement"** button are visible |
| 2 | Enter a vague goal (e.g., "learn about HR stuff") | Text area shows the goal |
| 3 | Click **"✨ AI Refinement"** | Button becomes disabled. Hint text appears: "✨ Refining learning goal...". After a few seconds, the goal text area updates with a refined, more specific version (e.g., "Develop comprehensive HR management competencies including talent acquisition, employee relations, compensation and benefits administration, and HRIS systems management") |
| 4 | Observe the refined goal | Toast: "Refined Learning goal successfully." Goal text area now contains the AI-refined version |
| 5 | Try clicking **"✨ AI Refinement"** again | The button should be re-enabled. You can refine again to iterate further |
| 6 | Edit the refined goal manually, then click **Save & Continue** | The manually edited version of the refined goal is used (not the original) |
| 7 | Click **"✨ AI Refinement"** with no learner information filled | Refinement should still work but may be less personalized |

---

## Flow 2E — Determining Skill Gap & Identifying Current Level

### User Story

> **As a** learner who has set a learning goal,
> **I want to** have the platform identify the skills required for my goal, determine my current skill levels (using my resume if available), and highlight the gaps,
> **so that** I can see exactly where I need to improve and get a learning path focused on my actual weaknesses.

### Backend Test Scripts

| Test file | Class / Tests | What it covers |
|---|---|---|
| `backend/tests/test_onboarding_api.py` | `TestIdentifySkillGapEndpoint` (4 tests) | `POST /identify-skill-gap-with-info` — success (mocked LLM), verifies each gap has required fields (name, is_gap, required_level, current_level), works with pre-existing skill requirements, LLM failure returns 500 |
| `backend/tests/test_onboarding_api.py` | `TestCreateLearnerProfileEndpoint` (3 tests) | `POST /create-learner-profile-with-info` — creates profile with cognitive_status/learning_preferences/behavioral_patterns, stores in profile store when user_id provided, does not store without user_id |
| `backend/tests/test_onboarding_api.py` | `TestProfileRetrieval` (4 tests) | `GET /profile/{user_id}` — get by goal_id, get all profiles for user, 404 for nonexistent user/goal |
| `backend/tests/test_onboarding_api.py` | `TestEventLogging` (3 tests) | `POST /events/log` — logs onboarding events, multiple events, auto-timestamps |
| `backend/tests/test_store_and_auth.py` | `TestProfilePersistence` (7 tests) | Profile upsert, get, overwrite, multiple goals per user, disk persistence, reload |

**Run command:**
```bash
python -m pytest backend/tests/test_onboarding_api.py backend/tests/test_store_and_auth.py::TestProfilePersistence -v
```

### Streamlit Frontend Test Steps

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Complete onboarding (persona + goal) and click **Save & Continue** | App navigates to the **Skill Gap** page. Spinner appears: "Identifying Skill Gap ..." |
| 2 | Wait for skill gap identification to complete | Page updates to show a list of skills with: skill name, required level, current level, gap status (red/green), reason, confidence |
| 3 | Verify summary text | Info banner: "There are X skills in total, with Y skill gaps identified." |
| 4 | Check each skill card | Each card shows: skill name (numbered), **Required Level** pill selector (unlearned/beginner/intermediate/advanced), **Current Level** pill selector, colored header (red = gap, green = no gap) |
| 5 | Expand **"More Analysis Details"** on a skill | Shows reason and confidence level. Shows warning if current < required, success message if current >= required |
| 6 | Change a skill's **Current Level** from "beginner" to "advanced" (higher than required) | Card header turns green. Gap toggle auto-disables. "Mark as Gap" toggle reflects the change. State saves automatically |
| 7 | Change a skill's **Required Level** to a higher value than current | Card header turns red. Skill is marked as a gap |
| 8 | Toggle **"Mark as Gap"** off on a gap skill | Gap is removed, current level is set to match required level |
| 9 | Verify resume influence (if resume was uploaded) | If a resume was uploaded in onboarding, the AI should have used it to set more accurate current levels. For example, if your resume says "5 years Python experience", Python-related skills should show higher current levels |
| 10 | Click **"Schedule Learning Path"** | Spinner: "Creating your profile ...". After completion, toast: "Your profile has been created!". App navigates to the **Learning Path** page. Onboarding is marked as complete (`if_complete_onboarding = True`) |
| 11 | Navigate to **My Profile** page | The created learner profile should show: cognitive status (overall progress, mastered skills, in-progress skills), learning preferences (FSLSM dimensions matching your persona), behavioral patterns |

---

## Flow 3 — User Account Deletion

### User Story

> **As a** user who no longer wants to use the platform,
> **I want to** permanently delete my account and all associated data,
> **so that** my personal information, learning history, and profile are completely removed from the system.

### Backend Test Scripts

| Test file | Class / Tests | What it covers |
|---|---|---|
| `backend/tests/test_auth_api.py` | `TestDeleteAccountEndpoint` (7 tests) | `DELETE /auth/user` — success (200), removes user from auth store, removes all user data (profiles, events, state), preserves other users' data, rejects invalid token (401), rejects no token (401), login fails after deletion |
| `backend/tests/test_store_and_auth.py` | `TestDeleteAllUserData` (3 tests) | `delete_all_user_data()` — removes profiles (all goals), removes events, removes user state, preserves other users |
| `backend/tests/test_store_and_auth.py` | `TestAuthStore` → `test_delete_user*` (3 tests) | `delete_user()` — removes user, returns False for nonexistent, persists deletion to disk |
| `backend/tests/test_auth_api.py` | `TestFullAuthLifecycle` (1 test) | Full lifecycle: register → login → create data → delete → verify everything is gone → verify login fails |

**Run command:**
```bash
python -m pytest backend/tests/test_auth_api.py::TestDeleteAccountEndpoint backend/tests/test_auth_api.py::TestFullAuthLifecycle backend/tests/test_store_and_auth.py::TestDeleteAllUserData -v
```

### Streamlit Frontend Test Steps

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Log in with an account that has completed onboarding (has goals, profiles, learning data) | App loads with the Goal Management page and full learning data |
| 2 | Navigate to **My Profile** page | Profile page shows: learner information, learning goal, cognitive status, learning preferences, behavioral patterns. "Restart Onboarding" and "Delete Account" buttons are at the bottom |
| 3 | Click **"Delete Account"** (red button at bottom) | Confirmation dialog appears: "This action is permanent. Your account and all associated data will be deleted and cannot be recovered." with **Delete** and **Cancel** buttons |
| 4 | Click **Cancel** | Dialog closes. Account and data are unchanged. Profile still visible |
| 5 | Click **"Delete Account"** again, then click **Delete** | Backend call: `DELETE /auth/user`. Success message: "Account deleted successfully." App redirects to the main page (logged-out state) |
| 6 | Try logging in with the deleted account's credentials | Error: "Invalid username or password." — account no longer exists |
| 7 | Register a new account with the same username | Should succeed — the old account was fully removed |
| 8 | Verify no old data exists for the new account | New account starts fresh: no goals, no profiles, no learning history. Onboarding starts from scratch |

---

## Test Coverage Summary

### Backend Test Files

| File | Tests | Flows Covered |
|---|---|---|
| `backend/tests/test_store_and_auth.py` | 33 | Flow 1 (auth store/JWT), Flow 2A-2E (profile/event persistence), Flow 3 (data deletion) |
| `backend/tests/test_user_state.py` | 19 | Flow 2A (persona persistence), Flow 2B (resume text persistence), Flow 2C (goal persistence) |
| `backend/tests/test_auth_api.py` | 23 | Flow 1 (register/login/me endpoints), Flow 3 (delete account endpoint + lifecycle) |
| `backend/tests/test_onboarding_api.py` | 21 | Flow 2B (PDF extract), Flow 2D (goal refinement), Flow 2E (skill gap + profile creation + event logging) |
| `backend/tests/test_fslsm_update.py` | 2 | Flow 2A (FSLSM dimension updates — integration test, requires LLM API key) |
| **Total** | **98** | |

### Running All Tests

```bash
# Unit tests only (no LLM/API key required):
python -m pytest backend/tests/test_store_and_auth.py backend/tests/test_user_state.py -v

# API endpoint tests (requires full backend dependencies — langchain, etc.):
python -m pytest backend/tests/test_auth_api.py backend/tests/test_onboarding_api.py -v

# All tests:
python -m pytest backend/tests/ -v

# Integration test (requires LLM API key):
python -m pytest backend/tests/test_fslsm_update.py -v
```

### Notes for the Team

1. **API endpoint tests** (`test_auth_api.py`, `test_onboarding_api.py`, `test_user_state.py` API section) require the full backend dependency stack (langchain, etc.) because they import `from main import app`. Run these in the dev environment with all backend dependencies installed.

2. **LLM-dependent endpoint tests** (`test_onboarding_api.py`) use **mocked LLM functions** — they do NOT call real LLM APIs. This means they test the endpoint contract (request/response shapes, error handling, store persistence) without needing API keys.

3. **Integration tests** (`test_fslsm_update.py`) call real LLMs and require an OpenAI API key configured in the environment.

4. **Frontend tests** are manual — Streamlit does not have a built-in automated testing framework. Follow the step-by-step tables above, checking each expected result. Document any deviations as bugs.
