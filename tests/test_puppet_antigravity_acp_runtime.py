from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "puppet" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from antigravity_acpx import claim_isolated_root, load_isolated_root
from puppet_lib.antigravity_acp import (
    DEFAULT_ANTIGRAVITY_MODEL,
    AntigravityAcpController,
    AntigravityAcpNodeRuntime,
    AntigravityAcpRuntimeRunner,
    AntigravityAcpSyntheticRuntime,
    map_runtime_antigravity_models,
    verified_antigravity_acp_catalog,
)
from puppet_lib.cursor_acp import (
    drain_runtime_turn_events,
    require_unsupported_permission_outcome,
    require_unsupported_question_outcome,
)
from puppet_lib.errors import IdentityError, UnsupportedError
from puppet_lib.session import _antigravity_acp_structured_launch
from puppet_lib.transport import bind_run_transport


GEMINI_MODELS = {
    "currentModelId": DEFAULT_ANTIGRAVITY_MODEL,
    "availableModelIds": [
        "gemini-3.8-flash-high",
        "gemini-3.1-pro",
        "gemini-3-flash",
    ],
}


def _workspace(path, **overrides):
    workspace = {
        "path": str(path),
        "branch": "codex/example",
        "head": "a" * 40,
        "tree": "b" * 40,
    }
    workspace.update(overrides)
    return workspace


def _private_root(temporary, name="isolated"):
    root = Path(temporary).resolve() / name
    root.mkdir(mode=0o700)
    os.chmod(root, 0o700)
    return root


def _handle(workspace, **overrides):
    handle = {
        "sessionKey": "agy-acp-session",
        "backend": "acpx",
        "runtimeSessionName": "acpx:agy-acp-session",
        "cwd": str(workspace),
        "acpxRecordId": "record-owned-1",
        "backendSessionId": "backend-session-1",
        "agentSessionId": "agent-session-1",
    }
    handle.update(overrides)
    return handle


class AntigravityAcpRuntimeControllerTests(unittest.TestCase):
    def _claim(self, isolated, workspace):
        claim_isolated_root(
            isolated,
            owner="puppet-owner",
            session="agy-acp-session",
            conversation_id="conv-agy-acp-1",
        )
        return _workspace(workspace)

    def _runner(self, isolated, workspace, runtime, **overrides):
        values = {
            "isolated_root": isolated,
            "owner": "puppet-owner",
            "session": "agy-acp-session",
            "conversation_id": "conv-agy-acp-1",
            "request_id": "agy-acp-request-1",
            "workspace": self._claim(isolated, workspace)
            if not isolated.joinpath("ownership.json").exists()
            else _workspace(workspace),
            "requested_model": DEFAULT_ANTIGRAVITY_MODEL,
            "catalog": verified_antigravity_acp_catalog(),
        }
        values.update(overrides)
        if "workspace" not in overrides and isolated.joinpath("ownership.json").exists():
            values["workspace"] = _workspace(workspace)
        return AntigravityAcpRuntimeRunner(runtime, **values)

    def test_runtime_derived_launch_turn_status_result_and_owned_halt(self):
        with tempfile.TemporaryDirectory() as temporary:
            isolated = _private_root(temporary)
            workspace = Path(temporary).resolve() / "workspace"
            workspace.mkdir()
            runtime = AntigravityAcpSyntheticRuntime(
                handle=_handle(workspace),
                models=GEMINI_MODELS,
                events=({"type": "content_delta", "text": "secret-body"},),
            )
            runner = self._runner(isolated, workspace, runtime, halt=True)
            controller = AntigravityAcpController(Path(temporary), runner=runner)
            result = controller.caller_result(
                expected_session="agy-acp-session",
                expected_conversation_id="conv-agy-acp-1",
                expected_workspace=_workspace(workspace),
                requested_model=DEFAULT_ANTIGRAVITY_MODEL,
                require_halt=True,
            )
            self.assertTrue(result["ok"])
            self.assertFalse(result["live_antigravity_acp_claimed"])
            self.assertEqual(
                result["antigravity_acp"]["model"]["observed_id"],
                DEFAULT_ANTIGRAVITY_MODEL,
            )
            self.assertIsNone(result["antigravity_acp"]["model"]["effort"])
            self.assertEqual(result["antigravity_acp"]["terminal"]["state"], "halted")
            self.assertEqual(result["state"], "HALTED")
            self.assertEqual(len(runtime.ensure_calls), 1)
            self.assertEqual(
                sorted(runtime.ensure_calls[0]),
                ["agent", "cwd", "mode", "sessionKey"],
            )
            self.assertEqual(len(runtime.start_calls), 1)
            self.assertEqual(runtime.start_calls[0]["requestId"], "agy-acp-request-1")
            self.assertGreaterEqual(len(runtime.status_calls), 1)
            self.assertEqual(len(runtime.close_calls), 1)
            self.assertTrue(runtime.close_calls[0]["discardPersistentState"])
            self.assertEqual(runner.discarded_events["body_retained"], False)
            self.assertNotIn("secret-body", str(runner.discarded_events))
            self.assertFalse(AntigravityAcpController.available())
            self.assertFalse(AntigravityAcpRuntimeRunner.available())

    def test_structured_launch_uses_runtime_runner_not_injected_observation(self):
        with tempfile.TemporaryDirectory() as temporary:
            isolated = _private_root(temporary)
            workspace = Path(temporary).resolve() / "workspace"
            workspace.mkdir()
            runtime = AntigravityAcpSyntheticRuntime(
                handle=_handle(workspace),
                models=GEMINI_MODELS,
            )
            runner = self._runner(isolated, workspace, runtime)
            contract = type("Contract", (), {})()
            contract.repo = workspace
            contract.requested_model = DEFAULT_ANTIGRAVITY_MODEL
            contract.target = "agy"
            with mock.patch(
                "puppet_lib.session._workspace_snapshot",
                return_value={
                    "branch": "codex/example",
                    "head": "a" * 40,
                    "tree": "b" * 40,
                    "dirty": False,
                },
            ):
                launched = _antigravity_acp_structured_launch(
                    session="agy-acp-session",
                    contract=contract,
                    transport=bind_run_transport("antigravity-acp"),
                    state_root=Path(temporary),
                    requested_model=DEFAULT_ANTIGRAVITY_MODEL,
                    runner=runner,
                )
            self.assertTrue(launched["ok"])
            self.assertEqual(
                launched["antigravity_acp"]["model"]["observed_id"],
                DEFAULT_ANTIGRAVITY_MODEL,
            )
            self.assertEqual(len(runtime.ensure_calls), 1)
            self.assertEqual(len(runtime.start_calls), 1)
            self.assertNotEqual(
                runner.handle["backendSessionId"],
                "conv-agy-acp-1",
            )
            self.assertNotEqual(runner.handle["acpxRecordId"], "conv-agy-acp-1")
            self.assertNotEqual(runner.handle["runtimeSessionName"], "agy-acp-session")

    def test_model_catalog_requested_selected_current_and_rejections(self):
        mapped = map_runtime_antigravity_models(
            GEMINI_MODELS,
            requested_model=DEFAULT_ANTIGRAVITY_MODEL,
            catalog=verified_antigravity_acp_catalog(),
        )
        self.assertEqual(mapped["selected_model"], DEFAULT_ANTIGRAVITY_MODEL)
        self.assertEqual(mapped["current_model"], DEFAULT_ANTIGRAVITY_MODEL)
        with self.assertRaisesRegex(IdentityError, "unavailable"):
            map_runtime_antigravity_models(
                GEMINI_MODELS,
                requested_model="gemini-missing",
                catalog=verified_antigravity_acp_catalog(),
            )
        with self.assertRaisesRegex(IdentityError, "fallback or default"):
            map_runtime_antigravity_models(
                {
                    "currentModelId": "fallback",
                    "availableModelIds": ["fallback", DEFAULT_ANTIGRAVITY_MODEL],
                },
                requested_model=DEFAULT_ANTIGRAVITY_MODEL,
            )
        with self.assertRaisesRegex(IdentityError, "unverified"):
            map_runtime_antigravity_models(
                {
                    "currentModelId": "foreign-model",
                    "availableModelIds": GEMINI_MODELS["availableModelIds"],
                },
                requested_model=DEFAULT_ANTIGRAVITY_MODEL,
                catalog=verified_antigravity_acp_catalog(),
            )
        with tempfile.TemporaryDirectory() as temporary:
            isolated = _private_root(temporary)
            workspace = Path(temporary).resolve() / "workspace"
            workspace.mkdir()
            runtime = AntigravityAcpSyntheticRuntime(
                handle=_handle(workspace),
                models={
                    "currentModelId": "gemini-3.1-pro",
                    "availableModelIds": GEMINI_MODELS["availableModelIds"],
                },
            )
            controller = AntigravityAcpController(
                Path(temporary),
                runner=self._runner(isolated, workspace, runtime),
            )
            with self.assertRaisesRegex(IdentityError, "does not match"):
                controller.caller_result(
                    expected_session="agy-acp-session",
                    expected_conversation_id="conv-agy-acp-1",
                    expected_workspace=_workspace(workspace),
                    requested_model=DEFAULT_ANTIGRAVITY_MODEL,
                )

    def test_foreign_workspace_session_request_and_unknown_model_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            isolated = _private_root(temporary)
            workspace = Path(temporary).resolve() / "workspace"
            workspace.mkdir()
            foreign_cwd = AntigravityAcpSyntheticRuntime(
                handle=_handle(workspace, cwd=str(Path(temporary) / "other")),
                models=GEMINI_MODELS,
            )
            controller = AntigravityAcpController(
                Path(temporary),
                runner=self._runner(isolated, workspace, foreign_cwd),
            )
            with self.assertRaisesRegex(IdentityError, "cwd"):
                controller.require_observation()
            foreign_session = AntigravityAcpSyntheticRuntime(
                handle=_handle(workspace, sessionKey="other-session"),
                models=GEMINI_MODELS,
            )
            other = _private_root(temporary, "foreign-session")
            controller = AntigravityAcpController(
                Path(temporary),
                runner=self._runner(other, workspace, foreign_session),
            )
            with self.assertRaisesRegex(IdentityError, "sessionKey"):
                controller.require_observation()
            self.assertEqual(len(foreign_session.close_calls), 0)
            mismatched_request = AntigravityAcpSyntheticRuntime(
                handle=_handle(workspace),
                models=GEMINI_MODELS,
            )
            original = mismatched_request.start_turn

            def foreign_turn(payload):
                turn = original(payload)
                turn["requestId"] = "foreign-request"
                return turn

            mismatched_request.start_turn = foreign_turn
            request_root = _private_root(temporary, "foreign-request")
            controller = AntigravityAcpController(
                Path(temporary),
                runner=self._runner(request_root, workspace, mismatched_request),
            )
            with self.assertRaisesRegex(IdentityError, "host request"):
                controller.require_observation()
            self.assertEqual(len(mismatched_request.close_calls), 1)

    def test_ownership_before_prompt_and_owned_cleanup_error_fence(self):
        with tempfile.TemporaryDirectory() as temporary:
            isolated = _private_root(temporary)
            workspace = Path(temporary).resolve() / "workspace"
            workspace.mkdir()
            claim_isolated_root(
                isolated,
                owner="foreign-owner",
                session="agy-acp-session",
                conversation_id="conv-agy-acp-1",
            )
            runtime = AntigravityAcpSyntheticRuntime(
                handle=_handle(workspace),
                models=GEMINI_MODELS,
            )
            runner = AntigravityAcpRuntimeRunner(
                runtime,
                isolated_root=isolated,
                owner="puppet-owner",
                session="agy-acp-session",
                conversation_id="conv-agy-acp-1",
                request_id="agy-acp-request-1",
                workspace=_workspace(workspace),
                requested_model=DEFAULT_ANTIGRAVITY_MODEL,
                catalog=verified_antigravity_acp_catalog(),
            )
            controller = AntigravityAcpController(Path(temporary), runner=runner)
            with self.assertRaisesRegex(IdentityError, "before session or prompt"):
                controller.require_observation()
            self.assertEqual(runtime.ensure_calls, [])
            self.assertEqual(runtime.start_calls, [])

            owned = _private_root(temporary, "owned-close")
            close_error = RuntimeError("owned close failed")
            failing = AntigravityAcpSyntheticRuntime(
                handle=_handle(workspace),
                models=GEMINI_MODELS,
                close_error=close_error,
            )
            failing_runner = self._runner(owned, workspace, failing)
            controller = AntigravityAcpController(Path(temporary), runner=failing_runner)
            with self.assertRaises(RuntimeError) as raised:
                controller.require_observation()
            self.assertIs(raised.exception, close_error)
            ownership = load_isolated_root(owned)
            self.assertEqual(ownership["cleanup"], "unknown")
            self.assertTrue(ownership["replacement_blocked"])
            with self.assertRaisesRegex(IdentityError, "replacement is blocked"):
                AntigravityAcpRuntimeRunner(
                    AntigravityAcpSyntheticRuntime(
                        handle=_handle(workspace),
                        models=GEMINI_MODELS,
                    ),
                    isolated_root=owned,
                    owner="puppet-owner",
                    session="agy-acp-session",
                    conversation_id="conv-agy-acp-1",
                    request_id="agy-acp-request-2",
                    workspace=_workspace(workspace),
                    requested_model=DEFAULT_ANTIGRAVITY_MODEL,
                    catalog=verified_antigravity_acp_catalog(),
                ).observation()

    def test_unsupported_backend_discard_with_proven_local_cleanup(self):
        with tempfile.TemporaryDirectory() as temporary:
            isolated = _private_root(temporary)
            workspace = Path(temporary).resolve() / "workspace"
            workspace.mkdir()
            runtime = AntigravityAcpSyntheticRuntime(
                handle=_handle(workspace),
                models=GEMINI_MODELS,
                unsupported_backend_close=True,
                local_cleanup_proved=True,
            )
            runner = self._runner(isolated, workspace, runtime)
            controller = AntigravityAcpController(Path(temporary), runner=runner)
            result = controller.caller_result(
                expected_session="agy-acp-session",
                expected_conversation_id="conv-agy-acp-1",
                expected_workspace=_workspace(workspace),
                requested_model=DEFAULT_ANTIGRAVITY_MODEL,
            )
            self.assertTrue(result["ok"])
            self.assertEqual(runner.backend_discard, "unsupported_local_cleanup_proved")
            ownership = load_isolated_root(isolated)
            self.assertEqual(ownership["cleanup"], "owned")
            self.assertFalse(ownership["replacement_blocked"])

    def test_uncertain_cleanup_fences_replacement(self):
        with tempfile.TemporaryDirectory() as temporary:
            isolated = _private_root(temporary)
            workspace = Path(temporary).resolve() / "workspace"
            workspace.mkdir()
            runtime = AntigravityAcpSyntheticRuntime(
                handle=_handle(workspace),
                models=GEMINI_MODELS,
                unsupported_backend_close=True,
                local_cleanup_proved=False,
            )
            runner = self._runner(isolated, workspace, runtime)
            controller = AntigravityAcpController(Path(temporary), runner=runner)
            with self.assertRaisesRegex(UnsupportedError, "session/close"):
                controller.require_observation()
            ownership = load_isolated_root(isolated)
            self.assertEqual(ownership["cleanup"], "unknown")
            self.assertTrue(ownership["replacement_blocked"])

    def test_observer_drain_return_is_body_free_and_bounded(self):
        overflow = [{"type": "unique_%s" % index, "text": "body-%s" % index} for index in range(20)]
        drained = drain_runtime_turn_events(
            [{"type": "content_delta", "text": "secret"}] + overflow
        )
        self.assertEqual(drained["observer"], "ended")
        self.assertEqual(drained["body_retained"], False)
        self.assertTrue(drained["observed_types_truncated"])
        self.assertEqual(len(drained["observed_types"]), 16)
        self.assertNotIn("secret", str(drained))

    def test_explicit_unsupported_permission_and_question_outcomes(self):
        cancelled = require_unsupported_question_outcome(
            {
                "state": "interaction_required",
                "interaction_id": "question-1",
                "human_required": True,
                "outcome": "cancelled",
                "invented_answer": None,
            }
        )
        self.assertEqual(cancelled["outcome"], "cancelled")
        self.assertIsNone(cancelled["invented_answer"])
        denied = require_unsupported_permission_outcome(
            {
                "state": "permission_required",
                "permission_id": "perm-1",
                "outcome": "denied",
                "allowed": False,
                "invented_decision": None,
            }
        )
        self.assertEqual(denied["outcome"], "denied")
        self.assertFalse(denied["allowed"])
        with tempfile.TemporaryDirectory() as temporary:
            isolated = _private_root(temporary)
            workspace = Path(temporary).resolve() / "workspace"
            workspace.mkdir()
            runtime = AntigravityAcpSyntheticRuntime(
                handle=_handle(workspace),
                models=GEMINI_MODELS,
                permission={
                    "state": "permission_required",
                    "permission_id": "perm-1",
                    "outcome": "cancelled",
                    "allowed": False,
                    "invented_decision": None,
                },
                question={
                    "state": "interaction_required",
                    "interaction_id": "question-1",
                    "human_required": True,
                    "outcome": "cancelled",
                    "invented_answer": None,
                },
            )
            runner = self._runner(
                isolated,
                workspace,
                runtime,
                permission=runtime.permission,
                question=runtime.question,
            )
            controller = AntigravityAcpController(Path(temporary), runner=runner)
            observation = controller.require_observation()
            self.assertEqual(observation["session"]["session_id"], "agy-acp-session")
            self.assertEqual(observation["question"]["outcome"], "cancelled")
            self.assertEqual(runner.permission_outcome["outcome"], "cancelled")
            self.assertEqual(runner.question_outcome["outcome"], "cancelled")

    def test_actual_public_runtime_through_controller_consumer(self):
        artifact = ROOT / "runs/puppet-dual-acp-controller-runs/20260921/artifacts/acpx-0.18.0.tgz"
        if not artifact.is_file():
            self.skipTest("exact local acpx artifact is task-owned proof input")
        with tempfile.TemporaryDirectory() as temporary:
            isolated = _private_root(temporary)
            workspace = Path(temporary).resolve() / "workspace"
            workspace.mkdir()
            claim_isolated_root(
                isolated,
                owner="puppet-owner",
                session="agy-acp-session",
                conversation_id="conv-agy-acp-1",
            )
            runtime = AntigravityAcpNodeRuntime(
                workspace=workspace,
                isolated_root=isolated,
                repo_root=ROOT,
            )
            try:
                runner = AntigravityAcpRuntimeRunner(
                    runtime,
                    isolated_root=isolated,
                    owner="puppet-owner",
                    session="agy-acp-session",
                    conversation_id="conv-agy-acp-1",
                    request_id="agy-acp-request-1",
                    workspace=_workspace(workspace),
                    requested_model=DEFAULT_ANTIGRAVITY_MODEL,
                    catalog=verified_antigravity_acp_catalog(),
                    halt=True,
                )
                controller = AntigravityAcpController(Path(temporary), runner=runner)
                result = controller.caller_result(
                    expected_session="agy-acp-session",
                    expected_conversation_id="conv-agy-acp-1",
                    expected_workspace=_workspace(workspace),
                    requested_model=DEFAULT_ANTIGRAVITY_MODEL,
                    require_halt=True,
                )
                self.assertTrue(result["ok"])
                self.assertFalse(result["live_antigravity_acp_claimed"])
                self.assertEqual(
                    result["antigravity_acp"]["model"]["observed_id"],
                    DEFAULT_ANTIGRAVITY_MODEL,
                )
                self.assertEqual(result["antigravity_acp"]["terminal"]["state"], "halted")
                self.assertNotEqual(runner.handle["backendSessionId"], "conv-agy-acp-1")
                self.assertNotEqual(runner.handle["acpxRecordId"], "conv-agy-acp-1")
                self.assertEqual(runner.discarded_events["body_retained"], False)
                self.assertFalse(AntigravityAcpController.available())
            finally:
                runtime.shutdown()


if __name__ == "__main__":
    unittest.main()
