"""Immutable native instruction-plane descriptor parsing and validation."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Mapping, Sequence

from .contracts import TARGETS
from .errors import ValidationError
from .safety import (
    canonical_json_bytes,
    sha256_bytes,
    validate_bounded_json,
    validate_identifier,
    validate_sha256,
)

_SCHEMA_NAME = "puppet.instruction-plane/v1"
_FIELD_KEYS = {
    "schema",
    "descriptor_id",
    "target",
    "plane",
    "status",
    "materialize",
    "launch_delta",
    "rollback",
    "assertions",
    "blockers",
}
_TARGET_KEYS = {
    "harness",
    "version",
    "adapter_manifest_sha256",
    "requested_model",
    "observed_model",
    "config_fingerprint",
}
_STATUS_KEYS = {"surface", "activation"}
_MATERIALIZE_KEYS = {
    "artifact_id",
    "root_ref",
    "relative_path",
    "content_ref",
    "write_mode",
}
_LAUNCH_DELTA_KEYS = {"cwd_ref", "env", "argv"}
_ROLLBACK_KEYS = {"owned_artifacts", "preimage_sha256", "retain_hash_only_proof"}
_PREIMAGE_KEYS = {"artifact_id", "sha256"}

_SUPPORTED_TARGETS = TARGETS
_SUPPORTED_TARGET_VERSIONS = {
    "agy": "1.1.5",
    "claude": "2.1.215",
    "codex": "0.145.0",
    "cursor": "2026.07.17-3e2a980",
    "grok": "0.2.106",
}
_SUPPORTED_PLAN_TYPES = {
    "harness_global",
    "workspace_addendum",
    "per_run_additive",
}
_SUPPORTED_SURFACES = {"factual", "hypothesis", "unsupported"}
_SUPPORTED_ACTIVATIONS = {"qualification_only", "disabled", "qualified"}
_SUPPORTED_ROOT_REFS = {"config_root", "workspace_root", "ephemeral_root"}
_SUPPORTED_CWD_REFS = {"workspace_root"}
_SUPPORTED_WRITE_MODES = {"create_only", "patch_if_base_sha256"}
_SUPPORTED_CONTENT_REFS = {"effective_contract"}
_SUPPORTED_LITERAL_FLAGS = {
    "--agent",
    "--append-system-prompt-file",
    "--cwd",
    "--output-style",
    "--profile",
    "--setting-sources",
    "--workspace",
}
_SUPPORTED_NAME_REFS = {
    "project_setting_sources",
    "puppet_agent_name",
    "puppet_output_style_name",
    "puppet_profile_name",
}
_SUPPORTED_ENV_REFS = {
    ("CLAUDE_CONFIG_DIR", "config_root_path"),
    ("CODEX_HOME", "config_root_path"),
    ("GROK_DISABLE_AUTOUPDATER", "true_literal"),
    ("GROK_HOME", "config_root_path"),
}


def _validate_text(
    value: Any,
    *,
    label: str,
    max_length: int,
    allow_empty: bool = False,
) -> str:
    if not isinstance(value, str):
        raise ValidationError("%s must be text" % label)
    if not allow_empty and not value.strip():
        raise ValidationError("%s must not be empty" % label)
    if not all(ch.isprintable() for ch in value):
        raise ValidationError("%s must contain only printable Unicode" % label)
    if len(value) > max_length:
        raise ValidationError("%s exceeds the allowed size" % label)
    return value


def _validate_target_version(value: str, *, label: str) -> str:
    version = _validate_text(value, label=label, max_length=100)
    if not version or version.startswith(".") or version.endswith("."):
        raise ValidationError("%s is not a valid version" % label)

    if version.count("-") > 1:
        raise ValidationError("%s is not a valid version" % label)

    if "-" in version:
        base_version, revision = version.split("-", 1)
        if not revision or not revision.isalnum() or len(revision) < 6:
            raise ValidationError("%s is not a valid version" % label)
    else:
        base_version = version

    if "." in base_version:
        if not all(part.isdigit() for part in base_version.split(".")):
            raise ValidationError("%s is not a valid version" % label)
    elif not base_version.replace("-", "").replace("_", "").isalnum():
        raise ValidationError("%s is not a valid version" % label)
    return version


def _validate_symbolic(value: Any, *, label: str) -> str:
    value = _validate_text(value, label=label, max_length=128)
    if not value:
        raise ValidationError("%s must not be empty" % label)
    first = value[0]
    if not first.isalpha():
        raise ValidationError("%s must start with a letter" % label)
    allowed = value.replace("_", "").replace("-", "").replace(".", "")
    if not allowed.isalnum():
        raise ValidationError("%s is not a symbolic reference" % label)
    return value


def _validate_reference_path(value: Any, *, label: str) -> str:
    path = _validate_text(value, label=label, max_length=256)
    if not path:
        raise ValidationError("%s must be non-empty" % label)
    if path.startswith("/") or "\\" in path:
        raise ValidationError("%s must be relative and slash-style" % label)
    if any(part in {"", ".", ".."} for part in path.split("/")):
        raise ValidationError(
            "%s must not contain absolute or traversal components" % label
        )
    return path


def _parse_json_no_duplicates(raw: str) -> dict[str, Any]:
    def dedupe_checker(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
        obj = {}
        seen = set()
        for key, value in pairs:
            if key in seen:
                raise ValidationError("duplicate JSON key")
            seen.add(key)
            obj[key] = value
        return obj

    return json.loads(raw, object_pairs_hook=dedupe_checker)


def _validate_env_name(value: Any, *, label: str) -> str:
    value = _validate_text(value, label=label, max_length=128)
    if not value:
        raise ValidationError("%s must not be empty" % label)
    if not all(ch.isupper() or ch.isdigit() or ch == "_" for ch in value):
        raise ValidationError("%s must be an environment name" % label)
    if not value[0].isupper() and value[0] != "_":
        raise ValidationError("%s must be an environment name" % label)
    return value


def _validate_flag(value: Any, *, label: str) -> str:
    flag = _validate_text(value, label=label, max_length=64)
    if not flag.startswith("-"):
        raise ValidationError("%s must be a literal flag" % label)
    if any(ch in flag for ch in ("\t", "\n", "\r", " ")):
        raise ValidationError("%s must be flag-like" % label)
    if "=" in flag:
        raise ValidationError("%s is not a literal flag" % label)
    if flag == "-" or flag == "--":
        raise ValidationError("%s is not a literal flag" % label)
    if flag not in _SUPPORTED_LITERAL_FLAGS:
        raise ValidationError("%s is not an allowlisted instruction-plane flag" % label)
    return flag


def _validate_target(value: Any) -> Dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValidationError("target must be an object")
    if set(value) != _TARGET_KEYS:
        raise ValidationError("target fields are invalid")

    harness = value.get("harness")
    if harness not in _SUPPORTED_TARGETS:
        raise ValidationError("unsupported target")

    version = _validate_target_version(value.get("version"), label="target version")
    if version != _SUPPORTED_TARGET_VERSIONS[harness]:
        raise ValidationError(
            "target version is not the exact supported census version"
        )
    adapter_manifest_sha256 = validate_sha256(
        value.get("adapter_manifest_sha256"),
        "target adapter_manifest_sha256",
    )

    requested_model = _validate_text(
        value.get("requested_model"),
        label="target requested_model",
        max_length=64,
    )
    if requested_model != "default":
        raise ValidationError("requested_model must be default")

    observed_model = _validate_text(
        value.get("observed_model"),
        label="target observed_model",
        max_length=256,
    )
    if observed_model != "unavailable":
        if not observed_model.strip():
            raise ValidationError(
                "target observed_model must be unavailable or non-empty"
            )

    config_fingerprint = _validate_text(
        value.get("config_fingerprint"),
        label="target config_fingerprint",
        max_length=64,
    )
    if config_fingerprint != "unavailable":
        validate_sha256(config_fingerprint, "target config_fingerprint")

    return {
        "harness": harness,
        "version": version,
        "adapter_manifest_sha256": adapter_manifest_sha256,
        "requested_model": requested_model,
        "observed_model": observed_model,
        "config_fingerprint": config_fingerprint,
    }


def _validate_status(value: Any) -> Dict[str, str]:
    if not isinstance(value, Mapping):
        raise ValidationError("status must be an object")
    if set(value) != _STATUS_KEYS:
        raise ValidationError("status fields are invalid")

    surface = _validate_text(
        value.get("surface"), label="status surface", max_length=32
    )
    activation = _validate_text(
        value.get("activation"),
        label="status activation",
        max_length=32,
    )
    if surface not in _SUPPORTED_SURFACES:
        raise ValidationError("status surface is unsupported")
    if activation not in _SUPPORTED_ACTIVATIONS:
        raise ValidationError("status activation is unsupported")
    if activation == "qualified" and surface != "factual":
        raise ValidationError("only factual descriptors can be qualified")
    if surface in {"unsupported", "hypothesis"} and activation != "disabled":
        raise ValidationError(
            "unsupported or hypothesis descriptors cannot be activatable"
        )

    return {"surface": surface, "activation": activation}


def _validate_materialize(
    value: Any,
    *,
    allow_empty: bool,
) -> List[Dict[str, Any]]:
    if not isinstance(value, list) or len(value) > 64:
        raise ValidationError("materialize must be a bounded list")
    if not value and not allow_empty:
        raise ValidationError("materialize must be a non-empty bounded list")

    materialize: List[Dict[str, Any]] = []
    if not value:
        return materialize

    artifact_ids = set()
    destinations: List[tuple[str, tuple[str, ...]]] = []
    for entry in value:
        if not isinstance(entry, Mapping):
            raise ValidationError("materialize entry must be an object")
        if set(entry) != _MATERIALIZE_KEYS:
            raise ValidationError("materialize entry fields are invalid")

        artifact_id = validate_identifier(entry["artifact_id"], "artifact_id")
        if artifact_id in artifact_ids:
            raise ValidationError("materialize artifact ids must be unique")
        artifact_ids.add(artifact_id)

        root_ref = _validate_text(
            entry["root_ref"], label="materialize root_ref", max_length=32
        )
        if root_ref not in _SUPPORTED_ROOT_REFS:
            raise ValidationError("unsupported root_ref")

        relative_path = _validate_reference_path(
            entry["relative_path"],
            label="materialize relative_path",
        )
        destination = (root_ref, tuple(relative_path.split("/")))
        for existing_root, existing_parts in destinations:
            if existing_root != root_ref:
                continue
            if (
                destination[1] == existing_parts
                or destination[1][: len(existing_parts)] == existing_parts
                or existing_parts[: len(destination[1])] == destination[1]
            ):
                raise ValidationError(
                    "materialize destinations must be unique and non-overlapping"
                )
        destinations.append(destination)
        content_ref = _validate_text(
            entry["content_ref"],
            label="materialize content_ref",
            max_length=64,
        )
        if content_ref not in _SUPPORTED_CONTENT_REFS:
            raise ValidationError("content_ref must be symbolic")

        write_mode = _validate_text(
            entry["write_mode"],
            label="materialize write_mode",
            max_length=32,
        )
        if write_mode not in _SUPPORTED_WRITE_MODES:
            raise ValidationError("unsupported materialization write_mode")

        materialize.append(
            {
                "artifact_id": artifact_id,
                "root_ref": root_ref,
                "relative_path": relative_path,
                "content_ref": content_ref,
                "write_mode": write_mode,
            }
        )
    return materialize


def _validate_ids(value: Any, *, label: str) -> List[str]:
    if not isinstance(value, list) or len(value) > 64:
        raise ValidationError("%s must be a bounded list" % label)
    normalized: List[str] = []
    seen = set()
    for item in value:
        identifier = validate_identifier(item, "%s id" % label)
        if identifier in seen:
            raise ValidationError("%s ids must be unique" % label)
        seen.add(identifier)
        normalized.append(identifier)
    return sorted(normalized)


def _validate_launch_delta(
    value: Any,
    *,
    materialize_keys: Sequence[str],
) -> Dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValidationError("launch_delta must be an object")
    if set(value) != _LAUNCH_DELTA_KEYS:
        raise ValidationError("launch_delta fields are invalid")

    cwd_ref = value.get("cwd_ref")
    if cwd_ref is not None:
        cwd_ref = _validate_text(cwd_ref, label="launch_delta cwd_ref", max_length=32)
        if cwd_ref not in _SUPPORTED_CWD_REFS:
            raise ValidationError("unsupported launch_delta cwd_ref")

    env = value.get("env")
    if not isinstance(env, list) or len(env) > 64:
        raise ValidationError("launch_delta env must be a bounded list")
    normalized_env = []
    env_names = set()
    for entry in env:
        if not isinstance(entry, Mapping):
            raise ValidationError("launch env entry must be an object")
        if set(entry) != {"name", "value_ref"}:
            raise ValidationError("launch env entry fields are invalid")
        name = _validate_env_name(entry["name"], label="launch env name")
        value_ref = _validate_symbolic(entry["value_ref"], label="launch env value_ref")
        if (name, value_ref) not in _SUPPORTED_ENV_REFS:
            raise ValidationError("launch env binding is not allowlisted")
        if name in env_names:
            raise ValidationError("launch env names must be unique")
        env_names.add(name)
        normalized_env.append({"name": name, "value_ref": value_ref})

    argv = value.get("argv")
    if not isinstance(argv, list) or len(argv) > 128:
        raise ValidationError("launch_delta argv must be a bounded list")
    normalized_argv = []
    for entry in argv:
        if not isinstance(entry, Mapping):
            raise ValidationError("launch argv entry must be an object")
        keys = set(entry)
        if len(keys) != 1:
            raise ValidationError("launch argv entry fields are invalid")
        if keys == {"literal"}:
            normalized_argv.append(
                {"literal": _validate_flag(entry["literal"], label="argv literal")}
            )
        elif keys == {"path_ref"}:
            path_ref = _validate_text(
                entry["path_ref"], label="argv path_ref", max_length=128
            )
            if path_ref not in materialize_keys:
                raise ValidationError(
                    "argv path_ref references unknown materialize artifact"
                )
            normalized_argv.append({"path_ref": path_ref})
        elif keys == {"name_ref"}:
            name_ref = _validate_symbolic(entry["name_ref"], label="argv name_ref")
            if name_ref not in _SUPPORTED_NAME_REFS:
                raise ValidationError("argv name_ref is not allowlisted")
            normalized_argv.append({"name_ref": name_ref})
        elif keys == {"root_ref"}:
            root_ref = _validate_text(
                entry["root_ref"], label="argv root_ref", max_length=32
            )
            if root_ref not in _SUPPORTED_ROOT_REFS:
                raise ValidationError("argv root_ref is unsupported")
            normalized_argv.append({"root_ref": root_ref})
        else:
            raise ValidationError("launch argv entry fields are invalid")

    return {
        "cwd_ref": cwd_ref,
        "env": sorted(normalized_env, key=lambda item: item["name"]),
        "argv": normalized_argv,
    }


def _validate_rollback(
    value: Any,
    *,
    materialize: Sequence[Mapping[str, Any]],
    materialize_keys: Sequence[str],
    allow_empty: bool = False,
) -> Dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValidationError("rollback must be an object")
    if set(value) != _ROLLBACK_KEYS:
        raise ValidationError("rollback fields are invalid")

    owned_artifacts = _validate_ids(
        value.get("owned_artifacts"), label="rollback owned_artifacts"
    )
    if allow_empty and not materialize_keys and not owned_artifacts:
        pass
    elif not materialize_keys and owned_artifacts:
        raise ValidationError(
            "rollback owned_artifacts must be empty for empty materialize"
        )
    elif not owned_artifacts:
        raise ValidationError("rollback must own at least one artifact")
    if materialize_keys and set(owned_artifacts) != set(materialize_keys):
        raise ValidationError(
            "rollback owned_artifacts must exactly match materialize artifacts"
        )
    for artifact_id in owned_artifacts:
        if artifact_id not in materialize_keys:
            raise ValidationError("rollback references unknown artifact")

    preimage = value.get("preimage_sha256")
    if not isinstance(preimage, list) or len(preimage) > 64:
        raise ValidationError("rollback preimage_sha256 must be a bounded list")
    normalized_preimage: List[Dict[str, str]] = []
    preimage_artifacts = set()
    for entry in preimage:
        if not isinstance(entry, Mapping) or set(entry) != _PREIMAGE_KEYS:
            raise ValidationError("rollback preimage entry fields are invalid")
        artifact_id = validate_identifier(
            entry["artifact_id"], "rollback preimage artifact_id"
        )
        if artifact_id not in materialize_keys:
            raise ValidationError("rollback preimage references unknown artifact")
        if artifact_id in preimage_artifacts:
            raise ValidationError("rollback preimage entries must be unique")
        preimage_artifacts.add(artifact_id)
        sha = validate_sha256(entry["sha256"], "rollback preimage sha256")
        normalized_preimage.append({"artifact_id": artifact_id, "sha256": sha})

    if not materialize_keys and preimage_artifacts:
        raise ValidationError(
            "rollback preimage_sha256 must be empty for empty materialize"
        )

    for entry in materialize:
        if entry["write_mode"] == "patch_if_base_sha256":
            if entry["artifact_id"] not in preimage_artifacts:
                raise ValidationError(
                    "materialize entries with patch_if_base_sha256 need rollback preimage"
                )
        if (
            entry["artifact_id"] in preimage_artifacts
            and entry["write_mode"] == "create_only"
        ):
            raise ValidationError("create_only entries cannot include preimage hashes")

    retain_hash_only_proof = value.get("retain_hash_only_proof")
    if retain_hash_only_proof is not True:
        raise ValidationError("rollback retain_hash_only_proof must be true")

    return {
        "owned_artifacts": owned_artifacts,
        "preimage_sha256": sorted(
            normalized_preimage, key=lambda item: item["artifact_id"]
        ),
        "retain_hash_only_proof": retain_hash_only_proof,
    }


def _validate_qualification_launch_grammar(
    *,
    target: Mapping[str, Any],
    plane: str,
    materialize: Sequence[Mapping[str, Any]],
    launch_delta: Mapping[str, Any],
) -> None:
    """Keep v1 activation authority to exact, closed native tuples."""
    harness = target["harness"]
    artifact_ids = [entry["artifact_id"] for entry in materialize]
    argv = launch_delta["argv"]
    env = launch_delta["env"]
    cwd_ref = launch_delta["cwd_ref"]

    if (harness, plane) == ("claude", "per_run_additive"):
        if (
            len(materialize) != 1
            or materialize[0]["root_ref"] != "ephemeral_root"
            or materialize[0]["content_ref"] != "effective_contract"
            or materialize[0]["write_mode"] != "create_only"
            or cwd_ref != "workspace_root"
            or env
            or argv
            != [
                {"literal": "--append-system-prompt-file"},
                {"path_ref": artifact_ids[0]},
            ]
        ):
            raise ValidationError(
                "Claude per-run qualification descriptor has an invalid closed launch grammar"
            )
        return

    if (harness, plane) in {
        ("codex", "workspace_addendum"),
        ("claude", "workspace_addendum"),
    }:
        expected = all(
            entry["root_ref"] == "workspace_root"
            and entry["content_ref"] == "effective_contract"
            and entry["write_mode"] == "create_only"
            for entry in materialize
        )
        if not expected or cwd_ref != "workspace_root" or env or argv:
            raise ValidationError(
                "workspace qualification descriptor has an invalid closed launch grammar"
            )
        return

    if (harness, plane) in {
        ("cursor", "workspace_addendum"),
        ("grok", "workspace_addendum"),
    }:
        flag = "--workspace" if harness == "cursor" else "--cwd"
        expected = all(
            entry["root_ref"] == "workspace_root"
            and entry["content_ref"] == "effective_contract"
            and entry["write_mode"] == "create_only"
            for entry in materialize
        )
        if (
            not expected
            or cwd_ref != "workspace_root"
            or env
            or argv != [{"literal": flag}, {"root_ref": "workspace_root"}]
        ):
            raise ValidationError(
                "%s workspace qualification descriptor has an invalid closed launch grammar"
                % harness
            )
        return

    if (harness, plane) == ("agy", "workspace_addendum"):
        expected = all(
            entry["root_ref"] == "workspace_root"
            and entry["content_ref"] == "effective_contract"
            and entry["write_mode"] == "create_only"
            for entry in materialize
        )
        if (
            not expected
            or cwd_ref != "workspace_root"
            or env
            or argv
            != [
                {"literal": "--agent"},
                {"name_ref": "puppet_agent_name"},
            ]
        ):
            raise ValidationError(
                "AGY workspace qualification descriptor has an invalid closed launch grammar"
            )
        return

    raise ValidationError(
        "instruction-plane tuple is not enabled for qualification in descriptor v1"
    )


def descriptor_fingerprint(descriptor: Mapping[str, Any]) -> str:
    normalized = validate_instruction_plane_descriptor(descriptor)
    return sha256_bytes(canonical_json_bytes(normalized))


def validate_instruction_plane_descriptor(raw: Mapping[str, Any]) -> Dict[str, Any]:
    """Validate and normalize one immutable instruction-plane descriptor."""
    if not isinstance(raw, Mapping):
        raise ValidationError("instruction-plane descriptor must be an object")
    normalized: Dict[str, Any] = dict(raw)

    validate_bounded_json(
        normalized,
        max_depth=8,
        max_items=128,
        max_string=2048,
        reject_sensitive_fields=True,
    )

    if set(normalized) != _FIELD_KEYS:
        raise ValidationError("instruction-plane descriptor fields are invalid")

    schema = normalized.get("schema")
    if _validate_text(schema, label="schema", max_length=64) != _SCHEMA_NAME:
        raise ValidationError("unsupported instruction-plane schema")

    descriptor_id = validate_identifier(
        normalized.get("descriptor_id"),
        "descriptor_id",
    )
    plane = _validate_text(normalized.get("plane"), label="plane", max_length=32)
    if plane not in _SUPPORTED_PLAN_TYPES:
        raise ValidationError("unsupported plane")

    target = _validate_target(normalized.get("target"))
    status = _validate_status(normalized.get("status"))
    if status["activation"] == "qualified":
        raise ValidationError(
            "qualified status requires a separate controller evidence binding"
        )
    allow_empty_activation_artifacts = (
        status["surface"] in {"unsupported", "hypothesis"}
        and status["activation"] == "disabled"
    )
    materialize = _validate_materialize(
        normalized.get("materialize"),
        allow_empty=allow_empty_activation_artifacts,
    )
    materialize_keys = [entry["artifact_id"] for entry in materialize]
    launch_delta = _validate_launch_delta(
        normalized.get("launch_delta"),
        materialize_keys=materialize_keys,
    )
    rollback = _validate_rollback(
        normalized.get("rollback"),
        materialize=materialize,
        materialize_keys=materialize_keys,
        allow_empty=allow_empty_activation_artifacts,
    )
    assertions = _validate_ids(normalized.get("assertions"), label="assertions")
    blockers = _validate_ids(normalized.get("blockers"), label="blockers")

    if status["activation"] == "qualification_only":
        _validate_qualification_launch_grammar(
            target=target,
            plane=plane,
            materialize=materialize,
            launch_delta=launch_delta,
        )

    if status["surface"] == "factual" and status["activation"] != "disabled":
        if not materialize_keys:
            raise ValidationError(
                "factual activatable descriptors must materialize artifacts"
            )
    if (
        status["surface"] in {"unsupported", "hypothesis"}
        and status["activation"] == "disabled"
    ):
        if not blockers:
            raise ValidationError(
                "unsupported or hypothesis disabled descriptors require blockers"
            )
        if materialize_keys:
            raise ValidationError(
                "unsupported or hypothesis disabled descriptors cannot include materialize artifacts"
            )
        if (
            launch_delta["cwd_ref"] is not None
            or launch_delta["env"]
            or launch_delta["argv"]
        ):
            raise ValidationError(
                "unsupported or hypothesis disabled descriptors cannot include activation deltas"
            )
        if rollback["owned_artifacts"] or rollback["preimage_sha256"]:
            raise ValidationError(
                "unsupported or hypothesis disabled descriptors cannot include rollback data"
            )
    return {
        "schema": _SCHEMA_NAME,
        "descriptor_id": descriptor_id,
        "target": target,
        "plane": plane,
        "status": status,
        "materialize": materialize,
        "launch_delta": launch_delta,
        "rollback": rollback,
        "assertions": assertions,
        "blockers": blockers,
    }


def parse_instruction_plane_descriptor(raw: str | Mapping[str, Any]) -> Dict[str, Any]:
    """Parse JSON descriptor text or validate a descriptor mapping."""
    if isinstance(raw, str):
        try:
            encoded = raw.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise ValidationError(
                "descriptor text must contain valid printable Unicode"
            ) from exc
        if len(encoded) > 131072:
            raise ValidationError("descriptor text exceeds the size limit")
        try:
            parsed = _parse_json_no_duplicates(raw)
        except ValidationError:
            raise
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValidationError("descriptor text must be valid JSON") from exc
        if not isinstance(parsed, Mapping):
            raise ValidationError("descriptor text must be an object")
        return validate_instruction_plane_descriptor(parsed)
    return validate_instruction_plane_descriptor(raw)


__all__ = [
    "descriptor_fingerprint",
    "parse_instruction_plane_descriptor",
    "validate_instruction_plane_descriptor",
]
