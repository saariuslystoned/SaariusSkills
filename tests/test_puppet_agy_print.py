from __future__ import annotations

import inspect
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "puppet" / "scripts"
TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(TESTS))

from puppet_lib.agy_print import (
    AgyPrintController,
    caller_fields_from_observation,
    fixture_observation,
    prove_agy_print_observation,
    prove_observed_model,
    prove_process_tree,
    prove_resume_identity,
    prove_shutdown,
    prove_terminal_result,
    prove_workspace_binding,
)
from puppet_lib.caller import make_blocker
from puppet_lib.errors import IdentityError, UnsupportedError
from puppet_lib.operator_plan import compile_operator_plan
from puppet_lib.registry import SessionRegistry
from puppet_lib.session import (
    _agy_print_structured_launch,
    _caller_blockers_from_details,
    _runtime,
    doctor,
    launch,
)
from test_puppet_session import controller_files, initialize_repo
from puppet_lib.tmux import TmuxController
from puppet_lib.transport import (
    bind_run_transport,
    open_run_transport,
    transport_capability_table,
    transport_is_available,
    transport_unavailable_detail,
)


def _workspace(**overrides):
    workspace = {
        "path": "/tmp/agy-print-workspace",
        "branch": "codex/example",
        "head": "a" * 40,
        "tree": "b" * 40,
    }
    workspace.update(overrides)
    return workspace


class AgyPrintTransportTests(unittest.TestCase):
    def test_success_proves_model_workspace_session_and_process(self):
        observation = fixture_observation()
        proved = prove_agy_print_observation(
            observation,
            expected_session="agy-print-session",
            expected_conversation_id="conv-agy-print-1",
            expected_workspace=_workspace(),
            requested_model="gemini-3.7-flash-high",
        )
        self.assertEqual(proved["transport"], "agy-print")
        self.assertEqual(proved["model"]["observed_model"], "gemini-3.7-flash-high")
        self.assertEqual(proved["model"]["source"], "process_metadata")
        self.assertEqual(proved["workspace"]["path"], "/tmp/agy-print-workspace")
        self.assertEqual(proved["resume"]["conversation_id"], "conv-agy-print-1")
        self.assertEqual(proved["process"]["pid"], 4242)
        self.assertFalse(proved["live_agy_claimed"])
        self.assertEqual(prove_terminal_result(observation)["state"], "completed")
        fields = caller_fields_from_observation(observation)
        self.assertEqual(fields["transport"]["id"], "agy-print")
        self.assertEqual(fields["caller_outcome"]["worker_completion"], "none")
        self.assertEqual(fields["caller_outcome"]["controller_acceptance"], "none")
        self.assertEqual(fields["caller_outcome"]["halt"], "none")
        self.assertIsNone(fields["final_outcome"])

    def test_stage2_outcomes_stay_distinct_on_agy_print(self):
        accepted = fixture_observation(
            last_checkpoint={"checkpoint_id": "c" * 64},
            last_beacon={"sequence": 3},
            last_validated_at="2026-09-18T00:00:00Z",
            record_state="ACCEPTED",
        )
        accepted_fields = caller_fields_from_observation(accepted)
        self.assertEqual(accepted_fields["caller_outcome"]["worker_completion"], "reported")
        self.assertEqual(accepted_fields["caller_outcome"]["controller_acceptance"], "accepted")
        self.assertEqual(accepted_fields["caller_outcome"]["halt"], "none")
        self.assertIn("controller accepted", accepted_fields["final_outcome"]["summary"])
        halted = fixture_observation(
            terminal_state="halted",
            record_state="HALTED",
            halt={
                "pid": 4242,
                "kernel_birth_id": "darwin:100:00004242",
                "pid_gone": True,
                "signaled_pids": [4242],
            },
        )
        halted_fields = caller_fields_from_observation(halted, halt_confirmed=True)
        self.assertEqual(halted_fields["caller_outcome"]["halt"], "confirmed")
        self.assertEqual(halted_fields["caller_outcome"]["controller_acceptance"], "none")
        self.assertEqual(halted_fields["final_outcome"]["process"]["pid"], 4242)

    def test_selector_only_and_mismatched_model_are_rejected(self):
        selector_only = fixture_observation()
        selector_only["observed_model"] = {
            "id": "gemini-3.7-flash-high",
            "source": "selector",
        }
        with self.assertRaisesRegex(IdentityError, "requested selector"):
            prove_observed_model(selector_only)
        missing_runtime = fixture_observation(
            observed_model="gemini-3.7-flash-high",
            command="agy --print",
        )
        with self.assertRaisesRegex(IdentityError, "missing from runtime"):
            prove_observed_model(missing_runtime)
        mismatched = fixture_observation(observed_model="other-model")
        with self.assertRaisesRegex(IdentityError, "does not match"):
            prove_observed_model(
                mismatched, requested_model="gemini-3.7-flash-high"
            )
        session_source = fixture_observation(
            observed_source="session_metadata",
            session="sess-gemini-3.7-flash-high",
            command="agy --print",
        )
        proved = prove_observed_model(session_source)
        self.assertEqual(proved["source"], "session_metadata")
        runtime_source = fixture_observation(observed_source="runtime_metadata")
        self.assertEqual(
            prove_observed_model(runtime_source)["source"], "runtime_metadata"
        )

    def test_workspace_session_and_process_identity_failures(self):
        observation = fixture_observation()
        with self.assertRaisesRegex(IdentityError, "workspace identity"):
            prove_workspace_binding(
                observation,
                expected_workspace=_workspace(path="/other/workspace"),
            )
        with self.assertRaisesRegex(IdentityError, "session and conversation"):
            prove_resume_identity(
                observation,
                expected_session="agy-print-session",
                expected_conversation_id="conv-other",
            )
        with self.assertRaisesRegex(IdentityError, "session and conversation"):
            prove_resume_identity(
                observation,
                expected_session="other-session",
                expected_conversation_id="conv-agy-print-1",
            )
        with self.assertRaisesRegex(IdentityError, "process identity"):
            prove_process_tree(
                observation,
                expected_process={"pid": 99, "kernel_birth_id": "darwin:100:00004242"},
            )
        with self.assertRaisesRegex(IdentityError, "process identity"):
            prove_process_tree(
                observation,
                expected_process={
                    "pid": 4242,
                    "kernel_birth_id": "darwin:1:stale",
                },
            )

    def test_shutdown_rejects_unowned_and_missing_halt(self):
        observation = fixture_observation()
        expected = {"pid": 4242, "kernel_birth_id": "darwin:100:00004242"}
        with self.assertRaisesRegex(IdentityError, "halt proof is missing"):
            prove_shutdown(observation, expected_process=expected)
        broadened = fixture_observation(
            halt={
                "pid": 4242,
                "kernel_birth_id": "darwin:100:00004242",
                "pid_gone": True,
                "signaled_pids": [4242, 9999],
            }
        )
        with self.assertRaisesRegex(IdentityError, "not confined"):
            prove_shutdown(broadened, expected_process=expected)
        owned = fixture_observation(
            halt={
                "pid": 4242,
                "kernel_birth_id": "darwin:100:00004242",
                "pid_gone": True,
                "signaled_pids": [4242],
            }
        )
        proof = prove_shutdown(owned, expected_process=expected)
        self.assertEqual(proof["pid"], 4242)
        self.assertTrue(proof["pid_gone"])

    def test_unavailable_observer_is_a_body_safe_blocker(self):
        with tempfile.TemporaryDirectory() as temporary:
            controller = AgyPrintController(Path(temporary))
            with self.assertRaises(UnsupportedError) as raised:
                controller.require_observation()
            payload = raised.exception.as_dict()
            self.assertEqual(payload["blocker"]["code"], "transport_unavailable")
            self.assertIn("no fallback", payload["blocker"]["remedy"])
            self.assertNotIn("\n", payload["blocker"]["changed"])

    def test_no_fallback_when_agy_print_is_requested(self):
        binding = bind_run_transport("agy-print")
        self.assertEqual(binding["id"], "agy-print")
        self.assertNotEqual(binding["id"], "tmux")
        with mock.patch.object(AgyPrintController, "available", return_value=False):
            self.assertFalse(AgyPrintController.available())
            self.assertFalse(transport_is_available("agy-print"))
        self.assertEqual(
            transport_unavailable_detail("agy-print"),
            "agy-print transport is unavailable",
        )
        blockers = _caller_blockers_from_details(["agy-print transport is unavailable"])
        self.assertEqual(blockers[0]["code"], "transport_unavailable")
        self.assertIn("no fallback", blockers[0]["remedy"])
        with mock.patch.object(TmuxController, "__init__", side_effect=AssertionError("tmux")):
            with tempfile.TemporaryDirectory() as temporary:
                controller = open_run_transport(binding, Path(temporary))
        self.assertIsInstance(controller, AgyPrintController)
        table = transport_capability_table()
        self.assertEqual(table["agy-print"]["implementation"], "implemented")
        self.assertEqual(table["herdr"]["implementation"], "unsupported")

    def test_structured_launch_uses_fixture_and_never_opens_tmux(self):
        observation = fixture_observation()
        contract = mock.Mock()
        contract.repo = Path("/tmp/agy-print-workspace")
        contract.requested_model = "gemini-3.7-flash-high"
        contract.target = "agy"
        with mock.patch(
            "puppet_lib.session._workspace_snapshot",
            return_value={
                "branch": "codex/example",
                "head": "a" * 40,
                "tree": "b" * 40,
                "dirty": False,
            },
        ), mock.patch.object(
            TmuxController, "__init__", side_effect=AssertionError("tmux fallback")
        ):
            with tempfile.TemporaryDirectory() as temporary:
                result = _agy_print_structured_launch(
                    session="agy-print-session",
                    contract=contract,
                    transport=bind_run_transport("agy-print"),
                    state_root=Path(temporary),
                    requested_model="gemini-3.7-flash-high",
                    observer=observation,
                )
        self.assertTrue(result["ok"])
        self.assertFalse(result["live_agy_claimed"])
        self.assertEqual(result["transport"]["id"], "agy-print")
        self.assertEqual(result["agy_print"]["model"]["observed_model"], "gemini-3.7-flash-high")
        self.assertEqual(result["lifecycle"]["schema"], "puppet.agy-print-lifecycle/v1")
        self.assertFalse(result["lifecycle"]["live_agy_claimed"])
        self.assertEqual(
            result["lifecycle"]["phase_order"],
            [
                "start_bound",
                "resume_matched",
                "terminal_result",
                "worker_completion",
                "controller_acceptance",
                "confirmed_halt",
                "final_outcome",
            ],
        )
        self.assertIsNone(result["lifecycle"]["phases"]["confirmed_halt"])
        self.assertFalse(result["live_agy_claimed"])
        self.assertFalse(result.get("process_backed"))

    def test_structured_launch_without_observer_does_not_fall_back(self):
        contract = mock.Mock()
        contract.repo = Path("/tmp/agy-print-workspace")
        contract.requested_model = None
        contract.target = "agy"
        with mock.patch(
            "puppet_lib.session._workspace_snapshot",
            return_value={
                "branch": "codex/example",
                "head": "a" * 40,
                "tree": "b" * 40,
                "dirty": False,
            },
        ), mock.patch.object(
            TmuxController, "__init__", side_effect=AssertionError("tmux fallback")
        ):
            with tempfile.TemporaryDirectory() as temporary:
                with self.assertRaises(UnsupportedError) as raised:
                    _agy_print_structured_launch(
                        session="agy-print-session",
                        contract=contract,
                        transport=bind_run_transport("agy-print"),
                        state_root=Path(temporary),
                        requested_model=None,
                    )
        self.assertEqual(raised.exception.as_dict()["blocker"]["code"], "transport_unavailable")

    def test_doctor_reports_agy_print_unavailable_without_tmux_fallback(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            candidate = initialize_repo(
                root / "candidate", "codex/agy-print-doctor", "candidate"
            )
            files = controller_files(
                root,
                candidate=candidate,
                branch="codex/agy-print-doctor",
                session="agy-print-doctor",
                task_profile="implementation",
                protocol_fingerprint="e" * 64,
            )
            with mock.patch.object(TmuxController, "__init__", side_effect=AssertionError("tmux")), mock.patch.object(
                AgyPrintController, "available", return_value=False
            ):
                report = doctor(
                    contract_path=files["contract"],
                    manifest_path=files["manifest"],
                    authorization_path=files["authorization"],
                    proof_root=files["proof"],
                    state_root=files["state"],
                    require_subscription_profile=False,
                    requested_transport="agy-print",
                )
            self.assertEqual(report["transport"]["id"], "agy-print")
            self.assertIn("agy-print transport is unavailable", report["blockers"])
            self.assertNotIn("tmux is unavailable", report["blockers"])
            self.assertTrue(
                any(
                    item["code"] == "transport_unavailable"
                    for item in report["caller_blockers"]
                )
            )
            self.assertEqual(
                report["transport_capabilities"]["agy-print"]["implementation"],
                "implemented",
            )
            self.assertFalse(report["launch_ready"])

    def test_tmux_capability_and_default_binding_are_preserved(self):
        self.assertEqual(bind_run_transport()["id"], "tmux")
        table = transport_capability_table()
        self.assertEqual(table["tmux"]["implementation"], "implemented")
        self.assertEqual(table["tmux"]["status_proves"], "pane_and_process_identity")
        self.assertEqual(table["tmux"]["resume_proves"], "unsupported")
        self.assertEqual(
            make_blocker(code="tmux_unavailable", detail="tmux is unavailable")[
                "remedy"
            ].startswith("install tmux"),
            True,
        )
        self.assertEqual(transport_unavailable_detail("tmux"), "tmux is unavailable")

    def test_registered_agy_print_session_does_not_open_tmux_runtime(self):
        record = {
            "transport": bind_run_transport("agy-print"),
            "session": "agy-print-session",
        }
        with tempfile.TemporaryDirectory() as temporary:
            with mock.patch.object(
                TmuxController, "__init__", side_effect=AssertionError("tmux")
            ):
                with self.assertRaisesRegex(IdentityError, "is not tmux"):
                    _runtime(
                        SessionRegistry(Path(temporary)),
                        record,
                        "status",
                        require_process=False,
                    )

    def test_public_launch_agy_print_stays_blocked_without_tmux(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            candidate = initialize_repo(
                root / "candidate", "codex/agy-print-launch", "candidate"
            )
            files = controller_files(
                root,
                candidate=candidate,
                branch="codex/agy-print-launch",
                session="agy-print-launch",
                task_profile="implementation",
                protocol_fingerprint="e" * 64,
            )
            with mock.patch.object(
                TmuxController, "__init__", side_effect=AssertionError("tmux")
            ):
                with self.assertRaisesRegex(UnsupportedError, "preflight is blocked"):
                    launch(
                        session="agy-print-launch",
                        contract_path=files["contract"],
                        manifest_path=files["manifest"],
                        authorization_path=files["authorization"],
                        proof_root=files["proof"],
                        state_root=files["state"],
                        supervisor_executable=files["supervisor_executable"],
                        prompt="fixture only",
                        require_subscription_profile=False,
                        requested_transport="agy-print",
                    )

    def test_operator_plan_field_set_stays_frozen(self):
        params = inspect.signature(compile_operator_plan).parameters
        self.assertNotIn("transport", params)
        self.assertNotIn("requested_transport", params)
        source = inspect.getsource(compile_operator_plan)
        self.assertNotIn('result["transport"]', source)
        self.assertNotIn("'transport':", source.split("result: Dict[str, Any] = {", 1)[1])
