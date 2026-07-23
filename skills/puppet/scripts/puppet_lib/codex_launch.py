"""Source-only Codex regular-session launch gate.

The gate binds manifest and filesystem identity without launching a target process.
Returned context is value-free by design; only the non-secret, exact launch argv is
retained for inspection.
"""

from __future__ import annotations

import json
import os
import selectors
import signal
import stat
import subprocess
import time
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

from .adapter_manifest import AdapterManifest, _validated_process_record
from .campaign import active_target_processes
from .census import adapter_implementation_fingerprint
from .errors import IdentityError, ValidationError
from .handoffs import PROTOCOL_FINGERPRINT
from .launch import public_launch_identity, select_launch_environment
from .safety import (
    absolute_root,
    canonical_json_bytes,
    ensure_within,
    paths_overlap,
    sha256_bytes,
    validate_bounded_json,
    validate_identifier,
)

LAUNCH_CONTEXT_SCHEMA = "puppet.codex-launch-context/v1"
DOCTOR_OBSERVATION_SCHEMA = "puppet.codex-doctor-observation/v1"
DOCTOR_OBSERVATION_STATE = "source_only_observation"
DOCTOR_TIMEOUT_SECONDS = 10.0
MAX_DOCTOR_OUTPUT_BYTES = 65536
EXPECTED_REQUESTED_EXECUTABLE_PATH = "/opt/homebrew/bin/codex"
EXPECTED_RESOLVED_EXECUTABLE_PATH = (
    "/opt/homebrew/Caskroom/codex/0.145.0/codex-aarch64-apple-darwin"
)
EXPECTED_EXECUTABLE_SHA256 = (
    "1da3f4e0e96028b8a771814293c3033dafd1971f943f6c7e79b0897fe705f590"
)
EXPECTED_VERSION_SHA256 = (
    "f9eb0c462cdded1fb971b33c647ff1b8b491dfe962a1506026e07a06f634f651"
)
EXPECTED_VERSION_TEXT = "codex-cli 0.145.0"
EXPECTED_UNRESTRICTED_FLAG = "--dangerously-bypass-approvals-and-sandbox"
EXPECTED_MODEL_FLAG = "--model"
CURRENT_DEFAULT_SELECTION = "current_default"
AUTH_ROUTE = "process_local_access_token_broker"
SOURCE_ONLY_BLOCKERS = (
    "approved process-local auth broker unavailable",
    "native instruction plane activation/precedence/no-bleed unproved",
    "live doctor/current-default and Pass-B lifecycle unproved",
    "launch remains fenced/source-only",
)
MAPPING_INCOMPLETE_BLOCKER = "native-plane mapping remains incomplete"
DEFAULT_MODEL_SENTINEL = "<default>"
DEFAULT_MODEL_CLASSIFICATION = "available_for_test_plan_only"
EXPLICIT_MODEL_CLASSIFICATION = "observed_only"
UNAVAILABLE_MODEL_CLASSIFICATION = "unavailable"


def _validate_root(path: Path, *, label: str) -> Dict[str, Any]:
    root = absolute_root(str(path), label)
    details = root.stat()
    if not stat.S_ISDIR(details.st_mode):
        raise ValidationError("%s is not a directory" % label)
    if details.st_uid != os.getuid():
        raise ValidationError("%s is not user-owned" % label)
    if stat.S_IMODE(details.st_mode) != 0o700:
        raise ValidationError("%s is not 0700" % label)
    return {
        "path": str(root),
        "device": details.st_dev,
        "inode": details.st_ino,
        "uid": details.st_uid,
        "gid": details.st_gid,
        "mode": stat.S_IMODE(details.st_mode),
        "nlink": details.st_nlink,
    }


def _contained_private_root(root: Path, *, parent: Path, label: str) -> Dict[str, Any]:
    details = _validate_root(root, label=label)
    contained = ensure_within(Path(details["path"]), parent, must_exist=True)
    if contained == parent:
        raise ValidationError("%s must be a distinct child of the lane root" % label)
    return _validate_root(contained, label=label)


def _validate_requested_executable_link(
    *, requested_path: str, resolved_path: str
) -> None:
    requested = Path(requested_path)
    expected_resolved = Path(resolved_path)
    try:
        requested_details = requested.lstat()
    except OSError as exc:
        raise IdentityError("requested Codex executable is unavailable") from exc
    if not stat.S_ISLNK(requested_details.st_mode):
        raise IdentityError("requested Codex executable is not a symlink")
    try:
        current_resolved = requested.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise IdentityError("requested Codex executable symlink is invalid") from exc
    if current_resolved != expected_resolved:
        raise IdentityError("requested Codex executable symlink target changed")


def _validate_launch_argv(
    *, mapping: Mapping[str, Any], executable_path: str
) -> Tuple[str, ...]:
    raw_argv = mapping.get("launch_argv")
    if not isinstance(raw_argv, list) or not raw_argv:
        raise ValidationError("manifest launch argv must be a non-empty list")
    if len(raw_argv) > 64:
        raise ValidationError("manifest launch argv is too long")
    validated = []
    for item in raw_argv:
        if (
            not isinstance(item, str)
            or not item
            or len(item) > 8192
            or any(character in item for character in "\x00\r\n")
        ):
            raise ValidationError("manifest launch argv item is invalid")
        validated.append(item)
    if validated[0] != executable_path:
        raise ValidationError(
            "manifest launch argv does not start with executable path"
        )
    return tuple(validated)


def _validate_codex_mapping(
    *, mapping: Mapping[str, Any], executable_path: str
) -> Tuple[str, ...]:
    argv = _validate_launch_argv(mapping=mapping, executable_path=executable_path)
    expected_argv = (executable_path, EXPECTED_UNRESTRICTED_FLAG)
    if argv != expected_argv:
        raise ValidationError(
            "manifest launch argv is not the exact Codex regular unrestricted mapping"
        )
    if mapping.get("permission_declared") is not True or mapping.get(
        "permission_flags"
    ) != [EXPECTED_UNRESTRICTED_FLAG]:
        raise ValidationError("Codex permission mapping is unexpected")
    if mapping.get("sandbox_disable_declared") is not True or mapping.get(
        "sandbox_flags"
    ) != [EXPECTED_UNRESTRICTED_FLAG]:
        raise ValidationError("Codex sandbox mapping is unexpected")
    if mapping.get("project_isolation_flags") != []:
        raise ValidationError("Codex project isolation mapping is unexpected")
    if mapping.get("complete") is not False:
        raise ValidationError("Codex mapping completeness is unexpected")
    if mapping.get("project_isolation_declared") is not False:
        raise ValidationError("Codex project isolation declaration is unexpected")
    if mapping.get("model_flag") != EXPECTED_MODEL_FLAG:
        raise ValidationError("Codex model capability mapping is unexpected")
    if "effort_flag" in mapping:
        raise ValidationError("Codex effort capability mapping is unexpected")
    return argv


def _validate_candidate_processes(
    processes: Any,
    *,
    selectors: Tuple[Tuple[str, int, int], ...],
    block: list[str],
) -> Tuple[Dict[str, Any], ...]:
    if not isinstance(processes, list):
        raise ValidationError("candidate process output must be a list")
    if len(processes) > 4096:
        raise ValidationError("candidate process output is too large")
    validated = []
    seen_pids = set()
    seen_birth_identities = set()
    selector_set = set(selectors)
    for process in processes:
        process = _validated_process_record(process, "candidate process")
        selector = (
            process["executable_path"],
            process["device"],
            process["inode"],
        )
        if selector not in selector_set:
            raise ValidationError("candidate process executable is not declared")
        birth_identity = (process["start"], process["kernel_birth_id"])
        if process["pid"] in seen_pids or birth_identity in seen_birth_identities:
            raise ValidationError("candidate process identities duplicate")
        seen_pids.add(process["pid"])
        seen_birth_identities.add(birth_identity)
        validated.append(process)
    if validated:
        block.append("existing target candidate processes detected")
    return tuple(sorted(validated, key=lambda item: item["pid"]))


def _build_candidate_fingerprint(processes: Sequence[Dict[str, Any]]) -> str:
    normalized = [
        {name: process[name] for name in sorted(process)} for process in processes
    ]
    return sha256_bytes(
        canonical_json_bytes(
            {
                "count": len(processes),
                "candidates": normalized,
            }
        )
    )


@dataclass(frozen=True)
class CodexLaunchContext:
    """Value-private source-only launch context."""

    target: str
    session_profile: str
    manifest_fingerprint: str
    execution_fingerprint: str
    adapter_fingerprint: str
    protocol_fingerprint: str
    version_text: str
    requested_executable_path: str
    resolved_executable_path: str
    manifest_executable_sha256: str
    manifest_version_sha256: str
    model_selection: str
    effort_selection: str
    lane_root_identity: Dict[str, Any]
    workspace_root_identity: Dict[str, Any]
    codex_home_identity: Dict[str, Any]
    launch_authorized: bool
    blockers: Tuple[str, ...]
    auth_route: str
    candidate_process_count: int
    candidate_process_pids: Tuple[int, ...]
    candidate_process_fingerprint: str
    _argv: Tuple[str, ...] = field(repr=False)
    _launch_identity: Dict[str, Any] = field(repr=False)

    def to_public_dict(self) -> Dict[str, Any]:
        return {
            "schema": LAUNCH_CONTEXT_SCHEMA,
            "target": self.target,
            "session_profile": self.session_profile,
            "launch_authorized": self.launch_authorized,
            "manifest_fingerprint": self.manifest_fingerprint,
            "execution_fingerprint": self.execution_fingerprint,
            "adapter_fingerprint": self.adapter_fingerprint,
            "protocol_fingerprint": self.protocol_fingerprint,
            "version_text": self.version_text,
            "requested_executable_path": self.requested_executable_path,
            "resolved_executable_path": self.resolved_executable_path,
            "executable_sha256": self.manifest_executable_sha256,
            "version_sha256": self.manifest_version_sha256,
            "lane_root_identity": self.lane_root_identity,
            "workspace_root_identity": self.workspace_root_identity,
            "codex_home_identity": self.codex_home_identity,
            "lane_root_identity_sha256": sha256_bytes(
                canonical_json_bytes(self.lane_root_identity)
            ),
            "workspace_root_identity_sha256": sha256_bytes(
                canonical_json_bytes(self.workspace_root_identity)
            ),
            "codex_home_identity_sha256": sha256_bytes(
                canonical_json_bytes(self.codex_home_identity)
            ),
            "launch_identity": self._launch_identity,
            "candidate_process_count": self.candidate_process_count,
            "candidate_process_pids": list(self.candidate_process_pids),
            "candidate_process_fingerprint": self.candidate_process_fingerprint,
            "model_selection": self.model_selection,
            "effort_selection": self.effort_selection,
            "auth_route": self.auth_route,
            "blockers": list(self.blockers),
        }

    @property
    def public_context_sha256(self) -> str:
        return sha256_bytes(canonical_json_bytes(self.to_public_dict()))

    @property
    def argv(self) -> list[str]:
        return list(self._argv)


@dataclass(frozen=True)
class CodexDoctorObservation:
    """Allowlisted doctor provenance with the raw report discarded."""

    classification: str
    observed_model: Optional[str]
    observed_provider: Optional[str]
    doctor_output_sha256: str
    doctor_output_bytes: int
    manifest_fingerprint: str
    execution_fingerprint: str
    adapter_fingerprint: str
    protocol_fingerprint: str
    codex_home_identity_sha256: str
    launch_context_sha256: str
    doctor_command_identity: Dict[str, Any]
    blockers: Tuple[str, ...]

    def to_public_dict(self) -> Dict[str, Any]:
        value = {
            "schema": DOCTOR_OBSERVATION_SCHEMA,
            "state": DOCTOR_OBSERVATION_STATE,
            "target": "codex",
            "session_profile": "regular",
            "classification": self.classification,
            "observed_model": self.observed_model,
            "observed_provider": self.observed_provider,
            "doctor_output_sha256": self.doctor_output_sha256,
            "doctor_output_bytes": self.doctor_output_bytes,
            "manifest_fingerprint": self.manifest_fingerprint,
            "execution_fingerprint": self.execution_fingerprint,
            "adapter_fingerprint": self.adapter_fingerprint,
            "protocol_fingerprint": self.protocol_fingerprint,
            "codex_home_identity_sha256": self.codex_home_identity_sha256,
            "launch_context_sha256": self.launch_context_sha256,
            "doctor_command_identity": dict(self.doctor_command_identity),
            "blockers": list(self.blockers),
            "launch_authorized": False,
            "qualification_authorized": False,
            "same_runtime_proved": False,
            "model_selection_authorized": False,
        }
        value["observation_sha256"] = sha256_bytes(canonical_json_bytes(value))
        validate_bounded_json(
            value,
            max_depth=6,
            max_items=64,
            max_string=4096,
            reject_sensitive_fields=True,
        )
        return value


def _bounded_doctor_run(
    argv: Sequence[str], *, environment: Mapping[str, str], cwd: Path
) -> subprocess.CompletedProcess[bytes]:
    process: Optional[subprocess.Popen[bytes]] = None
    selector: Optional[selectors.BaseSelector] = None
    output = bytearray()
    group_terminated = False

    def terminate_group() -> None:
        nonlocal group_terminated
        if process is None or group_terminated:
            return
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        group_terminated = True

    try:
        process = subprocess.Popen(
            list(argv),
            cwd=str(cwd),
            env=dict(environment),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        if process.stdout is None:  # pragma: no cover - PIPE guarantees this
            raise ValidationError("Codex doctor output pipe is unavailable")
        os.set_blocking(process.stdout.fileno(), False)
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ)
        deadline = time.monotonic() + DOCTOR_TIMEOUT_SECONDS
        eof = False
        while not eof:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(list(argv), DOCTOR_TIMEOUT_SECONDS)
            ready = selector.select(min(remaining, 0.25))
            for key, _mask in ready:
                try:
                    block = os.read(key.fileobj.fileno(), 4096)
                except BlockingIOError:
                    continue
                if not block:
                    eof = True
                    break
                output.extend(block)
                if len(output) > MAX_DOCTOR_OUTPUT_BYTES:
                    raise ValidationError("Codex doctor output exceeds the cap")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise subprocess.TimeoutExpired(list(argv), DOCTOR_TIMEOUT_SECONDS)
        returncode = process.wait(timeout=remaining)
        terminate_group()
        return subprocess.CompletedProcess(
            list(argv),
            returncode,
            stdout=bytes(output),
            stderr=None,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValidationError("Codex doctor command failed") from exc
    finally:
        if selector is not None:
            selector.close()
        if process is not None:
            terminate_group()
            process.wait()
            if process.stdout is not None:
                process.stdout.close()


def _doctor_command(
    context: CodexLaunchContext,
) -> Tuple[Tuple[str, ...], Dict[str, str], Dict[str, Any]]:
    argv = (context.resolved_executable_path, "doctor", "--json")
    lane_root = Path(context.lane_root_identity["path"])
    workspace = Path(context.workspace_root_identity["path"])
    environment = select_launch_environment(
        target="codex",
        source_environment={},
        bindings={"CODEX_HOME": context.codex_home_identity["path"]},
        admitted_lane_root=lane_root,
    )
    identity = public_launch_identity(
        repo=workspace,
        argv=argv,
        environment=environment,
        admitted_lane_root=lane_root,
    )
    return argv, environment, identity


def _unique_json_object(pairs: list[tuple[str, Any]]) -> Dict[str, Any]:
    value: Dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValidationError("Codex doctor JSON contains duplicate fields")
        value[key] = item
    return value


def _reject_json_constant(value: str) -> None:
    raise ValidationError("Codex doctor output contains a non-JSON constant: %s" % value)


def _safe_doctor_value(value: Any, *, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 200
        or value != value.strip()
        or any(unicodedata.category(character).startswith("C") for character in value)
    ):
        raise ValidationError("Codex doctor %s is invalid" % label)
    if value == DEFAULT_MODEL_SENTINEL and label == "model":
        return value
    if not all(
        character.isascii()
        and (character.isalnum() or character in "._:/-")
        for character in value
    ):
        raise ValidationError("Codex doctor %s is invalid" % label)
    return value


def _parse_doctor_model(output: bytes) -> Tuple[str, Optional[str], Optional[str]]:
    if len(output) > MAX_DOCTOR_OUTPUT_BYTES:
        raise ValidationError("Codex doctor output exceeds the cap")
    try:
        text = output.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValidationError("Codex doctor output is not UTF-8") from exc
    try:
        value = json.loads(
            text,
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_json_constant,
        )
    except (json.JSONDecodeError, RecursionError) as exc:
        raise ValidationError("Codex doctor output is not valid JSON") from exc
    if not isinstance(value, dict):
        raise ValidationError("Codex doctor JSON root is invalid")
    validate_bounded_json(
        value,
        max_depth=12,
        max_items=256,
        max_string=8192,
    )
    checks = value.get("checks")
    if not isinstance(checks, dict):
        raise ValidationError("Codex doctor checks are invalid")
    config = checks.get("config.load")
    if config is None:
        return UNAVAILABLE_MODEL_CLASSIFICATION, None, None
    if not isinstance(config, dict) or config.get("id") != "config.load":
        raise ValidationError("Codex doctor config check is ambiguous")
    details = config.get("details")
    if not isinstance(details, dict):
        return UNAVAILABLE_MODEL_CLASSIFICATION, None, None
    for key in details:
        normalized = " ".join(
            key.casefold().replace("_", " ").replace("-", " ").split()
        )
        if normalized in {"model", "model provider"} and key not in {
            "model",
            "model provider",
        }:
            raise ValidationError("Codex doctor model fields are ambiguous")
    if "model" not in details or "model provider" not in details:
        return UNAVAILABLE_MODEL_CLASSIFICATION, None, None
    model = _safe_doctor_value(details["model"], label="model")
    provider = _safe_doctor_value(details["model provider"], label="provider")
    classification = (
        DEFAULT_MODEL_CLASSIFICATION
        if model == DEFAULT_MODEL_SENTINEL
        else EXPLICIT_MODEL_CLASSIFICATION
    )
    return classification, model, provider


def _derive_codex_doctor_observation(
    context: CodexLaunchContext,
    output: bytes,
    *,
    doctor_command_identity: Mapping[str, Any],
) -> CodexDoctorObservation:
    if context.launch_authorized or context.target != "codex":
        raise IdentityError("Codex doctor context gained launch authority")
    _argv, _environment, expected_identity = _doctor_command(context)
    if dict(doctor_command_identity) != expected_identity:
        raise IdentityError("Codex doctor command identity changed")
    classification, model, provider = _parse_doctor_model(output)
    return CodexDoctorObservation(
        classification=classification,
        observed_model=model,
        observed_provider=provider,
        doctor_output_sha256=sha256_bytes(output),
        doctor_output_bytes=len(output),
        manifest_fingerprint=context.manifest_fingerprint,
        execution_fingerprint=context.execution_fingerprint,
        adapter_fingerprint=context.adapter_fingerprint,
        protocol_fingerprint=context.protocol_fingerprint,
        codex_home_identity_sha256=sha256_bytes(
            canonical_json_bytes(context.codex_home_identity)
        ),
        launch_context_sha256=context.public_context_sha256,
        doctor_command_identity=expected_identity,
        blockers=context.blockers,
    )


def build_codex_launch_context(
    *,
    manifest_path: Path | str,
    lane_root: Path | str,
    workspace_root: Path | str,
    codex_home: Path | str,
) -> CodexLaunchContext:
    """Build a source-only Codex launch context without starting anything."""

    session_profile = validate_identifier("regular", "session profile")
    manifest = AdapterManifest.from_path(Path(manifest_path))
    if manifest.target != "codex":
        raise ValidationError("launch context requires target codex")

    blockers = [*SOURCE_ONLY_BLOCKERS, MAPPING_INCOMPLETE_BLOCKER]
    lane = _validate_root(Path(lane_root), label="lane root")
    lane_root_path = Path(lane["path"])
    workspace = _contained_private_root(
        Path(workspace_root),
        parent=lane_root_path,
        label="workspace root",
    )
    workspace_path = Path(workspace["path"])
    home = _contained_private_root(
        Path(codex_home),
        parent=lane_root_path,
        label="CODEX_HOME",
    )
    codex_home_path = Path(home["path"])
    if paths_overlap(workspace_path, codex_home_path):
        raise ValidationError("workspace and CODEX_HOME must be non-overlapping")
    if manifest.raw["adapter_fingerprint"] != adapter_implementation_fingerprint():
        raise ValidationError("manifest adapter fingerprint is unexpected")
    if manifest.raw["protocol_fingerprint"] != PROTOCOL_FINGERPRINT:
        raise ValidationError("manifest protocol fingerprint is unexpected")

    executable = manifest.raw["executable"]
    if executable["requested_path"] != EXPECTED_REQUESTED_EXECUTABLE_PATH:
        raise ValidationError("manifest requested executable path is unexpected")
    if executable["resolved_path"] != EXPECTED_RESOLVED_EXECUTABLE_PATH:
        raise ValidationError("manifest resolved executable path is unexpected")
    if executable["sha256"] != EXPECTED_EXECUTABLE_SHA256:
        raise ValidationError("manifest executable hash is unexpected")
    if executable["version_sha256"] != EXPECTED_VERSION_SHA256:
        raise ValidationError("manifest executable version hash is unexpected")
    _validate_requested_executable_link(
        requested_path=executable["requested_path"],
        resolved_path=executable["resolved_path"],
    )
    manifest.verify_execution_files()

    mapping = manifest.raw["yolo_mapping"]
    argv = _validate_codex_mapping(
        mapping=mapping,
        executable_path=executable["resolved_path"],
    )
    if not manifest.raw["doctor_only"]:
        raise ValidationError("source-only Codex launch requires doctor-only manifest")
    if manifest.raw["qualification"] is not None:
        raise ValidationError(
            "source-only Codex launch requires a doctor-only manifest"
        )

    try:
        selectors = manifest.process_execution_selectors()
        selector_tuples = tuple(
            (
                selector["path"],
                selector["device"],
                selector["inode"],
            )
            for selector in selectors
        )
        candidate_processes = active_target_processes(manifest.target, selectors)
    except (TypeError, ValueError, IdentityError, ValidationError, AttributeError):
        raise ValidationError("candidate process lookup is malformed")
    except Exception as exc:  # pragma: no cover - defensive guardrail
        raise ValidationError("candidate process lookup failed") from exc
    try:
        candidate_processes = _validate_candidate_processes(
            candidate_processes,
            selectors=selector_tuples,
            block=blockers,
        )
    except (TypeError, ValueError, IdentityError, ValidationError) as exc:
        raise ValidationError("candidate process lookup is malformed") from exc

    candidate_pids = tuple(process["pid"] for process in candidate_processes)
    candidate_hash = _build_candidate_fingerprint(candidate_processes)

    environment = select_launch_environment(
        target="codex",
        source_environment={},
        bindings={"CODEX_HOME": str(codex_home_path)},
        admitted_lane_root=lane_root_path,
    )
    manifest.verify_launch_execution_environment(environment)
    launch_identity = public_launch_identity(
        repo=workspace_path,
        argv=argv,
        environment=environment,
        admitted_lane_root=lane_root_path,
    )
    return CodexLaunchContext(
        target=manifest.target,
        session_profile=session_profile,
        manifest_fingerprint=manifest.fingerprint,
        execution_fingerprint=manifest.raw["execution"]["execution_fingerprint"],
        adapter_fingerprint=manifest.raw["adapter_fingerprint"],
        protocol_fingerprint=manifest.raw["protocol_fingerprint"],
        version_text=EXPECTED_VERSION_TEXT,
        requested_executable_path=executable["requested_path"],
        resolved_executable_path=executable["resolved_path"],
        manifest_executable_sha256=executable["sha256"],
        manifest_version_sha256=executable["version_sha256"],
        model_selection=CURRENT_DEFAULT_SELECTION,
        effort_selection=CURRENT_DEFAULT_SELECTION,
        lane_root_identity=lane,
        workspace_root_identity=workspace,
        codex_home_identity=home,
        launch_authorized=False,
        auth_route=AUTH_ROUTE,
        blockers=tuple(blockers),
        candidate_process_count=len(candidate_pids),
        candidate_process_pids=candidate_pids,
        candidate_process_fingerprint=candidate_hash,
        _argv=argv,
        _launch_identity=launch_identity,
    )


def observe_codex_doctor(
    *,
    manifest_path: Path | str,
    lane_root: Path | str,
    workspace_root: Path | str,
    codex_home: Path | str,
) -> CodexDoctorObservation:
    """Run one exact private-root doctor command and discard its raw report."""

    before = build_codex_launch_context(
        manifest_path=manifest_path,
        lane_root=lane_root,
        workspace_root=workspace_root,
        codex_home=codex_home,
    )
    if before.candidate_process_count:
        raise IdentityError(
            "Codex doctor observation requires zero pre-existing target processes"
        )
    argv, environment, command_identity = _doctor_command(before)
    result = _bounded_doctor_run(
        argv,
        environment=environment,
        cwd=Path(before.workspace_root_identity["path"]),
    )
    if result.returncode != 0:
        raise ValidationError("Codex doctor command returned nonzero")
    after = build_codex_launch_context(
        manifest_path=manifest_path,
        lane_root=lane_root,
        workspace_root=workspace_root,
        codex_home=codex_home,
    )
    if after.candidate_process_count or (
        after.public_context_sha256 != before.public_context_sha256
    ):
        raise IdentityError("Codex doctor source identity changed during observation")
    _after_argv, _after_environment, after_identity = _doctor_command(after)
    if after_identity != command_identity:
        raise IdentityError("Codex doctor command identity changed during observation")
    return _derive_codex_doctor_observation(
        after,
        result.stdout,
        doctor_command_identity=after_identity,
    )


__all__ = [
    "CodexDoctorObservation",
    "CodexLaunchContext",
    "build_codex_launch_context",
    "observe_codex_doctor",
]
