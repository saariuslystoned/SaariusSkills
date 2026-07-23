"""Pure, body-free qualification fence for AGY regular sessions.

This module records only the static controller verdict.  It deliberately has
no target discovery, filesystem, launch, or operator-state surface.
"""

from __future__ import annotations

from typing import Any, Dict, Tuple

from .errors import UnsupportedError


AGY_REGULAR_VERDICT_SCHEMA = "puppet.agy-regular-verdict/v1"
AGY_REGULAR_AUTHORITY_BLOCKERS: Tuple[str, ...] = (
    "agy_config_root_isolation_unproved",
    "agy_sandbox_off_unproved",
    "agy_native_instruction_plane_unqualified",
    "agy_default_model_unobserved",
    "agy_ordinary_session_no_bleed_unproved",
)
AGY_REGULAR_AUTHORITY_BLOCKER = (
    "AGY regular sessions remain planner-only until config-root isolation, "
    "sandbox-off behavior, a native instruction plane, the default model, and "
    "ordinary-session no-bleed are controller-qualified"
)
AGY_NON_REGULAR_AUTHORITY_BLOCKER_ID = "agy_non_regular_profile_deferred"
AGY_NON_REGULAR_AUTHORITY_BLOCKER = (
    "AGY non-regular or unbound session profiles remain planner-only; regular, "
    "goal, and teamwork-preview authority must qualify independently"
)


def agy_regular_verdict() -> Dict[str, Any]:
    """Return the immutable source-only AGY regular-session decision."""

    return {
        "schema": AGY_REGULAR_VERDICT_SCHEMA,
        "target": "agy",
        "session_profile": "regular",
        "status": "unsupported_planner_only",
        "launch_authorized": False,
        "qualification_authorized": False,
        "blockers": AGY_REGULAR_AUTHORITY_BLOCKERS,
    }


def agy_authority_blockers(session_profile: Any) -> Tuple[str, ...]:
    """Return static blockers without allowing profile authority to bleed."""

    if session_profile == "regular":
        return AGY_REGULAR_AUTHORITY_BLOCKERS
    return AGY_REGULAR_AUTHORITY_BLOCKERS + (AGY_NON_REGULAR_AUTHORITY_BLOCKER_ID,)


def require_agy_regular_launch_authority(session_profile: Any) -> None:
    """Fail closed and prevent other AGY profiles from borrowing regular authority."""

    if session_profile != "regular":
        raise UnsupportedError(AGY_NON_REGULAR_AUTHORITY_BLOCKER)
    raise UnsupportedError(AGY_REGULAR_AUTHORITY_BLOCKER)
