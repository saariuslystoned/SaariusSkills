"""Source-only binding for AGY's disabled workspace custom-agent candidate.

The installed AGY tuple documents workspace custom agents, but Puppet has not
proved config isolation, sandbox-off behavior, activation, no-bleed, or the
default model.  This module therefore joins compiler output to the exact
doctor manifest and reserved descriptor without writing files or granting any
runtime authority.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Any, Dict, Mapping, Sequence, Tuple

from .adapter_manifest import AdapterManifest, QUALIFICATION_PROFILE
from .agy_launch import AGY_REGULAR_AUTHORITY_BLOCKERS, agy_regular_verdict
from .census import adapter_implementation_fingerprint
from .errors import IdentityError, UnsupportedError, ValidationError
from .handoffs import PROTOCOL_FINGERPRINT
from .instruction_planes import (
    AGY_WORKSPACE_ARTIFACT_ID,
    AGY_WORKSPACE_BLOCKERS,
    AGY_WORKSPACE_DESCRIPTOR_ID,
    descriptor_fingerprint,
    validate_agy_workspace_agent_descriptor,
)
from .instructions import validate_instruction_manifest
from .profiles import (
    PROMPT_TRANSPORT,
    SUBMIT_SETTLE_SECONDS,
    session_profiles_for,
    startup_settle_seconds_for,
)
from .safety import (
    canonical_json_bytes,
    sha256_bytes,
    validate_bounded_json,
    validate_identifier,
    validate_sha256,
)


AGY_VERSION = "1.1.5"
AGY_EXECUTABLE_SHA256 = (
    "6509d6ca54a66e3eaf61dfe35308ba1dfa1e6b552ef5c4f5f861562c6811ecaf"
)
AGY_VERSION_OBSERVATION_SHA256 = (
    "1c60df040a80b6d2e3f56442b17d127d8620cd773873e6e1353362f989b1deca"
)
AGY_HELP_SHA256 = "b208f7290114292858a1944ac90349bcd1f75168eb85c76ac40c8208cea342f5"

BINDING_SCHEMA = "puppet.agy-workspace-plane-binding/v1"
BINDING_STATE = "binding_only"
_MAX_CONTRACT_BYTES = 65536
_CONTRACT_IDENTITY_KEYS = {
    "fingerprint",
    "controller",
    "target",
    "task_profile",
}
_RUN_IDENTITY_KEYS = {"session", "run_id", "nonce"}
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
_DIR_MODE = 0o700
_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_CLOEXEC = getattr(os, "O_CLOEXEC", 0)
_DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | _NOFOLLOW | _CLOEXEC
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
    "admitted_lane_identity_sha256",
    "workspace_identity_sha256",
    "run_identity_sha256",
    "adapter_manifest_sha256",
    "adapter_implementation_sha256",
    "adapter_protocol_sha256",
    "adapter_execution_sha256",
    "regular_verdict_sha256",
    "launch_delta_sha256",
    "selector_name",
    "requested_model",
    "observed_model",
    "config_fingerprint",
    "artifact",
    "blockers",
    "materialization_authorized",
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


def _validate_contract_bytes(value: bytes) -> bytes:
    if not isinstance(value, bytes) or not value or len(value) > _MAX_CONTRACT_BYTES:
        raise ValidationError("AGY effective contract bytes are missing or oversized")
    if b"\x00" in value:
        raise ValidationError("AGY effective contract contains a NUL")
    try:
        value.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValidationError("AGY effective contract must be UTF-8") from exc
    return value


def _contract_identity(value: Mapping[str, Any]) -> Dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != _CONTRACT_IDENTITY_KEYS:
        raise ValidationError("expected AGY contract identity is not exact")
    result = {
        "fingerprint": validate_sha256(
            value.get("fingerprint"), "expected AGY contract fingerprint"
        ),
        "controller": validate_identifier(
            value.get("controller"), "expected AGY controller"
        ),
        "target": value.get("target"),
        "task_profile": value.get("task_profile"),
    }
    if result["target"] != "agy" or result["task_profile"] != QUALIFICATION_PROFILE:
        raise IdentityError("expected AGY contract identity is not canonical Pass B")
    return result


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
        or os.path.normpath(raw) != raw
    ):
        raise ValidationError("%s must be a normalized absolute path" % label)
    return Path(raw)


def _descendant_parts(path: Path, lane: Path) -> Tuple[str, ...]:
    try:
        parts = path.relative_to(lane).parts
    except ValueError as exc:
        raise ValidationError(
            "AGY workspace must be beneath the admitted lane"
        ) from exc
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise ValidationError("AGY workspace has an invalid lane-relative path")
    return tuple(parts)


def _directory_identity(
    details: os.stat_result,
    *,
    kind: str,
    path: str,
    lane_relative_path: str,
) -> Dict[str, Any]:
    if not stat.S_ISDIR(details.st_mode):
        raise IdentityError("AGY bound root is not a directory")
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
        raise ValidationError("expected AGY %s identity is not exact" % kind)
    if value.get("kind") != kind:
        raise ValidationError("expected AGY %s kind changed" % kind)
    path = _absolute_lexical(value.get("path"), label=kind)
    relative = value.get("lane_relative_path")
    if kind == "admitted_lane_root":
        if relative != ".":
            raise ValidationError("AGY lane relative path changed")
    elif (
        not isinstance(relative, str)
        or not relative
        or relative.startswith("/")
        or "\\" in relative
        or any(part in {"", ".", ".."} for part in relative.split("/"))
    ):
        raise ValidationError("AGY workspace relative path changed")
    result = {
        "kind": kind,
        "path": str(path),
        "lane_relative_path": relative,
        "device": _exact_int(value.get("device"), label="AGY root device"),
        "inode": _exact_int(value.get("inode"), label="AGY root inode", minimum=1),
        "uid": _exact_int(value.get("uid"), label="AGY root uid"),
        "gid": _exact_int(value.get("gid"), label="AGY root gid"),
        "mode": _exact_int(value.get("mode"), label="AGY root mode"),
        "nlink": _exact_int(value.get("nlink"), label="AGY root nlink", minimum=1),
    }
    if result["uid"] != os.getuid() or result["mode"] != _DIR_MODE:
        raise IdentityError("%s must be current-UID 0700" % kind)
    return result


def _require_fd_primitives() -> None:
    if not _NOFOLLOW or os.stat not in os.supports_dir_fd:
        raise UnsupportedError(
            "AGY workspace binding requires no-follow dir-FD support"
        )


def _open_lane(path: Path) -> Tuple[int, Dict[str, Any]]:
    _require_fd_primitives()
    try:
        lexical = os.lstat(path)
    except OSError as exc:
        raise IdentityError("AGY admitted lane is unavailable") from exc
    if stat.S_ISLNK(lexical.st_mode):
        raise IdentityError("AGY admitted lane must not be a symlink")
    descriptor = -1
    try:
        descriptor = os.open(str(path), _DIRECTORY_FLAGS)
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != (lexical.st_dev, lexical.st_ino):
            raise IdentityError("AGY admitted lane changed while opening")
        return descriptor, _directory_identity(
            opened,
            kind="admitted_lane_root",
            path=str(path),
            lane_relative_path=".",
        )
    except Exception:
        if descriptor >= 0:
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
                    "AGY workspace is missing, replaced, or linked"
                ) from exc
            if (
                stat.S_ISLNK(lexical.st_mode)
                or not stat.S_ISDIR(lexical.st_mode)
                or (lexical.st_dev, lexical.st_ino) != (opened.st_dev, opened.st_ino)
            ):
                os.close(child)
                raise IdentityError("AGY workspace changed while opening")
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
    parts = _descendant_parts(workspace_path, lane_path)
    lane_descriptor, lane_identity = _open_lane(lane_path)
    try:
        workspace_descriptor, workspace_identity = _open_descendant(
            lane_descriptor,
            parts=parts,
            path=workspace_path,
        )
        os.close(workspace_descriptor)
    finally:
        os.close(lane_descriptor)
    return lane_identity, workspace_identity


def capture_agy_workspace_identity(
    *, admitted_lane_root: Path | str, workspace_root: Path | str
) -> Dict[str, Any]:
    """Capture the strict source identity used by the compiler and binder."""

    _, workspace = _capture_roots(
        admitted_lane_root=admitted_lane_root,
        workspace_root=workspace_root,
    )
    return workspace


def _run_identity(value: Mapping[str, Any]) -> Dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != _RUN_IDENTITY_KEYS:
        raise ValidationError("expected AGY run identity is not exact")
    return {
        "session": validate_identifier(value.get("session"), "expected AGY session"),
        "run_id": validate_identifier(value.get("run_id"), "expected AGY run id"),
        "nonce": validate_identifier(value.get("nonce"), "expected AGY nonce"),
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


def _exact_agy_manifest(value: AdapterManifest | Mapping[str, Any]) -> AdapterManifest:
    manifest = AdapterManifest.from_dict(
        dict(value.raw) if isinstance(value, AdapterManifest) else dict(value)
    )
    raw = manifest.raw
    if raw["target"] != "agy":
        raise IdentityError("AGY workspace plane requires an AGY manifest")
    if raw["platform"].get("system") != "Darwin":
        raise IdentityError("AGY workspace plane requires the observed Darwin tuple")
    if not raw["doctor_only"] or raw["qualification"] is not None:
        raise IdentityError("AGY workspace plane requires a doctor-only manifest")
    if any(state != "declared" for state in raw["capabilities"].values()):
        raise IdentityError("AGY doctor capabilities must remain declared-only")

    executable = raw["executable"]
    if (
        executable["sha256"] != AGY_EXECUTABLE_SHA256
        or executable["version_sha256"] != AGY_VERSION_OBSERVATION_SHA256
        or executable["help_sha256"] != AGY_HELP_SHA256
        or executable["resolved_path"].rsplit("/", 1)[-1] != "agy"
    ):
        raise IdentityError("AGY executable tuple is not the exact supported build")
    execution = raw["execution"]
    runtime = execution["runtime_executable"]
    if (
        execution["transition"] != "direct"
        or runtime["path"] != executable["resolved_path"]
        or runtime["sha256"] != executable["sha256"]
        or execution["transient_executables"]
        or execution["support_files"]
    ):
        raise IdentityError("AGY execution tuple is not direct and exact")

    mapping = raw["yolo_mapping"]
    expected_argv = [
        executable["resolved_path"],
        "--dangerously-skip-permissions",
        "--sandbox=false",
        "--new-project",
        "--log-file",
        "/dev/null",
    ]
    if (
        mapping["complete"] is not True
        or mapping["launch_argv"] != expected_argv
        or mapping["permission_declared"] is not True
        or mapping["permission_flags"] != ["--dangerously-skip-permissions"]
        or mapping["sandbox_disable_declared"] is not True
        or mapping["sandbox_flags"] != ["--sandbox=false"]
        or mapping["project_isolation_declared"] is not True
        or mapping["project_isolation_flags"] != ["--new-project"]
        or mapping["prompt_transport"] != PROMPT_TRANSPORT
        or mapping["prompt_transport_declared"] is not True
        or mapping["session_profiles"] != session_profiles_for("agy")
        or mapping["session_profiles_declared"] is not True
        or mapping["startup_settle_seconds"] != startup_settle_seconds_for("agy")
        or mapping["submit_settle_seconds"] != SUBMIT_SETTLE_SECONDS
        or mapping.get("model_flag") != "--model"
        or mapping.get("effort_flag") != "--effort"
    ):
        raise IdentityError("AGY doctor mapping is not the expected parser-proved base")
    return manifest


def _bind_current_authority(manifest: AdapterManifest) -> tuple[str, str]:
    current_adapter = adapter_implementation_fingerprint()
    current_protocol = PROTOCOL_FINGERPRINT
    manifest.verify_execution_files()
    if manifest.raw["adapter_fingerprint"] != current_adapter:
        raise IdentityError("AGY doctor manifest adapter authority is stale")
    if manifest.raw["protocol_fingerprint"] != current_protocol:
        raise IdentityError("AGY doctor manifest protocol authority is stale")
    return current_adapter, current_protocol


def _validate_binding_record(value: Mapping[str, Any]) -> Dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _BINDING_KEYS:
        raise IdentityError("AGY workspace binding fields changed")
    result = json.loads(canonical_json_bytes(dict(value)).decode("utf-8"))
    if (
        result["schema"] != BINDING_SCHEMA
        or result["state"] != BINDING_STATE
        or result["target"] != "agy"
        or result["target_version"] != AGY_VERSION
        or result["plane"] != "workspace_addendum"
        or result["descriptor_id"] != AGY_WORKSPACE_DESCRIPTOR_ID
    ):
        raise IdentityError("AGY workspace binding tuple changed")
    for name in _BINDING_HASH_KEYS:
        validate_sha256(result.get(name), name.replace("_", " "))
    size = result.get("effective_contract_bytes")
    if (
        isinstance(size, bool)
        or not isinstance(size, int)
        or size < 1
        or size > _MAX_CONTRACT_BYTES
    ):
        raise ValidationError("AGY effective contract byte count is invalid")
    expected_selector = "puppet-%s" % result["effective_contract_sha256"]
    expected_artifact = {
        "artifact_id": AGY_WORKSPACE_ARTIFACT_ID,
        "root_ref": "workspace_root",
        "relative_path": ".agents/agents/%s/agent.md" % expected_selector,
        "content_ref": "effective_contract",
        "write_mode": "create_only",
    }
    if result.get("selector_name") != expected_selector:
        raise IdentityError("AGY workspace selector changed")
    if result.get("artifact") != expected_artifact:
        raise IdentityError("AGY workspace binding artifact changed")
    if result.get("blockers") != sorted(AGY_WORKSPACE_BLOCKERS):
        raise IdentityError("AGY workspace binding blockers changed")
    if (
        result["requested_model"] != "default"
        or result["observed_model"] != "unavailable"
        or result["config_fingerprint"] != "unavailable"
        or any(
            result[name] is not False
            for name in (
                "materialization_authorized",
                "activation_authorized",
                "launch_authorized",
                "qualification_authorized",
            )
        )
    ):
        raise IdentityError("AGY workspace binding gained authority")
    validate_bounded_json(
        result,
        max_depth=5,
        max_items=64,
        max_string=512,
        reject_sensitive_fields=True,
    )
    return result


def _derive_agy_workspace_binding_record(
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
    normalized_descriptor = validate_agy_workspace_agent_descriptor(descriptor)
    normalized_instruction = validate_instruction_manifest(
        instruction_manifest,
        target="agy",
    )
    contract_bytes = _validate_contract_bytes(effective_contract)
    rendered_sha = sha256_bytes(contract_bytes)
    if normalized_instruction[
        "rendered_sha256"
    ] != rendered_sha or normalized_instruction["byte_count"] != len(contract_bytes):
        raise IdentityError("AGY effective contract does not match its manifest")
    if normalized_instruction["runtime_binding"] != {
        "model": "default",
        "effort": "default",
    }:
        raise IdentityError("AGY workspace binding requires current defaults")

    contract_identity = _contract_identity(expected_contract_identity)
    expected_workspace = _validate_root(
        expected_workspace_identity,
        kind="workspace_root",
    )
    run_identity = _run_identity(expected_run_identity)
    if normalized_instruction["contract_identity"] != contract_identity:
        raise IdentityError("AGY instruction contract identity changed")
    if normalized_instruction["workspace_identity"] != expected_workspace:
        raise IdentityError("AGY instruction workspace identity changed")
    if normalized_instruction["run_identity"] != run_identity:
        raise IdentityError("AGY instruction run identity changed")

    manifest = _exact_agy_manifest(adapter_manifest)
    current_adapter, current_protocol = _bind_current_authority(manifest)
    lane_identity, workspace_identity = _capture_roots(
        admitted_lane_root=admitted_lane_root,
        workspace_root=workspace_root,
    )
    if workspace_identity != expected_workspace:
        raise IdentityError("AGY workspace root identity changed")
    target = normalized_descriptor["target"]
    if (
        target["adapter_manifest_sha256"] != manifest.fingerprint
        or target["version"] != AGY_VERSION
        or target["requested_model"] != "default"
        or target["observed_model"] != "unavailable"
        or target["config_fingerprint"] != "unavailable"
    ):
        raise IdentityError("AGY workspace descriptor target tuple changed")
    artifact = normalized_descriptor["materialize"][0]
    selector_name = "puppet-%s" % rendered_sha
    expected_path = ".agents/agents/%s/agent.md" % selector_name
    if artifact["relative_path"] != expected_path:
        raise IdentityError("AGY workspace artifact is not contract-hash named")
    expected_delta = {
        "cwd_ref": "workspace_root",
        "env": [],
        "argv": [
            {"literal": "--agent"},
            {"name_ref": "puppet_agent_name"},
        ],
    }
    if normalized_descriptor["launch_delta"] != expected_delta:
        raise IdentityError("AGY workspace descriptor launch delta changed")
    verdict = agy_regular_verdict()
    if (
        verdict.get("target") != "agy"
        or verdict.get("session_profile") != "regular"
        or verdict.get("status") != "shared_vendor_auth_config_route"
        or verdict.get("launch_authorized") is not True
        or verdict.get("qualification_authorized") is not False
        or tuple(verdict.get("blockers", ())) != AGY_REGULAR_AUTHORITY_BLOCKERS
    ):
        raise IdentityError("AGY regular authority fence changed")

    record: Dict[str, Any] = {
        "schema": BINDING_SCHEMA,
        "state": BINDING_STATE,
        "target": "agy",
        "target_version": AGY_VERSION,
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
        "admitted_lane_identity_sha256": _identity_sha256(lane_identity),
        "workspace_identity_sha256": _identity_sha256(workspace_identity),
        "run_identity_sha256": _identity_sha256(run_identity),
        "adapter_manifest_sha256": manifest.fingerprint,
        "adapter_implementation_sha256": current_adapter,
        "adapter_protocol_sha256": current_protocol,
        "adapter_execution_sha256": manifest.execution_fingerprint,
        "regular_verdict_sha256": sha256_bytes(canonical_json_bytes(verdict)),
        "launch_delta_sha256": sha256_bytes(canonical_json_bytes(expected_delta)),
        "selector_name": selector_name,
        "requested_model": "default",
        "observed_model": "unavailable",
        "config_fingerprint": "unavailable",
        "artifact": dict(artifact),
        "blockers": sorted(AGY_WORKSPACE_BLOCKERS),
        "materialization_authorized": False,
        "activation_authorized": False,
        "launch_authorized": False,
        "qualification_authorized": False,
    }
    encoded = canonical_json_bytes(record)
    if contract_bytes in encoded:
        raise IdentityError("AGY workspace binding contains instruction bytes")
    return _validate_binding_record(record)


class AgyWorkspacePlaneBinding:
    """Immutable body-free join whose runtime authority stays fixed false."""

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
        record = _derive_agy_workspace_binding_record(
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
            object.__setattr__(self, "_AgyWorkspacePlaneBinding__%s" % name, stored)

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("AGY workspace bindings are immutable")

    def __repr__(self) -> str:
        return "AgyWorkspacePlaneBinding(state='binding_only')"

    @property
    def record(self) -> Dict[str, Any]:
        record = _derive_agy_workspace_binding_record(
            descriptor=_mapping_from_canonical_json(
                self.__descriptor_json,
                label="AGY workspace descriptor",
            ),
            instruction_manifest=_mapping_from_canonical_json(
                self.__instruction_manifest_json,
                label="AGY instruction manifest",
            ),
            effective_contract=self.__effective_contract,
            adapter_manifest=_mapping_from_canonical_json(
                self.__adapter_manifest_json,
                label="AGY adapter manifest",
            ),
            admitted_lane_root=self.__admitted_lane_root,
            workspace_root=self.__workspace_root,
            expected_contract_identity=_mapping_from_canonical_json(
                self.__expected_contract_identity_json,
                label="expected AGY contract identity",
            ),
            expected_workspace_identity=_mapping_from_canonical_json(
                self.__expected_workspace_identity_json,
                label="expected AGY workspace identity",
            ),
            expected_run_identity=_mapping_from_canonical_json(
                self.__expected_run_identity_json,
                label="expected AGY run identity",
            ),
        )
        if sha256_bytes(canonical_json_bytes(record)) != self.__expected_record_sha256:
            raise IdentityError("AGY workspace binding changed after binding")
        return record

    def to_public_dict(self) -> Dict[str, Any]:
        return self.record


def bind_agy_workspace_plane(
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
) -> AgyWorkspacePlaneBinding:
    """Bind compiler output to AGY's exact disabled custom-agent descriptor."""

    return AgyWorkspacePlaneBinding(
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


def require_agy_workspace_lifecycle_authority(*args: object, **kwargs: object) -> None:
    """Keep filesystem activation and all live lifecycle paths unavailable."""

    del args, kwargs
    raise UnsupportedError(
        "AGY workspace materialization, activation, launch, and qualification "
        "remain disabled pending config isolation, sandbox-off, default-model, "
        "and matched no-bleed proof"
    )


__all__ = [
    "AGY_EXECUTABLE_SHA256",
    "AGY_HELP_SHA256",
    "AGY_VERSION",
    "AGY_VERSION_OBSERVATION_SHA256",
    "AgyWorkspacePlaneBinding",
    "BINDING_SCHEMA",
    "BINDING_STATE",
    "bind_agy_workspace_plane",
    "capture_agy_workspace_identity",
    "require_agy_workspace_lifecycle_authority",
]
