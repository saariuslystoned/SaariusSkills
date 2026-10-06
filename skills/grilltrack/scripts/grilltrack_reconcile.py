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
from types import SimpleNamespace


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encoded(data):
    return (json.dumps(data, indent=2, sort_keys=True) + "\n").encode()


def reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_adjudication(path, refs, api):
    try:
        value = json.loads(
            Path(path).read_text(encoding="utf-8"),
            object_pairs_hook=reject_duplicate_keys,
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read adjudication file: {exc}") from exc
    return validate_adjudication(value, refs, api)


def validate_adjudication(value, refs, api):
    if not isinstance(value, dict):
        raise ValueError("adjudication file must be a JSON object")
    if set(value) != {"schema", "refs", "decisions"}:
        raise ValueError("adjudication file has unknown or missing fields")
    if value["schema"] != "grilltrack/adjudication/v1":
        raise ValueError("unsupported adjudication schema")
    supplied_refs = value["refs"]
    if not isinstance(supplied_refs, dict) or set(supplied_refs) != set(refs):
        raise ValueError("adjudication refs must contain exactly base, current, incoming")
    if any(not isinstance(supplied_refs[role], str) for role in refs):
        raise ValueError("adjudication refs must be strings")
    if supplied_refs != refs:
        raise ValueError("adjudication refs do not match the exact reconcile inputs")
    selections = value["decisions"]
    if not isinstance(selections, dict):
        raise ValueError("adjudication decisions must be an object")
    parsed = {}
    for decision_id, selection in selections.items():
        api.validate_id(decision_id, "adjudication decision id")
        if not isinstance(selection, dict) or set(selection) != {"role", "reason"}:
            raise ValueError(
                f"adjudication for {decision_id} has unknown or missing fields"
            )
        role = selection["role"]
        if not isinstance(role, str) or role not in {"base", "current", "incoming"}:
            raise ValueError(f"adjudication for {decision_id} has invalid role")
        parsed[decision_id] = {
            "role": role,
            "reason": api.require_text(
                selection["reason"], f"adjudication reason for {decision_id}"
            ),
        }
    return {
        "schema": value["schema"],
        "refs": dict(supplied_refs),
        "decisions": parsed,
    }


def decision_candidates(snapshots, parsed, base_id, nested_roles=()):
    occurrences = {}
    for role in ("base", "current", "incoming"):
        live = json.loads(snapshots[role]["ledger.json"])
        sources = [("live", live)]
        if live["track_id"] != base_id and role not in nested_roles:
            sources.append(("archive/base-track", parsed[role][0][base_id][0]))
        for source, ledger in sources:
            for decision in ledger["decisions"]:
                occurrences.setdefault(decision["id"], []).append(
                    {"role": role, "source": source, "body": decision}
                )
    return occurrences


def choose_decisions(occurrences, adjudication):
    conflicts = {
        decision_id: items
        for decision_id, items in occurrences.items()
        if any(item["body"] != items[0]["body"] for item in items[1:])
    }
    if adjudication is None:
        if conflicts:
            decision_id = sorted(conflicts)[0]
            raise ValueError(
                f"conflicting decision {decision_id}; adjudicate before reconciliation"
            )
    else:
        selected_ids = set(adjudication["decisions"])
        conflict_ids = set(conflicts)
        if not conflict_ids:
            raise ValueError("adjudication supplied but no decision requires selection")
        unknown = selected_ids - set(occurrences)
        if unknown:
            raise ValueError(
                "adjudication selects unknown decision(s): "
                + ", ".join(sorted(unknown))
            )
        unnecessary = selected_ids - conflict_ids
        if unnecessary:
            raise ValueError(
                "adjudication selects non-conflicting decision(s): "
                + ", ".join(sorted(unnecessary))
            )
        missing = conflict_ids - selected_ids
        if missing:
            raise ValueError(
                "adjudication is missing conflicting decision(s): "
                + ", ".join(sorted(missing))
            )

    chosen = {}
    for decision_id, items in occurrences.items():
        if decision_id not in conflicts:
            chosen[decision_id] = copy.deepcopy(items[0]["body"])
            continue
        selection = adjudication["decisions"][decision_id]
        role_items = [item for item in items if item["role"] == selection["role"]]
        if not role_items:
            raise ValueError(
                f"adjudication for {decision_id} selects an absent role: "
                f"{selection['role']}"
            )
        bodies = {encoded(item["body"]) for item in role_items}
        if len(bodies) != 1:
            raise ValueError(
                f"adjudication for {decision_id} selects an ambiguous role: "
                f"{selection['role']}"
            )
        chosen[decision_id] = copy.deepcopy(role_items[0]["body"])
    return chosen, conflicts


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


def lineage_paths(ref, project):
    """Select immutable join artifacts only; no work or unrelated proof files."""
    entries = git(project, "ls-tree", "-rz", ref, "--", ".grilltrack/lineage").split(b"\0")
    found = {}
    for entry in entries:
        if not entry:
            continue
        meta, raw_name = entry.split(b"\t", 1)
        name = raw_name.decode().removeprefix(".grilltrack/lineage/")
        if Path(name).name.startswith(".reconcile-immutable-"):
            continue
        if (not re.match(r"[0-9a-f]{64}/", name)
                or Path(name).name not in {"ledger.json", "events.jsonl", "plan.json", "applied.json"}
                or meta.split()[0] not in {b"100644", b"100755"}):
            raise ValueError("unsupported file in immutable lineage")
        found[name] = git(project, "show", f"{ref}:.grilltrack/lineage/{name}")
    return found


def cached_paths(ref, project, context, *, lineage=False):
    cache, _ = context
    key = ("lineage" if lineage else "snapshot", str(project), ref)
    if key not in cache:
        cache[key] = (lineage_paths if lineage else paths)(ref, project)
    return cache[key]


def validate_nested_lineage(ref, evidence, store, api, context, inherited):
    """Recompute every retained join from its exact Git inputs and check bytes."""
    cache, visiting = context
    if any(evidence.get(name) != content for name, content in inherited.items()):
        raise ValueError("inherited immutable lineage changed or disappeared from the common base")
    key = (ref, digest(encoded({name: digest(value) for name, value in evidence.items()})),
           digest(encoded({name: digest(value) for name, value in inherited.items()})))
    if key in cache:
        return cache[key]
    if key in visiting or len(visiting) >= 32:
        raise ValueError("cyclic or excessively deep immutable lineage")
    visiting.add(key)
    try:
        plans = {}
        roots = {name.split("/", 1)[0] for name in evidence}
        for plan_id in sorted(roots):
            prefix = plan_id + "/"
            raw = evidence.get(prefix + "plan.json")
            if raw is None:
                raise ValueError("lineage plan is missing")
            plan = json.loads(raw, object_pairs_hook=reject_duplicate_keys)
            if not isinstance(plan, dict) or plan.get("plan_id") != plan_id:
                raise ValueError("lineage plan identity mismatch")
            retained = {name.removeprefix(prefix): value for name, value in evidence.items() if name.startswith(prefix)}
            anchored = {name.removeprefix(prefix): value for name, value in inherited.items() if name.startswith(prefix)}
            if anchored and retained != anchored:
                raise ValueError("inherited immutable lineage changed from the common base")
            refs = plan.get("refs")
            if not isinstance(refs, dict) or set(refs) != {"base", "current", "incoming"}:
                raise ValueError("lineage refs are incomplete")
            for source_ref in refs.values():
                if not isinstance(source_ref, str) or not re.fullmatch(r"[0-9a-f]{40}", source_ref):
                    raise ValueError("lineage ref is not an immutable commit")
                if source_ref == ref:
                    raise ValueError("lineage source cannot be its retaining commit")
                # Existing base artifacts can predate a squash/rebase. Their
                # exact bytes are anchored by the already-proven Git base;
                # newly introduced joins still require source ancestry.
                if not anchored:
                    try:
                        git(store.project, "merge-base", "--is-ancestor", source_ref, ref)
                    except ValueError as exc:
                        raise ValueError("foreign lineage source is not an ancestor of its retaining commit") from exc
            args = SimpleNamespace(**{role + "_ref": value for role, value in refs.items()},
                                   title=plan.get("title"), adjudication_file=None)
            approved = plan.get("adjudication")
            expected_plan, sources, decisions, prior_lineage = build_plan(
                store, args, api, context=context, adjudication=approved)
            if raw != encoded(expected_plan):
                raise ValueError("lineage plan differs from its exact source plan")
            projection = projected_files(expected_plan, sources, decisions, api)
            expected = {"plan.json": encoded(expected_plan),
                        "applied.json": encoded({"plan_id": plan_id, "track_id": expected_plan["joined_track_id"]})}
            expected.update({"projection/" + name: content for name, content in projection.items()})
            for role, files in sources.items():
                expected.update({"snapshots/" + role + "/" + name: content for name, content in files.items()})
            for role, files in prior_lineage.items():
                expected.update({"snapshots/" + role + "/lineage/" + name: content for name, content in files.items()})
            if retained != expected:
                raise ValueError("lineage receipt, projection or snapshots are missing or differ from their exact sources")
            plans[plan_id] = (expected_plan, sources, projection)
        # Reject unrelated joins spliced into this fork's state, even if their
        # source objects happen to exist in the same repository.
        reachable = set()
        pending = [cached_paths(ref, store.project, context)]
        while pending:
            files = pending.pop()
            for name, content in files.items():
                if not name.endswith("ledger.json"):
                    continue
                ledger = json.loads(content)
                record = ledger.get("reconciliation")
                if not isinstance(record, dict):
                    continue
                plan_id = record.get("plan_id")
                if not isinstance(plan_id, str):
                    raise ValueError("lineage metadata requires an immutable plan id")
                if plan_id in reachable:
                    continue
                reachable.add(plan_id)
                if plan_id in plans:
                    _, sources, _ = plans[plan_id]
                    pending.extend(sources.values())
        if roots - reachable:
            raise ValueError("lineage contains an unrelated join")
        cache[key] = plans
        return plans
    finally:
        visiting.remove(key)


def nested_base_proof(live, events, plans, base_files):
    record = live.get("reconciliation")
    if (not isinstance(record, dict) or not isinstance(record.get("plan_id"), str)
            or record["plan_id"] not in plans):
        raise ValueError("nested descendant requires its applied immutable lineage")
    plan, sources, projection = plans[record["plan_id"]]
    if (live["track_id"] != plan["joined_track_id"]
            or record != {"plan_id": plan["plan_id"], "snapshot_ref": plan["snapshot_ref"], "refs": plan["refs"]}
            or not events.startswith(projection["events.jsonl"])):
        raise ValueError("live descendant does not match its immutable lineage")
    # Walk only source joins reachable from the live join, never an arbitrary
    # same-track archive or an orphaned retained plan.
    pending = [sources]
    visited = set()
    while pending:
        source_group = pending.pop()
        for files in source_group.values():
            if (files.get("ledger.json") == base_files["ledger.json"]
                    and files.get("events.jsonl") == base_files["events.jsonl"]):
                return
            if "ledger.json" in files:
                source = json.loads(files["ledger.json"])
                record = source.get("reconciliation")
                previous = record.get("plan_id") if isinstance(record, dict) else None
                if isinstance(previous, str) and previous in plans and previous not in visited:
                    visited.add(previous)
                    prior_plan, prior_sources, prior_projection = plans[previous]
                    if (source["track_id"] != prior_plan["joined_track_id"]
                            or record != {"plan_id": prior_plan["plan_id"], "snapshot_ref": prior_plan["snapshot_ref"], "refs": prior_plan["refs"]}
                            or not files["events.jsonl"].startswith(prior_projection["events.jsonl"])):
                        raise ValueError("source descendant does not match its immutable lineage")
                    if all(prior_projection[name] == base_files[name]
                           for name in ("ledger.json", "events.jsonl")):
                        return
                    pending.append(prior_sources)
    raise ValueError("nested lineage does not retain the exact common base")


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


def build_plan(store, args, api, context=None, adjudication=None):
    if context is None:
        context = ({}, set())
    refs = {role: getattr(args, role + "_ref") for role in ("base", "current", "incoming")}
    for ref in refs.values():
        if not re.fullmatch(r"[0-9a-f]{40}", ref):
            raise ValueError("use full immutable commit ids")
        if git(store.project, "cat-file", "-t", ref).strip() != b"commit":
            raise ValueError("input identity must be a commit")
    for role in ("current", "incoming"):
        git(store.project, "merge-base", "--is-ancestor", refs["base"], refs[role])
    snapshots = {role: cached_paths(ref, store.project, context) for role, ref in refs.items()}
    lineage = {}
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
    nested_base_roles = set()
    for role in ("current", "incoming"):
        tracks = parsed[role][0]
        live = json.loads(snapshots[role]["ledger.json"])
        if base_id is not None:
            direct = (base_id in tracks and tracks[base_id][1].startswith(base_events)
                      and (live["track_id"] == base_id or live.get("predecessor_track_id") == base_id))
            if not direct:
                if not isinstance(live.get("reconciliation"), dict):
                    if base_id not in tracks or not tracks[base_id][1].startswith(base_events):
                        raise ValueError("fork does not preserve the exact common event prefix")
                    raise ValueError("only the base continuation or its direct successor is supported")
                if not lineage:
                    lineage = {source_role: cached_paths(source_ref, store.project, context, lineage=True)
                               for source_role, source_ref in refs.items()}
                plans = validate_nested_lineage(refs[role], lineage[role], store, api, context, lineage["base"])
                nested_base_proof(live, snapshots[role]["events.jsonl"], plans, base_files)
                nested_base_roles.add(role)
            # A nested role contributes its current live decisions; its retained
            # base is ancestry evidence, never a competing current-role body.
            for name, content in snapshots["base"].items():
                if name.startswith("archive/") and snapshots[role].get(name) != content:
                    raise ValueError("common historical archive changed or disappeared")
    if base_id is None:
        historical_decisions = {}
        for role in ("current", "incoming"):
            by_decision_id = {}
            for ledger, _ in parsed[role][0].values():
                for decision in ledger["decisions"]:
                    by_decision_id.setdefault(decision["id"], []).append(decision)
            historical_decisions[role] = by_decision_id
        for decision_id in sorted(
            set(historical_decisions["current"]) & set(historical_decisions["incoming"])
        ):
            for current_decision in historical_decisions["current"][decision_id]:
                for incoming_decision in historical_decisions["incoming"][decision_id]:
                    if current_decision != incoming_decision:
                        raise ValueError(
                            f"conflicting decision {decision_id}; adjudicate before reconciliation"
                        )
    if lineage:
        for role in refs:
            validate_nested_lineage(refs[role], lineage[role], store, api, context, lineage["base"])
    all_events = {}
    event_groups = [events.values() for _, events in parsed.values()]
    event_groups.extend(
        [json.loads(line) for line in content.splitlines()]
        for files in lineage.values() for name, content in files.items()
        if name.endswith("events.jsonl")
    )
    for events in event_groups:
        for event in events:
            event_id = event["event_id"]
            if event_id in all_events and all_events[event_id] != event:
                raise ValueError("conflicting event identity across forks")
            all_events[event_id] = event
    if args.adjudication_file:
        adjudication = load_adjudication(args.adjudication_file, refs, api)
    elif adjudication is not None:
        adjudication = validate_adjudication(adjudication, refs, api)
    if base_id is None:
        if adjudication is not None:
            raise ValueError("adjudication is unsupported for no-ledger-base reconciliation")
        # With no ledger at the Git base, each fork is authoritative for its
        # own complete history; no synthetic base ledger is fabricated.
        by_id = {}
        conflicts = {}
        for role in ("current", "incoming"):
            live = json.loads(snapshots[role]["ledger.json"])
            for decision in live["decisions"]:
                key = decision["id"]
                if key in by_id and by_id[key] != decision:
                    raise ValueError(
                        f"conflicting decision {key}; adjudicate before reconciliation"
                    )
                by_id[key] = copy.deepcopy(decision)
    else:
        # Base-track decisions plus each fork's current decisions. Other
        # historical archives remain history, never reactivated as composition
        # decisions.
        occurrences = decision_candidates(snapshots, parsed, base_id, nested_base_roles)
        by_id, conflicts = choose_decisions(occurrences, adjudication)
    provenance = {}
    roles = ("current", "incoming") if base_id is None else ("base", "current", "incoming")
    for role in roles:
        live = json.loads(snapshots[role]["ledger.json"])
        candidates = [live]
        if base_id is not None and live["track_id"] != base_id and role not in nested_base_roles:
            candidates.append(parsed[role][0][base_id][0])
        for ledger in candidates:
            for decision in ledger["decisions"]:
                key = decision["id"]
                provenance.setdefault(key, []).append({"role": role, "track_id": ledger["track_id"], "source_identity": "git:" + refs[role]})
    # Validate the exact decision projection during planning. Applying the
    # plan validates the same decisions again after adding reconciliation
    # metadata, so dependency and supersession constraints cannot first fail
    # after publication begins.
    projection = copy.deepcopy(json.loads(snapshots["current"]["ledger.json"]))
    projection["track_id"] = "gt-plan-projection"
    projection.pop("predecessor_track_id", None)
    projection["status"] = "active"
    projection["current_focus"] = None
    projection["pause"] = None
    projection["closeout"] = None
    projection["decisions"] = [copy.deepcopy(by_id[key]) for key in sorted(by_id)]
    api.validate_ledger(projection)
    manifest = {"schema": "grilltrack/reconcile/v1", "refs": refs, "title": api.require_text(args.title, "title"),
                "snapshots": {role: {name: digest(content) for name, content in sorted(files.items())} for role, files in snapshots.items()}}
    if any(lineage.values()):
        manifest["lineage"] = {
            role: {name: digest(content) for name, content in sorted(files.items())}
            for role, files in lineage.items()
            if files
        }
    if adjudication is not None:
        manifest["adjudication"] = adjudication
    if base_id is None:
        manifest["base_provenance"] = base_provenance
    plan_id = digest(encoded(manifest))
    joined_id = "gt-join-" + plan_id[:32]
    plan = {**manifest, "plan_id": plan_id, "joined_track_id": joined_id,
            "decision_ids": sorted(by_id), "decision_provenance": provenance,
            "needs_reverification": sorted(key for key, d in by_id.items() if d["status"] not in {"superseded", "deferred", "proposed", "reopened"}),
            "composed_verification": False, "composed_review": False,
            "snapshot_ref": f".grilltrack/lineage/{plan_id}"}
    if adjudication is not None:
        plan["adjudication"] = adjudication
        plan["adjudicated_decisions"] = {
            decision_id: adjudication["decisions"][decision_id]
            for decision_id in sorted(conflicts)
        }
    return plan, snapshots, by_id, lineage


def projected_files(plan, snapshots, decisions, api):
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
        decision = copy.deepcopy(decisions[key])
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
    return new


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
        plan, snapshots, decisions, lineage_sources = build_plan(store, args, api)
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
            for role, files in lineage_sources.items():
                retained.update({
                    lineage / "snapshots" / role / "lineage" / name: content
                    for name, content in files.items()
                })
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
        for name, content in lineage_sources.get("current", {}).items():
            original = state / "lineage" / name
            ordinary_path(original)
            if not original.is_file() or original.read_bytes() != content:
                raise ValueError("target immutable lineage differs from the current commit")
        if not args.apply:
            api.output({**plan, "already_applied": False, "applied": False})
            return
        new = projected_files(plan, snapshots, decisions, api)
        if journal.exists():
            if json.loads(journal.read_bytes()).get("plan_id") != plan["plan_id"]:
                raise ValueError("another reconciliation is interrupted")
            rollback(store, journal, snapshots["current"], new)
        if target_files(store) != snapshots["current"]:
            raise ValueError("target changed before publication")
        for role, files in snapshots.items():
            for name, content in files.items():
                immutable(lineage / "snapshots" / role / name, content)
        for role, files in lineage_sources.items():
            for name, content in files.items():
                immutable(lineage / "snapshots" / role / "lineage" / name, content)
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
            immutable(applied, encoded({"plan_id": plan["plan_id"], "track_id": plan["joined_track_id"]}))
            committed = True
            journal.unlink()
        except Exception:
            if not committed:
                rollback(store, journal, snapshots["current"], new)
            raise
        api.output({**plan, "already_applied": False, "applied": True})
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        raise api.LedgerError(str(exc)) from exc
