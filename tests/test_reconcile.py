from __future__ import annotations

import copy
import json
import hashlib
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

CLI = Path(__file__).resolve().parents[1] / "skills/grilltrack/scripts/grilltrack_ledger.py"
ROOT = Path(__file__).resolve().parents[1]
NOW = "2026-09-01T00:00:00+00:00"


def decision(key):
    return {"id": key, "domain": "fixture", "question": "Choose " + key,
            "choice": "value-" + key, "status": "verified", "dependencies": [],
            "history": [], "review_history": [], "implementation_ref": "fixture:source",
            "verification_ref": "fixture:proof", "review_ref": "fixture:review",
            "review_source_identity": "git:" + "1" * 40, "review_result": "clean",
            "review_classifications": [], "repair_required": False}


def ledger(track, decisions, status="active", predecessor=None):
    value = {"schema_version": "grilltrack/v0.1", "track_id": track, "title": "Synthetic fork",
             "status": status, "created_at": NOW, "updated_at": NOW, "current_focus": None,
             "decisions": decisions, "closeout": {} if status == "closed" else None,
             "recommendation": None, "pause": None, "last_pause": None}
    if predecessor:
        value["predecessor_track_id"] = predecessor
    if status == "paused":
        value["pause"] = {"reason": "fixture pause", "next_safe_action": "reconcile",
                          "paused_at": NOW, "artifact_refs": []}
    return value


def events(start, count, last_action=None):
    return b"".join((json.dumps({"event_id": f"fixture-event-{i}", "at": NOW,
                                "action": last_action if i == start + count - 1 and last_action else "fixture_transition",
                                "data": {"sequence": i}}, sort_keys=True) + "\n").encode()
                    for i in range(start, start + count))


class ReconcileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.project = self.root / "repo"
        self.project.mkdir()
        self.git("init", "-q")
        self.git("config", "user.name", "Fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        state = self.project / ".grilltrack"
        (state / "work").mkdir(parents=True)
        (state / ".gitignore").write_text("work/\n")
        self.shared = [decision(f"shared-{i}") for i in range(8)]
        self.write_state(state, ledger("base-track", self.shared), events(0, 35))
        for i in range(20):
            self.write_state(state / "archive" / f"historical-{i}", ledger(f"historical-{i}", [], "closed"), events(200 + i, 1))
        self.base = self.commit("base")
        continuation = ledger("base-track", self.shared + [decision(f"checkout-{i}") for i in range(4)], "paused")
        self.write_state(state, continuation, events(0, 35) + events(35, 35, "track_paused"))
        self.incoming = self.commit("continuation")
        # Each continuation descends independently from the same base.
        self.git("checkout", "--detach", self.base)
        self.write_state(state / "archive/base-track", ledger("base-track", self.shared, "closed"), events(0, 35) + events(100, 1, "track_closed"))
        self.write_state(state, ledger("successor-track", [decision(f"native-{i}") for i in range(4)], predecessor="base-track"), events(101, 33))
        self.current = self.commit("successor")

    def tearDown(self):
        self.temp.cleanup()

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.project), *args], stderr=subprocess.PIPE).decode().strip()

    def commit(self, message):
        self.git("add", ".grilltrack")
        self.git("commit", "-qm", message)
        return self.git("rev-parse", "HEAD")

    def write_state(self, directory, data, log):
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "ledger.json").write_text(json.dumps(data, indent=2) + "\n")
        (directory / "events.jsonl").write_bytes(log)

    def cli(self, *args, failpoint=None):
        env = os.environ.copy()
        env.pop("GRILLTRACK_TEST_FAILPOINT", None)
        if failpoint:
            env["GRILLTRACK_TEST_FAILPOINT"] = failpoint
        return subprocess.run([sys.executable, str(CLI), "--project", str(self.project), *args], capture_output=True, text=True, env=env)

    def reconcile(self, *extra, failpoint=None):
        return self.cli("reconcile", "--base-ref", self.base, "--current-ref", self.current,
                        "--incoming-ref", self.incoming, "--title", "Composed fixture", *extra, failpoint=failpoint)

    def state_bytes(self):
        state = self.project / ".grilltrack"
        return {str(p.relative_to(state)): p.read_bytes() for p in state.rglob("*") if p.is_file()}

    def plan(self):
        result = self.reconcile()
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def plan_with_adjudication(self, path):
        result = self.reconcile("--adjudication-file", str(path))
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def write_adjudication(self, decisions, **refs):
        data = {
            "schema": "grilltrack/adjudication/v1",
            "refs": {
                "base": refs.get("base", self.base),
                "current": refs.get("current", self.current),
                "incoming": refs.get("incoming", self.incoming),
            },
            "decisions": decisions,
        }
        path = self.root / "adjudication.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def test_exact_fork_preservation_and_honest_projection(self):
        before = self.state_bytes()
        plan = self.plan()
        self.assertNotIn("base_provenance", plan)
        self.assertEqual(
            plan["plan_id"],
            hashlib.sha256(
                (json.dumps(
                    {key: plan[key] for key in ("schema", "refs", "title", "snapshots")},
                    indent=2,
                    sort_keys=True,
                ) + "\n").encode()
            ).hexdigest(),
        )
        self.assertEqual(plan, self.plan())
        self.assertEqual(before, self.state_bytes(), "planning must not write")
        self.assertEqual(len(plan["decision_ids"]), 16)
        result = self.reconcile("--apply", plan["plan_id"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["applied"])
        state = self.project / ".grilltrack"
        for role, ref in (("base", self.base), ("current", self.current), ("incoming", self.incoming)):
            names = self.git("ls-tree", "-r", "--name-only", ref, "--", ".grilltrack").splitlines()
            for name in names:
                if name.endswith("ledger.json") or name.endswith("events.jsonl"):
                    original = subprocess.check_output(["git", "-C", str(self.project), "show", ref + ":" + name])
                    saved = state / "lineage" / plan["plan_id"] / "snapshots" / role / name.removeprefix(".grilltrack/")
                    self.assertEqual(saved.read_bytes(), original)
        for i in range(20):
            for name in ("ledger.json", "events.jsonl"):
                path = f"archive/historical-{i}/{name}"
                self.assertEqual((state / path).read_bytes(), before[path])
        joined = json.loads((state / "ledger.json").read_text())
        self.assertEqual(set(plan["decision_ids"]), {d["id"] for d in joined["decisions"]})
        self.assertTrue(all(d["status"] == "needs_reverification" for d in joined["decisions"]))
        self.assertTrue(all(d["review_ref"] is None for d in joined["decisions"]))
        self.assertIsNone(joined["current_focus"])
        self.assertEqual(self.cli("validate").returncode, 0)
        self.assertNotEqual(self.cli("close", "--confirmed-by", "user", "--reason", "fixture", "--summary", "fixture").returncode, 0)
        # The ordinary CLI still operates; repeat must not erase later progress.
        self.assertEqual(self.cli("focus", "--domain", "integration", "--cadence", "sequential").returncode, 0)
        progressed = self.state_bytes()
        again = self.reconcile("--apply", plan["plan_id"])
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertTrue(json.loads(again.stdout)["already_applied"])
        self.assertEqual(progressed, self.state_bytes())
        self.assertNotEqual(self.reconcile("--apply", "0" * 64).returncode, 0)
        self.assertEqual(progressed, self.state_bytes())

    def test_no_adjudication_plan_matches_legacy_cli(self):
        first = self.plan()
        second = self.plan()
        self.assertEqual(first, second)
        self.assertEqual(
            set(first),
            {
                "schema", "refs", "title", "snapshots", "plan_id",
                "joined_track_id", "decision_ids", "decision_provenance",
                "needs_reverification", "composed_verification",
                "composed_review", "snapshot_ref", "already_applied",
                "applied",
            },
        )
        self.assertEqual(first["schema"], "grilltrack/reconcile/v1")
        self.assertEqual(first["refs"], {
            "base": self.base, "current": self.current, "incoming": self.incoming,
        })
        self.assertEqual(first["title"], "Composed fixture")
        self.assertEqual(len(first["decision_ids"]), 16)
        self.assertEqual(first["decision_ids"], sorted(first["decision_ids"]))
        self.assertEqual(first["needs_reverification"], first["decision_ids"])
        self.assertFalse(first["composed_verification"])
        self.assertFalse(first["composed_review"])
        self.assertFalse(first["already_applied"])
        self.assertFalse(first["applied"])
        self.assertNotIn("adjudication", first)
        self.assertEqual(len(first["snapshots"]), 3)
        before = self.state_bytes()
        applied = self.reconcile("--apply", first["plan_id"])
        self.assertEqual(applied.returncode, 0, applied.stderr)
        output = json.loads(applied.stdout)
        self.assertTrue(output["applied"])
        joined = json.loads(
            (self.project / ".grilltrack/ledger.json").read_text()
        )
        self.assertEqual(joined["track_id"], first["joined_track_id"])
        self.assertEqual(
            {item["id"] for item in joined["decisions"]},
            set(first["decision_ids"]),
        )
        self.assertTrue(
            all(item["status"] == "needs_reverification"
                for item in joined["decisions"])
        )
        self.assertEqual(
            joined["reconciliation"]["plan_id"], first["plan_id"]
        )
        self.assertNotEqual(before, self.state_bytes())

    def test_invalid_digest_and_changed_target_refused(self):
        plan = self.plan()
        before = self.state_bytes()
        self.assertNotEqual(self.reconcile("--apply", "0" * 64).returncode, 0)
        self.assertEqual(before, self.state_bytes())
        self.cli("focus", "--domain", "different", "--cadence", "sequential")
        changed = self.state_bytes()
        self.assertNotEqual(self.reconcile("--apply", plan["plan_id"]).returncode, 0)
        self.assertEqual(changed, self.state_bytes())

    def test_failures_restore_canonical_and_interruption_is_guarded(self):
        plan = self.plan()
        before = self.state_bytes()
        for point in ("reconcile_before_publish", "reconcile_after_ledger", "reconcile_after_events"):
            result = self.reconcile("--apply", plan["plan_id"], failpoint=point)
            self.assertNotEqual(result.returncode, 0)
            after = self.state_bytes()
            for name in ("ledger.json", "events.jsonl"):
                self.assertEqual(before[name], after[name])
            self.assertEqual(self.cli("validate").returncode, 0)
        crash = self.reconcile("--apply", plan["plan_id"], failpoint="reconcile_crash_after_ledger")
        self.assertEqual(crash.returncode, 86)
        self.assertNotEqual(self.cli("show").returncode, 0)
        self.assertNotEqual(self.cli("new", "--title", "Bypass recovery").returncode, 0)
        self.assertNotEqual(self.cli("pause", "--reason", "unsafe", "--next-safe-action", "wait").returncode, 0)
        repaired = self.reconcile("--apply", plan["plan_id"])
        self.assertEqual(repaired.returncode, 0, repaired.stderr)
        self.assertEqual(self.cli("validate").returncode, 0)

    def test_contradictory_locks_and_malformed_events_refused(self):
        state = self.project / ".grilltrack"
        old_current = self.current
        data = json.loads((state / "archive/base-track/ledger.json").read_text())
        data["decisions"][0]["choice"] = "contradictory"
        (state / "archive/base-track/ledger.json").write_text(json.dumps(data))
        self.current = self.commit("conflict")
        before = self.state_bytes()
        result = self.reconcile()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("conflicting decision", result.stderr)
        self.assertEqual(before, self.state_bytes())
        self.git("restore", "--source", old_current, "--", ".grilltrack")
        (state / "events.jsonl").write_text('{"bad":"event"}\n')
        self.current = self.commit("malformed")
        before = self.state_bytes()
        self.assertNotEqual(self.reconcile().returncode, 0)
        self.assertEqual(before, self.state_bytes())

    def test_explicit_adjudication_selects_incoming_and_preserves_lineage(self):
        state = self.project / ".grilltrack"
        before_events = (state / "events.jsonl").read_bytes()
        before_archives = {
            path.relative_to(state): path.read_bytes()
            for path in (state / "archive").rglob("*")
            if path.is_file()
        }
        data = json.loads((state / "ledger.json").read_text())
        older = copy.deepcopy(self.shared[0])
        older["status"] = "locked"
        older["history"] = [{
            "at": NOW, "from": "proposed", "to": "locked",
            "note": "older lifecycle", "choice": older["choice"],
        }]
        older["implementation_ref"] = "fixture:older-implementation"
        older["verification_ref"] = None
        older["review_ref"] = None
        older["review_source_identity"] = None
        older["review_result"] = None
        older["review_classifications"] = []
        data["decisions"].append(older)
        (state / "ledger.json").write_text(json.dumps(data))
        self.current = self.commit("same choice, older current lifecycle")
        decision_id = self.shared[0]["id"]
        adjudication = self.write_adjudication({
            decision_id: {
                "role": "incoming",
                "reason": "Incoming is the completed record with the newer lifecycle.",
            }
        })
        result = self.reconcile("--adjudication-file", str(adjudication))
        self.assertEqual(result.returncode, 0, result.stderr)
        plan = json.loads(result.stdout)
        self.assertEqual(plan["adjudication"]["decisions"][decision_id]["role"], "incoming")
        self.assertEqual(
            plan["adjudicated_decisions"][decision_id]["reason"],
            "Incoming is the completed record with the newer lifecycle.",
        )
        self.assertEqual(self.plan_with_adjudication(adjudication), plan)
        self.assertEqual(before_events, (state / "events.jsonl").read_bytes())
        self.assertEqual(self.reconcile("--apply", plan["plan_id"], "--adjudication-file", str(adjudication)).returncode, 0)
        joined = json.loads((state / "ledger.json").read_text())
        decisions = {item["id"]: item for item in joined["decisions"]}
        self.assertEqual(decisions[decision_id]["choice"], self.shared[0]["choice"])
        self.assertEqual(decisions[decision_id]["status"], "needs_reverification")
        incoming = json.loads(
            subprocess.check_output(
                ["git", "-C", str(self.project), "show",
                 f"{self.incoming}:.grilltrack/ledger.json"]
            )
        )["decisions"][0]
        self.assertEqual(
            decisions[decision_id]["history"],
            incoming["history"] + [{
                "at": NOW, "from": "verified", "to": "needs_reverification",
                "note": "fork composition invalidates prior current proof",
                "source_snapshot_ref": plan["snapshot_ref"],
            }],
        )
        self.assertEqual(
            decisions[decision_id]["implementation_ref"],
            incoming["implementation_ref"],
        )
        self.assertIsNone(decisions[decision_id]["verification_ref"])
        self.assertIsNone(decisions[decision_id]["review_ref"])
        self.assertIsNone(decisions[decision_id]["review_source_identity"])
        self.assertIsNone(decisions[decision_id]["review_result"])
        self.assertEqual(decisions[decision_id]["review_classifications"], [])
        self.assertTrue(
            all(item["status"] == "needs_reverification" for item in decisions.values())
        )
        self.assertEqual(
            set(plan["decision_ids"]),
            {item["id"] for item in decisions.values()},
        )
        self.assertTrue(
            (state / "lineage" / plan["plan_id"] / "snapshots" / "current" / "archive/base-track/ledger.json").is_file()
        )
        lineage = state / "lineage" / plan["plan_id"] / "snapshots"
        self.assertEqual(
            (lineage / "current/events.jsonl").read_bytes(),
            before_events,
        )
        self.assertEqual(
            (lineage / "current/ledger.json").read_bytes(),
            subprocess.check_output(
                ["git", "-C", str(self.project), "show",
                 f"{self.current}:.grilltrack/ledger.json"]
            ),
        )
        for path, content in before_archives.items():
            retained = state / path
            if not str(path).startswith("archive/base-track/"):
                self.assertEqual(retained.read_bytes(), content)
        self.assertEqual(self.cli("validate").returncode, 0)

    def test_adjudication_validation_is_fail_closed(self):
        state = self.project / ".grilltrack"
        data = json.loads((state / "archive/base-track/ledger.json").read_text())
        data["decisions"][0]["choice"] = "conflicting-choice"
        (state / "archive/base-track/ledger.json").write_text(json.dumps(data))
        self.current = self.commit("conflicting current")
        decision_id = self.shared[0]["id"]
        cases = [
            ({}, "missing"),
            ({decision_id: {"role": "base", "reason": " "}}, "blank"),
            ({"unknown": {"role": "incoming", "reason": "not bound"}}, "unknown"),
            ({decision_id: {"role": "archive", "reason": "bad role"}}, "role"),
        ]
        for decisions, _label in cases:
            with self.subTest(_label):
                path = self.write_adjudication(decisions)
                self.assertNotEqual(
                    self.reconcile("--adjudication-file", str(path)).returncode,
                    0,
                )
        path = self.root / "duplicate.json"
        path.write_text(
            json.dumps({
                "schema": "grilltrack/adjudication/v1",
                "refs": {"base": self.base, "current": self.current, "incoming": self.incoming},
                "decisions": {decision_id: {"role": "incoming", "reason": "one"}},
            }).replace('"reason": "one"', '"reason": "one", "role": "incoming"'),
            encoding="utf-8",
        )
        self.assertNotEqual(self.reconcile("--adjudication-file", str(path)).returncode, 0)

    def test_adjudication_rejects_schema_types_and_ref_binding(self):
        state = self.project / ".grilltrack"
        data = json.loads((state / "archive/base-track/ledger.json").read_text())
        data["decisions"][0]["choice"] = "conflicting-choice"
        (state / "archive/base-track/ledger.json").write_text(json.dumps(data))
        self.current = self.commit("adjudication contract failures")
        decision_id = self.shared[0]["id"]
        valid = {
            "schema": "grilltrack/adjudication/v1",
            "refs": {"base": self.base, "current": self.current, "incoming": self.incoming},
            "decisions": {decision_id: {"role": "incoming", "reason": "select"}},
        }
        cases = [
            ({**valid, "schema": "wrong"}, "schema"),
            ({**valid, "unexpected": True}, "unknown top-level"),
            ({**valid, "refs": {**valid["refs"], "extra": self.base}}, "extra ref"),
            ({**valid, "decisions": {decision_id: {"role": 1, "reason": "select"}}}, "role type"),
            ({**valid, "decisions": {decision_id: {"role": "incoming", "reason": 1}}}, "reason type"),
            ({**valid, "refs": {**valid["refs"], "incoming": self.base}}, "ref binding"),
        ]
        for payload, label in cases:
            with self.subTest(label):
                path = self.root / f"invalid-{label.replace(' ', '-')}.json"
                path.write_text(json.dumps(payload), encoding="utf-8")
                self.assertNotEqual(
                    self.reconcile("--adjudication-file", str(path)).returncode,
                    0,
                )

    def test_adjudication_rejects_extra_missing_and_role_ambiguity(self):
        state = self.project / ".grilltrack"
        data = json.loads((state / "archive/base-track/ledger.json").read_text())
        data["decisions"][0]["choice"] = "conflicting-choice"
        (state / "archive/base-track/ledger.json").write_text(json.dumps(data))
        self.current = self.commit("adjudication selector failures")
        decision_id = self.shared[0]["id"]
        other_id = self.shared[1]["id"]
        fork_only = decision("fork-only")
        fork_only["choice"] = "incoming-fork-choice"
        self.git("checkout", "--detach", self.incoming)
        incoming_live = json.loads((state / "ledger.json").read_text())
        incoming_live["decisions"].append(copy.deepcopy(fork_only))
        (state / "ledger.json").write_text(json.dumps(incoming_live))
        self.incoming = self.commit("incoming-only conflict")
        self.git("checkout", "--detach", self.current)
        current_live = json.loads((state / "ledger.json").read_text())
        current_live["decisions"].append(copy.deepcopy(self.shared[0]))
        current_fork = copy.deepcopy(fork_only)
        current_fork["choice"] = "current-fork-choice"
        current_live["decisions"].append(current_fork)
        (state / "ledger.json").write_text(json.dumps(current_live))
        self.current = self.commit("current-only conflict")
        cases = [
            ({other_id: {"role": "incoming", "reason": "nonconflict"}}, "nonconflict"),
            ({}, "missing"),
            ({"bad": {"role": "incoming", "reason": "unknown"}}, "unknown"),
            ({
                decision_id: {"role": "incoming", "reason": "shared"},
                "fork-only": {"role": "base", "reason": "absent"},
            }, "absent"),
        ]
        for selections, label in cases:
            with self.subTest(label):
                path = self.write_adjudication(selections)
                self.assertNotEqual(
                    self.reconcile("--adjudication-file", str(path)).returncode,
                    0,
                )
        path = self.write_adjudication({
            decision_id: {"role": "current", "reason": "ambiguous"},
            "fork-only": {"role": "incoming", "reason": "fork"},
        })
        self.assertNotEqual(
            self.reconcile("--adjudication-file", str(path)).returncode,
            0,
        )

    def test_adjudication_selection_reason_and_refs_bind_plan_digest(self):
        state = self.project / ".grilltrack"
        data = json.loads((state / "archive/base-track/ledger.json").read_text())
        data["decisions"][0]["choice"] = "conflicting-choice"
        (state / "archive/base-track/ledger.json").write_text(json.dumps(data))
        self.current = self.commit("conflicting current")
        decision_id = self.shared[0]["id"]
        path = self.write_adjudication({
            decision_id: {"role": "incoming", "reason": "newer completed lifecycle"}
        })
        first = json.loads(self.reconcile("--adjudication-file", str(path)).stdout)
        changed = json.loads(path.read_text())
        changed["decisions"][decision_id]["reason"] = "different human reason"
        path.write_text(json.dumps(changed), encoding="utf-8")
        second = json.loads(self.reconcile("--adjudication-file", str(path)).stdout)
        self.assertNotEqual(first["plan_id"], second["plan_id"])
        changed["refs"]["incoming"] = self.base
        path.write_text(json.dumps(changed), encoding="utf-8")
        self.assertNotEqual(self.reconcile("--adjudication-file", str(path)).returncode, 0)

    def test_adjudication_changed_role_or_reason_rejects_prior_apply_digest(self):
        state = self.project / ".grilltrack"
        data = json.loads((state / "archive/base-track/ledger.json").read_text())
        data["decisions"][0]["choice"] = "conflicting-choice"
        (state / "archive/base-track/ledger.json").write_text(json.dumps(data))
        self.current = self.commit("adjudication digest binding")
        decision_id = self.shared[0]["id"]
        path = self.write_adjudication({
            decision_id: {"role": "incoming", "reason": "approved selection"}
        })
        plan = self.plan_with_adjudication(path)
        self.assertEqual(
            self.reconcile("--apply", plan["plan_id"],
                           "--adjudication-file", str(path)).returncode,
            0,
        )
        changed = json.loads(path.read_text())
        changed["decisions"][decision_id]["role"] = "base"
        path.write_text(json.dumps(changed), encoding="utf-8")
        self.assertNotEqual(
            self.reconcile("--apply", plan["plan_id"],
                           "--adjudication-file", str(path)).returncode,
            0,
        )
        changed["decisions"][decision_id]["role"] = "incoming"
        changed["decisions"][decision_id]["reason"] = "different reason"
        path.write_text(json.dumps(changed), encoding="utf-8")
        self.assertNotEqual(
            self.reconcile("--apply", plan["plan_id"],
                           "--adjudication-file", str(path)).returncode,
            0,
        )

    def test_adjudication_interruption_retries_after_progress(self):
        state = self.project / ".grilltrack"
        data = json.loads((state / "archive/base-track/ledger.json").read_text())
        data["decisions"][0]["choice"] = "conflicting-choice"
        (state / "archive/base-track/ledger.json").write_text(json.dumps(data))
        self.current = self.commit("adjudication interruption")
        decision_id = self.shared[0]["id"]
        path = self.write_adjudication({
            decision_id: {"role": "incoming", "reason": "retry approved"}
        })
        plan = self.plan_with_adjudication(path)
        crashed = self.reconcile(
            "--apply", plan["plan_id"], "--adjudication-file", str(path),
            failpoint="reconcile_crash_after_ledger",
        )
        self.assertEqual(crashed.returncode, 86)
        self.assertNotEqual(self.cli("show").returncode, 0)
        retry = self.reconcile(
            "--apply", plan["plan_id"], "--adjudication-file", str(path)
        )
        self.assertEqual(retry.returncode, 0, retry.stderr)
        self.assertEqual(self.cli("focus", "--domain", "retry-progress",
                                  "--cadence", "sequential").returncode, 0)
        repeated = self.reconcile(
            "--apply", plan["plan_id"], "--adjudication-file", str(path)
        )
        self.assertEqual(repeated.returncode, 0, repeated.stderr)
        self.assertTrue(json.loads(repeated.stdout)["already_applied"])
        self.assertEqual(self.cli("validate").returncode, 0)

    def test_adjudication_rejects_composed_dependency_cycle_during_planning(self):
        state = self.project / ".grilltrack"
        self.git("checkout", "--detach", self.incoming)
        incoming_ledger = json.loads((state / "ledger.json").read_text())
        incoming_ledger["decisions"][0]["dependencies"] = ["shared-1"]
        (state / "ledger.json").write_text(json.dumps(incoming_ledger, indent=2) + "\n")
        self.incoming = self.commit("incoming dependency choice")
        self.assertEqual(self.cli("validate").returncode, 0)

        self.git("checkout", "--detach", self.current)
        current_ledger = json.loads(
            (state / "archive/base-track/ledger.json").read_text()
        )
        current_ledger["decisions"][1]["dependencies"] = ["shared-0"]
        (state / "archive/base-track/ledger.json").write_text(
            json.dumps(current_ledger, indent=2) + "\n"
        )
        self.current = self.commit("current dependency choice")
        self.assertEqual(self.cli("validate").returncode, 0)

        adjudication = self.write_adjudication(
            {
                "shared-0": {
                    "role": "incoming",
                    "reason": "retain incoming dependency",
                },
                "shared-1": {
                    "role": "current",
                    "reason": "retain current dependency",
                },
            }
        )
        before = self.state_bytes()
        result = self.reconcile("--adjudication-file", str(adjudication))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("dependency cycle includes", result.stderr)
        self.assertEqual(before, self.state_bytes())

    def test_adjudication_accepts_valid_mixed_role_projection(self):
        state = self.project / ".grilltrack"
        self.git("checkout", "--detach", self.incoming)
        incoming_ledger = json.loads((state / "ledger.json").read_text())
        incoming_ledger["decisions"][0]["choice"] = "incoming-choice"
        (state / "ledger.json").write_text(json.dumps(incoming_ledger, indent=2) + "\n")
        self.incoming = self.commit("incoming mixed-role choice")

        self.git("checkout", "--detach", self.current)
        current_ledger = json.loads(
            (state / "archive/base-track/ledger.json").read_text()
        )
        current_ledger["decisions"][1]["choice"] = "current-choice"
        (state / "archive/base-track/ledger.json").write_text(
            json.dumps(current_ledger, indent=2) + "\n"
        )
        self.current = self.commit("current mixed-role choice")

        adjudication = self.write_adjudication(
            {
                "shared-0": {
                    "role": "incoming",
                    "reason": "retain incoming choice",
                },
                "shared-1": {
                    "role": "current",
                    "reason": "retain current choice",
                },
            }
        )
        plan = self.plan_with_adjudication(adjudication)
        applied = self.reconcile(
            "--adjudication-file",
            str(adjudication),
            "--apply",
            plan["plan_id"],
        )
        self.assertEqual(applied.returncode, 0, applied.stderr)
        joined = json.loads((state / "ledger.json").read_text())
        choices = {item["id"]: item["choice"] for item in joined["decisions"]}
        self.assertEqual(choices["shared-0"], "incoming-choice")
        self.assertEqual(choices["shared-1"], "current-choice")
        self.assertTrue(
            (
                state
                / "lineage"
                / plan["plan_id"]
                / "snapshots/incoming/ledger.json"
            ).is_file()
        )
        self.assertTrue(
            (
                state
                / "lineage"
                / plan["plan_id"]
                / "snapshots/current/archive/base-track/ledger.json"
            ).is_file()
        )
        self.assertEqual(self.cli("validate").returncode, 0)

    def test_common_prefix_and_archive_incompatibility_refused(self):
        state = self.project / ".grilltrack"
        (state / "archive/base-track/events.jsonl").write_bytes(events(1000, 36))
        self.current = self.commit("wrong prefix")
        before = self.state_bytes()
        result = self.reconcile()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("common event prefix", result.stderr)
        self.assertEqual(before, self.state_bytes())

    def test_changed_archive_and_unrelated_base_refused(self):
        state = self.project / ".grilltrack"
        (state / "archive/historical-0/events.jsonl").write_bytes(events(2000, 1))
        self.current = self.commit("changed archive")
        before = self.state_bytes()
        result = self.reconcile()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("common historical archive", result.stderr)
        self.assertEqual(before, self.state_bytes())
        self.base = self.incoming
        result = self.reconcile()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("incompatible", result.stderr)
        self.assertEqual(before, self.state_bytes())

    def test_symlink_receipt_and_missing_retained_snapshot_refused(self):
        plan = self.plan()
        self.assertEqual(self.reconcile("--apply", plan["plan_id"]).returncode, 0)
        lineage = self.project / ".grilltrack/lineage" / plan["plan_id"]
        receipt = lineage / "applied.json"
        saved = receipt.read_bytes()
        receipt.unlink()
        outside = self.root / "outside.json"
        outside.write_bytes(saved)
        receipt.symlink_to(outside)
        self.assertNotEqual(self.reconcile("--apply", plan["plan_id"]).returncode, 0)
        self.assertEqual(outside.read_bytes(), saved)
        receipt.unlink()
        receipt.write_bytes(saved)
        (lineage / "snapshots/base/events.jsonl").unlink()
        self.assertNotEqual(self.reconcile("--apply", plan["plan_id"]).returncode, 0)

    def test_immutable_publication_interruption_recovers_exactly(self):
        for kind in ("snapshot", "receipt"):
            for boundary in ("before", "after"):
                with self.subTest(kind=kind, boundary=boundary):
                    case = ReconcileTests()
                    case.setUp()
                    try:
                        plan = case.plan()
                        before = case.state_bytes()
                        script = '''
import os, runpy, sys
from pathlib import Path
kind, boundary, cli = sys.argv[1:4]
def selected(path):
    return Path(path).name == 'applied.json' if kind == 'receipt' else '/snapshots/' in str(path)
original_open, original_link = Path.open, os.link
def interrupted_open(self, mode='r', *args, **kwargs):
    stream = original_open(self, mode, *args, **kwargs)
    if mode == 'xb' and selected(self):
        os._exit(86)  # Original bug: incomplete final path already visible.
    return stream
def interrupted_link(source, target, *args, **kwargs):
    if selected(target) and boundary == 'before':
        os._exit(86)
    result = original_link(source, target, *args, **kwargs)
    if selected(target) and boundary == 'after':
        os._exit(86)
    return result
Path.open, os.link = interrupted_open, interrupted_link
sys.argv = [cli] + sys.argv[4:]
sys.path.insert(0, str(Path(cli).parent))
runpy.run_path(cli, run_name='__main__')
'''
                        args = ["--project", str(case.project), "reconcile", "--base-ref", case.base,
                                "--current-ref", case.current, "--incoming-ref", case.incoming,
                                "--title", "Composed fixture", "--apply", plan["plan_id"]]
                        crash = subprocess.run([sys.executable, "-c", script, kind, boundary, str(CLI), *args], capture_output=True, text=True)
                        self.assertEqual(crash.returncode, 86, crash.stderr)
                        state = case.project / ".grilltrack"
                        lineage = state / "lineage" / plan["plan_id"]
                        # Only complete final artifacts can become visible.
                        for role, files in plan["snapshots"].items():
                            for name, expected in files.items():
                                path = lineage / "snapshots" / role / name
                                if path.exists():
                                    self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), expected)
                        if kind == "receipt":
                            self.assertTrue((state / "work/reconcile-transaction.json").exists())
                            self.assertNotEqual(case.cli("show").returncode, 0)
                            self.assertNotEqual(case.cli("pause", "--reason", "mixed", "--next-safe-action", "retry").returncode, 0)
                        else:
                            for name in ("ledger.json", "events.jsonl"):
                                self.assertEqual((state / name).read_bytes(), before[name])
                        retried = case.reconcile("--apply", plan["plan_id"])
                        self.assertEqual(retried.returncode, 0, retried.stderr)
                        self.assertEqual(case.cli("validate").returncode, 0)
                        self.assertFalse((state / "work/reconcile-transaction.json").exists())
                        for role, files in plan["snapshots"].items():
                            for name, expected in files.items():
                                path = lineage / "snapshots" / role / name
                                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), expected)
                        completed = case.state_bytes()
                        self.assertEqual(case.reconcile("--apply", plan["plan_id"]).returncode, 0)
                        self.assertEqual(case.state_bytes(), completed)
                    finally:
                        case.tearDown()

    def test_foreign_immutable_artifact_is_never_replaced(self):
        plan = self.plan()
        before = self.state_bytes()
        foreign = self.project / ".grilltrack/lineage" / plan["plan_id"] / "snapshots/base/ledger.json"
        foreign.parent.mkdir(parents=True)
        foreign.write_bytes(b"foreign retained history")
        result = self.reconcile("--apply", plan["plan_id"])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("immutable reconciliation artifact differs", result.stderr)
        self.assertEqual(foreign.read_bytes(), b"foreign retained history")
        for name in ("ledger.json", "events.jsonl"):
            self.assertEqual((self.project / ".grilltrack" / name).read_bytes(), before[name])


class IndependentHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.project = Path(self.temp.name).resolve() / "repo"
        self.project.mkdir()
        self.git("init", "-q")
        self.git("config", "user.name", "Fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        (self.project / "README").write_text("shared Git root\n")
        self.base = self.commit("shared root without GrillTrack state")

        self.git("checkout", "-qb", "current", self.base)
        state = self.project / ".grilltrack"
        state.mkdir()
        self.write_state(state, ledger("current-track", [decision("current-only")]), events(0, 2))
        self.write_state(
            state / "archive" / "current-history",
            ledger("current-history", [], "closed"),
            events(100, 1),
        )
        self.current = self.commit("independent current history")

        self.git("checkout", "-qb", "incoming", self.base)
        state = self.project / ".grilltrack"
        state.mkdir()
        self.write_state(state, ledger("incoming-track", [decision("incoming-only")]), events(10, 2))
        self.write_state(
            state / "archive" / "incoming-history",
            ledger("incoming-history", [], "closed"),
            events(110, 1),
        )
        self.incoming = self.commit("independent incoming history")
        self.git("checkout", "--detach", self.current)

    def tearDown(self):
        self.temp.cleanup()

    def git(self, *args):
        return subprocess.check_output(
            ["git", "-C", str(self.project), *args], stderr=subprocess.PIPE
        ).decode().strip()

    def commit(self, message):
        self.git("add", ".")
        self.git("commit", "-qm", message)
        return self.git("rev-parse", "HEAD")

    def write_state(self, directory, data, log):
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "ledger.json").write_text(json.dumps(data, indent=2) + "\n")
        (directory / "events.jsonl").write_bytes(log)

    def cli(self, *args):
        return subprocess.run(
            [sys.executable, str(CLI), "--project", str(self.project), *args],
            capture_output=True,
            text=True,
        )

    def reconcile(self, *extra, failpoint=None, base=None, current=None, incoming=None, title="Independent histories"):
        env = os.environ.copy()
        env.pop("GRILLTRACK_TEST_FAILPOINT", None)
        if failpoint:
            env["GRILLTRACK_TEST_FAILPOINT"] = failpoint
        return subprocess.run(
            [sys.executable, str(CLI), "--project", str(self.project), "reconcile",
            "--base-ref",
            base or self.base,
            "--current-ref",
            current or self.current,
            "--incoming-ref",
            incoming or self.incoming,
            "--title",
            title,
            *extra],
            capture_output=True,
            text=True,
            env=env,
        )

    def test_no_ledger_base_unions_and_retains_independent_histories(self):
        before = {
            str(path.relative_to(self.project)): path.read_bytes()
            for path in self.project.rglob("*")
            if path.is_file() and ".git" not in path.parts
        }
        plan_result = self.reconcile()
        self.assertEqual(plan_result.returncode, 0, plan_result.stderr)
        plan = json.loads(plan_result.stdout)
        self.assertEqual(
            before,
            {
                str(path.relative_to(self.project)): path.read_bytes()
                for path in self.project.rglob("*")
                if path.is_file() and ".git" not in path.parts
            },
        )
        self.assertEqual(plan["base_provenance"], "no-ledger-base")
        self.assertEqual(plan["decision_ids"], ["current-only", "incoming-only"])
        self.assertEqual(
            plan["plan_id"],
            hashlib.sha256(
                (json.dumps(
                    {key: plan[key] for key in ("schema", "refs", "title", "base_provenance", "snapshots")},
                    indent=2,
                    sort_keys=True,
                ) + "\n").encode()
            ).hexdigest(),
        )
        self.assertEqual(
            {item["role"] for values in plan["decision_provenance"].values() for item in values},
            {"current", "incoming"},
        )

        applied = self.reconcile("--apply", plan["plan_id"])
        self.assertEqual(applied.returncode, 0, applied.stderr)
        lineage = self.project / ".grilltrack" / "lineage" / plan["plan_id"]
        for role, ref in (("current", self.current), ("incoming", self.incoming)):
            for name in ("ledger.json", "events.jsonl"):
                expected = subprocess.check_output(
                    ["git", "-C", str(self.project), "show", f"{ref}:.grilltrack/{name}"]
                )
                self.assertEqual(
                    (lineage / "snapshots" / role / name).read_bytes(), expected
                )
        for role, archive_name in (
            ("current", "current-history"),
            ("incoming", "incoming-history"),
        ):
            for name in ("ledger.json", "events.jsonl"):
                expected = subprocess.check_output(
                    [
                        "git",
                        "-C",
                        str(self.project),
                        "show",
                        f"{getattr(self, role)}:.grilltrack/archive/{archive_name}/{name}",
                    ]
                )
                self.assertEqual(
                    (lineage / "snapshots" / role / f"archive/{archive_name}/{name}").read_bytes(),
                    expected,
                )
        joined = json.loads((self.project / ".grilltrack" / "ledger.json").read_text())
        self.assertEqual(
            {item["id"] for item in joined["decisions"]},
            {"current-only", "incoming-only"},
        )
        self.assertTrue(all(d["status"] == "needs_reverification" for d in joined["decisions"]))
        self.assertTrue(all(d["review_ref"] is None for d in joined["decisions"]))
        self.assertEqual(self.cli("validate").returncode, 0)

    def test_independent_title_binding_and_no_dry_run_mutation(self):
        first = json.loads(self.reconcile().stdout)
        second = json.loads(self.reconcile().stdout)
        self.assertEqual(first, second)
        renamed = self.reconcile(title="Different independent title")
        self.assertEqual(renamed.returncode, 0, renamed.stderr)
        self.assertNotEqual(json.loads(renamed.stdout)["plan_id"], first["plan_id"])

    def test_independent_interruption_recovery_and_idempotent_progress(self):
        plan = json.loads(self.reconcile().stdout)
        crashed = self.reconcile("--apply", plan["plan_id"], failpoint="reconcile_crash_after_ledger")
        self.assertEqual(crashed.returncode, 86)
        self.assertNotEqual(self.cli("show").returncode, 0)
        repaired = self.reconcile("--apply", plan["plan_id"])
        self.assertEqual(repaired.returncode, 0, repaired.stderr)
        self.assertEqual(self.cli("focus", "--domain", "post-compose", "--cadence", "sequential").returncode, 0)
        progressed = {
            str(path.relative_to(self.project / ".grilltrack")): path.read_bytes()
            for path in (self.project / ".grilltrack").rglob("*")
            if path.is_file()
        }
        repeated = self.reconcile("--apply", plan["plan_id"])
        self.assertEqual(repeated.returncode, 0, repeated.stderr)
        self.assertTrue(json.loads(repeated.stdout)["already_applied"])
        self.assertEqual(
            progressed,
            {
                str(path.relative_to(self.project / ".grilltrack")): path.read_bytes()
                for path in (self.project / ".grilltrack").rglob("*")
                if path.is_file()
            },
        )

    def test_independent_conflicting_decision_id_requires_adjudication(self):
        self.git("checkout", "--detach", self.base)
        state = self.project / ".grilltrack"
        state.mkdir()
        conflicting = decision("current-only")
        conflicting["choice"] = "different-independent-choice"
        self.write_state(
            state, ledger("incoming-track", [conflicting]), events(20, 2)
        )
        self.incoming = self.commit("conflicting independent history")
        self.git("checkout", "--detach", self.current)

        result = self.reconcile()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("conflicting decision current-only", result.stderr)

    def test_independent_live_vs_archived_conflict_requires_adjudication(self):
        self.git("checkout", "--detach", self.incoming)
        archived = decision("current-only")
        archived["choice"] = "different-archived-choice"
        self.write_state(
            self.project / ".grilltrack/archive/incoming-history",
            ledger("incoming-history", [archived], "closed"),
            events(110, 1),
        )
        self.incoming = self.commit("archived conflict with current live decision")
        self.git("checkout", "--detach", self.current)

        result = self.reconcile()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("conflicting decision current-only", result.stderr)

    def test_independent_archived_vs_archived_conflict_requires_adjudication(self):
        for role, source, other_choice in (
            ("current", self.current, "current-archived-choice"),
            ("incoming", self.incoming, "incoming-archived-choice"),
        ):
            self.git("checkout", "--detach", source)
            archived = decision("archived-only")
            archived["choice"] = other_choice
            self.write_state(
                self.project / f".grilltrack/archive/{role}-history",
                ledger(f"{role}-history", [archived], "closed"),
                events(120 if role == "current" else 130, 1),
            )
            new_ref = self.commit(f"{role} archived conflict history")
            setattr(self, role, new_ref)
        self.git("checkout", "--detach", self.current)

        result = self.reconcile()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("conflicting decision archived-only", result.stderr)

    def test_independent_nonconflicting_archived_decisions_stay_historical(self):
        for role, source, key in (
            ("current", self.current, "current-archived-only"),
            ("incoming", self.incoming, "incoming-archived-only"),
        ):
            self.git("checkout", "--detach", source)
            archived = decision(key)
            self.write_state(
                self.project / f".grilltrack/archive/{role}-history",
                ledger(f"{role}-history", [archived], "closed"),
                events(140 if role == "current" else 150, 1),
            )
            new_ref = self.commit(f"{role} nonconflicting archive history")
            setattr(self, role, new_ref)
        self.git("checkout", "--detach", self.current)

        plan_result = self.reconcile()
        self.assertEqual(plan_result.returncode, 0, plan_result.stderr)
        plan = json.loads(plan_result.stdout)
        self.assertNotIn("current-archived-only", plan["decision_ids"])
        self.assertNotIn("incoming-archived-only", plan["decision_ids"])
        applied = self.reconcile("--apply", plan["plan_id"])
        self.assertEqual(applied.returncode, 0, applied.stderr)
        joined = json.loads((self.project / ".grilltrack/ledger.json").read_text())
        self.assertNotIn(
            "current-archived-only",
            {item["id"] for item in joined["decisions"]},
        )
        self.assertNotIn(
            "incoming-archived-only",
            {item["id"] for item in joined["decisions"]},
        )
        lineage = self.project / ".grilltrack/lineage" / plan["plan_id"]
        for role, key in (
            ("current", "current-archived-only"),
            ("incoming", "incoming-archived-only"),
        ):
            archived = json.loads(
                (
                    lineage
                    / f"snapshots/{role}/archive/{role}-history/ledger.json"
                ).read_text()
            )
            self.assertEqual(archived["decisions"][0]["id"], key)

    def test_independent_identical_archived_decision_bodies_are_accepted(self):
        for role, source in (("current", self.current), ("incoming", self.incoming)):
            self.git("checkout", "--detach", source)
            archived = decision("shared-archived")
            self.write_state(
                self.project / f".grilltrack/archive/{role}-history",
                ledger(f"{role}-history", [archived], "closed"),
                events(160 if role == "current" else 170, 1),
            )
            new_ref = self.commit(f"{role} identical archive history")
            setattr(self, role, new_ref)
        self.git("checkout", "--detach", self.current)

        result = self.reconcile()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_independent_one_sided_canonical_pair_fails_closed(self):
        self.git("checkout", "--detach", self.current)
        (self.project / ".grilltrack" / "events.jsonl").unlink()
        self.current = self.commit("one-sided current history")
        result = self.reconcile()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("snapshot requires ledger and events", result.stderr)

    def test_independent_incomplete_current_and_archive_streams_fail_closed(self):
        cases = []
        for role in ("current", "incoming"):
            cases.extend(
                [
                    (role, "events.jsonl", b""),
                    (role, "events.jsonl", events(0, 1)[:-1]),
                    (role, f"archive/{role}-history/events.jsonl", b""),
                    (role, f"archive/{role}-history/events.jsonl", events(0, 1)[:-1]),
                ]
            )
        for role, relative, content in cases:
            with self.subTest(role=role, relative=relative, content=content):
                try:
                    source = getattr(self, role)
                    self.git("checkout", "--detach", source)
                    path = self.project / ".grilltrack" / relative
                    path.write_bytes(content)
                    malformed = self.commit(f"incomplete {role} {relative}")
                    refs = {role: malformed}
                    result = self.reconcile(**refs)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("event stream must be nonempty and newline terminated", result.stderr)
                finally:
                    self.git("checkout", "--detach", self.current)

    def test_independent_malformed_incoming_and_unrelated_history_fail_closed(self):
        self.git("checkout", "--detach", self.base)
        state = self.project / ".grilltrack"
        state.mkdir()
        (state / "ledger.json").write_text("{malformed\n")
        (state / "events.jsonl").write_bytes(events(20, 1))
        malformed = self.commit("malformed incoming history")
        self.git("checkout", "--detach", self.current)
        result = self.reconcile(incoming=malformed)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Expecting", result.stderr)

        self.git("checkout", "--detach", self.incoming)
        (self.project / ".grilltrack" / "ledger.json").unlink()
        one_sided_incoming = self.commit("one-sided incoming history")
        self.git("checkout", "--detach", self.current)
        result = self.reconcile(incoming=one_sided_incoming)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("snapshot requires ledger and events", result.stderr)

        self.git("checkout", "--detach", self.base)
        state = self.project / ".grilltrack"
        state.mkdir()
        (state / "ledger.json").write_text(
            json.dumps(ledger("bad-base", []), indent=2) + "\n"
        )
        one_sided_base = self.commit("one-sided base history")
        self.git("checkout", "--detach", one_sided_base)
        self.write_state(
            state,
            ledger("base-current", [decision("base-current-only")]),
            events(30, 1),
        )
        current_from_one_sided_base = self.commit("current from one-sided base")
        self.git("checkout", "--detach", one_sided_base)
        self.write_state(
            state,
            ledger("base-incoming", [decision("base-incoming-only")]),
            events(40, 1),
        )
        incoming_from_one_sided_base = self.commit("incoming from one-sided base")
        self.git("checkout", "--detach", self.current)
        result = self.reconcile(
            base=one_sided_base,
            current=current_from_one_sided_base,
            incoming=incoming_from_one_sided_base,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("base canonical state must contain ledger and events together", result.stderr)

        self.git("checkout", "--orphan", "unrelated")
        self.git("rm", "-rf", ".")
        (self.project / "README").write_text("unrelated root\n")
        unrelated = self.commit("unrelated root")
        self.git("checkout", "--detach", self.current)
        result = self.reconcile(base=unrelated)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("incompatible", result.stderr)


if __name__ == "__main__":
    unittest.main()
