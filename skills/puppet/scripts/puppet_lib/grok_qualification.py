"""Fail-closed paired-runtime qualification for Grok Build regular sessions.

This module never launches Grok and never reads authentication or instruction
contents.  It verifies two already terminal controller-owned probe runs:

* one positive run with a create-only workspace rule that was rolled back; and
* one later ordinary run linked to that exact positive receipt, with no Puppet
  workspace rule.

Both runs must use the same authenticated private subscription profile and the
same canonical runtime-vector shape: explicit cwd, one private unique leader
socket, and one canonical UUIDv4.  Process, tmux, workspace, socket, UUID,
checkpoint, view, and halt identities must remain distinct.  Only the
controller-attested terminal pair is promotable.
"""

from __future__ import annotations

import json
import os
import stat
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional, Sequence

from .authority import attest_qualification, verify_qualification_attestation
from .errors import ConflictError, IdentityError, UnsupportedError, ValidationError
from .safety import (
    atomic_write_json,
    canonical_json_bytes,
    paths_overlap,
    read_json,
    sha256_bytes,
    sha256_file,
    validate_bounded_json,
    validate_identifier,
    validate_sha256,
)
from .subscription_profiles import (
    subscription_binding_environment,
    validate_subscription_launch_binding,
)


PAIR_MEMBER_SCHEMA = "puppet.grok-pair-member-source/v1"
CONTROL_SOURCE_SCHEMA = "puppet.grok-ordinary-control-source/v1"
NATIVE_VIEW_SCHEMA = "puppet.grok-native-view/v1"
TERMINAL_QUALIFICATION_SCHEMA = "puppet.grok-regular-qualification/v1"
MATCHED_CONTROL_SCHEMA = "puppet.grok-matched-control-attestation/v2"
RUNTIME_VECTOR_SCHEMA = "puppet.grok-runtime-vector/v1"
TREE_HALT_SCHEMA = "puppet.grok-standalone-tree-halt/v1"
NATIVE_VIEW_NAME = "grok-native-view.json"
GROK_NATIVE_TRIGGER = "Follow the active workspace rules and complete their bounded task."
GROK_NATIVE_TRIGGER_SHA256 = sha256_bytes(
    (GROK_NATIVE_TRIGGER + "\n").encode("utf-8")
)

_PROCESS_FIELDS = {
    "identity_version",
    "pid",
    "start",
    "kernel_birth_id",
    "command",
    "executable_path",
    "device",
    "inode",
}
_PAIR_MEMBER_FIELDS = {
    "schema",
    "target",
    "role",
    "positive_receipt",
    "descriptor_sha256",
    "runtime_vector",
    "instruction_artifact",
    "ordinary_absence_sha256",
    "ordinary_instruction_absent",
    "qualification_authorized",
}
_CONTROL_SOURCE_FIELDS = {
    "schema",
    "target",
    "positive_receipt",
    "run_id",
    "controller",
    "campaign_id",
    "goal_fingerprint",
    "subscription_profile_sha256",
    "yolo_mapping_sha256",
    "descriptor_sha256",
    "runtime_vector_sha256",
    "receipt_attestation_sequence",
}
_RUNTIME_VECTOR_FIELDS = {
    "schema",
    "cwd",
    "leader_socket",
    "session_uuid",
    "argv_sha256",
    "closed_env_sha256",
    "profile_root",
    "vector_sha256",
}
_NATIVE_VIEW_FIELDS = {
    "schema",
    "target",
    "run_id",
    "session",
    "tmux_identity_sha256",
    "target_process_sha256",
    "attach_argv_sha256",
    "viewer",
    "read_only",
    "attached",
    "detached",
    "target_alive_after_detach",
    "body_capture_performed",
    "raw_retained",
}
_TREE_HALT_FIELDS = {
    "schema",
    "target",
    "run_id",
    "session",
    "root_process_sha256",
    "descendants_sha256",
    "ancestry_sha256",
    "protected_baseline_sha256",
    "protected_terminal_sha256",
    "halt_receipt_sha256",
    "signal",
    "cleanup_scope",
    "complete_tree_stopped",
    "protected_baseline_equal",
    "raw_retained",
}


def _canonical_file(path: Path | str, label: str, *, maximum: int = 131072) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        raise ValidationError("%s path must be absolute" % label)
    if candidate.is_symlink() or not candidate.is_file():
        raise ValidationError("%s is unavailable or a symlink" % label)
    resolved = candidate.resolve(strict=True)
    if resolved != candidate:
        raise IdentityError("%s path is not canonical" % label)
    if resolved.stat().st_size > maximum:
        raise ValidationError("%s exceeds its size bound" % label)
    return resolved


def _canonical_directory(path: Path | str, label: str) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        raise ValidationError("%s path must be absolute" % label)
    if candidate.is_symlink() or not candidate.is_dir():
        raise ValidationError("%s is unavailable or a symlink" % label)
    resolved = candidate.resolve(strict=True)
    if resolved != candidate:
        raise IdentityError("%s path is not canonical" % label)
    return resolved


def _reference(path: Path | str, label: str, *, maximum: int = 131072) -> Dict[str, str]:
    candidate = _canonical_file(path, label, maximum=maximum)
    return {
        "path": str(candidate),
        "sha256": sha256_file(candidate, max_bytes=maximum),
    }


def _load_reference(
    value: Any, label: str, *, maximum: int = 131072
) -> tuple[Path, Dict[str, Any]]:
    if not isinstance(value, Mapping) or set(value) != {"path", "sha256"}:
        raise ValidationError("%s reference fields are invalid" % label)
    path = _canonical_file(value.get("path"), label, maximum=maximum)
    digest = validate_sha256(value.get("sha256"), "%s fingerprint" % label)
    if sha256_file(path, max_bytes=maximum) != digest:
        raise IdentityError("%s reference changed" % label)
    return path, read_json(path, max_bytes=maximum, reject_sensitive_fields=True)


def _uuid4(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise ValidationError("%s is not a UUIDv4" % label)
    try:
        parsed = uuid.UUID(value)
    except (AttributeError, ValueError) as exc:
        raise ValidationError("%s is not a UUIDv4" % label) from exc
    if parsed.version != 4 or str(parsed) != value:
        raise ValidationError("%s is not a canonical UUIDv4" % label)
    return value


def derive_grok_session_uuid(*, session: str, run_id: str) -> str:
    """Derive a stable UUIDv4-shaped identity from controller-owned run ids."""

    session = validate_identifier(session, "Grok session")
    run_id = validate_identifier(run_id, "Grok run id")
    raw = bytearray.fromhex(sha256_bytes(canonical_json_bytes([session, run_id]))[:32])
    raw[6] = (raw[6] & 0x0F) | 0x40
    raw[8] = (raw[8] & 0x3F) | 0x80
    return str(uuid.UUID(bytes=bytes(raw)))


def grok_puppet_rule_count(workspace_root: Path | str) -> int:
    """Count namespaced rule paths structurally without reading any body."""

    workspace = _canonical_directory(workspace_root, "Grok workspace")
    rules = workspace / ".grok" / "rules"
    if not rules.exists():
        return 0
    if rules.is_symlink() or not rules.is_dir():
        raise IdentityError("Grok rules root is not a real directory")
    count = 0
    for child in rules.iterdir():
        if child.name.startswith("puppet-") and child.name.endswith(".md"):
            if child.is_symlink() or not child.is_file():
                raise IdentityError("Grok namespaced rule is not a regular file")
            count += 1
    return count


def _normalized_profile(
    value: Any, *, expected_profile_root: Optional[Path | str] = None
) -> tuple[Dict[str, Any], Dict[str, str], Dict[str, str], Path]:
    binding = validate_subscription_launch_binding(
        value, expected_target="grok", require_logged_in=True
    )
    if binding["status"].get("default_model") != "grok-4.5":
        raise IdentityError(
            "Grok private profile does not report the qualified default model"
        )
    source, bindings, root = subscription_binding_environment(
        binding, expected_target="grok"
    )
    if expected_profile_root is not None:
        expected = _canonical_directory(expected_profile_root, "expected Grok profile")
        if root != expected:
            raise IdentityError("Grok private profile root changed")
    return binding, source, bindings, root


def build_grok_runtime_vector(
    *,
    base_argv: Sequence[str],
    subscription_binding: Mapping[str, Any],
    cwd: Path | str,
    leader_socket: Path | str,
    session_uuid: str,
) -> Dict[str, Any]:
    """Build the one admitted Grok vector from public profile binding only."""

    binding, source, bindings, profile_root = _normalized_profile(subscription_binding)
    workspace = _canonical_directory(cwd, "Grok runtime cwd")
    if paths_overlap(workspace, profile_root):
        raise IdentityError("Grok runtime cwd overlaps the private profile")
    socket = Path(leader_socket)
    if not socket.is_absolute() or os.path.normpath(str(socket)) != str(socket):
        raise ValidationError("Grok leader socket path is not canonical")
    if socket.exists() or socket.is_symlink():
        raise ConflictError("Grok leader socket path is not new")
    socket_parent = _canonical_directory(socket.parent, "Grok leader socket parent")
    try:
        socket_parent.relative_to(profile_root)
    except ValueError as exc:
        raise IdentityError(
            "Grok leader socket is outside a private profile child"
        ) from exc
    if socket_parent == profile_root:
        raise IdentityError("Grok leader socket is outside a private profile child")
    if len(os.fsencode(str(socket))) > 100:
        raise ValidationError("Grok leader socket path exceeds the safe bound")
    target_uuid = _uuid4(session_uuid, "Grok runtime session id")
    argv = list(base_argv)
    if (
        len(argv) != 4
        or not all(isinstance(item, str) and item for item in argv)
        or argv[1:] != ["--always-approve", "--sandbox", "off"]
        or "--model" in argv
        or "--reasoning-effort" in argv
        or any(
            selector in argv
            for selector in (
                "--no-leader",
                "--trust",
                "--cwd",
                "--leader-socket",
                "--session-id",
            )
        )
    ):
        raise IdentityError("Grok base regular argv is not exact")
    argv.extend(
        [
            "--no-leader",
            "--trust",
            "--cwd",
            str(workspace),
            "--leader-socket",
            str(socket),
            "--session-id",
            target_uuid,
        ]
    )
    environment = {**source, **bindings}
    if (
        environment.get("HOME") != binding["directory_identities"]["home"]["path"]
        or environment.get("GROK_HOME")
        != binding["directory_identities"]["config"]["path"]
        or environment.get("GROK_DISABLE_AUTOUPDATER") != "true"
    ):
        raise IdentityError("Grok runtime vector is not the private profile context")
    core = {
        "schema": RUNTIME_VECTOR_SCHEMA,
        "cwd": str(workspace),
        "leader_socket": str(socket),
        "session_uuid": target_uuid,
        "argv_sha256": sha256_bytes(canonical_json_bytes(argv)),
        "closed_env_sha256": sha256_bytes(canonical_json_bytes(environment)),
        "profile_root": str(profile_root),
    }
    core["vector_sha256"] = sha256_bytes(canonical_json_bytes(core))
    return {
        "argv": argv,
        "environment": environment,
        "record": core,
        "profile": binding,
    }


def validate_grok_runtime_vector(
    value: Any,
    *,
    launch_plan: Mapping[str, Any],
    subscription_binding: Mapping[str, Any],
) -> Dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _RUNTIME_VECTOR_FIELDS:
        raise ValidationError("Grok runtime vector fields are invalid")
    result = dict(value)
    if result.get("schema") != RUNTIME_VECTOR_SCHEMA:
        raise ValidationError("unsupported Grok runtime vector schema")
    supplied = validate_sha256(result.pop("vector_sha256"), "Grok runtime vector")
    if sha256_bytes(canonical_json_bytes(result)) != supplied:
        raise IdentityError("Grok runtime vector fingerprint changed")
    result["vector_sha256"] = supplied
    _, source, bindings, profile_root = _normalized_profile(subscription_binding)
    if result["profile_root"] != str(profile_root):
        raise IdentityError("Grok runtime vector profile changed")
    runtime_cwd = _canonical_directory(result.get("cwd"), "Grok runtime cwd")
    if (
        launch_plan.get("cwd") != str(runtime_cwd)
        or paths_overlap(runtime_cwd, profile_root)
    ):
        raise IdentityError("Grok runtime vector cwd changed")
    argv = launch_plan.get("argv")
    environment = launch_plan.get("launch_identity")
    if (
        not isinstance(argv, list)
        or sha256_bytes(canonical_json_bytes(argv)) != result.get("argv_sha256")
        or argv[-8:]
        != [
            "--no-leader",
            "--trust",
            "--cwd",
            result["cwd"],
            "--leader-socket",
            result["leader_socket"],
            "--session-id",
            result["session_uuid"],
        ]
        or "--model" in argv
        or "--reasoning-effort" in argv
    ):
        raise IdentityError("Grok runtime launch argv differs from its vector")
    _uuid4(result["session_uuid"], "Grok runtime session id")
    socket = Path(result["leader_socket"])
    if (
        not socket.is_absolute()
        or os.path.normpath(str(socket)) != str(socket)
        or len(os.fsencode(str(socket))) > 100
        or socket.exists()
        or socket.is_symlink()
    ):
        raise IdentityError("Grok runtime leader socket escaped its profile")
    socket_parent = _canonical_directory(
        socket.parent, "Grok runtime leader socket parent"
    )
    try:
        socket_parent.relative_to(profile_root)
    except ValueError as exc:
        raise IdentityError("Grok runtime leader socket escaped its profile") from exc
    if socket_parent == profile_root:
        raise IdentityError("Grok runtime leader socket escaped its profile")
    expected_environment = {**source, **bindings}
    environment_names = sorted(expected_environment)
    launch_environment_sha = sha256_bytes(
        canonical_json_bytes(
            [(name, expected_environment[name]) for name in environment_names]
        )
    )
    if (
        not isinstance(environment, Mapping)
        or environment.get("env_names") != environment_names
        or environment.get("env_fingerprint") != launch_environment_sha
        or result.get("closed_env_sha256")
        != sha256_bytes(canonical_json_bytes(expected_environment))
    ):
        raise IdentityError("Grok runtime closed environment changed")
    return result


def _attestation_sequence(receipt: Mapping[str, Any], label: str) -> int:
    attestation = receipt.get("controller_attestation")
    sequence = (
        attestation.get("ledger_sequence")
        if isinstance(attestation, Mapping)
        else None
    )
    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence <= 0:
        raise ValidationError("%s attestation sequence is invalid" % label)
    return sequence


def build_grok_control_source(
    positive_receipt_path: Path | str,
    *,
    authority_root: Optional[Path] = None,
    current_manifest: Optional[Any] = None,
    _verify_receipt_fn: Optional[Callable[..., Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Bind an ordinary run to one already terminal positive run."""

    from .adapter_manifest import verify_qualification_receipt

    path = _canonical_file(positive_receipt_path, "positive Grok receipt")
    verifier = _verify_receipt_fn or verify_qualification_receipt
    positive = verifier(
        path,
        _authority_root=authority_root,
        _current_manifest=current_manifest,
    )
    member = validate_grok_pair_member_source(positive.get("grok_pairing"))
    if (
        positive.get("target") != "grok"
        or member["role"] != "positive"
        or positive.get("workspace_isolation") is not None
        or positive.get("plane_activation") is not None
    ):
        raise UnsupportedError("Grok control source requires one positive pair member")
    return {
        "schema": CONTROL_SOURCE_SCHEMA,
        "target": "grok",
        "positive_receipt": _reference(path, "positive Grok receipt"),
        "run_id": positive["run_id"],
        "controller": positive["controller"],
        "campaign_id": positive["campaign_id"],
        "goal_fingerprint": positive["goal_fingerprint"],
        "subscription_profile_sha256": positive["subscription_profile_sha256"],
        "yolo_mapping_sha256": positive["yolo_mapping_sha256"],
        "descriptor_sha256": member["descriptor_sha256"],
        "runtime_vector_sha256": member["runtime_vector"]["vector_sha256"],
        "receipt_attestation_sequence": _attestation_sequence(
            positive, "positive Grok receipt"
        ),
    }


def validate_grok_control_source(value: Any) -> Dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _CONTROL_SOURCE_FIELDS:
        raise ValidationError("Grok control source fields are invalid")
    result = dict(value)
    if result.get("schema") != CONTROL_SOURCE_SCHEMA or result.get("target") != "grok":
        raise ValidationError("unsupported Grok control source schema")
    for name in ("run_id", "controller", "campaign_id"):
        validate_identifier(result.get(name), "Grok control " + name.replace("_", " "))
    for name in (
        "goal_fingerprint",
        "subscription_profile_sha256",
        "yolo_mapping_sha256",
        "descriptor_sha256",
        "runtime_vector_sha256",
    ):
        validate_sha256(result.get(name), "Grok control " + name.replace("_", " "))
    if (
        isinstance(result.get("receipt_attestation_sequence"), bool)
        or not isinstance(result.get("receipt_attestation_sequence"), int)
        or result["receipt_attestation_sequence"] <= 0
    ):
        raise ValidationError("Grok control attestation sequence is invalid")
    _load_reference(result["positive_receipt"], "positive Grok receipt")
    return result


def build_grok_pair_member_source(
    *,
    role: str,
    runtime_vector: Mapping[str, Any],
    descriptor_sha256: Optional[str] = None,
    positive_receipt_path: Optional[Path | str] = None,
    instruction_artifact: Optional[Mapping[str, str]] = None,
    ordinary_absence_sha256: Optional[str] = None,
    ordinary_instruction_absent: bool,
) -> Dict[str, Any]:
    if role not in {"positive", "ordinary_control"}:
        raise ValidationError("Grok pair-member role is invalid")
    if not isinstance(runtime_vector, Mapping):
        raise ValidationError("Grok pair-member runtime vector is invalid")
    vector = dict(runtime_vector)
    validate_sha256(vector.get("vector_sha256"), "Grok runtime vector")
    if role == "positive":
        descriptor = validate_sha256(descriptor_sha256, "Grok positive descriptor")
        positive_ref = None
        if not isinstance(instruction_artifact, Mapping) or set(
            instruction_artifact
        ) != {"relative_path", "sha256"}:
            raise ValidationError("Grok positive instruction artifact is invalid")
        validate_sha256(instruction_artifact.get("sha256"), "Grok instruction artifact")
        if ordinary_instruction_absent is not False:
            raise ValidationError("Grok positive member cannot claim ordinary absence")
        if ordinary_absence_sha256 is not None:
            raise ValidationError("Grok positive member carries ordinary absence proof")
    else:
        if descriptor_sha256 is not None or instruction_artifact is not None:
            raise ValidationError("Grok ordinary member carries positive instruction data")
        if positive_receipt_path is None:
            raise ValidationError("Grok ordinary member lacks its positive source")
        positive_ref = _reference(
            positive_receipt_path, "positive Grok receipt"
        )
        descriptor = None
        if ordinary_instruction_absent is not True:
            raise ValidationError("Grok ordinary member lacks instruction absence")
        ordinary_absence_sha256 = validate_sha256(
            ordinary_absence_sha256, "Grok ordinary absence proof"
        )
    value = {
        "schema": PAIR_MEMBER_SCHEMA,
        "target": "grok",
        "role": role,
        "positive_receipt": positive_ref,
        "descriptor_sha256": descriptor,
        "runtime_vector": vector,
        "instruction_artifact": (
            dict(instruction_artifact) if instruction_artifact is not None else None
        ),
        "ordinary_absence_sha256": ordinary_absence_sha256,
        "ordinary_instruction_absent": ordinary_instruction_absent,
        "qualification_authorized": False,
    }
    return validate_grok_pair_member_source(value)


def validate_grok_pair_member_source(value: Any) -> Dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _PAIR_MEMBER_FIELDS:
        raise ValidationError("Grok pair-member source fields are invalid")
    result = json.loads(canonical_json_bytes(dict(value)).decode("utf-8"))
    if (
        result.get("schema") != PAIR_MEMBER_SCHEMA
        or result.get("target") != "grok"
        or result.get("role") not in {"positive", "ordinary_control"}
        or result.get("qualification_authorized") is not False
        or not isinstance(result.get("runtime_vector"), dict)
        or set(result["runtime_vector"]) != _RUNTIME_VECTOR_FIELDS
    ):
        raise ValidationError("Grok pair-member source is invalid")
    validate_sha256(
        result["runtime_vector"].get("vector_sha256"), "Grok runtime vector"
    )
    if result["role"] == "positive":
        validate_sha256(result.get("descriptor_sha256"), "Grok positive descriptor")
        artifact = result.get("instruction_artifact")
        if (
            result.get("positive_receipt") is not None
            or result.get("ordinary_instruction_absent") is not False
            or result.get("ordinary_absence_sha256") is not None
            or not isinstance(artifact, dict)
            or set(artifact) != {"relative_path", "sha256"}
        ):
            raise ValidationError("Grok positive pair-member source is invalid")
        validate_sha256(artifact.get("sha256"), "Grok instruction artifact")
    else:
        if (
            result.get("descriptor_sha256") is not None
            or result.get("instruction_artifact") is not None
            or result.get("ordinary_instruction_absent") is not True
        ):
            raise ValidationError("Grok ordinary pair-member source is invalid")
        validate_sha256(
            result.get("ordinary_absence_sha256"), "Grok ordinary absence proof"
        )
        _load_reference(result.get("positive_receipt"), "positive Grok receipt")
    validate_bounded_json(
        result,
        max_depth=6,
        max_items=96,
        max_string=4096,
        reject_sensitive_fields=True,
    )
    return result


def record_grok_native_view(
    *,
    run_root: Path,
    timeout: float = 120.0,
    poll_interval: float = 0.1,
    _tmux_factory: Optional[Callable[[Path], Any]] = None,
    _process_birth_fn: Optional[Callable[[int], Dict[str, Any]]] = None,
    _sleep_fn: Callable[[float], None] = time.sleep,
    _monotonic_fn: Callable[[], float] = time.monotonic,
) -> Dict[str, Any]:
    """Observe one real read-only tmux attach/detach without pane capture."""

    from .campaign import process_birth_identity
    from .tmux import TmuxController

    if timeout <= 0 or timeout > 600:
        raise ValidationError("Grok native-view timeout is invalid")
    root = _canonical_directory(run_root, "Grok probe run root")
    output = root / NATIVE_VIEW_NAME
    if output.exists() or output.is_symlink():
        raise ConflictError("Grok native-view receipt already exists")
    state = read_json(
        root / "state.json", max_bytes=131072, reject_sensitive_fields=True
    )
    evidence = read_json(
        root / "evidence.json", max_bytes=131072, reject_sensitive_fields=True
    )
    tmux_record = evidence.get("tmux")
    process = evidence.get("process")
    if (
        state.get("target") != "grok"
        or evidence.get("target") != "grok"
        or state.get("run_id") != evidence.get("run_id")
        or state.get("phase")
        not in {"ready_validated", "followup_validated", "accepted_awaiting_halt"}
        or not isinstance(state.get("attach_command"), str)
        or not isinstance(tmux_record, dict)
        or not isinstance(process, dict)
        or set(process) != _PROCESS_FIELDS
    ):
        raise ValidationError("Grok probe is not live for native-view observation")
    factory = _tmux_factory or TmuxController
    birth = _process_birth_fn or process_birth_identity
    controller = factory(root / "tmux-authority")
    socket = Path(tmux_record["socket"])
    session = tmux_record["session"]
    server = tmux_record["server_identity"]
    attach_argv = controller.attach_argv(
        socket=socket,
        session=session,
        pane=tmux_record["target_id"],
        server_identity=server,
    )
    if controller.viewer_clients(
        socket=socket, session=session, server_identity=server
    ):
        raise ConflictError("Grok native-view observation requires no prior client")
    deadline = _monotonic_fn() + timeout
    viewer: Optional[Dict[str, Any]] = None
    while _monotonic_fn() < deadline:
        clients = controller.viewer_clients(
            socket=socket, session=session, server_identity=server
        )
        if clients:
            if len(clients) != 1 or clients[0].get("read_only") is not True:
                raise IdentityError("Grok native viewer is not one read-only client")
            viewer = dict(clients[0])
            viewer_process = birth(viewer["pid"])
            binary = tmux_record["tmux_binary_identity"]
            if (
                viewer.get("session") != session
                or not isinstance(viewer.get("tty"), str)
                or not viewer["tty"].startswith("/dev/")
                or viewer_process.get("executable_path") != binary["path"]
                or viewer_process.get("device") != binary["device"]
                or viewer_process.get("inode") != binary["inode"]
            ):
                raise IdentityError("Grok native viewer process identity is invalid")
            break
        _sleep_fn(poll_interval)
    if viewer is None:
        raise UnsupportedError("Grok native viewer attachment was not observed")
    while _monotonic_fn() < deadline:
        clients = controller.viewer_clients(
            socket=socket, session=session, server_identity=server
        )
        if not clients:
            break
        if clients != [viewer]:
            raise IdentityError("Grok native viewer population changed")
        _sleep_fn(poll_interval)
    else:
        raise UnsupportedError("Grok native viewer detach was not observed")
    if birth(process["pid"]) != process:
        raise IdentityError("Grok target changed during native-view observation")
    result = {
        "schema": NATIVE_VIEW_SCHEMA,
        "target": "grok",
        "run_id": state["run_id"],
        "session": session,
        "tmux_identity_sha256": sha256_bytes(canonical_json_bytes(tmux_record)),
        "target_process_sha256": sha256_bytes(canonical_json_bytes(process)),
        "attach_argv_sha256": sha256_bytes(canonical_json_bytes(attach_argv)),
        "viewer": viewer,
        "read_only": True,
        "attached": True,
        "detached": True,
        "target_alive_after_detach": True,
        "body_capture_performed": False,
        "raw_retained": False,
    }
    validate_grok_native_view(
        result,
        receipt={"run_id": state["run_id"]},
        session=session,
        evidence=evidence,
        attach_argv=attach_argv,
    )
    atomic_write_json(output, result)
    return result


def await_grok_native_view(
    *,
    run_root: Path,
    receipt: Mapping[str, Any],
    session: str,
    evidence: Mapping[str, Any],
    attach_argv: Sequence[str],
    runtime_guard: Callable[[], None],
    timeout: float = 120.0,
    poll_interval: float = 0.1,
    _sleep_fn: Callable[[float], None] = time.sleep,
    _monotonic_fn: Callable[[], float] = time.monotonic,
) -> Dict[str, Any]:
    """Hold a live Grok probe until its structural native-view proof lands."""

    if timeout <= 0 or timeout > 600:
        raise ValidationError("Grok native-view rendezvous timeout is invalid")
    if poll_interval <= 0 or poll_interval > 5:
        raise ValidationError("Grok native-view rendezvous interval is invalid")
    root = _canonical_directory(run_root, "Grok probe run root")
    output = root / NATIVE_VIEW_NAME
    deadline = _monotonic_fn() + timeout
    while True:
        runtime_guard()
        if output.is_symlink():
            raise IdentityError("Grok native-view receipt cannot be a symlink")
        if output.exists():
            value = read_json(
                output,
                max_bytes=65536,
                reject_sensitive_fields=True,
            )
            result = validate_grok_native_view(
                value,
                receipt=receipt,
                session=session,
                evidence=evidence,
                attach_argv=attach_argv,
            )
            runtime_guard()
            return result
        if _monotonic_fn() >= deadline:
            raise UnsupportedError(
                "Grok native-view receipt was not observed before the live deadline"
            )
        _sleep_fn(poll_interval)


def validate_grok_native_view(
    value: Any,
    *,
    receipt: Mapping[str, Any],
    session: str,
    evidence: Mapping[str, Any],
    attach_argv: Sequence[str],
) -> Dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _NATIVE_VIEW_FIELDS:
        raise ValidationError("Grok native-view fields are invalid")
    result = dict(value)
    viewer = result.get("viewer")
    if (
        result.get("schema") != NATIVE_VIEW_SCHEMA
        or result.get("target") != "grok"
        or result.get("run_id") != receipt.get("run_id")
        or result.get("session") != session
        or result.get("tmux_identity_sha256")
        != sha256_bytes(canonical_json_bytes(evidence.get("tmux")))
        or result.get("target_process_sha256")
        != sha256_bytes(canonical_json_bytes(evidence.get("process")))
        or result.get("attach_argv_sha256")
        != sha256_bytes(canonical_json_bytes(list(attach_argv)))
        or not isinstance(viewer, dict)
        or set(viewer) != {"pid", "tty", "read_only", "session"}
        or isinstance(viewer.get("pid"), bool)
        or not isinstance(viewer.get("pid"), int)
        or viewer["pid"] <= 1
        or not isinstance(viewer.get("tty"), str)
        or not viewer["tty"].startswith("/dev/")
        or viewer.get("read_only") is not True
        or viewer.get("session") != session
        or any(
            result.get(name) is not expected
            for name, expected in (
                ("read_only", True),
                ("attached", True),
                ("detached", True),
                ("target_alive_after_detach", True),
                ("body_capture_performed", False),
                ("raw_retained", False),
            )
        )
    ):
        raise IdentityError("Grok native-view observation does not join its run")
    return result


def _receipt_artifacts(
    receipt_path: Path, receipt: Mapping[str, Any]
) -> Dict[str, Any]:
    from .adapter_manifest import _qualification_artifacts
    from .launch import validate_admitted_launch_plan

    paths = _qualification_artifacts(receipt_path, dict(receipt))
    state = read_json(
        receipt_path.parent / "state.json",
        max_bytes=131072,
        reject_sensitive_fields=True,
    )
    session = validate_identifier(state.get("session"), "Grok probe session")
    if state.get("run_id") != receipt.get("run_id"):
        raise IdentityError("Grok probe state changed")
    launch = validate_admitted_launch_plan(
        read_json(paths["launch_plan"], max_bytes=131072, reject_sensitive_fields=True),
        expected_target="grok",
        expected_session=session,
        expected_run_id=receipt["run_id"],
    )
    return {
        "paths": paths,
        "state": state,
        "session": session,
        "launch": launch,
        "profile": read_json(
            paths["subscription_profile"],
            max_bytes=131072,
            reject_sensitive_fields=True,
        ),
        "evidence": read_json(
            paths["evidence"], max_bytes=131072, reject_sensitive_fields=True
        ),
        "halt": read_json(
            paths["halt"], max_bytes=65536, reject_sensitive_fields=True
        ),
    }


def verify_grok_pair_member_artifacts(
    *,
    receipt: Mapping[str, Any],
    receipt_path: Path,
    artifacts: Mapping[str, Path],
    launch_plan: Mapping[str, Any],
    subscription_binding: Mapping[str, Any],
) -> Dict[str, Any]:
    """Join one generic probe member to its immutable body-free artifacts."""

    member = validate_grok_pair_member_source(receipt.get("grok_pairing"))
    validate_grok_runtime_vector(
        member["runtime_vector"],
        launch_plan=launch_plan,
        subscription_binding=subscription_binding,
    )
    if receipt.get("target") != "grok" or receipt.get("workspace_isolation") is not None:
        raise ValidationError("Grok pair member cannot carry terminal qualification")
    if member["role"] == "positive":
        required = {
            "workspace_descriptor",
            "controller_contract",
            "workspace_materialization",
            "workspace_rollback",
        }
        if not required <= set(artifacts) or "grok_ordinary_absence" in artifacts:
            raise ValidationError("Grok positive member proof references are incomplete")
        descriptor = read_json(
            artifacts["workspace_descriptor"],
            max_bytes=131072,
            reject_sensitive_fields=True,
        )
        materialization = read_json(
            artifacts["workspace_materialization"],
            max_bytes=131072,
            reject_sensitive_fields=True,
        )
        rollback = read_json(
            artifacts["workspace_rollback"],
            max_bytes=131072,
            reject_sensitive_fields=True,
        )
        from .grok_workspace_plane import (
            validate_grok_entry_descriptor,
            validate_grok_workspace_materialization_receipt,
            validate_grok_workspace_rollback_receipt,
        )

        descriptor = validate_grok_entry_descriptor(
            descriptor,
            expected_controller=receipt["controller"],
            expected_campaign_id=receipt["campaign_id"],
            expected_goal_fingerprint=receipt["goal_fingerprint"],
            expected_executable_sha256=receipt["executable_fingerprint"],
            expected_subscription_profile_root=subscription_binding["profile_root"],
        )
        materialization = validate_grok_workspace_materialization_receipt(
            materialization,
            expected_workspace_root=descriptor["workspace_root"],
            expected_relative_path=descriptor["artifact_relative_path"],
            expected_content_sha256=member["instruction_artifact"]["sha256"],
            expected_descriptor_sha256=descriptor["descriptor_sha256"],
        )
        rollback = validate_grok_workspace_rollback_receipt(
            rollback,
            materialization_receipt=materialization,
        )
        if (
            descriptor.get("descriptor_sha256") != member["descriptor_sha256"]
            or materialization.get("relative_path")
            != member["instruction_artifact"]["relative_path"]
            or materialization.get("content_sha256")
            != member["instruction_artifact"]["sha256"]
            or materialization.get("created") is not True
            or materialization.get("launch_authorized") is not False
            or rollback.get("expected_content_sha256")
            != materialization.get("content_sha256")
            or rollback.get("absent_after") is not True
            or rollback.get("qualification_authorized") is not False
        ):
            raise IdentityError("Grok positive member artifacts changed")
    else:
        if any(
            name in artifacts
            for name in (
                "workspace_descriptor",
                "workspace_materialization",
                "workspace_rollback",
            )
        ) or "grok_ordinary_absence" not in artifacts:
            raise ValidationError("Grok ordinary member proof references are invalid")
        absence = read_json(
            artifacts["grok_ordinary_absence"],
            max_bytes=65536,
            reject_sensitive_fields=True,
        )
        if (
            set(absence)
            != {
                "schema",
                "target",
                "run_id",
                "workspace_root",
                "puppet_rule_count_before",
                "puppet_rule_count_after",
                "ordinary_instruction_absent",
                "raw_retained",
            }
            or absence.get("schema") != "puppet.grok-ordinary-absence/v1"
            or absence.get("target") != "grok"
            or absence.get("run_id") != receipt.get("run_id")
            or absence.get("workspace_root") != launch_plan.get("cwd")
            or absence.get("puppet_rule_count_before") != 0
            or absence.get("puppet_rule_count_after") != 0
            or absence.get("ordinary_instruction_absent") is not True
            or absence.get("raw_retained") is not False
            or sha256_file(artifacts["grok_ordinary_absence"], max_bytes=65536)
            != member["ordinary_absence_sha256"]
        ):
            raise IdentityError("Grok ordinary absence artifact changed")
        control = validate_grok_control_source(receipt.get("grok_control_source"))
        positive_path, _ = _load_reference(
            control["positive_receipt"], "positive Grok receipt"
        )
        if (
            member["positive_receipt"] != control["positive_receipt"]
            or positive_path == receipt_path
            or control["subscription_profile_sha256"]
            != receipt["subscription_profile_sha256"]
            or control["yolo_mapping_sha256"] != receipt["yolo_mapping_sha256"]
        ):
            raise IdentityError("Grok ordinary member positive source changed")
    return member


def _native_attach_argv(artifacts: Mapping[str, Any]) -> list[str]:
    tmux = artifacts["evidence"].get("tmux")
    if not isinstance(tmux, Mapping):
        raise ValidationError("Grok tmux identity is unavailable")
    binary = tmux.get("tmux_binary_identity")
    return [
        binary["path"],
        "-f",
        os.devnull,
        "-S",
        tmux["socket"],
        "attach-session",
        "-r",
        "-E",
        "-t",
        tmux["session"],
    ]


def _tree_halt(
    *,
    receipt: Mapping[str, Any],
    artifacts: Mapping[str, Any],
) -> Dict[str, Any]:
    evidence = artifacts["evidence"]
    halt = artifacts["halt"]
    before = evidence.get("active_target_processes_before_launch")
    after = evidence.get("active_target_processes_after_halt")
    descendants = evidence.get("observed_target_descendants")
    if (
        not isinstance(before, list)
        or not isinstance(after, list)
        or before != after
        or not isinstance(descendants, list)
        or halt.get("signal") != "exact_registered_pid_sigint"
        or halt.get("cleanup_scope") != "exact_new_target_only"
        or halt.get("stopped") is not True
        or halt.get("target_pid") != evidence.get("process", {}).get("pid")
    ):
        raise IdentityError("Grok standalone tree halt is incomplete")
    ancestry = [
        item.get("ancestry_chain")
        for item in descendants
        if isinstance(item, Mapping)
    ]
    root_process = evidence.get("process")
    if (
        len(ancestry) != len(descendants)
        or not isinstance(root_process, Mapping)
        or set(root_process) != _PROCESS_FIELDS
    ):
        raise ValidationError("Grok descendant ancestry evidence is incomplete")
    descendant_pids: set[int] = set()
    for item, chain in zip(descendants, ancestry):
        if (
            set(item) != {"process", "ancestry_chain"}
            or not isinstance(item.get("process"), Mapping)
            or set(item["process"]) != _PROCESS_FIELDS
            or not isinstance(chain, list)
            or not 2 <= len(chain) <= 65
            or any(
                not isinstance(node, Mapping)
                or set(node) != {"process", "parent_pid"}
                or not isinstance(node.get("process"), Mapping)
                or set(node["process"]) != _PROCESS_FIELDS
                or isinstance(node.get("parent_pid"), bool)
                or not isinstance(node.get("parent_pid"), int)
                or node["parent_pid"] < 0
                for node in chain
            )
            or chain[0]["process"] != item["process"]
            or chain[-1]["process"] != root_process
            or any(
                child["parent_pid"] != parent["process"]["pid"]
                for child, parent in zip(chain, chain[1:])
            )
        ):
            raise ValidationError("Grok descendant ancestry evidence is malformed")
        pids = [node["process"]["pid"] for node in chain]
        descendant_pid = item["process"]["pid"]
        if (
            len(pids) != len(set(pids))
            or descendant_pid == root_process["pid"]
            or descendant_pid in descendant_pids
        ):
            raise IdentityError("Grok descendant ancestry identity is ambiguous")
        descendant_pids.add(descendant_pid)
    value = {
        "schema": TREE_HALT_SCHEMA,
        "target": "grok",
        "run_id": receipt["run_id"],
        "session": artifacts["session"],
        "root_process_sha256": sha256_bytes(
            canonical_json_bytes(evidence["process"])
        ),
        "descendants_sha256": sha256_bytes(canonical_json_bytes(descendants)),
        "ancestry_sha256": sha256_bytes(canonical_json_bytes(ancestry)),
        "protected_baseline_sha256": sha256_bytes(canonical_json_bytes(before)),
        "protected_terminal_sha256": sha256_bytes(canonical_json_bytes(after)),
        "halt_receipt_sha256": receipt["halt_receipt_sha256"],
        "signal": halt["signal"],
        "cleanup_scope": halt["cleanup_scope"],
        "complete_tree_stopped": True,
        "protected_baseline_equal": True,
        "raw_retained": False,
    }
    if set(value) != _TREE_HALT_FIELDS:
        raise ValidationError("Grok tree-halt receipt fields are invalid")
    return value


def _pair_core(
    *,
    positive_path: Path,
    positive: Mapping[str, Any],
    ordinary_path: Path,
    ordinary: Mapping[str, Any],
    positive_view_path: Path,
    ordinary_view_path: Path,
    expected_profile_root: Path,
) -> Dict[str, Any]:
    from .adapter_manifest import PROBE_CAPABILITIES

    positive_member = validate_grok_pair_member_source(positive.get("grok_pairing"))
    ordinary_member = validate_grok_pair_member_source(ordinary.get("grok_pairing"))
    if positive_member["role"] != "positive" or ordinary_member["role"] != "ordinary_control":
        raise ValidationError("Grok pair roles are invalid")
    control_source = validate_grok_control_source(ordinary.get("grok_control_source"))
    expected_positive_ref = _reference(positive_path, "positive Grok receipt")
    if (
        ordinary_member["positive_receipt"] != expected_positive_ref
        or control_source["positive_receipt"] != expected_positive_ref
        or control_source["run_id"] != positive["run_id"]
        or control_source["descriptor_sha256"] != positive_member["descriptor_sha256"]
        or control_source["runtime_vector_sha256"]
        != positive_member["runtime_vector"]["vector_sha256"]
    ):
        raise IdentityError("Grok ordinary control was relinked")
    shared = (
        "target",
        "session_profile",
        "controller",
        "campaign_id",
        "goal_fingerprint",
        "executable_fingerprint",
        "execution_fingerprint",
        "version_fingerprint",
        "platform_fingerprint",
        "adapter_fingerprint",
        "protocol_fingerprint",
        "yolo_mapping_sha256",
        "subscription_profile_sha256",
        "instruction_policy_fingerprint",
        "capabilities",
    )
    if (
        positive.get("target") != "grok"
        or ordinary.get("target") != "grok"
        or positive.get("session_profile") != "regular"
        or ordinary.get("session_profile") != "regular"
        or positive.get("capabilities") != list(PROBE_CAPABILITIES)
        or ordinary.get("capabilities") != list(PROBE_CAPABILITIES)
        or any(positive.get(name) != ordinary.get(name) for name in shared)
        or positive["run_id"] == ordinary["run_id"]
        or positive["accepted_checkpoint_id"] == ordinary["accepted_checkpoint_id"]
        or _attestation_sequence(positive, "positive")
        >= _attestation_sequence(ordinary, "ordinary")
    ):
        raise IdentityError("Grok pair authority or sequence differs")
    positive_artifacts = _receipt_artifacts(positive_path, positive)
    ordinary_artifacts = _receipt_artifacts(ordinary_path, ordinary)
    profile_root = _canonical_directory(expected_profile_root, "Grok private profile")
    for artifacts in (positive_artifacts, ordinary_artifacts):
        binding, _, _, root = _normalized_profile(
            artifacts["profile"], expected_profile_root=profile_root
        )
        if binding["status"]["login_state"] != "logged_in" or root != profile_root:
            raise IdentityError("Grok pair is not subscription-backed")
    positive_vector = validate_grok_runtime_vector(
        positive_member["runtime_vector"],
        launch_plan=positive_artifacts["launch"],
        subscription_binding=positive_artifacts["profile"],
    )
    ordinary_vector = validate_grok_runtime_vector(
        ordinary_member["runtime_vector"],
        launch_plan=ordinary_artifacts["launch"],
        subscription_binding=ordinary_artifacts["profile"],
    )
    positive_evidence = positive_artifacts["evidence"]
    ordinary_evidence = ordinary_artifacts["evidence"]
    if (
        positive_vector["cwd"] == ordinary_vector["cwd"]
        or paths_overlap(Path(positive_vector["cwd"]), Path(ordinary_vector["cwd"]))
        or positive_vector["leader_socket"] == ordinary_vector["leader_socket"]
        or positive_vector["session_uuid"] == ordinary_vector["session_uuid"]
        or positive_artifacts["session"] == ordinary_artifacts["session"]
        or positive_evidence.get("process") == ordinary_evidence.get("process")
        or positive_evidence.get("tmux") == ordinary_evidence.get("tmux")
        or positive_evidence.get("tmux", {}).get("socket")
        == ordinary_evidence.get("tmux", {}).get("socket")
        or positive_evidence.get("active_target_processes_before_launch")
        != positive_evidence.get("active_target_processes_after_halt")
        or ordinary_evidence.get("active_target_processes_before_launch")
        != ordinary_evidence.get("active_target_processes_after_halt")
        or positive_evidence.get("active_target_processes_before_launch")
        != ordinary_evidence.get("active_target_processes_before_launch")
    ):
        raise IdentityError("Grok runtime pair identities or protected baseline differ")
    positive_view_ref = _reference(
        positive_view_path, "positive Grok native view", maximum=65536
    )
    ordinary_view_ref = _reference(
        ordinary_view_path, "ordinary Grok native view", maximum=65536
    )
    _, positive_view = _load_reference(
        positive_view_ref, "positive Grok native view", maximum=65536
    )
    _, ordinary_view = _load_reference(
        ordinary_view_ref, "ordinary Grok native view", maximum=65536
    )
    validate_grok_native_view(
        positive_view,
        receipt=positive,
        session=positive_artifacts["session"],
        evidence=positive_evidence,
        attach_argv=_native_attach_argv(positive_artifacts),
    )
    validate_grok_native_view(
        ordinary_view,
        receipt=ordinary,
        session=ordinary_artifacts["session"],
        evidence=ordinary_evidence,
        attach_argv=_native_attach_argv(ordinary_artifacts),
    )
    if positive_view["viewer"] == ordinary_view["viewer"]:
        raise IdentityError("Grok pair native viewers are not independent")
    positive_halt = _tree_halt(receipt=positive, artifacts=positive_artifacts)
    ordinary_halt = _tree_halt(receipt=ordinary, artifacts=ordinary_artifacts)
    positive_paths = positive_artifacts["paths"]
    ordinary_paths = ordinary_artifacts["paths"]
    if not {
        "workspace_descriptor",
        "workspace_materialization",
        "workspace_rollback",
    } <= set(positive_paths):
        raise ValidationError("Grok positive instruction proof is incomplete")
    if any(
        name in ordinary_paths
        for name in (
            "workspace_descriptor",
            "workspace_materialization",
            "workspace_rollback",
        )
    ):
        raise IdentityError("Grok ordinary control contains positive instruction proof")
    descriptor = read_json(
        positive_paths["workspace_descriptor"],
        max_bytes=131072,
        reject_sensitive_fields=True,
    )
    materialization = read_json(
        positive_paths["workspace_materialization"],
        max_bytes=131072,
        reject_sensitive_fields=True,
    )
    rollback = read_json(
        positive_paths["workspace_rollback"],
        max_bytes=131072,
        reject_sensitive_fields=True,
    )
    from .grok_workspace_plane import (
        validate_grok_workspace_materialization_receipt,
        validate_grok_workspace_rollback_receipt,
    )

    materialization = validate_grok_workspace_materialization_receipt(
        materialization,
        expected_workspace_root=descriptor["workspace_root"],
        expected_relative_path=descriptor["artifact_relative_path"],
        expected_content_sha256=positive_member["instruction_artifact"]["sha256"],
        expected_descriptor_sha256=descriptor["descriptor_sha256"],
    )
    rollback = validate_grok_workspace_rollback_receipt(
        rollback,
        materialization_receipt=materialization,
    )
    if (
        descriptor.get("descriptor_sha256") != positive_member["descriptor_sha256"]
        or materialization.get("content_sha256")
        != positive_member["instruction_artifact"]["sha256"]
        or materialization.get("relative_path")
        != positive_member["instruction_artifact"]["relative_path"]
        or materialization.get("created") is not True
        or rollback.get("expected_content_sha256")
        != materialization.get("content_sha256")
        or rollback.get("absent_after") is not True
        or ordinary_member["ordinary_instruction_absent"] is not True
    ):
        raise IdentityError("Grok positive consumption or rollback evidence changed")
    matched = {
        "schema": MATCHED_CONTROL_SCHEMA,
        "proof_strength": "paired_subscription_runtime",
        "positive_receipt": expected_positive_ref,
        "ordinary_control_receipt": _reference(
            ordinary_path, "ordinary Grok receipt"
        ),
        "positive_native_view": positive_view_ref,
        "ordinary_native_view": ordinary_view_ref,
        "positive_tree_halt": positive_halt,
        "ordinary_tree_halt": ordinary_halt,
        "positive_checkpoint_sha256": positive["accepted_checkpoint_id"],
        "ordinary_checkpoint_sha256": ordinary["accepted_checkpoint_id"],
        "positive_instruction_sha256": materialization["content_sha256"],
        "ordinary_instruction_absent": True,
        "protected_baseline_equal": True,
        "no_bleed_verified": True,
    }
    matched["attestation_sha256"] = sha256_bytes(canonical_json_bytes(matched))
    profile_status = positive_artifacts["profile"]["status"]
    core = {
        "schema": TERMINAL_QUALIFICATION_SCHEMA,
        "kind": "grok_regular_paired_runtime_qualification",
        "target": "grok",
        "run_id": "grok-pair-" + matched["attestation_sha256"][:32],
        "controller": positive["controller"],
        "campaign_id": positive["campaign_id"],
        "goal_fingerprint": positive["goal_fingerprint"],
        "session_profile": "regular",
        "executable_fingerprint": positive["executable_fingerprint"],
        "execution_fingerprint": positive["execution_fingerprint"],
        "version_fingerprint": positive["version_fingerprint"],
        "platform_fingerprint": positive["platform_fingerprint"],
        "adapter_fingerprint": positive["adapter_fingerprint"],
        "protocol_fingerprint": positive["protocol_fingerprint"],
        "yolo_mapping_sha256": positive["yolo_mapping_sha256"],
        "subscription_profile_sha256": positive["subscription_profile_sha256"],
        "instruction_policy_fingerprint": positive[
            "instruction_policy_fingerprint"
        ],
        "capabilities": list(PROBE_CAPABILITIES),
        "accepted_checkpoint_id": sha256_bytes(
            canonical_json_bytes(
                [
                    positive["accepted_checkpoint_id"],
                    ordinary["accepted_checkpoint_id"],
                ]
            )
        ),
        "acceptance_sha256": sha256_bytes(
            canonical_json_bytes(
                [positive["acceptance_sha256"], ordinary["acceptance_sha256"]]
            )
        ),
        "halt_receipt_sha256": sha256_bytes(
            canonical_json_bytes(
                [positive["halt_receipt_sha256"], ordinary["halt_receipt_sha256"]]
            )
        ),
        "private_profile_root": str(profile_root),
        "profile_status": {
            "login_state": profile_status["login_state"],
            "method": profile_status["method"],
            "default_model": profile_status["default_model"],
            "status_exit": profile_status["status_exit"],
            "raw_output_retained": profile_status["raw_output_retained"],
        },
        "positive_receipt": expected_positive_ref,
        "ordinary_control_receipt": _reference(
            ordinary_path, "ordinary Grok receipt"
        ),
        "matched_control": matched,
        "terminal_state": (
            "paired_runtime_verified_after_views_exact_tree_halts_and_positive_rollback"
        ),
        "qualification_authorized": True,
        "public_launch_authorized": True,
        "raw_retained": False,
    }
    return core


def _terminal_attestation_projection(core: Mapping[str, Any]) -> Dict[str, Any]:
    """Bind the terminal schema through the shared v5 controller ledger."""

    return {
        "schema_version": 5,
        "kind": "real_harness_conformance",
        "run_id": core["run_id"],
        "target": "grok",
        "controller": core["controller"],
        "campaign_id": core["campaign_id"],
        "goal_fingerprint": core["goal_fingerprint"],
        "executable_fingerprint": core["executable_fingerprint"],
        "execution_fingerprint": core["execution_fingerprint"],
        "platform_fingerprint": core["platform_fingerprint"],
        "adapter_fingerprint": core["adapter_fingerprint"],
        "protocol_fingerprint": core["protocol_fingerprint"],
        "yolo_mapping_sha256": core["yolo_mapping_sha256"],
        "launch_plan_sha256": sha256_bytes(canonical_json_bytes(dict(core))),
        "subscription_profile_sha256": core["subscription_profile_sha256"],
        "instruction_policy_fingerprint": core[
            "instruction_policy_fingerprint"
        ],
        "accepted_checkpoint_id": core["accepted_checkpoint_id"],
        "acceptance_sha256": core["acceptance_sha256"],
        "halt_receipt_sha256": core["halt_receipt_sha256"],
    }


def build_grok_terminal_qualification(
    *,
    positive_receipt_path: Path | str,
    ordinary_receipt_path: Path | str,
    positive_native_view_path: Path | str,
    ordinary_native_view_path: Path | str,
    private_profile_root: Path | str,
    authority_root: Optional[Path] = None,
    current_manifest: Optional[Any] = None,
    _verify_receipt_fn: Optional[Callable[..., Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Build the sole promotable Grok receipt from terminal source evidence."""

    from .adapter_manifest import verify_qualification_receipt

    positive_path = _canonical_file(positive_receipt_path, "positive Grok receipt")
    ordinary_path = _canonical_file(
        ordinary_receipt_path, "ordinary Grok receipt"
    )
    if positive_path == ordinary_path:
        raise IdentityError("Grok pair receipts must be distinct")
    verifier = _verify_receipt_fn or verify_qualification_receipt
    positive = verifier(
        positive_path,
        _authority_root=authority_root,
        _current_manifest=current_manifest,
    )
    ordinary = verifier(
        ordinary_path,
        _authority_root=authority_root,
        _current_manifest=current_manifest,
    )
    core = _pair_core(
        positive_path=positive_path,
        positive=positive,
        ordinary_path=ordinary_path,
        ordinary=ordinary,
        positive_view_path=_canonical_file(
            positive_native_view_path, "positive Grok native view", maximum=65536
        ),
        ordinary_view_path=_canonical_file(
            ordinary_native_view_path, "ordinary Grok native view", maximum=65536
        ),
        expected_profile_root=_canonical_directory(
            private_profile_root, "Grok private profile"
        ),
    )
    return {
        **core,
        "controller_attestation": attest_qualification(
            _terminal_attestation_projection(core),
            authority_root=authority_root,
        ),
    }


def verify_grok_terminal_qualification(
    path: Path | str,
    *,
    expected_private_profile_root: Path | str,
    authority_root: Optional[Path] = None,
    current_manifest: Optional[Any] = None,
    _verify_receipt_fn: Optional[Callable[..., Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Independently rebuild a terminal pair and reject stale/relinked inputs."""

    candidate = _canonical_file(path, "Grok terminal qualification")
    value = read_json(candidate, max_bytes=131072, reject_sensitive_fields=True)
    if not isinstance(value, dict):
        raise ValidationError("Grok terminal qualification root is invalid")
    required = {
        "schema",
        "kind",
        "target",
        "run_id",
        "controller",
        "campaign_id",
        "goal_fingerprint",
        "session_profile",
        "executable_fingerprint",
        "execution_fingerprint",
        "version_fingerprint",
        "platform_fingerprint",
        "adapter_fingerprint",
        "protocol_fingerprint",
        "yolo_mapping_sha256",
        "subscription_profile_sha256",
        "instruction_policy_fingerprint",
        "capabilities",
        "accepted_checkpoint_id",
        "acceptance_sha256",
        "halt_receipt_sha256",
        "private_profile_root",
        "profile_status",
        "positive_receipt",
        "ordinary_control_receipt",
        "matched_control",
        "terminal_state",
        "qualification_authorized",
        "public_launch_authorized",
        "raw_retained",
        "controller_attestation",
    }
    if set(value) != required:
        raise ValidationError("Grok terminal qualification fields are invalid")
    if (
        value.get("schema") != TERMINAL_QUALIFICATION_SCHEMA
        or value.get("kind") != "grok_regular_paired_runtime_qualification"
        or value.get("target") != "grok"
        or value.get("session_profile") != "regular"
        or value.get("terminal_state")
        != "paired_runtime_verified_after_views_exact_tree_halts_and_positive_rollback"
        or value.get("qualification_authorized") is not True
        or value.get("public_launch_authorized") is not True
        or value.get("raw_retained") is not False
    ):
        raise ValidationError("Grok terminal qualification state is invalid")
    core = dict(value)
    attestation = core.pop("controller_attestation")
    verify_qualification_attestation(
        _terminal_attestation_projection(core),
        attestation,
        authority_root=authority_root,
    )
    profile_root = _canonical_directory(
        value["private_profile_root"], "Grok private profile"
    )
    expected_profile = _canonical_directory(
        expected_private_profile_root, "expected Grok private profile"
    )
    if profile_root != expected_profile:
        raise IdentityError("Grok terminal private profile changed")
    positive_path, _ = _load_reference(
        value["positive_receipt"], "positive Grok receipt"
    )
    ordinary_path, _ = _load_reference(
        value["ordinary_control_receipt"], "ordinary Grok receipt"
    )
    matched = value.get("matched_control")
    if not isinstance(matched, Mapping):
        raise ValidationError("Grok matched-control attestation is invalid")
    positive_view_path, _ = _load_reference(
        matched.get("positive_native_view"),
        "positive Grok native view",
        maximum=65536,
    )
    ordinary_view_path, _ = _load_reference(
        matched.get("ordinary_native_view"),
        "ordinary Grok native view",
        maximum=65536,
    )
    from .adapter_manifest import verify_qualification_receipt

    verifier = _verify_receipt_fn or verify_qualification_receipt
    positive = verifier(
        positive_path,
        _authority_root=authority_root,
        _current_manifest=current_manifest,
    )
    ordinary = verifier(
        ordinary_path,
        _authority_root=authority_root,
        _current_manifest=current_manifest,
    )
    expected_core = _pair_core(
        positive_path=positive_path,
        positive=positive,
        ordinary_path=ordinary_path,
        ordinary=ordinary,
        positive_view_path=positive_view_path,
        ordinary_view_path=ordinary_view_path,
        expected_profile_root=profile_root,
    )
    if core != expected_core:
        raise IdentityError("Grok terminal qualification drifted from its evidence")
    if _attestation_sequence(ordinary, "ordinary Grok receipt") >= attestation.get(
        "ledger_sequence", 0
    ):
        raise IdentityError("Grok pair attestation order is invalid")
    if current_manifest is not None:
        expected = {
            "executable_fingerprint": current_manifest.raw["executable"]["sha256"],
            "execution_fingerprint": current_manifest.execution_fingerprint,
            "adapter_fingerprint": current_manifest.raw["adapter_fingerprint"],
            "protocol_fingerprint": current_manifest.raw["protocol_fingerprint"],
            "version_fingerprint": current_manifest.raw["executable"][
                "version_sha256"
            ],
            "platform_fingerprint": sha256_bytes(
                canonical_json_bytes(current_manifest.raw["platform"])
            ),
        }
        if any(value[name] != observed for name, observed in expected.items()):
            raise IdentityError("Grok terminal qualification is stale")
    validate_bounded_json(
        value,
        max_depth=14,
        max_items=420,
        max_string=4096,
        reject_sensitive_fields=True,
    )
    return value


__all__ = [
    "CONTROL_SOURCE_SCHEMA",
    "GROK_NATIVE_TRIGGER",
    "GROK_NATIVE_TRIGGER_SHA256",
    "MATCHED_CONTROL_SCHEMA",
    "NATIVE_VIEW_NAME",
    "NATIVE_VIEW_SCHEMA",
    "PAIR_MEMBER_SCHEMA",
    "RUNTIME_VECTOR_SCHEMA",
    "TERMINAL_QUALIFICATION_SCHEMA",
    "TREE_HALT_SCHEMA",
    "build_grok_control_source",
    "build_grok_pair_member_source",
    "build_grok_runtime_vector",
    "build_grok_terminal_qualification",
    "derive_grok_session_uuid",
    "grok_puppet_rule_count",
    "await_grok_native_view",
    "record_grok_native_view",
    "validate_grok_control_source",
    "validate_grok_native_view",
    "validate_grok_pair_member_source",
    "validate_grok_runtime_vector",
    "verify_grok_pair_member_artifacts",
    "verify_grok_terminal_qualification",
]
