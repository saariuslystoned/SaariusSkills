from __future__ import annotations

import json
import os
import socket
import stat
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

from .errors import HerdrPuppetError


MAX_PROMPT_BYTES = 256 * 1024
MAX_SOCKET_RESPONSE_BYTES = 1024 * 1024


class HerdrClient:
    def __init__(self, herdr_bin: str = "herdr", timeout_seconds: float = 10.0) -> None:
        self.herdr_bin = herdr_bin
        self.timeout_seconds = timeout_seconds

    def _run(
        self,
        args: list[str],
        *,
        json_output: bool = True,
        timeout_seconds: float | None = None,
        safe_command: list[str] | None = None,
    ) -> Any:
        command = [self.herdr_bin, *args]
        error_command = safe_command if safe_command is not None else command[1:]
        command_timeout = (
            self.timeout_seconds if timeout_seconds is None else timeout_seconds
        )
        try:
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=command_timeout,
            )
        except FileNotFoundError as exc:
            raise HerdrPuppetError(
                "herdr_not_found",
                "The configured Herdr executable was not found.",
                details={"herdr_bin": self.herdr_bin},
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise HerdrPuppetError(
                "herdr_timeout",
                "Herdr did not return within the bounded timeout.",
                details={"command": error_command},
            ) from exc

        if completed.returncode != 0:
            api_error_code = None
            try:
                error_payload = json.loads(completed.stderr)
            except json.JSONDecodeError:
                error_payload = None
            if isinstance(error_payload, dict):
                error = error_payload.get("error")
                if isinstance(error, dict) and isinstance(error.get("code"), str):
                    api_error_code = error["code"]
            raise HerdrPuppetError(
                "herdr_command_failed",
                "Herdr rejected the requested operation.",
                details={
                    "command": error_command,
                    "returncode": completed.returncode,
                    "api_error_code": api_error_code,
                },
            )
        output = completed.stdout.strip()
        if not json_output:
            return output
        try:
            return json.loads(output)
        except json.JSONDecodeError as exc:
            raise HerdrPuppetError(
                "invalid_herdr_json",
                "Herdr returned malformed JSON.",
                details={"command": error_command},
            ) from exc

    def version_text(self) -> str:
        return self._run(["--version"], json_output=False)

    def server_status(self, session: str) -> dict[str, Any]:
        return self._run(["--session", session, "status", "server", "--json"])

    def sessions(self) -> list[dict[str, Any]]:
        payload = self._run(["session", "list", "--json"])
        sessions = payload.get("sessions")
        if not isinstance(sessions, list):
            raise HerdrPuppetError(
                "invalid_session_inventory",
                "Herdr session inventory is missing its sessions list.",
            )
        return sessions

    def _result_list(
        self,
        session: str,
        command: list[str],
        key: str,
    ) -> list[dict[str, Any]]:
        payload = self._run(["--session", session, *command])
        result = payload.get("result")
        values = result.get(key) if isinstance(result, dict) else None
        if not isinstance(values, list):
            raise HerdrPuppetError(
                f"invalid_{key}_inventory",
                f"Herdr {key} inventory is malformed.",
            )
        return values

    def workspaces(self, session: str) -> list[dict[str, Any]]:
        return self._result_list(session, ["workspace", "list"], "workspaces")

    def snapshot(self, session: str) -> dict[str, Any]:
        payload = self._run(["--session", session, "api", "snapshot"])
        result = payload.get("result")
        snapshot = result.get("snapshot") if isinstance(result, dict) else None
        if not isinstance(snapshot, dict):
            raise HerdrPuppetError(
                "invalid_session_snapshot",
                "Herdr session snapshot is malformed.",
            )
        for key in ("workspaces", "tabs", "panes"):
            if not isinstance(snapshot.get(key), list):
                raise HerdrPuppetError(
                    "invalid_session_snapshot",
                    f"Herdr session snapshot is missing {key}.",
                )
        return snapshot

    def tabs(self, session: str, workspace_id: str | None = None) -> list[dict[str, Any]]:
        command = ["tab", "list"]
        if workspace_id:
            command.extend(["--workspace", workspace_id])
        return self._result_list(session, command, "tabs")

    def panes(self, session: str, workspace_id: str | None = None) -> list[dict[str, Any]]:
        command = ["pane", "list"]
        if workspace_id:
            command.extend(["--workspace", workspace_id])
        return self._result_list(session, command, "panes")

    def process_info(self, session: str, pane_id: str) -> dict[str, Any]:
        payload = self._run(
            [
                "--session",
                session,
                "pane",
                "process-info",
                "--pane",
                pane_id,
            ]
        )
        result = payload.get("result")
        process_info = result.get("process_info") if isinstance(result, dict) else None
        if not isinstance(process_info, dict):
            raise HerdrPuppetError(
                "invalid_process_info",
                "Herdr pane process metadata is malformed.",
                details={"pane_id": pane_id},
            )
        return process_info

    def create_tab(self, session: str, workspace_id: str, label: str) -> Any:
        return self._run(
            [
                "--session",
                session,
                "tab",
                "create",
                "--workspace",
                workspace_id,
                "--label",
                label,
                "--focus",
            ],
            json_output=False,
        )

    def close_tab(self, session: str, tab_id: str) -> Any:
        return self._run(
            [
                "--session",
                session,
                "tab",
                "close",
                tab_id,
            ]
        )

    def wait_pid_absence(self, pid: int, timeout_seconds: float = 5.0) -> bool:
        """Return true only when no process occupies the exact leased PID.

        A reused PID remains present and therefore blocks cleanup verification.
        """
        deadline = time.monotonic() + timeout_seconds
        while True:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return True
            except PermissionError:
                pass
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.05)

    def run_command(self, session: str, pane_id: str, command: str) -> Any:
        if not isinstance(command, str):
            raise HerdrPuppetError(
                "invalid_command",
                "The shell command must be text.",
            )
        if not command.strip():
            raise HerdrPuppetError(
                "command_empty",
                "The shell command must contain non-whitespace text.",
            )
        try:
            command_bytes = command.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise HerdrPuppetError(
                "invalid_command_encoding",
                "The shell command must be valid UTF-8.",
            ) from exc
        if len(command_bytes) > MAX_PROMPT_BYTES:
            raise HerdrPuppetError(
                "command_too_large",
                "The shell command exceeds the bounded input size.",
                details={"max_prompt_bytes": MAX_PROMPT_BYTES},
            )
        if "\x00" in command:
            raise HerdrPuppetError(
                "invalid_command",
                "The shell command contains an unsupported null byte.",
            )
        args = [
            "--session",
            session,
            "pane",
            "run",
            pane_id,
            command,
        ]
        safe_command = [
            "--session",
            session,
            "pane",
            "run",
            pane_id,
            "<redacted-command>",
        ]
        try:
            return self._run(
                args,
                json_output=False,
                safe_command=safe_command,
            )
        except HerdrPuppetError as exc:
            if exc.code != "herdr_command_failed":
                raise
            details: dict[str, Any] = {"command": safe_command}
            if isinstance(exc.details.get("returncode"), int):
                details["returncode"] = exc.details["returncode"]
            raise HerdrPuppetError(
                exc.code,
                exc.message,
                details=details,
                exit_code=exc.exit_code,
            ) from exc
        except OSError as exc:
            raise HerdrPuppetError(
                "herdr_launch_failed",
                "The Herdr process could not be launched.",
                details={"command": safe_command},
            ) from exc

    def run_input(self, socket_path: str, pane_id: str, text: str) -> Any:
        if not text.strip():
            raise HerdrPuppetError(
                "prompt_empty",
                "The prompt must contain non-whitespace text.",
            )
        text_bytes = text.encode("utf-8")
        if len(text_bytes) > MAX_PROMPT_BYTES:
            raise HerdrPuppetError(
                "prompt_too_large",
                "The prompt exceeds the bounded input size.",
                details={"max_prompt_bytes": MAX_PROMPT_BYTES},
            )
        request_id = f"herdr_puppet_{uuid.uuid4().hex}"
        request = {
            "id": request_id,
            "method": "pane.send_input",
            "params": {
                "pane_id": pane_id,
                "text": text,
                "keys": ["enter"],
            },
        }
        encoded = json.dumps(
            request,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        if b"\n" in encoded:
            raise HerdrPuppetError(
                "invalid_socket_request",
                "The encoded Herdr request is not one newline-delimited frame.",
            )

        path = Path(socket_path)
        if not path.is_absolute():
            raise HerdrPuppetError(
                "invalid_herdr_socket",
                "The leased Herdr socket path must be absolute.",
            )
        try:
            socket_stat = os.lstat(path)
        except OSError as exc:
            raise HerdrPuppetError(
                "herdr_socket_unavailable",
                "The leased Herdr socket is unavailable.",
            ) from exc
        if not stat.S_ISSOCK(socket_stat.st_mode):
            raise HerdrPuppetError(
                "invalid_herdr_socket",
                "The leased Herdr socket path is not a Unix socket.",
            )
        if socket_stat.st_uid != os.geteuid():
            raise HerdrPuppetError(
                "herdr_socket_owner_mismatch",
                "The leased Herdr socket is not owned by the current user.",
            )

        dispatch_started = False
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
                connection.settimeout(self.timeout_seconds)
                connection.connect(socket_path)
                connected_stat = os.lstat(path)
                if (
                    connected_stat.st_dev != socket_stat.st_dev
                    or connected_stat.st_ino != socket_stat.st_ino
                    or not stat.S_ISSOCK(connected_stat.st_mode)
                    or connected_stat.st_uid != socket_stat.st_uid
                ):
                    raise HerdrPuppetError(
                        "herdr_socket_replaced",
                        "The leased Herdr socket changed during connection.",
                    )
                dispatch_started = True
                connection.sendall(encoded + b"\n")
                response_line = self._read_socket_line(connection)
        except HerdrPuppetError:
            raise
        except (OSError, socket.timeout) as exc:
            if dispatch_started:
                raise HerdrPuppetError(
                    "herdr_input_outcome_unknown",
                    "The Herdr input request may have been applied; reconcile "
                    "the sequence before another send.",
                ) from exc
            raise HerdrPuppetError(
                "herdr_socket_connection_failed",
                "The leased Herdr socket could not be reached.",
            ) from exc

        try:
            response = json.loads(response_line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise HerdrPuppetError(
                "herdr_input_outcome_unknown",
                "Herdr returned an invalid input response; reconcile the "
                "sequence before another send.",
            ) from exc
        if not isinstance(response, dict) or response.get("id") != request_id:
            raise HerdrPuppetError(
                "herdr_input_outcome_unknown",
                "Herdr returned a mismatched input response; reconcile the "
                "sequence before another send.",
            )
        error = response.get("error")
        if isinstance(error, dict):
            error_code = error.get("code")
            raise HerdrPuppetError(
                "herdr_input_rejected",
                "Herdr rejected the input request.",
                details={
                    "api_error_code": (
                        error_code if isinstance(error_code, str) else None
                    )
                },
            )
        result = response.get("result")
        if not isinstance(result, dict) or result.get("type") != "ok":
            raise HerdrPuppetError(
                "herdr_input_outcome_unknown",
                "Herdr returned an unexpected input response; reconcile the "
                "sequence before another send.",
            )
        return result

    @staticmethod
    def _read_socket_line(connection: socket.socket) -> bytes:
        response = bytearray()
        while True:
            chunk = connection.recv(64 * 1024)
            if not chunk:
                raise HerdrPuppetError(
                    "herdr_input_outcome_unknown",
                    "Herdr closed the socket before acknowledging input; "
                    "reconcile the sequence before another send.",
                )
            response.extend(chunk)
            newline = response.find(b"\n")
            if newline >= 0:
                if newline > MAX_SOCKET_RESPONSE_BYTES:
                    raise HerdrPuppetError(
                        "herdr_input_outcome_unknown",
                        "Herdr returned an oversized input response; reconcile "
                        "the sequence before another send.",
                    )
                return bytes(response[:newline])
            if len(response) > MAX_SOCKET_RESPONSE_BYTES:
                raise HerdrPuppetError(
                    "herdr_input_outcome_unknown",
                    "Herdr returned an oversized input response; reconcile the "
                    "sequence before another send.",
                )

    def wait_output(
        self,
        session: str,
        pane_id: str,
        match_text: str,
        lines: int,
        timeout_ms: int,
        *,
        regex: bool = False,
    ) -> dict[str, Any] | None:
        args = [
            "--session",
            session,
            "wait",
            "output",
            pane_id,
            "--match",
            match_text,
            "--source",
            "recent",
            "--lines",
            str(lines),
            "--timeout",
            str(timeout_ms),
        ]
        if regex:
            args.append("--regex")
        try:
            payload = self._run(
                args,
                timeout_seconds=self.timeout_seconds,
                safe_command=[
                    "--session",
                    session,
                    "wait",
                    "output",
                    pane_id,
                    "--match",
                    "<redacted-match>",
                ],
            )
        except HerdrPuppetError as exc:
            if exc.details.get("api_error_code") == "timeout":
                return {
                    "type": "output_timeout",
                    "timeout_source": "herdr",
                }
            if exc.code == "herdr_timeout":
                return {
                    "type": "output_timeout",
                    "timeout_source": "controller",
                }
            raise
        result = payload.get("result")
        if not isinstance(result, dict) or result.get("type") != "output_matched":
            raise HerdrPuppetError(
                "invalid_wait_output",
                "Herdr wait output returned an unexpected response.",
            )
        return result


def load_json(path: str | Path) -> dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HerdrPuppetError(
            "invalid_json_file",
            "A required JSON file could not be read.",
            details={"path": str(path)},
        ) from exc
    if not isinstance(payload, dict):
        raise HerdrPuppetError(
            "invalid_json_object",
            "The JSON file must contain an object.",
            details={"path": str(path)},
        )
    return payload
