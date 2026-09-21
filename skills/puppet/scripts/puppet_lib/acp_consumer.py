"""Process-local task-owned ACP consumer owner and trusted route bindings.

The owner keeps the in-memory runner from first launch through a later turn
and final finish. A body-free continuation cannot recover that runner without
this live owner. Cross-process resume is unsupported and fails closed.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, Mapping, Optional

from .errors import ValidationError
from .safety import validate_identifier


CONTINUATION_SCHEMA = "puppet.acp-consumer-continuation/v1"
OWNER_SCHEMA = "puppet.acp-consumer-owner/v1"
_BODY_KEYS = frozenset(
    {"prompt", "output", "content", "text", "transcript", "title", "options"}
)
_CONTINUATION_KEYS = (
    "schema",
    "owner_id",
    "continuation_id",
    "route",
    "session",
    "host_conversation_id",
    "request_id",
    "runtime_session_name",
    "backend_session_id",
    "acpx_record_id",
    "process_local",
    "cross_process_resume",
)


def reject_consumer_bodies(value: Any, *, label: str = "consumer metadata") -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if key in _BODY_KEYS:
                raise ValidationError("%s contains body-bearing field %s" % (label, key))
            reject_consumer_bodies(nested, label=label)
    elif isinstance(value, list):
        for nested in value:
            reject_consumer_bodies(nested, label=label)


def _new_identifier(prefix: str) -> str:
    return validate_identifier("%s-%s" % (prefix, uuid.uuid4().hex[:12]), prefix)


def in_process_child_exit() -> Dict[str, Any]:
    return {
        "pid": None,
        "returncode": None,
        "exited": True,
        "kind": "in_process",
    }


def runtime_child_exit(runtime: Any) -> Dict[str, Any]:
    identity = getattr(runtime, "child_process_identity", None)
    if callable(identity):
        observed = dict(identity())
        reject_consumer_bodies(observed, label="child exit")
        return observed
    return in_process_child_exit()


def shutdown_task_owned_runtime(runtime: Any) -> Dict[str, Any]:
    shutdown = getattr(runtime, "shutdown", None)
    if callable(shutdown):
        shutdown()
    return runtime_child_exit(runtime)


def public_continuation(*, owner_id: str, continuation_id: str, runner: Any, route: str) -> Dict[str, Any]:
    handle = getattr(runner, "handle", None) or {}
    continuation = {
        "schema": CONTINUATION_SCHEMA,
        "owner_id": owner_id,
        "continuation_id": continuation_id,
        "route": route,
        "session": runner.session,
        "host_conversation_id": runner.conversation_id,
        "request_id": runner.request_id,
        "runtime_session_name": handle.get("runtimeSessionName"),
        "backend_session_id": handle.get("backendSessionId"),
        "acpx_record_id": handle.get("acpxRecordId"),
        "process_local": True,
        "cross_process_resume": False,
    }
    if set(continuation) != set(_CONTINUATION_KEYS):
        raise ValidationError("ACP consumer continuation fields do not match schema")
    reject_consumer_bodies(continuation, label="continuation")
    return continuation


class AcpConsumerOwner:
    """Process-local owner for one task-owned ACP consumer lifetime."""

    def __init__(self, *, owner_id: Optional[str] = None):
        self.schema = OWNER_SCHEMA
        self.owner_id = validate_identifier(
            owner_id or _new_identifier("owner"), "ACP consumer owner"
        )
        self.process_local = True
        self.cross_process_resume = False
        self.last_child_exit: Optional[Dict[str, Any]] = None
        self._held: Dict[str, Dict[str, Any]] = {}

    @staticmethod
    def available() -> bool:
        return False

    def __repr__(self) -> str:
        return (
            "AcpConsumerOwner(owner_id=%r, held=%d, process_local=True, "
            "cross_process_resume=False)"
            % (self.owner_id, len(self._held))
        )

    def retain(
        self,
        runner: Any,
        *,
        route: str,
        expected_workspace: Mapping[str, Any],
    ) -> Dict[str, Any]:
        continuation_id = _new_identifier("cont")
        self._held[continuation_id] = {
            "runner": runner,
            "route": route,
            "session": runner.session,
            "expected_workspace": dict(expected_workspace),
        }
        return public_continuation(
            owner_id=self.owner_id,
            continuation_id=continuation_id,
            runner=runner,
            route=route,
        )

    def next_turn(
        self,
        continuation: Any,
        *,
        text: Any,
        request_id: str,
        expected_workspace: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        record = self.resolve(continuation)
        runner = record["runner"]
        workspace = expected_workspace or record["expected_workspace"]
        try:
            observation = runner.next_turn(
                text=text,
                request_id=request_id,
                expected_workspace=workspace,
            )
        except BaseException as exc:
            self._release(record, primary=exc)
            raise
        updated = public_continuation(
            owner_id=self.owner_id,
            continuation_id=continuation["continuation_id"],
            runner=runner,
            route=record["route"],
        )
        return {
            "ok": True,
            "observation": observation,
            "continuation": updated,
        }

    def finish(
        self,
        continuation: Any,
        *,
        discard_persistent_state: bool = True,
    ) -> Dict[str, Any]:
        record = self.resolve(continuation)
        return self._release(
            record, discard_persistent_state=discard_persistent_state
        )

    def resolve(self, continuation: Any) -> Dict[str, Any]:
        if not isinstance(continuation, Mapping):
            raise ValidationError("process-local ACP consumer continuation is missing")
        if continuation.get("schema") != CONTINUATION_SCHEMA:
            raise ValidationError("process-local ACP consumer continuation is invalid")
        if continuation.get("process_local") is not True:
            raise ValidationError("ACP consumer continuation is not process-local")
        if continuation.get("cross_process_resume") is not False:
            raise ValidationError("ACP consumer continuation cannot claim cross-process resume")
        if continuation.get("owner_id") != self.owner_id:
            raise ValidationError("process-local ACP consumer owner does not match")
        continuation_id = continuation.get("continuation_id")
        if not isinstance(continuation_id, str) or continuation_id not in self._held:
            raise ValidationError("process-local ACP consumer owner is absent")
        record = self._held[continuation_id]
        if continuation.get("route") != record["route"]:
            raise ValidationError("process-local ACP consumer route does not match")
        if continuation.get("session") != record["session"]:
            raise ValidationError("process-local ACP consumer session does not match")
        return record

    def release_unretained(self, runner: Any, *, primary: BaseException) -> None:
        fake = {
            "runner": runner,
            "route": getattr(runner, "transport_id", "unbound"),
            "session": getattr(runner, "session", None),
            "expected_workspace": {},
            "unretained": True,
        }
        self._release(fake, primary=primary)

    def _release(
        self,
        record: Mapping[str, Any],
        *,
        primary: Optional[BaseException] = None,
        discard_persistent_state: bool = True,
    ) -> Dict[str, Any]:
        runner = record["runner"]
        closed: Dict[str, Any] = {}
        try:
            if (
                getattr(runner, "handle", None) is not None
                and not getattr(runner, "final_discard", False)
            ):
                closed = dict(
                    runner.finish(discard_persistent_state=discard_persistent_state)
                )
        except Exception:
            if primary is None:
                raise
        try:
            child_exit = shutdown_task_owned_runtime(getattr(runner, "runtime", None))
        except Exception:
            if primary is None:
                raise
            child_exit = {
                "pid": None,
                "returncode": None,
                "exited": False,
                "kind": "shutdown_failed",
            }
        reject_consumer_bodies(child_exit, label="child exit")
        self.last_child_exit = child_exit
        for key, held in list(self._held.items()):
            if held is record or held.get("runner") is runner:
                self._held.pop(key, None)
        if primary is not None:
            raise primary
        closed["child_exit"] = child_exit
        reject_consumer_bodies(closed, label="owner finish")
        return closed


def attach_consumer_lifecycle(
    result: Mapping[str, Any],
    *,
    owner: AcpConsumerOwner,
    runner: Any,
    route: str,
    expected_workspace: Mapping[str, Any],
) -> Dict[str, Any]:
    if not hasattr(runner, "session") or not hasattr(runner, "conversation_id"):
        return dict(result)
    attached = dict(result)
    attached["owner"] = owner
    attached["continuation"] = owner.retain(
        runner, route=route, expected_workspace=expected_workspace
    )
    reject_consumer_bodies(attached["continuation"], label="continuation")
    return attached
