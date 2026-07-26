from __future__ import annotations

import copy
import json
import re
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from typing import Any
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "skills" / "herdr-puppet" / "scripts"
sys.path.insert(0, str(LIB))

from herdr_puppet_lib.core import (  # noqa: E402
    cleanup_preserved_tab,
    create_qualification_tab,
    doctor,
    maintenance_checkpoint,
    plan,
    preserve_lease,
    qualification_beacon_wait,
    qualification_reconcile_send,
    qualification_send,
    qualification_token_probe,
    structural_status,
)
from herdr_puppet_lib.cli import _read_prompt  # noqa: E402
from herdr_puppet_lib.errors import HerdrPuppetError  # noqa: E402
from herdr_puppet_lib.herdr_client import (  # noqa: E402
    MAX_PROMPT_BYTES,
    HerdrClient,
)
from herdr_puppet_lib.journal import (  # noqa: E402
    append_event,
    initialize_journal,
    make_event,
    refresh_state,
    sha256_text,
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
        self.closed_tabs: list[str] = []
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

    def close_tab(self, session: str, tab_id: str) -> dict[str, Any]:
        self._session(session)
        self.closed_tabs.append(tab_id)
        pane_ids = {
            item["pane_id"]
            for item in self.pane_rows
            if item.get("tab_id") == tab_id
        }
        self.tab_rows = [
            item for item in self.tab_rows if item.get("tab_id") != tab_id
        ]
        self.pane_rows = [
            item for item in self.pane_rows if item.get("tab_id") != tab_id
        ]
        for pane_id in pane_ids:
            self.process_rows.pop(pane_id, None)
        return {"result": {"type": "ok"}}

    def wait_pid_absence(self, pid: int, timeout_seconds: float = 5.0) -> bool:
        return not any(
            process.get("pid") == pid
            for row in self.process_rows.values()
            for process in row.get("foreground_processes", [])
        )

    def run_input(self, socket_path: str, pane_id: str, text: str) -> str:
        if socket_path != self.server["socket"]:
            raise AssertionError(f"wrong socket: {socket_path}")
        self.sent.append(("input", pane_id, text))
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
    def start_socket_server(
        self,
        responder: Any,
    ) -> tuple[str, dict[str, Any], threading.Thread]:
        temporary_directory = tempfile.TemporaryDirectory()
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        socket_path = str(Path(temporary_directory.name) / "herdr.sock")
        server.bind(socket_path)
        server.listen(1)
        observed: dict[str, Any] = {}

        def serve() -> None:
            try:
                connection, _ = server.accept()
                with connection:
                    request_line = bytearray()
                    while b"\n" not in request_line:
                        request_line.extend(connection.recv(64 * 1024))
                    request = json.loads(request_line.split(b"\n", 1)[0])
                    observed["request"] = request
                    response = responder(request)
                    encoded_response = (
                        response
                        if isinstance(response, bytes)
                        else json.dumps(response).encode("utf-8")
                    )
                    connection.sendall(encoded_response + b"\n")
            finally:
                server.close()

        thread = threading.Thread(target=serve, daemon=True)
        thread.start()

        def cleanup() -> None:
            thread.join(timeout=1)
            server.close()
            temporary_directory.cleanup()

        self.addCleanup(cleanup)
        return socket_path, observed, thread

    @mock.patch("herdr_puppet_lib.herdr_client.subprocess.run")
    def test_create_tab_accepts_empty_success_output(self, run: mock.Mock) -> None:
        run.return_value = mock.Mock(returncode=0, stdout="", stderr="")
        client = HerdrClient()
        result = client.create_tab("operator-session", "w2", "owned-label")
        self.assertEqual(result, "")

    @mock.patch("herdr_puppet_lib.herdr_client.subprocess.run")
    def test_wait_output_honors_controller_cap_and_maps_native_timeout(
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
        self.assertEqual(
            result,
            {"type": "output_timeout", "timeout_source": "herdr"},
        )
        self.assertEqual(run.call_args.kwargs["timeout"], 10.0)

    @mock.patch("herdr_puppet_lib.herdr_client.subprocess.run")
    def test_wait_output_maps_controller_hard_timeout_without_hanging(
        self,
        run: mock.Mock,
    ) -> None:
        run.side_effect = subprocess.TimeoutExpired(
            cmd=["herdr", "wait", "output"],
            timeout=20.0,
        )
        client = HerdrClient(timeout_seconds=20.0)
        result = client.wait_output(
            "operator-session",
            "w2:p1",
            "NONCE",
            20,
            300_000,
        )
        self.assertEqual(
            result,
            {"type": "output_timeout", "timeout_source": "controller"},
        )
        self.assertEqual(run.call_args.kwargs["timeout"], 20.0)

    @mock.patch("herdr_puppet_lib.herdr_client.subprocess.run")
    def test_input_uses_atomic_socket_request_and_never_process_argv(
        self,
        run: mock.Mock,
    ) -> None:
        socket_path, observed, thread = self.start_socket_server(
            lambda request: {
                "id": request["id"],
                "result": {"type": "ok"},
            }
        )
        client = HerdrClient()
        result = client.run_input(
            socket_path,
            "w2:p1",
            "private prompt content",
        )
        thread.join(timeout=1)
        self.assertEqual(result, {"type": "ok"})
        self.assertEqual(observed["request"]["method"], "pane.send_input")
        self.assertEqual(
            observed["request"]["params"],
            {
                "pane_id": "w2:p1",
                "text": "private prompt content",
                "keys": ["enter"],
            },
        )
        run.assert_not_called()

    def test_failed_input_never_emits_prompt_in_error_details(self) -> None:
        socket_path, _, _ = self.start_socket_server(
            lambda request: {
                "id": request["id"],
                "error": {
                    "code": "invalid_params",
                    "message": f"rejected {request['params']['text']}",
                },
            }
        )
        client = HerdrClient()
        with self.assertRaises(HerdrPuppetError) as caught:
            client.run_input(
                socket_path,
                "w2:p1",
                "private prompt content",
            )
        serialized = json.dumps(caught.exception.as_json())
        self.assertNotIn("private prompt content", serialized)
        self.assertEqual(
            caught.exception.details["api_error_code"],
            "invalid_params",
        )

    def test_invalid_utf8_acknowledgement_is_unknown_without_prompt_leak(self) -> None:
        socket_path, _, _ = self.start_socket_server(lambda request: b"\xff")
        client = HerdrClient()
        with self.assertRaises(HerdrPuppetError) as caught:
            client.run_input(
                socket_path,
                "w2:p1",
                "private prompt content",
            )
        self.assertEqual(caught.exception.code, "herdr_input_outcome_unknown")
        self.assertNotIn(
            "private prompt content",
            json.dumps(caught.exception.as_json()),
        )

    def test_input_rejects_oversized_prompt_before_socket_access(self) -> None:
        client = HerdrClient()
        with self.assertRaises(HerdrPuppetError) as caught:
            client.run_input(
                "/does/not/exist.sock",
                "w2:p1",
                "x" * (MAX_PROMPT_BYTES + 1),
            )
        self.assertEqual(caught.exception.code, "prompt_too_large")

    def test_input_rejects_empty_prompt_before_socket_access(self) -> None:
        client = HerdrClient()
        with self.assertRaises(HerdrPuppetError) as caught:
            client.run_input(
                "/does/not/exist.sock",
                "w2:p1",
                " \r\n\t",
            )
        self.assertEqual(caught.exception.code, "prompt_empty")

    def test_prompt_file_removes_only_one_terminal_line_ending(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            prompt_path = Path(directory) / "prompt.txt"
            prompt_path.write_bytes(b"first line\nsecond line\n\n")
            self.assertEqual(
                _read_prompt(text_file=str(prompt_path), prompt_stdin=False),
                "first line\nsecond line\n",
            )


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

    def test_create_tab_requires_initialized_journal_before_mutation(self) -> None:
        run_root = self.root / "uninitialized-run"
        with self.assertRaisesRegex(
            HerdrPuppetError,
            "Initialize the controller journal before mutating Herdr",
        ):
            create_qualification_tab(
                self.client,
                plan_payload=self.plan,
                lease_path=self.lease_path,
                allow_live=True,
                settle_seconds=0.1,
                run_root=run_root,
            )
        self.assertEqual(self.client.tab_rows, [])
        self.assertEqual(self.client.pane_rows, [])
        self.assertFalse(self.lease_path.exists())

    def test_create_tab_rejects_journal_from_another_run_before_mutation(
        self,
    ) -> None:
        run_root = self.root / "wrong-run"
        wrong_plan = copy.deepcopy(self.plan)
        wrong_plan["run_id"] = "different-run"
        initialize_journal(run_root, wrong_plan)
        with self.assertRaisesRegex(
            HerdrPuppetError,
            "belongs to a different run",
        ):
            create_qualification_tab(
                self.client,
                plan_payload=self.plan,
                lease_path=self.lease_path,
                allow_live=True,
                settle_seconds=0.1,
                run_root=run_root,
            )
        self.assertEqual(self.client.tab_rows, [])
        self.assertEqual(self.client.pane_rows, [])
        self.assertFalse(self.lease_path.exists())

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

    def test_maintenance_checkpoint_classifies_exact_live_lease(self) -> None:
        lease = self.create_lease()
        run_root = self.root / "run"
        initialize_journal(run_root, self.plan)
        result = maintenance_checkpoint(
            self.client,
            lease_payload=lease,
            lease_path=self.lease_path,
            run_root=run_root,
        )
        events = (run_root / "events.jsonl").read_text(encoding="utf-8")
        self.assertEqual(result["classification"], "active")
        self.assertEqual(result["resources"]["tab"]["state"], "present")
        self.assertEqual(result["resources"]["pane"]["state"], "present")
        self.assertEqual(result["resources"]["ssh"]["state"], "present")
        self.assertFalse(result["maintenance_candidate"])
        self.assertFalse(result["cleanup_authorized"])
        self.assertFalse(result["cleanup_performed"])
        self.assertFalse(result["herdr_mutated"])
        self.assertFalse(result["transcript_read"])
        self.assertIn('"kind":"maintenance.checkpoint"', events)

    def test_maintenance_checkpoint_routes_missing_active_lease_to_preserve(
        self,
    ) -> None:
        lease = self.create_lease()
        run_root = self.root / "run"
        initialize_journal(run_root, self.plan)
        self.client.tab_rows = []
        self.client.pane_rows = []
        result = maintenance_checkpoint(
            self.client,
            lease_payload=lease,
            lease_path=self.lease_path,
            run_root=run_root,
        )
        self.assertEqual(result["classification"], "stale")
        self.assertTrue(result["maintenance_candidate"])
        self.assertEqual(result["recommended_action"], "preserve_lease")
        self.assertEqual(
            result["resources"]["tab"]["state"],
            "missing",
        )
        self.assertEqual(
            result["resources"]["pane"]["state"],
            "missing",
        )
        self.assertEqual(result["resources"]["ssh"]["state"], "unverified")
        self.assertFalse(result["cleanup_performed"])
        self.assertEqual(
            json.loads(self.lease_path.read_text(encoding="utf-8"))["state"],
            "active",
        )

    def test_maintenance_checkpoint_deduplicates_absent_prompt_files(self) -> None:
        lease = self.create_lease()
        preserved_prompt = self.root / "present.txt"
        removed_prompt = self.root / "removed.txt"
        preserved_prompt.write_text("still present", encoding="utf-8")
        removed_prompt.write_text("to remove", encoding="utf-8")
        lease["caller_text_files"] = [
            str(preserved_prompt.resolve()),
            str(removed_prompt.resolve()),
        ]
        removed_prompt.unlink()
        self.lease_path.write_text(json.dumps(lease), encoding="utf-8")
        run_root = self.root / "run"
        initialize_journal(run_root, self.plan)
        result = maintenance_checkpoint(
            self.client,
            lease_payload=lease,
            lease_path=self.lease_path,
            run_root=run_root,
        )
        updated = json.loads(self.lease_path.read_text(encoding="utf-8"))
        self.assertEqual(
            updated["caller_text_files"],
            [str(preserved_prompt.resolve())],
        )
        self.assertEqual(
            updated["caller_text_files_removed"],
            [str(removed_prompt.resolve())],
        )
        self.assertEqual(
            result["caller_text_files"],
            [str(preserved_prompt.resolve())],
        )
        self.assertEqual(
            result["caller_text_files_removed"],
            [str(removed_prompt.resolve())],
        )

    def test_maintenance_checkpoint_ignores_same_label_decoys(self) -> None:
        lease = self.create_lease()
        run_root = self.root / "run"
        initialize_journal(run_root, self.plan)
        self.client.tab_rows = [
            {
                "workspace_id": "w2",
                "tab_id": "w2:decoy",
                "label": lease["owned_label"],
            }
        ]
        self.client.pane_rows = [
            {
                "workspace_id": "w2",
                "tab_id": "w2:decoy",
                "pane_id": "w2:decoy-pane",
                "terminal_id": "decoy-terminal",
            }
        ]
        result = maintenance_checkpoint(
            self.client,
            lease_payload=lease,
            lease_path=self.lease_path,
            run_root=run_root,
        )
        self.assertEqual(result["classification"], "stale")
        self.assertEqual(result["resources"]["tab"]["state"], "missing")
        self.assertEqual(result["resources"]["pane"]["state"], "missing")
        self.assertEqual(self.client.sent, [])

    def test_maintenance_checkpoint_marks_moved_exact_ids_ambiguous(self) -> None:
        lease = self.create_lease()
        run_root = self.root / "run"
        initialize_journal(run_root, self.plan)
        self.client.tab_rows[0]["workspace_id"] = "w9"
        self.client.pane_rows[0]["workspace_id"] = "w9"
        self.client.pane_rows[0]["tab_id"] = lease["tab_id"]
        result = maintenance_checkpoint(
            self.client,
            lease_payload=lease,
            lease_path=self.lease_path,
            run_root=run_root,
        )
        self.assertEqual(result["classification"], "ambiguous")
        self.assertEqual(result["resources"]["tab"]["state"], "moved")
        self.assertEqual(result["resources"]["pane"]["state"], "moved")
        self.assertIn("leased_tab_moved", result["blockers"])
        self.assertIn("leased_pane_moved", result["blockers"])

    def test_maintenance_checkpoint_marks_duplicate_exact_ids_ambiguous(
        self,
    ) -> None:
        lease = self.create_lease()
        run_root = self.root / "run"
        initialize_journal(run_root, self.plan)
        self.client.tab_rows.append(copy.deepcopy(self.client.tab_rows[0]))
        self.client.pane_rows.append(copy.deepcopy(self.client.pane_rows[0]))
        result = maintenance_checkpoint(
            self.client,
            lease_payload=lease,
            lease_path=self.lease_path,
            run_root=run_root,
        )
        self.assertEqual(result["classification"], "ambiguous")
        self.assertEqual(result["resources"]["tab"]["state"], "duplicate")
        self.assertEqual(result["resources"]["pane"]["state"], "duplicate")
        self.assertIn("leased_tab_duplicate", result["blockers"])
        self.assertIn("leased_pane_duplicate", result["blockers"])

    def test_maintenance_checkpoint_retains_live_preserved_lease(self) -> None:
        lease = self.create_lease()
        lease["state"] = "preserved"
        run_root = self.root / "run"
        initialize_journal(run_root, self.plan)
        tabs_before = copy.deepcopy(self.client.tab_rows)
        panes_before = copy.deepcopy(self.client.pane_rows)
        result = maintenance_checkpoint(
            self.client,
            lease_payload=lease,
            lease_path=self.lease_path,
            run_root=run_root,
        )
        self.assertEqual(result["classification"], "preserved")
        self.assertEqual(
            result["recommended_action"],
            "retain_or_route_exact_cleanup",
        )
        self.assertEqual(self.client.tab_rows, tabs_before)
        self.assertEqual(self.client.pane_rows, panes_before)
        self.assertEqual(self.client.sent, [])
        self.assertFalse(result["cleanup_performed"])
        self.assertFalse(result["herdr_mutated"])

    def test_cleanup_preserved_tab_closes_only_exact_lease(self) -> None:
        lease = self.create_lease()
        lease["state"] = "preserved"
        self.lease_path.write_text(json.dumps(lease), encoding="utf-8")
        run_root = self.root / "run"
        initialize_journal(run_root, self.plan)
        self.client.tab_rows.append(
            {
                "workspace_id": "w2",
                "tab_id": "w2:decoy",
                "label": lease["owned_label"],
            }
        )
        result = cleanup_preserved_tab(
            self.client,
            lease_payload=lease,
            lease_path=self.lease_path,
            run_root=run_root,
            confirm_tab_id=lease["tab_id"],
            allow_live_cleanup=True,
        )
        updated = json.loads(self.lease_path.read_text(encoding="utf-8"))
        self.assertTrue(result["cleanup_performed"])
        self.assertTrue(result["absence_verified"])
        self.assertTrue(result["ssh_pid_absence_verified"])
        self.assertEqual(self.client.closed_tabs, [lease["tab_id"]])
        self.assertEqual(
            [item["tab_id"] for item in self.client.tab_rows],
            ["w2:decoy"],
        )
        self.assertEqual(updated["cleanup_state"], "closed")
        events = (run_root / "events.jsonl").read_text(encoding="utf-8")
        self.assertIn('"kind":"cleanup.requested"', events)
        self.assertIn('"kind":"cleanup.closed"', events)
        maintenance = maintenance_checkpoint(
            self.client,
            lease_payload=updated,
            lease_path=self.lease_path,
            run_root=run_root,
        )
        self.assertEqual(maintenance["classification"], "stale")
        self.assertFalse(maintenance["maintenance_candidate"])
        self.assertEqual(maintenance["recommended_action"], "none")

    def test_cleanup_preserved_tab_rejects_active_or_wrong_confirmation(
        self,
    ) -> None:
        lease = self.create_lease()
        run_root = self.root / "run"
        initialize_journal(run_root, self.plan)
        with self.assertRaises(HerdrPuppetError) as active:
            cleanup_preserved_tab(
                self.client,
                lease_payload=lease,
                lease_path=self.lease_path,
                run_root=run_root,
                confirm_tab_id=lease["tab_id"],
                allow_live_cleanup=True,
            )
        self.assertEqual(active.exception.code, "cleanup_lease_not_preserved")
        lease["state"] = "preserved"
        self.lease_path.write_text(json.dumps(lease), encoding="utf-8")
        with self.assertRaises(HerdrPuppetError) as mismatch:
            cleanup_preserved_tab(
                self.client,
                lease_payload=lease,
                lease_path=self.lease_path,
                run_root=run_root,
                confirm_tab_id="w2:wrong",
                allow_live_cleanup=True,
            )
        self.assertEqual(
            mismatch.exception.code,
            "cleanup_tab_confirmation_mismatch",
        )
        self.assertEqual(self.client.closed_tabs, [])

    def test_cleanup_preserved_tab_reconciles_already_absent_identity(
        self,
    ) -> None:
        lease = self.create_lease()
        lease["state"] = "preserved"
        self.lease_path.write_text(json.dumps(lease), encoding="utf-8")
        self.client.tab_rows = []
        self.client.pane_rows = []
        self.client.process_rows = {}
        run_root = self.root / "run"
        initialize_journal(run_root, self.plan)
        result = cleanup_preserved_tab(
            self.client,
            lease_payload=lease,
            lease_path=self.lease_path,
            run_root=run_root,
            confirm_tab_id=lease["tab_id"],
            allow_live_cleanup=True,
        )
        updated = json.loads(self.lease_path.read_text(encoding="utf-8"))
        self.assertFalse(result["cleanup_performed"])
        self.assertTrue(result["already_closed"])
        self.assertEqual(self.client.closed_tabs, [])
        self.assertEqual(updated["cleanup_state"], "closed")
        self.assertTrue(updated["cleanup_reconciled_absence"])

    def test_cleanup_preserved_tab_rejects_closed_record_with_live_identity(
        self,
    ) -> None:
        lease = self.create_lease()
        lease["state"] = "preserved"
        lease["cleanup_state"] = "closed"
        lease["cleanup_verified_at"] = "2026-07-26T00:00:00Z"
        lease["cleanup_reconciled_absence"] = False
        self.lease_path.write_text(json.dumps(lease), encoding="utf-8")
        run_root = self.root / "run"
        initialize_journal(run_root, self.plan)
        with self.assertRaises(HerdrPuppetError) as caught:
            cleanup_preserved_tab(
                self.client,
                lease_payload=lease,
                lease_path=self.lease_path,
                run_root=run_root,
                confirm_tab_id=lease["tab_id"],
                allow_live_cleanup=True,
            )
        self.assertEqual(caught.exception.code, "cleanup_record_conflict")
        self.assertEqual(self.client.closed_tabs, [])

    def test_cleanup_preserved_tab_rechecks_pid_absence_on_replay(self) -> None:
        lease = self.create_lease()
        lease["state"] = "preserved"
        lease["cleanup_state"] = "closed"
        lease["cleanup_verified_at"] = "2026-07-26T00:00:00Z"
        lease["cleanup_reconciled_absence"] = False
        self.lease_path.write_text(json.dumps(lease), encoding="utf-8")
        self.client.tab_rows = []
        self.client.pane_rows = []
        run_root = self.root / "run"
        initialize_journal(run_root, self.plan)
        with self.assertRaises(HerdrPuppetError) as caught:
            cleanup_preserved_tab(
                self.client,
                lease_payload=lease,
                lease_path=self.lease_path,
                run_root=run_root,
                confirm_tab_id=lease["tab_id"],
                allow_live_cleanup=True,
            )
        self.assertEqual(
            caught.exception.code,
            "cleanup_ssh_pid_absence_not_verified",
        )
        self.assertEqual(self.client.closed_tabs, [])

    def test_cleanup_preserved_tab_rejects_unverified_close(self) -> None:
        lease = self.create_lease()
        lease["state"] = "preserved"
        self.lease_path.write_text(json.dumps(lease), encoding="utf-8")
        run_root = self.root / "run"
        initialize_journal(run_root, self.plan)
        self.client.close_tab = (  # type: ignore[method-assign]
            lambda *args, **kwargs: {"result": {"type": "ok"}}
        )
        with self.assertRaises(HerdrPuppetError) as caught:
            cleanup_preserved_tab(
                self.client,
                lease_payload=lease,
                lease_path=self.lease_path,
                run_root=run_root,
                confirm_tab_id=lease["tab_id"],
                allow_live_cleanup=True,
            )
        self.assertEqual(caught.exception.code, "cleanup_close_not_verified")
        updated = json.loads(self.lease_path.read_text(encoding="utf-8"))
        self.assertNotIn("cleanup_state", updated)

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

    def test_send_rejects_followup_prompt_without_status_beacon(self) -> None:
        lease = self.create_lease()
        lease["next_seq"] = 2
        self.lease_path.write_text(json.dumps(lease), encoding="utf-8")
        with self.assertRaisesRegex(
            HerdrPuppetError,
            "status-verified harness readiness",
        ):
            qualification_send(
                self.client,
                lease_payload=lease,
                lease_path=self.lease_path,
                seq=2,
                text="next prompt",
                allow_live=True,
            )

    def test_send_allows_followup_prompt_after_status_beacon(self) -> None:
        lease = self.create_lease()
        lease["next_seq"] = 2
        lease["harness_readiness"] = "status_verified"
        self.lease_path.write_text(json.dumps(lease), encoding="utf-8")
        result = qualification_send(
            self.client,
            lease_payload=lease,
            lease_path=self.lease_path,
            seq=2,
            text="next prompt",
            allow_live=True,
        )
        self.assertEqual(result["next_seq"], 3)

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
        self.assertTrue(result["transport_acknowledged"])
        self.assertEqual(result["acceptance_scope"], "herdr_pane_input_only")
        self.assertEqual(result["outcome"], "pane_input_accepted")
        self.assertEqual(result["harness_readiness"], "unverified")
        self.assertEqual(result["harness_acceptance"], "unverified")
        self.assertEqual(updated["next_seq"], 2)
        self.assertNotIn("bounded prompt", json.dumps(result))
        self.assertNotIn("bounded prompt", events)
        self.assertEqual(
            self.client.sent,
            [("input", "w2:p1", "bounded prompt")],
        )

    def test_send_tracks_retained_prompt_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            prompt_path = Path(directory) / "prompt.txt"
            prompt_path.write_text("from file", encoding="utf-8")
            lease = self.create_lease()
            run_root = self.root / "run"
            initialize_journal(run_root, self.plan)
            result = qualification_send(
                self.client,
                lease_payload=lease,
                lease_path=self.lease_path,
                seq=1,
                text="via file",
                text_file=str(prompt_path),
                allow_live=True,
                run_root=run_root,
            )
            updated = json.loads(self.lease_path.read_text(encoding="utf-8"))
            normalized_prompt_path = str(prompt_path.resolve())
            self.assertEqual(updated["caller_text_files"], [normalized_prompt_path])
            self.assertEqual(result["caller_text_file_retained"], True)
            self.assertEqual(result["prompt_file_tracked"], normalized_prompt_path)

    def test_send_does_not_track_missing_prompt_file(self) -> None:
        lease = self.create_lease()
        missing_prompt = self.root / "missing.txt"
        if missing_prompt.exists():
            missing_prompt.unlink()
        result = qualification_send(
            self.client,
            lease_payload=lease,
            lease_path=self.lease_path,
            seq=1,
            text="missing file",
            text_file=str(missing_prompt),
            allow_live=True,
        )
        updated = json.loads(self.lease_path.read_text(encoding="utf-8"))
        self.assertEqual(result["caller_text_file_retained"], False)
        self.assertEqual(result["prompt_file_tracked"], str(missing_prompt.resolve()))
        self.assertEqual(updated["caller_text_files"], [])

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
                lease_path=self.lease_path,
                nonce="DO-NOT-WAIT",
                allow_live=True,
                run_root=self.root / "unused",
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
            lease_path=self.lease_path,
            nonce="CHECKPOINT-42",
            allow_live=True,
            lines=20,
            run_root=run_root,
        )
        events = (run_root / "events.jsonl").read_text(encoding="utf-8")
        self.assertEqual(result["result"], "human_gate")
        self.assertEqual(result["checkpoint"], "ACTION_REQUIRED")
        self.assertTrue(result["auto_preserved"])
        self.assertEqual(result["lease_state"], "preserved")
        updated = json.loads(self.lease_path.read_text(encoding="utf-8"))
        self.assertEqual(updated["state"], "preserved")
        self.assertEqual(updated["preserved_reason"], "human_gate")
        self.assertNotIn("CHECKPOINT-42", json.dumps(result))
        self.assertNotIn("private-looking", json.dumps(result))
        self.assertNotIn("CHECKPOINT-42", events)
        self.assertNotIn("private-looking", events)

    def test_beacon_wait_rejects_untrusted_line_shape(self) -> None:
        lease = self.create_lease()
        run_root = self.root / "run"
        initialize_journal(run_root, self.plan)
        self.client.read_payload = (
            "HERDR_PUPPET_DONE CHECKPOINT-42 trailing transcript content"
        )
        result = qualification_beacon_wait(
            self.client,
            lease_payload=lease,
            lease_path=self.lease_path,
            nonce="CHECKPOINT-42",
            allow_live=True,
            lines=20,
            timeout_ms=1,
            run_root=run_root,
        )
        self.assertEqual(result["result"], "not_matched")
        self.assertIsNone(result["checkpoint"])
        self.assertFalse(result["auto_preserved"])
        self.assertEqual(
            json.loads(self.lease_path.read_text(encoding="utf-8"))["state"],
            "active",
        )

    def test_done_beacon_auto_preserves_milestone_lease(self) -> None:
        lease = self.create_lease()
        run_root = self.root / "run"
        initialize_journal(run_root, self.plan)
        self.client.read_payload = "HERDR_PUPPET_DONE CHECKPOINT-99"
        result = qualification_beacon_wait(
            self.client,
            lease_payload=lease,
            lease_path=self.lease_path,
            nonce="CHECKPOINT-99",
            allow_live=True,
            lines=20,
            run_root=run_root,
        )
        updated = json.loads(self.lease_path.read_text(encoding="utf-8"))
        self.assertEqual(result["result"], "ok")
        self.assertEqual(result["checkpoint"], "DONE")
        self.assertTrue(result["auto_preserved"])
        self.assertEqual(updated["state"], "preserved")
        self.assertEqual(updated["preserved_reason"], "milestone_complete")

    def test_status_beacon_keeps_active_lease(self) -> None:
        lease = self.create_lease()
        run_root = self.root / "run"
        initialize_journal(run_root, self.plan)
        self.client.read_payload = "HERDR_PUPPET_STATUS CHECKPOINT-88"
        result = qualification_beacon_wait(
            self.client,
            lease_payload=lease,
            lease_path=self.lease_path,
            nonce="CHECKPOINT-88",
            allow_live=True,
            lines=20,
            run_root=run_root,
        )
        updated = json.loads(self.lease_path.read_text(encoding="utf-8"))
        self.assertEqual(result["result"], "observed")
        self.assertEqual(result["checkpoint"], "STATUS")
        self.assertFalse(result["auto_preserved"])
        self.assertEqual(result["lease_state"], "active")
        self.assertEqual(updated["state"], "active")
        self.assertEqual(result["harness_readiness"], "status_verified")
        self.assertEqual(updated["harness_readiness"], "status_verified")

    def test_beacon_wait_rejects_terminal_nonce_replay_before_wait(self) -> None:
        lease = self.create_lease()
        run_root = self.root / "run"
        initialize_journal(run_root, self.plan)
        nonce = "CHECKPOINT-77"
        append_event(
            run_root,
            make_event(
                lease["run_id"],
                "qualification.beacon",
                "ok",
                nonce_sha256=sha256_text(nonce),
                data={"checkpoint": "DONE"},
            ),
        )
        with mock.patch.object(
            self.client,
            "wait_output",
            wraps=self.client.wait_output,
        ) as wait_output:
            with self.assertRaises(HerdrPuppetError) as caught:
                qualification_beacon_wait(
                    self.client,
                    lease_payload=lease,
                    lease_path=self.lease_path,
                    nonce=nonce,
                    allow_live=True,
                    lines=20,
                    run_root=run_root,
                )
        self.assertEqual(caught.exception.code, "terminal_beacon_nonce_reused")
        wait_output.assert_not_called()

    def test_beacon_wait_rejects_status_nonce_replay_before_wait(self) -> None:
        lease = self.create_lease()
        run_root = self.root / "run"
        initialize_journal(run_root, self.plan)
        nonce = "CHECKPOINT-88"
        append_event(
            run_root,
            make_event(
                lease["run_id"],
                "qualification.beacon",
                "observed",
                nonce_sha256=sha256_text(nonce),
                data={"checkpoint": "STATUS"},
            ),
        )
        with self.assertRaises(HerdrPuppetError):
            qualification_beacon_wait(
                self.client,
                lease_payload=lease,
                lease_path=self.lease_path,
                nonce=nonce,
                allow_live=True,
                lines=20,
                run_root=run_root,
            )

    def test_beacon_wait_rejects_lease_revision_race_before_journaling(
        self,
    ) -> None:
        lease = self.create_lease()
        run_root = self.root / "run"
        initialize_journal(run_root, self.plan)

        def race_wait(*args: Any, **kwargs: Any) -> dict[str, Any]:
            changed = json.loads(self.lease_path.read_text(encoding="utf-8"))
            changed["next_seq"] += 1
            self.lease_path.write_text(
                json.dumps(changed),
                encoding="utf-8",
            )
            return {
                "type": "output_matched",
                "revision": 8,
                "matched_line": "HERDR_PUPPET_DONE CHECKPOINT-66",
            }

        self.client.wait_output = race_wait  # type: ignore[method-assign]
        with self.assertRaises(HerdrPuppetError) as caught:
            qualification_beacon_wait(
                self.client,
                lease_payload=lease,
                lease_path=self.lease_path,
                nonce="CHECKPOINT-66",
                allow_live=True,
                lines=20,
                run_root=run_root,
            )
        self.assertEqual(caught.exception.code, "lease_changed_during_wait")
        changed = json.loads(self.lease_path.read_text(encoding="utf-8"))
        self.assertEqual(changed["next_seq"], 2)
        self.assertEqual(changed["state"], "active")
        events = (run_root / "events.jsonl").read_text(encoding="utf-8")
        self.assertNotIn('"kind":"qualification.beacon"', events)

    def test_controller_timeout_is_reported_and_keeps_active_lease(self) -> None:
        lease = self.create_lease()
        run_root = self.root / "run"
        initialize_journal(run_root, self.plan)
        self.client.wait_output = (  # type: ignore[method-assign]
            lambda *args, **kwargs: {
                "type": "output_timeout",
                "timeout_source": "controller",
            }
        )
        result = qualification_beacon_wait(
            self.client,
            lease_payload=lease,
            lease_path=self.lease_path,
            nonce="CHECKPOINT-55",
            allow_live=True,
            lines=20,
            run_root=run_root,
        )
        self.assertEqual(result["result"], "not_matched")
        self.assertEqual(result["timeout_source"], "controller")
        self.assertFalse(result["auto_preserved"])
        self.assertEqual(result["lease_state"], "active")
        updated = json.loads(self.lease_path.read_text(encoding="utf-8"))
        self.assertEqual(updated["state"], "active")

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


class ContractDocTests(unittest.TestCase):
    def test_skill_contract_captures_agy_prompt_file_print_mode(self) -> None:
        text = (
            ROOT / "skills" / "herdr-puppet" / "SKILL.md"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "agy --prompt @/exact/task-owned-prompt-file --print-timeout <bounded>",
            text,
        )
        self.assertIn("should carry only a short launcher command", text)
        self.assertIn("terminal evidence proves the process consumed it", text)

    def test_qualification_contract_keeps_prompt_mode_narrow(self) -> None:
        text = (
            ROOT / "skills" / "herdr-puppet" / "references" / "qualification-contract.md"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "For AGY 1.1.7 noninteractive `--print`, launch task prompts through a",
            text,
        )
        self.assertIn(
            "Do not use positional/argv prompt",
            text,
        )
        self.assertIn("Send only the short launcher command", text)


if __name__ == "__main__":
    unittest.main()
