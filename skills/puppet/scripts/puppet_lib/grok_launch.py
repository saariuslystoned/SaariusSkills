"""Source-only, body-free launch planning for Grok Build regular sessions.

This module deliberately does not grant live launch authority.  It closes the
private roots and parser-derived launch vector that a future qualification lane
must bind while keeping leader/child halt semantics as an explicit blocker.
"""

from __future__ import annotations

import os
import shutil
import stat
import uuid
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Sequence, Tuple

from .adapter_manifest import AdapterManifest
from .census import adapter_implementation_fingerprint
from .errors import IdentityError, UnsupportedError, ValidationError
from .handoffs import PROTOCOL_FINGERPRINT
from .launch import build_admitted_launch_plan, build_launch_identity
from .safety import (
    absolute_root,
    ensure_within,
    paths_overlap,
    validate_identifier,
)


GROK_DISABLE_AUTOUPDATER_VALUE = "true"
GROK_EXECUTABLE_SHA256 = (
    "7229f5e2a69b05832c86db82bebda541e92b5c24958fbfacf5c8f463394d3027"
)
GROK_VERSION_OUTPUT_SHA256 = (
    "9bd542d793801415b20fcd8165e714196c3d7ae6f927782a2b41c6a0e939118e"
)
GROK_MAIN_HELP_SHA256 = (
    "17211afac01a2f089f47a0c6f0e9ec0ff38c0bc86a977c2da713e16c63e25fe2"
)
GROK_RUNTIME_BASENAME = "grok-macos-aarch64"
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
_MAX_SOCKET_PATH_BYTES = 100


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
    controller_session: str
    run_id: str
    grok_session_id: str
    argv: Tuple[str, ...]
    environment: Mapping[str, str]
    launch_identity: Mapping[str, Any]
    admitted_plan: Mapping[str, Any]
    blockers: Tuple[str, ...]
    launch_authorized: bool = False


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
        raise IdentityError("Grok doctor manifest does not match Build 0.2.106")
    if Path(executable["resolved_path"]).name != GROK_RUNTIME_BASENAME:
        raise IdentityError("Grok doctor manifest runtime basename is invalid")
    if manifest.raw["execution"]["transition"] != "direct":
        raise IdentityError("Grok Build 0.2.106 requires direct execution identity")
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


def build_grok_launch_context(
    *,
    manifest_path: Path,
    admitted_lane_root: Path,
    home: Path,
    grok_home: Path,
    cwd: Path,
    leader_socket: Path,
    controller_session: str,
    run_id: str,
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
    puppet_session = validate_identifier(controller_session, "controller session")
    bound_run_id = validate_identifier(run_id, "run id")
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


def require_live_grok_launch(context: GrokLaunchContext) -> None:
    """Fail closed until Grok's remaining authority blockers are qualified."""

    if not isinstance(context, GrokLaunchContext):
        raise ValidationError("Grok launch context is invalid")
    raise UnsupportedError(GROK_LAUNCH_AUTHORITY_BLOCKER)
