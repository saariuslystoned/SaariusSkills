"""Compile one body-free operator run plan without exercising a harness."""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

from .adapter_manifest import AdapterManifest
from .campaign import validate_campaign_authorization
from .census import adapter_implementation_fingerprint
from .contracts import Contract
from .errors import IdentityError, UnsupportedError, ValidationError
from .handoffs import PROTOCOL_FINGERPRINT
from .safety import (
    canonical_json_bytes,
    paths_overlap,
    sha256_bytes,
    sha256_file,
    validate_bounded_json,
    validate_identifier,
    validate_sha1,
)


OPERATOR_PLAN_SCHEMA = "puppet.operator-run-plan/v1"
OPERATOR_PLAN_STATE = "planning_only"
CONTROLLER_VERSION = "0.1.0-bootstrap"
_MAX_ARTIFACT_BYTES = 1024 * 1024
_GIT_TIMEOUT_SECONDS = 5.0
_GIT_OUTPUT_BYTES = 65536
_PRIVATE_MODE = 0o700
_WAIT_SECONDS = 60.0
_LAUNCH_BLOCKERS = (
    "operator_plan_is_not_launch_authority",
    "doctor_must_pass_at_execution_time",
    "private_profile_must_be_authenticated_at_execution_time",
    "adapter_qualification_must_be_current",
    "human_must_choose_to_execute_launch",
)


def _absolute_path(value: Path | str, *, label: str) -> Path:
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
    return Path(raw)


def _regular_artifact(path: Path | str, *, label: str) -> Dict[str, Any]:
    candidate = _absolute_path(path, label=label)
    try:
        lexical = os.lstat(candidate)
    except OSError as exc:
        raise ValidationError("%s is unavailable" % label) from exc
    if not stat.S_ISREG(lexical.st_mode) or stat.S_ISLNK(lexical.st_mode):
        raise ValidationError("%s must be a regular non-symlink file" % label)
    if lexical.st_size > _MAX_ARTIFACT_BYTES:
        raise ValidationError("%s exceeds the operator-plan size bound" % label)
    return {
        "path": str(candidate),
        "sha256": sha256_file(candidate, max_bytes=_MAX_ARTIFACT_BYTES),
        "bytes": lexical.st_size,
    }


def _private_root(path: Path | str, *, label: str) -> Path:
    candidate = _absolute_path(path, label=label)
    try:
        lexical = os.lstat(candidate)
    except OSError as exc:
        raise ValidationError("%s is unavailable" % label) from exc
    if stat.S_ISLNK(lexical.st_mode) or not stat.S_ISDIR(lexical.st_mode):
        raise ValidationError("%s must be a private directory" % label)
    if lexical.st_uid != os.getuid() or stat.S_IMODE(lexical.st_mode) != _PRIVATE_MODE:
        raise IdentityError("%s must be current-UID 0700" % label)
    return candidate


def _future_profile_root(path: Path | str) -> Path:
    candidate = _absolute_path(path, label="profile root")
    try:
        lexical = os.lstat(candidate)
    except FileNotFoundError:
        if not candidate.parent.is_dir() or candidate.parent.is_symlink():
            raise ValidationError("profile root must have a real existing parent")
    except OSError as exc:
        raise ValidationError("profile root is unavailable") from exc
    else:
        if stat.S_ISLNK(lexical.st_mode) or not stat.S_ISDIR(lexical.st_mode):
            raise ValidationError("existing profile root must be a private directory")
        if lexical.st_uid != os.getuid() or stat.S_IMODE(lexical.st_mode) != _PRIVATE_MODE:
            raise IdentityError("existing profile root must be current-UID 0700")
    return candidate


def _git_executable() -> Path:
    discovered = shutil.which("git", path="/usr/bin:/bin:/usr/local/bin")
    if not discovered:
        raise UnsupportedError("git is unavailable for operator planning")
    path = Path(discovered).resolve(strict=True)
    if not path.is_file() or path.is_symlink():
        raise IdentityError("git executable is unavailable or linked")
    return path


def _git_output(git: Path, repo: Path, arguments: Sequence[str]) -> str:
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
            env={
                "PATH": "/usr/bin:/bin:/usr/local/bin",
                "LC_ALL": "C",
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_GLOBAL": "/dev/null",
                "GIT_OPTIONAL_LOCKS": "0",
            },
            timeout=_GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValidationError("repository identity probe failed") from exc
    if (
        result.returncode != 0
        or len(result.stdout) > _GIT_OUTPUT_BYTES
        or len(result.stderr) > _GIT_OUTPUT_BYTES
    ):
        raise ValidationError("repository identity probe failed")
    try:
        return result.stdout.decode("utf-8").strip()
    except UnicodeDecodeError as exc:
        raise ValidationError("repository identity output is not UTF-8") from exc


def _git_path(value: str, *, repo: Path, label: str) -> Path:
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = repo / candidate
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise IdentityError("%s is unavailable" % label) from exc
    if not resolved.is_dir():
        raise IdentityError("%s is not a directory" % label)
    return resolved


def _repository_identity(repo: Path, *, require_linked_clean: bool) -> Dict[str, Any]:
    git = _git_executable()
    top = Path(_git_output(git, repo, ["rev-parse", "--show-toplevel"])).resolve(
        strict=True
    )
    if top != repo:
        raise IdentityError("selected repository is not its exact Git root")
    branch = _git_output(git, repo, ["symbolic-ref", "--quiet", "--short", "HEAD"])
    if not branch:
        raise IdentityError("selected repository is detached")
    head = validate_sha1(_git_output(git, repo, ["rev-parse", "HEAD"]), "head")
    tree = validate_sha1(
        _git_output(git, repo, ["rev-parse", "HEAD^{tree}"]),
        "tree",
    )
    git_dir = _git_path(
        _git_output(git, repo, ["rev-parse", "--git-dir"]),
        repo=repo,
        label="Git directory",
    )
    common_dir = _git_path(
        _git_output(git, repo, ["rev-parse", "--git-common-dir"]),
        repo=repo,
        label="Git common directory",
    )
    dirty = bool(
        _git_output(
            git,
            repo,
            ["status", "--porcelain=v1", "--untracked-files=normal"],
        )
    )
    linked = git_dir != common_dir
    if require_linked_clean and (dirty or not linked):
        raise IdentityError(
            "mutating operator plans require a clean linked Git worktree"
        )
    return {
        "repo": str(repo),
        "branch": branch,
        "head": head,
        "tree": tree,
        "git_dir": str(git_dir),
        "git_common_dir": str(common_dir),
        "linked_worktree": linked,
        "dirty": dirty,
        "git_executable": str(git),
        "git_executable_sha256": sha256_file(git),
    }


def _current_git_root(current_directory: Optional[Path | str]) -> Path:
    current = Path(
        current_directory if current_directory is not None else Path.cwd()
    ).resolve(strict=True)
    if not current.is_dir() or current.is_symlink():
        raise ValidationError("current directory must be a real directory")
    git = _git_executable()
    return Path(
        _git_output(git, current, ["rev-parse", "--show-toplevel"])
    ).resolve(strict=True)


def _command_base(cli: Path, interpreter: Path) -> list[str]:
    return [str(interpreter), str(cli), "--json"]


def _commands(
    *,
    base: Sequence[str],
    contract: Contract,
    contract_path: Path,
    manifest_path: Path,
    authorization_path: Path,
    prompt_path: Path,
    profile_root: Path,
    proof_root: Path,
    state_root: Path,
    session: str,
    executable_path: Path,
) -> Dict[str, Any]:
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
        "--profile-root",
        str(profile_root),
    ]
    launch = [
        *base,
        "launch",
        "--session",
        session,
        *common,
        "--prompt-file",
        str(prompt_path),
    ]
    if contract.requested_model is not None:
        launch.extend(["--model", contract.requested_model])
    if contract.requested_effort is not None:
        launch.extend(["--effort", contract.requested_effort])
    session_base = ["--state-root", str(state_root), "--session", session]
    result: Dict[str, Any] = {
        "doctor": [*base, "doctor", *common],
        "launch": launch,
        "status": [*base, "status", *session_base],
        "waits": {
            condition: [
                *base,
                "wait",
                *session_base,
                "--until",
                condition,
                "--timeout",
                str(_WAIT_SECONDS),
            ]
            for condition in ("checkpoint", "action-required", "done")
        },
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
    if contract.target == "agy":
        result["profile"] = {
            "supported": False,
            "reason": "agy_private_subscription_profile_unsupported",
        }
    else:
        result["profile"] = {
            "supported": True,
            "init": [
                *base,
                "profile-init",
                "--target",
                contract.target,
                "--profile-root",
                str(profile_root),
                "--executable",
                str(executable_path),
            ],
            "status": [
                *base,
                "profile-status",
                "--profile-root",
                str(profile_root),
            ],
        }
    return result


def compile_operator_plan(
    *,
    contract_path: Path | str,
    manifest_path: Path | str,
    authorization_path: Path | str,
    profile_root: Path | str,
    prompt_path: Path | str,
    session: str,
    run_root: Path | str,
    repo: Optional[Path | str] = None,
    current_directory: Optional[Path | str] = None,
) -> Dict[str, Any]:
    """Return deterministic exact command arrays without checking auth or launching."""

    session = validate_identifier(session, "session")
    contract_artifact = _regular_artifact(contract_path, label="contract")
    manifest_artifact = _regular_artifact(manifest_path, label="manifest")
    authorization_artifact = _regular_artifact(
        authorization_path,
        label="authorization",
    )
    prompt_artifact = _regular_artifact(prompt_path, label="prompt file")
    contract_file = Path(contract_artifact["path"])
    manifest_file = Path(manifest_artifact["path"])
    authorization_file = Path(authorization_artifact["path"])
    prompt_file = Path(prompt_artifact["path"])
    contract = Contract.from_path(contract_file)
    if contract.session_profile != "regular":
        raise UnsupportedError("operator planning currently supports regular only")
    manifest = AdapterManifest.from_path(manifest_file)
    if manifest.target != contract.target:
        raise IdentityError("operator-plan manifest target differs from the contract")
    validate_campaign_authorization(
        authorization_file,
        target=contract.target,
        controller=contract.controller,
        campaign_id=contract.campaign_authorization_id,
    )

    selected = (
        _absolute_path(repo, label="explicit repository")
        if repo is not None
        else _current_git_root(current_directory)
    )
    if not selected.is_dir() or selected.is_symlink():
        raise ValidationError("selected repository must be a real directory")
    if selected != contract.repo:
        raise IdentityError("selected repository differs from the contract repo")
    mutating = bool(contract.allowed_modes & {"mutate", "local_commit"})
    if mutating and (
        contract.candidate_root != selected or contract.supervisor_root is None
    ):
        raise IdentityError(
            "mutating operator plans require explicit supervisor and candidate roots"
        )
    repo_identity = _repository_identity(selected, require_linked_clean=mutating)
    if repo_identity["branch"] != contract.branch:
        raise IdentityError("selected repository branch differs from the contract")
    supervisor_identity = None
    if mutating:
        supervisor_identity = _repository_identity(
            contract.supervisor_root,
            require_linked_clean=False,
        )
        if (
            repo_identity["git_common_dir"]
            != supervisor_identity["git_common_dir"]
        ):
            raise IdentityError(
                "candidate worktree does not belong to the contract supervisor"
            )

    run = _private_root(run_root, label="run root")
    proof = _private_root(run / "proof", label="proof root")
    state = _private_root(run / "state", label="state root")
    profile = _future_profile_root(profile_root)
    if paths_overlap(selected, run) or paths_overlap(selected, profile):
        raise ValidationError("operator roots must remain outside the target repository")
    if paths_overlap(profile, run) or paths_overlap(proof, state):
        raise ValidationError(
            "profile, proof, and state ownership roots must not overlap"
        )

    cli = Path(__file__).resolve(strict=True).parents[1] / "puppet.py"
    cli = cli.resolve(strict=True)
    interpreter = Path(sys.executable).resolve(strict=True)
    base = _command_base(cli, interpreter)
    commands = _commands(
        base=base,
        contract=contract,
        contract_path=contract_file,
        manifest_path=manifest_file,
        authorization_path=authorization_file,
        prompt_path=prompt_file,
        profile_root=profile,
        proof_root=proof,
        state_root=state,
        session=session,
        executable_path=Path(manifest.raw["executable"]["resolved_path"]),
    )
    adapter_sha256 = adapter_implementation_fingerprint()
    blockers = list(_LAUNCH_BLOCKERS)
    if contract.target == "agy":
        blockers.append("agy_private_subscription_profile_unsupported")
    if manifest.raw["adapter_fingerprint"] != adapter_sha256:
        blockers.append("adapter_manifest_source_fingerprint_is_stale")
    if contract.requested_model is not None or contract.requested_effort is not None:
        blockers.append("explicit_model_or_effort_requires_separate_qualification")

    result: Dict[str, Any] = {
        "schema": OPERATOR_PLAN_SCHEMA,
        "state": OPERATOR_PLAN_STATE,
        "entry_mode": "cockpit_explicit" if repo is not None else "direct_git_root",
        "target": contract.target,
        "session_profile": "regular",
        "session": session,
        "branch": contract.branch,
        "launch_authorized": False,
        "blockers": blockers,
        "controller": {
            "version": CONTROLLER_VERSION,
            "adapter_implementation_sha256": adapter_sha256,
            "protocol_sha256": PROTOCOL_FINGERPRINT,
            "interpreter": str(interpreter),
            "interpreter_sha256": sha256_file(interpreter),
            "cli": str(cli),
            "cli_sha256": sha256_file(cli),
        },
        "repository": repo_identity,
        "supervisor_repository": supervisor_identity,
        "roots": {
            "run": str(run),
            "proof": str(proof),
            "state": str(state),
            "profile": str(profile),
        },
        "artifacts": {
            "contract": contract_artifact,
            "manifest": manifest_artifact,
            "authorization": authorization_artifact,
            "input_payload": prompt_artifact,
        },
        "commands": commands,
    }
    result["plan_sha256"] = sha256_bytes(canonical_json_bytes(result))
    validate_bounded_json(
        result,
        max_depth=8,
        max_items=192,
        max_string=4096,
        reject_sensitive_fields=True,
    )
    return result


__all__ = [
    "CONTROLLER_VERSION",
    "OPERATOR_PLAN_SCHEMA",
    "OPERATOR_PLAN_STATE",
    "compile_operator_plan",
]
