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
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


EVENT_SCHEMA = "saarius.custom-agent-event.v1"
IDENTITY_SCHEMA = "saarius.custom-agent.identity.v1"
INVENTORY_SCHEMA = "saarius.custom-agent-inventory.v1"
LOG_SCHEMA = "saarius.custom-agent-log-sanitizer.v1"
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
    fixture_root = root / "fixtures/custom-agents/phase1/workspace"
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
    manifest = load_manifest(Path(args.manifest) if args.manifest else None)
    agents = expected_agents(manifest)
    if args.agent not in agents:
        raise SystemExit("requested agent is absent from manifest")
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
        "role_marker": agents[args.agent]["role_marker"],
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)

    materialize_parser = commands.add_parser("materialize")
    materialize_parser.add_argument("--workspace", required=True)
    materialize_parser.add_argument("--init-git", action="store_true")
    materialize_parser.set_defaults(handler=materialize)

    inventory_parser = commands.add_parser("inventory")
    inventory_parser.add_argument("--manifest")
    inventory_parser.set_defaults(handler=inventory)

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
    verify_parser.set_defaults(handler=verify_result)

    return parser


def main() -> int:
    args = build_parser().parse_args()
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
