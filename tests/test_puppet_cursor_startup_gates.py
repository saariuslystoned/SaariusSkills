from __future__ import annotations

import hashlib
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "puppet" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from puppet_lib.adapter_manifest import (  # noqa: E402
    ADAPTER_MANIFEST_SCHEMA_VERSION,
    AdapterManifest,
    direct_execution_bundle,
)
from puppet_lib.cursor_qualification import cursor_qualified_mapping  # noqa: E402
from puppet_lib.cursor_startup_gates import (  # noqa: E402
    GATE_SCHEMA,
    MAX_SCREEN_BYTES,
    navigate_cursor_startup_gates,
    reduce_captured_cursor_startup_screen,
    validate_cursor_gate_manifest,
)
from puppet_lib.errors import IdentityError  # noqa: E402
from puppet_lib.profiles import (  # noqa: E402
    CURSOR_STARTUP_GATE_REDUCER,
    PROMPT_TRANSPORT,
    SUBMIT_SETTLE_SECONDS,
    cursor_gate_timing_policy,
    input_readiness_strategy_for,
    session_profiles_for,
    startup_settle_seconds_for,
)
from puppet_lib.session import _await_input_ready  # noqa: E402


WORKTREE = "/tmp/puppet-cursor-gate-worktree"
WORKTREE_WITH_SPACES = "/tmp/puppet cursor gate worktree"
LONG_WORKTREE = (
    "/Users/bobbybones/Developer/_machine-runs/"
    "puppet-five-harness-dogfood-20260725/"
    "cursor-gate-diagnostic/proof/probes/"
    "cursor-gate-diagnostic-20260726/fixture"
)
PANE_PID = 4242
FAST_TIMING = {
    "startup_deadline_seconds": 1.0,
    "poll_interval_seconds": 0.0,
    "transition_poll_interval_seconds": 0.0,
    "transition_deadline_seconds": 1.0,
}


def _boxed(line: str = "") -> str:
    return "│  %-72s  │" % line


def _trust_screen(
    *,
    worktree: str = WORKTREE,
    path_parts: list[str] | None = None,
    extra_options: list[str] | None = None,
) -> str:
    parts = path_parts or [worktree]
    lines = [
        "╭──────────────────────────────────────────────────────────────────────────╮",
        _boxed(),
        _boxed("⚠ Workspace Trust Required"),
        _boxed(),
        _boxed("Cursor Agent can execute code and access files in this directory."),
        _boxed(),
        _boxed("Do you trust the contents of this directory?"),
        _boxed(),
        *[_boxed(part) for part in parts],
        _boxed(),
        _boxed("▶ [a] Trust this workspace"),
        *[_boxed(item) for item in (extra_options or [])],
        _boxed("  [q] Quit"),
        _boxed(),
        _boxed(
            "Use arrow keys to navigate, Enter to select, or press the key shown"
        ),
        "╰──────────────────────────────────────────────────────────────────────────╯",
    ]
    return "\n".join(lines) + "\n"


def _ready_screen(worktree: str = WORKTREE, *, path_parts=None) -> str:
    parts = path_parts or [worktree]
    return (
        "Synthetic task status\n"
        "⠰ Running\n"
        "→ Add a follow-up                              ctrl+c to stop\n"
        "Auto · 8.7%                                      Run Everything\n"
        + "\n".join(parts)
        + "\n"
    )


def _manifest() -> AdapterManifest:
    executable = Path(sys.executable).resolve()
    details = executable.stat()
    executable_hash = hashlib.sha256(executable.read_bytes()).hexdigest()
    executable_record = {
        "requested_path": str(executable),
        "resolved_path": str(executable),
        "sha256": executable_hash,
        "version_sha256": "b" * 64,
        "help_sha256": "c" * 64,
        "device": details.st_dev,
        "inode": details.st_ino,
        "size": details.st_size,
        "mtime_ns": details.st_mtime_ns,
    }
    mapping = {
        "complete": False,
        "launch_argv": [str(executable), "--yolo", "--sandbox", "disabled"],
        "permission_declared": True,
        "permission_flags": ["--yolo"],
        "prompt_transport": PROMPT_TRANSPORT,
        "prompt_transport_declared": True,
        "sandbox_disable_declared": True,
        "sandbox_flags": ["--sandbox", "disabled"],
        "project_isolation_declared": False,
        "project_isolation_flags": [],
        "session_profiles": session_profiles_for("cursor"),
        "session_profiles_declared": True,
        "startup_settle_seconds": startup_settle_seconds_for("cursor"),
        "submit_settle_seconds": SUBMIT_SETTLE_SECONDS,
        "model_flag": "--model",
    }
    raw = {
        "schema_version": ADAPTER_MANIFEST_SCHEMA_VERSION,
        "target": "cursor",
        "generated_at": "2026-07-26T12:00:00Z",
        "platform": {"system": "Darwin", "release": "test", "machine": "test"},
        "executable": executable_record,
        "execution": direct_execution_bundle(executable_record),
        "adapter_fingerprint": "a" * 64,
        "protocol_fingerprint": "d" * 64,
        "yolo_mapping": mapping,
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


class FakeTmux:
    def __init__(self, screens: list[bytes]) -> None:
        self.screens = screens
        self.index = 0
        self.keys_sent: list[str] = []
        self.alive = True
        self.stale = False

    def pane_runtime_identity(self, **kwargs):
        if self.stale:
            raise IdentityError("tmux pane process identity changed")
        return {
            "session": kwargs["session"],
            "pane": kwargs["pane"],
            "pane_pid": kwargs["expected_pane_pid"],
            "pane_current_path": str(kwargs["expected_worktree"]),
            "pane_dead": False,
        }

    def capture_pane_bytes(self, **kwargs):
        del kwargs
        return self.screens[min(self.index, len(self.screens) - 1)]

    def send_keys_verified(self, **kwargs):
        if self.stale:
            raise IdentityError("tmux pane process identity changed")
        self.keys_sent.append(kwargs["keys"])
        self.index = min(self.index + 1, len(self.screens) - 1)


class CursorStartupScreenTests(unittest.TestCase):
    def test_exact_boxed_trust_gate_classifies_body_free(self):
        screen = _trust_screen()
        result = reduce_captured_cursor_startup_screen(
            screen.encode(), expected_worktree=WORKTREE, pane_pid=PANE_PID
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["schema"], GATE_SCHEMA)
        self.assertEqual(result["gate"], "workspace_trust")
        self.assertEqual(result["selected"], "yes")
        self.assertTrue(result["worktree_match"])
        self.assertFalse(result["raw_retained"])
        self.assertNotIn("Trust this workspace", json.dumps(result))

    def test_observed_hard_wrapped_path_matches_exactly(self):
        split = [
            LONG_WORKTREE[:72],
            LONG_WORKTREE[72:144],
            LONG_WORKTREE[144:],
        ]
        result = reduce_captured_cursor_startup_screen(
            _trust_screen(worktree=LONG_WORKTREE, path_parts=split).encode(),
            expected_worktree=LONG_WORKTREE,
            pane_pid=PANE_PID,
        )
        self.assertTrue(result["ok"])
        self.assertTrue(result["worktree_match"])

    def test_workspace_with_spaces_matches(self):
        result = reduce_captured_cursor_startup_screen(
            _trust_screen(worktree=WORKTREE_WITH_SPACES).encode(),
            expected_worktree=WORKTREE_WITH_SPACES,
            pane_pid=PANE_PID,
        )
        self.assertTrue(result["ok"])

    def test_wrong_path_and_decoy_fail_closed(self):
        for screen in (
            _trust_screen(worktree="/tmp/other-worktree"),
            "note %s\n" % WORKTREE
            + _trust_screen(worktree="/tmp/other-worktree"),
        ):
            with self.subTest(screen=screen[:12]):
                result = reduce_captured_cursor_startup_screen(
                    screen.encode(),
                    expected_worktree=WORKTREE,
                    pane_pid=PANE_PID,
                )
                self.assertFalse(result["ok"])
                self.assertEqual(
                    result["error"],
                    "displayed workspace path does not match contract",
                )

    def test_duplicate_and_malformed_markers_fail_closed(self):
        cases = (
            _trust_screen().replace(
                _boxed("⚠ Workspace Trust Required"),
                _boxed("⚠ Workspace Trust Required")
                + "\n"
                + _boxed("Workspace Trust Required"),
            ),
            _trust_screen().replace("[q] Quit", "[x] Continue"),
        )
        for screen in cases:
            result = reduce_captured_cursor_startup_screen(
                screen.encode(), expected_worktree=WORKTREE, pane_pid=PANE_PID
            )
            self.assertFalse(result["ok"])
            self.assertIn(
                result["error"],
                {
                    "displayed workspace trust markers are duplicated",
                    "screen contains an unresolved confirmation gate",
                },
            )

    def test_mcp_expanded_trust_gate_fails_closed(self):
        result = reduce_captured_cursor_startup_screen(
            _trust_screen(
                extra_options=[
                    "[w] Trust this workspace, but don't enable all MCP servers"
                ]
            ).encode(),
            expected_worktree=WORKTREE,
            pane_pid=PANE_PID,
        )
        self.assertFalse(result["ok"])
        self.assertEqual(
            result["error"],
            "screen contains an MCP-expanded workspace trust gate",
        )

    def test_login_terms_and_permission_screens_fail_closed(self):
        for marker in (
            "Log in to Cursor",
            "Terms of Service",
            "permission request pending",
        ):
            result = reduce_captured_cursor_startup_screen(
                ("Cursor Agent\n" + marker + "\n").encode(),
                expected_worktree=WORKTREE,
                pane_pid=PANE_PID,
            )
            self.assertFalse(result["ok"])
            self.assertEqual(
                result["error"],
                "screen matches a forbidden non-allowlisted gate",
            )

    def test_non_utf8_oversize_and_unknown_screens_fail_closed(self):
        cases = (
            (b"\xff", "pane screen is not strict UTF-8"),
            (
                b"x" * (MAX_SCREEN_BYTES + 1),
                "bounded pane screen exceeds the cap",
            ),
            (
                b"Cursor is warming up\n",
                "startup screen is not yet classifiable",
            ),
        )
        for captured, error in cases:
            result = reduce_captured_cursor_startup_screen(
                captured, expected_worktree=WORKTREE, pane_pid=PANE_PID
            )
            self.assertFalse(result["ok"])
            self.assertEqual(result["error"], error)

    def test_partially_rendered_trust_screen_is_transient_not_authorized(self):
        result = reduce_captured_cursor_startup_screen(
            (
                "⚠ Workspace Trust Required\n"
                "Cursor Agent can execute code and access files in this directory.\n"
            ).encode(),
            expected_worktree=WORKTREE,
            pane_pid=PANE_PID,
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["gate"], "unknown")
        self.assertEqual(result["error"], "startup screen is not yet classifiable")

    def test_ready_or_running_screen_requires_footer_and_exact_workspace(self):
        good = reduce_captured_cursor_startup_screen(
            _ready_screen().encode(),
            expected_worktree=WORKTREE,
            pane_pid=PANE_PID,
        )
        bad = reduce_captured_cursor_startup_screen(
            _ready_screen("/tmp/other").encode(),
            expected_worktree=WORKTREE,
            pane_pid=PANE_PID,
        )
        self.assertTrue(good["ok"])
        self.assertEqual(good["gate"], "ready")
        self.assertTrue(good["worktree_match"])
        self.assertFalse(bad["ok"])


class CursorStartupNavigationTests(unittest.TestCase):
    def _argv(self, manifest: AdapterManifest, *, positional: bool = True):
        argv = [
            *manifest.raw["yolo_mapping"]["launch_argv"],
            "--workspace",
            WORKTREE,
        ]
        if positional:
            argv.append("Proceed using the active Puppet workspace contract.")
        return argv

    def test_trust_gate_sends_literal_a_once_then_reaches_ready(self):
        tmux = FakeTmux([_trust_screen().encode(), _ready_screen().encode()])
        manifest = _manifest()
        result = navigate_cursor_startup_gates(
            tmux,
            manifest=manifest,
            socket=Path("/tmp/fake.sock"),
            session="probe-cursor",
            pane="%0",
            expected_worktree=WORKTREE,
            expected_pane_pid=PANE_PID,
            launch_argv=self._argv(manifest),
            process_alive_fn=lambda: True,
            sleep_fn=lambda _interval: None,
            timing=FAST_TIMING,
        )
        self.assertEqual(tmux.keys_sent, ["a"])
        self.assertEqual(result["final_gate"], "ready")
        self.assertEqual(
            [step["gate"] for step in result["steps"]],
            ["workspace_trust", "ready"],
        )
        self.assertTrue(all(step["raw_retained"] is False for step in result["steps"]))

    def test_persisted_ready_state_sends_no_key(self):
        tmux = FakeTmux([_ready_screen().encode()])
        manifest = _manifest()
        result = navigate_cursor_startup_gates(
            tmux,
            manifest=manifest,
            socket=Path("/tmp/fake.sock"),
            session="probe-cursor",
            pane="%0",
            expected_worktree=WORKTREE,
            expected_pane_pid=PANE_PID,
            launch_argv=self._argv(manifest, positional=False),
            process_alive_fn=lambda: True,
            sleep_fn=lambda _interval: None,
            timing=FAST_TIMING,
        )
        self.assertEqual(tmux.keys_sent, [])
        self.assertEqual(result["final_gate"], "ready")

    def test_dead_and_stale_targets_receive_no_key(self):
        manifest = _manifest()
        dead = FakeTmux([_trust_screen().encode()])
        with self.assertRaisesRegex(IdentityError, "unavailable"):
            navigate_cursor_startup_gates(
                dead,
                manifest=manifest,
                socket=Path("/tmp/fake.sock"),
                session="probe-cursor",
                pane="%0",
                expected_worktree=WORKTREE,
                expected_pane_pid=PANE_PID,
                launch_argv=self._argv(manifest),
                process_alive_fn=lambda: False,
                sleep_fn=lambda _interval: None,
                timing=FAST_TIMING,
            )
        self.assertEqual(dead.keys_sent, [])

        stale = FakeTmux([_trust_screen().encode()])
        stale.stale = True
        with self.assertRaisesRegex(IdentityError, "process identity changed"):
            navigate_cursor_startup_gates(
                stale,
                manifest=manifest,
                socket=Path("/tmp/fake.sock"),
                session="probe-cursor",
                pane="%0",
                expected_worktree=WORKTREE,
                expected_pane_pid=PANE_PID,
                launch_argv=self._argv(manifest),
                process_alive_fn=lambda: True,
                sleep_fn=lambda _interval: None,
                timing=FAST_TIMING,
            )
        self.assertEqual(stale.keys_sent, [])

    def test_unbound_or_model_selected_argv_fails_before_key(self):
        manifest = _manifest()
        for argv in (
            manifest.raw["yolo_mapping"]["launch_argv"],
            [*self._argv(manifest), "--model", "named-model"],
            [
                *manifest.raw["yolo_mapping"]["launch_argv"],
                "--workspace",
                "/tmp/other",
            ],
        ):
            tmux = FakeTmux([_trust_screen().encode()])
            with self.assertRaises(IdentityError):
                navigate_cursor_startup_gates(
                    tmux,
                    manifest=manifest,
                    socket=Path("/tmp/fake.sock"),
                    session="probe-cursor",
                    pane="%0",
                    expected_worktree=WORKTREE,
                    expected_pane_pid=PANE_PID,
                    launch_argv=argv,
                    process_alive_fn=lambda: True,
                    sleep_fn=lambda _interval: None,
                    timing=FAST_TIMING,
                )
            self.assertEqual(tmux.keys_sent, [])

    def test_session_readiness_orders_gate_before_process_revalidation(self):
        tmux = FakeTmux([_trust_screen().encode(), _ready_screen().encode()])
        manifest = _manifest()
        process = {"pid": PANE_PID, "identity_version": 1}
        with mock.patch.object(
            AdapterManifest, "verify_process_executable", autospec=True
        ) as verify:
            result = _await_input_ready(
                target="cursor",
                tmux=tmux,
                manifest=manifest,
                socket=Path("/tmp/fake.sock"),
                session="probe-cursor",
                pane="%0",
                pane_pid=PANE_PID,
                repo=Path(WORKTREE),
                argv=self._argv(manifest),
                process=process,
                server_identity={},
                sleep_fn=lambda _interval: None,
                process_alive_fn=lambda: True,
            )
        self.assertEqual(tmux.keys_sent, ["a"])
        self.assertTrue(result["process_revalidated"])
        verify.assert_called_once()

    def test_manifest_and_strategy_are_cursor_specific(self):
        manifest = _manifest()
        validate_cursor_gate_manifest(manifest)
        self.assertEqual(
            input_readiness_strategy_for("cursor"),
            CURSOR_STARTUP_GATE_REDUCER,
        )
        self.assertNotEqual(
            input_readiness_strategy_for("codex"),
            CURSOR_STARTUP_GATE_REDUCER,
        )
        self.assertEqual(
            cursor_gate_timing_policy()["startup_deadline_seconds"],
            startup_settle_seconds_for("cursor"),
        )


if __name__ == "__main__":
    unittest.main()
