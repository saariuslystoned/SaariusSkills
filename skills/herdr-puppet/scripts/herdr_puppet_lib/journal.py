from __future__ import annotations

import fcntl
import hashlib
import json
import os
import stat
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .authority import (
    canonical_sha256,
    destination_selection_for_record,
    selected_authority,
    selected_authority_sha256,
)
from .errors import HerdrPuppetError


MAX_JOURNAL_EVENT_BYTES = 64 * 1024
MAX_JOURNAL_BYTES = 16 * 1024 * 1024
MAX_PLAN_BYTES = 1024 * 1024


def _open_owned_regular(path: Path, flags: int) -> int:
    safe_flags = flags | getattr(os, "O_CLOEXEC", 0)
    safe_flags |= getattr(os, "O_NOFOLLOW", 0)
    safe_flags |= getattr(os, "O_NONBLOCK", 0)
    descriptor = os.open(path, safe_flags)
    file_stat = os.fstat(descriptor)
    if (
        not stat.S_ISREG(file_stat.st_mode)
        or file_stat.st_uid != os.getuid()
    ):
        os.close(descriptor)
        raise OSError("path is not a caller-owned regular file")
    return descriptor


def _load_bounded_plan(plan_path: Path) -> dict[str, Any]:
    descriptor: int | None = None
    try:
        descriptor = _open_owned_regular(plan_path, os.O_RDONLY)
        plan_stat = os.fstat(descriptor)
        if plan_stat.st_size > MAX_PLAN_BYTES:
            raise OSError("oversized plan")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            encoded = stream.read(MAX_PLAN_BYTES + 1)
        if len(encoded) > MAX_PLAN_BYTES:
            raise OSError("oversized plan")
        plan = json.loads(encoded.decode("utf-8"))
        if not isinstance(plan, dict):
            raise ValueError("plan must be an object")
        return plan
    finally:
        if descriptor is not None:
            os.close(descriptor)


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_DIRECTORY", 0)
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.",
        dir=path.parent,
        text=True,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def atomic_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.",
        dir=path.parent,
        text=True,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def append_event(run_root: Path, event: dict[str, Any]) -> None:
    events_path = run_root / "events.jsonl"
    encoded = json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n"
    encoded_bytes = encoded.encode("utf-8")
    if len(encoded_bytes) > MAX_JOURNAL_EVENT_BYTES:
        raise HerdrPuppetError(
            "journal_event_too_large",
            "The controller journal event exceeds its bounded size.",
        )
    descriptor: int | None = None
    try:
        descriptor = _open_owned_regular(
            events_path,
            os.O_WRONLY | os.O_APPEND,
        )
    except OSError as exc:
        raise HerdrPuppetError(
            "journal_not_initialized",
            "Initialize the controller journal before appending events.",
            details={"run_root": str(run_root)},
        ) from exc
    try:
        with os.fdopen(
            descriptor,
            "a",
            encoding="utf-8",
        ) as handle:
            descriptor = None
            file_descriptor = handle.fileno()
            fcntl.flock(file_descriptor, fcntl.LOCK_EX)
            if os.fstat(file_descriptor).st_size + len(encoded_bytes) > (
                MAX_JOURNAL_BYTES
            ):
                fcntl.flock(file_descriptor, fcntl.LOCK_UN)
                raise HerdrPuppetError(
                    "journal_byte_limit",
                    "The controller journal would exceed its bounded byte limit.",
                    details={"maximum": MAX_JOURNAL_BYTES},
                )
            handle.write(encoded)
            handle.flush()
            os.fsync(file_descriptor)
            fcntl.flock(file_descriptor, fcntl.LOCK_UN)
    finally:
        if descriptor is not None:
            os.close(descriptor)
    atomic_text(run_root / "heartbeat", event["timestamp"] + "\n")


def make_event(
    run_id: str,
    kind: str,
    result: str,
    *,
    seq: int | None = None,
    prompt_sha256: str | None = None,
    command_sha256: str | None = None,
    nonce_sha256: str | None = None,
    note: str | None = None,
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    timestamp = now()
    identity_material = f"{run_id}\0{timestamp}\0{kind}\0{seq or 0}"
    event: dict[str, Any] = {
        "schema": "herdr-puppet.event.v1",
        "event_id": sha256_text(identity_material)[:24],
        "timestamp": timestamp,
        "run_id": run_id,
        "kind": kind,
        "result": result,
    }
    if seq is not None:
        event["seq"] = seq
    if prompt_sha256 is not None:
        event["prompt_sha256"] = prompt_sha256
    if command_sha256 is not None:
        event["command_sha256"] = command_sha256
    if nonce_sha256 is not None:
        event["nonce_sha256"] = nonce_sha256
    if note:
        event["note"] = note
    if data:
        event["data"] = data
    return event


def _require_bound_run_root(run_root: Path, plan: dict[str, Any]) -> None:
    proof_root = plan.get("proof_root")
    if (
        not isinstance(proof_root, str)
        or not proof_root
        or run_root.expanduser().resolve()
        != Path(proof_root).expanduser().resolve()
    ):
        raise HerdrPuppetError(
            "journal_root_mismatch",
            "The controller journal root does not match the plan proof root.",
            details={"run_root": str(run_root)},
        )


def initialize_journal(run_root: Path, plan: dict[str, Any]) -> dict[str, Any]:
    # Local import avoids a module cycle; a fresh journal is mutation authority
    # and therefore accepts only the active plan schema.
    from .core import validate_plan

    validate_plan(plan)
    _require_bound_run_root(run_root, plan)
    if run_root.exists():
        raise HerdrPuppetError(
            "journal_root_exists",
            "The controller journal root already exists.",
            details={"run_root": str(run_root)},
        )
    run_root.mkdir(parents=True)
    atomic_json(run_root / "plan.json", plan)
    (run_root / "events.jsonl").touch(exist_ok=False)
    selection = destination_selection_for_record(plan)
    binding_schema = plan["harness_binding"]["schema"]
    next_action = (
        "create one qualification-owned tab after the live gate"
        if binding_schema == "herdr-puppet.harness-binding.v3"
        else (
            "maintenance only; recensus and create a new active plan-v2 "
            "carrying binding-v3 before fresh qualification"
        )
    )
    state = (
        "# Herdr-Puppet run state\n\n"
        f"- run_id: `{plan['run_id']}`\n"
        "- state: `planned`\n"
        f"- harness: `{plan['harness']}`\n"
        f"- owned_label: `{plan['owned_label']}`\n"
        f"- destination_mode: `{selection['mode']}`\n"
        f"- machine: `{selection['machine'] or 'legacy-explicit'}`\n"
        f"- workspace_label: `{selection['workspace_label']}`\n"
        "- tab_request: `fresh`\n"
        f"- tab_ordinal: `{selection['tab']['ordinal']}`\n"
        f"- model: `{plan['harness_binding']['model_observation']['model']}`\n"
        f"- model_effort: `{plan['harness_binding']['model_observation']['effort']}`\n"
        "- transcript_boundary: `controller journal only`\n"
        f"- next: {next_action}\n"
    )
    proof = (
        "# Herdr-Puppet dogfood proof\n\n"
        f"Run: `{plan['run_id']}`\n\n"
        "## Scope\n\n"
        "One explicitly owned Herdr tab and a transcript-blind controller journal.\n\n"
        "## Evidence\n\n"
        "- `plan.json`: local capability and source intent\n"
        "- `events.jsonl`: append-only structural controller events\n"
        "- `heartbeat`: last controller event time\n\n"
        "## Findings\n\n"
        "Pending.\n\n"
        "## Non-claims\n\n"
        "- No ordinary terminal transcript is copied into this packet.\n"
        "- No delivery, deploy, account, security, or secret authority is implied.\n"
    )
    atomic_text(run_root / "STATE.md", state)
    atomic_text(run_root / "PROOF.md", proof)
    event = make_event(
        plan["run_id"],
        "journal.initialized",
        "ok",
        data={
            "plan_schema": plan["schema"],
            "plan_sha256": canonical_sha256(plan),
            "selected_authority_sha256": selected_authority_sha256(plan),
            "owned_label": plan["owned_label"],
            "destination_selection": selection,
            "fresh_tab_required": True,
            "model_selection": plan["harness_binding"][
                "model_observation"
            ],
        },
    )
    append_event(run_root, event)
    return {
        "schema": "herdr-puppet.journal-init.v1",
        "result": "ok",
        "run_id": plan["run_id"],
        "run_root": str(run_root),
        "files": ["plan.json", "events.jsonl", "heartbeat", "STATE.md", "PROOF.md"],
    }


def read_events(run_root: Path, *, maximum: int = 10_000) -> list[dict[str, Any]]:
    events_path = run_root / "events.jsonl"
    if not events_path.exists():
        raise HerdrPuppetError(
            "journal_not_initialized",
            "The controller journal does not exist.",
            details={"run_root": str(run_root)},
        )
    events: list[dict[str, Any]] = []
    total_bytes = 0
    descriptor: int | None = None
    try:
        descriptor = _open_owned_regular(events_path, os.O_RDONLY)
    except OSError as exc:
        raise HerdrPuppetError(
            "journal_not_initialized",
            "The controller journal does not exist or is unsafe.",
            details={"run_root": str(run_root)},
        ) from exc
    with os.fdopen(descriptor, "rb") as handle:
        descriptor = None
        fcntl.flock(handle.fileno(), fcntl.LOCK_SH)
        try:
            line_number = 0
            while True:
                encoded = handle.readline(MAX_JOURNAL_EVENT_BYTES + 1)
                if not encoded:
                    break
                line_number += 1
                total_bytes += len(encoded)
                if len(encoded) > MAX_JOURNAL_EVENT_BYTES:
                    raise HerdrPuppetError(
                        "journal_event_too_large",
                        "The controller journal contains an oversized event.",
                        details={"line": line_number},
                    )
                if total_bytes > MAX_JOURNAL_BYTES:
                    raise HerdrPuppetError(
                        "journal_byte_limit",
                        "The controller journal exceeds its bounded byte limit.",
                        details={"maximum": MAX_JOURNAL_BYTES},
                    )
                if not encoded.strip():
                    continue
                if len(events) >= maximum:
                    raise HerdrPuppetError(
                        "journal_event_limit",
                        "The controller journal exceeds the bounded event limit.",
                        details={"maximum": maximum},
                    )
                try:
                    line = encoded.decode("utf-8")
                    event = json.loads(line)
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise HerdrPuppetError(
                        "invalid_journal_event",
                        "The controller journal contains malformed JSON.",
                        details={"line": line_number},
                    ) from exc
                if (
                    not isinstance(event, dict)
                    or event.get("schema") != "herdr-puppet.event.v1"
                ):
                    raise HerdrPuppetError(
                        "invalid_journal_event",
                        "The controller journal contains an unsupported event.",
                        details={"line": line_number},
                    )
                events.append(event)
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    return events


def require_initialized_journal(
    run_root: Path,
    *,
    run_id: str | None = None,
    proof_root: str | None = None,
    plan_payload: dict[str, Any] | None = None,
    lease_payload: dict[str, Any] | None = None,
    allow_historical_plan: bool = False,
) -> dict[str, Any]:
    if plan_payload is not None and lease_payload is not None:
        raise HerdrPuppetError(
            "journal_authority_ambiguous",
            "Journal preflight accepts exactly one plan or lease authority.",
        )
    plan_path = run_root / "plan.json"
    events_path = run_root / "events.jsonl"
    try:
        plan = _load_bounded_plan(plan_path)
        events_descriptor = _open_owned_regular(events_path, os.O_RDONLY)
        os.close(events_descriptor)
    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        ValueError,
    ) as exc:
        raise HerdrPuppetError(
            "journal_not_initialized",
            "Initialize the controller journal before mutating Herdr; its "
            "plan is unreadable or malformed.",
            details={"run_root": str(run_root)},
        ) from exc
    from .core import (
        HISTORICAL_LEASE_SCHEMA,
        HISTORICAL_PLAN_SCHEMA,
        LEASE_SCHEMA,
        PLAN_SCHEMA,
        validate_historical_plan,
        validate_lease,
        validate_legacy_lease,
        validate_plan,
    )

    if plan.get("schema") == PLAN_SCHEMA:
        validate_plan(plan)
        active_plan = True
    elif allow_historical_plan and plan.get("schema") == HISTORICAL_PLAN_SCHEMA:
        validate_historical_plan(plan)
        active_plan = False
    else:
        raise HerdrPuppetError(
            "historical_plan_requires_replan",
            "Fresh mutation requires an active plan and journal; historical plan-v1 is read-only evidence.",
        )
    if plan_payload is not None:
        validate_plan(plan_payload)
        run_id = plan_payload["run_id"]
        proof_root = plan_payload["proof_root"]
    elif lease_payload is not None:
        if lease_payload.get("schema") == LEASE_SCHEMA:
            validate_lease(lease_payload)
        elif (
            allow_historical_plan
            and lease_payload.get("schema") == HISTORICAL_LEASE_SCHEMA
        ):
            validate_legacy_lease(lease_payload)
        else:
            raise HerdrPuppetError(
                "invalid_lease_schema",
                "This journal operation does not accept a historical lease.",
            )
        run_id = lease_payload["run_id"]
        proof_root = lease_payload["proof_root"]
    if not isinstance(run_id, str) or not run_id:
        raise HerdrPuppetError(
            "journal_run_mismatch",
            "Journal preflight requires one exact run id.",
        )
    if plan.get("run_id") != run_id:
        raise HerdrPuppetError(
            "journal_run_mismatch",
            "The controller journal belongs to a different run.",
            details={"run_root": str(run_root)},
        )
    if plan_payload is not None and plan != plan_payload:
        raise HerdrPuppetError(
            "journal_plan_mismatch",
            "The incoming plan does not exactly match the initialized journal plan.",
        )
    _require_bound_run_root(run_root, plan)
    if (
        not isinstance(proof_root, str)
        or not proof_root
        or run_root.expanduser().resolve()
        != Path(proof_root).expanduser().resolve()
    ):
        raise HerdrPuppetError(
            "journal_root_mismatch",
            "The controller journal root does not match the exact lease proof root.",
            details={"run_root": str(run_root)},
        )
    events = read_events(run_root)
    if (
        not events
        or events[0].get("kind") != "journal.initialized"
        or events[0].get("run_id") != run_id
    ):
        raise HerdrPuppetError(
            "journal_not_initialized",
            "The controller journal has no matching initialization event.",
            details={"run_root": str(run_root)},
        )
    initialization_data = events[0].get("data")
    if not isinstance(initialization_data, dict):
        raise HerdrPuppetError(
            "journal_initialization_authority_invalid",
            "The journal initialization event has no authority binding.",
        )
    if active_plan:
        expected_initialization = {
            "plan_schema": plan["schema"],
            "plan_sha256": canonical_sha256(plan),
            "selected_authority_sha256": selected_authority_sha256(plan),
        }
        mismatches = [
            field
            for field, expected in expected_initialization.items()
            if initialization_data.get(field) != expected
        ]
        if mismatches:
            raise HerdrPuppetError(
                "journal_initialization_authority_invalid",
                "The journal initialization event does not match its stored plan authority.",
                details={"fields": mismatches},
            )
    if lease_payload is not None:
        plan_authority = selected_authority(plan)
        lease_authority = selected_authority(lease_payload)
        if plan_authority != lease_authority:
            differing_fields = sorted(
                field
                for field in set(plan_authority) | set(lease_authority)
                if plan_authority.get(field) != lease_authority.get(field)
            )
            raise HerdrPuppetError(
                "journal_lease_authority_mismatch",
                "The stored plan and lease select different exact authority.",
                details={"fields": differing_fields},
            )
    return plan


def summarize_journal(run_root: Path, *, recent_limit: int = 20) -> dict[str, Any]:
    if recent_limit < 1 or recent_limit > 100:
        raise HerdrPuppetError(
            "invalid_recent_limit",
            "Recent event limit must be between 1 and 100.",
        )
    events = read_events(run_root)
    counts: dict[str, int] = {}
    for event in events:
        result = str(event.get("result", "unknown"))
        counts[result] = counts.get(result, 0) + 1
    recent = []
    for event in events[-recent_limit:]:
        visible = {
            key: event[key]
            for key in (
                "event_id",
                "timestamp",
                "kind",
                "result",
                "seq",
                "note",
                "data",
                "prompt_sha256",
                "command_sha256",
                "nonce_sha256",
            )
            if key in event
        }
        recent.append(visible)
    return {
        "schema": "herdr-puppet.journal-summary.v1",
        "result": "ok",
        "run_root": str(run_root),
        "event_count": len(events),
        "result_counts": counts,
        "last_event_at": events[-1]["timestamp"] if events else None,
        "recent": recent,
        "transcript_included": False,
    }


def refresh_state(run_root: Path, lease: dict[str, Any] | None = None) -> dict[str, Any]:
    plan_path = run_root / "plan.json"
    try:
        plan = _load_bounded_plan(plan_path)
    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        ValueError,
    ) as exc:
        raise HerdrPuppetError(
            "invalid_journal_plan",
            "The controller journal plan could not be read.",
        ) from exc
    _require_bound_run_root(run_root, plan)
    from .core import (
        HISTORICAL_LEASE_SCHEMA,
        HISTORICAL_PLAN_SCHEMA,
        validate_historical_plan,
        validate_lease,
        validate_legacy_lease,
        validate_plan,
    )

    if plan.get("schema") == HISTORICAL_PLAN_SCHEMA:
        validate_historical_plan(plan)
    else:
        validate_plan(plan)
    if lease is not None:
        if lease.get("schema") == HISTORICAL_LEASE_SCHEMA:
            validate_legacy_lease(lease)
        else:
            validate_lease(lease)
        if lease["run_id"] != plan.get("run_id"):
            raise HerdrPuppetError(
                "journal_run_mismatch",
                "The lease belongs to a different controller journal run.",
            )
    require_initialized_journal(
        run_root,
        run_id=plan["run_id"] if lease is None else None,
        proof_root=plan["proof_root"] if lease is None else None,
        lease_payload=lease,
        allow_historical_plan=True,
    )
    events = read_events(run_root)
    last = events[-1] if events else None
    repairs = sum(event.get("result") == "repair" for event in events)
    failures = sum(event.get("result") == "failed" for event in events)
    state = lease.get("state", "planned") if lease else "planned"
    selection = destination_selection_for_record(plan)
    model = plan["harness_binding"]["model_observation"]
    lines = [
        "# Herdr-Puppet run state",
        "",
        f"- run_id: `{plan['run_id']}`",
        f"- state: `{state}`",
        f"- harness: `{plan['harness']}`",
        f"- owned_label: `{plan['owned_label']}`",
        f"- destination_mode: `{selection['mode']}`",
        f"- machine: `{selection['machine'] or 'legacy-explicit'}`",
        f"- workspace_label: `{selection['workspace_label']}`",
        "- tab_request: `fresh`",
        f"- tab_ordinal: `{selection['tab']['ordinal']}`",
        f"- model: `{model['model']}`",
        f"- model_effort: `{model['effort']}`",
        f"- event_count: `{len(events)}`",
        f"- repair_count: `{repairs}`",
        f"- failure_count: `{failures}`",
        f"- last_event: `{last['kind'] if last else 'none'}`",
        f"- last_event_at: `{last['timestamp'] if last else 'none'}`",
        "- transcript_boundary: `controller journal only`",
    ]
    if lease:
        lines.extend(
            [
                f"- tab_id: `{lease['tab_id']}`",
                f"- pane_id: `{lease['pane_id']}`",
                f"- terminal_id: `{lease['terminal_id']}`",
                f"- next_seq: `{lease['next_seq']}`",
            ]
        )
        if lease.get("cleanup_state") == "closed":
            lines.extend(
                [
                    "- cleanup_state: `closed`",
                    f"- cleanup_verified_at: `{lease['cleanup_verified_at']}`",
                ]
            )
    lines.extend(
        [
            "",
            "Review `events.jsonl` for structural receipts and classified dogfood notes.",
            "",
        ]
    )
    atomic_text(run_root / "STATE.md", "\n".join(lines))
    return {
        "schema": "herdr-puppet.journal-refresh.v1",
        "result": "ok",
        "run_id": plan["run_id"],
        "state": state,
        "cleanup_state": lease.get("cleanup_state") if lease else None,
        "event_count": len(events),
        "state_path": str(run_root / "STATE.md"),
    }
