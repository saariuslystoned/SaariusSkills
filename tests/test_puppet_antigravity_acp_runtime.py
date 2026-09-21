from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "puppet" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from antigravity_acpx import claim_isolated_root, load_isolated_root
from puppet_lib.acp_consumer import AcpConsumerOwner
from puppet_lib.antigravity_acp import (
    ANTIGRAVITY_ROUTE_BINDING_SCHEMA,
    ANTIGRAVITY_ROUTE_IDENTITY,
    ANTIGRAVITY_SANITIZED_ENV_NAMES,
    DEFAULT_ANTIGRAVITY_MODEL,
    OFFICIAL_ROUTE_KIND,
    PROFILE_ENV,
    RUNTIME_ID,
    RUNTIME_VERSION,
    TRANSPORT_ID,
    AntigravityAcpController,
    AntigravityAcpNodeRuntime,
    AntigravityAcpRuntimeRunner,
    AntigravityAcpSyntheticRuntime,
    build_antigravity_acp_candidate_runner,
    current_antigravity_platform_id,
    map_runtime_antigravity_models,
    require_antigravity_acp_route_binding,
    resolve_antigravity_acp_route_binding,
    test_only_antigravity_synthetic_route_binding,
    verified_antigravity_acp_catalog,
)
from puppet_lib.cursor_acp import (
    FINISH_POLICY_RETAIN,
    SESSION_MODE_PERSISTENT,
    SYNTHETIC_PEER_KIND,
    require_runtime_task_text,
    test_only_cursor_synthetic_route_binding,
)
from puppet_lib.cursor_acp import (
    drain_runtime_turn_events,
    require_unsupported_permission_outcome,
    require_unsupported_question_outcome,
)
from puppet_lib.errors import IdentityError, UnsupportedError, ValidationError
from puppet_lib.session import _antigravity_acp_structured_launch
from puppet_lib.transport import bind_run_transport


CALLER_TASK_TEXT = "caller task: inspect the owned workspace without echoing bodies"
SECOND_TURN_TEXT = "caller follow-up: continue the same owned session"
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


ENV_AMBIENT_SENTINEL = "PUPPET_TEST_AMBIENT_SENTINEL"
ENV_FORGED_KEY = "PUPPET_TEST_FORGED_API_KEY"
ENV_DUMP_NAME = "puppet-test-only-env-dump.json"
TEST_ONLY_ENV_PEER = """#!/usr/bin/env node
import { writeFileSync } from "node:fs";
import { pathToFileURL } from "node:url";
import path from "node:path";

writeFileSync(path.join(process.cwd(), "puppet-test-only-env-dump.json"), JSON.stringify({
  test_only: true,
  sentinel: process.env.PUPPET_TEST_AMBIENT_SENTINEL ?? null,
  forged_key: process.env.PUPPET_TEST_FORGED_API_KEY ?? null,
  has_path: Object.hasOwn(process.env, "PATH"),
  has_home: Object.hasOwn(process.env, "HOME"),
  has_tmpdir: Object.hasOwn(process.env, "TMPDIR"),
  has_lang: Object.hasOwn(process.env, "LANG"),
  has_gemini_home: Object.hasOwn(process.env, "GEMINI_HOME"),
  has_helper: Object.hasOwn(process.env, "ANTIGRAVITY_HARNESS_PATH"),
  force_file_storage: process.env.AGY_ACP_FORCE_FILE_STORAGE ?? null,
}));
await import(pathToFileURL(process.argv[2]).href);
"""


class _DummyOwnedRuntime:
    def __init__(self, *, shutdown_error=None, exited=True):
        self.shutdown_calls = 0
        self.shutdown_error = shutdown_error
        self.pid = 4242
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
        self.handle = {"sessionKey": "agy-acp-session"}
        self.final_discard = False
        self.finish_calls = 0
        self.finish_error = finish_error
        self.session = "agy-acp-session"
        self.conversation_id = "conv-agy-acp-1"
        self.request_id = "agy-acp-request-1"
        self.transport_id = "antigravity-acp"

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
            "text": CALLER_TASK_TEXT,
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
            self.assertEqual(runtime.start_calls[0]["text"], CALLER_TASK_TEXT)
            self.assertNotIn("antigravity-acp-runtime-turn", runtime.start_calls[0]["text"])
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
                    prompt=CALLER_TASK_TEXT,
                )
            self.assertTrue(launched["ok"])
            self.assertEqual(
                launched["antigravity_acp"]["model"]["observed_id"],
                DEFAULT_ANTIGRAVITY_MODEL,
            )
            self.assertEqual(len(runtime.ensure_calls), 1)
            self.assertEqual(len(runtime.start_calls), 1)
            self.assertEqual(runtime.start_calls[0]["text"], CALLER_TASK_TEXT)
            self.assertNotIn(CALLER_TASK_TEXT, str(launched))
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
            result = controller.caller_result(
                expected_session="agy-acp-session",
                expected_conversation_id="conv-agy-acp-1",
                expected_workspace=_workspace(workspace),
                requested_model=DEFAULT_ANTIGRAVITY_MODEL,
            )
            self.assertEqual(
                result["antigravity_acp"]["model"]["observed_id"],
                DEFAULT_ANTIGRAVITY_MODEL,
            )
            self.assertEqual(runtime.set_model_calls[0]["model"], DEFAULT_ANTIGRAVITY_MODEL)
            unsupported = AntigravityAcpSyntheticRuntime(
                handle=_handle(workspace),
                models={
                    "currentModelId": "gemini-3.1-pro",
                    "availableModelIds": GEMINI_MODELS["availableModelIds"],
                },
                set_model_supported=False,
            )
            missing = _private_root(temporary, "missing-set-model")
            with self.assertRaisesRegex(IdentityError, "does not match"):
                AntigravityAcpController(
                    Path(temporary),
                    runner=self._runner(missing, workspace, unsupported),
                ).caller_result(
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
                text=CALLER_TASK_TEXT,
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
                    text=CALLER_TASK_TEXT,
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
                synthetic_peer=True,
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
                    text=CALLER_TASK_TEXT,
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
                self.assertEqual(runtime.kind, SYNTHETIC_PEER_KIND)
            finally:
                runtime.shutdown()

    def test_missing_and_placeholder_task_text_are_rejected(self):
        with self.assertRaisesRegex(ValidationError, "missing"):
            require_runtime_task_text("")
        with self.assertRaisesRegex(ValidationError, "placeholder"):
            require_runtime_task_text("antigravity-acp-runtime-turn")
        with tempfile.TemporaryDirectory() as temporary:
            isolated = _private_root(temporary)
            workspace = Path(temporary).resolve() / "workspace"
            workspace.mkdir()
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
                workspace=self._claim(isolated, workspace),
                requested_model=DEFAULT_ANTIGRAVITY_MODEL,
                catalog=verified_antigravity_acp_catalog(),
            )
            with self.assertRaisesRegex(ValidationError, "missing"):
                AntigravityAcpController(Path(temporary), runner=runner).require_observation()
            self.assertEqual(runtime.start_calls, [])

    def test_structured_launch_factory_selects_model_and_persists_two_turns(self):
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
            holder = {}

            def factory(**kwargs):
                runner = build_antigravity_acp_candidate_runner(
                    runtime=runtime,
                    isolated_root=isolated,
                    conversation_id="conv-agy-acp-1",
                    request_id="agy-acp-request-1",
                    session_mode=SESSION_MODE_PERSISTENT,
                    finish_policy=FINISH_POLICY_RETAIN,
                    **kwargs,
                )
                holder["runner"] = runner
                return runner

            contract = type("Contract", (), {})()
            contract.repo = workspace
            contract.requested_model = DEFAULT_ANTIGRAVITY_MODEL
            contract.target = "agy"
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
                launched = _antigravity_acp_structured_launch(
                    session="agy-acp-session",
                    contract=contract,
                    transport=bind_run_transport("antigravity-acp"),
                    state_root=Path(temporary),
                    requested_model=DEFAULT_ANTIGRAVITY_MODEL,
                    prompt=CALLER_TASK_TEXT,
                    runtime_factory=factory,
                )
            runner = holder["runner"]
            self.assertTrue(launched["ok"])
            self.assertEqual(runtime.start_calls[0]["text"], CALLER_TASK_TEXT)
            self.assertEqual(runtime.set_model_calls[0]["model"], DEFAULT_ANTIGRAVITY_MODEL)
            self.assertEqual(runtime.ensure_calls[0]["mode"], SESSION_MODE_PERSISTENT)
            self.assertEqual(len(runtime.close_calls), 0)
            self.assertEqual(runner.persistent_state, "retained")
            first_handle = dict(runner.handle)
            second = runner.next_turn(
                text=SECOND_TURN_TEXT,
                request_id="agy-acp-request-2",
                expected_workspace=_workspace(workspace),
            )
            self.assertEqual(runtime.start_calls[1]["text"], SECOND_TURN_TEXT)
            self.assertEqual(len(runtime.ensure_calls), 1)
            self.assertEqual(runner.handle["sessionKey"], first_handle["sessionKey"])
            self.assertEqual(runner.handle["backendSessionId"], first_handle["backendSessionId"])
            self.assertEqual(second["session"]["session_id"], "agy-acp-session")
            self.assertNotIn(CALLER_TASK_TEXT, str(second))
            closed = runner.finish(discard_persistent_state=True)
            self.assertTrue(closed["final_discard"])
            self.assertEqual(len(runtime.close_calls), 1)
            self.assertTrue(runtime.close_calls[0]["discardPersistentState"])

    def test_caller_path_public_runtime_factory_uses_injected_synthetic_peer(self):
        artifact = ROOT / "runs/puppet-dual-acp-controller-runs/20260921/artifacts/acpx-0.18.0.tgz"
        if not artifact.is_file():
            self.skipTest("exact local acpx artifact is task-owned proof input")
        with tempfile.TemporaryDirectory() as temporary:
            isolated = _private_root(temporary)
            workspace = Path(temporary).resolve() / "workspace"
            workspace.mkdir()
            texts = []
            runtime = AntigravityAcpNodeRuntime(
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
                kwargs.setdefault("catalog", verified_antigravity_acp_catalog())
                runner = build_antigravity_acp_candidate_runner(
                    runtime=runtime,
                    isolated_root=isolated,
                    conversation_id="conv-agy-acp-1",
                    request_id="agy-acp-request-1",
                    session_mode=SESSION_MODE_PERSISTENT,
                    finish_policy=FINISH_POLICY_RETAIN,
                    **kwargs,
                )
                holder["runner"] = runner
                return runner

            contract = type("Contract", (), {})()
            contract.repo = workspace
            contract.requested_model = DEFAULT_ANTIGRAVITY_MODEL
            contract.target = "agy"
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
                    launched = _antigravity_acp_structured_launch(
                        session="agy-acp-session",
                        contract=contract,
                        transport=bind_run_transport("antigravity-acp"),
                        state_root=Path(temporary),
                        requested_model=DEFAULT_ANTIGRAVITY_MODEL,
                        prompt=CALLER_TASK_TEXT,
                        runtime_factory=factory,
                    )
                runner = holder["runner"]
                self.assertTrue(launched["ok"])
                self.assertEqual(texts, [CALLER_TASK_TEXT])
                self.assertEqual(
                    launched["antigravity_acp"]["model"]["observed_id"],
                    DEFAULT_ANTIGRAVITY_MODEL,
                )
                second = runner.next_turn(
                    text=SECOND_TURN_TEXT,
                    request_id="agy-acp-request-2",
                    expected_workspace=_workspace(workspace),
                )
                self.assertEqual(texts, [CALLER_TASK_TEXT, SECOND_TURN_TEXT])
                self.assertEqual(second["terminal"]["result_id"], "agy-acp-request-2")
                closed = runner.finish(discard_persistent_state=True)
                self.assertTrue(closed["final_discard"])
            finally:
                runtime.shutdown()

    def test_official_route_binding_uses_pinned_server_not_manifest_executable(self):
        with tempfile.TemporaryDirectory() as temporary:
            runtime_dir = Path(temporary) / "runtime"
            runtime_dir.mkdir()
            platform_id = current_antigravity_platform_id()
            server_name = (
                "agy_acp_server.exe"
                if platform_id.startswith("windows")
                else "agy_acp_server.par"
            )
            helper_name = (
                "localharness_external.exe"
                if platform_id.startswith("windows")
                else "localharness_external"
            )
            decoy = Path(temporary) / "agy"
            decoy.write_text("#!/bin/sh\nexit 0\n")
            os.chmod(decoy, 0o700)
            server = runtime_dir / server_name
            helper = runtime_dir / helper_name
            server.write_text("#!/bin/sh\nexit 0\n")
            helper.write_text("#!/bin/sh\nexit 0\n")
            os.chmod(server, 0o700)
            os.chmod(helper, 0o700)
            gemini_home = Path(temporary) / "gemini-home"
            gemini_home.mkdir()
            binding = resolve_antigravity_acp_route_binding(
                runtime_dir=runtime_dir,
                gemini_home=gemini_home,
                process_env={"PATH": os.environ.get("PATH", "")},
            )
            self.assertEqual(binding["kind"], "official_route")
            self.assertEqual(binding["identity"], "antigravity-acp-server")
            self.assertEqual(binding["executable"], str(server.resolve()))
            self.assertNotEqual(binding["executable"], str(decoy.resolve()))
            self.assertEqual(binding["argv"][0], binding["executable"])
            self.assertEqual(binding["helper"], str(helper.resolve()))
            self.assertEqual(binding["profile_env"], "GEMINI_HOME")
            self.assertEqual(binding["profile_path"], str(gemini_home.resolve()))
            self.assertEqual(binding["process_env"]["GEMINI_HOME"], binding["profile_path"])
            self.assertEqual(
                binding["process_env"]["ANTIGRAVITY_HARNESS_PATH"],
                binding["helper"],
            )

    def test_default_factory_rejects_arbitrary_executable_and_env(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary).resolve() / "workspace"
            workspace.mkdir()
            contract = type("Contract", (), {})()
            contract.repo = workspace
            contract.requested_model = "gemini-3.1-pro"
            contract.target = "agy"
            contract.controller = "puppet-owner"
            with self.assertRaisesRegex(ValidationError, "arbitrary executable"):
                build_antigravity_acp_candidate_runner(
                    session="agy-acp-session",
                    contract=contract,
                    state_root=Path(temporary),
                    prompt=CALLER_TASK_TEXT,
                    requested_model="gemini-3.1-pro",
                    expected_workspace=_workspace(workspace),
                    executable=Path(temporary) / "agy",
                    env={"GEMINI_HOME": str(Path(temporary) / "untrusted")},
                )

    def test_default_consumer_owner_lifecycle_uses_public_runtime_and_synthetic_peer(self):
        artifact = ROOT / "runs/puppet-dual-acp-controller-runs/20260921/artifacts/acpx-0.18.0.tgz"
        if not artifact.is_file():
            self.skipTest("exact local acpx artifact is task-owned proof input")
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary).resolve() / "workspace"
            workspace.mkdir()
            contract = type("Contract", (), {})()
            contract.repo = workspace
            contract.requested_model = "gemini-3.1-pro"
            contract.target = "agy"
            contract.controller = "puppet-owner"
            with mock.patch(
                "puppet_lib.antigravity_acp.build_antigravity_acp_candidate_runner",
                wraps=build_antigravity_acp_candidate_runner,
            ) as factory, mock.patch(
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
                    requested_model="gemini-3.1-pro",
                    prompt=CALLER_TASK_TEXT,
                    route_resolver=test_only_antigravity_synthetic_route_binding,
                )
            factory.assert_called_once()
            self.assertNotIn("runtime", factory.call_args.kwargs)
            self.assertEqual(
                factory.call_args.kwargs["route_binding"]["kind"], SYNTHETIC_PEER_KIND
            )
            owner = launched["owner"]
            continuation = launched["continuation"]
            self.assertIsInstance(owner, AcpConsumerOwner)
            self.assertFalse(owner.available())
            self.assertFalse(AntigravityAcpController.available())
            self.assertEqual(
                launched["antigravity_acp"]["model"]["observed_id"],
                "gemini-3.1-pro",
            )
            self.assertNotEqual(continuation["request_id"], continuation["backend_session_id"])
            self.assertNotEqual(
                continuation["host_conversation_id"],
                continuation["runtime_session_name"],
            )
            self.assertNotIn(CALLER_TASK_TEXT, str(launched))
            first_backend = continuation["backend_session_id"]
            first_request = continuation["request_id"]
            second = owner.next_turn(
                continuation,
                text=SECOND_TURN_TEXT,
                request_id="agy-acp-request-2",
                expected_workspace=_workspace(workspace),
            )
            self.assertEqual(second["observation"]["terminal"]["result_id"], "agy-acp-request-2")
            self.assertEqual(second["continuation"]["backend_session_id"], first_backend)
            self.assertEqual(second["continuation"]["request_id"], "agy-acp-request-2")
            self.assertNotEqual(second["continuation"]["request_id"], first_request)
            self.assertNotIn(CALLER_TASK_TEXT, str(second))
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
                    _antigravity_acp_structured_launch(
                        session="agy-wrong-binding",
                        contract=contract,
                        transport=bind_run_transport("antigravity-acp"),
                        state_root=Path(temporary),
                        requested_model="gemini-3.1-pro",
                        prompt=CALLER_TASK_TEXT,
                        route_resolver=test_only_cursor_synthetic_route_binding,
                    )
            closed = owner.finish(continuation)
            self.assertTrue(closed["final_discard"])
            self.assertTrue(closed["child_exit"]["exited"])
            self.assertIsInstance(closed["child_exit"]["pid"], int)
            self.assertIsNotNone(closed["child_exit"]["returncode"])
            with self.assertRaises(OSError):
                os.kill(closed["child_exit"]["pid"], 0)

    def test_wrong_owner_and_exceptional_cleanup(self):
        artifact = ROOT / "runs/puppet-dual-acp-controller-runs/20260921/artifacts/acpx-0.18.0.tgz"
        if not artifact.is_file():
            self.skipTest("exact local acpx artifact is task-owned proof input")
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary).resolve() / "workspace"
            workspace.mkdir()
            contract = type("Contract", (), {})()
            contract.repo = workspace
            contract.requested_model = "gemini-3.1-pro"
            contract.target = "agy"
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
                launched = _antigravity_acp_structured_launch(
                    session="agy-acp-session",
                    contract=contract,
                    transport=bind_run_transport("antigravity-acp"),
                    state_root=Path(temporary),
                    requested_model="gemini-3.1-pro",
                    prompt=CALLER_TASK_TEXT,
                    route_resolver=test_only_antigravity_synthetic_route_binding,
                )
            owner = launched["owner"]
            continuation = launched["continuation"]
            with self.assertRaisesRegex(ValidationError, "owner does not match"):
                AcpConsumerOwner().next_turn(
                    continuation,
                    text=SECOND_TURN_TEXT,
                    request_id="agy-acp-request-2",
                )
            foreign = _workspace(workspace)
            foreign["path"] = str(Path(temporary).resolve() / "foreign")
            Path(foreign["path"]).mkdir()
            with self.assertRaisesRegex(IdentityError, "bound checkout"):
                owner.next_turn(
                    continuation,
                    text=SECOND_TURN_TEXT,
                    request_id="agy-acp-request-2",
                    expected_workspace=foreign,
                )
            self.assertTrue(owner.last_child_exit["exited"])
            self.assertIsNotNone(owner.last_child_exit["returncode"])

    def test_owner_finish_failure_still_shuts_down_and_retires(self):
        runtime = _DummyOwnedRuntime()
        runner = _DummyOwnedRunner(runtime, finish_error=RuntimeError("synthetic finish failure"))
        owner = AcpConsumerOwner()
        continuation = owner.retain(
            runner, route="antigravity-acp", expected_workspace=_workspace("/tmp")
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
            runner, route="antigravity-acp", expected_workspace=_workspace("/tmp")
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
                request_id="agy-acp-request-2",
            )
        runtime.shutdown_error = None
        runner.finish_error = None
        closed = owner.finish(continuation)
        self.assertTrue(closed["child_exit"]["exited"])
        self.assertEqual(len(owner._held), 0)

    def test_owner_finish_failure_releases_task_owned_synthetic_child(self):
        artifact = ROOT / "runs/puppet-dual-acp-controller-runs/20260921/artifacts/acpx-0.18.0.tgz"
        if not artifact.is_file():
            self.skipTest("exact local acpx artifact is task-owned proof input")
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary).resolve() / "workspace"
            workspace.mkdir()
            contract = type("Contract", (), {})()
            contract.repo = workspace
            contract.requested_model = "gemini-3.1-pro"
            contract.target = "agy"
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
                launched = _antigravity_acp_structured_launch(
                    session="agy-acp-session",
                    contract=contract,
                    transport=bind_run_transport("antigravity-acp"),
                    state_root=Path(temporary),
                    requested_model="gemini-3.1-pro",
                    prompt=CALLER_TASK_TEXT,
                    route_resolver=test_only_antigravity_synthetic_route_binding,
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

    def test_owner_finish_and_shutdown_failure_keeps_synthetic_child(self):
        artifact = ROOT / "runs/puppet-dual-acp-controller-runs/20260921/artifacts/acpx-0.18.0.tgz"
        if not artifact.is_file():
            self.skipTest("exact local acpx artifact is task-owned proof input")
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary).resolve() / "workspace"
            workspace.mkdir()
            contract = type("Contract", (), {})()
            contract.repo = workspace
            contract.requested_model = "gemini-3.1-pro"
            contract.target = "agy"
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
                launched = _antigravity_acp_structured_launch(
                    session="agy-acp-session",
                    contract=contract,
                    transport=bind_run_transport("antigravity-acp"),
                    state_root=Path(temporary),
                    requested_model="gemini-3.1-pro",
                    prompt=CALLER_TASK_TEXT,
                    route_resolver=test_only_antigravity_synthetic_route_binding,
                )
            owner = launched["owner"]
            continuation = launched["continuation"]
            record = owner.resolve(continuation)
            runner = record["runner"]
            runtime = runner.runtime
            identity = runtime.child_process_identity()
            original_finish = runner.finish
            original_shutdown = runtime.shutdown
            runner.finish = lambda **_kwargs: (_ for _ in ()).throw(
                RuntimeError("synthetic finish failure")
            )
            runtime.shutdown = lambda: (_ for _ in ()).throw(
                RuntimeError("synthetic shutdown failure")
            )
            try:
                with self.assertRaisesRegex(RuntimeError, "synthetic finish failure"):
                    owner.finish(continuation)
                self.assertFalse(owner.last_child_exit["exited"])
                self.assertEqual(len(owner._held), 1)
                os.kill(identity["pid"], 0)
                with self.assertRaisesRegex(ValidationError, "release is uncertain"):
                    owner.next_turn(
                        continuation,
                        text=SECOND_TURN_TEXT,
                        request_id="agy-acp-request-2",
                    )
            finally:
                runner.finish = original_finish
                runtime.shutdown = original_shutdown
                closed = owner.finish(continuation)
            self.assertTrue(closed["child_exit"]["exited"])
            with self.assertRaises(OSError):
                os.kill(identity["pid"], 0)

    def test_official_route_binding_rejects_forged_process_env(self):
        with tempfile.TemporaryDirectory() as temporary:
            runtime_dir = Path(temporary) / "runtime"
            runtime_dir.mkdir()
            platform_id = current_antigravity_platform_id()
            server_name = (
                "agy_acp_server.exe"
                if platform_id.startswith("windows")
                else "agy_acp_server.par"
            )
            helper_name = (
                "localharness_external.exe"
                if platform_id.startswith("windows")
                else "localharness_external"
            )
            server = runtime_dir / server_name
            helper = runtime_dir / helper_name
            server.write_text("#!/bin/sh\nexit 0\n")
            helper.write_text("#!/bin/sh\nexit 0\n")
            os.chmod(server, 0o700)
            os.chmod(helper, 0o700)
            gemini_home = Path(temporary) / "gemini-home"
            gemini_home.mkdir()
            binding = resolve_antigravity_acp_route_binding(
                runtime_dir=runtime_dir,
                gemini_home=gemini_home,
                process_env={"PATH": os.environ.get("PATH", "")},
            )
            forged = dict(binding)
            forged["process_env"] = dict(binding["process_env"])
            forged["process_env"][ENV_FORGED_KEY] = "should-not-leak"
            with self.assertRaisesRegex(ValidationError, "process environment"):
                require_antigravity_acp_route_binding(forged)
            with self.assertRaisesRegex(ValidationError, "process environment"):
                AntigravityAcpNodeRuntime(
                    workspace=Path(temporary),
                    isolated_root=Path(temporary) / "isolated",
                    repo_root=ROOT,
                    env=forged["process_env"],
                    executable=server,
                )

    def test_official_candidate_child_gets_allowed_env_only(self):
        artifact = ROOT / "runs/puppet-dual-acp-controller-runs/20260921/artifacts/acpx-0.18.0.tgz"
        if not artifact.is_file():
            self.skipTest("exact local acpx artifact is task-owned proof input")
        node = shutil.which("node")
        if not node:
            self.skipTest("node is required for the official candidate env proof")
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary).resolve() / "workspace"
            workspace.mkdir()
            isolated = _private_root(temporary)
            helper = Path(temporary) / "localharness_external"
            helper.write_text("#!/bin/sh\nexit 0\n")
            os.chmod(helper, 0o700)
            wrapper = Path(temporary) / "puppet-test-only-env-peer.mjs"
            wrapper.write_text(TEST_ONLY_ENV_PEER)
            os.chmod(wrapper, 0o700)
            peer = ROOT / "bridge/antigravity-acp/test/candidate-peer.mjs"
            gemini_home = Path(temporary) / "gemini-home"
            gemini_home.mkdir()
            synth_home = Path(temporary) / "home"
            synth_tmp = Path(temporary) / "tmp"
            synth_home.mkdir()
            synth_tmp.mkdir()
            process_env = {
                "PATH": os.environ.get("PATH") or "/usr/bin:/bin",
                "HOME": str(synth_home),
                "TMPDIR": str(synth_tmp),
                "LANG": "C.UTF-8",
                "GEMINI_HOME": str(gemini_home.resolve()),
                "AGY_ACP_FORCE_FILE_STORAGE": "1",
                "ANTIGRAVITY_HARNESS_PATH": str(helper.resolve()),
            }
            binding = require_antigravity_acp_route_binding(
                {
                    "schema": ANTIGRAVITY_ROUTE_BINDING_SCHEMA,
                    "route": TRANSPORT_ID,
                    "kind": OFFICIAL_ROUTE_KIND,
                    "agent": "antigravity",
                    "transport": "acp",
                    "identity": ANTIGRAVITY_ROUTE_IDENTITY,
                    "platform_id": current_antigravity_platform_id(),
                    "runtime_id": RUNTIME_ID,
                    "runtime_version": RUNTIME_VERSION,
                    "executable": node,
                    "argv": [node, str(wrapper), str(peer)],
                    "helper": str(helper.resolve()),
                    "profile_env": PROFILE_ENV,
                    "profile_path": str(gemini_home.resolve()),
                    "process_env_names": list(ANTIGRAVITY_SANITIZED_ENV_NAMES),
                    "process_env": process_env,
                    "test_only": False,
                }
            )
            ambient = {
                ENV_AMBIENT_SENTINEL: "ambient-sentinel-value",
                ENV_FORGED_KEY: "should-not-leak",
            }
            contract = type("Contract", (), {})()
            contract.repo = workspace
            contract.requested_model = DEFAULT_ANTIGRAVITY_MODEL
            contract.target = "agy"
            contract.controller = "puppet-owner"
            with mock.patch.dict(os.environ, ambient, clear=False):
                runner = build_antigravity_acp_candidate_runner(
                    session="agy-acp-session",
                    contract=contract,
                    state_root=Path(temporary),
                    prompt=CALLER_TASK_TEXT,
                    requested_model=DEFAULT_ANTIGRAVITY_MODEL,
                    expected_workspace=_workspace(workspace),
                    catalog=verified_antigravity_acp_catalog(),
                    route_binding=binding,
                    isolated_root=isolated,
                )
                try:
                    observation = runner.observation()
                    self.assertEqual(observation["session"]["session_id"], "agy-acp-session")
                    dump = json.loads((workspace / ENV_DUMP_NAME).read_text())
                    self.assertTrue(dump["test_only"])
                    self.assertIsNone(dump["sentinel"])
                    self.assertIsNone(dump["forged_key"])
                    self.assertTrue(dump["has_path"])
                    self.assertTrue(dump["has_home"])
                    self.assertTrue(dump["has_tmpdir"])
                    self.assertTrue(dump["has_lang"])
                    self.assertTrue(dump["has_gemini_home"])
                    self.assertTrue(dump["has_helper"])
                    self.assertEqual(dump["force_file_storage"], "1")
                finally:
                    runner.runtime.shutdown()


if __name__ == "__main__":
    unittest.main()
