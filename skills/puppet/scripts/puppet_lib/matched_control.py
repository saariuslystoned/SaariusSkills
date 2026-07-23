"""Compile-only Claude marker binding with no runtime or promotion authority."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Mapping

from .adapter_manifest import AdapterManifest, QUALIFICATION_PROFILE
from .authority import AUTHORITY_ID
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
from .plane_activation import ActivationPlan


COMPILED_MARKER_BINDING_SCHEMA = "puppet.claude-compiled-marker-binding/v1"
COMPILED_MARKER_SCOPE = "compiled_binding_only"
COMPILED_MARKER_RESULT = "not_evaluated"
ACTIVATION_MARKER_JOIN_SCHEMA = "puppet.claude-activation-marker-join/v1"
ACTIVATION_MARKER_JOIN_SCOPE = "activation_plan_join_only"
ACTIVATION_MARKER_JOIN_RESULT = "not_evaluated"

_MARKER_DOMAIN = "puppet.claude-matched-control-marker/v1"
_MARKER_PREFIX = "PUPPET_CLAUDE_MATCHED_CONTROL_MARKER_V1="
_MARKER_PATTERN = re.compile(rb"PUPPET_CLAUDE_MATCHED_CONTROL_MARKER_V1=[0-9a-f]{64}")
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
_ACTIVATION_JOIN_FIELDS = {
    "schema",
    "scope",
    "result",
    "target",
    "session_profile",
    "session",
    "run_id",
    "controller",
    "campaign_id",
    "goal_fingerprint",
    "authority_id",
    "compiled_binding_sha256",
    "marker_sha256",
    "descriptor_sha256",
    "instruction_manifest_sha256",
    "rendered_sha256",
    "activation_plan_sha256",
    "adapter_manifest_sha256",
    "adapter_implementation_sha256",
    "activation_lifecycle_delivery_only",
    "runtime_scan_authorized",
    "checkpoint_observed",
    "no_bleed_evaluated",
    "no_bleed_verified",
    "qualification_authorized",
    "promotion_authorized",
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


def validate_compiled_marker_binding(
    compiled: CompiledMarkerInstruction,
) -> Dict[str, Any]:
    """Rejoin a compile-only binding to its exact in-memory instruction bytes."""

    if not isinstance(compiled, CompiledMarkerInstruction):
        raise ValidationError("compiled marker instruction type is invalid")
    manifest = validate_instruction_manifest(compiled.manifest, target="claude")
    binding = compiled.binding
    if not isinstance(binding, dict) or set(binding) != _BINDING_FIELDS:
        raise ValidationError("compiled marker binding fields changed")
    if (
        binding.get("schema") != COMPILED_MARKER_BINDING_SCHEMA
        or binding.get("scope") != COMPILED_MARKER_SCOPE
        or binding.get("result") != COMPILED_MARKER_RESULT
        or binding.get("target") != "claude"
        or binding.get("session_profile") != "regular"
        or binding.get("requested_model") != "default"
        or binding.get("observed_model") != "unavailable"
        or binding.get("config_fingerprint") != "unavailable"
    ):
        raise ValidationError("compiled marker binding status is invalid")
    for name in (
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
    ):
        validate_sha256(binding.get(name), name.replace("_", " "))
    for name in (
        "runtime_scan_authorized",
        "promotion_authorized",
        "qualification_authorized",
        "delivered",
        "checkpoint_observed",
        "lease_bound",
        "no_bleed_evaluated",
        "no_bleed_verified",
    ):
        if binding.get(name) is not False:
            raise ValidationError("compiled marker binding gained runtime authority")

    rendered = compiled.rendered
    markers = _MARKER_PATTERN.findall(rendered)
    if len(markers) != 1 or rendered.count(markers[0]) != 1:
        raise IdentityError("compiled marker must occur exactly once")
    manifest_sha = sha256_bytes(canonical_json_bytes(manifest) + b"\n")
    run_identity = _run_identity(manifest.get("run_identity", {}))
    contract_identity = _contract_identity(manifest.get("contract_identity", {}))
    workspace_identity = _workspace_identity(manifest.get("workspace_identity", {}))
    if (
        binding["session"] != run_identity["session"]
        or binding["run_id"] != run_identity["run_id"]
        or binding["nonce_sha256"]
        != sha256_bytes(run_identity["nonce"].encode("utf-8"))
        or binding["instruction_manifest_sha256"] != manifest_sha
        or binding["rendered_sha256"] != sha256_bytes(rendered)
        or binding["rendered_sha256"] != manifest.get("rendered_sha256")
        or binding["marker_sha256"] != sha256_bytes(markers[0])
        or binding["instruction_policy_fingerprint"]
        != manifest.get("instruction_policy_fingerprint")
        or binding["effective_contract_fingerprint"]
        != manifest.get("effective_contract_fingerprint")
        or binding["contract_identity_sha256"] != _identity_sha256(contract_identity)
        or binding["workspace_identity_sha256"] != _identity_sha256(workspace_identity)
        or binding["run_identity_sha256"] != _identity_sha256(run_identity)
    ):
        raise IdentityError("compiled marker binding identity changed")
    if markers[0] in canonical_json_bytes(binding):
        raise IdentityError("compiled marker binding contains instruction body")
    return binding


def bind_claude_marker_activation_plan(
    compiled: CompiledMarkerInstruction,
    *,
    activation_plan: ActivationPlan,
    descriptor: Mapping[str, Any],
    adapter_manifest: AdapterManifest | Mapping[str, Any],
    controller: str,
    campaign_id: str,
    goal_fingerprint: str,
) -> Dict[str, Any]:
    """Join source-owned marker compilation to one exact activation plan.

    The returned record authorizes no runtime scan, qualification, or promotion.
    It only proves that the marker-bearing bytes admitted for the existing
    activation-lifecycle probe match the descriptor, plan, and current adapter.
    """

    binding = validate_compiled_marker_binding(compiled)
    if not isinstance(activation_plan, ActivationPlan):
        raise ValidationError("activation marker join requires an activation plan")
    plan = ActivationPlan.from_dict(activation_plan.to_dict())
    normalized_descriptor = validate_instruction_plane_descriptor(descriptor)
    manifest = (
        adapter_manifest
        if isinstance(adapter_manifest, AdapterManifest)
        else AdapterManifest.from_dict(dict(adapter_manifest))
    )
    manifest = AdapterManifest.from_dict(manifest.raw)
    descriptor_sha = descriptor_fingerprint(normalized_descriptor)
    instruction_manifest = validate_instruction_manifest(
        compiled.manifest, target="claude"
    )
    normalized_controller = validate_identifier(controller, "marker join controller")
    if (
        normalized_descriptor["target"]["harness"] != "claude"
        or normalized_descriptor["target"]["adapter_manifest_sha256"]
        != manifest.fingerprint
        or binding["descriptor_sha256"] != descriptor_sha
        or plan.raw["descriptor_sha256"] != descriptor_sha
        or plan.raw["instruction_manifest_sha256"]
        != binding["instruction_manifest_sha256"]
        or plan.raw["effective_contract_sha256"] != binding["rendered_sha256"]
        or plan.raw["effective_contract_fingerprint"]
        != instruction_manifest["effective_contract_fingerprint"]
        or plan.raw["adapter_manifest_sha256"] != manifest.fingerprint
        or plan.raw["adapter_implementation_sha256"]
        != manifest.raw["adapter_fingerprint"]
        or instruction_manifest["contract_identity"]["controller"]
        != normalized_controller
    ):
        raise IdentityError("activation marker join identity changed")

    joined: Dict[str, Any] = {
        "schema": ACTIVATION_MARKER_JOIN_SCHEMA,
        "scope": ACTIVATION_MARKER_JOIN_SCOPE,
        "result": ACTIVATION_MARKER_JOIN_RESULT,
        "target": "claude",
        "session_profile": "regular",
        "session": binding["session"],
        "run_id": binding["run_id"],
        "controller": normalized_controller,
        "campaign_id": validate_identifier(campaign_id, "marker join campaign"),
        "goal_fingerprint": validate_sha256(
            goal_fingerprint, "marker join goal fingerprint"
        ),
        "authority_id": AUTHORITY_ID,
        "compiled_binding_sha256": sha256_bytes(canonical_json_bytes(binding)),
        "marker_sha256": binding["marker_sha256"],
        "descriptor_sha256": descriptor_sha,
        "instruction_manifest_sha256": binding["instruction_manifest_sha256"],
        "rendered_sha256": binding["rendered_sha256"],
        "activation_plan_sha256": plan.plan_sha256,
        "adapter_manifest_sha256": manifest.fingerprint,
        "adapter_implementation_sha256": manifest.raw["adapter_fingerprint"],
        "activation_lifecycle_delivery_only": True,
        "runtime_scan_authorized": False,
        "checkpoint_observed": False,
        "no_bleed_evaluated": False,
        "no_bleed_verified": False,
        "qualification_authorized": False,
        "promotion_authorized": False,
    }
    if set(joined) != _ACTIVATION_JOIN_FIELDS:
        raise IdentityError("activation marker join fields changed")
    if _MARKER_PATTERN.search(canonical_json_bytes(joined)):
        raise IdentityError("activation marker join contains instruction body")
    return joined


def validate_claude_marker_activation_join(
    value: Mapping[str, Any],
    compiled: CompiledMarkerInstruction,
    *,
    activation_plan: ActivationPlan,
    descriptor: Mapping[str, Any],
    adapter_manifest: AdapterManifest | Mapping[str, Any],
    controller: str,
    campaign_id: str,
    goal_fingerprint: str,
) -> Dict[str, Any]:
    """Rebuild and compare a saved body-free activation marker join."""

    if not isinstance(value, Mapping) or set(value) != _ACTIVATION_JOIN_FIELDS:
        raise ValidationError("activation marker join fields changed")
    expected = bind_claude_marker_activation_plan(
        compiled,
        activation_plan=activation_plan,
        descriptor=descriptor,
        adapter_manifest=adapter_manifest,
        controller=controller,
        campaign_id=campaign_id,
        goal_fingerprint=goal_fingerprint,
    )
    if dict(value) != expected:
        raise IdentityError("saved activation marker join identity changed")
    return expected


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
    "ACTIVATION_MARKER_JOIN_SCHEMA",
    "ACTIVATION_MARKER_JOIN_SCOPE",
    "ACTIVATION_MARKER_JOIN_RESULT",
    "COMPILED_MARKER_BINDING_SCHEMA",
    "COMPILED_MARKER_SCOPE",
    "COMPILED_MARKER_RESULT",
    "CompiledMarkerInstruction",
    "bind_claude_marker_activation_plan",
    "compile_claude_marker_instruction",
    "validate_claude_marker_activation_join",
    "validate_compiled_marker_binding",
]
