"""Versioned reusable harness-compatibility evidence.

The scope digest is deliberately separate from campaign and goal authority.
It answers whether a selected harness/runtime/policy pair is still compatible;
it never authorizes a task or a live launch.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Tuple

from .errors import UnsupportedError, ValidationError
from .safety import canonical_json_bytes, sha256_bytes, sha256_file, validate_sha256


QUALIFICATION_SCOPE_SCHEMA = "puppet.qualification-scope/v1"
QUALIFICATION_SCOPE_VERSION = 1

_TARGETS = frozenset({"agy", "cursor", "claude", "codex", "grok"})

# These modules own behavior shared by every target. Keep this list explicit:
# adding a shared authority, launch, probe, or instruction dependency here is a
# deliberate invalidation event for every target.
_SHARED_SOURCE_PATHS: Tuple[str, ...] = (
    "scripts/adapter_lab.py",
    "scripts/puppet.py",
    "scripts/puppet_lib/adapter_manifest.py",
    "scripts/puppet_lib/adapters.py",
    "scripts/puppet_lib/authority.py",
    "scripts/puppet_lib/census.py",
    "scripts/puppet_lib/contracts.py",
    "scripts/puppet_lib/errors.py",
    "scripts/puppet_lib/handoffs.py",
    "scripts/puppet_lib/instructions.py",
    "scripts/puppet_lib/launch.py",
    "scripts/puppet_lib/probe.py",
    "scripts/puppet_lib/profiles.py",
    "scripts/puppet_lib/qualification_scope.py",
    "scripts/puppet_lib/safety.py",
    "scripts/puppet_lib/session.py",
    "scripts/puppet_lib/verdicts.py",
    "templates/instructions/catalog.json",
    "templates/instructions/lifecycle/regular.md",
    "templates/instructions/model/default-unresolved.md",
    "templates/instructions/universal.md",
)

_TARGET_SOURCE_PATHS: Dict[str, Tuple[str, ...]] = {
    "agy": (
        "scripts/puppet_lib/agy_launch.py",
        "scripts/puppet_lib/agy_workspace_plane.py",
        "templates/instructions/harness/agy.md",
    ),
    "cursor": (
        "scripts/puppet_lib/cursor_qualification.py",
        "scripts/puppet_lib/cursor_startup_gates.py",
        "scripts/puppet_lib/cursor_workspace_plane.py",
        "templates/instructions/harness/cursor.md",
    ),
    "claude": (
        "scripts/puppet_lib/claude_paired_qualification.py",
        "scripts/puppet_lib/claude_startup_gates.py",
        "templates/instructions/harness/claude.md",
    ),
    "codex": (
        "scripts/puppet_lib/codex_launch.py",
        "scripts/puppet_lib/codex_qualification.py",
        "scripts/puppet_lib/codex_workspace_plane.py",
        "templates/instructions/harness/codex.md",
    ),
    "grok": (
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

_SCOPE_FIELDS = frozenset(
    {
        "schema",
        "target",
        "source_fingerprint",
        "identity",
        "model_effort",
        "instruction_policy_fingerprint",
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


def scope_source_paths(target: str) -> Tuple[str, ...]:
    """Return the explicit shared plus selected-target source ownership list."""

    if target not in _TARGETS:
        raise ValidationError("unsupported qualification scope target")
    return tuple(sorted(set(_SHARED_SOURCE_PATHS) | set(_TARGET_SOURCE_PATHS[target])))


def _source_fingerprint(target: str, source_root: Path) -> str:
    rows = []
    for relative in scope_source_paths(target):
        path = source_root / relative
        if path.is_symlink() or not path.is_file():
            raise ValidationError("qualification scope source is unavailable")
        rows.append({"path": relative, "sha256": sha256_file(path)})
    return sha256_bytes(canonical_json_bytes(rows))


def _model_effort(
    mapping: Mapping[str, Any],
    requested_model: Optional[str],
    requested_effort: Optional[str],
) -> Dict[str, Optional[str]]:
    if requested_model is not None and (
        not isinstance(requested_model, str)
        or not requested_model.strip()
        or len(requested_model) > 200
        or requested_model.startswith("-")
        or any(char in requested_model for char in "\x00\n\r")
    ):
        raise ValidationError("requested model is invalid")
    if requested_effort is not None and (
        not isinstance(requested_effort, str)
        or not requested_effort.strip()
        or len(requested_effort) > 80
        or requested_effort.startswith("-")
        or any(char in requested_effort for char in "\x00\n\r")
    ):
        raise ValidationError("requested effort is invalid")
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
    return {
        "requested_model": requested_model.strip() if requested_model else None,
        "requested_effort": requested_effort.strip() if requested_effort else None,
        "model_flag": model_flag,
        "effort_flag": effort_flag,
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
            "adapter_fingerprint": manifest["adapter_fingerprint"],
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
        "source_fingerprint": scope["source_fingerprint"],
        "identity": scope["identity"],
        "model_effort": scope["model_effort"],
        "instruction_policy_fingerprint": scope["instruction_policy_fingerprint"],
    }


def validate_compatibility_scope(value: Any) -> Dict[str, Any]:
    if not isinstance(value, dict) or set(value) != _SCOPE_FIELDS:
        raise ValidationError("qualification scope fields do not match schema")
    if value.get("schema") != QUALIFICATION_SCOPE_SCHEMA:
        raise UnsupportedError("legacy or unsupported qualification scope")
    target = value.get("target")
    if target not in _TARGETS:
        raise ValidationError("qualification scope target is invalid")
    validate_sha256(value.get("source_fingerprint"), "qualification scope source")
    validate_sha256(
        value.get("instruction_policy_fingerprint"),
        "qualification scope instruction policy",
    )
    identity = value.get("identity")
    if not isinstance(identity, dict) or set(identity) != {
        "executable_fingerprint",
        "execution_fingerprint",
        "version_fingerprint",
        "platform_fingerprint",
        "adapter_fingerprint",
        "protocol_fingerprint",
    }:
        raise ValidationError("qualification scope runtime identity is invalid")
    for name, item in identity.items():
        validate_sha256(item, "qualification scope %s" % name.replace("_", " "))
    model_effort = value.get("model_effort")
    if not isinstance(model_effort, dict) or set(model_effort) != {
        "requested_model",
        "requested_effort",
        "model_flag",
        "effort_flag",
    }:
        raise ValidationError("qualification scope model/effort identity is invalid")
    for name, maximum in (("requested_model", 200), ("requested_effort", 80)):
        field_value = model_effort[name]
        if field_value is not None and (
            not isinstance(field_value, str)
            or not field_value
            or len(field_value) > maximum
            or field_value.startswith("-")
            or any(char in field_value for char in "\x00\n\r")
        ):
            raise ValidationError("qualification scope %s is invalid" % name)
    for name in ("model_flag", "effort_flag"):
        field_value = model_effort[name]
        if field_value is not None and (
            not isinstance(field_value, str)
            or not field_value
            or len(field_value) > 80
            or field_value.startswith("-") is False
            or any(char in field_value for char in "\x00\n\r")
        ):
            raise ValidationError("qualification scope %s is invalid" % name)
    expected = sha256_bytes(canonical_json_bytes(_fingerprint_body(value)))
    if value.get("fingerprint") != expected:
        raise ValidationError("qualification scope fingerprint changed")
    return dict(value)


def build_compatibility_scope(
    manifest: Mapping[str, Any],
    *,
    requested_model: Optional[str],
    requested_effort: Optional[str],
    instruction_policy_fingerprint: str,
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
    validate_sha256(instruction_policy_fingerprint, "qualification scope instruction policy")
    mapping = manifest.get("yolo_mapping")
    if not isinstance(mapping, Mapping):
        raise ValidationError("qualification scope launch mapping is unavailable")
    model_effort = _model_effort(mapping, requested_model, requested_effort)
    scope: Dict[str, Any] = {
        "schema": QUALIFICATION_SCOPE_SCHEMA,
        "target": target,
        "source_fingerprint": _source_fingerprint(target, _skill_root(source_root)),
        "identity": _identity(manifest),
        "model_effort": model_effort,
        "instruction_policy_fingerprint": instruction_policy_fingerprint,
    }
    scope["fingerprint"] = sha256_bytes(canonical_json_bytes(_fingerprint_body(scope)))
    if existing_scope is not None:
        existing = validate_compatibility_scope(dict(existing_scope))
        if existing != scope:
            raise ValidationError("qualification scope fingerprint or identity changed")
    return scope
