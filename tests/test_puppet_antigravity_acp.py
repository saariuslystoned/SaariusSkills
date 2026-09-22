from __future__ import annotations

import copy
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "puppet" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from puppet_lib.antigravity_acp import (  # noqa: E402
    ACPX_LAST_INSPECTED_SOURCE_COMMIT,
    ACPX_LAST_INSPECTED_SOURCE_RELEASE,
    ACPX_SOURCE_COMMIT,
    CANDIDATE_SCHEMA,
    DEFAULT_ROUTE,
    OBSERVATION_SCHEMA,
    REGISTRY_REVISION,
    RUNTIME_ID,
    RUNTIME_VERSION,
    TARGET,
    TRANSPORT_ID,
    AntigravityAcpController,
    candidate_contract,
    validate_auth_observation,
    validate_candidate_contract,
    validate_candidate_observation,
    validate_model_observation,
    validate_question_observation,
)
from puppet_lib.errors import ValidationError  # noqa: E402
from puppet_lib.transport import (  # noqa: E402
    DEFAULT_TRANSPORT,
    bind_run_transport,
    transport_capability_table,
    transport_is_available,
)


def auth_observation(**changes):
    value = {
        "mode": "oauth-personal",
        "profile_env": "GEMINI_HOME",
        "credential_source": "runtime_owned",
        "account_state": "authenticated",
        "api_key_present": False,
        "cloud_credentials_present": False,
        "alternate_account": False,
        "interactive_login": False,
        "overage_state": "never",
    }
    value.update(changes)
    return value


def model_observation(**changes):
    value = {
        "requested_id": "gemini-3.8-flash-high",
        "advertised_ids": ["gemini-3.8-flash-high", "gemini-3.1-pro"],
        "observed_id": "gemini-3.8-flash-high",
        "selection_state": "exact",
        "effort": None,
    }
    value.update(changes)
    return value


def candidate_observation(**changes):
    value = {
        "schema": OBSERVATION_SCHEMA,
        "transport": TRANSPORT_ID,
        "target": TARGET,
        "qualification": "non_qualifying",
        "runtime": {
            "id": RUNTIME_ID,
            "version": RUNTIME_VERSION,
            "registry_revision": REGISTRY_REVISION,
        },
        "auth": auth_observation(),
        "model": model_observation(),
        "session": {"session_id": "session-1", "conversation_id": "conversation-1"},
        "terminal": {"state": "completed", "exit_code": 0, "result_id": "result-1"},
        "question": {
            "state": "none",
            "interaction_id": None,
            "human_required": False,
            "outcome": None,
        },
        "record_state": "candidate_non_qualifying",
    }
    value.update(changes)
    return value


class AntigravityAcpCandidateTests(unittest.TestCase):
    def test_contract_is_pinned_unavailable_and_native_default_unchanged(self):
        contract = candidate_contract()
        self.assertEqual(validate_candidate_contract(contract), contract)
        self.assertEqual(contract["transport"], TRANSPORT_ID)
        self.assertEqual(contract["default_route"], DEFAULT_ROUTE)
        self.assertFalse(contract["available"])
        self.assertEqual(contract["qualification"], "non_qualifying")
        table = transport_capability_table()
        self.assertEqual(table[TRANSPORT_ID]["implementation"], "implemented")
        self.assertEqual(DEFAULT_TRANSPORT, "tmux")
        self.assertEqual(bind_run_transport()["id"], "tmux")
        self.assertEqual(bind_run_transport(TRANSPORT_ID)["id"], TRANSPORT_ID)
        self.assertFalse(contract["available"])
        self.assertFalse(AntigravityAcpController.available())
        self.assertFalse(transport_is_available(TRANSPORT_ID))
        self.assertEqual(contract["runtime"]["acpx_release"], "0.19.0")
        self.assertEqual(
            contract["runtime"]["acpx_npm_integrity"],
            "sha512-sgG0CkhuvVxgfiksXjIPEl9hsHZW0CpxywPdQeoIP5D31gwZE4nrnddLUUqaSCLb1UIM7LFPBL5qdvy15/+B6Q==",
        )
        self.assertEqual(
            contract["runtime"]["acpx_tarball_sha256"],
            "5a61820401cfed668ce3ad77a2feaebdd9e496a037ba28b2afca3224e7505c6d",
        )
        self.assertIsNone(contract["runtime"]["acpx_source_commit"])
        self.assertIsNone(ACPX_SOURCE_COMMIT)
        self.assertEqual(
            contract["runtime"]["last_inspected_source_commit"],
            ACPX_LAST_INSPECTED_SOURCE_COMMIT,
        )
        self.assertEqual(
            contract["runtime"]["last_inspected_source_commit"],
            "50a47ad10a75431cbc276ec9b555d11fe1f69c84",
        )
        self.assertEqual(
            contract["runtime"]["last_inspected_source_release"],
            ACPX_LAST_INSPECTED_SOURCE_RELEASE,
        )
        self.assertEqual(contract["runtime"]["last_inspected_source_release"], "0.17.1")

    def test_contract_rejects_generic_acp_or_pin_drift(self):
        generic = candidate_contract()
        generic["transport"] = "acp"
        with self.assertRaisesRegex(ValidationError, "transport is invalid"):
            validate_candidate_contract(generic)

        drifted = candidate_contract()
        drifted["runtime"]["version"] = "1.1.2"
        with self.assertRaisesRegex(ValidationError, "runtime pin drifted"):
            validate_candidate_contract(drifted)

        qualified = candidate_contract()
        qualified["qualification"] = "qualified"
        with self.assertRaisesRegex(ValidationError, "cannot claim qualification"):
            validate_candidate_contract(qualified)

        claimed_source = candidate_contract()
        claimed_source["runtime"]["acpx_source_commit"] = ACPX_LAST_INSPECTED_SOURCE_COMMIT
        with self.assertRaisesRegex(ValidationError, "source commit is unknown"):
            validate_candidate_contract(claimed_source)

        relabeled_release = candidate_contract()
        relabeled_release["runtime"]["last_inspected_source_release"] = "0.19.0"
        with self.assertRaisesRegex(ValidationError, "not the published 0.19.0 release"):
            validate_candidate_contract(relabeled_release)

    def test_js_runtime_pin_keeps_published_source_unknown(self):
        script = (
            "import { RUNTIME_PIN, validateRuntimePin } "
            "from './bridge/antigravity-acp/contract.mjs'; "
            "process.stdout.write(JSON.stringify(validateRuntimePin(RUNTIME_PIN)))"
        )
        raw = subprocess.check_output(
            ["node", "--input-type=module", "-e", script],
            cwd=ROOT,
        )
        pin = json.loads(raw)
        runtime = candidate_contract()["runtime"]
        self.assertIsNone(pin["acpxSourceCommit"])
        self.assertIsNone(runtime["acpx_source_commit"])
        self.assertEqual(
            pin["lastInspectedSourceCommit"],
            runtime["last_inspected_source_commit"],
        )
        self.assertEqual(pin["lastInspectedSourceRelease"], "0.17.1")
        self.assertEqual(pin["acpxRelease"], runtime["acpx_release"])
        self.assertEqual(pin["acpxNpmIntegrity"], runtime["acpx_npm_integrity"])
        self.assertEqual(pin["acpxTarballSha256"], runtime["acpx_tarball_sha256"])
        self.assertEqual(pin["acpxRuntimeJsSha256"], runtime["acpx_runtime_js_sha256"])
        claimed = dict(pin, acpxSourceCommit=ACPX_LAST_INSPECTED_SOURCE_COMMIT)
        with self.assertRaises(subprocess.CalledProcessError):
            subprocess.check_output(
                [
                    "node",
                    "--input-type=module",
                    "-e",
                    (
                        "import { validateRuntimePin } from './bridge/antigravity-acp/contract.mjs'; "
                        "validateRuntimePin(%s)"
                    )
                    % json.dumps(claimed),
                ],
                cwd=ROOT,
                stderr=subprocess.STDOUT,
            )

    def test_auth_rejects_every_fallback_and_ambiguous_state(self):
        for changes, message in (
            ({"api_key_present": True}, "API-key fallback"),
            ({"cloud_credentials_present": True}, "Cloud credential fallback"),
            ({"alternate_account": True}, "alternate-account fallback"),
            ({"interactive_login": True}, "interactive login"),
            ({"overage_state": "unknown"}, "overage state"),
            ({"mode": "api-key"}, "personal OAuth"),
        ):
            with self.subTest(changes=changes):
                with self.assertRaisesRegex(ValidationError, message):
                    validate_auth_observation(auth_observation(**changes))

    def test_model_requires_exact_advertised_observation_and_no_effort_inference(self):
        accepted = validate_model_observation(model_observation())
        self.assertEqual(
            accepted["advertised_ids"],
            ["gemini-3.8-flash-high", "gemini-3.1-pro"],
        )
        self.assertEqual(accepted["requested_id"], accepted["observed_id"])
        with self.assertRaisesRegex(ValidationError, "advertised id"):
            validate_model_observation(model_observation(requested_id="unknown"))
        with self.assertRaisesRegex(ValidationError, "does not match"):
            validate_model_observation(model_observation(observed_id="substituted"))
        with self.assertRaisesRegex(ValidationError, "effort selection"):
            validate_model_observation(model_observation(effort="high"))

    def test_observation_rejects_unbounded_or_body_bearing_advertised_models(self):
        exact = "gemini-3.8-flash-high"
        sibling = "gemini-3.1-pro"
        cases = (
            ([exact, "x" * 201], "advertised model is invalid"),
            ([exact, sibling + "\nprompt body"], "advertised model contains control characters"),
            ([exact, sibling + "\routput body"], "advertised model contains control characters"),
            ([exact, sibling + "\x00content"], "advertised model contains control characters"),
        )
        for advertised_ids, message in cases:
            with self.subTest(advertised_ids=advertised_ids):
                model = model_observation(advertised_ids=advertised_ids)
                with self.assertRaisesRegex(ValidationError, message):
                    validate_model_observation(model)
                with self.assertRaisesRegex(ValidationError, message):
                    validate_candidate_observation(candidate_observation(model=model))

    def test_interaction_question_must_cancel_and_never_carries_question_body(self):
        question = {
            "state": "interaction_required",
            "interaction_id": "interaction-1",
            "human_required": True,
            "outcome": "cancelled",
        }
        self.assertEqual(validate_question_observation(question), question)
        with self.assertRaisesRegex(ValidationError, "fail closed"):
            validate_question_observation({**question, "outcome": "answered"})
        with self.assertRaisesRegex(ValidationError, "question observation fields do not match schema"):
            validate_question_observation({**question, "options": ["A", "B"]})

    def test_observation_is_body_free_and_non_qualifying(self):
        observation = candidate_observation()
        self.assertEqual(
            validate_candidate_observation(observation)["record_state"],
            "candidate_non_qualifying",
        )
        with self.assertRaisesRegex(ValidationError, "body-bearing field"):
            validate_candidate_observation({**observation, "prompt": "secret body"})

        nested_body = copy.deepcopy(observation)
        nested_body["question"] = {
            "state": "none",
            "interaction_id": None,
            "human_required": False,
            "outcome": None,
            "title": "question body",
        }
        with self.assertRaisesRegex(ValidationError, "body-bearing field"):
            validate_candidate_observation(nested_body)

        qualified = candidate_observation(qualification="qualified")
        with self.assertRaisesRegex(ValidationError, "cannot claim qualification"):
            validate_candidate_observation(qualified)

    def test_observation_preserves_allowlisted_terminal_failure_and_rejects_bodies(self):
        observation = candidate_observation(
            terminal={
                "state": "failed",
                "exit_code": 1,
                "result_id": "result-1",
                "status": "failed",
                "stop_reason": "timeout",
                "error_code": "ACP_TURN_FAILED",
                "event_kinds": ["status"],
            }
        )
        accepted = validate_candidate_observation(observation)
        self.assertEqual(accepted["terminal"]["status"], "failed")
        self.assertEqual(accepted["terminal"]["stop_reason"], "timeout")
        self.assertEqual(accepted["terminal"]["error_code"], "ACP_TURN_FAILED")
        self.assertEqual(accepted["terminal"]["event_kinds"], ["status"])
        with self.assertRaisesRegex(ValidationError, "body-bearing field prompt"):
            validate_candidate_observation(
                candidate_observation(
                    terminal={
                        "state": "failed",
                        "exit_code": 1,
                        "result_id": "result-1",
                        "prompt": "secret body",
                    }
                )
            )
        with self.assertRaisesRegex(ValidationError, "terminal stop_reason is invalid"):
            validate_candidate_observation(
                candidate_observation(
                    terminal={
                        "state": "failed",
                        "exit_code": 1,
                        "result_id": "result-1",
                        "status": "failed",
                        "stop_reason": "arbitrary_reason",
                    }
                )
            )


if __name__ == "__main__":
    unittest.main()
