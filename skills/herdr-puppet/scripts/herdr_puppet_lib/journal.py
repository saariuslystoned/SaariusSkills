from __future__ import annotations

import fcntl
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .errors import HerdrPuppetError


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


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
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def append_event(run_root: Path, event: dict[str, Any]) -> None:
    events_path = run_root / "events.jsonl"
    if not events_path.exists():
        raise HerdrPuppetError(
            "journal_not_initialized",
            "Initialize the controller journal before appending events.",
            details={"run_root": str(run_root)},
        )
    encoded = json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n"
    with events_path.open("a", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    atomic_text(run_root / "heartbeat", event["timestamp"] + "\n")


def make_event(
    run_id: str,
    kind: str,
    result: str,
    *,
    seq: int | None = None,
    prompt_sha256: str | None = None,
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
    if nonce_sha256 is not None:
        event["nonce_sha256"] = nonce_sha256
    if note:
        event["note"] = note
    if data:
        event["data"] = data
    return event


def initialize_journal(run_root: Path, plan: dict[str, Any]) -> dict[str, Any]:
    if run_root.exists():
        raise HerdrPuppetError(
            "journal_root_exists",
            "The controller journal root already exists.",
            details={"run_root": str(run_root)},
        )
    run_root.mkdir(parents=True)
    atomic_json(run_root / "plan.json", plan)
    (run_root / "events.jsonl").touch(exist_ok=False)
    state = (
        "# Herdr-Puppet run state\n\n"
        f"- run_id: `{plan['run_id']}`\n"
        "- state: `planned`\n"
        f"- harness: `{plan['harness']}`\n"
        f"- owned_label: `{plan['owned_label']}`\n"
        "- transcript_boundary: `controller journal only`\n"
        "- next: create one qualification-owned tab after the live gate\n"
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
        data={"owned_label": plan["owned_label"]},
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
    for line_number, line in enumerate(
        events_path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        if not line:
            continue
        if len(events) >= maximum:
            raise HerdrPuppetError(
                "journal_event_limit",
                "The controller journal exceeds the bounded event limit.",
                details={"maximum": maximum},
            )
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise HerdrPuppetError(
                "invalid_journal_event",
                "The controller journal contains malformed JSON.",
                details={"line": line_number},
            ) from exc
        if not isinstance(event, dict) or event.get("schema") != "herdr-puppet.event.v1":
            raise HerdrPuppetError(
                "invalid_journal_event",
                "The controller journal contains an unsupported event.",
                details={"line": line_number},
            )
        events.append(event)
    return events


def require_initialized_journal(run_root: Path, *, run_id: str) -> None:
    plan_path = run_root / "plan.json"
    events_path = run_root / "events.jsonl"
    if not plan_path.exists() or not events_path.exists():
        raise HerdrPuppetError(
            "journal_not_initialized",
            "Initialize the controller journal before mutating Herdr.",
            details={"run_root": str(run_root)},
        )
    try:
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HerdrPuppetError(
            "journal_not_initialized",
            "The controller journal plan is unreadable or malformed.",
            details={"run_root": str(run_root)},
        ) from exc
    if plan.get("run_id") != run_id:
        raise HerdrPuppetError(
            "journal_run_mismatch",
            "The controller journal belongs to a different run.",
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
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HerdrPuppetError(
            "invalid_journal_plan",
            "The controller journal plan could not be read.",
        ) from exc
    events = read_events(run_root)
    last = events[-1] if events else None
    repairs = sum(event.get("result") == "repair" for event in events)
    failures = sum(event.get("result") == "failed" for event in events)
    state = lease.get("state", "planned") if lease else "planned"
    lines = [
        "# Herdr-Puppet run state",
        "",
        f"- run_id: `{plan['run_id']}`",
        f"- state: `{state}`",
        f"- harness: `{plan['harness']}`",
        f"- owned_label: `{plan['owned_label']}`",
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
        "event_count": len(events),
        "state_path": str(run_root / "STATE.md"),
    }
