"""JSON file-backed persistence for learner profiles and behavior events."""

import json
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_PROFILES_PATH = _DATA_DIR / "profiles.json"
_EVENTS_PATH = _DATA_DIR / "events.json"
_USER_STATES_PATH = _DATA_DIR / "user_states.json"

_lock = threading.Lock()

# keyed by "{user_id}:{goal_id}"
_profiles: Dict[str, Dict[str, Any]] = {}
# keyed by user_id
_events: Dict[str, List[Dict[str, Any]]] = {}
# keyed by user_id — generic UI state blob per user
_user_states: Dict[str, Dict[str, Any]] = {}


def load():
    """Read persisted data from disk into memory. Call once at startup."""
    global _profiles, _events, _user_states
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    if _PROFILES_PATH.exists():
        try:
            _profiles = json.loads(_PROFILES_PATH.read_text(encoding="utf-8"))
        except Exception:
            _profiles = {}
    if _EVENTS_PATH.exists():
        try:
            _events = json.loads(_EVENTS_PATH.read_text(encoding="utf-8"))
        except Exception:
            _events = {}
    if _USER_STATES_PATH.exists():
        try:
            _user_states = json.loads(_USER_STATES_PATH.read_text(encoding="utf-8"))
        except Exception:
            _user_states = {}


def _flush_profiles():
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    _PROFILES_PATH.write_text(json.dumps(_profiles, ensure_ascii=False, indent=2), encoding="utf-8")


def _flush_events():
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    _EVENTS_PATH.write_text(json.dumps(_events, ensure_ascii=False, indent=2), encoding="utf-8")


def _profile_key(user_id: str, goal_id: int) -> str:
    return f"{user_id}:{goal_id}"


def upsert_profile(user_id: str, goal_id: int, profile: Dict[str, Any]):
    with _lock:
        _profiles[_profile_key(user_id, goal_id)] = profile
        _flush_profiles()


def get_profile(user_id: str, goal_id: int) -> Optional[Dict[str, Any]]:
    return _profiles.get(_profile_key(user_id, goal_id))


def get_all_profiles_for_user(user_id: str) -> Dict[int, Dict[str, Any]]:
    prefix = f"{user_id}:"
    result = {}
    for key, profile in _profiles.items():
        if key.startswith(prefix):
            gid = key[len(prefix):]
            try:
                result[int(gid)] = profile
            except ValueError:
                result[gid] = profile
    return result


def append_event(user_id: str, event: Dict[str, Any]):
    with _lock:
        _events.setdefault(user_id, []).append(event)
        _events[user_id] = _events[user_id][-200:]
        _flush_events()


def get_events(user_id: str) -> List[Dict[str, Any]]:
    return _events.get(user_id, [])


# --------------- user states (generic UI state per user) ---------------

def _flush_user_states():
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    _USER_STATES_PATH.write_text(json.dumps(_user_states, ensure_ascii=False, indent=2), encoding="utf-8")


def get_user_state(user_id: str) -> Optional[Dict[str, Any]]:
    return _user_states.get(user_id)


def put_user_state(user_id: str, state: Dict[str, Any]):
    with _lock:
        _user_states[user_id] = state
        _flush_user_states()


def delete_user_state(user_id: str):
    with _lock:
        _user_states.pop(user_id, None)
        _flush_user_states()
