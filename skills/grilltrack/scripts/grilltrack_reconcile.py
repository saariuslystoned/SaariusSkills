"""Lossless, explicitly applied fork reconciliation within one Git repository."""
from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encoded(data):
    return (json.dumps(data, indent=2, sort_keys=True) + "\n").encode()


def git(project, *args):
    result = subprocess.run(["git", "-C", str(project), *args], capture_output=True)
    if result.returncode:
        raise ValueError("Git input unavailable or incompatible: " + " ".join(args[:2]))
    return result.stdout


def paths(ref, project):
    names = git(project, "ls-tree", "-rz", ref, "--", ".grilltrack").split(b"\0")
    found = {}
    for entry in names:
        if not entry:
            continue
        meta, name = entry.split(b"\t", 1)
        name = name.decode()
        selected = name in {".grilltrack/ledger.json", ".grilltrack/events.jsonl"} or bool(
            re.fullmatch(r"\.grilltrack/archive/[a-z0-9][a-z0-9._-]{0,63}/(?:ledger\.json|events\.jsonl)", name))
        if name.startswith(".grilltrack/archive/") and not selected:
            raise ValueError("unsupported file in snapshot archive")
        if selected:
            if meta.split()[0] not in {b"100644", b"100755"}:
                raise ValueError("snapshot state must contain ordinary files")
            found[name.removeprefix(".grilltrack/")] = git(project, "show", f"{ref}:{name}")
    return found


def validate_complete_event_stream(content):
    if not content or not content.endswith(b"\n"):
        raise ValueError("event stream must be nonempty and newline terminated")


def validate_snapshot(files, api):
    ledgers = {}
    event_ids = {}
    if not {"ledger.json", "events.jsonl"}.issubset(files):
        raise ValueError("snapshot requires ledger and events")
    for name, content in files.items():
        if not name.endswith("ledger.json"):
            continue
        ledger = json.loads(content)
        api.validate_ledger(ledger)
        events_name = name.removesuffix("ledger.json") + "events.jsonl"
        if events_name not in files:
            raise ValueError("snapshot archive missing its event stream")
        if name.startswith("archive/"):
            if ledger["status"] != "closed" or ledger["track_id"] != name.split("/")[1]:
                raise ValueError("archive must be closed and match its directory id")
        if ledger["track_id"] in ledgers:
            raise ValueError("one snapshot contains competing versions of a track")
        ledgers[ledger["track_id"]] = (ledger, files[events_name])
        for line in files[events_name].splitlines():
            event = json.loads(line)
            if not isinstance(event, dict) or not all(isinstance(event.get(k), str) and event[k] for k in ("event_id", "at", "action")) or not isinstance(event.get("data"), dict):
                raise ValueError("malformed event")
            key = event["event_id"]
            if key in event_ids:
                raise ValueError("duplicate event id within a snapshot")
            event_ids[key] = event
    if any(name.endswith("events.jsonl") and name.removesuffix("events.jsonl") + "ledger.json" not in files for name in files):
        raise ValueError("event stream without ledger")
    return ledgers, event_ids


def target_files(store):
    state = store.state_dir
    store.guard_state_dir()
    result = {}
    for name in ("ledger.json", "events.jsonl"):
        p = state / name
        if p.is_symlink() or not p.is_file():
            raise ValueError("target canonical state must contain ordinary files")
        result[name] = p.read_bytes()
    archive = state / "archive"
    if archive.exists():
        if archive.is_symlink():
            raise ValueError("target archive cannot be a symlink")
        for directory in sorted(archive.iterdir()):
            if directory.is_symlink() or not directory.is_dir():
                raise ValueError("invalid target archive directory")
            for name in ("ledger.json", "events.jsonl"):
                p = directory / name
                if p.is_symlink() or not p.is_file():
                    raise ValueError("incomplete target archive")
                result[f"archive/{directory.name}/{name}"] = p.read_bytes()
    return result


def atomic(path, data):
    fd, temporary = tempfile.mkstemp(prefix=".reconcile-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def ordinary_path(path):
    if path.is_symlink() or any(parent.is_symlink() for parent in path.parents):
        raise ValueError("reconciliation artifact must not be a symlink")


def immutable(path, data):
    ordinary_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError("immutable reconciliation artifact differs")
        return
    # Publish only complete bytes. Linking a flushed sibling is atomic and
    # cannot replace an existing artifact, unlike renaming over the final path.
    fd, temporary = tempfile.mkstemp(prefix=".reconcile-immutable-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            ordinary_path(path)
            if path.read_bytes() != data:
                raise ValueError("immutable reconciliation artifact differs")
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def build_plan(store, args, api):
    refs = {role: getattr(args, role + "_ref") for role in ("base", "current", "incoming")}
    for ref in refs.values():
        if not re.fullmatch(r"[0-9a-f]{40}", ref):
            raise ValueError("use full immutable commit ids")
        if git(store.project, "cat-file", "-t", ref).strip() != b"commit":
            raise ValueError("input identity must be a commit")
    for role in ("current", "incoming"):
        git(store.project, "merge-base", "--is-ancestor", refs["base"], refs[role])
    snapshots = {role: paths(ref, store.project) for role, ref in refs.items()}
    base_files = snapshots["base"]
    base_canonical = {name for name in base_files if name in {"ledger.json", "events.jsonl"}}
    if base_canonical and base_canonical != {"ledger.json", "events.jsonl"}:
        raise ValueError("base canonical state must contain ledger and events together")
    if not base_files:
        base_provenance = "no-ledger-base"
        for role in ("current", "incoming"):
            for name, content in snapshots[role].items():
                if name.endswith("events.jsonl"):
                    validate_complete_event_stream(content)
        parsed = {
            role: validate_snapshot(files, api)
            for role, files in snapshots.items()
            if role != "base"
        }
        base = None
        base_id = None
        base_events = None
    else:
        if base_canonical != {"ledger.json", "events.jsonl"}:
            raise ValueError("base without canonical state may not contain other state")
        parsed = {role: validate_snapshot(files, api) for role, files in snapshots.items()}
        base = json.loads(snapshots["base"]["ledger.json"])
        base_provenance = "shared-ledger-base"
        base_id = base["track_id"]
        base_events = snapshots["base"]["events.jsonl"]
        if not base_events or not base_events.endswith(b"\n"):
            raise ValueError("common event stream must be nonempty and newline terminated")
    for role in ("current", "incoming"):
        tracks = parsed[role][0]
        live = json.loads(snapshots[role]["ledger.json"])
        if base_id is not None:
            if base_id not in tracks or not tracks[base_id][1].startswith(base_events):
                raise ValueError("fork does not preserve the exact common event prefix")
            if live["track_id"] != base_id and live.get("predecessor_track_id") != base_id:
                raise ValueError("only the base continuation or its direct successor is supported")
            for name, content in snapshots["base"].items():
                if name.startswith("archive/") and snapshots[role].get(name) != content:
                    raise ValueError("common historical archive changed or disappeared")
    all_events = {}
    for _, events in parsed.values():
        for event_id, event in events.items():
            if event_id in all_events and all_events[event_id] != event:
                raise ValueError("conflicting event identity across forks")
            all_events[event_id] = event
    # A shared base contributes its live track plus each fork's current
    # decisions. With no ledger at the Git base, each fork is authoritative for
    # its own complete history; no synthetic base ledger is fabricated.
    by_id = {}
    provenance = {}
    roles = ("current", "incoming") if base_id is None else ("base", "current", "incoming")
    for role in roles:
        live = json.loads(snapshots[role]["ledger.json"])
        candidates = [live]
        if base_id is not None and live["track_id"] != base_id:
            candidates.append(parsed[role][0][base_id][0])
        for ledger in candidates:
            for decision in ledger["decisions"]:
                key = decision["id"]
                if key in by_id and by_id[key] != decision:
                    # A lifecycle/history divergence for one decision also
                    # needs explicit adjudication. Do not pick a winner.
                    raise ValueError(f"conflicting decision {key}; adjudicate before reconciliation")
                by_id[key] = copy.deepcopy(decision)
                provenance.setdefault(key, []).append({"role": role, "track_id": ledger["track_id"], "source_identity": "git:" + refs[role]})
    manifest = {"schema": "grilltrack/reconcile/v1", "refs": refs, "title": api.require_text(args.title, "title"),
                "snapshots": {role: {name: digest(content) for name, content in sorted(files.items())} for role, files in snapshots.items()}}
    if base_id is None:
        manifest["base_provenance"] = base_provenance
    plan_id = digest(encoded(manifest))
    joined_id = "gt-join-" + plan_id[:32]
    plan = {**manifest, "plan_id": plan_id, "joined_track_id": joined_id,
            "decision_ids": sorted(by_id), "decision_provenance": provenance,
            "needs_reverification": sorted(key for key, d in by_id.items() if d["status"] not in {"superseded", "deferred", "proposed", "reopened"}),
            "composed_verification": False, "composed_review": False,
            "snapshot_ref": f".grilltrack/lineage/{plan_id}"}
    return plan, snapshots, by_id


def rollback(store, journal, old, new):
    for name in ("ledger.json", "events.jsonl"):
        p = store.state_dir / name
        if p.is_symlink() or p.read_bytes() not in (old[name], new[name]):
            raise ValueError("interrupted target changed; refusing rollback over foreign state")
    for name in ("ledger.json", "events.jsonl"):
        atomic(store.state_dir / name, old[name])
    journal.unlink()


def reconcile_command(store, args, api):
    try:
        plan, snapshots, decisions = build_plan(store, args, api)
        state = store.state_dir
        journal = state / "work" / "reconcile-transaction.json"
        lineage = state / "lineage" / plan["plan_id"]
        applied = lineage / "applied.json"
        ordinary_path(journal)
        ordinary_path(applied)
        if args.apply and args.apply != plan["plan_id"]:
            raise ValueError("approved plan digest does not match these exact inputs")
        if journal.exists() and (not args.apply or args.apply != plan["plan_id"]):
            raise ValueError("interrupted reconciliation requires its exact approved apply")
        current = target_files(store)
        if applied.exists() and not journal.exists():
            expected_receipt = encoded({"plan_id": plan["plan_id"], "track_id": plan["joined_track_id"]})
            if applied.read_bytes() != expected_receipt:
                raise ValueError("reconciliation receipt mismatch")
            retained = {lineage / "plan.json": encoded(plan)}
            for role, files in snapshots.items():
                retained.update({lineage / "snapshots" / role / name: content for name, content in files.items()})
            for path, content in retained.items():
                ordinary_path(path)
                if not path.is_file() or path.read_bytes() != content:
                    raise ValueError("retained reconciliation source missing or changed")
            canonical = json.loads(current["ledger.json"])
            joined_name = f"archive/{plan['joined_track_id']}/ledger.json"
            recorded = canonical if canonical.get("track_id") == plan["joined_track_id"] else json.loads(current.get(joined_name, b"{}"))
            if recorded.get("reconciliation", {}).get("plan_id") != plan["plan_id"]:
                raise ValueError("applied track absent from current target history")
            api.output({**plan, "already_applied": True, "applied": True})
            return
        if not journal.exists() and current != snapshots["current"]:
            raise ValueError("target state differs from the exact current commit snapshot")
        if not args.apply:
            api.output({**plan, "already_applied": False, "applied": False})
            return
        # Timestamp is fixed by immutable inputs so staged publication/retry is
        # byte-identical. Original histories remain in the source snapshots.
        now = max(
            json.loads(files["ledger.json"])["updated_at"]
            for files in snapshots.values()
            if "ledger.json" in files
        )
        joined = {"schema_version": api.SCHEMA_VERSION, "track_id": plan["joined_track_id"], "title": plan["title"],
                  "status": "active", "created_at": now, "updated_at": now, "current_focus": None,
                  "decisions": [], "recommendation": None, "closeout": None, "pause": None, "last_pause": None,
                  "last_activation": {"mechanism": "implicit", "at": now},
                  "reconciliation": {"plan_id": plan["plan_id"], "snapshot_ref": plan["snapshot_ref"], "refs": plan["refs"]}}
        for key in plan["decision_ids"]:
            decision = decisions[key]
            decision["reconciliation_sources"] = plan["decision_provenance"][key]
            if key in plan["needs_reverification"]:
                decision["history"].append({"at": now, "from": decision["status"], "to": "needs_reverification",
                    "note": "fork composition invalidates prior current proof", "source_snapshot_ref": plan["snapshot_ref"]})
                decision["status"] = "needs_reverification"
                for field in ("verification_ref", "review_ref", "review_source_identity", "review_result"):
                    decision[field] = None
                decision["review_classifications"] = []
                decision["updated_at"] = now
            joined["decisions"].append(decision)
        api.validate_ledger(joined)
        event = {"event_id": plan["plan_id"], "at": now, "action": "track_reconciled", "data": {"track_id": joined["track_id"], "snapshot_ref": plan["snapshot_ref"], "plan_id": plan["plan_id"]}}
        new = {"ledger.json": encoded(joined), "events.jsonl": encoded(event).replace(b"\n", b" ").strip() + b"\n"}
        if journal.exists():
            if json.loads(journal.read_bytes()).get("plan_id") != plan["plan_id"]:
                raise ValueError("another reconciliation is interrupted")
            rollback(store, journal, snapshots["current"], new)
        if target_files(store) != snapshots["current"]:
            raise ValueError("target changed before publication")
        for role, files in snapshots.items():
            for name, content in files.items():
                immutable(lineage / "snapshots" / role / name, content)
        immutable(lineage / "plan.json", encoded(plan))
        for name, content in new.items():
            immutable(lineage / "projection" / name, content)
        if target_files(store) != snapshots["current"]:
            raise ValueError("target changed while staging reconciliation")
        state.joinpath("work").mkdir(exist_ok=True)
        atomic(journal, encoded({"plan_id": plan["plan_id"]}))
        committed = False
        try:
            if os.environ.get("GRILLTRACK_TEST_FAILPOINT") == "reconcile_before_publish":
                raise ValueError("injected failure before publication")
            atomic(store.ledger_path, new["ledger.json"])
            failpoint = os.environ.get("GRILLTRACK_TEST_FAILPOINT")
            if failpoint == "reconcile_crash_after_ledger":
                os._exit(86)
            if failpoint == "reconcile_after_ledger":
                raise ValueError("injected failure after ledger")
            atomic(store.events_path, new["events.jsonl"])
            if failpoint == "reconcile_after_events":
                raise ValueError("injected failure after events")
            immutable(applied, encoded({"plan_id": plan["plan_id"], "track_id": joined["track_id"]}))
            committed = True
            journal.unlink()
        except Exception:
            if not committed:
                rollback(store, journal, snapshots["current"], new)
            raise
        api.output({**plan, "already_applied": False, "applied": True})
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        raise api.LedgerError(str(exc)) from exc
