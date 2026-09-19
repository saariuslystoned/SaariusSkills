from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "puppet" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from puppet_lib.agy_print import (
    SESSION_STORE_SCHEMA,
    AgyPrintController,
    AgyPrintRuntime,
    fixture_observation,
    persist_agy_print_session,
)
from puppet_lib.conformance import create_fixture, tree_fingerprint
from puppet_lib.contracts import MANDATORY_HARD_GATES
from puppet_lib.errors import IdentityError, UnsupportedError, ValidationError
from puppet_lib.handoffs import HANDOFF_SCHEMA_VERSION, PROTOCOL_FINGERPRINT
from puppet_lib.session import (
    accept_checkpoint,
    halt as session_halt,
    import_checkpoint,
    review_checkpoint,
    send_message,
)
from puppet_lib.registry import ProcessVanished


SESSION = "agy-print-session"
PROCESS = {"pid": 4242, "kernel_birth_id": "darwin:100:00004242"}
EXECUTABLE_FINGERPRINT = "11" * 32
EXECUTION_FINGERPRINT = "22" * 32
ADAPTER_FINGERPRINT = "33" * 32


def write_json(path: Path, value) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")
    return path


class AgyPrintPublicCheckpointTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.proof = self.root / "proof"
        self.state = self.root / "state"
        self.proof.mkdir(mode=0o700)
        self.state.mkdir(mode=0o700)
        self.fixture_contract = create_fixture(
            self.root / "fixture",
            run_id="agy-run",
            session=SESSION,
            target="agy",
        )
        self.repo = self.root / "fixture"
        self.fingerprints = {
            "executable_fingerprint": EXECUTABLE_FINGERPRINT,
            "execution_fingerprint": EXECUTION_FINGERPRINT,
            "adapter_fingerprint": ADAPTER_FINGERPRINT,
            "protocol_fingerprint": PROTOCOL_FINGERPRINT,
        }
        persist_agy_print_session(self.state, self._session_record())
        self.patches = mock.patch.multiple(
            "puppet_lib.session",
            process_birth_identity=mock.DEFAULT,
            require_session_lease=mock.DEFAULT,
        )
        self.identity_patch = mock.patch(
            "puppet_lib.agy_print._revalidate_live_identity",
            return_value=dict(PROCESS),
        )
        self.gone_patch = mock.patch(
            "puppet_lib.agy_print._pid_gone",
            return_value=False,
        )
        started = self.patches.start()
        started["process_birth_identity"].return_value = dict(PROCESS)
        started["require_session_lease"].return_value = {"state": "active"}
        self.identity_patch.start()
        self.gone_patch.start()
        self.addCleanup(self.temporary.cleanup)
        self.addCleanup(self.patches.stop)
        self.addCleanup(self.identity_patch.stop)
        self.addCleanup(self.gone_patch.stop)

    def _session_record(self, **overrides):
        observation = fixture_observation(
            session=SESSION,
            workspace_path=str(self.repo),
            record_state="ACTIVE",
        )
        record = {
            "schema": SESSION_STORE_SCHEMA,
            "transport": "agy-print",
            "session": SESSION,
            "conversation_id": "conv-agy-print-1",
            "contract": {
                "schema_version": 1,
                "objective": "Bounded AGY public checkpoint admission",
                "campaign_authorization_id": "campaign-test",
                "controller": "tester",
                "target": "agy",
                "task_profile": "conformance",
                "harness_trust": "unrestricted_required",
                "mutation_owner": "none",
                "repo": str(self.repo),
                "branch": "codex/agy-checkpoint",
                "allowed_modes": ["read", "test"],
                "terminal_criteria": [
                    {"id": "conformance_green", "evidence": "validated_handoff"}
                ],
                "hard_gates": sorted(MANDATORY_HARD_GATES),
            },
            "proof_root": str(self.proof),
            "lease_owner": {
                "activity": "session",
                "run_id": "agy-run",
                "campaign_id": "campaign-test",
                "goal_fingerprint": "aa" * 32,
                "proof_root": str(self.proof),
                "state_root": str(self.state),
            },
            "instruction_manifest_sha256": "bb" * 32,
            "observation": observation,
            "protocol": {
                "kind": "conformance",
                "run_id": self.fixture_contract["run_id"],
                "nonce": self.fixture_contract["nonce"],
                "phase": "awaiting_ready",
                "fixture_fingerprint": tree_fingerprint(self.repo),
                "ready_checkpoint_id": None,
                "ready_artifact_sha256": None,
                "message_id": None,
                "followup_checkpoint_id": None,
            },
            "adapter": dict(self.fingerprints),
            "send_requests": {},
            "held": True,
            "process_backed": True,
            "live_agy_claimed": False,
        }
        record.update(overrides)
        return record

    def _handoff(self, name: str, **overrides):
        payload = {
            "schema_version": HANDOFF_SCHEMA_VERSION,
            "checkpoint_kind": "conformance",
            "session": SESSION,
            "run_id": self.fixture_contract["run_id"],
            "nonce": self.fixture_contract["nonce"],
            "phase": "ready",
            "sequence": 0,
            "timestamp": "2026-09-19T03:01:00Z",
            "claims": [],
            "evidence_refs": [],
            "decisions_requested": [],
            "limitations": [],
            **self.fingerprints,
        }
        payload.update(overrides)
        return write_json(self.repo / "handoffs" / name, payload)

    def _import(self, path: Path):
        return import_checkpoint(
            state_root=self.state, session=SESSION, handoff_path=path
        )

    def _authorize_followup(self, request_id: str = "message-1"):
        AgyPrintController(self.state)._persist_send_result(
            session=SESSION,
            request_id=request_id,
            message_sha256="cc" * 32,
            result={"ok": True, "request_id": request_id},
        )

    def _bind_executable(self):
        current = AgyPrintController(self.state).require_session(SESSION)
        current["executable"] = sys.executable
        persist_agy_print_session(self.state, current)

    def _public_halt(self):
        with (
            mock.patch(
                "puppet_lib.session.require_session_lease",
                return_value={"state": "active", "process": dict(PROCESS)},
            ),
            mock.patch("puppet_lib.session.transition_session_lease"),
            mock.patch("puppet_lib.agy_print._pid_gone", return_value=True),
        ):
            result = session_halt(state_root=self.state, session=SESSION)
        self.assertEqual(result["state"], "HALTED")
        return result

    def _resumed_runtime(self, stored):
        observation = copy.deepcopy(stored["observation"])
        observation.update(
            record_state="ACTIVE",
            terminal_result={"state": "completed", "exit_code": 0},
            halt=None,
        )
        return SimpleNamespace(
            observation=observation,
            conversation_id=stored.get("conversation_id") or "conv-agy-print-1",
            require_observation=lambda: observation,
        )

    def _public_resume_send(self, message, request_id):
        stored = AgyPrintController(self.state).require_session(SESSION)
        runtime = self._resumed_runtime(stored)
        start_kwargs = {}

        def start(**kwargs):
            start_kwargs.update(kwargs)
            return runtime

        with (
            mock.patch(
                "puppet_lib.session.require_session_lease",
                return_value={"state": "halted", "process": dict(PROCESS)},
            ),
            mock.patch("puppet_lib.session._validate_agy_resume_identity"),
            mock.patch("puppet_lib.session.admit_session_lease"),
            mock.patch("puppet_lib.session.transition_session_lease"),
            mock.patch(
                "puppet_lib.agy_print.agy_print_runtime_available",
                return_value=True,
            ),
            mock.patch.object(AgyPrintRuntime, "start", side_effect=start),
        ):
            result = send_message(
                state_root=self.state,
                session=SESSION,
                message=message,
                request_id=request_id,
            )
        return result, start_kwargs

    def _git_output(self, repo, *arguments):
        return subprocess.check_output(
            ["git", "-C", str(repo), *arguments],
            text=True,
        ).strip()

    def _git_commit(self, repo, message):
        subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
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
        return {
            "head": self._git_output(repo, "rev-parse", "HEAD"),
            "tree": self._git_output(repo, "rev-parse", "HEAD^{tree}"),
            "branch": self._git_output(repo, "branch", "--show-current"),
        }

    def _init_source_repo(self):
        repo = self.root / "source-repo"
        repo.mkdir()
        subprocess.run(
            ["git", "init", "-q", "-b", "codex/agy-source", str(repo)],
            check=True,
        )
        (repo / "feature.txt").write_text("bounded source\n", encoding="utf-8")
        return repo, self._git_commit(repo, "source")

    def _source_session_record(self, repo, identity):
        record = self._session_record()
        record["contract"].update(
            {
                "objective": "Bounded AGY public source continuation",
                "task_profile": "implementation",
                "mutation_owner": "target",
                "repo": str(repo),
                "branch": identity["branch"],
                "allowed_modes": ["read", "test", "mutate", "local_commit"],
                "run_id": "source-run",
                "nonce": "source-nonce",
                "proof_path_prefixes": ["proof/"],
                "terminal_criteria": [
                    {"id": "source_green", "evidence": "validated_handoff"}
                ],
            }
        )
        record["observation"] = fixture_observation(
            session=SESSION,
            workspace_path=str(repo),
            branch=identity["branch"],
            head=identity["head"],
            tree=identity["tree"],
            record_state="ACTIVE",
        )
        record["protocol"] = {
            "kind": "source",
            "run_id": "source-run",
            "nonce": "source-nonce",
            "phase": "awaiting_source",
            "source_commit": None,
            "proof_commit": None,
        }
        return record

    def _source_handoff(self, name, commit, summary):
        return write_json(
            self.proof / name,
            {
                "schema_version": HANDOFF_SCHEMA_VERSION,
                "checkpoint_kind": "source",
                "session": SESSION,
                "run_id": "source-run",
                "nonce": "source-nonce",
                "candidate_commit": commit,
                "timestamp": "2026-09-19T03:10:00Z",
                "summary": summary,
                "claims": [],
                "evidence_refs": [],
                "decisions_requested": [],
                "limitations": [],
                "suggested_next_assignment": "Controller review",
                **self.fingerprints,
            },
        )

    def test_public_import_rejects_first_followup(self):
        followup = self._handoff(
            "followup.json",
            phase="followup",
            sequence=1,
            message_id="message-1",
            prior_checkpoint_sha256="ff" * 32,
            timestamp="2026-09-19T03:02:00Z",
        )
        with self.assertRaisesRegex(
            ValidationError, "handoff identity mismatch: phase"
        ):
            self._import(followup)

    def test_public_import_rejects_runtime_protocol_fingerprint_mismatch(self):
        ready = self._handoff(
            "ready.json",
            protocol_fingerprint="44" * 32,
        )
        with self.assertRaisesRegex(
            ValidationError, "handoff identity mismatch: protocol_fingerprint"
        ):
            self._import(ready)
        executable = self._handoff(
            "ready-executable.json",
            executable_fingerprint="55" * 32,
        )
        with self.assertRaisesRegex(
            ValidationError, "handoff identity mismatch: executable_fingerprint"
        ):
            self._import(executable)

    def test_public_import_rejects_nonexistent_prior_checkpoint(self):
        ready = self._import(self._handoff("ready.json"))
        self._authorize_followup()
        followup = self._handoff(
            "followup.json",
            phase="followup",
            sequence=1,
            message_id="message-1",
            prior_checkpoint_sha256="ff" * 32,
            timestamp="2026-09-19T03:02:00Z",
        )
        with self.assertRaisesRegex(
            ValidationError, "handoff identity mismatch: prior_checkpoint_sha256"
        ):
            self._import(followup)
        self.assertEqual(ready["checkpoint_kind"], "conformance")

    def test_public_ready_followup_review_accept_sequence(self):
        ready = self._import(self._handoff("ready.json"))
        self.assertEqual(
            AgyPrintController(self.state).status(session=SESSION)["state"],
            "CONFORMANCE_READY",
        )
        review_evidence = write_json(
            self.proof / "review.json",
            {"findings": [], "classification": "clean"},
        )
        with self.assertRaisesRegex(ValidationError, "not reviewable"):
            review_checkpoint(
                state_root=self.state,
                session=SESSION,
                checkpoint_id=ready["checkpoint_id"],
                actor="tester",
                verdict="conformance_accept",
                evidence_path=review_evidence,
            )
        self._authorize_followup()
        followup = self._import(
            self._handoff(
                "followup.json",
                phase="followup",
                sequence=1,
                message_id="message-1",
                prior_checkpoint_sha256=ready["artifact_sha256"],
                timestamp="2026-09-19T03:02:00Z",
            )
        )
        self.assertEqual(
            AgyPrintController(self.state).status(session=SESSION)["state"],
            "CONFORMANCE_CHECKPOINT_READY",
        )
        review_checkpoint(
            state_root=self.state,
            session=SESSION,
            checkpoint_id=followup["checkpoint_id"],
            actor="tester",
            verdict="conformance_accept",
            evidence_path=review_evidence,
        )
        self.assertEqual(
            AgyPrintController(self.state).status(session=SESSION)["state"],
            "AWAITING_CONFORMANCE_REVIEW",
        )
        accepted = accept_checkpoint(
            state_root=self.state,
            session=SESSION,
            checkpoint_id=followup["checkpoint_id"],
            actor="tester",
            evidence_path=write_json(
                self.proof / "acceptance.json",
                {"terminal_criteria": ["conformance_green"]},
            ),
        )
        self.assertEqual(accepted["state"], "ACCEPTED")
        self.assertEqual(
            accepted["caller_outcome"]["controller_acceptance"], "accepted"
        )

    def test_public_halt_uses_lease_identity_after_parent_vanishes(self):
        stored = self._session_record()
        persist_agy_print_session(self.state, stored)
        controller = AgyPrintController(self.state)
        with (
            mock.patch("puppet_lib.session._agy_print_bound_session", return_value=controller),
            mock.patch(
                "puppet_lib.session.process_birth_identity",
                side_effect=ProcessVanished(
                    "Linux process vanished before /proc identity sampling"
                ),
            ),
            mock.patch(
                "puppet_lib.session.require_session_lease",
                return_value={"state": "active", "process": dict(PROCESS)},
            ),
            mock.patch("puppet_lib.session.transition_session_lease") as transition,
            mock.patch.object(controller, "halt", return_value={"ok": True}) as halt_mock,
        ):
            result = session_halt(state_root=self.state, session=SESSION)
        self.assertEqual(result, {"ok": True})
        halt_mock.assert_called_once_with(session=SESSION, timeout=10.0)
        self.assertEqual(
            [item.kwargs["state"] for item in transition.call_args_list],
            ["halting", "halted"],
        )

    def test_public_resume_rejects_current_executable_drift_before_admission(self):
        stored = self._session_record(
            held=False,
            executable=sys.executable,
            manifest={
                "executable": {
                    "resolved_path": sys.executable,
                    "sha256": "00" * 32,
                }
            },
        )
        persist_agy_print_session(self.state, stored)
        with mock.patch(
            "puppet_lib.session.require_session_lease",
            return_value={"state": "halted", "process": dict(PROCESS)},
        ):
            with self.assertRaisesRegex(IdentityError, "executable identity changed"):
                from puppet_lib.session import send_message

                send_message(
                    state_root=self.state,
                    session=SESSION,
                    message="resume after drift",
                    request_id="resume-drift",
                )

    def test_public_halt_then_resume_and_replay_do_not_reactivate_history(self):
        base = self._session_record()
        base["held"] = True
        base["observation"] = fixture_observation(
            session=SESSION, workspace_path=str(self.repo), record_state="CONFORMANCE_READY"
        )
        base["protocol"].update(
            phase="ready_validated",
            ready_checkpoint_id="ready-1",
            ready_artifact_sha256="aa" * 32,
        )
        persist_agy_print_session(self.state, base)
        controller = AgyPrintController(self.state)
        with self.assertRaisesRegex(UnsupportedError, "requires explicit halt"):
            send_message(
                state_root=self.state, session=SESSION,
                message="follow up", request_id="followup-1"
            )

        def fake_halt(*, session, timeout):
            current = controller.require_session(session)
            persist_agy_print_session(
                self.state,
                dict(
                    current,
                    held=False,
                    observation=dict(current["observation"], record_state="HALTED"),
                ),
            )
            return {"ok": True, "session": session, "state": "HALTED"}

        with (
            mock.patch("puppet_lib.session._agy_print_bound_session", return_value=controller),
            mock.patch("puppet_lib.session.require_session_lease", return_value={"state": "active", "process": dict(PROCESS)}),
            mock.patch("puppet_lib.session.transition_session_lease"),
            mock.patch.object(controller, "halt", side_effect=fake_halt),
        ):
            self.assertEqual(session_halt(state_root=self.state, session=SESSION)["state"], "HALTED")

        with (
            mock.patch("puppet_lib.session._agy_print_bound_session", return_value=controller),
            mock.patch("puppet_lib.session.require_session_lease", return_value={"state": "halted", "process": dict(PROCESS)}),
            mock.patch("puppet_lib.session._validate_agy_resume_identity"),
            mock.patch("puppet_lib.session.admit_session_lease") as admit,
            mock.patch("puppet_lib.session.transition_session_lease") as transition,
            mock.patch.object(controller, "start", return_value={"ok": True, "state": "ACTIVE"}) as start,
        ):
            result = send_message(
                state_root=self.state, session=SESSION,
                message="follow up", request_id="followup-1"
            )
        self.assertEqual(result["state"], "ACTIVE")
        admit.assert_called_once()
        self.assertEqual(transition.call_args.kwargs["state"], "active")
        self.assertIn("PUPPET_FOLLOWUP_V2", start.call_args.kwargs["prompt"])
        current = controller.require_session(SESSION)
        self.assertEqual(current["protocol"]["phase"], "followup_sent")
        self.assertEqual(current["observation"]["record_state"], "ACTIVE")

        with (
            mock.patch("puppet_lib.session._agy_print_bound_session", return_value=controller),
            mock.patch("puppet_lib.session.require_session_lease", return_value={"state": "halted", "process": dict(PROCESS)}),
            mock.patch("puppet_lib.session.process_birth_identity") as identity,
        ):
            replay = send_message(
                state_root=self.state, session=SESSION,
                message="follow up", request_id="followup-1"
            )
        self.assertEqual(replay["request_id"], "followup-1")
        identity.assert_not_called()

    def test_post_start_identity_failure_halts_before_releasing_lease(self):
        base = self._session_record(
            held=False,
            observation=fixture_observation(
                session=SESSION, workspace_path=str(self.repo), record_state="HALTED"
            ),
        )
        base["protocol"].update(phase="ready_validated", ready_artifact_sha256="aa" * 32)
        persist_agy_print_session(self.state, base)
        controller = AgyPrintController(self.state)
        halt_calls = []

        def fake_halt(*, session, timeout=5.0):
            halt_calls.append(session)
            current = controller.require_session(session)
            persist_agy_print_session(
                self.state,
                dict(
                    current,
                    held=False,
                    observation=dict(current["observation"], record_state="HALTED"),
                ),
            )
            return {"ok": True, "session": session, "state": "HALTED"}

        with (
            mock.patch("puppet_lib.session._agy_print_bound_session", return_value=controller),
            mock.patch("puppet_lib.session.require_session_lease", return_value={"state": "halted", "process": dict(PROCESS)}),
            mock.patch("puppet_lib.session._validate_agy_resume_identity"),
            mock.patch("puppet_lib.session.admit_session_lease"),
            mock.patch("puppet_lib.session.transition_session_lease") as transition,
            mock.patch("puppet_lib.session.process_birth_identity", side_effect=IdentityError("transient identity unavailable")),
            mock.patch.object(controller, "start", return_value={"ok": True, "state": "ACTIVE"}),
            mock.patch.object(controller, "halt", side_effect=fake_halt),
        ):
            with self.assertRaisesRegex(IdentityError, "transient identity unavailable"):
                send_message(
                    state_root=self.state, session=SESSION,
                    message="follow up", request_id="followup-cleanup"
                )
        self.assertEqual(halt_calls, [SESSION])
        self.assertEqual(transition.call_args.kwargs["state"], "failed")

    def test_public_ready_halt_send_persists_followup_for_import(self):
        ready = self._import(self._handoff("ready.json"))
        self.assertEqual(
            AgyPrintController(self.state).status(session=SESSION)["state"],
            "CONFORMANCE_READY",
        )
        self._bind_executable()
        self._public_halt()
        result, start_kwargs = self._public_resume_send("follow up", "followup-1")
        self.assertEqual(result["state"], "ACTIVE")
        self.assertIn("PUPPET_FOLLOWUP_V2", start_kwargs["prompt"])
        current = AgyPrintController(self.state).require_session(SESSION)
        self.assertIsNone(current["observation"]["halt"])
        self.assertEqual(
            current["observation"]["terminal_result"]["state"], "completed"
        )
        self.assertEqual(current["observation"]["record_state"], "ACTIVE")
        self.assertEqual(current["protocol"]["phase"], "followup_sent")
        self.assertEqual(current["protocol"]["message_id"], "followup-1")
        self.assertEqual(
            current["send_requests"]["followup-1"]["phase"], "submitted"
        )
        followup = self._import(
            self._handoff(
                "followup.json",
                phase="followup",
                sequence=1,
                message_id="followup-1",
                prior_checkpoint_sha256=ready["artifact_sha256"],
                timestamp="2026-09-19T03:02:00Z",
            )
        )
        self.assertEqual(followup["checkpoint_kind"], "conformance")
        self.assertEqual(
            AgyPrintController(self.state).status(session=SESSION)["state"],
            "CONFORMANCE_CHECKPOINT_READY",
        )

    def test_public_source_accept_halt_assigns_proof_for_checkpoint(self):
        repo, identity = self._init_source_repo()
        persist_agy_print_session(
            self.state, self._source_session_record(repo, identity)
        )
        source = self._import(
            self._source_handoff(
                "source.json", identity["head"], "Bounded source checkpoint"
            )
        )
        review_evidence = write_json(
            self.proof / "source-review.json",
            {"findings": [], "classification": "clean"},
        )
        review_checkpoint(
            state_root=self.state,
            session=SESSION,
            checkpoint_id=source["checkpoint_id"],
            actor="tester",
            verdict="source_accept",
            evidence_path=review_evidence,
        )
        self.assertEqual(
            AgyPrintController(self.state).status(session=SESSION)["state"],
            "SOURCE_ACCEPTED",
        )
        self._bind_executable()
        self._public_halt()
        result, start_kwargs = self._public_resume_send(
            "Create one proof-only child of the accepted source.",
            "proof-1",
        )
        self.assertEqual(result["state"], "ACTIVE")
        self.assertIn("PUPPET_SOURCE_PROOF_ASSIGNMENT_V2", start_kwargs["prompt"])
        current = AgyPrintController(self.state).require_session(SESSION)
        self.assertIsNone(current["observation"]["halt"])
        self.assertEqual(
            current["observation"]["terminal_result"]["state"], "completed"
        )
        self.assertEqual(current["observation"]["record_state"], "SOURCE_ACCEPTED")
        self.assertEqual(current["protocol"]["phase"], "proof_assignment_sent")
        self.assertEqual(current["protocol"]["proof_assignment_id"], "proof-1")
        (repo / "proof").mkdir()
        write_json(repo / "proof" / "receipt.json", {"source_commit": identity["head"]})
        proof_identity = self._git_commit(repo, "proof")
        proof = self._import(
            self._source_handoff(
                "proof.json",
                proof_identity["head"],
                "Proof-only child checkpoint",
            )
        )
        self.assertEqual(
            AgyPrintController(self.state).status(session=SESSION)["state"],
            "PROOF_CHECKPOINT_READY",
        )
        review_checkpoint(
            state_root=self.state,
            session=SESSION,
            checkpoint_id=proof["checkpoint_id"],
            actor="tester",
            verdict="source_accept",
            evidence_path=review_evidence,
        )
        self.assertEqual(
            AgyPrintController(self.state).status(session=SESSION)["state"],
            "AWAITING_CONTROLLER_REVIEW",
        )

    def test_failed_resume_cleanup_recovers_through_later_public_halt(self):
        full_process = {
            "identity_version": 2,
            "pid": PROCESS["pid"],
            "kernel_birth_id": PROCESS["kernel_birth_id"],
            "start": "2026-09-19T15:00:00Z",
            "command": "agy --print",
            "executable_path": sys.executable,
            "device": 1,
            "inode": 2,
        }
        base = self._session_record(
            held=False,
            observation=fixture_observation(
                session=SESSION, workspace_path=str(self.repo), record_state="HALTED"
            ),
        )
        base["protocol"].update(
            phase="ready_validated", ready_artifact_sha256="aa" * 32
        )
        persist_agy_print_session(self.state, base)
        self._bind_executable()
        lease = {"state": "halted", "process": None}

        def require_lease(**kwargs):
            if lease["state"] not in kwargs["states"]:
                raise IdentityError("lease state refused: %s" % lease["state"])
            return dict(lease)

        def admit_lease(**kwargs):
            lease.update(state="launching", process=None)
            return dict(lease)

        def transition_lease(*, state, process, **kwargs):
            lease.update(state=state, process=process or lease.get("process"))
            return dict(lease)

        observation = copy.deepcopy(base["observation"])
        observation.update(
            record_state="ACTIVE",
            terminal_result={"state": "completed", "exit_code": 0},
            halt=None,
        )
        runtime = SimpleNamespace(
            observation=observation,
            identity=full_process,
            conversation_id=base["conversation_id"],
            require_observation=lambda: observation,
        )
        process_samples = [
            IdentityError("identity sampling unavailable"),
            dict(full_process),
        ]
        real_halt = AgyPrintController.halt
        halt_calls = []

        def fail_once_then_real(controller, **kwargs):
            halt_calls.append(kwargs.get("session"))
            if len(halt_calls) == 1:
                raise IdentityError("cleanup not proven")
            return real_halt(controller, **kwargs)

        with (
            mock.patch("puppet_lib.session.require_session_lease", side_effect=require_lease),
            mock.patch("puppet_lib.session.admit_session_lease", side_effect=admit_lease),
            mock.patch("puppet_lib.session.transition_session_lease", side_effect=transition_lease),
            mock.patch("puppet_lib.session._validate_agy_resume_identity"),
            mock.patch("puppet_lib.session.process_birth_identity", side_effect=process_samples),
            mock.patch("puppet_lib.agy_print.agy_print_runtime_available", return_value=True),
            mock.patch.object(AgyPrintRuntime, "start", return_value=runtime),
            mock.patch.object(AgyPrintController, "halt", autospec=True, side_effect=fail_once_then_real),
            mock.patch("puppet_lib.agy_print._pid_gone", return_value=True),
        ):
            with self.assertRaisesRegex(IdentityError, "resume cleanup was not proven"):
                send_message(
                    state_root=self.state,
                    session=SESSION,
                    message="follow up",
                    request_id="cleanup-recovery-1",
                )
            self.assertEqual(lease["state"], "active")
            self.assertEqual(lease["process"], full_process)
            result = session_halt(state_root=self.state, session=SESSION)

        self.assertEqual(result["state"], "HALTED")
        self.assertEqual(halt_calls, [SESSION, SESSION])
        self.assertEqual(lease["state"], "halted")
        self.assertFalse(AgyPrintController(self.state).require_session(SESSION)["held"])


if __name__ == "__main__":
    unittest.main()
