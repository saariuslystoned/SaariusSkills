#!/usr/bin/env python3
"""Prepare and run an explicit warm Puppet harness mix from one request."""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import math
import os
import shutil
import stat
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Mapping, Sequence

import puppet_fanout
from puppet_lib.adapter_manifest import AdapterManifest
from puppet_lib.adapters import adapter_for
from puppet_lib.campaign import validate_campaign_authorization
from puppet_lib.census import adapter_implementation_fingerprint
from puppet_lib.contracts import MANDATORY_HARD_GATES
from puppet_lib.errors import IdentityError, PuppetError, UnsupportedError, ValidationError
from puppet_lib.handoffs import (
    HANDOFF_SCHEMA_VERSION,
    MAX_HANDOFF_BYTES,
    PROTOCOL_FINGERPRINT,
    SOURCE_FIELDS,
)
from puppet_lib.operator_plan import compile_operator_plan
from puppet_lib.safety import (
    canonical_json_bytes,
    paths_overlap,
    read_json,
    sha256_bytes,
    sha256_file,
    validate_bounded_json,
    validate_branch,
    validate_identifier,
    validate_sha1,
    validate_sha256,
)
from puppet_lib.state import STATES


LAUNCHER_VERSION = "0.2.0"
CATALOG_SCHEMA = "puppet.warm-catalog/v1"
CAMPAIGN_SCHEMA = "puppet.launch-campaign/v1"
PROGRESS_SCHEMA = "puppet.launch-progress/v1"
CHECKPOINT_ASSIGNMENT_SCHEMA = "puppet.launch-checkpoint-assignment/v1"
CHECKPOINT_DELIVERY_SCHEMA = "puppet.launch-checkpoint-delivery/v1"
CHECKPOINT_RESULT_SCHEMA = "puppet.launch-checkpoint-result/v1"
TARGET_ORDER = ("agy", "codex", "claude", "cursor", "grok")
TARGETS = frozenset(TARGET_ORDER)
MAX_ARTIFACT_BYTES = 1024 * 1024
MAX_GIT_OUTPUT_BYTES = 64 * 1024
GIT_TIMEOUT_SECONDS = 30.0
PRIVATE_DIRECTORY_MODE = 0o700
PRIVATE_FILE_MODE = 0o600
MAX_CHECKPOINT_TIMEOUT_SECONDS = 300.0
CHECKPOINT_POLL_INTERVAL_SECONDS = 0.25
CHECKPOINT_STABLE_SAMPLES = 2


def _progress(phase: str, **fields: Any) -> None:
    print(
        json.dumps(
            {
                "schema": PROGRESS_SCHEMA,
                "version": LAUNCHER_VERSION,
                "phase": phase,
                **fields,
            },
            sort_keys=True,
        ),
        file=sys.stderr,
        flush=True,
    )


def _absolute_path(
    value: Path | str,
    *,
    label: str,
    must_exist: bool = True,
) -> Path:
    try:
        raw = os.fspath(value)
    except TypeError as exc:
        raise ValidationError("%s must be a filesystem path" % label) from exc
    if (
        not isinstance(raw, str)
        or not raw
        or "\x00" in raw
        or len(raw) > 4096
        or not os.path.isabs(raw)
        or os.path.normpath(raw) != raw
    ):
        raise ValidationError("%s must be a normalized absolute path" % label)
    path = Path(raw)
    if must_exist:
        try:
            resolved = path.resolve(strict=True)
        except OSError as exc:
            raise ValidationError("%s is unavailable" % label) from exc
        if resolved != path:
            raise IdentityError("%s must not traverse a symlink" % label)
        return resolved
    try:
        parent = path.parent.resolve(strict=True)
    except OSError as exc:
        raise ValidationError("%s parent is unavailable" % label) from exc
    if parent != path.parent:
        raise IdentityError("%s parent must not traverse a symlink" % label)
    return parent / path.name


def _real_directory(
    value: Path | str,
    *,
    label: str,
    private: bool = False,
) -> Path:
    path = _absolute_path(value, label=label)
    try:
        lexical = os.lstat(path)
    except OSError as exc:
        raise ValidationError("%s is unavailable" % label) from exc
    if stat.S_ISLNK(lexical.st_mode) or not stat.S_ISDIR(lexical.st_mode):
        raise ValidationError("%s must be a real directory" % label)
    if lexical.st_uid != os.getuid():
        raise IdentityError("%s must be owned by the current UID" % label)
    if private and stat.S_IMODE(lexical.st_mode) != PRIVATE_DIRECTORY_MODE:
        raise IdentityError("%s must be current-UID 0700" % label)
    return path


def _future_path(value: Path | str, *, label: str) -> Path:
    path = _absolute_path(value, label=label, must_exist=False)
    try:
        os.lstat(path)
    except FileNotFoundError:
        return path
    except OSError as exc:
        raise ValidationError("%s cannot be inspected" % label) from exc
    raise ValidationError("%s already exists" % label)


def _artifact(value: Path | str, *, label: str) -> Dict[str, Any]:
    path = _absolute_path(value, label=label)
    try:
        lexical = os.lstat(path)
    except OSError as exc:
        raise ValidationError("%s is unavailable" % label) from exc
    if stat.S_ISLNK(lexical.st_mode) or not stat.S_ISREG(lexical.st_mode):
        raise ValidationError("%s must be a regular non-symlink file" % label)
    if lexical.st_size > MAX_ARTIFACT_BYTES:
        raise ValidationError("%s exceeds the launcher size bound" % label)
    return {
        "path": str(path),
        "sha256": sha256_file(path, max_bytes=MAX_ARTIFACT_BYTES),
        "bytes": lexical.st_size,
    }


def _create_private_directory(path: Path) -> None:
    try:
        path.mkdir(mode=PRIVATE_DIRECTORY_MODE)
    except OSError as exc:
        raise ValidationError("private campaign directory could not be created") from exc
    path.chmod(PRIVATE_DIRECTORY_MODE)


def _create_only_json(path: Path, value: Mapping[str, Any]) -> None:
    payload = canonical_json_bytes(dict(value)) + b"\n"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags, PRIVATE_FILE_MODE)
    except OSError as exc:
        raise ValidationError("create-only JSON artifact could not be published") from exc
    try:
        offset = 0
        while offset < len(payload):
            written = os.write(descriptor, payload[offset:])
            if written <= 0:
                raise OSError("short write")
            offset += written
        os.fsync(descriptor)
    except OSError as exc:
        raise ValidationError("create-only JSON artifact could not be written") from exc
    finally:
        os.close(descriptor)


def _replace_json(path: Path, value: Mapping[str, Any]) -> None:
    payload = canonical_json_bytes(dict(value)) + b"\n"
    temporary = path.with_name(".%s.%d.tmp" % (path.name, os.getpid()))
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(temporary, flags, PRIVATE_FILE_MODE)
    except OSError as exc:
        raise ValidationError("campaign state could not be staged") from exc
    try:
        offset = 0
        while offset < len(payload):
            written = os.write(descriptor, payload[offset:])
            if written <= 0:
                raise OSError("short write")
            offset += written
        os.fsync(descriptor)
    except OSError as exc:
        raise ValidationError("campaign state could not be written") from exc
    finally:
        os.close(descriptor)
    try:
        os.replace(temporary, path)
    except OSError as exc:
        raise ValidationError("campaign state could not be published") from exc


def _git_executable() -> Path:
    candidate = shutil.which("git", path="/usr/bin:/bin:/usr/local/bin")
    if not candidate:
        raise UnsupportedError("git is unavailable")
    resolved = Path(candidate).resolve(strict=True)
    if not resolved.is_file() or resolved.is_symlink():
        raise IdentityError("git executable identity is invalid")
    return resolved


def _git_environment() -> Dict[str, str]:
    return {
        "PATH": "/usr/bin:/bin:/usr/local/bin",
        "LC_ALL": "C",
        "LANG": "C",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_OPTIONAL_LOCKS": "0",
    }


def _git(
    git: Path,
    repo: Path,
    arguments: Sequence[str],
    *,
    allow_failure: bool = False,
) -> subprocess.CompletedProcess[bytes]:
    try:
        result = subprocess.run(
            [
                str(git),
                "-c",
                "core.fsmonitor=false",
                "-C",
                str(repo),
                *arguments,
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=_git_environment(),
            timeout=GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValidationError("repository operation failed") from exc
    if (
        len(result.stdout) > MAX_GIT_OUTPUT_BYTES
        or len(result.stderr) > MAX_GIT_OUTPUT_BYTES
    ):
        raise ValidationError("repository operation exceeded its output bound")
    if result.returncode != 0 and not allow_failure:
        raise ValidationError("repository operation failed")
    return result


def _git_text(git: Path, repo: Path, arguments: Sequence[str]) -> str:
    result = _git(git, repo, arguments)
    try:
        return result.stdout.decode("utf-8").strip()
    except UnicodeDecodeError as exc:
        raise ValidationError("repository output is not UTF-8") from exc


def _source_identity(repo_value: Path | str, commit_value: str) -> Dict[str, Any]:
    repo = _real_directory(repo_value, label="source repository")
    git = _git_executable()
    top = Path(_git_text(git, repo, ["rev-parse", "--show-toplevel"])).resolve(
        strict=True
    )
    if top != repo:
        raise IdentityError("source repository is not its exact Git root")
    commit = validate_sha1(commit_value, "source commit")
    if _git_text(git, repo, ["rev-parse", "HEAD"]) != commit:
        raise IdentityError("source repository HEAD differs from the requested commit")
    if _git_text(git, repo, ["status", "--porcelain=v1", "--untracked-files=normal"]):
        raise IdentityError("source repository must be clean at the requested commit")
    if (
        _git(git, repo, ["cat-file", "-e", "%s^{commit}" % commit], allow_failure=True)
        .returncode
        != 0
    ):
        raise IdentityError("source commit is unavailable")
    branch = validate_branch(
        _git_text(git, repo, ["symbolic-ref", "--quiet", "--short", "HEAD"])
    )
    tree = validate_sha1(
        _git_text(git, repo, ["rev-parse", "%s^{tree}" % commit]),
        "source tree",
    )
    common = Path(
        _git_text(git, repo, ["rev-parse", "--git-common-dir"])
    )
    if not common.is_absolute():
        common = repo / common
    common = common.resolve(strict=True)
    return {
        "repo": str(repo),
        "branch": branch,
        "commit": commit,
        "tree": tree,
        "git_common_dir": str(common),
        "git_executable": str(git),
        "git_executable_sha256": sha256_file(git),
    }


def _validate_executing_controller(
    source: Mapping[str, Any],
    *,
    controller_paths: Sequence[Path | str] | None = None,
) -> Dict[str, Any]:
    """Bind the executing controller to the exact clean supervisor worktree."""

    source_root = _real_directory(
        source.get("repo", ""),
        label="controller supervisor root",
    )
    git = _absolute_path(
        source.get("git_executable", ""),
        label="controller Git executable",
    )
    if sha256_file(git) != validate_sha256(
        source.get("git_executable_sha256"),
        "controller Git executable",
    ):
        raise IdentityError("controller Git executable changed")

    selected = (
        controller_paths
        if controller_paths is not None
        else (
            Path(os.path.abspath(__file__)),
            Path(os.path.abspath(puppet_fanout.__file__)),
            Path(os.path.abspath(__file__)).with_name("puppet.py"),
        )
    )
    if not selected:
        raise ValidationError("executing controller file set is empty")
    runtime_paths: list[Path] = []
    for index, value in enumerate(selected):
        path = _absolute_path(
            Path(os.path.abspath(os.fspath(value))),
            label="executing controller file %d" % (index + 1),
        )
        try:
            details = os.lstat(path)
        except OSError as exc:
            raise ValidationError("executing controller file is unavailable") from exc
        if stat.S_ISLNK(details.st_mode) or not stat.S_ISREG(details.st_mode):
            raise ValidationError(
                "executing controller files must be regular non-symlink files"
            )
        if details.st_uid != os.getuid():
            raise IdentityError("executing controller file has another owner")
        runtime_paths.append(path)
    if len(set(runtime_paths)) != len(runtime_paths):
        raise ValidationError("executing controller file set is duplicated")

    try:
        discovered_root = _real_directory(
            _git_text(
                git,
                runtime_paths[0].parent,
                ["rev-parse", "--show-toplevel"],
            ),
            label="executing controller Git root",
        )
    except ValidationError as exc:
        raise IdentityError(
            "executing controller is not inside a Git worktree"
        ) from exc
    if discovered_root != source_root:
        raise IdentityError(
            "executing controller Git root differs from the supervisor root"
        )

    head = validate_sha1(
        _git_text(git, discovered_root, ["rev-parse", "HEAD"]),
        "executing controller head",
    )
    if head != validate_sha1(source.get("commit"), "controller source commit"):
        raise IdentityError("executing controller HEAD differs from the source commit")
    tree = validate_sha1(
        _git_text(git, discovered_root, ["rev-parse", "HEAD^{tree}"]),
        "executing controller tree",
    )
    if tree != validate_sha1(source.get("tree"), "controller source tree"):
        raise IdentityError("executing controller tree differs from the source tree")
    branch = validate_branch(
        _git_text(
            git,
            discovered_root,
            ["symbolic-ref", "--quiet", "--short", "HEAD"],
        )
    )
    if branch != validate_branch(source.get("branch")):
        raise IdentityError("executing controller branch differs from the source branch")
    common = Path(
        _git_text(git, discovered_root, ["rev-parse", "--git-common-dir"])
    )
    if not common.is_absolute():
        common = discovered_root / common
    try:
        common = common.resolve(strict=True)
    except OSError as exc:
        raise ValidationError(
            "executing controller Git common directory is unavailable"
        ) from exc
    expected_common = _real_directory(
        source.get("git_common_dir", ""),
        label="controller Git common directory",
    )
    if common != expected_common:
        raise IdentityError(
            "executing controller Git common directory differs from the source"
        )

    relative_paths: list[str] = []
    for path in runtime_paths:
        try:
            relative = str(path.relative_to(discovered_root))
        except ValueError as exc:
            raise IdentityError(
                "executing controller file escapes the supervisor root"
            ) from exc
        tracked = _git(
            git,
            discovered_root,
            ["ls-files", "--error-unmatch", "--", relative],
            allow_failure=True,
        )
        if tracked.returncode != 0:
            raise IdentityError("executing controller file is not tracked")
        relative_paths.append(relative)
    if _git_text(
        git,
        discovered_root,
        ["status", "--porcelain=v1", "--untracked-files=all"],
    ):
        raise IdentityError("executing controller worktree is not clean")

    return {
        "root": str(discovered_root),
        "branch": branch,
        "commit": head,
        "tree": tree,
        "git_common_dir": str(common),
        "files": relative_paths,
    }


def _parse_target_assignments(
    values: Iterable[str],
    *,
    label: str,
) -> Dict[str, Path]:
    result: Dict[str, Path] = {}
    for value in values:
        if not isinstance(value, str) or value.count("=") != 1:
            raise ValidationError("%s must use target=/absolute/path" % label)
        target, raw_path = value.split("=", 1)
        if target not in TARGETS or target in result:
            raise ValidationError("%s target is invalid or duplicated" % label)
        result[target] = _absolute_path(raw_path, label="%s %s" % (target, label))
    return result


def _selected_targets(values: Iterable[str]) -> tuple[str, ...]:
    expanded: list[str] = []
    for value in values:
        if not isinstance(value, str):
            raise ValidationError("target selection is invalid")
        expanded.extend(item.strip() for item in value.split(",") if item.strip())
    if expanded == ["all"]:
        return TARGET_ORDER
    if "all" in expanded:
        raise ValidationError("all cannot be combined with another target")
    if (
        not expanded
        or len(expanded) > len(TARGET_ORDER)
        or len(set(expanded)) != len(expanded)
        or not set(expanded) <= TARGETS
    ):
        raise ValidationError("target selection is invalid or duplicated")
    return tuple(target for target in TARGET_ORDER if target in set(expanded))


def _catalog_unhashed(value: Mapping[str, Any]) -> Dict[str, Any]:
    result = dict(value)
    result.pop("catalog_sha256", None)
    return result


def _load_catalog(path_value: Path | str) -> Dict[str, Any]:
    path_artifact = _artifact(path_value, label="warm catalog")
    value = read_json(
        Path(path_artifact["path"]),
        max_bytes=MAX_ARTIFACT_BYTES,
        reject_sensitive_fields=True,
    )
    validate_bounded_json(
        value,
        max_depth=8,
        max_items=256,
        max_string=4096,
        reject_sensitive_fields=True,
    )
    if not isinstance(value, dict) or set(value) != {
        "schema",
        "version",
        "state",
        "controller",
        "authorization",
        "adapter_implementation_sha256",
        "protocol_sha256",
        "targets",
        "catalog_sha256",
    }:
        raise ValidationError("warm catalog fields are invalid")
    if (
        value.get("schema") != CATALOG_SCHEMA
        or value.get("version") != LAUNCHER_VERSION
        or value.get("state") != "warm"
    ):
        raise ValidationError("warm catalog schema or state is invalid")
    recorded = validate_sha256(value.get("catalog_sha256"), "warm catalog")
    if sha256_bytes(canonical_json_bytes(_catalog_unhashed(value))) != recorded:
        raise IdentityError("warm catalog fingerprint changed")
    if (
        value.get("adapter_implementation_sha256")
        != adapter_implementation_fingerprint()
        or value.get("protocol_sha256") != PROTOCOL_FINGERPRINT
    ):
        raise IdentityError("warm catalog controller identity changed")
    authorization = value.get("authorization")
    if not isinstance(authorization, dict) or set(authorization) != {
        "path",
        "sha256",
        "campaign_id",
        "goal_fingerprint",
    }:
        raise ValidationError("warm catalog authorization is invalid")
    authorization_artifact = _artifact(
        authorization.get("path"),
        label="catalog authorization",
    )
    if authorization_artifact["sha256"] != authorization.get("sha256"):
        raise IdentityError("warm catalog authorization changed")
    targets = value.get("targets")
    if (
        not isinstance(targets, dict)
        or not targets
        or not set(targets) <= TARGETS
    ):
        raise ValidationError("warm catalog targets are invalid")
    parsed_authorizations = {
        target: validate_campaign_authorization(
            Path(authorization_artifact["path"]),
            target=target,
            controller=value.get("controller"),
            campaign_id=authorization.get("campaign_id"),
        )
        for target in targets
    }
    goal_fingerprints = {
        sha256_bytes(canonical_json_bytes(item["goal"]))
        for item in parsed_authorizations.values()
    }
    if (
        len(goal_fingerprints) != 1
        or next(iter(goal_fingerprints)) != authorization.get("goal_fingerprint")
    ):
        raise IdentityError("warm catalog qualification goal changed")
    for target, lane in targets.items():
        if not isinstance(lane, dict) or set(lane) != {
            "manifest",
            "manifest_sha256",
            "manifest_fingerprint",
            "execution_fingerprint",
            "qualification_sha256",
            "profile_root",
        }:
            raise ValidationError("warm catalog lane fields are invalid")
        manifest_artifact = _artifact(
            lane.get("manifest"),
            label="%s catalog manifest" % target,
        )
        if manifest_artifact["sha256"] != lane.get("manifest_sha256"):
            raise IdentityError("%s catalog manifest changed" % target)
        manifest = AdapterManifest.from_path(Path(manifest_artifact["path"]))
        if (
            manifest.target != target
            or manifest.raw["doctor_only"] is not False
            or manifest.raw["qualification"] is None
            or manifest.raw["adapter_fingerprint"]
            != value["adapter_implementation_sha256"]
            or manifest.raw["protocol_fingerprint"] != value["protocol_sha256"]
            or manifest.fingerprint != lane.get("manifest_fingerprint")
            or manifest.execution_fingerprint != lane.get("execution_fingerprint")
        ):
            raise IdentityError("%s catalog manifest identity changed" % target)
        validate_sha256(
            lane.get("qualification_sha256"),
            "%s catalog qualification" % target,
        )
        profile_root = lane.get("profile_root")
        if target == "agy":
            if profile_root is not None:
                raise ValidationError("AGY catalog lane cannot select a profile")
        else:
            _real_directory(
                profile_root,
                label="%s catalog profile" % target,
                private=True,
            )
    return value


def initialize_catalog(
    *,
    output_path: Path | str,
    authorization_path: Path | str,
    manifest_assignments: Iterable[str],
    profile_assignments: Iterable[str],
) -> Dict[str, Any]:
    output = _future_path(output_path, label="warm catalog output")
    _real_directory(output.parent, label="warm catalog parent", private=True)
    authorization_artifact = _artifact(
        authorization_path,
        label="campaign authorization",
    )
    manifests = _parse_target_assignments(
        manifest_assignments,
        label="manifest assignment",
    )
    profiles = _parse_target_assignments(
        profile_assignments,
        label="profile assignment",
    )
    if not manifests:
        raise ValidationError("warm catalog requires at least one manifest")
    if set(profiles) != set(manifests) - {"agy"}:
        raise ValidationError("warm catalog profile assignments are incomplete")
    adapter_sha256 = adapter_implementation_fingerprint()
    authorization_by_target: Dict[str, Dict[str, Any]] = {}
    for target in manifests:
        authorization_by_target[target] = validate_campaign_authorization(
            Path(authorization_artifact["path"]),
            target=target,
        )
    controllers = {
        authorization["controller"] for authorization in authorization_by_target.values()
    }
    campaigns = {
        authorization["campaign_id"]
        for authorization in authorization_by_target.values()
    }
    goals = {
        sha256_bytes(canonical_json_bytes(authorization["goal"]))
        for authorization in authorization_by_target.values()
    }
    if len(controllers) != 1 or len(campaigns) != 1 or len(goals) != 1:
        raise IdentityError("catalog authorization authority is inconsistent")
    controller = next(iter(controllers))
    campaign_id = next(iter(campaigns))
    goal_fingerprint = next(iter(goals))

    parsed: Dict[str, AdapterManifest] = {}
    profile_roots: Dict[str, Path | None] = {}
    for target, path in manifests.items():
        manifest = AdapterManifest.from_path(path)
        if (
            manifest.target != target
            or manifest.raw["doctor_only"] is not False
            or manifest.raw["qualification"] is None
            or manifest.raw["adapter_fingerprint"] != adapter_sha256
            or manifest.raw["protocol_fingerprint"] != PROTOCOL_FINGERPRINT
        ):
            raise IdentityError("%s manifest is not current and qualified" % target)
        parsed[target] = manifest
        profile_roots[target] = (
            None
            if target == "agy"
            else _real_directory(
                profiles[target],
                label="%s profile root" % target,
                private=True,
            )
        )

    def verify_target(target: str) -> tuple[str, Dict[str, Any]]:
        manifest = parsed[target]
        qualification = manifest.verify_qualification(
            expected_controller=controller,
            expected_campaign_id=campaign_id,
            expected_goal_fingerprint=goal_fingerprint,
            expected_session_profile="regular",
        )
        qualified_profile = qualification.get("private_profile_root")
        if (
            target != "agy"
            and qualified_profile is not None
            and qualified_profile != str(profile_roots[target])
        ):
            raise IdentityError("%s qualified profile root changed" % target)
        return target, qualification

    qualifications: Dict[str, Dict[str, Any]] = {}
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=len(parsed),
        thread_name_prefix="puppet-catalog",
    ) as executor:
        futures = {
            executor.submit(verify_target, target): target for target in parsed
        }
        for future in concurrent.futures.as_completed(futures):
            target, qualification = future.result()
            qualifications[target] = qualification

    target_rows: Dict[str, Any] = {}
    for target in TARGET_ORDER:
        if target not in parsed:
            continue
        manifest_path = manifests[target]
        manifest = parsed[target]
        target_rows[target] = {
            "manifest": str(manifest_path),
            "manifest_sha256": sha256_file(
                manifest_path,
                max_bytes=MAX_ARTIFACT_BYTES,
            ),
            "manifest_fingerprint": manifest.fingerprint,
            "execution_fingerprint": manifest.execution_fingerprint,
            "qualification_sha256": sha256_bytes(
                canonical_json_bytes(qualifications[target])
            ),
            "profile_root": (
                str(profile_roots[target])
                if profile_roots[target] is not None
                else None
            ),
        }
    result: Dict[str, Any] = {
        "schema": CATALOG_SCHEMA,
        "version": LAUNCHER_VERSION,
        "state": "warm",
        "controller": controller,
        "authorization": {
            "path": authorization_artifact["path"],
            "sha256": authorization_artifact["sha256"],
            "campaign_id": campaign_id,
            "goal_fingerprint": goal_fingerprint,
        },
        "adapter_implementation_sha256": adapter_sha256,
        "protocol_sha256": PROTOCOL_FINGERPRINT,
        "targets": target_rows,
    }
    result["catalog_sha256"] = sha256_bytes(canonical_json_bytes(result))
    validate_bounded_json(
        result,
        max_depth=8,
        max_items=256,
        max_string=4096,
        reject_sensitive_fields=True,
    )
    _create_only_json(output, result)
    return result


def _branch_for(launch_id: str, target: str) -> str:
    return validate_branch("codex/puppet-%s-%s" % (launch_id, target))


def _session_for(launch_id: str, target: str) -> str:
    return validate_identifier("puppet-%s-%s" % (launch_id, target), "session")


def _run_id_for(launch_id: str, target: str) -> str:
    return validate_identifier("%s-%s" % (launch_id, target), "run id")


def _nonce_for(launch_id: str, target: str, prompt_sha256: str) -> str:
    digest = sha256_bytes(
        canonical_json_bytes(
            {
                "launch_id": launch_id,
                "target": target,
                "prompt_sha256": prompt_sha256,
            }
        )
    )
    return validate_identifier(
        "%s-%s" % (target, digest[:24]),
        "nonce",
    )


def _checkpoint_request_id(
    launch_id: str,
    target: str,
    plan_sha256: str,
) -> str:
    digest = sha256_bytes(
        canonical_json_bytes(
            {
                "launch_id": validate_identifier(launch_id, "launch id"),
                "target": target,
                "plan_sha256": validate_sha256(plan_sha256, "lane plan"),
                "operation": "source_checkpoint",
            }
        )
    )
    return validate_identifier(
        "checkpoint-%s-%s" % (target, digest[:24]),
        "checkpoint request id",
    )


def _checkpoint_fixed_fields(
    lane: puppet_fanout.LanePlan,
    manifest: AdapterManifest,
) -> Dict[str, Any]:
    if manifest.target != lane.target:
        raise IdentityError("checkpoint manifest target changed")
    return {
        "schema_version": HANDOFF_SCHEMA_VERSION,
        "checkpoint_kind": "source",
        "session": lane.session,
        "run_id": lane.contract.run_id,
        "nonce": lane.contract.nonce,
        "executable_fingerprint": manifest.raw["executable"]["sha256"],
        "execution_fingerprint": manifest.execution_fingerprint,
        "adapter_fingerprint": manifest.raw["adapter_fingerprint"],
        "protocol_fingerprint": manifest.raw["protocol_fingerprint"],
    }


def _checkpoint_assignment(
    *,
    launch_id: str,
    lane: puppet_fanout.LanePlan,
    manifest: AdapterManifest,
    output_path: Path,
) -> Dict[str, Any]:
    request_id = _checkpoint_request_id(
        launch_id,
        lane.target,
        lane.plan_sha256,
    )
    fixed_fields = _checkpoint_fixed_fields(lane, manifest)
    agent_fields = sorted(set(SOURCE_FIELDS) - set(fixed_fields))
    result = {
        "schema": CHECKPOINT_ASSIGNMENT_SCHEMA,
        "version": LAUNCHER_VERSION,
        "operation": "publish_source_checkpoint",
        "target": lane.target,
        "session": lane.session,
        "request_id": request_id,
        "output": {
            "path": str(output_path),
            "checkpoint_kind": "source",
            "schema_version": HANDOFF_SCHEMA_VERSION,
            "max_bytes": MAX_HANDOFF_BYTES,
            "write_policy": "atomic_create_only_mode_0600",
        },
        "handoff": {
            "exact_fields": sorted(SOURCE_FIELDS),
            "fixed_fields": fixed_fields,
            "agent_fields": agent_fields,
            "agent_field_constraints": {
                "candidate_commit": "exact current full 40-character lowercase Git HEAD",
                "timestamp": "RFC3339 timestamp with timezone",
                "summary": "nonempty string of at most 2000 characters",
                "claims": "list of at most 32 objects",
                "evidence_refs": (
                    "list of at most 32 relative-path strings, each at most "
                    "1000 characters"
                ),
                "decisions_requested": (
                    "list of at most 32 strings, each at most 1000 characters"
                ),
                "limitations": (
                    "list of at most 32 strings, each at most 1000 characters"
                ),
                "suggested_next_assignment": "string of at most 1000 characters",
            },
        },
        "instructions": [
            "Finish the bounded assignment and validate the resulting repository state.",
            "Write exactly one UTF-8 JSON source handoff at output.path.",
            "Use every exact field once, preserve fixed_fields literally, and fill agent_fields.",
            "Set candidate_commit to the exact current full Git HEAD.",
            "Use relative evidence_refs only; never include output, logs, or conversation bodies.",
            (
                "Publish atomically as a current-UID regular file with mode 0600; "
                "finish this turn and remain in the interactive harness."
            ),
            "Do not exit the harness process.",
        ],
    }
    validate_bounded_json(
        result,
        max_depth=7,
        max_items=128,
        max_string=4096,
        reject_sensitive_fields=True,
    )
    return result


def _checkpoint_delivery_sha256(
    lane: puppet_fanout.LanePlan,
    assignment: Mapping[str, Any],
) -> str:
    message = (canonical_json_bytes(dict(assignment)) + b"\n").decode("utf-8")
    enveloped = adapter_for(lane.target).envelope(
        message,
        lane.contract.session_profile,
        initial=False,
    )
    return sha256_bytes(enveloped.encode("utf-8"))


def _checkpoint_delivery_receipt(
    *,
    launch_id: str,
    lane: puppet_fanout.LanePlan,
    request_id: str,
    assignment_sha256: str,
    delivery_sha256: str,
) -> Dict[str, Any]:
    result = {
        "schema": CHECKPOINT_DELIVERY_SCHEMA,
        "version": LAUNCHER_VERSION,
        "state": "assignment_submitted",
        "launch_id": validate_identifier(launch_id, "launch id"),
        "target": lane.target,
        "session": lane.session,
        "request_id": validate_identifier(
            request_id,
            "checkpoint request id",
        ),
        "assignment_sha256": validate_sha256(
            assignment_sha256,
            "checkpoint assignment",
        ),
        "delivery_sha256": validate_sha256(
            delivery_sha256,
            "checkpoint delivery",
        ),
    }
    validate_bounded_json(
        result,
        max_depth=4,
        max_items=32,
        max_string=4096,
        reject_sensitive_fields=True,
    )
    return result


def _validate_modes(values: Iterable[str]) -> tuple[str, ...]:
    modes = tuple(values) or ("read", "test")
    allowed = {"read", "test", "mutate", "local_commit"}
    if (
        len(modes) > len(allowed)
        or len(set(modes)) != len(modes)
        or not set(modes) <= allowed
    ):
        raise ValidationError("launcher modes are invalid or duplicated")
    return tuple(sorted(modes))


def _mutation_owner(
    targets: Sequence[str],
    modes: Sequence[str],
    requested_owner: str | None,
) -> str:
    mutating = bool(set(modes) & {"mutate", "local_commit"})
    if requested_owner is not None and requested_owner not in TARGETS:
        raise ValidationError("mutation owner target is invalid")
    if not mutating:
        if requested_owner is not None:
            raise ValidationError("mutation owner requires a mutating mode")
        return "none"
    if requested_owner is None:
        if len(targets) != 1:
            raise ValidationError(
                "a multi-target mutating launch requires --mutation-owner"
            )
        return targets[0]
    if requested_owner not in targets:
        raise ValidationError("mutation owner is absent from the selected targets")
    if len(targets) > 1 and not set(modes) & {"read", "test"}:
        raise ValidationError(
            "a multi-target mutating launch requires read or test support mode"
        )
    return requested_owner


def _lane_modes(
    modes: Sequence[str],
    *,
    target: str,
    mutation_owner: str,
) -> tuple[str, ...]:
    if mutation_owner in {"none", target}:
        return tuple(modes)
    support_modes = tuple(mode for mode in modes if mode in {"read", "test"})
    if not support_modes:
        raise ValidationError("support lane has no operator-authorized mode")
    return support_modes


def _campaign_unhashed(value: Mapping[str, Any]) -> Dict[str, Any]:
    result = dict(value)
    result.pop("campaign_sha256", None)
    return result


def _validate_checkpoint_binding(
    *,
    binding: Any,
    launch_id: str,
    lane: puppet_fanout.LanePlan,
    manifest: AdapterManifest,
) -> None:
    fields = {
        "assignment",
        "request_id",
        "path",
        "checkpoint_kind",
        "schema_version",
        "max_bytes",
        "delivery_receipt",
        "delivery_sha256",
    }
    if not isinstance(binding, dict) or set(binding) != fields:
        raise ValidationError(
            "%s campaign checkpoint binding is invalid" % lane.target
        )
    expected_path = lane.proof_root / "source-checkpoint.json"
    expected_receipt_path = (
        lane.proof_root / "source-checkpoint-delivery.json"
    )
    if (
        binding.get("path") != str(expected_path)
        or binding.get("checkpoint_kind") != "source"
        or binding.get("schema_version") != HANDOFF_SCHEMA_VERSION
        or binding.get("max_bytes") != MAX_HANDOFF_BYTES
        or binding.get("delivery_receipt") != str(expected_receipt_path)
        or binding.get("request_id")
        != _checkpoint_request_id(launch_id, lane.target, lane.plan_sha256)
    ):
        raise IdentityError(
            "%s campaign checkpoint identity changed" % lane.target
        )
    assignment = binding.get("assignment")
    if not isinstance(assignment, dict) or set(assignment) != {
        "path",
        "sha256",
        "bytes",
    }:
        raise ValidationError(
            "%s campaign checkpoint assignment is invalid" % lane.target
        )
    expected_assignment_path = (
        lane.proof_root / "source-checkpoint-assignment.json"
    )
    if assignment.get("path") != str(expected_assignment_path):
        raise IdentityError(
            "%s campaign checkpoint assignment path changed" % lane.target
        )
    current_assignment = _artifact(
        expected_assignment_path,
        label="%s campaign checkpoint assignment" % lane.target,
    )
    if current_assignment != assignment:
        raise IdentityError(
            "%s campaign checkpoint assignment changed" % lane.target
        )
    recorded_assignment = read_json(
        expected_assignment_path,
        max_bytes=MAX_ARTIFACT_BYTES,
        reject_sensitive_fields=True,
    )
    expected_assignment = _checkpoint_assignment(
        launch_id=launch_id,
        lane=lane,
        manifest=manifest,
        output_path=expected_path,
    )
    if recorded_assignment != expected_assignment:
        raise IdentityError(
            "%s campaign checkpoint assignment content changed" % lane.target
        )
    expected_delivery_sha256 = _checkpoint_delivery_sha256(
        lane,
        expected_assignment,
    )
    if binding.get("delivery_sha256") != expected_delivery_sha256:
        raise IdentityError(
            "%s campaign checkpoint delivery identity changed" % lane.target
        )
    expected_receipt = _checkpoint_delivery_receipt(
        launch_id=launch_id,
        lane=lane,
        request_id=binding["request_id"],
        assignment_sha256=current_assignment["sha256"],
        delivery_sha256=expected_delivery_sha256,
    )
    try:
        os.lstat(expected_receipt_path)
    except FileNotFoundError:
        return
    except OSError as exc:
        raise ValidationError(
            "%s campaign checkpoint delivery receipt is unavailable"
            % lane.target
        ) from exc
    receipt_artifact = _artifact(
        expected_receipt_path,
        label="%s campaign checkpoint delivery receipt" % lane.target,
    )
    receipt_stat = os.lstat(expected_receipt_path)
    if (
        receipt_stat.st_uid != os.getuid()
        or receipt_stat.st_nlink != 1
        or stat.S_IMODE(receipt_stat.st_mode) != PRIVATE_FILE_MODE
        or receipt_artifact["bytes"] <= 0
    ):
        raise IdentityError(
            "%s campaign checkpoint delivery receipt is unsafe" % lane.target
        )
    recorded_receipt = read_json(
        expected_receipt_path,
        max_bytes=MAX_ARTIFACT_BYTES,
        reject_sensitive_fields=True,
    )
    if recorded_receipt != expected_receipt:
        raise IdentityError(
            "%s campaign checkpoint delivery receipt changed" % lane.target
        )


def _load_campaign(path_value: Path | str) -> Dict[str, Any]:
    artifact = _artifact(path_value, label="launch campaign")
    value = read_json(
        Path(artifact["path"]),
        max_bytes=MAX_ARTIFACT_BYTES,
        reject_sensitive_fields=True,
    )
    validate_bounded_json(
        value,
        max_depth=9,
        max_items=384,
        max_string=4096,
        reject_sensitive_fields=True,
    )
    if not isinstance(value, dict) or set(value) != {
        "schema",
        "version",
        "state",
        "launch_id",
        "targets",
        "controller",
        "qualification_authority",
        "source",
        "request",
        "roots",
        "launcher",
        "lanes",
        "plan_set_sha256",
        "campaign_sha256",
    }:
        raise ValidationError("launch campaign fields are invalid")
    if (
        value.get("schema") != CAMPAIGN_SCHEMA
        or value.get("version") != LAUNCHER_VERSION
        or value.get("state") != "ready"
    ):
        raise ValidationError("launch campaign schema or state is invalid")
    recorded = validate_sha256(value.get("campaign_sha256"), "launch campaign")
    if sha256_bytes(canonical_json_bytes(_campaign_unhashed(value))) != recorded:
        raise IdentityError("launch campaign fingerprint changed")
    launch_id = validate_identifier(value.get("launch_id"), "launch id")
    validate_identifier(value.get("controller"), "campaign controller")
    qualification = value.get("qualification_authority")
    if not isinstance(qualification, dict) or set(qualification) != {
        "catalog",
        "catalog_sha256",
        "authorization",
    }:
        raise ValidationError("launch campaign qualification authority is invalid")
    catalog_artifact = qualification.get("catalog")
    if not isinstance(catalog_artifact, dict) or set(catalog_artifact) != {
        "path",
        "sha256",
        "bytes",
    }:
        raise ValidationError("launch campaign catalog artifact is invalid")
    current_catalog_artifact = _artifact(
        catalog_artifact.get("path"),
        label="launch campaign catalog",
    )
    if current_catalog_artifact != catalog_artifact:
        raise IdentityError("launch campaign catalog changed")
    catalog = _load_catalog(Path(current_catalog_artifact["path"]))
    if (
        catalog["catalog_sha256"] != qualification.get("catalog_sha256")
        or catalog["controller"] != value["controller"]
        or catalog["authorization"] != qualification.get("authorization")
    ):
        raise IdentityError("launch campaign qualification authority changed")
    source = value.get("source")
    if not isinstance(source, dict) or set(source) != {
        "repo",
        "branch",
        "commit",
        "tree",
        "git_common_dir",
        "git_executable",
        "git_executable_sha256",
    }:
        raise ValidationError("launch campaign source identity is invalid")
    _absolute_path(source.get("repo"), label="campaign source repository")
    validate_branch(source.get("branch"))
    validate_sha1(source.get("commit"), "campaign source commit")
    validate_sha1(source.get("tree"), "campaign source tree")
    _absolute_path(source.get("git_common_dir"), label="campaign Git common directory")
    git_path = _absolute_path(
        source.get("git_executable"),
        label="campaign Git executable",
    )
    if sha256_file(git_path) != validate_sha256(
        source.get("git_executable_sha256"),
        "campaign Git executable",
    ):
        raise IdentityError("launch campaign Git executable changed")
    request = value.get("request")
    if not isinstance(request, dict) or set(request) != {
        "input_artifact",
        "task_profile",
        "allowed_modes",
        "mutation_owner",
    }:
        raise ValidationError("launch campaign request is invalid")
    input_artifact = request.get("input_artifact")
    if not isinstance(input_artifact, dict) or set(input_artifact) != {
        "path",
        "sha256",
        "bytes",
    }:
        raise ValidationError("launch campaign input artifact is invalid")
    if _artifact(
        input_artifact.get("path"),
        label="launch campaign input artifact",
    ) != input_artifact:
        raise IdentityError("launch campaign input artifact changed")
    validate_identifier(request.get("task_profile"), "campaign task profile")
    modes = _validate_modes(request.get("allowed_modes", []))
    recorded_owner = request.get("mutation_owner")
    if not isinstance(recorded_owner, str):
        raise ValidationError("launch campaign mutation owner is invalid")
    roots = value.get("roots")
    if not isinstance(roots, dict) or set(roots) != {
        "campaign",
        "worktree_parent",
    }:
        raise ValidationError("launch campaign roots are invalid")
    campaign_root = _real_directory(
        roots.get("campaign"),
        label="campaign root",
        private=True,
    )
    if campaign_root != Path(artifact["path"]).parent:
        raise IdentityError("launch campaign root changed")
    _real_directory(
        roots.get("worktree_parent"),
        label="campaign worktree parent",
    )
    launcher = value.get("launcher")
    if not isinstance(launcher, dict) or set(launcher) != {
        "path",
        "sha256",
        "fanout_path",
        "fanout_sha256",
        "adapter_implementation_sha256",
        "protocol_sha256",
    }:
        raise ValidationError("launch campaign controller binding is invalid")
    own_path = Path(__file__).resolve(strict=True)
    fanout_path = Path(puppet_fanout.__file__).resolve(strict=True)
    if (
        launcher.get("path") != str(own_path)
        or launcher.get("sha256") != sha256_file(own_path)
        or launcher.get("fanout_path") != str(fanout_path)
        or launcher.get("fanout_sha256") != sha256_file(fanout_path)
        or launcher.get("adapter_implementation_sha256")
        != adapter_implementation_fingerprint()
        or launcher.get("protocol_sha256") != PROTOCOL_FINGERPRINT
    ):
        raise IdentityError("launch campaign controller implementation changed")
    lanes = value.get("lanes")
    targets = value.get("targets")
    if (
        not isinstance(targets, list)
        or not targets
        or targets != [target for target in TARGET_ORDER if target in set(targets)]
        or not isinstance(lanes, dict)
        or set(lanes) != set(targets)
    ):
        raise ValidationError("launch campaign targets are invalid")
    expected_owner = _mutation_owner(
        targets,
        modes,
        None if recorded_owner == "none" else recorded_owner,
    )
    if recorded_owner != expected_owner:
        raise IdentityError("launch campaign mutation ownership changed")
    plans: list[Path] = []
    for target in targets:
        if target not in catalog["targets"]:
            raise IdentityError("launch campaign target left its warm catalog")
        lane = lanes[target]
        if not isinstance(lane, dict) or set(lane) != {
            "branch",
            "repository",
            "run_root",
            "session",
            "plan",
            "plan_sha256",
            "plan_file_sha256",
            "source_checkpoint",
        }:
            raise ValidationError("launch campaign lane fields are invalid")
        validate_branch(lane.get("branch"))
        _absolute_path(
            lane.get("repository"),
            label="%s campaign repository" % target,
        )
        _real_directory(
            lane.get("run_root"),
            label="%s campaign run root" % target,
            private=True,
        )
        validate_identifier(lane.get("session"), "%s campaign session" % target)
        validate_sha256(lane.get("plan_sha256"), "%s campaign plan" % target)
        plan_artifact = _artifact(
            lane.get("plan"),
            label="%s campaign plan" % target,
        )
        if plan_artifact["sha256"] != lane.get("plan_file_sha256"):
            raise IdentityError("%s campaign plan changed" % target)
        plans.append(Path(plan_artifact["path"]))
    loaded = puppet_fanout.load_lane_plans(plans)
    if [lane.target for lane in loaded] != sorted(targets):
        raise IdentityError("launch campaign plan set changed")
    expected_input = request["input_artifact"]
    expected_authorization = _artifact(
        catalog["authorization"]["path"],
        label="campaign authorization binding",
    )
    for lane in loaded:
        target = lane.target
        row = lanes[target]
        expected_branch = _branch_for(launch_id, target)
        expected_session = _session_for(launch_id, target)
        expected_run_id = _run_id_for(launch_id, target)
        expected_nonce = _nonce_for(
            launch_id,
            target,
            expected_input["sha256"],
        )
        expected_objective = (
            "Execute the operator-supplied regular task for %s under launch %s."
            % (target, launch_id)
        )
        expected_repository = (
            Path(roots["worktree_parent"]) / ("%s-%s" % (launch_id, target))
        )
        expected_run_root = campaign_root / "lanes" / target
        expected_plan = campaign_root / "plans" / ("%s.json" % target)
        expected_contract = expected_run_root / "contract.json"
        expected_manifest = _artifact(
            catalog["targets"][target]["manifest"],
            label="%s campaign manifest binding" % target,
        )
        manifest = AdapterManifest.from_path(Path(expected_manifest["path"]))
        expected_contract_artifact = _artifact(
            expected_contract,
            label="%s campaign contract binding" % target,
        )
        recorded_artifacts = lane.raw.get("artifacts")
        if not isinstance(recorded_artifacts, dict):
            raise ValidationError("%s campaign plan artifacts are invalid" % target)
        expected_artifacts = {
            "contract": expected_contract_artifact,
            "manifest": expected_manifest,
            "authorization": expected_authorization,
            "input_payload": expected_input,
        }
        if recorded_artifacts != expected_artifacts:
            raise IdentityError("%s campaign artifact binding changed" % target)
        if (
            lane.path != expected_plan
            or lane.repository != expected_repository
            or lane.run_root != expected_run_root
            or lane.proof_root != expected_run_root / "proof"
            or lane.state_root != expected_run_root / "state"
            or lane.session != expected_session
            or lane.contract.branch != expected_branch
            or lane.contract.run_id != expected_run_id
            or lane.contract.nonce != expected_nonce
            or lane.contract.raw.get("objective") != expected_objective
            or lane.contract.repo != expected_repository
            or lane.contract.candidate_root != expected_repository
            or lane.contract.supervisor_root != Path(source["repo"])
            or lane.contract.controller != value["controller"]
            or lane.contract.campaign_authorization_id
            != catalog["authorization"]["campaign_id"]
            or lane.contract.target != target
            or lane.contract.session_profile != "regular"
            or lane.contract.task_profile != request["task_profile"]
            or lane.contract.requested_model is not None
            or lane.contract.requested_effort is not None
            or lane.contract.max_helpers != 0
            or lane.contract.harness_trust != "unrestricted_required"
            or lane.contract.proof_path_prefixes != ("proof/",)
            or lane.contract.terminal_criteria
            != ({"id": "task_complete", "evidence": "validated_handoff"},)
            or lane.contract.hard_gates != frozenset(MANDATORY_HARD_GATES)
        ):
            raise IdentityError("%s campaign lane ownership changed" % target)
        expected_profile = catalog["targets"][target]["profile_root"]
        if (
            str(lane.profile_root) if lane.profile_root is not None else None
        ) != expected_profile:
            raise IdentityError("%s campaign profile binding changed" % target)
        repository = lane.raw.get("repository")
        if not isinstance(repository, dict) or (
            repository.get("repo") != str(expected_repository)
            or repository.get("branch") != expected_branch
            or repository.get("head") != source["commit"]
            or repository.get("tree") != source["tree"]
            or repository.get("git_common_dir") != source["git_common_dir"]
            or repository.get("linked_worktree") is not True
            or repository.get("dirty") is not False
            or repository.get("git_executable") != source["git_executable"]
            or repository.get("git_executable_sha256")
            != source["git_executable_sha256"]
        ):
            raise IdentityError("%s campaign repository binding changed" % target)
        if lane.raw.get("entry_mode") != "cockpit_explicit":
            raise IdentityError("%s campaign entry mode changed" % target)
        supervisor = lane.raw.get("supervisor_repository")
        owns_mutation = target == recorded_owner
        if owns_mutation:
            if not isinstance(supervisor, dict) or (
                supervisor.get("repo") != source["repo"]
                or supervisor.get("branch") != source["branch"]
                or supervisor.get("head") != source["commit"]
                or supervisor.get("tree") != source["tree"]
                or supervisor.get("git_common_dir") != source["git_common_dir"]
                or supervisor.get("git_executable") != source["git_executable"]
                or supervisor.get("git_executable_sha256")
                != source["git_executable_sha256"]
            ):
                raise IdentityError(
                    "%s campaign supervisor binding changed" % target
                )
        elif supervisor is not None:
            raise IdentityError("%s support lane gained a supervisor" % target)
        if (
            row.get("branch") != expected_branch
            or row.get("repository") != str(expected_repository)
            or row.get("run_root") != str(expected_run_root)
            or row.get("session") != expected_session
            or row.get("plan") != str(expected_plan)
            or row.get("plan_sha256") != lane.plan_sha256
            or row.get("plan_file_sha256") != lane.file_sha256
        ):
            raise IdentityError("%s campaign lane index changed" % target)
        _validate_checkpoint_binding(
            binding=row.get("source_checkpoint"),
            launch_id=launch_id,
            lane=lane,
            manifest=manifest,
        )
    for lane in loaded:
        owns_mutation = lane.target == recorded_owner
        expected_lane_owner = "target" if owns_mutation else "none"
        expected_lane_modes = frozenset(
            _lane_modes(
                modes,
                target=lane.target,
                mutation_owner=recorded_owner,
            )
        )
        if (
            lane.contract.mutation_owner != expected_lane_owner
            or lane.contract.allowed_modes != expected_lane_modes
        ):
            raise IdentityError(
                "%s campaign mutation assignment changed" % lane.target
            )
    plan_set = sha256_bytes(
        canonical_json_bytes(
            [
                {
                    "target": lane.target,
                    "path": str(lane.path),
                    "file_sha256": lane.file_sha256,
                    "plan_sha256": lane.plan_sha256,
                }
                for lane in loaded
            ]
        )
    )
    if plan_set != value.get("plan_set_sha256"):
        raise IdentityError("launch campaign plan-set fingerprint changed")
    return value


def _update_prepare_state(
    state_path: Path,
    *,
    state: str,
    launch_id: str,
    targets: Sequence[str],
    attempted_worktrees: Sequence[Mapping[str, str]],
    created_worktrees: Sequence[Mapping[str, str]],
    error: str | None = None,
) -> None:
    created_targets = {item["target"] for item in created_worktrees}
    value: Dict[str, Any] = {
        "schema": "puppet.launch-prepare-state/v1",
        "version": LAUNCHER_VERSION,
        "state": state,
        "launch_id": launch_id,
        "targets": list(targets),
        "attempted_worktrees": [dict(item) for item in attempted_worktrees],
        "created_worktrees": [dict(item) for item in created_worktrees],
        "ambiguous_worktrees": [
            dict(item)
            for item in attempted_worktrees
            if item["target"] not in created_targets
        ],
        "automatic_cleanup": False,
    }
    if error is not None:
        value["error"] = error
    _replace_json(state_path, value)


def prepare_campaign(
    *,
    catalog_path: Path | str,
    target_values: Iterable[str],
    source_repo: Path | str,
    source_commit: str,
    prompt_path: Path | str,
    launch_id: str,
    campaign_root: Path | str,
    worktree_parent: Path | str,
    mode_values: Iterable[str] = (),
    mutation_owner_target: str | None = None,
    task_profile: str = "regular",
    _controller_identity_validator: (
        Callable[[Mapping[str, Any]], Mapping[str, Any] | None] | None
    ) = None,
) -> Dict[str, Any]:
    started = time.monotonic()
    launch_id = validate_identifier(launch_id, "launch id")
    task_profile = validate_identifier(task_profile, "task profile")
    targets = _selected_targets(target_values)
    modes = _validate_modes(mode_values)
    mutation_owner = _mutation_owner(targets, modes, mutation_owner_target)
    catalog_file = _artifact(catalog_path, label="warm catalog")
    catalog = _load_catalog(Path(catalog_file["path"]))
    if not set(targets) <= set(catalog["targets"]):
        raise UnsupportedError("selected target is absent from the warm catalog")
    source = _source_identity(source_repo, source_commit)
    controller_identity_validator = (
        _controller_identity_validator or _validate_executing_controller
    )
    controller_identity_validator(source)
    prompt_file = _absolute_path(prompt_path, label="launch prompt")
    root = _future_path(campaign_root, label="campaign root")
    root_parent = _real_directory(
        root.parent,
        label="campaign root parent",
    )
    if root.parent != root_parent:
        raise IdentityError("campaign root parent identity changed")
    worktrees = _real_directory(
        worktree_parent,
        label="worktree parent",
    )
    if paths_overlap(root, Path(source["repo"])) or paths_overlap(root, worktrees):
        raise ValidationError("campaign root overlaps source or worktree ownership")
    protected_profiles = [
        Path(lane["profile_root"])
        for lane in catalog["targets"].values()
        if lane["profile_root"] is not None
    ]
    for profile in protected_profiles:
        if profile is not None and (
            paths_overlap(root, profile)
            or paths_overlap(Path(source["repo"]), profile)
            or paths_overlap(prompt_file, profile)
        ):
            raise ValidationError("launcher ownership overlaps a private profile")
    prompt = _artifact(prompt_file, label="launch prompt")

    git = Path(source["git_executable"])
    candidate_rows: Dict[str, Dict[str, str]] = {}
    for target in targets:
        branch = _branch_for(launch_id, target)
        session = _session_for(launch_id, target)
        run_id = _run_id_for(launch_id, target)
        if (
            _git(
                git,
                Path(source["repo"]),
                ["check-ref-format", "--branch", branch],
                allow_failure=True,
            ).returncode
            != 0
        ):
            raise ValidationError("%s worktree branch is invalid" % target)
        candidate = _future_path(
            worktrees / ("%s-%s" % (launch_id, target)),
            label="%s worktree" % target,
        )
        if candidate.parent != worktrees:
            raise ValidationError("candidate worktree escapes its parent")
        if paths_overlap(candidate, Path(source["repo"])):
            raise ValidationError("%s worktree overlaps the source repository" % target)
        if any(paths_overlap(candidate, profile) for profile in protected_profiles):
            raise ValidationError("%s worktree overlaps a private profile" % target)
        if (
            _git(
                git,
                Path(source["repo"]),
                ["show-ref", "--verify", "--quiet", "refs/heads/%s" % branch],
                allow_failure=True,
            ).returncode
            == 0
        ):
            raise ValidationError("%s worktree branch already exists" % target)
        candidate_rows[target] = {
            "target": target,
            "branch": branch,
            "repository": str(candidate),
            "session": session,
            "run_id": run_id,
        }

    _create_private_directory(root)
    state_path = root / "prepare-state.json"
    _update_prepare_state(
        state_path,
        state="preparing",
        launch_id=launch_id,
        targets=targets,
        attempted_worktrees=[],
        created_worktrees=[],
    )
    lanes_root = root / "lanes"
    plans_root = root / "plans"
    attempted: list[Dict[str, str]] = []
    created: list[Dict[str, str]] = []
    try:
        _create_private_directory(lanes_root)
        _create_private_directory(plans_root)
        for target in targets:
            row = candidate_rows[target]
            _progress("worktree_start", launch_id=launch_id, target=target)
            attempted.append(dict(row))
            _update_prepare_state(
                state_path,
                state="preparing",
                launch_id=launch_id,
                targets=targets,
                attempted_worktrees=attempted,
                created_worktrees=created,
            )
            _git(
                git,
                Path(source["repo"]),
                [
                    "worktree",
                    "add",
                    "-b",
                    row["branch"],
                    row["repository"],
                    source["commit"],
                ],
            )
            created.append(dict(row))
            _update_prepare_state(
                state_path,
                state="preparing",
                launch_id=launch_id,
                targets=targets,
                attempted_worktrees=attempted,
                created_worktrees=created,
            )
            candidate = Path(row["repository"]).resolve(strict=True)
            if (
                _git_text(git, candidate, ["rev-parse", "HEAD"]) != source["commit"]
                or _git_text(
                    git,
                    candidate,
                    ["symbolic-ref", "--quiet", "--short", "HEAD"],
                )
                != row["branch"]
                or _git_text(
                    git,
                    candidate,
                    ["status", "--porcelain=v1", "--untracked-files=normal"],
                )
            ):
                raise IdentityError("%s created worktree identity is invalid" % target)
            _progress("worktree_ready", launch_id=launch_id, target=target)

        contract_paths: Dict[str, Path] = {}
        run_roots: Dict[str, Path] = {}
        sessions: Dict[str, str] = {}
        for target in targets:
            lane_root = lanes_root / target
            _create_private_directory(lane_root)
            proof_root = lane_root / "proof"
            state_root = lane_root / "state"
            _create_private_directory(proof_root)
            _create_private_directory(state_root)
            run_roots[target] = lane_root
            sessions[target] = candidate_rows[target]["session"]
            lane_modes = _lane_modes(
                modes,
                target=target,
                mutation_owner=mutation_owner,
            )
            owns_mutation = target == mutation_owner
            contract = {
                "schema_version": 1,
                "objective": (
                    "Execute the operator-supplied regular task for %s under "
                    "launch %s." % (target, launch_id)
                ),
                "campaign_authorization_id": catalog["authorization"][
                    "campaign_id"
                ],
                "controller": catalog["controller"],
                "target": target,
                "session_profile": "regular",
                "task_profile": task_profile,
                "harness_trust": "unrestricted_required",
                "mutation_owner": "target" if owns_mutation else "none",
                "repo": candidate_rows[target]["repository"],
                "branch": candidate_rows[target]["branch"],
                "max_helpers": 0,
                "allowed_modes": list(lane_modes),
                "terminal_criteria": [
                    {
                        "id": "task_complete",
                        "evidence": "validated_handoff",
                    }
                ],
                "hard_gates": sorted(MANDATORY_HARD_GATES),
                "supervisor_root": source["repo"],
                "candidate_root": candidate_rows[target]["repository"],
                "run_id": candidate_rows[target]["run_id"],
                "nonce": _nonce_for(
                    launch_id,
                    target,
                    prompt["sha256"],
                ),
                "proof_path_prefixes": ["proof/"],
            }
            contract_path = lane_root / "contract.json"
            _create_only_json(contract_path, contract)
            contract_paths[target] = contract_path

        def compile_target(target: str) -> tuple[str, Dict[str, Any]]:
            catalog_lane = catalog["targets"][target]
            plan = compile_operator_plan(
                contract_path=contract_paths[target],
                manifest_path=Path(catalog_lane["manifest"]),
                authorization_path=Path(catalog["authorization"]["path"]),
                profile_root=(
                    Path(catalog_lane["profile_root"])
                    if catalog_lane["profile_root"] is not None
                    else None
                ),
                prompt_path=Path(prompt["path"]),
                session=sessions[target],
                run_root=run_roots[target],
                repo=Path(candidate_rows[target]["repository"]),
            )
            return target, plan

        compiled: Dict[str, Dict[str, Any]] = {}
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=len(targets),
            thread_name_prefix="puppet-launch-compile",
        ) as executor:
            futures = {
                executor.submit(compile_target, target): target for target in targets
            }
            for future in concurrent.futures.as_completed(futures):
                target, plan = future.result()
                compiled[target] = plan
                _progress("plan_ready", launch_id=launch_id, target=target)

        plan_paths: list[Path] = []
        for target in targets:
            plan_path = plans_root / ("%s.json" % target)
            _create_only_json(plan_path, compiled[target])
            plan_paths.append(plan_path)
        loaded = puppet_fanout.load_lane_plans(plan_paths)
        plan_rows = [
            {
                "target": lane.target,
                "path": str(lane.path),
                "file_sha256": lane.file_sha256,
                "plan_sha256": lane.plan_sha256,
            }
            for lane in loaded
        ]
        plan_set_sha256 = sha256_bytes(canonical_json_bytes(plan_rows))
        checkpoint_rows: Dict[str, Dict[str, Any]] = {}
        for lane in loaded:
            checkpoint_path = _future_path(
                lane.proof_root / "source-checkpoint.json",
                label="%s source checkpoint output" % lane.target,
            )
            assignment_path = _future_path(
                lane.proof_root / "source-checkpoint-assignment.json",
                label="%s source checkpoint assignment" % lane.target,
            )
            delivery_receipt_path = _future_path(
                lane.proof_root / "source-checkpoint-delivery.json",
                label="%s source checkpoint delivery receipt" % lane.target,
            )
            manifest = AdapterManifest.from_path(
                Path(catalog["targets"][lane.target]["manifest"])
            )
            assignment = _checkpoint_assignment(
                launch_id=launch_id,
                lane=lane,
                manifest=manifest,
                output_path=checkpoint_path,
            )
            _create_only_json(assignment_path, assignment)
            delivery_sha256 = _checkpoint_delivery_sha256(
                lane,
                assignment,
            )
            checkpoint_rows[lane.target] = {
                "assignment": _artifact(
                    assignment_path,
                    label="%s source checkpoint assignment" % lane.target,
                ),
                "request_id": assignment["request_id"],
                "path": str(checkpoint_path),
                "checkpoint_kind": "source",
                "schema_version": HANDOFF_SCHEMA_VERSION,
                "max_bytes": MAX_HANDOFF_BYTES,
                "delivery_receipt": str(delivery_receipt_path),
                "delivery_sha256": delivery_sha256,
            }
        launcher_path = Path(__file__).resolve(strict=True)
        fanout_path = Path(puppet_fanout.__file__).resolve(strict=True)
        result: Dict[str, Any] = {
            "schema": CAMPAIGN_SCHEMA,
            "version": LAUNCHER_VERSION,
            "state": "ready",
            "launch_id": launch_id,
            "targets": list(targets),
            "controller": catalog["controller"],
            "qualification_authority": {
                "catalog": catalog_file,
                "catalog_sha256": catalog["catalog_sha256"],
                "authorization": dict(catalog["authorization"]),
            },
            "source": source,
            "request": {
                "input_artifact": prompt,
                "task_profile": task_profile,
                "allowed_modes": list(modes),
                "mutation_owner": mutation_owner,
            },
            "roots": {
                "campaign": str(root),
                "worktree_parent": str(worktrees),
            },
            "launcher": {
                "path": str(launcher_path),
                "sha256": sha256_file(launcher_path),
                "fanout_path": str(fanout_path),
                "fanout_sha256": sha256_file(fanout_path),
                "adapter_implementation_sha256": adapter_implementation_fingerprint(),
                "protocol_sha256": PROTOCOL_FINGERPRINT,
            },
            "lanes": {
                lane.target: {
                    "branch": lane.contract.branch,
                    "repository": str(lane.repository),
                    "run_root": str(lane.run_root),
                    "session": lane.session,
                    "plan": str(lane.path),
                    "plan_sha256": lane.plan_sha256,
                    "plan_file_sha256": lane.file_sha256,
                    "source_checkpoint": checkpoint_rows[lane.target],
                }
                for lane in loaded
            },
            "plan_set_sha256": plan_set_sha256,
        }
        result["campaign_sha256"] = sha256_bytes(canonical_json_bytes(result))
        validate_bounded_json(
            result,
            max_depth=9,
            max_items=384,
            max_string=4096,
            reject_sensitive_fields=True,
        )
        campaign_path = root / "campaign.json"
        _create_only_json(campaign_path, result)
        result = _load_campaign(campaign_path)
        _update_prepare_state(
            state_path,
            state="ready",
            launch_id=launch_id,
            targets=targets,
            attempted_worktrees=attempted,
            created_worktrees=created,
        )
        _progress(
            "campaign_ready",
            launch_id=launch_id,
            campaign=str(campaign_path),
            elapsed_ms=int((time.monotonic() - started) * 1000),
            targets=list(targets),
        )
        return result
    except (Exception, KeyboardInterrupt) as exc:
        if isinstance(exc, KeyboardInterrupt):
            error = "operator_interrupted"
        else:
            error = exc.category if isinstance(exc, PuppetError) else "prepare_failed"
        _update_prepare_state(
            state_path,
            state="blocked",
            launch_id=launch_id,
            targets=targets,
            attempted_worktrees=attempted,
            created_worktrees=created,
            error=error,
        )
        _progress(
            "campaign_blocked",
            launch_id=launch_id,
            error=error,
            attempted_targets=[row["target"] for row in attempted],
            created_targets=[row["target"] for row in created],
            automatic_cleanup=False,
        )
        raise


def _fanout_argv(
    *,
    action: str,
    campaign: Mapping[str, Any],
    allow_live_launch: bool = False,
    open_views: bool = False,
) -> list[str]:
    if action not in {"launch", "status", "attach", "view", "halt"}:
        raise ValidationError("campaign lifecycle action is invalid")
    argv = [
        str(Path(sys.executable).resolve(strict=True)),
        campaign["launcher"]["fanout_path"],
        action,
    ]
    for target in campaign["targets"]:
        argv.extend(["--plan", campaign["lanes"][target]["plan"]])
    if action == "launch":
        if not allow_live_launch:
            raise ValidationError("live launch requires --allow-live-launch")
        argv.append("--allow-live-launch")
        if open_views:
            argv.append("--open-views")
    return argv


def execute_fanout(argv: Sequence[str]) -> None:
    os.execv(argv[0], list(argv))
    raise AssertionError("execv returned")


class _CheckpointLaneFailure(Exception):
    def __init__(self, error: str) -> None:
        super().__init__(error)
        self.error = validate_identifier(error, "checkpoint lane error")


def _checkpoint_controller_call(
    *,
    lane: puppet_fanout.LanePlan,
    action: str,
    arguments: Sequence[str],
    runner: Callable[[Sequence[str]], subprocess.CompletedProcess[bytes]],
) -> Dict[str, Any]:
    argv = [
        lane.controller["interpreter"],
        lane.controller["cli"],
        "--json",
        action,
        *arguments,
    ]
    try:
        completed = runner(argv)
    except (OSError, subprocess.TimeoutExpired):
        raise _CheckpointLaneFailure(
            "controller_%s_invocation_failed" % action
        )
    if not isinstance(completed, subprocess.CompletedProcess):
        raise _CheckpointLaneFailure("controller_%s_output_invalid" % action)
    output = (
        puppet_fanout._safe_child_json(completed.stdout)
        if isinstance(completed.stdout, bytes)
        else None
    )
    if completed.returncode != 0:
        raise _CheckpointLaneFailure("controller_%s_rejected" % action)
    if output is None or output.get("ok") is not True:
        raise _CheckpointLaneFailure("controller_%s_output_invalid" % action)
    if action != "checkpoint" and output.get("session") != lane.session:
        raise _CheckpointLaneFailure("controller_%s_identity_changed" % action)
    return output


def _checkpoint_stat_sample(
    details: os.stat_result,
    *,
    max_bytes: int,
) -> tuple[int, ...]:
    if (
        stat.S_ISLNK(details.st_mode)
        or not stat.S_ISREG(details.st_mode)
        or details.st_uid != os.getuid()
        or details.st_nlink != 1
        or stat.S_IMODE(details.st_mode) != PRIVATE_FILE_MODE
        or details.st_size <= 0
        or details.st_size > max_bytes
    ):
        raise _CheckpointLaneFailure("checkpoint_path_unsafe")
    return (
        details.st_dev,
        details.st_ino,
        details.st_size,
        details.st_mtime_ns,
        stat.S_IMODE(details.st_mode),
        details.st_uid,
        details.st_nlink,
    )


def _checkpoint_file_sample(path: Path, *, max_bytes: int) -> tuple[int, ...] | None:
    try:
        details = os.lstat(path)
    except FileNotFoundError:
        return None
    except OSError:
        raise _CheckpointLaneFailure("checkpoint_path_unavailable")
    return _checkpoint_stat_sample(details, max_bytes=max_bytes)


def _checkpoint_file_hash_exact(
    path: Path,
    *,
    max_bytes: int,
) -> tuple[str, tuple[int, ...]]:
    before = _checkpoint_file_sample(path, max_bytes=max_bytes)
    if before is None:
        raise _CheckpointLaneFailure("checkpoint_path_unavailable")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError:
        raise _CheckpointLaneFailure("checkpoint_path_changed")
    digest = hashlib.sha256()
    total = 0
    try:
        opened = _checkpoint_stat_sample(
            os.fstat(descriptor),
            max_bytes=max_bytes,
        )
        if opened != before:
            raise _CheckpointLaneFailure("checkpoint_path_changed")
        while True:
            block = os.read(descriptor, 64 * 1024)
            if not block:
                break
            total += len(block)
            if total > max_bytes:
                raise _CheckpointLaneFailure("checkpoint_path_unsafe")
            digest.update(block)
        after_descriptor = _checkpoint_stat_sample(
            os.fstat(descriptor),
            max_bytes=max_bytes,
        )
        if total != before[2] or after_descriptor != before:
            raise _CheckpointLaneFailure("checkpoint_path_changed")
    except OSError:
        raise _CheckpointLaneFailure("checkpoint_path_changed")
    finally:
        os.close(descriptor)
    after = _checkpoint_file_sample(path, max_bytes=max_bytes)
    if after != before:
        raise _CheckpointLaneFailure("checkpoint_path_changed")
    return digest.hexdigest(), before


def _wait_for_stable_checkpoint(
    *,
    path: Path,
    max_bytes: int,
    deadline: float,
    monotonic: Callable[[], float],
    sleep: Callable[[float], None],
    poll_interval: float,
) -> tuple[int, ...]:
    prior: tuple[int, ...] | None = None
    stable_samples = 0
    while True:
        current = _checkpoint_file_sample(path, max_bytes=max_bytes)
        if current is not None:
            if current == prior:
                stable_samples += 1
            else:
                prior = current
                stable_samples = 1
            if stable_samples >= CHECKPOINT_STABLE_SAMPLES:
                return current
        now = monotonic()
        if now >= deadline:
            raise _CheckpointLaneFailure("checkpoint_timeout")
        sleep(min(poll_interval, max(0.0, deadline - now)))


def _checkpoint_reference_projection(
    *,
    reference: Any,
    lane: puppet_fanout.LanePlan,
    binding: Mapping[str, Any],
    fixed_fields: Mapping[str, Any],
) -> Dict[str, Any]:
    expected_identity = {
        key: value
        for key, value in fixed_fields.items()
        if key != "schema_version"
    }
    if not isinstance(reference, dict) or set(reference) != {
        "checkpoint_id",
        "artifact_sha256",
        "checkpoint_kind",
        "identity",
        "path",
        "validation",
    }:
        raise _CheckpointLaneFailure("checkpoint_reference_invalid")
    identity = reference.get("identity")
    if not isinstance(identity, dict) or set(identity) != {
        *expected_identity.keys(),
        "candidate_commit",
    }:
        raise _CheckpointLaneFailure("checkpoint_reference_invalid")
    try:
        checkpoint_id = validate_sha256(
            reference.get("checkpoint_id"),
            "checkpoint id",
        )
        artifact_sha256 = validate_sha256(
            reference.get("artifact_sha256"),
            "checkpoint artifact",
        )
        candidate_commit = validate_sha1(
            identity.get("candidate_commit"),
            "checkpoint candidate commit",
        )
    except PuppetError:
        raise _CheckpointLaneFailure("checkpoint_reference_invalid")
    if (
        reference.get("checkpoint_kind") != "source"
        or reference.get("path") != binding["path"]
        or reference.get("validation") != "valid"
        or any(
            identity.get(key) != value
            for key, value in expected_identity.items()
        )
        or identity.get("session") != lane.session
    ):
        raise _CheckpointLaneFailure("checkpoint_reference_identity_changed")
    return {
        "checkpoint_id": checkpoint_id,
        "artifact_sha256": artifact_sha256,
        "checkpoint_kind": "source",
        "candidate_commit": candidate_commit,
        "path": binding["path"],
    }


def _checkpoint_delivery_receipt_expected(
    *,
    campaign: Mapping[str, Any],
    lane: puppet_fanout.LanePlan,
    binding: Mapping[str, Any],
) -> Dict[str, Any]:
    return _checkpoint_delivery_receipt(
        launch_id=campaign["launch_id"],
        lane=lane,
        request_id=binding["request_id"],
        assignment_sha256=binding["assignment"]["sha256"],
        delivery_sha256=binding["delivery_sha256"],
    )


def _checkpoint_delivery_receipt_present(
    *,
    campaign: Mapping[str, Any],
    lane: puppet_fanout.LanePlan,
    binding: Mapping[str, Any],
) -> bool:
    path = Path(binding["delivery_receipt"])
    try:
        os.lstat(path)
    except FileNotFoundError:
        return False
    except OSError:
        raise _CheckpointLaneFailure("checkpoint_delivery_receipt_unavailable")
    expected = _checkpoint_delivery_receipt_expected(
        campaign=campaign,
        lane=lane,
        binding=binding,
    )
    expected_sha256 = sha256_bytes(canonical_json_bytes(expected) + b"\n")
    try:
        observed_sha256, _ = _checkpoint_file_hash_exact(
            path,
            max_bytes=MAX_ARTIFACT_BYTES,
        )
    except _CheckpointLaneFailure:
        raise _CheckpointLaneFailure("checkpoint_delivery_receipt_invalid")
    if observed_sha256 != expected_sha256:
        raise _CheckpointLaneFailure("checkpoint_delivery_receipt_invalid")
    return True


def _publish_checkpoint_delivery_receipt(
    *,
    campaign: Mapping[str, Any],
    lane: puppet_fanout.LanePlan,
    binding: Mapping[str, Any],
) -> None:
    path = Path(binding["delivery_receipt"])
    expected = _checkpoint_delivery_receipt_expected(
        campaign=campaign,
        lane=lane,
        binding=binding,
    )
    try:
        _create_only_json(path, expected)
    except ValidationError:
        if not _checkpoint_delivery_receipt_present(
            campaign=campaign,
            lane=lane,
            binding=binding,
        ):
            raise _CheckpointLaneFailure(
                "checkpoint_delivery_receipt_publish_failed"
            )
    if not _checkpoint_delivery_receipt_present(
        campaign=campaign,
        lane=lane,
        binding=binding,
    ):
        raise _CheckpointLaneFailure("checkpoint_delivery_receipt_publish_failed")


def _checkpoint_lane(
    *,
    campaign: Mapping[str, Any],
    lane: puppet_fanout.LanePlan,
    timeout: float,
    runner: Callable[[Sequence[str]], subprocess.CompletedProcess[bytes]],
    monotonic: Callable[[], float],
    sleep: Callable[[float], None],
    poll_interval: float,
) -> Dict[str, Any]:
    started = monotonic()
    binding = campaign["lanes"][lane.target]["source_checkpoint"]
    checkpoint_path = Path(binding["path"])
    assignment_path = Path(binding["assignment"]["path"])
    manifest = AdapterManifest.from_path(
        Path(lane.raw["artifacts"]["manifest"]["path"])
    )
    fixed_fields = _checkpoint_fixed_fields(lane, manifest)
    _progress(
        "checkpoint_start",
        launch_id=campaign["launch_id"],
        target=lane.target,
        session=lane.session,
    )
    try:
        status = _checkpoint_controller_call(
            lane=lane,
            action="status",
            arguments=[
                "--state-root",
                str(lane.state_root),
                "--session",
                lane.session,
            ],
            runner=runner,
        )
        current_reference = status.get("last_checkpoint")
        if current_reference is not None:
            projection = _checkpoint_reference_projection(
                reference=current_reference,
                lane=lane,
                binding=binding,
                fixed_fields=fixed_fields,
            )
            if not _checkpoint_delivery_receipt_present(
                campaign=campaign,
                lane=lane,
                binding=binding,
            ):
                raise _CheckpointLaneFailure(
                    "checkpoint_delivery_receipt_missing"
                )
            observed_sha256, _ = _checkpoint_file_hash_exact(
                checkpoint_path,
                max_bytes=binding["max_bytes"],
            )
            if observed_sha256 != projection["artifact_sha256"]:
                raise _CheckpointLaneFailure("checkpoint_artifact_changed")
            _progress(
                "checkpoint_complete",
                launch_id=campaign["launch_id"],
                target=lane.target,
                session=lane.session,
                status="already_imported",
            )
            return {
                "ok": True,
                "target": lane.target,
                "session": lane.session,
                "state": "checkpoint_confirmed",
                "delivery": "already_imported",
                "checkpoint": projection,
                "elapsed_ms": int((monotonic() - started) * 1000),
            }

        preexisting = _checkpoint_file_sample(
            checkpoint_path,
            max_bytes=binding["max_bytes"],
        )
        prior_delivery = _checkpoint_delivery_receipt_present(
            campaign=campaign,
            lane=lane,
            binding=binding,
        )
        if preexisting is not None and not prior_delivery:
            raise _CheckpointLaneFailure("stale_checkpoint_path")
        delivery = _checkpoint_controller_call(
            lane=lane,
            action="send",
            arguments=[
                "--state-root",
                str(lane.state_root),
                "--session",
                lane.session,
                "--request-id",
                binding["request_id"],
                "--message-file",
                str(assignment_path),
            ],
            runner=runner,
        )
        delivery_state = delivery.get("delivery")
        try:
            delivery_sha256 = validate_sha256(
                delivery.get("content_sha256"),
                "checkpoint assignment delivery",
            )
        except PuppetError:
            raise _CheckpointLaneFailure("controller_send_output_invalid")
        if (
            delivery_state not in {"submitted", "already_submitted"}
            or delivery_sha256 != binding["delivery_sha256"]
        ):
            raise _CheckpointLaneFailure("controller_send_output_invalid")
        if prior_delivery and delivery_state != "already_submitted":
            raise _CheckpointLaneFailure("checkpoint_delivery_replay_changed")
        if not prior_delivery:
            _publish_checkpoint_delivery_receipt(
                campaign=campaign,
                lane=lane,
                binding=binding,
            )
        _progress(
            "checkpoint_assignment_submitted",
            launch_id=campaign["launch_id"],
            target=lane.target,
            session=lane.session,
            status=delivery_state,
        )

        deadline = monotonic() + timeout
        _progress(
            "checkpoint_waiting",
            launch_id=campaign["launch_id"],
            target=lane.target,
            session=lane.session,
            wait_timeout_seconds=timeout,
        )
        stable_sample = _wait_for_stable_checkpoint(
            path=checkpoint_path,
            max_bytes=binding["max_bytes"],
            deadline=deadline,
            monotonic=monotonic,
            sleep=sleep,
            poll_interval=poll_interval,
        )
        imported = _checkpoint_controller_call(
            lane=lane,
            action="checkpoint",
            arguments=[
                "--state-root",
                str(lane.state_root),
                "--session",
                lane.session,
                "--handoff",
                str(checkpoint_path),
            ],
            runner=runner,
        )
        imported_projection = _checkpoint_reference_projection(
            reference={key: imported.get(key) for key in {
                "checkpoint_id",
                "artifact_sha256",
                "checkpoint_kind",
                "identity",
                "path",
                "validation",
            }},
            lane=lane,
            binding=binding,
            fixed_fields=fixed_fields,
        )
        waited = _checkpoint_controller_call(
            lane=lane,
            action="wait",
            arguments=[
                "--state-root",
                str(lane.state_root),
                "--session",
                lane.session,
                "--until",
                "checkpoint",
                "--timeout",
                "0",
            ],
            runner=runner,
        )
        if (
            waited.get("condition") != "checkpoint"
            or waited.get("matched") is not True
        ):
            raise _CheckpointLaneFailure("controller_wait_unconfirmed")
        waited_projection = _checkpoint_reference_projection(
            reference=waited.get("last_checkpoint"),
            lane=lane,
            binding=binding,
            fixed_fields=fixed_fields,
        )
        if waited_projection != imported_projection:
            raise _CheckpointLaneFailure("checkpoint_confirmation_changed")
        confirmed_sha256, confirmed_sample = _checkpoint_file_hash_exact(
            checkpoint_path,
            max_bytes=binding["max_bytes"],
        )
        if (
            confirmed_sample != stable_sample
            or confirmed_sha256 != imported_projection["artifact_sha256"]
        ):
            raise _CheckpointLaneFailure("checkpoint_path_changed")
        state = waited.get("state")
        if state not in STATES:
            raise _CheckpointLaneFailure("controller_wait_output_invalid")
        _progress(
            "checkpoint_complete",
            launch_id=campaign["launch_id"],
            target=lane.target,
            session=lane.session,
            status=state,
        )
        return {
            "ok": True,
            "target": lane.target,
            "session": lane.session,
            "state": state,
            "delivery": delivery_state,
            "delivery_sha256": delivery_sha256,
            "checkpoint": imported_projection,
            "elapsed_ms": int((monotonic() - started) * 1000),
        }
    except _CheckpointLaneFailure as exc:
        _progress(
            "checkpoint_failed",
            launch_id=campaign["launch_id"],
            target=lane.target,
            session=lane.session,
            error=exc.error,
        )
        return {
            "ok": False,
            "target": lane.target,
            "session": lane.session,
            "state": "checkpoint_failed",
            "error": exc.error,
            "elapsed_ms": int((monotonic() - started) * 1000),
        }
    except (PuppetError, OSError, KeyError, TypeError, ValueError):
        _progress(
            "checkpoint_failed",
            launch_id=campaign["launch_id"],
            target=lane.target,
            session=lane.session,
            error="checkpoint_worker_failed",
        )
        return {
            "ok": False,
            "target": lane.target,
            "session": lane.session,
            "state": "checkpoint_failed",
            "error": "checkpoint_worker_failed",
            "elapsed_ms": int((monotonic() - started) * 1000),
        }


def collect_checkpoints(
    *,
    campaign: Mapping[str, Any],
    timeout: float,
    _runner: Callable[
        [Sequence[str]], subprocess.CompletedProcess[bytes]
    ] = puppet_fanout._default_runner,
    _monotonic: Callable[[], float] = time.monotonic,
    _sleep: Callable[[float], None] = time.sleep,
    _poll_interval: float = CHECKPOINT_POLL_INTERVAL_SECONDS,
) -> Dict[str, Any]:
    if (
        isinstance(timeout, bool)
        or not isinstance(timeout, (int, float))
        or not math.isfinite(timeout)
        or timeout < 0
        or timeout > MAX_CHECKPOINT_TIMEOUT_SECONDS
    ):
        raise ValidationError(
            "checkpoint timeout must be between zero and 300 seconds"
        )
    if (
        isinstance(_poll_interval, bool)
        or not isinstance(_poll_interval, (int, float))
        or not math.isfinite(_poll_interval)
        or _poll_interval <= 0
        or _poll_interval > 1
    ):
        raise ValidationError("checkpoint poll interval is invalid")
    started = _monotonic()
    plans = [
        Path(campaign["lanes"][target]["plan"])
        for target in campaign["targets"]
    ]
    lanes = puppet_fanout.load_lane_plans(plans)
    results: Dict[str, Dict[str, Any]] = {}
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=len(lanes),
        thread_name_prefix="puppet-launch-checkpoint",
    ) as executor:
        futures = {
            executor.submit(
                _checkpoint_lane,
                campaign=campaign,
                lane=lane,
                timeout=float(timeout),
                runner=_runner,
                monotonic=_monotonic,
                sleep=_sleep,
                poll_interval=_poll_interval,
            ): lane.target
            for lane in lanes
        }
        for future in concurrent.futures.as_completed(futures):
            target = futures[future]
            try:
                results[target] = future.result()
            except Exception:
                lane = next(item for item in lanes if item.target == target)
                results[target] = {
                    "ok": False,
                    "target": target,
                    "session": lane.session,
                    "state": "checkpoint_failed",
                    "error": "checkpoint_worker_failed",
                    "elapsed_ms": int((_monotonic() - started) * 1000),
                }
    ordered = {
        target: results[target]
        for target in campaign["targets"]
    }
    succeeded = [
        target for target in campaign["targets"] if ordered[target]["ok"]
    ]
    failed = [
        target for target in campaign["targets"] if not ordered[target]["ok"]
    ]
    result = {
        "schema": CHECKPOINT_RESULT_SCHEMA,
        "version": LAUNCHER_VERSION,
        "ok": not failed,
        "state": (
            "complete"
            if not failed
            else ("partial" if succeeded else "failed")
        ),
        "action": "checkpoint",
        "launch_id": campaign["launch_id"],
        "campaign_sha256": campaign["campaign_sha256"],
        "targets": list(campaign["targets"]),
        "succeeded_targets": succeeded,
        "failed_targets": failed,
        "lanes": ordered,
        "automatic_review": False,
        "automatic_accept": False,
        "automatic_halt": False,
        "raw_output_retained": False,
        "elapsed_ms": int((_monotonic() - started) * 1000),
    }
    validate_bounded_json(
        result,
        max_depth=8,
        max_items=256,
        max_string=4096,
        reject_sensitive_fields=True,
    )
    return result


def _add_prepare_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--catalog", required=True, type=Path)
    parser.add_argument(
        "--target",
        action="append",
        required=True,
        help="agy, codex, claude, cursor, grok, comma-separated mix, or all",
    )
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--prompt-file", required=True, type=Path)
    parser.add_argument("--launch-id", required=True)
    parser.add_argument("--campaign-root", required=True, type=Path)
    parser.add_argument("--worktree-parent", required=True, type=Path)
    parser.add_argument(
        "--mode",
        action="append",
        default=[],
        help="read, test, mutate, or local_commit; repeat as needed",
    )
    parser.add_argument(
        "--mutation-owner",
        choices=TARGET_ORDER,
        help="single selected target allowed to mutate in a multi-target launch",
    )
    parser.add_argument("--task-profile", default="regular")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="puppet-launch",
        description=(
            "Prepare and run any explicit warm one-to-five-harness Puppet mix "
            "from one operator request."
        ),
    )
    parser.add_argument("--version", action="version", version=LAUNCHER_VERSION)
    commands = parser.add_subparsers(dest="action", required=True)

    catalog = commands.add_parser("catalog-init")
    catalog.add_argument("--out", required=True, type=Path)
    catalog.add_argument("--authorization", required=True, type=Path)
    catalog.add_argument(
        "--manifest",
        action="append",
        required=True,
        help="target=/absolute/path; repeat for every catalog target",
    )
    catalog.add_argument(
        "--profile",
        action="append",
        default=[],
        help="target=/absolute/path; required for every non-AGY target",
    )

    prepare = commands.add_parser("prepare")
    _add_prepare_arguments(prepare)

    run = commands.add_parser("run")
    _add_prepare_arguments(run)
    run.add_argument("--allow-live-launch", action="store_true")
    run.add_argument("--open-views", action="store_true")

    for action in ("status", "attach", "view", "halt"):
        lifecycle = commands.add_parser(action)
        lifecycle.add_argument("--campaign", required=True, type=Path)
    checkpoint = commands.add_parser("checkpoint")
    checkpoint.add_argument("--campaign", required=True, type=Path)
    checkpoint.add_argument(
        "--timeout",
        required=True,
        type=float,
        help=(
            "seconds to wait for each exact checkpoint file after assignment "
            "delivery (0-300); controller calls have their own fixed bounds"
        ),
    )
    return parser


def _prepare_from_args(args: argparse.Namespace) -> Dict[str, Any]:
    return prepare_campaign(
        catalog_path=args.catalog,
        target_values=args.target,
        source_repo=args.repo,
        source_commit=args.commit,
        prompt_path=args.prompt_file,
        launch_id=args.launch_id,
        campaign_root=args.campaign_root,
        worktree_parent=args.worktree_parent,
        mode_values=args.mode,
        mutation_owner_target=args.mutation_owner,
        task_profile=args.task_profile,
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.action == "catalog-init":
            result = initialize_catalog(
                output_path=args.out,
                authorization_path=args.authorization,
                manifest_assignments=args.manifest,
                profile_assignments=args.profile,
            )
            print(json.dumps(result, sort_keys=True))
            return 0
        if args.action == "prepare":
            result = _prepare_from_args(args)
            print(json.dumps(result, sort_keys=True))
            return 0
        if args.action == "run":
            if not args.allow_live_launch:
                raise ValidationError("live launch requires --allow-live-launch")
            campaign = _prepare_from_args(args)
            campaign_path = Path(campaign["roots"]["campaign"]) / "campaign.json"
            _progress(
                "fanout_exec",
                launch_id=campaign["launch_id"],
                campaign=str(campaign_path),
                targets=campaign["targets"],
            )
            execute_fanout(
                _fanout_argv(
                    action="launch",
                    campaign=campaign,
                    allow_live_launch=True,
                    open_views=args.open_views,
                )
            )
            return 0
        campaign = _load_campaign(args.campaign)
        if args.action == "checkpoint":
            result = collect_checkpoints(
                campaign=campaign,
                timeout=args.timeout,
            )
            print(json.dumps(result, sort_keys=True))
            if result["ok"]:
                return 0
            if result["state"] == "partial":
                return 4
            return 2
        _progress(
            "fanout_exec",
            launch_id=campaign["launch_id"],
            campaign=str(Path(args.campaign).resolve(strict=True)),
            action=args.action,
            targets=campaign["targets"],
        )
        execute_fanout(
            _fanout_argv(
                action=args.action,
                campaign=campaign,
            )
        )
        return 0
    except KeyboardInterrupt:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "operator_interrupted",
                    "automatic_cleanup": False,
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 130
    except PuppetError as exc:
        print(json.dumps(exc.as_dict(), sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
