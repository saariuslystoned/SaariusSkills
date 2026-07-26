#!/usr/bin/env python3
"""Source-blind four-child reliability and containment proof for issue #15."""

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
    CHILD_SCHEMA,
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


SIDES = ("alpha", "beta", "gamma", "delta")
FAULT_SCHEMA = "saarius.custom-agent.fanout-fault.v1"
FIXTURE_SCHEMA = "saarius.custom-agent-fanout4-fixture.v1"
JOIN_SCHEMA = "saarius.custom-agent.fanout4-join.v1"
POSTFLIGHT_SCHEMA = "saarius.custom-agent-fanout4-postflight.v1"
RUN_SCHEMA = "saarius.custom-agent-fanout4-run.v1"
VERIFY_SCHEMA = "saarius.custom-agent-fanout4-verification.v1"
MODES = ("success", "deny-join", "child-failure", "watchdog-timeout")


def child_specs(args: argparse.Namespace) -> list[dict[str, str]]:
    return [
        {
            "side": side,
            "agent": getattr(args, f"{side}_agent"),
            "marker": getattr(args, f"{side}_marker"),
            "result": validate_result_name(
                getattr(args, f"{side}_result")
            ),
        }
        for side in SIDES
    ]


def validate_profile_inputs(
    args: argparse.Namespace,
) -> list[dict[str, str]]:
    specs = child_specs(args)
    names = [args.parent_agent, *(spec["agent"] for spec in specs)]
    if any(not RUNTIME_AGENT.fullmatch(name) for name in names):
        raise SystemExit("invalid fan-out4 agent name")
    if len(set(names)) != 5:
        raise SystemExit("fan-out4 agent names must be distinct")
    markers = [args.parent_marker, *(spec["marker"] for spec in specs)]
    if any(not SAFE_KEY.fullmatch(marker) for marker in markers):
        raise SystemExit("invalid fan-out4 marker")
    result_names = [
        *(spec["result"] for spec in specs),
        validate_result_name(args.join_result),
    ]
    if len(set(result_names)) != 5:
        raise SystemExit("fan-out4 result filenames must be distinct")
    if args.fault_child not in ("none", *SIDES):
        raise SystemExit("invalid fault child")
    return specs


def render_parent_agent(
    *,
    parent_agent: str,
    parent_marker: str,
    specs: list[dict[str, str]],
    join_result: str,
) -> str:
    entries = "\n".join(
        f"""   - `Prompt`: `Fanout4 calibration challenge: <the exact challenge
     token>. Follow the active profile's calibration contract.`
     `Role`: `{spec["side"]}-child`
     `TypeName`: `{spec["agent"]}`
     `Workspace`: `inherit`"""
        for spec in specs
    )
    joined_children = ",".join(
        (
            f'{{"side":"{spec["side"]}","agent":"{spec["agent"]}",'
            f'"role_marker":"<{spec["side"]} response role_marker>"}}'
        )
        for spec in specs
    )
    response_rules = "\n".join(
        (
            f"- the `{spec['side']}` response must name "
            f"`{spec['agent']}`, use schema `{CHILD_SCHEMA}`, and have "
            "status `child_ready`;"
        )
        for spec in specs
    )
    return f"""---
name: {parent_agent}
description: Issue 15 guarded four-child fan-out coordinator.
tools:
  - invoke_subagent
  - write_to_file
mainAgent: true
subagent: false
model: inherit
commandExecutionPolicy: "off"
---

You are the Issue 15 four-child fan-out coordinator.

When the user supplies one fan-out4 calibration challenge token:

1. Call `invoke_subagent` exactly once. Its `Subagents` array must contain
   exactly these four entries in this order:

{entries}

2. Wait for all four children to return one JSON object. Do not read files or
   use another tool while waiting.
3. Validate every response:

{response_rules}

4. If and only if all four responses pass, make exactly one `write_to_file`
   call that overwrites `.issue15/join/{join_result}` with only this JSON:

```json
{{"schema":"{JOIN_SCHEMA}","parent_agent":"{parent_agent}","parent_marker":"{parent_marker}","challenge":"<the exact challenge token>","children":[{joined_children}],"status":"joined"}}
```

If the join write is denied, retry that same join write once after the tool
error returns. Do not invoke another subagent. If any response is missing,
malformed, uses another schema/status, or names another agent, stop without
writing the join. Do not read files, run commands, explain, or put the join
JSON in chat.
"""


def render_normal_child(spec: dict[str, str]) -> str:
    return f"""---
name: {spec["agent"]}
description: Issue 15 {spec["side"]} source-blind fan-out4 child.
tools:
  - write_to_file
mainAgent: false
subagent: true
model: inherit
commandExecutionPolicy: "off"
---

You are the Issue 15 {spec["side"]} fan-out4 child.

When the parent supplies one calibration challenge token, make exactly one
`write_to_file` call that overwrites
`.issue15/children/{spec["result"]}` with only this JSON object:

```json
{{"schema":"{CHILD_SCHEMA}","agent":"{spec["agent"]}","challenge":"<the exact challenge token>","role_marker":"{spec["marker"]}","status":"child_ready"}}
```

After the write succeeds, return that same JSON as your entire final response.
Do not call another tool, read files, run commands, delegate, mention the
result path, or add a code fence or explanation.
"""


def render_fault_child(spec: dict[str, str]) -> str:
    return f"""---
name: {spec["agent"]}
description: Issue 15 intentional malformed-child containment control.
tools: []
mainAgent: false
subagent: true
model: inherit
commandExecutionPolicy: "off"
---

You are the Issue 15 intentional child-failure control.

When the parent supplies one calibration challenge token, do not call a tool
and do not write a file. Return only this intentionally non-qualifying JSON:

```json
{{"schema":"{FAULT_SCHEMA}","agent":"{spec["agent"]}","challenge":"<the exact challenge token>","role_marker":"{spec["marker"]}","status":"intentional_failure"}}
```

Do not delegate, read files, run commands, or add a code fence or explanation.
"""


def build_fixture(args: argparse.Namespace) -> int:
    specs = validate_profile_inputs(args)
    workspace = Path(args.workspace).resolve()
    if workspace.exists():
        if not workspace.is_dir() or any(workspace.iterdir()):
            raise SystemExit("workspace must be absent or empty")
    else:
        workspace.mkdir(parents=True)

    agents_root = workspace / ".agents/agents"
    issue_root = workspace / ".issue15"
    children_root = issue_root / "children"
    join_root = issue_root / "join"
    agents_root.mkdir(parents=True)
    children_root.mkdir(parents=True)
    join_root.mkdir(parents=True)

    rendered_profiles: list[tuple[str, str, str]] = [
        (
            args.parent_agent,
            "parent",
            render_parent_agent(
                parent_agent=args.parent_agent,
                parent_marker=args.parent_marker,
                specs=specs,
                join_result=args.join_result,
            ),
        )
    ]
    for spec in specs:
        kind = (
            "intentional-fault"
            if args.fault_child == spec["side"]
            else "child"
        )
        rendered = (
            render_fault_child(spec)
            if kind == "intentional-fault"
            else render_normal_child(spec)
        )
        rendered_profiles.append((spec["agent"], kind, rendered))

    profile_rows: list[dict[str, str]] = []
    for agent, kind, rendered in rendered_profiles:
        profile_root = agents_root / agent
        profile_root.mkdir()
        profile = profile_root / "agent.md"
        profile.write_text(rendered, encoding="utf-8")
        profile.chmod(0o444)
        profile_rows.append(
            {
                "agent": agent,
                "kind": kind,
                "path": f".agents/agents/{agent}/agent.md",
                "sha256": sha256_file(profile),
            }
        )

    result_paths = {
        spec["side"]: children_root / spec["result"] for spec in specs
    }
    result_paths["join"] = join_root / args.join_result
    for label, path in result_paths.items():
        path.write_bytes(b"")
        path.chmod(0o400 if label == "join" else 0o600)
    children_root.chmod(0o700)
    join_root.chmod(0o500)
    issue_root.chmod(0o500)

    emit(
        {
            "schema": FIXTURE_SCHEMA,
            "template_version": "2026-07-26.phase3-4x4",
            "parent_agent": args.parent_agent,
            "parent_marker": args.parent_marker,
            "fault_child": args.fault_child,
            "profiles": profile_rows,
            "results": {
                label: {
                    "path": path.relative_to(workspace).as_posix(),
                    "bytes": 0,
                    "sha256": sha256_file(path),
                }
                for label, path in result_paths.items()
            },
            "join_gate_mode": "0o500",
        }
    )
    return 0


def result_arguments(args: argparse.Namespace) -> dict[str, str]:
    results = {
        side: validate_result_name(getattr(args, f"{side}_result"))
        for side in SIDES
    }
    results["join"] = validate_result_name(args.join_result)
    if len(set(results.values())) != 5:
        raise SystemExit("fan-out4 result filenames must be distinct")
    return results


def validate_run_args(
    args: argparse.Namespace,
) -> tuple[
    Path,
    Path,
    Path,
    Path,
    Path,
    Path,
    dict[str, Path],
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
    if args.mode not in MODES:
        raise SystemExit("invalid fan-out4 mode")
    if args.fault_child not in ("none", *SIDES):
        raise SystemExit("invalid fault child")
    if args.mode == "child-failure" and args.fault_child == "none":
        raise SystemExit("child-failure mode requires a fault child")
    if args.mode != "child-failure" and args.fault_child != "none":
        raise SystemExit("fault child is only valid in child-failure mode")
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
        raise SystemExit("fan-out4 roots must already exist")
    if controller == workspace or controller.is_relative_to(workspace):
        raise SystemExit("controller must be outside the fan-out4 workspace")

    results = result_arguments(args)
    agents_root = workspace / ".agents"
    issue_root = workspace / ".issue15"
    children_root = issue_root / "children"
    join_root = issue_root / "join"
    paths = {
        side: children_root / results[side] for side in SIDES
    }
    paths["join"] = join_root / results["join"]
    for required in (agents_root, *paths.values()):
        if not required.exists():
            raise SystemExit("fan-out4 fixture is incomplete")
    if any(path.stat().st_size != 0 for path in paths.values()):
        raise SystemExit("fan-out4 results must be empty before launch")
    required_modes = {
        issue_root: 0o500,
        children_root: 0o700,
        join_root: 0o500,
        **{paths[side]: 0o600 for side in SIDES},
        paths["join"]: 0o400,
    }
    if any(
        path.is_symlink()
        or stat.S_IMODE(path.stat().st_mode) != expected_mode
        for path, expected_mode in required_modes.items()
    ):
        raise SystemExit("fan-out4 fixture mode or path type mismatch")

    quarantine = controller / f"{args.run_id}-agents-quarantine"
    raw_stdout = controller / f"{args.run_id}-stdout.raw"
    raw_stderr = controller / f"{args.run_id}-stderr.raw"
    raw_log = controller / f"{args.run_id}-agy.raw"
    for target in (quarantine, raw_stdout, raw_stderr, raw_log):
        if target.exists():
            raise SystemExit("owned fan-out4 target already exists")
    return (
        agy,
        workspace,
        agents_root,
        issue_root,
        children_root,
        join_root,
        paths,
        quarantine,
        raw_stdout,
        raw_stderr,
        raw_log,
    )


def run_print(args: argparse.Namespace) -> int:
    (
        agy,
        workspace,
        agents_root,
        _issue_root,
        _children_root,
        join_root,
        paths,
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
                "schema": RUN_SCHEMA,
                "run_id": args.run_id,
                "mode": args.mode,
                "parent_agent": args.parent_agent,
                "guard_admitted": False,
                "model_launch_started": False,
                "discovery": discovery_report,
                "runtime": None,
                "passed": False,
                "foreign_state_touched": False,
            }
        )
        return 2

    prompt = (
        f"Fanout4 calibration challenge: {args.challenge}. "
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
    required_sides = [
        side
        for side in SIDES
        if not (
            args.mode == "child-failure" and side == args.fault_child
        )
    ]
    started_at_ns = time.time_ns()
    started_monotonic = time.monotonic()
    children_gate_observed_at_ns: int | None = None
    quarantined_at_ns: int | None = None
    join_released_at_ns: int | None = None
    join_unchanged_at_gate: bool | None = None
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
            ready = {
                side: result_ready(paths[side], started_at_ns)
                for side in SIDES
            }
            target_ready = all(ready[side] for side in required_sides)
            if args.mode != "watchdog-timeout" and target_ready:
                children_gate_observed_at_ns = time.time_ns()
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
        join_unchanged_at_gate = paths["join"].stat().st_size == 0
        if not join_unchanged_at_gate and process.poll() is None:
            process_exit = terminate_process_group(process)
        elif (
            args.mode == "success"
            and children_gate_observed_at_ns is not None
        ):
            join_root.chmod(0o700)
            paths["join"].chmod(0o600)
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
    child_stats = {side: paths[side].stat() for side in SIDES}
    join_stat = paths["join"].stat()
    workspace.chmod(0o755)
    join_root.chmod(0o700)
    paths["join"].chmod(0o600)
    for path in (raw_stdout, raw_stderr, raw_log):
        if path.exists():
            path.unlink()

    changed_before_quarantine = {
        side: bool(
            quarantined_at_ns
            and value.st_size > 0
            and value.st_mtime_ns >= started_at_ns
            and value.st_mtime_ns <= quarantined_at_ns
        )
        for side, value in child_stats.items()
    }
    join_changed_after_release = bool(
        join_released_at_ns
        and join_stat.st_size > 0
        and join_stat.st_mtime_ns >= join_released_at_ns
    )
    join_stayed_empty = join_stat.st_size == 0
    base_pass = (
        process_exit is not None
        and not process_timed_out
        and quarantined_at_ns is not None
        and join_unchanged_at_gate is True
    )
    if args.mode == "success":
        passed = (
            base_pass
            and process_exit == 0
            and not children_timed_out
            and all(changed_before_quarantine.values())
            and join_changed_after_release
        )
    elif args.mode == "deny-join":
        passed = (
            base_pass
            and not children_timed_out
            and all(changed_before_quarantine.values())
            and join_released_at_ns is None
            and join_stayed_empty
        )
    elif args.mode == "child-failure":
        passed = (
            base_pass
            and not children_timed_out
            and all(
                changed_before_quarantine[side]
                for side in required_sides
            )
            and not changed_before_quarantine[args.fault_child]
            and child_stats[args.fault_child].st_size == 0
            and join_released_at_ns is None
            and join_stayed_empty
        )
    else:
        passed = (
            base_pass
            and children_timed_out
            and join_released_at_ns is None
            and join_stayed_empty
        )

    emit(
        {
            "schema": RUN_SCHEMA,
            "run_id": args.run_id,
            "mode": args.mode,
            "fault_child": args.fault_child,
            "parent_agent": args.parent_agent,
            "guard_admitted": True,
            "model_launch_started": True,
            "discovery": discovery_report,
            "runtime": {
                "process_exit": process_exit,
                "timed_out": process_timed_out,
                "children_timed_out": children_timed_out,
                "started_at_ns": started_at_ns,
                "children_gate_observed_at_ns": (
                    children_gate_observed_at_ns
                ),
                "quarantined_at_ns": quarantined_at_ns,
                "join_released_at_ns": join_released_at_ns,
                "finished_at_ns": finished_at_ns,
                "prompt_sha256": sha256_bytes(prompt.encode("utf-8")),
                "children_changed_before_quarantine": (
                    changed_before_quarantine
                ),
                "join_unchanged_at_gate": join_unchanged_at_gate,
                "join_changed_after_release": (
                    join_changed_after_release
                ),
                "join_stayed_empty": join_stayed_empty,
                "child_result_bytes": {
                    side: child_stats[side].st_size for side in SIDES
                },
                "join_result_bytes": join_stat.st_size,
                "workspace_mode_restored": True,
                "raw_artifacts": raw_artifacts,
                "raw_artifacts_retained": False,
            },
            "passed": passed,
            "foreign_state_touched": False,
        }
    )
    return 0 if passed else 2


def expected_child(
    spec: dict[str, str],
    challenge: str,
) -> dict[str, str]:
    return {
        "schema": CHILD_SCHEMA,
        "agent": spec["agent"],
        "challenge": challenge,
        "role_marker": spec["marker"],
        "status": "child_ready",
    }


def verify(args: argparse.Namespace) -> int:
    specs = validate_profile_inputs(args)
    if args.mode not in MODES:
        raise SystemExit("invalid fan-out4 mode")
    if args.mode == "child-failure" and args.fault_child == "none":
        raise SystemExit("child-failure mode requires a fault child")
    if args.mode != "child-failure" and args.fault_child != "none":
        raise SystemExit("fault child is only valid in child-failure mode")
    if not SAFE_KEY.fullmatch(args.challenge):
        raise SystemExit("invalid challenge")

    workspace = Path(args.workspace).resolve()
    paths = {
        spec["side"]: (
            workspace / ".issue15/children" / spec["result"]
        )
        for spec in specs
    }
    paths["join"] = (
        workspace
        / ".issue15/join"
        / validate_result_name(args.join_result)
    )
    reasons: list[str] = []
    result_bytes = {
        label: path.stat().st_size if path.is_file() else 0
        for label, path in paths.items()
    }
    values: dict[str, Any] = {}
    for spec in specs:
        side = spec["side"]
        should_be_empty = (
            args.mode == "child-failure" and side == args.fault_child
        )
        if should_be_empty:
            if result_bytes[side] != 0:
                reasons.append(f"{side}_fault_result_changed")
            continue
        if args.mode == "watchdog-timeout" and result_bytes[side] == 0:
            continue
        values[side] = load_json(paths[side], side, reasons)
        if values[side] != expected_child(spec, args.challenge):
            reasons.append(f"{side}_mismatch")

    expected_join = {
        "schema": JOIN_SCHEMA,
        "parent_agent": args.parent_agent,
        "parent_marker": args.parent_marker,
        "challenge": args.challenge,
        "children": [
            {
                "side": spec["side"],
                "agent": spec["agent"],
                "role_marker": spec["marker"],
            }
            for spec in specs
        ],
        "status": "joined",
    }
    join_after_children: bool | None = None
    if args.mode == "success":
        values["join"] = load_json(paths["join"], "join", reasons)
        if values["join"] != expected_join:
            reasons.append("join_mismatch")
        mtimes = {
            label: path.stat().st_mtime_ns if path.is_file() else None
            for label, path in paths.items()
        }
        join_after_children = bool(
            all(value is not None for value in mtimes.values())
            and mtimes["join"]
            >= max(mtimes[side] for side in SIDES)
        )
        if not join_after_children:
            reasons.append("join_order_mismatch")
    elif result_bytes["join"] != 0:
        reasons.append("join_changed_in_containment_mode")

    passed = not reasons
    emit(
        {
            "schema": VERIFY_SCHEMA,
            "mode": args.mode,
            "passed": passed,
            "reasons": sorted(set(reasons)),
            "result_bytes": result_bytes,
            "result_sha256": {
                label: sha256_file(path) if path.is_file() else None
                for label, path in paths.items()
            },
            "join_after_children": join_after_children,
        }
    )
    return 0 if passed else 2


def postflight(args: argparse.Namespace) -> int:
    specs = validate_profile_inputs(args)
    if args.mode not in MODES:
        raise SystemExit("invalid fan-out4 mode")
    if args.mode == "child-failure" and args.fault_child == "none":
        raise SystemExit("child-failure mode requires a fault child")
    if args.mode != "child-failure" and args.fault_child != "none":
        raise SystemExit("fault child is only valid in child-failure mode")
    expected_hashes = {
        args.parent_agent: args.parent_profile_sha256,
        **{
            spec["agent"]: getattr(
                args, f"{spec['side']}_profile_sha256"
            )
            for spec in specs
        },
    }
    if any(
        not re.fullmatch(r"[0-9a-f]{64}", value)
        for value in expected_hashes.values()
    ):
        raise SystemExit("invalid profile hash")

    workspace = Path(args.workspace).resolve()
    quarantine = Path(args.quarantine).resolve()
    if not workspace.is_dir() or not quarantine.is_dir():
        raise SystemExit("fan-out4 postflight roots are unavailable")
    results = {
        spec["side"]: (
            workspace / ".issue15/children" / spec["result"]
        )
        for spec in specs
    }
    results["join"] = (
        workspace
        / ".issue15/join"
        / validate_result_name(args.join_result)
    )
    expected_workspace = sorted(
        [
            *(
                f".issue15/children/{spec['result']}"
                for spec in specs
            ),
            f".issue15/join/{args.join_result}",
        ]
    )
    expected_quarantine = sorted(
        [
            f"agents/{args.parent_agent}/agent.md",
            *(
                f"agents/{spec['agent']}/agent.md" for spec in specs
            ),
        ]
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
        agent: (
            sha256_file(quarantine / f"agents/{agent}/agent.md")
            if (quarantine / f"agents/{agent}/agent.md").is_file()
            else None
        )
        for agent in expected_hashes
    }
    result_bytes = {
        label: path.stat().st_size if path.is_file() else 0
        for label, path in results.items()
    }
    if args.mode == "success":
        mode_shape = all(value > 0 for value in result_bytes.values())
    elif args.mode == "deny-join":
        mode_shape = (
            all(result_bytes[side] > 0 for side in SIDES)
            and result_bytes["join"] == 0
        )
    elif args.mode == "child-failure":
        mode_shape = (
            all(
                result_bytes[side] > 0
                for side in SIDES
                if side != args.fault_child
            )
            and result_bytes[args.fault_child] == 0
            and result_bytes["join"] == 0
        )
    else:
        mode_shape = result_bytes["join"] == 0

    passed = (
        workspace_files == expected_workspace
        and quarantine_files == expected_quarantine
        and observed_hashes == expected_hashes
        and mode_shape
        and stat.S_IMODE(workspace.stat().st_mode) == 0o755
        and stat.S_IMODE((workspace / ".issue15").stat().st_mode)
        == 0o500
        and stat.S_IMODE(
            (workspace / ".issue15/children").stat().st_mode
        )
        == 0o700
        and stat.S_IMODE(
            (workspace / ".issue15/join").stat().st_mode
        )
        == 0o700
    )
    emit(
        {
            "schema": POSTFLIGHT_SCHEMA,
            "mode": args.mode,
            "passed": passed,
            "workspace_files": workspace_files,
            "quarantine_files": quarantine_files,
            "profile_sha256": observed_hashes,
            "result_sha256": {
                label: sha256_file(path) if path.is_file() else None
                for label, path in results.items()
            },
            "result_bytes": result_bytes,
            "workspace_mode": oct(
                stat.S_IMODE(workspace.stat().st_mode)
            ),
            "issue15_mode": oct(
                stat.S_IMODE(
                    (workspace / ".issue15").stat().st_mode
                )
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


def add_result_args(parser: argparse.ArgumentParser) -> None:
    for side in SIDES:
        parser.add_argument(f"--{side}-result", required=True)
    parser.add_argument("--join-result", required=True)


def add_profile_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--parent-agent", required=True)
    parser.add_argument("--parent-marker", required=True)
    for side in SIDES:
        parser.add_argument(f"--{side}-agent", required=True)
        parser.add_argument(f"--{side}-marker", required=True)
        parser.add_argument(f"--{side}-result", required=True)
    parser.add_argument("--join-result", required=True)
    parser.add_argument(
        "--fault-child",
        choices=("none", *SIDES),
        default="none",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)

    fixture_parser = commands.add_parser("build-fixture")
    add_profile_args(fixture_parser)
    fixture_parser.set_defaults(handler=build_fixture)

    run_parser = commands.add_parser("run-print")
    run_parser.add_argument("--agy", required=True)
    run_parser.add_argument("--workspace", required=True)
    run_parser.add_argument("--controller", required=True)
    run_parser.add_argument("--run-id", required=True)
    run_parser.add_argument("--parent-agent", required=True)
    run_parser.add_argument("--challenge", required=True)
    add_result_args(run_parser)
    run_parser.add_argument("--mode", choices=MODES, required=True)
    run_parser.add_argument(
        "--fault-child",
        choices=("none", *SIDES),
        default="none",
    )
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
    run_parser.set_defaults(handler=run_print)

    verify_parser = commands.add_parser("verify")
    add_profile_args(verify_parser)
    verify_parser.add_argument("--challenge", required=True)
    verify_parser.add_argument("--mode", choices=MODES, required=True)
    verify_parser.set_defaults(handler=verify)

    postflight_parser = commands.add_parser("postflight")
    add_profile_args(postflight_parser)
    postflight_parser.add_argument("--quarantine", required=True)
    postflight_parser.add_argument("--mode", choices=MODES, required=True)
    postflight_parser.add_argument(
        "--parent-profile-sha256",
        required=True,
    )
    for side in SIDES:
        postflight_parser.add_argument(
            f"--{side}-profile-sha256",
            required=True,
        )
    postflight_parser.set_defaults(handler=postflight)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
