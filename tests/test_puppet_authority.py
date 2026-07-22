from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "puppet" / "scripts"))

from puppet_lib.beacons import parse_beacon  # noqa: E402
import puppet_lib.campaign as puppet_campaign  # noqa: E402
from puppet_lib.authority import (  # noqa: E402
    admit_session_lease,
    current_session_lease,
    lease_owner,
)
from puppet_lib.contracts import Contract  # noqa: E402
from puppet_lib.diagnostics import agy_overage_advisory, terminal_verdict  # noqa: E402
from puppet_lib.errors import ConflictError, ValidationError  # noqa: E402
from puppet_lib.handoffs import validate_handoff  # noqa: E402
from puppet_lib.journal import Journal  # noqa: E402
from puppet_lib.registry import (  # noqa: E402
    SessionRegistry,
    process_alive,
    process_birth_identity,
)
from puppet_lib.safety import canonical_tmux_socket_path  # noqa: E402
from puppet_lib.verdicts import record_review, verify_current_identity  # noqa: E402


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


def contract(repo: Path):
    return Contract.from_dict(
        {
            "schema_version": 1,
            "objective": "Conformance",
            "campaign_authorization_id": "campaign-1",
            "controller": "codex",
            "target": "agy",
            "task_profile": "conformance",
            "harness_trust": "unrestricted_required",
            "mutation_owner": "none",
            "repo": str(repo),
            "branch": "codex/example",
            "allowed_modes": ["read", "test"],
            "terminal_criteria": [{"id": "proof_green", "evidence": "validated_handoff"}],
            "hard_gates": HARD_GATES,
        }
    )


def followup():
    return {
        "schema_version": 1,
        "checkpoint_kind": "conformance",
        "session": "agy-proof",
        "run_id": "run-1",
        "nonce": "nonce-1",
        "phase": "followup",
        "sequence": 1,
        "message_id": "message-1",
        "prior_checkpoint_sha256": "d" * 64,
        "executable_fingerprint": "a" * 64,
        "adapter_fingerprint": "b" * 64,
        "protocol_fingerprint": "c" * 64,
        "timestamp": "2026-07-22T02:00:00Z",
        "claims": [],
        "evidence_refs": [],
        "decisions_requested": [],
        "limitations": [],
    }


class AuthorityTests(unittest.TestCase):
    def test_cursor_census_includes_application_subcommand_executable(self):
        observed = []

        def identity(pid):
            observed.append(pid)
            return {"pid": pid}

        process_table = "101 /opt/bin/cursor\n102 /opt/bin/Cursor\n103 /opt/bin/cursor-agent\n"
        with patch.object(
            puppet_campaign.subprocess,
            "run",
            return_value=SimpleNamespace(returncode=0, stdout=process_table),
        ), patch.object(
            puppet_campaign,
            "process_birth_identity",
            side_effect=identity,
        ):
            result = puppet_campaign.active_target_processes("cursor")
        self.assertEqual(observed, [101, 103])
        self.assertEqual(result, [{"pid": 101}, {"pid": 103}])

    def test_target_process_snapshot_binds_ppid_birth_and_comm_without_argv(self):
        identity = {
            "pid": 4242,
            "start": "Wed Jul 22 02:05:39 2026",
            "command": "/opt/bin/codex",
            "executable_path": "/opt/bin/codex",
            "device": 1,
            "inode": 2,
        }
        process_table = (
            "4242 1 Wed Jul 22 02:05:39 2026 /opt/bin/codex\n"
            "5000 4242 Wed Jul 22 02:05:40 2026 /opt/bin/helper\n"
        )
        with patch.object(
            puppet_campaign.subprocess,
            "run",
            return_value=SimpleNamespace(returncode=0, stdout=process_table),
        ) as run, patch.object(
            puppet_campaign,
            "process_birth_identity",
            return_value=identity,
        ), patch.object(
            puppet_campaign,
            "process_alive",
            return_value=True,
        ):
            snapshot = puppet_campaign.target_process_snapshot("codex")
        self.assertEqual(snapshot["processes"], [identity])
        self.assertEqual(snapshot["parents"], {4242: 1, 5000: 4242})
        self.assertEqual(
            run.call_args.args[0],
            ["ps", "-axo", "pid=,ppid=,lstart=,comm="],
        )

    def test_duplicate_session_identity_cannot_change_state_root(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            authority = root / "authority"
            proof = root / "proof"
            first_state = root / "state-one"
            second_state = root / "state-two"
            for path in (authority, proof, first_state, second_state):
                path.mkdir(mode=0o700)
            common = {
                "activity": "session",
                "run_id": "duplicate-launch",
                "campaign_id": "campaign-test",
                "goal_fingerprint": "a" * 64,
                "proof_root": proof,
            }
            first_owner = lease_owner(state_root=first_state, **common)
            admit_session_lease(
                session="duplicate-launch",
                target="codex",
                controller="tester",
                owner=first_owner,
                authority_root=authority,
            )
            second_owner = lease_owner(state_root=second_state, **common)
            with self.assertRaisesRegex(ConflictError, "controller lease"):
                admit_session_lease(
                    session="duplicate-launch",
                    target="codex",
                    controller="tester",
                    owner=second_owner,
                    authority_root=authority,
                )
            self.assertEqual(current_session_lease(authority)["owner"], first_owner)

    def test_session_lease_projection_recovers_each_committed_transition(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            authority = root / "authority"
            authority.mkdir(mode=0o700)
            proof = root / "proof"
            proof.mkdir()
            owner = lease_owner(
                activity="probe",
                run_id="probe-crash-recovery",
                campaign_id="campaign-test",
                goal_fingerprint="a" * 64,
                proof_root=proof,
                state_root=proof,
            )
            launching = admit_session_lease(
                session="probe-crash-recovery",
                target="codex",
                controller="tester",
                owner=owner,
                authority_root=authority,
            )
            projection = authority / "current-session-lease.json"
            projection.unlink()
            self.assertEqual(current_session_lease(authority), launching)

            process = {"pid": 4242, "start": "stable"}
            history = Journal(authority / "session-lease-history")

            def append_without_projection(state: str, number: int):
                current = current_session_lease(authority)
                committed = dict(
                    current,
                    state=state,
                    process=process,
                    updated_at="2026-07-22T05:00:%02dZ" % number,
                )
                history.append(
                    request_id="lease-%d-%s" % (committed["generation"], state),
                    event={"kind": "session_lease", "lease": committed},
                )
                self.assertEqual(current_session_lease(authority), committed)
                return committed

            append_without_projection("active", 1)
            append_without_projection("halting", 2)
            append_without_projection("halted", 3)

            second_owner = lease_owner(
                activity="session",
                run_id="session-crash-recovery",
                campaign_id="campaign-test",
                goal_fingerprint="a" * 64,
                proof_root=proof,
                state_root=proof,
            )
            second = admit_session_lease(
                session="session-crash-recovery",
                target="claude",
                controller="tester",
                owner=second_owner,
                authority_root=authority,
            )
            failed = dict(
                second,
                state="failed",
                updated_at="2026-07-22T05:00:04Z",
            )
            history.append(
                request_id="lease-%d-failed" % failed["generation"],
                event={"kind": "session_lease", "lease": failed},
            )
            self.assertEqual(current_session_lease(authority), failed)

    def test_process_identity_binds_full_executable_file_identity(self):
        identity = process_birth_identity(os.getpid())
        self.assertEqual(
            set(identity),
            {"pid", "start", "command", "executable_path", "device", "inode"},
        )
        self.assertTrue(Path(identity["executable_path"]).is_absolute())
        self.assertTrue(process_alive(identity))
        self.assertFalse(process_alive(dict(identity, inode=identity["inode"] + 1)))

    def test_advisory_cannot_stop_campaign(self):
        advisory = agy_overage_advisory(
            executable_fingerprint="a" * 64, current_surface_validated=False
        )
        self.assertFalse(advisory["terminal"])
        self.assertEqual(terminal_verdict([advisory]), "continue")
        advisory["terminal"] = True
        advisory["source"] = "harness_banner"
        advisory["outcome"] = "failed"
        self.assertEqual(terminal_verdict([advisory]), "continue")
        fact = {
            "terminal": True,
            "source": "controller_protocol_failure",
            "outcome": "failed",
        }
        self.assertEqual(terminal_verdict([advisory, fact]), "failed")

    def test_beacons_are_claims_and_reject_sensitive_payloads(self):
        result = parse_beacon('PUPPET_STATUS {"phase":"testing","active":1}')
        self.assertEqual(result["authority"], "target_claim")
        for line in (
            'PUPPET_STATUS {"transcript":"leak"}',
            'PUPPET_STATUS {"phase":"one"}\nPUPPET_DONE {}',
            "UNKNOWN {}",
        ):
            with self.subTest(line=line), self.assertRaises(ValidationError):
                parse_beacon(line)

    def test_target_cannot_review_and_review_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            handoff_path = root / "handoff.json"
            handoff_path.write_text(json.dumps(followup()) + "\n", encoding="utf-8")
            handoff = validate_handoff(handoff_path, allowed_roots=[root])
            evidence = root / "review.json"
            evidence.write_text(
                json.dumps({"findings": [], "classification": "clean"}) + "\n",
                encoding="utf-8",
            )
            current_contract = contract(root)
            with self.assertRaisesRegex(ValidationError, "controller"):
                record_review(
                    contract=current_contract,
                    actor="agy",
                    handoff=handoff,
                    verdict="conformance_accept",
                    evidence_path=evidence,
                    verdict_root=root / "verdicts",
                )
            first = record_review(
                contract=current_contract,
                actor="codex",
                handoff=handoff,
                verdict="conformance_accept",
                evidence_path=evidence,
                verdict_root=root / "verdicts",
            )
            second = record_review(
                contract=current_contract,
                actor="codex",
                handoff=handoff,
                verdict="conformance_accept",
                evidence_path=evidence,
                verdict_root=root / "verdicts",
            )
            self.assertEqual(first, second)
            with self.assertRaisesRegex(ValidationError, "stale"):
                verify_current_identity(
                    first,
                    checkpoint_id=handoff.checkpoint_id,
                    artifact_sha256="f" * 64,
                )

    def test_session_collision_and_supervisor_hash_drift_fail(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root / "repo"
            proof = root / "proof"
            repo.mkdir()
            proof.mkdir()
            executable = repo / "puppet.py"
            executable.write_text("print('one')\n", encoding="utf-8")
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            subprocess.run(["git", "-C", str(repo), "add", "puppet.py"], check=True)
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
                    "fixture",
                ],
                check=True,
            )
            import hashlib

            executable_sha = hashlib.sha256(executable.read_bytes()).hexdigest()
            contract_path = proof / "controller-contract.json"
            contract_path.write_text('{"schema_version":1}\n', encoding="utf-8")
            manifest_path = proof / "adapter-manifest.json"
            manifest_path.write_text('{"schema_version":1}\n', encoding="utf-8")
            state_root = root / "state"
            registry = SessionRegistry(state_root)
            tmux_socket_path = canonical_tmux_socket_path(registry.root, "session-1")
            tmux_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            tmux_socket.bind(str(tmux_socket_path))
            tmux_socket_path.chmod(0o600)
            self.addCleanup(tmux_socket.close)
            self.addCleanup(lambda: tmux_socket_path.unlink(missing_ok=True))
            tmux_server_identity = process_birth_identity(os.getpid())
            tmux_executable = Path(
                tmux_server_identity["executable_path"]
            ).resolve(strict=True)
            tmux_details = tmux_executable.stat()
            record = {
                "schema_version": 1,
                "session": "session-1",
                "controller": "codex",
                "target": "agy",
                "lease_owner": {
                    "activity": "session",
                    "run_id": "run-1",
                    "campaign_id": "campaign-test",
                    "goal_fingerprint": "f" * 64,
                    "proof_root": str(proof.resolve(strict=True)),
                    "state_root": str(state_root.resolve(strict=True)),
                },
                "contract_fingerprint": "a" * 64,
                "contract_path": str(contract_path),
                "state": "ACTIVE",
                "repo": str(repo),
                "branch": "codex/example",
                "mutation_owner": "none",
                "proof_root": str(proof),
                "tmux": {
                    "socket": str(tmux_socket_path),
                    "socket_identity": {
                        "device": tmux_socket_path.stat().st_dev,
                        "inode": tmux_socket_path.stat().st_ino,
                        "uid": tmux_socket_path.stat().st_uid,
                        "mode": tmux_socket_path.stat().st_mode & 0o7777,
                    },
                    "session": "session-1",
                    "pane": "%1",
                    "server_identity": tmux_server_identity,
                    "tmux_binary_identity": {
                        "path": str(tmux_executable),
                        "device": tmux_details.st_dev,
                        "inode": tmux_details.st_ino,
                        "uid": tmux_details.st_uid,
                        "gid": tmux_details.st_gid,
                        "mode": tmux_details.st_mode & 0o7777,
                        "size": tmux_details.st_size,
                        "sha256": hashlib.sha256(
                            tmux_executable.read_bytes()
                        ).hexdigest(),
                        "version": "test-python",
                    },
                },
                "process": {
                    "pid": os.getpid(),
                    "start": "x",
                    "command": "python",
                    "executable_path": str(Path(sys.executable).resolve(strict=True)),
                    "device": Path(sys.executable).resolve(strict=True).stat().st_dev,
                    "inode": Path(sys.executable).resolve(strict=True).stat().st_ino,
                },
                "supervisor": {
                    "root": str(repo),
                    "commit": subprocess.run(
                        ["git", "-C", str(repo), "rev-parse", "HEAD"],
                        check=True,
                        capture_output=True,
                        text=True,
                    ).stdout.strip(),
                    "tree": subprocess.run(
                        ["git", "-C", str(repo), "rev-parse", "HEAD^{tree}"],
                        check=True,
                        capture_output=True,
                        text=True,
                    ).stdout.strip(),
                    "executable_path": str(executable),
                    "executable_sha256": executable_sha,
                },
                "adapter": {
                    "manifest_path": str(manifest_path),
                    "manifest_fingerprint": "b" * 64,
                    "executable_fingerprint": "c" * 64,
                    "adapter_fingerprint": "d" * 64,
                    "protocol_fingerprint": "e" * 64,
                    "qualification_controller": "tester",
                    "qualification_campaign_id": "campaign-test",
                    "qualification_goal_fingerprint": "f" * 64,
                },
                "protocol": {
                    "kind": "source",
                    "run_id": "run-1",
                    "nonce": "nonce-1",
                    "phase": "awaiting_source",
                    "source_commit": None,
                    "proof_commit": None,
                },
                "created_at": "2026-07-22T02:00:00Z",
                "last_checkpoint": None,
                "last_beacon": None,
                "blocker": None,
            }
            registry.create(record)
            with self.assertRaises(ConflictError):
                registry.create(record)
            registry.verify_supervisor(record)
            executable.write_text("print('two')\n", encoding="utf-8")
            with self.assertRaisesRegex(Exception, "fingerprint"):
                registry.verify_supervisor(record)


if __name__ == "__main__":
    unittest.main()
