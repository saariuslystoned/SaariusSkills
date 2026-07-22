"""Doctor-only bootstrap path for real-harness adapter qualification.

This module is deliberately separate from the normal Puppet session launcher.
It can exercise a doctor-only manifest, but it cannot turn that manifest into a
normal live adapter.  Only the bounded accepted receipt emitted at the end of
this path can later be consumed by ``adapter_lab qualify``.
"""

from __future__ import annotations

import copy
import datetime as dt
import fcntl
import os
import secrets
import stat
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from .adapter_manifest import (
    AdapterManifest,
    PROBE_CAPABILITIES,
    verify_qualification_receipt,
)
from .adapters import adapter_for
from .campaign import (
    active_target_processes,
    parallel_target_override,
    validate_campaign_authorization,
)
from .conformance import create_fixture, tree_fingerprint
from .contracts import Contract, MANDATORY_HARD_GATES, TARGETS
from .census import adapter_implementation_fingerprint, census_target
from .errors import ConflictError, IdentityError, PuppetError, ValidationError
from .handoffs import ValidatedHandoff, validate_handoff
from .registry import process_alive, process_birth_identity
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
from .tmux import TmuxController
from .verdicts import record_acceptance, record_review


MAX_PROBE_SECONDS = 900.0
MAX_HALT_SECONDS = 60.0
POLL_INTERVAL_SECONDS = 0.1
PROBE_PROFILE = "source-free-pass-b-v1"


def _utc_now() -> str:
    return (
        dt.datetime.now(dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _new_run_id(target: str) -> str:
    return "probe-%s-%s" % (target, secrets.token_hex(8))


def _acquire_campaign_probe_lock(proof_root: Path) -> tuple[int, Dict[str, Any]]:
    lock_root = proof_root / "probe-locks"
    if lock_root.exists() and lock_root.is_symlink():
        raise IdentityError("campaign probe lock root is a symlink")
    lock_root.mkdir(mode=0o700, exist_ok=True)
    ensure_within(lock_root, proof_root, must_exist=True)
    lock_path = lock_root / "real-harness.lock"
    flags = os.O_CREAT | os.O_RDWR
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(str(lock_path), flags, 0o600)
    try:
        details = os.fstat(descriptor)
        if (
            not stat.S_ISREG(details.st_mode)
            or details.st_uid != os.getuid()
            or stat.S_IMODE(details.st_mode) & 0o077
        ):
            raise IdentityError("campaign probe lock is not user-private")
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ConflictError("another real-harness probe owns the campaign lock") from exc
        return descriptor, {
            "path": str(lock_path.resolve(strict=True)),
            "device": details.st_dev,
            "inode": details.st_ino,
            "uid": details.st_uid,
            "mode": stat.S_IMODE(details.st_mode),
        }
    except BaseException:
        os.close(descriptor)
        raise


def _release_campaign_probe_lock(descriptor: Optional[int]) -> None:
    if descriptor is None:
        return
    try:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
    finally:
        os.close(descriptor)


def _session_id(target: str, run_id: str) -> str:
    digest = sha256_bytes(run_id.encode("utf-8"))[:16]
    return validate_identifier("probe-%s-%s" % (target, digest), "session")


def _validated_mapping(
    manifest_path: Path,
    mapping_path: Path,
    *,
    target: str,
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
        raise IdentityError("doctor manifest does not bind the current adapter implementation")
    observed = census_target_fn(target, implementation_fingerprint)
    for name in ("platform", "executable", "adapter_fingerprint", "protocol_fingerprint"):
        if observed.raw[name] != candidate.raw[name]:
            raise IdentityError("fresh zero-agent census identity changed: %s" % name)
    if observed.raw["yolo_mapping"] != mapping:
        raise IdentityError("fresh zero-agent census YOLO mapping changed")
    if not mapping.get("complete"):
        raise ValidationError("candidate YOLO and sandbox-off mapping is incomplete")
    argv = list(mapping["launch_argv"])
    _assert_executable_identity(candidate)
    executable = Path(candidate.raw["executable"]["resolved_path"])
    if argv[0] != str(executable):
        raise IdentityError("candidate mapping does not launch the exact executable")
    return candidate, mapping, argv


def _assert_executable_identity(manifest: AdapterManifest) -> None:
    executable = Path(manifest.raw["executable"]["resolved_path"])
    if executable.is_symlink() or not executable.is_file():
        raise IdentityError("fingerprinted executable is unavailable or a symlink")
    details = executable.stat()
    expected = manifest.raw["executable"]
    observed = {
        "device": details.st_dev,
        "inode": details.st_ino,
        "size": details.st_size,
        "mtime_ns": details.st_mtime_ns,
    }
    if any(observed[name] != expected[name] for name in observed):
        raise IdentityError("fingerprinted executable file identity changed")
    if sha256_file(executable) != expected["sha256"]:
        raise IdentityError("fingerprinted executable content changed")


def _assert_adapter_identity(
    manifest: AdapterManifest, fingerprint_fn: Callable[[], str]
) -> None:
    if fingerprint_fn() != manifest.raw["adapter_fingerprint"]:
        raise IdentityError("probe adapter implementation identity changed")


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
) -> Contract:
    raw = {
        "schema_version": 1,
        "objective": "Run the shared source-free real-harness conformance contract",
        "campaign_authorization_id": campaign_id,
        "controller": controller,
        "target": target,
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
        "schema_version": 1,
        "checkpoint_kind": "conformance",
        "session": session,
        "run_id": fixture_contract["run_id"],
        "nonce": fixture_contract["nonce"],
        "phase": phase,
        "sequence": 0 if phase == "ready" else 1,
        "executable_fingerprint": manifest.raw["executable"]["sha256"],
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
        "PUPPET_REAL_HARNESS_CONFORMANCE_V1\n"
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


def _followup_prompt(
    fixture_contract: Dict[str, Any], followup: Dict[str, Any]
) -> str:
    return (
        "PUPPET_REAL_HARNESS_FOLLOWUP_V1\n"
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
    process: Dict[str, Any],
    process_alive_fn: Callable[[Dict[str, Any]], bool],
) -> Dict[str, Any]:
    if tmux.socket_identity(socket) != socket_identity:
        raise IdentityError("probe tmux socket identity changed")
    metadata = tmux.metadata(socket=socket, session=session, pane=pane)
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
    process: Dict[str, Any],
    process_alive_fn: Callable[[Dict[str, Any]], bool],
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
            process=process,
            process_alive_fn=process_alive_fn,
        )
        if path.exists():
            handoff = validate_handoff(
                path, allowed_roots=[fixture], expected=expected
            )
            if handoff.data != expected_data:
                raise IdentityError("probe handoff content differs from the exact contract")
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
    process: Dict[str, Any],
    process_alive_fn: Callable[[Dict[str, Any]], bool],
    timeout: float,
    sleep_fn: Callable[[float], None],
    reason: str,
    require_live: bool = False,
) -> Dict[str, Any]:
    target_alive = process_alive_fn(process)
    if require_live and not target_alive:
        raise IdentityError("probe target stopped before the required controller halt")
    signal_sent = False
    signal_name = "none_already_stopped"
    if target_alive:
        deadline = time.monotonic() + timeout
        sent_keys = []
        for key in adapter_for(target).graceful_halt_keys:
            if not process_alive_fn(process):
                break
            _assert_runtime(
                tmux=tmux,
                socket=socket,
                session=session,
                pane=pane,
                pane_pid=process["pid"],
                socket_identity=socket_identity,
                process=process,
                process_alive_fn=process_alive_fn,
            )
            if key == "C-c":
                tmux.interrupt(socket=socket, session=session, pane=pane)
            else:
                tmux.send_control(
                    socket=socket,
                    session=session,
                    pane=pane,
                    key=key,
                )
            sent_keys.append(key)
            remaining = max(0.0, deadline - time.monotonic())
            if remaining:
                sleep_fn(min(0.25, remaining))
        signal_sent = bool(sent_keys)
        if sent_keys == ["C-d", "C-d"]:
            signal_name = "tmux_exact_pane_ctrl_d_twice"
        elif sent_keys == ["C-d"]:
            signal_name = "tmux_exact_pane_ctrl_d_once_target_stopped"
        elif sent_keys == ["C-c"]:
            signal_name = "tmux_exact_pane_ctrl_c"
        elif sent_keys:
            raise IdentityError("exact halt used an unexpected control sequence")
        while process_alive_fn(process) and time.monotonic() < deadline:
            sleep_fn(POLL_INTERVAL_SECONDS)
    stopped = not process_alive_fn(process)
    tmux_preserved = tmux.exists(socket, session)
    if not stopped:
        raise IdentityError(
            "exact probe target did not stop gracefully; no broad signal was attempted"
        )
    if not tmux_preserved:
        raise IdentityError("probe tmux evidence session was not preserved")
    if tmux.socket_identity(socket) != socket_identity:
        raise IdentityError("probe tmux socket identity changed during halt")
    stopped_metadata = tmux.metadata(socket=socket, session=session, pane=pane)
    if (
        stopped_metadata.get("session") != session
        or stopped_metadata.get("pane") != pane
        or not stopped_metadata.get("pane_dead")
    ):
        raise IdentityError("probe target stopped without a preserved dead evidence pane")
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
    timeout: float,
    sleep_fn: Callable[[float], None],
) -> Dict[str, Any]:
    """Clean a newly launched private pane when process birth binding failed."""

    if tmux.socket_identity(socket) != socket_identity:
        raise IdentityError("provisional probe tmux socket identity changed")
    current = tmux.metadata(
        socket=socket, session=session, pane=metadata.get("pane")
    )
    if any(
        current.get(name) != metadata.get(name)
        for name in ("session", "pane", "pane_pid")
    ):
        raise IdentityError("provisional probe tmux identity changed")
    deadline = time.monotonic() + timeout
    sent_keys = []
    for key in adapter_for(target).graceful_halt_keys:
        current = tmux.metadata(socket=socket, session=session, pane=metadata["pane"])
        if current.get("pane_dead"):
            break
        if any(
            current.get(name) != metadata.get(name)
            for name in ("session", "pane", "pane_pid")
        ):
            raise IdentityError("provisional probe tmux identity changed")
        if key == "C-c":
            tmux.interrupt(socket=socket, session=session, pane=metadata["pane"])
        else:
            tmux.send_control(
                socket=socket,
                session=session,
                pane=metadata["pane"],
                key=key,
            )
        sent_keys.append(key)
        remaining = max(0.0, deadline - time.monotonic())
        if remaining:
            sleep_fn(min(0.25, remaining))
    current = tmux.metadata(socket=socket, session=session, pane=metadata["pane"])
    while not current.get("pane_dead") and time.monotonic() < deadline:
        sleep_fn(POLL_INTERVAL_SECONDS)
        current = tmux.metadata(socket=socket, session=session, pane=metadata["pane"])
    if not current.get("pane_dead"):
        raise IdentityError("provisional exact target did not stop gracefully")
    if not tmux.exists(socket, session) or tmux.socket_identity(socket) != socket_identity:
        raise IdentityError("provisional probe tmux evidence was not preserved")
    return {
        "schema_version": 1,
        "timestamp": _utc_now(),
        "session": session,
        "target_pid": metadata["pane_pid"],
        "reason": "failed_probe_provisional_cleanup",
        "signal": "tmux_exact_pane_" + "_".join(key.lower().replace("-", "_") for key in sent_keys),
        "signal_sent": bool(sent_keys),
        "stopped": True,
        "tmux_preserved": True,
        "cleanup_scope": "exact_new_target_only",
        "identity_binding": "new_private_tmux_pane",
    }


def _write_state(path: Path, state: Dict[str, Any], phase: str, **changes: Any) -> None:
    state.update(changes)
    state["phase"] = phase
    state["updated_at"] = _utc_now()
    atomic_write_json(path, state)


def run_probe(
    *,
    target: str,
    profile: str,
    proof_root: Path,
    manifest_path: Path,
    mapping_path: Path,
    authorization_path: Path,
    controller: str,
    timeout: float = 300.0,
    halt_timeout: float = 10.0,
    run_id: Optional[str] = None,
    _tmux_factory: Callable[[Path], TmuxController] = TmuxController,
    _process_birth_fn: Callable[[int], Dict[str, Any]] = process_birth_identity,
    _process_alive_fn: Callable[[Dict[str, Any]], bool] = process_alive,
    _active_processes_fn: Callable[[str], list[Dict[str, Any]]] = active_target_processes,
    _adapter_fingerprint_fn: Callable[[], str] = adapter_implementation_fingerprint,
    _census_target_fn: Callable[[str, str], AdapterManifest] = census_target,
    _sleep_fn: Callable[[float], None] = time.sleep,
) -> Dict[str, Any]:
    """Run one isolated source-free qualification probe.

    Test-only dependency hooks are private keyword arguments.  The public CLI
    always uses the real structural process and private-socket tmux surfaces.
    """

    if target not in TARGETS:
        raise ValidationError("unsupported probe target")
    if profile != PROBE_PROFILE:
        raise ValidationError("probe profile must be the fixed source-free Pass B contract")
    validate_identifier(controller, "controller")
    if controller == target:
        raise ValidationError("a target cannot act as its own probe controller")
    if timeout <= 0 or timeout > MAX_PROBE_SECONDS:
        raise ValidationError("probe timeout must be greater than zero and at most 900 seconds")
    if halt_timeout < 0 or halt_timeout > MAX_HALT_SECONDS:
        raise ValidationError("halt timeout must be between zero and 60 seconds")
    proof_root = absolute_root(str(proof_root), "proof root")
    manifest, mapping, argv = _validated_mapping(
        manifest_path,
        mapping_path,
        target=target,
        adapter_fingerprint_fn=_adapter_fingerprint_fn,
        census_target_fn=_census_target_fn,
    )
    authorization = validate_campaign_authorization(
        authorization_path, target=target, controller=controller
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
    halt_path = run_root / "halt.json"
    receipt_path = run_root / "receipt.json"
    state: Dict[str, Any] = {
        "schema_version": 1,
        "run_id": run_id,
        "session": session,
        "target": target,
        "controller": controller,
        "profile": profile,
        "created_at": _utc_now(),
        "updated_at": _utc_now(),
        "phase": "preflight",
        "result": None,
        "blocker": None,
    }
    atomic_write_json(state_path, state)
    atomic_write_json(authorization_snapshot_path, authorization)
    metadata: Optional[Dict[str, Any]] = None
    process: Optional[Dict[str, Any]] = None
    tmux: Optional[TmuxController] = None
    socket: Optional[Path] = None
    socket_identity: Optional[Dict[str, Any]] = None
    provisional_bound = False
    lock_descriptor: Optional[int] = None
    cleanup: Optional[Dict[str, Any]] = None
    evidence: Dict[str, Any] = {
        "schema_version": 1,
        "run_id": run_id,
        "target": target,
        "controller": controller,
        "profile": profile,
        "campaign_id": authorization["campaign_id"],
        "authorization_sha256": sha256_file(
            authorization_snapshot_path, max_bytes=65536
        ),
        "manifest_fingerprint": manifest.fingerprint,
        "executable_fingerprint": manifest.raw["executable"]["sha256"],
        "version_fingerprint": manifest.raw["executable"]["version_sha256"],
        "platform_fingerprint": sha256_bytes(
            canonical_json_bytes(manifest.raw["platform"])
        ),
        "adapter_fingerprint": manifest.raw["adapter_fingerprint"],
        "protocol_fingerprint": manifest.raw["protocol_fingerprint"],
        "yolo_mapping_sha256": sha256_bytes(canonical_json_bytes(mapping)),
        "launch_argv_sha256": sha256_bytes(canonical_json_bytes(argv)),
        "input_transport": "tmux_load_buffer_stdin",
        "payload_argv_absent": True,
        "active_target_processes_before_launch": [],
        "active_target_processes_after_halt": None,
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
    }
    atomic_write_json(evidence_path, evidence)
    try:
        lock_descriptor, lock_identity = _acquire_campaign_probe_lock(proof_root)
        evidence["campaign_probe_lock"] = lock_identity
        atomic_write_json(evidence_path, evidence)
        active = _active_processes_fn(target)
        override = parallel_target_override(authorization, target, active)
        protected_session = (
            authorization.get("authorization", {})
            .get("parallel_target_override", {})
            .get("protected_session")
            if override
            else None
        )
        if protected_session == session:
            raise ConflictError("probe session collides with the protected operator session")
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

        fixture = run_root / "fixture"
        fixture_contract = create_fixture(
            fixture, run_id=run_id, session=session, target=target
        )
        if fixture_contract["protocol_fingerprint"] != manifest.raw["protocol_fingerprint"]:
            raise IdentityError("fixture and manifest protocol fingerprints differ")
        fixture_fingerprint = tree_fingerprint(fixture)
        evidence["fixture_fingerprint_before"] = fixture_fingerprint
        controller_contract = _controller_contract(
            fixture=fixture,
            campaign_id=authorization["campaign_id"],
            controller=controller,
            target=target,
            profile=profile,
        )
        atomic_write_json(run_root / "controller-contract.json", controller_contract.raw)

        tmux_authority = run_root / "tmux-authority"
        tmux_authority.mkdir(mode=0o700)
        tmux = _tmux_factory(tmux_authority)
        socket = tmux.socket_path(session)
        _write_state(state_path, state, "launching")
        metadata = tmux.launch(session=session, repo=fixture, argv=argv)
        if metadata.get("socket") != str(socket):
            raise IdentityError("probe launched on an unexpected tmux socket")
        socket_identity = tmux.socket_identity(socket)
        if (
            metadata.get("session") != session
            or not isinstance(metadata.get("pane_pid"), int)
            or metadata["pane_pid"] <= 1
            or not isinstance(metadata.get("pane"), str)
        ):
            raise IdentityError("probe launch metadata is structurally incomplete")
        provisional_bound = True
        if metadata.get("socket_identity") != socket_identity:
            raise IdentityError("probe launch did not bind the private tmux socket identity")
        process = _process_birth_fn(metadata["pane_pid"])
        if process.get("pid") != metadata["pane_pid"]:
            raise IdentityError("probe process and tmux pane identities differ")
        manifest.verify_process_executable(process)
        _assert_runtime(
            tmux=tmux,
            socket=socket,
            session=session,
            pane=metadata["pane"],
            pane_pid=metadata["pane_pid"],
            socket_identity=socket_identity,
            process=process,
            process_alive_fn=_process_alive_fn,
        )
        _assert_executable_identity(manifest)
        _assert_adapter_identity(manifest, _adapter_fingerprint_fn)
        evidence["tmux"] = {
            "socket": str(socket),
            "session": session,
            "target_id": metadata["pane"],
            "socket_identity": socket_identity,
        }
        evidence["process"] = process
        atomic_write_json(evidence_path, evidence)
        attach = tmux.attach_command(
            socket=socket, session=session, pane=metadata["pane"]
        )
        _write_state(
            state_path,
            state,
            "awaiting_ready",
            tmux=evidence["tmux"],
            process=process,
            attach_command=attach,
        )

        ready_value = _handoff_value(
            phase="ready",
            session=session,
            fixture_contract=fixture_contract,
            manifest=manifest,
        )
        initial = adapter_for(target).envelope(
            _initial_prompt(fixture_contract, ready_value)
        )
        initial_payload = _payload(initial)
        if any(
            initial in argument
            or "PUPPET_REAL_HARNESS" in argument
            or run_id in argument
            or fixture_contract["nonce"] in argument
            for argument in argv
        ):
            raise IdentityError("initial prompt appeared in the process arguments")
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
            process=process,
            process_alive_fn=_process_alive_fn,
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
        followup_message = adapter_for(target).envelope(
            _followup_prompt(fixture_contract, followup_value)
        )
        followup_payload = _payload(followup_message)
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
            process=process,
            process_alive_fn=_process_alive_fn,
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
        acceptance_path = (
            run_root / "acceptance" / (followup.checkpoint_id + ".json")
        )
        evidence["review_sha256"] = sha256_file(review_path, max_bytes=131072)
        evidence["acceptance_sha256"] = sha256_file(
            acceptance_path, max_bytes=131072
        )
        atomic_write_json(evidence_path, evidence)
        _write_state(state_path, state, "accepted_awaiting_halt")

        cleanup = _halt_exact(
            target=target,
            tmux=tmux,
            socket=socket,
            session=session,
            pane=metadata["pane"],
            socket_identity=socket_identity,
            process=process,
            process_alive_fn=_process_alive_fn,
            timeout=halt_timeout,
            sleep_fn=_sleep_fn,
            reason="accepted_probe_halt",
            require_live=True,
        )
        _assert_executable_identity(manifest)
        _assert_adapter_identity(manifest, _adapter_fingerprint_fn)
        active_after_halt = _active_processes_fn(target)
        if sorted(active_after_halt, key=lambda item: item["pid"]) != sorted(
            active, key=lambda item: item["pid"]
        ):
            raise IdentityError("protected same-target process population changed")
        atomic_write_json(halt_path, cleanup)
        halt_sha = sha256_file(halt_path, max_bytes=65536)
        evidence["halt_sha256"] = halt_sha
        evidence["active_target_processes_after_halt"] = active_after_halt
        evidence["result"] = "accepted"
        atomic_write_json(evidence_path, evidence)
        receipt = {
            "schema_version": 1,
            "kind": "real_harness_conformance",
            "run_id": run_id,
            "target": target,
            "result": "accepted",
            "controller": controller,
            "executable_fingerprint": manifest.raw["executable"]["sha256"],
            "version_fingerprint": manifest.raw["executable"]["version_sha256"],
            "platform_fingerprint": evidence["platform_fingerprint"],
            "adapter_fingerprint": manifest.raw["adapter_fingerprint"],
            "protocol_fingerprint": manifest.raw["protocol_fingerprint"],
            "yolo_mapping_sha256": evidence["yolo_mapping_sha256"],
            "capabilities": list(PROBE_CAPABILITIES),
            "accepted_checkpoint_id": followup.checkpoint_id,
            "acceptance_sha256": evidence["acceptance_sha256"],
            "halt_receipt_sha256": halt_sha,
            "proof_refs": [
                _proof_reference(
                    "authorization", authorization_snapshot_path, run_root
                ),
                _proof_reference("evidence", evidence_path, run_root),
                _proof_reference("halt", halt_path, run_root),
                _proof_reference(
                    "ready", fixture / "handoffs" / "ready.json", run_root
                ),
                _proof_reference(
                    "followup", fixture / "handoffs" / "followup.json", run_root
                ),
                _proof_reference("review", review_path, run_root),
                _proof_reference("acceptance", acceptance_path, run_root),
            ],
        }
        atomic_write_json(receipt_path, receipt)
        verify_qualification_receipt(receipt_path)
        _write_state(
            state_path,
            state,
            "complete",
            result="accepted",
            receipt_sha256=sha256_file(receipt_path, max_bytes=131072),
        )
        return {
            "ok": True,
            "run_id": run_id,
            "target": target,
            "result": "accepted",
            "run_root": str(run_root),
            "receipt": str(receipt_path),
            "tmux_preserved": True,
            "attach_command": attach,
        }
    except BaseException as exc:
        cleanup_error = None
        if (
            tmux is not None
            and metadata is not None
            and process is not None
            and socket is not None
            and socket_identity is not None
        ):
            try:
                cleanup = _halt_exact(
                    target=target,
                    tmux=tmux,
                    socket=socket,
                    session=session,
                    pane=metadata["pane"],
                    socket_identity=socket_identity,
                    process=process,
                    process_alive_fn=_process_alive_fn,
                    timeout=halt_timeout,
                    sleep_fn=_sleep_fn,
                    reason="failed_probe_cleanup",
                    require_live=False,
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
        ):
            try:
                cleanup = _halt_provisional_exact(
                    target=target,
                    tmux=tmux,
                    socket=socket,
                    session=session,
                    metadata=metadata,
                    socket_identity=socket_identity,
                    timeout=halt_timeout,
                    sleep_fn=_sleep_fn,
                )
                atomic_write_json(halt_path, cleanup)
                evidence["halt_sha256"] = sha256_file(halt_path, max_bytes=65536)
            except BaseException as halt_exc:  # Preserve the original failure.
                cleanup_error = "%s: %s" % (
                    halt_exc.__class__.__name__,
                    str(halt_exc)[:500],
                )
        evidence["result"] = "failed"
        evidence["failure"] = {
            "type": exc.__class__.__name__,
            "detail": str(exc)[:1000],
            "cleanup_error": cleanup_error,
        }
        atomic_write_json(evidence_path, evidence)
        _write_state(
            state_path,
            state,
            "failed",
            result="failed",
            blocker=evidence["failure"],
        )
        if isinstance(exc, PuppetError):
            raise
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        raise ValidationError("real-harness probe execution failed") from exc
    finally:
        _release_campaign_probe_lock(lock_descriptor)
