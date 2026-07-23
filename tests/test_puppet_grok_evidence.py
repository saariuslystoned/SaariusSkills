from __future__ import annotations

import inspect
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "puppet" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from puppet_lib import adapter_manifest, probe, session  # noqa: E402
from puppet_lib.errors import IdentityError, ValidationError  # noqa: E402
from puppet_lib.grok_evidence import (  # noqa: E402
    GROK_PASS_A_EXECUTABLE_SHA256,
    GROK_PASS_A_EVIDENCE_SCHEMA,
    GROK_PASS_A_MAIN_HELP_SHA256,
    GROK_PASS_A_TARGET_VERSION,
    GROK_PASS_A_VERSION_OUTPUT_SHA256,
    expected_grok_pass_a_evidence,
    load_grok_pass_a_evidence,
    validate_grok_pass_a_evidence,
)
from puppet_lib.grok_launch import (  # noqa: E402
    GROK_EXECUTABLE_SHA256,
    GROK_MAIN_HELP_SHA256,
    GROK_VERSION_OUTPUT_SHA256,
)
from puppet_lib.instruction_planes import GROK_BUILD_VERSION  # noqa: E402
from puppet_lib.safety import canonical_json_bytes, sha256_bytes  # noqa: E402


EVIDENCE = (
    ROOT / "plans" / "puppet" / "harnesses" / "grok-build-0.2.106-pass-a-evidence.json"
)


def with_recomputed_digest(value: dict) -> dict:
    changed = json.loads(json.dumps(value))
    changed.pop("record_sha256", None)
    changed["record_sha256"] = sha256_bytes(canonical_json_bytes(changed))
    return changed


class GrokPassAEvidenceTests(unittest.TestCase):
    def test_repository_packet_is_exact_canonical_source_only_evidence(self):
        value = load_grok_pass_a_evidence(EVIDENCE)
        self.assertEqual(value, expected_grok_pass_a_evidence())
        self.assertEqual(value["schema"], GROK_PASS_A_EVIDENCE_SCHEMA)
        self.assertEqual(value["target_version"], "0.2.106")
        self.assertEqual(value["clean_root_catalog"]["default_model"], "grok-4.5")
        self.assertEqual(
            value["clean_root_catalog"]["authenticated_effort"], "unavailable"
        )
        self.assertEqual(
            value["clean_root_catalog"]["observation_scope"],
            "clean_root_catalog_only",
        )
        provenance = value["provenance"]
        self.assertEqual(
            provenance["observation_source_revision"],
            "b8cce94bf2a4a62f974207a95abcfe1668412b90",
        )
        self.assertEqual(
            provenance["evidence_artifact_revision"],
            "c711c6b11ef529e1ff7860bef4232ad03c83e6ef",
        )
        self.assertNotEqual(
            provenance["observation_source_revision"],
            provenance["evidence_artifact_revision"],
        )
        self.assertEqual(
            provenance["artifact_blob_sha1"],
            "0e28e5d75f91f7415b619eaa27a6ce7b549750cc",
        )
        self.assertEqual(provenance["license"], "MIT")
        self.assertEqual(
            [row["claim_id"] for row in value["admission_rows"]],
            [
                "artifact_identity_candidate",
                "parser_capability_candidates",
                "clean_root_catalog_candidate",
            ],
        )
        self.assertEqual(
            value["parser_facts"]["reasoning_effort_flag"],
            "--reasoning-effort",
        )
        self.assertEqual(
            value["parser_facts"]["resume_flags"],
            ["--resume", "--continue"],
        )
        self.assertEqual(value["parser_facts"]["status_surface"], "unavailable")
        self.assertEqual(len(value["limitations"]), 11)
        for name in (
            "live_session_started",
            "private_store_accessed",
            "config_mutated",
            "live_semantics_verified",
            "launch_authorized",
            "model_selection_authorized",
            "qualification_authorized",
            "promotion_authorized",
        ):
            self.assertFalse(value[name])

    def test_historical_pass_a_tuple_is_decoupled_from_current_launch_tuple(self):
        self.assertEqual(GROK_PASS_A_TARGET_VERSION, "0.2.106")
        self.assertEqual(GROK_BUILD_VERSION, "0.2.111")
        self.assertNotEqual(GROK_PASS_A_EXECUTABLE_SHA256, GROK_EXECUTABLE_SHA256)
        self.assertNotEqual(
            GROK_PASS_A_VERSION_OUTPUT_SHA256,
            GROK_VERSION_OUTPUT_SHA256,
        )
        self.assertNotEqual(
            GROK_PASS_A_MAIN_HELP_SHA256,
            GROK_MAIN_HELP_SHA256,
        )

    def test_hash_and_semantic_tampering_fail_even_when_digest_is_recomputed(self):
        original = expected_grok_pass_a_evidence()
        mutations = (
            (
                "artifact",
                lambda item: item["artifact_hashes"].update(
                    {"main_help_sha256": "0" * 64}
                ),
            ),
            (
                "model",
                lambda item: item["clean_root_catalog"].update(
                    {"default_model": "grok-new"}
                ),
            ),
            (
                "parser",
                lambda item: item["parser_facts"].update(
                    {"agent_selector_scope": "additive"}
                ),
            ),
            (
                "effort",
                lambda item: item["parser_facts"].update(
                    {"reasoning_effort_flag": "--effort"}
                ),
            ),
            (
                "session",
                lambda item: item["parser_facts"].update({"resume_flags": []}),
            ),
            (
                "observation-source",
                lambda item: item["provenance"].update(
                    {"observation_source_revision": "1" * 40}
                ),
            ),
            (
                "evidence-revision",
                lambda item: item["provenance"].update(
                    {"evidence_artifact_revision": "2" * 40}
                ),
            ),
            (
                "evidence-artifact",
                lambda item: item["provenance"].update({"artifact_sha256": "0" * 64}),
            ),
            (
                "decision",
                lambda item: item["admission_rows"][0].update(
                    {"decision": "reuse_contract"}
                ),
            ),
            (
                "live-delta",
                lambda item: item["admission_rows"][2].update(
                    {"remaining_live_delta": []}
                ),
            ),
            ("authority", lambda item: item.update({"launch_authorized": True})),
            ("limitation", lambda item: item.update({"limitations": []})),
            ("hash-shape", lambda item: item.update({"artifact_hashes": []})),
        )
        for label, mutate in mutations:
            with self.subTest(label=label):
                changed = json.loads(json.dumps(original))
                mutate(changed)
                changed = with_recomputed_digest(changed)
                with self.assertRaises((IdentityError, ValidationError)):
                    validate_grok_pass_a_evidence(changed)

    def test_stale_digest_extra_fields_and_noncanonical_json_fail_closed(self):
        changed = expected_grok_pass_a_evidence()
        changed["state"] = "qualified"
        with self.assertRaises(IdentityError):
            validate_grok_pass_a_evidence(changed)

        changed = expected_grok_pass_a_evidence()
        changed["unexpected"] = True
        with self.assertRaises(ValidationError):
            validate_grok_pass_a_evidence(changed)

        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "evidence.json"
            path.write_text(
                json.dumps(expected_grok_pass_a_evidence(), indent=2) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(IdentityError, "canonical JSON"):
                load_grok_pass_a_evidence(path)

    def test_packet_is_body_free_and_has_no_runtime_consumer(self):
        value = load_grok_pass_a_evidence(EVIDENCE)
        encoded = json.dumps(value, sort_keys=True)
        self.assertNotIn("/Users/", encoded)
        self.assertNotIn("transcript", encoded.lower())
        self.assertNotIn("scrollback", encoded.lower())
        self.assertNotIn("task_body", encoded.lower())
        self.assertNotIn("output_body", encoded.lower())
        for module in (adapter_manifest, probe, session):
            self.assertNotIn("grok_evidence", inspect.getsource(module))


if __name__ == "__main__":
    unittest.main()
