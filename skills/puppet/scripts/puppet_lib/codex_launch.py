"""Source-only Codex launch gate context.

The gate binds manifest and filesystem identity without launching a target process.
Returned context is value-free by design; private launch argv and environment are
retained only as immutable launch checks.
"""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Tuple
from typing import Sequence

from .adapter_manifest import AdapterManifest
from .campaign import active_target_processes
from .census import adapter_implementation_fingerprint
from .errors import IdentityError, ValidationError
from .handoffs import PROTOCOL_FINGERPRINT
from .launch import public_launch_identity, select_launch_environment
from .contracts import PROCESS_IDENTITY_FIELDS
from .safety import (
    absolute_root,
    canonical_json_bytes,
    ensure_within,
    paths_overlap,
    sha256_bytes,
    validate_identifier,
)

LAUNCH_CONTEXT_SCHEMA = "puppet.codex-launch-context/v1"
EXPECTED_EXECUTABLE_PATH = "/opt/homebrew/bin/codex"
EXPECTED_EXECUTABLE_SHA256 = "1da3f4e0e96028b8a771814293c3033dafd1971f943f6c7e79b0897fe705f590"
EXPECTED_VERSION_SHA256 = "f9eb0c462cdded1fb971b33c647ff1b8b491dfe962a1506026e07a06f634f651"
EXPECTED_VERSION_TEXT = "codex-cli 0.145.0"
EXPECTED_ADAPTER_FINGERPRINT = adapter_implementation_fingerprint()


def _validate_root(path: Path, *, label: str) -> Dict[str, Any]:
    root = absolute_root(str(path), label)
    details = root.stat()
    if not stat.S_ISDIR(details.st_mode):
        raise ValidationError("%s is not a directory" % label)
    if details.st_uid != os.getuid():
        raise ValidationError("%s is not user-owned" % label)
    if stat.S_IMODE(details.st_mode) != 0o700:
        raise ValidationError("%s is not 0700" % label)
    return {
        "path": str(root),
        "device": details.st_dev,
        "inode": details.st_ino,
        "uid": details.st_uid,
        "gid": details.st_gid,
        "mode": stat.S_IMODE(details.st_mode),
        "nlink": details.st_nlink,
    }


def _contained_private_root(
    root: Path, *, parent: Path, label: str
) -> Dict[str, Any]:
    details = _validate_root(root, label=label)
    contained = ensure_within(Path(details["path"]), parent, must_exist=True)
    if contained == parent:
        raise ValidationError("%s must be a distinct child of the lane root" % label)
    return _validate_root(contained, label=label)


def _validate_launch_argv(*, mapping: Mapping[str, Any], executable_path: str) -> Tuple[str, ...]:
    raw_argv = mapping.get("launch_argv")
    if not isinstance(raw_argv, list) or not raw_argv:
        raise ValidationError("manifest launch argv must be a non-empty list")
    if len(raw_argv) > 64:
        raise ValidationError("manifest launch argv is too long")
    validated = []
    for item in raw_argv:
        if (
            not isinstance(item, str)
            or not item
            or len(item) > 8192
            or any(character in item for character in "\x00\r\n")
        ):
            raise ValidationError("manifest launch argv item is invalid")
        validated.append(item)
    if validated[0] != executable_path:
        raise ValidationError("manifest launch argv does not start with executable path")
    return tuple(validated)


def _validate_candidate_processes(processes: Any, *, block: list[str]) -> Tuple[int, ...]:
    if not isinstance(processes, list):
        raise ValidationError("candidate process output must be a list")
    if len(processes) > 4096:
        raise ValidationError("candidate process output is too large")
    validated = []
    seen = set()
    for process in processes:
        if (
            not isinstance(process, dict)
            or set(process) != PROCESS_IDENTITY_FIELDS
            or isinstance(process.get("pid"), bool)
            or not isinstance(process.get("pid"), int)
            or process["pid"] <= 1
        ):
            raise ValidationError("candidate process identity is invalid")
        if process["pid"] in seen:
            raise ValidationError("candidate process identities duplicate")
        seen.add(process["pid"])
        validated.append(process["pid"])
    if not processes:
        block.append("no existing target candidate processes detected")
    return tuple(sorted(validated))


def _build_candidate_fingerprint(pids: Sequence[int]) -> str:
    return sha256_bytes(
        canonical_json_bytes(
            {
                "count": len(pids),
                "pids": list(sorted(pids)),
            }
        )
    )


@dataclass(frozen=True)
class CodexLaunchContext:
    """Value-private source-only launch context."""

    target: str
    session_profile: str
    manifest_fingerprint: str
    adapter_fingerprint: str
    protocol_fingerprint: str
    version_text: str
    executable_path: str
    manifest_executable_sha256: str
    manifest_version_sha256: str
    lane_root_identity: Dict[str, Any]
    workspace_root_identity: Dict[str, Any]
    codex_home_identity: Dict[str, Any]
    launch_authorized: bool
    blockers: Tuple[str, ...]
    auth_value_accepted: bool
    auth_value_persisted: bool
    candidate_process_count: int
    candidate_process_pids: Tuple[int, ...]
    candidate_process_fingerprint: str
    _argv: Tuple[str, ...] = field(repr=False)
    _environment_items: Tuple[Tuple[str, str], ...] = field(repr=False)
    _launch_identity: Dict[str, Any] = field(repr=False)

    def to_public_dict(self) -> Dict[str, Any]:
        return {
            "schema": LAUNCH_CONTEXT_SCHEMA,
            "target": self.target,
            "session_profile": self.session_profile,
            "launch_authorized": self.launch_authorized,
            "manifest_fingerprint": self.manifest_fingerprint,
            "adapter_fingerprint": self.adapter_fingerprint,
            "protocol_fingerprint": self.protocol_fingerprint,
            "version_text": self.version_text,
            "executable_path": self.executable_path,
            "executable_sha256": self.manifest_executable_sha256,
            "version_sha256": self.manifest_version_sha256,
            "lane_root_identity": self.lane_root_identity,
            "workspace_root_identity": self.workspace_root_identity,
            "codex_home_identity": self.codex_home_identity,
            "lane_root_identity_sha256": sha256_bytes(
                canonical_json_bytes(self.lane_root_identity)
            ),
            "workspace_root_identity_sha256": sha256_bytes(
                canonical_json_bytes(self.workspace_root_identity)
            ),
            "codex_home_identity_sha256": sha256_bytes(
                canonical_json_bytes(self.codex_home_identity)
            ),
            "launch_identity": self._launch_identity,
            "candidate_process_count": self.candidate_process_count,
            "candidate_process_pids": list(self.candidate_process_pids),
            "candidate_process_fingerprint": self.candidate_process_fingerprint,
            "process_local_CODEX_ACCESS_TOKEN": {
                "accepted": self.auth_value_accepted,
                "persisted": self.auth_value_persisted,
            },
            "auth_value_accepted": self.auth_value_accepted,
            "auth_value_persisted": self.auth_value_persisted,
            "blockers": list(self.blockers),
        }

    @property
    def public_context_sha256(self) -> str:
        return sha256_bytes(canonical_json_bytes(self.to_public_dict()))

    @property
    def argv(self) -> list[str]:
        return list(self._argv)

    @property
    def environment(self) -> Dict[str, str]:
        return dict(self._environment_items)


def build_codex_launch_context(
    *,
    manifest_path: Path | str,
    lane_root: Path | str,
    workspace_root: Path | str,
    codex_home: Path | str,
    candidate_fn: Callable[[str, list[Dict[str, Any]]], list[Dict[str, Any]]] = active_target_processes,
    process_local_CODEX_ACCESS_TOKEN: str | None = None,
) -> CodexLaunchContext:
    """Build a source-only Codex launch context without starting anything."""

    session_profile = validate_identifier("regular", "session profile")
    manifest = AdapterManifest.from_path(Path(manifest_path))
    if manifest.target != "codex":
        raise ValidationError("launch context requires target codex")

    blockers = []
    if process_local_CODEX_ACCESS_TOKEN is not None:
        if not isinstance(process_local_CODEX_ACCESS_TOKEN, str):
            raise ValidationError("process-local CODEX access token must be a string")
        blockers.append("no approved CODEX_ACCESS_TOKEN broker route for child launch")
    lane = _validate_root(Path(lane_root), label="lane root")
    lane_root_path = Path(lane["path"])
    workspace = _contained_private_root(
        Path(workspace_root),
        parent=lane_root_path,
        label="workspace root",
    )
    workspace_path = Path(workspace["path"])
    home = _contained_private_root(
        Path(codex_home),
        parent=lane_root_path,
        label="CODEX_HOME",
    )
    codex_home_path = Path(home["path"])
    if paths_overlap(workspace_path, codex_home_path):
        raise ValidationError("workspace and CODEX_HOME must be non-overlapping")
    if manifest.raw["adapter_fingerprint"] != EXPECTED_ADAPTER_FINGERPRINT:
        raise ValidationError("manifest adapter fingerprint is unexpected")
    if manifest.raw["protocol_fingerprint"] != PROTOCOL_FINGERPRINT:
        raise ValidationError("manifest protocol fingerprint is unexpected")

    mapping = manifest.raw["yolo_mapping"]
    argv = _validate_launch_argv(
        mapping=mapping,
        executable_path=manifest.raw["executable"]["resolved_path"],
    )
    executable = manifest.raw["executable"]
    if executable["resolved_path"] != EXPECTED_EXECUTABLE_PATH:
        raise ValidationError("manifest executable path is not the expected Codex binary")
    if executable["sha256"] != EXPECTED_EXECUTABLE_SHA256:
        raise ValidationError("manifest executable hash is unexpected")
    if executable["version_sha256"] != EXPECTED_VERSION_SHA256:
        raise ValidationError("manifest executable version hash is unexpected")
    if not manifest.raw["yolo_mapping"].get("complete", False):
        blockers.append("native-plane mapping remains incomplete")
    if manifest.raw["yolo_mapping"].get("model_flag") is not None:
        blockers.append("native plane model selector remains unresolved")
    if manifest.raw["yolo_mapping"].get("effort_flag") is not None:
        blockers.append("native plane effort selector remains unresolved")
    if "--model" in argv:
        blockers.append("manifest launch argv includes model selector")
    if "--effort" in argv:
        blockers.append("manifest launch argv includes effort selector")
    if set(argv) != {manifest.raw["executable"]["resolved_path"]}:
        blockers.append("native launch argv is not source-only")
    if not manifest.raw["doctor_only"]:
        raise ValidationError("source-only Codex launch requires doctor-only manifest")
    if manifest.raw["qualification"] is not None:
        raise ValidationError("source-only Codex launch requires a doctor-only manifest")
    auth_accepted = False
    auth_persisted = False

    try:
        selectors = manifest.process_execution_selectors()
        candidate_processes = candidate_fn(manifest.target, selectors)
    except (TypeError, ValueError, IdentityError, ValidationError, AttributeError):
        raise ValidationError("candidate process lookup is malformed")
    except Exception as exc:  # pragma: no cover - defensive guardrail
        raise ValidationError("candidate process lookup failed") from exc
    try:
        candidate_pids = _validate_candidate_processes(
            candidate_processes,
            block=blockers,
        )
    except (TypeError, ValueError, IdentityError, ValidationError) as exc:
        raise ValidationError("candidate process lookup is malformed") from exc

    candidate_hash = _build_candidate_fingerprint(candidate_pids)

    environment = select_launch_environment(
        target="codex",
        source_environment={},
        bindings={"CODEX_HOME": str(codex_home_path)},
        admitted_lane_root=lane_root_path,
    )
    launch_identity = public_launch_identity(
        repo=workspace_path,
        argv=argv,
        environment=environment,
        admitted_lane_root=lane_root_path,
    )
    context = CodexLaunchContext(
        target=manifest.target,
        session_profile=session_profile,
        manifest_fingerprint=manifest.fingerprint,
        adapter_fingerprint=manifest.raw["adapter_fingerprint"],
        protocol_fingerprint=manifest.raw["protocol_fingerprint"],
        version_text=EXPECTED_VERSION_TEXT,
        executable_path=executable["resolved_path"],
        manifest_executable_sha256=executable["sha256"],
        manifest_version_sha256=executable["version_sha256"],
        lane_root_identity=lane,
        workspace_root_identity=workspace,
        codex_home_identity=home,
        launch_authorized=False,
        blockers=tuple(blockers),
        auth_value_accepted=auth_accepted,
        auth_value_persisted=auth_persisted,
        candidate_process_count=len(candidate_pids),
        candidate_process_pids=candidate_pids,
        candidate_process_fingerprint=candidate_hash,
        _argv=argv,
        _environment_items=tuple(sorted(environment.items())),
        _launch_identity=launch_identity,
    )
    return context
