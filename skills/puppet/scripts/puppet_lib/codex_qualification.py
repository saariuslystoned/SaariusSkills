"""Non-promotable Codex regular-session paired qualification substrate.

One accepted Codex worktree receipt is never public launch authority.  This
module can bind that positive run to a later ordinary-control run, one
structurally observed read-only native viewer, exact terminal lease history,
and the same private subscription profile.  The resulting create-only paired
receipt is controller-attested but deliberately has no manifest, launch, or
promotion consumer.

No function in this module reads a pane, transcript, prompt, auth value, or
configuration content.
"""

from __future__ import annotations

import os
import stat
import subprocess
import time
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional

from .conformance import tree_fingerprint
from .authority import (
    AUTHORITY_ID,
    attest_qualification,
    controller_authority_root,
    lease_owner,
    verify_qualification_attestation,
)
from .errors import ConflictError, IdentityError, UnsupportedError, ValidationError
from .journal import Journal
from .safety import (
    canonical_json_bytes,
    ensure_within,
    paths_overlap,
    read_json,
    reject_symlink_components,
    sha256_bytes,
    sha256_file,
    validate_bounded_json,
    validate_identifier,
    validate_sha1,
    validate_sha256,
)


PAIR_SCHEMA_VERSION = 5
PAIR_KIND = "codex_regular_paired_qualification_substrate"
ENTRY_SOURCE_SCHEMA = "puppet.codex-positive-entry-source/v1"
CONTROL_SOURCE_SCHEMA = "puppet.codex-ordinary-control-source/v1"
NATIVE_VIEW_SCHEMA = "puppet.codex-native-view-observation/v1"
NATIVE_VIEW_STATE = "read_only_attached_and_detached"
NATIVE_VIEW_NAME = "codex-native-view.json"
NATIVE_VIEW_ATTESTATION_SCHEMA_VERSION = 1
ORDINARY_REPOSITORY_SCHEMA = "puppet.codex-ordinary-repository/v1"
ORDINARY_REPOSITORY_BRANCH = "puppet-ordinary-control"

PAIR_BLOCKERS = (
    "paired receipt requires independent controller verification",
    "paired receipt is not accepted by adapter qualification",
    "public Codex launch remains fenced",
)

_PROCESS_FIELDS = {
    "identity_version",
    "pid",
    "start",
    "kernel_birth_id",
    "command",
    "executable_path",
    "device",
    "inode",
}
_LEASE_REF_FIELDS = {
    "session",
    "generation",
    "state",
    "lease_sha256",
    "owner_sha256",
    "process_sha256",
    "ledger_sequence",
    "ledger_entry_hash",
}
_CONTROL_SOURCE_FIELDS = {
    "schema",
    "positive_receipt",
    "run_id",
    "session",
    "controller",
    "campaign_id",
    "goal_fingerprint",
    "subscription_profile_sha256",
    "yolo_mapping_sha256",
    "candidate_head",
    "process_sha256",
    "tmux_sha256",
    "terminal_lease",
    "receipt_attestation_sequence",
}
_ENTRY_SOURCE_FIELDS = {
    "schema",
    "target",
    "entry_mode",
    "operator_plan",
    "run_id",
    "session",
    "controller",
    "campaign_id",
    "goal_fingerprint",
    "contract",
    "manifest",
    "authorization",
    "profile",
    "workspace",
}
_NATIVE_VIEW_FIELDS = {
    "schema",
    "target",
    "run_id",
    "controller",
    "campaign_id",
    "goal_fingerprint",
    "session",
    "state",
    "ready_checkpoint_id",
    "attach_argv_sha256",
    "tmux_sha256",
    "target_process_sha256",
    "viewer_client_sha256",
    "viewer_process_sha256",
    "viewer_client",
    "viewer_process",
    "read_only",
    "attached",
    "detached",
    "target_alive_after_detach",
    "body_capture_performed",
    "raw_retained",
    "controller_attestation",
}
_RECEIPT_REF_FIELDS = {
    "path",
    "sha256",
    "run_id",
    "session",
    "launch_plan_sha256",
    "accepted_checkpoint_id",
    "acceptance_sha256",
    "halt_receipt_sha256",
    "process_sha256",
    "tmux_sha256",
    "terminal_lease",
}
_POSITIVE_REF_FIELDS = _RECEIPT_REF_FIELDS | {"workspace_isolation"}
_PAIR_FIELDS = {
    "schema_version",
    "kind",
    "run_id",
    "target",
    "session_profile",
    "result",
    "controller",
    "campaign_id",
    "goal_fingerprint",
    "executable_fingerprint",
    "execution_fingerprint",
    "version_fingerprint",
    "platform_fingerprint",
    "adapter_fingerprint",
    "protocol_fingerprint",
    "yolo_mapping_sha256",
    "launch_plan_sha256",
    "subscription_profile_sha256",
    "instruction_policy_fingerprint",
    "capabilities",
    "accepted_checkpoint_id",
    "acceptance_sha256",
    "halt_receipt_sha256",
    "private_profile_root",
    "runtime_binding",
    "positive",
    "ordinary_control",
    "native_view",
    "entry_claim",
    "no_bleed",
    "receipt_attestation_order",
    "public_launch_authorized",
    "promotion_authorized",
    "independent_verification_required",
    "raw_retained",
    "blockers",
    "controller_attestation",
}
_ORDINARY_REPOSITORY_FIELDS = {
    "schema",
    "target",
    "role",
    "run_id",
    "workspace_root",
    "git_directory",
    "branch",
    "head_state",
    "git_metadata_sha256",
    "agents_md_absent",
    "system_config_disabled",
    "global_config_disabled",
    "templates_disabled",
    "raw_retained",
}


def _ordinary_repository_directory_identity(
    path: Path, *, label: str, private: bool
) -> Dict[str, Any]:
    candidate = Path(path)
    if not candidate.is_absolute():
        raise ValidationError("%s must be absolute" % label)
    try:
        lexical = candidate.lstat()
        resolved = candidate.resolve(strict=True)
        details = resolved.stat()
    except OSError as exc:
        raise ValidationError("%s is unavailable" % label) from exc
    if (
        candidate != resolved
        or stat.S_ISLNK(lexical.st_mode)
        or not stat.S_ISDIR(lexical.st_mode)
        or (lexical.st_dev, lexical.st_ino) != (details.st_dev, details.st_ino)
    ):
        raise IdentityError("%s must be one canonical non-symlink directory" % label)
    mode = stat.S_IMODE(details.st_mode)
    if details.st_uid != os.getuid() or (private and mode != 0o700):
        raise IdentityError(
            "%s must be current-UID%s"
            % (label, " 0700" if private else "")
        )
    return {
        "path": str(resolved),
        "device": details.st_dev,
        "inode": details.st_ino,
        "uid": details.st_uid,
        "mode": mode,
    }


def _ordinary_repository_git(
    workspace_root: Path,
    arguments: list[str],
    *,
    accepted_returncodes: tuple[int, ...] = (0,),
) -> tuple[int, str]:
    from .operator_plan import _git_executable

    git = _git_executable()
    try:
        result = subprocess.run(
            [
                str(git),
                "-c",
                "core.fsmonitor=false",
                "-C",
                str(workspace_root),
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
            timeout=10.0,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValidationError("Codex ordinary repository operation failed") from exc
    if (
        result.returncode not in accepted_returncodes
        or len(result.stdout) > 8192
        or len(result.stderr) > 8192
    ):
        raise ValidationError("Codex ordinary repository operation failed")
    try:
        return result.returncode, result.stdout.decode("utf-8").strip()
    except UnicodeDecodeError as exc:
        raise ValidationError(
            "Codex ordinary repository output is not UTF-8"
        ) from exc


def validate_codex_ordinary_repository(value: Any) -> Dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _ORDINARY_REPOSITORY_FIELDS:
        raise ValidationError("Codex ordinary repository fields are invalid")
    result = dict(value)
    if (
        result.get("schema") != ORDINARY_REPOSITORY_SCHEMA
        or result.get("target") != "codex"
        or result.get("role") != "ordinary_control"
        or result.get("branch") != ORDINARY_REPOSITORY_BRANCH
        or result.get("head_state") != "unborn"
        or result.get("agents_md_absent") is not True
        or result.get("system_config_disabled") is not True
        or result.get("global_config_disabled") is not True
        or result.get("templates_disabled") is not True
        or result.get("raw_retained") is not False
    ):
        raise ValidationError("Codex ordinary repository contract is invalid")
    validate_identifier(result.get("run_id"), "Codex ordinary repository run id")
    validate_sha256(
        result.get("git_metadata_sha256"),
        "Codex ordinary git metadata fingerprint",
    )
    workspace = result.get("workspace_root")
    git_directory = result.get("git_directory")
    expected_identity_fields = {"path", "device", "inode", "uid", "mode"}
    if (
        not isinstance(workspace, Mapping)
        or set(workspace) != expected_identity_fields
        or not isinstance(git_directory, Mapping)
        or set(git_directory) != expected_identity_fields
    ):
        raise ValidationError("Codex ordinary repository identity is invalid")
    for label, identity in (
        ("workspace root", workspace),
        ("git directory", git_directory),
    ):
        if (
            not isinstance(identity.get("path"), str)
            or not Path(identity["path"]).is_absolute()
            or isinstance(identity.get("device"), bool)
            or not isinstance(identity.get("device"), int)
            or identity["device"] <= 0
            or isinstance(identity.get("inode"), bool)
            or not isinstance(identity.get("inode"), int)
            or identity["inode"] <= 0
            or identity.get("uid") != os.getuid()
            or isinstance(identity.get("mode"), bool)
            or not isinstance(identity.get("mode"), int)
        ):
            raise ValidationError("Codex ordinary %s identity is invalid" % label)
    if Path(git_directory["path"]) != Path(workspace["path"]) / ".git":
        raise IdentityError("Codex ordinary git directory escaped its workspace")
    return result


def initialize_codex_ordinary_repository(
    workspace_root: Path, *, run_id: str
) -> Dict[str, Any]:
    """Create the minimal source-free git boundary required by the Codex TUI."""

    workspace = _ordinary_repository_directory_identity(
        workspace_root, label="Codex ordinary workspace", private=True
    )
    if (workspace_root / "AGENTS.md").exists():
        raise ConflictError("Codex ordinary workspace contains AGENTS.md")
    git_directory = workspace_root / ".git"
    if git_directory.exists() or git_directory.is_symlink():
        raise ConflictError("Codex ordinary workspace is already a repository")
    _ordinary_repository_git(
        workspace_root,
        [
            "init",
            "--quiet",
            "--initial-branch=" + ORDINARY_REPOSITORY_BRANCH,
            "--template=",
        ],
    )
    git_directory.chmod(0o700)
    git_identity = _ordinary_repository_directory_identity(
        git_directory, label="Codex ordinary git directory", private=True
    )
    _, top = _ordinary_repository_git(
        workspace_root, ["rev-parse", "--show-toplevel"]
    )
    _, branch = _ordinary_repository_git(
        workspace_root, ["symbolic-ref", "--short", "HEAD"]
    )
    head_returncode, head = _ordinary_repository_git(
        workspace_root,
        ["rev-parse", "--verify", "HEAD"],
        accepted_returncodes=(0, 128),
    )
    if (
        Path(top).resolve(strict=True) != workspace_root.resolve(strict=True)
        or branch != ORDINARY_REPOSITORY_BRANCH
        or head_returncode == 0
        or head
    ):
        raise IdentityError("Codex ordinary repository initialization changed")
    return validate_codex_ordinary_repository(
        {
            "schema": ORDINARY_REPOSITORY_SCHEMA,
            "target": "codex",
            "role": "ordinary_control",
            "run_id": validate_identifier(run_id, "run id"),
            "workspace_root": workspace,
            "git_directory": git_identity,
            "branch": branch,
            "head_state": "unborn",
            "git_metadata_sha256": tree_fingerprint(
                git_directory, excluded_prefix=()
            ),
            "agents_md_absent": True,
            "system_config_disabled": True,
            "global_config_disabled": True,
            "templates_disabled": True,
            "raw_retained": False,
        }
    )


def revalidate_codex_ordinary_repository(
    value: Mapping[str, Any],
) -> Dict[str, Any]:
    result = validate_codex_ordinary_repository(value)
    workspace_root = Path(result["workspace_root"]["path"])
    git_directory = Path(result["git_directory"]["path"])
    if (
        _ordinary_repository_directory_identity(
            workspace_root, label="Codex ordinary workspace", private=True
        )
        != result["workspace_root"]
        or _ordinary_repository_directory_identity(
            git_directory, label="Codex ordinary git directory", private=True
        )
        != result["git_directory"]
        or (workspace_root / "AGENTS.md").exists()
    ):
        raise IdentityError("Codex ordinary repository identity changed")
    _, branch = _ordinary_repository_git(
        workspace_root, ["symbolic-ref", "--short", "HEAD"]
    )
    head_returncode, head = _ordinary_repository_git(
        workspace_root,
        ["rev-parse", "--verify", "HEAD"],
        accepted_returncodes=(0, 128),
    )
    if (
        branch != ORDINARY_REPOSITORY_BRANCH
        or head_returncode == 0
        or head
        or tree_fingerprint(git_directory, excluded_prefix=())
        != result["git_metadata_sha256"]
    ):
        raise IdentityError("Codex ordinary repository metadata changed")
    return result


def _pair_sha(first: Any, second: Any) -> str:
    return sha256_bytes(canonical_json_bytes([first, second]))


def _canonical_file(path: Path | str, label: str) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = candidate.resolve(strict=True)
    if candidate.is_symlink() or not candidate.is_file():
        raise ValidationError("%s is unavailable or a symlink" % label)
    resolved = candidate.resolve(strict=True)
    if resolved != candidate or os.path.normpath(str(candidate)) != str(candidate):
        raise IdentityError("%s is not canonical" % label)
    return resolved


def _current_repository_tree(repository: Path) -> str:
    from .operator_plan import _git_executable, _git_output

    return validate_sha1(
        _git_output(
            _git_executable(),
            repository,
            ["rev-parse", "HEAD^{tree}"],
        ),
        "current repository tree",
    )


def _validated_entry_plan(
    path: Path,
    *,
    run_id: str,
    session: str,
    controller: str,
    campaign_id: str,
    goal_fingerprint: str,
    manifest_path: Path,
    manifest_fingerprint: str,
    authorization_path: Path,
    profile_root: Path,
    subscription_profile_sha256: str,
    workspace_isolation: Mapping[str, Any],
) -> Dict[str, Any]:
    """Recompile and bind the exact prelaunch operator plan to one positive run."""

    from .adapter_manifest import AdapterManifest
    from .campaign import validate_campaign_authorization
    from .contracts import Contract
    from .operator_plan import (
        OPERATOR_PLAN_SCHEMA,
        OPERATOR_PLAN_STATE,
        compile_operator_plan,
    )

    path = _canonical_file(path, "Codex operator entry plan")
    manifest_path = _canonical_file(manifest_path, "Codex entry-plan manifest")
    authorization_path = _canonical_file(
        authorization_path, "Codex entry-plan authorization"
    )
    profile_root = _canonical_directory(
        profile_root, "Codex entry-plan private profile"
    )
    run_id = validate_identifier(run_id, "Codex entry run id")
    session = validate_identifier(session, "Codex entry session")
    controller = validate_identifier(controller, "Codex entry controller")
    campaign_id = validate_identifier(campaign_id, "Codex entry campaign")
    validate_sha256(goal_fingerprint, "Codex entry goal fingerprint")
    validate_sha256(manifest_fingerprint, "Codex entry manifest fingerprint")
    validate_sha256(
        subscription_profile_sha256,
        "Codex entry subscription profile fingerprint",
    )
    plan = read_json(path, max_bytes=1024 * 1024, reject_sensitive_fields=True)
    expected_fields = {
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
        "target_gate",
        "plan_sha256",
    }
    if not isinstance(plan, Mapping) or set(plan) != expected_fields:
        raise ValidationError("Codex operator entry plan fields do not match schema")
    mode = plan.get("entry_mode")
    repository = plan.get("repository")
    artifacts = plan.get("artifacts")
    roots = plan.get("roots")
    if (
        plan.get("schema") != OPERATOR_PLAN_SCHEMA
        or plan.get("state") != OPERATOR_PLAN_STATE
        or plan.get("target") != "codex"
        or plan.get("session_profile") != "regular"
        or plan.get("session") != session
        or plan.get("launch_authorized") is not False
        or mode not in {"direct_git_root", "cockpit_explicit"}
        or not isinstance(repository, Mapping)
        or not isinstance(artifacts, Mapping)
        or set(artifacts)
        != {"contract", "manifest", "authorization", "input_payload"}
        or not isinstance(roots, Mapping)
        or set(roots) != {"run", "proof", "state", "profile"}
    ):
        raise IdentityError(
            "Codex direct-repository/cockpit entry evidence is not exact"
        )
    for name in ("contract", "manifest", "authorization", "input_payload"):
        reference = artifacts[name]
        if (
            not isinstance(reference, Mapping)
            or set(reference) != {"path", "sha256", "bytes"}
            or not isinstance(reference.get("bytes"), int)
            or isinstance(reference.get("bytes"), bool)
            or reference["bytes"] < 0
        ):
            raise ValidationError("Codex operator entry artifact is invalid")
        validate_sha256(reference.get("sha256"), "Codex operator entry artifact")
    plan_manifest_path = _canonical_file(
        artifacts["manifest"]["path"], "Codex operator-plan manifest"
    )
    plan_authorization_path = _canonical_file(
        artifacts["authorization"]["path"], "Codex operator-plan authorization"
    )
    if (
        plan_manifest_path != manifest_path
        or plan_authorization_path != authorization_path
        or roots["profile"] != str(profile_root)
    ):
        raise IdentityError("Codex operator entry source identity changed")
    contract_path = _canonical_file(
        artifacts["contract"]["path"], "Codex operator-plan contract"
    )
    prompt_path = _canonical_file(
        artifacts["input_payload"]["path"], "Codex operator-plan input payload"
    )
    for artifact_path, reference in (
        (contract_path, artifacts["contract"]),
        (manifest_path, artifacts["manifest"]),
        (authorization_path, artifacts["authorization"]),
        (prompt_path, artifacts["input_payload"]),
    ):
        details = artifact_path.stat()
        if (
            details.st_size != reference["bytes"]
            or sha256_file(artifact_path, max_bytes=1024 * 1024)
            != reference["sha256"]
        ):
            raise IdentityError("Codex operator entry artifact fingerprint changed")
    manifest = AdapterManifest.from_path(manifest_path)
    contract = Contract.from_path(contract_path)
    authorization = validate_campaign_authorization(
        authorization_path,
        target="codex",
        controller=controller,
        campaign_id=campaign_id,
    )
    if (
        manifest.target != "codex"
        or manifest.fingerprint != manifest_fingerprint
        or manifest.raw.get("doctor_only") is not True
        or manifest.raw.get("qualification") is not None
        or contract.target != "codex"
        or contract.session_profile != "regular"
        or contract.controller != controller
        or contract.campaign_authorization_id != campaign_id
        or contract.repo != Path(workspace_isolation["candidate_root"])
        or contract.branch != workspace_isolation["candidate_branch"]
        or contract.requested_model is not None
        or contract.requested_effort is not None
        or (
            contract.run_id is not None
            and contract.run_id != run_id
        )
        or sha256_bytes(canonical_json_bytes(authorization["goal"]))
        != goal_fingerprint
        or plan.get("branch") != workspace_isolation["candidate_branch"]
        or repository.get("repo") != workspace_isolation["candidate_root"]
        or repository.get("branch") != workspace_isolation["candidate_branch"]
        or repository.get("head") != workspace_isolation["candidate_head"]
        or repository.get("tree")
        != _current_repository_tree(Path(workspace_isolation["candidate_root"]))
        or repository.get("linked_worktree") is not True
        or repository.get("dirty") is not False
    ):
        raise IdentityError(
            "Codex direct-repository/cockpit entry evidence is not exact"
        )
    expected = compile_operator_plan(
        contract_path=contract_path,
        manifest_path=manifest_path,
        authorization_path=authorization_path,
        profile_root=profile_root,
        prompt_path=prompt_path,
        session=session,
        run_root=roots["run"],
        repo=Path(workspace_isolation["candidate_root"])
        if mode == "cockpit_explicit"
        else None,
        current_directory=Path(workspace_isolation["candidate_root"]),
    )
    if dict(plan) != expected:
        raise IdentityError("Codex operator entry plan does not recompile exactly")
    supplied_sha = validate_sha256(
        plan.get("plan_sha256"), "operator entry plan fingerprint"
    )
    return {
        "schema": ENTRY_SOURCE_SCHEMA,
        "target": "codex",
        "entry_mode": mode,
        "operator_plan": {
            "path": str(path),
            "sha256": sha256_file(path, max_bytes=1024 * 1024),
            "plan_sha256": supplied_sha,
        },
        "run_id": run_id,
        "session": session,
        "controller": controller,
        "campaign_id": campaign_id,
        "goal_fingerprint": goal_fingerprint,
        "contract": {
            "path": str(contract_path),
            "sha256": artifacts["contract"]["sha256"],
            "fingerprint": contract.fingerprint,
        },
        "manifest": {
            "path": str(manifest_path),
            "sha256": artifacts["manifest"]["sha256"],
            "fingerprint": manifest_fingerprint,
        },
        "authorization": {
            "path": str(authorization_path),
            "sha256": artifacts["authorization"]["sha256"],
        },
        "profile": {
            "root": str(profile_root),
            "sha256": subscription_profile_sha256,
        },
        "workspace": {
            "descriptor_sha256": workspace_isolation["descriptor_sha256"],
            "candidate_root": workspace_isolation["candidate_root"],
            "candidate_branch": workspace_isolation["candidate_branch"],
            "candidate_head": workspace_isolation["candidate_head"],
        },
    }


def build_codex_entry_source(
    entry_plan_path: Path | str,
    **expected: Any,
) -> Dict[str, Any]:
    """Build one exact prelaunch source record for a positive Codex probe."""

    return validate_codex_entry_source(
        _validated_entry_plan(Path(entry_plan_path), **expected)
    )


def validate_codex_entry_source(value: Any) -> Dict[str, Any]:
    """Reopen and recompile one persisted positive-entry source record."""

    if not isinstance(value, Mapping) or set(value) != _ENTRY_SOURCE_FIELDS:
        raise ValidationError("Codex positive-entry source fields are invalid")
    result = dict(value)
    if result.get("schema") != ENTRY_SOURCE_SCHEMA or result.get("target") != "codex":
        raise ValidationError("unsupported Codex positive-entry source schema")
    for name in ("run_id", "session", "controller", "campaign_id"):
        validate_identifier(result.get(name), "Codex entry " + name.replace("_", " "))
    validate_sha256(result.get("goal_fingerprint"), "Codex entry goal fingerprint")
    if result.get("entry_mode") not in {"direct_git_root", "cockpit_explicit"}:
        raise ValidationError("Codex positive entry mode is invalid")
    operator_plan = result.get("operator_plan")
    if (
        not isinstance(operator_plan, Mapping)
        or set(operator_plan) != {"path", "sha256", "plan_sha256"}
    ):
        raise ValidationError("Codex operator-plan reference is invalid")
    for reference_name in ("contract", "manifest"):
        reference = result.get(reference_name)
        if (
            not isinstance(reference, Mapping)
            or set(reference) != {"path", "sha256", "fingerprint"}
        ):
            raise ValidationError("Codex entry %s reference is invalid" % reference_name)
        validate_sha256(reference.get("fingerprint"), reference_name + " fingerprint")
    authorization = result.get("authorization")
    if (
        not isinstance(authorization, Mapping)
        or set(authorization) != {"path", "sha256"}
    ):
        raise ValidationError("Codex entry authorization reference is invalid")
    profile = result.get("profile")
    if not isinstance(profile, Mapping) or set(profile) != {"root", "sha256"}:
        raise ValidationError("Codex entry profile reference is invalid")
    workspace = result.get("workspace")
    if (
        not isinstance(workspace, Mapping)
        or set(workspace)
        != {
            "descriptor_sha256",
            "candidate_root",
            "candidate_branch",
            "candidate_head",
        }
    ):
        raise ValidationError("Codex entry workspace reference is invalid")
    for reference in (
        operator_plan,
        result["contract"],
        result["manifest"],
        authorization,
    ):
        if not Path(str(reference.get("path", ""))).is_absolute():
            raise ValidationError("Codex entry artifact path is invalid")
        validate_sha256(reference.get("sha256"), "Codex entry artifact fingerprint")
    validate_sha256(profile.get("sha256"), "Codex entry profile fingerprint")
    validate_sha256(
        workspace.get("descriptor_sha256"), "Codex entry workspace descriptor"
    )
    validate_sha1(workspace.get("candidate_head"), "Codex entry candidate head")
    rebuilt = _validated_entry_plan(
        Path(operator_plan["path"]),
        run_id=result["run_id"],
        session=result["session"],
        controller=result["controller"],
        campaign_id=result["campaign_id"],
        goal_fingerprint=result["goal_fingerprint"],
        manifest_path=Path(result["manifest"]["path"]),
        manifest_fingerprint=result["manifest"]["fingerprint"],
        authorization_path=Path(authorization["path"]),
        profile_root=Path(profile["root"]),
        subscription_profile_sha256=profile["sha256"],
        workspace_isolation=workspace,
    )
    if result != rebuilt:
        raise IdentityError("Codex positive-entry source changed")
    validate_bounded_json(
        result,
        max_depth=6,
        max_items=96,
        max_string=4096,
        reject_sensitive_fields=True,
    )
    return result


def _canonical_directory(path: Path | str, label: str) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = candidate.resolve(strict=True)
    if candidate.is_symlink() or not candidate.is_dir():
        raise ValidationError("%s is unavailable or a symlink" % label)
    resolved = candidate.resolve(strict=True)
    if resolved != candidate or os.path.normpath(str(candidate)) != str(candidate):
        raise IdentityError("%s is not canonical" % label)
    return resolved


def _write_new_json(path: Path, value: Mapping[str, Any]) -> tuple[int, int]:
    """Durably create one JSON artifact without replacing any preimage."""

    validate_bounded_json(
        value,
        max_depth=12,
        max_items=320,
        max_string=4096,
        reject_sensitive_fields=True,
    )
    path = Path(path)
    if not path.is_absolute():
        raise ValidationError("create-only artifact path must be absolute")
    parent = path.parent.resolve(strict=True)
    parent_details = parent.stat()
    if (
        parent.is_symlink()
        or not parent.is_dir()
        or parent_details.st_uid != os.getuid()
        or stat.S_IMODE(parent_details.st_mode) != 0o700
    ):
        raise IdentityError("create-only artifact parent must be current-UID 0700")
    reject_symlink_components(path, allow_missing_leaf=True)
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(str(path), flags, 0o600)
    except FileExistsError as exc:
        raise ConflictError("%s already exists" % path.name) from exc
    created_details = os.fstat(descriptor)
    created_identity = (created_details.st_dev, created_details.st_ino)
    try:
        payload = canonical_json_bytes(dict(value)) + b"\n"
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        directory = os.open(str(parent), os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        details = path.lstat()
        if not stat.S_ISREG(details.st_mode):
            raise IdentityError("create-only artifact identity changed")
        if (details.st_dev, details.st_ino) != created_identity:
            raise IdentityError("create-only artifact identity changed")
        return created_identity
    except BaseException:
        try:
            details = path.lstat()
            if (
                stat.S_ISREG(details.st_mode)
                and (details.st_dev, details.st_ino) == created_identity
            ):
                path.unlink()
        except FileNotFoundError:
            pass
        raise


def _receipt_session(receipt_path: Path, receipt: Mapping[str, Any]) -> str:
    from .adapter_manifest import validate_qualification_state_schema

    state = validate_qualification_state_schema(
        read_json(
            receipt_path.parent / "state.json",
            max_bytes=131072,
            reject_sensitive_fields=True,
        )
    )
    if state.get("run_id") != receipt.get("run_id"):
        raise IdentityError("Codex qualification state run changed")
    return validate_identifier(state.get("session"), "Codex qualification session")


def _receipt_artifacts(
    receipt_path: Path, receipt: Mapping[str, Any]
) -> Dict[str, Any]:
    from .adapter_manifest import _qualification_artifacts
    from .instructions import validate_instruction_manifest
    from .launch import validate_admitted_launch_plan

    paths = _qualification_artifacts(receipt_path, dict(receipt))
    session = _receipt_session(receipt_path, receipt)
    launch = validate_admitted_launch_plan(
        read_json(
            paths["launch_plan"],
            max_bytes=131072,
            reject_sensitive_fields=True,
        ),
        expected_target="codex",
        expected_session=session,
        expected_run_id=receipt["run_id"],
    )
    profile = read_json(
        paths["subscription_profile"],
        max_bytes=131072,
        reject_sensitive_fields=True,
    )
    evidence = read_json(
        paths["evidence"],
        max_bytes=131072,
        reject_sensitive_fields=True,
    )
    instructions = validate_instruction_manifest(
        read_json(
            paths["instructions"],
            max_bytes=131072,
            reject_sensitive_fields=True,
        ),
        target="codex",
    )
    descriptor = (
        read_json(
            paths["workspace_descriptor"],
            max_bytes=131072,
            reject_sensitive_fields=True,
        )
        if "workspace_descriptor" in paths
        else None
    )
    return {
        "paths": paths,
        "launch": launch,
        "profile": profile,
        "evidence": evidence,
        "instructions": instructions,
        "descriptor": descriptor,
    }


def _attestation_sequence(receipt: Mapping[str, Any], label: str) -> int:
    attestation = receipt.get("controller_attestation")
    sequence = (
        attestation.get("ledger_sequence")
        if isinstance(attestation, Mapping)
        else None
    )
    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence <= 0:
        raise ValidationError("%s receipt attestation sequence is invalid" % label)
    return sequence


def _validate_lease_ref(value: Any) -> Dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _LEASE_REF_FIELDS:
        raise ValidationError("Codex terminal lease reference is invalid")
    result = dict(value)
    validate_identifier(result.get("session"), "terminal lease session")
    generation = result.get("generation")
    sequence = result.get("ledger_sequence")
    if (
        isinstance(generation, bool)
        or not isinstance(generation, int)
        or generation <= 0
        or isinstance(sequence, bool)
        or not isinstance(sequence, int)
        or sequence <= 0
        or result.get("state") != "halted"
    ):
        raise ValidationError("Codex terminal lease state is invalid")
    for name in (
        "lease_sha256",
        "owner_sha256",
        "process_sha256",
        "ledger_entry_hash",
    ):
        validate_sha256(result.get(name), name.replace("_", " "))
    return result


def _terminal_lease_ref(
    *,
    receipt_path: Path,
    receipt: Mapping[str, Any],
    artifacts: Mapping[str, Any],
    session: str,
    authority_root: Optional[Path],
) -> Dict[str, Any]:
    """Find the exact halted lease row for one already terminal probe."""

    run_root = receipt_path.parent
    if run_root.parent.name != "probes":
        raise IdentityError("Codex receipt is outside the canonical probe topology")
    proof_root = run_root.parent.parent
    expected_owner = lease_owner(
        activity="probe",
        run_id=receipt["run_id"],
        campaign_id=receipt["campaign_id"],
        goal_fingerprint=receipt["goal_fingerprint"],
        proof_root=proof_root,
        state_root=run_root,
    )
    expected_instruction = sha256_file(
        artifacts["paths"]["instructions"], max_bytes=131072
    )
    expected_process = artifacts["evidence"].get("process")
    if (
        not isinstance(expected_process, Mapping)
        or set(expected_process) != _PROCESS_FIELDS
    ):
        raise ValidationError("Codex receipt target process identity is invalid")
    root = controller_authority_root(authority_root)
    rows = Journal(root / "session-lease-history.codex").snapshot()
    matches = []
    for row in rows:
        event = row.get("event")
        lease = event.get("lease") if isinstance(event, Mapping) else None
        if (
            event != {"kind": "session_lease", "lease": lease}
            or not isinstance(lease, Mapping)
            or lease.get("session") != session
            or lease.get("target") != "codex"
            or lease.get("controller") != receipt["controller"]
            or lease.get("owner") != expected_owner
            or lease.get("instruction_manifest_sha256") != expected_instruction
            or lease.get("state") != "halted"
            or lease.get("process") != expected_process
        ):
            continue
        matches.append((row, dict(lease)))
    if len(matches) != 1:
        raise IdentityError("Codex receipt lacks one exact terminal lease row")
    row, lease = matches[0]
    return _validate_lease_ref(
        {
            "session": session,
            "generation": lease["generation"],
            "state": "halted",
            "lease_sha256": sha256_bytes(canonical_json_bytes(lease)),
            "owner_sha256": sha256_bytes(canonical_json_bytes(expected_owner)),
            "process_sha256": sha256_bytes(canonical_json_bytes(expected_process)),
            "ledger_sequence": row["sequence"],
            "ledger_entry_hash": row["entry_hash"],
        }
    )


def build_codex_control_source(
    positive_receipt_path: Path | str,
    *,
    authority_root: Optional[Path] = None,
    current_manifest: Optional[Any] = None,
    server_process_fn: Optional[Any] = None,
    tmux_factory: Optional[Any] = None,
    _verify_receipt_fn: Optional[Callable[..., Dict[str, Any]]] = None,
    _terminal_lease_fn: Callable[..., Dict[str, Any]] = _terminal_lease_ref,
) -> Dict[str, Any]:
    """Bind an ordinary control to one earlier positive terminal run."""

    from .adapter_manifest import verify_qualification_receipt

    verify_receipt_fn = _verify_receipt_fn or verify_qualification_receipt
    path = _canonical_file(positive_receipt_path, "positive Codex receipt")
    receipt = verify_receipt_fn(
        path,
        _authority_root=authority_root,
        _current_manifest=current_manifest,
        _server_process_fn=server_process_fn,
        _tmux_factory=tmux_factory,
    )
    if (
        receipt.get("target") != "codex"
        or receipt.get("session_profile") != "regular"
        or receipt.get("workspace_isolation") is None
        or receipt.get("plane_activation") is not None
    ):
        raise ValidationError(
            "Codex ordinary control requires one positive worktree receipt"
        )
    validate_codex_entry_source(receipt.get("codex_entry_source"))
    artifacts = _receipt_artifacts(path, receipt)
    session = _receipt_session(path, receipt)
    lease = _terminal_lease_fn(
        receipt_path=path,
        receipt=receipt,
        artifacts=artifacts,
        session=session,
        authority_root=authority_root,
    )
    process = artifacts["evidence"].get("process")
    tmux = artifacts["evidence"].get("tmux")
    workspace = receipt["workspace_isolation"]
    value = {
        "schema": CONTROL_SOURCE_SCHEMA,
        "positive_receipt": {
            "path": str(path),
            "sha256": sha256_file(path, max_bytes=131072),
        },
        "run_id": receipt["run_id"],
        "session": session,
        "controller": receipt["controller"],
        "campaign_id": receipt["campaign_id"],
        "goal_fingerprint": receipt["goal_fingerprint"],
        "subscription_profile_sha256": receipt["subscription_profile_sha256"],
        "yolo_mapping_sha256": receipt["yolo_mapping_sha256"],
        "candidate_head": workspace["candidate_head"],
        "process_sha256": sha256_bytes(canonical_json_bytes(process)),
        "tmux_sha256": sha256_bytes(canonical_json_bytes(tmux)),
        "terminal_lease": lease,
        "receipt_attestation_sequence": _attestation_sequence(receipt, "positive"),
    }
    return validate_codex_control_source(value)


def validate_codex_control_source(value: Any) -> Dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _CONTROL_SOURCE_FIELDS:
        raise ValidationError("Codex ordinary-control source fields are invalid")
    result = dict(value)
    if result.get("schema") != CONTROL_SOURCE_SCHEMA:
        raise ValidationError("unsupported Codex ordinary-control source schema")
    reference = result.get("positive_receipt")
    if (
        not isinstance(reference, Mapping)
        or set(reference) != {"path", "sha256"}
        or not Path(str(reference.get("path", ""))).is_absolute()
    ):
        raise ValidationError("Codex positive receipt reference is invalid")
    validate_sha256(reference.get("sha256"), "positive receipt fingerprint")
    for name in ("run_id", "session", "controller", "campaign_id"):
        validate_identifier(result.get(name), name.replace("_", " "))
    for name in (
        "goal_fingerprint",
        "subscription_profile_sha256",
        "yolo_mapping_sha256",
        "process_sha256",
        "tmux_sha256",
    ):
        validate_sha256(result.get(name), name.replace("_", " "))
    validate_sha1(result.get("candidate_head"), "positive candidate head")
    result["terminal_lease"] = _validate_lease_ref(result.get("terminal_lease"))
    sequence = result.get("receipt_attestation_sequence")
    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence <= 0:
        raise ValidationError("positive receipt attestation sequence is invalid")
    validate_bounded_json(
        result,
        max_depth=5,
        max_items=64,
        max_string=4096,
        reject_sensitive_fields=True,
    )
    return result


def _native_attach_argv(evidence: Mapping[str, Any]) -> list[str]:
    tmux = evidence.get("tmux")
    if not isinstance(tmux, Mapping):
        raise ValidationError("Codex native-view tmux identity is unavailable")
    binary = tmux.get("tmux_binary_identity")
    if not isinstance(binary, Mapping):
        raise ValidationError("Codex native-view tmux executable is unavailable")
    return [
        binary["path"],
        "-f",
        os.devnull,
        "-S",
        tmux["socket"],
        "attach-session",
        "-r",
        "-E",
        "-t",
        tmux["session"],
    ]


def _native_view_event(core: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "schema_version": NATIVE_VIEW_ATTESTATION_SCHEMA_VERSION,
        "kind": "codex_native_view_observation",
        "observation_digest": sha256_bytes(canonical_json_bytes(core)),
        "run_id": core["run_id"],
        "session": core["session"],
        "target_process_sha256": core["target_process_sha256"],
        "tmux_sha256": core["tmux_sha256"],
        "viewer_client_sha256": core["viewer_client_sha256"],
        "viewer_process_sha256": core["viewer_process_sha256"],
    }


def _attest_native_view(
    core: Mapping[str, Any], *, authority_root: Optional[Path]
) -> Dict[str, Any]:
    root = controller_authority_root(authority_root)
    event = _native_view_event(core)
    request_id = "codex-view-%s" % event["observation_digest"][:40]
    row = Journal(root / "codex-native-view-observations").append(
        request_id=request_id,
        event=event,
    )
    return {
        "schema_version": NATIVE_VIEW_ATTESTATION_SCHEMA_VERSION,
        "authority_id": AUTHORITY_ID,
        "authority_root": str(root),
        "request_id": request_id,
        "ledger_sequence": row["sequence"],
        "ledger_entry_hash": row["entry_hash"],
        "observation_digest": event["observation_digest"],
    }


def _verify_native_view_attestation(
    core: Mapping[str, Any],
    attestation: Any,
    *,
    authority_root: Optional[Path],
) -> None:
    expected_fields = {
        "schema_version",
        "authority_id",
        "authority_root",
        "request_id",
        "ledger_sequence",
        "ledger_entry_hash",
        "observation_digest",
    }
    root = controller_authority_root(authority_root)
    if (
        not isinstance(attestation, Mapping)
        or set(attestation) != expected_fields
        or attestation.get("schema_version")
        != NATIVE_VIEW_ATTESTATION_SCHEMA_VERSION
        or attestation.get("authority_id") != AUTHORITY_ID
        or attestation.get("authority_root") != str(root)
    ):
        raise ValidationError("Codex native-view controller attestation is invalid")
    validate_identifier(
        attestation.get("request_id"), "native-view attestation request"
    )
    for name in ("ledger_entry_hash", "observation_digest"):
        validate_sha256(attestation.get(name), name.replace("_", " "))
    sequence = attestation.get("ledger_sequence")
    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence <= 0:
        raise ValidationError("Codex native-view attestation sequence is invalid")
    event = _native_view_event(core)
    if attestation["observation_digest"] != event["observation_digest"]:
        raise IdentityError("Codex native-view observation is not attested")
    row = Journal(root / "codex-native-view-observations").lookup(
        attestation["request_id"]
    )
    if (
        row is None
        or row.get("sequence") != sequence
        or row.get("entry_hash") != attestation["ledger_entry_hash"]
        or row.get("event") != event
    ):
        raise IdentityError("Codex native-view attestation is unavailable")


def _validate_native_view_core(
    result: Dict[str, Any],
    *,
    receipt: Mapping[str, Any],
    session: str,
    evidence: Mapping[str, Any],
    attach_argv: list[str],
) -> Dict[str, Any]:
    if (
        result.get("schema") != NATIVE_VIEW_SCHEMA
        or result.get("target") != "codex"
        or result.get("run_id") != receipt.get("run_id")
        or result.get("controller") != receipt.get("controller")
        or result.get("campaign_id") != receipt.get("campaign_id")
        or result.get("goal_fingerprint") != receipt.get("goal_fingerprint")
        or result.get("session") != session
        or result.get("state") != NATIVE_VIEW_STATE
        or result.get("ready_checkpoint_id")
        != evidence.get("ready", {}).get("checkpoint_id")
        or result.get("read_only") is not True
        or result.get("attached") is not True
        or result.get("detached") is not True
        or result.get("target_alive_after_detach") is not True
        or result.get("body_capture_performed") is not False
        or result.get("raw_retained") is not False
    ):
        raise ValidationError("Codex native-view terminal state is invalid")
    viewer_client = result.get("viewer_client")
    viewer_process = result.get("viewer_process")
    target_process = evidence.get("process")
    tmux = evidence.get("tmux")
    server_process = tmux.get("server_identity") if isinstance(tmux, Mapping) else None
    binary = (
        tmux.get("tmux_binary_identity") if isinstance(tmux, Mapping) else None
    )
    if (
        not isinstance(viewer_client, Mapping)
        or set(viewer_client) != {"pid", "tty", "read_only", "session"}
        or viewer_client.get("read_only") is not True
        or viewer_client.get("session") != session
        or not isinstance(viewer_client.get("tty"), str)
        or not viewer_client["tty"].startswith("/dev/")
        or not isinstance(viewer_process, Mapping)
        or set(viewer_process) != _PROCESS_FIELDS
        or viewer_process.get("pid") != viewer_client.get("pid")
        or viewer_client.get("pid")
        in {
            (target_process or {}).get("pid"),
            (server_process or {}).get("pid"),
        }
        or not isinstance(binary, Mapping)
        or viewer_process.get("executable_path") != binary.get("path")
        or viewer_process.get("device") != binary.get("device")
        or viewer_process.get("inode") != binary.get("inode")
    ):
        raise IdentityError(
            "Codex target, tmux server, and viewer identities are not distinct"
        )
    for name in (
        "ready_checkpoint_id",
        "goal_fingerprint",
        "attach_argv_sha256",
        "tmux_sha256",
        "target_process_sha256",
        "viewer_client_sha256",
        "viewer_process_sha256",
    ):
        validate_sha256(result.get(name), name.replace("_", " "))
    expected = {
        "attach_argv_sha256": sha256_bytes(canonical_json_bytes(attach_argv)),
        "tmux_sha256": sha256_bytes(canonical_json_bytes(evidence.get("tmux"))),
        "target_process_sha256": sha256_bytes(
            canonical_json_bytes(evidence.get("process"))
        ),
        "viewer_client_sha256": sha256_bytes(
            canonical_json_bytes(viewer_client)
        ),
        "viewer_process_sha256": sha256_bytes(
            canonical_json_bytes(viewer_process)
        ),
    }
    if any(result[name] != digest for name, digest in expected.items()):
        raise IdentityError("Codex native-view runtime identity changed")
    validate_bounded_json(
        result,
        max_depth=2,
        max_items=32,
        max_string=4096,
        reject_sensitive_fields=True,
    )
    return result


def validate_native_view_record(
    value: Any,
    *,
    receipt: Mapping[str, Any],
    session: str,
    evidence: Mapping[str, Any],
    attach_argv: list[str],
    authority_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Validate one body-free, controller-attested native-view rendezvous."""

    if not isinstance(value, Mapping) or set(value) != _NATIVE_VIEW_FIELDS:
        raise ValidationError("Codex native-view fields do not match schema")
    result = dict(value)
    attestation = result.pop("controller_attestation")
    core = _validate_native_view_core(
        result,
        receipt=receipt,
        session=session,
        evidence=evidence,
        attach_argv=attach_argv,
    )
    _verify_native_view_attestation(
        core,
        attestation,
        authority_root=authority_root,
    )
    result["controller_attestation"] = dict(attestation)
    validate_bounded_json(
        result,
        max_depth=4,
        max_items=64,
        max_string=4096,
        reject_sensitive_fields=True,
    )
    return result


def observe_codex_native_view(
    *,
    proof_root: Path,
    run_id: str,
    timeout: float = 30.0,
    _tmux_factory: Optional[Callable[[Path], Any]] = None,
    _process_birth_fn: Optional[Callable[[int], Dict[str, Any]]] = None,
    _sleep_fn: Callable[[float], None] = time.sleep,
    _monotonic_fn: Callable[[], float] = time.monotonic,
    _authority_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Observe an actual read-only tmux client attach and detach, structurally."""

    from .campaign import process_birth_identity
    from .tmux import TmuxController

    if (
        isinstance(timeout, bool)
        or not isinstance(timeout, (int, float))
        or timeout <= 0
    ):
        raise ValidationError("native-view timeout is invalid")
    proof = _canonical_directory(proof_root, "probe proof root")
    run_id = validate_identifier(run_id, "native-view run id")
    run_root = ensure_within(
        proof / "probes" / run_id,
        proof,
        must_exist=True,
    )
    state_path = run_root / "state.json"
    evidence_path = run_root / "evidence.json"
    state = read_json(state_path, max_bytes=131072, reject_sensitive_fields=True)
    evidence = read_json(
        evidence_path, max_bytes=131072, reject_sensitive_fields=True
    )
    tmux_value = evidence.get("tmux")
    process = evidence.get("process")
    ready = evidence.get("ready")
    if (
        state.get("run_id") != run_id
        or state.get("target") != "codex"
        or state.get("session") != (tmux_value or {}).get("session")
        or state.get("phase")
        not in {
            "ready_validated",
            "followup_validated",
            "accepted_awaiting_halt",
        }
        or not isinstance(tmux_value, Mapping)
        or not isinstance(process, Mapping)
        or set(process) != _PROCESS_FIELDS
        or not isinstance(ready, Mapping)
    ):
        raise ValidationError("Codex probe is not in a native-view live phase")
    process_birth_fn = _process_birth_fn or process_birth_identity
    tmux_factory = _tmux_factory or TmuxController
    socket = Path(tmux_value["socket"])
    session = tmux_value["session"]
    server = tmux_value["server_identity"]
    controller = tmux_factory(run_root / "tmux-authority")
    controller.assert_tmux_binary_identity(tmux_value["tmux_binary_identity"])
    controller.bind_server_identity(socket, server)
    attach_argv = controller.attach_argv(
        socket=socket,
        session=session,
        pane=tmux_value["target_id"],
        server_identity=server,
    )

    def runtime_check() -> None:
        current_state = read_json(
            state_path, max_bytes=131072, reject_sensitive_fields=True
        )
        current_evidence = read_json(
            evidence_path, max_bytes=131072, reject_sensitive_fields=True
        )
        metadata = controller.metadata_for_session(
            socket=socket,
            session=session,
            server_identity=server,
        )
        if (
            current_state.get("run_id") != run_id
            or current_state.get("phase")
            not in {
                "ready_validated",
                "followup_validated",
                "accepted_awaiting_halt",
            }
            or current_evidence.get("tmux") != tmux_value
            or current_evidence.get("process") != process
            or process_birth_fn(process["pid"]) != process
            or metadata.get("session") != session
            or metadata.get("pane") != tmux_value["target_id"]
            or metadata.get("pane_pid") != process["pid"]
            or metadata.get("pane_dead") is not False
        ):
            raise IdentityError("Codex native-view target identity changed")

    runtime_check()
    if controller.viewer_clients(
        socket=socket, session=session, server_identity=server
    ):
        raise IdentityError("Codex native-view observation started with a client")
    deadline = _monotonic_fn() + float(timeout)
    viewer: Optional[Dict[str, Any]] = None
    viewer_process: Optional[Dict[str, Any]] = None
    while _monotonic_fn() < deadline:
        runtime_check()
        clients = controller.viewer_clients(
            socket=socket, session=session, server_identity=server
        )
        if clients:
            if len(clients) != 1 or clients[0].get("read_only") is not True:
                raise IdentityError("Codex native-view client is not exactly read-only")
            viewer = dict(clients[0])
            viewer_process = process_birth_fn(viewer["pid"])
            binary = tmux_value["tmux_binary_identity"]
            if (
                viewer.get("session") != session
                or not isinstance(viewer.get("tty"), str)
                or not viewer["tty"].startswith("/dev/")
                or viewer["pid"] in {process["pid"], server.get("pid")}
                or viewer_process.get("pid") != viewer["pid"]
                or viewer_process.get("executable_path") != binary["path"]
                or viewer_process.get("device") != binary["device"]
                or viewer_process.get("inode") != binary["inode"]
            ):
                raise IdentityError("Codex native-view client identity is invalid")
            break
        _sleep_fn(0.1)
    if viewer is None or viewer_process is None:
        raise ValidationError("Codex native-view attach was not observed")
    while _monotonic_fn() < deadline:
        runtime_check()
        clients = controller.viewer_clients(
            socket=socket, session=session, server_identity=server
        )
        if not clients:
            runtime_check()
            break
        if clients != [viewer]:
            raise IdentityError("Codex native-view client identity changed")
        _sleep_fn(0.1)
    else:
        raise ValidationError("Codex native-view detach was not observed")
    record = {
        "schema": NATIVE_VIEW_SCHEMA,
        "target": "codex",
        "run_id": run_id,
        "controller": state["controller"],
        "campaign_id": evidence["campaign_id"],
        "goal_fingerprint": evidence["goal_fingerprint"],
        "session": session,
        "state": NATIVE_VIEW_STATE,
        "ready_checkpoint_id": ready["checkpoint_id"],
        "attach_argv_sha256": sha256_bytes(canonical_json_bytes(attach_argv)),
        "tmux_sha256": sha256_bytes(canonical_json_bytes(tmux_value)),
        "target_process_sha256": sha256_bytes(canonical_json_bytes(process)),
        "viewer_client_sha256": sha256_bytes(canonical_json_bytes(viewer)),
        "viewer_process_sha256": sha256_bytes(canonical_json_bytes(viewer_process)),
        "viewer_client": viewer,
        "viewer_process": viewer_process,
        "read_only": True,
        "attached": True,
        "detached": True,
        "target_alive_after_detach": True,
        "body_capture_performed": False,
        "raw_retained": False,
    }
    _validate_native_view_core(
        record,
        receipt={
            "run_id": run_id,
            "controller": state["controller"],
            "campaign_id": evidence["campaign_id"],
            "goal_fingerprint": evidence["goal_fingerprint"],
        },
        session=session,
        evidence=evidence,
        attach_argv=attach_argv,
    )
    record["controller_attestation"] = _attest_native_view(
        record,
        authority_root=_authority_root,
    )
    validate_native_view_record(
        record,
        receipt={
            "run_id": run_id,
            "controller": state["controller"],
            "campaign_id": evidence["campaign_id"],
            "goal_fingerprint": evidence["goal_fingerprint"],
        },
        session=session,
        evidence=evidence,
        attach_argv=attach_argv,
        authority_root=_authority_root,
    )
    destination = run_root / NATIVE_VIEW_NAME
    _write_new_json(destination, record)
    return {
        "ok": True,
        "target": "codex",
        "run_id": run_id,
        "native_view": str(destination),
        "native_view_sha256": sha256_file(destination, max_bytes=65536),
        "read_only": True,
        "body_capture_performed": False,
        "raw_retained": False,
    }


def _current_default_launch_is_exact(
    launch: Mapping[str, Any],
    instructions: Mapping[str, Any],
) -> bool:
    argv = launch.get("argv")
    return (
        instructions.get("runtime_binding") == {"model": "default", "effort": "default"}
        and instructions.get("model_observation")
        == {
            "selection": "current_default",
            "resolved_identity": "unavailable",
            "effort": "unavailable",
        }
        and isinstance(argv, list)
        and len(argv) == 2
        and all(
            selector not in argv
            for selector in (
                "--model",
                "-m",
                "--profile",
                "-p",
                "--config",
                "-c",
                "--effort",
            )
        )
        and launch.get("launch_identity", {}).get("env_names") == ["CODEX_HOME"]
    )


def _receipt_ref(
    *,
    path: Path,
    receipt: Mapping[str, Any],
    session: str,
    artifacts: Mapping[str, Any],
    lease: Mapping[str, Any],
    positive: bool,
) -> Dict[str, Any]:
    for name in (
        "launch_plan_sha256",
        "accepted_checkpoint_id",
        "acceptance_sha256",
        "halt_receipt_sha256",
    ):
        validate_sha256(receipt.get(name), name.replace("_", " "))
    result = {
        "path": str(path),
        "sha256": sha256_file(path, max_bytes=131072),
        "run_id": receipt["run_id"],
        "session": session,
        "launch_plan_sha256": receipt["launch_plan_sha256"],
        "accepted_checkpoint_id": receipt["accepted_checkpoint_id"],
        "acceptance_sha256": receipt["acceptance_sha256"],
        "halt_receipt_sha256": receipt["halt_receipt_sha256"],
        "process_sha256": sha256_bytes(
            canonical_json_bytes(artifacts["evidence"]["process"])
        ),
        "tmux_sha256": sha256_bytes(
            canonical_json_bytes(artifacts["evidence"]["tmux"])
        ),
        "terminal_lease": dict(lease),
    }
    if positive:
        result["workspace_isolation"] = receipt["workspace_isolation"]
    return result


def _verify_receipt_pair(
    *,
    positive_receipt_path: Path,
    ordinary_receipt_path: Path,
    private_profile_root: Path,
    native_view_path: Path,
    authority_root: Optional[Path],
    current_manifest: Optional[Any],
    server_process_fn: Optional[Any],
    tmux_factory: Optional[Any],
    verify_receipt_fn: Optional[Callable[..., Dict[str, Any]]],
    terminal_lease_fn: Callable[..., Dict[str, Any]],
) -> Dict[str, Any]:
    from .adapter_manifest import verify_qualification_receipt

    verifier = verify_receipt_fn or verify_qualification_receipt
    positive = verifier(
        positive_receipt_path,
        _authority_root=authority_root,
        _current_manifest=current_manifest,
        _server_process_fn=server_process_fn,
        _tmux_factory=tmux_factory,
    )
    positive_artifacts = _receipt_artifacts(positive_receipt_path, positive)
    positive_session = _receipt_session(positive_receipt_path, positive)
    positive_lease = terminal_lease_fn(
        receipt_path=positive_receipt_path,
        receipt=positive,
        artifacts=positive_artifacts,
        session=positive_session,
        authority_root=authority_root,
    )
    expected_source = build_codex_control_source(
        positive_receipt_path,
        authority_root=authority_root,
        current_manifest=current_manifest,
        server_process_fn=server_process_fn,
        tmux_factory=tmux_factory,
        _verify_receipt_fn=verifier,
        _terminal_lease_fn=terminal_lease_fn,
    )
    ordinary = verifier(
        ordinary_receipt_path,
        _authority_root=authority_root,
        _current_manifest=current_manifest,
        _server_process_fn=server_process_fn,
        _tmux_factory=tmux_factory,
    )
    persisted_source = validate_codex_control_source(
        ordinary.get("codex_control_source")
    )
    if persisted_source != expected_source:
        raise IdentityError("Codex ordinary control is not linked to the positive run")
    if (
        positive.get("target") != "codex"
        or positive.get("workspace_isolation") is None
        or ordinary.get("target") != "codex"
        or ordinary.get("workspace_isolation") is not None
        or positive.get("plane_activation") is not None
        or ordinary.get("plane_activation") is not None
        or positive.get("session_profile") != "regular"
        or ordinary.get("session_profile") != "regular"
    ):
        raise UnsupportedError(
            "Codex pair requires one worktree run and one ordinary control"
        )
    shared_fields = (
        "target",
        "session_profile",
        "controller",
        "campaign_id",
        "goal_fingerprint",
        "executable_fingerprint",
        "execution_fingerprint",
        "version_fingerprint",
        "platform_fingerprint",
        "adapter_fingerprint",
        "protocol_fingerprint",
        "yolo_mapping_sha256",
        "subscription_profile_sha256",
        "instruction_policy_fingerprint",
        "capabilities",
    )
    if any(positive.get(name) != ordinary.get(name) for name in shared_fields):
        raise IdentityError("Codex positive and ordinary control identities differ")
    positive_sequence = _attestation_sequence(positive, "positive")
    ordinary_sequence = _attestation_sequence(ordinary, "ordinary control")
    if positive_sequence >= ordinary_sequence:
        raise IdentityError("Codex receipt attestation order is invalid")
    if (
        positive["run_id"] == ordinary["run_id"]
        or positive["accepted_checkpoint_id"] == ordinary["accepted_checkpoint_id"]
    ):
        raise IdentityError("Codex positive and ordinary control are not independent")

    ordinary_artifacts = _receipt_artifacts(ordinary_receipt_path, ordinary)
    ordinary_session = _receipt_session(ordinary_receipt_path, ordinary)
    ordinary_lease = terminal_lease_fn(
        receipt_path=ordinary_receipt_path,
        receipt=ordinary,
        artifacts=ordinary_artifacts,
        session=ordinary_session,
        authority_root=authority_root,
    )
    if (
        positive_lease["generation"] == ordinary_lease["generation"]
        or positive_lease["ledger_sequence"] >= ordinary_lease["ledger_sequence"]
    ):
        raise IdentityError("Codex terminal leases are not distinct and ordered")
    expected_profile = str(private_profile_root)
    if (
        positive_artifacts["profile"].get("profile_root") != expected_profile
        or ordinary_artifacts["profile"].get("profile_root") != expected_profile
        or positive["subscription_profile_sha256"]
        != ordinary["subscription_profile_sha256"]
    ):
        raise IdentityError("Codex qualification private profile binding differs")
    positive_launch = positive_artifacts["launch"]
    ordinary_launch = ordinary_artifacts["launch"]
    positive_workspace = positive["workspace_isolation"]
    if (
        positive_launch["cwd"] != positive_workspace["startup_cwd"]
        or positive_launch["cwd"] != positive_workspace["candidate_root"]
        or ordinary_launch["cwd"] == positive_launch["cwd"]
        or paths_overlap(Path(positive_launch["cwd"]), Path(ordinary_launch["cwd"]))
        or positive_launch["argv"] != ordinary_launch["argv"]
        or positive_launch["launch_identity"]["env_names"]
        != ordinary_launch["launch_identity"]["env_names"]
        or positive_launch["launch_identity"]["env_fingerprint"]
        != ordinary_launch["launch_identity"]["env_fingerprint"]
        or not _current_default_launch_is_exact(
            positive_launch, positive_artifacts["instructions"]
        )
        or not _current_default_launch_is_exact(
            ordinary_launch, ordinary_artifacts["instructions"]
        )
    ):
        raise IdentityError("Codex default/no-selector workspace join is invalid")
    positive_evidence = positive_artifacts["evidence"]
    ordinary_evidence = ordinary_artifacts["evidence"]
    positive_process = positive_evidence.get("process")
    ordinary_process = ordinary_evidence.get("process")
    positive_tmux = positive_evidence.get("tmux")
    ordinary_tmux = ordinary_evidence.get("tmux")
    if (
        positive_evidence.get("active_target_processes_before_launch") != []
        or positive_evidence.get("active_target_processes_after_halt") != []
        or ordinary_evidence.get("active_target_processes_before_launch") != []
        or ordinary_evidence.get("active_target_processes_after_halt") != []
        or positive_process == ordinary_process
        or positive_session == ordinary_session
        or not isinstance(positive_tmux, Mapping)
        or not isinstance(ordinary_tmux, Mapping)
        or positive_tmux == ordinary_tmux
        or positive_tmux.get("socket") == ordinary_tmux.get("socket")
        or positive_tmux.get("server_identity")
        == ordinary_tmux.get("server_identity")
    ):
        raise IdentityError("Codex paired process/tmux no-bleed evidence is incomplete")
    native_raw = read_json(
        native_view_path, max_bytes=65536, reject_sensitive_fields=True
    )
    native = validate_native_view_record(
        native_raw,
        receipt=positive,
        session=positive_session,
        evidence=positive_evidence,
        attach_argv=_native_attach_argv(positive_evidence),
        authority_root=authority_root,
    )
    descriptor = positive_artifacts["descriptor"]
    if (
        not isinstance(descriptor, Mapping)
        or descriptor.get("surface") != "controller_proved_direct_worktree_cwd"
        or descriptor.get("descriptor_sha256")
        != positive_workspace["descriptor_sha256"]
        or descriptor.get("candidate_root") != positive_workspace["candidate_root"]
        or descriptor.get("candidate_head") != positive_workspace["candidate_head"]
    ):
        raise IdentityError("Codex direct-worktree entry claim is not evidence-backed")
    entry_source = validate_codex_entry_source(positive.get("codex_entry_source"))
    if (
        entry_source["run_id"] != positive["run_id"]
        or entry_source["session"] != positive_session
        or entry_source["controller"] != positive["controller"]
        or entry_source["campaign_id"] != positive["campaign_id"]
        or entry_source["goal_fingerprint"] != positive["goal_fingerprint"]
        or entry_source["profile"]["root"] != str(private_profile_root)
        or entry_source["profile"]["sha256"]
        != positive["subscription_profile_sha256"]
        or entry_source["workspace"]["descriptor_sha256"]
        != positive_workspace["descriptor_sha256"]
        or entry_source["workspace"]["candidate_root"]
        != positive_workspace["candidate_root"]
        or entry_source["workspace"]["candidate_branch"]
        != positive_workspace["candidate_branch"]
        or entry_source["workspace"]["candidate_head"]
        != positive_workspace["candidate_head"]
    ):
        raise IdentityError(
            "Codex positive-entry source differs from its accepted run"
        )
    entry_claim = {
        "mode": entry_source["entry_mode"],
        "operator_plan": dict(entry_source["operator_plan"]),
        "repository": {
            "repo": entry_source["workspace"]["candidate_root"],
            "branch": entry_source["workspace"]["candidate_branch"],
            "head": entry_source["workspace"]["candidate_head"],
        },
        "surface": descriptor["surface"],
        "descriptor_sha256": positive_workspace["descriptor_sha256"],
    }
    return {
        "positive": positive,
        "ordinary": ordinary,
        "positive_artifacts": positive_artifacts,
        "ordinary_artifacts": ordinary_artifacts,
        "positive_session": positive_session,
        "ordinary_session": ordinary_session,
        "positive_lease": positive_lease,
        "ordinary_lease": ordinary_lease,
        "positive_sequence": positive_sequence,
        "ordinary_sequence": ordinary_sequence,
        "native": native,
        "entry_claim": entry_claim,
    }


def _pair_core(
    *,
    verified: Mapping[str, Any],
    positive_path: Path,
    ordinary_path: Path,
    native_path: Path,
    profile_root: Path,
) -> Dict[str, Any]:
    positive = verified["positive"]
    ordinary = verified["ordinary"]
    positive_artifacts = verified["positive_artifacts"]
    ordinary_artifacts = verified["ordinary_artifacts"]
    positive_ref = _receipt_ref(
        path=positive_path,
        receipt=positive,
        session=verified["positive_session"],
        artifacts=positive_artifacts,
        lease=verified["positive_lease"],
        positive=True,
    )
    ordinary_ref = _receipt_ref(
        path=ordinary_path,
        receipt=ordinary,
        session=verified["ordinary_session"],
        artifacts=ordinary_artifacts,
        lease=verified["ordinary_lease"],
        positive=False,
    )
    pair_id = sha256_bytes(
        canonical_json_bytes(
            [
                positive_ref["sha256"],
                ordinary_ref["sha256"],
                sha256_file(native_path, max_bytes=65536),
            ]
        )
    )
    positive_population = positive_artifacts["evidence"][
        "active_target_processes_before_launch"
    ]
    ordinary_population = ordinary_artifacts["evidence"][
        "active_target_processes_before_launch"
    ]
    return {
        "schema_version": PAIR_SCHEMA_VERSION,
        "kind": PAIR_KIND,
        "run_id": "codex-pair-" + pair_id[:24],
        "target": "codex",
        "session_profile": "regular",
        "result": "paired_evidence_only",
        "controller": positive["controller"],
        "campaign_id": positive["campaign_id"],
        "goal_fingerprint": positive["goal_fingerprint"],
        "executable_fingerprint": positive["executable_fingerprint"],
        "execution_fingerprint": positive["execution_fingerprint"],
        "version_fingerprint": positive["version_fingerprint"],
        "platform_fingerprint": positive["platform_fingerprint"],
        "adapter_fingerprint": positive["adapter_fingerprint"],
        "protocol_fingerprint": positive["protocol_fingerprint"],
        "yolo_mapping_sha256": positive["yolo_mapping_sha256"],
        "launch_plan_sha256": _pair_sha(
            positive["launch_plan_sha256"], ordinary["launch_plan_sha256"]
        ),
        "subscription_profile_sha256": positive[
            "subscription_profile_sha256"
        ],
        "instruction_policy_fingerprint": positive[
            "instruction_policy_fingerprint"
        ],
        "capabilities": list(positive["capabilities"]),
        "accepted_checkpoint_id": _pair_sha(
            positive["accepted_checkpoint_id"], ordinary["accepted_checkpoint_id"]
        ),
        "acceptance_sha256": _pair_sha(
            positive["acceptance_sha256"], ordinary["acceptance_sha256"]
        ),
        "halt_receipt_sha256": _pair_sha(
            positive["halt_receipt_sha256"], ordinary["halt_receipt_sha256"]
        ),
        "private_profile_root": str(profile_root),
        "runtime_binding": {
            "model_selection": "current_default",
            "effort_selection": "current_default",
            "resolved_model": "unavailable",
            "resolved_effort": "unavailable",
            "explicit_selector": False,
        },
        "positive": positive_ref,
        "ordinary_control": ordinary_ref,
        "native_view": {
            "path": str(native_path),
            "sha256": sha256_file(native_path, max_bytes=65536),
            "record": verified["native"],
        },
        "entry_claim": verified["entry_claim"],
        "no_bleed": {
            "positive_cwd": positive_artifacts["launch"]["cwd"],
            "ordinary_control_cwd": ordinary_artifacts["launch"]["cwd"],
            "positive_population_sha256": sha256_bytes(
                canonical_json_bytes(positive_population)
            ),
            "ordinary_control_population_sha256": sha256_bytes(
                canonical_json_bytes(ordinary_population)
            ),
            "empty_baselines_and_terminal_populations": True,
            "distinct_non_overlapping_workspaces": True,
            "distinct_processes": True,
            "distinct_tmux_servers_sockets_sessions": True,
            "distinct_terminal_leases": True,
            "same_launch_argv": True,
            "same_closed_profile_context": True,
        },
        "receipt_attestation_order": {
            "positive": verified["positive_sequence"],
            "ordinary_control": verified["ordinary_sequence"],
        },
        "public_launch_authorized": False,
        "promotion_authorized": False,
        "independent_verification_required": True,
        "raw_retained": False,
        "blockers": list(PAIR_BLOCKERS),
    }


def create_codex_regular_pair_receipt(
    *,
    out: Path,
    positive_receipt_path: Path | str,
    ordinary_receipt_path: Path | str,
    native_view_path: Path | str,
    private_profile_root: Path | str,
    authority_root: Optional[Path] = None,
    _current_manifest: Optional[Any] = None,
    _server_process_fn: Optional[Any] = None,
    _tmux_factory: Optional[Any] = None,
    _verify_receipt_fn: Optional[Callable[..., Dict[str, Any]]] = None,
    _terminal_lease_fn: Callable[..., Dict[str, Any]] = _terminal_lease_ref,
) -> Dict[str, Any]:
    """Create and controller-attest one explicitly non-promotable pair."""

    positive_path = _canonical_file(positive_receipt_path, "positive receipt")
    ordinary_path = _canonical_file(
        ordinary_receipt_path, "ordinary control receipt"
    )
    native_path = _canonical_file(native_view_path, "native-view record")
    profile_root = _canonical_directory(private_profile_root, "private profile root")
    if positive_path == ordinary_path:
        raise IdentityError("Codex paired receipts must be distinct")
    verified = _verify_receipt_pair(
        positive_receipt_path=positive_path,
        ordinary_receipt_path=ordinary_path,
        private_profile_root=profile_root,
        native_view_path=native_path,
        authority_root=authority_root,
        current_manifest=_current_manifest,
        server_process_fn=_server_process_fn,
        tmux_factory=_tmux_factory,
        verify_receipt_fn=_verify_receipt_fn,
        terminal_lease_fn=_terminal_lease_fn,
    )
    core = _pair_core(
        verified=verified,
        positive_path=positive_path,
        ordinary_path=ordinary_path,
        native_path=native_path,
        profile_root=profile_root,
    )
    bundle = dict(
        core,
        controller_attestation=attest_qualification(
            core, authority_root=authority_root
        ),
    )
    destination = Path(out)
    created_identity = _write_new_json(destination, bundle)
    try:
        verify_codex_regular_pair_receipt(
            destination,
            expected_private_profile_root=profile_root,
            _authority_root=authority_root,
            _current_manifest=_current_manifest,
            _server_process_fn=_server_process_fn,
            _tmux_factory=_tmux_factory,
            _verify_receipt_fn=_verify_receipt_fn,
            _terminal_lease_fn=_terminal_lease_fn,
        )
    except BaseException:
        try:
            details = destination.lstat()
            if (
                stat.S_ISREG(details.st_mode)
                and (details.st_dev, details.st_ino) == created_identity
            ):
                destination.unlink()
        except FileNotFoundError:
            pass
        raise
    return {
        "ok": True,
        "target": "codex",
        "result": "paired_evidence_only",
        "receipt": str(destination),
        "receipt_sha256": sha256_file(destination, max_bytes=131072),
        "public_launch_authorized": False,
        "promotion_authorized": False,
        "independent_verification_required": True,
        "raw_retained": False,
    }


def verify_codex_regular_pair_receipt(
    value_or_path: Mapping[str, Any] | Path | str,
    *,
    expected_private_profile_root: Path | str,
    _authority_root: Optional[Path] = None,
    _current_manifest: Optional[Any] = None,
    _server_process_fn: Optional[Any] = None,
    _tmux_factory: Optional[Any] = None,
    _verify_receipt_fn: Optional[Callable[..., Dict[str, Any]]] = None,
    _terminal_lease_fn: Callable[..., Dict[str, Any]] = _terminal_lease_ref,
) -> Dict[str, Any]:
    """Independently rebuild the pair from current terminal source evidence."""

    if isinstance(value_or_path, Mapping):
        value = dict(value_or_path)
    else:
        path = _canonical_file(value_or_path, "Codex paired receipt")
        value = read_json(path, max_bytes=131072, reject_sensitive_fields=True)
    if not isinstance(value, dict) or set(value) != _PAIR_FIELDS:
        raise ValidationError("Codex paired receipt fields do not match schema")
    if (
        value.get("schema_version") != PAIR_SCHEMA_VERSION
        or value.get("kind") != PAIR_KIND
        or value.get("target") != "codex"
        or value.get("session_profile") != "regular"
        or value.get("result") != "paired_evidence_only"
        or value.get("public_launch_authorized") is not False
        or value.get("promotion_authorized") is not False
        or value.get("independent_verification_required") is not True
        or value.get("raw_retained") is not False
        or value.get("blockers") != list(PAIR_BLOCKERS)
    ):
        raise ValidationError("Codex paired receipt state is invalid")
    if (
        not isinstance(value.get("positive"), Mapping)
        or set(value["positive"]) != _POSITIVE_REF_FIELDS
        or not isinstance(value.get("ordinary_control"), Mapping)
        or set(value["ordinary_control"]) != _RECEIPT_REF_FIELDS
    ):
        raise ValidationError("Codex paired receipt references are invalid")
    native_ref = value.get("native_view")
    if not isinstance(native_ref, Mapping) or set(native_ref) != {
        "path",
        "sha256",
        "record",
    }:
        raise ValidationError("Codex native-view reference is invalid")
    receipt_core = dict(value)
    attestation = receipt_core.pop("controller_attestation")
    verified_attestation = verify_qualification_attestation(
        receipt_core, attestation, authority_root=_authority_root
    )
    profile_root = _canonical_directory(
        value.get("private_profile_root"), "private profile root"
    )
    expected_profile = _canonical_directory(
        expected_private_profile_root, "expected private profile root"
    )
    if profile_root != expected_profile:
        raise IdentityError("Codex paired receipt private profile root changed")
    positive_path = _canonical_file(value["positive"]["path"], "positive receipt")
    ordinary_path = _canonical_file(
        value["ordinary_control"]["path"], "ordinary control receipt"
    )
    native_path = _canonical_file(native_ref["path"], "native-view record")
    for path, reference, maximum in (
        (positive_path, value["positive"], 131072),
        (ordinary_path, value["ordinary_control"], 131072),
        (native_path, native_ref, 65536),
    ):
        validate_sha256(reference.get("sha256"), "Codex paired artifact")
        if sha256_file(path, max_bytes=maximum) != reference["sha256"]:
            raise IdentityError("Codex paired artifact fingerprint changed")
    verified = _verify_receipt_pair(
        positive_receipt_path=positive_path,
        ordinary_receipt_path=ordinary_path,
        private_profile_root=profile_root,
        native_view_path=native_path,
        authority_root=_authority_root,
        current_manifest=_current_manifest,
        server_process_fn=_server_process_fn,
        tmux_factory=_tmux_factory,
        verify_receipt_fn=_verify_receipt_fn,
        terminal_lease_fn=_terminal_lease_fn,
    )
    expected_core = _pair_core(
        verified=verified,
        positive_path=positive_path,
        ordinary_path=ordinary_path,
        native_path=native_path,
        profile_root=profile_root,
    )
    if receipt_core != expected_core:
        raise IdentityError("Codex paired receipt drifted from terminal evidence")
    pair_sequence = verified_attestation["sequence"]
    if verified["ordinary_sequence"] >= pair_sequence:
        raise IdentityError("Codex paired controller attestation order is invalid")
    validate_identifier(value.get("run_id"), "Codex paired run id")
    validate_bounded_json(
        value,
        max_depth=12,
        max_items=320,
        max_string=4096,
        reject_sensitive_fields=True,
    )
    return value


__all__ = [
    "CONTROL_SOURCE_SCHEMA",
    "ENTRY_SOURCE_SCHEMA",
    "NATIVE_VIEW_NAME",
    "NATIVE_VIEW_SCHEMA",
    "PAIR_BLOCKERS",
    "PAIR_KIND",
    "build_codex_control_source",
    "build_codex_entry_source",
    "create_codex_regular_pair_receipt",
    "observe_codex_native_view",
    "validate_codex_control_source",
    "validate_codex_entry_source",
    "validate_native_view_record",
    "verify_codex_regular_pair_receipt",
]
