from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "puppet" / "scripts"))

from puppet_lib.beacons import parse_beacon  # noqa: E402
from puppet_lib.contracts import Contract  # noqa: E402
from puppet_lib.diagnostics import agy_overage_advisory, terminal_verdict  # noqa: E402
from puppet_lib.errors import ConflictError, ValidationError  # noqa: E402
from puppet_lib.handoffs import validate_handoff  # noqa: E402
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
            record = {
                "schema_version": 1,
                "session": "session-1",
                "controller": "codex",
                "target": "agy",
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
