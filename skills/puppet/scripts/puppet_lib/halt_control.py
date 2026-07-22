"""Crash-aware graceful-control delivery for exact target halt."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Dict, List

from .contracts import PROCESS_IDENTITY_FIELDS
from .errors import IdentityError, ValidationError
from .journal import Journal
from .safety import (
    canonical_json_bytes,
    sha256_bytes,
    validate_bounded_json,
    validate_identifier,
)


def _request_id(session: str, index: int, phase: str) -> str:
    # Preserve the v1 request namespace so an old control intent collides and
    # fails identity matching instead of becoming eligible for a fresh action.
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


HALT_ACTIONS = {"exact_pid_sigint", "tmux_pane_eof"}


def deliver_halt_actions(
    *,
    journal: Journal,
    session: str,
    target_identity: Dict[str, object],
    actions: List[str],
    process_alive: Callable[[], bool],
    deliver_action: Callable[[str], None],
    after_send: Callable[[], None] = lambda: None,
) -> List[str]:
    """Deliver each action once or fail closed on an ambiguous prior attempt.

    An intent is committed before transport and a submission record immediately
    after the transport call returns. If the controller dies between those two
    commits, a retry cannot know whether the action reached its target and must
    not attempt it again.
    """
    validate_identifier(session, "halt-control session")
    if (
        not isinstance(target_identity, dict)
        or set(target_identity) != PROCESS_IDENTITY_FIELDS
        or target_identity.get("identity_version") != 2
        or isinstance(target_identity.get("pid"), bool)
        or not isinstance(target_identity.get("pid"), int)
        or target_identity["pid"] <= 1
        or not isinstance(target_identity.get("start"), str)
        or not target_identity["start"]
        or len(target_identity["start"]) > 200
        or any(character in target_identity["start"] for character in "\x00\n\r")
        or not isinstance(target_identity.get("kernel_birth_id"), str)
        or not target_identity["kernel_birth_id"]
        or len(target_identity["kernel_birth_id"]) > 200
        or any(
            character in target_identity["kernel_birth_id"]
            for character in "\x00\n\r"
        )
        or not isinstance(target_identity.get("command"), str)
        or not target_identity["command"]
        or len(target_identity["command"]) > 1000
        or "\x00" in target_identity["command"]
        or not isinstance(target_identity.get("executable_path"), str)
        or "\x00" in target_identity["executable_path"]
        or not Path(target_identity["executable_path"]).is_absolute()
        or any(
            isinstance(target_identity.get(name), bool)
            or not isinstance(target_identity.get(name), int)
            or target_identity[name] <= 0
            for name in ("device", "inode")
        )
    ):
        raise ValidationError("halt-control target identity is invalid")
    validate_bounded_json(
        target_identity,
        max_depth=2,
        max_items=16,
        max_string=4096,
        reject_sensitive_fields=True,
    )
    target_pid = target_identity["pid"]
    target_identity_sha256 = sha256_bytes(canonical_json_bytes(target_identity))
    if (
        not isinstance(actions, list)
        or not actions
        or any(action not in HALT_ACTIONS for action in actions)
    ):
        raise ValidationError("halt actions are invalid")
    submitted_actions: List[str] = []
    for index, action in enumerate(actions):
        intent_event: Dict[str, object] = {
            "kind": "halt_action",
            "phase": "intent",
            "session": session,
            "target_pid": target_pid,
            "target_identity_sha256": target_identity_sha256,
            "index": index,
            "action": action,
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
            submitted_actions.append(action)
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
        deliver_action(action)
        journal.append(
            request_id=_request_id(session, index, "submitted"),
            event=submitted_event,
        )
        submitted_actions.append(action)
        after_send()
    return submitted_actions
