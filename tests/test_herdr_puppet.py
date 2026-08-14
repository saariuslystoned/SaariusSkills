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
import stat
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
    _regular_launch_command,
    cleanup_preserved_tab,
    create_qualification_tab,
    doctor,
    maintenance_checkpoint,
    load_destination_catalog,
    migrate_legacy_lease,
    migrate_legacy_lease_file,
    plan,
    plan_selection_receipt,
    preserve_lease,
    qualification_beacon_wait,
    qualification_claude_lifecycle_observe,
    qualification_claude_receipt_command,
    qualification_harness_census_verify,
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
    validate_plan,
    validate_destination_catalog,
)
from herdr_puppet_lib import cli as herdr_cli  # noqa: E402
from herdr_puppet_lib.cli import _read_prompt, build_parser  # noqa: E402
from herdr_puppet_lib.errors import HerdrPuppetError  # noqa: E402
from herdr_puppet_lib.authority import (  # noqa: E402
    deterministic_owned_label,
    selected_authority,
    selected_authority_sha256,
)
from herdr_puppet_lib.claude_hooks import (  # noqa: E402
    CLAUDE_MARKER_NAMES,
    build_claude_lifecycle_observation,
    checkpoint_lifecycle_observation,
    claude_helper_exec_argv,
    claude_hook_settings,
    claude_launch_flags,
    validate_claude_hook_receipt,
)
from herdr_puppet_lib.claude_hook_marker import (  # noqa: E402
    ClaudeHookMarkerError,
    canonical_bytes as canonical_hook_bytes,
    marker_payload,
    observe as observe_claude_hooks,
    record_event as record_claude_hook,
)
from herdr_puppet_lib.herdr_client import (  # noqa: E402
    MAX_PROMPT_BYTES,
    HerdrClient,
    load_json,
)
from herdr_puppet_lib.harness_binding import (  # noqa: E402
    AGY_REQUIRED_MODEL,
    HISTORICAL_HARNESS_LAUNCH_FLAGS,
    build_harness_binding,
    compile_instruction_wrapper,
    binding_fingerprint,
    validate_harness_binding,
    validate_instruction_manifest,
    validate_remote_census,
    verify_remote_census,
)
from herdr_puppet_lib.journal import (  # noqa: E402
    append_event,
    atomic_json,
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


def refresh_selected_authority(record: dict[str, Any]) -> dict[str, Any]:
    record["selected_authority_sha256"] = selected_authority_sha256(record)
    return record


def historical_lease_v1(record: dict[str, Any]) -> dict[str, Any]:
    historical = copy.deepcopy(record)
    historical["schema"] = "herdr-puppet.lease.v1"
    historical.pop("destination_selection", None)
    historical.pop("selected_authority_sha256", None)
    binding = historical.get("harness_binding")
    if isinstance(binding, dict) and binding.get("schema") == (
        "herdr-puppet.harness-binding.v3"
    ):
        binding["schema"] = "herdr-puppet.harness-binding.v2"
        binding["regular_launch"]["argv"] = [
            binding["remote"]["executable"]["path"],
            *HISTORICAL_HARNESS_LAUNCH_FLAGS[historical["harness"]],
        ]
        binding["regular_launch"]["explicit_model_selector"] = False
        binding["regular_launch"]["vector_sha256"] = hashlib.sha256(
            json.dumps(
                {
                    "argv": binding["regular_launch"]["argv"],
                    "environment": binding["regular_launch"]["environment"],
                    "inherit_environment": False,
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        binding["model_observation"] = {
            "selection": "current_default",
            "model": "unavailable",
            "effort": "unavailable",
        }
        binding["instructions"]["layers"][2] = "model/default-unresolved"
        binding["fingerprint"] = binding_fingerprint(binding)
    return historical


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
        self.sent_key_vectors: list[list[str]] = []
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
        workspace_label = next(
            row["label"]
            for row in self.workspace_rows
            if row["workspace_id"] == workspace_id
        )
        ssh_target = (
            f"worker@{workspace_label}.example"
            if workspace_label.startswith("aiworker-")
            else "worker@worker-02.example"
        )
        self.process_rows[pane_id] = {
            "pane_id": pane_id,
            "foreground_processes": [
                {
                    "pid": 4242,
                    "argv": ["ssh", ssh_target],
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

    def run_input(
        self,
        socket_path: str,
        pane_id: str,
        text: str,
        keys: list[str] | None = None,
    ) -> str:
        if socket_path != self.server["socket"]:
            raise AssertionError(f"wrong socket: {socket_path}")
        self.sent.append(("input", pane_id, text))
        self.sent_key_vectors.append(["enter"] if keys is None else list(keys))
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
    run_root_text: str,
    marker_path_text: str,
    start_event: Any,
    result_queue: Any,
) -> None:
    lease_path = Path(lease_path_text)
    run_root = Path(run_root_text)
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
            command=(
                "printf '%s\\n' "
                "'HERDR_PUPPET_STATUS MULTIPROCESS-STATUS-1'"
            ),
            allow_live=True,
            run_root=run_root,
        )
    except HerdrPuppetError as exc:
        result_queue.put(exc.code)
    else:
        result_queue.put("ok")


def make_plan(
    client: FakeClient,
    *,
    live_mutation_authorized: bool = True,
    harness: str = "agy",
) -> dict[str, Any]:
    binding = sample_binding(harness=harness)
    return plan(
        client,
        session="operator-session",
        workspace_id="w2",
        workspace_label="worker-02",
        expected_ssh_target="worker@worker-02.example",
        run_id="run-20260723-a",
        harness=harness,
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
    run_id: str = "run-20260723-a",
) -> dict[str, Any]:
    commands = {
        "agy": (
            "agy",
            [
                "--model",
                AGY_REQUIRED_MODEL,
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
    if harness == "claude":
        local_helper = (
            ROOT
            / "skills"
            / "herdr-puppet"
            / "scripts"
            / "claude_hook_marker.py"
        )
        local_implementation = (
            ROOT
            / "skills"
            / "herdr-puppet"
            / "scripts"
            / "herdr_puppet_lib"
            / "claude_hook_marker.py"
        )
        lifecycle_observation = build_claude_lifecycle_observation(
            run_id=run_id,
            marker_root=f"/redacted/claude-hooks/{run_id}",
            helper_path=str(
                Path(worktree)
                / "skills"
                / "herdr-puppet"
                / "scripts"
                / "claude_hook_marker.py"
            ),
            helper_sha256=hashlib.sha256(local_helper.read_bytes()).hexdigest(),
            implementation_path=str(
                Path(worktree)
                / "skills"
                / "herdr-puppet"
                / "scripts"
                / "herdr_puppet_lib"
                / "claude_hook_marker.py"
            ),
            implementation_sha256=hashlib.sha256(
                local_implementation.read_bytes()
            ).hexdigest(),
            interpreter_path="/usr/bin/python3",
            interpreter_sha256="4" * 64,
        )
        flags = claude_launch_flags(lifecycle_observation)
    else:
        lifecycle_observation = checkpoint_lifecycle_observation()
    vector = {
        "argv": [executable["path"], *flags],
        "environment": {
            "HOME": "/redacted/home",
            "PATH": (
                "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:"
                "/usr/sbin:/sbin"
            ),
            "LANG": "C",
            "LC_ALL": "C",
            "TERM": "xterm-256color",
        },
        "inherit_environment": False,
    }
    census = {
        "schema": "herdr-puppet.remote-harness-census.v3",
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
            "explicit_model_selector": harness == "agy",
            "vector_sha256": _digest(vector),
        },
        "lifecycle_observation": lifecycle_observation,
        "model_observation": (
            {
                "selection": "explicit",
                "model": AGY_REQUIRED_MODEL,
                "effort": "high",
            }
            if harness == "agy"
            else {
                "selection": "current_default",
                "model": "unavailable",
                "effort": "unavailable",
            }
        ),
        "source": {"worktree": worktree},
        "raw_output_retained": False,
    }
    return build_harness_binding(census, repo=repo)


def sample_census_from_binding(
    binding: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema": "herdr-puppet.remote-harness-census.v3",
        "harness": binding["harness"],
        "host": binding["remote"]["host"],
        "recorded_at": binding["attestation"]["census_recorded_at"],
        "executable": copy.deepcopy(binding["remote"]["executable"]),
        "profile": copy.deepcopy(binding["profile"]),
        "regular_launch": copy.deepcopy(binding["regular_launch"]),
        "lifecycle_observation": copy.deepcopy(
            binding["lifecycle_observation"]
        ),
        "model_observation": copy.deepcopy(binding["model_observation"]),
        "source": {"worktree": binding["source"]["worktree"]},
        "raw_output_retained": False,
    }


def claude_hook_receipt(
    binding: dict[str, Any],
    *,
    session_start: int = 1,
    user_prompt_submit: int = 0,
    stop: int = 0,
    stop_failure: int = 0,
    prompt_sha256s: list[str] | None = None,
) -> dict[str, Any]:
    observation = binding["lifecycle_observation"]
    counts = {
        "session_start": session_start,
        "user_prompt_submit": user_prompt_submit,
        "stop": stop,
        "stop_failure": stop_failure,
    }
    prompt_sha256s = list(prompt_sha256s or [])
    if len(prompt_sha256s) != user_prompt_submit:
        raise AssertionError(
            "synthetic Claude receipts need one hash per submitted prompt"
        )
    markers = []
    for event in sorted(counts):
        for ordinal in range(1, counts[event] + 1):
            prompt_sha256 = (
                prompt_sha256s[ordinal - 1]
                if event == "user_prompt_submit"
                else None
            )
            encoded = canonical_hook_bytes(
                marker_payload(
                    run_id=observation["run_id"],
                    probe_id=observation["probe_id"],
                    event=event,
                    ordinal=ordinal,
                    prompt_sha256=prompt_sha256,
                )
            ) + b"\n"
            marker = {
                "event": event,
                "ordinal": ordinal,
                "sha256": hashlib.sha256(encoded).hexdigest(),
            }
            if prompt_sha256 is not None:
                marker["prompt_sha256"] = prompt_sha256
            markers.append(marker)
    return {
        "schema": "herdr-puppet.claude-hook-receipt.v1",
        "run_id": observation["run_id"],
        "probe_id": observation["probe_id"],
        "markers": markers,
        "counts": counts,
        "marker_set_sha256": hashlib.sha256(
            canonical_hook_bytes(markers)
        ).hexdigest(),
        "stdin_read": user_prompt_submit > 0,
        "raw_input_retained": False,
        "transcript_read": False,
    }


class ClaudeHookMarkerTests(unittest.TestCase):
    def test_native_hook_overflow_sentinel_invalidates_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "markers"
            run_id = "run-hook-overflow"
            probe_id = "8" * 64
            record_claude_hook(
                root_value=str(root),
                run_id=run_id,
                probe_id=probe_id,
                event="session_start",
            )
            for ordinal in (1, 2):
                record_claude_hook(
                    root_value=str(root),
                    run_id=run_id,
                    probe_id=probe_id,
                    event="user_prompt_submit",
                    prompt_sha256=str(ordinal) * 64,
                )
                record_claude_hook(
                    root_value=str(root),
                    run_id=run_id,
                    probe_id=probe_id,
                    event="stop",
                )
            with self.assertRaises(ClaudeHookMarkerError):
                record_claude_hook(
                    root_value=str(root),
                    run_id=run_id,
                    probe_id=probe_id,
                    event="user_prompt_submit",
                    prompt_sha256="3" * 64,
                )
            overflow = root / "overflow.json"
            self.assertTrue(overflow.is_file())
            self.assertEqual(stat.S_IMODE(overflow.stat().st_mode), 0o600)
            self.assertNotIn("3" * 64, overflow.read_text(encoding="utf-8"))
            with self.assertRaises(ClaudeHookMarkerError):
                observe_claude_hooks(
                    root_value=str(root),
                    run_id=run_id,
                    probe_id=probe_id,
                )

    def test_claude_hook_settings_use_isolated_exec_form(self) -> None:
        binding = sample_binding(harness="claude")
        observation = binding["lifecycle_observation"]
        settings = claude_hook_settings(observation)
        handlers = [
            handler
            for groups in settings["hooks"].values()
            for group in groups
            for handler in group["hooks"]
        ]
        self.assertEqual(len(handlers), 4)
        for handler in handlers:
            self.assertEqual(
                handler["command"],
                observation["interpreter"]["path"],
            )
            self.assertEqual(handler["args"][0], "-I")
            self.assertEqual(handler["args"][1], "-c")
            self.assertEqual(
                handler["args"][3],
                observation["interpreter"]["path"],
            )
            self.assertEqual(
                handler["args"][4],
                observation["interpreter"]["sha256"],
            )
            self.assertEqual(
                handler["args"][5],
                observation["helper"]["path"],
            )
            self.assertEqual(
                handler["args"][6],
                observation["helper"]["sha256"],
            )
            self.assertNotIn("shell", handler)

    def test_claude_helper_bootstrap_rejects_preexecution_helper_drift(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            worktree = Path(directory) / "worktree"
            helper = (
                worktree
                / "skills"
                / "herdr-puppet"
                / "scripts"
                / "claude_hook_marker.py"
            )
            implementation = (
                helper.parent
                / "herdr_puppet_lib"
                / "claude_hook_marker.py"
            )
            helper.parent.mkdir(parents=True)
            implementation.parent.mkdir(parents=True)
            source_helper = (
                ROOT
                / "skills"
                / "herdr-puppet"
                / "scripts"
                / "claude_hook_marker.py"
            )
            source_implementation = (
                source_helper.parent
                / "herdr_puppet_lib"
                / "claude_hook_marker.py"
            )
            shutil.copy2(source_helper, helper)
            shutil.copy2(source_implementation, implementation)
            interpreter = Path(sys.executable).resolve()
            observation = build_claude_lifecycle_observation(
                run_id="run-bootstrap-drift",
                marker_root=str(Path(directory) / "markers"),
                helper_path=str(helper),
                helper_sha256=hashlib.sha256(helper.read_bytes()).hexdigest(),
                implementation_path=str(implementation),
                implementation_sha256=hashlib.sha256(
                    implementation.read_bytes()
                ).hexdigest(),
                interpreter_path=str(interpreter),
                interpreter_sha256=hashlib.sha256(
                    interpreter.read_bytes()
                ).hexdigest(),
            )
            helper.write_text(
                "print('{\"schema\":\"forged\"}')\n",
                encoding="utf-8",
            )
            argv = claude_helper_exec_argv(
                observation,
                [
                    "observe",
                    "--root",
                    observation["marker_root"],
                    "--run-id",
                    observation["run_id"],
                    "--probe-id",
                    observation["probe_id"],
                    "--implementation-sha256",
                    observation["implementation"]["sha256"],
                ],
            )
            completed = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 2)
            self.assertEqual(completed.stdout, "")
            self.assertEqual(completed.stderr, "")
            shutil.copy2(source_helper, helper)
            wrong_interpreter = copy.deepcopy(observation)
            wrong_interpreter["interpreter"]["sha256"] = "0" * 64
            wrong_argv = claude_helper_exec_argv(
                wrong_interpreter,
                [
                    "observe",
                    "--root",
                    observation["marker_root"],
                    "--run-id",
                    observation["run_id"],
                    "--probe-id",
                    observation["probe_id"],
                    "--implementation-sha256",
                    observation["implementation"]["sha256"],
                ],
            )
            wrong_completed = subprocess.run(
                wrong_argv,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(wrong_completed.returncode, 2)
            self.assertEqual(wrong_completed.stdout, "")
            helper.unlink()
            os.mkfifo(helper)
            fifo_helper = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            )
            self.assertEqual(fifo_helper.returncode, 2)
            helper.unlink()
            shutil.copy2(source_helper, helper)
            implementation.unlink()
            os.mkfifo(implementation)
            fifo_implementation = subprocess.run(
                claude_helper_exec_argv(
                    observation,
                    [
                        "observe",
                        "--root",
                        observation["marker_root"],
                        "--run-id",
                        observation["run_id"],
                        "--probe-id",
                        observation["probe_id"],
                        "--implementation-sha256",
                        observation["implementation"]["sha256"],
                    ],
                ),
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            )
            self.assertEqual(fifo_implementation.returncode, 2)

    def test_native_hook_helper_is_silent_and_retains_no_input(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "markers"
            prompt_sentinel = "PRIVATE-PROMPT-MUST-NOT-PERSIST"
            transcript_sentinel = "/private/transcripts/MUST-NOT-PERSIST.jsonl"
            hook_stdin = json.dumps(
                {
                    "hook_event_name": "UserPromptSubmit",
                    "prompt": prompt_sentinel,
                    "transcript_path": transcript_sentinel,
                }
            )
            helper = (
                ROOT
                / "skills"
                / "herdr-puppet"
                / "scripts"
                / "claude_hook_marker.py"
            )
            implementation = (
                helper.parent
                / "herdr_puppet_lib"
                / "claude_hook_marker.py"
            )
            implementation_sha256 = hashlib.sha256(
                implementation.read_bytes()
            ).hexdigest()
            base = [
                sys.executable,
                str(helper),
                "record",
                "--root",
                str(root),
                "--run-id",
                "run-hook-silent",
                "--probe-id",
                "a" * 64,
                "--implementation-sha256",
                implementation_sha256,
            ]
            completed = subprocess.run(
                [*base, "--event", "session_start"],
                input=hook_stdin,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0)
            self.assertEqual(completed.stdout, "")
            self.assertEqual(completed.stderr, "")
            for event in ("user_prompt_submit", "stop"):
                event_result = subprocess.run(
                    [*base, "--event", event],
                    input=hook_stdin,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(event_result.returncode, 0)
                self.assertEqual(event_result.stdout, "")
                self.assertEqual(event_result.stderr, "")
            receipt = observe_claude_hooks(
                root_value=str(root),
                run_id="run-hook-silent",
                probe_id="a" * 64,
            )
            self.assertEqual(
                receipt["counts"],
                {
                    "session_start": 1,
                    "user_prompt_submit": 1,
                    "stop": 1,
                    "stop_failure": 0,
                },
            )
            self.assertIs(receipt["stdin_read"], True)
            prompt_markers = [
                marker
                for marker in receipt["markers"]
                if marker["event"] == "user_prompt_submit"
            ]
            self.assertEqual(
                prompt_markers[0]["prompt_sha256"],
                hashlib.sha256(prompt_sentinel.encode()).hexdigest(),
            )
            self.assertNotIn(
                prompt_sentinel,
                json.dumps(receipt),
            )
            self.assertNotIn(transcript_sentinel, json.dumps(receipt))
            self.assertEqual(stat.S_IMODE(root.stat().st_mode), 0o700)
            for marker in root.iterdir():
                self.assertEqual(stat.S_IMODE(marker.stat().st_mode), 0o600)
                marker_bytes = marker.read_bytes()
                self.assertNotIn(prompt_sentinel.encode(), marker_bytes)
                self.assertNotIn(transcript_sentinel.encode(), marker_bytes)

    def test_native_hook_accepts_maximum_escaped_controller_prompt(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "markers"
            helper = (
                ROOT
                / "skills"
                / "herdr-puppet"
                / "scripts"
                / "claude_hook_marker.py"
            )
            implementation = (
                helper.parent
                / "herdr_puppet_lib"
                / "claude_hook_marker.py"
            )
            implementation_sha256 = hashlib.sha256(
                implementation.read_bytes()
            ).hexdigest()
            base = [
                sys.executable,
                str(helper),
                "record",
                "--root",
                str(root),
                "--run-id",
                "run-hook-max-prompt",
                "--probe-id",
                "9" * 64,
                "--implementation-sha256",
                implementation_sha256,
            ]
            started = subprocess.run(
                [*base, "--event", "session_start"],
                input="",
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(started.returncode, 0)
            prompt = "\n" * MAX_PROMPT_BYTES
            hook_input = json.dumps(
                {
                    "hook_event_name": "UserPromptSubmit",
                    "prompt": prompt,
                }
            )
            self.assertGreater(len(hook_input.encode("utf-8")), 512 * 1024)
            submitted = subprocess.run(
                [*base, "--event", "user_prompt_submit"],
                input=hook_input,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(submitted.returncode, 0)
            receipt = observe_claude_hooks(
                root_value=str(root),
                run_id="run-hook-max-prompt",
                probe_id="9" * 64,
            )
            prompt_marker = next(
                marker
                for marker in receipt["markers"]
                if marker["event"] == "user_prompt_submit"
            )
            self.assertEqual(
                prompt_marker["prompt_sha256"],
                hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
            )

    def test_native_hook_helper_bounds_events_and_rejects_residue(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "markers"
            record_claude_hook(
                root_value=str(root),
                run_id="run-hook-bounds",
                probe_id="b" * 64,
                event="session_start",
            )
            for prompt_sha256 in ("c" * 64, "d" * 64):
                record_claude_hook(
                    root_value=str(root),
                    run_id="run-hook-bounds",
                    probe_id="b" * 64,
                    event="user_prompt_submit",
                    prompt_sha256=prompt_sha256,
                )
            with self.assertRaises(ClaudeHookMarkerError):
                record_claude_hook(
                    root_value=str(root),
                    run_id="run-hook-bounds",
                    probe_id="b" * 64,
                    event="user_prompt_submit",
                    prompt_sha256="e" * 64,
                )
            (root / "unexpected.txt").write_text("residue", encoding="utf-8")
            with self.assertRaises(ClaudeHookMarkerError):
                observe_claude_hooks(
                    root_value=str(root),
                    run_id="run-hook-bounds",
                    probe_id="b" * 64,
                )
            helper = (
                ROOT
                / "skills"
                / "herdr-puppet"
                / "scripts"
                / "claude_hook_marker.py"
            )
            implementation = (
                helper.parent
                / "herdr_puppet_lib"
                / "claude_hook_marker.py"
            )
            implementation_sha256 = hashlib.sha256(
                implementation.read_bytes()
            ).hexdigest()
            failed_record = subprocess.run(
                [
                    sys.executable,
                    str(helper),
                    "record",
                    "--root",
                    str(root),
                    "--run-id",
                    "run-hook-bounds",
                    "--probe-id",
                    "b" * 64,
                    "--event",
                    "stop",
                    "--implementation-sha256",
                    implementation_sha256,
                ],
                input="PRIVATE-STOP-INPUT-MUST-REMAIN-UNREAD",
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(failed_record.returncode, 0)
            self.assertEqual(failed_record.stdout, "")
            self.assertEqual(failed_record.stderr, "")
            failed_prompt_record = subprocess.run(
                [
                    sys.executable,
                    str(helper),
                    "record",
                    "--root",
                    str(root),
                    "--run-id",
                    "run-hook-bounds",
                    "--probe-id",
                    "b" * 64,
                    "--event",
                    "user_prompt_submit",
                    "--implementation-sha256",
                    implementation_sha256,
                ],
                input="{malformed hook json",
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(failed_prompt_record.returncode, 0)
            self.assertEqual(failed_prompt_record.stdout, "")
            self.assertEqual(failed_prompt_record.stderr, "")
            failed_observe = subprocess.run(
                [
                    sys.executable,
                    str(helper),
                    "observe",
                    "--root",
                    str(root),
                    "--run-id",
                    "run-hook-bounds",
                    "--probe-id",
                    "b" * 64,
                    "--implementation-sha256",
                    implementation_sha256,
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(failed_observe.returncode, 2)
            self.assertEqual(failed_observe.stdout, "")
            self.assertEqual(failed_observe.stderr, "")

    def test_claude_binding_carries_source_bound_native_hooks(self) -> None:
        binding = sample_binding(
            harness="claude",
            run_id="run-claude-binding",
        )
        lifecycle = binding["lifecycle_observation"]
        self.assertEqual(
            lifecycle["strategy"],
            "claude_native_hook_markers",
        )
        argv = binding["regular_launch"]["argv"]
        self.assertEqual(argv[1:3], ["--dangerously-skip-permissions", "--settings"])
        settings = json.loads(argv[3])
        self.assertEqual(
            set(settings["hooks"]),
            {"SessionStart", "UserPromptSubmit", "Stop", "StopFailure"},
        )
        self.assertEqual(
            settings["hooks"]["SessionStart"][0]["matcher"],
            "startup",
        )
        self.assertNotIn(
            "matcher",
            settings["hooks"]["UserPromptSubmit"][0],
        )
        serialized = json.dumps(settings)
        self.assertIn(lifecycle["helper"]["path"], serialized)
        self.assertIn(lifecycle["probe_id"], serialized)
        self.assertNotIn("PRIVATE-PROMPT-MUST-NOT-PERSIST", serialized)

        forged = copy.deepcopy(binding)
        forged["lifecycle_observation"]["settings_sha256"] = "f" * 64
        forged["fingerprint"] = binding_fingerprint(forged)
        with self.assertRaises(HerdrPuppetError) as caught:
            validate_harness_binding(forged)
        self.assertEqual(
            caught.exception.code,
            "invalid_lifecycle_observation",
        )
        forged_helper = copy.deepcopy(binding)
        forged_helper["lifecycle_observation"]["helper"]["path"] = (
            "/tmp/unbound-claude-hook-marker.py"
        )
        forged_helper["fingerprint"] = binding_fingerprint(forged_helper)
        with self.assertRaises(HerdrPuppetError) as caught:
            validate_harness_binding(forged_helper)
        self.assertEqual(
            caught.exception.code,
            "invalid_lifecycle_observation",
        )

    def test_receipt_classifies_submission_completion_and_failure(self) -> None:
        binding = sample_binding(
            harness="claude",
            run_id="run-claude-receipts",
        )
        observation = binding["lifecycle_observation"]
        prompt_one = "a" * 64
        prompt_two = "b" * 64
        cases = [
            (
                "armed",
                claude_hook_receipt(binding),
                "armed",
                [],
            ),
            (
                "initial",
                claude_hook_receipt(binding),
                "submission_not_observed",
                [prompt_one],
            ),
            (
                "initial",
                claude_hook_receipt(
                    binding,
                    user_prompt_submit=1,
                    prompt_sha256s=[prompt_one],
                ),
                "response_pending",
                [prompt_one],
            ),
            (
                "initial",
                claude_hook_receipt(
                    binding,
                    user_prompt_submit=1,
                    stop=1,
                    prompt_sha256s=[prompt_one],
                ),
                "response_completed",
                [prompt_one],
            ),
            (
                "initial",
                claude_hook_receipt(
                    binding,
                    user_prompt_submit=1,
                    stop_failure=1,
                    prompt_sha256s=[prompt_one],
                ),
                "response_failed",
                [prompt_one],
            ),
            (
                "steering",
                claude_hook_receipt(
                    binding,
                    user_prompt_submit=1,
                    stop=1,
                    prompt_sha256s=[prompt_one],
                ),
                "submission_not_observed",
                [prompt_one, prompt_two],
            ),
            (
                "steering",
                claude_hook_receipt(
                    binding,
                    user_prompt_submit=2,
                    stop=1,
                    prompt_sha256s=[prompt_one, prompt_two],
                ),
                "response_pending",
                [prompt_one, prompt_two],
            ),
            (
                "steering",
                claude_hook_receipt(
                    binding,
                    user_prompt_submit=2,
                    stop=2,
                    prompt_sha256s=[prompt_one, prompt_two],
                ),
                "response_completed",
                [prompt_one, prompt_two],
            ),
            (
                "steering",
                claude_hook_receipt(
                    binding,
                    user_prompt_submit=2,
                    stop=1,
                    stop_failure=1,
                    prompt_sha256s=[prompt_one, prompt_two],
                ),
                "response_failed",
                [prompt_one, prompt_two],
            ),
        ]
        for phase, receipt, expected, expected_prompts in cases:
            with self.subTest(phase=phase, expected=expected):
                _checked, classification = validate_claude_hook_receipt(
                    receipt,
                    observation=observation,
                    phase=phase,
                    expected_prompt_sha256s=expected_prompts,
                )
                self.assertEqual(classification, expected)

    def test_receipt_rejects_wrong_identity_counts_ordinals_and_hashes(
        self,
    ) -> None:
        binding = sample_binding(
            harness="claude",
            run_id="run-claude-invalid-receipts",
        )
        observation = binding["lifecycle_observation"]
        cases: dict[str, tuple[dict[str, Any], str]] = {}
        wrong_run = claude_hook_receipt(binding)
        wrong_run["run_id"] = "run-wrong"
        cases["run"] = (wrong_run, "armed")
        wrong_probe = claude_hook_receipt(binding)
        wrong_probe["probe_id"] = "f" * 64
        cases["probe"] = (wrong_probe, "armed")
        wrong_counts = claude_hook_receipt(binding)
        wrong_counts["counts"]["session_start"] = 2
        cases["counts"] = (wrong_counts, "armed")
        boolean_counts = claude_hook_receipt(binding)
        boolean_counts["counts"] = {
            event: bool(count)
            for event, count in boolean_counts["counts"].items()
        }
        cases["boolean_counts"] = (boolean_counts, "armed")
        wrong_ordinal = claude_hook_receipt(binding)
        wrong_ordinal["markers"][0]["ordinal"] = 2
        cases["ordinal"] = (wrong_ordinal, "armed")
        wrong_hash = claude_hook_receipt(binding)
        wrong_hash["markers"][0]["sha256"] = "e" * 64
        cases["marker_hash"] = (wrong_hash, "armed")
        wrong_set_hash = claude_hook_receipt(binding)
        wrong_set_hash["marker_set_sha256"] = "d" * 64
        cases["marker_set_hash"] = (wrong_set_hash, "armed")
        for name, (receipt, phase) in cases.items():
            with self.subTest(name=name):
                with self.assertRaises(HerdrPuppetError) as caught:
                    validate_claude_hook_receipt(
                        receipt,
                        observation=observation,
                        phase=phase,
                        expected_prompt_sha256s=[],
                    )
                self.assertEqual(
                    caught.exception.code,
                    "invalid_claude_hook_receipt",
                )
        with self.assertRaises(HerdrPuppetError) as caught:
            validate_claude_hook_receipt(
                claude_hook_receipt(binding),
                observation=observation,
                phase="unknown",
                expected_prompt_sha256s=[],
            )
        self.assertEqual(
            caught.exception.code,
            "invalid_claude_lifecycle_phase",
        )

    def test_receipt_rejects_private_extra_fields_without_echo(self) -> None:
        binding = sample_binding(
            harness="claude",
            run_id="run-claude-private-extra",
        )
        observation = binding["lifecycle_observation"]
        for field in ("prompt", "transcript_path", "hook_input"):
            sentinel = f"PRIVATE-{field.upper()}-MUST-NOT-ECHO"
            receipt = claude_hook_receipt(binding)
            receipt[field] = sentinel
            with self.subTest(field=field):
                with self.assertRaises(HerdrPuppetError) as caught:
                    validate_claude_hook_receipt(
                        receipt,
                        observation=observation,
                        phase="armed",
                        expected_prompt_sha256s=[],
                    )
                self.assertEqual(
                    caught.exception.code,
                    "invalid_claude_hook_receipt",
                )
                self.assertNotIn(
                    sentinel,
                    json.dumps(caught.exception.as_json()),
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
        self.assertEqual(
            result["destination_selection"]["tab"],
            {"request": "fresh", "ordinal": 1},
        )

    def test_named_catalog_resolves_both_aiworker_profiles_and_sanitizes_receipt(
        self,
    ) -> None:
        catalog = load_destination_catalog(
            FIXTURES / "destination-catalog-ok.json"
        )
        for ordinal, machine in enumerate(
            ("aiworker-01", "aiworker-02"),
            start=1,
        ):
            with self.subTest(machine=machine):
                facts = fixture("plan-ok.json")
                facts["workspaces"] = [
                    {
                        "workspace_id": f"w{ordinal}",
                        "label": machine,
                        "tab_count": 0,
                        "pane_count": 0,
                    }
                ]
                result = plan(
                    FakeClient(),
                    session="operator-session",
                    machine=machine,
                    destination_catalog=catalog,
                    run_id=f"run-{machine}",
                    harness="agy",
                    repo="example/SaariusSkills",
                    worktree="/redacted/worktree",
                    proof_root="/redacted/proof",
                    harness_binding=sample_binding(),
                    tab_ordinal=ordinal,
                    facts=facts,
                )
                profile = catalog["profiles"][ordinal - 1]
                self.assertEqual(result["workspace"]["label"], machine)
                self.assertEqual(
                    result["expected_ssh_target"],
                    profile["ssh_target"],
                )
                receipt = plan_selection_receipt(result)
                serialized = json.dumps(receipt, sort_keys=True)
                self.assertEqual(
                    receipt["destination_selection"]["machine"],
                    machine,
                )
                self.assertEqual(
                    receipt["destination_selection"]["tab"],
                    {"request": "fresh", "ordinal": ordinal},
                )
                self.assertNotIn(profile["ssh_target"], serialized)
                self.assertNotIn("destination-catalog-ok.json", serialized)
                self.assertFalse(
                    receipt["destination_selection"]["ssh_target_retained"]
                )

    def test_destination_catalog_rejects_extra_duplicate_and_missing_profiles(
        self,
    ) -> None:
        base = fixture("destination-catalog-ok.json")
        invalid_catalogs = []
        extra = copy.deepcopy(base)
        extra["profiles"][0]["tab_id"] = "forbidden"
        invalid_catalogs.append(extra)
        duplicate = copy.deepcopy(base)
        duplicate["profiles"][1]["name"] = "aiworker-01"
        invalid_catalogs.append(duplicate)
        duplicate_label = copy.deepcopy(base)
        duplicate_label["profiles"][1]["workspace_label"] = (
            duplicate_label["profiles"][0]["workspace_label"]
        )
        invalid_catalogs.append(duplicate_label)
        missing = copy.deepcopy(base)
        del missing["profiles"][0]["ssh_target"]
        invalid_catalogs.append(missing)
        oversized_target = copy.deepcopy(base)
        oversized_target["profiles"][0]["ssh_target"] = "a" * 321
        invalid_catalogs.append(oversized_target)
        for catalog in invalid_catalogs:
            with self.subTest(catalog=catalog):
                with self.assertRaises(HerdrPuppetError) as caught:
                    validate_destination_catalog(catalog)
                self.assertEqual(
                    caught.exception.code,
                    "invalid_destination_catalog",
                )
        with tempfile.TemporaryDirectory() as directory:
            duplicate_json = Path(directory) / "catalog.json"
            duplicate_json.write_text(
                '{"schema":"herdr-puppet.destination-catalog.v1",'
                '"schema":"herdr-puppet.destination-catalog.v1",'
                '"profiles":[]}',
                encoding="utf-8",
            )
            with self.assertRaises(HerdrPuppetError) as caught:
                load_destination_catalog(duplicate_json)
            self.assertEqual(
                caught.exception.code,
                "invalid_destination_catalog",
            )
            symlink = Path(directory) / "catalog-link.json"
            symlink.symlink_to(FIXTURES / "destination-catalog-ok.json")
            with self.assertRaises(HerdrPuppetError) as unsafe:
                load_destination_catalog(symlink)
            self.assertEqual(
                unsafe.exception.code,
                "invalid_destination_catalog",
            )

    def test_named_destination_rejects_wrong_workspace_and_legacy_mix(self) -> None:
        catalog = fixture("destination-catalog-ok.json")
        for machine in ("aiworker-01", "aiworker-02"):
            with self.subTest(machine=machine):
                with self.assertRaises(HerdrPuppetError) as wrong_workspace:
                    plan(
                        FakeClient(),
                        session="operator-session",
                        machine=machine,
                        destination_catalog=catalog,
                        run_id=f"run-wrong-{machine}",
                        harness="agy",
                        repo="example/SaariusSkills",
                        worktree="/redacted/worktree",
                        proof_root="/redacted/proof",
                        harness_binding=sample_binding(),
                        facts=fixture("plan-ok.json"),
                    )
                self.assertEqual(
                    wrong_workspace.exception.code,
                    "workspace_capability_mismatch",
                )
        with self.assertRaises(HerdrPuppetError) as mixed:
            plan(
                FakeClient(),
                session="operator-session",
                machine="aiworker-02",
                destination_catalog=catalog,
                workspace_id="w2",
                workspace_label="worker-02",
                expected_ssh_target="worker@worker-02.example",
                run_id="run-mixed-destination",
                harness="agy",
                repo="example/SaariusSkills",
                worktree="/redacted/worktree",
                proof_root="/redacted/proof",
                harness_binding=sample_binding(),
            )
        self.assertEqual(mixed.exception.code, "destination_route_conflict")

    def test_destination_receipt_rejects_non_fresh_tab_and_unsafe_machine(
        self,
    ) -> None:
        facts = fixture("plan-ok.json")
        facts["workspaces"] = [
            {
                "workspace_id": "w-ai2",
                "label": "aiworker-02",
                "tab_count": 0,
                "pane_count": 0,
            }
        ]
        valid = plan(
            FakeClient(),
            session="operator-session",
            machine="aiworker-02",
            destination_catalog=fixture("destination-catalog-ok.json"),
            run_id="run-receipt-negative",
            harness="agy",
            repo="example/SaariusSkills",
            worktree="/redacted/worktree",
            proof_root="/redacted/proof",
            harness_binding=sample_binding(),
            facts=facts,
        )
        non_fresh = copy.deepcopy(valid)
        non_fresh["destination_selection"]["tab"]["request"] = "existing"
        unsafe_machine = copy.deepcopy(valid)
        unsafe_machine["destination_selection"]["machine"] = "aiworker-02\nraw"
        for payload in (non_fresh, unsafe_machine):
            with self.subTest(payload=payload["destination_selection"]):
                with self.assertRaises(HerdrPuppetError) as caught:
                    plan_selection_receipt(payload)
                self.assertEqual(
                    caught.exception.code,
                    "invalid_destination_selection",
                )

    def test_tab_ordinal_alias_is_deprecated_and_mutually_exclusive(self) -> None:
        aliased = plan(
            FakeClient(),
            session="operator-session",
            workspace_id="w2",
            workspace_label="worker-02",
            expected_ssh_target="worker@worker-02.example",
            run_id="run-alias",
            harness="agy",
            repo="example/SaariusSkills",
            worktree="/redacted/worktree",
            proof_root="/redacted/proof",
            harness_binding=sample_binding(),
            ordinal=2,
        )
        self.assertTrue(
            aliased["destination_selection"]["legacy_ordinal_alias"]
        )
        self.assertEqual(
            aliased["destination_selection"]["tab"]["ordinal"],
            2,
        )
        with self.assertRaises(HerdrPuppetError) as conflict:
            plan(
                FakeClient(),
                session="operator-session",
                workspace_id="w2",
                workspace_label="worker-02",
                expected_ssh_target="worker@worker-02.example",
                run_id="run-alias-conflict",
                harness="agy",
                repo="example/SaariusSkills",
                worktree="/redacted/worktree",
                proof_root="/redacted/proof",
                harness_binding=sample_binding(),
                tab_ordinal=2,
                ordinal=2,
            )
        self.assertEqual(
            conflict.exception.code,
            "destination_ordinal_conflict",
        )

    def test_plan_cli_exposes_named_route_and_deprecated_ordinal_alias(self) -> None:
        parser = build_parser()
        common = [
            "--session",
            "operator-session",
            "--run-id",
            "run-cli-destination",
            "--harness",
            "agy",
            "--repo",
            "example/SaariusSkills",
            "--worktree",
            "/worktree",
            "--proof-root",
            "/proof",
            "--harness-binding-json",
            "binding.json",
            "--output",
            "plan.json",
        ]
        named = parser.parse_args(
            [
                "plan",
                "--machine",
                "aiworker-02",
                "--destination-catalog-json",
                "catalog.json",
                "--tab-ordinal",
                "2",
                *common,
            ]
        )
        self.assertEqual(named.machine, "aiworker-02")
        self.assertEqual(named.tab_ordinal, 2)
        legacy = parser.parse_args(
            [
                "plan",
                "--workspace-id",
                "w2",
                "--workspace-label",
                "worker-02",
                "--expected-ssh-target",
                "worker@worker-02.example",
                "--ordinal",
                "3",
                *common,
            ]
        )
        self.assertEqual(legacy.ordinal, 3)
        for invalid in (
            [
                "plan",
                "--machine",
                "aiworker-02",
                "--workspace-id",
                "w2",
                *common,
            ],
            [
                "plan",
                "--machine",
                "aiworker-02",
                "--tab-ordinal",
                "2",
                "--ordinal",
                "2",
                *common,
            ],
        ):
            with self.subTest(argv=invalid):
                with mock.patch("sys.stderr", new=io.StringIO()):
                    with self.assertRaises(SystemExit):
                        parser.parse_args(invalid)

    def test_plan_cli_writes_private_plan_and_returns_sanitized_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binding_path = root / "binding.json"
            facts_path = root / "facts.json"
            output_path = root / "plan.json"
            binding_path.write_text(
                json.dumps(sample_binding()),
                encoding="utf-8",
            )
            facts = fixture("plan-ok.json")
            facts["workspaces"] = [
                {
                    "workspace_id": "w-ai2",
                    "label": "aiworker-02",
                    "tab_count": 0,
                    "pane_count": 0,
                }
            ]
            facts_path.write_text(json.dumps(facts), encoding="utf-8")
            args = build_parser().parse_args(
                [
                    "plan",
                    "--session",
                    "operator-session",
                    "--machine",
                    "aiworker-02",
                    "--destination-catalog-json",
                    str(FIXTURES / "destination-catalog-ok.json"),
                    "--tab-ordinal",
                    "2",
                    "--run-id",
                    "run-cli-private-plan",
                    "--harness",
                    "agy",
                    "--repo",
                    "example/SaariusSkills",
                    "--worktree",
                    "/redacted/worktree",
                    "--proof-root",
                    "/redacted/proof",
                    "--harness-binding-json",
                    str(binding_path),
                    "--facts-json",
                    str(facts_path),
                    "--output",
                    str(output_path),
                ]
            )
            receipt = herdr_cli.run(args)
            original_plan_bytes = output_path.read_bytes()
            private_plan = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(stat.S_IMODE(output_path.stat().st_mode), 0o600)
            self.assertEqual(
                private_plan["expected_ssh_target"],
                "worker@aiworker-02.example",
            )
            serialized = json.dumps(receipt, sort_keys=True)
            self.assertNotIn("worker@aiworker-02.example", serialized)
            self.assertNotIn("destination-catalog-ok.json", serialized)
            self.assertEqual(
                receipt["destination_selection"]["machine"],
                "aiworker-02",
            )
            self.assertTrue(receipt["fresh_tab_required"])
            with self.assertRaises(HerdrPuppetError) as replay:
                herdr_cli.run(args)
            self.assertEqual(replay.exception.code, "plan_output_exists")
            self.assertEqual(output_path.read_bytes(), original_plan_bytes)

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

    def test_plan_rejects_claude_lifecycle_run_mismatch(self) -> None:
        binding = sample_binding(
            harness="claude",
            run_id="run-bound-claude",
        )
        with self.assertRaises(HerdrPuppetError) as caught:
            plan(
                FakeClient(),
                session="operator-session",
                workspace_id="w2",
                workspace_label="worker-02",
                expected_ssh_target="worker@worker-02.example",
                run_id="run-different-claude",
                harness="claude",
                repo="example/SaariusSkills",
                worktree="/redacted/worktree",
                proof_root="/redacted/proof",
                harness_binding=binding,
                facts=fixture("plan-ok.json"),
            )
        self.assertEqual(
            caught.exception.code,
            "claude_lifecycle_run_mismatch",
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
                "--run-root",
                "run",
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
                "--run-root",
                "run",
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
                "--run-root",
                "run",
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
            hook_parent = root / "claude-hook-runs"
            hook_parent.mkdir()
            cursor_status_marker = root / "cursor-status-was-called"
            executable_body = """#!/bin/sh
case "$1" in
  --version) echo "fake 1.0.0" ;;
  --help) echo "fake help --settings --model" ;;
  login) echo "Logged in using ChatGPT" ;;
  auth) echo '{"loggedIn":true}' ;;
  status) echo '{"loggedIn":true}' ;;
  models) printf '%s\t%s\n' 'gemini-3.7-flash-high' 'private inventory description' ;;
  *) exit 2 ;;
esac
"""
            for command in commands.values():
                executable = binary_root / command
                executable.write_text(executable_body, encoding="utf-8")
                executable.chmod(0o755)
            cursor_executable = binary_root / commands["cursor"]
            cursor_executable.write_text(
                f"""#!/bin/sh
case "$1" in
  --version) echo "fake 1.0.0" ;;
  --help) echo "fake help" ;;
  status) : > "{cursor_status_marker}"; exit 99 ;;
  *) exit 2 ;;
esac
""",
                encoding="utf-8",
            )
            cursor_executable.chmod(0o755)
            environment = dict(os.environ)
            environment["PATH"] = (
                str(binary_root)
                + os.pathsep
                + environment.get("PATH", "")
            )
            for harness, command in commands.items():
                with self.subTest(harness=harness):
                    census_command = [
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
                        str(ROOT if harness == "claude" else worktree),
                    ]
                    if harness == "claude":
                        census_command.extend(
                            [
                                "--run-id",
                                "run-census-claude",
                                "--claude-hook-root",
                                str(hook_parent / "run-census-claude"),
                            ]
                        )
                    if harness == "agy":
                        census_command.extend(
                            ["--model", AGY_REQUIRED_MODEL]
                        )
                    completed = subprocess.run(
                        census_command,
                        check=False,
                        capture_output=True,
                        text=True,
                        env=environment,
                    )
                    self.assertEqual(completed.returncode, 0, completed.stderr)
                    payload = json.loads(completed.stdout)
                    validated = validate_remote_census(payload)
                    self.assertEqual(payload["harness"], harness)
                    self.assertEqual(validated, payload)
                    self.assertEqual(
                        payload["executable"]["command"],
                        command,
                    )
                    self.assertEqual(
                        payload["profile"]["enrollment_state"],
                        "interactive_pending" if harness == "cursor" else "enrolled",
                    )
                    self.assertIs(
                        payload["profile"]["status_exit"],
                        None if harness == "cursor" else 0,
                    )
                    self.assertFalse(payload["raw_output_retained"])
                    self.assertNotIn(
                        "private inventory description",
                        completed.stdout,
                    )
                    census_schema = json.loads(
                        (
                            ROOT
                            / "skills"
                            / "herdr-puppet"
                            / "references"
                            / "remote-harness-census.schema.json"
                        ).read_text(encoding="utf-8")
                    )
                    self.assertEqual(
                        payload["schema"],
                        census_schema["properties"]["schema"]["const"],
                    )
                    self.assertIsNotNone(
                        re.fullmatch(
                            census_schema["properties"]["host"]["pattern"],
                            payload["host"],
                        )
                    )
            self.assertFalse(cursor_status_marker.exists())
            row_census = root / "row-census.json"
            row_nonce = "CENSUS-STATUS-0730-A1"
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
            cursor_row_census = root / "cursor-row-census.json"
            cursor_row_nonce = "CURSOR-CENSUS-0730-A1"
            cursor_row_completed = subprocess.run(
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
                    "cursor",
                    "--host",
                    "worker.example",
                    "--profile-root",
                    str(profile_root),
                    "--worktree",
                    str(worktree),
                    "--output",
                    str(cursor_row_census),
                    "--checkpoint-nonce",
                    cursor_row_nonce,
                ],
                check=False,
                capture_output=True,
                text=True,
                env=environment,
            )
            self.assertEqual(
                cursor_row_completed.returncode,
                0,
                cursor_row_completed.stderr,
            )
            self.assertEqual(
                cursor_row_completed.stdout,
                f"HERDR_PUPPET_STATUS {cursor_row_nonce}\n",
            )
            self.assertEqual(
                json.loads(cursor_row_census.read_text(encoding="utf-8"))[
                    "profile"
                ],
                {
                    "enrollment_state": "interactive_pending",
                    "isolation": "dedicated_remote_user",
                    "raw_output_retained": False,
                    "root": str(profile_root.resolve()),
                    "route": "dedicated_os_user_profile",
                    "status_exit": None,
                },
            )
            self.assertFalse(cursor_status_marker.exists())
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

    def test_remote_census_rejects_unsafe_host_before_probe_or_output(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binary_root = root / "bin"
            profile_root = root / "profile"
            worktree = root / "worktree"
            marker = root / "executable-was-probed"
            binary_root.mkdir()
            profile_root.mkdir()
            worktree.mkdir()
            executable = binary_root / "codex"
            executable.write_text(
                "#!/bin/sh\n"
                f": > {str(marker)!r}\n"
                "case \"$1\" in\n"
                "  --version) echo 'fake 1.0.0' ;;\n"
                "  --help) echo 'fake help' ;;\n"
                "  login) echo 'Logged in using ChatGPT' ;;\n"
                "  *) exit 2 ;;\n"
                "esac\n",
                encoding="utf-8",
            )
            executable.chmod(0o755)
            environment = dict(os.environ)
            environment["PATH"] = (
                str(binary_root)
                + os.pathsep
                + environment.get("PATH", "")
            )
            census_script = str(
                ROOT
                / "skills"
                / "herdr-puppet"
                / "scripts"
                / "harness_census.py"
            )
            for index, host in enumerate(
                ("", "worker host", "worker\nhost", "worker;host"),
                start=1,
            ):
                output = root / f"unsafe-{index}.json"
                completed = subprocess.run(
                    [
                        sys.executable,
                        census_script,
                        "--harness",
                        "codex",
                        "--host",
                        host,
                        "--profile-root",
                        str(profile_root),
                        "--worktree",
                        str(worktree),
                        "--output",
                        str(output),
                        "--checkpoint-nonce",
                        f"UNSAFE-HOST-{index:02d}",
                    ],
                    check=False,
                    capture_output=True,
                    text=True,
                    env=environment,
                )
                with self.subTest(host=host):
                    self.assertNotEqual(completed.returncode, 0)
                    self.assertIn(
                        "host must be one bounded safe identifier",
                        completed.stderr,
                    )
                    self.assertEqual(completed.stdout, "")
                    self.assertFalse(output.exists())
                    self.assertFalse(marker.exists())

    def test_remote_census_non_enrolled_emits_no_invalid_v3_record(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binary_root = root / "bin"
            profile_root = root / "profile"
            worktree = root / "worktree"
            binary_root.mkdir()
            profile_root.mkdir()
            worktree.mkdir()
            executable = binary_root / "codex"
            executable.write_text(
                "#!/bin/sh\n"
                "case \"$1\" in\n"
                "  --version) echo 'fake 1.0.0' ;;\n"
                "  --help) echo 'fake help' ;;\n"
                "  login) echo 'private enrollment response'; exit 7 ;;\n"
                "  *) exit 2 ;;\n"
                "esac\n",
                encoding="utf-8",
            )
            executable.chmod(0o755)
            environment = dict(os.environ)
            environment["PATH"] = (
                str(binary_root)
                + os.pathsep
                + environment.get("PATH", "")
            )
            output = root / "must-not-exist.json"
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
                    "codex",
                    "--host",
                    "worker.example",
                    "--profile-root",
                    str(profile_root),
                    "--worktree",
                    str(worktree),
                    "--output",
                    str(output),
                    "--checkpoint-nonce",
                    "UNENROLLED-CENSUS-01",
                ],
                check=False,
                capture_output=True,
                text=True,
                env=environment,
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn(
                "no active v3 census was emitted",
                completed.stderr,
            )
            self.assertNotIn(
                "private enrollment response",
                completed.stdout + completed.stderr,
            )
            self.assertEqual(completed.stdout, "")
            self.assertFalse(output.exists())

    def test_agy_census_requires_exact_model_help_and_first_tsv_cell(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binary_root = root / "bin"
            profile_root = root / "profile"
            worktree = root / "worktree"
            binary_root.mkdir()
            profile_root.mkdir()
            worktree.mkdir()
            executable = binary_root / "agy"
            environment = dict(os.environ)
            environment["PATH"] = (
                str(binary_root)
                + os.pathsep
                + environment.get("PATH", "")
            )
            census_script = str(
                ROOT
                / "skills"
                / "herdr-puppet"
                / "scripts"
                / "harness_census.py"
            )

            def run_case(
                *,
                help_text: str,
                models_body: str,
                model: str | None = AGY_REQUIRED_MODEL,
            ) -> subprocess.CompletedProcess[str]:
                executable.write_text(
                    "#!/bin/sh\n"
                    "case \"$1\" in\n"
                    "  --version) echo 'agy test 1.0' ;;\n"
                    f"  --help) printf '%s\\n' {help_text!r} ;;\n"
                    f"  models) {models_body} ;;\n"
                    "  *) exit 2 ;;\n"
                    "esac\n",
                    encoding="utf-8",
                )
                executable.chmod(0o755)
                command = [
                    sys.executable,
                    census_script,
                    "--harness",
                    "agy",
                    "--host",
                    "worker.example",
                    "--profile-root",
                    str(profile_root),
                    "--worktree",
                    str(worktree),
                ]
                if model is not None:
                    command.extend(["--model", model])
                return subprocess.run(
                    command,
                    check=False,
                    capture_output=True,
                    text=True,
                    env=environment,
                )

            success = run_case(
                help_text="usage: agy --model MODEL",
                models_body=(
                    "printf '%s\\t%s\\n' "
                    "'gemini-3.7-flash-high' 'private listing body'"
                ),
            )
            self.assertEqual(success.returncode, 0, success.stderr)
            payload = json.loads(success.stdout)
            self.assertEqual(
                payload["regular_launch"]["argv"],
                [
                    str(executable.resolve()),
                    "--model",
                    "gemini-3.7-flash-high",
                    "--dangerously-skip-permissions",
                    "--sandbox=false",
                    "--new-project",
                    "--log-file",
                    "/dev/null",
                ],
            )
            self.assertEqual(
                payload["model_observation"],
                {
                    "selection": "explicit",
                    "model": "gemini-3.7-flash-high",
                    "effort": "high",
                },
            )
            self.assertNotIn("private listing body", success.stdout)

            failures = {
                "missing": run_case(
                    help_text="usage: agy --model MODEL",
                    models_body="printf '%s\\t%s\\n' 'gemini-3.7-flash-high' 'private'",
                    model=None,
                ),
                "default": run_case(
                    help_text="usage: agy --model MODEL",
                    models_body="printf '%s\\t%s\\n' 'gemini-3.7-flash-high' 'private'",
                    model="default",
                ),
                "help-token": run_case(
                    help_text="usage: agy --models MODEL",
                    models_body="printf '%s\\t%s\\n' 'gemini-3.7-flash-high' 'private'",
                ),
                "wrong-cell": run_case(
                    help_text="usage: agy --model MODEL",
                    models_body="printf '%s\\t%s\\n' 'alias' 'gemini-3.7-flash-high private'",
                ),
                "non-exact-cell": run_case(
                    help_text="usage: agy --model MODEL",
                    models_body="printf ' gemini-3.7-flash-high\\tprivate\\n'",
                ),
                "ambiguous": run_case(
                    help_text="usage: agy --model MODEL",
                    models_body=(
                        "printf '%s\\t%s\\n%s\\t%s\\n' "
                        "'gemini-3.7-flash-high' 'private one' "
                        "'gemini-3.7-flash-high' 'private two'"
                    ),
                ),
                "unavailable": run_case(
                    help_text="usage: agy --model MODEL",
                    models_body="exit 7",
                ),
            }
            for label, completed in failures.items():
                with self.subTest(label=label):
                    self.assertNotEqual(completed.returncode, 0)
                    combined = completed.stdout + completed.stderr
                    self.assertNotIn("private", combined)
                    self.assertNotIn("private one", combined)
                    self.assertNotIn("private two", combined)
            non_agy = subprocess.run(
                [
                    sys.executable,
                    census_script,
                    "--harness",
                    "codex",
                    "--host",
                    "worker.example",
                    "--profile-root",
                    str(profile_root),
                    "--worktree",
                    str(worktree),
                    "--model",
                    AGY_REQUIRED_MODEL,
                ],
                check=False,
                capture_output=True,
                text=True,
                env=environment,
            )
            self.assertNotEqual(non_agy.returncode, 0)
            self.assertIn("valid only for the AGY harness", non_agy.stderr)
            non_agy_empty = subprocess.run(
                [
                    sys.executable,
                    census_script,
                    "--harness",
                    "codex",
                    "--host",
                    "worker.example",
                    "--profile-root",
                    str(profile_root),
                    "--worktree",
                    str(worktree),
                    "--model",
                    "",
                ],
                check=False,
                capture_output=True,
                text=True,
                env=environment,
            )
            self.assertNotEqual(non_agy_empty.returncode, 0)
            self.assertIn(
                "valid only for the AGY harness",
                non_agy_empty.stderr,
            )
            self.assertNotIn("executable not found", non_agy_empty.stderr)

    def test_remote_census_enforces_claude_lifecycle_arguments_and_settings(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binary_root = root / "bin"
            profile_root = root / "profile"
            hook_parent = root / "hooks"
            binary_root.mkdir()
            profile_root.mkdir()
            hook_parent.mkdir()
            claude = binary_root / "claude"
            claude.write_text(
                "#!/bin/sh\n"
                "case \"$1\" in\n"
                "  --version) echo 'fake 1.0.0' ;;\n"
                "  --help) echo 'fake help with --settings-file only' ;;\n"
                "  auth) echo '{\"loggedIn\":true}' ;;\n"
                "  *) exit 2 ;;\n"
                "esac\n",
                encoding="utf-8",
            )
            claude.chmod(0o755)
            codex = binary_root / "codex"
            codex.write_text(
                "#!/bin/sh\n"
                "case \"$1\" in\n"
                "  --version) echo 'fake 1.0.0' ;;\n"
                "  --help) echo 'fake help' ;;\n"
                "  login) echo 'Logged in using ChatGPT' ;;\n"
                "  *) exit 2 ;;\n"
                "esac\n",
                encoding="utf-8",
            )
            codex.chmod(0o755)
            environment = dict(os.environ)
            environment["PATH"] = (
                str(binary_root)
                + os.pathsep
                + environment.get("PATH", "")
            )
            census_script = str(
                ROOT
                / "skills"
                / "herdr-puppet"
                / "scripts"
                / "harness_census.py"
            )
            common = [
                "--host",
                "worker.example",
                "--profile-root",
                str(profile_root),
                "--worktree",
                str(ROOT),
            ]
            missing_lifecycle = subprocess.run(
                [
                    sys.executable,
                    census_script,
                    "--harness",
                    "claude",
                    *common,
                ],
                check=False,
                capture_output=True,
                text=True,
                env=environment,
            )
            self.assertNotEqual(missing_lifecycle.returncode, 0)
            non_claude_lifecycle = subprocess.run(
                [
                    sys.executable,
                    census_script,
                    "--harness",
                    "codex",
                    *common,
                    "--run-id",
                    "run-census-invalid",
                    "--claude-hook-root",
                    str(hook_parent / "non-claude"),
                ],
                check=False,
                capture_output=True,
                text=True,
                env=environment,
            )
            self.assertNotEqual(non_claude_lifecycle.returncode, 0)
            missing_settings = subprocess.run(
                [
                    sys.executable,
                    census_script,
                    "--harness",
                    "claude",
                    *common,
                    "--run-id",
                    "run-census-no-settings",
                    "--claude-hook-root",
                    str(hook_parent / "run-census-no-settings"),
                ],
                check=False,
                capture_output=True,
                text=True,
                env=environment,
            )
            self.assertNotEqual(missing_settings.returncode, 0)
            self.assertIn(
                "does not advertise --settings",
                missing_settings.stderr,
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

    def test_input_uses_double_enter_submit_keys_for_multiline_submit(self) -> None:
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
            "line one\nline two",
            keys=["enter", "enter"],
        )
        thread.join(timeout=1)
        self.assertEqual(result, {"type": "ok"})
        self.assertEqual(observed["request"]["method"], "pane.send_input")
        self.assertEqual(
            observed["request"]["params"],
            {
                "pane_id": "w2:p1",
                "text": "line one\nline two",
                "keys": ["enter", "enter"],
            },
        )

    def test_input_rejects_invalid_submit_key_vector_before_socket_access(self) -> None:
        client = HerdrClient()
        with self.assertRaises(HerdrPuppetError) as caught:
            client.run_input(
                "/does/not/exist.sock",
                "w2:p1",
                "bounded prompt",
                keys=["up", "down"],
            )
        self.assertEqual(caught.exception.code, "submit_key_vector_invalid")

    def test_input_keeps_key_only_startup_gate_vector(self) -> None:
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
            "",
            keys=["a", "enter"],
        )
        thread.join(timeout=1)
        self.assertEqual(result, {"type": "ok"})
        self.assertEqual(
            observed["request"]["params"],
            {
                "pane_id": "w2:p1",
                "text": "",
                "keys": ["a", "enter"],
            },
        )

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
        refresh_selected_authority(self.plan)
        self.lease_path = self.root / "lease.json"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def create_lease(self) -> dict[str, Any]:
        run_root = self.default_run_root()
        created_journal = not run_root.exists()
        if created_journal:
            initialize_journal(run_root, self.plan)
        try:
            return create_qualification_tab(
                self.client,
                plan_payload=self.plan,
                lease_path=self.lease_path,
                allow_live=True,
                run_root=run_root,
                settle_seconds=0.1,
            )
        finally:
            if created_journal:
                shutil.rmtree(run_root)

    def persist_lease(self, lease: dict[str, Any]) -> dict[str, Any]:
        self.lease_path.write_text(
            json.dumps(lease),
            encoding="utf-8",
        )
        return lease

    def default_run_root(self) -> Path:
        return self.root / "run"

    def initialize_default_journal(self) -> Path:
        run_root = self.default_run_root()
        if not run_root.exists():
            initialize_journal(run_root, self.plan)
        return run_root

    def wrapped_initial(
        self,
        lease: dict[str, Any],
        task: str = "bounded qualification task",
    ) -> tuple[str, dict[str, Any]]:
        rendered, manifest = compile_instruction_wrapper(
            binding_value=lease["harness_binding"],
            run_id=lease["run_id"],
            task=task,
        )
        return rendered.decode("utf-8"), manifest

    def mark_harness_ready(self, lease: dict[str, Any]) -> dict[str, Any]:
        ready = (
            copy.deepcopy(lease)
            if "harness_launch" in lease
            else self.mark_harness_launched(lease)
        )
        ready["harness_readiness"] = "operator_verified"
        ready["harness_readiness_evidence"] = "operator_observed_ready_input"
        ready["harness_readiness_operator"] = "test-operator"
        ready["harness_readiness_verified_at"] = "2026-07-26T00:00:00Z"
        return self.persist_lease(ready)

    def _ready_lease_for_harness(
        self,
        harness: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        run_id = f"run-ready-{harness}"
        harness_binding = sample_binding(harness=harness, run_id=run_id)
        bound_plan = plan(
            self.client,
            session="operator-session",
            workspace_id="w2",
            workspace_label="worker-02",
            expected_ssh_target="worker@worker-02.example",
            run_id=run_id,
            harness=harness,
            repo="example/SaariusSkills",
            worktree="/redacted/worktree",
            proof_root=str((self.root / "run").resolve()),
            harness_binding=harness_binding,
            live_mutation_authorized=True,
        )
        run_root = self.root / "run"
        initialize_journal(run_root, bound_plan)
        try:
            bound_lease = create_qualification_tab(
                self.client,
                plan_payload=bound_plan,
                lease_path=self.lease_path,
                allow_live=True,
                run_root=run_root,
                settle_seconds=0.1,
            )
        finally:
            shutil.rmtree(run_root)
        return self.mark_harness_ready(bound_lease), bound_plan

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

    def register_claude_marker_files(
        self,
        lease: dict[str, Any],
        run_root: Path,
    ) -> dict[str, Any]:
        marker_root = lease["harness_binding"]["lifecycle_observation"][
            "marker_root"
        ]
        current = lease
        for marker_name in CLAUDE_MARKER_NAMES:
            register_remote_task_file(
                lease_payload=current,
                lease_path=self.lease_path,
                remote_path=f"{marker_root}/{marker_name}",
                source_repo=current["source"]["repo"],
                source_worktree=current["source"]["worktree"],
                confirm_caller_owned=True,
                run_root=run_root,
            )
            current = load_json(self.lease_path)
        return current

    def verify_in_row_census(
        self,
        lease: dict[str, Any],
        run_root: Path,
    ) -> dict[str, Any]:
        result = qualification_harness_census_verify(
            lease_payload=lease,
            lease_path=self.lease_path,
            census=sample_census_from_binding(lease["harness_binding"]),
            run_root=run_root,
        )
        self.assertEqual(result["result"], "ok")
        return load_json(self.lease_path)

    def submit_for_beacon(self, lease: dict[str, Any]) -> dict[str, Any]:
        run_root = self.initialize_default_journal()
        qualification_run(
            self.client,
            lease_payload=lease,
            lease_path=self.lease_path,
            seq=lease["next_seq"],
            command=(
                "printf '%s\\n' "
                "'HERDR_PUPPET_STATUS BEACON-SUBMISSION-1'"
            ),
            allow_live=True,
            run_root=run_root,
        )
        return json.loads(self.lease_path.read_text(encoding="utf-8"))

    def ready_codex_submission(
        self,
    ) -> tuple[dict[str, Any], Path]:
        lease, bound_plan = self._ready_lease_for_harness("codex")
        run_root = self.root / "run"
        initialize_journal(run_root, bound_plan)
        initial_text, manifest = self.wrapped_initial(
            lease,
            "bounded prompt",
        )
        qualification_send(
            self.client,
            lease_payload=lease,
            lease_path=self.lease_path,
            seq=lease["next_seq"],
            text=initial_text,
            instruction_manifest=manifest,
            allow_live=True,
            run_root=run_root,
        )
        return load_json(self.lease_path), run_root

    def assert_ready_codex_checkpoint_miss(
        self,
        rendered_line: str,
    ) -> None:
        lease, run_root = self.ready_codex_submission()
        self.client.read_payload = rendered_line
        result = qualification_beacon_wait(
            self.client,
            lease_payload=lease,
            lease_path=self.lease_path,
            nonce="CHECKPOINT-88",
            allow_live=True,
            lines=20,
            timeout_ms=1,
            run_root=run_root,
        )
        self.assertEqual(result["result"], "not_matched")
        self.assertIsNone(result["checkpoint"])

    def test_create_tab_requires_both_live_gates(self) -> None:
        blocked_plan = make_plan(self.client, live_mutation_authorized=False)
        with self.assertRaisesRegex(HerdrPuppetError, "Both the plan capability"):
            create_qualification_tab(
                self.client,
                plan_payload=blocked_plan,
                lease_path=self.lease_path,
                allow_live=True,
                run_root=self.root / "not-used",
            )
        with self.assertRaisesRegex(HerdrPuppetError, "Both the plan capability"):
            create_qualification_tab(
                self.client,
                plan_payload=self.plan,
                lease_path=self.lease_path,
                allow_live=False,
                run_root=self.root / "not-used",
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

    def test_named_destination_and_agy_model_freeze_into_plan_lease_and_journal(
        self,
    ) -> None:
        client = FakeClient()
        client.workspace_rows = [
            {"workspace_id": "w-ai2", "label": "aiworker-02"}
        ]
        run_root = self.root / "named-run"
        plan_payload = plan(
            client,
            session="operator-session",
            machine="aiworker-02",
            destination_catalog=fixture("destination-catalog-ok.json"),
            run_id="run-named-aiworker-02",
            harness="agy",
            repo="example/SaariusSkills",
            worktree="/redacted/worktree",
            proof_root=str(run_root.resolve()),
            harness_binding=sample_binding(),
            tab_ordinal=2,
            live_mutation_authorized=True,
        )
        initialize_journal(run_root, plan_payload)
        lease_path = self.root / "named-lease.json"
        lease = create_qualification_tab(
            client,
            plan_payload=plan_payload,
            lease_path=lease_path,
            allow_live=True,
            settle_seconds=0.1,
            run_root=run_root,
        )
        expected_selection = {
            "schema": "herdr-puppet.destination-selection-receipt.v1",
            "mode": "named_catalog",
            "machine": "aiworker-02",
            "workspace_label": "aiworker-02",
            "tab": {"request": "fresh", "ordinal": 2},
            "legacy_ordinal_alias": False,
            "catalog_path_retained": False,
            "ssh_target_retained": False,
            "existing_tab_adoption": False,
        }
        expected_model = {
            "selection": "explicit",
            "model": "gemini-3.7-flash-high",
            "effort": "high",
        }
        self.assertEqual(plan_payload["destination_selection"], expected_selection)
        self.assertEqual(lease["destination_selection"], expected_selection)
        self.assertEqual(
            plan_payload["harness_binding"]["model_observation"],
            expected_model,
        )
        self.assertEqual(
            lease["harness_binding"]["model_observation"],
            expected_model,
        )
        events = read_events(run_root)
        for event in events:
            data = event.get("data") or {}
            if "destination_selection" in data:
                self.assertEqual(
                    data["destination_selection"],
                    expected_selection,
                )
            if "model_selection" in data:
                self.assertEqual(data["model_selection"], expected_model)
        serialized_events = json.dumps(events, sort_keys=True)
        self.assertNotIn("worker@aiworker-02.example", serialized_events)
        self.assertNotIn("destination-catalog-ok.json", serialized_events)
        refresh_state(run_root, lease)
        state = (run_root / "STATE.md").read_text(encoding="utf-8")
        self.assertIn("machine: `aiworker-02`", state)
        self.assertIn("workspace_label: `aiworker-02`", state)
        self.assertIn("tab_ordinal: `2`", state)
        self.assertIn("model: `gemini-3.7-flash-high`", state)
        self.assertNotIn("worker@aiworker-02.example", state)
        tab_event = next(
            event
            for event in events
            if event["kind"] == "qualification.tab-created"
        )
        self.assertTrue(tab_event["data"]["fresh_tab_created"])

    def test_create_tab_rolls_back_exact_unqualified_candidate(self) -> None:
        run_root = self.root / "run"
        wrong_target = copy.deepcopy(self.plan)
        wrong_target["expected_ssh_target"] = "worker@wrong.example"
        refresh_selected_authority(wrong_target)
        initialize_journal(run_root, wrong_target)
        with self.assertRaises(HerdrPuppetError) as caught:
            create_qualification_tab(
                self.client,
                plan_payload=wrong_target,
                lease_path=self.lease_path,
                allow_live=True,
                settle_seconds=0.01,
                run_root=run_root,
            )
        self.assertEqual(caught.exception.code, "candidate_tab_not_qualified")
        self.assertEqual(
            caught.exception.details,
            {
                "rollback_performed": True,
                "rollback_verified": True,
                "ambiguous_candidate_count": 0,
            },
        )
        self.assertEqual(self.client.closed_tabs, ["w2:t1"])
        self.assertEqual(self.client.tab_rows, [])
        self.assertEqual(self.client.pane_rows, [])
        self.assertFalse(self.lease_path.exists())
        rollback_events = [
            event
            for event in read_events(run_root)
            if event.get("kind") == "qualification.tab-create-rolled-back"
        ]
        self.assertEqual(len(rollback_events), 1)
        self.assertTrue(rollback_events[0]["data"]["absence_verified"])

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

    def test_active_plan_and_lease_reconstruct_deterministic_owned_label(
        self,
    ) -> None:
        malformed_plan = copy.deepcopy(self.plan)
        malformed_plan["destination_selection"]["tab"]["ordinal"] = 9
        refresh_selected_authority(malformed_plan)
        with self.assertRaises(HerdrPuppetError) as plan_error:
            validate_plan(malformed_plan)
        self.assertEqual(
            plan_error.exception.code,
            "owned_label_authority_mismatch",
        )

        malformed_lease = self.create_lease()
        malformed_lease["destination_selection"]["tab"]["ordinal"] = 9
        refresh_selected_authority(malformed_lease)
        with self.assertRaises(HerdrPuppetError) as lease_error:
            validate_lease(malformed_lease)
        self.assertEqual(
            lease_error.exception.code,
            "owned_label_authority_mismatch",
        )

    def test_selected_authority_projects_every_independent_identity_edge(
        self,
    ) -> None:
        mutations = {
            "run": (("run_id",), "different-run"),
            "harness": (("harness",), "codex"),
            "session": (("session", "socket"), "/different/herdr.sock"),
            "machine": (
                ("destination_selection", "machine"),
                "different-machine",
            ),
            "destination_workspace": (
                ("destination_selection", "workspace_label"),
                "different-workspace",
            ),
            "fresh_request": (
                ("destination_selection", "tab", "request"),
                "existing",
            ),
            "ordinal": (
                ("destination_selection", "tab", "ordinal"),
                2,
            ),
            "workspace_id": (("workspace", "id"), "different-id"),
            "owned_label": (("owned_label",), "puppet-different-1"),
            "ssh_target": (
                ("expected_ssh_target",),
                "worker@different.example",
            ),
            "source": (("source", "worktree"), "/different/worktree"),
            "proof_root": (("proof_root",), "/different/proof"),
            "binding": (
                ("harness_binding", "attestation", "recorded_at"),
                "2026-08-14T00:00:01Z",
            ),
            "model": (
                ("harness_binding", "model_observation", "model"),
                "different-model",
            ),
        }
        baseline = selected_authority_sha256(self.plan)
        for name, (path, replacement) in mutations.items():
            with self.subTest(name=name):
                altered = copy.deepcopy(self.plan)
                target: dict[str, Any] = altered
                for segment in path[:-1]:
                    target = target[segment]
                target[path[-1]] = replacement
                self.assertNotEqual(
                    selected_authority_sha256(altered),
                    baseline,
                )
                self.assertNotEqual(
                    selected_authority(altered),
                    selected_authority(self.plan),
                )

    def test_historical_plan_is_status_only_and_cannot_create(self) -> None:
        historical = copy.deepcopy(self.plan)
        historical["schema"] = "herdr-puppet.plan.v1"
        historical.pop("destination_selection")
        historical.pop("selected_authority_sha256")
        historical["harness_binding"] = historical_lease_v1(
            {
                "harness": historical["harness"],
                "harness_binding": historical["harness_binding"],
            }
        )["harness_binding"]
        status = structural_status(self.client, plan_payload=historical)
        self.assertEqual(status["result"], "ok")
        with mock.patch.object(
            self.client,
            "create_tab",
            wraps=self.client.create_tab,
        ) as create_tab:
            with self.assertRaises(HerdrPuppetError) as caught:
                create_qualification_tab(
                    self.client,
                    plan_payload=historical,
                    lease_path=self.lease_path,
                    allow_live=True,
                    settle_seconds=0.1,
                    run_root=self.root / "run",
                )
        self.assertEqual(caught.exception.code, "invalid_plan")
        create_tab.assert_not_called()
        self.assertFalse(self.lease_path.exists())

    def test_historical_v1_records_reject_post_f73_binding_v3(self) -> None:
        plan_v1_with_binding_v3 = copy.deepcopy(self.plan)
        plan_v1_with_binding_v3["schema"] = "herdr-puppet.plan.v1"
        plan_v1_with_binding_v3.pop("destination_selection")
        plan_v1_with_binding_v3.pop("selected_authority_sha256")
        with self.assertRaises(HerdrPuppetError) as plan_error:
            structural_status(
                self.client,
                plan_payload=plan_v1_with_binding_v3,
            )
        self.assertEqual(plan_error.exception.code, "invalid_harness_binding")

        lease_v1_with_binding_v3 = copy.deepcopy(self.create_lease())
        lease_v1_with_binding_v3["schema"] = "herdr-puppet.lease.v1"
        lease_v1_with_binding_v3.pop("destination_selection")
        lease_v1_with_binding_v3.pop("selected_authority_sha256")
        with self.assertRaises(HerdrPuppetError) as lease_error:
            validate_legacy_lease(lease_v1_with_binding_v3)
        self.assertEqual(lease_error.exception.code, "invalid_harness_binding")

    def test_legacy_lease_requires_explicit_canonical_migration(self) -> None:
        legacy = historical_lease_v1(self.create_lease())
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
        self.assertEqual(migrated["schema"], "herdr-puppet.lease.v2")
        self.assertEqual(
            migrated["destination_selection"],
            {
                "schema": "herdr-puppet.destination-selection-receipt.v1",
                "mode": "legacy_explicit",
                "machine": None,
                "workspace_label": legacy["workspace"]["label"],
                "tab": {"request": "fresh", "ordinal": 1},
                "legacy_ordinal_alias": True,
                "catalog_path_retained": False,
                "ssh_target_retained": False,
                "existing_tab_adoption": False,
            },
        )
        self.assertEqual(
            migrated["selected_authority_sha256"],
            selected_authority_sha256(migrated),
        )
        self.assertEqual(migrated["shell_readiness"], "status_verified")
        self.assertEqual(migrated["harness_readiness"], "unverified")
        self.assertEqual(migrated["caller_text_files"], [])
        self.assertEqual(migrated["caller_text_files_removed"], [])
        self.assertEqual(migrated["remote_task_files"], [])

    def test_historical_lease_v1_retains_bounded_maintenance_lifecycle(
        self,
    ) -> None:
        historical = historical_lease_v1(self.create_lease())
        self.persist_lease(historical)
        run_root = self.root / "run"
        self.plan["harness_binding"] = copy.deepcopy(
            historical["harness_binding"]
        )
        refresh_selected_authority(self.plan)
        initialize_journal(run_root, self.plan)
        self.assertEqual(
            structural_status(self.client, lease_payload=historical)["result"],
            "ok",
        )
        maintenance = maintenance_checkpoint(
            self.client,
            lease_payload=historical,
            lease_path=self.lease_path,
            run_root=run_root,
        )
        self.assertEqual(maintenance["classification"], "active")
        current = load_json(self.lease_path)
        preserve_lease(
            lease_payload=current,
            lease_path=self.lease_path,
            reason="operator_stop",
            run_root=run_root,
        )
        preserved = load_json(self.lease_path)
        self.assertEqual(preserved["schema"], "herdr-puppet.lease.v1")
        cleanup = cleanup_preserved_tab(
            self.client,
            lease_payload=preserved,
            lease_path=self.lease_path,
            run_root=run_root,
            confirm_tab_id=preserved["tab_id"],
            allow_live_cleanup=True,
        )
        self.assertEqual(cleanup["result"], "ok")
        self.assertTrue(cleanup["cleanup_performed"])

    def test_unbound_legacy_lease_cannot_be_attested_retroactively(self) -> None:
        legacy = historical_lease_v1(self.create_lease())
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

    def test_v1_to_v2_migration_preserves_historical_binding_v2(self) -> None:
        client = FakeClient()
        codex_plan = make_plan(client, harness="codex")
        codex_plan["proof_root"] = str((self.root / "codex-run").resolve())
        refresh_selected_authority(codex_plan)
        run_root = self.root / "codex-run"
        initialize_journal(run_root, codex_plan)
        active = create_qualification_tab(
            client,
            plan_payload=codex_plan,
            lease_path=self.lease_path,
            allow_live=True,
            run_root=run_root,
            settle_seconds=0.1,
        )
        historical = historical_lease_v1(active)
        historical["harness_binding"]["schema"] = (
            "herdr-puppet.harness-binding.v2"
        )
        historical["harness_binding"]["fingerprint"] = binding_fingerprint(
            historical["harness_binding"]
        )
        migrated = migrate_legacy_lease(historical)
        validate_lease(migrated)
        self.assertEqual(
            migrated["harness_binding"]["schema"],
            "herdr-puppet.harness-binding.v2",
        )

    def test_binding_v1_allows_maintenance_but_not_fresh_qualification(
        self,
    ) -> None:
        lease = self.create_lease()
        historical_binding = lease["harness_binding"]
        historical_binding["schema"] = "herdr-puppet.harness-binding.v1"
        historical_binding.pop("lifecycle_observation")
        historical_binding["regular_launch"]["argv"] = [
            historical_binding["remote"]["executable"]["path"],
            "--dangerously-skip-permissions",
            "--sandbox=false",
            "--new-project",
            "--log-file",
            "/dev/null",
        ]
        historical_binding["regular_launch"][
            "explicit_model_selector"
        ] = False
        historical_binding["regular_launch"]["vector_sha256"] = _digest(
            {
                "argv": historical_binding["regular_launch"]["argv"],
                "environment": historical_binding["regular_launch"][
                    "environment"
                ],
                "inherit_environment": False,
            }
        )
        historical_binding["model_observation"] = {
            "selection": "current_default",
            "model": "unavailable",
            "effort": "unavailable",
        }
        historical_binding["instructions"]["layers"][2] = (
            "model/default-unresolved"
        )
        historical_binding["fingerprint"] = binding_fingerprint(
            historical_binding
        )
        refresh_selected_authority(lease)
        self.plan["harness_binding"] = copy.deepcopy(historical_binding)
        refresh_selected_authority(self.plan)
        self.persist_lease(lease)
        run_root = self.root / "run"
        initialize_journal(run_root, self.plan)
        validate_lease(lease)
        self.assertEqual(
            structural_status(self.client, lease_payload=lease)["result"],
            "ok",
        )
        with self.assertRaises(HerdrPuppetError) as caught:
            qualification_run(
                self.client,
                lease_payload=lease,
                lease_path=self.lease_path,
                seq=lease["next_seq"],
                command="printf must-not-run",
                allow_live=True,
                run_root=run_root,
            )
        self.assertEqual(
            caught.exception.code,
            "legacy_harness_binding_requires_recensus",
        )
        self.assertEqual(self.client.ran, [])
        active_maintenance = maintenance_checkpoint(
            self.client,
            lease_payload=lease,
            lease_path=self.lease_path,
            run_root=run_root,
        )
        self.assertEqual(active_maintenance["classification"], "active")
        preserve_lease(
            lease_payload=lease,
            lease_path=self.lease_path,
            reason="operator_stop",
            run_root=run_root,
        )
        preserved = load_json(self.lease_path)
        cleanup = cleanup_preserved_tab(
            self.client,
            lease_payload=preserved,
            lease_path=self.lease_path,
            confirm_tab_id=preserved["tab_id"],
            allow_live_cleanup=True,
            run_root=run_root,
        )
        self.assertEqual(cleanup["result"], "ok")
        self.assertTrue(cleanup["cleanup_performed"])

    def test_legacy_lease_file_migration_is_locked_and_idempotent(self) -> None:
        legacy = historical_lease_v1(self.create_lease())
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
            [
                "destination_selection",
                "harness_readiness",
                "remote_task_files",
                "schema",
                "selected_authority_sha256",
                "shell_readiness",
            ],
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
        base_lease = self.create_lease()
        unlaunched = copy.deepcopy(base_lease)
        unlaunched["shell_readiness"] = "status_verified"
        unlaunched["harness_readiness"] = "operator_verified"
        unlaunched["harness_readiness_evidence"] = (
            "operator_observed_ready_input"
        )
        unlaunched["harness_readiness_operator"] = "operator-a"
        unlaunched["harness_readiness_verified_at"] = (
            "2026-07-26T00:00:00Z"
        )
        with self.assertRaises(HerdrPuppetError) as missing_launch:
            validate_lease(unlaunched)
        self.assertEqual(missing_launch.exception.code, "invalid_lease")

        lease = self.mark_harness_launched(base_lease)
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
        legacy = historical_lease_v1(self.create_lease())
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

    def test_journal_refresh_retains_historical_lease_status_evidence(self) -> None:
        lease = self.create_lease()
        run_root = self.root / "run"
        legacy = historical_lease_v1(lease)
        legacy.pop("shell_readiness")
        self.plan["harness_binding"] = copy.deepcopy(
            legacy["harness_binding"]
        )
        refresh_selected_authority(self.plan)
        initialize_journal(run_root, self.plan)
        result = refresh_state(run_root, legacy)
        self.assertEqual(result["state"], "active")
        state = (run_root / "STATE.md").read_text(encoding="utf-8")
        self.assertIn("workspace_label: `worker-02`", state)
        self.assertIn("tab_ordinal: `1`", state)

    def test_journal_initialization_marks_historical_binding_maintenance_only(
        self,
    ) -> None:
        historical = historical_lease_v1(self.create_lease())
        run_root = self.root / "historical-binding-run"
        historical_plan = copy.deepcopy(self.plan)
        historical_plan["proof_root"] = str(run_root.resolve())
        historical_plan["harness_binding"] = copy.deepcopy(
            historical["harness_binding"]
        )
        refresh_selected_authority(historical_plan)
        initialize_journal(run_root, historical_plan)
        state = (run_root / "STATE.md").read_text(encoding="utf-8")
        self.assertIn("next: maintenance only; recensus", state)
        self.assertIn("active plan-v2 carrying binding-v3", state)
        self.assertNotIn(
            "next: create one qualification-owned tab after the live gate",
            state,
        )

    def test_generic_journal_append_cannot_forge_controller_events(self) -> None:
        for kind in (
            "journal.initialized",
            "qualification.claude-lifecycle",
        ):
            args = build_parser().parse_args(
                [
                    "journal-append",
                    "--run-root",
                    str(self.root / "unused-run"),
                    "--run-id",
                    "run-forged-event",
                    "--kind",
                    kind,
                    "--result",
                    "observed",
                ]
            )
            with self.subTest(kind=kind):
                with self.assertRaises(HerdrPuppetError) as caught:
                    herdr_cli.run(args)
                self.assertEqual(
                    caught.exception.code,
                    "controller_event_kind_reserved",
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

    def test_create_tab_core_requires_run_root_before_mutation(self) -> None:
        with mock.patch.object(
            self.client,
            "create_tab",
            wraps=self.client.create_tab,
        ) as create_tab:
            with self.assertRaises(TypeError):
                create_qualification_tab(
                    self.client,
                    plan_payload=self.plan,
                    lease_path=self.lease_path,
                    allow_live=True,
                    settle_seconds=0.1,
                )
        create_tab.assert_not_called()
        self.assertFalse(self.lease_path.exists())

    def test_remote_task_registration_rejects_missing_active_journal_before_mutation(
        self,
    ) -> None:
        lease = self.create_lease()
        before = self.lease_path.read_bytes()
        with self.assertRaises(HerdrPuppetError) as caught:
            register_remote_task_file(
                lease_payload=lease,
                lease_path=self.lease_path,
                remote_path="/srv/agy/tasks/must-not-register.txt",
                source_repo=lease["source"]["repo"],
                source_worktree=lease["source"]["worktree"],
                confirm_caller_owned=True,
                run_root=None,  # type: ignore[arg-type]
            )
        self.assertEqual(caught.exception.code, "journal_root_required")
        self.assertEqual(self.lease_path.read_bytes(), before)
        self.assertEqual(load_json(self.lease_path)["remote_task_files"], [])

    def test_all_active_journal_callers_reject_explicit_none_before_mutation(
        self,
    ) -> None:
        lease = self.create_lease()
        before = self.lease_path.read_bytes()
        guarded_client = mock.Mock(spec=FakeClient)
        operations = {
            "remote_task_registration": lambda: register_remote_task_file(
                lease_payload=lease,
                lease_path=self.lease_path,
                remote_path="/srv/agy/tasks/none-journal.txt",
                source_repo=lease["source"]["repo"],
                source_worktree=lease["source"]["worktree"],
                confirm_caller_owned=True,
                run_root=None,  # type: ignore[arg-type]
            ),
            "harness_launch": lambda: qualification_harness_launch(
                guarded_client,
                lease_payload=lease,
                lease_path=self.lease_path,
                seq=lease["next_seq"],
                allow_live=True,
                run_root=None,  # type: ignore[arg-type]
            ),
            "claude_lifecycle_observe": lambda: qualification_claude_lifecycle_observe(
                lease_payload=lease,
                lease_path=self.lease_path,
                receipt={},
                phase="armed",
                run_root=None,  # type: ignore[arg-type]
            ),
            "startup_gate": lambda: qualification_startup_gate(
                guarded_client,
                lease_payload=lease,
                lease_path=self.lease_path,
                seq=lease["next_seq"],
                gate="security_acknowledgement",
                action="accept",
                source_worktree=lease["source"]["worktree"],
                operator_id="test-operator",
                evidence="operator_observed_exact_gate",
                confirm_exact_worktree=True,
                confirm_unrestricted=True,
                allow_live=True,
                run_root=None,  # type: ignore[arg-type]
            ),
            "harness_ready": lambda: qualification_harness_ready(
                guarded_client,
                lease_payload=lease,
                lease_path=self.lease_path,
                source_repo=lease["source"]["repo"],
                source_worktree=lease["source"]["worktree"],
                operator_id="test-operator",
                evidence="operator_observed_ready_input",
                confirm_ready=True,
                allow_live=True,
                run_root=None,  # type: ignore[arg-type]
            ),
            "view_begin": lambda: qualification_view_begin(
                guarded_client,
                lease_payload=lease,
                lease_path=self.lease_path,
                nonce="NONE-JOURNAL-VIEW-BEGIN",
                operator_id="test-operator",
                confirm_native_tui_visible=True,
                allow_live=True,
                run_root=None,  # type: ignore[arg-type]
            ),
            "view_complete": lambda: qualification_view_complete(
                guarded_client,
                lease_payload=lease,
                lease_path=self.lease_path,
                nonce="NONE-JOURNAL-VIEW-DONE",
                operator_id="test-operator",
                evidence="operator_observed_real_client_detach_reattach",
                confirm_detached_reattached=True,
                allow_live=True,
                run_root=None,  # type: ignore[arg-type]
            ),
        }
        for name, operation in operations.items():
            with self.subTest(operation=name):
                guarded_client.reset_mock()
                with self.assertRaises(HerdrPuppetError) as caught:
                    operation()
                self.assertEqual(
                    caught.exception.code,
                    "journal_root_required",
                )
                self.assertEqual(guarded_client.mock_calls, [])
                self.assertEqual(self.lease_path.read_bytes(), before)

    def test_journal_initialization_validates_plan_before_creating_root(
        self,
    ) -> None:
        run_root = self.root / "invalid-plan-run"
        malformed = copy.deepcopy(self.plan)
        malformed["proof_root"] = str(run_root.resolve())
        malformed["destination_selection"]["tab"]["ordinal"] = 2
        refresh_selected_authority(malformed)
        with self.assertRaises(HerdrPuppetError) as caught:
            initialize_journal(run_root, malformed)
        self.assertEqual(
            caught.exception.code,
            "owned_label_authority_mismatch",
        )
        self.assertFalse(run_root.exists())

    def test_extra_nested_plan_field_is_rejected_before_herdr_or_lease(
        self,
    ) -> None:
        run_root = self.root / "nested-plan-run"
        journal_plan = copy.deepcopy(self.plan)
        journal_plan["proof_root"] = str(run_root.resolve())
        refresh_selected_authority(journal_plan)
        initialize_journal(run_root, journal_plan)
        malformed = copy.deepcopy(journal_plan)
        malformed["session"]["unexpected"] = "must-fail-before-create"
        refresh_selected_authority(malformed)
        with mock.patch.object(
            self.client,
            "create_tab",
            wraps=self.client.create_tab,
        ) as create_tab:
            with self.assertRaises(HerdrPuppetError) as caught:
                create_qualification_tab(
                    self.client,
                    plan_payload=malformed,
                    lease_path=self.lease_path,
                    allow_live=True,
                    run_root=run_root,
                    settle_seconds=0.1,
                )
        self.assertEqual(caught.exception.code, "invalid_plan")
        create_tab.assert_not_called()
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
        wrong_plan["owned_label"] = deterministic_owned_label(
            wrong_plan["run_id"],
            wrong_plan["harness"],
            wrong_plan["destination_selection"]["tab"]["ordinal"],
        )
        refresh_selected_authority(wrong_plan)
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

    def test_create_tab_rejects_same_run_root_cross_machine_and_ordinal(
        self,
    ) -> None:
        client = FakeClient()
        client.workspace_rows = [
            {"workspace_id": "w-ai1", "label": "aiworker-01"},
            {"workspace_id": "w-ai2", "label": "aiworker-02"},
        ]
        facts = fixture("plan-ok.json")
        facts["workspaces"] = copy.deepcopy(client.workspace_rows)
        run_root = self.root / "cross-machine-run"
        binding = sample_binding()
        common = {
            "session": "operator-session",
            "destination_catalog": fixture("destination-catalog-ok.json"),
            "run_id": "same-run-machine-swap",
            "harness": "agy",
            "repo": "example/SaariusSkills",
            "worktree": "/redacted/worktree",
            "proof_root": str(run_root.resolve()),
            "harness_binding": binding,
            "live_mutation_authorized": True,
            "facts": facts,
        }
        journal_plan = plan(
            client,
            machine="aiworker-01",
            tab_ordinal=1,
            **common,
        )
        incoming_plan = plan(
            client,
            machine="aiworker-02",
            tab_ordinal=2,
            **common,
        )
        initialize_journal(run_root, journal_plan)
        lease_path = self.root / "cross-machine-lease.json"
        with mock.patch.object(
            client,
            "create_tab",
            wraps=client.create_tab,
        ) as create_tab:
            with self.assertRaises(HerdrPuppetError) as caught:
                create_qualification_tab(
                    client,
                    plan_payload=incoming_plan,
                    lease_path=lease_path,
                    allow_live=True,
                    settle_seconds=0.1,
                    run_root=run_root,
                )
        self.assertEqual(caught.exception.code, "journal_plan_mismatch")
        create_tab.assert_not_called()
        self.assertFalse(lease_path.exists())

    def test_create_tab_rejects_same_run_root_cross_harness_and_model(
        self,
    ) -> None:
        client = FakeClient()
        run_root = self.root / "cross-harness-run"
        common = {
            "session": "operator-session",
            "workspace_id": "w2",
            "workspace_label": "worker-02",
            "expected_ssh_target": "worker@worker-02.example",
            "run_id": "same-run-harness-swap",
            "repo": "example/SaariusSkills",
            "worktree": "/redacted/worktree",
            "proof_root": str(run_root.resolve()),
            "live_mutation_authorized": True,
            "facts": fixture("plan-ok.json"),
        }
        journal_plan = plan(
            client,
            harness="agy",
            harness_binding=sample_binding(harness="agy"),
            **common,
        )
        incoming_plan = plan(
            client,
            harness="codex",
            harness_binding=sample_binding(harness="codex"),
            **common,
        )
        initialize_journal(run_root, journal_plan)
        lease_path = self.root / "cross-harness-lease.json"
        with mock.patch.object(
            client,
            "create_tab",
            wraps=client.create_tab,
        ) as create_tab:
            with self.assertRaises(HerdrPuppetError) as caught:
                create_qualification_tab(
                    client,
                    plan_payload=incoming_plan,
                    lease_path=lease_path,
                    allow_live=True,
                    settle_seconds=0.1,
                    run_root=run_root,
                )
        self.assertEqual(caught.exception.code, "journal_plan_mismatch")
        create_tab.assert_not_called()
        self.assertFalse(lease_path.exists())

    def test_later_preflight_rejects_cross_ordinal_journal_authority(self) -> None:
        lease = self.create_lease()
        run_root = self.root / "run"
        swapped_plan = copy.deepcopy(self.plan)
        swapped_plan["destination_selection"]["tab"]["ordinal"] = 2
        swapped_plan["owned_label"] = deterministic_owned_label(
            swapped_plan["run_id"],
            swapped_plan["harness"],
            2,
        )
        refresh_selected_authority(swapped_plan)
        initialize_journal(run_root, swapped_plan)
        before = self.lease_path.read_bytes()
        with self.assertRaises(HerdrPuppetError) as caught:
            qualification_run(
                self.client,
                lease_payload=lease,
                lease_path=self.lease_path,
                seq=lease["next_seq"],
                command=(
                    "printf '%s\\n' "
                    "'HERDR_PUPPET_STATUS LATER-MISMATCH-1'"
                ),
                allow_live=True,
                run_root=run_root,
            )
        self.assertEqual(caught.exception.code, "journal_lease_authority_mismatch")
        self.assertEqual(self.client.ran, [])
        self.assertEqual(self.lease_path.read_bytes(), before)

    def test_later_preflight_rejects_cross_harness_model_authority(self) -> None:
        lease = self.create_lease()
        run_root = self.root / "run"
        swapped_plan = plan(
            self.client,
            session="operator-session",
            workspace_id="w2",
            workspace_label="worker-02",
            expected_ssh_target="worker@worker-02.example",
            run_id=lease["run_id"],
            harness="codex",
            repo=lease["source"]["repo"],
            worktree=lease["source"]["worktree"],
            proof_root=str(run_root.resolve()),
            harness_binding=sample_binding(harness="codex"),
            live_mutation_authorized=True,
            facts=fixture("plan-ok.json"),
        )
        initialize_journal(run_root, swapped_plan)
        before = self.lease_path.read_bytes()
        with self.assertRaises(HerdrPuppetError) as caught:
            qualification_run(
                self.client,
                lease_payload=lease,
                lease_path=self.lease_path,
                seq=lease["next_seq"],
                command=(
                    "printf '%s\\n' "
                    "'HERDR_PUPPET_STATUS LATER-MISMATCH-2'"
                ),
                allow_live=True,
                run_root=run_root,
            )
        self.assertEqual(caught.exception.code, "journal_lease_authority_mismatch")
        self.assertEqual(self.client.ran, [])
        self.assertEqual(self.lease_path.read_bytes(), before)

    def test_journal_initialization_digest_and_authority_are_verified(self) -> None:
        for field in ("plan_sha256", "selected_authority_sha256"):
            with self.subTest(field=field):
                client = FakeClient()
                plan_payload = make_plan(client)
                run_root = self.root / f"tampered-{field}"
                plan_payload["proof_root"] = str(run_root.resolve())
                refresh_selected_authority(plan_payload)
                initialize_journal(run_root, plan_payload)
                events = read_events(run_root)
                events[0]["data"][field] = "0" * 64
                (run_root / "events.jsonl").write_text(
                    "".join(
                        json.dumps(event, sort_keys=True, separators=(",", ":"))
                        + "\n"
                        for event in events
                    ),
                    encoding="utf-8",
                )
                lease_path = self.root / f"tampered-{field}-lease.json"
                with mock.patch.object(
                    client,
                    "create_tab",
                    wraps=client.create_tab,
                ) as create_tab:
                    with self.assertRaises(HerdrPuppetError) as caught:
                        create_qualification_tab(
                            client,
                            plan_payload=plan_payload,
                            lease_path=lease_path,
                            allow_live=True,
                            settle_seconds=0.1,
                            run_root=run_root,
                        )
                self.assertEqual(
                    caught.exception.code,
                    "journal_initialization_authority_invalid",
                )
                create_tab.assert_not_called()
                self.assertFalse(lease_path.exists())

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
        command = (
            "printf '%s\\n' "
            "'HERDR_PUPPET_STATUS HASHED-COMMAND-1'"
        )
        result = qualification_run(
            self.client,
            lease_payload=lease,
            lease_path=self.lease_path,
            seq=1,
            command=command,
            allow_live=True,
            run_root=run_root,
        )
        updated = json.loads(self.lease_path.read_text(encoding="utf-8"))
        events = (run_root / "events.jsonl").read_text(encoding="utf-8")
        self.assertEqual(result["next_seq"], 2)
        self.assertEqual(updated["next_seq"], 2)
        self.assertEqual(
            result["command_sha256"],
            sha256_text(command),
        )
        self.assertTrue(result["herdr_cli_acknowledged"])
        self.assertEqual(result["submission_mode"], "atomic_shell_command")
        self.assertEqual(result["execution_acceptance"], "unverified")
        self.assertFalse(result["readiness_advanced"])
        self.assertEqual(result["harness_readiness"], "unverified")
        self.assertFalse(result["transcript_read"])
        self.assertNotIn(command, json.dumps(result))
        self.assertNotIn(command, events)
        self.assertIn('"kind":"qualification.run"', events)
        self.assertIn('"command_sha256"', events)
        self.assertIn('"transcript_read":false', events)
        self.assertEqual(
            self.client.ran,
            [("run", "w2:p1", command)],
        )
        self.assertEqual(self.client.sent, [])

    def test_run_failure_does_not_advance_sequence_or_leak_command(self) -> None:
        lease = self.create_lease()
        run_root = self.root / "run"
        initialize_journal(run_root, self.plan)
        command_path = self.root / "failing-command.txt"
        command = (
            "printf '%s\\n' "
            "'HERDR_PUPPET_STATUS FAILING-COMMAND-1'"
        )
        command_path.write_text(command, encoding="utf-8")

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
                command=command,
                text_file=str(command_path),
                allow_live=True,
                run_root=run_root,
            )
        updated = json.loads(self.lease_path.read_text(encoding="utf-8"))
        events = (run_root / "events.jsonl").read_text(encoding="utf-8")
        self.assertEqual(updated["next_seq"], 1)
        self.assertEqual(
            updated["caller_text_files"],
            [str(command_path.resolve())],
        )
        self.assertEqual(
            updated["pending_sequence_operation"]["operation"],
            "run",
        )
        self.assertNotIn(
            command,
            json.dumps(caught.exception.as_json()),
        )
        self.assertNotIn(command, events)
        self.assertNotIn('"kind":"qualification.run"', events)
        with self.assertRaises(HerdrPuppetError) as replay:
            qualification_run(
                self.client,
                lease_payload=updated,
                lease_path=self.lease_path,
                seq=1,
                command=command,
                text_file=str(command_path),
                allow_live=True,
                run_root=run_root,
            )
        self.assertEqual(
            replay.exception.code,
            "qualification_sequence_delivery_unknown",
        )

    def test_run_tracks_retained_caller_command_file(self) -> None:
        command_path = self.root / "command.txt"
        command = (
            "printf '%s\\n' "
            "'HERDR_PUPPET_STATUS TRACKED-COMMAND-1'"
        )
        command_path.write_text(command, encoding="utf-8")
        lease = self.create_lease()
        run_root = self.initialize_default_journal()
        result = qualification_run(
            self.client,
            lease_payload=lease,
            lease_path=self.lease_path,
            seq=1,
            command=command,
            text_file=str(command_path),
            allow_live=True,
            run_root=run_root,
        )
        updated = json.loads(self.lease_path.read_text(encoding="utf-8"))
        normalized_command_path = str(command_path.resolve())
        self.assertEqual(updated["caller_text_files"], [normalized_command_path])
        self.assertTrue(result["caller_text_file_retained"])
        self.assertTrue(result["command_file_tracked"])
        self.assertFalse(result["controller_command_persisted"])
        self.assertEqual(result["caller_input_file_lifecycle"], "caller_owned")
        self.assertNotIn(normalized_command_path, json.dumps(result))
        self.assertNotIn(command, json.dumps(result))

    def test_run_does_not_retain_missing_caller_command_file(self) -> None:
        missing_command_path = self.root / "missing-command.txt"
        lease = self.create_lease()
        run_root = self.initialize_default_journal()
        result = qualification_run(
            self.client,
            lease_payload=lease,
            lease_path=self.lease_path,
            seq=1,
            command=(
                "printf '%s\\n' "
                "'HERDR_PUPPET_STATUS MISSING-COMMAND-1'"
            ),
            text_file=str(missing_command_path),
            allow_live=True,
            run_root=run_root,
        )
        updated = json.loads(self.lease_path.read_text(encoding="utf-8"))
        self.assertEqual(updated["caller_text_files"], [])
        self.assertFalse(result["caller_text_file_retained"])
        self.assertTrue(result["command_file_tracked"])
        self.assertNotIn(str(missing_command_path.resolve()), json.dumps(result))

    def test_run_rejects_live_sequence_and_structural_gate_failures(self) -> None:
        lease = self.create_lease()
        run_root = self.initialize_default_journal()
        with self.assertRaises(HerdrPuppetError) as caught:
            qualification_run(
                self.client,
                lease_payload=lease,
                lease_path=self.lease_path,
                seq=1,
                command=(
                    "printf '%s\\n' "
                    "'HERDR_PUPPET_STATUS LIVE-GATE-STATUS-1'"
                ),
                allow_live=False,
                run_root=run_root,
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
                run_root=run_root,
            )
        self.assertEqual(caught.exception.code, "send_sequence_mismatch")

        self.client.pane_rows[0]["terminal_id"] = "replacement"
        with self.assertRaises(HerdrPuppetError) as caught:
            qualification_run(
                self.client,
                lease_payload=lease,
                lease_path=self.lease_path,
                seq=1,
                command=(
                    "printf '%s\\n' "
                    "'HERDR_PUPPET_STATUS STRUCTURAL-GATE-1'"
                ),
                allow_live=True,
                run_root=run_root,
            )
        self.assertEqual(caught.exception.code, "prerun_status_blocked")
        self.assertEqual(self.client.ran, [])
        self.assertEqual(
            json.loads(self.lease_path.read_text(encoding="utf-8"))["next_seq"],
            1,
        )

    def test_run_preserves_followon_shell_readiness_gate(self) -> None:
        lease = self.create_lease()
        run_root = self.initialize_default_journal()
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
                run_root=run_root,
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
            run_root=run_root,
        )
        self.assertEqual(result["next_seq"], 3)
        self.assertEqual(result["shell_readiness"], "status_verified")

    def test_failed_first_shell_wait_allows_one_strict_status_retry(self) -> None:
        lease = self.create_lease()
        run_root = self.root / "run"
        initialize_journal(run_root, self.plan)
        first_command = (
            "printf '%s\\n' "
            "'HERDR_PUPPET_STATUS SHELL-FIRST-STATUS-1'"
        )
        first = qualification_run(
            self.client,
            lease_payload=lease,
            lease_path=self.lease_path,
            seq=1,
            command=first_command,
            allow_live=True,
            run_root=run_root,
        )
        self.assertTrue(first["shell_status_probe"])
        self.assertFalse(first["shell_status_retry"])
        first_wait = qualification_beacon_wait(
            self.client,
            lease_payload=load_json(self.lease_path),
            lease_path=self.lease_path,
            nonce="SHELL-FIRST-STATUS-1",
            lines=80,
            allow_live=True,
            run_root=run_root,
        )
        self.assertFalse(first_wait["matched"])

        retry_command = (
            "printf '%s\\n' "
            "'HERDR_PUPPET_STATUS SHELL-RETRY-STATUS-2'"
        )
        retry = qualification_run(
            self.client,
            lease_payload=load_json(self.lease_path),
            lease_path=self.lease_path,
            seq=2,
            command=retry_command,
            allow_live=True,
            run_root=run_root,
        )
        self.assertTrue(retry["shell_status_probe"])
        self.assertTrue(retry["shell_status_retry"])
        self.assertEqual(retry["next_seq"], 3)
        self.client.read_payload = (
            "HERDR_PUPPET_STATUS SHELL-RETRY-STATUS-2"
        )
        retry_wait = qualification_beacon_wait(
            self.client,
            lease_payload=load_json(self.lease_path),
            lease_path=self.lease_path,
            nonce="SHELL-RETRY-STATUS-2",
            lines=80,
            allow_live=True,
            run_root=run_root,
        )
        self.assertEqual(retry_wait["shell_readiness"], "status_verified")
        followon = qualification_run(
            self.client,
            lease_payload=load_json(self.lease_path),
            lease_path=self.lease_path,
            seq=3,
            command="python3 bounded-census.py",
            allow_live=True,
            run_root=run_root,
        )
        self.assertEqual(followon["next_seq"], 4)
        events = read_events(run_root)
        retry_events = [
            event
            for event in events
            if event.get("kind") == "qualification.run"
            and event.get("seq") == 2
        ]
        self.assertEqual(len(retry_events), 1)
        self.assertTrue(
            retry_events[0]["data"]["shell_status_retry"]
        )

    def test_shell_status_retry_requires_classified_first_probe(self) -> None:
        lease = self.create_lease()
        run_root = self.root / "run"
        initialize_journal(run_root, self.plan)
        with self.assertRaises(HerdrPuppetError) as caught:
            qualification_run(
                self.client,
                lease_payload=lease,
                lease_path=self.lease_path,
                seq=1,
                command="arbitrary first shell command",
                allow_live=True,
                run_root=run_root,
            )
        self.assertEqual(
            caught.exception.code,
            "initial_shell_status_probe_required",
        )
        self.assertEqual(self.client.ran, [])

    def test_shell_status_retry_is_narrow_and_single_use(self) -> None:
        lease = self.create_lease()
        run_root = self.root / "run"
        initialize_journal(run_root, self.plan)
        first_command = (
            "printf '%s\\n' "
            "'HERDR_PUPPET_STATUS SHELL-FIRST-STATUS-1'"
        )
        qualification_run(
            self.client,
            lease_payload=lease,
            lease_path=self.lease_path,
            seq=1,
            command=first_command,
            allow_live=True,
            run_root=run_root,
        )
        retry_command = (
            "printf '%s\\n' "
            "'HERDR_PUPPET_STATUS SHELL-RETRY-STATUS-2'"
        )
        with self.assertRaises(HerdrPuppetError) as caught:
            qualification_run(
                self.client,
                lease_payload=load_json(self.lease_path),
                lease_path=self.lease_path,
                seq=2,
                command=retry_command,
                allow_live=True,
                run_root=run_root,
            )
        self.assertEqual(
            caught.exception.code,
            "shell_status_retry_not_authorized",
        )

        qualification_beacon_wait(
            self.client,
            lease_payload=load_json(self.lease_path),
            lease_path=self.lease_path,
            nonce="SHELL-FIRST-STATUS-1",
            lines=80,
            allow_live=True,
            run_root=run_root,
        )
        with self.assertRaises(HerdrPuppetError) as caught:
            qualification_run(
                self.client,
                lease_payload=load_json(self.lease_path),
                lease_path=self.lease_path,
                seq=2,
                command="arbitrary pre-readiness command",
                allow_live=True,
                run_root=run_root,
            )
        self.assertEqual(caught.exception.code, "shell_readiness_not_proven")

        qualification_run(
            self.client,
            lease_payload=load_json(self.lease_path),
            lease_path=self.lease_path,
            seq=2,
            command=retry_command,
            allow_live=True,
            run_root=run_root,
        )
        qualification_beacon_wait(
            self.client,
            lease_payload=load_json(self.lease_path),
            lease_path=self.lease_path,
            nonce="SHELL-RETRY-STATUS-2",
            lines=80,
            allow_live=True,
            run_root=run_root,
        )
        with self.assertRaises(HerdrPuppetError) as caught:
            qualification_run(
                self.client,
                lease_payload=load_json(self.lease_path),
                lease_path=self.lease_path,
                seq=3,
                command=(
                    "printf '%s\\n' "
                    "'HERDR_PUPPET_STATUS SHELL-THIRD-STATUS-3'"
                ),
                allow_live=True,
                run_root=run_root,
            )
        self.assertEqual(caught.exception.code, "shell_readiness_not_proven")
        self.assertEqual(len(self.client.ran), 2)

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
        run_root = self.initialize_default_journal()
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
                run_root=run_root,
            )

        self.assertEqual(caught.exception.code, "generic_harness_launch_forbidden")
        self.assertEqual(self.client.ran, [])

    def test_run_allows_harness_name_as_non_command_argument(self) -> None:
        lease = self.create_lease()
        run_root = self.initialize_default_journal()
        lease["next_seq"] = 2
        lease["shell_readiness"] = "status_verified"
        self.lease_path.write_text(json.dumps(lease), encoding="utf-8")
        command = (
            "/private/harness_census.py --harness agy "
            "--model gemini-3.7-flash-high "
            "--output /private/census.json"
        )

        result = qualification_run(
            self.client,
            lease_payload=lease,
            lease_path=self.lease_path,
            seq=2,
            command=command,
            allow_live=True,
            run_root=run_root,
        )

        self.assertEqual(result["result"], "ok")
        self.assertEqual(self.client.ran[-1], ("run", "w2:p1", command))

    def test_run_rejects_wrapped_launchers_for_all_harnesses(self) -> None:
        for harness in ("agy", "codex", "claude", "cursor", "grok"):
            with self.subTest(harness=harness):
                client = FakeClient()
                binding = sample_binding(
                    harness=harness,
                    run_id=f"run-wrapped-{harness}",
                )
                run_root = self.root / f"run-wrapped-{harness}"
                lease_path = self.root / f"lease-wrapped-{harness}.json"
                bound_plan = plan(
                    client,
                    session="operator-session",
                    workspace_id="w2",
                    workspace_label="worker-02",
                    expected_ssh_target="worker@worker-02.example",
                    run_id=f"run-wrapped-{harness}",
                    harness=harness,
                    repo="example/SaariusSkills",
                    worktree="/redacted/worktree",
                    proof_root=str(run_root.resolve()),
                    harness_binding=binding,
                    live_mutation_authorized=True,
                )
                initialize_journal(run_root, bound_plan)
                lease = create_qualification_tab(
                    client,
                    plan_payload=bound_plan,
                    lease_path=lease_path,
                    allow_live=True,
                    settle_seconds=0.1,
                    run_root=run_root,
                )
                lease["shell_readiness"] = "status_verified"
                lease["next_seq"] = 2
                lease_path.write_text(json.dumps(lease), encoding="utf-8")
                command_name = binding["remote"]["executable"]["command"]
                commands = (
                    f"command {command_name}",
                    f"( {command_name} )",
                    f"nohup {command_name}",
                    f"HARNESS_MODE=test {command_name}",
                    f"exec env HARNESS_MODE=test {command_name}",
                    binding["remote"]["executable"]["path"],
                    f"sh -c '{command_name} --version'",
                    f"bash -lc 'exec {command_name}'",
                    f"eval '{command_name}'",
                )
                for command in commands:
                    with self.subTest(harness=harness, command=command):
                        with self.assertRaises(HerdrPuppetError) as caught:
                            qualification_run(
                                client,
                                lease_payload=load_json(lease_path),
                                lease_path=lease_path,
                                seq=2,
                                command=command,
                                allow_live=True,
                                run_root=run_root,
                            )
                        self.assertIn(
                            caught.exception.code,
                            {
                                "generic_harness_launch_forbidden",
                                "shell_replacing_harness_launcher",
                                "nested_shell_command_forbidden",
                            },
                        )

    def test_status_beacon_unlocks_followon_run_in_shared_sequence(self) -> None:
        lease = self.create_lease()
        run_root = self.root / "run"
        initialize_journal(run_root, self.plan)
        first = qualification_run(
            self.client,
            lease_payload=lease,
            lease_path=self.lease_path,
            seq=1,
            command=(
                "printf '%s\\n' "
                "'HERDR_PUPPET_STATUS SHELL-READY-1'"
            ),
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
                (
                    "run",
                    "w2:p1",
                    "printf '%s\\n' "
                    "'HERDR_PUPPET_STATUS SHELL-READY-1'",
                ),
                ("run", "w2:p1", "python3 bounded-census.py"),
            ],
        )

    def test_cross_process_same_sequence_mutates_herdr_at_most_once(self) -> None:
        self.create_lease()
        run_root = self.initialize_default_journal()
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
                    str(run_root),
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
        run_root = self.initialize_default_journal()
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
                    command=(
                        "printf '%s\\n' "
                        "'HERDR_PUPPET_STATUS SERIALIZED-RUN-1'"
                    ),
                    allow_live=True,
                    run_root=run_root,
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
        run_root = self.initialize_default_journal()
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
                run_root=run_root,
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
        initial_text, manifest = self.wrapped_initial(
            updated,
            "bounded prompt",
        )
        sent = qualification_send(
            self.client,
            lease_payload=updated,
            lease_path=self.lease_path,
            seq=3,
            text=initial_text,
            instruction_manifest=manifest,
            allow_live=True,
            run_root=run_root,
        )
        self.assertEqual(sent["next_seq"], 4)

    def test_cursor_ready_lease_without_workspace_trust_cannot_send(
        self,
    ) -> None:
        binding = sample_binding(harness="cursor")
        cursor_plan = plan(
            self.client,
            session="operator-session",
            workspace_id="w2",
            workspace_label="worker-02",
            expected_ssh_target="worker@worker-02.example",
            run_id="run-cursor-forged-ready",
            harness="cursor",
            repo="example/SaariusSkills",
            worktree="/redacted/worktree",
            proof_root=str((self.root / "cursor-forged-ready").resolve()),
            harness_binding=binding,
            live_mutation_authorized=True,
        )
        run_root = self.root / "cursor-forged-ready"
        initialize_journal(run_root, cursor_plan)
        lease = create_qualification_tab(
            self.client,
            plan_payload=cursor_plan,
            lease_path=self.lease_path,
            allow_live=True,
            run_root=run_root,
            settle_seconds=0.1,
        )
        lease = self.mark_harness_launched(lease)
        lease["harness_readiness"] = "operator_verified"
        lease["harness_readiness_evidence"] = (
            "operator_observed_ready_input"
        )
        lease["harness_readiness_operator"] = "operator-cursor"
        lease["harness_readiness_verified_at"] = "2026-07-30T12:02:00Z"
        self.persist_lease(lease)

        with self.assertRaises(HerdrPuppetError) as caught:
            qualification_send(
                self.client,
                lease_payload=lease,
                lease_path=self.lease_path,
                seq=lease["next_seq"],
                text="must not send",
                allow_live=True,
                run_root=self.root / "cursor-forged-ready",
            )
        self.assertEqual(caught.exception.code, "invalid_lease")
        self.assertEqual(self.client.sent, [])

    def test_send_rejects_replay_before_mutation(self) -> None:
        lease = self.create_lease()
        run_root = self.initialize_default_journal()
        with self.assertRaisesRegex(HerdrPuppetError, "stale, skipped"):
            qualification_send(
                self.client,
                lease_payload=lease,
                lease_path=self.lease_path,
                seq=2,
                text="bounded prompt",
                allow_live=True,
                run_root=run_root,
            )
        self.assertEqual(self.client.sent, [])

    def test_send_rejects_followup_prompt_without_status_beacon(self) -> None:
        lease = self.create_lease()
        run_root = self.initialize_default_journal()
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
                run_root=run_root,
            )

    def test_send_allows_followup_prompt_after_status_beacon(self) -> None:
        lease = self.create_lease()
        lease["next_seq"] = 2
        lease = self.mark_harness_ready(lease)
        run_root = self.initialize_default_journal()
        initial_text, manifest = self.wrapped_initial(lease, "next prompt")
        send_seq = lease["next_seq"]
        result = qualification_send(
            self.client,
            lease_payload=lease,
            lease_path=self.lease_path,
            seq=send_seq,
            text=initial_text,
            instruction_manifest=manifest,
            allow_live=True,
            run_root=run_root,
        )
        self.assertEqual(result["next_seq"], send_seq + 1)
        self.assertEqual(result["harness_readiness"], "operator_verified")

    def test_send_uses_double_enter_for_claude_multiline_prompt(self) -> None:
        lease, plan_payload = self._ready_lease_for_harness("claude")
        run_root = self.root / "run"
        initialize_journal(run_root, plan_payload)
        qualification_claude_lifecycle_observe(
            lease_payload=lease,
            lease_path=self.lease_path,
            receipt=claude_hook_receipt(plan_payload["harness_binding"]),
            phase="armed",
            run_root=run_root,
        )
        initial_text, manifest = self.wrapped_initial(
            lease,
            "line one\nline two",
        )
        result = qualification_send(
            self.client,
            lease_payload=lease,
            lease_path=self.lease_path,
            seq=lease["next_seq"],
            text=initial_text,
            instruction_manifest=manifest,
            allow_live=True,
            run_root=run_root,
        )
        send_events = [
            json.loads(line)
            for line in (run_root / "events.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        send_data = next(
            event["data"] for event in send_events if event.get("kind") == "qualification.send"
        )
        self.assertEqual(result["submit_key_count"], 2)
        self.assertEqual(result["submit_key_vector"], ["enter", "enter"])
        self.assertEqual(send_data["submit_key_count"], 2)
        self.assertEqual(send_data["submit_key_vector"], ["enter", "enter"])
        self.assertEqual(
            self.client.sent,
            [("input", "w2:p1", initial_text)],
        )
        self.assertEqual(self.client.sent_key_vectors, [["enter", "enter"]])

    def test_send_uses_single_enter_for_claude_single_line_prompt(self) -> None:
        lease, plan_payload = self._ready_lease_for_harness("claude")
        run_root = self.root / "run"
        initialize_journal(run_root, plan_payload)
        qualification_claude_lifecycle_observe(
            lease_payload=lease,
            lease_path=self.lease_path,
            receipt=claude_hook_receipt(plan_payload["harness_binding"]),
            phase="armed",
            run_root=run_root,
        )
        initial_text, manifest = self.wrapped_initial(
            lease,
            "establish initial turn",
        )
        qualification_send(
            self.client,
            lease_payload=lease,
            lease_path=self.lease_path,
            seq=lease["next_seq"],
            text=initial_text,
            instruction_manifest=manifest,
            allow_live=True,
            run_root=run_root,
        )
        qualification_claude_lifecycle_observe(
            lease_payload=load_json(self.lease_path),
            lease_path=self.lease_path,
            receipt=claude_hook_receipt(
                plan_payload["harness_binding"],
                user_prompt_submit=1,
                stop=1,
                prompt_sha256s=[sha256_text(initial_text)],
            ),
            phase="initial",
            run_root=run_root,
        )
        steering_lease = load_json(self.lease_path)
        result = qualification_send(
            self.client,
            lease_payload=steering_lease,
            lease_path=self.lease_path,
            seq=steering_lease["next_seq"],
            text="single line prompt",
            allow_live=True,
            run_root=run_root,
        )
        send_events = [
            json.loads(line)
            for line in (run_root / "events.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        send_data = next(
            event["data"]
            for event in reversed(send_events)
            if event.get("kind") == "qualification.send"
        )
        self.assertEqual(result["submit_key_count"], 1)
        self.assertEqual(result["submit_key_vector"], ["enter"])
        self.assertEqual(send_data["submit_key_count"], 1)
        self.assertEqual(send_data["submit_key_vector"], ["enter"])
        self.assertEqual(
            self.client.sent,
            [
                ("input", "w2:p1", initial_text),
                ("input", "w2:p1", "single line prompt"),
            ],
        )
        self.assertEqual(
            self.client.sent_key_vectors,
            [["enter", "enter"], ["enter"]],
        )

    def test_claude_unknown_send_cannot_bypass_lifecycle_by_reconciliation(
        self,
    ) -> None:
        lease, plan_payload = self._ready_lease_for_harness("claude")
        run_root = self.root / "run"
        initialize_journal(run_root, plan_payload)
        with self.assertRaises(HerdrPuppetError) as caught:
            qualification_reconcile_send(
                self.client,
                lease_payload=lease,
                lease_path=self.lease_path,
                seq=lease["next_seq"],
                text="private unknown-outcome prompt",
                evidence="independent_native_marker",
                confirm_applied=True,
                run_root=run_root,
            )
        self.assertEqual(
            caught.exception.code,
            "claude_send_reconciliation_unsupported",
        )
        self.assertEqual(self.client.sent, [])

    def test_malformed_claude_lifecycle_journal_cannot_unlock_send(self) -> None:
        lease, plan_payload = self._ready_lease_for_harness("claude")
        run_root = self.root / "run"
        initialize_journal(run_root, plan_payload)
        lifecycle = lease["harness_binding"]["lifecycle_observation"]
        append_event(
            run_root,
            make_event(
                lease["run_id"],
                "qualification.claude-lifecycle",
                "observed",
                data={
                    "phase": "armed",
                    "classification": "armed",
                    "probe_id": lifecycle["probe_id"],
                },
            ),
        )
        initial_text, manifest = self.wrapped_initial(
            lease,
            "must not send",
        )
        with self.assertRaises(HerdrPuppetError) as caught:
            qualification_send(
                self.client,
                lease_payload=lease,
                lease_path=self.lease_path,
                seq=lease["next_seq"],
                text=initial_text,
                instruction_manifest=manifest,
                allow_live=True,
                run_root=run_root,
            )
        self.assertEqual(
            caught.exception.code,
            "invalid_claude_lifecycle_journal",
        )
        self.assertEqual(self.client.sent, [])

    def test_in_row_census_reverification_ignores_only_newer_recorded_at(
        self,
    ) -> None:
        lease = self.create_lease()
        lease["shell_readiness"] = "status_verified"
        self.persist_lease(lease)
        run_root = self.initialize_default_journal()
        census = sample_census_from_binding(lease["harness_binding"])
        first = qualification_harness_census_verify(
            lease_payload=lease,
            lease_path=self.lease_path,
            census=census,
            run_root=run_root,
        )
        refreshed = copy.deepcopy(census)
        refreshed["recorded_at"] = "2099-07-30T12:00:00Z"
        second = qualification_harness_census_verify(
            lease_payload=load_json(self.lease_path),
            lease_path=self.lease_path,
            census=refreshed,
            run_root=run_root,
        )
        self.assertFalse(first["already_verified"])
        self.assertTrue(second["already_verified"])
        events = [
            event
            for event in read_events(run_root)
            if event.get("kind")
            == "qualification.harness-census-verified"
        ]
        self.assertEqual(len(events), 1)

    def test_claude_lifecycle_gates_readiness_steering_and_third_send(self) -> None:
        run_id = "run-claude-lifecycle"
        run_root = self.root / "claude-lifecycle-run"
        binding = sample_binding(harness="claude", run_id=run_id)
        initial_rendered, initial_manifest = compile_instruction_wrapper(
            binding_value=binding,
            run_id=run_id,
            task="private initial body",
        )
        initial_text = initial_rendered.decode("utf-8")
        steering_text = "private steering body"
        initial_sha256 = sha256_text(initial_text)
        steering_sha256 = sha256_text(steering_text)
        plan_payload = plan(
            self.client,
            session="operator-session",
            workspace_id="w2",
            workspace_label="worker-02",
            expected_ssh_target="worker@worker-02.example",
            run_id=run_id,
            harness="claude",
            repo="example/SaariusSkills",
            worktree="/redacted/worktree",
            proof_root=str(run_root.resolve()),
            harness_binding=binding,
            live_mutation_authorized=True,
        )
        initialize_journal(run_root, plan_payload)
        lease = create_qualification_tab(
            self.client,
            plan_payload=plan_payload,
            lease_path=self.lease_path,
            allow_live=True,
            settle_seconds=0.1,
            run_root=run_root,
        )
        lease["shell_readiness"] = "status_verified"
        lease["next_seq"] = 2
        self.persist_lease(lease)
        lease = self.verify_in_row_census(lease, run_root)
        with self.assertRaises(HerdrPuppetError) as caught:
            qualification_harness_launch(
                self.client,
                lease_payload=lease,
                lease_path=self.lease_path,
                seq=2,
                allow_live=True,
                run_root=run_root,
            )
        self.assertEqual(
            caught.exception.code,
            "claude_marker_registration_incomplete",
        )
        self.assertEqual(self.client.ran, [])
        lease = self.register_claude_marker_files(lease, run_root)
        qualification_harness_launch(
            self.client,
            lease_payload=lease,
            lease_path=self.lease_path,
            seq=2,
            allow_live=True,
            run_root=run_root,
        )
        launched = load_json(self.lease_path)
        with self.assertRaises(HerdrPuppetError) as caught:
            qualification_harness_ready(
                self.client,
                lease_payload=launched,
                lease_path=self.lease_path,
                source_repo="example/SaariusSkills",
                source_worktree="/redacted/worktree",
                operator_id="test-operator",
                evidence="operator_observed_ready_input",
                confirm_ready=True,
                allow_live=True,
                run_root=run_root,
            )
        self.assertEqual(caught.exception.code, "claude_lifecycle_not_proven")

        armed = qualification_claude_lifecycle_observe(
            lease_payload=launched,
            lease_path=self.lease_path,
            receipt=claude_hook_receipt(binding),
            phase="armed",
            run_root=run_root,
        )
        self.assertEqual(armed["classification"], "armed")
        armed_again = qualification_claude_lifecycle_observe(
            lease_payload=launched,
            lease_path=self.lease_path,
            receipt=claude_hook_receipt(binding),
            phase="armed",
            run_root=run_root,
        )
        self.assertTrue(armed_again["already_observed"])
        with self.assertRaises(HerdrPuppetError) as caught:
            qualification_claude_lifecycle_observe(
                lease_payload=launched,
                lease_path=self.lease_path,
                receipt=claude_hook_receipt(binding),
                phase="initial",
                run_root=run_root,
            )
        self.assertEqual(
            caught.exception.code,
            "claude_lifecycle_send_count_mismatch",
        )
        qualification_harness_ready(
            self.client,
            lease_payload=load_json(self.lease_path),
            lease_path=self.lease_path,
            source_repo="example/SaariusSkills",
            source_worktree="/redacted/worktree",
            operator_id="test-operator",
            evidence="operator_observed_ready_input",
            confirm_ready=True,
            allow_live=True,
            run_root=run_root,
        )
        ready = load_json(self.lease_path)
        qualification_send(
            self.client,
            lease_payload=ready,
            lease_path=self.lease_path,
            seq=ready["next_seq"],
            text=initial_text,
            instruction_manifest=initial_manifest,
            allow_live=True,
            run_root=run_root,
        )
        armed_after_initial = qualification_claude_lifecycle_observe(
            lease_payload=load_json(self.lease_path),
            lease_path=self.lease_path,
            receipt=claude_hook_receipt(binding),
            phase="armed",
            run_root=run_root,
        )
        self.assertTrue(armed_after_initial["already_observed"])
        with self.assertRaises(HerdrPuppetError) as caught:
            qualification_beacon_wait(
                self.client,
                lease_payload=load_json(self.lease_path),
                lease_path=self.lease_path,
                nonce="CLAUDE-INITIAL-1",
                lines=80,
                allow_live=True,
                run_root=run_root,
            )
        self.assertEqual(caught.exception.code, "claude_lifecycle_not_proven")
        with self.assertRaises(HerdrPuppetError) as caught:
            qualification_claude_lifecycle_observe(
                lease_payload=load_json(self.lease_path),
                lease_path=self.lease_path,
                receipt=claude_hook_receipt(
                    binding,
                    user_prompt_submit=1,
                    prompt_sha256s=["f" * 64],
                ),
                phase="initial",
                run_root=run_root,
            )
        self.assertEqual(
            caught.exception.code,
            "invalid_claude_hook_receipt",
        )
        pending = qualification_claude_lifecycle_observe(
            lease_payload=load_json(self.lease_path),
            lease_path=self.lease_path,
            receipt=claude_hook_receipt(
                binding,
                user_prompt_submit=1,
                prompt_sha256s=[initial_sha256],
            ),
            phase="initial",
            run_root=run_root,
        )
        self.assertEqual(pending["classification"], "response_pending")
        pending_again = qualification_claude_lifecycle_observe(
            lease_payload=load_json(self.lease_path),
            lease_path=self.lease_path,
            receipt=claude_hook_receipt(
                binding,
                user_prompt_submit=1,
                prompt_sha256s=[initial_sha256],
            ),
            phase="initial",
            run_root=run_root,
        )
        self.assertTrue(pending_again["already_observed"])
        with self.assertRaises(HerdrPuppetError) as caught:
            qualification_claude_lifecycle_observe(
                lease_payload=load_json(self.lease_path),
                lease_path=self.lease_path,
                receipt=claude_hook_receipt(binding),
                phase="initial",
                run_root=run_root,
            )
        self.assertEqual(
            caught.exception.code,
            "claude_lifecycle_receipt_regression",
        )
        initial = qualification_claude_lifecycle_observe(
            lease_payload=load_json(self.lease_path),
            lease_path=self.lease_path,
            receipt=claude_hook_receipt(
                binding,
                user_prompt_submit=1,
                stop=1,
                prompt_sha256s=[initial_sha256],
            ),
            phase="initial",
            run_root=run_root,
        )
        self.assertEqual(initial["classification"], "response_completed")
        with self.assertRaises(HerdrPuppetError) as caught:
            qualification_claude_lifecycle_observe(
                lease_payload=load_json(self.lease_path),
                lease_path=self.lease_path,
                receipt=claude_hook_receipt(
                    binding,
                    user_prompt_submit=1,
                    stop_failure=1,
                    prompt_sha256s=[initial_sha256],
                ),
                phase="initial",
                run_root=run_root,
            )
        self.assertEqual(
            caught.exception.code,
            "claude_lifecycle_terminal_conflict",
        )
        after_initial = load_json(self.lease_path)
        qualification_send(
            self.client,
            lease_payload=after_initial,
            lease_path=self.lease_path,
            seq=after_initial["next_seq"],
            text=steering_text,
            allow_live=True,
            run_root=run_root,
        )
        initial_after_steering = qualification_claude_lifecycle_observe(
            lease_payload=load_json(self.lease_path),
            lease_path=self.lease_path,
            receipt=claude_hook_receipt(
                binding,
                user_prompt_submit=1,
                stop=1,
                prompt_sha256s=[initial_sha256],
            ),
            phase="initial",
            run_root=run_root,
        )
        self.assertTrue(initial_after_steering["already_observed"])
        steering = qualification_claude_lifecycle_observe(
            lease_payload=load_json(self.lease_path),
            lease_path=self.lease_path,
            receipt=claude_hook_receipt(
                binding,
                user_prompt_submit=2,
                stop=2,
                prompt_sha256s=[initial_sha256, steering_sha256],
            ),
            phase="steering",
            run_root=run_root,
        )
        self.assertEqual(steering["classification"], "response_completed")
        after_steering = load_json(self.lease_path)
        with self.assertRaises(HerdrPuppetError) as caught:
            qualification_send(
                self.client,
                lease_payload=after_steering,
                lease_path=self.lease_path,
                seq=after_steering["next_seq"],
                text="must not become a third bounded send",
                allow_live=True,
                run_root=run_root,
            )
        self.assertEqual(caught.exception.code, "claude_lifecycle_send_limit")
        events = read_events(run_root)
        lifecycle_events = [
            event
            for event in events
            if event.get("kind") == "qualification.claude-lifecycle"
        ]
        self.assertEqual(len(lifecycle_events), 4)
        send_events = [
            event
            for event in events
            if event.get("kind") == "qualification.send"
        ]
        self.assertEqual(len(send_events), 2)
        terminal_by_phase = {
            event["data"]["phase"]: event
            for event in lifecycle_events
            if event["data"]["classification"] == "response_completed"
        }
        for index, phase in enumerate(("initial", "steering")):
            lifecycle_event = terminal_by_phase[phase]
            send_event = send_events[index]
            self.assertEqual(lifecycle_event["result"], "observed")
            self.assertEqual(lifecycle_event["seq"], send_event["seq"])
            self.assertEqual(
                lifecycle_event["prompt_sha256"],
                send_event["prompt_sha256"],
            )
            self.assertEqual(
                lifecycle_event["data"]["send_seq"],
                send_event["seq"],
            )
            self.assertIs(
                lifecycle_event["data"]["receipt_verified"],
                True,
            )
        refreshed = refresh_state(run_root, after_steering)
        self.assertEqual(refreshed["result"], "ok")
        private_surface = "\n".join(
            [
                (run_root / "events.jsonl").read_text(encoding="utf-8"),
                json.dumps(summarize_journal(run_root), sort_keys=True),
                (run_root / "STATE.md").read_text(encoding="utf-8"),
            ]
        )
        lifecycle = binding["lifecycle_observation"]
        for private_value in (
            initial_text,
            steering_text,
            lifecycle["marker_root"],
            lifecycle["helper"]["path"],
            lifecycle["interpreter"]["path"],
            binding["regular_launch"]["argv"][3],
        ):
            self.assertNotIn(private_value, private_surface)

    def test_send_uses_single_enter_for_non_claude_multiline_prompt(self) -> None:
        lease = self.mark_harness_ready(self.create_lease())
        run_root = self.root / "run"
        initialize_journal(run_root, self.plan)
        initial_text, manifest = self.wrapped_initial(
            lease,
            "line one\nline two",
        )
        result = qualification_send(
            self.client,
            lease_payload=lease,
            lease_path=self.lease_path,
            seq=lease["next_seq"],
            text=initial_text,
            instruction_manifest=manifest,
            allow_live=True,
            run_root=run_root,
        )
        send_events = [
            json.loads(line)
            for line in (run_root / "events.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        send_data = next(
            event["data"] for event in send_events if event.get("kind") == "qualification.send"
        )
        self.assertEqual(result["submit_key_count"], 1)
        self.assertEqual(result["submit_key_vector"], ["enter"])
        self.assertEqual(send_data["submit_key_count"], 1)
        self.assertEqual(send_data["submit_key_vector"], ["enter"])
        self.assertEqual(
            self.client.sent,
            [("input", "w2:p1", initial_text)],
        )
        self.assertEqual(self.client.sent_key_vectors, [["enter"]])

    def test_send_hashes_prompt_and_atomically_advances_sequence(self) -> None:
        lease = self.create_lease()
        lease = self.mark_harness_ready(lease)
        run_root = self.root / "run"
        initialize_journal(run_root, self.plan)
        initial_text, manifest = self.wrapped_initial(
            lease,
            "bounded prompt",
        )
        result = qualification_send(
            self.client,
            lease_payload=lease,
            lease_path=self.lease_path,
            seq=lease["next_seq"],
            text=initial_text,
            instruction_manifest=manifest,
            allow_live=True,
            run_root=run_root,
        )
        updated = json.loads(self.lease_path.read_text(encoding="utf-8"))
        events = (run_root / "events.jsonl").read_text(encoding="utf-8")
        self.assertEqual(result["next_seq"], lease["next_seq"] + 1)
        self.assertTrue(result["transport_acknowledged"])
        self.assertEqual(result["acceptance_scope"], "herdr_pane_input_only")
        self.assertEqual(result["outcome"], "pane_input_accepted")
        self.assertEqual(result["harness_readiness"], "operator_verified")
        self.assertEqual(result["harness_acceptance"], "operator_verified")
        self.assertEqual(updated["next_seq"], lease["next_seq"] + 1)
        self.assertNotIn("bounded prompt", json.dumps(result))
        self.assertNotIn("bounded prompt", events)
        self.assertEqual(
            self.client.sent,
            [("input", "w2:p1", initial_text)],
        )

    def test_send_journal_failure_fails_closed_against_extra_initial(self) -> None:
        lease = self.mark_harness_ready(self.create_lease())
        run_root = self.initialize_default_journal()
        initial_text, manifest = self.wrapped_initial(
            lease,
            "first bounded task",
        )
        def fail_completed_send_event(
            run_path: Path,
            event: dict[str, Any],
        ) -> None:
            if event.get("kind") == "qualification.send":
                raise RuntimeError("simulated journal failure")
            append_event(run_path, event)

        with mock.patch(
            "herdr_puppet_lib.core.append_event",
            side_effect=fail_completed_send_event,
        ):
            with self.assertRaisesRegex(RuntimeError, "journal failure"):
                qualification_send(
                    self.client,
                    lease_payload=lease,
                    lease_path=self.lease_path,
                    seq=lease["next_seq"],
                    text=initial_text,
                    instruction_manifest=manifest,
                    allow_live=True,
                    run_root=run_root,
                )
        advanced = load_json(self.lease_path)
        self.assertEqual(len(advanced["interactive_sends"]), 1)
        self.assertIsNone(advanced["pending_interactive_send"])
        replacement_text, replacement_manifest = self.wrapped_initial(
            advanced,
            "must not become another initial task",
        )
        with self.assertRaises(HerdrPuppetError) as caught:
            qualification_send(
                self.client,
                lease_payload=advanced,
                lease_path=self.lease_path,
                seq=advanced["next_seq"],
                text=replacement_text,
                instruction_manifest=replacement_manifest,
                allow_live=True,
                run_root=run_root,
            )
        self.assertEqual(
            caught.exception.code,
            "qualification_send_history_diverged",
        )
        self.assertEqual(len(self.client.sent), 1)

    def test_send_ack_then_finalize_failure_blocks_replay(self) -> None:
        lease = self.mark_harness_ready(self.create_lease())
        run_root = self.initialize_default_journal()
        initial_text, manifest = self.wrapped_initial(
            lease,
            "one bounded task",
        )

        def fail_completed_lease_write(
            path: Path,
            payload: dict[str, Any],
        ) -> None:
            if (
                payload.get("pending_interactive_send") is None
                and payload.get("interactive_sends")
            ):
                raise RuntimeError("simulated lease finalize failure")
            atomic_json(path, payload)

        with mock.patch(
            "herdr_puppet_lib.core.atomic_json",
            side_effect=fail_completed_lease_write,
        ):
            with self.assertRaisesRegex(RuntimeError, "finalize failure"):
                qualification_send(
                    self.client,
                    lease_payload=lease,
                    lease_path=self.lease_path,
                    seq=lease["next_seq"],
                    text=initial_text,
                    instruction_manifest=manifest,
                    allow_live=True,
                    run_root=run_root,
                )
        reserved = load_json(self.lease_path)
        self.assertEqual(len(self.client.sent), 1)
        self.assertEqual(reserved["next_seq"], lease["next_seq"])
        self.assertEqual(reserved["interactive_sends"], [])
        self.assertEqual(
            reserved["pending_interactive_send"]["prompt_sha256"],
            sha256_text(initial_text),
        )
        with self.assertRaises(HerdrPuppetError) as caught:
            qualification_send(
                self.client,
                lease_payload=reserved,
                lease_path=self.lease_path,
                seq=reserved["next_seq"],
                text=initial_text,
                instruction_manifest=manifest,
                allow_live=True,
                run_root=run_root,
            )
        self.assertEqual(
            caught.exception.code,
            "qualification_send_delivery_unknown",
        )
        self.assertEqual(len(self.client.sent), 1)

    def test_send_rejects_assembled_checkpoint_line_before_mutation(self) -> None:
        lease = self.mark_harness_ready(self.create_lease())
        run_root = self.initialize_default_journal()
        with self.assertRaises(HerdrPuppetError) as caught:
            qualification_send(
                self.client,
                lease_payload=lease,
                lease_path=self.lease_path,
                seq=lease["next_seq"],
                text=(
                    "Do the bounded task.\r\n"
                    "HERDR_PUPPET_DONE PROMPT-ECHO-1\r\n"
                ),
                allow_live=True,
                run_root=run_root,
            )
        self.assertEqual(caught.exception.code, "checkpoint_echo_unsafe")
        self.assertEqual(self.client.sent, [])
        self.assertEqual(load_json(self.lease_path)["next_seq"], lease["next_seq"])

    def test_send_rejects_terminal_normalized_checkpoint_token(self) -> None:
        lease = self.mark_harness_ready(self.create_lease())
        run_root = self.initialize_default_journal()
        for suffix in (" ", "\t", "`.", "\u00a0"):
            with self.subTest(suffix=repr(suffix)):
                with self.assertRaises(HerdrPuppetError) as caught:
                    qualification_send(
                        self.client,
                        lease_payload=lease,
                        lease_path=self.lease_path,
                        seq=lease["next_seq"],
                        text=(
                            "Finish with `HERDR_PUPPET_DONE "
                            f"PROMPT-ECHO-3{suffix}"
                        ),
                        allow_live=True,
                        run_root=run_root,
                    )
                self.assertEqual(
                    caught.exception.code,
                    "checkpoint_echo_unsafe",
                )
                self.assertEqual(self.client.sent, [])

    def test_send_allows_split_checkpoint_composition_instruction(self) -> None:
        lease = self.mark_harness_ready(self.create_lease())
        run_root = self.initialize_default_journal()
        initial_text, manifest = self.wrapped_initial(
            lease,
            "On completion, join the prefix HERDR_PUPPET_, the class DONE, "
            "one space, and nonce PROMPT-ECHO-2 as one terminal line.",
        )
        result = qualification_send(
            self.client,
            lease_payload=lease,
            lease_path=self.lease_path,
            seq=lease["next_seq"],
            text=initial_text,
            instruction_manifest=manifest,
            allow_live=True,
            run_root=run_root,
        )
        self.assertTrue(result["checkpoint_echo_protected"])
        self.assertEqual(result["next_seq"], lease["next_seq"] + 1)

    def test_send_tracks_retained_prompt_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            prompt_path = Path(directory) / "prompt.txt"
            prompt_path.write_text("from file", encoding="utf-8")
            lease = self.create_lease()
            lease = self.mark_harness_ready(lease)
            run_root = self.root / "run"
            initialize_journal(run_root, self.plan)
            initial_text, manifest = self.wrapped_initial(
                lease,
                "via file",
            )
            result = qualification_send(
                self.client,
                lease_payload=lease,
                lease_path=self.lease_path,
                seq=lease["next_seq"],
                text=initial_text,
                text_file=str(prompt_path),
                instruction_manifest=manifest,
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
        run_root = self.initialize_default_journal()
        initial_text, manifest = self.wrapped_initial(
            lease,
            "missing file",
        )
        result = qualification_send(
            self.client,
            lease_payload=lease,
            lease_path=self.lease_path,
            seq=lease["next_seq"],
            text=initial_text,
            text_file=str(missing_prompt),
            instruction_manifest=manifest,
            allow_live=True,
            run_root=run_root,
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
        run_root = self.initialize_default_journal()
        with self.assertRaisesRegex(HerdrPuppetError, "explicit evidence"):
            qualification_reconcile_send(
                self.client,
                lease_payload=lease,
                lease_path=self.lease_path,
                seq=1,
                text="already applied",
                evidence="remote_process_match",
                confirm_applied=False,
                run_root=run_root,
            )
        self.assertEqual(
            json.loads(self.lease_path.read_text(encoding="utf-8"))["next_seq"],
            1,
        )
        with self.assertRaisesRegex(HerdrPuppetError, "bounded"):
            qualification_reconcile_send(
                self.client,
                lease_payload=lease,
                lease_path=self.lease_path,
                seq=1,
                text="already applied",
                evidence="x" * 1025,
                confirm_applied=True,
                run_root=run_root,
            )
        self.assertEqual(
            json.loads(self.lease_path.read_text(encoding="utf-8"))["next_seq"],
            1,
        )

    def test_partial_send_reconciliation_advances_without_herdr_mutation(self) -> None:
        lease = self.create_lease()
        lease = self.mark_harness_ready(lease)
        run_root = self.initialize_default_journal()
        initial_text, manifest = self.wrapped_initial(
            lease,
            "establish initial turn",
        )
        qualification_send(
            self.client,
            lease_payload=lease,
            lease_path=self.lease_path,
            seq=lease["next_seq"],
            text=initial_text,
            instruction_manifest=manifest,
            allow_live=True,
            run_root=run_root,
        )
        steering_lease = load_json(self.lease_path)
        self.client.read_payload = (
            "HERDR_PUPPET_STATUS RECONCILE-INITIAL-1"
        )
        qualification_beacon_wait(
            self.client,
            lease_payload=steering_lease,
            lease_path=self.lease_path,
            nonce="RECONCILE-INITIAL-1",
            allow_live=True,
            run_root=run_root,
        )
        steering_lease = load_json(self.lease_path)
        sent_before = list(self.client.sent)
        with mock.patch.object(
            self.client,
            "run_input",
            side_effect=RuntimeError("simulated unknown delivery"),
        ):
            with self.assertRaisesRegex(RuntimeError, "unknown delivery"):
                qualification_send(
                    self.client,
                    lease_payload=steering_lease,
                    lease_path=self.lease_path,
                    seq=steering_lease["next_seq"],
                    text="already applied",
                    allow_live=True,
                    run_root=run_root,
                )
        steering_lease = load_json(self.lease_path)
        self.assertEqual(
            steering_lease["pending_interactive_send"]["phase"],
            "steering",
        )
        result = qualification_reconcile_send(
            self.client,
            lease_payload=steering_lease,
            lease_path=self.lease_path,
            seq=steering_lease["next_seq"],
            text="already applied",
            evidence="herdr_success_exit+remote_process_match",
            confirm_applied=True,
            run_root=run_root,
        )
        self.assertEqual(result["next_seq"], steering_lease["next_seq"] + 1)
        self.assertFalse(result["herdr_mutated"])
        self.assertEqual(self.client.sent, sent_before)

    def test_reconciliation_repairs_missing_completion_event_idempotently(
        self,
    ) -> None:
        lease = self.mark_harness_ready(self.create_lease())
        run_root = self.initialize_default_journal()
        initial_text, manifest = self.wrapped_initial(
            lease,
            "establish initial turn",
        )
        qualification_send(
            self.client,
            lease_payload=lease,
            lease_path=self.lease_path,
            seq=lease["next_seq"],
            text=initial_text,
            instruction_manifest=manifest,
            allow_live=True,
            run_root=run_root,
        )
        steering_lease = load_json(self.lease_path)
        self.client.read_payload = "HERDR_PUPPET_STATUS RECONCILE-REPAIR-1"
        qualification_beacon_wait(
            self.client,
            lease_payload=steering_lease,
            lease_path=self.lease_path,
            nonce="RECONCILE-REPAIR-1",
            allow_live=True,
            run_root=run_root,
        )
        steering_lease = load_json(self.lease_path)
        steering_seq = steering_lease["next_seq"]
        with mock.patch.object(
            self.client,
            "run_input",
            side_effect=RuntimeError("simulated unknown delivery"),
        ):
            with self.assertRaisesRegex(RuntimeError, "unknown delivery"):
                qualification_send(
                    self.client,
                    lease_payload=steering_lease,
                    lease_path=self.lease_path,
                    seq=steering_seq,
                    text="already applied",
                    allow_live=True,
                    run_root=run_root,
                )
        pending = load_json(self.lease_path)

        def fail_reconcile_event(
            run_path: Path,
            event: dict[str, Any],
        ) -> None:
            if event.get("kind") == "qualification.send-reconciled":
                raise RuntimeError("simulated reconcile journal failure")
            append_event(run_path, event)

        with mock.patch(
            "herdr_puppet_lib.core.append_event",
            side_effect=fail_reconcile_event,
        ):
            with self.assertRaisesRegex(RuntimeError, "journal failure"):
                qualification_reconcile_send(
                    self.client,
                    lease_payload=pending,
                    lease_path=self.lease_path,
                    seq=steering_seq,
                    text="already applied",
                    evidence="source_bound_terminal_artifact",
                    confirm_applied=True,
                    run_root=run_root,
                )
        completed = load_json(self.lease_path)
        self.assertIsNone(completed["pending_interactive_send"])
        self.assertEqual(
            completed["interactive_sends"][-1]["transport"],
            "reconciled",
        )
        repaired = qualification_reconcile_send(
            self.client,
            lease_payload=completed,
            lease_path=self.lease_path,
            seq=steering_seq,
            text="already applied",
            evidence="source_bound_terminal_artifact",
            confirm_applied=True,
            run_root=run_root,
        )
        self.assertTrue(repaired["already_reconciled"])
        self.assertTrue(repaired["completion_event_repaired"])
        self.assertEqual(
            len(
                [
                    event
                    for event in read_events(run_root)
                    if event.get("kind") == "qualification.send-reconciled"
                ]
            ),
            1,
        )
        with self.assertRaisesRegex(
            HerdrPuppetError,
            "does not match the durable",
        ):
            qualification_reconcile_send(
                self.client,
                lease_payload=load_json(self.lease_path),
                lease_path=self.lease_path,
                seq=steering_seq,
                text="already applied",
                evidence="contradictory_evidence",
                confirm_applied=True,
                run_root=run_root,
            )
        with mock.patch.object(
            self.client,
            "snapshot",
            side_effect=AssertionError("idempotent retry touched Herdr"),
        ):
            replayed = qualification_reconcile_send(
                self.client,
                lease_payload=load_json(self.lease_path),
                lease_path=self.lease_path,
                seq=steering_seq,
                text="already applied",
                evidence="source_bound_terminal_artifact",
                confirm_applied=True,
                run_root=run_root,
            )
        self.assertTrue(replayed["already_reconciled"])
        self.assertEqual(
            replayed["evidence"],
            "source_bound_terminal_artifact",
        )

    def test_preserved_lease_rejects_run_send_reconciliation_and_waits(
        self,
    ) -> None:
        lease = self.create_lease()
        lease["state"] = "preserved"
        self.persist_lease(lease)
        run_root = self.root / "run"
        initialize_journal(run_root, self.plan)
        for operation in (
            lambda: qualification_run(
                self.client,
                lease_payload=lease,
                lease_path=self.lease_path,
                seq=1,
                command="do not run",
                allow_live=True,
                run_root=run_root,
            ),
            lambda: qualification_send(
                self.client,
                lease_payload=lease,
                lease_path=self.lease_path,
                seq=1,
                text="do not send",
                allow_live=True,
                run_root=run_root,
            ),
            lambda: qualification_reconcile_send(
                self.client,
                lease_payload=lease,
                lease_path=self.lease_path,
                seq=1,
                text="do not reconcile",
                evidence="none",
                confirm_applied=True,
                run_root=run_root,
            ),
            lambda: qualification_token_probe(
                self.client,
                lease_payload=lease,
                lease_path=self.lease_path,
                nonce="DO-NOT-PROBE",
                allow_live=True,
                run_root=run_root,
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

    def test_historical_preserve_remains_compatible_without_journal(self) -> None:
        historical = historical_lease_v1(self.create_lease())
        self.persist_lease(historical)
        self.assertFalse(self.default_run_root().exists())
        result = preserve_lease(
            lease_payload=historical,
            lease_path=self.lease_path,
            reason="operator_stop",
        )
        preserved = load_json(self.lease_path)
        self.assertEqual(result["state"], "preserved")
        self.assertEqual(preserved["schema"], "herdr-puppet.lease.v1")
        self.assertEqual(preserved["state"], "preserved")
        self.assertFalse(self.default_run_root().exists())

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

    def test_status_beacon_accepts_tui_horizontal_presentation_padding(
        self,
    ) -> None:
        lease = self.create_lease()
        run_root = self.root / "run"
        initialize_journal(run_root, self.plan)
        lease = self.submit_for_beacon(lease)
        self.client.read_payload = (
            "\t\u00a0 HERDR_PUPPET_STATUS CHECKPOINT-88 \t\u00a0"
        )
        result = qualification_beacon_wait(
            self.client,
            lease_payload=lease,
            lease_path=self.lease_path,
            nonce="CHECKPOINT-88",
            allow_live=True,
            lines=20,
            run_root=run_root,
        )
        self.assertEqual(result["result"], "observed")
        self.assertEqual(result["checkpoint"], "STATUS")
        self.assertFalse(result["auto_preserved"])

    def test_non_codex_beacon_wait_rejects_tui_bullet(self) -> None:
        lease = self.create_lease()
        run_root = self.root / "run"
        initialize_journal(run_root, self.plan)
        lease = self.submit_for_beacon(lease)
        self.client.read_payload = (
            "• HERDR_PUPPET_STATUS CHECKPOINT-88"
        )
        result = qualification_beacon_wait(
            self.client,
            lease_payload=lease,
            lease_path=self.lease_path,
            nonce="CHECKPOINT-88",
            allow_live=True,
            lines=20,
            timeout_ms=1,
            run_root=run_root,
        )
        self.assertEqual(result["result"], "not_matched")
        self.assertIsNone(result["checkpoint"])

    def test_codex_beacon_wait_accepts_native_assistant_bullet(self) -> None:
        lease, run_root = self.ready_codex_submission()
        self.client.read_payload = (
            "  • HERDR_PUPPET_STATUS CHECKPOINT-88 \u00a0"
        )
        result = qualification_beacon_wait(
            self.client,
            lease_payload=lease,
            lease_path=self.lease_path,
            nonce="CHECKPOINT-88",
            allow_live=True,
            lines=20,
            run_root=run_root,
        )
        self.assertEqual(result["result"], "observed")
        self.assertEqual(result["checkpoint"], "STATUS")
        self.assertFalse(result["auto_preserved"])
        serialized = json.dumps(result)
        events = (run_root / "events.jsonl").read_text(encoding="utf-8")
        self.assertNotIn("CHECKPOINT-88", serialized)
        self.assertNotIn("CHECKPOINT-88", events)
        self.assertNotIn("bounded prompt", serialized)
        self.assertNotIn("bounded prompt", events)

    def test_early_done_preserves_without_qualifying_two_turn_row(self) -> None:
        lease, run_root = self.ready_codex_submission()
        self.client.read_payload = (
            "• HERDR_PUPPET_DONE EARLY-DONE-CODEX-1"
        )
        result = qualification_beacon_wait(
            self.client,
            lease_payload=lease,
            lease_path=self.lease_path,
            nonce="EARLY-DONE-CODEX-1",
            allow_live=True,
            run_root=run_root,
        )
        self.assertEqual(result["checkpoint"], "DONE")
        self.assertTrue(result["auto_preserved"])
        self.assertEqual(result["interactive_send_count"], 1)
        self.assertFalse(result["qualification_complete"])

    def test_two_turn_done_marks_qualification_complete(self) -> None:
        lease, run_root = self.ready_codex_submission()
        self.client.read_payload = (
            "• HERDR_PUPPET_STATUS CODEX-INITIAL-OK-1"
        )
        first = qualification_beacon_wait(
            self.client,
            lease_payload=lease,
            lease_path=self.lease_path,
            nonce="CODEX-INITIAL-OK-1",
            allow_live=True,
            run_root=run_root,
        )
        self.assertFalse(first["qualification_complete"])
        steering_lease = load_json(self.lease_path)
        qualification_send(
            self.client,
            lease_payload=steering_lease,
            lease_path=self.lease_path,
            seq=steering_lease["next_seq"],
            text="separate steering turn",
            allow_live=True,
            run_root=run_root,
        )
        self.client.read_payload = (
            "• HERDR_PUPPET_DONE CODEX-FINAL-DONE-1"
        )
        final = qualification_beacon_wait(
            self.client,
            lease_payload=load_json(self.lease_path),
            lease_path=self.lease_path,
            nonce="CODEX-FINAL-DONE-1",
            allow_live=True,
            run_root=run_root,
        )
        self.assertEqual(final["interactive_send_count"], 2)
        self.assertTrue(final["qualification_complete"])
        self.assertEqual(final["lease_state"], "preserved")

    def test_post_readiness_beacon_rejects_untracked_sequence_advance(
        self,
    ) -> None:
        lease, run_root = self.ready_codex_submission()
        lease["next_seq"] += 1
        self.persist_lease(lease)
        with self.assertRaises(HerdrPuppetError) as caught:
            qualification_beacon_wait(
                self.client,
                lease_payload=lease,
                lease_path=self.lease_path,
                nonce="STALE-SEND-BEACON-1",
                allow_live=True,
                run_root=run_root,
            )
        self.assertEqual(
            caught.exception.code,
            "beacon_submission_not_latest_interactive_send",
        )

    def test_codex_beacon_wait_rejects_non_native_bullet_shape(self) -> None:
        self.assert_ready_codex_checkpoint_miss(
            "• note: HERDR_PUPPET_STATUS CHECKPOINT-88"
        )

    def test_codex_beacon_wait_rejects_bullet_without_separation(self) -> None:
        self.assert_ready_codex_checkpoint_miss(
            "•HERDR_PUPPET_STATUS CHECKPOINT-88"
        )

    def test_codex_beacon_wait_rejects_double_bullet(self) -> None:
        self.assert_ready_codex_checkpoint_miss(
            "•• HERDR_PUPPET_STATUS CHECKPOINT-88"
        )

    def test_codex_beacon_wait_rejects_ascii_bullet(self) -> None:
        self.assert_ready_codex_checkpoint_miss(
            "- HERDR_PUPPET_STATUS CHECKPOINT-88"
        )

    def test_codex_beacon_wait_rejects_trailing_prose(self) -> None:
        self.assert_ready_codex_checkpoint_miss(
            "• HERDR_PUPPET_STATUS CHECKPOINT-88 extra"
        )

    def test_pre_readiness_codex_beacon_wait_rejects_tui_bullet(self) -> None:
        self.plan = make_plan(self.client, harness="codex")
        self.plan["proof_root"] = str((self.root / "run").resolve())
        refresh_selected_authority(self.plan)
        lease = self.create_lease()
        run_root = self.root / "run"
        initialize_journal(run_root, self.plan)
        lease = self.submit_for_beacon(lease)
        self.client.read_payload = (
            "• HERDR_PUPPET_STATUS CHECKPOINT-88"
        )
        result = qualification_beacon_wait(
            self.client,
            lease_payload=lease,
            lease_path=self.lease_path,
            nonce="CHECKPOINT-88",
            allow_live=True,
            lines=20,
            timeout_ms=1,
            run_root=run_root,
        )
        self.assertEqual(result["result"], "not_matched")
        self.assertIsNone(result["checkpoint"])

    def test_codex_send_rejects_bulleted_assembled_checkpoint(self) -> None:
        lease, _bound_plan = self._ready_lease_for_harness("codex")
        run_root = self.root / "run"
        initialize_journal(run_root, _bound_plan)
        with self.assertRaises(HerdrPuppetError) as caught:
            qualification_send(
                self.client,
                lease_payload=lease,
                lease_path=self.lease_path,
                seq=lease["next_seq"],
                text="• HERDR_PUPPET_DONE PROMPT-ECHO-4",
                allow_live=True,
                run_root=run_root,
            )
        self.assertEqual(caught.exception.code, "checkpoint_echo_unsafe")
        self.assertEqual(self.client.sent, [])

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

    def test_beacon_wait_accepts_max_nonce_length(self) -> None:
        lease = self.create_lease()
        run_root = self.root / "run"
        initialize_journal(run_root, self.plan)
        lease = self.submit_for_beacon(lease)
        nonce = "N" * 24
        result = qualification_beacon_wait(
            self.client,
            lease_payload=lease,
            lease_path=self.lease_path,
            nonce=nonce,
            allow_live=True,
            timeout_ms=1,
            run_root=run_root,
        )
        self.assertEqual(result["attempt"], 1)
        self.assertEqual(result["result"], "not_matched")

    def test_beacon_wait_rejects_nonce_longer_than_max(self) -> None:
        lease = self.create_lease()
        run_root = self.root / "run"
        initialize_journal(run_root, self.plan)
        lease = self.submit_for_beacon(lease)
        nonce = "N" * 25
        with self.assertRaises(HerdrPuppetError) as caught:
            qualification_beacon_wait(
                self.client,
                lease_payload=lease,
                lease_path=self.lease_path,
                nonce=nonce,
                allow_live=True,
                timeout_ms=1,
                run_root=run_root,
            )
        self.assertEqual(caught.exception.code, "invalid_beacon_nonce")

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
        refresh_selected_authority(copied_plan)
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
            run_root=run_root,
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

    def test_shell_command_after_harness_launch_is_rejected(self) -> None:
        lease = self.create_lease()
        lease = self.mark_harness_launched(lease)
        run_root = self.root / "run"
        initialize_journal(run_root, self.plan)
        with self.assertRaises(HerdrPuppetError) as caught:
            qualification_run(
                self.client,
                lease_payload=lease,
                lease_path=self.lease_path,
                seq=lease["next_seq"],
                command="python3 late-census.py",
                allow_live=True,
                run_root=run_root,
            )
        self.assertEqual(
            caught.exception.code,
            "shell_command_after_harness_launch_forbidden",
        )
        self.assertEqual(self.client.ran, [])

    def test_token_probe_rejects_stale_active_payload_after_preserve(self) -> None:
        lease = self.create_lease()
        run_root = self.initialize_default_journal()
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
                    run_root=run_root,
                )
        self.assertEqual(caught.exception.code, "stale_lease_payload")
        wait_output.assert_not_called()

    def test_token_probe_rejects_stale_preserved_caller_payload(self) -> None:
        lease = self.create_lease()
        run_root = self.initialize_default_journal()
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
                    run_root=run_root,
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
        run_root = self.initialize_default_journal()
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
            run_root=run_root,
            lines=20,
        )
        self.assertTrue(result["matched"])
        self.assertEqual(result["revision"], 7)
        self.assertNotIn("TOKEN-12345", json.dumps(result))
        self.assertNotIn("unrelated", json.dumps(result))
        self.assertFalse(result["pane_text_emitted"])

    def test_token_probe_accepts_raw_herdr_text_without_emitting_it(self) -> None:
        lease = self.create_lease()
        run_root = self.initialize_default_journal()
        self.client.read_payload = "private-looking text\nTOKEN-RAW"
        result = qualification_token_probe(
            self.client,
            lease_payload=lease,
            lease_path=self.lease_path,
            nonce="TOKEN-RAW",
            allow_live=True,
            run_root=run_root,
            lines=20,
        )
        self.assertTrue(result["matched"])
        self.assertNotIn("private-looking", json.dumps(result))
        self.assertNotIn("TOKEN-RAW", json.dumps(result))

    def test_token_probe_rejects_unbounded_window(self) -> None:
        lease = self.create_lease()
        run_root = self.initialize_default_journal()
        with self.assertRaisesRegex(HerdrPuppetError, "between 1 and 80"):
            qualification_token_probe(
                self.client,
                lease_payload=lease,
                lease_path=self.lease_path,
                nonce="TOKEN",
                allow_live=True,
                run_root=run_root,
                lines=81,
            )

    def test_journal_summary_and_state_are_transcript_blind(self) -> None:
        lease = self.create_lease()
        lease = self.mark_harness_ready(lease)
        run_root = self.root / "run"
        initialize_journal(run_root, self.plan)
        initial_text, manifest = self.wrapped_initial(
            lease,
            "private prompt body",
        )
        qualification_send(
            self.client,
            lease_payload=lease,
            lease_path=self.lease_path,
            seq=lease["next_seq"],
            text=initial_text,
            instruction_manifest=manifest,
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

    def test_agy_binding_freezes_exact_gemini_37_launch_vector(self) -> None:
        binding = validate_harness_binding(sample_binding())
        self.assertEqual(
            binding["model_observation"],
            {
                "selection": "explicit",
                "model": "gemini-3.7-flash-high",
                "effort": "high",
            },
        )
        self.assertEqual(
            binding["regular_launch"]["argv"],
            [
                "/usr/local/bin/agy",
                "--model",
                "gemini-3.7-flash-high",
                "--dangerously-skip-permissions",
                "--sandbox=false",
                "--new-project",
                "--log-file",
                "/dev/null",
            ],
        )
        self.assertTrue(
            binding["regular_launch"]["explicit_model_selector"]
        )
        self.assertEqual(
            binding["instructions"]["layers"][2],
            "model/agy-gemini-3.7-flash-high",
        )
        for mutation in ("model", "selector", "order"):
            drifted = copy.deepcopy(binding)
            if mutation == "model":
                drifted["model_observation"]["model"] = "default"
            elif mutation == "selector":
                drifted["regular_launch"]["explicit_model_selector"] = False
            else:
                argv = drifted["regular_launch"]["argv"]
                argv[1:3] = argv[2:0:-1]
                drifted["regular_launch"]["vector_sha256"] = _digest(
                    {
                        "argv": argv,
                        "environment": drifted["regular_launch"][
                            "environment"
                        ],
                        "inherit_environment": False,
                    }
                )
            drifted["fingerprint"] = binding_fingerprint(drifted)
            with self.subTest(mutation=mutation):
                with self.assertRaises(HerdrPuppetError):
                    validate_harness_binding(drifted)

    def test_cursor_binding_profiles_allow_interactive_pending(self) -> None:
        binding = sample_binding(harness="cursor")
        binding["profile"]["enrollment_state"] = "interactive_pending"
        binding["profile"]["status_exit"] = None
        binding["fingerprint"] = binding_fingerprint(binding)
        checked = validate_harness_binding(binding)
        self.assertEqual(
            checked["profile"]["enrollment_state"],
            "interactive_pending",
        )
        self.assertIsNone(checked["profile"]["status_exit"])

    def test_frozen_historical_binding_validator_covers_all_harnesses(
        self,
    ) -> None:
        for schema in (
            "herdr-puppet.harness-binding.v1",
            "herdr-puppet.harness-binding.v2",
        ):
            for harness in ("agy", "codex", "claude", "cursor", "grok"):
                binding = sample_binding(harness=harness)
                binding["schema"] = schema
                if schema.endswith(".v1"):
                    binding.pop("lifecycle_observation")
                if harness == "agy":
                    binding["regular_launch"]["argv"] = [
                        binding["remote"]["executable"]["path"],
                        "--dangerously-skip-permissions",
                        "--sandbox=false",
                        "--new-project",
                        "--log-file",
                        "/dev/null",
                    ]
                    binding["regular_launch"][
                        "explicit_model_selector"
                    ] = False
                    binding["model_observation"] = {
                        "selection": "current_default",
                        "model": "unavailable",
                        "effort": "unavailable",
                    }
                    binding["instructions"]["layers"][2] = (
                        "model/default-unresolved"
                    )
                if harness == "claude" and schema.endswith(".v1"):
                    binding["regular_launch"]["argv"] = [
                        binding["remote"]["executable"]["path"],
                        "--dangerously-skip-permissions",
                    ]
                if harness in {"agy", "claude"}:
                    vector = {
                        "argv": binding["regular_launch"]["argv"],
                        "environment": binding["regular_launch"]["environment"],
                        "inherit_environment": False,
                    }
                    binding["regular_launch"]["vector_sha256"] = _digest(vector)
                binding["fingerprint"] = binding_fingerprint(binding)
                with self.subTest(schema=schema, harness=harness):
                    checked = validate_harness_binding(
                        binding,
                        allow_historical=True,
                        verify_current_adapters=False,
                    )
                    self.assertEqual(checked["schema"], schema)

    def test_non_cursor_binding_profiles_reject_interactive_pending(self) -> None:
        for harness in ("agy", "codex", "claude", "grok"):
            binding = sample_binding(harness=harness)
            binding["profile"]["enrollment_state"] = "interactive_pending"
            binding["profile"]["status_exit"] = None
            binding["fingerprint"] = binding_fingerprint(binding)
            with self.subTest(harness=harness):
                with self.assertRaises(HerdrPuppetError) as caught:
                    validate_harness_binding(binding)
                self.assertEqual(caught.exception.code, "invalid_harness_binding")

    def test_in_row_recensus_must_match_bound_remote_facts(self) -> None:
        binding = sample_binding(harness="claude")
        census = {
            "schema": "herdr-puppet.remote-harness-census.v3",
            "harness": binding["harness"],
            "host": binding["remote"]["host"],
            "recorded_at": binding["attestation"]["census_recorded_at"],
            "executable": binding["remote"]["executable"],
            "profile": binding["profile"],
            "regular_launch": binding["regular_launch"],
            "lifecycle_observation": binding["lifecycle_observation"],
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
        drifted_census = copy.deepcopy(census)
        lifecycle = binding["lifecycle_observation"]
        drifted_lifecycle = build_claude_lifecycle_observation(
            run_id=lifecycle["run_id"],
            marker_root=lifecycle["marker_root"] + "-drifted",
            helper_path=lifecycle["helper"]["path"],
            helper_sha256=lifecycle["helper"]["sha256"],
            implementation_path=lifecycle["implementation"]["path"],
            implementation_sha256=lifecycle["implementation"]["sha256"],
            interpreter_path=lifecycle["interpreter"]["path"],
            interpreter_sha256=lifecycle["interpreter"]["sha256"],
        )
        drifted_census["lifecycle_observation"] = drifted_lifecycle
        drifted_census["regular_launch"] = copy.deepcopy(
            drifted_census["regular_launch"]
        )
        drifted_census["regular_launch"]["argv"] = [
            binding["remote"]["executable"]["path"],
            *claude_launch_flags(drifted_lifecycle),
        ]
        drifted_vector = {
            "argv": drifted_census["regular_launch"]["argv"],
            "environment": drifted_census["regular_launch"]["environment"],
            "inherit_environment": False,
        }
        drifted_census["regular_launch"]["vector_sha256"] = _digest(
            drifted_vector
        )
        with self.assertRaises(HerdrPuppetError) as caught:
            verify_remote_census(
                binding_value=binding,
                census_value=drifted_census,
            )
        self.assertEqual(caught.exception.code, "harness_recensus_mismatch")

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

    def test_cursor_recensus_allows_interactive_pending_profile(self) -> None:
        binding = sample_binding(harness="cursor")
        binding["profile"]["enrollment_state"] = "interactive_pending"
        binding["profile"]["status_exit"] = None
        binding["fingerprint"] = binding_fingerprint(binding)
        census = {
            "schema": "herdr-puppet.remote-harness-census.v3",
            "harness": binding["harness"],
            "host": binding["remote"]["host"],
            "recorded_at": binding["attestation"]["census_recorded_at"],
            "executable": binding["remote"]["executable"],
            "profile": dict(binding["profile"]),
            "regular_launch": binding["regular_launch"],
            "lifecycle_observation": binding["lifecycle_observation"],
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

    def test_cli_claude_lifecycle_dispatches_only_bounded_regular_receipt(
        self,
    ) -> None:
        lease_path = self.root / "claude-cli-lease.json"
        receipt_path = self.root / "claude-cli-receipt.json"
        lease_path.write_text("{}\n", encoding="utf-8")
        receipt_path.write_text(
            '{"schema":"test-receipt"}\n',
            encoding="utf-8",
        )
        args = build_parser().parse_args(
            [
                "qualification-claude-lifecycle-observe",
                "--lease-json",
                str(lease_path),
                "--receipt-json",
                str(receipt_path),
                "--phase",
                "initial",
                "--run-root",
                str(self.root / "run"),
            ]
        )
        with mock.patch.object(
            herdr_cli,
            "qualification_claude_lifecycle_observe",
            return_value={"result": "observed"},
        ) as observe:
            result = herdr_cli.run(args)
        self.assertEqual(result, {"result": "observed"})
        self.assertEqual(
            observe.call_args.kwargs["receipt"],
            {"schema": "test-receipt"},
        )
        self.assertEqual(observe.call_args.kwargs["phase"], "initial")

        oversized = self.root / "oversized-receipt.json"
        oversized.write_bytes(b"{" + b"x" * (64 * 1024) + b"}")
        with self.assertRaises(HerdrPuppetError) as caught:
            herdr_cli._load_bounded_receipt(str(oversized))
        self.assertEqual(
            caught.exception.code,
            "invalid_claude_hook_receipt_file",
        )

        symlink = self.root / "symlink-receipt.json"
        symlink.symlink_to(receipt_path)
        with self.assertRaises(HerdrPuppetError) as caught:
            herdr_cli._load_bounded_receipt(str(symlink))
        self.assertEqual(
            caught.exception.code,
            "invalid_claude_hook_receipt_file",
        )

        fifo = self.root / "fifo-receipt.json"
        os.mkfifo(fifo)
        with self.assertRaises(HerdrPuppetError) as caught:
            herdr_cli._load_bounded_receipt(str(fifo))
        self.assertEqual(
            caught.exception.code,
            "invalid_claude_hook_receipt_file",
        )

        duplicate_field = self.root / "duplicate-field-receipt.json"
        duplicate_field.write_text(
            '{"schema":"one","schema":"two"}\n',
            encoding="utf-8",
        )
        with self.assertRaises(HerdrPuppetError) as caught:
            herdr_cli._load_bounded_receipt(str(duplicate_field))
        self.assertEqual(
            caught.exception.code,
            "invalid_claude_hook_receipt_file",
        )

        non_object = self.root / "non-object-receipt.json"
        non_object.write_text("[]\n", encoding="utf-8")
        with self.assertRaises(HerdrPuppetError) as caught:
            herdr_cli._load_bounded_receipt(str(non_object))
        self.assertEqual(
            caught.exception.code,
            "invalid_claude_hook_receipt_file",
        )

    def test_claude_receipt_command_uses_bound_preexecution_verifier(
        self,
    ) -> None:
        lease, _plan = self._ready_lease_for_harness("claude")
        result = qualification_claude_receipt_command(
            lease_payload=lease,
            lease_path=self.lease_path,
        )
        lifecycle = lease["harness_binding"]["lifecycle_observation"]
        argv = result["argv"]
        self.assertEqual(argv[:3], [lifecycle["interpreter"]["path"], "-I", "-c"])
        self.assertEqual(argv[4], lifecycle["interpreter"]["path"])
        self.assertEqual(argv[5], lifecycle["interpreter"]["sha256"])
        self.assertEqual(argv[6], lifecycle["helper"]["path"])
        self.assertEqual(argv[7], lifecycle["helper"]["sha256"])
        self.assertEqual(argv[8], "observe")
        self.assertIn(lifecycle["implementation"]["sha256"], argv)
        self.assertNotIn("prompt", json.dumps(result).lower())
        parsed = build_parser().parse_args(
            [
                "qualification-claude-receipt-command",
                "--lease-json",
                str(self.lease_path),
            ]
        )
        with mock.patch.object(
            herdr_cli,
            "qualification_claude_receipt_command",
            return_value={"result": "ok"},
        ) as command:
            self.assertEqual(herdr_cli.run(parsed), {"result": "ok"})
        self.assertEqual(
            command.call_args.kwargs["lease_path"],
            self.lease_path,
        )

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
                "--run-root",
                str(self.root / "run"),
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
        self.assertEqual(
            send.call_args.kwargs["run_root"],
            self.root / "run",
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
        lease = self.verify_in_row_census(lease, run_root)

        result = qualification_harness_launch(
            self.client,
            lease_payload=lease,
            lease_path=self.lease_path,
            seq=2,
            allow_live=True,
            run_root=run_root,
        )

        self.assertEqual(result["next_seq"], 3)
        self.assertTrue(result["explicit_model_selector"])
        self.assertEqual(result["remote_harness_pid"], "unavailable")
        self.assertEqual(result["targeted_halt"], "unsupported")
        self.assertEqual(len(self.client.ran), 1)
        command = self.client.ran[0][2]
        self.assertIn("agy", command)
        self.assertIn("--model gemini-3.7-flash-high", command)
        self.assertIn("/usr/bin/env -i", command)
        self.assertNotRegex(command, r"(?:^|&&)\s*exec\s+")
        updated = load_json(self.lease_path)
        self.assertEqual(
            updated["harness_launch"]["launch_vector_sha256"],
            lease["harness_binding"]["regular_launch"]["vector_sha256"],
        )

    def test_harness_launch_ack_then_finalize_failure_blocks_second_launch(
        self,
    ) -> None:
        lease = self.create_lease()
        lease["shell_readiness"] = "status_verified"
        lease["next_seq"] = 2
        self.persist_lease(lease)
        run_root = self.initialize_default_journal()
        lease = self.verify_in_row_census(lease, run_root)

        def fail_launch_completion(
            path: Path,
            payload: dict[str, Any],
        ) -> None:
            if (
                "harness_launch" in payload
                and payload.get("pending_sequence_operation") is None
            ):
                raise RuntimeError("simulated launch finalize failure")
            atomic_json(path, payload)

        with mock.patch(
            "herdr_puppet_lib.core.atomic_json",
            side_effect=fail_launch_completion,
        ):
            with self.assertRaisesRegex(RuntimeError, "finalize failure"):
                qualification_harness_launch(
                    self.client,
                    lease_payload=lease,
                    lease_path=self.lease_path,
                    seq=2,
                    allow_live=True,
                    run_root=run_root,
                )
        reserved = load_json(self.lease_path)
        self.assertEqual(len(self.client.ran), 1)
        self.assertNotIn("harness_launch", reserved)
        self.assertEqual(reserved["next_seq"], 2)
        self.assertEqual(
            reserved["pending_sequence_operation"]["operation"],
            "harness_launch",
        )
        with self.assertRaises(HerdrPuppetError) as replay:
            qualification_harness_launch(
                self.client,
                lease_payload=reserved,
                lease_path=self.lease_path,
                seq=2,
                allow_live=True,
                run_root=run_root,
            )
        self.assertEqual(
            replay.exception.code,
            "qualification_sequence_delivery_unknown",
        )
        self.assertEqual(len(self.client.ran), 1)

    def test_regular_launch_clears_parent_agent_environment(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            worktree = Path(directory).resolve()
            output = worktree / "observed-environment.txt"
            executable = worktree / "fake-harness"
            executable.write_text(
                "#!/bin/sh\n"
                "{\n"
                "  printf 'HOME=%s\\n' \"$HOME\"\n"
                "  printf 'PATH=%s\\n' \"$PATH\"\n"
                "  printf 'LANG=%s\\n' \"$LANG\"\n"
                "  printf 'LC_ALL=%s\\n' \"$LC_ALL\"\n"
                "  printf 'TERM=%s\\n' \"$TERM\"\n"
                "  for name in CODEX_HOME CODEX_THREAD_ID "
                "CLAUDE_CODE_SESSION_ID HERDR_SESSION; do\n"
                "    eval \"value=\\${$name-}\"\n"
                "    if [ -n \"$value\" ]; then\n"
                "      printf '%s=LEAKED\\n' \"$name\"\n"
                "    fi\n"
                "  done\n"
                f"}} > {str(output)!r}\n",
                encoding="utf-8",
            )
            executable.chmod(0o700)
            binding = sample_binding(worktree=str(worktree))
            binding["remote"]["executable"]["path"] = str(executable)
            binding["regular_launch"]["argv"][0] = str(executable)
            vector = {
                "argv": binding["regular_launch"]["argv"],
                "environment": binding["regular_launch"]["environment"],
                "inherit_environment": False,
            }
            binding["regular_launch"]["vector_sha256"] = _digest(vector)
            binding["fingerprint"] = binding_fingerprint(binding)

            parent_environment = dict(os.environ)
            parent_environment.update(
                {
                    "CODEX_HOME": "/must/not/leak",
                    "CODEX_THREAD_ID": "must-not-leak",
                    "CLAUDE_CODE_SESSION_ID": "must-not-leak",
                    "HERDR_SESSION": "must-not-leak",
                }
            )
            subprocess.run(
                ["/bin/sh", "-c", _regular_launch_command(binding)],
                check=True,
                env=parent_environment,
            )

            observed = output.read_text(encoding="utf-8").splitlines()
            self.assertEqual(
                observed,
                [
                    "HOME=/redacted/home",
                    (
                        "PATH=/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:"
                        "/usr/sbin:/sbin"
                    ),
                    "LANG=C",
                    "LC_ALL=C",
                    "TERM=xterm-256color",
                ],
            )

    def test_codex_regular_launch_has_no_resume_selector(self) -> None:
        argv = sample_binding(harness="codex")["regular_launch"]["argv"]
        self.assertEqual(
            argv[1:],
            ["--dangerously-bypass-approvals-and-sandbox"],
        )
        self.assertFalse(
            {"resume", "--last", "fork", "--session-id"}.intersection(argv)
        )

    def test_regular_launch_rejects_forged_extra_environment(self) -> None:
        binding = sample_binding()
        binding["regular_launch"]["environment"]["CODEX_HOME"] = "/forged"
        vector = {
            "argv": binding["regular_launch"]["argv"],
            "environment": binding["regular_launch"]["environment"],
            "inherit_environment": False,
        }
        binding["regular_launch"]["vector_sha256"] = _digest(vector)
        binding["fingerprint"] = binding_fingerprint(binding)
        with self.assertRaises(HerdrPuppetError) as caught:
            _regular_launch_command(binding)
        self.assertEqual(caught.exception.code, "invalid_harness_binding")

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
        qualification_harness_census_verify(
            lease_payload=lease,
            lease_path=lease_path,
            census=sample_census_from_binding(binding),
            run_root=run_root,
        )
        lease = load_json(lease_path)
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

    def test_startup_gate_ack_then_finalize_failure_blocks_replay(self) -> None:
        client = FakeClient()
        binding = sample_binding(harness="cursor")
        run_root = self.root / "cursor-gate-unknown"
        plan_payload = plan(
            client,
            session="operator-session",
            workspace_id="w2",
            workspace_label="worker-02",
            expected_ssh_target="worker@worker-02.example",
            run_id="run-cursor-gate-unknown",
            harness="cursor",
            repo="example/SaariusSkills",
            worktree="/redacted/worktree",
            proof_root=str(run_root.resolve()),
            harness_binding=binding,
            live_mutation_authorized=True,
        )
        initialize_journal(run_root, plan_payload)
        lease_path = self.root / "cursor-gate-unknown-lease.json"
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
        atomic_json(lease_path, lease)
        qualification_harness_census_verify(
            lease_payload=lease,
            lease_path=lease_path,
            census=sample_census_from_binding(binding),
            run_root=run_root,
        )
        qualification_harness_launch(
            client,
            lease_payload=load_json(lease_path),
            lease_path=lease_path,
            seq=2,
            allow_live=True,
            run_root=run_root,
        )
        launched = load_json(lease_path)

        def fail_gate_completion(
            path: Path,
            payload: dict[str, Any],
        ) -> None:
            if (
                payload.get("startup_gate_operations")
                and payload.get("pending_sequence_operation") is None
            ):
                raise RuntimeError("simulated gate finalize failure")
            atomic_json(path, payload)

        with mock.patch(
            "herdr_puppet_lib.core.atomic_json",
            side_effect=fail_gate_completion,
        ):
            with self.assertRaisesRegex(RuntimeError, "finalize failure"):
                qualification_startup_gate(
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
        reserved = load_json(lease_path)
        self.assertEqual(
            reserved["pending_sequence_operation"]["operation"],
            "startup_gate",
        )
        self.assertEqual(client.sent, [("keys", "w2:p1", "a")])
        with self.assertRaises(HerdrPuppetError) as replay:
            qualification_startup_gate(
                client,
                lease_payload=reserved,
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
        self.assertEqual(
            replay.exception.code,
            "qualification_sequence_delivery_unknown",
        )
        self.assertEqual(client.sent, [("keys", "w2:p1", "a")])

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
        run_root = self.initialize_default_journal()
        with self.assertRaises(HerdrPuppetError) as caught:
            qualification_send(
                self.client,
                lease_payload=lease,
                lease_path=self.lease_path,
                seq=lease["next_seq"],
                text=rendered.decode("utf-8"),
                allow_live=True,
                run_root=run_root,
            )
        self.assertEqual(caught.exception.code, "instruction_wrapper_required")
        result = qualification_send(
            self.client,
            lease_payload=lease,
            lease_path=self.lease_path,
            seq=lease["next_seq"],
            text=rendered.decode("utf-8"),
            instruction_manifest=manifest,
            allow_live=True,
            run_root=run_root,
        )
        self.assertEqual(
            result["instruction_wrapper"]["plane"],
            "initial_message_wrapper",
        )
        self.assertEqual(
            result["instruction_wrapper"]["binding_fingerprint"],
            binding["fingerprint"],
        )
        steering_lease = load_json(self.lease_path)
        with self.assertRaises(HerdrPuppetError) as caught:
            qualification_send(
                self.client,
                lease_payload=steering_lease,
                lease_path=self.lease_path,
                seq=steering_lease["next_seq"],
                text="steer separately",
                instruction_manifest=manifest,
                allow_live=True,
                run_root=run_root,
            )
        self.assertEqual(
            caught.exception.code,
            "instruction_wrapper_steering_forbidden",
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
    def test_skill_contract_marks_agy_prompt_file_print_mode_unsupported(self) -> None:
        text = (
            ROOT / "skills" / "herdr-puppet" / "SKILL.md"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "agy --prompt @/exact/task-owned-prompt-file --print-timeout 420s",
            text,
        )
        self.assertIn("no supported noninteractive AGY qualification recipe", text)
        self.assertIn("rejects every harness launcher", text)
        self.assertIn("Do not improvise a `--print` carve-out", text)
        self.assertIn("Use `qualification-send` only for ordinary interactive", text)
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
            "Earlier AGY 1.1.7 diagnostics used a task-owned prompt file",
            text,
        )
        self.assertIn(
            "historical evidence, not a supported controller recipe",
            text,
        )
        self.assertIn(
            "rejects every harness launcher submitted through `qualification-run`",
            text,
        )
        self.assertIn("execution_acceptance: unverified", text)
        self.assertIn(
            "Ordinary interactive harness prompts remain on `qualification-send`",
            text,
        )
        self.assertNotIn("submit the launcher through", text)
        self.assertNotIn("normal 420-second AGY recipe", text)
        self.assertIn("`journal-init` owns creating", text)


if __name__ == "__main__":
    unittest.main()
