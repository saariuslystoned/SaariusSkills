"""Zero-agent profile declarations and helpers."""

from __future__ import annotations

from typing import Dict

from .errors import ValidationError


PROMPT_TRANSPORT = "interactive_tmux_load_buffer_stdin_declared"
OBSERVED_INPUT_TRANSPORT = "tmux_load_buffer_stdin"
INPUT_READINESS_STRATEGY = "bounded_structural_settle"
SUBMIT_SETTLE_SECONDS = 1.0

SESSION_PROFILE_COMMANDS: Dict[str, Dict[str, str]] = {
    "agy": {
        "regular": "",
        "goal": "/goal",
        "teamwork-preview": "/teamwork-preview",
    },
    "codex": {"regular": "", "goal": "/goal"},
    "claude": {
        "regular": "",
        "loop": "/loop",
        "goal": "/goal",
    },
    "cursor": {"regular": ""},
    "grok": {"regular": ""},
}

STARTUP_SETTLE_SECONDS = {
    "agy": 8.0,
    "codex": 12.0,
    "claude": 8.0,
    "cursor": 8.0,
    "grok": 8.0,
}


def default_session_profile(target: str) -> str:
    profiles = SESSION_PROFILE_COMMANDS.get(target)
    if profiles is None:
        raise ValidationError("unsupported target")
    return "regular"


def validate_session_profile(target: str, session_profile: str) -> str:
    profiles = SESSION_PROFILE_COMMANDS.get(target)
    if profiles is None:
        raise ValidationError("unsupported target")
    if not isinstance(session_profile, str) or session_profile not in profiles:
        raise ValidationError("unsupported session profile")
    return session_profile


def session_command_for(target: str, session_profile: str) -> str:
    profile = validate_session_profile(target, session_profile)
    return SESSION_PROFILE_COMMANDS[target][profile]


def session_profiles_for(target: str) -> Dict[str, str]:
    profiles = SESSION_PROFILE_COMMANDS.get(target)
    if profiles is None:
        raise ValidationError("unsupported target")
    return dict(profiles)


def startup_settle_seconds_for(target: str) -> float:
    settle = STARTUP_SETTLE_SECONDS.get(target)
    if settle is None:
        raise ValidationError("unsupported target")
    return float(settle)
