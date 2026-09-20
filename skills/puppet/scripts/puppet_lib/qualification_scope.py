"""Versioned reusable harness-compatibility evidence.

Compatibility evidence answers whether a selected harness, transport, and
shared-controller/authority pair is still current. It never authorizes a task
or a live launch. Task campaign/goal/authorization identity is a separate
scope and cannot be copied from compatibility evidence.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

from .errors import UnsupportedError, ValidationError
from .safety import (
    canonical_json_bytes,
    sha256_bytes,
    sha256_file,
    validate_identifier,
    validate_sha256,
)


QUALIFICATION_SCOPE_SCHEMA = "puppet.qualification-scope/v1"
TASK_SCOPE_SCHEMA = "puppet.task-authorization-scope/v1"
QUALIFICATION_SCOPE_VERSION = 1

_TARGETS = frozenset({"agy", "cursor", "claude", "codex", "grok"})

# Shared transport, controller, authority, subscription-profile,
# runtime-signal, and instruction-plane validator owners. Adding a path
# here is a deliberate invalidation event for every target.
_SHARED_SOURCE_PATHS: Tuple[str, ...] = (
    "scripts/adapter_lab.py",
    "scripts/profile_login.py",
    "scripts/puppet.py",
    "scripts/puppet_lib/adapter_manifest.py",
    "scripts/puppet_lib/adapters.py",
    "scripts/puppet_lib/authority.py",
    "scripts/puppet_lib/beacons.py",
    "scripts/puppet_lib/caller.py",
    "scripts/puppet_lib/campaign.py",
    "scripts/puppet_lib/census.py",
    "scripts/puppet_lib/conformance.py",
    "scripts/puppet_lib/contracts.py",
    "scripts/puppet_lib/diagnostics.py",
    "scripts/puppet_lib/errors.py",
    "scripts/puppet_lib/handoffs.py",
    "scripts/puppet_lib/halt_control.py",
    "scripts/puppet_lib/instruction_planes.py",
    "scripts/puppet_lib/instructions.py",
    "scripts/puppet_lib/journal.py",
    "scripts/puppet_lib/launch.py",
    "scripts/puppet_lib/operator_plan.py",
    "scripts/puppet_lib/probe.py",
    "scripts/puppet_lib/profiles.py",
    "scripts/puppet_lib/qualification_scope.py",
    "scripts/puppet_lib/registry.py",
    "scripts/puppet_lib/safety.py",
    "scripts/puppet_lib/session.py",
    "scripts/puppet_lib/signal_exec.py",
    "scripts/puppet_lib/state.py",
    "scripts/puppet_lib/subscription_profiles.py",
    "scripts/puppet_lib/target_population.py",
    "scripts/puppet_lib/transport.py",
    "scripts/puppet_lib/verdicts.py",
    "scripts/viewer_attach.py",
    "templates/instructions/catalog.json",
    "templates/instructions/lifecycle/regular.md",
    "templates/instructions/model/default-unresolved.md",
    "templates/instructions/universal.md",
)

_TARGET_SOURCE_PATHS: Dict[str, Tuple[str, ...]] = {
    "agy": (
        "scripts/puppet_lib/agy_launch.py",
        "scripts/puppet_lib/agy_print.py",
        "scripts/puppet_lib/agy_workspace_plane.py",
        "templates/instructions/harness/agy.md",
    ),
    "cursor": (
        "scripts/puppet_lib/cursor_acp.py",
        "scripts/puppet_lib/cursor_qualification.py",
        "scripts/puppet_lib/cursor_startup_gates.py",
        "scripts/puppet_lib/cursor_workspace_plane.py",
        "scripts/puppet_lib/plane_activation.py",
        "templates/instructions/harness/cursor.md",
    ),
    "claude": (
        "scripts/puppet_lib/claude_admission.py",
        "scripts/puppet_lib/claude_paired_qualification.py",
        "scripts/puppet_lib/claude_startup_gates.py",
        "scripts/puppet_lib/matched_control.py",
        "scripts/puppet_lib/matched_control_authority.py",
        "scripts/puppet_lib/matched_control_signal.py",
        "templates/instructions/harness/claude.md",
    ),
    "codex": (
        "scripts/puppet_lib/codex_admission.py",
        "scripts/puppet_lib/codex_launch.py",
        "scripts/puppet_lib/codex_qualification.py",
        "scripts/puppet_lib/codex_workspace_plane.py",
        "templates/instructions/harness/codex.md",
    ),
    "grok": (
        "scripts/puppet_lib/grok_admission.py",
        "scripts/puppet_lib/grok_evidence.py",
        "scripts/puppet_lib/grok_halt.py",
        "scripts/puppet_lib/grok_launch.py",
        "scripts/puppet_lib/grok_qualification.py",
        "scripts/puppet_lib/grok_shared_leader.py",
        "scripts/puppet_lib/grok_subscription_adoption.py",
        "scripts/puppet_lib/grok_workspace_plane.py",
        "templates/instructions/harness/grok.md",
    ),
}

_TRANSPORT_SOURCE_PATHS: Dict[str, Tuple[str, ...]] = {
    "tmux": ("scripts/puppet_lib/tmux.py",),
    "agy-print": ("scripts/puppet_lib/agy_print.py",),
    "cursor-acp": ("scripts/puppet_lib/cursor_acp.py",),
}

_SCOPE_FIELDS = frozenset(
    {
        "schema",
        "target",
        "transport",
        "harness_scope",
        "transport_authority_scope",
        "instruction_policy_fingerprint",
        "fingerprint",
    }
)
_HARNESS_SCOPE_FIELDS = frozenset(
    {
        "target_source_fingerprint",
        "identity",
        "model_effort",
    }
)
_TRANSPORT_AUTHORITY_FIELDS = frozenset({"shared_source_fingerprint"})
_IDENTITY_FIELDS = frozenset(
    {
        "executable_fingerprint",
        "execution_fingerprint",
        "version_fingerprint",
        "platform_fingerprint",
        "protocol_fingerprint",
    }
)
_MODEL_EFFORT_FIELDS = frozenset(
    {
        "requested_model",
        "requested_effort",
        "model_flag",
        "effort_flag",
        "observed_model",
        "observed_effort",
    }
)
_TASK_SCOPE_FIELDS = frozenset(
    {
        "schema",
        "controller",
        "campaign_id",
        "goal_fingerprint",
        "fingerprint",
    }
)


def _skill_root(source_root: Optional[Path]) -> Path:
    root = (
        Path(source_root).resolve(strict=True)
        if source_root is not None
        else Path(__file__).resolve(strict=True).parents[2]
    )
    if not root.is_dir() or root.is_symlink():
        raise ValidationError("qualification scope source root is invalid")
    return root


def shared_source_paths() -> Tuple[str, ...]:
    """Return the explicit shared transport/controller/authority source list."""

    return _SHARED_SOURCE_PATHS


def target_source_paths(target: str, transport: Optional[str] = None) -> Tuple[str, ...]:
    """Return the selected-target harness source list."""

    if target not in _TARGETS:
        raise ValidationError("unsupported qualification scope target")
    paths = set(_TARGET_SOURCE_PATHS[target])
    if transport is not None:
        if transport not in _TRANSPORT_SOURCE_PATHS:
            raise ValidationError("unsupported qualification scope transport")
        all_transport_paths = {
            path for values in _TRANSPORT_SOURCE_PATHS.values() for path in values
        }
        paths.difference_update(all_transport_paths)
        paths.update(_TRANSPORT_SOURCE_PATHS[transport])
    return tuple(sorted(paths))


def scope_source_paths(target: str, transport: Optional[str] = None) -> Tuple[str, ...]:
    """Return the explicit shared plus selected-target source ownership list."""

    return tuple(sorted(set(shared_source_paths()) | set(target_source_paths(target, transport))))


def _source_fingerprint(relative_paths: Tuple[str, ...], source_root: Path) -> str:
    rows = []
    for relative in relative_paths:
        path = source_root / relative
        if path.is_symlink() or not path.is_file():
            raise ValidationError("qualification scope source is unavailable")
        rows.append({"path": relative, "sha256": sha256_file(path)})
    return sha256_bytes(canonical_json_bytes(rows))


def _bounded_optional_text(
    value: Any, *, label: str, maximum: int, allow_leading_dash: bool = True
) -> Optional[str]:
    if value is None:
        return None
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > maximum
        or (not allow_leading_dash and value.startswith("-"))
        or any(char in value for char in "\x00\n\r")
    ):
        raise ValidationError("%s is invalid" % label)
    return value.strip()


def _model_effort(
    mapping: Mapping[str, Any],
    requested_model: Optional[str],
    requested_effort: Optional[str],
) -> Dict[str, Optional[str]]:
    requested_model = _bounded_optional_text(
        requested_model,
        label="requested model",
        maximum=200,
        allow_leading_dash=False,
    )
    requested_effort = _bounded_optional_text(
        requested_effort,
        label="requested effort",
        maximum=80,
        allow_leading_dash=False,
    )
    model_flag = mapping.get("model_flag")
    effort_flag = mapping.get("effort_flag")
    if model_flag is not None and not isinstance(model_flag, str):
        raise ValidationError("model selector flag is invalid")
    if effort_flag is not None and not isinstance(effort_flag, str):
        raise ValidationError("effort selector flag is invalid")
    if requested_model is not None and model_flag is None:
        raise UnsupportedError("requested model selection is not proved by the manifest")
    if requested_effort is not None and effort_flag is None:
        raise UnsupportedError("requested effort selection is not proved by the manifest")
    # Observed model/effort stay unavailable: a requested selector is not
    # harness-originated proof of the executed model.
    return {
        "requested_model": requested_model,
        "requested_effort": requested_effort,
        "model_flag": model_flag,
        "effort_flag": effort_flag,
        "observed_model": None,
        "observed_effort": None,
    }


def _identity(manifest: Mapping[str, Any]) -> Dict[str, str]:
    try:
        executable = manifest["executable"]
        execution = manifest["execution"]
        platform = manifest["platform"]
        identity = {
            "executable_fingerprint": executable["sha256"],
            "execution_fingerprint": execution["execution_fingerprint"],
            "version_fingerprint": executable["version_sha256"],
            "platform_fingerprint": sha256_bytes(canonical_json_bytes(platform)),
            "protocol_fingerprint": manifest["protocol_fingerprint"],
        }
    except (KeyError, TypeError) as exc:
        raise ValidationError("qualification scope manifest identity is incomplete") from exc
    for name, value in identity.items():
        validate_sha256(value, name.replace("_", " "))
    return identity


def _fingerprint_body(scope: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "schema": scope["schema"],
        "target": scope["target"],
        "transport": scope["transport"],
        "harness_scope": scope["harness_scope"],
        "transport_authority_scope": scope["transport_authority_scope"],
        "instruction_policy_fingerprint": scope["instruction_policy_fingerprint"],
    }


def _task_fingerprint_body(scope: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "schema": scope["schema"],
        "controller": scope["controller"],
        "campaign_id": scope["campaign_id"],
        "goal_fingerprint": scope["goal_fingerprint"],
    }


def _validate_model_effort(value: Any) -> Dict[str, Optional[str]]:
    if not isinstance(value, dict) or set(value) != _MODEL_EFFORT_FIELDS:
        raise ValidationError("qualification scope model/effort identity is invalid")
    for name, maximum in (("requested_model", 200), ("requested_effort", 80)):
        _bounded_optional_text(
            value[name],
            label="qualification scope %s" % name,
            maximum=maximum,
            allow_leading_dash=False,
        )
    for name in ("model_flag", "effort_flag"):
        field_value = value[name]
        if field_value is not None and (
            not isinstance(field_value, str)
            or not field_value
            or len(field_value) > 80
            or not field_value.startswith("-")
            or any(char in field_value for char in "\x00\n\r")
        ):
            raise ValidationError("qualification scope %s is invalid" % name)
    for name in ("observed_model", "observed_effort"):
        if value.get(name) is not None:
            raise ValidationError(
                "qualification scope cannot claim observed %s from a requested selector"
                % name.replace("observed_", "")
            )
    return dict(value)


def validate_compatibility_scope(value: Any) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise ValidationError("qualification scope fields do not match schema")
    if value.get("schema") != QUALIFICATION_SCOPE_SCHEMA:
        raise UnsupportedError("legacy or unsupported qualification scope")
    if set(value) != _SCOPE_FIELDS:
        raise ValidationError("qualification scope fields do not match schema")
    target = value.get("target")
    if target not in _TARGETS:
        raise ValidationError("qualification scope target is invalid")
    transport_id = value.get("transport")
    if transport_id not in _TRANSPORT_SOURCE_PATHS:
        raise ValidationError("qualification scope transport is invalid")
    validate_sha256(
        value.get("instruction_policy_fingerprint"),
        "qualification scope instruction policy",
    )
    harness = value.get("harness_scope")
    if not isinstance(harness, dict) or set(harness) != _HARNESS_SCOPE_FIELDS:
        raise ValidationError("qualification harness scope is invalid")
    validate_sha256(
        harness.get("target_source_fingerprint"),
        "qualification harness source",
    )
    identity = harness.get("identity")
    if not isinstance(identity, dict) or set(identity) != _IDENTITY_FIELDS:
        raise ValidationError("qualification scope runtime identity is invalid")
    for name, item in identity.items():
        validate_sha256(item, "qualification scope %s" % name.replace("_", " "))
    _validate_model_effort(harness.get("model_effort"))
    transport_authority = value.get("transport_authority_scope")
    if (
        not isinstance(transport_authority, dict)
        or set(transport_authority) != _TRANSPORT_AUTHORITY_FIELDS
    ):
        raise ValidationError("qualification transport/authority scope is invalid")
    validate_sha256(
        transport_authority.get("shared_source_fingerprint"),
        "qualification transport/authority source",
    )
    expected = sha256_bytes(canonical_json_bytes(_fingerprint_body(value)))
    if value.get("fingerprint") != expected:
        raise ValidationError("qualification scope fingerprint changed")
    return {
        "schema": value["schema"],
        "target": target,
        "transport": transport_id,
        "harness_scope": {
            "target_source_fingerprint": harness["target_source_fingerprint"],
            "identity": dict(identity),
            "model_effort": dict(harness["model_effort"]),
        },
        "transport_authority_scope": {
            "shared_source_fingerprint": transport_authority["shared_source_fingerprint"],
        },
        "instruction_policy_fingerprint": value["instruction_policy_fingerprint"],
        "fingerprint": value["fingerprint"],
    }


def build_compatibility_scope(
    manifest: Mapping[str, Any],
    *,
    requested_model: Optional[str],
    requested_effort: Optional[str],
    instruction_policy_fingerprint: str,
    transport: Optional[str] = None,
    source_root: Optional[Path] = None,
    existing_scope: Optional[Mapping[str, Any]] = None,
    legacy: bool = False,
) -> Dict[str, Any]:
    """Build or verify reusable selected-target compatibility evidence."""

    if legacy:
        raise UnsupportedError("legacy qualification evidence cannot be promoted")
    target = manifest.get("target")
    if target not in _TARGETS:
        raise ValidationError("unsupported qualification scope target")
    if transport is None:
        transport = manifest.get("transport") or "tmux"
    if transport not in _TRANSPORT_SOURCE_PATHS:
        raise ValidationError("unsupported qualification scope transport")
    validate_sha256(
        instruction_policy_fingerprint, "qualification scope instruction policy"
    )
    mapping = manifest.get("yolo_mapping")
    if not isinstance(mapping, Mapping):
        raise ValidationError("qualification scope launch mapping is unavailable")
    root = _skill_root(source_root)
    scope: Dict[str, Any] = {
        "schema": QUALIFICATION_SCOPE_SCHEMA,
        "target": target,
        "transport": transport,
        "harness_scope": {
            "target_source_fingerprint": _source_fingerprint(
                target_source_paths(target, transport), root
            ),
            "identity": _identity(manifest),
            "model_effort": _model_effort(mapping, requested_model, requested_effort),
        },
        "transport_authority_scope": {
            "shared_source_fingerprint": _source_fingerprint(
                shared_source_paths(), root
            ),
        },
        "instruction_policy_fingerprint": instruction_policy_fingerprint,
    }
    scope["fingerprint"] = sha256_bytes(canonical_json_bytes(_fingerprint_body(scope)))
    if existing_scope is not None:
        existing = validate_compatibility_scope(dict(existing_scope))
        if existing != scope:
            raise ValidationError("qualification scope fingerprint or identity changed")
    return scope


def build_task_scope(
    *,
    controller: str,
    campaign_id: str,
    goal_fingerprint: str,
) -> Dict[str, Any]:
    """Build the non-reusable task authorization identity."""

    validate_identifier(controller, "task controller")
    validate_identifier(campaign_id, "task campaign")
    validate_sha256(goal_fingerprint, "task goal fingerprint")
    scope: Dict[str, Any] = {
        "schema": TASK_SCOPE_SCHEMA,
        "controller": controller,
        "campaign_id": campaign_id,
        "goal_fingerprint": goal_fingerprint,
    }
    scope["fingerprint"] = sha256_bytes(canonical_json_bytes(_task_fingerprint_body(scope)))
    return scope


def validate_task_scope(value: Any) -> Dict[str, Any]:
    if not isinstance(value, dict) or set(value) != _TASK_SCOPE_FIELDS:
        raise ValidationError("task authorization scope fields do not match schema")
    if value.get("schema") != TASK_SCOPE_SCHEMA:
        raise UnsupportedError("legacy or unsupported task authorization scope")
    validate_identifier(value.get("controller"), "task controller")
    validate_identifier(value.get("campaign_id"), "task campaign")
    validate_sha256(value.get("goal_fingerprint"), "task goal fingerprint")
    expected = sha256_bytes(canonical_json_bytes(_task_fingerprint_body(value)))
    if value.get("fingerprint") != expected:
        raise ValidationError("task authorization scope fingerprint changed")
    return dict(value)


def compatibility_invalidations(
    stored: Optional[Mapping[str, Any]],
    observed: Mapping[str, Any],
) -> List[Dict[str, str]]:
    """Return body-safe reasons the stored compatibility evidence is not current."""

    if stored is None:
        return [
            {
                "reason": "legacy_or_unscoped_qualification",
                "detail": "stored qualification has no versioned compatibility scope",
            }
        ]
    invalidations: List[Dict[str, str]] = []
    if stored.get("target") != observed.get("target"):
        invalidations.append({"reason": "target_changed"})
    stored_harness = stored.get("harness_scope") if isinstance(stored, Mapping) else None
    observed_harness = observed.get("harness_scope") if isinstance(observed, Mapping) else None
    stored_harness = stored_harness if isinstance(stored_harness, Mapping) else {}
    observed_harness = observed_harness if isinstance(observed_harness, Mapping) else {}
    if stored_harness.get("target_source_fingerprint") != observed_harness.get(
        "target_source_fingerprint"
    ):
        invalidations.append({"reason": "selected_target_source_changed"})
    stored_identity = stored_harness.get("identity")
    observed_identity = observed_harness.get("identity")
    stored_identity = stored_identity if isinstance(stored_identity, Mapping) else {}
    observed_identity = observed_identity if isinstance(observed_identity, Mapping) else {}
    for name in (
        "executable_fingerprint",
        "execution_fingerprint",
        "version_fingerprint",
        "platform_fingerprint",
        "protocol_fingerprint",
    ):
        if stored_identity.get(name) != observed_identity.get(name):
            invalidations.append({"reason": "runtime_identity_changed", "field": name})
    if stored_harness.get("model_effort") != observed_harness.get("model_effort"):
        invalidations.append({"reason": "model_or_effort_selection_changed"})
    stored_transport = (
        stored.get("transport_authority_scope") if isinstance(stored, Mapping) else None
    )
    observed_transport = (
        observed.get("transport_authority_scope")
        if isinstance(observed, Mapping)
        else None
    )
    stored_transport = stored_transport if isinstance(stored_transport, Mapping) else {}
    observed_transport = (
        observed_transport if isinstance(observed_transport, Mapping) else {}
    )
    if stored_transport.get("shared_source_fingerprint") != observed_transport.get(
        "shared_source_fingerprint"
    ):
        invalidations.append({"reason": "transport_or_shared_authority_changed"})
    if stored.get("instruction_policy_fingerprint") != observed.get(
        "instruction_policy_fingerprint"
    ):
        invalidations.append({"reason": "instruction_policy_changed"})
    if stored.get("fingerprint") != observed.get("fingerprint"):
        invalidations.append({"reason": "compatibility_scope_fingerprint_changed"})
    return invalidations


def compare_qualification_compatibility(
    *,
    stored_scope: Mapping[str, Any],
    current_manifest: Mapping[str, Any],
    instruction_policy_fingerprint: str,
    source_root: Optional[Path] = None,
    requested_model: Optional[str] = None,
    requested_effort: Optional[str] = None,
    transport: Optional[str] = None,
) -> Dict[str, Any]:
    """Rebuild the current compatibility scope and compare it to stored evidence."""

    stored = validate_compatibility_scope(dict(stored_scope))
    model_effort = stored["harness_scope"]["model_effort"]
    selected_transport = transport if transport is not None else stored["transport"]
    current_scope = build_compatibility_scope(
        current_manifest,
        requested_model=(
            requested_model
            if requested_model is not None
            else model_effort["requested_model"]
        ),
        requested_effort=(
            requested_effort
            if requested_effort is not None
            else model_effort["requested_effort"]
        ),
        instruction_policy_fingerprint=instruction_policy_fingerprint,
        source_root=source_root,
        transport=selected_transport,
    )
    return {
        "current_scope": current_scope,
        "invalidations": compatibility_invalidations(stored, current_scope),
    }


def evaluate_qualification_reuse(
    *,
    stored_compatibility: Mapping[str, Any],
    stored_task: Mapping[str, Any],
    current_compatibility: Mapping[str, Any],
    new_task: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Decide whether compatibility may be reused without transferring task authority."""

    stored = validate_compatibility_scope(dict(stored_compatibility))
    try:
        current = validate_compatibility_scope(dict(current_compatibility))
    except (UnsupportedError, ValidationError):
        current = dict(current_compatibility)
    invalidations = compatibility_invalidations(stored, current)
    if not invalidations and current != stored:
        invalidations = [{"reason": "compatibility_scope_fingerprint_changed"}]
    stored_task_scope = validate_task_scope(dict(stored_task))
    model_effort = stored["harness_scope"]["model_effort"]
    observed_model_claimed = (
        model_effort.get("observed_model") is not None
        or model_effort.get("observed_effort") is not None
    )
    result = {
        "compatibility_reusable": not invalidations,
        "task_authority_reusable": False,
        "observed_model_claimed": observed_model_claimed,
        "task_authority": "not_requested",
        "stored_task_fingerprint": stored_task_scope["fingerprint"],
        "invalidations": invalidations,
    }
    if new_task is None:
        return result
    requested = validate_task_scope(dict(new_task))
    result["requested_task_fingerprint"] = requested["fingerprint"]
    result["task_authority"] = (
        "original_binding" if stored_task_scope == requested else "fresh_required"
    )
    return result


def task_authority_from_receipt(receipt: Mapping[str, Any]) -> Dict[str, Any]:
    return build_task_scope(
        controller=str(receipt.get("controller")),
        campaign_id=str(receipt.get("campaign_id")),
        goal_fingerprint=str(receipt.get("goal_fingerprint")),
    )
