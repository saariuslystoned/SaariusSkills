"""Pure, body-free qualification fence and launch validation for AGY regular sessions.

This module records the static controller verdict and validates AGY regular session
launch parameters on the explicit shared vendor auth/config route.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional, Sequence, Tuple

from .errors import IdentityError, UnsupportedError, ValidationError


AGY_REGULAR_VERDICT_SCHEMA = "puppet.agy-regular-verdict/v1"
AGY_SHARED_VENDOR_AUTH_LIMITATION = (
    "AGY regular sessions run under an explicit shared-vendor-auth/config route "
    "using the real user HOME because no config-root selector exists; private "
    "profile isolation is not claimed"
)

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
        "status": "shared_vendor_auth_config_route",
        "launch_authorized": True,
        "qualification_authorized": False,
        "blockers": AGY_REGULAR_AUTHORITY_BLOCKERS,
        "route": "shared_vendor_auth_config_route",
        "limitation": AGY_SHARED_VENDOR_AUTH_LIMITATION,
    }


def agy_authority_blockers(session_profile: Any) -> Tuple[str, ...]:
    """Return static blockers without allowing profile authority to bleed."""

    if session_profile == "regular":
        return AGY_REGULAR_AUTHORITY_BLOCKERS
    return AGY_REGULAR_AUTHORITY_BLOCKERS + (AGY_NON_REGULAR_AUTHORITY_BLOCKER_ID,)


def require_agy_regular_launch_authority(session_profile: Any) -> None:
    """Admit the regular session profile on the explicit shared vendor auth/config route while failing non-regular profiles closed."""

    if session_profile != "regular":
        raise UnsupportedError(AGY_NON_REGULAR_AUTHORITY_BLOCKER)


def run_agy_status_preflight(*, executable_path: Path, timeout: float = 10.0) -> Dict[str, Any]:
    """Run body-free status preflight (agy models), discarding raw output."""

    try:
        res = subprocess.run(
            [str(executable_path), "models"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
            check=False,
        )
        if res.returncode != 0:
            raise IdentityError("AGY status preflight (agy models) exited non-zero")
    except (OSError, subprocess.SubprocessError) as exc:
        raise IdentityError("AGY status preflight execution failed") from exc

    return {
        "schema": "puppet.agy-shared-auth-status/v1",
        "target": "agy",
        "route": "shared_vendor_auth_config_route",
        "status_preflight": "models_command_verified",
        "limitation": AGY_SHARED_VENDOR_AUTH_LIMITATION,
    }


def verify_agy_executable_not_updated(manifest_executable: Dict[str, Any]) -> None:
    """Revalidate manifest executable identity immediately before target start to catch auto-updater races."""

    from .adapter_manifest import execution_file_identity

    path = Path(manifest_executable["resolved_path"])
    try:
        current = execution_file_identity(path)
    except Exception as exc:
        raise IdentityError("target executable unavailable for updater revalidation") from exc

    if (
        current["device"] != manifest_executable["device"]
        or current["inode"] != manifest_executable["inode"]
        or current["sha256"] != manifest_executable["sha256"]
    ):
        raise IdentityError("target executable updated or changed during status preflight; fresh census and plan required")


def validate_agy_regular_launch_params(
    *,
    session_profile: str,
    argv: Sequence[str],
    requested_model: Optional[str] = None,
    requested_effort: Optional[str] = None,
    log_destination: Optional[str] = None,
    profile_root: Optional[Any] = None,
    executable_path: Optional[str] = None,
    allow_workspace_agent: bool = False,
) -> None:
    """Validate that AGY launch parameters strictly conform to the regular-session shared auth/config route grammar."""

    if session_profile != "regular":
        raise UnsupportedError(AGY_NON_REGULAR_AUTHORITY_BLOCKER)

    if profile_root is not None:
        raise ValidationError(
            "AGY does not support private profile isolation; any claim of private config isolation fails closed"
        )

    if requested_model is not None or "--model" in argv:
        raise ValidationError(
            "AGY regular launch forbids explicit model selection; model selector must be absent"
        )

    if requested_effort is not None or "--effort" in argv:
        raise ValidationError(
            "AGY regular launch forbids explicit effort selection; effort selector must be absent"
        )

    if argv.count("--new-project") != 1:
        raise ValidationError(
            "AGY launch argv must contain exactly one project flag (--new-project)"
        )

    if "--dangerously-skip-permissions" not in argv:
        raise ValidationError(
            "AGY launch argv missing required permission bypass flag (--dangerously-skip-permissions)"
        )

    if "--log-file" not in argv:
        raise ValidationError(
            "AGY launch argv missing required log file flag (--log-file)"
        )

    log_file_idx = argv.index("--log-file")
    if log_file_idx + 1 >= len(argv) or argv[log_file_idx + 1] != "/dev/null":
        raise ValidationError(
            "AGY launch log destination must be /dev/null"
        )

    if log_destination is not None and log_destination != "/dev/null":
        raise ValidationError(
            "AGY launch log destination must be /dev/null"
        )

    if executable_path is not None and argv[0] != executable_path:
        raise ValidationError(
            "AGY launch argv executable does not match fingerprinted executable"
        )

    allowed_single_flags = {
        "--dangerously-skip-permissions",
        "--new-project",
        "--sandbox=false",
    }
    allowed_valued_flags = {"--log-file"}
    if allow_workspace_agent:
        allowed_valued_flags.add("--agent")

    idx = 1
    n = len(argv)
    while idx < n:
        item = argv[idx]
        if item in allowed_single_flags:
            idx += 1
            continue
        elif item in allowed_valued_flags:
            if idx + 1 >= n:
                raise ValidationError(f"flag {item} missing required value in AGY launch argv")
            val = argv[idx + 1]
            if item == "--log-file" and val != "/dev/null":
                raise ValidationError("AGY launch log destination must be /dev/null")
            if item == "--agent":
                if not val.startswith("puppet-"):
                    raise ValidationError("AGY agent name must match contract hash naming")
            idx += 2
            continue
        else:
            if item.startswith("/") and not Path(item).is_absolute():
                raise ValidationError("caller-supplied slash commands are forbidden in AGY launch argv")
            raise ValidationError(f"disallowed argument in AGY launch argv: {item}")
