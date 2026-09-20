"""Non-qualifying contract for Google's official Antigravity ACP runtime.

This module is deliberately not a Puppet transport.  It pins the upstream
runtime shape and validates body-free candidate metadata so a future adapter
cannot silently reuse generic ``acp``, an API/cloud credential, an unobserved
model, or an automatic answer to an Antigravity interaction question.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Mapping

from .errors import ValidationError
from .safety import validate_identifier


TRANSPORT_ID = "antigravity-acp"
GENERIC_ACP_ID = "acp"
TARGET = "agy"
DEFAULT_ROUTE = "agy-print"
CANDIDATE_SCHEMA = "puppet.antigravity-acp-candidate/v1"
OBSERVATION_SCHEMA = "puppet.antigravity-acp-observation/v1"

REGISTRY_REVISION = "81bf71b55e15f630c4fb8a86d20d3088071d2071"
RUNTIME_ID = "antigravity-acp"
RUNTIME_VERSION = "1.1.1"
ACPX_SOURCE_COMMIT = "50a47ad10a75431cbc276ec9b555d11fe1f69c84"
ACPX_RELEASE = "0.17.1"

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
    if terminal.get("state") not in {"active", "completed", "failed", "cancelled"}:
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


__all__ = [
    "ACPX_RELEASE",
    "ACPX_SOURCE_COMMIT",
    "CANDIDATE_SCHEMA",
    "DEFAULT_ROUTE",
    "GENERIC_ACP_ID",
    "OBSERVATION_SCHEMA",
    "REGISTRY_REVISION",
    "RUNTIME_ID",
    "RUNTIME_VERSION",
    "TARGET",
    "TRANSPORT_ID",
    "candidate_contract",
    "validate_auth_observation",
    "validate_candidate_contract",
    "validate_candidate_observation",
    "validate_model_observation",
    "validate_question_observation",
]
