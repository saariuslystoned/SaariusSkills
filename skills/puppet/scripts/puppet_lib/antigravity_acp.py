"""Named antigravity-acp candidate transport with existing candidate contracts.

Pins the official Antigravity runtime shape and consumes the pinned public
acpx runtime through the existing controller/caller path. Ordinary
availability stays false. Host conversation_id stays separate from
runtimeSessionName/backendSessionId/acpxRecordId.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence

from .caller import caller_projection, make_blocker
from .cursor_acp import (
    CANDIDATE_RUNTIME_KIND,
    FINISH_POLICY_DISCARD,
    FINISH_POLICY_LOCAL_RELEASE,
    FINISH_POLICY_RETAIN,
    SESSION_MODE_ONESHOT,
    SESSION_MODE_PERSISTENT,
    SYNTHETIC_PEER_KIND,
    drain_runtime_turn_events,
    project_runtime_handle,
    reject_runtime_conversation_params,
    require_runtime_task_text,
    require_unsupported_permission_outcome,
    require_unsupported_question_outcome,
)
from .errors import IdentityError, UnsupportedError, ValidationError
from .safety import validate_identifier


TRANSPORT_ID = "antigravity-acp"
GENERIC_ACP_ID = "acp"
TARGET = "agy"
DEFAULT_ROUTE = "agy-print"
CANDIDATE_SCHEMA = "puppet.antigravity-acp-candidate/v1"
OBSERVATION_SCHEMA = "puppet.antigravity-acp-observation/v1"
MODEL_CATALOG_SCHEMA = "puppet.antigravity-acp-model-catalog/v1"
ADAPTER_ID = "antigravity-acpx"
OWNERSHIP_SCHEMA = "puppet.antigravity-acpx-ownership/v1"

REGISTRY_REVISION = "81bf71b55e15f630c4fb8a86d20d3088071d2071"
RUNTIME_ID = "antigravity-acp"
RUNTIME_VERSION = "1.1.1"
ACPX_SOURCE_COMMIT = "50a47ad10a75431cbc276ec9b555d11fe1f69c84"
ACPX_RELEASE = "0.17.1"

DEFAULT_ANTIGRAVITY_MODEL = "gemini-3.8-flash-high"
ADVERTISED_ANTIGRAVITY_MODELS = (
    "gemini-3.8-flash-high",
    "gemini-3.1-pro",
    "gemini-3-flash",
)
FALLBACK_OR_DEFAULT_MODEL_IDS = frozenset(
    {"default", "fallback", "auto", "unavailable", "current_default"}
)
CONTROLLER_RUNTIME_DRIVER = (
    "bridge/antigravity-acp/test/controller-runtime-driver.mjs"
)

_PLATFORM_COMMANDS = {
    "darwin-aarch64": {
        "runtime_command": "./agy_acp_server.par",
        "runtime_args": [],
        "helper": "localharness_external",
    },
    "linux-aarch64": {
        "runtime_command": "./agy_acp_server.par",
        "runtime_args": ["--uid="],
        "helper": "localharness_external",
    },
    "linux-x86_64": {
        "runtime_command": "./agy_acp_server.par",
        "runtime_args": ["--uid="],
        "helper": "localharness_external",
    },
    "windows-aarch64": {
        "runtime_command": "./agy_acp_server.exe",
        "runtime_args": [],
        "helper": "localharness_external.exe",
    },
    "windows-x86_64": {
        "runtime_command": "./agy_acp_server.exe",
        "runtime_args": [],
        "helper": "localharness_external.exe",
    },
}

_CONTRACT_KEYS = frozenset(
    {
        "schema",
        "transport",
        "target",
        "default_route",
        "available",
        "qualification",
        "explicit_activation_required",
        "runtime",
        "auth_policy",
        "model_policy",
        "question_policy",
        "platform_commands",
    }
)
_RUNTIME_KEYS = frozenset(
    {"id", "version", "registry_revision", "acpx_source_commit", "acpx_release"}
)
_AUTH_POLICY_KEYS = frozenset(
    {
        "mode",
        "profile_env",
        "credential_source",
        "api_key_fallback",
        "cloud_fallback",
        "alternate_account_fallback",
        "interactive_login",
        "overage_policy",
    }
)
_MODEL_POLICY_KEYS = frozenset(
    {"selection", "observed_required", "unknown_model", "effort_policy"}
)
_QUESTION_POLICY_KEYS = frozenset(
    {"interaction_requests", "answer_selection", "human_required_outcome"}
)
_OBSERVATION_KEYS = frozenset(
    {
        "schema",
        "transport",
        "target",
        "qualification",
        "runtime",
        "auth",
        "model",
        "session",
        "terminal",
        "question",
        "record_state",
    }
)
_OBS_RUNTIME_KEYS = frozenset({"id", "version", "registry_revision"})
_OBS_AUTH_KEYS = frozenset(
    {
        "mode",
        "profile_env",
        "credential_source",
        "account_state",
        "api_key_present",
        "cloud_credentials_present",
        "alternate_account",
        "interactive_login",
        "overage_state",
    }
)
_OBS_MODEL_KEYS = frozenset(
    {"requested_id", "advertised_ids", "observed_id", "selection_state", "effort"}
)
_OBS_SESSION_KEYS = frozenset({"session_id", "conversation_id"})
_OBS_TERMINAL_KEYS = frozenset({"state", "exit_code", "result_id"})
_OBS_QUESTION_KEYS = frozenset(
    {"state", "interaction_id", "human_required", "outcome"}
)
_BODY_KEYS = frozenset(
    {"prompt", "output", "content", "text", "transcript", "title", "options"}
)


def _blocker(code: str, detail: str, **identity: Any) -> Dict[str, Any]:
    return make_blocker(code=code, detail=detail, **identity)


def _raise_identity(code: str, detail: str, **identity: Any) -> None:
    raise IdentityError(detail, blocker=_blocker(code, detail, **identity))


def _raise_unsupported(code: str, detail: str) -> None:
    raise UnsupportedError(detail, blocker=_blocker(code, detail))


def _raise_unavailable(detail: str) -> None:
    raise UnsupportedError(detail, blocker=_blocker("transport_unavailable", detail))


def _backend_unsupported_close(detail: str) -> UnsupportedError:
    error = UnsupportedError(
        detail,
        blocker=_blocker("acp_backend_unsupported_control", detail),
    )
    error.code = "ACP_BACKEND_UNSUPPORTED_CONTROL"
    return error


def require_antigravity_acp_target(target: Any) -> str:
    if target != TARGET:
        raise ValidationError("antigravity-acp transport requires target agy")
    return TARGET


def _exact_mapping(value: Any, keys: frozenset[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != keys:
        raise ValidationError("%s fields do not match schema" % label)
    return value


def _reject_body_keys(value: Any, label: str = "metadata") -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if key in _BODY_KEYS:
                raise ValidationError("%s contains body-bearing field %s" % (label, key))
            _reject_body_keys(nested, label)
    elif isinstance(value, list):
        for nested in value:
            _reject_body_keys(nested, label)


def _bool(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValidationError("%s must be boolean" % label)
    return value


def _bounded_string(value: Any, label: str, maximum: int = 200) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise ValidationError("%s is invalid" % label)
    if any(character in value for character in "\x00\n\r"):
        raise ValidationError("%s contains control characters" % label)
    return value


def candidate_contract() -> Dict[str, Any]:
    """Return the pinned, explicitly non-qualifying candidate contract."""

    return {
        "schema": CANDIDATE_SCHEMA,
        "transport": TRANSPORT_ID,
        "target": TARGET,
        "default_route": DEFAULT_ROUTE,
        "available": False,
        "qualification": "non_qualifying",
        "explicit_activation_required": True,
        "runtime": {
            "id": RUNTIME_ID,
            "version": RUNTIME_VERSION,
            "registry_revision": REGISTRY_REVISION,
            "acpx_source_commit": ACPX_SOURCE_COMMIT,
            "acpx_release": ACPX_RELEASE,
        },
        "auth_policy": {
            "mode": "oauth-personal",
            "profile_env": "GEMINI_HOME",
            "credential_source": "runtime_owned",
            "api_key_fallback": False,
            "cloud_fallback": False,
            "alternate_account_fallback": False,
            "interactive_login": "fail_closed",
            "overage_policy": "must_observe_disabled_or_never",
        },
        "model_policy": {
            "selection": "exact_advertised_id_only",
            "observed_required": True,
            "unknown_model": "fail_closed",
            "effort_policy": "unsupported_until_acp_proof",
        },
        "question_policy": {
            "interaction_requests": "cancel_and_report",
            "answer_selection": "never_auto_select",
            "human_required_outcome": "cancelled",
        },
        "platform_commands": deepcopy(_PLATFORM_COMMANDS),
    }


def validate_candidate_contract(value: Any) -> Dict[str, Any]:
    """Validate exact pinning and safety policy for the candidate contract."""

    contract = _exact_mapping(value, _CONTRACT_KEYS, "candidate contract")
    if contract.get("schema") != CANDIDATE_SCHEMA:
        raise ValidationError("candidate contract schema is invalid")
    if contract.get("transport") != TRANSPORT_ID:
        raise ValidationError("candidate contract transport is invalid")
    if contract.get("transport") == GENERIC_ACP_ID:
        raise ValidationError("generic acp is not Antigravity ACP")
    if contract.get("target") != TARGET:
        raise ValidationError("candidate contract target is invalid")
    if contract.get("default_route") != DEFAULT_ROUTE:
        raise ValidationError("native default route changed")
    if contract.get("available") is not False:
        raise ValidationError("candidate contract must remain unavailable")
    if contract.get("qualification") != "non_qualifying":
        raise ValidationError("candidate contract cannot claim qualification")
    if contract.get("explicit_activation_required") is not True:
        raise ValidationError("candidate contract requires explicit activation")

    runtime = _exact_mapping(contract.get("runtime"), _RUNTIME_KEYS, "runtime pin")
    expected_runtime = candidate_contract()["runtime"]
    if dict(runtime) != expected_runtime:
        raise ValidationError("Antigravity ACP runtime pin drifted")

    auth = _exact_mapping(contract.get("auth_policy"), _AUTH_POLICY_KEYS, "auth policy")
    expected_auth = candidate_contract()["auth_policy"]
    if dict(auth) != expected_auth:
        raise ValidationError("Antigravity ACP auth policy drifted")

    model = _exact_mapping(contract.get("model_policy"), _MODEL_POLICY_KEYS, "model policy")
    if dict(model) != candidate_contract()["model_policy"]:
        raise ValidationError("Antigravity ACP model policy drifted")

    question = _exact_mapping(
        contract.get("question_policy"), _QUESTION_POLICY_KEYS, "question policy"
    )
    if dict(question) != candidate_contract()["question_policy"]:
        raise ValidationError("Antigravity ACP question policy drifted")

    platforms = contract.get("platform_commands")
    if not isinstance(platforms, Mapping) or set(platforms) != set(_PLATFORM_COMMANDS):
        raise ValidationError("platform command pin is incomplete")
    for platform, expected in _PLATFORM_COMMANDS.items():
        actual = _exact_mapping(platforms[platform], frozenset(expected), platform)
        if dict(actual) != expected:
            raise ValidationError("platform command pin drifted for %s" % platform)
        if not isinstance(actual["runtime_args"], list) or not all(
            isinstance(argument, str) and argument for argument in actual["runtime_args"]
        ):
            raise ValidationError("platform runtime arguments are invalid")
    return deepcopy(dict(contract))


def validate_auth_observation(value: Any) -> Dict[str, Any]:
    """Require personal OAuth and reject every unproven credential fallback."""

    auth = _exact_mapping(value, _OBS_AUTH_KEYS, "auth observation")
    if auth.get("mode") != "oauth-personal":
        raise ValidationError("Antigravity ACP requires personal OAuth")
    if auth.get("profile_env") != "GEMINI_HOME":
        raise ValidationError("Antigravity ACP profile must use GEMINI_HOME")
    if auth.get("credential_source") != "runtime_owned":
        raise ValidationError("Antigravity ACP credential source is not runtime-owned")
    if auth.get("account_state") != "authenticated":
        raise ValidationError("Antigravity ACP account authentication is unproven")
    if _bool(auth.get("api_key_present"), "API-key presence"):
        raise ValidationError("API-key fallback is forbidden")
    if _bool(auth.get("cloud_credentials_present"), "Cloud credential presence"):
        raise ValidationError("Cloud credential fallback is forbidden")
    if _bool(auth.get("alternate_account"), "alternate account"):
        raise ValidationError("alternate-account fallback is forbidden")
    if auth.get("interactive_login") is not False:
        raise ValidationError("interactive login must fail closed")
    if auth.get("overage_state") not in {"disabled", "never"}:
        raise ValidationError("AI-credit overage state is unproven")
    return dict(auth)


def validate_model_observation(value: Any) -> Dict[str, Any]:
    """Require exact advertised/observed identity; effort is not inferred."""

    model = _exact_mapping(value, _OBS_MODEL_KEYS, "model observation")
    requested = _bounded_string(model.get("requested_id"), "requested model")
    advertised = model.get("advertised_ids")
    if not isinstance(advertised, list) or not advertised:
        raise ValidationError("advertised model catalog is unproven")
    if any(not isinstance(item, str) or not item for item in advertised):
        raise ValidationError("advertised model catalog is invalid")
    advertised = [_bounded_string(item, "advertised model") for item in advertised]
    if len(set(advertised)) != len(advertised) or requested not in advertised:
        raise ValidationError("requested model is not an exact advertised id")
    observed = _bounded_string(model.get("observed_id"), "observed model")
    if observed != requested:
        raise ValidationError("observed model does not match requested model")
    if model.get("selection_state") != "exact":
        raise ValidationError("model selection was not exact")
    if model.get("effort") is not None:
        raise ValidationError("ACP effort selection is unsupported until proved")
    return {
        "requested_id": requested,
        "advertised_ids": list(advertised),
        "observed_id": observed,
        "selection_state": "exact",
        "effort": None,
    }


def validate_question_observation(value: Any) -> Dict[str, Any]:
    """Represent fixed-choice questions only as fail-closed control metadata."""

    question = _exact_mapping(value, _OBS_QUESTION_KEYS, "question observation")
    state = question.get("state")
    if state not in {"none", "interaction_required", "cancelled"}:
        raise ValidationError("question state is invalid")
    interaction_id = question.get("interaction_id")
    if state == "none":
        if interaction_id is not None:
            raise ValidationError("question id is invalid for no question")
        if question.get("human_required") is not False or question.get("outcome") is not None:
            raise ValidationError("no-question state is invalid")
    else:
        if interaction_id is None:
            raise ValidationError("interaction question id is missing")
        validate_identifier(interaction_id, "interaction question")
        if question.get("human_required") is not True:
            raise ValidationError("interaction question requires a human")
        if question.get("outcome") != "cancelled":
            raise ValidationError("interaction question must fail closed")
    return {
        "state": state,
        "interaction_id": interaction_id,
        "human_required": question.get("human_required"),
        "outcome": question.get("outcome"),
    }


def validate_candidate_observation(value: Any) -> Dict[str, Any]:
    """Validate one bounded observation without retaining prompt/output bodies."""

    _reject_body_keys(value)
    observation = _exact_mapping(value, _OBSERVATION_KEYS, "candidate observation")
    if observation.get("schema") != OBSERVATION_SCHEMA:
        raise ValidationError("candidate observation schema is invalid")
    if observation.get("transport") != TRANSPORT_ID:
        raise ValidationError("candidate observation transport is invalid")
    if observation.get("target") != TARGET:
        raise ValidationError("candidate observation target is invalid")
    if observation.get("qualification") != "non_qualifying":
        raise ValidationError("candidate observation cannot claim qualification")

    runtime = _exact_mapping(observation.get("runtime"), _OBS_RUNTIME_KEYS, "runtime observation")
    if dict(runtime) != {
        "id": RUNTIME_ID,
        "version": RUNTIME_VERSION,
        "registry_revision": REGISTRY_REVISION,
    }:
        raise ValidationError("runtime observation does not match the pinned candidate")
    auth = validate_auth_observation(observation.get("auth"))
    model = validate_model_observation(observation.get("model"))
    session = _exact_mapping(observation.get("session"), _OBS_SESSION_KEYS, "session observation")
    session = {
        "session_id": validate_identifier(session.get("session_id"), "ACP session"),
        "conversation_id": validate_identifier(
            session.get("conversation_id"), "ACP conversation"
        ),
    }
    terminal = _exact_mapping(observation.get("terminal"), _OBS_TERMINAL_KEYS, "terminal observation")
    if terminal.get("state") not in {"active", "completed", "failed", "cancelled", "halted"}:
        raise ValidationError("terminal state is invalid")
    exit_code = terminal.get("exit_code")
    if exit_code is not None and (
        isinstance(exit_code, bool) or not isinstance(exit_code, int) or exit_code < 0
    ):
        raise ValidationError("terminal exit code is invalid")
    result_id = terminal.get("result_id")
    if result_id is not None:
        result_id = validate_identifier(result_id, "ACP result")
    question = validate_question_observation(observation.get("question"))
    record_state = observation.get("record_state")
    if record_state != "candidate_non_qualifying":
        raise ValidationError("candidate record state is invalid")
    return {
        "schema": OBSERVATION_SCHEMA,
        "transport": TRANSPORT_ID,
        "target": TARGET,
        "qualification": "non_qualifying",
        "runtime": dict(runtime),
        "auth": auth,
        "model": model,
        "session": session,
        "terminal": {
            "state": terminal.get("state"),
            "exit_code": exit_code,
            "result_id": result_id,
        },
        "question": question,
        "record_state": "candidate_non_qualifying",
    }


def validate_antigravity_acp_catalog(value: Any) -> Dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValidationError("model catalog must be a mapping")
    if value.get("schema") != MODEL_CATALOG_SCHEMA:
        raise ValidationError("model catalog schema is invalid")
    if value.get("transport") != TRANSPORT_ID:
        raise ValidationError("model catalog transport is invalid")
    if value.get("target") != TARGET:
        raise ValidationError("model catalog target is invalid")
    advertised = value.get("advertised_models")
    if not isinstance(advertised, (list, tuple)) or not advertised:
        raise ValidationError("model catalog advertised_models is invalid")
    clean_advertised = []
    for item in advertised:
        if not isinstance(item, str) or not item.strip():
            raise ValidationError("model catalog model id is invalid")
        if item in clean_advertised:
            raise ValidationError("model catalog has duplicate model ids")
        clean_advertised.append(item)
    current = value.get("current_model")
    if not isinstance(current, str) or current not in clean_advertised:
        raise ValidationError("model catalog current_model is not in advertised_models")
    return {
        "schema": MODEL_CATALOG_SCHEMA,
        "transport": TRANSPORT_ID,
        "target": TARGET,
        "current_model": current,
        "advertised_models": clean_advertised,
    }


def verified_antigravity_acp_catalog() -> Dict[str, Any]:
    return {
        "schema": MODEL_CATALOG_SCHEMA,
        "transport": TRANSPORT_ID,
        "target": TARGET,
        "current_model": DEFAULT_ANTIGRAVITY_MODEL,
        "advertised_models": list(ADVERTISED_ANTIGRAVITY_MODELS),
    }


def map_runtime_antigravity_models(
    models: Any,
    *,
    requested_model: Optional[str] = None,
    catalog: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Map requested/selected/current models from one advertised catalog."""

    if not isinstance(models, Mapping):
        _raise_identity("model_observation_mismatch", "Antigravity ACP model catalog is unverified")
    current_model = models.get("currentModelId")
    if not isinstance(current_model, str) or not current_model.strip():
        _raise_identity("model_observation_mismatch", "observed Antigravity ACP model is unverified")
    current_model = current_model.strip()
    available_raw = models.get("availableModels") or models.get("availableModelIds")
    if not isinstance(available_raw, (list, tuple)) or not available_raw:
        _raise_identity(
            "model_observation_mismatch",
            "requested Antigravity ACP selector is unavailable",
        )
    advertised_ids: list[str] = []
    for item in available_raw:
        if isinstance(item, Mapping):
            mid = item.get("modelId")
        elif isinstance(item, str):
            mid = item
        else:
            _raise_identity(
                "model_observation_mismatch",
                "Antigravity ACP model catalog is unverified",
            )
            continue
        if not isinstance(mid, str) or not mid.strip():
            _raise_identity(
                "model_observation_mismatch",
                "Antigravity ACP model catalog is unverified",
            )
        mid = mid.strip()
        if mid in FALLBACK_OR_DEFAULT_MODEL_IDS:
            _raise_identity(
                "model_observation_mismatch",
                "Antigravity ACP fallback or default model is not bound requested-model proof",
            )
        if mid not in advertised_ids:
            advertised_ids.append(mid)
    if catalog is not None:
        validated = validate_antigravity_acp_catalog(catalog)
        if set(validated["advertised_models"]) != set(advertised_ids):
            _raise_identity(
                "model_observation_mismatch",
                "observed Antigravity ACP model is unverified",
            )
    requested = requested_model or DEFAULT_ANTIGRAVITY_MODEL
    if requested in FALLBACK_OR_DEFAULT_MODEL_IDS:
        _raise_identity(
            "model_observation_mismatch",
            "Antigravity ACP fallback or default model is not bound requested-model proof",
        )
    if requested not in advertised_ids:
        _raise_identity(
            "model_observation_mismatch",
            "requested Antigravity ACP selector is unavailable",
        )
    if current_model in FALLBACK_OR_DEFAULT_MODEL_IDS:
        _raise_identity(
            "model_observation_mismatch",
            "Antigravity ACP fallback or default model is not bound requested-model proof",
        )
    if current_model not in advertised_ids:
        _raise_identity(
            "model_observation_mismatch",
            "observed Antigravity ACP model is unverified",
        )
    if current_model != requested:
        _raise_identity(
            "model_observation_mismatch",
            "observed model does not match the bound Antigravity ACP runtime",
        )
    return {
        "current_model": current_model,
        "selected_model": requested,
        "advertised_models": advertised_ids,
        "requested_model": requested,
        "selection_state": "exact",
        "effort": None,
    }


def select_and_map_runtime_antigravity_models(
    runtime: Any,
    handle: Mapping[str, Any],
    *,
    requested_model: Optional[str] = None,
    catalog: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Select the requested AGY catalog model through public setModel, then remap."""

    status = runtime.get_status(
        reject_runtime_conversation_params({"handle": dict(handle)}, label="getStatus")
    )
    models = status.get("models") if isinstance(status, Mapping) else None
    requested = requested_model or DEFAULT_ANTIGRAVITY_MODEL
    if requested in FALLBACK_OR_DEFAULT_MODEL_IDS:
        _raise_identity(
            "model_observation_mismatch",
            "Antigravity ACP fallback or default model is not bound requested-model proof",
        )
    current = models.get("currentModelId") if isinstance(models, Mapping) else None
    if isinstance(current, str):
        current = current.strip()
    if current != requested:
        setter = getattr(runtime, "set_model", None)
        if not callable(setter):
            _raise_identity(
                "model_observation_mismatch",
                "observed model does not match the bound Antigravity ACP runtime",
            )
        try:
            setter(
                reject_runtime_conversation_params(
                    {"handle": dict(handle), "model": requested},
                    label="setModel",
                )
            )
        except (ValidationError, UnsupportedError):
            _raise_identity(
                "model_observation_mismatch",
                "observed model does not match the bound Antigravity ACP runtime",
            )
        status = runtime.get_status(
            reject_runtime_conversation_params({"handle": dict(handle)}, label="getStatus")
        )
        models = status.get("models") if isinstance(status, Mapping) else None
    mapped = map_runtime_antigravity_models(
        models,
        requested_model=requested_model,
        catalog=catalog,
    )
    if mapped["selected_model"] != mapped["current_model"] or mapped["selected_model"] != requested:
        _raise_identity(
            "model_observation_mismatch",
            "observed model does not match the bound Antigravity ACP runtime",
        )
    return mapped


def session_record_from_observation(
    observation: Mapping[str, Any],
    *,
    record_state: Optional[str] = None,
) -> Dict[str, Any]:
    obs = validate_candidate_observation(observation)
    state = record_state or "ACTIVE"
    if obs["terminal"]["state"] == "halted" and state in {
        "ACTIVE",
        "candidate_non_qualifying",
        None,
    }:
        state = "HALTED"
    return {
        "session": obs["session"]["session_id"],
        "target": TARGET,
        "state": state,
        "process": None,
        "transport": {"schema": "puppet.transport-binding/v1", "id": TRANSPORT_ID},
    }


def caller_fields_from_observation(
    observation: Mapping[str, Any],
    *,
    record_state: Optional[str] = None,
    halt_confirmed: Optional[bool] = None,
) -> Dict[str, Any]:
    record = session_record_from_observation(observation, record_state=record_state)
    if halt_confirmed is None:
        halt_confirmed = record["state"] == "HALTED"
    return caller_projection(
        record, transport_id=TRANSPORT_ID, halt_confirmed=halt_confirmed
    )


def _question_for_observation(question: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    if question is None:
        return {
            "state": "none",
            "interaction_id": None,
            "human_required": False,
            "outcome": None,
        }
    return {
        "state": "cancelled",
        "interaction_id": question.get("interaction_id"),
        "human_required": True,
        "outcome": "cancelled",
    }


def observation_from_runtime_turn(
    *,
    host_session: str,
    host_conversation_id: str,
    requested_model: str,
    observed_model: str,
    advertised_models: Sequence[str],
    terminal_state: str,
    result_id: str,
    question: Optional[Mapping[str, Any]] = None,
    auth: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    return validate_candidate_observation(
        {
            "schema": OBSERVATION_SCHEMA,
            "transport": TRANSPORT_ID,
            "target": TARGET,
            "qualification": "non_qualifying",
            "runtime": {
                "id": RUNTIME_ID,
                "version": RUNTIME_VERSION,
                "registry_revision": REGISTRY_REVISION,
            },
            "auth": auth
            if auth is not None
            else {
                "mode": "oauth-personal",
                "profile_env": "GEMINI_HOME",
                "credential_source": "runtime_owned",
                "account_state": "authenticated",
                "api_key_present": False,
                "cloud_credentials_present": False,
                "alternate_account": False,
                "interactive_login": False,
                "overage_state": "never",
            },
            "model": {
                "requested_id": requested_model,
                "advertised_ids": list(advertised_models),
                "observed_id": observed_model,
                "selection_state": "exact",
                "effort": None,
            },
            "session": {
                "session_id": host_session,
                "conversation_id": host_conversation_id,
            },
            "terminal": {
                "state": terminal_state,
                "exit_code": 0 if terminal_state in {"completed", "halted"} else 1,
                "result_id": result_id,
            },
            "question": _question_for_observation(question),
            "record_state": "candidate_non_qualifying",
        }
    )


def prove_antigravity_acp_observation(
    observation: Mapping[str, Any],
    *,
    expected_session: str,
    expected_conversation_id: str,
    expected_workspace: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    obs = validate_candidate_observation(observation)
    if obs["transport"] != TRANSPORT_ID:
        _raise_identity("identity_mismatch", "transport is not antigravity-acp")
    if obs["target"] != TARGET:
        _raise_identity("identity_mismatch", "target is not agy")
    if obs["session"]["session_id"] != expected_session:
        _raise_identity(
            "session_identity_mismatch",
            "observation session does not match expected session",
        )
    if obs["session"]["conversation_id"] != expected_conversation_id:
        _raise_identity(
            "session_identity_mismatch",
            "observation conversation does not match expected conversation",
        )
    return obs


def fixture_observation(**changes: Any) -> Dict[str, Any]:
    base = {
        "schema": OBSERVATION_SCHEMA,
        "transport": TRANSPORT_ID,
        "target": TARGET,
        "qualification": "non_qualifying",
        "runtime": {
            "id": RUNTIME_ID,
            "version": RUNTIME_VERSION,
            "registry_revision": REGISTRY_REVISION,
        },
        "auth": {
            "mode": "oauth-personal",
            "profile_env": "GEMINI_HOME",
            "credential_source": "runtime_owned",
            "account_state": "authenticated",
            "api_key_present": False,
            "cloud_credentials_present": False,
            "alternate_account": False,
            "interactive_login": False,
            "overage_state": "never",
        },
        "model": {
            "requested_id": DEFAULT_ANTIGRAVITY_MODEL,
            "advertised_ids": list(ADVERTISED_ANTIGRAVITY_MODELS),
            "observed_id": DEFAULT_ANTIGRAVITY_MODEL,
            "selection_state": "exact",
            "effort": None,
        },
        "session": {
            "session_id": "ses-agy-1",
            "conversation_id": "conv-agy-1",
        },
        "terminal": {
            "state": "completed",
            "exit_code": 0,
            "result_id": "req-agy-1",
        },
        "question": {
            "state": "none",
            "interaction_id": None,
            "human_required": False,
            "outcome": None,
        },
        "record_state": "candidate_non_qualifying",
    }
    base.update(changes)
    return validate_candidate_observation(base)


def _load_ownership(isolated_root: Path) -> Dict[str, Any]:
    from antigravity_acpx import load_isolated_root

    return load_isolated_root(isolated_root)


def _mark_cleanup_unknown(isolated_root: Path) -> Dict[str, Any]:
    from antigravity_acpx import mark_cleanup_unknown

    return mark_cleanup_unknown(isolated_root)


class AntigravityAcpSyntheticRuntime:
    """In-process public-runtime peer. Never starts live AGY or Cursor."""

    def __init__(
        self,
        *,
        handle: Optional[Mapping[str, Any]] = None,
        models: Optional[Mapping[str, Any]] = None,
        result: Optional[Mapping[str, Any]] = None,
        events: Optional[Sequence[Mapping[str, Any]]] = None,
        unsupported_backend_close: bool = False,
        local_cleanup_proved: bool = True,
        close_error: Optional[BaseException] = None,
        permission: Optional[Mapping[str, Any]] = None,
        question: Optional[Mapping[str, Any]] = None,
        set_model_supported: bool = True,
    ):
        self.handle = None if handle is None else dict(handle)
        self.models = dict(models) if models is not None else {
            "currentModelId": DEFAULT_ANTIGRAVITY_MODEL,
            "availableModelIds": list(ADVERTISED_ANTIGRAVITY_MODELS),
        }
        self.result = dict(result or {"status": "completed", "stopReason": "end_turn"})
        self.events = list(events or ())
        self.unsupported_backend_close = unsupported_backend_close
        self.local_cleanup_proved = local_cleanup_proved
        self.close_error = close_error
        self.permission = None if permission is None else dict(permission)
        self.question = None if question is None else dict(question)
        self.set_model_supported = set_model_supported
        self.ensure_calls: list[Dict[str, Any]] = []
        self.status_calls: list[Dict[str, Any]] = []
        self.set_model_calls: list[Dict[str, Any]] = []
        self.start_calls: list[Dict[str, Any]] = []
        self.close_calls: list[Dict[str, Any]] = []

    def ensure_session(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        reject_runtime_conversation_params(payload, label="ensureSession")
        self.ensure_calls.append(dict(payload))
        if self.handle is not None:
            return dict(self.handle)
        return {
            "sessionKey": payload["sessionKey"],
            "cwd": payload["cwd"],
            "backend": "acpx",
            "runtimeSessionName": "acpx:%s" % payload["sessionKey"],
            "acpxRecordId": "record-owned-1",
            "backendSessionId": "backend-session-1",
            "agentSessionId": "agent-session-1",
        }

    def get_status(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        reject_runtime_conversation_params(payload, label="getStatus")
        self.status_calls.append(dict(payload))
        last_request = self.start_calls[-1]["requestId"] if self.start_calls else None
        status = {"models": dict(self.models)}
        if last_request is not None:
            status["lastRequestId"] = last_request
        return status

    def set_model(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        reject_runtime_conversation_params(payload, label="setModel")
        self.set_model_calls.append(dict(payload))
        if not self.set_model_supported:
            raise ValidationError("setModel is unsupported")
        model = payload.get("model")
        advertised = []
        for item in self.models.get("availableModelIds") or self.models.get("availableModels") or ():
            if isinstance(item, Mapping):
                advertised.append(item.get("modelId"))
            else:
                advertised.append(item)
        if not isinstance(model, str) or model not in advertised:
            _raise_identity(
                "model_observation_mismatch",
                "requested Antigravity ACP selector is unavailable",
            )
        if model in FALLBACK_OR_DEFAULT_MODEL_IDS:
            _raise_identity(
                "model_observation_mismatch",
                "Antigravity ACP fallback or default model is not bound requested-model proof",
            )
        self.models["currentModelId"] = model
        return {}

    def start_turn(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        reject_runtime_conversation_params(payload, label="startTurn")
        self.start_calls.append(dict(payload))
        return {
            "requestId": payload["requestId"],
            "events": list(self.events),
            "result": dict(self.result),
        }

    def close(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        reject_runtime_conversation_params(payload, label="close")
        self.close_calls.append(dict(payload))
        if self.close_error is not None:
            raise self.close_error
        if self.unsupported_backend_close:
            raise _backend_unsupported_close(
                "Agent does not support session/close for surviving-peer."
            )
        return {"status": "completed"}

    def is_local_cleanup_proved(self, handle: Mapping[str, Any]) -> bool:
        return self.local_cleanup_proved


class AntigravityAcpNodeRuntime:
    """Pinned public createAcpRuntime through the task-owned archive closure."""

    def __init__(
        self,
        *,
        workspace: Path,
        isolated_root: Path,
        repo_root: Path,
        env: Optional[Mapping[str, str]] = None,
        synthetic_peer: bool = False,
        executable: Optional[Path] = None,
        candidate_args: Optional[Sequence[str]] = None,
    ):
        if synthetic_peer and executable is not None:
            raise ValidationError("synthetic peer injection cannot carry a candidate executable")
        driver = Path(repo_root) / CONTROLLER_RUNTIME_DRIVER
        run_env = dict(os.environ)
        if env is not None:
            run_env.update(env)
        self.kind = SYNTHETIC_PEER_KIND if synthetic_peer else CANDIDATE_RUNTIME_KIND
        self._proc = subprocess.Popen(
            ["node", str(driver)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            cwd=str(repo_root),
            env=run_env,
        )
        payload: Dict[str, Any] = {
            "cwd": str(workspace),
            "isolatedRoot": str(isolated_root),
            "syntheticPeer": True if synthetic_peer else False,
            "agent": "antigravity",
        }
        if not synthetic_peer:
            payload["candidate"] = {
                "kind": CANDIDATE_RUNTIME_KIND,
                "agent": "antigravity",
                "executable": None if executable is None else str(executable),
                "args": list(candidate_args or ()),
            }
        self._rpc("create", payload)

    def ensure_session(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        return self._rpc("ensureSession", dict(payload))

    def get_status(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        return self._rpc("getStatus", dict(payload))

    def set_model(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        return self._rpc("setModel", dict(payload))

    def start_turn(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        return self._rpc("startTurn", dict(payload))

    def close(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        return self._rpc("close", dict(payload))

    def shutdown(self) -> None:
        try:
            self._rpc("shutdown", {})
        finally:
            if self._proc.stdin is not None:
                self._proc.stdin.close()
            if self._proc.stdout is not None:
                self._proc.stdout.close()
            if self._proc.poll() is None:
                self._proc.terminate()
            self._proc.wait(timeout=30)

    def _rpc(self, op: str, payload: Mapping[str, Any]) -> Dict[str, Any]:
        if self._proc.stdin is None or self._proc.stdout is None:
            raise ValidationError("controller runtime driver is unavailable")
        message = json.dumps({"op": op, "payload": dict(payload)}, separators=(",", ":"))
        self._proc.stdin.write(message + "\n")
        self._proc.stdin.flush()
        line = self._proc.stdout.readline()
        if not line:
            raise ValidationError("controller runtime driver closed")
        response = json.loads(line)
        if response.get("ok") is not True:
            detail = response.get("error") or "controller runtime driver failed"
            code = response.get("code")
            if code in {
                "OWNER_MISMATCH",
                "SESSION_MISMATCH",
                "WORKSPACE_MISMATCH",
                "IDENTITY_MISMATCH",
            }:
                _raise_identity("identity_mismatch", str(detail))
            if code == "ACP_BACKEND_UNSUPPORTED_CONTROL":
                raise _backend_unsupported_close(str(detail))
            raise ValidationError(str(detail))
        value = response.get("value")
        return {} if value is None else dict(value)


class AntigravityAcpRuntimeRunner:
    """Derive antigravity-acp observations from a public runtime for the controller."""

    def __init__(
        self,
        runtime: Any,
        *,
        isolated_root: Path,
        owner: str,
        session: str,
        conversation_id: str,
        request_id: str,
        workspace: Mapping[str, Any],
        requested_model: Optional[str] = None,
        text: Optional[str] = None,
        catalog: Optional[Mapping[str, Any]] = None,
        halt: bool = False,
        permission: Optional[Mapping[str, Any]] = None,
        question: Optional[Mapping[str, Any]] = None,
        auth: Optional[Mapping[str, Any]] = None,
        session_mode: str = SESSION_MODE_ONESHOT,
        finish_policy: str = FINISH_POLICY_DISCARD,
    ):
        self.runtime = runtime
        self.isolated_root = Path(isolated_root)
        self.owner = owner
        self.session = session
        self.conversation_id = conversation_id
        self.request_id = request_id
        self.workspace = dict(workspace)
        self.requested_model = requested_model or DEFAULT_ANTIGRAVITY_MODEL
        self._text = None if text is None else require_runtime_task_text(text)
        self._supplied_catalog = None if catalog is None else dict(catalog)
        self._catalog = self._supplied_catalog
        self.require_halt = halt
        self.permission = None if permission is None else dict(permission)
        self.question = None if question is None else dict(question)
        self.auth = None if auth is None else dict(auth)
        if session_mode not in {SESSION_MODE_ONESHOT, SESSION_MODE_PERSISTENT}:
            raise ValidationError("antigravity-acp session mode is invalid")
        if finish_policy not in {
            FINISH_POLICY_DISCARD,
            FINISH_POLICY_RETAIN,
            FINISH_POLICY_LOCAL_RELEASE,
        }:
            raise ValidationError("antigravity-acp finish policy is invalid")
        self.session_mode = session_mode
        self.finish_policy = finish_policy
        self.discarded_events: Optional[Dict[str, Any]] = None
        self.permission_outcome: Optional[Dict[str, Any]] = None
        self.question_outcome: Optional[Dict[str, Any]] = None
        self._observation: Optional[Dict[str, Any]] = None
        self.handle: Optional[Dict[str, str]] = None
        self.backend_identity_changes: list[Dict[str, Optional[str]]] = []
        self.local_release = False
        self.persistent_state = "absent"
        self.final_discard = False
        self.backend_discard: str = "closed"

    def bind_task_text(self, text: Any) -> str:
        self._text = require_runtime_task_text(text)
        return self._text

    def has_task_text(self) -> bool:
        return self._text is not None

    @staticmethod
    def available() -> bool:
        return False

    def catalog(self) -> Optional[Dict[str, Any]]:
        if self._observation is None:
            self.observation()
        return None if self._catalog is None else dict(self._catalog)

    def observation(self) -> Dict[str, Any]:
        if self._observation is None:
            self._observation = self._derive()
        return validate_candidate_observation(self._observation)

    def _validate_ownership(self) -> Dict[str, Any]:
        ownership = _load_ownership(self.isolated_root)
        if (
            ownership.get("owner") != self.owner
            or ownership.get("session") != self.session
            or ownership.get("conversation_id") != self.conversation_id
        ):
            _raise_identity(
                "session_identity_mismatch",
                "ownership must validate before session or prompt",
            )
        if ownership.get("transport") != TRANSPORT_ID or ownership.get("target") != TARGET:
            _raise_identity(
                "identity_mismatch",
                "isolated state root is not an Antigravity ACP ownership claim",
            )
        if ownership.get("cleanup") == "unknown" or ownership.get("replacement_blocked"):
            _raise_identity(
                "cleanup_unknown",
                "process-query failure left cleanup unknown; replacement is blocked",
            )
        return ownership

    def _fence_cleanup(self) -> None:
        try:
            _mark_cleanup_unknown(self.isolated_root)
        except Exception:
            pass

    def _is_unsupported_backend_session_close(self, exc: BaseException) -> bool:
        code = getattr(exc, "code", "")
        return code == "ACP_BACKEND_UNSUPPORTED_CONTROL" or bool(
            re.search(r"session/close", str(exc), re.I)
        )

    def _is_local_cleanup_proved(self, handle: Mapping[str, Any]) -> bool:
        checker = getattr(self.runtime, "is_local_cleanup_proved", None)
        if callable(checker):
            return bool(checker(handle))
        return bool(getattr(self.runtime, "local_cleanup_proved", False))

    def _owned_close(
        self,
        handle: Mapping[str, Any],
        *,
        primary: Optional[BaseException] = None,
        discard_persistent_state: bool = True,
        reason: str = "antigravity-acp-owned-close",
    ) -> None:
        try:
            self.runtime.close(
                reject_runtime_conversation_params(
                    {
                        "handle": dict(handle),
                        "reason": reason,
                        "discardPersistentState": discard_persistent_state,
                    },
                    label="close",
                )
            )
            self.backend_discard = "closed"
        except BaseException as exc:
            if self._is_unsupported_backend_session_close(exc) and self._is_local_cleanup_proved(
                handle
            ):
                self.backend_discard = "unsupported_local_cleanup_proved"
                if discard_persistent_state:
                    self.final_discard = True
                    self.persistent_state = "discarded"
                else:
                    self.local_release = True
                    self.persistent_state = "retained"
                if primary is not None:
                    raise primary
                return
            self._fence_cleanup()
            if primary is not None:
                raise primary
            raise
        if discard_persistent_state:
            self.final_discard = True
            self.persistent_state = "discarded"
        else:
            self.local_release = True
            self.persistent_state = "retained"
        if primary is not None:
            raise primary

    def _reject_conflated_ids(self, handle: Mapping[str, str]) -> None:
        foreign = {
            handle.get("backendSessionId"),
            handle.get("acpxRecordId"),
            handle.get("runtimeSessionName"),
            handle.get("agentSessionId"),
        }
        host = {self.conversation_id, self.request_id}
        if foreign & host:
            _raise_identity(
                "identity_mismatch",
                "runtime identities must not be fabricated from host correlation",
            )

    def _bind_handle(self, raw_handle: Mapping[str, Any]) -> Dict[str, str]:
        handle = project_runtime_handle(raw_handle)
        if handle.get("sessionKey") != self.session:
            _raise_identity(
                "session_identity_mismatch",
                "runtime sessionKey does not match the host session",
            )
        if os.path.realpath(handle.get("cwd", "")) != os.path.realpath(
            self.workspace["path"]
        ):
            _raise_identity(
                "workspace_identity_mismatch",
                "runtime cwd does not match the bound checkout",
            )
        self._reject_conflated_ids(handle)
        previous = self.handle
        if previous is not None:
            previous_backend = previous.get("backendSessionId")
            next_backend = handle.get("backendSessionId")
            if previous_backend != next_backend:
                self.backend_identity_changes.append(
                    {
                        "previous_backend_session_id": previous_backend,
                        "backend_session_id": next_backend,
                    }
                )
        self.handle = handle
        self.persistent_state = "retained"
        return handle

    def _ensure_owned_handle(self, *, reconnect: bool = False) -> Dict[str, str]:
        if self.handle is not None and not reconnect:
            return dict(self.handle)
        ensure_input = reject_runtime_conversation_params(
            {
                "sessionKey": self.session,
                "agent": "antigravity",
                "mode": self.session_mode,
                "cwd": self.workspace["path"],
            },
            label="ensureSession",
        )
        return self._bind_handle(self.runtime.ensure_session(ensure_input))

    def _run_turn(self, handle: Mapping[str, Any]) -> Dict[str, Any]:
        text = require_runtime_task_text(self._text)
        mapped = select_and_map_runtime_antigravity_models(
            self.runtime,
            handle,
            requested_model=self.requested_model,
            catalog=self._supplied_catalog,
        )
        self._catalog = (
            self._supplied_catalog
            if self._supplied_catalog is not None
            else {
                "schema": MODEL_CATALOG_SCHEMA,
                "transport": TRANSPORT_ID,
                "target": TARGET,
                "current_model": mapped["current_model"],
                "advertised_models": mapped["advertised_models"],
            }
        )
        turn = self.runtime.start_turn(
            reject_runtime_conversation_params(
                {
                    "handle": dict(handle),
                    "text": text,
                    "mode": "prompt",
                    "requestId": self.request_id,
                },
                label="startTurn",
            )
        )
        if not isinstance(turn, Mapping):
            raise ValidationError("runtime turn is missing")
        if turn.get("requestId") != self.request_id:
            _raise_identity(
                "identity_mismatch",
                "returned turn request does not match the host request",
            )
        self.discarded_events = drain_runtime_turn_events(turn.get("events"))
        result = turn.get("result")
        if not isinstance(result, Mapping) or result.get("status") not in {
            "completed",
            "failed",
            "cancelled",
        }:
            raise ValidationError("runtime turn result is incomplete")
        after = self.runtime.get_status(
            reject_runtime_conversation_params({"handle": dict(handle)}, label="getStatus")
        )
        if isinstance(after, Mapping) and "lastRequestId" in after:
            if after.get("lastRequestId") != self.request_id:
                _raise_identity(
                    "identity_mismatch",
                    "status lastRequestId does not match the completed turn request",
                )
        terminal_state = "completed" if result.get("status") == "completed" else "failed"
        if self.require_halt:
            terminal_state = "halted"
        return observation_from_runtime_turn(
            host_session=self.session,
            host_conversation_id=self.conversation_id,
            requested_model=self.requested_model,
            observed_model=mapped["current_model"],
            advertised_models=mapped["advertised_models"],
            terminal_state=terminal_state,
            result_id=self.request_id,
            question=self.question_outcome,
            auth=self.auth,
        )

    def _apply_finish_policy(self, handle: Mapping[str, Any]) -> None:
        if self.require_halt or self.session_mode == SESSION_MODE_ONESHOT:
            self._owned_close(handle, discard_persistent_state=True)
            return
        if self.finish_policy == FINISH_POLICY_DISCARD:
            self._owned_close(handle, discard_persistent_state=True)
            return
        if self.finish_policy == FINISH_POLICY_LOCAL_RELEASE:
            self._owned_close(
                handle,
                discard_persistent_state=False,
                reason="antigravity-acp-local-release",
            )
            return
        self.persistent_state = "retained"

    def _derive(self) -> Dict[str, Any]:
        self._validate_ownership()
        if self.permission is not None:
            self.permission_outcome = require_unsupported_permission_outcome(self.permission)
        if self.question is not None:
            self.question_outcome = require_unsupported_question_outcome(self.question)
        require_runtime_task_text(self._text)
        handle: Optional[Dict[str, str]] = None
        try:
            handle = self._ensure_owned_handle()
            observation = self._run_turn(handle)
            self._apply_finish_policy(handle)
            return observation
        except BaseException as exc:
            if handle is not None and handle.get("sessionKey") == self.session:
                try:
                    self._owned_close(handle, primary=exc)
                except Exception:
                    raise exc
            elif handle is not None:
                self._fence_cleanup()
            raise

    def next_turn(
        self,
        *,
        text: Any,
        request_id: str,
        expected_workspace: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Bind a fresh request to the same owned handle. Never replay a cached turn."""

        self._validate_ownership()
        if expected_workspace is not None:
            if os.path.realpath(str(expected_workspace["path"])) != os.path.realpath(
                self.workspace["path"]
            ):
                _raise_identity(
                    "workspace_identity_mismatch",
                    "runtime cwd does not match the bound checkout",
                )
        if self.handle is None:
            raise ValidationError("owned runtime session is missing")
        self.bind_task_text(text)
        self.request_id = validate_identifier(request_id, "antigravity-acp request")
        self.require_halt = False
        observation = self._run_turn(self.handle)
        self._observation = validate_candidate_observation(observation)
        return self._observation

    def finish(self, *, discard_persistent_state: bool = True) -> Dict[str, str]:
        """Final close of the owned handle. Distinct from local release and retain."""

        if self.handle is None:
            raise ValidationError("owned runtime session is missing")
        if self.final_discard:
            raise ValidationError("owned runtime session already discarded")
        handle = dict(self.handle)
        self._owned_close(
            handle,
            discard_persistent_state=discard_persistent_state,
            reason=(
                "antigravity-acp-final-discard"
                if discard_persistent_state
                else "antigravity-acp-local-release"
            ),
        )
        return {
            "local_release": self.local_release,
            "persistent_state": self.persistent_state,
            "final_discard": self.final_discard,
            "backend_discard": self.backend_discard,
        }


class AntigravityAcpRunnerFixture:
    """Deterministic Antigravity ACP observation runner. Never starts a live process."""

    def __init__(
        self,
        observation: Optional[Mapping[str, Any]] = None,
        *,
        catalog: Optional[Mapping[str, Any]] = None,
    ):
        self._observation = (
            dict(observation) if observation is not None else fixture_observation()
        )
        self._catalog = dict(catalog) if catalog is not None else None

    @staticmethod
    def available() -> bool:
        return False

    def observation(self) -> Dict[str, Any]:
        return validate_candidate_observation(self._observation)

    def catalog(self) -> Optional[Dict[str, Any]]:
        return None if self._catalog is None else dict(self._catalog)


class AntigravityAcpController:
    """Structured Antigravity ACP transport. Never constructs tmux or agy-print."""

    transport_id: str = TRANSPORT_ID
    target: str = TARGET

    def __init__(
        self,
        registry_root: Path,
        *,
        observer: Optional[Mapping[str, Any]] = None,
        _observer: Optional[Mapping[str, Any]] = None,
        runner: Any = None,
        _runner: Any = None,
        catalog: Optional[Mapping[str, Any]] = None,
    ):
        self.registry_root = Path(registry_root)
        self.observer = observer if observer is not None else _observer
        self.runner = runner if runner is not None else _runner
        self.catalog = catalog

    @staticmethod
    def available() -> bool:
        return False

    def require_observation(self) -> Dict[str, Any]:
        if self.runner is not None:
            if self.runner.available():
                _raise_unsupported(
                    "transport_unavailable",
                    "antigravity-acp runner fixture must stay fail-closed",
                )
            return self.runner.observation()
        if self.observer is None:
            _raise_unavailable("antigravity-acp structured observation is unavailable")
        return validate_candidate_observation(self.observer)

    def require_catalog(
        self, catalog: Optional[Mapping[str, Any]] = None
    ) -> Dict[str, Any]:
        if catalog is not None:
            return validate_antigravity_acp_catalog(catalog)
        if self.runner is not None:
            observed = self.runner.catalog()
            if observed is not None:
                return validate_antigravity_acp_catalog(observed)
        if self.catalog is not None:
            return validate_antigravity_acp_catalog(self.catalog)
        return verified_antigravity_acp_catalog()

    def prove(
        self,
        *,
        expected_session: Optional[str] = None,
        expected_conversation_id: Optional[str] = None,
        expected_workspace: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        observation = self.require_observation()
        return prove_antigravity_acp_observation(
            observation,
            expected_session=expected_session or observation["session"]["session_id"],
            expected_conversation_id=(
                expected_conversation_id or observation["session"]["conversation_id"]
            ),
            expected_workspace=expected_workspace,
        )

    def caller_result(
        self,
        *,
        expected_session: Optional[str] = None,
        expected_conversation_id: Optional[str] = None,
        expected_workspace: Optional[Mapping[str, Any]] = None,
        requested_model: Optional[str] = None,
        expected_observed_model: Optional[str] = None,
        record_state: Optional[str] = None,
        halt_confirmed: Optional[bool] = None,
        catalog: Optional[Mapping[str, Any]] = None,
        require_halt: bool = False,
    ) -> Dict[str, Any]:
        observation = self.require_observation()
        expected_session = expected_session or observation["session"]["session_id"]
        expected_conversation_id = (
            expected_conversation_id or observation["session"]["conversation_id"]
        )
        proved = self.prove(
            expected_session=expected_session,
            expected_conversation_id=expected_conversation_id,
            expected_workspace=expected_workspace,
        )
        if requested_model is not None and proved["model"]["requested_id"] != requested_model:
            _raise_identity(
                "model_observation_mismatch",
                "observed model does not match the bound Antigravity ACP runtime",
            )
        if (
            expected_observed_model is not None
            and proved["model"]["observed_id"] != expected_observed_model
        ):
            _raise_identity(
                "model_observation_mismatch",
                "observed model does not match the bound Antigravity ACP runtime",
            )
        if require_halt and proved["terminal"]["state"] != "halted":
            _raise_identity("identity_mismatch", "antigravity-acp halt was not observed")
        halted = proved["terminal"]["state"] == "halted"
        fields = caller_fields_from_observation(
            proved,
            record_state="HALTED" if halted else record_state,
            halt_confirmed=True if halt_confirmed is None and halted else halt_confirmed,
        )
        return {
            "ok": True,
            "session": expected_session,
            "state": (
                "HALTED"
                if fields["caller_outcome"]["halt"] == "confirmed"
                else (record_state or "ACTIVE")
            ),
            "live_antigravity_acp_claimed": False,
            "antigravity_acp": proved,
            **fields,
        }


__all__ = [
    "ACPX_RELEASE",
    "ACPX_SOURCE_COMMIT",
    "ADAPTER_ID",
    "ADVERTISED_ANTIGRAVITY_MODELS",
    "AntigravityAcpController",
    "AntigravityAcpNodeRuntime",
    "AntigravityAcpRunnerFixture",
    "AntigravityAcpRuntimeRunner",
    "AntigravityAcpSyntheticRuntime",
    "CANDIDATE_SCHEMA",
    "CONTROLLER_RUNTIME_DRIVER",
    "DEFAULT_ANTIGRAVITY_MODEL",
    "DEFAULT_ROUTE",
    "FALLBACK_OR_DEFAULT_MODEL_IDS",
    "GENERIC_ACP_ID",
    "MODEL_CATALOG_SCHEMA",
    "OBSERVATION_SCHEMA",
    "OWNERSHIP_SCHEMA",
    "REGISTRY_REVISION",
    "RUNTIME_ID",
    "RUNTIME_VERSION",
    "TARGET",
    "TRANSPORT_ID",
    "caller_fields_from_observation",
    "candidate_contract",
    "fixture_observation",
    "map_runtime_antigravity_models",
    "observation_from_runtime_turn",
    "prove_antigravity_acp_observation",
    "require_antigravity_acp_target",
    "session_record_from_observation",
    "validate_antigravity_acp_catalog",
    "validate_auth_observation",
    "validate_candidate_contract",
    "validate_candidate_observation",
    "validate_model_observation",
    "validate_question_observation",
    "verified_antigravity_acp_catalog",
    "build_antigravity_acp_candidate_runner",
    "select_and_map_runtime_antigravity_models",
]


def claim_antigravity_acp_isolated_root(
    isolated_root: Path,
    *,
    owner: str,
    session: str,
    conversation_id: str,
) -> Dict[str, Any]:
    from antigravity_acpx import claim_isolated_root

    root = Path(isolated_root)
    root.mkdir(parents=True, exist_ok=True)
    os.chmod(root, 0o700)
    return claim_isolated_root(
        root,
        owner=owner,
        session=session,
        conversation_id=conversation_id,
    )


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def build_antigravity_acp_candidate_runner(
    *,
    session: str,
    contract: Any,
    state_root: Path,
    prompt: Any,
    requested_model: Optional[str],
    expected_workspace: Mapping[str, Any],
    catalog: Optional[Mapping[str, Any]] = None,
    runtime: Any = None,
    synthetic_peer: bool = False,
    executable: Optional[Path] = None,
    isolated_root: Optional[Path] = None,
    conversation_id: Optional[str] = None,
    request_id: Optional[str] = None,
    session_mode: str = SESSION_MODE_PERSISTENT,
    finish_policy: str = FINISH_POLICY_RETAIN,
    halt: bool = False,
    repo_root: Optional[Path] = None,
    env: Optional[Mapping[str, str]] = None,
) -> AntigravityAcpRuntimeRunner:
    """Construct the task-owned AGY candidate runner. Synthetic peer is test-only."""

    text = require_runtime_task_text(prompt)
    owner = validate_identifier(contract.controller, "controller")
    host_conversation = conversation_id or ("conv-%s" % session)
    host_request = request_id or ("%s-turn-1" % session)
    isolated = (
        Path(isolated_root)
        if isolated_root is not None
        else Path(state_root) / session / "acp-isolated"
    )
    claim_antigravity_acp_isolated_root(
        isolated,
        owner=owner,
        session=session,
        conversation_id=host_conversation,
    )
    if runtime is None:
        runtime = AntigravityAcpNodeRuntime(
            workspace=Path(expected_workspace["path"]),
            isolated_root=isolated,
            repo_root=repo_root or _repo_root(),
            env=env,
            synthetic_peer=synthetic_peer,
            executable=None if synthetic_peer else executable,
        )
    return AntigravityAcpRuntimeRunner(
        runtime,
        isolated_root=isolated,
        owner=owner,
        session=session,
        conversation_id=host_conversation,
        request_id=host_request,
        workspace=expected_workspace,
        requested_model=requested_model or contract.requested_model,
        text=text,
        catalog=catalog,
        halt=halt,
        session_mode=session_mode,
        finish_policy=finish_policy,
    )
