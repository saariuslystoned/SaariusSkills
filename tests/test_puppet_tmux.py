from __future__ import annotations

import os
import json
import shlex
import socket as socket_module
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
    select_launch_environment,
    validate_admitted_launch_plan,
)
from puppet_lib.profiles import SUBMIT_SETTLE_SECONDS  # noqa: E402
from puppet_lib.tmux import TmuxController  # noqa: E402


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
                ("grok", "GROK_HOME"),
            ):
                config_root = lane_root / (target + "-config")
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
