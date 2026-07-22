from __future__ import annotations

import copy
import json
import sys
import unittest

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "puppet" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from puppet_lib.errors import ValidationError  # noqa: E402
from puppet_lib.instruction_planes import (  # noqa: E402
    descriptor_fingerprint,
    parse_instruction_plane_descriptor,
    validate_instruction_plane_descriptor,
)


def _fixture() -> dict:
    return {
        "schema": "puppet.instruction-plane/v1",
        "descriptor_id": "fixture-regular-coverage",
        "target": {
            "harness": "codex",
            "version": "0.145.0",
            "adapter_manifest_sha256": "0" * 64,
            "requested_model": "default",
            "observed_model": "unavailable",
            "config_fingerprint": "unavailable",
        },
        "plane": "harness_global",
        "status": {
            "surface": "factual",
            "activation": "qualification_only",
        },
        "materialize": [
            {
                "artifact_id": "instruction_contract",
                "root_ref": "config_root",
                "relative_path": "workspace/.puppet/contracts/instruction_contract.md",
                "content_ref": "effective_contract",
                "write_mode": "create_only",
            },
            {
                "artifact_id": "profile_override",
                "root_ref": "ephemeral_root",
                "relative_path": "run/profile_override.md",
                "content_ref": "effective_contract",
                "write_mode": "patch_if_base_sha256",
            },
        ],
        "launch_delta": {
            "cwd_ref": "workspace_root",
            "env": [
                {"name": "PUPPET_DESCRIPTOR", "value_ref": "lane_binding"},
            ],
            "argv": [
                {"path_ref": "instruction_contract"},
                {"name_ref": "fixture_profile"},
                {"literal": "--format=json"},
            ],
        },
        "rollback": {
            "owned_artifacts": ["instruction_contract", "profile_override"],
            "preimage_sha256": [
                {
                    "artifact_id": "profile_override",
                    "sha256": "1" * 64,
                }
            ],
            "retain_hash_only_proof": True,
        },
        "assertions": ["assertions_coverage_001"],
        "blockers": ["blocker_coverage_001"],
    }


class InstructionPlaneDescriptorTests(unittest.TestCase):
    def test_valid_descriptor_is_stable_and_fingerprint_is_deterministic(self):
        first = validate_instruction_plane_descriptor(_fixture())
        ordered = dict(sorted(first.items()))
        self.assertEqual(first, ordered)
        self.assertEqual(descriptor_fingerprint(first), descriptor_fingerprint(_fixture()))

        reordered = {
            "blockers": ["blocker_coverage_001"],
            "assertions": ["assertions_coverage_001"],
            "schema": "puppet.instruction-plane/v1",
            "descriptor_id": "fixture-regular-coverage",
            "plane": "harness_global",
            "target": _fixture()["target"],
            "status": _fixture()["status"],
            "materialize": _fixture()["materialize"],
            "launch_delta": _fixture()["launch_delta"],
            "rollback": _fixture()["rollback"],
        }
        self.assertEqual(descriptor_fingerprint(first), descriptor_fingerprint(reordered))

    def test_parse_from_json_text(self):
        payload = json.dumps(_fixture())
        parsed = parse_instruction_plane_descriptor(payload)
        self.assertEqual(parsed["plane"], "harness_global")
        self.assertEqual(parsed["status"]["surface"], "factual")

    def test_adversarial_cases(self):
        base = _fixture()
        invalid_cases = [
            (
                "unknown_top_level_field",
                lambda value: value.update({"extra": True}),
                "descriptor fields are invalid",
            ),
            (
                "unknown_target",
                lambda value: value["target"].update({"harness": "not-a-target"}),
                "unsupported target",
            ),
            (
                "requested_model_not_default",
                lambda value: value["target"].update({"requested_model": "small"}),
                "requested_model must be default",
            ),
            (
                "unsupported_plane",
                lambda value: value.update({"plane": "unknown"}),
                "unsupported plane",
            ),
            (
                "unsupported_status_activation",
                lambda value: value["status"].update(
                    {"surface": "unsupported", "activation": "qualified"}
                ),
                "only factual descriptors can be qualified",
            ),
            (
                "hypothesis_requires_disabled",
                lambda value: value["status"].update(
                    {"surface": "hypothesis", "activation": "qualification_only"}
                ),
                "unsupported or hypothesis descriptors cannot be activatable",
            ),
            (
                "patch_mode_missing_preimage",
                lambda value: value["materialize"].append(
                    {
                        "artifact_id": "patched_missing",
                        "root_ref": "config_root",
                        "relative_path": "workspace/.puppet/config/patch.md",
                        "content_ref": "effective_contract",
                        "write_mode": "patch_if_base_sha256",
                    }
                ),
                "need rollback preimage",
            ),
            (
                "create_mode_with_preimage",
                lambda value: value["rollback"]["preimage_sha256"].append(
                    {"artifact_id": "instruction_contract", "sha256": "2" * 64}
                ),
                "cannot include preimage",
            ),
            (
                "absolute_artifact_path",
                lambda value: value["materialize"][0].update(
                    {"relative_path": "/tmp/absolute.md"}
                ),
                "relative and slash-style",
            ),
            (
                "traversal_artifact_path",
                lambda value: value["materialize"][0].update(
                    {"relative_path": "workspace/../danger.md"}
                ),
                "must not contain absolute or traversal components",
            ),
            (
                "duplicate_artifact_id",
                lambda value: value["materialize"].append(value["materialize"][0]),
                "materialize artifact ids must be unique",
            ),
            (
                "duplicate_env_name",
                lambda value: value["launch_delta"]["env"].append(
                    {"name": "PUPPET_DESCRIPTOR", "value_ref": "lane2"}
                ),
                "launch env names must be unique",
            ),
            (
                "invalid_env_name",
                lambda value: value["launch_delta"]["env"][0].update({"name": "bad-name"}),
                "launch env name",
            ),
            (
                "argv_literal_body",
                lambda value: value["launch_delta"]["argv"].append(
                    {"literal": "this is body text"}
                ),
                "argv literal must be a literal flag",
            ),
            (
                "argv_unknown_artifact",
                lambda value: value["launch_delta"]["argv"].append(
                    {"path_ref": "does_not_exist"}
                ),
                "unknown materialize artifact",
            ),
            (
                "sensitive_field_in_descriptor",
                lambda value: value.update({"session_secret": "abcd"}),
                "forbidden secret or transcript-shaped field",
            ),
            (
                "rollback_unknown_artifact",
                lambda value: value["rollback"]["owned_artifacts"].append("missing_artifact"),
                "references unknown artifact",
            ),
            (
                "preimage_not_sha256",
                lambda value: value["rollback"]["preimage_sha256"][0].update(
                    {"sha256": "not-a-hash"}
                ),
                "must be a lowercase SHA-256",
            ),
            (
                "non_list_assertions",
                lambda value: value.update({"assertions": "not-list"}),
                "assertions must be a bounded list",
            ),
        ]

        for case_id, mutate, pattern in invalid_cases:
            with self.subTest(case_id):
                candidate = copy.deepcopy(base)
                mutate(candidate)
                with self.assertRaisesRegex(ValidationError, pattern):
                    validate_instruction_plane_descriptor(candidate)


if __name__ == "__main__":
    unittest.main()
