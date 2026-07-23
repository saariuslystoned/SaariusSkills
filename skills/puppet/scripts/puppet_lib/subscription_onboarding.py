"""Manifest-bound, body-free first-use subscription onboarding."""

from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Any, Dict, Mapping

from .adapter_manifest import AdapterManifest
from .agy_launch import AGY_REGULAR_AUTHORITY_BLOCKERS
from .census import adapter_implementation_fingerprint
from .errors import ConflictError, IdentityError, PuppetError, ValidationError
from .grok_subscription_adoption import grok_subscription_adoption_plan
from .handoffs import PROTOCOL_FINGERPRINT
from .safety import validate_identifier
from .subscription_profiles import (
    PROFILE_HUMAN_LOGIN_POLICY,
    PROFILE_OPERATOR_GLOBAL_ADOPTION,
    PROFILE_REUSE_SCOPE,
    PROFILE_STATUS_POLICY,
    initialize_subscription_profile,
    subscription_profile_status,
)


ONBOARDING_SCHEMA = "puppet.subscription-onboarding/v1"
ONBOARDING_TARGETS = ("agy", "claude", "codex", "cursor", "grok")
PUBLIC_PROFILE_TARGETS = frozenset({"claude", "codex", "grok"})
UNSUPPORTED_PROFILE_REASONS = {
    "cursor": "cursor_private_subscription_profile_unqualified",
}
UNSUPPORTED_PROFILE_ACTIONS = {
    "cursor": {
        "human_action_required": True,
        "next_action": "human_approve_cursor_auth_isolation_probe",
    },
}

AGY_NATIVE_REUSE_RESULT = {
    "supported": False,
    "state": "native_reuse_candidate",
    "reason": "agy_native_keyring_reuse_discovered_runtime_isolation_unqualified",
    "authentication_mechanism": "operating_system_native_keyring",
    "subscription_reuse": "silent_when_valid_native_profile_exists",
    "current_operator_auth_state": "unobserved",
    "first_use_fallback": "vendor_interactive_browser_auth",
    "repeat_human_auth_policy": "provider_invalidated_revoked_or_logged_out_only",
    "runtime_blockers": AGY_REGULAR_AUTHORITY_BLOCKERS,
    "human_action_required": False,
    "next_action": "qualify_agy_runtime_isolation_without_credential_copy",
    "profile_material_copied": False,
    "login_performed": False,
    "account_change_performed": False,
    "model_launched": False,
    "raw_output_retained": False,
}


def _private_shelf(path: Path | str) -> Path:
    shelf = Path(path)
    if not shelf.is_absolute():
        raise ValidationError("subscription profile shelf must be absolute")
    try:
        lexical = os.lstat(shelf)
        resolved = shelf.resolve(strict=True)
        details = resolved.stat()
    except OSError as exc:
        raise ValidationError("subscription profile shelf is unavailable") from exc
    if (
        stat.S_ISLNK(lexical.st_mode)
        or not stat.S_ISDIR(lexical.st_mode)
        or resolved != shelf
        or not stat.S_ISDIR(details.st_mode)
        or details.st_uid != os.getuid()
        or stat.S_IMODE(details.st_mode) != 0o700
    ):
        raise IdentityError(
            "subscription profile shelf must be a real current-UID mode-0700 directory"
        )
    return resolved


def _current_manifest(
    target: str,
    path: Path | str,
    *,
    expected_adapter_fingerprint: str,
) -> AdapterManifest:
    target = validate_identifier(target, "onboarding target")
    if target not in ONBOARDING_TARGETS:
        raise ValidationError("onboarding target is unsupported")
    manifest = AdapterManifest.from_path(Path(path))
    if manifest.target != target:
        raise IdentityError("onboarding manifest target changed")
    manifest.verify_execution_files()
    if manifest.raw["adapter_fingerprint"] != expected_adapter_fingerprint:
        raise IdentityError("onboarding manifest source fingerprint is stale")
    if manifest.raw["protocol_fingerprint"] != PROTOCOL_FINGERPRINT:
        raise IdentityError("onboarding manifest protocol fingerprint is stale")
    return manifest


def _safe_status(status: Mapping[str, Any]) -> Dict[str, Any]:
    allowed = (
        "login_state",
        "method",
        "provider",
        "default_model",
        "status_exit",
        "raw_output_retained",
    )
    return {name: status[name] for name in allowed if name in status}


def _supported_result(
    *,
    target: str,
    shelf: Path,
    manifest: AdapterManifest,
) -> Dict[str, Any]:
    profile_root = shelf / target
    initialized = initialize_subscription_profile(
        target=target,
        profile_root=profile_root,
        executable_path=Path(manifest.raw["executable"]["resolved_path"]),
    )
    base = {
        "supported": True,
        "profile_root": str(profile_root),
        "profile_manifest_sha256": initialized["manifest_sha256"],
        "adapter_manifest_fingerprint": manifest.fingerprint,
        "reuse_scope": PROFILE_REUSE_SCOPE,
        "status_policy": PROFILE_STATUS_POLICY,
        "human_login_policy": PROFILE_HUMAN_LOGIN_POLICY,
        "operator_global_adoption": PROFILE_OPERATOR_GLOBAL_ADOPTION,
        "login_performed": False,
        "account_change_performed": False,
        "model_launched": False,
        "raw_output_retained": False,
    }
    if target == "grok":
        base["operator_subscription_adoption"] = (
            grok_subscription_adoption_plan()
        )
    try:
        status = subscription_profile_status(profile_root=profile_root)
    except PuppetError as exc:
        return {
            **base,
            "state": "status_unavailable",
            "human_action_required": False,
            "next_action": "investigate_native_status",
            "status_error": exc.category,
        }
    safe_status = _safe_status(status)
    if status["login_state"] == "logged_in":
        return {
            **base,
            "state": "ready",
            "human_action_required": False,
            "next_action": "reuse_authenticated_profile",
            "status": safe_status,
        }
    if status["login_state"] == "logged_out":
        return {
            **base,
            "state": "enrollment_required",
            "human_action_required": True,
            "next_action": "human_run_one_time_login_handoff",
            "login_command": initialized["login_command"],
            "status": safe_status,
        }
    return {
        **base,
        "state": "status_unknown",
        "human_action_required": False,
        "next_action": "investigate_native_status",
        "status": safe_status,
    }


def run_subscription_onboarding(
    *,
    profile_shelf: Path | str,
    manifest_paths: Mapping[str, Path | str],
) -> Dict[str, Any]:
    """Prepare selected profiles and return only bounded readiness/actions."""

    shelf = _private_shelf(profile_shelf)
    if (
        not isinstance(manifest_paths, Mapping)
        or not manifest_paths
        or len(manifest_paths) > len(ONBOARDING_TARGETS)
    ):
        raise ValidationError("onboarding requires selected target manifests")

    manifest_items = list(manifest_paths.items())
    for target, _path in manifest_items:
        if not isinstance(target, str):
            raise ValidationError("onboarding target must be a string")
    implementation_fingerprint = adapter_implementation_fingerprint()
    manifests: Dict[str, AdapterManifest] = {}
    for target, path in sorted(manifest_items):
        if target in manifests:
            raise ConflictError("duplicate onboarding target")
        manifests[target] = _current_manifest(
            target,
            path,
            expected_adapter_fingerprint=implementation_fingerprint,
        )
    if adapter_implementation_fingerprint() != implementation_fingerprint:
        raise IdentityError("onboarding controller source changed during preflight")

    results: Dict[str, Dict[str, Any]] = {}
    for target, manifest in sorted(manifests.items()):
        if target == "agy":
            results[target] = dict(AGY_NATIVE_REUSE_RESULT)
            continue
        if target not in PUBLIC_PROFILE_TARGETS:
            action = UNSUPPORTED_PROFILE_ACTIONS[target]
            results[target] = {
                "supported": False,
                "state": "unsupported",
                "reason": UNSUPPORTED_PROFILE_REASONS[target],
                **action,
                "login_performed": False,
                "account_change_performed": False,
                "model_launched": False,
                "raw_output_retained": False,
            }
            continue
        results[target] = _supported_result(
            target=target,
            shelf=shelf,
            manifest=manifest,
        )

    states = {
        state: [
            target
            for target, result in results.items()
            if result["state"] == state
        ]
        for state in (
            "ready",
            "enrollment_required",
            "status_unknown",
            "status_unavailable",
            "native_reuse_candidate",
            "unsupported",
        )
    }
    human_action_targets = [
        target
        for target, result in results.items()
        if result["human_action_required"]
    ]
    return {
        "schema": ONBOARDING_SCHEMA,
        "adapter_fingerprint": implementation_fingerprint,
        "protocol_fingerprint": PROTOCOL_FINGERPRINT,
        "profile_shelf": str(shelf),
        "selected_targets": sorted(results),
        "ready_targets": states["ready"],
        "enrollment_targets": states["enrollment_required"],
        "unknown_targets": [
            *states["status_unknown"],
            *states["status_unavailable"],
        ],
        "native_reuse_candidate_targets": states["native_reuse_candidate"],
        "unsupported_targets": states["unsupported"],
        "human_action_targets": human_action_targets,
        "human_action_required": bool(human_action_targets),
        "login_performed": False,
        "account_change_performed": False,
        "model_launched": False,
        "raw_output_retained": False,
        "results": results,
    }


__all__ = [
    "ONBOARDING_SCHEMA",
    "ONBOARDING_TARGETS",
    "AGY_NATIVE_REUSE_RESULT",
    "PUBLIC_PROFILE_TARGETS",
    "UNSUPPORTED_PROFILE_ACTIONS",
    "UNSUPPORTED_PROFILE_REASONS",
    "run_subscription_onboarding",
]
