from __future__ import annotations

import os
import json
import pty
import shlex
import signal
import socket as socket_module
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "puppet" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from puppet_lib.errors import IdentityError, ValidationError  # noqa: E402
from puppet_lib.launch import (  # noqa: E402
    build_admitted_launch_plan,
    build_launch_identity,
    control_environment,
    public_launch_identity,
    select_launch_environment,
    validate_admitted_launch_plan,
)
from puppet_lib.profiles import SUBMIT_SETTLE_SECONDS  # noqa: E402
from puppet_lib.probe import _assert_runtime  # noqa: E402
from puppet_lib.registry import (  # noqa: E402
    process_birth_identity,
    send_exact_sigint,
)
from puppet_lib.safety import tmux_socket_identities_match  # noqa: E402
from puppet_lib.tmux import TargetLaunch, TmuxController  # noqa: E402


class TmuxTransportTests(unittest.TestCase):
    @staticmethod
    def _launch_environment(
        target: str = "codex",
        admitted_lane_root: Path | None = None,
        **bindings: str,
    ) -> dict[str, str]:
        return select_launch_environment(
            target=target,
            bindings=bindings,
            admitted_lane_root=admitted_lane_root,
        )

    def _tmux_run(
        self, *, socket: Path, arguments: list[str]
    ) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["tmux", "-f", os.devnull, "-S", str(socket)] + arguments,
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

    def _assert_target_start_failure_cleans_up(
        self,
        *,
        controller,
        session,
        repo,
        argv,
        environment,
        before_target_start,
        exception,
        message,
    ):
        socket = controller.socket_path(session)
        socket_identity = {
            "device": 1,
            "inode": 2,
            "uid": os.getuid(),
            "mode": 0o600,
        }
        with (
            patch.object(controller, "exists", return_value=False),
            patch.object(controller, "_start_server") as start_server,
            patch.object(controller, "socket_identity", return_value=socket_identity),
            patch.object(
                controller,
                "_run",
                return_value=SimpleNamespace(
                    args=[], returncode=0, stdout="", stderr=""
                ),
            ) as run,
            patch.object(controller, "_kill_session") as kill_session,
        ):
            with self.assertRaisesRegex(exception, message):
                controller.launch(
                    session=session,
                    target="codex",
                    repo=repo,
                    argv=argv,
                    environment=environment,
                    before_target_start=before_target_start,
                )
        start_server.assert_called_once()
        self.assertFalse(
            any("respawn-pane" in call.args[1] for call in run.call_args_list)
        )
        kill_session.assert_called_once_with(
            socket=socket,
            session=session,
            socket_identity=socket_identity,
            created_by_launch=True,
        )

    def test_socket_identity_ignores_only_owner_execute_attached_state(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            socket_path = root / "identity.sock"
            bound_socket = socket_module.socket(
                socket_module.AF_UNIX, socket_module.SOCK_STREAM
            )
            try:
                bound_socket.bind(str(socket_path))
                socket_path.chmod(0o600)
                initial = TmuxController.socket_identity(socket_path)
                socket_path.chmod(0o700)
                attached = TmuxController.socket_identity(socket_path)

                self.assertEqual(initial, attached)
                self.assertEqual(attached["mode"], 0o600)
                self.assertTrue(
                    tmux_socket_identities_match(
                        {**initial, "mode": 0o700}, attached
                    )
                )

                for field in ("device", "inode", "uid"):
                    with self.subTest(drift=field):
                        drifted = {**initial, field: initial[field] + 1}
                        self.assertFalse(
                            tmux_socket_identities_match(initial, drifted)
                        )

                socket_path.chmod(0o500)
                self.assertNotEqual(
                    TmuxController.socket_identity(socket_path), initial
                )
                for unsafe_mode in (0o610, 0o601):
                    with self.subTest(unsafe_mode=oct(unsafe_mode)):
                        socket_path.chmod(unsafe_mode)
                        with self.assertRaisesRegex(
                            IdentityError, "not user-private"
                        ):
                            TmuxController.socket_identity(socket_path)

                symlink_path = root / "identity-link.sock"
                symlink_path.symlink_to(socket_path)
                with self.assertRaisesRegex(IdentityError, "symlink"):
                    TmuxController.socket_identity(symlink_path)
                regular_path = root / "not-a-socket"
                regular_path.touch()
                with self.assertRaisesRegex(IdentityError, "not a socket"):
                    TmuxController.socket_identity(regular_path)
            finally:
                bound_socket.close()

    def test_kill_session_accepts_owner_execute_transition_only(self):
        if not TmuxController.available():
            self.skipTest("tmux is unavailable")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            controller = TmuxController(root)
            socket_path = root / "cleanup.sock"
            bound_socket = socket_module.socket(
                socket_module.AF_UNIX, socket_module.SOCK_STREAM
            )
            try:
                bound_socket.bind(str(socket_path))
                socket_path.chmod(0o600)
                identity = controller.socket_identity(socket_path)
                socket_path.chmod(0o700)
                with patch.object(controller, "_run_raw") as run:
                    controller._kill_session(
                        socket=socket_path,
                        session="cleanup-owner-execute",
                        socket_identity=identity,
                    )
                run.assert_called_once()
                self.assertIn("kill-session", run.call_args.args[0])

                socket_path.chmod(0o500)
                with patch.object(controller, "_run_raw") as run:
                    controller._kill_session(
                        socket=socket_path,
                        session="cleanup-owner-mode-drift",
                        socket_identity=identity,
                    )
                run.assert_not_called()

                socket_path.chmod(0o710)
                with patch.object(controller, "_run_raw") as run:
                    controller._kill_session(
                        socket=socket_path,
                        session="cleanup-group-access",
                        socket_identity=identity,
                    )
                run.assert_not_called()
            finally:
                bound_socket.close()

    def test_real_readonly_attach_mode_preserves_socket_identity(self):
        if sys.platform != "darwin":
            self.skipTest("tmux attached-state mode regression is Darwin-specific")
        if not TmuxController.available():
            self.skipTest("tmux is unavailable")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            controller = TmuxController(root)
            session = "tmux-readonly-attach-mode"
            socket_path = controller.socket_path(session)
            started = self._tmux_run(
                socket=socket_path,
                arguments=[
                    "new-session",
                    "-d",
                    "-s",
                    session,
                    "/bin/sleep",
                    "60",
                ],
            )
            self.assertEqual(started.returncode, 0, started.stderr)
            client = None
            master_fd = None
            try:
                self.assertEqual(
                    stat.S_IMODE(socket_path.stat().st_mode), 0o600
                )
                initial = controller.socket_identity(socket_path)
                master_fd, slave_fd = pty.openpty()
                try:
                    client = subprocess.Popen(
                        [
                            controller.tmux_binary.as_posix(),
                            "-f",
                            os.devnull,
                            "-S",
                            str(socket_path),
                            "attach-session",
                            "-r",
                            "-E",
                            "-t",
                            session,
                        ],
                        stdin=slave_fd,
                        stdout=slave_fd,
                        stderr=slave_fd,
                        env={**control_environment(), "TERM": "xterm-256color"},
                        close_fds=True,
                    )
                finally:
                    os.close(slave_fd)

                deadline = time.monotonic() + 3.0
                attached_mode = None
                while time.monotonic() < deadline:
                    if client.poll() is not None:
                        self.fail(
                            "read-only tmux client exited before attached-state proof"
                        )
                    attached_mode = stat.S_IMODE(socket_path.stat().st_mode)
                    if attached_mode & stat.S_IXUSR:
                        break
                    time.sleep(0.02)
                self.assertEqual(attached_mode, 0o700)
                self.assertEqual(controller.socket_identity(socket_path), initial)
                server_identity = controller.server_identity(socket_path)
                metadata = controller.metadata_for_session(
                    socket=socket_path,
                    session=session,
                    server_identity=server_identity,
                )
                target_process = process_birth_identity(metadata["pane_pid"])
                integrated = _assert_runtime(
                    tmux=controller,
                    socket=socket_path,
                    session=session,
                    pane=metadata["pane"],
                    pane_pid=metadata["pane_pid"],
                    socket_identity=initial,
                    server_identity=server_identity,
                    tmux_binary_identity=controller.tmux_binary_identity(),
                    process=target_process,
                    process_alive_fn=lambda observed: process_birth_identity(
                        observed["pid"]
                    )
                    == observed,
                )
                self.assertEqual(integrated["pane_pid"], target_process["pid"])
            finally:
                if client is not None and client.poll() is None:
                    client.terminate()
                    try:
                        client.wait(timeout=2.0)
                    except subprocess.TimeoutExpired:
                        client.kill()
                        client.wait(timeout=2.0)
                if master_fd is not None:
                    os.close(master_fd)
                self._kill(socket=socket_path, session=session)

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
                target="codex",
                repo=repo,
                argv=["/bin/sleep", "600"],
                environment=self._launch_environment(),
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
                self.assertEqual(parts[1:5], ["-f", os.devnull, "-S", str(socket)])
                self.assertIn("-r", parts)
                self.assertIn("-E", parts)
                self.assertEqual(parts[-1], session)
                update_environment = self._tmux_run(
                    socket=socket,
                    arguments=[
                        "show-options",
                        "-v",
                        "-t",
                        session,
                        "update-environment",
                    ],
                )
                self.assertEqual(update_environment.returncode, 0)
                self.assertEqual(update_environment.stdout, "")
            finally:
                self._kill(socket=socket, session=session)

    def test_launch_normalizes_inherited_sigint_for_exact_halt(self):
        if not TmuxController.available():
            self.skipTest("tmux is unavailable")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root / "repo"
            repo.mkdir()
            controller = TmuxController(root)
            session = "tmux-normalized-sigint"
            socket = controller.socket_path(session)
            original_handler = signal.getsignal(signal.SIGINT)
            original_mask = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGINT})
            metadata = None
            try:
                signal.signal(signal.SIGINT, signal.SIG_IGN)
                metadata = controller.launch(
                    session=session,
                    target="codex",
                    repo=repo,
                    argv=["/bin/sleep", "600"],
                    environment=self._launch_environment(),
                )
            finally:
                signal.signal(signal.SIGINT, original_handler)
                signal.pthread_sigmask(signal.SIG_SETMASK, original_mask)
            try:
                send_exact_sigint(process_birth_identity(metadata["pane_pid"]))
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    observed = controller.metadata_for_session(
                        socket=socket,
                        session=session,
                        server_identity=metadata["server_identity"],
                    )
                    if observed["pane_dead"]:
                        break
                    time.sleep(0.05)
                self.assertTrue(observed["pane_dead"])
            finally:
                self._kill(socket=socket, session=session)

    def test_launch_delivers_only_explicit_environment_and_exact_cwd(self):
        if not TmuxController.available():
            self.skipTest("tmux is unavailable")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root / "repo"
            repo.mkdir()
            home = root / "home"
            home.mkdir()
            (home / ".tmux.conf").write_text(
                "set-environment -g PUPPET_TMUX_CONFIG_LOADED 1\n",
                encoding="utf-8",
            )
            codex_home = root / "private-codex-home"
            codex_home.mkdir()
            codex_home = codex_home.resolve()
            output = root / "target.json"
            source = dict(os.environ)
            source["PUPPET_PARENT_CANARY"] = "parent-canary-value"
            argv = [
                sys.executable,
                "-c",
                (
                    "import json, os, pathlib, sys; "
                    "pathlib.Path(sys.argv[1]).write_text(json.dumps({"
                    "'cwd': os.getcwd(), 'home': os.environ.get('HOME'), "
                    "'codex_home': os.environ.get('CODEX_HOME'), "
                    "'parent_canary': os.environ.get('PUPPET_PARENT_CANARY'), "
                    "'tmux_config': os.environ.get('PUPPET_TMUX_CONFIG_LOADED')}))"
                ),
                str(output),
            ]
            source["HOME"] = str(home)
            environment, expected_identity = build_launch_identity(
                target="codex",
                repo=repo,
                argv=argv,
                source_environment=source,
                bindings={"CODEX_HOME": str(codex_home)},
                admitted_lane_root=root,
            )
            controller = TmuxController(root)
            metadata = controller.launch(
                session="tmux-closed-environment",
                target="codex",
                repo=repo,
                argv=argv,
                environment=environment,
                admitted_lane_root=root,
            )
            socket = Path(metadata["socket"])
            try:
                deadline = time.monotonic() + 2
                while not output.exists() and time.monotonic() < deadline:
                    time.sleep(0.01)
                self.assertTrue(output.is_file())
                observed = json.loads(output.read_text(encoding="utf-8"))
                self.assertEqual(observed["cwd"], str(repo.resolve()))
                self.assertEqual(observed["home"], str(home))
                self.assertEqual(observed["codex_home"], str(codex_home))
                self.assertIsNone(observed["parent_canary"])
                self.assertIsNone(observed["tmux_config"])
                self.assertEqual(metadata["launch_identity"], expected_identity)
                self.assertEqual(
                    set(metadata["launch_identity"]),
                    {"cwd", "argv_sha256", "env_names", "env_fingerprint"},
                )
                serialized = json.dumps(metadata, sort_keys=True)
                self.assertNotIn(str(codex_home), serialized)
                self.assertNotIn("parent-canary-value", serialized)
                self.assertNotIn("launch_environment", metadata)
            finally:
                self._kill(socket=socket, session="tmux-closed-environment")

    def test_closed_environment_rejects_arbitrary_sensitive_and_control_bindings(self):
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            lane_root = repo / "lane"
            lane_root.mkdir()
            codex_home = lane_root / "codex-home"
            codex_home.mkdir()
            codex_home = codex_home.resolve()
            source = {
                "HOME": "/safe/home",
                "PATH": "/usr/bin:/bin",
                "PUPPET_PARENT_CANARY": "must-not-cross",
                "PWD": "/must/not/cross",
                "TERM": "must-not-cross",
            }
            environment, identity = build_launch_identity(
                target="codex",
                repo=repo,
                argv=["/bin/true", "--"],
                source_environment=source,
                bindings={"CODEX_HOME": str(codex_home)},
                admitted_lane_root=lane_root,
            )
            self.assertEqual(
                environment,
                {
                    "CODEX_HOME": str(codex_home),
                    "HOME": "/safe/home",
                    "PATH": "/usr/bin:/bin",
                },
            )
            self.assertNotIn("must-not-cross", json.dumps(identity, sort_keys=True))
            ambient_extension = dict(source, CODEX_HOME="/ambient/must-not-cross")
            self.assertNotIn(
                "CODEX_HOME",
                select_launch_environment(
                    target="codex",
                    source_environment=ambient_extension,
                ),
            )
            with self.assertRaisesRegex(ValidationError, "explicitly admitted"):
                select_launch_environment(
                    target="codex",
                    bindings={"CODEX_HOME": str(codex_home)},
                )
            outside = repo / "outside"
            outside.mkdir()
            with self.assertRaisesRegex(ValidationError, "escapes"):
                select_launch_environment(
                    target="codex",
                    bindings={"CODEX_HOME": str(outside)},
                    admitted_lane_root=lane_root,
                )
            with self.assertRaisesRegex(ValidationError, "allowlisted"):
                select_launch_environment(
                    target="codex",
                    source_environment=source,
                    bindings={"HOME": "/caller/cannot/override/baseline"},
                )
            for target, config_name in (
                ("codex", "CODEX_HOME"),
                ("claude", "CLAUDE_CONFIG_DIR"),
                ("cursor", "CURSOR_CONFIG_DIR"),
                ("cursor", "CURSOR_DATA_DIR"),
                ("grok", "GROK_HOME"),
            ):
                config_root = lane_root / (target + "-" + config_name.lower())
                config_root.mkdir()
                config_root = config_root.resolve()
                selected = select_launch_environment(
                    target=target,
                    bindings={config_name: str(config_root)},
                    admitted_lane_root=lane_root,
                )
                self.assertEqual(selected[config_name], str(config_root))
            for target, control_name in (
                ("claude", "CLAUDE_CODE_DISABLE_AUTO_MEMORY"),
                ("grok", "GROK_DISABLE_AUTOUPDATER"),
            ):
                control = select_launch_environment(
                    target=target,
                    bindings={control_name: "true"},
                )
                self.assertEqual(control[control_name], "true")
                for bad_control in ("1", "TRUE", ""):
                    with self.subTest(
                        target=target,
                        bad_control=bad_control,
                    ):
                        with self.assertRaisesRegex(ValidationError, "exact true"):
                            select_launch_environment(
                                target=target,
                                bindings={control_name: bad_control},
                            )
            cursor_store = select_launch_environment(
                target="cursor",
                bindings={"AGENT_CLI_CREDENTIAL_STORE": "file"},
            )
            self.assertEqual(cursor_store["AGENT_CLI_CREDENTIAL_STORE"], "file")
            for bad_store in ("keychain", "memory", ""):
                with self.assertRaisesRegex(ValidationError, "exact file"):
                    select_launch_environment(
                        target="cursor",
                        bindings={"AGENT_CLI_CREDENTIAL_STORE": bad_store},
                    )
            for name in (
                "FOO",
                "PWD",
                "OLDPWD",
                "TMUX",
                "TERM",
                "API_TOKEN",
                "PUPPET_SECRET",
                "PRIVATE_KEY_PATH",
                "HARNESS_PASSWORD",
                "GROK_HOME",
            ):
                with self.subTest(name=name):
                    with self.assertRaisesRegex(ValidationError, "allowlisted"):
                        select_launch_environment(
                            target="codex",
                            source_environment=source,
                            bindings={name: "value"},
                        )
            for value in (
                "bad\x00value",
                "bad\nvalue",
                "bad\rvalue",
                "bad\tvalue",
                "bad\x1bvalue",
                "bad\ud800value",
                "bad\u200bvalue",
            ):
                with self.subTest(value=repr(value)):
                    with self.assertRaisesRegex(ValidationError, "value is invalid"):
                        select_launch_environment(
                            target="codex",
                            source_environment=source,
                            bindings={"CODEX_HOME": value},
                        )

    def test_admitted_launch_plan_binds_exact_context_and_rejects_missing_plan_data(
        self,
    ):
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            argv = ["/bin/true", "--literal"]
            environment, identity = build_launch_identity(
                target="codex",
                repo=repo,
                argv=argv,
                source_environment={},
            )
            plan = build_admitted_launch_plan(
                target="codex",
                session="plan-session",
                run_id="plan-run",
                repo=repo,
                argv=argv,
                environment=environment,
            )
            validated = validate_admitted_launch_plan(
                plan,
                expected_target="codex",
                expected_session="plan-session",
                expected_run_id="plan-run",
            )
            self.assertEqual(validated["cwd"], str(repo.resolve()))
            self.assertEqual(validated["argv"], argv)
            self.assertEqual(validated["launch_identity"], identity)

            missing_argv = dict(plan)
            missing_argv.pop("argv")
            with self.assertRaisesRegex(ValidationError, "fields are invalid"):
                validate_admitted_launch_plan(missing_argv)

            malformed_names = dict(plan)
            malformed_names["env_names"] = [{}]
            with self.assertRaisesRegex(
                ValidationError, "environment names are invalid"
            ):
                validate_admitted_launch_plan(malformed_names)

            changed_argv = dict(plan)
            changed_argv["argv"] = ["/bin/false", "--literal"]
            changed = validate_admitted_launch_plan(changed_argv)
            self.assertNotEqual(
                changed["launch_identity"]["argv_sha256"],
                identity["argv_sha256"],
            )

    def test_launch_command_shape_is_direct_value_private_and_same_cwd(self):
        if not TmuxController.available():
            self.skipTest("tmux is unavailable")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root / "repo"
            repo.mkdir()
            secret_root = root / "private-codex-home"
            secret_root.mkdir()
            secret_root = secret_root.resolve()
            secret_value = str(secret_root)
            environment = self._launch_environment(
                admitted_lane_root=root, CODEX_HOME=secret_value
            )
            controller = TmuxController(root)
            session = "tmux-command-shape"
            socket = controller.socket_path(session)
            argv = ["/bin/echo", "argument with spaces", "--literal"]
            calls = []
            admission = []

            def fake_run_raw(
                command,
                *,
                check=True,
                input_data=None,
                env,
                admitted_lane_root=None,
                before_run=None,
            ):
                if before_run is not None:
                    before_run()
                calls.append((list(command), dict(env)))
                return SimpleNamespace(
                    args=command,
                    returncode=1 if "has-session" in command else 0,
                    stdout="",
                    stderr="",
                )

            with (
                patch.object(controller, "assert_tmux_binary_identity"),
                patch.object(controller, "_run_raw", side_effect=fake_run_raw),
                patch.object(
                    controller,
                    "socket_identity",
                    return_value={
                        "device": 1,
                        "inode": 2,
                        "uid": os.getuid(),
                        "mode": 0o600,
                    },
                ),
                patch.object(controller, "server_identity", return_value={"pid": 10}),
                patch.object(
                    controller,
                    "metadata_for_session",
                    return_value={
                        "session": session,
                        "pane": "%1",
                        "pane_pid": 42,
                        "current_command": "echo",
                        "pane_dead": False,
                    },
                ),
            ):
                metadata = controller.launch(
                    session=session,
                    target="codex",
                    repo=repo,
                    argv=argv,
                    environment=environment,
                    admitted_lane_root=root,
                    before_start=lambda: admission.append("admitted"),
                )

            commands = [command for command, _environment in calls]
            self.assertEqual(admission, ["admitted"])
            self.assertTrue(commands)
            self.assertTrue(
                all(
                    command[:5]
                    == [
                        controller.tmux_binary.as_posix(),
                        "-f",
                        os.devnull,
                        "-S",
                        str(socket),
                    ]
                    for command in commands
                )
            )
            new_session = next(
                command for command in commands if "new-session" in command
            )
            respawn = next(command for command in commands if "respawn-pane" in command)
            self.assertEqual(new_session[5:8], ["new-session", "-d", "-E"])
            self.assertNotIn("-f", new_session[5:])
            self.assertEqual(
                new_session[new_session.index("-c") + 1], str(repo.resolve())
            )
            self.assertEqual(respawn[respawn.index("-c") + 1], str(repo.resolve()))
            self.assertEqual(respawn[-len(argv) :], argv)
            update = next(
                command
                for command in commands
                if "set-option" in command and "update-environment" in command
            )
            self.assertEqual(update[-2:], ["update-environment", ""])
            self.assertEqual(
                next(env for command, env in calls if "new-session" in command),
                environment,
            )
            self.assertTrue(
                all(
                    env == control_environment()
                    for command, env in calls
                    if "new-session" not in command
                )
            )
            flattened = "\x00".join(item for command in commands for item in command)
            self.assertNotIn(secret_value, flattened)
            self.assertNotIn(secret_value, json.dumps(metadata, sort_keys=True))

    def test_tmux_client_subprocess_and_error_surfaces_do_not_inherit_canaries(self):
        if not TmuxController.available():
            self.skipTest("tmux is unavailable")
        with tempfile.TemporaryDirectory() as temporary:
            controller = TmuxController(Path(temporary))
            calls = []
            canary_value = "private-environment-canary"

            def fake_run(command, **kwargs):
                calls.append((command, kwargs))
                if command[-1] == "-V":
                    return SimpleNamespace(
                        args=command,
                        returncode=0,
                        stdout=controller.bound_tmux_binary_identity["version"],
                        stderr="",
                    )
                return SimpleNamespace(
                    args=command,
                    returncode=1,
                    stdout=b"",
                    stderr=canary_value.encode(),
                )

            with patch.dict(
                os.environ,
                {"PUPPET_PARENT_CANARY": canary_value},
                clear=False,
            ):
                with patch("puppet_lib.tmux.subprocess.run", side_effect=fake_run):
                    result = controller._run(
                        Path(temporary) / "missing.sock",
                        ["has-session", "-t", "missing"],
                        check=False,
                    )
            self.assertEqual(result.returncode, 1)
            self.assertGreaterEqual(len(calls), 2)
            for _command, kwargs in calls:
                self.assertIn("env", kwargs)
                self.assertNotIn("PUPPET_PARENT_CANARY", kwargs["env"])

            with patch(
                "puppet_lib.tmux.subprocess.run",
                return_value=SimpleNamespace(
                    args=["tmux", "synthetic"],
                    returncode=1,
                    stdout=b"",
                    stderr=canary_value.encode(),
                ),
            ):
                with self.assertRaises(subprocess.CalledProcessError) as raised:
                    controller._run_raw(
                        ["tmux", "synthetic"],
                        env={"HOME": canary_value},
                    )
            self.assertNotIn(canary_value, str(raised.exception))
            self.assertNotIn(canary_value, raised.exception.stderr)
            self.assertNotIn(canary_value, raised.exception.output)

    def test_launch_requires_an_explicit_complete_environment(self):
        if not TmuxController.available():
            self.skipTest("tmux is unavailable")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root / "repo"
            repo.mkdir()
            controller = TmuxController(root)
            with self.assertRaises(TypeError):
                controller.launch(  # type: ignore[call-arg]
                    session="tmux-environment-required",
                    target="codex",
                    repo=repo,
                    argv=["/bin/true", "--"],
                )

    def test_singleton_tmux_argv_rejects_shell_metacharacter_path(self):
        if not TmuxController.available():
            self.skipTest("tmux is unavailable")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root / "repo"
            repo.mkdir()
            controller = TmuxController(root)
            marker = root / "must-not-exist"
            session = "tmux-singleton-shell-rejected"
            admission = []
            with self.assertRaisesRegex(ValidationError, "direct exec"):
                controller.launch(
                    session=session,
                    target="codex",
                    repo=repo,
                    argv=[f"/bin/true; touch {marker}"],
                    environment=self._launch_environment(),
                    before_start=lambda: admission.append("must-not-admit"),
                )
            self.assertEqual(admission, [])
            self.assertFalse(marker.exists())
            self.assertFalse(controller.socket_path(session).exists())

    def test_control_requires_exact_pane_and_rejects_sigint_key(self):
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
                target="codex",
                repo=repo,
                argv=["/bin/sleep", "600"],
                environment=self._launch_environment(),
            )
            socket = Path(metadata["socket"])
            try:
                initial = self._list_panes(socket=socket, session=session)
                self.assertEqual(len(initial), 1)
                with self.assertRaisesRegex(IdentityError, "process identity"):
                    controller.send_control(
                        socket=socket,
                        session=session,
                        pane=initial[0],
                        key="C-d",
                        server_identity=metadata["server_identity"],
                        expected_pane_pid=metadata["pane_pid"] + 1,
                    )
                self._tmux_run(
                    socket=socket,
                    arguments=["split-window", "-t", session, "/bin/sleep", "600"],
                )
                panes = self._list_panes(socket=socket, session=session)
                self.assertGreaterEqual(len(panes), 2)
                with self.assertRaisesRegex(IdentityError, "pane identity"):
                    controller.send_control(
                        socket=socket,
                        session=session,
                        pane="%999",
                        key="C-d",
                        expected_pane_pid=metadata["pane_pid"],
                        server_identity=metadata["server_identity"],
                    )
                with self.assertRaisesRegex(IdentityError, "unexpected pane topology"):
                    controller.metadata_for_session(
                        socket=socket,
                        session=session,
                        server_identity=metadata["server_identity"],
                    )
                with self.assertRaisesRegex(ValidationError, "allowlist"):
                    controller.send_control(
                        socket=socket,
                        session=session,
                        pane=initial[0],
                        key="C-c",
                        expected_pane_pid=metadata["pane_pid"],
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
                target="codex",
                repo=repo,
                argv=["/bin/true", "--"],
                environment=self._launch_environment(),
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
            sleeps = []
            controller = TmuxController(root, _sleep_fn=sleeps.append)
            socket = root / "sock"
            payload = b"prompt:Do the task\ntest-bytes"
            calls = []

            def fake_run(command, **kwargs):
                calls.append((command, kwargs.get("input")))
                return SimpleNamespace(
                    args=command, returncode=0, stdout=b"", stderr=b""
                )

            with patch.object(
                controller,
                "metadata",
                return_value={"pane": "%1", "pane_pid": 42, "pane_dead": False},
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
                call for call in calls if "load-buffer" in call[0] and "-b" in call[0]
            ]
            self.assertEqual(len(load_buffer_calls), 1)
            self.assertEqual(load_buffer_calls[0][1], payload)
            self.assertEqual(load_buffer_calls[0][0][-1], "-")
            self.assertNotIn("prompt:Do the task", " ".join(load_buffer_calls[0][0]))
            paste_calls = [call for call in calls if "paste-buffer" in call[0]]
            self.assertEqual(len(paste_calls), 1)
            self.assertEqual(paste_calls[0][0][-1], "%1")
            submit_calls = [call for call in calls if "send-keys" in call[0]]
            self.assertEqual(len(submit_calls), 1)
            self.assertEqual(sleeps, [SUBMIT_SETTLE_SECONDS])
            self.assertLess(calls.index(paste_calls[0]), calls.index(submit_calls[0]))
            flattened = " ".join(token for call in calls for token in call[0])
            self.assertIn("delete-buffer", flattened)

    def test_paste_bytes_rechecks_pane_after_submit_settle(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            controller = TmuxController(root, _sleep_fn=lambda _: None)
            socket = root / "sock"
            calls = []

            def fake_run(command, **kwargs):
                calls.append(command)
                return SimpleNamespace(
                    args=command, returncode=0, stdout=b"", stderr=b""
                )

            with patch.object(
                controller,
                "metadata",
                side_effect=[
                    {"pane": "%1", "pane_pid": 42, "pane_dead": False},
                    {"pane": "%1", "pane_pid": 42, "pane_dead": True},
                ],
            ):
                with patch.object(controller, "assert_tmux_binary_identity"):
                    with patch("puppet_lib.tmux.subprocess.run", side_effect=fake_run):
                        with self.assertRaisesRegex(
                            IdentityError, "changed before input submission"
                        ):
                            controller.paste_bytes(
                                socket=socket,
                                session="session-one",
                                pane="%1",
                                buffer_name="session-one-prompt",
                                payload=b"message",
                            )

            self.assertTrue(any("paste-buffer" in call for call in calls))
            self.assertFalse(any("send-keys" in call for call in calls))
            self.assertTrue(any("delete-buffer" in call for call in calls))

    def test_paste_bytes_rejects_a_different_initial_pane_process(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            controller = TmuxController(root, _sleep_fn=lambda _: None)
            with patch.object(
                controller,
                "metadata",
                return_value={"pane": "%1", "pane_pid": 43, "pane_dead": False},
            ):
                with self.assertRaisesRegex(
                    IdentityError,
                    "pane process changed before input delivery",
                ):
                    controller.paste_bytes(
                        socket=root / "sock",
                        session="session-one",
                        pane="%1",
                        buffer_name="session-one-prompt",
                        payload=b"message",
                        expected_pane_pid=42,
                    )

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

    def test_before_target_start_orders_after_options_and_consumes_returned_launch(
        self,
    ):
        if not TmuxController.available():
            self.skipTest("tmux is unavailable")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root / "repo"
            repo.mkdir()
            config_root = root / "private-codex-home"
            config_root.mkdir()
            environment = self._launch_environment(
                admitted_lane_root=root,
                CODEX_HOME=str(config_root.resolve()),
            )
            original_argv = ["/bin/sleep", "600"]
            refreshed_argv = ["/bin/echo", "refreshed-target"]
            refreshed_identity = public_launch_identity(
                repo=repo,
                argv=refreshed_argv,
                environment=environment,
                admitted_lane_root=root,
            )
            controller = TmuxController(root)
            session = "tmux-target-start-order"
            events: list[str] = []
            calls: list[tuple[list[str], dict[str, str]]] = []

            def fake_run_raw(
                command,
                *,
                check=True,
                input_data=None,
                env,
                admitted_lane_root=None,
                before_run=None,
            ):
                if before_run is not None:
                    before_run()
                operation = command[5]
                if operation == "set-option":
                    operation += ":" + command[-2]
                events.append(operation)
                calls.append((list(command), dict(env)))
                return SimpleNamespace(
                    args=command,
                    returncode=1 if command[5] == "has-session" else 0,
                    stdout="",
                    stderr="",
                )

            def refresh_target() -> TargetLaunch:
                events.append("before_target_start")
                return TargetLaunch(
                    argv=list(refreshed_argv),
                    environment=dict(environment),
                    launch_identity=dict(refreshed_identity),
                )

            with (
                patch.object(controller, "assert_tmux_binary_identity"),
                patch.object(controller, "_run_raw", side_effect=fake_run_raw),
                patch.object(
                    controller,
                    "socket_identity",
                    return_value={
                        "device": 1,
                        "inode": 2,
                        "uid": os.getuid(),
                        "mode": 0o600,
                    },
                ),
                patch.object(controller, "server_identity", return_value={"pid": 10}),
                patch.object(
                    controller,
                    "metadata_for_session",
                    return_value={
                        "session": session,
                        "pane": "%1",
                        "pane_pid": 42,
                        "current_command": "echo",
                        "pane_dead": False,
                    },
                ),
            ):
                metadata = controller.launch(
                    session=session,
                    target="codex",
                    repo=repo,
                    argv=original_argv,
                    environment=environment,
                    admitted_lane_root=root,
                    before_start=lambda: events.append("before_start"),
                    before_target_start=refresh_target,
                )

            self.assertEqual(
                events,
                [
                    "has-session",
                    "before_start",
                    "new-session",
                    "set-option:update-environment",
                    "set-option:remain-on-exit",
                    "before_target_start",
                    "respawn-pane",
                ],
            )
            respawn = next(
                command for command, _environment in calls if "respawn-pane" in command
            )
            self.assertEqual(respawn[-len(refreshed_argv) :], refreshed_argv)
            self.assertNotEqual(respawn[-len(original_argv) :], original_argv)
            self.assertEqual(metadata["launch_identity"], refreshed_identity)
            self.assertEqual(
                next(env for command, env in calls if "new-session" in command),
                environment,
            )
            self.assertEqual(
                next(env for command, env in calls if "respawn-pane" in command),
                control_environment(),
            )
            flattened = "\x00".join(item for command, _env in calls for item in command)
            self.assertNotIn(str(config_root.resolve()), flattened)

    def test_before_target_start_rejects_environment_drift_and_cleans_up(self):
        if not TmuxController.available():
            self.skipTest("tmux is unavailable")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root / "repo"
            repo.mkdir()
            initial_home = root / "initial-home"
            initial_home.mkdir()
            changed_home = root / "changed-home"
            changed_home.mkdir()
            environment = {"HOME": str(initial_home.resolve())}
            changed_environment = {"HOME": str(changed_home.resolve())}
            argv = ["/bin/sleep", "600"]
            changed_identity = public_launch_identity(
                repo=repo,
                argv=argv,
                environment=changed_environment,
            )
            controller = TmuxController(root)
            session = "tmux-target-environment-drift"
            self._assert_target_start_failure_cleans_up(
                controller=controller,
                session=session,
                repo=repo,
                argv=argv,
                environment=environment,
                before_target_start=lambda: TargetLaunch(
                    argv=list(argv),
                    environment=changed_environment,
                    launch_identity=changed_identity,
                ),
                exception=IdentityError,
                message="environment changed after server start",
            )

    def test_before_target_start_rejects_claimed_identity_drift_and_cleans_up(self):
        if not TmuxController.available():
            self.skipTest("tmux is unavailable")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root / "repo"
            repo.mkdir()
            environment = self._launch_environment()
            refreshed_argv = ["/bin/echo", "refreshed-target"]
            drifted_identity = public_launch_identity(
                repo=repo,
                argv=refreshed_argv,
                environment=environment,
            )
            drifted_identity["argv_sha256"] = "0" * 64
            controller = TmuxController(root)
            session = "tmux-target-identity-drift"
            self._assert_target_start_failure_cleans_up(
                controller=controller,
                session=session,
                repo=repo,
                argv=["/bin/sleep", "600"],
                environment=environment,
                before_target_start=lambda: TargetLaunch(
                    argv=list(refreshed_argv),
                    environment=dict(environment),
                    launch_identity=drifted_identity,
                ),
                exception=IdentityError,
                message="public launch identity changed",
            )

    def test_before_target_start_callback_failure_cleans_up_placeholder(self):
        if not TmuxController.available():
            self.skipTest("tmux is unavailable")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root / "repo"
            repo.mkdir()
            controller = TmuxController(root)
            session = "tmux-target-callback-failure"

            def fail_target_start() -> TargetLaunch:
                raise RuntimeError("injected target-start failure")

            self._assert_target_start_failure_cleans_up(
                controller=controller,
                session=session,
                repo=repo,
                argv=["/bin/sleep", "600"],
                environment=self._launch_environment(),
                before_target_start=fail_target_start,
                exception=RuntimeError,
                message="injected target-start failure",
            )

    def test_before_start_waits_for_nested_binary_and_environment_validation(self):
        if not TmuxController.available():
            self.skipTest("tmux is unavailable")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root / "repo"
            repo.mkdir()
            controller = TmuxController(root)
            admissions = []
            with patch.object(
                controller,
                "assert_tmux_binary_identity",
                side_effect=IdentityError("injected binary drift"),
            ):
                with self.assertRaisesRegex(IdentityError, "binary drift"):
                    controller._start_server(
                        socket=controller.socket_path("nested-validation"),
                        session="nested-validation",
                        repo=repo,
                        environment={},
                        admitted_lane_root=None,
                        before_start=lambda: admissions.append("binary"),
                    )
            self.assertEqual(admissions, [])

            with self.assertRaisesRegex(ValidationError, "value is invalid"):
                controller._run_raw(
                    ["/bin/true", "--"],
                    env={"HOME": "bad\nvalue"},
                    before_run=lambda: admissions.append("environment"),
                )
            self.assertEqual(admissions, [])

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

            def fake_run_raw(
                command,
                *,
                check=True,
                input_data=None,
                env,
                admitted_lane_root=None,
                before_run=None,
            ):
                nonlocal cleanup_server
                calls.append((command, check, input_data))
                operation = command[5]
                if operation == "has-session":
                    return SimpleNamespace(
                        args=command, returncode=1, stdout=b"", stderr=b""
                    )
                if operation == "new-session":
                    cleanup_server = socket_module.socket(
                        socket_module.AF_UNIX, socket_module.SOCK_STREAM
                    )
                    cleanup_server.bind(command[4])
                    os.chmod(command[4], 0o600)
                    return SimpleNamespace(
                        args=command, returncode=0, stdout=b"", stderr=b""
                    )
                if operation == "set-option":
                    return SimpleNamespace(
                        args=command, returncode=0, stdout=b"", stderr=b""
                    )
                if operation == "respawn-pane":
                    raise KeyboardInterrupt
                if operation == "kill-session":
                    return SimpleNamespace(
                        args=command, returncode=0, stdout=b"", stderr=b""
                    )
                return SimpleNamespace(
                    args=command, returncode=0, stdout=b"", stderr=b""
                )

            try:
                with patch.object(controller, "_run_raw", side_effect=fake_run_raw):
                    with self.assertRaises(KeyboardInterrupt):
                        controller.launch(
                            session=session,
                            target="codex",
                            repo=repo,
                            argv=["/bin/true", "--"],
                            environment=self._launch_environment(),
                        )
            finally:
                if cleanup_server is not None:
                    cleanup_server.close()
                controller.socket_path(session).unlink(missing_ok=True)

            self.assertTrue(
                any(
                    "kill-session" in call[0] and call[0][-1] == session
                    for call in calls
                ),
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
                        target="codex",
                        repo=repo,
                        argv=["/bin/sleep", "600"],
                        environment=self._launch_environment(),
                    )
            result = self._tmux_run(
                socket=socket,
                arguments=["has-session", "-t", session],
            )
            self.assertNotEqual(result.returncode, 0)
