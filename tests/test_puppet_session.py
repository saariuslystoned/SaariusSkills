from __future__ import annotations

import hashlib
import json
import threading
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "puppet" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import puppet_lib.session as puppet_session  # noqa: E402
from puppet_lib.adapter_manifest import AdapterManifest  # noqa: E402
from puppet_lib.authority import (  # noqa: E402
    admit_session_lease,
    current_session_lease,
    lease_owner,
)
from puppet_lib.campaign import (  # noqa: E402
    ALLOWED_ACTIONS as CAMPAIGN_ALLOWED_ACTIONS,
    HARD_GATES as CAMPAIGN_HARD_GATES,
)
from puppet_lib.conformance import create_fixture  # noqa: E402
from puppet_lib.contracts import Contract  # noqa: E402
from puppet_lib.errors import ConflictError, IdentityError, ValidationError  # noqa: E402
from puppet_lib.registry import SessionRegistry, send_exact_sigint  # noqa: E402
from puppet_lib.instructions import instruction_policy_fingerprint  # noqa: E402
from puppet_lib.session import (  # noqa: E402
    _deliver,
    accept_checkpoint,
    halt,
    import_checkpoint,
    launch as _launch,
    record_beacon,
    review_checkpoint,
    send_message,
    status,
    wait_for,
)
from puppet_lib.tmux import TmuxController  # noqa: E402
from puppet_lib.profiles import (  # noqa: E402
    PROMPT_TRANSPORT,
    SUBMIT_SETTLE_SECONDS,
    default_session_profile,
    session_profiles_for,
    startup_settle_seconds_for,
)
from puppet_lib.safety import sha256_file  # noqa: E402
from tests.puppet_test_receipt import write_qualification_receipt  # noqa: E402


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


def launch(**kwargs):
    kwargs.setdefault("_sleep_fn", lambda _interval: None)
    return _launch(**kwargs)


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
        "prompt_transport": PROMPT_TRANSPORT,
        "prompt_transport_declared": True,
        "sandbox_disable_declared": True,
        "sandbox_flags": ["test-owned-process"],
        "project_isolation_declared": True,
        "project_isolation_flags": [],
        "session_profiles": session_profiles_for(target),
        "session_profiles_declared": True,
        "startup_settle_seconds": startup_settle_seconds_for(target),
        "submit_settle_seconds": SUBMIT_SETTLE_SECONDS,
    }
    platform_value = {"system": "Darwin", "release": "test", "machine": "test"}
    platform_fingerprint = hashlib.sha256(
        json.dumps(
            platform_value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()
    mapping_fingerprint = hashlib.sha256(
        json.dumps(
            yolo_mapping,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()
    write_qualification_receipt(
        receipt_path,
        run_id="kernel-test-qualification",
        target=target,
        controller="tester",
        executable_path=executable,
        executable_fingerprint=executable_sha,
        version_fingerprint="b" * 64,
        platform_fingerprint=platform_fingerprint,
        adapter_fingerprint=adapter_fingerprint,
        protocol_fingerprint=protocol,
        yolo_mapping_sha256=mapping_fingerprint,
        capabilities=[
            "launch",
            "send",
            "status",
            "wait",
            "checkpoint",
            "halt",
        ],
    )
    raw = {
        "schema_version": 1,
        "target": target,
        "generated_at": "2026-07-22T03:00:00Z",
        "platform": platform_value,
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
            name: "controller_verified" if name != "resume" else "unsupported"
            for name in (
                "launch",
                "send",
                "status",
                "wait",
                "checkpoint",
                "resume",
                "halt",
            )
        },
        "doctor_only": False,
        "qualification": {
            "receipt_path": str(receipt_path),
            "receipt_sha256": hashlib.sha256(receipt_path.read_bytes()).hexdigest(),
            "session_profile": default_session_profile(target),
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
                "id": "conformance_green"
                if task_profile == "conformance"
                else "source_green",
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
            "schema_version": 1,
            "campaign_id": "campaign-test",
            "operator_identity": "tester",
            "controller": "tester",
            "goal": {
                "repository": "test/SaariusSkills",
                "commit": "1" * 40,
                "path": "plans/puppet/codex-goal.md",
                "sha256": "2" * 64,
            },
            "acknowledged_at": "2026-07-22T03:00:00Z",
            "authorization": {
                "trust_profile": "unrestricted_required",
                "harnesses": ["codex"],
                "disable_harness_sandbox_where_exposed": True,
                "ordinary_configured_model_provider_traffic": True,
                "scope": "bounded Puppet implementation and conformance campaign only",
            },
            "allowed_actions": CAMPAIGN_ALLOWED_ACTIONS,
            "hard_gates": CAMPAIGN_HARD_GATES,
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
    def setUp(self):
        # Session composition tests use /bin/cat as a deterministic target.
        # Real-adapter qualification and anti-forgery are covered separately.
        qualification_patcher = patch.object(
            AdapterManifest,
            "verify_qualification",
            return_value={
                "result": "accepted",
                "test_only": True,
                "instruction_policy_fingerprint": instruction_policy_fingerprint(
                    target="codex"
                ),
            },
        )
        qualification_patcher.start()
        self.addCleanup(qualification_patcher.stop)
        self._authority_temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self._authority_temporary.cleanup)
        authority_root = Path(self._authority_temporary.name) / "authority"
        self.authority_root = authority_root
        authority_patcher = patch(
            "puppet_lib.authority.canonical_authority_root",
            return_value=authority_root,
        )
        authority_patcher.start()
        self.addCleanup(authority_patcher.stop)

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

    def test_doctor_rejects_deferred_profile_and_model_selection(self):
        cases = (
            ("session_profile", "goal", "only the regular session profile"),
            ("requested_model", "explicit-model", "model and effort selection"),
            ("requested_effort", "high", "model and effort selection"),
        )
        for field, selected, blocker in cases:
            with self.subTest(field=field), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary).resolve()
                candidate = initialize_repo(
                    root / "candidate",
                    "codex/deferred-selector",
                    "candidate",
                )
                files = controller_files(
                    root,
                    candidate=candidate,
                    branch="codex/deferred-selector",
                    session="codex-deferred-selector",
                    task_profile="implementation",
                    protocol_fingerprint="e" * 64,
                )
                contract = json.loads(files["contract"].read_text(encoding="utf-8"))
                contract[field] = selected
                write_json(files["contract"], contract)
                report = puppet_session.doctor(
                    contract_path=files["contract"],
                    manifest_path=files["manifest"],
                    authorization_path=files["authorization"],
                    proof_root=files["proof"],
                    state_root=files["state"],
                )
                self.assertFalse(report["launch_ready"])
                self.assertTrue(any(blocker in item for item in report["blockers"]))

    def test_doctor_requires_a_clean_read_only_candidate(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            candidate = initialize_repo(
                root / "candidate",
                "codex/dirty-read-only",
                "candidate",
            )
            files = controller_files(
                root,
                candidate=candidate,
                branch="codex/dirty-read-only",
                session="codex-dirty-read-only",
                task_profile="conformance",
                protocol_fingerprint="e" * 64,
            )
            (candidate / "candidate.txt").write_text(
                "dirty read-only content\n", encoding="utf-8"
            )
            report = puppet_session.doctor(
                contract_path=files["contract"],
                manifest_path=files["manifest"],
                authorization_path=files["authorization"],
                proof_root=files["proof"],
                state_root=files["state"],
            )
            self.assertFalse(report["launch_ready"])
            self.assertIn("candidate worktree is not clean", report["blockers"])

    def test_workspace_drift_after_doctor_fails_before_tmux_launch(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            session = "codex-workspace-drift"
            candidate = initialize_repo(
                root / "candidate", "codex/workspace-drift", "candidate"
            )
            files = controller_files(
                root,
                candidate=candidate,
                branch="codex/workspace-drift",
                session=session,
                task_profile="implementation",
                protocol_fingerprint="e" * 64,
            )
            contract = Contract.from_path(files["contract"])
            baseline = puppet_session._workspace_snapshot(contract)
            changed = dict(baseline, head="0" * 40)
            with (
                patch.object(
                    puppet_session,
                    "_workspace_snapshot",
                    side_effect=[baseline, changed],
                ),
                patch.object(TmuxController, "launch") as tmux_launch,
            ):
                with self.assertRaisesRegex(
                    IdentityError, "workspace changed after preflight"
                ):
                    launch(
                        session=session,
                        contract_path=files["contract"],
                        manifest_path=files["manifest"],
                        authorization_path=files["authorization"],
                        proof_root=files["proof"],
                        state_root=files["state"],
                        supervisor_executable=files["supervisor_executable"],
                        prompt="Do not launch after workspace drift.",
                    )
            tmux_launch.assert_not_called()
            self.assertFalse(SessionRegistry(files["state"]).exists(session))
            self.assertEqual(
                current_session_lease(self.authority_root, target="codex")["state"],
                "failed",
            )

    def test_instruction_drift_during_settle_prevents_first_delivery(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            session = "codex-instruction-settle-drift"
            candidate = initialize_repo(
                root / "candidate", "codex/instruction-settle-drift", "candidate"
            )
            files = controller_files(
                root,
                candidate=candidate,
                branch="codex/instruction-settle-drift",
                session=session,
                task_profile="implementation",
                protocol_fingerprint="e" * 64,
            )
            socket = None

            def tamper(_interval):
                path = files["proof"] / "effective-instructions.json"
                manifest = json.loads(path.read_text(encoding="utf-8"))
                manifest["rendered_sha256"] = "0" * 64
                puppet_session.atomic_write_json(path, manifest)

            try:
                with self.assertRaisesRegex(
                    IdentityError, "instruction manifest fingerprint changed"
                ):
                    _launch(
                        session=session,
                        contract_path=files["contract"],
                        manifest_path=files["manifest"],
                        authorization_path=files["authorization"],
                        proof_root=files["proof"],
                        state_root=files["state"],
                        supervisor_executable=files["supervisor_executable"],
                        prompt="Never deliver this after instruction drift.",
                        _sleep_fn=tamper,
                    )
                record = SessionRegistry(files["state"]).load(session)
                socket = record["tmux"]["socket"]
                self.assertEqual(record["state"], "BLOCKED")
                self.assertEqual(
                    current_session_lease(self.authority_root, target="codex")["state"],
                    "halting",
                )
                events = [
                    row["event"]
                    for row in puppet_session._journal(files["proof"]).snapshot()
                ]
                self.assertFalse(
                    any(event.get("kind") == "initial_message" for event in events)
                )
            finally:
                kill_test_server(socket)

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
            task_marker = "PUPPET_TASK_MARKER_42"
            private_launch_value = "session-launch-value-that-must-remain-private"
            try:
                with patch.dict(
                    "os.environ",
                    {"CODEX_HOME": private_launch_value},
                    clear=False,
                ):
                    launched = launch(
                        session=session,
                        contract_path=files["contract"],
                        manifest_path=files["manifest"],
                        authorization_path=files["authorization"],
                        proof_root=files["proof"],
                        state_root=files["state"],
                        supervisor_executable=files["supervisor_executable"],
                        prompt=(
                            "Write the bounded ready handoff and wait. " + task_marker
                        ),
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
                self.assertEqual(beacon_wait["last_beacon"]["kind"], "status_claim")
                record = SessionRegistry(files["state"]).load(session)
                socket = record["tmux"]["socket"]
                instruction_path = Path(record["instructions"]["manifest_path"])
                instruction_manifest = json.loads(
                    instruction_path.read_text(encoding="utf-8")
                )
                self.assertEqual(
                    launched["instruction_policy_fingerprint"],
                    instruction_manifest["instruction_policy_fingerprint"],
                )
                self.assertEqual(
                    launched["effective_contract_fingerprint"],
                    instruction_manifest["effective_contract_fingerprint"],
                )
                launch_intent = next(
                    row["event"]
                    for row in puppet_session._journal(files["proof"]).snapshot()
                    if row["event"].get("kind") == "launch"
                    and row["event"].get("phase") == "intent"
                )
                self.assertEqual(
                    launch_intent["content_sha256"],
                    instruction_manifest["rendered_sha256"],
                )
                launch_started = next(
                    row["event"]
                    for row in puppet_session._journal(files["proof"]).snapshot()
                    if row["event"].get("kind") == "launch"
                    and row["event"].get("phase") == "target_started"
                )
                self.assertEqual(
                    set(launch_started["launch_identity"]),
                    {"cwd", "argv_sha256", "env_names", "env_fingerprint"},
                )
                self.assertIn(
                    "CODEX_HOME", launch_started["launch_identity"]["env_names"]
                )
                marker_bytes = task_marker.encode("utf-8")
                private_launch_bytes = private_launch_value.encode("utf-8")
                persisted = [
                    path
                    for root_path in (files["proof"], files["state"])
                    for path in root_path.rglob("*")
                    if path.is_file()
                ]
                self.assertTrue(persisted)
                for path in persisted:
                    with self.subTest(no_raw_task=path):
                        self.assertNotIn(marker_bytes, path.read_bytes())
                        self.assertNotIn(private_launch_bytes, path.read_bytes())

                tampered_instructions = dict(
                    instruction_manifest,
                    rendered_sha256="0" * 64,
                )
                write_json(instruction_path, tampered_instructions)
                with self.assertRaisesRegex(
                    IdentityError, "instruction manifest fingerprint changed"
                ):
                    status(state_root=files["state"], session=session)
                puppet_session.atomic_write_json(instruction_path, instruction_manifest)
                bound_contract_path = Path(record["contract_path"])
                bound_contract = json.loads(
                    bound_contract_path.read_text(encoding="utf-8")
                )
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
                    "executable_fingerprint": record["adapter"][
                        "executable_fingerprint"
                    ],
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
                    state_root=files["state"],
                    session=session,
                    handoff_path=followup_path,
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
                self.assertEqual(
                    status(state_root=files["state"], session=session)["state"], before
                )
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
                    halt(state_root=files["state"], session=session, timeout=5)[
                        "state"
                    ],
                    "HALTED",
                )
            finally:
                kill_test_server(socket)

    def test_halt_seals_an_exact_blocked_session_when_target_already_stopped(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            candidate = initialize_repo(
                root / "candidate", "codex/dead-target", "candidate"
            )
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
                send_exact_sigint(record["process"])
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    metadata = TmuxController(files["state"]).metadata(
                        socket=Path(socket),
                        session=session,
                        pane=record["tmux"]["pane"],
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
                original_transition = puppet_session.transition_session_lease
                injected = {"raised": False}

                def interrupt_terminal_lease(**kwargs):
                    if kwargs.get("state") == "halted" and not injected["raised"]:
                        injected["raised"] = True
                        raise KeyboardInterrupt()
                    return original_transition(**kwargs)

                with patch.object(
                    puppet_session,
                    "transition_session_lease",
                    side_effect=interrupt_terminal_lease,
                ):
                    with self.assertRaises(KeyboardInterrupt):
                        halt(state_root=files["state"], session=session, timeout=1)
                self.assertEqual(registry.load(session)["state"], "HALTED")
                self.assertEqual(
                    current_session_lease(self.authority_root, target="codex")["state"],
                    "halting",
                )
                replay = halt(state_root=files["state"], session=session, timeout=1)
                self.assertEqual(replay["state"], "HALTED")
                self.assertFalse(replay["signal_sent"])
                self.assertTrue(replay["tmux_preserved"])
                self.assertEqual(
                    current_session_lease(self.authority_root, target="codex")["state"],
                    "halted",
                )
                later_owner = lease_owner(
                    activity="session",
                    run_id="later-session-run",
                    campaign_id="campaign-test",
                    goal_fingerprint="a" * 64,
                    proof_root=files["proof"],
                    state_root=files["state"],
                )
                later = admit_session_lease(
                    session="later-session",
                    target="claude",
                    controller="tester",
                    owner=later_owner,
                    instruction_manifest_sha256=sha256_file(files["manifest"]),
                    authority_root=self.authority_root,
                )
                replay = halt(state_root=files["state"], session=session, timeout=1)
                self.assertEqual(replay["state"], "HALTED")
                self.assertEqual(
                    current_session_lease(self.authority_root, target="claude"),
                    later,
                )
            finally:
                kill_test_server(socket)

    def test_launch_delivery_failure_keeps_recoverable_halting_lease(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            candidate = initialize_repo(
                root / "candidate", "codex/launch-recovery", "candidate"
            )
            session = "codex-launch-recovery"
            files = controller_files(
                root,
                candidate=candidate,
                branch="codex/launch-recovery",
                session=session,
                task_profile="implementation",
                protocol_fingerprint="e" * 64,
            )
            socket = None
            try:
                with patch.object(
                    puppet_session,
                    "_deliver",
                    side_effect=RuntimeError("injected delivery failure"),
                ):
                    with self.assertRaisesRegex(RuntimeError, "injected delivery"):
                        launch(
                            session=session,
                            contract_path=files["contract"],
                            manifest_path=files["manifest"],
                            authorization_path=files["authorization"],
                            proof_root=files["proof"],
                            state_root=files["state"],
                            supervisor_executable=files["supervisor_executable"],
                            prompt="Remain available for launch recovery.",
                        )
                record = SessionRegistry(files["state"]).load(session)
                socket = record["tmux"]["socket"]
                self.assertEqual(record["state"], "BLOCKED")
                self.assertTrue(record["blocker"]["cleanup_stopped"])
                self.assertEqual(
                    current_session_lease(self.authority_root, target="codex")["state"],
                    "halting",
                )
                result = halt(state_root=files["state"], session=session, timeout=1)
                self.assertEqual(result["state"], "HALTED")
                self.assertEqual(
                    current_session_lease(self.authority_root, target="codex")["state"],
                    "halted",
                )
            finally:
                kill_test_server(socket)

    def test_concurrent_duplicate_launch_cannot_switch_state_root(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            candidate = initialize_repo(
                root / "candidate", "codex/duplicate-launch", "candidate"
            )
            session = "codex-duplicate-launch"
            files = controller_files(
                root,
                candidate=candidate,
                branch="codex/duplicate-launch",
                session=session,
                task_profile="implementation",
                protocol_fingerprint="e" * 64,
            )
            second_state = root / "second-state"
            second_state.mkdir(mode=0o700)
            socket = None
            first_entered_tmux = threading.Event()
            release_first = threading.Event()
            original_launch = TmuxController.launch
            launch_calls = []
            first_result = []
            first_error = []

            def paused_launch(controller, **kwargs):
                launch_calls.append(kwargs["session"])
                first_entered_tmux.set()
                if not release_first.wait(timeout=5):
                    raise RuntimeError("test launch barrier timed out")
                return original_launch(controller, **kwargs)

            def run_first():
                try:
                    first_result.append(
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
                    )
                except BaseException as exc:
                    first_error.append(exc)

            try:
                with patch.object(TmuxController, "launch", new=paused_launch):
                    thread = threading.Thread(target=run_first)
                    thread.start()
                    self.assertTrue(first_entered_tmux.wait(timeout=5))
                    with self.assertRaisesRegex(ConflictError, "controller lease"):
                        launch(
                            session=session,
                            contract_path=files["contract"],
                            manifest_path=files["manifest"],
                            authorization_path=files["authorization"],
                            proof_root=files["proof"],
                            state_root=second_state,
                            supervisor_executable=files["supervisor_executable"],
                            prompt="Remain available for exact halt.",
                        )
                    release_first.set()
                    thread.join(timeout=10)
                self.assertFalse(thread.is_alive())
                self.assertEqual(first_error, [])
                self.assertEqual(len(first_result), 1)
                self.assertEqual(launch_calls, [session])
                record = SessionRegistry(files["state"]).load(session)
                socket = record["tmux"]["socket"]
                self.assertEqual(
                    current_session_lease(self.authority_root, target="codex")["state"],
                    "active",
                )
                self.assertEqual(
                    halt(state_root=files["state"], session=session, timeout=5)[
                        "state"
                    ],
                    "HALTED",
                )
            finally:
                release_first.set()
                if "thread" in locals() and thread.is_alive():
                    thread.join(timeout=5)
                kill_test_server(socket)

    def test_process_binding_failure_fences_provisional_launch_without_input(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            candidate = initialize_repo(
                root / "candidate", "codex/provisional-cleanup", "candidate"
            )
            session = "codex-provisional-cleanup"
            files = controller_files(
                root,
                candidate=candidate,
                branch="codex/provisional-cleanup",
                session=session,
                task_profile="implementation",
                protocol_fingerprint="e" * 64,
            )
            socket = str(TmuxController(files["state"]).socket_path(session))
            try:
                with patch.object(
                    puppet_session,
                    "process_birth_identity",
                    side_effect=IdentityError("injected process binding failure"),
                ):
                    with self.assertRaisesRegex(
                        IdentityError, "injected process binding"
                    ):
                        launch(
                            session=session,
                            contract_path=files["contract"],
                            manifest_path=files["manifest"],
                            authorization_path=files["authorization"],
                            proof_root=files["proof"],
                            state_root=files["state"],
                            supervisor_executable=files["supervisor_executable"],
                            prompt="Remain available for provisional cleanup.",
                        )
                self.assertTrue(SessionRegistry(files["state"]).exists(session))
                self.assertEqual(
                    current_session_lease(self.authority_root, target="codex")["state"],
                    "launching",
                )
                metadata = TmuxController(files["state"]).metadata_for_session(
                    socket=Path(socket),
                    session=session,
                )
                self.assertFalse(metadata["pane_dead"])
            finally:
                kill_test_server(socket)

    def test_concurrent_conformance_followups_deliver_exactly_once(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            session = "codex-followup-owner"
            candidate = root / "candidate"
            fixture_contract = create_fixture(
                candidate,
                run_id="followup-owner-run",
                session=session,
                target="codex",
            )
            subprocess.run(
                ["git", "init", "-q", "-b", "codex/followup-owner", str(candidate)],
                check=True,
            )
            commit_all(candidate, "candidate")
            files = controller_files(
                root,
                candidate=candidate,
                branch="codex/followup-owner",
                session=session,
                task_profile="conformance",
                protocol_fingerprint=fixture_contract["protocol_fingerprint"],
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
                    prompt="Remain available for follow-up ownership proof.",
                )
                registry = SessionRegistry(files["state"])
                record = registry.load(session)
                socket = record["tmux"]["socket"]
                protocol = dict(record["protocol"])
                protocol.update(
                    phase="ready_validated",
                    ready_checkpoint_id="a" * 64,
                    ready_artifact_sha256="b" * 64,
                )
                registry.update(
                    session,
                    {"state": "CONFORMANCE_READY", "protocol": protocol},
                )
                deliveries = []
                delivery_lock = threading.Lock()

                def fake_deliver(**kwargs):
                    with delivery_lock:
                        deliveries.append(kwargs["operation_id"])
                    time.sleep(0.1)
                    return {"delivery": "submitted", "content_sha256": "c" * 64}

                results = []
                errors = []
                start = threading.Barrier(2)

                def worker(request_id):
                    try:
                        start.wait()
                        results.append(
                            send_message(
                                state_root=files["state"],
                                session=session,
                                message="Write exactly one follow-up.",
                                request_id=request_id,
                            )
                        )
                    except Exception as exc:
                        errors.append(exc)

                with patch.object(puppet_session, "_deliver", side_effect=fake_deliver):
                    threads = [
                        threading.Thread(target=worker, args=("message-a",)),
                        threading.Thread(target=worker, args=("message-b",)),
                    ]
                    for thread in threads:
                        thread.start()
                    for thread in threads:
                        thread.join()
                self.assertEqual(len(results), 1)
                self.assertEqual(len(errors), 1)
                self.assertIsInstance(errors[0], ValidationError)
                self.assertEqual(len(deliveries), 1)
                self.assertEqual(
                    halt(state_root=files["state"], session=session, timeout=2)[
                        "state"
                    ],
                    "HALTED",
                )
            finally:
                kill_test_server(socket)

    def test_interrupted_normal_agy_eof_is_never_resent(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            candidate = initialize_repo(
                root / "candidate", "codex/ambiguous-eof", "candidate"
            )
            session = "codex-ambiguous-eof"
            files = controller_files(
                root,
                candidate=candidate,
                branch="codex/ambiguous-eof",
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
                    prompt="Remain available for ambiguous EOF proof.",
                )
                record = SessionRegistry(files["state"]).load(session)
                socket = record["tmux"]["socket"]

                class DummyAdapter:
                    graceful_halt_actions = ("tmux_pane_eof", "tmux_pane_eof")

                class InterruptingTmux:
                    def __init__(self):
                        self.calls = []

                    def send_control(self, **kwargs):
                        self.calls.append(kwargs["key"])
                        raise KeyboardInterrupt()

                fake_tmux = InterruptingTmux()

                def fake_runtime(*args, **kwargs):
                    return fake_tmux, {
                        "pane_pid": record["process"]["pid"],
                        "pane_dead": False,
                    }

                with (
                    patch.object(puppet_session, "_runtime", side_effect=fake_runtime),
                    patch.object(
                        puppet_session,
                        "adapter_for",
                        return_value=DummyAdapter(),
                    ),
                    patch.object(puppet_session, "process_alive", return_value=True),
                ):
                    with self.assertRaises(KeyboardInterrupt):
                        halt(state_root=files["state"], session=session, timeout=1)
                    with self.assertRaisesRegex(IdentityError, "ambiguous"):
                        halt(state_root=files["state"], session=session, timeout=1)
                self.assertEqual(fake_tmux.calls, ["C-d"])
            finally:
                kill_test_server(socket)

    def test_halt_is_single_owner_with_two_eof_sequence(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            candidate = initialize_repo(
                root / "candidate", "codex/agy-halt", "candidate"
            )
            session = "codex-agy-halt"
            files = controller_files(
                root,
                candidate=candidate,
                branch="codex/agy-halt",
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
                    prompt="Stay idle for halt concurrency proof.",
                )
                record = SessionRegistry(files["state"]).load(session)
                socket = record["tmux"]["socket"]
                lock_state = {"alive": True, "sends": 0}

                class DummyAdapter:
                    graceful_halt_actions = ("tmux_pane_eof", "tmux_pane_eof")

                class FakeTmux:
                    def __init__(self):
                        self.control_keys = []

                    def send_control(
                        self,
                        *,
                        socket: Path,
                        session: str,
                        pane: str | None = None,
                        key: str,
                        expected_pane_pid: int | None = None,
                    ):
                        if expected_pane_pid != record["process"]["pid"]:
                            raise AssertionError("halt did not bind the pane PID")
                        self.control_keys.append(key)
                        lock_state["sends"] += 1
                        if lock_state["sends"] >= 2:
                            lock_state["alive"] = False

                    def metadata(
                        self, *, socket: Path, session: str, pane: str | None = None
                    ):
                        return {
                            "pane_pid": record["process"]["pid"],
                            "pane_dead": not lock_state["alive"],
                        }

                    def socket_identity(self, socket: Path):
                        return record["tmux"]["socket_identity"]

                fake_tmux = FakeTmux()

                def fake_runtime(
                    registry: SessionRegistry,
                    _record: dict,
                    capability: str,
                    *,
                    require_process: bool,
                ) -> tuple[FakeTmux, dict]:
                    return fake_tmux, {
                        "pane_pid": record["process"]["pid"],
                        "pane_dead": False,
                    }

                def fake_process_alive(identity):
                    return bool(lock_state["alive"])

                def fake_adapter_for(_target: str) -> DummyAdapter:
                    return DummyAdapter()

                original_runtime = puppet_session._runtime
                original_adapter_for = puppet_session.adapter_for
                original_process_alive = puppet_session.process_alive
                results = []
                errors = []
                start = threading.Barrier(2)

                def worker():
                    try:
                        start.wait()
                        results.append(
                            halt(
                                state_root=files["state"],
                                session=session,
                                timeout=1,
                            )
                        )
                    except Exception as exc:
                        errors.append(exc)

                try:
                    puppet_session._runtime = fake_runtime
                    puppet_session.adapter_for = fake_adapter_for
                    puppet_session.process_alive = fake_process_alive
                    threads = [
                        threading.Thread(target=worker),
                        threading.Thread(target=worker),
                    ]
                    for thread in threads:
                        thread.start()
                    for thread in threads:
                        thread.join()
                finally:
                    puppet_session._runtime = original_runtime
                    puppet_session.adapter_for = original_adapter_for
                    puppet_session.process_alive = original_process_alive

                self.assertEqual(errors, [])
                self.assertEqual(len(results), 2)
                self.assertEqual(results[0], results[1])
                self.assertEqual(results[0]["state"], "HALTED")
                self.assertEqual(fake_tmux.control_keys, ["C-d", "C-d"])
                self.assertEqual(
                    SessionRegistry(files["state"]).load(session)["state"], "HALTED"
                )
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
                (candidate / "feature.txt").write_text(
                    "bounded source\n", encoding="utf-8"
                )
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
                            "executable_fingerprint": record["adapter"][
                                "executable_fingerprint"
                            ],
                            "adapter_fingerprint": record["adapter"][
                                "adapter_fingerprint"
                            ],
                            "protocol_fingerprint": record["adapter"][
                                "protocol_fingerprint"
                            ],
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
                write_source_handoff(
                    source_path, source_commit, "Bounded source checkpoint"
                )
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
                write_source_handoff(
                    proof_handoff, proof_commit, "Proof-only child checkpoint"
                )
                proof_import = import_checkpoint(
                    state_root=files["state"],
                    session=session,
                    handoff_path=proof_handoff,
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
                    halt(state_root=files["state"], session=session, timeout=5)[
                        "state"
                    ],
                    "HALTED",
                )
            finally:
                kill_test_server(socket)


if __name__ == "__main__":
    unittest.main()
