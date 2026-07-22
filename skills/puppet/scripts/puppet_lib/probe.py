"""Doctor-only bootstrap path for real-harness adapter qualification.

This module is deliberately separate from the normal Puppet session launcher.
It can exercise a doctor-only manifest, but it cannot turn that manifest into a
normal live adapter.  Only the bounded accepted receipt emitted at the end of
this path can later be consumed by ``adapter_lab qualify``.
"""

from __future__ import annotations

import copy
import datetime as dt
import secrets
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from .adapter_manifest import (
    AdapterManifest,
    PROBE_CAPABILITIES,
    QUALIFICATION_EVIDENCE_SCHEMA_VERSION,
    QUALIFICATION_PROFILE,
    QUALIFICATION_RECEIPT_SCHEMA_VERSION,
    QUALIFICATION_STATE_SCHEMA_VERSION,
    validate_qualification_evidence_schema,
    validate_qualification_state_schema,
    verify_qualification_receipt,
)
from .adapters import adapter_for
from .authority import (
    acquire_real_harness_lock,
    admit_session_lease,
    attest_qualification,
    current_session_lease,
    lease_owner as build_lease_owner,
    require_session_lease,
    release_real_harness_lock,
    transition_session_lease,
)
from .campaign import (
    active_target_processes,
    parallel_target_override,
    target_process_snapshot,
    validate_campaign_authorization,
    verify_campaign_goal,
)
from .conformance import create_fixture, tree_fingerprint
from .contracts import (
    Contract,
    MANDATORY_HARD_GATES,
    PROCESS_IDENTITY_FIELDS,
    TARGET_POPULATION_POLICY,
    TARGETS,
)
from .census import adapter_implementation_fingerprint, census_target
from .errors import (
    ConflictError,
    IdentityError,
    PuppetError,
    ValidationError,
)
from .handoffs import HANDOFF_SCHEMA_VERSION, ValidatedHandoff, validate_handoff
from .halt_control import deliver_halt_actions
from .instructions import compile_instruction_wrapper, validate_instruction_manifest
from .instruction_planes import (
    descriptor_fingerprint,
    parse_instruction_plane_descriptor,
)
from .journal import Journal
from .launch import build_admitted_launch_plan, build_launch_identity
from .plane_activation import (
    ACTIVATION_LIFECYCLE_SCOPE,
    CLAUDE_NATIVE_TRIGGER,
    CLAUDE_NATIVE_TRIGGER_SHA256,
    PROBE_PLANE_ACTIVATION_SCHEMA,
    ActivationLaunchContext,
    ActivationPlan,
    build_activation_launch_context,
    materialize_activation,
    plan_activation,
    recover_activation,
    revalidate_activation_launch_context,
    rollback_activation,
    validate_terminal_activation_evidence,
)
from .profiles import (
    INPUT_READINESS_STRATEGY,
    OBSERVED_INPUT_TRANSPORT,
    PROMPT_TRANSPORT,
    SUBMIT_SETTLE_SECONDS,
    session_profiles_for,
    startup_settle_seconds_for,
    validate_session_profile,
)
from .registry import (
    bind_runtime_process,
    process_alive,
    process_birth_identity,
    process_tree_alive,
    send_exact_sigint,
)
from .safety import (
    absolute_root,
    atomic_write_json,
    canonical_json_bytes,
    ensure_within,
    read_json,
    sha256_bytes,
    sha256_file,
    validate_identifier,
)
from .tmux import TargetLaunch, TmuxController
from .verdicts import record_acceptance, record_review


MAX_PROBE_SECONDS = 900.0
MAX_HALT_SECONDS = 60.0
POLL_INTERVAL_SECONDS = 0.1
PROBE_PROFILE = QUALIFICATION_PROFILE
MAX_TARGET_POPULATION = 64
MAX_TARGET_DESCENDANTS = 32
MAX_TARGET_ANCESTRY_NODES = 512
MAX_ANCESTRY_DEPTH = 64


def _utc_now() -> str:
    return (
        dt.datetime.now(dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _new_run_id(target: str) -> str:
    return "probe-%s-%s" % (target, secrets.token_hex(8))


def _acquire_campaign_probe_lock(
    authority_root: Optional[Path] = None,
    *,
    target: str,
    reject_active_lease: bool = True,
) -> tuple[int, Dict[str, Any]]:
    """Compatibility wrapper around one target-specific authority lock."""
    return acquire_real_harness_lock(
        authority_root,
        target=target,
        reject_active_lease=reject_active_lease,
    )


def _release_campaign_probe_lock(descriptor: Optional[int]) -> None:
    release_real_harness_lock(descriptor)


def _session_id(target: str, run_id: str) -> str:
    digest = sha256_bytes(run_id.encode("utf-8"))[:16]
    return validate_identifier("probe-%s-%s" % (target, digest), "session")


def _validated_target_population(
    *,
    snapshot: Dict[str, Any],
    protected: list[Dict[str, Any]],
    registered: Dict[str, Any],
    process_alive_fn: Callable[[Dict[str, Any]], bool],
    process_tree_alive_fn: Callable[[Dict[str, Any]], bool],
) -> Dict[str, Any]:
    """Admit only exact protected/root identities plus exact root descendants."""

    if not isinstance(snapshot, dict) or set(snapshot) != {
        "processes",
        "ancestry_nodes",
    }:
        raise IdentityError("same-target process snapshot fields are invalid")
    observed = snapshot["processes"]
    nodes = snapshot["ancestry_nodes"]
    if (
        not isinstance(observed, list)
        or len(observed) > MAX_TARGET_POPULATION
        or not isinstance(nodes, list)
        or len(nodes) > MAX_TARGET_ANCESTRY_NODES
    ):
        raise IdentityError("same-target process snapshot exceeds its bound")
    for identity in [*protected, registered, *observed]:
        if not isinstance(identity, dict) or set(identity) != PROCESS_IDENTITY_FIELDS:
            raise IdentityError("same-target process identity fields are invalid")
    nodes_by_pid = {}
    for node in nodes:
        if (
            not isinstance(node, dict)
            or set(node) != {"process", "parent_pid"}
            or not isinstance(node["process"], dict)
            or set(node["process"]) != PROCESS_IDENTITY_FIELDS
            or isinstance(node["parent_pid"], bool)
            or not isinstance(node["parent_pid"], int)
            or node["parent_pid"] < 0
            or node["process"]["pid"] in nodes_by_pid
            or not process_tree_alive_fn(node)
        ):
            raise IdentityError("same-target ancestry node is invalid")
        nodes_by_pid[node["process"]["pid"]] = node
    expected = [*protected, registered]
    expected_pids = [item["pid"] for item in expected]
    observed_pids = [item["pid"] for item in observed]
    if len(expected_pids) != len(set(expected_pids)) or len(observed_pids) != len(
        set(observed_pids)
    ):
        raise IdentityError("same-target process snapshot contains duplicate PIDs")
    observed_by_pid = {item["pid"]: item for item in observed}
    if any(
        nodes_by_pid.get(identity["pid"], {}).get("process") != identity
        for identity in observed
    ):
        raise IdentityError("same-target process lacks an exact ancestry node")
    for identity in expected:
        if observed_by_pid.get(identity["pid"]) != identity or not process_alive_fn(
            identity
        ):
            raise IdentityError("protected or registered process identity changed")

    protected_pids = {item["pid"] for item in protected}
    executable_identity = {
        name: registered[name] for name in ("executable_path", "device", "inode")
    }
    descendants = []
    chains = []
    for identity in observed:
        if identity["pid"] in expected_pids:
            continue
        if {
            name: identity[name] for name in ("executable_path", "device", "inode")
        } != executable_identity or not process_alive_fn(identity):
            raise IdentityError(
                "same-target extra lacks the registered executable identity"
            )
        chain = [nodes_by_pid[identity["pid"]]]
        seen = {identity["pid"]}
        current = nodes_by_pid[identity["pid"]]
        for _ in range(MAX_ANCESTRY_DEPTH):
            parent_pid = current["parent_pid"]
            if parent_pid <= 1 or parent_pid in seen:
                raise IdentityError(
                    "same-target extra lacks an exact registered-target ancestry chain"
                )
            parent = nodes_by_pid.get(parent_pid)
            if parent is None:
                raise IdentityError(
                    "same-target extra lacks an exact registered-target ancestry chain"
                )
            chain.append(parent)
            if parent["process"] == registered:
                break
            if parent_pid in protected_pids:
                raise IdentityError(
                    "same-target extra descends from a protected process"
                )
            seen.add(parent_pid)
            current = parent
        else:
            raise IdentityError("same-target ancestry exceeds the depth bound")
        if chain[-1]["process"] != registered:
            raise IdentityError(
                "same-target extra is unrelated to the registered target"
            )
        descendants.append(identity)
        chains.append(chain)
        if len(descendants) > MAX_TARGET_DESCENDANTS:
            raise IdentityError("same-target descendants exceed the count bound")
    return {
        "processes": sorted(observed, key=lambda item: item["pid"]),
        "descendants": sorted(descendants, key=lambda item: item["pid"]),
        "ancestry_chains": sorted(chains, key=lambda chain: chain[0]["process"]["pid"]),
    }


def _validated_mapping(
    manifest_path: Path,
    mapping_path: Path,
    *,
    target: str,
    allow_claude_activation: bool = False,
    adapter_fingerprint_fn: Callable[[], str] = adapter_implementation_fingerprint,
    census_target_fn: Callable[[str, str], AdapterManifest] = census_target,
) -> tuple[AdapterManifest, Dict[str, Any], list[str]]:
    manifest = AdapterManifest.from_path(manifest_path)
    if manifest.target != target:
        raise ValidationError("probe target does not match doctor-only manifest")
    if not manifest.raw["doctor_only"] or manifest.raw["qualification"] is not None:
        raise ValidationError("Pass B input must be a doctor-only manifest")
    mapping = read_json(Path(mapping_path), max_bytes=65536)
    raw = copy.deepcopy(manifest.raw)
    raw["yolo_mapping"] = mapping
    candidate = AdapterManifest.from_dict(raw)
    implementation_fingerprint = adapter_fingerprint_fn()
    if candidate.raw["adapter_fingerprint"] != implementation_fingerprint:
        raise IdentityError(
            "doctor manifest does not bind the current adapter implementation"
        )
    observed = census_target_fn(target, implementation_fingerprint)
    for name in (
        "platform",
        "executable",
        "execution",
        "adapter_fingerprint",
        "protocol_fingerprint",
    ):
        if observed.raw[name] != candidate.raw[name]:
            raise IdentityError("fresh zero-agent census identity changed: %s" % name)
    if observed.raw["yolo_mapping"] != mapping:
        raise IdentityError("fresh zero-agent census YOLO mapping changed")
    if not mapping.get("complete"):
        expected_activation_mapping = {
            "complete": False,
            "launch_argv": [
                candidate.raw["executable"]["resolved_path"],
                "--dangerously-skip-permissions",
            ],
            "permission_declared": True,
            "permission_flags": ["--dangerously-skip-permissions"],
            "prompt_transport": PROMPT_TRANSPORT,
            "prompt_transport_declared": True,
            "sandbox_disable_declared": True,
            "sandbox_flags": [],
            "project_isolation_declared": False,
            "project_isolation_flags": [],
            "session_profiles": session_profiles_for("claude"),
            "session_profiles_declared": True,
            "startup_settle_seconds": startup_settle_seconds_for("claude"),
            "submit_settle_seconds": SUBMIT_SETTLE_SECONDS,
            "model_flag": "--model",
            "effort_flag": "--effort",
        }
        if (
            not allow_claude_activation
            or target != "claude"
            or mapping != expected_activation_mapping
        ):
            raise ValidationError(
                "candidate YOLO and sandbox-off mapping is incomplete"
            )
    argv = list(mapping["launch_argv"])
    _assert_executable_identity(candidate)
    executable = Path(candidate.raw["executable"]["resolved_path"])
    if argv[0] != str(executable):
        raise IdentityError("candidate mapping does not launch the exact executable")
    return candidate, mapping, argv


def _read_plane_descriptor(path: Path) -> Dict[str, Any]:
    candidate = Path(path)
    if candidate.is_symlink() or not candidate.is_file():
        raise ValidationError(
            "instruction-plane descriptor must be a regular non-symlink file"
        )
    raw = candidate.read_bytes()
    if len(raw) > 131072:
        raise ValidationError("instruction-plane descriptor exceeds the size limit")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValidationError("instruction-plane descriptor must be UTF-8") from exc
    return parse_instruction_plane_descriptor(text)


def _active_population(
    selector_fn: Callable[..., list[Dict[str, Any]]],
    target: str,
    manifest: AdapterManifest,
) -> list[Dict[str, Any]]:
    if selector_fn is active_target_processes:
        return selector_fn(
            target, execution_files=manifest.process_execution_selectors()
        )
    return selector_fn(target)


def _assert_executable_identity(manifest: AdapterManifest) -> None:
    manifest.verify_execution_files()


def _assert_adapter_identity(
    manifest: AdapterManifest, fingerprint_fn: Callable[[], str]
) -> None:
    if fingerprint_fn() != manifest.raw["adapter_fingerprint"]:
        raise IdentityError("probe adapter implementation identity changed")


def _assert_instruction_artifact(
    *,
    path: Path,
    expected_sha256: str,
    expected_manifest: Dict[str, Any],
    target: str,
) -> Dict[str, Any]:
    if sha256_file(path, max_bytes=131072) != expected_sha256:
        raise IdentityError("probe instruction manifest fingerprint changed")
    observed = validate_instruction_manifest(
        read_json(path, max_bytes=131072, reject_sensitive_fields=True),
        target=target,
    )
    if canonical_json_bytes(observed) != canonical_json_bytes(expected_manifest):
        raise IdentityError("probe instruction manifest identity changed")
    return observed


def _assert_handoff_set(fixture: Path, expected_names: set[str]) -> None:
    handoffs = ensure_within(fixture / "handoffs", fixture, must_exist=True)
    observed = set()
    for entry in handoffs.iterdir():
        if entry.is_symlink() or not entry.is_file():
            raise IdentityError("probe handoff directory contains a non-regular entry")
        observed.add(entry.name)
    if observed != expected_names:
        raise IdentityError("probe handoff directory contains unexpected artifacts")


def _proof_reference(kind: str, path: Path, run_root: Path) -> Dict[str, str]:
    artifact = ensure_within(path, run_root, must_exist=True)
    if artifact.is_symlink() or not artifact.is_file():
        raise IdentityError("probe proof artifact is not a regular file")
    return {
        "kind": kind,
        "path": artifact.relative_to(run_root.resolve(strict=True)).as_posix(),
        "sha256": sha256_file(artifact, max_bytes=131072),
    }


def _controller_contract(
    *,
    fixture: Path,
    campaign_id: str,
    controller: str,
    target: str,
    profile: str,
    session_profile: str,
) -> Contract:
    raw = {
        "schema_version": 1,
        "objective": "Run the shared source-free real-harness conformance contract",
        "campaign_authorization_id": campaign_id,
        "controller": controller,
        "target": target,
        "session_profile": session_profile,
        "requested_model": None,
        "requested_effort": None,
        "task_profile": profile,
        "harness_trust": "unrestricted_required",
        "mutation_owner": "none",
        "repo": str(fixture),
        "branch": "probe/source-free",
        "max_helpers": 0,
        "allowed_modes": ["read", "test"],
        "terminal_criteria": [
            {"id": "conformance_green", "evidence": "validated_handoff"}
        ],
        "hard_gates": sorted(MANDATORY_HARD_GATES),
    }
    return Contract.from_dict(raw)


def _handoff_value(
    *,
    phase: str,
    session: str,
    fixture_contract: Dict[str, Any],
    manifest: AdapterManifest,
    message_id: Optional[str] = None,
    prior_checkpoint_sha256: Optional[str] = None,
) -> Dict[str, Any]:
    value: Dict[str, Any] = {
        "schema_version": HANDOFF_SCHEMA_VERSION,
        "checkpoint_kind": "conformance",
        "session": session,
        "run_id": fixture_contract["run_id"],
        "nonce": fixture_contract["nonce"],
        "phase": phase,
        "sequence": 0 if phase == "ready" else 1,
        "executable_fingerprint": manifest.raw["executable"]["sha256"],
        "execution_fingerprint": manifest.execution_fingerprint,
        "adapter_fingerprint": manifest.raw["adapter_fingerprint"],
        "protocol_fingerprint": manifest.raw["protocol_fingerprint"],
        "timestamp": _utc_now(),
        "claims": [
            {
                "id": "source_free_contract_acknowledged",
                "status": phase,
            }
        ],
        "evidence_refs": [],
        "decisions_requested": [],
        "limitations": [],
    }
    if phase == "followup":
        value["message_id"] = message_id
        value["prior_checkpoint_sha256"] = prior_checkpoint_sha256
    return value


def _initial_prompt(fixture_contract: Dict[str, Any], ready: Dict[str, Any]) -> str:
    return (
        "PUPPET_REAL_HARNESS_CONFORMANCE_V2\n"
        "Read ./contract.json and verify schema_version, run_id, nonce, and "
        "allowed_fixture_root. Make no source, repository, account, external-send, "
        "or system changes. Atomically write only ./handoffs/ready.json with the "
        "exact JSON object below, then remain available for one follow-up. Do not "
        "claim controller acceptance.\n"
        "run_id=%s\nnonce=%s\nWRITE_READY_JSON=%s"
        % (
            fixture_contract["run_id"],
            fixture_contract["nonce"],
            canonical_json_bytes(ready).decode("utf-8"),
        )
    )


def _followup_prompt(fixture_contract: Dict[str, Any], followup: Dict[str, Any]) -> str:
    return (
        "PUPPET_REAL_HARNESS_FOLLOWUP_V2\n"
        "Verify the same run_id and nonce plus message_id and sequence=1. "
        "Atomically write only ./handoffs/followup.json with the exact JSON object "
        "below, make no other changes, and remain waiting for exact halt.\n"
        "run_id=%s\nnonce=%s\nmessage_id=%s\nsequence=1\n"
        "prior_checkpoint_sha256=%s\nWRITE_FOLLOWUP_JSON=%s"
        % (
            fixture_contract["run_id"],
            fixture_contract["nonce"],
            followup["message_id"],
            followup["prior_checkpoint_sha256"],
            canonical_json_bytes(followup).decode("utf-8"),
        )
    )


def _payload(message: str) -> bytes:
    value = message.encode("utf-8")
    if not value or len(value) > 65536 or b"\x00" in value:
        raise ValidationError("probe message exceeds the bounded transport contract")
    return value


def _assert_runtime(
    *,
    tmux: TmuxController,
    socket: Path,
    session: str,
    pane: str,
    pane_pid: int,
    socket_identity: Dict[str, Any],
    server_identity: Dict[str, Any],
    tmux_binary_identity: Dict[str, Any],
    process: Dict[str, Any],
    process_alive_fn: Callable[[Dict[str, Any]], bool],
) -> Dict[str, Any]:
    tmux.assert_tmux_binary_identity(tmux_binary_identity)
    tmux.assert_tmux_server_identity(socket, server_identity)
    if tmux.socket_identity(socket) != socket_identity:
        raise IdentityError("probe tmux socket identity changed")
    metadata = tmux.metadata(
        socket=socket,
        session=session,
        pane=pane,
        server_identity=server_identity,
    )
    if (
        metadata.get("session") != session
        or metadata.get("pane") != pane
        or metadata.get("pane_pid") != pane_pid
    ):
        raise IdentityError("probe tmux structural identity changed")
    if metadata.get("pane_dead") or not process_alive_fn(process):
        raise IdentityError("exact probe target stopped before the controller halt")
    return metadata


def _wait_for_handoff(
    *,
    path: Path,
    expected: Dict[str, Any],
    expected_data: Dict[str, Any],
    fixture: Path,
    fixture_fingerprint: str,
    tmux: TmuxController,
    socket: Path,
    session: str,
    pane: str,
    pane_pid: int,
    socket_identity: Dict[str, Any],
    server_identity: Dict[str, Any],
    tmux_binary_identity: Dict[str, Any],
    process: Dict[str, Any],
    process_alive_fn: Callable[[Dict[str, Any]], bool],
    population_guard: Callable[[], None],
    expected_handoff_names: set[str],
    timeout: float,
    sleep_fn: Callable[[float], None],
) -> ValidatedHandoff:
    deadline = time.monotonic() + timeout
    while True:
        _assert_runtime(
            tmux=tmux,
            socket=socket,
            session=session,
            pane=pane,
            pane_pid=pane_pid,
            socket_identity=socket_identity,
            server_identity=server_identity,
            tmux_binary_identity=tmux_binary_identity,
            process=process,
            process_alive_fn=process_alive_fn,
        )
        population_guard()
        if path.exists():
            handoff = validate_handoff(path, allowed_roots=[fixture], expected=expected)
            if handoff.data != expected_data:
                raise IdentityError(
                    "probe handoff content differs from the exact contract"
                )
            _assert_handoff_set(fixture, expected_handoff_names)
            if tree_fingerprint(fixture) != fixture_fingerprint:
                raise IdentityError("non-handoff conformance fixture content drifted")
            return handoff
        if time.monotonic() >= deadline:
            raise ValidationError("timed out waiting for the expected probe handoff")
        sleep_fn(POLL_INTERVAL_SECONDS)


def _halt_exact(
    *,
    target: str,
    tmux: TmuxController,
    socket: Path,
    session: str,
    pane: str,
    socket_identity: Dict[str, Any],
    server_identity: Dict[str, Any],
    tmux_binary_identity: Dict[str, Any],
    process: Dict[str, Any],
    process_alive_fn: Callable[[Dict[str, Any]], bool],
    timeout: float,
    sleep_fn: Callable[[float], None],
    reason: str,
    journal: Journal,
    require_live: bool = False,
    exact_sigint_fn: Callable[[Dict[str, Any]], None] = send_exact_sigint,
) -> Dict[str, Any]:
    target_alive = process_alive_fn(process)
    if require_live and not target_alive:
        raise IdentityError("probe target stopped before the required controller halt")
    deadline = time.monotonic() + timeout

    def deliver_one(action: str) -> None:
        if not process_alive_fn(process):
            raise IdentityError("probe target stopped before its exact halt action")
        _assert_runtime(
            tmux=tmux,
            socket=socket,
            session=session,
            pane=pane,
            pane_pid=process["pid"],
            socket_identity=socket_identity,
            server_identity=server_identity,
            tmux_binary_identity=tmux_binary_identity,
            process=process,
            process_alive_fn=process_alive_fn,
        )
        if action == "exact_pid_sigint":
            exact_sigint_fn(process)
        elif action == "tmux_pane_eof":
            tmux.send_control(
                socket=socket,
                session=session,
                pane=pane,
                key="C-d",
                server_identity=server_identity,
                expected_pane_pid=process["pid"],
            )
        else:
            raise IdentityError("exact halt selected an unknown action")

    def pause_after_send() -> None:
        remaining = max(0.0, deadline - time.monotonic())
        if remaining:
            sleep_fn(min(0.25, remaining))

    submitted_actions = deliver_halt_actions(
        journal=journal,
        session=session,
        target_identity=process,
        actions=list(adapter_for(target).graceful_halt_actions),
        process_alive=lambda: process_alive_fn(process),
        deliver_action=deliver_one,
        after_send=pause_after_send,
    )
    signal_sent = bool(submitted_actions)
    signal_name = "none_already_stopped"
    if submitted_actions == ["tmux_pane_eof", "tmux_pane_eof"]:
        signal_name = "tmux_exact_pane_ctrl_d_twice"
    elif submitted_actions == ["tmux_pane_eof"]:
        signal_name = "tmux_exact_pane_ctrl_d_once_target_stopped"
    elif submitted_actions == ["exact_pid_sigint"]:
        signal_name = "exact_registered_pid_sigint"
    elif submitted_actions:
        raise IdentityError("exact halt used an unexpected action sequence")
    while process_alive_fn(process) and time.monotonic() < deadline:
        sleep_fn(POLL_INTERVAL_SECONDS)
    stopped = not process_alive_fn(process)
    tmux_preserved = tmux.exists(socket, session, server_identity=server_identity)
    if not stopped:
        raise IdentityError(
            "exact probe target did not stop gracefully; no broad signal was attempted"
        )
    if not tmux_preserved:
        raise IdentityError("probe tmux evidence session was not preserved")
    if tmux.socket_identity(socket) != socket_identity:
        raise IdentityError("probe tmux socket identity changed during halt")
    stopped_metadata = tmux.metadata_for_session(
        socket=socket,
        session=session,
        server_identity=server_identity,
    )
    if (
        stopped_metadata.get("session") != session
        or stopped_metadata.get("pane") != pane
        or stopped_metadata.get("pane_pid") != process["pid"]
        or not stopped_metadata.get("pane_dead")
    ):
        raise IdentityError(
            "probe target stopped without a preserved dead evidence pane"
        )
    return {
        "schema_version": 1,
        "timestamp": _utc_now(),
        "session": session,
        "target_pid": process["pid"],
        "reason": reason,
        "signal": signal_name,
        "signal_sent": signal_sent,
        "stopped": True,
        "tmux_preserved": True,
        "cleanup_scope": "exact_new_target_only",
    }


def _halt_provisional_exact(
    *,
    target: str,
    tmux: TmuxController,
    socket: Path,
    session: str,
    metadata: Dict[str, Any],
    socket_identity: Dict[str, Any],
    server_identity: Dict[str, Any],
    tmux_binary_identity: Dict[str, Any],
    timeout: float,
    sleep_fn: Callable[[float], None],
    journal: Journal,
    manifest: AdapterManifest,
    process_birth_fn: Callable[[int], Dict[str, Any]],
    process_alive_fn: Callable[[Dict[str, Any]], bool],
    exact_sigint_fn: Callable[[Dict[str, Any]], None],
) -> Dict[str, Any]:
    """Rebind and clean a provisional pane, or leave it fenced without input."""

    tmux.assert_tmux_binary_identity(tmux_binary_identity)
    tmux.assert_tmux_server_identity(socket, server_identity)
    if tmux.socket_identity(socket) != socket_identity:
        raise IdentityError("provisional probe tmux socket identity changed")
    current = tmux.metadata(
        socket=socket,
        session=session,
        pane=metadata.get("pane"),
        server_identity=server_identity,
    )
    if any(
        current.get(name) != metadata.get(name)
        for name in ("session", "pane", "pane_pid")
    ):
        raise IdentityError("provisional probe tmux identity changed")
    if current.get("pane_dead"):
        return {
            "schema_version": 1,
            "timestamp": _utc_now(),
            "session": session,
            "target_pid": metadata["pane_pid"],
            "reason": "failed_probe_provisional_cleanup",
            "signal": "none_already_stopped",
            "signal_sent": False,
            "stopped": True,
            "tmux_preserved": True,
            "cleanup_scope": "exact_new_target_only",
            "identity_binding": "new_private_dead_tmux_pane",
        }
    raise IdentityError(
        "provisional probe runtime remains unbound; no halt action was attempted"
    )


def _write_state(path: Path, state: Dict[str, Any], phase: str, **changes: Any) -> None:
    state.update(changes)
    state["phase"] = phase
    state["updated_at"] = _utc_now()
    atomic_write_json(path, state)


def run_probe(
    *,
    target: str,
    profile: str,
    session_profile: str,
    proof_root: Path,
    manifest_path: Path,
    mapping_path: Path,
    authorization_path: Path,
    controller: str,
    goal_repo: Path,
    expected_campaign_id: str,
    expected_goal: Dict[str, str],
    plane_descriptor: Optional[Path] = None,
    timeout: float = 300.0,
    halt_timeout: float = 10.0,
    run_id: Optional[str] = None,
    _tmux_factory: Callable[[Path], TmuxController] = TmuxController,
    _process_birth_fn: Callable[[int], Dict[str, Any]] = process_birth_identity,
    _server_process_birth_fn: Callable[[int], Dict[str, Any]] = process_birth_identity,
    _process_alive_fn: Callable[[Dict[str, Any]], bool] = process_alive,
    _process_tree_alive_fn: Callable[[Dict[str, Any]], bool] = process_tree_alive,
    _exact_sigint_fn: Callable[[Dict[str, Any]], None] = send_exact_sigint,
    _active_processes_fn: Callable[
        [str], list[Dict[str, Any]]
    ] = active_target_processes,
    _continuous_population_fn: Optional[Callable[[str], list[Dict[str, Any]]]] = None,
    _population_snapshot_fn: Optional[Callable[[str], Dict[str, Any]]] = None,
    _adapter_fingerprint_fn: Callable[[], str] = adapter_implementation_fingerprint,
    _census_target_fn: Callable[[str, str], AdapterManifest] = census_target,
    _sleep_fn: Callable[[float], None] = time.sleep,
    _execution_sleep_fn: Callable[[float], None] = time.sleep,
    _execution_monotonic_fn: Callable[[], float] = time.monotonic,
    _authority_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Run one isolated source-free qualification probe.

    Test-only dependency hooks are private keyword arguments.  The public CLI
    always uses the real structural process and private-socket tmux surfaces.
    """

    if target not in TARGETS:
        raise ValidationError("unsupported probe target")
    if profile != PROBE_PROFILE:
        raise ValidationError(
            "probe profile must be the fixed source-free Pass B contract"
        )
    session_profile = validate_session_profile(target, session_profile)
    if session_profile != "regular":
        raise ValidationError("Pass B qualification is limited to regular sessions")
    validate_identifier(controller, "controller")
    if controller == target:
        raise ValidationError("a target cannot act as its own probe controller")
    if timeout <= 0 or timeout > MAX_PROBE_SECONDS:
        raise ValidationError(
            "probe timeout must be greater than zero and at most 900 seconds"
        )
    if halt_timeout < 0 or halt_timeout > MAX_HALT_SECONDS:
        raise ValidationError("halt timeout must be between zero and 60 seconds")
    proof_root = absolute_root(str(proof_root), "proof root")
    plane_descriptor_value = (
        _read_plane_descriptor(plane_descriptor)
        if plane_descriptor is not None
        else None
    )
    if plane_descriptor_value is not None and (
        target != "claude" or plane_descriptor_value["target"]["harness"] != target
    ):
        raise ValidationError(
            "native instruction-plane activation is limited to the Claude probe"
        )
    manifest, mapping, argv = _validated_mapping(
        manifest_path,
        mapping_path,
        target=target,
        allow_claude_activation=plane_descriptor_value is not None,
        adapter_fingerprint_fn=_adapter_fingerprint_fn,
        census_target_fn=_census_target_fn,
    )
    authorization = validate_campaign_authorization(
        authorization_path,
        target=target,
        controller=controller,
        campaign_id=expected_campaign_id,
    )
    goal_verification = verify_campaign_goal(
        authorization,
        repo_root=goal_repo,
        expected_campaign_id=expected_campaign_id,
        expected_goal=expected_goal,
    )
    run_id = validate_identifier(run_id or _new_run_id(target), "run id")
    session = _session_id(target, run_id)
    probes_root = proof_root / "probes"
    if probes_root.exists() and probes_root.is_symlink():
        raise ValidationError("probe root must not be a symlink")
    probes_root.mkdir(mode=0o700, exist_ok=True)
    ensure_within(probes_root, proof_root, must_exist=True)
    run_root = probes_root / run_id
    if run_root.exists():
        raise ConflictError("probe run id already exists")
    run_root.mkdir(mode=0o700)
    ensure_within(run_root, proof_root, must_exist=True)
    state_path = run_root / "state.json"
    authorization_snapshot_path = run_root / "authorization.json"
    evidence_path = run_root / "evidence.json"
    instruction_path = run_root / "effective-instructions.json"
    launch_plan_path = run_root / "launch-plan.json"
    plane_descriptor_snapshot_path = run_root / "plane-descriptor.json"
    activation_context_path = run_root / "activation-context.json"
    activation_lane_root = run_root / "activation-lane"
    activation_ephemeral_root = activation_lane_root / "ephemeral"
    activation_transaction_root = activation_lane_root / "transaction"
    activation_config_root = activation_lane_root / "config"
    halt_path = run_root / "halt.json"
    receipt_path = run_root / "receipt.json"
    halt_control_journal = Journal(run_root / "halt-control")
    state: Dict[str, Any] = {
        "schema_version": QUALIFICATION_STATE_SCHEMA_VERSION,
        "run_id": run_id,
        "session": session,
        "target": target,
        "controller": controller,
        "profile": profile,
        "session_profile": session_profile,
        "created_at": _utc_now(),
        "updated_at": _utc_now(),
        "phase": "preflight",
        "result": None,
        "blocker": None,
    }
    metadata: Optional[Dict[str, Any]] = None
    process: Optional[Dict[str, Any]] = None
    tmux: Optional[TmuxController] = None
    socket: Optional[Path] = None
    socket_identity: Optional[Dict[str, Any]] = None
    server_identity: Optional[Dict[str, Any]] = None
    tmux_binary_identity: Optional[Dict[str, Any]] = None
    provisional_bound = False
    server_attempted = False
    target_launch_attempted = False
    activation_plan: Optional[ActivationPlan] = None
    activation_context: Optional[ActivationLaunchContext] = None
    activation_public_context: Optional[Dict[str, Any]] = None
    activation_receipt: Optional[Dict[str, Any]] = None
    activation_terminal: Optional[Dict[str, Any]] = None
    active: Optional[list[Dict[str, Any]]] = None
    lock_descriptor: Optional[int] = None
    lease_owned = False
    cleanup: Optional[Dict[str, Any]] = None
    evidence: Dict[str, Any] = {
        "schema_version": QUALIFICATION_EVIDENCE_SCHEMA_VERSION,
        "run_id": run_id,
        "target": target,
        "controller": controller,
        "profile": profile,
        "session_profile": session_profile,
        "campaign_id": authorization["campaign_id"],
        "goal_fingerprint": goal_verification["goal_fingerprint"],
        "authorization_sha256": None,
        "manifest_fingerprint": manifest.fingerprint,
        "executable_fingerprint": manifest.raw["executable"]["sha256"],
        "execution_fingerprint": manifest.execution_fingerprint,
        "version_fingerprint": manifest.raw["executable"]["version_sha256"],
        "platform_fingerprint": sha256_bytes(
            canonical_json_bytes(manifest.raw["platform"])
        ),
        "adapter_fingerprint": manifest.raw["adapter_fingerprint"],
        "protocol_fingerprint": manifest.raw["protocol_fingerprint"],
        "yolo_mapping_sha256": sha256_bytes(canonical_json_bytes(mapping)),
        "launch_argv_sha256": sha256_bytes(canonical_json_bytes(argv)),
        "launch_plan_sha256": None,
        "launch_identity": None,
        "input_transport": OBSERVED_INPUT_TRANSPORT,
        "input_readiness_strategy": INPUT_READINESS_STRATEGY,
        "startup_settle_seconds": startup_settle_seconds_for(target),
        "submit_settle_seconds": SUBMIT_SETTLE_SECONDS,
        "payload_argv_absent": True,
        "instruction_wrapper": None,
        "plane_activation": None,
        "active_target_processes_before_launch": [],
        "active_target_processes_after_halt": None,
        "target_population_policy": TARGET_POPULATION_POLICY,
        "observed_target_descendants": [],
        "last_target_population": None,
        "parallel_target_override": False,
        "protected_session": None,
        "parallel_isolation": None,
        "campaign_probe_lock": None,
        "tmux": None,
        "process": None,
        "ready": None,
        "followup": None,
        "fixture_fingerprint_before": None,
        "fixture_fingerprint_after": None,
        "review_sha256": None,
        "acceptance_sha256": None,
        "halt_sha256": None,
        "result": "running",
        "failure": None,
    }
    try:
        atomic_write_json(state_path, state)
        atomic_write_json(authorization_snapshot_path, authorization)
        if plane_descriptor_value is not None:
            atomic_write_json(
                plane_descriptor_snapshot_path,
                plane_descriptor_value,
            )
        evidence["authorization_sha256"] = sha256_file(
            authorization_snapshot_path, max_bytes=65536
        )
        atomic_write_json(evidence_path, evidence)
        if plane_descriptor_value is not None:
            activation_lane_root.mkdir(mode=0o700)
        fixture = (
            run_root / "fixture"
            if plane_descriptor_value is None
            else activation_lane_root / "workspace"
        )
        fixture_contract = create_fixture(
            fixture, run_id=run_id, session=session, target=target
        )
        if (
            fixture_contract["protocol_fingerprint"]
            != manifest.raw["protocol_fingerprint"]
        ):
            raise IdentityError("fixture and manifest protocol fingerprints differ")
        fixture_fingerprint = tree_fingerprint(fixture)
        evidence["fixture_fingerprint_before"] = fixture_fingerprint
        controller_contract = _controller_contract(
            fixture=fixture,
            campaign_id=authorization["campaign_id"],
            controller=controller,
            target=target,
            profile=profile,
            session_profile=session_profile,
        )
        atomic_write_json(
            run_root / "controller-contract.json", controller_contract.raw
        )
        ready_value = _handoff_value(
            phase="ready",
            session=session,
            fixture_contract=fixture_contract,
            manifest=manifest,
        )
        compiled = compile_instruction_wrapper(
            target=target,
            task=_initial_prompt(fixture_contract, ready_value),
            contract_identity={
                "fingerprint": controller_contract.fingerprint,
                "controller": controller,
                "target": target,
                "task_profile": profile,
            },
            workspace_identity={
                "fixture_fingerprint": fixture_fingerprint,
                "workspace": "isolated_conformance_fixture",
            },
            run_identity={
                "session": session,
                "run_id": run_id,
                "nonce": fixture_contract["nonce"],
            },
            session_profile=session_profile,
            model_binding="default",
            effort_binding="default",
            runtime_contract_layer={
                "mutation_owner": controller_contract.mutation_owner,
                "allowed_modes": sorted(controller_contract.allowed_modes),
                "hard_gates": sorted(controller_contract.hard_gates),
            },
        )
        atomic_write_json(instruction_path, compiled.manifest)
        instruction_manifest_sha = sha256_file(instruction_path, max_bytes=131072)
        evidence["instruction_wrapper"] = {
            "manifest_sha256": instruction_manifest_sha,
            "instruction_policy_fingerprint": compiled.manifest[
                "instruction_policy_fingerprint"
            ],
            "effective_contract_fingerprint": compiled.manifest[
                "effective_contract_fingerprint"
            ],
            "rendered_sha256": compiled.manifest["rendered_sha256"],
            "instruction_plane": compiled.manifest["instruction_plane"],
            "session_profile": compiled.manifest["session_profile"],
            "delivery_transport": compiled.manifest["delivery_transport"],
        }
        admitted_lane_root: Optional[Path] = None
        if plane_descriptor_value is None:
            launch_environment, launch_identity = build_launch_identity(
                target=target,
                repo=fixture,
                argv=argv,
            )
            manifest.verify_launch_execution_environment(launch_environment)
            launch_plan = build_admitted_launch_plan(
                target=target,
                session=session,
                run_id=run_id,
                repo=fixture,
                argv=argv,
                environment=launch_environment,
            )
        else:
            for activation_root in (
                activation_ephemeral_root,
                activation_transaction_root,
                activation_config_root,
            ):
                activation_root.mkdir(mode=0o700)
            activation_plan = plan_activation(
                plane_descriptor_value,
                instruction_manifest=compiled.manifest,
                adapter_manifest=manifest,
                effective_contract=compiled.rendered,
                workspace_root=fixture,
                ephemeral_root=activation_ephemeral_root,
                transaction_root=activation_transaction_root,
                config_root=activation_config_root,
                _current_manifest=manifest,
            )
            activation_receipt = materialize_activation(
                activation_plan,
                effective_contract=compiled.rendered,
            )
            activation_context = build_activation_launch_context(
                activation_plan,
                adapter_manifest=manifest,
                session=session,
                run_id=run_id,
                session_profile=session_profile,
                workspace_root=fixture,
                config_root=activation_config_root,
                admitted_lane_root=activation_lane_root,
            )
            activation_public_context = activation_context.to_public_dict()
            atomic_write_json(activation_context_path, activation_public_context)
            argv = activation_context.argv
            launch_environment = activation_context.environment
            launch_identity = activation_context.launch_identity
            launch_plan = activation_context.admitted_launch_plan
            admitted_lane_root = activation_lane_root
        atomic_write_json(launch_plan_path, launch_plan)
        evidence["launch_plan_sha256"] = sha256_file(launch_plan_path, max_bytes=131072)
        evidence["launch_identity"] = launch_identity
        evidence["launch_argv_sha256"] = sha256_bytes(canonical_json_bytes(argv))
        atomic_write_json(evidence_path, evidence)
        probe_lease_owner = build_lease_owner(
            activity="probe",
            run_id=run_id,
            campaign_id=authorization["campaign_id"],
            goal_fingerprint=goal_verification["goal_fingerprint"],
            proof_root=proof_root,
            state_root=run_root,
        )
        lock_descriptor, lock_identity = _acquire_campaign_probe_lock(
            _authority_root,
            target=target,
            reject_active_lease=False,
        )
        evidence["campaign_probe_lock"] = lock_identity
        atomic_write_json(evidence_path, evidence)
        active = _active_population(_active_processes_fn, target, manifest)
        override = parallel_target_override(authorization, target, active)
        protected_session = (
            authorization.get("authorization", {})
            .get("parallel_target_override", {})
            .get("protected_session")
            if override
            else None
        )
        if protected_session == session:
            raise ConflictError(
                "probe session collides with the protected operator session"
            )
        evidence.update(
            active_target_processes_before_launch=active,
            parallel_target_override=override,
            protected_session=protected_session,
            parallel_isolation=(
                "unique_private_tmux_socket_and_session" if override else None
            ),
        )
        atomic_write_json(evidence_path, evidence)
        if active and not override:
            raise ConflictError(
                "an active same-target process blocks Pass B without the exact parallel isolation override"
            )
        tmux_authority = run_root / "tmux-authority"
        tmux_authority.mkdir(mode=0o700)
        tmux = _tmux_factory(tmux_authority)
        socket = tmux.socket_path(session)

        def admit_before_start() -> None:
            nonlocal lease_owned, server_attempted
            admit_session_lease(
                session=session,
                target=target,
                controller=controller,
                owner=probe_lease_owner,
                instruction_manifest_sha256=instruction_manifest_sha,
                authority_root=_authority_root,
                _lock_descriptor=lock_descriptor,
            )
            lease_owned = True
            require_session_lease(
                session=session,
                target=target,
                controller=controller,
                owner=probe_lease_owner,
                instruction_manifest_sha256=instruction_manifest_sha,
                states={"launching"},
                authority_root=_authority_root,
            )
            if sorted(
                _active_population(_active_processes_fn, target, manifest),
                key=lambda item: item["pid"],
            ) != sorted(active, key=lambda item: item["pid"]):
                raise IdentityError(
                    "same-target process population changed before probe launch"
                )
            _write_state(state_path, state, "launching")
            server_attempted = True

        def admit_before_target_start() -> TargetLaunch:
            nonlocal activation_context, target_launch_attempted
            if activation_plan is not None:
                if activation_context is None or activation_public_context is None:
                    raise IdentityError(
                        "activation launch context is unavailable before target start"
                    )
                activation_context = revalidate_activation_launch_context(
                    activation_context,
                    activation_plan,
                    adapter_manifest=manifest,
                    workspace_root=fixture,
                    config_root=activation_config_root,
                    admitted_lane_root=activation_lane_root,
                    argv=argv,
                    environment=launch_environment,
                    admitted_launch_plan=launch_plan,
                    public_context=activation_public_context,
                )
                refreshed = TargetLaunch(
                    argv=activation_context.argv,
                    environment=activation_context.environment,
                    launch_identity=activation_context.launch_identity,
                )
            else:
                refreshed = TargetLaunch(
                    argv=list(argv),
                    environment=dict(launch_environment),
                    launch_identity=dict(launch_identity),
                )
            target_launch_attempted = True
            return refreshed

        metadata = tmux.launch(
            session=session,
            target=target,
            repo=fixture,
            argv=argv,
            environment=launch_environment,
            admitted_lane_root=admitted_lane_root,
            before_start=admit_before_start,
            before_target_start=admit_before_target_start,
        )
        if metadata.get("launch_identity") != launch_identity:
            raise IdentityError("probe launch context identity is invalid")
        if metadata.get("socket") != str(socket):
            raise IdentityError("probe launched on an unexpected tmux socket")
        socket_identity = tmux.socket_identity(socket)
        server_identity = metadata.get("server_identity")
        tmux_binary_identity = metadata.get("tmux_binary_identity")
        if (
            metadata.get("session") != session
            or not isinstance(metadata.get("pane_pid"), int)
            or metadata["pane_pid"] <= 1
            or not isinstance(metadata.get("pane"), str)
            or not isinstance(server_identity, dict)
            or not isinstance(tmux_binary_identity, dict)
        ):
            raise IdentityError("probe launch metadata is structurally incomplete")
        provisional_bound = True
        if metadata.get("socket_identity") != socket_identity:
            raise IdentityError(
                "probe launch did not bind the private tmux socket identity"
            )
        tmux.assert_tmux_binary_identity(tmux_binary_identity)
        tmux.assert_tmux_server_identity(socket, server_identity)

        def assert_pane_owner(expected_pid: int) -> None:
            current = tmux.metadata(
                socket=socket,
                session=session,
                pane=metadata["pane"],
                server_identity=server_identity,
            )
            if (
                current.get("session") != session
                or current.get("pane") != metadata["pane"]
                or current.get("pane_pid") != expected_pid
                or current.get("pane_dead") is True
            ):
                raise IdentityError(
                    "probe tmux pane no longer owns the provisional runtime process"
                )

        process = bind_runtime_process(
            metadata["pane_pid"],
            manifest,
            assert_pane_owner,
            process_sample_fn=_process_birth_fn,
            monotonic_fn=_execution_monotonic_fn,
            sleep_fn=_execution_sleep_fn,
        )
        evidence["tmux"] = {
            "socket": str(socket),
            "session": session,
            "target_id": metadata["pane"],
            "socket_identity": socket_identity,
            "server_identity": server_identity,
            "tmux_binary_identity": tmux_binary_identity,
        }
        evidence["launch_identity"] = metadata["launch_identity"]
        evidence["process"] = process
        atomic_write_json(evidence_path, evidence)
        transition_session_lease(
            session=session,
            target=target,
            controller=controller,
            owner=probe_lease_owner,
            instruction_manifest_sha256=instruction_manifest_sha,
            state="active",
            process=process,
            authority_root=_authority_root,
            _lock_descriptor=lock_descriptor,
        )
        observed_descendants: Dict[str, Dict[str, Any]] = {}

        def population_guard() -> None:
            if _population_snapshot_fn is not None:
                snapshot = _population_snapshot_fn(target)
            elif _continuous_population_fn is not None:
                legacy_processes = _continuous_population_fn(target)
                snapshot = {
                    "processes": legacy_processes,
                    "ancestry_nodes": [
                        {"process": item, "parent_pid": 1} for item in legacy_processes
                    ],
                }
            else:
                snapshot = target_process_snapshot(
                    target, execution_files=manifest.process_execution_selectors()
                )
            try:
                observation = _validated_target_population(
                    snapshot=snapshot,
                    protected=active,
                    registered=process,
                    process_alive_fn=_process_alive_fn,
                    process_tree_alive_fn=_process_tree_alive_fn,
                )
            except BaseException:
                raw_processes = (
                    snapshot.get("processes") if isinstance(snapshot, dict) else None
                )
                processes = []
                if isinstance(raw_processes, list):
                    for item in raw_processes[:MAX_TARGET_POPULATION]:
                        if (
                            isinstance(item, dict)
                            and set(item) == PROCESS_IDENTITY_FIELDS
                        ):
                            processes.append(item)
                evidence["last_target_population"] = {
                    "policy": TARGET_POPULATION_POLICY,
                    "processes": processes,
                    "ancestry_chains": [],
                    "accepted": False,
                }
                raise
            evidence["last_target_population"] = {
                "policy": TARGET_POPULATION_POLICY,
                "processes": observation["processes"],
                "ancestry_chains": observation["ancestry_chains"],
                "accepted": True,
            }
            changed = False
            chains_by_pid = {
                chain[0]["process"]["pid"]: chain
                for chain in observation["ancestry_chains"]
            }
            for descendant in observation["descendants"]:
                descendant_observation = {
                    "process": descendant,
                    "ancestry_chain": chains_by_pid[descendant["pid"]],
                }
                identity = sha256_bytes(canonical_json_bytes(descendant))
                previous = observed_descendants.get(identity)
                if previous is not None and previous != descendant_observation:
                    raise IdentityError(
                        "same-target descendant ancestry changed during the probe"
                    )
                if previous is None:
                    observed_descendants[identity] = descendant_observation
                    changed = True
            if changed:
                evidence["observed_target_descendants"] = sorted(
                    observed_descendants.values(),
                    key=lambda item: item["process"]["pid"],
                )
                atomic_write_json(evidence_path, evidence)

        population_guard()
        _assert_runtime(
            tmux=tmux,
            socket=socket,
            session=session,
            pane=metadata["pane"],
            pane_pid=metadata["pane_pid"],
            socket_identity=socket_identity,
            server_identity=server_identity,
            tmux_binary_identity=tmux_binary_identity,
            process=process,
            process_alive_fn=_process_alive_fn,
        )
        _assert_executable_identity(manifest)
        _assert_adapter_identity(manifest, _adapter_fingerprint_fn)
        attach = tmux.attach_command(
            socket=socket,
            session=session,
            pane=metadata["pane"],
            server_identity=server_identity,
        )
        _write_state(
            state_path,
            state,
            "settling_input",
            tmux=evidence["tmux"],
            process=process,
            attach_command=attach,
        )
        settle_seconds = startup_settle_seconds_for(target)
        _sleep_fn(settle_seconds)
        population_guard()
        _assert_runtime(
            tmux=tmux,
            socket=socket,
            session=session,
            pane=metadata["pane"],
            pane_pid=metadata["pane_pid"],
            socket_identity=socket_identity,
            server_identity=server_identity,
            tmux_binary_identity=tmux_binary_identity,
            process=process,
            process_alive_fn=_process_alive_fn,
        )
        _assert_executable_identity(manifest)
        _assert_adapter_identity(manifest, _adapter_fingerprint_fn)
        _write_state(state_path, state, "awaiting_ready")

        adapter = adapter_for(target)
        if activation_plan is None:
            initial = adapter.envelope(
                compiled.rendered.decode("utf-8"),
                session_profile,
                initial=True,
            )
            initial_payload = _payload(initial)
            if sha256_bytes(initial_payload) != compiled.manifest["rendered_sha256"]:
                raise IdentityError(
                    "regular profile altered the compiled instruction payload"
                )
        else:
            initial = CLAUDE_NATIVE_TRIGGER
            initial_payload = _payload(CLAUDE_NATIVE_TRIGGER + "\n")
            if (
                sha256_bytes(initial_payload) != CLAUDE_NATIVE_TRIGGER_SHA256
                or sha256_bytes(initial_payload) == compiled.manifest["rendered_sha256"]
            ):
                raise IdentityError("native activation trigger identity is invalid")
        if any(
            initial in argument
            or compiled.rendered.decode("utf-8") in argument
            or "PUPPET_REAL_HARNESS" in argument
            or (activation_plan is None and run_id in argument)
            or fixture_contract["nonce"] in argument
            for argument in argv
        ):
            raise IdentityError("initial prompt appeared in the process arguments")
        _assert_instruction_artifact(
            path=instruction_path,
            expected_sha256=instruction_manifest_sha,
            expected_manifest=compiled.manifest,
            target=target,
        )
        tmux.paste_bytes(
            socket=socket,
            session=session,
            pane=metadata["pane"],
            buffer_name=session + "-initial",
            payload=initial_payload,
        )
        initial_sha = sha256_bytes(initial_payload)
        ready_expected = {
            "session": session,
            "run_id": run_id,
            "nonce": fixture_contract["nonce"],
            "executable_fingerprint": manifest.raw["executable"]["sha256"],
            "execution_fingerprint": manifest.execution_fingerprint,
            "adapter_fingerprint": manifest.raw["adapter_fingerprint"],
            "protocol_fingerprint": manifest.raw["protocol_fingerprint"],
            "phase": "ready",
            "sequence": 0,
        }
        ready = _wait_for_handoff(
            path=fixture / "handoffs" / "ready.json",
            expected=ready_expected,
            expected_data=ready_value,
            fixture=fixture,
            fixture_fingerprint=fixture_fingerprint,
            tmux=tmux,
            socket=socket,
            session=session,
            pane=metadata["pane"],
            pane_pid=metadata["pane_pid"],
            socket_identity=socket_identity,
            server_identity=server_identity,
            tmux_binary_identity=tmux_binary_identity,
            process=process,
            process_alive_fn=_process_alive_fn,
            population_guard=population_guard,
            expected_handoff_names={"ready.json"},
            timeout=timeout,
            sleep_fn=_sleep_fn,
        )
        evidence["ready"] = ready.reference()
        atomic_write_json(evidence_path, evidence)
        _write_state(
            state_path,
            state,
            "ready_validated",
            ready_checkpoint_id=ready.checkpoint_id,
        )

        message_id = validate_identifier(
            "message-%s" % secrets.token_hex(8), "message id"
        )
        followup_value = _handoff_value(
            phase="followup",
            session=session,
            fixture_contract=fixture_contract,
            manifest=manifest,
            message_id=message_id,
            prior_checkpoint_sha256=ready.artifact_sha256,
        )
        followup_message = adapter.envelope(
            _followup_prompt(fixture_contract, followup_value),
            session_profile,
            initial=False,
        )
        followup_payload = _payload(followup_message)
        population_guard()
        if any(
            followup_message in argument
            or "PUPPET_REAL_HARNESS" in argument
            or message_id in argument
            for argument in argv
        ):
            raise IdentityError("follow-up prompt appeared in the process arguments")
        tmux.paste_bytes(
            socket=socket,
            session=session,
            pane=metadata["pane"],
            buffer_name=session + "-followup",
            payload=followup_payload,
        )
        followup_expected = dict(
            ready_expected,
            phase="followup",
            sequence=1,
            message_id=message_id,
            prior_checkpoint_sha256=ready.artifact_sha256,
        )
        followup = _wait_for_handoff(
            path=fixture / "handoffs" / "followup.json",
            expected=followup_expected,
            expected_data=followup_value,
            fixture=fixture,
            fixture_fingerprint=fixture_fingerprint,
            tmux=tmux,
            socket=socket,
            session=session,
            pane=metadata["pane"],
            pane_pid=metadata["pane_pid"],
            socket_identity=socket_identity,
            server_identity=server_identity,
            tmux_binary_identity=tmux_binary_identity,
            process=process,
            process_alive_fn=_process_alive_fn,
            population_guard=population_guard,
            expected_handoff_names={"ready.json", "followup.json"},
            timeout=timeout,
            sleep_fn=_sleep_fn,
        )
        evidence["followup"] = followup.reference()
        evidence["fixture_fingerprint_after"] = tree_fingerprint(fixture)
        if evidence["fixture_fingerprint_after"] != fixture_fingerprint:
            raise IdentityError("non-handoff conformance fixture content drifted")
        _assert_executable_identity(manifest)
        _assert_adapter_identity(manifest, _adapter_fingerprint_fn)
        atomic_write_json(evidence_path, evidence)
        _write_state(
            state_path,
            state,
            "followup_validated",
            followup_checkpoint_id=followup.checkpoint_id,
        )
        population_guard()

        review_evidence_path = run_root / "review-evidence.json"
        atomic_write_json(
            review_evidence_path,
            {
                "classification": "clean",
                "findings": [],
                "observed_capabilities": list(PROBE_CAPABILITIES),
                "fixture_fingerprint": fixture_fingerprint,
                "initial_payload_sha256": initial_sha,
                "followup_payload_sha256": sha256_bytes(followup_payload),
            },
        )
        review = record_review(
            contract=controller_contract,
            actor=controller,
            handoff=followup,
            verdict="conformance_accept",
            evidence_path=review_evidence_path,
            verdict_root=run_root / "verdicts",
        )
        acceptance_evidence_path = run_root / "acceptance-evidence.json"
        atomic_write_json(
            acceptance_evidence_path,
            {"terminal_criteria": ["conformance_green"]},
        )
        record_acceptance(
            contract=controller_contract,
            actor=controller,
            review=review,
            evidence_path=acceptance_evidence_path,
            acceptance_root=run_root / "acceptance",
        )
        review_path = run_root / "verdicts" / (followup.checkpoint_id + ".json")
        acceptance_path = run_root / "acceptance" / (followup.checkpoint_id + ".json")
        evidence["review_sha256"] = sha256_file(review_path, max_bytes=131072)
        evidence["acceptance_sha256"] = sha256_file(acceptance_path, max_bytes=131072)
        atomic_write_json(evidence_path, evidence)
        _write_state(state_path, state, "accepted_awaiting_halt")

        population_guard()
        transition_session_lease(
            session=session,
            target=target,
            controller=controller,
            owner=probe_lease_owner,
            instruction_manifest_sha256=instruction_manifest_sha,
            state="halting",
            process=process,
            authority_root=_authority_root,
            _lock_descriptor=lock_descriptor,
        )
        cleanup = _halt_exact(
            target=target,
            tmux=tmux,
            socket=socket,
            session=session,
            pane=metadata["pane"],
            socket_identity=socket_identity,
            server_identity=server_identity,
            tmux_binary_identity=tmux_binary_identity,
            process=process,
            process_alive_fn=_process_alive_fn,
            timeout=halt_timeout,
            sleep_fn=_sleep_fn,
            reason="accepted_probe_halt",
            journal=halt_control_journal,
            require_live=True,
            exact_sigint_fn=_exact_sigint_fn,
        )
        _assert_executable_identity(manifest)
        _assert_adapter_identity(manifest, _adapter_fingerprint_fn)
        active_after_halt = _active_population(_active_processes_fn, target, manifest)
        if sorted(active_after_halt, key=lambda item: item["pid"]) != sorted(
            active, key=lambda item: item["pid"]
        ):
            raise IdentityError("protected same-target process population changed")
        if activation_plan is not None:
            if (
                plane_descriptor_value is None
                or activation_public_context is None
                or activation_receipt is None
            ):
                raise IdentityError("activation proof family is incomplete")
            rollback_activation(activation_plan)
            activation_intent = read_json(
                activation_plan.intent_path,
                max_bytes=131072,
            )
            activation_receipt = read_json(
                activation_plan.receipt_path,
                max_bytes=131072,
            )
            activation_rollback_intent = read_json(
                activation_plan.rollback_intent_path,
                max_bytes=131072,
            )
            activation_rollback = read_json(
                activation_plan.rollback_receipt_path,
                max_bytes=131072,
            )
            activation_terminal = validate_terminal_activation_evidence(
                {
                    "schema": PROBE_PLANE_ACTIVATION_SCHEMA,
                    "qualification_scope": ACTIVATION_LIFECYCLE_SCOPE,
                    "terminal_state": "rolled_back",
                    "descriptor_sha256": descriptor_fingerprint(plane_descriptor_value),
                    "plan_sha256": activation_plan.plan_sha256,
                    "intent_sha256": sha256_bytes(
                        canonical_json_bytes(activation_intent)
                    ),
                    "materialization_receipt_sha256": sha256_bytes(
                        canonical_json_bytes(activation_receipt)
                    ),
                    "launch_context_sha256": sha256_bytes(
                        canonical_json_bytes(activation_public_context)
                    ),
                    "artifact_sha256": activation_plan.raw["effective_contract_sha256"],
                    "initial_trigger_sha256": CLAUDE_NATIVE_TRIGGER_SHA256,
                    "rollback_intent_sha256": sha256_bytes(
                        canonical_json_bytes(activation_rollback_intent)
                    ),
                    "rollback_receipt_sha256": sha256_bytes(
                        canonical_json_bytes(activation_rollback)
                    ),
                },
                descriptor=plane_descriptor_value,
                intent=activation_intent,
                materialization_receipt=activation_receipt,
                public_context=activation_public_context,
                admitted_launch_plan=launch_plan,
                rollback_intent=activation_rollback_intent,
                rollback_receipt=activation_rollback,
            )
        atomic_write_json(halt_path, cleanup)
        halt_sha = sha256_file(halt_path, max_bytes=65536)
        evidence["halt_sha256"] = halt_sha
        evidence["active_target_processes_after_halt"] = active_after_halt
        evidence["plane_activation"] = activation_terminal
        evidence["result"] = "accepted"
        atomic_write_json(evidence_path, evidence)
        _assert_instruction_artifact(
            path=instruction_path,
            expected_sha256=instruction_manifest_sha,
            expected_manifest=compiled.manifest,
            target=target,
        )
        proof_refs = [
            _proof_reference("authorization", authorization_snapshot_path, run_root),
            _proof_reference("evidence", evidence_path, run_root),
            _proof_reference("launch_plan", launch_plan_path, run_root),
            _proof_reference("instructions", instruction_path, run_root),
            _proof_reference("halt", halt_path, run_root),
            _proof_reference("ready", fixture / "handoffs" / "ready.json", run_root),
            _proof_reference(
                "followup", fixture / "handoffs" / "followup.json", run_root
            ),
            _proof_reference("review", review_path, run_root),
            _proof_reference("acceptance", acceptance_path, run_root),
        ]
        if activation_plan is not None:
            proof_refs.extend(
                [
                    _proof_reference(
                        "plane_descriptor",
                        plane_descriptor_snapshot_path,
                        run_root,
                    ),
                    _proof_reference(
                        "activation_intent", activation_plan.intent_path, run_root
                    ),
                    _proof_reference(
                        "activation_receipt", activation_plan.receipt_path, run_root
                    ),
                    _proof_reference(
                        "activation_context", activation_context_path, run_root
                    ),
                    _proof_reference(
                        "activation_rollback_intent",
                        activation_plan.rollback_intent_path,
                        run_root,
                    ),
                    _proof_reference(
                        "activation_rollback",
                        activation_plan.rollback_receipt_path,
                        run_root,
                    ),
                ]
            )
        receipt_core = {
            "schema_version": QUALIFICATION_RECEIPT_SCHEMA_VERSION,
            "kind": "real_harness_conformance",
            "run_id": run_id,
            "target": target,
            "session_profile": session_profile,
            "result": "accepted",
            "controller": controller,
            "campaign_id": authorization["campaign_id"],
            "goal_fingerprint": goal_verification["goal_fingerprint"],
            "executable_fingerprint": manifest.raw["executable"]["sha256"],
            "execution_fingerprint": manifest.execution_fingerprint,
            "version_fingerprint": manifest.raw["executable"]["version_sha256"],
            "platform_fingerprint": evidence["platform_fingerprint"],
            "adapter_fingerprint": manifest.raw["adapter_fingerprint"],
            "protocol_fingerprint": manifest.raw["protocol_fingerprint"],
            "yolo_mapping_sha256": evidence["yolo_mapping_sha256"],
            "launch_plan_sha256": evidence["launch_plan_sha256"],
            "instruction_policy_fingerprint": compiled.manifest[
                "instruction_policy_fingerprint"
            ],
            "capabilities": list(PROBE_CAPABILITIES),
            "accepted_checkpoint_id": followup.checkpoint_id,
            "acceptance_sha256": evidence["acceptance_sha256"],
            "halt_receipt_sha256": halt_sha,
            "plane_activation": activation_terminal,
            "proof_refs": proof_refs,
        }
        controller_attestation = attest_qualification(
            receipt_core,
            authority_root=_authority_root,
        )
        receipt = dict(
            receipt_core,
            controller_attestation=controller_attestation,
        )
        atomic_write_json(receipt_path, receipt)
        receipt_sha = sha256_file(receipt_path, max_bytes=131072)
        _write_state(
            state_path,
            state,
            "complete",
            result="accepted",
            receipt_sha256=receipt_sha,
        )
        verify_qualification_receipt(
            receipt_path,
            _authority_root=_authority_root,
            _current_manifest=manifest,
            _server_process_fn=_server_process_birth_fn,
            _tmux_factory=_tmux_factory,
        )
        _assert_executable_identity(manifest)
        _assert_adapter_identity(manifest, _adapter_fingerprint_fn)
        active_before_terminal = _active_population(
            _active_processes_fn, target, manifest
        )
        if sorted(active_before_terminal, key=lambda item: item["pid"]) != sorted(
            active, key=lambda item: item["pid"]
        ):
            raise IdentityError(
                "protected same-target process population changed before terminal lease"
            )
        accepted_result = {
            "ok": True,
            "run_id": run_id,
            "target": target,
            "result": "accepted",
            "run_root": str(run_root),
            "receipt": str(receipt_path),
            "tmux_preserved": True,
            "attach_command": attach,
        }
        transition_session_lease(
            session=session,
            target=target,
            controller=controller,
            owner=probe_lease_owner,
            instruction_manifest_sha256=instruction_manifest_sha,
            state="halted",
            process=process,
            authority_root=_authority_root,
            _lock_descriptor=lock_descriptor,
        )
        return accepted_result
    except BaseException as exc:
        cleanup_error = None
        if (
            tmux is not None
            and metadata is not None
            and process is not None
            and socket is not None
            and socket_identity is not None
            and server_identity is not None
            and tmux_binary_identity is not None
        ):
            try:
                cleanup = _halt_exact(
                    target=target,
                    tmux=tmux,
                    socket=socket,
                    session=session,
                    pane=metadata["pane"],
                    socket_identity=socket_identity,
                    server_identity=server_identity,
                    tmux_binary_identity=tmux_binary_identity,
                    process=process,
                    process_alive_fn=_process_alive_fn,
                    timeout=halt_timeout,
                    sleep_fn=_sleep_fn,
                    reason="failed_probe_cleanup",
                    journal=halt_control_journal,
                    require_live=False,
                    exact_sigint_fn=_exact_sigint_fn,
                )
                atomic_write_json(halt_path, cleanup)
                evidence["halt_sha256"] = sha256_file(halt_path, max_bytes=65536)
            except Exception as halt_exc:  # Preserve the original failure.
                cleanup_error = "%s: %s" % (
                    halt_exc.__class__.__name__,
                    str(halt_exc)[:500],
                )
        elif (
            provisional_bound
            and tmux is not None
            and metadata is not None
            and socket is not None
            and socket_identity is not None
            and server_identity is not None
            and tmux_binary_identity is not None
        ):
            try:
                cleanup = _halt_provisional_exact(
                    target=target,
                    tmux=tmux,
                    socket=socket,
                    session=session,
                    metadata=metadata,
                    socket_identity=socket_identity,
                    server_identity=server_identity,
                    tmux_binary_identity=tmux_binary_identity,
                    timeout=halt_timeout,
                    sleep_fn=_sleep_fn,
                    journal=halt_control_journal,
                    manifest=manifest,
                    process_birth_fn=_process_birth_fn,
                    process_alive_fn=_process_alive_fn,
                    exact_sigint_fn=_exact_sigint_fn,
                )
                atomic_write_json(halt_path, cleanup)
                evidence["halt_sha256"] = sha256_file(halt_path, max_bytes=65536)
            except BaseException as halt_exc:  # Preserve the original failure.
                cleanup_error = "%s: %s" % (
                    halt_exc.__class__.__name__,
                    str(halt_exc)[:500],
                )
        safe_terminal = not target_launch_attempted
        if isinstance(cleanup, dict) and cleanup.get("stopped") is True:
            safe_terminal = False
            if active is not None:
                try:
                    active_after_cleanup = _active_population(
                        _active_processes_fn, target, manifest
                    )
                    evidence["active_target_processes_after_halt"] = (
                        active_after_cleanup
                    )
                    safe_terminal = sorted(
                        active_after_cleanup, key=lambda item: item["pid"]
                    ) == sorted(active, key=lambda item: item["pid"])
                    if not safe_terminal:
                        cleanup_error = (
                            cleanup_error
                            or "IdentityError: protected same-target process "
                            "population did not return to the pre-launch baseline"
                        )
                except Exception as population_exc:
                    cleanup_error = cleanup_error or "%s: %s" % (
                        population_exc.__class__.__name__,
                        str(population_exc)[:500],
                    )
        if activation_plan is not None and safe_terminal:
            try:
                activation_recovery = recover_activation(
                    activation_plan.raw["transaction_root"]["path"]
                )
                if activation_recovery.state == "active":
                    rollback_activation(activation_recovery.plan)
                elif (
                    activation_recovery.state == "rolled_back"
                    and not activation_recovery.plan.rollback_receipt_path.exists()
                ):
                    rollback_activation(activation_recovery.plan)
                elif activation_recovery.state not in {"prepared", "rolled_back"}:
                    raise IdentityError("activation recovery state is unsupported")
            except Exception as activation_exc:
                safe_terminal = False
                cleanup_error = cleanup_error or "%s: %s" % (
                    activation_exc.__class__.__name__,
                    str(activation_exc)[:500],
                )
        evidence["result"] = "failed"
        evidence["failure"] = {
            "type": exc.__class__.__name__,
            "detail": str(exc)[:1000],
            "cleanup_error": cleanup_error,
            "launch_attempted": target_launch_attempted,
            "server_attempted": server_attempted,
            "target_launch_attempted": target_launch_attempted,
        }
        atomic_write_json(evidence_path, evidence)
        _write_state(
            state_path,
            state,
            "failed",
            result="failed",
            blocker=evidence["failure"],
        )
        if lease_owned and safe_terminal:
            try:
                transition_session_lease(
                    session=session,
                    target=target,
                    controller=controller,
                    owner=probe_lease_owner,
                    instruction_manifest_sha256=instruction_manifest_sha,
                    state="failed",
                    process=process,
                    authority_root=_authority_root,
                    _lock_descriptor=lock_descriptor,
                )
            except (IdentityError, ValidationError):
                # A successful accepted halt may already have committed the
                # terminal halted lease before a later proof write failed.
                pass
        if isinstance(exc, PuppetError):
            raise
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        raise ValidationError("real-harness probe execution failed") from exc
    finally:
        _release_campaign_probe_lock(lock_descriptor)


def recover_probe(
    *,
    target: str,
    proof_root: Path,
    manifest_path: Path,
    mapping_path: Path,
    authorization_path: Path,
    controller: str,
    goal_repo: Path,
    expected_campaign_id: str,
    expected_goal: Dict[str, str],
    run_id: str,
    plane_descriptor: Optional[Path] = None,
    halt_timeout: float = 10.0,
    _tmux_factory: Callable[[Path], TmuxController] = TmuxController,
    _process_birth_fn: Callable[[int], Dict[str, Any]] = process_birth_identity,
    _process_alive_fn: Callable[[Dict[str, Any]], bool] = process_alive,
    _exact_sigint_fn: Callable[[Dict[str, Any]], None] = send_exact_sigint,
    _server_process_birth_fn: Callable[[int], Dict[str, Any]] = process_birth_identity,
    _active_processes_fn: Callable[
        [str], list[Dict[str, Any]]
    ] = active_target_processes,
    _adapter_fingerprint_fn: Callable[[], str] = adapter_implementation_fingerprint,
    _census_target_fn: Callable[[str, str], AdapterManifest] = census_target,
    _sleep_fn: Callable[[float], None] = time.sleep,
    _authority_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Reconcile one persisted probe by exact identity without relaunching it."""
    if target not in TARGETS:
        raise ValidationError("unsupported recovery target")
    validate_identifier(controller, "controller")
    run_id = validate_identifier(run_id, "run id")
    if halt_timeout < 0 or halt_timeout > MAX_HALT_SECONDS:
        raise ValidationError("halt timeout must be between zero and 60 seconds")
    proof_root = absolute_root(str(proof_root), "proof root")
    run_root = ensure_within(
        proof_root / "probes" / run_id,
        proof_root,
        must_exist=True,
    )
    supplied_plane_descriptor = (
        _read_plane_descriptor(plane_descriptor)
        if plane_descriptor is not None
        else None
    )
    plane_descriptor_snapshot_path = run_root / "plane-descriptor.json"
    persisted_plane_descriptor = (
        _read_plane_descriptor(plane_descriptor_snapshot_path)
        if (
            plane_descriptor_snapshot_path.exists()
            or plane_descriptor_snapshot_path.is_symlink()
        )
        else None
    )
    persisted_activation_transaction = run_root / "activation-lane" / "transaction"
    if (
        persisted_activation_transaction.exists()
        or persisted_activation_transaction.is_symlink()
    ) and persisted_plane_descriptor is None:
        raise IdentityError(
            "activation transaction lacks its canonical descriptor snapshot"
        )
    if (
        supplied_plane_descriptor is not None
        and persisted_plane_descriptor is not None
        and canonical_json_bytes(supplied_plane_descriptor)
        != canonical_json_bytes(persisted_plane_descriptor)
    ):
        raise IdentityError(
            "supplied instruction-plane descriptor differs from the probe snapshot"
        )
    if supplied_plane_descriptor is not None and persisted_plane_descriptor is None:
        raise IdentityError(
            "supplied instruction-plane descriptor lacks a canonical probe snapshot"
        )
    plane_descriptor_value = persisted_plane_descriptor
    if plane_descriptor_value is not None and (
        target != "claude" or plane_descriptor_value["target"]["harness"] != target
    ):
        raise ValidationError(
            "native instruction-plane activation is limited to Claude recovery"
        )
    manifest, _, _ = _validated_mapping(
        manifest_path,
        mapping_path,
        target=target,
        allow_claude_activation=plane_descriptor_value is not None,
        adapter_fingerprint_fn=_adapter_fingerprint_fn,
        census_target_fn=_census_target_fn,
    )
    authorization = validate_campaign_authorization(
        authorization_path,
        target=target,
        controller=controller,
        campaign_id=expected_campaign_id,
    )
    goal_verification = verify_campaign_goal(
        authorization,
        repo_root=goal_repo,
        expected_campaign_id=expected_campaign_id,
        expected_goal=expected_goal,
    )
    state_path = run_root / "state.json"
    evidence_path = run_root / "evidence.json"
    recovery_path = run_root / "recovery.json"
    halt_control_journal = Journal(run_root / "halt-control")
    state = validate_qualification_state_schema(
        read_json(state_path, max_bytes=131072, reject_sensitive_fields=True)
    )
    evidence = read_json(evidence_path, max_bytes=131072, reject_sensitive_fields=True)
    evidence = validate_qualification_evidence_schema(evidence)
    instruction_path = ensure_within(
        run_root / "effective-instructions.json",
        run_root,
        must_exist=True,
    )
    instruction_manifest_sha = sha256_file(instruction_path, max_bytes=131072)
    instruction_manifest = validate_instruction_manifest(
        read_json(
            instruction_path,
            max_bytes=131072,
            reject_sensitive_fields=True,
        ),
        target=target,
    )
    expected_instruction_wrapper = {
        "manifest_sha256": instruction_manifest_sha,
        "instruction_policy_fingerprint": instruction_manifest[
            "instruction_policy_fingerprint"
        ],
        "effective_contract_fingerprint": instruction_manifest[
            "effective_contract_fingerprint"
        ],
        "rendered_sha256": instruction_manifest["rendered_sha256"],
        "instruction_plane": instruction_manifest["instruction_plane"],
        "session_profile": instruction_manifest["session_profile"],
        "delivery_transport": instruction_manifest["delivery_transport"],
    }
    if evidence.get("instruction_wrapper") != expected_instruction_wrapper:
        raise IdentityError(
            "persisted probe instruction evidence differs from its manifest"
        )
    state_session_profile = validate_session_profile(
        target, state.get("session_profile")
    )
    evidence_session_profile = validate_session_profile(
        target, evidence.get("session_profile")
    )
    session = _session_id(target, run_id)
    instruction_contract = instruction_manifest["contract_identity"]
    instruction_run = instruction_manifest["run_identity"]
    probe_lease_owner = build_lease_owner(
        activity="probe",
        run_id=run_id,
        campaign_id=expected_campaign_id,
        goal_fingerprint=goal_verification["goal_fingerprint"],
        proof_root=proof_root,
        state_root=run_root,
    )
    if (
        state.get("run_id") != run_id
        or state.get("session") != session
        or state.get("target") != target
        or state.get("controller") != controller
        or evidence.get("run_id") != run_id
        or evidence.get("target") != target
        or evidence.get("controller") != controller
        or evidence.get("manifest_fingerprint") != manifest.fingerprint
        or evidence.get("executable_fingerprint")
        != manifest.raw["executable"]["sha256"]
        or evidence.get("execution_fingerprint") != manifest.execution_fingerprint
        or evidence.get("adapter_fingerprint") != manifest.raw["adapter_fingerprint"]
        or evidence.get("protocol_fingerprint") != manifest.raw["protocol_fingerprint"]
        or state_session_profile != evidence_session_profile
        or instruction_manifest["target"] != target
        or instruction_manifest["session_profile"] != state_session_profile
        or instruction_contract.get("controller") != controller
        or instruction_contract.get("target") != target
        or instruction_contract.get("task_profile") != PROBE_PROFILE
        or instruction_run.get("session") != session
        or instruction_run.get("run_id") != run_id
        or evidence.get("campaign_id") != expected_campaign_id
        or evidence.get("goal_fingerprint") != goal_verification["goal_fingerprint"]
    ):
        raise IdentityError("persisted probe recovery identity mismatch")

    activation_transaction_root = run_root / "activation-lane" / "transaction"
    if (
        activation_transaction_root.exists() or activation_transaction_root.is_symlink()
    ) and plane_descriptor_value is None:
        raise IdentityError(
            "activation transaction exists without descriptor authority"
        )

    def reconcile_plane_activation(*, rollback_active: bool) -> Optional[str]:
        if (
            not activation_transaction_root.exists()
            and not activation_transaction_root.is_symlink()
        ):
            return None
        if plane_descriptor_value is None:
            raise IdentityError(
                "activation transaction exists without descriptor authority"
            )
        recovered_activation = recover_activation(activation_transaction_root)
        if recovered_activation.plan.raw[
            "adapter_manifest_sha256"
        ] != manifest.fingerprint or recovered_activation.plan.raw[
            "descriptor_sha256"
        ] != descriptor_fingerprint(plane_descriptor_value):
            raise IdentityError("persisted activation recovery identity mismatch")
        if recovered_activation.state == "active" and rollback_active:
            rollback_activation(recovered_activation.plan)
            recovered_activation = recover_activation(activation_transaction_root)
            if recovered_activation.state != "rolled_back":
                raise IdentityError("activation rollback did not reach terminal state")
        elif (
            recovered_activation.state == "rolled_back"
            and rollback_active
            and not recovered_activation.plan.rollback_receipt_path.exists()
        ):
            rollback_activation(recovered_activation.plan)
            recovered_activation = recover_activation(activation_transaction_root)
            if recovered_activation.state != "rolled_back":
                raise IdentityError("activation rollback proof was not reconciled")
        if recovered_activation.state not in {"prepared", "active", "rolled_back"}:
            raise IdentityError("activation recovery state is unsupported")
        return recovered_activation.state

    lock_descriptor: Optional[int] = None
    try:
        complete = (
            state.get("phase") == "complete" and state.get("result") == "accepted"
        )
        lock_descriptor, lock_identity = _acquire_campaign_probe_lock(
            _authority_root,
            target=target,
            reject_active_lease=False,
        )
        if complete:
            if plane_descriptor_value is not None:
                if reconcile_plane_activation(rollback_active=False) != "rolled_back":
                    raise IdentityError(
                        "accepted activation probe is not durably rolled back"
                    )
            lease = require_session_lease(
                session=session,
                target=target,
                controller=controller,
                owner=probe_lease_owner,
                instruction_manifest_sha256=instruction_manifest_sha,
                states={"halting", "halted"},
                authority_root=_authority_root,
            )
            process = evidence.get("process")
            if not isinstance(process, dict) or lease.get("process") != process:
                raise IdentityError(
                    "accepted probe process differs from the controller lease"
                )
            receipt_path = run_root / "receipt.json"
            verify_qualification_receipt(
                receipt_path,
                _authority_root=_authority_root,
                _current_manifest=manifest,
                _server_process_fn=_server_process_birth_fn,
                _tmux_factory=_tmux_factory,
            )
            recovered = lease["state"] == "halting"
            if recovered:
                if _process_alive_fn(process):
                    raise IdentityError(
                        "accepted probe still has a live registered target"
                    )
                baseline = evidence.get("active_target_processes_before_launch")
                observed = _active_population(_active_processes_fn, target, manifest)
                if not isinstance(baseline, list) or sorted(
                    baseline, key=lambda item: item["pid"]
                ) != sorted(observed, key=lambda item: item["pid"]):
                    raise IdentityError(
                        "accepted probe protected target population changed"
                    )
                _assert_executable_identity(manifest)
                _assert_adapter_identity(manifest, _adapter_fingerprint_fn)
                transition_session_lease(
                    session=session,
                    target=target,
                    controller=controller,
                    owner=probe_lease_owner,
                    instruction_manifest_sha256=instruction_manifest_sha,
                    state="halted",
                    process=process,
                    authority_root=_authority_root,
                    _lock_descriptor=lock_descriptor,
                )
            return {
                "ok": True,
                "run_id": run_id,
                "target": target,
                "session_profile": state_session_profile,
                "result": "accepted",
                "recovered": recovered,
                "receipt": str(receipt_path),
            }

        current_lease = current_session_lease(_authority_root, target=target)
        unrelated_terminal_lease = (
            current_lease is not None
            and current_lease["session"] != session
            and current_lease["state"] in {"halted", "failed"}
        )
        lease = (
            None
            if current_lease is None or unrelated_terminal_lease
            else require_session_lease(
                session=session,
                target=target,
                controller=controller,
                owner=probe_lease_owner,
                instruction_manifest_sha256=instruction_manifest_sha,
                states={"launching", "active", "halting", "halted", "failed"},
                authority_root=_authority_root,
            )
        )

        tmux_authority_path = run_root / "tmux-authority"
        if not tmux_authority_path.exists():
            persisted_process = evidence.get("process")
            if isinstance(persisted_process, dict) and _process_alive_fn(
                persisted_process
            ):
                raise IdentityError(
                    "missing private launch root still has a live persisted target"
                )
            baseline = evidence.get("active_target_processes_before_launch")
            observed = _active_population(_active_processes_fn, target, manifest)
            if not isinstance(baseline, list) or sorted(
                baseline, key=lambda item: item["pid"]
            ) != sorted(observed, key=lambda item: item["pid"]):
                raise IdentityError(
                    "missing private launch root has an ambiguous target population"
                )
            activation_state = reconcile_plane_activation(rollback_active=True)
            if lease is not None:
                transition_session_lease(
                    session=session,
                    target=target,
                    controller=controller,
                    owner=probe_lease_owner,
                    instruction_manifest_sha256=instruction_manifest_sha,
                    state="failed",
                    process=None,
                    authority_root=_authority_root,
                    _lock_descriptor=lock_descriptor,
                )
            recovery = {
                "schema_version": 1,
                "run_id": run_id,
                "target": target,
                "controller": controller,
                "campaign_id": expected_campaign_id,
                "goal_fingerprint": goal_verification["goal_fingerprint"],
                "authority_lock": lock_identity,
                "identity_source": "private_launch_root_absent",
                "launch_attempted": False,
                "server_attempted": False,
                "target_launch_attempted": False,
                "plane_activation_state": activation_state,
                "cleanup": None,
                "result": "interrupted_probe_reconciled",
            }
            atomic_write_json(recovery_path, recovery)
            blocker = {
                "type": "InterruptedProbeRecovered",
                "detail": "no target was launched; the interrupted run cannot qualify",
                "recovery_sha256": sha256_file(recovery_path, max_bytes=131072),
            }
            _write_state(
                state_path,
                state,
                "failed",
                result="failed",
                blocker=blocker,
                recovery_sha256=blocker["recovery_sha256"],
            )
            return {
                "ok": True,
                "run_id": run_id,
                "target": target,
                "result": "interrupted_probe_reconciled",
                "recovered": True,
                "recovery": str(recovery_path),
                "tmux_preserved": False,
            }
        tmux_authority = ensure_within(tmux_authority_path, run_root, must_exist=True)
        tmux = _tmux_factory(tmux_authority)
        socket = tmux.socket_path(session)
        tmux_record = evidence.get("tmux")
        process = evidence.get("process")
        identity_source = "persisted_launch_identity"
        launch_attempted: Optional[bool]
        server_attempted: Optional[bool]
        target_launch_attempted: Optional[bool]
        failure = evidence.get("failure")
        persisted_launch_attempted = (
            failure.get("launch_attempted")
            if isinstance(failure, dict)
            and isinstance(failure.get("launch_attempted"), bool)
            else None
        )
        persisted_server_attempted = (
            failure.get("server_attempted")
            if isinstance(failure, dict)
            and isinstance(failure.get("server_attempted"), bool)
            else persisted_launch_attempted
        )
        persisted_target_launch_attempted = (
            failure.get("target_launch_attempted")
            if isinstance(failure, dict)
            and isinstance(failure.get("target_launch_attempted"), bool)
            else persisted_launch_attempted
        )
        if not socket.exists():
            launch_attempted = persisted_launch_attempted
            server_attempted = persisted_server_attempted
            target_launch_attempted = persisted_target_launch_attempted
            if isinstance(process, dict) and _process_alive_fn(process):
                raise IdentityError(
                    "absent private probe socket still has a live persisted target"
                )
            baseline = evidence.get("active_target_processes_before_launch")
            observed = _active_population(_active_processes_fn, target, manifest)
            if not isinstance(baseline, list) or sorted(
                baseline, key=lambda item: item["pid"]
            ) != sorted(observed, key=lambda item: item["pid"]):
                raise IdentityError(
                    "absent private probe socket has an ambiguous target population"
                )
            if lease is not None:
                transition_session_lease(
                    session=session,
                    target=target,
                    controller=controller,
                    owner=probe_lease_owner,
                    instruction_manifest_sha256=instruction_manifest_sha,
                    state="failed",
                    process=None,
                    authority_root=_authority_root,
                    _lock_descriptor=lock_descriptor,
                )
            cleanup = {
                "schema_version": 1,
                "session": session,
                "signal_sent": False,
                "stopped": True,
                "tmux_preserved": False,
                "cleanup_scope": "deterministic_private_socket_absent",
            }
            identity_source = "deterministic_private_socket_absent"
            process = None
        elif isinstance(tmux_record, dict) and isinstance(process, dict):
            launch_attempted = True
            server_attempted = True
            target_launch_attempted = True
            if tmux_record.get("socket") != str(socket):
                raise IdentityError("persisted recovery socket identity mismatch")
            socket_identity = tmux_record.get("socket_identity")
            server_identity = tmux_record.get("server_identity")
            tmux_binary_identity = tmux_record.get("tmux_binary_identity")
            pane = tmux_record.get("target_id")
            tmux.assert_tmux_binary_identity(tmux_binary_identity)
            tmux.bind_server_identity(socket, server_identity)
            metadata = tmux.metadata(
                socket=socket,
                session=session,
                pane=pane,
                server_identity=server_identity,
            )
            if metadata.get("pane_pid") != process.get("pid"):
                raise IdentityError("persisted recovery pane identity mismatch")
            if tmux.socket_identity(socket) != socket_identity:
                raise IdentityError("persisted recovery socket identity changed")
            manifest.verify_process_executable(process)
        else:
            launch_attempted = True
            server_attempted = True
            target_launch_attempted = persisted_target_launch_attempted
            identity_source = "unpersisted_private_launch_identity"
            recovery = {
                "schema_version": 1,
                "run_id": run_id,
                "target": target,
                "controller": controller,
                "campaign_id": expected_campaign_id,
                "goal_fingerprint": goal_verification["goal_fingerprint"],
                "authority_lock": lock_identity,
                "identity_source": identity_source,
                "launch_attempted": True,
                "server_attempted": True,
                "target_launch_attempted": target_launch_attempted,
                "plane_activation_state": reconcile_plane_activation(
                    rollback_active=False
                ),
                "cleanup": None,
                "result": "interrupted_probe_fenced",
            }
            atomic_write_json(recovery_path, recovery)
            blocker = {
                "type": "InterruptedProbeIdentityUnpersisted",
                "detail": (
                    "private socket exists without a durably persisted exact launch "
                    "identity; no halt action was attempted"
                ),
                "recovery_sha256": sha256_file(recovery_path, max_bytes=131072),
            }
            _write_state(
                state_path,
                state,
                "failed",
                result="failed",
                blocker=blocker,
                recovery_sha256=blocker["recovery_sha256"],
            )
            raise IdentityError(
                "private launch identity was not durably persisted; target remains fenced"
            )
        if process is not None:
            if lease is None:
                raise IdentityError(
                    "persisted target exists without its controller lease"
                )
            if lease.get("process") is not None and lease["process"] != process:
                raise IdentityError(
                    "persisted recovery process differs from the controller lease"
                )
            if lease["state"] == "launching":
                lease = transition_session_lease(
                    session=session,
                    target=target,
                    controller=controller,
                    owner=probe_lease_owner,
                    instruction_manifest_sha256=instruction_manifest_sha,
                    state="active",
                    process=process,
                    authority_root=_authority_root,
                    _lock_descriptor=lock_descriptor,
                )
            if lease["state"] == "active":
                lease = transition_session_lease(
                    session=session,
                    target=target,
                    controller=controller,
                    owner=probe_lease_owner,
                    instruction_manifest_sha256=instruction_manifest_sha,
                    state="halting",
                    process=process,
                    authority_root=_authority_root,
                    _lock_descriptor=lock_descriptor,
                )
            if lease["state"] in {"halted", "failed"} and _process_alive_fn(process):
                raise IdentityError("terminal controller lease still has a live target")
            cleanup = _halt_exact(
                target=target,
                tmux=tmux,
                socket=socket,
                session=session,
                pane=pane,
                socket_identity=socket_identity,
                server_identity=server_identity,
                tmux_binary_identity=tmux_binary_identity,
                process=process,
                process_alive_fn=_process_alive_fn,
                timeout=halt_timeout,
                sleep_fn=_sleep_fn,
                reason="interrupted_probe_recovery",
                journal=halt_control_journal,
                require_live=False,
                exact_sigint_fn=_exact_sigint_fn,
            )
        baseline = evidence.get("active_target_processes_before_launch")
        observed = _active_population(_active_processes_fn, target, manifest)
        if not isinstance(baseline, list) or sorted(
            baseline, key=lambda item: item["pid"]
        ) != sorted(observed, key=lambda item: item["pid"]):
            raise IdentityError(
                "protected same-target process population changed during recovery"
            )
        activation_state = reconcile_plane_activation(rollback_active=True)
        if lease is not None and lease["state"] in {"launching", "active", "halting"}:
            transition_session_lease(
                session=session,
                target=target,
                controller=controller,
                owner=probe_lease_owner,
                instruction_manifest_sha256=instruction_manifest_sha,
                state="failed",
                process=process,
                authority_root=_authority_root,
                _lock_descriptor=lock_descriptor,
            )
        recovery = {
            "schema_version": 1,
            "run_id": run_id,
            "target": target,
            "controller": controller,
            "campaign_id": expected_campaign_id,
            "goal_fingerprint": goal_verification["goal_fingerprint"],
            "authority_lock": lock_identity,
            "identity_source": identity_source,
            "launch_attempted": launch_attempted,
            "server_attempted": server_attempted,
            "target_launch_attempted": target_launch_attempted,
            "plane_activation_state": activation_state,
            "cleanup": cleanup,
            "result": "interrupted_probe_reconciled",
        }
        atomic_write_json(recovery_path, recovery)
        blocker = {
            "type": "InterruptedProbeRecovered",
            "detail": "exact target halted; the interrupted run cannot qualify",
            "recovery_sha256": sha256_file(recovery_path, max_bytes=131072),
        }
        _write_state(
            state_path,
            state,
            "failed",
            result="failed",
            blocker=blocker,
            recovery_sha256=blocker["recovery_sha256"],
        )
        return {
            "ok": True,
            "run_id": run_id,
            "target": target,
            "result": "interrupted_probe_reconciled",
            "recovered": True,
            "recovery": str(recovery_path),
            "tmux_preserved": (
                cleanup.get("tmux_preserved", True)
                if isinstance(cleanup, dict)
                else True
            ),
        }
    finally:
        _release_campaign_probe_lock(lock_descriptor)
