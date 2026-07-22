"""Fingerprint-bound adapter capability manifests."""

from __future__ import annotations

import math
import os
import shutil
import stat
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Optional

from .authority import (
    AUTHORITY_ID,
    controller_authority_root,
    verify_qualification_attestation,
)
from .contracts import (
    MANDATORY_HARD_GATES,
    PROCESS_IDENTITY_FIELDS,
    TARGET_POPULATION_POLICY,
)
from .errors import IdentityError, UnsupportedError, ValidationError
from .instructions import validate_instruction_manifest
from .launch import validate_admitted_launch_plan, validate_public_launch_identity
from .profiles import (
    INPUT_READINESS_STRATEGY,
    OBSERVED_INPUT_TRANSPORT,
    PROMPT_TRANSPORT,
    SUBMIT_SETTLE_SECONDS,
    session_profiles_for,
    startup_settle_seconds_for,
    validate_session_profile,
)
from .safety import (
    atomic_write_json,
    canonical_json_bytes,
    ensure_within,
    read_json,
    sha256_file,
    sha256_bytes,
    validate_identifier,
    validate_pane_id,
    validate_sha256,
)


EXECUTION_FILE_FIELDS = {
    "path",
    "device",
    "inode",
    "size",
    "mtime_ns",
    "sha256",
}
EXECUTION_FIELDS = {
    "transition",
    "runtime_executable",
    "transient_executables",
    "support_files",
    "settle_timeout_seconds",
    "execution_fingerprint",
}
EXECUTION_TRANSITIONS = frozenset({"direct", "same_pid_exec"})
MAX_TRANSIENT_EXECUTABLES = 8
MAX_EXECUTION_SUPPORT_FILES = 16


def execution_file_identity(path: Path) -> Dict[str, Any]:
    """Return one exact regular-file identity for a launch execution bundle."""

    candidate = Path(path)
    if not candidate.is_absolute():
        raise ValidationError("execution file path must be absolute")
    if candidate.is_symlink() or not candidate.is_file():
        raise ValidationError("execution file must be a regular non-symlink file")
    resolved = candidate.resolve(strict=True)
    details = resolved.stat()
    return {
        "path": str(resolved),
        "device": details.st_dev,
        "inode": details.st_ino,
        "size": details.st_size,
        "mtime_ns": details.st_mtime_ns,
        "sha256": sha256_file(resolved),
    }


def validate_execution_file_identity(
    value: Any,
    label: str,
    *,
    verify_current: bool = False,
) -> Dict[str, Any]:
    """Validate one exact execution file, optionally rechecking live bytes."""

    if not isinstance(value, dict) or set(value) != EXECUTION_FILE_FIELDS:
        raise ValidationError("%s execution file fields do not match schema" % label)
    path_text = value.get("path")
    if (
        not isinstance(path_text, str)
        or not path_text
        or len(path_text) > 4096
        or "\x00" in path_text
        or not Path(path_text).is_absolute()
    ):
        raise ValidationError("%s execution file path is invalid" % label)
    for name in ("device", "inode", "size", "mtime_ns"):
        observed = value.get(name)
        if isinstance(observed, bool) or not isinstance(observed, int) or observed < 0:
            raise ValidationError("%s execution file %s is invalid" % (label, name))
    if value["device"] == 0 or value["inode"] == 0:
        raise ValidationError("%s execution file identity is invalid" % label)
    validate_sha256(value.get("sha256"), "%s execution file" % label)
    validated = dict(value)
    if verify_current:
        path = Path(path_text)
        if path.is_symlink() or not path.is_file():
            raise IdentityError("%s execution file is unavailable" % label)
        resolved = path.resolve(strict=True)
        if str(resolved) != path_text:
            raise IdentityError("%s execution file path changed" % label)
        details = resolved.stat()
        current = {
            "path": str(resolved),
            "device": details.st_dev,
            "inode": details.st_ino,
            "size": details.st_size,
            "mtime_ns": details.st_mtime_ns,
            "sha256": sha256_file(resolved),
        }
        if current != validated:
            raise IdentityError("%s execution file identity changed" % label)
    return validated


def launcher_execution_identity(executable: Dict[str, Any]) -> Dict[str, Any]:
    """Project the top-level launch file into the shared file schema."""

    return {
        "path": executable["resolved_path"],
        "device": executable["device"],
        "inode": executable["inode"],
        "size": executable["size"],
        "mtime_ns": executable["mtime_ns"],
        "sha256": executable["sha256"],
    }


def build_execution_bundle(
    *,
    launcher: Dict[str, Any],
    transition: str,
    runtime_executable: Dict[str, Any],
    transient_executables: list[Dict[str, Any]],
    support_files: list[Dict[str, Any]],
    settle_timeout_seconds: float,
) -> Dict[str, Any]:
    """Build the canonical launcher-to-runtime identity bundle."""

    core = {
        "transition": transition,
        "launcher": validate_execution_file_identity(launcher, "launcher"),
        "runtime_executable": validate_execution_file_identity(
            runtime_executable, "runtime"
        ),
        "transient_executables": [
            validate_execution_file_identity(item, "transient")
            for item in transient_executables
        ],
        "support_files": [
            validate_execution_file_identity(item, "support") for item in support_files
        ],
        "settle_timeout_seconds": settle_timeout_seconds,
    }
    bundle = {
        name: core[name]
        for name in (
            "transition",
            "runtime_executable",
            "transient_executables",
            "support_files",
            "settle_timeout_seconds",
        )
    }
    bundle["execution_fingerprint"] = sha256_bytes(canonical_json_bytes(core))
    return bundle


def direct_execution_bundle(
    executable: Dict[str, Any], *, settle_timeout_seconds: float = 2.0
) -> Dict[str, Any]:
    launcher = launcher_execution_identity(executable)
    return build_execution_bundle(
        launcher=launcher,
        transition="direct",
        runtime_executable=launcher,
        transient_executables=[],
        support_files=[],
        settle_timeout_seconds=settle_timeout_seconds,
    )


CAPABILITY_STATES = frozenset(
    {
        "unknown",
        "declared",
        "historical",
        "controller_observed",
        "controller_verified",
        "unsupported",
    }
)
BEHAVIOR_CAPABILITIES = (
    "launch",
    "send",
    "status",
    "wait",
    "checkpoint",
    "resume",
    "halt",
)
PROBE_CAPABILITIES = (
    "launch",
    "send",
    "status",
    "wait",
    "checkpoint",
    "halt",
)

QUALIFICATION_PROOF_KINDS = (
    "authorization",
    "evidence",
    "launch_plan",
    "instructions",
    "halt",
    "ready",
    "followup",
    "review",
    "acceptance",
)

_RECEIPT_FIELDS = {
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
    "instruction_policy_fingerprint",
    "capabilities",
    "accepted_checkpoint_id",
    "acceptance_sha256",
    "halt_receipt_sha256",
    "proof_refs",
    "controller_attestation",
}

_ACCEPTED_EVIDENCE_FIELDS = {
    "schema_version",
    "run_id",
    "target",
    "controller",
    "profile",
    "session_profile",
    "campaign_id",
    "goal_fingerprint",
    "authorization_sha256",
    "manifest_fingerprint",
    "executable_fingerprint",
    "execution_fingerprint",
    "version_fingerprint",
    "platform_fingerprint",
    "adapter_fingerprint",
    "protocol_fingerprint",
    "yolo_mapping_sha256",
    "launch_argv_sha256",
    "launch_plan_sha256",
    "launch_identity",
    "input_transport",
    "input_readiness_strategy",
    "startup_settle_seconds",
    "submit_settle_seconds",
    "payload_argv_absent",
    "instruction_wrapper",
    "active_target_processes_before_launch",
    "active_target_processes_after_halt",
    "target_population_policy",
    "observed_target_descendants",
    "last_target_population",
    "parallel_target_override",
    "protected_session",
    "parallel_isolation",
    "campaign_probe_lock",
    "tmux",
    "process",
    "ready",
    "followup",
    "fixture_fingerprint_before",
    "fixture_fingerprint_after",
    "review_sha256",
    "acceptance_sha256",
    "halt_sha256",
    "result",
}

_PROCESS_FIELDS = PROCESS_IDENTITY_FIELDS

_INSTRUCTION_WRAPPER_FIELDS = {
    "manifest_sha256",
    "instruction_policy_fingerprint",
    "effective_contract_fingerprint",
    "rendered_sha256",
    "instruction_plane",
    "session_profile",
    "delivery_transport",
}


def _verify_qualification_instruction_authority(
    *,
    instruction_manifest: Dict[str, Any],
    receipt: Dict[str, Any],
    evidence: Dict[str, Any],
    ready_identity: Dict[str, Any],
    review: Dict[str, Any],
    review_summary: Dict[str, Any],
) -> None:
    expected = {
        "contract_identity": {
            "fingerprint": review["contract_fingerprint"],
            "controller": receipt["controller"],
            "target": receipt["target"],
            "task_profile": "source-free-pass-b-v1",
        },
        "workspace_identity": {
            "fixture_fingerprint": evidence["fixture_fingerprint_before"],
            "workspace": "isolated_conformance_fixture",
        },
        "run_identity": {
            "session": ready_identity["session"],
            "run_id": receipt["run_id"],
            "nonce": ready_identity["nonce"],
        },
        "orchestration_contract": {
            "mutation_owner": "none",
            "allowed_modes": ["read", "test"],
            "hard_gates": sorted(MANDATORY_HARD_GATES),
        },
        "runtime_binding": {"model": "default", "effort": "default"},
    }
    if any(instruction_manifest.get(name) != value for name, value in expected.items()):
        raise ValidationError("qualification instruction authority is incomplete")
    if review_summary.get("initial_payload_sha256") != instruction_manifest.get(
        "rendered_sha256"
    ):
        raise ValidationError(
            "qualification delivered payload does not match instruction manifest"
        )


def _qualification_artifacts(path: Path, receipt: Dict[str, Any]) -> Dict[str, Path]:
    refs = receipt.get("proof_refs")
    if not isinstance(refs, list) or len(refs) != len(QUALIFICATION_PROOF_KINDS):
        raise ValidationError("qualification proof references are incomplete")
    root = path.resolve(strict=True).parent
    artifacts: Dict[str, Path] = {}
    for reference in refs:
        if not isinstance(reference, dict) or set(reference) != {
            "kind",
            "path",
            "sha256",
        }:
            raise ValidationError(
                "qualification proof reference fields do not match schema"
            )
        kind = reference.get("kind")
        relative_text = reference.get("path")
        if kind not in QUALIFICATION_PROOF_KINDS or kind in artifacts:
            raise ValidationError("qualification proof reference kind is invalid")
        if (
            not isinstance(relative_text, str)
            or not relative_text
            or len(relative_text) > 1000
            or relative_text.startswith(".")
            or "\\" in relative_text
        ):
            raise ValidationError("qualification proof reference path is invalid")
        relative = PurePosixPath(relative_text)
        if relative.is_absolute() or ".." in relative.parts or not relative.parts:
            raise ValidationError("qualification proof reference escapes its run root")
        validate_sha256(reference.get("sha256"), "qualification proof reference")
        artifact = ensure_within(root.joinpath(*relative.parts), root, must_exist=True)
        if artifact.is_symlink() or not artifact.is_file():
            raise ValidationError("qualification proof reference is not a regular file")
        if sha256_file(artifact, max_bytes=131072) != reference["sha256"]:
            raise ValidationError("qualification proof artifact fingerprint changed")
        artifacts[kind] = artifact
    if set(artifacts) != set(QUALIFICATION_PROOF_KINDS):
        raise ValidationError("qualification proof reference kinds are incomplete")
    return artifacts


def _validated_process_record(value: Any, label: str) -> Dict[str, Any]:
    if not isinstance(value, dict) or set(value) != _PROCESS_FIELDS:
        raise ValidationError("%s process identity fields do not match schema" % label)
    if (
        value.get("identity_version") != 2
        or isinstance(value.get("pid"), bool)
        or not isinstance(value.get("pid"), int)
        or value["pid"] <= 1
        or not isinstance(value.get("start"), str)
        or not value["start"]
        or len(value["start"]) > 200
        or not isinstance(value.get("kernel_birth_id"), str)
        or not value["kernel_birth_id"]
        or len(value["kernel_birth_id"]) > 200
        or any(character in value["kernel_birth_id"] for character in "\x00\n\r")
        or not isinstance(value.get("command"), str)
        or not value["command"]
        or len(value["command"]) > 1000
        or not isinstance(value.get("executable_path"), str)
        or not Path(value["executable_path"]).is_absolute()
        or isinstance(value.get("device"), bool)
        or not isinstance(value.get("device"), int)
        or value["device"] < 0
        or isinstance(value.get("inode"), bool)
        or not isinstance(value.get("inode"), int)
        or value["inode"] < 0
    ):
        raise ValidationError("%s process identity is invalid" % label)
    return value


def _validated_process_population(
    value: Any, label: str, *, max_items: int = 32
) -> list[Dict[str, Any]]:
    if not isinstance(value, list) or len(value) > max_items:
        raise ValidationError("%s process population is invalid" % label)
    records = [_validated_process_record(item, label) for item in value]
    pids = [item["pid"] for item in records]
    if len(pids) != len(set(pids)) or pids != sorted(pids):
        raise ValidationError(
            "%s process population order or identity is invalid" % label
        )
    return records


def _validated_ancestry_chain(
    value: Any,
    label: str,
    *,
    registered: Dict[str, Any],
    protected_pids: set[int],
) -> list[Dict[str, Any]]:
    if not isinstance(value, list) or not 2 <= len(value) <= 65:
        raise ValidationError("%s ancestry chain is invalid" % label)
    nodes = []
    pids = []
    for item in value:
        if (
            not isinstance(item, dict)
            or set(item) != {"process", "parent_pid"}
            or isinstance(item.get("parent_pid"), bool)
            or not isinstance(item.get("parent_pid"), int)
            or item["parent_pid"] < 0
        ):
            raise ValidationError("%s ancestry node is invalid" % label)
        process = _validated_process_record(item.get("process"), label)
        nodes.append({"process": process, "parent_pid": item["parent_pid"]})
        pids.append(process["pid"])
    if (
        len(pids) != len(set(pids))
        or nodes[-1]["process"] != registered
        or any(node["process"]["pid"] in protected_pids for node in nodes[1:-1])
        or any(
            child["parent_pid"] != parent["process"]["pid"]
            for child, parent in zip(nodes, nodes[1:])
        )
    ):
        raise ValidationError("%s ancestry edge identity is invalid" % label)
    return nodes


def _validate_ancestry_node_coherence(
    chains: list[list[Dict[str, Any]]], label: str
) -> None:
    nodes_by_pid: Dict[int, Dict[str, Any]] = {}
    for chain in chains:
        for node in chain:
            pid = node["process"]["pid"]
            prior = nodes_by_pid.get(pid)
            if prior is not None and prior != node:
                raise ValidationError("%s ancestry node identity conflicts" % label)
            nodes_by_pid[pid] = node


def verify_qualification_receipt(
    path: Path,
    *,
    _authority_root: Optional[Path] = None,
    _current_manifest: Optional["AdapterManifest"] = None,
    _server_process_fn: Optional[Any] = None,
    _tmux_factory: Optional[Any] = None,
) -> Dict[str, Any]:
    """Verify an accepted receipt and every immutable proof artifact it binds."""

    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValidationError("qualification receipt is unavailable or a symlink")
    receipt = read_json(path, max_bytes=131072, reject_sensitive_fields=True)
    if set(receipt) != _RECEIPT_FIELDS or receipt.get("schema_version") != 1:
        raise ValidationError("qualification receipt fields do not match schema")
    if (
        receipt.get("kind") != "real_harness_conformance"
        or receipt.get("result") != "accepted"
    ):
        raise ValidationError(
            "qualification receipt is not an accepted real-harness run"
        )
    if receipt.get("target") not in {"agy", "cursor", "claude", "codex", "grok"}:
        raise ValidationError("qualification receipt target is invalid")
    validate_session_profile(receipt["target"], receipt.get("session_profile"))
    validate_identifier(receipt.get("run_id"), "qualification run id")
    validate_identifier(receipt.get("controller"), "qualification controller")
    validate_identifier(receipt.get("campaign_id"), "qualification campaign id")
    for name in (
        "executable_fingerprint",
        "execution_fingerprint",
        "version_fingerprint",
        "platform_fingerprint",
        "adapter_fingerprint",
        "protocol_fingerprint",
        "yolo_mapping_sha256",
        "launch_plan_sha256",
        "instruction_policy_fingerprint",
        "accepted_checkpoint_id",
        "acceptance_sha256",
        "halt_receipt_sha256",
        "goal_fingerprint",
    ):
        validate_sha256(receipt.get(name), name.replace("_", " "))
    capabilities = receipt.get("capabilities")
    if capabilities != list(PROBE_CAPABILITIES):
        raise ValidationError("qualification capability receipt is invalid")

    receipt_core = dict(receipt)
    attestation = receipt_core.pop("controller_attestation")
    verify_qualification_attestation(
        receipt_core,
        attestation,
        authority_root=_authority_root,
    )

    if _current_manifest is None:
        from .census import adapter_implementation_fingerprint, census_target

        current_manifest = census_target(
            receipt["target"], adapter_implementation_fingerprint()
        )
    else:
        current_manifest = _current_manifest
    if current_manifest.target != receipt["target"]:
        raise IdentityError("qualification current target identity mismatch")
    current = current_manifest.raw
    current_identities = {
        "executable_fingerprint": current["executable"]["sha256"],
        "execution_fingerprint": current["execution"]["execution_fingerprint"],
        "version_fingerprint": current["executable"]["version_sha256"],
        "platform_fingerprint": sha256_bytes(canonical_json_bytes(current["platform"])),
        "adapter_fingerprint": current["adapter_fingerprint"],
        "protocol_fingerprint": current["protocol_fingerprint"],
        "yolo_mapping_sha256": sha256_bytes(
            canonical_json_bytes(current["yolo_mapping"])
        ),
    }
    for name, observed in current_identities.items():
        if receipt.get(name) != observed:
            raise IdentityError(
                "qualification is stale for the current controller identity: %s" % name
            )

    state_path = path.resolve(strict=True).parent / "state.json"
    terminal_state = read_json(
        state_path,
        max_bytes=131072,
        reject_sensitive_fields=True,
    )
    if (
        terminal_state.get("schema_version") != 1
        or terminal_state.get("run_id") != receipt["run_id"]
        or terminal_state.get("target") != receipt["target"]
        or terminal_state.get("controller") != receipt["controller"]
        or terminal_state.get("profile") != "source-free-pass-b-v1"
        or terminal_state.get("session_profile") != receipt["session_profile"]
        or terminal_state.get("phase") != "complete"
        or terminal_state.get("result") != "accepted"
        or terminal_state.get("blocker") is not None
        or terminal_state.get("receipt_sha256") != sha256_file(path, max_bytes=131072)
    ):
        raise ValidationError(
            "qualification receipt lacks its terminal lifecycle commit"
        )

    artifacts = _qualification_artifacts(path, receipt)
    authorization = read_json(
        artifacts["authorization"], max_bytes=65536, reject_sensitive_fields=True
    )
    evidence = read_json(
        artifacts["evidence"], max_bytes=131072, reject_sensitive_fields=True
    )
    launch_plan = validate_admitted_launch_plan(
        read_json(
            artifacts["launch_plan"],
            max_bytes=131072,
            reject_sensitive_fields=True,
        ),
        expected_target=receipt["target"],
        expected_session=terminal_state.get("session"),
        expected_run_id=receipt["run_id"],
    )
    instruction_manifest = validate_instruction_manifest(
        read_json(
            artifacts["instructions"],
            max_bytes=131072,
            reject_sensitive_fields=True,
        ),
        target=receipt["target"],
    )
    halt = read_json(artifacts["halt"], max_bytes=65536, reject_sensitive_fields=True)
    review = read_json(
        artifacts["review"], max_bytes=131072, reject_sensitive_fields=True
    )
    acceptance = read_json(
        artifacts["acceptance"], max_bytes=131072, reject_sensitive_fields=True
    )
    if (
        set(evidence) != _ACCEPTED_EVIDENCE_FIELDS
        or evidence.get("schema_version") != 1
    ):
        raise ValidationError("qualification evidence fields do not match schema")
    if (
        evidence.get("profile") != "source-free-pass-b-v1"
        or evidence.get("session_profile") != receipt["session_profile"]
        or evidence.get("input_transport") != OBSERVED_INPUT_TRANSPORT
        or evidence.get("input_readiness_strategy") != INPUT_READINESS_STRATEGY
        or evidence.get("startup_settle_seconds")
        != startup_settle_seconds_for(receipt["target"])
        or evidence.get("submit_settle_seconds") != SUBMIT_SETTLE_SECONDS
        or evidence.get("payload_argv_absent") is not True
    ):
        raise ValidationError("qualification evidence transport contract is invalid")
    launch_identity = validate_public_launch_identity(
        evidence.get("launch_identity"),
        target=receipt["target"],
    )
    if launch_identity != launch_plan["launch_identity"]:
        raise ValidationError(
            "qualification launch identity differs from its admitted plan"
        )
    observed_plan_sha = sha256_file(artifacts["launch_plan"], max_bytes=131072)
    if (
        evidence.get("launch_plan_sha256") != observed_plan_sha
        or receipt.get("launch_plan_sha256") != observed_plan_sha
    ):
        raise ValidationError("qualification launch plan fingerprint mismatch")
    if (
        evidence.get("launch_argv_sha256")
        != launch_plan["launch_identity"]["argv_sha256"]
    ):
        raise ValidationError(
            "qualification launch argv differs from its admitted plan"
        )
    expected_fixture = artifacts["ready"].resolve(strict=True).parent.parent
    if launch_plan["cwd"] != str(expected_fixture):
        raise ValidationError(
            "qualification launch cwd differs from its admitted fixture"
        )
    if launch_plan["argv"] != current["yolo_mapping"]["launch_argv"]:
        raise ValidationError(
            "qualification launch argv differs from the current mapping"
        )
    wrapper = evidence.get("instruction_wrapper")
    if not isinstance(wrapper, dict) or set(wrapper) != _INSTRUCTION_WRAPPER_FIELDS:
        raise ValidationError("qualification instruction wrapper fields are invalid")
    expected_wrapper = {
        "manifest_sha256": sha256_file(artifacts["instructions"], max_bytes=131072),
        "instruction_policy_fingerprint": instruction_manifest[
            "instruction_policy_fingerprint"
        ],
        "effective_contract_fingerprint": instruction_manifest[
            "effective_contract_fingerprint"
        ],
        "rendered_sha256": instruction_manifest["rendered_sha256"],
        "instruction_plane": instruction_manifest["instruction_plane"],
        "session_profile": instruction_manifest["session_profile"],
        "delivery_transport": instruction_manifest["delivery_transport"],
    }
    if wrapper != expected_wrapper:
        raise ValidationError("qualification instruction wrapper identity changed")
    if (
        receipt["instruction_policy_fingerprint"]
        != instruction_manifest["instruction_policy_fingerprint"]
        or instruction_manifest["target"] != receipt["target"]
        or instruction_manifest["session_profile"] != receipt["session_profile"]
        or instruction_manifest["instruction_plane"] != "initial_message_wrapper"
        or instruction_manifest["delivery_transport"]["body_in_argv"] is not False
        or instruction_manifest["delivery_transport"]["materialization"]
        != "memory_only"
        or instruction_manifest["delivery_transport"]["native_config_writes"] != []
    ):
        raise ValidationError("qualification instruction wrapper contract is invalid")
    instruction_contract = instruction_manifest["contract_identity"]
    instruction_run = instruction_manifest["run_identity"]
    if (
        instruction_contract.get("controller") != receipt["controller"]
        or instruction_contract.get("target") != receipt["target"]
        or instruction_run.get("run_id") != receipt["run_id"]
        or instruction_run.get("session") != terminal_state.get("session")
    ):
        raise ValidationError("qualification instruction authority is invalid")
    if (
        terminal_state.get("tmux") != evidence.get("tmux")
        or terminal_state.get("process") != evidence.get("process")
        or terminal_state.get("followup_checkpoint_id")
        != receipt["accepted_checkpoint_id"]
    ):
        raise ValidationError("qualification terminal state identity mismatch")
    for name in (
        "authorization_sha256",
        "manifest_fingerprint",
        "execution_fingerprint",
        "launch_argv_sha256",
        "launch_plan_sha256",
        "fixture_fingerprint_before",
        "fixture_fingerprint_after",
        "review_sha256",
        "acceptance_sha256",
        "halt_sha256",
    ):
        validate_sha256(evidence.get(name), "qualification evidence %s" % name)
    if evidence["fixture_fingerprint_before"] != evidence["fixture_fingerprint_after"]:
        raise ValidationError("qualification fixture drifted")
    if (
        sha256_file(artifacts["authorization"], max_bytes=65536)
        != evidence["authorization_sha256"]
    ):
        raise ValidationError("qualification authorization fingerprint mismatch")
    authorization_fields = {
        "schema_version",
        "campaign_id",
        "operator_identity",
        "controller",
        "goal",
        "acknowledged_at",
        "authorization",
        "allowed_actions",
        "hard_gates",
    }
    execution_authorization = authorization.get("authorization", {})
    execution_fields = {
        "harnesses",
        "trust_profile",
        "disable_harness_sandbox_where_exposed",
        "ordinary_configured_model_provider_traffic",
        "scope",
    }
    if (
        not isinstance(authorization, dict)
        or set(authorization) != authorization_fields
        or authorization.get("schema_version") != 1
        or authorization.get("campaign_id") != evidence.get("campaign_id")
        or authorization.get("campaign_id") != receipt["campaign_id"]
        or authorization.get("controller") != receipt["controller"]
        or sha256_bytes(canonical_json_bytes(authorization.get("goal")))
        != receipt["goal_fingerprint"]
        or not isinstance(execution_authorization, dict)
        or set(execution_authorization)
        not in (execution_fields, execution_fields | {"parallel_target_override"})
        or receipt["target"] not in execution_authorization.get("harnesses", [])
        or execution_authorization.get("trust_profile") != "unrestricted_required"
        or execution_authorization.get("disable_harness_sandbox_where_exposed")
        is not True
        or execution_authorization.get("ordinary_configured_model_provider_traffic")
        is not True
        or execution_authorization.get("scope")
        != "bounded Puppet implementation and conformance campaign only"
        or authorization.get("allowed_actions")
        != [
            "read",
            "test",
            "mutate_isolated_worktrees",
            "local_commit",
            "internal_between_session_promotion",
        ]
        or authorization.get("hard_gates")
        != [
            "merge",
            "push",
            "pull_request_creation",
            "release",
            "deploy",
            "publish",
            "global_install",
            "external_send",
            "spend",
            "delete_or_archive",
            "account_or_security_change",
            "secret_or_auth_data_access",
            "interference_with_preexisting_processes_or_sessions",
        ]
    ):
        raise ValidationError("qualification campaign authorization identity mismatch")
    active_before = _validated_process_population(
        evidence.get("active_target_processes_before_launch"), "pre-launch"
    )
    active_after = _validated_process_population(
        evidence.get("active_target_processes_after_halt"), "post-halt"
    )
    if active_before != active_after:
        raise ValidationError("qualification protected process population changed")
    override = authorization.get("authorization", {}).get("parallel_target_override")
    if evidence.get("parallel_target_override") is True:
        if (
            not isinstance(override, dict)
            or override.get("target") != receipt["target"]
            or override.get("isolation") != "unique_private_tmux_socket_and_session"
            or override.get("failure_cleanup_scope") != "exact_new_target_only"
            or override.get("protected_session") != evidence.get("protected_session")
            or override.get("protected_processes") != active_before
            or evidence.get("parallel_isolation")
            != "unique_private_tmux_socket_and_session"
            or not active_before
        ):
            raise ValidationError("qualification parallel authorization mismatch")
    elif (
        evidence.get("parallel_target_override") is not False
        or evidence.get("protected_session") is not None
        or evidence.get("parallel_isolation") is not None
        or active_before
    ):
        raise ValidationError("qualification unapproved parallel target evidence")

    if evidence["execution_fingerprint"] != receipt["execution_fingerprint"]:
        raise ValidationError("qualification execution fingerprint mismatch")
    current_manifest.verify_execution_files()
    process = _validated_process_record(evidence.get("process"), "target")
    current_manifest.verify_process_executable(process)
    raw_descendants = evidence.get("observed_target_descendants")
    if not isinstance(raw_descendants, list) or len(raw_descendants) > 32:
        raise ValidationError("observed target descendants are invalid")
    last_population = evidence.get("last_target_population")
    if (
        evidence.get("target_population_policy") != TARGET_POPULATION_POLICY
        or not isinstance(last_population, dict)
        or set(last_population)
        != {"policy", "processes", "ancestry_chains", "accepted"}
        or last_population.get("policy") != TARGET_POPULATION_POLICY
        or last_population.get("accepted") is not True
    ):
        raise ValidationError("qualification target population policy is invalid")
    last_processes = _validated_process_population(
        last_population.get("processes"),
        "last target population",
        max_items=64,
    )
    expected_population = sorted(
        [*active_before, process], key=lambda item: item["pid"]
    )
    last_by_pid = {item["pid"]: item for item in last_processes}
    if any(last_by_pid.get(item["pid"]) != item for item in expected_population):
        raise ValidationError("qualification target population root identity changed")
    expected_pids = {item["pid"] for item in expected_population}
    protected_pids = {item["pid"] for item in active_before}
    last_extras = [item for item in last_processes if item["pid"] not in expected_pids]
    executable_identity = {
        name: process[name] for name in ("executable_path", "device", "inode")
    }
    descendant_observations = []
    descendant_pids = set()
    for item in raw_descendants:
        if not isinstance(item, dict) or set(item) != {"process", "ancestry_chain"}:
            raise ValidationError("observed target descendant fields are invalid")
        descendant = _validated_process_record(
            item.get("process"), "observed target descendant"
        )
        chain = _validated_ancestry_chain(
            item.get("ancestry_chain"),
            "observed target descendant",
            registered=process,
            protected_pids=protected_pids,
        )
        if (
            chain[0]["process"] != descendant
            or descendant["pid"] in descendant_pids
            or descendant["pid"] in expected_pids
            or {
                name: descendant[name]
                for name in ("executable_path", "device", "inode")
            }
            != executable_identity
        ):
            raise ValidationError("qualification target descendant identity is invalid")
        descendant_pids.add(descendant["pid"])
        descendant_observations.append({"process": descendant, "ancestry_chain": chain})
    if descendant_observations != sorted(
        descendant_observations, key=lambda item: item["process"]["pid"]
    ):
        raise ValidationError("qualification target descendant order is invalid")
    raw_chains = last_population.get("ancestry_chains")
    if not isinstance(raw_chains, list) or len(raw_chains) > 32:
        raise ValidationError("qualification target ancestry evidence is invalid")
    chains = [
        _validated_ancestry_chain(
            item,
            "last target population",
            registered=process,
            protected_pids=protected_pids,
        )
        for item in raw_chains
    ]
    _validate_ancestry_node_coherence(chains, "last target population")
    observed_by_pid = {item["process"]["pid"]: item for item in descendant_observations}
    last_extra_by_pid = {item["pid"]: item for item in last_extras}
    if (
        chains != sorted(chains, key=lambda chain: chain[0]["process"]["pid"])
        or len(chains) != len(last_extras)
        or {chain[0]["process"]["pid"] for chain in chains}
        != {item["pid"] for item in last_extras}
        or any(
            observed_by_pid.get(chain[0]["process"]["pid"], {}).get("ancestry_chain")
            != chain
            for chain in chains
        )
        or any(
            last_extra_by_pid.get(chain[0]["process"]["pid"]) != chain[0]["process"]
            for chain in chains
        )
        or any(item["pid"] not in descendant_pids for item in last_extras)
    ):
        raise ValidationError("qualification target ancestry evidence is invalid")
    tmux = evidence.get("tmux")
    if not isinstance(tmux, dict) or set(tmux) != {
        "socket",
        "session",
        "target_id",
        "socket_identity",
        "server_identity",
        "tmux_binary_identity",
    }:
        raise ValidationError("qualification tmux identity fields do not match schema")
    validate_identifier(tmux.get("session"), "qualification tmux session")
    validate_pane_id(tmux.get("target_id"))
    socket_path = Path(tmux.get("socket", ""))
    socket_identity = tmux.get("socket_identity")
    if (
        not socket_path.is_absolute()
        or socket_path.is_symlink()
        or not socket_path.exists()
        or not isinstance(socket_identity, dict)
        or set(socket_identity) != {"device", "inode", "uid", "mode"}
    ):
        raise ValidationError("qualification tmux socket identity is invalid")
    socket_details = socket_path.stat()
    if (
        not stat.S_ISSOCK(socket_details.st_mode)
        or socket_details.st_uid != os.getuid()
        or stat.S_IMODE(socket_details.st_mode) & 0o077
        or socket_identity
        != {
            "device": socket_details.st_dev,
            "inode": socket_details.st_ino,
            "uid": socket_details.st_uid,
            "mode": stat.S_IMODE(socket_details.st_mode),
        }
    ):
        raise ValidationError("qualification tmux socket fingerprint changed")
    tmux_binary = tmux.get("tmux_binary_identity")
    expected_tmux_binary_fields = {
        "path",
        "device",
        "inode",
        "uid",
        "gid",
        "mode",
        "size",
        "sha256",
        "version",
    }
    if (
        not isinstance(tmux_binary, dict)
        or set(tmux_binary) != expected_tmux_binary_fields
        or not isinstance(tmux_binary.get("path"), str)
        or not Path(tmux_binary["path"]).is_absolute()
        or not isinstance(tmux_binary.get("version"), str)
        or not tmux_binary["version"]
        or len(tmux_binary["version"]) > 200
    ):
        raise ValidationError("qualification tmux executable identity is invalid")
    validate_sha256(tmux_binary.get("sha256"), "tmux executable")
    tmux_binary_path = Path(tmux_binary["path"])
    if tmux_binary_path.is_symlink() or not tmux_binary_path.is_file():
        raise ValidationError("qualification tmux executable is unavailable")
    tmux_binary_details = tmux_binary_path.stat()
    observed_tmux_binary = {
        "path": str(tmux_binary_path.resolve(strict=True)),
        "device": tmux_binary_details.st_dev,
        "inode": tmux_binary_details.st_ino,
        "uid": tmux_binary_details.st_uid,
        "gid": tmux_binary_details.st_gid,
        "mode": stat.S_IMODE(tmux_binary_details.st_mode),
        "size": tmux_binary_details.st_size,
        "sha256": sha256_file(tmux_binary_path),
        "version": tmux_binary["version"],
    }
    if observed_tmux_binary != tmux_binary:
        raise ValidationError("qualification tmux executable fingerprint changed")
    server = _validated_process_record(tmux.get("server_identity"), "tmux server")
    if (
        Path(server["executable_path"]).resolve(strict=True) != tmux_binary_path
        or server["device"] != tmux_binary["device"]
        or server["inode"] != tmux_binary["inode"]
    ):
        raise ValidationError("qualification tmux server identity mismatch")
    if _server_process_fn is None:
        from .registry import process_birth_identity

        server_process_fn = process_birth_identity
    else:
        server_process_fn = _server_process_fn
    if server_process_fn(server["pid"]) != server:
        raise ValidationError("qualification tmux server birth identity changed")
    if _tmux_factory is None:
        from .tmux import TmuxController

        tmux_controller = TmuxController(socket_path.parent)
    else:
        tmux_controller = _tmux_factory(socket_path.parent)
    tmux_controller.assert_tmux_binary_identity(tmux_binary)
    tmux_controller.bind_server_identity(socket_path, server)
    terminal_tmux = tmux_controller.metadata_for_session(
        socket=socket_path,
        session=tmux["session"],
        server_identity=server,
    )
    if (
        terminal_tmux.get("session") != tmux["session"]
        or terminal_tmux.get("pane") != tmux["target_id"]
        or terminal_tmux.get("pane_pid") != process["pid"]
        or terminal_tmux.get("pane_dead") is not True
    ):
        raise ValidationError("qualification terminal tmux identity changed")
    lock = evidence.get("campaign_probe_lock")
    if not isinstance(lock, dict) or set(lock) != {
        "authority_id",
        "path",
        "device",
        "inode",
        "uid",
        "mode",
    }:
        raise ValidationError("qualification campaign lock identity is invalid")
    lock_path = Path(lock.get("path", ""))
    authority_root = controller_authority_root(_authority_root)
    expected_lock_paths = {
        authority_root / "real-harness.lock",
        authority_root / ("real-harness.%s.lock" % receipt["target"]),
    }
    if (
        lock.get("authority_id") != AUTHORITY_ID
        or lock_path not in expected_lock_paths
        or not lock_path.is_absolute()
        or lock_path.is_symlink()
        or not lock_path.is_file()
    ):
        raise ValidationError("qualification campaign lock is unavailable")
    lock_details = lock_path.stat()
    if (
        lock_details.st_uid != os.getuid()
        or stat.S_IMODE(lock_details.st_mode) & 0o077
        or lock
        != {
            "authority_id": AUTHORITY_ID,
            "path": str(lock_path.resolve(strict=True)),
            "device": lock_details.st_dev,
            "inode": lock_details.st_ino,
            "uid": lock_details.st_uid,
            "mode": stat.S_IMODE(lock_details.st_mode),
        }
    ):
        raise ValidationError("qualification campaign lock fingerprint changed")
    for name in (
        "run_id",
        "target",
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
    ):
        if evidence.get(name) != receipt.get(name):
            raise ValidationError("qualification evidence identity mismatch: %s" % name)
    if evidence.get("result") != "accepted":
        raise ValidationError("qualification evidence is not accepted")
    if evidence.get("halt_sha256") != receipt["halt_receipt_sha256"]:
        raise ValidationError("qualification halt cross-reference mismatch")
    if evidence.get("acceptance_sha256") != receipt["acceptance_sha256"]:
        raise ValidationError("qualification acceptance cross-reference mismatch")
    if (
        sha256_file(artifacts["halt"], max_bytes=65536)
        != receipt["halt_receipt_sha256"]
    ):
        raise ValidationError("qualification halt receipt mismatch")
    if (
        sha256_file(artifacts["acceptance"], max_bytes=131072)
        != receipt["acceptance_sha256"]
    ):
        raise ValidationError("qualification acceptance receipt mismatch")

    from .handoffs import validate_handoff

    ready = validate_handoff(
        artifacts["ready"],
        allowed_roots=[path.resolve(strict=True).parent],
        expected={
            "session": evidence.get("tmux", {}).get("session"),
            "run_id": receipt["run_id"],
            "executable_fingerprint": receipt["executable_fingerprint"],
            "execution_fingerprint": receipt["execution_fingerprint"],
            "adapter_fingerprint": receipt["adapter_fingerprint"],
            "protocol_fingerprint": receipt["protocol_fingerprint"],
            "phase": "ready",
            "sequence": 0,
        },
    )
    followup = validate_handoff(
        artifacts["followup"],
        allowed_roots=[path.resolve(strict=True).parent],
        expected={
            "session": ready.identity["session"],
            "run_id": receipt["run_id"],
            "nonce": ready.identity["nonce"],
            "executable_fingerprint": receipt["executable_fingerprint"],
            "execution_fingerprint": receipt["execution_fingerprint"],
            "adapter_fingerprint": receipt["adapter_fingerprint"],
            "protocol_fingerprint": receipt["protocol_fingerprint"],
            "phase": "followup",
            "sequence": 1,
            "prior_checkpoint_sha256": ready.artifact_sha256,
        },
    )
    if followup.checkpoint_id != receipt["accepted_checkpoint_id"]:
        raise ValidationError("qualification accepted checkpoint mismatch")
    if (
        ready.data.get("claims")
        != [{"id": "source_free_contract_acknowledged", "status": "ready"}]
        or followup.data.get("claims")
        != [{"id": "source_free_contract_acknowledged", "status": "followup"}]
        or any(
            handoff.data.get(name) != []
            for handoff in (ready, followup)
            for name in ("evidence_refs", "decisions_requested", "limitations")
        )
    ):
        raise ValidationError("qualification handoff semantic acknowledgement mismatch")
    for label, handoff in (("ready", ready), ("followup", followup)):
        reference = evidence.get(label)
        if not isinstance(reference, dict) or not isinstance(
            reference.get("path"), str
        ):
            raise ValidationError(
                "qualification %s evidence reference mismatch" % label
            )
        reference_path = ensure_within(
            Path(reference["path"]), path.resolve(strict=True).parent, must_exist=True
        )
        if (
            reference.get("checkpoint_id") != handoff.checkpoint_id
            or reference.get("artifact_sha256") != handoff.artifact_sha256
            or reference_path != handoff.path
        ):
            raise ValidationError(
                "qualification %s evidence reference mismatch" % label
            )
    expected_review_fields = {
        "schema_version",
        "timestamp",
        "actor",
        "target",
        "contract_fingerprint",
        "checkpoint_id",
        "checkpoint_kind",
        "checkpoint_identity",
        "artifact_sha256",
        "verdict",
        "evidence_sha256",
        "evidence_summary",
    }
    if (
        set(review) != expected_review_fields
        or review.get("schema_version") != 1
        or review.get("actor") != receipt["controller"]
        or review.get("target") != receipt["target"]
        or review.get("checkpoint_id") != followup.checkpoint_id
        or review.get("checkpoint_kind") != "conformance"
        or review.get("checkpoint_identity") != followup.identity
        or review.get("artifact_sha256") != followup.artifact_sha256
        or review.get("verdict") != "conformance_accept"
    ):
        raise ValidationError("qualification review identity mismatch")
    review_summary = review.get("evidence_summary")
    if (
        not isinstance(review_summary, dict)
        or set(review_summary)
        != {
            "classification",
            "findings",
            "observed_capabilities",
            "fixture_fingerprint",
            "initial_payload_sha256",
            "followup_payload_sha256",
        }
        or review_summary.get("classification") != "clean"
        or review_summary.get("findings") != []
        or review_summary.get("observed_capabilities") != list(PROBE_CAPABILITIES)
        or review_summary.get("fixture_fingerprint")
        != evidence["fixture_fingerprint_before"]
    ):
        raise ValidationError("qualification review evidence summary mismatch")
    validate_sha256(review_summary.get("initial_payload_sha256"), "initial payload")
    validate_sha256(review_summary.get("followup_payload_sha256"), "followup payload")
    _verify_qualification_instruction_authority(
        instruction_manifest=instruction_manifest,
        receipt=receipt,
        evidence=evidence,
        ready_identity=ready.identity,
        review=review,
        review_summary=review_summary,
    )
    if evidence.get("review_sha256") != sha256_file(
        artifacts["review"], max_bytes=131072
    ):
        raise ValidationError("qualification review cross-reference mismatch")
    expected_acceptance_fields = {
        "schema_version",
        "timestamp",
        "actor",
        "checkpoint_id",
        "review_verdict",
        "review_evidence_sha256",
        "contract_fingerprint",
        "terminal_criteria",
        "acceptance_evidence_sha256",
    }
    if (
        set(acceptance) != expected_acceptance_fields
        or acceptance.get("schema_version") != 1
        or acceptance.get("actor") != receipt["controller"]
        or acceptance.get("checkpoint_id") != followup.checkpoint_id
        or acceptance.get("review_verdict") != "conformance_accept"
        or acceptance.get("review_evidence_sha256") != review.get("evidence_sha256")
        or acceptance.get("contract_fingerprint") != review.get("contract_fingerprint")
        or acceptance.get("terminal_criteria") != ["conformance_green"]
    ):
        raise ValidationError("qualification acceptance identity mismatch")
    validate_sha256(acceptance.get("acceptance_evidence_sha256"), "acceptance evidence")
    expected_halt_fields = {
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
    expected_signal = (
        {"tmux_exact_pane_ctrl_d_twice", "tmux_exact_pane_ctrl_d_once_target_stopped"}
        if receipt["target"] == "agy"
        else {"exact_registered_pid_sigint"}
    )
    if (
        set(halt) != expected_halt_fields
        or halt.get("schema_version") != 1
        or halt.get("session") != tmux["session"]
        or halt.get("signal") not in expected_signal
        or halt.get("stopped") is not True
        or halt.get("tmux_preserved") is not True
        or halt.get("signal_sent") is not True
        or halt.get("cleanup_scope") != "exact_new_target_only"
        or halt.get("reason") != "accepted_probe_halt"
        or halt.get("target_pid") != evidence.get("process", {}).get("pid")
    ):
        raise ValidationError("qualification halt identity mismatch")
    return receipt


@dataclass(frozen=True)
class AdapterManifest:
    raw: Dict[str, Any]

    @classmethod
    def from_dict(cls, value: Dict[str, Any]) -> "AdapterManifest":
        required = {
            "schema_version",
            "target",
            "generated_at",
            "platform",
            "executable",
            "execution",
            "adapter_fingerprint",
            "protocol_fingerprint",
            "yolo_mapping",
            "capabilities",
            "doctor_only",
            "qualification",
        }
        if set(value) != required:
            raise ValidationError("adapter manifest fields do not match schema")
        if value.get("schema_version") != 1:
            raise ValidationError("unsupported adapter manifest schema")
        if value.get("target") not in {"agy", "cursor", "claude", "codex", "grok"}:
            raise ValidationError("unsupported adapter target")
        executable = value.get("executable")
        executable_fields = {
            "requested_path",
            "resolved_path",
            "device",
            "inode",
            "size",
            "mtime_ns",
            "sha256",
            "version_sha256",
            "help_sha256",
        }
        if not isinstance(executable, dict) or set(executable) != executable_fields:
            raise ValidationError("invalid executable manifest")
        requested_path = executable.get("requested_path")
        resolved_path = executable.get("resolved_path")
        if (
            not isinstance(requested_path, str)
            or not requested_path
            or len(requested_path) > 4096
            or "\x00" in requested_path
            or not Path(requested_path).is_absolute()
            or not isinstance(resolved_path, str)
            or not resolved_path
            or len(resolved_path) > 4096
            or "\x00" in resolved_path
            or not Path(resolved_path).is_absolute()
        ):
            raise ValidationError("resolved executable path must be absolute")
        validate_sha256(executable.get("sha256"), "executable fingerprint")
        validate_sha256(executable.get("version_sha256"), "version fingerprint")
        validate_sha256(executable.get("help_sha256"), "help fingerprint")
        for name in ("device", "inode", "size", "mtime_ns"):
            if isinstance(executable.get(name), bool) or not isinstance(
                executable.get(name), int
            ):
                raise ValidationError("executable %s identity is missing" % name)
            if executable[name] < 0:
                raise ValidationError("executable %s identity is invalid" % name)
        launcher = validate_execution_file_identity(
            launcher_execution_identity(executable), "launcher"
        )
        execution = value.get("execution")
        if not isinstance(execution, dict) or set(execution) != EXECUTION_FIELDS:
            raise ValidationError("runtime execution fields do not match schema")
        transition = execution.get("transition")
        if transition not in EXECUTION_TRANSITIONS:
            raise ValidationError("runtime execution transition is invalid")
        runtime = validate_execution_file_identity(
            execution.get("runtime_executable"), "runtime"
        )
        transient_values = execution.get("transient_executables")
        support_values = execution.get("support_files")
        if (
            not isinstance(transient_values, list)
            or len(transient_values) > MAX_TRANSIENT_EXECUTABLES
            or not isinstance(support_values, list)
            or len(support_values) > MAX_EXECUTION_SUPPORT_FILES
        ):
            raise ValidationError("runtime execution file lists exceed their bounds")
        transients = [
            validate_execution_file_identity(item, "transient")
            for item in transient_values
        ]
        support = [
            validate_execution_file_identity(item, "support") for item in support_values
        ]
        for label, files in (("transient", transients), ("support", support)):
            paths = [item["path"] for item in files]
            if paths != sorted(paths) or len(paths) != len(set(paths)):
                raise ValidationError(
                    "runtime execution %s files are not canonical" % label
                )
        all_paths = [
            runtime["path"],
            *[item["path"] for item in transients],
            *[item["path"] for item in support],
        ]
        all_file_ids = [
            (item["device"], item["inode"]) for item in [runtime, *transients, *support]
        ]
        if len(all_paths) != len(set(all_paths)) or len(all_file_ids) != len(
            set(all_file_ids)
        ):
            raise ValidationError("runtime execution file roles overlap")
        launcher_file_id = (launcher["device"], launcher["inode"])
        if any((item["device"], item["inode"]) == launcher_file_id for item in support):
            raise ValidationError("runtime execution file roles overlap")
        settle = execution.get("settle_timeout_seconds")
        if (
            isinstance(settle, bool)
            or not isinstance(settle, (int, float))
            or not math.isfinite(float(settle))
            or settle <= 0
            or settle > 30
        ):
            raise ValidationError("runtime execution settle timeout is invalid")
        if transition == "direct":
            if runtime != launcher or transients or support:
                raise ValidationError(
                    "direct runtime execution must equal the launch file"
                )
        elif (
            runtime["device"],
            runtime["inode"],
        ) == launcher_file_id or not transients:
            raise ValidationError(
                "same-pid exec requires a distinct runtime and declared transients"
            )
        expected_execution = build_execution_bundle(
            launcher=launcher,
            transition=transition,
            runtime_executable=runtime,
            transient_executables=transients,
            support_files=support,
            settle_timeout_seconds=settle,
        )
        if execution != expected_execution:
            raise ValidationError("runtime execution fingerprint is invalid")
        validate_sha256(value.get("adapter_fingerprint"), "adapter fingerprint")
        validate_sha256(value.get("protocol_fingerprint"), "protocol fingerprint")
        capabilities = value.get("capabilities")
        if not isinstance(capabilities, dict) or set(capabilities) != set(
            BEHAVIOR_CAPABILITIES
        ):
            raise ValidationError("manifest must declare every behavior capability")
        for name, state in capabilities.items():
            if state not in CAPABILITY_STATES:
                raise ValidationError("invalid capability state for %s" % name)
        if not isinstance(value.get("doctor_only"), bool):
            raise ValidationError("doctor_only must be boolean")
        qualification = value.get("qualification")
        if value["doctor_only"]:
            if qualification is not None:
                raise ValidationError(
                    "doctor-only manifests cannot carry qualification"
                )
            if any(state == "controller_verified" for state in capabilities.values()):
                raise ValidationError(
                    "doctor-only capabilities cannot be controller-verified"
                )
        else:
            if not isinstance(qualification, dict) or set(qualification) != {
                "receipt_path",
                "receipt_sha256",
                "session_profile",
            }:
                raise ValidationError("live manifest requires a qualification receipt")
            receipt_path = qualification.get("receipt_path")
            if (
                not isinstance(receipt_path, str)
                or not Path(receipt_path).is_absolute()
            ):
                raise ValidationError("qualification receipt path must be absolute")
            validate_sha256(
                qualification.get("receipt_sha256"), "qualification receipt"
            )
            validate_session_profile(
                value["target"], qualification.get("session_profile")
            )
            if any(
                capabilities[name] != "controller_verified"
                for name in PROBE_CAPABILITIES
            ):
                raise ValidationError(
                    "live manifest requires every shared-probe capability to be verified"
                )
            if any(
                state not in {"controller_verified", "unsupported"}
                for state in capabilities.values()
            ):
                raise ValidationError(
                    "live manifest must fail closed for every unverified capability"
                )
            if capabilities["resume"] != "unsupported":
                raise ValidationError(
                    "live manifest cannot enable resume without a separate proof contract"
                )
        mapping = value.get("yolo_mapping")
        if not isinstance(mapping, dict):
            raise ValidationError("invalid YOLO mapping")
        required_mapping = {
            "complete",
            "launch_argv",
            "permission_declared",
            "permission_flags",
            "prompt_transport",
            "prompt_transport_declared",
            "sandbox_disable_declared",
            "sandbox_flags",
            "project_isolation_declared",
            "project_isolation_flags",
            "session_profiles",
            "session_profiles_declared",
            "startup_settle_seconds",
            "submit_settle_seconds",
        }
        allowed_mapping = required_mapping | {"model_flag", "effort_flag"}
        if not required_mapping <= set(mapping) or set(mapping) - allowed_mapping:
            raise ValidationError("YOLO mapping fields do not match schema")
        if not isinstance(mapping["complete"], bool):
            raise ValidationError("YOLO mapping completeness must be boolean")
        argv = mapping["launch_argv"]
        if (
            not isinstance(argv, list)
            or not argv
            or len(argv) > 64
            or not all(isinstance(item, str) and 0 < len(item) <= 4096 for item in argv)
        ):
            raise ValidationError("manifest launch_argv is invalid")
        if argv[0] != resolved_path:
            raise ValidationError(
                "launch executable does not match its fingerprinted path"
            )
        if any("\x00" in item or "\n" in item or "\r" in item for item in argv):
            raise ValidationError(
                "manifest launch arguments contain control characters"
            )
        for name in (
            "permission_declared",
            "prompt_transport_declared",
            "sandbox_disable_declared",
            "project_isolation_declared",
            "session_profiles_declared",
        ):
            if not isinstance(mapping[name], bool):
                raise ValidationError("%s must be boolean" % name)
        for name in ("permission_flags", "sandbox_flags", "project_isolation_flags"):
            flags = mapping[name]
            if not isinstance(flags, list) or not all(
                isinstance(item, str) and item for item in flags
            ):
                raise ValidationError("%s must be a string list" % name)
            if len(flags) != len(set(flags)):
                raise ValidationError("%s contains duplicate entries" % name)
        if set(mapping["project_isolation_flags"]) & set(
            mapping["permission_flags"] + mapping["sandbox_flags"]
        ):
            raise ValidationError(
                "project isolation flags overlap another semantic bucket"
            )
        selector_flags = []
        for name in ("model_flag", "effort_flag"):
            if name not in mapping:
                continue
            flag = mapping[name]
            if (
                not isinstance(flag, str)
                or not flag.startswith("--")
                or len(flag) > 80
                or any(character.isspace() for character in flag)
                or any(character in flag for character in "\x00\n\r")
            ):
                raise ValidationError("%s is invalid" % name)
            selector_flags.append(flag)
        if len(selector_flags) != len(set(selector_flags)):
            raise ValidationError("model and effort selector flags overlap")
        if set(selector_flags) & set(
            mapping["permission_flags"]
            + mapping["sandbox_flags"]
            + mapping["project_isolation_flags"]
        ):
            raise ValidationError("selector flags overlap another semantic bucket")

        if value["target"] == "agy":
            if mapping["project_isolation_flags"] != ["--new-project"]:
                raise ValidationError("agy project isolation flags are invalid")
        transport = mapping["prompt_transport"]
        if not isinstance(transport, str) or not transport or len(transport) > 80:
            raise ValidationError("prompt transport declaration is invalid")
        if transport != PROMPT_TRANSPORT:
            raise ValidationError("prompt transport does not match the adapter policy")
        if mapping["session_profiles"] != session_profiles_for(value["target"]):
            raise ValidationError(
                "session profile mapping does not match the adapter policy"
            )
        settle_seconds = mapping["startup_settle_seconds"]
        if (
            isinstance(settle_seconds, bool)
            or not isinstance(settle_seconds, (int, float))
            or settle_seconds != startup_settle_seconds_for(value["target"])
        ):
            raise ValidationError(
                "startup settle mapping does not match the adapter policy"
            )
        submit_settle_seconds = mapping["submit_settle_seconds"]
        if (
            isinstance(submit_settle_seconds, bool)
            or not isinstance(submit_settle_seconds, (int, float))
            or submit_settle_seconds != SUBMIT_SETTLE_SECONDS
        ):
            raise ValidationError(
                "submit settle mapping does not match the adapter policy"
            )
        if value["target"] == "agy":
            expected_argv = [resolved_path]
            for flag in mapping["permission_flags"] + mapping["sandbox_flags"]:
                if flag not in expected_argv:
                    expected_argv.append(flag)
            for flag in mapping["project_isolation_flags"]:
                if flag not in expected_argv:
                    expected_argv.append(flag)
            if argv != expected_argv:
                raise ValidationError(
                    "manifest launch_argv does not match declared flags"
                )
        if mapping["complete"] and not all(
            mapping[name]
            for name in (
                "permission_declared",
                "prompt_transport_declared",
                "sandbox_disable_declared",
                "project_isolation_declared",
                "session_profiles_declared",
            )
        ):
            raise ValidationError("complete YOLO mapping lacks a proved component")
        return cls(raw=dict(value))

    @classmethod
    def from_path(cls, path: Path) -> "AdapterManifest":
        return cls.from_dict(read_json(Path(path), max_bytes=131072))

    @property
    def target(self) -> str:
        return self.raw["target"]

    @property
    def fingerprint(self) -> str:
        return sha256_bytes(canonical_json_bytes(self.raw))

    def save(self, path: Path) -> None:
        atomic_write_json(Path(path), self.raw)

    def require(self, capability: str) -> None:
        if capability not in BEHAVIOR_CAPABILITIES:
            raise ValidationError("unknown adapter capability")
        if (
            self.raw["doctor_only"]
            or self.raw["capabilities"][capability] != "controller_verified"
        ):
            raise UnsupportedError(
                "%s adapter capability %s is not controller-verified"
                % (self.target, capability)
            )

    def verify_process_executable(self, process: Dict[str, Any]) -> None:
        process = _validated_process_record(process, "target")
        self.verify_execution_files()
        if self.classify_process_executable(process) != "runtime":
            raise IdentityError(
                "target process does not execute the fingerprinted final runtime"
            )

    @property
    def execution_fingerprint(self) -> str:
        return self.raw["execution"]["execution_fingerprint"]

    @property
    def execution_settle_timeout(self) -> float:
        return float(self.raw["execution"]["settle_timeout_seconds"])

    def process_execution_selectors(self) -> list[Dict[str, Any]]:
        """Return the exact final-runtime selector for global process census."""

        execution = self.raw["execution"]
        return [
            {
                "path": execution["runtime_executable"]["path"],
                "device": execution["runtime_executable"]["device"],
                "inode": execution["runtime_executable"]["inode"],
            }
        ]

    def verify_execution_files(self) -> None:
        """Recheck every launcher, runtime, transient, and support file."""

        validate_execution_file_identity(
            launcher_execution_identity(self.raw["executable"]),
            "launcher",
            verify_current=True,
        )
        execution = self.raw["execution"]
        validate_execution_file_identity(
            execution["runtime_executable"], "runtime", verify_current=True
        )
        for index, identity in enumerate(execution["transient_executables"]):
            validate_execution_file_identity(
                identity, "transient %d" % index, verify_current=True
            )
        for index, identity in enumerate(execution["support_files"]):
            validate_execution_file_identity(
                identity, "support %d" % index, verify_current=True
            )

    def classify_process_executable(self, process: Dict[str, Any]) -> str:
        """Classify one process as the declared final runtime or transient."""

        process = _validated_process_record(process, "target")
        return self.classify_executable_identity(
            {
                "executable_path": process["executable_path"],
                "device": process["device"],
                "inode": process["inode"],
            }
        )

    def classify_executable_identity(self, value: Dict[str, Any]) -> str:
        """Classify one exact executable selector without trusting argv or comm."""

        if (
            not isinstance(value, dict)
            or set(value) != {"executable_path", "device", "inode"}
            or not isinstance(value.get("executable_path"), str)
            or not Path(value["executable_path"]).is_absolute()
            or isinstance(value.get("device"), bool)
            or not isinstance(value.get("device"), int)
            or value["device"] <= 0
            or isinstance(value.get("inode"), bool)
            or not isinstance(value.get("inode"), int)
            or value["inode"] <= 0
        ):
            raise IdentityError("target process executable identity is invalid")
        observed = {
            "path": value["executable_path"],
            "device": value["device"],
            "inode": value["inode"],
        }

        def matches(identity: Dict[str, Any]) -> bool:
            return observed == {
                "path": identity["path"],
                "device": identity["device"],
                "inode": identity["inode"],
            }

        execution = self.raw["execution"]
        if matches(execution["runtime_executable"]):
            return "runtime"
        if any(matches(item) for item in execution["transient_executables"]):
            return "transient"
        raise IdentityError("target process executable is not declared")

    def verify_launch_execution_environment(self, environment: Dict[str, str]) -> None:
        """Bind cwd-sensitive interpreter lookup to the exact launch environment."""

        execution = self.raw["execution"]
        if self.target != "cursor" or execution["transition"] != "same_pid_exec":
            return
        if not isinstance(environment, dict):
            raise ValidationError("runtime launch environment is invalid")
        path_value = environment.get("PATH")
        if not isinstance(path_value, str) or not path_value:
            raise IdentityError("cursor runtime PATH is unavailable")
        path_entries = path_value.split(os.pathsep)
        if any(not item or not Path(item).is_absolute() for item in path_entries):
            raise IdentityError("cursor runtime PATH is cwd-dependent")
        discovered = shutil.which("bash", path=path_value)
        if not discovered:
            raise IdentityError("cursor runtime bash interpreter is unavailable")
        bash = execution_file_identity(Path(discovered).resolve(strict=True))
        observed = {
            "executable_path": bash["path"],
            "device": bash["device"],
            "inode": bash["inode"],
        }
        if self.classify_executable_identity(observed) != "transient":
            raise IdentityError("cursor runtime bash interpreter is not declared")

    def verify_qualification(
        self,
        *,
        expected_controller: Optional[str] = None,
        expected_campaign_id: Optional[str] = None,
        expected_goal_fingerprint: Optional[str] = None,
        expected_session_profile: Optional[str] = None,
        _authority_root: Optional[Path] = None,
        _current_manifest: Optional["AdapterManifest"] = None,
        _server_process_fn: Optional[Any] = None,
        _tmux_factory: Optional[Any] = None,
    ) -> Dict[str, Any]:
        if self.raw["doctor_only"]:
            raise UnsupportedError(
                "doctor-only manifest has no real-harness qualification"
            )
        qualification = self.raw["qualification"]
        path = Path(qualification["receipt_path"])
        if sha256_file(path, max_bytes=131072) != qualification["receipt_sha256"]:
            raise ValidationError("qualification receipt fingerprint changed")
        receipt = verify_qualification_receipt(
            path,
            _authority_root=_authority_root,
            _current_manifest=_current_manifest,
            _server_process_fn=_server_process_fn,
            _tmux_factory=_tmux_factory,
        )
        if receipt.get("target") != self.target:
            raise ValidationError("qualification target mismatch")
        if receipt.get("session_profile") != qualification["session_profile"]:
            raise ValidationError("qualification session profile mismatch")
        if expected_session_profile is not None:
            expected_session_profile = validate_session_profile(
                self.target, expected_session_profile
            )
            if receipt.get("session_profile") != expected_session_profile:
                raise IdentityError(
                    "qualification session profile does not match the active contract"
                )
        expected_authority = {
            "controller": expected_controller,
            "campaign_id": expected_campaign_id,
            "goal_fingerprint": expected_goal_fingerprint,
        }
        for name, expected in expected_authority.items():
            if expected is None:
                continue
            if name == "goal_fingerprint":
                validate_sha256(expected, "expected goal fingerprint")
            else:
                validate_identifier(expected, "expected qualification %s" % name)
            if receipt.get(name) != expected:
                raise IdentityError(
                    "qualification %s does not match the active campaign" % name
                )
        if not self.identity_matches(
            executable=receipt.get("executable_fingerprint"),
            execution=receipt.get("execution_fingerprint"),
            adapter=receipt.get("adapter_fingerprint"),
            protocol=receipt.get("protocol_fingerprint"),
        ):
            raise ValidationError("qualification identity mismatch")
        evidence = read_json(
            _qualification_artifacts(path, receipt)["evidence"],
            max_bytes=131072,
            reject_sensitive_fields=True,
        )
        process = _validated_process_record(evidence.get("process"), "target")
        expected_executable = self.raw["execution"]["runtime_executable"]
        if (
            process["executable_path"] != expected_executable["path"]
            or process["device"] != expected_executable["device"]
            or process["inode"] != expected_executable["inode"]
        ):
            raise ValidationError(
                "qualification process does not bind the manifest executable"
            )
        validate_sha256(receipt.get("version_fingerprint"), "version fingerprint")
        validate_sha256(receipt.get("platform_fingerprint"), "platform fingerprint")
        if receipt["version_fingerprint"] != self.raw["executable"][
            "version_sha256"
        ] or receipt["platform_fingerprint"] != sha256_bytes(
            canonical_json_bytes(self.raw["platform"])
        ):
            raise ValidationError("qualification platform or version identity mismatch")
        if receipt.get("yolo_mapping_sha256") != sha256_bytes(
            canonical_json_bytes(self.raw["yolo_mapping"])
        ):
            raise ValidationError("qualified YOLO mapping changed")
        verified_capabilities = [
            name
            for name in BEHAVIOR_CAPABILITIES
            if self.raw["capabilities"][name] == "controller_verified"
        ]
        if receipt.get("capabilities") != verified_capabilities:
            raise ValidationError(
                "qualification capability receipt does not match manifest"
            )
        if not set(PROBE_CAPABILITIES) <= set(verified_capabilities):
            raise ValidationError(
                "qualification did not prove the shared behavior contract"
            )
        return receipt

    def identity_matches(
        self, *, executable: str, execution: str, adapter: str, protocol: str
    ) -> bool:
        return (
            self.raw["executable"]["sha256"] == executable
            and self.execution_fingerprint == execution
            and self.raw["adapter_fingerprint"] == adapter
            and self.raw["protocol_fingerprint"] == protocol
        )
