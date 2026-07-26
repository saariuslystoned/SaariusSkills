"""Pure, body-free qualification fence and launch validation for AGY regular sessions.

This module records the static controller verdict and validates AGY regular session
launch parameters on the explicit shared vendor auth/config route.
"""

from __future__ import annotations

import os
import pwd
import stat
import subprocess
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

from .errors import IdentityError, UnsupportedError, ValidationError
from .safety import validate_sha256


AGY_REGULAR_VERDICT_SCHEMA = "puppet.agy-regular-verdict/v1"
AGY_SHARED_AUTH_LAUNCH_BINDING_SCHEMA = "puppet.agy-shared-auth-launch-binding/v1"
AGY_SHARED_AUTH_STATUS_SCHEMA = "puppet.agy-shared-auth-status/v1"
_SHARED_AUTH_BINDING_FIELDS = frozenset(
    {
        "schema",
        "target",
        "route",
        "limitation",
        "executable",
        "home_identity",
        "launch_identity",
        "status",
    }
)
_STATUS_FIELDS = frozenset(
    {
        "schema",
        "target",
        "route",
        "limitation",
        "status_preflight",
        "executable",
        "home_identity",
        "launch_identity",
    }
)
_HOME_IDENTITY_FIELDS = frozenset({"path", "device", "inode", "uid", "mode"})
_EXECUTABLE_IDENTITY_FIELDS = frozenset(
    {"resolved_path", "device", "inode", "sha256"}
)
AGY_SHARED_VENDOR_AUTH_LIMITATION = (
    "AGY regular sessions run under an explicit shared-vendor-auth/config route "
    "using the real user HOME because no config-root selector exists; private "
    "profile isolation is not claimed"
)
AGY_ACCEPTED_LIMITATIONS: Tuple[str, ...] = (
    "agy_shared_vendor_auth_config_without_private_isolation",
    "agy_tmux_buffer_transport_with_native_agent_deferred",
    "agy_provider_default_model_identity_unclaimed",
    "agy_explicit_model_effort_and_resume_deferred",
)

AGY_REGULAR_AUTHORITY_BLOCKERS: Tuple[str, ...] = (
    "agy_fresh_pass_b_required",
    "agy_regular_receipt_promotion_required",
    "agy_clean_doctor_required",
)
AGY_REGULAR_AUTHORITY_BLOCKER = (
    "AGY source state never authorizes launch; a fresh regular Pass B, receipt "
    "promotion, and a clean execution-time doctor are required"
)
AGY_NON_REGULAR_AUTHORITY_BLOCKER_ID = "agy_non_regular_profile_deferred"
AGY_NON_REGULAR_AUTHORITY_BLOCKER = (
    "AGY non-regular or unbound session profiles remain planner-only; regular, "
    "goal, and teamwork-preview authority must qualify independently"
)

# Controller-proved regular-session launch mapping. Semantic buckets and argv
# are one claim: omission of the explicit negative sandbox override fails closed.
AGY_REGULAR_PERMISSION_FLAGS: Tuple[str, ...] = ("--dangerously-skip-permissions",)
AGY_REGULAR_SANDBOX_FLAGS: Tuple[str, ...] = ("--sandbox=false",)
AGY_REGULAR_PROJECT_ISOLATION_FLAGS: Tuple[str, ...] = ("--new-project",)
AGY_REGULAR_LAUNCH_ARGV_TAIL: Tuple[str, ...] = (
    "--dangerously-skip-permissions",
    "--sandbox=false",
    "--new-project",
    "--log-file",
    "/dev/null",
)


def agy_regular_launch_argv(executable_path: str | Path) -> list[str]:
    """Return the exact live-proved AGY regular launch argv for one executable."""

    return [str(executable_path), *AGY_REGULAR_LAUNCH_ARGV_TAIL]


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
        "accepted_limitations": AGY_ACCEPTED_LIMITATIONS,
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


def _directory_identity(path: Path, *, label: str) -> Dict[str, Any]:
    try:
        resolved = path.resolve(strict=True)
        details = resolved.stat()
    except OSError as exc:
        raise ValidationError("%s is unavailable" % label) from exc
    if not stat.S_ISDIR(details.st_mode):
        raise ValidationError("%s must be a directory" % label)
    return {
        "path": str(resolved),
        "device": details.st_dev,
        "inode": details.st_ino,
        "uid": details.st_uid,
        "mode": stat.S_IMODE(details.st_mode),
    }


def _account_home_identity() -> Dict[str, Any]:
    try:
        account_home = Path(pwd.getpwuid(os.getuid()).pw_dir)
    except (KeyError, TypeError) as exc:
        raise IdentityError("AGY account HOME authority is unavailable") from exc
    identity = _directory_identity(account_home, label="AGY account HOME")
    if identity["uid"] != os.getuid():
        raise IdentityError("AGY account HOME owner changed")
    return identity


def agy_shared_source_environment(
    source_environment: Optional[Mapping[str, str]] = None,
) -> Dict[str, str]:
    """Select ambient inputs while pinning AGY HOME to the same-user account HOME."""

    source = os.environ if source_environment is None else source_environment
    if not isinstance(source, Mapping):
        raise ValidationError("AGY source environment must be a mapping")
    return {
        **dict(source),
        "HOME": _account_home_identity()["path"],
    }


def _validate_home_identity(value: Any) -> Dict[str, Any]:
    if not isinstance(value, dict) or set(value) != _HOME_IDENTITY_FIELDS:
        raise ValidationError("AGY HOME identity fields are invalid")
    path = value.get("path")
    if (
        not isinstance(path, str)
        or not path
        or not Path(path).is_absolute()
        or any(character in path for character in "\x00\n\r")
    ):
        raise ValidationError("AGY HOME path is invalid")
    for name in ("device", "inode", "uid", "mode"):
        observed = value.get(name)
        if isinstance(observed, bool) or not isinstance(observed, int) or observed < 0:
            raise ValidationError("AGY HOME identity is invalid")
    if value["device"] <= 0 or value["inode"] <= 0 or value["mode"] <= 0:
        raise ValidationError("AGY HOME identity is invalid")
    if value["uid"] != os.getuid():
        raise IdentityError("AGY HOME owner changed")
    return dict(value)


def _validate_executable_identity(value: Any) -> Dict[str, Any]:
    if not isinstance(value, dict) or set(value) != _EXECUTABLE_IDENTITY_FIELDS:
        raise ValidationError("AGY executable identity fields are invalid")
    path = value.get("resolved_path")
    if (
        not isinstance(path, str)
        or not path
        or not Path(path).is_absolute()
        or any(character in path for character in "\x00\n\r")
    ):
        raise ValidationError("AGY executable path is invalid")
    for name in ("device", "inode"):
        observed = value.get(name)
        if isinstance(observed, bool) or not isinstance(observed, int) or observed <= 0:
            raise ValidationError("AGY executable identity is invalid")
    validate_sha256(value.get("sha256"), "AGY executable sha256")
    return dict(value)


def _shared_launch_authority(
    *,
    executable_path: Path | str,
    cwd: Path | str,
    environment: Mapping[str, str],
) -> tuple[Dict[str, Any], Dict[str, str]]:
    """Bind executable, account HOME, cwd, argv, and the exact closed environment."""

    from .adapter_manifest import execution_file_identity
    from .launch import (
        public_launch_identity,
        validate_launch_environment,
    )

    executable = execution_file_identity(Path(executable_path))
    closed_environment = validate_launch_environment(
        target="agy",
        environment=environment,
    )
    home_identity = _account_home_identity()
    if closed_environment.get("HOME") != home_identity["path"]:
        raise IdentityError(
            "AGY shared-auth preflight HOME does not match account HOME authority"
        )
    launch_identity = public_launch_identity(
        repo=Path(cwd),
        argv=agy_regular_launch_argv(executable["path"]),
        environment=closed_environment,
    )
    return (
        {
            "executable": {
                "resolved_path": executable["path"],
                "device": executable["device"],
                "inode": executable["inode"],
                "sha256": executable["sha256"],
            },
            "home_identity": home_identity,
            "launch_identity": launch_identity,
        },
        closed_environment,
    )


def run_agy_status_preflight(
    *,
    executable_path: Path,
    cwd: Path,
    environment: Mapping[str, str],
    timeout: float = 10.0,
) -> Dict[str, Any]:
    """Run body-free ``agy models`` under the exact admitted launch authority."""

    before, closed_environment = _shared_launch_authority(
        executable_path=executable_path,
        cwd=cwd,
        environment=environment,
    )

    try:
        res = subprocess.run(
            [before["executable"]["resolved_path"], "models"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd=before["launch_identity"]["cwd"],
            env=closed_environment,
            timeout=timeout,
            check=False,
        )
        if res.returncode != 0:
            raise IdentityError("AGY status preflight (agy models) exited non-zero")
    except (OSError, subprocess.SubprocessError) as exc:
        raise IdentityError("AGY status preflight execution failed") from exc

    after, _ = _shared_launch_authority(
        executable_path=executable_path,
        cwd=cwd,
        environment=closed_environment,
    )
    if after != before:
        raise IdentityError("AGY shared-auth authority changed during status preflight")

    return {
        "schema": AGY_SHARED_AUTH_STATUS_SCHEMA,
        "target": "agy",
        "route": "shared_vendor_auth_config_route",
        "status_preflight": "models_command_verified",
        "limitation": AGY_SHARED_VENDOR_AUTH_LIMITATION,
        **before,
    }


def _validate_agy_status(value: Any) -> Dict[str, Any]:
    if not isinstance(value, dict) or set(value) != _STATUS_FIELDS:
        raise ValidationError("AGY shared-auth status fields are invalid")
    if (
        value.get("schema") != AGY_SHARED_AUTH_STATUS_SCHEMA
        or value.get("target") != "agy"
        or value.get("route") != "shared_vendor_auth_config_route"
        or value.get("status_preflight") != "models_command_verified"
        or value.get("limitation") != AGY_SHARED_VENDOR_AUTH_LIMITATION
    ):
        raise ValidationError("AGY shared-auth status is invalid")
    from .launch import validate_public_launch_identity

    return {
        **dict(value),
        "executable": _validate_executable_identity(value.get("executable")),
        "home_identity": _validate_home_identity(value.get("home_identity")),
        "launch_identity": validate_public_launch_identity(
            value.get("launch_identity"),
            target="agy",
        ),
    }


def build_agy_shared_auth_launch_binding(
    *,
    executable_path: Path | str,
    cwd: Path | str,
    environment: Mapping[str, str],
    status: Mapping[str, Any],
) -> Dict[str, Any]:
    """Build the body-free shared-auth proof joined to one launch context."""

    validated_status = _validate_agy_status(status)
    authority, _ = _shared_launch_authority(
        executable_path=executable_path,
        cwd=cwd,
        environment=environment,
    )
    if any(validated_status[name] != authority[name] for name in authority):
        raise IdentityError(
            "AGY status preflight authority differs from the admitted launch context"
        )
    return {
        "schema": AGY_SHARED_AUTH_LAUNCH_BINDING_SCHEMA,
        "target": "agy",
        "route": "shared_vendor_auth_config_route",
        "limitation": AGY_SHARED_VENDOR_AUTH_LIMITATION,
        **authority,
        "status": validated_status,
    }


def validate_agy_shared_auth_launch_binding(
    value: Any,
    *,
    expected_executable_path: str | Path | None = None,
    expected_launch_identity: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Validate and rejoin one shared-auth binding without reading auth content."""

    if not isinstance(value, dict) or set(value) != _SHARED_AUTH_BINDING_FIELDS:
        raise ValidationError("AGY shared-auth launch binding fields are invalid")
    if (
        value.get("schema") != AGY_SHARED_AUTH_LAUNCH_BINDING_SCHEMA
        or value.get("target") != "agy"
        or value.get("route") != "shared_vendor_auth_config_route"
    ):
        raise ValidationError("AGY shared-auth launch binding route is invalid")
    if value.get("limitation") != AGY_SHARED_VENDOR_AUTH_LIMITATION:
        raise ValidationError("AGY shared-auth limitation changed")
    from .adapter_manifest import execution_file_identity
    from .launch import validate_public_launch_identity

    executable = _validate_executable_identity(value.get("executable"))
    home_identity = _validate_home_identity(value.get("home_identity"))
    launch_identity = validate_public_launch_identity(
        value.get("launch_identity"),
        target="agy",
    )
    status = _validate_agy_status(value.get("status"))
    if (
        status["executable"] != executable
        or status["home_identity"] != home_identity
        or status["launch_identity"] != launch_identity
    ):
        raise IdentityError("AGY shared-auth status authority is unbound")
    if _account_home_identity() != home_identity:
        raise IdentityError("AGY shared-auth HOME identity changed")
    if expected_executable_path is not None:
        expected = execution_file_identity(Path(expected_executable_path))
        if executable != {
            "resolved_path": expected["path"],
            "device": expected["device"],
            "inode": expected["inode"],
            "sha256": expected["sha256"],
        }:
            raise IdentityError("AGY shared-auth executable identity changed")
    if expected_launch_identity is not None:
        expected_identity = validate_public_launch_identity(
            expected_launch_identity,
            target="agy",
        )
        if launch_identity != expected_identity:
            raise IdentityError(
                "AGY shared-auth authority is not the admitted launch environment"
            )
    return {
        "schema": AGY_SHARED_AUTH_LAUNCH_BINDING_SCHEMA,
        "target": "agy",
        "route": "shared_vendor_auth_config_route",
        "limitation": AGY_SHARED_VENDOR_AUTH_LIMITATION,
        "executable": executable,
        "home_identity": home_identity,
        "launch_identity": launch_identity,
        "status": status,
    }


def revalidate_agy_shared_auth_before_start(
    *,
    executable_path: Path | str,
    cwd: Path | str,
    argv: Sequence[str],
    admitted_environment: Mapping[str, str],
    admitted_launch_identity: Mapping[str, Any],
    admitted_binding: Mapping[str, Any],
    source_environment: Optional[Mapping[str, str]] = None,
) -> tuple[Dict[str, str], Dict[str, Any]]:
    """Rebuild and re-probe the exact shared authority immediately before exec."""

    from .launch import build_launch_identity

    refreshed_environment, refreshed_identity = build_launch_identity(
        target="agy",
        repo=Path(cwd),
        argv=argv,
        source_environment=agy_shared_source_environment(source_environment),
    )
    if (
        refreshed_environment != dict(admitted_environment)
        or refreshed_identity != dict(admitted_launch_identity)
    ):
        raise IdentityError(
            "AGY shared-auth launch context changed before target start"
        )
    validated_admitted_binding = validate_agy_shared_auth_launch_binding(
        admitted_binding,
        expected_executable_path=executable_path,
        expected_launch_identity=refreshed_identity,
    )
    status = run_agy_status_preflight(
        executable_path=Path(executable_path),
        cwd=Path(cwd),
        environment=refreshed_environment,
    )
    refreshed_binding = build_agy_shared_auth_launch_binding(
        executable_path=executable_path,
        cwd=cwd,
        environment=refreshed_environment,
        status=status,
    )
    validate_agy_shared_auth_launch_binding(
        refreshed_binding,
        expected_executable_path=executable_path,
        expected_launch_identity=refreshed_identity,
    )
    if refreshed_binding != validated_admitted_binding:
        raise IdentityError(
            "AGY shared-auth launch context changed before target start"
        )
    return refreshed_environment, refreshed_identity


def reject_agy_private_profile_root(profile_root: Any) -> None:
    """Fail closed when a caller claims private profile isolation for AGY."""

    if profile_root is not None:
        raise ValidationError(
            "AGY does not support private profile isolation; any claim of private config isolation fails closed"
        )


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
) -> None:
    """Validate that AGY launch parameters strictly conform to the exact live-proved regular-session argv grammar."""

    if session_profile != "regular":
        raise UnsupportedError(AGY_NON_REGULAR_AUTHORITY_BLOCKER)

    reject_agy_private_profile_root(profile_root)

    if requested_model is not None or "--model" in argv:
        raise ValidationError(
            "AGY regular launch forbids explicit model selection; model selector must be absent"
        )

    if requested_effort is not None or "--effort" in argv:
        raise ValidationError(
            "AGY regular launch forbids explicit effort selection; effort selector must be absent"
        )

    if log_destination is not None and log_destination != "/dev/null":
        raise ValidationError(
            "AGY launch log destination must be /dev/null"
        )

    if not isinstance(argv, (list, tuple)) or len(argv) != 6:
        raise ValidationError(
            "AGY regular launch argv must be exactly 6 tokens: [executable, --dangerously-skip-permissions, --sandbox=false, --new-project, --log-file, /dev/null]"
        )

    if executable_path is not None and argv[0] != executable_path:
        raise ValidationError(
            "AGY launch argv executable does not match fingerprinted executable"
        )

    expected = agy_regular_launch_argv(
        executable_path if executable_path is not None else argv[0]
    )
    if list(argv) != expected:
        raise ValidationError(
            "AGY regular launch argv must match the exact sequence: [executable, --dangerously-skip-permissions, --sandbox=false, --new-project, --log-file, /dev/null]"
        )
