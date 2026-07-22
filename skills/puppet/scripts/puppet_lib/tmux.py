"""Private-socket tmux transport with no terminal-reading surface."""

from __future__ import annotations

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


class TmuxController:
    def __init__(self, registry_root: Path):
        self.registry_root = Path(registry_root).resolve(strict=True)

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

    def _run(self, socket: Path, arguments: List[str], check: bool = True, input_data: Optional[bytes] = None) -> subprocess.CompletedProcess:
        return self._run_raw(
            ["tmux", "-S", str(socket)] + arguments,
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

    def _pane_rows(self, socket: Path, session: str) -> List[Dict[str, Any]]:
        if not self.exists(socket, session):
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

    def exists(self, socket: Path, session: str) -> bool:
        validate_identifier(session, "session")
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
        try:
            self._run(
                socket,
                ["new-session", "-d", "-s", session, "-c", str(repo), "--", *argv],
            )
            self._run(socket, ["set-option", "-t", session, "remain-on-exit", "on"])
        except Exception:
            self._run(socket, ["kill-session", "-t", session], check=False)
            raise
        try:
            metadata = self.metadata_for_session(socket=socket, session=session)
        except Exception:
            self._run(socket, ["kill-session", "-t", session], check=False)
            raise
        if metadata["session"] != session or metadata["pane_dead"]:
            self._run(socket, ["kill-session", "-t", session], check=False)
            raise IdentityError("tmux session initial identity is invalid")
        metadata["socket"] = str(socket)
        metadata["socket_identity"] = self.socket_identity(socket)
        return metadata

    def metadata(self, *, socket: Path, session: str, pane: Optional[str] = None) -> Dict[str, Any]:
        validate_identifier(session, "session")
        if pane is None:
            return self.metadata_for_session(socket=socket, session=session)
        validate_pane_id(pane)
        for row in self._pane_rows(socket, session):
            if row["pane"] == pane:
                return row
        raise IdentityError("tmux pane identity is unavailable")

    def metadata_for_session(self, *, socket: Path, session: str) -> Dict[str, Any]:
        rows = self._pane_rows(socket, session)
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
    ) -> None:
        validate_identifier(session, "session")
        validate_identifier(buffer_name, "buffer name")
        validate_pane_id(pane)
        metadata = self.metadata(socket=socket, session=session, pane=pane)
        if metadata["pane_dead"]:
            raise IdentityError("tmux pane is unavailable")
        self._run_raw(
            ["tmux", "-S", str(socket), "load-buffer", "-b", buffer_name, "-"],
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
    ) -> None:
        validate_identifier(session, "session")
        validate_identifier(buffer_name, "buffer name")
        path = Path(path)
        if path.is_symlink() or not path.is_file():
            raise ValidationError("message file must be a regular non-symlink file")
        if pane is None:
            metadata = self.metadata_for_session(socket=socket, session=session)
            pane = metadata["pane"]
        self.paste_bytes(
            socket=socket,
            session=session,
            pane=pane,
            buffer_name=buffer_name,
            payload=path.read_bytes(),
        )

    def interrupt(self, *, socket: Path, session: str, pane: Optional[str] = None) -> None:
        self.send_control(socket=socket, session=session, pane=pane, key="C-c")

    def send_control(
        self,
        *,
        socket: Path,
        session: str,
        pane: Optional[str] = None,
        key: str,
    ) -> None:
        if key not in {"C-c", "C-d"}:
            raise ValidationError("control key is outside the exact halt allowlist")
        metadata = self.metadata(socket=socket, session=session, pane=pane)
        if metadata["pane_dead"]:
            raise IdentityError("tmux pane is unavailable")
        self._run(socket, ["send-keys", "-t", metadata["pane"], key])

    def attach_command(self, *, socket: Path, session: str, pane: Optional[str] = None) -> str:
        self.metadata(socket=socket, session=session, pane=pane)
        return shlex.join(
            ["tmux", "-S", str(socket), "attach-session", "-r", "-t", session]
        )
