from __future__ import annotations

import inspect
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "puppet" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import adapter_lab as puppet_adapter_lab  # noqa: E402
from puppet_lib import adapter_manifest  # noqa: E402
from puppet_lib.errors import (  # noqa: E402
    IdentityError,
    UnsupportedError,
    ValidationError,
)
from matched_control_experimental import (  # noqa: E402
    EXPERIMENTAL_MATCHED_CONTROL_SCHEMA,
    EXPERIMENTAL_MATCHED_CONTROL_SCOPE,
    NON_AUTHORITATIVE,
    PROMOTION_FORBIDDEN,
    REQUIRED_CONTROLLER_EVIDENCE,
    validate_experimental_matched_control_candidate,
)


def process(pid: int) -> dict:
    return {
        "identity_version": 2,
        "pid": pid,
        "start": "Wed Jul 22 20:00:00 2026",
        "kernel_birth_id": "fixture:%d" % pid,
        "command": "claude",
        "executable_path": "/opt/puppet-fixture/claude",
        "device": 100,
        "inode": pid,
    }


def root_identity(seed: int) -> dict:
    return {
        "path_sha256": "%064x" % seed,
        "device": 100,
        "inode": seed,
        "uid": 501,
        "mode": 0o700,
    }


def session(role: str, seed: int, *, entry_mode: str = "direct") -> dict:
    return {
        "authority": NON_AUTHORITATIVE,
        "role": role,
        "session": "%s-session" % role,
        "run_id": "%s-run" % role,
        "target": "claude",
        "controller": "codex",
        "process": process(4200 + seed),
        "lease_sha256": ("%x" % (seed + 2)) * 64,
        "workspace": root_identity(seed + 10),
        "config": root_identity(seed + 20),
        "entry_mode": entry_mode,
        "native_plane": (
            "per_run_additive_candidate" if role == "activated" else "none"
        ),
    }


def candidate() -> dict:
    references = []
    for index, required in enumerate(REQUIRED_CONTROLLER_EVIDENCE, start=1):
        references.append(
            {
                "authority": NON_AUTHORITATIVE,
                **required,
                "path": "candidate/%02d-%s.json" % (index, required["kind"]),
                "sha256": ("%x" % index) * 64,
            }
        )
    return {
        "schema": EXPERIMENTAL_MATCHED_CONTROL_SCHEMA,
        "qualification_scope": EXPERIMENTAL_MATCHED_CONTROL_SCOPE,
        "promotion_status": PROMOTION_FORBIDDEN,
        "result": "not_evaluated",
        "target": "claude",
        "controller": "codex",
        "campaign_id": "campaign-one",
        "goal_fingerprint": "a" * 64,
        "manifest_fingerprint": "b" * 64,
        "descriptor_sha256": "c" * 64,
        "compiled_marker_sha256": "d" * 64,
        "runtime_defaults": {
            "authority": NON_AUTHORITATIVE,
            "model_selection": "current_default_unqualified",
            "model_identity": "live_controller_observation_required",
            "provider_selection": "current_default_unqualified",
            "provider_identity": "live_controller_observation_required",
            "effort_selection": "current_default_unqualified",
            "effort_identity": "unavailable",
            "config_selection": "exact_controller_owned_lane_required",
        },
        "activated": session("activated", 1),
        "control": session("control", 2),
        "evidence_refs": references,
    }


class ExperimentalMatchedControlTests(unittest.TestCase):
    def test_candidate_is_exact_body_free_and_explicitly_non_promotable(self):
        value = candidate()
        self.assertEqual(validate_experimental_matched_control_candidate(value), value)
        serialized = repr(value)
        self.assertNotIn("no_bleed", serialized)
        self.assertNotIn("passed", serialized)
        self.assertNotIn("transcript", serialized)
        self.assertEqual(value["result"], "not_evaluated")
        self.assertEqual(value["promotion_status"], PROMOTION_FORBIDDEN)
        self.assertTrue(
            all(
                item["authority"] == NON_AUTHORITATIVE
                for item in value["evidence_refs"]
            )
        )

    def test_candidate_cannot_add_a_verdict_or_sensitive_body_field(self):
        value = candidate()
        value["qualified"] = True
        with self.assertRaisesRegex(ValidationError, "fields are invalid"):
            validate_experimental_matched_control_candidate(value)

        value = candidate()
        value["evidence_refs"][0]["raw_log"] = "marker body"
        with self.assertRaises(ValidationError):
            validate_experimental_matched_control_candidate(value)

    def test_missing_reordered_or_authoritative_claims_fail_closed(self):
        value = candidate()
        value["evidence_refs"].pop()
        with self.assertRaisesRegex(ValidationError, "incomplete"):
            validate_experimental_matched_control_candidate(value)

        value = candidate()
        value["evidence_refs"][0], value["evidence_refs"][1] = (
            value["evidence_refs"][1],
            value["evidence_refs"][0],
        )
        with self.assertRaisesRegex(ValidationError, "order is invalid"):
            validate_experimental_matched_control_candidate(value)

        value = candidate()
        value["evidence_refs"][0]["authority"] = "controller_verified"
        with self.assertRaisesRegex(ValidationError, "order is invalid"):
            validate_experimental_matched_control_candidate(value)

    def test_pair_must_use_distinct_identities_and_one_entry_mode(self):
        value = candidate()
        value["control"]["session"] = value["activated"]["session"]
        with self.assertRaisesRegex(IdentityError, "reuses"):
            validate_experimental_matched_control_candidate(value)

        value = candidate()
        value["control"]["entry_mode"] = "cockpit"
        with self.assertRaisesRegex(IdentityError, "entry modes"):
            validate_experimental_matched_control_candidate(value)

    def test_runtime_defaults_cannot_claim_model_or_provider_identity(self):
        value = candidate()
        value["runtime_defaults"]["model_identity"] = "claude-opus"
        with self.assertRaisesRegex(ValidationError, "runtime defaults"):
            validate_experimental_matched_control_candidate(value)

        value = candidate()
        value["runtime_defaults"]["provider_identity"] = "anthropic"
        with self.assertRaisesRegex(ValidationError, "runtime defaults"):
            validate_experimental_matched_control_candidate(value)

    def test_candidate_module_is_not_imported_by_qualification_code(self):
        self.assertNotIn("matched_control", inspect.getsource(adapter_manifest))
        self.assertNotIn("matched_control", inspect.getsource(puppet_adapter_lab))

    def test_adapter_lab_still_rejects_every_activation_receipt(self):
        arguments = SimpleNamespace(
            manifest=Path("unused"),
            mapping=Path("unused"),
            receipt=Path("unused"),
            out=Path("unused"),
        )
        with (
            patch.object(
                puppet_adapter_lab.AdapterManifest,
                "from_path",
                return_value=SimpleNamespace(raw={"doctor_only": True}),
            ),
            patch.object(
                puppet_adapter_lab,
                "read_json",
                return_value={},
            ),
            patch.object(
                puppet_adapter_lab,
                "_verified_receipt",
                return_value={
                    "target": "claude",
                    "plane_activation": {
                        "qualification_scope": EXPERIMENTAL_MATCHED_CONTROL_SCOPE
                    },
                },
            ),
            patch.object(Path, "resolve", return_value=Path("/tmp/receipt.json")),
        ):
            with self.assertRaisesRegex(UnsupportedError, "matched no-bleed"):
                puppet_adapter_lab._qualify(arguments)


if __name__ == "__main__":
    unittest.main()
