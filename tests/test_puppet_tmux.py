from __future__ import annotations

import shlex
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
                self.assertEqual(panes[0], controller.metadata(socket=socket, session=session, pane=metadata["pane"])["pane"])
                with self.assertRaisesRegex(IdentityError, "pane identity"):
                    controller.metadata(socket=socket, session=session, pane="%999")
                command = controller.attach_command(
                    socket=socket, session=session, pane=metadata["pane"]
                )
                parts = shlex.split(command)
                self.assertEqual(parts[:2], ["tmux", "-S"])
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
                    )
                with self.assertRaisesRegex(IdentityError, "unexpected pane topology"):
                    controller.metadata_for_session(socket=socket, session=session)
                controller.interrupt(
                    socket=socket,
                    session=session,
                    pane=initial[0],
                )
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
