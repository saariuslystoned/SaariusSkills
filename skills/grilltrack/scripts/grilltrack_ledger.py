#!/usr/bin/env python3
"""Create and evolve a durable, non-destructive GrillTrack ledger."""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import json
import os
import re
import shutil
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "grilltrack/v0.1"
NEW_TRACK_ROLLOVER_FILE = "new_track_rollover.json"
NEW_TRACK_ROLLOVER_SCHEMA = "grilltrack/new-track-rollover/v1"
ACTIVATIONS = {"implicit", "$grilltrack"}
DECISION_STATES = {
    "proposed",
    "locked",
    "implemented",
    "verified",
    "reopened",
    "superseded",
    "needs_reverification",
    "deferred",
}
TRACK_STATES = {"active", "paused", "closed"}
CADENCES = {"sequential", "frontier-batch"}
BLOCKING_CLOSE_STATES = {
    "proposed",
    "locked",
    "implemented",
    "reopened",
    "needs_reverification",
}
ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
NEW_TRACK_FAILPOINTS = {"after_archive", "after_ledger", "after_rollover_stage"}


class LedgerError(RuntimeError):
    """A user-correctable ledger or transition error."""


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def require_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LedgerError(f"{label} must be a non-empty string")
    return value.strip()


def normalize_activation(value: str | None) -> str:
    mechanism = (value or "implicit").strip() or "implicit"
    if mechanism not in ACTIVATIONS:
        raise LedgerError(
            "activation must be implicit or $grilltrack"
        )
    return mechanism


def validate_id(value: str, label: str) -> str:
    value = require_text(value, label)
    if not ID_PATTERN.fullmatch(value):
        raise LedgerError(
            f"{label} must match {ID_PATTERN.pattern} (lower-case, max 64 chars)"
        )
    return value


class Store:
    def __init__(self, project: str) -> None:
        self.project = Path(project).expanduser().resolve()
        if not self.project.is_dir():
            raise LedgerError(f"project directory does not exist: {self.project}")
        self.state_dir = self.project / ".grilltrack"
        self.ledger_path = self.state_dir / "ledger.json"
        self.events_path = self.state_dir / "events.jsonl"
        self.archive_root = self.state_dir / "archive"
        self.rollover_state_path = self.state_dir / "work" / NEW_TRACK_ROLLOVER_FILE

    def guard_state_dir(self) -> None:
        if self.state_dir.is_symlink():
            raise LedgerError(".grilltrack must not be a symlink")

    def initialize_dirs(self) -> None:
        self.guard_state_dir()
        self.state_dir.mkdir(mode=0o755, exist_ok=False)
        (self.state_dir / "proof").mkdir()
        (self.state_dir / "work").mkdir()
        (self.state_dir / ".gitignore").write_text("work/\n", encoding="utf-8")

    def load(self) -> dict[str, Any]:
        self.guard_state_dir()
        if not self.ledger_path.is_file():
            raise LedgerError(
                f"no ledger found at {self.ledger_path}; initialize a track first"
            )
        try:
            data = json.loads(self.ledger_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise LedgerError(f"cannot read ledger: {exc}") from exc
        validate_ledger(data)
        return data

    def write_projection(self, ledger: dict[str, Any]) -> None:
        validate_ledger(ledger)
        payload = json.dumps(ledger, indent=2, sort_keys=True) + "\n"
        self.state_dir.mkdir(mode=0o755, exist_ok=True)
        fd, temporary = tempfile.mkstemp(
            prefix=".ledger-", suffix=".json", dir=self.state_dir
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.ledger_path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def append_event(self, action: str, data: dict[str, Any]) -> None:
        line = self.event_line(action, data)
        with self.events_path.open("a", encoding="utf-8") as handle:
            handle.write(line)
            handle.flush()
            os.fsync(handle.fileno())

    def event_line(self, action: str, data: dict[str, Any]) -> str:
        event = {
            "event_id": str(uuid.uuid4()),
            "at": utc_now(),
            "action": action,
            "data": data,
        }
        return json.dumps(event, sort_keys=True) + "\n"

    def replace_events(self, action: str, data: dict[str, Any]) -> None:
        line = self.event_line(action, data)
        fd, temporary = tempfile.mkstemp(
            prefix=".events-", suffix=".jsonl", dir=self.state_dir
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(line)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.events_path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def write_rollover_state(self, data: dict[str, Any]) -> None:
        self.rollover_state_path.parent.mkdir(mode=0o755, exist_ok=True)
        payload = json.dumps(data, sort_keys=True, indent=2) + "\n"
        fd, temporary = tempfile.mkstemp(
            prefix=".rollover-", suffix=".json", dir=self.rollover_state_path.parent
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.rollover_state_path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def read_rollover_state(self) -> dict[str, Any] | None:
        if not self.rollover_state_path.is_file():
            return None
        try:
            data = json.loads(self.rollover_state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise LedgerError(f"cannot read rollover state: {exc}") from exc
        if not isinstance(data, dict):
            raise LedgerError("rollover state must be an object")
        expected = {
            "schema_version",
            "predecessor_track_id",
            "successor_track_id",
            "title",
            "mechanism",
            "stage",
        }
        if not expected.issubset(data):
            raise LedgerError("rollover state missing required fields")
        if data["schema_version"] != NEW_TRACK_ROLLOVER_SCHEMA:
            raise LedgerError("unsupported rollover state schema")
        if data["stage"] not in {"started", "archived", "ledger_written"}:
            raise LedgerError(f"unknown rollover state stage: {data['stage']}")
        validate_id(data["predecessor_track_id"], "predecessor_track_id")
        validate_id(data["successor_track_id"], "successor_track_id")
        data["title"] = require_text(data["title"], "rollover title")
        if data["mechanism"] not in ACTIVATIONS:
            raise LedgerError("rollover mechanism must be implicit or $grilltrack")
        return data

    def clear_rollover_state(self) -> None:
        if self.rollover_state_path.exists():
            self.rollover_state_path.unlink()

    def archive_closed(self, ledger: dict[str, Any]) -> str:
        if ledger["status"] != "closed":
            raise LedgerError("only a closed track can be archived")
        validate_ledger(ledger)
        if self.archive_root.is_symlink():
            raise LedgerError(".grilltrack/archive must not be a symlink")
        self.archive_root.mkdir(mode=0o755, exist_ok=True)
        archive_dir = self.archive_root / ledger["track_id"]
        archive_ref = f".grilltrack/archive/{ledger['track_id']}"

        if archive_dir.exists():
            if archive_dir.is_symlink():
                raise LedgerError(f"track archive must not be a symlink: {archive_ref}")
            archived_ledger = archive_dir / "ledger.json"
            archived_events = archive_dir / "events.jsonl"
            if (
                archived_ledger.is_file()
                and archived_events.is_file()
                and archived_ledger.read_bytes() == self.ledger_path.read_bytes()
                and archived_events.read_bytes() == self.events_path.read_bytes()
            ):
                return archive_ref
            raise LedgerError(f"track archive already exists: {archive_ref}")

        temporary = Path(
            tempfile.mkdtemp(prefix=".archive-", dir=self.archive_root)
        )
        try:
            shutil.copy2(self.ledger_path, temporary / "ledger.json")
            shutil.copy2(self.events_path, temporary / "events.jsonl")
            os.replace(temporary, archive_dir)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)
        return archive_ref

    def archived_track_ids(self) -> set[str]:
        if not self.archive_root.is_dir():
            return set()
        return {item.name for item in self.archive_root.iterdir()}

    def persist(
        self, ledger: dict[str, Any], action: str, data: dict[str, Any]
    ) -> None:
        ledger["updated_at"] = utc_now()
        validate_ledger(ledger)
        self.write_projection(ledger)
        self.append_event(action, data)


def decision_map(ledger: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {decision["id"]: decision for decision in ledger["decisions"]}


def transition(
    decision: dict[str, Any],
    new_status: str,
    note: str,
    changes: dict[str, Any] | None = None,
) -> None:
    old_status = decision["status"]
    snapshot = {
        "at": utc_now(),
        "from": old_status,
        "to": new_status,
        "note": note,
        "choice": decision.get("choice"),
        "implementation_ref": decision.get("implementation_ref"),
        "verification_ref": decision.get("verification_ref"),
    }
    decision.setdefault("history", []).append(snapshot)
    if changes:
        decision.update(changes)
    decision["status"] = new_status
    decision["updated_at"] = utc_now()


def transitive_dependents(
    decisions: dict[str, dict[str, Any]], root_id: str
) -> list[dict[str, Any]]:
    affected: list[dict[str, Any]] = []
    frontier = {root_id}
    seen = {root_id}
    while frontier:
        next_frontier: set[str] = set()
        for decision in decisions.values():
            if decision["id"] in seen:
                continue
            if frontier.intersection(decision["dependencies"]):
                affected.append(decision)
                seen.add(decision["id"])
                next_frontier.add(decision["id"])
        frontier = next_frontier
    return affected


def mark_dependents_for_reverification(
    ledger: dict[str, Any], root_id: str, reason: str
) -> list[str]:
    decisions = decision_map(ledger)
    affected_ids: list[str] = []
    for dependent in transitive_dependents(decisions, root_id):
        if dependent["status"] not in {"locked", "implemented", "verified"}:
            continue
        transition(
            dependent,
            "needs_reverification",
            f"dependency {root_id} changed: {reason}",
        )
        affected_ids.append(dependent["id"])
    return affected_ids


def validate_ledger(ledger: Any) -> None:
    if not isinstance(ledger, dict):
        raise LedgerError("ledger must be a JSON object")
    if ledger.get("schema_version") != SCHEMA_VERSION:
        raise LedgerError(f"schema_version must be {SCHEMA_VERSION}")
    validate_id(ledger.get("track_id"), "track_id")
    predecessor = ledger.get("predecessor_track_id")
    if predecessor is not None:
        predecessor = validate_id(predecessor, "predecessor_track_id")
        if predecessor == ledger["track_id"]:
            raise LedgerError("a track cannot be its own predecessor")
    require_text(ledger.get("title"), "title")
    if ledger.get("status") not in TRACK_STATES:
        raise LedgerError(f"track status must be one of {sorted(TRACK_STATES)}")
    require_text(ledger.get("created_at"), "created_at")
    require_text(ledger.get("updated_at"), "updated_at")

    focus = ledger.get("current_focus")
    if focus is not None:
        if not isinstance(focus, dict):
            raise LedgerError("current_focus must be an object or null")
        require_text(focus.get("domain"), "current_focus.domain")
        if focus.get("cadence") not in CADENCES:
            raise LedgerError(
                f"current_focus.cadence must be one of {sorted(CADENCES)}"
            )
        if not isinstance(focus.get("confirmed"), bool):
            raise LedgerError("current_focus.confirmed must be boolean")

    decisions = ledger.get("decisions")
    if not isinstance(decisions, list):
        raise LedgerError("decisions must be an array")
    by_id: dict[str, dict[str, Any]] = {}
    for decision in decisions:
        if not isinstance(decision, dict):
            raise LedgerError("every decision must be an object")
        decision_id = validate_id(decision.get("id"), "decision.id")
        if decision_id in by_id:
            raise LedgerError(f"duplicate decision id: {decision_id}")
        by_id[decision_id] = decision
        require_text(decision.get("domain"), f"{decision_id}.domain")
        require_text(decision.get("question"), f"{decision_id}.question")
        require_text(decision.get("choice"), f"{decision_id}.choice")
        if decision.get("status") not in DECISION_STATES:
            raise LedgerError(
                f"{decision_id}.status must be one of {sorted(DECISION_STATES)}"
            )
        dependencies = decision.get("dependencies")
        if not isinstance(dependencies, list) or not all(
            isinstance(item, str) for item in dependencies
        ):
            raise LedgerError(f"{decision_id}.dependencies must be an array of ids")
        if len(dependencies) != len(set(dependencies)):
            raise LedgerError(f"{decision_id}.dependencies contains duplicates")
        if decision_id in dependencies:
            raise LedgerError(f"{decision_id} cannot depend on itself")
        if not isinstance(decision.get("history"), list):
            raise LedgerError(f"{decision_id}.history must be an array")
        if decision["status"] in {"implemented", "verified"}:
            require_text(
                decision.get("implementation_ref"),
                f"{decision_id}.implementation_ref",
            )
        if decision["status"] == "verified":
            require_text(
                decision.get("verification_ref"),
                f"{decision_id}.verification_ref",
            )

    for decision_id, decision in by_id.items():
        missing = [item for item in decision["dependencies"] if item not in by_id]
        if missing:
            raise LedgerError(
                f"{decision_id} has missing dependencies: {', '.join(missing)}"
            )
        superseded_by = decision.get("superseded_by")
        if decision["status"] == "superseded":
            if superseded_by not in by_id or superseded_by == decision_id:
                raise LedgerError(
                    f"{decision_id}.superseded_by must name another decision"
                )

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(decision_id: str) -> None:
        if decision_id in visiting:
            raise LedgerError(f"dependency cycle includes {decision_id}")
        if decision_id in visited:
            return
        visiting.add(decision_id)
        for dependency in by_id[decision_id]["dependencies"]:
            visit(dependency)
        visiting.remove(decision_id)
        visited.add(decision_id)

    for decision_id in by_id:
        visit(decision_id)

    recommendation = ledger.get("recommendation")
    if recommendation is not None:
        if not isinstance(recommendation, dict):
            raise LedgerError("recommendation must be an object or null")
        recommended = require_text(
            recommendation.get("recommended"), "recommendation.recommended"
        )
        alternatives = recommendation.get("alternatives")
        if not isinstance(alternatives, list) or not all(
            isinstance(item, str) and item.strip() for item in alternatives
        ):
            raise LedgerError("recommendation.alternatives must be strings")
        if len(alternatives) > 2:
            raise LedgerError("recommendation allows at most two alternatives")
        if recommended in alternatives or len(alternatives) != len(set(alternatives)):
            raise LedgerError("recommendation choices must be distinct")

    if ledger["status"] == "closed":
        if not isinstance(ledger.get("closeout"), dict):
            raise LedgerError("closed ledger requires closeout")
        blocking = [
            item["id"]
            for item in decisions
            if item["status"] in BLOCKING_CLOSE_STATES
        ]
        if blocking:
            raise LedgerError(
                "closed ledger has unresolved decisions: " + ", ".join(blocking)
            )


def fail_if_requested(point: str) -> None:
    requested = os.environ.get("GRILLTRACK_TEST_FAILPOINT")
    if requested is None:
        return
    if requested == point:
        raise LedgerError(f"simulated failure at {point}")
    if requested not in NEW_TRACK_FAILPOINTS:
        raise LedgerError(f"unknown failure point: {requested}")


def require_mutable(ledger: dict[str, Any]) -> None:
    if ledger["status"] == "closed":
        raise LedgerError("closed tracks are immutable")


def require_active(ledger: dict[str, Any]) -> None:
    require_mutable(ledger)
    if ledger["status"] != "active":
        raise LedgerError("track must be active")


def get_decision(ledger: dict[str, Any], decision_id: str) -> dict[str, Any]:
    decision_id = validate_id(decision_id, "decision id")
    try:
        return decision_map(ledger)[decision_id]
    except KeyError as exc:
        raise LedgerError(f"unknown decision: {decision_id}") from exc


def output(ledger: dict[str, Any]) -> None:
    print(json.dumps(ledger, indent=2, sort_keys=True))


def new_ledger(
    args: argparse.Namespace,
    mechanism: str,
    predecessor_track_id: str | None = None,
) -> dict[str, Any]:
    track_id = (
        validate_id(args.track_id, "track_id")
        if args.track_id
        else f"gt-{dt.datetime.now(dt.timezone.utc):%Y%m%d%H%M%S}-{uuid.uuid4().hex[:6]}"
    )
    now = utc_now()
    ledger = {
        "schema_version": SCHEMA_VERSION,
        "track_id": track_id,
        "title": require_text(args.title, "title"),
        "status": "active",
        "created_at": now,
        "updated_at": now,
        "current_focus": None,
        "decisions": [],
        "recommendation": None,
        "closeout": None,
        "last_activation": {"mechanism": mechanism, "at": now},
    }
    if predecessor_track_id:
        ledger["predecessor_track_id"] = predecessor_track_id
    return ledger


def command_init(store: Store, args: argparse.Namespace) -> None:
    mechanism = normalize_activation(args.activation)
    if store.state_dir.exists():
        raise LedgerError(f"state already exists: {store.state_dir}")
    ledger = new_ledger(args, mechanism)
    store.initialize_dirs()
    store.write_projection(ledger)
    store.replace_events("track_initialized", {"track_id": ledger["track_id"]})
    output(ledger)


def command_new(store: Store, args: argparse.Namespace) -> None:
    mechanism = normalize_activation(args.activation)
    previous = store.load()
    rollover = store.read_rollover_state()
    if rollover is not None:
        predecessor_track_id = rollover["predecessor_track_id"]
        successor_track_id = rollover["successor_track_id"]
        mechanism = rollover["mechanism"]
        if previous["status"] == "active":
            if previous["track_id"] != successor_track_id:
                raise LedgerError(
                    "track rollover recovery is in progress for "
                    f'{rollover["predecessor_track_id"]}'
                )
            if rollover["stage"] == "archived":
                if previous.get("status") != "active":
                    raise LedgerError(
                        "in-progress track rollover expects an active successor ledger"
                    )
                if previous.get("track_id") != successor_track_id:
                    raise LedgerError(
                        "in-progress track rollover has mismatched successor track id"
                    )
                if previous.get("predecessor_track_id") != predecessor_track_id:
                    raise LedgerError(
                        "in-progress track rollover predecessor mismatch"
                    )
                if previous.get("title") != rollover["title"]:
                    raise LedgerError(
                        "in-progress track rollover successor title mismatch"
                    )
                activation = previous.get("last_activation")
                if (
                    not isinstance(activation, dict)
                    or activation.get("mechanism") != mechanism
                ):
                    raise LedgerError(
                        "in-progress track rollover expects an active successor ledger"
                    )
                if previous.get("decisions") != []:
                    raise LedgerError(
                        "in-progress track rollover successor has unexpected decisions"
                    )
                if previous.get("current_focus") is not None:
                    raise LedgerError(
                        "in-progress track rollover successor must not have current focus"
                    )
                if previous.get("recommendation") is not None:
                    raise LedgerError(
                        "in-progress track rollover successor must not have recommendation"
                    )
                if previous.get("closeout") is not None:
                    raise LedgerError(
                        "in-progress track rollover successor must not have closeout"
                    )
            elif rollover["stage"] != "ledger_written":
                raise LedgerError(
                    "cannot recover a new track rollover from this stage"
                )
        elif previous["status"] != "closed":
            raise LedgerError("start a next track only after the current track is closed")
        elif previous["track_id"] != rollover["predecessor_track_id"]:
            raise LedgerError(
                "unmatched rollover state for current track"
            )
    else:
        if previous["status"] != "closed":
            raise LedgerError("start a next track only after the current track is closed")
        predecessor_track_id = previous["track_id"]
        if args.track_id:
            successor_track_id = validate_id(args.track_id, "track_id")
            if successor_track_id == predecessor_track_id:
                raise LedgerError("new track id must not equal predecessor track id")
            if successor_track_id in store.archived_track_ids():
                raise LedgerError(
                    f"new track id already archived: {successor_track_id}"
                )
        else:
            archived_ids = store.archived_track_ids()
            while True:
                successor_track_id = (
                    f"gt-{dt.datetime.now(dt.timezone.utc):%Y%m%d%H%M%S}-{uuid.uuid4().hex[:6]}"
                )
                if (
                    successor_track_id != predecessor_track_id
                    and successor_track_id not in archived_ids
                ):
                    break
        rollover = {
            "schema_version": NEW_TRACK_ROLLOVER_SCHEMA,
            "predecessor_track_id": predecessor_track_id,
            "successor_track_id": successor_track_id,
            "title": require_text(args.title, "title"),
            "mechanism": mechanism,
            "stage": "started",
        }
        store.write_rollover_state(rollover)

    if rollover["stage"] == "started":
        archive_ref = store.archive_closed(previous)
        rollover["archive_ref"] = archive_ref
        rollover["stage"] = "archived"
        store.write_rollover_state(rollover)
        fail_if_requested("after_archive")

    if rollover["stage"] in {"started", "archived"}:
        if rollover["stage"] == "archived" and previous["status"] == "active":
            ledger = previous
        else:
            if previous["status"] != "closed":
                raise LedgerError("cannot recover a new track rollover from this state")
            ledger = new_ledger(
                argparse.Namespace(
                    track_id=successor_track_id,
                    title=rollover["title"],
                ),
                mechanism,
                predecessor_track_id,
            )
            store.write_projection(ledger)
            fail_if_requested("after_ledger")
            rollover["stage"] = "ledger_written"
            store.write_rollover_state(rollover)
            fail_if_requested("after_rollover_stage")
    elif rollover["stage"] == "ledger_written":
        ledger = store.load()
        if ledger["track_id"] != successor_track_id:
            raise LedgerError(
                "in-progress track rollover has mismatched successor track id"
            )
        if ledger["status"] != "active":
            raise LedgerError(
                "in-progress track rollover expects an active successor ledger"
            )

    store.replace_events(
        "track_initialized",
        {
            "track_id": successor_track_id,
            "predecessor_track_id": predecessor_track_id,
            "archive_ref": rollover["archive_ref"],
        },
    )
    store.clear_rollover_state()
    output(ledger)


def command_focus(store: Store, args: argparse.Namespace) -> None:
    ledger = store.load()
    require_active(ledger)
    ledger["current_focus"] = {
        "domain": require_text(args.domain, "domain"),
        "cadence": args.cadence,
        "confirmed": False,
        "status": "grilling",
        "summary": args.summary.strip(),
        "started_at": utc_now(),
    }
    store.persist(
        ledger,
        "focus_started",
        {"domain": args.domain, "cadence": args.cadence},
    )
    output(ledger)


def command_confirm(store: Store, args: argparse.Namespace) -> None:
    ledger = store.load()
    require_active(ledger)
    focus = ledger.get("current_focus")
    if not focus:
        raise LedgerError("start a focused grill before confirmation")
    focus["confirmed"] = True
    focus["status"] = "confirmed"
    focus["summary"] = require_text(args.summary, "summary")
    focus["confirmed_at"] = utc_now()
    store.persist(ledger, "shared_understanding_confirmed", {"summary": args.summary})
    output(ledger)


def command_propose(store: Store, args: argparse.Namespace) -> None:
    ledger = store.load()
    require_active(ledger)
    focus = ledger.get("current_focus")
    if not focus:
        raise LedgerError("start a focused grill before proposing a decision")
    decision_id = validate_id(args.id, "decision id")
    if decision_id in decision_map(ledger):
        raise LedgerError(f"decision already exists: {decision_id}")
    dependencies = [validate_id(item, "dependency id") for item in args.depends_on]
    existing = decision_map(ledger)
    missing = [item for item in dependencies if item not in existing]
    if missing:
        raise LedgerError("missing dependencies: " + ", ".join(missing))
    now = utc_now()
    ledger["decisions"].append(
        {
            "id": decision_id,
            "domain": focus["domain"],
            "question": require_text(args.question, "question"),
            "choice": require_text(args.choice, "choice"),
            "rationale": args.rationale.strip(),
            "dependencies": dependencies,
            "context_ref": args.context_ref,
            "baseline_ref": args.baseline_ref,
            "candidate_refs": args.candidate_ref,
            "implementation_ref": None,
            "verification_ref": None,
            "review_ref": None,
            "delivery_ref": None,
            "superseded_by": None,
            "deferred_reason": None,
            "status": "proposed",
            "created_at": now,
            "updated_at": now,
            "history": [],
        }
    )
    store.persist(ledger, "decision_proposed", {"decision_id": decision_id})
    output(ledger)


def command_lock(store: Store, args: argparse.Namespace) -> None:
    ledger = store.load()
    require_active(ledger)
    decision = get_decision(ledger, args.id)
    if decision["status"] not in {"proposed", "reopened"}:
        raise LedgerError("only proposed or reopened decisions can be locked")
    changes: dict[str, Any] = {}
    if args.choice:
        changes["choice"] = require_text(args.choice, "choice")
    if args.rationale is not None:
        changes["rationale"] = args.rationale.strip()
    transition(decision, "locked", "user accepted the scoped decision", changes)
    store.persist(ledger, "decision_locked", {"decision_id": decision["id"]})
    output(ledger)


def command_implement(store: Store, args: argparse.Namespace) -> None:
    ledger = store.load()
    require_active(ledger)
    focus = ledger.get("current_focus")
    if not focus or not focus.get("confirmed"):
        raise LedgerError("shared understanding must be confirmed before implementation")
    decision = get_decision(ledger, args.id)
    if decision["status"] not in {"locked", "needs_reverification"}:
        raise LedgerError(
            "implementation requires a locked or re-verification-needed decision"
        )
    transition(
        decision,
        "implemented",
        "bounded implementation recorded",
        {"implementation_ref": require_text(args.ref, "implementation ref")},
    )
    store.persist(ledger, "decision_implemented", {"decision_id": decision["id"]})
    output(ledger)


def command_verify(store: Store, args: argparse.Namespace) -> None:
    ledger = store.load()
    require_active(ledger)
    decision = get_decision(ledger, args.id)
    if decision["status"] not in {"implemented", "needs_reverification"}:
        raise LedgerError(
            "verification requires an implemented or re-verification-needed decision"
        )
    transition(
        decision,
        "verified",
        "verification recorded in cumulative context",
        {"verification_ref": require_text(args.ref, "verification ref")},
    )
    store.persist(ledger, "decision_verified", {"decision_id": decision["id"]})
    output(ledger)


def command_reopen(store: Store, args: argparse.Namespace) -> None:
    mechanism = normalize_activation(args.activation)
    ledger = store.load()
    require_mutable(ledger)
    if ledger["status"] == "paused":
        ledger["status"] = "active"
    decision = get_decision(ledger, args.id)
    if decision["status"] in {"reopened", "superseded"}:
        raise LedgerError("decision is already reopened or superseded")
    reason = require_text(args.reason, "reason")
    transition(decision, "reopened", reason)
    affected = mark_dependents_for_reverification(ledger, decision["id"], reason)
    ledger["current_focus"] = {
        "domain": decision["domain"],
        "cadence": "sequential",
        "confirmed": False,
        "status": "grilling",
        "summary": f"Reopen {decision['id']}: {reason}",
        "started_at": utc_now(),
    }
    ledger["last_activation"] = {"mechanism": mechanism, "at": utc_now()}
    store.persist(
        ledger,
        "decision_reopened",
        {"decision_id": decision["id"], "affected": affected, "reason": reason},
    )
    output(ledger)


def command_supersede(store: Store, args: argparse.Namespace) -> None:
    ledger = store.load()
    require_active(ledger)
    decision = get_decision(ledger, args.id)
    replacement = get_decision(ledger, args.by)
    if decision["id"] == replacement["id"]:
        raise LedgerError("a decision cannot supersede itself")
    if decision["status"] == "superseded":
        raise LedgerError("decision is already superseded")
    reason = require_text(args.reason, "reason")
    transition(
        decision,
        "superseded",
        reason,
        {"superseded_by": replacement["id"]},
    )
    affected = mark_dependents_for_reverification(ledger, decision["id"], reason)
    store.persist(
        ledger,
        "decision_superseded",
        {
            "decision_id": decision["id"],
            "replacement_id": replacement["id"],
            "affected": affected,
        },
    )
    output(ledger)


def command_defer(store: Store, args: argparse.Namespace) -> None:
    ledger = store.load()
    require_active(ledger)
    decision = get_decision(ledger, args.id)
    if decision["status"] == "superseded":
        raise LedgerError("superseded decisions cannot be deferred")
    reason = require_text(args.reason, "reason")
    transition(
        decision,
        "deferred",
        reason,
        {"deferred_reason": reason},
    )
    store.persist(ledger, "decision_deferred", {"decision_id": decision["id"]})
    output(ledger)


def command_recommend(store: Store, args: argparse.Namespace) -> None:
    ledger = store.load()
    require_active(ledger)
    if len(args.alternative) > 2:
        raise LedgerError("provide at most two alternatives")
    ledger["recommendation"] = {
        "recommended": require_text(args.recommended, "recommended next grill"),
        "alternatives": [
            require_text(item, "alternative") for item in args.alternative
        ],
        "reason": require_text(args.reason, "reason"),
        "recorded_at": utc_now(),
    }
    if ledger.get("current_focus"):
        ledger["current_focus"]["status"] = "inspected"
    store.persist(ledger, "next_grill_recommended", ledger["recommendation"])
    output(ledger)


def command_pause(store: Store, args: argparse.Namespace) -> None:
    ledger = store.load()
    require_active(ledger)
    ledger["status"] = "paused"
    store.persist(
        ledger,
        "track_paused",
        {
            "reason": require_text(args.reason, "reason"),
            "next_safe_action": require_text(
                args.next_safe_action, "next safe action"
            ),
        },
    )
    output(ledger)


def command_resume(store: Store, args: argparse.Namespace) -> None:
    mechanism = normalize_activation(args.activation)
    ledger = store.load()
    require_mutable(ledger)
    if ledger["status"] != "paused":
        raise LedgerError("only a paused track can be resumed")
    ledger["status"] = "active"
    ledger["last_activation"] = {"mechanism": mechanism, "at": utc_now()}
    store.persist(ledger, "track_resumed", {"activation": mechanism})
    output(ledger)


def command_close(store: Store, args: argparse.Namespace) -> None:
    ledger = store.load()
    require_active(ledger)
    if args.confirmed_by.strip().lower() != "user":
        raise LedgerError("closeout requires --confirmed-by user")
    blocking = [
        decision["id"]
        for decision in ledger["decisions"]
        if decision["status"] in BLOCKING_CLOSE_STATES
    ]
    if blocking:
        raise LedgerError(
            "resolve, verify, supersede, or defer before closeout: "
            + ", ".join(blocking)
        )
    ledger["status"] = "closed"
    if ledger.get("current_focus"):
        ledger["current_focus"]["status"] = "closed"
    ledger["closeout"] = {
        "confirmed_by": "user",
        "closed_at": utc_now(),
        "reason": require_text(args.reason, "reason"),
        "summary": require_text(args.summary, "summary"),
        "proof_refs": args.proof_ref,
        "verified_decisions": [
            item["id"] for item in ledger["decisions"] if item["status"] == "verified"
        ],
        "superseded_decisions": [
            item["id"]
            for item in ledger["decisions"]
            if item["status"] == "superseded"
        ],
        "deferred_decisions": [
            item["id"] for item in ledger["decisions"] if item["status"] == "deferred"
        ],
    }
    store.persist(ledger, "track_closed", copy.deepcopy(ledger["closeout"]))
    output(ledger)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project",
        default=".",
        help="project root that owns .grilltrack/ (default: current directory)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init", help="initialize the first track")
    init.add_argument("--activation", default="implicit")
    init.add_argument("--title", required=True)
    init.add_argument("--track-id")
    init.set_defaults(handler=command_init)

    new = subparsers.add_parser(
        "new", help="preserve a closed track and initialize the next track"
    )
    new.add_argument("--activation", default="implicit")
    new.add_argument("--title", required=True)
    new.add_argument("--track-id")
    new.set_defaults(handler=command_new)

    show = subparsers.add_parser("show", help="print the current ledger")
    show.set_defaults(handler=lambda store, args: output(store.load()))

    validate = subparsers.add_parser("validate", help="validate the current ledger")
    validate.set_defaults(
        handler=lambda store, args: (
            validate_ledger(store.load()),
            print("valid"),
        )
    )

    focus = subparsers.add_parser("focus", help="start a focused grill")
    focus.add_argument("--domain", required=True)
    focus.add_argument("--cadence", choices=sorted(CADENCES), required=True)
    focus.add_argument("--summary", default="")
    focus.set_defaults(handler=command_focus)

    confirm = subparsers.add_parser(
        "confirm", help="record explicit shared-understanding confirmation"
    )
    confirm.add_argument("--summary", required=True)
    confirm.set_defaults(handler=command_confirm)

    propose = subparsers.add_parser("propose", help="record a proposed decision")
    propose.add_argument("--id", required=True)
    propose.add_argument("--question", required=True)
    propose.add_argument("--choice", required=True)
    propose.add_argument("--rationale", default="")
    propose.add_argument("--depends-on", action="append", default=[])
    propose.add_argument("--context-ref")
    propose.add_argument("--baseline-ref")
    propose.add_argument("--candidate-ref", action="append", default=[])
    propose.set_defaults(handler=command_propose)

    lock = subparsers.add_parser("lock", help="lock a proposed or reopened decision")
    lock.add_argument("--id", required=True)
    lock.add_argument("--choice")
    lock.add_argument("--rationale")
    lock.set_defaults(handler=command_lock)

    implement = subparsers.add_parser(
        "implement", help="record bounded implementation"
    )
    implement.add_argument("--id", required=True)
    implement.add_argument("--ref", required=True)
    implement.set_defaults(handler=command_implement)

    verify = subparsers.add_parser("verify", help="record cumulative verification")
    verify.add_argument("--id", required=True)
    verify.add_argument("--ref", required=True)
    verify.set_defaults(handler=command_verify)

    reopen = subparsers.add_parser("reopen", help="reopen a prior decision")
    reopen.add_argument("--activation", default="implicit")
    reopen.add_argument("--id", required=True)
    reopen.add_argument("--reason", required=True)
    reopen.set_defaults(handler=command_reopen)

    supersede = subparsers.add_parser(
        "supersede", help="supersede one decision with another"
    )
    supersede.add_argument("--id", required=True)
    supersede.add_argument("--by", required=True)
    supersede.add_argument("--reason", required=True)
    supersede.set_defaults(handler=command_supersede)

    defer = subparsers.add_parser("defer", help="defer a decision with risk")
    defer.add_argument("--id", required=True)
    defer.add_argument("--reason", required=True)
    defer.set_defaults(handler=command_defer)

    recommend = subparsers.add_parser(
        "recommend", help="record the next-grill recommendation"
    )
    recommend.add_argument("--recommended", required=True)
    recommend.add_argument("--alternative", action="append", default=[])
    recommend.add_argument("--reason", required=True)
    recommend.set_defaults(handler=command_recommend)

    pause = subparsers.add_parser("pause", help="pause a track")
    pause.add_argument("--reason", required=True)
    pause.add_argument("--next-safe-action", required=True)
    pause.set_defaults(handler=command_pause)

    resume = subparsers.add_parser("resume", help="resume a paused track")
    resume.add_argument("--activation", default="implicit")
    resume.set_defaults(handler=command_resume)

    close = subparsers.add_parser("close", help="close after user confirmation")
    close.add_argument("--confirmed-by", required=True)
    close.add_argument("--reason", required=True)
    close.add_argument("--summary", required=True)
    close.add_argument("--proof-ref", action="append", default=[])
    close.set_defaults(handler=command_close)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        store = Store(args.project)
        result = args.handler(store, args)
        if isinstance(result, tuple):
            _ = result
        return 0
    except LedgerError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
