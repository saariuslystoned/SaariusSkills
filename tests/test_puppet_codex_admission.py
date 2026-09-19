from __future__ import annotations

import inspect
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

CODEX_SESSION_ID = "3a1e9c70-8b24-4d51-9f06-2c7e4a8b9153"

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "puppet" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from puppet_lib.agy_print import AgyPrintController
from puppet_lib.caller import make_blocker
from puppet_lib.codex_admission import (
    CodexBuilderAdmissionController,
    CodexBuilderAdmissionFixture,
    caller_fields_from_observation,
    codex_builder_receipt_fingerprint,
    fixture_observation,
    fixture_receipt,
    prove_codex_builder_admission,
    prove_observed_model,
    prove_qualification_receipt,
    prove_session_identity,
    prove_shutdown,
    prove_terminal_result,
    prove_workspace_binding,
    qualify_codex_builder_lifecycle,
    require_codex_builder_target,
    require_live_codex_builder,
    validate_codex_builder_observation,
)
from puppet_lib.codex_launch import (
    CURRENT_DEFAULT_SELECTION,
    DEFAULT_MODEL_SENTINEL,
    EXPECTED_EXECUTABLE_SHA256,
    EXPECTED_VERSION_SHA256,
    EXPECTED_VERSION_TEXT,
    EXPLICIT_MODEL_CLASSIFICATION,
)
from puppet_lib.codex_qualification import PAIR_KIND, PAIR_SCHEMA_VERSION
from puppet_lib.cursor_acp import require_cursor_acp_target
from puppet_lib.errors import IdentityError, UnsupportedError, ValidationError
from puppet_lib.grok_admission import require_grok_builder_target
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
        "path": "/tmp/codex-builder-workspace",
        "branch": "codex/example",
        "head": "a" * 40,
        "tree": "b" * 40,
    }
    workspace.update(overrides)
    return workspace


class CodexBuilderAdmissionTests(unittest.TestCase):
    def test_success_proves_model_workspace_session_result_and_receipt(self):
        observation = fixture_observation()
        admitted = prove_codex_builder_admission(
            observation,
            expected_session="codex-builder-session",
            expected_codex_session_id=CODEX_SESSION_ID,
            expected_workspace=_workspace(),
            expected_receipt=fixture_receipt(),
            requested_model=CURRENT_DEFAULT_SELECTION,
            expected_observed_model="gpt-5.6-sol",
            expected_result_state="completed",
            expected_result_id="codex-result-1",
        )
        self.assertEqual(admitted["schema"], "puppet.codex-builder-admission/v1")
        self.assertEqual(admitted["target"], "codex")
        self.assertEqual(admitted["transport"], "tmux")
        self.assertTrue(admitted["builder_admitted"])
        self.assertEqual(admitted["model"]["observed_model"], "gpt-5.6-sol")
        self.assertEqual(admitted["model"]["source"], "doctor_observation")
        self.assertEqual(
            admitted["model"]["classification"], EXPLICIT_MODEL_CLASSIFICATION
        )
        self.assertEqual(admitted["model"]["requested_model"], CURRENT_DEFAULT_SELECTION)
        self.assertEqual(admitted["model"]["executable_sha256"], EXPECTED_EXECUTABLE_SHA256)
        self.assertEqual(admitted["model"]["version_text"], EXPECTED_VERSION_TEXT)
        self.assertEqual(admitted["model"]["version_sha256"], EXPECTED_VERSION_SHA256)
        self.assertEqual(admitted["workspace"]["path"], "/tmp/codex-builder-workspace")
        self.assertEqual(admitted["workspace"]["branch"], "codex/example")
        self.assertEqual(admitted["workspace"]["head"], "a" * 40)
        self.assertEqual(admitted["workspace"]["tree"], "b" * 40)
        self.assertEqual(admitted["session"]["codex_session_id"], CODEX_SESSION_ID)
        self.assertEqual(admitted["terminal_result"]["state"], "completed")
        self.assertEqual(admitted["terminal_result"]["result_id"], "codex-result-1")
        self.assertTrue(admitted["qualification_receipt"]["qualification_authorized"])
        self.assertFalse(admitted["qualification_receipt"]["public_launch_authorized"])
        self.assertEqual(admitted["qualification_receipt"]["kind"], PAIR_KIND)
        self.assertEqual(
            admitted["qualification_receipt"]["qualification_schema_version"],
            PAIR_SCHEMA_VERSION,
        )
        self.assertFalse(admitted["launch_authorized"])
        self.assertFalse(admitted["live_codex_claimed"])
        fields = caller_fields_from_observation(observation)
        self.assertEqual(fields["transport"]["id"], "tmux")
        self.assertEqual(fields["caller_outcome"]["worker_completion"], "none")
        self.assertEqual(fields["caller_outcome"]["controller_acceptance"], "none")
        self.assertEqual(fields["caller_outcome"]["halt"], "none")
        self.assertIsNone(fields["final_outcome"])

    def test_stage2_outcomes_stay_distinct_on_codex_admission(self):
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
                "session": "codex-builder-session",
                "codex_session_id": CODEX_SESSION_ID,
                "halted": True,
            },
        )
        halted_fields = caller_fields_from_observation(halted, halt_confirmed=True)
        self.assertEqual(halted_fields["caller_outcome"]["halt"], "confirmed")
        self.assertEqual(
            halted_fields["caller_outcome"]["controller_acceptance"], "none"
        )
        self.assertEqual(halted_fields["caller_outcome"]["worker_completion"], "none")
        qualified = qualify_codex_builder_lifecycle(
            accepted,
            expected_session="codex-builder-session",
            expected_codex_session_id=CODEX_SESSION_ID,
            expected_workspace=_workspace(),
            requested_model=CURRENT_DEFAULT_SELECTION,
        )
        self.assertEqual(qualified["schema"], "puppet.codex-builder-lifecycle/v1")
        self.assertFalse(qualified["live_codex_claimed"])
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
            "id": CURRENT_DEFAULT_SELECTION,
            "source": "selector",
            "classification": EXPLICIT_MODEL_CLASSIFICATION,
        }
        with self.assertRaises(IdentityError) as raised:
            prove_observed_model(selector_only)
        self.assertEqual(
            raised.exception.as_dict()["blocker"]["code"],
            "model_observation_selector_only",
        )
        self.assertNotIn("\n", raised.exception.as_dict()["blocker"]["changed"])
        default_sentinel = fixture_observation(
            observed_model=DEFAULT_MODEL_SENTINEL,
            runtime_model=DEFAULT_MODEL_SENTINEL,
        )
        with self.assertRaisesRegex(IdentityError, "requested selector"):
            prove_observed_model(default_sentinel)
        copied_selector = fixture_observation(
            requested_model="gpt-5.6-sol",
            observed_model="gpt-5.6-sol",
            runtime_model="gpt-5.6-sol",
        )
        with self.assertRaisesRegex(IdentityError, "requested selector"):
            prove_observed_model(copied_selector)
        default_classification = fixture_observation(
            observed_classification="available_for_test_plan_only",
        )
        with self.assertRaisesRegex(IdentityError, "requested selector"):
            prove_observed_model(default_classification)
        missing_runtime = fixture_observation(
            observed_model="gpt-5.6-sol",
            runtime_model="other-runtime-model",
        )
        with self.assertRaisesRegex(IdentityError, "missing from Codex runtime"):
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
        with self.assertRaisesRegex(IdentityError, "codex-cli 0.145.0"):
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
        with self.assertRaisesRegex(IdentityError, "session and Codex session"):
            prove_session_identity(
                observation,
                expected_session="codex-builder-session",
                expected_codex_session_id="aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee",
            )
        with self.assertRaisesRegex(IdentityError, "terminal result state"):
            prove_terminal_result(observation, expected_state="failed")
        with self.assertRaisesRegex(IdentityError, "terminal result identity"):
            prove_terminal_result(observation, expected_result_id="other-result")

    def test_session_identity_requires_canonical_uuidv4(self):
        observation = fixture_observation()
        self.assertEqual(
            validate_codex_builder_observation(observation)["session"][
                "codex_session_id"
            ],
            CODEX_SESSION_ID,
        )
        for invalid in (
            "codex-builder-run",
            "3A1E9C70-8B24-4D51-9F06-2C7E4A8B9153",
            "3a1e9c70-8b24-1d51-9f06-2c7e4a8b9153",
            "not-a-uuid",
        ):
            invalid_session = fixture_observation(codex_session_id=invalid)
            with self.assertRaisesRegex(ValidationError, "UUIDv4"):
                validate_codex_builder_observation(invalid_session)
        conversation = fixture_observation()
        conversation["session"] = {
            "id": "codex-builder-session",
            "conversation_id": CODEX_SESSION_ID,
        }
        with self.assertRaisesRegex(ValidationError, "session fields"):
            validate_codex_builder_observation(conversation)
        grok_shaped = fixture_observation()
        grok_shaped["session"] = {
            "id": "codex-builder-session",
            "grok_session_id": CODEX_SESSION_ID,
        }
        with self.assertRaisesRegex(ValidationError, "session fields"):
            validate_codex_builder_observation(grok_shaped)

    def test_stale_receipt_fails_closed(self):
        stale_fingerprint = fixture_receipt(fingerprint="ee" * 32)
        with self.assertRaises(IdentityError) as raised:
            prove_qualification_receipt(
                fixture_observation(qualification_receipt=stale_fingerprint)
            )
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
        unauthorized["fingerprint"] = codex_builder_receipt_fingerprint(unauthorized)
        with self.assertRaisesRegex(IdentityError, "not authorized"):
            prove_qualification_receipt(
                fixture_observation(qualification_receipt=unauthorized)
            )
        claimed_launch = fixture_receipt(public_launch_authorized=True)
        claimed_launch["fingerprint"] = codex_builder_receipt_fingerprint(claimed_launch)
        with self.assertRaisesRegex(IdentityError, "not public launch"):
            prove_qualification_receipt(
                fixture_observation(qualification_receipt=claimed_launch)
            )

    def test_wrong_target_and_foreign_transports_fail_closed(self):
        with self.assertRaises(UnsupportedError) as raised:
            require_codex_builder_target("cursor")
        payload = raised.exception.as_dict()["blocker"]
        self.assertEqual(payload["code"], "codex_builder_target_mismatch")
        self.assertIn("codex", payload["remedy"])
        self.assertNotIn("\n", payload["changed"])
        with self.assertRaisesRegex(UnsupportedError, "codex target"):
            require_codex_builder_target("grok")
        with self.assertRaisesRegex(UnsupportedError, "grok target"):
            require_grok_builder_target("codex")
        wrong_target = fixture_observation(target="grok")
        with self.assertRaisesRegex(UnsupportedError, "codex target"):
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
            controller = CodexBuilderAdmissionController(Path(temporary))
            with self.assertRaises(UnsupportedError) as raised:
                controller.require_observation()
            payload = raised.exception.as_dict()["blocker"]
            self.assertEqual(payload["code"], "codex_builder_unavailable")
            self.assertIn("do not fall back", payload["remedy"])
            self.assertNotIn("\n", payload["changed"])

    def test_live_gate_stays_closed_and_does_not_fall_back(self):
        observation = fixture_observation()
        self.assertFalse(CodexBuilderAdmissionController.available())
        self.assertFalse(CodexBuilderAdmissionFixture.available())
        with self.assertRaises(UnsupportedError) as raised:
            require_live_codex_builder(observation)
        self.assertEqual(
            raised.exception.as_dict()["blocker"]["code"],
            "codex_launch_authority",
        )
        with mock.patch.object(
            TmuxController, "__init__", side_effect=AssertionError("tmux fallback")
        ), mock.patch.object(
            AgyPrintController, "__init__", side_effect=AssertionError("agy-print")
        ):
            with tempfile.TemporaryDirectory() as temporary:
                controller = CodexBuilderAdmissionController(
                    Path(temporary),
                    fixture=CodexBuilderAdmissionFixture(observation),
                )
                admitted = controller.admit(
                    expected_session="codex-builder-session",
                    expected_codex_session_id=CODEX_SESSION_ID,
                    expected_workspace=_workspace(),
                )
        self.assertTrue(admitted["builder_admitted"])
        self.assertFalse(admitted["live_codex_claimed"])

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
            require_cursor_acp_target("codex")
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

    def test_qualification_scope_keeps_codex_admission_target_local(self):
        codex_sources = set(target_source_paths("codex"))
        grok_sources = set(target_source_paths("grok"))
        shared = set(shared_source_paths())
        self.assertIn("scripts/puppet_lib/codex_admission.py", codex_sources)
        self.assertNotIn("scripts/puppet_lib/codex_admission.py", shared)
        self.assertNotIn("scripts/puppet_lib/codex_admission.py", grok_sources)
        self.assertNotIn("scripts/puppet_lib/grok_admission.py", codex_sources)
        self.assertNotIn("scripts/puppet_lib/cursor_acp.py", codex_sources)
        self.assertNotIn("scripts/puppet_lib/agy_print.py", codex_sources)

    def test_halt_rejects_foreign_or_missing_session(self):
        observation = fixture_observation()
        with self.assertRaisesRegex(IdentityError, "halt proof is missing"):
            prove_shutdown(
                observation,
                expected_session="codex-builder-session",
                expected_codex_session_id=CODEX_SESSION_ID,
            )
        foreign = fixture_observation(
            halt={
                "session": "other-session",
                "codex_session_id": CODEX_SESSION_ID,
                "halted": True,
            }
        )
        with self.assertRaisesRegex(IdentityError, "not confined"):
            prove_shutdown(
                foreign,
                expected_session="codex-builder-session",
                expected_codex_session_id=CODEX_SESSION_ID,
            )

    def test_controller_caller_result_and_operator_plan_stay_frozen(self):
        with tempfile.TemporaryDirectory() as temporary:
            controller = CodexBuilderAdmissionController(
                Path(temporary),
                fixture=CodexBuilderAdmissionFixture(
                    fixture_observation(
                        last_checkpoint={"checkpoint_id": "c" * 64},
                        record_state="ACCEPTED",
                    )
                ),
            )
            result = controller.caller_result(
                expected_session="codex-builder-session",
                expected_codex_session_id=CODEX_SESSION_ID,
                expected_workspace=_workspace(),
                record_state="ACCEPTED",
            )
        self.assertTrue(result["ok"])
        self.assertFalse(result["live_codex_claimed"])
        self.assertEqual(result["caller_outcome"]["controller_acceptance"], "accepted")
        self.assertIsNotNone(result["final_outcome"])
        self.assertIn("codex_admission", result)
        self.assertNotIn("grok_admission", result)
        params = inspect.signature(compile_operator_plan).parameters
        self.assertNotIn("transport", params)
        self.assertNotIn("requested_transport", params)
        source = inspect.getsource(compile_operator_plan)
        self.assertNotIn('result["transport"]', source)
        self.assertNotIn("'transport':", source.split("result: Dict[str, Any] = {", 1)[1])


if __name__ == "__main__":
    unittest.main()
