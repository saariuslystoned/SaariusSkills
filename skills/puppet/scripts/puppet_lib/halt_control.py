"""Crash-aware graceful-control delivery for exact target halt."""

from __future__ import annotations

from typing import Callable, Dict, List

from .errors import IdentityError, ValidationError
from .journal import Journal
from .safety import canonical_json_bytes, sha256_bytes, validate_identifier


def _request_id(session: str, index: int, phase: str) -> str:
    return sha256_bytes(
        canonical_json_bytes(
            {
                "kind": "halt_control",
                "session": session,
                "index": index,
                "phase": phase,
            }
        )
    )


def deliver_halt_controls(
    *,
    journal: Journal,
    session: str,
    target_pid: int,
    keys: List[str],
    process_alive: Callable[[], bool],
    send_control: Callable[[str], None],
    after_send: Callable[[], None] = lambda: None,
) -> List[str]:
    """Deliver each key once or fail closed on an ambiguous prior send.

    An intent is committed before transport and a submission record immediately
    after the transport call returns. If the controller dies between those two
    commits, a retry cannot know whether the key reached tmux and must not send
    it again.
    """
    validate_identifier(session, "halt-control session")
    if not isinstance(target_pid, int) or target_pid <= 1:
        raise ValidationError("halt-control target pid is invalid")
    if not isinstance(keys, list) or not keys or not all(
        isinstance(key, str) and key for key in keys
    ):
        raise ValidationError("halt-control keys are invalid")
    submitted_keys: List[str] = []
    for index, key in enumerate(keys):
        intent_event: Dict[str, object] = {
            "kind": "halt_control",
            "phase": "intent",
            "session": session,
            "target_pid": target_pid,
            "index": index,
            "key": key,
        }
        submitted_event = dict(intent_event, phase="submitted")
        intent = journal.lookup(_request_id(session, index, "intent"))
        submitted = journal.lookup(_request_id(session, index, "submitted"))
        if intent is not None and intent.get("event") != intent_event:
            raise IdentityError("halt-control intent identity changed")
        if submitted is not None and submitted.get("event") != submitted_event:
            raise IdentityError("halt-control submission identity changed")
        if submitted is not None:
            if intent is None:
                raise IdentityError("halt-control submission lacks its intent")
            submitted_keys.append(key)
            if not process_alive():
                break
            continue
        if intent is not None:
            raise IdentityError(
                "halt-control delivery is ambiguous after an interrupted submission"
            )
        if not process_alive():
            break
        journal.append(
            request_id=_request_id(session, index, "intent"),
            event=intent_event,
        )
        send_control(key)
        journal.append(
            request_id=_request_id(session, index, "submitted"),
            event=submitted_event,
        )
        submitted_keys.append(key)
        after_send()
    return submitted_keys
