"""Named Cursor ACP transport with exact observed-identity proof.

`cursor-acp` is a Puppet-owned Cursor-only ACP adapter/transport. It never
falls back to tmux, agy-print, Herdr, or generic `acp`. Generic `acp` stays
unsupported for every target, including Cursor. Model, workspace, ACP
session/conversation, and terminal/result claims come from observed runtime
metadata, not from a requested selector or path alone. Live Cursor ACP is
not claimed; tests inject a deterministic observation/runner fixture.
`available()` stays false.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence

from .caller import caller_projection, make_blocker
from .errors import IdentityError, UnsupportedError, ValidationError
from .safety import validate_identifier


TRANSPORT_ID = "cursor-acp"
GENERIC_ACP_ID = "acp"
TARGET = "cursor"
OBSERVATION_SCHEMA = "puppet.cursor-acp-observation/v1"
BINDING_SCHEMA = "puppet.cursor-acp-binding/v1"
RESUME_SCHEMA = "puppet.cursor-acp-resume-identity/v1"
HALT_SCHEMA = "puppet.cursor-acp-halt-proof/v1"
LIFECYCLE_SCHEMA = "puppet.cursor-acp-lifecycle/v1"
LIFECYCLE_PHASES = (
    "start_bound",
    "resume_matched",
    "terminal_result",
    "worker_completion",
    "controller_acceptance",
    "confirmed_halt",
    "final_outcome",
)

RUNTIME_MODEL_SOURCES = frozenset(
    {"runtime_metadata", "session_metadata", "acp_runtime_metadata"}
)
TERMINAL_STATES = frozenset({"active", "completed", "failed", "halted"})
MODEL_CATALOG_SCHEMA = "puppet.cursor-acp-model-catalog/v1"
_CURSOR_SELECTOR_RE = re.compile(r"^cursor-grok-4\.6-(low|medium|high|xhigh)$")
_PARAMETERIZED_RUNTIME_RE = re.compile(r"^(?:cursor-)?grok-4\.6\[(.+)\]$")
FALLBACK_OR_DEFAULT_MODEL_IDS = frozenset(
    {"default", "fallback", "auto", "unavailable", "current_default"}
)
VERIFIED_CURSOR_ACP_CATALOG = {
    "schema": MODEL_CATALOG_SCHEMA,
    "verified": True,
    "advertised_model_ids": (
        "grok-4.6[effort=low,fast=true]",
        "grok-4.6[effort=medium,fast=true]",
        "grok-4.6[effort=high,fast=true]",
        "grok-4.6[effort=xhigh,fast=true]",
    ),
}
_OBSERVATION_KEYS = frozenset(
    {
        "schema",
        "transport",
        "target",
        "requested_model",
        "observed_model",
        "workspace",
        "session",
        "terminal_result",
        "runtime",
        "halt",
        "last_checkpoint",
        "last_beacon",
        "last_validated_at",
        "record_state",
    }
)
_OBSERVED_MODEL_KEYS = frozenset({"id", "source"})
_WORKSPACE_KEYS = frozenset({"path", "branch", "head", "tree"})
_SESSION_KEYS = frozenset({"id", "conversation_id"})
_TERMINAL_KEYS = frozenset({"state", "exit_code", "result_id"})
_RUNTIME_KEYS = frozenset({"model_id"})
_HALT_KEYS = frozenset({"session", "conversation_id", "halted"})


def _blocker(code: str, detail: str, **identity: Any) -> Dict[str, Any]:
    return make_blocker(code=code, detail=detail, **identity)


def _raise_identity(code: str, detail: str, **identity: Any) -> None:
    raise IdentityError(detail, blocker=_blocker(code, detail, **identity))


def _raise_unavailable(detail: str) -> None:
    raise UnsupportedError(
        detail,
        blocker=_blocker("transport_unavailable", detail),
    )


def _raise_unsupported(code: str, detail: str) -> None:
    raise UnsupportedError(detail, blocker=_blocker(code, detail))


def require_cursor_acp_target(target: Any) -> str:
    """Generic ACP is never a Cursor transport. Non-Cursor targets refuse."""

    if target != TARGET:
        _raise_unsupported(
            "transport_target_mismatch",
            "cursor-acp is valid only for the cursor target",
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


def validate_cursor_acp_observation(value: Any) -> Dict[str, Any]:
    """Return one body-safe structured Cursor ACP observation."""

    if not isinstance(value, Mapping) or set(value) != _OBSERVATION_KEYS:
        raise ValidationError("cursor-acp observation fields do not match schema")
    if value.get("schema") != OBSERVATION_SCHEMA:
        raise ValidationError("cursor-acp observation schema is invalid")
    transport = value.get("transport")
    if transport == GENERIC_ACP_ID:
        _raise_identity(
            "identity_mismatch",
            "generic acp is not a Cursor ACP transport",
        )
    if transport != TRANSPORT_ID:
        _raise_identity(
            "identity_mismatch",
            "cursor-acp observation is bound to a different transport",
        )
    require_cursor_acp_target(value.get("target"))
    requested = value.get("requested_model")
    if requested is not None:
        requested = _bounded_text(requested, label="requested model", maximum=200)
    observed_model = value.get("observed_model")
    if observed_model is not None:
        if (
            not isinstance(observed_model, Mapping)
            or set(observed_model) != _OBSERVED_MODEL_KEYS
        ):
            raise ValidationError("cursor-acp observed model fields are invalid")
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
        raise ValidationError("cursor-acp workspace fields are invalid")
    workspace = {
        "path": _bounded_text(workspace.get("path"), label="workspace path", maximum=1024),
        "branch": _bounded_text(workspace.get("branch"), label="workspace branch", maximum=200),
        "head": _bounded_text(workspace.get("head"), label="workspace head", maximum=64),
        "tree": _bounded_text(workspace.get("tree"), label="workspace tree", maximum=64),
    }
    session = value.get("session")
    if not isinstance(session, Mapping) or set(session) != _SESSION_KEYS:
        raise ValidationError("cursor-acp session fields are invalid")
    session = {
        "id": validate_identifier(session.get("id"), "cursor-acp session"),
        "conversation_id": validate_identifier(
            session.get("conversation_id"), "cursor-acp conversation"
        ),
    }
    terminal = value.get("terminal_result")
    if not isinstance(terminal, Mapping) or set(terminal) != _TERMINAL_KEYS:
        raise ValidationError("cursor-acp terminal result fields are invalid")
    state = terminal.get("state")
    if state not in TERMINAL_STATES:
        raise ValidationError("cursor-acp terminal result state is invalid")
    result_id = terminal.get("result_id")
    if result_id is not None:
        result_id = validate_identifier(result_id, "cursor-acp result")
    terminal = {
        "state": state,
        "exit_code": _optional_int(terminal.get("exit_code"), label="terminal exit code"),
        "result_id": result_id,
    }
    runtime = value.get("runtime")
    if not isinstance(runtime, Mapping) or set(runtime) != _RUNTIME_KEYS:
        raise ValidationError("cursor-acp runtime fields are invalid")
    runtime = {
        "model_id": _bounded_text(
            runtime.get("model_id"), label="runtime model", maximum=200
        )
    }
    halt = value.get("halt")
    if halt is not None:
        if not isinstance(halt, Mapping) or set(halt) != _HALT_KEYS:
            raise ValidationError("cursor-acp halt fields are invalid")
        if halt.get("halted") is not True:
            raise ValidationError("cursor-acp halt state is invalid")
        halt = {
            "session": validate_identifier(halt.get("session"), "cursor-acp halt session"),
            "conversation_id": validate_identifier(
                halt.get("conversation_id"), "cursor-acp halt conversation"
            ),
            "halted": True,
        }
    checkpoint = value.get("last_checkpoint")
    if checkpoint is not None:
        if not isinstance(checkpoint, Mapping) or "checkpoint_id" not in checkpoint:
            raise ValidationError("cursor-acp checkpoint is invalid")
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
            raise ValidationError("cursor-acp beacon is invalid")
        sequence = beacon.get("sequence")
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 0:
            raise ValidationError("cursor-acp beacon sequence is invalid")
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
        "transport": TRANSPORT_ID,
        "target": TARGET,
        "requested_model": requested,
        "observed_model": observed_model,
        "workspace": workspace,
        "session": session,
        "terminal_result": terminal,
        "runtime": runtime,
        "halt": halt,
        "last_checkpoint": checkpoint,
        "last_beacon": beacon,
        "last_validated_at": validated_at,
        "record_state": record_state,
    }


def _verified_advertised_model_ids(
    catalog: Optional[Mapping[str, Any]] = None,
) -> Sequence[str]:
    raw = VERIFIED_CURSOR_ACP_CATALOG if catalog is None else catalog
    if (
        not isinstance(raw, Mapping)
        or raw.get("schema") != MODEL_CATALOG_SCHEMA
        or raw.get("verified") is not True
    ):
        _raise_identity(
            "model_observation_mismatch",
            "Cursor ACP model catalog is unverified",
        )
    advertised = raw.get("advertised_model_ids")
    if not isinstance(advertised, (tuple, list)) or not advertised:
        _raise_identity(
            "model_observation_mismatch",
            "requested Cursor ACP selector is unavailable",
        )
    model_ids = []
    for model_id in advertised:
        if not isinstance(model_id, str) or not model_id.strip():
            _raise_identity(
                "model_observation_mismatch",
                "Cursor ACP model catalog is unverified",
            )
        model_ids.append(model_id)
    return tuple(model_ids)


def _runtime_parameters(model_id: str) -> Optional[Dict[str, str]]:
    match = _PARAMETERIZED_RUNTIME_RE.fullmatch(model_id)
    if match is None:
        return None
    values: Dict[str, str] = {}
    for parameter in match.group(1).split(","):
        if "=" not in parameter:
            return None
        key, value = parameter.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key or not value:
            return None
        values[key] = value
    return values


def _is_cursor_selector(model_id: str) -> bool:
    return _CURSOR_SELECTOR_RE.fullmatch(model_id) is not None


def resolve_requested_cursor_model(
    requested_model: Optional[str],
    *,
    catalog: Optional[Mapping[str, Any]] = None,
) -> str:
    """Resolve one requested selector through the local verified catalog."""

    if not isinstance(requested_model, str) or not requested_model.strip():
        _raise_identity(
            "model_observation_mismatch",
            "requested Cursor ACP selector is unavailable",
        )
    requested = requested_model.strip()
    if requested in FALLBACK_OR_DEFAULT_MODEL_IDS:
        _raise_identity(
            "model_observation_mismatch",
            "Cursor ACP fallback or default model is not bound requested-model proof",
        )
    advertised = _verified_advertised_model_ids(catalog)
    if requested in advertised:
        return requested
    match = _CURSOR_SELECTOR_RE.fullmatch(requested)
    if match is None:
        _raise_identity(
            "model_observation_mismatch",
            "requested Cursor ACP selector is unavailable",
        )
    effort = match.group(1)
    candidates = []
    for model_id in advertised:
        parameters = _runtime_parameters(model_id)
        if (
            parameters is not None
            and parameters.get("effort") == effort
            and parameters.get("fast") == "true"
        ):
            candidates.append(model_id)
    if len(candidates) != 1:
        _raise_identity(
            "model_observation_mismatch",
            "requested Cursor ACP selector is unavailable",
        )
    return candidates[0]


def bind_expected_runtime_model(
    requested_model: Optional[str],
    *,
    catalog: Optional[Mapping[str, Any]] = None,
    expected_observed_model: Optional[str] = None,
) -> str:
    """Bind the catalog-resolved runtime model independently of observation."""

    bound = resolve_requested_cursor_model(requested_model, catalog=catalog)
    if expected_observed_model is not None and expected_observed_model != bound:
        _raise_identity(
            "model_observation_mismatch",
            "observed model does not match the bound Cursor ACP runtime",
        )
    return bound


def prove_observed_model(
    observation: Mapping[str, Any],
    *,
    requested_model: Optional[str] = None,
    expected_observed_model: Optional[str] = None,
    catalog: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Prove the executed ACP model against a catalog-bound runtime identity."""

    observation = validate_cursor_acp_observation(observation)
    observed = observation.get("observed_model")
    requested = requested_model or observation.get("requested_model")
    expected = bind_expected_runtime_model(
        requested,
        catalog=catalog,
        expected_observed_model=expected_observed_model,
    )
    if observed is None or observed.get("source") not in RUNTIME_MODEL_SOURCES:
        _raise_identity(
            "model_observation_selector_only",
            "requested selector is not observed model proof",
        )
    model_id = observed["id"]
    if model_id != observation["runtime"]["model_id"]:
        _raise_identity(
            "model_observation_selector_only",
            "observed model is missing from runtime ACP metadata",
        )
    if _is_cursor_selector(model_id) and model_id != expected:
        _raise_identity(
            "model_observation_selector_only",
            "requested selector is not observed model proof",
        )
    if model_id in FALLBACK_OR_DEFAULT_MODEL_IDS:
        _raise_identity(
            "model_observation_mismatch",
            "Cursor ACP fallback or default model is not bound requested-model proof",
        )
    advertised = _verified_advertised_model_ids(catalog)
    if model_id not in advertised:
        _raise_identity(
            "model_observation_mismatch",
            "observed Cursor ACP model is unverified",
        )
    if model_id != expected:
        _raise_identity(
            "model_observation_mismatch",
            "observed model does not match the bound Cursor ACP runtime",
        )
    return {
        "observed_model": model_id,
        "source": observed["source"],
        "requested_model": requested,
    }


def prove_workspace_binding(
    observation: Mapping[str, Any],
    *,
    expected_workspace: Mapping[str, Any],
) -> Dict[str, Any]:
    """Prove the exact bound workspace. A path alone is not enough."""

    observation = validate_cursor_acp_observation(observation)
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
            "cursor-acp workspace identity does not match the bound checkout",
        )
    return dict(workspace)


def prove_terminal_result(
    observation: Mapping[str, Any],
    *,
    expected_state: Optional[str] = None,
    expected_result_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Prove the worker terminal/result state from structured observation."""

    observation = validate_cursor_acp_observation(observation)
    terminal = observation["terminal_result"]
    if expected_state is not None and terminal["state"] != expected_state:
        _raise_identity(
            "result_identity_mismatch",
            "cursor-acp terminal result state does not match the bound result",
        )
    if (
        expected_result_id is not None
        and terminal["result_id"] != expected_result_id
    ):
        _raise_identity(
            "result_identity_mismatch",
            "cursor-acp terminal result identity does not match the bound result",
        )
    return dict(terminal)


def prove_resume_identity(
    observation: Mapping[str, Any],
    *,
    expected_session: str,
    expected_conversation_id: str,
) -> Dict[str, Any]:
    """Prove matching ACP session/conversation identity."""

    observation = validate_cursor_acp_observation(observation)
    session = observation["session"]
    if (
        not expected_session
        or not expected_conversation_id
        or session["id"] != expected_session
        or session["conversation_id"] != expected_conversation_id
    ):
        _raise_identity(
            "session_identity_mismatch",
            "cursor-acp resume requires matching session and conversation identity",
        )
    return {
        "schema": RESUME_SCHEMA,
        "session": session["id"],
        "conversation_id": session["conversation_id"],
        "resume_proved": True,
    }


def prove_shutdown(
    observation: Mapping[str, Any],
    *,
    expected_session: str,
    expected_conversation_id: str,
) -> Dict[str, Any]:
    """Prove exact ACP session halt. Do not accept a foreign session."""

    resume = prove_resume_identity(
        observation,
        expected_session=expected_session,
        expected_conversation_id=expected_conversation_id,
    )
    observation = validate_cursor_acp_observation(observation)
    halt = observation.get("halt")
    if not isinstance(halt, Mapping):
        _raise_identity(
            "session_identity_mismatch",
            "cursor-acp halt proof is missing the owned ACP session identity",
        )
    if (
        halt["session"] != resume["session"]
        or halt["conversation_id"] != resume["conversation_id"]
        or halt["halted"] is not True
    ):
        _raise_identity(
            "session_identity_mismatch",
            "cursor-acp halt is not confined to the owned ACP session",
        )
    return {
        "schema": HALT_SCHEMA,
        "session": halt["session"],
        "conversation_id": halt["conversation_id"],
        "halted": True,
    }


def prove_cursor_acp_observation(
    observation: Mapping[str, Any],
    *,
    expected_session: str,
    expected_conversation_id: str,
    expected_workspace: Mapping[str, Any],
    requested_model: Optional[str] = None,
    expected_observed_model: Optional[str] = None,
    expected_result_state: Optional[str] = None,
    expected_result_id: Optional[str] = None,
    require_halt: bool = False,
) -> Dict[str, Any]:
    """Prove the full structured Cursor ACP identity set from one observation."""

    observation = validate_cursor_acp_observation(observation)
    requested = (
        requested_model
        if requested_model is not None
        else observation.get("requested_model")
    )
    expected = bind_expected_runtime_model(
        requested, expected_observed_model=expected_observed_model
    )
    model = prove_observed_model(
        observation,
        requested_model=requested,
        expected_observed_model=expected,
    )
    workspace = prove_workspace_binding(
        observation, expected_workspace=expected_workspace
    )
    terminal = prove_terminal_result(
        observation,
        expected_state=expected_result_state,
        expected_result_id=expected_result_id,
    )
    resume = prove_resume_identity(
        observation,
        expected_session=expected_session,
        expected_conversation_id=expected_conversation_id,
    )
    halt = None
    if require_halt or observation.get("halt") is not None:
        halt = prove_shutdown(
            observation,
            expected_session=expected_session,
            expected_conversation_id=expected_conversation_id,
        )
    return {
        "schema": BINDING_SCHEMA,
        "transport": TRANSPORT_ID,
        "target": TARGET,
        "model": model,
        "workspace": workspace,
        "terminal_result": terminal,
        "resume": resume,
        "halt": halt,
        "live_cursor_acp_claimed": False,
    }


def session_record_from_observation(
    observation: Mapping[str, Any],
    *,
    record_state: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a caller-projection record. Does not persist a tmux session."""

    observation = validate_cursor_acp_observation(observation)
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
        "transport": {"schema": "puppet.transport-binding/v1", "id": TRANSPORT_ID},
    }


def caller_fields_from_observation(
    observation: Mapping[str, Any],
    *,
    record_state: Optional[str] = None,
    halt_confirmed: Optional[bool] = None,
) -> Dict[str, Any]:
    """Preserve stage-2 worker/controller/halt distinctions on cursor-acp."""

    record = session_record_from_observation(
        observation, record_state=record_state
    )
    if halt_confirmed is None:
        halt_confirmed = record["state"] == "HALTED"
    return caller_projection(
        record, transport_id=TRANSPORT_ID, halt_confirmed=halt_confirmed
    )


def qualify_cursor_acp_lifecycle(
    observation: Mapping[str, Any],
    *,
    expected_session: str,
    expected_conversation_id: str,
    expected_workspace: Mapping[str, Any],
    requested_model: Optional[str] = None,
    expected_observed_model: Optional[str] = None,
    expected_result_state: Optional[str] = None,
    expected_result_id: Optional[str] = None,
    require_halt: bool = False,
    record_state: Optional[str] = None,
    halt_confirmed: Optional[bool] = None,
) -> Dict[str, Any]:
    """Qualify the deterministic Cursor ACP lifecycle. Never claims a live run."""

    observation = validate_cursor_acp_observation(observation)
    requested = (
        requested_model
        if requested_model is not None
        else observation.get("requested_model")
    )
    expected = bind_expected_runtime_model(
        requested, expected_observed_model=expected_observed_model
    )
    start = {
        "model": prove_observed_model(
            observation,
            requested_model=requested,
            expected_observed_model=expected,
        ),
        "workspace": prove_workspace_binding(
            observation, expected_workspace=expected_workspace
        ),
        "session": prove_resume_identity(
            observation,
            expected_session=expected_session,
            expected_conversation_id=expected_conversation_id,
        ),
    }
    resume = start["session"]
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
            expected_conversation_id=expected_conversation_id,
        )
        if halt_state != "confirmed":
            _raise_identity(
                "session_identity_mismatch",
                "cursor-acp confirmed halt is missing",
            )
    final = fields["final_outcome"]
    if halt_proof is None and acceptance == "none":
        if final is not None:
            raise ValidationError("cursor-acp final outcome is not bounded")
    elif final is None:
        raise ValidationError("cursor-acp final outcome is missing")
    phases = {
        "start_bound": start,
        "resume_matched": resume,
        "terminal_result": terminal,
        "worker_completion": worker,
        "controller_acceptance": acceptance,
        "confirmed_halt": halt_proof,
        "final_outcome": final,
    }
    if tuple(phases) != LIFECYCLE_PHASES:
        raise ValidationError("cursor-acp lifecycle phases do not match schema")
    return {
        "schema": LIFECYCLE_SCHEMA,
        "transport": TRANSPORT_ID,
        "target": TARGET,
        "phases": phases,
        "phase_order": list(LIFECYCLE_PHASES),
        "caller_outcome": fields["caller_outcome"],
        "progress_cursor": fields["progress_cursor"],
        "live_cursor_acp_claimed": False,
    }


class CursorAcpRunnerFixture:
    """Deterministic ACP observation runner. Never starts a live Cursor process."""

    def __init__(self, observation: Optional[Mapping[str, Any]] = None):
        self._observation = (
            dict(observation) if observation is not None else fixture_observation()
        )

    @staticmethod
    def available() -> bool:
        return False

    def observation(self) -> Dict[str, Any]:
        return validate_cursor_acp_observation(self._observation)


class CursorAcpController:
    """Structured Cursor ACP transport. Never constructs tmux or agy-print."""

    def __init__(
        self,
        registry_root: Path,
        *,
        observer: Optional[Mapping[str, Any]] = None,
        _observer: Optional[Mapping[str, Any]] = None,
        runner: Optional[CursorAcpRunnerFixture] = None,
        _runner: Optional[CursorAcpRunnerFixture] = None,
    ):
        self.registry_root = Path(registry_root)
        self.observer = observer if observer is not None else _observer
        self.runner = runner if runner is not None else _runner

    @staticmethod
    def available() -> bool:
        """Live Cursor ACP is not claimed. Fixtures do not make this true."""

        return False

    def require_observation(self) -> Dict[str, Any]:
        if self.runner is not None:
            if self.runner.available():
                _raise_unsupported(
                    "transport_unavailable",
                    "cursor-acp runner fixture must stay fail-closed",
                )
            return self.runner.observation()
        if self.observer is None:
            _raise_unavailable("cursor-acp structured observation is unavailable")
        return validate_cursor_acp_observation(self.observer)

    def prove(
        self,
        *,
        expected_session: str,
        expected_conversation_id: str,
        expected_workspace: Mapping[str, Any],
        requested_model: Optional[str] = None,
        expected_observed_model: Optional[str] = None,
        expected_result_state: Optional[str] = None,
        expected_result_id: Optional[str] = None,
        require_halt: bool = False,
    ) -> Dict[str, Any]:
        return prove_cursor_acp_observation(
            self.require_observation(),
            expected_session=expected_session,
            expected_conversation_id=expected_conversation_id,
            expected_workspace=expected_workspace,
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
        expected_conversation_id: str,
        expected_workspace: Mapping[str, Any],
        requested_model: Optional[str] = None,
        expected_observed_model: Optional[str] = None,
        expected_result_state: Optional[str] = None,
        expected_result_id: Optional[str] = None,
        require_halt: bool = False,
        record_state: Optional[str] = None,
        halt_confirmed: Optional[bool] = None,
    ) -> Dict[str, Any]:
        return qualify_cursor_acp_lifecycle(
            self.require_observation(),
            expected_session=expected_session,
            expected_conversation_id=expected_conversation_id,
            expected_workspace=expected_workspace,
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
        expected_conversation_id: str,
        expected_workspace: Mapping[str, Any],
        requested_model: Optional[str] = None,
        expected_observed_model: Optional[str] = None,
        expected_result_state: Optional[str] = None,
        expected_result_id: Optional[str] = None,
        record_state: Optional[str] = None,
        require_halt: bool = False,
    ) -> Dict[str, Any]:
        observation = self.require_observation()
        requested = (
            requested_model
            if requested_model is not None
            else observation.get("requested_model")
        )
        expected = bind_expected_runtime_model(
            requested, expected_observed_model=expected_observed_model
        )
        proved = self.prove(
            expected_session=expected_session,
            expected_conversation_id=expected_conversation_id,
            expected_workspace=expected_workspace,
            requested_model=requested,
            expected_observed_model=expected,
            expected_result_state=expected_result_state,
            expected_result_id=expected_result_id,
            require_halt=require_halt,
        )
        lifecycle = self.qualify_lifecycle(
            expected_session=expected_session,
            expected_conversation_id=expected_conversation_id,
            expected_workspace=expected_workspace,
            requested_model=requested,
            expected_observed_model=expected,
            expected_result_state=expected_result_state,
            expected_result_id=expected_result_id,
            require_halt=require_halt,
            record_state=record_state,
        )
        fields = caller_fields_from_observation(
            observation,
            record_state=record_state,
            halt_confirmed=proved["halt"] is not None,
        )
        return {
            "ok": True,
            "session": expected_session,
            "state": fields["caller_outcome"]["halt"] == "confirmed"
            and "HALTED"
            or (record_state or observation.get("record_state") or "ACTIVE"),
            "live_cursor_acp_claimed": False,
            "cursor_acp": proved,
            "lifecycle": lifecycle,
            **fields,
        }


def fixture_observation(
    *,
    session: str = "cursor-acp-session",
    conversation_id: str = "conv-cursor-acp-1",
    requested_model: str = "cursor-grok-4.6-high",
    observed_model: str = "grok-4.6[effort=high,fast=true]",
    observed_source: str = "runtime_metadata",
    runtime_model: Optional[str] = None,
    workspace_path: str = "/tmp/cursor-acp-workspace",
    branch: str = "codex/example",
    head: str = "a" * 40,
    tree: str = "b" * 40,
    terminal_state: str = "completed",
    exit_code: Optional[int] = 0,
    result_id: Optional[str] = "acp-result-1",
    halt: Optional[Mapping[str, Any]] = None,
    last_checkpoint: Optional[Mapping[str, Any]] = None,
    last_beacon: Optional[Mapping[str, Any]] = None,
    last_validated_at: Optional[str] = None,
    record_state: Optional[str] = None,
    transport: str = TRANSPORT_ID,
    target: str = TARGET,
) -> Dict[str, Any]:
    """Deterministic body-free fixture. Not a live Cursor ACP run."""

    return {
        "schema": OBSERVATION_SCHEMA,
        "transport": transport,
        "target": target,
        "requested_model": requested_model,
        "observed_model": {"id": observed_model, "source": observed_source},
        "workspace": {
            "path": workspace_path,
            "branch": branch,
            "head": head,
            "tree": tree,
        },
        "session": {"id": session, "conversation_id": conversation_id},
        "terminal_result": {
            "state": terminal_state,
            "exit_code": exit_code,
            "result_id": result_id,
        },
        "runtime": {"model_id": runtime_model or observed_model},
        "halt": None if halt is None else dict(halt),
        "last_checkpoint": last_checkpoint,
        "last_beacon": last_beacon,
        "last_validated_at": last_validated_at,
        "record_state": record_state,
    }
