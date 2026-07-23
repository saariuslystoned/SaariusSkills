from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from .errors import HerdrPuppetError


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
                "--no-focus",
            ],
            json_output=False,
        )

    def run_input(self, session: str, pane_id: str, text: str) -> Any:
        return self._run(
            ["--session", session, "pane", "run", pane_id, text],
            json_output=False,
            safe_command=[
                "--session",
                session,
                "pane",
                "run",
                pane_id,
                "<redacted-input>",
            ],
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
                timeout_seconds=max(self.timeout_seconds, timeout_ms / 1000 + 2.0),
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
                return None
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
