from __future__ import annotations

import inspect
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "puppet" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from puppet_lib.agy_print import AgyPrintController
from puppet_lib.caller import make_blocker
from puppet_lib.cursor_acp import require_cursor_acp_target
from puppet_lib.errors import IdentityError, UnsupportedError
from puppet_lib.grok_admission import (
    GrokBuilderAdmissionController,
    GrokBuilderAdmissionFixture,
    caller_fields_from_observation,
    fixture_observation,
    fixture_receipt,
    grok_builder_receipt_fingerprint,
    prove_grok_builder_admission,
    prove_observed_model,
    prove_qualification_receipt,
    prove_session_identity,
    prove_shutdown,
    prove_terminal_result,
    prove_workspace_binding,
    qualify_grok_builder_lifecycle,
    require_grok_builder_target,
    require_live_grok_builder,
)
from puppet_lib.grok_launch import GROK_EXECUTABLE_SHA256, GROK_RUNTIME_BASENAME
from puppet_lib.instruction_planes import GROK_BUILD_VERSION
from puppet_lib.operator_plan import compile_operator_plan
from puppet_lib.qualification_scope import shared_source_paths, target_source_paths
from puppet_lib.tmux import TmuxController
from puppet_lib.transport import (
    bind_run_transport,
    transport_capability_table,
    transport_is_available,
)


def _workspace(**overrides):
    workspace = {
        "path": "/tmp/grok-builder-workspace",
        "branch": "codex/example",
        "head": "a" * 40,
        "tree": "b" * 40,
    }
    workspace.update(overrides)
    return workspace


class GrokBuilderAdmissionTests(unittest.TestCase):
    def test_success_proves_model_workspace_session_result_and_receipt(self):
        observation = fixture_observation()
        admitted = prove_grok_builder_admission(
            observation,
            expected_session="grok-builder-session",
            expected_grok_session_id="6f1c8a2e-4b70-4d91-9c3a-1e5b7d0f2a44",
            expected_workspace=_workspace(),
            expected_receipt=fixture_receipt(),
            requested_model="default",
            expected_observed_model="grok-4.5",
            expected_result_state="completed",
            expected_result_id="grok-result-1",
        )
        self.assertEqual(admitted["schema"], "puppet.grok-builder-admission/v1")
        self.assertEqual(admitted["target"], "grok")
        self.assertEqual(admitted["transport"], "tmux")
        self.assertTrue(admitted["builder_admitted"])
        self.assertEqual(admitted["model"]["observed_model"], "grok-4.5")
        self.assertEqual(admitted["model"]["source"], "runtime_metadata")
        self.assertEqual(admitted["model"]["requested_model"], "default")
        self.assertEqual(admitted["model"]["executable_sha256"], GROK_EXECUTABLE_SHA256)
        self.assertEqual(admitted["model"]["version"], GROK_BUILD_VERSION)
        self.assertEqual(admitted["model"]["basename"], GROK_RUNTIME_BASENAME)
        self.assertEqual(admitted["workspace"]["path"], "/tmp/grok-builder-workspace")
        self.assertEqual(admitted["workspace"]["branch"], "codex/example")
        self.assertEqual(admitted["workspace"]["head"], "a" * 40)
        self.assertEqual(admitted["workspace"]["tree"], "b" * 40)
        self.assertEqual(
            admitted["session"]["grok_session_id"],
            "6f1c8a2e-4b70-4d91-9c3a-1e5b7d0f2a44",
        )
        self.assertEqual(admitted["terminal_result"]["state"], "completed")
        self.assertEqual(admitted["terminal_result"]["result_id"], "grok-result-1")
        self.assertTrue(admitted["qualification_receipt"]["qualification_authorized"])
        self.assertFalse(admitted["launch_authorized"])
        self.assertFalse(admitted["live_grok_claimed"])
        fields = caller_fields_from_observation(observation)
        self.assertEqual(fields["transport"]["id"], "tmux")
        self.assertEqual(fields["caller_outcome"]["worker_completion"], "none")
        self.assertEqual(fields["caller_outcome"]["controller_acceptance"], "none")
        self.assertEqual(fields["caller_outcome"]["halt"], "none")
        self.assertIsNone(fields["final_outcome"])

    def test_stage2_outcomes_stay_distinct_on_grok_admission(self):
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
                "session": "grok-builder-session",
                "grok_session_id": "6f1c8a2e-4b70-4d91-9c3a-1e5b7d0f2a44",
                "halted": True,
            },
        )
        halted_fields = caller_fields_from_observation(halted, halt_confirmed=True)
        self.assertEqual(halted_fields["caller_outcome"]["halt"], "confirmed")
        self.assertEqual(
            halted_fields["caller_outcome"]["controller_acceptance"], "none"
        )
        self.assertEqual(halted_fields["caller_outcome"]["worker_completion"], "none")
        qualified = qualify_grok_builder_lifecycle(
            accepted,
            expected_session="grok-builder-session",
            expected_grok_session_id="6f1c8a2e-4b70-4d91-9c3a-1e5b7d0f2a44",
            expected_workspace=_workspace(),
            requested_model="default",
        )
        self.assertEqual(qualified["schema"], "puppet.grok-builder-lifecycle/v1")
        self.assertFalse(qualified["live_grok_claimed"])
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
        selector_only["observed_model"] = {"id": "default", "source": "selector"}
        with self.assertRaises(IdentityError) as raised:
            prove_observed_model(selector_only)
        self.assertEqual(
            raised.exception.as_dict()["blocker"]["code"],
            "model_observation_selector_only",
        )
        self.assertNotIn("\n", raised.exception.as_dict()["blocker"]["changed"])
        copied_selector = fixture_observation(
            observed_model="default",
            runtime_model="default",
        )
        with self.assertRaisesRegex(IdentityError, "requested selector"):
            prove_observed_model(copied_selector)
        missing_runtime = fixture_observation(
            observed_model="grok-4.5",
            runtime_model="other-runtime-model",
        )
        with self.assertRaisesRegex(IdentityError, "missing from Grok runtime"):
            prove_observed_model(missing_runtime)
        mismatched = fixture_observation()
        with self.assertRaises(IdentityError) as raised:
            prove_observed_model(
                mismatched,
                expected_observed_model="other-observed-model",
            )
        self.assertEqual(
            raised.exception.as_dict()["blocker"]["code"],
            "model_observation_mismatch",
        )
        wrong_runtime = fixture_observation(executable_sha256="aa" * 32)
        with self.assertRaisesRegex(IdentityError, "Build 0.2.112"):
            prove_observed_model(wrong_runtime)

    def test_wrong_workspace_session_and_result_fail_closed(self):
        observation = fixture_observation()
        with self.assertRaises(IdentityError) as raised:
            prove_workspace_binding(
                observation,
                expected_workspace=_workspace(path="/other/workspace"),
            )
        self.assertEqual(
            raised.exception.as_dict()["blocker"]["code"],
            "workspace_identity_mismatch",
        )
        with self.assertRaisesRegex(IdentityError, "workspace identity"):
            prove_workspace_binding(
                observation,
                expected_workspace=_workspace(branch="other-branch"),
            )
        with self.assertRaisesRegex(IdentityError, "workspace identity"):
            prove_workspace_binding(
                observation,
                expected_workspace=_workspace(head="c" * 40),
            )
        with self.assertRaisesRegex(IdentityError, "workspace identity"):
            prove_workspace_binding(
                observation,
                expected_workspace=_workspace(tree="d" * 40),
            )
        with self.assertRaisesRegex(IdentityError, "session and Grok session"):
            prove_session_identity(
                observation,
                expected_session="grok-builder-session",
                expected_grok_session_id="aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee",
            )
        with self.assertRaisesRegex(IdentityError, "terminal result state"):
            prove_terminal_result(observation, expected_state="failed")
        with self.assertRaisesRegex(IdentityError, "terminal result identity"):
            prove_terminal_result(observation, expected_result_id="other-result")

    def test_stale_receipt_fails_closed(self):
        stale_fingerprint = fixture_receipt(fingerprint="ee" * 32)
        with self.assertRaises(IdentityError) as raised:
            prove_qualification_receipt(fixture_observation(qualification_receipt=stale_fingerprint))
        self.assertEqual(
            raised.exception.as_dict()["blocker"]["code"],
            "qualification_receipt_invalid",
        )
        self.assertIn("stale", str(raised.exception))
        drifted = fixture_receipt(adapter_fingerprint="66" * 32)
        with self.assertRaises(IdentityError) as raised:
            prove_qualification_receipt(
                fixture_observation(),
                expected_receipt=drifted,
            )
        self.assertEqual(
            raised.exception.as_dict()["blocker"]["code"],
            "qualification_receipt_invalid",
        )
        unauthorized = fixture_receipt(qualification_authorized=False)
        unauthorized["fingerprint"] = grok_builder_receipt_fingerprint(unauthorized)
        with self.assertRaisesRegex(IdentityError, "not authorized"):
            prove_qualification_receipt(
                fixture_observation(qualification_receipt=unauthorized)
            )

    def test_wrong_target_and_foreign_transports_fail_closed(self):
        with self.assertRaises(UnsupportedError) as raised:
            require_grok_builder_target("cursor")
        payload = raised.exception.as_dict()["blocker"]
        self.assertEqual(payload["code"], "grok_builder_target_mismatch")
        self.assertIn("grok", payload["remedy"])
        self.assertNotIn("\n", payload["changed"])
        with self.assertRaisesRegex(UnsupportedError, "grok target"):
            require_grok_builder_target("agy")
        wrong_target = fixture_observation(target="cursor")
        with self.assertRaisesRegex(UnsupportedError, "grok target"):
            prove_observed_model(wrong_target)
        generic = fixture_observation(transport="acp")
        with self.assertRaisesRegex(IdentityError, "generic acp"):
            prove_observed_model(generic)
        cursor_acp = fixture_observation(transport="cursor-acp")
        with self.assertRaises(UnsupportedError) as raised:
            prove_observed_model(cursor_acp)
        self.assertEqual(
            raised.exception.as_dict()["blocker"]["code"],
            "transport_unsupported",
        )
        herdr = fixture_observation(transport="herdr")
        with self.assertRaisesRegex(UnsupportedError, "herdr"):
            prove_observed_model(herdr)

    def test_unavailable_observation_is_a_body_safe_blocker(self):
        with tempfile.TemporaryDirectory() as temporary:
            controller = GrokBuilderAdmissionController(Path(temporary))
            with self.assertRaises(UnsupportedError) as raised:
                controller.require_observation()
            payload = raised.exception.as_dict()["blocker"]
            self.assertEqual(payload["code"], "grok_builder_unavailable")
            self.assertIn("do not fall back", payload["remedy"])
            self.assertNotIn("\n", payload["changed"])

    def test_live_gate_stays_closed_and_does_not_fall_back(self):
        observation = fixture_observation()
        self.assertFalse(GrokBuilderAdmissionController.available())
        self.assertFalse(GrokBuilderAdmissionFixture.available())
        with self.assertRaises(UnsupportedError) as raised:
            require_live_grok_builder(observation)
        self.assertEqual(
            raised.exception.as_dict()["blocker"]["code"],
            "grok_launch_authority",
        )
        with mock.patch.object(
            TmuxController, "__init__", side_effect=AssertionError("tmux fallback")
        ), mock.patch.object(
            AgyPrintController, "__init__", side_effect=AssertionError("agy-print")
        ):
            with tempfile.TemporaryDirectory() as temporary:
                controller = GrokBuilderAdmissionController(
                    Path(temporary),
                    fixture=GrokBuilderAdmissionFixture(observation),
                )
                admitted = controller.admit(
                    expected_session="grok-builder-session",
                    expected_grok_session_id="6f1c8a2e-4b70-4d91-9c3a-1e5b7d0f2a44",
                    expected_workspace=_workspace(),
                )
        self.assertTrue(admitted["builder_admitted"])
        self.assertFalse(admitted["live_grok_claimed"])

    def test_existing_transports_and_generic_acp_stay_unchanged(self):
        self.assertEqual(bind_run_transport()["id"], "tmux")
        self.assertEqual(bind_run_transport("agy-print")["id"], "agy-print")
        self.assertEqual(bind_run_transport("cursor-acp")["id"], "cursor-acp")
        with self.assertRaises(UnsupportedError) as raised:
            bind_run_transport("acp")
        self.assertEqual(
            raised.exception.as_dict()["blocker"]["code"],
            "transport_unsupported",
        )
        with self.assertRaisesRegex(UnsupportedError, "not implemented"):
            bind_run_transport("herdr")
        with self.assertRaisesRegex(UnsupportedError, "cursor target"):
            require_cursor_acp_target("grok")
        table = transport_capability_table()
        self.assertEqual(table["tmux"]["implementation"], "implemented")
        self.assertEqual(table["agy-print"]["implementation"], "implemented")
        self.assertEqual(table["cursor-acp"]["implementation"], "implemented")
        self.assertEqual(table["acp"]["implementation"], "unsupported")
        self.assertEqual(table["herdr"]["implementation"], "unsupported")
        self.assertFalse(transport_is_available("cursor-acp"))
        self.assertEqual(
            make_blocker(code="tmux_unavailable", detail="tmux is unavailable")[
                "remedy"
            ].startswith("install tmux"),
            True,
        )

    def test_qualification_scope_keeps_grok_admission_target_local(self):
        grok_sources = set(target_source_paths("grok"))
        shared = set(shared_source_paths())
        self.assertIn("scripts/puppet_lib/grok_admission.py", grok_sources)
        self.assertNotIn("scripts/puppet_lib/grok_admission.py", shared)
        self.assertNotIn("scripts/puppet_lib/cursor_acp.py", grok_sources)
        self.assertNotIn("scripts/puppet_lib/agy_print.py", grok_sources)

    def test_halt_rejects_foreign_or_missing_session(self):
        observation = fixture_observation()
        with self.assertRaisesRegex(IdentityError, "halt proof is missing"):
            prove_shutdown(
                observation,
                expected_session="grok-builder-session",
                expected_grok_session_id="6f1c8a2e-4b70-4d91-9c3a-1e5b7d0f2a44",
            )
        foreign = fixture_observation(
            halt={
                "session": "other-session",
                "grok_session_id": "6f1c8a2e-4b70-4d91-9c3a-1e5b7d0f2a44",
                "halted": True,
            }
        )
        with self.assertRaisesRegex(IdentityError, "not confined"):
            prove_shutdown(
                foreign,
                expected_session="grok-builder-session",
                expected_grok_session_id="6f1c8a2e-4b70-4d91-9c3a-1e5b7d0f2a44",
            )

    def test_controller_caller_result_and_operator_plan_stay_frozen(self):
        with tempfile.TemporaryDirectory() as temporary:
            controller = GrokBuilderAdmissionController(
                Path(temporary),
                fixture=GrokBuilderAdmissionFixture(
                    fixture_observation(
                        last_checkpoint={"checkpoint_id": "c" * 64},
                        record_state="ACCEPTED",
                    )
                ),
            )
            result = controller.caller_result(
                expected_session="grok-builder-session",
                expected_grok_session_id="6f1c8a2e-4b70-4d91-9c3a-1e5b7d0f2a44",
                expected_workspace=_workspace(),
                record_state="ACCEPTED",
            )
        self.assertTrue(result["ok"])
        self.assertFalse(result["live_grok_claimed"])
        self.assertEqual(result["caller_outcome"]["controller_acceptance"], "accepted")
        self.assertIsNotNone(result["final_outcome"])
        params = inspect.signature(compile_operator_plan).parameters
        self.assertNotIn("transport", params)
        self.assertNotIn("requested_transport", params)
        source = inspect.getsource(compile_operator_plan)
        self.assertNotIn('result["transport"]', source)
        self.assertNotIn("'transport':", source.split("result: Dict[str, Any] = {", 1)[1])


if __name__ == "__main__":
    unittest.main()
