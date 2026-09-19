"""Grok-specific builder admission after qualification and authority gates.

This is not a transport. It does not implement Cursor ACP, generic ACP,
Herdr, or a Grok ACP adapter. Grok remains on its existing tmux path; live
Grok launch stays closed. Model, workspace, session, result, and receipt
claims come from observed fixture metadata plus a current qualification
receipt projection, not from a requested selector or path alone.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from .caller import caller_projection, make_blocker
from .errors import IdentityError, UnsupportedError, ValidationError
from .grok_launch import (
    GROK_EXECUTABLE_SHA256,
    GROK_LAUNCH_AUTHORITY_BLOCKER,
    GROK_LAUNCH_AUTHORITY_BLOCKERS,
    GROK_RUNTIME_BASENAME,
    require_live_grok_launch,
)
from .grok_qualification import TERMINAL_QUALIFICATION_SCHEMA
from .instruction_planes import GROK_BUILD_VERSION
from .safety import (
    canonical_json_bytes,
    sha256_bytes,
    validate_branch,
    validate_identifier,
    validate_sha1,
    validate_sha256,
)
from .transport import DEFAULT_TRANSPORT


TARGET = "grok"
BOUND_TRANSPORT = DEFAULT_TRANSPORT
GENERIC_ACP_ID_NAME = "acp"
OBSERVATION_SCHEMA = "puppet.grok-builder-observation/v1"
RECEIPT_SCHEMA = "puppet.grok-builder-receipt/v1"
ADMISSION_SCHEMA = "puppet.grok-builder-admission/v1"
LIFECYCLE_SCHEMA = "puppet.grok-builder-lifecycle/v1"
LIFECYCLE_PHASES = (
    "start_bound",
    "session_matched",
    "terminal_result",
    "worker_completion",
    "controller_acceptance",
    "confirmed_halt",
    "final_outcome",
)

RUNTIME_MODEL_SOURCES = frozenset(
    {"runtime_metadata", "session_metadata", "grok_runtime_metadata"}
)
TERMINAL_STATES = frozenset({"active", "completed", "failed", "halted"})
FORBIDDEN_TRANSPORTS = frozenset({"herdr", "acp", "agy-print", "cursor-acp"})
_OBSERVATION_KEYS = frozenset(
    {
        "schema",
        "target",
        "transport",
        "requested_model",
        "observed_model",
        "workspace",
        "session",
        "terminal_result",
        "runtime",
        "halt",
        "qualification_receipt",
        "last_checkpoint",
        "last_beacon",
        "last_validated_at",
        "record_state",
    }
)
_OBSERVED_MODEL_KEYS = frozenset({"id", "source"})
_WORKSPACE_KEYS = frozenset({"path", "branch", "head", "tree"})
_SESSION_KEYS = frozenset({"id", "grok_session_id"})
_TERMINAL_KEYS = frozenset({"state", "exit_code", "result_id"})
_RUNTIME_KEYS = frozenset(
    {"model_id", "executable_sha256", "version", "basename"}
)
_HALT_KEYS = frozenset({"session", "grok_session_id", "halted"})
_RECEIPT_KEYS = frozenset(
    {
        "schema",
        "qualification_schema",
        "kind",
        "target",
        "session_profile",
        "qualification_authorized",
        "public_launch_authorized",
        "executable_fingerprint",
        "execution_fingerprint",
        "version_fingerprint",
        "platform_fingerprint",
        "adapter_fingerprint",
        "protocol_fingerprint",
        "fingerprint",
    }
)
_RECEIPT_HASH_FIELDS = (
    "qualification_schema",
    "kind",
    "target",
    "session_profile",
    "qualification_authorized",
    "public_launch_authorized",
    "executable_fingerprint",
    "execution_fingerprint",
    "version_fingerprint",
    "platform_fingerprint",
    "adapter_fingerprint",
    "protocol_fingerprint",
)


def _blocker(code: str, detail: str, *, remedy: Optional[str] = None, **identity: Any) -> Dict[str, Any]:
    return make_blocker(code=code, detail=detail, remedy=remedy, **identity)


def _raise_identity(code: str, detail: str, *, remedy: Optional[str] = None, **identity: Any) -> None:
    raise IdentityError(detail, blocker=_blocker(code, detail, remedy=remedy, **identity))


def _raise_unsupported(code: str, detail: str, *, remedy: Optional[str] = None) -> None:
    raise UnsupportedError(detail, blocker=_blocker(code, detail, remedy=remedy))


def require_grok_builder_target(target: Any) -> str:
    """Grok builder admission is valid only for the grok target."""

    if target != TARGET:
        _raise_unsupported(
            "grok_builder_target_mismatch",
            "Grok builder admission is valid only for the grok target",
            remedy=(
                "bind target=grok after its qualification and authority gates; "
                "do not admit cursor, agy, claude, or codex through this contract"
            ),
        )
    return TARGET


def _bounded_text(value: Any, *, label: str, maximum: int = 400) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError("%s is invalid" % label)
    cleaned = value.replace("\x00", "").replace("\r", " ").replace("\n", " ").strip()
    if len(cleaned) > maximum:
        raise ValidationError("%s is oversized" % label)
    return cleaned


def _optional_int(value: Any, *, label: str, minimum: int = 0) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValidationError("%s is invalid" % label)
    return value


def _session_uuid(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise ValidationError("%s is not a UUIDv4" % label)
    try:
        parsed = uuid.UUID(value)
    except (AttributeError, ValueError) as exc:
        raise ValidationError("%s is not a UUIDv4" % label) from exc
    if parsed.version != 4 or str(parsed) != value:
        raise ValidationError("%s is not a canonical UUIDv4" % label)
    return value


def grok_builder_receipt_fingerprint(value: Mapping[str, Any]) -> str:
    """Hash the current Grok qualification projection without the fingerprint."""

    body = {name: value[name] for name in _RECEIPT_HASH_FIELDS}
    return sha256_bytes(canonical_json_bytes(body))


def validate_grok_builder_receipt(value: Any) -> Dict[str, Any]:
    """Return one body-safe current Grok qualification receipt projection."""

    if not isinstance(value, Mapping) or set(value) != _RECEIPT_KEYS:
        raise ValidationError("Grok builder receipt fields do not match schema")
    if value.get("schema") != RECEIPT_SCHEMA:
        raise ValidationError("Grok builder receipt schema is invalid")
    if value.get("qualification_schema") != TERMINAL_QUALIFICATION_SCHEMA:
        _raise_identity(
            "qualification_receipt_invalid",
            "Grok builder admission requires the regular paired qualification schema",
        )
    if (
        value.get("kind") != "grok_regular_paired_runtime_qualification"
        or value.get("session_profile") != "regular"
    ):
        _raise_identity(
            "qualification_receipt_invalid",
            "Grok builder admission requires the regular paired qualification kind",
        )
    require_grok_builder_target(value.get("target"))
    if value.get("qualification_authorized") is not True:
        _raise_identity(
            "qualification_receipt_invalid",
            "Grok qualification receipt is not authorized",
        )
    if value.get("public_launch_authorized") is not True:
        _raise_identity(
            "qualification_receipt_invalid",
            "Grok qualification receipt has not closed its authority gates",
        )
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "qualification_schema": TERMINAL_QUALIFICATION_SCHEMA,
        "kind": "grok_regular_paired_runtime_qualification",
        "target": TARGET,
        "session_profile": "regular",
        "qualification_authorized": True,
        "public_launch_authorized": True,
        "executable_fingerprint": validate_sha256(
            value.get("executable_fingerprint"), "Grok executable fingerprint"
        ),
        "execution_fingerprint": validate_sha256(
            value.get("execution_fingerprint"), "Grok execution fingerprint"
        ),
        "version_fingerprint": validate_sha256(
            value.get("version_fingerprint"), "Grok version fingerprint"
        ),
        "platform_fingerprint": validate_sha256(
            value.get("platform_fingerprint"), "Grok platform fingerprint"
        ),
        "adapter_fingerprint": validate_sha256(
            value.get("adapter_fingerprint"), "Grok adapter fingerprint"
        ),
        "protocol_fingerprint": validate_sha256(
            value.get("protocol_fingerprint"), "Grok protocol fingerprint"
        ),
        "fingerprint": validate_sha256(
            value.get("fingerprint"), "Grok builder receipt fingerprint"
        ),
    }
    expected = grok_builder_receipt_fingerprint(receipt)
    if receipt["fingerprint"] != expected:
        _raise_identity(
            "qualification_receipt_invalid",
            "Grok qualification receipt fingerprint is stale",
        )
    return receipt


def validate_grok_builder_observation(value: Any) -> Dict[str, Any]:
    """Return one body-safe structured Grok builder observation."""

    if not isinstance(value, Mapping) or set(value) != _OBSERVATION_KEYS:
        raise ValidationError("Grok builder observation fields do not match schema")
    if value.get("schema") != OBSERVATION_SCHEMA:
        raise ValidationError("Grok builder observation schema is invalid")
    require_grok_builder_target(value.get("target"))
    transport = value.get("transport")
    if transport == GENERIC_ACP_ID_NAME:
        _raise_identity(
            "identity_mismatch",
            "generic acp is not a Grok builder transport",
            remedy=(
                "keep generic acp unsupported; Grok builder admission stays on "
                "tmux after qualification and never opens acp"
            ),
        )
    if transport in FORBIDDEN_TRANSPORTS:
        _raise_unsupported(
            "transport_unsupported",
            "Grok builder admission does not bind transport %s" % transport,
            remedy=(
                "keep Grok on tmux after qualification; herdr, generic acp, "
                "agy-print, and cursor-acp are not Grok builder transports"
            ),
        )
    if transport != BOUND_TRANSPORT:
        _raise_identity(
            "identity_mismatch",
            "Grok builder observation is bound to a different transport",
        )
    requested = value.get("requested_model")
    if requested is not None:
        requested = _bounded_text(requested, label="requested model", maximum=200)
    observed_model = value.get("observed_model")
    if observed_model is not None:
        if (
            not isinstance(observed_model, Mapping)
            or set(observed_model) != _OBSERVED_MODEL_KEYS
        ):
            raise ValidationError("Grok observed model fields are invalid")
        observed_model = {
            "id": _bounded_text(
                observed_model.get("id"), label="observed model", maximum=200
            ),
            "source": _bounded_text(
                observed_model.get("source"),
                label="observed model source",
                maximum=80,
            ),
        }
    workspace = value.get("workspace")
    if not isinstance(workspace, Mapping) or set(workspace) != _WORKSPACE_KEYS:
        raise ValidationError("Grok workspace fields are invalid")
    workspace = {
        "path": _bounded_text(workspace.get("path"), label="workspace path", maximum=1024),
        "branch": validate_branch(workspace.get("branch")),
        "head": validate_sha1(workspace.get("head"), "workspace head"),
        "tree": validate_sha1(workspace.get("tree"), "workspace tree"),
    }
    session = value.get("session")
    if not isinstance(session, Mapping) or set(session) != _SESSION_KEYS:
        raise ValidationError("Grok session fields are invalid")
    session = {
        "id": validate_identifier(session.get("id"), "Grok session"),
        "grok_session_id": _session_uuid(
            session.get("grok_session_id"), "Grok session id"
        ),
    }
    terminal = value.get("terminal_result")
    if not isinstance(terminal, Mapping) or set(terminal) != _TERMINAL_KEYS:
        raise ValidationError("Grok terminal result fields are invalid")
    state = terminal.get("state")
    if state not in TERMINAL_STATES:
        raise ValidationError("Grok terminal result state is invalid")
    result_id = terminal.get("result_id")
    if result_id is not None:
        result_id = validate_identifier(result_id, "Grok result")
    terminal = {
        "state": state,
        "exit_code": _optional_int(terminal.get("exit_code"), label="terminal exit code"),
        "result_id": result_id,
    }
    runtime = value.get("runtime")
    if not isinstance(runtime, Mapping) or set(runtime) != _RUNTIME_KEYS:
        raise ValidationError("Grok runtime fields are invalid")
    runtime = {
        "model_id": _bounded_text(runtime.get("model_id"), label="runtime model", maximum=200),
        "executable_sha256": validate_sha256(
            runtime.get("executable_sha256"), "Grok runtime executable"
        ),
        "version": _bounded_text(runtime.get("version"), label="Grok runtime version", maximum=32),
        "basename": _bounded_text(
            runtime.get("basename"), label="Grok runtime basename", maximum=80
        ),
    }
    halt = value.get("halt")
    if halt is not None:
        if not isinstance(halt, Mapping) or set(halt) != _HALT_KEYS:
            raise ValidationError("Grok halt fields are invalid")
        if halt.get("halted") is not True:
            raise ValidationError("Grok halt state is invalid")
        halt = {
            "session": validate_identifier(halt.get("session"), "Grok halt session"),
            "grok_session_id": _session_uuid(
                halt.get("grok_session_id"), "Grok halt session id"
            ),
            "halted": True,
        }
    checkpoint = value.get("last_checkpoint")
    if checkpoint is not None:
        if not isinstance(checkpoint, Mapping) or "checkpoint_id" not in checkpoint:
            raise ValidationError("Grok checkpoint is invalid")
        checkpoint = {
            "checkpoint_id": _bounded_text(
                checkpoint.get("checkpoint_id"),
                label="checkpoint id",
                maximum=64,
            )
        }
    beacon = value.get("last_beacon")
    if beacon is not None:
        if not isinstance(beacon, Mapping):
            raise ValidationError("Grok beacon is invalid")
        sequence = beacon.get("sequence")
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 0:
            raise ValidationError("Grok beacon sequence is invalid")
        beacon = {"sequence": sequence}
    validated_at = value.get("last_validated_at")
    if validated_at is not None:
        validated_at = _bounded_text(
            validated_at, label="last validated at", maximum=64
        )
    record_state = value.get("record_state")
    if record_state is not None:
        record_state = _bounded_text(record_state, label="record state", maximum=32)
    return {
        "schema": OBSERVATION_SCHEMA,
        "target": TARGET,
        "transport": BOUND_TRANSPORT,
        "requested_model": requested,
        "observed_model": observed_model,
        "workspace": workspace,
        "session": session,
        "terminal_result": terminal,
        "runtime": runtime,
        "halt": halt,
        "qualification_receipt": validate_grok_builder_receipt(
            value.get("qualification_receipt")
        ),
        "last_checkpoint": checkpoint,
        "last_beacon": beacon,
        "last_validated_at": validated_at,
        "record_state": record_state,
    }


def prove_qualification_receipt(
    observation: Mapping[str, Any],
    *,
    expected_receipt: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Prove the current Grok qualification receipt. Stale or foreign fails."""

    observation = validate_grok_builder_observation(observation)
    receipt = observation["qualification_receipt"]
    if expected_receipt is not None:
        expected = validate_grok_builder_receipt(expected_receipt)
        if receipt != expected:
            _raise_identity(
                "qualification_receipt_invalid",
                "Grok qualification receipt is stale",
            )
    return dict(receipt)


def prove_observed_model(
    observation: Mapping[str, Any],
    *,
    requested_model: Optional[str] = None,
    expected_observed_model: Optional[str] = None,
) -> Dict[str, Any]:
    """Prove the executed Grok model from runtime metadata, not the selector."""

    observation = validate_grok_builder_observation(observation)
    observed = observation.get("observed_model")
    requested = requested_model or observation.get("requested_model")
    if observed is None or observed.get("source") not in RUNTIME_MODEL_SOURCES:
        _raise_identity(
            "model_observation_selector_only",
            "requested selector is not observed model proof",
        )
    model_id = observed["id"]
    runtime = observation["runtime"]
    if model_id != runtime["model_id"]:
        _raise_identity(
            "model_observation_selector_only",
            "observed model is missing from Grok runtime metadata",
        )
    if requested is not None and model_id == requested:
        _raise_identity(
            "model_observation_selector_only",
            "requested selector is not observed model proof",
        )
    if expected_observed_model is not None and expected_observed_model != model_id:
        _raise_identity(
            "model_observation_mismatch",
            "observed model does not match the bound Grok runtime",
        )
    if (
        runtime["executable_sha256"] != GROK_EXECUTABLE_SHA256
        or runtime["version"] != GROK_BUILD_VERSION
        or runtime["basename"] != GROK_RUNTIME_BASENAME
    ):
        _raise_identity(
            "model_observation_mismatch",
            "observed Grok runtime identity does not match Build 0.2.112",
        )
    return {
        "observed_model": model_id,
        "source": observed["source"],
        "requested_model": requested,
        "executable_sha256": runtime["executable_sha256"],
        "version": runtime["version"],
        "basename": runtime["basename"],
    }


def prove_workspace_binding(
    observation: Mapping[str, Any],
    *,
    expected_workspace: Mapping[str, Any],
) -> Dict[str, Any]:
    """Prove the exact bound workspace. A path alone is not enough."""

    observation = validate_grok_builder_observation(observation)
    workspace = observation["workspace"]
    expected_path = expected_workspace.get("path")
    expected_branch = expected_workspace.get("branch")
    expected_head = expected_workspace.get("head")
    expected_tree = expected_workspace.get("tree")
    if (
        not isinstance(expected_path, str)
        or not isinstance(expected_branch, str)
        or not isinstance(expected_head, str)
        or not isinstance(expected_tree, str)
    ):
        raise ValidationError("expected workspace identity is incomplete")
    if (
        workspace["path"] != expected_path
        or workspace["branch"] != expected_branch
        or workspace["head"] != expected_head
        or workspace["tree"] != expected_tree
    ):
        _raise_identity(
            "workspace_identity_mismatch",
            "Grok workspace identity does not match the bound checkout",
        )
    return dict(workspace)


def prove_terminal_result(
    observation: Mapping[str, Any],
    *,
    expected_state: Optional[str] = None,
    expected_result_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Prove the worker terminal/result state from structured observation."""

    observation = validate_grok_builder_observation(observation)
    terminal = observation["terminal_result"]
    if expected_state is not None and terminal["state"] != expected_state:
        _raise_identity(
            "result_identity_mismatch",
            "Grok terminal result state does not match the bound result",
        )
    if expected_result_id is not None and terminal["result_id"] != expected_result_id:
        _raise_identity(
            "result_identity_mismatch",
            "Grok terminal result identity does not match the bound result",
        )
    return dict(terminal)


def prove_session_identity(
    observation: Mapping[str, Any],
    *,
    expected_session: str,
    expected_grok_session_id: str,
) -> Dict[str, Any]:
    """Prove matching controller session and Grok UUIDv4 identity."""

    observation = validate_grok_builder_observation(observation)
    session = observation["session"]
    if (
        not expected_session
        or not expected_grok_session_id
        or session["id"] != expected_session
        or session["grok_session_id"] != expected_grok_session_id
    ):
        _raise_identity(
            "session_identity_mismatch",
            "Grok admission requires matching session and Grok session identity",
        )
    return {
        "session": session["id"],
        "grok_session_id": session["grok_session_id"],
        "session_proved": True,
    }


def prove_shutdown(
    observation: Mapping[str, Any],
    *,
    expected_session: str,
    expected_grok_session_id: str,
) -> Dict[str, Any]:
    """Prove exact Grok session halt. Do not accept a foreign session."""

    matched = prove_session_identity(
        observation,
        expected_session=expected_session,
        expected_grok_session_id=expected_grok_session_id,
    )
    observation = validate_grok_builder_observation(observation)
    halt = observation.get("halt")
    if not isinstance(halt, Mapping):
        _raise_identity(
            "session_identity_mismatch",
            "Grok halt proof is missing the owned Grok session identity",
        )
    if (
        halt["session"] != matched["session"]
        or halt["grok_session_id"] != matched["grok_session_id"]
        or halt["halted"] is not True
    ):
        _raise_identity(
            "session_identity_mismatch",
            "Grok halt is not confined to the owned Grok session",
        )
    return {
        "session": halt["session"],
        "grok_session_id": halt["grok_session_id"],
        "halted": True,
    }


def prove_grok_builder_admission(
    observation: Mapping[str, Any],
    *,
    expected_session: str,
    expected_grok_session_id: str,
    expected_workspace: Mapping[str, Any],
    expected_receipt: Optional[Mapping[str, Any]] = None,
    requested_model: Optional[str] = None,
    expected_observed_model: Optional[str] = None,
    expected_result_state: Optional[str] = None,
    expected_result_id: Optional[str] = None,
    require_halt: bool = False,
) -> Dict[str, Any]:
    """Admit Grok as a builder from one current observation and receipt."""

    observation = validate_grok_builder_observation(observation)
    receipt = prove_qualification_receipt(
        observation, expected_receipt=expected_receipt
    )
    model = prove_observed_model(
        observation,
        requested_model=requested_model,
        expected_observed_model=expected_observed_model,
    )
    workspace = prove_workspace_binding(
        observation, expected_workspace=expected_workspace
    )
    terminal = prove_terminal_result(
        observation,
        expected_state=expected_result_state,
        expected_result_id=expected_result_id,
    )
    session = prove_session_identity(
        observation,
        expected_session=expected_session,
        expected_grok_session_id=expected_grok_session_id,
    )
    halt = None
    if require_halt or observation.get("halt") is not None:
        halt = prove_shutdown(
            observation,
            expected_session=expected_session,
            expected_grok_session_id=expected_grok_session_id,
        )
    return {
        "schema": ADMISSION_SCHEMA,
        "target": TARGET,
        "transport": BOUND_TRANSPORT,
        "builder_admitted": True,
        "model": model,
        "workspace": workspace,
        "terminal_result": terminal,
        "session": session,
        "halt": halt,
        "qualification_receipt": receipt,
        "authority_blockers": list(GROK_LAUNCH_AUTHORITY_BLOCKERS),
        "launch_authorized": False,
        "live_grok_claimed": False,
    }


def session_record_from_observation(
    observation: Mapping[str, Any],
    *,
    record_state: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a caller-projection record. Does not persist a tmux session."""

    observation = validate_grok_builder_observation(observation)
    state = record_state or observation.get("record_state") or "ACTIVE"
    if observation["terminal_result"]["state"] == "halted" and state == "ACTIVE":
        state = "HALTED"
    return {
        "session": observation["session"]["id"],
        "target": TARGET,
        "state": state,
        "process": None,
        "last_checkpoint": observation.get("last_checkpoint"),
        "last_beacon": observation.get("last_beacon"),
        "last_validated_at": observation.get("last_validated_at"),
        "transport": {"schema": "puppet.transport-binding/v1", "id": BOUND_TRANSPORT},
    }


def caller_fields_from_observation(
    observation: Mapping[str, Any],
    *,
    record_state: Optional[str] = None,
    halt_confirmed: Optional[bool] = None,
) -> Dict[str, Any]:
    """Preserve stage-2 worker/controller/halt distinctions on Grok admission."""

    record = session_record_from_observation(
        observation, record_state=record_state
    )
    if halt_confirmed is None:
        halt_confirmed = record["state"] == "HALTED"
    return caller_projection(
        record, transport_id=BOUND_TRANSPORT, halt_confirmed=halt_confirmed
    )


def qualify_grok_builder_lifecycle(
    observation: Mapping[str, Any],
    *,
    expected_session: str,
    expected_grok_session_id: str,
    expected_workspace: Mapping[str, Any],
    expected_receipt: Optional[Mapping[str, Any]] = None,
    requested_model: Optional[str] = None,
    expected_observed_model: Optional[str] = None,
    expected_result_state: Optional[str] = None,
    expected_result_id: Optional[str] = None,
    require_halt: bool = False,
    record_state: Optional[str] = None,
    halt_confirmed: Optional[bool] = None,
) -> Dict[str, Any]:
    """Qualify the deterministic Grok builder lifecycle. Never claims a live run."""

    observation = validate_grok_builder_observation(observation)
    start = {
        "model": prove_observed_model(
            observation,
            requested_model=requested_model,
            expected_observed_model=expected_observed_model,
        ),
        "workspace": prove_workspace_binding(
            observation, expected_workspace=expected_workspace
        ),
        "session": prove_session_identity(
            observation,
            expected_session=expected_session,
            expected_grok_session_id=expected_grok_session_id,
        ),
        "qualification_receipt": prove_qualification_receipt(
            observation, expected_receipt=expected_receipt
        ),
    }
    session = start["session"]
    terminal = prove_terminal_result(
        observation,
        expected_state=expected_result_state,
        expected_result_id=expected_result_id,
    )
    if halt_confirmed is None:
        halt_confirmed = observation.get("halt") is not None or require_halt
    fields = caller_fields_from_observation(
        observation,
        record_state=record_state,
        halt_confirmed=halt_confirmed
        if (require_halt or observation.get("halt"))
        else False,
    )
    worker = fields["caller_outcome"]["worker_completion"]
    acceptance = fields["caller_outcome"]["controller_acceptance"]
    halt_state = fields["caller_outcome"]["halt"]
    halt_proof = None
    if require_halt or observation.get("halt") is not None:
        halt_proof = prove_shutdown(
            observation,
            expected_session=expected_session,
            expected_grok_session_id=expected_grok_session_id,
        )
        if halt_state != "confirmed":
            _raise_identity(
                "session_identity_mismatch",
                "Grok confirmed halt is missing",
            )
    final = fields["final_outcome"]
    if halt_proof is None and acceptance == "none":
        if final is not None:
            raise ValidationError("Grok final outcome is not bounded")
    elif final is None:
        raise ValidationError("Grok final outcome is missing")
    phases = {
        "start_bound": start,
        "session_matched": session,
        "terminal_result": terminal,
        "worker_completion": worker,
        "controller_acceptance": acceptance,
        "confirmed_halt": halt_proof,
        "final_outcome": final,
    }
    if tuple(phases) != LIFECYCLE_PHASES:
        raise ValidationError("Grok builder lifecycle phases do not match schema")
    return {
        "schema": LIFECYCLE_SCHEMA,
        "target": TARGET,
        "transport": BOUND_TRANSPORT,
        "phases": phases,
        "phase_order": list(LIFECYCLE_PHASES),
        "caller_outcome": fields["caller_outcome"],
        "progress_cursor": fields["progress_cursor"],
        "live_grok_claimed": False,
    }


def require_live_grok_builder(observation: Optional[Mapping[str, Any]] = None) -> None:
    """Fail closed. Builder admission never opens a live Grok process."""

    if observation is not None:
        validate_grok_builder_observation(observation)
    raise UnsupportedError(
        GROK_LAUNCH_AUTHORITY_BLOCKER,
        blocker=_blocker("grok_launch_authority", GROK_LAUNCH_AUTHORITY_BLOCKER),
    )


class GrokBuilderAdmissionFixture:
    """Deterministic Grok builder observation. Never starts a live Grok process."""

    def __init__(self, observation: Optional[Mapping[str, Any]] = None):
        self._observation = (
            dict(observation) if observation is not None else fixture_observation()
        )

    @staticmethod
    def available() -> bool:
        return False

    def observation(self) -> Dict[str, Any]:
        return validate_grok_builder_observation(self._observation)


class GrokBuilderAdmissionController:
    """Structured Grok builder admission. Never constructs a live Grok runtime."""

    def __init__(
        self,
        registry_root: Path,
        *,
        observer: Optional[Mapping[str, Any]] = None,
        fixture: Optional[GrokBuilderAdmissionFixture] = None,
    ):
        self.registry_root = Path(registry_root)
        self.observer = observer
        self.fixture = fixture

    @staticmethod
    def available() -> bool:
        """Live Grok is not claimed. Fixtures do not make this true."""

        return False

    def require_observation(self) -> Dict[str, Any]:
        if self.fixture is not None:
            if self.fixture.available():
                _raise_unsupported(
                    "grok_builder_unavailable",
                    "Grok builder fixture must stay fail-closed",
                    remedy="keep the live Grok gate closed; do not treat a fixture as a live process",
                )
            return self.fixture.observation()
        if self.observer is None:
            _raise_unsupported(
                "grok_builder_unavailable",
                "Grok builder observation is unavailable",
                remedy=(
                    "supply a deterministic Grok builder fixture after qualification; "
                    "do not fall back to tmux, agy-print, cursor-acp, or generic acp"
                ),
            )
        return validate_grok_builder_observation(self.observer)

    def admit(
        self,
        *,
        expected_session: str,
        expected_grok_session_id: str,
        expected_workspace: Mapping[str, Any],
        expected_receipt: Optional[Mapping[str, Any]] = None,
        requested_model: Optional[str] = None,
        expected_observed_model: Optional[str] = None,
        expected_result_state: Optional[str] = None,
        expected_result_id: Optional[str] = None,
        require_halt: bool = False,
    ) -> Dict[str, Any]:
        return prove_grok_builder_admission(
            self.require_observation(),
            expected_session=expected_session,
            expected_grok_session_id=expected_grok_session_id,
            expected_workspace=expected_workspace,
            expected_receipt=expected_receipt,
            requested_model=requested_model,
            expected_observed_model=expected_observed_model,
            expected_result_state=expected_result_state,
            expected_result_id=expected_result_id,
            require_halt=require_halt,
        )

    def qualify_lifecycle(
        self,
        *,
        expected_session: str,
        expected_grok_session_id: str,
        expected_workspace: Mapping[str, Any],
        expected_receipt: Optional[Mapping[str, Any]] = None,
        requested_model: Optional[str] = None,
        expected_observed_model: Optional[str] = None,
        expected_result_state: Optional[str] = None,
        expected_result_id: Optional[str] = None,
        require_halt: bool = False,
        record_state: Optional[str] = None,
        halt_confirmed: Optional[bool] = None,
    ) -> Dict[str, Any]:
        return qualify_grok_builder_lifecycle(
            self.require_observation(),
            expected_session=expected_session,
            expected_grok_session_id=expected_grok_session_id,
            expected_workspace=expected_workspace,
            expected_receipt=expected_receipt,
            requested_model=requested_model,
            expected_observed_model=expected_observed_model,
            expected_result_state=expected_result_state,
            expected_result_id=expected_result_id,
            require_halt=require_halt,
            record_state=record_state,
            halt_confirmed=halt_confirmed,
        )

    def caller_result(
        self,
        *,
        expected_session: str,
        expected_grok_session_id: str,
        expected_workspace: Mapping[str, Any],
        expected_receipt: Optional[Mapping[str, Any]] = None,
        requested_model: Optional[str] = None,
        expected_observed_model: Optional[str] = None,
        expected_result_state: Optional[str] = None,
        expected_result_id: Optional[str] = None,
        record_state: Optional[str] = None,
        require_halt: bool = False,
    ) -> Dict[str, Any]:
        observation = self.require_observation()
        admitted = self.admit(
            expected_session=expected_session,
            expected_grok_session_id=expected_grok_session_id,
            expected_workspace=expected_workspace,
            expected_receipt=expected_receipt,
            requested_model=requested_model,
            expected_observed_model=expected_observed_model,
            expected_result_state=expected_result_state,
            expected_result_id=expected_result_id,
            require_halt=require_halt,
        )
        lifecycle = self.qualify_lifecycle(
            expected_session=expected_session,
            expected_grok_session_id=expected_grok_session_id,
            expected_workspace=expected_workspace,
            expected_receipt=expected_receipt,
            requested_model=requested_model,
            expected_observed_model=expected_observed_model,
            expected_result_state=expected_result_state,
            expected_result_id=expected_result_id,
            require_halt=require_halt,
            record_state=record_state,
        )
        fields = caller_fields_from_observation(
            observation,
            record_state=record_state,
            halt_confirmed=admitted["halt"] is not None,
        )
        return {
            "ok": True,
            "session": expected_session,
            "state": fields["caller_outcome"]["halt"] == "confirmed"
            and "HALTED"
            or (record_state or observation.get("record_state") or "ACTIVE"),
            "live_grok_claimed": False,
            "grok_admission": admitted,
            "lifecycle": lifecycle,
            **fields,
        }


def fixture_receipt(
    *,
    executable_fingerprint: str = "41" * 32,
    execution_fingerprint: str = "52" * 32,
    version_fingerprint: str = "53" * 32,
    platform_fingerprint: str = "54" * 32,
    adapter_fingerprint: str = "55" * 32,
    protocol_fingerprint: str = "56" * 32,
    qualification_authorized: bool = True,
    public_launch_authorized: bool = True,
    target: str = TARGET,
    kind: str = "grok_regular_paired_runtime_qualification",
    fingerprint: Optional[str] = None,
) -> Dict[str, Any]:
    """Deterministic body-safe qualification projection. Not a live pair."""

    receipt = {
        "schema": RECEIPT_SCHEMA,
        "qualification_schema": TERMINAL_QUALIFICATION_SCHEMA,
        "kind": kind,
        "target": target,
        "session_profile": "regular",
        "qualification_authorized": qualification_authorized,
        "public_launch_authorized": public_launch_authorized,
        "executable_fingerprint": executable_fingerprint,
        "execution_fingerprint": execution_fingerprint,
        "version_fingerprint": version_fingerprint,
        "platform_fingerprint": platform_fingerprint,
        "adapter_fingerprint": adapter_fingerprint,
        "protocol_fingerprint": protocol_fingerprint,
    }
    receipt["fingerprint"] = fingerprint or grok_builder_receipt_fingerprint(receipt)
    return receipt


def fixture_observation(
    *,
    session: str = "grok-builder-session",
    grok_session_id: str = "6f1c8a2e-4b70-4d91-9c3a-1e5b7d0f2a44",
    requested_model: str = "default",
    observed_model: str = "grok-4.5",
    observed_source: str = "runtime_metadata",
    runtime_model: Optional[str] = None,
    executable_sha256: str = GROK_EXECUTABLE_SHA256,
    version: str = GROK_BUILD_VERSION,
    basename: str = GROK_RUNTIME_BASENAME,
    workspace_path: str = "/tmp/grok-builder-workspace",
    branch: str = "codex/example",
    head: str = "a" * 40,
    tree: str = "b" * 40,
    terminal_state: str = "completed",
    exit_code: Optional[int] = 0,
    result_id: Optional[str] = "grok-result-1",
    halt: Optional[Mapping[str, Any]] = None,
    qualification_receipt: Optional[Mapping[str, Any]] = None,
    last_checkpoint: Optional[Mapping[str, Any]] = None,
    last_beacon: Optional[Mapping[str, Any]] = None,
    last_validated_at: Optional[str] = None,
    record_state: Optional[str] = None,
    transport: str = BOUND_TRANSPORT,
    target: str = TARGET,
) -> Dict[str, Any]:
    """Deterministic body-free fixture. Not a live Grok run."""

    return {
        "schema": OBSERVATION_SCHEMA,
        "target": target,
        "transport": transport,
        "requested_model": requested_model,
        "observed_model": {"id": observed_model, "source": observed_source},
        "workspace": {
            "path": workspace_path,
            "branch": branch,
            "head": head,
            "tree": tree,
        },
        "session": {"id": session, "grok_session_id": grok_session_id},
        "terminal_result": {
            "state": terminal_state,
            "exit_code": exit_code,
            "result_id": result_id,
        },
        "runtime": {
            "model_id": runtime_model or observed_model,
            "executable_sha256": executable_sha256,
            "version": version,
            "basename": basename,
        },
        "halt": None if halt is None else dict(halt),
        "qualification_receipt": dict(qualification_receipt or fixture_receipt()),
        "last_checkpoint": last_checkpoint,
        "last_beacon": last_beacon,
        "last_validated_at": last_validated_at,
        "record_state": record_state,
    }


# Keep the existing live-launch gate imported for tests that prove no-fallback.
__all__ = [
    "ADMISSION_SCHEMA",
    "BOUND_TRANSPORT",
    "GrokBuilderAdmissionController",
    "GrokBuilderAdmissionFixture",
    "LIFECYCLE_SCHEMA",
    "OBSERVATION_SCHEMA",
    "RECEIPT_SCHEMA",
    "TARGET",
    "caller_fields_from_observation",
    "fixture_observation",
    "fixture_receipt",
    "grok_builder_receipt_fingerprint",
    "prove_grok_builder_admission",
    "prove_observed_model",
    "prove_qualification_receipt",
    "prove_session_identity",
    "prove_shutdown",
    "prove_terminal_result",
    "prove_workspace_binding",
    "qualify_grok_builder_lifecycle",
    "require_grok_builder_target",
    "require_live_grok_builder",
    "require_live_grok_launch",
    "validate_grok_builder_observation",
    "validate_grok_builder_receipt",
]
