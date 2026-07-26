from __future__ import annotations

import hashlib
import json
import shlex
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "puppet" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from puppet_lib.adapter_manifest import (  # noqa: E402
    ADAPTER_MANIFEST_SCHEMA_VERSION,
    AdapterManifest,
    direct_execution_bundle,
)
from puppet_lib.claude_startup_gates import (  # noqa: E402
    GATE_SCHEMA,
    MAX_SCREEN_BYTES,
    navigate_claude_startup_gates,
    reduce_captured_claude_startup_screen,
    revalidate_claude_ready_process,
    validate_claude_gate_manifest,
)
from puppet_lib.errors import IdentityError  # noqa: E402
from puppet_lib.profiles import (  # noqa: E402
    CLAUDE_GATE_POLL_INTERVAL_SECONDS,
    CLAUDE_GATE_TRANSITION_DEADLINE_SECONDS,
    CLAUDE_GATE_TRANSITION_POLL_INTERVAL_SECONDS,
    CLAUDE_STARTUP_GATE_REDUCER,
    SUBMIT_SETTLE_SECONDS,
    claude_gate_timing_policy,
    input_readiness_strategy_for,
    session_profiles_for,
    startup_settle_seconds_for,
)
from puppet_lib.profiles import PROMPT_TRANSPORT  # noqa: E402
from puppet_lib.session import _await_input_ready  # noqa: E402
from puppet_lib.tmux import TmuxController, control_environment  # noqa: E402


WORKTREE = "/tmp/puppet-claude-gate-worktree"
PANE_PID = 4242
FAST_TIMING = {
    "startup_deadline_seconds": 1.0,
    "poll_interval_seconds": 0.0,
    "transition_poll_interval_seconds": 0.0,
    "transition_deadline_seconds": 1.0,
}
ADAPTER_IMPLEMENTATION_SHA256 = "a" * 64
VERSION_OBSERVATION_SHA256 = (
    "3c95eff850dac10d40c5692a73957f526b54a74767163913dc858c4f8d4c8c63"
)


class AdvancingMonotonicClock:
    """Fake monotonic clock that advances on sleep and cannot spin forever."""

    def __init__(self, *, start: float = 0.0, max_calls: int = 10_000) -> None:
        self.now = start
        self.max_calls = max_calls
        self.calls = 0

    def monotonic(self) -> float:
        self.calls += 1
        if self.calls > self.max_calls:
            raise AssertionError("monotonic_fn call bound exceeded in test")
        return self.now

    def sleep(self, interval: float) -> None:
        self.now += interval


class FakeGateTmux:
    """Stable pane captures until a key or startup sleep advances the script."""

    def __init__(
        self,
        screens: list[bytes],
        *,
        startup_sleep_advances: int = 0,
    ) -> None:
        self._screens = list(screens)
        self._index = 0
        self.keys_sent: list[str] = []
        self._startup_sleep_advances = startup_sleep_advances
        self._startup_sleeps_seen = 0
        self.capture_calls = 0

    def _advance(self) -> None:
        if self._index < len(self._screens) - 1:
            self._index += 1

    def notify_startup_sleep(self, interval: float) -> None:
        del interval
        if self._startup_sleeps_seen < self._startup_sleep_advances:
            self._startup_sleeps_seen += 1
            self._advance()

    def pane_runtime_identity(self, **kwargs):
        return {
            "session": kwargs["session"],
            "pane": kwargs["pane"],
            "pane_pid": kwargs["expected_pane_pid"],
            "pane_current_path": kwargs["expected_worktree"],
            "pane_dead": False,
        }

    def capture_pane_bytes(self, **kwargs):
        del kwargs
        if not self._screens:
            raise IdentityError("no scripted pane capture remains")
        self.capture_calls += 1
        if self.capture_calls > 10_000:
            raise AssertionError("capture_pane_bytes call bound exceeded in test")
        return self._screens[min(self._index, len(self._screens) - 1)]

    def send_keys_verified(self, **kwargs):
        self.keys_sent.append(kwargs["keys"])
        self._advance()


def _gate_sleep(tmux: FakeGateTmux, interval: float) -> None:
    tmux.notify_startup_sleep(interval)


def _security_screen() -> str:
    return (
        "Security notes:\n"
        "Claude can make mistakes.\n"
        "Due to prompt injection risks\n"
        "Press Enter to continue\n"
        "https://code.claude.com/docs/en/security\n"
    )


def _trust_screen(*, worktree: str = WORKTREE, selected: str = "yes") -> str:
    yes_prefix = "❯ " if selected == "yes" else "  "
    no_prefix = "❯ " if selected == "no" else "  "
    return (
        "Accessing workspace: %s\n"
        "Quick safety check:\n"
        "%s1. Yes, I trust this folder\n"
        "%s2. No, exit\n"
        "Enter to confirm\n"
    ) % (worktree, yes_prefix, no_prefix)


def _bypass_screen(*, selected: str = "no") -> str:
    no_prefix = "❯ " if selected == "no" else "  "
    yes_prefix = "❯ " if selected == "yes" else "  "
    return (
        "In Bypass Permissions mode\n"
        "you accept all responsibility\n"
        "%s1. No, exit\n"
        "%s2. Yes, I accept\n"
        "Enter to confirm\n"
        "https://code.claude.com/docs/en/security\n"
    ) % (no_prefix, yes_prefix)


def _ready_screen() -> str:
    return (
        "Claude Code v2.1.215\n"
        "? for shortcuts\n"
        "Bypass permissions on\n"
        'Try "fix tests"\n'
    )


def _adapter_manifest(*, argv=None, permission_flags=None) -> AdapterManifest:
    executable = Path(sys.executable).resolve()
    executable_details = executable.stat()
    executable_hash = hashlib.sha256(executable.read_bytes()).hexdigest()
    permission_flags = permission_flags or ["--dangerously-skip-permissions"]
    argv = argv or [str(executable), *permission_flags]
    raw = {
        "schema_version": ADAPTER_MANIFEST_SCHEMA_VERSION,
        "target": "claude",
        "generated_at": "2026-07-22T03:00:00Z",
        "platform": {"system": "Darwin", "release": "test", "machine": "test"},
        "executable": {
            "requested_path": str(executable),
            "resolved_path": str(executable),
            "sha256": executable_hash,
            "version_sha256": VERSION_OBSERVATION_SHA256,
            "help_sha256": "c" * 64,
            "device": executable_details.st_dev,
            "inode": executable_details.st_ino,
            "size": executable_details.st_size,
            "mtime_ns": executable_details.st_mtime_ns,
        },
        "execution": direct_execution_bundle(
            {
                "requested_path": str(executable),
                "resolved_path": str(executable),
                "sha256": executable_hash,
                "version_sha256": VERSION_OBSERVATION_SHA256,
                "help_sha256": "c" * 64,
                "device": executable_details.st_dev,
                "inode": executable_details.st_ino,
                "size": executable_details.st_size,
                "mtime_ns": executable_details.st_mtime_ns,
            }
        ),
        "adapter_fingerprint": ADAPTER_IMPLEMENTATION_SHA256,
        "protocol_fingerprint": "d" * 64,
        "yolo_mapping": {
            "complete": False,
            "launch_argv": argv,
            "permission_declared": True,
            "permission_flags": permission_flags,
            "prompt_transport": PROMPT_TRANSPORT,
            "prompt_transport_declared": True,
            "sandbox_disable_declared": True,
            "sandbox_flags": [],
            "project_isolation_declared": False,
            "project_isolation_flags": [],
            "session_profiles": session_profiles_for("claude"),
            "session_profiles_declared": True,
            "startup_settle_seconds": startup_settle_seconds_for("claude"),
            "submit_settle_seconds": SUBMIT_SETTLE_SECONDS,
            "model_flag": "--model",
            "effort_flag": "--effort",
        },
        "capabilities": {
            name: "declared"
            for name in (
                "launch",
                "send",
                "status",
                "wait",
                "checkpoint",
                "resume",
                "halt",
            )
        },
        "doctor_only": True,
        "qualification": None,
    }
    return AdapterManifest.from_dict(raw)


class ClaudeStartupGateReducerTests(unittest.TestCase):
    def test_each_gate_classifies_exactly_once(self):
        cases = (
            ("security_notice", _security_screen(), None),
            ("workspace_trust", _trust_screen(), "yes"),
            ("bypass_warning", _bypass_screen(), "no"),
            ("ready", _ready_screen(), None),
        )
        for gate, screen, selected in cases:
            with self.subTest(gate=gate):
                captured = screen.encode("utf-8")
                result = reduce_captured_claude_startup_screen(
                    captured,
                    expected_worktree=WORKTREE,
                    pane_pid=PANE_PID,
                )
                self.assertTrue(result["ok"])
                self.assertEqual(result["schema"], GATE_SCHEMA)
                self.assertEqual(result["gate"], gate)
                self.assertEqual(result["selected"], selected)
                self.assertFalse(result["raw_retained"])
                encoded = json.dumps(result, sort_keys=True)
                self.assertNotIn(screen.strip().splitlines()[0], encoded)

    def test_ready_with_persisted_profile_classifies_directly(self):
        result = reduce_captured_claude_startup_screen(
            _ready_screen().encode("utf-8"),
            expected_worktree=WORKTREE,
            pane_pid=PANE_PID,
        )
        self.assertEqual(result["gate"], "ready")
        self.assertTrue(result["ok"])

    def test_wrong_worktree_fails_closed(self):
        result = reduce_captured_claude_startup_screen(
            _trust_screen(worktree="/tmp/other-worktree").encode("utf-8"),
            expected_worktree=WORKTREE,
            pane_pid=PANE_PID,
        )
        self.assertFalse(result["ok"])
        self.assertIn("displayed workspace path", result["error"])

    def test_substring_worktree_elsewhere_does_not_match(self):
        decoy = (
            "note about %s during boot\n" % WORKTREE
        ) + _trust_screen(worktree="/tmp/decoy-worktree")
        result = reduce_captured_claude_startup_screen(
            decoy.encode("utf-8"),
            expected_worktree=WORKTREE,
            pane_pid=PANE_PID,
        )
        self.assertFalse(result["ok"])
        self.assertIn("displayed workspace path", result["error"])

    def test_ambiguous_screen_fails_closed(self):
        combined = _security_screen() + _trust_screen()
        result = reduce_captured_claude_startup_screen(
            combined.encode("utf-8"),
            expected_worktree=WORKTREE,
            pane_pid=PANE_PID,
        )
        self.assertFalse(result["ok"])
        self.assertIn("multiple allowlisted", result["error"])

    def test_transient_empty_then_gate(self):
        tmux = FakeGateTmux(
            [
                b"",
                _security_screen().encode("utf-8"),
                _trust_screen(selected="yes").encode("utf-8"),
                _bypass_screen(selected="yes").encode("utf-8"),
                _ready_screen().encode("utf-8"),
            ],
            startup_sleep_advances=1,
        )
        manifest = _adapter_manifest()
        result = navigate_claude_startup_gates(
            tmux,
            manifest=manifest,
            socket=Path("/tmp/fake.sock"),
            session="probe-claude",
            pane="%0",
            expected_worktree=WORKTREE,
            expected_pane_pid=PANE_PID,
            launch_argv=manifest.raw["yolo_mapping"]["launch_argv"],
            process_alive_fn=lambda: True,
            sleep_fn=lambda interval: _gate_sleep(tmux, interval),
            timing=FAST_TIMING,
        )
        self.assertEqual(result["final_gate"], "ready")

    def test_startup_deadline_exhaustion_fails_closed(self):
        tmux = FakeGateTmux([b""])
        manifest = _adapter_manifest()
        clock = AdvancingMonotonicClock(max_calls=64)
        timing = {
            "startup_deadline_seconds": 1.0,
            "poll_interval_seconds": 0.25,
            "transition_poll_interval_seconds": 0.25,
            "transition_deadline_seconds": 1.0,
        }
        with self.assertRaisesRegex(IdentityError, "startup deadline exceeded"):
            navigate_claude_startup_gates(
                tmux,
                manifest=manifest,
                socket=Path("/tmp/fake.sock"),
                session="probe-claude",
                pane="%0",
                expected_worktree=WORKTREE,
                expected_pane_pid=PANE_PID,
                launch_argv=manifest.raw["yolo_mapping"]["launch_argv"],
                process_alive_fn=lambda: True,
                sleep_fn=clock.sleep,
                monotonic_fn=clock.monotonic,
                timing=timing,
            )

    def test_forbidden_screen_fails_immediately_without_retry(self):
        tmux = FakeGateTmux([b"Claude Code\nLog in to continue\n"])
        manifest = _adapter_manifest()
        with self.assertRaisesRegex(IdentityError, "forbidden"):
            navigate_claude_startup_gates(
                tmux,
                manifest=manifest,
                socket=Path("/tmp/fake.sock"),
                session="probe-claude",
                pane="%0",
                expected_worktree=WORKTREE,
                expected_pane_pid=PANE_PID,
                launch_argv=manifest.raw["yolo_mapping"]["launch_argv"],
                process_alive_fn=lambda: True,
                sleep_fn=lambda _interval: None,
                timing=FAST_TIMING,
            )

    def test_oversize_and_non_utf8_fail_closed(self):
        oversized = b"x" * (MAX_SCREEN_BYTES + 1)
        over = reduce_captured_claude_startup_screen(
            oversized,
            expected_worktree=WORKTREE,
            pane_pid=PANE_PID,
        )
        self.assertFalse(over["ok"])
        self.assertIn("cap", over["error"])

        invalid = b"\xff\xfe"
        bad = reduce_captured_claude_startup_screen(
            invalid,
            expected_worktree=WORKTREE,
            pane_pid=PANE_PID,
        )
        self.assertFalse(bad["ok"])
        self.assertIn("UTF-8", bad["error"])

    def test_login_and_unknown_screens_fail_closed(self):
        for screen in (
            "Claude Code\nLog in to continue\n",
            "Claude Code\npermission request pending\n",
            "Claude Code\nTerms of Service\nAccept and continue\n",
        ):
            with self.subTest(screen=screen.splitlines()[1]):
                result = reduce_captured_claude_startup_screen(
                    screen.encode("utf-8"),
                    expected_worktree=WORKTREE,
                    pane_pid=PANE_PID,
                )
                self.assertFalse(result["ok"])
                self.assertEqual(result["gate"], "unknown")

    def test_raw_body_is_never_retained_in_reduction_or_exceptions(self):
        body = _ready_screen()
        result = reduce_captured_claude_startup_screen(
            body.encode("utf-8"),
            expected_worktree=WORKTREE,
            pane_pid=PANE_PID,
        )
        encoded = json.dumps(result)
        for marker in ("Try ", "shortcuts", "Bypass permissions"):
            self.assertNotIn(marker, encoded)
        self.assertFalse(result["raw_retained"])

    def test_manifest_policy_requires_exact_bypass_argv(self):
        manifest = _adapter_manifest()
        validate_claude_gate_manifest(manifest)
        executable = str(Path(sys.executable).resolve())
        bad = _adapter_manifest(
            argv=[executable, "--safe-only"],
            permission_flags=["--dangerously-skip-permissions"],
        )
        with self.assertRaisesRegex(IdentityError, "does not authorize"):
            validate_claude_gate_manifest(bad)

    def test_navigation_confirms_selected_choice_for_each_gate(self):
        tmux = FakeGateTmux(
            [
                _security_screen().encode("utf-8"),
                _trust_screen(selected="no").encode("utf-8"),
                _trust_screen(selected="yes").encode("utf-8"),
                _bypass_screen(selected="no").encode("utf-8"),
                _bypass_screen(selected="yes").encode("utf-8"),
                _ready_screen().encode("utf-8"),
            ]
        )
        manifest = _adapter_manifest()
        result = navigate_claude_startup_gates(
            tmux,
            manifest=manifest,
            socket=Path("/tmp/fake.sock"),
            session="probe-claude",
            pane="%0",
            expected_worktree=WORKTREE,
            expected_pane_pid=PANE_PID,
            launch_argv=manifest.raw["yolo_mapping"]["launch_argv"],
            process_alive_fn=lambda: True,
            sleep_fn=lambda _interval: None,
            timing=FAST_TIMING,
        )
        self.assertEqual(result["final_gate"], "ready")
        self.assertEqual(result["strategy"], CLAUDE_STARTUP_GATE_REDUCER)
        self.assertEqual(tmux.keys_sent, ["Enter", "Up", "Enter", "Down", "Enter"])
        for step in result["steps"]:
            self.assertFalse(step["raw_retained"])
            self.assertIn("screen_sha256", step)

    def test_persisted_ready_profile_skips_intermediate_gates(self):
        tmux = FakeGateTmux([_ready_screen().encode("utf-8")])
        manifest = _adapter_manifest()
        result = navigate_claude_startup_gates(
            tmux,
            manifest=manifest,
            socket=Path("/tmp/fake.sock"),
            session="probe-claude",
            pane="%0",
            expected_worktree=WORKTREE,
            expected_pane_pid=PANE_PID,
            launch_argv=manifest.raw["yolo_mapping"]["launch_argv"],
            process_alive_fn=lambda: True,
            sleep_fn=lambda _interval: None,
            timing=FAST_TIMING,
        )
        self.assertEqual(result["final_gate"], "ready")
        self.assertEqual(tmux.keys_sent, [])

    def test_process_death_during_navigation_fails_closed(self):
        tmux = FakeGateTmux([_security_screen().encode("utf-8")])
        manifest = _adapter_manifest()
        with self.assertRaisesRegex(IdentityError, "unavailable"):
            navigate_claude_startup_gates(
                tmux,
                manifest=manifest,
                socket=Path("/tmp/fake.sock"),
                session="probe-claude",
                pane="%0",
                expected_worktree=WORKTREE,
                expected_pane_pid=PANE_PID,
                launch_argv=manifest.raw["yolo_mapping"]["launch_argv"],
                process_alive_fn=lambda: False,
                sleep_fn=lambda _interval: None,
            )

    def test_unauthorized_bypass_launch_argv_fails_closed(self):
        tmux = FakeGateTmux([_bypass_screen().encode("utf-8")])
        manifest = _adapter_manifest()
        with self.assertRaisesRegex(IdentityError, "does not authorize"):
            navigate_claude_startup_gates(
                tmux,
                manifest=manifest,
                socket=Path("/tmp/fake.sock"),
                session="probe-claude",
                pane="%0",
                expected_worktree=WORKTREE,
                expected_pane_pid=PANE_PID,
                launch_argv=[str(Path(sys.executable))],
                process_alive_fn=lambda: True,
                sleep_fn=lambda _interval: None,
            )

    def test_claude_strategy_is_distinct_from_structural_settle(self):
        self.assertEqual(
            input_readiness_strategy_for("claude"),
            CLAUDE_STARTUP_GATE_REDUCER,
        )
        self.assertEqual(
            input_readiness_strategy_for("codex"),
            "bounded_structural_settle",
        )

    def test_timing_policy_is_public_and_bound(self):
        policy = claude_gate_timing_policy()
        self.assertEqual(
            policy["startup_deadline_seconds"],
            startup_settle_seconds_for("claude"),
        )
        self.assertEqual(
            policy["poll_interval_seconds"], CLAUDE_GATE_POLL_INTERVAL_SECONDS
        )
        self.assertEqual(
            policy["transition_poll_interval_seconds"],
            CLAUDE_GATE_TRANSITION_POLL_INTERVAL_SECONDS,
        )
        self.assertEqual(
            policy["transition_deadline_seconds"],
            CLAUDE_GATE_TRANSITION_DEADLINE_SECONDS,
        )

    def test_transition_deadline_exhaustion_fails_closed(self):
        tmux = FakeGateTmux([_security_screen().encode("utf-8")])
        manifest = _adapter_manifest()
        clock = AdvancingMonotonicClock(max_calls=64)
        timing = {
            **FAST_TIMING,
            "transition_poll_interval_seconds": 0.25,
        }
        with self.assertRaisesRegex(IdentityError, "transition deadline exceeded"):
            navigate_claude_startup_gates(
                tmux,
                manifest=manifest,
                socket=Path("/tmp/fake.sock"),
                session="probe-claude",
                pane="%0",
                expected_worktree=WORKTREE,
                expected_pane_pid=PANE_PID,
                launch_argv=manifest.raw["yolo_mapping"]["launch_argv"],
                process_alive_fn=lambda: True,
                sleep_fn=clock.sleep,
                monotonic_fn=clock.monotonic,
                timing=timing,
            )

    def test_post_ready_revalidation_requires_ready_screen(self):
        tmux = FakeGateTmux([_ready_screen().encode("utf-8")])
        manifest = _adapter_manifest()
        with mock.patch.object(AdapterManifest, "verify_process_executable", autospec=True):
            revalidate_claude_ready_process(
                manifest=manifest,
                tmux=tmux,
                socket=Path("/tmp/fake.sock"),
                session="probe-claude",
                pane="%0",
                expected_pane_pid=PANE_PID,
                expected_worktree=WORKTREE,
                process={"pid": PANE_PID, "identity_version": 1},
                server_identity={},
                process_alive_fn=lambda: True,
            )

    def test_post_ready_revalidation_fails_when_screen_is_not_ready(self):
        tmux = FakeGateTmux([_security_screen().encode("utf-8")])
        manifest = _adapter_manifest()
        with mock.patch.object(AdapterManifest, "verify_process_executable", autospec=True):
            with self.assertRaisesRegex(IdentityError, "not ready before prompt delivery"):
                revalidate_claude_ready_process(
                    manifest=manifest,
                    tmux=tmux,
                    socket=Path("/tmp/fake.sock"),
                    session="probe-claude",
                    pane="%0",
                    expected_pane_pid=PANE_PID,
                    expected_worktree=WORKTREE,
                    process={"pid": PANE_PID, "identity_version": 1},
                    server_identity={},
                    process_alive_fn=lambda: True,
                )


class ClaudeTmuxIntegrationTests(unittest.TestCase):
    @staticmethod
    def _tmux_run(socket: Path, arguments: list[str]) -> subprocess.CompletedProcess:
        import os
        import subprocess

        return subprocess.run(
            ["tmux", "-f", os.devnull, "-S", str(socket)] + arguments,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def test_run_raw_bytes_and_capture_pane_use_bytes_on_real_tmux(self):
        import os
        import subprocess

        if not TmuxController.available():
            self.skipTest("tmux is unavailable")
        marker = "PUPPET_GATE_FIXTURE_MARKER_7c2a"
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root / "repo"
            repo.mkdir()
            registry = root / "registry"
            registry.mkdir()
            controller = TmuxController(registry)
            socket = root / "sock"
            session = "gate-fixture"
            launch_command = (
                "printf '%%s\\n' %s; exec sleep 999" % shlex.quote(marker)
            )
            try:
                created = self._tmux_run(
                    socket,
                    [
                        "new-session",
                        "-d",
                        "-s",
                        session,
                        "-c",
                        str(repo),
                        "sh",
                        "-c",
                        launch_command,
                    ],
                )
                self.assertEqual(created.returncode, 0, created.stderr)
                listed = self._tmux_run(
                    socket,
                    ["list-panes", "-t", session, "-F", "#{pane_id},#{pane_pid}"],
                )
                self.assertEqual(listed.returncode, 0, listed.stderr)
                pane, pid_text = listed.stdout.decode("utf-8").strip().split(",")
                pane_pid = int(pid_text)
                expected_worktree = str(repo.resolve())
                capture_command = controller._tmux_command(
                    socket,
                    [
                        "capture-pane",
                        "-p",
                        "-t",
                        "%s:%s" % (session, pane),
                        "-S",
                        "-256",
                    ],
                )
                raw_capture = controller._run_raw_bytes(
                    capture_command,
                    check=False,
                    env=control_environment(),
                )
                self.assertIsInstance(raw_capture.stdout, bytes)
                runtime = controller.pane_runtime_identity(
                    socket=socket,
                    session=session,
                    pane=pane,
                    expected_pane_pid=pane_pid,
                    expected_worktree=expected_worktree,
                )
                self.assertEqual(runtime["pane_current_path"], expected_worktree)
                captured = controller.capture_pane_bytes(
                    socket=socket,
                    session=session,
                    pane=pane,
                    expected_pane_pid=pane_pid,
                )
                self.assertIsInstance(captured, bytes)
                digest = hashlib.sha256(captured).hexdigest()
                self.assertIn(marker.encode("utf-8"), captured)
                self.assertNotIn(marker, json.dumps({"screen_sha256": digest}))
            finally:
                self._tmux_run(socket, ["kill-server"])


class ClaudeLaunchOrderingTests(unittest.TestCase):
    def test_gate_ready_precedes_paste_settle_and_submit(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        registry_root = root / "registry"
        registry_root.mkdir()
        controller = TmuxController(registry_root, _sleep_fn=lambda _interval: None)
        socket = root / "socket"
        session = "claude-order"
        pane = "%0"
        order: list[str] = []
        calls: list[list[str]] = []

        def fake_await_claude_input_ready(*args, **kwargs):
            del args, kwargs
            order.append("gates_ready")
            return {
                "strategy": CLAUDE_STARTUP_GATE_REDUCER,
                "final_gate": "ready",
                "steps": [{"gate": "ready", "raw_retained": False}],
                "raw_retained": False,
            }

        def fake_run(command, **kwargs):
            calls.append(list(command))
            if "paste-buffer" in command:
                order.append("paste")
            if "send-keys" in command and command[-1] == "Enter":
                order.append("submit")
            return SimpleNamespace(
                args=command, returncode=0, stdout=b"", stderr=b""
            )

        manifest = _adapter_manifest()
        process = {"pid": PANE_PID, "executable_path": str(Path(sys.executable))}
        with (
            mock.patch(
                "puppet_lib.claude_startup_gates.await_claude_input_ready",
                side_effect=fake_await_claude_input_ready,
            ),
            mock.patch(
                "puppet_lib.claude_startup_gates.revalidate_claude_ready_process",
                autospec=True,
            ),
            mock.patch.object(controller, "metadata", return_value={
                "pane": pane,
                "pane_pid": PANE_PID,
                "pane_dead": False,
            }),
            mock.patch("puppet_lib.tmux.subprocess.run", side_effect=fake_run),
            mock.patch.object(controller, "assert_tmux_binary_identity"),
        ):
            result = _await_input_ready(
                target="claude",
                tmux=controller,
                manifest=manifest,
                socket=socket,
                session=session,
                pane=pane,
                pane_pid=PANE_PID,
                repo=Path(WORKTREE),
                argv=manifest.raw["yolo_mapping"]["launch_argv"],
                process=process,
                server_identity={},
                sleep_fn=lambda _interval: None,
                process_alive_fn=lambda: True,
            )
            self.assertTrue(result["process_revalidated"])
            controller.paste_bytes(
                socket=socket,
                session=session,
                pane=pane,
                buffer_name="initial",
                payload=b"task body",
            )
        self.assertEqual(order, ["gates_ready", "paste", "submit"])
        paste_index = next(
            index for index, call in enumerate(calls) if "paste-buffer" in call
        )
        submit_index = next(
            index
            for index, call in enumerate(calls)
            if "send-keys" in call and call[-1] == "Enter"
        )
        self.assertLess(paste_index, submit_index)


if __name__ == "__main__":
    unittest.main()
