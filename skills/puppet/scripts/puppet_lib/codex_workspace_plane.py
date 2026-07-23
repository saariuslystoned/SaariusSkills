"""Launch-disabled Codex workspace instruction-plane planner.

The exact Codex tuple has no authenticated isolated-home proof and no native
workspace-plane activation/no-bleed evidence.  This module therefore creates
only a body-free plan for a future create-only ``AGENTS.md`` candidate.  It
never writes the candidate, launches Codex, or claims lifecycle authority.
"""

from __future__ import annotations

import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, NoReturn, Optional

from .adapter_manifest import QUALIFICATION_PROFILE
from .codex_launch import (
    AUTH_ROUTE,
    CURRENT_DEFAULT_SELECTION,
    EXPECTED_EXECUTABLE_SHA256,
    EXPECTED_REQUESTED_EXECUTABLE_PATH,
    EXPECTED_RESOLVED_EXECUTABLE_PATH,
    EXPECTED_UNRESTRICTED_FLAG,
    EXPECTED_VERSION_TEXT,
    EXPECTED_VERSION_SHA256,
    MAPPING_INCOMPLETE_BLOCKER,
    SOURCE_ONLY_BLOCKERS,
    CodexLaunchContext,
    build_codex_launch_context,
)
from .errors import ConflictError, IdentityError, UnsupportedError, ValidationError
from .conformance import tree_fingerprint
from .instructions import validate_instruction_manifest
from .launch import (
    build_admitted_launch_plan,
    select_launch_environment,
    validate_admitted_launch_plan,
)
from .safety import (
    canonical_json_bytes,
    paths_overlap,
    sha256_bytes,
    validate_bounded_json,
    validate_identifier,
    validate_sha256,
)


PLAN_SCHEMA = "puppet.codex-workspace-plane-plan/v2"
STATUS = {"surface": "hypothesis", "activation": "disabled"}
PLANNED_ARTIFACT = "AGENTS.md"
WORKSPACE_BLOCKERS = (
    "codex_workspace_agents_activation_unqualified",
    "codex_workspace_instruction_precedence_unproved",
    "codex_workspace_no_bleed_unproved",
    "codex_workspace_lifecycle_disabled",
)
_ALL_BLOCKERS = (*SOURCE_ONLY_BLOCKERS, MAPPING_INCOMPLETE_BLOCKER, *WORKSPACE_BLOCKERS)
_LIFECYCLE_DISABLED = (
    "Codex workspace materialization, launch, verification, rollback, and "
    "recovery remain disabled pending authenticated isolated-home, activation, "
    "precedence, exact halt, and no-bleed proof"
)
_ROOT_FIELDS = {"path", "device", "inode", "uid", "gid", "mode", "nlink"}
_PLAN_FIELDS = {
    "schema",
    "target",
    "codex_version",
    "status",
    "blockers",
    "launch_authorized",
    "materialization_supported",
    "rollback_supported",
    "recovery_supported",
    "manifest_fingerprint",
    "adapter_implementation_sha256",
    "adapter_protocol_sha256",
    "requested_executable_path",
    "resolved_executable_path",
    "executable_sha256",
    "version_sha256",
    "launch_context_sha256",
    "lane_root_identity",
    "workspace_root_identity",
    "codex_home_identity",
    "launch_delta",
    "admitted_launch_plan",
    "instruction_manifest_sha256",
    "contract_identity_sha256",
    "workspace_identity_sha256",
    "run_identity",
    "run_identity_sha256",
    "instruction_policy_fingerprint",
    "effective_contract_fingerprint",
    "effective_contract_sha256",
    "effective_contract_size",
    "planned_artifact",
    "plan_sha256",
}


def _codex_launch_environment(
    *, lane: Mapping[str, Any], codex_home: Mapping[str, Any]
) -> Dict[str, str]:
    environment = select_launch_environment(
        target="codex",
        source_environment={},
        bindings={"CODEX_HOME": str(codex_home["path"])},
        admitted_lane_root=Path(str(lane["path"])),
    )
    if set(environment) != {"CODEX_HOME"}:
        raise IdentityError("Codex workspace launch environment changed")
    return environment


def _build_codex_admitted_plan(
    *,
    session: str,
    run_id: str,
    lane: Mapping[str, Any],
    workspace: Mapping[str, Any],
    codex_home: Mapping[str, Any],
    argv: list[str],
) -> Dict[str, Any]:
    expected_argv = [
        EXPECTED_RESOLVED_EXECUTABLE_PATH,
        EXPECTED_UNRESTRICTED_FLAG,
        "-C",
        str(workspace["path"]),
    ]
    if argv != expected_argv:
        raise IdentityError("Codex workspace admitted argv changed")
    return build_admitted_launch_plan(
        target="codex",
        session=validate_identifier(session, "Codex admitted session"),
        run_id=validate_identifier(run_id, "Codex admitted run id"),
        repo=Path(str(workspace["path"])),
        argv=expected_argv,
        environment=_codex_launch_environment(lane=lane, codex_home=codex_home),
        admitted_lane_root=Path(str(lane["path"])),
    )


def _exact_int(value: Any, *, label: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValidationError("%s is invalid" % label)
    return value


def _validate_root_identity(value: Any, *, label: str) -> Dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _ROOT_FIELDS:
        raise ValidationError("%s identity fields are invalid" % label)
    path = value.get("path")
    if (
        not isinstance(path, str)
        or not path
        or not os.path.isabs(path)
        or os.path.normpath(path) != path
        or "\x00" in path
        or len(path) > 4096
    ):
        raise ValidationError("%s path is invalid" % label)
    result = {
        "path": path,
        "device": _exact_int(value.get("device"), label="%s device" % label),
        "inode": _exact_int(value.get("inode"), label="%s inode" % label, minimum=1),
        "uid": _exact_int(value.get("uid"), label="%s uid" % label),
        "gid": _exact_int(value.get("gid"), label="%s gid" % label),
        "mode": _exact_int(value.get("mode"), label="%s mode" % label),
        "nlink": _exact_int(value.get("nlink"), label="%s nlink" % label, minimum=1),
    }
    if result["uid"] != os.getuid() or result["mode"] != 0o700:
        raise IdentityError("%s must be current-UID 0700" % label)
    return result


def _assert_current_root(identity: Mapping[str, Any], *, label: str) -> None:
    path = Path(str(identity["path"]))
    try:
        details = path.lstat()
    except OSError as exc:
        raise IdentityError("%s is unavailable" % label) from exc
    if stat.S_ISLNK(details.st_mode) or not stat.S_ISDIR(details.st_mode):
        raise IdentityError("%s must be a non-symlink directory" % label)
    current = {
        "path": str(path),
        "device": details.st_dev,
        "inode": details.st_ino,
        "uid": details.st_uid,
        "gid": details.st_gid,
        "mode": stat.S_IMODE(details.st_mode),
        "nlink": details.st_nlink,
    }
    if any(current[key] != identity[key] for key in _ROOT_FIELDS):
        raise IdentityError("%s identity changed" % label)


def _require_absent_agents_file(workspace: Mapping[str, Any]) -> None:
    candidate = Path(str(workspace["path"])) / PLANNED_ARTIFACT
    try:
        candidate.lstat()
    except FileNotFoundError:
        return
    except OSError as exc:
        raise IdentityError("Codex workspace AGENTS.md cannot be inspected") from exc
    raise ConflictError(
        "Codex workspace AGENTS.md must be absent for create-only planning"
    )


def _validate_contract_bytes(value: bytes, manifest: Mapping[str, Any]) -> bytes:
    if not isinstance(value, bytes) or not value:
        raise ValidationError("effective contract bytes are required")
    if sha256_bytes(value) != manifest["rendered_sha256"]:
        raise IdentityError("effective contract bytes changed")
    if len(value) != manifest["byte_count"]:
        raise IdentityError("effective contract byte count changed")
    try:
        value.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValidationError("effective contract bytes must be UTF-8") from exc
    return value


def _expected_contract_identity(value: Mapping[str, Any]) -> Dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != {
        "fingerprint",
        "controller",
        "target",
        "task_profile",
    }:
        raise ValidationError("expected Codex contract identity is not exact")
    result = {
        "fingerprint": validate_sha256(
            value.get("fingerprint"), "expected contract fingerprint"
        ),
        "controller": validate_identifier(
            value.get("controller"), "expected contract controller"
        ),
        "target": value.get("target"),
        "task_profile": value.get("task_profile"),
    }
    if result["target"] != "codex" or result["task_profile"] != QUALIFICATION_PROFILE:
        raise IdentityError("expected Codex contract identity is not canonical Pass B")
    return result


def _expected_run_identity(value: Mapping[str, Any]) -> Dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != {"session", "run_id", "nonce"}:
        raise ValidationError("expected Codex run identity is not exact")
    return {
        "session": validate_identifier(value.get("session"), "expected session"),
        "run_id": validate_identifier(value.get("run_id"), "expected run id"),
        "nonce": validate_identifier(value.get("nonce"), "expected nonce"),
    }


def _validate_manifest_identities(
    manifest: Mapping[str, Any],
    *,
    workspace: Mapping[str, Any],
    expected_contract_identity: Mapping[str, Any],
    expected_run_identity: Mapping[str, Any],
) -> tuple[Dict[str, str], Dict[str, str], Dict[str, str]]:
    contract = _expected_contract_identity(expected_contract_identity)
    run = _expected_run_identity(expected_run_identity)
    if manifest.get("contract_identity") != contract:
        raise IdentityError("Codex instruction contract identity changed")
    if manifest.get("run_identity") != run:
        raise IdentityError("Codex instruction run identity changed")

    expected_workspace = {
        "fixture_fingerprint": tree_fingerprint(Path(str(workspace["path"]))),
        "workspace": "isolated_conformance_fixture",
    }
    if manifest.get("workspace_identity") != expected_workspace:
        raise IdentityError("Codex instruction workspace identity changed")
    return contract, expected_workspace, run


def _validate_launch_context(context: CodexLaunchContext) -> Dict[str, Any]:
    if not isinstance(context, CodexLaunchContext):
        raise ValidationError("Codex launch context is invalid")
    if (
        context.target != "codex"
        or context.session_profile != "regular"
        or context.version_text != EXPECTED_VERSION_TEXT
        or context.model_selection != CURRENT_DEFAULT_SELECTION
        or context.effort_selection != CURRENT_DEFAULT_SELECTION
        or context.auth_route != AUTH_ROUTE
        or context.launch_authorized is not False
        or tuple(context.blockers)
        != (*SOURCE_ONLY_BLOCKERS, MAPPING_INCOMPLETE_BLOCKER)
    ):
        raise IdentityError("Codex launch context is not the exact source-only tuple")
    public = json.loads(canonical_json_bytes(context.to_public_dict()).decode("utf-8"))
    if public.get("launch_authorized") is not False:
        raise IdentityError("Codex launch context cannot authorize launch")
    if context.argv != [context.resolved_executable_path, EXPECTED_UNRESTRICTED_FLAG]:
        raise IdentityError("Codex launch context argv changed")
    return public


def _validate_planned_artifact(
    value: Any, *, contract_sha256: str, size: int
) -> Dict[str, Any]:
    expected = {
        "artifact_id": "codex_workspace_agents",
        "relative_path": PLANNED_ARTIFACT,
        "write_mode": "create_only_if_lifecycle_is_later_proved",
        "preimage": "absent",
        "content_sha256": contract_sha256,
        "content_size": size,
    }
    if value != expected:
        raise IdentityError("Codex workspace planned artifact changed")
    return dict(expected)


def _validate_plan(value: Mapping[str, Any]) -> Dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _PLAN_FIELDS:
        raise ValidationError("Codex workspace plan fields are invalid")
    if value.get("schema") != PLAN_SCHEMA or value.get("target") != "codex":
        raise ValidationError("Codex workspace plan schema is unsupported")
    if value.get("codex_version") != EXPECTED_VERSION_TEXT:
        raise UnsupportedError("Codex workspace plan version is unsupported")
    if value.get("status") != STATUS or value.get("blockers") != list(_ALL_BLOCKERS):
        raise IdentityError("Codex workspace plan status changed")
    if value.get("launch_authorized") is not False or any(
        value.get(name) is not False
        for name in (
            "materialization_supported",
            "rollback_supported",
            "recovery_supported",
        )
    ):
        raise UnsupportedError("Codex workspace lifecycle must remain disabled")

    lane = _validate_root_identity(value.get("lane_root_identity"), label="lane root")
    workspace = _validate_root_identity(
        value.get("workspace_root_identity"), label="workspace root"
    )
    codex_home = _validate_root_identity(
        value.get("codex_home_identity"), label="CODEX_HOME"
    )
    lane_path = Path(lane["path"])
    workspace_path = Path(workspace["path"])
    home_path = Path(codex_home["path"])
    try:
        workspace_path.relative_to(lane_path)
        home_path.relative_to(lane_path)
    except ValueError as exc:
        raise IdentityError("Codex workspace plan roots escaped the lane") from exc
    if (
        workspace_path == lane_path
        or home_path == lane_path
        or paths_overlap(workspace_path, home_path)
    ):
        raise IdentityError("Codex workspace plan roots overlap")
    expected_delta = {"argv": ["-C", workspace["path"]]}
    if value.get("launch_delta") != expected_delta:
        raise IdentityError("Codex workspace launch delta changed")
    run_identity = _expected_run_identity(value.get("run_identity"))
    run_identity_sha256 = validate_sha256(
        value.get("run_identity_sha256"), "run identity sha256"
    )
    if run_identity_sha256 != sha256_bytes(canonical_json_bytes(run_identity)):
        raise IdentityError("Codex workspace run identity changed")
    admitted_value = value.get("admitted_launch_plan")
    admitted = validate_admitted_launch_plan(
        admitted_value,
        expected_target="codex",
        expected_session=run_identity["session"],
        expected_run_id=run_identity["run_id"],
    )
    expected_admitted = _build_codex_admitted_plan(
        session=admitted["session"],
        run_id=admitted["run_id"],
        lane=lane,
        workspace=workspace,
        codex_home=codex_home,
        argv=admitted["argv"],
    )
    if admitted_value != expected_admitted:
        raise IdentityError("Codex workspace admitted launch plan changed")

    effective_sha = validate_sha256(
        value.get("effective_contract_sha256"), "effective contract sha256"
    )
    effective_size = _exact_int(
        value.get("effective_contract_size"),
        label="effective contract size",
        minimum=1,
    )
    result = {
        "schema": PLAN_SCHEMA,
        "target": "codex",
        "codex_version": EXPECTED_VERSION_TEXT,
        "status": dict(STATUS),
        "blockers": list(_ALL_BLOCKERS),
        "launch_authorized": False,
        "materialization_supported": False,
        "rollback_supported": False,
        "recovery_supported": False,
        "manifest_fingerprint": validate_sha256(
            value.get("manifest_fingerprint"), "manifest fingerprint"
        ),
        "adapter_implementation_sha256": validate_sha256(
            value.get("adapter_implementation_sha256"),
            "adapter implementation sha256",
        ),
        "adapter_protocol_sha256": validate_sha256(
            value.get("adapter_protocol_sha256"), "adapter protocol sha256"
        ),
        "requested_executable_path": value.get("requested_executable_path"),
        "resolved_executable_path": value.get("resolved_executable_path"),
        "executable_sha256": validate_sha256(
            value.get("executable_sha256"), "executable sha256"
        ),
        "version_sha256": validate_sha256(
            value.get("version_sha256"), "version sha256"
        ),
        "launch_context_sha256": validate_sha256(
            value.get("launch_context_sha256"), "launch context sha256"
        ),
        "lane_root_identity": lane,
        "workspace_root_identity": workspace,
        "codex_home_identity": codex_home,
        "launch_delta": expected_delta,
        "admitted_launch_plan": expected_admitted,
        "instruction_manifest_sha256": validate_sha256(
            value.get("instruction_manifest_sha256"),
            "instruction manifest sha256",
        ),
        "contract_identity_sha256": validate_sha256(
            value.get("contract_identity_sha256"),
            "contract identity sha256",
        ),
        "workspace_identity_sha256": validate_sha256(
            value.get("workspace_identity_sha256"),
            "workspace identity sha256",
        ),
        "run_identity": run_identity,
        "run_identity_sha256": run_identity_sha256,
        "instruction_policy_fingerprint": validate_sha256(
            value.get("instruction_policy_fingerprint"),
            "instruction policy fingerprint",
        ),
        "effective_contract_fingerprint": validate_sha256(
            value.get("effective_contract_fingerprint"),
            "effective contract fingerprint",
        ),
        "effective_contract_sha256": effective_sha,
        "effective_contract_size": effective_size,
        "planned_artifact": _validate_planned_artifact(
            value.get("planned_artifact"),
            contract_sha256=effective_sha,
            size=effective_size,
        ),
    }
    for name in ("requested_executable_path", "resolved_executable_path"):
        path = result[name]
        if (
            not isinstance(path, str)
            or not path
            or not os.path.isabs(path)
            or os.path.normpath(path) != path
            or "\x00" in path
            or len(path) > 4096
        ):
            raise ValidationError("%s is invalid" % name)
    if (
        result["requested_executable_path"] != EXPECTED_REQUESTED_EXECUTABLE_PATH
        or result["resolved_executable_path"] != EXPECTED_RESOLVED_EXECUTABLE_PATH
        or result["executable_sha256"] != EXPECTED_EXECUTABLE_SHA256
        or result["version_sha256"] != EXPECTED_VERSION_SHA256
    ):
        raise IdentityError("Codex workspace executable tuple changed")
    supplied_sha = validate_sha256(value.get("plan_sha256"), "plan sha256")
    if supplied_sha != sha256_bytes(canonical_json_bytes(result)):
        raise IdentityError("Codex workspace plan fingerprint changed")
    result["plan_sha256"] = supplied_sha
    validate_bounded_json(
        result,
        max_depth=8,
        max_items=96,
        max_string=4096,
        reject_sensitive_fields=True,
    )
    return result


@dataclass(frozen=True)
class CodexWorkspacePlan:
    """Typed, body-free, disabled Codex workspace-plane plan."""

    raw: Dict[str, Any]

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "CodexWorkspacePlan":
        return cls(raw=_validate_plan(value))

    def to_dict(self) -> Dict[str, Any]:
        return json.loads(canonical_json_bytes(self.raw).decode("utf-8"))

    @property
    def plan_sha256(self) -> str:
        return self.raw["plan_sha256"]

    @property
    def planned_artifact_path(self) -> Path:
        return Path(self.raw["workspace_root_identity"]["path"]) / PLANNED_ARTIFACT


def plan_codex_workspace_plane(
    *,
    manifest_path: Path | str,
    lane_root: Path | str,
    workspace_root: Path | str,
    codex_home: Path | str,
    instruction_manifest: Mapping[str, Any],
    effective_contract: bytes,
    expected_contract_identity: Mapping[str, Any],
    expected_run_identity: Mapping[str, Any],
) -> CodexWorkspacePlan:
    """Plan one create-only candidate without writing or launching anything."""

    context = build_codex_launch_context(
        manifest_path=manifest_path,
        lane_root=lane_root,
        workspace_root=workspace_root,
        codex_home=codex_home,
    )
    public = _validate_launch_context(context)
    manifest = validate_instruction_manifest(instruction_manifest, target="codex")
    lane = _validate_root_identity(public["lane_root_identity"], label="lane root")
    workspace = _validate_root_identity(
        public["workspace_root_identity"], label="workspace root"
    )
    home = _validate_root_identity(public["codex_home_identity"], label="CODEX_HOME")
    _require_absent_agents_file(workspace)
    for identity, label in (
        (lane, "lane root"),
        (workspace, "workspace root"),
        (home, "CODEX_HOME"),
    ):
        _assert_current_root(identity, label=label)
    contract_identity, workspace_identity, run_identity = _validate_manifest_identities(
        manifest,
        workspace=workspace,
        expected_contract_identity=expected_contract_identity,
        expected_run_identity=expected_run_identity,
    )
    contract = _validate_contract_bytes(effective_contract, manifest)
    contract_sha = sha256_bytes(contract)
    value = {
        "schema": PLAN_SCHEMA,
        "target": "codex",
        "codex_version": EXPECTED_VERSION_TEXT,
        "status": dict(STATUS),
        "blockers": list(_ALL_BLOCKERS),
        "launch_authorized": False,
        "materialization_supported": False,
        "rollback_supported": False,
        "recovery_supported": False,
        "manifest_fingerprint": context.manifest_fingerprint,
        "adapter_implementation_sha256": context.adapter_fingerprint,
        "adapter_protocol_sha256": context.protocol_fingerprint,
        "requested_executable_path": context.requested_executable_path,
        "resolved_executable_path": context.resolved_executable_path,
        "executable_sha256": context.manifest_executable_sha256,
        "version_sha256": context.manifest_version_sha256,
        "launch_context_sha256": context.public_context_sha256,
        "lane_root_identity": lane,
        "workspace_root_identity": workspace,
        "codex_home_identity": home,
        "launch_delta": {"argv": ["-C", workspace["path"]]},
        "admitted_launch_plan": _build_codex_admitted_plan(
            session=run_identity["session"],
            run_id=run_identity["run_id"],
            lane=lane,
            workspace=workspace,
            codex_home=home,
            argv=[*context.argv, "-C", workspace["path"]],
        ),
        "instruction_manifest_sha256": sha256_bytes(
            canonical_json_bytes(manifest) + b"\n"
        ),
        "contract_identity_sha256": sha256_bytes(
            canonical_json_bytes(contract_identity)
        ),
        "workspace_identity_sha256": sha256_bytes(
            canonical_json_bytes(workspace_identity)
        ),
        "run_identity": run_identity,
        "run_identity_sha256": sha256_bytes(canonical_json_bytes(run_identity)),
        "instruction_policy_fingerprint": manifest["instruction_policy_fingerprint"],
        "effective_contract_fingerprint": manifest["effective_contract_fingerprint"],
        "effective_contract_sha256": contract_sha,
        "effective_contract_size": len(contract),
        "planned_artifact": {
            "artifact_id": "codex_workspace_agents",
            "relative_path": PLANNED_ARTIFACT,
            "write_mode": "create_only_if_lifecycle_is_later_proved",
            "preimage": "absent",
            "content_sha256": contract_sha,
            "content_size": len(contract),
        },
    }
    value["plan_sha256"] = sha256_bytes(canonical_json_bytes(value))
    return CodexWorkspacePlan.from_dict(value)


def revalidate_codex_workspace_plan(
    plan: CodexWorkspacePlan,
    *,
    manifest_path: Path | str,
    lane_root: Path | str,
    workspace_root: Path | str,
    codex_home: Path | str,
    instruction_manifest: Mapping[str, Any],
    effective_contract: bytes,
    expected_contract_identity: Mapping[str, Any],
    expected_run_identity: Mapping[str, Any],
) -> CodexWorkspacePlan:
    """Rebuild the disabled plan and require exact current-state identity."""

    if not isinstance(plan, CodexWorkspacePlan):
        raise ValidationError("Codex workspace plan is invalid")
    expected = CodexWorkspacePlan.from_dict(plan.to_dict())
    current = plan_codex_workspace_plane(
        manifest_path=manifest_path,
        lane_root=lane_root,
        workspace_root=workspace_root,
        codex_home=codex_home,
        instruction_manifest=instruction_manifest,
        effective_contract=effective_contract,
        expected_contract_identity=expected_contract_identity,
        expected_run_identity=expected_run_identity,
    )
    if current.plan_sha256 != expected.plan_sha256:
        raise IdentityError("Codex workspace plan changed after planning")
    return current


def _disabled_lifecycle(plan: Any) -> NoReturn:
    if isinstance(plan, CodexWorkspacePlan):
        CodexWorkspacePlan.from_dict(plan.to_dict())
    raise UnsupportedError(_LIFECYCLE_DISABLED)


def materialize_codex_workspace_plane(
    plan: CodexWorkspacePlan,
    *,
    effective_contract: Optional[bytes] = None,
) -> NoReturn:
    del effective_contract
    _disabled_lifecycle(plan)


def verify_codex_workspace_plane(
    plan: CodexWorkspacePlan,
    *,
    receipt: Optional[Mapping[str, Any]] = None,
) -> NoReturn:
    del receipt
    _disabled_lifecycle(plan)


def rollback_codex_workspace_plane(
    plan: CodexWorkspacePlan,
    *,
    exact_halt_proof: Optional[Mapping[str, Any]] = None,
) -> NoReturn:
    del exact_halt_proof
    _disabled_lifecycle(plan)


def recover_codex_workspace_plane(
    plan: CodexWorkspacePlan,
    *,
    rollback_record: Optional[Mapping[str, Any]] = None,
) -> NoReturn:
    del rollback_record
    _disabled_lifecycle(plan)


__all__ = [
    "PLAN_SCHEMA",
    "STATUS",
    "WORKSPACE_BLOCKERS",
    "CodexWorkspacePlan",
    "materialize_codex_workspace_plane",
    "plan_codex_workspace_plane",
    "recover_codex_workspace_plane",
    "revalidate_codex_workspace_plan",
    "rollback_codex_workspace_plane",
    "verify_codex_workspace_plane",
]
