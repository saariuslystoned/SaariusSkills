"""Source-only, body-free launch planning for Grok Build regular sessions.

This module deliberately does not grant live launch authority.  It closes the
private roots and parser-derived launch vector that a future qualification lane
must bind while keeping leader/child halt semantics as an explicit blocker.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import uuid
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Dict, Mapping, Sequence, Tuple

from .adapter_manifest import QUALIFICATION_PROFILE, AdapterManifest
from .census import adapter_implementation_fingerprint
from .errors import IdentityError, UnsupportedError, ValidationError
from .handoffs import PROTOCOL_FINGERPRINT
from .instruction_planes import (
    GROK_BUILD_VERSION,
    GROK_WORKSPACE_ARTIFACT_ID,
    descriptor_fingerprint,
    validate_grok_workspace_addendum_descriptor,
)
from .instructions import validate_instruction_manifest
from .launch import build_admitted_launch_plan, build_launch_identity
from .safety import (
    absolute_root,
    canonical_json_bytes,
    ensure_within,
    paths_overlap,
    sha256_bytes,
    validate_bounded_json,
    validate_identifier,
    validate_sha256,
)


GROK_DISABLE_AUTOUPDATER_VALUE = "true"
GROK_EXECUTABLE_SHA256 = (
    "e1fafdfffe14f339460befaf194360e8f90bfd02efe8a4f24cfa1c7aea657ffe"
)
GROK_VERSION_OUTPUT_SHA256 = (
    "580e7f325a2b1c0807e2eca5ad4bceac313dee481c3e66c06af08013ef89430d"
)
GROK_MAIN_HELP_SHA256 = (
    "d11f1815c770a69d87a05f394c6f7759562738c7de4e29a043f9f06c0aeba1c1"
)
GROK_RUNTIME_BASENAME = "grok-0.2.111-macos-aarch64"
GROK_SAFE_PATH_COMPONENTS: Tuple[str, ...] = ("/usr/bin", "/bin")
GROK_REQUIRED_PATH_TOOLS: Tuple[str, ...] = ("git", "sh")
GROK_LAUNCH_AUTHORITY_BLOCKERS: Tuple[str, ...] = (
    "grok_authentication_isolation_unapproved",
    "grok_native_instruction_plane_unqualified",
    "grok_leader_child_halt_authority_unmodeled",
)
GROK_LAUNCH_AUTHORITY_BLOCKER = (
    "Grok launch remains doctor-only until authentication isolation, the native "
    "instruction plane, and leader/child halt authority are qualified"
)
GROK_WORKSPACE_BINDING_SCHEMA = "puppet.grok-workspace-plane-binding/v1"
GROK_WORKSPACE_BINDING_STATE = "binding_only"
_MAX_SOCKET_PATH_BYTES = 100
_DIRECTORY_IDENTITY_FIELDS = {"path", "device", "inode", "uid", "mode", "nlink"}
_CONTRACT_IDENTITY_FIELDS = {
    "fingerprint",
    "controller",
    "target",
    "task_profile",
}
_RUN_IDENTITY_FIELDS = {"session", "run_id", "nonce"}
_GROK_BINDING_FIELDS = {
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
    "launch_context_sha256",
    "launch_plan_sha256",
    "launch_delta_sha256",
    "workspace_root_sha256",
    "config_root_sha256",
    "requested_model",
    "observed_model",
    "config_fingerprint",
    "artifact",
    "activation_authorized",
    "launch_authorized",
    "qualification_authorized",
}
_GROK_BINDING_HASH_FIELDS = {
    "descriptor_sha256",
    "instruction_manifest_sha256",
    "instruction_policy_fingerprint",
    "effective_contract_fingerprint",
    "effective_contract_sha256",
    "contract_identity_sha256",
    "workspace_identity_sha256",
    "run_identity_sha256",
    "adapter_manifest_sha256",
    "adapter_implementation_sha256",
    "adapter_protocol_sha256",
    "adapter_execution_sha256",
    "launch_context_sha256",
    "launch_plan_sha256",
    "launch_delta_sha256",
    "workspace_root_sha256",
    "config_root_sha256",
}


@dataclass(frozen=True)
class GrokLaunchContext:
    """One immutable, body-free Grok launch candidate without launch authority."""

    doctor_manifest: Path
    doctor_manifest_fingerprint: str
    adapter_fingerprint: str
    executable: Path
    admitted_lane_root: Path
    home: Path
    grok_home: Path
    cwd: Path
    leader_socket: Path
    admitted_lane_root_identity: Mapping[str, Any]
    home_root_identity: Mapping[str, Any]
    workspace_root_identity: Mapping[str, Any]
    config_root_identity: Mapping[str, Any]
    contract_identity: Mapping[str, Any]
    run_identity: Mapping[str, Any]
    controller_session: str
    run_id: str
    grok_session_id: str
    argv: Tuple[str, ...]
    environment: Mapping[str, str]
    launch_identity: Mapping[str, Any]
    admitted_plan: Mapping[str, Any]
    blockers: Tuple[str, ...]
    launch_authorized: bool = False


class GrokWorkspacePlaneBinding:
    """Body-free join rederived from controller-owned expected inputs."""

    __slots__ = (
        "__adapter_manifest_json",
        "__descriptor_json",
        "__effective_contract",
        "__expected_contract_identity_json",
        "__expected_home_root_identity_json",
        "__expected_lane_root_identity_json",
        "__expected_record_sha256",
        "__expected_run_identity_json",
        "__expected_workspace_root_identity_json",
        "__expected_config_root_identity_json",
        "__grok_session_id",
        "__instruction_manifest_json",
        "__leader_socket",
        "__manifest_path",
        "__admitted_lane_root",
        "__home",
        "__grok_home",
        "__cwd",
    )

    def __init__(
        self,
        *,
        descriptor: Mapping[str, Any],
        instruction_manifest: Mapping[str, Any],
        effective_contract: bytes,
        adapter_manifest: AdapterManifest | Mapping[str, Any],
        manifest_path: Path,
        admitted_lane_root: Path,
        home: Path,
        grok_home: Path,
        cwd: Path,
        leader_socket: Path,
        grok_session_id: str,
        expected_contract_identity: Mapping[str, Any],
        expected_run_identity: Mapping[str, Any],
        expected_lane_root_identity: Mapping[str, Any],
        expected_home_root_identity: Mapping[str, Any],
        expected_workspace_root_identity: Mapping[str, Any],
        expected_config_root_identity: Mapping[str, Any],
    ) -> None:
        record = _derive_grok_workspace_binding_record(
            descriptor=descriptor,
            instruction_manifest=instruction_manifest,
            effective_contract=effective_contract,
            adapter_manifest=adapter_manifest,
            manifest_path=manifest_path,
            admitted_lane_root=admitted_lane_root,
            home=home,
            grok_home=grok_home,
            cwd=cwd,
            leader_socket=leader_socket,
            grok_session_id=grok_session_id,
            expected_contract_identity=expected_contract_identity,
            expected_run_identity=expected_run_identity,
            expected_lane_root_identity=expected_lane_root_identity,
            expected_home_root_identity=expected_home_root_identity,
            expected_workspace_root_identity=expected_workspace_root_identity,
            expected_config_root_identity=expected_config_root_identity,
        )
        manifest = _normalized_adapter_manifest(adapter_manifest)
        values = {
            "descriptor_json": canonical_json_bytes(dict(descriptor)),
            "instruction_manifest_json": canonical_json_bytes(
                dict(instruction_manifest)
            ),
            "effective_contract": bytes(effective_contract),
            "adapter_manifest_json": canonical_json_bytes(dict(manifest.raw)),
            "manifest_path": Path(manifest_path),
            "admitted_lane_root": Path(admitted_lane_root),
            "home": Path(home),
            "grok_home": Path(grok_home),
            "cwd": Path(cwd),
            "leader_socket": Path(leader_socket),
            "grok_session_id": grok_session_id,
            "expected_contract_identity_json": canonical_json_bytes(
                dict(expected_contract_identity)
            ),
            "expected_run_identity_json": canonical_json_bytes(
                dict(expected_run_identity)
            ),
            "expected_lane_root_identity_json": canonical_json_bytes(
                dict(expected_lane_root_identity)
            ),
            "expected_home_root_identity_json": canonical_json_bytes(
                dict(expected_home_root_identity)
            ),
            "expected_workspace_root_identity_json": canonical_json_bytes(
                dict(expected_workspace_root_identity)
            ),
            "expected_config_root_identity_json": canonical_json_bytes(
                dict(expected_config_root_identity)
            ),
            "expected_record_sha256": sha256_bytes(canonical_json_bytes(record)),
        }
        for name, value in values.items():
            object.__setattr__(
                self,
                "_GrokWorkspacePlaneBinding__%s" % name,
                value,
            )

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("Grok workspace bindings are immutable")

    def __repr__(self) -> str:
        return "GrokWorkspacePlaneBinding(state='binding_only')"

    @staticmethod
    def _mapping_from_json(value: bytes, label: str) -> Dict[str, Any]:
        try:
            decoded = json.loads(value.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
            raise IdentityError("%s storage is invalid" % label) from exc
        if not isinstance(decoded, dict) or canonical_json_bytes(decoded) != value:
            raise IdentityError("%s storage is invalid" % label)
        return decoded

    @property
    def record(self) -> Dict[str, Any]:
        """Rederive the record from current sources and trusted expectations."""

        record = _derive_grok_workspace_binding_record(
            descriptor=self._mapping_from_json(
                self.__descriptor_json, "Grok workspace descriptor"
            ),
            instruction_manifest=self._mapping_from_json(
                self.__instruction_manifest_json, "Grok instruction manifest"
            ),
            effective_contract=self.__effective_contract,
            adapter_manifest=self._mapping_from_json(
                self.__adapter_manifest_json, "Grok adapter manifest"
            ),
            manifest_path=self.__manifest_path,
            admitted_lane_root=self.__admitted_lane_root,
            home=self.__home,
            grok_home=self.__grok_home,
            cwd=self.__cwd,
            leader_socket=self.__leader_socket,
            grok_session_id=self.__grok_session_id,
            expected_contract_identity=self._mapping_from_json(
                self.__expected_contract_identity_json,
                "expected Grok contract identity",
            ),
            expected_run_identity=self._mapping_from_json(
                self.__expected_run_identity_json,
                "expected Grok run identity",
            ),
            expected_lane_root_identity=self._mapping_from_json(
                self.__expected_lane_root_identity_json,
                "expected Grok lane root identity",
            ),
            expected_home_root_identity=self._mapping_from_json(
                self.__expected_home_root_identity_json,
                "expected Grok home root identity",
            ),
            expected_workspace_root_identity=self._mapping_from_json(
                self.__expected_workspace_root_identity_json,
                "expected Grok workspace root identity",
            ),
            expected_config_root_identity=self._mapping_from_json(
                self.__expected_config_root_identity_json,
                "expected Grok config root identity",
            ),
        )
        if sha256_bytes(canonical_json_bytes(record)) != self.__expected_record_sha256:
            raise IdentityError("Grok workspace binding changed after binding")
        return record

    def to_public_dict(self) -> Dict[str, Any]:
        """Return only hashes, closed identities, and artifact metadata."""

        return self.record


def _private_directory(path: Path, label: str) -> Path:
    root = absolute_root(str(path), label)
    details = root.stat()
    mode = stat.S_IMODE(details.st_mode)
    if details.st_uid != os.getuid() or mode != 0o700:
        raise ValidationError(
            "%s must be owned by the current uid with mode 0700" % label
        )
    return root


def _contained_private_directory(path: Path, lane_root: Path, label: str) -> Path:
    root = _private_directory(path, label)
    contained = ensure_within(root, lane_root, must_exist=True)
    if contained == lane_root:
        raise ValidationError(
            "%s must be a distinct child of the admitted lane root" % label
        )
    return contained


def _regular_file(path: Path, label: str) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        raise ValidationError("%s must be an absolute path" % label)
    if candidate.is_symlink() or not candidate.is_file():
        raise ValidationError("%s must be a non-symlink regular file" % label)
    resolved = candidate.resolve(strict=True)
    if not stat.S_ISREG(resolved.stat().st_mode):
        raise ValidationError("%s must be a regular file" % label)
    return resolved


def _validated_grok_doctor_manifest(
    manifest_path: Path,
) -> tuple[Path, AdapterManifest, Path]:
    """Bind the one known Grok census tuple and its current source owner."""

    bound_path = _regular_file(manifest_path, "Grok doctor manifest")
    manifest = AdapterManifest.from_path(bound_path)
    if manifest.target != "grok":
        raise ValidationError("Grok doctor manifest target is invalid")
    if (
        manifest.raw["doctor_only"] is not True
        or manifest.raw["qualification"] is not None
    ):
        raise ValidationError("Grok launch planning requires a doctor-only manifest")
    current_adapter_fingerprint = adapter_implementation_fingerprint()
    if manifest.raw["adapter_fingerprint"] != current_adapter_fingerprint:
        raise IdentityError("Grok doctor manifest adapter fingerprint is stale")
    if manifest.raw["protocol_fingerprint"] != PROTOCOL_FINGERPRINT:
        raise IdentityError("Grok doctor manifest protocol fingerprint is stale")
    executable = manifest.raw["executable"]
    expected_hashes = {
        "sha256": GROK_EXECUTABLE_SHA256,
        "version_sha256": GROK_VERSION_OUTPUT_SHA256,
        "help_sha256": GROK_MAIN_HELP_SHA256,
    }
    if any(executable[name] != digest for name, digest in expected_hashes.items()):
        raise IdentityError("Grok doctor manifest does not match Build 0.2.111")
    if Path(executable["resolved_path"]).name != GROK_RUNTIME_BASENAME:
        raise IdentityError("Grok doctor manifest runtime basename is invalid")
    if manifest.raw["execution"]["transition"] != "direct":
        raise IdentityError("Grok Build 0.2.111 requires direct execution identity")
    manifest.verify_execution_files()
    binary = _regular_file(Path(executable["resolved_path"]), "Grok executable")
    return bound_path, manifest, binary


def _session_uuid(value: str) -> str:
    if not isinstance(value, str):
        raise ValidationError("Grok session id must be a canonical UUIDv4")
    try:
        parsed = uuid.UUID(value)
    except (AttributeError, ValueError) as exc:
        raise ValidationError("Grok session id must be a canonical UUIDv4") from exc
    if parsed.version != 4 or str(parsed) != value:
        raise ValidationError("Grok session id must be a canonical UUIDv4")
    return value


def _source_owned_environment(home: Path) -> dict[str, str]:
    """Build Grok's closed baseline without consulting operator environment."""

    path_entries = []
    for value in GROK_SAFE_PATH_COMPONENTS:
        if (
            not isinstance(value, str)
            or not value
            or os.pathsep in value
            or not Path(value).is_absolute()
            or not Path(value).is_dir()
        ):
            raise ValidationError(
                "Grok safe PATH must contain existing absolute directories"
            )
        path_entries.append(value)
    if len(path_entries) != len(set(path_entries)):
        raise ValidationError("Grok safe PATH contains duplicate directories")
    safe_path = os.pathsep.join(path_entries)
    for tool in GROK_REQUIRED_PATH_TOOLS:
        discovered = shutil.which(tool, path=safe_path)
        if discovered is None or not Path(discovered).is_absolute():
            raise ValidationError("Grok safe PATH is missing required tooling")
    return {
        "HOME": str(home),
        "PATH": safe_path,
        "LANG": "C",
        "LC_ALL": "C",
    }


def _leader_socket(path: Path, lane_root: Path, roots: Sequence[Path]) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        raise ValidationError("Grok leader socket must be an absolute path")
    if candidate.is_symlink() or candidate.exists():
        raise ValidationError("Grok leader socket must be a new non-symlink path")
    parent = _private_directory(candidate.parent, "Grok leader socket parent")
    ensure_within(parent, lane_root, must_exist=True)
    resolved = ensure_within(candidate, lane_root, must_exist=False)
    if any(paths_overlap(resolved, root) for root in roots):
        raise ValidationError("Grok leader socket collides with a declared root")
    if len(os.fsencode(str(resolved))) > _MAX_SOCKET_PATH_BYTES:
        raise ValidationError("Grok leader socket path exceeds the safe bound")
    return resolved


def _frozen_identity(value: Mapping[str, Any]) -> Mapping[str, Any]:
    frozen = dict(value)
    if isinstance(frozen.get("env_names"), list):
        frozen["env_names"] = tuple(frozen["env_names"])
    if isinstance(frozen.get("argv"), list):
        frozen["argv"] = tuple(frozen["argv"])
    return MappingProxyType(frozen)


def _directory_identity(path: Path, *, label: str) -> Dict[str, Any]:
    candidate = absolute_root(str(path), label)
    details = candidate.stat()
    if not stat.S_ISDIR(details.st_mode):  # pragma: no cover - absolute_root invariant
        raise IdentityError("%s is not a directory" % label)
    return {
        "path": str(candidate),
        "device": details.st_dev,
        "inode": details.st_ino,
        "uid": details.st_uid,
        "mode": stat.S_IMODE(details.st_mode),
        "nlink": details.st_nlink,
    }


def _normalized_directory_identity(
    value: Mapping[str, Any], *, label: str
) -> Dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _DIRECTORY_IDENTITY_FIELDS:
        raise ValidationError("%s fields are invalid" % label)
    path = value.get("path")
    if not isinstance(path, str) or not Path(path).is_absolute():
        raise ValidationError("%s path is invalid" % label)
    result: Dict[str, Any] = {"path": path}
    for name in ("device", "inode", "uid", "mode", "nlink"):
        item = value.get(name)
        if isinstance(item, bool) or not isinstance(item, int) or item < 0:
            raise ValidationError("%s %s is invalid" % (label, name))
        result[name] = item
    return result


def _revalidate_directory_identity(
    expected: Mapping[str, Any], path: Path, *, label: str
) -> None:
    normalized = _normalized_directory_identity(expected, label=label)
    observed = _directory_identity(path, label=label)
    if canonical_json_bytes(normalized) != canonical_json_bytes(observed):
        raise IdentityError("%s identity changed after planning" % label)


def _normalized_contract_identity(value: Mapping[str, Any]) -> Dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != _CONTRACT_IDENTITY_FIELDS:
        raise ValidationError("Grok contract identity fields are invalid")
    fingerprint = validate_sha256(value.get("fingerprint"), "Grok contract fingerprint")
    controller = validate_identifier(value.get("controller"), "Grok controller")
    if (
        value.get("target") != "grok"
        or value.get("task_profile") != QUALIFICATION_PROFILE
    ):
        raise ValidationError("Grok contract identity is not exact")
    return {
        "fingerprint": fingerprint,
        "controller": controller,
        "target": "grok",
        "task_profile": QUALIFICATION_PROFILE,
    }


def _normalized_run_identity(value: Mapping[str, Any]) -> Dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != _RUN_IDENTITY_FIELDS:
        raise ValidationError("Grok run identity fields are invalid")
    return {
        "session": validate_identifier(value.get("session"), "Grok session"),
        "run_id": validate_identifier(value.get("run_id"), "Grok run id"),
        "nonce": validate_identifier(value.get("nonce"), "Grok nonce"),
    }


def _private_context_identity(context: GrokLaunchContext) -> Dict[str, Any]:
    return {
        "doctor_manifest": str(context.doctor_manifest),
        "doctor_manifest_fingerprint": context.doctor_manifest_fingerprint,
        "adapter_fingerprint": context.adapter_fingerprint,
        "executable": str(context.executable),
        "admitted_lane_root": str(context.admitted_lane_root),
        "home": str(context.home),
        "grok_home": str(context.grok_home),
        "cwd": str(context.cwd),
        "leader_socket": str(context.leader_socket),
        "admitted_lane_root_identity": dict(context.admitted_lane_root_identity),
        "home_root_identity": dict(context.home_root_identity),
        "workspace_root_identity": dict(context.workspace_root_identity),
        "config_root_identity": dict(context.config_root_identity),
        "contract_identity": dict(context.contract_identity),
        "run_identity": dict(context.run_identity),
        "controller_session": context.controller_session,
        "run_id": context.run_id,
        "grok_session_id": context.grok_session_id,
        "argv": list(context.argv),
        "environment": dict(context.environment),
        "launch_identity": dict(context.launch_identity),
        "admitted_plan": dict(context.admitted_plan),
        "blockers": list(context.blockers),
        "launch_authorized": context.launch_authorized,
    }


def _revalidate_context_roots(context: GrokLaunchContext) -> None:
    if type(context) is not GrokLaunchContext:
        raise IdentityError("Grok launch context is invalid")
    for expected, path, label in (
        (
            context.admitted_lane_root_identity,
            context.admitted_lane_root,
            "admitted Grok lane root",
        ),
        (context.home_root_identity, context.home, "Grok lane HOME"),
        (context.workspace_root_identity, context.cwd, "Grok workspace root"),
        (context.config_root_identity, context.grok_home, "Grok config root"),
    ):
        _revalidate_directory_identity(expected, path, label=label)


def _require_expected_directory_identity(
    path: Path,
    expected: Mapping[str, Any],
    *,
    label: str,
) -> Dict[str, Any]:
    normalized = _normalized_directory_identity(expected, label=label)
    try:
        observed = _directory_identity(path, label=label)
    except (OSError, ValidationError) as exc:
        raise IdentityError("%s identity changed" % label) from exc
    if canonical_json_bytes(observed) != canonical_json_bytes(normalized):
        raise IdentityError("%s identity changed" % label)
    return normalized


def _normalized_adapter_manifest(
    value: AdapterManifest | Mapping[str, Any],
) -> AdapterManifest:
    if isinstance(value, AdapterManifest):
        return AdapterManifest.from_dict(dict(value.raw))
    if not isinstance(value, Mapping):
        raise ValidationError("Grok adapter manifest is invalid")
    return AdapterManifest.from_dict(dict(value))


def _identity_sha256(value: Mapping[str, Any]) -> str:
    return sha256_bytes(canonical_json_bytes(dict(value)))


def _validate_binding_record(value: Mapping[str, Any]) -> Dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _GROK_BINDING_FIELDS:
        raise IdentityError("Grok workspace binding fields changed")
    result = dict(value)
    if (
        result["schema"] != GROK_WORKSPACE_BINDING_SCHEMA
        or result["state"] != GROK_WORKSPACE_BINDING_STATE
        or result["target"] != "grok"
        or result["target_version"] != GROK_BUILD_VERSION
        or result["plane"] != "workspace_addendum"
        or result["requested_model"] != "default"
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
        raise IdentityError("Grok workspace binding authority state changed")
    validate_identifier(result["descriptor_id"], "Grok descriptor id")
    for name in _GROK_BINDING_HASH_FIELDS:
        validate_sha256(result[name], "Grok binding %s" % name)
    if (
        isinstance(result["effective_contract_bytes"], bool)
        or not isinstance(result["effective_contract_bytes"], int)
        or result["effective_contract_bytes"] <= 0
    ):
        raise IdentityError("Grok effective contract size changed")
    artifact = result["artifact"]
    if not isinstance(artifact, Mapping) or set(artifact) != {
        "artifact_id",
        "root_ref",
        "relative_path",
        "content_ref",
        "write_mode",
    }:
        raise IdentityError("Grok workspace binding artifact changed")
    if dict(artifact) != {
        "artifact_id": GROK_WORKSPACE_ARTIFACT_ID,
        "root_ref": "workspace_root",
        "relative_path": ".grok/rules/puppet-%s.md"
        % result["effective_contract_sha256"],
        "content_ref": "effective_contract",
        "write_mode": "create_only",
    }:
        raise IdentityError("Grok workspace binding artifact changed")
    validate_bounded_json(
        result,
        max_depth=5,
        max_items=64,
        max_string=512,
        reject_sensitive_fields=True,
    )
    return result


def build_grok_launch_context(
    *,
    manifest_path: Path,
    admitted_lane_root: Path,
    home: Path,
    grok_home: Path,
    cwd: Path,
    leader_socket: Path,
    contract_identity: Mapping[str, Any],
    run_identity: Mapping[str, Any],
    grok_session_id: str,
) -> GrokLaunchContext:
    """Build an exact source-only Grok plan without task or instruction inputs."""

    bound_manifest, manifest, binary = _validated_grok_doctor_manifest(manifest_path)
    lane_root = _private_directory(admitted_lane_root, "admitted Grok lane root")
    lane_home = _contained_private_directory(home, lane_root, "Grok lane HOME")
    lane_grok_home = _contained_private_directory(
        grok_home, lane_root, "Grok lane GROK_HOME"
    )
    if paths_overlap(lane_home, lane_grok_home):
        raise ValidationError("Grok lane HOME and GROK_HOME must not overlap")
    workspace = absolute_root(str(cwd), "Grok workspace cwd")
    if paths_overlap(workspace, lane_root):
        raise ValidationError(
            "Grok workspace cwd must not overlap the private lane root"
        )
    socket_path = _leader_socket(
        leader_socket,
        lane_root,
        (lane_home, lane_grok_home, workspace),
    )
    bound_contract_identity = _normalized_contract_identity(contract_identity)
    bound_run_identity = _normalized_run_identity(run_identity)
    puppet_session = bound_run_identity["session"]
    bound_run_id = bound_run_identity["run_id"]
    target_session = _session_uuid(grok_session_id)

    argv = (
        str(binary),
        "--always-approve",
        "--sandbox",
        "off",
        "--cwd",
        str(workspace),
        "--leader-socket",
        str(socket_path),
        "--session-id",
        target_session,
    )
    source = _source_owned_environment(lane_home)
    environment, launch_identity = build_launch_identity(
        target="grok",
        repo=workspace,
        argv=argv,
        source_environment=source,
        bindings={
            "GROK_HOME": str(lane_grok_home),
            "GROK_DISABLE_AUTOUPDATER": GROK_DISABLE_AUTOUPDATER_VALUE,
        },
        admitted_lane_root=lane_root,
    )
    manifest.verify_launch_execution_environment(environment)
    if environment.get("HOME") != str(lane_home):
        raise ValidationError("Grok launch context did not bind the private lane HOME")
    admitted_plan = build_admitted_launch_plan(
        target="grok",
        session=puppet_session,
        run_id=bound_run_id,
        repo=workspace,
        argv=argv,
        environment=environment,
        admitted_lane_root=lane_root,
    )
    return GrokLaunchContext(
        doctor_manifest=bound_manifest,
        doctor_manifest_fingerprint=manifest.fingerprint,
        adapter_fingerprint=manifest.raw["adapter_fingerprint"],
        executable=binary,
        admitted_lane_root=lane_root,
        home=lane_home,
        grok_home=lane_grok_home,
        cwd=workspace,
        leader_socket=socket_path,
        admitted_lane_root_identity=_frozen_identity(
            _directory_identity(lane_root, label="admitted Grok lane root")
        ),
        home_root_identity=_frozen_identity(
            _directory_identity(lane_home, label="Grok lane HOME")
        ),
        workspace_root_identity=_frozen_identity(
            _directory_identity(workspace, label="Grok workspace root")
        ),
        config_root_identity=_frozen_identity(
            _directory_identity(lane_grok_home, label="Grok config root")
        ),
        contract_identity=_frozen_identity(bound_contract_identity),
        run_identity=_frozen_identity(bound_run_identity),
        controller_session=puppet_session,
        run_id=bound_run_id,
        grok_session_id=target_session,
        argv=argv,
        environment=MappingProxyType(dict(environment)),
        launch_identity=_frozen_identity(launch_identity),
        admitted_plan=_frozen_identity(admitted_plan),
        blockers=GROK_LAUNCH_AUTHORITY_BLOCKERS,
        launch_authorized=False,
    )


def _derive_grok_workspace_binding_record(
    *,
    descriptor: Mapping[str, Any],
    instruction_manifest: Mapping[str, Any],
    effective_contract: bytes,
    adapter_manifest: AdapterManifest | Mapping[str, Any],
    manifest_path: Path,
    admitted_lane_root: Path,
    home: Path,
    grok_home: Path,
    cwd: Path,
    leader_socket: Path,
    grok_session_id: str,
    expected_contract_identity: Mapping[str, Any],
    expected_run_identity: Mapping[str, Any],
    expected_lane_root_identity: Mapping[str, Any],
    expected_home_root_identity: Mapping[str, Any],
    expected_workspace_root_identity: Mapping[str, Any],
    expected_config_root_identity: Mapping[str, Any],
) -> Dict[str, Any]:
    """Rederive the join from current sources and controller expectations."""

    normalized_descriptor = validate_grok_workspace_addendum_descriptor(descriptor)
    normalized_instruction = validate_instruction_manifest(
        instruction_manifest,
        target="grok",
    )
    if not isinstance(effective_contract, bytes) or not effective_contract:
        raise ValidationError("Grok effective contract must be non-empty bytes")
    contract_bytes = bytes(effective_contract)
    rendered_sha = sha256_bytes(contract_bytes)
    if normalized_instruction[
        "rendered_sha256"
    ] != rendered_sha or normalized_instruction["byte_count"] != len(contract_bytes):
        raise IdentityError(
            "Grok effective contract does not match its instruction manifest"
        )
    if normalized_instruction["runtime_binding"] != {
        "model": "unavailable",
        "effort": "unavailable",
    }:
        raise IdentityError(
            "Grok workspace binding requires the unresolved default model"
        )

    artifact = normalized_descriptor["materialize"][0]
    expected_relative_path = ".grok/rules/puppet-%s.md" % rendered_sha
    if artifact["relative_path"] != expected_relative_path:
        raise IdentityError(
            "Grok workspace rule filename does not match the effective contract"
        )

    bound_contract_identity = _normalized_contract_identity(expected_contract_identity)
    bound_run_identity = _normalized_run_identity(expected_run_identity)
    _require_expected_directory_identity(
        admitted_lane_root,
        expected_lane_root_identity,
        label="admitted Grok lane root",
    )
    _require_expected_directory_identity(
        home,
        expected_home_root_identity,
        label="Grok lane HOME",
    )
    _require_expected_directory_identity(
        cwd,
        expected_workspace_root_identity,
        label="Grok workspace root",
    )
    _require_expected_directory_identity(
        grok_home,
        expected_config_root_identity,
        label="Grok config root",
    )
    context = build_grok_launch_context(
        manifest_path=manifest_path,
        admitted_lane_root=admitted_lane_root,
        home=home,
        grok_home=grok_home,
        cwd=cwd,
        leader_socket=leader_socket,
        contract_identity=bound_contract_identity,
        run_identity=bound_run_identity,
        grok_session_id=grok_session_id,
    )
    manifest = _normalized_adapter_manifest(adapter_manifest)
    descriptor_target = normalized_descriptor["target"]
    if (
        manifest.target != "grok"
        or manifest.raw["doctor_only"] is not True
        or manifest.raw["qualification"] is not None
        or manifest.fingerprint != context.doctor_manifest_fingerprint
        or descriptor_target["adapter_manifest_sha256"] != manifest.fingerprint
    ):
        raise IdentityError("Grok workspace descriptor adapter manifest mismatch")
    if (
        manifest.raw["adapter_fingerprint"] != context.adapter_fingerprint
        or manifest.raw["adapter_fingerprint"] != adapter_implementation_fingerprint()
    ):
        raise IdentityError("Grok workspace adapter implementation mismatch")
    if (
        descriptor_target["version"] != GROK_BUILD_VERSION
        or descriptor_target["requested_model"] != "default"
        or descriptor_target["observed_model"] != "unavailable"
        or descriptor_target["config_fingerprint"] != "unavailable"
    ):
        raise IdentityError("Grok workspace target tuple mismatch")

    expected_environment = {
        "GROK_DISABLE_AUTOUPDATER": GROK_DISABLE_AUTOUPDATER_VALUE,
        "GROK_HOME": str(context.grok_home),
        "HOME": str(context.home),
        "LANG": "C",
        "LC_ALL": "C",
        "PATH": os.pathsep.join(GROK_SAFE_PATH_COMPONENTS),
    }
    argv = list(context.argv)
    if (
        dict(context.environment) != expected_environment
        or argv.count("--cwd") != 1
        or argv[argv.index("--cwd") + 1] != str(context.cwd)
        or "--model" in argv
        or "--reasoning-effort" in argv
    ):
        raise IdentityError("Grok workspace launch context delta mismatch")
    if normalized_descriptor["launch_delta"] != {
        "cwd_ref": "workspace_root",
        "env": [
            {
                "name": "GROK_DISABLE_AUTOUPDATER",
                "value_ref": "true_literal",
            },
            {"name": "GROK_HOME", "value_ref": "config_root_path"},
        ],
        "argv": [],
    }:
        raise IdentityError("Grok workspace descriptor launch delta mismatch")

    workspace_identity = _normalized_directory_identity(
        normalized_instruction["workspace_identity"],
        label="Grok instruction workspace identity",
    )
    if workspace_identity != dict(context.workspace_root_identity):
        raise IdentityError(
            "Grok instruction manifest workspace does not match launch context"
        )
    contract_identity = _normalized_contract_identity(
        normalized_instruction["contract_identity"]
    )
    if contract_identity != bound_contract_identity:
        raise IdentityError(
            "Grok instruction manifest contract does not match launch context"
        )
    run_identity = _normalized_run_identity(normalized_instruction["run_identity"])
    if run_identity != bound_run_identity:
        raise IdentityError(
            "Grok instruction manifest run does not match launch context"
        )
    instruction_manifest_sha = sha256_bytes(
        canonical_json_bytes(normalized_instruction) + b"\n"
    )
    private_context_sha = sha256_bytes(
        canonical_json_bytes(_private_context_identity(context))
    )
    record: Dict[str, Any] = {
        "schema": GROK_WORKSPACE_BINDING_SCHEMA,
        "state": GROK_WORKSPACE_BINDING_STATE,
        "target": "grok",
        "target_version": GROK_BUILD_VERSION,
        "plane": "workspace_addendum",
        "descriptor_id": normalized_descriptor["descriptor_id"],
        "descriptor_sha256": descriptor_fingerprint(normalized_descriptor),
        "instruction_manifest_sha256": instruction_manifest_sha,
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
        "adapter_implementation_sha256": context.adapter_fingerprint,
        "adapter_protocol_sha256": manifest.raw["protocol_fingerprint"],
        "adapter_execution_sha256": manifest.execution_fingerprint,
        "launch_context_sha256": private_context_sha,
        "launch_plan_sha256": sha256_bytes(
            canonical_json_bytes(dict(context.admitted_plan))
        ),
        "launch_delta_sha256": sha256_bytes(
            canonical_json_bytes(normalized_descriptor["launch_delta"])
        ),
        "workspace_root_sha256": _identity_sha256(workspace_identity),
        "config_root_sha256": _identity_sha256(context.config_root_identity),
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
    validate_bounded_json(
        record,
        max_depth=5,
        max_items=64,
        max_string=512,
        reject_sensitive_fields=True,
    )
    record_json = canonical_json_bytes(record)
    if contract_bytes in record_json:
        raise IdentityError("Grok workspace binding contains instruction bytes")
    return _validate_binding_record(record)


def bind_grok_workspace_plane(
    *,
    descriptor: Mapping[str, Any],
    instruction_manifest: Mapping[str, Any],
    effective_contract: bytes,
    adapter_manifest: AdapterManifest | Mapping[str, Any],
    manifest_path: Path,
    admitted_lane_root: Path,
    home: Path,
    grok_home: Path,
    cwd: Path,
    leader_socket: Path,
    grok_session_id: str,
    expected_contract_identity: Mapping[str, Any],
    expected_run_identity: Mapping[str, Any],
    expected_lane_root_identity: Mapping[str, Any],
    expected_home_root_identity: Mapping[str, Any],
    expected_workspace_root_identity: Mapping[str, Any],
    expected_config_root_identity: Mapping[str, Any],
) -> GrokWorkspacePlaneBinding:
    """Bind current Grok sources to explicit controller-owned expectations."""

    return GrokWorkspacePlaneBinding(
        descriptor=descriptor,
        instruction_manifest=instruction_manifest,
        effective_contract=effective_contract,
        adapter_manifest=adapter_manifest,
        manifest_path=manifest_path,
        admitted_lane_root=admitted_lane_root,
        home=home,
        grok_home=grok_home,
        cwd=cwd,
        leader_socket=leader_socket,
        grok_session_id=grok_session_id,
        expected_contract_identity=expected_contract_identity,
        expected_run_identity=expected_run_identity,
        expected_lane_root_identity=expected_lane_root_identity,
        expected_home_root_identity=expected_home_root_identity,
        expected_workspace_root_identity=expected_workspace_root_identity,
        expected_config_root_identity=expected_config_root_identity,
    )


def require_live_grok_launch(context: GrokLaunchContext) -> None:
    """Fail closed until Grok's remaining authority blockers are qualified."""

    if not isinstance(context, GrokLaunchContext):
        raise ValidationError("Grok launch context is invalid")
    raise UnsupportedError(GROK_LAUNCH_AUTHORITY_BLOCKER)
