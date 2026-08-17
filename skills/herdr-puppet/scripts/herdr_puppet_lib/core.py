from __future__ import annotations

import fcntl
import hashlib
import json
import os
import posixpath
import re
import shlex
import stat
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from .authority import (
    deterministic_owned_label,
    destination_selection_for_record,
    selected_authority_sha256,
)
from .claude_hooks import (
    CLAUDE_MARKER_NAMES,
    PHASE_SUBMISSIONS,
    claude_helper_exec_argv,
    validate_claude_hook_receipt,
)
from .errors import HerdrPuppetError
from .harness_binding import (
    CANONICAL_HARNESSES,
    INSTRUCTION_PLANE,
    binding_fingerprint,
    remote_census_facts_fingerprint,
    validate_harness_binding,
    validate_instruction_manifest,
    verify_remote_census,
)
from .herdr_client import HerdrClient, load_json
from .journal import (
    append_event,
    atomic_json,
    make_event,
    now,
    read_events,
    refresh_state,
    require_initialized_journal,
    sha256_text,
)


SUPPORTED_HERDR_VERSION = "0.7.3"
SUPPORTED_HERDR_PROTOCOL = 16
CHECKPOINT_KINDS = ("STATUS", "ACTION_REQUIRED", "DONE")
SHELL_READY = "status_verified"
HARNESS_READY = "operator_verified"
HARNESS_CHECKPOINT_PENDING = "checkpoint_pending"
HARNESS_CHECKPOINT_READY = "checkpoint_verified"
HARNESS_INPUT_ADMITTED = {
    HARNESS_READY,
    HARNESS_CHECKPOINT_READY,
}
LEGACY_HARNESS_STATUS = "status_verified"
DEFAULT_BEACON_TIMEOUT_MS = 480_000
MAX_BEACON_TIMEOUT_MS = 3_600_000
MAX_BEACON_WAIT_ATTEMPTS = 2
MAX_SHELL_STATUS_SUBMISSIONS = 2
MAX_RECONCILIATION_EVIDENCE_BYTES = 1024
MAX_DESTINATION_CATALOG_BYTES = 256 * 1024
DESTINATION_CATALOG_SCHEMA = "herdr-puppet.destination-catalog.v1"
DESTINATION_RECEIPT_SCHEMA = "herdr-puppet.destination-selection-receipt.v1"
PLAN_SCHEMA = "herdr-puppet.plan.v2"
HISTORICAL_PLAN_SCHEMA = "herdr-puppet.plan.v1"
LEASE_SCHEMA = "herdr-puppet.lease.v3"
PREVIOUS_LEASE_SCHEMA = "herdr-puppet.lease.v2"
HISTORICAL_LEASE_SCHEMA = "herdr-puppet.lease.v1"
BEACON_RESERVATION_KIND = "qualification.beacon-wait-reserved"
REMOTE_FILE_REGISTERED = "registered"
REMOTE_FILE_REMOVED = "removal_verified"
REMOTE_REMOVAL_EVIDENCE = {
    "operator_verified_remote_absence",
    "source_bound_terminal_artifact",
}
HARNESS_COMMANDS = {
    "agy": "agy",
    "codex": "codex",
    "claude": "claude",
    "cursor": "cursor-agent",
    "grok": "grok",
}
STARTUP_GATE_ACTIONS = {
    "cursor": {
        "workspace_trust": {
            "accept": ["a"],
            "not_present": [],
        },
    },
    "codex": {
        "workspace_trust": {
            "accept_selected": ["enter"],
            "select_accept": ["up", "enter"],
            "not_present": [],
        },
        "security_acknowledgement": {
            "acknowledge": ["enter"],
            "not_present": [],
        },
        "permission_bypass_confirmation": {
            "accept_selected": ["enter"],
            "select_accept": ["down", "enter"],
            "not_present": [],
        },
    },
    "claude": {
        "workspace_trust": {
            "accept_selected": ["enter"],
            "select_accept": ["up", "enter"],
            "not_present": [],
        },
        "security_acknowledgement": {
            "acknowledge": ["enter"],
            "not_present": [],
        },
        "permission_bypass_confirmation": {
            "accept_selected": ["enter"],
            "select_accept": ["down", "enter"],
            "not_present": [],
        },
    },
}
VIEW_BEGIN_KIND = "qualification.view-begin"
VIEW_COMPLETE_KIND = "qualification.view-complete"
PRESERVE_REASONS = {
    "checkpoint_failed",
    "human_gate",
    "milestone_complete",
    "operator_stop",
    "route_superseded",
}
CLAUDE_LIFECYCLE_EVENT = "qualification.claude-lifecycle"
RFC3339_TIMESTAMP = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
    r"(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)
STRICT_CHECKPOINT_TOKEN = re.compile(
    r"HERDR_PUPPET_(?:STATUS|ACTION_REQUIRED|DONE)[ \t]+"
    r"[A-Za-z0-9._:-]{8,24}(?![A-Za-z0-9._:-])"
)

LEASE_IDENTITY_FIELDS = (
    "schema",
    "run_id",
    "harness",
    "session",
    "workspace",
    "destination_selection",
    "selected_authority_sha256",
    "owned_label",
    "tab_id",
    "pane_id",
    "terminal_id",
    "ssh",
    "source",
    "proof_root",
    "harness_binding",
)
CONTROLLER_FILE_FIELDS = ("caller_text_files", "caller_text_files_removed")
LEASE_FIELDS = {
    "schema",
    "state",
    "run_id",
    "harness",
    "session",
    "workspace",
    "destination_selection",
    "selected_authority_sha256",
    "owned_label",
    "tab_id",
    "pane_id",
    "terminal_id",
    "ssh",
    "next_seq",
    "shell_readiness",
    "harness_readiness",
    "harness_readiness_evidence",
    "harness_readiness_operator",
    "harness_readiness_verified_at",
    "harness_readiness_submission_seq",
    "harness_readiness_nonce_sha256",
    "source",
    "proof_root",
    "caller_text_files",
    "caller_text_files_removed",
    "remote_task_files",
    "interactive_sends",
    "pending_interactive_send",
    "pending_sequence_operation",
    "harness_binding",
    "harness_launch",
    "startup_gate_operations",
    "preserved_reason",
    "preserved_at",
    "cleanup_state",
    "cleanup_verified_at",
    "cleanup_reconciled_absence",
}
CANONICAL_LEASE_REQUIRED_FIELDS = {
    "schema",
    "state",
    "run_id",
    "harness",
    "session",
    "workspace",
    "destination_selection",
    "selected_authority_sha256",
    "owned_label",
    "tab_id",
    "pane_id",
    "terminal_id",
    "ssh",
    "next_seq",
    "shell_readiness",
    "harness_readiness",
    "source",
    "harness_binding",
    "startup_gate_operations",
    "proof_root",
    "caller_text_files",
    "caller_text_files_removed",
    "remote_task_files",
    "interactive_sends",
    "pending_interactive_send",
    "pending_sequence_operation",
}
LEGACY_OPTIONAL_CANONICAL_FIELDS = {
    "destination_selection",
    "selected_authority_sha256",
    "shell_readiness",
    "harness_readiness",
    "caller_text_files",
    "caller_text_files_removed",
    "remote_task_files",
    "interactive_sends",
    "pending_interactive_send",
    "pending_sequence_operation",
    "harness_binding",
    "startup_gate_operations",
}
LEGACY_LEASE_REQUIRED_FIELDS = (
    CANONICAL_LEASE_REQUIRED_FIELDS - LEGACY_OPTIONAL_CANONICAL_FIELDS
)
PREVIOUS_LEASE_FIELDS = LEASE_FIELDS - {
    "harness_readiness_submission_seq",
    "harness_readiness_nonce_sha256",
}
HISTORICAL_LEASE_FIELDS = PREVIOUS_LEASE_FIELDS - {
    "destination_selection",
    "selected_authority_sha256",
}


def _shell_tokens(command: str) -> list[str]:
    try:
        lexer = shlex.shlex(
            command,
            posix=True,
            punctuation_chars=";&|()<>",
        )
        lexer.whitespace_split = True
        lexer.commenters = ""
        return list(lexer)
    except ValueError as exc:
        raise HerdrPuppetError(
            "shell_command_unparseable",
            "The shell command cannot be safely classified.",
        ) from exc


def _token_names_bound_harness(
    token: str,
    *,
    executable: str,
    command_name: str,
) -> bool:
    candidates = [token]
    if "=" in token:
        candidates.append(token.rsplit("=", 1)[1])
    for candidate in candidates:
        if candidate == executable:
            return True
        if Path(candidate).name.lower() == command_name.lower():
            return True
    return False


def _is_shell_assignment(token: str) -> bool:
    name, separator, _value = token.partition("=")
    return bool(
        separator
        and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name)
    )


def _shell_command_segments(tokens: list[str]) -> list[list[str]]:
    boundaries = {";", "&&", "||", "|", "&", "(", ")"}
    segments: list[list[str]] = []
    current: list[str] = []
    for token in tokens:
        if token in boundaries:
            if current:
                segments.append(current)
                current = []
        else:
            current.append(token)
    if current:
        segments.append(current)
    return segments


def _unwrap_shell_command(
    segment: list[str],
) -> tuple[list[str], str | None]:
    wrappers: list[str] = []
    index = 0
    while index < len(segment):
        token = segment[index]
        if _is_shell_assignment(token):
            index += 1
            continue
        name = Path(token).name.lower()
        if name in {"command", "exec", "nohup", "time"}:
            wrappers.append(name)
            index += 1
            while index < len(segment) and segment[index].startswith("-"):
                index += 1
            continue
        if name == "env":
            wrappers.append(name)
            index += 1
            while index < len(segment):
                candidate = segment[index]
                if _is_shell_assignment(candidate):
                    index += 1
                    continue
                if candidate in {"-u", "--unset", "-C", "--chdir"}:
                    index += 2
                    continue
                if candidate.startswith("-"):
                    index += 1
                    continue
                break
            continue
        return wrappers, token
    return wrappers, None


def _reject_shell_replacing_harness_launcher(
    command: str,
    harness: str,
) -> None:
    harness_binary = HARNESS_COMMANDS.get(harness, Path(harness.strip()).name)
    if not harness_binary:
        return
    for segment in _shell_command_segments(_shell_tokens(command)):
        wrappers, candidate = _unwrap_shell_command(segment)
        if (
            "exec" in wrappers
            and candidate is not None
            and _token_names_bound_harness(
                candidate,
                executable="",
                command_name=harness_binary,
            )
        ):
            raise HerdrPuppetError(
                "shell_replacing_harness_launcher",
                "The launcher must return to the leased shell after the "
                "harness exits.",
            )


def _reject_generic_harness_launcher(
    command: str,
    binding: dict[str, Any],
) -> None:
    executable = binding["remote"]["executable"]["path"]
    command_name = HARNESS_COMMANDS[binding["harness"]]
    for segment in _shell_command_segments(_shell_tokens(command)):
        _wrappers, candidate = _unwrap_shell_command(segment)
        if candidate is not None and _token_names_bound_harness(
            candidate,
            executable=executable,
            command_name=command_name,
        ):
            raise HerdrPuppetError(
                "generic_harness_launch_forbidden",
                "Use the controller-attested qualification-harness-launch "
                "operation.",
            )


def _reject_nested_shell_command(command: str) -> None:
    nested_shells = {
        "sh",
        "bash",
        "zsh",
        "dash",
        "ksh",
        "mksh",
        "ash",
        "fish",
        "eval",
    }
    for token in _shell_tokens(command):
        candidate = token.rsplit("=", 1)[-1]
        if Path(candidate).name.lower() in nested_shells:
            raise HerdrPuppetError(
                "nested_shell_command_forbidden",
                "The bounded qualification shell surface rejects nested shell "
                "and eval launchers.",
            )


@contextmanager
def _lease_lock(lease_path: Path) -> Iterator[Path]:
    canonical_lease_path = lease_path.expanduser().resolve()
    canonical_lease_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = canonical_lease_path.with_name(
        f".{canonical_lease_path.name}.lock"
    )
    flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(lock_path, flags, 0o600)
    except OSError as exc:
        raise HerdrPuppetError(
            "lease_lock_unavailable",
            "The exact lease mutation lock could not be opened.",
        ) from exc
    try:
        os.fchmod(descriptor, 0o600)
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield canonical_lease_path
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def _assert_same_lease_identity(
    expected: dict[str, Any],
    current: dict[str, Any],
) -> None:
    drifted = [
        field
        for field in LEASE_IDENTITY_FIELDS
        if (field in current) != (field in expected)
        or current.get(field) != expected.get(field)
    ]
    if drifted:
        raise HerdrPuppetError(
            "lease_path_identity_mismatch",
            "The lease path resolves to a different exact lease identity.",
            details={"fields": drifted},
        )


def _reload_locked_lease(
    lease_payload: dict[str, Any],
    lease_path: Path,
    *,
    allow_historical: bool = False,
) -> dict[str, Any]:
    current = load_json(lease_path)
    _validate_maintainable_lease(current, allow_historical=allow_historical)
    _assert_same_lease_identity(lease_payload, current)
    return current


def _require_active_lease_journal(
    run_root: Path | None,
    lease_payload: dict[str, Any],
) -> None:
    if run_root is None:
        raise HerdrPuppetError(
            "journal_root_required",
            "Active lease operations require the exact initialized journal root.",
        )
    require_initialized_journal(
        run_root,
        lease_payload=lease_payload,
    )


def _require_optional_preserve_journal(
    run_root: Path | None,
    lease_payload: dict[str, Any],
) -> None:
    if run_root is not None:
        require_initialized_journal(
            run_root,
            lease_payload=lease_payload,
            allow_historical_plan=True,
        )


def _as_text_file_list(raw_value: Any) -> list[str]:
    if not isinstance(raw_value, list):
        raise HerdrPuppetError(
            "invalid_lease",
            "Unexpected prompt-file tracking field type.",
            details={"field": "caller_text_files"},
        )
    if not raw_value:
        return []
    values: list[str] = []
    for value in raw_value:
        if isinstance(value, str) and value.strip():
            values.append(value)
        else:
            raise HerdrPuppetError(
                "invalid_lease",
                "Prompt-file tracking requires non-empty string paths.",
                details={"value": value},
            )
    if len(set(values)) != len(values):
        raise HerdrPuppetError(
            "invalid_lease",
            "Prompt-file tracking paths must be unique.",
        )
    return values


def _as_interactive_sends(
    raw_value: Any,
    *,
    next_seq: int,
) -> list[dict[str, Any]]:
    if not isinstance(raw_value, list) or len(raw_value) > 2:
        raise HerdrPuppetError(
            "invalid_lease",
            "Interactive send state must be a bounded array.",
        )
    normalized: list[dict[str, Any]] = []
    previous_seq = 0
    for index, item in enumerate(raw_value):
        expected_phase = "initial" if index == 0 else "steering"
        if (
            not isinstance(item, dict)
            or set(item)
            != {
                "seq",
                "phase",
                "prompt_sha256",
                "transport",
                "instruction_wrapper_verified",
            }
            or isinstance(item["seq"], bool)
            or not isinstance(item["seq"], int)
            or item["seq"] <= previous_seq
            or item["seq"] >= next_seq
            or item["phase"] != expected_phase
            or item["transport"] not in {"direct", "reconciled"}
            or not isinstance(item["instruction_wrapper_verified"], bool)
            or not isinstance(item["prompt_sha256"], str)
            or re.fullmatch(r"[0-9a-f]{64}", item["prompt_sha256"]) is None
            or (
                index == 0
                and (
                    item["transport"] != "direct"
                    or item["instruction_wrapper_verified"] is not True
                )
            )
            or (
                index == 1
                and item["instruction_wrapper_verified"] is not False
            )
        ):
            raise HerdrPuppetError(
                "invalid_lease",
                "Interactive send state is malformed or non-monotonic.",
            )
        previous_seq = item["seq"]
        normalized.append(dict(item))
    return normalized


def _as_pending_interactive_send(
    raw_value: Any,
    *,
    next_seq: int,
    completed_sends: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if raw_value is None:
        return None
    expected_phase = "initial" if not completed_sends else "steering"
    if (
        len(completed_sends) >= 2
        or not isinstance(raw_value, dict)
        or set(raw_value)
        != {
            "seq",
            "phase",
            "prompt_sha256",
            "transport",
            "instruction_wrapper_verified",
            "delivery_state",
            "reserved_at",
        }
        or isinstance(raw_value["seq"], bool)
        or raw_value["seq"] != next_seq
        or raw_value["phase"] != expected_phase
        or raw_value["transport"] != "direct"
        or raw_value["delivery_state"] != "pending_or_unknown"
        or not _is_rfc3339_timestamp(raw_value["reserved_at"])
        or not isinstance(raw_value["prompt_sha256"], str)
        or re.fullmatch(r"[0-9a-f]{64}", raw_value["prompt_sha256"]) is None
        or raw_value["instruction_wrapper_verified"]
        is not (expected_phase == "initial")
    ):
        raise HerdrPuppetError(
            "invalid_lease",
            "Pending interactive-send state is malformed or replayable.",
        )
    return dict(raw_value)


def _as_pending_sequence_operation(
    raw_value: Any,
    *,
    next_seq: int,
) -> dict[str, Any] | None:
    if raw_value is None:
        return None
    if (
        not isinstance(raw_value, dict)
        or set(raw_value)
        != {
            "operation",
            "seq",
            "payload_sha256",
            "delivery_state",
            "reserved_at",
        }
        or raw_value["operation"]
        not in {"run", "harness_launch", "startup_gate"}
        or isinstance(raw_value["seq"], bool)
        or raw_value["seq"] != next_seq
        or not isinstance(raw_value["payload_sha256"], str)
        or re.fullmatch(r"[0-9a-f]{64}", raw_value["payload_sha256"]) is None
        or raw_value["delivery_state"] != "pending_or_unknown"
        or not _is_rfc3339_timestamp(raw_value["reserved_at"])
    ):
        raise HerdrPuppetError(
            "invalid_lease",
            "Pending sequence-operation state is malformed or replayable.",
        )
    return dict(raw_value)


def _require_no_pending_sequence_operation(
    lease: dict[str, Any],
) -> None:
    pending = _as_pending_sequence_operation(
        lease.get("pending_sequence_operation"),
        next_seq=lease["next_seq"],
    )
    if pending is not None:
        raise HerdrPuppetError(
            "qualification_sequence_delivery_unknown",
            "A durably reserved sequence operation may already have reached "
            "Herdr; preserve the row and do not replay it.",
            details={
                "operation": pending["operation"],
                "seq": pending["seq"],
            },
        )


def _reserve_sequence_operation(
    *,
    lease: dict[str, Any],
    lease_path: Path,
    run_root: Path,
    operation: str,
    seq: int,
    payload_sha256: str,
) -> dict[str, Any]:
    _require_no_pending_sequence_operation(lease)
    if lease.get("pending_interactive_send") is not None:
        raise HerdrPuppetError(
            "qualification_send_delivery_unknown",
            "A pending interactive send blocks another sequence mutation.",
        )
    reserved = json.loads(json.dumps(lease))
    reserved["pending_sequence_operation"] = {
        "operation": operation,
        "seq": seq,
        "payload_sha256": payload_sha256,
        "delivery_state": "pending_or_unknown",
        "reserved_at": now(),
    }
    atomic_json(lease_path, reserved)
    append_event(
        run_root,
        make_event(
            reserved["run_id"],
            "qualification.sequence-operation-reserved",
            "observed",
            seq=seq,
            data={
                "operation": operation,
                "payload_sha256": payload_sha256,
                "delivery_state": "pending_or_unknown",
                "herdr_mutated": False,
            },
        ),
    )
    return reserved


def _normalize_remote_task_path(path: str) -> str:
    try:
        encoded_path = path.encode("utf-8") if isinstance(path, str) else b""
    except UnicodeEncodeError as exc:
        raise HerdrPuppetError(
            "invalid_remote_task_path",
            "A remote task file path must be valid UTF-8.",
        ) from exc
    if (
        not isinstance(path, str)
        or not path
        or path == "/"
        or len(encoded_path) > 4096
        or "\x00" in path
        or any(ord(character) < 32 or ord(character) == 127 for character in path)
        or not path.startswith("/")
        or posixpath.normpath(path) != path
    ):
        raise HerdrPuppetError(
            "invalid_remote_task_path",
            "A remote task file requires one normalized absolute POSIX path.",
        )
    return path


def _as_remote_task_files(
    raw_value: Any,
    *,
    expected_ssh_target: str,
) -> list[dict[str, Any]]:
    if not isinstance(raw_value, list):
        raise HerdrPuppetError(
            "invalid_lease",
            "Remote task-file tracking must be a list.",
        )
    if not raw_value:
        return []
    values: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw_entry in raw_value:
        if not isinstance(raw_entry, dict):
            raise HerdrPuppetError(
                "invalid_lease",
                "Remote task-file entries must be objects.",
            )
        allowed = {
            "path",
            "ssh_target",
            "state",
            "registered_at",
            "removal_verified_at",
            "removal_evidence",
        }
        if set(raw_entry) - allowed:
            raise HerdrPuppetError(
                "invalid_lease",
                "Remote task-file entry has unexpected fields.",
            )
        path = _normalize_remote_task_path(raw_entry.get("path"))
        if path in seen:
            raise HerdrPuppetError(
                "invalid_lease",
                "Remote task-file paths must be unique.",
            )
        seen.add(path)
        if raw_entry.get("ssh_target") != expected_ssh_target:
            raise HerdrPuppetError(
                "invalid_lease",
                "Remote task-file target does not match the leased SSH target.",
            )
        state = raw_entry.get("state")
        if state not in {REMOTE_FILE_REGISTERED, REMOTE_FILE_REMOVED}:
            raise HerdrPuppetError(
                "invalid_lease",
                "Remote task-file state is unsupported.",
            )
        if not _is_rfc3339_timestamp(raw_entry.get("registered_at")):
            raise HerdrPuppetError(
                "invalid_lease",
                "Remote task-file registration time must be RFC 3339.",
            )
        if state == REMOTE_FILE_REMOVED:
            if (
                not _is_rfc3339_timestamp(
                    raw_entry.get("removal_verified_at")
                )
                or raw_entry.get("removal_evidence")
                not in REMOTE_REMOVAL_EVIDENCE
            ):
                raise HerdrPuppetError(
                    "invalid_lease",
                    "Verified remote removal requires bounded evidence and time.",
                )
        elif (
            "removal_verified_at" in raw_entry
            or "removal_evidence" in raw_entry
        ):
            raise HerdrPuppetError(
                "invalid_lease",
                "Registered remote files may not claim removal evidence.",
            )
        values.append(json.loads(json.dumps(raw_entry)))
    return values


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def _normalize_prompt_file(path: str) -> str:
    return str(Path(path).expanduser().resolve())


def _is_prompt_file_retained(path: str) -> bool:
    return Path(path).is_file()


def _shell_readiness(payload: dict[str, Any]) -> str:
    if "shell_readiness" in payload:
        return payload["shell_readiness"]
    if payload.get("harness_readiness") == LEGACY_HARNESS_STATUS:
        return SHELL_READY
    return "unverified"


def _harness_input_admitted(payload: dict[str, Any]) -> bool:
    return payload.get("harness_readiness") in HARNESS_INPUT_ADMITTED


def _is_strict_shell_status_probe(command: str) -> bool:
    return (
        re.fullmatch(
            r"printf[ \t]+'%s\\n'[ \t]+'HERDR_PUPPET_STATUS "
            r"[A-Za-z0-9._:-]{8,128}'",
            command.strip(),
        )
        is not None
    )


def _require_bounded_shell_status_retry(
    *,
    lease: dict[str, Any],
    seq: int,
    command: str,
    run_root: Path | None,
) -> None:
    if (
        seq != MAX_SHELL_STATUS_SUBMISSIONS
        or run_root is None
        or not _is_strict_shell_status_probe(command)
        or "harness_launch" in lease
        or lease.get("harness_readiness") != "unverified"
    ):
        raise HerdrPuppetError(
            "shell_readiness_not_proven",
            "Further shell submissions require a STATUS-verified shell or one "
            "bounded strict STATUS retry after a failed first wait.",
            details={
                "expected": SHELL_READY,
                "actual": _shell_readiness(lease),
            },
        )
    events = read_events(run_root)
    first_runs = [
        event
        for event in events
        if event.get("kind") == "qualification.run"
        and event.get("seq") == 1
        and event.get("result") == "ok"
        and (event.get("data") or {}).get("shell_status_probe") is True
    ]
    first_beacons = [
        event
        for event in events
        if event.get("kind") == "qualification.beacon"
        and event.get("seq") == 1
    ]
    failed_waits = [
        event
        for event in first_beacons
        if event.get("result") == "failed"
        and (event.get("data") or {}).get("checkpoint") is None
    ]
    matched_waits = [
        event
        for event in first_beacons
        if (event.get("data") or {}).get("checkpoint") is not None
    ]
    if len(first_runs) != 1 or not failed_waits or matched_waits:
        raise HerdrPuppetError(
            "shell_status_retry_not_authorized",
            "A strict shell STATUS retry requires exactly one first submission "
            "and a controller-recorded failed wait for that submission.",
        )


def _require_string(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise HerdrPuppetError(
            "invalid_record",
            f"Required string field is missing: {key}",
        )
    return value


def _is_rfc3339_timestamp(value: Any) -> bool:
    if not isinstance(value, str) or RFC3339_TIMESTAMP.fullmatch(value) is None:
        return False
    try:
        parsed = datetime.fromisoformat(
            value[:-1] + "+00:00" if value.endswith("Z") else value
        )
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _require_exact_object_fields(
    payload: dict[str, Any],
    key: str,
    fields: set[str],
    *,
    error_code: str = "invalid_lease",
    record_name: str = "Lease",
) -> dict[str, Any]:
    value = payload.get(key)
    if not isinstance(value, dict) or set(value) != fields:
        raise HerdrPuppetError(
            error_code,
            f"{record_name} {key} must contain exactly the normative fields.",
            details={
                "field": key,
                "missing_fields": sorted(
                    fields - set(value) if isinstance(value, dict) else fields
                ),
                "unexpected_fields": sorted(
                    set(value) - fields if isinstance(value, dict) else set()
                ),
            },
        )
    return value


def _validate_record_binding(payload: dict[str, Any]) -> dict[str, Any]:
    binding = payload.get("harness_binding")
    if not isinstance(binding, dict):
        raise HerdrPuppetError(
            "harness_binding_missing",
            "The plan or lease must reference one controller-attested harness binding.",
        )
    source = payload.get("source")
    if not isinstance(source, dict):
        raise HerdrPuppetError(
            "invalid_record",
            "The binding cannot be validated without a source record.",
        )
    return validate_harness_binding(
        binding,
        expected_harness=payload.get("harness"),
        expected_repo=source.get("repo"),
        expected_worktree=source.get("worktree"),
        verify_current_adapters=(
            binding.get("schema") == "herdr-puppet.harness-binding.v3"
        ),
        allow_historical=True,
    )


def _require_current_record_binding(
    payload: dict[str, Any],
) -> dict[str, Any]:
    binding = _validate_record_binding(payload)
    if binding.get("schema") != "herdr-puppet.harness-binding.v3":
        raise HerdrPuppetError(
            "legacy_harness_binding_requires_recensus",
            "Harness-binding v1/v2 remains available for status, preservation, "
            "maintenance, and exact cleanup only; fresh qualification requires "
            "a new census and active plan-v2 carrying a binding-v3 record.",
        )
    return binding


def _validate_harness_launch_record(
    value: Any,
    *,
    binding: dict[str, Any],
    next_seq: int,
) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {
        "seq",
        "launched_at",
        "command_sha256",
        "binding_fingerprint",
        "launch_vector_sha256",
        "remote_harness_pid",
    }:
        raise HerdrPuppetError(
            "invalid_lease",
            "The harness launch record shape is invalid.",
        )
    if (
        not isinstance(value["seq"], int)
        or isinstance(value["seq"], bool)
        or value["seq"] < 2
        or value["seq"] >= next_seq
        or not _is_rfc3339_timestamp(value["launched_at"])
        or value["binding_fingerprint"] != binding["fingerprint"]
        or value["launch_vector_sha256"]
        != binding["regular_launch"]["vector_sha256"]
        or value["remote_harness_pid"] != "unavailable"
    ):
        raise HerdrPuppetError(
            "invalid_lease",
            "The harness launch record does not match its binding and sequence.",
        )
    command_sha256 = value["command_sha256"]
    if (
        not isinstance(command_sha256, str)
        or re.fullmatch(r"[0-9a-f]{64}", command_sha256) is None
    ):
        raise HerdrPuppetError(
            "invalid_lease",
            "The harness launch command fingerprint is invalid.",
        )
    return dict(value)


def _validate_startup_gate_operations(
    value: Any,
    *,
    harness: str,
    next_seq: int,
) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise HerdrPuppetError(
            "invalid_lease",
            "Startup-gate operations must be an array.",
        )
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    previous_seq = 0
    for item in value:
        if not isinstance(item, dict) or set(item) != {
            "gate",
            "action",
            "seq",
            "observed_at",
            "operator_sha256",
            "worktree_sha256",
            "key_vector_sha256",
            "pane_input_mutated",
        }:
            raise HerdrPuppetError(
                "invalid_lease",
                "A startup-gate operation shape is invalid.",
            )
        gate = item["gate"]
        action = item["action"]
        allowed = STARTUP_GATE_ACTIONS.get(harness, {}).get(gate)
        if (
            allowed is None
            or action not in allowed
            or gate in seen
            or not isinstance(item["seq"], int)
            or isinstance(item["seq"], bool)
            or item["seq"] <= previous_seq
            or item["seq"] >= next_seq
            or not _is_rfc3339_timestamp(item["observed_at"])
            or item["pane_input_mutated"] is not bool(allowed[action])
        ):
            raise HerdrPuppetError(
                "invalid_lease",
                "A startup-gate operation is unsupported, repeated, or out of sequence.",
            )
        for field in (
            "operator_sha256",
            "worktree_sha256",
            "key_vector_sha256",
        ):
            if (
                not isinstance(item[field], str)
                or re.fullmatch(r"[0-9a-f]{64}", item[field]) is None
            ):
                raise HerdrPuppetError(
                    "invalid_lease",
                    "A startup-gate operation fingerprint is invalid.",
                )
        seen.add(gate)
        previous_seq = item["seq"]
        normalized.append(dict(item))
    return normalized


def validate_plan(payload: dict[str, Any]) -> None:
    _validate_plan(payload, historical=False)


def validate_historical_plan(payload: dict[str, Any]) -> None:
    _validate_plan(payload, historical=True)


def _validate_plan(
    payload: dict[str, Any],
    *,
    historical: bool,
) -> None:
    required_fields = {
        "schema",
        "state",
        "run_id",
        "harness",
        "session",
        "workspace",
        "destination_selection",
        "expected_ssh_target",
        "owned_label",
        "source",
        "harness_binding",
        "proof_root",
        "safety",
    }
    if historical:
        required_fields.remove("destination_selection")
    else:
        required_fields.add("selected_authority_sha256")
    if set(payload) != required_fields:
        raise HerdrPuppetError(
            "invalid_plan",
            "The plan must contain exactly the normative fields.",
            details={
                "missing_fields": sorted(required_fields - set(payload)),
                "unexpected_fields": sorted(set(payload) - required_fields),
            },
        )
    expected_schema = HISTORICAL_PLAN_SCHEMA if historical else PLAN_SCHEMA
    if payload.get("schema") != expected_schema:
        raise HerdrPuppetError("invalid_plan_schema", "Unsupported plan schema.")
    if payload.get("state") != "planned":
        raise HerdrPuppetError("invalid_plan_state", "The plan is not in planned state.")
    for key in (
        "run_id",
        "harness",
        "expected_ssh_target",
        "owned_label",
        "proof_root",
    ):
        _require_string(payload, key)
    if payload.get("harness") not in CANONICAL_HARNESSES:
        raise HerdrPuppetError(
            "noncanonical_harness",
            "Harness must be one of agy, codex, claude, cursor, or grok.",
        )
    session = _require_exact_object_fields(
        payload,
        "session",
        {"name", "version", "protocol", "socket", "incarnation_proven"},
        error_code="invalid_plan",
        record_name="Plan",
    )
    for key in ("name", "version", "socket"):
        _require_string(session, key)
    if (
        isinstance(session.get("protocol"), bool)
        or not isinstance(session.get("protocol"), int)
        or session["protocol"] < 1
    ):
        raise HerdrPuppetError(
            "invalid_plan",
            "Plan session protocol must be a positive integer.",
        )
    workspace = _require_exact_object_fields(
        payload,
        "workspace",
        {"id", "label"},
        error_code="invalid_plan",
        record_name="Plan",
    )
    for key in ("id", "label"):
        _require_string(workspace, key)
    source = _require_exact_object_fields(
        payload,
        "source",
        {"repo", "worktree"},
        error_code="invalid_plan",
        record_name="Plan",
    )
    for key in ("repo", "worktree"):
        _require_string(source, key)
    safety = _require_exact_object_fields(
        payload,
        "safety",
        {
            "parent_session_mutation",
            "adopt_existing_tab",
            "ordinary_transcript_read",
            "live_mutation_authorized",
        },
        error_code="invalid_plan",
        record_name="Plan",
    )
    owned_label = payload["owned_label"]
    if re.fullmatch(r"puppet-[a-z0-9-]+", owned_label) is None:
        raise HerdrPuppetError(
            "invalid_plan",
            "Plan owned_label does not match the canonical pattern.",
        )
    if not historical:
        selection = _validate_destination_selection(
            payload["destination_selection"]
        )
        if selection["workspace_label"] != workspace["label"]:
            raise HerdrPuppetError(
                "invalid_destination_selection",
                "The destination selection workspace does not match the plan.",
            )
        expected_label = deterministic_owned_label(
            payload["run_id"],
            payload["harness"],
            selection["tab"]["ordinal"],
        )
        if owned_label != expected_label:
            raise HerdrPuppetError(
                "owned_label_authority_mismatch",
                "The plan owned label does not match run, harness, and ordinal authority.",
            )
    if safety.get("parent_session_mutation") is not False:
        raise HerdrPuppetError(
            "parent_session_mutation_forbidden",
            "A plan may not authorize parent-session mutation.",
        )
    if safety.get("adopt_existing_tab") is not False:
        raise HerdrPuppetError(
            "existing_tab_adoption_forbidden",
            "A plan may not authorize existing-tab adoption.",
        )
    if safety.get("ordinary_transcript_read") is not False:
        raise HerdrPuppetError(
            "ordinary_transcript_read_forbidden",
            "A plan may not authorize ordinary transcript reads.",
        )
    if not isinstance(safety.get("live_mutation_authorized"), bool):
        raise HerdrPuppetError(
            "invalid_plan",
            "Plan live mutation authorization must be boolean.",
        )
    if session.get("incarnation_proven") is not False:
        raise HerdrPuppetError(
            "server_incarnation_claim_forbidden",
            "Herdr 0.7.3 does not expose a server-incarnation authority field.",
        )
    historical_binding = payload.get("harness_binding")
    if historical and (
        not isinstance(historical_binding, dict)
        or historical_binding.get("schema")
        not in {
            "herdr-puppet.harness-binding.v1",
            "herdr-puppet.harness-binding.v2",
        }
    ):
        raise HerdrPuppetError(
            "invalid_harness_binding",
            "Historical plan-v1 accepts only its frozen binding-v1/v2 authority.",
        )
    _validate_record_binding(payload)
    if not historical:
        expected_authority = selected_authority_sha256(payload)
        if payload.get("selected_authority_sha256") != expected_authority:
            raise HerdrPuppetError(
                "selected_authority_fingerprint_mismatch",
                "The plan selected-authority fingerprint does not match its facts.",
            )


def validate_lease(payload: dict[str, Any]) -> None:
    if payload.get("schema") in {
        PREVIOUS_LEASE_SCHEMA,
        HISTORICAL_LEASE_SCHEMA,
    }:
        validate_legacy_lease(payload)
        raise HerdrPuppetError(
            "legacy_lease_requires_migration",
            "Historical lease-v1/v2 requires explicit migration before active "
            "qualification.",
        )
    _validate_lease(payload, lease_version=3)


def validate_legacy_lease(payload: dict[str, Any]) -> None:
    if payload.get("schema") == PREVIOUS_LEASE_SCHEMA:
        _validate_lease(payload, lease_version=2)
        return
    if payload.get("schema") == HISTORICAL_LEASE_SCHEMA:
        _validate_lease(payload, lease_version=1)
        return
    raise HerdrPuppetError("invalid_lease_schema", "Unsupported lease schema.")


def _validate_maintainable_lease(
    payload: dict[str, Any],
    *,
    allow_historical: bool,
) -> None:
    if payload.get("schema") == LEASE_SCHEMA:
        validate_lease(payload)
        return
    if allow_historical and payload.get("schema") in {
        PREVIOUS_LEASE_SCHEMA,
        HISTORICAL_LEASE_SCHEMA,
    }:
        validate_legacy_lease(payload)
        return
    raise HerdrPuppetError(
        "invalid_lease_schema",
        "Unsupported lease schema for this operation.",
    )


def _validate_lease(
    payload: dict[str, Any],
    *,
    lease_version: int,
) -> None:
    schemas = {
        1: HISTORICAL_LEASE_SCHEMA,
        2: PREVIOUS_LEASE_SCHEMA,
        3: LEASE_SCHEMA,
    }
    expected_schema = schemas.get(lease_version)
    if expected_schema is None:
        raise HerdrPuppetError("invalid_lease_schema", "Unsupported lease schema.")
    if payload.get("schema") != expected_schema:
        raise HerdrPuppetError("invalid_lease_schema", "Unsupported lease schema.")
    allowed_fields = (
        HISTORICAL_LEASE_FIELDS
        if lease_version == 1
        else PREVIOUS_LEASE_FIELDS
        if lease_version == 2
        else LEASE_FIELDS
    )
    unexpected_fields = sorted(set(payload) - allowed_fields)
    if unexpected_fields:
        raise HerdrPuppetError(
            "invalid_lease",
            "Lease contains fields outside the normative schema.",
            details={"unexpected_fields": unexpected_fields},
        )
    missing_baseline_fields = sorted(LEGACY_LEASE_REQUIRED_FIELDS - set(payload))
    if missing_baseline_fields:
        raise HerdrPuppetError(
            "invalid_lease",
            "Lease is missing required fields.",
            details={"missing_fields": missing_baseline_fields},
        )
    canonical_missing = sorted(CANONICAL_LEASE_REQUIRED_FIELDS - set(payload))
    legacy_readiness = payload.get("harness_readiness") == LEGACY_HARNESS_STATUS
    if lease_version != 1 and (canonical_missing or legacy_readiness):
        raise HerdrPuppetError(
            "legacy_lease_requires_migration",
            "Historical lease-v1 shape requires explicit canonical migration.",
            details={
                "missing_fields": canonical_missing,
                "legacy_harness_readiness": legacy_readiness,
            },
        )
    if payload.get("state") not in {"active", "preserved"}:
        raise HerdrPuppetError(
            "invalid_lease_state",
            "The lease state is neither active nor preserved.",
        )
    for key in (
        "run_id",
        "harness",
        "tab_id",
        "pane_id",
        "terminal_id",
        "proof_root",
    ):
        _require_string(payload, key)
    if payload.get("harness") not in CANONICAL_HARNESSES:
        raise HerdrPuppetError(
            "noncanonical_harness",
            "Lease harness is not canonical.",
        )
    owned_label = _require_string(payload, "owned_label")
    if re.fullmatch(r"puppet-[a-z0-9-]+", owned_label) is None:
        raise HerdrPuppetError(
            "invalid_lease",
            "Lease owned_label does not match the canonical pattern.",
        )
    if (
        not isinstance(payload.get("next_seq"), int)
        or isinstance(payload["next_seq"], bool)
        or payload["next_seq"] < 1
    ):
        raise HerdrPuppetError("invalid_next_seq", "Lease next_seq must be positive.")
    session = _require_exact_object_fields(
        payload,
        "session",
        {"name", "version", "protocol", "socket", "incarnation_proven"},
    )
    for key in ("name", "version", "socket"):
        _require_string(session, key)
    if (
        not isinstance(session.get("protocol"), int)
        or isinstance(session["protocol"], bool)
        or session["protocol"] < 1
    ):
        raise HerdrPuppetError(
            "invalid_lease",
            "Lease session protocol must be a positive integer.",
        )
    if session.get("incarnation_proven") is not False:
        raise HerdrPuppetError(
            "server_incarnation_claim_forbidden",
            "Herdr 0.7.3 does not expose a server-incarnation authority field.",
        )
    workspace = _require_exact_object_fields(
        payload,
        "workspace",
        {"id", "label"},
    )
    for key in ("id", "label"):
        _require_string(workspace, key)
    selection: dict[str, Any] | None = None
    if "destination_selection" in payload:
        selection = _validate_destination_selection(
            payload["destination_selection"]
        )
        if selection["workspace_label"] != workspace["label"]:
            raise HerdrPuppetError(
                "invalid_destination_selection",
                "The leased destination workspace does not match its receipt.",
            )
        expected_label = deterministic_owned_label(
            payload["run_id"],
            payload["harness"],
            selection["tab"]["ordinal"],
        )
        if owned_label != expected_label:
            raise HerdrPuppetError(
                "owned_label_authority_mismatch",
                "The lease owned label does not match run, harness, and ordinal authority.",
            )
    ssh = _require_exact_object_fields(
        payload,
        "ssh",
        {"pid", "argv", "target"},
    )
    if (
        not isinstance(ssh.get("pid"), int)
        or isinstance(ssh["pid"], bool)
        or ssh["pid"] < 1
    ):
        raise HerdrPuppetError(
            "invalid_lease",
            "Lease SSH pid must be a positive integer.",
        )
    argv = ssh.get("argv")
    if (
        not isinstance(argv, list)
        or len(argv) < 2
        or any(not isinstance(value, str) for value in argv)
    ):
        raise HerdrPuppetError(
            "invalid_lease",
            "Lease SSH argv must contain at least two string values.",
        )
    ssh_target = _require_string(ssh, "target")
    source = _require_exact_object_fields(
        payload,
        "source",
        {"repo", "worktree"},
    )
    for key in ("repo", "worktree"):
        _require_string(source, key)
    binding: dict[str, Any] | None = None
    if "harness_binding" in payload:
        historical_binding = payload["harness_binding"]
        if lease_version == 1 and (
            not isinstance(historical_binding, dict)
            or historical_binding.get("schema")
            not in {
                "herdr-puppet.harness-binding.v1",
                "herdr-puppet.harness-binding.v2",
            }
        ):
            raise HerdrPuppetError(
                "invalid_harness_binding",
                "Historical lease-v1 accepts only its frozen binding-v1/v2 authority.",
            )
        binding = _validate_record_binding(payload)
    if lease_version != 1:
        expected_authority = selected_authority_sha256(payload)
        if payload.get("selected_authority_sha256") != expected_authority:
            raise HerdrPuppetError(
                "selected_authority_fingerprint_mismatch",
                "The lease selected-authority fingerprint does not match its facts.",
            )
    if "harness_launch" in payload:
        if binding is None:
            raise HerdrPuppetError(
                "invalid_lease",
                "A harness launch record requires a harness binding.",
            )
        _validate_harness_launch_record(
            payload["harness_launch"],
            binding=binding,
            next_seq=payload["next_seq"],
        )
    startup_gate_operations: list[dict[str, Any]] = []
    if "startup_gate_operations" in payload:
        operations = payload["startup_gate_operations"]
        if binding is None or (
            operations and "harness_launch" not in payload
        ):
            raise HerdrPuppetError(
                "invalid_lease",
                "Startup-gate operations require a bound harness launch.",
            )
        startup_gate_operations = _validate_startup_gate_operations(
            operations,
            harness=payload["harness"],
            next_seq=payload["next_seq"],
        )
    if payload.get("shell_readiness", "unverified") not in {
        "unverified",
        SHELL_READY,
    }:
        raise HerdrPuppetError(
            "invalid_lease",
            "Unexpected shell readiness state.",
            details={"shell_readiness": payload.get("shell_readiness")},
        )
    harness_readiness = payload.get("harness_readiness", "unverified")
    allowed_harness_readiness = {"unverified", HARNESS_READY}
    if lease_version == 1:
        allowed_harness_readiness.add(LEGACY_HARNESS_STATUS)
    if lease_version == 3:
        allowed_harness_readiness.update(
            {HARNESS_CHECKPOINT_PENDING, HARNESS_CHECKPOINT_READY}
        )
    if harness_readiness not in allowed_harness_readiness:
        raise HerdrPuppetError(
            "invalid_lease",
            "Unexpected harness readiness state.",
            details={"harness_readiness": harness_readiness},
        )
    for field in CONTROLLER_FILE_FIELDS:
        if field in payload:
            _as_text_file_list(payload[field])
    _as_remote_task_files(
        payload.get("remote_task_files", []),
        expected_ssh_target=ssh_target,
    )
    interactive_sends = _as_interactive_sends(
        payload.get("interactive_sends", []),
        next_seq=payload["next_seq"],
    )
    pending_interactive_send = _as_pending_interactive_send(
        payload.get("pending_interactive_send"),
        next_seq=payload["next_seq"],
        completed_sends=interactive_sends,
    )
    pending_sequence_operation = _as_pending_sequence_operation(
        payload.get("pending_sequence_operation"),
        next_seq=payload["next_seq"],
    )
    readiness_evidence_fields = {
        "harness_readiness_evidence",
        "harness_readiness_operator",
        "harness_readiness_verified_at",
        "harness_readiness_submission_seq",
        "harness_readiness_nonce_sha256",
    }
    if harness_readiness == HARNESS_READY:
        if (
            (lease_version == 3 and payload["harness"] == "agy")
            or payload.get("shell_readiness") != SHELL_READY
            or "harness_launch" not in payload
            or (
                payload["harness"] == "cursor"
                and not any(
                    operation.get("gate") == "workspace_trust"
                    for operation in startup_gate_operations
                )
            )
            or payload.get("harness_readiness_evidence")
            != "operator_observed_ready_input"
            or not isinstance(payload.get("harness_readiness_operator"), str)
            or not re.fullmatch(
                r"[A-Za-z0-9._@:-]{1,128}",
                payload["harness_readiness_operator"],
            )
            or not _is_rfc3339_timestamp(
                payload.get("harness_readiness_verified_at")
            )
            or "harness_readiness_submission_seq" in payload
            or "harness_readiness_nonce_sha256" in payload
        ):
            raise HerdrPuppetError(
                "invalid_lease",
                "Operator-verified readiness requires shell and launch proof, "
                "all required startup gates, bounded operator evidence, and a "
                "verification time.",
            )
    elif harness_readiness == HARNESS_CHECKPOINT_PENDING:
        readiness_seq = payload.get("harness_readiness_submission_seq")
        if (
            payload["harness"] != "agy"
            or payload.get("shell_readiness") != SHELL_READY
            or "harness_launch" not in payload
            or len(interactive_sends) != 1
            or interactive_sends[0]["phase"] != "initial"
            or startup_gate_operations
            or isinstance(readiness_seq, bool)
            or not isinstance(readiness_seq, int)
            or readiness_seq != interactive_sends[0]["seq"]
            or readiness_seq != payload["harness_launch"]["seq"] + 1
            or re.fullmatch(
                r"[0-9a-f]{64}",
                str(payload.get("harness_readiness_nonce_sha256", "")),
            )
            is None
            or pending_interactive_send is not None
            or pending_sequence_operation is not None
            or any(
                field in payload
                for field in {
                    "harness_readiness_evidence",
                    "harness_readiness_operator",
                    "harness_readiness_verified_at",
                }
            )
        ):
            raise HerdrPuppetError(
                "invalid_lease",
                "Checkpoint-pending readiness is limited to one acknowledged "
                "wrapped AGY initial send and its exact expected nonce after "
                "the bound launch.",
            )
    elif harness_readiness == HARNESS_CHECKPOINT_READY:
        readiness_seq = payload.get("harness_readiness_submission_seq")
        if (
            payload["harness"] != "agy"
            or payload.get("shell_readiness") != SHELL_READY
            or "harness_launch" not in payload
            or not interactive_sends
            or interactive_sends[0]["phase"] != "initial"
            or startup_gate_operations
            or isinstance(readiness_seq, bool)
            or not isinstance(readiness_seq, int)
            or readiness_seq != interactive_sends[0]["seq"]
            or readiness_seq != payload["harness_launch"]["seq"] + 1
            or payload.get("harness_readiness_evidence")
            != "strict_initial_status_checkpoint"
            or "harness_readiness_operator" in payload
            or pending_sequence_operation is not None
            or not _is_rfc3339_timestamp(
                payload.get("harness_readiness_verified_at")
            )
            or re.fullmatch(
                r"[0-9a-f]{64}",
                str(payload.get("harness_readiness_nonce_sha256", "")),
            )
            is None
        ):
            raise HerdrPuppetError(
                "invalid_lease",
                "Checkpoint-verified readiness requires one exact AGY initial "
                "send and its strict STATUS nonce evidence.",
            )
    elif (
        any(field in payload for field in readiness_evidence_fields)
        or (
            lease_version == 3
            and harness_readiness == "unverified"
            and bool(interactive_sends)
        )
    ):
        raise HerdrPuppetError(
            "invalid_lease",
            "Unverified or legacy readiness may not carry completed readiness "
            "evidence, and active unverified readiness may not carry a "
            "completed interactive send.",
        )
    if (
        pending_interactive_send is not None
        and pending_sequence_operation is not None
    ):
        raise HerdrPuppetError(
            "invalid_lease",
            "Only one pending Herdr mutation may exist.",
        )
    if (
        "preserved_reason" in payload
        and payload["preserved_reason"] not in PRESERVE_REASONS
    ):
        raise HerdrPuppetError(
            "invalid_lease",
            "Lease preservation reason is unsupported.",
        )
    if (
        "preserved_at" in payload
        and not _is_rfc3339_timestamp(payload["preserved_at"])
    ):
        raise HerdrPuppetError(
            "invalid_lease",
            "Lease preservation time must be RFC 3339.",
        )
    cleanup_fields = {
        "cleanup_state",
        "cleanup_verified_at",
        "cleanup_reconciled_absence",
    }
    if cleanup_fields.intersection(payload):
        if (
            not cleanup_fields.issubset(payload)
            or payload["state"] != "preserved"
            or payload.get("cleanup_state") != "closed"
            or not _is_rfc3339_timestamp(
                payload.get("cleanup_verified_at")
            )
            or not isinstance(payload.get("cleanup_reconciled_absence"), bool)
        ):
            raise HerdrPuppetError(
                "invalid_cleanup_record",
                "A closed cleanup record requires a preserved lease and "
                "complete verification fields.",
            )


def migrate_legacy_lease(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("schema") == LEASE_SCHEMA:
        validate_lease(payload)
        return json.loads(json.dumps(payload))
    validate_legacy_lease(payload)
    if "harness_binding" not in payload:
        raise HerdrPuppetError(
            "legacy_harness_binding_unavailable",
            "An unbound historical lease cannot be attested retroactively.",
        )
    migrated = json.loads(json.dumps(payload))
    migrated["schema"] = LEASE_SCHEMA
    legacy_status_ready = (
        migrated.get("harness_readiness") == LEGACY_HARNESS_STATUS
    )
    if "shell_readiness" not in migrated or legacy_status_ready:
        migrated["shell_readiness"] = (
            SHELL_READY if legacy_status_ready else "unverified"
        )
    if (
        "harness_readiness" not in migrated
        or migrated["harness_readiness"] == LEGACY_HARNESS_STATUS
    ):
        migrated["harness_readiness"] = "unverified"
    if (
        migrated["harness"] == "agy"
        and migrated["harness_readiness"] == HARNESS_READY
    ):
        # Frozen lease-v1/v2 allowed operator-ready AGY rows. Active lease-v3
        # makes AGY readiness checkpoint-driven, so explicit migration keeps
        # the row maintainable but never carries the old human observation
        # forward as pane-input authority.
        if migrated.get("interactive_sends"):
            raise HerdrPuppetError(
                "legacy_agy_readiness_requires_fresh_row",
                "A historical AGY row with completed input remains maintainable "
                "as a historical lease but cannot migrate its operator readiness into the "
                "checkpoint-driven active state; preserve it and create a fresh row.",
            )
        migrated["harness_readiness"] = "unverified"
        migrated.pop("harness_readiness_evidence", None)
        migrated.pop("harness_readiness_operator", None)
        migrated.pop("harness_readiness_verified_at", None)
    migrated.setdefault("caller_text_files", [])
    migrated.setdefault("caller_text_files_removed", [])
    migrated.setdefault("remote_task_files", [])
    migrated.setdefault("interactive_sends", [])
    migrated.setdefault("pending_interactive_send", None)
    migrated.setdefault("pending_sequence_operation", None)
    migrated.setdefault("startup_gate_operations", [])
    migrated["destination_selection"] = destination_selection_for_record(payload)
    migrated["selected_authority_sha256"] = selected_authority_sha256(migrated)
    validate_lease(migrated)
    return migrated


def migrate_legacy_lease_file(
    *,
    lease_payload: dict[str, Any],
    lease_path: Path,
    receipt_schema: str = "herdr-puppet.lease-migrate.v1",
) -> dict[str, Any]:
    if receipt_schema not in {
        "herdr-puppet.lease-migrate.v1",
        "herdr-puppet.lease-migrate-v1.v1",
    }:
        raise HerdrPuppetError(
            "invalid_migration_receipt_schema",
            "Migration receipt schema must be a controller-owned supported value.",
        )
    if lease_payload.get("schema") == LEASE_SCHEMA:
        validate_lease(lease_payload)
    else:
        validate_legacy_lease(lease_payload)
    with _lease_lock(lease_path) as locked_lease_path:
        current = load_json(locked_lease_path)
        if current.get("schema") == LEASE_SCHEMA:
            validate_lease(current)
        else:
            validate_legacy_lease(current)
        _assert_same_lease_identity(lease_payload, current)
        migrated = migrate_legacy_lease(current)
        changed_fields = sorted(
            field
            for field in LEASE_FIELDS
            if (field in current) != (field in migrated)
            or current.get(field) != migrated.get(field)
        )
        if changed_fields:
            atomic_json(locked_lease_path, migrated)
    return {
        "schema": receipt_schema,
        "result": "ok",
        "run_id": migrated["run_id"],
        "migrated": bool(changed_fields),
        "changed_fields": changed_fields,
        "shell_readiness": migrated["shell_readiness"],
        "harness_readiness": migrated["harness_readiness"],
        "herdr_mutated": False,
        "transcript_read": False,
    }


def _version_from_text(version_text: str) -> str:
    match = re.fullmatch(r"herdr\s+([0-9]+\.[0-9]+\.[0-9]+)", version_text.strip())
    if not match:
        raise HerdrPuppetError(
            "invalid_herdr_version",
            "Herdr returned an unrecognized version string.",
        )
    return match.group(1)


def doctor(
    client: HerdrClient,
    session: str,
    *,
    facts: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if facts is None:
        version_text = client.version_text()
        server = client.server_status(session)
        sessions = client.sessions()
    else:
        version_text = _require_string(facts, "version_text")
        server = facts.get("server_status")
        sessions = facts.get("sessions")
        if not isinstance(server, dict) or not isinstance(sessions, list):
            raise HerdrPuppetError(
                "invalid_doctor_facts",
                "Doctor fixture is missing server_status or sessions.",
            )

    version = _version_from_text(version_text)
    matches = [item for item in sessions if item.get("name") == session]
    blockers: list[str] = []
    if version != SUPPORTED_HERDR_VERSION:
        blockers.append("unsupported_herdr_version")
    if server.get("version") != SUPPORTED_HERDR_VERSION:
        blockers.append("server_version_mismatch")
    if server.get("protocol") != SUPPORTED_HERDR_PROTOCOL:
        blockers.append("unsupported_herdr_protocol")
    if server.get("session") != session:
        blockers.append("server_session_mismatch")
    if server.get("running") is not True or server.get("status") != "running":
        blockers.append("server_not_running")
    if server.get("compatible") is not True:
        blockers.append("server_incompatible")
    if not isinstance(server.get("socket"), str) or not server["socket"]:
        blockers.append("server_socket_missing")
    if len(matches) != 1 or matches[0].get("running") is not True:
        blockers.append("session_inventory_ambiguous")

    return {
        "schema": "herdr-puppet.doctor.v1",
        "result": "ok" if not blockers else "blocked",
        "session": session,
        "version": version,
        "protocol": server.get("protocol"),
        "socket": server.get("socket"),
        "blockers": blockers,
        "safety": {
            "mutated": False,
            "pane_read": False,
            "parent_session_mutation": False,
        },
    }


def _reject_duplicate_json_fields(
    pairs: list[tuple[str, Any]],
) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON field")
        value[key] = item
    return value


def validate_destination_catalog(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {"schema", "profiles"}:
        raise HerdrPuppetError(
            "invalid_destination_catalog",
            "The destination catalog must contain exactly schema and profiles.",
        )
    if value["schema"] != DESTINATION_CATALOG_SCHEMA:
        raise HerdrPuppetError(
            "invalid_destination_catalog",
            "The destination catalog schema is unsupported.",
        )
    profiles = value["profiles"]
    if not isinstance(profiles, list) or not profiles or len(profiles) > 64:
        raise HerdrPuppetError(
            "invalid_destination_catalog",
            "The destination catalog profiles are missing or unbounded.",
        )
    normalized: list[dict[str, str]] = []
    names: set[str] = set()
    labels: set[str] = set()
    for profile in profiles:
        if not isinstance(profile, dict) or set(profile) != {
            "name",
            "workspace_label",
            "ssh_target",
        }:
            raise HerdrPuppetError(
                "invalid_destination_catalog",
                "Each destination profile must contain exactly name, "
                "workspace_label, and ssh_target.",
            )
        name = profile["name"]
        workspace_label = profile["workspace_label"]
        ssh_target = profile["ssh_target"]
        if (
            not isinstance(name, str)
            or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", name)
            is None
            or not isinstance(workspace_label, str)
            or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._ -]{0,127}", workspace_label)
            is None
            or not isinstance(ssh_target, str)
            or len(ssh_target) > 320
            or re.fullmatch(
                r"(?:[A-Za-z0-9._-]+@)?[A-Za-z0-9][A-Za-z0-9._-]{0,254}",
                ssh_target,
            )
            is None
        ):
            raise HerdrPuppetError(
                "invalid_destination_catalog",
                "A destination profile contains an invalid bounded value.",
            )
        if name in names or workspace_label in labels:
            raise HerdrPuppetError(
                "invalid_destination_catalog",
                "Destination names and workspace labels must be unique.",
            )
        names.add(name)
        labels.add(workspace_label)
        normalized.append(
            {
                "name": name,
                "workspace_label": workspace_label,
                "ssh_target": ssh_target,
            }
        )
    return {"schema": DESTINATION_CATALOG_SCHEMA, "profiles": normalized}


def load_destination_catalog(path: str | Path) -> dict[str, Any]:
    catalog_path = Path(path)
    descriptor: int | None = None
    try:
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NONBLOCK", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(catalog_path, flags)
        identity = os.fstat(descriptor)
        if (
            not stat.S_ISREG(identity.st_mode)
            or identity.st_uid != os.getuid()
            or identity.st_size > MAX_DESTINATION_CATALOG_BYTES
        ):
            raise OSError("catalog is not a caller-owned bounded regular file")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            encoded = stream.read(MAX_DESTINATION_CATALOG_BYTES + 1)
        if len(encoded) > MAX_DESTINATION_CATALOG_BYTES:
            raise OSError("catalog is oversized")
        value = json.loads(
            encoded.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_json_fields,
        )
    except (OSError, UnicodeDecodeError, ValueError, RecursionError) as exc:
        raise HerdrPuppetError(
            "invalid_destination_catalog",
            "The destination catalog is unavailable or malformed.",
        ) from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
    return validate_destination_catalog(value)


def _validate_destination_selection(value: Any) -> dict[str, Any]:
    fields = {
        "schema",
        "mode",
        "machine",
        "workspace_label",
        "tab",
        "legacy_ordinal_alias",
        "catalog_path_retained",
        "ssh_target_retained",
        "existing_tab_adoption",
    }
    if not isinstance(value, dict) or set(value) != fields:
        raise HerdrPuppetError(
            "invalid_destination_selection",
            "The destination selection receipt shape is invalid.",
        )
    mode = value["mode"]
    machine = value["machine"]
    if mode not in {"named_catalog", "legacy_explicit"}:
        raise HerdrPuppetError(
            "invalid_destination_selection",
            "The destination selection mode is invalid.",
        )
    if (
        value["schema"] != DESTINATION_RECEIPT_SCHEMA
        or not isinstance(value["workspace_label"], str)
        or not value["workspace_label"]
        or len(value["workspace_label"]) > 128
        or any(
            character in value["workspace_label"]
            for character in "\x00\r\n"
        )
        or value["catalog_path_retained"] is not False
        or value["ssh_target_retained"] is not False
        or value["existing_tab_adoption"] is not False
        or not isinstance(value["legacy_ordinal_alias"], bool)
        or (
            mode == "named_catalog"
            and (
                not isinstance(machine, str)
                or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", machine)
                is None
            )
        )
        or (mode == "legacy_explicit" and machine is not None)
    ):
        raise HerdrPuppetError(
            "invalid_destination_selection",
            "The destination selection receipt is not sanitized and bounded.",
        )
    tab = value["tab"]
    if (
        not isinstance(tab, dict)
        or set(tab) != {"request", "ordinal"}
        or tab["request"] != "fresh"
        or isinstance(tab["ordinal"], bool)
        or not isinstance(tab["ordinal"], int)
        or tab["ordinal"] < 1
        or tab["ordinal"] > 999
    ):
        raise HerdrPuppetError(
            "invalid_destination_selection",
            "Every destination selection must request one fresh bounded tab.",
        )
    return value


def _destination_selection_receipt(
    *,
    mode: str,
    machine: str | None,
    workspace_label: str,
    tab_ordinal: int,
    legacy_ordinal_alias: bool,
) -> dict[str, Any]:
    receipt = {
        "schema": DESTINATION_RECEIPT_SCHEMA,
        "mode": mode,
        "machine": machine,
        "workspace_label": workspace_label,
        "tab": {"request": "fresh", "ordinal": tab_ordinal},
        "legacy_ordinal_alias": legacy_ordinal_alias,
        "catalog_path_retained": False,
        "ssh_target_retained": False,
        "existing_tab_adoption": False,
    }
    _validate_destination_selection(receipt)
    return receipt


def _find_workspace(
    workspaces: list[dict[str, Any]],
    workspace_id: str,
    workspace_label: str,
) -> dict[str, Any]:
    matches = [
        item
        for item in workspaces
        if item.get("workspace_id") == workspace_id
        and item.get("label") == workspace_label
    ]
    if len(matches) != 1:
        raise HerdrPuppetError(
            "workspace_capability_mismatch",
            "The exact workspace ID and label did not resolve once.",
            details={"workspace_id": workspace_id, "workspace_label": workspace_label},
        )
    return matches[0]


def _find_workspace_by_label(
    workspaces: list[dict[str, Any]],
    workspace_label: str,
) -> dict[str, Any]:
    matches = [
        item for item in workspaces if item.get("label") == workspace_label
    ]
    if (
        len(matches) != 1
        or not isinstance(matches[0].get("workspace_id"), str)
        or not matches[0]["workspace_id"]
    ):
        raise HerdrPuppetError(
            "workspace_capability_mismatch",
            "The named destination workspace label did not resolve once.",
            details={"workspace_label": workspace_label},
        )
    return matches[0]


def _label(run_id: str, harness: str, ordinal: int) -> str:
    return deterministic_owned_label(run_id, harness, ordinal)


def plan(
    client: HerdrClient,
    *,
    session: str,
    workspace_id: str | None = None,
    workspace_label: str | None = None,
    expected_ssh_target: str | None = None,
    machine: str | None = None,
    destination_catalog: dict[str, Any] | None = None,
    run_id: str,
    harness: str,
    repo: str,
    worktree: str,
    proof_root: str,
    harness_binding: dict[str, Any],
    tab_ordinal: int | None = None,
    ordinal: int | None = None,
    live_mutation_authorized: bool = False,
    facts: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if tab_ordinal is not None and ordinal is not None:
        raise HerdrPuppetError(
            "destination_ordinal_conflict",
            "Use --tab-ordinal or the deprecated --ordinal alias, not both.",
        )
    selected_ordinal = (
        tab_ordinal if tab_ordinal is not None else ordinal
    )
    if selected_ordinal is None:
        selected_ordinal = 1
    if (
        isinstance(selected_ordinal, bool)
        or not isinstance(selected_ordinal, int)
        or selected_ordinal < 1
        or selected_ordinal > 999
    ):
        raise HerdrPuppetError(
            "invalid_tab_ordinal",
            "Tab ordinal must be an integer from 1 through 999.",
        )
    legacy_values = (workspace_id, workspace_label, expected_ssh_target)
    named_requested = machine is not None or destination_catalog is not None
    if named_requested:
        if (
            machine is None
            or destination_catalog is None
            or any(value is not None for value in legacy_values)
        ):
            raise HerdrPuppetError(
                "destination_route_conflict",
                "Named destination selection and the legacy destination triple "
                "are mutually exclusive and complete routes.",
            )
        catalog = validate_destination_catalog(destination_catalog)
        profile_matches = [
            profile
            for profile in catalog["profiles"]
            if profile["name"] == machine
        ]
        if len(profile_matches) != 1:
            raise HerdrPuppetError(
                "destination_machine_not_found",
                "The named destination did not resolve exactly once.",
            )
        selected_profile = profile_matches[0]
        selected_workspace_label = selected_profile["workspace_label"]
        selected_ssh_target = selected_profile["ssh_target"]
        destination_mode = "named_catalog"
    else:
        if any(value is None for value in legacy_values):
            raise HerdrPuppetError(
                "destination_route_incomplete",
                "Supply --machine with a catalog or the complete legacy "
                "workspace/SSH destination triple.",
            )
        assert workspace_label is not None
        assert expected_ssh_target is not None
        selected_workspace_label = workspace_label
        selected_ssh_target = expected_ssh_target
        destination_mode = "legacy_explicit"
    if harness not in CANONICAL_HARNESSES:
        raise HerdrPuppetError(
            "noncanonical_harness",
            "Harness must be one of agy, codex, claude, cursor, or grok.",
        )
    checked_binding = validate_harness_binding(
        harness_binding,
        expected_harness=harness,
        expected_repo=repo,
        expected_worktree=worktree,
    )
    if (
        harness == "claude"
        and checked_binding["lifecycle_observation"]["run_id"] != run_id
    ):
        raise HerdrPuppetError(
            "claude_lifecycle_run_mismatch",
            "The Claude lifecycle observation must bind the exact plan run id.",
        )
    doctor_facts = facts.get("doctor") if facts else None
    doctor_result = doctor(client, session, facts=doctor_facts)
    if doctor_result["result"] != "ok":
        raise HerdrPuppetError(
            "doctor_blocked",
            "Herdr doctor must pass before planning.",
            details={"blockers": doctor_result["blockers"]},
        )
    if facts is None:
        workspaces = client.snapshot(session)["workspaces"]
    else:
        workspaces = facts.get("workspaces")
        if not isinstance(workspaces, list):
            raise HerdrPuppetError(
                "invalid_plan_facts",
                "Plan fixture is missing workspaces.",
            )
    if named_requested:
        workspace = _find_workspace_by_label(
            workspaces,
            selected_workspace_label,
        )
        selected_workspace_id = workspace["workspace_id"]
    else:
        assert workspace_id is not None
        _find_workspace(workspaces, workspace_id, selected_workspace_label)
        selected_workspace_id = workspace_id
    destination_selection = _destination_selection_receipt(
        mode=destination_mode,
        machine=machine,
        workspace_label=selected_workspace_label,
        tab_ordinal=selected_ordinal,
        legacy_ordinal_alias=ordinal is not None,
    )
    payload = {
        "schema": PLAN_SCHEMA,
        "state": "planned",
        "run_id": run_id,
        "harness": harness,
        "session": {
            "name": session,
            "version": doctor_result["version"],
            "protocol": doctor_result["protocol"],
            "socket": doctor_result["socket"],
            "incarnation_proven": False,
        },
        "workspace": {
            "id": selected_workspace_id,
            "label": selected_workspace_label,
        },
        "destination_selection": destination_selection,
        "expected_ssh_target": selected_ssh_target,
        "owned_label": _label(run_id, harness, selected_ordinal),
        "source": {"repo": repo, "worktree": worktree},
        "harness_binding": checked_binding,
        "proof_root": proof_root,
        "safety": {
            "parent_session_mutation": False,
            "adopt_existing_tab": False,
            "ordinary_transcript_read": False,
            "live_mutation_authorized": bool(live_mutation_authorized),
        },
    }
    payload["selected_authority_sha256"] = selected_authority_sha256(payload)
    validate_plan(payload)
    return payload


def plan_selection_receipt(payload: dict[str, Any]) -> dict[str, Any]:
    validate_plan(payload)
    return {
        "schema": "herdr-puppet.plan-selection-receipt.v1",
        "result": "ok",
        "run_id": payload["run_id"],
        "harness": payload["harness"],
        "owned_label": payload["owned_label"],
        "destination_selection": dict(payload["destination_selection"]),
        "workspace_id_retained": False,
        "ssh_target_retained": False,
        "catalog_path_retained": False,
        "fresh_tab_required": True,
        "harness_binding_fingerprint": payload["harness_binding"][
            "fingerprint"
        ],
    }


def _expected_ssh_process(
    process_info: dict[str, Any],
    expected_target: str,
) -> dict[str, Any]:
    processes = process_info.get("foreground_processes")
    if not isinstance(processes, list):
        raise HerdrPuppetError(
            "invalid_foreground_processes",
            "Foreground process inventory is missing.",
        )
    matches = []
    for item in processes:
        argv = item.get("argv")
        if not isinstance(argv, list) or not argv:
            continue
        executable = Path(str(argv[0])).name
        if executable == "ssh" and expected_target in argv[1:]:
            matches.append(item)
    if len(matches) != 1:
        raise HerdrPuppetError(
            "ssh_identity_mismatch",
            "The pane does not contain exactly one expected foreground SSH process.",
            details={"expected_target": expected_target},
        )
    if not isinstance(matches[0].get("pid"), int) or matches[0]["pid"] < 1:
        raise HerdrPuppetError("invalid_ssh_pid", "The SSH PID is invalid.")
    return matches[0]


def structural_status(
    client: HerdrClient,
    *,
    plan_payload: dict[str, Any] | None = None,
    lease_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if (plan_payload is None) == (lease_payload is None):
        raise HerdrPuppetError(
            "status_record_ambiguous",
            "Provide exactly one plan or lease to status.",
        )
    payload = lease_payload if lease_payload is not None else plan_payload
    assert payload is not None
    if lease_payload is not None:
        _validate_maintainable_lease(payload, allow_historical=True)
    else:
        if payload.get("schema") == HISTORICAL_PLAN_SCHEMA:
            validate_historical_plan(payload)
        else:
            validate_plan(payload)
    session = payload["session"]["name"]
    doctor_result = doctor(client, session)
    if doctor_result["result"] != "ok":
        return {
            "schema": "herdr-puppet.status.v1",
            "result": "blocked",
            "run_id": payload["run_id"],
            "blockers": doctor_result["blockers"],
            "transcript_read": False,
        }
    snapshot = client.snapshot(session)
    workspaces = snapshot["workspaces"]
    _find_workspace(
        workspaces,
        payload["workspace"]["id"],
        payload["workspace"]["label"],
    )
    tabs = [
        item
        for item in snapshot["tabs"]
        if item.get("workspace_id") == payload["workspace"]["id"]
    ]
    panes = [
        item
        for item in snapshot["panes"]
        if item.get("workspace_id") == payload["workspace"]["id"]
    ]
    snapshot_blockers: list[str] = []
    if doctor_result["socket"] != payload["session"]["socket"]:
        snapshot_blockers.append("server_socket_drift")
    if snapshot.get("version") != payload["session"]["version"]:
        snapshot_blockers.append("snapshot_version_drift")
    if snapshot.get("protocol") != payload["session"]["protocol"]:
        snapshot_blockers.append("snapshot_protocol_drift")
    if lease_payload is None:
        label_matches = [
            item for item in tabs if item.get("label") == payload["owned_label"]
        ]
        return {
            "schema": "herdr-puppet.status.v1",
            "result": "ok" if not label_matches and not snapshot_blockers else "blocked",
            "run_id": payload["run_id"],
            "state": "planned",
            "blockers": snapshot_blockers
            + ([] if not label_matches else ["owned_label_already_exists"]),
            "workspace": payload["workspace"],
            "owned_label": payload["owned_label"],
            "transcript_read": False,
        }

    tab_matches = [
        item
        for item in tabs
        if item.get("tab_id") == payload["tab_id"]
        and item.get("workspace_id") == payload["workspace"]["id"]
    ]
    pane_matches = [
        item
        for item in panes
        if item.get("pane_id") == payload["pane_id"]
        and item.get("tab_id") == payload["tab_id"]
        and item.get("workspace_id") == payload["workspace"]["id"]
    ]
    blockers: list[str] = list(snapshot_blockers)
    if len(tab_matches) != 1:
        blockers.append("leased_tab_missing_or_ambiguous")
    elif tab_matches[0].get("label") != payload["owned_label"]:
        blockers.append("leased_tab_label_drift")
    if len(pane_matches) != 1:
        blockers.append("leased_pane_missing_or_ambiguous")
    elif pane_matches[0].get("terminal_id") != payload["terminal_id"]:
        blockers.append("leased_terminal_drift")
    process: dict[str, Any] | None = None
    if not blockers:
        process_info = client.process_info(session, payload["pane_id"])
        try:
            process = _expected_ssh_process(
                process_info,
                payload["ssh"]["target"],
            )
        except HerdrPuppetError as exc:
            blockers.append(exc.code)
        if process and (
            process.get("pid") != payload["ssh"]["pid"]
            or process.get("argv") != payload["ssh"]["argv"]
        ):
            blockers.append("leased_ssh_process_drift")
    return {
        "schema": "herdr-puppet.status.v1",
        "result": "ok" if not blockers else "blocked",
        "run_id": payload["run_id"],
        "state": payload["state"],
        "blockers": blockers,
        "workspace_id": payload["workspace"]["id"],
        "tab_id": payload["tab_id"],
        "pane_id": payload["pane_id"],
        "terminal_id": payload["terminal_id"],
        "ssh_pid": process.get("pid") if process else None,
        "next_seq": payload["next_seq"],
        "harness_binding_fingerprint": (
            payload["harness_binding"]["fingerprint"]
            if isinstance(payload.get("harness_binding"), dict)
            else None
        ),
        "capabilities": (
            dict(payload["harness_binding"]["capabilities"])
            if isinstance(payload.get("harness_binding"), dict)
            else {
                "remote_harness_pid": "unavailable",
                "targeted_halt": "unsupported",
                "recovery": "unsupported",
                "crash_persistence": "unsupported",
            }
        ),
        "transcript_read": False,
    }


def register_remote_task_file(
    *,
    lease_payload: dict[str, Any],
    lease_path: Path,
    remote_path: str,
    source_repo: str,
    source_worktree: str,
    confirm_caller_owned: bool,
    run_root: Path,
) -> dict[str, Any]:
    validate_lease(lease_payload)
    _require_active_lease_journal(run_root, lease_payload)
    if not confirm_caller_owned:
        raise HerdrPuppetError(
            "remote_task_file_ownership_not_confirmed",
            "Remote task-file registration requires caller ownership confirmation.",
        )
    normalized_path = _normalize_remote_task_path(remote_path)
    with _lease_lock(lease_path) as locked_lease_path:
        current = _reload_locked_lease(lease_payload, locked_lease_path)
        _require_current_record_binding(current)
        if current["state"] != "active":
            raise HerdrPuppetError("lease_not_active", "The lease is not active.")
        if (
            current["source"].get("repo") != source_repo
            or current["source"].get("worktree") != source_worktree
        ):
            raise HerdrPuppetError(
                "remote_task_file_source_mismatch",
                "Remote task-file registration must bind to the exact leased source.",
            )
        remote_files = _as_remote_task_files(
            current.get("remote_task_files", []),
            expected_ssh_target=current["ssh"]["target"],
        )
        matches = [item for item in remote_files if item["path"] == normalized_path]
        if matches and matches[0]["state"] == REMOTE_FILE_REMOVED:
            raise HerdrPuppetError(
                "remote_task_file_already_removed",
                "A removal-verified remote task file may not be re-registered.",
            )
        already_registered = bool(matches)
        if not already_registered:
            remote_files.append(
                {
                    "path": normalized_path,
                    "ssh_target": current["ssh"]["target"],
                    "state": REMOTE_FILE_REGISTERED,
                    "registered_at": now(),
                }
            )
            updated = json.loads(json.dumps(current))
            updated["remote_task_files"] = remote_files
            atomic_json(locked_lease_path, updated)
            append_event(
                run_root,
                make_event(
                    updated["run_id"],
                    "qualification.remote-task-file-registered",
                    "observed",
                    data={
                        "remote_task_file_location": "remote",
                        "remote_task_file_registered": True,
                        "remote_task_file_count": len(remote_files),
                        "path_emitted": False,
                        "path_hashed": False,
                        "source_binding_verified": True,
                    },
                ),
            )
        else:
            updated = current
    return {
        "schema": "herdr-puppet.remote-task-file-register.v1",
        "result": "ok",
        "run_id": updated["run_id"],
        "remote_task_file_location": "remote",
        "remote_task_file_registered": True,
        "remote_task_file_count": len(remote_files),
        "already_registered": already_registered,
        "path_emitted": False,
        "path_hashed": False,
        "source_binding_verified": True,
    }


def maintenance_checkpoint(
    client: HerdrClient,
    *,
    lease_payload: dict[str, Any],
    lease_path: Path,
    run_root: Path,
    remote_removed_path: str | None = None,
    remote_removal_evidence: str | None = None,
    confirm_remote_removed: bool = False,
) -> dict[str, Any]:
    _validate_maintainable_lease(lease_payload, allow_historical=True)
    removal_requested = any(
        (
            remote_removed_path is not None,
            remote_removal_evidence is not None,
            confirm_remote_removed,
        )
    )
    if removal_requested and (
        remote_removed_path is None
        or remote_removal_evidence not in REMOTE_REMOVAL_EVIDENCE
        or not confirm_remote_removed
    ):
        raise HerdrPuppetError(
            "remote_removal_evidence_incomplete",
            "Remote removal requires an exact registered path, bounded evidence, "
            "and explicit confirmation.",
        )
    require_initialized_journal(
        run_root,
        lease_payload=lease_payload,
        allow_historical_plan=True,
    )
    with _lease_lock(lease_path) as locked_lease_path:
        current = _reload_locked_lease(
            lease_payload,
            locked_lease_path,
            allow_historical=True,
        )
        return _maintenance_checkpoint_locked(
            client,
            lease_payload=current,
            lease_path=locked_lease_path,
            run_root=run_root,
            remote_removed_path=remote_removed_path,
            remote_removal_evidence=remote_removal_evidence,
            confirm_remote_removed=confirm_remote_removed,
        )


def _maintenance_checkpoint_locked(
    client: HerdrClient,
    *,
    lease_payload: dict[str, Any],
    lease_path: Path,
    run_root: Path,
    remote_removed_path: str | None,
    remote_removal_evidence: str | None,
    confirm_remote_removed: bool,
) -> dict[str, Any]:
    _validate_maintainable_lease(lease_payload, allow_historical=True)
    current_from_disk = load_json(lease_path)
    _validate_maintainable_lease(current_from_disk, allow_historical=True)
    _assert_same_lease_identity(lease_payload, current_from_disk)
    remote_files = _as_remote_task_files(
        current_from_disk.get("remote_task_files", []),
        expected_ssh_target=current_from_disk["ssh"]["target"],
    )
    if remote_removed_path is not None:
        normalized_remote_path = _normalize_remote_task_path(remote_removed_path)
        matches = [
            item for item in remote_files if item["path"] == normalized_remote_path
        ]
        if len(matches) != 1:
            raise HerdrPuppetError(
                "remote_task_file_not_registered",
                "Remote removal evidence must name one exact registered task file.",
            )
        remote_entry = matches[0]
        if remote_entry["state"] == REMOTE_FILE_REMOVED:
            if remote_entry["removal_evidence"] != remote_removal_evidence:
                raise HerdrPuppetError(
                    "remote_removal_evidence_conflict",
                    "Remote removal is already recorded with different evidence.",
                )
        else:
            remote_entry["state"] = REMOTE_FILE_REMOVED
            remote_entry["removal_verified_at"] = now()
            remote_entry["removal_evidence"] = remote_removal_evidence
            current_from_disk = json.loads(json.dumps(current_from_disk))
            current_from_disk["remote_task_files"] = remote_files
            atomic_json(lease_path, current_from_disk)
    lease_payload = current_from_disk
    prompt_files = _as_text_file_list(current_from_disk.get("caller_text_files", []))
    prompt_files_removed = _as_text_file_list(
        current_from_disk.get("caller_text_files_removed", [])
    )
    retained_prompt_files = [
        path
        for path in prompt_files
        if _is_prompt_file_retained(path)
    ]
    removed_prompt_files = [
        path for path in prompt_files if path not in retained_prompt_files
    ]
    updated_prompt_file_state = json.loads(json.dumps(current_from_disk))
    updated_prompt_file_state["caller_text_files"] = _dedupe_preserve_order(
        retained_prompt_files
    )
    updated_prompt_file_state["caller_text_files_removed"] = _dedupe_preserve_order(
        prompt_files_removed + removed_prompt_files
    )
    if updated_prompt_file_state != current_from_disk:
        atomic_json(lease_path, updated_prompt_file_state)
        lease_payload = updated_prompt_file_state
    session = lease_payload["session"]["name"]
    doctor_result = doctor(client, session)
    blockers: list[str] = list(doctor_result["blockers"])
    tab_state = "unverified"
    pane_state = "unverified"
    terminal_state = "unverified"
    ssh_state = "unverified"

    if doctor_result["result"] == "ok":
        snapshot = client.snapshot(session)
        if doctor_result["socket"] != lease_payload["session"]["socket"]:
            blockers.append("server_socket_drift")
        if snapshot.get("version") != lease_payload["session"]["version"]:
            blockers.append("snapshot_version_drift")
        if snapshot.get("protocol") != lease_payload["session"]["protocol"]:
            blockers.append("snapshot_protocol_drift")

        workspace_matches = [
            item
            for item in snapshot["workspaces"]
            if item.get("workspace_id") == lease_payload["workspace"]["id"]
        ]
        if (
            len(workspace_matches) != 1
            or workspace_matches[0].get("label")
            != lease_payload["workspace"]["label"]
        ):
            blockers.append("workspace_capability_mismatch")

        tab_matches = [
            item
            for item in snapshot["tabs"]
            if item.get("tab_id") == lease_payload["tab_id"]
        ]
        pane_matches = [
            item
            for item in snapshot["panes"]
            if item.get("pane_id") == lease_payload["pane_id"]
        ]

        if not tab_matches:
            tab_state = "missing"
        elif len(tab_matches) > 1:
            tab_state = "duplicate"
            blockers.append("leased_tab_duplicate")
        elif tab_matches[0].get("workspace_id") != lease_payload["workspace"]["id"]:
            tab_state = "moved"
            blockers.append("leased_tab_moved")
        elif tab_matches[0].get("label") != lease_payload["owned_label"]:
            tab_state = "label_drift"
            blockers.append("leased_tab_label_drift")
        else:
            tab_state = "present"

        if not pane_matches:
            pane_state = "missing"
        elif len(pane_matches) > 1:
            pane_state = "duplicate"
            blockers.append("leased_pane_duplicate")
        elif (
            pane_matches[0].get("workspace_id")
            != lease_payload["workspace"]["id"]
            or pane_matches[0].get("tab_id") != lease_payload["tab_id"]
        ):
            pane_state = "moved"
            blockers.append("leased_pane_moved")
        elif pane_matches[0].get("terminal_id") != lease_payload["terminal_id"]:
            pane_state = "present"
            terminal_state = "drifted"
            blockers.append("leased_terminal_drift")
        else:
            pane_state = "present"
            terminal_state = "present"

        exact_structure_present = (
            tab_state == "present"
            and pane_state == "present"
            and terminal_state == "present"
        )
        if exact_structure_present and not blockers:
            try:
                process = _expected_ssh_process(
                    client.process_info(session, lease_payload["pane_id"]),
                    lease_payload["ssh"]["target"],
                )
            except HerdrPuppetError as exc:
                blockers.append(exc.code)
            else:
                if (
                    process.get("pid") != lease_payload["ssh"]["pid"]
                    or process.get("argv") != lease_payload["ssh"]["argv"]
                ):
                    blockers.append("leased_ssh_process_drift")
                    ssh_state = "drifted"
                else:
                    ssh_state = "present"

    stale_structure = (
        doctor_result["result"] == "ok"
        and not blockers
        and tab_state == "missing"
        and pane_state == "missing"
    )
    exact_live_structure = (
        doctor_result["result"] == "ok"
        and not blockers
        and tab_state == "present"
        and pane_state == "present"
        and terminal_state == "present"
        and ssh_state == "present"
    )
    if stale_structure:
        classification = "stale"
    elif exact_live_structure:
        classification = lease_payload["state"]
    else:
        classification = "ambiguous"

    cleanup_recorded = lease_payload.get("cleanup_state") == "closed"
    maintenance_candidate = (
        classification == "ambiguous"
        or classification == "stale"
        and not cleanup_recorded
    )
    recommended_action = (
        "none"
        if classification == "stale" and cleanup_recorded
        else
        "preserve_lease"
        if classification == "stale" and lease_payload["state"] == "active"
        else "owner_specific_cleanup_review"
        if classification == "stale"
        else "human_review"
        if classification == "ambiguous"
        else "retain_or_route_exact_cleanup"
        if classification == "preserved"
        else "continue_bounded_run"
    )
    resources = {
        "tab": {"id": lease_payload["tab_id"], "state": tab_state},
        "pane": {"id": lease_payload["pane_id"], "state": pane_state},
        "terminal": {
            "id": lease_payload["terminal_id"],
            "state": terminal_state,
        },
        "ssh": {
            "pid": lease_payload["ssh"]["pid"],
            "state": ssh_state,
        },
    }
    append_event(
        run_root,
        make_event(
            lease_payload["run_id"],
            "maintenance.checkpoint",
            "repair" if maintenance_candidate else "observed",
            data={
                "classification": classification,
                "lease_state": lease_payload["state"],
                "resources": resources,
                "blockers": blockers,
                "maintenance_candidate": maintenance_candidate,
                "recommended_action": recommended_action,
                "cleanup_authorized": False,
                "cleanup_performed": False,
                "herdr_mutated": False,
                "transcript_read": False,
                "caller_text_files": lease_payload.get("caller_text_files", []),
                "caller_text_files_removed": lease_payload.get(
                    "caller_text_files_removed",
                    [],
                ),
                "caller_text_file_location": "controller_local",
                "remote_task_files": lease_payload.get("remote_task_files", []),
                "remote_task_file_location": "remote",
                "remote_removal_verification_required": any(
                    item["state"] == REMOTE_FILE_REGISTERED
                    for item in lease_payload.get("remote_task_files", [])
                ),
            },
        ),
    )
    return {
        "schema": "herdr-puppet.maintenance-checkpoint.v1",
        "result": "ok",
        "run_id": lease_payload["run_id"],
        "classification": classification,
        "lease_state": lease_payload["state"],
        "resources": resources,
        "blockers": blockers,
        "maintenance_candidate": maintenance_candidate,
        "recommended_action": recommended_action,
        "cleanup_authorized": False,
        "cleanup_performed": False,
        "herdr_mutated": False,
        "transcript_read": False,
        "caller_text_files": lease_payload.get("caller_text_files", []),
        "caller_text_files_removed": lease_payload.get(
            "caller_text_files_removed",
            [],
        ),
        "caller_text_file_location": "controller_local",
        "remote_task_files": lease_payload.get("remote_task_files", []),
        "remote_task_file_location": "remote",
        "remote_removal_verification_required": any(
            item["state"] == REMOTE_FILE_REGISTERED
            for item in lease_payload.get("remote_task_files", [])
        ),
    }


def cleanup_preserved_tab(
    client: HerdrClient,
    *,
    lease_payload: dict[str, Any],
    lease_path: Path,
    run_root: Path,
    confirm_tab_id: str,
    allow_live_cleanup: bool,
) -> dict[str, Any]:
    _validate_maintainable_lease(lease_payload, allow_historical=True)
    with _lease_lock(lease_path) as locked_lease_path:
        current = _reload_locked_lease(
            lease_payload,
            locked_lease_path,
            allow_historical=True,
        )
        return _cleanup_preserved_tab_locked(
            client,
            lease_payload=current,
            lease_path=locked_lease_path,
            run_root=run_root,
            confirm_tab_id=confirm_tab_id,
            allow_live_cleanup=allow_live_cleanup,
        )


def _cleanup_preserved_tab_locked(
    client: HerdrClient,
    *,
    lease_payload: dict[str, Any],
    lease_path: Path,
    run_root: Path,
    confirm_tab_id: str,
    allow_live_cleanup: bool,
) -> dict[str, Any]:
    _validate_maintainable_lease(lease_payload, allow_historical=True)
    if lease_payload["state"] != "preserved":
        raise HerdrPuppetError(
            "cleanup_lease_not_preserved",
            "Exact tab cleanup requires a preserved lease.",
        )
    if not allow_live_cleanup:
        raise HerdrPuppetError(
            "live_cleanup_not_authorized",
            "The command flag must explicitly authorize live tab cleanup.",
        )
    if confirm_tab_id != lease_payload["tab_id"]:
        raise HerdrPuppetError(
            "cleanup_tab_confirmation_mismatch",
            "The confirmed tab ID does not match the exact leased tab.",
            details={
                "confirmed_tab_id": confirm_tab_id,
                "leased_tab_id": lease_payload["tab_id"],
            },
        )
    require_initialized_journal(
        run_root,
        lease_payload=lease_payload,
        allow_historical_plan=True,
    )
    current = load_json(lease_path)
    _validate_maintainable_lease(current, allow_historical=True)
    _assert_same_lease_identity(lease_payload, current)
    if current["state"] != "preserved":
        raise HerdrPuppetError(
            "cleanup_lease_not_preserved",
            "The on-disk lease is not preserved.",
        )

    inventory = _maintenance_checkpoint_locked(
        client,
        lease_payload=current,
        lease_path=lease_path,
        run_root=run_root,
        remote_removed_path=None,
        remote_removal_evidence=None,
        confirm_remote_removed=False,
    )
    if inventory["classification"] == "ambiguous":
        raise HerdrPuppetError(
            "cleanup_identity_ambiguous",
            "Exact tab cleanup requires an unambiguous live or absent identity.",
            details={"blockers": inventory["blockers"]},
        )

    after_maintenance = load_json(lease_path)
    _validate_maintainable_lease(after_maintenance, allow_historical=True)
    _assert_same_lease_identity(current, after_maintenance)
    current = after_maintenance
    if any(
        item["state"] == REMOTE_FILE_REGISTERED
        for item in current.get("remote_task_files", [])
    ):
        raise HerdrPuppetError(
            "remote_task_file_removal_unverified",
            "Final maintenance must record exact remote task-file removal "
            "evidence before tab cleanup.",
        )

    already_absent = inventory["classification"] == "stale"
    if current.get("cleanup_state") == "closed":
        if already_absent:
            if not client.wait_pid_absence(current["ssh"]["pid"]):
                raise HerdrPuppetError(
                    "cleanup_ssh_pid_absence_not_verified",
                    "The leased foreground SSH PID is not absent.",
                    details={"ssh_pid": current["ssh"]["pid"]},
                )
            refresh_state(run_root, current)
            return {
                "schema": "herdr-puppet.cleanup-preserved-tab.v1",
                "result": "ok",
                "run_id": current["run_id"],
                "tab_id": current["tab_id"],
                "pane_id": current["pane_id"],
                "cleanup_performed": False,
                "already_closed": True,
                "absence_verified": True,
                "ssh_pid_absence_verified": True,
                "transcript_read": False,
            }
        raise HerdrPuppetError(
            "cleanup_record_conflict",
            "A lease recorded as closed resolved to a live exact identity.",
        )

    append_event(
        run_root,
        make_event(
            current["run_id"],
            "cleanup.requested",
            "observed",
            data={
                "tab_id": current["tab_id"],
                "pane_id": current["pane_id"],
                "confirmed_tab_id": confirm_tab_id,
                "cleanup_authorized": True,
                "transcript_read": False,
            },
        ),
    )

    cleanup_performed = False
    if not already_absent:
        client.close_tab(
            current["session"]["name"],
            current["tab_id"],
        )
        cleanup_performed = True
        after = client.snapshot(current["session"]["name"])
        tab_matches = [
            item
            for item in after["tabs"]
            if item.get("tab_id") == current["tab_id"]
        ]
        pane_matches = [
            item
            for item in after["panes"]
            if item.get("pane_id") == current["pane_id"]
        ]
        if tab_matches or pane_matches:
            raise HerdrPuppetError(
                "cleanup_close_not_verified",
                "Herdr accepted tab close but the exact leased identity remains.",
                details={
                    "tab_present": bool(tab_matches),
                    "pane_present": bool(pane_matches),
                },
            )
    if not client.wait_pid_absence(current["ssh"]["pid"]):
        raise HerdrPuppetError(
            "cleanup_ssh_pid_absence_not_verified",
            "The leased foreground SSH PID is not absent after tab cleanup.",
            details={"ssh_pid": current["ssh"]["pid"]},
        )

    updated = json.loads(json.dumps(current))
    updated["cleanup_state"] = "closed"
    updated["cleanup_verified_at"] = now()
    updated["cleanup_reconciled_absence"] = already_absent
    atomic_json(lease_path, updated)
    append_event(
        run_root,
        make_event(
            updated["run_id"],
            "cleanup.closed",
            "ok",
            data={
                "tab_id": updated["tab_id"],
                "pane_id": updated["pane_id"],
                "cleanup_performed": cleanup_performed,
                "already_absent": already_absent,
                "absence_verified": True,
                "ssh_pid_absence_verified": True,
                "transcript_read": False,
            },
        ),
    )
    refresh_state(run_root, updated)
    return {
        "schema": "herdr-puppet.cleanup-preserved-tab.v1",
        "result": "ok",
        "run_id": updated["run_id"],
        "tab_id": updated["tab_id"],
        "pane_id": updated["pane_id"],
        "cleanup_performed": cleanup_performed,
        "already_closed": already_absent,
        "absence_verified": True,
        "ssh_pid_absence_verified": True,
        "transcript_read": False,
    }


def _live_gate(plan_payload: dict[str, Any], allow_live: bool) -> None:
    if not allow_live or plan_payload["safety"].get("live_mutation_authorized") is not True:
        raise HerdrPuppetError(
            "live_qualification_not_authorized",
            "Both the plan capability and command flag must authorize live qualification.",
        )


def create_qualification_tab(
    client: HerdrClient,
    *,
    plan_payload: dict[str, Any],
    lease_path: Path,
    allow_live: bool,
    run_root: Path,
    settle_seconds: float = 10.0,
) -> dict[str, Any]:
    validate_plan(plan_payload)
    _require_current_record_binding(plan_payload)
    _live_gate(plan_payload, allow_live)
    with _lease_lock(lease_path) as locked_lease_path:
        return _create_qualification_tab_locked(
            client,
            plan_payload=plan_payload,
            lease_path=locked_lease_path,
            allow_live=allow_live,
            settle_seconds=settle_seconds,
            run_root=run_root,
        )


def _create_qualification_tab_locked(
    client: HerdrClient,
    *,
    plan_payload: dict[str, Any],
    lease_path: Path,
    allow_live: bool,
    run_root: Path,
    settle_seconds: float = 10.0,
) -> dict[str, Any]:
    validate_plan(plan_payload)
    _require_current_record_binding(plan_payload)
    _live_gate(plan_payload, allow_live)
    require_initialized_journal(
        run_root,
        plan_payload=plan_payload,
    )
    before_status = structural_status(client, plan_payload=plan_payload)
    if before_status["result"] != "ok":
        raise HerdrPuppetError(
            "prelaunch_status_blocked",
            "Structural status blocked tab creation.",
            details={"blockers": before_status["blockers"]},
        )
    if lease_path.exists():
        raise HerdrPuppetError(
            "lease_path_exists",
            "Refusing to overwrite an existing lease.",
            details={"lease_path": str(lease_path)},
        )
    session = plan_payload["session"]["name"]
    workspace_id = plan_payload["workspace"]["id"]
    before_tabs = {
        item.get("tab_id")
        for item in client.snapshot(session)["tabs"]
        if item.get("workspace_id") == workspace_id and item.get("tab_id")
    }
    client.create_tab(session, workspace_id, plan_payload["owned_label"])

    deadline = time.monotonic() + settle_seconds
    new_tab: dict[str, Any] | None = None
    new_pane: dict[str, Any] | None = None
    ssh_process: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        snapshot = client.snapshot(session)
        tabs = [
            item
            for item in snapshot["tabs"]
            if item.get("workspace_id") == workspace_id
        ]
        candidates = [
            item
            for item in tabs
            if item.get("tab_id") not in before_tabs
            and item.get("label") == plan_payload["owned_label"]
            and item.get("workspace_id") == workspace_id
        ]
        if len(candidates) == 1:
            panes = [
                item
                for item in snapshot["panes"]
                if item.get("tab_id") == candidates[0].get("tab_id")
                and item.get("workspace_id") == workspace_id
            ]
            if len(panes) == 1:
                try:
                    process_info = client.process_info(session, panes[0]["pane_id"])
                    ssh_process = _expected_ssh_process(
                        process_info,
                        plan_payload["expected_ssh_target"],
                    )
                except HerdrPuppetError:
                    time.sleep(0.2)
                    continue
                new_tab = candidates[0]
                new_pane = panes[0]
                break
        time.sleep(0.2)
    if new_tab is None or new_pane is None or ssh_process is None:
        rollback_snapshot = client.snapshot(session)
        rollback_candidates = [
            item
            for item in rollback_snapshot["tabs"]
            if item.get("workspace_id") == workspace_id
            and item.get("tab_id") not in before_tabs
            and item.get("label") == plan_payload["owned_label"]
            and item.get("tab_id")
        ]
        rollback_performed = False
        rollback_verified = False
        rollback_tab_id: str | None = None
        rollback_pane_id: str | None = None
        rollback_ssh_pid: int | None = None
        if len(rollback_candidates) == 1:
            rollback_tab_id = rollback_candidates[0]["tab_id"]
            rollback_panes = [
                item
                for item in rollback_snapshot["panes"]
                if item.get("workspace_id") == workspace_id
                and item.get("tab_id") == rollback_tab_id
            ]
            if len(rollback_panes) == 1:
                rollback_pane_id = rollback_panes[0].get("pane_id")
                if isinstance(rollback_pane_id, str):
                    try:
                        rollback_process_info = client.process_info(
                            session,
                            rollback_pane_id,
                        )
                    except HerdrPuppetError:
                        rollback_process_info = {}
                    rollback_processes = rollback_process_info.get(
                        "foreground_processes",
                    )
                    if isinstance(rollback_processes, list):
                        rollback_ssh_processes = [
                            item
                            for item in rollback_processes
                            if isinstance(item, dict)
                            and isinstance(item.get("argv"), list)
                            and item["argv"]
                            and Path(str(item["argv"][0])).name == "ssh"
                            and isinstance(item.get("pid"), int)
                            and item["pid"] > 0
                        ]
                        if len(rollback_ssh_processes) == 1:
                            rollback_ssh_pid = rollback_ssh_processes[0]["pid"]
            try:
                client.close_tab(session, rollback_tab_id)
            except HerdrPuppetError as exc:
                raise HerdrPuppetError(
                    "candidate_tab_rollback_failed",
                    "The exact transaction-created tab could not be rolled back.",
                    details={"tab_id": rollback_tab_id},
                ) from exc
            rollback_performed = True
            after_rollback = client.snapshot(session)
            rollback_verified = (
                not any(
                    item.get("tab_id") == rollback_tab_id
                    for item in after_rollback["tabs"]
                )
                and not any(
                    item.get("tab_id") == rollback_tab_id
                    for item in after_rollback["panes"]
                )
                and (
                    rollback_ssh_pid is None
                    or client.wait_pid_absence(rollback_ssh_pid)
                )
            )
            if not rollback_verified:
                raise HerdrPuppetError(
                    "candidate_tab_rollback_unverified",
                    "The exact transaction-created tab rollback could not be "
                    "verified.",
                    details={"tab_id": rollback_tab_id},
                )
            append_event(
                run_root,
                make_event(
                    plan_payload["run_id"],
                    "qualification.tab-create-rolled-back",
                    "observed",
                    data={
                        "tab_id": rollback_tab_id,
                        "pane_id": rollback_pane_id,
                        "ssh_pid_observed": rollback_ssh_pid is not None,
                        "absence_verified": True,
                        "reason": "post_create_identity_unqualified",
                        "transcript_read": False,
                    },
                ),
            )
        raise HerdrPuppetError(
            "candidate_tab_not_qualified",
            "The new tab did not resolve to one expected SSH pane in time.",
            details={
                "rollback_performed": rollback_performed,
                "rollback_verified": rollback_verified,
                "ambiguous_candidate_count": (
                    len(rollback_candidates)
                    if not rollback_performed
                    else 0
                ),
            },
        )
    lease = {
        "schema": LEASE_SCHEMA,
        "state": "active",
        "run_id": plan_payload["run_id"],
        "harness": plan_payload["harness"],
        "session": json.loads(json.dumps(plan_payload["session"])),
        "workspace": json.loads(json.dumps(plan_payload["workspace"])),
        "destination_selection": json.loads(
            json.dumps(plan_payload["destination_selection"])
        ),
        "owned_label": plan_payload["owned_label"],
        "tab_id": new_tab["tab_id"],
        "pane_id": new_pane["pane_id"],
        "terminal_id": new_pane["terminal_id"],
        "ssh": {
            "pid": ssh_process["pid"],
            "argv": ssh_process["argv"],
            "target": plan_payload["expected_ssh_target"],
        },
        "next_seq": 1,
        "shell_readiness": "unverified",
        "harness_readiness": "unverified",
        "source": json.loads(json.dumps(plan_payload["source"])),
        "harness_binding": json.loads(
            json.dumps(plan_payload["harness_binding"])
        ),
        "startup_gate_operations": [],
        "proof_root": plan_payload["proof_root"],
        "caller_text_files": [],
        "caller_text_files_removed": [],
        "remote_task_files": [],
        "interactive_sends": [],
        "pending_interactive_send": None,
        "pending_sequence_operation": None,
    }
    lease["selected_authority_sha256"] = selected_authority_sha256(lease)
    validate_lease(lease)
    atomic_json(lease_path, lease)
    append_event(
        run_root,
        make_event(
            lease["run_id"],
            "qualification.tab-created",
            "ok",
            data={
                "tab_id": lease["tab_id"],
                "pane_id": lease["pane_id"],
                "terminal_id": lease["terminal_id"],
                "ssh_pid": lease["ssh"]["pid"],
                "destination_selection": lease["destination_selection"],
                "fresh_tab_created": True,
                "shell_transport_only": True,
                "harness_started": False,
                "shell_readiness": "unverified",
                "harness_readiness": "unverified",
                "harness_binding_fingerprint": lease["harness_binding"][
                    "fingerprint"
                ],
                "model_selection": lease["harness_binding"][
                    "model_observation"
                ],
                "remote_harness_pid": "unavailable",
                "targeted_halt": "unsupported",
                "recovery": "unsupported",
                "crash_persistence": "unsupported",
            },
        ),
    )
    return lease


def qualification_run(
    client: HerdrClient,
    *,
    lease_payload: dict[str, Any],
    lease_path: Path,
    seq: int,
    command: str,
    text_file: str | None = None,
    allow_live: bool,
    run_root: Path,
) -> dict[str, Any]:
    validate_lease(lease_payload)
    require_initialized_journal(
        run_root,
        lease_payload=lease_payload,
    )
    if not allow_live:
        raise HerdrPuppetError(
            "live_qualification_not_authorized",
            "The command flag must authorize live qualification.",
        )
    with _lease_lock(lease_path) as locked_lease_path:
        current = _reload_locked_lease(lease_payload, locked_lease_path)
        _require_current_record_binding(current)
        if current["state"] != "active":
            raise HerdrPuppetError("lease_not_active", "The lease is not active.")
        _require_no_pending_sequence_operation(current)
        if seq != current["next_seq"]:
            raise HerdrPuppetError(
                "send_sequence_mismatch",
                "Send sequence is stale, skipped, duplicate, or replayed.",
                details={"expected": current["next_seq"], "received": seq},
            )
        if "harness_launch" in current:
            raise HerdrPuppetError(
                "shell_command_after_harness_launch_forbidden",
                "Shell commands are forbidden after the regular interactive "
                "harness launch.",
            )
        _reject_shell_replacing_harness_launcher(command, current["harness"])
        _reject_generic_harness_launcher(
            command,
            current["harness_binding"],
        )
        _reject_nested_shell_command(command)
        shell_readiness = _shell_readiness(current)
        shell_status_probe = _is_strict_shell_status_probe(command)
        if seq == 1 and not shell_status_probe:
            raise HerdrPuppetError(
                "initial_shell_status_probe_required",
                "The first shell submission must be the strict STATUS probe.",
            )
        shell_status_retry = False
        if seq > 1 and shell_readiness != SHELL_READY:
            _require_bounded_shell_status_retry(
                lease=current,
                seq=seq,
                command=command,
                run_root=run_root,
            )
            shell_status_retry = True
        status = structural_status(client, lease_payload=current)
        if status["result"] != "ok":
            raise HerdrPuppetError(
                "prerun_status_blocked",
                "Structural status blocked the atomic shell command.",
                details={"blockers": status["blockers"]},
            )
        text_file_retained = False
        tracked_text_file: str | None = None
        if text_file is not None:
            tracked_text_file = _normalize_prompt_file(text_file)
            text_file_retained = _is_prompt_file_retained(tracked_text_file)
        session = current["session"]["name"]
        pane_id = current["pane_id"]
        harness_readiness = current.get("harness_readiness", "unverified")
        digest = sha256_text(command)
        reservation_base = json.loads(json.dumps(current))
        if tracked_text_file is not None and text_file_retained:
            reservation_base["caller_text_files"] = _dedupe_preserve_order(
                _as_text_file_list(
                    reservation_base.get("caller_text_files", [])
                )
                + [tracked_text_file]
            )
        reserved = _reserve_sequence_operation(
            lease=reservation_base,
            lease_path=locked_lease_path,
            run_root=run_root,
            operation="run",
            seq=seq,
            payload_sha256=digest,
        )
        client.run_command(session, pane_id, command)
        updated = json.loads(json.dumps(reserved))
        updated["pending_sequence_operation"] = None
        updated["next_seq"] = seq + 1
        atomic_json(locked_lease_path, updated)
        append_event(
            run_root,
            make_event(
                updated["run_id"],
                "qualification.run",
                "ok",
                seq=seq,
                command_sha256=digest,
                data={
                        "pane_id": pane_id,
                        "input_request": "pane run",
                        "herdr_cli_acknowledged": True,
                        "acceptance_scope": "herdr_pane_run_cli_only",
                        "submission_mode": "atomic_shell_command",
                        "execution_acceptance": "unverified",
                        "transcript_read": False,
                        "readiness_advanced": False,
                        "shell_status_probe": shell_status_probe,
                        "shell_status_retry": shell_status_retry,
                        "shell_readiness": shell_readiness,
                        "harness_readiness": harness_readiness,
                        "caller_text_file_retained": text_file_retained,
                        "command_file_tracked": tracked_text_file is not None,
                        "controller_command_persisted": False,
                        "caller_input_file_location": (
                            "controller_local"
                            if tracked_text_file is not None
                            else "not_applicable"
                        ),
                        "caller_input_file_lifecycle": (
                            "caller_owned"
                            if tracked_text_file is not None
                            else "not_applicable"
                        ),
                },
            ),
        )
    return {
        "schema": "herdr-puppet.qualification-run.v1",
        "result": "ok",
        "run_id": updated["run_id"],
        "pane_id": pane_id,
        "seq": seq,
        "next_seq": updated["next_seq"],
        "command_sha256": digest,
        "herdr_cli_acknowledged": True,
        "acceptance_scope": "herdr_pane_run_cli_only",
        "submission_mode": "atomic_shell_command",
        "execution_acceptance": "unverified",
        "readiness_advanced": False,
        "shell_status_probe": shell_status_probe,
        "shell_status_retry": shell_status_retry,
        "shell_readiness": shell_readiness,
        "harness_readiness": harness_readiness,
        "caller_text_file_retained": text_file_retained,
        "command_file_tracked": tracked_text_file is not None,
        "controller_command_persisted": False,
        "caller_input_file_location": (
            "controller_local"
            if tracked_text_file is not None
            else "not_applicable"
        ),
        "caller_input_file_lifecycle": (
            "caller_owned" if tracked_text_file is not None else "not_applicable"
        ),
        "command_persisted": False,
        "transcript_read": False,
    }


def _regular_launch_command(binding: dict[str, Any]) -> str:
    checked = validate_harness_binding(binding)
    worktree = checked["source"]["worktree"]
    environment = checked["regular_launch"]["environment"]
    argv = checked["regular_launch"]["argv"]
    for key in environment:
        if re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", key) is None:
            raise HerdrPuppetError(
                "invalid_harness_binding",
                "The regular launch environment contains an invalid name.",
            )
    environment_argv = [
        f"{key}={environment[key]}" for key in sorted(environment)
    ]
    return (
        f"cd -- {shlex.quote(worktree)} && "
        + shlex.join(["/usr/bin/env", "-i", *environment_argv, *argv])
    )


def qualification_harness_census_verify(
    *,
    lease_payload: dict[str, Any],
    lease_path: Path,
    census: dict[str, Any],
    run_root: Path,
) -> dict[str, Any]:
    validate_lease(lease_payload)
    require_initialized_journal(
        run_root,
        lease_payload=lease_payload,
    )
    with _lease_lock(lease_path) as locked_lease_path:
        current = _reload_locked_lease(lease_payload, locked_lease_path)
        binding = _require_current_record_binding(current)
        if current["state"] != "active":
            raise HerdrPuppetError("lease_not_active", "The lease is not active.")
        _require_no_pending_sequence_operation(current)
        if _shell_readiness(current) != SHELL_READY:
            raise HerdrPuppetError(
                "shell_readiness_not_proven",
                "In-row census verification requires a STATUS-verified shell.",
            )
        if "harness_launch" in current:
            raise HerdrPuppetError(
                "harness_already_launched",
                "In-row census verification must happen before harness launch.",
            )
        verification = verify_remote_census(
            binding_value=binding,
            census_value=census,
        )
        census_sha256 = remote_census_facts_fingerprint(census)
        matches = [
            event
            for event in read_events(run_root)
            if event.get("run_id") == current["run_id"]
            and event.get("kind") == "qualification.harness-census-verified"
            and event.get("result") == "observed"
        ]
        already_verified = False
        if matches:
            latest_data = matches[-1].get("data")
            if (
                len(matches) != 1
                or not isinstance(latest_data, dict)
                or latest_data.get("binding_fingerprint")
                != binding["fingerprint"]
                or latest_data.get("census_sha256") != census_sha256
            ):
                raise HerdrPuppetError(
                    "harness_recensus_verification_conflict",
                    "The row already carries a different in-row census verification.",
                )
            already_verified = True
        if not already_verified:
            append_event(
                run_root,
                make_event(
                    current["run_id"],
                    "qualification.harness-census-verified",
                    "observed",
                    data={
                        "binding_fingerprint": binding["fingerprint"],
                        "census_sha256": census_sha256,
                        "executable_fingerprint": verification[
                            "executable_fingerprint"
                        ],
                        "launch_vector_sha256": verification[
                            "launch_vector_sha256"
                        ],
                        "lifecycle_strategy": verification[
                            "lifecycle_strategy"
                        ],
                        "raw_output_retained": False,
                        "transcript_read": False,
                    },
                ),
            )
    return {
        **verification,
        "schema": "herdr-puppet.qualification-harness-census-verify.v1",
        "run_id": current["run_id"],
        "census_sha256": census_sha256,
        "already_verified": already_verified,
        "transcript_read": False,
    }


def _require_in_row_census_verification(
    run_root: Path,
    *,
    lease: dict[str, Any],
    binding: dict[str, Any],
) -> None:
    matches = [
        event
        for event in read_events(run_root)
        if event.get("run_id") == lease["run_id"]
        and event.get("kind") == "qualification.harness-census-verified"
        and event.get("result") == "observed"
        and isinstance(event.get("data"), dict)
        and event["data"].get("binding_fingerprint")
        == binding["fingerprint"]
    ]
    if len(matches) != 1:
        raise HerdrPuppetError(
            "harness_recensus_verification_missing",
            "Regular harness launch requires one exact in-row census verification.",
        )


def _require_claude_marker_registrations(
    lease: dict[str, Any],
    binding: dict[str, Any],
) -> None:
    if lease["harness"] != "claude":
        return
    marker_root = binding["lifecycle_observation"]["marker_root"]
    expected_paths = {
        posixpath.join(marker_root, name)
        for name in CLAUDE_MARKER_NAMES
    }
    remote_files = _as_remote_task_files(
        lease.get("remote_task_files", []),
        expected_ssh_target=lease["ssh"]["target"],
    )
    registered_paths = {
        item["path"]
        for item in remote_files
        if item["state"] == REMOTE_FILE_REGISTERED
    }
    if (
        len(remote_files) != len(CLAUDE_MARKER_NAMES)
        or registered_paths != expected_paths
    ):
        raise HerdrPuppetError(
            "claude_marker_registration_incomplete",
            "Claude launch requires all exact run-bound marker paths "
            "registered and none removed.",
            details={
                "expected_count": len(CLAUDE_MARKER_NAMES),
                "registered_count": len(registered_paths),
                "total_remote_file_count": len(remote_files),
            },
        )


def qualification_harness_launch(
    client: HerdrClient,
    *,
    lease_payload: dict[str, Any],
    lease_path: Path,
    seq: int,
    allow_live: bool,
    run_root: Path,
) -> dict[str, Any]:
    validate_lease(lease_payload)
    _require_active_lease_journal(run_root, lease_payload)
    if not allow_live:
        raise HerdrPuppetError(
            "live_qualification_not_authorized",
            "The command flag must authorize the regular harness launch.",
        )
    with _lease_lock(lease_path) as locked_lease_path:
        current = _reload_locked_lease(lease_payload, locked_lease_path)
        if current["state"] != "active":
            raise HerdrPuppetError("lease_not_active", "The lease is not active.")
        _require_no_pending_sequence_operation(current)
        if seq != current["next_seq"]:
            raise HerdrPuppetError(
                "send_sequence_mismatch",
                "Harness launch sequence is stale, skipped, duplicate, or replayed.",
                details={"expected": current["next_seq"], "received": seq},
            )
        if _shell_readiness(current) != SHELL_READY:
            raise HerdrPuppetError(
                "shell_readiness_not_proven",
                "Regular harness launch requires a STATUS-verified shell.",
            )
        if "harness_launch" in current:
            raise HerdrPuppetError(
                "harness_already_launched",
                "A lease permits exactly one controller-attested harness launch.",
            )
        binding = _require_current_record_binding(current)
        expected_model_selector = binding["harness"] == "agy"
        if (
            binding["regular_launch"]["explicit_model_selector"]
            is not expected_model_selector
            or binding["regular_launch"]["unrestricted"] is not True
        ):
            raise HerdrPuppetError(
                "invalid_regular_launch",
                "The bound launch model-selection posture is invalid.",
            )
        _require_in_row_census_verification(
            run_root,
            lease=current,
            binding=binding,
        )
        _require_claude_marker_registrations(current, binding)
        status = structural_status(client, lease_payload=current)
        if status["result"] != "ok":
            raise HerdrPuppetError(
                "prelaunch_status_blocked",
                "Structural status blocked the regular harness launch.",
                details={"blockers": status["blockers"]},
            )
        command = _regular_launch_command(binding)
        _reject_shell_replacing_harness_launcher(command, current["harness"])
        command_digest = sha256_text(command)
        reserved = _reserve_sequence_operation(
            lease=current,
            lease_path=locked_lease_path,
            run_root=run_root,
            operation="harness_launch",
            seq=seq,
            payload_sha256=command_digest,
        )
        client.run_command(
            current["session"]["name"],
            current["pane_id"],
            command,
        )
        updated = json.loads(json.dumps(reserved))
        updated["pending_sequence_operation"] = None
        updated["harness_launch"] = {
            "seq": seq,
            "launched_at": now(),
            "command_sha256": command_digest,
            "binding_fingerprint": binding["fingerprint"],
            "launch_vector_sha256": binding["regular_launch"][
                "vector_sha256"
            ],
            "remote_harness_pid": "unavailable",
        }
        updated["next_seq"] = seq + 1
        atomic_json(locked_lease_path, updated)
        append_event(
            run_root,
            make_event(
                updated["run_id"],
                "qualification.harness-launch",
                "ok",
                seq=seq,
                command_sha256=command_digest,
                data={
                    "pane_id": updated["pane_id"],
                    "binding_fingerprint": binding["fingerprint"],
                    "launch_vector_sha256": binding["regular_launch"][
                        "vector_sha256"
                    ],
                    "explicit_model_selector": expected_model_selector,
                    "model_selection": binding["model_observation"],
                    "unrestricted": True,
                    "remote_harness_pid": "unavailable",
                    "targeted_halt": "unsupported",
                    "recovery": "unsupported",
                    "crash_persistence": "unsupported",
                    "acceptance_scope": "herdr_pane_run_cli_only",
                    "execution_acceptance": "unverified",
                    "transcript_read": False,
                },
            ),
        )
    return {
        "schema": "herdr-puppet.qualification-harness-launch.v1",
        "result": "ok",
        "run_id": updated["run_id"],
        "pane_id": updated["pane_id"],
        "seq": seq,
        "next_seq": updated["next_seq"],
        "harness": updated["harness"],
        "binding_fingerprint": binding["fingerprint"],
        "launch_vector_sha256": binding["regular_launch"]["vector_sha256"],
        "command_sha256": command_digest,
        "explicit_model_selector": expected_model_selector,
        "unrestricted": True,
        "remote_harness_pid": "unavailable",
        "targeted_halt": "unsupported",
        "recovery": "unsupported",
        "crash_persistence": "unsupported",
        "herdr_cli_acknowledged": True,
        "execution_acceptance": "unverified",
        "transcript_read": False,
    }


def _qualification_send_history(
    run_root: Path,
    *,
    run_id: str,
) -> list[dict[str, Any]]:
    sends = [
        event
        for event in read_events(run_root)
        if event.get("run_id") == run_id
        and (
            (
                event.get("kind") == "qualification.send"
                and event.get("result") == "ok"
            )
            or (
                event.get("kind") == "qualification.send-reconciled"
                and event.get("result") == "observed"
            )
        )
    ]
    if len(sends) > 2:
        raise HerdrPuppetError(
            "invalid_qualification_send_history",
            "Controller send history exceeds its bounded two-turn contract.",
        )
    previous_seq = 0
    for index, event in enumerate(sends):
        seq = event.get("seq")
        prompt_sha256 = event.get("prompt_sha256")
        data = event.get("data")
        expected_phase = "initial" if index == 0 else "steering"
        expected_transport = (
            "direct"
            if event.get("kind") == "qualification.send"
            else "reconciled"
        )
        if (
            isinstance(seq, bool)
            or not isinstance(seq, int)
            or seq <= previous_seq
            or not isinstance(prompt_sha256, str)
            or re.fullmatch(r"[0-9a-f]{64}", prompt_sha256) is None
            or not isinstance(data, dict)
            or data.get("phase") != expected_phase
            or (
                index == 0
                and (
                    expected_transport != "direct"
                    or not isinstance(data.get("instruction_wrapper"), dict)
                )
            )
            or (
                index == 1
                and data.get("instruction_wrapper") is not None
                and expected_transport == "direct"
            )
        ):
            raise HerdrPuppetError(
                "invalid_qualification_send_history",
                "Controller send history is malformed or non-monotonic.",
            )
        previous_seq = seq
    return sends


def _qualification_send_state(
    lease: dict[str, Any],
    run_root: Path,
    *,
    allow_pending: bool,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    _require_no_pending_sequence_operation(lease)
    lease_sends = _as_interactive_sends(
        lease.get("interactive_sends", []),
        next_seq=lease["next_seq"],
    )
    journal_state = _qualification_journal_send_state(
        run_root,
        run_id=lease["run_id"],
    )
    if lease_sends != journal_state:
        raise HerdrPuppetError(
            "qualification_send_history_diverged",
            "Canonical lease send state and controller journal disagree; "
            "preserve the row and do not submit more input.",
        )
    pending = _as_pending_interactive_send(
        lease.get("pending_interactive_send"),
        next_seq=lease["next_seq"],
        completed_sends=lease_sends,
    )
    if pending is not None and not allow_pending:
        raise HerdrPuppetError(
            "qualification_send_delivery_unknown",
            "A durably reserved interactive send may already have reached Herdr; "
            "do not replay it. Preserve the row, or use the narrow steering-only "
            "reconciliation path when supported.",
            details={
                "seq": pending["seq"],
                "phase": pending["phase"],
            },
        )
    return lease_sends, pending


def _qualification_journal_send_state(
    run_root: Path,
    *,
    run_id: str,
) -> list[dict[str, Any]]:
    journal_sends = _qualification_send_history(
        run_root,
        run_id=run_id,
    )
    return [
        {
            "seq": event["seq"],
            "phase": event["data"]["phase"],
            "prompt_sha256": event["prompt_sha256"],
            "transport": (
                "direct"
                if event["kind"] == "qualification.send"
                else "reconciled"
            ),
            "instruction_wrapper_verified": isinstance(
                event["data"].get("instruction_wrapper"),
                dict,
            ),
        }
        for event in journal_sends
    ]


def _qualification_reconciled_evidence(
    run_root: Path,
    *,
    run_id: str,
    seq: int,
    prompt_sha256: str,
) -> str:
    matches = [
        event
        for event in read_events(run_root)
        if event.get("run_id") == run_id
        and event.get("kind") == "qualification.send-reconciled"
        and event.get("result") == "observed"
        and event.get("seq") == seq
        and event.get("prompt_sha256") == prompt_sha256
    ]
    if len(matches) != 1:
        raise HerdrPuppetError(
            "qualification_reconciliation_evidence_missing",
            "The durable reconciliation event is missing or ambiguous.",
        )
    data = matches[0].get("data")
    stored = data.get("evidence") if isinstance(data, dict) else None
    if (
        not isinstance(stored, str)
        or not stored.strip()
        or "\x00" in stored
        or len(stored.encode("utf-8"))
        > MAX_RECONCILIATION_EVIDENCE_BYTES
    ):
        raise HerdrPuppetError(
            "invalid_qualification_reconciliation_evidence",
            "The durable reconciliation evidence is malformed.",
        )
    return stored


def _require_qualification_send_consistency(
    lease: dict[str, Any],
    run_root: Path,
) -> list[dict[str, Any]]:
    lease_sends, _pending = _qualification_send_state(
        lease,
        run_root,
        allow_pending=False,
    )
    return lease_sends


def _require_initial_send_consumption(
    run_root: Path,
    *,
    lease: dict[str, Any],
    initial_send: dict[str, Any],
) -> None:
    matches = [
        event
        for event in read_events(run_root)
        if event.get("run_id") == lease["run_id"]
        and event.get("kind") == "qualification.beacon"
        and event.get("result") == "observed"
        and event.get("seq") == initial_send["seq"]
        and isinstance(event.get("data"), dict)
        and event["data"].get("checkpoint") == "STATUS"
    ]
    if lease.get("harness_readiness") == HARNESS_CHECKPOINT_READY:
        expected_seq = lease.get("harness_readiness_submission_seq")
        expected_nonce = lease.get("harness_readiness_nonce_sha256")
        evidence_matches = [
            event
            for event in matches
            if event.get("seq") == expected_seq
            and event.get("nonce_sha256") == expected_nonce
        ]
        evidence_is_exact = len(matches) == 1 and len(evidence_matches) == 1
    else:
        evidence_is_exact = bool(matches)
    if not evidence_is_exact:
        raise HerdrPuppetError(
            "initial_send_consumption_not_proven",
            "The separate steering turn requires one exact controller-observed "
            "STATUS checkpoint for the wrapped initial send and its bound nonce.",
        )


def _claude_lifecycle_events(
    run_root: Path,
    *,
    binding: dict[str, Any],
    phase: str,
) -> list[dict[str, Any]]:
    probe_id = binding["lifecycle_observation"]["probe_id"]
    matches = [
        event
        for event in read_events(run_root)
        if event.get("kind") == CLAUDE_LIFECYCLE_EVENT
        and event.get("result") == "observed"
        and event.get("run_id") == binding["lifecycle_observation"]["run_id"]
        and isinstance(event.get("data"), dict)
        and event["data"].get("probe_id") == probe_id
        and event["data"].get("phase") == phase
    ]
    expected_data_fields = {
        "phase",
        "classification",
        "probe_id",
        "send_seq",
        "counts",
        "marker_set_sha256",
        "receipt_verified",
        "stdin_read",
        "raw_input_retained",
        "transcript_read",
    }
    for event in matches:
        data = event["data"]
        counts = data.get("counts")
        if (
            set(data) != expected_data_fields
            or data.get("classification")
            not in {
                "armed",
                "submission_not_observed",
                "response_pending",
                "response_completed",
                "response_failed",
            }
            or (
                data.get("send_seq") is not None
                and (
                    isinstance(data["send_seq"], bool)
                    or not isinstance(data["send_seq"], int)
                    or data["send_seq"] < 1
                )
            )
            or not isinstance(counts, dict)
            or set(counts)
            != {
                "session_start",
                "user_prompt_submit",
                "stop",
                "stop_failure",
            }
            or any(
                isinstance(count, bool)
                or not isinstance(count, int)
                or count < 0
                for count in counts.values()
            )
            or not isinstance(data.get("marker_set_sha256"), str)
            or re.fullmatch(
                r"[0-9a-f]{64}", data["marker_set_sha256"]
            )
            is None
            or data.get("receipt_verified") is not True
            or data.get("stdin_read")
            is not bool(counts.get("user_prompt_submit"))
            or data.get("raw_input_retained") is not False
            or data.get("transcript_read") is not False
        ):
            raise HerdrPuppetError(
                "invalid_claude_lifecycle_journal",
                "A Claude lifecycle journal event is malformed.",
            )
    return matches


def _require_claude_lifecycle_phase(
    *,
    run_root: Path,
    binding: dict[str, Any],
    phase: str,
    classification: str,
) -> dict[str, Any]:
    expected_submissions = PHASE_SUBMISSIONS.get(phase)
    if expected_submissions is None:
        raise HerdrPuppetError(
            "invalid_claude_lifecycle_phase",
            "Claude lifecycle phase must be armed, initial, or steering.",
        )
    sends = _qualification_send_history(
        run_root,
        run_id=binding["lifecycle_observation"]["run_id"],
    )
    matches = _claude_lifecycle_events(
        run_root,
        binding=binding,
        phase=phase,
    )
    if not matches or matches[-1]["data"].get("classification") != classification:
        raise HerdrPuppetError(
            "claude_lifecycle_not_proven",
            "The required Claude native lifecycle phase is not proven.",
            details={
                "phase": phase,
                "expected_classification": classification,
            },
        )
    latest = matches[-1]
    if expected_submissions == 0:
        bound = "seq" not in latest and "prompt_sha256" not in latest
    else:
        if len(sends) < expected_submissions:
            bound = False
        else:
            send = sends[expected_submissions - 1]
            bound = (
                latest.get("seq") == send["seq"]
                and latest.get("prompt_sha256") == send["prompt_sha256"]
                and latest["data"].get("send_seq") == send["seq"]
            )
    if not bound:
        raise HerdrPuppetError(
            "claude_lifecycle_send_binding_invalid",
            "The Claude lifecycle receipt is not bound to its exact controller send.",
        )
    return latest


def qualification_claude_lifecycle_observe(
    *,
    lease_payload: dict[str, Any],
    lease_path: Path,
    receipt: dict[str, Any],
    phase: str,
    run_root: Path,
) -> dict[str, Any]:
    validate_lease(lease_payload)
    _require_active_lease_journal(run_root, lease_payload)
    with _lease_lock(lease_path) as locked_lease_path:
        current = _reload_locked_lease(lease_payload, locked_lease_path)
        if current["harness"] != "claude":
            raise HerdrPuppetError(
                "claude_lifecycle_wrong_harness",
                "Native Claude lifecycle receipts apply only to Claude rows.",
            )
        if current["state"] not in {"active", "preserved"}:
            raise HerdrPuppetError(
                "lease_state_invalid",
                "Claude lifecycle observation requires an active or preserved lease.",
            )
        if "harness_launch" not in current:
            raise HerdrPuppetError(
                "harness_launch_missing",
                "Claude lifecycle observation requires the bound harness launch.",
            )
        binding = _require_current_record_binding(current)
        expected_submissions = PHASE_SUBMISSIONS.get(phase)
        if expected_submissions is None:
            raise HerdrPuppetError(
                "invalid_claude_lifecycle_phase",
                "Claude lifecycle phase must be armed, initial, or steering.",
            )
        send_state = _require_qualification_send_consistency(
            current,
            run_root,
        )
        if len(send_state) < expected_submissions:
            raise HerdrPuppetError(
                "claude_lifecycle_send_count_mismatch",
                "The Claude lifecycle phase does not match controller send history.",
                details={
                    "phase": phase,
                    "expected": expected_submissions,
                    "observed": len(send_state),
                },
            )
        phase_send_state = send_state[:expected_submissions]
        if phase == "initial":
            _require_claude_lifecycle_phase(
                run_root=run_root,
                binding=binding,
                phase="armed",
                classification="armed",
            )
        elif phase == "steering":
            _require_claude_lifecycle_phase(
                run_root=run_root,
                binding=binding,
                phase="initial",
                classification="response_completed",
            )
        checked_receipt, classification = validate_claude_hook_receipt(
            receipt,
            observation=binding["lifecycle_observation"],
            phase=phase,
            expected_prompt_sha256s=[
                item["prompt_sha256"] for item in phase_send_state
            ],
        )
        existing = _claude_lifecycle_events(
            run_root,
            binding=binding,
            phase=phase,
        )
        already_observed = False
        if existing:
            previous = existing[-1]["data"]
            previous_counts = previous.get("counts")
            if (
                previous.get("marker_set_sha256")
                == checked_receipt["marker_set_sha256"]
                and previous.get("classification") == classification
            ):
                already_observed = True
            else:
                if previous.get("classification") in {
                    "armed",
                    "response_completed",
                    "response_failed",
                }:
                    raise HerdrPuppetError(
                        "claude_lifecycle_terminal_conflict",
                        "A terminal Claude lifecycle phase cannot be replaced.",
                    )
                if (
                    not isinstance(previous_counts, dict)
                    or set(previous_counts) != set(checked_receipt["counts"])
                    or any(
                        checked_receipt["counts"][event]
                        < previous_counts.get(event, -1)
                        for event in checked_receipt["counts"]
                    )
                ):
                    raise HerdrPuppetError(
                        "claude_lifecycle_receipt_regression",
                        "Claude lifecycle receipt counts cannot regress.",
                    )
                classification_rank = {
                    "submission_not_observed": 0,
                    "response_pending": 1,
                    "response_completed": 2,
                    "response_failed": 2,
                }
                if classification_rank.get(
                    classification, -1
                ) < classification_rank.get(
                    previous.get("classification"), -1
                ):
                    raise HerdrPuppetError(
                        "claude_lifecycle_receipt_regression",
                        "Claude lifecycle classification cannot regress.",
                    )
        if not already_observed and len(send_state) != expected_submissions:
            raise HerdrPuppetError(
                "claude_lifecycle_send_count_mismatch",
                "Only an identical prior Claude lifecycle receipt may be replayed "
                "after the row advances.",
                details={
                    "phase": phase,
                    "expected": expected_submissions,
                    "observed": len(send_state),
                },
            )
        bound_send = (
            phase_send_state[expected_submissions - 1]
            if expected_submissions
            else None
        )
        if already_observed:
            _require_claude_lifecycle_phase(
                run_root=run_root,
                binding=binding,
                phase=phase,
                classification=classification,
            )
        if not already_observed:
            append_event(
                run_root,
                make_event(
                    current["run_id"],
                    CLAUDE_LIFECYCLE_EVENT,
                    "observed",
                    seq=bound_send["seq"] if bound_send else None,
                    prompt_sha256=(
                        bound_send["prompt_sha256"] if bound_send else None
                    ),
                    data={
                        "phase": phase,
                        "classification": classification,
                        "probe_id": checked_receipt["probe_id"],
                        "send_seq": (
                            bound_send["seq"] if bound_send else None
                        ),
                        "counts": checked_receipt["counts"],
                        "marker_set_sha256": checked_receipt[
                            "marker_set_sha256"
                        ],
                        "receipt_verified": True,
                        "stdin_read": checked_receipt["stdin_read"],
                        "raw_input_retained": False,
                        "transcript_read": False,
                    },
                ),
            )
    return {
        "schema": "herdr-puppet.qualification-claude-lifecycle.v1",
        "result": "observed",
        "run_id": current["run_id"],
        "phase": phase,
        "classification": classification,
        "probe_id": checked_receipt["probe_id"],
        "counts": checked_receipt["counts"],
        "marker_set_sha256": checked_receipt["marker_set_sha256"],
        "send_seq": bound_send["seq"] if bound_send else None,
        "already_observed": already_observed,
        "receipt_verified": True,
        "stdin_read": checked_receipt["stdin_read"],
        "raw_input_retained": False,
        "transcript_read": False,
    }


def qualification_startup_gate(
    client: HerdrClient,
    *,
    lease_payload: dict[str, Any],
    lease_path: Path,
    seq: int,
    gate: str,
    action: str,
    source_worktree: str,
    operator_id: str,
    evidence: str,
    confirm_exact_worktree: bool,
    confirm_unrestricted: bool,
    allow_live: bool,
    run_root: Path,
) -> dict[str, Any]:
    validate_lease(lease_payload)
    _require_active_lease_journal(run_root, lease_payload)
    if not allow_live:
        raise HerdrPuppetError(
            "live_qualification_not_authorized",
            "The command flag must authorize startup-gate handling.",
        )
    if (
        not confirm_exact_worktree
        or not confirm_unrestricted
        or evidence != "operator_observed_exact_gate"
    ):
        raise HerdrPuppetError(
            "startup_gate_not_confirmed",
            "Startup-gate handling requires exact-worktree and unrestricted-posture confirmation.",
        )
    if (
        not isinstance(operator_id, str)
        or re.fullmatch(r"[A-Za-z0-9._@:-]{1,128}", operator_id) is None
    ):
        raise HerdrPuppetError(
            "startup_gate_operator_invalid",
            "Startup-gate handling requires a bounded operator identifier.",
        )
    with _lease_lock(lease_path) as locked_lease_path:
        current = _reload_locked_lease(lease_payload, locked_lease_path)
        if current["state"] != "active":
            raise HerdrPuppetError("lease_not_active", "The lease is not active.")
        _require_no_pending_sequence_operation(current)
        if seq != current["next_seq"]:
            raise HerdrPuppetError(
                "send_sequence_mismatch",
                "Startup-gate sequence is stale, skipped, duplicate, or replayed.",
                details={"expected": current["next_seq"], "received": seq},
            )
        if current.get("harness_readiness") in {
            HARNESS_READY,
            HARNESS_CHECKPOINT_PENDING,
            HARNESS_CHECKPOINT_READY,
        }:
            raise HerdrPuppetError(
                "startup_gate_after_readiness_forbidden",
                "Startup gates may be handled only before ordinary readiness.",
            )
        binding = _require_current_record_binding(current)
        if "harness_launch" not in current:
            raise HerdrPuppetError(
                "harness_launch_missing",
                "Startup-gate handling requires the bound regular launch.",
            )
        if (
            source_worktree != current["source"]["worktree"]
            or source_worktree != binding["source"]["worktree"]
        ):
            raise HerdrPuppetError(
                "startup_gate_worktree_mismatch",
                "Startup-gate handling must bind the exact task-owned worktree.",
            )
        allowed = STARTUP_GATE_ACTIONS.get(current["harness"], {}).get(gate)
        if allowed is None or action not in allowed:
            raise HerdrPuppetError(
                "startup_gate_unsupported",
                "The startup gate or action is outside the harness allowlist.",
            )
        existing = current.get("startup_gate_operations", [])
        if any(item.get("gate") == gate for item in existing):
            raise HerdrPuppetError(
                "startup_gate_replay",
                "Each startup gate may be handled at most once per lease.",
            )
        if binding["regular_launch"]["unrestricted"] is not True:
            raise HerdrPuppetError(
                "startup_gate_unrestricted_posture_missing",
                "Startup-gate handling requires the bound unrestricted posture.",
            )
        status = structural_status(client, lease_payload=current)
        if status["result"] != "ok":
            raise HerdrPuppetError(
                "startup_gate_status_blocked",
                "Structural status blocked startup-gate handling.",
                details={"blockers": status["blockers"]},
            )
        keys = list(allowed[action])
        operator_digest = sha256_text(operator_id)
        worktree_digest = sha256_text(source_worktree)
        key_vector_digest = sha256_text(
            json.dumps(keys, separators=(",", ":"), ensure_ascii=False)
        )
        gate_payload_digest = sha256_text(
            json.dumps(
                {
                    "gate": gate,
                    "action": action,
                    "operator_sha256": operator_digest,
                    "worktree_sha256": worktree_digest,
                    "key_vector_sha256": key_vector_digest,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        reserved = _reserve_sequence_operation(
            lease=current,
            lease_path=locked_lease_path,
            run_root=run_root,
            operation="startup_gate",
            seq=seq,
            payload_sha256=gate_payload_digest,
        )
        if keys:
            client.run_keys(
                current["session"]["socket"],
                current["pane_id"],
                keys,
            )
        operation = {
            "gate": gate,
            "action": action,
            "seq": seq,
            "observed_at": now(),
            "operator_sha256": operator_digest,
            "worktree_sha256": worktree_digest,
            "key_vector_sha256": key_vector_digest,
            "pane_input_mutated": bool(keys),
        }
        updated = json.loads(json.dumps(reserved))
        updated["pending_sequence_operation"] = None
        updated["startup_gate_operations"] = [
            *existing,
            operation,
        ]
        updated["next_seq"] = seq + 1
        atomic_json(locked_lease_path, updated)
        append_event(
            run_root,
            make_event(
                updated["run_id"],
                "qualification.startup-gate",
                "observed",
                seq=seq,
                data={
                    "pane_id": updated["pane_id"],
                    "gate": gate,
                    "action": action,
                    "operator_id_sha256": operator_digest,
                    "worktree_sha256": worktree_digest,
                    "key_vector_sha256": key_vector_digest,
                    "pane_input_mutated": bool(keys),
                    "single_use": True,
                    "pre_readiness": True,
                    "transcript_read": False,
                },
            ),
        )
    return {
        "schema": "herdr-puppet.qualification-startup-gate.v1",
        "result": "ok",
        "run_id": updated["run_id"],
        "pane_id": updated["pane_id"],
        "harness": updated["harness"],
        "gate": gate,
        "action": action,
        "seq": seq,
        "next_seq": updated["next_seq"],
        "operator_id_sha256": operator_digest,
        "worktree_sha256": worktree_digest,
        "key_vector_sha256": key_vector_digest,
        "pane_input_mutated": bool(keys),
        "single_use": True,
        "pre_readiness": True,
        "transcript_read": False,
    }


def qualification_harness_ready(
    client: HerdrClient,
    *,
    lease_payload: dict[str, Any],
    lease_path: Path,
    source_repo: str,
    source_worktree: str,
    operator_id: str,
    evidence: str,
    confirm_ready: bool,
    allow_live: bool,
    run_root: Path,
) -> dict[str, Any]:
    validate_lease(lease_payload)
    _require_active_lease_journal(run_root, lease_payload)
    if not allow_live:
        raise HerdrPuppetError(
            "live_qualification_not_authorized",
            "The command flag must authorize harness readiness verification.",
        )
    if lease_payload["harness"] == "agy":
        raise HerdrPuppetError(
            "agy_readiness_is_checkpoint_driven",
            "AGY does not require operator-observed input readiness. Submit the "
            "single wrapped initial prompt after its bound launch, then wait "
            "for the strict nonce checkpoint.",
        )
    if not confirm_ready:
        raise HerdrPuppetError(
            "harness_readiness_not_confirmed",
            "Harness readiness requires explicit operator confirmation.",
        )
    if evidence != "operator_observed_ready_input":
        raise HerdrPuppetError(
            "harness_readiness_evidence_invalid",
            "Harness readiness requires the bounded operator-observed evidence.",
        )
    if (
        not isinstance(operator_id, str)
        or not re.fullmatch(r"[A-Za-z0-9._@:-]{1,128}", operator_id)
    ):
        raise HerdrPuppetError(
            "harness_readiness_operator_missing",
            "Harness readiness requires one bounded operator identifier.",
        )
    with _lease_lock(lease_path) as locked_lease_path:
        current = _reload_locked_lease(lease_payload, locked_lease_path)
        if current["state"] != "active":
            raise HerdrPuppetError("lease_not_active", "The lease is not active.")
        _require_no_pending_sequence_operation(current)
        if (
            current["source"].get("repo") != source_repo
            or current["source"].get("worktree") != source_worktree
        ):
            raise HerdrPuppetError(
                "harness_readiness_source_mismatch",
                "Harness readiness must bind to the exact leased source.",
            )
        if _shell_readiness(current) != SHELL_READY:
            raise HerdrPuppetError(
                "shell_readiness_not_proven",
                "Harness readiness may be verified only after a shell STATUS beacon.",
            )
        binding = _require_current_record_binding(current)
        if "harness_launch" not in current:
            raise HerdrPuppetError(
                "harness_launch_missing",
                "Harness readiness requires the controller-attested regular launch.",
            )
        if current["harness"] == "claude":
            _require_claude_lifecycle_phase(
                run_root=run_root,
                binding=binding,
                phase="armed",
                classification="armed",
            )
        if current["harness"] == "cursor" and not any(
            operation.get("gate") == "workspace_trust"
            for operation in current.get("startup_gate_operations", [])
        ):
            raise HerdrPuppetError(
                "cursor_workspace_trust_unresolved",
                "Cursor Workspace Trust must be handled before ordinary readiness.",
            )
        status = structural_status(client, lease_payload=current)
        if status["result"] != "ok":
            raise HerdrPuppetError(
                "harness_readiness_status_blocked",
                "Structural status blocked harness readiness verification.",
                details={"blockers": status["blockers"]},
            )
        already_ready = current.get("harness_readiness") == HARNESS_READY
        if already_ready and (
            current.get("harness_readiness_operator") != operator_id
            or current.get("harness_readiness_evidence") != evidence
        ):
            raise HerdrPuppetError(
                "harness_readiness_binding_conflict",
                "Harness readiness is already bound to another operator or evidence.",
            )
        updated = json.loads(json.dumps(current))
        operator_digest = sha256_text(operator_id)
        if not already_ready:
            updated["harness_readiness"] = HARNESS_READY
            updated["harness_readiness_evidence"] = evidence
            updated["harness_readiness_operator"] = operator_id
            updated["harness_readiness_verified_at"] = now()
            atomic_json(locked_lease_path, updated)
            append_event(
                run_root,
                make_event(
                    updated["run_id"],
                    "qualification.harness-ready",
                    "observed",
                    data={
                        "operator_id_sha256": operator_digest,
                        "source_binding_verified": True,
                        "operator_confirmation": True,
                        "evidence": evidence,
                        "shell_readiness": _shell_readiness(updated),
                        "harness_readiness": HARNESS_READY,
                        "transcript_read": False,
                        "binding_fingerprint": binding["fingerprint"],
                        "startup_gate_count": len(
                            updated.get("startup_gate_operations", [])
                        ),
                    },
                ),
            )
    return {
        "schema": "herdr-puppet.qualification-harness-ready.v1",
        "result": "ok",
        "run_id": updated["run_id"],
        "operator_id_sha256": operator_digest,
        "source_binding_verified": True,
        "operator_confirmation": True,
        "shell_readiness": _shell_readiness(updated),
        "harness_readiness": HARNESS_READY,
        "already_ready": already_ready,
        "binding_fingerprint": binding["fingerprint"],
        "startup_gate_count": len(
            updated.get("startup_gate_operations", [])
        ),
        "transcript_read": False,
    }


def qualification_claude_receipt_command(
    *,
    lease_payload: dict[str, Any],
    lease_path: Path,
) -> dict[str, Any]:
    validate_lease(lease_payload)
    with _lease_lock(lease_path) as locked_lease_path:
        current = _reload_locked_lease(lease_payload, locked_lease_path)
        if current["harness"] != "claude":
            raise HerdrPuppetError(
                "claude_lifecycle_wrong_harness",
                "Native Claude receipt generation applies only to Claude rows.",
            )
        if current["state"] not in {"active", "preserved"}:
            raise HerdrPuppetError(
                "lease_state_invalid",
                "Claude receipt generation requires an active or preserved lease.",
            )
        binding = _require_current_record_binding(current)
        observation = binding["lifecycle_observation"]
        argv = claude_helper_exec_argv(
            observation,
            [
                "observe",
                "--root",
                observation["marker_root"],
                "--run-id",
                observation["run_id"],
                "--probe-id",
                observation["probe_id"],
                "--implementation-sha256",
                observation["implementation"]["sha256"],
            ],
        )
    return {
        "schema": "herdr-puppet.claude-receipt-command.v1",
        "result": "ok",
        "run_id": current["run_id"],
        "ssh_target": current["ssh"]["target"],
        "argv": argv,
        "shell_command": shlex.join(argv),
        "helper_sha256": observation["helper"]["sha256"],
        "implementation_sha256": observation["implementation"]["sha256"],
        "raw_input_retained": False,
        "transcript_read": False,
    }


def qualification_send(
    client: HerdrClient,
    *,
    lease_payload: dict[str, Any],
    lease_path: Path,
    seq: int,
    text: str,
    text_file: str | None = None,
    instruction_manifest: dict[str, Any] | None = None,
    allow_live: bool,
    run_root: Path,
    checkpoint_nonce: str | None = None,
) -> dict[str, Any]:
    validate_lease(lease_payload)
    require_initialized_journal(
        run_root,
        lease_payload=lease_payload,
    )
    if not allow_live:
        raise HerdrPuppetError(
            "live_qualification_not_authorized",
            "The command flag must authorize live qualification.",
        )
    normalized_text = text.replace("\r\n", "\n").replace("\r", "\n")
    if STRICT_CHECKPOINT_TOKEN.search(normalized_text):
        raise HerdrPuppetError(
            "checkpoint_echo_unsafe",
            "Harness input must describe the checkpoint composition without "
            "containing an assembled strict checkpoint token.",
        )
    with _lease_lock(lease_path) as locked_lease_path:
        current = _reload_locked_lease(lease_payload, locked_lease_path)
        if current["state"] != "active":
            raise HerdrPuppetError("lease_not_active", "The lease is not active.")
        if seq != current["next_seq"]:
            raise HerdrPuppetError(
                "send_sequence_mismatch",
                "Send sequence is stale, skipped, duplicate, or replayed.",
                details={"expected": current["next_seq"], "received": seq},
            )
        binding = _require_current_record_binding(current)
        prior_sends = _require_qualification_send_consistency(
            current,
            run_root,
        )
        if len(prior_sends) >= 2:
            raise HerdrPuppetError(
                (
                    "claude_lifecycle_send_limit"
                    if current["harness"] == "claude"
                    else "qualification_send_limit"
                ),
                "A qualification row permits exactly one wrapped initial "
                "send and one separate steering send.",
            )
        phase = "initial" if not prior_sends else "steering"
        readiness = current.get("harness_readiness", "unverified")
        checkpoint_driven_initial = (
            current["harness"] == "agy"
            and phase == "initial"
            and readiness == "unverified"
        )
        if checkpoint_driven_initial:
            if (
                _shell_readiness(current) != SHELL_READY
                or "harness_launch" not in current
                or current.get("startup_gate_operations") != []
                or current["next_seq"]
                != current["harness_launch"]["seq"] + 1
            ):
                raise HerdrPuppetError(
                    "agy_bound_launch_missing",
                    "AGY's autonomous initial send requires shell STATUS and "
                    "the exact immediately preceding controller-attested launch.",
                )
            if checkpoint_nonce is None or re.fullmatch(
                r"[A-Za-z0-9._:-]{8,24}", checkpoint_nonce
            ) is None:
                raise HerdrPuppetError(
                    "agy_checkpoint_nonce_required",
                    "AGY's autonomous initial send requires the exact 8-24 "
                    "character checkpoint nonce that its first wait will use.",
                )
            if normalized_text.count(checkpoint_nonce) != 1:
                raise HerdrPuppetError(
                    "agy_checkpoint_nonce_not_bound_to_prompt",
                    "AGY's wrapped initial prompt must contain its expected "
                    "checkpoint nonce exactly once as a split checkpoint fragment.",
                )
        elif checkpoint_nonce is not None:
            raise HerdrPuppetError(
                "checkpoint_nonce_not_applicable",
                "An initial checkpoint nonce is accepted only for AGY's first "
                "autonomous send.",
            )
        elif not _harness_input_admitted(current):
            raise HerdrPuppetError(
                (
                    "harness_readiness_checkpoint_pending"
                    if readiness == HARNESS_CHECKPOINT_PENDING
                    else "harness_readiness_not_proven"
                ),
                "Pane input requires operator readiness or AGY's strict "
                "initial STATUS checkpoint.",
                details={
                    "expected": sorted(HARNESS_INPUT_ADMITTED),
                    "actual": readiness,
                },
            )
        if phase == "initial" and instruction_manifest is None:
            raise HerdrPuppetError(
                "instruction_wrapper_required",
                "The first interactive send requires its validated instruction "
                "wrapper manifest.",
            )
        if phase == "steering" and instruction_manifest is not None:
            raise HerdrPuppetError(
                "instruction_wrapper_steering_forbidden",
                "The separate steering send must not repeat an instruction "
                "wrapper manifest.",
            )
        if current["harness"] == "claude":
            if phase == "initial":
                _require_claude_lifecycle_phase(
                    run_root=run_root,
                    binding=binding,
                    phase="armed",
                    classification="armed",
                )
            else:
                _require_claude_lifecycle_phase(
                    run_root=run_root,
                    binding=binding,
                    phase="initial",
                    classification="response_completed",
                )
        elif phase == "steering":
            _require_initial_send_consumption(
                run_root,
                lease=current,
                initial_send=prior_sends[0],
            )
        checked_instruction_manifest: dict[str, Any] | None = None
        if instruction_manifest is not None:
            checked_instruction_manifest = validate_instruction_manifest(
                instruction_manifest,
                binding_value=binding,
                rendered=text.encode("utf-8"),
            )
            if checked_instruction_manifest["run_id"] != current["run_id"]:
                raise HerdrPuppetError(
                    "instruction_wrapper_run_mismatch",
                    "The instruction wrapper does not match the leased run.",
                )
        status = structural_status(client, lease_payload=current)
        if status["result"] != "ok":
            raise HerdrPuppetError(
                "presend_status_blocked",
                "Structural status blocked the send.",
                details={"blockers": status["blockers"]},
            )
        submit_keys = (
            ["enter", "enter"]
            if current["harness"] == "claude" and "\n" in normalized_text
            else ["enter"]
        )
        text_file_retained = False
        tracked_text_file: str | None = None
        if text_file is not None:
            tracked_text_file = _normalize_prompt_file(text_file)
            text_file_retained = _is_prompt_file_retained(tracked_text_file)
        socket_path = current["session"]["socket"]
        pane_id = current["pane_id"]
        digest = sha256_text(text)
        reservation = {
            "seq": seq,
            "phase": phase,
            "prompt_sha256": digest,
            "transport": "direct",
            "instruction_wrapper_verified": (
                checked_instruction_manifest is not None
            ),
            "delivery_state": "pending_or_unknown",
            "reserved_at": now(),
        }
        reserved = json.loads(json.dumps(current))
        reserved["pending_interactive_send"] = reservation
        if tracked_text_file is not None and text_file_retained:
            reserved["caller_text_files"] = _dedupe_preserve_order(
                _as_text_file_list(reserved.get("caller_text_files", []))
                + [tracked_text_file]
            )
        atomic_json(locked_lease_path, reserved)
        append_event(
            run_root,
            make_event(
                reserved["run_id"],
                "qualification.send-reserved",
                "observed",
                seq=seq,
                prompt_sha256=digest,
                data={
                    "phase": phase,
                    "pane_id": pane_id,
                    "delivery_state": "pending_or_unknown",
                    "instruction_wrapper_verified": (
                        checked_instruction_manifest is not None
                    ),
                    "herdr_mutated": False,
                },
            ),
        )
        client.run_input(socket_path, pane_id, text, keys=submit_keys)
        updated = json.loads(json.dumps(reserved))
        updated["next_seq"] = seq + 1
        updated["pending_interactive_send"] = None
        updated["interactive_sends"] = prior_sends + [
            {
                "seq": seq,
                "phase": phase,
                "prompt_sha256": digest,
                "transport": "direct",
                "instruction_wrapper_verified": (
                    checked_instruction_manifest is not None
                ),
            }
        ]
        if checkpoint_driven_initial:
            updated["harness_readiness"] = HARNESS_CHECKPOINT_PENDING
            updated["harness_readiness_submission_seq"] = seq
            updated["harness_readiness_nonce_sha256"] = sha256_text(
                checkpoint_nonce
            )
        post_send_readiness = updated.get(
            "harness_readiness",
            "unverified",
        )
        harness_acceptance = (
            "unverified"
            if checkpoint_driven_initial
            else post_send_readiness
        )
        atomic_json(locked_lease_path, updated)
        append_event(
            run_root,
            make_event(
                updated["run_id"],
                "qualification.send",
                "ok",
                seq=seq,
                prompt_sha256=digest,
                data={
                        "phase": phase,
                        "pane_id": pane_id,
                        "input_request": "pane.send_input",
                        "transport_acknowledged": True,
                        "acceptance_scope": "herdr_pane_input_only",
                        "outcome": "pane_input_accepted",
                        "shell_readiness": _shell_readiness(current),
                        "harness_readiness": post_send_readiness,
                        "harness_acceptance": harness_acceptance,
                        "checkpoint_echo_protected": True,
                        "caller_text_file_retained": text_file_retained,
                        "prompt_file_tracked": tracked_text_file is not None,
                        "controller_prompt_persisted": False,
                        "caller_input_file_location": (
                            "controller_local"
                            if tracked_text_file is not None
                            else "not_applicable"
                        ),
                        "caller_input_file_lifecycle": (
                            "caller_owned"
                            if tracked_text_file is not None
                            else "not_applicable"
                        ),
                        "submit_key_count": len(submit_keys),
                        "submit_key_vector": submit_keys,
                        "instruction_wrapper": (
                            {
                                "schema": checked_instruction_manifest["schema"],
                                "plane": checked_instruction_manifest["plane"],
                                "policy_fingerprint": checked_instruction_manifest[
                                    "policy_fingerprint"
                                ],
                                "binding_fingerprint": checked_instruction_manifest[
                                    "binding_fingerprint"
                                ],
                                "rendered_sha256": checked_instruction_manifest[
                                    "rendered_sha256"
                                ],
                            }
                            if checked_instruction_manifest is not None
                            else None
                        ),
                },
            ),
        )
    return {
        "schema": "herdr-puppet.qualification-send.v2",
        "result": "ok",
        "run_id": updated["run_id"],
        "pane_id": pane_id,
        "seq": seq,
        "next_seq": updated["next_seq"],
        "prompt_sha256": digest,
        "transport_acknowledged": True,
        "acceptance_scope": "herdr_pane_input_only",
        "outcome": "pane_input_accepted",
        "shell_readiness": _shell_readiness(updated),
        "harness_readiness": post_send_readiness,
        "harness_acceptance": harness_acceptance,
        "checkpoint_echo_protected": True,
        "caller_text_file_retained": text_file_retained,
        "prompt_file_tracked": tracked_text_file is not None,
        "controller_prompt_persisted": False,
        "caller_input_file_location": (
            "controller_local"
            if tracked_text_file is not None
            else "not_applicable"
        ),
        "caller_input_file_lifecycle": (
            "caller_owned" if tracked_text_file is not None else "not_applicable"
        ),
        "submit_key_count": len(submit_keys),
        "submit_key_vector": submit_keys,
        "prompt_persisted": False,
        "instruction_wrapper": (
            {
                "schema": checked_instruction_manifest["schema"],
                "plane": checked_instruction_manifest["plane"],
                "policy_fingerprint": checked_instruction_manifest[
                    "policy_fingerprint"
                ],
                "binding_fingerprint": checked_instruction_manifest[
                    "binding_fingerprint"
                ],
                "rendered_sha256": checked_instruction_manifest[
                    "rendered_sha256"
                ],
            }
            if checked_instruction_manifest is not None
            else None
        ),
        "transcript_read": False,
    }


def qualification_reconcile_send(
    client: HerdrClient,
    *,
    lease_payload: dict[str, Any],
    lease_path: Path,
    seq: int,
    text: str,
    evidence: str,
    confirm_applied: bool,
    run_root: Path,
) -> dict[str, Any]:
    validate_lease(lease_payload)
    require_initialized_journal(
        run_root,
        lease_payload=lease_payload,
    )
    if not confirm_applied:
        raise HerdrPuppetError(
            "partial_send_not_confirmed",
            "Reconciliation requires explicit evidence that the text was applied.",
        )
    if (
        not evidence.strip()
        or "\x00" in evidence
        or len(evidence.encode("utf-8"))
        > MAX_RECONCILIATION_EVIDENCE_BYTES
    ):
        raise HerdrPuppetError(
            "partial_send_evidence_missing",
            "Reconciliation requires a concise bounded structural evidence label.",
            details={
                "maximum_bytes": MAX_RECONCILIATION_EVIDENCE_BYTES,
            },
        )
    with _lease_lock(lease_path) as locked_lease_path:
        current = _reload_locked_lease(lease_payload, locked_lease_path)
        _require_current_record_binding(current)
        if current["state"] != "active":
            raise HerdrPuppetError("lease_not_active", "The lease is not active.")
        if current["harness"] == "claude":
            raise HerdrPuppetError(
                "claude_send_reconciliation_unsupported",
                "Claude lifecycle qualification cannot reconcile an unknown send; "
                "preserve the row and start a fresh bounded run.",
            )
        _require_no_pending_sequence_operation(current)
        digest = sha256_text(text)
        lease_sends = _as_interactive_sends(
            current.get("interactive_sends", []),
            next_seq=current["next_seq"],
        )
        journal_state = _qualification_journal_send_state(
            run_root,
            run_id=current["run_id"],
        )
        completed_reconcile = (
            len(lease_sends) == 2
            and lease_sends[1]["phase"] == "steering"
            and lease_sends[1]["transport"] == "reconciled"
        )
        repair_completion_event = False
        if completed_reconcile:
            completed_send = lease_sends[1]
            if (
                completed_send["seq"] != seq
                or completed_send["prompt_sha256"] != digest
                or completed_send["instruction_wrapper_verified"] is not False
                or current["next_seq"] != seq + 1
                or current.get("pending_interactive_send") is not None
            ):
                raise HerdrPuppetError(
                    "steering_reconciliation_reservation_mismatch",
                    "The completed reconciliation does not match this exact retry.",
                )
            if journal_state == lease_sends[:1]:
                repair_completion_event = True
            elif journal_state != lease_sends:
                raise HerdrPuppetError(
                    "qualification_send_history_diverged",
                    "Canonical lease send state and controller journal disagree.",
                )
            if not repair_completion_event:
                durable_evidence = _qualification_reconciled_evidence(
                    run_root,
                    run_id=current["run_id"],
                    seq=seq,
                    prompt_sha256=digest,
                )
                if evidence != durable_evidence:
                    raise HerdrPuppetError(
                        "steering_reconciliation_evidence_mismatch",
                        "The retry evidence does not match the durable "
                        "reconciliation event.",
                    )
                evidence = durable_evidence
            prior_sends = lease_sends[:1]
            pending_send = None
        else:
            prior_sends, pending_send = _qualification_send_state(
                current,
                run_root,
                allow_pending=True,
            )
        if (
            len(prior_sends) != 1
            or prior_sends[0]["transport"] != "direct"
            or prior_sends[0]["phase"] != "initial"
            or prior_sends[0]["instruction_wrapper_verified"] is not True
        ):
            raise HerdrPuppetError(
                "steering_reconciliation_prerequisite_missing",
                "Send reconciliation is limited to the second steering turn "
                "after one proven wrapped initial send.",
            )
        if not completed_reconcile and (
            pending_send is None
            or pending_send["phase"] != "steering"
            or pending_send["seq"] != seq
            or pending_send["prompt_sha256"] != digest
            or pending_send["instruction_wrapper_verified"] is not False
        ):
            raise HerdrPuppetError(
                "steering_reconciliation_reservation_mismatch",
                "Reconciliation requires the exact durably reserved, "
                "delivery-unknown steering send.",
            )
        _require_initial_send_consumption(
            run_root,
            lease=current,
            initial_send=prior_sends[0],
        )
        expected_next_seq = seq + 1 if completed_reconcile else seq
        if current["next_seq"] != expected_next_seq:
            raise HerdrPuppetError(
                "send_sequence_mismatch",
                "Send sequence is stale, skipped, duplicate, or replayed.",
                details={
                    "expected": expected_next_seq,
                    "received": current["next_seq"],
                },
            )
        if not _harness_input_admitted(current):
            raise HerdrPuppetError(
                "harness_readiness_not_proven",
                "Pane-input reconciliation requires explicit harness readiness.",
            )
        if not completed_reconcile:
            status = structural_status(client, lease_payload=current)
            if status["result"] != "ok":
                raise HerdrPuppetError(
                    "reconcile_status_blocked",
                    "Structural status blocked partial-send reconciliation.",
                    details={"blockers": status["blockers"]},
                )
        if completed_reconcile:
            updated = current
        else:
            updated = json.loads(json.dumps(current))
            updated["next_seq"] = seq + 1
            updated["pending_interactive_send"] = None
            updated["interactive_sends"] = prior_sends + [
                {
                    "seq": seq,
                    "phase": "steering",
                    "prompt_sha256": digest,
                    "transport": "reconciled",
                    "instruction_wrapper_verified": False,
                }
            ]
            atomic_json(locked_lease_path, updated)
        if not completed_reconcile or repair_completion_event:
            append_event(
                run_root,
                make_event(
                    updated["run_id"],
                    "qualification.send-reconciled",
                    "observed",
                    seq=seq,
                    prompt_sha256=digest,
                    data={
                            "phase": "steering",
                            "pane_id": updated["pane_id"],
                            "evidence": evidence,
                            "harness_readiness": current.get(
                                "harness_readiness",
                                "unverified",
                            ),
                            "herdr_mutated": False,
                            "completion_event_repaired": repair_completion_event,
                    },
                ),
            )
    return {
        "schema": "herdr-puppet.qualification-send-reconciled.v1",
        "result": "ok",
        "run_id": updated["run_id"],
        "pane_id": updated["pane_id"],
        "seq": seq,
        "next_seq": updated["next_seq"],
        "prompt_sha256": digest,
        "evidence": evidence,
        "herdr_mutated": False,
        "already_reconciled": completed_reconcile,
        "completion_event_repaired": repair_completion_event,
        "transcript_read": False,
    }


def _view_identity(lease: dict[str, Any]) -> dict[str, Any]:
    return {
        "session": lease["session"]["name"],
        "workspace_id": lease["workspace"]["id"],
        "tab_id": lease["tab_id"],
        "pane_id": lease["pane_id"],
        "terminal_id": lease["terminal_id"],
        "ssh_pid": lease["ssh"]["pid"],
        "ssh_target": lease["ssh"]["target"],
    }


def qualification_view_begin(
    client: HerdrClient,
    *,
    lease_payload: dict[str, Any],
    lease_path: Path,
    nonce: str,
    operator_id: str,
    confirm_native_tui_visible: bool,
    allow_live: bool,
    run_root: Path,
) -> dict[str, Any]:
    validate_lease(lease_payload)
    _require_active_lease_journal(run_root, lease_payload)
    if not allow_live:
        raise HerdrPuppetError(
            "live_qualification_not_authorized",
            "The command flag must authorize the native-view checkpoint.",
        )
    if not confirm_native_tui_visible:
        raise HerdrPuppetError(
            "native_tui_not_confirmed",
            "The operator must confirm the exact leased native TUI is visible.",
        )
    if (
        re.fullmatch(r"[A-Za-z0-9._:-]{8,128}", nonce) is None
        or re.fullmatch(r"[A-Za-z0-9._@:-]{1,128}", operator_id) is None
    ):
        raise HerdrPuppetError(
            "invalid_view_checkpoint",
            "The view nonce or operator identity is invalid.",
        )
    nonce_digest = sha256_text(nonce)
    operator_digest = sha256_text(operator_id)
    for event in read_events(run_root):
        if (
            event.get("kind") in {VIEW_BEGIN_KIND, VIEW_COMPLETE_KIND}
            and event.get("nonce_sha256") == nonce_digest
        ):
            raise HerdrPuppetError(
                "view_checkpoint_replay",
                "A native-view checkpoint nonce may be used only once.",
            )
    with _lease_lock(lease_path) as locked_lease_path:
        current = _reload_locked_lease(lease_payload, locked_lease_path)
        _require_current_record_binding(current)
        if current["state"] != "active":
            raise HerdrPuppetError("lease_not_active", "The lease is not active.")
        status = structural_status(client, lease_payload=current)
        if status["result"] != "ok":
            raise HerdrPuppetError(
                "view_status_blocked",
                "Structural status blocked the native-view checkpoint.",
                details={"blockers": status["blockers"]},
            )
        identity = _view_identity(current)
        identity_digest = sha256_text(
            json.dumps(identity, sort_keys=True, separators=(",", ":"))
        )
        append_event(
            run_root,
            make_event(
                current["run_id"],
                VIEW_BEGIN_KIND,
                "observed",
                nonce_sha256=nonce_digest,
                data={
                    "operator_id_sha256": operator_digest,
                    "identity_sha256": identity_digest,
                    "native_tui_visible": True,
                    "detach_reattach_pending": True,
                    "transcript_read": False,
                },
            ),
        )
    return {
        "schema": "herdr-puppet.qualification-view-begin.v1",
        "result": "ok",
        "run_id": current["run_id"],
        "nonce_sha256": nonce_digest,
        "operator_id_sha256": operator_digest,
        "identity_sha256": identity_digest,
        "native_tui_visible": True,
        "detach_reattach_pending": True,
        "transcript_read": False,
    }


def qualification_view_complete(
    client: HerdrClient,
    *,
    lease_payload: dict[str, Any],
    lease_path: Path,
    nonce: str,
    operator_id: str,
    evidence: str,
    confirm_detached_reattached: bool,
    allow_live: bool,
    run_root: Path,
) -> dict[str, Any]:
    validate_lease(lease_payload)
    _require_active_lease_journal(run_root, lease_payload)
    if not allow_live:
        raise HerdrPuppetError(
            "live_qualification_not_authorized",
            "The command flag must authorize detach/reattach completion.",
        )
    if (
        not confirm_detached_reattached
        or evidence != "operator_observed_real_client_detach_reattach"
    ):
        raise HerdrPuppetError(
            "detach_reattach_not_confirmed",
            "Completion requires operator-observed real client detach/reattach.",
        )
    if (
        re.fullmatch(r"[A-Za-z0-9._:-]{8,128}", nonce) is None
        or re.fullmatch(r"[A-Za-z0-9._@:-]{1,128}", operator_id) is None
    ):
        raise HerdrPuppetError(
            "invalid_view_checkpoint",
            "The view nonce or operator identity is invalid.",
        )
    nonce_digest = sha256_text(nonce)
    operator_digest = sha256_text(operator_id)
    begins = [
        event
        for event in read_events(run_root)
        if event.get("kind") == VIEW_BEGIN_KIND
        and event.get("nonce_sha256") == nonce_digest
    ]
    completes = [
        event
        for event in read_events(run_root)
        if event.get("kind") == VIEW_COMPLETE_KIND
        and event.get("nonce_sha256") == nonce_digest
    ]
    if len(begins) != 1 or completes:
        raise HerdrPuppetError(
            "view_checkpoint_missing_or_replayed",
            "Detach/reattach completion requires exactly one unmatched begin record.",
        )
    begin_data = begins[0].get("data") or {}
    if begin_data.get("operator_id_sha256") != operator_digest:
        raise HerdrPuppetError(
            "view_checkpoint_operator_mismatch",
            "Detach/reattach completion must use the same operator identity.",
        )
    with _lease_lock(lease_path) as locked_lease_path:
        current = _reload_locked_lease(lease_payload, locked_lease_path)
        _require_current_record_binding(current)
        if current["state"] != "active":
            raise HerdrPuppetError("lease_not_active", "The lease is not active.")
        status = structural_status(client, lease_payload=current)
        if status["result"] != "ok":
            raise HerdrPuppetError(
                "view_status_blocked",
                "Structural status blocked detach/reattach completion.",
                details={"blockers": status["blockers"]},
            )
        identity = _view_identity(current)
        identity_digest = sha256_text(
            json.dumps(identity, sort_keys=True, separators=(",", ":"))
        )
        if identity_digest != begin_data.get("identity_sha256"):
            raise HerdrPuppetError(
                "view_identity_drift",
                "Leased identities changed across client detach/reattach.",
            )
        append_event(
            run_root,
            make_event(
                current["run_id"],
                VIEW_COMPLETE_KIND,
                "observed",
                nonce_sha256=nonce_digest,
                data={
                    "operator_id_sha256": operator_digest,
                    "identity_sha256": identity_digest,
                    "native_tui_visible": True,
                    "real_client_detach_reattach": True,
                    "leased_identities_unchanged": True,
                    "transcript_read": False,
                },
            ),
        )
    return {
        "schema": "herdr-puppet.qualification-view-complete.v1",
        "result": "ok",
        "run_id": current["run_id"],
        "nonce_sha256": nonce_digest,
        "operator_id_sha256": operator_digest,
        "identity_sha256": identity_digest,
        "native_tui_visible": True,
        "real_client_detach_reattach": True,
        "leased_identities_unchanged": True,
        "transcript_read": False,
    }


def qualification_token_probe(
    client: HerdrClient,
    *,
    lease_payload: dict[str, Any],
    lease_path: Path,
    nonce: str,
    allow_live: bool,
    run_root: Path,
    lines: int = 40,
    timeout_ms: int = 30_000,
) -> dict[str, Any]:
    validate_lease(lease_payload)
    require_initialized_journal(
        run_root,
        lease_payload=lease_payload,
    )
    if not allow_live:
        raise HerdrPuppetError(
            "live_qualification_not_authorized",
            "The command flag must authorize the qualification token probe.",
        )
    if lines < 1 or lines > 80:
        raise HerdrPuppetError(
            "invalid_probe_window",
            "Qualification token probe lines must be between 1 and 80.",
        )
    if timeout_ms < 1 or timeout_ms > 300_000:
        raise HerdrPuppetError(
            "invalid_probe_timeout",
            "Qualification token probe timeout must be between 1 and 300000 ms.",
        )
    with _lease_lock(lease_path) as locked_lease_path:
        current = _reload_locked_lease(lease_payload, locked_lease_path)
        _require_current_record_binding(current)
        drifted = _lease_revision_drifted_fields(lease_payload, current)
        if drifted:
            raise HerdrPuppetError(
                "stale_lease_payload",
                "Token probe requires the caller's exact current lease revision.",
                details={"fields": drifted},
            )
        if current["state"] != "active":
            raise HerdrPuppetError("lease_not_active", "The lease is not active.")
        status = structural_status(client, lease_payload=current)
        if status["result"] != "ok":
            raise HerdrPuppetError(
                "preprobe_status_blocked",
                "Structural status blocked the token probe.",
                details={"blockers": status["blockers"]},
            )
        expected_after_probe = json.loads(json.dumps(current))
    wait_result = client.wait_output(
        current["session"]["name"],
        current["pane_id"],
        nonce,
        lines,
        timeout_ms,
    )
    matched = (
        wait_result is not None
        and wait_result.get("type") == "output_matched"
    )
    revision = wait_result.get("revision") if matched else None
    timeout_source = (
        wait_result.get("timeout_source")
        if wait_result is not None
        and wait_result.get("type") == "output_timeout"
        else None
    )
    nonce_digest = hashlib.sha256(nonce.encode("utf-8")).hexdigest()
    with _lease_lock(lease_path) as locked_lease_path:
        current_after_probe = _reload_locked_lease(
            expected_after_probe,
            locked_lease_path,
        )
        drifted = _lease_revision_drifted_fields(
            expected_after_probe,
            current_after_probe,
        )
        if drifted:
            raise HerdrPuppetError(
                "lease_changed_during_probe",
                "The lease changed while the token probe was active.",
                details={"fields": drifted},
            )
        if run_root is not None:
            append_event(
                run_root,
                make_event(
                    current_after_probe["run_id"],
                    "qualification.token-probe",
                    "ok" if matched else "failed",
                    nonce_sha256=nonce_digest,
                    data={
                        "pane_id": current_after_probe["pane_id"],
                        "matched": matched,
                        "revision": revision,
                        "timeout_source": timeout_source,
                        "wait": "herdr.wait.output",
                    },
                ),
            )
    return {
        "schema": "herdr-puppet.qualification-token-probe.v1",
        "result": "ok" if matched else "not_matched",
        "run_id": current_after_probe["run_id"],
        "pane_id": current_after_probe["pane_id"],
        "matched": matched,
        "nonce_sha256": nonce_digest,
        "pane_text_emitted": False,
        "bounded_lines": lines,
        "timeout_ms": timeout_ms,
        "timeout_source": timeout_source,
        "revision": revision,
    }


def _lease_revision_drifted_fields(
    expected: dict[str, Any],
    current: dict[str, Any],
) -> list[str]:
    validate_lease(current)
    return [
        field
        for field in sorted(LEASE_FIELDS)
        if (field in current) != (field in expected)
        or current.get(field) != expected.get(field)
    ]


def _assert_wait_lease_revision(
    expected: dict[str, Any],
    current: dict[str, Any],
) -> None:
    drifted = _lease_revision_drifted_fields(expected, current)
    if drifted:
        raise HerdrPuppetError(
            "lease_changed_during_wait",
            "The lease changed while the checkpoint wait was active.",
            details={"fields": drifted},
        )


def _beacon_wait_usage(
    run_root: Path,
    nonce_digest: str,
    submission_seq: int,
) -> int:
    numbered_attempts: set[int] = set()
    legacy_completed_attempts = 0
    for event in read_events(run_root):
        if (
            event.get("kind")
            not in {"qualification.beacon", BEACON_RESERVATION_KIND}
            or event.get("nonce_sha256") != nonce_digest
        ):
            continue
        checkpoint = (event.get("data") or {}).get("checkpoint")
        if event.get("kind") == "qualification.beacon" and checkpoint is not None:
            raise HerdrPuppetError(
                "terminal_beacon_nonce_reused",
                "A matched beacon nonce may not be waited again.",
            )
        if event.get("seq") != submission_seq:
            raise HerdrPuppetError(
                "beacon_nonce_submission_mismatch",
                "A beacon nonce may be re-waited only for the same submission.",
            )
        attempt = (event.get("data") or {}).get("attempt")
        if attempt is None and event.get("kind") == "qualification.beacon":
            legacy_completed_attempts += 1
            continue
        if (
            not isinstance(attempt, int)
            or isinstance(attempt, bool)
            or attempt < 1
            or attempt > MAX_BEACON_WAIT_ATTEMPTS
        ):
            raise HerdrPuppetError(
                "invalid_beacon_attempt_journal",
                "Beacon attempt history contains an invalid reservation.",
            )
        numbered_attempts.add(attempt)
    return max(
        max(numbered_attempts, default=0),
        len(numbered_attempts) + legacy_completed_attempts,
    )


def _reserve_beacon_wait_attempt(
    run_root: Path,
    *,
    run_id: str,
    pane_id: str,
    nonce_digest: str,
    submission_seq: int,
) -> int:
    used_attempts = _beacon_wait_usage(
        run_root,
        nonce_digest,
        submission_seq,
    )
    if used_attempts >= MAX_BEACON_WAIT_ATTEMPTS:
        raise HerdrPuppetError(
            "beacon_rewait_limit",
            "A submission nonce permits at most two bounded wait attempts.",
        )
    attempt = used_attempts + 1
    append_event(
        run_root,
        make_event(
            run_id,
            BEACON_RESERVATION_KIND,
            "observed",
            seq=submission_seq,
            nonce_sha256=nonce_digest,
            data={
                "pane_id": pane_id,
                "attempt": attempt,
                "reservation": "durable_before_wait",
                "transcript_read": False,
            },
        ),
    )
    return attempt


def _validate_beacon_wait_reservation(
    run_root: Path,
    *,
    nonce_digest: str,
    submission_seq: int,
    attempt: int,
) -> None:
    reservation_matches = 0
    for event in read_events(run_root):
        if (
            event.get("kind")
            not in {"qualification.beacon", BEACON_RESERVATION_KIND}
            or event.get("nonce_sha256") != nonce_digest
        ):
            continue
        data = event.get("data") or {}
        if (
            event.get("kind") == "qualification.beacon"
            and data.get("checkpoint") is not None
        ):
            raise HerdrPuppetError(
                "terminal_beacon_nonce_reused",
                "A matched beacon nonce may not be waited again.",
            )
        if event.get("seq") != submission_seq:
            raise HerdrPuppetError(
                "beacon_nonce_submission_mismatch",
                "A beacon nonce may be re-waited only for the same submission.",
            )
        if (
            event.get("kind") == BEACON_RESERVATION_KIND
            and data.get("attempt") == attempt
        ):
            reservation_matches += 1
    if reservation_matches != 1:
        raise HerdrPuppetError(
            "beacon_attempt_reservation_invalid",
            "The exact beacon wait attempt reservation is missing or ambiguous.",
        )


def qualification_beacon_wait(
    client: HerdrClient,
    *,
    lease_payload: dict[str, Any],
    lease_path: Path,
    nonce: str,
    allow_live: bool,
    lines: int = 40,
    timeout_ms: int = DEFAULT_BEACON_TIMEOUT_MS,
    run_root: Path,
) -> dict[str, Any]:
    validate_lease(lease_payload)
    if not allow_live:
        raise HerdrPuppetError(
            "live_qualification_not_authorized",
            "The command flag must authorize the qualification beacon wait.",
        )
    if not re.fullmatch(r"[A-Za-z0-9._:-]{8,24}", nonce):
        raise HerdrPuppetError(
            "invalid_beacon_nonce",
            "Beacon nonce must be 8-24 safe identifier characters.",
        )
    if lines < 1 or lines > 80:
        raise HerdrPuppetError(
            "invalid_probe_window",
            "Qualification beacon lines must be between 1 and 80.",
        )
    if timeout_ms < 1 or timeout_ms > MAX_BEACON_TIMEOUT_MS:
        raise HerdrPuppetError(
            "invalid_beacon_timeout",
            "Qualification beacon timeout must be between 1 and 3600000 ms.",
        )
    require_initialized_journal(
        run_root,
        lease_payload=lease_payload,
    )
    nonce_digest = sha256_text(nonce)
    with _lease_lock(lease_path) as locked_lease_path:
        current_before_wait = _reload_locked_lease(
            lease_payload,
            locked_lease_path,
        )
        current_binding = _require_current_record_binding(
            current_before_wait
        )
        if current_before_wait["state"] != "active":
            raise HerdrPuppetError("lease_not_active", "The lease is not active.")
        _require_no_pending_sequence_operation(current_before_wait)
        if current_before_wait.get("pending_interactive_send") is not None:
            raise HerdrPuppetError(
                "qualification_send_delivery_unknown",
                "A checkpoint wait cannot adjudicate a delivery-unknown send; "
                "preserve the row and do not wait, resend, or reconcile it.",
            )
        if (
            current_before_wait["harness"] == "agy"
            and "harness_launch" in current_before_wait
            and current_before_wait.get("harness_readiness") == "unverified"
        ):
            raise HerdrPuppetError(
                "agy_initial_checkpoint_missing",
                "After AGY launch, a checkpoint wait requires the acknowledged "
                "wrapped initial send and its pre-bound nonce.",
            )
        submission_seq = current_before_wait["next_seq"] - 1
        if submission_seq < 1:
            raise HerdrPuppetError(
                "beacon_submission_missing",
                "Beacon waits require a prior sequenced submission.",
            )
        interactive_send_count = 0
        readiness_before_wait = current_before_wait.get(
            "harness_readiness",
            "unverified",
        )
        if (
            readiness_before_wait == HARNESS_CHECKPOINT_PENDING
            or _harness_input_admitted(current_before_wait)
        ):
            interactive_sends = _require_qualification_send_consistency(
                current_before_wait,
                run_root,
            )
            send_count = len(interactive_sends)
            interactive_send_count = send_count
            if (
                readiness_before_wait == HARNESS_CHECKPOINT_PENDING
                and (
                    current_before_wait["harness"] != "agy"
                    or send_count != 1
                )
            ):
                raise HerdrPuppetError(
                    "agy_initial_checkpoint_state_invalid",
                    "Checkpoint-pending AGY readiness requires exactly one "
                    "wrapped initial send.",
                )
            if (
                readiness_before_wait != HARNESS_CHECKPOINT_PENDING
                and send_count not in {1, 2}
            ):
                raise HerdrPuppetError(
                    "qualification_send_count_mismatch",
                    "Admitted beacon waits require one or two bound sends.",
                )
            if interactive_sends[-1]["seq"] != submission_seq:
                raise HerdrPuppetError(
                    "beacon_submission_not_latest_interactive_send",
                    "A post-readiness beacon must bind to the latest exact "
                    "interactive send sequence.",
                )
            if (
                current_before_wait["harness"] == "agy"
                and send_count == 1
                and readiness_before_wait
                in {HARNESS_CHECKPOINT_PENDING, HARNESS_CHECKPOINT_READY}
                and (
                    current_before_wait.get(
                        "harness_readiness_submission_seq"
                    )
                    != submission_seq
                    or current_before_wait.get(
                        "harness_readiness_nonce_sha256"
                    )
                    != nonce_digest
                )
            ):
                raise HerdrPuppetError(
                    "agy_checkpoint_nonce_mismatch",
                    "AGY's first wait must use the exact nonce bound before its "
                    "autonomous initial send.",
                )
            if current_before_wait["harness"] == "claude":
                _require_claude_lifecycle_phase(
                    run_root=run_root,
                    binding=current_binding,
                    phase=("initial" if send_count == 1 else "steering"),
                    classification="response_completed",
                )
        status = structural_status(client, lease_payload=current_before_wait)
        if status["result"] != "ok":
            raise HerdrPuppetError(
                "prewait_status_blocked",
                "Structural status blocked the beacon wait.",
                details={"blockers": status["blockers"]},
            )
        attempt = _reserve_beacon_wait_attempt(
            run_root,
            run_id=current_before_wait["run_id"],
            pane_id=current_before_wait["pane_id"],
            nonce_digest=nonce_digest,
            submission_seq=submission_seq,
        )
        expected_after_wait = json.loads(json.dumps(current_before_wait))
    canonical_pattern = (
        r"^HERDR_PUPPET_("
        + "|".join(CHECKPOINT_KINDS)
        + r") "
        + re.escape(nonce)
        + r"$"
    )
    # Interactive TUIs may add horizontal presentation padding to an otherwise
    # exact assistant line. Codex also renders its assistant response with one
    # U+2022 bullet and horizontal separation. The submitted prompt cannot
    # contain an assembled checkpoint token, so accepting only that
    # harness-scoped, exact presentation marker preserves echo safety while
    # matching the logical line the harness emitted.
    allow_codex_assistant_marker = (
        current_before_wait["harness"] == "codex"
        and _harness_input_admitted(current_before_wait)
    )
    presentation_prefix = (
        r"[ \t\u00a0]*(?:•[ \t\u00a0]+)?"
        if allow_codex_assistant_marker
        else r"[ \t\u00a0]*"
    )
    wait_pattern = (
        r"^"
        + presentation_prefix
        + r"HERDR_PUPPET_("
        + "|".join(CHECKPOINT_KINDS)
        + r") "
        + re.escape(nonce)
        + r"[ \t\u00a0]*$"
    )
    wait_result = client.wait_output(
        current_before_wait["session"]["name"],
        current_before_wait["pane_id"],
        wait_pattern,
        lines,
        timeout_ms,
        regex=True,
    )
    matched_line = (
        wait_result.get("matched_line")
        if wait_result is not None
        and wait_result.get("type") == "output_matched"
        else None
    )
    normalized_line = (
        matched_line.strip(" \t\u00a0")
        if isinstance(matched_line, str)
        else None
    )
    if (
        allow_codex_assistant_marker
        and isinstance(normalized_line, str)
    ):
        normalized_line = re.sub(
            r"^•[ \t\u00a0]+",
            "",
            normalized_line,
            count=1,
        )
    match = (
        re.fullmatch(canonical_pattern, normalized_line)
        if isinstance(normalized_line, str)
        else None
    )
    checkpoint = match.group(1) if match else None
    revision = (
        wait_result.get("revision")
        if wait_result is not None
        and wait_result.get("type") == "output_matched"
        else None
    )
    timeout_source = (
        wait_result.get("timeout_source")
        if wait_result is not None
        and wait_result.get("type") == "output_timeout"
        else None
    )
    result = (
        "human_gate"
        if checkpoint == "ACTION_REQUIRED"
        else "ok"
        if checkpoint == "DONE"
        else "observed"
        if checkpoint == "STATUS"
        else "failed"
    )
    qualification_complete = (
        checkpoint == "DONE"
        and _harness_input_admitted(current_before_wait)
        and interactive_send_count == 2
    )
    auto_preserved = checkpoint in {"ACTION_REQUIRED", "DONE"}
    with _lease_lock(lease_path) as locked_lease_path:
        current_after_wait = _reload_locked_lease(
            expected_after_wait,
            locked_lease_path,
        )
        _assert_wait_lease_revision(expected_after_wait, current_after_wait)
        _validate_beacon_wait_reservation(
            run_root,
            nonce_digest=nonce_digest,
            submission_seq=submission_seq,
            attempt=attempt,
        )
        updated = json.loads(json.dumps(current_after_wait))
        if checkpoint == "STATUS":
            updated["shell_readiness"] = SHELL_READY
            if (
                readiness_before_wait == HARNESS_CHECKPOINT_PENDING
                and current_after_wait["harness"] == "agy"
                and interactive_send_count == 1
            ):
                updated["harness_readiness"] = HARNESS_CHECKPOINT_READY
                updated["harness_readiness_evidence"] = (
                    "strict_initial_status_checkpoint"
                )
                updated["harness_readiness_verified_at"] = now()
        preserve_reason: str | None = None
        if auto_preserved:
            preserve_reason = (
                "human_gate"
                if checkpoint == "ACTION_REQUIRED"
                else "milestone_complete"
            )
            updated["state"] = "preserved"
            updated["preserved_reason"] = preserve_reason
            updated["preserved_at"] = now()
        if updated != current_after_wait:
            atomic_json(locked_lease_path, updated)
        append_event(
            run_root,
            make_event(
                updated["run_id"],
                "qualification.beacon",
                result,
                seq=submission_seq,
                nonce_sha256=nonce_digest,
                data={
                    "pane_id": updated["pane_id"],
                    "checkpoint": checkpoint,
                    "revision": revision,
                    "timeout_source": timeout_source,
                    "wait": "herdr.wait.output.regex",
                    "attempt": attempt,
                    "shell_readiness": _shell_readiness(updated),
                    "harness_readiness": updated.get(
                        "harness_readiness",
                        "unverified",
                    ),
                    "interactive_send_count": interactive_send_count,
                    "qualification_complete": qualification_complete,
                },
            ),
        )
        if preserve_reason is not None:
            append_event(
                run_root,
                make_event(
                    updated["run_id"],
                    "lease.preserved",
                    "human_gate"
                    if preserve_reason == "human_gate"
                    else "observed",
                    data={"reason": preserve_reason, "herdr_mutated": False},
                ),
            )
    return {
        "schema": "herdr-puppet.qualification-beacon-wait.v2",
        "result": result if checkpoint else "not_matched",
        "run_id": updated["run_id"],
        "pane_id": updated["pane_id"],
        "seq": submission_seq,
        "attempt": attempt,
        "checkpoint": checkpoint,
        "matched": checkpoint is not None,
        "nonce_sha256": nonce_digest,
        "pane_text_emitted": False,
        "bounded_lines": lines,
        "timeout_ms": timeout_ms,
        "timeout_source": timeout_source,
        "revision": revision,
        "auto_preserved": auto_preserved,
        "interactive_send_count": interactive_send_count,
        "qualification_complete": qualification_complete,
        "shell_readiness": _shell_readiness(updated),
        "harness_readiness": updated.get("harness_readiness", "unverified"),
        "lease_state": updated["state"],
    }


def preserve_lease(
    *,
    lease_payload: dict[str, Any],
    lease_path: Path,
    reason: str,
    run_root: Path | None = None,
) -> dict[str, Any]:
    _validate_maintainable_lease(lease_payload, allow_historical=True)
    _require_optional_preserve_journal(run_root, lease_payload)
    if reason not in PRESERVE_REASONS:
        raise HerdrPuppetError(
            "invalid_preserve_reason",
            "Lease preservation requires a supported bounded reason.",
            details={"supported": sorted(PRESERVE_REASONS)},
        )
    with _lease_lock(lease_path) as locked_lease_path:
        current = _reload_locked_lease(
            lease_payload,
            locked_lease_path,
            allow_historical=True,
        )
        if current["state"] == "preserved":
            return {
                "schema": "herdr-puppet.lease-preserve.v1",
                "result": "ok",
                "run_id": current["run_id"],
                "state": "preserved",
                "reason": current.get("preserved_reason", reason),
                "already_preserved": True,
                "herdr_mutated": False,
            }
        updated = json.loads(json.dumps(current))
        updated["state"] = "preserved"
        updated["preserved_reason"] = reason
        updated["preserved_at"] = now()
        atomic_json(locked_lease_path, updated)
        if run_root is not None:
            append_event(
                run_root,
                make_event(
                    updated["run_id"],
                    "lease.preserved",
                    "human_gate" if reason == "human_gate" else "observed",
                    data={"reason": reason, "herdr_mutated": False},
                ),
            )
    return {
        "schema": "herdr-puppet.lease-preserve.v1",
        "result": "ok",
        "run_id": updated["run_id"],
        "state": "preserved",
        "reason": reason,
        "already_preserved": False,
        "herdr_mutated": False,
    }
