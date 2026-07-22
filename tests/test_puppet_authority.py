from __future__ import annotations

import io
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "puppet" / "scripts"))

from puppet_lib.beacons import parse_beacon  # noqa: E402
import puppet_lib.authority as puppet_authority  # noqa: E402
import puppet_lib.campaign as puppet_campaign  # noqa: E402
import puppet_lib.registry as puppet_registry  # noqa: E402
from puppet_lib.authority import (  # noqa: E402
    acquire_real_harness_lock,
    admit_session_lease,
    current_session_lease,
    lease_owner,
    release_real_harness_lock,
    require_session_lease,
    transition_session_lease,
)
from puppet_lib.contracts import Contract  # noqa: E402
from puppet_lib.diagnostics import agy_overage_advisory, terminal_verdict  # noqa: E402
from puppet_lib.errors import (  # noqa: E402
    ConflictError,
    IdentityError,
    ValidationError,
)
from puppet_lib.handoffs import validate_handoff  # noqa: E402
from puppet_lib.instructions import compile_instruction_wrapper  # noqa: E402
from puppet_lib.journal import Journal  # noqa: E402
from puppet_lib.registry import (  # noqa: E402
    SessionRegistry,
    process_alive,
    process_birth_identity,
    send_exact_sigint,
)
from puppet_lib.safety import (  # noqa: E402
    atomic_write_json,
    canonical_tmux_socket_path,
    sha256_file,
)
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

STABLE_INSTRUCTION_MANIFEST_SHA256 = "0" * 64
ALTERNATE_INSTRUCTION_MANIFEST_SHA256 = "1" * 64


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
            "terminal_criteria": [
                {"id": "proof_green", "evidence": "validated_handoff"}
            ],
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

        process_table = (
            "101 /opt/bin/cursor\n102 /opt/bin/Cursor\n103 /opt/bin/cursor-agent\n"
        )
        with (
            patch.object(
                puppet_campaign.subprocess,
                "run",
                return_value=SimpleNamespace(returncode=0, stdout=process_table),
            ),
            patch.object(
                puppet_campaign,
                "process_birth_identity",
                side_effect=identity,
            ),
        ):
            result = puppet_campaign.active_target_processes("cursor")
        self.assertEqual(observed, [101, 103])
        self.assertEqual(result, [{"pid": 101}, {"pid": 103}])

    def test_target_process_snapshot_binds_ppid_birth_and_comm_without_argv(self):
        identity = {
            "identity_version": 2,
            "pid": 4242,
            "start": "Wed Jul 22 02:05:39 2026",
            "kernel_birth_id": "test:4242",
            "command": "/opt/bin/codex",
            "executable_path": "/opt/bin/codex",
            "device": 1,
            "inode": 2,
        }
        process_table = "4242 /opt/bin/codex\n5000 /opt/bin/helper\n"
        node = {"process": identity, "parent_pid": 1}
        with (
            patch.object(
                puppet_campaign.subprocess,
                "run",
                return_value=SimpleNamespace(returncode=0, stdout=process_table),
            ) as run,
            patch.object(
                puppet_campaign,
                "process_tree_identity",
                return_value=node,
            ),
            patch.object(
                puppet_campaign,
                "process_tree_alive",
                return_value=True,
            ),
        ):
            snapshot = puppet_campaign.target_process_snapshot("codex")
        self.assertEqual(snapshot["processes"], [identity])
        self.assertEqual(snapshot["ancestry_nodes"], [node])
        self.assertEqual(
            run.call_args.args[0],
            ["ps", "-axo", "pid=,comm="],
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
                instruction_manifest_sha256=STABLE_INSTRUCTION_MANIFEST_SHA256,
                authority_root=authority,
            )
            second_owner = lease_owner(state_root=second_state, **common)
            with self.assertRaisesRegex(ConflictError, "controller lease"):
                admit_session_lease(
                    session="duplicate-launch",
                    target="codex",
                    controller="tester",
                    owner=second_owner,
                    instruction_manifest_sha256=STABLE_INSTRUCTION_MANIFEST_SHA256,
                    authority_root=authority,
                )
            self.assertEqual(
                current_session_lease(authority, target="codex")["owner"],
                first_owner,
            )

    def test_different_targets_have_independent_leases_and_generations(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            authority = root / "authority"
            proof = root / "proof"
            codex_state = root / "codex-state"
            claude_state = root / "claude-state"
            for path in (authority, proof, codex_state, claude_state):
                path.mkdir(mode=0o700)
            codex_owner = lease_owner(
                activity="session",
                run_id="codex-lane",
                campaign_id="campaign-test",
                goal_fingerprint="a" * 64,
                proof_root=proof,
                state_root=codex_state,
            )
            claude_owner = lease_owner(
                activity="session",
                run_id="claude-lane",
                campaign_id="campaign-test",
                goal_fingerprint="a" * 64,
                proof_root=proof,
                state_root=claude_state,
            )
            codex = admit_session_lease(
                session="codex-lane",
                target="codex",
                controller="tester",
                owner=codex_owner,
                instruction_manifest_sha256=STABLE_INSTRUCTION_MANIFEST_SHA256,
                authority_root=authority,
            )
            claude = admit_session_lease(
                session="claude-lane",
                target="claude",
                controller="tester",
                owner=claude_owner,
                instruction_manifest_sha256=STABLE_INSTRUCTION_MANIFEST_SHA256,
                authority_root=authority,
            )
            self.assertEqual(codex["generation"], 1)
            self.assertEqual(claude["generation"], 1)
            self.assertEqual(current_session_lease(authority, target="codex"), codex)
            self.assertEqual(current_session_lease(authority, target="claude"), claude)
            with self.assertRaisesRegex(ConflictError, "controller lease"):
                admit_session_lease(
                    session="codex-collision",
                    target="codex",
                    controller="tester",
                    owner=codex_owner,
                    instruction_manifest_sha256=STABLE_INSTRUCTION_MANIFEST_SHA256,
                    authority_root=authority,
                )

            transition_session_lease(
                session="codex-lane",
                target="codex",
                controller="tester",
                owner=codex_owner,
                instruction_manifest_sha256=STABLE_INSTRUCTION_MANIFEST_SHA256,
                state="failed",
                process=None,
                authority_root=authority,
            )
            self.assertEqual(
                current_session_lease(authority, target="claude")["state"],
                "launching",
            )
            legacy_fence = current_session_lease(authority)
            self.assertEqual(legacy_fence["target"], "claude")
            self.assertEqual(legacy_fence["state"], "launching")
            self.assertTrue((authority / "session-lease-history.codex").exists())
            self.assertTrue((authority / "session-lease-history.claude").exists())

    def test_concurrent_different_target_admissions_serialize_only_the_fence(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            authority = root / "authority"
            proof = root / "proof"
            codex_state = root / "codex-state"
            claude_state = root / "claude-state"
            for path in (authority, proof, codex_state, claude_state):
                path.mkdir(mode=0o700)
            owners = {
                "codex": lease_owner(
                    activity="session",
                    run_id="concurrent-codex",
                    campaign_id="campaign-test",
                    goal_fingerprint="a" * 64,
                    proof_root=proof,
                    state_root=codex_state,
                ),
                "claude": lease_owner(
                    activity="session",
                    run_id="concurrent-claude",
                    campaign_id="campaign-test",
                    goal_fingerprint="a" * 64,
                    proof_root=proof,
                    state_root=claude_state,
                ),
            }
            results = {}
            errors = []

            def admit(target):
                try:
                    results[target] = admit_session_lease(
                        session="concurrent-%s" % target,
                        target=target,
                        controller="tester",
                        owner=owners[target],
                        instruction_manifest_sha256=STABLE_INSTRUCTION_MANIFEST_SHA256,
                        authority_root=authority,
                    )
                except BaseException as exc:
                    errors.append(exc)

            legacy_descriptor, _ = acquire_real_harness_lock(
                authority, reject_active_lease=False
            )
            threads = [
                threading.Thread(target=admit, args=(target,))
                for target in ("codex", "claude")
            ]
            try:
                for thread in threads:
                    thread.start()
                deadline = time.monotonic() + 0.5
                while time.monotonic() < deadline and not all(
                    (authority / ("real-harness.%s.lock" % target)).exists()
                    for target in ("codex", "claude")
                ):
                    time.sleep(0.005)
            finally:
                release_real_harness_lock(legacy_descriptor)
            for thread in threads:
                thread.join(timeout=2)
                self.assertFalse(thread.is_alive())
            self.assertEqual(errors, [])
            self.assertEqual(set(results), {"codex", "claude"})
            self.assertEqual(results["codex"]["generation"], 1)
            self.assertEqual(results["claude"]["generation"], 1)

    def test_partial_target_commit_replays_and_rotates_the_legacy_fence(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            authority = root / "authority"
            proof = root / "proof"
            codex_state = root / "codex-state"
            claude_state = root / "claude-state"
            for path in (authority, proof, codex_state, claude_state):
                path.mkdir(mode=0o700)
            codex_owner = lease_owner(
                activity="session",
                run_id="partial-codex",
                campaign_id="campaign-test",
                goal_fingerprint="a" * 64,
                proof_root=proof,
                state_root=codex_state,
            )
            claude_owner = lease_owner(
                activity="session",
                run_id="partial-claude",
                campaign_id="campaign-test",
                goal_fingerprint="a" * 64,
                proof_root=proof,
                state_root=claude_state,
            )
            admit_session_lease(
                session="partial-codex",
                target="codex",
                controller="tester",
                owner=codex_owner,
                instruction_manifest_sha256=STABLE_INSTRUCTION_MANIFEST_SHA256,
                authority_root=authority,
            )
            claude = admit_session_lease(
                session="partial-claude",
                target="claude",
                controller="tester",
                owner=claude_owner,
                instruction_manifest_sha256=STABLE_INSTRUCTION_MANIFEST_SHA256,
                authority_root=authority,
            )
            with patch.object(
                puppet_authority,
                "_sync_legacy_fence",
                side_effect=KeyboardInterrupt(),
            ):
                with self.assertRaises(KeyboardInterrupt):
                    transition_session_lease(
                        session="partial-codex",
                        target="codex",
                        controller="tester",
                        owner=codex_owner,
                        instruction_manifest_sha256=STABLE_INSTRUCTION_MANIFEST_SHA256,
                        state="failed",
                        process=None,
                        authority_root=authority,
                    )
            self.assertEqual(
                current_session_lease(authority, target="codex")["state"],
                "failed",
            )
            self.assertEqual(current_session_lease(authority)["target"], "codex")

            replayed = admit_session_lease(
                session="partial-claude",
                target="claude",
                controller="tester",
                owner=claude_owner,
                instruction_manifest_sha256=STABLE_INSTRUCTION_MANIFEST_SHA256,
                authority_root=authority,
            )
            self.assertEqual(replayed, claude)
            legacy = current_session_lease(authority)
            self.assertEqual(legacy["target"], "claude")
            self.assertEqual(legacy["state"], "launching")
            self.assertEqual(legacy["generation"], 2)

    def test_target_lock_descriptor_cannot_cross_harnesses(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            authority = root / "authority"
            proof = root / "proof"
            authority.mkdir(mode=0o700)
            proof.mkdir(mode=0o700)
            owner = lease_owner(
                activity="probe",
                run_id="descriptor-scope",
                campaign_id="campaign-test",
                goal_fingerprint="a" * 64,
                proof_root=proof,
                state_root=proof,
            )
            descriptor, _ = acquire_real_harness_lock(
                authority,
                target="codex",
                reject_active_lease=False,
            )
            try:
                with self.assertRaisesRegex(IdentityError, "descriptor changed"):
                    admit_session_lease(
                        session="wrong-target-lock",
                        target="claude",
                        controller="tester",
                        owner=owner,
                        instruction_manifest_sha256=STABLE_INSTRUCTION_MANIFEST_SHA256,
                        authority_root=authority,
                        _lock_descriptor=descriptor,
                    )
                with self.assertRaisesRegex(IdentityError, "descriptor changed"):
                    transition_session_lease(
                        session="wrong-target-lock",
                        target="claude",
                        controller="tester",
                        owner=owner,
                        instruction_manifest_sha256=STABLE_INSTRUCTION_MANIFEST_SHA256,
                        state="failed",
                        process=None,
                        authority_root=authority,
                        _lock_descriptor=descriptor,
                    )
            finally:
                release_real_harness_lock(descriptor)

    def test_legacy_controller_lock_sees_the_per_target_fence(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            authority = root / "authority"
            proof = root / "proof"
            authority.mkdir(mode=0o700)
            proof.mkdir(mode=0o700)
            owner = lease_owner(
                activity="session",
                run_id="new-controller-lane",
                campaign_id="campaign-test",
                goal_fingerprint="a" * 64,
                proof_root=proof,
                state_root=proof,
            )
            admit_session_lease(
                session="new-controller-lane",
                target="codex",
                controller="tester",
                owner=owner,
                instruction_manifest_sha256=STABLE_INSTRUCTION_MANIFEST_SHA256,
                authority_root=authority,
            )
            with self.assertRaisesRegex(ConflictError, "controller lease"):
                acquire_real_harness_lock(authority)

    def test_foreign_active_legacy_lease_blocks_per_target_admission(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            authority = root / "authority"
            proof = root / "proof"
            authority.mkdir(mode=0o700)
            proof.mkdir(mode=0o700)
            owner = lease_owner(
                activity="session",
                run_id="legacy-active",
                campaign_id="campaign-test",
                goal_fingerprint="a" * 64,
                proof_root=proof,
                state_root=proof,
            )
            legacy = {
                "schema_version": 1,
                "authority_id": "puppet-local-controller-v1",
                "generation": 1,
                "session": "legacy-active",
                "target": "codex",
                "controller": "old-controller",
                "owner": owner,
                "state": "launching",
                "created_at": "2026-07-22T05:00:00Z",
                "updated_at": "2026-07-22T05:00:00Z",
                "process": None,
            }
            Journal(authority / "session-lease-history").append(
                request_id="lease-1-launching",
                event={"kind": "session_lease", "lease": legacy},
            )
            (authority / "current-session-lease.json").write_text(
                json.dumps(legacy) + "\n", encoding="utf-8"
            )
            next_owner = lease_owner(
                activity="session",
                run_id="claude-after-legacy",
                campaign_id="campaign-test",
                goal_fingerprint="a" * 64,
                proof_root=proof,
                state_root=proof,
            )
            with self.assertRaisesRegex(ConflictError, "legacy real-harness"):
                admit_session_lease(
                    session="claude-after-legacy",
                    target="claude",
                    controller="tester",
                    owner=next_owner,
                    instruction_manifest_sha256=STABLE_INSTRUCTION_MANIFEST_SHA256,
                    authority_root=authority,
                )
            self.assertIsNone(current_session_lease(authority, target="claude"))

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
                instruction_manifest_sha256=STABLE_INSTRUCTION_MANIFEST_SHA256,
                authority_root=authority,
            )
            projection = authority / "current-session-lease.codex.json"
            projection.unlink()
            self.assertEqual(
                current_session_lease(authority, target="codex"), launching
            )
            self.assertEqual(json.loads(projection.read_text()), launching)

            process = {
                "identity_version": 2,
                "pid": 4242,
                "start": "stable",
                "kernel_birth_id": "test:4242",
                "command": "codex",
                "executable_path": "/opt/bin/codex",
                "device": 1,
                "inode": 2,
            }
            history = Journal(authority / "session-lease-history.codex")

            def append_without_projection(state: str, number: int):
                current = current_session_lease(authority, target="codex")
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
                self.assertEqual(
                    current_session_lease(authority, target="codex"), committed
                )
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
                instruction_manifest_sha256=STABLE_INSTRUCTION_MANIFEST_SHA256,
                authority_root=authority,
            )
            failed = dict(
                second,
                state="failed",
                updated_at="2026-07-22T05:00:04Z",
            )
            claude_history = Journal(authority / "session-lease-history.claude")
            claude_history.append(
                request_id="lease-%d-failed" % failed["generation"],
                event={"kind": "session_lease", "lease": failed},
            )
            self.assertEqual(current_session_lease(authority, target="claude"), failed)

    def test_projection_recovery_proves_latest_ledger_row_before_rewrite(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            authority = root / "authority"
            authority.mkdir(mode=0o700)
            proof = root / "proof"
            proof.mkdir()
            owner = lease_owner(
                activity="probe",
                run_id="wrong-ledger-row",
                campaign_id="campaign-test",
                goal_fingerprint="a" * 64,
                proof_root=proof,
                state_root=proof,
            )
            launching = admit_session_lease(
                session="wrong-ledger-row",
                target="codex",
                controller="tester",
                owner=owner,
                instruction_manifest_sha256=STABLE_INSTRUCTION_MANIFEST_SHA256,
                authority_root=authority,
            )
            process = {
                "identity_version": 2,
                "pid": 4242,
                "start": "stable",
                "kernel_birth_id": "test:4242",
                "command": "codex",
                "executable_path": "/opt/bin/codex",
                "device": 1,
                "inode": 2,
            }
            active = dict(
                launching,
                state="active",
                process=process,
                updated_at="2026-07-22T05:00:01Z",
            )
            Journal(authority / "session-lease-history.codex").append(
                request_id="wrong-request-id",
                event={"kind": "session_lease", "lease": active},
            )
            projection = authority / "current-session-lease.codex.json"
            with self.assertRaisesRegex(IdentityError, "authority ledger"):
                current_session_lease(authority, target="codex")
            self.assertEqual(json.loads(projection.read_text()), launching)

    def test_missing_projection_rejects_noncanonical_latest_ledger_row(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            authority = root / "authority"
            authority.mkdir(mode=0o700)
            proof = root / "proof"
            proof.mkdir()
            owner = lease_owner(
                activity="probe",
                run_id="missing-projection-wrong-row",
                campaign_id="campaign-test",
                goal_fingerprint="a" * 64,
                proof_root=proof,
                state_root=proof,
            )
            launching = admit_session_lease(
                session="missing-projection-wrong-row",
                target="codex",
                controller="tester",
                owner=owner,
                instruction_manifest_sha256=STABLE_INSTRUCTION_MANIFEST_SHA256,
                authority_root=authority,
            )
            projection = authority / "current-session-lease.codex.json"
            projection.unlink()
            Journal(authority / "session-lease-history.codex").append(
                request_id="wrong-request-id",
                event={"kind": "session_lease", "lease": launching},
            )
            with self.assertRaisesRegex(IdentityError, "authority ledger"):
                current_session_lease(authority, target="codex")
            self.assertFalse(projection.exists())

    def test_lease_schema_rejects_boolean_and_float_versions(self):
        for version in (True, 2.0):
            with (
                self.subTest(version=version),
                tempfile.TemporaryDirectory() as temporary,
            ):
                root = Path(temporary).resolve()
                authority = root / "authority"
                authority.mkdir(mode=0o700)
                proof = root / "proof"
                proof.mkdir()
                owner = lease_owner(
                    activity="probe",
                    run_id="invalid-schema",
                    campaign_id="campaign-test",
                    goal_fingerprint="a" * 64,
                    proof_root=proof,
                    state_root=proof,
                )
                lease = {
                    "schema_version": version,
                    "authority_id": "puppet-local-controller-v1",
                    "generation": 1,
                    "session": "invalid-schema",
                    "target": "codex",
                    "controller": "tester",
                    "owner": owner,
                    "instruction_manifest_sha256": (STABLE_INSTRUCTION_MANIFEST_SHA256),
                    "state": "launching",
                    "created_at": "2026-07-22T05:00:00Z",
                    "updated_at": "2026-07-22T05:00:00Z",
                    "process": None,
                }
                Journal(authority / "session-lease-history.codex").append(
                    request_id="lease-1-launching",
                    event={"kind": "session_lease", "lease": lease},
                )
                with self.assertRaisesRegex(ValidationError, "schema"):
                    current_session_lease(authority, target="codex")

    def test_legacy_halted_lease_is_idempotent_and_can_be_superseded(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            authority = root / "authority"
            proof = root / "proof"
            authority.mkdir(mode=0o700)
            proof.mkdir()
            owner = lease_owner(
                activity="probe",
                run_id="legacy-halted",
                campaign_id="campaign-test",
                goal_fingerprint="a" * 64,
                proof_root=proof,
                state_root=proof,
            )
            legacy_process = {"pid": 4242, "start": "legacy"}
            legacy = {
                "schema_version": 1,
                "authority_id": "puppet-local-controller-v1",
                "generation": 1,
                "session": "legacy-halted",
                "target": "agy",
                "controller": "tester",
                "owner": owner,
                "state": "halted",
                "created_at": "2026-07-22T05:00:00Z",
                "updated_at": "2026-07-22T05:00:01Z",
                "process": legacy_process,
            }
            Journal(authority / "session-lease-history").append(
                request_id="lease-1-halted",
                event={"kind": "session_lease", "lease": legacy},
            )
            (authority / "current-session-lease.json").write_text(
                json.dumps(legacy) + "\n", encoding="utf-8"
            )

            self.assertEqual(current_session_lease(authority), legacy)
            with self.assertRaisesRegex(
                IdentityError, "controller session lease identity mismatch"
            ):
                transition_session_lease(
                    session="legacy-halted",
                    target="agy",
                    controller="tester",
                    owner=owner,
                    instruction_manifest_sha256=STABLE_INSTRUCTION_MANIFEST_SHA256,
                    state="halted",
                    process=legacy_process,
                    authority_root=authority,
                )

            next_owner = lease_owner(
                activity="probe",
                run_id="v2-next",
                campaign_id="campaign-test",
                goal_fingerprint="a" * 64,
                proof_root=proof,
                state_root=proof,
            )
            next_lease = admit_session_lease(
                session="v2-next",
                target="agy",
                controller="tester",
                owner=next_owner,
                instruction_manifest_sha256=STABLE_INSTRUCTION_MANIFEST_SHA256,
                authority_root=authority,
            )
            self.assertEqual(next_lease["generation"], 1)
            self.assertEqual(next_lease["state"], "launching")
            self.assertEqual(current_session_lease(authority)["generation"], 2)
            v2_process = {
                "identity_version": 2,
                "pid": 5252,
                "start": "stable",
                "kernel_birth_id": "test:5252",
                "command": "agy",
                "executable_path": "/opt/bin/agy",
                "device": 1,
                "inode": 2,
            }
            active = transition_session_lease(
                session="v2-next",
                target="agy",
                controller="tester",
                owner=next_owner,
                instruction_manifest_sha256=STABLE_INSTRUCTION_MANIFEST_SHA256,
                state="active",
                process=v2_process,
                authority_root=authority,
            )
            self.assertEqual(active["process"], v2_process)

    def test_legacy_failed_lease_can_be_superseded(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            authority = root / "authority"
            proof = root / "proof"
            authority.mkdir(mode=0o700)
            proof.mkdir()
            owner = lease_owner(
                activity="probe",
                run_id="legacy-failed",
                campaign_id="campaign-test",
                goal_fingerprint="a" * 64,
                proof_root=proof,
                state_root=proof,
            )
            legacy = {
                "schema_version": 1,
                "authority_id": "puppet-local-controller-v1",
                "generation": 1,
                "session": "legacy-failed",
                "target": "agy",
                "controller": "tester",
                "owner": owner,
                "state": "failed",
                "created_at": "2026-07-22T05:00:00Z",
                "updated_at": "2026-07-22T05:00:01Z",
                "process": {"pid": 4242, "start": "legacy"},
            }
            Journal(authority / "session-lease-history").append(
                request_id="lease-1-failed",
                event={"kind": "session_lease", "lease": legacy},
            )
            (authority / "current-session-lease.json").write_text(
                json.dumps(legacy) + "\n", encoding="utf-8"
            )
            self.assertEqual(current_session_lease(authority), legacy)

            next_owner = lease_owner(
                activity="probe",
                run_id="after-legacy-failure",
                campaign_id="campaign-test",
                goal_fingerprint="a" * 64,
                proof_root=proof,
                state_root=proof,
            )
            admitted = admit_session_lease(
                session="after-legacy-failure",
                target="agy",
                controller="tester",
                owner=next_owner,
                instruction_manifest_sha256=STABLE_INSTRUCTION_MANIFEST_SHA256,
                authority_root=authority,
            )
            self.assertEqual(admitted["generation"], 1)
            self.assertEqual(admitted["state"], "launching")
            self.assertEqual(current_session_lease(authority)["generation"], 2)

    def test_legacy_live_projection_recovers_an_appended_terminal_successor(self):
        for live_state, terminal_state in (
            ("active", "failed"),
            ("halting", "halted"),
        ):
            with (
                self.subTest(live_state=live_state),
                tempfile.TemporaryDirectory() as temporary,
            ):
                root = Path(temporary).resolve()
                authority = root / "authority"
                proof = root / "proof"
                authority.mkdir(mode=0o700)
                proof.mkdir()
                owner = lease_owner(
                    activity="probe",
                    run_id="legacy-projection",
                    campaign_id="campaign-test",
                    goal_fingerprint="a" * 64,
                    proof_root=proof,
                    state_root=proof,
                )
                launching = admit_session_lease(
                    session="legacy-projection",
                    target="agy",
                    controller="tester",
                    owner=owner,
                    instruction_manifest_sha256=STABLE_INSTRUCTION_MANIFEST_SHA256,
                    authority_root=authority,
                )
                legacy_process = {"pid": 4242, "start": "legacy"}
                live = dict(
                    launching,
                    state=live_state,
                    updated_at="2026-07-22T05:00:01Z",
                    process=legacy_process,
                )
                terminal = dict(
                    live,
                    state=terminal_state,
                    updated_at="2026-07-22T05:00:02Z",
                )
                history = Journal(authority / "session-lease-history")
                history.append(
                    request_id="lease-1-%s" % live_state,
                    event={"kind": "session_lease", "lease": live},
                )
                (authority / "current-session-lease.json").write_text(
                    json.dumps(live) + "\n", encoding="utf-8"
                )
                history.append(
                    request_id="lease-1-%s" % terminal_state,
                    event={"kind": "session_lease", "lease": terminal},
                )

                self.assertEqual(current_session_lease(authority), terminal)
                self.assertEqual(
                    json.loads(
                        (authority / "current-session-lease.json").read_text(
                            encoding="utf-8"
                        )
                    ),
                    terminal,
                )

    def test_active_lease_rejects_each_malformed_v2_identity_field(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            authority = root / "authority"
            proof = root / "proof"
            authority.mkdir(mode=0o700)
            proof.mkdir()
            owner = lease_owner(
                activity="probe",
                run_id="v2-shape",
                campaign_id="campaign-test",
                goal_fingerprint="a" * 64,
                proof_root=proof,
                state_root=proof,
            )
            admit_session_lease(
                session="v2-shape",
                target="codex",
                controller="tester",
                owner=owner,
                instruction_manifest_sha256=STABLE_INSTRUCTION_MANIFEST_SHA256,
                authority_root=authority,
            )
            valid = {
                "identity_version": 2,
                "pid": 4242,
                "start": "stable",
                "kernel_birth_id": "test:4242",
                "command": "codex",
                "executable_path": "/opt/bin/codex",
                "device": 1,
                "inode": 2,
            }
            invalid_values = {
                "identity_version": 1,
                "pid": True,
                "start": [],
                "kernel_birth_id": "",
                "command": {},
                "executable_path": "relative/codex",
                "device": "1",
                "inode": -1,
            }
            for name, invalid in invalid_values.items():
                with (
                    self.subTest(name=name),
                    self.assertRaisesRegex(ValidationError, "v2 process identity"),
                ):
                    transition_session_lease(
                        session="v2-shape",
                        target="codex",
                        controller="tester",
                        owner=owner,
                        instruction_manifest_sha256=STABLE_INSTRUCTION_MANIFEST_SHA256,
                        state="active",
                        process=dict(valid, **{name: invalid}),
                        authority_root=authority,
                    )
            self.assertEqual(
                current_session_lease(authority, target="codex")["state"],
                "launching",
            )

    def test_different_instruction_manifest_hash_blocks_same_session_idempotence(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            authority = root / "authority"
            proof = root / "proof"
            authority.mkdir(mode=0o700)
            proof.mkdir()
            owner = lease_owner(
                activity="probe",
                run_id="manifest-drift",
                campaign_id="campaign-test",
                goal_fingerprint="a" * 64,
                proof_root=proof,
                state_root=proof,
            )
            first = admit_session_lease(
                session="manifest-drift",
                target="codex",
                controller="tester",
                owner=owner,
                instruction_manifest_sha256=STABLE_INSTRUCTION_MANIFEST_SHA256,
                authority_root=authority,
            )
            self.assertEqual(
                first["instruction_manifest_sha256"],
                STABLE_INSTRUCTION_MANIFEST_SHA256,
            )
            self.assertEqual(first, current_session_lease(authority, target="codex"))

            with self.assertRaisesRegex(
                ConflictError, "another real-harness session owns the controller lease"
            ):
                admit_session_lease(
                    session="manifest-drift",
                    target="codex",
                    controller="tester",
                    owner=owner,
                    instruction_manifest_sha256=ALTERNATE_INSTRUCTION_MANIFEST_SHA256,
                    authority_root=authority,
                )

            requested = require_session_lease(
                session="manifest-drift",
                target="codex",
                controller="tester",
                owner=owner,
                instruction_manifest_sha256=STABLE_INSTRUCTION_MANIFEST_SHA256,
                states={"launching"},
                authority_root=authority,
            )
            self.assertEqual(requested, first)
            with self.assertRaisesRegex(
                IdentityError, "controller session lease identity mismatch"
            ):
                require_session_lease(
                    session="manifest-drift",
                    target="codex",
                    controller="tester",
                    owner=owner,
                    instruction_manifest_sha256=ALTERNATE_INSTRUCTION_MANIFEST_SHA256,
                    states={"launching"},
                    authority_root=authority,
                )

            process = {
                "identity_version": 2,
                "pid": 4242,
                "start": "stable",
                "kernel_birth_id": "test:4242",
                "command": "codex",
                "executable_path": "/opt/bin/codex",
                "device": 1,
                "inode": 2,
            }
            active = transition_session_lease(
                session="manifest-drift",
                target="codex",
                controller="tester",
                owner=owner,
                instruction_manifest_sha256=STABLE_INSTRUCTION_MANIFEST_SHA256,
                state="active",
                process=process,
                authority_root=authority,
            )
            self.assertEqual(active["state"], "active")
            self.assertEqual(active["process"], process)

            with self.assertRaisesRegex(
                IdentityError, "controller session lease identity mismatch"
            ):
                transition_session_lease(
                    session="manifest-drift",
                    target="codex",
                    controller="tester",
                    owner=owner,
                    instruction_manifest_sha256=ALTERNATE_INSTRUCTION_MANIFEST_SHA256,
                    state="active",
                    process=process,
                    authority_root=authority,
                )

    def test_process_identity_binds_full_executable_file_identity(self):
        identity = process_birth_identity(os.getpid())
        self.assertEqual(
            set(identity),
            {
                "identity_version",
                "pid",
                "start",
                "kernel_birth_id",
                "command",
                "executable_path",
                "device",
                "inode",
            },
        )
        self.assertTrue(Path(identity["executable_path"]).is_absolute())
        self.assertTrue(process_alive(identity))
        self.assertFalse(process_alive(dict(identity, inode=identity["inode"] + 1)))

    def test_darwin_kernel_sampler_binds_microsecond_birth_and_parent(self):
        class FakeProcPidInfo:
            argtypes = None
            restype = None

            def __call__(self, pid, flavor, arg, buffer, size):
                self.asserted = (pid, flavor, arg)
                info = puppet_registry.ctypes.cast(
                    buffer,
                    puppet_registry.ctypes.POINTER(puppet_registry._DarwinProcBSDInfo),
                ).contents
                info.pbi_pid = pid
                info.pbi_ppid = 42
                info.pbi_start_tvsec = 1_784_700_000
                info.pbi_start_tvusec = 1234
                return size

        proc_pidinfo = FakeProcPidInfo()
        library = SimpleNamespace(proc_pidinfo=proc_pidinfo)
        with patch.object(puppet_registry.ctypes, "CDLL", return_value=library):
            record = puppet_registry._darwin_kernel_process_record(4242)
        self.assertEqual(proc_pidinfo.asserted, (4242, 3, 0))
        self.assertEqual(
            record,
            {
                "pid": 4242,
                "parent_pid": 42,
                "kernel_birth_id": "darwin:1784700000:001234",
            },
        )

    def test_linux_kernel_sampler_parses_parent_and_start_ticks(self):
        fields = ["S", "42", *("0" for _ in range(17)), "987654321"]
        stat_bytes = ("4242 (worker name) " + " ".join(fields) + "\n").encode()

        def fake_open(_path, _mode):
            return io.BytesIO(stat_bytes)

        with (
            patch.object(puppet_registry.Path, "open", new=fake_open),
            patch.object(
                puppet_registry,
                "_linux_boot_id",
                return_value="12345678-1234-1234-1234-123456789abc",
            ),
        ):
            record = puppet_registry._linux_kernel_process_record(4242)
        self.assertEqual(
            record,
            {
                "pid": 4242,
                "parent_pid": 42,
                "kernel_birth_id": (
                    "linux:12345678-1234-1234-1234-123456789abc:987654321"
                ),
            },
        )

    def test_process_tree_binding_rejects_kernel_identity_drift(self):
        before = {
            "pid": 4242,
            "parent_pid": 42,
            "kernel_birth_id": "test:before",
        }
        after = dict(before, kernel_birth_id="test:after")
        executable = Path("/bin/cat").resolve(strict=True)
        with (
            patch.object(
                puppet_registry,
                "_kernel_process_record",
                side_effect=[before, after],
            ),
            patch.object(
                puppet_registry.subprocess,
                "run",
                return_value=SimpleNamespace(
                    returncode=0, stdout="Wed Jul 22 02:05:39 2026 cat\n"
                ),
            ),
            patch.object(
                puppet_registry, "_process_executable_path", return_value=executable
            ),
        ):
            with self.assertRaisesRegex(IdentityError, "kernel binding"):
                puppet_registry.process_tree_identity(4242)

    def test_process_tree_binding_rejects_executable_drift(self):
        kernel = {
            "pid": 4242,
            "parent_pid": 42,
            "kernel_birth_id": "test:stable",
        }
        with (
            patch.object(
                puppet_registry,
                "_kernel_process_record",
                return_value=kernel,
            ),
            patch.object(
                puppet_registry.subprocess,
                "run",
                return_value=SimpleNamespace(
                    returncode=0, stdout="Wed Jul 22 02:05:39 2026 cat\n"
                ),
            ),
            patch.object(
                puppet_registry,
                "_process_executable_path",
                side_effect=[
                    Path("/bin/cat").resolve(strict=True),
                    Path("/bin/echo").resolve(strict=True),
                ],
            ),
        ):
            with self.assertRaisesRegex(IdentityError, "executable binding"):
                puppet_registry.process_tree_identity(4242)

    def test_process_birth_identity_tolerates_reparent_but_tree_identity_does_not(self):
        before = {
            "pid": 4242,
            "parent_pid": 42,
            "kernel_birth_id": "test:stable",
        }
        after = dict(before, parent_pid=1)
        display = SimpleNamespace(returncode=0, stdout="Wed Jul 22 02:05:39 2026 cat\n")
        executable = Path("/bin/cat").resolve(strict=True)
        with (
            patch.object(
                puppet_registry,
                "_kernel_process_record",
                side_effect=[before, after],
            ),
            patch.object(puppet_registry.subprocess, "run", return_value=display),
            patch.object(
                puppet_registry, "_process_executable_path", return_value=executable
            ),
        ):
            process = process_birth_identity(4242)
        self.assertEqual(process["kernel_birth_id"], "test:stable")

        with (
            patch.object(
                puppet_registry,
                "_kernel_process_record",
                side_effect=[before, after],
            ),
            patch.object(puppet_registry.subprocess, "run", return_value=display),
            patch.object(
                puppet_registry, "_process_executable_path", return_value=executable
            ),
        ):
            with self.assertRaisesRegex(IdentityError, "parent changed"):
                puppet_registry.process_tree_identity(4242)

    def test_exact_sigint_does_not_signal_a_shared_process_group(self):
        parent = subprocess.Popen(
            [
                sys.executable,
                "-c",
                (
                    "import subprocess,sys,time;"
                    "child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)']);"
                    "print(child.pid,flush=True);time.sleep(30)"
                ),
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        child_pid = None
        child_identity = None
        try:
            child_pid = int(parent.stdout.readline().strip())
            identity_deadline = time.monotonic() + 5
            while time.monotonic() < identity_deadline:
                try:
                    candidate = process_birth_identity(child_pid)
                except IdentityError:
                    time.sleep(0.01)
                    continue
                if process_alive(candidate):
                    child_identity = candidate
                    break
                time.sleep(0.01)
            self.assertIsNotNone(child_identity)
            parent_identity = process_birth_identity(parent.pid)
            self.assertEqual(os.getpgid(parent.pid), os.getpgid(child_pid))

            send_exact_sigint(parent_identity)
            parent.wait(timeout=5)
            survival_deadline = time.monotonic() + 5
            while (
                not process_alive(child_identity)
                and time.monotonic() < survival_deadline
            ):
                time.sleep(0.01)
            self.assertTrue(process_alive(child_identity))
        finally:
            if parent.stdout is not None:
                parent.stdout.close()
            if parent.poll() is None:
                parent.terminate()
                parent.wait(timeout=5)
            if child_identity is not None:
                cleanup_identity_deadline = time.monotonic() + 2
                while (
                    not process_alive(child_identity)
                    and time.monotonic() < cleanup_identity_deadline
                ):
                    time.sleep(0.01)
                if process_alive(child_identity):
                    send_exact_sigint(child_identity)
                    deadline = time.monotonic() + 5
                    while process_alive(child_identity) and time.monotonic() < deadline:
                        time.sleep(0.01)

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
            compiled = compile_instruction_wrapper(
                target="agy",
                task="Run the bounded authority fixture.",
                contract_identity={
                    "fingerprint": "a" * 64,
                    "controller": "codex",
                    "target": "agy",
                    "task_profile": "source",
                },
                workspace_identity={
                    "repo_fingerprint": "1" * 64,
                    "branch": "codex/example",
                },
                run_identity={
                    "session": "session-1",
                    "run_id": "run-1",
                    "nonce": "nonce-1",
                },
                model_binding="default",
                effort_binding="default",
            )
            instruction_path = proof / "effective-instructions.json"
            atomic_write_json(instruction_path, compiled.manifest)
            state_root = root / "state"
            registry = SessionRegistry(state_root)
            tmux_socket_path = canonical_tmux_socket_path(registry.root, "session-1")
            tmux_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            tmux_socket.bind(str(tmux_socket_path))
            tmux_socket_path.chmod(0o600)
            self.addCleanup(tmux_socket.close)
            self.addCleanup(lambda: tmux_socket_path.unlink(missing_ok=True))
            tmux_server_identity = process_birth_identity(os.getpid())
            tmux_executable = Path(tmux_server_identity["executable_path"]).resolve(
                strict=True
            )
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
                    "identity_version": 2,
                    "pid": os.getpid(),
                    "start": "x",
                    "kernel_birth_id": "test:%d" % os.getpid(),
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
                "instructions": {
                    "manifest_path": str(instruction_path),
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
            for name, invalid in {
                "identity_version": 1,
                "kernel_birth_id": "",
            }.items():
                with (
                    self.subTest(name=name),
                    self.assertRaisesRegex(
                        ValidationError, "registered process identity"
                    ),
                ):
                    registry.validate(
                        dict(record, process=dict(record["process"], **{name: invalid}))
                    )
            registry.create(record)
            with self.assertRaises(ConflictError):
                registry.create(record)
            registry.verify_supervisor(record)
            executable.write_text("print('two')\n", encoding="utf-8")
            with self.assertRaisesRegex(Exception, "fingerprint"):
                registry.verify_supervisor(record)


if __name__ == "__main__":
    unittest.main()
