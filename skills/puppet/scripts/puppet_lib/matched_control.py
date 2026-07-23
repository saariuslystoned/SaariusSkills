"""Compile-only Claude marker binding with no runtime or promotion authority."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, Mapping

from .adapter_manifest import QUALIFICATION_PROFILE
from .contracts import MANDATORY_HARD_GATES
from .errors import IdentityError, ValidationError
from .instruction_planes import (
    descriptor_fingerprint,
    validate_instruction_plane_descriptor,
)
from .instructions import compile_instruction_wrapper, validate_instruction_manifest
from .safety import (
    canonical_json_bytes,
    sha256_bytes,
    validate_identifier,
    validate_sha256,
)


COMPILED_MARKER_BINDING_SCHEMA = "puppet.claude-compiled-marker-binding/v1"
COMPILED_MARKER_SCOPE = "compiled_binding_only"
COMPILED_MARKER_RESULT = "not_evaluated"

_MARKER_DOMAIN = "puppet.claude-matched-control-marker/v1"
_MARKER_PREFIX = "PUPPET_CLAUDE_MATCHED_CONTROL_MARKER_V1="
_BINDING_FIELDS = {
    "schema",
    "scope",
    "target",
    "session_profile",
    "session",
    "run_id",
    "nonce_sha256",
    "descriptor_sha256",
    "instruction_manifest_sha256",
    "rendered_sha256",
    "marker_sha256",
    "instruction_policy_fingerprint",
    "effective_contract_fingerprint",
    "contract_identity_sha256",
    "workspace_identity_sha256",
    "run_identity_sha256",
    "requested_model",
    "observed_model",
    "config_fingerprint",
    "runtime_scan_authorized",
    "promotion_authorized",
    "qualification_authorized",
    "delivered",
    "checkpoint_observed",
    "lease_bound",
    "no_bleed_evaluated",
    "no_bleed_verified",
    "result",
}


@dataclass(frozen=True)
class CompiledMarkerInstruction:
    """In-memory controller result; repr and binding contain no instruction body."""

    _rendered: bytes = field(repr=False)
    _manifest_json: bytes = field(repr=False)
    _binding_json: bytes = field(repr=False)

    @property
    def rendered(self) -> bytes:
        """Return the exact activated-plane bytes for later controller delivery."""

        return bytes(self._rendered)

    @property
    def manifest(self) -> Dict[str, Any]:
        """Return a detached copy of the validated instruction manifest."""

        value = json.loads(self._manifest_json.decode("utf-8"))
        if not isinstance(value, dict):  # pragma: no cover - constructor invariant
            raise IdentityError("compiled marker manifest storage is invalid")
        return value

    @property
    def binding(self) -> Dict[str, Any]:
        """Return the body-free, explicitly non-promotable compile binding."""

        value = json.loads(self._binding_json.decode("utf-8"))
        if not isinstance(value, dict):  # pragma: no cover - constructor invariant
            raise IdentityError("compiled marker binding storage is invalid")
        return value


def _run_identity(value: Mapping[str, Any]) -> Dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != {"session", "run_id", "nonce"}:
        raise ValidationError("matched-control run identity fields are invalid")
    return {
        "session": validate_identifier(value.get("session"), "matched-control session"),
        "run_id": validate_identifier(value.get("run_id"), "matched-control run id"),
        "nonce": validate_identifier(value.get("nonce"), "matched-control nonce"),
    }


def _contract_identity(value: Mapping[str, Any]) -> Dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != {
        "fingerprint",
        "controller",
        "target",
        "task_profile",
    }:
        raise ValidationError("matched-control contract identity fields are invalid")
    fingerprint = validate_sha256(
        value.get("fingerprint"), "matched-control contract fingerprint"
    )
    controller = validate_identifier(
        value.get("controller"), "matched-control controller"
    )
    if (
        value.get("target") != "claude"
        or value.get("task_profile") != QUALIFICATION_PROFILE
    ):
        raise ValidationError("matched-control contract identity is not exact Pass B")
    return {
        "fingerprint": fingerprint,
        "controller": controller,
        "target": "claude",
        "task_profile": QUALIFICATION_PROFILE,
    }


def _workspace_identity(value: Mapping[str, Any]) -> Dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != {
        "fixture_fingerprint",
        "workspace",
    }:
        raise ValidationError("matched-control workspace identity fields are invalid")
    fingerprint = validate_sha256(
        value.get("fixture_fingerprint"), "matched-control fixture fingerprint"
    )
    if value.get("workspace") != "isolated_conformance_fixture":
        raise ValidationError("matched-control workspace identity is not isolated")
    return {
        "fixture_fingerprint": fingerprint,
        "workspace": "isolated_conformance_fixture",
    }


def _marker_token(
    *, descriptor_sha256: str, session: str, run_id: str, nonce: str
) -> bytes:
    digest = sha256_bytes(
        canonical_json_bytes(
            {
                "domain": _MARKER_DOMAIN,
                "descriptor_sha256": descriptor_sha256,
                "session": session,
                "run_id": run_id,
                "nonce": nonce,
            }
        )
    )
    return (_MARKER_PREFIX + digest).encode("ascii")


def _marker_directive(token: bytes) -> str:
    return (
        "Controller matched-control checkpoint requirement: in each requested "
        "conformance handoff, include exactly one claim whose marker value is `"
        + token.decode("ascii")
        + "`. Do not copy that value anywhere else."
    )


def _identity_sha256(value: Mapping[str, Any]) -> str:
    return sha256_bytes(canonical_json_bytes(dict(value)))


def compile_claude_marker_instruction(
    *,
    descriptor: Mapping[str, Any],
    task: str,
    contract_identity: Mapping[str, Any],
    workspace_identity: Mapping[str, Any],
    run_identity: Mapping[str, Any],
) -> CompiledMarkerInstruction:
    """Compile one source-owned marker into Claude's activated native plane.

    This function does not materialize, deliver, scan, lease, launch, journal,
    attest, or qualify anything. The returned binding is compile evidence only.
    """

    normalized_descriptor = validate_instruction_plane_descriptor(descriptor)
    if (
        normalized_descriptor["target"]["harness"] != "claude"
        or normalized_descriptor["plane"] != "per_run_additive"
        or normalized_descriptor["status"]
        != {"surface": "factual", "activation": "qualification_only"}
        or normalized_descriptor["target"]["version"] != "2.1.215"
        or normalized_descriptor["target"]["observed_model"] != "unavailable"
        or normalized_descriptor["target"]["config_fingerprint"] != "unavailable"
    ):
        raise ValidationError(
            "matched-control requires the exact unobserved-default Claude additive plane"
        )

    normalized_contract = _contract_identity(contract_identity)
    normalized_workspace = _workspace_identity(workspace_identity)
    normalized_run = _run_identity(run_identity)
    descriptor_sha = descriptor_fingerprint(normalized_descriptor)
    token = _marker_token(descriptor_sha256=descriptor_sha, **normalized_run)
    activated_task = task + "\n\n" + _marker_directive(token)
    compiled = compile_instruction_wrapper(
        target="claude",
        task=activated_task,
        contract_identity=normalized_contract,
        workspace_identity=normalized_workspace,
        run_identity=normalized_run,
        session_profile="regular",
        model_binding="default",
        effort_binding="default",
        runtime_contract_layer={
            "mutation_owner": "none",
            "allowed_modes": ["read", "test"],
            "hard_gates": sorted(MANDATORY_HARD_GATES),
        },
    )
    manifest = validate_instruction_manifest(compiled.manifest, target="claude")
    if manifest["run_identity"] != normalized_run:
        raise IdentityError("compiled marker run identity changed")
    if sha256_bytes(compiled.rendered) != manifest["rendered_sha256"]:
        raise IdentityError("compiled marker bytes changed")
    if compiled.rendered.count(token) != 1:
        raise IdentityError("compiled marker must occur exactly once")

    manifest_json = canonical_json_bytes(manifest)
    binding: Dict[str, Any] = {
        "schema": COMPILED_MARKER_BINDING_SCHEMA,
        "scope": COMPILED_MARKER_SCOPE,
        "target": "claude",
        "session_profile": "regular",
        "session": normalized_run["session"],
        "run_id": normalized_run["run_id"],
        "nonce_sha256": sha256_bytes(normalized_run["nonce"].encode("utf-8")),
        "descriptor_sha256": descriptor_sha,
        "instruction_manifest_sha256": sha256_bytes(manifest_json + b"\n"),
        "rendered_sha256": manifest["rendered_sha256"],
        "marker_sha256": sha256_bytes(token),
        "instruction_policy_fingerprint": manifest["instruction_policy_fingerprint"],
        "effective_contract_fingerprint": manifest["effective_contract_fingerprint"],
        "contract_identity_sha256": _identity_sha256(manifest["contract_identity"]),
        "workspace_identity_sha256": _identity_sha256(manifest["workspace_identity"]),
        "run_identity_sha256": _identity_sha256(manifest["run_identity"]),
        "requested_model": normalized_descriptor["target"]["requested_model"],
        "observed_model": normalized_descriptor["target"]["observed_model"],
        "config_fingerprint": normalized_descriptor["target"]["config_fingerprint"],
        "runtime_scan_authorized": False,
        "promotion_authorized": False,
        "qualification_authorized": False,
        "delivered": False,
        "checkpoint_observed": False,
        "lease_bound": False,
        "no_bleed_evaluated": False,
        "no_bleed_verified": False,
        "result": COMPILED_MARKER_RESULT,
    }
    if set(binding) != _BINDING_FIELDS:
        raise IdentityError("compiled marker binding fields changed")
    binding_json = canonical_json_bytes(binding)
    if token in binding_json:
        raise IdentityError("compiled marker binding contains instruction body")

    return CompiledMarkerInstruction(
        _rendered=bytes(compiled.rendered),
        _manifest_json=manifest_json,
        _binding_json=binding_json,
    )


__all__ = [
    "COMPILED_MARKER_BINDING_SCHEMA",
    "COMPILED_MARKER_SCOPE",
    "COMPILED_MARKER_RESULT",
    "CompiledMarkerInstruction",
    "compile_claude_marker_instruction",
]
