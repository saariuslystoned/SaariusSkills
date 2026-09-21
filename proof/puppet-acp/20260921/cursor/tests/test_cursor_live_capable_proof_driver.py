from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


V3_ROOT = Path(__file__).resolve().parents[1]
DRIVER_DIR = V3_ROOT / "driver"
WORKTREE = V3_ROOT.parents[3]
SCRIPTS = WORKTREE / "skills" / "puppet" / "scripts"
sys.path.insert(0, str(DRIVER_DIR))
sys.path.insert(0, str(SCRIPTS))

from cursor_live_capable_proof_driver import (  # noqa: E402
    EXPECTED_PROTECTED_TEST_SHA256,
    FIRST_TASK_TEXT,
    FIRST_TURN_SOURCE,
    FIXTURE_BRANCH,
    FIXED_IMPL,
    IMPLEMENTATION_JOB_ID,
    LIVE_PATH_EXISTS,
    LIVE_RELEASE_MISSING,
    LIVE_SELECTOR,
    LIVE_SESSION_REQUIRED,
    OFFICIAL_RESOLVER_NAME,
    PIN_ARTIFACT,
    SECOND_TASK_TEXT,
    STAGED_LIVE_SESSION,
    SYNTHETIC_REQUESTED,
    TEMPLATE_IMPL,
    capture_baseline,
    consume,
    create_fixture_workspace,
    fixture_identity,
    observe_helper_and_backend,
    official_route_resolver,
    reject_existing_live_session_paths,
    reject_live_flag_without_release,
    reject_live_without_release,
    reject_mismatched_model,
    reject_mismatched_workspace_and_owner,
    require_attached_branch,
    require_explicit_live_session,
    require_parent_release,
    staged_live_invocation,
    synthetic_catalog,
    live_owned_paths,
)
from puppet_lib.cursor_acp import (  # noqa: E402
    resolve_cursor_acp_route_binding,
    test_only_cursor_synthetic_route_binding,
)
from puppet_lib.session import _cursor_acp_structured_launch  # noqa: E402


def _skip_without_artifact() -> None:
    if not PIN_ARTIFACT.is_file():
        raise unittest.SkipTest("exact local acpx artifact is task-owned proof input")


def _wrap_live_launch(captured: dict):
    def wrap_launch(**kwargs):
        captured["requested_model"] = kwargs.get("requested_model")
        captured["prompt"] = kwargs.get("prompt")
        captured["route_resolver"] = kwargs.get("route_resolver")
        captured["catalog"] = kwargs.get("catalog")
        captured["repo"] = str(Path(kwargs["contract"].repo).resolve())
        captured["session"] = kwargs.get("session")
        kwargs["route_resolver"] = test_only_cursor_synthetic_route_binding
        kwargs["catalog"] = synthetic_catalog()
        kwargs["requested_model"] = SYNTHETIC_REQUESTED
        kwargs["contract"].requested_model = SYNTHETIC_REQUESTED
        return _cursor_acp_structured_launch(**kwargs)

    return wrap_launch


class CursorLiveCapableProofDriverTests(unittest.TestCase):
    def test_consumer_lifecycle_uses_fixture_workspace_and_owner(self):
        _skip_without_artifact()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            receipt = consume(
                live=False,
                state_root=root / "state",
                fixture_dir=root / "fixture",
                session="cproof-v3-lifecycle",
                continue_turn=True,
            )
        self.assertTrue(receipt["ok"])
        self.assertFalse(receipt["live"])
        self.assertFalse(receipt["live_claimed"])
        self.assertFalse(receipt["available"])
        self.assertEqual(receipt["entrypoint"], "_cursor_acp_structured_launch")
        self.assertEqual(receipt["continuation_api"], "owner.next_turn")
        self.assertEqual(receipt["cleanup_api"], "owner.finish")
        self.assertEqual(receipt["model"]["used_kind"], "synthetic_peer")
        self.assertEqual(receipt["model"]["current_model"], "candidate-fast")
        self.assertEqual(receipt["workspace"]["branch"], FIXTURE_BRANCH)
        self.assertTrue(receipt["workspace"]["path"].endswith("fixture"))
        self.assertNotEqual(receipt["workspace"]["path"], str(WORKTREE))
        self.assertEqual(receipt["baseline"]["passed"], 2)
        self.assertEqual(receipt["baseline"]["failed"], 1)
        self.assertEqual(receipt["after"]["tests"]["passed"], 3)
        self.assertTrue(receipt["after"]["protected_test_digest_unchanged"])
        self.assertTrue(receipt["offline_known_answer"]["offline_known_answer"])
        self.assertFalse(receipt["offline_known_answer"]["useful_agent_output"])
        self.assertIn("offline-only", receipt["offline_known_answer"]["label"])
        self.assertNotEqual(
            receipt["host"]["first_request_id"],
            receipt["runtime_ids"]["first"]["backend_session_id"],
        )
        self.assertNotEqual(
            receipt["host"]["first_request_id"],
            receipt["host"]["second_request_id"],
        )
        self.assertTrue(receipt["cleanup"]["final_discard"])
        self.assertTrue(receipt["cleanup"]["child_exit"]["exited"])
        self.assertEqual(
            receipt["process"]["first_turn"]["helper"]["role"],
            "implementation_or_helper",
        )
        self.assertFalse(receipt["process"]["first_turn"]["backend"]["inferred_from_helper_exit"])
        self.assertFalse(receipt["process"]["helper_exit_sufficient"])
        self.assertIsNone(receipt["cleanup"]["fence"])
        self.assertEqual(receipt["implementation_job_id"], IMPLEMENTATION_JOB_ID)
        serialized = str(receipt)
        self.assertNotIn(FIRST_TASK_TEXT, serialized)
        self.assertNotIn(SECOND_TASK_TEXT, serialized)
        self.assertNotIn("prompt", serialized)

    def test_live_rejects_existing_workspace_state_or_fence_before_launch(self):
        started = []

        def forbidden_launch(**_kwargs):
            started.append("structured_launch")
            raise AssertionError("existing live paths must not launch")

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "existing-workspace"
            workspace.mkdir()
            marker = workspace / "old-evidence.txt"
            marker.write_text("retain me\n")
            with mock.patch.object(
                sys.modules["cursor_live_capable_proof_driver"],
                "create_fixture_workspace",
                side_effect=AssertionError("must not recreate existing live workspace"),
            ):
                with self.assertRaisesRegex(RuntimeError, "already exists"):
                    consume(
                        live=True,
                        parent_release="parent-issued-test-release",
                        state_root=root / "fresh-state",
                        fixture_dir=workspace,
                        session="cproof-v3-reuse-workspace",
                        structured_launch=forbidden_launch,
                    )
            self.assertTrue(marker.is_file())
            self.assertEqual(marker.read_text(), "retain me\n")

            state = root / "existing-state"
            state.mkdir()
            (state / "retain.json").write_text("{}\n")
            with self.assertRaisesRegex(RuntimeError, "already exists"):
                consume(
                    live=True,
                    parent_release="parent-issued-test-release",
                    state_root=state,
                    fixture_dir=root / "fresh-workspace",
                    session="cproof-v3-reuse-state",
                    structured_launch=forbidden_launch,
                )
            self.assertTrue((state / "retain.json").is_file())

            fence_session = "cproof-v3-reuse-fence"
            fence_state = root / "fence-state"
            fence_paths = live_owned_paths(session=fence_session, state_root=fence_state)
            fence_paths["fence_dir"].mkdir(parents=True)
            fence_paths["fence"].write_text("{}\n")
            with self.assertRaisesRegex(RuntimeError, "already exists"):
                consume(
                    live=True,
                    parent_release="parent-issued-test-release",
                    state_root=fence_state,
                    fixture_dir=root / "fence-workspace",
                    session=fence_session,
                    structured_launch=forbidden_launch,
                )
            self.assertTrue(fence_paths["fence"].is_file())

            with self.assertRaisesRegex(RuntimeError, "explicit fresh --session"):
                require_explicit_live_session(None)
            with self.assertRaisesRegex(RuntimeError, "explicit fresh --session"):
                consume(
                    live=True,
                    parent_release="parent-issued-test-release",
                    structured_launch=forbidden_launch,
                    fixture_dir=root / "must-not-create",
                )
            self.assertIn(LIVE_SESSION_REQUIRED, LIVE_SESSION_REQUIRED)
            self.assertIn("preserved", LIVE_PATH_EXISTS)
            reject_existing_live_session_paths(
                live_owned_paths(
                    session="cproof-v3-absent",
                    state_root=root / "absent-state",
                    fixture_dir=root / "absent-workspace",
                )
            )
        self.assertEqual(started, [])

    def test_live_never_invokes_known_answer_helper(self):
        _skip_without_artifact()
        captured = {}
        known_answer_calls = []

        def boom(*_args, **_kwargs):
            known_answer_calls.append(True)
            raise AssertionError("known-answer helper invoked in live mode")

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture = root / "fixture"
            with mock.patch(
                "cursor_live_capable_proof_driver.apply_offline_only_known_answer_fix",
                side_effect=boom,
            ):
                receipt = consume(
                    live=True,
                    parent_release="parent-issued-test-release",
                    state_root=root / "state",
                    fixture_dir=fixture,
                    session="cproof-v3-no-known-answer",
                    continue_turn=True,
                    inspect_after=False,
                    structured_launch=_wrap_live_launch(captured),
                )
            impl = (fixture / "normalize-lines.mjs").read_text()
            self.assertEqual(impl, TEMPLATE_IMPL.read_text())
            self.assertEqual(known_answer_calls, [])
        self.assertEqual(captured["requested_model"], LIVE_SELECTOR)
        self.assertEqual(captured["prompt"], FIRST_TASK_TEXT)
        self.assertIs(captured["route_resolver"], resolve_cursor_acp_route_binding)
        self.assertIsNone(captured["catalog"])
        self.assertEqual(captured["repo"], str(fixture.resolve()))
        self.assertEqual(receipt["launch_parameters"]["requested_model"], LIVE_SELECTOR)
        self.assertEqual(receipt["launch_parameters"]["route_resolver"], OFFICIAL_RESOLVER_NAME)
        self.assertFalse(receipt["launch_parameters"]["catalog_injected"])
        self.assertEqual(receipt["launch_parameters"]["intended_kind"], "official_route")
        self.assertIsNone(receipt["offline_known_answer"])
        self.assertIsNone(receipt["after"])
        self.assertFalse(receipt["live_claimed"])
        self.assertFalse(receipt["available"])
        self.assertEqual(official_route_resolver.__name__, "official_route_resolver")
        staged = staged_live_invocation()
        self.assertFalse(staged["executed"])
        self.assertIn("--live", staged["command"])
        self.assertIn("--parent-release", staged["command"])
        self.assertIn("--session", staged["command"])
        self.assertEqual(staged["session"], STAGED_LIVE_SESSION)
        self.assertFalse(staged["preflight"]["workspace_exists"])
        self.assertFalse(staged["preflight"]["state_exists"])
        self.assertFalse(staged["preflight"]["fence_exists"])
        self.assertFalse(staged["preflight"]["rmtree_on_live"])
        self.assertEqual(staged["selector"], LIVE_SELECTOR)
        self.assertIn("normalizeLines", FIXED_IMPL)

    def test_structured_launch_is_first_turn_not_next_turn(self):
        _skip_without_artifact()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            receipt = consume(
                live=False,
                state_root=root / "state",
                fixture_dir=root / "fixture",
                session="cproof-v3-first-turn",
                continue_turn=True,
            )
        attribution = receipt["turn_attribution"]
        self.assertTrue(attribution["structured_launch_includes_first_turn"])
        self.assertTrue(attribution["require_observation_completes_first_turn"])
        self.assertFalse(attribution["owner_next_turn_is_first_turn"])
        self.assertEqual(attribution["first_turn_source"], FIRST_TURN_SOURCE)
        self.assertEqual(attribution["second_turn_source"], "owner.next_turn")
        self.assertEqual(attribution["first_request_id"], "cproof-v3-first-turn-turn-1")
        self.assertEqual(attribution["second_request_id"], "cproof-v3-first-turn-turn-2")
        self.assertEqual(
            receipt["process"]["first_turn"]["sampled_after"],
            "structured_launch_first_turn",
        )
        self.assertEqual(
            receipt["process"]["second_turn"]["sampled_after"],
            "owner_next_turn_second_turn",
        )
        self.assertFalse(receipt["process"]["first_turn"]["owner_next_turn_is_first_turn"])
        self.assertFalse(receipt["launch_parameters"]["owner_next_turn_is_first_turn"])

    def test_helper_versus_backend_observation(self):
        helper = {
            "pid": 4242,
            "returncode": None,
            "exited": False,
            "kind": "synthetic_peer",
        }
        backend = {
            "pid": 4343,
            "ppid": 4242,
            "executable_name": "cursor-agent",
            "start_identity": "Mon Sep 21 00:00:00 2026",
        }
        peer = {
            "pid": 4444,
            "ppid": 4242,
            "executable_name": "node",
            "start_identity": "Mon Sep 21 00:00:00 2026",
        }
        observed = observe_helper_and_backend(
            helper,
            sampled_after="structured_launch_first_turn",
            os_children=[backend, peer],
        )
        self.assertEqual(observed["helper"]["pid"], 4242)
        self.assertEqual(observed["helper"]["role"], "implementation_or_helper")
        self.assertNotEqual(observed["helper"]["pid"], observed["backend"]["incarnations"][0]["pid"])
        self.assertTrue(observed["backend"]["observed"])
        self.assertEqual(observed["backend"]["incarnations"][0]["pid"], 4343)
        self.assertEqual(observed["backend"]["incarnations"][0]["ppid"], 4242)
        self.assertEqual(observed["backend"]["incarnations"][0]["executable_name"], "cursor-agent")
        self.assertEqual(
            set(observed["backend"]["incarnations"][0]),
            {"pid", "ppid", "executable_name", "start_identity"},
        )
        self.assertFalse(observed["backend"]["inferred_from_helper_exit"])
        self.assertFalse(observed["backend"]["helper_exit_sufficient"])
        missing = observe_helper_and_backend(
            helper,
            sampled_after="structured_launch_first_turn",
            os_children=[peer],
        )
        self.assertFalse(missing["backend"]["observed"])
        self.assertIn("not inferred from helper exit", missing["backend"]["evidence_gap"])

    def test_backend_termination_verification_and_fence(self):
        _skip_without_artifact()
        captured = {}
        child = subprocess.Popen(["sleep", "90"])
        try:
            incarnation = {
                "pid": child.pid,
                "ppid": os.getpid(),
                "executable_name": "sleep",
                "start_identity": "synthetic-child",
            }
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                fixture = root / "fixture"
                surviving = consume(
                    live=True,
                    parent_release="parent-issued-test-release",
                    state_root=root / "state",
                    fixture_dir=fixture,
                    session="cproof-v3-backend-survive",
                    continue_turn=False,
                    inspect_after=False,
                    structured_launch=_wrap_live_launch(captured),
                    inject_backend_incarnations=[incarnation],
                )
                self.assertFalse(surviving["ok"])
                self.assertFalse(surviving["live_claimed"])
                fence = surviving["cleanup"]["fence"]
                self.assertIsNotNone(fence)
                self.assertTrue(fence["cleanup_uncertain"])
                self.assertTrue(fence["replacement_blocked"])
                self.assertFalse(fence["session_replaced"])
                self.assertFalse(fence["fixture_deleted"])
                self.assertFalse(fence["helper_exit_sufficient"])
                self.assertIn("survived owner.finish", fence["reason"])
                self.assertTrue(surviving["fixture_retained"])
                self.assertTrue(surviving["state_retained"])
                self.assertTrue((fixture / "normalize-lines.mjs").is_file())
                os.kill(child.pid, 0)
        finally:
            child.terminate()
            child.wait(timeout=30)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            missing = consume(
                live=True,
                parent_release="parent-issued-test-release",
                state_root=root / "state",
                fixture_dir=root / "fixture",
                session="cproof-v3-backend-missing",
                continue_turn=False,
                inspect_after=False,
                structured_launch=_wrap_live_launch({}),
            )
        self.assertFalse(missing["ok"])
        self.assertIsNotNone(missing["cleanup"]["fence"])
        self.assertIn("not observed", missing["cleanup"]["fence"]["reason"])
        self.assertFalse(missing["process"]["first_turn"]["backend"]["inferred_from_helper_exit"])
        self.assertFalse(missing["cleanup"]["fence"]["helper_exit_sufficient"])
        self.assertTrue(missing["fixture_retained"])
        self.assertTrue(missing["state_retained"])
        self.assertFalse(missing["session_replaced"])

    def test_mismatched_identity_and_model_are_rejected(self):
        _skip_without_artifact()
        model = reject_mismatched_model()
        self.assertTrue(model["ok"])
        self.assertEqual(model["rejected"], "mismatched_model")
        identities = reject_mismatched_workspace_and_owner()
        rejected = {item["rejected"] for item in identities["rejections"]}
        self.assertEqual(
            rejected,
            {"mismatched_workspace", "mismatched_owner", "mismatched_session"},
        )
        self.assertTrue(identities["cleanup"]["child_exited"])

    def test_injected_post_launch_cleanup_release_and_fence(self):
        _skip_without_artifact()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            released = consume(
                live=False,
                state_root=root / "release-state",
                fixture_dir=root / "release-fixture",
                session="cproof-v3-inject-release",
                inject_post_launch_failure="raise",
            )
            self.assertFalse(released["ok"])
            self.assertTrue(released["injected_failure"])
            self.assertTrue(released["primary_preserved"])
            self.assertEqual(released["primary_error"]["message"], "injected post-launch failure")
            self.assertTrue(released["finish_attempted_once"])
            self.assertTrue(released["cleanup"]["child_exit"]["exited"])
            self.assertIsNone(released["cleanup"]["fence"])
            self.assertTrue(released["fixture_retained"])
            self.assertTrue(released["state_retained"])
            self.assertFalse(released["session_replaced"])
            helper_pid = released["cleanup"]["child_exit"]["pid"]
            self.assertIsInstance(helper_pid, int)
            with self.assertRaises(OSError):
                os.kill(helper_pid, 0)

            held = {}
            uncertain = consume(
                live=False,
                state_root=root / "fence-state",
                fixture_dir=root / "fence-fixture",
                session="cproof-v3-inject-fence",
                inject_post_launch_failure="raise_uncertain",
                retain_owned_runtime=held,
            )
            self.assertFalse(uncertain["ok"])
            self.assertTrue(uncertain["primary_preserved"])
            self.assertTrue(uncertain["finish_attempted_once"])
            self.assertIsNotNone(uncertain["cleanup"]["fence"])
            self.assertTrue(uncertain["cleanup"]["fence"]["cleanup_uncertain"])
            self.assertTrue(uncertain["cleanup"]["fence"]["replacement_blocked"])
            self.assertFalse(uncertain["cleanup"]["fence"]["session_replaced"])
            self.assertFalse(uncertain["cleanup"]["fence"]["fixture_deleted"])
            self.assertTrue(uncertain["fixture_retained"])
            self.assertTrue((root / "fence-fixture" / "normalize-lines.mjs").is_file())
            self.assertTrue((root / "fence-state").is_dir())
            self.assertFalse(uncertain["session_replaced"])
            fence_path = Path(uncertain["cleanup"]["fence"]["path"])
            self.assertTrue(fence_path.is_file())
            proc = getattr(held.get("runtime"), "_proc", None)
            self.assertIsNotNone(proc)
            if proc.poll() is None:
                proc.terminate()
                proc.wait(timeout=30)
            self.assertIsNotNone(proc.poll())

    def test_live_release_rejects_before_process_start(self):
        started = []

        def forbidden_launch(**_kwargs):
            started.append("structured_launch")
            raise AssertionError("structured_launch must not start without release")

        with mock.patch("subprocess.Popen", side_effect=lambda *a, **k: started.append("popen")):
            with self.assertRaisesRegex(RuntimeError, "missing release rejects before process start"):
                reject_live_without_release(True, None)
            with self.assertRaisesRegex(RuntimeError, "parent-issued"):
                require_parent_release(None)
            rejected = reject_live_flag_without_release()
            self.assertTrue(rejected["ok"])
            self.assertEqual(rejected["rejected"], "live_release_missing")
            self.assertIn(LIVE_RELEASE_MISSING, rejected["message"])
            with self.assertRaisesRegex(RuntimeError, "missing release rejects before process start"):
                consume(
                    live=True,
                    parent_release=None,
                    session="cproof-v3-must-not-launch",
                    structured_launch=forbidden_launch,
                    fixture_dir=Path("/tmp/must-not-be-created-v3-live"),
                )
        self.assertEqual(started, [])

    def test_fixture_workspace_and_branch_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = Path(temporary) / "fixture"
            identity = create_fixture_workspace(fixture)
            self.assertEqual(identity["branch"], FIXTURE_BRANCH)
            self.assertEqual(require_attached_branch(identity), FIXTURE_BRANCH)
            baseline = capture_baseline(fixture)
            self.assertEqual(baseline["passed"], 2)
            self.assertEqual(baseline["failed"], 1)
            self.assertEqual(baseline["protected_test_sha256"], EXPECTED_PROTECTED_TEST_SHA256)
            self.assertNotEqual(identity["path"], str(WORKTREE))
            subprocess.run(
                ["git", "-C", str(fixture), "checkout", "--detach"],
                check=True,
                capture_output=True,
            )
            detached = fixture_identity(fixture)
            with self.assertRaisesRegex(RuntimeError, "detached"):
                require_attached_branch(detached)
            launched = []

            def forbidden_launch(**_kwargs):
                launched.append(True)
                raise AssertionError("detached fixture must not launch")

            with self.assertRaisesRegex(RuntimeError, "detached"):
                consume(
                    live=False,
                    state_root=Path(temporary) / "state",
                    fixture_dir=fixture,
                    session="cproof-v3-detached",
                    create_workspace=False,
                    structured_launch=forbidden_launch,
                )
            self.assertEqual(launched, [])


if __name__ == "__main__":
    unittest.main()
