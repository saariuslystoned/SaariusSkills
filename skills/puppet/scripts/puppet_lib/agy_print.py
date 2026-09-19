"""Named AGY structured transport with exact observed-identity proof.

`agy-print` is a Puppet-owned structured transport. It never falls back to
tmux, Herdr, or ACP. The live path uses AGY's native ``--print`` /
``--input-format stream-json`` / ``--output-format stream-json`` interface
as advertised by the installed binary. Model, workspace, session, resume,
and process-tree claims come from observed runtime/process/session metadata,
not from a requested selector or path alone. Resume uses exact
``--conversation`` identity only; ``--continue`` is refused.

Lifecycle qualification remains deterministic: start/bind, matching resume,
terminal result, distinct worker/controller/halt outcomes, and confined
process-tree shutdown. Fixture helpers stay available for identity tests.
``available()`` follows the installed help probe and is never made true by
fixtures. Process-backed tests may use a task-owned fake executable; they
do not claim a live AGY public-controller run.
"""

from __future__ import annotations

import json
import os
import select
import shlex
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from .caller import (
    caller_projection,
    make_blocker,
)
from .contracts import Contract
from .errors import ConflictError, IdentityError, UnsupportedError, ValidationError
from .handoffs import validate_handoff
from .safety import (
    atomic_write_json,
    canonical_json_bytes,
    exclusive_lock,
    read_json,
    sha256_bytes,
    sha256_file,
    validate_identifier,
)


TRANSPORT_ID = "agy-print"
OBSERVATION_SCHEMA = "puppet.agy-print-observation/v1"
BINDING_SCHEMA = "puppet.agy-print-binding/v1"
RESUME_SCHEMA = "puppet.agy-print-resume-identity/v1"
HALT_SCHEMA = "puppet.agy-print-halt-proof/v1"
LIFECYCLE_SCHEMA = "puppet.agy-print-lifecycle/v1"
SESSION_STORE_SCHEMA = "puppet.agy-print-session/v1"
RUNTIME_PROBE_SCHEMA = "puppet.agy-print-runtime-probe/v1"
STREAM_JSON = "stream-json"
PRINT_FLAG = "--print"
PRINT_EQUALS = "--print="
INPUT_FORMAT_FLAG = "--input-format"
OUTPUT_FORMAT_FLAG = "--output-format"
CONVERSATION_FLAG = "--conversation"
CONTINUE_FLAG = "--continue"
MODEL_FLAG = "--model"
EFFORT_FLAG = "--effort"
DANGEROUS_PERMISSIONS_FLAG = "--dangerously-skip-permissions"
NEW_PROJECT_FLAG = "--new-project"
DISABLE_SLASH_COMMANDS_FLAG = "--disable-slash-commands"
LOG_FILE_FLAG = "--log-file"
DEFAULT_AGY_EXECUTABLE = Path("/Users/bobbybones/.local/bin/agy")
TEST_ENV_PREFIX = "PUPPET_AGY_TEST_"
HELP_PROBE_TIMEOUT_SECONDS = 5.0
TURN_READ_TIMEOUT_SECONDS = 8.0
HALT_WAIT_SECONDS = 5.0
MAX_STREAM_LINE_BYTES = 8192
MAX_STREAM_EVENTS = 64
MAX_SAFE_TOOLS = 8
_STREAM_METADATA_KEYS = frozenset(
    {
        "type",
        "subtype",
        "model",
        "session_id",
        "conversation_id",
        "cwd",
        "is_error",
        "success",
        "status",
    }
)
_STREAM_BODY_KEYS = frozenset(
    {
        "message",
        "content",
        "text",
        "prompt",
        "transcript",
        "delta",
        "result",
        "error",
        "output",
        "arguments",
        "input",
    }
)
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

def agy_print_blocker(code: str, detail: str, **identity: Any) -> Dict[str, Any]:
    """Return one body-safe agy-print blocker for parent session integration."""

    return _blocker(code, detail, **identity)


def require_agy_print_selectors(
    requested_model: Optional[str] = None,
    requested_effort: Optional[str] = None,
    *,
    known_models: Optional[Sequence[str]] = None,
    known_efforts: Optional[Sequence[str]] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """Qualify requested model/effort. Unknown selectors fail closed."""

    model = None
    if requested_model is not None:
        model = _bounded_text(requested_model, label="requested model", maximum=200)
        if known_models is not None and model not in set(known_models):
            _raise_identity(
                "model_observation_mismatch",
                "agy-print model selector is unknown or unqualified",
            )
    effort = None
    if requested_effort is not None:
        effort = _bounded_text(requested_effort, label="requested effort", maximum=80)
        if known_efforts is not None and effort not in set(known_efforts):
            _raise_identity(
                "model_observation_mismatch",
                "agy-print effort selector is unknown or unqualified",
            )
    return model, effort


def agy_print_launch_argv(
    executable: Path | str,
    *,
    requested_model: Optional[str] = None,
    requested_effort: Optional[str] = None,
    conversation_id: Optional[str] = None,
    extra_flags: Sequence[str] = (),
    known_models: Optional[Sequence[str]] = None,
    known_efforts: Optional[Sequence[str]] = None,
) -> List[str]:
    """Return the native print/stream-json argv. Never uses ``--continue``."""

    path = Path(executable)
    if (
        not str(path)
        or not path.is_absolute()
        or any(character in str(path) for character in "\x00\n\r")
    ):
        raise ValidationError("agy-print executable path is invalid")
    if CONTINUE_FLAG in extra_flags:
        raise UnsupportedError(
            "agy-print resume refuses --continue; exact --conversation identity is required",
            blocker=_blocker(
                "session_identity_mismatch",
                "agy-print resume refuses --continue; exact --conversation identity is required",
            ),
        )
    model, effort = require_agy_print_selectors(
        requested_model,
        requested_effort,
        known_models=known_models,
        known_efforts=known_efforts,
    )
    argv = [
        str(path),
        PRINT_EQUALS,
        INPUT_FORMAT_FLAG,
        STREAM_JSON,
        OUTPUT_FORMAT_FLAG,
        STREAM_JSON,
    ]
    if model is not None:
        argv.extend([MODEL_FLAG, model])
    if effort is not None:
        argv.extend([EFFORT_FLAG, effort])
    argv.extend(
        [
            DANGEROUS_PERMISSIONS_FLAG,
            NEW_PROJECT_FLAG,
            DISABLE_SLASH_COMMANDS_FLAG,
            LOG_FILE_FLAG,
            "/dev/null",
        ]
    )
    if conversation_id is not None:
        argv.extend(
            [
                CONVERSATION_FLAG,
                validate_identifier(conversation_id, "agy-print conversation"),
            ]
        )
    argv.extend(str(item) for item in extra_flags)
    if CONTINUE_FLAG in argv:
        raise UnsupportedError(
            "agy-print resume refuses --continue; exact --conversation identity is required",
            blocker=_blocker(
                "session_identity_mismatch",
                "agy-print resume refuses --continue; exact --conversation identity is required",
            ),
        )
    return argv


def _resolve_agy_executable(executable: Optional[Path | str] = None) -> Path:
    if executable is not None:
        return Path(executable)
    resolved = shutil.which("agy")
    if resolved:
        return Path(resolved)
    return DEFAULT_AGY_EXECUTABLE


def agy_print_runtime_available(executable: Optional[Path | str] = None) -> bool:
    """True when the exact executable exists. Fixtures never satisfy this."""

    path = _resolve_agy_executable(executable)
    try:
        return path.is_file() and not path.is_symlink() and os.access(path, os.X_OK)
    except OSError:
        return False


def probe_agy_print_runtime(executable: Path | str) -> Dict[str, Any]:
    """Help-only probe. No session, no auth store, no prompt body."""

    path = Path(executable)
    if path.is_symlink() or not path.is_file() or not os.access(path, os.X_OK):
        _raise_unavailable("agy-print executable is unavailable")
    try:
        completed = subprocess.run(
            [str(path), "--help"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=HELP_PROBE_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise IdentityError("agy-print help probe failed") from exc
    help_text = (completed.stdout or b"").decode("utf-8", errors="replace")
    supports_print = PRINT_FLAG in help_text
    supports_stream_json = STREAM_JSON in help_text
    supports_input = INPUT_FORMAT_FLAG in help_text
    supports_output = OUTPUT_FORMAT_FLAG in help_text
    supports_conversation = CONVERSATION_FLAG in help_text
    available = bool(
        supports_print
        and supports_stream_json
        and supports_input
        and supports_output
        and supports_conversation
    )
    return {
        "schema": RUNTIME_PROBE_SCHEMA,
        "executable": str(path.resolve()),
        "supports_print": supports_print,
        "supports_stream_json": supports_stream_json,
        "supports_input_format": supports_input,
        "supports_output_format": supports_output,
        "supports_conversation": supports_conversation,
        "available": available,
        "live_agy_claimed": False,
    }


def installed_agy_print_runtime() -> Optional[Dict[str, Any]]:
    """Probe the installed ``agy`` binary. Fixtures never satisfy this."""

    resolved = shutil.which("agy")
    if resolved is None:
        fallback = DEFAULT_AGY_EXECUTABLE
        if not agy_print_runtime_available(fallback):
            return None
        resolved = str(fallback)
    try:
        probe = probe_agy_print_runtime(resolved)
    except (IdentityError, UnsupportedError, ValidationError):
        return None
    if not probe["available"]:
        return None
    return probe


def _copy_stream_scalar(event: Dict[str, Any], key: str, value: Any) -> None:
    if value is None or key in event:
        return
    if key in {"is_error", "success"}:
        if isinstance(value, bool):
            event[key] = value
        return
    if key in {"step"} and not isinstance(value, bool) and isinstance(value, int):
        event["step"] = str(value)
        return
    if not isinstance(value, str) or not value.strip():
        return
    event[key] = _bounded_text(value, label="agy-print stream %s" % key, maximum=1024)


def parse_agy_stream_event(line: Any) -> Optional[Dict[str, Any]]:
    """Return body-free stream-json metadata. Transcript fields are dropped.

    Blank lines are ignored. Malformed JSON or non-object payloads fail closed.
    """

    if not isinstance(line, str):
        raise ValidationError("agy-print stream-json line is malformed")
    if not line.strip():
        return None
    if len(line.encode("utf-8")) > MAX_STREAM_LINE_BYTES:
        raise ValidationError("agy-print stream-json line is oversized")
    try:
        payload = json.loads(line)
    except json.JSONDecodeError as exc:
        raise ValidationError("agy-print stream-json line is malformed") from exc
    if not isinstance(payload, Mapping):
        raise ValidationError("agy-print stream-json event is malformed")
    event: Dict[str, Any] = {}
    for key in _STREAM_METADATA_KEYS:
        _copy_stream_scalar(event, key, payload.get(key))
    # AGY's native stream-json protocol names the envelope with ``event`` and
    # keeps the useful metadata in an event-specific object.  Preserve only
    # bounded identity/progress fields; never retain the nested body.
    if isinstance(payload.get("event"), str) and payload["event"].strip():
        event.setdefault("type", _bounded_text(payload["event"], label="agy-print event type", maximum=80))
    for nested_name in ("init", "step_update", "result"):
        nested = payload.get(nested_name)
        if not isinstance(nested, Mapping):
            continue
        for key in ("model", "cwd", "session_id", "conversation_id", "status", "step", "step_id", "progress"):
            _copy_stream_scalar(event, key, nested.get(key))
        if nested_name == "step_update":
            event.setdefault("type", "step_update")
        elif nested_name == "result":
            event.setdefault("type", "result")
        elif nested_name == "init":
            event.setdefault("type", "init")
            event.setdefault("subtype", "init")
    event_type = event.get("type")
    if isinstance(event_type, str) and "tool" in event_type:
        tool: Dict[str, str] = {}
        for key in ("tool_name", "name", "tool", "tool_id"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip() and key not in _STREAM_BODY_KEYS:
                tool[key] = _bounded_text(value, label="agy-print tool %s" % key, maximum=200)
        if tool:
            event["tool"] = tool
    for key in ("step", "step_id", "progress"):
        _copy_stream_scalar(event, key, payload.get(key))
    if not event:
        return None
    return event


def empty_stream_proof_state() -> Dict[str, Any]:
    return {
        "observed_model": None,
        "conversation_id": None,
        "session_id": None,
        "cwd": None,
        "terminal_state": "active",
        "failed": False,
        "step_count": 0,
        "last_step": None,
        "tools": [],
        "result_seen": False,
    }


def reduce_agy_stream_event(
    state: Mapping[str, Any],
    event: Mapping[str, Any],
) -> Dict[str, Any]:
    """Fold one metadata event. Raw stream bytes are never retained."""

    reduced = dict(state)
    tools = list(reduced.get("tools") or [])
    event_type = event.get("type")
    subtype = event.get("subtype")
    model = event.get("model")
    if isinstance(model, str) and model.strip():
        reduced["observed_model"] = model
    conversation = event.get("conversation_id")
    if isinstance(conversation, str) and conversation.strip():
        reduced["conversation_id"] = conversation
    observed_session = event.get("session_id")
    if isinstance(observed_session, str) and observed_session.strip():
        reduced["session_id"] = observed_session
    observed_cwd = event.get("cwd")
    if isinstance(observed_cwd, str) and observed_cwd.strip():
        reduced["cwd"] = observed_cwd
    if event.get("is_error") is True:
        reduced["failed"] = True
    step = event.get("step") or event.get("step_id") or event.get("progress")
    if event_type == "step_update" or step is not None:
        reduced["step_count"] = int(reduced.get("step_count") or 0) + 1
        if isinstance(step, str) and step.strip():
            reduced["last_step"] = step
    tool = event.get("tool")
    if isinstance(tool, Mapping) and tool and len(tools) < MAX_SAFE_TOOLS:
        tools.append(dict(tool))
    reduced["tools"] = tools
    status = event.get("status")
    if event_type == "result" or subtype in {"success", "error", "failure"}:
        failed = reduced["failed"] or subtype in {"error", "failure"}
        if isinstance(status, str) and status.upper() in {"ERROR", "FAILURE", "FAILED"}:
            failed = True
        reduced["failed"] = failed
        reduced["terminal_state"] = "failed" if failed else "completed"
        reduced["result_seen"] = True
    if reduced.get("conversation_id") is None:
        reduced["conversation_id"] = reduced.get("session_id")
    return reduced


def extract_stream_json_metadata(events: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Reduce stream-json events to model, conversation, cwd, and result state."""

    if len(events) > MAX_STREAM_EVENTS:
        raise ValidationError("agy-print stream-json event count is oversized")
    state = empty_stream_proof_state()
    for event in events:
        state = reduce_agy_stream_event(state, event)
    return state


def user_stream_event(text: str) -> str:
    cleaned = text.replace("\x00", "").strip()
    if not cleaned:
        raise ValidationError("agy-print user message is empty")
    return json.dumps(
        {
            "type": "user",
            "event": "user",
            "message": {"role": "user", "content": cleaned},
        },
        separators=(",", ":"),
    )


def _workspace_paths_match(observed: Any, expected: Any) -> bool:
    if not isinstance(observed, str) or not isinstance(expected, str):
        return False
    if observed == expected:
        return True
    try:
        return Path(observed).resolve() == Path(expected).resolve()
    except OSError:
        return False


def _closed_process_environment(
    source: Optional[Mapping[str, str]] = None,
) -> Dict[str, str]:
    raw = os.environ if source is None else source
    if not isinstance(raw, Mapping):
        raise ValidationError("agy-print environment is invalid")
    allowed = ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "TZ")
    closed = {
        name: raw[name]
        for name in allowed
        if name in raw and isinstance(raw[name], str)
    }
    for name, value in raw.items():
        if (
            isinstance(name, str)
            and name.startswith(TEST_ENV_PREFIX)
            and isinstance(value, str)
            and "\x00" not in value
        ):
            closed[name] = value
    if "PATH" not in closed or not closed["PATH"]:
        raise ValidationError("agy-print PATH is unavailable")
    return closed


def _command_text(argv: Sequence[str], *, observed_model: Optional[str] = None) -> str:
    rendered = " ".join(shlex.quote(item) for item in argv)
    if observed_model and observed_model not in rendered:
        rendered = "%s init.model=%s" % (rendered, observed_model)
    return _bounded_text(rendered, label="process command", maximum=1024)


def _list_child_pids(parent_pid: int) -> List[int]:
    try:
        completed = subprocess.run(
            ["ps", "-ax", "-o", "pid=", "-o", "ppid="],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=2.0,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise IdentityError("agy-print child process census failed") from exc
    children: List[int] = []
    for line in (completed.stdout or b"").decode("utf-8", errors="replace").splitlines():
        parts = line.split()
        if len(parts) != 2:
            continue
        try:
            pid = int(parts[0])
            ppid = int(parts[1])
        except ValueError:
            continue
        if ppid == parent_pid and pid > 1:
            children.append(pid)
    if len(children) != len(set(children)):
        _raise_identity(
            "process_identity_mismatch",
            "agy-print owned process identity is ambiguous",
            pid=parent_pid,
        )
    return children


def _bind_owned_children(parent_pid: int) -> List[Dict[str, Any]]:
    from .registry import ProcessVanished

    pending = list(_list_child_pids(parent_pid))
    seen: set[int] = set()
    owned = []
    while pending:
        child_pid = pending.pop(0)
        if child_pid in seen:
            _raise_identity(
                "process_identity_mismatch",
                "agy-print owned process identity is ambiguous",
                pid=parent_pid,
            )
        seen.add(child_pid)
        try:
            identity = _sample_birth_identity(child_pid)
        except ProcessVanished:
            continue
        if identity.get("pid") != child_pid:
            _raise_identity(
                "process_identity_mismatch",
                "agy-print process identity changed",
                pid=child_pid,
            )
        owned.append(
            {
                "pid": identity["pid"],
                "kernel_birth_id": identity["kernel_birth_id"],
            }
        )
        pending.extend(pid for pid in _list_child_pids(child_pid) if pid not in seen)
    return owned


def _merge_owned_children(
    parent_pid: int,
    recorded_children: Sequence[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    """Union recorded birth-bound children with a fresh descendant census."""

    from .registry import ProcessVanished

    merged: List[Dict[str, Any]] = []
    by_pid: Dict[int, Dict[str, Any]] = {}
    for child in recorded_children:
        pid, birth = _identity_pair(child, label="agy-print recorded child")
        try:
            current = _revalidate_live_identity(
                {"pid": pid, "kernel_birth_id": birth}
            )
        except ProcessVanished:
            continue
        if current["pid"] != pid or current["kernel_birth_id"] != birth:
            _raise_identity(
                "process_identity_mismatch",
                "agy-print recorded child identity changed",
                pid=pid,
                kernel_birth_id=birth,
            )
        normalized = {"pid": pid, "kernel_birth_id": birth}
        by_pid[pid] = normalized
        merged.append(normalized)
    for child in _bind_owned_children(parent_pid):
        pid, birth = _identity_pair(child, label="agy-print census child")
        previous = by_pid.get(pid)
        if previous is not None and previous["kernel_birth_id"] != birth:
            _raise_identity(
                "process_identity_mismatch",
                "agy-print owned child PID was reused",
                pid=pid,
                kernel_birth_id=birth,
            )
        if previous is None:
            normalized = {"pid": pid, "kernel_birth_id": birth}
            by_pid[pid] = normalized
            merged.append(normalized)
    return merged


def _sample_birth_identity(pid: int, *, attempts: int = 12) -> Dict[str, Any]:
    """Sample a just-created PID across a bounded exec transition window.

    Popen returns before a shebang/launcher child has finished its exec.  The
    registry intentionally rejects that ambiguous sample; the transport may
    retry only this immediate birth-binding window.  Later revalidation stays
    fail-closed.
    """

    from .registry import (
        ExecTransitionSamplingError,
        ProcessExecutableUnavailable,
        ProcessVanished,
        process_birth_identity,
    )

    last: Optional[BaseException] = None
    for attempt in range(attempts):
        try:
            return process_birth_identity(pid)
        except (ExecTransitionSamplingError, ProcessExecutableUnavailable, ProcessVanished) as exc:
            last = exc
            if attempt + 1 < attempts:
                time.sleep(0.02)
    assert last is not None
    raise last


def _revalidate_live_identity(expected: Mapping[str, Any]) -> Dict[str, Any]:
    from .registry import process_alive

    pid, birth = _identity_pair(expected, label="agy-print expected")
    current = _sample_birth_identity(pid, attempts=4)
    if current["kernel_birth_id"] != birth:
        _raise_identity(
            "process_identity_mismatch",
            "agy-print process identity changed",
            pid=pid,
            kernel_birth_id=current["kernel_birth_id"],
        )
    if not process_alive(current):
        _raise_identity(
            "process_identity_mismatch",
            "agy-print process identity is stale",
            pid=pid,
            kernel_birth_id=birth,
        )
    return current


def _pid_gone(expected: Mapping[str, Any]) -> bool:
    from .registry import (
        ProcessExecutableUnavailable,
        ProcessVanished,
        process_birth_identity,
    )

    pid, birth = _identity_pair(expected, label="agy-print expected")
    try:
        current = process_birth_identity(pid)
    except ProcessVanished:
        return True
    except ProcessExecutableUnavailable as exc:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        except OSError:
            raise exc
        try:
            state = subprocess.run(
                ["ps", "-p", str(pid), "-o", "stat="],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=1.0,
                check=False,
            ).stdout.decode("ascii", errors="ignore").strip()
        except (OSError, subprocess.SubprocessError):
            raise exc
        if not state or state.startswith("Z"):
            # A zombie is no longer an executable target. This is a positive
            # terminal-state observation, unlike treating arbitrary identity
            # errors as proof of absence.
            return True
        raise exc
    if current["kernel_birth_id"] != birth:
        _raise_identity(
            "process_identity_mismatch",
            "agy-print process identity changed",
            pid=pid,
            kernel_birth_id=current["kernel_birth_id"],
        )
    return False


def _session_store_dir(registry_root: Path) -> Path:
    return Path(registry_root) / "agy-print"


def _session_store_path(registry_root: Path, session: str) -> Path:
    return _session_store_dir(registry_root) / (
        validate_identifier(session, "agy-print session") + ".json"
    )


def _session_lock_path(registry_root: Path, session: str) -> Path:
    return _session_store_dir(registry_root) / (
        validate_identifier(session, "agy-print session") + ".lock"
    )


def load_agy_print_session(registry_root: Path, session: str) -> Optional[Dict[str, Any]]:
    path = _session_store_path(registry_root, session)
    if path.is_symlink() or not path.is_file():
        return None
    value = read_json(path, max_bytes=131072, reject_sensitive_fields=True)
    if not isinstance(value, Mapping) or value.get("schema") != SESSION_STORE_SCHEMA:
        raise ValidationError("agy-print session store schema is invalid")
    if value.get("transport") != TRANSPORT_ID:
        _raise_identity(
            "identity_mismatch",
            "agy-print session is bound to a different transport",
        )
    return dict(value)


def persist_agy_print_session(registry_root: Path, record: Mapping[str, Any]) -> Dict[str, Any]:
    session = validate_identifier(record.get("session"), "agy-print session")
    if record.get("schema") != SESSION_STORE_SCHEMA:
        raise ValidationError("agy-print session store schema is invalid")
    destination = _session_store_path(registry_root, session)
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with exclusive_lock(_session_lock_path(registry_root, session)):
        atomic_write_json(destination, dict(record))
    return dict(record)


def require_current_agy_qualification(
    stored_scope: Optional[Mapping[str, Any]],
    current_scope: Optional[Mapping[str, Any]],
) -> None:
    """Fail closed when stored AGY compatibility evidence is stale."""

    if stored_scope is None or current_scope is None:
        return
    from .qualification_scope import compatibility_invalidations

    invalidations = compatibility_invalidations(stored_scope, current_scope)
    if invalidations:
        _raise_identity(
            "qualification_receipt_invalid",
            "agy-print qualification is stale: %s"
            % ",".join(item.get("reason", "changed") for item in invalidations),
        )


def observation_from_runtime_state(
    *,
    session: str,
    conversation_id: str,
    requested_model: Optional[str],
    observed_model: str,
    expected_workspace: Mapping[str, Any],
    command: str,
    pid: int,
    kernel_birth_id: str,
    owned_children: Sequence[Mapping[str, Any]],
    terminal_state: str,
    exit_code: Optional[int],
    halt: Optional[Mapping[str, Any]] = None,
    record_state: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a body-safe observation from process-backed metadata. Not a fixture."""

    return fixture_observation(
        session=session,
        conversation_id=conversation_id,
        requested_model=requested_model or observed_model,
        observed_model=observed_model,
        observed_source="runtime_metadata",
        workspace_path=str(expected_workspace["path"]),
        branch=str(expected_workspace["branch"]),
        head=str(expected_workspace["head"]),
        tree=str(expected_workspace["tree"]),
        command=command,
        pid=pid,
        kernel_birth_id=kernel_birth_id,
        owned_children=owned_children,
        terminal_state=terminal_state,
        exit_code=exit_code,
        halt=halt,
        last_validated_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        record_state=record_state or "ACTIVE",
    )


class AgyPrintRuntime:
    """One process-backed native stream-json session. Not a fixture."""

    def __init__(
        self,
        *,
        session: str,
        expected_workspace: Mapping[str, Any],
        requested_model: Optional[str] = None,
        requested_effort: Optional[str] = None,
        conversation_id: Optional[str] = None,
    ) -> None:
        self.session = validate_identifier(session, "agy-print session")
        self.expected_workspace = dict(expected_workspace)
        self.requested_model = requested_model
        self.requested_effort = requested_effort
        self.expected_conversation_id = conversation_id
        self.process: Optional[subprocess.Popen] = None
        self.identity: Optional[Dict[str, Any]] = None
        self.argv: List[str] = []
        self.stream = empty_stream_proof_state()
        self.observation: Optional[Dict[str, Any]] = None
        self.owned_children: List[Dict[str, Any]] = []
        self.turn_count = 0
        self._stdout_buf = b""

    @classmethod
    def launch(
        cls,
        *,
        executable: Path | str,
        cwd: Path | str,
        session: str,
        expected_workspace: Mapping[str, Any],
        requested_model: Optional[str] = None,
        requested_effort: Optional[str] = None,
        conversation_id: Optional[str] = None,
        environment: Optional[Mapping[str, str]] = None,
        extra_flags: Sequence[str] = (),
        known_models: Optional[Sequence[str]] = None,
        known_efforts: Optional[Sequence[str]] = None,
        qualification_scope: Optional[Mapping[str, Any]] = None,
        current_qualification_scope: Optional[Mapping[str, Any]] = None,
    ) -> "AgyPrintRuntime":
        """Start one native process in the exact disposable workspace cwd."""

        require_current_agy_qualification(
            qualification_scope, current_qualification_scope
        )
        if not agy_print_runtime_available(executable):
            _raise_unavailable("agy-print transport is unavailable")
        workspace = Path(cwd)
        if not workspace.is_dir():
            raise ValidationError("agy-print workspace is unavailable")
        expected_path = expected_workspace.get("path")
        if expected_path is not None and not _workspace_paths_match(
            str(workspace), str(expected_path)
        ):
            _raise_identity(
                "workspace_identity_mismatch",
                "agy-print workspace identity does not match the bound checkout",
            )
        argv = agy_print_launch_argv(
            executable,
            requested_model=requested_model,
            requested_effort=requested_effort,
            conversation_id=conversation_id,
            extra_flags=extra_flags,
            known_models=known_models,
            known_efforts=known_efforts,
        )
        try:
            process = subprocess.Popen(
                argv,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                cwd=str(workspace),
                env=_closed_process_environment(environment),
                start_new_session=True,
                bufsize=0,
            )
        except OSError as exc:
            raise IdentityError("agy-print process failed to start") from exc
        if process.stdin is None or process.stdout is None:
            process.kill()
            process.wait(timeout=1.0)
            raise IdentityError("agy-print stdio pipes are unavailable")
        runtime = cls(
            session=session,
            expected_workspace=expected_workspace,
            requested_model=requested_model,
            requested_effort=requested_effort,
            conversation_id=conversation_id,
        )
        runtime.process = process
        runtime.argv = argv
        try:
            runtime.identity = _sample_birth_identity(process.pid)
        except Exception:
            runtime._abandon()
            raise
        return runtime

    @classmethod
    def start(
        cls,
        *,
        prompt: str,
        timeout: float = TURN_READ_TIMEOUT_SECONDS,
        **launch_kwargs: Any,
    ) -> "AgyPrintRuntime":
        """Launch one process and complete the first send/read-result turn."""

        runtime = cls.launch(**launch_kwargs)
        try:
            runtime.send(prompt)
            runtime.read_result(timeout=timeout)
        except Exception:
            runtime._abandon()
            raise
        return runtime

    def send(self, message: str) -> None:
        """Write one user stream-json event. Steering without this process fails."""

        process = self._require_live_process()
        self._revalidate_owned_process()
        if self.turn_count > 0 and not self.conversation_id:
            raise UnsupportedError(
                "agy-print steering is unsupported until exact conversation identity is observed",
                blocker=_blocker(
                    "session_identity_mismatch",
                    "agy-print steering is unsupported until exact conversation identity is observed",
                ),
            )
        if CONTINUE_FLAG in message.split():
            raise UnsupportedError(
                "agy-print resume refuses --continue; exact --conversation identity is required",
                blocker=_blocker(
                    "session_identity_mismatch",
                    "agy-print resume refuses --continue; exact --conversation identity is required",
                ),
            )
        assert process.stdin is not None
        payload = (user_stream_event(message) + "\n").encode("utf-8")
        process.stdin.write(payload)
        process.stdin.flush()
        self.turn_count += 1

    def read_result(self, *, timeout: float = TURN_READ_TIMEOUT_SECONDS) -> Dict[str, Any]:
        """Read NDJSON until a terminal result. Raw lines are discarded."""

        process = self.process
        if process is None or process.stdout is None:
            raise IdentityError("agy-print stdio pipes are unavailable")
        if process.poll() is None:
            try:
                self._revalidate_owned_process()
            except IdentityError as exc:
                from .registry import ProcessVanished

                if not isinstance(exc, ProcessVanished) and process.poll() is None:
                    raise
        elif self.identity is None:
            raise IdentityError("agy-print process identity is unavailable")
        state = dict(self.stream)
        state["result_seen"] = False
        events = 0
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline and events < MAX_STREAM_EVENTS:
            line = self._readline(max(0.05, deadline - time.monotonic()))
            if line is None:
                if process.poll() is not None and not state.get("result_seen"):
                    raise IdentityError("agy-print stream-json metadata was not observed")
                continue
            event = parse_agy_stream_event(line)
            if event is None:
                continue
            events += 1
            state = reduce_agy_stream_event(state, event)
            if state.get("result_seen"):
                break
        if not state.get("result_seen"):
            raise IdentityError("agy-print stream-json metadata was not observed")
        self.stream = state
        self._bind_observation()
        self._reap_if_finished()
        return dict(self.observation or {})

    def status(self) -> Dict[str, Any]:
        """Return conversation, step progress, and owned process liveness."""

        observation = self.require_observation()
        process = observation["process"]
        gone = _pid_gone(process)
        if not gone:
            self._revalidate_owned_process()
        fields = caller_fields_from_observation(
            observation,
            record_state=observation.get("record_state"),
            halt_confirmed=observation["terminal_result"]["state"] == "halted",
        )
        return {
            "ok": True,
            "session": self.session,
            "conversation_id": observation["session"]["conversation_id"],
            "state": observation.get("record_state") or "ACTIVE",
            "target_process_alive": not gone,
            "step_progress": {
                "count": int(self.stream.get("step_count") or 0),
                "last_step": self.stream.get("last_step"),
            },
            "terminal_result": dict(observation["terminal_result"]),
            "process": {
                "pid": process["pid"],
                "kernel_birth_id": process["kernel_birth_id"],
            },
            "workspace": dict(observation["workspace"]),
            "live_agy_claimed": False,
            "process_backed": True,
            "progress_cursor": fields["progress_cursor"],
            "caller_outcome": fields["caller_outcome"],
            "final_outcome": fields["final_outcome"],
            "transport": fields["transport"],
        }

    def wait(
        self,
        *,
        condition: str,
        timeout: float,
        after: Any = None,
        interval: float = 0.25,
    ) -> Dict[str, Any]:
        deadline = time.monotonic() + timeout
        while True:
            report = self.status()
            if condition == "target-stopped":
                matched = not report["target_process_alive"]
            elif condition == "result":
                matched = report["terminal_result"]["state"] in {"completed", "failed"}
            elif condition == "progress":
                count = report["step_progress"]["count"]
                matched = after is None or count > int(after)
            else:
                raise ValidationError("unsupported wait condition")
            if matched:
                report.update(condition=condition, after=after, matched=True)
                return report
            if time.monotonic() >= deadline:
                return {
                    "ok": True,
                    "session": self.session,
                    "condition": condition,
                    "after": after,
                    "matched": False,
                    "live_agy_claimed": False,
                    "process_backed": True,
                }
            time.sleep(interval)

    def halt(self, *, timeout: float = HALT_WAIT_SECONDS) -> Dict[str, Any]:
        """Stop only the owned PID+birth tree. Never signal a foreign or reused PID."""

        from .registry import send_exact_sigint

        observation = self.require_observation()
        process = observation["process"]
        expected = {"pid": process["pid"], "kernel_birth_id": process["kernel_birth_id"]}
        signaled: List[int] = []
        parent_alive = not _pid_gone(expected)
        children = (
            _merge_owned_children(expected["pid"], self.owned_children)
            if parent_alive
            else list(self.owned_children)
        )
        self.owned_children = children
        for child in children:
            if not _pid_gone(child):
                child_identity = _revalidate_live_identity(child)
                send_exact_sigint(child_identity)
                signaled.append(child_identity["pid"])
        if parent_alive:
            current = _revalidate_live_identity(expected)
            send_exact_sigint(current)
            signaled.append(current["pid"])
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if all(_pid_gone(item) for item in [expected, *children]):
                break
            time.sleep(0.05)
        if not all(_pid_gone(item) for item in [expected, *children]):
            raise IdentityError(
                "registered owned process tree did not stop gracefully; no broad kill attempted"
            )
        if (
            self.process is not None
            and self.process.pid == expected["pid"]
            and _pid_gone(expected)
        ):
            try:
                self.process.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                raise IdentityError(
                    "registered target did not stop gracefully; no broad kill attempted"
                )
        for handle in (self.process.stdin, self.process.stdout, self.process.stderr):
            if handle is not None:
                try:
                    handle.close()
                except OSError:
                    pass
        self.process = None
        halt = {
            "pid": process["pid"],
            "kernel_birth_id": process["kernel_birth_id"],
            "pid_gone": True,
            "signaled_pids": signaled,
        }
        self.observation = observation_from_runtime_state(
            session=self.session,
            conversation_id=observation["session"]["conversation_id"],
            requested_model=self.requested_model,
            observed_model=observation["observed_model"]["id"],
            expected_workspace=self.expected_workspace,
            command=process["command"],
            pid=process["pid"],
            kernel_birth_id=process["kernel_birth_id"],
            owned_children=self.owned_children,
            terminal_state="halted",
            exit_code=None,
            halt=halt,
            record_state="HALTED",
        )
        return prove_shutdown(
            self.observation,
            expected_process={
                "pid": process["pid"],
                "kernel_birth_id": process["kernel_birth_id"],
                "owned_children": self.owned_children,
            },
        )

    @property
    def conversation_id(self) -> Optional[str]:
        return self.stream.get("conversation_id")

    def require_observation(self) -> Dict[str, Any]:
        if self.observation is None:
            _raise_unavailable("agy-print structured observation is unavailable")
        return validate_agy_print_observation(self.observation)

    def _require_live_process(self) -> subprocess.Popen:
        process = self.process
        if process is None or process.poll() is not None:
            raise UnsupportedError(
                "agy-print steering is unsupported because the process is not accepting input",
                blocker=_blocker(
                    "transport_unavailable",
                    "agy-print steering is unsupported because the process is not accepting input",
                ),
            )
        if process.stdin is None or process.stdout is None:
            raise IdentityError("agy-print stdio pipes are unavailable")
        return process

    def _revalidate_owned_process(self) -> Dict[str, Any]:
        if self.identity is None:
            raise IdentityError("agy-print process identity is unavailable")
        return _revalidate_live_identity(self.identity)

    def _reap_if_finished(self) -> None:
        process = self.process
        if process is None or process.poll() is None:
            return
        try:
            process.wait(timeout=0.2)
        except subprocess.TimeoutExpired:
            return
        for handle in (process.stdin, process.stdout, process.stderr):
            if handle is not None:
                try:
                    handle.close()
                except OSError:
                    pass

    def _readline(self, timeout: float) -> Optional[str]:
        process = self.process
        if process is None or process.stdout is None:
            raise IdentityError("agy-print stdio pipes are unavailable")
        deadline = time.monotonic() + timeout
        while b"\n" not in self._stdout_buf:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            ready, _, _ = select.select([process.stdout], [], [], remaining)
            if not ready:
                return None
            chunk = os.read(process.stdout.fileno(), 1024)
            if not chunk:
                if not self._stdout_buf:
                    return None
                line = self._stdout_buf
                self._stdout_buf = b""
                if len(line) > MAX_STREAM_LINE_BYTES:
                    raise ValidationError("agy-print stream-json line is oversized")
                return line.decode("utf-8", errors="strict")
            if len(self._stdout_buf) + len(chunk) > MAX_STREAM_LINE_BYTES:
                self._stdout_buf = b""
                raise ValidationError("agy-print stream-json line is oversized")
            self._stdout_buf += chunk
        raw, self._stdout_buf = self._stdout_buf.split(b"\n", 1)
        if len(raw) > MAX_STREAM_LINE_BYTES:
            raise ValidationError("agy-print stream-json line is oversized")
        return raw.decode("utf-8", errors="strict")

    def _bind_observation(self) -> Dict[str, Any]:
        if self.identity is None:
            raise IdentityError("agy-print process identity is unavailable")
        observed_model = self.stream.get("observed_model")
        conversation_id = self.stream.get("conversation_id")
        cwd = self.stream.get("cwd")
        if self.requested_model is not None and observed_model is None:
            _raise_identity(
                "model_observation_selector_only",
                "requested selector is not observed model proof",
            )
        if self.requested_model is not None and observed_model != self.requested_model:
            _raise_identity(
                "model_observation_mismatch",
                "observed model does not match the requested selector",
            )
        if conversation_id is None:
            raise UnsupportedError(
                "agy-print steering is unsupported until exact conversation identity is observed",
                blocker=_blocker(
                    "session_identity_mismatch",
                    "agy-print steering is unsupported until exact conversation identity is observed",
                ),
            )
        if (
            self.expected_conversation_id is not None
            and conversation_id != self.expected_conversation_id
        ):
            _raise_identity(
                "session_identity_mismatch",
                "agy-print resume requires matching session and conversation identity",
            )
        if self.turn_count > 1 and conversation_id != self.expected_conversation_id:
            _raise_identity(
                "session_identity_mismatch",
                "agy-print resume requires matching session and conversation identity",
            )
        workspace_path = str(self.expected_workspace.get("path") or "")
        if cwd is None or not _workspace_paths_match(cwd, workspace_path):
            _raise_identity(
                "workspace_identity_mismatch",
                "agy-print workspace identity does not match the bound checkout",
            )
        self.owned_children = _bind_owned_children(self.identity["pid"])
        command = _command_text(self.argv, observed_model=observed_model)
        self.expected_conversation_id = conversation_id
        self.observation = observation_from_runtime_state(
            session=self.session,
            conversation_id=conversation_id,
            requested_model=self.requested_model,
            observed_model=observed_model or self.requested_model or "unavailable",
            expected_workspace=self.expected_workspace,
            command=command,
            pid=self.identity["pid"],
            kernel_birth_id=self.identity["kernel_birth_id"],
            owned_children=self.owned_children,
            terminal_state=str(self.stream.get("terminal_state") or "active"),
            exit_code=None,
            record_state="ACTIVE",
        )
        return self.observation

    def _abandon(self) -> None:
        process = self.process
        identity = self.identity
        self.process = None
        if process is None:
            return
        try:
            if identity is not None:
                expected = {
                    "pid": identity["pid"],
                    "kernel_birth_id": identity["kernel_birth_id"],
                }
                if not _pid_gone(expected) and process.pid == identity["pid"]:
                    _revalidate_live_identity(expected)
                    process.kill()
            elif process.poll() is None:
                process.kill()
            try:
                process.wait(timeout=1.0)
            except (subprocess.TimeoutExpired, OSError):
                pass
        except (IdentityError, OSError, subprocess.SubprocessError):
            # Cleanup is bounded and never broadens beyond the bound PID.
            pass
        finally:
            for handle in (process.stdin, process.stdout, process.stderr):
                if handle is not None:
                    try:
                        handle.close()
                    except OSError:
                        pass


class AgyPrintController:
    """Structured AGY transport. Never constructs or falls back to tmux."""

    def __init__(
        self,
        registry_root: Path,
        *,
        observer: Optional[Mapping[str, Any]] = None,
        _observer: Optional[Mapping[str, Any]] = None,
        executable: Optional[Path] = None,
        _executable: Optional[Path] = None,
        runtime: Optional[AgyPrintRuntime] = None,
    ):
        self.registry_root = Path(registry_root)
        self.observer = observer if observer is not None else _observer
        self.executable = executable if executable is not None else _executable
        self.runtime = runtime
        self.last_public_send_outcome: Optional[str] = None

    @staticmethod
    def available(executable: Optional[Path | str] = None) -> bool:
        """True only when print/stream-json is advertised. Fixtures never qualify."""

        if executable is not None:
            try:
                return probe_agy_print_runtime(executable)["available"]
            except (IdentityError, UnsupportedError, ValidationError):
                return False
        return installed_agy_print_runtime() is not None

    def session_path(self, session: str) -> Path:
        return _session_store_path(self.registry_root, session)

    def has_session(self, session: str) -> bool:
        path = self.session_path(session)
        return path.is_file() and not path.is_symlink()

    def load_session(self, session: str) -> Optional[Dict[str, Any]]:
        return load_agy_print_session(self.registry_root, session)

    def require_session(self, session: str) -> Dict[str, Any]:
        record = self.load_session(session)
        if record is None:
            _raise_unavailable("agy-print session store is unavailable")
        executable = record.get("executable")
        if executable and self.executable is None:
            self.executable = Path(str(executable))
        return record

    def require_runtime(self) -> AgyPrintRuntime:
        if self.runtime is None:
            _raise_unavailable("agy-print process runtime is unavailable")
        return self.runtime

    def require_observation(self) -> Dict[str, Any]:
        if self.runtime is not None and self.runtime.observation is not None:
            return self.runtime.require_observation()
        if self.observer is not None:
            return validate_agy_print_observation(self.observer)
        _raise_unavailable("agy-print structured observation is unavailable")

    def start(
        self,
        *,
        session: str,
        prompt: str,
        expected_workspace: Mapping[str, Any],
        requested_model: Optional[str] = None,
        requested_effort: Optional[str] = None,
        conversation_id: Optional[str] = None,
        environment: Optional[Mapping[str, str]] = None,
        extra_flags: Sequence[str] = (),
        known_models: Optional[Sequence[str]] = None,
        known_efforts: Optional[Sequence[str]] = None,
        qualification_scope: Optional[Mapping[str, Any]] = None,
        current_qualification_scope: Optional[Mapping[str, Any]] = None,
        timeout: float = TURN_READ_TIMEOUT_SECONDS,
    ) -> Dict[str, Any]:
        self.requested_model = requested_model
        self.requested_effort = requested_effort
        executable = self.executable
        if executable is None:
            installed = installed_agy_print_runtime()
            if installed is None:
                _raise_unavailable("agy-print transport is unavailable")
            executable = Path(installed["executable"])
        elif not agy_print_runtime_available(executable):
            _raise_unavailable("agy-print transport is unavailable")
        self.runtime = AgyPrintRuntime.start(
            prompt=prompt,
            timeout=timeout,
            executable=executable,
            cwd=expected_workspace["path"],
            session=session,
            expected_workspace=expected_workspace,
            requested_model=requested_model,
            requested_effort=requested_effort,
            conversation_id=conversation_id,
            environment=environment,
            extra_flags=extra_flags,
            known_models=known_models,
            known_efforts=known_efforts,
            qualification_scope=qualification_scope,
            current_qualification_scope=current_qualification_scope,
        )
        self.observer = self.runtime.observation
        self.executable = Path(executable)
        self._persist_current(
            session=session,
            qualification_scope=qualification_scope,
        )
        return self.caller_result(
            expected_session=session,
            expected_conversation_id=self.runtime.conversation_id or session,
            expected_workspace=expected_workspace,
            requested_model=requested_model,
            record_state="ACTIVE",
        )

    def send(self, message: Optional[str] = None, **kwargs: Any) -> Any:
        if "session" in kwargs or "expected_workspace" in kwargs:
            payload = kwargs.get("message", message)
            if not isinstance(payload, str):
                raise ValidationError("agy-print user message is empty")
            return self._public_send(message=payload, **kwargs)
        if not isinstance(message, str):
            raise ValidationError("agy-print user message is empty")
        self.require_runtime().send(message)

    def read_result(self, *, timeout: float = TURN_READ_TIMEOUT_SECONDS) -> Dict[str, Any]:
        observation = self.require_runtime().read_result(timeout=timeout)
        self.observer = observation
        if self.runtime is not None:
            self._persist_current(session=self.runtime.session)
        return observation

    def status(
        self,
        session: Optional[str] = None,
        *,
        expected_workspace: Optional[Mapping[str, Any]] = None,
        current_qualification_scope: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        if session is None:
            return self.require_runtime().status()
        stored = self.require_session(session)
        self._require_stored_qualification(stored, current_qualification_scope)
        observation = validate_agy_print_observation(stored["observation"])
        workspace = expected_workspace or observation["workspace"]
        process = observation["process"]
        gone = _pid_gone(process)
        if stored.get("held") and not gone:
            _revalidate_live_identity(process)
        elif not gone:
            try:
                _revalidate_live_identity(process)
            except IdentityError:
                gone = _pid_gone(process)
                if not gone:
                    raise
        self.observer = observation
        fields = caller_fields_from_observation(
            observation,
            record_state=observation.get("record_state"),
            halt_confirmed=observation["terminal_result"]["state"] == "halted",
        )
        return {
            "ok": True,
            "session": session,
            "state": observation.get("record_state") or "ACTIVE",
            "target_process_alive": not gone,
            "live_agy_claimed": False,
            "process_backed": stored.get("process_backed") is True,
            "progress_cursor": fields["progress_cursor"],
            "caller_outcome": fields["caller_outcome"],
            "final_outcome": fields["final_outcome"],
            "transport": fields["transport"],
            "last_checkpoint": observation.get("last_checkpoint"),
            "last_beacon": observation.get("last_beacon"),
            "agy_print": {
                "conversation_id": observation["session"]["conversation_id"],
                "terminal_result": observation["terminal_result"],
                "process": {
                    "pid": process["pid"],
                    "kernel_birth_id": process["kernel_birth_id"],
                },
            },
            "workspace": dict(workspace),
        }

    def wait(
        self,
        *,
        condition: str,
        timeout: float,
        after: Any = None,
        interval: float = 0.25,
        session: Optional[str] = None,
    ) -> Dict[str, Any]:
        if session is None and self.runtime is not None:
            mapped = condition
            if condition == "done":
                mapped = "result"
            if mapped in {"target-stopped", "result", "progress"}:
                return self.require_runtime().wait(
                    condition=mapped, timeout=timeout, after=after, interval=interval
                )
        deadline = time.monotonic() + timeout
        while True:
            report = self.status(session=session) if session is not None else self.status()
            if condition == "target-stopped":
                matched = not report["target_process_alive"]
            elif condition == "checkpoint":
                checkpoint = (report.get("progress_cursor") or {}).get("checkpoint_id")
                matched = checkpoint is not None and (
                    after is None or checkpoint != after
                )
            elif condition == "beacon":
                beacon = (report.get("progress_cursor") or {}).get("beacon_sequence") or 0
                matched = beacon > 0 and (after is None or beacon > after)
            elif condition == "action-required":
                matched = False
            elif condition == "done":
                outcome = report.get("caller_outcome") or {}
                matched = outcome.get("controller_acceptance") == "accepted" or (
                    outcome.get("halt") == "confirmed"
                )
            elif condition == "result":
                terminal = (report.get("agy_print") or {}).get("terminal_result") or {}
                if not terminal and self.runtime is not None:
                    terminal = self.runtime.status()["terminal_result"]
                matched = terminal.get("state") in {"completed", "failed"}
            else:
                raise ValidationError("unsupported wait condition")
            if matched:
                report.update(condition=condition, after=after, matched=True)
                return report
            if time.monotonic() >= deadline:
                return {
                    "ok": True,
                    "session": session or (self.runtime.session if self.runtime else ""),
                    "condition": condition,
                    "after": after,
                    "matched": False,
                    "live_agy_claimed": False,
                }
            time.sleep(interval)

    def record_checkpoint(
        self,
        session: str,
        checkpoint_id: str,
        *,
        beacon_sequence: Optional[int] = None,
    ) -> Dict[str, Any]:
        stored = self.require_session(session)
        observation = validate_agy_print_observation(stored["observation"])
        observation = dict(
            observation,
            last_checkpoint={
                "checkpoint_id": _bounded_text(
                    checkpoint_id, label="checkpoint id", maximum=64
                )
            },
            last_validated_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        )
        if beacon_sequence is not None:
            observation["last_beacon"] = {"sequence": beacon_sequence}
        self.observer = observation
        persist_agy_print_session(
            self.registry_root,
            dict(stored, observation=observation),
        )
        return observation

    def import_checkpoint(self, *, session: str, handoff_path: Path) -> Dict[str, Any]:
        stored = self.require_session(session)
        observation = validate_agy_print_observation(stored["observation"])
        if not stored.get("held"):
            raise IdentityError("agy-print checkpoint requires a live session")
        _revalidate_live_identity(observation["process"])
        contract_raw = stored.get("contract")
        if not isinstance(contract_raw, Mapping) or not contract_raw:
            raise IdentityError("agy-print session is missing its bound contract")
        contract = Contract.from_dict(dict(contract_raw))
        proof_root = stored.get("proof_root")
        if not isinstance(proof_root, str) or not proof_root:
            raise IdentityError("agy-print session is missing its proof root")
        from .session import admit_checkpoint_handoff, agy_session_admission_record

        admission = agy_session_admission_record(stored, contract)
        handoff, protocol, next_state = admit_checkpoint_handoff(
            record=admission,
            contract=contract,
            handoff_path=Path(handoff_path),
            allowed_roots=[Path(proof_root), Path(contract.repo)],
        )
        observation = dict(
            observation,
            last_checkpoint={"checkpoint_id": handoff.checkpoint_id},
            last_validated_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            record_state=next_state,
        )
        reference = handoff.reference()
        persist_agy_print_session(
            self.registry_root,
            dict(
                stored,
                observation=observation,
                protocol=protocol,
                adapter=admission["adapter"],
                handoff=reference,
                handoff_path=str(handoff.path),
            ),
        )
        self.observer = observation
        return {"ok": True, **reference}

    def accept(
        self,
        *,
        session: str,
        checkpoint_id: str,
        expected_workspace: Mapping[str, Any],
        actor: Optional[str] = None,
        evidence_path: Optional[Path] = None,
    ) -> Dict[str, Any]:
        if not isinstance(actor, str) or not actor.strip():
            raise ValidationError("agy-print acceptance actor is required")
        if evidence_path is None or not Path(evidence_path).is_file():
            raise ValidationError("agy-print acceptance evidence is required")
        stored = self.require_session(session)
        self._require_stored_qualification(stored, None)
        contract_raw = stored.get("contract")
        if not isinstance(contract_raw, Mapping):
            raise IdentityError("agy-print session is missing its bound contract")
        contract = Contract.from_dict(dict(contract_raw))
        handoff = self._stored_handoff(stored, checkpoint_id, contract)
        proof_root = Path(stored["proof_root"])
        review_path = proof_root / "verdicts" / (checkpoint_id + ".json")
        review = read_json(review_path, max_bytes=131072)
        from .session import require_conformance_acceptable, require_source_acceptable
        from .verdicts import record_acceptance, verify_current_identity

        verify_current_identity(
            review,
            checkpoint_id=handoff.checkpoint_id,
            artifact_sha256=handoff.artifact_sha256,
            candidate_commit=handoff.identity.get("candidate_commit"),
        )
        observation = validate_agy_print_observation(stored["observation"])
        checkpoint = observation.get("last_checkpoint") or {}
        if checkpoint.get("checkpoint_id") != checkpoint_id:
            _raise_identity(
                "identity_mismatch",
                "agy-print accept requires the current checkpoint identity",
            )
        state = observation.get("record_state") or "ACTIVE"
        if handoff.checkpoint_kind == "conformance":
            require_conformance_acceptable(state, review)
        else:
            require_source_acceptable(state, review)
            from .session import _verify_source_identity

            _verify_source_identity(contract, handoff.identity["candidate_commit"])
        acceptance = record_acceptance(
            contract=contract,
            actor=actor,
            review=review,
            evidence_path=Path(evidence_path),
            acceptance_root=proof_root / "acceptance",
        )
        protocol = dict(stored.get("protocol") or {})
        protocol["phase"] = "accepted"
        observation = dict(observation, record_state="ACCEPTED")
        self.observer = observation
        persist_agy_print_session(
            self.registry_root,
            dict(
                stored,
                observation=observation,
                protocol=protocol,
                acceptance=acceptance,
            ),
        )
        return self.caller_result(
            expected_session=session,
            expected_conversation_id=observation["session"]["conversation_id"],
            expected_workspace=expected_workspace,
            record_state="ACCEPTED",
        )

    def _stored_handoff(
        self, stored: Mapping[str, Any], checkpoint_id: str, contract: Contract
    ) -> Any:
        reference = stored.get("handoff")
        handoff_path = stored.get("handoff_path")
        if not isinstance(reference, Mapping) or not isinstance(handoff_path, str):
            raise ValidationError("agy-print session has no current validated handoff")
        if reference.get("checkpoint_id") != checkpoint_id:
            raise IdentityError("agy-print checkpoint is not current")
        expected_identity = reference.get("identity")
        if not isinstance(expected_identity, Mapping):
            raise IdentityError("agy-print handoff identity reference is invalid")
        handoff = validate_handoff(
            Path(handoff_path),
            allowed_roots=[Path(stored["proof_root"]), Path(contract.repo)],
            expected=dict(expected_identity),
        )
        if (
            handoff.checkpoint_id != checkpoint_id
            or handoff.artifact_sha256 != reference.get("artifact_sha256")
        ):
            raise IdentityError("agy-print handoff reference changed")
        return handoff

    def review(
        self,
        *,
        session: str,
        checkpoint_id: str,
        actor: str,
        verdict: str,
        evidence_path: Path,
    ) -> Dict[str, Any]:
        if verdict not in {"source_accept", "conformance_accept", "repair", "block", "fail"}:
            raise ValidationError("invalid controller verdict")
        stored = self.require_session(session)
        self._require_stored_qualification(stored, None)
        contract_raw = stored.get("contract")
        if not isinstance(contract_raw, Mapping):
            raise IdentityError("agy-print session is missing its bound contract")
        contract = Contract.from_dict(dict(contract_raw))
        handoff = self._stored_handoff(stored, checkpoint_id, contract)
        from .session import (
            _require_repair_budget,
            _verify_source_identity,
            require_conformance_reviewable,
        )
        from .verdicts import record_review

        observation = validate_agy_print_observation(stored["observation"])
        state = observation.get("record_state") or "ACTIVE"
        if handoff.checkpoint_kind == "conformance":
            require_conformance_reviewable(state)
            next_state = {
                "block": "BLOCKED",
                "fail": "FAILED",
            }.get(verdict, "AWAITING_CONFORMANCE_REVIEW")
        elif state == "SOURCE_CHECKPOINT_READY":
            _verify_source_identity(contract, handoff.identity["candidate_commit"])
            next_state = {
                "repair": "ACTIVE",
                "source_accept": "SOURCE_ACCEPTED",
                "block": "BLOCKED",
                "fail": "FAILED",
            }.get(verdict, "AWAITING_SOURCE_REVIEW")
        elif state == "PROOF_CHECKPOINT_READY":
            if verdict == "repair":
                raise ValidationError(
                    "final proof repair requires a fresh source-review session"
                )
            next_state = {
                "block": "BLOCKED",
                "fail": "FAILED",
            }.get(verdict, "AWAITING_CONTROLLER_REVIEW")
        else:
            raise ValidationError("source checkpoint is not reviewable")
        if state == "SOURCE_CHECKPOINT_READY" and verdict == "repair":
            _require_repair_budget(
                dict(stored, repair_count=stored.get("repair_count", 0))
            )
        record = record_review(
            contract=contract,
            actor=actor,
            handoff=handoff,
            verdict=verdict,
            evidence_path=Path(evidence_path),
            verdict_root=Path(stored["proof_root"]) / "verdicts",
        )
        protocol = dict(stored.get("protocol") or {})
        updates: Dict[str, Any] = {}
        if state == "SOURCE_CHECKPOINT_READY":
            if verdict == "repair":
                protocol.update(
                    phase="awaiting_source", source_commit=None, proof_commit=None
                )
                updates["repair_count"] = int(stored.get("repair_count", 0)) + 1
            elif verdict == "source_accept":
                protocol["phase"] = "source_accepted"
            else:
                protocol["phase"] = "reviewed"
        elif state == "PROOF_CHECKPOINT_READY" and verdict not in {"block", "fail"}:
            protocol["phase"] = "final_reviewed"
        else:
            protocol["phase"] = "reviewed"
        observation = dict(observation, record_state=next_state)
        persist_agy_print_session(
            self.registry_root,
            dict(
                stored,
                observation=observation,
                protocol=protocol,
                review=record,
                **updates,
            ),
        )
        self.observer = observation
        return {"ok": True, "review": record}

    def halt(
        self,
        *,
        session: Optional[str] = None,
        expected_workspace: Optional[Mapping[str, Any]] = None,
        timeout: float = HALT_WAIT_SECONDS,
    ) -> Dict[str, Any]:
        if self.runtime is not None and (
            session is None or self.runtime.session == session
        ):
            self.require_runtime().halt(timeout=timeout)
            self.observer = self.require_runtime().observation
            bound_session = session or self.runtime.session
            self._persist_current(session=bound_session, held=False)
            workspace = expected_workspace or self.runtime.expected_workspace
            return self.caller_result(
                expected_session=bound_session,
                expected_conversation_id=self.observer["session"]["conversation_id"],
                expected_workspace=workspace,
                expected_process=self.observer["process"],
                record_state="HALTED",
                require_halt=True,
            )
        if session is None:
            _raise_unavailable("agy-print session store is unavailable")
        stored = self.require_session(session)
        observation = validate_agy_print_observation(stored["observation"])
        process = observation["process"]
        expected = {
            "pid": process["pid"],
            "kernel_birth_id": process["kernel_birth_id"],
        }
        signaled: List[int] = []
        children = list(process["owned_children"])
        from .registry import send_exact_sigint

        parent_alive = not _pid_gone(expected)
        if parent_alive:
            children = _merge_owned_children(expected["pid"], children)
        for child in children:
            if not _pid_gone(child):
                child_identity = _revalidate_live_identity(child)
                send_exact_sigint(child_identity)
                signaled.append(child_identity["pid"])
        if parent_alive:
            current = _revalidate_live_identity(expected)
            send_exact_sigint(current)
            signaled.append(current["pid"])
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if all(_pid_gone(item) for item in [expected, *children]):
                break
            time.sleep(0.05)
        if not all(_pid_gone(item) for item in [expected, *children]):
            raise IdentityError(
                "registered owned process tree did not stop gracefully; no broad kill attempted"
            )
        observation = dict(
            observation,
            terminal_result={"state": "halted", "exit_code": None},
            record_state="HALTED",
            halt={
                "pid": process["pid"],
                "kernel_birth_id": process["kernel_birth_id"],
                "pid_gone": True,
                "signaled_pids": signaled,
            },
            process=dict(process, owned_children=children),
        )
        self.observer = observation
        persist_agy_print_session(
            self.registry_root,
            dict(stored, observation=observation, held=False),
        )
        workspace = expected_workspace or observation["workspace"]
        return self.caller_result(
            expected_session=session,
            expected_conversation_id=observation["session"]["conversation_id"],
            expected_workspace=workspace,
            expected_process=observation["process"],
            record_state="HALTED",
            require_halt=True,
        )

    def _qualification_fingerprint(
        self, scope: Optional[Mapping[str, Any]]
    ) -> Optional[str]:
        if scope is None:
            return None
        return sha256_bytes(canonical_json_bytes(dict(scope)))

    def _require_stored_qualification(
        self,
        stored: Mapping[str, Any],
        current_qualification_scope: Optional[Mapping[str, Any]],
    ) -> None:
        observed_scope = current_qualification_scope
        stored_scope = stored.get("qualification_scope")
        manifest = stored.get("manifest")
        if observed_scope is None and isinstance(stored_scope, Mapping) and isinstance(manifest, Mapping):
            from .instructions import instruction_policy_fingerprint
            from .qualification_scope import build_compatibility_scope

            model_effort = stored_scope.get("harness_scope", {}).get("model_effort", {})
            observed_scope = build_compatibility_scope(
                manifest,
                requested_model=model_effort.get("requested_model"),
                requested_effort=model_effort.get("requested_effort"),
                instruction_policy_fingerprint=instruction_policy_fingerprint(target="agy"),
                transport=stored_scope.get("transport"),
            )
        require_current_agy_qualification(stored_scope, observed_scope)
        if (
            stored.get("qualification_fingerprint")
            and current_qualification_scope is not None
            and stored["qualification_fingerprint"]
            != self._qualification_fingerprint(current_qualification_scope)
        ):
            _raise_identity(
                "qualification_receipt_invalid",
                "agy-print qualification is stale: compatibility_scope_fingerprint_changed",
            )

    def _persist_current(
        self,
        *,
        session: str,
        qualification_scope: Optional[Mapping[str, Any]] = None,
        held: Optional[bool] = None,
        requested_model: Optional[str] = None,
        requested_effort: Optional[str] = None,
    ) -> Dict[str, Any]:
        observation = self.require_observation()
        existing = self.load_session(session) or {}
        process = observation["process"]
        alive = not _pid_gone(
            {"pid": process["pid"], "kernel_birth_id": process["kernel_birth_id"]}
        )
        record = {
            "schema": SESSION_STORE_SCHEMA,
            "transport": TRANSPORT_ID,
            "session": session,
            "conversation_id": observation["session"]["conversation_id"],
            "contract": dict(getattr(self, "contract_raw", existing.get("contract") or {})),
            "manifest": dict(getattr(self, "manifest_raw", existing.get("manifest") or {})),
            "proof_root": getattr(self, "proof_root", None) or existing.get("proof_root"),
            "deadline_at": getattr(self, "deadline_at", None) or existing.get("deadline_at"),
            "lease_owner": getattr(self, "lease_owner", None) or existing.get("lease_owner"),
            "instruction_manifest_sha256": getattr(self, "instruction_manifest_sha256", None) or existing.get("instruction_manifest_sha256"),
            "requested_model": (
                requested_model if requested_model is not None else existing.get("requested_model", getattr(self, "requested_model", None))
            ),
            "requested_effort": (
                requested_effort if requested_effort is not None else existing.get("requested_effort", getattr(self, "requested_effort", None))
            ),
            "qualification_scope": (
                dict(qualification_scope) if qualification_scope is not None else existing.get("qualification_scope")
            ),
            "observation": observation,
            "executable": str(self.executable) if self.executable is not None else existing.get("executable"),
            "qualification_fingerprint": (
                self._qualification_fingerprint(qualification_scope)
                if qualification_scope is not None
                else existing.get("qualification_fingerprint")
            ),
            "send_requests": dict(existing.get("send_requests") or {}),
            "process_backed": True,
            "live_agy_claimed": False,
            "held": alive if held is None else held,
            "repair_count": existing.get("repair_count", 0),
        }
        for key in (
            "protocol",
            "adapter",
            "handoff",
            "handoff_path",
            "review",
            "acceptance",
        ):
            if existing.get(key) is not None:
                record[key] = existing[key]
        persist_agy_print_session(self.registry_root, record)
        return record

    def _public_send(
        self,
        *,
        session: str,
        message: str,
        expected_workspace: Mapping[str, Any],
        requested_model: Optional[str] = None,
        qualification_scope: Optional[Mapping[str, Any]] = None,
        current_qualification_scope: Optional[Mapping[str, Any]] = None,
        request_id: Optional[str] = None,
        **_ignored: Any,
    ) -> Dict[str, Any]:
        if request_id is None:
            request_id = "direct-" + sha256_bytes(message.encode("utf-8"))[:24]
        if not isinstance(request_id, str) or not request_id.strip():
            raise ValidationError("agy-print request id is required")
        stored = self.require_session(session)
        protocol = stored.get("protocol")
        if isinstance(protocol, Mapping) and protocol.get("kind") == "conformance":
            state = (stored.get("observation") or {}).get("record_state") or "ACTIVE"
            first_submission = (
                state in {"CONFORMANCE_READY", "HALTED"}
                and protocol.get("phase") == "ready_validated"
            )
            replay = (
                state == "ACTIVE"
                and protocol.get("phase") == "followup_sent"
                and protocol.get("message_id") == request_id
            )
            if not first_submission and not replay:
                raise ValidationError(
                    "conformance follow-up is not currently authorized"
                )
        elif isinstance(protocol, Mapping) and protocol.get("kind") == "source":
            state = (stored.get("observation") or {}).get("record_state") or "ACTIVE"
            first_submission = (
                state == "SOURCE_ACCEPTED"
                and protocol.get("phase") == "source_accepted"
                and "proof_assignment_id" not in protocol
            )
            replay = (
                state == "SOURCE_ACCEPTED"
                and protocol.get("phase") == "proof_assignment_sent"
                and protocol.get("proof_assignment_id") == request_id
            )
            if not (state in {"ACTIVE", "WAITING_EXTERNAL"} or first_submission or replay):
                raise ValidationError("source session is not accepting messages")
        message_sha256 = sha256_bytes(message.encode("utf-8"))
        requests = stored.get("send_requests")
        if requests is None:
            requests = {}
        if not isinstance(requests, Mapping):
            raise IdentityError("agy-print send request ledger is invalid")
        prior = requests.get(request_id)
        if prior is not None:
            if (
                not isinstance(prior, Mapping)
                or prior.get("message_sha256") != message_sha256
            ):
                raise ConflictError("request id was already used for a different message")
            if prior.get("phase") == "submitted" and isinstance(
                prior.get("result"), Mapping
            ):
                self.last_public_send_outcome = "replay"
                return dict(prior["result"], request_id=request_id)
            if prior.get("phase") == "intent":
                raise ConflictError(
                    "prior AGY send delivery is ambiguous; adjudicate before retry"
                )
            raise IdentityError("agy-print send request ledger entry is invalid")
        require_current_agy_qualification(
            qualification_scope, current_qualification_scope
        )
        self._require_stored_qualification(stored, current_qualification_scope)
        conversation_id = stored.get("conversation_id")
        if not conversation_id:
            raise UnsupportedError(
                "agy-print steering is unsupported until exact conversation identity is observed",
                blocker=_blocker(
                    "session_identity_mismatch",
                    "agy-print steering is unsupported until exact conversation identity is observed",
                ),
            )
        if CONTINUE_FLAG in message.split():
            raise UnsupportedError(
                "agy-print resume refuses --continue; exact --conversation identity is required",
                blocker=_blocker(
                    "session_identity_mismatch",
                    "agy-print resume refuses --continue; exact --conversation identity is required",
                ),
            )
        live = (
            self.runtime is not None
            and self.runtime.process is not None
            and self.runtime.process.poll() is None
        )
        if not live and stored.get("held"):
            raise UnsupportedError(
                "agy-print public send requires explicit halt before validated resume",
                blocker=_blocker(
                    "session_resume_requires_halt",
                    "agy-print public send requires explicit halt before validated resume",
                ),
            )
        before_resume = _ignored.get("before_resume")
        on_resume_failure = _ignored.get("on_resume_failure")
        if before_resume is not None and not callable(before_resume):
            raise ValidationError("agy-print resume preflight hook is invalid")
        if on_resume_failure is not None and not callable(on_resume_failure):
            raise ValidationError("agy-print resume failure hook is invalid")
        if len(requests) >= 64:
            raise ConflictError(
                "agy-print send request ledger is full; adjudicate historical requests before retry"
            )
        admitted_resume = False
        if not live and before_resume is not None:
            before_resume()
            admitted_resume = True
        request_ledger = dict(requests)
        request_ledger[request_id] = {
            "message_sha256": message_sha256,
            "phase": "intent",
        }
        try:
            persist_agy_print_session(
                self.registry_root,
                dict(stored, send_requests=request_ledger),
            )
        except Exception:
            if admitted_resume and on_resume_failure is not None:
                on_resume_failure()
            raise
        if live:
            self.last_public_send_outcome = "live"
            self.runtime.send(message)
            observation = self.runtime.read_result()
            self.observer = observation
            result = self.caller_result(
                expected_session=session,
                expected_conversation_id=conversation_id,
                expected_workspace=expected_workspace,
                requested_model=stored.get("requested_model") or requested_model,
                record_state=observation.get("record_state") or "ACTIVE",
            )
            self._persist_send_result(
                session=session,
                request_id=request_id,
                message_sha256=message_sha256,
                result=result,
            )
            result["request_id"] = request_id
            return result
        try:
            result = self.start(
                session=session,
                prompt=message,
                expected_workspace=expected_workspace,
                requested_model=stored.get("requested_model") or requested_model,
                requested_effort=stored.get("requested_effort"),
                conversation_id=conversation_id,
                qualification_scope=stored.get("qualification_scope") or qualification_scope,
                current_qualification_scope=current_qualification_scope,
            )
        except Exception:
            if admitted_resume and on_resume_failure is not None:
                on_resume_failure()
            raise
        self._persist_send_result(
            session=session,
            request_id=request_id,
            message_sha256=message_sha256,
            result=result,
        )
        self.last_public_send_outcome = "new_launch"
        result["request_id"] = request_id
        return result

    def _persist_send_result(
        self,
        *,
        session: str,
        request_id: str,
        message_sha256: str,
        result: Mapping[str, Any],
    ) -> None:
        current = self.load_session(session)
        if current is None:
            raise IdentityError("agy-print send result lost its session record")
        requests = current.get("send_requests")
        if not isinstance(requests, Mapping):
            raise IdentityError("agy-print send request ledger is invalid")
        updated_requests = dict(requests)
        updated_requests[request_id] = {
            "message_sha256": message_sha256,
            "phase": "submitted",
            "result": dict(result),
        }
        updates: Dict[str, Any] = {
            "send_requests": updated_requests,
            "last_send_request_id": request_id,
            "last_send_message_sha256": message_sha256,
            "last_send_result": dict(result),
        }
        protocol = current.get("protocol")
        observation = current.get("observation")
        if (
            isinstance(protocol, Mapping)
            and protocol.get("kind") == "conformance"
            and protocol.get("phase") == "ready_validated"
            and isinstance(observation, Mapping)
            and observation.get("record_state") in {"CONFORMANCE_READY", "HALTED"}
        ):
            updates["protocol"] = dict(
                protocol, phase="followup_sent", message_id=request_id
            )
            updates["observation"] = dict(observation, record_state="ACTIVE")
        elif (
            isinstance(protocol, Mapping)
            and protocol.get("kind") == "source"
            and protocol.get("phase") == "source_accepted"
            and isinstance(observation, Mapping)
            and observation.get("record_state") == "SOURCE_ACCEPTED"
        ):
            updates["protocol"] = dict(
                protocol, phase="proof_assignment_sent", proof_assignment_id=request_id
            )
        persist_agy_print_session(
            self.registry_root,
            dict(current, **updates),
        )

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
            "process_backed": self.runtime is not None
            or self.has_session(expected_session),
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
