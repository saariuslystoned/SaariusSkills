"""Controller-owned Cursor workspace activation and paired qualification.

The older :mod:`cursor_workspace_plane` module remains a source-only planning
surface.  This module is the narrower live-qualification path: it accepts one
exact qualification-only descriptor, creates one hash-named workspace rule,
derives a private-profile-bound launch plan, and rolls the rule back only after
the shared Pass B controller has recorded exact halt.

An activated Pass B receipt is intentionally not promotable by itself.  The
terminal Cursor receipt below joins it to a separate ordinary control and a
structural read-only native-view observation before it can qualify a manifest.
"""

from __future__ import annotations

import json
import os
import stat
import time
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional, Sequence

from .errors import ConflictError, IdentityError, UnsupportedError, ValidationError
from .instruction_planes import (
    CURSOR_AGENT_VERSION,
    CURSOR_WORKSPACE_ARTIFACT_ID,
    descriptor_fingerprint,
    validate_instruction_plane_descriptor,
)
from .launch import build_admitted_launch_plan, build_launch_identity
from .safety import (
    atomic_write_json,
    canonical_json_bytes,
    read_json,
    sha256_bytes,
    sha256_file,
    validate_bounded_json,
    validate_identifier,
    validate_sha256,
)


CURSOR_QUALIFICATION_DESCRIPTOR_ID = (
    "cursor-2026.07.17-3e2a980-workspace-addendum-qualification-v1"
)
CURSOR_QUALIFICATION_REQUEST_SCHEMA = "puppet.cursor-qualification-request/v1"
CURSOR_QUALIFICATION_ASSERTIONS = (
    "cursor_workspace_context_delta_exact",
    "cursor_workspace_create_only",
    "cursor_workspace_effective_contract_hash_named",
    "cursor_workspace_rollback_after_exact_halt",
)
CURSOR_QUALIFICATION_BLOCKERS = (
    "cursor_default_model_resolution_unavailable",
)
CURSOR_NATIVE_TRIGGER = "Proceed using the active Puppet workspace qualification contract."
CURSOR_NATIVE_TRIGGER_SHA256 = sha256_bytes(
    (CURSOR_NATIVE_TRIGGER + "\n").encode("utf-8")
)

ACTIVATION_PLAN_SCHEMA = "puppet.cursor-workspace-activation-plan/v1"
ACTIVATION_INTENT_SCHEMA = "puppet.cursor-workspace-activation-intent/v1"
ACTIVATION_RECEIPT_SCHEMA = "puppet.cursor-workspace-activation-receipt/v1"
ACTIVATION_CONTEXT_SCHEMA = "puppet.cursor-workspace-activation-context/v1"
ROLLBACK_INTENT_SCHEMA = "puppet.cursor-workspace-rollback-intent/v1"
ROLLBACK_RECEIPT_SCHEMA = "puppet.cursor-workspace-rollback-receipt/v1"
NATIVE_VIEW_SCHEMA = "puppet.cursor-native-view/v1"
TERMINAL_QUALIFICATION_SCHEMA = "puppet.cursor-regular-qualification/v1"

_DIR_MODE = 0o700
_FILE_MODE = 0o600
_MAX_CONTRACT_BYTES = 131072
_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_CLOEXEC = getattr(os, "O_CLOEXEC", 0)
_DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | _NOFOLLOW | _CLOEXEC
_FILE_READ_FLAGS = os.O_RDONLY | _NOFOLLOW | _CLOEXEC
_FILE_CREATE_FLAGS = os.O_WRONLY | os.O_CREAT | os.O_EXCL | _NOFOLLOW | _CLOEXEC


def _json_copy(value: Mapping[str, Any]) -> Dict[str, Any]:
    return json.loads(canonical_json_bytes(dict(value)).decode("utf-8"))


def _exact_contract(value: bytes) -> bytes:
    if (
        not isinstance(value, bytes)
        or not value
        or len(value) > _MAX_CONTRACT_BYTES
        or b"\x00" in value
    ):
        raise ValidationError("Cursor effective contract is invalid")
    try:
        value.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValidationError("Cursor effective contract must be UTF-8") from exc
    return bytes(value)


def _root_identity(path: Path | str, *, label: str) -> Dict[str, Any]:
    candidate = Path(path)
    if (
        not candidate.is_absolute()
        or os.path.normpath(str(candidate)) != str(candidate)
        or "\x00" in str(candidate)
    ):
        raise ValidationError("%s must be normalized and absolute" % label)
    try:
        lexical = os.lstat(candidate)
    except OSError as exc:
        raise IdentityError("%s is unavailable" % label) from exc
    if stat.S_ISLNK(lexical.st_mode) or not stat.S_ISDIR(lexical.st_mode):
        raise IdentityError("%s must be a real directory" % label)
    if lexical.st_uid != os.getuid() or stat.S_IMODE(lexical.st_mode) != _DIR_MODE:
        raise IdentityError("%s must be current-UID mode 0700" % label)
    return {
        "path": str(candidate),
        "device": lexical.st_dev,
        "inode": lexical.st_ino,
        "uid": lexical.st_uid,
        "gid": lexical.st_gid,
        "mode": stat.S_IMODE(lexical.st_mode),
    }


def _same_root(observed: Mapping[str, Any], expected: Mapping[str, Any], *, label: str) -> None:
    if observed != expected:
        raise IdentityError("%s identity changed" % label)


def _open_directory(path: Path, *, label: str) -> int:
    if not _NOFOLLOW or os.stat not in os.supports_dir_fd:
        raise UnsupportedError("Cursor qualification requires no-follow dir-FD primitives")
    try:
        descriptor = os.open(str(path), _DIRECTORY_FLAGS)
    except OSError as exc:
        raise IdentityError("%s cannot be opened safely" % label) from exc
    details = os.fstat(descriptor)
    if (
        not stat.S_ISDIR(details.st_mode)
        or details.st_uid != os.getuid()
        or stat.S_IMODE(details.st_mode) != _DIR_MODE
    ):
        os.close(descriptor)
        raise IdentityError("%s must remain current-UID mode 0700" % label)
    return descriptor


def _open_child_directory(parent_fd: int, name: str, *, label: str) -> int:
    try:
        lexical = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        descriptor = os.open(name, _DIRECTORY_FLAGS, dir_fd=parent_fd)
    except OSError as exc:
        raise IdentityError("%s is unavailable" % label) from exc
    opened = os.fstat(descriptor)
    if (
        stat.S_ISLNK(lexical.st_mode)
        or not stat.S_ISDIR(lexical.st_mode)
        or (lexical.st_dev, lexical.st_ino) != (opened.st_dev, opened.st_ino)
        or opened.st_uid != os.getuid()
        or stat.S_IMODE(opened.st_mode) != _DIR_MODE
    ):
        os.close(descriptor)
        raise IdentityError("%s identity changed" % label)
    return descriptor


def _artifact_relative_path(rendered_sha256: str) -> str:
    rendered = validate_sha256(rendered_sha256, "Cursor rendered contract")
    return ".cursor/rules/puppet-%s.mdc" % rendered


def build_cursor_qualification_request(
    *, adapter_manifest_sha256: str
) -> Dict[str, Any]:
    """Build a body-free request; Pass B derives the hash-named descriptor."""

    value = {
        "schema": CURSOR_QUALIFICATION_REQUEST_SCHEMA,
        "kind": "cursor_workspace_activation_request",
        "target": "cursor",
        "target_version": CURSOR_AGENT_VERSION,
        "adapter_manifest_sha256": validate_sha256(
            adapter_manifest_sha256, "Cursor adapter manifest"
        ),
        "activation": "qualification_only",
        "materialization_authorized": False,
        "launch_authorized": False,
        "qualification_authorized": False,
    }
    return validate_cursor_qualification_request(value)


def validate_cursor_qualification_request(
    value: Mapping[str, Any],
) -> Dict[str, Any]:
    fields = {
        "schema",
        "kind",
        "target",
        "target_version",
        "adapter_manifest_sha256",
        "activation",
        "materialization_authorized",
        "launch_authorized",
        "qualification_authorized",
    }
    result = _json_copy(value)
    if (
        set(result) != fields
        or result.get("schema") != CURSOR_QUALIFICATION_REQUEST_SCHEMA
        or result.get("kind") != "cursor_workspace_activation_request"
        or result.get("target") != "cursor"
        or result.get("target_version") != CURSOR_AGENT_VERSION
        or result.get("activation") != "qualification_only"
        or any(
            result.get(name) is not False
            for name in (
                "materialization_authorized",
                "launch_authorized",
                "qualification_authorized",
            )
        )
    ):
        raise ValidationError("Cursor qualification request is invalid")
    validate_sha256(
        result.get("adapter_manifest_sha256"), "Cursor adapter manifest"
    )
    return result


def build_cursor_qualification_descriptor(
    *,
    adapter_manifest_sha256: str,
    rendered_sha256: str,
) -> Dict[str, Any]:
    """Build the sole Cursor descriptor accepted by the live qualification lane."""

    adapter_sha = validate_sha256(
        adapter_manifest_sha256, "Cursor adapter manifest"
    )
    rendered_sha = validate_sha256(rendered_sha256, "Cursor rendered contract")
    value = {
        "schema": "puppet.instruction-plane/v1",
        "descriptor_id": CURSOR_QUALIFICATION_DESCRIPTOR_ID,
        "target": {
            "harness": "cursor",
            "version": CURSOR_AGENT_VERSION,
            "adapter_manifest_sha256": adapter_sha,
            "requested_model": "default",
            "observed_model": "unavailable",
            "config_fingerprint": "unavailable",
        },
        "plane": "workspace_addendum",
        "status": {"surface": "factual", "activation": "qualification_only"},
        "materialize": [
            {
                "artifact_id": CURSOR_WORKSPACE_ARTIFACT_ID,
                "root_ref": "workspace_root",
                "relative_path": _artifact_relative_path(rendered_sha),
                "content_ref": "effective_contract",
                "write_mode": "create_only",
            }
        ],
        "launch_delta": {
            "cwd_ref": "workspace_root",
            "env": [],
            "argv": [
                {"literal": "--workspace"},
                {"root_ref": "workspace_root"},
            ],
        },
        "rollback": {
            "owned_artifacts": [CURSOR_WORKSPACE_ARTIFACT_ID],
            "preimage_sha256": [],
            "retain_hash_only_proof": True,
        },
        "assertions": list(CURSOR_QUALIFICATION_ASSERTIONS),
        "blockers": list(CURSOR_QUALIFICATION_BLOCKERS),
    }
    return validate_cursor_qualification_descriptor(value)


def validate_cursor_qualification_descriptor(
    value: Mapping[str, Any],
) -> Dict[str, Any]:
    normalized = validate_instruction_plane_descriptor(value)
    if (
        normalized["descriptor_id"] != CURSOR_QUALIFICATION_DESCRIPTOR_ID
        or normalized["target"]["harness"] != "cursor"
        or normalized["target"]["version"] != CURSOR_AGENT_VERSION
        or normalized["target"]["requested_model"] != "default"
        or normalized["target"]["observed_model"] != "unavailable"
        or normalized["target"]["config_fingerprint"] != "unavailable"
        or normalized["plane"] != "workspace_addendum"
        or normalized["status"]
        != {"surface": "factual", "activation": "qualification_only"}
        or normalized["assertions"] != list(CURSOR_QUALIFICATION_ASSERTIONS)
        or normalized["blockers"] != list(CURSOR_QUALIFICATION_BLOCKERS)
    ):
        raise IdentityError("Cursor qualification descriptor tuple changed")
    materialize = normalized["materialize"]
    if len(materialize) != 1:
        raise IdentityError("Cursor qualification artifact tuple changed")
    artifact = materialize[0]
    rendered_sha = artifact["relative_path"].removeprefix(
        ".cursor/rules/puppet-"
    ).removesuffix(".mdc")
    exact = {
        "artifact_id": CURSOR_WORKSPACE_ARTIFACT_ID,
        "root_ref": "workspace_root",
        "relative_path": _artifact_relative_path(rendered_sha),
        "content_ref": "effective_contract",
        "write_mode": "create_only",
    }
    if (
        artifact != exact
        or normalized["launch_delta"]
        != {
            "cwd_ref": "workspace_root",
            "env": [],
            "argv": [
                {"literal": "--workspace"},
                {"root_ref": "workspace_root"},
            ],
        }
        or normalized["rollback"]
        != {
            "owned_artifacts": [CURSOR_WORKSPACE_ARTIFACT_ID],
            "preimage_sha256": [],
            "retain_hash_only_proof": True,
        }
    ):
        raise IdentityError("Cursor qualification descriptor shape changed")
    return normalized


def _manifest_identity(manifest: Any) -> Dict[str, Any]:
    from .adapter_manifest import AdapterManifest
    from .cursor_workspace_plane import (
        CURSOR_ENTRYPOINT_SHA256,
        CURSOR_HELP_SHA256,
        CURSOR_LAUNCHER_SHA256,
        CURSOR_RUNTIME_SHA256,
        CURSOR_VERSION_OBSERVATION_SHA256,
    )

    normalized = AdapterManifest.from_dict(
        dict(manifest.raw) if isinstance(manifest, AdapterManifest) else dict(manifest)
    )
    if (
        normalized.target != "cursor"
        or not normalized.raw["doctor_only"]
        or normalized.raw["qualification"] is not None
        or normalized.raw["platform"].get("system") != "Darwin"
    ):
        raise IdentityError("Cursor activation requires the current doctor-only tuple")
    executable = normalized.raw["executable"]
    version_root = Path(executable["resolved_path"]).parent
    execution = normalized.raw["execution"]
    if (
        version_root.name != CURSOR_AGENT_VERSION
        or Path(executable["resolved_path"]).name != "cursor-agent"
        or executable["sha256"] != CURSOR_LAUNCHER_SHA256
        or executable["version_sha256"] != CURSOR_VERSION_OBSERVATION_SHA256
        or executable["help_sha256"] != CURSOR_HELP_SHA256
        or execution["transition"] != "same_pid_exec"
        or execution["runtime_executable"]["path"] != str(version_root / "node")
        or execution["runtime_executable"]["sha256"] != CURSOR_RUNTIME_SHA256
        or len(execution["support_files"]) != 1
        or execution["support_files"][0]["path"] != str(version_root / "index.js")
        or execution["support_files"][0]["sha256"] != CURSOR_ENTRYPOINT_SHA256
    ):
        raise IdentityError("Cursor activation executable tuple changed")
    normalized.verify_execution_files()
    return {
        "manifest": normalized,
        "manifest_sha256": normalized.fingerprint,
        "execution_sha256": normalized.execution_fingerprint,
        "adapter_sha256": normalized.raw["adapter_fingerprint"],
        "protocol_sha256": normalized.raw["protocol_fingerprint"],
    }


def _validate_plan(value: Mapping[str, Any]) -> Dict[str, Any]:
    fields = {
        "schema",
        "target",
        "descriptor_sha256",
        "adapter_manifest_sha256",
        "adapter_execution_sha256",
        "adapter_implementation_sha256",
        "adapter_protocol_sha256",
        "workspace_root",
        "transaction_root",
        "artifact",
        "launch",
        "plan_sha256",
    }
    if not isinstance(value, Mapping) or set(value) != fields:
        raise ValidationError("Cursor activation plan fields are invalid")
    result = _json_copy(value)
    if result["schema"] != ACTIVATION_PLAN_SCHEMA or result["target"] != "cursor":
        raise ValidationError("Cursor activation plan schema is unsupported")
    for name in (
        "descriptor_sha256",
        "adapter_manifest_sha256",
        "adapter_execution_sha256",
        "adapter_implementation_sha256",
        "adapter_protocol_sha256",
    ):
        validate_sha256(result.get(name), name.replace("_", " "))
    for name in ("workspace_root", "transaction_root"):
        root = result.get(name)
        if not isinstance(root, dict) or set(root) != {
            "path",
            "device",
            "inode",
            "uid",
            "gid",
            "mode",
        }:
            raise ValidationError("Cursor activation root fields are invalid")
        if root.get("uid") != os.getuid() or root.get("mode") != _DIR_MODE:
            raise IdentityError("Cursor activation root authority changed")
    artifact = result.get("artifact")
    if not isinstance(artifact, dict) or set(artifact) != {
        "relative_path",
        "sha256",
        "size",
        "mode",
    }:
        raise ValidationError("Cursor activation artifact fields are invalid")
    expected_path = _artifact_relative_path(artifact.get("sha256"))
    if (
        artifact.get("relative_path") != expected_path
        or artifact.get("mode") != _FILE_MODE
        or isinstance(artifact.get("size"), bool)
        or not isinstance(artifact.get("size"), int)
        or artifact["size"] <= 0
        or artifact["size"] > _MAX_CONTRACT_BYTES
    ):
        raise IdentityError("Cursor activation artifact tuple changed")
    workspace_path = result["workspace_root"]["path"]
    if result.get("launch") != {
        "cwd": workspace_path,
        "argv": ["--workspace", workspace_path],
        "requested_model": "default",
        "observed_model": "unavailable",
    }:
        raise IdentityError("Cursor activation launch delta changed")
    supplied = validate_sha256(result.get("plan_sha256"), "Cursor activation plan")
    unhashed = dict(result)
    unhashed.pop("plan_sha256")
    if supplied != sha256_bytes(canonical_json_bytes(unhashed)):
        raise IdentityError("Cursor activation plan fingerprint changed")
    return result


def plan_cursor_activation(
    *,
    descriptor: Mapping[str, Any],
    adapter_manifest: Any,
    effective_contract: bytes,
    workspace_root: Path | str,
    transaction_root: Path | str,
) -> Dict[str, Any]:
    """Compile one body-free, current-authority-bound activation plan."""

    normalized_descriptor = validate_cursor_qualification_descriptor(descriptor)
    contract = _exact_contract(effective_contract)
    contract_sha = sha256_bytes(contract)
    artifact = normalized_descriptor["materialize"][0]
    if artifact["relative_path"] != _artifact_relative_path(contract_sha):
        raise IdentityError("Cursor descriptor does not name the effective contract")
    manifest = _manifest_identity(adapter_manifest)
    if (
        normalized_descriptor["target"]["adapter_manifest_sha256"]
        != manifest["manifest_sha256"]
    ):
        raise IdentityError("Cursor descriptor manifest authority changed")
    workspace = _root_identity(workspace_root, label="Cursor workspace root")
    transaction = _root_identity(transaction_root, label="Cursor transaction root")
    if Path(workspace["path"]) == Path(transaction["path"]):
        raise ValidationError("Cursor workspace and transaction roots overlap")
    if os.listdir(transaction["path"]):
        raise ConflictError("Cursor activation transaction root must be empty")
    cursor_root = Path(workspace["path"]) / ".cursor"
    if cursor_root.exists() or cursor_root.is_symlink():
        raise ConflictError("Cursor activation requires an absent .cursor root")
    value = {
        "schema": ACTIVATION_PLAN_SCHEMA,
        "target": "cursor",
        "descriptor_sha256": descriptor_fingerprint(normalized_descriptor),
        "adapter_manifest_sha256": manifest["manifest_sha256"],
        "adapter_execution_sha256": manifest["execution_sha256"],
        "adapter_implementation_sha256": manifest["adapter_sha256"],
        "adapter_protocol_sha256": manifest["protocol_sha256"],
        "workspace_root": workspace,
        "transaction_root": transaction,
        "artifact": {
            "relative_path": artifact["relative_path"],
            "sha256": contract_sha,
            "size": len(contract),
            "mode": _FILE_MODE,
        },
        "launch": {
            "cwd": workspace["path"],
            "argv": ["--workspace", workspace["path"]],
            "requested_model": "default",
            "observed_model": "unavailable",
        },
    }
    value["plan_sha256"] = sha256_bytes(canonical_json_bytes(value))
    return _validate_plan(value)


def _plan_paths(plan: Mapping[str, Any]) -> Dict[str, Path]:
    transaction = Path(plan["transaction_root"]["path"])
    return {
        "intent": transaction / "activation-intent.json",
        "receipt": transaction / "activation-receipt.json",
        "context": transaction / "activation-context.json",
        "rollback_intent": transaction / "rollback-intent.json",
        "rollback_receipt": transaction / "rollback-receipt.json",
        "artifact": Path(plan["workspace_root"]["path"])
        / plan["artifact"]["relative_path"],
    }


def _read_exact_file(descriptor: int, *, expected: Mapping[str, Any]) -> bytes:
    details = os.fstat(descriptor)
    if (
        not stat.S_ISREG(details.st_mode)
        or details.st_uid != os.getuid()
        or stat.S_IMODE(details.st_mode) != expected["mode"]
        or details.st_size != expected["size"]
    ):
        raise IdentityError("Cursor workspace rule identity changed")
    chunks = []
    remaining = expected["size"] + 1
    while remaining:
        chunk = os.read(descriptor, min(65536, remaining))
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    payload = b"".join(chunks)
    if len(payload) != expected["size"] or sha256_bytes(payload) != expected["sha256"]:
        raise IdentityError("Cursor workspace rule content changed")
    return payload


def materialize_cursor_activation(
    plan: Mapping[str, Any],
    *,
    effective_contract: bytes,
) -> Dict[str, Any]:
    """Create the exact hash-named rule once, after persisting intent."""

    normalized = _validate_plan(plan)
    contract = _exact_contract(effective_contract)
    if (
        sha256_bytes(contract) != normalized["artifact"]["sha256"]
        or len(contract) != normalized["artifact"]["size"]
    ):
        raise IdentityError("Cursor activation bytes changed after planning")
    _same_root(
        _root_identity(normalized["workspace_root"]["path"], label="Cursor workspace root"),
        normalized["workspace_root"],
        label="Cursor workspace root",
    )
    _same_root(
        _root_identity(
            normalized["transaction_root"]["path"],
            label="Cursor transaction root",
        ),
        normalized["transaction_root"],
        label="Cursor transaction root",
    )
    paths = _plan_paths(normalized)
    if any(path.exists() or path.is_symlink() for path in paths.values()):
        raise ConflictError("Cursor activation path already exists")
    intent = {
        "schema": ACTIVATION_INTENT_SCHEMA,
        "state": "prepared",
        "plan": normalized,
    }
    atomic_write_json(paths["intent"], intent)
    workspace_fd = _open_directory(
        Path(normalized["workspace_root"]["path"]), label="Cursor workspace root"
    )
    cursor_fd = rules_fd = artifact_fd = -1
    try:
        os.mkdir(".cursor", mode=_DIR_MODE, dir_fd=workspace_fd)
        cursor_fd = _open_child_directory(
            workspace_fd, ".cursor", label="Cursor activation directory"
        )
        os.mkdir("rules", mode=_DIR_MODE, dir_fd=cursor_fd)
        rules_fd = _open_child_directory(
            cursor_fd, "rules", label="Cursor rules directory"
        )
        leaf = Path(normalized["artifact"]["relative_path"]).name
        artifact_fd = os.open(
            leaf,
            _FILE_CREATE_FLAGS,
            _FILE_MODE,
            dir_fd=rules_fd,
        )
        written = 0
        while written < len(contract):
            count = os.write(artifact_fd, contract[written:])
            if count <= 0:
                raise IdentityError("Cursor workspace rule write stalled")
            written += count
        os.fsync(artifact_fd)
        details = os.fstat(artifact_fd)
        artifact_identity = {
            "device": details.st_dev,
            "inode": details.st_ino,
            "uid": details.st_uid,
            "gid": details.st_gid,
            "mode": stat.S_IMODE(details.st_mode),
            "size": details.st_size,
            "sha256": normalized["artifact"]["sha256"],
        }
        if (
            artifact_identity["uid"] != os.getuid()
            or artifact_identity["mode"] != _FILE_MODE
            or artifact_identity["size"] != len(contract)
        ):
            raise IdentityError("Cursor workspace rule creation identity is invalid")
    except FileExistsError as exc:
        raise ConflictError("Cursor activation is create-only") from exc
    finally:
        for descriptor in (artifact_fd, rules_fd, cursor_fd, workspace_fd):
            if descriptor >= 0:
                os.close(descriptor)
    receipt = {
        "schema": ACTIVATION_RECEIPT_SCHEMA,
        "state": "active",
        "plan_sha256": normalized["plan_sha256"],
        "intent_sha256": sha256_file(paths["intent"], max_bytes=131072),
        "artifact": {
            "relative_path": normalized["artifact"]["relative_path"],
            **artifact_identity,
        },
        "created_directories": [".cursor", ".cursor/rules"],
    }
    atomic_write_json(paths["receipt"], receipt)
    return receipt


def _validate_materialized(
    plan: Mapping[str, Any],
    receipt: Mapping[str, Any],
) -> Dict[str, Any]:
    normalized = _validate_plan(plan)
    value = _json_copy(receipt)
    if set(value) != {
        "schema",
        "state",
        "plan_sha256",
        "intent_sha256",
        "artifact",
        "created_directories",
    } or (
        value["schema"] != ACTIVATION_RECEIPT_SCHEMA
        or value["state"] != "active"
        or value["plan_sha256"] != normalized["plan_sha256"]
        or value["created_directories"] != [".cursor", ".cursor/rules"]
    ):
        raise IdentityError("Cursor activation receipt changed")
    validate_sha256(value.get("intent_sha256"), "Cursor activation intent")
    artifact = value.get("artifact")
    if not isinstance(artifact, dict) or set(artifact) != {
        "relative_path",
        "device",
        "inode",
        "uid",
        "gid",
        "mode",
        "size",
        "sha256",
    }:
        raise ValidationError("Cursor activation artifact receipt is invalid")
    if (
        artifact["relative_path"] != normalized["artifact"]["relative_path"]
        or artifact["sha256"] != normalized["artifact"]["sha256"]
        or artifact["size"] != normalized["artifact"]["size"]
        or artifact["mode"] != _FILE_MODE
        or artifact["uid"] != os.getuid()
    ):
        raise IdentityError("Cursor activation artifact receipt changed")
    workspace_fd = _open_directory(
        Path(normalized["workspace_root"]["path"]), label="Cursor workspace root"
    )
    cursor_fd = rules_fd = artifact_fd = -1
    try:
        cursor_fd = _open_child_directory(
            workspace_fd, ".cursor", label="Cursor activation directory"
        )
        rules_fd = _open_child_directory(
            cursor_fd, "rules", label="Cursor rules directory"
        )
        leaf = Path(artifact["relative_path"]).name
        artifact_fd = os.open(leaf, _FILE_READ_FLAGS, dir_fd=rules_fd)
        details = os.fstat(artifact_fd)
        if (details.st_dev, details.st_ino) != (
            artifact["device"],
            artifact["inode"],
        ):
            raise IdentityError("Cursor workspace rule vnode changed")
        _read_exact_file(artifact_fd, expected=artifact)
    finally:
        for descriptor in (artifact_fd, rules_fd, cursor_fd, workspace_fd):
            if descriptor >= 0:
                os.close(descriptor)
    return value


def build_cursor_activation_context(
    plan: Mapping[str, Any],
    *,
    materialization_receipt: Mapping[str, Any],
    adapter_manifest: Any,
    session: str,
    run_id: str,
    source_environment: Mapping[str, str],
    bindings: Mapping[str, str],
    admitted_lane_root: Path,
) -> Dict[str, Any]:
    """Join the active rule to the exact private-profile launch environment."""

    normalized = _validate_plan(plan)
    receipt = _validate_materialized(normalized, materialization_receipt)
    manifest = _manifest_identity(adapter_manifest)
    if (
        manifest["manifest_sha256"] != normalized["adapter_manifest_sha256"]
        or manifest["execution_sha256"] != normalized["adapter_execution_sha256"]
        or manifest["adapter_sha256"] != normalized["adapter_implementation_sha256"]
        or manifest["protocol_sha256"] != normalized["adapter_protocol_sha256"]
    ):
        raise IdentityError("Cursor activation adapter authority changed")
    base = list(manifest["manifest"].raw["yolo_mapping"]["launch_argv"])
    argv = base + list(normalized["launch"]["argv"])
    expected = [
        manifest["manifest"].raw["executable"]["resolved_path"],
        "--yolo",
        "--sandbox",
        "disabled",
        "--workspace",
        normalized["workspace_root"]["path"],
    ]
    if argv != expected or argv.count("--workspace") != 1:
        raise IdentityError("Cursor activation launch argv changed")
    environment, launch_identity = build_launch_identity(
        target="cursor",
        repo=Path(normalized["workspace_root"]["path"]),
        argv=argv,
        source_environment=source_environment,
        bindings=bindings,
        admitted_lane_root=admitted_lane_root,
    )
    manifest["manifest"].verify_launch_execution_environment(environment)
    admitted = build_admitted_launch_plan(
        target="cursor",
        session=validate_identifier(session, "Cursor activation session"),
        run_id=validate_identifier(run_id, "Cursor activation run id"),
        repo=Path(normalized["workspace_root"]["path"]),
        argv=argv,
        environment=environment,
        admitted_lane_root=admitted_lane_root,
    )
    value = {
        "schema": ACTIVATION_CONTEXT_SCHEMA,
        "plan_sha256": normalized["plan_sha256"],
        "materialization_receipt_sha256": sha256_bytes(
            canonical_json_bytes(receipt)
        ),
        "artifact_sha256": normalized["artifact"]["sha256"],
        "argv": argv,
        "environment": environment,
        "launch_identity": launch_identity,
        "admitted_launch_plan": admitted,
    }
    validate_bounded_json(value, max_depth=8, max_items=128, max_string=8192)
    return value


def revalidate_cursor_activation_context(
    context: Mapping[str, Any],
    plan: Mapping[str, Any],
    *,
    materialization_receipt: Mapping[str, Any],
    adapter_manifest: Any,
    session: str,
    run_id: str,
    source_environment: Mapping[str, str],
    bindings: Mapping[str, str],
    admitted_lane_root: Path,
) -> Dict[str, Any]:
    rebuilt = build_cursor_activation_context(
        plan,
        materialization_receipt=materialization_receipt,
        adapter_manifest=adapter_manifest,
        session=session,
        run_id=run_id,
        source_environment=source_environment,
        bindings=bindings,
        admitted_lane_root=admitted_lane_root,
    )
    if canonical_json_bytes(dict(context)) != canonical_json_bytes(rebuilt):
        raise IdentityError("Cursor activation launch context changed")
    return rebuilt


def public_cursor_activation_context(
    context: Mapping[str, Any],
) -> Dict[str, Any]:
    """Project private launch values into the value-free proof context."""

    from .launch import validate_admitted_launch_plan

    private = _json_copy(context)
    if set(private) != {
        "schema",
        "plan_sha256",
        "materialization_receipt_sha256",
        "artifact_sha256",
        "argv",
        "environment",
        "launch_identity",
        "admitted_launch_plan",
    } or private.get("schema") != ACTIVATION_CONTEXT_SCHEMA:
        raise ValidationError("Cursor activation launch context is invalid")
    admitted = validate_admitted_launch_plan(
        private["admitted_launch_plan"],
        expected_target="cursor",
    )
    admitted_public = dict(admitted)
    admitted_public.pop("launch_identity")
    environment = private.get("environment")
    environment_names = (
        sorted(environment)
        if isinstance(environment, dict)
        and all(isinstance(name, str) for name in environment)
        and all(isinstance(item, str) for item in environment.values())
        else None
    )
    if (
        admitted_public != private["admitted_launch_plan"]
        or private.get("argv") != admitted["argv"]
        or private.get("launch_identity") != admitted["launch_identity"]
        or environment_names != admitted["env_names"]
        or sha256_bytes(
            canonical_json_bytes(
                [(name, environment[name]) for name in environment_names]
            )
        )
        != admitted["env_fingerprint"]
    ):
        raise IdentityError("Cursor activation admitted launch plan changed")
    return {
        "schema": ACTIVATION_CONTEXT_SCHEMA,
        "plan_sha256": private["plan_sha256"],
        "materialization_receipt_sha256": private[
            "materialization_receipt_sha256"
        ],
        "artifact_sha256": private["artifact_sha256"],
        "launch_identity": private["launch_identity"],
        "admitted_launch_plan": private["admitted_launch_plan"],
    }


def _validate_exact_halt(value: Mapping[str, Any]) -> Dict[str, Any]:
    expected_fields = {
        "schema_version",
        "timestamp",
        "session",
        "target_pid",
        "reason",
        "signal",
        "signal_sent",
        "stopped",
        "tmux_preserved",
        "cleanup_scope",
    }
    result = _json_copy(value)
    if (
        set(result) != expected_fields
        or result.get("schema_version") != 1
        or result.get("signal") != "exact_registered_pid_sigint"
        or result.get("signal_sent") is not True
        or result.get("stopped") is not True
        or result.get("tmux_preserved") is not True
        or result.get("cleanup_scope") != "exact_new_target_only"
        or result.get("reason") != "accepted_probe_halt"
        or isinstance(result.get("target_pid"), bool)
        or not isinstance(result.get("target_pid"), int)
        or result["target_pid"] <= 1
    ):
        raise ValidationError("Cursor rollback lacks exact halt proof")
    validate_identifier(result.get("session"), "Cursor halted session")
    return result


def rollback_cursor_activation(
    plan: Mapping[str, Any],
    *,
    materialization_receipt: Mapping[str, Any],
    exact_halt_receipt: Mapping[str, Any],
) -> Dict[str, Any]:
    """Remove only the receipted rule and transaction-created empty directories."""

    normalized = _validate_plan(plan)
    receipt = _validate_materialized(normalized, materialization_receipt)
    halt = _validate_exact_halt(exact_halt_receipt)
    paths = _plan_paths(normalized)
    if paths["rollback_receipt"].exists() or paths["rollback_receipt"].is_symlink():
        raise ConflictError("Cursor activation is already rolled back")
    rollback_intent = {
        "schema": ROLLBACK_INTENT_SCHEMA,
        "state": "prepared_after_exact_halt",
        "plan_sha256": normalized["plan_sha256"],
        "materialization_receipt_sha256": sha256_bytes(
            canonical_json_bytes(receipt)
        ),
        "halt_receipt_sha256": sha256_bytes(canonical_json_bytes(halt)),
        "artifact": receipt["artifact"],
    }
    atomic_write_json(paths["rollback_intent"], rollback_intent)
    workspace_fd = _open_directory(
        Path(normalized["workspace_root"]["path"]), label="Cursor workspace root"
    )
    cursor_fd = rules_fd = artifact_fd = -1
    try:
        cursor_fd = _open_child_directory(
            workspace_fd, ".cursor", label="Cursor activation directory"
        )
        rules_fd = _open_child_directory(
            cursor_fd, "rules", label="Cursor rules directory"
        )
        leaf = Path(receipt["artifact"]["relative_path"]).name
        artifact_fd = os.open(leaf, _FILE_READ_FLAGS, dir_fd=rules_fd)
        details = os.fstat(artifact_fd)
        if (details.st_dev, details.st_ino) != (
            receipt["artifact"]["device"],
            receipt["artifact"]["inode"],
        ):
            raise IdentityError("Cursor rollback artifact vnode changed")
        _read_exact_file(artifact_fd, expected=receipt["artifact"])
        if os.listdir(rules_fd) != [leaf]:
            raise ConflictError("Cursor rules directory gained foreign content")
        if os.listdir(cursor_fd) != ["rules"]:
            raise ConflictError("Cursor activation directory gained foreign content")
        os.close(artifact_fd)
        artifact_fd = -1
        os.unlink(leaf, dir_fd=rules_fd)
        if os.listdir(rules_fd):
            raise ConflictError("Cursor rules directory gained foreign content")
        os.close(rules_fd)
        rules_fd = -1
        os.rmdir("rules", dir_fd=cursor_fd)
        if os.listdir(cursor_fd):
            raise ConflictError("Cursor activation directory gained foreign content")
        os.close(cursor_fd)
        cursor_fd = -1
        os.rmdir(".cursor", dir_fd=workspace_fd)
    finally:
        for descriptor in (artifact_fd, rules_fd, cursor_fd, workspace_fd):
            if descriptor >= 0:
                os.close(descriptor)
    if paths["artifact"].exists() or paths["artifact"].is_symlink():
        raise IdentityError("Cursor workspace rule remains after rollback")
    result = {
        "schema": ROLLBACK_RECEIPT_SCHEMA,
        "state": "rolled_back_after_exact_halt",
        "plan_sha256": normalized["plan_sha256"],
        "rollback_intent_sha256": sha256_file(
            paths["rollback_intent"], max_bytes=131072
        ),
        "halt_receipt_sha256": rollback_intent["halt_receipt_sha256"],
        "artifact_sha256": normalized["artifact"]["sha256"],
        "removed_artifact": normalized["artifact"]["relative_path"],
        "removed_directories": [".cursor/rules", ".cursor"],
    }
    atomic_write_json(paths["rollback_receipt"], result)
    return result


def validate_cursor_terminal_activation(
    summary: Mapping[str, Any],
    *,
    descriptor: Mapping[str, Any],
    intent: Mapping[str, Any],
    materialization_receipt: Mapping[str, Any],
    context: Mapping[str, Any],
    launch_plan: Mapping[str, Any],
    rollback_intent: Mapping[str, Any],
    rollback_receipt: Mapping[str, Any],
) -> Dict[str, Any]:
    """Rejoin all body-free activation artifacts after exact halt and rollback."""

    from .adapter_manifest import validate_probe_plane_activation
    from .launch import validate_admitted_launch_plan

    terminal = validate_probe_plane_activation(dict(summary))
    if terminal is None:
        raise ValidationError("Cursor terminal activation is unavailable")
    normalized_descriptor = validate_cursor_qualification_descriptor(descriptor)
    if (
        not isinstance(intent, Mapping)
        or intent.get("schema") != ACTIVATION_INTENT_SCHEMA
        or intent.get("state") != "prepared"
        or not isinstance(intent.get("plan"), Mapping)
    ):
        raise ValidationError("Cursor activation intent is invalid")
    plan = _validate_plan(intent["plan"])
    receipt = _json_copy(materialization_receipt)
    _validate_materialized_shape(plan, receipt)
    if receipt["intent_sha256"] != sha256_bytes(
        canonical_json_bytes(dict(intent)) + b"\n"
    ):
        raise IdentityError("Cursor activation intent receipt changed")
    public_context = _json_copy(context)
    if (
        set(public_context)
        != {
            "schema",
            "plan_sha256",
            "materialization_receipt_sha256",
            "artifact_sha256",
            "launch_identity",
            "admitted_launch_plan",
        }
        or public_context.get("schema") != ACTIVATION_CONTEXT_SCHEMA
        or public_context.get("plan_sha256") != plan["plan_sha256"]
        or public_context.get("artifact_sha256") != plan["artifact"]["sha256"]
        or public_context.get("materialization_receipt_sha256")
        != sha256_bytes(canonical_json_bytes(receipt))
    ):
        raise IdentityError("Cursor activation context changed")
    admitted = validate_admitted_launch_plan(
        dict(launch_plan),
        expected_target="cursor",
        expected_session=public_context["admitted_launch_plan"]["session"],
        expected_run_id=public_context["admitted_launch_plan"]["run_id"],
    )
    admitted_public = dict(admitted)
    admitted_public.pop("launch_identity")
    if (
        admitted_public != public_context["admitted_launch_plan"]
        or public_context.get("launch_identity") != admitted["launch_identity"]
    ):
        raise IdentityError("Cursor activation admitted launch plan changed")
    rollback_intent_value = _json_copy(rollback_intent)
    rollback_receipt_value = _json_copy(rollback_receipt)
    if (
        set(rollback_intent_value)
        != {
            "schema",
            "state",
            "plan_sha256",
            "materialization_receipt_sha256",
            "halt_receipt_sha256",
            "artifact",
        }
        or set(rollback_receipt_value)
        != {
            "schema",
            "state",
            "plan_sha256",
            "rollback_intent_sha256",
            "halt_receipt_sha256",
            "artifact_sha256",
            "removed_artifact",
            "removed_directories",
        }
        or rollback_intent_value.get("schema") != ROLLBACK_INTENT_SCHEMA
        or rollback_intent_value.get("state") != "prepared_after_exact_halt"
        or rollback_intent_value.get("plan_sha256") != plan["plan_sha256"]
        or rollback_intent_value.get("materialization_receipt_sha256")
        != sha256_bytes(canonical_json_bytes(receipt))
        or rollback_intent_value.get("artifact") != receipt["artifact"]
        or rollback_receipt_value.get("schema") != ROLLBACK_RECEIPT_SCHEMA
        or rollback_receipt_value.get("state") != "rolled_back_after_exact_halt"
        or rollback_receipt_value.get("plan_sha256") != plan["plan_sha256"]
        or rollback_receipt_value.get("rollback_intent_sha256")
        != sha256_bytes(canonical_json_bytes(rollback_intent_value) + b"\n")
        or rollback_receipt_value.get("halt_receipt_sha256")
        != rollback_intent_value.get("halt_receipt_sha256")
        or rollback_receipt_value.get("artifact_sha256")
        != plan["artifact"]["sha256"]
        or rollback_receipt_value.get("removed_artifact")
        != plan["artifact"]["relative_path"]
        or rollback_receipt_value.get("removed_directories")
        != [".cursor/rules", ".cursor"]
    ):
        raise IdentityError("Cursor activation rollback proof changed")
    expected = {
        "schema": terminal["schema"],
        "qualification_scope": terminal["qualification_scope"],
        "terminal_state": "rolled_back",
        "descriptor_sha256": descriptor_fingerprint(normalized_descriptor),
        "plan_sha256": plan["plan_sha256"],
        "intent_sha256": sha256_bytes(canonical_json_bytes(dict(intent))),
        "materialization_receipt_sha256": sha256_bytes(
            canonical_json_bytes(receipt)
        ),
        "launch_context_sha256": sha256_bytes(canonical_json_bytes(public_context)),
        "artifact_sha256": plan["artifact"]["sha256"],
        "initial_trigger_sha256": CURSOR_NATIVE_TRIGGER_SHA256,
        "rollback_intent_sha256": sha256_bytes(
            canonical_json_bytes(rollback_intent_value)
        ),
        "rollback_receipt_sha256": sha256_bytes(
            canonical_json_bytes(rollback_receipt_value)
        ),
    }
    if terminal != expected:
        raise IdentityError("Cursor terminal activation summary changed")
    return terminal


def _validate_materialized_shape(
    plan: Mapping[str, Any], receipt: Mapping[str, Any]
) -> Dict[str, Any]:
    """Shape-only receipt verifier used after terminal rollback."""

    normalized = _validate_plan(plan)
    value = _json_copy(receipt)
    artifact = value.get("artifact")
    if (
        set(value)
        != {
            "schema",
            "state",
            "plan_sha256",
            "intent_sha256",
            "artifact",
            "created_directories",
        }
        or value.get("schema") != ACTIVATION_RECEIPT_SCHEMA
        or value.get("state") != "active"
        or value.get("plan_sha256") != normalized["plan_sha256"]
        or value.get("created_directories") != [".cursor", ".cursor/rules"]
        or not isinstance(artifact, dict)
        or set(artifact)
        != {
            "relative_path",
            "device",
            "inode",
            "uid",
            "gid",
            "mode",
            "size",
            "sha256",
        }
        or artifact.get("relative_path")
        != normalized["artifact"]["relative_path"]
        or artifact.get("sha256") != normalized["artifact"]["sha256"]
        or artifact.get("size") != normalized["artifact"]["size"]
        or artifact.get("mode") != _FILE_MODE
        or artifact.get("uid") != os.getuid()
        or any(
            isinstance(artifact.get(name), bool)
            or not isinstance(artifact.get(name), int)
            or artifact[name] < minimum
            for name, minimum in (
                ("device", 1),
                ("inode", 1),
                ("uid", 0),
                ("gid", 0),
                ("mode", 0),
                ("size", 1),
            )
        )
    ):
        raise IdentityError("Cursor activation receipt changed")
    validate_sha256(value.get("intent_sha256"), "Cursor activation intent")
    return value


def record_cursor_native_view(
    *,
    run_root: Path,
    timeout: float = 120.0,
    poll_interval: float = 0.1,
    _tmux_factory: Optional[Callable[[Path], Any]] = None,
    _sleep_fn: Callable[[float], None] = time.sleep,
    _monotonic_fn: Callable[[], float] = time.monotonic,
) -> Dict[str, Any]:
    """Observe one read-only native tmux client attach and detach structurally."""

    from .tmux import TmuxController

    if timeout <= 0 or timeout > 600:
        raise ValidationError("Cursor native-view timeout is invalid")
    root = Path(run_root).resolve(strict=True)
    state_path = root / "state.json"
    evidence_path = root / "evidence.json"
    output = root / "cursor-native-view.json"
    if output.exists() or output.is_symlink():
        raise ConflictError("Cursor native-view receipt already exists")
    state = read_json(state_path, max_bytes=131072, reject_sensitive_fields=True)
    evidence = read_json(
        evidence_path, max_bytes=131072, reject_sensitive_fields=True
    )
    if (
        state.get("target") != "cursor"
        or evidence.get("target") != "cursor"
        or state.get("run_id") != evidence.get("run_id")
        or not isinstance(state.get("attach_command"), str)
        or not state["attach_command"]
        or not isinstance(evidence.get("tmux"), dict)
    ):
        raise ValidationError("Cursor probe is not ready for native-view observation")
    tmux_record = evidence["tmux"]
    socket = Path(tmux_record["socket"])
    controller = (
        TmuxController(root / "tmux-authority")
        if _tmux_factory is None
        else _tmux_factory(root / "tmux-authority")
    )
    baseline = controller.viewer_clients(
        socket=socket,
        session=tmux_record["session"],
        server_identity=tmux_record["server_identity"],
    )
    if baseline:
        raise ConflictError("Cursor native-view observation requires no prior client")
    deadline = _monotonic_fn() + timeout
    observed: Optional[Dict[str, Any]] = None
    while _monotonic_fn() < deadline:
        clients = controller.viewer_clients(
            socket=socket,
            session=tmux_record["session"],
            server_identity=tmux_record["server_identity"],
        )
        if clients:
            if len(clients) != 1 or clients[0].get("read_only") is not True:
                raise IdentityError("Cursor native viewer is not one read-only client")
            observed = clients[0]
            break
        _sleep_fn(poll_interval)
    if observed is None:
        raise UnsupportedError("Cursor native viewer attachment was not observed")
    while _monotonic_fn() < deadline:
        clients = controller.viewer_clients(
            socket=socket,
            session=tmux_record["session"],
            server_identity=tmux_record["server_identity"],
        )
        if not clients:
            break
        if clients != [observed]:
            raise IdentityError("Cursor native viewer population changed")
        _sleep_fn(poll_interval)
    else:
        raise UnsupportedError("Cursor native viewer detach was not observed")
    result = {
        "schema": NATIVE_VIEW_SCHEMA,
        "target": "cursor",
        "run_id": state["run_id"],
        "session": tmux_record["session"],
        "tmux_identity_sha256": sha256_bytes(canonical_json_bytes(tmux_record)),
        "attach_command_sha256": sha256_bytes(
            canonical_json_bytes(state["attach_command"])
        ),
        "viewer": observed,
        "read_only": True,
        "attached": True,
        "detached": True,
    }
    atomic_write_json(output, result)
    return result


def cursor_qualified_mapping(mapping: Mapping[str, Any]) -> Dict[str, Any]:
    """Close only the dynamic absolute-workspace isolation bit."""

    result = _json_copy(mapping)
    if (
        result.get("complete") is not False
        or result.get("project_isolation_declared") is not False
        or result.get("project_isolation_flags") != []
        or result.get("permission_flags") != ["--yolo"]
        or result.get("sandbox_flags") != ["--sandbox", "disabled"]
    ):
        raise IdentityError("Cursor doctor mapping is not the exact incomplete tuple")
    result["complete"] = True
    result["project_isolation_declared"] = True
    return result


def cursor_probe_mapping_from_qualified(mapping: Mapping[str, Any]) -> Dict[str, Any]:
    qualified = _json_copy(mapping)
    if (
        qualified.get("complete") is not True
        or qualified.get("project_isolation_declared") is not True
        or qualified.get("project_isolation_flags") != []
    ):
        raise IdentityError("Cursor qualified mapping closure changed")
    probe = dict(qualified)
    probe["complete"] = False
    probe["project_isolation_declared"] = False
    if cursor_qualified_mapping(probe) != qualified:
        raise IdentityError("Cursor qualified mapping closure is not exact")
    return probe


def is_cursor_mapping_closure(mapping: Mapping[str, Any]) -> bool:
    try:
        return cursor_qualified_mapping(
            cursor_probe_mapping_from_qualified(mapping)
        ) == _json_copy(mapping)
    except (IdentityError, TypeError, ValueError):
        return False


def cursor_regular_launch_argv(
    mapping: Mapping[str, Any],
    *,
    base_argv: Sequence[str],
    workspace_root: Path | str,
) -> list[str]:
    """Compose the qualified dynamic workspace selector for a normal session."""

    if not is_cursor_mapping_closure(mapping):
        raise UnsupportedError(
            "Cursor regular launch lacks terminal workspace qualification"
        )
    workspace = Path(workspace_root)
    if (
        not workspace.is_absolute()
        or os.path.normpath(str(workspace)) != str(workspace)
        or "\x00" in str(workspace)
    ):
        raise ValidationError("Cursor regular workspace must be normalized and absolute")
    base = list(base_argv)
    if base != list(mapping["launch_argv"]):
        raise IdentityError("Cursor regular base argv changed")
    if any(
        item
        in {
            "--workspace",
            "--worktree",
            "--worktree-base",
            "--add-dir",
            "--api-key",
            "--config",
            "--profile",
            "--model",
        }
        for item in base
    ):
        raise IdentityError("Cursor regular base argv gained a forbidden selector")
    return [*base, "--workspace", str(workspace)]


def cursor_qualification_launch_argv(
    mapping: Mapping[str, Any],
    *,
    base_argv: Sequence[str],
    workspace_root: Path | str,
) -> list[str]:
    """Compose the same dynamic selector for the ordinary Pass B control."""

    qualified = cursor_qualified_mapping(mapping)
    return cursor_regular_launch_argv(
        qualified,
        base_argv=base_argv,
        workspace_root=workspace_root,
    )


def _receipt_ref(path: Path) -> Dict[str, str]:
    resolved = Path(path).resolve(strict=True)
    if resolved.is_symlink() or not resolved.is_file():
        raise ValidationError("Cursor qualification receipt reference is invalid")
    return {
        "path": str(resolved),
        "sha256": sha256_file(resolved, max_bytes=131072),
    }


def _load_ref(value: Mapping[str, Any], *, label: str) -> tuple[Path, Dict[str, Any]]:
    if not isinstance(value, Mapping) or set(value) != {"path", "sha256"}:
        raise ValidationError("%s reference is invalid" % label)
    path = Path(value["path"])
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise ValidationError("%s reference is unavailable" % label)
    if sha256_file(path, max_bytes=131072) != validate_sha256(
        value.get("sha256"), "%s fingerprint" % label
    ):
        raise IdentityError("%s reference changed" % label)
    return path, read_json(path, max_bytes=131072, reject_sensitive_fields=True)


def build_cursor_terminal_qualification(
    *,
    activated_receipt_path: Path,
    ordinary_receipt_path: Path,
    native_view_path: Path,
    authority_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Mint the sole promotable Cursor receipt from three independently verified inputs."""

    from .adapter_manifest import verify_qualification_receipt

    activated = verify_qualification_receipt(
        Path(activated_receipt_path), _authority_root=authority_root
    )
    ordinary = verify_qualification_receipt(
        Path(ordinary_receipt_path), _authority_root=authority_root
    )
    if (
        activated["target"] != "cursor"
        or ordinary["target"] != "cursor"
        or activated.get("plane_activation") is None
        or ordinary.get("plane_activation") is not None
        or activated["run_id"] == ordinary["run_id"]
    ):
        raise ValidationError(
            "Cursor qualification requires one activated run and one distinct ordinary control"
        )
    return _build_cursor_terminal_from_verified(
        activated_receipt_path=Path(activated_receipt_path),
        activated=activated,
        ordinary_receipt_path=Path(ordinary_receipt_path),
        ordinary=ordinary,
        native_view_path=Path(native_view_path),
        authority_root=authority_root,
        attest=True,
    )


def _build_cursor_terminal_from_verified(
    *,
    activated_receipt_path: Path,
    activated: Mapping[str, Any],
    ordinary_receipt_path: Path,
    ordinary: Mapping[str, Any],
    native_view_path: Path,
    authority_root: Optional[Path],
    attest: bool,
) -> Dict[str, Any]:
    from .adapter_manifest import PROBE_CAPABILITIES
    from .authority import attest_qualification

    exact_names = (
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
        "session_profile",
    )
    if any(activated[name] != ordinary[name] for name in exact_names):
        raise IdentityError("Cursor activated and ordinary control authority differs")
    if (
        activated.get("capabilities") != list(PROBE_CAPABILITIES)
        or ordinary.get("capabilities") != list(PROBE_CAPABILITIES)
    ):
        raise ValidationError("Cursor paired runs lack the shared capability contract")
    view_path, view = _load_ref(
        _receipt_ref(native_view_path), label="Cursor native view"
    )
    activated_root = Path(activated_receipt_path).resolve(strict=True).parent
    activated_state = read_json(
        activated_root / "state.json",
        max_bytes=131072,
        reject_sensitive_fields=True,
    )
    activated_evidence = read_json(
        activated_root / "evidence.json",
        max_bytes=131072,
        reject_sensitive_fields=True,
    )
    ordinary_root = Path(ordinary_receipt_path).resolve(strict=True).parent
    ordinary_evidence = read_json(
        ordinary_root / "evidence.json",
        max_bytes=131072,
        reject_sensitive_fields=True,
    )
    viewer = view.get("viewer")
    if (
        view.get("schema") != NATIVE_VIEW_SCHEMA
        or view.get("target") != "cursor"
        or view.get("run_id") != activated["run_id"]
        or view.get("session") != activated_state.get("session")
        or view.get("read_only") is not True
        or view.get("attached") is not True
        or view.get("detached") is not True
        or view.get("tmux_identity_sha256")
        != sha256_bytes(canonical_json_bytes(activated_evidence["tmux"]))
        or view.get("attach_command_sha256")
        != sha256_bytes(canonical_json_bytes(activated_state["attach_command"]))
        or not isinstance(viewer, dict)
        or set(viewer) != {"pid", "tty", "read_only", "session"}
        or isinstance(viewer.get("pid"), bool)
        or not isinstance(viewer.get("pid"), int)
        or viewer["pid"] <= 1
        or not isinstance(viewer.get("tty"), str)
        or not viewer["tty"].startswith("/dev/")
        or viewer.get("read_only") is not True
        or viewer.get("session") != view.get("session")
    ):
        raise IdentityError("Cursor native-view observation does not join the activated run")
    activated_cwd = activated_evidence["launch_identity"]["cwd"]
    ordinary_cwd = ordinary_evidence["launch_identity"]["cwd"]
    if (
        activated_cwd == ordinary_cwd
        or activated_evidence.get("fixture_fingerprint_before")
        != activated_evidence.get("fixture_fingerprint_after")
        or ordinary_evidence.get("fixture_fingerprint_before")
        != ordinary_evidence.get("fixture_fingerprint_after")
    ):
        raise IdentityError("Cursor paired workspace no-bleed evidence is invalid")
    core = {
        "schema": TERMINAL_QUALIFICATION_SCHEMA,
        "kind": "cursor_regular_paired_qualification",
        "target": "cursor",
        "run_id": "cursor-pair-%s" % sha256_bytes(
            canonical_json_bytes(
                [activated["run_id"], ordinary["run_id"], view["session"]]
            )
        )[:32],
        "controller": activated["controller"],
        "campaign_id": activated["campaign_id"],
        "goal_fingerprint": activated["goal_fingerprint"],
        "session_profile": activated["session_profile"],
        "executable_fingerprint": activated["executable_fingerprint"],
        "execution_fingerprint": activated["execution_fingerprint"],
        "version_fingerprint": activated["version_fingerprint"],
        "platform_fingerprint": activated["platform_fingerprint"],
        "adapter_fingerprint": activated["adapter_fingerprint"],
        "protocol_fingerprint": activated["protocol_fingerprint"],
        "yolo_mapping_sha256": activated["yolo_mapping_sha256"],
        "subscription_profile_sha256": activated["subscription_profile_sha256"],
        "instruction_policy_fingerprint": activated[
            "instruction_policy_fingerprint"
        ],
        "capabilities": list(PROBE_CAPABILITIES),
        "accepted_checkpoint_id": activated["accepted_checkpoint_id"],
        "acceptance_sha256": activated["acceptance_sha256"],
        "halt_receipt_sha256": activated["halt_receipt_sha256"],
        "activated_receipt": _receipt_ref(activated_receipt_path),
        "ordinary_control_receipt": _receipt_ref(ordinary_receipt_path),
        "native_view_receipt": _receipt_ref(view_path),
        "default_model": {
            "requested": "default",
            "observed": "unavailable",
            "explicit_model_injected": False,
        },
        "no_bleed": {
            "ordinary_activation_absent": True,
            "workspaces_distinct": True,
            "activated_workspace_restored": True,
            "ordinary_workspace_unchanged": True,
            "private_profile_identical": True,
        },
        "terminal_state": "paired_control_verified_after_exact_halt_and_rollback",
    }
    if not attest:
        return core
    attestation = attest_qualification(core, authority_root=authority_root)
    return {**core, "controller_attestation": attestation}


def verify_cursor_terminal_qualification(
    path: Path,
    *,
    authority_root: Optional[Path] = None,
    current_manifest: Optional[Any] = None,
) -> Dict[str, Any]:
    """Reverify a paired terminal receipt and both underlying Pass B runs."""

    from .adapter_manifest import PROBE_CAPABILITIES, verify_qualification_receipt
    from .authority import verify_qualification_attestation

    candidate = Path(path)
    if candidate.is_symlink() or not candidate.is_file():
        raise ValidationError("Cursor terminal qualification is unavailable")
    value = read_json(candidate, max_bytes=131072, reject_sensitive_fields=True)
    fields = {
        "schema",
        "kind",
        "target",
        "run_id",
        "controller",
        "campaign_id",
        "goal_fingerprint",
        "session_profile",
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
        "accepted_checkpoint_id",
        "acceptance_sha256",
        "halt_receipt_sha256",
        "activated_receipt",
        "ordinary_control_receipt",
        "native_view_receipt",
        "default_model",
        "no_bleed",
        "terminal_state",
        "controller_attestation",
    }
    if not isinstance(value, dict) or set(value) != fields:
        raise ValidationError("Cursor terminal qualification fields are invalid")
    if (
        value.get("schema") != TERMINAL_QUALIFICATION_SCHEMA
        or value.get("kind") != "cursor_regular_paired_qualification"
        or value.get("target") != "cursor"
        or value.get("session_profile") != "regular"
        or value.get("capabilities") != list(PROBE_CAPABILITIES)
        or value.get("terminal_state")
        != "paired_control_verified_after_exact_halt_and_rollback"
        or value.get("default_model")
        != {
            "requested": "default",
            "observed": "unavailable",
            "explicit_model_injected": False,
        }
        or value.get("no_bleed")
        != {
            "ordinary_activation_absent": True,
            "workspaces_distinct": True,
            "activated_workspace_restored": True,
            "ordinary_workspace_unchanged": True,
            "private_profile_identical": True,
        }
    ):
        raise ValidationError("Cursor terminal qualification state is invalid")
    core = dict(value)
    attestation = core.pop("controller_attestation")
    verify_qualification_attestation(core, attestation, authority_root=authority_root)
    activated_path, _ = _load_ref(
        value["activated_receipt"], label="Cursor activated receipt"
    )
    ordinary_path, _ = _load_ref(
        value["ordinary_control_receipt"], label="Cursor ordinary control receipt"
    )
    view_path, _ = _load_ref(value["native_view_receipt"], label="Cursor native view")
    activated = verify_qualification_receipt(
        activated_path,
        _authority_root=authority_root,
        _current_manifest=current_manifest,
    )
    ordinary = verify_qualification_receipt(
        ordinary_path,
        _authority_root=authority_root,
        _current_manifest=current_manifest,
    )
    rebuilt_core = _build_cursor_terminal_from_verified(
        activated_receipt_path=activated_path,
        activated=activated,
        ordinary_receipt_path=ordinary_path,
        ordinary=ordinary,
        native_view_path=view_path,
        authority_root=authority_root,
        attest=False,
    )
    if rebuilt_core != core:
        raise IdentityError("Cursor terminal qualification join changed")
    if current_manifest is not None:
        manifest = _manifest_identity(current_manifest)
        expected = {
            "executable_fingerprint": manifest["manifest"].raw["executable"]["sha256"],
            "execution_fingerprint": manifest["execution_sha256"],
            "adapter_fingerprint": manifest["adapter_sha256"],
            "protocol_fingerprint": manifest["protocol_sha256"],
        }
        if any(value[name] != observed for name, observed in expected.items()):
            raise IdentityError("Cursor terminal qualification is stale")
    return value


__all__ = [
    "ACTIVATION_CONTEXT_SCHEMA",
    "ACTIVATION_INTENT_SCHEMA",
    "ACTIVATION_PLAN_SCHEMA",
    "ACTIVATION_RECEIPT_SCHEMA",
    "CURSOR_NATIVE_TRIGGER",
    "CURSOR_NATIVE_TRIGGER_SHA256",
    "CURSOR_QUALIFICATION_DESCRIPTOR_ID",
    "CURSOR_QUALIFICATION_REQUEST_SCHEMA",
    "NATIVE_VIEW_SCHEMA",
    "ROLLBACK_INTENT_SCHEMA",
    "ROLLBACK_RECEIPT_SCHEMA",
    "TERMINAL_QUALIFICATION_SCHEMA",
    "build_cursor_activation_context",
    "build_cursor_qualification_descriptor",
    "build_cursor_qualification_request",
    "build_cursor_terminal_qualification",
    "cursor_probe_mapping_from_qualified",
    "cursor_qualification_launch_argv",
    "cursor_qualified_mapping",
    "cursor_regular_launch_argv",
    "is_cursor_mapping_closure",
    "materialize_cursor_activation",
    "plan_cursor_activation",
    "public_cursor_activation_context",
    "record_cursor_native_view",
    "revalidate_cursor_activation_context",
    "rollback_cursor_activation",
    "validate_cursor_qualification_descriptor",
    "validate_cursor_qualification_request",
    "validate_cursor_terminal_activation",
    "verify_cursor_terminal_qualification",
]
