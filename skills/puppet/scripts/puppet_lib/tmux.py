"""Private-socket tmux transport with no terminal-reading surface."""

from __future__ import annotations

import hashlib
import os
import shlex
import shutil
import stat
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from .errors import ConflictError, IdentityError, ValidationError
from .safety import (
    absolute_root,
    canonical_tmux_socket_path,
    validate_identifier,
    validate_pane_id,
)


_PANE_FORMAT = "#{session_name}\t#{pane_id}\t#{pane_pid}\t#{pane_current_command}\t#{pane_dead}"
_PLACEHOLDER_COMMAND = ["/bin/sleep", "2147483647"]


class TmuxController:
    def __init__(self, registry_root: Path):
        self.registry_root = Path(registry_root).resolve(strict=True)
        tmux_binary = shutil.which("tmux")
        if tmux_binary is None:
            raise ValidationError("tmux executable is unavailable")
        self.tmux_binary = Path(tmux_binary).resolve()
        self.bound_tmux_binary_identity = self.binary_identity(self.tmux_binary)
        self._server_identity: Dict[str, Dict[str, Any]] = {}

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

    @staticmethod
    def _server_birth_identity(server_pid: int) -> Dict[str, str]:
        process_result = subprocess.run(
            ["ps", "-p", str(server_pid), "-o", "lstart=,comm="],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            text=True,
        )
        if process_result.returncode != 0:
            raise IdentityError("tmux process identity is unavailable")
        process_identity = process_result.stdout.strip()
        if not process_identity:
            raise IdentityError("tmux process identity is unavailable")
        return {"pid": server_pid, "birth_identity": process_identity}

    def tmux_binary_identity(self) -> Dict[str, Any]:
        return dict(self.bound_tmux_binary_identity)

    def assert_tmux_binary_identity(self, expected: Dict[str, Any]) -> None:
        observed = self.binary_identity(self.tmux_binary)
        if observed != expected:
            raise IdentityError("tmux executable identity has drifted")

    def server_identity(self, socket: Path) -> Dict[str, Any]:
        try:
            server_pid = self._run(socket, ["display-message", "-p", "#{pid}"]).stdout.strip()
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
    ) -> None:
        if socket_identity is None:
            return
        try:
            if self.socket_identity(socket) != socket_identity:
                return
        except IdentityError:
            return
        self._run_raw(
            [self.tmux_binary.as_posix(), "-S", str(socket), "kill-session", "-t", session],
            check=False,
        )

    def _run(
        self,
        socket: Path,
        arguments: List[str],
        check: bool = True,
        input_data: Optional[bytes] = None,
    ) -> subprocess.CompletedProcess:
        self.assert_tmux_binary_identity(self.bound_tmux_binary_identity)
        return self._run_raw(
            [self.tmux_binary.as_posix(), "-S", str(socket)] + arguments,
            check=check,
            input_data=input_data,
        )

    @staticmethod
    def _run_raw(
        command: List[str],
        *,
        check: bool = True,
        input_data: Optional[bytes] = None,
    ) -> subprocess.CompletedProcess:
        run_options = {
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "check": False,
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
                output=stdout,
                stderr=stderr,
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

    def launch(self, *, session: str, repo: Path, argv: List[str]) -> Dict[str, Any]:
        validate_identifier(session, "session")
        repo = absolute_root(str(repo), "repo")
        if not argv or not all(isinstance(item, str) and item for item in argv):
            raise ValidationError("launch argv must be a non-empty string list")
        socket = self.socket_path(session)
        if socket.exists() or self.exists(socket, session):
            raise ConflictError("tmux socket or session already exists")

        socket_identity: Optional[Dict[str, int]] = None
        server_identity: Optional[Dict[str, Any]] = None

        try:
            self._run(
                socket,
                [
                    "new-session",
                    "-d",
                    "-s",
                    session,
                    "-c",
                    str(repo),
                    "--",
                    *_PLACEHOLDER_COMMAND,
                ],
            )
            socket_identity = self.socket_identity(socket)
            self._run(socket, ["set-option", "-t", session, "remain-on-exit", "on"])
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
                    *argv,
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
            self._kill_session(socket=socket, session=session, socket_identity=socket_identity)
            self._server_identity.pop(str(socket), None)
            raise

        if metadata["session"] != session:
            self._kill_session(socket=socket, session=session, socket_identity=socket_identity)
            self._server_identity.pop(str(socket), None)
            raise IdentityError("tmux session initial identity is invalid")

        metadata["socket"] = str(socket)
        metadata["socket_identity"] = socket_identity
        metadata["server_identity"] = server_identity
        metadata["tmux_binary_identity"] = self.tmux_binary_identity()
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
        self._run_raw(
            [
                self.tmux_binary.as_posix(),
                "-S",
                str(socket),
                "load-buffer",
                "-b",
                buffer_name,
                "-",
            ],
            input_data=payload,
        )
        try:
            self._run(socket, ["paste-buffer", "-d", "-b", buffer_name, "-t", metadata["pane"]])
            self._run(socket, ["send-keys", "-t", metadata["pane"], "Enter"])
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

    def interrupt(
        self,
        *,
        socket: Path,
        session: str,
        pane: Optional[str] = None,
        server_identity: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.send_control(
            socket=socket,
            session=session,
            pane=pane,
            key="C-c",
            server_identity=server_identity,
        )

    def send_control(
        self,
        *,
        socket: Path,
        session: str,
        pane: Optional[str] = None,
        key: str,
        server_identity: Optional[Dict[str, Any]] = None,
    ) -> None:
        if key not in {"C-c", "C-d"}:
            raise ValidationError("control key is outside the exact halt allowlist")
        metadata = self.metadata(
            socket=socket,
            session=session,
            pane=pane,
            server_identity=server_identity,
        )
        if metadata["pane_dead"]:
            raise IdentityError("tmux pane is unavailable")
        self._run(socket, ["send-keys", "-t", metadata["pane"], key])

    def attach_command(
        self,
        *,
        socket: Path,
        session: str,
        pane: Optional[str] = None,
        server_identity: Optional[Dict[str, Any]] = None,
    ) -> str:
        self.metadata(socket=socket, session=session, pane=pane, server_identity=server_identity)
        return shlex.join(
            [
                self.tmux_binary.as_posix(),
                "-S",
                str(socket),
                "attach-session",
                "-r",
                "-t",
                session,
            ]
        )
