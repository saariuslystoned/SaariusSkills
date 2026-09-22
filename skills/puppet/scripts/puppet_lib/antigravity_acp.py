"""Named antigravity-acp candidate transport with existing candidate contracts.

Pins the official Antigravity runtime shape and consumes the pinned public
acpx runtime through the existing controller/caller path. Ordinary
availability stays false. Host conversation_id stays separate from
runtimeSessionName/backendSessionId/acpxRecordId.
"""

from __future__ import annotations

import json
import os
import platform
import re
import subprocess
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence

from .caller import caller_projection, make_blocker
from .cursor_acp import (
    CANDIDATE_RUNTIME_KIND,
    FINISH_POLICY_DISCARD,
    FINISH_POLICY_LOCAL_RELEASE,
    FINISH_POLICY_RETAIN,
    SESSION_MODE_ONESHOT,
    SESSION_MODE_PERSISTENT,
    SYNTHETIC_PEER_KIND,
    WORKER_EXIT_WAIT_MS,
    drain_runtime_turn_events,
    is_owned_session_process,
    is_unsupported_backend_session_close,
    process_identities_match,
    project_runtime_handle,
    public_worker_identity,
    reject_runtime_conversation_params,
    require_runtime_task_text,
    require_unsupported_permission_outcome,
    require_unsupported_question_outcome,
)
from .contracts import require_intended_write_relative
from .errors import IdentityError, UnsupportedError, ValidationError
from .safety import validate_identifier


TRANSPORT_ID = "antigravity-acp"
GENERIC_ACP_ID = "acp"
TARGET = "agy"
DEFAULT_ROUTE = "agy-print"
CANDIDATE_SCHEMA = "puppet.antigravity-acp-candidate/v1"
OBSERVATION_SCHEMA = "puppet.antigravity-acp-observation/v1"
MODEL_CATALOG_SCHEMA = "puppet.antigravity-acp-model-catalog/v1"
HOST_PERMISSION_SCHEMA = "puppet.antigravity-acp-host-permission/v1"
ADAPTER_ID = "antigravity-acpx"
OWNERSHIP_SCHEMA = "puppet.antigravity-acpx-ownership/v1"

REGISTRY_REVISION = "81bf71b55e15f630c4fb8a86d20d3088071d2071"
RUNTIME_ID = "antigravity-acp"
RUNTIME_VERSION = "1.1.1"
# Published acpx@0.19.0 has no gitHead. The 0.17.1 SHA is a historical watch
# identity only and must not machine-read as the published package source.
ACPX_SOURCE_COMMIT = None
ACPX_LAST_INSPECTED_SOURCE_COMMIT = "50a47ad10a75431cbc276ec9b555d11fe1f69c84"
ACPX_LAST_INSPECTED_SOURCE_RELEASE = "0.17.1"
ACPX_RELEASE = "0.19.0"
ACPX_NPM_INTEGRITY = (
    "sha512-sgG0CkhuvVxgfiksXjIPEl9hsHZW0CpxywPdQeoIP5D31gwZE4nrnddLUUqaSCLb1UIM7LFPBL5qdvy15/+B6Q=="
)
ACPX_TARBALL_SHA256 = (
    "5a61820401cfed668ce3ad77a2feaebdd9e496a037ba28b2afca3224e7505c6d"
)
ACPX_RUNTIME_JS_SHA256 = (
    "88a9799088146a191360a297bec94fb9006853a4420bef6257635a6b10520e1b"
)

DEFAULT_ANTIGRAVITY_MODEL = "gemini-3.8-flash-high"
ADVERTISED_ANTIGRAVITY_MODELS = (
    "gemini-3.8-flash-high",
    "gemini-3.1-pro",
    "gemini-3-flash",
)
FALLBACK_OR_DEFAULT_MODEL_IDS = frozenset(
    {"default", "fallback", "auto", "unavailable", "current_default"}
)
CONTROLLER_RUNTIME_DRIVER = (
    "bridge/antigravity-acp/test/controller-runtime-driver.mjs"
)
STARTUP_TIMEOUT_MS = 30_000
CANDIDATE_PROMPT_TIMEOUT_MS = 300_000
MIN_TIMEOUT_MS = 1_000
MAX_TIMEOUT_MS = 1_800_000
ALLOWED_TURN_STATUSES = frozenset({"completed", "failed", "cancelled"})
RECEIPT_DURABILITY_DURABLE = "durable"
RECEIPT_DURABILITY_NONDURABLE = "nondurable"
ALLOWED_STOP_REASONS = frozenset(
    {
        "end_turn",
        "max_tokens",
        "cancelled",
        "canceled",
        "error",
        "stop",
        "refused",
        "timeout",
        "length",
        "content_filter",
    }
)
_SECRET_CODE_PARTS = ("token", "secret", "password", "prompt", "credential")
OFFICIAL_ROUTE_KIND = "official_route"
ANTIGRAVITY_ROUTE_BINDING_SCHEMA = "puppet.antigravity-acp-route-binding/v1"
ANTIGRAVITY_ROUTE_IDENTITY = "antigravity-acp-server"
PROFILE_ENV = "GEMINI_HOME"
ANTIGRAVITY_SANITIZED_ENV_NAMES = (
    "PATH",
    "GEMINI_HOME",
    "AGY_ACP_FORCE_FILE_STORAGE",
    "HOME",
    "TMPDIR",
    "LANG",
    "ANTIGRAVITY_HARNESS_PATH",
)
_ANTIGRAVITY_REQUIRED_ENV_NAMES = (
    "PATH",
    "GEMINI_HOME",
    "AGY_ACP_FORCE_FILE_STORAGE",
    "ANTIGRAVITY_HARNESS_PATH",
)
_ANTIGRAVITY_OPTIONAL_ENV_NAMES = ("HOME", "TMPDIR", "LANG")
_PLATFORM_ARCHIVE_DIRS = {
    "darwin-aarch64": "1.1.1-darwin-arm64",
    "linux-aarch64": "1.1.1-linux-arm64",
    "linux-x86_64": "1.1.1-linux-x86_64",
    "windows-aarch64": "1.1.1-windows-arm64",
    "windows-x86_64": "1.1.1-windows-x86_64",
}

_PLATFORM_COMMANDS = {
    "darwin-aarch64": {
        "runtime_command": "./agy_acp_server.par",
        "runtime_args": [],
        "helper": "localharness_external",
    },
    "linux-aarch64": {
        "runtime_command": "./agy_acp_server.par",
        "runtime_args": ["--uid="],
        "helper": "localharness_external",
    },
    "linux-x86_64": {
        "runtime_command": "./agy_acp_server.par",
        "runtime_args": ["--uid="],
        "helper": "localharness_external",
    },
    "windows-aarch64": {
        "runtime_command": "./agy_acp_server.exe",
        "runtime_args": [],
        "helper": "localharness_external.exe",
    },
    "windows-x86_64": {
        "runtime_command": "./agy_acp_server.exe",
        "runtime_args": [],
        "helper": "localharness_external.exe",
    },
}

_CONTRACT_KEYS = frozenset(
    {
        "schema",
        "transport",
        "target",
        "default_route",
        "available",
        "qualification",
        "explicit_activation_required",
        "runtime",
        "auth_policy",
        "model_policy",
        "question_policy",
        "platform_commands",
    }
)
_RUNTIME_KEYS = frozenset(
    {
        "id",
        "version",
        "registry_revision",
        "acpx_source_commit",
        "last_inspected_source_commit",
        "last_inspected_source_release",
        "acpx_release",
        "acpx_npm_integrity",
        "acpx_tarball_sha256",
        "acpx_runtime_js_sha256",
    }
)
_AUTH_POLICY_KEYS = frozenset(
    {
        "mode",
        "profile_env",
        "credential_source",
        "api_key_fallback",
        "cloud_fallback",
        "alternate_account_fallback",
        "interactive_login",
        "overage_policy",
    }
)
_MODEL_POLICY_KEYS = frozenset(
    {"selection", "observed_required", "unknown_model", "effort_policy"}
)
_QUESTION_POLICY_KEYS = frozenset(
    {"interaction_requests", "answer_selection", "human_required_outcome"}
)
_OBSERVATION_KEYS = frozenset(
    {
        "schema",
        "transport",
        "target",
        "qualification",
        "runtime",
        "auth",
        "model",
        "session",
        "terminal",
        "question",
        "record_state",
    }
)
_OBS_RUNTIME_KEYS = frozenset({"id", "version", "registry_revision"})
_OBS_AUTH_KEYS = frozenset(
    {
        "mode",
        "profile_env",
        "credential_source",
        "account_state",
        "api_key_present",
        "cloud_credentials_present",
        "alternate_account",
        "interactive_login",
        "overage_state",
    }
)
_OBS_MODEL_KEYS = frozenset(
    {"requested_id", "advertised_ids", "observed_id", "selection_state", "effort"}
)
_OBS_SESSION_KEYS = frozenset({"session_id", "conversation_id"})
_OBS_TERMINAL_REQUIRED_KEYS = frozenset({"state", "exit_code", "result_id"})
_OBS_TERMINAL_OPTIONAL_KEYS = frozenset(
    {"status", "stop_reason", "error_code", "event_kinds"}
)
_OBS_QUESTION_KEYS = frozenset(
    {"state", "interaction_id", "human_required", "outcome"}
)
_BODY_KEYS = frozenset(
    {"prompt", "output", "content", "text", "transcript", "title", "options"}
)


def _blocker(code: str, detail: str, **identity: Any) -> Dict[str, Any]:
    return make_blocker(code=code, detail=detail, **identity)


def _raise_identity(code: str, detail: str, **identity: Any) -> None:
    raise IdentityError(detail, blocker=_blocker(code, detail, **identity))


def _raise_unsupported(code: str, detail: str) -> None:
    raise UnsupportedError(detail, blocker=_blocker(code, detail))


def _raise_unavailable(detail: str) -> None:
    raise UnsupportedError(detail, blocker=_blocker("transport_unavailable", detail))


def _backend_unsupported_close(detail: str) -> UnsupportedError:
    error = UnsupportedError(
        detail,
        blocker=_blocker("acp_backend_unsupported_control", detail),
    )
    error.code = "ACP_BACKEND_UNSUPPORTED_CONTROL"
    return error


def require_antigravity_acp_target(target: Any) -> str:
    if target != TARGET:
        raise ValidationError("antigravity-acp transport requires target agy")
    return TARGET


def current_antigravity_platform_id(
    system: Optional[str] = None, machine: Optional[str] = None
) -> str:
    host = system or platform.system()
    cpu_raw = (machine or platform.machine()).lower()
    os_name = {
        "Darwin": "darwin",
        "Linux": "linux",
        "Windows": "windows",
        "darwin": "darwin",
        "linux": "linux",
        "windows": "windows",
        "win32": "windows",
    }.get(host, host.lower())
    cpu = "aarch64" if cpu_raw in {"arm64", "aarch64"} else (
        "x86_64" if cpu_raw in {"x86_64", "amd64"} else cpu_raw
    )
    return "%s-%s" % (os_name, cpu)


def default_antigravity_runtime_dir(platform_id: Optional[str] = None) -> Path:
    resolved = platform_id or current_antigravity_platform_id()
    archive = _PLATFORM_ARCHIVE_DIRS.get(resolved, "%s-%s" % (RUNTIME_VERSION, resolved))
    return Path.home() / ".local" / "share" / "saarius-skills" / RUNTIME_ID / archive


def default_antigravity_gemini_home() -> Path:
    return (
        Path.home()
        / ".local"
        / "state"
        / "saarius-skills"
        / "antigravity-acp"
        / "gemini-home"
    )


def sanitized_antigravity_process_env(
    process_env: Optional[Mapping[str, str]],
    *,
    gemini_home: Path,
    helper: Path,
) -> Dict[str, str]:
    # Mirrors bridge/antigravity-acp/broker.mjs sanitizedAgentEnv.
    env = os.environ if process_env is None else process_env
    child = {
        "PATH": env.get("PATH") or "",
        "GEMINI_HOME": str(gemini_home),
        "AGY_ACP_FORCE_FILE_STORAGE": "1",
    }
    if env.get("HOME"):
        child["HOME"] = env["HOME"]
    if env.get("TMPDIR"):
        child["TMPDIR"] = env["TMPDIR"]
    if env.get("LANG"):
        child["LANG"] = env["LANG"]
    child["ANTIGRAVITY_HARNESS_PATH"] = str(helper)
    return child


def require_antigravity_process_env(
    process_env: Any,
    *,
    helper: str,
    profile_path: str,
) -> Dict[str, str]:
    if not isinstance(process_env, Mapping):
        raise ValidationError("antigravity-acp trusted route binding process environment is invalid")
    extra = set(process_env) - set(ANTIGRAVITY_SANITIZED_ENV_NAMES)
    if extra:
        raise ValidationError("antigravity-acp trusted route binding process environment is invalid")
    child: Dict[str, str] = {}
    for name in _ANTIGRAVITY_REQUIRED_ENV_NAMES:
        value = process_env.get(name)
        if not isinstance(value, str):
            raise ValidationError("antigravity-acp trusted route binding process environment is invalid")
        child[name] = value
    for name in _ANTIGRAVITY_OPTIONAL_ENV_NAMES:
        if name not in process_env:
            continue
        value = process_env[name]
        if not isinstance(value, str):
            raise ValidationError("antigravity-acp trusted route binding process environment is invalid")
        child[name] = value
    if child.get("GEMINI_HOME") != profile_path:
        raise ValidationError("antigravity-acp trusted route binding process environment is invalid")
    if child.get("ANTIGRAVITY_HARNESS_PATH") != helper:
        raise ValidationError("antigravity-acp trusted route binding process environment is invalid")
    if child.get("AGY_ACP_FORCE_FILE_STORAGE") != "1":
        raise ValidationError("antigravity-acp trusted route binding process environment is invalid")
    return child


def resolve_antigravity_acp_route_binding(
    *,
    runtime_dir: Optional[Path] = None,
    runtime_server: Optional[Path] = None,
    helper_path: Optional[Path] = None,
    gemini_home: Optional[Path] = None,
    process_env: Optional[Mapping[str, str]] = None,
    platform_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Bind the official pinned ACP server, helper, argv, and profile env.

    This is not the native AGY manifest executable. Policy matches
    bridge/antigravity-acp/broker.mjs resolveLaunch + sanitizedAgentEnv.
    """

    env = os.environ if process_env is None else process_env
    resolved_platform = platform_id or current_antigravity_platform_id()
    launch = _PLATFORM_COMMANDS.get(resolved_platform)
    if launch is None:
        raise ValidationError(
            "antigravity-acp official route has no pinned launch for %s" % resolved_platform
        )
    basename = Path(launch["runtime_command"]).name
    configured_server = runtime_server or (
        Path(env["ANTIGRAVITY_ACP_SERVER"]) if env.get("ANTIGRAVITY_ACP_SERVER") else None
    )
    configured_dir = runtime_dir or (
        Path(env["ANTIGRAVITY_ACP_RUNTIME_DIR"])
        if env.get("ANTIGRAVITY_ACP_RUNTIME_DIR")
        else default_antigravity_runtime_dir(resolved_platform)
    )
    if configured_server is not None:
        command = Path(configured_server).expanduser().resolve()
    else:
        command = Path(configured_dir).expanduser().resolve() / basename
    if not command.is_file() or not os.access(command, os.X_OK):
        raise ValidationError("antigravity-acp official route executable is missing")
    helper_name = Path(launch["helper"]).name
    if helper_path is not None:
        helper = Path(helper_path).expanduser().resolve()
    elif env.get("ANTIGRAVITY_HARNESS_PATH"):
        helper = Path(env["ANTIGRAVITY_HARNESS_PATH"]).expanduser().resolve()
    else:
        helper = command.parent / helper_name
    if not helper.is_file() or not os.access(helper, os.X_OK):
        raise ValidationError("antigravity-acp official route helper is missing")
    scoped = env.get("SAARIUS_ANTIGRAVITY_ACP_GEMINI_HOME") or env.get("GEMINI_HOME")
    profile = (
        Path(gemini_home).expanduser().resolve()
        if gemini_home is not None
        else (
            Path(scoped).expanduser().resolve()
            if isinstance(scoped, str) and scoped.strip()
            else default_antigravity_gemini_home()
        )
    )
    argv = [str(command), *list(launch["runtime_args"])]
    process = sanitized_antigravity_process_env(
        env, gemini_home=profile, helper=helper
    )
    return require_antigravity_acp_route_binding(
        {
            "schema": ANTIGRAVITY_ROUTE_BINDING_SCHEMA,
            "route": TRANSPORT_ID,
            "kind": OFFICIAL_ROUTE_KIND,
            "agent": "antigravity",
            "transport": "acp",
            "identity": ANTIGRAVITY_ROUTE_IDENTITY,
            "platform_id": resolved_platform,
            "runtime_id": RUNTIME_ID,
            "runtime_version": RUNTIME_VERSION,
            "executable": str(command),
            "argv": argv,
            "helper": str(helper),
            "profile_env": PROFILE_ENV,
            "profile_path": str(profile),
            "process_env_names": list(ANTIGRAVITY_SANITIZED_ENV_NAMES),
            "process_env": process,
            "test_only": False,
        }
    )


def test_only_antigravity_synthetic_route_binding() -> Dict[str, Any]:
    return require_antigravity_acp_route_binding(
        {
            "schema": ANTIGRAVITY_ROUTE_BINDING_SCHEMA,
            "route": TRANSPORT_ID,
            "kind": SYNTHETIC_PEER_KIND,
            "agent": "antigravity",
            "transport": "acp",
            "identity": ANTIGRAVITY_ROUTE_IDENTITY,
            "platform_id": current_antigravity_platform_id(),
            "runtime_id": RUNTIME_ID,
            "runtime_version": RUNTIME_VERSION,
            "executable": None,
            "argv": None,
            "helper": None,
            "profile_env": PROFILE_ENV,
            "profile_path": None,
            "process_env_names": list(ANTIGRAVITY_SANITIZED_ENV_NAMES),
            "process_env": None,
            "test_only": True,
        }
    )


def require_antigravity_acp_route_binding(value: Any) -> Dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValidationError("antigravity-acp trusted route binding is missing")
    if value.get("schema") != ANTIGRAVITY_ROUTE_BINDING_SCHEMA:
        raise ValidationError("antigravity-acp trusted route binding schema is invalid")
    if value.get("route") != TRANSPORT_ID or value.get("agent") != "antigravity":
        raise ValidationError("antigravity-acp trusted route binding identity is wrong")
    if (
        value.get("transport") != "acp"
        or value.get("identity") != ANTIGRAVITY_ROUTE_IDENTITY
        or value.get("runtime_id") != RUNTIME_ID
        or value.get("runtime_version") != RUNTIME_VERSION
        or value.get("profile_env") != PROFILE_ENV
    ):
        raise ValidationError("antigravity-acp trusted route binding identity is wrong")
    kind = value.get("kind")
    if kind == SYNTHETIC_PEER_KIND:
        if value.get("test_only") is not True:
            raise ValidationError("antigravity-acp synthetic peer remains test-only")
        if value.get("executable") is not None or value.get("argv") is not None:
            raise ValidationError("synthetic peer injection cannot carry a candidate executable")
        return {
            "schema": ANTIGRAVITY_ROUTE_BINDING_SCHEMA,
            "route": TRANSPORT_ID,
            "kind": SYNTHETIC_PEER_KIND,
            "agent": "antigravity",
            "transport": "acp",
            "identity": ANTIGRAVITY_ROUTE_IDENTITY,
            "platform_id": value.get("platform_id") or current_antigravity_platform_id(),
            "runtime_id": RUNTIME_ID,
            "runtime_version": RUNTIME_VERSION,
            "executable": None,
            "argv": None,
            "helper": None,
            "profile_env": PROFILE_ENV,
            "profile_path": None,
            "process_env_names": list(ANTIGRAVITY_SANITIZED_ENV_NAMES),
            "process_env": None,
            "test_only": True,
        }
    if kind != OFFICIAL_ROUTE_KIND:
        raise ValidationError("antigravity-acp trusted route binding kind is invalid")
    executable = value.get("executable")
    argv = value.get("argv")
    helper = value.get("helper")
    profile_path = value.get("profile_path")
    process_env = value.get("process_env")
    if not isinstance(executable, str) or not executable:
        raise ValidationError("antigravity-acp trusted route binding executable is missing")
    if not isinstance(argv, (list, tuple)) or not argv or argv[0] != executable:
        raise ValidationError("antigravity-acp trusted route binding argv is invalid")
    if not isinstance(helper, str) or not helper:
        raise ValidationError("antigravity-acp trusted route binding helper is missing")
    if not isinstance(profile_path, str) or not profile_path:
        raise ValidationError("antigravity-acp trusted route binding profile is missing")
    process = require_antigravity_process_env(
        process_env, helper=helper, profile_path=profile_path
    )
    return {
        "schema": ANTIGRAVITY_ROUTE_BINDING_SCHEMA,
        "route": TRANSPORT_ID,
        "kind": OFFICIAL_ROUTE_KIND,
        "agent": "antigravity",
        "transport": "acp",
        "identity": ANTIGRAVITY_ROUTE_IDENTITY,
        "platform_id": value.get("platform_id"),
        "runtime_id": RUNTIME_ID,
        "runtime_version": RUNTIME_VERSION,
        "executable": executable,
        "argv": list(argv),
        "helper": helper,
        "profile_env": PROFILE_ENV,
        "profile_path": profile_path,
        "process_env_names": list(ANTIGRAVITY_SANITIZED_ENV_NAMES),
        "process_env": process,
        "test_only": False,
    }


def _exact_mapping(value: Any, keys: frozenset[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != keys:
        raise ValidationError("%s fields do not match schema" % label)
    return value


def require_bounded_timeout_ms(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValidationError(
            "%s timeoutMs must be an integer between %s and %s"
            % (label, MIN_TIMEOUT_MS, MAX_TIMEOUT_MS)
        )
    if value < MIN_TIMEOUT_MS or value > MAX_TIMEOUT_MS:
        raise ValidationError(
            "%s timeoutMs must be an integer between %s and %s"
            % (label, MIN_TIMEOUT_MS, MAX_TIMEOUT_MS)
        )
    return value


def bound_error_code(value: Any) -> Optional[str]:
    if not isinstance(value, str) or not value or len(value) > 64:
        return None
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", value):
        return None
    lower = value.lower()
    if any(part in lower for part in _SECRET_CODE_PARTS):
        return None
    return value


def bound_stop_reason(value: Any) -> Optional[str]:
    return value if isinstance(value, str) and value in ALLOWED_STOP_REASONS else None


def bound_terminal_receipt(
    result: Any,
    *,
    discarded: Optional[Mapping[str, Any]] = None,
    timeout_ms: Optional[int] = None,
) -> Dict[str, Any]:
    if not isinstance(result, Mapping):
        raise ValidationError("runtime turn result is incomplete")
    status = result.get("status")
    if status not in ALLOWED_TURN_STATUSES:
        raise ValidationError("runtime turn result is incomplete")
    receipt: Dict[str, Any] = {"status": status}
    reason = bound_stop_reason(result.get("stopReason") or result.get("stop_reason"))
    if reason is not None:
        receipt["stop_reason"] = reason
    error = result.get("error")
    code = bound_error_code(result.get("errorCode") or result.get("error_code"))
    if code is None and isinstance(error, Mapping):
        code = bound_error_code(error.get("code"))
    if code is not None:
        receipt["error_code"] = code
    if isinstance(discarded, Mapping):
        kinds = discarded.get("observed_types")
        if isinstance(kinds, list):
            receipt["event_kinds"] = [
                item for item in kinds if isinstance(item, str) and item
            ][:16]
    if timeout_ms is not None:
        receipt["timeout_ms"] = require_bounded_timeout_ms(timeout_ms, "candidate prompt")
    _reject_body_keys(receipt, "terminal receipt")
    return receipt


def bound_receipt_durability(*, written: bool) -> Dict[str, Any]:
    """Project a body-free persist signal. Missing or failed writes are never durable."""

    receipt = (
        {
            "receipt_durability": RECEIPT_DURABILITY_DURABLE,
            "durable": True,
        }
        if written
        else {
            "receipt_durability": RECEIPT_DURABILITY_NONDURABLE,
            "durable": False,
        }
    )
    _reject_body_keys(receipt, "receipt durability")
    return receipt


def _receipt_durability_from_runner(runner: Any) -> Dict[str, Any]:
    recorded = getattr(runner, "receipt_durability", None)
    written = (
        isinstance(recorded, Mapping)
        and recorded.get("receipt_durability") == RECEIPT_DURABILITY_DURABLE
        and recorded.get("durable") is True
    )
    return bound_receipt_durability(written=written)


def _terminal_mapping(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValidationError("terminal observation fields do not match schema")
    keys = set(value)
    required = _OBS_TERMINAL_REQUIRED_KEYS
    allowed = required | _OBS_TERMINAL_OPTIONAL_KEYS
    if not required <= keys or not keys <= allowed:
        raise ValidationError("terminal observation fields do not match schema")
    return value


def _reject_body_keys(value: Any, label: str = "metadata") -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if key in _BODY_KEYS:
                raise ValidationError("%s contains body-bearing field %s" % (label, key))
            _reject_body_keys(nested, label)
    elif isinstance(value, list):
        for nested in value:
            _reject_body_keys(nested, label)


def _bool(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValidationError("%s must be boolean" % label)
    return value


def _bounded_string(value: Any, label: str, maximum: int = 200) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise ValidationError("%s is invalid" % label)
    if any(character in value for character in "\x00\n\r"):
        raise ValidationError("%s contains control characters" % label)
    return value


def candidate_contract() -> Dict[str, Any]:
    """Return the pinned, explicitly non-qualifying candidate contract."""

    return {
        "schema": CANDIDATE_SCHEMA,
        "transport": TRANSPORT_ID,
        "target": TARGET,
        "default_route": DEFAULT_ROUTE,
        "available": False,
        "qualification": "non_qualifying",
        "explicit_activation_required": True,
        "runtime": {
            "id": RUNTIME_ID,
            "version": RUNTIME_VERSION,
            "registry_revision": REGISTRY_REVISION,
            "acpx_source_commit": ACPX_SOURCE_COMMIT,
            "last_inspected_source_commit": ACPX_LAST_INSPECTED_SOURCE_COMMIT,
            "last_inspected_source_release": ACPX_LAST_INSPECTED_SOURCE_RELEASE,
            "acpx_release": ACPX_RELEASE,
            "acpx_npm_integrity": ACPX_NPM_INTEGRITY,
            "acpx_tarball_sha256": ACPX_TARBALL_SHA256,
            "acpx_runtime_js_sha256": ACPX_RUNTIME_JS_SHA256,
        },
        "auth_policy": {
            "mode": "oauth-personal",
            "profile_env": "GEMINI_HOME",
            "credential_source": "runtime_owned",
            "api_key_fallback": False,
            "cloud_fallback": False,
            "alternate_account_fallback": False,
            "interactive_login": "fail_closed",
            "overage_policy": "must_observe_disabled_or_never",
        },
        "model_policy": {
            "selection": "exact_advertised_id_only",
            "observed_required": True,
            "unknown_model": "fail_closed",
            "effort_policy": "unsupported_until_acp_proof",
        },
        "question_policy": {
            "interaction_requests": "cancel_and_report",
            "answer_selection": "never_auto_select",
            "human_required_outcome": "cancelled",
        },
        "platform_commands": deepcopy(_PLATFORM_COMMANDS),
    }


def validate_candidate_contract(value: Any) -> Dict[str, Any]:
    """Validate exact pinning and safety policy for the candidate contract."""

    contract = _exact_mapping(value, _CONTRACT_KEYS, "candidate contract")
    if contract.get("schema") != CANDIDATE_SCHEMA:
        raise ValidationError("candidate contract schema is invalid")
    if contract.get("transport") != TRANSPORT_ID:
        raise ValidationError("candidate contract transport is invalid")
    if contract.get("transport") == GENERIC_ACP_ID:
        raise ValidationError("generic acp is not Antigravity ACP")
    if contract.get("target") != TARGET:
        raise ValidationError("candidate contract target is invalid")
    if contract.get("default_route") != DEFAULT_ROUTE:
        raise ValidationError("native default route changed")
    if contract.get("available") is not False:
        raise ValidationError("candidate contract must remain unavailable")
    if contract.get("qualification") != "non_qualifying":
        raise ValidationError("candidate contract cannot claim qualification")
    if contract.get("explicit_activation_required") is not True:
        raise ValidationError("candidate contract requires explicit activation")

    runtime = _exact_mapping(contract.get("runtime"), _RUNTIME_KEYS, "runtime pin")
    if runtime.get("acpx_source_commit") is not None:
        raise ValidationError("published acpx@0.19.0 source commit is unknown")
    if runtime.get("last_inspected_source_release") == ACPX_RELEASE:
        raise ValidationError("last inspected 0.17.1 source is not the published 0.19.0 release")
    if runtime.get("last_inspected_source_commit") != ACPX_LAST_INSPECTED_SOURCE_COMMIT:
        raise ValidationError("last inspected Antigravity source commit drifted")
    if runtime.get("last_inspected_source_release") != ACPX_LAST_INSPECTED_SOURCE_RELEASE:
        raise ValidationError("last inspected Antigravity source release drifted")
    expected_runtime = candidate_contract()["runtime"]
    if dict(runtime) != expected_runtime:
        raise ValidationError("Antigravity ACP runtime pin drifted")

    auth = _exact_mapping(contract.get("auth_policy"), _AUTH_POLICY_KEYS, "auth policy")
    expected_auth = candidate_contract()["auth_policy"]
    if dict(auth) != expected_auth:
        raise ValidationError("Antigravity ACP auth policy drifted")

    model = _exact_mapping(contract.get("model_policy"), _MODEL_POLICY_KEYS, "model policy")
    if dict(model) != candidate_contract()["model_policy"]:
        raise ValidationError("Antigravity ACP model policy drifted")

    question = _exact_mapping(
        contract.get("question_policy"), _QUESTION_POLICY_KEYS, "question policy"
    )
    if dict(question) != candidate_contract()["question_policy"]:
        raise ValidationError("Antigravity ACP question policy drifted")

    platforms = contract.get("platform_commands")
    if not isinstance(platforms, Mapping) or set(platforms) != set(_PLATFORM_COMMANDS):
        raise ValidationError("platform command pin is incomplete")
    for platform, expected in _PLATFORM_COMMANDS.items():
        actual = _exact_mapping(platforms[platform], frozenset(expected), platform)
        if dict(actual) != expected:
            raise ValidationError("platform command pin drifted for %s" % platform)
        if not isinstance(actual["runtime_args"], list) or not all(
            isinstance(argument, str) and argument for argument in actual["runtime_args"]
        ):
            raise ValidationError("platform runtime arguments are invalid")
    return deepcopy(dict(contract))


def validate_auth_observation(value: Any) -> Dict[str, Any]:
    """Require personal OAuth and reject every unproven credential fallback."""

    auth = _exact_mapping(value, _OBS_AUTH_KEYS, "auth observation")
    if auth.get("mode") != "oauth-personal":
        raise ValidationError("Antigravity ACP requires personal OAuth")
    if auth.get("profile_env") != "GEMINI_HOME":
        raise ValidationError("Antigravity ACP profile must use GEMINI_HOME")
    if auth.get("credential_source") != "runtime_owned":
        raise ValidationError("Antigravity ACP credential source is not runtime-owned")
    if auth.get("account_state") != "authenticated":
        raise ValidationError("Antigravity ACP account authentication is unproven")
    if _bool(auth.get("api_key_present"), "API-key presence"):
        raise ValidationError("API-key fallback is forbidden")
    if _bool(auth.get("cloud_credentials_present"), "Cloud credential presence"):
        raise ValidationError("Cloud credential fallback is forbidden")
    if _bool(auth.get("alternate_account"), "alternate account"):
        raise ValidationError("alternate-account fallback is forbidden")
    if auth.get("interactive_login") is not False:
        raise ValidationError("interactive login must fail closed")
    if auth.get("overage_state") not in {"disabled", "never"}:
        raise ValidationError("AI-credit overage state is unproven")
    return dict(auth)


def validate_model_observation(value: Any) -> Dict[str, Any]:
    """Require exact advertised/observed identity; effort is not inferred."""

    model = _exact_mapping(value, _OBS_MODEL_KEYS, "model observation")
    requested = _bounded_string(model.get("requested_id"), "requested model")
    advertised = model.get("advertised_ids")
    if not isinstance(advertised, list) or not advertised:
        raise ValidationError("advertised model catalog is unproven")
    if any(not isinstance(item, str) or not item for item in advertised):
        raise ValidationError("advertised model catalog is invalid")
    advertised = [_bounded_string(item, "advertised model") for item in advertised]
    if len(set(advertised)) != len(advertised) or requested not in advertised:
        raise ValidationError("requested model is not an exact advertised id")
    observed = _bounded_string(model.get("observed_id"), "observed model")
    if observed != requested:
        raise ValidationError("observed model does not match requested model")
    if model.get("selection_state") != "exact":
        raise ValidationError("model selection was not exact")
    if model.get("effort") is not None:
        raise ValidationError("ACP effort selection is unsupported until proved")
    return {
        "requested_id": requested,
        "advertised_ids": list(advertised),
        "observed_id": observed,
        "selection_state": "exact",
        "effort": None,
    }


def validate_question_observation(value: Any) -> Dict[str, Any]:
    """Represent fixed-choice questions only as fail-closed control metadata."""

    question = _exact_mapping(value, _OBS_QUESTION_KEYS, "question observation")
    state = question.get("state")
    if state not in {"none", "interaction_required", "cancelled"}:
        raise ValidationError("question state is invalid")
    interaction_id = question.get("interaction_id")
    if state == "none":
        if interaction_id is not None:
            raise ValidationError("question id is invalid for no question")
        if question.get("human_required") is not False or question.get("outcome") is not None:
            raise ValidationError("no-question state is invalid")
    else:
        if interaction_id is None:
            raise ValidationError("interaction question id is missing")
        validate_identifier(interaction_id, "interaction question")
        if question.get("human_required") is not True:
            raise ValidationError("interaction question requires a human")
        if question.get("outcome") != "cancelled":
            raise ValidationError("interaction question must fail closed")
    return {
        "state": state,
        "interaction_id": interaction_id,
        "human_required": question.get("human_required"),
        "outcome": question.get("outcome"),
    }


def validate_candidate_observation(value: Any) -> Dict[str, Any]:
    """Validate one bounded observation without retaining prompt/output bodies."""

    _reject_body_keys(value)
    observation = _exact_mapping(value, _OBSERVATION_KEYS, "candidate observation")
    if observation.get("schema") != OBSERVATION_SCHEMA:
        raise ValidationError("candidate observation schema is invalid")
    if observation.get("transport") != TRANSPORT_ID:
        raise ValidationError("candidate observation transport is invalid")
    if observation.get("target") != TARGET:
        raise ValidationError("candidate observation target is invalid")
    if observation.get("qualification") != "non_qualifying":
        raise ValidationError("candidate observation cannot claim qualification")

    runtime = _exact_mapping(observation.get("runtime"), _OBS_RUNTIME_KEYS, "runtime observation")
    if dict(runtime) != {
        "id": RUNTIME_ID,
        "version": RUNTIME_VERSION,
        "registry_revision": REGISTRY_REVISION,
    }:
        raise ValidationError("runtime observation does not match the pinned candidate")
    auth = validate_auth_observation(observation.get("auth"))
    model = validate_model_observation(observation.get("model"))
    session = _exact_mapping(observation.get("session"), _OBS_SESSION_KEYS, "session observation")
    session = {
        "session_id": validate_identifier(session.get("session_id"), "ACP session"),
        "conversation_id": validate_identifier(
            session.get("conversation_id"), "ACP conversation"
        ),
    }
    terminal = _terminal_mapping(observation.get("terminal"))
    if terminal.get("state") not in {"active", "completed", "failed", "cancelled", "halted"}:
        raise ValidationError("terminal state is invalid")
    exit_code = terminal.get("exit_code")
    if exit_code is not None and (
        isinstance(exit_code, bool) or not isinstance(exit_code, int) or exit_code < 0
    ):
        raise ValidationError("terminal exit code is invalid")
    result_id = terminal.get("result_id")
    if result_id is not None:
        result_id = validate_identifier(result_id, "ACP result")
    projected_terminal: Dict[str, Any] = {
        "state": terminal.get("state"),
        "exit_code": exit_code,
        "result_id": result_id,
    }
    status = terminal.get("status")
    if status is not None:
        if status not in ALLOWED_TURN_STATUSES:
            raise ValidationError("terminal status is invalid")
        projected_terminal["status"] = status
    stop_reason = bound_stop_reason(terminal.get("stop_reason"))
    if terminal.get("stop_reason") is not None and stop_reason is None:
        raise ValidationError("terminal stop_reason is invalid")
    if stop_reason is not None:
        projected_terminal["stop_reason"] = stop_reason
    error_code = bound_error_code(terminal.get("error_code"))
    if terminal.get("error_code") is not None and error_code is None:
        raise ValidationError("terminal error_code is invalid")
    if error_code is not None:
        projected_terminal["error_code"] = error_code
    event_kinds = terminal.get("event_kinds")
    if event_kinds is not None:
        if not isinstance(event_kinds, list) or any(
            not isinstance(item, str) or not item or len(item) > 64 for item in event_kinds
        ):
            raise ValidationError("terminal event_kinds are invalid")
        projected_terminal["event_kinds"] = list(event_kinds)[:16]
    question = validate_question_observation(observation.get("question"))
    record_state = observation.get("record_state")
    if record_state != "candidate_non_qualifying":
        raise ValidationError("candidate record state is invalid")
    return {
        "schema": OBSERVATION_SCHEMA,
        "transport": TRANSPORT_ID,
        "target": TARGET,
        "qualification": "non_qualifying",
        "runtime": dict(runtime),
        "auth": auth,
        "model": model,
        "session": session,
        "terminal": projected_terminal,
        "question": question,
        "record_state": "candidate_non_qualifying",
    }


def validate_antigravity_acp_catalog(value: Any) -> Dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValidationError("model catalog must be a mapping")
    if value.get("schema") != MODEL_CATALOG_SCHEMA:
        raise ValidationError("model catalog schema is invalid")
    if value.get("transport") != TRANSPORT_ID:
        raise ValidationError("model catalog transport is invalid")
    if value.get("target") != TARGET:
        raise ValidationError("model catalog target is invalid")
    advertised = value.get("advertised_models")
    if not isinstance(advertised, (list, tuple)) or not advertised:
        raise ValidationError("model catalog advertised_models is invalid")
    clean_advertised = []
    for item in advertised:
        if not isinstance(item, str) or not item.strip():
            raise ValidationError("model catalog model id is invalid")
        if item in clean_advertised:
            raise ValidationError("model catalog has duplicate model ids")
        clean_advertised.append(item)
    current = value.get("current_model")
    if not isinstance(current, str) or current not in clean_advertised:
        raise ValidationError("model catalog current_model is not in advertised_models")
    return {
        "schema": MODEL_CATALOG_SCHEMA,
        "transport": TRANSPORT_ID,
        "target": TARGET,
        "current_model": current,
        "advertised_models": clean_advertised,
    }


def verified_antigravity_acp_catalog() -> Dict[str, Any]:
    return {
        "schema": MODEL_CATALOG_SCHEMA,
        "transport": TRANSPORT_ID,
        "target": TARGET,
        "current_model": DEFAULT_ANTIGRAVITY_MODEL,
        "advertised_models": list(ADVERTISED_ANTIGRAVITY_MODELS),
    }


def map_runtime_antigravity_models(
    models: Any,
    *,
    requested_model: Optional[str] = None,
    catalog: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Map requested/selected/current models from one advertised catalog."""

    if not isinstance(models, Mapping):
        _raise_identity("model_observation_mismatch", "Antigravity ACP model catalog is unverified")
    current_model = models.get("currentModelId")
    if not isinstance(current_model, str) or not current_model.strip():
        _raise_identity("model_observation_mismatch", "observed Antigravity ACP model is unverified")
    current_model = current_model.strip()
    available_raw = models.get("availableModels") or models.get("availableModelIds")
    if not isinstance(available_raw, (list, tuple)) or not available_raw:
        _raise_identity(
            "model_observation_mismatch",
            "requested Antigravity ACP selector is unavailable",
        )
    advertised_ids: list[str] = []
    for item in available_raw:
        if isinstance(item, Mapping):
            mid = item.get("modelId")
        elif isinstance(item, str):
            mid = item
        else:
            _raise_identity(
                "model_observation_mismatch",
                "Antigravity ACP model catalog is unverified",
            )
            continue
        if not isinstance(mid, str) or not mid.strip():
            _raise_identity(
                "model_observation_mismatch",
                "Antigravity ACP model catalog is unverified",
            )
        mid = mid.strip()
        if mid in FALLBACK_OR_DEFAULT_MODEL_IDS:
            _raise_identity(
                "model_observation_mismatch",
                "Antigravity ACP fallback or default model is not bound requested-model proof",
            )
        if mid not in advertised_ids:
            advertised_ids.append(mid)
    if catalog is not None:
        validated = validate_antigravity_acp_catalog(catalog)
        if set(validated["advertised_models"]) != set(advertised_ids):
            _raise_identity(
                "model_observation_mismatch",
                "observed Antigravity ACP model is unverified",
            )
    requested = requested_model or DEFAULT_ANTIGRAVITY_MODEL
    if requested in FALLBACK_OR_DEFAULT_MODEL_IDS:
        _raise_identity(
            "model_observation_mismatch",
            "Antigravity ACP fallback or default model is not bound requested-model proof",
        )
    if requested not in advertised_ids:
        _raise_identity(
            "model_observation_mismatch",
            "requested Antigravity ACP selector is unavailable",
        )
    if current_model in FALLBACK_OR_DEFAULT_MODEL_IDS:
        _raise_identity(
            "model_observation_mismatch",
            "Antigravity ACP fallback or default model is not bound requested-model proof",
        )
    if current_model not in advertised_ids:
        _raise_identity(
            "model_observation_mismatch",
            "observed Antigravity ACP model is unverified",
        )
    if current_model != requested:
        _raise_identity(
            "model_observation_mismatch",
            "observed model does not match the bound Antigravity ACP runtime",
        )
    return {
        "current_model": current_model,
        "selected_model": requested,
        "advertised_models": advertised_ids,
        "requested_model": requested,
        "selection_state": "exact",
        "effort": None,
    }


def select_and_map_runtime_antigravity_models(
    runtime: Any,
    handle: Mapping[str, Any],
    *,
    requested_model: Optional[str] = None,
    catalog: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Select the requested AGY catalog model through public setModel, then remap."""

    status = runtime.get_status(
        reject_runtime_conversation_params({"handle": dict(handle)}, label="getStatus")
    )
    models = status.get("models") if isinstance(status, Mapping) else None
    requested = requested_model or DEFAULT_ANTIGRAVITY_MODEL
    if requested in FALLBACK_OR_DEFAULT_MODEL_IDS:
        _raise_identity(
            "model_observation_mismatch",
            "Antigravity ACP fallback or default model is not bound requested-model proof",
        )
    current = models.get("currentModelId") if isinstance(models, Mapping) else None
    if isinstance(current, str):
        current = current.strip()
    if current != requested:
        setter = getattr(runtime, "set_model", None)
        if not callable(setter):
            _raise_identity(
                "model_observation_mismatch",
                "observed model does not match the bound Antigravity ACP runtime",
            )
        try:
            setter(
                reject_runtime_conversation_params(
                    {"handle": dict(handle), "model": requested},
                    label="setModel",
                )
            )
        except (ValidationError, UnsupportedError):
            _raise_identity(
                "model_observation_mismatch",
                "observed model does not match the bound Antigravity ACP runtime",
            )
        status = runtime.get_status(
            reject_runtime_conversation_params({"handle": dict(handle)}, label="getStatus")
        )
        models = status.get("models") if isinstance(status, Mapping) else None
    mapped = map_runtime_antigravity_models(
        models,
        requested_model=requested_model,
        catalog=catalog,
    )
    if mapped["selected_model"] != mapped["current_model"] or mapped["selected_model"] != requested:
        _raise_identity(
            "model_observation_mismatch",
            "observed model does not match the bound Antigravity ACP runtime",
        )
    return mapped


def session_record_from_observation(
    observation: Mapping[str, Any],
    *,
    record_state: Optional[str] = None,
) -> Dict[str, Any]:
    obs = validate_candidate_observation(observation)
    state = record_state or "ACTIVE"
    if obs["terminal"]["state"] == "halted" and state in {
        "ACTIVE",
        "candidate_non_qualifying",
        None,
    }:
        state = "HALTED"
    return {
        "session": obs["session"]["session_id"],
        "target": TARGET,
        "state": state,
        "process": None,
        "transport": {"schema": "puppet.transport-binding/v1", "id": TRANSPORT_ID},
    }


def caller_fields_from_observation(
    observation: Mapping[str, Any],
    *,
    record_state: Optional[str] = None,
    halt_confirmed: Optional[bool] = None,
) -> Dict[str, Any]:
    record = session_record_from_observation(observation, record_state=record_state)
    if halt_confirmed is None:
        halt_confirmed = record["state"] == "HALTED"
    return caller_projection(
        record, transport_id=TRANSPORT_ID, halt_confirmed=halt_confirmed
    )


def _question_for_observation(question: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    if question is None:
        return {
            "state": "none",
            "interaction_id": None,
            "human_required": False,
            "outcome": None,
        }
    return {
        "state": "cancelled",
        "interaction_id": question.get("interaction_id"),
        "human_required": True,
        "outcome": "cancelled",
    }


def observation_from_runtime_turn(
    *,
    host_session: str,
    host_conversation_id: str,
    requested_model: str,
    observed_model: str,
    advertised_models: Sequence[str],
    terminal_state: str,
    result_id: str,
    question: Optional[Mapping[str, Any]] = None,
    auth: Optional[Mapping[str, Any]] = None,
    terminal_receipt: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    terminal: Dict[str, Any] = {
        "state": terminal_state,
        "exit_code": 0 if terminal_state in {"completed", "halted"} else 1,
        "result_id": result_id,
    }
    if isinstance(terminal_receipt, Mapping):
        for key in ("status", "stop_reason", "error_code", "event_kinds"):
            if key in terminal_receipt:
                terminal[key] = terminal_receipt[key]
    return validate_candidate_observation(
        {
            "schema": OBSERVATION_SCHEMA,
            "transport": TRANSPORT_ID,
            "target": TARGET,
            "qualification": "non_qualifying",
            "runtime": {
                "id": RUNTIME_ID,
                "version": RUNTIME_VERSION,
                "registry_revision": REGISTRY_REVISION,
            },
            "auth": auth
            if auth is not None
            else {
                "mode": "oauth-personal",
                "profile_env": "GEMINI_HOME",
                "credential_source": "runtime_owned",
                "account_state": "authenticated",
                "api_key_present": False,
                "cloud_credentials_present": False,
                "alternate_account": False,
                "interactive_login": False,
                "overage_state": "never",
            },
            "model": {
                "requested_id": requested_model,
                "advertised_ids": list(advertised_models),
                "observed_id": observed_model,
                "selection_state": "exact",
                "effort": None,
            },
            "session": {
                "session_id": host_session,
                "conversation_id": host_conversation_id,
            },
            "terminal": terminal,
            "question": _question_for_observation(question),
            "record_state": "candidate_non_qualifying",
        }
    )


def prove_antigravity_acp_observation(
    observation: Mapping[str, Any],
    *,
    expected_session: str,
    expected_conversation_id: str,
    expected_workspace: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    obs = validate_candidate_observation(observation)
    if obs["transport"] != TRANSPORT_ID:
        _raise_identity("identity_mismatch", "transport is not antigravity-acp")
    if obs["target"] != TARGET:
        _raise_identity("identity_mismatch", "target is not agy")
    if obs["session"]["session_id"] != expected_session:
        _raise_identity(
            "session_identity_mismatch",
            "observation session does not match expected session",
        )
    if obs["session"]["conversation_id"] != expected_conversation_id:
        _raise_identity(
            "session_identity_mismatch",
            "observation conversation does not match expected conversation",
        )
    return obs


HOST_PERMISSION_OUTCOMES = frozenset({"allow_once", "denied", "cancelled"})
HOST_PERMISSION_KINDS = frozenset(
    {"edit", "denied", "interaction", "elicitation", "ambiguous", "host"}
)
HOST_PERMISSION_DECISION_LIMIT = 32
HOST_PERMISSION_ACP_KINDS = frozenset(
    {
        "read",
        "edit",
        "delete",
        "move",
        "search",
        "execute",
        "think",
        "fetch",
        "switch_mode",
        "other",
        "absent",
    }
)
HOST_PERMISSION_KIND_SOURCES = frozenset({"standardized", "inferred", "absent"})
HOST_PERMISSION_ID_CLASSES = frozenset({"opaque", "interaction", "absent"})
HOST_PERMISSION_PATH_SOURCES = frozenset(
    {"raw_input", "locations", "both", "absent", "multiple", "conflicting"}
)
HOST_PERMISSION_PATH_CARDINALITIES = frozenset({"zero", "one", "multiple"})
HOST_PERMISSION_PATH_CLASSES = frozenset(
    {"intended", "non_intended", "absent", "ambiguous"}
)
HOST_PERMISSION_OPTION_KINDS = frozenset(
    {"allow_once", "allow_always", "reject_once", "reject_always"}
)
HOST_PERMISSION_REASONS = frozenset(
    {
        "granted_once",
        "replay",
        "absent_kind",
        "other_kind",
        "inferred_kind_only",
        "absent_path",
        "multiple_paths",
        "conflicting_paths",
        "non_intended_path",
        "absent_allow_once",
        "interaction",
        "elicitation",
        "ambiguous",
        "missing_session",
    }
)


def _enum_member(value: Any, allowed: frozenset) -> bool:
    return isinstance(value, str) and value in allowed


def _bound_host_option_kinds(value: Any) -> list:
    if not isinstance(value, list):
        return []
    bounded = []
    for option in value:
        if _enum_member(option, HOST_PERMISSION_OPTION_KINDS) and option not in bounded:
            bounded.append(option)
        if len(bounded) >= len(HOST_PERMISSION_OPTION_KINDS):
            break
    return bounded


def _bound_host_permission_diagnostics(item: Mapping[str, Any]) -> Dict[str, Any]:
    """Copy allowlisted body-free permission classifications only."""

    bounded: Dict[str, Any] = {}
    kind = item.get("kind")
    if _enum_member(kind, HOST_PERMISSION_ACP_KINDS):
        bounded["kind"] = kind
    kind_source = item.get("kind_source")
    if _enum_member(kind_source, HOST_PERMISSION_KIND_SOURCES):
        bounded["kind_source"] = kind_source
    id_class = item.get("id_class")
    if _enum_member(id_class, HOST_PERMISSION_ID_CLASSES):
        bounded["id_class"] = id_class
    path_source = item.get("path_source")
    if _enum_member(path_source, HOST_PERMISSION_PATH_SOURCES):
        bounded["path_source"] = path_source
    path_cardinality = item.get("path_cardinality")
    if _enum_member(path_cardinality, HOST_PERMISSION_PATH_CARDINALITIES):
        bounded["path_cardinality"] = path_cardinality
    path_class = item.get("path_class")
    if _enum_member(path_class, HOST_PERMISSION_PATH_CLASSES):
        bounded["path_class"] = path_class
    offered = item.get("offered_option_kinds")
    if isinstance(offered, list):
        bounded["offered_option_kinds"] = _bound_host_option_kinds(offered)
    reason = item.get("reason")
    if _enum_member(reason, HOST_PERMISSION_REASONS):
        bounded["reason"] = reason
    return bounded


def require_host_permission_outcome(permission: Mapping[str, Any]) -> Dict[str, Any]:
    """Record a body-free host permission decision. Never persist allow-always."""

    if not isinstance(permission, Mapping):
        raise ValidationError("host permission outcome is missing")
    if permission.get("schema") not in {HOST_PERMISSION_SCHEMA, None}:
        raise ValidationError("host permission schema is invalid")
    outcome = permission.get("outcome")
    if not _enum_member(outcome, HOST_PERMISSION_OUTCOMES):
        raise ValidationError("host permission outcome is invalid")
    grant_count = permission.get("grant_count", 1 if outcome == "allow_once" else 0)
    if not isinstance(grant_count, int) or isinstance(grant_count, bool) or grant_count not in {0, 1}:
        raise ValidationError("host permission grant must stay one-time")
    if permission.get("allowed") is True and grant_count != 1:
        raise ValidationError("host permission must not mark a non-grant as allowed")
    if grant_count == 1 and permission.get("allowed") is not True:
        raise ValidationError("one-time host permission must be marked allowed")
    if permission.get("invented_decision") is not None:
        raise ValidationError("antigravity-acp must not invent a permission decision")
    if permission.get("persisted") is not False:
        raise ValidationError("host permission must not persist an approval")
    if permission.get("approve_all") is not False:
        raise ValidationError("host permission must not import approve-all")
    if permission.get("os_sandbox") is not False:
        raise ValidationError("host permission must not claim an OS sandbox")
    if permission.get("fs") is not False or permission.get("terminal") is not False:
        raise ValidationError("filesystem and terminal callbacks must stay disabled")
    if permission.get("ordinary_launch") != "unavailable":
        raise ValidationError("ordinary launch must stay unavailable")
    if permission.get("body_retained") is not False:
        raise ValidationError("host permission receipt retained a body")
    kind = permission.get("permission_kind") or permission.get("permission_id") or "host"
    if not _enum_member(kind, HOST_PERMISSION_KINDS):
        raise ValidationError("host permission kind is invalid")
    decisions = permission.get("decisions")
    bounded_decisions = []
    if decisions is None:
        bounded_decisions = [
            {
                "outcome": outcome,
                "permission_kind": kind,
                **_bound_host_permission_diagnostics(permission),
            }
        ]
        decision_count = 1
        decisions_truncated = False
    elif not isinstance(decisions, list):
        raise ValidationError("host permission decisions are invalid")
    else:
        for item in decisions:
            if not isinstance(item, Mapping):
                raise ValidationError("host permission decisions are invalid")
            item_outcome = item.get("outcome")
            item_kind = item.get("permission_kind")
            if item_outcome == "allow_always" or item.get("kind") == "allow_always":
                raise ValidationError("host permission must not persist allow-always")
            if not _enum_member(item_outcome, HOST_PERMISSION_OUTCOMES):
                raise ValidationError("host permission decision outcome is invalid")
            if not _enum_member(item_kind, HOST_PERMISSION_KINDS):
                raise ValidationError("host permission decision kind is invalid")
            if item.get("allowed") is True and item_outcome != "allow_once":
                raise ValidationError("host permission must not mark a non-grant as allowed")
            bounded_decisions.append(
                {
                    "outcome": item_outcome,
                    "permission_kind": item_kind,
                    **_bound_host_permission_diagnostics(item),
                }
            )
        reported = permission.get("decision_count")
        if (
            isinstance(reported, int)
            and not isinstance(reported, bool)
            and reported >= len(decisions)
        ):
            decision_count = reported
        else:
            decision_count = len(decisions)
        decisions_truncated = permission.get("decisions_truncated") is True
        if len(bounded_decisions) > HOST_PERMISSION_DECISION_LIMIT:
            bounded_decisions = bounded_decisions[-HOST_PERMISSION_DECISION_LIMIT:]
            decisions_truncated = True
        if decision_count > len(bounded_decisions):
            decisions_truncated = True
    if any(
        item.get("outcome") == "allow_always"
        or item.get("kind") == "allow_always"
        for item in (decisions or ())
        if isinstance(item, Mapping)
    ):
        raise ValidationError("host permission must not persist allow-always")
    receipt = {
        "schema": HOST_PERMISSION_SCHEMA,
        "state": outcome,
        "outcome": outcome,
        "permission_id": kind,
        "permission_kind": kind,
        "decisions": bounded_decisions,
        "decision_count": decision_count,
        "decisions_truncated": decisions_truncated,
        "grant_count": grant_count,
        "allowed": grant_count == 1,
        "persisted": False,
        "approve_all": False,
        "os_sandbox": False,
        "fs": False,
        "terminal": False,
        "ordinary_launch": "unavailable",
        "body_retained": False,
        "invented_decision": None,
    }
    receipt.update(_bound_host_permission_diagnostics(permission))
    return receipt


def fixture_observation(**changes: Any) -> Dict[str, Any]:
    base = {
        "schema": OBSERVATION_SCHEMA,
        "transport": TRANSPORT_ID,
        "target": TARGET,
        "qualification": "non_qualifying",
        "runtime": {
            "id": RUNTIME_ID,
            "version": RUNTIME_VERSION,
            "registry_revision": REGISTRY_REVISION,
        },
        "auth": {
            "mode": "oauth-personal",
            "profile_env": "GEMINI_HOME",
            "credential_source": "runtime_owned",
            "account_state": "authenticated",
            "api_key_present": False,
            "cloud_credentials_present": False,
            "alternate_account": False,
            "interactive_login": False,
            "overage_state": "never",
        },
        "model": {
            "requested_id": DEFAULT_ANTIGRAVITY_MODEL,
            "advertised_ids": list(ADVERTISED_ANTIGRAVITY_MODELS),
            "observed_id": DEFAULT_ANTIGRAVITY_MODEL,
            "selection_state": "exact",
            "effort": None,
        },
        "session": {
            "session_id": "ses-agy-1",
            "conversation_id": "conv-agy-1",
        },
        "terminal": {
            "state": "completed",
            "exit_code": 0,
            "result_id": "req-agy-1",
        },
        "question": {
            "state": "none",
            "interaction_id": None,
            "human_required": False,
            "outcome": None,
        },
        "record_state": "candidate_non_qualifying",
    }
    base.update(changes)
    return validate_candidate_observation(base)


def _load_ownership(isolated_root: Path) -> Dict[str, Any]:
    from antigravity_acpx import load_isolated_root

    return load_isolated_root(isolated_root)


def _mark_cleanup_unknown(
    isolated_root: Path,
    extras: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    from antigravity_acpx import mark_cleanup_unknown

    return mark_cleanup_unknown(isolated_root, extras)


class AntigravityAcpSyntheticRuntime:
    """In-process public-runtime peer. Never starts live AGY or Cursor."""

    def __init__(
        self,
        *,
        handle: Optional[Mapping[str, Any]] = None,
        models: Optional[Mapping[str, Any]] = None,
        result: Optional[Mapping[str, Any]] = None,
        events: Optional[Sequence[Mapping[str, Any]]] = None,
        unsupported_backend_close: bool = False,
        close_error: Optional[BaseException] = None,
        permission: Optional[Mapping[str, Any]] = None,
        question: Optional[Mapping[str, Any]] = None,
        set_model_supported: bool = True,
    ):
        self.handle = None if handle is None else dict(handle)
        self.models = dict(models) if models is not None else {
            "currentModelId": DEFAULT_ANTIGRAVITY_MODEL,
            "availableModelIds": list(ADVERTISED_ANTIGRAVITY_MODELS),
        }
        self.result = dict(result or {"status": "completed", "stopReason": "end_turn"})
        self.events = list(events or ())
        self.unsupported_backend_close = unsupported_backend_close
        self.close_error = close_error
        self.permission = None if permission is None else dict(permission)
        self.question = None if question is None else dict(question)
        self.set_model_supported = set_model_supported
        self.ensure_calls: list[Dict[str, Any]] = []
        self.status_calls: list[Dict[str, Any]] = []
        self.set_model_calls: list[Dict[str, Any]] = []
        self.start_calls: list[Dict[str, Any]] = []
        self.close_calls: list[Dict[str, Any]] = []
        self.process_lifecycle: Dict[str, Any] = {"started": [], "exits": []}

    def ensure_session(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        reject_runtime_conversation_params(payload, label="ensureSession")
        self.ensure_calls.append(dict(payload))
        if self.handle is not None:
            return dict(self.handle)
        return {
            "sessionKey": payload["sessionKey"],
            "cwd": payload["cwd"],
            "backend": "acpx",
            "runtimeSessionName": "acpx:%s" % payload["sessionKey"],
            "acpxRecordId": "record-owned-1",
            "backendSessionId": "backend-session-1",
            "agentSessionId": "agent-session-1",
        }

    def get_status(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        reject_runtime_conversation_params(payload, label="getStatus")
        self.status_calls.append(dict(payload))
        last_request = self.start_calls[-1]["requestId"] if self.start_calls else None
        status = {"models": dict(self.models)}
        if last_request is not None:
            status["lastRequestId"] = last_request
        return status

    def set_model(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        reject_runtime_conversation_params(payload, label="setModel")
        self.set_model_calls.append(dict(payload))
        if not self.set_model_supported:
            raise ValidationError("setModel is unsupported")
        model = payload.get("model")
        advertised = []
        for item in self.models.get("availableModelIds") or self.models.get("availableModels") or ():
            if isinstance(item, Mapping):
                advertised.append(item.get("modelId"))
            else:
                advertised.append(item)
        if not isinstance(model, str) or model not in advertised:
            _raise_identity(
                "model_observation_mismatch",
                "requested Antigravity ACP selector is unavailable",
            )
        if model in FALLBACK_OR_DEFAULT_MODEL_IDS:
            _raise_identity(
                "model_observation_mismatch",
                "Antigravity ACP fallback or default model is not bound requested-model proof",
            )
        self.models["currentModelId"] = model
        return {}

    def start_turn(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        reject_runtime_conversation_params(payload, label="startTurn")
        timeout_ms = require_bounded_timeout_ms(payload.get("timeoutMs"), "candidate prompt")
        recorded = dict(payload)
        recorded["timeoutMs"] = timeout_ms
        self.start_calls.append(recorded)
        return {
            "requestId": payload["requestId"],
            "timeoutMs": timeout_ms,
            "events": list(self.events),
            "result": dict(self.result),
            "process_lifecycle": dict(self.process_lifecycle),
        }

    def close(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        reject_runtime_conversation_params(payload, label="close")
        self.close_calls.append(dict(payload))
        if self.close_error is not None:
            raise self.close_error
        if self.unsupported_backend_close:
            raise _backend_unsupported_close(
                "Agent does not support session/close for surviving-peer."
            )
        return {"status": "completed"}

class AntigravityAcpNodeRuntime:
    """Pinned public createAcpRuntime through the task-owned archive closure."""

    def __init__(
        self,
        *,
        workspace: Path,
        isolated_root: Path,
        repo_root: Path,
        env: Optional[Mapping[str, str]] = None,
        synthetic_peer: bool = False,
        executable: Optional[Path] = None,
        candidate_args: Optional[Sequence[str]] = None,
        synthetic_peer_script: Optional[str] = None,
        synthetic_peer_survive: bool = False,
        synthetic_peer_hang_prompt: bool = False,
        synthetic_peer_permission: Optional[str] = None,
        startup_timeout_ms: int = STARTUP_TIMEOUT_MS,
    ):
        if synthetic_peer and executable is not None:
            raise ValidationError("synthetic peer injection cannot carry a candidate executable")
        if synthetic_peer and env is not None:
            raise ValidationError("synthetic peer injection cannot carry a candidate process environment")
        driver = Path(repo_root) / CONTROLLER_RUNTIME_DRIVER
        allowed_env: Optional[Dict[str, str]] = None
        if not synthetic_peer:
            if env is None:
                raise ValidationError("antigravity-acp official candidate process environment is missing")
            helper = env.get("ANTIGRAVITY_HARNESS_PATH")
            profile_path = env.get("GEMINI_HOME")
            if not isinstance(helper, str) or not isinstance(profile_path, str):
                raise ValidationError("antigravity-acp official candidate process environment is invalid")
            allowed_env = require_antigravity_process_env(
                env, helper=helper, profile_path=profile_path
            )
        self.kind = SYNTHETIC_PEER_KIND if synthetic_peer else CANDIDATE_RUNTIME_KIND
        self._proc = subprocess.Popen(
            ["node", str(driver)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            cwd=str(repo_root),
            **({} if allowed_env is None else {"env": allowed_env}),
        )
        self.last_process_lifecycle: Dict[str, Any] = {"started": [], "exits": []}
        self._shutdown_complete = False
        payload: Dict[str, Any] = {
            "cwd": str(workspace),
            "isolatedRoot": str(isolated_root),
            "syntheticPeer": True if synthetic_peer else False,
            "agent": "antigravity",
        }
        if not synthetic_peer:
            payload["candidate"] = {
                "kind": CANDIDATE_RUNTIME_KIND,
                "agent": "antigravity",
                "executable": None if executable is None else str(executable),
                "args": list(candidate_args or ()),
            }
            payload["allowedProcessEnv"] = dict(allowed_env or {})
        elif synthetic_peer:
            if synthetic_peer_script:
                payload["syntheticPeerScript"] = synthetic_peer_script
            payload["syntheticPeerSurvive"] = bool(synthetic_peer_survive)
            payload["syntheticPeerHangPrompt"] = bool(synthetic_peer_hang_prompt)
            if synthetic_peer_permission:
                payload["syntheticPeerPermission"] = synthetic_peer_permission
        payload["startupTimeoutMs"] = require_bounded_timeout_ms(
            startup_timeout_ms, "startup"
        )
        self._rpc("create", payload)

    def child_process_identity(self) -> Dict[str, Any]:
        return {
            "pid": self._proc.pid,
            "returncode": self._proc.returncode,
            "exited": self._proc.poll() is not None,
            "kind": self.kind,
        }

    def ensure_session(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        return self._rpc("ensureSession", dict(payload))

    def get_status(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        return self._rpc("getStatus", dict(payload))

    def set_model(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        return self._rpc("setModel", dict(payload))

    def start_turn(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        return self._rpc("startTurn", dict(payload))

    def close(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        return self._rpc("close", dict(payload))

    def wait_for_owned_worker_exit(
        self,
        session_key: str,
        *,
        timeout_ms: int = WORKER_EXIT_WAIT_MS,
    ) -> Optional[Dict[str, Any]]:
        proof = self._rpc(
            "waitForOwnedExit",
            {"sessionKey": session_key, "timeoutMs": timeout_ms},
        )
        if proof.get("status") != "exited":
            return None
        exits = proof.get("exits") or []
        if not isinstance(exits, list) or not exits:
            return None
        first = exits[0]
        return dict(first) if isinstance(first, Mapping) else None

    def process_lifecycle_snapshot(self, session_key: str) -> Dict[str, Any]:
        if self._shutdown_complete:
            return dict(self.last_process_lifecycle)
        snapshot = self._rpc("processLifecycleSnapshot", {"sessionKey": session_key})
        self.last_process_lifecycle = (
            dict(snapshot) if snapshot else {"started": [], "exits": []}
        )
        return dict(self.last_process_lifecycle)

    def shutdown(self) -> None:
        try:
            result = self._rpc("shutdown", {})
            lifecycle = result.get("process_lifecycle")
            if isinstance(lifecycle, Mapping):
                self.last_process_lifecycle = dict(lifecycle)
            self._shutdown_complete = True
        finally:
            if self._proc.stdin is not None:
                self._proc.stdin.close()
            if self._proc.stdout is not None:
                self._proc.stdout.close()
            if self._proc.poll() is None:
                self._proc.terminate()
            self._proc.wait(timeout=30)

    def _rpc(self, op: str, payload: Mapping[str, Any]) -> Dict[str, Any]:
        if self._proc.stdin is None or self._proc.stdout is None:
            raise ValidationError("controller runtime driver is unavailable")
        message = json.dumps({"op": op, "payload": dict(payload)}, separators=(",", ":"))
        self._proc.stdin.write(message + "\n")
        self._proc.stdin.flush()
        line = self._proc.stdout.readline()
        if not line:
            raise ValidationError("controller runtime driver closed")
        response = json.loads(line)
        if response.get("ok") is not True:
            detail = response.get("error") or "controller runtime driver failed"
            code = response.get("code")
            if code in {
                "OWNER_MISMATCH",
                "SESSION_MISMATCH",
                "WORKSPACE_MISMATCH",
                "IDENTITY_MISMATCH",
            }:
                _raise_identity("identity_mismatch", str(detail))
            if code == "ACP_BACKEND_UNSUPPORTED_CONTROL":
                raise _backend_unsupported_close(str(detail))
            raise ValidationError(str(detail))
        value = response.get("value")
        return {} if value is None else dict(value)


class AntigravityAcpRuntimeRunner:
    """Derive antigravity-acp observations from a public runtime for the controller."""

    def __init__(
        self,
        runtime: Any,
        *,
        isolated_root: Path,
        owner: str,
        session: str,
        conversation_id: str,
        request_id: str,
        workspace: Mapping[str, Any],
        requested_model: Optional[str] = None,
        text: Optional[str] = None,
        catalog: Optional[Mapping[str, Any]] = None,
        halt: bool = False,
        permission: Optional[Mapping[str, Any]] = None,
        question: Optional[Mapping[str, Any]] = None,
        auth: Optional[Mapping[str, Any]] = None,
        session_mode: str = SESSION_MODE_ONESHOT,
        finish_policy: str = FINISH_POLICY_DISCARD,
        prompt_timeout_ms: int = CANDIDATE_PROMPT_TIMEOUT_MS,
        intended_write_relative: Optional[str] = None,
    ):
        self.runtime = runtime
        self.isolated_root = Path(isolated_root)
        self.owner = owner
        self.session = session
        self.conversation_id = conversation_id
        self.request_id = request_id
        self.workspace = dict(workspace)
        self.requested_model = requested_model or DEFAULT_ANTIGRAVITY_MODEL
        self._text = None if text is None else require_runtime_task_text(text)
        self._supplied_catalog = None if catalog is None else dict(catalog)
        self._catalog = self._supplied_catalog
        self.require_halt = halt
        self.permission = None if permission is None else dict(permission)
        self.question = None if question is None else dict(question)
        self.auth = None if auth is None else dict(auth)
        if session_mode not in {SESSION_MODE_ONESHOT, SESSION_MODE_PERSISTENT}:
            raise ValidationError("antigravity-acp session mode is invalid")
        if finish_policy not in {
            FINISH_POLICY_DISCARD,
            FINISH_POLICY_RETAIN,
            FINISH_POLICY_LOCAL_RELEASE,
        }:
            raise ValidationError("antigravity-acp finish policy is invalid")
        self.session_mode = session_mode
        self.finish_policy = finish_policy
        self.discarded_events: Optional[Dict[str, Any]] = None
        self.permission_outcome: Optional[Dict[str, Any]] = None
        self.question_outcome: Optional[Dict[str, Any]] = None
        self._observation: Optional[Dict[str, Any]] = None
        self.handle: Optional[Dict[str, str]] = None
        self.backend_identity_changes: list[Dict[str, Optional[str]]] = []
        self.local_release = False
        self.persistent_state = "absent"
        self.final_discard = False
        self.backend_discard: str = "closed"
        self.selected_model: Optional[str] = None
        self.current_model: Optional[str] = None
        self.owned_worker: Optional[Dict[str, Any]] = None
        self.cleanup_receipt: Optional[Dict[str, Any]] = None
        self.terminal_receipt: Optional[Dict[str, Any]] = None
        self.receipt_durability = bound_receipt_durability(written=False)
        self.process_lifecycle: Dict[str, Any] = {"started": [], "exits": []}
        self.worker_termination = "unknown"
        self.cleanup_uncertain = False
        self.replacement_blocked = False
        self.worker_exit_wait_ms = WORKER_EXIT_WAIT_MS
        self.prompt_timeout_ms = require_bounded_timeout_ms(
            prompt_timeout_ms, "candidate prompt"
        )
        self.intended_write_relative = (
            None
            if intended_write_relative is None
            else require_intended_write_relative(intended_write_relative)
        )
        self._mark_cleanup_unknown: Any = None

    def bind_task_text(self, text: Any) -> str:
        self._text = require_runtime_task_text(text)
        return self._text

    def has_task_text(self) -> bool:
        return self._text is not None

    @staticmethod
    def available() -> bool:
        return False

    def catalog(self) -> Optional[Dict[str, Any]]:
        if self._observation is None:
            self.observation()
        return None if self._catalog is None else dict(self._catalog)

    def observation(self) -> Dict[str, Any]:
        if self._observation is None:
            self._observation = self._derive()
        return validate_candidate_observation(self._observation)

    def _validate_ownership(self) -> Dict[str, Any]:
        ownership = _load_ownership(self.isolated_root)
        if (
            ownership.get("owner") != self.owner
            or ownership.get("session") != self.session
            or ownership.get("conversation_id") != self.conversation_id
        ):
            _raise_identity(
                "session_identity_mismatch",
                "ownership must validate before session or prompt",
            )
        if ownership.get("transport") != TRANSPORT_ID or ownership.get("target") != TARGET:
            _raise_identity(
                "identity_mismatch",
                "isolated state root is not an Antigravity ACP ownership claim",
            )
        if ownership.get("cleanup") == "unknown" or ownership.get("replacement_blocked"):
            _raise_identity(
                "cleanup_unknown",
                "process-query failure left cleanup unknown; replacement is blocked",
            )
        return ownership

    def _fence_cleanup(self, extras: Optional[Mapping[str, Any]] = None) -> None:
        if self._mark_cleanup_unknown is None:
            from antigravity_acpx import mark_cleanup_unknown

            self._mark_cleanup_unknown = mark_cleanup_unknown
        try:
            self._mark_cleanup_unknown(self.isolated_root, extras)
        except Exception:
            pass

    def _is_unsupported_backend_session_close(self, exc: BaseException) -> bool:
        return is_unsupported_backend_session_close(exc)

    def _model_receipt_fields(self) -> Dict[str, str]:
        fields: Dict[str, str] = {}
        if self.selected_model:
            fields["selected_model"] = self.selected_model
        if self.current_model:
            fields["current_model"] = self.current_model
        return fields

    def _persist_turn_models(self) -> None:
        if not self.selected_model or not self.current_model:
            return
        try:
            from antigravity_acpx import persist_turn_models

            persist_turn_models(
                self.isolated_root,
                session=self.session,
                conversation_id=self.conversation_id,
                selected_model=self.selected_model,
                current_model=self.current_model,
            )
        except Exception:
            pass

    def _ingest_process_lifecycle(self, snapshot: Mapping[str, Any]) -> Dict[str, Any]:
        self.process_lifecycle = {
            "started": [
                public_worker_identity(item)
                for item in snapshot.get("started", [])
                if isinstance(item, Mapping)
            ],
            "exits": [
                public_worker_identity(item)
                for item in snapshot.get("exits", [])
                if isinstance(item, Mapping)
            ],
        }
        return self.process_lifecycle

    def _snapshot_process_lifecycle(self, handle: Mapping[str, Any]) -> Dict[str, Any]:
        session_key = handle.get("sessionKey")
        snapshotter = getattr(self.runtime, "process_lifecycle_snapshot", None)
        if isinstance(session_key, str) and callable(snapshotter):
            try:
                snapshot = snapshotter(session_key)
            except Exception:
                snapshot = None
            if isinstance(snapshot, Mapping):
                return self._ingest_process_lifecycle(snapshot)
        return self.process_lifecycle

    def _derive_worker_termination(self, handle: Mapping[str, Any]) -> str:
        session_key = handle.get("sessionKey")
        if not isinstance(session_key, str) or not session_key:
            return "unknown"
        started = [
            item
            for item in self.process_lifecycle.get("started", [])
            if is_owned_session_process(item, session_key)
        ]
        exits = self.process_lifecycle.get("exits", [])
        if started and all(
            any(process_identities_match(item, exit_record) for exit_record in exits)
            for item in started
        ):
            return "proven"
        return "unknown"

    def _persist_cleanup_receipt(
        self,
        *,
        status: str,
        observed: str,
        extras: Optional[Mapping[str, Any]] = None,
    ) -> None:
        payload: Dict[str, Any] = {
            **self._model_receipt_fields(),
            "local_release": self.local_release,
            "persistent_state": self.persistent_state,
            "final_discard": self.final_discard,
            "backend_discard": self.backend_discard,
            "worker_termination": self.worker_termination,
            "cleanup_uncertain": self.cleanup_uncertain,
            "replacement_blocked": self.replacement_blocked,
            "process_lifecycle": self.process_lifecycle,
        }
        if extras:
            payload.update(dict(extras))
        if self.terminal_receipt and "terminal" not in payload:
            payload["terminal"] = dict(self.terminal_receipt)
        if self.owned_worker and "worker" not in payload:
            payload["worker"] = self.owned_worker
        if self.backend_discard != "closed":
            payload.setdefault("backendSessionDiscard", self.backend_discard)
        self.cleanup_receipt = {"status": status, "observed": observed, **payload}
        try:
            from antigravity_acpx import persist_cleanup_receipt

            persist_cleanup_receipt(
                self.isolated_root,
                status=status,
                observed=observed,
                extras=payload,
            )
        except Exception:
            pass

    def _wait_for_owned_worker_exit(self, handle: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
        session_key = handle.get("sessionKey")
        waiter = getattr(self.runtime, "wait_for_owned_worker_exit", None)
        if not isinstance(session_key, str) or not callable(waiter):
            return None
        try:
            proof = waiter(session_key, timeout_ms=self.worker_exit_wait_ms)
        except Exception:
            return None
        if not isinstance(proof, Mapping):
            return None
        return dict(proof)

    def _admit_close(self, *, discard_persistent_state: bool) -> None:
        if discard_persistent_state:
            self.final_discard = True
            self.persistent_state = "discarded"
        else:
            self.local_release = True
            self.persistent_state = "retained"

    def _owned_close(
        self,
        handle: Mapping[str, Any],
        *,
        primary: Optional[BaseException] = None,
        discard_persistent_state: bool = True,
        reason: str = "antigravity-acp-owned-close",
    ) -> None:
        self._persist_turn_models()
        try:
            self.runtime.close(
                reject_runtime_conversation_params(
                    {
                        "handle": dict(handle),
                        "reason": reason,
                        "discardPersistentState": discard_persistent_state,
                    },
                    label="close",
                )
            )
            self._snapshot_process_lifecycle(handle)
            self.backend_discard = "closed"
            self.worker_termination = self._derive_worker_termination(handle)
            self.cleanup_uncertain = False
            self.replacement_blocked = False
            self._admit_close(discard_persistent_state=discard_persistent_state)
            self._persist_cleanup_receipt(
                status="completed",
                observed="runtime_close_returned",
            )
        except BaseException as exc:
            if self._is_unsupported_backend_session_close(exc):
                observed_exit = self._wait_for_owned_worker_exit(handle)
                if observed_exit is not None:
                    self.backend_discard = "unsupported"
                    self.owned_worker = public_worker_identity(observed_exit)
                    self._snapshot_process_lifecycle(handle)
                    self.worker_termination = "proven"
                    self.cleanup_uncertain = False
                    self.replacement_blocked = False
                    self.local_release = True
                    self.final_discard = False
                    self.persistent_state = (
                        "retained" if not discard_persistent_state else "unknown"
                    )
                    self._persist_cleanup_receipt(
                        status="completed",
                        observed="local_worker_terminated_backend_session_discard_unsupported",
                        extras={
                            "message": (
                                "local worker termination observed; "
                                "backend session discard unsupported"
                            ),
                            "backendSessionDiscard": "unsupported",
                            "worker": self.owned_worker,
                        },
                    )
                    if primary is not None:
                        raise primary
                    return
                self.backend_discard = "unsupported"
                self._snapshot_process_lifecycle(handle)
                self.worker_termination = "unknown"
                self.cleanup_uncertain = True
                self.replacement_blocked = True
                self._persist_cleanup_receipt(
                    status="uncertain",
                    observed="runtime_close_failed",
                    extras={"backendSessionDiscard": "unsupported"},
                )
                self._fence_cleanup(
                    {
                        "observed": "runtime_close_failed",
                        "backendSessionDiscard": "unsupported",
                        "worker_termination": self.worker_termination,
                        "cleanup_uncertain": self.cleanup_uncertain,
                        "replacement_blocked": self.replacement_blocked,
                        "process_lifecycle": self.process_lifecycle,
                        **self._model_receipt_fields(),
                    }
                )
            else:
                self.worker_termination = "unknown"
                self.cleanup_uncertain = True
                self.replacement_blocked = True
                self._persist_cleanup_receipt(
                    status="uncertain",
                    observed="runtime_close_failed",
                )
                self._fence_cleanup(
                    {
                        "observed": "runtime_close_failed",
                        "worker_termination": self.worker_termination,
                        "cleanup_uncertain": self.cleanup_uncertain,
                        "replacement_blocked": self.replacement_blocked,
                        "process_lifecycle": self.process_lifecycle,
                        **self._model_receipt_fields(),
                    }
                )
            if primary is not None:
                raise primary
            raise
        if primary is not None:
            raise primary

    def _reject_conflated_ids(self, handle: Mapping[str, str]) -> None:
        foreign = {
            handle.get("backendSessionId"),
            handle.get("acpxRecordId"),
            handle.get("runtimeSessionName"),
            handle.get("agentSessionId"),
        }
        host = {self.conversation_id, self.request_id}
        if foreign & host:
            _raise_identity(
                "identity_mismatch",
                "runtime identities must not be fabricated from host correlation",
            )

    def _bind_handle(self, raw_handle: Mapping[str, Any]) -> Dict[str, str]:
        handle = project_runtime_handle(raw_handle)
        if handle.get("sessionKey") != self.session:
            _raise_identity(
                "session_identity_mismatch",
                "runtime sessionKey does not match the host session",
            )
        if os.path.realpath(handle.get("cwd", "")) != os.path.realpath(
            self.workspace["path"]
        ):
            _raise_identity(
                "workspace_identity_mismatch",
                "runtime cwd does not match the bound checkout",
            )
        self._reject_conflated_ids(handle)
        previous = self.handle
        if previous is not None:
            previous_backend = previous.get("backendSessionId")
            next_backend = handle.get("backendSessionId")
            if previous_backend != next_backend:
                self.backend_identity_changes.append(
                    {
                        "previous_backend_session_id": previous_backend,
                        "backend_session_id": next_backend,
                    }
                )
        self.handle = handle
        self.persistent_state = "retained"
        return handle

    def _ensure_owned_handle(self, *, reconnect: bool = False) -> Dict[str, str]:
        if self.handle is not None and not reconnect:
            return dict(self.handle)
        ensure_input = reject_runtime_conversation_params(
            {
                "sessionKey": self.session,
                "agent": "antigravity",
                "mode": self.session_mode,
                "cwd": self.workspace["path"],
            },
            label="ensureSession",
        )
        return self._bind_handle(self.runtime.ensure_session(ensure_input))

    def _run_turn(self, handle: Mapping[str, Any]) -> Dict[str, Any]:
        text = require_runtime_task_text(self._text)
        mapped = select_and_map_runtime_antigravity_models(
            self.runtime,
            handle,
            requested_model=self.requested_model,
            catalog=self._supplied_catalog,
        )
        self.selected_model = mapped["selected_model"]
        self.current_model = mapped["current_model"]
        self._persist_turn_models()
        self._catalog = (
            self._supplied_catalog
            if self._supplied_catalog is not None
            else {
                "schema": MODEL_CATALOG_SCHEMA,
                "transport": TRANSPORT_ID,
                "target": TARGET,
                "current_model": mapped["current_model"],
                "advertised_models": mapped["advertised_models"],
            }
        )
        turn = self.runtime.start_turn(
            reject_runtime_conversation_params(
                {
                    "handle": dict(handle),
                    "text": text,
                    "mode": "prompt",
                    "requestId": self.request_id,
                    "timeoutMs": self.prompt_timeout_ms,
                    "intendedRelativePath": require_intended_write_relative(
                        self.intended_write_relative
                    ),
                },
                label="startTurn",
            )
        )
        if not isinstance(turn, Mapping):
            raise ValidationError("runtime turn is missing")
        if turn.get("requestId") != self.request_id:
            _raise_identity(
                "identity_mismatch",
                "returned turn request does not match the host request",
            )
        lifecycle = turn.get("process_lifecycle")
        if isinstance(lifecycle, Mapping):
            self._ingest_process_lifecycle(lifecycle)
        else:
            self._snapshot_process_lifecycle(handle)
        self.discarded_events = drain_runtime_turn_events(turn.get("events"))
        result = turn.get("result")
        self.terminal_receipt = bound_terminal_receipt(
            result,
            discarded=self.discarded_events,
            timeout_ms=self.prompt_timeout_ms,
        )
        host_permission = turn.get("permission")
        if host_permission is not None:
            self.permission_outcome = require_host_permission_outcome(host_permission)
        self.receipt_durability = self._persist_turn_receipt()
        after = self.runtime.get_status(
            reject_runtime_conversation_params({"handle": dict(handle)}, label="getStatus")
        )
        if isinstance(after, Mapping) and "lastRequestId" in after:
            if after.get("lastRequestId") != self.request_id:
                _raise_identity(
                    "identity_mismatch",
                    "status lastRequestId does not match the completed turn request",
                )
        terminal_state = "completed" if result.get("status") == "completed" else "failed"
        if self.require_halt:
            terminal_state = "halted"
        return observation_from_runtime_turn(
            host_session=self.session,
            host_conversation_id=self.conversation_id,
            requested_model=self.requested_model,
            observed_model=mapped["current_model"],
            advertised_models=mapped["advertised_models"],
            terminal_state=terminal_state,
            result_id=self.request_id,
            question=self.question_outcome,
            auth=self.auth,
            terminal_receipt=self.terminal_receipt,
        )

    def _apply_finish_policy(self, handle: Mapping[str, Any]) -> None:
        if self.require_halt or self.session_mode == SESSION_MODE_ONESHOT:
            self._owned_close(handle, discard_persistent_state=True)
            return
        if self.finish_policy == FINISH_POLICY_DISCARD:
            self._owned_close(handle, discard_persistent_state=True)
            return
        if self.finish_policy == FINISH_POLICY_LOCAL_RELEASE:
            self._owned_close(
                handle,
                discard_persistent_state=False,
                reason="antigravity-acp-local-release",
            )
            return
        self.persistent_state = "retained"

    def _persist_turn_receipt(self) -> Dict[str, Any]:
        if self.terminal_receipt is None:
            self.receipt_durability = bound_receipt_durability(written=False)
            return self.receipt_durability
        try:
            from antigravity_acpx import persist_turn_receipt

            extras = {
                **self.terminal_receipt,
                "process_lifecycle": self.process_lifecycle,
            }
            if self.permission_outcome is not None:
                extras["permission"] = self.permission_outcome
            event = persist_turn_receipt(
                self.isolated_root,
                session=self.session,
                conversation_id=self.conversation_id,
                request_id=self.request_id,
                extras=extras,
            )
        except Exception:
            self.receipt_durability = bound_receipt_durability(written=False)
            return self.receipt_durability
        written = (
            isinstance(event, Mapping)
            and event.get("event") == "runtime_turn_observed"
        )
        self.receipt_durability = bound_receipt_durability(written=written)
        return self.receipt_durability

    def _derive(self) -> Dict[str, Any]:
        self._validate_ownership()
        if self.permission is not None:
            self.permission_outcome = require_unsupported_permission_outcome(self.permission)
        if self.question is not None:
            self.question_outcome = require_unsupported_question_outcome(self.question)
        require_runtime_task_text(self._text)
        handle: Optional[Dict[str, str]] = None
        observation: Optional[Dict[str, Any]] = None
        try:
            handle = self._ensure_owned_handle()
            observation = self._run_turn(handle)
            self._observation = validate_candidate_observation(observation)
            self._apply_finish_policy(handle)
            return observation
        except BaseException as exc:
            if observation is not None:
                self._observation = validate_candidate_observation(observation)
            if handle is not None and handle.get("sessionKey") == self.session:
                try:
                    self._owned_close(handle, primary=exc)
                except Exception:
                    raise exc
            elif handle is not None:
                self._fence_cleanup()
            raise

    def next_turn(
        self,
        *,
        text: Any,
        request_id: str,
        expected_workspace: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Bind a fresh request to the same owned handle. Never replay a cached turn."""

        self._validate_ownership()
        if expected_workspace is not None:
            if os.path.realpath(str(expected_workspace["path"])) != os.path.realpath(
                self.workspace["path"]
            ):
                _raise_identity(
                    "workspace_identity_mismatch",
                    "runtime cwd does not match the bound checkout",
                )
        if self.handle is None:
            raise ValidationError("owned runtime session is missing")
        self.bind_task_text(text)
        self.request_id = validate_identifier(request_id, "antigravity-acp request")
        self.require_halt = False
        observation = self._run_turn(self.handle)
        self._observation = validate_candidate_observation(observation)
        return self._observation

    def finish(self, *, discard_persistent_state: bool = True) -> Dict[str, str]:
        """Final close of the owned handle. Distinct from local release and retain."""

        if self.handle is None:
            raise ValidationError("owned runtime session is missing")
        if self.final_discard:
            raise ValidationError("owned runtime session already discarded")
        handle = dict(self.handle)
        self._owned_close(
            handle,
            discard_persistent_state=discard_persistent_state,
            reason=(
                "antigravity-acp-final-discard"
                if discard_persistent_state
                else "antigravity-acp-local-release"
            ),
        )
        closed: Dict[str, Any] = {
            "local_release": self.local_release,
            "persistent_state": self.persistent_state,
            "final_discard": self.final_discard,
            "backend_discard": self.backend_discard,
            "worker_termination": self.worker_termination,
            "cleanup_uncertain": self.cleanup_uncertain,
            "replacement_blocked": self.replacement_blocked,
            "process_lifecycle": dict(self.process_lifecycle),
        }
        if self.owned_worker is not None:
            closed["worker"] = dict(self.owned_worker)
        if self.cleanup_receipt is not None:
            closed["cleanup"] = dict(self.cleanup_receipt)
        if self.selected_model is not None:
            closed["selected_model"] = self.selected_model
        if self.current_model is not None:
            closed["current_model"] = self.current_model
        return closed


class AntigravityAcpRunnerFixture:
    """Deterministic Antigravity ACP observation runner. Never starts a live process."""

    def __init__(
        self,
        observation: Optional[Mapping[str, Any]] = None,
        *,
        catalog: Optional[Mapping[str, Any]] = None,
    ):
        self._observation = (
            dict(observation) if observation is not None else fixture_observation()
        )
        self._catalog = dict(catalog) if catalog is not None else None

    @staticmethod
    def available() -> bool:
        return False

    def observation(self) -> Dict[str, Any]:
        return validate_candidate_observation(self._observation)

    def catalog(self) -> Optional[Dict[str, Any]]:
        return None if self._catalog is None else dict(self._catalog)


class AntigravityAcpController:
    """Structured Antigravity ACP transport. Never constructs tmux or agy-print."""

    transport_id: str = TRANSPORT_ID
    target: str = TARGET

    def __init__(
        self,
        registry_root: Path,
        *,
        observer: Optional[Mapping[str, Any]] = None,
        _observer: Optional[Mapping[str, Any]] = None,
        runner: Any = None,
        _runner: Any = None,
        catalog: Optional[Mapping[str, Any]] = None,
    ):
        self.registry_root = Path(registry_root)
        self.observer = observer if observer is not None else _observer
        self.runner = runner if runner is not None else _runner
        self.catalog = catalog

    @staticmethod
    def available() -> bool:
        return False

    def require_observation(self) -> Dict[str, Any]:
        if self.runner is not None:
            if self.runner.available():
                _raise_unsupported(
                    "transport_unavailable",
                    "antigravity-acp runner fixture must stay fail-closed",
                )
            return self.runner.observation()
        if self.observer is None:
            _raise_unavailable("antigravity-acp structured observation is unavailable")
        return validate_candidate_observation(self.observer)

    def require_catalog(
        self, catalog: Optional[Mapping[str, Any]] = None
    ) -> Dict[str, Any]:
        if catalog is not None:
            return validate_antigravity_acp_catalog(catalog)
        if self.runner is not None:
            observed = self.runner.catalog()
            if observed is not None:
                return validate_antigravity_acp_catalog(observed)
        if self.catalog is not None:
            return validate_antigravity_acp_catalog(self.catalog)
        return verified_antigravity_acp_catalog()

    def prove(
        self,
        *,
        expected_session: Optional[str] = None,
        expected_conversation_id: Optional[str] = None,
        expected_workspace: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        observation = self.require_observation()
        return prove_antigravity_acp_observation(
            observation,
            expected_session=expected_session or observation["session"]["session_id"],
            expected_conversation_id=(
                expected_conversation_id or observation["session"]["conversation_id"]
            ),
            expected_workspace=expected_workspace,
        )

    def caller_result(
        self,
        *,
        expected_session: Optional[str] = None,
        expected_conversation_id: Optional[str] = None,
        expected_workspace: Optional[Mapping[str, Any]] = None,
        requested_model: Optional[str] = None,
        expected_observed_model: Optional[str] = None,
        record_state: Optional[str] = None,
        halt_confirmed: Optional[bool] = None,
        catalog: Optional[Mapping[str, Any]] = None,
        require_halt: bool = False,
    ) -> Dict[str, Any]:
        observation = self.require_observation()
        expected_session = expected_session or observation["session"]["session_id"]
        expected_conversation_id = (
            expected_conversation_id or observation["session"]["conversation_id"]
        )
        proved = self.prove(
            expected_session=expected_session,
            expected_conversation_id=expected_conversation_id,
            expected_workspace=expected_workspace,
        )
        if requested_model is not None and proved["model"]["requested_id"] != requested_model:
            _raise_identity(
                "model_observation_mismatch",
                "observed model does not match the bound Antigravity ACP runtime",
            )
        if (
            expected_observed_model is not None
            and proved["model"]["observed_id"] != expected_observed_model
        ):
            _raise_identity(
                "model_observation_mismatch",
                "observed model does not match the bound Antigravity ACP runtime",
            )
        if require_halt and proved["terminal"]["state"] != "halted":
            _raise_identity("identity_mismatch", "antigravity-acp halt was not observed")
        halted = proved["terminal"]["state"] == "halted"
        fields = caller_fields_from_observation(
            proved,
            record_state="HALTED" if halted else record_state,
            halt_confirmed=True if halt_confirmed is None and halted else halt_confirmed,
        )
        durability = (
            _receipt_durability_from_runner(self.runner)
            if self.runner is not None
            else bound_receipt_durability(written=False)
        )
        return {
            "ok": True,
            "session": expected_session,
            "state": (
                "HALTED"
                if fields["caller_outcome"]["halt"] == "confirmed"
                else (record_state or "ACTIVE")
            ),
            "live_antigravity_acp_claimed": False,
            "antigravity_acp": proved,
            **fields,
            **durability,
        }


__all__ = [
    "ACPX_LAST_INSPECTED_SOURCE_COMMIT",
    "ACPX_LAST_INSPECTED_SOURCE_RELEASE",
    "ACPX_RELEASE",
    "ACPX_SOURCE_COMMIT",
    "ADAPTER_ID",
    "ADVERTISED_ANTIGRAVITY_MODELS",
    "AntigravityAcpController",
    "AntigravityAcpNodeRuntime",
    "AntigravityAcpRunnerFixture",
    "AntigravityAcpRuntimeRunner",
    "AntigravityAcpSyntheticRuntime",
    "CANDIDATE_PROMPT_TIMEOUT_MS",
    "CANDIDATE_SCHEMA",
    "CONTROLLER_RUNTIME_DRIVER",
    "DEFAULT_ANTIGRAVITY_MODEL",
    "DEFAULT_ROUTE",
    "FALLBACK_OR_DEFAULT_MODEL_IDS",
    "GENERIC_ACP_ID",
    "HOST_PERMISSION_DECISION_LIMIT",
    "HOST_PERMISSION_SCHEMA",
    "MODEL_CATALOG_SCHEMA",
    "OBSERVATION_SCHEMA",
    "OWNERSHIP_SCHEMA",
    "RECEIPT_DURABILITY_DURABLE",
    "RECEIPT_DURABILITY_NONDURABLE",
    "REGISTRY_REVISION",
    "RUNTIME_ID",
    "RUNTIME_VERSION",
    "STARTUP_TIMEOUT_MS",
    "TARGET",
    "TRANSPORT_ID",
    "bound_receipt_durability",
    "bound_terminal_receipt",
    "caller_fields_from_observation",
    "candidate_contract",
    "fixture_observation",
    "require_bounded_timeout_ms",
    "map_runtime_antigravity_models",
    "observation_from_runtime_turn",
    "prove_antigravity_acp_observation",
    "require_antigravity_acp_target",
    "require_host_permission_outcome",
    "require_intended_write_relative",
    "session_record_from_observation",
    "validate_antigravity_acp_catalog",
    "validate_auth_observation",
    "validate_candidate_contract",
    "validate_candidate_observation",
    "validate_model_observation",
    "validate_question_observation",
    "verified_antigravity_acp_catalog",
    "build_antigravity_acp_candidate_runner",
    "require_antigravity_acp_route_binding",
    "require_antigravity_process_env",
    "resolve_antigravity_acp_route_binding",
    "select_and_map_runtime_antigravity_models",
    "test_only_antigravity_synthetic_route_binding",
]


def claim_antigravity_acp_isolated_root(
    isolated_root: Path,
    *,
    owner: str,
    session: str,
    conversation_id: str,
) -> Dict[str, Any]:
    from antigravity_acpx import claim_isolated_root

    root = Path(isolated_root)
    root.mkdir(parents=True, exist_ok=True)
    os.chmod(root, 0o700)
    return claim_isolated_root(
        root,
        owner=owner,
        session=session,
        conversation_id=conversation_id,
    )


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def build_antigravity_acp_candidate_runner(
    *,
    session: str,
    contract: Any,
    state_root: Path,
    prompt: Any,
    requested_model: Optional[str],
    expected_workspace: Mapping[str, Any],
    catalog: Optional[Mapping[str, Any]] = None,
    runtime: Any = None,
    synthetic_peer: bool = False,
    synthetic_peer_script: Optional[str] = None,
    synthetic_peer_survive: bool = False,
    executable: Optional[Path] = None,
    route_binding: Optional[Mapping[str, Any]] = None,
    isolated_root: Optional[Path] = None,
    conversation_id: Optional[str] = None,
    request_id: Optional[str] = None,
    session_mode: str = SESSION_MODE_PERSISTENT,
    finish_policy: str = FINISH_POLICY_RETAIN,
    halt: bool = False,
    repo_root: Optional[Path] = None,
    env: Optional[Mapping[str, str]] = None,
) -> AntigravityAcpRuntimeRunner:
    """Construct the task-owned AGY candidate runner. Synthetic peer is test-only."""

    text = require_runtime_task_text(prompt)
    owner = validate_identifier(contract.controller, "controller")
    intended_write_relative = require_intended_write_relative(
        getattr(contract, "intended_write_relative", None)
    )
    host_conversation = conversation_id or ("conv-%s" % session)
    host_request = request_id or ("%s-turn-1" % session)
    isolated = (
        Path(isolated_root)
        if isolated_root is not None
        else Path(state_root) / session / "acp-isolated"
    )
    claim_antigravity_acp_isolated_root(
        isolated,
        owner=owner,
        session=session,
        conversation_id=host_conversation,
    )
    if runtime is None:
        if (executable is not None or env is not None) and route_binding is None and not synthetic_peer:
            raise ValidationError(
                "antigravity-acp does not accept an arbitrary executable or env payload as a trusted route binding"
            )
        if synthetic_peer and route_binding is None:
            route_binding = test_only_antigravity_synthetic_route_binding()
        binding = require_antigravity_acp_route_binding(route_binding)
        if binding["kind"] == SYNTHETIC_PEER_KIND:
            runtime = AntigravityAcpNodeRuntime(
                workspace=Path(expected_workspace["path"]),
                isolated_root=isolated,
                repo_root=repo_root or _repo_root(),
                synthetic_peer=True,
                synthetic_peer_script=synthetic_peer_script,
                synthetic_peer_survive=synthetic_peer_survive,
            )
        else:
            runtime = AntigravityAcpNodeRuntime(
                workspace=Path(expected_workspace["path"]),
                isolated_root=isolated,
                repo_root=repo_root or _repo_root(),
                env=binding["process_env"],
                synthetic_peer=False,
                executable=Path(binding["executable"]),
                candidate_args=list(binding["argv"][1:]),
            )
    return AntigravityAcpRuntimeRunner(
        runtime,
        isolated_root=isolated,
        owner=owner,
        session=session,
        conversation_id=host_conversation,
        request_id=host_request,
        workspace=expected_workspace,
        requested_model=requested_model or contract.requested_model,
        text=text,
        catalog=catalog,
        halt=halt,
        session_mode=session_mode,
        finish_policy=finish_policy,
        intended_write_relative=intended_write_relative,
    )
