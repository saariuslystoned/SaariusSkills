"""Controller-owned Claude activation/control qualification closure.

The activation and ordinary-control probes remain independently
non-promotable.  This module joins two already terminal receipts, structural
native-view observations, and the exact source binding on the control run into
one separately attested receipt.  It never reads pane or instruction bodies.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional

from .authority import AUTHORITY_ID, controller_authority_root
from .errors import ConflictError, IdentityError, ValidationError
from .instructions import validate_instruction_manifest
from .journal import Journal
from .launch import validate_admitted_launch_plan
from .safety import (
    canonical_json_bytes,
    ensure_within,
    read_json,
    reject_symlink_components,
    sha256_bytes,
    sha256_file,
    validate_bounded_json,
    validate_identifier,
    validate_sha256,
)


PAIR_SCHEMA = "puppet.claude-paired-qualification/v1"
CONTROL_SOURCE_SCHEMA = "puppet.claude-ordinary-control-source/v1"
NATIVE_VIEW_SCHEMA = "puppet.claude-native-view-observation/v1"
NATIVE_VIEW_ATTESTATION_SCHEMA = "puppet.claude-native-view-attestation/v1"
PAIRED_RECEIPT_NAME = "claude-paired-receipt.json"
NATIVE_VIEW_NAME = "native-view.json"

_PAIR_FIELDS = {
    "schema",
    "activation_receipt",
    "control_receipt",
    "activation_run_id",
    "control_run_id",
    "activation_process_sha256",
    "control_process_sha256",
    "activation_workspace",
    "control_workspace",
    "subscription_profile_sha256",
    "default_model_observation",
    "native_views",
    "no_bleed",
    "qualified_mapping_sha256",
}
_RECEIPT_REF_FIELDS = {"path", "sha256"}
_NATIVE_VIEW_FIELDS = {
    "schema",
    "run_id",
    "target",
    "controller",
    "campaign_id",
    "goal_fingerprint",
    "session",
    "tmux_sha256",
    "target_process_sha256",
    "viewer",
    "viewer_process",
    "attach_argv_sha256",
    "body_capture_performed",
    "controller_attestation",
}
_NATIVE_VIEW_ATTESTATION_FIELDS = {
    "schema",
    "authority_id",
    "authority_root",
    "request_id",
    "ledger_sequence",
    "ledger_entry_hash",
    "observation_sha256",
}
_VIEWER_FIELDS = {"pid", "tty", "read_only", "session"}
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
_CONTROL_SOURCE_FIELDS = {
    "schema",
    "receipt_path",
    "receipt_sha256",
    "run_id",
    "session_profile",
    "controller",
    "campaign_id",
    "goal_fingerprint",
    "subscription_profile_sha256",
    "process_sha256",
    "attestation_sequence",
}
_DEFAULT_MODEL_OBSERVATION = {
    "selection": "current_default",
    "resolved_identity": "unavailable",
    "effort": "unavailable",
}


def _write_new_json(path: Path, value: Dict[str, Any]) -> None:
    validate_bounded_json(
        value,
        max_depth=12,
        max_items=256,
        max_string=8192,
        reject_sensitive_fields=True,
    )
    path = Path(path)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    reject_symlink_components(path, allow_missing_leaf=True)
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(str(path), flags, 0o600)
    except FileExistsError as exc:
        raise ConflictError("%s already exists" % path.name) from exc
    try:
        payload = canonical_json_bytes(value) + b"\n"
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        directory = os.open(str(path.parent), os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except BaseException:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        raise


def claude_qualified_mapping(mapping: Mapping[str, Any]) -> Dict[str, Any]:
    """Close only the isolation bit proved by a paired Claude receipt."""

    if (
        not isinstance(mapping, Mapping)
        or mapping.get("complete") is not False
        or mapping.get("project_isolation_declared") is not False
        or mapping.get("project_isolation_flags") != []
    ):
        raise ValidationError("Claude probe mapping is not the incomplete census tuple")
    result = dict(mapping)
    result["complete"] = True
    result["project_isolation_declared"] = True
    return result


def is_claude_pair_mapping_closure(mapping: Any) -> bool:
    if not isinstance(mapping, Mapping):
        return False
    try:
        probe = claude_probe_mapping_from_qualified(mapping)
    except (ValidationError, IdentityError):
        return False
    return probe.get("complete") is False


def claude_probe_mapping_from_qualified(
    mapping: Mapping[str, Any],
) -> Dict[str, Any]:
    if (
        not isinstance(mapping, Mapping)
        or mapping.get("complete") is not True
        or mapping.get("project_isolation_declared") is not True
        or mapping.get("project_isolation_flags") != []
    ):
        raise ValidationError("Claude mapping is not a paired qualification closure")
    result = dict(mapping)
    result["complete"] = False
    result["project_isolation_declared"] = False
    return result


def _proof_artifact(receipt_path: Path, receipt: Mapping[str, Any], kind: str) -> Path:
    refs = receipt.get("proof_refs")
    if not isinstance(refs, list):
        raise ValidationError("qualification proof references are unavailable")
    matches = [item for item in refs if isinstance(item, dict) and item.get("kind") == kind]
    if len(matches) != 1:
        raise ValidationError("qualification proof reference is unavailable: %s" % kind)
    reference = matches[0]
    if set(reference) != {"kind", "path", "sha256"}:
        raise ValidationError("qualification proof reference fields are invalid")
    relative = reference.get("path")
    if not isinstance(relative, str) or not relative:
        raise ValidationError("qualification proof path is invalid")
    artifact = ensure_within(
        receipt_path.resolve(strict=True).parent / relative,
        receipt_path.resolve(strict=True).parent,
        must_exist=True,
    )
    if sha256_file(artifact, max_bytes=131072) != reference.get("sha256"):
        raise IdentityError("qualification proof artifact changed")
    return artifact


def build_claude_control_source(
    activation_receipt_path: Path,
    *,
    verify_receipt_fn: Callable[..., Dict[str, Any]],
    authority_root: Optional[Path] = None,
    current_manifest: Optional[Any] = None,
    server_process_fn: Optional[Any] = None,
    tmux_factory: Optional[Any] = None,
) -> Dict[str, Any]:
    path = Path(activation_receipt_path).resolve(strict=True)
    receipt = verify_receipt_fn(
        path,
        _authority_root=authority_root,
        _current_manifest=current_manifest,
        _server_process_fn=server_process_fn,
        _tmux_factory=tmux_factory,
    )
    if (
        receipt.get("target") != "claude"
        or receipt.get("session_profile") != "regular"
        or receipt.get("plane_activation") is None
        or receipt.get("claude_pairing") is not None
    ):
        raise ValidationError(
            "ordinary Claude control requires one activation-only regular receipt"
        )
    evidence_path = _proof_artifact(path, receipt, "evidence")
    evidence = read_json(
        evidence_path, max_bytes=131072, reject_sensitive_fields=True
    )
    process = evidence.get("process")
    if not isinstance(process, dict) or set(process) != _PROCESS_FIELDS:
        raise ValidationError("activation receipt process identity is unavailable")
    attestation = receipt.get("controller_attestation")
    sequence = attestation.get("ledger_sequence") if isinstance(attestation, dict) else None
    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence <= 0:
        raise ValidationError("activation receipt attestation sequence is invalid")
    return {
        "schema": CONTROL_SOURCE_SCHEMA,
        "receipt_path": str(path),
        "receipt_sha256": sha256_file(path, max_bytes=131072),
        "run_id": receipt["run_id"],
        "session_profile": receipt["session_profile"],
        "controller": receipt["controller"],
        "campaign_id": receipt["campaign_id"],
        "goal_fingerprint": receipt["goal_fingerprint"],
        "subscription_profile_sha256": receipt["subscription_profile_sha256"],
        "process_sha256": sha256_bytes(canonical_json_bytes(process)),
        "attestation_sequence": sequence,
    }


def validate_claude_control_source(value: Any) -> Dict[str, Any]:
    if not isinstance(value, dict) or set(value) != _CONTROL_SOURCE_FIELDS:
        raise ValidationError("Claude ordinary-control source fields are invalid")
    if value.get("schema") != CONTROL_SOURCE_SCHEMA:
        raise ValidationError("unsupported Claude ordinary-control source schema")
    path = Path(value.get("receipt_path", ""))
    if not path.is_absolute():
        raise ValidationError("Claude activation receipt path must be absolute")
    validate_identifier(value.get("run_id"), "activation run id")
    validate_identifier(value.get("controller"), "activation controller")
    validate_identifier(value.get("campaign_id"), "activation campaign")
    for name in (
        "receipt_sha256",
        "goal_fingerprint",
        "subscription_profile_sha256",
        "process_sha256",
    ):
        validate_sha256(value.get(name), name.replace("_", " "))
    if value.get("session_profile") != "regular":
        raise ValidationError("Claude ordinary-control source must be regular")
    sequence = value.get("attestation_sequence")
    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence <= 0:
        raise ValidationError("activation attestation sequence is invalid")
    return dict(value)


def _native_view_event(value: Mapping[str, Any]) -> Dict[str, Any]:
    core = dict(value)
    core.pop("controller_attestation", None)
    observation_sha256 = sha256_bytes(canonical_json_bytes(core))
    return {
        "schema": NATIVE_VIEW_ATTESTATION_SCHEMA,
        "kind": "claude_native_view_observation",
        "authority_id": AUTHORITY_ID,
        "run_id": validate_identifier(value.get("run_id"), "native-view run id"),
        "target": "claude",
        "controller": validate_identifier(
            value.get("controller"), "native-view controller"
        ),
        "campaign_id": validate_identifier(
            value.get("campaign_id"), "native-view campaign"
        ),
        "goal_fingerprint": validate_sha256(
            value.get("goal_fingerprint"), "native-view goal"
        ),
        "observation_sha256": observation_sha256,
        "tmux_sha256": validate_sha256(
            value.get("tmux_sha256"), "native-view tmux"
        ),
        "target_process_sha256": validate_sha256(
            value.get("target_process_sha256"), "native-view target process"
        ),
        "viewer_process_sha256": sha256_bytes(
            canonical_json_bytes(value.get("viewer_process"))
        ),
        "attach_argv_sha256": validate_sha256(
            value.get("attach_argv_sha256"), "native-view attach argv"
        ),
    }


def _attest_native_view(
    value: Mapping[str, Any], *, authority_root: Optional[Path]
) -> Dict[str, Any]:
    root = controller_authority_root(authority_root)
    event = _native_view_event(value)
    request_id = "claude-view-%s" % event["observation_sha256"][:40]
    row = Journal(root / "claude-native-view-observations").append(
        request_id=request_id,
        event=event,
    )
    return {
        "schema": NATIVE_VIEW_ATTESTATION_SCHEMA,
        "authority_id": AUTHORITY_ID,
        "authority_root": str(root),
        "request_id": request_id,
        "ledger_sequence": row["sequence"],
        "ledger_entry_hash": row["entry_hash"],
        "observation_sha256": event["observation_sha256"],
    }


def _verify_native_view_attestation(
    value: Mapping[str, Any], *, authority_root: Optional[Path]
) -> Dict[str, Any]:
    attestation = value.get("controller_attestation")
    root = controller_authority_root(authority_root)
    if (
        not isinstance(attestation, dict)
        or set(attestation) != _NATIVE_VIEW_ATTESTATION_FIELDS
        or attestation.get("schema") != NATIVE_VIEW_ATTESTATION_SCHEMA
        or attestation.get("authority_id") != AUTHORITY_ID
        or attestation.get("authority_root") != str(root)
    ):
        raise ValidationError("Claude native-view attestation is invalid")
    validate_identifier(attestation.get("request_id"), "native-view request")
    validate_sha256(attestation.get("ledger_entry_hash"), "native-view ledger entry")
    validate_sha256(attestation.get("observation_sha256"), "native-view observation")
    sequence = attestation.get("ledger_sequence")
    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence <= 0:
        raise ValidationError("Claude native-view attestation sequence is invalid")
    event = _native_view_event(value)
    if event["observation_sha256"] != attestation["observation_sha256"]:
        raise IdentityError("Claude native-view attestation binding changed")
    row = Journal(root / "claude-native-view-observations").lookup(
        attestation["request_id"]
    )
    if (
        row is None
        or row.get("sequence") != sequence
        or row.get("entry_hash") != attestation["ledger_entry_hash"]
        or row.get("event") != event
    ):
        raise IdentityError("Claude native-view controller inclusion is unavailable")
    return dict(attestation)


def observe_native_view(
    *,
    proof_root: Path,
    run_id: str,
    tmux_factory: Callable[[Path], Any],
    process_birth_fn: Callable[[int], Dict[str, Any]],
    authority_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Record one live read-only native tmux client without reading pane content."""

    proof_root = Path(proof_root).resolve(strict=True)
    run_id = validate_identifier(run_id, "run id")
    run_root = ensure_within(
        proof_root / "probes" / run_id, proof_root, must_exist=True
    )
    state = read_json(
        run_root / "state.json", max_bytes=131072, reject_sensitive_fields=True
    )
    evidence = read_json(
        run_root / "evidence.json", max_bytes=131072, reject_sensitive_fields=True
    )
    if (
        state.get("run_id") != run_id
        or evidence.get("run_id") != run_id
        or state.get("target") != "claude"
        or evidence.get("target") != "claude"
        # Probe state stays nonterminal with ``result: null`` while the
        # evidence envelope carries the explicit live ``running`` marker.
        or state.get("result") is not None
        or state.get("blocker") is not None
        or evidence.get("result") != "running"
        or state.get("phase")
        not in {
            "settling_input",
            "awaiting_ready",
            "ready_validated",
            "followup_validated",
            "accepted_awaiting_halt",
        }
        or state.get("tmux") != evidence.get("tmux")
        or state.get("process") != evidence.get("process")
    ):
        raise ValidationError("Claude probe is not in an observable live phase")
    tmux_value = evidence.get("tmux")
    process = evidence.get("process")
    if not isinstance(tmux_value, dict) or not isinstance(process, dict):
        raise ValidationError("Claude probe runtime identity is unavailable")
    socket = Path(tmux_value.get("socket", ""))
    session = tmux_value.get("session")
    server = tmux_value.get("server_identity")
    controller = tmux_factory(socket.parent)
    controller.assert_tmux_binary_identity(tmux_value.get("tmux_binary_identity"))
    controller.bind_server_identity(socket, server)
    metadata = controller.metadata_for_session(
        socket=socket,
        session=session,
        server_identity=server,
    )
    if (
        metadata.get("session") != session
        or metadata.get("pane") != tmux_value.get("target_id")
        or metadata.get("pane_pid") != process.get("pid")
        or metadata.get("pane_dead") is not False
        or process_birth_fn(process["pid"]) != process
    ):
        raise IdentityError("Claude native view target identity changed")
    clients = controller.viewer_clients(
        socket=socket,
        session=session,
        server_identity=server,
    )
    if len(clients) != 1 or clients[0].get("read_only") is not True:
        raise ValidationError(
            "Claude native view requires exactly one read-only tmux client"
        )
    viewer = clients[0]
    viewer_process = process_birth_fn(viewer["pid"])
    attach_argv = controller.attach_argv(
        socket=socket,
        session=session,
        pane=tmux_value.get("target_id"),
        server_identity=server,
    )
    observation_core = {
        "schema": NATIVE_VIEW_SCHEMA,
        "run_id": run_id,
        "target": "claude",
        "controller": state.get("controller"),
        "campaign_id": evidence.get("campaign_id"),
        "goal_fingerprint": evidence.get("goal_fingerprint"),
        "session": session,
        "tmux_sha256": sha256_bytes(canonical_json_bytes(tmux_value)),
        "target_process_sha256": sha256_bytes(canonical_json_bytes(process)),
        "viewer": viewer,
        "viewer_process": viewer_process,
        "attach_argv_sha256": sha256_bytes(canonical_json_bytes(attach_argv)),
        "body_capture_performed": False,
    }
    observation = dict(
        observation_core,
        controller_attestation=_attest_native_view(
            observation_core, authority_root=authority_root
        ),
    )
    validate_native_view(
        observation,
        receipt_path=None,
        receipt=None,
        evidence=evidence,
        launch_plan=None,
        authority_root=authority_root,
    )
    destination = run_root / NATIVE_VIEW_NAME
    _write_new_json(destination, observation)
    return {
        "ok": True,
        "run_id": run_id,
        "native_view": str(destination),
        "native_view_sha256": sha256_file(destination, max_bytes=131072),
        "body_capture_performed": False,
    }


def validate_native_view(
    value: Any,
    *,
    receipt_path: Optional[Path],
    receipt: Optional[Mapping[str, Any]],
    evidence: Mapping[str, Any],
    launch_plan: Optional[Mapping[str, Any]],
    authority_root: Optional[Path],
) -> Dict[str, Any]:
    if not isinstance(value, dict) or set(value) != _NATIVE_VIEW_FIELDS:
        raise ValidationError("Claude native-view fields are invalid")
    if (
        value.get("schema") != NATIVE_VIEW_SCHEMA
        or value.get("target") != "claude"
        or value.get("body_capture_performed") is not False
    ):
        raise ValidationError("Claude native-view contract is invalid")
    validate_identifier(value.get("run_id"), "native-view run id")
    validate_identifier(value.get("controller"), "native-view controller")
    validate_identifier(value.get("campaign_id"), "native-view campaign")
    validate_sha256(value.get("goal_fingerprint"), "native-view goal")
    validate_identifier(value.get("session"), "native-view session")
    for name in ("tmux_sha256", "target_process_sha256", "attach_argv_sha256"):
        validate_sha256(value.get(name), "native-view %s" % name)
    viewer = value.get("viewer")
    viewer_process = value.get("viewer_process")
    target_process = evidence.get("process")
    server_process = evidence.get("tmux", {}).get("server_identity")
    if (
        not isinstance(viewer, dict)
        or set(viewer) != _VIEWER_FIELDS
        or isinstance(viewer.get("pid"), bool)
        or not isinstance(viewer.get("pid"), int)
        or viewer["pid"] <= 1
        or not isinstance(viewer.get("tty"), str)
        or not viewer["tty"].startswith("/dev/")
        or viewer.get("read_only") is not True
        or viewer.get("session") != value.get("session")
        or not isinstance(viewer_process, dict)
        or set(viewer_process) != _PROCESS_FIELDS
        or viewer_process.get("pid") != viewer.get("pid")
        or not isinstance(target_process, dict)
        or set(target_process) != _PROCESS_FIELDS
        or not isinstance(server_process, dict)
        or set(server_process) != _PROCESS_FIELDS
        or viewer["pid"] in {target_process.get("pid"), server_process.get("pid")}
    ):
        raise ValidationError("Claude native-view client identity is invalid")
    tmux_value = evidence.get("tmux")
    process = evidence.get("process")
    if (
        value["tmux_sha256"] != sha256_bytes(canonical_json_bytes(tmux_value))
        or value["target_process_sha256"]
        != sha256_bytes(canonical_json_bytes(process))
    ):
        raise IdentityError("Claude native-view runtime binding changed")
    if receipt is not None:
        if (
            receipt_path is None
            or value["run_id"] != receipt.get("run_id")
            or value["controller"] != receipt.get("controller")
            or value["campaign_id"] != receipt.get("campaign_id")
            or value["goal_fingerprint"] != receipt.get("goal_fingerprint")
            or value["session"] != tmux_value.get("session")
        ):
            raise IdentityError("Claude native-view receipt binding changed")
    if launch_plan is not None:
        expected_attach = [
            tmux_value["tmux_binary_identity"]["path"],
            "-f",
            os.devnull,
            "-S",
            tmux_value["socket"],
            "attach-session",
            "-r",
            "-E",
            "-t",
            tmux_value["session"],
        ]
        if value["attach_argv_sha256"] != sha256_bytes(
            canonical_json_bytes(expected_attach)
        ):
            raise IdentityError("Claude native-view attach identity changed")
    _verify_native_view_attestation(value, authority_root=authority_root)
    return dict(value)


def validate_pairing_shape(value: Any) -> Dict[str, Any]:
    if not isinstance(value, dict) or set(value) != _PAIR_FIELDS:
        raise ValidationError("Claude paired qualification fields are invalid")
    if value.get("schema") != PAIR_SCHEMA:
        raise ValidationError("unsupported Claude paired qualification schema")
    for name in ("activation_receipt", "control_receipt"):
        ref = value.get(name)
        if not isinstance(ref, dict) or set(ref) != _RECEIPT_REF_FIELDS:
            raise ValidationError("Claude paired receipt reference is invalid")
        if not Path(ref.get("path", "")).is_absolute():
            raise ValidationError("Claude paired receipt path must be absolute")
        validate_sha256(ref.get("sha256"), "Claude paired receipt")
    for name in ("activation_run_id", "control_run_id"):
        validate_identifier(value.get(name), name.replace("_", " "))
    for name in (
        "activation_process_sha256",
        "control_process_sha256",
        "subscription_profile_sha256",
        "qualified_mapping_sha256",
    ):
        validate_sha256(value.get(name), name.replace("_", " "))
    for name in ("activation_workspace", "control_workspace"):
        workspace = value.get(name)
        if not isinstance(workspace, str) or not Path(workspace).is_absolute():
            raise ValidationError("Claude paired workspace is invalid")
    native_views = value.get("native_views")
    if (
        not isinstance(native_views, dict)
        or set(native_views) != {"activation", "control"}
        or any(
            not isinstance(item, dict)
            or set(item) != {"path", "sha256"}
            or not Path(item.get("path", "")).is_absolute()
            for item in native_views.values()
        )
    ):
        raise ValidationError("Claude paired native-view references are invalid")
    for item in native_views.values():
        validate_sha256(item.get("sha256"), "Claude native-view receipt")
    if value.get("default_model_observation") != _DEFAULT_MODEL_OBSERVATION:
        raise ValidationError("Claude default-model observation is invalid")
    if value.get("no_bleed") != {
        "activation_population_before": [],
        "activation_population_after": [],
        "control_population_before": [],
        "control_population_after": [],
        "distinct_processes": True,
        "distinct_sessions": True,
        "distinct_workspaces": True,
        "verified": True,
    }:
        raise ValidationError("Claude paired no-bleed verdict is invalid")
    return dict(value)


def _load_run(
    path: Path, receipt: Mapping[str, Any]
) -> tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    evidence = read_json(
        _proof_artifact(path, receipt, "evidence"),
        max_bytes=131072,
        reject_sensitive_fields=True,
    )
    launch_plan = validate_admitted_launch_plan(
        read_json(
            _proof_artifact(path, receipt, "launch_plan"),
            max_bytes=131072,
            reject_sensitive_fields=True,
        ),
        expected_target="claude",
        expected_session=evidence.get("tmux", {}).get("session"),
        expected_run_id=receipt["run_id"],
    )
    instructions = validate_instruction_manifest(
        read_json(
            _proof_artifact(path, receipt, "instructions"),
            max_bytes=131072,
            reject_sensitive_fields=True,
        ),
        target="claude",
    )
    return evidence, launch_plan, instructions


def _default_model_is_unavailable(
    instructions: Mapping[str, Any], launch_plan: Mapping[str, Any]
) -> bool:
    argv = launch_plan.get("argv")
    return (
        instructions.get("runtime_binding") == {"model": "default", "effort": "default"}
        and instructions.get("model_observation") == _DEFAULT_MODEL_OBSERVATION
        and isinstance(argv, list)
        and "--model" not in argv
        and "--effort" not in argv
    )


def _pair_value(
    *,
    activation_path: Path,
    activation: Mapping[str, Any],
    activation_evidence: Mapping[str, Any],
    activation_plan: Mapping[str, Any],
    activation_view_path: Path,
    control_path: Path,
    control: Mapping[str, Any],
    control_evidence: Mapping[str, Any],
    control_plan: Mapping[str, Any],
    control_view_path: Path,
    qualified_mapping_sha256: str,
) -> Dict[str, Any]:
    return {
        "schema": PAIR_SCHEMA,
        "activation_receipt": {
            "path": str(activation_path),
            "sha256": sha256_file(activation_path, max_bytes=131072),
        },
        "control_receipt": {
            "path": str(control_path),
            "sha256": sha256_file(control_path, max_bytes=131072),
        },
        "activation_run_id": activation["run_id"],
        "control_run_id": control["run_id"],
        "activation_process_sha256": sha256_bytes(
            canonical_json_bytes(activation_evidence["process"])
        ),
        "control_process_sha256": sha256_bytes(
            canonical_json_bytes(control_evidence["process"])
        ),
        "activation_workspace": activation_plan["cwd"],
        "control_workspace": control_plan["cwd"],
        "subscription_profile_sha256": control["subscription_profile_sha256"],
        "default_model_observation": dict(_DEFAULT_MODEL_OBSERVATION),
        "native_views": {
            "activation": {
                "path": str(activation_view_path),
                "sha256": sha256_file(activation_view_path, max_bytes=131072),
            },
            "control": {
                "path": str(control_view_path),
                "sha256": sha256_file(control_view_path, max_bytes=131072),
            },
        },
        "no_bleed": {
            "activation_population_before": [],
            "activation_population_after": [],
            "control_population_before": [],
            "control_population_after": [],
            "distinct_processes": True,
            "distinct_sessions": True,
            "distinct_workspaces": True,
            "verified": True,
        },
        "qualified_mapping_sha256": qualified_mapping_sha256,
    }


def verify_claude_pairing(
    pair: Mapping[str, Any],
    *,
    paired_receipt: Mapping[str, Any],
    paired_receipt_path: Path,
    verify_receipt_fn: Callable[..., Dict[str, Any]],
    authority_root: Optional[Path] = None,
    current_manifest: Optional[Any] = None,
    server_process_fn: Optional[Any] = None,
    tmux_factory: Optional[Any] = None,
) -> Dict[str, Any]:
    pair = validate_pairing_shape(pair)
    if paired_receipt.get("target") != "claude" or paired_receipt.get(
        "plane_activation"
    ) is not None:
        raise ValidationError("Claude paired receipt must project the ordinary control")
    activation_path = Path(pair["activation_receipt"]["path"]).resolve(strict=True)
    control_path = Path(pair["control_receipt"]["path"]).resolve(strict=True)
    if (
        paired_receipt_path.resolve(strict=True).name != PAIRED_RECEIPT_NAME
        or paired_receipt_path.resolve(strict=True).parent != control_path.parent
        or control_path.name != "receipt.json"
        or activation_path.name != "receipt.json"
        or activation_path.parent.parent != control_path.parent.parent
        or activation_path == control_path
    ):
        raise IdentityError("Claude paired receipt locations are not canonical")
    for path, reference in (
        (activation_path, pair["activation_receipt"]),
        (control_path, pair["control_receipt"]),
    ):
        if sha256_file(path, max_bytes=131072) != reference["sha256"]:
            raise IdentityError("Claude source receipt changed")
    activation = verify_receipt_fn(
        activation_path,
        _authority_root=authority_root,
        _current_manifest=current_manifest,
        _server_process_fn=server_process_fn,
        _tmux_factory=tmux_factory,
    )
    control = verify_receipt_fn(
        control_path,
        _authority_root=authority_root,
        _current_manifest=current_manifest,
        _server_process_fn=server_process_fn,
        _tmux_factory=tmux_factory,
    )
    if (
        activation.get("target") != "claude"
        or activation.get("plane_activation") is None
        or activation.get("claude_pairing") is not None
        or control.get("target") != "claude"
        or control.get("plane_activation") is not None
        or control.get("claude_pairing") is not None
    ):
        raise IdentityError("Claude activation/control receipt identities do not match")
    shared_names = (
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
    )
    if any(control.get(name) != activation.get(name) for name in shared_names):
        raise IdentityError("Claude activation/control shared identity changed")
    if any(
        paired_receipt.get(name) != control.get(name)
        for name in set(control) - {"controller_attestation"}
    ):
        raise IdentityError("Claude paired receipt does not project its control")
    activation_evidence, activation_plan, activation_instructions = _load_run(
        activation_path, activation
    )
    control_evidence, control_plan, control_instructions = _load_run(
        control_path, control
    )
    control_state = read_json(
        control_path.parent / "state.json",
        max_bytes=131072,
        reject_sensitive_fields=True,
    )
    expected_source = build_claude_control_source(
        activation_path,
        verify_receipt_fn=verify_receipt_fn,
        authority_root=authority_root,
        current_manifest=current_manifest,
        server_process_fn=server_process_fn,
        tmux_factory=tmux_factory,
    )
    if control_state.get("claude_control_source") != expected_source:
        raise IdentityError("Claude ordinary control is not bound to the activation")
    activation_process = activation_evidence.get("process")
    control_process = control_evidence.get("process")
    activation_tmux = activation_evidence.get("tmux", {})
    control_tmux = control_evidence.get("tmux", {})
    if (
        activation_evidence.get("active_target_processes_before_launch") != []
        or activation_evidence.get("active_target_processes_after_halt") != []
        or control_evidence.get("active_target_processes_before_launch") != []
        or control_evidence.get("active_target_processes_after_halt") != []
        or activation_process == control_process
        or activation_tmux.get("session") == control_tmux.get("session")
        or activation_tmux.get("socket") == control_tmux.get("socket")
        or activation_plan.get("cwd") == control_plan.get("cwd")
    ):
        raise IdentityError("Claude activation/control no-bleed evidence is incomplete")
    if not _default_model_is_unavailable(
        activation_instructions, activation_plan
    ) or not _default_model_is_unavailable(control_instructions, control_plan):
        raise IdentityError("Claude default-model-unavailable evidence is incomplete")
    activation_view_path = activation_path.parent / NATIVE_VIEW_NAME
    control_view_path = control_path.parent / NATIVE_VIEW_NAME
    for path, receipt, evidence, plan in (
        (activation_view_path, activation, activation_evidence, activation_plan),
        (control_view_path, control, control_evidence, control_plan),
    ):
        view = read_json(path, max_bytes=131072, reject_sensitive_fields=True)
        validate_native_view(
            view,
            receipt_path=path.parent / "receipt.json",
            receipt=receipt,
            evidence=evidence,
            launch_plan=plan,
            authority_root=authority_root,
        )
    raw_mapping = current_manifest.raw["yolo_mapping"] if current_manifest is not None else None
    if raw_mapping is not None and is_claude_pair_mapping_closure(raw_mapping):
        raw_mapping = claude_probe_mapping_from_qualified(raw_mapping)
    if raw_mapping is None:
        raise ValidationError("Claude paired qualification requires current mapping")
    qualified_mapping_sha256 = sha256_bytes(
        canonical_json_bytes(claude_qualified_mapping(raw_mapping))
    )
    expected_pair = _pair_value(
        activation_path=activation_path,
        activation=activation,
        activation_evidence=activation_evidence,
        activation_plan=activation_plan,
        activation_view_path=activation_view_path,
        control_path=control_path,
        control=control,
        control_evidence=control_evidence,
        control_plan=control_plan,
        control_view_path=control_view_path,
        qualified_mapping_sha256=qualified_mapping_sha256,
    )
    if pair != expected_pair:
        raise IdentityError("Claude paired qualification evidence changed")
    activation_sequence = activation["controller_attestation"]["ledger_sequence"]
    control_sequence = control["controller_attestation"]["ledger_sequence"]
    pair_sequence = paired_receipt["controller_attestation"]["ledger_sequence"]
    if not activation_sequence < control_sequence < pair_sequence:
        raise IdentityError("Claude paired qualification attestation order is invalid")
    return dict(pair)


def create_claude_pair(
    *,
    activation_receipt_path: Path,
    control_receipt_path: Path,
    verify_receipt_fn: Callable[..., Dict[str, Any]],
    attest_receipt_fn: Callable[..., Dict[str, Any]],
    authority_root: Optional[Path] = None,
    current_manifest: Any,
    server_process_fn: Optional[Any] = None,
    tmux_factory: Optional[Any] = None,
) -> Dict[str, Any]:
    activation_path = Path(activation_receipt_path).resolve(strict=True)
    control_path = Path(control_receipt_path).resolve(strict=True)
    activation = verify_receipt_fn(
        activation_path,
        _authority_root=authority_root,
        _current_manifest=current_manifest,
        _server_process_fn=server_process_fn,
        _tmux_factory=tmux_factory,
    )
    control = verify_receipt_fn(
        control_path,
        _authority_root=authority_root,
        _current_manifest=current_manifest,
        _server_process_fn=server_process_fn,
        _tmux_factory=tmux_factory,
    )
    activation_evidence, activation_plan, _ = _load_run(activation_path, activation)
    control_evidence, control_plan, _ = _load_run(control_path, control)
    mapping = current_manifest.raw["yolo_mapping"]
    pair = _pair_value(
        activation_path=activation_path,
        activation=activation,
        activation_evidence=activation_evidence,
        activation_plan=activation_plan,
        activation_view_path=activation_path.parent / NATIVE_VIEW_NAME,
        control_path=control_path,
        control=control,
        control_evidence=control_evidence,
        control_plan=control_plan,
        control_view_path=control_path.parent / NATIVE_VIEW_NAME,
        qualified_mapping_sha256=sha256_bytes(
            canonical_json_bytes(claude_qualified_mapping(mapping))
        ),
    )
    control_core = dict(control)
    control_core.pop("controller_attestation")
    paired_core = dict(control_core, claude_pairing=pair)
    paired = dict(
        paired_core,
        controller_attestation=attest_receipt_fn(
            paired_core, authority_root=authority_root
        ),
    )
    destination = control_path.parent / PAIRED_RECEIPT_NAME
    _write_new_json(destination, paired)
    try:
        verify_receipt_fn(
            destination,
            _authority_root=authority_root,
            _current_manifest=current_manifest,
            _server_process_fn=server_process_fn,
            _tmux_factory=tmux_factory,
        )
    except BaseException:
        destination.unlink()
        raise
    return {
        "ok": True,
        "target": "claude",
        "result": "paired_accepted",
        "receipt": str(destination),
        "receipt_sha256": sha256_file(destination, max_bytes=131072),
        "activation_receipt": str(activation_path),
        "control_receipt": str(control_path),
        "no_bleed_verified": True,
        "body_capture_performed": False,
    }
