"""Test-only builder for a structurally linked Puppet qualification receipt."""

from __future__ import annotations

import json
import os
import socket
import stat
from pathlib import Path

from puppet_lib.handoffs import validate_handoff
from puppet_lib.safety import sha256_file


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
    version_fingerprint: str,
    platform_fingerprint: str,
    adapter_fingerprint: str,
    protocol_fingerprint: str,
    yolo_mapping_sha256: str,
    capabilities: list[str],
) -> dict:
    receipt_path = Path(receipt_path)
    run_root = receipt_path.parent
    proof_root = run_root / (receipt_path.stem + "-proof")
    handoff_root = proof_root / "fixture" / "handoffs"
    handoff_root.mkdir(mode=0o700, parents=True)
    session = "test-%s-session" % target
    nonce = "testnonce1234"
    timestamp = "2026-07-22T04:00:00Z"
    common = {
        "schema_version": 1,
        "checkpoint_kind": "conformance",
        "session": session,
        "run_id": run_id,
        "nonce": nonce,
        "executable_fingerprint": executable_fingerprint,
        "adapter_fingerprint": adapter_fingerprint,
        "protocol_fingerprint": protocol_fingerprint,
        "timestamp": timestamp,
        "claims": [
            {"id": "source_free_contract_acknowledged", "status": "ready"}
        ],
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
    review_evidence_sha256 = "a" * 64
    review_path = proof_root / "review.json"
    _write_json(
        review_path,
        {
            "schema_version": 1,
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
                "fixture_fingerprint": "6" * 64,
                "initial_payload_sha256": "c" * 64,
                "followup_payload_sha256": "d" * 64,
            },
        },
    )
    acceptance_path = proof_root / "acceptance.json"
    _write_json(
        acceptance_path,
        {
            "schema_version": 1,
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
                else "tmux_exact_pane_ctrl_c"
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
    executable_details = executable_path.stat()
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
    fixture_fingerprint = "6" * 64
    evidence_path = proof_root / "evidence.json"
    _write_json(
        evidence_path,
        {
            "schema_version": 1,
            "run_id": run_id,
            "target": target,
            "controller": controller,
            "profile": "source-free-pass-b-v1",
            "campaign_id": "test-campaign",
            "authorization_sha256": sha256_file(authorization_path),
            "manifest_fingerprint": "7" * 64,
            "executable_fingerprint": executable_fingerprint,
            "version_fingerprint": version_fingerprint,
            "platform_fingerprint": platform_fingerprint,
            "adapter_fingerprint": adapter_fingerprint,
            "protocol_fingerprint": protocol_fingerprint,
            "yolo_mapping_sha256": yolo_mapping_sha256,
            "launch_argv_sha256": "8" * 64,
            "input_transport": "tmux_load_buffer_stdin",
            "payload_argv_absent": True,
            "active_target_processes_before_launch": [],
            "active_target_processes_after_halt": [],
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
            "halt_sha256": sha256_file(halt_path),
            "acceptance_sha256": sha256_file(acceptance_path),
            "review_sha256": sha256_file(review_path),
            "process": {
                "pid": 4242,
                "start": "Wed Jul 22 04:00:00 2026",
                "command": executable_path.name,
                "executable_path": str(executable_path),
                "device": executable_details.st_dev,
                "inode": executable_details.st_ino,
            },
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

    receipt = {
        "schema_version": 1,
        "kind": "real_harness_conformance",
        "run_id": run_id,
        "target": target,
        "result": "accepted",
        "controller": controller,
        "executable_fingerprint": executable_fingerprint,
        "version_fingerprint": version_fingerprint,
        "platform_fingerprint": platform_fingerprint,
        "adapter_fingerprint": adapter_fingerprint,
        "protocol_fingerprint": protocol_fingerprint,
        "yolo_mapping_sha256": yolo_mapping_sha256,
        "capabilities": list(capabilities),
        "accepted_checkpoint_id": followup.checkpoint_id,
        "acceptance_sha256": sha256_file(acceptance_path),
        "halt_receipt_sha256": sha256_file(halt_path),
        "proof_refs": [
            reference("authorization", authorization_path),
            reference("evidence", evidence_path),
            reference("halt", halt_path),
            reference("ready", ready_path),
            reference("followup", followup_path),
            reference("review", review_path),
            reference("acceptance", acceptance_path),
        ],
    }
    _write_json(receipt_path, receipt)
    return receipt
