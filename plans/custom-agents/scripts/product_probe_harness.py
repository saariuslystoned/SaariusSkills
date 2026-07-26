#!/usr/bin/env python3
"""Pixel-use read-only single-agent versus width-two product probe."""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import subprocess
import time
from pathlib import Path
from typing import Any

from fanout_harness import (
    digest_owned_file,
    load_json,
    result_ready,
    terminate_process_group,
    validate_result_name,
)
from phase1_harness import (
    RUNTIME_AGENT,
    SAFE_KEY,
    bounded_discovery,
    emit,
    sha256_bytes,
    sha256_file,
)


SINGLE_SCHEMA = "saarius.pixel-use-single-probe.v1"
POLICY_SCHEMA = "saarius.pixel-use-policy-branch.v1"
FRICTION_SCHEMA = "saarius.pixel-use-friction-branch.v1"
CUSTOM_SCHEMA = "saarius.pixel-use-custom-probe.v1"
FIXTURE_SCHEMA = "saarius.pixel-use-product-fixture.v1"
RUN_SCHEMA = "saarius.pixel-use-product-run.v1"
VERIFY_SCHEMA = "saarius.pixel-use-product-verification.v1"
POSTFLIGHT_SCHEMA = "saarius.pixel-use-product-postflight.v1"

EXPECTED_POLICY = {
    "cases": [
        {"id": "P1", "decision": "APPROVED", "receipt_type": None},
        {
            "id": "P2",
            "decision": "REQUIRES_RECEIPT",
            "receipt_type": "SCREEN_TIMEOUT_RESTORE_PLAN",
        },
        {"id": "P3", "decision": "BLOCKED", "receipt_type": None},
        {"id": "P4", "decision": "BLOCKED", "receipt_type": None},
        {"id": "P5", "decision": "APPROVED", "receipt_type": None},
        {"id": "P6", "decision": "BLOCKED", "receipt_type": None},
    ]
}

EXPECTED_FRICTION = {
    "source_event_count": 6,
    "hotspots": [
        {
            "rank": 1,
            "app_package": "com.example.beta",
            "task_stage": "search",
            "blocker_class": "target_missing",
            "event_count": 1,
            "affected_runs": 1,
            "recovered_count": 0,
            "failed_count": 1,
            "human_intervention_count": 1,
            "general_fallback_count": 0,
        },
        {
            "rank": 2,
            "app_package": "com.example.alpha",
            "task_stage": "launch",
            "blocker_class": "transport_failed",
            "event_count": 2,
            "affected_runs": 2,
            "recovered_count": 1,
            "failed_count": 1,
            "human_intervention_count": 0,
            "general_fallback_count": 1,
        },
        {
            "rank": 3,
            "app_package": "com.example.gamma",
            "task_stage": "answer",
            "blocker_class": "verification_failed",
            "event_count": 3,
            "affected_runs": 2,
            "recovered_count": 3,
            "failed_count": 0,
            "human_intervention_count": 1,
            "general_fallback_count": 2,
        },
    ],
}

POLICY_PACKET = """
Apply this committed Pixel-use PolicyCore behavior in the listed order:

1. A setting key or target id containing wifi, bluetooth, mobile_data,
   airplane, cellular, radio, dnd, notification, sms, call, email, message,
   account, security, purchase, buy, or pay is BLOCKED.
2. A type action with text is BLOCKED when targetId contains password, passwd,
   pwd, token, secret, apikey, ssn, pin, creditcard, or cvv.
3. Allowlisted setting sys.setting.dark_theme is APPROVED.
4. Allowlisted sys.setting.screen_timeout is REQUIRES_RECEIPT with receipt type
   SCREEN_TIMEOUT_RESTORE_PLAN.
5. Other settings are BLOCKED.
6. Reversible playground actions are APPROVED after rules 1-5.
7. For a real app, BACK/HOME key navigation and tab/navigation/back clicks are
   APPROVED; any other mutation is BLOCKED.

Classify in order:

P1 setting_change, real app, sys.setting.dark_theme=true
P2 setting_change, real app, sys.setting.screen_timeout=60
P3 setting_change, playground, sys.setting.wifi=true
P4 type, playground, targetId=login_password, text=sample
P5 key, real app, text=BACK
P6 click, real app, targetId=save_button, targetRole=button

Return exactly one object with exactly one key named `cases`. Its value must be
an ordered six-entry array. Every entry must contain exactly `id`, `decision`,
and `receipt_type`, in that key order. Use JSON null when no receipt applies.
Do not include reasons or any other keys.
""".strip()

FRICTION_PACKET = """
Apply this committed Pixel-use friction aggregation:

- Keep only valid events.
- Group by appPackage, taskStage, and blockerClass.
- Count events, distinct runIds, recovered/failed outcomes,
  human_intervention recoveries, and use_general_control recoveries.
- Sort by failedCount descending, then humanInterventionCount descending,
  generalFallbackCount descending, eventCount descending, appPackage,
  taskStage, and blockerClass ascending.

All six events are valid and use layer=general_control:

E1 r1 com.example.alpha launch transport_failed none failed
E2 r2 com.example.alpha launch transport_failed use_general_control recovered
E3 r3 com.example.beta search target_missing human_intervention failed
E4 r4 com.example.gamma answer verification_failed human_intervention recovered
E5 r4 com.example.gamma answer verification_failed use_general_control recovered
E6 r5 com.example.gamma answer verification_failed use_general_control recovered

Return source_event_count and ordered hotspots. Each hotspot must use these
snake_case fields: rank, app_package, task_stage, blocker_class, event_count,
affected_runs, recovered_count, failed_count, human_intervention_count,
general_fallback_count.
""".strip()


def render_single(
    *,
    agent: str,
    marker: str,
    result_name: str,
) -> str:
    return f"""---
name: {agent}
description: Pixel-use bounded single-agent product baseline.
tools:
  - write_to_file
mainAgent: true
subagent: false
model: inherit
commandExecutionPolicy: "off"
---

You are the single-agent Pixel-use product baseline.

When the user supplies one product-probe challenge, solve both packets below.

POLICY PACKET

{POLICY_PACKET}

FRICTION PACKET

{FRICTION_PACKET}

Make exactly one `write_to_file` call that overwrites
`.issue15/result/{result_name}` with one JSON object containing exactly:

- `schema`: `{SINGLE_SCHEMA}`
- `agent`: `{agent}`
- `marker`: `{marker}`
- `challenge`: the exact challenge
- `policy`: the computed policy object
- `friction`: the computed friction object
- `status`: `complete`

Then stop. Do not read files, delegate, run commands, or put the JSON in chat.
"""


def render_policy_child(
    *,
    agent: str,
    marker: str,
    result_name: str,
) -> str:
    return f"""---
name: {agent}
description: Pixel-use policy product-probe branch.
tools:
  - write_to_file
mainAgent: false
subagent: true
model: inherit
commandExecutionPolicy: "off"
---

When the parent supplies one product-probe challenge, solve this packet:

{POLICY_PACKET}

Write `.issue15/branches/{result_name}` with exactly one JSON object:

- `schema`: `{POLICY_SCHEMA}`
- `agent`: `{agent}`
- `branch_marker`: `{marker}`
- `challenge`: the exact challenge
- `policy`: the computed policy object
- `status`: `complete`

Return that same JSON as your entire final response. Do not read files, call
another tool, delegate, run commands, or add explanation.
"""


def render_friction_child(
    *,
    agent: str,
    marker: str,
    result_name: str,
) -> str:
    return f"""---
name: {agent}
description: Pixel-use friction product-probe branch.
tools:
  - write_to_file
mainAgent: false
subagent: true
model: inherit
commandExecutionPolicy: "off"
---

When the parent supplies one product-probe challenge, solve this packet:

{FRICTION_PACKET}

Write `.issue15/branches/{result_name}` with exactly one JSON object:

- `schema`: `{FRICTION_SCHEMA}`
- `agent`: `{agent}`
- `branch_marker`: `{marker}`
- `challenge`: the exact challenge
- `friction`: the computed friction object
- `status`: `complete`

Return that same JSON as your entire final response. Do not read files, call
another tool, delegate, run commands, or add explanation.
"""


def render_parent(
    *,
    agent: str,
    marker: str,
    policy_agent: str,
    friction_agent: str,
    join_result: str,
) -> str:
    return f"""---
name: {agent}
description: Pixel-use bounded width-two product coordinator.
tools:
  - invoke_subagent
  - write_to_file
mainAgent: true
subagent: false
model: inherit
commandExecutionPolicy: "off"
---

When the user supplies one product-probe challenge:

1. Call `invoke_subagent` exactly once with one two-entry `Subagents` array:
   - `Prompt`: `Product probe challenge: <exact challenge>. Follow the active
     profile contract.`
     `Role`: `policy-branch`
     `TypeName`: `{policy_agent}`
     `Workspace`: `inherit`
   - the same challenge-only `Prompt`
     `Role`: `friction-branch`
     `TypeName`: `{friction_agent}`
     `Workspace`: `inherit`
2. Require complete responses with schemas `{POLICY_SCHEMA}` and
   `{FRICTION_SCHEMA}` from the exact agents above.
3. Make one `write_to_file` call overwriting
   `.issue15/join/{join_result}` with exactly one JSON object containing:
   - `schema`: `{CUSTOM_SCHEMA}`
   - `parent_agent`: `{agent}`
   - `parent_marker`: `{marker}`
   - `challenge`: the exact challenge
   - `policy_branch`: object with the policy agent and its returned
     `branch_marker`
   - `friction_branch`: object with the friction agent and its returned
     `branch_marker`
   - `policy`: the returned policy object, unchanged
   - `friction`: the returned friction object, unchanged
   - `status`: `complete`

If the join is temporarily denied, retry the same join write once. If either
response is absent, malformed, or from another agent, stop without a join. Do
not read files, run commands, invoke another subagent, explain, or put JSON in
chat.
"""


def write_profile(root: Path, name: str, rendered: str) -> dict[str, str]:
    profile_root = root / name
    profile_root.mkdir()
    profile = profile_root / "agent.md"
    profile.write_text(rendered, encoding="utf-8")
    profile.chmod(0o444)
    return {
        "agent": name,
        "path": f".agents/agents/{name}/agent.md",
        "sha256": sha256_file(profile),
    }


def validate_names(names: list[str], markers: list[str]) -> None:
    if any(not RUNTIME_AGENT.fullmatch(name) for name in names):
        raise SystemExit("invalid product-probe agent name")
    if len(set(names)) != len(names):
        raise SystemExit("product-probe agent names must be distinct")
    if any(not SAFE_KEY.fullmatch(marker) for marker in markers):
        raise SystemExit("invalid product-probe marker")


def empty_workspace(path: str) -> Path:
    workspace = Path(path).resolve()
    if workspace.exists():
        if not workspace.is_dir() or any(workspace.iterdir()):
            raise SystemExit("workspace must be absent or empty")
    else:
        workspace.mkdir(parents=True)
    return workspace


def build_single(args: argparse.Namespace) -> int:
    validate_names([args.agent], [args.marker])
    result_name = validate_result_name(args.result)
    workspace = empty_workspace(args.workspace)
    agents_root = workspace / ".agents/agents"
    result_root = workspace / ".issue15/result"
    agents_root.mkdir(parents=True)
    result_root.mkdir(parents=True)
    profile = write_profile(
        agents_root,
        args.agent,
        render_single(
            agent=args.agent,
            marker=args.marker,
            result_name=result_name,
        ),
    )
    result = result_root / result_name
    result.write_bytes(b"")
    result.chmod(0o600)
    emit(
        {
            "schema": FIXTURE_SCHEMA,
            "arm": "single",
            "pixel_use_source_head": (
                "6474159cc15eafbd2abe602e13017a2754768ce9"
            ),
            "profiles": [profile],
            "results": {
                "single": {
                    "path": result.relative_to(workspace).as_posix(),
                    "bytes": 0,
                    "sha256": sha256_file(result),
                }
            },
        }
    )
    return 0


def build_custom(args: argparse.Namespace) -> int:
    names = [args.parent_agent, args.policy_agent, args.friction_agent]
    markers = [
        args.parent_marker,
        args.policy_marker,
        args.friction_marker,
    ]
    validate_names(names, markers)
    results = [
        validate_result_name(args.policy_result),
        validate_result_name(args.friction_result),
        validate_result_name(args.join_result),
    ]
    if len(set(results)) != 3:
        raise SystemExit("product-probe result names must be distinct")
    workspace = empty_workspace(args.workspace)
    agents_root = workspace / ".agents/agents"
    branch_root = workspace / ".issue15/branches"
    join_root = workspace / ".issue15/join"
    agents_root.mkdir(parents=True)
    branch_root.mkdir(parents=True)
    join_root.mkdir(parents=True)
    profiles = [
        write_profile(
            agents_root,
            args.parent_agent,
            render_parent(
                agent=args.parent_agent,
                marker=args.parent_marker,
                policy_agent=args.policy_agent,
                friction_agent=args.friction_agent,
                join_result=args.join_result,
            ),
        ),
        write_profile(
            agents_root,
            args.policy_agent,
            render_policy_child(
                agent=args.policy_agent,
                marker=args.policy_marker,
                result_name=args.policy_result,
            ),
        ),
        write_profile(
            agents_root,
            args.friction_agent,
            render_friction_child(
                agent=args.friction_agent,
                marker=args.friction_marker,
                result_name=args.friction_result,
            ),
        ),
    ]
    paths = {
        "policy": branch_root / args.policy_result,
        "friction": branch_root / args.friction_result,
        "join": join_root / args.join_result,
    }
    for label, path in paths.items():
        path.write_bytes(b"")
        path.chmod(0o400 if label == "join" else 0o600)
    branch_root.chmod(0o700)
    join_root.chmod(0o500)
    (workspace / ".issue15").chmod(0o500)
    emit(
        {
            "schema": FIXTURE_SCHEMA,
            "arm": "custom-width-two",
            "pixel_use_source_head": (
                "6474159cc15eafbd2abe602e13017a2754768ce9"
            ),
            "profiles": profiles,
            "results": {
                label: {
                    "path": path.relative_to(workspace).as_posix(),
                    "bytes": 0,
                    "sha256": sha256_file(path),
                }
                for label, path in paths.items()
            },
            "join_gate_mode": "0o500",
        }
    )
    return 0


def discovery_report(
    *,
    agy: Path,
    workspace: Path,
    agent: str,
    timeout_seconds: int,
) -> tuple[dict[str, Any], bool]:
    stdout, stderr, exit_code, timed_out, started, finished = (
        bounded_discovery(
            agy=agy,
            workspace=workspace,
            timeout_seconds=timeout_seconds,
        )
    )
    rendered = stdout.decode("utf-8", errors="replace")
    pattern = re.compile(
        rf"(?<![A-Za-z0-9_-]){re.escape(agent)}(?![A-Za-z0-9_-])"
    )
    occurrences = len(pattern.findall(rendered))
    report = {
        "process_exit": exit_code,
        "timed_out": timed_out,
        "started_at_ns": started,
        "finished_at_ns": finished,
        "exact_name_occurrences": occurrences,
        "stdout": {
            "bytes": len(stdout),
            "line_count": len(rendered.splitlines()),
            "sha256": sha256_bytes(stdout),
        },
        "stderr": {
            "bytes": len(stderr),
            "sha256": sha256_bytes(stderr),
        },
        "raw_retained": False,
    }
    return report, bool(
        exit_code == 0 and not timed_out and occurrences == 1
    )


def launch_command(
    args: argparse.Namespace,
    *,
    agy: Path,
    workspace: Path,
    agent: str,
    raw_log: Path,
) -> tuple[list[str], str]:
    prompt = (
        f"Product probe challenge: {args.challenge}. "
        "Follow the active profile contract."
    )
    return (
        [
            str(agy),
            "--add-dir",
            str(workspace),
            "--agent",
            agent,
            "--model",
            args.model,
            "--effort",
            args.effort,
            "--mode",
            "accept-edits",
            "--sandbox",
            "--log-file",
            str(raw_log),
            "--print-timeout",
            f"{args.timeout_seconds}s",
            "--print",
            prompt,
        ],
        prompt,
    )


def validate_common_run(
    args: argparse.Namespace,
    *,
    agent: str,
) -> tuple[Path, Path, Path, Path, Path, Path]:
    if not RUNTIME_AGENT.fullmatch(agent):
        raise SystemExit("invalid product-probe agent")
    if not SAFE_KEY.fullmatch(args.challenge):
        raise SystemExit("invalid product-probe challenge")
    if not SAFE_KEY.fullmatch(args.run_id):
        raise SystemExit("invalid product-probe run id")
    if not 1 <= args.discovery_timeout_seconds <= 30:
        raise SystemExit("invalid discovery timeout")
    if not 1 <= args.timeout_seconds <= 240:
        raise SystemExit("invalid process timeout")
    agy = Path(args.agy).resolve()
    workspace = Path(args.workspace).resolve()
    controller = Path(args.controller).resolve()
    if not agy.is_file() or not os.access(agy, os.X_OK):
        raise SystemExit("agy executable unavailable")
    if not workspace.is_dir() or not controller.is_dir():
        raise SystemExit("product-probe roots unavailable")
    if controller == workspace or controller.is_relative_to(workspace):
        raise SystemExit("controller must be outside workspace")
    if (workspace / ".agents").is_symlink():
        raise SystemExit("product-probe profile root must not be a symlink")
    quarantine = controller / f"{args.run_id}-agents-quarantine"
    raw_stdout = controller / f"{args.run_id}-stdout.raw"
    raw_stderr = controller / f"{args.run_id}-stderr.raw"
    raw_log = controller / f"{args.run_id}-agy.raw"
    for target in (quarantine, raw_stdout, raw_stderr, raw_log):
        if target.exists():
            raise SystemExit("owned product-probe target exists")
    return agy, workspace, quarantine, raw_stdout, raw_stderr, raw_log


def run_single(args: argparse.Namespace) -> int:
    (
        agy,
        workspace,
        quarantine,
        raw_stdout,
        raw_stderr,
        raw_log,
    ) = validate_common_run(args, agent=args.agent)
    result = (
        workspace
        / ".issue15/result"
        / validate_result_name(args.result)
    )
    agents_root = workspace / ".agents"
    issue_root = workspace / ".issue15"
    result_root = result.parent
    required_modes = {
        result: 0o600,
    }
    if (
        not agents_root.is_dir()
        or not issue_root.is_dir()
        or not result_root.is_dir()
        or not result.is_file()
        or result.stat().st_size != 0
    ):
        raise SystemExit("single product fixture incomplete")
    if any(
        path.is_symlink()
        or stat.S_IMODE(path.stat().st_mode) != expected_mode
        for path, expected_mode in required_modes.items()
    ):
        raise SystemExit("single product fixture mode or path type mismatch")
    report, admitted = discovery_report(
        agy=agy,
        workspace=workspace,
        agent=args.agent,
        timeout_seconds=args.discovery_timeout_seconds,
    )
    if not admitted:
        emit(
            {
                "schema": RUN_SCHEMA,
                "arm": "single",
                "guard_admitted": False,
                "model_launch_started": False,
                "discovery": report,
                "runtime": None,
                "passed": False,
                "foreign_state_touched": False,
            }
        )
        return 2
    command, prompt = launch_command(
        args,
        agy=agy,
        workspace=workspace,
        agent=args.agent,
        raw_log=raw_log,
    )
    started_at_ns = time.time_ns()
    started_monotonic = time.monotonic()
    timed_out = False
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
        time.sleep(args.quarantine_delay_ms / 1000)
        agents_root.rename(quarantine)
        quarantined_at_ns = time.time_ns()
        workspace.chmod(0o555)
        try:
            process_exit = process.wait(timeout=args.timeout_seconds + 5)
        except subprocess.TimeoutExpired:
            timed_out = True
            process_exit = terminate_process_group(process)
    finished_at_ns = time.time_ns()
    raw_artifacts = {
        "stdout": digest_owned_file(raw_stdout),
        "stderr": digest_owned_file(raw_stderr),
        "log": digest_owned_file(raw_log),
    }
    result_stat = result.stat()
    workspace.chmod(0o755)
    for path in (raw_stdout, raw_stderr, raw_log):
        if path.exists():
            path.unlink()
    changed_after_quarantine = bool(
        result_stat.st_size > 0
        and result_stat.st_mtime_ns >= quarantined_at_ns
    )
    passed = (
        process_exit == 0 and not timed_out and changed_after_quarantine
    )
    emit(
        {
            "schema": RUN_SCHEMA,
            "arm": "single",
            "run_id": args.run_id,
            "guard_admitted": True,
            "model_launch_started": True,
            "discovery": report,
            "runtime": {
                "process_exit": process_exit,
                "timed_out": timed_out,
                "started_at_ns": started_at_ns,
                "quarantined_at_ns": quarantined_at_ns,
                "finished_at_ns": finished_at_ns,
                "duration_ms": round(
                    (time.monotonic() - started_monotonic) * 1000
                ),
                "prompt_sha256": sha256_bytes(prompt.encode()),
                "result_changed_after_quarantine": (
                    changed_after_quarantine
                ),
                "result_bytes": result_stat.st_size,
                "raw_artifacts": raw_artifacts,
                "raw_artifacts_retained": False,
            },
            "passed": passed,
            "foreign_state_touched": False,
        }
    )
    return 0 if passed else 2


def run_custom(args: argparse.Namespace) -> int:
    (
        agy,
        workspace,
        quarantine,
        raw_stdout,
        raw_stderr,
        raw_log,
    ) = validate_common_run(args, agent=args.parent_agent)
    paths = {
        "policy": (
            workspace
            / ".issue15/branches"
            / validate_result_name(args.policy_result)
        ),
        "friction": (
            workspace
            / ".issue15/branches"
            / validate_result_name(args.friction_result)
        ),
        "join": (
            workspace
            / ".issue15/join"
            / validate_result_name(args.join_result)
        ),
    }
    agents_root = workspace / ".agents"
    issue_root = workspace / ".issue15"
    branch_root = paths["policy"].parent
    join_root = paths["join"].parent
    if (
        not agents_root.is_dir()
        or not issue_root.is_dir()
        or not branch_root.is_dir()
        or not join_root.is_dir()
        or any(
            not path.is_file() or path.stat().st_size
            for path in paths.values()
        )
    ):
        raise SystemExit("custom product fixture incomplete")
    required_modes = {
        issue_root: 0o500,
        branch_root: 0o700,
        join_root: 0o500,
        paths["policy"]: 0o600,
        paths["friction"]: 0o600,
        paths["join"]: 0o400,
    }
    if any(
        path.is_symlink()
        or stat.S_IMODE(path.stat().st_mode) != expected_mode
        for path, expected_mode in required_modes.items()
    ):
        raise SystemExit("custom product fixture mode or path type mismatch")
    report, admitted = discovery_report(
        agy=agy,
        workspace=workspace,
        agent=args.parent_agent,
        timeout_seconds=args.discovery_timeout_seconds,
    )
    if not admitted:
        emit(
            {
                "schema": RUN_SCHEMA,
                "arm": "custom-width-two",
                "guard_admitted": False,
                "model_launch_started": False,
                "discovery": report,
                "runtime": None,
                "passed": False,
                "foreign_state_touched": False,
            }
        )
        return 2
    command, prompt = launch_command(
        args,
        agy=agy,
        workspace=workspace,
        agent=args.parent_agent,
        raw_log=raw_log,
    )
    started_at_ns = time.time_ns()
    started_monotonic = time.monotonic()
    children_ready_at_ns: int | None = None
    timed_out = False
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
        deadline = started_monotonic + args.children_timeout_seconds
        total_deadline = started_monotonic + args.timeout_seconds + 5
        while True:
            if result_ready(
                paths["policy"], started_at_ns
            ) and result_ready(paths["friction"], started_at_ns):
                children_ready_at_ns = time.time_ns()
                break
            process_exit = process.poll()
            if process_exit is not None:
                break
            if time.monotonic() >= deadline:
                timed_out = True
                process_exit = terminate_process_group(process)
                break
            if time.monotonic() >= total_deadline:
                timed_out = True
                process_exit = terminate_process_group(process)
                break
            time.sleep(0.02)
        agents_root.rename(quarantine)
        quarantined_at_ns = time.time_ns()
        workspace.chmod(0o555)
        join_empty_at_release = paths["join"].stat().st_size == 0
        join_released_at_ns: int | None = None
        if children_ready_at_ns is not None and join_empty_at_release:
            join_root.chmod(0o700)
            paths["join"].chmod(0o600)
            join_released_at_ns = time.time_ns()
        elif process.poll() is None:
            process_exit = terminate_process_group(process)
        if process_exit is None:
            try:
                process_exit = process.wait(
                    timeout=max(0.1, total_deadline - time.monotonic())
                )
            except subprocess.TimeoutExpired:
                timed_out = True
                process_exit = terminate_process_group(process)
    finished_at_ns = time.time_ns()
    raw_artifacts = {
        "stdout": digest_owned_file(raw_stdout),
        "stderr": digest_owned_file(raw_stderr),
        "log": digest_owned_file(raw_log),
    }
    stats = {label: path.stat() for label, path in paths.items()}
    workspace.chmod(0o755)
    join_root.chmod(0o700)
    paths["join"].chmod(0o600)
    for path in (raw_stdout, raw_stderr, raw_log):
        if path.exists():
            path.unlink()
    children_before_quarantine = all(
        stats[label].st_size > 0
        and stats[label].st_mtime_ns <= quarantined_at_ns
        for label in ("policy", "friction")
    )
    join_after_release = bool(
        join_released_at_ns
        and stats["join"].st_size > 0
        and stats["join"].st_mtime_ns >= join_released_at_ns
    )
    passed = (
        process_exit == 0
        and not timed_out
        and children_ready_at_ns is not None
        and children_before_quarantine
        and join_empty_at_release
        and join_after_release
    )
    emit(
        {
            "schema": RUN_SCHEMA,
            "arm": "custom-width-two",
            "run_id": args.run_id,
            "guard_admitted": True,
            "model_launch_started": True,
            "discovery": report,
            "runtime": {
                "process_exit": process_exit,
                "timed_out": timed_out,
                "started_at_ns": started_at_ns,
                "children_ready_at_ns": children_ready_at_ns,
                "quarantined_at_ns": quarantined_at_ns,
                "join_released_at_ns": join_released_at_ns,
                "finished_at_ns": finished_at_ns,
                "duration_ms": round(
                    (time.monotonic() - started_monotonic) * 1000
                ),
                "prompt_sha256": sha256_bytes(prompt.encode()),
                "children_changed_before_quarantine": (
                    children_before_quarantine
                ),
                "join_empty_at_release": join_empty_at_release,
                "join_changed_after_release": join_after_release,
                "result_bytes": {
                    label: value.st_size for label, value in stats.items()
                },
                "raw_artifacts": raw_artifacts,
                "raw_artifacts_retained": False,
            },
            "passed": passed,
            "foreign_state_touched": False,
        }
    )
    return 0 if passed else 2


def verify_single(args: argparse.Namespace) -> int:
    validate_names([args.agent], [args.marker])
    if not SAFE_KEY.fullmatch(args.challenge):
        raise SystemExit("invalid product-probe challenge")
    path = (
        Path(args.workspace).resolve()
        / ".issue15/result"
        / validate_result_name(args.result)
    )
    reasons: list[str] = []
    value = load_json(path, "single", reasons)
    expected = {
        "schema": SINGLE_SCHEMA,
        "agent": args.agent,
        "marker": args.marker,
        "challenge": args.challenge,
        "policy": EXPECTED_POLICY,
        "friction": EXPECTED_FRICTION,
        "status": "complete",
    }
    if value != expected:
        reasons.append("single_result_mismatch")
    emit(
        {
            "schema": VERIFY_SCHEMA,
            "arm": "single",
            "passed": not reasons,
            "reasons": sorted(set(reasons)),
            "policy_exact": bool(
                isinstance(value, dict)
                and value.get("policy") == EXPECTED_POLICY
            ),
            "friction_exact": bool(
                isinstance(value, dict)
                and value.get("friction") == EXPECTED_FRICTION
            ),
            "result_sha256": sha256_file(path) if path.is_file() else None,
        }
    )
    return 0 if not reasons else 2


def verify_custom(args: argparse.Namespace) -> int:
    validate_names(
        [args.parent_agent, args.policy_agent, args.friction_agent],
        [args.parent_marker, args.policy_marker, args.friction_marker],
    )
    if not SAFE_KEY.fullmatch(args.challenge):
        raise SystemExit("invalid product-probe challenge")
    workspace = Path(args.workspace).resolve()
    paths = {
        "policy": (
            workspace
            / ".issue15/branches"
            / validate_result_name(args.policy_result)
        ),
        "friction": (
            workspace
            / ".issue15/branches"
            / validate_result_name(args.friction_result)
        ),
        "join": (
            workspace
            / ".issue15/join"
            / validate_result_name(args.join_result)
        ),
    }
    reasons: list[str] = []
    values = {
        label: load_json(path, label, reasons)
        for label, path in paths.items()
    }
    expected_policy = {
        "schema": POLICY_SCHEMA,
        "agent": args.policy_agent,
        "branch_marker": args.policy_marker,
        "challenge": args.challenge,
        "policy": EXPECTED_POLICY,
        "status": "complete",
    }
    expected_friction = {
        "schema": FRICTION_SCHEMA,
        "agent": args.friction_agent,
        "branch_marker": args.friction_marker,
        "challenge": args.challenge,
        "friction": EXPECTED_FRICTION,
        "status": "complete",
    }
    expected_join = {
        "schema": CUSTOM_SCHEMA,
        "parent_agent": args.parent_agent,
        "parent_marker": args.parent_marker,
        "challenge": args.challenge,
        "policy_branch": {
            "agent": args.policy_agent,
            "branch_marker": args.policy_marker,
        },
        "friction_branch": {
            "agent": args.friction_agent,
            "branch_marker": args.friction_marker,
        },
        "policy": EXPECTED_POLICY,
        "friction": EXPECTED_FRICTION,
        "status": "complete",
    }
    for label, expected in (
        ("policy", expected_policy),
        ("friction", expected_friction),
        ("join", expected_join),
    ):
        if values[label] != expected:
            reasons.append(f"{label}_mismatch")
    emit(
        {
            "schema": VERIFY_SCHEMA,
            "arm": "custom-width-two",
            "passed": not reasons,
            "reasons": sorted(set(reasons)),
            "policy_branch_exact": values["policy"] == expected_policy,
            "friction_branch_exact": (
                values["friction"] == expected_friction
            ),
            "join_exact": values["join"] == expected_join,
            "result_sha256": {
                label: sha256_file(path) if path.is_file() else None
                for label, path in paths.items()
            },
        }
    )
    return 0 if not reasons else 2


def postflight(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).resolve()
    quarantine = Path(args.quarantine).resolve()
    if not workspace.is_dir() or not quarantine.is_dir():
        raise SystemExit("product-probe postflight roots unavailable")
    if args.arm == "single":
        required = (
            args.agent,
            args.result,
            args.agent_profile_sha256,
        )
        if any(value is None for value in required):
            raise SystemExit("single postflight identity is incomplete")
        validate_names([args.agent], [])
        result_name = validate_result_name(args.result)
        names = [args.agent]
        hashes = {args.agent: args.agent_profile_sha256}
        results = {
            "single": workspace / ".issue15/result" / result_name,
        }
        expected_workspace = [f".issue15/result/{result_name}"]
    else:
        required = (
            args.parent_agent,
            args.policy_agent,
            args.friction_agent,
            args.policy_result,
            args.friction_result,
            args.join_result,
            args.parent_profile_sha256,
            args.policy_profile_sha256,
            args.friction_profile_sha256,
        )
        if any(value is None for value in required):
            raise SystemExit("custom postflight identity is incomplete")
        validate_names(
            [args.parent_agent, args.policy_agent, args.friction_agent],
            [],
        )
        result_names = {
            "policy": validate_result_name(args.policy_result),
            "friction": validate_result_name(args.friction_result),
            "join": validate_result_name(args.join_result),
        }
        names = [
            args.parent_agent,
            args.policy_agent,
            args.friction_agent,
        ]
        hashes = {
            args.parent_agent: args.parent_profile_sha256,
            args.policy_agent: args.policy_profile_sha256,
            args.friction_agent: args.friction_profile_sha256,
        }
        results = {
            "policy": (
                workspace
                / ".issue15/branches"
                / result_names["policy"]
            ),
            "friction": (
                workspace
                / ".issue15/branches"
                / result_names["friction"]
            ),
            "join": (
                workspace / ".issue15/join" / result_names["join"]
            ),
        }
        expected_workspace = sorted(
            [
                f".issue15/branches/{result_names['policy']}",
                f".issue15/branches/{result_names['friction']}",
                f".issue15/join/{result_names['join']}",
            ]
        )
    if any(not re.fullmatch(r"[0-9a-f]{64}", value) for value in hashes.values()):
        raise SystemExit("invalid product profile hash")
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
    expected_quarantine = sorted(
        f"agents/{name}/agent.md" for name in names
    )
    observed_hashes = {
        name: (
            sha256_file(quarantine / f"agents/{name}/agent.md")
            if (quarantine / f"agents/{name}/agent.md").is_file()
            else None
        )
        for name in names
    }
    result_bytes = {
        label: path.stat().st_size if path.is_file() else 0
        for label, path in results.items()
    }
    expected_modes = {
        workspace / ".issue15": 0o755 if args.arm == "single" else 0o500,
        (
            workspace / ".issue15/result"
            if args.arm == "single"
            else workspace / ".issue15/branches"
        ): 0o755 if args.arm == "single" else 0o700,
    }
    if args.arm == "custom":
        expected_modes[workspace / ".issue15/join"] = 0o700
    passed = (
        workspace_files == sorted(expected_workspace)
        and quarantine_files == expected_quarantine
        and observed_hashes == hashes
        and all(value > 0 for value in result_bytes.values())
        and stat.S_IMODE(workspace.stat().st_mode) == 0o755
        and all(
            path.is_dir()
            and not path.is_symlink()
            and stat.S_IMODE(path.stat().st_mode) == mode
            for path, mode in expected_modes.items()
        )
    )
    emit(
        {
            "schema": POSTFLIGHT_SCHEMA,
            "arm": args.arm,
            "passed": passed,
            "workspace_files": workspace_files,
            "quarantine_files": quarantine_files,
            "profile_sha256": observed_hashes,
            "result_bytes": result_bytes,
            "foreign_state_touched": False,
        }
    )
    return 0 if passed else 2


def add_common_run(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--agy", required=True)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--controller", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--challenge", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument(
        "--effort", choices=("low", "medium", "high"), required=True
    )
    parser.add_argument(
        "--discovery-timeout-seconds", type=int, default=10
    )
    parser.add_argument("--timeout-seconds", type=int, default=180)


def add_custom_identity(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--parent-agent", required=True)
    parser.add_argument("--parent-marker", required=True)
    parser.add_argument("--policy-agent", required=True)
    parser.add_argument("--policy-marker", required=True)
    parser.add_argument("--policy-result", required=True)
    parser.add_argument("--friction-agent", required=True)
    parser.add_argument("--friction-marker", required=True)
    parser.add_argument("--friction-result", required=True)
    parser.add_argument("--join-result", required=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)

    single_fixture = commands.add_parser("build-single")
    single_fixture.add_argument("--workspace", required=True)
    single_fixture.add_argument("--agent", required=True)
    single_fixture.add_argument("--marker", required=True)
    single_fixture.add_argument("--result", required=True)
    single_fixture.set_defaults(handler=build_single)

    custom_fixture = commands.add_parser("build-custom")
    custom_fixture.add_argument("--workspace", required=True)
    add_custom_identity(custom_fixture)
    custom_fixture.set_defaults(handler=build_custom)

    single_run = commands.add_parser("run-single")
    add_common_run(single_run)
    single_run.add_argument("--agent", required=True)
    single_run.add_argument("--result", required=True)
    single_run.add_argument(
        "--quarantine-delay-ms", type=int, default=400
    )
    single_run.set_defaults(handler=run_single)

    custom_run = commands.add_parser("run-custom")
    add_common_run(custom_run)
    custom_run.add_argument("--parent-agent", required=True)
    custom_run.add_argument("--policy-result", required=True)
    custom_run.add_argument("--friction-result", required=True)
    custom_run.add_argument("--join-result", required=True)
    custom_run.add_argument(
        "--children-timeout-seconds", type=int, default=90
    )
    custom_run.set_defaults(handler=run_custom)

    single_verify = commands.add_parser("verify-single")
    single_verify.add_argument("--workspace", required=True)
    single_verify.add_argument("--agent", required=True)
    single_verify.add_argument("--marker", required=True)
    single_verify.add_argument("--result", required=True)
    single_verify.add_argument("--challenge", required=True)
    single_verify.set_defaults(handler=verify_single)

    custom_verify = commands.add_parser("verify-custom")
    custom_verify.add_argument("--workspace", required=True)
    add_custom_identity(custom_verify)
    custom_verify.add_argument("--challenge", required=True)
    custom_verify.set_defaults(handler=verify_custom)

    post = commands.add_parser("postflight")
    post.add_argument("--arm", choices=("single", "custom"), required=True)
    post.add_argument("--workspace", required=True)
    post.add_argument("--quarantine", required=True)
    post.add_argument("--agent")
    post.add_argument("--result")
    post.add_argument("--agent-profile-sha256")
    post.add_argument("--parent-agent")
    post.add_argument("--policy-agent")
    post.add_argument("--friction-agent")
    post.add_argument("--policy-result")
    post.add_argument("--friction-result")
    post.add_argument("--join-result")
    post.add_argument("--parent-profile-sha256")
    post.add_argument("--policy-profile-sha256")
    post.add_argument("--friction-profile-sha256")
    post.set_defaults(handler=postflight)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if hasattr(args, "quarantine_delay_ms") and not (
        100 <= args.quarantine_delay_ms <= 2000
    ):
        raise SystemExit("quarantine delay must be 100-2000 ms")
    if hasattr(args, "children_timeout_seconds") and not (
        1 <= args.children_timeout_seconds <= args.timeout_seconds
    ):
        raise SystemExit("invalid children timeout")
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
