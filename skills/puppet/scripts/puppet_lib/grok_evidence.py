"""Strict admission for sanitized Grok Build Pass-A parser/catalog evidence.

The admitted packet is source-only. It binds exact historical executable,
help, parser, and clean-root catalog observations without granting live launch,
model-selection, qualification, or promotion authority.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Mapping

from .errors import IdentityError, ValidationError
from .grok_launch import (
    GROK_EXECUTABLE_SHA256,
    GROK_MAIN_HELP_SHA256,
    GROK_VERSION_OUTPUT_SHA256,
)
from .instruction_planes import GROK_BUILD_VERSION
from .safety import (
    canonical_json_bytes,
    read_json,
    sha256_bytes,
    validate_bounded_json,
    validate_sha1,
    validate_sha256,
)


GROK_PASS_A_EVIDENCE_SCHEMA = "puppet.grok-pass-a-evidence-admission/v1"
GROK_PASS_A_EVIDENCE_STATE = "prior_evidence_admitted_source_only"
GROK_PASS_A_OBSERVATION_SOURCE_HEAD = "b8cce94bf2a4a62f974207a95abcfe1668412b90"
GROK_PASS_A_OBSERVATION_SOURCE_DATE = "2026-07-22T11:07:44-04:00"
GROK_PASS_A_EVIDENCE_REVISION = "c711c6b11ef529e1ff7860bef4232ad03c83e6ef"
GROK_PASS_A_EVIDENCE_DATE = "2026-07-22T12:12:31-04:00"
GROK_PASS_A_EVIDENCE_BLOB_SHA1 = "0e28e5d75f91f7415b619eaa27a6ce7b549750cc"
GROK_PASS_A_EVIDENCE_ARTIFACT_SHA256 = (
    "d765826af6a19b741119fee4f3d40e5e62d2b28d44bcbbe6d0ccf727addd039c"
)
GROK_VERSION_TEXT = "grok 0.2.106 (bde89716f679)"
GROK_AGENT_HELP_SHA256 = (
    "80eca1cc827e677c5d4310fe60ccaa941627cc688189405742e69e4f4ec734d3"
)
GROK_CLEAN_ROOT_MODEL_OUTPUT_SHA256 = (
    "5c7ad803cc612bd198e2f200f4fac1340800382a0e321c9b69e2082085af18b8"
)
GROK_CLEAN_ROOT_DEFAULT_MODEL = "grok-4.5"
GROK_PASS_A_LIMITATIONS = (
    "grok_authentication_isolation_unapproved",
    "grok_authenticated_default_model_unobserved",
    "grok_authenticated_default_effort_unobserved",
    "grok_sandbox_off_live_semantics_unproved",
    "grok_always_approve_live_semantics_unproved",
    "grok_native_instruction_plane_unqualified",
    "grok_leader_child_halt_authority_unmodeled",
    "grok_session_resume_semantics_unproved",
    "grok_status_surface_unavailable",
    "grok_ordinary_session_no_bleed_unproved",
    "grok_direct_cockpit_lifecycle_unproved",
)
_AUTHORITY_FIELDS = (
    "live_session_started",
    "private_store_accessed",
    "config_mutated",
    "live_semantics_verified",
    "launch_authorized",
    "model_selection_authorized",
    "qualification_authorized",
    "promotion_authorized",
)
_RECORD_FIELDS = {
    "schema",
    "state",
    "target",
    "target_version",
    "version_text",
    "provenance",
    "artifact_hashes",
    "parser_facts",
    "clean_root_catalog",
    "admission_rows",
    "limitations",
    *_AUTHORITY_FIELDS,
    "record_sha256",
}


def _expected_core() -> Dict[str, Any]:
    return {
        "schema": GROK_PASS_A_EVIDENCE_SCHEMA,
        "state": GROK_PASS_A_EVIDENCE_STATE,
        "target": "grok",
        "target_version": GROK_BUILD_VERSION,
        "version_text": GROK_VERSION_TEXT,
        "provenance": {
            "source_kind": "public_repository_commit",
            "repository": "saariuslystoned/SaariusSkills",
            "observation_source_revision": GROK_PASS_A_OBSERVATION_SOURCE_HEAD,
            "observation_source_recorded_at": GROK_PASS_A_OBSERVATION_SOURCE_DATE,
            "evidence_artifact_revision": GROK_PASS_A_EVIDENCE_REVISION,
            "evidence_artifact_recorded_at": GROK_PASS_A_EVIDENCE_DATE,
            "owner": "puppet_grok_parser_evidence_lane",
            "artifact_path": "plans/puppet/harnesses/grok-regular.md",
            "artifact_blob_sha1": GROK_PASS_A_EVIDENCE_BLOB_SHA1,
            "artifact_sha256": GROK_PASS_A_EVIDENCE_ARTIFACT_SHA256,
            "proof_scope": "sanitized_parser_help_and_clean_root_catalog",
            "freshness": "dated_not_current",
            "platform": "macos_arm64",
            "license": "MIT",
            "attribution_path": "LICENSE",
        },
        "artifact_hashes": {
            "executable_sha256": GROK_EXECUTABLE_SHA256,
            "version_output_sha256": GROK_VERSION_OUTPUT_SHA256,
            "main_help_sha256": GROK_MAIN_HELP_SHA256,
            "agent_help_sha256": GROK_AGENT_HELP_SHA256,
            "clean_root_model_output_sha256": GROK_CLEAN_ROOT_MODEL_OUTPUT_SHA256,
        },
        "parser_facts": {
            "permission_mode_flag": "--always-approve",
            "sandbox_disable_argv": ["--sandbox", "off"],
            "additive_text_alias": "--append-system-prompt=--rules",
            "rejected_additive_file_flags": [
                "--append-system-prompt-file",
                "--rules-file",
            ],
            "replacement_system_flags": [
                "--system-prompt",
                "--system-prompt-override",
            ],
            "model_flag": "--model",
            "reasoning_effort_flag": "--reasoning-effort",
            "task_input_file_flag": "--prompt-file",
            "interactive_transport": "native_tui",
            "workspace_flags": ["--cwd", "--worktree"],
            "session_identity_flag": "--session-id",
            "resume_flags": ["--resume", "--continue"],
            "leader_socket_flag": "--leader-socket",
            "status_surface": "unavailable",
            "agent_selector_scope": "whole_agent_profile",
        },
        "clean_root_catalog": {
            "authentication_state": "unauthenticated",
            "default_model": GROK_CLEAN_ROOT_DEFAULT_MODEL,
            "authenticated_model": "unavailable",
            "authenticated_effort": "unavailable",
            "observation_scope": "clean_root_catalog_only",
        },
        "admission_rows": [
            {
                "claim_id": "artifact_identity_candidate",
                "invariant": (
                    "exact_historical_0_2_106_binary_version_and_help_hashes"
                ),
                "proof_artifact": (
                    "plans/puppet/harnesses/grok-regular.md@"
                    + GROK_PASS_A_EVIDENCE_REVISION
                ),
                "proof_strength": "hash_bound_historical_local_census",
                "mechanism_match": "artifact_hash_census_only",
                "version_match": "exact_0_2_106_source_tuple",
                "portability_assumptions": [
                    "macos_arm64",
                    "operator_local_install_layout_not_portable",
                ],
                "operator_assumptions": [
                    "read_only_source_lane",
                    "no_live_store_contents_admitted",
                ],
                "license_attribution": "MIT:LICENSE",
                "decision": "design_input_only",
                "deterministic_tests": [
                    "tests.test_puppet_grok_evidence",
                    "tests.test_puppet_grok_launch",
                ],
                "remaining_live_delta": [
                    "re_resolve_current_launcher_and_runtime_identity",
                    "rerun_version_and_help_hashes",
                ],
            },
            {
                "claim_id": "parser_capability_candidates",
                "invariant": ("exact_help_and_parse_probes_expose_candidate_controls"),
                "proof_artifact": (
                    "plans/puppet/harnesses/grok-regular.md@"
                    + GROK_PASS_A_EVIDENCE_REVISION
                ),
                "proof_strength": "exact_help_hash_plus_bounded_parse_probes",
                "mechanism_match": "parser_acceptance_not_runtime_semantics",
                "version_match": "exact_0_2_106_source_tuple",
                "portability_assumptions": [
                    "macos_arm64",
                    "cli_parser_surface_may_drift",
                ],
                "operator_assumptions": [
                    "no_model_session_started",
                    "no_live_config_read",
                ],
                "license_attribution": "MIT:LICENSE",
                "decision": "design_input_only",
                "deterministic_tests": [
                    "tests.test_puppet_grok_evidence",
                    "tests.test_puppet_instruction_planes.GrokWorkspaceDescriptorTests",
                ],
                "remaining_live_delta": [
                    "rerun_current_exact_help_and_parser_probes",
                    "prove_permission_and_sandbox_runtime_semantics",
                    "prove_session_resume_and_status_semantics",
                ],
            },
            {
                "claim_id": "clean_root_catalog_candidate",
                "invariant": (
                    "unauthenticated_clean_root_catalog_names_grok_4_5_default"
                ),
                "proof_artifact": (
                    "plans/puppet/harnesses/grok-regular.md@"
                    + GROK_PASS_A_EVIDENCE_REVISION
                ),
                "proof_strength": "hash_bound_clean_root_catalog_output",
                "mechanism_match": "catalog_observation_not_live_model_selection",
                "version_match": "exact_0_2_106_source_tuple",
                "portability_assumptions": [
                    "catalog_may_differ_after_authentication",
                    "provider_default_may_change",
                ],
                "operator_assumptions": [
                    "isolated_empty_roots",
                    "unauthenticated_observation_only",
                ],
                "license_attribution": "MIT:LICENSE",
                "decision": "fresh_live_proof",
                "deterministic_tests": [
                    "tests.test_puppet_grok_evidence",
                    "tests.test_puppet_grok_launch",
                ],
                "remaining_live_delta": [
                    "human_authenticate_lane_owned_private_roots",
                    "observe_same_runtime_default_model",
                    "observe_same_runtime_default_effort",
                ],
            },
        ],
        "limitations": list(GROK_PASS_A_LIMITATIONS),
        "live_session_started": False,
        "private_store_accessed": False,
        "config_mutated": False,
        "live_semantics_verified": False,
        "launch_authorized": False,
        "model_selection_authorized": False,
        "qualification_authorized": False,
        "promotion_authorized": False,
    }


def expected_grok_pass_a_evidence() -> Dict[str, Any]:
    """Return the one exact source-only Grok Pass-A evidence record."""

    value = _expected_core()
    value["record_sha256"] = sha256_bytes(canonical_json_bytes(value))
    return value


def validate_grok_pass_a_evidence(value: Mapping[str, Any]) -> Dict[str, Any]:
    """Validate and rederive one exact sanitized Grok evidence packet."""

    if not isinstance(value, Mapping) or set(value) != _RECORD_FIELDS:
        raise ValidationError("Grok Pass-A evidence fields changed")
    supplied = dict(value)
    supplied_sha = validate_sha256(
        supplied.get("record_sha256"), "Grok Pass-A evidence"
    )
    core = dict(supplied)
    core.pop("record_sha256")
    if supplied_sha != sha256_bytes(canonical_json_bytes(core)):
        raise IdentityError("Grok Pass-A evidence fingerprint changed")
    provenance = supplied.get("provenance")
    if not isinstance(provenance, Mapping):
        raise ValidationError("Grok Pass-A provenance is invalid")
    validate_sha1(
        provenance.get("observation_source_revision"),
        "Grok Pass-A observation source revision",
    )
    validate_sha1(
        provenance.get("evidence_artifact_revision"),
        "Grok Pass-A evidence artifact revision",
    )
    validate_sha1(
        provenance.get("artifact_blob_sha1"), "Grok Pass-A source artifact blob"
    )
    validate_sha256(provenance.get("artifact_sha256"), "Grok Pass-A source artifact")
    artifact_hashes = supplied.get("artifact_hashes")
    if not isinstance(artifact_hashes, Mapping):
        raise ValidationError("Grok Pass-A artifact hashes are invalid")
    for name, digest in artifact_hashes.items():
        validate_sha256(digest, "Grok %s" % name.replace("_", " "))
    if any(supplied.get(name) is not False for name in _AUTHORITY_FIELDS):
        raise IdentityError("Grok Pass-A evidence gained runtime authority")
    expected = expected_grok_pass_a_evidence()
    if supplied != expected:
        raise IdentityError("Grok Pass-A evidence differs from admitted facts")
    validate_bounded_json(
        supplied,
        max_depth=6,
        max_items=64,
        max_string=4096,
        reject_sensitive_fields=True,
    )
    return supplied


def load_grok_pass_a_evidence(path: Path | str) -> Dict[str, Any]:
    """Load an exact canonical source packet without consuming it at runtime."""

    path = Path(path)
    value = read_json(path, max_bytes=16384, reject_sensitive_fields=True)
    if path.read_bytes() != canonical_json_bytes(value) + b"\n":
        raise IdentityError("Grok Pass-A evidence is not canonical JSON")
    return validate_grok_pass_a_evidence(value)


__all__ = [
    "GROK_AGENT_HELP_SHA256",
    "GROK_CLEAN_ROOT_DEFAULT_MODEL",
    "GROK_CLEAN_ROOT_MODEL_OUTPUT_SHA256",
    "GROK_PASS_A_EVIDENCE_SCHEMA",
    "GROK_PASS_A_EVIDENCE_STATE",
    "GROK_PASS_A_LIMITATIONS",
    "GROK_PASS_A_EVIDENCE_ARTIFACT_SHA256",
    "GROK_PASS_A_EVIDENCE_BLOB_SHA1",
    "GROK_PASS_A_EVIDENCE_DATE",
    "GROK_PASS_A_EVIDENCE_REVISION",
    "GROK_PASS_A_OBSERVATION_SOURCE_DATE",
    "GROK_PASS_A_OBSERVATION_SOURCE_HEAD",
    "GROK_VERSION_TEXT",
    "expected_grok_pass_a_evidence",
    "load_grok_pass_a_evidence",
    "validate_grok_pass_a_evidence",
]
