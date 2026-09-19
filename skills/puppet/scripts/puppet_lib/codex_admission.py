"""Codex-specific builder admission after qualification and authority gates.

This is not a transport. It does not implement Cursor ACP, generic ACP,
Herdr, or a Grok builder contract. Codex remains on its existing tmux path;
live Codex launch stays source-only. Model, workspace, UUIDv4 session,
result, and receipt claims come from observed doctor/runtime metadata plus a
current paired-qualification projection, not from a requested selector, path,
or ACP conversation id.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from .caller import caller_projection, make_blocker
from .codex_launch import (
    CURRENT_DEFAULT_SELECTION,
    DEFAULT_MODEL_SENTINEL,
    EXPECTED_EXECUTABLE_SHA256,
    EXPECTED_VERSION_SHA256,
    EXPECTED_VERSION_TEXT,
    EXPLICIT_MODEL_CLASSIFICATION,
    MAPPING_INCOMPLETE_BLOCKER,
    SOURCE_ONLY_BLOCKERS,
)
from .codex_qualification import PAIR_KIND, PAIR_SCHEMA_VERSION
from .errors import IdentityError, UnsupportedError, ValidationError
from .safety import (
    canonical_json_bytes,
    sha256_bytes,
    validate_branch,
    validate_identifier,
    validate_sha1,
    validate_sha256,
)
from .transport import DEFAULT_TRANSPORT


TARGET = "codex"
BOUND_TRANSPORT = DEFAULT_TRANSPORT
GENERIC_ACP_ID_NAME = "acp"
OBSERVATION_SCHEMA = "puppet.codex-builder-observation/v1"
RECEIPT_SCHEMA = "puppet.codex-builder-receipt/v1"
ADMISSION_SCHEMA = "puppet.codex-builder-admission/v1"
LIFECYCLE_SCHEMA = "puppet.codex-builder-lifecycle/v1"
PAIR_RESULT = "paired_evidence_only"
CODEX_LAUNCH_AUTHORITY_BLOCKERS = (*SOURCE_ONLY_BLOCKERS, MAPPING_INCOMPLETE_BLOCKER)
CODEX_LAUNCH_AUTHORITY_BLOCKER = SOURCE_ONLY_BLOCKERS[-1]
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
    {"doctor_observation", "runtime_metadata", "session_metadata"}
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
_OBSERVED_MODEL_KEYS = frozenset({"id", "source", "classification"})
_WORKSPACE_KEYS = frozenset({"path", "branch", "head", "tree"})
_SESSION_KEYS = frozenset({"id", "codex_session_id"})
_TERMINAL_KEYS = frozenset({"state", "exit_code", "result_id"})
_RUNTIME_KEYS = frozenset(
    {"model_id", "executable_sha256", "version_text", "version_sha256"}
)
_HALT_KEYS = frozenset({"session", "codex_session_id", "halted"})
_RECEIPT_KEYS = frozenset(
    {
        "schema",
        "qualification_schema_version",
        "kind",
        "result",
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
    "qualification_schema_version",
    "kind",
    "result",
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


def require_codex_builder_target(target: Any) -> str:
    """Codex builder admission is valid only for the codex target."""

    if target != TARGET:
        _raise_unsupported(
            "codex_builder_target_mismatch",
            "Codex builder admission is valid only for the codex target",
            remedy=(
                "bind target=codex after its paired qualification and source-only "
                "authority gates; do not admit cursor, agy, claude, or grok "
                "through this contract"
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


def codex_builder_receipt_fingerprint(value: Mapping[str, Any]) -> str:
    """Hash the current Codex paired-qualification projection without the fingerprint."""

    body = {name: value[name] for name in _RECEIPT_HASH_FIELDS}
    return sha256_bytes(canonical_json_bytes(body))


def validate_codex_builder_receipt(value: Any) -> Dict[str, Any]:
    """Return one body-safe current Codex paired-qualification receipt projection."""

    if not isinstance(value, Mapping) or set(value) != _RECEIPT_KEYS:
        raise ValidationError("Codex builder receipt fields do not match schema")
    if value.get("schema") != RECEIPT_SCHEMA:
        raise ValidationError("Codex builder receipt schema is invalid")
    if value.get("qualification_schema_version") != PAIR_SCHEMA_VERSION:
        _raise_identity(
            "qualification_receipt_invalid",
            "Codex builder admission requires the regular paired qualification schema version",
        )
    if value.get("kind") != PAIR_KIND or value.get("session_profile") != "regular":
        _raise_identity(
            "qualification_receipt_invalid",
            "Codex builder admission requires the regular paired qualification substrate",
        )
    if value.get("result") != PAIR_RESULT:
        _raise_identity(
            "qualification_receipt_invalid",
            "Codex builder admission requires paired-evidence-only qualification result",
        )
    require_codex_builder_target(value.get("target"))
    if value.get("qualification_authorized") is not True:
        _raise_identity(
            "qualification_receipt_invalid",
            "Codex qualification receipt is not authorized",
        )
    if value.get("public_launch_authorized") is not False:
        _raise_identity(
            "qualification_receipt_invalid",
            "Codex paired receipt is not public launch authority",
        )
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "qualification_schema_version": PAIR_SCHEMA_VERSION,
        "kind": PAIR_KIND,
        "result": PAIR_RESULT,
        "target": TARGET,
        "session_profile": "regular",
        "qualification_authorized": True,
        "public_launch_authorized": False,
        "executable_fingerprint": validate_sha256(
            value.get("executable_fingerprint"), "Codex executable fingerprint"
        ),
        "execution_fingerprint": validate_sha256(
            value.get("execution_fingerprint"), "Codex execution fingerprint"
        ),
        "version_fingerprint": validate_sha256(
            value.get("version_fingerprint"), "Codex version fingerprint"
        ),
        "platform_fingerprint": validate_sha256(
            value.get("platform_fingerprint"), "Codex platform fingerprint"
        ),
        "adapter_fingerprint": validate_sha256(
            value.get("adapter_fingerprint"), "Codex adapter fingerprint"
        ),
        "protocol_fingerprint": validate_sha256(
            value.get("protocol_fingerprint"), "Codex protocol fingerprint"
        ),
        "fingerprint": validate_sha256(
            value.get("fingerprint"), "Codex builder receipt fingerprint"
        ),
    }
    expected = codex_builder_receipt_fingerprint(receipt)
    if receipt["fingerprint"] != expected:
        _raise_identity(
            "qualification_receipt_invalid",
            "Codex qualification receipt fingerprint is stale",
        )
    return receipt


def validate_codex_builder_observation(value: Any) -> Dict[str, Any]:
    """Return one body-safe structured Codex builder observation."""

    if not isinstance(value, Mapping) or set(value) != _OBSERVATION_KEYS:
        raise ValidationError("Codex builder observation fields do not match schema")
    if value.get("schema") != OBSERVATION_SCHEMA:
        raise ValidationError("Codex builder observation schema is invalid")
    require_codex_builder_target(value.get("target"))
    transport = value.get("transport")
    if transport == GENERIC_ACP_ID_NAME:
        _raise_identity(
            "identity_mismatch",
            "generic acp is not a Codex builder transport",
            remedy=(
                "keep generic acp unsupported; Codex builder admission stays on "
                "tmux after paired qualification and never opens acp"
            ),
        )
    if transport in FORBIDDEN_TRANSPORTS:
        _raise_unsupported(
            "transport_unsupported",
            "Codex builder admission does not bind transport %s" % transport,
            remedy=(
                "keep Codex on tmux after paired qualification; herdr, generic acp, "
                "agy-print, and cursor-acp are not Codex builder transports"
            ),
        )
    if transport != BOUND_TRANSPORT:
        _raise_identity(
            "identity_mismatch",
            "Codex builder observation is bound to a different transport",
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
            raise ValidationError("Codex observed model fields are invalid")
        observed_model = {
            "id": _bounded_text(
                observed_model.get("id"), label="observed model", maximum=200
            ),
            "source": _bounded_text(
                observed_model.get("source"),
                label="observed model source",
                maximum=80,
            ),
            "classification": _bounded_text(
                observed_model.get("classification"),
                label="observed model classification",
                maximum=80,
            ),
        }
    workspace = value.get("workspace")
    if not isinstance(workspace, Mapping) or set(workspace) != _WORKSPACE_KEYS:
        raise ValidationError("Codex workspace fields are invalid")
    workspace = {
        "path": _bounded_text(workspace.get("path"), label="workspace path", maximum=1024),
        "branch": validate_branch(workspace.get("branch")),
        "head": validate_sha1(workspace.get("head"), "workspace head"),
        "tree": validate_sha1(workspace.get("tree"), "workspace tree"),
    }
    session = value.get("session")
    if not isinstance(session, Mapping) or set(session) != _SESSION_KEYS:
        raise ValidationError("Codex session fields are invalid")
    session = {
        "id": validate_identifier(session.get("id"), "Codex session"),
        "codex_session_id": _session_uuid(
            session.get("codex_session_id"), "Codex session id"
        ),
    }
    terminal = value.get("terminal_result")
    if not isinstance(terminal, Mapping) or set(terminal) != _TERMINAL_KEYS:
        raise ValidationError("Codex terminal result fields are invalid")
    state = terminal.get("state")
    if state not in TERMINAL_STATES:
        raise ValidationError("Codex terminal result state is invalid")
    result_id = terminal.get("result_id")
    if result_id is not None:
        result_id = validate_identifier(result_id, "Codex result")
    terminal = {
        "state": state,
        "exit_code": _optional_int(terminal.get("exit_code"), label="terminal exit code"),
        "result_id": result_id,
    }
    runtime = value.get("runtime")
    if not isinstance(runtime, Mapping) or set(runtime) != _RUNTIME_KEYS:
        raise ValidationError("Codex runtime fields are invalid")
    runtime = {
        "model_id": _bounded_text(runtime.get("model_id"), label="runtime model", maximum=200),
        "executable_sha256": validate_sha256(
            runtime.get("executable_sha256"), "Codex runtime executable"
        ),
        "version_text": _bounded_text(
            runtime.get("version_text"), label="Codex runtime version", maximum=64
        ),
        "version_sha256": validate_sha256(
            runtime.get("version_sha256"), "Codex runtime version hash"
        ),
    }
    halt = value.get("halt")
    if halt is not None:
        if not isinstance(halt, Mapping) or set(halt) != _HALT_KEYS:
            raise ValidationError("Codex halt fields are invalid")
        if halt.get("halted") is not True:
            raise ValidationError("Codex halt state is invalid")
        halt = {
            "session": validate_identifier(halt.get("session"), "Codex halt session"),
            "codex_session_id": _session_uuid(
                halt.get("codex_session_id"), "Codex halt session id"
            ),
            "halted": True,
        }
    checkpoint = value.get("last_checkpoint")
    if checkpoint is not None:
        if not isinstance(checkpoint, Mapping) or "checkpoint_id" not in checkpoint:
            raise ValidationError("Codex checkpoint is invalid")
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
            raise ValidationError("Codex beacon is invalid")
        sequence = beacon.get("sequence")
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 0:
            raise ValidationError("Codex beacon sequence is invalid")
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
        "qualification_receipt": validate_codex_builder_receipt(
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
    """Prove the current Codex paired-qualification receipt. Stale or foreign fails."""

    observation = validate_codex_builder_observation(observation)
    receipt = observation["qualification_receipt"]
    if expected_receipt is not None:
        expected = validate_codex_builder_receipt(expected_receipt)
        if receipt != expected:
            _raise_identity(
                "qualification_receipt_invalid",
                "Codex qualification receipt is stale",
            )
    return dict(receipt)


def prove_observed_model(
    observation: Mapping[str, Any],
    *,
    requested_model: Optional[str] = None,
    expected_observed_model: Optional[str] = None,
) -> Dict[str, Any]:
    """Prove the executed Codex model from doctor/runtime metadata, not the selector."""

    observation = validate_codex_builder_observation(observation)
    observed = observation.get("observed_model")
    requested = requested_model or observation.get("requested_model")
    if (
        observed is None
        or observed.get("source") not in RUNTIME_MODEL_SOURCES
        or observed.get("classification") != EXPLICIT_MODEL_CLASSIFICATION
        or observed.get("id") in {DEFAULT_MODEL_SENTINEL, CURRENT_DEFAULT_SELECTION}
    ):
        _raise_identity(
            "model_observation_selector_only",
            "requested selector is not observed Codex doctor model proof",
        )
    model_id = observed["id"]
    runtime = observation["runtime"]
    if model_id != runtime["model_id"]:
        _raise_identity(
            "model_observation_selector_only",
            "observed model is missing from Codex runtime metadata",
        )
    if requested is not None and model_id == requested:
        _raise_identity(
            "model_observation_selector_only",
            "requested selector is not observed Codex doctor model proof",
        )
    if expected_observed_model is not None and expected_observed_model != model_id:
        _raise_identity(
            "model_observation_mismatch",
            "observed model does not match the bound Codex runtime",
        )
    if (
        runtime["executable_sha256"] != EXPECTED_EXECUTABLE_SHA256
        or runtime["version_text"] != EXPECTED_VERSION_TEXT
        or runtime["version_sha256"] != EXPECTED_VERSION_SHA256
    ):
        _raise_identity(
            "model_observation_mismatch",
            "observed Codex runtime identity does not match codex-cli 0.145.0",
        )
    return {
        "observed_model": model_id,
        "source": observed["source"],
        "classification": observed["classification"],
        "requested_model": requested,
        "executable_sha256": runtime["executable_sha256"],
        "version_text": runtime["version_text"],
        "version_sha256": runtime["version_sha256"],
    }


def prove_workspace_binding(
    observation: Mapping[str, Any],
    *,
    expected_workspace: Mapping[str, Any],
) -> Dict[str, Any]:
    """Prove the exact bound workspace. A path alone is not enough."""

    observation = validate_codex_builder_observation(observation)
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
            "Codex workspace identity does not match the bound checkout",
        )
    return dict(workspace)


def prove_terminal_result(
    observation: Mapping[str, Any],
    *,
    expected_state: Optional[str] = None,
    expected_result_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Prove the worker terminal/result state from structured observation."""

    observation = validate_codex_builder_observation(observation)
    terminal = observation["terminal_result"]
    if expected_state is not None and terminal["state"] != expected_state:
        _raise_identity(
            "result_identity_mismatch",
            "Codex terminal result state does not match the bound result",
        )
    if expected_result_id is not None and terminal["result_id"] != expected_result_id:
        _raise_identity(
            "result_identity_mismatch",
            "Codex terminal result identity does not match the bound result",
        )
    return dict(terminal)


def prove_session_identity(
    observation: Mapping[str, Any],
    *,
    expected_session: str,
    expected_codex_session_id: str,
) -> Dict[str, Any]:
    """Prove matching controller session and Codex UUIDv4 identity."""

    observation = validate_codex_builder_observation(observation)
    session = observation["session"]
    if (
        not expected_session
        or not expected_codex_session_id
        or session["id"] != expected_session
        or session["codex_session_id"] != expected_codex_session_id
    ):
        _raise_identity(
            "session_identity_mismatch",
            "Codex admission requires matching session and Codex session identity",
        )
    return {
        "session": session["id"],
        "codex_session_id": session["codex_session_id"],
        "session_proved": True,
    }


def prove_shutdown(
    observation: Mapping[str, Any],
    *,
    expected_session: str,
    expected_codex_session_id: str,
) -> Dict[str, Any]:
    """Prove exact Codex session halt. Do not accept a foreign session."""

    matched = prove_session_identity(
        observation,
        expected_session=expected_session,
        expected_codex_session_id=expected_codex_session_id,
    )
    observation = validate_codex_builder_observation(observation)
    halt = observation.get("halt")
    if not isinstance(halt, Mapping):
        _raise_identity(
            "session_identity_mismatch",
            "Codex halt proof is missing the owned Codex session identity",
        )
    if (
        halt["session"] != matched["session"]
        or halt["codex_session_id"] != matched["codex_session_id"]
        or halt["halted"] is not True
    ):
        _raise_identity(
            "session_identity_mismatch",
            "Codex halt is not confined to the owned Codex session",
        )
    return {
        "session": halt["session"],
        "codex_session_id": halt["codex_session_id"],
        "halted": True,
    }


def prove_codex_builder_admission(
    observation: Mapping[str, Any],
    *,
    expected_session: str,
    expected_codex_session_id: str,
    expected_workspace: Mapping[str, Any],
    expected_receipt: Optional[Mapping[str, Any]] = None,
    requested_model: Optional[str] = None,
    expected_observed_model: Optional[str] = None,
    expected_result_state: Optional[str] = None,
    expected_result_id: Optional[str] = None,
    require_halt: bool = False,
) -> Dict[str, Any]:
    """Admit Codex as a builder from one current observation and receipt."""

    observation = validate_codex_builder_observation(observation)
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
        expected_codex_session_id=expected_codex_session_id,
    )
    halt = None
    if require_halt or observation.get("halt") is not None:
        halt = prove_shutdown(
            observation,
            expected_session=expected_session,
            expected_codex_session_id=expected_codex_session_id,
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
        "authority_blockers": list(CODEX_LAUNCH_AUTHORITY_BLOCKERS),
        "launch_authorized": False,
        "live_codex_claimed": False,
    }


def session_record_from_observation(
    observation: Mapping[str, Any],
    *,
    record_state: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a caller-projection record. Does not persist a tmux session."""

    observation = validate_codex_builder_observation(observation)
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
    """Preserve stage-2 worker/controller/halt distinctions on Codex admission."""

    record = session_record_from_observation(
        observation, record_state=record_state
    )
    if halt_confirmed is None:
        halt_confirmed = record["state"] == "HALTED"
    return caller_projection(
        record, transport_id=BOUND_TRANSPORT, halt_confirmed=halt_confirmed
    )


def qualify_codex_builder_lifecycle(
    observation: Mapping[str, Any],
    *,
    expected_session: str,
    expected_codex_session_id: str,
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
    """Qualify the deterministic Codex builder lifecycle. Never claims a live run."""

    observation = validate_codex_builder_observation(observation)
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
            expected_codex_session_id=expected_codex_session_id,
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
            expected_codex_session_id=expected_codex_session_id,
        )
        if halt_state != "confirmed":
            _raise_identity(
                "session_identity_mismatch",
                "Codex confirmed halt is missing",
            )
    final = fields["final_outcome"]
    if halt_proof is None and acceptance == "none":
        if final is not None:
            raise ValidationError("Codex final outcome is not bounded")
    elif final is None:
        raise ValidationError("Codex final outcome is missing")
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
        raise ValidationError("Codex builder lifecycle phases do not match schema")
    return {
        "schema": LIFECYCLE_SCHEMA,
        "target": TARGET,
        "transport": BOUND_TRANSPORT,
        "phases": phases,
        "phase_order": list(LIFECYCLE_PHASES),
        "caller_outcome": fields["caller_outcome"],
        "progress_cursor": fields["progress_cursor"],
        "live_codex_claimed": False,
    }


def require_live_codex_builder(observation: Optional[Mapping[str, Any]] = None) -> None:
    """Fail closed. Builder admission never opens a live Codex process."""

    if observation is not None:
        validate_codex_builder_observation(observation)
    raise UnsupportedError(
        CODEX_LAUNCH_AUTHORITY_BLOCKER,
        blocker=_blocker("codex_launch_authority", CODEX_LAUNCH_AUTHORITY_BLOCKER),
    )


class CodexBuilderAdmissionFixture:
    """Deterministic Codex builder observation. Never starts a live Codex process."""

    def __init__(self, observation: Optional[Mapping[str, Any]] = None):
        self._observation = (
            dict(observation) if observation is not None else fixture_observation()
        )

    @staticmethod
    def available() -> bool:
        return False

    def observation(self) -> Dict[str, Any]:
        return validate_codex_builder_observation(self._observation)


class CodexBuilderAdmissionController:
    """Structured Codex builder admission. Never constructs a live Codex runtime."""

    def __init__(
        self,
        registry_root: Path,
        *,
        observer: Optional[Mapping[str, Any]] = None,
        fixture: Optional[CodexBuilderAdmissionFixture] = None,
    ):
        self.registry_root = Path(registry_root)
        self.observer = observer
        self.fixture = fixture

    @staticmethod
    def available() -> bool:
        """Live Codex is not claimed. Fixtures do not make this true."""

        return False

    def require_observation(self) -> Dict[str, Any]:
        if self.fixture is not None:
            if self.fixture.available():
                _raise_unsupported(
                    "codex_builder_unavailable",
                    "Codex builder fixture must stay fail-closed",
                    remedy="keep the live Codex gate closed; do not treat a fixture as a live process",
                )
            return self.fixture.observation()
        if self.observer is None:
            _raise_unsupported(
                "codex_builder_unavailable",
                "Codex builder observation is unavailable",
                remedy=(
                    "supply a deterministic Codex builder fixture after paired "
                    "qualification; do not fall back to tmux, agy-print, "
                    "cursor-acp, or generic acp"
                ),
            )
        return validate_codex_builder_observation(self.observer)

    def admit(
        self,
        *,
        expected_session: str,
        expected_codex_session_id: str,
        expected_workspace: Mapping[str, Any],
        expected_receipt: Optional[Mapping[str, Any]] = None,
        requested_model: Optional[str] = None,
        expected_observed_model: Optional[str] = None,
        expected_result_state: Optional[str] = None,
        expected_result_id: Optional[str] = None,
        require_halt: bool = False,
    ) -> Dict[str, Any]:
        return prove_codex_builder_admission(
            self.require_observation(),
            expected_session=expected_session,
            expected_codex_session_id=expected_codex_session_id,
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
        expected_codex_session_id: str,
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
        return qualify_codex_builder_lifecycle(
            self.require_observation(),
            expected_session=expected_session,
            expected_codex_session_id=expected_codex_session_id,
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
        expected_codex_session_id: str,
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
            expected_codex_session_id=expected_codex_session_id,
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
            expected_codex_session_id=expected_codex_session_id,
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
            "live_codex_claimed": False,
            "codex_admission": admitted,
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
    public_launch_authorized: bool = False,
    target: str = TARGET,
    kind: str = PAIR_KIND,
    result: str = PAIR_RESULT,
    fingerprint: Optional[str] = None,
) -> Dict[str, Any]:
    """Deterministic body-safe paired-qualification projection. Not a live pair."""

    receipt = {
        "schema": RECEIPT_SCHEMA,
        "qualification_schema_version": PAIR_SCHEMA_VERSION,
        "kind": kind,
        "result": result,
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
    receipt["fingerprint"] = fingerprint or codex_builder_receipt_fingerprint(receipt)
    return receipt


def fixture_observation(
    *,
    session: str = "codex-builder-session",
    codex_session_id: str = "3a1e9c70-8b24-4d51-9f06-2c7e4a8b9153",
    requested_model: str = CURRENT_DEFAULT_SELECTION,
    observed_model: str = "gpt-5.6-sol",
    observed_source: str = "doctor_observation",
    observed_classification: str = EXPLICIT_MODEL_CLASSIFICATION,
    runtime_model: Optional[str] = None,
    executable_sha256: str = EXPECTED_EXECUTABLE_SHA256,
    version_text: str = EXPECTED_VERSION_TEXT,
    version_sha256: str = EXPECTED_VERSION_SHA256,
    workspace_path: str = "/tmp/codex-builder-workspace",
    branch: str = "codex/example",
    head: str = "a" * 40,
    tree: str = "b" * 40,
    terminal_state: str = "completed",
    exit_code: Optional[int] = 0,
    result_id: Optional[str] = "codex-result-1",
    halt: Optional[Mapping[str, Any]] = None,
    qualification_receipt: Optional[Mapping[str, Any]] = None,
    last_checkpoint: Optional[Mapping[str, Any]] = None,
    last_beacon: Optional[Mapping[str, Any]] = None,
    last_validated_at: Optional[str] = None,
    record_state: Optional[str] = None,
    transport: str = BOUND_TRANSPORT,
    target: str = TARGET,
) -> Dict[str, Any]:
    """Deterministic body-free fixture. Not a live Codex run."""

    return {
        "schema": OBSERVATION_SCHEMA,
        "target": target,
        "transport": transport,
        "requested_model": requested_model,
        "observed_model": {
            "id": observed_model,
            "source": observed_source,
            "classification": observed_classification,
        },
        "workspace": {
            "path": workspace_path,
            "branch": branch,
            "head": head,
            "tree": tree,
        },
        "session": {"id": session, "codex_session_id": codex_session_id},
        "terminal_result": {
            "state": terminal_state,
            "exit_code": exit_code,
            "result_id": result_id,
        },
        "runtime": {
            "model_id": runtime_model or observed_model,
            "executable_sha256": executable_sha256,
            "version_text": version_text,
            "version_sha256": version_sha256,
        },
        "halt": None if halt is None else dict(halt),
        "qualification_receipt": dict(qualification_receipt or fixture_receipt()),
        "last_checkpoint": last_checkpoint,
        "last_beacon": last_beacon,
        "last_validated_at": last_validated_at,
        "record_state": record_state,
    }


__all__ = [
    "ADMISSION_SCHEMA",
    "BOUND_TRANSPORT",
    "CODEX_LAUNCH_AUTHORITY_BLOCKER",
    "CODEX_LAUNCH_AUTHORITY_BLOCKERS",
    "CodexBuilderAdmissionController",
    "CodexBuilderAdmissionFixture",
    "LIFECYCLE_SCHEMA",
    "OBSERVATION_SCHEMA",
    "RECEIPT_SCHEMA",
    "TARGET",
    "caller_fields_from_observation",
    "codex_builder_receipt_fingerprint",
    "fixture_observation",
    "fixture_receipt",
    "prove_codex_builder_admission",
    "prove_observed_model",
    "prove_qualification_receipt",
    "prove_session_identity",
    "prove_shutdown",
    "prove_terminal_result",
    "prove_workspace_binding",
    "qualify_codex_builder_lifecycle",
    "require_codex_builder_target",
    "require_live_codex_builder",
    "validate_codex_builder_observation",
    "validate_codex_builder_receipt",
]
