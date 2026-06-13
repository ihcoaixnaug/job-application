"""Persist user profile fields to a local JSON file across page navigations."""
import json
from pathlib import Path

_PROFILE_PATH = Path(__file__).parent / "data" / "profile.json"

_KEYS = [
    "resume_text",
    "prof_lastname", "prof_firstname", "prof_email", "prof_phone",
    "prof_location", "prof_bio", "prof_github", "prof_portfolio", "prof_linkedin",
    "prof_school", "prof_major", "prof_degree", "prof_gpa", "prof_edu_dates",
    "prof_exp", "prof_skills", "prof_links", "prof_notes",
    "preferences", "filter_cities", "min_score", "prof_saved",
]


def save_profile(session_state) -> None:
    _PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = {k: session_state.get(k) for k in _KEYS if session_state.get(k) is not None}
    _PROFILE_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_profile() -> dict:
    if not _PROFILE_PATH.exists():
        return {}
    try:
        return json.loads(_PROFILE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
