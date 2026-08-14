#!/usr/bin/env python3
"""Concurrent operator coordinator for exact Puppet v0.1 run plans.

This script owns no harness authority.  It validates controller-produced plans
and invokes their existing single-lane Puppet commands in parallel.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import signal
import stat
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Mapping, Sequence

from puppet_lib.census import adapter_implementation_fingerprint
from puppet_lib.contracts import Contract, TARGETS
from puppet_lib.errors import IdentityError, PuppetError, ValidationError
from puppet_lib.handoffs import PROTOCOL_FINGERPRINT
from puppet_lib.operator_plan import (
    OPERATOR_PLAN_SCHEMA,
    OPERATOR_PLAN_STATE,
    compile_operator_plan,
)
from puppet_lib.safety import (
    canonical_json_bytes,
    paths_overlap,
    read_json,
    sha256_bytes,
    sha256_file,
    validate_bounded_json,
    validate_identifier,
    validate_sha256,
)
from puppet_lib.state import STATES
from puppet_lib.viewer import TICKET_TTL_SECONDS


FANOUT_VERSION = "0.2.0"
RESULT_SCHEMA = "puppet.fanout-result/v1"
PROGRESS_SCHEMA = "puppet.fanout-progress/v1"
MAX_LANES = len(TARGETS)
MAX_CHILD_OUTPUT_BYTES = 1024 * 1024
CHILD_TIMEOUT_SECONDS = 120.0
CHILD_INTERRUPT_GRACE_SECONDS = 15.0
CHILD_OPERATOR_INTERRUPT_GRACE_SECONDS = 5.0
CHILD_TERMINATE_GRACE_SECONDS = 5.0
CHILD_DRAIN_GRACE_SECONDS = 1.0
CHILD_DRAIN_SETTLE_SECONDS = 0.25
ATTACH_CHILD_TIMEOUT_SECONDS = 5.0
ATTACH_INTERRUPT_GRACE_SECONDS = 3.0
ATTACH_TERMINATE_GRACE_SECONDS = 2.0
ATTACH_PHASE_MAX_SECONDS = (
    ATTACH_CHILD_TIMEOUT_SECONDS
    + ATTACH_INTERRUPT_GRACE_SECONDS
    + (2 * ATTACH_TERMINATE_GRACE_SECONDS)
    + CHILD_DRAIN_GRACE_SECONDS
    + CHILD_DRAIN_SETTLE_SECONDS
)
_OPERATOR_INTERRUPT = threading.Event()
_ACTION_KEYS = {
    "launch": ("launch", "launch"),
    "status": ("status", "status"),
    "attach": ("attach_command", "attach-command"),
    "view": ("open_view", "open-view"),
    "halt": ("halt", "halt"),
}
_WARM_LAUNCH_BLOCKERS = {
    "operator_plan_is_not_launch_authority",
    "doctor_must_pass_at_execution_time",
    "private_profile_must_be_authenticated_at_execution_time",
    "adapter_qualification_must_be_current",
    "human_must_choose_to_execute_launch",
}
_CONTROLLER_ERROR_CATEGORIES = frozenset(
    {
        "puppet_error",
        "validation_error",
        "conflict",
        "identity_mismatch",
        "unsupported",
    }
)
_TERMINAL_APPS = {
    "iTerm": frozenset({"/Applications/iTerm.app"}),
    "Terminal": frozenset(
        {
            "/System/Applications/Utilities/Terminal.app",
            "/Applications/Utilities/Terminal.app",
        }
    ),
}


@dataclass(frozen=True)
class LanePlan:
    target: str
    session: str
    path: Path
    file_sha256: str
    plan_sha256: str
    controller: Dict[str, Any]
    repository: Path
    run_root: Path
    proof_root: Path
    state_root: Path
    profile_root: Path | None
    contract: Contract
    commands: Dict[str, Any]
    raw: Dict[str, Any]


def _regular_file(path: Path, *, label: str, max_bytes: int) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        raise ValidationError("%s must be absolute" % label)
    try:
        details = os.lstat(candidate)
    except OSError as exc:
        raise ValidationError("%s is unavailable" % label) from exc
    if (
        stat.S_ISLNK(details.st_mode)
        or not stat.S_ISREG(details.st_mode)
        or details.st_size > max_bytes
    ):
        raise ValidationError("%s must be a bounded regular non-symlink file" % label)
    return candidate


def _absolute_path(value: Any, *, label: str) -> Path:
    if (
        not isinstance(value, str)
        or not value
        or "\x00" in value
        or len(value) > 4096
    ):
        raise ValidationError("%s path is invalid" % label)
    candidate = Path(value)
    if not candidate.is_absolute() or os.path.normpath(value) != value:
        raise ValidationError("%s path must be normalized and absolute" % label)
    return candidate


def _artifact(plan: Mapping[str, Any], name: str) -> Path:
    artifacts = plan.get("artifacts")
    if not isinstance(artifacts, Mapping):
        raise ValidationError("operator plan artifacts are invalid")
    value = artifacts.get(name)
    if not isinstance(value, Mapping) or set(value) != {"path", "sha256", "bytes"}:
        raise ValidationError("operator plan artifact identity is invalid")
    path = _regular_file(
        _absolute_path(value.get("path"), label="operator plan artifact"),
        label="operator plan artifact",
        max_bytes=1024 * 1024,
    )
    if (
        isinstance(value.get("bytes"), bool)
        or not isinstance(value.get("bytes"), int)
        or value["bytes"] != path.stat().st_size
        or sha256_file(path, max_bytes=1024 * 1024)
        != validate_sha256(value.get("sha256"), "operator plan artifact")
    ):
        raise IdentityError("operator plan artifact changed")
    return path


def _root(plan: Mapping[str, Any], name: str, *, optional: bool = False) -> Path | None:
    roots = plan.get("roots")
    if not isinstance(roots, Mapping):
        raise ValidationError("operator plan roots are invalid")
    value = roots.get(name)
    if value is None and optional:
        return None
    path = _absolute_path(value, label="operator plan %s root" % name)
    if not path.is_dir() or path.is_symlink():
        raise ValidationError("operator plan %s root is unavailable" % name)
    path.resolve(strict=True)
    return path


def _controller(plan: Mapping[str, Any]) -> Dict[str, Any]:
    value = plan.get("controller")
    fields = {
        "version",
        "adapter_implementation_sha256",
        "protocol_sha256",
        "interpreter",
        "interpreter_sha256",
        "cli",
        "cli_sha256",
    }
    if not isinstance(value, Mapping) or set(value) != fields:
        raise ValidationError("operator plan controller identity is invalid")
    result = dict(value)
    interpreter = _regular_file(
        _absolute_path(result["interpreter"], label="operator interpreter"),
        label="operator interpreter",
        max_bytes=256 * 1024 * 1024,
    ).resolve(strict=True)
    cli = _regular_file(
        _absolute_path(result["cli"], label="Puppet controller"),
        label="Puppet controller",
        max_bytes=1024 * 1024,
    ).resolve(strict=True)
    expected_cli = (Path(__file__).resolve(strict=True).parent / "puppet.py").resolve(
        strict=True
    )
    if cli != expected_cli or interpreter != Path(sys.executable).resolve(strict=True):
        raise IdentityError("operator plan belongs to another controller runtime")
    if (
        sha256_file(interpreter)
        != validate_sha256(
            result["interpreter_sha256"], "operator interpreter fingerprint"
        )
        or sha256_file(cli)
        != validate_sha256(result["cli_sha256"], "Puppet controller fingerprint")
        or result["adapter_implementation_sha256"]
        != adapter_implementation_fingerprint()
        or result["protocol_sha256"] != PROTOCOL_FINGERPRINT
    ):
        raise IdentityError("operator plan controller identity changed")
    result["interpreter"] = str(interpreter)
    result["cli"] = str(cli)
    return result


def _expected_commands(
    *,
    plan: Mapping[str, Any],
    contract: Contract,
    controller: Mapping[str, Any],
    session: str,
    proof_root: Path,
    state_root: Path,
    profile_root: Path | None,
) -> Dict[str, list[str]]:
    base = [controller["interpreter"], controller["cli"], "--json"]
    contract_path = _artifact(plan, "contract")
    manifest_path = _artifact(plan, "manifest")
    authorization_path = _artifact(plan, "authorization")
    input_path = _artifact(plan, "input_payload")
    common = [
        "--contract",
        str(contract_path),
        "--manifest",
        str(manifest_path),
        "--authorization",
        str(authorization_path),
        "--proof-root",
        str(proof_root),
        "--state-root",
        str(state_root),
    ]
    if profile_root is not None:
        common.extend(["--profile-root", str(profile_root)])
    launch = [
        *base,
        "launch",
        "--session",
        session,
        *common,
        "--prompt-file",
        str(input_path),
    ]
    if contract.requested_model is not None:
        launch.extend(["--model", contract.requested_model])
    if contract.requested_effort is not None:
        launch.extend(["--effort", contract.requested_effort])
    session_base = ["--state-root", str(state_root), "--session", session]
    return {
        "launch": launch,
        "status": [*base, "status", *session_base],
        "attach_command": [*base, "attach-command", *session_base],
        "open_view": [
            *base,
            "open-view",
            *session_base,
            "--terminal",
            "auto",
        ],
        "halt": [*base, "halt", *session_base, "--timeout", "10.0"],
    }


def load_lane_plan(path: Path | str) -> LanePlan:
    plan_path = _regular_file(
        Path(path),
        label="operator plan",
        max_bytes=1024 * 1024,
    ).resolve(strict=True)
    plan = read_json(
        plan_path,
        max_bytes=1024 * 1024,
        reject_sensitive_fields=True,
    )
    validate_bounded_json(
        plan,
        max_depth=8,
        max_items=192,
        max_string=4096,
        reject_sensitive_fields=True,
    )
    if (
        plan.get("schema") != OPERATOR_PLAN_SCHEMA
        or plan.get("state") != OPERATOR_PLAN_STATE
        or plan.get("launch_authorized") is not False
    ):
        raise ValidationError("operator plan schema or state is invalid")
    required_fields = {
        "schema",
        "state",
        "entry_mode",
        "target",
        "session_profile",
        "session",
        "branch",
        "launch_authorized",
        "blockers",
        "controller",
        "repository",
        "supervisor_repository",
        "roots",
        "artifacts",
        "commands",
        "plan_sha256",
    }
    if set(plan) not in (required_fields, required_fields | {"target_gate"}):
        raise ValidationError("operator plan fields are invalid")
    recorded_plan_sha = validate_sha256(
        plan.get("plan_sha256"), "operator plan fingerprint"
    )
    unhashed = dict(plan)
    unhashed.pop("plan_sha256")
    if sha256_bytes(canonical_json_bytes(unhashed)) != recorded_plan_sha:
        raise IdentityError("operator plan fingerprint changed")

    target = plan.get("target")
    if target not in TARGETS:
        raise ValidationError("operator plan target is invalid")
    session = validate_identifier(plan.get("session"), "operator plan session")
    blockers = plan.get("blockers")
    expected_blockers = set(_WARM_LAUNCH_BLOCKERS)
    if target == "agy":
        expected_blockers.remove(
            "private_profile_must_be_authenticated_at_execution_time"
        )
    if (
        not isinstance(blockers, list)
        or len(blockers) != len(expected_blockers)
        or set(blockers) != expected_blockers
        or "target_gate" in plan
    ):
        raise ValidationError(
            "fanout accepts only warm qualified regular operator plans"
        )
    controller = _controller(plan)
    contract_path = _artifact(plan, "contract")
    contract = Contract.from_path(contract_path)
    if contract.target != target or contract.branch != plan.get("branch"):
        raise IdentityError("operator plan contract identity changed")
    repository_value = plan.get("repository")
    if not isinstance(repository_value, Mapping):
        raise ValidationError("operator plan repository identity is invalid")
    repository = _absolute_path(
        repository_value.get("repo"), label="operator plan repository"
    )
    if repository.resolve(strict=True) != contract.repo:
        raise IdentityError("operator plan repository identity changed")

    run_root = _root(plan, "run")
    proof_root = _root(plan, "proof")
    state_root = _root(plan, "state")
    profile_root = _root(plan, "profile", optional=True)
    if run_root is None or proof_root is None or state_root is None:
        raise ValidationError("operator plan ownership roots are incomplete")
    if proof_root != run_root / "proof" or state_root != run_root / "state":
        raise IdentityError("operator plan proof and state roots changed")
    if target == "agy" and profile_root is not None:
        raise ValidationError("AGY fanout plans must not select a private profile")
    if target != "agy" and profile_root is None:
        raise ValidationError("non-AGY fanout plans require a private profile")

    commands = plan.get("commands")
    if not isinstance(commands, Mapping) or set(commands) != {
        "doctor",
        "launch",
        "status",
        "waits",
        "attach_command",
        "open_view",
        "halt",
        "profile",
    }:
        raise ValidationError("operator plan commands are invalid")
    expected = _expected_commands(
        plan=plan,
        contract=contract,
        controller=controller,
        session=session,
        proof_root=proof_root,
        state_root=state_root,
        profile_root=profile_root,
    )
    for key, expected_argv in expected.items():
        recorded = commands.get(key)
        if isinstance(recorded, list) and recorded != expected_argv:
            raise IdentityError("operator plan %s command changed" % key)
        if not isinstance(recorded, (list, Mapping)):
            raise ValidationError("operator plan %s command is invalid" % key)

    return LanePlan(
        target=target,
        session=session,
        path=plan_path,
        file_sha256=sha256_file(plan_path, max_bytes=1024 * 1024),
        plan_sha256=recorded_plan_sha,
        controller=controller,
        repository=contract.repo,
        run_root=run_root,
        proof_root=proof_root,
        state_root=state_root,
        profile_root=profile_root,
        contract=contract,
        commands=dict(commands),
        raw=dict(plan),
    )


def load_lane_plans(paths: Iterable[Path | str]) -> list[LanePlan]:
    raw_paths = list(paths)
    if not raw_paths or len(raw_paths) > MAX_LANES:
        raise ValidationError("fanout requires between one and five operator plans")
    lanes = [load_lane_plan(path) for path in raw_paths]
    if len({lane.path for lane in lanes}) != len(lanes):
        raise ValidationError("fanout operator plans must be unique")
    if len({lane.target for lane in lanes}) != len(lanes):
        raise ValidationError("fanout permits at most one lane per target")
    if len({lane.session for lane in lanes}) != len(lanes):
        raise ValidationError("fanout sessions must be unique")
    if any(lane.controller != lanes[0].controller for lane in lanes[1:]):
        raise IdentityError("fanout plans must use one immutable controller")
    if any(
        lane.contract.controller != lanes[0].contract.controller
        or lane.contract.campaign_authorization_id
        != lanes[0].contract.campaign_authorization_id
        for lane in lanes[1:]
    ):
        raise IdentityError("fanout plans must share controller and campaign authority")
    if len({lane.repository for lane in lanes}) != len(lanes):
        raise ValidationError("fanout lanes require distinct worktrees")

    for index, lane in enumerate(lanes):
        own_roots = [lane.repository, lane.run_root]
        if lane.profile_root is not None:
            own_roots.append(lane.profile_root)
        for left_index, left in enumerate(own_roots):
            for right in own_roots[left_index + 1 :]:
                if paths_overlap(left, right):
                    raise ValidationError(
                        "fanout worktree, run, and profile roots must not overlap"
                    )
        for other in lanes[index + 1 :]:
            other_roots = [other.repository, other.run_root]
            if other.profile_root is not None:
                other_roots.append(other.profile_root)
            for left in own_roots:
                for right in other_roots:
                    if paths_overlap(left, right):
                        raise ValidationError(
                            "fanout ownership roots must not overlap across lanes"
                        )
    return sorted(lanes, key=lambda lane: lane.target)


def _safe_child_json(value: bytes) -> Dict[str, Any] | None:
    if not value or len(value) > MAX_CHILD_OUTPUT_BYTES:
        return None
    try:
        decoded = value.decode("utf-8")
        parsed = json.loads(decoded)
        validate_bounded_json(
            parsed,
            max_depth=8,
            max_items=192,
            max_string=8192,
            reject_sensitive_fields=True,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, PuppetError, RecursionError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _drain_bounded(
    stream: Any,
    captures: Dict[str, tuple[bytes, bool]],
    key: str,
) -> None:
    buffered = bytearray()
    invalid = False
    try:
        while True:
            chunk = stream.read(64 * 1024)
            if not chunk:
                break
            remaining = MAX_CHILD_OUTPUT_BYTES + 1 - len(buffered)
            if remaining > 0:
                buffered.extend(chunk[:remaining])
            if len(buffered) > MAX_CHILD_OUTPUT_BYTES or len(chunk) > remaining:
                invalid = True
    except (OSError, ValueError):
        invalid = True
    finally:
        try:
            stream.close()
        except (OSError, ValueError):
            pass
        captures[key] = (bytes(buffered), invalid)


def _default_runner(argv: Sequence[str]) -> subprocess.CompletedProcess[bytes]:
    command = list(argv)
    if _OPERATOR_INTERRUPT.is_set():
        raise subprocess.TimeoutExpired(command, 0)
    child_timeout, child_interrupt_grace, terminate_grace = _runner_limits(
        command
    )
    process = subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    if process.stdout is None or process.stderr is None:
        raise RuntimeError("controller output pipes are unavailable")
    captures: Dict[str, tuple[bytes, bool]] = {}
    drainers = {
        "stdout": (
            process.stdout,
            threading.Thread(
                target=_drain_bounded,
                args=(process.stdout, captures, "stdout"),
                daemon=True,
            ),
        ),
        "stderr": (
            process.stderr,
            threading.Thread(
                target=_drain_bounded,
                args=(process.stderr, captures, "stderr"),
                daemon=True,
            ),
        ),
    }
    for _, thread in drainers.values():
        thread.start()

    interrupted = False
    deadline = time.monotonic() + child_timeout
    while process.poll() is None:
        if _OPERATOR_INTERRUPT.is_set():
            interrupted = True
            break
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        try:
            process.wait(timeout=min(0.1, remaining))
        except subprocess.TimeoutExpired:
            continue

    timed_out = process.poll() is None
    if timed_out:
        try:
            process.send_signal(signal.SIGINT)
        except ProcessLookupError:
            pass
        grace = (
            min(
                CHILD_OPERATOR_INTERRUPT_GRACE_SECONDS,
                child_interrupt_grace,
            )
            if interrupted
            else child_interrupt_grace
        )
        grace_deadline = time.monotonic() + grace
        while process.poll() is None:
            if not interrupted and _OPERATOR_INTERRUPT.is_set():
                interrupted = True
                grace_deadline = min(
                    grace_deadline,
                    time.monotonic()
                    + min(
                        CHILD_OPERATOR_INTERRUPT_GRACE_SECONDS,
                        child_interrupt_grace,
                    ),
                )
            remaining = grace_deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                process.wait(timeout=min(0.1, remaining))
            except subprocess.TimeoutExpired:
                continue
        _terminate_owned_process_group(
            process,
            grace_seconds=terminate_grace,
        )
        if process.poll() is None:
            try:
                process.wait(timeout=terminate_grace)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    if process.poll() is None:
                        process.kill()
                process.wait(timeout=terminate_grace)

    drain_deadline = time.monotonic() + CHILD_DRAIN_GRACE_SECONDS
    for _, thread in drainers.values():
        thread.join(timeout=max(0.0, drain_deadline - time.monotonic()))
    incomplete_drain = any(
        thread.is_alive() for _, thread in drainers.values()
    )
    if incomplete_drain:
        _terminate_owned_process_group(
            process,
            grace_seconds=terminate_grace,
        )
    settle_deadline = time.monotonic() + CHILD_DRAIN_SETTLE_SECONDS
    for _, thread in drainers.values():
        if thread.is_alive():
            thread.join(timeout=max(0.0, settle_deadline - time.monotonic()))
    outputs: Dict[str, bytes] = {}
    for key in ("stdout", "stderr"):
        value, invalid = captures.get(key, (b"", True))
        invalid = invalid or incomplete_drain
        outputs[key] = (
            b"\x00" * (MAX_CHILD_OUTPUT_BYTES + 1) if invalid else value
        )
    if timed_out:
        raise subprocess.TimeoutExpired(
            command,
            child_timeout,
        )
    return subprocess.CompletedProcess(
        command,
        process.returncode,
        stdout=outputs["stdout"],
        stderr=outputs["stderr"],
    )


def _runner_limits(command: Sequence[str]) -> tuple[float, float, float]:
    if len(command) > 3 and command[3] == "attach-command":
        return (
            ATTACH_CHILD_TIMEOUT_SECONDS,
            ATTACH_INTERRUPT_GRACE_SECONDS,
            ATTACH_TERMINATE_GRACE_SECONDS,
        )
    return (
        CHILD_TIMEOUT_SECONDS,
        CHILD_INTERRUPT_GRACE_SECONDS,
        CHILD_TERMINATE_GRACE_SECONDS,
    )


def _terminate_owned_process_group(
    process: subprocess.Popen[bytes],
    *,
    grace_seconds: float,
) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        return
    deadline = time.monotonic() + grace_seconds
    while time.monotonic() < deadline:
        try:
            os.killpg(process.pid, 0)
        except (ProcessLookupError, PermissionError):
            return
        time.sleep(0.05)
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


def _lane_command(lane: LanePlan, action: str) -> list[str] | None:
    try:
        plan_key, command_name = _ACTION_KEYS[action]
    except KeyError as exc:
        raise ValidationError("fanout action is unsupported") from exc
    command = lane.commands.get(plan_key)
    if not isinstance(command, list):
        return None
    if (
        len(command) < 4
        or command[:3]
        != [lane.controller["interpreter"], lane.controller["cli"], "--json"]
        or command[3] != command_name
    ):
        raise IdentityError("fanout command no longer matches the operator plan")
    return list(command)


def _lane_failure(
    lane: LanePlan,
    *,
    action: str,
    state: str,
    error: str,
    returncode: int | None = None,
    elapsed_ms: int | None = None,
) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "ok": False,
        "target": lane.target,
        "session": lane.session,
        "state": state,
        "error": error,
    }
    if returncode is not None:
        result["returncode"] = returncode
    if elapsed_ms is not None:
        result["elapsed_ms"] = elapsed_ms
    if action in {"launch", "halt"} and state == "recovery_required":
        result["recovery"] = {
            "status": _lane_command(lane, "status"),
            "halt_after_status": _lane_command(lane, "halt"),
        }
    return result


def _failure_state(action: str) -> str:
    return "recovery_required" if action in {"launch", "halt"} else "blocked"


def _success_output_error(
    lane: LanePlan,
    *,
    action: str,
    output: Mapping[str, Any],
) -> str | None:
    if output.get("session") != lane.session:
        return "controller_session_mismatch"
    if action == "launch":
        try:
            validate_sha256(
                output.get("instruction_policy_fingerprint"),
                "launch instruction policy fingerprint",
            )
            validate_sha256(
                output.get("effective_contract_fingerprint"),
                "launch effective contract fingerprint",
            )
        except ValidationError:
            return "controller_launch_result_invalid"
        if (
            output.get("state") != "ACTIVE"
            or not _attach_output_is_bound(lane, output)
            or type(output.get("attach_ticket_ttl_seconds")) is not int
            or output["attach_ticket_ttl_seconds"] <= 0
        ):
            return "controller_launch_result_invalid"
    elif action == "status":
        if (
            output.get("target") != lane.target
            or output.get("controller") != lane.contract.controller
            or output.get("session_profile") != lane.contract.session_profile
            or output.get("repo") != str(lane.repository)
            or output.get("branch") != lane.contract.branch
            or output.get("mutation_owner") != lane.contract.mutation_owner
            or not isinstance(output.get("state"), str)
            or output.get("state") not in STATES
            or type(output.get("target_process_alive")) is not bool
            or type(output.get("tmux_alive")) is not bool
        ):
            return "controller_status_result_invalid"
    elif action == "attach":
        if (
            _view_ticket_path(lane, output.get("ticket_path")) is None
            or not _attach_output_is_bound(lane, output)
            or type(output.get("ticket_ttl_seconds")) is not int
            or output["ticket_ttl_seconds"] <= 0
            or output.get("read_only") is not True
            or output.get("execution_time_identity_check") is not True
        ):
            return "controller_attach_result_invalid"
    elif action == "view":
        if (
            output.get("read_only") is not True
            or output.get("native_tui") is not True
            or output.get("controller_attached") is not False
            or not isinstance(output.get("terminal_app"), str)
            or output.get("terminal_app") not in _TERMINAL_APPS
            or output.get("terminal_app_path")
            not in _TERMINAL_APPS[output["terminal_app"]]
            or output.get("open_request_submitted") is not True
            or output.get("viewer_attached") is not True
            or type(output.get("new_read_only_clients")) is not int
            or output["new_read_only_clients"] <= 0
            or output.get("ticket_revoked") is not True
        ):
            return "controller_view_result_invalid"
    elif action == "halt":
        if (
            output.get("state") != "HALTED"
            or output.get("tmux_preserved") is not True
            or type(output.get("signal_sent")) is not bool
        ):
            return "controller_halt_result_invalid"
    return None


def _view_ticket_path(lane: LanePlan, value: Any) -> Path | None:
    if not isinstance(value, str) or not value or len(value) > 4096:
        return None
    path = Path(value)
    if not path.is_absolute() or os.path.normpath(value) != value:
        return None
    expected_parent = lane.state_root.resolve(strict=True) / "views"
    if path.parent.resolve(strict=False) != expected_parent:
        return None
    prefix = lane.session + "-"
    if not path.name.startswith(prefix) or path.suffix != ".json":
        return None
    nonce = path.name[len(prefix) : -len(".json")]
    if len(nonce) != 32 or any(
        character not in "0123456789abcdef" for character in nonce
    ):
        return None
    return path


def _attach_output_is_bound(
    lane: LanePlan,
    output: Mapping[str, Any],
) -> bool:
    command = output.get("attach_command")
    if not isinstance(command, str) or not command or len(command) > 4096:
        return False
    try:
        argv = shlex.split(command)
    except ValueError:
        return False
    if len(argv) != 8:
        return False
    ticket_path = _view_ticket_path(lane, argv[7])
    recorded_ticket = output.get("ticket_path")
    if recorded_ticket is not None and recorded_ticket != argv[7]:
        return False
    expected_helper = (
        Path(__file__).resolve(strict=True).parent / "viewer_attach.py"
    ).resolve(strict=True)
    return (
        argv[0] == lane.controller["interpreter"]
        and argv[1] == str(expected_helper)
        and argv[2:7:2] == ["--state-root", "--session", "--ticket"]
        and argv[3] == str(lane.state_root.resolve(strict=True))
        and argv[5] == lane.session
        and ticket_path is not None
    )


def _project_status_blocker(
    lane: LanePlan,
    output: Mapping[str, Any],
) -> Dict[str, Any] | None:
    if "blocker" not in output:
        raise ValidationError("controller status blocker is missing")
    blocker = output.get("blocker")
    if blocker is None:
        return None
    expected_fields = {
        "code",
        "target_process_alive",
        "cleanup_stopped",
        "cleanup_error",
    }
    if (
        not isinstance(blocker, Mapping)
        or set(blocker) != expected_fields
        or blocker.get("code") != "launch_incomplete"
        or (
            blocker.get("target_process_alive") is not None
            and type(blocker.get("target_process_alive")) is not bool
        )
        or type(blocker.get("cleanup_stopped")) is not bool
        or (
            blocker.get("cleanup_error") is not None
            and not isinstance(blocker.get("cleanup_error"), str)
        )
        or (
            type(blocker.get("target_process_alive")) is bool
            and blocker["target_process_alive"]
            is not output.get("target_process_alive")
        )
    ):
        raise ValidationError("controller status blocker is invalid")
    dead_lease_candidate = (
        lane.target == "grok"
        and output.get("state") == "BLOCKED"
        and blocker["target_process_alive"] is False
        and blocker["cleanup_stopped"] is True
    )
    return {
        "code": "launch_incomplete",
        "target_process_alive": blocker["target_process_alive"],
        "cleanup_stopped": blocker["cleanup_stopped"],
        "cleanup_error_present": blocker["cleanup_error"] is not None,
        "dead_lease_reconciliation_candidate": dead_lease_candidate,
    }


def _project_success_output(
    lane: LanePlan,
    *,
    action: str,
    output: Mapping[str, Any],
) -> Dict[str, Any]:
    projected: Dict[str, Any] = {
        "ok": True,
        "session": lane.session,
    }
    if action == "launch":
        projected.update(
            {
                "state": "ACTIVE",
                "instruction_policy_fingerprint": output[
                    "instruction_policy_fingerprint"
                ],
                "effective_contract_fingerprint": output[
                    "effective_contract_fingerprint"
                ],
                "initial_attach_command_exposed": False,
                "fresh_viewer_result": "viewer.result",
            }
        )
    elif action == "status":
        blocker = _project_status_blocker(lane, output)
        projected.update(
            {
                "controller": lane.contract.controller,
                "target": lane.target,
                "session_profile": lane.contract.session_profile,
                "repo": str(lane.repository),
                "branch": lane.contract.branch,
                "mutation_owner": lane.contract.mutation_owner,
                "state": output["state"],
                "target_process_alive": output["target_process_alive"],
                "tmux_alive": output["tmux_alive"],
                "blocker": blocker,
            }
        )
    elif action == "attach":
        projected.update(
            {
                "attach_command": output["attach_command"],
                "ticket_path": output["ticket_path"],
                "ticket_ttl_seconds": output["ticket_ttl_seconds"],
                "read_only": True,
                "execution_time_identity_check": True,
            }
        )
    elif action == "view":
        projected.update(
            {
                "read_only": True,
                "native_tui": True,
                "controller_attached": False,
                "terminal_app": output["terminal_app"],
                "terminal_app_path": output["terminal_app_path"],
                "open_request_submitted": True,
                "viewer_attached": True,
                "new_read_only_clients": output["new_read_only_clients"],
                "ticket_revoked": True,
            }
        )
    elif action == "halt":
        projected.update(
            {
                "state": "HALTED",
                "signal_sent": output["signal_sent"],
                "tmux_preserved": True,
            }
        )
    return projected


def _recompile_launch_plan(lane: LanePlan) -> Dict[str, Any]:
    try:
        rebuilt = compile_operator_plan(
            contract_path=_artifact(lane.raw, "contract"),
            manifest_path=_artifact(lane.raw, "manifest"),
            authorization_path=_artifact(lane.raw, "authorization"),
            profile_root=lane.profile_root,
            prompt_path=_artifact(lane.raw, "input_payload"),
            session=lane.session,
            run_root=lane.run_root,
            repo=(
                lane.repository
                if lane.raw.get("entry_mode") == "cockpit_explicit"
                else None
            ),
            current_directory=lane.repository,
        )
    except PuppetError as exc:
        return _lane_failure(
            lane,
            action="launch",
            state="not_started",
            error=exc.category,
        )
    except Exception:
        return _lane_failure(
            lane,
            action="launch",
            state="not_started",
            error="operator_plan_recompile_failed",
        )
    if canonical_json_bytes(rebuilt) != canonical_json_bytes(lane.raw):
        return _lane_failure(
            lane,
            action="launch",
            state="not_started",
            error="operator_plan_stale",
        )
    if _lane_command(lane, "launch") is None:
        return _lane_failure(
            lane,
            action="launch",
            state="not_started",
            error="launch_unsupported",
        )
    return {
        "ok": True,
        "target": lane.target,
        "session": lane.session,
        "state": "preflight_ready",
    }


def _run_lane(
    lane: LanePlan,
    *,
    action: str,
    runner: Callable[[Sequence[str]], subprocess.CompletedProcess[bytes]],
) -> Dict[str, Any]:
    if _OPERATOR_INTERRUPT.is_set():
        return _lane_failure(
            lane,
            action=action,
            state="not_started",
            error="controller_cancelled",
        )
    command = _lane_command(lane, action)
    if command is None:
        return _lane_failure(
            lane,
            action=action,
            state="blocked",
            error="unsupported",
        )
    started = time.monotonic()
    try:
        completed = runner(command)
    except subprocess.TimeoutExpired:
        return _lane_failure(
            lane,
            action=action,
            state=_failure_state(action),
            error="controller_timeout",
            elapsed_ms=int((time.monotonic() - started) * 1000),
        )
    except Exception:
        return _lane_failure(
            lane,
            action=action,
            state=_failure_state(action),
            error="controller_invocation_failed",
        )
    elapsed_ms = int((time.monotonic() - started) * 1000)
    try:
        output = _safe_child_json(
            completed.stdout if completed.returncode == 0 else completed.stderr
        )
    except Exception:
        output = None
    if output is None:
        return _lane_failure(
            lane,
            action=action,
            state=_failure_state(action),
            error="controller_output_invalid",
            returncode=completed.returncode,
            elapsed_ms=elapsed_ms,
        )
    if completed.returncode != 0 or output.get("ok") is not True:
        error = output.get("error")
        if (
            not isinstance(error, str)
            or error not in _CONTROLLER_ERROR_CATEGORIES
        ):
            error = "controller_rejected"
        return _lane_failure(
            lane,
            action=action,
            state=_failure_state(action),
            error=error,
            returncode=completed.returncode,
            elapsed_ms=elapsed_ms,
        )
    try:
        output_error = _success_output_error(lane, action=action, output=output)
    except Exception:
        output_error = "controller_%s_result_invalid" % action
    if output_error is not None:
        return _lane_failure(
            lane,
            action=action,
            state=_failure_state(action),
            error=output_error,
            returncode=completed.returncode,
            elapsed_ms=elapsed_ms,
        )
    try:
        projected = _project_success_output(
            lane,
            action=action,
            output=output,
        )
    except Exception:
        return _lane_failure(
            lane,
            action=action,
            state=_failure_state(action),
            error="controller_%s_result_invalid" % action,
            returncode=completed.returncode,
            elapsed_ms=elapsed_ms,
        )
    return {
        "ok": True,
        "target": lane.target,
        "session": lane.session,
        "state": projected.get("state", "ready"),
        "elapsed_ms": elapsed_ms,
        "result": projected,
    }


def _resolve_lane_future(
    future: Any,
    lane: LanePlan,
    *,
    action: str,
    submitted: bool = True,
) -> Dict[str, Any]:
    try:
        result = future.result()
        if not isinstance(result, dict):
            raise TypeError("lane worker returned a non-object")
        return result
    except Exception:
        return _lane_failure(
            lane,
            action=action,
            state=(
                _failure_state(action)
                if submitted
                else "not_started"
            ),
            error="controller_worker_failed",
        )


def run_fanout(
    lanes: Sequence[LanePlan],
    *,
    action: str,
    runner: Callable[[Sequence[str]], subprocess.CompletedProcess[bytes]] = _default_runner,
    progress: Callable[[Mapping[str, Any]], None] | None = None,
    open_views: bool = False,
) -> Dict[str, Any]:
    if action not in _ACTION_KEYS:
        raise ValidationError("fanout action is unsupported")
    if open_views and action != "launch":
        raise ValidationError("open_views is available only with launch")
    if not lanes or len(lanes) > MAX_LANES:
        raise ValidationError("fanout lane count is invalid")
    progress_fn = progress or (lambda _event: None)
    started = time.monotonic()
    results: Dict[str, Dict[str, Any]] = {}
    viewer_action: str | None = None
    submit_actions = True
    if action == "launch":
        preflight: Dict[str, Dict[str, Any]] = {}
        with ThreadPoolExecutor(
            max_workers=len(lanes),
            thread_name_prefix="puppet-fanout-preflight",
        ) as executor:
            preflight_futures = {}
            for lane in lanes:
                progress_fn(
                    {
                        "schema": PROGRESS_SCHEMA,
                        "event": "lane_preflight_submitted",
                        "action": action,
                        "target": lane.target,
                        "session": lane.session,
                    }
                )
                preflight_futures[executor.submit(_recompile_launch_plan, lane)] = lane
            for future in as_completed(preflight_futures):
                lane = preflight_futures[future]
                result = _resolve_lane_future(
                    future,
                    lane,
                    action="launch",
                    submitted=False,
                )
                preflight[lane.target] = result
                progress_fn(
                    {
                        "schema": PROGRESS_SCHEMA,
                        "event": "lane_preflight_complete",
                        "action": action,
                        "target": lane.target,
                        "session": lane.session,
                        "ok": result["ok"],
                        "state": result["state"],
                    }
                )
        if any(result["ok"] is not True for result in preflight.values()):
            submit_actions = False
            for lane in lanes:
                result = preflight[lane.target]
                if result["ok"] is True:
                    result = _lane_failure(
                        lane,
                        action=action,
                        state="not_started",
                        error="peer_preflight_failed",
                    )
                results[lane.target] = result

    if submit_actions:
        with ThreadPoolExecutor(
            max_workers=len(lanes),
            thread_name_prefix="puppet-fanout",
        ) as executor:
            futures = {}
            for lane in lanes:
                progress_fn(
                    {
                        "schema": PROGRESS_SCHEMA,
                        "event": "lane_submitted",
                        "action": action,
                        "target": lane.target,
                        "session": lane.session,
                    }
                )
                futures[
                    executor.submit(_run_lane, lane, action=action, runner=runner)
                ] = lane
            for future in as_completed(futures):
                lane = futures[future]
                result = _resolve_lane_future(
                    future,
                    lane,
                    action=action,
                )
                results[lane.target] = result
                progress_fn(
                    {
                        "schema": PROGRESS_SCHEMA,
                        "event": "lane_complete",
                        "action": action,
                        "target": lane.target,
                        "session": lane.session,
                        "ok": result["ok"],
                        "state": result["state"],
                    }
                )

    if action in {"launch", "halt"} and submit_actions:
        uncertain = [
            lane
            for lane in lanes
            if results.get(lane.target, {}).get("ok") is not True
        ]
        if uncertain:
            with ThreadPoolExecutor(
                max_workers=len(uncertain),
                thread_name_prefix="puppet-fanout-reconcile",
            ) as executor:
                status_futures = {}
                for lane in uncertain:
                    progress_fn(
                        {
                            "schema": PROGRESS_SCHEMA,
                            "event": "lane_reconciliation_submitted",
                            "action": "status",
                            "target": lane.target,
                            "session": lane.session,
                        }
                    )
                    status_futures[
                        executor.submit(
                            _run_lane,
                            lane,
                            action="status",
                            runner=runner,
                        )
                    ] = lane
                for future in as_completed(status_futures):
                    lane = status_futures[future]
                    observed = _resolve_lane_future(
                        future,
                        lane,
                        action="status",
                    )
                    results[lane.target]["reconciliation"] = observed
                    progress_fn(
                        {
                            "schema": PROGRESS_SCHEMA,
                            "event": "lane_reconciliation_complete",
                            "action": "status",
                            "target": lane.target,
                            "session": lane.session,
                            "ok": observed["ok"],
                            "state": observed["state"],
                        }
                    )

    if action == "launch":
        active = [
            lane
            for lane in lanes
            if results.get(lane.target, {}).get("ok") is True
            and results[lane.target].get("state") == "ACTIVE"
        ]
        viewer_action = "view" if open_views else "attach"
        if active:
            with ThreadPoolExecutor(
                max_workers=len(active),
                thread_name_prefix="puppet-fanout-view",
            ) as executor:
                view_futures = {}
                for lane in active:
                    progress_fn(
                        {
                            "schema": PROGRESS_SCHEMA,
                            "event": "lane_viewer_submitted",
                            "action": viewer_action,
                            "target": lane.target,
                            "session": lane.session,
                        }
                    )
                    view_futures[
                        executor.submit(
                            _run_lane,
                            lane,
                            action=viewer_action,
                            runner=runner,
                        )
                    ] = lane
                for future in as_completed(view_futures):
                    lane = view_futures[future]
                    observed = _resolve_lane_future(
                        future,
                        lane,
                        action=viewer_action,
                    )
                    results[lane.target]["viewer"] = observed
                    progress_fn(
                        {
                            "schema": PROGRESS_SCHEMA,
                            "event": "lane_viewer_complete",
                            "action": viewer_action,
                            "target": lane.target,
                            "session": lane.session,
                            "ok": observed["ok"],
                            "state": observed["state"],
                        }
                    )

    ordered = {target: results[target] for target in sorted(results)}
    succeeded = [
        target for target, result in ordered.items() if result.get("ok") is True
    ]
    failed = [target for target in ordered if target not in succeeded]
    viewer_failed = [
        target
        for target, result in ordered.items()
        if isinstance(result.get("viewer"), Mapping)
        and result["viewer"].get("ok") is not True
    ]
    viewer_succeeded = [
        target
        for target, result in ordered.items()
        if isinstance(result.get("viewer"), Mapping)
        and result["viewer"].get("ok") is True
    ]
    plan_identities = {
        lane.target: {
            "path": str(lane.path),
            "file_sha256": lane.file_sha256,
            "plan_sha256": lane.plan_sha256,
        }
        for lane in lanes
    }
    plan_set_sha256 = sha256_bytes(canonical_json_bytes(plan_identities))
    complete = not failed and not viewer_failed
    return {
        "schema": RESULT_SCHEMA,
        "version": FANOUT_VERSION,
        "ok": complete,
        "partial": bool(succeeded and (failed or viewer_failed)),
        "action": action,
        "selected_targets": [lane.target for lane in lanes],
        "succeeded_targets": succeeded,
        "failed_targets": failed,
        "action_ok": not failed,
        "viewer_action": viewer_action,
        "viewer_succeeded_targets": viewer_succeeded,
        "viewer_failed_targets": viewer_failed,
        "elapsed_ms": int((time.monotonic() - started) * 1000),
        "controller": {
            "fanout_sha256": sha256_file(
                Path(__file__).resolve(strict=True),
                max_bytes=1024 * 1024,
            ),
            "adapter_implementation_sha256": lanes[0].controller[
                "adapter_implementation_sha256"
            ],
            "protocol_sha256": lanes[0].controller["protocol_sha256"],
            "cli_sha256": lanes[0].controller["cli_sha256"],
        },
        "plans": plan_identities,
        "plan_set_sha256": plan_set_sha256,
        "lanes": ordered,
        "automatic_requalification": False,
        "automatic_sibling_halt": False,
        "raw_output_retained": False,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="puppet-fanout",
        description=(
            "Run any selected mix of exact Puppet operator plans concurrently "
            "without changing adapter qualification authority."
        ),
    )
    parser.add_argument("--version", action="version", version=FANOUT_VERSION)
    commands = parser.add_subparsers(dest="action", required=True)
    for action in ("launch", "status", "attach", "view", "halt"):
        command = commands.add_parser(action)
        command.add_argument(
            "--plan",
            action="append",
            required=True,
            type=Path,
            help="exact controller-produced operator plan; repeat for each target",
        )
        if action == "launch":
            command.add_argument(
                "--allow-live-launch",
                action="store_true",
                help="confirm execution of the plans' existing YOLO launch commands",
            )
            command.add_argument(
                "--open-views",
                action="store_true",
                help="open read-only native TUI views after all launch results settle",
            )
    return parser


def _progress(event: Mapping[str, Any]) -> None:
    print(json.dumps(dict(event), sort_keys=True), file=sys.stderr, flush=True)


def _operator_sigint(_signum: int, _frame: Any) -> None:
    if _OPERATOR_INTERRUPT.is_set():
        return
    _OPERATOR_INTERRUPT.set()
    raise KeyboardInterrupt


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.action == "launch" and not args.allow_live_launch:
        error = ValidationError("launch fanout requires --allow-live-launch")
        print(json.dumps(error.as_dict(), sort_keys=True), file=sys.stderr)
        return 2
    installed_handler = threading.current_thread() is threading.main_thread()
    previous_sigint: Any = None
    _OPERATOR_INTERRUPT.clear()
    if installed_handler:
        previous_sigint = signal.signal(signal.SIGINT, _operator_sigint)
    lanes: list[LanePlan] = []
    try:
        lanes = load_lane_plans(args.plan)
        result = run_fanout(
            lanes,
            action=args.action,
            progress=_progress,
            open_views=getattr(args, "open_views", False),
        )
    except KeyboardInterrupt:
        recovery = {
            lane.target: {
                "session": lane.session,
                "status": _lane_command(lane, "status"),
                "halt_after_status": _lane_command(lane, "halt"),
            }
            for lane in lanes
        }
        print(
            json.dumps(
                {
                    "schema": RESULT_SCHEMA,
                    "version": FANOUT_VERSION,
                    "ok": False,
                    "error": "operator_interrupted",
                    "recovery_required": True,
                    "recovery": recovery,
                    "automatic_sibling_halt": False,
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 130
    except PuppetError as exc:
        print(json.dumps(exc.as_dict(), sort_keys=True), file=sys.stderr)
        return 2
    finally:
        if installed_handler:
            signal.signal(signal.SIGINT, previous_sigint)
        _OPERATOR_INTERRUPT.clear()
    print(json.dumps(result, sort_keys=True))
    if result["ok"]:
        return 0
    return 4 if result["partial"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
