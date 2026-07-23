"""Private-socket tmux transport with no terminal-reading surface."""

from __future__ import annotations

import hashlib
import os
import shlex
import shutil
import stat
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

from .errors import ConflictError, IdentityError, ValidationError
from .launch import (
    control_environment,
    public_launch_identity,
    validate_launch_environment,
    validate_public_launch_identity,
    validate_subprocess_environment,
    validate_tmux_launch_argv,
)
from .profiles import SUBMIT_SETTLE_SECONDS
from .registry import process_birth_identity
from .safety import (
    absolute_root,
    canonical_tmux_socket_path,
    validate_identifier,
    validate_pane_id,
)


_PANE_FORMAT = (
    "#{session_name}\t#{pane_id}\t#{pane_pid}\t#{pane_current_command}\t#{pane_dead}"
)
_CLIENT_FORMAT = "#{client_pid}\t#{client_tty}\t#{client_readonly}\t#{session_name}"
_PLACEHOLDER_COMMAND = ["/bin/sleep", "2147483647"]


@dataclass(frozen=True)
class TargetLaunch:
    """Fresh private target values and their exact value-free identity."""

    argv: Sequence[str] = field(repr=False)
    environment: Mapping[str, str] = field(repr=False)
    launch_identity: Mapping[str, Any] = field(repr=False)


class TmuxController:
    def __init__(self, registry_root: Path, _sleep_fn=time.sleep):
        self.registry_root = Path(registry_root).resolve(strict=True)
        tmux_binary = shutil.which("tmux")
        if tmux_binary is None:
            raise ValidationError("tmux executable is unavailable")
        self.tmux_binary = Path(tmux_binary).resolve()
        self.bound_tmux_binary_identity = self.binary_identity(self.tmux_binary)
        self._server_identity: Dict[str, Dict[str, Any]] = {}
        self._sleep_fn = _sleep_fn

    @staticmethod
    def available() -> bool:
        return shutil.which("tmux") is not None

    def socket_path(self, session: str) -> Path:
        return canonical_tmux_socket_path(self.registry_root, session)

    @staticmethod
    def socket_identity(socket: Path) -> Dict[str, int]:
        socket = Path(socket)
        if socket.is_symlink() or not socket.exists():
            raise IdentityError("tmux socket is unavailable or a symlink")
        details = socket.stat()
        if not stat.S_ISSOCK(details.st_mode):
            raise IdentityError("tmux authority path is not a socket")
        if details.st_uid != os.getuid() or details.st_mode & 0o077:
            raise IdentityError("tmux socket is not user-private")
        return {
            "device": details.st_dev,
            "inode": details.st_ino,
            "uid": details.st_uid,
            "mode": stat.S_IMODE(details.st_mode),
        }

    @staticmethod
    def binary_identity(path: Path) -> Dict[str, Any]:
        path = Path(path).resolve(strict=True)
        details = path.stat()
        if not stat.S_ISREG(details.st_mode):
            raise IdentityError("tmux executable path is not a regular file")
        if not os.access(path, os.X_OK):
            raise IdentityError("tmux executable is not executable")
        hasher = hashlib.sha256()
        with path.open("rb") as binary:
            for chunk in iter(lambda: binary.read(65536), b""):
                hasher.update(chunk)
        version_result = subprocess.run(
            [str(path), "-V"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            text=True,
            env=control_environment(),
        )
        if version_result.returncode != 0:
            raise IdentityError("unable to collect tmux executable version")
        return {
            "path": str(path),
            "device": details.st_dev,
            "inode": details.st_ino,
            "uid": details.st_uid,
            "gid": details.st_gid,
            "mode": stat.S_IMODE(details.st_mode),
            "size": details.st_size,
            "sha256": hasher.hexdigest(),
            "version": version_result.stdout.strip(),
        }

    def _server_birth_identity(self, server_pid: int) -> Dict[str, Any]:
        identity = process_birth_identity(server_pid)
        expected = self.bound_tmux_binary_identity
        if (
            Path(identity["executable_path"]).resolve(strict=True)
            != Path(expected["path"])
            or identity["device"] != expected["device"]
            or identity["inode"] != expected["inode"]
        ):
            raise IdentityError("tmux server does not execute the bound tmux binary")
        return identity

    def tmux_binary_identity(self) -> Dict[str, Any]:
        return dict(self.bound_tmux_binary_identity)

    def assert_tmux_binary_identity(self, expected: Dict[str, Any]) -> None:
        observed = self.binary_identity(self.tmux_binary)
        if observed != expected:
            raise IdentityError("tmux executable identity has drifted")

    def server_identity(self, socket: Path) -> Dict[str, Any]:
        try:
            server_pid = self._run(
                socket, ["display-message", "-p", "#{pid}"]
            ).stdout.strip()
        except subprocess.CalledProcessError as exc:
            raise IdentityError("tmux process identity is unavailable") from exc
        try:
            server_pid_int = int(server_pid)
        except ValueError as exc:
            raise IdentityError("tmux process identity is invalid") from exc
        return self._server_birth_identity(server_pid_int)

    def assert_tmux_server_identity(
        self,
        socket: Path,
        expected: Optional[Dict[str, Any]],
    ) -> None:
        if expected is None:
            return
        observed = self.server_identity(socket)
        if observed != expected:
            raise IdentityError("tmux server identity has drifted")

    def bind_server_identity(
        self,
        socket: Path,
        expected: Dict[str, Any],
    ) -> None:
        """Rebind a reconstructed controller to one recorded private server."""
        self.assert_tmux_server_identity(socket, expected)
        self._server_identity[str(socket)] = dict(expected)

    def _resolve_server_identity(
        self,
        socket: Path,
        expected: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        if expected is not None:
            return expected
        return self._server_identity.get(str(socket))

    def _verify_server_identity(
        self,
        socket: Path,
        expected: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.assert_tmux_server_identity(
            socket=socket,
            expected=self._resolve_server_identity(socket, expected),
        )

    def _kill_session(
        self,
        *,
        socket: Path,
        session: str,
        socket_identity: Optional[Dict[str, int]],
        created_by_launch: bool = False,
    ) -> None:
        if socket_identity is None:
            if not created_by_launch:
                return
            try:
                details = socket.lstat()
            except OSError:
                return
            if (
                not stat.S_ISSOCK(details.st_mode)
                or details.st_uid != os.getuid()
                or stat.S_IMODE(details.st_mode) & 0o077
            ):
                return
            socket_identity = {
                "device": details.st_dev,
                "inode": details.st_ino,
                "uid": details.st_uid,
                "mode": stat.S_IMODE(details.st_mode),
            }
        try:
            details = socket.lstat()
        except OSError:
            return
        observed = {
            "device": details.st_dev,
            "inode": details.st_ino,
            "uid": details.st_uid,
            "mode": stat.S_IMODE(details.st_mode),
        }
        if (
            not stat.S_ISSOCK(details.st_mode)
            or details.st_uid != os.getuid()
            or stat.S_IMODE(details.st_mode) & 0o077
            or observed != socket_identity
        ):
            return
        self._run_raw(
            self._tmux_command(socket, ["kill-session", "-t", session]),
            check=False,
            env=control_environment(),
        )

    def _tmux_command(self, socket: Path, arguments: List[str]) -> List[str]:
        return [
            self.tmux_binary.as_posix(),
            "-f",
            os.devnull,
            "-S",
            str(socket),
            *arguments,
        ]

    def _run(
        self,
        socket: Path,
        arguments: List[str],
        check: bool = True,
        input_data: Optional[bytes] = None,
    ) -> subprocess.CompletedProcess:
        self.assert_tmux_binary_identity(self.bound_tmux_binary_identity)
        return self._run_raw(
            self._tmux_command(socket, arguments),
            check=check,
            input_data=input_data,
            env=control_environment(),
        )

    def _start_server(
        self,
        *,
        socket: Path,
        session: str,
        repo: Path,
        environment: Mapping[str, str],
        admitted_lane_root: Path | None,
        before_start: Optional[Callable[[], None]],
    ) -> subprocess.CompletedProcess:
        def admit_after_binary_validation() -> None:
            self.assert_tmux_binary_identity(self.bound_tmux_binary_identity)
            if before_start is not None:
                before_start()

        return self._run_raw(
            self._tmux_command(
                socket,
                [
                    "new-session",
                    "-d",
                    "-E",
                    "-s",
                    session,
                    "-c",
                    str(repo),
                    "--",
                    *_PLACEHOLDER_COMMAND,
                ],
            ),
            env=environment,
            admitted_lane_root=admitted_lane_root,
            before_run=admit_after_binary_validation,
        )

    @staticmethod
    def _run_raw(
        command: List[str],
        *,
        check: bool = True,
        input_data: Optional[bytes] = None,
        env: Mapping[str, str],
        admitted_lane_root: Path | None = None,
        before_run: Optional[Callable[[], None]] = None,
    ) -> subprocess.CompletedProcess:
        closed_environment = validate_subprocess_environment(
            env,
            admitted_lane_root=admitted_lane_root,
        )
        if before_run is not None:
            before_run()
        run_options = {
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "check": False,
            "env": closed_environment,
        }
        if input_data is None:
            run_options["stdin"] = subprocess.DEVNULL
        else:
            run_options["input"] = input_data
        result = subprocess.run(command, **run_options)
        stdout = (
            result.stdout.decode("utf-8", errors="replace")
            if isinstance(result.stdout, (bytes, bytearray))
            else str(result.stdout)
        )
        stderr = (
            result.stderr.decode("utf-8", errors="replace")
            if isinstance(result.stderr, (bytes, bytearray))
            else str(result.stderr)
        )
        if check and result.returncode != 0:
            raise subprocess.CalledProcessError(
                returncode=result.returncode,
                cmd=result.args,
                output="",
                stderr="tmux client command failed",
            )
        return subprocess.CompletedProcess(
            args=result.args, returncode=result.returncode, stdout=stdout, stderr=stderr
        )

    def _pane_rows(
        self,
        socket: Path,
        session: str,
        *,
        server_identity: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        self._verify_server_identity(socket, expected=server_identity)
        if not self.exists(socket, session, server_identity=server_identity):
            raise IdentityError("registered tmux session is unavailable")
        result = self._run(socket, ["list-panes", "-t", session, "-F", _PANE_FORMAT])
        text = result.stdout.rstrip("\n")
        if not text:
            raise IdentityError("registered tmux session has no panes")
        rows = []
        for line in text.splitlines():
            parts = line.split("\t")
            if len(parts) != 5:
                raise IdentityError("tmux structural identity is ambiguous")
            try:
                pane_pid = int(parts[2])
            except ValueError as exc:
                raise IdentityError("tmux pane identity is invalid") from exc
            rows.append(
                {
                    "session": parts[0],
                    "pane": parts[1],
                    "pane_pid": pane_pid,
                    "current_command": parts[3],
                    "pane_dead": parts[4] == "1",
                }
            )
        return rows

    def exists(
        self,
        socket: Path,
        session: str,
        *,
        server_identity: Optional[Dict[str, Any]] = None,
    ) -> bool:
        validate_identifier(session, "session")
        self._verify_server_identity(socket, expected=server_identity)
        result = self._run(socket, ["has-session", "-t", session], check=False)
        return result.returncode == 0

    def launch(
        self,
        *,
        session: str,
        target: str,
        repo: Path,
        argv: List[str],
        environment: Mapping[str, str],
        admitted_lane_root: Path | None = None,
        before_start: Optional[Callable[[], None]] = None,
        before_target_start: Optional[Callable[[], TargetLaunch]] = None,
    ) -> Dict[str, Any]:
        validate_identifier(session, "session")
        repo = absolute_root(str(repo), "repo")
        argv = validate_tmux_launch_argv(argv)
        socket = self.socket_path(session)
        if socket.exists() or self.exists(socket, session):
            raise ConflictError("tmux socket or session already exists")
        launch_environment = validate_launch_environment(
            target=target,
            environment=environment,
            admitted_lane_root=admitted_lane_root,
        )
        launch_identity = public_launch_identity(
            repo=repo,
            argv=argv,
            environment=launch_environment,
            admitted_lane_root=admitted_lane_root,
        )
        socket_identity: Optional[Dict[str, int]] = None
        server_identity: Optional[Dict[str, Any]] = None

        try:
            self._start_server(
                socket=socket,
                session=session,
                repo=repo,
                environment=launch_environment,
                admitted_lane_root=admitted_lane_root,
                before_start=before_start,
            )
            socket_identity = self.socket_identity(socket)
            self._run(
                socket,
                ["set-option", "-t", session, "update-environment", ""],
            )
            self._run(
                socket,
                ["set-option", "-t", session, "remain-on-exit", "on"],
            )
            target_argv = argv
            if before_target_start is not None:
                refreshed = before_target_start()
                try:
                    refreshed_argv = refreshed.argv
                    refreshed_environment = refreshed.environment
                    refreshed_identity = refreshed.launch_identity
                except AttributeError as exc:
                    raise ValidationError(
                        "before target start result is invalid"
                    ) from exc
                target_argv = validate_tmux_launch_argv(refreshed_argv)
                target_environment = validate_launch_environment(
                    target=target,
                    environment=refreshed_environment,
                    admitted_lane_root=admitted_lane_root,
                )
                # Environment values stay out of tmux client argv.  The
                # placeholder server already owns this exact closed mapping,
                # so only a byte-for-byte equivalent refresh may be consumed.
                if target_environment != launch_environment:
                    raise IdentityError(
                        "before target start environment changed after server start"
                    )
                launch_identity = public_launch_identity(
                    repo=repo,
                    argv=target_argv,
                    environment=target_environment,
                    admitted_lane_root=admitted_lane_root,
                )
                claimed_identity = validate_public_launch_identity(
                    refreshed_identity,
                    target=target,
                )
                if claimed_identity != launch_identity:
                    raise IdentityError(
                        "before target start public launch identity changed"
                    )
            self._run(
                socket,
                [
                    "respawn-pane",
                    "-k",
                    "-t",
                    session,
                    "-c",
                    str(repo),
                    "--",
                    *target_argv,
                ],
            )
            server_identity = self.server_identity(socket)
            self._server_identity[str(socket)] = server_identity
            metadata = self.metadata_for_session(
                socket=socket,
                session=session,
                server_identity=server_identity,
            )
        except BaseException:
            self._kill_session(
                socket=socket,
                session=session,
                socket_identity=socket_identity,
                created_by_launch=True,
            )
            self._server_identity.pop(str(socket), None)
            raise

        if metadata["session"] != session:
            self._kill_session(
                socket=socket,
                session=session,
                socket_identity=socket_identity,
                created_by_launch=True,
            )
            self._server_identity.pop(str(socket), None)
            raise IdentityError("tmux session initial identity is invalid")

        metadata["socket"] = str(socket)
        metadata["socket_identity"] = socket_identity
        metadata["server_identity"] = server_identity
        metadata["tmux_binary_identity"] = self.tmux_binary_identity()
        metadata["launch_identity"] = launch_identity
        return metadata

    def metadata(
        self,
        *,
        socket: Path,
        session: str,
        pane: Optional[str] = None,
        server_identity: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        validate_identifier(session, "session")
        if pane is None:
            return self.metadata_for_session(
                socket=socket,
                session=session,
                server_identity=server_identity,
            )
        validate_pane_id(pane)
        for row in self._pane_rows(socket, session, server_identity=server_identity):
            if row["pane"] == pane:
                return row
        raise IdentityError("tmux pane identity is unavailable")

    def metadata_for_session(
        self,
        *,
        socket: Path,
        session: str,
        server_identity: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        rows = self._pane_rows(socket, session, server_identity=server_identity)
        if len(rows) != 1:
            raise IdentityError("tmux session has unexpected pane topology")
        return rows[0]

    def paste_bytes(
        self,
        *,
        socket: Path,
        session: str,
        pane: str,
        buffer_name: str,
        payload: bytes,
        server_identity: Optional[Dict[str, Any]] = None,
    ) -> None:
        validate_identifier(session, "session")
        validate_identifier(buffer_name, "buffer name")
        validate_pane_id(pane)
        metadata = self.metadata(
            socket=socket,
            session=session,
            pane=pane,
            server_identity=server_identity,
        )
        if metadata["pane_dead"]:
            raise IdentityError("tmux pane is unavailable")
        self._run(
            socket,
            ["load-buffer", "-b", buffer_name, "-"],
            input_data=payload,
        )
        try:
            self._run(
                socket,
                ["paste-buffer", "-d", "-b", buffer_name, "-t", metadata["pane"]],
            )
            self._sleep_fn(SUBMIT_SETTLE_SECONDS)
            settled = self.metadata(
                socket=socket,
                session=session,
                pane=metadata["pane"],
                server_identity=server_identity,
            )
            if (
                settled["pane"] != metadata["pane"]
                or settled["pane_pid"] != metadata["pane_pid"]
                or settled["pane_dead"]
            ):
                raise IdentityError("tmux pane changed before input submission")
            self._run(socket, ["send-keys", "-t", settled["pane"], "Enter"])
        finally:
            self._run(socket, ["delete-buffer", "-b", buffer_name], check=False)

    def paste_file(
        self,
        *,
        socket: Path,
        session: str,
        pane: Optional[str] = None,
        buffer_name: str,
        path: Path,
        server_identity: Optional[Dict[str, Any]] = None,
    ) -> None:
        validate_identifier(session, "session")
        validate_identifier(buffer_name, "buffer name")
        path = Path(path)
        if path.is_symlink() or not path.is_file():
            raise ValidationError("message file must be a regular non-symlink file")
        if pane is None:
            metadata = self.metadata_for_session(
                socket=socket,
                session=session,
                server_identity=server_identity,
            )
            pane = metadata["pane"]
        self.paste_bytes(
            socket=socket,
            session=session,
            pane=pane,
            buffer_name=buffer_name,
            server_identity=server_identity,
            payload=path.read_bytes(),
        )

    def send_control(
        self,
        *,
        socket: Path,
        session: str,
        pane: Optional[str] = None,
        key: str,
        expected_pane_pid: int,
        server_identity: Optional[Dict[str, Any]] = None,
    ) -> None:
        if key != "C-d":
            raise ValidationError("control key is outside the exact halt allowlist")
        if (
            isinstance(expected_pane_pid, bool)
            or not isinstance(expected_pane_pid, int)
            or expected_pane_pid <= 1
        ):
            raise ValidationError("expected pane process identity is invalid")
        metadata = self.metadata(
            socket=socket,
            session=session,
            pane=pane,
            server_identity=server_identity,
        )
        if metadata["pane_dead"]:
            raise IdentityError("tmux pane is unavailable")
        if metadata["pane_pid"] != expected_pane_pid:
            raise IdentityError("tmux pane process identity changed")
        self._run(socket, ["send-keys", "-t", metadata["pane"], key])

    def viewer_clients(
        self,
        *,
        socket: Path,
        session: str,
        server_identity: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Return structural client identity only; never pane content."""
        validate_identifier(session, "session")
        self._verify_server_identity(socket, expected=server_identity)
        if not self.exists(socket, session, server_identity=server_identity):
            raise IdentityError("registered tmux session is unavailable")
        result = self._run(
            socket,
            ["list-clients", "-t", session, "-F", _CLIENT_FORMAT],
            check=False,
        )
        text = result.stdout.rstrip("\n")
        if result.returncode != 0:
            if not text:
                return []
            raise IdentityError("tmux client inventory failed")
        if not text:
            return []
        clients = []
        for line in text.splitlines():
            parts = line.split("\t")
            if len(parts) != 4 or parts[2] not in {"0", "1"}:
                raise IdentityError("tmux client identity is ambiguous")
            try:
                client_pid = int(parts[0])
            except ValueError as exc:
                raise IdentityError("tmux client process identity is invalid") from exc
            if (
                client_pid <= 1
                or not parts[1].startswith("/dev/")
                or parts[3] != session
            ):
                raise IdentityError("tmux client identity is invalid")
            clients.append(
                {
                    "pid": client_pid,
                    "tty": parts[1],
                    "read_only": parts[2] == "1",
                    "session": parts[3],
                }
            )
        return clients

    def attach_argv(
        self,
        *,
        socket: Path,
        session: str,
        pane: Optional[str] = None,
        server_identity: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        self.metadata(
            socket=socket, session=session, pane=pane, server_identity=server_identity
        )
        return [
            self.tmux_binary.as_posix(),
            "-f",
            os.devnull,
            "-S",
            str(socket),
            "attach-session",
            "-r",
            "-E",
            "-t",
            session,
        ]

    def attach_command(
        self,
        *,
        socket: Path,
        session: str,
        pane: Optional[str] = None,
        server_identity: Optional[Dict[str, Any]] = None,
    ) -> str:
        return shlex.join(
            self.attach_argv(
                socket=socket,
                session=session,
                pane=pane,
                server_identity=server_identity,
            )
        )
