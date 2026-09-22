from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "puppet" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from antigravity_acpx import ACPX_ARTIFACT_PATH, claim_isolated_root, load_isolated_root
from puppet_lib.acp_consumer import AcpConsumerOwner
from puppet_lib.antigravity_acp import (
    ANTIGRAVITY_ROUTE_BINDING_SCHEMA,
    ANTIGRAVITY_ROUTE_IDENTITY,
    ANTIGRAVITY_SANITIZED_ENV_NAMES,
    CANDIDATE_PROMPT_TIMEOUT_MS,
    DEFAULT_ANTIGRAVITY_MODEL,
    OFFICIAL_ROUTE_KIND,
    PROFILE_ENV,
    RECEIPT_DURABILITY_DURABLE,
    RECEIPT_DURABILITY_NONDURABLE,
    RUNTIME_ID,
    RUNTIME_VERSION,
    STARTUP_TIMEOUT_MS,
    TRANSPORT_ID,
    AntigravityAcpController,
    AntigravityAcpNodeRuntime,
    AntigravityAcpRuntimeRunner,
    AntigravityAcpSyntheticRuntime,
    bound_receipt_durability,
    build_antigravity_acp_candidate_runner,
    current_antigravity_platform_id,
    map_runtime_antigravity_models,
    require_antigravity_acp_route_binding,
    require_host_permission_outcome,
    resolve_antigravity_acp_route_binding,
    test_only_antigravity_synthetic_route_binding,
    verified_antigravity_acp_catalog,
    HOST_PERMISSION_SCHEMA,
)
from puppet_lib.cursor_acp import (
    FINISH_POLICY_DISCARD,
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
FIXTURE_OWNED_RELATIVE = "bin/normalize-lines.mjs"
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
            "intended_write_relative": FIXTURE_OWNED_RELATIVE,
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
            self.assertEqual(runtime.start_calls[0]["timeoutMs"], CANDIDATE_PROMPT_TIMEOUT_MS)
            self.assertNotIn("antigravity-acp-runtime-turn", runtime.start_calls[0]["text"])
            self.assertEqual(runner.terminal_receipt["status"], "completed")
            self.assertEqual(runner.terminal_receipt["stop_reason"], "end_turn")
            self.assertEqual(runner.terminal_receipt["timeout_ms"], CANDIDATE_PROMPT_TIMEOUT_MS)
            self.assertEqual(
                result["antigravity_acp"]["terminal"]["stop_reason"],
                "end_turn",
            )
            self.assertGreaterEqual(len(runtime.status_calls), 1)
            self.assertEqual(len(runtime.close_calls), 1)
            self.assertTrue(runtime.close_calls[0]["discardPersistentState"])
            self.assertEqual(runner.discarded_events["body_retained"], False)
            self.assertNotIn("secret-body", str(runner.discarded_events))
            self.assertFalse(AntigravityAcpController.available())
            self.assertFalse(AntigravityAcpRuntimeRunner.available())

    def test_failed_turn_receipt_is_kept_when_cleanup_also_errors(self):
        with tempfile.TemporaryDirectory() as temporary:
            isolated = _private_root(temporary)
            workspace = Path(temporary).resolve() / "workspace"
            workspace.mkdir()
            runtime = AntigravityAcpSyntheticRuntime(
                handle=_handle(workspace),
                models=GEMINI_MODELS,
                result={
                    "status": "failed",
                    "stopReason": "timeout",
                    "errorCode": "ACP_TURN_FAILED",
                },
                close_error=RuntimeError("cleanup also failed"),
            )
            runner = self._runner(isolated, workspace, runtime, halt=True)
            with self.assertRaisesRegex(RuntimeError, "cleanup also failed"):
                runner.observation()
            self.assertEqual(runner.terminal_receipt["status"], "failed")
            self.assertEqual(runner.terminal_receipt["stop_reason"], "timeout")
            self.assertEqual(runner.terminal_receipt["error_code"], "ACP_TURN_FAILED")
            self.assertEqual(runner.terminal_receipt["timeout_ms"], CANDIDATE_PROMPT_TIMEOUT_MS)
            self.assertIsNotNone(runner._observation)
            self.assertEqual(runner._observation["terminal"]["status"], "failed")
            self.assertEqual(runner._observation["terminal"]["stop_reason"], "timeout")
            self.assertEqual(runtime.start_calls[0]["timeoutMs"], CANDIDATE_PROMPT_TIMEOUT_MS)
            events = [
                json.loads(line)
                for line in (isolated / "ownership.events.jsonl").read_text().splitlines()
            ]
            turn_events = [item for item in events if item.get("event") == "runtime_turn_observed"]
            self.assertEqual(turn_events[-1]["status"], "failed")
            self.assertEqual(turn_events[-1]["stop_reason"], "timeout")
            self.assertEqual(turn_events[-1]["error_code"], "ACP_TURN_FAILED")
            self.assertNotIn("prompt", turn_events[-1])

    def test_successful_turn_receipt_persist_is_durable(self):
        with tempfile.TemporaryDirectory() as temporary:
            isolated = _private_root(temporary)
            workspace = Path(temporary).resolve() / "workspace"
            workspace.mkdir()
            runtime = AntigravityAcpSyntheticRuntime(
                handle=_handle(workspace),
                models=GEMINI_MODELS,
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
            self.assertEqual(result["receipt_durability"], RECEIPT_DURABILITY_DURABLE)
            self.assertTrue(result["durable"])
            self.assertEqual(runner.receipt_durability, bound_receipt_durability(written=True))
            self.assertEqual(runner.terminal_receipt["status"], "completed")
            self.assertEqual(runner.terminal_receipt["stop_reason"], "end_turn")
            self.assertEqual(result["antigravity_acp"]["terminal"]["status"], "completed")
            self.assertEqual(result["antigravity_acp"]["terminal"]["stop_reason"], "end_turn")
            self.assertEqual(len(runtime.close_calls), 1)
            events = [
                json.loads(line)
                for line in (isolated / "ownership.events.jsonl").read_text().splitlines()
            ]
            turn_events = [item for item in events if item.get("event") == "runtime_turn_observed"]
            self.assertEqual(turn_events[-1]["status"], "completed")
            self.assertEqual(turn_events[-1]["stop_reason"], "end_turn")
            self.assertNotIn("receipt_durability", turn_events[-1])
            self.assertTrue(any(item.get("event") == "cleanup_completed" for item in events))

    def test_failed_turn_receipt_persist_is_nondurable_and_preserves_task_outcome(self):
        with tempfile.TemporaryDirectory() as temporary:
            isolated = _private_root(temporary)
            workspace = Path(temporary).resolve() / "workspace"
            workspace.mkdir()
            runtime = AntigravityAcpSyntheticRuntime(
                handle=_handle(workspace),
                models=GEMINI_MODELS,
            )
            runner = self._runner(isolated, workspace, runtime, halt=True)
            secret = "synthetic persistence I/O failure token-secret password"
            with mock.patch(
                "antigravity_acpx.persist_turn_receipt",
                side_effect=OSError(secret),
            ):
                controller = AntigravityAcpController(Path(temporary), runner=runner)
                result = controller.caller_result(
                    expected_session="agy-acp-session",
                    expected_conversation_id="conv-agy-acp-1",
                    expected_workspace=_workspace(workspace),
                    requested_model=DEFAULT_ANTIGRAVITY_MODEL,
                    require_halt=True,
                )
            self.assertTrue(result["ok"])
            self.assertEqual(result["receipt_durability"], RECEIPT_DURABILITY_NONDURABLE)
            self.assertFalse(result["durable"])
            self.assertEqual(
                runner.receipt_durability,
                bound_receipt_durability(written=False),
            )
            self.assertEqual(runner.terminal_receipt["status"], "completed")
            self.assertEqual(runner.terminal_receipt["stop_reason"], "end_turn")
            self.assertNotIn("error_code", runner.terminal_receipt)
            self.assertEqual(result["antigravity_acp"]["terminal"]["state"], "halted")
            self.assertEqual(result["antigravity_acp"]["terminal"]["status"], "completed")
            self.assertEqual(result["antigravity_acp"]["terminal"]["stop_reason"], "end_turn")
            self.assertNotIn("error_code", result["antigravity_acp"]["terminal"])
            self.assertEqual(len(runtime.close_calls), 1)
            self.assertTrue(runtime.close_calls[0]["discardPersistentState"])
            self.assertTrue(runner.final_discard)
            self.assertEqual(runner.persistent_state, "discarded")
            self.assertFalse(runner.cleanup_uncertain)
            events = [
                json.loads(line)
                for line in (isolated / "ownership.events.jsonl").read_text().splitlines()
            ]
            turn_events = [item for item in events if item.get("event") == "runtime_turn_observed"]
            self.assertEqual(turn_events, [])
            self.assertTrue(any(item.get("event") == "cleanup_completed" for item in events))
            rendered = json.dumps(
                {
                    "observation": result["antigravity_acp"],
                    "terminal_receipt": runner.terminal_receipt,
                    "receipt_durability": runner.receipt_durability,
                    "caller": result,
                    "events": events,
                }
            )
            self.assertNotIn(secret, rendered)
            self.assertNotIn("token-secret", rendered)

    def test_persist_failure_does_not_overwrite_failed_task_outcome(self):
        with tempfile.TemporaryDirectory() as temporary:
            isolated = _private_root(temporary)
            workspace = Path(temporary).resolve() / "workspace"
            workspace.mkdir()
            runtime = AntigravityAcpSyntheticRuntime(
                handle=_handle(workspace),
                models=GEMINI_MODELS,
                result={
                    "status": "failed",
                    "stopReason": "timeout",
                    "errorCode": "ACP_TURN_FAILED",
                },
            )
            runner = self._runner(isolated, workspace, runtime, halt=True)
            with mock.patch(
                "antigravity_acpx.persist_turn_receipt",
                side_effect=OSError("synthetic persistence I/O failure"),
            ):
                observation = runner.observation()
            self.assertEqual(observation["terminal"]["status"], "failed")
            self.assertEqual(observation["terminal"]["stop_reason"], "timeout")
            self.assertEqual(observation["terminal"]["error_code"], "ACP_TURN_FAILED")
            self.assertEqual(runner.terminal_receipt["status"], "failed")
            self.assertEqual(runner.terminal_receipt["stop_reason"], "timeout")
            self.assertEqual(runner.terminal_receipt["error_code"], "ACP_TURN_FAILED")
            self.assertEqual(
                runner.receipt_durability,
                bound_receipt_durability(written=False),
            )
            self.assertFalse(runner.receipt_durability["durable"])
            self.assertEqual(len(runtime.close_calls), 1)
            events = [
                json.loads(line)
                for line in (isolated / "ownership.events.jsonl").read_text().splitlines()
            ]
            turn_events = [item for item in events if item.get("event") == "runtime_turn_observed"]
            self.assertEqual(turn_events, [])
            self.assertTrue(any(item.get("event") == "cleanup_completed" for item in events))
            self.assertNotIn("synthetic persistence I/O failure", json.dumps(events))

    def test_missing_turn_receipt_write_cannot_claim_durable(self):
        self.assertEqual(
            bound_receipt_durability(written=False),
            {
                "receipt_durability": RECEIPT_DURABILITY_NONDURABLE,
                "durable": False,
            },
        )
        self.assertEqual(
            bound_receipt_durability(written=True),
            {
                "receipt_durability": RECEIPT_DURABILITY_DURABLE,
                "durable": True,
            },
        )
        with tempfile.TemporaryDirectory() as temporary:
            isolated = _private_root(temporary)
            workspace = Path(temporary).resolve() / "workspace"
            workspace.mkdir()
            runtime = AntigravityAcpSyntheticRuntime(
                handle=_handle(workspace),
                models=GEMINI_MODELS,
            )
            runner = self._runner(isolated, workspace, runtime, halt=True)
            self.assertEqual(
                runner.receipt_durability,
                bound_receipt_durability(written=False),
            )
            self.assertFalse(runner.receipt_durability["durable"])
            runner.terminal_receipt = None
            self.assertEqual(
                runner._persist_turn_receipt(),
                bound_receipt_durability(written=False),
            )
            self.assertFalse(runner.receipt_durability["durable"])
            runner.terminal_receipt = {"status": "completed", "stop_reason": "end_turn"}
            with mock.patch(
                "antigravity_acpx.persist_turn_receipt",
                return_value=None,
            ):
                self.assertEqual(
                    runner._persist_turn_receipt(),
                    bound_receipt_durability(written=False),
                )
            self.assertFalse(runner.receipt_durability["durable"])

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
            contract.intended_write_relative = FIXTURE_OWNED_RELATIVE
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
            self.assertEqual(
                runtime.start_calls[0]["intendedRelativePath"],
                FIXTURE_OWNED_RELATIVE,
            )
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
                intended_write_relative=FIXTURE_OWNED_RELATIVE,
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
                    intended_write_relative=FIXTURE_OWNED_RELATIVE,
                ).observation()

    def test_unsupported_backend_close_without_worker_proof_fences(self):
        with tempfile.TemporaryDirectory() as temporary:
            isolated = _private_root(temporary)
            workspace = Path(temporary).resolve() / "workspace"
            workspace.mkdir()
            runtime = AntigravityAcpSyntheticRuntime(
                handle=_handle(workspace),
                models=GEMINI_MODELS,
                unsupported_backend_close=True,
            )
            runner = self._runner(isolated, workspace, runtime)
            controller = AntigravityAcpController(Path(temporary), runner=runner)
            with self.assertRaisesRegex(UnsupportedError, "session/close"):
                controller.require_observation()
            self.assertEqual(runner.backend_discard, "unsupported")
            self.assertEqual(runner.worker_termination, "unknown")
            self.assertTrue(runner.cleanup_uncertain)
            ownership = load_isolated_root(isolated)
            self.assertEqual(ownership["cleanup"], "unknown")
            self.assertTrue(ownership["replacement_blocked"])

    def test_uncertain_cleanup_fences_replacement(self):
        with tempfile.TemporaryDirectory() as temporary:
            isolated = _private_root(temporary)
            workspace = Path(temporary).resolve() / "workspace"
            workspace.mkdir()
            runtime = AntigravityAcpSyntheticRuntime(
                handle=_handle(workspace),
                models=GEMINI_MODELS,
                unsupported_backend_close=True,
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
                    intended_write_relative=FIXTURE_OWNED_RELATIVE,
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
                self.assertEqual(result["antigravity_acp"]["terminal"]["status"], "completed")
                self.assertEqual(result["antigravity_acp"]["terminal"]["stop_reason"], "end_turn")
                self.assertEqual(runner.terminal_receipt["timeout_ms"], CANDIDATE_PROMPT_TIMEOUT_MS)
                self.assertGreaterEqual(len(runner.process_lifecycle["started"]), 1)
                self.assertNotEqual(
                    runner.process_lifecycle["started"][0]["pid"],
                    runtime.child_process_identity()["pid"],
                )
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
            contract.intended_write_relative = FIXTURE_OWNED_RELATIVE
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
            self.assertEqual(
                runtime.start_calls[0]["intendedRelativePath"],
                FIXTURE_OWNED_RELATIVE,
            )
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
        artifact = ROOT / ACPX_ARTIFACT_PATH
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
            contract.intended_write_relative = FIXTURE_OWNED_RELATIVE
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
                self.assertFalse(closed["final_discard"])
                self.assertEqual(closed["backend_discard"], "unsupported")
                self.assertEqual(closed["persistent_state"], "unknown")
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

    def test_factory_requires_task_owned_relative_path_from_contract(self):
        with tempfile.TemporaryDirectory() as temporary:
            isolated = _private_root(temporary)
            workspace = Path(temporary).resolve() / "workspace"
            workspace.mkdir()
            runtime = AntigravityAcpSyntheticRuntime(
                handle=_handle(workspace),
                models=GEMINI_MODELS,
            )
            missing = type("Contract", (), {})()
            missing.repo = workspace
            missing.requested_model = DEFAULT_ANTIGRAVITY_MODEL
            missing.target = "agy"
            missing.controller = "puppet-owner"
            with self.assertRaisesRegex(ValidationError, "intended write relative is missing"):
                build_antigravity_acp_candidate_runner(
                    runtime=runtime,
                    isolated_root=isolated,
                    session="agy-acp-session",
                    contract=missing,
                    state_root=Path(temporary),
                    prompt=CALLER_TASK_TEXT,
                    requested_model=DEFAULT_ANTIGRAVITY_MODEL,
                    expected_workspace=_workspace(workspace),
                )
            owned = "src/owned.mjs"
            contract = type("Contract", (), {})()
            contract.repo = workspace
            contract.requested_model = DEFAULT_ANTIGRAVITY_MODEL
            contract.target = "agy"
            contract.controller = "puppet-owner"
            contract.intended_write_relative = owned
            runner = build_antigravity_acp_candidate_runner(
                runtime=runtime,
                isolated_root=isolated,
                session="agy-acp-session",
                contract=contract,
                state_root=Path(temporary),
                prompt=CALLER_TASK_TEXT,
                requested_model=DEFAULT_ANTIGRAVITY_MODEL,
                expected_workspace=_workspace(workspace),
            )
            runner.observation()
            self.assertEqual(runtime.start_calls[0]["intendedRelativePath"], owned)
            self.assertNotEqual(owned, FIXTURE_OWNED_RELATIVE)

    def _assert_factory_rejects_intended_write_relative_before_side_effects(
        self, *, intended_write_relative, error_regex
    ):
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary).resolve() / "workspace"
            workspace.mkdir()
            contract = type("Contract", (), {})()
            contract.repo = workspace
            contract.requested_model = DEFAULT_ANTIGRAVITY_MODEL
            contract.target = "agy"
            contract.controller = "puppet-owner"
            if intended_write_relative is not None:
                contract.intended_write_relative = intended_write_relative
            isolated = Path(temporary) / "agy-acp-session" / "acp-isolated"
            with mock.patch(
                "puppet_lib.antigravity_acp.claim_antigravity_acp_isolated_root"
            ) as claim, mock.patch(
                "puppet_lib.antigravity_acp.AntigravityAcpNodeRuntime"
            ) as runtime_cls:
                with self.assertRaisesRegex(ValidationError, error_regex):
                    build_antigravity_acp_candidate_runner(
                        session="agy-acp-session",
                        contract=contract,
                        state_root=Path(temporary),
                        prompt=CALLER_TASK_TEXT,
                        requested_model=DEFAULT_ANTIGRAVITY_MODEL,
                        expected_workspace=_workspace(workspace),
                        synthetic_peer=True,
                    )
            claim.assert_not_called()
            runtime_cls.assert_not_called()
            self.assertFalse(isolated.exists())
            self.assertFalse((isolated / "ownership.json").exists())

    def test_factory_rejects_missing_intended_write_relative_before_claim_or_runtime(self):
        self._assert_factory_rejects_intended_write_relative_before_side_effects(
            intended_write_relative=None,
            error_regex="intended write relative is missing",
        )

    def test_factory_rejects_invalid_intended_write_relative_before_claim_or_runtime(self):
        self._assert_factory_rejects_intended_write_relative_before_side_effects(
            intended_write_relative="../escape.mjs",
            error_regex="invalid intended write relative",
        )

    def test_default_factory_rejects_arbitrary_executable_and_env(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary).resolve() / "workspace"
            workspace.mkdir()
            contract = type("Contract", (), {})()
            contract.repo = workspace
            contract.requested_model = "gemini-3.1-pro"
            contract.target = "agy"
            contract.intended_write_relative = FIXTURE_OWNED_RELATIVE
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
        artifact = ROOT / ACPX_ARTIFACT_PATH
        if not artifact.is_file():
            self.skipTest("exact local acpx artifact is task-owned proof input")
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary).resolve() / "workspace"
            workspace.mkdir()
            contract = type("Contract", (), {})()
            contract.repo = workspace
            contract.requested_model = "gemini-3.1-pro"
            contract.target = "agy"
            contract.intended_write_relative = FIXTURE_OWNED_RELATIVE
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
            self.assertFalse(closed["final_discard"])
            self.assertEqual(closed["backend_discard"], "unsupported")
            self.assertEqual(closed["persistent_state"], "unknown")
            self.assertTrue(closed["child_exit"]["exited"])
            self.assertIsInstance(closed["child_exit"]["pid"], int)
            self.assertIsNotNone(closed["child_exit"]["returncode"])
            with self.assertRaises(OSError):
                os.kill(closed["child_exit"]["pid"], 0)

    def test_wrong_owner_and_exceptional_cleanup(self):
        artifact = ROOT / ACPX_ARTIFACT_PATH
        if not artifact.is_file():
            self.skipTest("exact local acpx artifact is task-owned proof input")
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary).resolve() / "workspace"
            workspace.mkdir()
            contract = type("Contract", (), {})()
            contract.repo = workspace
            contract.requested_model = "gemini-3.1-pro"
            contract.target = "agy"
            contract.intended_write_relative = FIXTURE_OWNED_RELATIVE
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
        artifact = ROOT / ACPX_ARTIFACT_PATH
        if not artifact.is_file():
            self.skipTest("exact local acpx artifact is task-owned proof input")
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary).resolve() / "workspace"
            workspace.mkdir()
            contract = type("Contract", (), {})()
            contract.repo = workspace
            contract.requested_model = "gemini-3.1-pro"
            contract.target = "agy"
            contract.intended_write_relative = FIXTURE_OWNED_RELATIVE
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
        artifact = ROOT / ACPX_ARTIFACT_PATH
        if not artifact.is_file():
            self.skipTest("exact local acpx artifact is task-owned proof input")
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary).resolve() / "workspace"
            workspace.mkdir()
            contract = type("Contract", (), {})()
            contract.repo = workspace
            contract.requested_model = "gemini-3.1-pro"
            contract.target = "agy"
            contract.intended_write_relative = FIXTURE_OWNED_RELATIVE
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
        artifact = ROOT / ACPX_ARTIFACT_PATH
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
            contract.intended_write_relative = FIXTURE_OWNED_RELATIVE
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

    def test_public_runtime_records_backend_mapping_after_owned_shutdown_reconnect(self):
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
                session="agy-acp-session",
                conversation_id="conv-agy-acp-1",
            )
            first_runtime = AntigravityAcpNodeRuntime(
                workspace=workspace,
                isolated_root=isolated,
                repo_root=ROOT,
                synthetic_peer=True,
            )
            try:
                first_runner = AntigravityAcpRuntimeRunner(
                    first_runtime,
                    isolated_root=isolated,
                    owner="puppet-owner",
                    session="agy-acp-session",
                    conversation_id="conv-agy-acp-1",
                    request_id="agy-acp-request-1",
                    workspace=_workspace(workspace),
                    requested_model="gemini-3.1-pro",
                    text=CALLER_TASK_TEXT,
                    catalog=verified_antigravity_acp_catalog(),
                    intended_write_relative=FIXTURE_OWNED_RELATIVE,
                    session_mode=SESSION_MODE_PERSISTENT,
                    finish_policy=FINISH_POLICY_RETAIN,
                )
                first = first_runner.observation()
                self.assertEqual(first["model"]["observed_id"], "gemini-3.1-pro")
                first_handle = dict(first_runner.handle)
                first_identity = first_runtime.child_process_identity()
            finally:
                first_runtime.shutdown()
            self.assertTrue(first_runtime.child_process_identity()["exited"])
            with self.assertRaises(OSError):
                os.kill(first_identity["pid"], 0)
            second_runtime = AntigravityAcpNodeRuntime(
                workspace=workspace,
                isolated_root=isolated,
                repo_root=ROOT,
                synthetic_peer=True,
            )
            try:
                second_runner = AntigravityAcpRuntimeRunner(
                    second_runtime,
                    isolated_root=isolated,
                    owner="puppet-owner",
                    session="agy-acp-session",
                    conversation_id="conv-agy-acp-1",
                    request_id="agy-acp-request-2",
                    workspace=_workspace(workspace),
                    requested_model="gemini-3.1-pro",
                    text=SECOND_TURN_TEXT,
                    catalog=verified_antigravity_acp_catalog(),
                    intended_write_relative=FIXTURE_OWNED_RELATIVE,
                    session_mode=SESSION_MODE_PERSISTENT,
                    finish_policy=FINISH_POLICY_RETAIN,
                )
                second = second_runner.observation()
                self.assertEqual(second["model"]["observed_id"], "gemini-3.1-pro")
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
                self.assertFalse(closed["final_discard"])
                self.assertEqual(closed["backend_discard"], "unsupported")
                self.assertEqual(closed["persistent_state"], "unknown")
            finally:
                second_runtime.shutdown()
            self.assertTrue(second_runtime.child_process_identity()["exited"])

    def test_actual_public_runtime_unsupported_close_uses_exact_owned_worker_exit(self):
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
                session="agy-acp-session",
                conversation_id="conv-agy-acp-1",
            )
            runtime = AntigravityAcpNodeRuntime(
                workspace=workspace,
                isolated_root=isolated,
                repo_root=ROOT,
                synthetic_peer=True,
                synthetic_peer_script="unsupported-close-peer.mjs",
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
                    intended_write_relative=FIXTURE_OWNED_RELATIVE,
                    halt=True,
                )
                observation = runner.observation()
                self.assertEqual(observation["model"]["observed_id"], DEFAULT_ANTIGRAVITY_MODEL)
                self.assertEqual(runner.selected_model, DEFAULT_ANTIGRAVITY_MODEL)
                self.assertEqual(runner.current_model, DEFAULT_ANTIGRAVITY_MODEL)
                self.assertEqual(runner.backend_discard, "unsupported")
                self.assertEqual(runner.worker_termination, "proven")
                self.assertTrue(runner.local_release)
                self.assertEqual(runner.persistent_state, "unknown")
                self.assertFalse(runner.final_discard)
                self.assertFalse(runner.cleanup_uncertain)
                self.assertFalse(runner.replacement_blocked)
                self.assertEqual(
                    runner.cleanup_receipt["observed"],
                    "local_worker_terminated_backend_session_discard_unsupported",
                )
                snapshot = runtime.process_lifecycle_snapshot("agy-acp-session")
                self.assertGreaterEqual(len(snapshot["started"]), 1)
                self.assertEqual(len(snapshot["started"]), len(snapshot["exits"]))
                ownership = load_isolated_root(isolated)
                self.assertEqual(ownership["cleanup"], "owned")
                self.assertFalse(ownership["replacement_blocked"])
                events = [
                    json.loads(line)
                    for line in (isolated / "ownership.events.jsonl").read_text().splitlines()
                ]
                self.assertTrue(any(item.get("event") == "runtime_models_observed" for item in events))
                cleanup = [item for item in events if item.get("event") == "cleanup_completed"][-1]
                self.assertEqual(cleanup["backendSessionDiscard"], "unsupported")
                self.assertEqual(cleanup["persistent_state"], "unknown")
                self.assertTrue(cleanup["local_release"])
                self.assertFalse(cleanup["final_discard"])
            finally:
                runtime.shutdown()

    def test_actual_public_runtime_surviving_unsupported_close_fences_and_preserves_models(self):
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
                session="agy-acp-session",
                conversation_id="conv-agy-acp-1",
            )
            runtime = AntigravityAcpNodeRuntime(
                workspace=workspace,
                isolated_root=isolated,
                repo_root=ROOT,
                synthetic_peer=True,
                synthetic_peer_script="unsupported-close-peer.mjs",
                synthetic_peer_survive=True,
            )
            started = []
            original_close = runtime.close

            def injected_close(payload):
                error = ValidationError(
                    "Agent does not support session/close for agy-acp-session."
                )
                error.code = "ACP_BACKEND_UNSUPPORTED_CONTROL"
                raise error

            runtime.close = injected_close
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
                    intended_write_relative=FIXTURE_OWNED_RELATIVE,
                    session_mode=SESSION_MODE_PERSISTENT,
                    finish_policy=FINISH_POLICY_DISCARD,
                )
                runner.worker_exit_wait_ms = 250
                with self.assertRaisesRegex(ValidationError, "session/close"):
                    runner.observation()
                self.assertEqual(runner.selected_model, DEFAULT_ANTIGRAVITY_MODEL)
                self.assertEqual(runner.current_model, DEFAULT_ANTIGRAVITY_MODEL)
                self.assertEqual(runner.backend_discard, "unsupported")
                self.assertEqual(runner.worker_termination, "unknown")
                self.assertTrue(runner.cleanup_uncertain)
                self.assertTrue(runner.replacement_blocked)
                snapshot = runtime.process_lifecycle_snapshot("agy-acp-session")
                started = snapshot.get("started") or []
                self.assertGreaterEqual(len(started), 1)
                self.assertEqual(snapshot.get("exits"), [])
                ownership = load_isolated_root(isolated)
                self.assertEqual(ownership["cleanup"], "unknown")
                self.assertTrue(ownership["replacement_blocked"])
                events = [
                    json.loads(line)
                    for line in (isolated / "ownership.events.jsonl").read_text().splitlines()
                ]
                models = [item for item in events if item.get("event") == "runtime_models_observed"]
                unknown = [item for item in events if item.get("event") == "cleanup_unknown"][-1]
                self.assertEqual(models[-1]["selected_model"], DEFAULT_ANTIGRAVITY_MODEL)
                self.assertEqual(models[-1]["current_model"], DEFAULT_ANTIGRAVITY_MODEL)
                self.assertEqual(unknown["backendSessionDiscard"], "unsupported")
                self.assertTrue(unknown["replacement_blocked"])
            finally:
                runtime.close = original_close
                runtime.shutdown()
                for worker in started:
                    try:
                        os.kill(worker["pid"], 9)
                    except OSError:
                        pass

    def test_actual_public_runtime_binds_prompt_timeout_and_retains_failure(self):
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
                session="agy-acp-session",
                conversation_id="conv-agy-acp-1",
            )
            runtime = AntigravityAcpNodeRuntime(
                workspace=workspace,
                isolated_root=isolated,
                repo_root=ROOT,
                synthetic_peer=True,
                synthetic_peer_hang_prompt=True,
                startup_timeout_ms=STARTUP_TIMEOUT_MS,
            )
            try:
                runner = AntigravityAcpRuntimeRunner(
                    runtime,
                    isolated_root=isolated,
                    owner="puppet-owner",
                    session="agy-acp-session",
                    conversation_id="conv-agy-acp-1",
                    request_id="agy-acp-request-timeout",
                    workspace=_workspace(workspace),
                    requested_model=DEFAULT_ANTIGRAVITY_MODEL,
                    text=CALLER_TASK_TEXT,
                    catalog=verified_antigravity_acp_catalog(),
                    intended_write_relative=FIXTURE_OWNED_RELATIVE,
                    session_mode=SESSION_MODE_PERSISTENT,
                    finish_policy=FINISH_POLICY_RETAIN,
                    prompt_timeout_ms=1_000,
                )
                started_at = time.monotonic()
                observation = runner.observation()
                self.assertEqual(observation["terminal"]["status"], "failed")
                self.assertEqual(runner.terminal_receipt["status"], "failed")
                self.assertEqual(runner.terminal_receipt["timeout_ms"], 1_000)
                self.assertTrue(runner.terminal_receipt.get("error_code"))
                self.assertGreaterEqual(len(runner.process_lifecycle["started"]), 1)
                self.assertNotEqual(
                    runner.process_lifecycle["started"][0]["pid"],
                    runtime.child_process_identity()["pid"],
                )
                events = [
                    json.loads(line)
                    for line in (isolated / "ownership.events.jsonl").read_text().splitlines()
                ]
                turn_events = [
                    item for item in events if item.get("event") == "runtime_turn_observed"
                ]
                self.assertEqual(turn_events[-1]["timeout_ms"], 1_000)
                self.assertEqual(turn_events[-1]["status"], "failed")
                self.assertNotIn("prompt", str(turn_events[-1]))
                self.assertLess(time.monotonic() - started_at, 15.0)
            finally:
                runtime.shutdown()

    def test_host_permission_outcome_is_body_free_and_one_time(self):
        allowed = require_host_permission_outcome(
            {
                "schema": HOST_PERMISSION_SCHEMA,
                "outcome": "allow_once",
                "permission_kind": "edit",
                "kind": "edit",
                "kind_source": "standardized",
                "id_class": "opaque",
                "path_source": "raw_input",
                "path_cardinality": "one",
                "path_class": "intended",
                "offered_option_kinds": ["allow_once", "reject_once"],
                "reason": "granted_once",
                "grant_count": 1,
                "allowed": True,
                "persisted": False,
                "approve_all": False,
                "os_sandbox": False,
                "fs": False,
                "terminal": False,
                "ordinary_launch": "unavailable",
                "body_retained": False,
                "invented_decision": None,
                "title": "write bin/normalize-lines.mjs",
                "rawInput": {"path": "/secret/bin/normalize-lines.mjs"},
                "toolCallId": "call_should_not_retain",
            }
        )
        self.assertEqual(allowed["outcome"], "allow_once")
        self.assertEqual(allowed["permission_kind"], "edit")
        self.assertEqual(allowed["kind"], "edit")
        self.assertEqual(allowed["kind_source"], "standardized")
        self.assertEqual(allowed["id_class"], "opaque")
        self.assertEqual(allowed["path_source"], "raw_input")
        self.assertEqual(allowed["reason"], "granted_once")
        self.assertTrue(allowed["allowed"])
        self.assertFalse(allowed["os_sandbox"])
        self.assertEqual(allowed["decision_count"], 1)
        self.assertFalse(allowed["decisions_truncated"])
        self.assertNotIn("options", allowed)
        self.assertNotIn("title", allowed)
        self.assertNotIn("rawInput", allowed)
        self.assertNotIn("toolCallId", allowed)
        serialized = json.dumps(allowed)
        self.assertNotIn("/secret/", serialized)
        self.assertNotIn("call_should_not_retain", serialized)
        self.assertNotIn("write bin/normalize-lines.mjs", serialized)
        with self.assertRaisesRegex(ValidationError, "allow-always"):
            require_host_permission_outcome(
                {
                    "schema": HOST_PERMISSION_SCHEMA,
                    "outcome": "allow_once",
                    "permission_kind": "edit",
                    "grant_count": 1,
                    "allowed": True,
                    "persisted": False,
                    "approve_all": False,
                    "os_sandbox": False,
                    "fs": False,
                    "terminal": False,
                    "ordinary_launch": "unavailable",
                    "body_retained": False,
                    "invented_decision": None,
                    "decisions": [{"outcome": "allow_always", "permission_kind": "edit"}],
                }
            )
        with self.assertRaisesRegex(ValidationError, "OS sandbox"):
            require_host_permission_outcome(
                {
                    **allowed,
                    "os_sandbox": True,
                }
            )

    def test_actual_public_runtime_host_permission_edits_fixture_once(self):
        artifact = ROOT / ACPX_ARTIFACT_PATH
        if not artifact.is_file():
            self.skipTest("exact local acpx artifact is task-owned proof input")
        template = (
            ROOT
            / "proof"
            / "puppet-acp"
            / "20260921"
            / "antigravity"
            / "inputs"
            / "v2-fixture"
            / "normalize-lines-fixture"
        )
        intended = (
            ROOT
            / "proof"
            / "puppet-acp"
            / "20260921"
            / "antigravity"
            / "inputs"
            / "v2-fixture"
            / "intended"
            / "bin"
            / "normalize-lines.mjs"
        )
        with tempfile.TemporaryDirectory() as temporary:
            isolated = _private_root(temporary)
            workspace = Path(temporary).resolve() / "fixture"
            shutil.copytree(template, workspace)
            protected = workspace / "test" / "normalize-lines.test.mjs"
            protected_before = hashlib.sha256(protected.read_bytes()).hexdigest()
            intended_digest = hashlib.sha256(intended.read_bytes()).hexdigest()
            runtime = AntigravityAcpNodeRuntime(
                workspace=workspace,
                isolated_root=isolated,
                repo_root=ROOT,
                synthetic_peer=True,
                synthetic_peer_script="permission-peer.mjs",
                synthetic_peer_permission="fs_write_file",
            )
            try:
                runner = self._runner(
                    isolated,
                    workspace,
                    runtime,
                    session_mode=SESSION_MODE_PERSISTENT,
                    finish_policy=FINISH_POLICY_RETAIN,
                )
                observation = runner.observation()
                self.assertEqual(observation["session"]["session_id"], "agy-acp-session")
                self.assertEqual(runner.permission_outcome["outcome"], "allow_once")
                self.assertTrue(runner.permission_outcome["allowed"])
                self.assertEqual(runner.permission_outcome["grant_count"], 1)
                self.assertEqual(runner.permission_outcome["permission_kind"], "edit")
                self.assertEqual(runner.permission_outcome["kind"], "edit")
                self.assertEqual(runner.permission_outcome["kind_source"], "standardized")
                self.assertEqual(runner.permission_outcome["id_class"], "opaque")
                self.assertEqual(runner.permission_outcome["path_source"], "raw_input")
                self.assertEqual(runner.permission_outcome["path_class"], "intended")
                self.assertEqual(runner.permission_outcome["reason"], "granted_once")
                self.assertFalse(runner.permission_outcome["os_sandbox"])
                self.assertFalse(runner.permission_outcome["persisted"])
                self.assertFalse(runner.permission_outcome["fs"])
                self.assertFalse(runner.permission_outcome["terminal"])
                permission_dump = json.dumps(runner.permission_outcome)
                self.assertNotIn("rawInput", permission_dump)
                self.assertNotIn(str(workspace / "bin" / "normalize-lines.mjs"), permission_dump)
                self.assertNotIn("call_", permission_dump)
                self.assertEqual(
                    hashlib.sha256(
                        (workspace / "bin" / "normalize-lines.mjs").read_bytes()
                    ).hexdigest(),
                    intended_digest,
                )
                self.assertEqual(
                    hashlib.sha256(protected.read_bytes()).hexdigest(),
                    protected_before,
                )
                after = subprocess.run(
                    [
                        "node",
                        "--test",
                        "--test-reporter=tap",
                        "test/normalize-lines.test.mjs",
                    ],
                    cwd=str(workspace),
                    text=True,
                    capture_output=True,
                    check=False,
                )
                stream = "%s\n%s" % (after.stdout, after.stderr)
                self.assertRegex(stream, r"(?:#|ℹ)\s+pass\s+2")
                self.assertRegex(stream, r"(?:#|ℹ)\s+fail\s+0")
                events = [
                    json.loads(line)
                    for line in (isolated / "ownership.events.jsonl").read_text().splitlines()
                ]
                turn_events = [
                    item for item in events if item.get("event") == "runtime_turn_observed"
                ]
                self.assertEqual(turn_events[-1]["permission"]["outcome"], "allow_once")
                self.assertEqual(turn_events[-1]["permission"]["path_source"], "raw_input")
                self.assertNotIn("options", json.dumps(turn_events[-1]))
                self.assertNotIn("prompt", json.dumps(turn_events[-1]))
                self.assertNotIn("rawInput", json.dumps(turn_events[-1]))
            finally:
                runtime.shutdown()

    def test_actual_public_runtime_host_permission_locations_path_edits_once(self):
        artifact = ROOT / ACPX_ARTIFACT_PATH
        if not artifact.is_file():
            self.skipTest("exact local acpx artifact is task-owned proof input")
        template = (
            ROOT
            / "proof"
            / "puppet-acp"
            / "20260921"
            / "antigravity"
            / "inputs"
            / "v2-fixture"
            / "normalize-lines-fixture"
        )
        intended = (
            ROOT
            / "proof"
            / "puppet-acp"
            / "20260921"
            / "antigravity"
            / "inputs"
            / "v2-fixture"
            / "intended"
            / "bin"
            / "normalize-lines.mjs"
        )
        with tempfile.TemporaryDirectory() as temporary:
            isolated = _private_root(temporary)
            workspace = Path(temporary).resolve() / "fixture"
            shutil.copytree(template, workspace)
            intended_digest = hashlib.sha256(intended.read_bytes()).hexdigest()
            runtime = AntigravityAcpNodeRuntime(
                workspace=workspace,
                isolated_root=isolated,
                repo_root=ROOT,
                synthetic_peer=True,
                synthetic_peer_script="permission-peer.mjs",
                synthetic_peer_permission="locations_path",
            )
            try:
                runner = self._runner(
                    isolated,
                    workspace,
                    runtime,
                    session_mode=SESSION_MODE_PERSISTENT,
                    finish_policy=FINISH_POLICY_RETAIN,
                )
                runner.observation()
                self.assertEqual(runner.permission_outcome["outcome"], "allow_once")
                self.assertEqual(runner.permission_outcome["path_source"], "locations")
                self.assertEqual(runner.permission_outcome["id_class"], "opaque")
                self.assertEqual(runner.permission_outcome["reason"], "granted_once")
                self.assertFalse(runner.permission_outcome["fs"])
                self.assertFalse(runner.permission_outcome["terminal"])
                self.assertEqual(
                    hashlib.sha256(
                        (workspace / "bin" / "normalize-lines.mjs").read_bytes()
                    ).hexdigest(),
                    intended_digest,
                )
                self.assertNotIn(
                    str(workspace / "bin" / "normalize-lines.mjs"),
                    json.dumps(runner.permission_outcome),
                )
            finally:
                runtime.shutdown()

    def test_actual_public_runtime_host_permission_fails_closed_without_fixture_edit(self):
        artifact = ROOT / ACPX_ARTIFACT_PATH
        if not artifact.is_file():
            self.skipTest("exact local acpx artifact is task-owned proof input")
        template = (
            ROOT
            / "proof"
            / "puppet-acp"
            / "20260921"
            / "antigravity"
            / "inputs"
            / "v2-fixture"
            / "normalize-lines-fixture"
        )
        for mode, reason in (
            ("deny_protected", "non_intended_path"),
            ("absent_path", "absent_path"),
            ("multiple_paths", "multiple_paths"),
            ("conflicting_paths", "conflicting_paths"),
            ("absent_kind", "absent_kind"),
            ("other_kind", "other_kind"),
            ("absent_allow_once", "absent_allow_once"),
            ("title_only", "inferred_kind_only"),
            ("interaction", "interaction"),
            ("elicitation", "elicitation"),
            ("ambiguous", "absent_path"),
        ):
            with self.subTest(mode=mode):
                with tempfile.TemporaryDirectory() as temporary:
                    isolated = _private_root(temporary)
                    workspace = Path(temporary).resolve() / "fixture"
                    shutil.copytree(template, workspace)
                    protected = workspace / "test" / "normalize-lines.test.mjs"
                    protected_before = hashlib.sha256(protected.read_bytes()).hexdigest()
                    runtime = AntigravityAcpNodeRuntime(
                        workspace=workspace,
                        isolated_root=isolated,
                        repo_root=ROOT,
                        synthetic_peer=True,
                        synthetic_peer_script="permission-peer.mjs",
                        synthetic_peer_permission=mode,
                    )
                    try:
                        runner = self._runner(
                            isolated,
                            workspace,
                            runtime,
                            session_mode=SESSION_MODE_PERSISTENT,
                            finish_policy=FINISH_POLICY_RETAIN,
                        )
                        runner.observation()
                        if runner.permission_outcome is None:
                            self.assertEqual(mode, "elicitation")
                        else:
                            self.assertNotEqual(runner.permission_outcome["outcome"], "allow_once")
                            self.assertFalse(runner.permission_outcome["allowed"])
                            self.assertEqual(runner.permission_outcome["reason"], reason)
                            self.assertFalse(runner.permission_outcome["os_sandbox"])
                            self.assertFalse(runner.permission_outcome["fs"])
                            self.assertFalse(runner.permission_outcome["terminal"])
                            dump = json.dumps(runner.permission_outcome)
                            self.assertNotIn("rawInput", dump)
                            self.assertNotIn(str(workspace), dump)
                            self.assertNotIn("write bin/normalize-lines.mjs", dump)
                        self.assertFalse((workspace / "bin" / "normalize-lines.mjs").exists())
                        self.assertEqual(
                            hashlib.sha256(protected.read_bytes()).hexdigest(),
                            protected_before,
                        )
                    finally:
                        runtime.shutdown()


if __name__ == "__main__":
    unittest.main()
