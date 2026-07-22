from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "puppet" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from puppet_lib.adapter_manifest import AdapterManifest  # noqa: E402
from puppet_lib.conformance import create_fixture  # noqa: E402
from puppet_lib.contracts import Contract  # noqa: E402
from puppet_lib.errors import ConflictError, IdentityError, ValidationError  # noqa: E402
from puppet_lib.registry import SessionRegistry  # noqa: E402
from puppet_lib.session import (  # noqa: E402
    _deliver,
    accept_checkpoint,
    halt,
    import_checkpoint,
    launch,
    record_beacon,
    review_checkpoint,
    send_message,
    status,
    wait_for,
)
from puppet_lib.tmux import TmuxController  # noqa: E402


HARD_GATES = [
    "merge",
    "push",
    "deploy",
    "force_push",
    "global_install",
    "external_send",
    "spend",
    "secrets",
    "account_change",
    "destructive_cleanup",
]


def write_json(path: Path, value):
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")


def git(repo: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *arguments],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return result.stdout.strip()


def commit_all(repo: Path, message: str) -> str:
    git(repo, "add", "-A")
    subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "-c",
            "user.name=Puppet Test",
            "-c",
            "user.email=puppet@example.invalid",
            "commit",
            "-q",
            "-m",
            message,
        ],
        check=True,
    )
    return git(repo, "rev-parse", "HEAD")


def initialize_repo(path: Path, branch: str, name: str) -> Path:
    path.mkdir()
    subprocess.run(["git", "init", "-q", "-b", branch, str(path)], check=True)
    marker = path / (name + ".txt")
    marker.write_text(name + "\n", encoding="utf-8")
    commit_all(path, name)
    return path


def manifest(target: str, executable: Path, protocol: str, receipt_path: Path):
    executable_sha = hashlib.sha256(executable.read_bytes()).hexdigest()
    executable_stat = executable.stat()
    adapter_fingerprint = "d" * 64
    yolo_mapping = {
        "complete": True,
        "launch_argv": [str(executable)],
        "permission_declared": True,
        "permission_flags": ["test-owned-process"],
        "prompt_transport": "tmux_stdin_buffer",
        "prompt_transport_declared": True,
        "sandbox_disable_declared": True,
        "sandbox_flags": ["test-owned-process"],
    }
    write_json(
        receipt_path,
        {
            "schema_version": 1,
            "kind": "real_harness_conformance",
            "run_id": "kernel-test-qualification",
            "target": target,
            "result": "accepted",
            "controller": "tester",
            "executable_fingerprint": executable_sha,
            "adapter_fingerprint": adapter_fingerprint,
            "protocol_fingerprint": protocol,
            "yolo_mapping_sha256": hashlib.sha256(
                json.dumps(
                    yolo_mapping,
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                ).encode("utf-8")
            ).hexdigest(),
            "capabilities": [
                "launch",
                "send",
                "status",
                "wait",
                "checkpoint",
                "resume",
                "halt",
            ],
            "accepted_checkpoint_id": "1" * 64,
            "acceptance_sha256": "2" * 64,
            "halt_receipt_sha256": "3" * 64,
            "proof_refs": ["deterministic/test-owned-kernel"],
        },
    )
    raw = {
        "schema_version": 1,
        "target": target,
        "generated_at": "2026-07-22T03:00:00Z",
        "platform": {"system": "Darwin", "release": "test", "machine": "test"},
        "executable": {
            "requested_path": str(executable),
            "resolved_path": str(executable),
            "sha256": executable_sha,
            "version_sha256": "b" * 64,
            "help_sha256": "c" * 64,
            "device": executable_stat.st_dev,
            "inode": executable_stat.st_ino,
            "size": executable_stat.st_size,
            "mtime_ns": executable_stat.st_mtime_ns,
        },
        "adapter_fingerprint": adapter_fingerprint,
        "protocol_fingerprint": protocol,
        "yolo_mapping": yolo_mapping,
        "capabilities": {
            name: "controller_verified"
            for name in ("launch", "send", "status", "wait", "checkpoint", "resume", "halt")
        },
        "doctor_only": False,
        "qualification": {
            "receipt_path": str(receipt_path),
            "receipt_sha256": hashlib.sha256(receipt_path.read_bytes()).hexdigest(),
        },
    }
    return AdapterManifest.from_dict(raw).raw


def controller_files(
    root: Path,
    *,
    candidate: Path,
    branch: str,
    session: str,
    task_profile: str,
    protocol_fingerprint: str,
):
    supervisor = initialize_repo(root / "supervisor", "main", "supervisor")
    supervisor_executable = supervisor / "puppet.py"
    supervisor_executable.write_text("# immutable test supervisor\n", encoding="utf-8")
    commit_all(supervisor, "supervisor executable")
    executable = Path("/bin/cat").resolve(strict=True)
    manifest_path = root / "manifest.json"
    write_json(
        manifest_path,
        manifest(
            "codex",
            executable,
            protocol_fingerprint,
            root / "qualification-receipt.json",
        ),
    )
    proof = root / "controller-proof"
    state_root = root / "state"
    proof.mkdir()
    state_root.mkdir()
    contract_raw = {
        "schema_version": 1,
        "objective": "Exercise the composed Puppet controller kernel",
        "campaign_authorization_id": "campaign-test",
        "controller": "tester",
        "target": "codex",
        "task_profile": task_profile,
        "harness_trust": "unrestricted_required",
        "mutation_owner": "none" if task_profile == "conformance" else "target",
        "repo": str(candidate),
        "branch": branch,
        "allowed_modes": (
            ["read", "test"]
            if task_profile == "conformance"
            else ["read", "test", "mutate", "local_commit"]
        ),
        "terminal_criteria": [
            {
                "id": "conformance_green" if task_profile == "conformance" else "source_green",
                "evidence": "validated_handoff",
            }
        ],
        "hard_gates": HARD_GATES,
        "supervisor_root": str(supervisor),
        "candidate_root": str(candidate),
    }
    if task_profile != "conformance":
        contract_raw.update(
            run_id="source-run",
            nonce="source-nonce",
            proof_path_prefixes=["proof/"],
        )
    Contract.from_dict(contract_raw)
    contract_path = root / "controller-contract.json"
    write_json(contract_path, contract_raw)
    authorization_path = root / "authorization.json"
    write_json(
        authorization_path,
        {
            "campaign_id": "campaign-test",
            "acknowledged_at": "2026-07-22T03:00:00Z",
            "authorization": {
                "trust_profile": "unrestricted_required",
                "harnesses": ["codex"],
            },
        },
    )
    return {
        "supervisor_executable": supervisor_executable,
        "manifest": manifest_path,
        "contract": contract_path,
        "authorization": authorization_path,
        "proof": proof,
        "state": state_root,
        "session": session,
    }


def kill_test_server(socket):
    if socket:
        subprocess.run(
            ["tmux", "-S", socket, "kill-server"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        Path(socket).unlink(missing_ok=True)


class SessionIntegrationTests(unittest.TestCase):
    def test_delivery_deduplication_is_scoped_to_the_exact_session(self):
        class RecordingTmux:
            def __init__(self):
                self.deliveries = []

            def paste_bytes(self, **kwargs):
                self.deliveries.append(kwargs)

        with tempfile.TemporaryDirectory() as temporary:
            proof_root = Path(temporary).resolve()
            tmux = RecordingTmux()
            common = {
                "tmux": tmux,
                "socket": proof_root / "unused.sock",
                "pane": "%0",
                "buffer_name": "message-1",
                "message": "One bounded message.",
                "proof_root": proof_root,
                "operation_id": "message-1",
                "kind": "send",
            }
            first = _deliver(session="session-one", **common)
            second = _deliver(session="session-two", **common)
            replay = _deliver(session="session-one", **common)
            self.assertEqual(first["delivery"], "submitted")
            self.assertEqual(second["delivery"], "submitted")
            self.assertEqual(replay["delivery"], "already_submitted")
            self.assertEqual(len(tmux.deliveries), 2)

    def test_complete_conformance_path_is_bound_and_accept_is_terminal(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            session = "codex-kernel-test"
            fixture = root / "fixture"
            fixture_contract = create_fixture(
                fixture, run_id="run-1", session=session, target="codex"
            )
            subprocess.run(
                ["git", "init", "-q", "-b", "codex/conformance-fixture", str(fixture)],
                check=True,
            )
            commit_all(fixture, "fixture")
            files = controller_files(
                root,
                candidate=fixture,
                branch="codex/conformance-fixture",
                session=session,
                task_profile="conformance",
                protocol_fingerprint=fixture_contract["protocol_fingerprint"],
            )
            socket = None
            try:
                launched = launch(
                    session=session,
                    contract_path=files["contract"],
                    manifest_path=files["manifest"],
                    authorization_path=files["authorization"],
                    proof_root=files["proof"],
                    state_root=files["state"],
                    supervisor_executable=files["supervisor_executable"],
                    prompt="Write the bounded ready handoff and wait.",
                )
                self.assertEqual(launched["state"], "ACTIVE")
                self.assertFalse(
                    wait_for(
                        state_root=files["state"],
                        session=session,
                        condition="beacon",
                        timeout=0,
                    )["matched"]
                )
                recorded_beacon = record_beacon(
                    state_root=files["state"],
                    session=session,
                    line='PUPPET_STATUS {"phase":"ready-contract"}',
                )
                self.assertEqual(recorded_beacon["beacon"]["authority"], "target_claim")
                beacon_wait = wait_for(
                    state_root=files["state"],
                    session=session,
                    condition="beacon",
                    timeout=0,
                )
                self.assertTrue(beacon_wait["matched"])
                self.assertEqual(
                    beacon_wait["last_beacon"]["kind"], "status_claim"
                )
                record = SessionRegistry(files["state"]).load(session)
                socket = record["tmux"]["socket"]
                bound_contract_path = Path(record["contract_path"])
                bound_contract = json.loads(bound_contract_path.read_text(encoding="utf-8"))
                tampered_contract = dict(bound_contract, controller="other-controller")
                write_json(bound_contract_path, tampered_contract)
                with self.assertRaises(IdentityError):
                    status(state_root=files["state"], session=session)
                write_json(bound_contract_path, bound_contract)
                ready = {
                    "schema_version": 1,
                    "checkpoint_kind": "conformance",
                    "session": session,
                    "run_id": fixture_contract["run_id"],
                    "nonce": fixture_contract["nonce"],
                    "phase": "ready",
                    "sequence": 0,
                    "executable_fingerprint": record["adapter"]["executable_fingerprint"],
                    "adapter_fingerprint": record["adapter"]["adapter_fingerprint"],
                    "protocol_fingerprint": record["adapter"]["protocol_fingerprint"],
                    "timestamp": "2026-07-22T03:01:00Z",
                    "claims": [],
                    "evidence_refs": [],
                    "decisions_requested": [],
                    "limitations": [],
                }
                ready_path = fixture / "handoffs" / "ready.json"
                write_json(ready_path, ready)
                ready_import = import_checkpoint(
                    state_root=files["state"], session=session, handoff_path=ready_path
                )
                self.assertEqual(
                    status(state_root=files["state"], session=session)["state"],
                    "CONFORMANCE_READY",
                )
                message = "Write the one sequenced follow-up and wait."
                sent = send_message(
                    state_root=files["state"],
                    session=session,
                    message=message,
                    request_id="message-1",
                )
                self.assertEqual(sent["delivery"], "submitted")
                replay = send_message(
                    state_root=files["state"],
                    session=session,
                    message=message,
                    request_id="message-1",
                )
                self.assertEqual(replay["delivery"], "already_submitted")
                with self.assertRaises(ConflictError):
                    send_message(
                        state_root=files["state"],
                        session=session,
                        message="Different content must never be delivered.",
                        request_id="message-1",
                    )
                followup = dict(ready)
                followup.update(
                    phase="followup",
                    sequence=1,
                    message_id="message-1",
                    prior_checkpoint_sha256=ready_import["artifact_sha256"],
                    timestamp="2026-07-22T03:02:00Z",
                )
                followup_path = fixture / "handoffs" / "followup.json"
                write_json(followup_path, followup)
                wrong_followup = dict(followup, prior_checkpoint_sha256="f" * 64)
                write_json(followup_path, wrong_followup)
                with self.assertRaises(ValidationError):
                    import_checkpoint(
                        state_root=files["state"],
                        session=session,
                        handoff_path=followup_path,
                    )
                write_json(followup_path, followup)
                imported = import_checkpoint(
                    state_root=files["state"], session=session, handoff_path=followup_path
                )
                before = status(state_root=files["state"], session=session)["state"]
                self.assertEqual(before, "CONFORMANCE_CHECKPOINT_READY")
                review_evidence = files["proof"] / "review.json"
                write_json(review_evidence, {"findings": [], "classification": "clean"})
                with self.assertRaises(IdentityError):
                    review_checkpoint(
                        state_root=files["state"],
                        session=session,
                        checkpoint_id="f" * 64,
                        actor="tester",
                        verdict="conformance_accept",
                        evidence_path=review_evidence,
                    )
                with self.assertRaises(ValidationError):
                    review_checkpoint(
                        state_root=files["state"],
                        session=session,
                        checkpoint_id=imported["checkpoint_id"],
                        actor="codex",
                        verdict="conformance_accept",
                        evidence_path=review_evidence,
                    )
                self.assertEqual(status(state_root=files["state"], session=session)["state"], before)
                review_checkpoint(
                    state_root=files["state"],
                    session=session,
                    checkpoint_id=imported["checkpoint_id"],
                    actor="tester",
                    verdict="conformance_accept",
                    evidence_path=review_evidence,
                )
                self.assertEqual(
                    status(state_root=files["state"], session=session)["state"],
                    "AWAITING_CONFORMANCE_REVIEW",
                )
                bad = files["proof"] / "bad-acceptance.json"
                write_json(bad, {"terminal_criteria": []})
                with self.assertRaises(ValidationError):
                    accept_checkpoint(
                        state_root=files["state"],
                        session=session,
                        checkpoint_id=imported["checkpoint_id"],
                        actor="tester",
                        evidence_path=bad,
                    )
                acceptance = files["proof"] / "acceptance.json"
                write_json(acceptance, {"terminal_criteria": ["conformance_green"]})
                accepted = accept_checkpoint(
                    state_root=files["state"],
                    session=session,
                    checkpoint_id=imported["checkpoint_id"],
                    actor="tester",
                    evidence_path=acceptance,
                )
                self.assertEqual(accepted["state"], "ACCEPTED")
                self.assertEqual(
                    halt(state_root=files["state"], session=session, timeout=5)["state"],
                    "HALTED",
                )
            finally:
                kill_test_server(socket)

    def test_halt_seals_an_exact_blocked_session_when_target_already_stopped(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            candidate = initialize_repo(root / "candidate", "codex/dead-target", "candidate")
            session = "codex-dead-target"
            files = controller_files(
                root,
                candidate=candidate,
                branch="codex/dead-target",
                session=session,
                task_profile="implementation",
                protocol_fingerprint="e" * 64,
            )
            socket = None
            try:
                launch(
                    session=session,
                    contract_path=files["contract"],
                    manifest_path=files["manifest"],
                    authorization_path=files["authorization"],
                    proof_root=files["proof"],
                    state_root=files["state"],
                    supervisor_executable=files["supervisor_executable"],
                    prompt="Remain available for exact halt.",
                )
                registry = SessionRegistry(files["state"])
                record = registry.load(session)
                socket = record["tmux"]["socket"]
                TmuxController(files["state"]).interrupt(
                    socket=Path(socket),
                    session=session,
                    pane=record["tmux"]["pane"],
                )
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    metadata = TmuxController(files["state"]).metadata(
                        socket=Path(socket), session=session, pane=record["tmux"]["pane"]
                    )
                    if metadata["pane_dead"]:
                        break
                    time.sleep(0.05)
                self.assertTrue(metadata["pane_dead"])
                registry.update(
                    session,
                    {
                        "state": "BLOCKED",
                        "blocker": {
                            "code": "launch_incomplete",
                            "target_process_alive": False,
                        },
                    },
                )
                result = halt(state_root=files["state"], session=session, timeout=1)
                self.assertEqual(result["state"], "HALTED")
                self.assertFalse(result["signal_sent"])
                self.assertTrue(result["tmux_preserved"])
                replay = halt(state_root=files["state"], session=session, timeout=1)
                self.assertEqual(replay["state"], "HALTED")
            finally:
                kill_test_server(socket)

    def test_source_and_proof_child_path_reaches_controller_acceptance(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            candidate = initialize_repo(
                root / "candidate", "codex/source-fixture", "candidate"
            )
            session = "codex-source-test"
            files = controller_files(
                root,
                candidate=candidate,
                branch="codex/source-fixture",
                session=session,
                task_profile="implementation",
                protocol_fingerprint="e" * 64,
            )
            socket = None
            try:
                launch(
                    session=session,
                    contract_path=files["contract"],
                    manifest_path=files["manifest"],
                    authorization_path=files["authorization"],
                    proof_root=files["proof"],
                    state_root=files["state"],
                    supervisor_executable=files["supervisor_executable"],
                    prompt="Create one bounded source commit and wait.",
                )
                record = SessionRegistry(files["state"]).load(session)
                socket = record["tmux"]["socket"]
                (candidate / "feature.txt").write_text("bounded source\n", encoding="utf-8")
                source_commit = commit_all(candidate, "source")

                def write_source_handoff(path: Path, commit: str, summary: str):
                    write_json(
                        path,
                        {
                            "schema_version": 1,
                            "checkpoint_kind": "source",
                            "session": session,
                            "run_id": "source-run",
                            "nonce": "source-nonce",
                            "candidate_commit": commit,
                            "executable_fingerprint": record["adapter"]["executable_fingerprint"],
                            "adapter_fingerprint": record["adapter"]["adapter_fingerprint"],
                            "protocol_fingerprint": record["adapter"]["protocol_fingerprint"],
                            "timestamp": "2026-07-22T03:10:00Z",
                            "summary": summary,
                            "claims": [],
                            "evidence_refs": [],
                            "decisions_requested": [],
                            "limitations": [],
                            "suggested_next_assignment": "Controller review",
                        },
                    )

                source_path = files["proof"] / "source-handoff.json"
                write_source_handoff(source_path, source_commit, "Bounded source checkpoint")
                source_import = import_checkpoint(
                    state_root=files["state"], session=session, handoff_path=source_path
                )
                review_evidence = files["proof"] / "source-review.json"
                write_json(review_evidence, {"findings": [], "classification": "clean"})
                review_checkpoint(
                    state_root=files["state"],
                    session=session,
                    checkpoint_id=source_import["checkpoint_id"],
                    actor="tester",
                    verdict="source_accept",
                    evidence_path=review_evidence,
                )
                self.assertEqual(
                    status(state_root=files["state"], session=session)["state"],
                    "SOURCE_ACCEPTED",
                )
                proof_dir = candidate / "proof"
                proof_dir.mkdir()
                write_json(proof_dir / "receipt.json", {"source_commit": source_commit})
                proof_commit = commit_all(candidate, "proof")
                proof_handoff = files["proof"] / "proof-handoff.json"
                write_source_handoff(proof_handoff, proof_commit, "Proof-only child checkpoint")
                proof_import = import_checkpoint(
                    state_root=files["state"], session=session, handoff_path=proof_handoff
                )
                final_review = files["proof"] / "final-review.json"
                write_json(final_review, {"findings": [], "classification": "clean"})
                review_checkpoint(
                    state_root=files["state"],
                    session=session,
                    checkpoint_id=proof_import["checkpoint_id"],
                    actor="tester",
                    verdict="source_accept",
                    evidence_path=final_review,
                )
                self.assertEqual(
                    status(state_root=files["state"], session=session)["state"],
                    "AWAITING_CONTROLLER_REVIEW",
                )
                acceptance = files["proof"] / "source-acceptance.json"
                write_json(acceptance, {"terminal_criteria": ["source_green"]})
                accepted = accept_checkpoint(
                    state_root=files["state"],
                    session=session,
                    checkpoint_id=proof_import["checkpoint_id"],
                    actor="tester",
                    evidence_path=acceptance,
                )
                self.assertEqual(accepted["state"], "ACCEPTED")
                self.assertEqual(
                    halt(state_root=files["state"], session=session, timeout=5)["state"],
                    "HALTED",
                )
            finally:
                kill_test_server(socket)


if __name__ == "__main__":
    unittest.main()
