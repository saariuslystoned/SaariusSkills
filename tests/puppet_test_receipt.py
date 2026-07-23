"""Test-only builder for a structurally linked Puppet qualification receipt."""

from __future__ import annotations

import json
import os
import socket
import stat
from pathlib import Path

from puppet_lib.contracts import MANDATORY_HARD_GATES
from puppet_lib.authority import QUALIFICATION_ATTESTATION_SCHEMA_VERSION
from puppet_lib.adapter_manifest import (
    QUALIFICATION_EVIDENCE_SCHEMA_VERSION,
    QUALIFICATION_RECEIPT_SCHEMA_VERSION,
)
from puppet_lib.handoffs import HANDOFF_SCHEMA_VERSION, validate_handoff
from puppet_lib.instructions import compile_instruction_wrapper
from puppet_lib.launch import build_admitted_launch_plan
from puppet_lib.profiles import (
    INPUT_READINESS_STRATEGY,
    OBSERVED_INPUT_TRANSPORT,
    SUBMIT_SETTLE_SECONDS,
    default_session_profile,
    startup_settle_seconds_for,
)
from puppet_lib.safety import canonical_json_bytes, sha256_bytes, sha256_file
from puppet_lib.subscription_profiles import (
    STATUS_SCHEMA,
    build_subscription_launch_binding,
    initialize_subscription_profile,
    subscription_profile_launch_context,
)
from puppet_lib.verdicts import ACCEPTANCE_SCHEMA_VERSION, REVIEW_SCHEMA_VERSION


def _write_json(path: Path, value) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")


def write_qualification_receipt(
    receipt_path: Path,
    *,
    run_id: str,
    target: str,
    controller: str,
    executable_path: Path,
    executable_fingerprint: str,
    execution_fingerprint: str,
    version_fingerprint: str,
    platform_fingerprint: str,
    adapter_fingerprint: str,
    protocol_fingerprint: str,
    yolo_mapping_sha256: str,
    launch_argv: list[str],
    capabilities: list[str],
    session_profile: str | None = None,
    runtime_executable_path: Path | None = None,
) -> dict:
    if target == "agy":
        raise AssertionError("synthetic accepted AGY receipts are unsupported")
    receipt_path = Path(receipt_path)
    run_root = receipt_path.parent
    proof_root = run_root / (receipt_path.stem + "-proof")
    handoff_root = proof_root / "fixture" / "handoffs"
    handoff_root.mkdir(mode=0o700, parents=True)
    session = "test-%s-session" % target
    nonce = "testnonce1234"
    timestamp = "2026-07-22T04:00:00Z"
    if session_profile is None:
        session_profile = default_session_profile(target)
    common = {
        "schema_version": HANDOFF_SCHEMA_VERSION,
        "checkpoint_kind": "conformance",
        "session": session,
        "run_id": run_id,
        "nonce": nonce,
        "executable_fingerprint": executable_fingerprint,
        "execution_fingerprint": execution_fingerprint,
        "adapter_fingerprint": adapter_fingerprint,
        "protocol_fingerprint": protocol_fingerprint,
        "timestamp": timestamp,
        "claims": [{"id": "source_free_contract_acknowledged", "status": "ready"}],
        "evidence_refs": [],
        "decisions_requested": [],
        "limitations": [],
    }
    ready_value = dict(common, phase="ready", sequence=0)
    ready_path = handoff_root / "ready.json"
    _write_json(ready_path, ready_value)
    ready = validate_handoff(ready_path, allowed_roots=[run_root])
    followup_value = dict(
        common,
        phase="followup",
        sequence=1,
        message_id="test-message-1",
        prior_checkpoint_sha256=ready.artifact_sha256,
    )
    followup_value["claims"] = [
        {"id": "source_free_contract_acknowledged", "status": "followup"}
    ]
    followup_path = handoff_root / "followup.json"
    _write_json(followup_path, followup_value)
    followup = validate_handoff(followup_path, allowed_roots=[run_root])

    contract_fingerprint = "9" * 64
    fixture_fingerprint = "6" * 64
    compiled = compile_instruction_wrapper(
        target=target,
        task="Perform the bounded synthetic conformance task.",
        contract_identity={
            "fingerprint": contract_fingerprint,
            "controller": controller,
            "target": target,
            "task_profile": "source-free-pass-b-v2",
        },
        workspace_identity={
            "fixture_fingerprint": fixture_fingerprint,
            "workspace": "isolated_conformance_fixture",
        },
        run_identity={"session": session, "run_id": run_id, "nonce": nonce},
        session_profile=session_profile,
        model_binding="default",
        effort_binding="default",
        runtime_contract_layer={
            "mutation_owner": "none",
            "allowed_modes": ["read", "test"],
            "hard_gates": sorted(MANDATORY_HARD_GATES),
        },
    )
    review_evidence_sha256 = "a" * 64
    review_path = proof_root / "review.json"
    _write_json(
        review_path,
        {
            "schema_version": REVIEW_SCHEMA_VERSION,
            "timestamp": timestamp,
            "actor": controller,
            "target": target,
            "contract_fingerprint": contract_fingerprint,
            "checkpoint_id": followup.checkpoint_id,
            "checkpoint_kind": "conformance",
            "checkpoint_identity": followup.identity,
            "artifact_sha256": followup.artifact_sha256,
            "verdict": "conformance_accept",
            "evidence_sha256": review_evidence_sha256,
            "evidence_summary": {
                "classification": "clean",
                "findings": [],
                "observed_capabilities": [
                    "launch",
                    "send",
                    "status",
                    "wait",
                    "checkpoint",
                    "halt",
                ],
                "fixture_fingerprint": fixture_fingerprint,
                "initial_payload_sha256": compiled.manifest["rendered_sha256"],
                "followup_payload_sha256": "d" * 64,
            },
        },
    )
    acceptance_path = proof_root / "acceptance.json"
    _write_json(
        acceptance_path,
        {
            "schema_version": ACCEPTANCE_SCHEMA_VERSION,
            "timestamp": timestamp,
            "actor": controller,
            "checkpoint_id": followup.checkpoint_id,
            "review_verdict": "conformance_accept",
            "review_evidence_sha256": review_evidence_sha256,
            "contract_fingerprint": contract_fingerprint,
            "terminal_criteria": ["conformance_green"],
            "acceptance_evidence_sha256": "b" * 64,
        },
    )
    halt_path = proof_root / "halt.json"
    _write_json(
        halt_path,
        {
            "schema_version": 1,
            "timestamp": timestamp,
            "session": session,
            "stopped": True,
            "tmux_preserved": True,
            "signal_sent": True,
            "signal": (
                "tmux_exact_pane_ctrl_d_twice"
                if target == "agy"
                else "exact_registered_pid_sigint"
            ),
            "cleanup_scope": "exact_new_target_only",
            "reason": "accepted_probe_halt",
            "target_pid": 4242,
        },
    )
    authorization_path = proof_root / "authorization.json"
    _write_json(
        authorization_path,
        {
            "schema_version": 1,
            "campaign_id": "test-campaign",
            "operator_identity": "tester",
            "controller": controller,
            "goal": {
                "repository": "test/SaariusSkills",
                "commit": "1" * 40,
                "path": "plans/puppet/codex-goal.md",
                "sha256": "2" * 64,
            },
            "acknowledged_at": timestamp,
            "authorization": {
                "harnesses": [target],
                "trust_profile": "unrestricted_required",
                "disable_harness_sandbox_where_exposed": True,
                "ordinary_configured_model_provider_traffic": True,
                "scope": "bounded Puppet implementation and conformance campaign only",
            },
            "allowed_actions": [
                "read",
                "test",
                "mutate_isolated_worktrees",
                "local_commit",
                "internal_between_session_promotion",
            ],
            "hard_gates": [
                "merge",
                "push",
                "pull_request_creation",
                "release",
                "deploy",
                "publish",
                "global_install",
                "external_send",
                "spend",
                "delete_or_archive",
                "account_or_security_change",
                "secret_or_auth_data_access",
                "interference_with_preexisting_processes_or_sessions",
            ],
        },
    )
    executable_path = Path(executable_path).resolve(strict=True)
    runtime_path = Path(runtime_executable_path or executable_path).resolve(strict=True)
    executable_details = runtime_path.stat()
    target_process = {
        "identity_version": 2,
        "pid": 4242,
        "start": "Wed Jul 22 04:00:00 2026",
        "kernel_birth_id": "test:4242",
        "command": runtime_path.name,
        "executable_path": str(runtime_path),
        "device": executable_details.st_dev,
        "inode": executable_details.st_ino,
    }
    socket_path = proof_root / "s"
    socket_server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    socket_server.bind(str(socket_path))
    os.chmod(socket_path, 0o600)
    socket_server.close()
    socket_details = socket_path.stat()
    lock_path = proof_root / "l"
    lock_path.touch(mode=0o600)
    os.chmod(lock_path, 0o600)
    lock_details = lock_path.stat()
    instruction_path = proof_root / "effective-instructions.json"
    _write_json(instruction_path, compiled.manifest)
    subscription_root = proof_root / "subscription-profile-root"
    initialize_subscription_profile(
        target=target,
        profile_root=subscription_root,
        executable_path=executable_path,
    )
    subscription_context = subscription_profile_launch_context(
        profile_root=subscription_root,
        expected_target=target,
        expected_executable_path=executable_path,
    )
    subscription_status = {
        "schema": STATUS_SCHEMA,
        "target": target,
        "profile_root": str(subscription_context.profile_root),
        "login_state": "logged_in",
        "method": {
            "codex": "chatgpt",
            "claude": "claude.ai",
            "cursor": "private_file_store",
            "grok": "private_grok_home",
        }[target],
        "status_exit": 0,
        "raw_output_retained": False,
        "login_performed": False,
        "model_launched": False,
    }
    if target == "claude":
        subscription_status["provider"] = "firstParty"
    if target == "grok":
        subscription_status["default_model"] = "grok-4.5"
    subscription_binding = build_subscription_launch_binding(
        subscription_context, subscription_status
    )
    subscription_profile_path = proof_root / "subscription-profile.json"
    _write_json(subscription_profile_path, subscription_binding)
    launch_environment = {
        **subscription_context.source_environment,
        **subscription_context.bindings,
    }
    launch_plan_path = proof_root / "launch-plan.json"
    launch_plan = build_admitted_launch_plan(
        target=target,
        session=session,
        run_id=run_id,
        repo=handoff_root.parent,
        argv=launch_argv,
        environment=launch_environment,
        admitted_lane_root=subscription_root,
    )
    _write_json(launch_plan_path, launch_plan)
    launch_identity = {
        "cwd": launch_plan["cwd"],
        "argv_sha256": sha256_bytes(canonical_json_bytes(launch_plan["argv"])),
        "env_names": launch_plan["env_names"],
        "env_fingerprint": launch_plan["env_fingerprint"],
    }
    evidence_path = proof_root / "evidence.json"
    _write_json(
        evidence_path,
        {
            "schema_version": QUALIFICATION_EVIDENCE_SCHEMA_VERSION,
            "run_id": run_id,
            "target": target,
            "controller": controller,
            "profile": "source-free-pass-b-v2",
            "campaign_id": "test-campaign",
            "authorization_sha256": sha256_file(authorization_path),
            "manifest_fingerprint": "7" * 64,
            "executable_fingerprint": executable_fingerprint,
            "execution_fingerprint": execution_fingerprint,
            "version_fingerprint": version_fingerprint,
            "platform_fingerprint": platform_fingerprint,
            "adapter_fingerprint": adapter_fingerprint,
            "protocol_fingerprint": protocol_fingerprint,
            "yolo_mapping_sha256": yolo_mapping_sha256,
            "launch_argv_sha256": launch_identity["argv_sha256"],
            "launch_plan_sha256": sha256_file(launch_plan_path),
            "subscription_profile_sha256": sha256_file(subscription_profile_path),
            "launch_identity": launch_identity,
            "input_transport": OBSERVED_INPUT_TRANSPORT,
            "input_readiness_strategy": INPUT_READINESS_STRATEGY,
            "session_profile": session_profile,
            "startup_settle_seconds": startup_settle_seconds_for(target),
            "submit_settle_seconds": SUBMIT_SETTLE_SECONDS,
            "payload_argv_absent": True,
            "instruction_wrapper": {
                "manifest_sha256": sha256_file(instruction_path),
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
            },
            "plane_activation": None,
            "active_target_processes_before_launch": [],
            "active_target_processes_after_halt": [],
            "target_population_policy": "protected-plus-root-plus-birth-bound-descendants-v2",
            "observed_target_descendants": [],
            "last_target_population": {
                "policy": "protected-plus-root-plus-birth-bound-descendants-v2",
                "processes": [target_process],
                "ancestry_chains": [],
                "accepted": True,
            },
            "parallel_target_override": False,
            "protected_session": None,
            "parallel_isolation": None,
            "campaign_probe_lock": {
                "path": str(lock_path.resolve(strict=True)),
                "device": lock_details.st_dev,
                "inode": lock_details.st_ino,
                "uid": lock_details.st_uid,
                "mode": stat.S_IMODE(lock_details.st_mode),
            },
            "result": "accepted",
            "failure": None,
            "halt_sha256": sha256_file(halt_path),
            "acceptance_sha256": sha256_file(acceptance_path),
            "review_sha256": sha256_file(review_path),
            "process": target_process,
            "tmux": {
                "socket": str(socket_path.resolve(strict=True)),
                "session": session,
                "target_id": "%7",
                "socket_identity": {
                    "device": socket_details.st_dev,
                    "inode": socket_details.st_ino,
                    "uid": socket_details.st_uid,
                    "mode": stat.S_IMODE(socket_details.st_mode),
                },
            },
            "ready": ready.reference(),
            "followup": followup.reference(),
            "fixture_fingerprint_before": fixture_fingerprint,
            "fixture_fingerprint_after": fixture_fingerprint,
        },
    )

    def reference(kind: str, path: Path) -> dict:
        return {
            "kind": kind,
            "path": path.relative_to(run_root).as_posix(),
            "sha256": sha256_file(path),
        }

    goal = {
        "repository": "test/SaariusSkills",
        "commit": "1" * 40,
        "path": "plans/puppet/codex-goal.md",
        "sha256": "2" * 64,
    }
    receipt_core = {
        "schema_version": QUALIFICATION_RECEIPT_SCHEMA_VERSION,
        "kind": "real_harness_conformance",
        "run_id": run_id,
        "target": target,
        "session_profile": session_profile,
        "result": "accepted",
        "controller": controller,
        "campaign_id": "test-campaign",
        "goal_fingerprint": sha256_bytes(canonical_json_bytes(goal)),
        "executable_fingerprint": executable_fingerprint,
        "execution_fingerprint": execution_fingerprint,
        "version_fingerprint": version_fingerprint,
        "platform_fingerprint": platform_fingerprint,
        "adapter_fingerprint": adapter_fingerprint,
        "protocol_fingerprint": protocol_fingerprint,
        "yolo_mapping_sha256": yolo_mapping_sha256,
        "launch_plan_sha256": sha256_file(launch_plan_path),
        "subscription_profile_sha256": sha256_file(subscription_profile_path),
        "instruction_policy_fingerprint": compiled.manifest[
            "instruction_policy_fingerprint"
        ],
        "capabilities": list(capabilities),
        "accepted_checkpoint_id": followup.checkpoint_id,
        "acceptance_sha256": sha256_file(acceptance_path),
        "halt_receipt_sha256": sha256_file(halt_path),
        "plane_activation": None,
        "proof_refs": [
            reference("authorization", authorization_path),
            reference("subscription_profile", subscription_profile_path),
            reference("evidence", evidence_path),
            reference("launch_plan", launch_plan_path),
            reference("instructions", instruction_path),
            reference("halt", halt_path),
            reference("ready", ready_path),
            reference("followup", followup_path),
            reference("review", review_path),
            reference("acceptance", acceptance_path),
        ],
    }
    receipt_digest = sha256_bytes(canonical_json_bytes(receipt_core))
    receipt = dict(
        receipt_core,
        controller_attestation={
            "schema_version": QUALIFICATION_ATTESTATION_SCHEMA_VERSION,
            "authority_id": "puppet-local-controller-v1",
            "authority_root": str(proof_root),
            "request_id": "qualify-" + receipt_digest[:40],
            "ledger_sequence": 1,
            "ledger_entry_hash": "3" * 64,
            "receipt_digest": receipt_digest,
        },
    )
    _write_json(receipt_path, receipt)
    return receipt
