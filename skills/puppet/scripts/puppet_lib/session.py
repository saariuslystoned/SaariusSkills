"""Fail-closed Puppet session orchestration."""

from __future__ import annotations

import datetime as dt
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .adapter_manifest import AdapterManifest
from .adapters import adapter_for
from .agy_launch import require_agy_regular_launch_authority
from .authority import (
    admit_session_lease,
    lease_owner as build_lease_owner,
    reconcile_halted_session_lease,
    transition_session_lease,
)
from .beacons import parse_beacon
from .campaign import (
    active_target_processes,
    agy_process_population,
    grok_process_population,
    parallel_target_override,
    validate_campaign_authorization,
)
from .conformance import tree_fingerprint, validate_fixture_contract
from .contracts import Contract
from .errors import ConflictError, IdentityError, UnsupportedError, ValidationError
from .grok_launch import GROK_LAUNCH_AUTHORITY_BLOCKER
from .handoffs import ValidatedHandoff, validate_handoff
from .halt_control import deliver_halt_actions
from .instructions import (
    compile_instruction_wrapper,
    instruction_policy_fingerprint,
)
from .journal import Journal
from .launch import build_launch_identity
from .profiles import INPUT_READINESS_STRATEGY, startup_settle_seconds_for
from .registry import (
    SESSION_REGISTRY_SCHEMA_VERSION,
    SessionRegistry,
    bind_runtime_process,
    process_alive,
    process_birth_identity,
    send_exact_sigint,
)
from .safety import (
    SECRET_TEXT_PATTERNS,
    absolute_root,
    atomic_write_json,
    canonical_json_bytes,
    ensure_within,
    exclusive_lock,
    read_json,
    sha256_bytes,
    sha256_file,
    validate_identifier,
)
from .state import is_terminal, transition
from .subscription_profiles import (
    SubscriptionLaunchContext,
    build_subscription_launch_binding,
    subscription_profile_preflight,
)
from .tmux import TargetLaunch, TmuxController
from .verdicts import (
    record_acceptance,
    record_review,
    verify_current_identity,
)
from .viewer import (
    TICKET_TTL_SECONDS,
    build_view_ticket,
    dispatch_operator_view,
    load_and_claim_ticket,
    prepare_operator_view,
    prepare_view_ticket,
    revoke_ticket,
    ticket_claim_identity,
    ticket_is_revoked,
)


YOLO_WARNING = (
    "Puppet live execution is YOLO-only: unrestricted/always-approve mode is "
    "required and the harness sandbox is disabled wherever exposed."
)


def _utc_now() -> str:
    return (
        dt.datetime.now(dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _git(repo: Path, arguments: List[str], *, identity_error: bool = False) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo)] + arguments,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        error = IdentityError if identity_error else ValidationError
        raise error("repository identity probe failed")
    return result.stdout.strip()


def _active_processes(target: str, manifest: AdapterManifest) -> List[Dict[str, Any]]:
    return active_target_processes(
        target, execution_files=manifest.process_execution_selectors()
    )


def _authorization(path: Path, contract: Contract) -> Dict[str, Any]:
    return validate_campaign_authorization(
        path,
        target=contract.target,
        controller=contract.controller,
        campaign_id=contract.campaign_authorization_id,
    )


def _qualification_authority(
    contract: Contract, authorization: Dict[str, Any]
) -> Dict[str, str]:
    return {
        "controller": contract.controller,
        "campaign_id": authorization["campaign_id"],
        "goal_fingerprint": sha256_bytes(canonical_json_bytes(authorization["goal"])),
    }


def _parallel_target_override(
    authorization: Dict[str, Any], target: str, active: List[Dict[str, Any]]
) -> bool:
    return parallel_target_override(authorization, target, active)


def _agy_population(
    manifest: AdapterManifest,
) -> Dict[str, List[Dict[str, Any]]]:
    runtime = manifest.raw["execution"]["runtime_executable"]
    return agy_process_population(
        runtime_selector={
            "path": runtime["path"],
            "device": runtime["device"],
            "inode": runtime["inode"],
        }
    )


def _assess_agy_population(
    authorization: Dict[str, Any],
    population: Dict[str, List[Dict[str, Any]]],
) -> Tuple[List[Dict[str, Any]], bool, List[str]]:
    matching = population["matching"]
    mismatched = population["mismatched"]
    override = _parallel_target_override(authorization, "agy", matching)
    blockers = []
    if mismatched:
        override = False
        blockers.append(
            "a live AGY candidate has a different executable identity and blocks launch"
        )
    if matching and not override:
        blockers.append(
            "active AGY processes may hold the exclusive store lock and require "
            "the exact parallel isolation override"
        )
    return matching, override, blockers


def _grok_population(
    manifest: AdapterManifest,
) -> Dict[str, List[Dict[str, Any]]]:
    runtime = manifest.raw["execution"]["runtime_executable"]
    return grok_process_population(
        runtime_selector={
            "path": runtime["path"],
            "device": runtime["device"],
            "inode": runtime["inode"],
        }
    )


def _assess_grok_population(
    authorization: Dict[str, Any],
    population: Dict[str, List[Dict[str, Any]]],
) -> Tuple[List[Dict[str, Any]], bool, List[str]]:
    matching = population["matching"]
    mismatched = population["mismatched"]
    override = _parallel_target_override(authorization, "grok", matching)
    blockers = []
    if mismatched:
        blockers.append(
            "a live Grok candidate has a different executable identity and "
            "blocks launch"
        )
    if matching and not override:
        blockers.append(
            "active Grok processes require the exact parallel isolation override"
        )
    return matching, override, blockers


def _bind_json(path: Path, value: Dict[str, Any], label: str) -> Path:
    path = Path(path)
    if path.exists():
        existing = read_json(path, max_bytes=262144)
        if canonical_json_bytes(existing) != canonical_json_bytes(value):
            raise ConflictError("bound %s already contains different content" % label)
    else:
        atomic_write_json(path, value)
    return path.resolve(strict=True)


def _bound_contract(record: Dict[str, Any]) -> Contract:
    proof_root = absolute_root(record["proof_root"], "proof root")
    path = ensure_within(Path(record["contract_path"]), proof_root, must_exist=True)
    contract = Contract.from_path(path)
    if contract.fingerprint != record["contract_fingerprint"]:
        raise IdentityError("bound contract fingerprint changed")
    expected = {
        "controller": record["controller"],
        "target": record["target"],
        "repo": str(contract.repo),
        "branch": contract.branch,
        "mutation_owner": contract.mutation_owner,
    }
    actual = {
        "controller": contract.controller,
        "target": contract.target,
        "repo": record["repo"],
        "branch": record["branch"],
        "mutation_owner": record["mutation_owner"],
    }
    if expected != actual:
        raise IdentityError("bound contract authority changed")
    return contract


def _supervisor_identity(
    executable: Path, expected_root: Optional[Path]
) -> Dict[str, Any]:
    executable = Path(executable)
    if executable.is_symlink() or not executable.is_file():
        raise ValidationError("supervisor executable is unavailable or a symlink")
    executable = executable.resolve(strict=True)
    discovered = Path(
        _git(executable.parent, ["rev-parse", "--show-toplevel"])
    ).resolve(strict=True)
    if expected_root is not None and discovered != expected_root.resolve(strict=True):
        raise IdentityError(
            "supervisor executable is outside the contracted release root"
        )
    ensure_within(executable, discovered, must_exist=True)
    relative = str(executable.relative_to(discovered))
    _git(discovered, ["ls-files", "--error-unmatch", "--", relative])
    if _git(discovered, ["status", "--porcelain=v1", "--untracked-files=all"]):
        raise IdentityError("supervisor release must be committed and clean")
    return {
        "root": str(discovered),
        "commit": _git(discovered, ["rev-parse", "HEAD"]),
        "tree": _git(discovered, ["rev-parse", "HEAD^{tree}"]),
        "executable_path": str(executable),
        "executable_sha256": sha256_file(executable),
    }


def _message_payload(message: str) -> bytes:
    if not isinstance(message, str) or not message.strip():
        raise ValidationError("message must not be empty")
    payload = message.encode("utf-8")
    if len(payload) > 65536:
        raise ValidationError("message exceeds the size limit")
    if any(pattern.search(message) for pattern in SECRET_TEXT_PATTERNS):
        raise ValidationError("message contains secret-shaped text")
    return payload


def _journal(proof_root: Path) -> Journal:
    return Journal(Path(proof_root) / "journal")


def _delivery_request_id(session: str, operation_id: str, phase: str) -> str:
    validate_identifier(session, "session")
    return sha256_bytes(
        (session + "\x00" + phase + "\x00" + operation_id).encode("utf-8")
    )


def _cleanup_incomplete_launch(
    *,
    tmux: TmuxController,
    metadata: Dict[str, Any],
    session: str,
    target: str,
    process: Optional[Dict[str, Any]],
    process_verified: bool,
    journal: Journal,
    timeout: float = 2.0,
) -> bool:
    """Gracefully stop only the exact private pane created by this launch."""
    socket = Path(metadata.get("socket", ""))
    pane = metadata.get("pane")
    pane_pid = metadata.get("pane_pid")
    socket_identity = metadata.get("socket_identity")
    server_identity = metadata.get("server_identity")
    tmux_binary_identity = metadata.get("tmux_binary_identity")
    if (
        metadata.get("session") != session
        or not isinstance(pane_pid, int)
        or pane_pid <= 1
        or not isinstance(pane, str)
        or not isinstance(socket_identity, dict)
        or not isinstance(server_identity, dict)
        or not isinstance(tmux_binary_identity, dict)
    ):
        raise IdentityError("incomplete launch tmux identity is ambiguous")
    tmux.assert_tmux_binary_identity(tmux_binary_identity)
    tmux.bind_server_identity(socket, server_identity)
    if tmux.socket_identity(socket) != socket_identity:
        raise IdentityError("incomplete launch socket identity changed")

    def target_alive() -> bool:
        current = tmux.metadata(
            socket=socket,
            session=session,
            pane=pane,
            server_identity=server_identity,
        )
        if any(
            current.get(name) != metadata.get(name)
            for name in ("session", "pane", "pane_pid")
        ):
            raise IdentityError("incomplete launch pane identity changed")
        if current.get("pane_dead"):
            return False
        if process_verified:
            if process is None or process.get("pid") != pane_pid:
                raise IdentityError("incomplete launch process identity changed")
            if not process_alive(process):
                raise IdentityError(
                    "incomplete launch pane remained live after process identity changed"
                )
        return True

    initially_alive = target_alive()
    if initially_alive and not process_verified:
        raise IdentityError(
            "incomplete launch process remains unbound; no halt action was attempted"
        )
    if not initially_alive and process is None:
        terminal = tmux.metadata_for_session(
            socket=socket,
            session=session,
            server_identity=server_identity,
        )
        if (
            terminal.get("pane") != pane
            or terminal.get("pane_pid") != pane_pid
            or terminal.get("pane_dead") is not True
            or tmux.socket_identity(socket) != socket_identity
        ):
            raise IdentityError("incomplete launch dead-pane evidence changed")
        return True

    def deliver_one(action: str) -> None:
        if not target_alive() or process is None:
            raise IdentityError("incomplete launch stopped before its halt action")
        if action == "exact_pid_sigint":
            send_exact_sigint(process)
        elif action == "tmux_pane_eof":
            tmux.send_control(
                socket=socket,
                session=session,
                pane=pane,
                key="C-d",
                server_identity=server_identity,
                expected_pane_pid=pane_pid,
            )
        else:
            raise IdentityError("incomplete launch selected an unknown halt action")

    deadline = time.monotonic() + timeout

    def pause_after_send() -> None:
        time.sleep(min(0.1, max(0.0, deadline - time.monotonic())))

    deliver_halt_actions(
        journal=journal,
        session=session,
        target_identity=process,
        actions=list(adapter_for(target).graceful_halt_actions),
        process_alive=target_alive,
        deliver_action=deliver_one,
        after_send=pause_after_send,
    )
    while target_alive() and time.monotonic() < deadline:
        time.sleep(0.05)
    if target_alive():
        raise IdentityError("incomplete launch target did not stop gracefully")
    terminal = tmux.metadata_for_session(
        socket=socket,
        session=session,
        server_identity=server_identity,
    )
    if (
        terminal.get("pane") != pane
        or terminal.get("pane_pid") != pane_pid
        or terminal.get("pane_dead") is not True
        or tmux.socket_identity(socket) != socket_identity
    ):
        raise IdentityError("incomplete launch dead-pane evidence changed")
    return True


def _halt_terminal_result(journal: Journal, session: str) -> Optional[Dict[str, Any]]:
    event = journal.lookup(_delivery_request_id(session, session, "halted"))
    if (
        event is None
        or event.get("event", {}).get("kind") != "halt"
        or event.get("event", {}).get("result") != "stopped"
    ):
        return None
    return {
        "ok": True,
        "session": session,
        "state": "HALTED",
        "signal_sent": bool(event["event"].get("signal_sent")),
        "tmux_preserved": bool(event["event"].get("tmux_preserved", True)),
    }


def _deliver(
    *,
    tmux: TmuxController,
    socket: Path,
    session: str,
    pane: str,
    buffer_name: str,
    message: str,
    proof_root: Path,
    operation_id: str,
    kind: str,
) -> Dict[str, Any]:
    validate_identifier(operation_id, "operation id")
    payload = _message_payload(message)
    content_sha = sha256_bytes(payload)
    journal = _journal(proof_root)
    intent_id = _delivery_request_id(session, operation_id, "intent")
    submitted_id = _delivery_request_id(session, operation_id, "submitted")
    intent_event = {
        "kind": kind,
        "session": session,
        "operation_id": operation_id,
        "content_sha256": content_sha,
        "delivery": "intent",
    }
    submitted_event = dict(intent_event, delivery="submitted")
    lock = Path(proof_root) / ".delivery.lock"
    with exclusive_lock(lock):
        submitted = journal.lookup(submitted_id)
        if submitted is not None:
            if submitted["event"] != submitted_event:
                raise ConflictError("operation id was submitted with different content")
            return {
                "content_sha256": content_sha,
                "delivery": "already_submitted",
            }
        intent = journal.lookup(intent_id)
        if intent is not None:
            if intent["event"] != intent_event:
                raise ConflictError("operation id was reserved with different content")
            raise ConflictError(
                "prior delivery is ambiguous; use a new operation id after adjudication"
            )
        journal.append(request_id=intent_id, event=intent_event)
        tmux.paste_bytes(
            socket=socket,
            session=session,
            pane=pane,
            buffer_name=buffer_name,
            payload=payload,
        )
        journal.append(request_id=submitted_id, event=submitted_event)
    return {"content_sha256": content_sha, "delivery": "submitted"}


def _runtime(
    registry: SessionRegistry,
    record: Dict[str, Any],
    capability: str,
    *,
    require_process: bool,
) -> Tuple[TmuxController, Dict[str, Any]]:
    registry.verify_supervisor(record)
    registry.verify_instructions(record)
    registry.verify_adapter(record, capability)
    tmux = TmuxController(registry.root)
    tmux.assert_tmux_binary_identity(record["tmux"]["tmux_binary_identity"])
    tmux.bind_server_identity(
        Path(record["tmux"]["socket"]), record["tmux"]["server_identity"]
    )
    metadata = tmux.metadata(
        socket=Path(record["tmux"]["socket"]),
        session=record["tmux"]["session"],
        pane=record["tmux"]["pane"],
        server_identity=record["tmux"]["server_identity"],
    )
    if metadata["pane_pid"] != record["process"]["pid"]:
        raise IdentityError("registered tmux pane no longer owns the target process")
    if require_process:
        registry.verify_process(record)
        if metadata["pane_dead"]:
            raise IdentityError("registered target pane is dead")
    return tmux, metadata


def _fixture_contract(contract: Contract, session: str) -> Dict[str, Any]:
    path = contract.repo / "contract.json"
    fixture = read_json(path, max_bytes=32768, reject_sensitive_fields=True)
    return validate_fixture_contract(
        fixture,
        root=contract.repo,
        session=session,
        target=contract.target,
    )


def _protocol_state(
    contract: Contract, manifest: AdapterManifest, session: str
) -> Dict[str, Any]:
    if contract.task_profile == "conformance":
        fixture = _fixture_contract(contract, session)
        if fixture["protocol_fingerprint"] != manifest.raw["protocol_fingerprint"]:
            raise IdentityError("fixture and adapter protocol fingerprints differ")
        return {
            "kind": "conformance",
            "run_id": fixture["run_id"],
            "nonce": fixture["nonce"],
            "phase": "awaiting_ready",
            "fixture_fingerprint": tree_fingerprint(contract.repo),
            "ready_checkpoint_id": None,
            "ready_artifact_sha256": None,
            "message_id": None,
            "followup_checkpoint_id": None,
        }
    if not contract.run_id or not contract.nonce:
        raise ValidationError(
            "source contracts require controller-created run_id and nonce"
        )
    if not contract.proof_path_prefixes:
        raise ValidationError("source contracts require proof_path_prefixes")
    return {
        "kind": "source",
        "run_id": contract.run_id,
        "nonce": contract.nonce,
        "phase": "awaiting_source",
        "source_commit": None,
        "proof_commit": None,
    }


def _verify_source_identity(contract: Contract, candidate_commit: str) -> None:
    if (
        _git(contract.repo, ["branch", "--show-current"], identity_error=True)
        != contract.branch
    ):
        raise IdentityError("candidate branch changed")
    if (
        _git(contract.repo, ["rev-parse", "HEAD"], identity_error=True)
        != candidate_commit
    ):
        raise IdentityError("source checkpoint is not the current exact head")
    if _git(contract.repo, ["status", "--porcelain=v1"], identity_error=True):
        raise IdentityError("candidate worktree is not clean at the exact head")


def _initial_envelope(
    contract: Contract, protocol: Dict[str, Any], session: str, message: str
) -> str:
    body = message.strip()
    gates = ",".join(sorted(contract.hard_gates))
    modes = ",".join(sorted(contract.allowed_modes))
    return (
        "PUPPET_SESSION_V2\n"
        "session=%s\ncontroller=%s\ntarget=%s\nrun_id=%s\nnonce=%s\n"
        "mutation_owner=%s\nallowed_modes=%s\nhard_gates=%s\n"
        "Controller acceptance is authoritative; target claims are nonterminal.\n\n%s"
        % (
            session,
            contract.controller,
            contract.target,
            protocol["run_id"],
            protocol["nonce"],
            contract.mutation_owner,
            modes,
            gates,
            body,
        )
    )


def _followup_envelope(protocol: Dict[str, Any], message_id: str, message: str) -> str:
    return (
        "PUPPET_FOLLOWUP_V2\nrun_id=%s\nnonce=%s\nmessage_id=%s\nsequence=1\n"
        "prior_checkpoint_sha256=%s\n\n%s"
        % (
            protocol["run_id"],
            protocol["nonce"],
            message_id,
            protocol["ready_artifact_sha256"],
            message.strip(),
        )
    )


def _workspace_snapshot(contract: Contract) -> Dict[str, Any]:
    return {
        "branch": _git(contract.repo, ["branch", "--show-current"]),
        "head": _git(contract.repo, ["rev-parse", "HEAD"]),
        "tree": _git(contract.repo, ["rev-parse", "HEAD^{tree}"]),
        "dirty": bool(_git(contract.repo, ["status", "--porcelain=v1"])),
    }


def _profile_doctor_state(
    *,
    profile_root: Optional[Path],
    contract: Contract,
    manifest: AdapterManifest,
    require_subscription_profile: bool,
) -> Tuple[Optional[SubscriptionLaunchContext], Optional[Dict[str, Any]], List[str]]:
    """Return body-free profile state and blockers without leaking status output."""

    if profile_root is None:
        return (
            None,
            None,
            (
                ["an explicit private subscription profile is required"]
                if require_subscription_profile
                else []
            ),
        )
    if contract.target == "agy":
        return (
            None,
            None,
            [
                "AGY has no proved authentication-preserving private "
                "subscription profile"
            ],
        )
    try:
        context, status = subscription_profile_preflight(
            profile_root=profile_root,
            expected_target=contract.target,
            expected_executable_path=manifest.raw["executable"]["resolved_path"],
        )
    except (ConflictError, IdentityError, UnsupportedError, ValidationError):
        return (
            None,
            None,
            ["private subscription profile is invalid or unavailable"],
        )
    blockers = []
    if status["login_state"] != "logged_in":
        blockers.append("private subscription profile is not authenticated")
    public_status = {
        name: status[name]
        for name in (
            "schema",
            "target",
            "profile_root",
            "login_state",
            "method",
            "provider",
            "default_model",
            "status_exit",
            "raw_output_retained",
            "login_performed",
            "model_launched",
        )
        if name in status
    }
    return context, public_status, blockers


def doctor(
    *,
    contract_path: Path,
    manifest_path: Path,
    authorization_path: Path,
    proof_root: Path,
    state_root: Path,
    profile_root: Optional[Path] = None,
    require_subscription_profile: bool = True,
) -> Dict[str, Any]:
    contract = Contract.from_path(contract_path)
    if contract.target == "agy":
        require_agy_regular_launch_authority(contract.session_profile)
    manifest = AdapterManifest.from_path(manifest_path)
    if contract.target != manifest.target:
        raise ValidationError("contract and adapter target mismatch")
    authorization = _authorization(authorization_path, contract)
    proof_root = absolute_root(str(proof_root), "proof root")
    state_root = absolute_root(str(state_root), "state root")
    blockers = []
    executable = Path(manifest.raw["executable"]["resolved_path"])
    if executable.is_symlink() or not executable.is_file():
        blockers.append("resolved executable is unavailable or a symlink")
    elif sha256_file(executable) != manifest.raw["executable"]["sha256"]:
        blockers.append("executable fingerprint drifted")
    profile_context, profile_status, profile_blockers = _profile_doctor_state(
        profile_root=profile_root,
        contract=contract,
        manifest=manifest,
        require_subscription_profile=require_subscription_profile,
    )
    blockers.extend(profile_blockers)
    if not TmuxController.available():
        blockers.append("tmux is unavailable")
    workspace = _workspace_snapshot(contract)
    branch = workspace["branch"]
    head = workspace["head"]
    tree = workspace["tree"]
    dirty = workspace["dirty"]
    if branch != contract.branch:
        blockers.append("contract branch does not match checkout")
    if dirty:
        blockers.append("candidate worktree is not clean")
    if not os.access(str(proof_root), os.W_OK):
        blockers.append("proof root is not writable")
    if not os.access(str(state_root), os.W_OK):
        blockers.append("state root is not writable")
    mapping = manifest.raw["yolo_mapping"]
    if contract.session_profile != "regular":
        blockers.append("only the regular session profile is enabled")
    if contract.requested_model is not None or contract.requested_effort is not None:
        blockers.append("explicit model and effort selection remain deferred")
    if not mapping.get("complete"):
        blockers.append(
            "exact YOLO, sandbox-off, and argv-free prompt mapping is incomplete"
        )
    candidate_processes: List[Dict[str, Any]]
    if contract.target == "agy":
        agy_population = _agy_population(manifest)
        active, parallel_override, population_blockers = _assess_agy_population(
            authorization, agy_population
        )
        candidate_processes = agy_population["candidates"]
        blockers.extend(population_blockers)
    elif contract.target == "grok":
        grok_population = _grok_population(manifest)
        active, parallel_override, population_blockers = _assess_grok_population(
            authorization, grok_population
        )
        candidate_processes = grok_population["candidates"]
        blockers.extend(population_blockers)
        # The source-only Grok planner binds private roots and an exact launch
        # vector, but no live session may start until leader/child halt authority
        # and the remaining Grok-specific qualification gates are proved.
        blockers.append(GROK_LAUNCH_AUTHORITY_BLOCKER)
    else:
        active = _active_processes(contract.target, manifest)
        candidate_processes = active
        parallel_override = _parallel_target_override(
            authorization, contract.target, active
        )
    unverified = sorted(
        name
        for name, status in manifest.raw["capabilities"].items()
        if status not in {"controller_verified", "unsupported"}
    )
    unsupported = sorted(
        name
        for name, status in manifest.raw["capabilities"].items()
        if status == "unsupported"
    )
    if not manifest.raw["doctor_only"]:
        try:
            authority = _qualification_authority(contract, authorization)
            qualification = manifest.verify_qualification(
                expected_controller=authority["controller"],
                expected_campaign_id=authority["campaign_id"],
                expected_goal_fingerprint=authority["goal_fingerprint"],
                expected_session_profile=contract.session_profile,
            )
            if qualification.get(
                "instruction_policy_fingerprint"
            ) != instruction_policy_fingerprint(target=contract.target):
                raise IdentityError(
                    "qualification instruction policy does not match the current compiler"
                )
        except (UnsupportedError, ValidationError, IdentityError):
            blockers.append("real-harness qualification receipt is missing or invalid")
    return {
        "ok": True,
        "warning": YOLO_WARNING,
        "target": contract.target,
        "session_profile": contract.session_profile,
        "contract_fingerprint": contract.fingerprint,
        "manifest_fingerprint": manifest.fingerprint,
        "subscription_profile": (
            {
                **dict(profile_context.public_binding),
                "status": profile_status,
            }
            if profile_context is not None and profile_status is not None
            else None
        ),
        "repo": str(contract.repo),
        "branch": branch,
        "head": head,
        "tree": tree,
        "dirty": dirty,
        "active_target_pids": [item["pid"] for item in active],
        "candidate_target_pids": [item["pid"] for item in candidate_processes],
        "parallel_target_override": parallel_override,
        "unverified_capabilities": unverified,
        "unsupported_capabilities": unsupported,
        "blockers": blockers,
        "launch_ready": not blockers
        and not unverified
        and not manifest.raw["doctor_only"],
    }


def launch(
    *,
    session: str,
    contract_path: Path,
    manifest_path: Path,
    authorization_path: Path,
    proof_root: Path,
    state_root: Path,
    supervisor_executable: Path,
    prompt: str,
    requested_model: Optional[str] = None,
    requested_effort: Optional[str] = None,
    profile_root: Optional[Path] = None,
    require_subscription_profile: bool = True,
    _sleep_fn: Any = time.sleep,
    _execution_sleep_fn: Any = time.sleep,
    _execution_monotonic_fn: Any = time.monotonic,
    _process_birth_fn: Any = None,
) -> Dict[str, Any]:
    validate_identifier(session, "session")
    initial_contract = Contract.from_path(contract_path)
    if initial_contract.target == "agy":
        require_agy_regular_launch_authority(initial_contract.session_profile)
    report = doctor(
        contract_path=contract_path,
        manifest_path=manifest_path,
        authorization_path=authorization_path,
        proof_root=proof_root,
        state_root=state_root,
        profile_root=profile_root,
        require_subscription_profile=require_subscription_profile,
    )
    if report["target"] == "grok":
        # Defense in depth: no generic launch path may inherit an operator HOME
        # or pretend the pane PID owns Grok's possible leader/child process tree.
        raise UnsupportedError(GROK_LAUNCH_AUTHORITY_BLOCKER)
    if not report["launch_ready"]:
        raise UnsupportedError("adapter remains doctor-only or preflight is blocked")
    contract = Contract.from_path(contract_path)
    manifest = AdapterManifest.from_path(manifest_path)
    if (
        contract.fingerprint != report["contract_fingerprint"]
        or manifest.fingerprint != report["manifest_fingerprint"]
    ):
        raise IdentityError("contract or manifest changed during preflight")
    authorization = _authorization(authorization_path, contract)
    qualification_authority = _qualification_authority(contract, authorization)
    qualification = manifest.verify_qualification(
        expected_controller=qualification_authority["controller"],
        expected_campaign_id=qualification_authority["campaign_id"],
        expected_goal_fingerprint=qualification_authority["goal_fingerprint"],
        expected_session_profile=contract.session_profile,
    )
    current_instruction_policy = instruction_policy_fingerprint(target=contract.target)
    if (
        qualification.get("instruction_policy_fingerprint")
        != current_instruction_policy
    ):
        raise IdentityError(
            "qualification instruction policy does not match the current compiler"
        )
    if requested_model is not None and requested_model != contract.requested_model:
        raise ValidationError("CLI model selection must match the bound contract")
    if requested_effort is not None and requested_effort != contract.requested_effort:
        raise ValidationError("CLI effort selection must match the bound contract")
    effective_model = contract.requested_model
    effective_effort = contract.requested_effort
    adapter = adapter_for(contract.target)
    argv = adapter.build_launch_argv(manifest, effective_model, effective_effort)
    profile_context: Optional[SubscriptionLaunchContext] = None
    profile_status: Optional[Dict[str, Any]] = None
    if profile_root is not None:
        profile_context, profile_status = subscription_profile_preflight(
            profile_root=profile_root,
            expected_target=contract.target,
            expected_executable_path=manifest.raw["executable"]["resolved_path"],
        )
        if profile_status["login_state"] != "logged_in":
            raise IdentityError(
                "private subscription profile authentication changed after preflight"
            )
    elif require_subscription_profile:
        raise UnsupportedError("an explicit private subscription profile is required")
    proof_root = absolute_root(str(proof_root), "proof root")
    state_root = absolute_root(str(state_root), "state root")
    contract_copy = _bind_json(
        proof_root / "controller-contract.json", contract.raw, "controller contract"
    )
    manifest_copy = _bind_json(
        proof_root / "adapter-manifest.json", manifest.raw, "adapter manifest"
    )
    manifest = AdapterManifest.from_path(manifest_copy)
    profile_binding_sha: Optional[str] = None
    if profile_context is not None and profile_status is not None:
        profile_binding = build_subscription_launch_binding(
            profile_context, profile_status
        )
        profile_copy = _bind_json(
            proof_root / "subscription-profile.json",
            profile_binding,
            "subscription profile binding",
        )
        profile_binding_sha = sha256_file(profile_copy, max_bytes=131072)
    supervisor = _supervisor_identity(supervisor_executable, contract.supervisor_root)
    protocol = _protocol_state(contract, manifest, session)
    compiled = compile_instruction_wrapper(
        target=contract.target,
        task=_initial_envelope(contract, protocol, session, prompt),
        contract_identity={
            "fingerprint": contract.fingerprint,
            "controller": contract.controller,
            "target": contract.target,
            "task_profile": contract.task_profile,
        },
        workspace_identity={
            "repo_fingerprint": sha256_bytes(str(contract.repo).encode("utf-8")),
            "branch": contract.branch,
            "head": report["head"],
            "tree": report["tree"],
        },
        run_identity={
            "session": session,
            "run_id": protocol["run_id"],
            "nonce": protocol["nonce"],
        },
        session_profile=contract.session_profile,
        model_binding="default",
        effort_binding="default",
        runtime_contract_layer={
            "mutation_owner": contract.mutation_owner,
            "allowed_modes": sorted(contract.allowed_modes),
            "hard_gates": sorted(contract.hard_gates),
        },
    )
    instruction_copy = _bind_json(
        proof_root / "effective-instructions.json",
        compiled.manifest,
        "effective instruction manifest",
    )
    instruction_manifest_sha = sha256_file(instruction_copy, max_bytes=131072)
    session_lease_owner = build_lease_owner(
        activity="session",
        run_id=protocol["run_id"],
        campaign_id=qualification_authority["campaign_id"],
        goal_fingerprint=qualification_authority["goal_fingerprint"],
        proof_root=proof_root,
        state_root=state_root,
    )
    initial = adapter.envelope(
        compiled.rendered.decode("utf-8"),
        session_profile=contract.session_profile,
        initial=True,
    )
    initial_sha = sha256_bytes(_message_payload(initial))
    if initial_sha != compiled.manifest["rendered_sha256"]:
        raise IdentityError("regular profile altered the compiled instruction payload")
    current_workspace = _workspace_snapshot(contract)
    expected_workspace = {
        name: report[name] for name in ("branch", "head", "tree", "dirty")
    }
    if current_workspace != expected_workspace:
        raise IdentityError("candidate workspace changed after preflight")
    if current_workspace["dirty"]:
        raise IdentityError("candidate worktree is not clean before launch")
    launch_environment, launch_identity = build_launch_identity(
        target=contract.target,
        repo=contract.repo,
        argv=argv,
        source_environment=(
            profile_context.source_environment if profile_context is not None else None
        ),
        bindings=(profile_context.bindings if profile_context is not None else None),
        admitted_lane_root=(
            profile_context.profile_root if profile_context is not None else None
        ),
    )
    manifest.verify_launch_execution_environment(launch_environment)
    registry = SessionRegistry(state_root)
    tmux = TmuxController(state_root)
    socket = tmux.socket_path(session)
    reservation = {
        "schema_version": 1,
        "session": session,
        "contract_fingerprint": contract.fingerprint,
        "proof_root": str(proof_root),
        "expected_socket": str(socket),
        "instruction_manifest_sha256": instruction_manifest_sha,
        "created_at": _utc_now(),
    }
    journal = _journal(proof_root)
    metadata = None
    process = None
    process_verified = False
    lease_active = False
    lease_owned = False
    reservation_owned = False
    activated = False
    launch_attempted = False

    def admit_before_start() -> None:
        nonlocal launch_attempted, lease_owned, reservation_owned
        admit_session_lease(
            session=session,
            target=contract.target,
            controller=contract.controller,
            owner=session_lease_owner,
            instruction_manifest_sha256=instruction_manifest_sha,
        )
        lease_owned = True
        registry.reserve(reservation)
        reservation_owned = True
        journal.append(
            request_id=_delivery_request_id(session, session, "launch"),
            event={
                "kind": "launch",
                "phase": "intent",
                "contract_fingerprint": contract.fingerprint,
                "manifest_fingerprint": manifest.fingerprint,
                "content_sha256": initial_sha,
                "instruction_manifest_sha256": instruction_manifest_sha,
                "instruction_policy_fingerprint": compiled.manifest[
                    "instruction_policy_fingerprint"
                ],
                "effective_contract_fingerprint": compiled.manifest[
                    "effective_contract_fingerprint"
                ],
                "subscription_profile_sha256": profile_binding_sha,
            },
        )
        launch_attempted = True

    def revalidate_before_target_start() -> TargetLaunch:
        if profile_context is None:
            return TargetLaunch(
                argv=list(argv),
                environment=dict(launch_environment),
                launch_identity=dict(launch_identity),
            )
        refreshed, refreshed_status = subscription_profile_preflight(
            profile_root=profile_context.profile_root,
            expected_target=contract.target,
            expected_executable_path=manifest.raw["executable"]["resolved_path"],
        )
        if refreshed_status["login_state"] != "logged_in":
            raise IdentityError(
                "private subscription profile authentication changed before target start"
            )
        refreshed_environment, refreshed_identity = build_launch_identity(
            target=contract.target,
            repo=contract.repo,
            argv=argv,
            source_environment=refreshed.source_environment,
            bindings=refreshed.bindings,
            admitted_lane_root=refreshed.profile_root,
        )
        manifest.verify_launch_execution_environment(refreshed_environment)
        if (
            refreshed.manifest_sha256 != profile_context.manifest_sha256
            or refreshed.public_binding != profile_context.public_binding
            or refreshed_environment != launch_environment
            or refreshed_identity != launch_identity
        ):
            raise IdentityError(
                "private subscription profile launch context changed before target start"
            )
        return TargetLaunch(
            argv=list(argv),
            environment=refreshed_environment,
            launch_identity=refreshed_identity,
        )

    operation_guard = exclusive_lock(registry.operation_lock(session))
    operation_guard.__enter__()
    try:
        if registry.exists(session):
            raise ConflictError("session is already reserved or registered")
        if socket.exists() or tmux.exists(socket, session):
            raise ConflictError("tmux socket or session already exists")
    except BaseException:
        operation_guard.__exit__(None, None, None)
        raise

    try:
        metadata = tmux.launch(
            session=session,
            target=contract.target,
            repo=contract.repo,
            argv=argv,
            environment=launch_environment,
            admitted_lane_root=(
                profile_context.profile_root if profile_context is not None else None
            ),
            before_start=admit_before_start,
            before_target_start=revalidate_before_target_start,
        )
        if metadata.get("launch_identity") != launch_identity:
            raise IdentityError("tmux launch context identity is invalid")

        def assert_pane_owner(expected_pid: int) -> None:
            current = tmux.metadata(
                socket=Path(metadata["socket"]),
                session=session,
                pane=metadata["pane"],
                server_identity=metadata["server_identity"],
            )
            if (
                current.get("session") != session
                or current.get("pane") != metadata["pane"]
                or current.get("pane_pid") != expected_pid
                or current.get("pane_dead") is True
            ):
                raise IdentityError(
                    "tmux pane no longer owns the provisional runtime process"
                )

        sample_process = _process_birth_fn or (
            lambda selected_pid: process_birth_identity(selected_pid)
        )
        process = bind_runtime_process(
            metadata["pane_pid"],
            manifest,
            assert_pane_owner,
            process_sample_fn=sample_process,
            monotonic_fn=_execution_monotonic_fn,
            sleep_fn=_execution_sleep_fn,
        )
        process_verified = True
        transition_session_lease(
            session=session,
            target=contract.target,
            controller=contract.controller,
            owner=session_lease_owner,
            instruction_manifest_sha256=instruction_manifest_sha,
            state="active",
            process=process,
        )
        lease_active = True
        record = {
            "schema_version": SESSION_REGISTRY_SCHEMA_VERSION,
            "session": session,
            "controller": contract.controller,
            "target": contract.target,
            "lease_owner": session_lease_owner,
            "contract_fingerprint": contract.fingerprint,
            "contract_path": str(contract_copy),
            "state": "STARTING",
            "repo": str(contract.repo),
            "branch": contract.branch,
            "mutation_owner": contract.mutation_owner,
            "proof_root": str(proof_root),
            "tmux": {
                "socket": metadata["socket"],
                "socket_identity": metadata["socket_identity"],
                "session": session,
                "pane": metadata["pane"],
                "server_identity": metadata["server_identity"],
                "tmux_binary_identity": metadata["tmux_binary_identity"],
            },
            "process": process,
            "supervisor": supervisor,
            "adapter": {
                "manifest_path": str(manifest_copy),
                "manifest_fingerprint": manifest.fingerprint,
                "executable_fingerprint": manifest.raw["executable"]["sha256"],
                "execution_fingerprint": manifest.execution_fingerprint,
                "adapter_fingerprint": manifest.raw["adapter_fingerprint"],
                "protocol_fingerprint": manifest.raw["protocol_fingerprint"],
                "qualification_controller": qualification_authority["controller"],
                "qualification_campaign_id": qualification_authority["campaign_id"],
                "qualification_goal_fingerprint": qualification_authority[
                    "goal_fingerprint"
                ],
            },
            "instructions": {
                "manifest_path": str(instruction_copy),
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
            },
            "protocol": protocol,
            "created_at": _utc_now(),
            "last_checkpoint": None,
            "last_beacon": None,
            "blocker": None,
        }
        registry.activate(record)
        activated = True
        registry.verify_instructions(record)
        journal.append(
            request_id=_delivery_request_id(session, session, "started"),
            event={
                "kind": "launch",
                "phase": "target_started",
                "target_pid": process["pid"],
                "tmux_target_id": metadata["pane"],
                "launch_identity": metadata["launch_identity"],
                "subscription_profile_sha256": profile_binding_sha,
            },
        )
        settle_seconds = startup_settle_seconds_for(contract.target)
        _sleep_fn(settle_seconds)
        settled = tmux.metadata(
            socket=Path(metadata["socket"]),
            session=session,
            pane=metadata["pane"],
            server_identity=metadata["server_identity"],
        )
        if (
            settled.get("pane") != metadata["pane"]
            or settled.get("pane_pid") != process["pid"]
            or settled.get("pane_dead") is True
            or not process_alive(process)
        ):
            raise IdentityError("target changed during bounded startup settle")
        manifest.verify_process_executable(process)
        registry.verify_instructions(record)
        journal.append(
            request_id=_delivery_request_id(session, session, "input-settled"),
            event={
                "kind": "launch",
                "phase": "input_settled",
                "strategy": INPUT_READINESS_STRATEGY,
                "seconds": settle_seconds,
            },
        )
        registry.verify_instructions(record)
        delivery = _deliver(
            tmux=tmux,
            socket=Path(metadata["socket"]),
            session=session,
            pane=metadata["pane"],
            buffer_name=session + "-initial",
            message=initial,
            proof_root=proof_root,
            operation_id=session + "-initial",
            kind="initial_message",
        )
        registry.transition_path(session, ["ACTIVE"])
        journal.append(
            request_id=_delivery_request_id(session, session, "active"),
            event={"kind": "launch", "phase": "active", **delivery},
        )
        viewer = attach_command(state_root=state_root, session=session)
        return {
            "ok": True,
            "session": session,
            "state": "ACTIVE",
            "instruction_policy_fingerprint": compiled.manifest[
                "instruction_policy_fingerprint"
            ],
            "effective_contract_fingerprint": compiled.manifest[
                "effective_contract_fingerprint"
            ],
            "attach_command": viewer["attach_command"],
            "attach_ticket_ttl_seconds": viewer["ticket_ttl_seconds"],
        }
    except BaseException:
        cleanup_stopped = False
        cleanup_error = None
        if metadata is not None:
            try:
                if lease_active:
                    transition_session_lease(
                        session=session,
                        target=contract.target,
                        controller=contract.controller,
                        owner=session_lease_owner,
                        instruction_manifest_sha256=instruction_manifest_sha,
                        state="halting",
                        process=process,
                    )
                cleanup_stopped = _cleanup_incomplete_launch(
                    tmux=tmux,
                    metadata=metadata,
                    session=session,
                    target=contract.target,
                    process=process,
                    process_verified=process_verified,
                    journal=journal,
                )
            except Exception as cleanup_exc:
                cleanup_error = "%s: %s" % (
                    cleanup_exc.__class__.__name__,
                    str(cleanup_exc)[:500],
                )
        if activated:
            try:
                registry.update(
                    session,
                    {
                        "state": "BLOCKED",
                        "blocker": {
                            "code": "launch_incomplete",
                            "target_process_alive": (
                                process_alive(process)
                                if process_verified and process is not None
                                else None
                            ),
                            "cleanup_stopped": cleanup_stopped,
                            "cleanup_error": cleanup_error,
                        },
                    },
                )
            except Exception:
                pass
        elif cleanup_stopped or not launch_attempted:
            if reservation_owned:
                try:
                    registry.release_reservation(session, contract.fingerprint)
                except Exception:
                    pass
            if lease_owned:
                try:
                    transition_session_lease(
                        session=session,
                        target=contract.target,
                        controller=contract.controller,
                        owner=session_lease_owner,
                        instruction_manifest_sha256=instruction_manifest_sha,
                        state="failed",
                        process=process if process_verified else None,
                    )
                except Exception:
                    pass
        raise
    finally:
        operation_guard.__exit__(None, None, None)


def send_message(
    *, state_root: Path, session: str, message: str, request_id: str
) -> Dict[str, Any]:
    validate_identifier(request_id, "request id")
    registry = SessionRegistry(Path(state_root))
    with exclusive_lock(registry.operation_lock(session)):
        record = registry.load(session)
        contract = _bound_contract(record)
        tmux, _ = _runtime(registry, record, "send", require_process=True)
        adapter = adapter_for(record["target"])
        protocol = dict(record["protocol"])
        if protocol["kind"] == "conformance":
            first_submission = (
                record["state"] == "CONFORMANCE_READY"
                and protocol["phase"] == "ready_validated"
            )
            replay = (
                record["state"] == "ACTIVE"
                and protocol["phase"] == "followup_sent"
                and protocol["message_id"] == request_id
            )
            if not first_submission and not replay:
                raise ValidationError(
                    "conformance follow-up is not currently authorized"
                )
            enveloped = adapter.envelope(
                _followup_envelope(protocol, request_id, message),
                contract.session_profile,
                initial=False,
            )
        else:
            if record["state"] not in {"ACTIVE", "WAITING_EXTERNAL"}:
                raise ValidationError("source session is not accepting messages")
            enveloped = adapter.envelope(
                message, contract.session_profile, initial=False
            )
        delivery = _deliver(
            tmux=tmux,
            socket=Path(record["tmux"]["socket"]),
            session=session,
            pane=record["tmux"]["pane"],
            buffer_name=request_id,
            message=enveloped,
            proof_root=Path(record["proof_root"]),
            operation_id=request_id,
            kind="send",
        )
        if protocol["kind"] == "conformance" and first_submission:
            if delivery["delivery"] not in {"submitted", "already_submitted"}:
                raise ConflictError(
                    "conformance follow-up delivery is not authoritative"
                )
            protocol.update(phase="followup_sent", message_id=request_id)
            registry.transition_path(session, ["ACTIVE"], {"protocol": protocol})
        return {"ok": True, "session": session, **delivery}


def status(*, state_root: Path, session: str) -> Dict[str, Any]:
    registry = SessionRegistry(Path(state_root))
    record = registry.load(session)
    contract = _bound_contract(record)
    _, metadata = _runtime(registry, record, "status", require_process=False)
    alive = process_alive(record["process"])
    return {
        "ok": True,
        "session": session,
        "controller": record["controller"],
        "target": record["target"],
        "session_profile": contract.session_profile,
        "repo": record["repo"],
        "branch": record["branch"],
        "mutation_owner": record["mutation_owner"],
        "state": record["state"],
        "target_process_alive": alive,
        "tmux_alive": not metadata["pane_dead"],
        "protocol": record["protocol"],
        "last_checkpoint": record["last_checkpoint"],
        "last_beacon": record["last_beacon"],
        "blocker": record["blocker"],
    }


def record_beacon(*, state_root: Path, session: str, line: str) -> Dict[str, Any]:
    """Ingest one line from an adapter-owned sanitized event hook."""
    registry = SessionRegistry(Path(state_root))
    record = registry.load(session)
    _bound_contract(record)
    _runtime(registry, record, "status", require_process=True)
    beacon = dict(parse_beacon(line), received_at=_utc_now())
    registry.update(session, {"last_beacon": beacon})
    return {"ok": True, "session": session, "beacon": beacon}


def wait_for(
    *,
    state_root: Path,
    session: str,
    condition: str,
    timeout: float,
    interval: float = 0.25,
) -> Dict[str, Any]:
    if condition not in {
        "beacon",
        "checkpoint",
        "action-required",
        "target-stopped",
        "done",
    }:
        raise ValidationError("unsupported wait condition")
    if timeout < 0 or timeout > 300:
        raise ValidationError("wait timeout must be between zero and 300 seconds")
    deadline = time.monotonic() + timeout
    while True:
        report = status(state_root=state_root, session=session)
        if condition == "beacon":
            matched = report["last_beacon"] is not None
        elif condition == "checkpoint":
            matched = report["last_checkpoint"] is not None
        elif condition == "action-required":
            matched = report["blocker"] is not None
        elif condition == "target-stopped":
            matched = not report["target_process_alive"]
        else:
            matched = is_terminal(report["state"])
        if matched:
            report.update(condition=condition, matched=True)
            return report
        if time.monotonic() >= deadline:
            return {
                "ok": True,
                "session": session,
                "condition": condition,
                "matched": False,
            }
        time.sleep(interval)


def _checkpoint_expected(record: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
    protocol = record["protocol"]
    expected = {
        "session": record["session"],
        "run_id": protocol["run_id"],
        "nonce": protocol["nonce"],
        "executable_fingerprint": record["adapter"]["executable_fingerprint"],
        "execution_fingerprint": record["adapter"]["execution_fingerprint"],
        "adapter_fingerprint": record["adapter"]["adapter_fingerprint"],
        "protocol_fingerprint": record["adapter"]["protocol_fingerprint"],
    }
    if protocol["kind"] == "conformance":
        if protocol["phase"] == "awaiting_ready" and record["state"] == "ACTIVE":
            expected.update(phase="ready", sequence=0)
            return expected, "ready"
        if protocol["phase"] == "followup_sent" and record["state"] == "ACTIVE":
            expected.update(
                phase="followup",
                sequence=1,
                message_id=protocol["message_id"],
                prior_checkpoint_sha256=protocol["ready_artifact_sha256"],
            )
            return expected, "followup"
        raise ValidationError("conformance checkpoint is out of sequence")
    if protocol["phase"] == "awaiting_source" and record["state"] == "ACTIVE":
        return expected, "source"
    if protocol["phase"] == "source_accepted" and record["state"] == "SOURCE_ACCEPTED":
        return expected, "proof"
    raise ValidationError("source checkpoint is out of sequence")


def import_checkpoint(
    *, state_root: Path, session: str, handoff_path: Path
) -> Dict[str, Any]:
    registry = SessionRegistry(Path(state_root))
    record = registry.load(session)
    contract = _bound_contract(record)
    _runtime(registry, record, "checkpoint", require_process=True)
    expected, phase = _checkpoint_expected(record)
    handoff = validate_handoff(
        Path(handoff_path),
        allowed_roots=[Path(record["proof_root"]), Path(record["repo"])],
        expected=expected,
    )
    protocol = dict(record["protocol"])
    if protocol["kind"] == "conformance":
        if handoff.checkpoint_kind != "conformance":
            raise ValidationError("conformance session requires conformance handoffs")
        if tree_fingerprint(contract.repo) != protocol["fixture_fingerprint"]:
            raise IdentityError("protected conformance fixture content drifted")
        if phase == "ready":
            protocol.update(
                phase="ready_validated",
                ready_checkpoint_id=handoff.checkpoint_id,
                ready_artifact_sha256=handoff.artifact_sha256,
            )
            next_state = "CONFORMANCE_READY"
        else:
            protocol.update(
                phase="followup_validated",
                followup_checkpoint_id=handoff.checkpoint_id,
            )
            next_state = "CONFORMANCE_CHECKPOINT_READY"
    else:
        if handoff.checkpoint_kind != "source":
            raise ValidationError("source session requires source handoffs")
        current_head = handoff.identity["candidate_commit"]
        _verify_source_identity(contract, current_head)
        if phase == "source":
            protocol.update(phase="source_checkpoint", source_commit=current_head)
            next_state = "SOURCE_CHECKPOINT_READY"
        else:
            parent = _git(contract.repo, ["rev-parse", "HEAD^"], identity_error=True)
            if parent != protocol["source_commit"]:
                raise IdentityError(
                    "proof checkpoint is not a child of accepted source"
                )
            changed = _git(
                contract.repo,
                ["diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"],
                identity_error=True,
            ).splitlines()
            if not changed or any(
                not any(
                    path.startswith(prefix) for prefix in contract.proof_path_prefixes
                )
                for path in changed
            ):
                raise IdentityError(
                    "proof checkpoint changed files outside proof-only paths"
                )
            protocol.update(phase="proof_checkpoint", proof_commit=current_head)
            next_state = "PROOF_CHECKPOINT_READY"
    reference = handoff.reference()
    registry.update(
        session,
        {"state": next_state, "last_checkpoint": reference, "protocol": protocol},
    )
    _journal(Path(record["proof_root"])).append(
        request_id=handoff.checkpoint_id,
        event={
            "kind": "checkpoint_imported",
            "checkpoint_id": handoff.checkpoint_id,
            "artifact_sha256": handoff.artifact_sha256,
            "checkpoint_kind": handoff.checkpoint_kind,
        },
    )
    return {"ok": True, **reference}


def _current_handoff(record: Dict[str, Any], checkpoint_id: str) -> ValidatedHandoff:
    validate_identifier(checkpoint_id, "checkpoint id")
    reference = record.get("last_checkpoint")
    if not reference or reference.get("checkpoint_id") != checkpoint_id:
        raise IdentityError("explicit checkpoint is not the current checkpoint")
    handoff = validate_handoff(
        Path(reference["path"]),
        allowed_roots=[Path(record["proof_root"]), Path(record["repo"])],
        expected=reference["identity"],
    )
    if (
        handoff.checkpoint_id != checkpoint_id
        or handoff.artifact_sha256 != reference["artifact_sha256"]
    ):
        raise IdentityError("checkpoint artifact changed")
    return handoff


def review_checkpoint(
    *,
    state_root: Path,
    session: str,
    checkpoint_id: str,
    actor: str,
    verdict: str,
    evidence_path: Path,
) -> Dict[str, Any]:
    registry = SessionRegistry(Path(state_root))
    record = registry.load(session)
    contract = _bound_contract(record)
    _runtime(registry, record, "checkpoint", require_process=True)
    handoff = _current_handoff(record, checkpoint_id)
    verify_current_identity(
        {
            "checkpoint_id": handoff.checkpoint_id,
            "artifact_sha256": handoff.artifact_sha256,
            "checkpoint_identity": handoff.identity,
        },
        checkpoint_id=checkpoint_id,
        artifact_sha256=record["last_checkpoint"]["artifact_sha256"],
        candidate_commit=handoff.identity.get("candidate_commit"),
    )
    protocol = dict(record["protocol"])
    if handoff.checkpoint_kind == "source":
        _verify_source_identity(contract, handoff.identity["candidate_commit"])
    if handoff.checkpoint_kind == "conformance":
        if record["state"] != "CONFORMANCE_CHECKPOINT_READY":
            raise ValidationError("conformance checkpoint is not reviewable")
        transition(record["state"], "AWAITING_CONFORMANCE_REVIEW")
        if verdict in {"block", "fail"}:
            transition(
                "AWAITING_CONFORMANCE_REVIEW",
                "FAILED" if verdict == "fail" else "BLOCKED",
            )
    elif record["state"] == "SOURCE_CHECKPOINT_READY":
        transition(record["state"], "AWAITING_SOURCE_REVIEW")
        destination = {
            "repair": "ACTIVE",
            "source_accept": "SOURCE_ACCEPTED",
            "block": "BLOCKED",
            "fail": "FAILED",
        }.get(verdict)
        if destination is not None:
            transition("AWAITING_SOURCE_REVIEW", destination)
    elif record["state"] == "PROOF_CHECKPOINT_READY":
        if verdict == "repair":
            raise ValidationError(
                "final proof repair requires a fresh source-review session"
            )
        transition(record["state"], "TARGET_DONE")
        transition("TARGET_DONE", "AWAITING_CONTROLLER_REVIEW")
        destination = {
            "repair": "ACTIVE",
            "block": "BLOCKED",
            "fail": "FAILED",
        }.get(verdict)
        if destination is not None:
            transition("AWAITING_CONTROLLER_REVIEW", destination)
    else:
        raise ValidationError("source checkpoint is not reviewable")
    review = record_review(
        contract=contract,
        actor=actor,
        handoff=handoff,
        verdict=verdict,
        evidence_path=evidence_path,
        verdict_root=Path(record["proof_root"]) / "verdicts",
    )
    if handoff.checkpoint_kind == "conformance":
        states = ["AWAITING_CONFORMANCE_REVIEW"]
        if verdict == "block":
            states.append("BLOCKED")
        elif verdict == "fail":
            states.append("FAILED")
        protocol["phase"] = "reviewed"
    elif record["state"] == "SOURCE_CHECKPOINT_READY":
        states = ["AWAITING_SOURCE_REVIEW"]
        if verdict == "repair":
            states.append("ACTIVE")
            protocol.update(
                phase="awaiting_source", source_commit=None, proof_commit=None
            )
        elif verdict == "source_accept":
            states.append("SOURCE_ACCEPTED")
            protocol["phase"] = "source_accepted"
        elif verdict == "block":
            states.append("BLOCKED")
        else:
            states.append("FAILED")
    else:
        states = ["TARGET_DONE", "AWAITING_CONTROLLER_REVIEW"]
        if verdict == "block":
            states.append("BLOCKED")
        elif verdict == "fail":
            states.append("FAILED")
        else:
            protocol["phase"] = "final_reviewed"
    registry.transition_path(session, states, {"protocol": protocol})
    return {"ok": True, "review": review}


def accept_checkpoint(
    *,
    state_root: Path,
    session: str,
    checkpoint_id: str,
    actor: str,
    evidence_path: Path,
) -> Dict[str, Any]:
    registry = SessionRegistry(Path(state_root))
    record = registry.load(session)
    contract = _bound_contract(record)
    _runtime(registry, record, "checkpoint", require_process=True)
    handoff = _current_handoff(record, checkpoint_id)
    review_path = Path(record["proof_root"]) / "verdicts" / (checkpoint_id + ".json")
    review = read_json(review_path, max_bytes=131072)
    verify_current_identity(
        review,
        checkpoint_id=checkpoint_id,
        artifact_sha256=handoff.artifact_sha256,
        candidate_commit=handoff.identity.get("candidate_commit"),
    )
    if handoff.checkpoint_kind == "conformance":
        if (
            record["state"] != "AWAITING_CONFORMANCE_REVIEW"
            or review.get("verdict") != "conformance_accept"
        ):
            raise ValidationError("conformance checkpoint lacks an accept review")
    else:
        if (
            record["state"] != "AWAITING_CONTROLLER_REVIEW"
            or review.get("verdict") != "source_accept"
        ):
            raise ValidationError("source proof checkpoint lacks a final accept review")
        _verify_source_identity(contract, handoff.identity["candidate_commit"])
    acceptance = record_acceptance(
        contract=contract,
        actor=actor,
        review=review,
        evidence_path=evidence_path,
        acceptance_root=Path(record["proof_root"]) / "acceptance",
    )
    protocol = dict(record["protocol"])
    protocol["phase"] = "accepted"
    registry.transition_path(session, ["ACCEPTED"], {"protocol": protocol})
    return {"ok": True, "acceptance": acceptance, "state": "ACCEPTED"}


def attach_command(*, state_root: Path, session: str) -> Dict[str, Any]:
    state_root = Path(state_root).resolve(strict=True)
    registry = SessionRegistry(state_root)
    record = registry.load(session)
    _bound_contract(record)
    tmux, metadata = _runtime(registry, record, "status", require_process=True)
    attach_argv = tmux.attach_argv(
        socket=Path(record["tmux"]["socket"]),
        session=session,
        pane=record["tmux"]["pane"],
        server_identity=record["tmux"]["server_identity"],
    )
    helper_path = Path(__file__).resolve(strict=True).parents[1] / "viewer_attach.py"
    interpreter_path = Path(sys.executable).resolve(strict=True)
    ticket = build_view_ticket(
        session=session,
        state_root=state_root,
        expected_identity=_viewer_identity(record, metadata, attach_argv),
        helper_path=helper_path,
        interpreter_path=interpreter_path,
    )
    ticket_path = state_root / "views" / (session + "-" + ticket["nonce"] + ".json")
    prepared = prepare_view_ticket(
        helper_argv=[
            str(interpreter_path),
            str(helper_path),
            "--state-root",
            str(state_root),
            "--session",
            session,
            "--ticket",
            str(ticket_path),
        ],
        ticket=ticket,
        state_root=state_root,
        session=session,
    )
    return {
        "ok": True,
        "session": session,
        "attach_command": prepared["attach_command"],
        "ticket_path": prepared["ticket_path"],
        "ticket_ttl_seconds": TICKET_TTL_SECONDS,
        "read_only": True,
        "execution_time_identity_check": True,
    }


def _viewer_identity(
    record: Dict[str, Any],
    metadata: Dict[str, Any],
    attach_argv: List[str],
) -> Dict[str, Any]:
    return {
        "socket_identity_sha256": sha256_bytes(
            canonical_json_bytes(record["tmux"]["socket_identity"])
        ),
        "server_identity_sha256": sha256_bytes(
            canonical_json_bytes(record["tmux"]["server_identity"])
        ),
        "tmux_binary_identity_sha256": sha256_bytes(
            canonical_json_bytes(record["tmux"]["tmux_binary_identity"])
        ),
        "process_identity_sha256": sha256_bytes(
            canonical_json_bytes(record["process"])
        ),
        "pane": metadata["pane"],
        "pane_pid": metadata["pane_pid"],
        "attach_argv_sha256": sha256_bytes(canonical_json_bytes(attach_argv)),
    }


def open_view(
    *,
    state_root: Path,
    session: str,
    terminal: str = "auto",
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Open an optional separate human terminal on the exact native TUI."""
    state_root = Path(state_root).resolve(strict=True)
    registry = SessionRegistry(state_root)
    record = registry.load(session)
    _bound_contract(record)
    tmux, metadata = _runtime(registry, record, "status", require_process=True)
    socket = Path(record["tmux"]["socket"])
    server_identity = record["tmux"]["server_identity"]
    attach_argv = tmux.attach_argv(
        socket=socket,
        session=session,
        pane=record["tmux"]["pane"],
        server_identity=server_identity,
    )
    helper_path = Path(__file__).resolve(strict=True).parents[1] / "viewer_attach.py"
    ticket = build_view_ticket(
        session=session,
        state_root=state_root,
        expected_identity=_viewer_identity(record, metadata, attach_argv),
        helper_path=helper_path,
        interpreter_path=Path(sys.executable).resolve(strict=True),
    )
    ticket_path = state_root / "views" / (session + "-" + ticket["nonce"] + ".json")
    helper_argv = [
        str(Path(sys.executable).resolve(strict=True)),
        str(helper_path),
        "--state-root",
        str(state_root.resolve(strict=True)),
        "--session",
        session,
        "--ticket",
        str(ticket_path),
    ]
    before_clients = {
        (client["pid"], client["tty"])
        for client in tmux.viewer_clients(
            socket=socket,
            session=session,
            server_identity=server_identity,
        )
    }
    prepared = prepare_operator_view(
        helper_argv=helper_argv,
        ticket=ticket,
        state_root=state_root,
        session=session,
        terminal=terminal,
    )
    if dry_run:
        revoke_ticket(Path(prepared["ticket_path"]))
        return {
            "ok": True,
            "session": session,
            "read_only": True,
            "native_tui": False,
            "native_tui_requested": True,
            "controller_attached": False,
            "terminal_app": prepared["terminal_app"],
            "terminal_app_path": prepared["terminal_app_path"],
            "viewer_command": prepared["viewer_command"],
            "open_request_submitted": False,
            "viewer_attached": False,
            "ticket_revoked": True,
        }

    ticket_path = Path(prepared["ticket_path"])
    try:
        dispatch_operator_view(prepared)
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            current_record = registry.load(session)
            current_tmux, _ = _runtime(
                registry,
                current_record,
                "status",
                require_process=True,
            )
            clients = current_tmux.viewer_clients(
                socket=socket,
                session=session,
                server_identity=server_identity,
            )
            new_clients = [
                client
                for client in clients
                if (client["pid"], client["tty"]) not in before_clients
            ]
            if any(not client["read_only"] for client in new_clients):
                raise IdentityError("new native viewer client is not read-only")
            claim = ticket_claim_identity(ticket_path) if new_clients else None
            matching_clients = []
            if claim is not None:
                for client in new_clients:
                    if client["pid"] != claim["pid"]:
                        continue
                    client_process = process_birth_identity(client["pid"])
                    if client_process["kernel_birth_id"] == claim["kernel_birth_id"]:
                        matching_clients.append(client)
            if matching_clients:
                revoke_ticket(ticket_path)
                return {
                    "ok": True,
                    "session": session,
                    "read_only": True,
                    "native_tui": True,
                    "controller_attached": False,
                    "terminal_app": prepared["terminal_app"],
                    "terminal_app_path": prepared["terminal_app_path"],
                    "viewer_command": prepared["viewer_command"],
                    "open_request_submitted": True,
                    "viewer_attached": True,
                    "new_read_only_clients": len(matching_clients),
                    "ticket_revoked": True,
                }
            time.sleep(0.1)
        raise UnsupportedError("native viewer attachment was not structurally observed")
    except BaseException:
        revoke_ticket(ticket_path)
        raise


def attach_viewer(*, state_root: Path, session: str, ticket_path: Path) -> None:
    """Execution-time ticket claim, identity revalidation, then exact tmux exec."""
    state_root = Path(state_root).resolve(strict=True)
    helper_path = Path(__file__).resolve(strict=True).parents[1] / "viewer_attach.py"
    helper_process = process_birth_identity(os.getpid())
    ticket = load_and_claim_ticket(
        ticket_path=Path(ticket_path),
        state_root=state_root,
        session=session,
        helper_path=helper_path,
        interpreter_path=Path(sys.executable).resolve(strict=True),
        claimant_pid=helper_process["pid"],
        claimant_kernel_birth_id=helper_process["kernel_birth_id"],
    )
    registry = SessionRegistry(state_root)
    record = registry.load(session)
    _bound_contract(record)
    tmux, metadata = _runtime(registry, record, "status", require_process=True)
    attach_argv = tmux.attach_argv(
        socket=Path(record["tmux"]["socket"]),
        session=session,
        pane=record["tmux"]["pane"],
        server_identity=record["tmux"]["server_identity"],
    )
    if ticket.get("expected_identity") != _viewer_identity(
        record,
        metadata,
        attach_argv,
    ):
        raise IdentityError("viewer runtime identity changed after ticket issue")
    if ticket_is_revoked(Path(ticket_path)):
        raise ConflictError("viewer ticket was revoked before attach")
    term = os.environ.get("TERM", "xterm-256color")
    if (
        not term
        or len(term) > 64
        or any(
            character
            not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._+-"
            for character in term
        )
    ):
        raise ValidationError("viewer terminal type is invalid")
    environment = {
        "PATH": "/usr/bin:/bin",
        "LANG": "C",
        "LC_ALL": "C",
        "TERM": term,
    }
    os.execve(attach_argv[0], attach_argv, environment)


def halt(*, state_root: Path, session: str, timeout: float = 10.0) -> Dict[str, Any]:
    if timeout < 0 or timeout > 60:
        raise ValidationError("halt timeout must be between zero and 60 seconds")
    registry = SessionRegistry(Path(state_root))
    with exclusive_lock(registry.operation_lock(session)):
        record = registry.load(session)
        _bound_contract(record)
        journal = _journal(Path(record["proof_root"]))
        if record["state"] == "HALTED":
            reconcile_halted_session_lease(
                session=session,
                target=record["target"],
                controller=record["controller"],
                owner=record["lease_owner"],
                instruction_manifest_sha256=record["instructions"]["manifest_sha256"],
                process=record["process"],
            )
            terminal = _halt_terminal_result(journal, session)
            if terminal is not None:
                return terminal
            return {
                "ok": True,
                "session": session,
                "state": "HALTED",
                "signal_sent": False,
                "tmux_preserved": True,
            }

        transition(record["state"], "HALTED")
        tmux, metadata = _runtime(registry, record, "halt", require_process=False)
        target_alive = process_alive(record["process"])
        if not target_alive and not metadata["pane_dead"]:
            raise IdentityError(
                "registered process identity changed while its tmux pane remains live"
            )
        transition_session_lease(
            session=session,
            target=record["target"],
            controller=record["controller"],
            owner=record["lease_owner"],
            instruction_manifest_sha256=record["instructions"]["manifest_sha256"],
            state="halting",
            process=record["process"],
        )
        journal.append(
            request_id=_delivery_request_id(session, session, "halt-intent"),
            event={
                "kind": "halt",
                "session": session,
                "target_pid": record["process"]["pid"],
                "result": "intent",
            },
        )
        deadline = time.monotonic() + timeout

        def deliver_one(action: str) -> None:
            if not process_alive(record["process"]):
                raise IdentityError("registered target stopped before its halt action")
            registry.verify_process(record)
            if action == "exact_pid_sigint":
                send_exact_sigint(record["process"])
            elif action == "tmux_pane_eof":
                tmux.send_control(
                    socket=Path(record["tmux"]["socket"]),
                    session=session,
                    pane=record["tmux"]["pane"],
                    key="C-d",
                    expected_pane_pid=record["process"]["pid"],
                )
            else:
                raise IdentityError("registered target selected an unknown halt action")

        def pause_after_send() -> None:
            time.sleep(min(0.25, max(0.0, deadline - time.monotonic())))

        submitted_actions = deliver_halt_actions(
            journal=journal,
            session=session,
            target_identity=record["process"],
            actions=list(adapter_for(record["target"]).graceful_halt_actions),
            process_alive=lambda: process_alive(record["process"]),
            deliver_action=deliver_one,
            after_send=pause_after_send,
        )
        while process_alive(record["process"]) and time.monotonic() < deadline:
            time.sleep(0.1)
        if process_alive(record["process"]):
            raise IdentityError(
                "registered target did not stop gracefully; no broad kill attempted"
            )
        halted_metadata = tmux.metadata(
            socket=Path(record["tmux"]["socket"]),
            session=session,
            pane=record["tmux"]["pane"],
        )
        if (
            halted_metadata["pane_pid"] != record["process"]["pid"]
            or not halted_metadata["pane_dead"]
            or tmux.socket_identity(Path(record["tmux"]["socket"]))
            != record["tmux"]["socket_identity"]
        ):
            raise IdentityError("registered tmux evidence did not survive exact halt")
        journal.append(
            request_id=_delivery_request_id(session, session, "halted"),
            event={
                "kind": "halt",
                "session": session,
                "target_pid": record["process"]["pid"],
                "result": "stopped",
                "signal_sent": bool(submitted_actions),
                "tmux_preserved": True,
            },
        )
        record = dict(record)
        record["state"] = "HALTED"
        registry.validate(record)
        atomic_write_json(registry._path(session), record)
        transition_session_lease(
            session=session,
            target=record["target"],
            controller=record["controller"],
            owner=record["lease_owner"],
            instruction_manifest_sha256=record["instructions"]["manifest_sha256"],
            state="halted",
            process=record["process"],
        )
        return {
            "ok": True,
            "session": session,
            "state": "HALTED",
            "signal_sent": bool(submitted_actions),
            "tmux_preserved": True,
        }
