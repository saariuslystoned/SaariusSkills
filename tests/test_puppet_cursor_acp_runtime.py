from __future__ import annotations

import os
import shlex
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "puppet" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from cursor_acpx import ACPX_ARTIFACT_PATH, claim_isolated_root, load_isolated_root
from puppet_lib.acp_consumer import AcpConsumerOwner
from puppet_lib.cursor_acp import (
    CANDIDATE_RUNTIME_KIND,
    CURSOR_ACP_ARGV_TAIL,
    DEFAULT_CURSOR_EXECUTABLE,
    FINISH_POLICY_RETAIN,
    SESSION_MODE_PERSISTENT,
    SYNTHETIC_AGENT,
    SYNTHETIC_PEER_KIND,
    CursorAcpController,
    CursorAcpNodeRuntime,
    CursorAcpRuntimeRunner,
    CursorAcpSyntheticRuntime,
    advertised_catalog_from_runtime_models,
    build_cursor_acp_candidate_runner,
    cursor_acp_runtime_agent,
    drain_runtime_turn_events,
    map_runtime_models,
    require_cursor_acp_runtime_agent,
    require_runtime_task_text,
    require_unsupported_permission_outcome,
    require_unsupported_question_outcome,
    resolve_cursor_acp_route_binding,
    test_only_cursor_synthetic_route_binding,
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


class _DummyOwnedRuntime:
    def __init__(self, *, shutdown_error=None, exited=True):
        self.shutdown_calls = 0
        self.shutdown_error = shutdown_error
        self.pid = 4343
        self.exited = False
        self._exited_after_shutdown = exited

    def shutdown(self):
        self.shutdown_calls += 1
        if self.shutdown_error is not None:
            raise self.shutdown_error
        self.exited = self._exited_after_shutdown

    def child_process_identity(self):
        return {
            "pid": self.pid,
            "returncode": 0 if self.exited else None,
            "exited": self.exited,
            "kind": "dummy",
        }


class _DummyOwnedRunner:
    def __init__(self, runtime, *, finish_error=None):
        self.runtime = runtime
        self.handle = {"sessionKey": "cursor-acp-session"}
        self.final_discard = False
        self.finish_calls = 0
        self.finish_error = finish_error
        self.session = "cursor-acp-session"
        self.conversation_id = "conv-cursor-acp-1"
        self.request_id = "cursor-acp-request-1"
        self.transport_id = "cursor-acp"

    def finish(self, *, discard_persistent_state=True):
        self.finish_calls += 1
        if self.finish_error is not None:
            raise self.finish_error
        self.final_discard = discard_persistent_state
        return {
            "final_discard": self.final_discard,
            "local_release": False,
            "persistent_state": "discarded" if discard_persistent_state else "retained",
            "backend_discard": "closed",
        }


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
            self.assertEqual(runtime.ensure_calls[0]["agent"], SYNTHETIC_AGENT)
            self.assertEqual(runtime.agent, SYNTHETIC_AGENT)
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
        artifact = ROOT / ACPX_ARTIFACT_PATH
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
                self.assertEqual(runtime.agent, SYNTHETIC_AGENT)
            finally:
                runtime.shutdown()

    def test_runtime_agent_contract_keeps_official_and_synthetic_identities(self):
        self.assertEqual(cursor_acp_runtime_agent(synthetic_peer=False), "cursor")
        self.assertEqual(cursor_acp_runtime_agent(synthetic_peer=True), SYNTHETIC_AGENT)
        self.assertEqual(require_cursor_acp_runtime_agent(type("R", (), {"agent": "cursor"})()), "cursor")
        self.assertEqual(
            require_cursor_acp_runtime_agent(type("R", (), {"agent": SYNTHETIC_AGENT})()),
            SYNTHETIC_AGENT,
        )
        self.assertEqual(
            require_cursor_acp_runtime_agent(type("R", (), {"kind": CANDIDATE_RUNTIME_KIND})()),
            "cursor",
        )
        with self.assertRaisesRegex(ValidationError, "cursor or synthetic candidate"):
            require_cursor_acp_runtime_agent(type("R", (), {"agent": "codex"})())
        with self.assertRaisesRegex(ValidationError, "cursor or synthetic candidate"):
            require_cursor_acp_runtime_agent(type("R", (), {"agent": "antigravity"})())
        with tempfile.TemporaryDirectory() as temporary:
            isolated = _private_root(temporary)
            workspace = Path(temporary).resolve() / "workspace"
            workspace.mkdir()
            with self.assertRaisesRegex(ValidationError, "must stay on the cursor route"):
                CursorAcpNodeRuntime(
                    workspace=workspace,
                    isolated_root=isolated,
                    repo_root=ROOT,
                    synthetic_peer=False,
                    executable=Path(temporary) / "peer",
                    agent=SYNTHETIC_AGENT,
                )

    def test_official_public_registry_ensure_session_selects_cursor_not_candidate(self):
        artifact = ROOT / ACPX_ARTIFACT_PATH
        if not artifact.is_file():
            self.skipTest("exact local acpx artifact is task-owned proof input")
        peer = ROOT / "bridge" / "cursor-acp" / "test" / "candidate-peer.mjs"
        models = {
            "currentModelId": "candidate-default",
            "availableModelIds": ["candidate-default", "candidate-fast"],
        }
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
            executable = Path(temporary) / "official-cursor-peer"
            executable.write_text(
                "#!/bin/sh\nexec /usr/bin/env node %s\n" % shlex.quote(str(peer)),
                encoding="utf-8",
            )
            os.chmod(executable, 0o700)
            runtime = CursorAcpNodeRuntime(
                workspace=workspace,
                isolated_root=isolated,
                repo_root=ROOT,
                synthetic_peer=False,
                executable=executable,
                agent="cursor",
            )
            try:
                self.assertEqual(runtime.kind, CANDIDATE_RUNTIME_KIND)
                self.assertEqual(runtime.agent, "cursor")
                self.assertNotEqual(str(executable), DEFAULT_CURSOR_EXECUTABLE)
                with self.assertRaisesRegex(
                    ValidationError,
                    "Failed to spawn agent command: candidate",
                ):
                    runtime.ensure_session(
                        {
                            "sessionKey": "cursor-acp-mismatch",
                            "agent": SYNTHETIC_AGENT,
                            "mode": "oneshot",
                            "cwd": str(workspace),
                        }
                    )
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
                self.assertEqual(runner.handle["sessionKey"], "cursor-acp-session")
                self.assertNotEqual(runner.handle["backendSessionId"], "conv-cursor-acp-1")
                self.assertNotEqual(runner.handle["acpxRecordId"], "conv-cursor-acp-1")
                self.assertEqual(require_cursor_acp_runtime_agent(runtime), "cursor")
                self.assertFalse(CursorAcpController.available())
                self.assertFalse(CursorAcpRuntimeRunner.available())
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
        artifact = ROOT / ACPX_ARTIFACT_PATH
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

    def test_official_route_binding_uses_approved_cursor_agent_acp_argv(self):
        with tempfile.TemporaryDirectory() as temporary:
            executable = Path(temporary) / "cursor-agent"
            executable.write_text("#!/bin/sh\nexit 0\n")
            os.chmod(executable, 0o700)
            binding = resolve_cursor_acp_route_binding(executable=executable)
            resolved = str(executable.resolve())
            self.assertEqual(binding["kind"], "official_route")
            self.assertEqual(binding["identity"], "cursor-agent-acp")
            self.assertEqual(binding["executable"], resolved)
            self.assertEqual(binding["argv"], [resolved, CURSOR_ACP_ARGV_TAIL])
            self.assertFalse(binding["test_only"])

    def test_default_factory_rejects_arbitrary_executable_without_route_binding(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary).resolve() / "workspace"
            workspace.mkdir()
            contract = type("Contract", (), {})()
            contract.repo = workspace
            contract.requested_model = "candidate-fast"
            contract.target = "cursor"
            contract.controller = "puppet-owner"
            with self.assertRaisesRegex(ValidationError, "arbitrary executable"):
                build_cursor_acp_candidate_runner(
                    session="cursor-acp-session",
                    contract=contract,
                    state_root=Path(temporary),
                    prompt=CALLER_TASK_TEXT,
                    requested_model="candidate-fast",
                    expected_workspace=_workspace(workspace),
                    executable=Path(temporary) / "untrusted",
                )

    def test_default_consumer_owner_lifecycle_uses_public_runtime_and_synthetic_peer(self):
        artifact = ROOT / ACPX_ARTIFACT_PATH
        if not artifact.is_file():
            self.skipTest("exact local acpx artifact is task-owned proof input")
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary).resolve() / "workspace"
            workspace.mkdir()
            contract = type("Contract", (), {})()
            contract.repo = workspace
            contract.requested_model = "candidate-fast"
            contract.target = "cursor"
            contract.controller = "puppet-owner"
            with mock.patch(
                "puppet_lib.cursor_acp.build_cursor_acp_candidate_runner",
                wraps=build_cursor_acp_candidate_runner,
            ) as factory, mock.patch(
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
                    route_resolver=test_only_cursor_synthetic_route_binding,
                )
            factory.assert_called_once()
            self.assertNotIn("runtime", factory.call_args.kwargs)
            self.assertNotIn("runtime_factory", factory.call_args.kwargs)
            self.assertEqual(
                factory.call_args.kwargs["route_binding"]["kind"], SYNTHETIC_PEER_KIND
            )
            owner = launched["owner"]
            continuation = launched["continuation"]
            self.assertIsInstance(owner, AcpConsumerOwner)
            self.assertFalse(owner.available())
            self.assertFalse(CursorAcpController.available())
            self.assertTrue(continuation["process_local"])
            self.assertFalse(continuation["cross_process_resume"])
            self.assertEqual(
                launched["cursor_acp"]["model"]["observed_model"],
                "candidate-fast",
            )
            self.assertNotEqual(continuation["request_id"], continuation["backend_session_id"])
            self.assertNotEqual(continuation["host_conversation_id"], continuation["runtime_session_name"])
            self.assertNotIn(CALLER_TASK_TEXT, str(launched))
            first_backend = continuation["backend_session_id"]
            first_runtime = continuation["runtime_session_name"]
            first_request = continuation["request_id"]
            second = owner.next_turn(
                continuation,
                text=SECOND_TURN_TEXT,
                request_id="cursor-acp-request-2",
                expected_workspace=_workspace(workspace),
            )
            self.assertEqual(
                second["observation"]["terminal_result"]["result_id"],
                "cursor-acp-request-2",
            )
            self.assertEqual(second["continuation"]["backend_session_id"], first_backend)
            self.assertEqual(second["continuation"]["runtime_session_name"], first_runtime)
            self.assertEqual(second["continuation"]["request_id"], "cursor-acp-request-2")
            self.assertNotEqual(second["continuation"]["request_id"], first_request)
            self.assertNotIn(CALLER_TASK_TEXT, str(second))
            self.assertNotIn(SECOND_TURN_TEXT, str(second))
            with self.assertRaisesRegex(ValidationError, "owner does not match"):
                AcpConsumerOwner().next_turn(
                    continuation,
                    text=SECOND_TURN_TEXT,
                    request_id="cursor-acp-request-3",
                )
            closed = owner.finish(continuation)
            self.assertTrue(closed["final_discard"])
            self.assertTrue(closed["child_exit"]["exited"])
            self.assertIsInstance(closed["child_exit"]["pid"], int)
            self.assertIsNotNone(closed["child_exit"]["returncode"])
            with self.assertRaises(OSError):
                os.kill(closed["child_exit"]["pid"], 0)

    def test_wrong_route_binding_and_exceptional_owner_cleanup(self):
        artifact = ROOT / ACPX_ARTIFACT_PATH
        if not artifact.is_file():
            self.skipTest("exact local acpx artifact is task-owned proof input")
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary).resolve() / "workspace"
            workspace.mkdir()
            contract = type("Contract", (), {})()
            contract.repo = workspace
            contract.requested_model = "candidate-fast"
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
                with self.assertRaisesRegex(ValidationError, "trusted route binding"):
                    _cursor_acp_structured_launch(
                        session="cursor-acp-session",
                        contract=contract,
                        transport=bind_run_transport("cursor-acp"),
                        state_root=Path(temporary),
                        requested_model="candidate-fast",
                        prompt=CALLER_TASK_TEXT,
                        route_resolver=lambda: None,
                    )
                launched = _cursor_acp_structured_launch(
                    session="cursor-acp-session",
                    contract=contract,
                    transport=bind_run_transport("cursor-acp"),
                    state_root=Path(temporary),
                    requested_model="candidate-fast",
                    prompt=CALLER_TASK_TEXT,
                    route_resolver=test_only_cursor_synthetic_route_binding,
                )
            owner = launched["owner"]
            continuation = launched["continuation"]
            foreign = _workspace(workspace)
            foreign["path"] = str(Path(temporary).resolve() / "foreign")
            Path(foreign["path"]).mkdir()
            with self.assertRaisesRegex(IdentityError, "bound checkout"):
                owner.next_turn(
                    continuation,
                    text=SECOND_TURN_TEXT,
                    request_id="cursor-acp-request-2",
                    expected_workspace=foreign,
                )
            self.assertIsNotNone(owner.last_child_exit)
            self.assertTrue(owner.last_child_exit["exited"])
            self.assertIsNotNone(owner.last_child_exit["returncode"])
            with self.assertRaisesRegex(ValidationError, "owner is absent"):
                owner.finish(continuation)

    def test_owner_finish_failure_still_shuts_down_and_retires(self):
        runtime = _DummyOwnedRuntime()
        runner = _DummyOwnedRunner(runtime, finish_error=RuntimeError("synthetic finish failure"))
        owner = AcpConsumerOwner()
        continuation = owner.retain(
            runner, route="cursor-acp", expected_workspace=_workspace("/tmp")
        )
        with self.assertRaisesRegex(RuntimeError, "synthetic finish failure"):
            owner.finish(continuation)
        self.assertEqual(runner.finish_calls, 1)
        self.assertEqual(runtime.shutdown_calls, 1)
        self.assertTrue(owner.last_child_exit["exited"])
        self.assertEqual(len(owner._held), 0)
        with self.assertRaisesRegex(ValidationError, "owner is absent"):
            owner.finish(continuation)

    def test_owner_finish_and_shutdown_failure_keeps_ownership(self):
        runtime = _DummyOwnedRuntime(
            shutdown_error=RuntimeError("synthetic shutdown failure"),
        )
        runner = _DummyOwnedRunner(runtime, finish_error=RuntimeError("synthetic finish failure"))
        owner = AcpConsumerOwner()
        continuation = owner.retain(
            runner, route="cursor-acp", expected_workspace=_workspace("/tmp")
        )
        with self.assertRaisesRegex(RuntimeError, "synthetic finish failure"):
            owner.finish(continuation)
        self.assertEqual(runner.finish_calls, 1)
        self.assertEqual(runtime.shutdown_calls, 1)
        self.assertFalse(owner.last_child_exit["exited"])
        self.assertEqual(len(owner._held), 1)
        with self.assertRaisesRegex(ValidationError, "release is uncertain"):
            owner.next_turn(
                continuation,
                text=SECOND_TURN_TEXT,
                request_id="cursor-acp-request-2",
            )
        runtime.shutdown_error = None
        runner.finish_error = None
        closed = owner.finish(continuation)
        self.assertTrue(closed["child_exit"]["exited"])
        self.assertEqual(len(owner._held), 0)

    def test_owner_finish_failure_releases_task_owned_synthetic_child(self):
        artifact = ROOT / ACPX_ARTIFACT_PATH
        if not artifact.is_file():
            self.skipTest("exact local acpx artifact is task-owned proof input")
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary).resolve() / "workspace"
            workspace.mkdir()
            contract = type("Contract", (), {})()
            contract.repo = workspace
            contract.requested_model = "candidate-fast"
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
                    requested_model="candidate-fast",
                    prompt=CALLER_TASK_TEXT,
                    route_resolver=test_only_cursor_synthetic_route_binding,
                )
            owner = launched["owner"]
            continuation = launched["continuation"]
            record = owner.resolve(continuation)
            runner = record["runner"]
            identity = runner.runtime.child_process_identity()
            runner.finish = lambda **_kwargs: (_ for _ in ()).throw(
                RuntimeError("synthetic finish failure")
            )
            with self.assertRaisesRegex(RuntimeError, "synthetic finish failure"):
                owner.finish(continuation)
            self.assertTrue(owner.last_child_exit["exited"])
            self.assertEqual(owner.last_child_exit["pid"], identity["pid"])
            with self.assertRaises(OSError):
                os.kill(identity["pid"], 0)
            with self.assertRaisesRegex(ValidationError, "owner is absent"):
                owner.finish(continuation)

    def test_public_runtime_records_backend_mapping_after_owned_shutdown_reconnect(self):
        artifact = ROOT / ACPX_ARTIFACT_PATH
        if not artifact.is_file():
            self.skipTest("exact local acpx artifact is task-owned proof input")
        models = {
            "currentModelId": "candidate-default",
            "availableModelIds": ["candidate-default", "candidate-fast"],
        }
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
            first_runtime = CursorAcpNodeRuntime(
                workspace=workspace,
                isolated_root=isolated,
                repo_root=ROOT,
                synthetic_peer=True,
            )
            try:
                first_runner = CursorAcpRuntimeRunner(
                    first_runtime,
                    isolated_root=isolated,
                    owner="puppet-owner",
                    session="cursor-acp-session",
                    conversation_id="conv-cursor-acp-1",
                    request_id="cursor-acp-request-1",
                    workspace=_workspace(workspace),
                    requested_model="candidate-fast",
                    text=CALLER_TASK_TEXT,
                    catalog=advertised_catalog_from_runtime_models(models),
                    session_mode=SESSION_MODE_PERSISTENT,
                    finish_policy=FINISH_POLICY_RETAIN,
                )
                first = first_runner.observation()
                self.assertEqual(first["observed_model"]["id"], "candidate-fast")
                first_handle = dict(first_runner.handle)
                first_identity = first_runtime.child_process_identity()
            finally:
                first_runtime.shutdown()
            self.assertTrue(first_runtime.child_process_identity()["exited"])
            with self.assertRaises(OSError):
                os.kill(first_identity["pid"], 0)
            second_runtime = CursorAcpNodeRuntime(
                workspace=workspace,
                isolated_root=isolated,
                repo_root=ROOT,
                synthetic_peer=True,
            )
            try:
                second_runner = CursorAcpRuntimeRunner(
                    second_runtime,
                    isolated_root=isolated,
                    owner="puppet-owner",
                    session="cursor-acp-session",
                    conversation_id="conv-cursor-acp-1",
                    request_id="cursor-acp-request-2",
                    workspace=_workspace(workspace),
                    requested_model="candidate-fast",
                    text=SECOND_TURN_TEXT,
                    catalog=advertised_catalog_from_runtime_models(models),
                    session_mode=SESSION_MODE_PERSISTENT,
                    finish_policy=FINISH_POLICY_RETAIN,
                )
                second = second_runner.observation()
                self.assertEqual(second["observed_model"]["id"], "candidate-fast")
                self.assertEqual(second_runner.handle["sessionKey"], first_handle["sessionKey"])
                mapping = {
                    "previous_backend_session_id": first_handle.get("backendSessionId"),
                    "backend_session_id": second_runner.handle.get("backendSessionId"),
                    "previous_acpx_record_id": first_handle.get("acpxRecordId"),
                    "acpx_record_id": second_runner.handle.get("acpxRecordId"),
                }
                self.assertIsInstance(mapping["previous_backend_session_id"], str)
                self.assertIsInstance(mapping["backend_session_id"], str)
                self.assertNotIn(CALLER_TASK_TEXT, str(second))
                closed = second_runner.finish(discard_persistent_state=True)
                self.assertTrue(closed["final_discard"])
            finally:
                second_runtime.shutdown()
            self.assertTrue(second_runtime.child_process_identity()["exited"])


if __name__ == "__main__":
    unittest.main()
