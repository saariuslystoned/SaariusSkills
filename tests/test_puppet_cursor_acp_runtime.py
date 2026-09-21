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

from cursor_acpx import claim_isolated_root, load_isolated_root
from puppet_lib.cursor_acp import (
    FINISH_POLICY_RETAIN,
    SESSION_MODE_PERSISTENT,
    SYNTHETIC_PEER_KIND,
    CursorAcpController,
    CursorAcpNodeRuntime,
    CursorAcpRuntimeRunner,
    CursorAcpSyntheticRuntime,
    advertised_catalog_from_runtime_models,
    build_cursor_acp_candidate_runner,
    drain_runtime_turn_events,
    map_runtime_models,
    require_runtime_task_text,
    require_unsupported_permission_outcome,
    require_unsupported_question_outcome,
)
from puppet_lib.errors import IdentityError, ValidationError
from puppet_lib.session import _cursor_acp_structured_launch
from puppet_lib.transport import bind_run_transport


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
        "sessionKey": "cursor-acp-session",
        "backend": "acpx",
        "runtimeSessionName": "acpx:cursor-acp-session",
        "cwd": str(workspace),
        "acpxRecordId": "record-owned-1",
        "backendSessionId": "backend-session-1",
        "agentSessionId": "agent-session-1",
    }
    handle.update(overrides)
    return handle


CALLER_TASK_TEXT = "caller task: inspect the owned workspace without echoing bodies"
SECOND_TURN_TEXT = "caller follow-up: continue the same owned session"
GROK_HIGH = "grok-4.6[effort=high,fast=true]"
GROK_MODELS = {
    "currentModelId": GROK_HIGH,
    "availableModelIds": [
        "grok-4.6[effort=low,fast=true]",
        "grok-4.6[effort=medium,fast=true]",
        GROK_HIGH,
        "grok-4.6[effort=xhigh,fast=true]",
    ],
}


class CursorAcpRuntimeControllerTests(unittest.TestCase):
    def _claim(self, isolated, workspace):
        claim_isolated_root(
            isolated,
            owner="puppet-owner",
            session="cursor-acp-session",
            conversation_id="conv-cursor-acp-1",
        )
        return _workspace(workspace)

    def _runner(self, isolated, workspace, runtime, **overrides):
        values = {
            "isolated_root": isolated,
            "owner": "puppet-owner",
            "session": "cursor-acp-session",
            "conversation_id": "conv-cursor-acp-1",
            "request_id": "cursor-acp-request-1",
            "workspace": self._claim(isolated, workspace) if not isolated.joinpath("ownership.json").exists() else _workspace(workspace),
            "requested_model": "cursor-grok-4.6-high",
            "text": CALLER_TASK_TEXT,
            "catalog": advertised_catalog_from_runtime_models(GROK_MODELS),
        }
        values.update(overrides)
        if "workspace" not in overrides and isolated.joinpath("ownership.json").exists():
            values["workspace"] = _workspace(workspace)
        return CursorAcpRuntimeRunner(runtime, **values)

    def test_runtime_derived_launch_turn_status_result_and_owned_halt(self):
        with tempfile.TemporaryDirectory() as temporary:
            isolated = _private_root(temporary)
            workspace = Path(temporary).resolve() / "workspace"
            workspace.mkdir()
            runtime = CursorAcpSyntheticRuntime(
                handle=_handle(workspace),
                models=GROK_MODELS,
                events=({"type": "text_delta", "text": "secret-body"},),
            )
            runner = self._runner(isolated, workspace, runtime, halt=True)
            controller = CursorAcpController(Path(temporary), runner=runner)
            result = controller.caller_result(
                expected_session="cursor-acp-session",
                expected_conversation_id="conv-cursor-acp-1",
                expected_workspace=_workspace(workspace),
                requested_model="cursor-grok-4.6-high",
                require_halt=True,
            )
            self.assertTrue(result["ok"])
            self.assertFalse(result["live_cursor_acp_claimed"])
            self.assertEqual(result["cursor_acp"]["model"]["observed_model"], GROK_HIGH)
            self.assertEqual(result["cursor_acp"]["model"]["source"], "acp_runtime_metadata")
            self.assertEqual(result["cursor_acp"]["terminal_result"]["state"], "halted")
            self.assertEqual(result["cursor_acp"]["halt"]["session"], "cursor-acp-session")
            self.assertEqual(len(runtime.ensure_calls), 1)
            self.assertEqual(sorted(runtime.ensure_calls[0]), ["agent", "cwd", "mode", "sessionKey"])
            self.assertEqual(len(runtime.start_calls), 1)
            self.assertEqual(runtime.start_calls[0]["requestId"], "cursor-acp-request-1")
            self.assertEqual(runtime.start_calls[0]["text"], CALLER_TASK_TEXT)
            self.assertNotIn("cursor-acp-runtime-turn", runtime.start_calls[0]["text"])
            self.assertGreaterEqual(len(runtime.status_calls), 1)
            self.assertEqual(len(runtime.close_calls), 1)
            self.assertTrue(runtime.close_calls[0]["discardPersistentState"])
            self.assertEqual(runner.discarded_events["body_retained"], False)
            self.assertNotIn("secret-body", str(runner.discarded_events))
            self.assertFalse(CursorAcpController.available())
            self.assertFalse(CursorAcpRuntimeRunner.available())

    def test_structured_launch_uses_runtime_runner_not_injected_observation(self):
        with tempfile.TemporaryDirectory() as temporary:
            isolated = _private_root(temporary)
            workspace = Path(temporary).resolve() / "workspace"
            workspace.mkdir()
            runtime = CursorAcpSyntheticRuntime(handle=_handle(workspace), models=GROK_MODELS)
            runner = self._runner(isolated, workspace, runtime)
            contract = type("Contract", (), {})()
            contract.repo = workspace
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
            ):
                launched = _cursor_acp_structured_launch(
                    session="cursor-acp-session",
                    contract=contract,
                    transport=bind_run_transport("cursor-acp"),
                    state_root=Path(temporary),
                    requested_model="cursor-grok-4.6-high",
                    runner=runner,
                    prompt=CALLER_TASK_TEXT,
                )
            self.assertTrue(launched["ok"])
            self.assertEqual(launched["cursor_acp"]["model"]["observed_model"], GROK_HIGH)
            self.assertEqual(len(runtime.ensure_calls), 1)
            self.assertEqual(len(runtime.start_calls), 1)
            self.assertEqual(runtime.start_calls[0]["text"], CALLER_TASK_TEXT)
            self.assertNotIn(CALLER_TASK_TEXT, str(launched))

    def test_model_catalog_requested_selected_current_and_rejections(self):
        mapped = map_runtime_models(
            GROK_MODELS,
            requested_model="cursor-grok-4.6-high",
            catalog=advertised_catalog_from_runtime_models(GROK_MODELS),
        )
        self.assertEqual(mapped["selected_model"], GROK_HIGH)
        self.assertEqual(mapped["current_model"], GROK_HIGH)
        with self.assertRaisesRegex(IdentityError, "unavailable"):
            map_runtime_models(
                GROK_MODELS,
                requested_model="cursor-grok-4.6-missing",
                catalog=advertised_catalog_from_runtime_models(GROK_MODELS),
            )
        with self.assertRaisesRegex(IdentityError, "fallback or default"):
            map_runtime_models(
                {
                    "currentModelId": "fallback",
                    "availableModelIds": ["fallback", GROK_HIGH],
                },
                requested_model="cursor-grok-4.6-high",
            )
        with self.assertRaisesRegex(IdentityError, "unverified"):
            map_runtime_models(
                {
                    "currentModelId": "foreign-model",
                    "availableModelIds": GROK_MODELS["availableModelIds"],
                },
                requested_model="cursor-grok-4.6-high",
                catalog=advertised_catalog_from_runtime_models(GROK_MODELS),
            )
        with tempfile.TemporaryDirectory() as temporary:
            isolated = _private_root(temporary)
            workspace = Path(temporary).resolve() / "workspace"
            workspace.mkdir()
            runtime = CursorAcpSyntheticRuntime(
                handle=_handle(workspace),
                models={
                    "currentModelId": "grok-4.6[effort=low,fast=true]",
                    "availableModelIds": GROK_MODELS["availableModelIds"],
                },
            )
            runner = self._runner(isolated, workspace, runtime)
            controller = CursorAcpController(Path(temporary), runner=runner)
            result = controller.caller_result(
                expected_session="cursor-acp-session",
                expected_conversation_id="conv-cursor-acp-1",
                expected_workspace=_workspace(workspace),
                requested_model="cursor-grok-4.6-high",
            )
            self.assertEqual(result["cursor_acp"]["model"]["observed_model"], GROK_HIGH)
            self.assertEqual(runtime.set_model_calls[0]["model"], GROK_HIGH)
            unsupported = CursorAcpSyntheticRuntime(
                handle=_handle(workspace),
                models={
                    "currentModelId": "grok-4.6[effort=low,fast=true]",
                    "availableModelIds": GROK_MODELS["availableModelIds"],
                },
                set_model_supported=False,
            )
            missing = _private_root(temporary, "missing-set-model")
            with self.assertRaisesRegex(IdentityError, "does not match"):
                CursorAcpController(
                    Path(temporary),
                    runner=self._runner(missing, workspace, unsupported),
                ).caller_result(
                    expected_session="cursor-acp-session",
                    expected_conversation_id="conv-cursor-acp-1",
                    expected_workspace=_workspace(workspace),
                    requested_model="cursor-grok-4.6-high",
                )

    def test_foreign_workspace_session_request_and_unknown_model_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            isolated = _private_root(temporary)
            workspace = Path(temporary).resolve() / "workspace"
            workspace.mkdir()
            foreign_cwd = CursorAcpSyntheticRuntime(
                handle=_handle(workspace, cwd=str(Path(temporary) / "other")),
                models=GROK_MODELS,
            )
            controller = CursorAcpController(
                Path(temporary),
                runner=self._runner(isolated, workspace, foreign_cwd),
            )
            with self.assertRaisesRegex(IdentityError, "cwd"):
                controller.require_observation()
            foreign_session = CursorAcpSyntheticRuntime(
                handle=_handle(workspace, sessionKey="other-session"),
                models=GROK_MODELS,
            )
            other = _private_root(temporary, "foreign-session")
            controller = CursorAcpController(
                Path(temporary),
                runner=self._runner(other, workspace, foreign_session),
            )
            with self.assertRaisesRegex(IdentityError, "sessionKey"):
                controller.require_observation()
            self.assertEqual(len(foreign_session.close_calls), 0)
            mismatched_request = CursorAcpSyntheticRuntime(
                handle=_handle(workspace),
                models=GROK_MODELS,
            )
            original = mismatched_request.start_turn

            def foreign_turn(payload):
                turn = original(payload)
                turn["requestId"] = "foreign-request"
                return turn

            mismatched_request.start_turn = foreign_turn
            request_root = _private_root(temporary, "foreign-request")
            controller = CursorAcpController(
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
                session="cursor-acp-session",
                conversation_id="conv-cursor-acp-1",
            )
            runtime = CursorAcpSyntheticRuntime(handle=_handle(workspace), models=GROK_MODELS)
            runner = CursorAcpRuntimeRunner(
                runtime,
                isolated_root=isolated,
                owner="puppet-owner",
                session="cursor-acp-session",
                conversation_id="conv-cursor-acp-1",
                request_id="cursor-acp-request-1",
                workspace=_workspace(workspace),
                requested_model="cursor-grok-4.6-high",
                text=CALLER_TASK_TEXT,
                catalog=advertised_catalog_from_runtime_models(GROK_MODELS),
            )
            controller = CursorAcpController(Path(temporary), runner=runner)
            with self.assertRaisesRegex(IdentityError, "before session or prompt"):
                controller.require_observation()
            self.assertEqual(runtime.ensure_calls, [])
            self.assertEqual(runtime.start_calls, [])

            owned = _private_root(temporary, "owned-close")
            close_error = RuntimeError("owned close failed")
            failing = CursorAcpSyntheticRuntime(
                handle=_handle(workspace),
                models=GROK_MODELS,
                close_error=close_error,
            )
            failing_runner = self._runner(owned, workspace, failing)
            controller = CursorAcpController(Path(temporary), runner=failing_runner)
            with self.assertRaises(RuntimeError) as raised:
                controller.require_observation()
            self.assertIs(raised.exception, close_error)
            ownership = load_isolated_root(owned)
            self.assertEqual(ownership["cleanup"], "unknown")
            self.assertTrue(ownership["replacement_blocked"])
            with self.assertRaisesRegex(IdentityError, "replacement is blocked"):
                CursorAcpRuntimeRunner(
                    CursorAcpSyntheticRuntime(handle=_handle(workspace), models=GROK_MODELS),
                    isolated_root=owned,
                    owner="puppet-owner",
                    session="cursor-acp-session",
                    conversation_id="conv-cursor-acp-1",
                    request_id="cursor-acp-request-2",
                    workspace=_workspace(workspace),
                    requested_model="cursor-grok-4.6-high",
                    text=CALLER_TASK_TEXT,
                    catalog=advertised_catalog_from_runtime_models(GROK_MODELS),
                ).observation()

    def test_observer_drain_return_is_body_free_and_bounded(self):
        overflow = [{"type": "unique_%s" % index, "text": "body-%s" % index} for index in range(20)]
        drained = drain_runtime_turn_events([{"type": "text_delta", "text": "secret"}] + overflow)
        self.assertEqual(drained["observer"], "ended")
        self.assertEqual(drained["body_retained"], False)
        self.assertTrue(drained["observed_types_truncated"])
        self.assertEqual(len(drained["observed_types"]), 16)
        self.assertNotIn("secret", str(drained))
        returned = {"closed": False}

        def limited():
            try:
                yield {"type": "text_delta", "text": "secret"}
                yield {"type": "tool_call", "text": "secret"}
            finally:
                returned["closed"] = True

        events = limited()
        ended = drain_runtime_turn_events(events, limit=1)
        self.assertEqual(ended["event_count"], 1)
        self.assertTrue(returned["closed"])
        self.assertEqual(ended["observed_types"], ["text_delta"])

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
        with self.assertRaisesRegex(ValidationError, "invent"):
            require_unsupported_question_outcome(
                {
                    "state": "interaction_required",
                    "interaction_id": "question-1",
                    "human_required": True,
                    "outcome": "cancelled",
                    "invented_answer": "yes",
                }
            )
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
        with self.assertRaisesRegex(ValidationError, "invent"):
            require_unsupported_permission_outcome(
                {
                    "state": "permission_required",
                    "permission_id": "perm-1",
                    "outcome": "denied",
                    "allowed": False,
                    "invented_decision": "allow",
                }
            )
        with self.assertRaisesRegex(ValidationError, "allowed"):
            require_unsupported_permission_outcome(
                {
                    "state": "permission_required",
                    "permission_id": "perm-1",
                    "outcome": "denied",
                    "allowed": True,
                    "invented_decision": None,
                }
            )
        with tempfile.TemporaryDirectory() as temporary:
            isolated = _private_root(temporary)
            workspace = Path(temporary).resolve() / "workspace"
            workspace.mkdir()
            runtime = CursorAcpSyntheticRuntime(
                handle=_handle(workspace),
                models=GROK_MODELS,
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
            controller = CursorAcpController(Path(temporary), runner=runner)
            observation = controller.require_observation()
            self.assertEqual(observation["session"]["id"], "cursor-acp-session")
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
                session="cursor-acp-session",
                conversation_id="conv-cursor-acp-1",
            )
            runtime = CursorAcpNodeRuntime(
                workspace=workspace,
                isolated_root=isolated,
                repo_root=ROOT,
                synthetic_peer=True,
            )
            try:
                models = {
                    "currentModelId": "candidate-default",
                    "availableModelIds": ["candidate-default", "candidate-fast"],
                }
                runner = CursorAcpRuntimeRunner(
                    runtime,
                    isolated_root=isolated,
                    owner="puppet-owner",
                    session="cursor-acp-session",
                    conversation_id="conv-cursor-acp-1",
                    request_id="cursor-acp-request-1",
                    workspace=_workspace(workspace),
                    requested_model="candidate-default",
                    text=CALLER_TASK_TEXT,
                    catalog=advertised_catalog_from_runtime_models(models),
                    halt=True,
                )
                controller = CursorAcpController(Path(temporary), runner=runner)
                result = controller.caller_result(
                    expected_session="cursor-acp-session",
                    expected_conversation_id="conv-cursor-acp-1",
                    expected_workspace=_workspace(workspace),
                    requested_model="candidate-default",
                    require_halt=True,
                )
                self.assertTrue(result["ok"])
                self.assertFalse(result["live_cursor_acp_claimed"])
                self.assertEqual(
                    result["cursor_acp"]["model"]["observed_model"],
                    "candidate-default",
                )
                self.assertEqual(result["cursor_acp"]["model"]["source"], "acp_runtime_metadata")
                self.assertEqual(result["cursor_acp"]["terminal_result"]["state"], "halted")
                self.assertEqual(result["cursor_acp"]["halt"]["session"], "cursor-acp-session")
                self.assertNotEqual(
                    runner.handle["backendSessionId"],
                    "conv-cursor-acp-1",
                )
                self.assertNotEqual(runner.handle["acpxRecordId"], "conv-cursor-acp-1")
                self.assertEqual(runner.discarded_events["body_retained"], False)
                self.assertFalse(CursorAcpController.available())
                self.assertEqual(runtime.kind, SYNTHETIC_PEER_KIND)
            finally:
                runtime.shutdown()

    def test_missing_and_placeholder_task_text_are_rejected(self):
        with self.assertRaisesRegex(ValidationError, "missing"):
            require_runtime_task_text("")
        with self.assertRaisesRegex(ValidationError, "placeholder"):
            require_runtime_task_text("cursor-acp-runtime-turn")
        with tempfile.TemporaryDirectory() as temporary:
            isolated = _private_root(temporary)
            workspace = Path(temporary).resolve() / "workspace"
            workspace.mkdir()
            runtime = CursorAcpSyntheticRuntime(handle=_handle(workspace), models=GROK_MODELS)
            runner = CursorAcpRuntimeRunner(
                runtime,
                isolated_root=isolated,
                owner="puppet-owner",
                session="cursor-acp-session",
                conversation_id="conv-cursor-acp-1",
                request_id="cursor-acp-request-1",
                workspace=self._claim(isolated, workspace),
                requested_model="cursor-grok-4.6-high",
                catalog=advertised_catalog_from_runtime_models(GROK_MODELS),
            )
            with self.assertRaisesRegex(ValidationError, "missing"):
                CursorAcpController(Path(temporary), runner=runner).require_observation()
            self.assertEqual(runtime.start_calls, [])

    def test_structured_launch_factory_selects_model_and_persists_two_turns(self):
        with tempfile.TemporaryDirectory() as temporary:
            isolated = _private_root(temporary)
            workspace = Path(temporary).resolve() / "workspace"
            workspace.mkdir()
            runtime = CursorAcpSyntheticRuntime(
                handle=_handle(workspace),
                models={
                    "currentModelId": "grok-4.6[effort=low,fast=true]",
                    "availableModelIds": GROK_MODELS["availableModelIds"],
                },
            )
            holder = {}

            def factory(**kwargs):
                runner = build_cursor_acp_candidate_runner(
                    runtime=runtime,
                    isolated_root=isolated,
                    conversation_id="conv-cursor-acp-1",
                    request_id="cursor-acp-request-1",
                    session_mode=SESSION_MODE_PERSISTENT,
                    finish_policy=FINISH_POLICY_RETAIN,
                    **kwargs,
                )
                holder["runner"] = runner
                return runner

            contract = type("Contract", (), {})()
            contract.repo = workspace
            contract.requested_model = "cursor-grok-4.6-high"
            contract.target = "cursor"
            contract.controller = "puppet-owner"
            with mock.patch(
                "puppet_lib.session._workspace_snapshot",
                return_value={
                    "branch": "codex/example",
                    "head": "a" * 40,
                    "tree": "b" * 40,
                    "dirty": False,
                },
            ):
                launched = _cursor_acp_structured_launch(
                    session="cursor-acp-session",
                    contract=contract,
                    transport=bind_run_transport("cursor-acp"),
                    state_root=Path(temporary),
                    requested_model="cursor-grok-4.6-high",
                    prompt=CALLER_TASK_TEXT,
                    runtime_factory=factory,
                )
            runner = holder["runner"]
            self.assertTrue(launched["ok"])
            self.assertEqual(runtime.start_calls[0]["text"], CALLER_TASK_TEXT)
            self.assertEqual(runtime.set_model_calls[0]["model"], GROK_HIGH)
            self.assertEqual(runtime.ensure_calls[0]["mode"], SESSION_MODE_PERSISTENT)
            self.assertEqual(len(runtime.close_calls), 0)
            self.assertEqual(runner.persistent_state, "retained")
            first_handle = dict(runner.handle)
            second = runner.next_turn(
                text=SECOND_TURN_TEXT,
                request_id="cursor-acp-request-2",
                expected_workspace=_workspace(workspace),
            )
            self.assertEqual(runtime.start_calls[1]["text"], SECOND_TURN_TEXT)
            self.assertEqual(runtime.start_calls[1]["requestId"], "cursor-acp-request-2")
            self.assertEqual(len(runtime.ensure_calls), 1)
            self.assertEqual(runner.handle["sessionKey"], first_handle["sessionKey"])
            self.assertEqual(runner.handle["backendSessionId"], first_handle["backendSessionId"])
            self.assertEqual(second["session"]["id"], "cursor-acp-session")
            self.assertNotIn(CALLER_TASK_TEXT, str(second))
            self.assertNotIn(SECOND_TURN_TEXT, str(second))
            closed = runner.finish(discard_persistent_state=True)
            self.assertTrue(closed["final_discard"])
            self.assertEqual(closed["persistent_state"], "discarded")
            self.assertEqual(len(runtime.close_calls), 1)
            self.assertTrue(runtime.close_calls[0]["discardPersistentState"])
            self.assertFalse(runner.local_release)

    def test_caller_path_public_runtime_factory_uses_injected_synthetic_peer(self):
        artifact = ROOT / "runs/puppet-dual-acp-controller-runs/20260921/artifacts/acpx-0.18.0.tgz"
        if not artifact.is_file():
            self.skipTest("exact local acpx artifact is task-owned proof input")
        with tempfile.TemporaryDirectory() as temporary:
            isolated = _private_root(temporary)
            workspace = Path(temporary).resolve() / "workspace"
            workspace.mkdir()
            models = {
                "currentModelId": "candidate-default",
                "availableModelIds": ["candidate-default", "candidate-fast"],
            }
            texts = []
            runtime = CursorAcpNodeRuntime(
                workspace=workspace,
                isolated_root=isolated,
                repo_root=ROOT,
                synthetic_peer=True,
            )
            original = runtime.start_turn

            def capture(payload):
                texts.append(payload.get("text"))
                return original(payload)

            runtime.start_turn = capture
            holder = {}

            def factory(**kwargs):
                kwargs.setdefault("catalog", advertised_catalog_from_runtime_models(models))
                runner = build_cursor_acp_candidate_runner(
                    runtime=runtime,
                    isolated_root=isolated,
                    conversation_id="conv-cursor-acp-1",
                    request_id="cursor-acp-request-1",
                    session_mode=SESSION_MODE_PERSISTENT,
                    finish_policy=FINISH_POLICY_RETAIN,
                    **kwargs,
                )
                holder["runner"] = runner
                return runner

            contract = type("Contract", (), {})()
            contract.repo = workspace
            contract.requested_model = "candidate-fast"
            contract.target = "cursor"
            contract.controller = "puppet-owner"
            try:
                with mock.patch(
                    "puppet_lib.session._workspace_snapshot",
                    return_value={
                        "branch": "codex/example",
                        "head": "a" * 40,
                        "tree": "b" * 40,
                        "dirty": False,
                    },
                ):
                    launched = _cursor_acp_structured_launch(
                        session="cursor-acp-session",
                        contract=contract,
                        transport=bind_run_transport("cursor-acp"),
                        state_root=Path(temporary),
                        requested_model="candidate-fast",
                        prompt=CALLER_TASK_TEXT,
                        runtime_factory=factory,
                    )
                runner = holder["runner"]
                self.assertTrue(launched["ok"])
                self.assertEqual(texts, [CALLER_TASK_TEXT])
                self.assertEqual(
                    launched["cursor_acp"]["model"]["observed_model"],
                    "candidate-fast",
                )
                self.assertEqual(runner.persistent_state, "retained")
                second = runner.next_turn(
                    text=SECOND_TURN_TEXT,
                    request_id="cursor-acp-request-2",
                    expected_workspace=_workspace(workspace),
                )
                self.assertEqual(texts, [CALLER_TASK_TEXT, SECOND_TURN_TEXT])
                self.assertEqual(second["terminal_result"]["result_id"], "cursor-acp-request-2")
                self.assertNotIn(CALLER_TASK_TEXT, str(launched))
                closed = runner.finish(discard_persistent_state=True)
                self.assertTrue(closed["final_discard"])
            finally:
                runtime.shutdown()


if __name__ == "__main__":
    unittest.main()
