"""Claude-specific builder admission after paired qualification and authority.

This is not a transport. It does not implement Cursor ACP, generic ACP,
Herdr, or a Codex/Grok builder contract. Claude remains on its existing tmux
path; live Claude launch stays source-only. Model, workspace, session, result,
and receipt claims come from observed runtime metadata plus a current paired-
qualification projection, not from a requested selector, path, or ACP
conversation id.

Session identity uses Claude's existing ``session_id`` field (the ``--session-id``
contract), not ``codex_session_id``, ``grok_session_id``, or ``conversation_id``.
Model identity uses Claude's existing ``resolved_identity`` field.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from .caller import caller_projection, make_blocker
from .claude_paired_qualification import PAIR_SCHEMA
from .claude_startup_gates import CLAUDE_VERSION, CLAUDE_VERSION_OBSERVATION_SHA256
from .errors import IdentityError, UnsupportedError, ValidationError
from .run_observations import CLAUDE_MATCHED_CONTROL_BLOCKERS
from .safety import (
    canonical_json_bytes,
    sha256_bytes,
    validate_branch,
    validate_identifier,
    validate_sha1,
    validate_sha256,
)
from .transport import DEFAULT_TRANSPORT


TARGET = "claude"
BOUND_TRANSPORT = DEFAULT_TRANSPORT
GENERIC_ACP_ID_NAME = "acp"
OBSERVATION_SCHEMA = "puppet.claude-builder-observation/v1"
RECEIPT_SCHEMA = "puppet.claude-builder-receipt/v1"
ADMISSION_SCHEMA = "puppet.claude-builder-admission/v1"
LIFECYCLE_SCHEMA = "puppet.claude-builder-lifecycle/v1"
PAIR_KIND = "claude_regular_paired_qualification"
PAIR_RESULT = "paired_accepted"
CURRENT_DEFAULT_SELECTION = "current_default"
UNAVAILABLE_IDENTITY = "unavailable"
CLAUDE_LAUNCH_AUTHORITY_BLOCKERS = CLAUDE_MATCHED_CONTROL_BLOCKERS
CLAUDE_LAUNCH_AUTHORITY_BLOCKER = CLAUDE_MATCHED_CONTROL_BLOCKERS[-1]
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
    {"runtime_metadata", "session_metadata", "claude_runtime_metadata"}
)
SELECTOR_IDENTITIES = frozenset(
    {CURRENT_DEFAULT_SELECTION, UNAVAILABLE_IDENTITY, "default"}
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
_OBSERVED_MODEL_KEYS = frozenset({"id", "source", "resolved_identity"})
_WORKSPACE_KEYS = frozenset({"path", "branch", "head", "tree"})
_SESSION_KEYS = frozenset({"id", "session_id"})
_TERMINAL_KEYS = frozenset({"state", "exit_code", "result_id"})
_RUNTIME_KEYS = frozenset({"model_id", "version", "version_sha256"})
_HALT_KEYS = frozenset({"session", "session_id", "halted"})
_RECEIPT_KEYS = frozenset(
    {
        "schema",
        "qualification_schema",
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
    "qualification_schema",
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


def require_claude_builder_target(target: Any) -> str:
    """Claude builder admission is valid only for the claude target."""

    if target != TARGET:
        _raise_unsupported(
            "claude_builder_target_mismatch",
            "Claude builder admission is valid only for the claude target",
            remedy=(
                "bind target=claude after its paired qualification and source-only "
                "authority gates; do not admit cursor, agy, codex, or grok "
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


def claude_builder_receipt_fingerprint(value: Mapping[str, Any]) -> str:
    """Hash the current Claude paired-qualification projection without the fingerprint."""

    body = {name: value[name] for name in _RECEIPT_HASH_FIELDS}
    return sha256_bytes(canonical_json_bytes(body))


def validate_claude_builder_receipt(value: Any) -> Dict[str, Any]:
    """Return one body-safe current Claude paired-qualification receipt projection."""

    if not isinstance(value, Mapping) or set(value) != _RECEIPT_KEYS:
        raise ValidationError("Claude builder receipt fields do not match schema")
    if value.get("schema") != RECEIPT_SCHEMA:
        raise ValidationError("Claude builder receipt schema is invalid")
    if value.get("qualification_schema") != PAIR_SCHEMA:
        _raise_identity(
            "qualification_receipt_invalid",
            "Claude builder admission requires the regular paired qualification schema",
        )
    if value.get("kind") != PAIR_KIND or value.get("session_profile") != "regular":
        _raise_identity(
            "qualification_receipt_invalid",
            "Claude builder admission requires the regular paired qualification substrate",
        )
    if value.get("result") != PAIR_RESULT:
        _raise_identity(
            "qualification_receipt_invalid",
            "Claude builder admission requires paired-accepted qualification result",
        )
    require_claude_builder_target(value.get("target"))
    if value.get("qualification_authorized") is not True:
        _raise_identity(
            "qualification_receipt_invalid",
            "Claude qualification receipt is not authorized",
        )
    if value.get("public_launch_authorized") is not False:
        _raise_identity(
            "qualification_receipt_invalid",
            "Claude paired receipt is not public launch authority",
        )
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "qualification_schema": PAIR_SCHEMA,
        "kind": PAIR_KIND,
        "result": PAIR_RESULT,
        "target": TARGET,
        "session_profile": "regular",
        "qualification_authorized": True,
        "public_launch_authorized": False,
        "executable_fingerprint": validate_sha256(
            value.get("executable_fingerprint"), "Claude executable fingerprint"
        ),
        "execution_fingerprint": validate_sha256(
            value.get("execution_fingerprint"), "Claude execution fingerprint"
        ),
        "version_fingerprint": validate_sha256(
            value.get("version_fingerprint"), "Claude version fingerprint"
        ),
        "platform_fingerprint": validate_sha256(
            value.get("platform_fingerprint"), "Claude platform fingerprint"
        ),
        "adapter_fingerprint": validate_sha256(
            value.get("adapter_fingerprint"), "Claude adapter fingerprint"
        ),
        "protocol_fingerprint": validate_sha256(
            value.get("protocol_fingerprint"), "Claude protocol fingerprint"
        ),
        "fingerprint": validate_sha256(
            value.get("fingerprint"), "Claude builder receipt fingerprint"
        ),
    }
    expected = claude_builder_receipt_fingerprint(receipt)
    if receipt["fingerprint"] != expected:
        _raise_identity(
            "qualification_receipt_invalid",
            "Claude qualification receipt fingerprint is stale",
        )
    return receipt


def validate_claude_builder_observation(value: Any) -> Dict[str, Any]:
    """Return one body-safe structured Claude builder observation."""

    if not isinstance(value, Mapping) or set(value) != _OBSERVATION_KEYS:
        raise ValidationError("Claude builder observation fields do not match schema")
    if value.get("schema") != OBSERVATION_SCHEMA:
        raise ValidationError("Claude builder observation schema is invalid")
    require_claude_builder_target(value.get("target"))
    transport = value.get("transport")
    if transport == GENERIC_ACP_ID_NAME:
        _raise_identity(
            "identity_mismatch",
            "generic acp is not a Claude builder transport",
            remedy=(
                "keep generic acp unsupported; Claude builder admission stays on "
                "tmux after paired qualification and never opens acp"
            ),
        )
    if transport in FORBIDDEN_TRANSPORTS:
        _raise_unsupported(
            "transport_unsupported",
            "Claude builder admission does not bind transport %s" % transport,
            remedy=(
                "keep Claude on tmux after paired qualification; herdr, generic acp, "
                "agy-print, and cursor-acp are not Claude builder transports"
            ),
        )
    if transport != BOUND_TRANSPORT:
        _raise_identity(
            "identity_mismatch",
            "Claude builder observation is bound to a different transport",
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
            raise ValidationError("Claude observed model fields are invalid")
        observed_model = {
            "id": _bounded_text(
                observed_model.get("id"), label="observed model", maximum=200
            ),
            "source": _bounded_text(
                observed_model.get("source"),
                label="observed model source",
                maximum=80,
            ),
            "resolved_identity": _bounded_text(
                observed_model.get("resolved_identity"),
                label="resolved identity",
                maximum=200,
            ),
        }
    workspace = value.get("workspace")
    if not isinstance(workspace, Mapping) or set(workspace) != _WORKSPACE_KEYS:
        raise ValidationError("Claude workspace fields are invalid")
    workspace = {
        "path": _bounded_text(workspace.get("path"), label="workspace path", maximum=1024),
        "branch": validate_branch(workspace.get("branch")),
        "head": validate_sha1(workspace.get("head"), "workspace head"),
        "tree": validate_sha1(workspace.get("tree"), "workspace tree"),
    }
    session = value.get("session")
    if not isinstance(session, Mapping) or set(session) != _SESSION_KEYS:
        raise ValidationError("Claude session fields are invalid")
    session = {
        "id": validate_identifier(session.get("id"), "Claude session"),
        "session_id": _session_uuid(session.get("session_id"), "Claude session id"),
    }
    terminal = value.get("terminal_result")
    if not isinstance(terminal, Mapping) or set(terminal) != _TERMINAL_KEYS:
        raise ValidationError("Claude terminal result fields are invalid")
    state = terminal.get("state")
    if state not in TERMINAL_STATES:
        raise ValidationError("Claude terminal result state is invalid")
    result_id = terminal.get("result_id")
    if result_id is not None:
        result_id = validate_identifier(result_id, "Claude result")
    terminal = {
        "state": state,
        "exit_code": _optional_int(terminal.get("exit_code"), label="terminal exit code"),
        "result_id": result_id,
    }
    runtime = value.get("runtime")
    if not isinstance(runtime, Mapping) or set(runtime) != _RUNTIME_KEYS:
        raise ValidationError("Claude runtime fields are invalid")
    runtime = {
        "model_id": _bounded_text(runtime.get("model_id"), label="runtime model", maximum=200),
        "version": _bounded_text(runtime.get("version"), label="Claude runtime version", maximum=32),
        "version_sha256": validate_sha256(
            runtime.get("version_sha256"), "Claude runtime version hash"
        ),
    }
    halt = value.get("halt")
    if halt is not None:
        if not isinstance(halt, Mapping) or set(halt) != _HALT_KEYS:
            raise ValidationError("Claude halt fields are invalid")
        if halt.get("halted") is not True:
            raise ValidationError("Claude halt state is invalid")
        halt = {
            "session": validate_identifier(halt.get("session"), "Claude halt session"),
            "session_id": _session_uuid(halt.get("session_id"), "Claude halt session id"),
            "halted": True,
        }
    checkpoint = value.get("last_checkpoint")
    if checkpoint is not None:
        if not isinstance(checkpoint, Mapping) or "checkpoint_id" not in checkpoint:
            raise ValidationError("Claude checkpoint is invalid")
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
            raise ValidationError("Claude beacon is invalid")
        sequence = beacon.get("sequence")
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 0:
            raise ValidationError("Claude beacon sequence is invalid")
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
        "qualification_receipt": validate_claude_builder_receipt(
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
    """Prove the current Claude paired-qualification receipt. Stale or foreign fails."""

    observation = validate_claude_builder_observation(observation)
    receipt = observation["qualification_receipt"]
    if expected_receipt is not None:
        expected = validate_claude_builder_receipt(expected_receipt)
        if receipt != expected:
            _raise_identity(
                "qualification_receipt_invalid",
                "Claude qualification receipt is stale",
            )
    return dict(receipt)


def prove_observed_model(
    observation: Mapping[str, Any],
    *,
    requested_model: Optional[str] = None,
    expected_observed_model: Optional[str] = None,
) -> Dict[str, Any]:
    """Prove the executed Claude model from resolved_identity, not the selector."""

    observation = validate_claude_builder_observation(observation)
    observed = observation.get("observed_model")
    requested = requested_model or observation.get("requested_model")
    if (
        observed is None
        or observed.get("source") not in RUNTIME_MODEL_SOURCES
        or observed.get("id") in SELECTOR_IDENTITIES
        or observed.get("resolved_identity") in SELECTOR_IDENTITIES
        or observed.get("resolved_identity") != observed.get("id")
    ):
        _raise_identity(
            "model_observation_selector_only",
            "requested selector is not observed Claude resolved_identity proof",
        )
    model_id = observed["id"]
    runtime = observation["runtime"]
    if model_id != runtime["model_id"]:
        _raise_identity(
            "model_observation_selector_only",
            "observed model is missing from Claude runtime metadata",
        )
    if requested is not None and model_id == requested:
        _raise_identity(
            "model_observation_selector_only",
            "requested selector is not observed Claude resolved_identity proof",
        )
    if expected_observed_model is not None and expected_observed_model != model_id:
        _raise_identity(
            "model_observation_mismatch",
            "observed model does not match the bound Claude runtime",
        )
    if (
        runtime["version"] != CLAUDE_VERSION
        or runtime["version_sha256"] != CLAUDE_VERSION_OBSERVATION_SHA256
    ):
        _raise_identity(
            "model_observation_mismatch",
            "observed Claude runtime identity does not match Claude Code 2.1.215",
        )
    return {
        "observed_model": model_id,
        "source": observed["source"],
        "resolved_identity": observed["resolved_identity"],
        "requested_model": requested,
        "version": runtime["version"],
        "version_sha256": runtime["version_sha256"],
    }


def prove_workspace_binding(
    observation: Mapping[str, Any],
    *,
    expected_workspace: Mapping[str, Any],
) -> Dict[str, Any]:
    """Prove the exact bound workspace. A path alone is not enough."""

    observation = validate_claude_builder_observation(observation)
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
            "Claude workspace identity does not match the bound checkout",
        )
    return dict(workspace)


def prove_terminal_result(
    observation: Mapping[str, Any],
    *,
    expected_state: Optional[str] = None,
    expected_result_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Prove the worker terminal/result state from structured observation."""

    observation = validate_claude_builder_observation(observation)
    terminal = observation["terminal_result"]
    if expected_state is not None and terminal["state"] != expected_state:
        _raise_identity(
            "result_identity_mismatch",
            "Claude terminal result state does not match the bound result",
        )
    if expected_result_id is not None and terminal["result_id"] != expected_result_id:
        _raise_identity(
            "result_identity_mismatch",
            "Claude terminal result identity does not match the bound result",
        )
    return dict(terminal)


def prove_session_identity(
    observation: Mapping[str, Any],
    *,
    expected_session: str,
    expected_session_id: str,
) -> Dict[str, Any]:
    """Prove matching controller session and Claude ``session_id`` identity."""

    observation = validate_claude_builder_observation(observation)
    session = observation["session"]
    if (
        not expected_session
        or not expected_session_id
        or session["id"] != expected_session
        or session["session_id"] != expected_session_id
    ):
        _raise_identity(
            "session_identity_mismatch",
            "Claude admission requires matching session and Claude session_id identity",
        )
    return {
        "session": session["id"],
        "session_id": session["session_id"],
        "session_proved": True,
    }


def prove_shutdown(
    observation: Mapping[str, Any],
    *,
    expected_session: str,
    expected_session_id: str,
) -> Dict[str, Any]:
    """Prove exact Claude session halt. Do not accept a foreign session."""

    matched = prove_session_identity(
        observation,
        expected_session=expected_session,
        expected_session_id=expected_session_id,
    )
    observation = validate_claude_builder_observation(observation)
    halt = observation.get("halt")
    if not isinstance(halt, Mapping):
        _raise_identity(
            "session_identity_mismatch",
            "Claude halt proof is missing the owned Claude session_id identity",
        )
    if (
        halt["session"] != matched["session"]
        or halt["session_id"] != matched["session_id"]
        or halt["halted"] is not True
    ):
        _raise_identity(
            "session_identity_mismatch",
            "Claude halt is not confined to the owned Claude session",
        )
    return {
        "session": halt["session"],
        "session_id": halt["session_id"],
        "halted": True,
    }


def prove_claude_builder_admission(
    observation: Mapping[str, Any],
    *,
    expected_session: str,
    expected_session_id: str,
    expected_workspace: Mapping[str, Any],
    expected_receipt: Optional[Mapping[str, Any]] = None,
    requested_model: Optional[str] = None,
    expected_observed_model: Optional[str] = None,
    expected_result_state: Optional[str] = None,
    expected_result_id: Optional[str] = None,
    require_halt: bool = False,
) -> Dict[str, Any]:
    """Admit Claude as a builder from one current observation and receipt."""

    observation = validate_claude_builder_observation(observation)
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
        expected_session_id=expected_session_id,
    )
    halt = None
    if require_halt or observation.get("halt") is not None:
        halt = prove_shutdown(
            observation,
            expected_session=expected_session,
            expected_session_id=expected_session_id,
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
        "authority_blockers": list(CLAUDE_LAUNCH_AUTHORITY_BLOCKERS),
        "launch_authorized": False,
        "live_claude_claimed": False,
    }


def session_record_from_observation(
    observation: Mapping[str, Any],
    *,
    record_state: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a caller-projection record. Does not persist a tmux session."""

    observation = validate_claude_builder_observation(observation)
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
    """Preserve stage-2 worker/controller/halt distinctions on Claude admission."""

    record = session_record_from_observation(
        observation, record_state=record_state
    )
    if halt_confirmed is None:
        halt_confirmed = record["state"] == "HALTED"
    return caller_projection(
        record, transport_id=BOUND_TRANSPORT, halt_confirmed=halt_confirmed
    )


def qualify_claude_builder_lifecycle(
    observation: Mapping[str, Any],
    *,
    expected_session: str,
    expected_session_id: str,
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
    """Qualify the deterministic Claude builder lifecycle. Never claims a live run."""

    observation = validate_claude_builder_observation(observation)
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
            expected_session_id=expected_session_id,
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
            expected_session_id=expected_session_id,
        )
        if halt_state != "confirmed":
            _raise_identity(
                "session_identity_mismatch",
                "Claude confirmed halt is missing",
            )
    final = fields["final_outcome"]
    if halt_proof is None and acceptance == "none":
        if final is not None:
            raise ValidationError("Claude final outcome is not bounded")
    elif final is None:
        raise ValidationError("Claude final outcome is missing")
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
        raise ValidationError("Claude builder lifecycle phases do not match schema")
    return {
        "schema": LIFECYCLE_SCHEMA,
        "target": TARGET,
        "transport": BOUND_TRANSPORT,
        "phases": phases,
        "phase_order": list(LIFECYCLE_PHASES),
        "caller_outcome": fields["caller_outcome"],
        "progress_cursor": fields["progress_cursor"],
        "live_claude_claimed": False,
    }


def require_live_claude_builder(observation: Optional[Mapping[str, Any]] = None) -> None:
    """Fail closed. Builder admission never opens a live Claude process."""

    if observation is not None:
        validate_claude_builder_observation(observation)
    raise UnsupportedError(
        CLAUDE_LAUNCH_AUTHORITY_BLOCKER,
        blocker=_blocker("claude_launch_authority", CLAUDE_LAUNCH_AUTHORITY_BLOCKER),
    )


class ClaudeBuilderAdmissionFixture:
    """Deterministic Claude builder observation. Never starts a live Claude process."""

    def __init__(self, observation: Optional[Mapping[str, Any]] = None):
        self._observation = (
            dict(observation) if observation is not None else fixture_observation()
        )

    @staticmethod
    def available() -> bool:
        return False

    def observation(self) -> Dict[str, Any]:
        return validate_claude_builder_observation(self._observation)


class ClaudeBuilderAdmissionController:
    """Structured Claude builder admission. Never constructs a live Claude runtime."""

    def __init__(
        self,
        registry_root: Path,
        *,
        observer: Optional[Mapping[str, Any]] = None,
        fixture: Optional[ClaudeBuilderAdmissionFixture] = None,
    ):
        self.registry_root = Path(registry_root)
        self.observer = observer
        self.fixture = fixture

    @staticmethod
    def available() -> bool:
        """Live Claude is not claimed. Fixtures do not make this true."""

        return False

    def require_observation(self) -> Dict[str, Any]:
        if self.fixture is not None:
            if self.fixture.available():
                _raise_unsupported(
                    "claude_builder_unavailable",
                    "Claude builder fixture must stay fail-closed",
                    remedy="keep the live Claude gate closed; do not treat a fixture as a live process",
                )
            return self.fixture.observation()
        if self.observer is None:
            _raise_unsupported(
                "claude_builder_unavailable",
                "Claude builder observation is unavailable",
                remedy=(
                    "supply a deterministic Claude builder fixture after paired "
                    "qualification; do not fall back to tmux, agy-print, "
                    "cursor-acp, or generic acp"
                ),
            )
        return validate_claude_builder_observation(self.observer)

    def admit(
        self,
        *,
        expected_session: str,
        expected_session_id: str,
        expected_workspace: Mapping[str, Any],
        expected_receipt: Optional[Mapping[str, Any]] = None,
        requested_model: Optional[str] = None,
        expected_observed_model: Optional[str] = None,
        expected_result_state: Optional[str] = None,
        expected_result_id: Optional[str] = None,
        require_halt: bool = False,
    ) -> Dict[str, Any]:
        return prove_claude_builder_admission(
            self.require_observation(),
            expected_session=expected_session,
            expected_session_id=expected_session_id,
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
        expected_session_id: str,
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
        return qualify_claude_builder_lifecycle(
            self.require_observation(),
            expected_session=expected_session,
            expected_session_id=expected_session_id,
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
        expected_session_id: str,
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
            expected_session_id=expected_session_id,
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
            expected_session_id=expected_session_id,
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
            "live_claude_claimed": False,
            "claude_admission": admitted,
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
        "qualification_schema": PAIR_SCHEMA,
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
    receipt["fingerprint"] = fingerprint or claude_builder_receipt_fingerprint(receipt)
    return receipt


def fixture_observation(
    *,
    session: str = "claude-builder-session",
    session_id: str = "8c2d4e16-7a91-4b30-9e5f-1d6a3c8b0472",
    requested_model: str = CURRENT_DEFAULT_SELECTION,
    observed_model: str = "claude-sonnet-4-6",
    observed_source: str = "runtime_metadata",
    resolved_identity: Optional[str] = None,
    runtime_model: Optional[str] = None,
    version: str = CLAUDE_VERSION,
    version_sha256: str = CLAUDE_VERSION_OBSERVATION_SHA256,
    workspace_path: str = "/tmp/claude-builder-workspace",
    branch: str = "codex/example",
    head: str = "a" * 40,
    tree: str = "b" * 40,
    terminal_state: str = "completed",
    exit_code: Optional[int] = 0,
    result_id: Optional[str] = "claude-result-1",
    halt: Optional[Mapping[str, Any]] = None,
    qualification_receipt: Optional[Mapping[str, Any]] = None,
    last_checkpoint: Optional[Mapping[str, Any]] = None,
    last_beacon: Optional[Mapping[str, Any]] = None,
    last_validated_at: Optional[str] = None,
    record_state: Optional[str] = None,
    transport: str = BOUND_TRANSPORT,
    target: str = TARGET,
) -> Dict[str, Any]:
    """Deterministic body-free fixture. Not a live Claude run."""

    identity = resolved_identity if resolved_identity is not None else observed_model
    return {
        "schema": OBSERVATION_SCHEMA,
        "target": target,
        "transport": transport,
        "requested_model": requested_model,
        "observed_model": {
            "id": observed_model,
            "source": observed_source,
            "resolved_identity": identity,
        },
        "workspace": {
            "path": workspace_path,
            "branch": branch,
            "head": head,
            "tree": tree,
        },
        "session": {"id": session, "session_id": session_id},
        "terminal_result": {
            "state": terminal_state,
            "exit_code": exit_code,
            "result_id": result_id,
        },
        "runtime": {
            "model_id": runtime_model or observed_model,
            "version": version,
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
    "CLAUDE_LAUNCH_AUTHORITY_BLOCKER",
    "CLAUDE_LAUNCH_AUTHORITY_BLOCKERS",
    "ClaudeBuilderAdmissionController",
    "ClaudeBuilderAdmissionFixture",
    "LIFECYCLE_SCHEMA",
    "OBSERVATION_SCHEMA",
    "RECEIPT_SCHEMA",
    "TARGET",
    "caller_fields_from_observation",
    "claude_builder_receipt_fingerprint",
    "fixture_observation",
    "fixture_receipt",
    "prove_claude_builder_admission",
    "prove_observed_model",
    "prove_qualification_receipt",
    "prove_session_identity",
    "prove_shutdown",
    "prove_terminal_result",
    "prove_workspace_binding",
    "qualify_claude_builder_lifecycle",
    "require_claude_builder_target",
    "require_live_claude_builder",
    "validate_claude_builder_observation",
    "validate_claude_builder_receipt",
]
