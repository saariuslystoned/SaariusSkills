"""Named AGY structured transport with exact observed-identity proof.

`agy-print` is a Puppet-owned structured transport. It never falls back to
tmux, Herdr, or ACP. Model, workspace, session, resume, and process-tree
claims come from observed runtime/process/session metadata, not from a
requested selector or path alone. Lifecycle qualification is deterministic:
start/bind, matching resume, terminal result, distinct worker/controller/halt
outcomes, and confined process-tree shutdown. Live AGY is not claimed; tests
inject observation and process-identity fixtures. `available()` stays false.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from .caller import (
    caller_projection,
    make_blocker,
)
from .errors import IdentityError, UnsupportedError, ValidationError
from .safety import validate_identifier


TRANSPORT_ID = "agy-print"
OBSERVATION_SCHEMA = "puppet.agy-print-observation/v1"
BINDING_SCHEMA = "puppet.agy-print-binding/v1"
RESUME_SCHEMA = "puppet.agy-print-resume-identity/v1"
HALT_SCHEMA = "puppet.agy-print-halt-proof/v1"
LIFECYCLE_SCHEMA = "puppet.agy-print-lifecycle/v1"
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
    {"runtime_metadata", "process_metadata", "session_metadata"}
)
TERMINAL_STATES = frozenset({"active", "completed", "failed", "halted"})
_OBSERVATION_KEYS = frozenset(
    {
        "schema",
        "transport",
        "requested_model",
        "observed_model",
        "workspace",
        "session",
        "terminal_result",
        "process",
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
_TERMINAL_KEYS = frozenset({"state", "exit_code"})
_PROCESS_KEYS = frozenset(
    {"pid", "kernel_birth_id", "command", "owned_children"}
)
_HALT_KEYS = frozenset(
    {"pid", "kernel_birth_id", "pid_gone", "signaled_pids"}
)


def _blocker(code: str, detail: str, **identity: Any) -> Dict[str, Any]:
    return make_blocker(code=code, detail=detail, **identity)


def _raise_identity(code: str, detail: str, **identity: Any) -> None:
    raise IdentityError(detail, blocker=_blocker(code, detail, **identity))


def _raise_unavailable(detail: str) -> None:
    raise UnsupportedError(
        detail,
        blocker=_blocker("transport_unavailable", detail),
    )


def _identity_pair(value: Mapping[str, Any], *, label: str) -> Tuple[int, str]:
    pid = value.get("pid")
    birth = value.get("kernel_birth_id")
    if (
        isinstance(pid, bool)
        or not isinstance(pid, int)
        or pid <= 1
        or not isinstance(birth, str)
        or not birth.strip()
    ):
        raise ValidationError("%s process identity is invalid" % label)
    return pid, birth


def owned_identity_map(
    process: Mapping[str, Any],
    *,
    label: str = "agy-print",
) -> Dict[int, str]:
    """Index owned pid->birth. Duplicate or colliding PIDs fail closed."""

    mapping: Dict[int, str] = {}
    pairs = [(_identity_pair(process, label="%s process" % label), "process")]
    children = process.get("owned_children") or []
    if not isinstance(children, list):
        raise ValidationError("%s owned children are invalid" % label)
    for child in children:
        if not isinstance(child, Mapping):
            raise ValidationError("%s owned child is invalid" % label)
        pairs.append((_identity_pair(child, label="%s owned child" % label), "child"))
    for (pid, birth), _kind in pairs:
        if pid in mapping:
            _raise_identity(
                "process_identity_mismatch",
                "%s owned process identity is ambiguous" % label,
                pid=pid,
                kernel_birth_id=birth,
            )
        mapping[pid] = birth
    return mapping


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


def validate_agy_print_observation(value: Any) -> Dict[str, Any]:
    """Return one body-safe structured AGY observation. No pane or transcript."""

    if not isinstance(value, Mapping) or set(value) != _OBSERVATION_KEYS:
        raise ValidationError("agy-print observation fields do not match schema")
    if value.get("schema") != OBSERVATION_SCHEMA:
        raise ValidationError("agy-print observation schema is invalid")
    if value.get("transport") != TRANSPORT_ID:
        raise IdentityError(
            "agy-print observation is bound to a different transport",
            blocker=_blocker(
                "identity_mismatch",
                "agy-print observation is bound to a different transport",
            ),
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
            raise ValidationError("agy-print observed model fields are invalid")
        observed_model = {
            "id": _bounded_text(observed_model.get("id"), label="observed model", maximum=200),
            "source": _bounded_text(
                observed_model.get("source"),
                label="observed model source",
                maximum=80,
            ),
        }
    workspace = value.get("workspace")
    if not isinstance(workspace, Mapping) or set(workspace) != _WORKSPACE_KEYS:
        raise ValidationError("agy-print workspace fields are invalid")
    workspace = {
        "path": _bounded_text(workspace.get("path"), label="workspace path", maximum=1024),
        "branch": _bounded_text(workspace.get("branch"), label="workspace branch", maximum=200),
        "head": _bounded_text(workspace.get("head"), label="workspace head", maximum=64),
        "tree": _bounded_text(workspace.get("tree"), label="workspace tree", maximum=64),
    }
    session = value.get("session")
    if not isinstance(session, Mapping) or set(session) != _SESSION_KEYS:
        raise ValidationError("agy-print session fields are invalid")
    session = {
        "id": validate_identifier(session.get("id"), "agy-print session"),
        "conversation_id": validate_identifier(
            session.get("conversation_id"), "agy-print conversation"
        ),
    }
    terminal = value.get("terminal_result")
    if not isinstance(terminal, Mapping) or set(terminal) != _TERMINAL_KEYS:
        raise ValidationError("agy-print terminal result fields are invalid")
    state = terminal.get("state")
    if state not in TERMINAL_STATES:
        raise ValidationError("agy-print terminal result state is invalid")
    terminal = {
        "state": state,
        "exit_code": _optional_int(terminal.get("exit_code"), label="terminal exit code"),
    }
    process = value.get("process")
    if not isinstance(process, Mapping) or set(process) != _PROCESS_KEYS:
        raise ValidationError("agy-print process fields are invalid")
    children = process.get("owned_children")
    if not isinstance(children, list) or len(children) > 32:
        raise ValidationError("agy-print owned children are invalid")
    owned_children = []
    for child in children:
        if not isinstance(child, Mapping):
            raise ValidationError("agy-print owned child is invalid")
        owned_children.append(
            {
                "pid": _optional_int(child.get("pid"), label="owned child pid", minimum=2),
                "kernel_birth_id": _bounded_text(
                    child.get("kernel_birth_id"),
                    label="owned child birth",
                    maximum=200,
                ),
            }
        )
        if owned_children[-1]["pid"] is None:
            raise ValidationError("agy-print owned child pid is invalid")
    process = {
        "pid": _optional_int(process.get("pid"), label="process pid", minimum=2),
        "kernel_birth_id": _bounded_text(
            process.get("kernel_birth_id"),
            label="process birth",
            maximum=200,
        ),
        "command": _bounded_text(process.get("command"), label="process command", maximum=1024),
        "owned_children": owned_children,
    }
    if process["pid"] is None:
        raise ValidationError("agy-print process pid is invalid")
    owned_identity_map(process)
    halt = value.get("halt")
    if halt is not None:
        if not isinstance(halt, Mapping) or set(halt) != _HALT_KEYS:
            raise ValidationError("agy-print halt fields are invalid")
        signaled = halt.get("signaled_pids")
        if not isinstance(signaled, list) or len(signaled) > 32:
            raise ValidationError("agy-print signaled pids are invalid")
        halt = {
            "pid": _optional_int(halt.get("pid"), label="halt pid", minimum=2),
            "kernel_birth_id": _bounded_text(
                halt.get("kernel_birth_id"),
                label="halt birth",
                maximum=200,
            ),
            "pid_gone": halt.get("pid_gone") is True,
            "signaled_pids": [
                _optional_int(item, label="signaled pid", minimum=2) for item in signaled
            ],
        }
        if halt["pid"] is None or any(item is None for item in halt["signaled_pids"]):
            raise ValidationError("agy-print halt process identity is invalid")
    checkpoint = value.get("last_checkpoint")
    if checkpoint is not None:
        if not isinstance(checkpoint, Mapping) or "checkpoint_id" not in checkpoint:
            raise ValidationError("agy-print checkpoint is invalid")
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
            raise ValidationError("agy-print beacon is invalid")
        sequence = beacon.get("sequence")
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 0:
            raise ValidationError("agy-print beacon sequence is invalid")
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
        "requested_model": requested,
        "observed_model": observed_model,
        "workspace": workspace,
        "session": session,
        "terminal_result": terminal,
        "process": process,
        "halt": halt,
        "last_checkpoint": checkpoint,
        "last_beacon": beacon,
        "last_validated_at": validated_at,
        "record_state": record_state,
    }


def _runtime_haystack(observation: Mapping[str, Any]) -> str:
    process = observation["process"]
    session = observation["session"]
    parts = [
        process["command"],
        process["kernel_birth_id"],
        session["id"],
        session["conversation_id"],
    ]
    observed = observation.get("observed_model")
    if isinstance(observed, Mapping) and observed.get("source") in RUNTIME_MODEL_SOURCES:
        source = observed["source"]
        if source == "process_metadata":
            return process["command"]
        if source == "session_metadata":
            return " ".join((session["id"], session["conversation_id"]))
    return " ".join(parts)


def prove_observed_model(
    observation: Mapping[str, Any],
    *,
    requested_model: Optional[str] = None,
) -> Dict[str, Any]:
    """Prove the executed model from runtime metadata, not the selector."""

    observation = validate_agy_print_observation(observation)
    observed = observation.get("observed_model")
    if observed is None or observed.get("source") not in RUNTIME_MODEL_SOURCES:
        _raise_identity(
            "model_observation_selector_only",
            "requested selector is not observed model proof",
        )
    model_id = observed["id"]
    if model_id not in _runtime_haystack(observation):
        _raise_identity(
            "model_observation_selector_only",
            "observed model is missing from runtime process or session metadata",
        )
    expected = requested_model or observation.get("requested_model")
    if expected is not None and expected != model_id:
        _raise_identity(
            "model_observation_mismatch",
            "observed model does not match the requested selector",
        )
    return {
        "observed_model": model_id,
        "source": observed["source"],
        "requested_model": expected,
    }


def prove_workspace_binding(
    observation: Mapping[str, Any],
    *,
    expected_workspace: Mapping[str, Any],
) -> Dict[str, Any]:
    """Prove the exact bound workspace. A path alone is not enough."""

    observation = validate_agy_print_observation(observation)
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
            "agy-print workspace identity does not match the bound checkout",
        )
    return dict(workspace)


def prove_terminal_result(observation: Mapping[str, Any]) -> Dict[str, Any]:
    """Prove the worker terminal/result state from structured observation."""

    observation = validate_agy_print_observation(observation)
    terminal = observation["terminal_result"]
    if terminal["state"] not in TERMINAL_STATES:
        raise ValidationError("agy-print terminal result state is invalid")
    return dict(terminal)


def prove_resume_identity(
    observation: Mapping[str, Any],
    *,
    expected_session: str,
    expected_conversation_id: str,
) -> Dict[str, Any]:
    """Prove matching conversation/session identity. Selector or path is not resume."""

    observation = validate_agy_print_observation(observation)
    session = observation["session"]
    if (
        not expected_session
        or not expected_conversation_id
        or session["id"] != expected_session
        or session["conversation_id"] != expected_conversation_id
    ):
        _raise_identity(
            "session_identity_mismatch",
            "agy-print resume requires matching session and conversation identity",
        )
    return {
        "schema": RESUME_SCHEMA,
        "session": session["id"],
        "conversation_id": session["conversation_id"],
        "resume_proved": True,
    }


def prove_process_tree(
    observation: Mapping[str, Any],
    *,
    expected_process: Mapping[str, Any],
    process_table: Optional["ProcessIdentityFixture"] = None,
) -> Dict[str, Any]:
    """Prove exact owned pid and birth. Do not accept a foreign process."""

    observation = validate_agy_print_observation(observation)
    process = observation["process"]
    owned = owned_identity_map(process)
    expected_pid = expected_process.get("pid")
    expected_birth = expected_process.get("kernel_birth_id")
    if expected_pid != process["pid"] or expected_birth != process["kernel_birth_id"]:
        _raise_identity(
            "process_identity_mismatch",
            "agy-print process identity does not match the owned target",
            pid=process["pid"],
            kernel_birth_id=process["kernel_birth_id"],
        )
    expected_children = expected_process.get("owned_children")
    if expected_children is not None:
        expected_map = owned_identity_map(
            {
                "pid": expected_process.get("pid"),
                "kernel_birth_id": expected_process.get("kernel_birth_id"),
                "owned_children": expected_children,
            }
        )
        if expected_map != owned:
            _raise_identity(
                "process_identity_mismatch",
                "agy-print process identity does not match the owned target",
                pid=process["pid"],
                kernel_birth_id=process["kernel_birth_id"],
            )
    if process_table is not None:
        process_table.revalidate_owned_tree(
            {"pid": process["pid"], "kernel_birth_id": process["kernel_birth_id"]},
            list(process["owned_children"]),
        )
    return {
        "pid": process["pid"],
        "kernel_birth_id": process["kernel_birth_id"],
        "owned_children": list(process["owned_children"]),
    }


def prove_shutdown(
    observation: Mapping[str, Any],
    *,
    expected_process: Mapping[str, Any],
    process_table: Optional["ProcessIdentityFixture"] = None,
) -> Dict[str, Any]:
    """Prove exact owned-target halt. Do not broaden cleanup to other PIDs."""

    owned = prove_process_tree(
        observation,
        expected_process=expected_process,
        process_table=process_table,
    )
    observation = validate_agy_print_observation(observation)
    halt = observation.get("halt")
    if not isinstance(halt, Mapping):
        _raise_identity(
            "process_identity_mismatch",
            "agy-print halt proof is missing the owned process identity",
            pid=owned["pid"],
            kernel_birth_id=owned["kernel_birth_id"],
        )
    signaled = [item for item in halt["signaled_pids"] if item is not None]
    if len(signaled) != len(set(signaled)):
        _raise_identity(
            "process_identity_mismatch",
            "agy-print owned process identity is ambiguous",
            pid=owned["pid"],
            kernel_birth_id=owned["kernel_birth_id"],
        )
    allowed = owned_identity_map(
        {
            "pid": owned["pid"],
            "kernel_birth_id": owned["kernel_birth_id"],
            "owned_children": owned["owned_children"],
        }
    )
    if (
        halt["pid"] != owned["pid"]
        or halt["kernel_birth_id"] != owned["kernel_birth_id"]
        or halt["pid_gone"] is not True
        or set(signaled) - set(allowed)
    ):
        _raise_identity(
            "process_tree_unowned",
            "agy-print halt is not confined to the owned process tree",
            pid=owned["pid"],
            kernel_birth_id=owned["kernel_birth_id"],
        )
    signaled_identities = [
        {"pid": pid, "kernel_birth_id": allowed[pid]} for pid in signaled
    ]
    return {
        "schema": HALT_SCHEMA,
        "pid": owned["pid"],
        "kernel_birth_id": owned["kernel_birth_id"],
        "pid_gone": True,
        "signaled_pids": signaled,
        "signaled_identities": signaled_identities,
    }


def prove_agy_print_observation(
    observation: Mapping[str, Any],
    *,
    expected_session: str,
    expected_conversation_id: str,
    expected_workspace: Mapping[str, Any],
    expected_process: Optional[Mapping[str, Any]] = None,
    requested_model: Optional[str] = None,
    require_halt: bool = False,
    process_table: Optional["ProcessIdentityFixture"] = None,
) -> Dict[str, Any]:
    """Prove the full structured AGY identity set from one observation."""

    observation = validate_agy_print_observation(observation)
    model = prove_observed_model(observation, requested_model=requested_model)
    workspace = prove_workspace_binding(
        observation, expected_workspace=expected_workspace
    )
    terminal = prove_terminal_result(observation)
    resume = prove_resume_identity(
        observation,
        expected_session=expected_session,
        expected_conversation_id=expected_conversation_id,
    )
    process_expected = expected_process or observation["process"]
    process = prove_process_tree(
        observation,
        expected_process=process_expected,
        process_table=process_table,
    )
    halt = None
    if require_halt or observation.get("halt") is not None:
        halt = prove_shutdown(
            observation,
            expected_process=process_expected,
            process_table=process_table,
        )
    return {
        "schema": BINDING_SCHEMA,
        "transport": TRANSPORT_ID,
        "model": model,
        "workspace": workspace,
        "terminal_result": terminal,
        "resume": resume,
        "process": process,
        "halt": halt,
        "live_agy_claimed": False,
    }


def session_record_from_observation(
    observation: Mapping[str, Any],
    *,
    target: str = "agy",
    record_state: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a caller-projection record. Does not persist a tmux session."""

    observation = validate_agy_print_observation(observation)
    state = record_state or observation.get("record_state") or "ACTIVE"
    if observation["terminal_result"]["state"] == "halted" and state == "ACTIVE":
        state = "HALTED"
    return {
        "session": observation["session"]["id"],
        "target": target,
        "state": state,
        "process": {
            "pid": observation["process"]["pid"],
            "kernel_birth_id": observation["process"]["kernel_birth_id"],
        },
        "last_checkpoint": observation.get("last_checkpoint"),
        "last_beacon": observation.get("last_beacon"),
        "last_validated_at": observation.get("last_validated_at"),
        "transport": {"schema": "puppet.transport-binding/v1", "id": TRANSPORT_ID},
    }


def caller_fields_from_observation(
    observation: Mapping[str, Any],
    *,
    target: str = "agy",
    record_state: Optional[str] = None,
    halt_confirmed: Optional[bool] = None,
) -> Dict[str, Any]:
    """Preserve stage-2 worker/controller/halt distinctions on agy-print."""

    record = session_record_from_observation(
        observation, target=target, record_state=record_state
    )
    if halt_confirmed is None:
        halt_confirmed = record["state"] == "HALTED"
    return caller_projection(
        record, transport_id=TRANSPORT_ID, halt_confirmed=halt_confirmed
    )


class ProcessIdentityFixture:
    """Deterministic PID+birth table. Not a live OS or AGY process."""

    def __init__(self) -> None:
        self._live: Dict[int, Dict[str, Any]] = {}
        self._ambiguous: set[int] = set()
        self._signaled: List[Dict[str, Any]] = []

    def spawn(
        self,
        pid: int,
        kernel_birth_id: str,
        *,
        parent_pid: Optional[int] = None,
        command: str = "agy --print",
    ) -> Dict[str, Any]:
        if pid in self._ambiguous:
            _raise_identity(
                "process_identity_mismatch",
                "agy-print process identity is ambiguous",
                pid=pid,
                kernel_birth_id=kernel_birth_id,
            )
        if pid in self._live:
            _raise_identity(
                "process_identity_mismatch",
                "agy-print process identity is ambiguous",
                pid=pid,
                kernel_birth_id=kernel_birth_id,
            )
        record = {
            "pid": pid,
            "kernel_birth_id": kernel_birth_id,
            "parent_pid": parent_pid,
            "command": command,
        }
        self._live[pid] = record
        return dict(record)

    def vanish(self, pid: int) -> None:
        self._live.pop(pid, None)

    def reuse_pid(
        self,
        pid: int,
        new_kernel_birth_id: str,
        *,
        parent_pid: Optional[int] = None,
        command: str = "agy --print",
    ) -> Dict[str, Any]:
        """Replace the occupant. The prior birth becomes stale."""

        self._live.pop(pid, None)
        self._ambiguous.discard(pid)
        return self.spawn(
            pid,
            new_kernel_birth_id,
            parent_pid=parent_pid,
            command=command,
        )

    def mark_ambiguous(self, pid: int) -> None:
        self._ambiguous.add(pid)

    def current(self, pid: int) -> Optional[Dict[str, Any]]:
        if pid in self._ambiguous:
            _raise_identity(
                "process_identity_mismatch",
                "agy-print process identity is ambiguous",
                pid=pid,
            )
        record = self._live.get(pid)
        return None if record is None else dict(record)

    def revalidate(self, expected: Mapping[str, Any]) -> Dict[str, Any]:
        pid, birth = _identity_pair(expected, label="agy-print expected")
        if pid in self._ambiguous:
            _raise_identity(
                "process_identity_mismatch",
                "agy-print process identity is ambiguous",
                pid=pid,
                kernel_birth_id=birth,
            )
        current = self._live.get(pid)
        if current is None:
            _raise_identity(
                "process_identity_mismatch",
                "agy-print process identity is stale",
                pid=pid,
                kernel_birth_id=birth,
            )
        if current["kernel_birth_id"] != birth:
            _raise_identity(
                "process_identity_mismatch",
                "agy-print process identity changed",
                pid=pid,
                kernel_birth_id=current["kernel_birth_id"],
            )
        return dict(current)

    def revalidate_owned_tree(
        self,
        root: Mapping[str, Any],
        owned_children: Sequence[Mapping[str, Any]],
    ) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        pinned_root = self.revalidate(root)
        pinned_children = [self.revalidate(child) for child in owned_children]
        owned_pids = {pinned_root["pid"], *(child["pid"] for child in pinned_children)}
        extras = [
            record
            for record in self._live.values()
            if record.get("parent_pid") == pinned_root["pid"]
            and record["pid"] not in owned_pids
        ]
        if extras:
            _raise_identity(
                "process_tree_unowned",
                "agy-print halt is not confined to the owned process tree",
                pid=pinned_root["pid"],
                kernel_birth_id=pinned_root["kernel_birth_id"],
            )
        return pinned_root, pinned_children

    def signal_exact(
        self,
        expected: Mapping[str, Any],
        *,
        race: Optional[Callable[["ProcessIdentityFixture"], None]] = None,
    ) -> Dict[str, Any]:
        """Pin pid+birth, then signal only if that exact identity is still live."""

        pinned = self.revalidate(expected)
        if race is not None:
            race(self)
        current = None
        try:
            current = self.revalidate(pinned)
        except IdentityError:
            raise
        if (
            current["pid"] != pinned["pid"]
            or current["kernel_birth_id"] != pinned["kernel_birth_id"]
        ):
            _raise_identity(
                "process_identity_mismatch",
                "agy-print process identity is stale",
                pid=pinned["pid"],
                kernel_birth_id=pinned["kernel_birth_id"],
            )
        signaled = {
            "pid": pinned["pid"],
            "kernel_birth_id": pinned["kernel_birth_id"],
        }
        self._signaled.append(signaled)
        return dict(signaled)

    def signal_owned_tree(
        self,
        root: Mapping[str, Any],
        owned_children: Sequence[Mapping[str, Any]],
        *,
        signaled_pids: Optional[Sequence[int]] = None,
        race: Optional[Callable[["ProcessIdentityFixture"], None]] = None,
    ) -> List[Dict[str, Any]]:
        """Revalidate the whole owned tree, then signal only claimed identities."""

        pinned_root, pinned_children = self.revalidate_owned_tree(root, owned_children)
        child_by_pid = {child["pid"]: child for child in pinned_children}
        if signaled_pids is None:
            targets = [pinned_root, *pinned_children]
        else:
            if len(list(signaled_pids)) != len(set(signaled_pids)):
                _raise_identity(
                    "process_identity_mismatch",
                    "agy-print owned process identity is ambiguous",
                    pid=pinned_root["pid"],
                    kernel_birth_id=pinned_root["kernel_birth_id"],
                )
            targets = []
            for pid in signaled_pids:
                if pid == pinned_root["pid"]:
                    targets.append(pinned_root)
                elif pid in child_by_pid:
                    targets.append(child_by_pid[pid])
                else:
                    _raise_identity(
                        "process_tree_unowned",
                        "agy-print halt is not confined to the owned process tree",
                        pid=pinned_root["pid"],
                        kernel_birth_id=pinned_root["kernel_birth_id"],
                    )
        if race is not None:
            race(self)
        confirmed: List[Dict[str, Any]] = []
        for target in targets:
            confirmed.append(self.revalidate(target))
        signaled: List[Dict[str, Any]] = []
        for target in confirmed:
            record = {
                "pid": target["pid"],
                "kernel_birth_id": target["kernel_birth_id"],
            }
            self._signaled.append(record)
            signaled.append(dict(record))
        return signaled

    @property
    def signaled(self) -> List[Dict[str, Any]]:
        return [dict(item) for item in self._signaled]


def process_table_from_observation(
    observation: Mapping[str, Any],
) -> ProcessIdentityFixture:
    """Seed a fixture from one observation. Not a live AGY process."""

    observation = validate_agy_print_observation(observation)
    table = ProcessIdentityFixture()
    process = observation["process"]
    table.spawn(
        process["pid"],
        process["kernel_birth_id"],
        command=process["command"],
    )
    for child in process["owned_children"]:
        table.spawn(
            child["pid"],
            child["kernel_birth_id"],
            parent_pid=process["pid"],
        )
    return table


def qualify_agy_print_lifecycle(
    observation: Mapping[str, Any],
    *,
    expected_session: str,
    expected_conversation_id: str,
    expected_workspace: Mapping[str, Any],
    expected_process: Optional[Mapping[str, Any]] = None,
    requested_model: Optional[str] = None,
    require_halt: bool = False,
    process_table: Optional[ProcessIdentityFixture] = None,
    record_state: Optional[str] = None,
    halt_confirmed: Optional[bool] = None,
    race: Optional[Callable[[ProcessIdentityFixture], None]] = None,
) -> Dict[str, Any]:
    """Qualify the deterministic AGY lifecycle. Never claims a live AGY run."""

    observation = validate_agy_print_observation(observation)
    process_expected = expected_process or observation["process"]
    table = process_table
    if table is None:
        table = process_table_from_observation(observation)
    start = {
        "model": prove_observed_model(observation, requested_model=requested_model),
        "workspace": prove_workspace_binding(
            observation, expected_workspace=expected_workspace
        ),
        "process": prove_process_tree(
            observation,
            expected_process=process_expected,
            process_table=table,
        ),
    }
    resume = prove_resume_identity(
        observation,
        expected_session=expected_session,
        expected_conversation_id=expected_conversation_id,
    )
    terminal = prove_terminal_result(observation)
    if halt_confirmed is None:
        halt_confirmed = observation.get("halt") is not None or require_halt
    fields = caller_fields_from_observation(
        observation,
        record_state=record_state,
        halt_confirmed=halt_confirmed if (require_halt or observation.get("halt")) else False,
    )
    worker = fields["caller_outcome"]["worker_completion"]
    acceptance = fields["caller_outcome"]["controller_acceptance"]
    halt_state = fields["caller_outcome"]["halt"]
    halt_proof = None
    if require_halt or observation.get("halt") is not None:
        halt_proof = prove_shutdown(
            observation,
            expected_process=process_expected,
            process_table=table,
        )
        table.signal_owned_tree(
            {
                "pid": halt_proof["pid"],
                "kernel_birth_id": halt_proof["kernel_birth_id"],
            },
            start["process"]["owned_children"],
            signaled_pids=halt_proof["signaled_pids"],
            race=race,
        )
        halt_proof = dict(halt_proof, signaled_identities=list(table.signaled))
        if halt_state != "confirmed":
            _raise_identity(
                "process_identity_mismatch",
                "agy-print confirmed halt is missing",
                pid=halt_proof["pid"],
                kernel_birth_id=halt_proof["kernel_birth_id"],
            )
    final = fields["final_outcome"]
    if halt_proof is None and acceptance == "none":
        if final is not None:
            raise ValidationError("agy-print final outcome is not bounded")
    elif final is None:
        raise ValidationError("agy-print final outcome is missing")
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
        raise ValidationError("agy-print lifecycle phases do not match schema")
    return {
        "schema": LIFECYCLE_SCHEMA,
        "transport": TRANSPORT_ID,
        "phases": phases,
        "phase_order": list(LIFECYCLE_PHASES),
        "caller_outcome": fields["caller_outcome"],
        "progress_cursor": fields["progress_cursor"],
        "live_agy_claimed": False,
    }


class AgyPrintController:
    """Structured AGY transport. Never constructs or falls back to tmux."""

    def __init__(
        self,
        registry_root: Path,
        *,
        observer: Optional[Mapping[str, Any]] = None,
        _observer: Optional[Mapping[str, Any]] = None,
    ):
        self.registry_root = Path(registry_root)
        self.observer = observer if observer is not None else _observer

    @staticmethod
    def available() -> bool:
        """Live AGY is not claimed. Fixtures do not make this true."""

        return False

    def require_observation(self) -> Dict[str, Any]:
        if self.observer is None:
            _raise_unavailable(
                "agy-print structured observation is unavailable"
            )
        return validate_agy_print_observation(self.observer)

    def prove(
        self,
        *,
        expected_session: str,
        expected_conversation_id: str,
        expected_workspace: Mapping[str, Any],
        expected_process: Optional[Mapping[str, Any]] = None,
        requested_model: Optional[str] = None,
        require_halt: bool = False,
        process_table: Optional[ProcessIdentityFixture] = None,
    ) -> Dict[str, Any]:
        return prove_agy_print_observation(
            self.require_observation(),
            expected_session=expected_session,
            expected_conversation_id=expected_conversation_id,
            expected_workspace=expected_workspace,
            expected_process=expected_process,
            requested_model=requested_model,
            require_halt=require_halt,
            process_table=process_table,
        )

    def qualify_lifecycle(
        self,
        *,
        expected_session: str,
        expected_conversation_id: str,
        expected_workspace: Mapping[str, Any],
        expected_process: Optional[Mapping[str, Any]] = None,
        requested_model: Optional[str] = None,
        require_halt: bool = False,
        process_table: Optional[ProcessIdentityFixture] = None,
        record_state: Optional[str] = None,
        halt_confirmed: Optional[bool] = None,
        race: Optional[Callable[[ProcessIdentityFixture], None]] = None,
    ) -> Dict[str, Any]:
        return qualify_agy_print_lifecycle(
            self.require_observation(),
            expected_session=expected_session,
            expected_conversation_id=expected_conversation_id,
            expected_workspace=expected_workspace,
            expected_process=expected_process,
            requested_model=requested_model,
            require_halt=require_halt,
            process_table=process_table,
            record_state=record_state,
            halt_confirmed=halt_confirmed,
            race=race,
        )

    def caller_result(
        self,
        *,
        expected_session: str,
        expected_conversation_id: str,
        expected_workspace: Mapping[str, Any],
        expected_process: Optional[Mapping[str, Any]] = None,
        requested_model: Optional[str] = None,
        target: str = "agy",
        record_state: Optional[str] = None,
        require_halt: bool = False,
        process_table: Optional[ProcessIdentityFixture] = None,
    ) -> Dict[str, Any]:
        observation = self.require_observation()
        proved = self.prove(
            expected_session=expected_session,
            expected_conversation_id=expected_conversation_id,
            expected_workspace=expected_workspace,
            expected_process=expected_process,
            requested_model=requested_model,
            require_halt=require_halt,
            process_table=process_table,
        )
        lifecycle = self.qualify_lifecycle(
            expected_session=expected_session,
            expected_conversation_id=expected_conversation_id,
            expected_workspace=expected_workspace,
            expected_process=expected_process,
            requested_model=requested_model,
            require_halt=require_halt,
            process_table=process_table,
            record_state=record_state,
        )
        fields = caller_fields_from_observation(
            observation,
            target=target,
            record_state=record_state,
            halt_confirmed=proved["halt"] is not None,
        )
        return {
            "ok": True,
            "session": expected_session,
            "state": fields["caller_outcome"]["halt"] == "confirmed"
            and "HALTED"
            or (record_state or observation.get("record_state") or "ACTIVE"),
            "live_agy_claimed": False,
            "agy_print": proved,
            "lifecycle": lifecycle,
            **fields,
        }


def fixture_observation(
    *,
    session: str = "agy-print-session",
    conversation_id: str = "conv-agy-print-1",
    requested_model: str = "gemini-3.7-flash-high",
    observed_model: str = "gemini-3.7-flash-high",
    observed_source: str = "process_metadata",
    workspace_path: str = "/tmp/agy-print-workspace",
    branch: str = "codex/example",
    head: str = "a" * 40,
    tree: str = "b" * 40,
    command: Optional[str] = None,
    pid: int = 4242,
    kernel_birth_id: str = "darwin:100:00004242",
    owned_children: Optional[Sequence[Mapping[str, Any]]] = None,
    terminal_state: str = "completed",
    exit_code: Optional[int] = 0,
    halt: Optional[Mapping[str, Any]] = None,
    last_checkpoint: Optional[Mapping[str, Any]] = None,
    last_beacon: Optional[Mapping[str, Any]] = None,
    last_validated_at: Optional[str] = None,
    record_state: Optional[str] = None,
) -> Dict[str, Any]:
    """Deterministic body-free fixture. Not a live AGY run."""

    if command is None:
        command = "agy --model %s --print" % observed_model
    return {
        "schema": OBSERVATION_SCHEMA,
        "transport": TRANSPORT_ID,
        "requested_model": requested_model,
        "observed_model": {"id": observed_model, "source": observed_source},
        "workspace": {
            "path": workspace_path,
            "branch": branch,
            "head": head,
            "tree": tree,
        },
        "session": {"id": session, "conversation_id": conversation_id},
        "terminal_result": {"state": terminal_state, "exit_code": exit_code},
        "process": {
            "pid": pid,
            "kernel_birth_id": kernel_birth_id,
            "command": command,
            "owned_children": list(owned_children or []),
        },
        "halt": None if halt is None else dict(halt),
        "last_checkpoint": last_checkpoint,
        "last_beacon": last_beacon,
        "last_validated_at": last_validated_at,
        "record_state": record_state,
    }
