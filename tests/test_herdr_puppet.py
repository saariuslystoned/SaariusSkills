from __future__ import annotations

import copy
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "skills" / "herdr-puppet" / "scripts"
sys.path.insert(0, str(LIB))

from herdr_puppet_lib.core import (  # noqa: E402
    create_qualification_tab,
    doctor,
    plan,
    preserve_lease,
    qualification_beacon_wait,
    qualification_reconcile_send,
    qualification_send,
    qualification_token_probe,
    structural_status,
)
from herdr_puppet_lib.errors import HerdrPuppetError  # noqa: E402
from herdr_puppet_lib.herdr_client import HerdrClient  # noqa: E402
from herdr_puppet_lib.journal import (  # noqa: E402
    initialize_journal,
    refresh_state,
    summarize_journal,
)


FIXTURES = ROOT / "fixtures" / "herdr-puppet"


def fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class FakeClient:
    def __init__(self) -> None:
        self.session = "operator-session"
        self.version = "herdr 0.7.3"
        self.server = {
            "status": "running",
            "running": True,
            "version": "0.7.3",
            "protocol": 16,
            "compatible": True,
            "socket": "/redacted/herdr.sock",
            "session": self.session,
        }
        self.session_rows = [{"name": self.session, "running": True}]
        self.workspace_rows = [{"workspace_id": "w2", "label": "worker-02"}]
        self.tab_rows: list[dict[str, Any]] = []
        self.pane_rows: list[dict[str, Any]] = []
        self.process_rows: dict[str, dict[str, Any]] = {}
        self.sent: list[tuple[str, str, str]] = []
        self.read_payload: Any = {"result": {"text": ""}}

    def version_text(self) -> str:
        return self.version

    def server_status(self, session: str) -> dict[str, Any]:
        self._session(session)
        return copy.deepcopy(self.server)

    def sessions(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self.session_rows)

    def workspaces(self, session: str) -> list[dict[str, Any]]:
        self._session(session)
        return copy.deepcopy(self.workspace_rows)

    def snapshot(self, session: str) -> dict[str, Any]:
        self._session(session)
        return {
            "version": "0.7.3",
            "protocol": 16,
            "workspaces": copy.deepcopy(self.workspace_rows),
            "tabs": copy.deepcopy(self.tab_rows),
            "panes": copy.deepcopy(self.pane_rows),
        }

    def tabs(
        self, session: str, workspace_id: str | None = None
    ) -> list[dict[str, Any]]:
        self._session(session)
        return [
            copy.deepcopy(item)
            for item in self.tab_rows
            if workspace_id is None or item["workspace_id"] == workspace_id
        ]

    def panes(
        self, session: str, workspace_id: str | None = None
    ) -> list[dict[str, Any]]:
        self._session(session)
        return [
            copy.deepcopy(item)
            for item in self.pane_rows
            if workspace_id is None or item["workspace_id"] == workspace_id
        ]

    def process_info(self, session: str, pane_id: str) -> dict[str, Any]:
        self._session(session)
        return copy.deepcopy(self.process_rows[pane_id])

    def create_tab(self, session: str, workspace_id: str, label: str) -> dict[str, Any]:
        self._session(session)
        tab_id = "w2:t1"
        pane_id = "w2:p1"
        self.tab_rows.append(
            {
                "workspace_id": workspace_id,
                "tab_id": tab_id,
                "label": label,
                "pane_count": 1,
            }
        )
        self.pane_rows.append(
            {
                "workspace_id": workspace_id,
                "tab_id": tab_id,
                "pane_id": pane_id,
                "terminal_id": "term_one",
            }
        )
        self.process_rows[pane_id] = {
            "pane_id": pane_id,
            "foreground_processes": [
                {
                    "pid": 4242,
                    "argv": ["ssh", "worker@worker-02.example"],
                }
            ],
        }
        return {"result": {"tab_id": tab_id}}

    def run_input(self, session: str, pane_id: str, text: str) -> str:
        self._session(session)
        self.sent.append(("run", pane_id, text))
        return ""

    def wait_output(
        self,
        session: str,
        pane_id: str,
        match_text: str,
        lines: int,
        timeout_ms: int,
        *,
        regex: bool = False,
    ) -> dict[str, Any] | None:
        self._session(session)
        if lines > 80:
            raise AssertionError("unbounded read")
        serialized = (
            self.read_payload
            if isinstance(self.read_payload, str)
            else json.dumps(self.read_payload)
        )
        if regex:
            matched_line = next(
                (
                    line
                    for line in serialized.splitlines()
                    if re.fullmatch(match_text, line)
                ),
                None,
            )
        else:
            matched_line = match_text if match_text in serialized else None
        if matched_line is None:
            return None
        return {
            "type": "output_matched",
            "revision": 7,
            "matched_line": matched_line,
        }

    def _session(self, session: str) -> None:
        if session != self.session:
            raise AssertionError(f"wrong session: {session}")


def make_plan(
    client: FakeClient,
    *,
    live_mutation_authorized: bool = True,
) -> dict[str, Any]:
    return plan(
        client,
        session="operator-session",
        workspace_id="w2",
        workspace_label="worker-02",
        expected_ssh_target="worker@worker-02.example",
        run_id="run-20260723-a",
        harness="agy",
        repo="example/SaariusSkills",
        worktree="/redacted/worktree",
        proof_root="/redacted/proof",
        live_mutation_authorized=live_mutation_authorized,
    )


class DoctorAndPlanTests(unittest.TestCase):
    def test_doctor_accepts_exact_version_protocol_and_session(self) -> None:
        result = doctor(
            FakeClient(),
            "operator-session",
            facts=fixture("doctor-ok.json"),
        )
        self.assertEqual(result["result"], "ok")
        self.assertFalse(result["safety"]["pane_read"])

    def test_doctor_blocks_wrong_version_and_protocol(self) -> None:
        result = doctor(
            FakeClient(),
            "operator-session",
            facts=fixture("doctor-wrong-version.json"),
        )
        self.assertEqual(result["result"], "blocked")
        self.assertIn("unsupported_herdr_version", result["blockers"])
        self.assertIn("unsupported_herdr_protocol", result["blockers"])

    def test_doctor_blocks_missing_socket(self) -> None:
        facts = fixture("doctor-ok.json")
        facts["server_status"]["socket"] = ""
        result = doctor(FakeClient(), "operator-session", facts=facts)
        self.assertEqual(result["result"], "blocked")
        self.assertIn("server_socket_missing", result["blockers"])

    def test_plan_is_source_only_and_deterministic(self) -> None:
        result = plan(
            FakeClient(),
            session="operator-session",
            workspace_id="w2",
            workspace_label="worker-02",
            expected_ssh_target="worker@worker-02.example",
            run_id="run-20260723-a",
            harness="agy",
            repo="example/SaariusSkills",
            worktree="/redacted/worktree",
            proof_root="/redacted/proof",
            facts=fixture("plan-ok.json"),
        )
        self.assertRegex(
            result["owned_label"],
            r"^puppet-agy-run20260-[a-f0-9]{6}-1$",
        )
        self.assertFalse(result["safety"]["parent_session_mutation"])
        self.assertFalse(result["safety"]["live_mutation_authorized"])
        self.assertFalse(result["session"]["incarnation_proven"])

    def test_plan_rejects_workspace_label_mismatch(self) -> None:
        with self.assertRaisesRegex(
            HerdrPuppetError, "exact workspace ID and label"
        ):
            plan(
                FakeClient(),
                session="operator-session",
                workspace_id="w2",
                workspace_label="wrong-label",
                expected_ssh_target="worker@worker-02.example",
                run_id="run-20260723-a",
                harness="agy",
                repo="example/SaariusSkills",
                worktree="/redacted/worktree",
                proof_root="/redacted/proof",
                facts=fixture("plan-ok.json"),
            )


class HerdrClientTests(unittest.TestCase):
    @mock.patch("herdr_puppet_lib.herdr_client.subprocess.run")
    def test_create_tab_accepts_empty_success_output(self, run: mock.Mock) -> None:
        run.return_value = mock.Mock(returncode=0, stdout="", stderr="")
        client = HerdrClient()
        result = client.create_tab("operator-session", "w2", "owned-label")
        self.assertEqual(result, "")

    @mock.patch("herdr_puppet_lib.herdr_client.subprocess.run")
    def test_wait_output_extends_process_timeout_and_maps_native_timeout(
        self,
        run: mock.Mock,
    ) -> None:
        run.return_value = mock.Mock(
            returncode=1,
            stdout="",
            stderr='{"error":{"code":"timeout"}}',
        )
        client = HerdrClient(timeout_seconds=10.0)
        result = client.wait_output(
            "operator-session",
            "w2:p1",
            "NONCE",
            20,
            30_000,
        )
        self.assertIsNone(result)
        self.assertEqual(run.call_args.kwargs["timeout"], 32.0)

    @mock.patch("herdr_puppet_lib.herdr_client.subprocess.run")
    def test_failed_input_never_emits_prompt_in_error_details(
        self,
        run: mock.Mock,
    ) -> None:
        run.return_value = mock.Mock(
            returncode=1,
            stdout="",
            stderr="rejected",
        )
        client = HerdrClient()
        with self.assertRaises(HerdrPuppetError) as caught:
            client.run_input(
                "operator-session",
                "w2:p1",
                "private prompt content",
            )
        serialized = json.dumps(caught.exception.as_json())
        self.assertNotIn("private prompt content", serialized)
        self.assertIn("<redacted-input>", serialized)


class QualificationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = FakeClient()
        self.plan = make_plan(self.client)
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.lease_path = self.root / "lease.json"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def create_lease(self) -> dict[str, Any]:
        return create_qualification_tab(
            self.client,
            plan_payload=self.plan,
            lease_path=self.lease_path,
            allow_live=True,
            settle_seconds=0.1,
        )

    def test_create_tab_requires_both_live_gates(self) -> None:
        blocked_plan = make_plan(self.client, live_mutation_authorized=False)
        with self.assertRaisesRegex(HerdrPuppetError, "Both the plan capability"):
            create_qualification_tab(
                self.client,
                plan_payload=blocked_plan,
                lease_path=self.lease_path,
                allow_live=True,
            )
        with self.assertRaisesRegex(HerdrPuppetError, "Both the plan capability"):
            create_qualification_tab(
                self.client,
                plan_payload=self.plan,
                lease_path=self.lease_path,
                allow_live=False,
            )

    def test_create_tab_never_adopts_duplicate_label(self) -> None:
        self.client.tab_rows.append(
            {
                "workspace_id": "w2",
                "tab_id": "w2:old",
                "label": self.plan["owned_label"],
            }
        )
        with self.assertRaisesRegex(HerdrPuppetError, "Structural status blocked"):
            self.create_lease()
        self.assertFalse(self.lease_path.exists())

    def test_create_tab_binds_exact_structural_and_ssh_identity(self) -> None:
        run_root = self.root / "run"
        initialize_journal(run_root, self.plan)
        lease = create_qualification_tab(
            self.client,
            plan_payload=self.plan,
            lease_path=self.lease_path,
            allow_live=True,
            settle_seconds=0.1,
            run_root=run_root,
        )
        self.assertEqual(lease["tab_id"], "w2:t1")
        self.assertEqual(lease["pane_id"], "w2:p1")
        self.assertEqual(lease["terminal_id"], "term_one")
        self.assertEqual(lease["ssh"]["pid"], 4242)
        self.assertEqual(lease["next_seq"], 1)
        events = (run_root / "events.jsonl").read_text(encoding="utf-8")
        self.assertIn('"kind":"qualification.tab-created"', events)
        self.assertIn('"pane_id":"w2:p1"', events)

    def test_status_detects_terminal_and_process_drift(self) -> None:
        lease = self.create_lease()
        self.client.pane_rows[0]["terminal_id"] = "replacement"
        status = structural_status(self.client, lease_payload=lease)
        self.assertIn("leased_terminal_drift", status["blockers"])
        self.client.pane_rows[0]["terminal_id"] = "term_one"
        self.client.process_rows["w2:p1"]["foreground_processes"][0]["pid"] = 9999
        status = structural_status(self.client, lease_payload=lease)
        self.assertIn("leased_ssh_process_drift", status["blockers"])

    def test_status_detects_socket_path_drift_without_incarnation_claim(self) -> None:
        lease = self.create_lease()
        self.client.server["socket"] = "/redacted/replaced.sock"
        status = structural_status(self.client, lease_payload=lease)
        self.assertIn("server_socket_drift", status["blockers"])
        self.assertFalse(lease["session"]["incarnation_proven"])

    def test_send_rejects_replay_before_mutation(self) -> None:
        lease = self.create_lease()
        with self.assertRaisesRegex(HerdrPuppetError, "stale, skipped"):
            qualification_send(
                self.client,
                lease_payload=lease,
                lease_path=self.lease_path,
                seq=2,
                text="bounded prompt",
                allow_live=True,
            )
        self.assertEqual(self.client.sent, [])

    def test_send_hashes_prompt_and_atomically_advances_sequence(self) -> None:
        lease = self.create_lease()
        run_root = self.root / "run"
        initialize_journal(run_root, self.plan)
        result = qualification_send(
            self.client,
            lease_payload=lease,
            lease_path=self.lease_path,
            seq=1,
            text="bounded prompt",
            allow_live=True,
            run_root=run_root,
        )
        updated = json.loads(self.lease_path.read_text(encoding="utf-8"))
        events = (run_root / "events.jsonl").read_text(encoding="utf-8")
        self.assertEqual(result["next_seq"], 2)
        self.assertEqual(updated["next_seq"], 2)
        self.assertNotIn("bounded prompt", json.dumps(result))
        self.assertNotIn("bounded prompt", events)
        self.assertEqual(
            self.client.sent,
            [("run", "w2:p1", "bounded prompt")],
        )

    def test_partial_send_reconciliation_requires_evidence(self) -> None:
        lease = self.create_lease()
        with self.assertRaisesRegex(HerdrPuppetError, "explicit evidence"):
            qualification_reconcile_send(
                self.client,
                lease_payload=lease,
                lease_path=self.lease_path,
                seq=1,
                text="already applied",
                evidence="remote_process_match",
                confirm_applied=False,
            )
        self.assertEqual(
            json.loads(self.lease_path.read_text(encoding="utf-8"))["next_seq"],
            1,
        )

    def test_partial_send_reconciliation_advances_without_herdr_mutation(self) -> None:
        lease = self.create_lease()
        result = qualification_reconcile_send(
            self.client,
            lease_payload=lease,
            lease_path=self.lease_path,
            seq=1,
            text="already applied",
            evidence="herdr_success_exit+remote_process_match",
            confirm_applied=True,
        )
        self.assertEqual(result["next_seq"], 2)
        self.assertFalse(result["herdr_mutated"])
        self.assertEqual(self.client.sent, [])

    def test_preserved_lease_rejects_send_reconciliation_and_probe(self) -> None:
        lease = self.create_lease()
        lease["state"] = "preserved"
        for operation in (
            lambda: qualification_send(
                self.client,
                lease_payload=lease,
                lease_path=self.lease_path,
                seq=1,
                text="do not send",
                allow_live=True,
            ),
            lambda: qualification_reconcile_send(
                self.client,
                lease_payload=lease,
                lease_path=self.lease_path,
                seq=1,
                text="do not reconcile",
                evidence="none",
                confirm_applied=True,
            ),
            lambda: qualification_token_probe(
                self.client,
                lease_payload=lease,
                nonce="DO-NOT-PROBE",
                allow_live=True,
            ),
            lambda: qualification_beacon_wait(
                self.client,
                lease_payload=lease,
                nonce="DO-NOT-WAIT",
                allow_live=True,
            ),
        ):
            with self.assertRaisesRegex(HerdrPuppetError, "not active"):
                operation()
        self.assertEqual(self.client.sent, [])

    def test_preserve_lease_is_local_idempotent_and_journaled(self) -> None:
        lease = self.create_lease()
        run_root = self.root / "run"
        initialize_journal(run_root, self.plan)
        result = preserve_lease(
            lease_payload=lease,
            lease_path=self.lease_path,
            reason="human_gate",
            run_root=run_root,
        )
        updated = json.loads(self.lease_path.read_text(encoding="utf-8"))
        events = (run_root / "events.jsonl").read_text(encoding="utf-8")
        self.assertEqual(result["state"], "preserved")
        self.assertFalse(result["herdr_mutated"])
        self.assertEqual(updated["state"], "preserved")
        self.assertEqual(updated["preserved_reason"], "human_gate")
        self.assertIn('"kind":"lease.preserved"', events)
        self.assertEqual(self.client.sent, [])
        repeated = preserve_lease(
            lease_payload=updated,
            lease_path=self.lease_path,
            reason="human_gate",
            run_root=run_root,
        )
        self.assertTrue(repeated["already_preserved"])
        self.assertEqual(
            events,
            (run_root / "events.jsonl").read_text(encoding="utf-8"),
        )

    def test_preserve_lease_rejects_unbounded_reason(self) -> None:
        lease = self.create_lease()
        with self.assertRaisesRegex(HerdrPuppetError, "supported bounded reason"):
            preserve_lease(
                lease_payload=lease,
                lease_path=self.lease_path,
                reason="because I felt like it",
            )
        self.assertEqual(
            json.loads(self.lease_path.read_text(encoding="utf-8"))["state"],
            "active",
        )

    def test_beacon_wait_classifies_strict_line_without_emitting_text(self) -> None:
        lease = self.create_lease()
        run_root = self.root / "run"
        initialize_journal(run_root, self.plan)
        self.client.read_payload = (
            "unrelated private-looking output\n"
            "HERDR_PUPPET_ACTION_REQUIRED CHECKPOINT-42"
        )
        result = qualification_beacon_wait(
            self.client,
            lease_payload=lease,
            nonce="CHECKPOINT-42",
            allow_live=True,
            lines=20,
            run_root=run_root,
        )
        events = (run_root / "events.jsonl").read_text(encoding="utf-8")
        self.assertEqual(result["result"], "human_gate")
        self.assertEqual(result["checkpoint"], "ACTION_REQUIRED")
        self.assertNotIn("CHECKPOINT-42", json.dumps(result))
        self.assertNotIn("private-looking", json.dumps(result))
        self.assertNotIn("CHECKPOINT-42", events)
        self.assertNotIn("private-looking", events)

    def test_beacon_wait_rejects_untrusted_line_shape(self) -> None:
        lease = self.create_lease()
        self.client.read_payload = (
            "HERDR_PUPPET_DONE CHECKPOINT-42 trailing transcript content"
        )
        result = qualification_beacon_wait(
            self.client,
            lease_payload=lease,
            nonce="CHECKPOINT-42",
            allow_live=True,
            lines=20,
            timeout_ms=1,
        )
        self.assertEqual(result["result"], "not_matched")
        self.assertIsNone(result["checkpoint"])

    def test_token_probe_never_emits_pane_text(self) -> None:
        lease = self.create_lease()
        self.client.read_payload = {
            "result": {
                "text": "unrelated private-looking pane text\nTOKEN-12345"
            }
        }
        result = qualification_token_probe(
            self.client,
            lease_payload=lease,
            nonce="TOKEN-12345",
            allow_live=True,
            lines=20,
        )
        self.assertTrue(result["matched"])
        self.assertEqual(result["revision"], 7)
        self.assertNotIn("TOKEN-12345", json.dumps(result))
        self.assertNotIn("unrelated", json.dumps(result))
        self.assertFalse(result["pane_text_emitted"])

    def test_token_probe_accepts_raw_herdr_text_without_emitting_it(self) -> None:
        lease = self.create_lease()
        self.client.read_payload = "private-looking text\nTOKEN-RAW"
        result = qualification_token_probe(
            self.client,
            lease_payload=lease,
            nonce="TOKEN-RAW",
            allow_live=True,
            lines=20,
        )
        self.assertTrue(result["matched"])
        self.assertNotIn("private-looking", json.dumps(result))
        self.assertNotIn("TOKEN-RAW", json.dumps(result))

    def test_token_probe_rejects_unbounded_window(self) -> None:
        lease = self.create_lease()
        with self.assertRaisesRegex(HerdrPuppetError, "between 1 and 80"):
            qualification_token_probe(
                self.client,
                lease_payload=lease,
                nonce="TOKEN",
                allow_live=True,
                lines=81,
            )

    def test_journal_summary_and_state_are_transcript_blind(self) -> None:
        lease = self.create_lease()
        run_root = self.root / "run"
        initialize_journal(run_root, self.plan)
        qualification_send(
            self.client,
            lease_payload=lease,
            lease_path=self.lease_path,
            seq=1,
            text="private prompt body",
            allow_live=True,
            run_root=run_root,
        )
        summary = summarize_journal(run_root)
        refreshed = refresh_state(
            run_root,
            json.loads(self.lease_path.read_text(encoding="utf-8")),
        )
        serialized = json.dumps(summary)
        state = (run_root / "STATE.md").read_text(encoding="utf-8")
        self.assertFalse(summary["transcript_included"])
        self.assertNotIn("private prompt body", serialized)
        self.assertNotIn("private prompt body", state)
        self.assertEqual(refreshed["state"], "active")


if __name__ == "__main__":
    unittest.main()
