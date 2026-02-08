"""Tests for user-state persistence (store layer + API endpoints).

Run from the repo root:
    python -m pytest backend/tests/test_user_state.py -v
"""

import sys
import os
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from utils import store


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _isolate_store(tmp_path, monkeypatch):
    """Point store module at a temp directory and reset in-memory state."""
    data_dir = tmp_path / "store_data"
    data_dir.mkdir()
    monkeypatch.setattr(store, "_DATA_DIR", data_dir)
    monkeypatch.setattr(store, "_PROFILES_PATH", data_dir / "profiles.json")
    monkeypatch.setattr(store, "_EVENTS_PATH", data_dir / "events.json")
    monkeypatch.setattr(store, "_USER_STATES_PATH", data_dir / "user_states.json")
    monkeypatch.setattr(store, "_profiles", {})
    monkeypatch.setattr(store, "_events", {})
    monkeypatch.setattr(store, "_user_states", {})


# ===================================================================
# store.py – user state CRUD
# ===================================================================

class TestUserStateStore:
    def test_put_and_get(self):
        state = {"goals": [{"id": 0, "name": "Learn Python"}], "logged_in": True}
        store.put_user_state("alice", state)

        result = store.get_user_state("alice")
        assert result == state

    def test_get_nonexistent_returns_none(self):
        assert store.get_user_state("nobody") is None

    def test_put_overwrites_existing(self):
        store.put_user_state("alice", {"v": 1})
        store.put_user_state("alice", {"v": 2})
        assert store.get_user_state("alice") == {"v": 2}

    def test_delete_removes_state(self):
        store.put_user_state("alice", {"v": 1})
        store.delete_user_state("alice")
        assert store.get_user_state("alice") is None

    def test_delete_nonexistent_is_noop(self):
        # Should not raise
        store.delete_user_state("nobody")
        assert store.get_user_state("nobody") is None

    def test_isolated_between_users(self):
        store.put_user_state("alice", {"user": "alice"})
        store.put_user_state("bob", {"user": "bob"})

        assert store.get_user_state("alice")["user"] == "alice"
        assert store.get_user_state("bob")["user"] == "bob"

    def test_delete_one_user_preserves_other(self):
        store.put_user_state("alice", {"user": "alice"})
        store.put_user_state("bob", {"user": "bob"})
        store.delete_user_state("alice")

        assert store.get_user_state("alice") is None
        assert store.get_user_state("bob") == {"user": "bob"}

    def test_persisted_to_disk(self):
        store.put_user_state("alice", {"goals": []})

        raw = json.loads(store._USER_STATES_PATH.read_text(encoding="utf-8"))
        assert "alice" in raw
        assert raw["alice"] == {"goals": []}

    def test_delete_flushes_to_disk(self):
        store.put_user_state("alice", {"v": 1})
        store.delete_user_state("alice")

        raw = json.loads(store._USER_STATES_PATH.read_text(encoding="utf-8"))
        assert "alice" not in raw

    def test_load_restores_from_disk(self):
        store.put_user_state("alice", {"goals": ["Python"]})
        # Simulate restart: clear in-memory, then load from disk
        store._user_states.clear()
        assert store.get_user_state("alice") is None

        store.load()
        assert store.get_user_state("alice") == {"goals": ["Python"]}

    def test_load_handles_missing_file(self):
        # load() should not crash if user_states.json doesn't exist
        store.load()
        assert store.get_user_state("alice") is None

    def test_complex_nested_state(self):
        """Ensure deeply-nested dicts/lists survive the round-trip."""
        state = {
            "goals": [
                {
                    "id": 0,
                    "learning_goal": "Learn ML",
                    "learner_profile": {"cognitive_status": {"overall_progress": 42}},
                    "learning_path": [{"session": 1, "topics": ["regression"]}],
                }
            ],
            "tutor_messages": [
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there!"},
            ],
            "document_caches": {"0-1-0": "<html>...</html>"},
        }
        store.put_user_state("alice", state)

        # Reload from disk to verify JSON serialization round-trip
        store._user_states.clear()
        store.load()
        assert store.get_user_state("alice") == state


# ===================================================================
# API endpoints (FastAPI TestClient)
# ===================================================================

@pytest.fixture()
def client(_isolate_store):
    """Create a TestClient for the FastAPI app with isolated store."""
    from fastapi.testclient import TestClient
    from main import app
    return TestClient(app)


class TestUserStateAPI:
    def test_get_nonexistent_returns_404(self, client):
        resp = client.get("/user-state/nobody")
        assert resp.status_code == 404

    def test_put_then_get(self, client):
        state = {"goals": [], "logged_in": True}
        put_resp = client.put("/user-state/alice", json={"state": state})
        assert put_resp.status_code == 200
        assert put_resp.json() == {"ok": True}

        get_resp = client.get("/user-state/alice")
        assert get_resp.status_code == 200
        assert get_resp.json()["state"] == state

    def test_put_overwrites(self, client):
        client.put("/user-state/alice", json={"state": {"v": 1}})
        client.put("/user-state/alice", json={"state": {"v": 2}})

        resp = client.get("/user-state/alice")
        assert resp.json()["state"] == {"v": 2}

    def test_delete_clears_state(self, client):
        client.put("/user-state/alice", json={"state": {"v": 1}})
        del_resp = client.delete("/user-state/alice")
        assert del_resp.status_code == 200
        assert del_resp.json() == {"ok": True}

        get_resp = client.get("/user-state/alice")
        assert get_resp.status_code == 404

    def test_delete_nonexistent_returns_ok(self, client):
        resp = client.delete("/user-state/nobody")
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}

    def test_put_invalid_body_returns_422(self, client):
        # Missing required "state" field
        resp = client.put("/user-state/alice", json={"wrong_key": 1})
        assert resp.status_code == 422

    def test_users_isolated(self, client):
        client.put("/user-state/alice", json={"state": {"user": "alice"}})
        client.put("/user-state/bob", json={"state": {"user": "bob"}})

        assert client.get("/user-state/alice").json()["state"]["user"] == "alice"
        assert client.get("/user-state/bob").json()["state"]["user"] == "bob"

    def test_large_state_payload(self, client):
        """Verify the endpoint handles a realistically-sized state blob."""
        state = {
            "goals": [{"id": i, "learning_goal": f"Goal {i}"} for i in range(20)],
            "tutor_messages": [{"role": "user", "content": f"msg {i}"} for i in range(100)],
            "document_caches": {str(i): f"<html>{i}</html>" for i in range(50)},
        }
        put_resp = client.put("/user-state/alice", json={"state": state})
        assert put_resp.status_code == 200

        get_resp = client.get("/user-state/alice")
        assert get_resp.json()["state"] == state
