"""Body-free outcome observations for zero-agent and future live Puppet runs."""

from __future__ import annotations

import os
import stat
import tempfile
from pathlib import Path
from typing import Any, Dict, Mapping

from .codex_launch import (
    CURRENT_DEFAULT_SELECTION,
    DEFAULT_MODEL_CLASSIFICATION,
    DEFAULT_MODEL_SENTINEL,
    DOCTOR_OBSERVATION_SCHEMA,
    DOCTOR_OBSERVATION_STATE,
    EXPECTED_VERSION_TEXT,
    EXPLICIT_MODEL_CLASSIFICATION,
    MAPPING_INCOMPLETE_BLOCKER,
    SOURCE_ONLY_BLOCKERS,
    UNAVAILABLE_MODEL_CLASSIFICATION,
    CodexDoctorObservation,
)
from .errors import ConflictError, IdentityError, ValidationError
from .safety import (
    canonical_json_bytes,
    sha256_bytes,
    sha256_file,
    validate_bounded_json,
    validate_identifier,
    validate_sha256,
)


RUN_OBSERVATION_SCHEMA = "puppet.run-observation/v1"
ZERO_AGENT_CODEX_DOCTOR_KIND = "zero_agent_codex_doctor"
ZERO_AGENT_CLAUDE_MATCHED_CONTROL_BLOCKER_KIND = (
    "zero_agent_claude_matched_control_blocker"
)
UNAVAILABLE = "unavailable"
SOURCE_ONLY_PROOF = "source_only"
BLOCKED_VERDICT = "blocked"
MAX_LATENCY_MILLISECONDS = 3_600_000
_EXPECTED_BLOCKERS = (*SOURCE_ONLY_BLOCKERS, MAPPING_INCOMPLETE_BLOCKER)
CLAUDE_MATCHED_CONTROL_BLOCKERS = (
    "claude_ordinary_control_missing",
    "claude_paired_no_bleed_unproved",
    "claude_default_model_observation_unavailable",
    "claude_direct_cockpit_pair_unproved",
    "claude_native_tui_attach_unproved",
    "claude_activation_lifecycle_nonqualifying",
)
_CLAUDE_SOURCE_ROLES = (
    ("activation_binding", "matched_control.py"),
    ("pre_delivery_authority", "matched_control_authority.py"),
    ("signal_observation", "matched_control_signal.py"),
    ("probe_integration", "probe.py"),
    ("terminal_verifier", "adapter_manifest.py"),
)
_SOURCE_FIELDS = {
    "schema",
    "state",
    "target",
    "session_profile",
    "classification",
    "observed_model",
    "observed_provider",
    "doctor_output_sha256",
    "doctor_output_bytes",
    "manifest_fingerprint",
    "execution_fingerprint",
    "adapter_fingerprint",
    "protocol_fingerprint",
    "codex_home_identity_sha256",
    "launch_context_sha256",
    "doctor_command_identity",
    "blockers",
    "launch_authorized",
    "qualification_authorized",
    "same_runtime_proved",
    "model_selection_authorized",
    "observation_sha256",
}
_RECORD_FIELDS = {
    "schema",
    "kind",
    "run_id",
    "requested_harness",
    "observed_harness",
    "requested_version",
    "observed_version",
    "requested_model",
    "observed_model",
    "model_observation_classification",
    "observed_provider",
    "requested_effort",
    "observed_effort",
    "task_type",
    "task_profile",
    "latency_milliseconds",
    "native_turn_count",
    "native_tool_call_count",
    "checkpoint_quality",
    "repair_cycles",
    "proof_integrity",
    "verification_depth",
    "exact_accepted_head",
    "target_claimed_green",
    "controller_gates_green",
    "independent_review_clean",
    "controller_verdict",
    "limitations",
    "source_observation_sha256",
    "launch_authorized",
    "model_selection_authorized",
    "qualification_authorized",
    "promotion_authorized",
    "record_sha256",
}
_CLAUDE_RECORD_FIELDS = _RECORD_FIELDS | {
    "source_bundle",
    "source_bundle_sha256",
    "delivery_authorized",
    "checkpoint_observed",
    "no_bleed_evaluated",
    "no_bleed_verified",
}


def _validated_source(observation: CodexDoctorObservation) -> Dict[str, Any]:
    if type(observation) is not CodexDoctorObservation:
        raise ValidationError(
            "run observation requires an exact Codex doctor observation"
        )
    source = observation.to_public_dict()
    if not isinstance(source, dict) or set(source) != _SOURCE_FIELDS:
        raise ValidationError("Codex doctor observation fields changed")
    supplied_sha = validate_sha256(
        source.get("observation_sha256"), "Codex doctor observation"
    )
    source_core = dict(source)
    source_core.pop("observation_sha256")
    if supplied_sha != sha256_bytes(canonical_json_bytes(source_core)):
        raise IdentityError("Codex doctor observation fingerprint changed")
    if (
        source.get("schema") != DOCTOR_OBSERVATION_SCHEMA
        or source.get("state") != DOCTOR_OBSERVATION_STATE
        or source.get("target") != "codex"
        or source.get("session_profile") != "regular"
        or tuple(source.get("blockers", ())) != _EXPECTED_BLOCKERS
        or any(
            source.get(name) is not False
            for name in (
                "launch_authorized",
                "qualification_authorized",
                "same_runtime_proved",
                "model_selection_authorized",
            )
        )
    ):
        raise IdentityError("Codex doctor observation gained runtime authority")
    classification = source.get("classification")
    model = source.get("observed_model")
    provider = source.get("observed_provider")
    if classification == DEFAULT_MODEL_CLASSIFICATION:
        if model != DEFAULT_MODEL_SENTINEL or not isinstance(provider, str):
            raise IdentityError("Codex default-model observation is incomplete")
    elif classification == EXPLICIT_MODEL_CLASSIFICATION:
        if not isinstance(model, str) or not isinstance(provider, str):
            raise IdentityError("Codex explicit-model observation is incomplete")
    elif classification == UNAVAILABLE_MODEL_CLASSIFICATION:
        if model is not None or provider is not None:
            raise IdentityError("Codex unavailable-model observation is ambiguous")
    else:
        raise ValidationError("Codex model observation classification is invalid")
    for name in (
        "doctor_output_sha256",
        "manifest_fingerprint",
        "execution_fingerprint",
        "adapter_fingerprint",
        "protocol_fingerprint",
        "codex_home_identity_sha256",
        "launch_context_sha256",
    ):
        validate_sha256(source.get(name), name.replace("_", " "))
    output_bytes = source.get("doctor_output_bytes")
    if (
        isinstance(output_bytes, bool)
        or not isinstance(output_bytes, int)
        or output_bytes <= 0
        or output_bytes > 65536
    ):
        raise ValidationError("Codex doctor output size is invalid")
    validate_bounded_json(
        source,
        max_depth=8,
        max_items=64,
        max_string=4096,
        reject_sensitive_fields=True,
    )
    return source


def build_codex_doctor_run_observation(
    observation: CodexDoctorObservation,
    *,
    run_id: str,
    task_type: str,
    task_profile: str,
    latency_milliseconds: int,
) -> Dict[str, Any]:
    """Build one non-authorizing zero-agent observation from exact doctor evidence."""

    source = _validated_source(observation)
    run_id = validate_identifier(run_id, "run observation run id")
    task_type = validate_identifier(task_type, "run observation task type")
    task_profile = validate_identifier(task_profile, "run observation task profile")
    if (
        isinstance(latency_milliseconds, bool)
        or not isinstance(latency_milliseconds, int)
        or latency_milliseconds < 0
        or latency_milliseconds > MAX_LATENCY_MILLISECONDS
    ):
        raise ValidationError("run observation latency is invalid")
    value = _build_from_validated_source(
        source,
        run_id=run_id,
        task_type=task_type,
        task_profile=task_profile,
        latency_milliseconds=latency_milliseconds,
    )
    validate_codex_doctor_run_observation(
        value,
        observation,
        run_id=run_id,
        task_type=task_type,
        task_profile=task_profile,
        latency_milliseconds=latency_milliseconds,
    )
    return value


def validate_codex_doctor_run_observation(
    value: Mapping[str, Any],
    observation: CodexDoctorObservation,
    *,
    run_id: str,
    task_type: str,
    task_profile: str,
    latency_milliseconds: int,
) -> Dict[str, Any]:
    """Rebuild and compare one exact zero-agent observation."""

    if not isinstance(value, Mapping) or set(value) != _RECORD_FIELDS:
        raise ValidationError("run observation fields changed")
    supplied = dict(value)
    supplied_sha = validate_sha256(
        supplied.get("record_sha256"), "run observation record"
    )
    core = dict(supplied)
    core.pop("record_sha256")
    if supplied_sha != sha256_bytes(canonical_json_bytes(core)):
        raise IdentityError("run observation record fingerprint changed")
    if (
        isinstance(latency_milliseconds, bool)
        or not isinstance(latency_milliseconds, int)
        or latency_milliseconds < 0
        or latency_milliseconds > MAX_LATENCY_MILLISECONDS
    ):
        raise ValidationError("run observation latency is invalid")
    source = _validated_source(observation)
    expected = _build_from_validated_source(
        source,
        run_id=validate_identifier(run_id, "run observation run id"),
        task_type=validate_identifier(task_type, "run observation task type"),
        task_profile=validate_identifier(task_profile, "run observation task profile"),
        latency_milliseconds=latency_milliseconds,
    )
    if supplied != expected:
        raise IdentityError("run observation differs from its Codex doctor source")
    validate_bounded_json(
        supplied,
        max_depth=6,
        max_items=64,
        max_string=4096,
        reject_sensitive_fields=True,
    )
    return supplied


def _build_from_validated_source(
    source: Mapping[str, Any],
    *,
    run_id: str,
    task_type: str,
    task_profile: str,
    latency_milliseconds: int,
) -> Dict[str, Any]:
    """Build the canonical record from one already validated source."""

    observed_model = source["observed_model"] or UNAVAILABLE
    observed_provider = source["observed_provider"] or UNAVAILABLE
    value: Dict[str, Any] = {
        "schema": RUN_OBSERVATION_SCHEMA,
        "kind": ZERO_AGENT_CODEX_DOCTOR_KIND,
        "run_id": run_id,
        "requested_harness": "codex",
        "observed_harness": "codex",
        "requested_version": "current_installed",
        "observed_version": EXPECTED_VERSION_TEXT,
        "requested_model": CURRENT_DEFAULT_SELECTION,
        "observed_model": observed_model,
        "model_observation_classification": source["classification"],
        "observed_provider": observed_provider,
        "requested_effort": CURRENT_DEFAULT_SELECTION,
        "observed_effort": UNAVAILABLE,
        "task_type": task_type,
        "task_profile": task_profile,
        "latency_milliseconds": latency_milliseconds,
        "native_turn_count": UNAVAILABLE,
        "native_tool_call_count": UNAVAILABLE,
        "checkpoint_quality": UNAVAILABLE,
        "repair_cycles": 0,
        "proof_integrity": SOURCE_ONLY_PROOF,
        "verification_depth": SOURCE_ONLY_PROOF,
        "exact_accepted_head": UNAVAILABLE,
        "target_claimed_green": False,
        "controller_gates_green": False,
        "independent_review_clean": False,
        "controller_verdict": BLOCKED_VERDICT,
        "limitations": list(_EXPECTED_BLOCKERS),
        "source_observation_sha256": source["observation_sha256"],
        "launch_authorized": False,
        "model_selection_authorized": False,
        "qualification_authorized": False,
        "promotion_authorized": False,
    }
    value["record_sha256"] = sha256_bytes(canonical_json_bytes(value))
    return value


def _claude_source_bundle() -> tuple[list[Dict[str, str]], str]:
    library_root = Path(__file__).resolve(strict=True).parent
    entries = []
    for role, filename in _CLAUDE_SOURCE_ROLES:
        source = library_root / filename
        if source.is_symlink() or not source.is_file():
            raise ValidationError("Claude blocker source bundle is unavailable")
        entries.append({"role": role, "sha256": sha256_file(source)})
    return entries, sha256_bytes(canonical_json_bytes(entries))


def _build_claude_matched_control_blocker(
    *,
    run_id: str,
    latency_milliseconds: int,
) -> Dict[str, Any]:
    source_bundle, source_bundle_sha256 = _claude_source_bundle()
    value: Dict[str, Any] = {
        "schema": RUN_OBSERVATION_SCHEMA,
        "kind": ZERO_AGENT_CLAUDE_MATCHED_CONTROL_BLOCKER_KIND,
        "run_id": run_id,
        "requested_harness": "claude",
        "observed_harness": UNAVAILABLE,
        "requested_version": "current_installed",
        "observed_version": UNAVAILABLE,
        "requested_model": "current_default",
        "observed_model": UNAVAILABLE,
        "model_observation_classification": UNAVAILABLE,
        "observed_provider": UNAVAILABLE,
        "requested_effort": "current_default",
        "observed_effort": UNAVAILABLE,
        "task_type": "zero_agent_source_gap",
        "task_profile": "regular_qualification",
        "latency_milliseconds": latency_milliseconds,
        "native_turn_count": UNAVAILABLE,
        "native_tool_call_count": UNAVAILABLE,
        "checkpoint_quality": UNAVAILABLE,
        "repair_cycles": 0,
        "proof_integrity": SOURCE_ONLY_PROOF,
        "verification_depth": SOURCE_ONLY_PROOF,
        "exact_accepted_head": UNAVAILABLE,
        "target_claimed_green": False,
        "controller_gates_green": False,
        "independent_review_clean": False,
        "controller_verdict": BLOCKED_VERDICT,
        "limitations": list(CLAUDE_MATCHED_CONTROL_BLOCKERS),
        "source_observation_sha256": source_bundle_sha256,
        "source_bundle": source_bundle,
        "source_bundle_sha256": source_bundle_sha256,
        "launch_authorized": False,
        "delivery_authorized": False,
        "checkpoint_observed": False,
        "no_bleed_evaluated": False,
        "no_bleed_verified": False,
        "model_selection_authorized": False,
        "qualification_authorized": False,
        "promotion_authorized": False,
    }
    value["record_sha256"] = sha256_bytes(canonical_json_bytes(value))
    return value


def build_claude_matched_control_blocker_observation(
    *,
    run_id: str,
    latency_milliseconds: int,
) -> Dict[str, Any]:
    """Build one source-bound, non-authorizing Claude lane blocker."""

    run_id = validate_identifier(run_id, "run observation run id")
    if (
        isinstance(latency_milliseconds, bool)
        or not isinstance(latency_milliseconds, int)
        or latency_milliseconds < 0
        or latency_milliseconds > MAX_LATENCY_MILLISECONDS
    ):
        raise ValidationError("run observation latency is invalid")
    value = _build_claude_matched_control_blocker(
        run_id=run_id,
        latency_milliseconds=latency_milliseconds,
    )
    validate_claude_matched_control_blocker_observation(
        value,
        run_id=run_id,
        latency_milliseconds=latency_milliseconds,
    )
    return value


def validate_claude_matched_control_blocker_observation(
    value: Mapping[str, Any],
    *,
    run_id: str,
    latency_milliseconds: int,
) -> Dict[str, Any]:
    """Rederive one exact Claude blocker from the current source bundle."""

    if not isinstance(value, Mapping) or set(value) != _CLAUDE_RECORD_FIELDS:
        raise ValidationError("Claude blocker observation fields changed")
    supplied = dict(value)
    supplied_sha = validate_sha256(
        supplied.get("record_sha256"), "Claude blocker observation record"
    )
    core = dict(supplied)
    core.pop("record_sha256")
    if supplied_sha != sha256_bytes(canonical_json_bytes(core)):
        raise IdentityError("Claude blocker observation fingerprint changed")
    if (
        isinstance(latency_milliseconds, bool)
        or not isinstance(latency_milliseconds, int)
        or latency_milliseconds < 0
        or latency_milliseconds > MAX_LATENCY_MILLISECONDS
    ):
        raise ValidationError("run observation latency is invalid")
    expected = _build_claude_matched_control_blocker(
        run_id=validate_identifier(run_id, "run observation run id"),
        latency_milliseconds=latency_milliseconds,
    )
    if supplied != expected:
        raise IdentityError(
            "Claude blocker observation differs from its current source bundle"
        )
    validate_bounded_json(
        supplied,
        max_depth=6,
        max_items=64,
        max_string=4096,
        reject_sensitive_fields=True,
    )
    return supplied


def _private_observation_root(root: Path | str) -> Path:
    candidate = Path(root)
    if not candidate.is_absolute() or candidate.is_symlink() or not candidate.is_dir():
        raise ValidationError("run observation root must be an existing directory")
    candidate = candidate.resolve(strict=True)
    details = candidate.stat()
    if (
        not stat.S_ISDIR(details.st_mode)
        or details.st_uid != os.getuid()
        or stat.S_IMODE(details.st_mode) != 0o700
    ):
        raise IdentityError("run observation root is not user-private")
    return candidate


def _write_create_only_observation(
    root: Path | str,
    *,
    run_id: str,
    value: Mapping[str, Any],
) -> Path:
    root_path = _private_observation_root(root)
    run_id = validate_identifier(run_id, "run observation run id")
    path = root_path / (run_id + ".json")
    if path.exists() or path.is_symlink():
        raise ConflictError("run observation already exists")
    payload = canonical_json_bytes(dict(value)) + b"\n"
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".%s." % path.name,
        dir=str(root_path),
    )
    temporary = Path(temporary_name)
    try:
        try:
            os.fchmod(descriptor, 0o600)
            offset = 0
            while offset < len(payload):
                written = os.write(descriptor, payload[offset:])
                if written <= 0:
                    raise OSError("short run observation write")
                offset += written
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        try:
            os.link(str(temporary), str(path), follow_symlinks=False)
        except FileExistsError as exc:
            raise ConflictError("run observation already exists") from exc
        parent_descriptor = os.open(str(root_path), os.O_RDONLY)
        try:
            os.fsync(parent_descriptor)
        finally:
            os.close(parent_descriptor)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
    return path


def write_codex_doctor_run_observation(
    root: Path | str,
    observation: CodexDoctorObservation,
    *,
    run_id: str,
    task_type: str,
    task_profile: str,
    latency_milliseconds: int,
) -> Path:
    """Atomically create one immutable mode-0600 run observation."""

    run_id = validate_identifier(run_id, "run observation run id")
    value = build_codex_doctor_run_observation(
        observation,
        run_id=run_id,
        task_type=task_type,
        task_profile=task_profile,
        latency_milliseconds=latency_milliseconds,
    )
    return _write_create_only_observation(
        root,
        run_id=run_id,
        value=value,
    )


def write_claude_matched_control_blocker_observation(
    root: Path | str,
    *,
    run_id: str,
    latency_milliseconds: int,
) -> Path:
    """Atomically create one immutable source-only Claude blocker record."""

    run_id = validate_identifier(run_id, "run observation run id")
    value = build_claude_matched_control_blocker_observation(
        run_id=run_id,
        latency_milliseconds=latency_milliseconds,
    )
    return _write_create_only_observation(
        root,
        run_id=run_id,
        value=value,
    )


__all__ = [
    "BLOCKED_VERDICT",
    "CLAUDE_MATCHED_CONTROL_BLOCKERS",
    "RUN_OBSERVATION_SCHEMA",
    "SOURCE_ONLY_PROOF",
    "UNAVAILABLE",
    "ZERO_AGENT_CODEX_DOCTOR_KIND",
    "ZERO_AGENT_CLAUDE_MATCHED_CONTROL_BLOCKER_KIND",
    "build_claude_matched_control_blocker_observation",
    "build_codex_doctor_run_observation",
    "validate_claude_matched_control_blocker_observation",
    "validate_codex_doctor_run_observation",
    "write_claude_matched_control_blocker_observation",
    "write_codex_doctor_run_observation",
]
