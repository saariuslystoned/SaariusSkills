"""Planner-only Cursor workspace instruction-plane substrate.

The exact installed Cursor tuple exposes a plausible workspace guidance
surface, but Puppet has not proved activation, no-bleed behavior, isolated
authentication, default-model resolution, or a race-safe rollback primitive.
This module therefore plans and revalidates only.  It never creates guidance,
launches Cursor, mints halt authority, or removes filesystem objects.

The sole public artifact is a body-free plan.  Private guidance bytes are
accepted only to bind their size and digest into that plan; they are never
returned or persisted here.
"""

from __future__ import annotations

import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, NoReturn, Optional, Sequence, Tuple

from .adapter_manifest import AdapterManifest
from .census import adapter_implementation_fingerprint
from .errors import ConflictError, IdentityError, UnsupportedError, ValidationError
from .handoffs import PROTOCOL_FINGERPRINT
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
STATUS = {"surface": "hypothesis", "activation": "disabled"}
BLOCKERS = (
    "cursor_auth_isolation_unproved",
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
