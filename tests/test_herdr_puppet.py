from __future__ import annotations

import copy
import hashlib
import io
import json
import multiprocessing
import os
import re
import shutil
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
    migrate_legacy_lease,
    migrate_legacy_lease_file,
    plan,
    preserve_lease,
    qualification_beacon_wait,
    qualification_harness_launch,
    qualification_harness_ready,
    qualification_reconcile_send,
    qualification_run,
    qualification_send,
    qualification_startup_gate,
    qualification_token_probe,
    qualification_view_begin,
    qualification_view_complete,
    register_remote_task_file,
    structural_status,
    validate_legacy_lease,
    validate_lease,
)
from herdr_puppet_lib import cli as herdr_cli  # noqa: E402
from herdr_puppet_lib.cli import _read_prompt, build_parser  # noqa: E402
from herdr_puppet_lib.errors import HerdrPuppetError  # noqa: E402
from herdr_puppet_lib.herdr_client import (  # noqa: E402
    MAX_PROMPT_BYTES,
    HerdrClient,
    load_json,
)
from herdr_puppet_lib.harness_binding import (  # noqa: E402
    build_harness_binding,
    compile_instruction_wrapper,
    validate_harness_binding,
    validate_instruction_manifest,
    verify_remote_census,
)
from herdr_puppet_lib.journal import (  # noqa: E402
    append_event,
    initialize_journal,
    make_event,
    read_events,
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
        self.ran: list[tuple[str, str, str]] = []
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

    def run_keys(
        self,
        socket_path: str,
        pane_id: str,
        keys: list[str],
    ) -> str:
        if socket_path != self.server["socket"]:
            raise AssertionError(f"wrong socket: {socket_path}")
        self.sent.append(("keys", pane_id, ",".join(keys)))
        return ""

    def run_command(self, session: str, pane_id: str, command: str) -> str:
        self._session(session)
        self.ran.append(("run", pane_id, command))
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


def multiprocessing_same_seq_run(
    lease_path_text: str,
    marker_path_text: str,
    start_event: Any,
    result_queue: Any,
) -> None:
    lease_path = Path(lease_path_text)
    marker_path = Path(marker_path_text)
    lease = load_json(lease_path)
    client = FakeClient()
    client.create_tab(
        lease["session"]["name"],
        lease["workspace"]["id"],
        lease["owned_label"],
    )

    def record_run(session: str, pane_id: str, command: str) -> str:
        client._session(session)
        with marker_path.open("a", encoding="utf-8") as handle:
            handle.write(f"{pane_id}\n")
        return ""

    client.run_command = record_run  # type: ignore[method-assign]
    start_event.wait(5)
    try:
        qualification_run(
            client,
            lease_payload=lease,
            lease_path=lease_path,
            seq=1,
            command="same-sequence",
            allow_live=True,
        )
    except HerdrPuppetError as exc:
        result_queue.put(exc.code)
    else:
        result_queue.put("ok")


def make_plan(
    client: FakeClient,
    *,
    live_mutation_authorized: bool = True,
) -> dict[str, Any]:
    binding = sample_binding()
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
        harness_binding=binding,
        live_mutation_authorized=live_mutation_authorized,
    )


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def sample_binding(
    *,
    harness: str = "agy",
    repo: str = "example/SaariusSkills",
    worktree: str = "/redacted/worktree",
) -> dict[str, Any]:
    commands = {
        "agy": (
            "agy",
            [
                "--dangerously-skip-permissions",
                "--sandbox=false",
                "--new-project",
                "--log-file",
                "/dev/null",
            ],
        ),
        "codex": ("codex", ["--dangerously-bypass-approvals-and-sandbox"]),
        "claude": ("claude", ["--dangerously-skip-permissions"]),
        "cursor": ("cursor-agent", ["--yolo", "--sandbox", "disabled"]),
        "grok": ("grok", ["--always-approve", "--sandbox", "off"]),
    }
    command, flags = commands[harness]
    executable = {
        "command": command,
        "path": f"/usr/local/bin/{command}",
        "version": f"{command} test-version",
        "sha256": "1" * 64,
        "version_sha256": "2" * 64,
        "help_sha256": "3" * 64,
    }
    executable["fingerprint"] = _digest(executable)
    vector = {
        "argv": [executable["path"], *flags],
        "environment": {
            "HOME": "/redacted/home",
            "LANG": "C",
            "LC_ALL": "C",
            "TERM": "xterm-256color",
        },
    }
    census = {
        "schema": "herdr-puppet.remote-harness-census.v1",
        "harness": harness,
        "host": "worker-02.example",
        "recorded_at": "2026-07-30T12:00:00Z",
        "executable": executable,
        "profile": {
            "route": "dedicated_os_user_profile",
            "root": "/redacted/home",
            "isolation": "dedicated_remote_user",
            "enrollment_state": "enrolled",
            "status_exit": 0,
            "raw_output_retained": False,
        },
        "regular_launch": {
            **vector,
            "unrestricted": True,
            "explicit_model_selector": False,
            "vector_sha256": _digest(vector),
        },
        "model_observation": {
            "selection": "current_default",
            "model": "unavailable",
            "effort": "unavailable",
        },
        "source": {"worktree": worktree},
        "raw_output_retained": False,
    }
    return build_harness_binding(census, repo=repo)


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
        binding = sample_binding()
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
            harness_binding=binding,
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
        binding = sample_binding()
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
                harness_binding=binding,
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
    def test_create_tab_focuses_owned_tab_and_accepts_empty_output(
        self,
        run: mock.Mock,
    ) -> None:
        run.return_value = mock.Mock(returncode=0, stdout="", stderr="")
        client = HerdrClient()
        result = client.create_tab("operator-session", "w2", "owned-label")
        self.assertEqual(result, "")
        run.assert_called_once_with(
            [
                "herdr",
                "--session",
                "operator-session",
                "tab",
                "create",
                "--workspace",
                "w2",
                "--label",
                "owned-label",
                "--focus",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=10.0,
        )

    @mock.patch("herdr_puppet_lib.herdr_client.subprocess.run")
    def test_run_command_uses_exact_pane_run_argv(self, run: mock.Mock) -> None:
        run.return_value = mock.Mock(returncode=0, stdout="accepted\n", stderr="")
        client = HerdrClient()
        result = client.run_command(
            "operator-session",
            "w2:p1",
            "private shell command",
        )
        self.assertEqual(result, "accepted")
        run.assert_called_once_with(
            [
                "herdr",
                "--session",
                "operator-session",
                "pane",
                "run",
                "w2:p1",
                "private shell command",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=10.0,
        )

    @mock.patch("herdr_puppet_lib.herdr_client.subprocess.run")
    def test_run_command_redacts_cli_error(self, run: mock.Mock) -> None:
        run.return_value = mock.Mock(
            returncode=1,
            stdout="",
            stderr=(
                '{"error":{"code":"private shell command",'
                '"message":"rejected private shell command"}}'
            ),
        )
        client = HerdrClient()
        with self.assertRaises(HerdrPuppetError) as caught:
            client.run_command(
                "operator-session",
                "w2:p1",
                "private shell command",
            )
        serialized = json.dumps(caught.exception.as_json())
        self.assertNotIn("private shell command", serialized)
        self.assertEqual(
            caught.exception.details["command"],
            [
                "--session",
                "operator-session",
                "pane",
                "run",
                "w2:p1",
                "<redacted-command>",
            ],
        )
        self.assertEqual(caught.exception.details["returncode"], 1)

    @mock.patch("herdr_puppet_lib.herdr_client.subprocess.run")
    def test_run_command_redacts_controller_timeout(self, run: mock.Mock) -> None:
        run.side_effect = subprocess.TimeoutExpired(
            cmd=["herdr", "private shell command"],
            timeout=10.0,
        )
        client = HerdrClient()
        with self.assertRaises(HerdrPuppetError) as caught:
            client.run_command(
                "operator-session",
                "w2:p1",
                "private shell command",
            )
        serialized = json.dumps(caught.exception.as_json())
        self.assertNotIn("private shell command", serialized)
        self.assertEqual(
            caught.exception.details["command"][-1],
            "<redacted-command>",
        )

    @mock.patch("herdr_puppet_lib.herdr_client.subprocess.run")
    def test_run_command_redacts_process_launch_error(self, run: mock.Mock) -> None:
        run.side_effect = OSError("failed to launch private shell command")
        client = HerdrClient()
        with self.assertRaises(HerdrPuppetError) as caught:
            client.run_command(
                "operator-session",
                "w2:p1",
                "private shell command",
            )
        serialized = json.dumps(caught.exception.as_json())
        self.assertEqual(caught.exception.code, "herdr_launch_failed")
        self.assertNotIn("private shell command", serialized)
        self.assertEqual(
            caught.exception.details["command"][-1],
            "<redacted-command>",
        )

    @mock.patch("herdr_puppet_lib.herdr_client.subprocess.run")
    def test_run_command_rejects_empty_oversized_and_invalid_utf8(
        self,
        run: mock.Mock,
    ) -> None:
        client = HerdrClient()
        for command, code in (
            (" \r\n\t", "command_empty"),
            ("x" * (MAX_PROMPT_BYTES + 1), "command_too_large"),
            ("é" * ((MAX_PROMPT_BYTES // 2) + 1), "command_too_large"),
            ("\ud800", "invalid_command_encoding"),
        ):
            with self.subTest(code=code):
                with self.assertRaises(HerdrPuppetError) as caught:
                    client.run_command("operator-session", "w2:p1", command)
                self.assertEqual(caught.exception.code, code)
        run.assert_not_called()

    def test_qualification_run_parser_requires_non_argv_source(self) -> None:
        parser = build_parser()
        from_file = parser.parse_args(
            [
                "qualification-run",
                "--lease-json",
                "lease.json",
                "--seq",
                "1",
                "--text-file",
                "command.txt",
            ]
        )
        from_stdin = parser.parse_args(
            [
                "qualification-run",
                "--lease-json",
                "lease.json",
                "--seq",
                "1",
                "--stdin",
            ]
        )
        self.assertEqual(from_file.text_file, "command.txt")
        self.assertTrue(from_stdin.prompt_stdin)
        invalid_argv = (
            [
                "qualification-run",
                "--lease-json",
                "lease.json",
                "--seq",
                "1",
            ],
            [
                "qualification-run",
                "--lease-json",
                "lease.json",
                "--seq",
                "1",
                "--text-file",
                "command.txt",
                "--stdin",
            ],
            [
                "qualification-run",
                "--lease-json",
                "lease.json",
                "--seq",
                "1",
                "--text",
                "forbidden",
            ],
            [
                "qualification-run",
                "--lease-json",
                "lease.json",
                "--seq",
                "1",
                "--stdin",
                "forbidden positional command",
            ],
        )
        for argv in invalid_argv:
            with self.subTest(argv=argv):
                with mock.patch("sys.stderr", new=io.StringIO()):
                    with self.assertRaises(SystemExit):
                        parser.parse_args(argv)

    def test_beacon_parser_default_envelope_exceeds_420_seconds(self) -> None:
        args = build_parser().parse_args(
            [
                "qualification-beacon-wait",
                "--lease-json",
                "lease.json",
                "--nonce",
                "CHECKPOINT-123",
                "--run-root",
                "run",
            ]
        )
        self.assertEqual(args.timeout_ms, 480_000)
        self.assertEqual(args.timeout_seconds, 510.0)

    def test_remote_census_is_body_free_for_all_canonical_harnesses(
        self,
    ) -> None:
        commands = {
            "agy": "agy",
            "codex": "codex",
            "claude": "claude",
            "cursor": "cursor-agent",
            "grok": "grok",
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binary_root = root / "bin"
            profile_root = root / "profile"
            worktree = root / "worktree"
            binary_root.mkdir()
            profile_root.mkdir()
            worktree.mkdir()
            executable_body = """#!/bin/sh
case "$1" in
  --version) echo "fake 1.0.0" ;;
  --help) echo "fake help" ;;
  login) echo "Logged in using ChatGPT" ;;
  auth) echo '{"loggedIn":true}' ;;
  status) echo '{"loggedIn":true}' ;;
  models) echo "subscription models available" ;;
  *) exit 2 ;;
esac
"""
            for command in commands.values():
                executable = binary_root / command
                executable.write_text(executable_body, encoding="utf-8")
                executable.chmod(0o755)
            environment = dict(os.environ)
            environment["PATH"] = (
                str(binary_root)
                + os.pathsep
                + environment.get("PATH", "")
            )
            for harness, command in commands.items():
                with self.subTest(harness=harness):
                    completed = subprocess.run(
                        [
                            sys.executable,
                            str(
                                ROOT
                                / "skills"
                                / "herdr-puppet"
                                / "scripts"
                                / "harness_census.py"
                            ),
                            "--harness",
                            harness,
                            "--host",
                            "worker.example",
                            "--profile-root",
                            str(profile_root),
                            "--worktree",
                            str(worktree),
                        ],
                        check=False,
                        capture_output=True,
                        text=True,
                        env=environment,
                    )
                    self.assertEqual(completed.returncode, 0, completed.stderr)
                    payload = json.loads(completed.stdout)
                    self.assertEqual(payload["harness"], harness)
                    self.assertEqual(
                        payload["executable"]["command"],
                        command,
                    )
                    self.assertEqual(
                        payload["profile"]["enrollment_state"],
                        "enrolled",
                    )
                    self.assertFalse(payload["raw_output_retained"])
                    self.assertNotIn("subscription models", completed.stdout)
            row_census = root / "row-census.json"
            row_nonce = "CENSUS-STATUS-20260730-A1"
            row_command = [
                sys.executable,
                str(
                    ROOT
                    / "skills"
                    / "herdr-puppet"
                    / "scripts"
                    / "harness_census.py"
                ),
                "--harness",
                "codex",
                "--host",
                "worker.example",
                "--profile-root",
                str(profile_root),
                "--worktree",
                str(worktree),
                "--output",
                str(row_census),
                "--checkpoint-nonce",
                row_nonce,
            ]
            completed = subprocess.run(
                row_command,
                check=False,
                capture_output=True,
                text=True,
                env=environment,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(
                completed.stdout,
                f"HERDR_PUPPET_STATUS {row_nonce}\n",
            )
            self.assertEqual(
                json.loads(row_census.read_text(encoding="utf-8"))[
                    "harness"
                ],
                "codex",
            )
            replay = subprocess.run(
                row_command,
                check=False,
                capture_output=True,
                text=True,
                env=environment,
            )
            self.assertNotEqual(replay.returncode, 0)
            self.assertEqual(
                json.loads(row_census.read_text(encoding="utf-8"))[
                    "harness"
                ],
                "codex",
            )

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
        self.plan["proof_root"] = str((self.root / "run").resolve())
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

    def persist_lease(self, lease: dict[str, Any]) -> dict[str, Any]:
        self.lease_path.write_text(
            json.dumps(lease),
            encoding="utf-8",
        )
        return lease

    def mark_harness_ready(self, lease: dict[str, Any]) -> dict[str, Any]:
        ready = copy.deepcopy(lease)
        ready["shell_readiness"] = "status_verified"
        ready["harness_readiness"] = "operator_verified"
        ready["harness_readiness_evidence"] = "operator_observed_ready_input"
        ready["harness_readiness_operator"] = "test-operator"
        ready["harness_readiness_verified_at"] = "2026-07-26T00:00:00Z"
        return self.persist_lease(ready)

    def mark_harness_launched(self, lease: dict[str, Any]) -> dict[str, Any]:
        launched = copy.deepcopy(lease)
        launched["shell_readiness"] = "status_verified"
        launched["next_seq"] = max(launched["next_seq"], 3)
        launched["harness_launch"] = {
            "seq": 2,
            "launched_at": "2026-07-30T12:01:00Z",
            "command_sha256": "4" * 64,
            "binding_fingerprint": launched["harness_binding"][
                "fingerprint"
            ],
            "launch_vector_sha256": launched["harness_binding"][
                "regular_launch"
            ]["vector_sha256"],
            "remote_harness_pid": "unavailable",
        }
        return self.persist_lease(launched)

    def submit_for_beacon(self, lease: dict[str, Any]) -> dict[str, Any]:
        qualification_run(
            self.client,
            lease_payload=lease,
            lease_path=self.lease_path,
            seq=lease["next_seq"],
            command="printf beacon-submission",
            allow_live=True,
        )
        return json.loads(self.lease_path.read_text(encoding="utf-8"))

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
        self.assertEqual(lease["shell_readiness"], "unverified")
        self.assertEqual(lease["harness_readiness"], "unverified")
        self.assertEqual(lease["caller_text_files"], [])
        self.assertEqual(lease["caller_text_files_removed"], [])
        self.assertEqual(lease["remote_task_files"], [])
        events = (run_root / "events.jsonl").read_text(encoding="utf-8")
        self.assertIn('"kind":"qualification.tab-created"', events)
        self.assertIn('"pane_id":"w2:p1"', events)
        self.assertIn('"shell_transport_only":true', events)
        self.assertIn('"harness_started":false', events)

    def test_lease_validation_rejects_unknown_schema_field(self) -> None:
        lease = self.create_lease()
        lease["unexpected"] = True
        with self.assertRaises(HerdrPuppetError) as caught:
            validate_lease(lease)
        self.assertEqual(caught.exception.code, "invalid_lease")
        self.assertEqual(
            caught.exception.details["unexpected_fields"],
            ["unexpected"],
        )

    def test_legacy_lease_requires_explicit_canonical_migration(self) -> None:
        legacy = self.create_lease()
        legacy.pop("shell_readiness")
        legacy["harness_readiness"] = "status_verified"
        legacy.pop("caller_text_files")
        legacy.pop("caller_text_files_removed")
        legacy.pop("remote_task_files")
        validate_legacy_lease(legacy)
        with self.assertRaises(HerdrPuppetError) as caught:
            validate_lease(legacy)
        self.assertEqual(
            caught.exception.code,
            "legacy_lease_requires_migration",
        )
        migrated = migrate_legacy_lease(legacy)
        validate_lease(migrated)
        self.assertEqual(migrated["shell_readiness"], "status_verified")
        self.assertEqual(migrated["harness_readiness"], "unverified")
        self.assertEqual(migrated["caller_text_files"], [])
        self.assertEqual(migrated["caller_text_files_removed"], [])
        self.assertEqual(migrated["remote_task_files"], [])

    def test_unbound_legacy_lease_cannot_be_attested_retroactively(self) -> None:
        legacy = self.create_lease()
        legacy.pop("harness_binding")
        legacy.pop("startup_gate_operations")
        legacy.pop("shell_readiness")
        legacy["harness_readiness"] = "status_verified"
        validate_legacy_lease(legacy)
        with self.assertRaises(HerdrPuppetError) as caught:
            migrate_legacy_lease(legacy)
        self.assertEqual(
            caught.exception.code,
            "legacy_harness_binding_unavailable",
        )

    def test_legacy_lease_file_migration_is_locked_and_idempotent(self) -> None:
        legacy = self.create_lease()
        legacy.pop("shell_readiness")
        legacy["harness_readiness"] = "status_verified"
        legacy.pop("remote_task_files")
        self.persist_lease(legacy)
        first = migrate_legacy_lease_file(
            lease_payload=legacy,
            lease_path=self.lease_path,
        )
        self.assertTrue(first["migrated"])
        self.assertEqual(
            first["changed_fields"],
            ["harness_readiness", "remote_task_files", "shell_readiness"],
        )
        canonical = load_json(self.lease_path)
        validate_lease(canonical)
        second = migrate_legacy_lease_file(
            lease_payload=canonical,
            lease_path=self.lease_path,
        )
        self.assertFalse(second["migrated"])
        self.assertEqual(second["changed_fields"], [])

    def test_readiness_evidence_is_accepted_only_for_operator_ready(self) -> None:
        lease = self.create_lease()
        lease["harness_readiness_evidence"] = "operator_observed_ready_input"
        lease["harness_readiness_operator"] = "operator-a"
        lease["harness_readiness_verified_at"] = "2026-07-26T00:00:00Z"
        with self.assertRaises(HerdrPuppetError) as unverified:
            validate_lease(lease)
        self.assertEqual(unverified.exception.code, "invalid_lease")

        lease["harness_readiness"] = "operator_verified"
        validate_lease(lease)
        lease["harness_readiness_operator"] = "operator with spaces"
        with self.assertRaises(HerdrPuppetError) as invalid_operator:
            validate_lease(lease)
        self.assertEqual(invalid_operator.exception.code, "invalid_lease")
        lease["harness_readiness_operator"] = "operator-a"
        lease["harness_readiness_verified_at"] = "not-a-date"
        with self.assertRaises(HerdrPuppetError) as invalid_timestamp:
            validate_lease(lease)
        self.assertEqual(invalid_timestamp.exception.code, "invalid_lease")

    def test_canonical_lease_runtime_rejects_normative_schema_mismatches(
        self,
    ) -> None:
        lease = self.create_lease()

        def operator_ready(payload: dict[str, Any]) -> None:
            payload["harness_readiness"] = "operator_verified"
            payload["harness_readiness_evidence"] = (
                "operator_observed_ready_input"
            )
            payload["harness_readiness_operator"] = "operator-a"
            payload["harness_readiness_verified_at"] = (
                "2026-07-26 00:00:00+00:00"
            )

        invalid_mutations = {
            "boolean_next_seq": lambda payload: payload.__setitem__(
                "next_seq", True
            ),
            "invalid_owned_label": lambda payload: payload.__setitem__(
                "owned_label", "not-owned"
            ),
            "missing_session_socket": lambda payload: payload["session"].pop(
                "socket"
            ),
            "extra_workspace_field": lambda payload: payload[
                "workspace"
            ].__setitem__("extra", True),
            "boolean_ssh_pid": lambda payload: payload["ssh"].__setitem__(
                "pid", True
            ),
            "short_ssh_argv": lambda payload: payload["ssh"].__setitem__(
                "argv", ["ssh"]
            ),
            "missing_source_repo": lambda payload: payload["source"].pop(
                "repo"
            ),
            "missing_harness_binding": lambda payload: payload.pop(
                "harness_binding"
            ),
            "missing_startup_gate_operations": lambda payload: payload.pop(
                "startup_gate_operations"
            ),
            "non_rfc3339_readiness_time": operator_ready,
            "non_array_caller_files": lambda payload: payload.__setitem__(
                "caller_text_files", None
            ),
            "non_array_remote_files": lambda payload: payload.__setitem__(
                "remote_task_files", None
            ),
        }
        for name, mutate in invalid_mutations.items():
            with self.subTest(name=name):
                malformed = copy.deepcopy(lease)
                mutate(malformed)
                with self.assertRaises(HerdrPuppetError):
                    validate_lease(malformed)

    def test_legacy_migration_never_writes_schema_invalid_nested_identity(
        self,
    ) -> None:
        legacy = self.create_lease()
        legacy.pop("shell_readiness")
        legacy["harness_readiness"] = "status_verified"
        legacy["session"].pop("socket")
        self.persist_lease(legacy)
        before = self.lease_path.read_bytes()
        with self.assertRaises(HerdrPuppetError) as caught:
            migrate_legacy_lease_file(
                lease_payload=legacy,
                lease_path=self.lease_path,
            )
        self.assertEqual(caught.exception.code, "invalid_lease")
        self.assertEqual(self.lease_path.read_bytes(), before)

    def test_journal_refresh_rejects_legacy_lease_until_migrated(self) -> None:
        lease = self.create_lease()
        run_root = self.root / "run"
        initialize_journal(run_root, self.plan)
        legacy = copy.deepcopy(lease)
        legacy.pop("shell_readiness")
        with self.assertRaises(HerdrPuppetError) as caught:
            refresh_state(run_root, legacy)
        self.assertEqual(
            caught.exception.code,
            "legacy_lease_requires_migration",
        )

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
        wrong_plan["proof_root"] = str(run_root.resolve())
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

    def test_remote_task_file_lifecycle_never_probes_local_path(self) -> None:
        lease = self.create_lease()
        run_root = self.root / "run"
        initialize_journal(run_root, self.plan)
        remote_path = "/srv/agy/tasks/private-prompt.txt"
        original_exists = Path.exists
        original_is_file = Path.is_file

        def guarded_exists(path: Path) -> bool:
            if str(path) == remote_path:
                raise AssertionError("remote path was probed locally")
            return original_exists(path)

        def guarded_is_file(path: Path) -> bool:
            if str(path) == remote_path:
                raise AssertionError("remote path was probed locally")
            return original_is_file(path)

        with (
            mock.patch.object(Path, "exists", guarded_exists),
            mock.patch.object(Path, "is_file", guarded_is_file),
        ):
            receipt = register_remote_task_file(
                lease_payload=lease,
                lease_path=self.lease_path,
                remote_path=remote_path,
                source_repo=lease["source"]["repo"],
                source_worktree=lease["source"]["worktree"],
                confirm_caller_owned=True,
                run_root=run_root,
            )
        serialized_receipt = json.dumps(receipt)
        events = (run_root / "events.jsonl").read_text(encoding="utf-8")
        self.assertNotIn(remote_path, serialized_receipt)
        self.assertNotIn(remote_path, events)
        self.assertFalse(receipt["path_hashed"])
        registered = load_json(self.lease_path)
        self.assertEqual(
            registered["remote_task_files"][0]["path"],
            remote_path,
        )
        self.assertEqual(
            registered["remote_task_files"][0]["state"],
            "registered",
        )

        maintenance = maintenance_checkpoint(
            self.client,
            lease_payload=registered,
            lease_path=self.lease_path,
            run_root=run_root,
            remote_removed_path=remote_path,
            remote_removal_evidence="operator_verified_remote_absence",
            confirm_remote_removed=True,
        )
        self.assertEqual(
            maintenance["remote_task_files"][0]["path"],
            remote_path,
        )
        self.assertEqual(
            maintenance["remote_task_files"][0]["state"],
            "removal_verified",
        )
        self.assertFalse(maintenance["remote_removal_verification_required"])

    def test_cleanup_requires_remote_removal_evidence(self) -> None:
        lease = self.create_lease()
        run_root = self.root / "run"
        initialize_journal(run_root, self.plan)
        register_remote_task_file(
            lease_payload=lease,
            lease_path=self.lease_path,
            remote_path="/srv/agy/tasks/still-present.txt",
            source_repo=lease["source"]["repo"],
            source_worktree=lease["source"]["worktree"],
            confirm_caller_owned=True,
            run_root=run_root,
        )
        current = load_json(self.lease_path)
        preserve_lease(
            lease_payload=current,
            lease_path=self.lease_path,
            reason="operator_stop",
            run_root=run_root,
        )
        with self.assertRaises(HerdrPuppetError) as caught:
            cleanup_preserved_tab(
                self.client,
                lease_payload=load_json(self.lease_path),
                lease_path=self.lease_path,
                run_root=run_root,
                confirm_tab_id=lease["tab_id"],
                allow_live_cleanup=True,
            )
        self.assertEqual(
            caught.exception.code,
            "remote_task_file_removal_unverified",
        )
        self.assertEqual(self.client.closed_tabs, [])

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
        self.persist_lease(lease)
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
        removed_prompt = str((self.root / "removed-before-cleanup.txt").resolve())
        lease["caller_text_files"] = [removed_prompt]
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
        self.assertEqual(updated["caller_text_files"], [])
        self.assertEqual(updated["caller_text_files_removed"], [removed_prompt])
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

    def test_run_hashes_command_and_advances_sequence_after_cli_success(
        self,
    ) -> None:
        lease = self.create_lease()
        run_root = self.root / "run"
        initialize_journal(run_root, self.plan)
        result = qualification_run(
            self.client,
            lease_payload=lease,
            lease_path=self.lease_path,
            seq=1,
            command="private shell command",
            allow_live=True,
            run_root=run_root,
        )
        updated = json.loads(self.lease_path.read_text(encoding="utf-8"))
        events = (run_root / "events.jsonl").read_text(encoding="utf-8")
        self.assertEqual(result["next_seq"], 2)
        self.assertEqual(updated["next_seq"], 2)
        self.assertEqual(
            result["command_sha256"],
            sha256_text("private shell command"),
        )
        self.assertTrue(result["herdr_cli_acknowledged"])
        self.assertEqual(result["submission_mode"], "atomic_shell_command")
        self.assertEqual(result["execution_acceptance"], "unverified")
        self.assertFalse(result["readiness_advanced"])
        self.assertEqual(result["harness_readiness"], "unverified")
        self.assertFalse(result["transcript_read"])
        self.assertNotIn("private shell command", json.dumps(result))
        self.assertNotIn("private shell command", events)
        self.assertIn('"kind":"qualification.run"', events)
        self.assertIn('"command_sha256"', events)
        self.assertIn('"transcript_read":false', events)
        self.assertEqual(
            self.client.ran,
            [("run", "w2:p1", "private shell command")],
        )
        self.assertEqual(self.client.sent, [])

    def test_run_failure_does_not_advance_sequence_or_leak_command(self) -> None:
        lease = self.create_lease()
        run_root = self.root / "run"
        initialize_journal(run_root, self.plan)
        command_path = self.root / "failing-command.txt"
        command_path.write_text("private failing command", encoding="utf-8")

        def reject_run(*args: Any, **kwargs: Any) -> str:
            raise HerdrPuppetError(
                "herdr_command_failed",
                "Herdr rejected the requested operation.",
                details={
                    "command": [
                        "--session",
                        "operator-session",
                        "pane",
                        "run",
                        "w2:p1",
                        "<redacted-command>",
                    ],
                    "returncode": 1,
                },
            )

        self.client.run_command = reject_run  # type: ignore[method-assign]
        with self.assertRaises(HerdrPuppetError) as caught:
            qualification_run(
                self.client,
                lease_payload=lease,
                lease_path=self.lease_path,
                seq=1,
                command="private failing command",
                text_file=str(command_path),
                allow_live=True,
                run_root=run_root,
            )
        updated = json.loads(self.lease_path.read_text(encoding="utf-8"))
        events = (run_root / "events.jsonl").read_text(encoding="utf-8")
        self.assertEqual(updated["next_seq"], 1)
        self.assertEqual(updated["caller_text_files"], [])
        self.assertNotIn(
            "private failing command",
            json.dumps(caught.exception.as_json()),
        )
        self.assertNotIn("private failing command", events)
        self.assertNotIn('"kind":"qualification.run"', events)

    def test_run_tracks_retained_caller_command_file(self) -> None:
        command_path = self.root / "command.txt"
        command_path.write_text("private command", encoding="utf-8")
        lease = self.create_lease()
        result = qualification_run(
            self.client,
            lease_payload=lease,
            lease_path=self.lease_path,
            seq=1,
            command="private command",
            text_file=str(command_path),
            allow_live=True,
        )
        updated = json.loads(self.lease_path.read_text(encoding="utf-8"))
        normalized_command_path = str(command_path.resolve())
        self.assertEqual(updated["caller_text_files"], [normalized_command_path])
        self.assertTrue(result["caller_text_file_retained"])
        self.assertTrue(result["command_file_tracked"])
        self.assertFalse(result["controller_command_persisted"])
        self.assertEqual(result["caller_input_file_lifecycle"], "caller_owned")
        self.assertNotIn(normalized_command_path, json.dumps(result))
        self.assertNotIn("private command", json.dumps(result))

    def test_run_does_not_retain_missing_caller_command_file(self) -> None:
        missing_command_path = self.root / "missing-command.txt"
        lease = self.create_lease()
        result = qualification_run(
            self.client,
            lease_payload=lease,
            lease_path=self.lease_path,
            seq=1,
            command="private command",
            text_file=str(missing_command_path),
            allow_live=True,
        )
        updated = json.loads(self.lease_path.read_text(encoding="utf-8"))
        self.assertEqual(updated["caller_text_files"], [])
        self.assertFalse(result["caller_text_file_retained"])
        self.assertTrue(result["command_file_tracked"])
        self.assertNotIn(str(missing_command_path.resolve()), json.dumps(result))

    def test_run_rejects_live_sequence_and_structural_gate_failures(self) -> None:
        lease = self.create_lease()
        with self.assertRaises(HerdrPuppetError) as caught:
            qualification_run(
                self.client,
                lease_payload=lease,
                lease_path=self.lease_path,
                seq=1,
                command="do not run",
                allow_live=False,
            )
        self.assertEqual(caught.exception.code, "live_qualification_not_authorized")

        with self.assertRaises(HerdrPuppetError) as caught:
            qualification_run(
                self.client,
                lease_payload=lease,
                lease_path=self.lease_path,
                seq=2,
                command="do not run",
                allow_live=True,
            )
        self.assertEqual(caught.exception.code, "send_sequence_mismatch")

        self.client.pane_rows[0]["terminal_id"] = "replacement"
        with self.assertRaises(HerdrPuppetError) as caught:
            qualification_run(
                self.client,
                lease_payload=lease,
                lease_path=self.lease_path,
                seq=1,
                command="do not run",
                allow_live=True,
            )
        self.assertEqual(caught.exception.code, "prerun_status_blocked")
        self.assertEqual(self.client.ran, [])
        self.assertEqual(
            json.loads(self.lease_path.read_text(encoding="utf-8"))["next_seq"],
            1,
        )

    def test_run_preserves_followon_shell_readiness_gate(self) -> None:
        lease = self.create_lease()
        lease["next_seq"] = 2
        self.lease_path.write_text(json.dumps(lease), encoding="utf-8")
        with self.assertRaises(HerdrPuppetError) as caught:
            qualification_run(
                self.client,
                lease_payload=lease,
                lease_path=self.lease_path,
                seq=2,
                command="next command",
                allow_live=True,
            )
        self.assertEqual(caught.exception.code, "shell_readiness_not_proven")
        self.assertEqual(self.client.ran, [])

        lease["shell_readiness"] = "status_verified"
        self.lease_path.write_text(json.dumps(lease), encoding="utf-8")
        result = qualification_run(
            self.client,
            lease_payload=lease,
            lease_path=self.lease_path,
            seq=2,
            command="next command",
            allow_live=True,
        )
        self.assertEqual(result["next_seq"], 3)
        self.assertEqual(result["shell_readiness"], "status_verified")

    def test_run_rejects_shell_replacing_harness_launcher(self) -> None:
        lease = self.create_lease()
        lease["next_seq"] = 2
        lease["shell_readiness"] = "status_verified"
        self.lease_path.write_text(json.dumps(lease), encoding="utf-8")
        run_root = self.root / "run"
        initialize_journal(run_root, self.plan)
        command = "cd /private/worktree && exec agy --prompt @private-task"

        with self.assertRaises(HerdrPuppetError) as caught:
            qualification_run(
                self.client,
                lease_payload=lease,
                lease_path=self.lease_path,
                seq=2,
                command=command,
                allow_live=True,
                run_root=run_root,
            )

        self.assertEqual(
            caught.exception.code,
            "shell_replacing_harness_launcher",
        )
        self.assertEqual(self.client.ran, [])
        self.assertEqual(load_json(self.lease_path)["next_seq"], 2)
        self.assertNotIn(command, json.dumps(caught.exception.as_json()))
        self.assertNotIn(
            command,
            (run_root / "events.jsonl").read_text(encoding="utf-8"),
        )

    def test_run_rejects_generic_harness_launcher_even_when_shell_survives(self) -> None:
        lease = self.create_lease()
        lease["next_seq"] = 2
        lease["shell_readiness"] = "status_verified"
        self.lease_path.write_text(json.dumps(lease), encoding="utf-8")
        command = "cd /private/worktree && agy --prompt @private-task"

        with self.assertRaises(HerdrPuppetError) as caught:
            qualification_run(
                self.client,
                lease_payload=lease,
                lease_path=self.lease_path,
                seq=2,
                command=command,
                allow_live=True,
            )

        self.assertEqual(caught.exception.code, "generic_harness_launch_forbidden")
        self.assertEqual(self.client.ran, [])

    def test_status_beacon_unlocks_followon_run_in_shared_sequence(self) -> None:
        lease = self.create_lease()
        run_root = self.root / "run"
        initialize_journal(run_root, self.plan)
        first = qualification_run(
            self.client,
            lease_payload=lease,
            lease_path=self.lease_path,
            seq=1,
            command="shell status preflight",
            allow_live=True,
            run_root=run_root,
        )
        self.assertEqual(first["next_seq"], 2)
        self.client.read_payload = "HERDR_PUPPET_STATUS SHELL-READY-1"
        beacon = qualification_beacon_wait(
            self.client,
            lease_payload=load_json(self.lease_path),
            lease_path=self.lease_path,
            nonce="SHELL-READY-1",
            lines=80,
            allow_live=True,
            run_root=run_root,
        )
        self.assertEqual(beacon["shell_readiness"], "status_verified")
        self.assertEqual(beacon["harness_readiness"], "unverified")
        second = qualification_run(
            self.client,
            lease_payload=load_json(self.lease_path),
            lease_path=self.lease_path,
            seq=2,
            command="python3 bounded-census.py",
            allow_live=True,
            run_root=run_root,
        )
        self.assertEqual(second["next_seq"], 3)
        self.assertEqual(
            self.client.ran,
            [
                ("run", "w2:p1", "shell status preflight"),
                ("run", "w2:p1", "python3 bounded-census.py"),
            ],
        )

    def test_cross_process_same_sequence_mutates_herdr_at_most_once(self) -> None:
        self.create_lease()
        marker_path = self.root / "run-marker.txt"
        marker_path.touch()
        context = multiprocessing.get_context("fork")
        start_event = context.Event()
        result_queue = context.Queue()
        processes = [
            context.Process(
                target=multiprocessing_same_seq_run,
                args=(
                    str(self.lease_path),
                    str(marker_path),
                    start_event,
                    result_queue,
                ),
            )
            for _ in range(2)
        ]
        for process in processes:
            process.start()
        start_event.set()
        for process in processes:
            process.join(5)
            self.assertEqual(process.exitcode, 0)
        results = sorted(result_queue.get(timeout=1) for _ in processes)
        self.assertEqual(results, ["ok", "send_sequence_mismatch"])
        self.assertEqual(
            marker_path.read_text(encoding="utf-8").splitlines(),
            ["w2:p1"],
        )
        self.assertEqual(load_json(self.lease_path)["next_seq"], 2)

    def test_run_and_preserve_serialize_without_lost_sequence(self) -> None:
        lease = self.create_lease()
        run_entered = threading.Event()
        release_run = threading.Event()
        preserve_done = threading.Event()
        errors: list[str] = []

        def blocked_run(*args: Any, **kwargs: Any) -> str:
            run_entered.set()
            release_run.wait(2)
            return ""

        self.client.run_command = blocked_run  # type: ignore[method-assign]

        def run_submission() -> None:
            try:
                qualification_run(
                    self.client,
                    lease_payload=lease,
                    lease_path=self.lease_path,
                    seq=1,
                    command="bounded",
                    allow_live=True,
                )
            except HerdrPuppetError as exc:
                errors.append(exc.code)

        def preserve() -> None:
            try:
                preserve_lease(
                    lease_payload=lease,
                    lease_path=self.lease_path,
                    reason="operator_stop",
                )
            except HerdrPuppetError as exc:
                errors.append(exc.code)
            finally:
                preserve_done.set()

        run_thread = threading.Thread(target=run_submission)
        preserve_thread = threading.Thread(target=preserve)
        run_thread.start()
        self.assertTrue(run_entered.wait(1))
        preserve_thread.start()
        self.assertFalse(preserve_done.wait(0.05))
        release_run.set()
        run_thread.join(2)
        preserve_thread.join(2)
        self.assertEqual(errors, [])
        updated = load_json(self.lease_path)
        self.assertEqual(updated["next_seq"], 2)
        self.assertEqual(updated["state"], "preserved")

    def test_shell_status_does_not_authorize_first_pane_input(self) -> None:
        lease = self.create_lease()
        lease["shell_readiness"] = "status_verified"
        self.persist_lease(lease)
        with self.assertRaises(HerdrPuppetError) as caught:
            qualification_send(
                self.client,
                lease_payload=lease,
                lease_path=self.lease_path,
                seq=1,
                text="must not send",
                allow_live=True,
            )
        self.assertEqual(caught.exception.code, "harness_readiness_not_proven")
        self.assertEqual(self.client.sent, [])

    def test_harness_readiness_binds_operator_and_exact_source(self) -> None:
        lease = self.create_lease()
        lease = self.mark_harness_launched(lease)
        run_root = self.root / "run"
        initialize_journal(run_root, self.plan)
        with self.assertRaises(HerdrPuppetError) as caught:
            qualification_harness_ready(
                self.client,
                lease_payload=lease,
                lease_path=self.lease_path,
                source_repo="wrong/repo",
                source_worktree=lease["source"]["worktree"],
                operator_id="operator-a",
                evidence="operator_observed_ready_input",
                confirm_ready=True,
                allow_live=True,
                run_root=run_root,
            )
        self.assertEqual(
            caught.exception.code,
            "harness_readiness_source_mismatch",
        )
        result = qualification_harness_ready(
            self.client,
            lease_payload=lease,
            lease_path=self.lease_path,
            source_repo=lease["source"]["repo"],
            source_worktree=lease["source"]["worktree"],
            operator_id="operator-a",
            evidence="operator_observed_ready_input",
            confirm_ready=True,
            allow_live=True,
            run_root=run_root,
        )
        self.assertEqual(result["harness_readiness"], "operator_verified")
        updated = load_json(self.lease_path)
        self.assertEqual(
            updated["harness_readiness_operator"],
            "operator-a",
        )
        sent = qualification_send(
            self.client,
            lease_payload=updated,
            lease_path=self.lease_path,
            seq=3,
            text="bounded prompt",
            allow_live=True,
        )
        self.assertEqual(sent["next_seq"], 4)

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
            "source/operator-bound harness readiness",
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
        lease = self.mark_harness_ready(lease)
        result = qualification_send(
            self.client,
            lease_payload=lease,
            lease_path=self.lease_path,
            seq=2,
            text="next prompt",
            allow_live=True,
        )
        self.assertEqual(result["next_seq"], 3)
        self.assertEqual(result["harness_readiness"], "operator_verified")

    def test_send_hashes_prompt_and_atomically_advances_sequence(self) -> None:
        lease = self.create_lease()
        lease = self.mark_harness_ready(lease)
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
        self.assertEqual(result["harness_readiness"], "operator_verified")
        self.assertEqual(result["harness_acceptance"], "operator_verified")
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
            lease = self.mark_harness_ready(lease)
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
            self.assertEqual(result["prompt_file_tracked"], True)
            self.assertEqual(result["controller_prompt_persisted"], False)
            self.assertEqual(result["caller_input_file_lifecycle"], "caller_owned")
            self.assertNotIn(normalized_prompt_path, json.dumps(result))

    def test_send_does_not_track_missing_prompt_file(self) -> None:
        lease = self.create_lease()
        lease = self.mark_harness_ready(lease)
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
        self.assertEqual(result["prompt_file_tracked"], True)
        self.assertEqual(result["controller_prompt_persisted"], False)
        self.assertEqual(result["caller_input_file_lifecycle"], "caller_owned")
        self.assertNotIn(str(missing_prompt.resolve()), json.dumps(result))
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
        lease = self.mark_harness_ready(lease)
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

    def test_preserved_lease_rejects_run_send_reconciliation_and_waits(
        self,
    ) -> None:
        lease = self.create_lease()
        lease["state"] = "preserved"
        self.persist_lease(lease)
        initialize_journal(self.root / "run", self.plan)
        for operation in (
            lambda: qualification_run(
                self.client,
                lease_payload=lease,
                lease_path=self.lease_path,
                seq=1,
                command="do not run",
                allow_live=True,
            ),
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
                lease_path=self.lease_path,
                nonce="DO-NOT-PROBE",
                allow_live=True,
            ),
            lambda: qualification_beacon_wait(
                self.client,
                lease_payload=lease,
                lease_path=self.lease_path,
                nonce="DO-NOT-WAIT",
                allow_live=True,
                run_root=self.root / "run",
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
        lease = self.submit_for_beacon(lease)
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
        lease = self.submit_for_beacon(lease)
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
        lease = self.submit_for_beacon(lease)
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
        lease = self.submit_for_beacon(lease)
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
        self.assertEqual(result["shell_readiness"], "status_verified")
        self.assertEqual(updated["shell_readiness"], "status_verified")
        self.assertEqual(result["harness_readiness"], "unverified")
        self.assertEqual(updated["harness_readiness"], "unverified")

    def test_beacon_wait_rejects_terminal_nonce_replay_before_wait(self) -> None:
        lease = self.create_lease()
        run_root = self.root / "run"
        initialize_journal(run_root, self.plan)
        lease = self.submit_for_beacon(lease)
        nonce = "CHECKPOINT-77"
        append_event(
            run_root,
            make_event(
                lease["run_id"],
                "qualification.beacon",
                "ok",
                seq=1,
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
        lease = self.submit_for_beacon(lease)
        nonce = "CHECKPOINT-88"
        append_event(
            run_root,
            make_event(
                lease["run_id"],
                "qualification.beacon",
                "observed",
                seq=1,
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
        lease = self.submit_for_beacon(lease)

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
        self.assertEqual(changed["next_seq"], 3)
        self.assertEqual(changed["state"], "active")
        events = (run_root / "events.jsonl").read_text(encoding="utf-8")
        self.assertNotIn('"kind":"qualification.beacon"', events)

    def test_beacon_wait_rejects_readiness_revision_race(self) -> None:
        lease = self.create_lease()
        run_root = self.root / "run"
        initialize_journal(run_root, self.plan)
        lease = self.submit_for_beacon(lease)

        def race_wait(*args: Any, **kwargs: Any) -> dict[str, Any]:
            changed = json.loads(self.lease_path.read_text(encoding="utf-8"))
            changed["shell_readiness"] = "status_verified"
            self.lease_path.write_text(
                json.dumps(changed),
                encoding="utf-8",
            )
            return {
                "type": "output_matched",
                "revision": 9,
                "matched_line": "HERDR_PUPPET_STATUS CHECKPOINT-67",
            }

        self.client.wait_output = race_wait  # type: ignore[method-assign]
        with self.assertRaises(HerdrPuppetError) as caught:
            qualification_beacon_wait(
                self.client,
                lease_payload=lease,
                lease_path=self.lease_path,
                nonce="CHECKPOINT-67",
                allow_live=True,
                lines=20,
                run_root=run_root,
            )
        self.assertEqual(caught.exception.code, "lease_changed_during_wait")
        events = (run_root / "events.jsonl").read_text(encoding="utf-8")
        self.assertNotIn('"kind":"qualification.beacon"', events)

    def test_controller_timeout_is_reported_and_keeps_active_lease(self) -> None:
        lease = self.create_lease()
        run_root = self.root / "run"
        initialize_journal(run_root, self.plan)
        lease = self.submit_for_beacon(lease)
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

    def test_beacon_rewait_is_nonce_and_submission_bound(self) -> None:
        lease = self.create_lease()
        run_root = self.root / "run"
        initialize_journal(run_root, self.plan)
        lease = self.submit_for_beacon(lease)
        nonce = "REWAIT-NONCE-1"
        self.client.read_payload = "no strict checkpoint"
        first = qualification_beacon_wait(
            self.client,
            lease_payload=lease,
            lease_path=self.lease_path,
            nonce=nonce,
            allow_live=True,
            timeout_ms=1,
            run_root=run_root,
        )
        self.assertEqual(first["attempt"], 1)
        self.assertEqual(first["result"], "not_matched")
        self.client.read_payload = f"HERDR_PUPPET_STATUS {nonce}"
        second = qualification_beacon_wait(
            self.client,
            lease_payload=load_json(self.lease_path),
            lease_path=self.lease_path,
            nonce=nonce,
            allow_live=True,
            timeout_ms=1,
            run_root=run_root,
        )
        self.assertEqual(second["attempt"], 2)
        self.assertEqual(second["checkpoint"], "STATUS")
        with self.assertRaises(HerdrPuppetError) as caught:
            qualification_beacon_wait(
                self.client,
                lease_payload=load_json(self.lease_path),
                lease_path=self.lease_path,
                nonce=nonce,
                allow_live=True,
                timeout_ms=1,
                run_root=run_root,
            )
        self.assertEqual(caught.exception.code, "terminal_beacon_nonce_reused")

    def test_beacon_rewait_rejects_third_not_matched_attempt(self) -> None:
        lease = self.create_lease()
        run_root = self.root / "run"
        initialize_journal(run_root, self.plan)
        lease = self.submit_for_beacon(lease)
        self.client.read_payload = "no strict checkpoint"
        for expected_attempt in (1, 2):
            result = qualification_beacon_wait(
                self.client,
                lease_payload=load_json(self.lease_path),
                lease_path=self.lease_path,
                nonce="REWAIT-NONCE-2",
                allow_live=True,
                timeout_ms=1,
                run_root=run_root,
            )
            self.assertEqual(result["attempt"], expected_attempt)
        with self.assertRaises(HerdrPuppetError) as caught:
            qualification_beacon_wait(
                self.client,
                lease_payload=load_json(self.lease_path),
                lease_path=self.lease_path,
                nonce="REWAIT-NONCE-2",
                allow_live=True,
                timeout_ms=1,
                run_root=run_root,
            )
        self.assertEqual(caught.exception.code, "beacon_rewait_limit")

    def test_beacon_attempts_are_reserved_before_concurrent_waits(self) -> None:
        lease = self.create_lease()
        run_root = self.root / "run"
        initialize_journal(run_root, self.plan)
        lease = self.submit_for_beacon(lease)
        release_waits = threading.Event()
        two_waits_entered = threading.Event()
        calls_lock = threading.Lock()
        wait_calls = 0
        results: list[tuple[str, int | str]] = []

        def blocked_wait(*args: Any, **kwargs: Any) -> dict[str, Any]:
            nonlocal wait_calls
            with calls_lock:
                wait_calls += 1
                if wait_calls == 2:
                    two_waits_entered.set()
            release_waits.wait(2)
            return {
                "type": "output_timeout",
                "timeout_source": "controller",
            }

        self.client.wait_output = blocked_wait  # type: ignore[method-assign]

        def invoke_wait() -> None:
            try:
                receipt = qualification_beacon_wait(
                    self.client,
                    lease_payload=lease,
                    lease_path=self.lease_path,
                    nonce="CONCURRENT-WAIT-1",
                    allow_live=True,
                    timeout_ms=1,
                    run_root=run_root,
                )
            except HerdrPuppetError as exc:
                results.append(("error", exc.code))
            else:
                results.append(("ok", receipt["attempt"]))

        first_two = [threading.Thread(target=invoke_wait) for _ in range(2)]
        for waiter in first_two:
            waiter.start()
        self.assertTrue(two_waits_entered.wait(1))
        third = threading.Thread(target=invoke_wait)
        third.start()
        third.join(1)
        self.assertFalse(third.is_alive())
        self.assertIn(("error", "beacon_rewait_limit"), results)
        self.assertEqual(wait_calls, 2)
        release_waits.set()
        for waiter in first_two:
            waiter.join(2)
        self.assertEqual(
            sorted(item for item in results if item[0] == "ok"),
            [("ok", 1), ("ok", 2)],
        )
        reservations = [
            event
            for event in read_events(run_root)
            if event.get("kind") == "qualification.beacon-wait-reserved"
        ]
        self.assertEqual(len(reservations), 2)

    def test_beacon_rejects_copied_alternate_journal_before_wait(self) -> None:
        lease = self.create_lease()
        run_root = self.root / "run"
        initialize_journal(run_root, self.plan)
        lease = self.submit_for_beacon(lease)
        alternate_root = self.root / "copied-run"
        shutil.copytree(run_root, alternate_root)
        copied_plan = load_json(alternate_root / "plan.json")
        copied_plan["proof_root"] = str(alternate_root.resolve())
        (alternate_root / "plan.json").write_text(
            json.dumps(copied_plan),
            encoding="utf-8",
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
                    nonce="SPLIT-JOURNAL-WAIT",
                    allow_live=True,
                    timeout_ms=1,
                    run_root=alternate_root,
                )
        self.assertEqual(caught.exception.code, "journal_root_mismatch")
        wait_output.assert_not_called()

    def test_beacon_rewait_rejects_cross_submission_nonce_reuse(self) -> None:
        lease = self.create_lease()
        run_root = self.root / "run"
        initialize_journal(run_root, self.plan)
        lease = self.submit_for_beacon(lease)
        self.client.read_payload = "no strict checkpoint"
        qualification_beacon_wait(
            self.client,
            lease_payload=lease,
            lease_path=self.lease_path,
            nonce="REWAIT-NONCE-3",
            allow_live=True,
            timeout_ms=1,
            run_root=run_root,
        )
        advanced = load_json(self.lease_path)
        advanced["shell_readiness"] = "status_verified"
        self.persist_lease(advanced)
        qualification_run(
            self.client,
            lease_payload=advanced,
            lease_path=self.lease_path,
            seq=2,
            command="next submission",
            allow_live=True,
        )
        with self.assertRaises(HerdrPuppetError) as caught:
            qualification_beacon_wait(
                self.client,
                lease_payload=load_json(self.lease_path),
                lease_path=self.lease_path,
                nonce="REWAIT-NONCE-3",
                allow_live=True,
                timeout_ms=1,
                run_root=run_root,
            )
        self.assertEqual(
            caught.exception.code,
            "beacon_nonce_submission_mismatch",
        )

    def test_beacon_wait_does_not_hold_lease_lock_or_overwrite_preserve(
        self,
    ) -> None:
        lease = self.create_lease()
        run_root = self.root / "run"
        initialize_journal(run_root, self.plan)
        lease = self.submit_for_beacon(lease)
        wait_entered = threading.Event()
        release_wait = threading.Event()
        errors: list[str] = []

        def blocked_wait(*args: Any, **kwargs: Any) -> dict[str, Any]:
            wait_entered.set()
            release_wait.wait(2)
            return {
                "type": "output_matched",
                "revision": 10,
                "matched_line": "HERDR_PUPPET_STATUS LOCK-FREE-WAIT",
            }

        self.client.wait_output = blocked_wait  # type: ignore[method-assign]

        def wait_for_beacon() -> None:
            try:
                qualification_beacon_wait(
                    self.client,
                    lease_payload=lease,
                    lease_path=self.lease_path,
                    nonce="LOCK-FREE-WAIT",
                    allow_live=True,
                    run_root=run_root,
                )
            except HerdrPuppetError as exc:
                errors.append(exc.code)

        waiter = threading.Thread(target=wait_for_beacon)
        waiter.start()
        self.assertTrue(wait_entered.wait(1))
        preserved = preserve_lease(
            lease_payload=lease,
            lease_path=self.lease_path,
            reason="operator_stop",
            run_root=run_root,
        )
        self.assertEqual(preserved["state"], "preserved")
        release_wait.set()
        waiter.join(2)
        self.assertEqual(errors, ["lease_changed_during_wait"])
        updated = load_json(self.lease_path)
        self.assertEqual(updated["state"], "preserved")
        self.assertEqual(updated["shell_readiness"], "unverified")
        events = (run_root / "events.jsonl").read_text(encoding="utf-8")
        self.assertNotIn('"kind":"qualification.beacon"', events)

    def test_beacon_wait_does_not_overwrite_harness_readiness(self) -> None:
        lease = self.create_lease()
        lease = self.mark_harness_launched(lease)
        run_root = self.root / "run"
        initialize_journal(run_root, self.plan)
        lease = self.submit_for_beacon(lease)
        wait_entered = threading.Event()
        release_wait = threading.Event()
        errors: list[str] = []

        def blocked_wait(*args: Any, **kwargs: Any) -> dict[str, Any]:
            wait_entered.set()
            release_wait.wait(2)
            return {
                "type": "output_matched",
                "revision": 11,
                "matched_line": "HERDR_PUPPET_STATUS READY-RACE-1",
            }

        self.client.wait_output = blocked_wait  # type: ignore[method-assign]

        def wait_for_beacon() -> None:
            try:
                qualification_beacon_wait(
                    self.client,
                    lease_payload=lease,
                    lease_path=self.lease_path,
                    nonce="READY-RACE-1",
                    allow_live=True,
                    run_root=run_root,
                )
            except HerdrPuppetError as exc:
                errors.append(exc.code)

        waiter = threading.Thread(target=wait_for_beacon)
        waiter.start()
        self.assertTrue(wait_entered.wait(1))
        qualification_harness_ready(
            self.client,
            lease_payload=lease,
            lease_path=self.lease_path,
            source_repo=lease["source"]["repo"],
            source_worktree=lease["source"]["worktree"],
            operator_id="operator-race",
            evidence="operator_observed_ready_input",
            confirm_ready=True,
            allow_live=True,
            run_root=run_root,
        )
        release_wait.set()
        waiter.join(2)
        self.assertEqual(errors, ["lease_changed_during_wait"])
        updated = load_json(self.lease_path)
        self.assertEqual(updated["harness_readiness"], "operator_verified")
        self.assertEqual(
            updated["harness_readiness_operator"],
            "operator-race",
        )

    def test_token_probe_rejects_stale_active_payload_after_preserve(self) -> None:
        lease = self.create_lease()
        stale_active = copy.deepcopy(lease)
        preserve_lease(
            lease_payload=lease,
            lease_path=self.lease_path,
            reason="operator_stop",
        )
        with mock.patch.object(
            self.client,
            "wait_output",
            wraps=self.client.wait_output,
        ) as wait_output:
            with self.assertRaises(HerdrPuppetError) as caught:
                qualification_token_probe(
                    self.client,
                    lease_payload=stale_active,
                    lease_path=self.lease_path,
                    nonce="TOKEN-STALE-ACTIVE",
                    allow_live=True,
                )
        self.assertEqual(caught.exception.code, "stale_lease_payload")
        wait_output.assert_not_called()

    def test_token_probe_rejects_stale_preserved_caller_payload(self) -> None:
        lease = self.create_lease()
        stale_preserved = copy.deepcopy(lease)
        stale_preserved["state"] = "preserved"
        stale_preserved["preserved_reason"] = "operator_stop"
        stale_preserved["preserved_at"] = "2026-07-26T00:00:00Z"
        validate_lease(stale_preserved)
        with mock.patch.object(
            self.client,
            "wait_output",
            wraps=self.client.wait_output,
        ) as wait_output:
            with self.assertRaises(HerdrPuppetError) as caught:
                qualification_token_probe(
                    self.client,
                    lease_payload=stale_preserved,
                    lease_path=self.lease_path,
                    nonce="TOKEN-STALE-PRESERVED",
                    allow_live=True,
                )
        self.assertEqual(caught.exception.code, "stale_lease_payload")
        wait_output.assert_not_called()

    def test_token_probe_rejects_lease_change_during_wait_before_journal(self) -> None:
        lease = self.create_lease()
        run_root = self.root / "run"
        initialize_journal(run_root, self.plan)

        def preserve_during_wait(*args: Any, **kwargs: Any) -> dict[str, Any]:
            preserve_lease(
                lease_payload=lease,
                lease_path=self.lease_path,
                reason="operator_stop",
            )
            return {
                "type": "output_timeout",
                "timeout_source": "native",
            }

        with mock.patch.object(
            self.client,
            "wait_output",
            side_effect=preserve_during_wait,
        ):
            with self.assertRaises(HerdrPuppetError) as caught:
                qualification_token_probe(
                    self.client,
                    lease_payload=lease,
                    lease_path=self.lease_path,
                    nonce="TOKEN-LEASE-RACE",
                    allow_live=True,
                    run_root=run_root,
                )
        self.assertEqual(caught.exception.code, "lease_changed_during_probe")
        self.assertEqual(load_json(self.lease_path)["state"], "preserved")
        self.assertNotIn(
            "qualification.token-probe",
            [event["kind"] for event in read_events(run_root)],
        )

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
            lease_path=self.lease_path,
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
            lease_path=self.lease_path,
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
                lease_path=self.lease_path,
                nonce="TOKEN",
                allow_live=True,
                lines=81,
            )

    def test_journal_summary_and_state_are_transcript_blind(self) -> None:
        lease = self.create_lease()
        lease = self.mark_harness_ready(lease)
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

    def test_binding_records_all_controller_attested_boundaries(self) -> None:
        binding = sample_binding(harness="codex")
        checked = validate_harness_binding(binding)
        self.assertEqual(checked["harness"], "codex")
        self.assertEqual(
            checked["profile"]["isolation"],
            "dedicated_remote_user",
        )
        self.assertFalse(
            checked["regular_launch"]["explicit_model_selector"]
        )
        self.assertEqual(
            checked["model_observation"],
            {
                "selection": "current_default",
                "model": "unavailable",
                "effort": "unavailable",
            },
        )
        self.assertEqual(
            checked["capabilities"],
            {
                "remote_harness_pid": "unavailable",
                "targeted_halt": "unsupported",
                "recovery": "unsupported",
                "crash_persistence": "unsupported",
            },
        )

    def test_in_row_recensus_must_match_bound_remote_facts(self) -> None:
        binding = sample_binding(harness="claude")
        census = {
            "schema": "herdr-puppet.remote-harness-census.v1",
            "harness": binding["harness"],
            "host": binding["remote"]["host"],
            "recorded_at": binding["attestation"]["census_recorded_at"],
            "executable": binding["remote"]["executable"],
            "profile": binding["profile"],
            "regular_launch": binding["regular_launch"],
            "model_observation": binding["model_observation"],
            "source": {"worktree": binding["source"]["worktree"]},
            "raw_output_retained": False,
        }
        result = verify_remote_census(
            binding_value=binding,
            census_value=census,
        )
        self.assertEqual(result["result"], "ok")
        self.assertEqual(
            result["binding_fingerprint"],
            binding["fingerprint"],
        )
        census["executable"] = dict(census["executable"])
        census["executable"]["version"] = "changed"
        census["executable"]["fingerprint"] = _digest(
            {
                key: census["executable"][key]
                for key in (
                    "command",
                    "path",
                    "version",
                    "sha256",
                    "version_sha256",
                    "help_sha256",
                )
            }
        )
        with self.assertRaises(HerdrPuppetError) as caught:
            verify_remote_census(
                binding_value=binding,
                census_value=census,
            )
        self.assertEqual(caught.exception.code, "harness_recensus_mismatch")

    def test_cli_send_forwards_bound_instruction_manifest(self) -> None:
        lease_path = self.root / "cli-lease.json"
        prompt_path = self.root / "cli-prompt.txt"
        manifest_path = self.root / "cli-manifest.json"
        lease_path.write_text("{}\n", encoding="utf-8")
        prompt_path.write_text("wrapped prompt\n", encoding="utf-8")
        manifest_path.write_text('{"schema":"test"}\n', encoding="utf-8")
        args = build_parser().parse_args(
            [
                "qualification-send",
                "--lease-json",
                str(lease_path),
                "--seq",
                "4",
                "--text-file",
                str(prompt_path),
                "--instruction-manifest-json",
                str(manifest_path),
                "--allow-live-qualification",
            ]
        )
        with mock.patch.object(
            herdr_cli,
            "qualification_send",
            return_value={"result": "ok"},
        ) as send:
            result = herdr_cli.run(args)
        self.assertEqual(result["result"], "ok")
        self.assertEqual(
            send.call_args.kwargs["instruction_manifest"],
            {"schema": "test"},
        )

    def test_plan_rejects_noncanonical_harness_before_mutation(self) -> None:
        with self.assertRaises(HerdrPuppetError) as caught:
            plan(
                self.client,
                session="operator-session",
                workspace_id="w2",
                workspace_label="worker-02",
                expected_ssh_target="worker@worker-02.example",
                run_id="run-invalid-harness",
                harness="gemini",
                repo="example/SaariusSkills",
                worktree="/redacted/worktree",
                proof_root="/redacted/proof",
                harness_binding=sample_binding(),
            )
        self.assertEqual(caught.exception.code, "noncanonical_harness")

    def test_dedicated_harness_launch_binds_vector_and_omits_exec(self) -> None:
        lease = self.create_lease()
        lease["shell_readiness"] = "status_verified"
        lease["next_seq"] = 2
        self.persist_lease(lease)
        run_root = self.root / "run"
        initialize_journal(run_root, self.plan)

        result = qualification_harness_launch(
            self.client,
            lease_payload=lease,
            lease_path=self.lease_path,
            seq=2,
            allow_live=True,
            run_root=run_root,
        )

        self.assertEqual(result["next_seq"], 3)
        self.assertFalse(result["explicit_model_selector"])
        self.assertEqual(result["remote_harness_pid"], "unavailable")
        self.assertEqual(result["targeted_halt"], "unsupported")
        self.assertEqual(len(self.client.ran), 1)
        command = self.client.ran[0][2]
        self.assertIn("agy", command)
        self.assertNotRegex(command, r"(?:^|&&)\s*exec\s+")
        updated = load_json(self.lease_path)
        self.assertEqual(
            updated["harness_launch"]["launch_vector_sha256"],
            lease["harness_binding"]["regular_launch"]["vector_sha256"],
        )

    def test_cursor_workspace_trust_is_pre_readiness_single_use(self) -> None:
        client = FakeClient()
        binding = sample_binding(harness="cursor")
        plan_payload = plan(
            client,
            session="operator-session",
            workspace_id="w2",
            workspace_label="worker-02",
            expected_ssh_target="worker@worker-02.example",
            run_id="run-cursor-gate",
            harness="cursor",
            repo="example/SaariusSkills",
            worktree="/redacted/worktree",
            proof_root=str((self.root / "cursor-run").resolve()),
            harness_binding=binding,
            live_mutation_authorized=True,
        )
        run_root = self.root / "cursor-run"
        initialize_journal(run_root, plan_payload)
        lease_path = self.root / "cursor-lease.json"
        lease = create_qualification_tab(
            client,
            plan_payload=plan_payload,
            lease_path=lease_path,
            allow_live=True,
            settle_seconds=0.1,
            run_root=run_root,
        )
        lease["shell_readiness"] = "status_verified"
        lease["next_seq"] = 2
        lease_path.write_text(json.dumps(lease), encoding="utf-8")
        qualification_harness_launch(
            client,
            lease_payload=lease,
            lease_path=lease_path,
            seq=2,
            allow_live=True,
            run_root=run_root,
        )
        launched = load_json(lease_path)
        gate = qualification_startup_gate(
            client,
            lease_payload=launched,
            lease_path=lease_path,
            seq=3,
            gate="workspace_trust",
            action="accept",
            source_worktree="/redacted/worktree",
            operator_id="operator-cursor",
            evidence="operator_observed_exact_gate",
            confirm_exact_worktree=True,
            confirm_unrestricted=True,
            allow_live=True,
            run_root=run_root,
        )
        self.assertTrue(gate["pane_input_mutated"])
        self.assertEqual(client.sent, [("keys", "w2:p1", "a")])
        with self.assertRaises(HerdrPuppetError) as caught:
            qualification_startup_gate(
                client,
                lease_payload=load_json(lease_path),
                lease_path=lease_path,
                seq=4,
                gate="workspace_trust",
                action="accept",
                source_worktree="/redacted/worktree",
                operator_id="operator-cursor",
                evidence="operator_observed_exact_gate",
                confirm_exact_worktree=True,
                confirm_unrestricted=True,
                allow_live=True,
                run_root=run_root,
            )
        self.assertEqual(caught.exception.code, "startup_gate_replay")

    def test_instruction_wrapper_is_bound_to_first_send(self) -> None:
        binding = self.plan["harness_binding"]
        rendered, manifest = compile_instruction_wrapper(
            binding_value=binding,
            run_id=self.plan["run_id"],
            task="Emit the requested checkpoint and remain available.",
        )
        validate_instruction_manifest(
            manifest,
            binding_value=binding,
            rendered=rendered,
        )
        lease = self.mark_harness_ready(self.create_lease())
        result = qualification_send(
            self.client,
            lease_payload=lease,
            lease_path=self.lease_path,
            seq=lease["next_seq"],
            text=rendered.decode("utf-8"),
            instruction_manifest=manifest,
            allow_live=True,
        )
        self.assertEqual(
            result["instruction_wrapper"]["plane"],
            "initial_message_wrapper",
        )
        self.assertEqual(
            result["instruction_wrapper"]["binding_fingerprint"],
            binding["fingerprint"],
        )

    def test_view_checkpoint_binds_real_detach_reattach_evidence(self) -> None:
        lease = self.create_lease()
        run_root = self.root / "run"
        initialize_journal(run_root, self.plan)
        begun = qualification_view_begin(
            self.client,
            lease_payload=lease,
            lease_path=self.lease_path,
            nonce="VIEW-DETACH-1",
            operator_id="operator-view",
            confirm_native_tui_visible=True,
            allow_live=True,
            run_root=run_root,
        )
        completed = qualification_view_complete(
            self.client,
            lease_payload=lease,
            lease_path=self.lease_path,
            nonce="VIEW-DETACH-1",
            operator_id="operator-view",
            evidence="operator_observed_real_client_detach_reattach",
            confirm_detached_reattached=True,
            allow_live=True,
            run_root=run_root,
        )
        self.assertEqual(
            begun["identity_sha256"],
            completed["identity_sha256"],
        )
        self.assertTrue(completed["real_client_detach_reattach"])
        self.assertTrue(completed["leased_identities_unchanged"])


class ContractDocTests(unittest.TestCase):
    def test_skill_contract_captures_agy_prompt_file_print_mode(self) -> None:
        text = (
            ROOT / "skills" / "herdr-puppet" / "SKILL.md"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "agy --prompt @/exact/task-owned-prompt-file --print-timeout 420s",
            text,
        )
        self.assertIn("qualification-run", text)
        self.assertIn("qualification-beacon-wait", text)
        self.assertIn("--lines 80", text)
        self.assertIn("Use `qualification-send` only for ordinary interactive", text)
        self.assertIn("terminal evidence proves the process consumed it", text)
        self.assertIn("Keep the controller plan file outside the intended run root", text)
        self.assertIn("focuses that exact newly created", text)

    def test_qualification_contract_keeps_prompt_mode_narrow(self) -> None:
        text = (
            ROOT
            / "skills"
            / "herdr-puppet"
            / "references"
            / "qualification-contract.md"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "For AGY 1.1.7 noninteractive `--print`, launch task prompts through a",
            text,
        )
        self.assertIn(
            "Do not use positional/argv prompt",
            text,
        )
        self.assertIn(
            "Submit only the short launcher command through `qualification-run`",
            text,
        )
        self.assertIn("execution_acceptance: unverified", text)
        self.assertIn(
            "Ordinary interactive harness prompts remain on `qualification-send`",
            text,
        )
        self.assertIn("`journal-init` owns creating", text)


if __name__ == "__main__":
    unittest.main()
