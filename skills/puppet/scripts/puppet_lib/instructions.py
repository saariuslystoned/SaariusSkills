"""Deterministic, in-memory instruction wrapper compiler."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple, Union

from .contracts import TARGETS
from .errors import ValidationError
from .safety import (
    SECRET_TEXT_PATTERNS,
    canonical_json_bytes,
    sha256_bytes,
    validate_bounded_json,
    validate_sha256,
)

DEFAULT_TEMPLATE_ROOT = (
    Path(__file__).resolve().parents[2] / "templates" / "instructions"
)
_CATALOG_FILENAME = "catalog.json"
_COMPILER_ID = "puppet-instruction-compiler-core"
_MAX_TEMPLATE_BYTES = 65536
_MAX_RENDERED_BYTES = 65536
_MAX_TEXT_BYTES = 32768
_MAX_RUNTIME_LAYER_SIZE = 8192
_POLICY_NONE_VALUE = "unavailable"
_POLICY_SCHEMA_VERSION = 1
_MANIFEST_KIND = "instruction_wrapper"
_INSTRUCTION_PLANE = "initial_message_wrapper"
_QUALIFICATION_STATE = "baseline_unqualified"
_SESSION_PROFILE = "regular"
_ACTIVATION_SCOPE = "regular_only"
_BASE_MODEL_OBSERVATION: Dict[str, str] = {
    "selection": "current_default",
    "resolved_identity": "unavailable",
    "effort": "unavailable",
}
_BASE_DELIVERY_TRANSPORT: Dict[str, Any] = {
    "kind": "tmux_load_buffer_stdin",
    "body_in_argv": False,
    "materialization": "memory_only",
    "native_config_writes": [],
}
_BASE_CLEANUP: Dict[str, str] = {"kind": "none"}


def _expected_layer_specs(target: str, include_addendum: bool) -> List[Tuple[str, str]]:
    base: List[Tuple[str, str]] = [
        ("universal", "universal"),
        (f"harness/{target}", "harness"),
        ("model/default-unresolved", "model"),
        ("lifecycle/regular", "lifecycle"),
        ("runtime_contract", "runtime"),
        ("task_packet", "task"),
    ]
    if include_addendum:
        base.append(("user_addendum", "addendum"))
    return base


def _compute_effective_contract_fingerprint(
    manifest: Mapping[str, Any],
) -> str:
    payload = canonical_json_bytes(
        {
            key: value
            for key, value in manifest.items()
            if key != "effective_contract_fingerprint"
        }
    )
    return sha256_bytes(payload)


@dataclass(frozen=True)
class CompiledInstruction:
    """Deterministic compiler output.

    `rendered` is UTF-8 bytes and `manifest` is JSON-serializable.
    """

    rendered: bytes
    manifest: Dict[str, Any]


def _coerce_template_root(template_root: Optional[Union[str, Path]]) -> Path:
    root = (
        Path.cwd() / template_root
        if template_root is not None
        else DEFAULT_TEMPLATE_ROOT
    )
    root = root if root.is_absolute() else root.resolve()
    root = root.absolute()
    if not root.is_dir():
        raise ValidationError("template root must be an existing directory")
    if root.is_symlink():
        raise ValidationError("template root must not be a symlink")
    return root


def _validate_text(
    value: str,
    *,
    label: str,
    max_bytes: int,
) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError("%s must be non-empty text" % label)
    normalized = value.replace("\r\n", "\n").replace("\r", "\n")
    if "\x00" in normalized:
        raise ValidationError("%s must not contain NUL bytes" % label)
    if normalized.startswith("\ufeff"):
        raise ValidationError("%s must not include BOM" % label)
    if any(pattern.search(normalized) for pattern in SECRET_TEXT_PATTERNS):
        raise ValidationError("%s contains secret-shaped content" % label)
    if len(normalized.encode("utf-8")) > max_bytes:
        raise ValidationError("%s exceeds the allowed size" % label)
    return normalized


def _normalize_template_path(value: str, *, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValidationError("%s path must be text" % label)
    if "/" in value and value.startswith("/"):
        raise ValidationError("%s path must be relative" % label)
    if "\\" in value:
        raise ValidationError("%s path must be slash-style relative" % label)
    parts = tuple(value.split("/"))
    if not parts or any(not part or part in {".", ".."} for part in parts):
        raise ValidationError("%s path contains escaping or empty path parts" % label)
    return value


def _validate_template_file(
    template_root: Path,
    relative_path: str,
    *,
    label: str,
) -> Path:
    normalized = _normalize_template_path(relative_path, label=label)
    path = template_root / normalized
    current = template_root
    for part in normalized.split("/"):
        current = current / part
        if current.exists() and current.is_symlink():
            raise ValidationError("missing or unsafe %s template" % label)
    root = template_root.resolve()
    if not path.exists() or not path.is_file() or path.is_symlink():
        raise ValidationError("missing or unsafe %s template" % label)
    resolved = path.resolve()
    if not resolved.exists() or not resolved.is_file():
        raise ValidationError("missing or unsafe %s template" % label)
    path = resolved
    if path.is_symlink():
        raise ValidationError("missing or unsafe %s template" % label)
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValidationError("template path escapes template root") from exc
    return path


def _read_template_text(path: Path, *, label: str) -> str:
    if path.stat().st_size > _MAX_TEMPLATE_BYTES:
        raise ValidationError("%s template is oversized" % label)
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ValidationError("%s template cannot be read" % label) from exc
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValidationError("%s template is not UTF-8" % label) from exc
    return _validate_text(text, label=label, max_bytes=_MAX_TEMPLATE_BYTES)


def _read_catalog(path: Path) -> Dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise ValidationError("catalog must be a regular file")
    if path.stat().st_size > _MAX_TEMPLATE_BYTES:
        raise ValidationError("catalog is oversized")
    try:
        raw = path.read_bytes().decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValidationError("catalog is not UTF-8") from exc
    try:
        raw_data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValidationError("catalog is malformed JSON") from exc
    return raw_data


def _validate_catalog(raw: Dict[str, Any], *, catalog_root: Path) -> Dict[str, str]:
    if not isinstance(raw, dict):
        raise ValidationError("catalog must be an object")
    if raw.get("schema_version") != 1:
        raise ValidationError("catalog schema version is unsupported")
    shipped = raw.get("shipped_layers")
    if not isinstance(shipped, dict):
        raise ValidationError("catalog missing shipped_layers")
    expected_layers = {"universal", "harnesses", "model", "lifecycle"}
    if set(shipped.keys()) != expected_layers:
        raise ValidationError("catalog shipped layers are invalid")

    universal = shipped.get("universal")
    model = shipped.get("model")
    lifecycle = shipped.get("lifecycle")
    harnesses = shipped.get("harnesses")
    if not isinstance(universal, dict) or set(universal.keys()) != {"path"}:
        raise ValidationError("universal layer must declare one path")
    if not isinstance(model, dict) or set(model.keys()) != {"path"}:
        raise ValidationError("model layer must declare one path")
    if not isinstance(lifecycle, dict) or set(lifecycle.keys()) != {"regular"}:
        raise ValidationError("lifecycle layer must declare regular")
    if not isinstance(harnesses, dict) or set(harnesses.keys()) != set(TARGETS):
        raise ValidationError("harness layer declarations are invalid")
    if len(set(harnesses.values())) != len(harnesses):
        raise ValidationError("harness layer paths must be unique")

    paths = {
        "universal": _validate_template_file(
            catalog_root, str(universal["path"]), label="universal"
        ).as_posix(),
        "model": _validate_template_file(
            catalog_root, str(model["path"]), label="model"
        ).as_posix(),
        "lifecycle_regular": _validate_template_file(
            catalog_root, str(lifecycle["regular"]), label="lifecycle regular"
        ).as_posix(),
    }
    for target, relative in harnesses.items():
        paths["harness_%s" % target] = _validate_template_file(
            catalog_root, str(relative), label="harness %s" % target
        ).as_posix()
    return paths


def _validate_identity(value: Mapping[str, Any], *, label: str) -> Dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValidationError("%s must be an object" % label)
    normalized = dict(value)
    if not normalized:
        raise ValidationError("%s must not be empty" % label)
    validate_bounded_json(
        normalized,
        max_depth=4,
        max_items=16,
        max_string=512,
        reject_sensitive_fields=True,
    )
    return normalized


def _policy_layers(
    template_root: Path,
    target: str,
) -> Tuple[List[Dict[str, str]], List[Tuple[str, str, str]]]:
    catalog_raw = _read_catalog(template_root / _CATALOG_FILENAME)
    catalog_paths = _validate_catalog(catalog_raw, catalog_root=template_root)

    shipped = [
        ("universal", "universal", catalog_paths["universal"]),
        (f"harness/{target}", "harness", catalog_paths["harness_%s" % target]),
        ("model/default-unresolved", "model", catalog_paths["model"]),
        ("lifecycle/regular", "lifecycle", catalog_paths["lifecycle_regular"]),
    ]
    layer_hashes: List[Dict[str, str]] = []
    layer_texts: List[Tuple[str, str, str]] = []

    for name, source, path in shipped:
        payload = _read_template_text(
            Path(path), label=source if source != "universal" else source
        )
        body = payload.rstrip("\n")
        digest = sha256_bytes(body.encode("utf-8"))
        layer_hashes.append({"name": name, "sha256": digest})
        layer_texts.append((name, source, payload))
    return layer_hashes, layer_texts


def _manifest_required_keys() -> List[str]:
    return [
        "schema_version",
        "kind",
        "compiler_id",
        "target",
        "session_profile",
        "instruction_plane",
        "qualification_state",
        "contract_identity",
        "workspace_identity",
        "run_identity",
        "orchestration_contract",
        "instruction_policy_fingerprint",
        "effective_contract_fingerprint",
        "rendered_sha256",
        "byte_count",
        "ordered_layers",
        "runtime_binding",
        "model_observation",
        "delivery_transport",
        "session_activation",
        "cleanup",
    ]


def _policy_payload(
    *,
    target: str,
    template_root: Path,
) -> Tuple[str, List[Dict[str, str]]]:
    layer_hashes, _ = _policy_layers(template_root, target)
    payload = canonical_json_bytes(
        {
            "compiler": _COMPILER_ID,
            "catalog_sha256": sha256_bytes(
                (template_root / _CATALOG_FILENAME).read_bytes()
            ),
            "target": target,
            "session_profile": _SESSION_PROFILE,
            "initial_wrapper_plane": _INSTRUCTION_PLANE,
            "shipped_layer_hashes": layer_hashes,
        }
    )
    return sha256_bytes(payload), layer_hashes


def instruction_policy_fingerprint(
    *,
    target: str,
    template_root: Optional[Union[str, Path]] = None,
) -> str:
    """Return deterministic fingerprint for the shipped policy-only wrapper layers."""
    if target not in TARGETS:
        raise ValidationError("unsupported target")
    root = _coerce_template_root(template_root)
    digest, _ = _policy_payload(target=target, template_root=root)
    return digest


def _validate_ordered_layers(
    layers: Iterable[Mapping[str, Any]], *, target: str
) -> List[Dict[str, Any]]:
    if not isinstance(layers, list):
        raise ValidationError("ordered_layers must be a list")
    if any(not isinstance(layer, Mapping) for layer in layers):
        raise ValidationError("ordered_layers entries must be objects")
    normalized: List[Dict[str, Any]] = [dict(layer) for layer in layers]
    if not normalized:
        raise ValidationError("ordered_layers must be non-empty")
    if len(normalized) not in (6, 7):
        raise ValidationError("ordered_layers length is invalid")
    for layer in normalized:
        if set(layer.keys()) != {"name", "source", "sha256", "bytes"}:
            raise ValidationError("ordered layer shape is unsupported")
        if not layer["name"] or not layer["source"]:
            raise ValidationError("ordered layer name and source are required")
        if (
            isinstance(layer["bytes"], bool)
            or not isinstance(layer["bytes"], int)
            or layer["bytes"] < 0
        ):
            raise ValidationError("ordered layer byte count is invalid")
        if not isinstance(layer["sha256"], str):
            raise ValidationError("ordered layer fingerprint is required")
        validate_sha256(layer["sha256"], "ordered layer sha256")

    include_addendum = len(normalized) == 7
    expected = _expected_layer_specs(target=target, include_addendum=include_addendum)
    expected_names = [name for name, _ in expected]
    expected_sources = [source for _, source in expected]
    names: List[str] = []
    sources: List[str] = []
    seen_names = set()
    for layer in normalized:
        name = str(layer["name"])
        source = str(layer["source"])
        names.append(name)
        sources.append(source)
        if name in seen_names:
            raise ValidationError("ordered_layers contain duplicates")
        seen_names.add(name)
    if names != expected_names or sources != expected_sources:
        raise ValidationError("ordered_layers order is invalid")
    return normalized


def _runtime_layer_payload(manifest: Mapping[str, Any]) -> bytes:
    return canonical_json_bytes(
        {
            "target": manifest["target"],
            "session_profile": manifest["session_profile"],
            "instruction_plane": manifest["instruction_plane"],
            "qualification_state": manifest["qualification_state"],
            "runtime_binding": manifest["runtime_binding"],
            "model_observation": manifest["model_observation"],
            "contract_identity": manifest["contract_identity"],
            "workspace_identity": manifest["workspace_identity"],
            "run_identity": manifest["run_identity"],
            "runtime_contract_layer": manifest["orchestration_contract"],
        }
    )


def _expected_rendered_byte_count(layers: List[Mapping[str, Any]]) -> int:
    section_bytes = sum(
        len(("## %s\n" % layer["name"]).encode("utf-8")) + int(layer["bytes"])
        for layer in layers
    )
    return section_bytes + (2 * (len(layers) - 1)) + 1


def validate_instruction_manifest(
    manifest: Mapping[str, Any],
    *,
    target: str,
    template_root: Optional[Union[str, Path]] = None,
) -> Dict[str, Any]:
    """Validate a compiler manifest without rederiving non-payload task material."""
    if target not in TARGETS:
        raise ValidationError("unsupported target")
    if not isinstance(manifest, Mapping):
        raise ValidationError("manifest must be an object")
    normalized = dict(manifest)

    validate_bounded_json(
        normalized,
        max_depth=6,
        max_items=64,
        max_string=1024,
        reject_sensitive_fields=True,
    )

    required = _manifest_required_keys()
    if set(normalized.keys()) != set(required):
        raise ValidationError("manifest fields do not match the required schema")
    if normalized["schema_version"] != _POLICY_SCHEMA_VERSION:
        raise ValidationError("unsupported schema version")
    if normalized["kind"] != _MANIFEST_KIND:
        raise ValidationError("unsupported manifest kind")
    if normalized["compiler_id"] != _COMPILER_ID:
        raise ValidationError("unsupported compiler id")
    if normalized["target"] not in TARGETS:
        raise ValidationError("unsupported target")
    if normalized["target"] != target:
        raise ValidationError("manifest target does not match requested target")
    if normalized["session_profile"] != _SESSION_PROFILE:
        raise ValidationError("unsupported session profile")
    if normalized["instruction_plane"] != _INSTRUCTION_PLANE:
        raise ValidationError("unsupported instruction plane")
    if normalized["qualification_state"] != _QUALIFICATION_STATE:
        raise ValidationError("unexpected qualification state")

    try:
        normalized["contract_identity"] = _validate_identity(
            normalized["contract_identity"], label="contract identity"
        )
        normalized["workspace_identity"] = _validate_identity(
            normalized["workspace_identity"], label="workspace identity"
        )
        normalized["run_identity"] = _validate_identity(
            normalized["run_identity"], label="run identity"
        )
        orchestration_contract = normalized["orchestration_contract"]
        normalized["orchestration_contract"] = (
            _validate_identity(orchestration_contract, label="orchestration contract")
            if orchestration_contract is not None
            else None
        )
    except ValidationError as exc:
        raise ValidationError("manifest identity is invalid") from exc

    validate_sha256(
        normalized["instruction_policy_fingerprint"], "instruction policy fingerprint"
    )
    validate_sha256(
        normalized["effective_contract_fingerprint"], "effective contract fingerprint"
    )
    validate_sha256(normalized["rendered_sha256"], "rendered sha256")
    if (
        isinstance(normalized["byte_count"], bool)
        or not isinstance(normalized["byte_count"], int)
        or normalized["byte_count"] <= 0
    ):
        raise ValidationError("manifest byte_count is invalid")
    if normalized["delivery_transport"] != _BASE_DELIVERY_TRANSPORT:
        raise ValidationError("delivery transport is invalid")
    if (
        not isinstance(normalized["session_activation"], dict)
        or normalized["session_activation"].get("scope") != _ACTIVATION_SCOPE
        or set(normalized["session_activation"].keys()) != {"scope"}
    ):
        raise ValidationError("session activation is unexpected")
    if (
        not isinstance(normalized["cleanup"], dict)
        or normalized["cleanup"] != _BASE_CLEANUP
        or set(normalized["cleanup"].keys()) != set(_BASE_CLEANUP)
    ):
        raise ValidationError("cleanup is invalid")
    if (
        normalized["delivery_transport"]["materialization"]
        != _BASE_DELIVERY_TRANSPORT["materialization"]
    ):
        raise ValidationError("delivery transport is unexpected")
    binding = normalized.get("runtime_binding")
    if (
        not isinstance(binding, dict)
        or set(binding.keys()) != {"model", "effort"}
        or binding["model"] not in {_POLICY_NONE_VALUE, "default"}
        or binding["effort"] not in {_POLICY_NONE_VALUE, "default"}
    ):
        raise ValidationError("runtime_binding is invalid")
    model_observation = normalized.get("model_observation")
    if (
        not isinstance(model_observation, dict)
        or model_observation != _BASE_MODEL_OBSERVATION
        or set(model_observation.keys()) != set(_BASE_MODEL_OBSERVATION)
    ):
        raise ValidationError("model_observation is invalid")

    normalized["ordered_layers"] = _validate_ordered_layers(
        normalized["ordered_layers"], target=target
    )
    root = _coerce_template_root(template_root)
    expected, _ = _policy_payload(target=target, template_root=root)
    if normalized["instruction_policy_fingerprint"] != expected:
        raise ValidationError("instruction policy fingerprint mismatch")
    _, shipped_texts = _policy_layers(root, target)
    expected_shipped = []
    for name, source, payload in shipped_texts:
        body = payload.rstrip("\n").encode("utf-8")
        expected_shipped.append(
            {
                "name": name,
                "source": source,
                "sha256": sha256_bytes(body),
                "bytes": len(body),
            }
        )
    if normalized["ordered_layers"][:4] != expected_shipped:
        raise ValidationError("shipped ordered layer metadata mismatch")

    runtime_payload = _runtime_layer_payload(normalized)
    runtime_layer = normalized["ordered_layers"][4]
    if runtime_layer["sha256"] != sha256_bytes(runtime_payload) or runtime_layer[
        "bytes"
    ] != len(runtime_payload):
        raise ValidationError("runtime contract layer metadata mismatch")

    expected_byte_count = _expected_rendered_byte_count(normalized["ordered_layers"])
    if normalized["byte_count"] != expected_byte_count:
        raise ValidationError("manifest byte_count does not match ordered layers")
    expected_effective = _compute_effective_contract_fingerprint(normalized)
    if normalized["effective_contract_fingerprint"] != expected_effective:
        raise ValidationError("effective contract fingerprint mismatch")
    if normalized["byte_count"] > _MAX_RENDERED_BYTES:
        raise ValidationError("manifest byte_count is invalid")

    return normalized


def _render_layers(
    layers: List[Tuple[str, str, str]],
) -> Tuple[bytes, List[Dict[str, Any]], List[Dict[str, str]]]:
    rendered_sections = []
    metadata: List[Dict[str, Any]] = []
    policy_layers: List[Dict[str, str]] = []

    for name, source, payload in layers:
        body = payload.rstrip("\n")
        rendered_sections.append(f"## {name}\n{body}")
        data = body.encode("utf-8")
        layer = {
            "name": name,
            "source": source,
            "sha256": sha256_bytes(data),
            "bytes": len(data),
        }
        metadata.append(layer)
        if source in {"universal", "model", "lifecycle", "harness"}:
            policy_layers.append({"name": name, "sha256": layer["sha256"]})
    rendered = ("\n\n".join(rendered_sections) + "\n").encode("utf-8")
    return rendered, metadata, policy_layers


def compile_instruction_wrapper(
    *,
    target: str,
    task: str,
    contract_identity: Mapping[str, Any],
    workspace_identity: Mapping[str, Any],
    run_identity: Mapping[str, Any],
    template_root: Optional[Union[str, Path]] = None,
    session_profile: str = "regular",
    model_binding: str = _POLICY_NONE_VALUE,
    effort_binding: str = _POLICY_NONE_VALUE,
    task_addendum: Optional[str] = None,
    runtime_contract_layer: Optional[Mapping[str, Any]] = None,
) -> CompiledInstruction:
    """Compile in-memory instruction wrapper layers with deterministic manifests.

    This function never writes files; all writes are the caller's responsibility.
    """

    root = _coerce_template_root(template_root)
    if target not in TARGETS:
        raise ValidationError("unsupported target")
    if session_profile != "regular":
        raise ValidationError("only regular session profile is permitted")
    if model_binding not in {_POLICY_NONE_VALUE, "default"}:
        raise ValidationError("model binding must be default or unavailable")
    if effort_binding not in {_POLICY_NONE_VALUE, "default"}:
        raise ValidationError("effort binding must be default or unavailable")

    normalized_task = _validate_text(
        task, label="task packet", max_bytes=_MAX_TEXT_BYTES
    )
    normalized_addendum = (
        _validate_text(task_addendum, label="task addendum", max_bytes=_MAX_TEXT_BYTES)
        if task_addendum is not None
        else None
    )
    normalized_contract = _validate_identity(
        contract_identity, label="contract identity"
    )
    normalized_workspace = _validate_identity(
        workspace_identity, label="workspace identity"
    )
    normalized_run = _validate_identity(run_identity, label="run identity")
    normalized_runtime_contract = (
        _validate_identity(runtime_contract_layer, label="runtime contract layer")
        if runtime_contract_layer is not None
        else None
    )

    runtime_binding = {"model": model_binding, "effort": effort_binding}
    runtime_manifest_fields = {
        "target": target,
        "session_profile": session_profile,
        "instruction_plane": _INSTRUCTION_PLANE,
        "qualification_state": _QUALIFICATION_STATE,
        "runtime_binding": runtime_binding,
        "model_observation": _BASE_MODEL_OBSERVATION,
        "contract_identity": normalized_contract,
        "workspace_identity": normalized_workspace,
        "run_identity": normalized_run,
        "orchestration_contract": normalized_runtime_contract,
    }
    task_layer = _runtime_layer_payload(runtime_manifest_fields).decode("utf-8")

    if len(task_layer.encode("utf-8")) > _MAX_RUNTIME_LAYER_SIZE:
        raise ValidationError("runtime contract layer is oversized")

    _, layer_templates = _policy_layers(root, target)
    layers = layer_templates + [
        ("runtime_contract", "runtime", task_layer),
        ("task_packet", "task", normalized_task),
    ]
    if normalized_addendum is not None:
        layers.append(("user_addendum", "addendum", normalized_addendum))

    rendered, ordered_layers, _ = _render_layers(layers)
    if len(rendered) > _MAX_RENDERED_BYTES:
        raise ValidationError("rendered payload exceeds the bounded size")

    rendered_sha = sha256_bytes(rendered)

    instruction_policy_fingerprint, _ = _policy_payload(
        target=target,
        template_root=root,
    )

    manifest = {
        "schema_version": _POLICY_SCHEMA_VERSION,
        "kind": _MANIFEST_KIND,
        "compiler_id": _COMPILER_ID,
        "target": target,
        "session_profile": session_profile,
        "instruction_plane": _INSTRUCTION_PLANE,
        "qualification_state": _QUALIFICATION_STATE,
        "contract_identity": normalized_contract,
        "workspace_identity": normalized_workspace,
        "run_identity": normalized_run,
        "orchestration_contract": normalized_runtime_contract,
        "instruction_policy_fingerprint": instruction_policy_fingerprint,
        "effective_contract_fingerprint": "0" * 64,
        "rendered_sha256": rendered_sha,
        "byte_count": len(rendered),
        "ordered_layers": ordered_layers,
        "runtime_binding": runtime_binding,
        "model_observation": dict(_BASE_MODEL_OBSERVATION),
        "delivery_transport": dict(_BASE_DELIVERY_TRANSPORT),
        "session_activation": {"scope": _ACTIVATION_SCOPE},
        "cleanup": dict(_BASE_CLEANUP),
    }
    manifest["effective_contract_fingerprint"] = (
        _compute_effective_contract_fingerprint(manifest)
    )

    if any(key in manifest for key in ("task", "rendered", "addendum")):
        raise ValidationError("manifest contains forbidden raw fields")

    validate_instruction_manifest(manifest, target=target, template_root=root)

    return CompiledInstruction(rendered=rendered, manifest=manifest)


__all__ = [
    "CompiledInstruction",
    "instruction_policy_fingerprint",
    "compile_instruction_wrapper",
    "validate_instruction_manifest",
]
