from __future__ import annotations

import json
import hashlib
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

CLI = Path(__file__).resolve().parents[1] / "skills/grilltrack/scripts/grilltrack_ledger.py"
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

    def test_exact_fork_preservation_and_honest_projection(self):
        before = self.state_bytes()
        plan = self.plan()
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


if __name__ == "__main__":
    unittest.main()
