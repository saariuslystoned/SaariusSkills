"""Fingerprint-bound adapter capability manifests."""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Dict

from .errors import IdentityError, UnsupportedError, ValidationError
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
    "result",
    "controller",
    "executable_fingerprint",
    "version_fingerprint",
    "platform_fingerprint",
    "adapter_fingerprint",
    "protocol_fingerprint",
    "yolo_mapping_sha256",
    "capabilities",
    "accepted_checkpoint_id",
    "acceptance_sha256",
    "halt_receipt_sha256",
    "proof_refs",
}

_ACCEPTED_EVIDENCE_FIELDS = {
    "schema_version",
    "run_id",
    "target",
    "controller",
    "profile",
    "campaign_id",
    "authorization_sha256",
    "manifest_fingerprint",
    "executable_fingerprint",
    "version_fingerprint",
    "platform_fingerprint",
    "adapter_fingerprint",
    "protocol_fingerprint",
    "yolo_mapping_sha256",
    "launch_argv_sha256",
    "input_transport",
    "payload_argv_absent",
    "active_target_processes_before_launch",
    "active_target_processes_after_halt",
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

_PROCESS_FIELDS = {
    "pid",
    "start",
    "command",
    "executable_path",
    "device",
    "inode",
}


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
            raise ValidationError("qualification proof reference fields do not match schema")
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
        isinstance(value.get("pid"), bool)
        or not isinstance(value.get("pid"), int)
        or value["pid"] <= 1
        or not isinstance(value.get("start"), str)
        or not value["start"]
        or len(value["start"]) > 200
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


def _validated_process_population(value: Any, label: str) -> list[Dict[str, Any]]:
    if not isinstance(value, list) or len(value) > 32:
        raise ValidationError("%s process population is invalid" % label)
    records = [_validated_process_record(item, label) for item in value]
    pids = [item["pid"] for item in records]
    if len(pids) != len(set(pids)) or pids != sorted(pids):
        raise ValidationError("%s process population order or identity is invalid" % label)
    return records


def verify_qualification_receipt(path: Path) -> Dict[str, Any]:
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
        raise ValidationError("qualification receipt is not an accepted real-harness run")
    if receipt.get("target") not in {"agy", "cursor", "claude", "codex", "grok"}:
        raise ValidationError("qualification receipt target is invalid")
    validate_identifier(receipt.get("run_id"), "qualification run id")
    validate_identifier(receipt.get("controller"), "qualification controller")
    for name in (
        "executable_fingerprint",
        "version_fingerprint",
        "platform_fingerprint",
        "adapter_fingerprint",
        "protocol_fingerprint",
        "yolo_mapping_sha256",
        "accepted_checkpoint_id",
        "acceptance_sha256",
        "halt_receipt_sha256",
    ):
        validate_sha256(receipt.get(name), name.replace("_", " "))
    capabilities = receipt.get("capabilities")
    if capabilities != list(PROBE_CAPABILITIES):
        raise ValidationError("qualification capability receipt is invalid")

    artifacts = _qualification_artifacts(path, receipt)
    authorization = read_json(
        artifacts["authorization"], max_bytes=65536, reject_sensitive_fields=True
    )
    evidence = read_json(artifacts["evidence"], max_bytes=131072, reject_sensitive_fields=True)
    halt = read_json(artifacts["halt"], max_bytes=65536, reject_sensitive_fields=True)
    review = read_json(artifacts["review"], max_bytes=131072, reject_sensitive_fields=True)
    acceptance = read_json(
        artifacts["acceptance"], max_bytes=131072, reject_sensitive_fields=True
    )
    if set(evidence) != _ACCEPTED_EVIDENCE_FIELDS or evidence.get("schema_version") != 1:
        raise ValidationError("qualification evidence fields do not match schema")
    if (
        evidence.get("profile") != "source-free-pass-b-v1"
        or evidence.get("input_transport") != "tmux_load_buffer_stdin"
        or evidence.get("payload_argv_absent") is not True
    ):
        raise ValidationError("qualification evidence transport contract is invalid")
    for name in (
        "authorization_sha256",
        "manifest_fingerprint",
        "launch_argv_sha256",
        "fixture_fingerprint_before",
        "fixture_fingerprint_after",
        "review_sha256",
        "acceptance_sha256",
        "halt_sha256",
    ):
        validate_sha256(evidence.get(name), "qualification evidence %s" % name)
    if evidence["fixture_fingerprint_before"] != evidence["fixture_fingerprint_after"]:
        raise ValidationError("qualification fixture drifted")
    if sha256_file(artifacts["authorization"], max_bytes=65536) != evidence[
        "authorization_sha256"
    ]:
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
        or authorization.get("controller") != receipt["controller"]
        or not isinstance(execution_authorization, dict)
        or set(execution_authorization)
        not in (execution_fields, execution_fields | {"parallel_target_override"})
        or receipt["target"] not in execution_authorization.get("harnesses", [])
        or execution_authorization.get("trust_profile") != "unrestricted_required"
        or execution_authorization.get("disable_harness_sandbox_where_exposed") is not True
        or execution_authorization.get("ordinary_configured_model_provider_traffic") is not True
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
            or override.get("isolation")
            != "unique_private_tmux_socket_and_session"
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

    process = _validated_process_record(evidence.get("process"), "target")
    executable_path = Path(process["executable_path"])
    if executable_path.is_symlink() or not executable_path.is_file():
        raise ValidationError("qualification process executable is unavailable")
    executable_details = executable_path.stat()
    if (
        executable_details.st_dev != process["device"]
        or executable_details.st_ino != process["inode"]
        or sha256_file(executable_path) != receipt["executable_fingerprint"]
    ):
        raise ValidationError("qualification process executable identity mismatch")
    tmux = evidence.get("tmux")
    if not isinstance(tmux, dict) or set(tmux) != {
        "socket",
        "session",
        "target_id",
        "socket_identity",
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
    lock = evidence.get("campaign_probe_lock")
    if not isinstance(lock, dict) or set(lock) != {
        "path",
        "device",
        "inode",
        "uid",
        "mode",
    }:
        raise ValidationError("qualification campaign lock identity is invalid")
    lock_path = Path(lock.get("path", ""))
    if not lock_path.is_absolute() or lock_path.is_symlink() or not lock_path.is_file():
        raise ValidationError("qualification campaign lock is unavailable")
    lock_details = lock_path.stat()
    if (
        lock_details.st_uid != os.getuid()
        or stat.S_IMODE(lock_details.st_mode) & 0o077
        or lock
        != {
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
        "executable_fingerprint",
        "version_fingerprint",
        "platform_fingerprint",
        "adapter_fingerprint",
        "protocol_fingerprint",
        "yolo_mapping_sha256",
    ):
        if evidence.get(name) != receipt.get(name):
            raise ValidationError("qualification evidence identity mismatch: %s" % name)
    if evidence.get("result") != "accepted":
        raise ValidationError("qualification evidence is not accepted")
    if evidence.get("halt_sha256") != receipt["halt_receipt_sha256"]:
        raise ValidationError("qualification halt cross-reference mismatch")
    if evidence.get("acceptance_sha256") != receipt["acceptance_sha256"]:
        raise ValidationError("qualification acceptance cross-reference mismatch")
    if sha256_file(artifacts["halt"], max_bytes=65536) != receipt["halt_receipt_sha256"]:
        raise ValidationError("qualification halt receipt mismatch")
    if sha256_file(artifacts["acceptance"], max_bytes=131072) != receipt["acceptance_sha256"]:
        raise ValidationError("qualification acceptance receipt mismatch")

    from .handoffs import validate_handoff

    ready = validate_handoff(
        artifacts["ready"],
        allowed_roots=[path.resolve(strict=True).parent],
        expected={
            "session": evidence.get("tmux", {}).get("session"),
            "run_id": receipt["run_id"],
            "executable_fingerprint": receipt["executable_fingerprint"],
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
        if not isinstance(reference, dict) or not isinstance(reference.get("path"), str):
            raise ValidationError("qualification %s evidence reference mismatch" % label)
        reference_path = ensure_within(
            Path(reference["path"]), path.resolve(strict=True).parent, must_exist=True
        )
        if (
            reference.get("checkpoint_id") != handoff.checkpoint_id
            or reference.get("artifact_sha256") != handoff.artifact_sha256
            or reference_path != handoff.path
        ):
            raise ValidationError("qualification %s evidence reference mismatch" % label)
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
    validate_sha256(
        acceptance.get("acceptance_evidence_sha256"), "acceptance evidence"
    )
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
        else {"tmux_exact_pane_ctrl_c"}
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
        if not isinstance(executable, dict):
            raise ValidationError("invalid executable manifest")
        resolved_path = executable.get("resolved_path")
        if not isinstance(resolved_path, str) or not Path(resolved_path).is_absolute():
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
        validate_sha256(value.get("adapter_fingerprint"), "adapter fingerprint")
        validate_sha256(value.get("protocol_fingerprint"), "protocol fingerprint")
        capabilities = value.get("capabilities")
        if not isinstance(capabilities, dict) or set(capabilities) != set(BEHAVIOR_CAPABILITIES):
            raise ValidationError("manifest must declare every behavior capability")
        for name, state in capabilities.items():
            if state not in CAPABILITY_STATES:
                raise ValidationError("invalid capability state for %s" % name)
        if not isinstance(value.get("doctor_only"), bool):
            raise ValidationError("doctor_only must be boolean")
        qualification = value.get("qualification")
        if value["doctor_only"]:
            if qualification is not None:
                raise ValidationError("doctor-only manifests cannot carry qualification")
            if any(state == "controller_verified" for state in capabilities.values()):
                raise ValidationError("doctor-only capabilities cannot be controller-verified")
        else:
            if not isinstance(qualification, dict) or set(qualification) != {
                "receipt_path",
                "receipt_sha256",
            }:
                raise ValidationError("live manifest requires a qualification receipt")
            receipt_path = qualification.get("receipt_path")
            if not isinstance(receipt_path, str) or not Path(receipt_path).is_absolute():
                raise ValidationError("qualification receipt path must be absolute")
            validate_sha256(qualification.get("receipt_sha256"), "qualification receipt")
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
            raise ValidationError("launch executable does not match its fingerprinted path")
        if any("\x00" in item or "\n" in item or "\r" in item for item in argv):
            raise ValidationError("manifest launch arguments contain control characters")
        for name in (
            "permission_declared",
            "prompt_transport_declared",
            "sandbox_disable_declared",
        ):
            if not isinstance(mapping[name], bool):
                raise ValidationError("%s must be boolean" % name)
        for name in ("permission_flags", "sandbox_flags"):
            flags = mapping[name]
            if not isinstance(flags, list) or not all(
                isinstance(item, str) and item for item in flags
            ):
                raise ValidationError("%s must be a string list" % name)
        transport = mapping["prompt_transport"]
        if not isinstance(transport, str) or not transport or len(transport) > 80:
            raise ValidationError("prompt transport declaration is invalid")
        if mapping["complete"] and not all(
            mapping[name]
            for name in (
                "permission_declared",
                "prompt_transport_declared",
                "sandbox_disable_declared",
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
        if self.raw["doctor_only"] or self.raw["capabilities"][capability] != "controller_verified":
            raise UnsupportedError(
                "%s adapter capability %s is not controller-verified"
                % (self.target, capability)
            )

    def verify_process_executable(self, process: Dict[str, Any]) -> None:
        process = _validated_process_record(process, "target")
        expected = self.raw["executable"]
        executable = Path(process["executable_path"])
        if executable.is_symlink() or not executable.is_file():
            raise IdentityError("target process executable is unavailable")
        if (
            executable.resolve(strict=True) != Path(expected["resolved_path"])
            or process["device"] != expected["device"]
            or process["inode"] != expected["inode"]
            or sha256_file(executable) != expected["sha256"]
        ):
            raise IdentityError("target process does not execute the fingerprinted launcher")

    def verify_qualification(self) -> Dict[str, Any]:
        if self.raw["doctor_only"]:
            raise UnsupportedError("doctor-only manifest has no real-harness qualification")
        qualification = self.raw["qualification"]
        path = Path(qualification["receipt_path"])
        if sha256_file(path, max_bytes=131072) != qualification["receipt_sha256"]:
            raise ValidationError("qualification receipt fingerprint changed")
        receipt = verify_qualification_receipt(path)
        if receipt.get("target") != self.target:
            raise ValidationError("qualification target mismatch")
        if not self.identity_matches(
            executable=receipt.get("executable_fingerprint"),
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
        expected_executable = self.raw["executable"]
        if (
            process["executable_path"] != expected_executable["resolved_path"]
            or process["device"] != expected_executable["device"]
            or process["inode"] != expected_executable["inode"]
        ):
            raise ValidationError("qualification process does not bind the manifest executable")
        validate_sha256(receipt.get("version_fingerprint"), "version fingerprint")
        validate_sha256(receipt.get("platform_fingerprint"), "platform fingerprint")
        if (
            receipt["version_fingerprint"]
            != self.raw["executable"]["version_sha256"]
            or receipt["platform_fingerprint"]
            != sha256_bytes(canonical_json_bytes(self.raw["platform"]))
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
            raise ValidationError("qualification capability receipt does not match manifest")
        if not set(PROBE_CAPABILITIES) <= set(verified_capabilities):
            raise ValidationError(
                "qualification did not prove the shared behavior contract"
            )
        return receipt

    def identity_matches(self, *, executable: str, adapter: str, protocol: str) -> bool:
        return (
            self.raw["executable"]["sha256"] == executable
            and self.raw["adapter_fingerprint"] == adapter
            and self.raw["protocol_fingerprint"] == protocol
        )
