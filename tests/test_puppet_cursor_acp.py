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

from puppet_lib.agy_print import AgyPrintController
from puppet_lib.caller import make_blocker
from puppet_lib.cursor_acp import (
    CursorAcpController,
    CursorAcpRunnerFixture,
    caller_fields_from_observation,
    fixture_observation,
    prove_cursor_acp_observation,
    prove_observed_model,
    prove_resume_identity,
    prove_shutdown,
    prove_terminal_result,
    prove_workspace_binding,
    qualify_cursor_acp_lifecycle,
    require_cursor_acp_target,
)
from puppet_lib.errors import IdentityError, UnsupportedError
from puppet_lib.operator_plan import compile_operator_plan
from puppet_lib.registry import SessionRegistry
from puppet_lib.session import (
    _caller_blockers_from_details,
    _cursor_acp_structured_launch,
    _runtime,
    doctor,
    launch,
)
from puppet_lib.tmux import TmuxController
from puppet_lib.transport import (
    bind_run_transport,
    open_run_transport,
    transport_capability_table,
    transport_is_available,
    transport_unavailable_detail,
)
from test_puppet_session import controller_files, initialize_repo


def _workspace(**overrides):
    workspace = {
        "path": "/tmp/cursor-acp-workspace",
        "branch": "codex/example",
        "head": "a" * 40,
        "tree": "b" * 40,
    }
    workspace.update(overrides)
    return workspace


class CursorAcpTransportTests(unittest.TestCase):
    def test_success_proves_model_workspace_session_and_result(self):
        observation = fixture_observation()
        proved = prove_cursor_acp_observation(
            observation,
            expected_session="cursor-acp-session",
            expected_conversation_id="conv-cursor-acp-1",
            expected_workspace=_workspace(),
            requested_model="cursor-grok-4.6-high",
            expected_observed_model="grok-4.6[effort=high,fast=true]",
            expected_result_state="completed",
            expected_result_id="acp-result-1",
        )
        self.assertEqual(proved["transport"], "cursor-acp")
        self.assertEqual(proved["target"], "cursor")
        self.assertEqual(
            proved["model"]["observed_model"],
            "grok-4.6[effort=high,fast=true]",
        )
        self.assertEqual(proved["model"]["source"], "runtime_metadata")
        self.assertEqual(proved["model"]["requested_model"], "cursor-grok-4.6-high")
        self.assertEqual(proved["workspace"]["path"], "/tmp/cursor-acp-workspace")
        self.assertEqual(proved["workspace"]["branch"], "codex/example")
        self.assertEqual(proved["workspace"]["head"], "a" * 40)
        self.assertEqual(proved["workspace"]["tree"], "b" * 40)
        self.assertEqual(proved["resume"]["conversation_id"], "conv-cursor-acp-1")
        self.assertEqual(proved["terminal_result"]["state"], "completed")
        self.assertEqual(proved["terminal_result"]["result_id"], "acp-result-1")
        self.assertFalse(proved["live_cursor_acp_claimed"])
        fields = caller_fields_from_observation(observation)
        self.assertEqual(fields["transport"]["id"], "cursor-acp")
        self.assertEqual(fields["caller_outcome"]["worker_completion"], "none")
        self.assertEqual(fields["caller_outcome"]["controller_acceptance"], "none")
        self.assertEqual(fields["caller_outcome"]["halt"], "none")
        self.assertIsNone(fields["final_outcome"])

    def test_stage2_outcomes_stay_distinct_on_cursor_acp(self):
        accepted = fixture_observation(
            last_checkpoint={"checkpoint_id": "c" * 64},
            last_beacon={"sequence": 3},
            last_validated_at="2026-09-18T00:00:00Z",
            record_state="ACCEPTED",
        )
        accepted_fields = caller_fields_from_observation(accepted)
        self.assertEqual(accepted_fields["caller_outcome"]["worker_completion"], "reported")
        self.assertEqual(
            accepted_fields["caller_outcome"]["controller_acceptance"], "accepted"
        )
        self.assertEqual(accepted_fields["caller_outcome"]["halt"], "none")
        self.assertIn("controller accepted", accepted_fields["final_outcome"]["summary"])
        halted = fixture_observation(
            terminal_state="halted",
            record_state="HALTED",
            halt={
                "session": "cursor-acp-session",
                "conversation_id": "conv-cursor-acp-1",
                "halted": True,
            },
        )
        halted_fields = caller_fields_from_observation(halted, halt_confirmed=True)
        self.assertEqual(halted_fields["caller_outcome"]["halt"], "confirmed")
        self.assertEqual(
            halted_fields["caller_outcome"]["controller_acceptance"], "none"
        )
        self.assertEqual(halted_fields["caller_outcome"]["worker_completion"], "none")
        qualified = qualify_cursor_acp_lifecycle(
            accepted,
            expected_session="cursor-acp-session",
            expected_conversation_id="conv-cursor-acp-1",
            expected_workspace=_workspace(),
            requested_model="cursor-grok-4.6-high",
        )
        self.assertEqual(qualified["schema"], "puppet.cursor-acp-lifecycle/v1")
        self.assertFalse(qualified["live_cursor_acp_claimed"])
        self.assertEqual(qualified["phases"]["worker_completion"], "reported")
        self.assertEqual(qualified["phases"]["controller_acceptance"], "accepted")
        self.assertIsNone(qualified["phases"]["confirmed_halt"])
        source_accepted = fixture_observation(
            last_checkpoint={"checkpoint_id": "c" * 64},
            record_state="SOURCE_ACCEPTED",
        )
        source_fields = caller_fields_from_observation(source_accepted)
        self.assertEqual(source_fields["caller_outcome"]["worker_completion"], "reported")
        self.assertEqual(source_fields["caller_outcome"]["controller_acceptance"], "none")
        self.assertIsNone(source_fields["final_outcome"])

    def test_selector_only_and_mismatched_model_are_rejected(self):
        selector_only = fixture_observation()
        selector_only["observed_model"] = {
            "id": "cursor-grok-4.6-high",
            "source": "selector",
        }
        with self.assertRaisesRegex(IdentityError, "requested selector"):
            prove_observed_model(selector_only)
        copied_selector = fixture_observation(
            observed_model="cursor-grok-4.6-high",
            runtime_model="cursor-grok-4.6-high",
        )
        with self.assertRaisesRegex(IdentityError, "requested selector"):
            prove_observed_model(copied_selector)
        missing_runtime = fixture_observation(
            observed_model="grok-4.6[effort=high,fast=true]",
            runtime_model="other-runtime-model",
        )
        with self.assertRaisesRegex(IdentityError, "missing from runtime"):
            prove_observed_model(missing_runtime)
        mismatched = fixture_observation()
        with self.assertRaisesRegex(IdentityError, "does not match"):
            prove_observed_model(
                mismatched,
                expected_observed_model="other-observed-model",
            )

    def test_workspace_session_and_result_identity_failures(self):
        observation = fixture_observation()
        with self.assertRaisesRegex(IdentityError, "workspace identity"):
            prove_workspace_binding(
                observation,
                expected_workspace=_workspace(path="/other/workspace"),
            )
        with self.assertRaisesRegex(IdentityError, "workspace identity"):
            prove_workspace_binding(
                observation,
                expected_workspace=_workspace(branch="other-branch"),
            )
        with self.assertRaisesRegex(IdentityError, "session and conversation"):
            prove_resume_identity(
                observation,
                expected_session="cursor-acp-session",
                expected_conversation_id="conv-other",
            )
        with self.assertRaisesRegex(IdentityError, "session and conversation"):
            prove_resume_identity(
                observation,
                expected_session="other-session",
                expected_conversation_id="conv-cursor-acp-1",
            )
        with self.assertRaisesRegex(IdentityError, "terminal result state"):
            prove_terminal_result(observation, expected_state="failed")
        with self.assertRaisesRegex(IdentityError, "terminal result identity"):
            prove_terminal_result(observation, expected_result_id="other-result")

    def test_generic_acp_and_non_cursor_targets_are_unsupported(self):
        generic = fixture_observation(transport="acp")
        with self.assertRaisesRegex(IdentityError, "generic acp"):
            prove_observed_model(generic)
        with self.assertRaises(UnsupportedError) as raised:
            require_cursor_acp_target("agy")
        self.assertEqual(
            raised.exception.as_dict()["blocker"]["code"],
            "transport_target_mismatch",
        )
        with self.assertRaisesRegex(UnsupportedError, "cursor target"):
            require_cursor_acp_target("codex")
        wrong_target = fixture_observation(target="agy")
        with self.assertRaisesRegex(UnsupportedError, "cursor target"):
            prove_observed_model(wrong_target)
        with self.assertRaisesRegex(UnsupportedError, "not implemented"):
            bind_run_transport("acp")

    def test_unavailable_observer_is_a_body_safe_blocker(self):
        with tempfile.TemporaryDirectory() as temporary:
            controller = CursorAcpController(Path(temporary))
            with self.assertRaises(UnsupportedError) as raised:
                controller.require_observation()
            payload = raised.exception.as_dict()
            self.assertEqual(payload["blocker"]["code"], "transport_unavailable")
            self.assertIn("no fallback", payload["blocker"]["remedy"])
            self.assertNotIn("\n", payload["blocker"]["changed"])

    def test_no_fallback_when_cursor_acp_is_requested(self):
        binding = bind_run_transport("cursor-acp")
        self.assertEqual(binding["id"], "cursor-acp")
        self.assertNotEqual(binding["id"], "tmux")
        self.assertNotEqual(binding["id"], "agy-print")
        self.assertNotEqual(binding["id"], "acp")
        self.assertFalse(CursorAcpController.available())
        self.assertFalse(CursorAcpRunnerFixture.available())
        self.assertFalse(transport_is_available("cursor-acp"))
        self.assertEqual(
            transport_unavailable_detail("cursor-acp"),
            "cursor-acp transport is unavailable",
        )
        blockers = _caller_blockers_from_details(
            ["cursor-acp transport is unavailable"]
        )
        self.assertEqual(blockers[0]["code"], "transport_unavailable")
        self.assertIn("no fallback", blockers[0]["remedy"])
        with mock.patch.object(
            TmuxController, "__init__", side_effect=AssertionError("tmux")
        ), mock.patch.object(
            AgyPrintController, "__init__", side_effect=AssertionError("agy-print")
        ):
            with tempfile.TemporaryDirectory() as temporary:
                controller = open_run_transport(binding, Path(temporary))
        self.assertIsInstance(controller, CursorAcpController)
        table = transport_capability_table()
        self.assertEqual(table["cursor-acp"]["implementation"], "implemented")
        self.assertEqual(table["acp"]["implementation"], "unsupported")
        self.assertEqual(table["herdr"]["implementation"], "unsupported")
        self.assertEqual(table["agy-print"]["implementation"], "implemented")
        self.assertEqual(table["tmux"]["implementation"], "implemented")

    def test_structured_launch_uses_fixture_and_never_opens_other_transports(self):
        runner = CursorAcpRunnerFixture(fixture_observation())
        contract = mock.Mock()
        contract.repo = Path("/tmp/cursor-acp-workspace")
        contract.requested_model = "cursor-grok-4.6-high"
        contract.target = "cursor"
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
        ), mock.patch.object(
            AgyPrintController,
            "__init__",
            side_effect=AssertionError("agy-print fallback"),
        ):
            with tempfile.TemporaryDirectory() as temporary:
                result = _cursor_acp_structured_launch(
                    session="cursor-acp-session",
                    contract=contract,
                    transport=bind_run_transport("cursor-acp"),
                    state_root=Path(temporary),
                    requested_model="cursor-grok-4.6-high",
                    runner=runner,
                )
        self.assertTrue(result["ok"])
        self.assertFalse(result["live_cursor_acp_claimed"])
        self.assertEqual(result["transport"]["id"], "cursor-acp")
        self.assertEqual(
            result["cursor_acp"]["model"]["observed_model"],
            "grok-4.6[effort=high,fast=true]",
        )
        self.assertEqual(result["lifecycle"]["schema"], "puppet.cursor-acp-lifecycle/v1")
        self.assertFalse(result["lifecycle"]["live_cursor_acp_claimed"])
        self.assertFalse(CursorAcpController.available())

    def test_structured_launch_without_observer_does_not_fall_back(self):
        contract = mock.Mock()
        contract.repo = Path("/tmp/cursor-acp-workspace")
        contract.requested_model = None
        contract.target = "cursor"
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
        ), mock.patch.object(
            AgyPrintController,
            "__init__",
            side_effect=AssertionError("agy-print fallback"),
        ):
            with tempfile.TemporaryDirectory() as temporary:
                with self.assertRaises(UnsupportedError) as raised:
                    _cursor_acp_structured_launch(
                        session="cursor-acp-session",
                        contract=contract,
                        transport=bind_run_transport("cursor-acp"),
                        state_root=Path(temporary),
                        requested_model=None,
                    )
        self.assertEqual(
            raised.exception.as_dict()["blocker"]["code"],
            "transport_unavailable",
        )

    def test_doctor_reports_cursor_acp_unavailable_without_fallback(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            candidate = initialize_repo(
                root / "candidate", "codex/cursor-acp-doctor", "candidate"
            )
            files = controller_files(
                root,
                candidate=candidate,
                branch="codex/cursor-acp-doctor",
                session="cursor-acp-doctor",
                task_profile="implementation",
                protocol_fingerprint="e" * 64,
                target="cursor",
            )
            with mock.patch.object(
                TmuxController, "__init__", side_effect=AssertionError("tmux")
            ), mock.patch.object(
                AgyPrintController, "__init__", side_effect=AssertionError("agy-print")
            ):
                report = doctor(
                    contract_path=files["contract"],
                    manifest_path=files["manifest"],
                    authorization_path=files["authorization"],
                    proof_root=files["proof"],
                    state_root=files["state"],
                    require_subscription_profile=False,
                    requested_transport="cursor-acp",
                )
            self.assertEqual(report["transport"]["id"], "cursor-acp")
            self.assertIn("cursor-acp transport is unavailable", report["blockers"])
            self.assertNotIn("tmux is unavailable", report["blockers"])
            self.assertNotIn("agy-print transport is unavailable", report["blockers"])
            self.assertTrue(
                any(
                    item["code"] == "transport_unavailable"
                    for item in report["caller_blockers"]
                )
            )
            self.assertEqual(
                report["transport_capabilities"]["cursor-acp"]["implementation"],
                "implemented",
            )
            self.assertEqual(
                report["transport_capabilities"]["acp"]["implementation"],
                "unsupported",
            )
            self.assertFalse(report["launch_ready"])

    def test_doctor_rejects_cursor_acp_for_non_cursor_targets(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            candidate = initialize_repo(
                root / "candidate", "codex/cursor-acp-codex", "candidate"
            )
            files = controller_files(
                root,
                candidate=candidate,
                branch="codex/cursor-acp-codex",
                session="cursor-acp-codex",
                task_profile="implementation",
                protocol_fingerprint="e" * 64,
                target="codex",
            )
            report = doctor(
                contract_path=files["contract"],
                manifest_path=files["manifest"],
                authorization_path=files["authorization"],
                proof_root=files["proof"],
                state_root=files["state"],
                require_subscription_profile=False,
                requested_transport="cursor-acp",
            )
            self.assertEqual(report["transport"]["id"], "cursor-acp")
            self.assertIn(
                "cursor-acp is valid only for the cursor target",
                report["blockers"],
            )
            self.assertTrue(
                any(
                    item["code"] == "transport_target_mismatch"
                    for item in report["caller_blockers"]
                )
            )
            self.assertFalse(report["launch_ready"])

    def test_existing_transports_are_preserved(self):
        self.assertEqual(bind_run_transport()["id"], "tmux")
        self.assertEqual(bind_run_transport("agy-print")["id"], "agy-print")
        table = transport_capability_table()
        self.assertEqual(table["tmux"]["implementation"], "implemented")
        self.assertEqual(table["tmux"]["status_proves"], "pane_and_process_identity")
        self.assertEqual(table["tmux"]["resume_proves"], "unsupported")
        self.assertEqual(table["agy-print"]["implementation"], "implemented")
        self.assertEqual(
            make_blocker(code="tmux_unavailable", detail="tmux is unavailable")[
                "remedy"
            ].startswith("install tmux"),
            True,
        )
        self.assertEqual(transport_unavailable_detail("tmux"), "tmux is unavailable")
        self.assertEqual(
            transport_unavailable_detail("agy-print"),
            "agy-print transport is unavailable",
        )

    def test_registered_cursor_acp_session_does_not_open_tmux_runtime(self):
        record = {
            "transport": bind_run_transport("cursor-acp"),
            "session": "cursor-acp-session",
        }
        with tempfile.TemporaryDirectory() as temporary:
            with mock.patch.object(
                TmuxController, "__init__", side_effect=AssertionError("tmux")
            ), mock.patch.object(
                AgyPrintController, "__init__", side_effect=AssertionError("agy-print")
            ):
                with self.assertRaisesRegex(IdentityError, "is not tmux"):
                    _runtime(
                        SessionRegistry(Path(temporary)),
                        record,
                        "status",
                        require_process=False,
                    )

    def test_public_launch_cursor_acp_stays_blocked_without_fallback(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            candidate = initialize_repo(
                root / "candidate", "codex/cursor-acp-launch", "candidate"
            )
            files = controller_files(
                root,
                candidate=candidate,
                branch="codex/cursor-acp-launch",
                session="cursor-acp-launch",
                task_profile="implementation",
                protocol_fingerprint="e" * 64,
                target="cursor",
            )
            with mock.patch.object(
                TmuxController, "__init__", side_effect=AssertionError("tmux")
            ), mock.patch.object(
                AgyPrintController, "__init__", side_effect=AssertionError("agy-print")
            ):
                with self.assertRaisesRegex(UnsupportedError, "preflight is blocked"):
                    launch(
                        session="cursor-acp-launch",
                        contract_path=files["contract"],
                        manifest_path=files["manifest"],
                        authorization_path=files["authorization"],
                        proof_root=files["proof"],
                        state_root=files["state"],
                        supervisor_executable=files["supervisor_executable"],
                        prompt="fixture only",
                        require_subscription_profile=False,
                        requested_transport="cursor-acp",
                    )

    def test_halt_rejects_foreign_or_missing_session(self):
        observation = fixture_observation()
        with self.assertRaisesRegex(IdentityError, "halt proof is missing"):
            prove_shutdown(
                observation,
                expected_session="cursor-acp-session",
                expected_conversation_id="conv-cursor-acp-1",
            )
        foreign = fixture_observation(
            halt={
                "session": "other-session",
                "conversation_id": "conv-cursor-acp-1",
                "halted": True,
            }
        )
        with self.assertRaisesRegex(IdentityError, "not confined"):
            prove_shutdown(
                foreign,
                expected_session="cursor-acp-session",
                expected_conversation_id="conv-cursor-acp-1",
            )

    def test_operator_plan_field_set_stays_frozen(self):
        params = inspect.signature(compile_operator_plan).parameters
        self.assertNotIn("transport", params)
        self.assertNotIn("requested_transport", params)
        source = inspect.getsource(compile_operator_plan)
        self.assertNotIn('result["transport"]', source)
        self.assertNotIn("'transport':", source.split("result: Dict[str, Any] = {", 1)[1])
