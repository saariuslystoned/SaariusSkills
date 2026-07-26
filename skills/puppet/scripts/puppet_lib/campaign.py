"""Exact non-secret campaign authorization and process admission."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Optional

from .contracts import PROCESS_IDENTITY_FIELDS, TARGETS
from .errors import IdentityError, ValidationError
from .registry import (
    ExecTransitionSamplingError,
    ProcessExecutableUnavailable,
    darwin_process_inventory,
    darwin_process_text_vnodes,
    process_birth_identity,
    process_executable_identity,
    process_tree_alive,
    process_tree_identity,
)
from .safety import (
    FORBIDDEN_FIELD_PARTS,
    absolute_root,
    canonical_json_bytes,
    read_json,
    sha256_bytes,
    validate_bounded_json,
    validate_identifier,
    validate_sha1,
    validate_sha256,
)


MAX_GOAL_BYTES = 1024 * 1024
MAX_PROCESS_SNAPSHOT_BYTES = 4 * 1024 * 1024
MAX_PROCESS_SNAPSHOT_ROWS = 32768
MAX_PROCESS_ANCESTRY_NODES = 512
MAX_PROCESS_ANCESTRY_DEPTH = 64
MAX_PROCESS_EXECUTION_SELECTORS = 10
PROCESS_SELECTION_RETRY_DELAYS = (0.01, 0.05, 0.1)
_AGY_PROCESS_CANDIDATE_NAMES = frozenset({"agy"})
_GROK_PROCESS_CANDIDATE_NAMES = frozenset(
    {
        "grok",
        "grok-macos-aarch64",
        "grok-0.2.111-macos-aarch64",
    }
)


ALLOWED_ACTIONS = [
    "read",
    "test",
    "mutate_isolated_worktrees",
    "local_commit",
    "internal_between_session_promotion",
]

HARD_GATES = [
    "merge",
    "push",
    "pull_request_creation",
    "release",
    "deploy",
    "publish",
    "global_install",
    "external_send",
    "spend",
    "delete_or_archive",
    "account_or_security_change",
    "secret_or_auth_data_access",
    "interference_with_preexisting_processes_or_sessions",
]


def _assert_non_secret_shape(value: Any, path: str = "authorization") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = key.lower().replace("-", "_")
            if key != "protected_session" and any(
                part in normalized for part in FORBIDDEN_FIELD_PARTS
            ):
                raise ValidationError(
                    "campaign authorization contains a forbidden field: %s.%s"
                    % (path, key)
                )
            _assert_non_secret_shape(item, "%s.%s" % (path, key))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _assert_non_secret_shape(item, "%s[%d]" % (path, index))


def _validate_process_record(value: Any) -> Dict[str, Any]:
    if not isinstance(value, dict) or set(value) != PROCESS_IDENTITY_FIELDS:
        raise ValidationError("protected process identity fields do not match schema")
    if (
        value.get("identity_version") != 2
        or isinstance(value.get("pid"), bool)
        or not isinstance(value.get("pid"), int)
        or value["pid"] <= 1
        or not isinstance(value.get("start"), str)
        or not value["start"]
        or len(value["start"]) > 200
        or not isinstance(value.get("kernel_birth_id"), str)
        or not value["kernel_birth_id"]
        or len(value["kernel_birth_id"]) > 200
        or any(character in value["kernel_birth_id"] for character in "\x00\n\r")
        or not isinstance(value.get("command"), str)
        or not value["command"]
        or len(value["command"]) > 1000
        or not isinstance(value.get("executable_path"), str)
        or not Path(value["executable_path"]).is_absolute()
        or isinstance(value.get("device"), bool)
        or not isinstance(value.get("device"), int)
        or value["device"] < 0
        or isinstance(value.get("inode"), bool)
        or not isinstance(value.get("inode"), int)
        or value["inode"] < 0
    ):
        raise ValidationError("protected process identity is invalid")
    return value


def validate_campaign_authorization(
    path: Path,
    *,
    target: str,
    controller: Optional[str] = None,
    campaign_id: Optional[str] = None,
) -> Dict[str, Any]:
    if target not in TARGETS:
        raise ValidationError("target is outside the campaign allowlist")
    value = read_json(Path(path), max_bytes=65536)
    validate_bounded_json(value, max_depth=8, max_items=128, max_string=4096)
    _assert_non_secret_shape(value)
    required_fields = {
        "schema_version",
        "campaign_id",
        "operator_identity",
        "controller",
        "goal",
        "acknowledged_at",
        "authorization",
        "allowed_actions",
        "hard_gates",
    }
    if not isinstance(value, dict) or set(value) != required_fields:
        raise ValidationError("campaign authorization fields do not match schema")
    if value.get("schema_version") != 1:
        raise ValidationError("unsupported campaign authorization schema")
    validate_identifier(value.get("campaign_id"), "campaign id")
    validate_identifier(value.get("operator_identity"), "operator identity")
    validate_identifier(value.get("controller"), "campaign controller")
    if controller is not None and value["controller"] != controller:
        raise IdentityError("campaign authorization controller identity mismatch")
    if campaign_id is not None and value["campaign_id"] != campaign_id:
        raise IdentityError("campaign authorization identity mismatch")
    goal = value.get("goal")
    if not isinstance(goal, dict) or set(goal) != {
        "repository",
        "commit",
        "path",
        "sha256",
    }:
        raise ValidationError("campaign goal identity fields do not match schema")
    if not all(
        isinstance(goal.get(name), str) and goal[name] and len(goal[name]) <= 1000
        for name in ("repository", "path")
    ):
        raise ValidationError("campaign goal source identity is invalid")
    validate_sha1(goal.get("commit"))
    validate_sha256(goal.get("sha256"), "campaign goal")
    acknowledged = value.get("acknowledged_at")
    if not isinstance(acknowledged, str) or not acknowledged or len(acknowledged) > 80:
        raise ValidationError("campaign has no bounded local YOLO acknowledgement")
    authorization = value.get("authorization")
    required_authorization = {
        "harnesses",
        "trust_profile",
        "disable_harness_sandbox_where_exposed",
        "ordinary_configured_model_provider_traffic",
        "scope",
    }
    if not isinstance(authorization, dict) or set(authorization) not in (
        required_authorization,
        required_authorization | {"parallel_target_override"},
    ):
        raise ValidationError(
            "campaign execution authorization fields do not match schema"
        )
    if (
        authorization.get("trust_profile") != "unrestricted_required"
        or authorization.get("disable_harness_sandbox_where_exposed") is not True
        or authorization.get("ordinary_configured_model_provider_traffic") is not True
        or authorization.get("scope")
        != "bounded Puppet implementation and conformance campaign only"
    ):
        raise ValidationError("campaign execution scope is incomplete")
    harnesses = authorization.get("harnesses")
    if (
        not isinstance(harnesses, list)
        or len(harnesses) > len(TARGETS)
        or len(set(harnesses)) != len(harnesses)
        or target not in harnesses
        or not set(harnesses) <= set(TARGETS)
    ):
        raise ValidationError("target is outside the campaign authorization")
    if value.get("allowed_actions") != ALLOWED_ACTIONS:
        raise ValidationError("campaign allowed-action envelope changed")
    if value.get("hard_gates") != HARD_GATES:
        raise ValidationError("campaign hard-gate envelope changed")
    override = authorization.get("parallel_target_override")
    if override is not None:
        if not isinstance(override, dict) or set(override) != {
            "target",
            "isolation",
            "failure_cleanup_scope",
            "protected_session",
            "protected_processes",
        }:
            raise ValidationError("parallel target override fields do not match schema")
        validate_identifier(override.get("protected_session"), "protected session")
        protected = override.get("protected_processes")
        if not isinstance(protected, list) or not protected or len(protected) > 32:
            raise ValidationError("parallel target override process set is invalid")
        records = [_validate_process_record(item) for item in protected]
        pids = [item["pid"] for item in records]
        if len(pids) != len(set(pids)) or pids != sorted(pids):
            raise ValidationError("parallel target override process order is invalid")
    return value


def _git(repo: Path, arguments: list[str]) -> subprocess.CompletedProcess:
    result = subprocess.run(
        ["git", "-C", str(repo), *arguments],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise IdentityError("campaign goal git identity is unavailable")
    return result


def verify_campaign_goal(
    authorization: Dict[str, Any],
    *,
    repo_root: Path,
    expected_campaign_id: str,
    expected_goal: Dict[str, str],
) -> Dict[str, Any]:
    """Resolve and hash the exact separately supplied campaign goal tuple."""
    validate_identifier(expected_campaign_id, "expected campaign id")
    if authorization.get("campaign_id") != expected_campaign_id:
        raise IdentityError("campaign authorization identity mismatch")
    goal = authorization.get("goal")
    required = {"repository", "commit", "path", "sha256"}
    if not isinstance(expected_goal, dict) or set(expected_goal) != required:
        raise ValidationError("expected campaign goal fields do not match schema")
    if goal != expected_goal:
        raise IdentityError("campaign authorization goal identity mismatch")
    validate_sha1(expected_goal.get("commit"), "expected goal commit")
    validate_sha256(expected_goal.get("sha256"), "expected campaign goal")
    for name in ("repository", "path"):
        if (
            not isinstance(expected_goal.get(name), str)
            or not expected_goal[name]
            or len(expected_goal[name]) > 1000
        ):
            raise ValidationError("expected campaign goal source identity is invalid")
    relative = PurePosixPath(expected_goal["path"])
    if (
        relative.is_absolute()
        or ".." in relative.parts
        or not relative.parts
        or expected_goal["path"].startswith(".")
        or "\\" in expected_goal["path"]
    ):
        raise ValidationError("campaign goal path is invalid")
    repo = absolute_root(str(repo_root), "campaign goal repository")
    top = Path(
        _git(repo, ["rev-parse", "--show-toplevel"])
        .stdout.decode("utf-8", errors="strict")
        .strip()
    ).resolve(strict=True)
    if top != repo:
        raise IdentityError("campaign goal repository root is ambiguous")
    commit = (
        _git(repo, ["rev-parse", "%s^{commit}" % expected_goal["commit"]])
        .stdout.decode("ascii", errors="strict")
        .strip()
    )
    if commit != expected_goal["commit"]:
        raise IdentityError("campaign goal commit identity mismatch")
    object_name = "%s:%s" % (commit, expected_goal["path"])
    size_text = (
        _git(repo, ["cat-file", "-s", object_name])
        .stdout.decode("ascii", errors="strict")
        .strip()
    )
    try:
        size = int(size_text)
    except ValueError as exc:
        raise IdentityError("campaign goal blob size is invalid") from exc
    if size <= 0 or size > MAX_GOAL_BYTES:
        raise ValidationError("campaign goal blob exceeds the size bound")
    content = _git(repo, ["cat-file", "blob", object_name]).stdout
    if len(content) != size:
        raise IdentityError("campaign goal blob size changed during verification")
    observed_sha = sha256_bytes(content)
    if observed_sha != expected_goal["sha256"]:
        raise IdentityError("campaign goal content fingerprint mismatch")
    return {
        "repository_root": str(repo),
        "campaign_id": expected_campaign_id,
        "goal": dict(expected_goal),
        "goal_fingerprint": sha256_bytes(canonical_json_bytes(expected_goal)),
        "content_sha256": observed_sha,
        "content_bytes": size,
    }


def _target_process_selectors(
    target: str, execution_files: Optional[list[Dict[str, Any]]]
) -> tuple[set[str], set[tuple[str, int, int]]]:
    expected = {
        "agy": {"agy"},
        # ``cursor agent`` retains the lowercase ``cursor`` executable name.
        # Treat that CLI process conservatively as a target without reading or
        # recording its argv, which may contain user content.
        "cursor": {"cursor-agent", "cursor"},
        "claude": {"claude"},
        "codex": {"codex"},
        "grok": {"grok"},
    }[target]
    if execution_files is None:
        return expected, set()
    if (
        not isinstance(execution_files, list)
        or not 1 <= len(execution_files) <= MAX_PROCESS_EXECUTION_SELECTORS
    ):
        raise ValidationError("target execution selectors are invalid")
    identities: set[tuple[str, int, int]] = set()
    for item in execution_files:
        if (
            not isinstance(item, dict)
            or set(item) != {"path", "device", "inode"}
            or not isinstance(item.get("path"), str)
            or not Path(item["path"]).is_absolute()
            or isinstance(item.get("device"), bool)
            or not isinstance(item.get("device"), int)
            or item["device"] <= 0
            or isinstance(item.get("inode"), bool)
            or not isinstance(item.get("inode"), int)
            or item["inode"] <= 0
        ):
            raise ValidationError("target execution selector is invalid")
        identity = (item["path"], item["device"], item["inode"])
        if identity in identities:
            raise ValidationError("target execution selectors contain duplicates")
        identities.add(identity)
        expected.add(Path(item["path"]).name)
    return expected, identities


def _matches_execution_selector(
    process: Dict[str, Any], selectors: set[tuple[str, int, int]]
) -> bool:
    return (
        not selectors
        or (process["executable_path"], process["device"], process["inode"])
        in selectors
    )


def _pid_still_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _target_process_rows(
    expected: set[str],
    selectors: set[tuple[str, int, int]],
    *,
    error_prefix: str,
) -> list[tuple[int, Optional[str]]]:
    if sys.platform == "darwin":
        inventory = darwin_process_inventory(max_processes=MAX_PROCESS_SNAPSHOT_ROWS)
        rows: list[tuple[int, Optional[str]]] = []
        for record in inventory:
            names = {
                Path(value).name
                for value in (
                    record.get("name"),
                    record.get("comm"),
                    record.get("command"),
                )
                if isinstance(value, str) and value
            }
            if names & expected:
                rows.append((record["pid"], record["command"]))
        return rows
    result = subprocess.run(
        ["ps", "-axo", "pid=,uid=,comm="],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise IdentityError("%s is unavailable" % error_prefix)
    if len(result.stdout.encode("utf-8")) > MAX_PROCESS_SNAPSHOT_BYTES:
        raise IdentityError("%s exceeds the byte bound" % error_prefix)
    lines = result.stdout.splitlines()
    if len(lines) > MAX_PROCESS_SNAPSHOT_ROWS:
        raise IdentityError("%s exceeds the row bound" % error_prefix)
    observed_pids = set()
    rows: list[tuple[int, Optional[str]]] = []
    for line in lines:
        fields = line.strip().split(maxsplit=2)
        if len(fields) < 2:
            continue
        try:
            pid = int(fields[0])
            uid = int(fields[1])
        except ValueError as exc:
            raise IdentityError("%s is ambiguous" % error_prefix) from exc
        if pid <= 0 or pid in observed_pids or uid < 0:
            raise IdentityError("%s contains an invalid PID" % error_prefix)
        observed_pids.add(pid)
        if pid == 1:
            continue
        command = fields[2] if len(fields) == 3 else None
        if (
            uid == os.getuid()
            and command is not None
            and Path(command).name in expected
        ):
            rows.append((pid, command))
    return rows


def _selected_process_identity(
    pid: int, selectors: set[tuple[str, int, int]]
) -> Optional[Dict[str, Any]]:
    unavailable: Optional[ProcessExecutableUnavailable] = None
    for delay in (0.0, *PROCESS_SELECTION_RETRY_DELAYS):
        if delay:
            time.sleep(delay)
        try:
            executable = process_executable_identity(pid)
            break
        except ExecTransitionSamplingError:
            raise
        except ProcessExecutableUnavailable as exc:
            unavailable = exc
            if not _pid_still_exists(pid):
                return None
        except IdentityError:
            if not _pid_still_exists(pid):
                return None
            raise
    else:
        if not _pid_still_exists(pid):
            return None
        if sys.platform == "darwin":
            text_vnodes = darwin_process_text_vnodes(pid)
            observed_vnodes = {
                (
                    item["executable_path"],
                    item["device"],
                    item["inode"],
                )
                for item in text_vnodes
            }
            if observed_vnodes.isdisjoint(selectors):
                return None
        raise IdentityError(
            "same-target executable identity is unavailable for a live PID"
        ) from unavailable
    observed = (
        executable["executable_path"],
        executable["device"],
        executable["inode"],
    )
    if observed not in selectors:
        return None
    try:
        process = process_birth_identity(pid)
    except IdentityError:
        if not _pid_still_exists(pid):
            return None
        raise
    if process["kernel_birth_id"] != executable[
        "kernel_birth_id"
    ] or not _matches_execution_selector(process, selectors):
        raise IdentityError("same-target process changed during exact selection")
    return process


def active_target_processes(
    target: str, execution_files: Optional[list[Dict[str, Any]]] = None
) -> list[Dict[str, Any]]:
    expected, selectors = _target_process_selectors(target, execution_files)
    rows = _target_process_rows(
        expected,
        selectors,
        error_prefix="same-target process inventory",
    )
    processes = []
    for pid, command in sorted(rows):
        if selectors:
            process = _selected_process_identity(pid, selectors)
            if process is not None:
                processes.append(process)
        else:
            process = process_birth_identity(pid)
            if process["command"] != command:
                raise IdentityError("same-target process changed during the inventory")
            processes.append(process)
    return processes


def agy_process_population(
    runtime_selector: Dict[str, Any],
) -> Dict[str, list[Dict[str, Any]]]:
    """Return AGY candidates split by exact current-runtime identity.

    The fixed candidate name keeps this census independent from caller-supplied
    execution basenames. Every same-name current-UID process is retained before
    exact path/device/inode classification, so another AGY build cannot appear
    absent merely because its vnode differs from the current 1.1.5 manifest.
    """

    _, selectors = _target_process_selectors("agy", [runtime_selector])
    rows = _target_process_rows(
        set(_AGY_PROCESS_CANDIDATE_NAMES),
        set(),
        error_prefix="AGY candidate process inventory",
    )
    candidates = []
    for pid, command in sorted(rows):
        try:
            process = process_birth_identity(pid)
        except ExecTransitionSamplingError:
            raise
        except IdentityError:
            if not _pid_still_exists(pid):
                continue
            raise
        if process["command"] != command:
            raise IdentityError("AGY candidate changed during the inventory")
        candidates.append(process)
    matching = [
        process
        for process in candidates
        if _matches_execution_selector(process, selectors)
    ]
    mismatched = [
        process
        for process in candidates
        if not _matches_execution_selector(process, selectors)
    ]
    return {
        "candidates": sorted(candidates, key=lambda item: item["pid"]),
        "matching": sorted(matching, key=lambda item: item["pid"]),
        "mismatched": sorted(mismatched, key=lambda item: item["pid"]),
    }


def grok_process_population(
    runtime_selector: Dict[str, Any],
) -> Dict[str, list[Dict[str, Any]]]:
    """Return the argv-free Grok population split by exact executable identity.

    Unlike ``active_target_processes``, this keeps same-name candidates whose
    mapped executable is not the current manifest's final runtime. Normal Grok
    sessions use the mismatched set as a hard no-interference blocker instead
    of silently treating another version or vnode as absent. Candidate names
    are fixed, and launcher or transient roles never gain matching authority.
    """

    _, selectors = _target_process_selectors("grok", [runtime_selector])
    rows = _target_process_rows(
        set(_GROK_PROCESS_CANDIDATE_NAMES),
        set(),
        error_prefix="Grok candidate process inventory",
    )
    candidates = []
    for pid, command in sorted(rows):
        try:
            process = process_birth_identity(pid)
        except ExecTransitionSamplingError:
            raise
        except IdentityError:
            if not _pid_still_exists(pid):
                continue
            raise
        if process["command"] != command:
            raise IdentityError("Grok candidate changed during the inventory")
        candidates.append(process)
    matching = [
        process
        for process in candidates
        if _matches_execution_selector(process, selectors)
    ]
    mismatched = [
        process
        for process in candidates
        if not _matches_execution_selector(process, selectors)
    ]
    return {
        "candidates": sorted(candidates, key=lambda item: item["pid"]),
        "matching": sorted(matching, key=lambda item: item["pid"]),
        "mismatched": sorted(mismatched, key=lambda item: item["pid"]),
    }


def target_process_snapshot(
    target: str, execution_files: Optional[list[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """Return a bounded argv-free, kernel-bound target ancestry snapshot."""

    expected, selectors = _target_process_selectors(target, execution_files)
    target_rows = _target_process_rows(
        expected,
        selectors,
        error_prefix="process-tree snapshot",
    )
    processes = []
    ancestry_nodes: Dict[int, Dict[str, Any]] = {}
    for pid, command in sorted(target_rows):
        selected = None
        if selectors:
            selected = _selected_process_identity(pid, selectors)
            if selected is None:
                continue
        node = process_tree_identity(pid)
        if selectors and node["process"] != selected:
            raise IdentityError("same-target process changed during exact snapshot")
        if not selectors and node["process"]["command"] != command:
            raise IdentityError("same-target process changed during the snapshot")
        processes.append(node["process"])
        for _ in range(MAX_PROCESS_ANCESTRY_DEPTH):
            node_pid = node["process"]["pid"]
            existing = ancestry_nodes.get(node_pid)
            if existing is not None and existing != node:
                raise IdentityError("process ancestry node changed during the snapshot")
            ancestry_nodes[node_pid] = node
            if len(ancestry_nodes) > MAX_PROCESS_ANCESTRY_NODES:
                raise IdentityError("process ancestry exceeds the node bound")
            parent_pid = node["parent_pid"]
            if parent_pid <= 1:
                break
            node = process_tree_identity(parent_pid)
        else:
            raise IdentityError("process ancestry exceeds the depth bound")
    for node in ancestry_nodes.values():
        if not process_tree_alive(node):
            raise IdentityError("process ancestry changed during revalidation")
    return {
        "processes": sorted(processes, key=lambda item: item["pid"]),
        "ancestry_nodes": sorted(
            ancestry_nodes.values(), key=lambda item: item["process"]["pid"]
        ),
    }


def parallel_target_override(
    authorization: Dict[str, Any], target: str, active: list[Dict[str, Any]]
) -> bool:
    override = authorization.get("authorization", {}).get("parallel_target_override")
    if not isinstance(override, dict) or override.get("target") != target:
        return False
    if override.get("isolation") != "unique_private_tmux_socket_and_session":
        return False
    if override.get("failure_cleanup_scope") != "exact_new_target_only":
        return False
    protected = override.get("protected_processes")
    if not isinstance(protected, list):
        return False
    return sorted(protected, key=lambda item: item["pid"]) == sorted(
        active, key=lambda item: item["pid"]
    )
