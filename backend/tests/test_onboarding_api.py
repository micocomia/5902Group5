"""Tests for onboarding-related API endpoints.

Covers the backend side of:
  - Flow 2B: PDF resume upload  (POST /extract-pdf-text)
  - Flow 2D: Goal refinement    (POST /refine-learning-goal)
  - Flow 2E: Skill gap ID       (POST /identify-skill-gap-with-info)
  - Profile creation             (POST /create-learner-profile-with-info)
  - Event logging                (POST /events/log)
  - Profile retrieval            (GET  /profile/{user_id})

LLM-dependent endpoints are tested with mocked LLM functions so
these tests run without API keys or network access.

Run from the repo root:
    python -m pytest backend/tests/test_onboarding_api.py -v
"""

import sys
import os
import io
import json
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi.testclient import TestClient
from utils import store, auth_store


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _isolate_store(tmp_path, monkeypatch):
    data_dir = tmp_path / "store_data"
    data_dir.mkdir()
    monkeypatch.setattr(store, "_DATA_DIR", data_dir)
    monkeypatch.setattr(store, "_PROFILES_PATH", data_dir / "profiles.json")
    monkeypatch.setattr(store, "_EVENTS_PATH", data_dir / "events.json")
    monkeypatch.setattr(store, "_USER_STATES_PATH", data_dir / "user_states.json")
    monkeypatch.setattr(store, "_profiles", {})
    monkeypatch.setattr(store, "_events", {})
    monkeypatch.setattr(store, "_user_states", {})


@pytest.fixture(autouse=True)
def _isolate_auth_store(tmp_path, monkeypatch):
    data_dir = tmp_path / "auth_data"
    data_dir.mkdir()
    monkeypatch.setattr(auth_store, "_DATA_DIR", data_dir)
    monkeypatch.setattr(auth_store, "_USERS_PATH", data_dir / "users.json")
    monkeypatch.setattr(auth_store, "_users", {})


@pytest.fixture()
def client():
    from main import app
    return TestClient(app)


# ---------------------------------------------------------------------------
# Shared mock return values
# ---------------------------------------------------------------------------

MOCK_REFINED_GOAL = {
    "refined_goal": "Become a certified HR Manager with expertise in HRIS systems and talent acquisition"
}

MOCK_SKILL_GAPS_RESULT = {
    "skill_gaps": [
        {
            "name": "HRIS Management",
            "is_gap": True,
            "required_level": "intermediate",
            "current_level": "beginner",
            "reason": "Limited hands-on experience with HRIS platforms",
            "level_confidence": "high",
        },
        {
            "name": "Communication",
            "is_gap": False,
            "required_level": "advanced",
            "current_level": "advanced",
            "reason": "Strong background from MBA program",
            "level_confidence": "high",
        },
    ]
}

MOCK_SKILL_REQUIREMENTS = {
    "skill_requirements": {
        "HRIS Management": "intermediate",
        "Communication": "advanced",
    }
}

MOCK_LEARNER_PROFILE = {
    "learner_information": "MBA grad with admin background",
    "learning_goal": "Become an HR Manager",
    "cognitive_status": {
        "overall_progress": 20,
        "mastered_skills": [
            {"name": "Communication", "proficiency_level": "advanced"}
        ],
        "in_progress_skills": [
            {
                "name": "HRIS Management",
                "required_proficiency_level": "intermediate",
                "current_proficiency_level": "beginner",
            }
        ],
    },
    "learning_preferences": {
        "fslsm_dimensions": {
            "fslsm_processing": -0.5,
            "fslsm_perception": -0.3,
            "fslsm_input": -0.5,
            "fslsm_understanding": -0.3,
        },
        "content_style": "Concrete examples and practical applications",
        "activity_type": "Hands-on and interactive activities",
        "additional_notes": "Prefers step-by-step guidance",
    },
    "behavioral_patterns": {
        "system_usage_frequency": "3 logins/week",
        "session_duration_engagement": "25 min avg",
        "motivational_triggers": "Career advancement, practical application",
        "additional_notes": "Most active in evenings",
    },
}


# ===================================================================
# POST /extract-pdf-text  (Flow 2B: Resume upload)
# ===================================================================

class TestExtractPdfText:
    def test_upload_valid_pdf(self, client):
        """A minimal valid PDF should return extracted text."""
        # Build a tiny in-memory PDF via reportlab if available,
        # otherwise use pdfplumber-compatible raw bytes.
        # For simplicity, we mock pdfplumber at the endpoint level.
        import pdfplumber

        fake_pdf_bytes = b"%PDF-1.4 fake"  # not a real PDF

        with patch("main.pdfplumber") as mock_plumber:
            mock_page = MagicMock()
            mock_page.extract_text.return_value = "John Doe - Software Engineer - 5 years experience"
            mock_pdf = MagicMock()
            mock_pdf.pages = [mock_page]
            mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
            mock_pdf.__exit__ = MagicMock(return_value=False)
            mock_plumber.open.return_value = mock_pdf

            resp = client.post(
                "/extract-pdf-text",
                files={"file": ("resume.pdf", io.BytesIO(fake_pdf_bytes), "application/pdf")},
            )
            assert resp.status_code == 200
            assert "John Doe" in resp.json()["text"]

    def test_upload_multi_page_pdf(self, client):
        """Multi-page PDF should concatenate text from all pages."""
        fake_pdf_bytes = b"%PDF-1.4 fake"

        with patch("main.pdfplumber") as mock_plumber:
            page1 = MagicMock()
            page1.extract_text.return_value = "Page 1 content"
            page2 = MagicMock()
            page2.extract_text.return_value = "Page 2 content"
            mock_pdf = MagicMock()
            mock_pdf.pages = [page1, page2]
            mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
            mock_pdf.__exit__ = MagicMock(return_value=False)
            mock_plumber.open.return_value = mock_pdf

            resp = client.post(
                "/extract-pdf-text",
                files={"file": ("resume.pdf", io.BytesIO(fake_pdf_bytes), "application/pdf")},
            )
            assert resp.status_code == 200
            text = resp.json()["text"]
            assert "Page 1 content" in text
            assert "Page 2 content" in text

    def test_upload_no_file_returns_422(self, client):
        """Missing file should return 422 (validation error)."""
        resp = client.post("/extract-pdf-text")
        assert resp.status_code == 422


# ===================================================================
# POST /refine-learning-goal  (Flow 2D: Goal refinement)
# ===================================================================

class TestRefineGoalEndpoint:
    @patch("main.refine_learning_goal_with_llm")
    @patch("main.get_llm")
    def test_refine_goal_success(self, mock_get_llm, mock_refine, client):
        mock_get_llm.return_value = MagicMock()
        mock_refine.return_value = MOCK_REFINED_GOAL

        resp = client.post("/refine-learning-goal", json={
            "learning_goal": "Become HR Manager",
            "learner_information": "MBA grad with admin background",
        })
        assert resp.status_code == 200
        assert "refined_goal" in resp.json()
        mock_refine.assert_called_once()

    @patch("main.refine_learning_goal_with_llm")
    @patch("main.get_llm")
    def test_refine_goal_passes_learner_info(self, mock_get_llm, mock_refine, client):
        mock_get_llm.return_value = MagicMock()
        mock_refine.return_value = MOCK_REFINED_GOAL

        client.post("/refine-learning-goal", json={
            "learning_goal": "Learn Python",
            "learner_information": "CS student, sophomore year",
        })

        _, kwargs = mock_refine.call_args
        # Verify the learner_information was forwarded
        call_args = mock_refine.call_args
        assert "Learn Python" in str(call_args)

    @patch("main.refine_learning_goal_with_llm")
    @patch("main.get_llm")
    def test_refine_goal_empty_learner_info(self, mock_get_llm, mock_refine, client):
        """Refinement should work even without learner information."""
        mock_get_llm.return_value = MagicMock()
        mock_refine.return_value = MOCK_REFINED_GOAL

        resp = client.post("/refine-learning-goal", json={
            "learning_goal": "Learn Python",
            "learner_information": "",
        })
        assert resp.status_code == 200

    @patch("main.get_llm")
    def test_refine_goal_llm_failure_returns_500(self, mock_get_llm, client):
        mock_get_llm.return_value = MagicMock()

        with patch("main.refine_learning_goal_with_llm", side_effect=Exception("LLM timeout")):
            resp = client.post("/refine-learning-goal", json={
                "learning_goal": "Learn Python",
                "learner_information": "",
            })
            assert resp.status_code == 500


# ===================================================================
# POST /identify-skill-gap-with-info  (Flow 2E: Skill gap)
# ===================================================================

class TestIdentifySkillGapEndpoint:
    @patch("main.identify_skill_gap_with_llm")
    @patch("main.get_llm")
    def test_identify_skill_gap_success(self, mock_get_llm, mock_identify, client):
        mock_get_llm.return_value = MagicMock()
        mock_identify.return_value = (MOCK_SKILL_GAPS_RESULT, MOCK_SKILL_REQUIREMENTS)

        resp = client.post("/identify-skill-gap-with-info", json={
            "learning_goal": "Become an HR Manager",
            "learner_information": "MBA grad with admin background",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "skill_gaps" in data
        assert "skill_requirements" in data
        assert len(data["skill_gaps"]) == 2

    @patch("main.identify_skill_gap_with_llm")
    @patch("main.get_llm")
    def test_identify_skill_gap_returns_gap_fields(self, mock_get_llm, mock_identify, client):
        mock_get_llm.return_value = MagicMock()
        mock_identify.return_value = (MOCK_SKILL_GAPS_RESULT, MOCK_SKILL_REQUIREMENTS)

        resp = client.post("/identify-skill-gap-with-info", json={
            "learning_goal": "Become an HR Manager",
            "learner_information": "MBA grad",
        })
        gaps = resp.json()["skill_gaps"]
        for gap in gaps:
            assert "name" in gap
            assert "is_gap" in gap
            assert "required_level" in gap
            assert "current_level" in gap

    @patch("main.identify_skill_gap_with_llm")
    @patch("main.get_llm")
    def test_identify_skill_gap_with_existing_requirements(self, mock_get_llm, mock_identify, client):
        mock_get_llm.return_value = MagicMock()
        mock_identify.return_value = (MOCK_SKILL_GAPS_RESULT, MOCK_SKILL_REQUIREMENTS)

        resp = client.post("/identify-skill-gap-with-info", json={
            "learning_goal": "Become an HR Manager",
            "learner_information": "MBA grad",
            "skill_requirements": '{"HRIS Management": "intermediate"}',
        })
        assert resp.status_code == 200

    @patch("main.get_llm")
    def test_identify_skill_gap_llm_failure(self, mock_get_llm, client):
        mock_get_llm.return_value = MagicMock()

        with patch("main.identify_skill_gap_with_llm", side_effect=Exception("LLM error")):
            resp = client.post("/identify-skill-gap-with-info", json={
                "learning_goal": "Learn Python",
                "learner_information": "Beginner",
            })
            assert resp.status_code == 500


# ===================================================================
# POST /create-learner-profile-with-info  (Profile creation)
# ===================================================================

class TestCreateLearnerProfileEndpoint:
    @patch("main.initialize_learner_profile_with_llm")
    @patch("main.get_llm")
    def test_create_profile_success(self, mock_get_llm, mock_init, client):
        mock_get_llm.return_value = MagicMock()
        mock_init.return_value = MOCK_LEARNER_PROFILE

        resp = client.post("/create-learner-profile-with-info", json={
            "learning_goal": "Become an HR Manager",
            "learner_information": "MBA grad with admin background",
            "skill_gaps": json.dumps(MOCK_SKILL_GAPS_RESULT["skill_gaps"]),
        })
        assert resp.status_code == 200
        profile = resp.json()["learner_profile"]
        assert "cognitive_status" in profile
        assert "learning_preferences" in profile
        assert "behavioral_patterns" in profile

    @patch("main.initialize_learner_profile_with_llm")
    @patch("main.get_llm")
    def test_create_profile_stores_when_user_id_provided(self, mock_get_llm, mock_init, client):
        mock_get_llm.return_value = MagicMock()
        mock_init.return_value = MOCK_LEARNER_PROFILE

        resp = client.post("/create-learner-profile-with-info", json={
            "learning_goal": "Become an HR Manager",
            "learner_information": "MBA grad",
            "skill_gaps": json.dumps(MOCK_SKILL_GAPS_RESULT["skill_gaps"]),
            "user_id": "alice",
            "goal_id": 0,
        })
        assert resp.status_code == 200

        # Verify it was persisted in the store
        stored = store.get_profile("alice", 0)
        assert stored is not None
        assert stored["learning_goal"] == "Become an HR Manager"

    @patch("main.initialize_learner_profile_with_llm")
    @patch("main.get_llm")
    def test_create_profile_does_not_store_without_user_id(self, mock_get_llm, mock_init, client):
        mock_get_llm.return_value = MagicMock()
        mock_init.return_value = MOCK_LEARNER_PROFILE

        resp = client.post("/create-learner-profile-with-info", json={
            "learning_goal": "Become an HR Manager",
            "learner_information": "MBA grad",
            "skill_gaps": json.dumps(MOCK_SKILL_GAPS_RESULT["skill_gaps"]),
        })
        assert resp.status_code == 200
        # No user_id/goal_id => not stored
        assert store.get_profile("alice", 0) is None


# ===================================================================
# POST /events/log  (Event logging during onboarding)
# ===================================================================

class TestEventLogging:
    def test_log_event_success(self, client):
        resp = client.post("/events/log", json={
            "user_id": "alice",
            "event_type": "page_view",
            "payload": {"page": "onboarding"},
        })
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        assert resp.json()["event_count"] == 1

    def test_log_multiple_events(self, client):
        for i in range(3):
            client.post("/events/log", json={
                "user_id": "alice",
                "event_type": f"action_{i}",
                "payload": {},
            })
        resp = client.post("/events/log", json={
            "user_id": "alice",
            "event_type": "action_3",
            "payload": {},
        })
        assert resp.json()["event_count"] == 4

    def test_log_event_auto_timestamps(self, client):
        resp = client.post("/events/log", json={
            "user_id": "alice",
            "event_type": "click",
            "payload": {},
        })
        assert resp.status_code == 200
        events = store.get_events("alice")
        assert events[0]["ts"] is not None


# ===================================================================
# GET /profile/{user_id}  (Profile retrieval)
# ===================================================================

class TestProfileRetrieval:
    def test_get_profile_by_goal_id(self, client):
        store.upsert_profile("alice", 0, MOCK_LEARNER_PROFILE)
        resp = client.get("/profile/alice", params={"goal_id": 0})
        assert resp.status_code == 200
        assert resp.json()["learner_profile"]["learning_goal"] == "Become an HR Manager"

    def test_get_all_profiles(self, client):
        store.upsert_profile("alice", 0, {"goal": "Python"})
        store.upsert_profile("alice", 1, {"goal": "Rust"})
        resp = client.get("/profile/alice")
        assert resp.status_code == 200
        assert len(resp.json()["profiles"]) == 2

    def test_get_profile_nonexistent_returns_404(self, client):
        resp = client.get("/profile/nobody", params={"goal_id": 0})
        assert resp.status_code == 404

    def test_get_profiles_nonexistent_user_returns_404(self, client):
        resp = client.get("/profile/nobody")
        assert resp.status_code == 404
