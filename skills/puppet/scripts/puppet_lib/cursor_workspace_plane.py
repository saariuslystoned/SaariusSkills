"""Planner-only Cursor workspace instruction-plane substrate.

The exact installed Cursor tuple exposes a plausible workspace guidance
surface, but Puppet has not proved activation, no-bleed behavior, isolated
authentication, default-model resolution, or a race-safe rollback primitive.
This module therefore plans and revalidates only.  It never creates guidance,
launches Cursor, mints halt authority, or removes filesystem objects.

The public artifacts are a body-free disabled plan and a source-only binding
that joins the exact compiler manifest, effective-contract hash, controller
identities, descriptor, current adapter tuple, and plan. Private guidance bytes
are never returned or persisted here.
"""

from __future__ import annotations

import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, NoReturn, Optional, Sequence, Tuple

from .adapter_manifest import AdapterManifest, QUALIFICATION_PROFILE
from .census import adapter_implementation_fingerprint
from .errors import ConflictError, IdentityError, UnsupportedError, ValidationError
from .handoffs import PROTOCOL_FINGERPRINT
from .instruction_planes import (
    CURSOR_MDC_ALWAYS_APPLY_CONTENT_REF,
    CURSOR_WORKSPACE_DESCRIPTOR_ID,
    descriptor_fingerprint,
    validate_cursor_workspace_addendum_descriptor,
)
from .instructions import validate_instruction_manifest
from .safety import (
    canonical_json_bytes,
    sha256_bytes,
    validate_bounded_json,
    validate_identifier,
    validate_sha256,
)


CURSOR_VERSION = "2026.07.17-3e2a980"
CURSOR_VERSION_OBSERVATION_SHA256 = (
    "ff67fa8c4d173904e13f0da944d7f763f5399ec48052b81c1ae3c7d87f118f4a"
)
CURSOR_LAUNCHER_SHA256 = (
    "eed61c5224668c9236334c4c68936a16aecc37374b592f59e31eb50433817831"
)
CURSOR_RUNTIME_SHA256 = (
    "336b5b3ebc5deb86df842102b20b6e4761605b7a667823e68dda7761b91a161b"
)
CURSOR_ENTRYPOINT_SHA256 = (
    "f45ce0860ce8c282110c2f8cfc04e0e8d8b3bc6a83ad01fcded0b5916e1e3a6e"
)
CURSOR_HELP_SHA256 = "bb2aed29e46b3c80635858d2181c140985dbf9f6a96d788f1b6a8adbb0d725af"

PLAN_SCHEMA = "puppet.cursor-workspace-plane-plan/v2"
BINDING_SCHEMA = "puppet.cursor-workspace-plane-binding/v1"
BINDING_STATE = "binding_only"
STATUS = {"surface": "hypothesis", "activation": "disabled"}
BLOCKERS = (
    "cursor_default_model_resolution_unavailable",
    "cursor_live_process_population_unproved",
    "cursor_workspace_plane_no_bleed_unproved",
    "cursor_workspace_rule_activation_unqualified",
    "cursor_workspace_cleanup_has_no_race_safe_delete_primitive",
)

_DIR_MODE = 0o700
_MAX_GUIDANCE_BYTES = 131072
_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_CLOEXEC = getattr(os, "O_CLOEXEC", 0)
_DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | _NOFOLLOW | _CLOEXEC
_EMPTY_PREIMAGE_SHA256 = sha256_bytes(canonical_json_bytes([]))
_LIFECYCLE_DISABLED = (
    "Cursor workspace materialization, launch, rollback, and recovery remain "
    "disabled: Python/macOS has no conditional pathname delete bound to a "
    "previously verified vnode, and no controller-attested exact halt proof "
    "is integrated"
)

_ROOT_KEYS = {
    "kind",
    "path",
    "lane_relative_path",
    "device",
    "inode",
    "uid",
    "gid",
    "mode",
    "nlink",
}
_PLAN_KEYS = {
    "schema",
    "target",
    "cursor_version",
    "scope_id",
    "status",
    "blockers",
    "launch_authorized",
    "launch_delta",
    "materialization_supported",
    "rollback_supported",
    "recovery_supported",
    "adapter_manifest_sha256",
    "adapter_implementation_sha256",
    "adapter_protocol_sha256",
    "execution_fingerprint",
    "admitted_lane_root",
    "workspace_root",
    "planned_artifact",
    "workspace_preimage_sha256",
    "plan_sha256",
}
_CONTRACT_IDENTITY_KEYS = {
    "fingerprint",
    "controller",
    "target",
    "task_profile",
}
_RUN_IDENTITY_KEYS = {"session", "run_id", "nonce"}
_BINDING_KEYS = {
    "schema",
    "state",
    "target",
    "target_version",
    "plane",
    "descriptor_id",
    "descriptor_sha256",
    "instruction_manifest_sha256",
    "instruction_policy_fingerprint",
    "effective_contract_fingerprint",
    "effective_contract_sha256",
    "effective_contract_bytes",
    "contract_identity_sha256",
    "workspace_identity_sha256",
    "run_identity_sha256",
    "adapter_manifest_sha256",
    "adapter_implementation_sha256",
    "adapter_protocol_sha256",
    "adapter_execution_sha256",
    "workspace_plan_sha256",
    "launch_delta_sha256",
    "launch_argv_sha256",
    "requested_model",
    "observed_model",
    "config_fingerprint",
    "artifact",
    "activation_authorized",
    "launch_authorized",
    "qualification_authorized",
}
_BINDING_HASH_KEYS = {
    name
    for name in _BINDING_KEYS
    if name.endswith("_sha256")
    or (name.endswith("_fingerprint") and name != "config_fingerprint")
}


def _require_fd_primitives() -> None:
    if not _NOFOLLOW or os.stat not in os.supports_dir_fd:
        raise UnsupportedError(
            "Cursor workspace planning requires no-follow dir-FD primitives"
        )
    if os.listdir not in os.supports_fd:
        raise UnsupportedError(
            "Cursor workspace planning requires FD directory listing"
        )


def _exact_int(value: Any, *, label: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValidationError("%s is invalid" % label)
    return value


def _absolute_lexical(path: Path | str, *, label: str) -> Path:
    try:
        raw = os.fspath(path)
    except TypeError as exc:
        raise ValidationError("%s must be a filesystem path" % label) from exc
    if (
        not isinstance(raw, str)
        or not raw
        or "\x00" in raw
        or len(raw) > 4096
        or not os.path.isabs(raw)
    ):
        raise ValidationError("%s must be an absolute path" % label)
    normalized = os.path.normpath(raw)
    if normalized != raw:
        raise ValidationError("%s must be normalized" % label)
    return Path(normalized)


def _safe_relative_parts(value: str, *, label: str) -> Tuple[str, ...]:
    if (
        not isinstance(value, str)
        or not value
        or value.startswith("/")
        or "\\" in value
        or "\x00" in value
    ):
        raise ValidationError("%s must be a safe relative path" % label)
    parts = tuple(value.split("/"))
    if any(not part or part in {".", ".."} for part in parts):
        raise ValidationError("%s must be a safe relative path" % label)
    return parts


def _descendant_parts(path: Path, lane: Path, *, label: str) -> Tuple[str, ...]:
    try:
        relative = path.relative_to(lane)
    except ValueError as exc:
        raise ValidationError("%s must be beneath the admitted lane" % label) from exc
    parts = relative.parts
    if not parts:
        raise ValidationError(
            "%s must be beneath, not equal to, the admitted lane" % label
        )
    if any(part in {"", ".", ".."} for part in parts):
        raise ValidationError("%s has an invalid lane-relative path" % label)
    return tuple(parts)


def _directory_identity(
    details: os.stat_result,
    *,
    kind: str,
    path: str,
    lane_relative_path: str,
) -> Dict[str, Any]:
    if not stat.S_ISDIR(details.st_mode):
        raise IdentityError("bound root is not a directory")
    result = {
        "kind": kind,
        "path": path,
        "lane_relative_path": lane_relative_path,
        "device": details.st_dev,
        "inode": details.st_ino,
        "uid": details.st_uid,
        "gid": details.st_gid,
        "mode": stat.S_IMODE(details.st_mode),
        "nlink": details.st_nlink,
    }
    if result["uid"] != os.getuid() or result["mode"] != _DIR_MODE:
        raise IdentityError("%s must be current-UID 0700" % kind)
    return result


def _validate_root(value: Any, *, kind: str) -> Dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _ROOT_KEYS:
        raise ValidationError("%s identity fields are invalid" % kind)
    if value.get("kind") != kind:
        raise ValidationError("%s type is invalid" % kind)
    path = _absolute_lexical(value.get("path"), label=kind)
    relative = value.get("lane_relative_path")
    if kind == "admitted_lane_root":
        if relative != ".":
            raise ValidationError("admitted lane relative path is invalid")
    else:
        relative = "/".join(
            _safe_relative_parts(relative, label="workspace lane-relative path")
        )
    result = {
        "kind": kind,
        "path": str(path),
        "lane_relative_path": relative,
        "device": _exact_int(value.get("device"), label="%s device" % kind),
        "inode": _exact_int(value.get("inode"), label="%s inode" % kind, minimum=1),
        "uid": _exact_int(value.get("uid"), label="%s uid" % kind),
        "gid": _exact_int(value.get("gid"), label="%s gid" % kind),
        "mode": _exact_int(value.get("mode"), label="%s mode" % kind),
        "nlink": _exact_int(value.get("nlink"), label="%s nlink" % kind, minimum=1),
    }
    if result["uid"] != os.getuid() or result["mode"] != _DIR_MODE:
        raise IdentityError("%s must be current-UID 0700" % kind)
    return result


def _assert_identity(
    live: Mapping[str, Any], expected: Mapping[str, Any], *, label: str
) -> None:
    if any(live[key] != expected[key] for key in expected):
        raise IdentityError("%s identity changed" % label)


def _open_lane(path: Path) -> Tuple[int, Dict[str, Any]]:
    _require_fd_primitives()
    try:
        lexical = os.lstat(path)
    except FileNotFoundError as exc:
        raise ValidationError("admitted lane root does not exist") from exc
    if stat.S_ISLNK(lexical.st_mode):
        raise IdentityError("admitted lane root must not be a symlink")
    try:
        descriptor = os.open(str(path), _DIRECTORY_FLAGS)
    except OSError as exc:
        raise IdentityError("admitted lane root cannot be opened safely") from exc
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != (lexical.st_dev, lexical.st_ino):
            raise IdentityError("admitted lane root changed while opening")
        return descriptor, _directory_identity(
            opened,
            kind="admitted_lane_root",
            path=str(path),
            lane_relative_path=".",
        )
    except Exception:
        os.close(descriptor)
        raise


def _open_descendant(
    lane_descriptor: int,
    *,
    parts: Sequence[str],
    path: Path,
) -> Tuple[int, Dict[str, Any]]:
    current = os.dup(lane_descriptor)
    try:
        for name in parts:
            child = -1
            try:
                lexical = os.stat(name, dir_fd=current, follow_symlinks=False)
                child = os.open(name, _DIRECTORY_FLAGS, dir_fd=current)
                opened = os.fstat(child)
            except OSError as exc:
                if child >= 0:
                    os.close(child)
                raise IdentityError(
                    "workspace root is missing, replaced, or linked"
                ) from exc
            if (
                stat.S_ISLNK(lexical.st_mode)
                or not stat.S_ISDIR(lexical.st_mode)
                or (lexical.st_dev, lexical.st_ino) != (opened.st_dev, opened.st_ino)
            ):
                os.close(child)
                raise IdentityError("workspace root changed while opening")
            os.close(current)
            current = child
        return current, _directory_identity(
            os.fstat(current),
            kind="workspace_root",
            path=str(path),
            lane_relative_path="/".join(parts),
        )
    except Exception:
        os.close(current)
        raise


def _capture_roots(
    *, admitted_lane_root: Path | str, workspace_root: Path | str
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    lane_path = _absolute_lexical(admitted_lane_root, label="admitted lane root")
    workspace_path = _absolute_lexical(workspace_root, label="workspace root")
    workspace_parts = _descendant_parts(
        workspace_path, lane_path, label="workspace root"
    )
    lane_descriptor, lane_identity = _open_lane(lane_path)
    try:
        workspace_descriptor, workspace_identity = _open_descendant(
            lane_descriptor,
            parts=workspace_parts,
            path=workspace_path,
        )
        try:
            if os.listdir(workspace_descriptor):
                raise ConflictError(
                    "workspace root must be an empty Puppet-owned scope"
                )
        finally:
            os.close(workspace_descriptor)
    finally:
        os.close(lane_descriptor)
    return lane_identity, workspace_identity


def _validate_guidance(value: bytes) -> bytes:
    if not isinstance(value, bytes) or not value or len(value) > _MAX_GUIDANCE_BYTES:
        raise ValidationError("guidance bytes are missing or exceed the bound")
    if b"\x00" in value:
        raise ValidationError("guidance bytes contain a NUL")
    try:
        value.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValidationError("guidance bytes must be UTF-8") from exc
    return value


def _normalized_contract_identity(value: Mapping[str, Any]) -> Dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != _CONTRACT_IDENTITY_KEYS:
        raise ValidationError("expected Cursor contract identity is not exact")
    result = {
        "fingerprint": validate_sha256(
            value.get("fingerprint"), "expected Cursor contract fingerprint"
        ),
        "controller": validate_identifier(
            value.get("controller"), "expected Cursor controller"
        ),
        "target": value.get("target"),
        "task_profile": value.get("task_profile"),
    }
    if result["target"] != "cursor" or result["task_profile"] != QUALIFICATION_PROFILE:
        raise IdentityError("expected Cursor contract identity is not canonical Pass B")
    return result


def _normalized_run_identity(value: Mapping[str, Any]) -> Dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != _RUN_IDENTITY_KEYS:
        raise ValidationError("expected Cursor run identity is not exact")
    return {
        "session": validate_identifier(value.get("session"), "expected Cursor session"),
        "run_id": validate_identifier(value.get("run_id"), "expected Cursor run id"),
        "nonce": validate_identifier(value.get("nonce"), "expected Cursor nonce"),
    }


def _identity_sha256(value: Mapping[str, Any]) -> str:
    return sha256_bytes(canonical_json_bytes(dict(value)))


def _mapping_from_canonical_json(value: bytes, *, label: str) -> Dict[str, Any]:
    try:
        decoded = json.loads(value.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise IdentityError("%s storage is invalid" % label) from exc
    if not isinstance(decoded, dict) or canonical_json_bytes(decoded) != value:
        raise IdentityError("%s storage is invalid" % label)
    return decoded


def _exact_cursor_manifest(
    value: AdapterManifest | Mapping[str, Any], *, observed_version: str
) -> AdapterManifest:
    if observed_version != CURSOR_VERSION:
        raise UnsupportedError("Cursor workspace plane version is unsupported")
    manifest = AdapterManifest.from_dict(
        dict(value.raw) if isinstance(value, AdapterManifest) else dict(value)
    )
    raw = manifest.raw
    if raw["target"] != "cursor":
        raise IdentityError("Cursor workspace plane requires a Cursor manifest")
    if raw["platform"].get("system") != "Darwin":
        raise IdentityError("Cursor workspace plane requires the observed Darwin tuple")
    if not raw["doctor_only"] or raw["qualification"] is not None:
        raise IdentityError("Cursor workspace plane requires a doctor-only manifest")
    if any(state != "declared" for state in raw["capabilities"].values()):
        raise IdentityError("Cursor doctor capabilities must remain declared-only")

    executable = raw["executable"]
    version_root = Path(executable["resolved_path"]).parent
    if (
        executable["sha256"] != CURSOR_LAUNCHER_SHA256
        or executable["version_sha256"] != CURSOR_VERSION_OBSERVATION_SHA256
        or executable["help_sha256"] != CURSOR_HELP_SHA256
        or Path(executable["resolved_path"]).name != "cursor-agent"
        or version_root.name != CURSOR_VERSION
    ):
        raise IdentityError("Cursor executable tuple is not the exact supported build")
    execution = raw["execution"]
    support = execution["support_files"]
    if (
        execution["transition"] != "same_pid_exec"
        or execution["runtime_executable"]["path"] != str(version_root / "node")
        or execution["runtime_executable"]["sha256"] != CURSOR_RUNTIME_SHA256
        or len(support) != 1
        or support[0]["path"] != str(version_root / "index.js")
        or support[0]["sha256"] != CURSOR_ENTRYPOINT_SHA256
    ):
        raise IdentityError("Cursor runtime bundle is not the exact supported build")

    mapping = raw["yolo_mapping"]
    if (
        mapping["complete"] is not False
        or mapping["launch_argv"]
        != [
            executable["resolved_path"],
            "--yolo",
            "--sandbox",
            "disabled",
        ]
        or mapping["permission_flags"] != ["--yolo"]
        or mapping["permission_declared"] is not True
        or mapping["sandbox_flags"] != ["--sandbox", "disabled"]
        or mapping["sandbox_disable_declared"] is not True
        or mapping["project_isolation_flags"] != []
        or mapping["project_isolation_declared"] is not False
        or mapping.get("model_flag") != "--model"
    ):
        raise IdentityError("Cursor doctor mapping is not the expected disabled base")
    return manifest


def _bind_current_authority(manifest: AdapterManifest) -> Tuple[str, str]:
    current_adapter = adapter_implementation_fingerprint()
    current_protocol = PROTOCOL_FINGERPRINT
    manifest.verify_execution_files()
    if manifest.raw["adapter_fingerprint"] != current_adapter:
        raise IdentityError("Cursor doctor manifest adapter authority is stale")
    if manifest.raw["protocol_fingerprint"] != current_protocol:
        raise IdentityError("Cursor doctor manifest protocol authority is stale")
    return current_adapter, current_protocol


def _artifact_relative_path(scope_id: str) -> str:
    return ".cursor/rules/puppet-%s.mdc" % scope_id


def _validate_planned_artifact(value: Any, *, scope_id: str) -> Dict[str, Any]:
    keys = {
        "artifact_id",
        "relative_path",
        "write_mode",
        "content_sha256",
        "content_size",
    }
    if not isinstance(value, Mapping) or set(value) != keys:
        raise ValidationError("Cursor planned artifact fields are invalid")
    expected_path = _artifact_relative_path(scope_id)
    if (
        value.get("artifact_id") != "cursor_workspace_guidance"
        or value.get("relative_path") != expected_path
        or value.get("write_mode") != "create_only_if_lifecycle_is_later_proved"
    ):
        raise IdentityError("Cursor planned artifact changed")
    size = _exact_int(value.get("content_size"), label="guidance size", minimum=1)
    if size > _MAX_GUIDANCE_BYTES:
        raise ValidationError("guidance size exceeds the bound")
    return {
        "artifact_id": "cursor_workspace_guidance",
        "relative_path": expected_path,
        "write_mode": "create_only_if_lifecycle_is_later_proved",
        "content_sha256": validate_sha256(
            value.get("content_sha256"), "guidance sha256"
        ),
        "content_size": size,
    }


def _validate_plan(value: Mapping[str, Any]) -> Dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _PLAN_KEYS:
        raise ValidationError("Cursor workspace plan fields are invalid")
    if value.get("schema") != PLAN_SCHEMA or value.get("target") != "cursor":
        raise ValidationError("Cursor workspace plan schema is unsupported")
    if value.get("cursor_version") != CURSOR_VERSION:
        raise UnsupportedError("Cursor workspace plane version is unsupported")
    scope_id = validate_identifier(value.get("scope_id"), "Cursor plane scope")
    if value.get("status") != STATUS:
        raise IdentityError("Cursor workspace plane must remain hypothesis/disabled")
    if value.get("blockers") != list(BLOCKERS):
        raise IdentityError("Cursor workspace plane blockers changed")
    if value.get("launch_authorized") is not False:
        raise UnsupportedError("Cursor workspace plane cannot authorize launch")
    if any(
        value.get(name) is not False
        for name in (
            "materialization_supported",
            "rollback_supported",
            "recovery_supported",
        )
    ):
        raise UnsupportedError("Cursor workspace lifecycle must remain disabled")

    lane = _validate_root(value.get("admitted_lane_root"), kind="admitted_lane_root")
    workspace = _validate_root(value.get("workspace_root"), kind="workspace_root")
    expected_workspace = Path(lane["path"]).joinpath(
        *workspace["lane_relative_path"].split("/")
    )
    if str(expected_workspace) != workspace["path"]:
        raise IdentityError("workspace containment binding changed")
    expected_delta = {"argv": ["--workspace", workspace["path"]]}
    if value.get("launch_delta") != expected_delta:
        raise IdentityError("Cursor workspace launch delta changed")

    result = {
        "schema": PLAN_SCHEMA,
        "target": "cursor",
        "cursor_version": CURSOR_VERSION,
        "scope_id": scope_id,
        "status": dict(STATUS),
        "blockers": list(BLOCKERS),
        "launch_authorized": False,
        "launch_delta": expected_delta,
        "materialization_supported": False,
        "rollback_supported": False,
        "recovery_supported": False,
        "adapter_manifest_sha256": validate_sha256(
            value.get("adapter_manifest_sha256"), "adapter manifest sha256"
        ),
        "adapter_implementation_sha256": validate_sha256(
            value.get("adapter_implementation_sha256"),
            "adapter implementation sha256",
        ),
        "adapter_protocol_sha256": validate_sha256(
            value.get("adapter_protocol_sha256"), "adapter protocol sha256"
        ),
        "execution_fingerprint": validate_sha256(
            value.get("execution_fingerprint"), "execution fingerprint"
        ),
        "admitted_lane_root": lane,
        "workspace_root": workspace,
        "planned_artifact": _validate_planned_artifact(
            value.get("planned_artifact"), scope_id=scope_id
        ),
        "workspace_preimage_sha256": validate_sha256(
            value.get("workspace_preimage_sha256"), "workspace preimage sha256"
        ),
    }
    if result["workspace_preimage_sha256"] != _EMPTY_PREIMAGE_SHA256:
        raise IdentityError("Cursor workspace preimage policy changed")
    supplied_hash = validate_sha256(value.get("plan_sha256"), "plan sha256")
    if supplied_hash != sha256_bytes(canonical_json_bytes(result)):
        raise IdentityError("Cursor workspace plan fingerprint changed")
    result["plan_sha256"] = supplied_hash
    validate_bounded_json(
        result,
        max_depth=8,
        max_items=64,
        max_string=4096,
        reject_sensitive_fields=True,
    )
    return result


@dataclass(frozen=True)
class CursorWorkspacePlan:
    """Typed, body-free, planner-only Cursor workspace record."""

    raw: Dict[str, Any]

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "CursorWorkspacePlan":
        return cls(raw=_validate_plan(value))

    def to_dict(self) -> Dict[str, Any]:
        return json.loads(canonical_json_bytes(self.raw).decode("utf-8"))

    @property
    def plan_sha256(self) -> str:
        return self.raw["plan_sha256"]

    @property
    def planned_artifact_path(self) -> Path:
        return (
            Path(self.raw["workspace_root"]["path"])
            / self.raw["planned_artifact"]["relative_path"]
        )


def plan_cursor_workspace_plane(
    *,
    adapter_manifest: AdapterManifest | Mapping[str, Any],
    expected_manifest_sha256: str,
    expected_adapter_implementation_sha256: str,
    observed_version: str,
    admitted_lane_root: Path | str,
    workspace_root: Path | str,
    scope_id: str,
    guidance: bytes,
) -> CursorWorkspacePlan:
    """Build one current-authority-bound plan without writing or launching."""

    scope_id = validate_identifier(scope_id, "Cursor plane scope")
    guidance = _validate_guidance(guidance)
    manifest = _exact_cursor_manifest(
        adapter_manifest, observed_version=observed_version
    )
    expected_manifest = validate_sha256(
        expected_manifest_sha256, "adapter manifest sha256"
    )
    expected_adapter = validate_sha256(
        expected_adapter_implementation_sha256,
        "adapter implementation sha256",
    )
    if manifest.fingerprint != expected_manifest:
        raise IdentityError("Cursor doctor manifest fingerprint changed")
    if manifest.raw["adapter_fingerprint"] != expected_adapter:
        raise IdentityError("Cursor expected adapter fingerprint changed")
    current_adapter, current_protocol = _bind_current_authority(manifest)
    if expected_adapter != current_adapter:
        raise IdentityError("Cursor expected adapter is not current")

    lane, workspace = _capture_roots(
        admitted_lane_root=admitted_lane_root,
        workspace_root=workspace_root,
    )
    value = {
        "schema": PLAN_SCHEMA,
        "target": "cursor",
        "cursor_version": CURSOR_VERSION,
        "scope_id": scope_id,
        "status": dict(STATUS),
        "blockers": list(BLOCKERS),
        "launch_authorized": False,
        "launch_delta": {"argv": ["--workspace", workspace["path"]]},
        "materialization_supported": False,
        "rollback_supported": False,
        "recovery_supported": False,
        "adapter_manifest_sha256": manifest.fingerprint,
        "adapter_implementation_sha256": current_adapter,
        "adapter_protocol_sha256": current_protocol,
        "execution_fingerprint": manifest.execution_fingerprint,
        "admitted_lane_root": lane,
        "workspace_root": workspace,
        "planned_artifact": {
            "artifact_id": "cursor_workspace_guidance",
            "relative_path": _artifact_relative_path(scope_id),
            "write_mode": "create_only_if_lifecycle_is_later_proved",
            "content_sha256": sha256_bytes(guidance),
            "content_size": len(guidance),
        },
        "workspace_preimage_sha256": _EMPTY_PREIMAGE_SHA256,
    }
    value["plan_sha256"] = sha256_bytes(canonical_json_bytes(value))
    return CursorWorkspacePlan.from_dict(value)


def revalidate_cursor_workspace_plan(
    plan: CursorWorkspacePlan,
    *,
    adapter_manifest: AdapterManifest | Mapping[str, Any],
) -> CursorWorkspacePlan:
    """Read-only rejoin of current authority and the still-empty root."""

    if not isinstance(plan, CursorWorkspacePlan):
        raise ValidationError("Cursor workspace plan is invalid")
    plan = CursorWorkspacePlan.from_dict(plan.to_dict())
    manifest = _exact_cursor_manifest(
        adapter_manifest, observed_version=plan.raw["cursor_version"]
    )
    if manifest.fingerprint != plan.raw["adapter_manifest_sha256"]:
        raise IdentityError("Cursor doctor manifest changed after planning")
    current_adapter, current_protocol = _bind_current_authority(manifest)
    if (
        current_adapter != plan.raw["adapter_implementation_sha256"]
        or current_protocol != plan.raw["adapter_protocol_sha256"]
        or manifest.execution_fingerprint != plan.raw["execution_fingerprint"]
    ):
        raise IdentityError("Cursor current authority changed after planning")
    lane, workspace = _capture_roots(
        admitted_lane_root=plan.raw["admitted_lane_root"]["path"],
        workspace_root=plan.raw["workspace_root"]["path"],
    )
    _assert_identity(lane, plan.raw["admitted_lane_root"], label="admitted lane root")
    _assert_identity(workspace, plan.raw["workspace_root"], label="workspace root")
    return plan


def derive_cursor_workspace_launch_argv(
    plan: CursorWorkspacePlan,
    *,
    adapter_manifest: AdapterManifest | Mapping[str, Any],
) -> Tuple[str, ...]:
    """Derive the exact disabled Cursor vector without granting launch authority."""

    plan = revalidate_cursor_workspace_plan(
        plan,
        adapter_manifest=adapter_manifest,
    )
    manifest = _exact_cursor_manifest(
        adapter_manifest,
        observed_version=plan.raw["cursor_version"],
    )
    base = list(manifest.raw["yolo_mapping"]["launch_argv"])
    delta = list(plan.raw["launch_delta"]["argv"])
    argv = tuple(base + delta)
    workspace = plan.raw["workspace_root"]["path"]
    expected = (
        manifest.raw["executable"]["resolved_path"],
        "--yolo",
        "--sandbox",
        "disabled",
        "--workspace",
        workspace,
    )
    if argv != expected or argv.count("--workspace") != 1:
        raise IdentityError("Cursor workspace launch vector changed")
    if not Path(workspace).is_absolute() or workspace != str(
        Path(workspace).absolute()
    ):
        raise IdentityError("Cursor workspace launch vector is not absolute")
    forbidden = {
        "--add-dir",
        "--api-key",
        "--append-system-prompt",
        "--config",
        "--continue",
        "--model",
        "--profile",
        "--rules",
        "--system-prompt",
        "--system-prompt-file",
        "--worktree",
        "--worktree-base",
    }
    if any(item in forbidden for item in argv):
        raise IdentityError("Cursor workspace launch vector gained a forbidden flag")
    return argv


def _validate_binding_record(value: Mapping[str, Any]) -> Dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _BINDING_KEYS:
        raise IdentityError("Cursor workspace binding fields changed")
    result = json.loads(canonical_json_bytes(dict(value)).decode("utf-8"))
    if (
        result["schema"] != BINDING_SCHEMA
        or result["state"] != BINDING_STATE
        or result["target"] != "cursor"
        or result["target_version"] != CURSOR_VERSION
        or result["plane"] != "workspace_addendum"
        or result["descriptor_id"] != CURSOR_WORKSPACE_DESCRIPTOR_ID
    ):
        raise IdentityError("Cursor workspace binding tuple changed")
    for name in _BINDING_HASH_KEYS:
        validate_sha256(result.get(name), name.replace("_", " "))
    size = _exact_int(
        result.get("effective_contract_bytes"),
        label="Cursor effective contract bytes",
        minimum=1,
    )
    if size > _MAX_GUIDANCE_BYTES:
        raise ValidationError("Cursor effective contract exceeds the bound")
    artifact = result.get("artifact")
    if not isinstance(artifact, Mapping) or set(artifact) != {
        "artifact_id",
        "root_ref",
        "relative_path",
        "content_ref",
        "write_mode",
    }:
        raise IdentityError("Cursor workspace binding artifact changed")
    if artifact != {
        "artifact_id": "cursor_workspace_rule",
        "root_ref": "workspace_root",
        "relative_path": (
            ".cursor/rules/puppet-%s.mdc" % result["effective_contract_sha256"]
        ),
        "content_ref": CURSOR_MDC_ALWAYS_APPLY_CONTENT_REF,
        "write_mode": "create_only",
    }:
        raise IdentityError("Cursor workspace binding artifact changed")
    if (
        result["requested_model"] != "default"
        or result["observed_model"] != "unavailable"
        or result["config_fingerprint"] != "unavailable"
        or any(
            result[name] is not False
            for name in (
                "activation_authorized",
                "launch_authorized",
                "qualification_authorized",
            )
        )
    ):
        raise IdentityError("Cursor workspace binding gained authority")
    validate_bounded_json(
        result,
        max_depth=5,
        max_items=64,
        max_string=512,
        reject_sensitive_fields=True,
    )
    return result


def _derive_cursor_workspace_binding_record(
    *,
    descriptor: Mapping[str, Any],
    instruction_manifest: Mapping[str, Any],
    effective_contract: bytes,
    adapter_manifest: AdapterManifest | Mapping[str, Any],
    admitted_lane_root: Path | str,
    workspace_root: Path | str,
    expected_contract_identity: Mapping[str, Any],
    expected_workspace_identity: Mapping[str, Any],
    expected_run_identity: Mapping[str, Any],
) -> Dict[str, Any]:
    normalized_descriptor = validate_cursor_workspace_addendum_descriptor(descriptor)
    normalized_instruction = validate_instruction_manifest(
        instruction_manifest,
        target="cursor",
    )
    contract_bytes = _validate_guidance(effective_contract)
    rendered_sha = sha256_bytes(contract_bytes)
    if normalized_instruction[
        "rendered_sha256"
    ] != rendered_sha or normalized_instruction["byte_count"] != len(contract_bytes):
        raise IdentityError(
            "Cursor effective contract does not match its instruction manifest"
        )
    if normalized_instruction["runtime_binding"] != {
        "model": "default",
        "effort": "default",
    }:
        raise IdentityError("Cursor workspace binding requires current defaults")

    contract_identity = _normalized_contract_identity(expected_contract_identity)
    run_identity = _normalized_run_identity(expected_run_identity)
    workspace_identity = _validate_root(
        expected_workspace_identity,
        kind="workspace_root",
    )
    if normalized_instruction["contract_identity"] != contract_identity:
        raise IdentityError("Cursor instruction contract identity changed")
    if normalized_instruction["run_identity"] != run_identity:
        raise IdentityError("Cursor instruction run identity changed")
    if normalized_instruction["workspace_identity"] != workspace_identity:
        raise IdentityError("Cursor instruction workspace identity changed")

    manifest = _exact_cursor_manifest(
        adapter_manifest,
        observed_version=CURSOR_VERSION,
    )
    target = normalized_descriptor["target"]
    if (
        target["adapter_manifest_sha256"] != manifest.fingerprint
        or target["version"] != CURSOR_VERSION
        or target["requested_model"] != "default"
        or target["observed_model"] != "unavailable"
        or target["config_fingerprint"] != "unavailable"
    ):
        raise IdentityError("Cursor workspace descriptor target tuple changed")
    artifact = normalized_descriptor["materialize"][0]
    expected_relative_path = ".cursor/rules/puppet-%s.mdc" % rendered_sha
    if artifact["relative_path"] != expected_relative_path:
        raise IdentityError(
            "Cursor workspace rule filename does not match the effective contract"
        )
    expected_launch_delta = {
        "cwd_ref": "workspace_root",
        "env": [],
        "argv": [
            {"literal": "--workspace"},
            {"root_ref": "workspace_root"},
        ],
    }
    if normalized_descriptor["launch_delta"] != expected_launch_delta:
        raise IdentityError("Cursor workspace descriptor launch delta changed")

    plan = plan_cursor_workspace_plane(
        adapter_manifest=manifest,
        expected_manifest_sha256=manifest.fingerprint,
        expected_adapter_implementation_sha256=manifest.raw["adapter_fingerprint"],
        observed_version=CURSOR_VERSION,
        admitted_lane_root=admitted_lane_root,
        workspace_root=workspace_root,
        scope_id=rendered_sha,
        guidance=contract_bytes,
    )
    if plan.raw["workspace_root"] != workspace_identity:
        raise IdentityError("Cursor workspace binding root changed")
    if (
        plan.raw["planned_artifact"]["relative_path"] != expected_relative_path
        or plan.raw["planned_artifact"]["content_sha256"] != rendered_sha
        or plan.raw["planned_artifact"]["content_size"] != len(contract_bytes)
        or plan.raw["launch_delta"]
        != {"argv": ["--workspace", workspace_identity["path"]]}
    ):
        raise IdentityError("Cursor workspace plan join changed")
    launch_argv = derive_cursor_workspace_launch_argv(
        plan,
        adapter_manifest=manifest,
    )

    record: Dict[str, Any] = {
        "schema": BINDING_SCHEMA,
        "state": BINDING_STATE,
        "target": "cursor",
        "target_version": CURSOR_VERSION,
        "plane": "workspace_addendum",
        "descriptor_id": normalized_descriptor["descriptor_id"],
        "descriptor_sha256": descriptor_fingerprint(normalized_descriptor),
        "instruction_manifest_sha256": sha256_bytes(
            canonical_json_bytes(normalized_instruction) + b"\n"
        ),
        "instruction_policy_fingerprint": normalized_instruction[
            "instruction_policy_fingerprint"
        ],
        "effective_contract_fingerprint": normalized_instruction[
            "effective_contract_fingerprint"
        ],
        "effective_contract_sha256": rendered_sha,
        "effective_contract_bytes": len(contract_bytes),
        "contract_identity_sha256": _identity_sha256(contract_identity),
        "workspace_identity_sha256": _identity_sha256(workspace_identity),
        "run_identity_sha256": _identity_sha256(run_identity),
        "adapter_manifest_sha256": manifest.fingerprint,
        "adapter_implementation_sha256": plan.raw["adapter_implementation_sha256"],
        "adapter_protocol_sha256": plan.raw["adapter_protocol_sha256"],
        "adapter_execution_sha256": plan.raw["execution_fingerprint"],
        "workspace_plan_sha256": plan.plan_sha256,
        "launch_delta_sha256": sha256_bytes(
            canonical_json_bytes(normalized_descriptor["launch_delta"])
        ),
        "launch_argv_sha256": sha256_bytes(canonical_json_bytes(list(launch_argv))),
        "requested_model": "default",
        "observed_model": "unavailable",
        "config_fingerprint": "unavailable",
        "artifact": {
            "artifact_id": artifact["artifact_id"],
            "root_ref": artifact["root_ref"],
            "relative_path": artifact["relative_path"],
            "content_ref": artifact["content_ref"],
            "write_mode": artifact["write_mode"],
        },
        "activation_authorized": False,
        "launch_authorized": False,
        "qualification_authorized": False,
    }
    encoded = canonical_json_bytes(record)
    if contract_bytes in encoded:
        raise IdentityError("Cursor workspace binding contains instruction bytes")
    return _validate_binding_record(record)


class CursorWorkspacePlaneBinding:
    """Immutable, body-free source join with lifecycle authority fixed false."""

    __slots__ = (
        "__adapter_manifest_json",
        "__admitted_lane_root",
        "__descriptor_json",
        "__effective_contract",
        "__expected_contract_identity_json",
        "__expected_record_sha256",
        "__expected_run_identity_json",
        "__expected_workspace_identity_json",
        "__instruction_manifest_json",
        "__workspace_root",
    )

    def __init__(
        self,
        *,
        descriptor: Mapping[str, Any],
        instruction_manifest: Mapping[str, Any],
        effective_contract: bytes,
        adapter_manifest: AdapterManifest | Mapping[str, Any],
        admitted_lane_root: Path | str,
        workspace_root: Path | str,
        expected_contract_identity: Mapping[str, Any],
        expected_workspace_identity: Mapping[str, Any],
        expected_run_identity: Mapping[str, Any],
    ) -> None:
        record = _derive_cursor_workspace_binding_record(
            descriptor=descriptor,
            instruction_manifest=instruction_manifest,
            effective_contract=effective_contract,
            adapter_manifest=adapter_manifest,
            admitted_lane_root=admitted_lane_root,
            workspace_root=workspace_root,
            expected_contract_identity=expected_contract_identity,
            expected_workspace_identity=expected_workspace_identity,
            expected_run_identity=expected_run_identity,
        )
        manifest = AdapterManifest.from_dict(
            dict(adapter_manifest.raw)
            if isinstance(adapter_manifest, AdapterManifest)
            else dict(adapter_manifest)
        )
        values = {
            "adapter_manifest_json": canonical_json_bytes(manifest.raw),
            "admitted_lane_root": Path(admitted_lane_root),
            "descriptor_json": canonical_json_bytes(dict(descriptor)),
            "effective_contract": bytes(effective_contract),
            "expected_contract_identity_json": canonical_json_bytes(
                dict(expected_contract_identity)
            ),
            "expected_record_sha256": sha256_bytes(canonical_json_bytes(record)),
            "expected_run_identity_json": canonical_json_bytes(
                dict(expected_run_identity)
            ),
            "expected_workspace_identity_json": canonical_json_bytes(
                dict(expected_workspace_identity)
            ),
            "instruction_manifest_json": canonical_json_bytes(
                dict(instruction_manifest)
            ),
            "workspace_root": Path(workspace_root),
        }
        for name, stored in values.items():
            object.__setattr__(
                self,
                "_CursorWorkspacePlaneBinding__%s" % name,
                stored,
            )

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("Cursor workspace bindings are immutable")

    def __repr__(self) -> str:
        return "CursorWorkspacePlaneBinding(state='binding_only')"

    @property
    def record(self) -> Dict[str, Any]:
        record = _derive_cursor_workspace_binding_record(
            descriptor=_mapping_from_canonical_json(
                self.__descriptor_json,
                label="Cursor workspace descriptor",
            ),
            instruction_manifest=_mapping_from_canonical_json(
                self.__instruction_manifest_json,
                label="Cursor instruction manifest",
            ),
            effective_contract=self.__effective_contract,
            adapter_manifest=_mapping_from_canonical_json(
                self.__adapter_manifest_json,
                label="Cursor adapter manifest",
            ),
            admitted_lane_root=self.__admitted_lane_root,
            workspace_root=self.__workspace_root,
            expected_contract_identity=_mapping_from_canonical_json(
                self.__expected_contract_identity_json,
                label="expected Cursor contract identity",
            ),
            expected_workspace_identity=_mapping_from_canonical_json(
                self.__expected_workspace_identity_json,
                label="expected Cursor workspace identity",
            ),
            expected_run_identity=_mapping_from_canonical_json(
                self.__expected_run_identity_json,
                label="expected Cursor run identity",
            ),
        )
        if sha256_bytes(canonical_json_bytes(record)) != self.__expected_record_sha256:
            raise IdentityError("Cursor workspace binding changed after binding")
        return record

    def to_public_dict(self) -> Dict[str, Any]:
        return self.record


def bind_cursor_workspace_plane(
    *,
    descriptor: Mapping[str, Any],
    instruction_manifest: Mapping[str, Any],
    effective_contract: bytes,
    adapter_manifest: AdapterManifest | Mapping[str, Any],
    admitted_lane_root: Path | str,
    workspace_root: Path | str,
    expected_contract_identity: Mapping[str, Any],
    expected_workspace_identity: Mapping[str, Any],
    expected_run_identity: Mapping[str, Any],
) -> CursorWorkspacePlaneBinding:
    """Bind Cursor compiler output to the exact disabled workspace plan."""

    return CursorWorkspacePlaneBinding(
        descriptor=descriptor,
        instruction_manifest=instruction_manifest,
        effective_contract=effective_contract,
        adapter_manifest=adapter_manifest,
        admitted_lane_root=admitted_lane_root,
        workspace_root=workspace_root,
        expected_contract_identity=expected_contract_identity,
        expected_workspace_identity=expected_workspace_identity,
        expected_run_identity=expected_run_identity,
    )


def _disabled_lifecycle(plan: Any) -> NoReturn:
    if isinstance(plan, CursorWorkspacePlan):
        CursorWorkspacePlan.from_dict(plan.to_dict())
    raise UnsupportedError(_LIFECYCLE_DISABLED)


def materialize_cursor_workspace_plane(
    plan: CursorWorkspacePlan,
    *,
    guidance: Optional[bytes] = None,
    adapter_manifest: Optional[AdapterManifest | Mapping[str, Any]] = None,
) -> NoReturn:
    """Remain disabled; planning is not filesystem mutation authority."""

    del guidance, adapter_manifest
    _disabled_lifecycle(plan)


def verify_cursor_workspace_plane(
    plan: CursorWorkspacePlan,
    *,
    receipt: Optional[Mapping[str, Any]] = None,
    adapter_manifest: Optional[AdapterManifest | Mapping[str, Any]] = None,
) -> NoReturn:
    """Remain disabled because no materialization receipt can be authoritative."""

    del receipt, adapter_manifest
    _disabled_lifecycle(plan)


def rollback_cursor_workspace_plane(
    plan: CursorWorkspacePlan,
    receipt: Optional[Mapping[str, Any]] = None,
    *,
    exact_halt_proof: Optional[Mapping[str, Any]] = None,
    adapter_manifest: Optional[AdapterManifest | Mapping[str, Any]] = None,
) -> NoReturn:
    """Reject every cleanup request; no self-mintable halt assertion exists."""

    del receipt, exact_halt_proof, adapter_manifest
    _disabled_lifecycle(plan)


def recover_cursor_workspace_plane(
    plan: CursorWorkspacePlan,
    *,
    rollback_record: Optional[Mapping[str, Any]] = None,
    adapter_manifest: Optional[AdapterManifest | Mapping[str, Any]] = None,
) -> NoReturn:
    """Reject terminal-state claims, including canonical forged records."""

    del rollback_record, adapter_manifest
    _disabled_lifecycle(plan)
