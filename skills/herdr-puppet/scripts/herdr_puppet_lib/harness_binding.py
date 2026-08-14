from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .claude_hooks import (
    CLAUDE_BASE_FLAGS,
    claude_launch_flags,
    validate_lifecycle_observation,
)
from .errors import HerdrPuppetError


CANONICAL_HARNESSES = ("agy", "codex", "claude", "cursor", "grok")
AGY_REQUIRED_MODEL = "gemini-3.7-flash-high"
HARNESS_LAUNCH_SPECS = {
    "agy": {
        "command": "agy",
        "flags": [
            "--model",
            AGY_REQUIRED_MODEL,
            "--dangerously-skip-permissions",
            "--sandbox=false",
            "--new-project",
            "--log-file",
            "/dev/null",
        ],
    },
    "codex": {
        "command": "codex",
        "flags": ["--dangerously-bypass-approvals-and-sandbox"],
    },
    "claude": {
        "command": "claude",
        "flags": CLAUDE_BASE_FLAGS,
    },
    "cursor": {
        "command": "cursor-agent",
        "flags": ["--yolo", "--sandbox", "disabled"],
    },
    "grok": {
        "command": "grok",
        "flags": ["--always-approve", "--sandbox", "off"],
    },
}
HISTORICAL_HARNESS_LAUNCH_FLAGS = {
    "agy": [
        "--dangerously-skip-permissions",
        "--sandbox=false",
        "--new-project",
        "--log-file",
        "/dev/null",
    ],
    "codex": ["--dangerously-bypass-approvals-and-sandbox"],
    "claude": ["--dangerously-skip-permissions"],
    "cursor": ["--yolo", "--sandbox", "disabled"],
    "grok": ["--always-approve", "--sandbox", "off"],
}
BINDING_SCHEMA = "herdr-puppet.harness-binding.v3"
HISTORICAL_BINDING_SCHEMAS = {
    "herdr-puppet.harness-binding.v1",
    "herdr-puppet.harness-binding.v2",
}
CENSUS_SCHEMA = "herdr-puppet.remote-harness-census.v3"
INSTRUCTION_MANIFEST_SCHEMA = "herdr-puppet.instruction-wrapper.v1"
INSTRUCTION_PLANE = "initial_message_wrapper"
HISTORICAL_INSTRUCTION_MANIFEST_SCHEMA = (
    "herdr-puppet.instruction-wrapper.v1"
)
HISTORICAL_INSTRUCTION_PLANE = "initial_message_wrapper"
MAX_TEXT_BYTES = 32 * 1024
MAX_TEMPLATE_BYTES = 64 * 1024
ISOLATED_LAUNCH_PATH = (
    "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
)

_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9._@:+/-]{1,512}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_RFC3339 = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
    r"(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)
_SECRET_SHAPES = (
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\b(?:ghp|github_pat|sk)-[A-Za-z0-9_-]{16,}\b"),
)


def _model_layer(harness: str) -> str:
    return (
        "model/agy-gemini-3.7-flash-high"
        if harness == "agy"
        else "model/default-unresolved"
    )


def _now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            block = stream.read(1024 * 1024)
            if not block:
                return digest.hexdigest()
            digest.update(block)


def _require_sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise HerdrPuppetError(
            "invalid_harness_binding",
            f"{label} must be a lowercase SHA-256 digest.",
        )
    return value


def _require_text(value: Any, label: str, *, absolute: bool = False) -> str:
    if (
        not isinstance(value, str)
        or not value
        or "\x00" in value
        or "\n" in value
        or "\r" in value
    ):
        raise HerdrPuppetError(
            "invalid_harness_binding",
            f"{label} must be bounded single-line text.",
        )
    if absolute and not Path(value).is_absolute():
        raise HerdrPuppetError(
            "invalid_harness_binding",
            f"{label} must be an absolute path.",
        )
    return value


def _require_safe_value(value: Any, label: str) -> str:
    text = _require_text(value, label)
    if _SAFE_IDENTIFIER.fullmatch(text) is None:
        raise HerdrPuppetError(
            "invalid_harness_binding",
            f"{label} contains unsupported characters.",
        )
    return text


def _require_rfc3339(value: Any, label: str) -> str:
    if not isinstance(value, str) or _RFC3339.fullmatch(value) is None:
        raise HerdrPuppetError(
            "invalid_harness_binding",
            f"{label} must be an RFC 3339 timestamp.",
        )
    try:
        parsed = datetime.fromisoformat(
            value[:-1] + "+00:00" if value.endswith("Z") else value
        )
    except ValueError as exc:
        raise HerdrPuppetError(
            "invalid_harness_binding",
            f"{label} must be an RFC 3339 timestamp.",
        ) from exc
    if parsed.tzinfo is None:
        raise HerdrPuppetError(
            "invalid_harness_binding",
            f"{label} must include a timezone.",
        )
    return value


def _require_exact_fields(
    value: Any,
    fields: set[str],
    label: str,
) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        raise HerdrPuppetError(
            "invalid_harness_binding",
            f"{label} must contain exactly the normative fields.",
            details={
                "missing_fields": sorted(
                    fields - set(value) if isinstance(value, dict) else fields
                ),
                "unexpected_fields": sorted(
                    set(value) - fields if isinstance(value, dict) else set()
                ),
            },
        )
    return dict(value)


def _binding_payload(value: Mapping[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if key != "fingerprint"}


def binding_fingerprint(value: Mapping[str, Any]) -> str:
    return _sha256_bytes(_canonical_bytes(_binding_payload(value)))


def remote_census_facts_fingerprint(value: Mapping[str, Any]) -> str:
    """Fingerprint stable census facts while allowing observation time to advance."""
    return _sha256_bytes(
        _canonical_bytes(
            {
                key: item
                for key, item in value.items()
                if key != "recorded_at"
            }
        )
    )


def _skill_root(skill_root: Path | None = None) -> Path:
    root = (
        Path(skill_root)
        if skill_root is not None
        else Path(__file__).resolve(strict=True).parents[2]
    )
    try:
        resolved = root.resolve(strict=True)
    except OSError as exc:
        raise HerdrPuppetError(
            "harness_binding_source_unavailable",
            "The Herdr-Puppet skill root is unavailable.",
        ) from exc
    if not resolved.is_dir():
        raise HerdrPuppetError(
            "harness_binding_source_unavailable",
            "The Herdr-Puppet skill root is not a directory.",
        )
    return resolved


def _source_fingerprint(skill_root: Path, relative_paths: list[str]) -> str:
    rows: list[dict[str, str]] = []
    for relative in sorted(relative_paths):
        path = skill_root / relative
        if not path.is_file() or path.is_symlink():
            raise HerdrPuppetError(
                "harness_binding_source_unavailable",
                "A required binding source is missing or unsafe.",
                details={"relative_path": relative},
            )
        rows.append({"path": relative, "sha256": _sha256_file(path)})
    return _sha256_bytes(_canonical_bytes(rows))


def harness_adapter_fingerprint(skill_root: Path | None = None) -> str:
    root = _skill_root(skill_root)
    templates = [
        path.relative_to(root).as_posix()
        for path in (root / "templates" / "instructions").rglob("*")
        if path.is_file()
    ]
    return _source_fingerprint(
        root,
        [
            "scripts/claude_hook_marker.py",
            "scripts/harness_census.py",
            "scripts/herdr_puppet_lib/claude_hook_marker.py",
            "scripts/herdr_puppet_lib/claude_hooks.py",
            "scripts/herdr_puppet_lib/harness_binding.py",
            *templates,
        ],
    )


def transport_adapter_fingerprint(skill_root: Path | None = None) -> str:
    root = _skill_root(skill_root)
    return _source_fingerprint(
        root,
        [
            "scripts/herdr_puppet_lib/__init__.py",
            "scripts/herdr_puppet_lib/authority.py",
            "scripts/herdr_puppet_lib/cli.py",
            "scripts/herdr_puppet_lib/core.py",
            "scripts/herdr_puppet_lib/herdr_client.py",
            "scripts/herdr_puppet_lib/journal.py",
            "references/destination-catalog.schema.json",
            "references/event.schema.json",
            "references/harness-binding.schema.json",
            "references/harness-binding-v2.schema.json",
            "references/harness-binding-v1.schema.json",
            "references/lease.schema.json",
            "references/lease-v1.schema.json",
            "references/plan.schema.json",
            "references/plan-v1.schema.json",
            "references/remote-harness-census.schema.json",
        ],
    )


def protocol_fingerprint() -> str:
    return _sha256_bytes(
        _canonical_bytes(
            {
                "herdr_version": "0.7.3",
                "protocol": 16,
                "operations": [
                    "pane.run",
                    "pane.send_input",
                    "wait.output",
                    "api.snapshot",
                    "pane.process-info",
                ],
            }
        )
    )


def _template_catalog(skill_root: Path) -> tuple[list[dict[str, str]], str]:
    template_root = skill_root / "templates" / "instructions"
    catalog_path = template_root / "catalog.json"
    try:
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HerdrPuppetError(
            "instruction_catalog_invalid",
            "The instruction template catalog is unavailable or malformed.",
        ) from exc
    expected = {"schema", "universal", "models", "lifecycle", "harnesses"}
    if not isinstance(catalog, dict) or set(catalog) != expected:
        raise HerdrPuppetError(
            "instruction_catalog_invalid",
            "The instruction template catalog shape is invalid.",
        )
    if catalog["schema"] != "herdr-puppet.instruction-catalog.v2":
        raise HerdrPuppetError(
            "instruction_catalog_invalid",
            "The instruction template catalog version is unsupported.",
        )
    harnesses = catalog["harnesses"]
    if not isinstance(harnesses, dict) or set(harnesses) != set(CANONICAL_HARNESSES):
        raise HerdrPuppetError(
            "instruction_catalog_invalid",
            "The instruction catalog harness map is invalid.",
        )
    models = catalog["models"]
    if not isinstance(models, dict) or set(models) != {
        "default_unresolved",
        "agy_gemini_3_7_flash_high",
    }:
        raise HerdrPuppetError(
            "instruction_catalog_invalid",
            "The instruction catalog model map is invalid.",
        )
    paths = [
        ("universal", catalog["universal"]),
        ("model/default-unresolved", models["default_unresolved"]),
        (
            "model/agy-gemini-3.7-flash-high",
            models["agy_gemini_3_7_flash_high"],
        ),
        ("lifecycle/regular", catalog["lifecycle"]),
    ]
    rows: list[dict[str, str]] = []
    for name, relative in paths:
        path = _safe_template_path(template_root, relative)
        rows.append({"name": name, "path": relative, "sha256": _sha256_file(path)})
    for harness in CANONICAL_HARNESSES:
        relative = harnesses[harness]
        path = _safe_template_path(template_root, relative)
        rows.append(
            {
                "name": f"harness/{harness}",
                "path": relative,
                "sha256": _sha256_file(path),
            }
        )
    return rows, _sha256_bytes(_canonical_bytes(rows))


def _safe_template_path(root: Path, relative: Any) -> Path:
    if (
        not isinstance(relative, str)
        or not relative
        or relative.startswith("/")
        or "\\" in relative
        or any(part in {"", ".", ".."} for part in relative.split("/"))
    ):
        raise HerdrPuppetError(
            "instruction_catalog_invalid",
            "An instruction template path is unsafe.",
        )
    path = root / relative
    if not path.is_file() or path.is_symlink():
        raise HerdrPuppetError(
            "instruction_catalog_invalid",
            "An instruction template is missing or unsafe.",
        )
    resolved = path.resolve(strict=True)
    try:
        resolved.relative_to(root.resolve(strict=True))
    except ValueError as exc:
        raise HerdrPuppetError(
            "instruction_catalog_invalid",
            "An instruction template escapes the template root.",
        ) from exc
    if resolved.stat().st_size > MAX_TEMPLATE_BYTES:
        raise HerdrPuppetError(
            "instruction_catalog_invalid",
            "An instruction template exceeds the bounded size.",
        )
    return resolved


def instruction_policy_fingerprint(skill_root: Path | None = None) -> str:
    _, fingerprint = _template_catalog(_skill_root(skill_root))
    return fingerprint


def validate_remote_census(
    value: Any,
    *,
    skill_root: Path | None = None,
) -> dict[str, Any]:
    census = _require_exact_fields(
        value,
        {
            "schema",
            "harness",
            "host",
            "recorded_at",
            "executable",
            "profile",
            "regular_launch",
            "lifecycle_observation",
            "model_observation",
            "source",
            "raw_output_retained",
        },
        "remote harness census",
    )
    if census["schema"] != CENSUS_SCHEMA:
        raise HerdrPuppetError(
            "invalid_remote_census",
            "The remote harness census schema is unsupported.",
        )
    harness = census["harness"]
    if harness not in CANONICAL_HARNESSES:
        raise HerdrPuppetError(
            "invalid_remote_census",
            "The census harness is not canonical.",
        )
    _require_safe_value(census["host"], "census host")
    _require_rfc3339(census["recorded_at"], "census recorded_at")
    executable = _require_exact_fields(
        census["executable"],
        {
            "command",
            "path",
            "version",
            "sha256",
            "version_sha256",
            "help_sha256",
            "fingerprint",
        },
        "census executable",
    )
    _require_safe_value(executable["command"], "census executable command")
    if executable["command"] != HARNESS_LAUNCH_SPECS[harness]["command"]:
        raise HerdrPuppetError(
            "invalid_remote_census",
            "The census executable does not match the canonical harness.",
        )
    _require_text(executable["path"], "census executable path", absolute=True)
    _require_text(executable["version"], "census executable version")
    for field in ("sha256", "version_sha256", "help_sha256", "fingerprint"):
        _require_sha256(executable[field], f"census executable {field}")
    expected_executable_fingerprint = _sha256_bytes(
        _canonical_bytes(
            {
                key: executable[key]
                for key in (
                    "command",
                    "path",
                    "version",
                    "sha256",
                    "version_sha256",
                    "help_sha256",
                )
            }
        )
    )
    if executable["fingerprint"] != expected_executable_fingerprint:
        raise HerdrPuppetError(
            "invalid_remote_census",
            "The remote executable fingerprint does not match its facts.",
        )
    profile = _require_exact_fields(
        census["profile"],
        {
            "route",
            "root",
            "isolation",
            "enrollment_state",
            "status_exit",
            "raw_output_retained",
        },
        "census profile",
    )
    _require_safe_value(profile["route"], "census profile route")
    _require_text(profile["root"], "census profile root", absolute=True)
    if (
        profile["route"] != "dedicated_os_user_profile"
        or profile["isolation"] != "dedicated_remote_user"
    ):
        raise HerdrPuppetError(
            "invalid_remote_census",
            "A qualifying profile must use the dedicated remote-user route.",
        )
    if profile["enrollment_state"] == "enrolled":
        if (
            isinstance(profile["status_exit"], bool)
            or not isinstance(profile["status_exit"], int)
            or profile["status_exit"] != 0
            or profile["raw_output_retained"] is not False
        ):
            raise HerdrPuppetError(
                "invalid_remote_census",
                "The qualifying profile status is not an enrolled body-free result.",
            )
    elif (
        profile["enrollment_state"] == "interactive_pending"
        and harness != "cursor"
    ):
        raise HerdrPuppetError(
            "invalid_remote_census",
            "The qualifying profile status is not controller-observed enrolled.",
            details={"harness": harness},
        )
    elif profile["enrollment_state"] == "interactive_pending":
        if (
            profile["status_exit"] is not None
            or profile["raw_output_retained"] is not False
        ):
            raise HerdrPuppetError(
                "invalid_remote_census",
                "The qualifying profile status is not a provisional body-free result.",
            )
    else:
        raise HerdrPuppetError(
            "profile_not_enrolled",
            "The dedicated remote-user profile is not controller-observed enrolled.",
            details={"harness": harness},
        )
    source = _require_exact_fields(
        census["source"],
        {"worktree"},
        "census source",
    )
    _require_text(source["worktree"], "census source worktree", absolute=True)
    lifecycle = validate_lifecycle_observation(
        census["lifecycle_observation"],
        harness=harness,
        source_worktree=source["worktree"],
        skill_root=_skill_root(skill_root),
    )
    launch = _require_exact_fields(
        census["regular_launch"],
        {
            "argv",
            "environment",
            "inherit_environment",
            "unrestricted",
            "explicit_model_selector",
            "vector_sha256",
        },
        "census regular launch",
    )
    argv = launch["argv"]
    environment = launch["environment"]
    expected_argv = [
        executable["path"],
        *(
            claude_launch_flags(lifecycle)
            if harness == "claude"
            else HARNESS_LAUNCH_SPECS[harness]["flags"]
        ),
    ]
    if (
        not isinstance(argv, list)
        or len(argv) < 2
        or any(not isinstance(item, str) or not item for item in argv)
        or argv != expected_argv
    ):
        raise HerdrPuppetError(
            "invalid_remote_census",
            "The regular launch argv is invalid.",
        )
    expected_environment = {
        "HOME": profile["root"],
        "PATH": ISOLATED_LAUNCH_PATH,
        "LANG": "C",
        "LC_ALL": "C",
        "TERM": "xterm-256color",
    }
    if environment != expected_environment:
        raise HerdrPuppetError(
            "invalid_remote_census",
            "The regular launch environment is not the isolated regular profile.",
        )
    if (
        launch["inherit_environment"] is not False
        or launch["unrestricted"] is not True
        or launch["explicit_model_selector"] is not (harness == "agy")
    ):
        raise HerdrPuppetError(
            "invalid_remote_census",
            "The regular launch model-selection posture is invalid.",
        )
    expected_vector = _sha256_bytes(
        _canonical_bytes(
            {
                "argv": argv,
                "environment": environment,
                "inherit_environment": False,
            }
        )
    )
    if launch["vector_sha256"] != expected_vector:
        raise HerdrPuppetError(
            "invalid_remote_census",
            "The regular launch-vector fingerprint is invalid.",
        )
    model = _require_exact_fields(
        census["model_observation"],
        {"selection", "model", "effort"},
        "census model observation",
    )
    if harness == "agy":
        if model != {
            "selection": "explicit",
            "model": AGY_REQUIRED_MODEL,
            "effort": "high",
        }:
            raise HerdrPuppetError(
                "invalid_remote_census",
                "The AGY census must bind the required explicit model.",
            )
    elif model["selection"] != "current_default":
        raise HerdrPuppetError(
            "invalid_remote_census",
            "The census must observe the current default without selecting a model.",
        )
    for field in ("model", "effort"):
        _require_safe_value(model[field], f"census observed {field}")
    if census["raw_output_retained"] is not False:
        raise HerdrPuppetError(
            "invalid_remote_census",
            "Remote census output bodies must not be retained.",
        )
    return census


def build_harness_binding(
    census_value: Any,
    *,
    repo: str,
    skill_root: Path | None = None,
) -> dict[str, Any]:
    root = _skill_root(skill_root)
    census = validate_remote_census(census_value, skill_root=root)
    _require_text(repo, "source repository")
    template_rows, policy_fingerprint = _template_catalog(root)
    required_layers = [
        "universal",
        f"harness/{census['harness']}",
        _model_layer(census["harness"]),
        "lifecycle/regular",
    ]
    catalog_layer_names = {row["name"] for row in template_rows}
    if any(layer not in catalog_layer_names for layer in required_layers):
        raise HerdrPuppetError(
            "instruction_catalog_invalid",
            "The instruction catalog is missing a required wrapper layer.",
        )
    binding = {
        "schema": BINDING_SCHEMA,
        "harness": census["harness"],
        "remote": {
            "host": census["host"],
            "executable": dict(census["executable"]),
        },
        "profile": dict(census["profile"]),
        "model_observation": dict(census["model_observation"]),
        "regular_launch": dict(census["regular_launch"]),
        "lifecycle_observation": dict(census["lifecycle_observation"]),
        "adapters": {
            "harness_fingerprint": harness_adapter_fingerprint(root),
            "transport_fingerprint": transport_adapter_fingerprint(root),
            "protocol_fingerprint": protocol_fingerprint(),
        },
        "source": {
            "repo": repo,
            "worktree": census["source"]["worktree"],
        },
        "instructions": {
            "schema": INSTRUCTION_MANIFEST_SCHEMA,
            "plane": INSTRUCTION_PLANE,
            "policy_fingerprint": policy_fingerprint,
            "layers": required_layers,
        },
        "capabilities": {
            "remote_harness_pid": "unavailable",
            "targeted_halt": "unsupported",
            "recovery": "unsupported",
            "crash_persistence": "unsupported",
        },
        "attestation": {
            "kind": "controller_attested",
            "recorded_at": _now(),
            "census_recorded_at": census["recorded_at"],
            "raw_output_retained": False,
        },
    }
    binding["fingerprint"] = binding_fingerprint(binding)
    validate_harness_binding(binding, skill_root=root)
    return binding


def validate_harness_binding(
    value: Any,
    *,
    expected_harness: str | None = None,
    expected_repo: str | None = None,
    expected_worktree: str | None = None,
    skill_root: Path | None = None,
    verify_current_adapters: bool = True,
    allow_historical: bool = False,
) -> dict[str, Any]:
    schema = value.get("schema") if isinstance(value, dict) else None
    historical_v1 = schema == "herdr-puppet.harness-binding.v1"
    historical_v2 = schema == "herdr-puppet.harness-binding.v2"
    historical = schema in HISTORICAL_BINDING_SCHEMAS
    if historical and not allow_historical:
        raise HerdrPuppetError(
            "legacy_harness_binding_requires_recensus",
            "Harness-binding v1/v2 is historical evidence; fresh qualification "
            "requires a new census and v3 binding.",
        )
    binding_fields = {
        "schema",
        "harness",
        "remote",
        "profile",
        "model_observation",
        "regular_launch",
        "adapters",
        "source",
        "instructions",
        "capabilities",
        "attestation",
        "fingerprint",
    }
    if not historical_v1:
        binding_fields.add("lifecycle_observation")
    binding = _require_exact_fields(
        value,
        binding_fields,
        "harness binding",
    )
    if binding["schema"] not in {
        BINDING_SCHEMA,
        *HISTORICAL_BINDING_SCHEMAS,
    }:
        raise HerdrPuppetError(
            "invalid_harness_binding",
            "The harness binding schema is unsupported.",
        )
    harness = binding["harness"]
    if harness not in CANONICAL_HARNESSES or (
        expected_harness is not None and harness != expected_harness
    ):
        raise HerdrPuppetError(
            "harness_binding_mismatch",
            "The harness binding target does not match.",
        )
    source = _require_exact_fields(
        binding["source"],
        {"repo", "worktree"},
        "binding source",
    )
    _require_text(source["repo"], "binding source repo")
    _require_text(source["worktree"], "binding source worktree", absolute=True)
    if expected_repo is not None and source["repo"] != expected_repo:
        raise HerdrPuppetError(
            "harness_binding_source_mismatch",
            "The harness binding repository does not match the leased source.",
        )
    if expected_worktree is not None and source["worktree"] != expected_worktree:
        raise HerdrPuppetError(
            "harness_binding_source_mismatch",
            "The harness binding worktree does not match the leased source.",
        )
    remote = _require_exact_fields(
        binding["remote"],
        {"host", "executable"},
        "binding remote",
    )
    _require_safe_value(remote["host"], "binding remote host")
    executable = remote["executable"]
    if not isinstance(executable, dict):
        raise HerdrPuppetError(
            "invalid_harness_binding",
            "The binding executable is invalid.",
        )
    for field in ("sha256", "version_sha256", "help_sha256", "fingerprint"):
        _require_sha256(executable.get(field), f"binding executable {field}")
    _require_text(executable.get("path"), "binding executable path", absolute=True)
    _require_text(executable.get("version"), "binding executable version")
    profile = binding["profile"]
    if (
        not isinstance(profile, dict)
        or profile.get("route") != "dedicated_os_user_profile"
        or not isinstance(profile.get("root"), str)
        or not Path(profile["root"]).is_absolute()
        or profile.get("isolation") != "dedicated_remote_user"
        or profile.get("enrollment_state") not in {
            "enrolled",
            "interactive_pending",
        }
        or profile.get("raw_output_retained") is not False
    ):
        raise HerdrPuppetError(
            "invalid_harness_binding",
            "The binding profile route or evidence state is invalid.",
        )
    if profile["enrollment_state"] == "enrolled":
        if profile.get("status_exit") != 0:
            raise HerdrPuppetError(
                "invalid_harness_binding",
                "The binding profile enrollment result is invalid.",
            )
    elif profile["enrollment_state"] == "interactive_pending":
        if harness != "cursor" or profile.get("status_exit") is not None:
            raise HerdrPuppetError(
                "invalid_harness_binding",
                "Only Cursor may carry a provisional interactive profile.",
            )
    validation_root = (
        _skill_root(skill_root)
        if verify_current_adapters and not historical
        else None
    )
    lifecycle = (
        None
        if historical_v1
        else validate_lifecycle_observation(
            binding["lifecycle_observation"],
            harness=harness,
            source_worktree=source["worktree"],
            skill_root=validation_root,
        )
    )
    launch = _require_exact_fields(
        binding["regular_launch"],
        {
            "argv",
            "environment",
            "inherit_environment",
            "unrestricted",
            "explicit_model_selector",
            "vector_sha256",
        },
        "binding regular launch",
    )
    expected_launch_environment = {
        "HOME": profile["root"],
        "PATH": ISOLATED_LAUNCH_PATH,
        "LANG": "C",
        "LC_ALL": "C",
        "TERM": "xterm-256color",
    }
    expected_launch_argv = [
        executable["path"],
        *(
            HISTORICAL_HARNESS_LAUNCH_FLAGS[harness]
            if historical_v1
            else (
                claude_launch_flags(lifecycle)
                if harness == "claude" and lifecycle is not None
                else (
                    HISTORICAL_HARNESS_LAUNCH_FLAGS[harness]
                    if historical_v2
                    else HARNESS_LAUNCH_SPECS[harness]["flags"]
                )
            )
        ),
    ]
    if (
        launch["inherit_environment"] is not False
        or launch.get("unrestricted") is not True
        or launch.get("explicit_model_selector")
        is not (harness == "agy" and not historical)
        or launch.get("argv") != expected_launch_argv
        or launch.get("environment") != expected_launch_environment
    ):
        raise HerdrPuppetError(
            "invalid_harness_binding",
            "The binding regular launch is invalid.",
        )
    expected_vector = _sha256_bytes(
        _canonical_bytes(
            {
                "argv": launch["argv"],
                "environment": launch["environment"],
                "inherit_environment": False,
            }
        )
    )
    if launch.get("vector_sha256") != expected_vector:
        raise HerdrPuppetError(
            "invalid_harness_binding",
            "The binding regular launch vector changed.",
        )
    model = binding["model_observation"]
    model_is_valid = (
        isinstance(model, dict)
        and set(model) == {"selection", "model", "effort"}
        and isinstance(model["model"], str)
        and isinstance(model["effort"], str)
        and (
            model["selection"] == "current_default"
            if historical or harness != "agy"
            else model
            == {
                "selection": "explicit",
                "model": AGY_REQUIRED_MODEL,
                "effort": "high",
            }
        )
    )
    if not model_is_valid:
        raise HerdrPuppetError(
            "invalid_harness_binding",
            "The binding model observation is invalid.",
        )
    adapters = _require_exact_fields(
        binding["adapters"],
        {
            "harness_fingerprint",
            "transport_fingerprint",
            "protocol_fingerprint",
        },
        "binding adapters",
    )
    for field in adapters:
        _require_sha256(adapters[field], f"binding adapter {field}")
    instructions = _require_exact_fields(
        binding["instructions"],
        {"schema", "plane", "policy_fingerprint", "layers"},
        "binding instructions",
    )
    expected_instruction_schema = (
        HISTORICAL_INSTRUCTION_MANIFEST_SCHEMA
        if historical
        else INSTRUCTION_MANIFEST_SCHEMA
    )
    expected_instruction_plane = (
        HISTORICAL_INSTRUCTION_PLANE
        if historical
        else INSTRUCTION_PLANE
    )
    if (
        instructions["schema"] != expected_instruction_schema
        or instructions["plane"] != expected_instruction_plane
        or instructions["layers"]
        != [
            "universal",
            f"harness/{harness}",
            (
                "model/default-unresolved"
                if historical
                else _model_layer(harness)
            ),
            "lifecycle/regular",
        ]
    ):
        raise HerdrPuppetError(
            "invalid_harness_binding",
            "The binding instruction plane is invalid.",
        )
    _require_sha256(
        instructions["policy_fingerprint"],
        "binding instruction policy fingerprint",
    )
    capabilities = _require_exact_fields(
        binding["capabilities"],
        {
            "remote_harness_pid",
            "targeted_halt",
            "recovery",
            "crash_persistence",
        },
        "binding capabilities",
    )
    if capabilities != {
        "remote_harness_pid": "unavailable",
        "targeted_halt": "unsupported",
        "recovery": "unsupported",
        "crash_persistence": "unsupported",
    }:
        raise HerdrPuppetError(
            "invalid_harness_binding",
            "Stable remote-process capabilities must remain explicitly unsupported.",
        )
    attestation = _require_exact_fields(
        binding["attestation"],
        {
            "kind",
            "recorded_at",
            "census_recorded_at",
            "raw_output_retained",
        },
        "binding attestation",
    )
    if (
        attestation["kind"] != "controller_attested"
        or attestation["raw_output_retained"] is not False
    ):
        raise HerdrPuppetError(
            "invalid_harness_binding",
            "The binding is not a body-free controller attestation.",
        )
    _require_rfc3339(attestation["recorded_at"], "binding recorded_at")
    _require_rfc3339(
        attestation["census_recorded_at"],
        "binding census_recorded_at",
    )
    _require_sha256(binding["fingerprint"], "binding fingerprint")
    if binding["fingerprint"] != binding_fingerprint(binding):
        raise HerdrPuppetError(
            "harness_binding_fingerprint_mismatch",
            "The harness binding fingerprint does not match its payload.",
        )
    if verify_current_adapters and not historical:
        root = validation_root
        assert root is not None
        if (
            adapters["harness_fingerprint"] != harness_adapter_fingerprint(root)
            or adapters["transport_fingerprint"]
            != transport_adapter_fingerprint(root)
            or adapters["protocol_fingerprint"] != protocol_fingerprint()
            or instructions["policy_fingerprint"]
            != instruction_policy_fingerprint(root)
        ):
            raise HerdrPuppetError(
                "harness_binding_adapter_drift",
                "The harness binding does not match the current controller sources.",
            )
    return binding


def verify_remote_census(
    *,
    binding_value: Any,
    census_value: Any,
    skill_root: Path | None = None,
) -> dict[str, Any]:
    binding = validate_harness_binding(
        binding_value,
        skill_root=skill_root,
    )
    census = validate_remote_census(census_value, skill_root=skill_root)
    expected = {
        "harness": binding["harness"],
        "host": binding["remote"]["host"],
        "executable": binding["remote"]["executable"],
        "profile": binding["profile"],
        "regular_launch": binding["regular_launch"],
        "lifecycle_observation": binding["lifecycle_observation"],
        "model_observation": binding["model_observation"],
        "source": {"worktree": binding["source"]["worktree"]},
        "raw_output_retained": False,
    }
    mismatches = [
        field
        for field, expected_value in expected.items()
        if census.get(field) != expected_value
    ]
    if mismatches:
        raise HerdrPuppetError(
            "harness_recensus_mismatch",
            "The in-row remote census does not match the controller-attested binding.",
            details={"mismatched_fields": mismatches},
        )
    binding_census_time = datetime.fromisoformat(
        binding["attestation"]["census_recorded_at"].replace("Z", "+00:00")
    )
    row_census_time = datetime.fromisoformat(
        census["recorded_at"].replace("Z", "+00:00")
    )
    if row_census_time < binding_census_time:
        raise HerdrPuppetError(
            "harness_recensus_stale",
            "The in-row remote census predates the bound controller census.",
        )
    return {
        "schema": "herdr-puppet.harness-recensus-verification.v1",
        "result": "ok",
        "harness": binding["harness"],
        "binding_fingerprint": binding["fingerprint"],
        "bound_census_recorded_at": binding["attestation"][
            "census_recorded_at"
        ],
        "row_census_recorded_at": census["recorded_at"],
        "executable_fingerprint": census["executable"]["fingerprint"],
        "profile_route": census["profile"]["route"],
        "profile_enrollment": census["profile"]["enrollment_state"],
        "observed_model": census["model_observation"]["model"],
        "observed_effort": census["model_observation"]["effort"],
        "launch_vector_sha256": census["regular_launch"]["vector_sha256"],
        "lifecycle_strategy": census["lifecycle_observation"]["strategy"],
        "source_worktree": census["source"]["worktree"],
        "explicit_model_selector": census["regular_launch"][
            "explicit_model_selector"
        ],
        "raw_output_retained": False,
    }


def _validate_instruction_text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise HerdrPuppetError(
            "invalid_instruction_wrapper",
            f"{label} must be non-empty UTF-8 text.",
        )
    normalized = value.replace("\r\n", "\n").replace("\r", "\n")
    if "\x00" in normalized or len(normalized.encode("utf-8")) > MAX_TEXT_BYTES:
        raise HerdrPuppetError(
            "invalid_instruction_wrapper",
            f"{label} exceeds the bounded text contract.",
        )
    if any(pattern.search(normalized) for pattern in _SECRET_SHAPES):
        raise HerdrPuppetError(
            "invalid_instruction_wrapper",
            f"{label} contains secret-shaped content.",
        )
    return normalized


def compile_instruction_wrapper(
    *,
    binding_value: Any,
    run_id: str,
    task: str,
    skill_root: Path | None = None,
) -> tuple[bytes, dict[str, Any]]:
    root = _skill_root(skill_root)
    binding = validate_harness_binding(binding_value, skill_root=root)
    _require_safe_value(run_id, "instruction run id")
    normalized_task = _validate_instruction_text(task, "instruction task")
    template_root = root / "templates" / "instructions"
    catalog = json.loads(
        (template_root / "catalog.json").read_text(encoding="utf-8")
    )
    models = catalog["models"]
    model_layer = _model_layer(binding["harness"])
    model_path = (
        models["agy_gemini_3_7_flash_high"]
        if binding["harness"] == "agy"
        else models["default_unresolved"]
    )
    layer_specs = [
        ("universal", catalog["universal"]),
        (f"harness/{binding['harness']}", catalog["harnesses"][binding["harness"]]),
        (model_layer, model_path),
        ("lifecycle/regular", catalog["lifecycle"]),
    ]
    runtime = _canonical_bytes(
        {
            "run_id": run_id,
            "harness": binding["harness"],
            "binding_fingerprint": binding["fingerprint"],
            "source": binding["source"],
            "instruction_plane": INSTRUCTION_PLANE,
            "model_observation": binding["model_observation"],
            "capabilities": binding["capabilities"],
        }
    ).decode("utf-8")
    layers: list[tuple[str, str]] = []
    for name, relative in layer_specs:
        path = _safe_template_path(template_root, relative)
        layers.append((name, path.read_text(encoding="utf-8").rstrip("\n")))
    layers.extend(
        [
            ("runtime_contract", runtime),
            ("task_packet", normalized_task.rstrip("\n")),
        ]
    )
    rendered = "\n\n".join(
        f"## {name}\n{body}" for name, body in layers
    ).encode("utf-8")
    if len(rendered) > 64 * 1024:
        raise HerdrPuppetError(
            "invalid_instruction_wrapper",
            "The rendered instruction wrapper exceeds the bounded size.",
        )
    ordered_layers = [
        {
            "name": name,
            "sha256": _sha256_bytes(body.encode("utf-8")),
            "bytes": len(body.encode("utf-8")),
        }
        for name, body in layers
    ]
    manifest = {
        "schema": INSTRUCTION_MANIFEST_SCHEMA,
        "harness": binding["harness"],
        "run_id": run_id,
        "binding_fingerprint": binding["fingerprint"],
        "plane": INSTRUCTION_PLANE,
        "policy_fingerprint": binding["instructions"]["policy_fingerprint"],
        "rendered_sha256": _sha256_bytes(rendered),
        "byte_count": len(rendered),
        "ordered_layers": ordered_layers,
        "task_body_retained": False,
    }
    validate_instruction_manifest(
        manifest,
        binding_value=binding,
        rendered=rendered,
        skill_root=root,
    )
    return rendered, manifest


def validate_instruction_manifest(
    value: Any,
    *,
    binding_value: Any,
    rendered: bytes | None = None,
    skill_root: Path | None = None,
) -> dict[str, Any]:
    binding = validate_harness_binding(
        binding_value,
        skill_root=skill_root,
    )
    manifest = _require_exact_fields(
        value,
        {
            "schema",
            "harness",
            "run_id",
            "binding_fingerprint",
            "plane",
            "policy_fingerprint",
            "rendered_sha256",
            "byte_count",
            "ordered_layers",
            "task_body_retained",
        },
        "instruction manifest",
    )
    if (
        manifest["schema"] != INSTRUCTION_MANIFEST_SCHEMA
        or manifest["harness"] != binding["harness"]
        or manifest["binding_fingerprint"] != binding["fingerprint"]
        or manifest["plane"] != INSTRUCTION_PLANE
        or manifest["policy_fingerprint"]
        != binding["instructions"]["policy_fingerprint"]
        or manifest["task_body_retained"] is not False
    ):
        raise HerdrPuppetError(
            "invalid_instruction_wrapper",
            "The instruction manifest does not match its harness binding.",
        )
    _require_safe_value(manifest["run_id"], "instruction manifest run id")
    _require_sha256(
        manifest["rendered_sha256"],
        "instruction manifest rendered_sha256",
    )
    if (
        isinstance(manifest["byte_count"], bool)
        or not isinstance(manifest["byte_count"], int)
        or manifest["byte_count"] < 1
        or manifest["byte_count"] > 64 * 1024
    ):
        raise HerdrPuppetError(
            "invalid_instruction_wrapper",
            "The instruction manifest byte count is invalid.",
        )
    layers = manifest["ordered_layers"]
    expected_names = [
        "universal",
        f"harness/{binding['harness']}",
        _model_layer(binding["harness"]),
        "lifecycle/regular",
        "runtime_contract",
        "task_packet",
    ]
    if (
        not isinstance(layers, list)
        or [item.get("name") for item in layers if isinstance(item, dict)]
        != expected_names
    ):
        raise HerdrPuppetError(
            "invalid_instruction_wrapper",
            "The instruction manifest layer order is invalid.",
        )
    for layer in layers:
        if (
            not isinstance(layer, dict)
            or set(layer) != {"name", "sha256", "bytes"}
            or not isinstance(layer["bytes"], int)
            or isinstance(layer["bytes"], bool)
            or layer["bytes"] < 0
        ):
            raise HerdrPuppetError(
                "invalid_instruction_wrapper",
                "An instruction manifest layer is invalid.",
            )
        _require_sha256(layer["sha256"], "instruction layer sha256")
    if rendered is not None and (
        _sha256_bytes(rendered) != manifest["rendered_sha256"]
        or len(rendered) != manifest["byte_count"]
    ):
        raise HerdrPuppetError(
            "instruction_wrapper_payload_mismatch",
            "The rendered instruction payload does not match its manifest.",
        )
    return manifest


def write_create_only(path: Path, payload: bytes, *, mode: int = 0o600) -> None:
    destination = Path(path).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(destination, flags, mode)
    except FileExistsError as exc:
        raise HerdrPuppetError(
            "output_exists",
            "Refusing to overwrite a controller-owned output.",
        ) from exc
    try:
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "wb", closefd=False) as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        os.close(descriptor)
    details = destination.stat()
    if (
        not stat.S_ISREG(details.st_mode)
        or stat.S_IMODE(details.st_mode) != mode
    ):
        raise HerdrPuppetError(
            "output_identity_invalid",
            "The controller output does not have the required file identity.",
        )
