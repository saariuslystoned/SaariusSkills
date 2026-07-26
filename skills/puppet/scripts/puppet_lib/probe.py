"""Doctor-only bootstrap path for real-harness adapter qualification.

This module is deliberately separate from the normal Puppet session launcher.
It can exercise a doctor-only manifest, but it cannot turn that manifest into a
normal live adapter.  Only the bounded accepted receipt emitted at the end of
this path can later be consumed by ``adapter_lab qualify``.
"""

from __future__ import annotations

import copy
import datetime as dt
import json
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
from .agy_launch import (
    agy_shared_source_environment,
    build_agy_shared_auth_launch_binding,
    revalidate_agy_shared_auth_before_start,
    reject_agy_private_profile_root,
    require_agy_regular_launch_authority,
    run_agy_status_preflight,
    validate_agy_shared_auth_launch_binding,
)
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
from .codex_workspace_plane import (
    DESCRIPTOR_SCHEMA as CODEX_WORKTREE_DESCRIPTOR_SCHEMA,
    TERMINAL_SCHEMA as CODEX_WORKTREE_TERMINAL_SCHEMA,
    validate_codex_worktree_descriptor,
)
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
from .matched_control import (
    MARKER_SIGNAL_RELATIVE_PATH,
    CompiledMarkerInstruction,
    _compile_claude_marker_ready_instruction,
    claude_marker_ready_task,
)
from .matched_control_authority import (
    attest_claude_marker_activation_join,
)
from .matched_control_signal import (
    prepare_claude_marker_signal,
    recover_claude_marker_signal_observation,
    verify_claude_marker_signal_observation,
)
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
    OBSERVED_INPUT_TRANSPORT,
    PROMPT_TRANSPORT,
    SUBMIT_SETTLE_SECONDS,
    input_readiness_strategy_for,
    session_profiles_for,
    startup_settle_seconds_for,
    validate_session_profile,
)
from .session import _await_input_ready
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
from .subscription_profiles import (
    build_subscription_launch_binding,
    subscription_profile_preflight,
    validate_subscription_launch_binding,
)
from .target_population import (
    MAX_TARGET_POPULATION,
    validated_target_population as _validated_target_population,
)
from .tmux import TargetLaunch, TmuxController
from .verdicts import record_acceptance, record_review


MAX_PROBE_SECONDS = 900.0
MAX_HALT_SECONDS = 60.0
POLL_INTERVAL_SECONDS = 0.1
PROBE_PROFILE = QUALIFICATION_PROFILE


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


def _validated_mapping(
    manifest_path: Path,
    mapping_path: Path,
    *,
    target: str,
    allow_claude_activation: bool = False,
    allow_codex_worktree_probe: bool = False,
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
        codex_worktree_exception = (
            allow_codex_worktree_probe
            and target == "codex"
            and mapping.get("project_isolation_declared") is False
            and mapping.get("project_isolation_flags") == []
            and all(
                mapping.get(name) is True
                for name in (
                    "permission_declared",
                    "prompt_transport_declared",
                    "sandbox_disable_declared",
                    "session_profiles_declared",
                )
            )
        )
        if not codex_worktree_exception and (
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
    try:
        decoded = json.loads(text)
    except json.JSONDecodeError:
        return parse_instruction_plane_descriptor(text)
    if isinstance(decoded, dict) and decoded.get("schema") == CODEX_WORKTREE_DESCRIPTOR_SCHEMA:
        return decoded
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


def _observed_handoff_set(fixture: Path) -> set[str]:
    handoffs = ensure_within(fixture / "handoffs", fixture, must_exist=True)
    observed = set()
    for entry in handoffs.iterdir():
        if entry.is_symlink() or not entry.is_file():
            raise IdentityError("probe handoff directory contains a non-regular entry")
        observed.add(entry.name)
    return observed


def _assert_handoff_set(fixture: Path, expected_names: set[str]) -> None:
    observed = _observed_handoff_set(fixture)
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


def _initial_prompt(
    fixture_contract: Dict[str, Any],
    ready: Dict[str, Any],
    *,
    bind_absolute_fixture: bool = False,
) -> str:
    fixture_root = fixture_contract["allowed_fixture_root"]
    contract_path = (
        str(Path(fixture_root) / "contract.json")
        if bind_absolute_fixture
        else "./contract.json"
    )
    ready_path = (
        str(Path(fixture_root) / "handoffs" / "ready.json")
        if bind_absolute_fixture
        else "./handoffs/ready.json"
    )
    fixture_binding = (
        "PUPPET_CONFORMANCE_FIXTURE_ROOT=%s\n"
        % canonical_json_bytes(fixture_root).decode("utf-8")
        if bind_absolute_fixture
        else ""
    )
    return (
        "PUPPET_REAL_HARNESS_CONFORMANCE_V2\n"
        "%s"
        "Read %s and verify schema_version, run_id, nonce, and "
        "allowed_fixture_root. Make no source, repository, account, external-send, "
        "or system changes. Atomically write only %s with the "
        "exact JSON object below, then remain available for one follow-up. The "
        "handoffs directory must contain exactly one regular file after this step: "
        "ready.json. Do not create conformance_handoff.json, a summary, or any "
        "other artifact. Do not claim controller acceptance.\n"
        "run_id=%s\nnonce=%s\nWRITE_READY_JSON=%s"
        % (
            fixture_binding,
            contract_path,
            ready_path,
            fixture_contract["run_id"],
            fixture_contract["nonce"],
            canonical_json_bytes(ready).decode("utf-8"),
        )
    )


def _matched_initial_prompt(
    fixture_contract: Dict[str, Any], ready: Dict[str, Any]
) -> str:
    return claude_marker_ready_task(
        run_id=fixture_contract["run_id"],
        nonce=fixture_contract["nonce"],
        ready=ready,
    )


def _followup_prompt(
    fixture_contract: Dict[str, Any],
    followup: Dict[str, Any],
    *,
    bind_absolute_fixture: bool = False,
) -> str:
    fixture_root = fixture_contract["allowed_fixture_root"]
    followup_path = (
        str(Path(fixture_root) / "handoffs" / "followup.json")
        if bind_absolute_fixture
        else "./handoffs/followup.json"
    )
    fixture_binding = (
        "PUPPET_CONFORMANCE_FIXTURE_ROOT=%s\n"
        % canonical_json_bytes(fixture_root).decode("utf-8")
        if bind_absolute_fixture
        else ""
    )
    return (
        "PUPPET_REAL_HARNESS_FOLLOWUP_V2\n"
        "%s"
        "Verify the same run_id and nonce plus message_id and sequence=1. "
        "Atomically write only %s with the exact JSON object "
        "below, make no other changes, and remain waiting for exact halt. "
        "WRITE_FOLLOWUP_JSON is a complete replacement object: do not copy or "
        "patch ready.json. Its top-level phase and its nested claim status must "
        "both be followup, never ready.\n"
        "run_id=%s\nnonce=%s\nmessage_id=%s\nsequence=1\n"
        "prior_checkpoint_sha256=%s\nWRITE_FOLLOWUP_JSON=%s"
        % (
            fixture_binding,
            followup_path,
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
    transient_missing_handoff_names: Optional[set[str]] = None,
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
            observed_names = _observed_handoff_set(fixture)
            if observed_names != expected_handoff_names:
                if (
                    transient_missing_handoff_names
                    and observed_names
                    == expected_handoff_names - transient_missing_handoff_names
                    and time.monotonic() < deadline
                ):
                    sleep_fn(POLL_INTERVAL_SECONDS)
                    continue
                raise IdentityError(
                    "probe handoff directory contains unexpected artifacts"
                )
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
    subscription_profile_root: Optional[Path] = None,
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
    _subscription_profile_preflight_fn: Callable[
        ..., tuple[Any, Dict[str, Any]]
    ] = subscription_profile_preflight,
) -> Dict[str, Any]:
    """Run one isolated source-free qualification probe.

    Test-only dependency hooks are private keyword arguments.  The public CLI
    always uses the real structural process and private-socket tmux surfaces.
    """

    if target not in TARGETS:
        raise ValidationError("unsupported probe target")
    if target == "agy":
        require_agy_regular_launch_authority(session_profile)
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
    codex_worktree_descriptor = (
        plane_descriptor_value is not None
        and plane_descriptor_value.get("schema") == CODEX_WORKTREE_DESCRIPTOR_SCHEMA
    )
    claude_plane_descriptor = (
        plane_descriptor_value is not None and not codex_worktree_descriptor
    )
    if claude_plane_descriptor and (
        target != "claude" or plane_descriptor_value["target"]["harness"] != target
    ):
        raise ValidationError(
            "native instruction-plane activation is limited to the Claude probe"
        )
    if codex_worktree_descriptor and target != "codex":
        raise ValidationError("Codex worktree descriptor target changed")
    manifest, mapping, argv = _validated_mapping(
        manifest_path,
        mapping_path,
        target=target,
        allow_claude_activation=claude_plane_descriptor,
        allow_codex_worktree_probe=codex_worktree_descriptor,
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
    subscription_binding: Optional[Dict[str, Any]]
    if target == "agy":
        reject_agy_private_profile_root(subscription_profile_root)
        subscription_context = None
        subscription_status = None
        subscription_binding = None
    else:
        if subscription_profile_root is None:
            raise ValidationError(
                "regular qualification requires an explicit private subscription profile"
            )
        subscription_context, subscription_status = _subscription_profile_preflight_fn(
            profile_root=subscription_profile_root,
            expected_target=target,
            expected_executable_path=manifest.raw["executable"]["resolved_path"],
        )
        if subscription_status.get("login_state") != "logged_in":
            raise IdentityError(
                "private subscription profile is not authenticated for qualification"
            )
        subscription_binding = build_subscription_launch_binding(
            subscription_context, subscription_status
        )
    if codex_worktree_descriptor:
        validate_codex_worktree_descriptor(
            plane_descriptor_value,
            expected_controller=controller,
            expected_campaign_id=authorization["campaign_id"],
            expected_goal_fingerprint=goal_verification["goal_fingerprint"],
            expected_executable_sha256=manifest.raw["executable"]["sha256"],
            expected_subscription_profile_root=subscription_context.profile_root,
        )
    if target != "agy":
        validate_subscription_launch_binding(
            subscription_binding,
            expected_target=target,
            require_logged_in=True,
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
    controller_contract_path = run_root / "controller-contract.json"
    subscription_profile_path = run_root / "subscription-profile.json"
    launch_plan_path = run_root / "launch-plan.json"
    plane_descriptor_snapshot_path = run_root / "plane-descriptor.json"
    activation_context_path = run_root / "activation-context.json"
    matched_attestation_path = run_root / "matched-control-attestation.json"
    matched_signal_path = run_root / "matched-control-signal.json"
    activation_lane_root = run_root / "activation-lane"
    activation_ephemeral_root = activation_lane_root / "ephemeral"
    activation_transaction_root = activation_lane_root / "transaction"
    activation_config_root = (
        Path(subscription_context.bindings["CLAUDE_CONFIG_DIR"])
        if claude_plane_descriptor
        else activation_lane_root / "unused-config"
    )
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
    matched_compiled: Optional[CompiledMarkerInstruction] = None
    matched_activation_attestation: Optional[Dict[str, Any]] = None
    matched_signal_guard: Optional[Any] = None
    matched_signal_observation: Optional[Dict[str, Any]] = None
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
        "subscription_profile_sha256": None,
        "launch_identity": None,
        "input_transport": OBSERVED_INPUT_TRANSPORT,
        "input_readiness_strategy": input_readiness_strategy_for(target),
        "startup_settle_seconds": startup_settle_seconds_for(target),
        "submit_settle_seconds": SUBMIT_SETTLE_SECONDS,
        "payload_argv_absent": True,
        "instruction_wrapper": None,
        "plane_activation": None,
        "workspace_isolation": None,
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
        if subscription_binding is not None:
            atomic_write_json(subscription_profile_path, subscription_binding)
            evidence["subscription_profile_sha256"] = sha256_file(
                subscription_profile_path, max_bytes=131072
            )
        if plane_descriptor_value is not None:
            atomic_write_json(
                plane_descriptor_snapshot_path,
                plane_descriptor_value,
            )
        evidence["authorization_sha256"] = sha256_file(
            authorization_snapshot_path, max_bytes=65536
        )
        atomic_write_json(evidence_path, evidence)
        if claude_plane_descriptor:
            activation_lane_root.mkdir(mode=0o700)
        fixture = (
            run_root / "fixture"
            if not claude_plane_descriptor
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
        atomic_write_json(controller_contract_path, controller_contract.raw)
        ready_value = _handoff_value(
            phase="ready",
            session=session,
            fixture_contract=fixture_contract,
            manifest=manifest,
        )
        contract_identity = {
            "fingerprint": controller_contract.fingerprint,
            "controller": controller,
            "target": target,
            "task_profile": profile,
        }
        workspace_identity = {
            "fixture_fingerprint": fixture_fingerprint,
            "workspace": "isolated_conformance_fixture",
        }
        run_identity = {
            "session": session,
            "run_id": run_id,
            "nonce": fixture_contract["nonce"],
        }
        ready_task = (
            _initial_prompt(
                fixture_contract,
                ready_value,
                bind_absolute_fixture=codex_worktree_descriptor,
            )
            if not claude_plane_descriptor
            else _matched_initial_prompt(fixture_contract, ready_value)
        )
        if not claude_plane_descriptor:
            compiled = compile_instruction_wrapper(
                target=target,
                task=ready_task,
                contract_identity=contract_identity,
                workspace_identity=workspace_identity,
                run_identity=run_identity,
                session_profile=session_profile,
                model_binding="default",
                effort_binding="default",
                runtime_contract_layer={
                    "mutation_owner": controller_contract.mutation_owner,
                    "allowed_modes": sorted(controller_contract.allowed_modes),
                    "hard_gates": sorted(controller_contract.hard_gates),
                },
            )
        else:
            matched_compiled = _compile_claude_marker_ready_instruction(
                descriptor=plane_descriptor_value,
                contract_identity=contract_identity,
                workspace_identity=workspace_identity,
                run_identity=run_identity,
                ready_task=ready_task,
            )
            compiled = matched_compiled
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
        launch_repo = fixture
        if not claude_plane_descriptor:
            if target == "agy":
                launch_environment, launch_identity = build_launch_identity(
                    target=target,
                    repo=launch_repo,
                    argv=argv,
                    source_environment=agy_shared_source_environment(),
                )
            else:
                if subscription_context is None:
                    raise IdentityError(
                        "subscription profile launch context is unavailable"
                    )
                admitted_lane_root = subscription_context.profile_root
                if codex_worktree_descriptor:
                    # The fixture remains the bounded conformance task workspace.
                    # Codex starts in the candidate worktree so its workspace plane
                    # binds there; terminal workspace_isolation independently proves
                    # that real process cwd while prompts use absolute fixture paths.
                    launch_repo = Path(plane_descriptor_value["candidate_root"])
                launch_environment, launch_identity = build_launch_identity(
                    target=target,
                    repo=launch_repo,
                    argv=argv,
                    source_environment=subscription_context.source_environment,
                    bindings=subscription_context.bindings,
                    admitted_lane_root=admitted_lane_root,
                )
            manifest.verify_launch_execution_environment(launch_environment)
            launch_plan = build_admitted_launch_plan(
                target=target,
                session=session,
                run_id=run_id,
                repo=launch_repo,
                argv=argv,
                environment=launch_environment,
                admitted_lane_root=admitted_lane_root,
            )
            if target == "agy":
                status = run_agy_status_preflight(
                    executable_path=Path(
                        manifest.raw["executable"]["resolved_path"]
                    ),
                    cwd=launch_repo,
                    environment=launch_environment,
                )
                subscription_binding = build_agy_shared_auth_launch_binding(
                    executable_path=Path(
                        manifest.raw["executable"]["resolved_path"]
                    ),
                    cwd=launch_repo,
                    environment=launch_environment,
                    status=status,
                )
                validate_agy_shared_auth_launch_binding(
                    subscription_binding,
                    expected_executable_path=manifest.raw["executable"][
                        "resolved_path"
                    ],
                    expected_launch_identity=launch_identity,
                )
                atomic_write_json(
                    subscription_profile_path,
                    subscription_binding,
                )
                evidence["subscription_profile_sha256"] = sha256_file(
                    subscription_profile_path,
                    max_bytes=131072,
                )
        else:
            for activation_root in (
                activation_ephemeral_root,
                activation_transaction_root,
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
            if matched_compiled is None:
                raise IdentityError(
                    "matched-control compilation is unavailable before activation"
                )
            matched_activation_attestation = attest_claude_marker_activation_join(
                matched_compiled,
                activation_plan=activation_plan,
                descriptor=plane_descriptor_value,
                adapter_manifest=manifest,
            )
            matched_signal_guard = prepare_claude_marker_signal(
                matched_compiled,
                activation_plan=activation_plan,
                descriptor=plane_descriptor_value,
                adapter_manifest=manifest,
                activation_attestation=matched_activation_attestation,
            )
            atomic_write_json(
                matched_attestation_path,
                matched_activation_attestation,
            )
            _write_state(
                state_path,
                state,
                "preflight",
                matched_control_attestation_sha256=sha256_file(
                    matched_attestation_path, max_bytes=131072
                ),
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
                admitted_lane_root=subscription_context.profile_root,
                source_environment=subscription_context.source_environment,
            )
            activation_public_context = activation_context.to_public_dict()
            atomic_write_json(activation_context_path, activation_public_context)
            argv = activation_context.argv
            launch_environment = activation_context.environment
            launch_identity = activation_context.launch_identity
            launch_plan = activation_context.admitted_launch_plan
            admitted_lane_root = subscription_context.profile_root
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
                refreshed_context, refreshed_status = (
                    _subscription_profile_preflight_fn(
                        profile_root=subscription_context.profile_root,
                        expected_target=target,
                        expected_executable_path=manifest.raw["executable"][
                            "resolved_path"
                        ],
                    )
                )
                refreshed_binding = build_subscription_launch_binding(
                    refreshed_context, refreshed_status
                )
                validate_subscription_launch_binding(
                    refreshed_binding,
                    expected_target=target,
                    require_logged_in=True,
                )
                if refreshed_binding != subscription_binding:
                    raise IdentityError(
                        "subscription profile authority changed before target start"
                    )
                activation_context = revalidate_activation_launch_context(
                    activation_context,
                    activation_plan,
                    adapter_manifest=manifest,
                    workspace_root=fixture,
                    config_root=activation_config_root,
                    admitted_lane_root=refreshed_context.profile_root,
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
                if target == "agy":
                    if subscription_binding is None:
                        raise IdentityError(
                            "AGY shared-auth binding is unavailable before target start"
                        )
                    refreshed_environment, refreshed_identity = (
                        revalidate_agy_shared_auth_before_start(
                            executable_path=Path(
                                manifest.raw["executable"]["resolved_path"]
                            ),
                            cwd=launch_repo,
                            argv=argv,
                            admitted_environment=launch_environment,
                            admitted_launch_identity=launch_identity,
                            admitted_binding=subscription_binding,
                        )
                    )
                    refreshed = TargetLaunch(
                        argv=list(argv),
                        environment=refreshed_environment,
                        launch_identity=refreshed_identity,
                    )
                elif subscription_context is None or subscription_binding is None:
                    raise IdentityError(
                        "subscription profile authority is unavailable before target start"
                    )
                else:
                    refreshed_context, refreshed_status = (
                        _subscription_profile_preflight_fn(
                            profile_root=subscription_context.profile_root,
                            expected_target=target,
                            expected_executable_path=manifest.raw["executable"][
                                "resolved_path"
                            ],
                        )
                    )
                    refreshed_binding = build_subscription_launch_binding(
                        refreshed_context, refreshed_status
                    )
                    validate_subscription_launch_binding(
                        refreshed_binding,
                        expected_target=target,
                        require_logged_in=True,
                    )
                    refreshed_environment, refreshed_identity = build_launch_identity(
                        target=target,
                        repo=launch_repo,
                        argv=argv,
                        source_environment=refreshed_context.source_environment,
                        bindings=refreshed_context.bindings,
                        admitted_lane_root=refreshed_context.profile_root,
                    )
                    manifest.verify_launch_execution_environment(refreshed_environment)
                    if (
                        refreshed_binding != subscription_binding
                        or refreshed_environment != launch_environment
                        or refreshed_identity != launch_identity
                    ):
                        raise IdentityError(
                            "subscription profile authority changed before target start"
                        )
                    refreshed = TargetLaunch(
                        argv=list(argv),
                        environment=refreshed_environment,
                        launch_identity=refreshed_identity,
                    )
            target_launch_attempted = True
            return refreshed

        metadata = tmux.launch(
            session=session,
            target=target,
            repo=launch_repo,
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
        settle_result = _await_input_ready(
            target=target,
            tmux=tmux,
            manifest=manifest,
            socket=socket,
            session=session,
            pane=metadata["pane"],
            pane_pid=metadata["pane_pid"],
            repo=launch_repo,
            argv=argv,
            process=process,
            server_identity=server_identity,
            sleep_fn=_sleep_fn,
            verify_structural_settle=False,
            process_alive_fn=lambda: _process_alive_fn(process),
        )
        del settle_result
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
            expected_handoff_names=(
                {"ready.json"}
                if activation_plan is None
                else {"ready.json", Path(MARKER_SIGNAL_RELATIVE_PATH).name}
            ),
            transient_missing_handoff_names=(
                None
                if activation_plan is None
                else {Path(MARKER_SIGNAL_RELATIVE_PATH).name}
            ),
            timeout=timeout,
            sleep_fn=_sleep_fn,
        )
        if activation_plan is not None:
            if (
                plane_descriptor_value is None
                or matched_compiled is None
                or matched_activation_attestation is None
                or matched_signal_guard is None
            ):
                raise IdentityError(
                    "matched-control signal authority is incomplete after ready"
                )
            matched_signal_observation = matched_signal_guard.consume()
            verify_claude_marker_signal_observation(
                matched_signal_observation,
                matched_compiled,
                activation_plan=activation_plan,
                descriptor=plane_descriptor_value,
                adapter_manifest=manifest,
                activation_attestation=matched_activation_attestation,
            )
            atomic_write_json(matched_signal_path, matched_signal_observation)
        evidence["ready"] = ready.reference()
        atomic_write_json(evidence_path, evidence)
        _write_state(
            state_path,
            state,
            "ready_validated",
            ready_checkpoint_id=ready.checkpoint_id,
            **(
                {
                    "matched_control_signal_sha256": sha256_file(
                        matched_signal_path, max_bytes=131072
                    )
                }
                if activation_plan is not None
                else {}
            ),
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
            _followup_prompt(
                fixture_contract,
                followup_value,
                bind_absolute_fixture=codex_worktree_descriptor,
            ),
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
                or matched_compiled is None
                or matched_activation_attestation is None
                or matched_signal_observation is None
            ):
                raise IdentityError("activation proof family is incomplete")
            terminal_signal_observation = recover_claude_marker_signal_observation(
                matched_compiled,
                activation_plan=activation_plan,
                descriptor=plane_descriptor_value,
                adapter_manifest=manifest,
                activation_attestation=matched_activation_attestation,
            )
            if terminal_signal_observation != matched_signal_observation:
                raise IdentityError(
                    "matched-control signal changed before terminal activation"
                )
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
        if codex_worktree_descriptor:
            validate_codex_worktree_descriptor(
                plane_descriptor_value,
                expected_controller=controller,
                expected_campaign_id=authorization["campaign_id"],
                expected_goal_fingerprint=goal_verification["goal_fingerprint"],
                expected_executable_sha256=manifest.raw["executable"]["sha256"],
                expected_subscription_profile_root=subscription_context.profile_root,
            )
            evidence["workspace_isolation"] = {
                "schema": CODEX_WORKTREE_TERMINAL_SCHEMA,
                "terminal_state": "controller_verified_after_exact_halt",
                "descriptor_sha256": plane_descriptor_value["descriptor_sha256"],
                "candidate_root": plane_descriptor_value["candidate_root"],
                "candidate_branch": plane_descriptor_value["candidate_branch"],
                "candidate_head": plane_descriptor_value["candidate_head"],
                "startup_cwd": launch_plan["cwd"],
                "controller_contract_sha256": sha256_file(
                    controller_contract_path, max_bytes=131072
                ),
                "instruction_manifest_sha256": instruction_manifest_sha,
                "executable_sha256": manifest.raw["executable"]["sha256"],
                "subscription_profile_sha256": evidence[
                    "subscription_profile_sha256"
                ],
                "launch_plan_sha256": evidence["launch_plan_sha256"],
            }
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
        ]
        proof_refs.append(
            _proof_reference(
                "subscription_profile", subscription_profile_path, run_root
            )
        )
        proof_refs.extend(
            [
                _proof_reference("evidence", evidence_path, run_root),
                _proof_reference("launch_plan", launch_plan_path, run_root),
                _proof_reference("instructions", instruction_path, run_root),
                _proof_reference("halt", halt_path, run_root),
                _proof_reference(
                    "ready", fixture / "handoffs" / "ready.json", run_root
                ),
                _proof_reference(
                    "followup", fixture / "handoffs" / "followup.json", run_root
                ),
                _proof_reference("review", review_path, run_root),
                _proof_reference("acceptance", acceptance_path, run_root),
            ]
        )
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
                    _proof_reference(
                        "matched_control_attestation",
                        matched_attestation_path,
                        run_root,
                    ),
                    _proof_reference(
                        "matched_control_signal",
                        matched_signal_path,
                        run_root,
                    ),
                ]
            )
        if codex_worktree_descriptor:
            proof_refs.extend(
                [
                    _proof_reference(
                        "workspace_descriptor",
                        plane_descriptor_snapshot_path,
                        run_root,
                    ),
                    _proof_reference(
                        "controller_contract", controller_contract_path, run_root
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
            "subscription_profile_sha256": evidence["subscription_profile_sha256"],
            "instruction_policy_fingerprint": compiled.manifest[
                "instruction_policy_fingerprint"
            ],
            "capabilities": list(PROBE_CAPABILITIES),
            "accepted_checkpoint_id": followup.checkpoint_id,
            "acceptance_sha256": evidence["acceptance_sha256"],
            "halt_receipt_sha256": halt_sha,
            "plane_activation": activation_terminal,
            "workspace_isolation": evidence["workspace_isolation"],
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
        if matched_signal_guard is not None:
            matched_signal_guard.close()
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
    codex_worktree_descriptor = (
        plane_descriptor_value is not None
        and plane_descriptor_value.get("schema") == CODEX_WORKTREE_DESCRIPTOR_SCHEMA
    )
    claude_plane_descriptor = (
        plane_descriptor_value is not None and not codex_worktree_descriptor
    )
    if claude_plane_descriptor and (
        target != "claude" or plane_descriptor_value["target"]["harness"] != target
    ):
        raise ValidationError(
            "native instruction-plane activation is limited to Claude recovery"
        )
    if codex_worktree_descriptor and target != "codex":
        raise ValidationError("Codex worktree descriptor target changed")
    manifest, _, _ = _validated_mapping(
        manifest_path,
        mapping_path,
        target=target,
        allow_claude_activation=claude_plane_descriptor,
        allow_codex_worktree_probe=codex_worktree_descriptor,
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
    matched_attestation_path = run_root / "matched-control-attestation.json"
    matched_signal_path = run_root / "matched-control-signal.json"
    if (
        activation_transaction_root.exists() or activation_transaction_root.is_symlink()
    ) and not claude_plane_descriptor:
        raise IdentityError(
            "activation transaction exists without descriptor authority"
        )

    def reconcile_plane_activation(*, rollback_active: bool) -> Optional[str]:
        if (
            not activation_transaction_root.exists()
            and not activation_transaction_root.is_symlink()
        ):
            return None
        if not claude_plane_descriptor:
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

    def reconcile_matched_control_signal(
        *, require_observation: bool
    ) -> Optional[Dict[str, Any]]:
        if not claude_plane_descriptor:
            return None
        fixture = run_root / "activation-lane" / "workspace"
        signal_leaf = fixture / MARKER_SIGNAL_RELATIVE_PATH
        ready_path = fixture / "handoffs" / "ready.json"
        if not matched_attestation_path.exists():
            if signal_leaf.exists() or signal_leaf.is_symlink():
                raise IdentityError(
                    "matched-control signal exists without persisted attestation"
                )
            if require_observation:
                raise IdentityError(
                    "accepted activation lacks matched-control attestation"
                )
            return None
        attestation_sha = sha256_file(
            matched_attestation_path,
            max_bytes=131072,
        )
        if state.get("matched_control_attestation_sha256") != attestation_sha:
            raise IdentityError(
                "matched-control attestation reference changed during recovery"
            )
        if not ready_path.exists():
            if signal_leaf.exists() or signal_leaf.is_symlink():
                raise IdentityError(
                    "matched-control signal exists without the exact ready checkpoint"
                )
            if require_observation:
                raise IdentityError(
                    "accepted activation lacks the exact matched-control ready checkpoint"
                )
            return None

        fixture_contract = read_json(
            fixture / "contract.json",
            max_bytes=131072,
            reject_sensitive_fields=True,
        )
        ready_value = read_json(
            ready_path,
            max_bytes=131072,
            reject_sensitive_fields=True,
        )
        matched_compiled = _compile_claude_marker_ready_instruction(
            descriptor=plane_descriptor_value,
            contract_identity=instruction_manifest["contract_identity"],
            workspace_identity=instruction_manifest["workspace_identity"],
            run_identity=instruction_manifest["run_identity"],
            ready_task=_matched_initial_prompt(fixture_contract, ready_value),
        )
        if canonical_json_bytes(matched_compiled.manifest) != canonical_json_bytes(
            instruction_manifest
        ):
            raise IdentityError(
                "matched-control recovery source differs from the instruction manifest"
            )
        recovered_activation = recover_activation(activation_transaction_root)
        activation_attestation = read_json(
            matched_attestation_path,
            max_bytes=131072,
            reject_sensitive_fields=True,
        )
        observation = recover_claude_marker_signal_observation(
            matched_compiled,
            activation_plan=recovered_activation.plan,
            descriptor=plane_descriptor_value,
            adapter_manifest=manifest,
            activation_attestation=activation_attestation,
        )
        if observation is None:
            if require_observation:
                raise IdentityError(
                    "accepted activation lacks matched-control signal observation"
                )
            return None
        if matched_signal_path.exists():
            persisted_observation = read_json(
                matched_signal_path,
                max_bytes=131072,
                reject_sensitive_fields=True,
            )
            if persisted_observation != observation:
                raise IdentityError("persisted matched-control signal receipt changed")
        else:
            atomic_write_json(matched_signal_path, observation)
        observation_sha = sha256_file(matched_signal_path, max_bytes=131072)
        persisted_sha = state.get("matched_control_signal_sha256")
        if persisted_sha is not None and persisted_sha != observation_sha:
            raise IdentityError(
                "matched-control signal reference changed during recovery"
            )
        _write_state(
            state_path,
            state,
            state["phase"],
            matched_control_signal_sha256=observation_sha,
        )
        return observation

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
            reconcile_matched_control_signal(require_observation=True)
            if claude_plane_descriptor:
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
            reconcile_matched_control_signal(require_observation=False)
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
        reconcile_matched_control_signal(require_observation=False)
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
