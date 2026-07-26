"""Zero-agent profile declarations and helpers."""

from __future__ import annotations

from typing import Dict

from .errors import ValidationError


PROMPT_TRANSPORT = "interactive_tmux_load_buffer_stdin_declared"
OBSERVED_INPUT_TRANSPORT = "tmux_load_buffer_stdin"
BOUNDED_STRUCTURAL_SETTLE = "bounded_structural_settle"
CLAUDE_STARTUP_GATE_REDUCER = "bounded_claude_startup_gate_reducer"
INPUT_READINESS_STRATEGY = BOUNDED_STRUCTURAL_SETTLE
SUBMIT_SETTLE_SECONDS = 1.0
CLAUDE_GATE_POLL_INTERVAL_SECONDS = 0.25
CLAUDE_GATE_TRANSITION_POLL_INTERVAL_SECONDS = 1.0
CLAUDE_GATE_TRANSITION_DEADLINE_SECONDS = 5.0

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


def input_readiness_strategy_for(target: str) -> str:
    if target == "claude":
        return CLAUDE_STARTUP_GATE_REDUCER
    return BOUNDED_STRUCTURAL_SETTLE


def claude_gate_timing_policy() -> Dict[str, float]:
    """Public Claude gate timing bound to startup settle and live-proved intervals."""

    return {
        "startup_deadline_seconds": startup_settle_seconds_for("claude"),
        "poll_interval_seconds": CLAUDE_GATE_POLL_INTERVAL_SECONDS,
        "transition_poll_interval_seconds": CLAUDE_GATE_TRANSITION_POLL_INTERVAL_SECONDS,
        "transition_deadline_seconds": CLAUDE_GATE_TRANSITION_DEADLINE_SECONDS,
    }
