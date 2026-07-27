from __future__ import annotations

import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "puppet" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from puppet_lib.adapter_manifest import AdapterManifest  # noqa: E402
import puppet_lib.authority as puppet_authority  # noqa: E402
import puppet_lib.session as puppet_session  # noqa: E402
from puppet_lib.authority import (  # noqa: E402
    admit_session_lease,
    current_session_lease,
    lease_owner,
    strict_session_lease_projection,
    transition_session_lease,
)
from puppet_lib.contracts import Contract  # noqa: E402
from puppet_lib.errors import IdentityError, ValidationError  # noqa: E402
from puppet_lib.instructions import instruction_policy_fingerprint  # noqa: E402
from puppet_lib.journal import Journal  # noqa: E402
from puppet_lib.registry import SessionRegistry, send_exact_sigint  # noqa: E402
from puppet_lib.safety import atomic_write_json  # noqa: E402
from puppet_lib.session import (  # noqa: E402
    _dead_grok_lease_preflight,
    _prove_recorded_process_birth_gone,
    halt,
    launch,
    reconcile_grok_dead_lease,
    status,
)
from puppet_lib.tmux import TmuxController  # noqa: E402
from tests.test_puppet_session import (  # noqa: E402
    commit_all,
    controller_files,
    initialize_repo,
    kill_test_server,
)


class GrokDeadLeaseReconciliationTests(unittest.TestCase):
    def setUp(self):
        if not TmuxController.available():
            self.skipTest("tmux is unavailable")
        self.active_processes = patch(
            "puppet_lib.session._active_processes",
            return_value=[],
        )
        self.active_processes.start()
        self.addCleanup(self.active_processes.stop)
        self.qualification = patch.object(
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
        self.qualification.start()
        self.addCleanup(self.qualification.stop)
        self.authority_temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.authority_temporary.cleanup)
        self.authority_root = (
            Path(self.authority_temporary.name).resolve() / "authority"
        )
        self.authority = patch(
            "puppet_lib.authority.canonical_authority_root",
            return_value=self.authority_root,
        )
        self.authority.start()
        self.addCleanup(self.authority.stop)

    @staticmethod
    def _files_snapshot(root: Path) -> dict[str, bytes]:
        return {
            str(path.relative_to(root)): path.read_bytes()
            for path in sorted(root.rglob("*"))
            if path.is_file()
        }

    def _seed_historical_v1_legacy_generation(self, root: Path) -> None:
        authority = puppet_authority.controller_authority_root(root)
        proof_root = root.parent / "legacy-v1-proof"
        state_root = root.parent / "legacy-v1-state"
        proof_root.mkdir(mode=0o700)
        state_root.mkdir(mode=0o700)
        owner = lease_owner(
            activity="session",
            run_id="legacy-v1-run",
            campaign_id="legacy-v1-campaign",
            goal_fingerprint="a" * 64,
            proof_root=proof_root,
            state_root=state_root,
        )
        process = {
            "pid": 4242,
            "start": "darwin:1:000001",
            "command": "historical-agent",
            "executable_path": "/usr/bin/true",
            "device": 1,
            "inode": 1,
        }
        common = {
            "schema_version": 1,
            "authority_id": puppet_authority.AUTHORITY_ID,
            "generation": 1,
            "session": "historical-v1-session",
            "target": "agy",
            "controller": "historical-controller",
            "owner": owner,
            "created_at": "2026-01-01T00:00:00Z",
        }
        journal = Journal(authority / "session-lease-history")
        projection = None
        for state in ("launching", "active", "failed"):
            projection = {
                **common,
                "state": state,
                "updated_at": "2026-01-01T00:00:0%sZ"
                % {"launching": 0, "active": 1, "failed": 2}[state],
                "process": None if state == "launching" else process,
            }
            journal.append(
                request_id="lease-1-%s" % state,
                event={"kind": "session_lease", "lease": projection},
            )
        atomic_write_json(authority / "current-session-lease.json", projection)

    def _fixture(
        self,
        root: Path,
        *,
        historical_v1_legacy_generation: bool = False,
    ) -> tuple[dict, SessionRegistry, dict]:
        if historical_v1_legacy_generation:
            self._seed_historical_v1_legacy_generation(self.authority_root)
        candidate = initialize_repo(
            root / "candidate",
            "codex/grok-dead-lease",
            "candidate",
        )
        session = "grok-dead-lease"
        files = controller_files(
            root,
            candidate=candidate,
            branch="codex/grok-dead-lease",
            session=session,
            task_profile="implementation",
            protocol_fingerprint="e" * 64,
        )
        launch(
            session=session,
            contract_path=files["contract"],
            manifest_path=files["manifest"],
            authorization_path=files["authorization"],
            proof_root=files["proof"],
            state_root=files["state"],
            supervisor_executable=files["supervisor_executable"],
            prompt="Remain available for exact halt.",
            require_subscription_profile=False,
            _allow_test_profile_bypass=True,
            _sleep_fn=lambda _interval: None,
            _execution_sleep_fn=lambda _interval: None,
        )
        registry = SessionRegistry(files["state"])
        record = registry.load(session)
        send_exact_sigint(record["process"])
        tmux = TmuxController(files["state"])
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            metadata = tmux.metadata(
                socket=Path(record["tmux"]["socket"]),
                session=session,
                pane=record["tmux"]["pane"],
                server_identity=record["tmux"]["server_identity"],
            )
            if metadata["pane_dead"]:
                break
            time.sleep(0.05)
        self.assertTrue(metadata["pane_dead"])

        transition_session_lease(
            session=session,
            target="codex",
            controller=record["controller"],
            owner=record["lease_owner"],
            instruction_manifest_sha256=record["instructions"]["manifest_sha256"],
            state="failed",
            process=record["process"],
            authority_root=self.authority_root,
        )
        bound_contract_path = Path(record["contract_path"])
        contract_raw = json.loads(bound_contract_path.read_text(encoding="utf-8"))
        contract_raw["target"] = "grok"
        contract = Contract.from_dict(contract_raw)
        atomic_write_json(bound_contract_path, contract_raw)
        registry.update(
            session,
            {
                "target": "grok",
                "contract_fingerprint": contract.fingerprint,
                "state": "BLOCKED",
                "blocker": {
                    "code": "launch_incomplete",
                    "target_process_alive": False,
                    "cleanup_stopped": True,
                    "cleanup_error": None,
                },
            },
        )
        record = registry.load(session)
        admit_session_lease(
            session=session,
            target="grok",
            controller=record["controller"],
            owner=record["lease_owner"],
            instruction_manifest_sha256=record["instructions"]["manifest_sha256"],
            authority_root=self.authority_root,
        )
        transition_session_lease(
            session=session,
            target="grok",
            controller=record["controller"],
            owner=record["lease_owner"],
            instruction_manifest_sha256=record["instructions"]["manifest_sha256"],
            state="active",
            process=record["process"],
            authority_root=self.authority_root,
        )
        transition_session_lease(
            session=session,
            target="grok",
            controller=record["controller"],
            owner=record["lease_owner"],
            instruction_manifest_sha256=record["instructions"]["manifest_sha256"],
            state="halting",
            process=record["process"],
            authority_root=self.authority_root,
        )

        supervisor = Path(record["supervisor"]["root"])
        (supervisor / "advanced.txt").write_text(
            "new supervisor source\n",
            encoding="utf-8",
        )
        commit_all(supervisor, "advance supervisor")
        return files, registry, record

    def test_reconciles_exact_dead_lease_without_relaxing_status_or_halt(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            files, registry, record = self._fixture(root)
            socket = record["tmux"]["socket"]
            try:
                registry_before = registry._path(record["session"]).read_bytes()
                proof_before = self._files_snapshot(files["proof"])
                authority_before = self._files_snapshot(self.authority_root)
                tmux_before = TmuxController(files["state"]).metadata_for_session(
                    socket=Path(socket),
                    session=record["session"],
                    server_identity=record["tmux"]["server_identity"],
                )

                for ordinary in (
                    lambda: status(
                        state_root=files["state"],
                        session=record["session"],
                    ),
                    lambda: halt(
                        state_root=files["state"],
                        session=record["session"],
                        timeout=0,
                    ),
                ):
                    with self.assertRaisesRegex(
                        IdentityError,
                        "supervisor commit changed",
                    ):
                        ordinary()
                self.assertEqual(
                    current_session_lease(
                        self.authority_root,
                        target="grok",
                    )["state"],
                    "halting",
                )
                self.assertEqual(
                    registry._path(record["session"]).read_bytes(),
                    registry_before,
                )

                preflight_authority = self._files_snapshot(self.authority_root)
                preflight_proof = self._files_snapshot(files["proof"])
                _dead_grok_lease_preflight(
                    state_root=files["state"],
                    session=record["session"],
                )
                self.assertEqual(
                    self._files_snapshot(self.authority_root),
                    preflight_authority,
                )
                self.assertEqual(
                    self._files_snapshot(files["proof"]),
                    preflight_proof,
                )
                self.assertEqual(
                    registry._path(record["session"]).read_bytes(),
                    registry_before,
                )

                result = reconcile_grok_dead_lease(
                    state_root=files["state"],
                    session=record["session"],
                )
                self.assertTrue(result["exact_lease_halted"])
                self.assertTrue(result["lease_transitioned"])
                self.assertTrue(result["exact_legacy_fence_halted"])
                self.assertTrue(result["legacy_fence_transitioned"])
                self.assertFalse(result["signal_sent"])
                self.assertFalse(result["attach_performed"])
                self.assertTrue(result["tmux_preserved"])
                self.assertTrue(result["historical_session_preserved"])
                self.assertEqual(
                    current_session_lease(
                        self.authority_root,
                        target="grok",
                    )["state"],
                    "halted",
                )
                legacy = puppet_authority._strict_legacy_session_lease_projection(
                    self.authority_root
                )
                self.assertEqual(legacy["session"], "target-fence-grok-1")
                self.assertEqual(legacy["state"], "halted")
                self.assertEqual(
                    registry._path(record["session"]).read_bytes(),
                    registry_before,
                )
                self.assertEqual(self._files_snapshot(files["proof"]), proof_before)
                self.assertEqual(
                    TmuxController(files["state"]).metadata_for_session(
                        socket=Path(socket),
                        session=record["session"],
                        server_identity=record["tmux"]["server_identity"],
                    ),
                    tmux_before,
                )
                authority_after = self._files_snapshot(self.authority_root)
                mutable = {
                    "current-session-lease.grok.json",
                    "current-session-lease.json",
                    "session-lease-history.grok/events.jsonl",
                    "session-lease-history.grok/journal-head.json",
                    "session-lease-history/events.jsonl",
                    "session-lease-history/journal-head.json",
                }
                self.assertEqual(
                    {
                        name: body
                        for name, body in authority_after.items()
                        if name not in mutable
                    },
                    {
                        name: body
                        for name, body in authority_before.items()
                        if name not in mutable
                    },
                )
            finally:
                kill_test_server(socket)

    def test_reconciles_with_a_closed_historical_v1_legacy_generation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            files, _, record = self._fixture(
                root,
                historical_v1_legacy_generation=True,
            )
            socket = record["tmux"]["socket"]
            try:
                before = Journal(
                    self.authority_root / "session-lease-history"
                ).read_only_snapshot()
                self.assertNotIn(
                    "identity_version",
                    before[1]["event"]["lease"]["process"],
                )
                result = reconcile_grok_dead_lease(
                    state_root=files["state"],
                    session=record["session"],
                )
                self.assertTrue(result["exact_lease_halted"])
                self.assertTrue(result["exact_legacy_fence_halted"])
                after = Journal(
                    self.authority_root / "session-lease-history"
                ).read_only_snapshot()
                self.assertEqual(after[:3], before[:3])
                self.assertEqual(
                    puppet_authority._strict_legacy_session_lease_projection(
                        self.authority_root
                    )["state"],
                    "halted",
                )
            finally:
                kill_test_server(socket)

    def test_replay_of_the_same_halted_generation_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            files, registry, record = self._fixture(root)
            socket = record["tmux"]["socket"]
            try:
                first = reconcile_grok_dead_lease(
                    state_root=files["state"],
                    session=record["session"],
                )
                after_first = self._files_snapshot(self.authority_root)
                registry_after_first = registry._path(record["session"]).read_bytes()
                second = reconcile_grok_dead_lease(
                    state_root=files["state"],
                    session=record["session"],
                )
                self.assertTrue(first["lease_transitioned"])
                self.assertTrue(first["legacy_fence_transitioned"])
                self.assertFalse(second["lease_transitioned"])
                self.assertFalse(second["legacy_fence_transitioned"])
                self.assertEqual(
                    second["lease_generation"],
                    first["lease_generation"],
                )
                self.assertTrue(second["exact_lease_halted"])
                self.assertTrue(second["exact_legacy_fence_halted"])
                self.assertEqual(
                    self._files_snapshot(self.authority_root),
                    after_first,
                )
                self.assertEqual(
                    registry._path(record["session"]).read_bytes(),
                    registry_after_first,
                )
            finally:
                kill_test_server(socket)

    def test_synchronizes_an_exact_legacy_fence_left_halting(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            files, registry, record = self._fixture(root)
            socket = record["tmux"]["socket"]
            try:
                target = strict_session_lease_projection(
                    self.authority_root,
                    target="grok",
                )
                puppet_authority._append_lease(
                    self.authority_root,
                    dict(target, state="halted"),
                    target="grok",
                )
                target_before = {
                    name: body
                    for name, body in self._files_snapshot(
                        self.authority_root
                    ).items()
                    if name == "current-session-lease.grok.json"
                    or name.startswith("session-lease-history.grok/")
                }
                registry_before = registry._path(record["session"]).read_bytes()

                result = reconcile_grok_dead_lease(
                    state_root=files["state"],
                    session=record["session"],
                )

                self.assertFalse(result["lease_transitioned"])
                self.assertTrue(result["legacy_fence_transitioned"])
                self.assertTrue(result["exact_lease_halted"])
                self.assertTrue(result["exact_legacy_fence_halted"])
                self.assertEqual(
                    {
                        name: body
                        for name, body in self._files_snapshot(
                            self.authority_root
                        ).items()
                        if name == "current-session-lease.grok.json"
                        or name.startswith("session-lease-history.grok/")
                    },
                    target_before,
                )
                self.assertEqual(
                    puppet_authority._strict_legacy_session_lease_projection(
                        self.authority_root
                    )["state"],
                    "halted",
                )
                self.assertEqual(
                    registry._path(record["session"]).read_bytes(),
                    registry_before,
                )
            finally:
                kill_test_server(socket)

    def test_refuses_a_later_grok_generation_without_changing_it(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            files, registry, record = self._fixture(root)
            socket = record["tmux"]["socket"]
            try:
                transition_session_lease(
                    session=record["session"],
                    target="grok",
                    controller=record["controller"],
                    owner=record["lease_owner"],
                    instruction_manifest_sha256=record["instructions"][
                        "manifest_sha256"
                    ],
                    state="halted",
                    process=record["process"],
                    authority_root=self.authority_root,
                )
                later_proof = root / "later-proof"
                later_state = root / "later-state"
                later_proof.mkdir(mode=0o700)
                later_state.mkdir(mode=0o700)
                later_owner = lease_owner(
                    activity="session",
                    run_id="later-grok-run",
                    campaign_id="campaign-test",
                    goal_fingerprint="a" * 64,
                    proof_root=later_proof,
                    state_root=later_state,
                )
                later = admit_session_lease(
                    session="later-grok-session",
                    target="grok",
                    controller="tester",
                    owner=later_owner,
                    instruction_manifest_sha256="f" * 64,
                    authority_root=self.authority_root,
                )
                before = self._files_snapshot(self.authority_root)
                with self.assertRaisesRegex(
                    IdentityError,
                    "controller session lease identity mismatch",
                ):
                    reconcile_grok_dead_lease(
                        state_root=files["state"],
                        session=record["session"],
                    )
                self.assertEqual(
                    strict_session_lease_projection(
                        self.authority_root,
                        target="grok",
                    ),
                    later,
                )
                self.assertEqual(self._files_snapshot(self.authority_root), before)
                self.assertEqual(registry.load(record["session"])["state"], "BLOCKED")
            finally:
                kill_test_server(socket)

    def test_refuses_later_or_unrelated_legacy_fence_without_changes(self):
        for boundary in ("later anchor", "unrelated anchor"):
            with (
                self.subTest(boundary=boundary),
                tempfile.TemporaryDirectory() as temporary,
                tempfile.TemporaryDirectory() as authority_temporary,
            ):
                root = Path(temporary).resolve()
                prior_authority_root = self.authority_root
                self.authority_root = (
                    Path(authority_temporary).resolve() / "authority"
                )
                authority_override = patch(
                    "puppet_lib.authority.canonical_authority_root",
                    return_value=self.authority_root,
                )
                authority_override.start()
                socket = None
                try:
                    files, registry, record = self._fixture(root)
                    socket = record["tmux"]["socket"]
                    legacy = puppet_authority._strict_legacy_session_lease_projection(
                        self.authority_root
                    )
                    terminal = puppet_authority._append_lease(
                        self.authority_root,
                        dict(legacy, state="failed"),
                    )
                    next_generation = dict(
                        terminal,
                        generation=terminal["generation"] + 1,
                        session=(
                            "target-fence-grok-2"
                            if boundary == "later anchor"
                            else "unrelated-legacy-session"
                        ),
                        target=(
                            "grok"
                            if boundary == "later anchor"
                            else "codex"
                        ),
                        controller=(
                            terminal["controller"]
                            if boundary == "later anchor"
                            else "unrelated-controller"
                        ),
                        state="launching",
                        created_at="2026-07-27T00:00:00Z",
                        updated_at="2026-07-27T00:00:00Z",
                        process=None,
                    )
                    puppet_authority._append_lease(
                        self.authority_root,
                        next_generation,
                    )
                    self.assertEqual(
                        puppet_authority._strict_legacy_session_lease_projection(
                            self.authority_root
                        ),
                        next_generation,
                    )
                    authority_before = self._files_snapshot(self.authority_root)
                    registry_before = registry._path(
                        record["session"]
                    ).read_bytes()

                    with self.assertRaisesRegex(
                        IdentityError,
                        "legacy compatibility fence identity mismatch",
                    ):
                        reconcile_grok_dead_lease(
                            state_root=files["state"],
                            session=record["session"],
                        )

                    self.assertEqual(
                        self._files_snapshot(self.authority_root),
                        authority_before,
                    )
                    self.assertEqual(
                        registry._path(record["session"]).read_bytes(),
                        registry_before,
                    )
                finally:
                    kill_test_server(socket)
                    authority_override.stop()
                    self.authority_root = prior_authority_root

    def test_preflight_refuses_each_distinct_registry_and_lease_mismatch(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            files, _registry, record = self._fixture(root)
            socket = record["tmux"]["socket"]
            try:
                lease = strict_session_lease_projection(
                    self.authority_root,
                    target="grok",
                )
                authority_before = self._files_snapshot(self.authority_root)

                registry_cases = {
                    "session": dict(record, session="different-session"),
                    "unrelated target": dict(record, target="codex"),
                    "registry state": dict(record, state="FAILED"),
                    "blocker code": dict(
                        record,
                        blocker=dict(record["blocker"], code="operator_blocked"),
                    ),
                    "target liveness claim": dict(
                        record,
                        blocker=dict(
                            record["blocker"],
                            target_process_alive=None,
                        ),
                    ),
                    "cleanup result": dict(
                        record,
                        blocker=dict(record["blocker"], cleanup_stopped=False),
                    ),
                }
                for label, changed in registry_cases.items():
                    with (
                        self.subTest(boundary=label),
                        patch.object(SessionRegistry, "load", return_value=changed),
                        self.assertRaises((IdentityError, ValidationError)),
                    ):
                        _dead_grok_lease_preflight(
                            state_root=files["state"],
                            session=record["session"],
                        )

                lease_cases = {
                    "controller": dict(lease, controller="different-controller"),
                    "owner": dict(
                        lease,
                        owner=dict(lease["owner"], run_id="different-run"),
                    ),
                    "instruction": dict(
                        lease,
                        instruction_manifest_sha256="0" * 64,
                    ),
                    "process": dict(
                        lease,
                        process=dict(
                            lease["process"],
                            kernel_birth_id="different-birth",
                        ),
                    ),
                    "state": dict(lease, state="active"),
                }
                for label, changed in lease_cases.items():
                    with (
                        self.subTest(boundary=label),
                        patch.object(
                            puppet_session,
                            "strict_session_lease_projection",
                            return_value=changed,
                        ),
                        self.assertRaisesRegex(
                            IdentityError,
                            "lease identity mismatch",
                        ),
                    ):
                        _dead_grok_lease_preflight(
                            state_root=files["state"],
                            session=record["session"],
                        )
                self.assertEqual(
                    self._files_snapshot(self.authority_root),
                    authority_before,
                )

                later_generation = dict(
                    lease,
                    generation=lease["generation"] + 1,
                )
                with (
                    patch.object(
                        puppet_session,
                        "strict_session_lease_projection",
                        side_effect=[lease, later_generation],
                    ),
                    self.assertRaisesRegex(
                        IdentityError,
                        "lease identity mismatch",
                    ),
                ):
                    reconcile_grok_dead_lease(
                        state_root=files["state"],
                        session=record["session"],
                    )
                self.assertEqual(
                    self._files_snapshot(self.authority_root),
                    authority_before,
                )
            finally:
                kill_test_server(socket)

    def test_refuses_each_legacy_fence_identity_mismatch_without_changes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            files, registry, record = self._fixture(root)
            socket = record["tmux"]["socket"]
            try:
                legacy = puppet_authority._strict_legacy_session_lease_projection(
                    self.authority_root
                )
                authority_before = self._files_snapshot(self.authority_root)
                registry_before = registry._path(record["session"]).read_bytes()
                mismatches = {
                    "anchor": dict(
                        legacy,
                        session="target-fence-grok-2",
                    ),
                    "owner": dict(
                        legacy,
                        owner=dict(
                            legacy["owner"],
                            run_id="different-run",
                        ),
                    ),
                    "process": dict(
                        legacy,
                        process=dict(
                            legacy["process"],
                            kernel_birth_id="different-birth",
                        ),
                    ),
                    "state ahead": dict(legacy, state="halted"),
                    "schema": dict(
                        legacy,
                        schema_version=2,
                        instruction_manifest_sha256="0" * 64,
                    ),
                }
                for boundary, changed in mismatches.items():
                    with (
                        self.subTest(boundary=boundary),
                        patch.object(
                            puppet_authority,
                            "_strict_legacy_session_lease_projection",
                            return_value=changed,
                        ),
                        self.assertRaisesRegex(
                            IdentityError,
                            "legacy compatibility fence identity mismatch",
                        ),
                    ):
                        reconcile_grok_dead_lease(
                            state_root=files["state"],
                            session=record["session"],
                        )
                    self.assertEqual(
                        self._files_snapshot(self.authority_root),
                        authority_before,
                    )
                    self.assertEqual(
                        registry._path(record["session"]).read_bytes(),
                        registry_before,
                    )
            finally:
                kill_test_server(socket)

    def test_preflight_refuses_process_and_tmux_ambiguity_without_side_effects(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            files, registry, record = self._fixture(root)
            socket = record["tmux"]["socket"]
            try:
                authority_before = self._files_snapshot(self.authority_root)
                registry_before = registry._path(record["session"]).read_bytes()

                with (
                    patch.object(
                        puppet_session,
                        "_prove_recorded_process_birth_gone",
                        side_effect=IdentityError("ambiguous process"),
                    ),
                    self.assertRaisesRegex(IdentityError, "ambiguous process"),
                ):
                    _dead_grok_lease_preflight(
                        state_root=files["state"],
                        session=record["session"],
                    )

                tmux_failures = (
                    (
                        "binary",
                        "assert_tmux_binary_identity",
                        IdentityError("binary drift"),
                    ),
                    (
                        "server",
                        "bind_server_identity",
                        IdentityError("server drift"),
                    ),
                    (
                        "missing session",
                        "metadata_for_session",
                        IdentityError("session unavailable"),
                    ),
                )
                for label, method, failure in tmux_failures:
                    with (
                        self.subTest(boundary=label),
                        patch.object(
                            TmuxController,
                            method,
                            side_effect=failure,
                        ),
                        self.assertRaises(IdentityError),
                    ):
                        _dead_grok_lease_preflight(
                            state_root=files["state"],
                            session=record["session"],
                        )

                socket_identity = dict(record["tmux"]["socket_identity"])
                socket_identity["inode"] += 1
                with (
                    patch.object(
                        TmuxController,
                        "socket_identity",
                        return_value=socket_identity,
                    ),
                    self.assertRaisesRegex(IdentityError, "socket identity"),
                ):
                    _dead_grok_lease_preflight(
                        state_root=files["state"],
                        session=record["session"],
                    )

                metadata = TmuxController(files["state"]).metadata_for_session(
                    socket=Path(socket),
                    session=record["session"],
                    server_identity=record["tmux"]["server_identity"],
                )
                metadata_cases = {
                    "live pane": dict(metadata, pane_dead=False),
                    "replaced pane": dict(metadata, pane="%999"),
                    "pane owner": dict(metadata, pane_pid=metadata["pane_pid"] + 1),
                    "different session": dict(metadata, session="different-session"),
                }
                for label, changed in metadata_cases.items():
                    with (
                        self.subTest(boundary=label),
                        patch.object(
                            TmuxController,
                            "metadata_for_session",
                            return_value=changed,
                        ),
                        self.assertRaisesRegex(IdentityError, "dead-pane identity"),
                    ):
                        _dead_grok_lease_preflight(
                            state_root=files["state"],
                            session=record["session"],
                        )

                self.assertEqual(
                    self._files_snapshot(self.authority_root),
                    authority_before,
                )
                self.assertEqual(
                    registry._path(record["session"]).read_bytes(),
                    registry_before,
                )
            finally:
                kill_test_server(socket)

    def test_process_birth_proof_rejects_live_and_ambiguous_samples(self):
        process = {
            "identity_version": 2,
            "pid": 4242,
            "start": "stable",
            "kernel_birth_id": "test:4242",
            "command": "grok",
            "executable_path": "/opt/grok",
            "device": 1,
            "inode": 2,
        }
        with (
            patch("puppet_lib.session.os.kill", return_value=None),
            patch(
                "puppet_lib.session.process_birth_identity",
                return_value=process,
            ),
            self.assertRaisesRegex(IdentityError, "still alive"),
        ):
            _prove_recorded_process_birth_gone(process)
        with (
            patch("puppet_lib.session.os.kill", return_value=None),
            patch(
                "puppet_lib.session.process_birth_identity",
                side_effect=IdentityError("sample failed"),
            ),
            self.assertRaisesRegex(IdentityError, "ambiguous"),
        ):
            _prove_recorded_process_birth_gone(process)
        with patch(
            "puppet_lib.session.os.kill",
            side_effect=ProcessLookupError(),
        ):
            _prove_recorded_process_birth_gone(process)
        with (
            patch("puppet_lib.session.os.kill", return_value=None),
            patch(
                "puppet_lib.session.process_birth_identity",
                return_value=dict(process, kernel_birth_id="test:replacement"),
            ),
        ):
            _prove_recorded_process_birth_gone(process)

    def test_rejects_projection_and_journal_mismatches_read_only(self):
        corruptions = (
            ("target", "projection divergence"),
            ("target", "noncanonical history"),
            ("legacy", "projection divergence"),
            ("legacy", "noncanonical history"),
        )
        for surface, corruption in corruptions:
            with (
                self.subTest(surface=surface, corruption=corruption),
                tempfile.TemporaryDirectory() as temporary,
                tempfile.TemporaryDirectory() as authority_temporary,
            ):
                root = Path(temporary).resolve()
                prior_authority_root = self.authority_root
                self.authority_root = (
                    Path(authority_temporary).resolve() / "authority"
                )
                authority_override = patch(
                    "puppet_lib.authority.canonical_authority_root",
                    return_value=self.authority_root,
                )
                authority_override.start()
                socket = None
                try:
                    files, registry, record = self._fixture(root)
                    socket = record["tmux"]["socket"]
                    projection_path = (
                        self.authority_root
                        / (
                            "current-session-lease.grok.json"
                            if surface == "target"
                            else "current-session-lease.json"
                        )
                    )
                    lease = (
                        strict_session_lease_projection(
                            self.authority_root,
                            target="grok",
                        )
                        if surface == "target"
                        else puppet_authority._strict_legacy_session_lease_projection(
                            self.authority_root
                        )
                    )
                    if corruption == "projection divergence":
                        atomic_write_json(
                            projection_path,
                            dict(
                                lease,
                                updated_at="2026-07-27T00:00:00Z",
                            ),
                        )
                    else:
                        invalid = dict(
                            lease,
                            generation=lease["generation"] + 1,
                            state="launching",
                            created_at="2026-07-27T00:00:00Z",
                            updated_at="2026-07-27T00:00:00Z",
                            process=None,
                        )
                        Journal(
                            self.authority_root
                            / (
                                "session-lease-history.grok"
                                if surface == "target"
                                else "session-lease-history"
                            )
                        ).append(
                            request_id="lease-%d-launching"
                            % invalid["generation"],
                            event={"kind": "session_lease", "lease": invalid},
                        )
                        atomic_write_json(projection_path, invalid)
                    authority_before = self._files_snapshot(self.authority_root)
                    registry_before = registry._path(record["session"]).read_bytes()
                    with self.assertRaisesRegex(
                        IdentityError,
                        "not canonical|projection diverged",
                    ):
                        reconcile_grok_dead_lease(
                            state_root=files["state"],
                            session=record["session"],
                        )
                    self.assertEqual(
                        self._files_snapshot(self.authority_root),
                        authority_before,
                    )
                    self.assertEqual(
                        registry._path(record["session"]).read_bytes(),
                        registry_before,
                    )
                finally:
                    kill_test_server(socket)
                    authority_override.stop()
                    self.authority_root = prior_authority_root
