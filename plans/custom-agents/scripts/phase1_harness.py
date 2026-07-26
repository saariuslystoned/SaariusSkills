#!/usr/bin/env python3
"""Privacy-safe controller helpers for issue #15 Phase 1.

The harness never opens a transcript. It materializes inert fixtures into an
empty disposable workspace, records allowlisted hook metadata, sanitizes agent
inventory and CLI logs, and validates the bounded identity artifact.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import signal
import shutil
import stat
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


EVENT_SCHEMA = "saarius.custom-agent-event.v1"
IDENTITY_SCHEMA = "saarius.custom-agent.identity.v1"
INVENTORY_SCHEMA = "saarius.custom-agent-inventory.v1"
LOG_SCHEMA = "saarius.custom-agent-log-sanitizer.v1"
PLUGIN_INVENTORY_SCHEMA = "saarius.custom-agent-plugin-inventory.v1"
RUNTIME_FIXTURE_SCHEMA = "saarius.custom-agent-runtime-fixture.v1"
GUARDED_RUN_SCHEMA = "saarius.custom-agent-guarded-run.v1"
RUNTIME_POSTFLIGHT_SCHEMA = "saarius.custom-agent-runtime-postflight.v1"
RUNTIME_RUN_SCHEMA = "saarius.custom-agent-runtime-run.v1"
VERIFY_SCHEMA = "saarius.custom-agent-result-verification.v1"
ALLOWED_EVENTS = {"PreInvocation", "PreToolUse", "PostToolUse", "Stop"}
ALLOWED_TERMINATIONS = {
    "model_stop",
    "max_steps_exceeded",
    "error",
    "interrupted",
    "timeout",
}
SAFE_KEY = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
RUNTIME_AGENT = re.compile(r"^saarius-i15-[a-z0-9-]{8,48}$")
RUNTIME_ROLES = {
    "reconnaissance",
    "implementation",
    "verification",
    "proof",
}


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def emit(value: Any) -> None:
    json.dump(value, sys.stdout, sort_keys=True, separators=(",", ":"))
    sys.stdout.write("\n")


def load_manifest(path: Path | None = None) -> dict[str, Any]:
    target = path or repo_root() / "fixtures/custom-agents/phase1/manifest.json"
    value = json.loads(target.read_text(encoding="utf-8"))
    if value.get("schema") != "saarius.custom-agent-fixtures.v1":
        raise ValueError("unsupported fixture manifest")
    agents = value.get("agents")
    if not isinstance(agents, list) or len(agents) != 4:
        raise ValueError("fixture manifest must name exactly four agents")
    return value


def expected_agents(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in manifest["agents"]:
        name = row.get("name")
        marker = row.get("role_marker")
        path = row.get("path")
        if not all(isinstance(item, str) and item for item in (name, marker, path)):
            raise ValueError("invalid agent fixture row")
        if name in result:
            raise ValueError("duplicate expected agent name")
        result[name] = row
    return result


def materialize(args: argparse.Namespace) -> int:
    root = repo_root()
    fixture_root = (
        root / "fixtures/custom-agents" / args.fixture_set / "workspace"
    )
    if not fixture_root.is_dir():
        raise SystemExit("fixture set is absent")
    workspace = Path(args.workspace).resolve()
    if workspace.exists():
        if not workspace.is_dir() or any(workspace.iterdir()):
            raise SystemExit("workspace must be absent or empty")
    else:
        workspace.mkdir(parents=True)

    copied: list[dict[str, str]] = []
    for source in sorted(path for path in fixture_root.rglob("*") if path.is_file()):
        relative = source.relative_to(fixture_root)
        destination = workspace / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        destination.chmod(0o444)
        copied.append(
            {
                "path": relative.as_posix(),
                "sha256": sha256_file(destination),
            }
        )

    harness_destination = workspace / ".issue15/phase1_harness.py"
    harness_destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(Path(__file__).resolve(), harness_destination)
    harness_destination.chmod(0o555)
    copied.append(
        {
            "path": ".issue15/phase1_harness.py",
            "sha256": sha256_file(harness_destination),
        }
    )

    if args.init_git:
        subprocess.run(
            ["git", "init", "--quiet", str(workspace)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )

    emit(
        {
            "schema": "saarius.custom-agent-materialization.v1",
            "workspace_class": "disposable",
            "file_count": len(copied),
            "files": copied,
            "git_initialized": bool(args.init_git),
        }
    )
    return 0


def inventory(args: argparse.Namespace) -> int:
    manifest = load_manifest(Path(args.manifest) if args.manifest else None)
    names = list(expected_agents(manifest))
    raw = sys.stdin.buffer.read()
    text = raw.decode("utf-8", errors="replace")
    found = {name: name in text for name in names}
    result = {
        "schema": INVENTORY_SCHEMA,
        "expected": found,
        "expected_found_count": sum(found.values()),
        "expected_total": len(names),
        "raw_line_count": len(text.splitlines()),
        "raw_sha256": sha256_bytes(raw),
    }
    emit(result)
    return 0 if all(found.values()) else 2


def plugin_inventory(args: argparse.Namespace) -> int:
    if not SAFE_KEY.fullmatch(args.name):
        raise SystemExit("invalid expected plugin name")
    raw = sys.stdin.buffer.read()
    rendered = raw.decode("utf-8", errors="replace")
    found = args.name in rendered
    emit(
        {
            "schema": PLUGIN_INVENTORY_SCHEMA,
            "expected_plugin": args.name,
            "expected_found": found,
            "raw_line_count": len(rendered.splitlines()),
            "raw_sha256": sha256_bytes(raw),
        }
    )
    return 0 if found else 2


def parse_flag(value: str) -> bool:
    if value == "true":
        return True
    if value == "false":
        return False
    raise ValueError("flag must be true or false")


def render_runtime_agent(
    *,
    agent: str,
    role: str,
    role_marker: str,
    main_agent: bool,
    subagent: bool,
) -> str:
    return f"""---
name: {agent}
description: Issue 15 runtime identity fixture for the {role} role.
tools:
  - write_to_file
mainAgent: {str(main_agent).lower()}
subagent: {str(subagent).lower()}
model: inherit
commandExecutionPolicy: "off"
---

You are the Issue 15 {role} runtime identity fixture.

When the user supplies an identity calibration challenge, make exactly one
`write_to_file` call that overwrites the existing `.issue15/result.json` with
only this JSON object:

```json
{{"schema":"{IDENTITY_SCHEMA}","agent":"{agent}","challenge":"<the exact challenge token>","role_marker":"{role_marker}","status":"identity_ready"}}
```

Do not call any other tool. Do not read files, run commands, delegate, explain,
or place the JSON in chat. If the challenge token is absent or ambiguous, stop
without writing.
"""


def build_runtime_fixture(args: argparse.Namespace) -> int:
    if not RUNTIME_AGENT.fullmatch(args.agent):
        raise SystemExit("invalid runtime agent name")
    if args.role not in RUNTIME_ROLES:
        raise SystemExit("invalid runtime role")
    if not SAFE_KEY.fullmatch(args.role_marker):
        raise SystemExit("invalid runtime role marker")
    workspace = Path(args.workspace).resolve()
    if workspace.exists():
        if not workspace.is_dir() or any(workspace.iterdir()):
            raise SystemExit("workspace must be absent or empty")
    else:
        workspace.mkdir(parents=True)

    agent_dir = workspace / ".agents/agents" / args.agent
    result_dir = workspace / ".issue15"
    agent_dir.mkdir(parents=True)
    result_dir.mkdir(parents=True)
    profile = agent_dir / "agent.md"
    result = result_dir / "result.json"
    profile.write_text(
        render_runtime_agent(
            agent=args.agent,
            role=args.role,
            role_marker=args.role_marker,
            main_agent=parse_flag(args.main_agent),
            subagent=parse_flag(args.subagent),
        ),
        encoding="utf-8",
    )
    result.write_bytes(b"")
    profile.chmod(0o444)
    result.chmod(0o600)
    result_dir.chmod(0o700)

    emit(
        {
            "schema": RUNTIME_FIXTURE_SCHEMA,
            "template_version": "2026-07-26.phase1c",
            "agent": args.agent,
            "role": args.role,
            "role_marker": args.role_marker,
            "main_agent": parse_flag(args.main_agent),
            "subagent": parse_flag(args.subagent),
            "profile_sha256": sha256_file(profile),
            "initial_result_sha256": sha256_file(result),
            "initial_result_bytes": 0,
        }
    )
    return 0


def digest_owned_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"present": False, "bytes": 0, "sha256": None}
    raw = path.read_bytes()
    return {
        "present": True,
        "bytes": len(raw),
        "sha256": sha256_bytes(raw),
    }


def validate_print_args(
    args: argparse.Namespace,
) -> tuple[Path, Path, Path, Path, Path, Path, Path, Path, Path]:
    if not RUNTIME_AGENT.fullmatch(args.agent):
        raise SystemExit("invalid runtime agent name")
    if not SAFE_KEY.fullmatch(args.challenge):
        raise SystemExit("invalid challenge token")
    if not SAFE_KEY.fullmatch(args.run_id):
        raise SystemExit("invalid runtime run id")
    if not 100 <= args.quarantine_delay_ms <= 2000:
        raise SystemExit("quarantine delay must be between 100 and 2000 ms")
    if not 1 <= args.timeout_seconds <= 90:
        raise SystemExit("timeout must be between 1 and 90 seconds")

    agy = Path(args.agy).resolve()
    workspace = Path(args.workspace).resolve()
    controller = Path(args.controller).resolve()
    if not agy.is_file() or not os.access(agy, os.X_OK):
        raise SystemExit("agy executable is unavailable")
    if not workspace.is_dir() or not controller.is_dir():
        raise SystemExit("runtime roots must already exist")

    agents_root = workspace / ".agents"
    result = workspace / ".issue15/result.json"
    quarantine = controller / f"{args.run_id}-agents-quarantine"
    raw_stdout = controller / f"{args.run_id}-stdout.raw"
    raw_stderr = controller / f"{args.run_id}-stderr.raw"
    raw_log = controller / f"{args.run_id}-agy.raw"
    for required in (agents_root, result):
        if not required.exists():
            raise SystemExit("runtime fixture is incomplete")
    for target in (quarantine, raw_stdout, raw_stderr, raw_log):
        if target.exists():
            raise SystemExit("owned runtime target already exists")

    return (
        agy,
        workspace,
        controller,
        agents_root,
        result,
        quarantine,
        raw_stdout,
        raw_stderr,
        raw_log,
    )


def execute_print(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    (
        agy,
        workspace,
        controller,
        agents_root,
        result,
        quarantine,
        raw_stdout,
        raw_stderr,
        raw_log,
    ) = validate_print_args(args)

    prompt = (
        f"Identity calibration challenge: {args.challenge}. "
        "Follow the active profile's calibration contract."
    )
    command = [
        str(agy),
        "--add-dir",
        str(workspace),
        "--agent",
        args.agent,
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

    timed_out = False
    process_exit: int | None = None
    started_at_ns = time.time_ns()
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
        workspace.chmod(0o555)
        quarantined_at_ns = time.time_ns()
        try:
            process_exit = process.wait(timeout=args.timeout_seconds + 5)
        except subprocess.TimeoutExpired:
            timed_out = True
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                process_exit = process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process_exit = process.wait(timeout=2)
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

    changed_after_quarantine = (
        result_stat.st_size > 0
        and result_stat.st_mtime_ns >= quarantined_at_ns
    )
    report = {
        "schema": RUNTIME_RUN_SCHEMA,
        "run_id": args.run_id,
        "agent": args.agent,
        "model": args.model,
        "effort": args.effort,
        "execution_mode": args.execution_mode,
        "sandbox": True,
        "workspace_binding": "add-dir-absolute",
        "surface": "print",
        "prompt_class": "challenge-only-argument",
        "prompt_sha256": sha256_bytes(prompt.encode("utf-8")),
        "started_at_ns": started_at_ns,
        "quarantined_at_ns": quarantined_at_ns,
        "finished_at_ns": finished_at_ns,
        "quarantine_delay_ms": args.quarantine_delay_ms,
        "process_exit": process_exit,
        "timed_out": timed_out,
        "result_bytes": result_stat.st_size,
        "result_changed_after_quarantine": changed_after_quarantine,
        "runtime_workspace_mode": "0o555",
        "workspace_mode_restored": True,
        "raw_artifacts": raw_artifacts,
        "raw_artifacts_retained": False,
    }
    return report, 0 if process_exit == 0 and not timed_out else 2


def run_print(args: argparse.Namespace) -> int:
    report, return_code = execute_print(args)
    emit(report)
    return return_code


def exact_name_occurrences(raw: bytes, name: str) -> int:
    if not RUNTIME_AGENT.fullmatch(name):
        raise ValueError("invalid runtime agent name")
    rendered = raw.decode("utf-8", errors="replace")
    pattern = re.compile(
        rf"(?<![A-Za-z0-9_-]){re.escape(name)}(?![A-Za-z0-9_-])"
    )
    return len(pattern.findall(rendered))


def bounded_discovery(
    *,
    agy: Path,
    workspace: Path,
    timeout_seconds: int,
) -> tuple[bytes, bytes, int | None, bool, int, int]:
    command = [
        str(agy),
        "--add-dir",
        str(workspace),
        "agents",
    ]
    started_at_ns = time.time_ns()
    process = subprocess.Popen(
        command,
        cwd=workspace,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    timed_out = False
    process_exit: int | None = None
    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds)
        process_exit = process.returncode
    except subprocess.TimeoutExpired:
        timed_out = True
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            stdout, stderr = process.communicate(timeout=2)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            stdout, stderr = process.communicate(timeout=2)
        process_exit = process.returncode
    finished_at_ns = time.time_ns()
    return (
        stdout,
        stderr,
        process_exit,
        timed_out,
        started_at_ns,
        finished_at_ns,
    )


def guarded_run_print(args: argparse.Namespace) -> int:
    if not 1 <= args.discovery_timeout_seconds <= 30:
        raise SystemExit("discovery timeout must be between 1 and 30 seconds")
    (
        agy,
        workspace,
        _controller,
        _agents_root,
        _result,
        _quarantine,
        _raw_stdout,
        _raw_stderr,
        _raw_log,
    ) = validate_print_args(args)

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
    occurrence_count = exact_name_occurrences(
        discovery_stdout,
        args.agent,
    )
    if discovery_timed_out:
        gate_reason = "discovery_timeout"
    elif discovery_exit != 0:
        gate_reason = "discovery_error"
    elif occurrence_count == 0:
        gate_reason = "agent_absent"
    elif occurrence_count > 1:
        gate_reason = "agent_ambiguous"
    else:
        gate_reason = "exactly_one"
    admitted = gate_reason == "exactly_one"

    report: dict[str, Any] = {
        "schema": GUARDED_RUN_SCHEMA,
        "run_id": args.run_id,
        "requested_agent": args.agent,
        "admitted": admitted,
        "gate_reason": gate_reason,
        "model_launch_started": False,
        "discovery": {
            "command_class": "absolute-add-dir-agents",
            "process_exit": discovery_exit,
            "timed_out": discovery_timed_out,
            "started_at_ns": discovery_started_at_ns,
            "finished_at_ns": discovery_finished_at_ns,
            "exact_name_occurrences": occurrence_count,
            "stdout": {
                "bytes": len(discovery_stdout),
                "line_count": len(
                    discovery_stdout.decode(
                        "utf-8",
                        errors="replace",
                    ).splitlines()
                ),
                "sha256": sha256_bytes(discovery_stdout),
            },
            "stderr": {
                "bytes": len(discovery_stderr),
                "sha256": sha256_bytes(discovery_stderr),
            },
            "raw_retained": False,
        },
        "runtime": None,
    }
    if not admitted:
        emit(report)
        return 2

    report["model_launch_started"] = True
    runtime_report, return_code = execute_print(args)
    report["runtime"] = runtime_report
    emit(report)
    return return_code


def runtime_postflight(args: argparse.Namespace) -> int:
    if not RUNTIME_AGENT.fullmatch(args.agent):
        raise SystemExit("invalid runtime agent name")
    workspace = Path(args.workspace).resolve()
    quarantine = Path(args.quarantine).resolve()
    if not workspace.is_dir() or not quarantine.is_dir():
        raise SystemExit("runtime roots are unavailable")

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
    profile_agent = args.profile_agent or args.agent
    if not RUNTIME_AGENT.fullmatch(profile_agent):
        raise SystemExit("invalid profile agent name")
    expected_workspace = [".issue15/result.json"]
    expected_quarantine = [f"agents/{profile_agent}/agent.md"]
    profile = quarantine / expected_quarantine[0]
    result = workspace / expected_workspace[0]
    profile_hash = sha256_file(profile) if profile.is_file() else None
    result_hash = sha256_file(result) if result.is_file() else None
    result_state_matches = (
        result.is_file()
        and (
            (args.result_state == "changed" and result.stat().st_size > 0)
            or (args.result_state == "unchanged" and result.stat().st_size == 0)
        )
    )
    passed = (
        workspace_files == expected_workspace
        and quarantine_files == expected_quarantine
        and profile_hash == args.expected_profile_sha256
        and result_state_matches
    )
    emit(
        {
            "schema": RUNTIME_POSTFLIGHT_SCHEMA,
            "passed": passed,
            "workspace_files": workspace_files,
            "quarantine_files": quarantine_files,
            "profile_sha256": profile_hash,
            "result_sha256": result_hash,
            "result_bytes": result.stat().st_size if result.is_file() else 0,
            "expected_result_state": args.result_state,
            "workspace_mode": oct(stat.S_IMODE(workspace.stat().st_mode)),
            "foreign_state_touched": False,
        }
    )
    return 0 if passed else 2


def opaque_actor(conversation_id: Any, salt: str) -> str:
    raw = conversation_id if isinstance(conversation_id, str) else "missing"
    return hashlib.sha256((salt + "\0" + raw).encode("utf-8")).hexdigest()[:24]


def safe_arg_keys(payload: dict[str, Any]) -> list[str]:
    tool_call = payload.get("toolCall")
    if not isinstance(tool_call, dict):
        return []
    args = tool_call.get("args")
    if not isinstance(args, dict):
        return []
    return sorted(key for key in args if isinstance(key, str) and SAFE_KEY.fullmatch(key))


def append_event(path: Path, event: dict[str, Any]) -> None:
    if not path.parent.is_dir():
        raise RuntimeError("event log parent must already exist")
    encoded = (
        json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        os.write(descriptor, encoded)
    finally:
        os.close(descriptor)


def acquire_write_sentinel(path: Path, actor_id: str) -> bool:
    if not path.parent.is_dir():
        raise RuntimeError("write sentinel parent must already exist")
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return False
    try:
        os.write(descriptor, (actor_id + "\n").encode("ascii"))
    finally:
        os.close(descriptor)
    return True


def is_exact_result_write(payload: dict[str, Any]) -> bool:
    tool_call = payload.get("toolCall")
    if not isinstance(tool_call, dict) or tool_call.get("name") != "write_to_file":
        return False
    tool_args = tool_call.get("args")
    if not isinstance(tool_args, dict):
        return False
    target = tool_args.get("TargetFile")
    if not isinstance(target, str) or not target:
        return False

    workspace = Path(os.environ["ISSUE15_WORKSPACE"]).resolve()
    configured_result = Path(os.environ["ISSUE15_RESULT_FILE"]).resolve()
    expected_result = (workspace / ".issue15/result.json").resolve()
    if configured_result != expected_result:
        raise RuntimeError("result path is outside the exact campaign contract")

    candidate = Path(target)
    if not candidate.is_absolute():
        candidate = workspace / candidate
    return candidate.resolve() == expected_result


def hook(args: argparse.Namespace) -> int:
    if args.event not in ALLOWED_EVENTS:
        raise SystemExit("unsupported hook event")
    payload = json.load(sys.stdin)
    if not isinstance(payload, dict):
        raise SystemExit("hook payload must be an object")

    event_log = Path(os.environ["ISSUE15_EVENT_LOG"]).resolve()
    salt = os.environ["ISSUE15_RUN_SALT"]
    actor_id = opaque_actor(payload.get("conversationId"), salt)
    tool_call = payload.get("toolCall")
    tool_name = tool_call.get("name") if isinstance(tool_call, dict) else None
    if not isinstance(tool_name, str) or not SAFE_KEY.fullmatch(tool_name):
        tool_name = None

    decision: str | None = None
    exact_result_target: bool | None = None
    if args.event == "PreToolUse":
        allow_write = os.environ.get("ISSUE15_ALLOW_ONE_WRITE") == "1"
        sentinel_value = os.environ.get("ISSUE15_WRITE_SENTINEL")
        first_write = False
        exact_result_target = is_exact_result_write(payload)
        if allow_write and exact_result_target and sentinel_value:
            first_write = acquire_write_sentinel(Path(sentinel_value), actor_id)
        decision = "allow" if first_write else "deny"

    termination = payload.get("terminationReason")
    if termination not in ALLOWED_TERMINATIONS:
        termination = "other" if termination is not None else None
    workspace_paths = payload.get("workspacePaths")
    workspace_count = len(workspace_paths) if isinstance(workspace_paths, list) else 0
    workspace_digest = None
    if isinstance(workspace_paths, list):
        bounded = [item for item in workspace_paths if isinstance(item, str)]
        workspace_digest = sha256_bytes(
            (salt + "\0" + json.dumps(bounded, sort_keys=True)).encode("utf-8")
        )

    event = {
        "schema": EVENT_SCHEMA,
        "observed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "event": args.event,
        "actor_id": actor_id,
        "workspace_count": workspace_count,
        "workspace_digest": workspace_digest,
        "tool_name": tool_name,
        "tool_arg_keys": safe_arg_keys(payload),
        "invocation_num": payload.get("invocationNum")
        if isinstance(payload.get("invocationNum"), int)
        else None,
        "step_idx": payload.get("stepIdx")
        if isinstance(payload.get("stepIdx"), int)
        else None,
        "execution_num": payload.get("executionNum")
        if isinstance(payload.get("executionNum"), int)
        else None,
        "termination_reason": termination,
        "error": bool(payload.get("error")),
        "fully_idle": payload.get("fullyIdle")
        if isinstance(payload.get("fullyIdle"), bool)
        else None,
        "exact_result_target": exact_result_target,
        "decision": decision,
    }
    append_event(event_log, event)

    if args.event == "PreToolUse":
        emit(
            {
                "decision": decision,
                "reason": "issue15_phase1_single_result_write"
                if decision == "allow"
                else "issue15_phase1_tool_denied",
            }
        )
    elif args.event == "Stop":
        emit({"decision": "allow"})
    else:
        emit({})
    return 0


def iter_agent_metadata(
    value: Any,
    expected: set[str],
    path: tuple[str, ...] = (),
) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        for key, child in value.items():
            safe_key = key if isinstance(key, str) and SAFE_KEY.fullmatch(key) else "other"
            yield from iter_agent_metadata(child, expected, path + (safe_key,))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from iter_agent_metadata(child, expected, path + (str(index),))
    elif isinstance(value, str) and value in expected:
        if any("agent" in item.lower() or "profile" in item.lower() for item in path):
            yield {"agent": value, "path": list(path)}


def sanitize_log(args: argparse.Namespace) -> int:
    manifest = load_manifest(Path(args.manifest) if args.manifest else None)
    expected = set(expected_agents(manifest))
    raw_path = Path(args.input).resolve()
    raw = raw_path.read_bytes()
    matches: list[dict[str, Any]] = []
    parse_errors = 0
    record_count = 0
    for line in raw.splitlines():
        if not line.strip():
            continue
        record_count += 1
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            parse_errors += 1
            continue
        matches.extend(iter_agent_metadata(value, expected))

    unique: list[dict[str, Any]] = []
    seen: set[tuple[str, tuple[str, ...]]] = set()
    for match in matches:
        identity = (match["agent"], tuple(match["path"]))
        if identity not in seen:
            seen.add(identity)
            unique.append(match)

    result = {
        "schema": LOG_SCHEMA,
        "record_count": record_count,
        "parse_errors": parse_errors,
        "raw_sha256": sha256_bytes(raw),
        "agent_metadata_matches": unique,
        "raw_retained": False,
    }
    output = Path(args.output).resolve()
    output.write_text(
        json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    emit(result)
    return 0


def verify_result(args: argparse.Namespace) -> int:
    if args.role_marker:
        if not SAFE_KEY.fullmatch(args.role_marker):
            raise SystemExit("invalid role marker")
        marker = args.role_marker
    else:
        manifest = load_manifest(Path(args.manifest) if args.manifest else None)
        agents = expected_agents(manifest)
        if args.agent not in agents:
            raise SystemExit("requested agent is absent from manifest")
        marker = agents[args.agent]["role_marker"]
    raw_path = Path(args.result).resolve()
    raw = raw_path.read_bytes()
    reasons: list[str] = []
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        value = None
        reasons.append("invalid_json")

    expected = {
        "schema": IDENTITY_SCHEMA,
        "agent": args.agent,
        "challenge": args.challenge,
        "role_marker": marker,
        "status": "identity_ready",
    }
    if not isinstance(value, dict):
        reasons.append("not_object")
    elif value != expected:
        if set(value) != set(expected):
            reasons.append("field_set_mismatch")
        for key, expected_value in expected.items():
            if value.get(key) != expected_value:
                reasons.append(f"{key}_mismatch")

    passed = not reasons
    emit(
        {
            "schema": VERIFY_SCHEMA,
            "agent": args.agent,
            "passed": passed,
            "reasons": sorted(set(reasons)),
            "result_sha256": sha256_bytes(raw),
        }
    )
    return 0 if passed else 2


def configure_runtime_run_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--agy", required=True)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--controller", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--agent", required=True)
    parser.add_argument("--challenge", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument(
        "--effort", choices=("low", "medium", "high"), required=True
    )
    parser.add_argument(
        "--execution-mode",
        choices=("accept-edits",),
        default="accept-edits",
    )
    parser.add_argument("--quarantine-delay-ms", type=int, default=350)
    parser.add_argument("--timeout-seconds", type=int, default=90)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)

    materialize_parser = commands.add_parser("materialize")
    materialize_parser.add_argument("--workspace", required=True)
    materialize_parser.add_argument("--init-git", action="store_true")
    materialize_parser.add_argument(
        "--fixture-set",
        choices=("phase1", "phase1b"),
        default="phase1",
    )
    materialize_parser.set_defaults(handler=materialize)

    inventory_parser = commands.add_parser("inventory")
    inventory_parser.add_argument("--manifest")
    inventory_parser.set_defaults(handler=inventory)

    plugin_inventory_parser = commands.add_parser("plugin-inventory")
    plugin_inventory_parser.add_argument("--name", required=True)
    plugin_inventory_parser.set_defaults(handler=plugin_inventory)

    runtime_fixture_parser = commands.add_parser("build-runtime-fixture")
    runtime_fixture_parser.add_argument("--workspace", required=True)
    runtime_fixture_parser.add_argument("--agent", required=True)
    runtime_fixture_parser.add_argument("--role", choices=sorted(RUNTIME_ROLES))
    runtime_fixture_parser.add_argument("--role-marker", required=True)
    runtime_fixture_parser.add_argument(
        "--main-agent", choices=("true", "false"), default="true"
    )
    runtime_fixture_parser.add_argument(
        "--subagent", choices=("true", "false"), default="true"
    )
    runtime_fixture_parser.set_defaults(handler=build_runtime_fixture)

    runtime_run_parser = commands.add_parser("run-print")
    configure_runtime_run_parser(runtime_run_parser)
    runtime_run_parser.set_defaults(handler=run_print)

    guarded_run_parser = commands.add_parser("guarded-run-print")
    configure_runtime_run_parser(guarded_run_parser)
    guarded_run_parser.add_argument(
        "--discovery-timeout-seconds",
        type=int,
        default=10,
    )
    guarded_run_parser.set_defaults(handler=guarded_run_print)

    runtime_postflight_parser = commands.add_parser("runtime-postflight")
    runtime_postflight_parser.add_argument("--workspace", required=True)
    runtime_postflight_parser.add_argument("--quarantine", required=True)
    runtime_postflight_parser.add_argument("--agent", required=True)
    runtime_postflight_parser.add_argument("--profile-agent")
    runtime_postflight_parser.add_argument(
        "--expected-profile-sha256", required=True
    )
    runtime_postflight_parser.add_argument(
        "--result-state",
        choices=("changed", "unchanged"),
        default="changed",
    )
    runtime_postflight_parser.set_defaults(handler=runtime_postflight)

    hook_parser = commands.add_parser("hook")
    hook_parser.add_argument("event", choices=sorted(ALLOWED_EVENTS))
    hook_parser.set_defaults(handler=hook)

    log_parser = commands.add_parser("sanitize-log")
    log_parser.add_argument("--input", required=True)
    log_parser.add_argument("--output", required=True)
    log_parser.add_argument("--manifest")
    log_parser.set_defaults(handler=sanitize_log)

    verify_parser = commands.add_parser("verify-result")
    verify_parser.add_argument("--result", required=True)
    verify_parser.add_argument("--agent", required=True)
    verify_parser.add_argument("--challenge", required=True)
    verify_parser.add_argument("--manifest")
    verify_parser.add_argument("--role-marker")
    verify_parser.set_defaults(handler=verify_result)

    return parser


def main() -> int:
    args = build_parser().parse_args()
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
