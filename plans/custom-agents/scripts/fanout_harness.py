#!/usr/bin/env python3
"""Source-blind 2x2 custom-subagent proof helpers for issue #15."""

from __future__ import annotations

import argparse
import json
import os
import re
import signal
import stat
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from phase1_harness import (
    RUNTIME_AGENT,
    SAFE_KEY,
    bounded_discovery,
    digest_owned_file,
    emit,
    sha256_bytes,
    sha256_file,
)


CHILD_SCHEMA = "saarius.custom-agent.fanout-child.v1"
FANOUT_FIXTURE_SCHEMA = "saarius.custom-agent-fanout-fixture.v1"
FANOUT_POSTFLIGHT_SCHEMA = "saarius.custom-agent-fanout-postflight.v1"
FANOUT_RUN_SCHEMA = "saarius.custom-agent-fanout-run.v1"
FANOUT_VERIFY_SCHEMA = "saarius.custom-agent-fanout-verification.v1"
JOIN_SCHEMA = "saarius.custom-agent.fanout-join.v1"
RESULT_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{7,47}\.json$")


def validate_result_name(value: str) -> str:
    if not RESULT_NAME.fullmatch(value):
        raise SystemExit("invalid result filename")
    return value


def render_parent_agent(
    *,
    parent_agent: str,
    parent_marker: str,
    left_agent: str,
    right_agent: str,
    join_result: str,
) -> str:
    return f"""---
name: {parent_agent}
description: Issue 15 guarded two-child fan-out coordinator.
tools:
  - invoke_subagent
  - write_to_file
mainAgent: true
subagent: false
model: inherit
commandExecutionPolicy: "off"
---

You are the Issue 15 two-child fan-out coordinator.

When the user supplies one fan-out calibration challenge token:

1. Call `invoke_subagent` exactly once. Its `Subagents` array must contain
   exactly these two entries in this order:

   - `Prompt`: `Fanout calibration challenge: <the exact challenge token>.
     Follow the active profile's calibration contract.`
     `Role`: `left-child`
     `TypeName`: `{left_agent}`
     `Workspace`: `inherit`
   - `Prompt`: the same challenge-only text
     `Role`: `right-child`
     `TypeName`: `{right_agent}`
     `Workspace`: `inherit`

2. Wait for both children to return one JSON object. Do not read files or use
   another tool while waiting.
3. Require the left response to name `{left_agent}` and the right response to
   name `{right_agent}`. Extract each response's `role_marker`.
4. Make exactly one `write_to_file` call that overwrites
   `.issue15/join/{join_result}` with only this JSON object:

```json
{{"schema":"{JOIN_SCHEMA}","parent_agent":"{parent_agent}","parent_marker":"{parent_marker}","challenge":"<the exact challenge token>","left":{{"agent":"{left_agent}","role_marker":"<left response role_marker>"}},"right":{{"agent":"{right_agent}","role_marker":"<right response role_marker>"}},"status":"joined"}}
```

If the join write is temporarily denied, retry that same join write once after
the tool error returns. Do not invoke another subagent. Do not read files, run
commands, explain, or place the join JSON in chat. If either child response is
absent, malformed, or names the wrong agent, stop without writing.
"""


def render_child_agent(
    *,
    agent: str,
    side: str,
    role_marker: str,
    result_name: str,
) -> str:
    return f"""---
name: {agent}
description: Issue 15 {side} source-blind fan-out child.
tools:
  - write_to_file
mainAgent: false
subagent: true
model: inherit
commandExecutionPolicy: "off"
---

You are the Issue 15 {side} fan-out child.

When the parent supplies one fan-out calibration challenge token, make exactly
one `write_to_file` call that overwrites
`.issue15/children/{result_name}` with only this JSON object:

```json
{{"schema":"{CHILD_SCHEMA}","agent":"{agent}","challenge":"<the exact challenge token>","role_marker":"{role_marker}","status":"child_ready"}}
```

After the write succeeds, return that same JSON object as your entire final
response with no code fence or explanation. Do not call any other tool, read
files, run commands, delegate, or mention the result path in your response.
"""


def build_fanout_fixture(args: argparse.Namespace) -> int:
    agents = (args.parent_agent, args.left_agent, args.right_agent)
    if any(not RUNTIME_AGENT.fullmatch(agent) for agent in agents):
        raise SystemExit("invalid runtime agent name")
    if len(set(agents)) != 3:
        raise SystemExit("fan-out agent names must be distinct")
    markers = (args.parent_marker, args.left_marker, args.right_marker)
    if any(not SAFE_KEY.fullmatch(marker) for marker in markers):
        raise SystemExit("invalid fan-out marker")
    result_names = (
        validate_result_name(args.left_result),
        validate_result_name(args.right_result),
        validate_result_name(args.join_result),
    )
    if len(set(result_names)) != 3:
        raise SystemExit("fan-out result filenames must be distinct")

    workspace = Path(args.workspace).resolve()
    if workspace.exists():
        if not workspace.is_dir() or any(workspace.iterdir()):
            raise SystemExit("workspace must be absent or empty")
    else:
        workspace.mkdir(parents=True)

    agents_root = workspace / ".agents/agents"
    children_root = workspace / ".issue15/children"
    join_root = workspace / ".issue15/join"
    agents_root.mkdir(parents=True)
    children_root.mkdir(parents=True)
    join_root.mkdir(parents=True)

    profiles = {
        args.parent_agent: render_parent_agent(
            parent_agent=args.parent_agent,
            parent_marker=args.parent_marker,
            left_agent=args.left_agent,
            right_agent=args.right_agent,
            join_result=args.join_result,
        ),
        args.left_agent: render_child_agent(
            agent=args.left_agent,
            side="left",
            role_marker=args.left_marker,
            result_name=args.left_result,
        ),
        args.right_agent: render_child_agent(
            agent=args.right_agent,
            side="right",
            role_marker=args.right_marker,
            result_name=args.right_result,
        ),
    }
    profile_rows: list[dict[str, str]] = []
    for agent, rendered in profiles.items():
        profile_dir = agents_root / agent
        profile_dir.mkdir()
        profile = profile_dir / "agent.md"
        profile.write_text(rendered, encoding="utf-8")
        profile.chmod(0o444)
        profile_rows.append(
            {
                "agent": agent,
                "path": f".agents/agents/{agent}/agent.md",
                "sha256": sha256_file(profile),
            }
        )

    result_paths = {
        "left": children_root / args.left_result,
        "right": children_root / args.right_result,
        "join": join_root / args.join_result,
    }
    for path in result_paths.values():
        path.write_bytes(b"")
    result_paths["left"].chmod(0o600)
    result_paths["right"].chmod(0o600)
    result_paths["join"].chmod(0o400)
    children_root.chmod(0o700)
    join_root.chmod(0o500)
    (workspace / ".issue15").chmod(0o500)

    emit(
        {
            "schema": FANOUT_FIXTURE_SCHEMA,
            "template_version": "2026-07-26.phase2-2x2",
            "parent_agent": args.parent_agent,
            "parent_marker": args.parent_marker,
            "left_agent": args.left_agent,
            "left_marker": args.left_marker,
            "right_agent": args.right_agent,
            "right_marker": args.right_marker,
            "profiles": profile_rows,
            "results": {
                key: {
                    "path": path.relative_to(workspace).as_posix(),
                    "bytes": 0,
                    "sha256": sha256_file(path),
                }
                for key, path in result_paths.items()
            },
            "join_gate_mode": "0o500",
        }
    )
    return 0


def terminate_process_group(process: subprocess.Popen[bytes]) -> int:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        return process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        return process.wait(timeout=2)


def result_ready(path: Path, started_at_ns: int) -> bool:
    if not path.is_file():
        return False
    value = path.stat()
    return value.st_size > 0 and value.st_mtime_ns >= started_at_ns


def validate_run_args(
    args: argparse.Namespace,
) -> tuple[
    Path,
    Path,
    Path,
    Path,
    Path,
    Path,
    Path,
    Path,
    Path,
    Path,
    Path,
    Path,
]:
    if not RUNTIME_AGENT.fullmatch(args.parent_agent):
        raise SystemExit("invalid parent agent")
    if not SAFE_KEY.fullmatch(args.challenge):
        raise SystemExit("invalid challenge token")
    if not SAFE_KEY.fullmatch(args.run_id):
        raise SystemExit("invalid run id")
    validate_result_name(args.left_result)
    validate_result_name(args.right_result)
    validate_result_name(args.join_result)
    if len(
        {args.left_result, args.right_result, args.join_result}
    ) != 3:
        raise SystemExit("fan-out result filenames must be distinct")
    if not 1 <= args.discovery_timeout_seconds <= 30:
        raise SystemExit("discovery timeout must be between 1 and 30 seconds")
    if not 1 <= args.children_timeout_seconds <= 180:
        raise SystemExit("children timeout must be between 1 and 180 seconds")
    if not 1 <= args.timeout_seconds <= 240:
        raise SystemExit("timeout must be between 1 and 240 seconds")
    if args.children_timeout_seconds > args.timeout_seconds:
        raise SystemExit("children timeout cannot exceed total timeout")
    if not 5 <= args.poll_ms <= 1000:
        raise SystemExit("poll interval must be between 5 and 1000 ms")

    agy = Path(args.agy).resolve()
    workspace = Path(args.workspace).resolve()
    controller = Path(args.controller).resolve()
    if not agy.is_file() or not os.access(agy, os.X_OK):
        raise SystemExit("agy executable is unavailable")
    if not workspace.is_dir() or not controller.is_dir():
        raise SystemExit("fan-out roots must already exist")
    if controller == workspace or controller.is_relative_to(workspace):
        raise SystemExit("controller must be outside the fan-out workspace")

    agents_root = workspace / ".agents"
    issue_root = workspace / ".issue15"
    children_root = issue_root / "children"
    left_result = children_root / args.left_result
    right_result = children_root / args.right_result
    join_result = issue_root / "join" / args.join_result
    join_root = join_result.parent
    for required in (agents_root, left_result, right_result, join_result):
        if not required.exists():
            raise SystemExit("fan-out fixture is incomplete")
    if any(
        path.stat().st_size != 0
        for path in (left_result, right_result, join_result)
    ):
        raise SystemExit("fan-out result must be empty before launch")
    required_modes = {
        issue_root: 0o500,
        children_root: 0o700,
        join_root: 0o500,
        left_result: 0o600,
        right_result: 0o600,
        join_result: 0o400,
    }
    if any(
        path.is_symlink()
        or stat.S_IMODE(path.stat().st_mode) != expected_mode
        for path, expected_mode in required_modes.items()
    ):
        raise SystemExit("fan-out fixture mode or path type mismatch")

    quarantine = controller / f"{args.run_id}-agents-quarantine"
    raw_stdout = controller / f"{args.run_id}-stdout.raw"
    raw_stderr = controller / f"{args.run_id}-stderr.raw"
    raw_log = controller / f"{args.run_id}-agy.raw"
    for target in (quarantine, raw_stdout, raw_stderr, raw_log):
        if target.exists():
            raise SystemExit("owned fan-out target already exists")

    return (
        agy,
        workspace,
        controller,
        agents_root,
        left_result,
        right_result,
        join_result,
        join_root,
        quarantine,
        raw_stdout,
        raw_stderr,
        raw_log,
    )


def run_fanout_print(args: argparse.Namespace) -> int:
    (
        agy,
        workspace,
        _controller,
        agents_root,
        left_result,
        right_result,
        join_result,
        join_root,
        quarantine,
        raw_stdout,
        raw_stderr,
        raw_log,
    ) = validate_run_args(args)

    (
        discovery_stdout,
        discovery_stderr,
        discovery_exit,
        discovery_timed_out,
        discovery_started_at_ns,
        discovery_finished_at_ns,
    ) = bounded_discovery(
        agy=agy,
        workspace=workspace,
        timeout_seconds=args.discovery_timeout_seconds,
    )
    rendered_discovery = discovery_stdout.decode("utf-8", errors="replace")
    pattern = re.compile(
        rf"(?<![A-Za-z0-9_-]){re.escape(args.parent_agent)}"
        r"(?![A-Za-z0-9_-])"
    )
    parent_occurrences = len(pattern.findall(rendered_discovery))
    admitted = (
        discovery_exit == 0
        and not discovery_timed_out
        and parent_occurrences == 1
    )
    discovery_report = {
        "process_exit": discovery_exit,
        "timed_out": discovery_timed_out,
        "started_at_ns": discovery_started_at_ns,
        "finished_at_ns": discovery_finished_at_ns,
        "parent_exact_name_occurrences": parent_occurrences,
        "stdout": {
            "bytes": len(discovery_stdout),
            "line_count": len(rendered_discovery.splitlines()),
            "sha256": sha256_bytes(discovery_stdout),
        },
        "stderr": {
            "bytes": len(discovery_stderr),
            "sha256": sha256_bytes(discovery_stderr),
        },
        "raw_retained": False,
    }
    if not admitted:
        emit(
            {
                "schema": FANOUT_RUN_SCHEMA,
                "run_id": args.run_id,
                "parent_agent": args.parent_agent,
                "guard_admitted": False,
                "model_launch_started": False,
                "discovery": discovery_report,
                "runtime": None,
                "foreign_state_touched": False,
            }
        )
        return 2

    prompt = (
        f"Fanout calibration challenge: {args.challenge}. "
        "Follow the active profile's calibration contract."
    )
    command = [
        str(agy),
        "--add-dir",
        str(workspace),
        "--agent",
        args.parent_agent,
        "--model",
        args.model,
        "--effort",
        args.effort,
        "--mode",
        args.execution_mode,
        "--sandbox",
        "--log-file",
        str(raw_log),
        "--print-timeout",
        f"{args.timeout_seconds}s",
        "--print",
        prompt,
    ]

    started_at_ns = time.time_ns()
    started_monotonic = time.monotonic()
    children_ready_observed_at_ns: int | None = None
    quarantined_at_ns: int | None = None
    join_released_at_ns: int | None = None
    join_unchanged_at_release: bool | None = None
    children_timed_out = False
    process_timed_out = False
    process_exit: int | None = None

    with raw_stdout.open("wb") as stdout_handle, raw_stderr.open(
        "wb"
    ) as stderr_handle:
        process = subprocess.Popen(
            command,
            cwd=workspace,
            stdin=subprocess.DEVNULL,
            stdout=stdout_handle,
            stderr=stderr_handle,
            start_new_session=True,
        )
        children_deadline = (
            started_monotonic + args.children_timeout_seconds
        )
        total_deadline = started_monotonic + args.timeout_seconds + 5
        while True:
            left_ready = result_ready(left_result, started_at_ns)
            right_ready = result_ready(right_result, started_at_ns)
            if left_ready and right_ready:
                children_ready_observed_at_ns = time.time_ns()
                break
            process_exit = process.poll()
            if process_exit is not None:
                break
            if time.monotonic() >= children_deadline:
                children_timed_out = True
                process_exit = terminate_process_group(process)
                break
            if time.monotonic() >= total_deadline:
                process_timed_out = True
                process_exit = terminate_process_group(process)
                break
            time.sleep(args.poll_ms / 1000)

        if agents_root.exists():
            agents_root.rename(quarantine)
            quarantined_at_ns = time.time_ns()
        workspace.chmod(0o555)

        if children_ready_observed_at_ns is not None:
            join_unchanged_at_release = join_result.stat().st_size == 0
            if not join_unchanged_at_release and process.poll() is None:
                process_exit = terminate_process_group(process)
            elif join_unchanged_at_release:
                join_root.chmod(0o700)
                join_result.chmod(0o600)
                join_released_at_ns = time.time_ns()

        if process_exit is None:
            remaining = max(0.1, total_deadline - time.monotonic())
            try:
                process_exit = process.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                process_timed_out = True
                process_exit = terminate_process_group(process)

    finished_at_ns = time.time_ns()
    raw_artifacts = {
        "stdout": digest_owned_file(raw_stdout),
        "stderr": digest_owned_file(raw_stderr),
        "log": digest_owned_file(raw_log),
    }
    left_stat = left_result.stat()
    right_stat = right_result.stat()
    join_stat = join_result.stat()
    workspace.chmod(0o755)
    join_root.chmod(0o700)
    join_result.chmod(0o600)
    for path in (raw_stdout, raw_stderr, raw_log):
        if path.exists():
            path.unlink()

    children_changed_before_quarantine = bool(
        quarantined_at_ns
        and left_stat.st_size > 0
        and right_stat.st_size > 0
        and left_stat.st_mtime_ns <= quarantined_at_ns
        and right_stat.st_mtime_ns <= quarantined_at_ns
    )
    join_changed_after_release = bool(
        join_released_at_ns
        and join_stat.st_size > 0
        and join_stat.st_mtime_ns >= join_released_at_ns
    )
    runtime = {
        "process_exit": process_exit,
        "timed_out": process_timed_out,
        "children_timed_out": children_timed_out,
        "started_at_ns": started_at_ns,
        "children_ready_observed_at_ns": children_ready_observed_at_ns,
        "quarantined_at_ns": quarantined_at_ns,
        "join_released_at_ns": join_released_at_ns,
        "finished_at_ns": finished_at_ns,
        "prompt_sha256": sha256_bytes(prompt.encode("utf-8")),
        "children_changed_before_quarantine": children_changed_before_quarantine,
        "join_unchanged_at_release": join_unchanged_at_release,
        "join_changed_after_release": join_changed_after_release,
        "left_result_bytes": left_stat.st_size,
        "right_result_bytes": right_stat.st_size,
        "join_result_bytes": join_stat.st_size,
        "workspace_mode_restored": True,
        "raw_artifacts": raw_artifacts,
        "raw_artifacts_retained": False,
    }
    passed = (
        process_exit == 0
        and not process_timed_out
        and not children_timed_out
        and children_ready_observed_at_ns is not None
        and quarantined_at_ns is not None
        and children_changed_before_quarantine
        and join_unchanged_at_release is True
        and join_changed_after_release
    )
    emit(
        {
            "schema": FANOUT_RUN_SCHEMA,
            "run_id": args.run_id,
            "parent_agent": args.parent_agent,
            "guard_admitted": True,
            "model_launch_started": True,
            "discovery": discovery_report,
            "runtime": runtime,
            "passed": passed,
            "foreign_state_touched": False,
        }
    )
    return 0 if passed else 2


def load_json(path: Path, label: str, reasons: list[str]) -> Any:
    try:
        return json.loads(path.read_bytes())
    except OSError:
        reasons.append(f"{label}_unavailable")
        return None
    except json.JSONDecodeError:
        reasons.append(f"{label}_invalid_json")
        return None


def verify_fanout(args: argparse.Namespace) -> int:
    agents = (args.parent_agent, args.left_agent, args.right_agent)
    if any(not RUNTIME_AGENT.fullmatch(agent) for agent in agents):
        raise SystemExit("invalid fan-out agent")
    markers = (args.parent_marker, args.left_marker, args.right_marker)
    if any(not SAFE_KEY.fullmatch(marker) for marker in markers):
        raise SystemExit("invalid fan-out marker")
    if not SAFE_KEY.fullmatch(args.challenge):
        raise SystemExit("invalid challenge")

    workspace = Path(args.workspace).resolve()
    paths = {
        "left": workspace / ".issue15/children" / validate_result_name(args.left_result),
        "right": workspace / ".issue15/children" / validate_result_name(args.right_result),
        "join": workspace / ".issue15/join" / validate_result_name(args.join_result),
    }
    reasons: list[str] = []
    values = {
        label: load_json(path, label, reasons)
        for label, path in paths.items()
    }
    expected_left = {
        "schema": CHILD_SCHEMA,
        "agent": args.left_agent,
        "challenge": args.challenge,
        "role_marker": args.left_marker,
        "status": "child_ready",
    }
    expected_right = {
        "schema": CHILD_SCHEMA,
        "agent": args.right_agent,
        "challenge": args.challenge,
        "role_marker": args.right_marker,
        "status": "child_ready",
    }
    expected_join = {
        "schema": JOIN_SCHEMA,
        "parent_agent": args.parent_agent,
        "parent_marker": args.parent_marker,
        "challenge": args.challenge,
        "left": {
            "agent": args.left_agent,
            "role_marker": args.left_marker,
        },
        "right": {
            "agent": args.right_agent,
            "role_marker": args.right_marker,
        },
        "status": "joined",
    }
    for label, expected in (
        ("left", expected_left),
        ("right", expected_right),
        ("join", expected_join),
    ):
        if values[label] != expected:
            reasons.append(f"{label}_mismatch")

    mtimes = {
        label: path.stat().st_mtime_ns if path.is_file() else None
        for label, path in paths.items()
    }
    join_after_children = bool(
        all(value is not None for value in mtimes.values())
        and mtimes["join"] >= max(mtimes["left"], mtimes["right"])
    )
    if not join_after_children:
        reasons.append("join_order_mismatch")

    passed = not reasons
    emit(
        {
            "schema": FANOUT_VERIFY_SCHEMA,
            "passed": passed,
            "reasons": sorted(set(reasons)),
            "result_sha256": {
                label: sha256_file(path) if path.is_file() else None
                for label, path in paths.items()
            },
            "join_after_children": join_after_children,
        }
    )
    return 0 if passed else 2


def fanout_postflight(args: argparse.Namespace) -> int:
    agents = (args.parent_agent, args.left_agent, args.right_agent)
    if any(not RUNTIME_AGENT.fullmatch(agent) for agent in agents):
        raise SystemExit("invalid fan-out agent")
    expected_hashes = {
        args.parent_agent: args.parent_profile_sha256,
        args.left_agent: args.left_profile_sha256,
        args.right_agent: args.right_profile_sha256,
    }
    if any(
        not re.fullmatch(r"[0-9a-f]{64}", value)
        for value in expected_hashes.values()
    ):
        raise SystemExit("invalid profile hash")

    workspace = Path(args.workspace).resolve()
    quarantine = Path(args.quarantine).resolve()
    if not workspace.is_dir() or not quarantine.is_dir():
        raise SystemExit("fan-out postflight roots are unavailable")
    result_names = {
        "left": validate_result_name(args.left_result),
        "right": validate_result_name(args.right_result),
        "join": validate_result_name(args.join_result),
    }
    expected_workspace = sorted(
        [
            f".issue15/children/{result_names['left']}",
            f".issue15/children/{result_names['right']}",
            f".issue15/join/{result_names['join']}",
        ]
    )
    expected_quarantine = sorted(
        f"agents/{agent}/agent.md" for agent in agents
    )
    workspace_files = sorted(
        path.relative_to(workspace).as_posix()
        for path in workspace.rglob("*")
        if path.is_file()
    )
    quarantine_files = sorted(
        path.relative_to(quarantine).as_posix()
        for path in quarantine.rglob("*")
        if path.is_file()
    )
    observed_hashes = {
        agent: sha256_file(quarantine / f"agents/{agent}/agent.md")
        if (quarantine / f"agents/{agent}/agent.md").is_file()
        else None
        for agent in agents
    }
    results = {
        "left": workspace / f".issue15/children/{result_names['left']}",
        "right": workspace / f".issue15/children/{result_names['right']}",
        "join": workspace / f".issue15/join/{result_names['join']}",
    }
    result_hashes = {
        label: sha256_file(path) if path.is_file() else None
        for label, path in results.items()
    }
    result_bytes = {
        label: path.stat().st_size if path.is_file() else 0
        for label, path in results.items()
    }
    passed = (
        workspace_files == expected_workspace
        and quarantine_files == expected_quarantine
        and observed_hashes == expected_hashes
        and all(value > 0 for value in result_bytes.values())
        and stat.S_IMODE(workspace.stat().st_mode) == 0o755
        and stat.S_IMODE((workspace / ".issue15").stat().st_mode) == 0o500
        and stat.S_IMODE(
            (workspace / ".issue15/children").stat().st_mode
        )
        == 0o700
        and stat.S_IMODE((workspace / ".issue15/join").stat().st_mode)
        == 0o700
    )
    emit(
        {
            "schema": FANOUT_POSTFLIGHT_SCHEMA,
            "passed": passed,
            "workspace_files": workspace_files,
            "quarantine_files": quarantine_files,
            "profile_sha256": observed_hashes,
            "result_sha256": result_hashes,
            "result_bytes": result_bytes,
            "workspace_mode": oct(stat.S_IMODE(workspace.stat().st_mode)),
            "issue15_mode": oct(
                stat.S_IMODE((workspace / ".issue15").stat().st_mode)
            ),
            "children_mode": oct(
                stat.S_IMODE(
                    (workspace / ".issue15/children").stat().st_mode
                )
            ),
            "join_mode": oct(
                stat.S_IMODE(
                    (workspace / ".issue15/join").stat().st_mode
                )
            ),
            "foreign_state_touched": False,
        }
    )
    return 0 if passed else 2


def add_fixture_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--parent-agent", required=True)
    parser.add_argument("--parent-marker", required=True)
    parser.add_argument("--left-agent", required=True)
    parser.add_argument("--left-marker", required=True)
    parser.add_argument("--right-agent", required=True)
    parser.add_argument("--right-marker", required=True)
    parser.add_argument("--left-result", required=True)
    parser.add_argument("--right-result", required=True)
    parser.add_argument("--join-result", required=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)

    fixture_parser = commands.add_parser("build-fixture")
    add_fixture_arguments(fixture_parser)
    fixture_parser.set_defaults(handler=build_fanout_fixture)

    run_parser = commands.add_parser("run-print")
    run_parser.add_argument("--agy", required=True)
    run_parser.add_argument("--workspace", required=True)
    run_parser.add_argument("--controller", required=True)
    run_parser.add_argument("--run-id", required=True)
    run_parser.add_argument("--parent-agent", required=True)
    run_parser.add_argument("--challenge", required=True)
    run_parser.add_argument("--left-result", required=True)
    run_parser.add_argument("--right-result", required=True)
    run_parser.add_argument("--join-result", required=True)
    run_parser.add_argument("--model", required=True)
    run_parser.add_argument(
        "--effort", choices=("low", "medium", "high"), required=True
    )
    run_parser.add_argument(
        "--execution-mode",
        choices=("accept-edits",),
        default="accept-edits",
    )
    run_parser.add_argument(
        "--discovery-timeout-seconds",
        type=int,
        default=10,
    )
    run_parser.add_argument(
        "--children-timeout-seconds",
        type=int,
        default=90,
    )
    run_parser.add_argument("--timeout-seconds", type=int, default=180)
    run_parser.add_argument("--poll-ms", type=int, default=20)
    run_parser.set_defaults(handler=run_fanout_print)

    verify_parser = commands.add_parser("verify")
    add_fixture_arguments(verify_parser)
    verify_parser.add_argument("--challenge", required=True)
    verify_parser.set_defaults(handler=verify_fanout)

    postflight_parser = commands.add_parser("postflight")
    postflight_parser.add_argument("--workspace", required=True)
    postflight_parser.add_argument("--quarantine", required=True)
    postflight_parser.add_argument("--parent-agent", required=True)
    postflight_parser.add_argument("--left-agent", required=True)
    postflight_parser.add_argument("--right-agent", required=True)
    postflight_parser.add_argument("--left-result", required=True)
    postflight_parser.add_argument("--right-result", required=True)
    postflight_parser.add_argument("--join-result", required=True)
    postflight_parser.add_argument(
        "--parent-profile-sha256",
        required=True,
    )
    postflight_parser.add_argument(
        "--left-profile-sha256",
        required=True,
    )
    postflight_parser.add_argument(
        "--right-profile-sha256",
        required=True,
    )
    postflight_parser.set_defaults(handler=fanout_postflight)

    return parser


def main() -> int:
    args = build_parser().parse_args()
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
