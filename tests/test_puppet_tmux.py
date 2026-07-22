from __future__ import annotations

import os
import shlex
import socket as socket_module
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "puppet" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from puppet_lib.errors import IdentityError  # noqa: E402
from puppet_lib.tmux import TmuxController  # noqa: E402


class TmuxTransportTests(unittest.TestCase):
    def _tmux_run(self, *, socket: Path, arguments: list[str]) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["tmux", "-S", str(socket)] + arguments,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )

    def _kill(self, *, socket: Path, session: str) -> None:
        self._tmux_run(socket=socket, arguments=["kill-server"])
        socket.unlink(missing_ok=True)

    def _list_panes(self, *, socket: Path, session: str):
        result = self._tmux_run(
            socket=socket,
            arguments=["list-panes", "-t", session, "-F", "#{pane_id}"],
        )
        if result.returncode != 0:
            return []
        return [line for line in result.stdout.splitlines() if line.strip()]

    def test_launch_records_single_initial_pane(self):
        if not TmuxController.available():
            self.skipTest("tmux is unavailable")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root / "repo"
            repo.mkdir()
            controller = TmuxController(root)
            session = "tmux-single-pane"
            metadata = controller.launch(
                session=session,
                repo=repo,
                argv=["/bin/sleep", "600"],
            )
            socket = Path(metadata["socket"])
            try:
                panes = self._list_panes(socket=socket, session=session)
                self.assertEqual(len(panes), 1)
                self.assertEqual(panes[0], metadata["pane"])
                self.assertEqual(
                    metadata["socket_identity"],
                    controller.socket_identity(socket),
                )
                self.assertEqual(
                    metadata["tmux_binary_identity"],
                    controller.tmux_binary_identity(),
                )
                self.assertEqual(
                    metadata["tmux_binary_identity"]["path"],
                    controller.tmux_binary.as_posix(),
                )
                self.assertIn("server_identity", metadata)
                self.assertEqual(
                    panes[0],
                    controller.metadata(
                        socket=socket,
                        session=session,
                        pane=metadata["pane"],
                        server_identity=metadata["server_identity"],
                    )["pane"],
                )
                command = controller.attach_command(
                    socket=socket,
                    session=session,
                    server_identity=metadata["server_identity"],
                )
                parts = shlex.split(command)
                self.assertEqual(parts[0], metadata["tmux_binary_identity"]["path"])
                self.assertEqual(parts[2], str(socket))
                self.assertEqual(parts[-1], session)
            finally:
                self._kill(socket=socket, session=session)

    def test_interrupt_requires_exact_pane_after_topology_change(self):
        if not TmuxController.available():
            self.skipTest("tmux is unavailable")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root / "repo"
            repo.mkdir()
            controller = TmuxController(root)
            session = "tmux-panes"
            metadata = controller.launch(
                session=session,
                repo=repo,
                argv=["/bin/sleep", "600"],
            )
            socket = Path(metadata["socket"])
            try:
                initial = self._list_panes(socket=socket, session=session)
                self.assertEqual(len(initial), 1)
                self._tmux_run(
                    socket=socket,
                    arguments=["split-window", "-t", session, "/bin/sleep", "600"],
                )
                panes = self._list_panes(socket=socket, session=session)
                self.assertGreaterEqual(len(panes), 2)
                with self.assertRaisesRegex(IdentityError, "pane identity"):
                    controller.interrupt(
                        socket=socket,
                        session=session,
                        pane="%999",
                        server_identity=metadata["server_identity"],
                    )
                with self.assertRaisesRegex(IdentityError, "unexpected pane topology"):
                    controller.metadata_for_session(
                        socket=socket,
                        session=session,
                        server_identity=metadata["server_identity"],
                    )
                controller.interrupt(
                    socket=socket,
                    session=session,
                    pane=initial[0],
                    server_identity=metadata["server_identity"],
                )
            finally:
                self._kill(socket=socket, session=session)

    def test_launch_preserves_immediate_target_exit_pane(self):
        if not TmuxController.available():
            self.skipTest("tmux is unavailable")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root / "repo"
            repo.mkdir()
            controller = TmuxController(root)
            session = "tmux-immediate-exit"
            metadata = controller.launch(
                session=session,
                repo=repo,
                argv=["/bin/true"],
            )
            socket = Path(metadata["socket"])
            try:
                self.assertTrue(metadata["pane_dead"])
                current = controller.metadata(
                    socket=socket,
                    session=session,
                    pane=metadata["pane"],
                    server_identity=metadata["server_identity"],
                )
                self.assertEqual(current["pane"], metadata["pane"])
                self.assertTrue(current["pane_dead"])
            finally:
                self._kill(socket=socket, session=session)

    def test_paste_bytes_streams_literal_data_via_stdin(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            controller = TmuxController(root)
            socket = root / "sock"
            payload = b"prompt:Do the task\ntest-bytes"
            calls = []

            def fake_run(command, **kwargs):
                calls.append((command, kwargs.get("input")))
                return SimpleNamespace(args=command, returncode=0, stdout=b"", stderr=b"")

            with patch.object(
                controller,
                "metadata",
                return_value={"pane": "%1", "pane_dead": False},
            ):
                with patch.object(controller, "assert_tmux_binary_identity"):
                    with patch("puppet_lib.tmux.subprocess.run", side_effect=fake_run):
                        controller.paste_bytes(
                            socket=socket,
                            session="session-one",
                            pane="%1",
                            buffer_name="session-one-prompt",
                            payload=payload,
                        )

            load_buffer_calls = [
                call for call in calls if call[0][3] == "load-buffer" and call[0][4] == "-b"
            ]
            self.assertEqual(len(load_buffer_calls), 1)
            self.assertEqual(load_buffer_calls[0][1], payload)
            self.assertEqual(load_buffer_calls[0][0][-1], "-")
            self.assertNotIn("prompt:Do the task", " ".join(load_buffer_calls[0][0]))
            paste_calls = [call for call in calls if "paste-buffer" in call[0]]
            self.assertEqual(len(paste_calls), 1)
            self.assertEqual(paste_calls[0][0][-1], "%1")
            flattened = " ".join(token for call in calls for token in call[0])
            self.assertIn("delete-buffer", flattened)

    def test_tmux_binary_drift_is_detected(self):
        if not TmuxController.available():
            self.skipTest("tmux is unavailable")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            controller = TmuxController(root)
            original = controller.tmux_binary_identity()
            drifted = dict(original)
            drifted["sha256"] = "0" * len(original["sha256"])
            with patch.object(
                TmuxController,
                "binary_identity",
                return_value=original,
            ):
                controller.assert_tmux_binary_identity(expected=original)
            with patch.object(
                TmuxController,
                "binary_identity",
                return_value=drifted,
            ):
                with self.assertRaises(IdentityError):
                    controller.assert_tmux_binary_identity(expected=original)

    def test_launch_cleans_up_private_session_on_launch_keyboard_interrupt(self):
        if not TmuxController.available():
            self.skipTest("tmux is unavailable")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root / "repo"
            repo.mkdir()
            controller = TmuxController(root)
            session = "tmux-cleanup"
            calls: list[tuple[list[str], bool, bytes | None]] = []
            cleanup_server = None

            def fake_run_raw(command, *, check=True, input_data=None):
                nonlocal cleanup_server
                calls.append((command, check, input_data))
                if command[3] == "has-session":
                    return SimpleNamespace(args=command, returncode=1, stdout=b"", stderr=b"")
                if command[3] == "new-session":
                    cleanup_server = socket_module.socket(
                        socket_module.AF_UNIX, socket_module.SOCK_STREAM
                    )
                    cleanup_server.bind(command[2])
                    os.chmod(command[2], 0o600)
                    return SimpleNamespace(args=command, returncode=0, stdout=b"", stderr=b"")
                if command[3] == "set-option":
                    return SimpleNamespace(args=command, returncode=0, stdout=b"", stderr=b"")
                if command[3] == "respawn-pane":
                    raise KeyboardInterrupt
                if command[3] == "kill-session":
                    return SimpleNamespace(args=command, returncode=0, stdout=b"", stderr=b"")
                return SimpleNamespace(args=command, returncode=0, stdout=b"", stderr=b"")

            try:
                with patch.object(controller, "_run_raw", side_effect=fake_run_raw):
                    with self.assertRaises(KeyboardInterrupt):
                        controller.launch(
                            session=session,
                            repo=repo,
                            argv=["/bin/true"],
                        )
            finally:
                if cleanup_server is not None:
                    cleanup_server.close()
                controller.socket_path(session).unlink(missing_ok=True)

            self.assertTrue(
                any(call[0][3] == "kill-session" and call[0][5] == session for call in calls),
                calls,
            )

    def test_launch_reconciles_exact_session_when_socket_identity_capture_fails(self):
        if not TmuxController.available():
            self.skipTest("tmux is unavailable")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root / "repo"
            repo.mkdir()
            controller = TmuxController(root)
            session = "tmux-socket-identity-failure"
            socket = controller.socket_path(session)
            with patch.object(
                controller,
                "socket_identity",
                side_effect=IdentityError("injected socket identity failure"),
            ):
                with self.assertRaisesRegex(IdentityError, "injected"):
                    controller.launch(
                        session=session,
                        repo=repo,
                        argv=["/bin/sleep", "600"],
                    )
            result = self._tmux_run(
                socket=socket,
                arguments=["has-session", "-t", session],
            )
            self.assertNotEqual(result.returncode, 0)
