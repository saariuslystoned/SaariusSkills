from __future__ import annotations

import os
import stat
import subprocess
import sys
import tempfile
import threading
import unittest
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "puppet" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from puppet_lib import session as session_module  # noqa: E402
from puppet_lib import viewer  # noqa: E402
from puppet_lib.errors import (  # noqa: E402
    ConflictError,
    IdentityError,
    UnsupportedError,
    ValidationError,
)
from puppet_lib.tmux import TmuxController  # noqa: E402


class NativeViewerArtifactTests(unittest.TestCase):
    def _state_root(self, parent: str) -> Path:
        root = Path(parent) / "state"
        root.mkdir(mode=0o700)
        os.chmod(root, 0o700)
        return root

    @staticmethod
    def _expected_identity() -> dict[str, object]:
        return {
            "socket_identity_sha256": "1" * 64,
            "server_identity_sha256": "2" * 64,
            "tmux_binary_identity_sha256": "3" * 64,
            "process_identity_sha256": "4" * 64,
            "pane": "%1",
            "pane_pid": 1234,
            "attach_argv_sha256": "5" * 64,
        }

    def _prepare(self, temporary: str, *, now: float = 100.0):
        root = self._state_root(temporary)
        helper = Path(temporary) / "viewer helper.py"
        helper.write_text("# helper\n", encoding="utf-8")
        app = Path(temporary) / "Exact Terminal.app"
        app.mkdir()
        interpreter = Path(sys.executable).resolve(strict=True)
        ticket = viewer.build_view_ticket(
            session="puppet-codex",
            state_root=root,
            expected_identity=self._expected_identity(),
            helper_path=helper,
            interpreter_path=interpreter,
            now=now,
        )
        ticket_path = (
            root.resolve(strict=True)
            / "views"
            / ("puppet-codex-" + ticket["nonce"] + ".json")
        )
        argv = [
            str(interpreter),
            str(helper.resolve(strict=True)),
            "--state-root",
            str(root.resolve(strict=True)),
            "--session",
            "puppet-codex",
            "--ticket",
            str(ticket_path),
        ]
        applications = {"iterm": ("iTerm", (app,))}
        with patch.dict(viewer._TERMINAL_APPLICATIONS, applications, clear=True):
            prepared = viewer.prepare_operator_view(
                helper_argv=argv,
                ticket=ticket,
                state_root=root,
                session="puppet-codex",
                terminal="iterm",
            )
        return root, helper, app, interpreter, ticket, prepared

    def test_prepares_exact_one_use_argv_and_private_artifacts(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, _helper, app, _interpreter, _ticket, prepared = self._prepare(
                temporary
            )

            command = Path(prepared["viewer_command"])
            ticket_path = Path(prepared["ticket_path"])
            self.assertEqual(stat.S_IMODE(command.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE(ticket_path.stat().st_mode), 0o600)
            self.assertEqual(prepared["terminal_app_path"], str(app.resolve()))
            payload = command.read_text(encoding="utf-8")
            self.assertIn("exec ", payload)
            self.assertIn(str(root.resolve()), payload)
            self.assertIn(str(ticket_path), payload)
            self.assertNotIn("capture-" + "pane", payload)
            self.assertNotIn("pipe-" + "pane", payload)

    def test_rejects_arbitrary_shell_or_authority_argv(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self._state_root(temporary)
            helper = Path(temporary) / "helper.py"
            helper.write_text("# helper\n", encoding="utf-8")
            app = Path(temporary) / "Terminal.app"
            app.mkdir()
            interpreter = Path(sys.executable).resolve(strict=True)
            ticket = viewer.build_view_ticket(
                session="puppet-codex",
                state_root=root,
                expected_identity=self._expected_identity(),
                helper_path=helper,
                interpreter_path=interpreter,
                now=100.0,
            )
            applications = {"iterm": ("iTerm", (app,))}
            with (
                patch.dict(viewer._TERMINAL_APPLICATIONS, applications, clear=True),
                self.assertRaisesRegex(ValidationError, "grammar"),
            ):
                viewer.prepare_operator_view(
                    helper_argv=["/bin/sh", "-c", "tmux attach-session -r"],
                    ticket=ticket,
                    state_root=root,
                    session="puppet-codex",
                    terminal="iterm",
                )

    def test_dispatch_uses_exact_bundle_and_revalidates_both_artifacts(self):
        with tempfile.TemporaryDirectory() as temporary:
            _root, _helper, app, _interpreter, _ticket, prepared = self._prepare(
                temporary
            )
            open_binary = Path(temporary) / "open"
            open_binary.write_text("", encoding="utf-8")
            calls = []

            def run(arguments, **kwargs):
                calls.append((arguments, kwargs))
                return SimpleNamespace(returncode=0)

            viewer.dispatch_operator_view(
                prepared,
                _run=run,
                _open_binary=open_binary,
            )
            self.assertEqual(
                calls[0][0],
                [
                    str(open_binary),
                    "-a",
                    str(app.resolve()),
                    prepared["viewer_command"],
                ],
            )
            self.assertIs(calls[0][1]["stdout"], subprocess.DEVNULL)

            Path(prepared["viewer_command"]).write_text(
                "#!/bin/sh\nexit 0\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(ValidationError, "identity changed"):
                viewer.dispatch_operator_view(
                    prepared,
                    _run=run,
                    _open_binary=open_binary,
                )

    def test_dispatch_rejects_terminal_bundle_identity_drift(self):
        with tempfile.TemporaryDirectory() as temporary:
            _root, _helper, app, _interpreter, _ticket, prepared = self._prepare(
                temporary
            )
            open_binary = Path(temporary) / "open"
            open_binary.write_text("", encoding="utf-8")
            os.chmod(app, 0o700)
            with self.assertRaisesRegex(ValidationError, "identity changed"):
                viewer.dispatch_operator_view(
                    prepared,
                    _run=lambda *_args, **_kwargs: self.fail("open was invoked"),
                    _open_binary=open_binary,
                )

    def test_ticket_claim_is_one_use_and_structurally_visible(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, helper, _app, interpreter, ticket, prepared = self._prepare(temporary)
            ticket_path = Path(prepared["ticket_path"])
            claimed = viewer.load_and_claim_ticket(
                ticket_path=ticket_path,
                state_root=root,
                session="puppet-codex",
                helper_path=helper,
                interpreter_path=interpreter,
                claimant_pid=4321,
                claimant_kernel_birth_id="darwin:100:4321",
                now=ticket["issued_at"] + 1,
            )
            self.assertEqual(claimed["nonce"], ticket["nonce"])
            self.assertEqual(
                viewer.ticket_claim_identity(ticket_path),
                {
                    "schema": viewer.CLAIM_SCHEMA,
                    "pid": 4321,
                    "kernel_birth_id": "darwin:100:4321",
                },
            )
            with self.assertRaisesRegex(ConflictError, "already claimed"):
                viewer.load_and_claim_ticket(
                    ticket_path=ticket_path,
                    state_root=root,
                    session="puppet-codex",
                    helper_path=helper,
                    interpreter_path=interpreter,
                    claimant_pid=4321,
                    claimant_kernel_birth_id="darwin:100:4321",
                    now=ticket["issued_at"] + 2,
                )

    def test_expired_revoked_and_helper_drifted_tickets_fail_closed(self):
        for failure in ("expired", "revoked", "helper"):
            with (
                self.subTest(failure=failure),
                tempfile.TemporaryDirectory() as temporary,
            ):
                root, helper, _app, interpreter, ticket, prepared = self._prepare(
                    temporary
                )
                ticket_path = Path(prepared["ticket_path"])
                now = ticket["issued_at"] + 1
                expected_error = ValidationError
                if failure == "expired":
                    now = ticket["expires_at"]
                elif failure == "revoked":
                    viewer.revoke_ticket(ticket_path)
                    expected_error = ConflictError
                else:
                    helper.write_text("# changed helper\n", encoding="utf-8")
                with self.assertRaises(expected_error):
                    viewer.load_and_claim_ticket(
                        ticket_path=ticket_path,
                        state_root=root,
                        session="puppet-codex",
                        helper_path=helper,
                        interpreter_path=interpreter,
                        claimant_pid=4321,
                        claimant_kernel_birth_id="darwin:100:4321",
                        now=now,
                    )

    def test_dangling_revocation_symlink_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            _root, _helper, _app, _interpreter, _ticket, prepared = self._prepare(
                temporary
            )
            ticket_path = Path(prepared["ticket_path"])
            revoked = ticket_path.with_suffix(".revoked")
            revoked.symlink_to(Path(temporary) / "missing")
            with self.assertRaisesRegex(ValidationError, "marker identity"):
                viewer.revoke_ticket(ticket_path)

    def test_marker_is_invisible_until_fully_written_atomic_publication(self):
        with tempfile.TemporaryDirectory() as temporary:
            marker = Path(temporary) / "claim.claimed"
            link_ready = threading.Event()
            publish = threading.Event()
            errors = []
            real_link = os.link

            def paused_link(source, destination, **kwargs):
                link_ready.set()
                if not publish.wait(timeout=2):
                    raise RuntimeError("test publication timeout")
                return real_link(source, destination, **kwargs)

            def writer():
                try:
                    with patch.object(viewer.os, "link", side_effect=paused_link):
                        viewer._create_marker(
                            marker,
                            {
                                "schema": viewer.CLAIM_SCHEMA,
                                "pid": 4321,
                                "kernel_birth_id": "darwin:100:4321",
                            },
                        )
                except BaseException as exc:  # pragma: no cover - asserted below
                    errors.append(exc)

            thread = threading.Thread(target=writer)
            thread.start()
            self.assertTrue(link_ready.wait(timeout=2))
            self.assertIsNone(viewer._marker_payload(marker))
            publish.set()
            thread.join(timeout=2)
            self.assertFalse(thread.is_alive())
            self.assertEqual(errors, [])
            self.assertEqual(
                viewer._marker_payload(marker),
                {
                    "schema": viewer.CLAIM_SCHEMA,
                    "pid": 4321,
                    "kernel_birth_id": "darwin:100:4321",
                },
            )


class NativeViewerSessionTests(unittest.TestCase):
    @staticmethod
    def _record() -> dict[str, object]:
        return {
            "tmux": {
                "socket": "/private/tmp/puppet.sock",
                "pane": "%1",
                "socket_identity": {"inode": 1},
                "server_identity": {"pid": 20},
                "tmux_binary_identity": {"inode": 2},
            },
            "process": {"pid": 1234},
        }

    @staticmethod
    def _metadata() -> dict[str, object]:
        return {"pane": "%1", "pane_pid": 1234}

    def _session_patches(self, root: Path, client_results):
        record = self._record()
        registry = MagicMock()
        registry.load.return_value = record
        tmux = MagicMock()
        tmux.attach_argv.return_value = [
            "/opt/homebrew/bin/tmux",
            "-f",
            "/dev/null",
            "-S",
            "/private/tmp/puppet.sock",
            "attach-session",
            "-r",
            "-E",
            "-t",
            "puppet-codex",
        ]
        tmux.viewer_clients.side_effect = client_results
        ticket_path = root / "views" / "puppet-codex-nonce.json"
        prepared = {
            "terminal_app": "iTerm",
            "terminal_app_path": "/Applications/iTerm.app",
            "ticket_path": str(ticket_path),
            "viewer_command": str(ticket_path.with_suffix(".command")),
        }
        patches = (
            patch.object(session_module, "SessionRegistry", return_value=registry),
            patch.object(session_module, "_bound_contract"),
            patch.object(
                session_module,
                "_runtime",
                return_value=(tmux, self._metadata()),
            ),
            patch.object(
                session_module,
                "build_view_ticket",
                return_value={"nonce": "nonce"},
            ),
            patch.object(
                session_module, "prepare_operator_view", return_value=prepared
            ),
            patch.object(session_module, "dispatch_operator_view"),
            patch.object(session_module, "revoke_ticket"),
        )
        return tmux, ticket_path, patches

    def test_manual_attach_command_is_ticketed_not_raw_tmux(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve(strict=True)
            record = self._record()
            registry = MagicMock()
            registry.load.return_value = record
            tmux = MagicMock()
            tmux.attach_argv.return_value = [
                "/opt/homebrew/bin/tmux",
                "-f",
                "/dev/null",
                "-S",
                "/private/tmp/puppet.sock",
                "attach-session",
                "-r",
                "-E",
                "-t",
                "puppet-codex",
            ]
            with (
                patch.object(session_module, "SessionRegistry", return_value=registry),
                patch.object(session_module, "_bound_contract"),
                patch.object(
                    session_module,
                    "_runtime",
                    return_value=(tmux, self._metadata()),
                ),
            ):
                result = session_module.attach_command(
                    state_root=root,
                    session="puppet-codex",
                )
            self.assertTrue(result["execution_time_identity_check"])
            self.assertEqual(result["ticket_ttl_seconds"], viewer.TICKET_TTL_SECONDS)
            self.assertIn("viewer_attach.py", result["attach_command"])
            self.assertNotIn("attach-session", result["attach_command"])
            self.assertTrue(Path(result["ticket_path"]).is_file())

    def test_open_success_requires_claim_and_new_read_only_tmux_client(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            tmux, ticket_path, patches = self._session_patches(
                root,
                [[], [{"pid": 55, "tty": "/dev/ttys055", "read_only": True}]],
            )
            with ExitStack() as stack:
                mocks = [stack.enter_context(item) for item in patches]
                stack.enter_context(
                    patch.object(
                        session_module,
                        "ticket_claim_identity",
                        return_value={
                            "schema": viewer.CLAIM_SCHEMA,
                            "pid": 55,
                            "kernel_birth_id": "darwin:100:55",
                        },
                    )
                )
                stack.enter_context(
                    patch.object(
                        session_module,
                        "process_birth_identity",
                        return_value={
                            "pid": 55,
                            "kernel_birth_id": "darwin:100:55",
                        },
                    )
                )
                stack.enter_context(
                    patch.object(
                        session_module.time,
                        "monotonic",
                        side_effect=[0.0, 0.1],
                    )
                )
                stack.enter_context(patch.object(session_module.time, "sleep"))
                result = session_module.open_view(
                    state_root=root,
                    session="puppet-codex",
                    terminal="iterm",
                )
                mocks[-1].assert_called_once_with(ticket_path)
            self.assertTrue(result["viewer_attached"])
            self.assertTrue(result["native_tui"])
            self.assertTrue(result["ticket_revoked"])
            self.assertEqual(tmux.viewer_clients.call_count, 2)
            self.assertEqual(ticket_path.suffix, ".json")

    def test_unrelated_read_only_client_cannot_satisfy_helper_claim(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _tmux, _ticket_path, patches = self._session_patches(
                root,
                [[], [{"pid": 77, "tty": "/dev/ttys077", "read_only": True}]],
            )
            with ExitStack() as stack:
                mocks = [stack.enter_context(item) for item in patches]
                stack.enter_context(
                    patch.object(
                        session_module,
                        "ticket_claim_identity",
                        return_value={
                            "schema": viewer.CLAIM_SCHEMA,
                            "pid": 55,
                            "kernel_birth_id": "darwin:100:55",
                        },
                    )
                )
                stack.enter_context(
                    patch.object(
                        session_module.time,
                        "monotonic",
                        side_effect=[0.0, 0.1, 11.0],
                    )
                )
                stack.enter_context(patch.object(session_module.time, "sleep"))
                with self.assertRaisesRegex(
                    UnsupportedError, "not structurally observed"
                ):
                    session_module.open_view(
                        state_root=root,
                        session="puppet-codex",
                        terminal="iterm",
                    )
                mocks[-1].assert_called_once()

    def test_open_return_code_without_new_client_is_not_viewer_proof(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _tmux, _ticket_path, patches = self._session_patches(root, [[], []])
            with ExitStack() as stack:
                mocks = [stack.enter_context(item) for item in patches]
                stack.enter_context(
                    patch.object(
                        session_module.time,
                        "monotonic",
                        side_effect=[0.0, 11.0],
                    )
                )
                stack.enter_context(patch.object(session_module.time, "sleep"))
                with self.assertRaisesRegex(
                    UnsupportedError, "not structurally observed"
                ):
                    session_module.open_view(
                        state_root=root,
                        session="puppet-codex",
                        terminal="iterm",
                    )
                mocks[-1].assert_called_once()

    def test_new_write_client_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _tmux, _ticket_path, patches = self._session_patches(
                root,
                [[], [{"pid": 56, "tty": "/dev/ttys056", "read_only": False}]],
            )
            with ExitStack() as stack:
                mocks = [stack.enter_context(item) for item in patches]
                stack.enter_context(
                    patch.object(
                        session_module.time,
                        "monotonic",
                        side_effect=[0.0, 0.1],
                    )
                )
                stack.enter_context(patch.object(session_module.time, "sleep"))
                with self.assertRaisesRegex(IdentityError, "not read-only"):
                    session_module.open_view(
                        state_root=root,
                        session="puppet-codex",
                        terminal="iterm",
                    )
                mocks[-1].assert_called_once()

    def test_polling_exception_always_revokes_ticket(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _tmux, _ticket_path, patches = self._session_patches(
                root,
                [[], IdentityError("client inventory drift")],
            )
            with ExitStack() as stack:
                mocks = [stack.enter_context(item) for item in patches]
                stack.enter_context(
                    patch.object(
                        session_module.time,
                        "monotonic",
                        side_effect=[0.0, 0.1],
                    )
                )
                with self.assertRaisesRegex(IdentityError, "inventory drift"):
                    session_module.open_view(
                        state_root=root,
                        session="puppet-codex",
                        terminal="iterm",
                    )
                mocks[-1].assert_called_once()

    def test_execution_time_runtime_drift_prevents_tmux_exec(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            record = self._record()
            registry = MagicMock()
            registry.load.return_value = record
            tmux = MagicMock()
            tmux.attach_argv.return_value = ["/opt/homebrew/bin/tmux", "-r"]
            with (
                patch.object(session_module, "SessionRegistry", return_value=registry),
                patch.object(session_module, "_bound_contract"),
                patch.object(
                    session_module,
                    "_runtime",
                    return_value=(tmux, self._metadata()),
                ),
                patch.object(
                    session_module,
                    "load_and_claim_ticket",
                    return_value={"expected_identity": {"drifted": True}},
                ),
                patch.object(session_module.os, "execve") as execve,
                self.assertRaisesRegex(IdentityError, "runtime identity changed"),
            ):
                session_module.attach_viewer(
                    state_root=root,
                    session="puppet-codex",
                    ticket_path=root / "views" / "puppet-codex-nonce.json",
                )
            execve.assert_not_called()


class NativeViewerTmuxTests(unittest.TestCase):
    def test_structural_client_inventory_and_exact_attach_argv(self):
        controller = object.__new__(TmuxController)
        controller.tmux_binary = Path("/opt/homebrew/bin/tmux")
        socket = Path("/private/tmp/puppet.sock")
        result = SimpleNamespace(
            returncode=0,
            stdout=(
                "52\t/dev/ttys052\t1\tpuppet-codex\n53\t/dev/ttys053\t0\tpuppet-codex\n"
            ),
        )
        with (
            patch.object(controller, "_verify_server_identity"),
            patch.object(controller, "exists", return_value=True),
            patch.object(controller, "_run", return_value=result),
        ):
            clients = controller.viewer_clients(
                socket=socket,
                session="puppet-codex",
                server_identity={"pid": 20},
            )
        self.assertEqual(
            clients,
            [
                {
                    "pid": 52,
                    "tty": "/dev/ttys052",
                    "read_only": True,
                    "session": "puppet-codex",
                },
                {
                    "pid": 53,
                    "tty": "/dev/ttys053",
                    "read_only": False,
                    "session": "puppet-codex",
                },
            ],
        )
        with patch.object(controller, "metadata"):
            argv = controller.attach_argv(
                socket=socket,
                session="puppet-codex",
                pane="%1",
                server_identity={"pid": 20},
            )
        self.assertEqual(
            argv,
            [
                "/opt/homebrew/bin/tmux",
                "-f",
                os.devnull,
                "-S",
                str(socket),
                "attach-session",
                "-r",
                "-E",
                "-t",
                "puppet-codex",
            ],
        )


if __name__ == "__main__":
    unittest.main()
