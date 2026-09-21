#!/usr/bin/env python3
"""Focused offline v4 AGY failure-receipt driver coverage."""

from __future__ import annotations

import errno
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


V4_ROOT = Path(__file__).resolve().parents[1]
DRIVER_DIR = V4_ROOT / "driver"
WORKTREE = V4_ROOT.parents[4]
SCRIPTS = WORKTREE / "skills" / "puppet" / "scripts"
sys.path.insert(0, str(DRIVER_DIR))
sys.path.insert(0, str(SCRIPTS))

from agy_live_capable_proof_driver import (
    EXACT_AGY_MODEL,
    EXPECTED_CHANGED_PATHS,
    FIRST_TURN_SOURCE,
    FOLLOW_UP_TEXT,
    IMPLEMENTATION_JOB_ID,
    INTENDED_BIN,
    LAUNCH_INPUT_SCHEMA,
    LIVE_RELEASE_MISSING,
    OFFICIAL_LIVE_DRIVER,
    OFFICIAL_LIVE_LAUNCH_INPUT,
    OFFICIAL_LIVE_PYTHON,
    OFFICIAL_RESOLVER_NAME,
    PINNED_ARTIFACT,
    PRODUCT_RUNTIME_TIMEOUT_MS,
    RECEIPT_SCHEMA,
    SECOND_TURN_SOURCE,
    SOURCE_HEAD,
    SOURCE_TREE,
    TASK_TEXT,
    UNKNOWN,
    V4_ROOT as DRIVER_V4_ROOT,
    V3_ROOT,
    CleanupVisibleError,
    accept_unsupported_backend_discard,
    apply_intended_implementation,
    backend_cleanup_policy,
    body_free,
    consume,
    create_fixture_workspace,
    evaluate_backend_after_finish,
    fixture_digests,
    observe_helper_and_backend,
    official_route_resolver,
    persist_receipt,
    pid_is_alive,
    reject_live_claim,
    reject_live_without_launch_input,
    reject_non_official_live_binding,
    require_exact_agy_model,
    require_exact_changed_paths,
    require_launch_input,
    require_synthetic_non_live,
    run_fixture_after,
    run_fixture_baseline,
    sha256_file,
    source_identities,
    staged_live_invocation,
    start_owned_local_backend,
    stop_owned_local_backend,
    write_cleanup_fence,
    write_staged_artifacts,
)
from puppet_lib.antigravity_acp import (
    OFFICIAL_ROUTE_KIND,
    resolve_antigravity_acp_route_binding,
    test_only_antigravity_synthetic_route_binding,
)
from puppet_lib.cursor_acp import SYNTHETIC_PEER_KIND, test_only_cursor_synthetic_route_binding
from puppet_lib.errors import IdentityError, UnsupportedError, ValidationError
from puppet_lib.session import _antigravity_acp_structured_launch


def _skip_without_artifact() -> None:
    if not PINNED_ARTIFACT.is_file():
        raise unittest.SkipTest("exact local acpx artifact is task-owned proof input")


def _write_launch_input(directory: Path) -> Path:
    path = Path(directory) / "launch-input.json"
    path.write_text(
        json.dumps(
            {
                "schema": LAUNCH_INPUT_SCHEMA,
                "authorized": True,
                "parent_release": "parent-issued-test-release",
                "requested_model": EXACT_AGY_MODEL,
                "effort": None,
                "route": "antigravity-acp",
                "apply_known_answer": False,
                "client_callback_policy": {"fs": False, "terminal": False},
                "enable_callbacks": False,
            },
            indent=2,
        )
        + "\n"
    )
    return path


class AgyLiveCapableProofDriverTests(unittest.TestCase):
    def test_source_and_exact_model_identities(self):
        identities = source_identities()
        self.assertEqual(identities["source_head"], SOURCE_HEAD)
        self.assertEqual(identities["source_tree"], SOURCE_TREE)
        self.assertEqual(require_exact_agy_model(EXACT_AGY_MODEL), EXACT_AGY_MODEL)
        with self.assertRaisesRegex(ValidationError, "exact gemini-3.8-flash-high"):
            require_exact_agy_model("gemini-3.1-pro")
        with self.assertRaisesRegex(ValidationError, "exact gemini-3.8-flash-high"):
            require_exact_agy_model("gemini-3.8-flash-high[effort=high]")

    def test_public_runtime_synthetic_owner_lifecycle(self):
        _skip_without_artifact()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            evidence = consume(
                live=False,
                state_root=root / "state",
                fixture_dir=root / "fixture",
                session="agy-v2-lifecycle",
            )
        self.assertTrue(evidence["ok"])
        self.assertFalse(evidence["live"])
        self.assertFalse(evidence["live_claimed"])
        self.assertEqual(evidence["route_kind"], SYNTHETIC_PEER_KIND)
        self.assertTrue(evidence["test_only"])
        self.assertFalse(evidence["synthetic_live_pass_possible"])
        self.assertEqual(evidence["entrypoint"], "_antigravity_acp_structured_launch")
        self.assertEqual(evidence["continuation_api"], "owner.next_turn")
        self.assertEqual(evidence["cleanup_api"], "owner.finish")
        self.assertEqual(evidence["model"]["requested_model"], EXACT_AGY_MODEL)
        self.assertEqual(evidence["model"]["selected_model"], EXACT_AGY_MODEL)
        self.assertEqual(evidence["model"]["current_model"], EXACT_AGY_MODEL)
        self.assertIsNone(evidence["model"]["effort"])
        self.assertFalse(evidence["model"]["synthetic_model_used_as_live"])
        self.assertEqual(evidence["identities"]["route"]["client_callback_policy"], {"fs": False, "terminal": False})
        self.assertEqual(evidence["identities"]["route"]["callback_enablement_from_flags"], "not_implemented")
        self.assertTrue(evidence["finish"]["final_discard"])
        self.assertTrue(evidence["finish"]["child_exit"]["exited"])
        self.assertEqual(evidence["child_start"]["role"], "node_driver_helper")
        self.assertIsInstance(evidence["child_start"]["pid"], int)
        self.assertEqual(evidence["child_start"]["pid"], evidence["finish"]["child_exit"]["pid"])
        self.assertEqual(evidence["process"]["first_turn"]["helper"]["role"], "node_driver_helper")
        self.assertEqual(evidence["process"]["first_turn"]["sampled_after"], "structured_launch_first_turn")
        self.assertFalse(evidence["process"]["first_turn"]["owner_next_turn_is_first_turn"])
        self.assertFalse(evidence["process"]["first_turn"]["backend"]["inferred_from_helper_exit"])
        self.assertFalse(evidence["process"]["first_turn"]["backend"]["agy_backend_claimed"])
        self.assertFalse(evidence["process"]["backend_after_finish"]["inferred_from_helper_exit"])
        self.assertFalse(evidence["backend_acceptance"]["accepted"])
        self.assertIsNone(evidence["finish"]["cleanup_fence"])
        self.assertEqual(evidence["turn_attribution"]["first_turn_source"], FIRST_TURN_SOURCE)
        self.assertEqual(evidence["turn_attribution"]["second_turn_source"], SECOND_TURN_SOURCE)
        self.assertFalse(evidence["turn_attribution"]["owner_next_turn_is_first_turn"])
        self.assertEqual(evidence["launch_parameters"]["product_runtime_timeout_ms"], PRODUCT_RUNTIME_TIMEOUT_MS)
        self.assertFalse(evidence["launch_parameters"]["product_timeout_feature_added"])
        self.assertTrue(evidence["offline_known_answer"]["offline_known_answer"])
        self.assertTrue(evidence["offline_known_answer"]["agy_useful_edit_unproven"])
        self.assertEqual(evidence["after"]["changed_paths"], sorted(EXPECTED_CHANGED_PATHS))
        self.assertEqual(evidence["after"]["check_normalized"]["exit_code"], 0)
        self.assertEqual(evidence["after"]["check_normalized"]["marker"], "OK")
        self.assertEqual(evidence["after"]["check_dirty"]["exit_code"], 1)
        self.assertEqual(evidence["after"]["check_dirty"]["marker"], "NON_NORMALIZED")
        self.assertFalse(evidence["task_text_retained"])
        self.assertNotIn(TASK_TEXT, str(evidence))
        self.assertEqual(evidence["implementation_job_id"], IMPLEMENTATION_JOB_ID)

    def test_fixture_baseline_after_and_unrelated_file_negative(self):
        baseline = run_fixture_baseline()
        self.assertEqual(baseline["tests"]["pass_count"], 1)
        self.assertEqual(baseline["tests"]["fail_count"], 1)
        self.assertFalse(baseline["bin_present"])
        after = run_fixture_after()
        self.assertEqual(after["tests"]["pass_count"], 2)
        self.assertEqual(after["check_normalized"]["exit_code"], 0)
        self.assertEqual(after["check_normalized"]["marker"], "OK")
        self.assertEqual(after["check_dirty"]["exit_code"], 1)
        self.assertEqual(after["check_dirty"]["marker"], "NON_NORMALIZED")
        self.assertEqual(after["protected_digests"], baseline["digests"])
        self.assertEqual(after["changed_paths"], ["bin/normalize-lines.mjs"])
        self.assertTrue(after["agy_useful_edit_unproven"])
        self.assertIn("offline/unproven", after["label"])
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary) / "negative"
            create_fixture_workspace(workspace)
            apply_intended_implementation(workspace)
            (workspace / "unrelated.txt").write_text("no\n")
            with self.assertRaisesRegex(ValidationError, "complete changed-path set"):
                require_exact_changed_paths(workspace)

    def test_live_launch_input_rejects_before_process_start(self):
        started = []

        def forbidden_launch(**_kwargs):
            started.append("structured_launch")
            raise AssertionError("structured_launch must not start without launch-input")

        with mock.patch("subprocess.Popen", side_effect=lambda *a, **k: started.append("popen")):
            with self.assertRaisesRegex(UnsupportedError, "missing launch-input rejects before process start"):
                reject_live_without_launch_input(True, None)
            with self.assertRaisesRegex(UnsupportedError, "missing launch-input"):
                require_launch_input(None)
            with self.assertRaisesRegex(UnsupportedError, "not authorized"):
                reject_live_claim(live=True)
            with self.assertRaisesRegex(UnsupportedError, "missing launch-input rejects before process start"):
                consume(
                    live=True,
                    launch_input=None,
                    structured_launch=forbidden_launch,
                    fixture_dir=Path("/tmp/must-not-be-created-agy-v3-live"),
                )
        self.assertEqual(started, [])

    def test_official_live_path_wiring_uses_non_provider_substitute(self):
        _skip_without_artifact()
        captured = {}

        def wrap_launch(**kwargs):
            captured["requested_model"] = kwargs.get("requested_model")
            captured["prompt"] = kwargs.get("prompt")
            captured["route_resolver"] = kwargs.get("route_resolver")
            captured["catalog"] = kwargs.get("catalog")
            captured["repo"] = str(Path(kwargs["contract"].repo).resolve())
            captured["session"] = kwargs.get("session")
            kwargs["route_resolver"] = test_only_antigravity_synthetic_route_binding
            kwargs["catalog"] = None
            return _antigravity_acp_structured_launch(**kwargs)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            launch_input = _write_launch_input(root)
            applied = []

            def forbidden_known_answer(workspace):
                applied.append(str(workspace))
                raise AssertionError("live branch must not apply the known answer")

            with mock.patch(
                "agy_live_capable_proof_driver.apply_intended_implementation",
                side_effect=forbidden_known_answer,
            ):
                receipt = consume(
                    live=True,
                    launch_input=launch_input,
                    state_root=root / "state",
                    fixture_dir=root / "fixture",
                    session="agy-v2-live-wiring",
                    continue_turn=True,
                    inspect_after=False,
                    apply_known_answer=False,
                    structured_launch=wrap_launch,
                )
        self.assertEqual(captured["requested_model"], EXACT_AGY_MODEL)
        self.assertEqual(captured["prompt"], TASK_TEXT)
        self.assertIs(captured["route_resolver"], resolve_antigravity_acp_route_binding)
        self.assertIsNone(captured["catalog"])
        self.assertEqual(captured["repo"], str((root / "fixture").resolve()))
        self.assertEqual(receipt["launch_parameters"]["requested_model"], EXACT_AGY_MODEL)
        self.assertEqual(receipt["launch_parameters"]["route_resolver"], OFFICIAL_RESOLVER_NAME)
        self.assertFalse(receipt["launch_parameters"]["catalog_injected"])
        self.assertEqual(receipt["launch_parameters"]["intended_kind"], OFFICIAL_ROUTE_KIND)
        self.assertEqual(receipt["route_kind"], SYNTHETIC_PEER_KIND)
        self.assertFalse(receipt["live_claimed"])
        self.assertFalse(receipt["model"]["synthetic_model_used_as_live"])
        self.assertEqual(receipt["model"]["source"], "synthetic_offline_substitute")
        self.assertIsNone(receipt["offline_known_answer"])
        self.assertEqual(applied, [])
        self.assertEqual(official_route_resolver.__name__, "official_route_resolver")
        staged = staged_live_invocation()
        self.assertFalse(staged["executed"])
        self.assertEqual(staged["command"][0], OFFICIAL_LIVE_PYTHON)
        self.assertEqual(Path(staged["command"][1]), OFFICIAL_LIVE_DRIVER)
        self.assertIn("--live", staged["command"])
        self.assertIn("--launch-input", staged["command"])
        self.assertEqual(Path(staged["command"][4]), OFFICIAL_LIVE_LAUNCH_INPUT)
        self.assertEqual(staged["requested_model"], EXACT_AGY_MODEL)
        self.assertIsNone(staged["effort"])
        self.assertFalse(staged["apply_known_answer"])
        self.assertEqual(staged["first_turn_source"], FIRST_TURN_SOURCE)
        self.assertFalse(staged["owner_next_turn_is_first_turn"])
        self.assertEqual(staged["product_runtime_timeout_ms"], PRODUCT_RUNTIME_TIMEOUT_MS)
        self.assertFalse(staged["product_timeout_feature_added"])

    def test_reject_non_official_live_binding_and_secret_launch_input(self):
        synthetic = test_only_antigravity_synthetic_route_binding()
        require_synthetic_non_live(synthetic)
        live_synthetic = dict(synthetic)
        live_synthetic["test_only"] = False
        with self.assertRaisesRegex(ValidationError, "test-only|live"):
            reject_non_official_live_binding(live_synthetic)
        cursor = test_only_cursor_synthetic_route_binding()
        with self.assertRaisesRegex(ValidationError, "non-official live binding is rejected"):
            reject_non_official_live_binding(cursor)
        with tempfile.TemporaryDirectory() as temporary:
            secret = Path(temporary) / "secret.json"
            secret.write_text(json.dumps({"schema": LAUNCH_INPUT_SCHEMA, "token": "nope"}))
            with self.assertRaisesRegex(ValidationError, "forbidden secret-bearing field"):
                require_launch_input(secret)
            body = Path(temporary) / "body.json"
            body.write_text(json.dumps({"schema": LAUNCH_INPUT_SCHEMA, "prompt": TASK_TEXT}))
            with self.assertRaisesRegex(ValidationError, "body-bearing field prompt"):
                require_launch_input(body)

    def test_reject_body_bearing_evidence(self):
        with self.assertRaisesRegex(ValidationError, "body-bearing field prompt"):
            body_free({"ok": True, "prompt": TASK_TEXT}, label="evidence")
        with self.assertRaisesRegex(ValidationError, "body-bearing field transcript"):
            body_free({"nested": {"transcript": "secret"}}, label="evidence")

    def test_injected_assertion_and_cleanup_failure_remain_visible(self):
        _skip_without_artifact()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            released = consume(
                live=False,
                state_root=root / "release-state",
                fixture_dir=root / "release-fixture",
                session="agy-v2-inject-release",
                inject_post_launch_failure="raise",
            )
            self.assertFalse(released["ok"])
            self.assertTrue(released["primary_preserved"])
            self.assertEqual(released["primary_error"]["message"], "injected post-launch assertion failure")
            self.assertTrue(released["finish_attempted_once"])
            self.assertTrue(released["cleanup"]["child_exit"]["exited"])
            self.assertIsNone(released["cleanup"]["cleanup_fence"])
            self.assertTrue(released["fixture_retained"])
            self.assertTrue(released["state_retained"])
            helper_pid = released["cleanup"]["child_exit"]["pid"]
            self.assertIsInstance(helper_pid, int)
            with self.assertRaises(OSError):
                os.kill(helper_pid, 0)

            held = {}
            both = consume(
                live=False,
                state_root=root / "cleanup-state",
                fixture_dir=root / "cleanup-fixture",
                session="agy-v2-inject-cleanup",
                inject_post_launch_failure="raise_cleanup",
                retain_owned_runtime=held,
            )
            self.assertFalse(both["ok"])
            self.assertTrue(both["primary_preserved"])
            self.assertEqual(both["primary_error"]["message"], "injected post-launch assertion failure")
            self.assertIsNotNone(both["cleanup_error"])
            self.assertIn("injected cleanup failure", both["cleanup_error"]["message"])
            self.assertTrue(both["cleanup_failure_visible"])
            self.assertIsNotNone(both["cleanup"]["cleanup_fence"])
            self.assertTrue(both["cleanup"]["cleanup_fence"]["cleanup_uncertain"])
            self.assertTrue(both["cleanup"]["cleanup_fence"]["replacement_blocked"])
            self.assertFalse(both["cleanup"]["cleanup_fence"]["workspace_deleted"])
            self.assertTrue(both["fixture_retained"])
            self.assertTrue((root / "cleanup-fixture" / "package.json").is_file())
            self.assertTrue((root / "cleanup-state").is_dir())
            owner = held["owner"]
            continuation = held["continuation"]
            with self.assertRaisesRegex(ValidationError, "release is uncertain"):
                owner.next_turn(
                    continuation,
                    text=FOLLOW_UP_TEXT,
                    request_id="agy-v2-inject-cleanup-turn-2",
                )
            held["runner"].finish = held["original_finish"]
            held["runtime"].shutdown = held["original_shutdown"]
            closed = owner.finish(continuation)
            self.assertTrue(closed["child_exit"]["exited"])
            with self.assertRaises(OSError):
                os.kill(closed["child_exit"]["pid"], 0)

    def test_unsupported_backend_discard_requires_helper_and_backend_termination(self):
        helper = {"exited": True, "pid": 4242, "role": "node_driver_helper"}
        missing_backend = {
            "observed": False,
            "terminated": False,
            "evidence_gap": "no OS child of the owned Node helper was observed",
        }
        with self.assertRaisesRegex(ValidationError, "helper exit and independently established backend"):
            accept_unsupported_backend_discard(
                {"backend_discard": "unsupported_local_cleanup_proved", "local_release": True, "final_discard": False},
                helper,
                missing_backend,
            )
        accepted = accept_unsupported_backend_discard(
            {"backend_discard": "unsupported_local_cleanup_proved", "local_release": True, "final_discard": False},
            helper,
            {"observed": True, "terminated": True},
        )
        self.assertTrue(accepted["accepted"])
        self.assertTrue(accepted["local_release"])
        self.assertNotEqual(accepted["backend_discard"], accepted["local_release"])
        closed = accept_unsupported_backend_discard(
            {"backend_discard": "closed", "local_release": False, "final_discard": True},
            helper,
            missing_backend,
        )
        self.assertFalse(closed["accepted"])
        self.assertEqual(closed["backend_discard"], "closed")
        self.assertFalse(closed["local_release"])

    def test_staged_live_command_is_not_executed(self):
        paths = write_staged_artifacts()
        staged = json.loads(Path(paths["invocation"]).read_text())
        contract = json.loads(Path(paths["launch_input"]).read_text())
        self.assertFalse(staged["executed"])
        self.assertEqual(staged["command"][0], OFFICIAL_LIVE_PYTHON)
        self.assertEqual(Path(staged["command"][1]), OFFICIAL_LIVE_DRIVER)
        self.assertEqual(Path(staged["launch_input_contract"]), OFFICIAL_LIVE_LAUNCH_INPUT)
        self.assertEqual(contract["schema"], LAUNCH_INPUT_SCHEMA)
        self.assertEqual(contract["requested_model"], EXACT_AGY_MODEL)
        self.assertIsNone(contract["effort"])
        self.assertFalse(contract["apply_known_answer"])
        self.assertNotIn("prompt", contract)
        self.assertNotIn("argv", contract)
        self.assertNotIn("process_env", contract)
        self.assertTrue(str(OFFICIAL_LIVE_DRIVER).endswith("/v4/driver/agy_live_capable_proof_driver.py"))
        self.assertTrue(str(OFFICIAL_LIVE_LAUNCH_INPUT).endswith("/v4/staged/launch-input.contract.json"))
        self.assertTrue(staged["historical_v3_to_v2_quarantined"])
        self.assertIn("/v3/staged/live-invocation.json", staged["historical_v3_to_v2_invocation"])

    def test_structured_launch_is_first_turn_not_next_turn(self):
        _skip_without_artifact()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            receipt = consume(
                live=False,
                state_root=root / "state",
                fixture_dir=root / "fixture",
                session="agy-v3-first-turn",
                continue_turn=True,
            )
        attribution = receipt["turn_attribution"]
        self.assertTrue(attribution["structured_launch_includes_first_turn"])
        self.assertTrue(attribution["require_observation_completes_first_turn"])
        self.assertFalse(attribution["owner_next_turn_is_first_turn"])
        self.assertEqual(attribution["first_turn_source"], FIRST_TURN_SOURCE)
        self.assertEqual(attribution["second_turn_source"], SECOND_TURN_SOURCE)
        self.assertNotEqual(attribution["first_request_id"], attribution["second_request_id"])
        self.assertNotEqual(attribution["second_request_id"], "agy-v3-first-turn-turn-1")
        self.assertEqual(receipt["process"]["first_turn"]["sampled_after"], "structured_launch_first_turn")
        self.assertEqual(receipt["process"]["second_turn"]["sampled_after"], "owner_next_turn_second_turn")
        self.assertFalse(receipt["launch_parameters"]["owner_next_turn_is_first_turn"])

    def test_generic_node_helper_is_not_agy_backend(self):
        helper = {
            "pid": 4242,
            "returncode": None,
            "exited": False,
            "kind": "synthetic_peer",
        }
        node_child = {
            "pid": 4343,
            "ppid": 4242,
            "executable_name": "node",
            "start_birth_identity": "Mon Sep 21 00:00:00 2026",
        }
        backend = {
            "pid": 4444,
            "ppid": 4242,
            "executable_name": "localharness_external",
            "start_birth_identity": "Mon Sep 21 00:00:00 2026",
        }
        missing = observe_helper_and_backend(
            helper,
            sampled_after="structured_launch_first_turn",
            os_descendants=[node_child],
        )
        self.assertEqual(missing["helper"]["role"], "node_driver_helper")
        self.assertFalse(missing["backend"]["observed"])
        self.assertFalse(missing["backend"]["agy_backend_claimed"])
        self.assertFalse(missing["backend"]["inferred_from_helper_exit"])
        self.assertIn("generic node child", missing["backend"]["evidence_gap"])
        observed = observe_helper_and_backend(
            helper,
            sampled_after="structured_launch_first_turn",
            os_descendants=[node_child, backend],
        )
        self.assertTrue(observed["backend"]["observed"])
        self.assertEqual(observed["backend"]["incarnations"][0]["pid"], 4444)
        self.assertNotEqual(observed["helper"]["pid"], observed["backend"]["incarnations"][0]["pid"])
        self.assertEqual(
            set(observed["backend"]["incarnations"][0]),
            {"pid", "ppid", "executable_name", "start_birth_identity"},
        )

    def test_unsupported_close_accepts_owned_local_backend_exit(self):
        _skip_without_artifact()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            handle = start_owned_local_backend(root / "owned-backend")
            try:
                self.assertEqual(handle["incarnation"]["executable_name"], "localharness_external")
                self.assertFalse(handle["agy_backend_claimed"])
                os.kill(handle["pid"], 0)
                evidence = consume(
                    live=False,
                    state_root=root / "state",
                    fixture_dir=root / "fixture",
                    session="agy-v3-owned-backend-exit",
                    continue_turn=False,
                    inspect_after=False,
                    apply_known_answer=False,
                    inject_unsupported_backend_close=True,
                    extra_owned_pids=[handle["pid"]],
                    stop_owned_backends=lambda: stop_owned_local_backend(handle),
                )
            finally:
                if handle["proc"].poll() is None:
                    stop_owned_local_backend(handle)
        self.assertTrue(evidence["ok"])
        self.assertFalse(evidence["live"])
        self.assertFalse(evidence["live_claimed"])
        self.assertEqual(evidence["finish"]["backend_discard"], "unsupported_local_cleanup_proved")
        self.assertTrue(evidence["backend_acceptance"]["accepted"])
        self.assertTrue(evidence["process"]["first_turn"]["backend"]["observed"])
        self.assertEqual(
            evidence["process"]["first_turn"]["backend"]["incarnations"][0]["pid"],
            handle["pid"],
        )
        self.assertTrue(evidence["process"]["backend_after_finish"]["terminated"])
        self.assertFalse(evidence["process"]["backend_after_finish"]["inferred_from_helper_exit"])
        self.assertFalse(evidence["backend_acceptance"]["helper_exit_sufficient"])
        self.assertIsNone(evidence["finish"]["cleanup_fence"])
        with self.assertRaises(OSError):
            os.kill(handle["pid"], 0)

    def test_unknown_or_surviving_backend_remains_fenced_with_primary(self):
        _skip_without_artifact()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            unknown = consume(
                live=False,
                state_root=root / "unknown-state",
                fixture_dir=root / "unknown-fixture",
                session="agy-v3-unknown-backend",
                continue_turn=False,
                inject_post_launch_failure="raise",
                inject_unsupported_backend_close=True,
            )
            self.assertFalse(unknown["ok"])
            self.assertTrue(unknown["primary_preserved"])
            self.assertEqual(unknown["primary_error"]["message"], "injected post-launch assertion failure")
            self.assertEqual(unknown["cleanup"]["backend_discard"], "unsupported_local_cleanup_proved")
            self.assertFalse(unknown["cleanup"]["backend_acceptance"]["accepted"])
            self.assertIsNotNone(unknown["cleanup"]["cleanup_fence"])
            self.assertTrue(unknown["cleanup"]["cleanup_fence"]["cleanup_uncertain"])
            self.assertTrue(unknown["cleanup"]["cleanup_fence"]["replacement_blocked"])
            self.assertFalse(unknown["cleanup"]["cleanup_fence"]["helper_exit_sufficient"])
            self.assertFalse(unknown["cleanup"]["cleanup_fence"]["workspace_deleted"])
            self.assertIsNotNone(unknown["cleanup"]["cleanup_fence"]["owner_id"])
            self.assertIsNotNone(unknown["cleanup"]["cleanup_fence"]["continuation_id"])
            self.assertTrue(unknown["fixture_retained"])
            self.assertTrue(unknown["state_retained"])
            self.assertFalse(unknown["session_replaced"])
            self.assertTrue((root / "unknown-fixture" / "package.json").is_file())
            self.assertTrue((root / "unknown-state").is_dir())

            handle = start_owned_local_backend(root / "surviving-backend")
            try:
                surviving = consume(
                    live=False,
                    state_root=root / "surviving-state",
                    fixture_dir=root / "surviving-fixture",
                    session="agy-v3-surviving-backend",
                    continue_turn=False,
                    inject_post_launch_failure="raise",
                    inject_unsupported_backend_close=True,
                    extra_owned_pids=[handle["pid"]],
                )
                self.assertFalse(surviving["ok"])
                self.assertTrue(surviving["primary_preserved"])
                self.assertEqual(surviving["primary_error"]["message"], "injected post-launch assertion failure")
                self.assertEqual(surviving["cleanup"]["backend_discard"], "unsupported_local_cleanup_proved")
                self.assertFalse(surviving["cleanup"]["backend_acceptance"]["accepted"])
                fence = surviving["cleanup"]["cleanup_fence"]
                self.assertIsNotNone(fence)
                self.assertTrue(fence["cleanup_uncertain"])
                self.assertTrue(fence["replacement_blocked"])
                self.assertFalse(fence["session_replaced"])
                self.assertFalse(fence["workspace_deleted"])
                self.assertFalse(fence["state_deleted"])
                self.assertFalse(fence["helper_exit_sufficient"])
                self.assertIn("survived owner.finish", fence["reason"])
                self.assertEqual(fence["owner_id"], surviving["cleanup"]["cleanup_fence"]["owner_id"])
                self.assertIsNotNone(fence["continuation_id"])
                self.assertTrue(surviving["fixture_retained"])
                self.assertTrue(surviving["state_retained"])
                self.assertTrue((root / "surviving-fixture" / "package.json").is_file())
                os.kill(handle["pid"], 0)
            finally:
                if handle["proc"].poll() is None:
                    stop_owned_local_backend(handle)

        missing = evaluate_backend_after_finish([])
        self.assertFalse(missing["observed"])
        self.assertFalse(missing["terminated"])
        self.assertFalse(missing["inferred_from_helper_exit"])
        self.assertFalse(missing["cleanup_uncertain"])

    def test_official_empty_capture_after_helper_exit_discard_is_fenced(self):
        self.assertEqual(backend_cleanup_policy(live=True, used_kind=OFFICIAL_ROUTE_KIND), "official")
        evaluated = evaluate_backend_after_finish([], policy="official")
        self.assertFalse(evaluated["observed"])
        self.assertFalse(evaluated["terminated"])
        self.assertTrue(evaluated["cleanup_uncertain"])
        self.assertTrue(evaluated["replacement_blocked"])
        self.assertFalse(evaluated["helper_exit_sufficient"])
        self.assertFalse(evaluated["inferred_from_helper_exit"])
        self.assertFalse(evaluated["agy_backend_claimed"])
        helper = {"exited": True, "pid": 4242, "role": "node_driver_helper"}
        closed = accept_unsupported_backend_discard(
            {"backend_discard": "closed", "local_release": False, "final_discard": True},
            helper,
            evaluated,
        )
        self.assertFalse(closed["accepted"])
        self.assertEqual(closed["backend_discard"], "closed")
        self.assertTrue(closed["helper_exited"])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fence = write_cleanup_fence(
                fence_dir=root / "fences",
                session="agy-v4-official-empty-capture",
                reason=evaluated["reason"],
                helper_pid=helper["pid"],
                workspace=root / "workspace",
                state_root=root / "state",
                extra={
                    "backend_after_finish": evaluated,
                    "backend_acceptance": closed,
                    "helper_exit_sufficient": False,
                },
            )
            self.assertTrue(fence["cleanup_uncertain"])
            self.assertTrue(fence["replacement_blocked"])
            self.assertFalse(fence["helper_exit_sufficient"])
            self.assertFalse(fence["workspace_deleted"])
            self.assertTrue(Path(fence["path"]).is_file())

    def test_failed_metadata_query_with_alive_or_unknown_liveness_is_not_terminated(self):
        captured = {
            "pid": 5555,
            "ppid": 4242,
            "executable_name": "localharness_external",
            "start_birth_identity": "Mon Sep 21 00:00:00 2026",
        }
        with mock.patch("agy_live_capable_proof_driver.os.kill", side_effect=ProcessLookupError()):
            self.assertIs(pid_is_alive(5555), False)
        with mock.patch("agy_live_capable_proof_driver.os.kill", side_effect=PermissionError()):
            self.assertIsNone(pid_is_alive(5555))
        with mock.patch(
            "agy_live_capable_proof_driver.os.kill",
            side_effect=OSError(errno.EPERM, "Operation not permitted"),
        ):
            self.assertIsNone(pid_is_alive(5555))
        with mock.patch("agy_live_capable_proof_driver.os.kill", return_value=None):
            self.assertIs(pid_is_alive(5555), True)

        cases = (
            (None, True),
            (None, None),
            (OSError("ps metadata denied"), True),
            (OSError("ps metadata denied"), None),
        )
        for metadata, alive in cases:
            with self.subTest(metadata=metadata, alive=alive):
                identity = mock.Mock(side_effect=metadata) if isinstance(metadata, Exception) else mock.Mock(return_value=metadata)
                with mock.patch("agy_live_capable_proof_driver._ps_identity", identity):
                    with mock.patch("agy_live_capable_proof_driver.pid_is_alive", return_value=alive):
                        result = evaluate_backend_after_finish([captured])
                self.assertTrue(result["observed"])
                self.assertFalse(result["terminated"])
                self.assertTrue(result["cleanup_uncertain"])
                self.assertTrue(result["replacement_blocked"])
                self.assertFalse(result["helper_exit_sufficient"])
                self.assertFalse(result["inferred_from_helper_exit"])
                self.assertEqual(result["surviving_count"], 0)

    def test_task_owned_local_peer_exit_is_accepted_with_positive_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            handle = start_owned_local_backend(Path(temporary) / "owned-backend")
            try:
                living = evaluate_backend_after_finish([handle["incarnation"]])
                self.assertTrue(living["observed"])
                self.assertFalse(living["terminated"])
                self.assertTrue(living["cleanup_uncertain"])
                self.assertEqual(living["surviving"][0]["pid"], handle["pid"])
                os.kill(handle["pid"], 0)
            finally:
                stop_owned_local_backend(handle)
            exited = evaluate_backend_after_finish([handle["incarnation"]])
        self.assertTrue(exited["observed"])
        self.assertTrue(exited["terminated"])
        self.assertFalse(exited["cleanup_uncertain"])
        self.assertFalse(exited["replacement_blocked"])
        self.assertFalse(exited["inferred_from_helper_exit"])
        self.assertFalse(exited["agy_backend_claimed"])
        self.assertEqual(exited["terminated_count"], 1)
        with self.assertRaises(OSError):
            os.kill(handle["pid"], 0)

    def test_synthetic_no_backend_empty_capture_remains_non_qualifying(self):
        self.assertEqual(backend_cleanup_policy(live=False, used_kind=SYNTHETIC_PEER_KIND), "synthetic")
        self.assertEqual(backend_cleanup_policy(live=True, used_kind=SYNTHETIC_PEER_KIND), "synthetic")
        missing = evaluate_backend_after_finish([], policy="synthetic")
        self.assertFalse(missing["observed"])
        self.assertFalse(missing["terminated"])
        self.assertFalse(missing["cleanup_uncertain"])
        self.assertFalse(missing.get("replacement_blocked", False))
        self.assertFalse(missing["agy_backend_claimed"])
        self.assertFalse(missing["inferred_from_helper_exit"])
        self.assertFalse(missing["helper_exit_sufficient"])
        self.assertNotIn("reason", missing)
        helper = {"exited": True, "pid": 4242, "role": "node_driver_helper"}
        closed = accept_unsupported_backend_discard(
            {"backend_discard": "closed", "local_release": False, "final_discard": True},
            helper,
            missing,
        )
        self.assertFalse(closed["accepted"])
        self.assertFalse(closed["backend_terminated"])

    def test_ordinary_no_edit_fixture_failure_persists_fresh_receipt(self):
        _skip_without_artifact()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            receipt = consume(
                live=False,
                state_root=root / "state",
                fixture_dir=root / "fixture",
                session="agy-v4-ordinary-failure",
                apply_known_answer=False,
                inspect_after=True,
                receipt_dir=root / "receipts",
            )
            persisted = Path(receipt["receipt"]["path"])
            self.assertTrue(persisted.is_file())
            disk = json.loads(persisted.read_text())
            self.assertEqual(disk["receipt_schema"], RECEIPT_SCHEMA)
            self.assertFalse(receipt["ok"])
            self.assertFalse(receipt["live"])
            self.assertFalse(receipt["live_claimed"])
            self.assertFalse(receipt["qualifying_pass"])
            self.assertEqual(receipt["mode"], "ordinary_fixture_failure")
            self.assertTrue(receipt["runtime_contacted"])
            self.assertFalse(receipt["official_agy_provider_contacted"])
            self.assertFalse(receipt["provider_never_contacted_implied"])
            self.assertTrue(receipt["synthetic_peer_used"])
            self.assertTrue(receipt["test_only"])
            self.assertEqual(receipt["route_kind"], SYNTHETIC_PEER_KIND)
            self.assertIsNone(receipt["finish"]["cleanup_fence"])
            self.assertFalse(receipt["process"]["backend_after_finish"]["observed"])
            self.assertFalse(receipt["process"]["backend_after_finish"]["terminated"])
            self.assertFalse(receipt["process"]["backend_after_finish"]["cleanup_uncertain"])
            self.assertFalse(receipt["backend_acceptance"]["accepted"])
            self.assertEqual(receipt["model"]["requested_model"], EXACT_AGY_MODEL)
            self.assertEqual(receipt["model"]["current_model"], EXACT_AGY_MODEL)
            self.assertIsNone(receipt["model"]["effort"])
            self.assertNotEqual(receipt["turns"]["first"]["request_id"], UNKNOWN)
            self.assertEqual(receipt["turns"]["first"]["stop_reason"], "end_turn")
            self.assertNotEqual(receipt["turns"]["second"]["request_id"], UNKNOWN)
            self.assertEqual(receipt["turns"]["second"]["stop_reason"], "end_turn")
            self.assertTrue(receipt["turns"]["second"]["same_owner_continuation"])
            self.assertNotEqual(receipt["owner_id"], UNKNOWN)
            self.assertTrue(receipt["owner_handle_existed"])
            self.assertIsNotNone(receipt["finish"])
            self.assertNotEqual(receipt["finish"].get("result", "present"), UNKNOWN)
            self.assertTrue(receipt["primary_preserved"])
            self.assertEqual(
                receipt["primary_error"]["message"],
                "fixture after tests did not pass independently",
            )
            self.assertIsNone(receipt["cleanup_error"])
            self.assertFalse(receipt["fixture_outcome"]["ok"])
            self.assertTrue(receipt["fixture_outcome"]["independent"])
            self.assertFalse(receipt["fixture_outcome"]["bin_present"])
            self.assertFalse(receipt["fixture_outcome"]["qualifying_pass"])
            self.assertNotIn("prompt", receipt)
            self.assertNotIn("transcript", receipt)
            self.assertNotIn("output", receipt)
            self.assertNotIn(TASK_TEXT, str(receipt))
            self.assertNotIn(FOLLOW_UP_TEXT, str(receipt))
            self.assertNotIn("agy-ack", str(receipt))
            body_free(disk, label="ordinary failure disk receipt")

    def test_failure_before_owner_handle_persists_receipt(self):
        _skip_without_artifact()

        def failing_launch(**_kwargs):
            raise RuntimeError("launch failed before owner/handle exists")

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            receipt = consume(
                live=False,
                state_root=root / "state",
                fixture_dir=root / "fixture",
                session="agy-v4-before-owner",
                apply_known_answer=False,
                inspect_after=False,
                structured_launch=failing_launch,
                receipt_dir=root / "receipts",
            )
            self.assertTrue(Path(receipt["receipt"]["path"]).is_file())
        self.assertFalse(receipt["ok"])
        self.assertFalse(receipt["owner_handle_existed"])
        self.assertEqual(receipt["owner_id"], UNKNOWN)
        self.assertEqual(receipt["continuation"], UNKNOWN)
        self.assertFalse(receipt["runtime_contacted"])
        self.assertFalse(receipt["official_agy_provider_contacted"])
        self.assertEqual(receipt["turns"]["first"]["request_id"], UNKNOWN)
        self.assertEqual(receipt["turns"]["first"]["stop_reason"], UNKNOWN)
        self.assertEqual(receipt["model"]["current_model"], UNKNOWN)
        self.assertTrue(receipt["cleanup"]["uncertain"])
        self.assertFalse(receipt["finish_attempted_once"])
        self.assertEqual(receipt["primary_error"]["message"], "launch failed before owner/handle exists")

    def test_refuses_overwrite_existing_receipt(self):
        with tempfile.TemporaryDirectory() as temporary:
            existing = Path(temporary) / "receipt.json"
            first = persist_receipt(existing, {"schema": RECEIPT_SCHEMA, "ok": False, "marker": "original"})
            original = existing.read_bytes()
            with self.assertRaisesRegex(ValidationError, "refusing to overwrite existing receipt"):
                persist_receipt(existing, {"schema": RECEIPT_SCHEMA, "ok": True, "marker": "replacement"})
            self.assertEqual(existing.read_bytes(), original)
            self.assertEqual(first["sha256"], sha256_file(existing))
            v3_path = V3_ROOT / "receipts" / "must-not-write.json"
            with self.assertRaisesRegex(ValidationError, "frozen v3 evidence"):
                persist_receipt(v3_path, {"schema": RECEIPT_SCHEMA, "ok": False})
            self.assertFalse(v3_path.exists())

    def test_live_mode_rejects_known_answer_helper_but_allows_identical_bytes(self):
        _skip_without_artifact()
        captured = []

        def wrap_launch(**kwargs):
            kwargs["route_resolver"] = test_only_antigravity_synthetic_route_binding
            kwargs["catalog"] = None
            return _antigravity_acp_structured_launch(**kwargs)

        def place_identical_bytes(workspace):
            target = Path(workspace) / "bin" / "normalize-lines.mjs"
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(INTENDED_BIN, target)
            os.chmod(target, 0o755)

        def forbidden_known_answer(workspace):
            captured.append(str(workspace))
            raise AssertionError("live branch must not apply the known answer")

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            launch_input = _write_launch_input(root)
            with mock.patch(
                "agy_live_capable_proof_driver.apply_intended_implementation",
                side_effect=forbidden_known_answer,
            ):
                receipt = consume(
                    live=True,
                    launch_input=launch_input,
                    state_root=root / "state",
                    fixture_dir=root / "fixture",
                    session="agy-v4-identical-bytes",
                    continue_turn=True,
                    inspect_after=True,
                    apply_known_answer=False,
                    structured_launch=wrap_launch,
                    after_turns=place_identical_bytes,
                    receipt_dir=root / "receipts",
                )
        self.assertEqual(captured, [])
        self.assertTrue(receipt["ok"])
        self.assertFalse(receipt["live"])
        self.assertFalse(receipt["live_claimed"])
        self.assertIsNone(receipt["offline_known_answer"])
        self.assertEqual(receipt["after"]["changed_paths"], ["bin/normalize-lines.mjs"])
        self.assertEqual(receipt["after"]["tests"]["pass_count"], 2)
        self.assertEqual(receipt["after"]["check_normalized"]["marker"], "OK")
        self.assertEqual(receipt["after"]["check_dirty"]["marker"], "NON_NORMALIZED")
        self.assertTrue(receipt["fixture_outcome"]["protected_unchanged"])
        self.assertNotIn("copied the known answer", str(receipt))


if __name__ == "__main__":
    unittest.main()
