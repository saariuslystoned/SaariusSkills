"""Controller-owned Grok workspace isolation substrate (non-promotable slice).

Census remains doctor-only with an incomplete mapping because Grok has no CLI
project-isolation flag.  This module binds create-only
``.grok/rules/puppet-<hash>.md`` materialization, direct/cockpit entry join,
hash-guarded rollback, and structural ordinary-control *prechecks*.

Filesystem absence of a rule in a sibling directory is never ``no_bleed_verified``
and never grants terminal qualification or public launch authority.  Paired
subscription-backed runtime matched control (independent positive/control
checkpoints, native read-only attach, and exact halts of both owned processes)
remains required before any promotion.  This module never launches Grok or
reads auth/config-store contents.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Tuple

from .errors import ConflictError, IdentityError, UnsupportedError, ValidationError
from .grok_launch import (
    GROK_BUILD_VERSION,
    GROK_LAUNCH_AUTHORITY_BLOCKERS,
    GROK_RUNTIME_BASENAME,
    GROK_WORKSPACE_BINDING_SCHEMA,
    GROK_WORKSPACE_BINDING_STATE,
)
from .instruction_planes import (
    GROK_WORKSPACE_ARTIFACT_ID,
    build_grok_workspace_addendum_descriptor,
    validate_grok_workspace_addendum_descriptor,
)
from .operator_plan import _repository_identity
from .safety import (
    absolute_root,
    canonical_json_bytes,
    paths_overlap,
    sha256_bytes,
    validate_bounded_json,
    validate_identifier,
    validate_sha1,
    validate_sha256,
)


DESCRIPTOR_SCHEMA = "puppet.grok-workspace-entry-descriptor/v1"
TERMINAL_SCHEMA = "puppet.grok-workspace-isolation-receipt/v1"
MATERIALIZATION_RECEIPT_SCHEMA = "puppet.grok-workspace-materialization/v1"
ROLLBACK_RECEIPT_SCHEMA = "puppet.grok-workspace-rollback/v1"
MATCHED_CONTROL_SCHEMA = "puppet.grok-matched-control-attestation/v1"
MATCHED_CONTROL_PRECHECK_SCHEMA = "puppet.grok-matched-control-precheck/v1"
FILESYSTEM_ABSENCE_PROOF = "filesystem_absence_only_nonpromotable"
PAIRED_RUNTIME_PROOF = "paired_subscription_runtime"
GROK_NO_BLEED_FS_SHORTCUT_BLOCKER = (
    "Grok no_bleed_verified cannot be claimed from ordinary-control filesystem "
    "absence alone; paired subscription-backed runtime control with independent "
    "checkpoints, read-only attach, and exact halts is required"
)
GROK_QUALIFICATION_NONPROMOTABLE = (
    "Grok public qualification remains non-promotable until paired "
    "subscription-backed runtime matched control is controller-proved"
)
GROK_PUBLIC_LAUNCH_FENCED = (
    "Grok public launch remains fenced until authentication isolation, the native "
    "instruction plane, paired runtime no-bleed, and leader/child halt authority "
    "are controller-proved"
)
ENTRY_SURFACES = ("direct_repository", "cockpit")
GROK_REGULAR_PERMISSION_FLAGS: Tuple[str, ...] = ("--always-approve",)
GROK_REGULAR_SANDBOX_FLAGS: Tuple[str, ...] = ("--sandbox", "off")
GROK_REGULAR_ARGV_TAIL: Tuple[str, ...] = (
    "--always-approve",
    "--sandbox",
    "off",
)
_RULE_RE_PREFIX = ".grok/rules/puppet-"
_RULE_RE_SUFFIX = ".md"
_DIR_MODE = 0o700
_FILE_MODE = 0o600
_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_CREATE_FLAGS = os.O_CREAT | os.O_EXCL | os.O_RDWR | _NOFOLLOW
_READ_FLAGS = os.O_RDONLY | _NOFOLLOW
_DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | _NOFOLLOW

_DESCRIPTOR_FIELDS = {
    "schema",
    "target",
    "target_version",
    "surface",
    "qualification_authorized",
    "workspace_root",
    "workspace_identity_sha256",
    "direct_repository_root",
    "cockpit_root",
    "candidate_branch",
    "candidate_head",
    "controller",
    "campaign_id",
    "goal_fingerprint",
    "executable_sha256",
    "subscription_profile_root",
    "artifact_relative_path",
    "descriptor_sha256",
}

_MATERIALIZATION_FIELDS = {
    "schema",
    "target",
    "target_version",
    "workspace_root",
    "relative_path",
    "artifact_id",
    "write_mode",
    "content_sha256",
    "content_bytes",
    "descriptor_sha256",
    "created",
    "activation_authorized",
    "launch_authorized",
    "qualification_authorized",
}

_ROLLBACK_FIELDS = {
    "schema",
    "target",
    "target_version",
    "workspace_root",
    "relative_path",
    "expected_content_sha256",
    "removed",
    "absent_after",
    "launch_authorized",
    "qualification_authorized",
}

_MATCHED_CONTROL_PRECHECK_FIELDS = {
    "schema",
    "target",
    "target_version",
    "positive_workspace_root",
    "ordinary_workspace_root",
    "positive_artifact_relative_path",
    "positive_artifact_sha256",
    "ordinary_artifact_absent",
    "workspace_identity_join_sha256",
    "proof_strength",
    "no_bleed_verified",
    "activation_authorized",
    "launch_authorized",
    "qualification_authorized",
    "attestation_sha256",
}
_MATCHED_CONTROL_FIELDS = {
    "schema",
    "target",
    "target_version",
    "positive_workspace_root",
    "ordinary_workspace_root",
    "positive_artifact_relative_path",
    "positive_artifact_sha256",
    "ordinary_artifact_absent",
    "workspace_identity_join_sha256",
    "proof_strength",
    "positive_runtime_halt_sha256",
    "ordinary_runtime_halt_sha256",
    "positive_checkpoint_sha256",
    "ordinary_checkpoint_sha256",
    "positive_attach_sha256",
    "ordinary_attach_sha256",
    "no_bleed_verified",
    "activation_authorized",
    "launch_authorized",
    "qualification_authorized",
    "attestation_sha256",
}


def _canonical_directory(value: Any, label: str) -> Path:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ValidationError("%s is invalid" % label)
    path = Path(value)
    if not path.is_absolute() or os.path.normpath(value) != value:
        raise ValidationError("%s must be canonical and absolute" % label)
    try:
        current = path.resolve(strict=True)
    except OSError as exc:
        raise IdentityError("%s is unavailable" % label) from exc
    if current != path or path.is_symlink() or not path.is_dir():
        raise IdentityError("%s is not a canonical real directory" % label)
    return path


def _directory_identity(path: Path, *, label: str) -> Dict[str, Any]:
    root = _canonical_directory(str(path), label)
    details = root.lstat()
    if not stat.S_ISDIR(details.st_mode) or stat.S_ISLNK(details.st_mode):
        raise IdentityError("%s must be a real directory" % label)
    return {
        "path": str(root),
        "device": details.st_dev,
        "inode": details.st_ino,
        "uid": details.st_uid,
        "mode": stat.S_IMODE(details.st_mode),
        "nlink": details.st_nlink,
    }


def _identity_sha256(value: Mapping[str, Any]) -> str:
    return sha256_bytes(canonical_json_bytes(value))


def _validate_rule_relative_path(value: Any) -> str:
    if (
        not isinstance(value, str)
        or not value.startswith(_RULE_RE_PREFIX)
        or not value.endswith(_RULE_RE_SUFFIX)
    ):
        raise ValidationError("Grok workspace rule relative path is invalid")
    digest = value[len(_RULE_RE_PREFIX) : -len(_RULE_RE_SUFFIX)]
    validate_sha256(digest, "Grok workspace rule content hash")
    if "/" in digest or ".." in value.split("/"):
        raise ValidationError("Grok workspace rule relative path is invalid")
    return value


def _artifact_path(workspace: Path, relative_path: str) -> Path:
    relative = _validate_rule_relative_path(relative_path)
    parts = relative.split("/")
    candidate = workspace.joinpath(*parts)
    if candidate.is_absolute() is False:
        pass
    try:
        resolved_workspace = workspace.resolve(strict=True)
    except OSError as exc:
        raise IdentityError("Grok workspace root is unavailable") from exc
    # Lexical containment before create; resolve after parents exist.
    if os.path.commonpath([str(resolved_workspace), str(candidate)]) != str(
        resolved_workspace
    ):
        raise IdentityError("Grok workspace rule escapes its workspace root")
    return candidate


def _regular_launch_argv(mapping: Mapping[str, Any]) -> list[str]:
    argv = mapping.get("launch_argv")
    if (
        not isinstance(argv, list)
        or len(argv) != 1 + len(GROK_REGULAR_ARGV_TAIL)
        or not all(isinstance(item, str) and item for item in argv)
        or argv[1:] != list(GROK_REGULAR_ARGV_TAIL)
        or Path(argv[0]).name != GROK_RUNTIME_BASENAME
        or "--model" in argv
        or "--reasoning-effort" in argv
    ):
        raise IdentityError("Grok doctor mapping is not the exact regular argv tuple")
    return list(argv)


def grok_regular_launch_argv(executable_path: str | Path) -> list[str]:
    """Return the exact regular census argv with no model or effort selector."""

    path = Path(executable_path)
    if path.name != GROK_RUNTIME_BASENAME:
        raise IdentityError("Grok regular argv requires the exact 0.2.111 runtime basename")
    return [str(path), *GROK_REGULAR_ARGV_TAIL]


def grok_qualified_mapping(mapping: Mapping[str, Any]) -> Dict[str, Any]:
    """Close only the project-isolation bit proved by a terminal receipt."""

    result = json.loads(canonical_json_bytes(mapping).decode("utf-8"))
    argv = _regular_launch_argv(result)
    if (
        result.get("complete") is not False
        or result.get("project_isolation_declared") is not False
        or result.get("project_isolation_flags") != []
        or result.get("permission_flags") != list(GROK_REGULAR_PERMISSION_FLAGS)
        or result.get("sandbox_flags") != list(GROK_REGULAR_SANDBOX_FLAGS)
        or result.get("permission_declared") is not True
        or result.get("sandbox_disable_declared") is not True
        or result.get("prompt_transport_declared") is not True
        or result.get("session_profiles_declared") is not True
        or result.get("launch_argv") != argv
    ):
        raise IdentityError("Grok doctor mapping is not the exact incomplete tuple")
    result["complete"] = True
    result["project_isolation_declared"] = True
    return result


def grok_probe_mapping_from_qualified(
    mapping: Mapping[str, Any],
    *,
    workspace_isolation: Any,
) -> Dict[str, Any]:
    """Recover only the exact doctor mapping committed by terminal proof."""

    from .adapter_manifest import validate_grok_workspace_isolation

    if validate_grok_workspace_isolation(workspace_isolation) is None:
        raise IdentityError("Grok qualified mapping lacks terminal workspace proof")
    qualified = json.loads(canonical_json_bytes(mapping).decode("utf-8"))
    if (
        qualified.get("complete") is not True
        or qualified.get("project_isolation_declared") is not True
    ):
        raise IdentityError("Grok qualified mapping closure changed")
    probe_mapping = dict(qualified)
    probe_mapping["complete"] = False
    probe_mapping["project_isolation_declared"] = False
    if grok_qualified_mapping(probe_mapping) != qualified:
        raise IdentityError("Grok qualified mapping closure is not exact")
    return probe_mapping


def is_grok_workspace_mapping_closure(mapping: Mapping[str, Any]) -> bool:
    """Identify the exact current closure that must carry terminal proof."""

    try:
        qualified = json.loads(canonical_json_bytes(mapping).decode("utf-8"))
        if (
            qualified.get("complete") is not True
            or qualified.get("project_isolation_declared") is not True
        ):
            return False
        probe_mapping = dict(qualified)
        probe_mapping["complete"] = False
        probe_mapping["project_isolation_declared"] = False
        return grok_qualified_mapping(probe_mapping) == qualified
    except (IdentityError, TypeError, ValueError):
        return False


def validate_grok_entry_descriptor(
    value: Any,
    *,
    expected_controller: str,
    expected_campaign_id: str,
    expected_goal_fingerprint: str,
    expected_executable_sha256: str,
    expected_subscription_profile_root: Path | str,
) -> Dict[str, Any]:
    """Rejoin one non-authorizing entry descriptor to current workspace identity."""

    if not isinstance(value, Mapping) or set(value) != _DESCRIPTOR_FIELDS:
        raise ValidationError("Grok workspace entry descriptor fields are invalid")
    if (
        value.get("schema") != DESCRIPTOR_SCHEMA
        or value.get("target") != "grok"
        or value.get("target_version") != GROK_BUILD_VERSION
        or value.get("surface") != "controller_proved_direct_and_cockpit_join"
        or value.get("qualification_authorized") is not False
    ):
        raise ValidationError("Grok workspace entry descriptor is not source-only")
    result = dict(value)
    controller = validate_identifier(value.get("controller"), "descriptor controller")
    campaign = validate_identifier(value.get("campaign_id"), "descriptor campaign")
    goal = validate_sha256(value.get("goal_fingerprint"), "descriptor goal")
    executable = validate_sha256(
        value.get("executable_sha256"), "descriptor executable"
    )
    if (
        controller != expected_controller
        or campaign != expected_campaign_id
        or goal != expected_goal_fingerprint
        or executable != expected_executable_sha256
    ):
        raise IdentityError("Grok workspace entry descriptor authority changed")
    workspace = _canonical_directory(value.get("workspace_root"), "workspace root")
    direct = _canonical_directory(
        value.get("direct_repository_root"), "direct repository root"
    )
    cockpit = _canonical_directory(value.get("cockpit_root"), "cockpit root")
    profile = _canonical_directory(
        value.get("subscription_profile_root"), "subscription profile root"
    )
    expected_profile = Path(expected_subscription_profile_root).resolve(strict=True)
    if profile != expected_profile:
        raise IdentityError("Grok workspace entry descriptor profile changed")
    if paths_overlap(workspace, profile) or paths_overlap(direct, profile):
        raise IdentityError("Grok workspace entry descriptor roots overlap profile")
    if paths_overlap(cockpit, profile):
        raise IdentityError("Grok cockpit root overlaps the subscription profile")
    workspace_identity = _directory_identity(workspace, label="workspace root")
    direct_identity = _directory_identity(direct, label="direct repository root")
    if workspace != direct:
        raise IdentityError(
            "Grok direct-repository entry must join the exact workspace root"
        )
    if _identity_sha256(workspace_identity) != _identity_sha256(direct_identity):
        raise IdentityError("Grok direct entry workspace identity changed")
    if value.get("workspace_identity_sha256") != _identity_sha256(workspace_identity):
        raise IdentityError("Grok workspace identity fingerprint changed")
    cockpit_identity = _repository_identity(cockpit, require_linked_clean=False)
    direct_repo = _repository_identity(direct, require_linked_clean=True)
    if direct_repo["git_common_dir"] != cockpit_identity["git_common_dir"]:
        raise IdentityError(
            "Grok direct and cockpit entries do not join the same repository identity"
        )
    branch = direct_repo["branch"]
    head = direct_repo["head"]
    if (
        branch != value.get("candidate_branch")
        or head != validate_sha1(value.get("candidate_head"), "descriptor head")
    ):
        raise IdentityError("Grok workspace branch or head changed")
    if cockpit_identity["dirty"]:
        raise IdentityError("Grok cockpit source is mutable")
    relative = _validate_rule_relative_path(value.get("artifact_relative_path"))
    if relative != value.get("artifact_relative_path"):
        raise IdentityError("Grok workspace artifact path changed")
    supplied = validate_sha256(value.get("descriptor_sha256"), "descriptor fingerprint")
    unsigned = {name: result[name] for name in result if name != "descriptor_sha256"}
    if supplied != sha256_bytes(canonical_json_bytes(unsigned)):
        raise IdentityError("Grok workspace entry descriptor is stale")
    return result


def build_grok_entry_descriptor(
    *,
    workspace_root: Path | str,
    cockpit_root: Path | str,
    controller: str,
    campaign_id: str,
    goal_fingerprint: str,
    executable_sha256: str,
    subscription_profile_root: Path | str,
    artifact_relative_path: str,
) -> Dict[str, Any]:
    """Compile body-free Pass-B entry input; grants no launch authority."""

    workspace = Path(workspace_root).resolve(strict=True)
    cockpit = Path(cockpit_root).resolve(strict=True)
    profile = Path(subscription_profile_root).resolve(strict=True)
    relative = _validate_rule_relative_path(artifact_relative_path)
    workspace_identity = _directory_identity(workspace, label="workspace root")
    value = {
        "schema": DESCRIPTOR_SCHEMA,
        "target": "grok",
        "target_version": GROK_BUILD_VERSION,
        "surface": "controller_proved_direct_and_cockpit_join",
        "qualification_authorized": False,
        "workspace_root": str(workspace),
        "workspace_identity_sha256": _identity_sha256(workspace_identity),
        "direct_repository_root": str(workspace),
        "cockpit_root": str(cockpit),
        "candidate_branch": _repository_identity(workspace, require_linked_clean=True)[
            "branch"
        ],
        "candidate_head": _repository_identity(workspace, require_linked_clean=True)[
            "head"
        ],
        "controller": validate_identifier(controller, "descriptor controller"),
        "campaign_id": validate_identifier(campaign_id, "descriptor campaign"),
        "goal_fingerprint": validate_sha256(goal_fingerprint, "descriptor goal"),
        "executable_sha256": validate_sha256(
            executable_sha256, "descriptor executable"
        ),
        "subscription_profile_root": str(profile),
        "artifact_relative_path": relative,
    }
    value["descriptor_sha256"] = sha256_bytes(canonical_json_bytes(value))
    return validate_grok_entry_descriptor(
        value,
        expected_controller=controller,
        expected_campaign_id=campaign_id,
        expected_goal_fingerprint=goal_fingerprint,
        expected_executable_sha256=executable_sha256,
        expected_subscription_profile_root=profile,
    )


def materialize_grok_workspace_rule(
    *,
    workspace_root: Path | str,
    relative_path: str,
    content: bytes,
    descriptor_sha256: str,
) -> Dict[str, Any]:
    """Create-only materialize the namespaced workspace rule. No launch authority."""

    if not isinstance(content, (bytes, bytearray)) or not content:
        raise ValidationError("Grok workspace rule content must be non-empty bytes")
    content_bytes = bytes(content)
    content_sha = sha256_bytes(content_bytes)
    relative = _validate_rule_relative_path(relative_path)
    expected_name = "%s%s%s" % (_RULE_RE_PREFIX, content_sha, _RULE_RE_SUFFIX)
    if relative != expected_name:
        raise IdentityError(
            "Grok workspace rule filename does not match its content hash"
        )
    workspace = absolute_root(str(workspace_root), "Grok workspace root")
    try:
        workspace_stat = workspace.lstat()
    except OSError as exc:
        raise IdentityError("Grok workspace root is unavailable") from exc
    if (
        not stat.S_ISDIR(workspace_stat.st_mode)
        or stat.S_ISLNK(workspace_stat.st_mode)
        or workspace_stat.st_uid != os.getuid()
    ):
        raise IdentityError("Grok workspace root must be a current-UID directory")

    rules_dir = workspace / ".grok" / "rules"
    artifact = _artifact_path(workspace, relative)
    for parent in (workspace / ".grok", rules_dir):
        try:
            os.mkdir(parent, _DIR_MODE)
        except FileExistsError:
            try:
                details = parent.lstat()
            except OSError as exc:
                raise IdentityError("Grok rules parent is unavailable") from exc
            if not stat.S_ISDIR(details.st_mode) or stat.S_ISLNK(details.st_mode):
                raise IdentityError("Grok rules parent must be a real directory")
            if details.st_uid != os.getuid():
                raise IdentityError("Grok rules parent must be current-UID owned")
        except OSError as exc:
            raise ValidationError("Grok rules parent could not be created") from exc

    flags = _CREATE_FLAGS
    try:
        descriptor = os.open(artifact, flags, _FILE_MODE)
    except FileExistsError as exc:
        raise ConflictError(
            "Grok workspace rule already exists; create-only materialization refused"
        ) from exc
    except OSError as exc:
        raise ValidationError("Grok workspace rule could not be created") from exc
    try:
        written = 0
        view = memoryview(content_bytes)
        while written < len(content_bytes):
            chunk = os.write(descriptor, view[written:])
            if chunk <= 0:
                raise ValidationError("Grok workspace rule write stalled")
            written += chunk
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    try:
        details = artifact.lstat()
    except OSError as exc:
        raise IdentityError("Grok workspace rule vanished after create") from exc
    if (
        not stat.S_ISREG(details.st_mode)
        or stat.S_ISLNK(details.st_mode)
        or details.st_size != len(content_bytes)
        or details.st_uid != os.getuid()
    ):
        raise IdentityError("Grok workspace rule identity is invalid after create")
    observed = sha256_bytes(artifact.read_bytes())
    if observed != content_sha:
        raise IdentityError("Grok workspace rule content hash changed after create")
    receipt = {
        "schema": MATERIALIZATION_RECEIPT_SCHEMA,
        "target": "grok",
        "target_version": GROK_BUILD_VERSION,
        "workspace_root": str(workspace),
        "relative_path": relative,
        "artifact_id": GROK_WORKSPACE_ARTIFACT_ID,
        "write_mode": "create_only",
        "content_sha256": content_sha,
        "content_bytes": len(content_bytes),
        "descriptor_sha256": validate_sha256(
            descriptor_sha256, "materialization descriptor"
        ),
        "created": True,
        "activation_authorized": False,
        "launch_authorized": False,
        "qualification_authorized": False,
    }
    validate_bounded_json(
        receipt,
        max_depth=3,
        max_items=32,
        max_string=4096,
        reject_sensitive_fields=True,
    )
    if set(receipt) != _MATERIALIZATION_FIELDS:
        raise IdentityError("Grok materialization receipt fields changed")
    return receipt


def verify_grok_workspace_rule(
    *,
    workspace_root: Path | str,
    relative_path: str,
    expected_content_sha256: str,
) -> Dict[str, Any]:
    """Body-free verify of an existing create-only rule. No content returned."""

    workspace = absolute_root(str(workspace_root), "Grok workspace root")
    relative = _validate_rule_relative_path(relative_path)
    expected = validate_sha256(expected_content_sha256, "expected rule content")
    artifact = _artifact_path(workspace, relative)
    try:
        details = artifact.lstat()
    except FileNotFoundError as exc:
        raise IdentityError("Grok workspace rule is missing") from exc
    except OSError as exc:
        raise IdentityError("Grok workspace rule is unavailable") from exc
    if not stat.S_ISREG(details.st_mode) or stat.S_ISLNK(details.st_mode):
        raise IdentityError("Grok workspace rule must be a regular non-symlink file")
    observed = sha256_bytes(artifact.read_bytes())
    if observed != expected:
        raise IdentityError("Grok workspace rule content hash changed")
    return {
        "workspace_root": str(workspace),
        "relative_path": relative,
        "content_sha256": observed,
        "content_bytes": details.st_size,
        "present": True,
    }


def rollback_grok_workspace_rule(
    *,
    workspace_root: Path | str,
    relative_path: str,
    expected_content_sha256: str,
) -> Dict[str, Any]:
    """Remove only an exact hash-matching create-only artifact."""

    workspace = absolute_root(str(workspace_root), "Grok workspace root")
    relative = _validate_rule_relative_path(relative_path)
    expected = validate_sha256(expected_content_sha256, "expected rule content")
    artifact = _artifact_path(workspace, relative)
    try:
        details = artifact.lstat()
    except FileNotFoundError:
        receipt = {
            "schema": ROLLBACK_RECEIPT_SCHEMA,
            "target": "grok",
            "target_version": GROK_BUILD_VERSION,
            "workspace_root": str(workspace),
            "relative_path": relative,
            "expected_content_sha256": expected,
            "removed": False,
            "absent_after": True,
            "launch_authorized": False,
            "qualification_authorized": False,
        }
        if set(receipt) != _ROLLBACK_FIELDS:
            raise IdentityError("Grok rollback receipt fields changed")
        return receipt
    except OSError as exc:
        raise IdentityError("Grok workspace rule is unavailable for rollback") from exc
    if not stat.S_ISREG(details.st_mode) or stat.S_ISLNK(details.st_mode):
        raise IdentityError("Grok workspace rule rollback target is not a regular file")
    observed = sha256_bytes(artifact.read_bytes())
    if observed != expected:
        raise IdentityError(
            "Grok workspace rule hash mismatch; refusing non-owned rollback"
        )
    try:
        os.unlink(artifact)
    except OSError as exc:
        raise ValidationError("Grok workspace rule could not be removed") from exc
    if artifact.exists() or artifact.is_symlink():
        raise IdentityError("Grok workspace rule remained after rollback")
    receipt = {
        "schema": ROLLBACK_RECEIPT_SCHEMA,
        "target": "grok",
        "target_version": GROK_BUILD_VERSION,
        "workspace_root": str(workspace),
        "relative_path": relative,
        "expected_content_sha256": expected,
        "removed": True,
        "absent_after": True,
        "launch_authorized": False,
        "qualification_authorized": False,
    }
    if set(receipt) != _ROLLBACK_FIELDS:
        raise IdentityError("Grok rollback receipt fields changed")
    return receipt


def precheck_grok_ordinary_control_artifact_absence(
    *,
    positive_workspace_root: Path | str,
    ordinary_workspace_root: Path | str,
    positive_relative_path: str,
    positive_content_sha256: str,
    workspace_identity_join_sha256: str,
) -> Dict[str, Any]:
    """Structural FS precheck only. Never verifies no-bleed or qualifies.

    Observing that an ordinary directory lacks ``.grok/rules/puppet-*.md`` does
    not prove runtime non-activation.  ``no_bleed_verified`` stays false and
    every authority bit stays false.
    """

    positive = absolute_root(str(positive_workspace_root), "positive workspace")
    ordinary = absolute_root(str(ordinary_workspace_root), "ordinary workspace")
    if positive == ordinary or paths_overlap(positive, ordinary):
        raise IdentityError("Grok matched-control workspaces must be disjoint")
    relative = _validate_rule_relative_path(positive_relative_path)
    content_sha = validate_sha256(positive_content_sha256, "positive rule content")
    join_sha = validate_sha256(
        workspace_identity_join_sha256, "workspace identity join"
    )
    verify_grok_workspace_rule(
        workspace_root=positive,
        relative_path=relative,
        expected_content_sha256=content_sha,
    )
    ordinary_artifact = _artifact_path(ordinary, relative)
    if ordinary_artifact.exists() or ordinary_artifact.is_symlink():
        raise IdentityError(
            "Grok ordinary control contains the Puppet rule; instruction bleed"
        )
    ordinary_rules = ordinary / ".grok" / "rules"
    if ordinary_rules.is_dir() and not ordinary_rules.is_symlink():
        for child in ordinary_rules.iterdir():
            if child.name.startswith("puppet-") and child.name.endswith(".md"):
                raise IdentityError(
                    "Grok ordinary control contains a Puppet-namespaced rule"
                )
    precheck = {
        "schema": MATCHED_CONTROL_PRECHECK_SCHEMA,
        "target": "grok",
        "target_version": GROK_BUILD_VERSION,
        "positive_workspace_root": str(positive),
        "ordinary_workspace_root": str(ordinary),
        "positive_artifact_relative_path": relative,
        "positive_artifact_sha256": content_sha,
        "ordinary_artifact_absent": True,
        "workspace_identity_join_sha256": join_sha,
        "proof_strength": FILESYSTEM_ABSENCE_PROOF,
        "no_bleed_verified": False,
        "activation_authorized": False,
        "launch_authorized": False,
        "qualification_authorized": False,
    }
    precheck["attestation_sha256"] = sha256_bytes(
        canonical_json_bytes(
            {
                name: precheck[name]
                for name in precheck
                if name != "attestation_sha256"
            }
        )
    )
    if set(precheck) != _MATCHED_CONTROL_PRECHECK_FIELDS:
        raise IdentityError("Grok matched-control precheck fields changed")
    validate_bounded_json(
        precheck,
        max_depth=3,
        max_items=32,
        max_string=4096,
        reject_sensitive_fields=True,
    )
    return precheck


def reject_filesystem_only_no_bleed_claim(value: Any = None) -> None:
    """Fail closed on the rejected ordinary-workspace filesystem shortcut."""

    if isinstance(value, Mapping):
        if (
            value.get("schema") == MATCHED_CONTROL_PRECHECK_SCHEMA
            or value.get("proof_strength") == FILESYSTEM_ABSENCE_PROOF
            or (
                value.get("ordinary_artifact_absent") is True
                and value.get("no_bleed_verified") is True
                and value.get("proof_strength") != PAIRED_RUNTIME_PROOF
            )
        ):
            raise UnsupportedError(GROK_NO_BLEED_FS_SHORTCUT_BLOCKER)
    raise UnsupportedError(GROK_NO_BLEED_FS_SHORTCUT_BLOCKER)


def attest_grok_matched_control(
    *,
    positive_workspace_root: Path | str,
    ordinary_workspace_root: Path | str,
    positive_relative_path: str,
    positive_content_sha256: str,
    workspace_identity_join_sha256: str,
) -> Dict[str, Any]:
    """Rejected shortcut: never promote FS absence to no-bleed verification.

    Performs the structural precheck, then always fails closed.  Callers that
    need the non-promotable precheck must use
    ``precheck_grok_ordinary_control_artifact_absence`` explicitly.
    """

    precheck = precheck_grok_ordinary_control_artifact_absence(
        positive_workspace_root=positive_workspace_root,
        ordinary_workspace_root=ordinary_workspace_root,
        positive_relative_path=positive_relative_path,
        positive_content_sha256=positive_content_sha256,
        workspace_identity_join_sha256=workspace_identity_join_sha256,
    )
    reject_filesystem_only_no_bleed_claim(precheck)
    raise UnsupportedError(GROK_NO_BLEED_FS_SHORTCUT_BLOCKER)


def require_grok_qualification_promotion() -> None:
    """Public qualify remains non-promotable in this slice."""

    raise UnsupportedError(GROK_QUALIFICATION_NONPROMOTABLE)


def require_grok_public_launch_authority() -> None:
    """Public puppet.py launch remains fenced in this slice."""

    raise UnsupportedError(GROK_PUBLIC_LAUNCH_FENCED)


def build_grok_terminal_workspace_isolation(
    *,
    descriptor: Mapping[str, Any],
    materialization: Mapping[str, Any],
    matched_control: Mapping[str, Any],
    rollback: Mapping[str, Any],
    startup_cwd: str | Path,
    controller_contract_sha256: str,
    instruction_manifest_sha256: str,
    executable_sha256: str,
    subscription_profile_sha256: str,
    launch_plan_sha256: str,
    observed_model: str,
    halt_receipt_sha256: str,
) -> Dict[str, Any]:
    """Build terminal isolation only from paired-runtime no-bleed proof.

    Filesystem-only prechecks and source-only records cannot construct this
    claim.  This helper remains for a future controller-owned paired runtime
    lane; it is unreachable from the FS shortcut path.
    """

    if (
        not isinstance(descriptor, Mapping)
        or descriptor.get("schema") != DESCRIPTOR_SCHEMA
        or descriptor.get("qualification_authorized") is not False
    ):
        raise ValidationError("Grok terminal isolation requires the entry descriptor")
    if (
        not isinstance(materialization, Mapping)
        or materialization.get("schema") != MATERIALIZATION_RECEIPT_SCHEMA
        or materialization.get("created") is not True
        or materialization.get("qualification_authorized") is not False
    ):
        raise ValidationError("Grok terminal isolation requires create-only materialization")
    if not isinstance(matched_control, Mapping):
        raise ValidationError(
            "Grok terminal isolation requires verified matched ordinary control"
        )
    if (
        matched_control.get("schema") == MATCHED_CONTROL_PRECHECK_SCHEMA
        or matched_control.get("proof_strength") == FILESYSTEM_ABSENCE_PROOF
    ):
        reject_filesystem_only_no_bleed_claim(matched_control)
    if (
        matched_control.get("schema") != MATCHED_CONTROL_SCHEMA
        or matched_control.get("proof_strength") != PAIRED_RUNTIME_PROOF
        or matched_control.get("no_bleed_verified") is not True
        or matched_control.get("qualification_authorized") is not False
    ):
        raise ValidationError(
            "Grok terminal isolation requires paired-runtime matched ordinary control"
        )
    for name in (
        "positive_runtime_halt_sha256",
        "ordinary_runtime_halt_sha256",
        "positive_checkpoint_sha256",
        "ordinary_checkpoint_sha256",
        "positive_attach_sha256",
        "ordinary_attach_sha256",
    ):
        validate_sha256(matched_control.get(name), name.replace("_", " "))
    if (
        not isinstance(rollback, Mapping)
        or rollback.get("schema") != ROLLBACK_RECEIPT_SCHEMA
        or rollback.get("absent_after") is not True
        or rollback.get("qualification_authorized") is not False
    ):
        raise ValidationError("Grok terminal isolation requires hash-guarded rollback")
    cwd = str(startup_cwd)
    if (
        not isinstance(cwd, str)
        or not cwd
        or not Path(cwd).is_absolute()
        or os.path.normpath(cwd) != cwd
        or cwd != descriptor.get("workspace_root")
    ):
        raise IdentityError("Grok terminal isolation startup cwd binding is invalid")
    if observed_model not in {"unavailable", "grok-4.5", "unknown"}:
        raise ValidationError("Grok observed model claim is invalid")
    if (
        materialization.get("relative_path") != descriptor.get("artifact_relative_path")
        or materialization.get("content_sha256")
        != matched_control.get("positive_artifact_sha256")
        or materialization.get("workspace_root") != descriptor.get("workspace_root")
        or matched_control.get("positive_workspace_root")
        != descriptor.get("workspace_root")
        or rollback.get("relative_path") != materialization.get("relative_path")
        or rollback.get("expected_content_sha256")
        != materialization.get("content_sha256")
    ):
        raise IdentityError("Grok terminal isolation artifact join changed")
    value = {
        "schema": TERMINAL_SCHEMA,
        "terminal_state": "controller_verified_after_exact_halt",
        "descriptor_sha256": validate_sha256(
            descriptor.get("descriptor_sha256"), "descriptor fingerprint"
        ),
        "workspace_root": descriptor["workspace_root"],
        "startup_cwd": cwd,
        "artifact_relative_path": materialization["relative_path"],
        "artifact_sha256": materialization["content_sha256"],
        "workspace_identity_sha256": validate_sha256(
            descriptor.get("workspace_identity_sha256"), "workspace identity"
        ),
        "matched_control_sha256": validate_sha256(
            matched_control.get("attestation_sha256"), "matched control"
        ),
        "materialization_sha256": sha256_bytes(canonical_json_bytes(materialization)),
        "rollback_sha256": sha256_bytes(canonical_json_bytes(rollback)),
        "controller_contract_sha256": validate_sha256(
            controller_contract_sha256, "controller contract"
        ),
        "instruction_manifest_sha256": validate_sha256(
            instruction_manifest_sha256, "instruction manifest"
        ),
        "executable_sha256": validate_sha256(executable_sha256, "executable"),
        "subscription_profile_sha256": validate_sha256(
            subscription_profile_sha256, "subscription profile"
        ),
        "launch_plan_sha256": validate_sha256(launch_plan_sha256, "launch plan"),
        "halt_receipt_sha256": validate_sha256(halt_receipt_sha256, "halt receipt"),
        "observed_model": observed_model,
    }
    return value


def validate_grok_workspace_isolation(value: Any) -> Optional[Dict[str, Any]]:
    """Validate terminal Grok workspace isolation without requiring live roots."""

    if value is None:
        return None
    fields = {
        "schema",
        "terminal_state",
        "descriptor_sha256",
        "workspace_root",
        "startup_cwd",
        "artifact_relative_path",
        "artifact_sha256",
        "workspace_identity_sha256",
        "matched_control_sha256",
        "materialization_sha256",
        "rollback_sha256",
        "controller_contract_sha256",
        "instruction_manifest_sha256",
        "executable_sha256",
        "subscription_profile_sha256",
        "launch_plan_sha256",
        "halt_receipt_sha256",
        "observed_model",
    }
    if not isinstance(value, dict) or set(value) != fields:
        raise ValidationError("Grok workspace isolation fields do not match schema")
    validate_bounded_json(value, max_depth=2, max_items=32, max_string=4096)
    if (
        value.get("schema") != TERMINAL_SCHEMA
        or value.get("terminal_state") != "controller_verified_after_exact_halt"
    ):
        raise ValidationError("Grok workspace isolation is not terminal")
    for name in fields - {
        "schema",
        "terminal_state",
        "workspace_root",
        "startup_cwd",
        "artifact_relative_path",
        "observed_model",
    }:
        validate_sha256(value.get(name), name.replace("_", " "))
    _validate_rule_relative_path(value.get("artifact_relative_path"))
    if value.get("observed_model") not in {"unavailable", "grok-4.5", "unknown"}:
        raise ValidationError("Grok observed model claim is invalid")
    roots = {}
    for name in ("workspace_root", "startup_cwd"):
        root = value.get(name)
        if (
            not isinstance(root, str)
            or not root
            or len(root) > 4096
            or not Path(root).is_absolute()
            or root.startswith("//")
            or os.path.normpath(root) != root
            or any(ord(character) < 32 for character in root)
        ):
            raise ValidationError(
                "Grok workspace %s is not normalized and absolute"
                % name.replace("_", " ")
            )
        roots[name] = root
    if roots["workspace_root"] != roots["startup_cwd"]:
        raise ValidationError("Grok workspace startup cwd binding is invalid")
    return dict(value)


def require_source_only_grok_binding(binding: Mapping[str, Any]) -> None:
    """Activation-only / binding-only records remain non-promotable."""

    if (
        not isinstance(binding, Mapping)
        or binding.get("schema") != GROK_WORKSPACE_BINDING_SCHEMA
        or binding.get("state") != GROK_WORKSPACE_BINDING_STATE
        or binding.get("activation_authorized") is not False
        or binding.get("launch_authorized") is not False
        or binding.get("qualification_authorized") is not False
    ):
        raise UnsupportedError(
            "Grok binding-only evidence cannot authorize launch or qualification"
        )


def source_authority_blockers() -> Tuple[str, ...]:
    """Static blockers that keep doctor/census incomplete without terminal proof."""

    return GROK_LAUNCH_AUTHORITY_BLOCKERS + (
        "grok_workspace_project_isolation_requires_terminal_receipt",
        "grok_matched_ordinary_control_required",
        "grok_paired_runtime_no_bleed_required",
        "grok_filesystem_absence_is_nonpromotable",
        "grok_hash_guarded_rollback_required",
        "grok_public_launch_fenced",
        "grok_public_qualification_nonpromotable",
    )


def build_artifact_relative_path(content_sha256: str) -> str:
    digest = validate_sha256(content_sha256, "rule content")
    return "%s%s%s" % (_RULE_RE_PREFIX, digest, _RULE_RE_SUFFIX)


def descriptor_for_effective_contract(
    *,
    adapter_manifest_sha256: str,
    rendered_sha256: str,
) -> Dict[str, Any]:
    """Exact source-owned instruction-plane descriptor for the workspace rule."""

    return build_grok_workspace_addendum_descriptor(
        adapter_manifest_sha256=adapter_manifest_sha256,
        rendered_sha256=rendered_sha256,
    )


def validate_plane_descriptor(raw: Mapping[str, Any]) -> Dict[str, Any]:
    """Accept only the exact Grok workspace addendum instruction-plane shape."""

    return validate_grok_workspace_addendum_descriptor(raw)


__all__ = [
    "DESCRIPTOR_SCHEMA",
    "FILESYSTEM_ABSENCE_PROOF",
    "GROK_NO_BLEED_FS_SHORTCUT_BLOCKER",
    "GROK_PUBLIC_LAUNCH_FENCED",
    "GROK_QUALIFICATION_NONPROMOTABLE",
    "GROK_REGULAR_ARGV_TAIL",
    "GROK_REGULAR_PERMISSION_FLAGS",
    "GROK_REGULAR_SANDBOX_FLAGS",
    "MATCHED_CONTROL_PRECHECK_SCHEMA",
    "MATCHED_CONTROL_SCHEMA",
    "MATERIALIZATION_RECEIPT_SCHEMA",
    "PAIRED_RUNTIME_PROOF",
    "ROLLBACK_RECEIPT_SCHEMA",
    "TERMINAL_SCHEMA",
    "attest_grok_matched_control",
    "build_artifact_relative_path",
    "build_grok_entry_descriptor",
    "build_grok_terminal_workspace_isolation",
    "descriptor_for_effective_contract",
    "grok_probe_mapping_from_qualified",
    "grok_qualified_mapping",
    "grok_regular_launch_argv",
    "is_grok_workspace_mapping_closure",
    "materialize_grok_workspace_rule",
    "precheck_grok_ordinary_control_artifact_absence",
    "reject_filesystem_only_no_bleed_claim",
    "require_grok_public_launch_authority",
    "require_grok_qualification_promotion",
    "require_source_only_grok_binding",
    "rollback_grok_workspace_rule",
    "source_authority_blockers",
    "validate_grok_entry_descriptor",
    "validate_grok_workspace_isolation",
    "validate_plane_descriptor",
    "verify_grok_workspace_rule",
]
