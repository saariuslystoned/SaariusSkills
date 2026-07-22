"""Fingerprint-bound adapter capability manifests."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

from .errors import UnsupportedError, ValidationError
from .safety import (
    atomic_write_json,
    canonical_json_bytes,
    read_json,
    sha256_file,
    sha256_bytes,
    validate_identifier,
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
            if any(state != "controller_verified" for state in capabilities.values()):
                raise ValidationError("live manifest requires every capability to be verified")
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

    def verify_qualification(self) -> Dict[str, Any]:
        if self.raw["doctor_only"]:
            raise UnsupportedError("doctor-only manifest has no real-harness qualification")
        qualification = self.raw["qualification"]
        path = Path(qualification["receipt_path"])
        if path.is_symlink() or not path.is_file():
            raise ValidationError("qualification receipt is unavailable or a symlink")
        if sha256_file(path, max_bytes=131072) != qualification["receipt_sha256"]:
            raise ValidationError("qualification receipt fingerprint changed")
        receipt = read_json(path, max_bytes=131072, reject_sensitive_fields=True)
        required = {
            "schema_version",
            "kind",
            "run_id",
            "target",
            "result",
            "controller",
            "executable_fingerprint",
            "adapter_fingerprint",
            "protocol_fingerprint",
            "yolo_mapping_sha256",
            "capabilities",
            "accepted_checkpoint_id",
            "acceptance_sha256",
            "halt_receipt_sha256",
            "proof_refs",
        }
        if set(receipt) != required or receipt.get("schema_version") != 1:
            raise ValidationError("qualification receipt fields do not match schema")
        if receipt.get("kind") != "real_harness_conformance" or receipt.get("result") != "accepted":
            raise ValidationError("qualification receipt is not an accepted real-harness run")
        validate_identifier(receipt.get("run_id"), "qualification run id")
        validate_identifier(receipt.get("controller"), "qualification controller")
        if receipt.get("target") != self.target:
            raise ValidationError("qualification target mismatch")
        if not self.identity_matches(
            executable=receipt.get("executable_fingerprint"),
            adapter=receipt.get("adapter_fingerprint"),
            protocol=receipt.get("protocol_fingerprint"),
        ):
            raise ValidationError("qualification identity mismatch")
        if receipt.get("yolo_mapping_sha256") != sha256_bytes(
            canonical_json_bytes(self.raw["yolo_mapping"])
        ):
            raise ValidationError("qualified YOLO mapping changed")
        if receipt.get("capabilities") != list(BEHAVIOR_CAPABILITIES):
            raise ValidationError("qualification did not prove the complete behavior contract")
        for name in (
            "accepted_checkpoint_id",
            "acceptance_sha256",
            "halt_receipt_sha256",
        ):
            validate_sha256(receipt.get(name), name.replace("_", " "))
        refs = receipt.get("proof_refs")
        if not isinstance(refs, list) or not refs or len(refs) > 32 or not all(
            isinstance(item, str) and item and len(item) <= 1000 for item in refs
        ):
            raise ValidationError("qualification proof references are invalid")
        return receipt

    def identity_matches(self, *, executable: str, adapter: str, protocol: str) -> bool:
        return (
            self.raw["executable"]["sha256"] == executable
            and self.raw["adapter_fingerprint"] == adapter
            and self.raw["protocol_fingerprint"] == protocol
        )
