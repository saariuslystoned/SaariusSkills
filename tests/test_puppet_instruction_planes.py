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
    AGY_CLI_VERSION,
    AGY_WORKSPACE_ARTIFACT_ID,
    AGY_WORKSPACE_BLOCKERS,
    AGY_WORKSPACE_DESCRIPTOR_ID,
    CURSOR_AGENT_VERSION,
    CURSOR_WORKSPACE_ARTIFACT_ID,
    CURSOR_WORKSPACE_BLOCKERS,
    CURSOR_WORKSPACE_DESCRIPTOR_ID,
    GROK_BUILD_VERSION,
    GROK_WORKSPACE_ARTIFACT_ID,
    GROK_WORKSPACE_DESCRIPTOR_ID,
    build_agy_workspace_agent_descriptor,
    build_cursor_workspace_addendum_descriptor,
    build_grok_workspace_addendum_descriptor,
    descriptor_fingerprint,
    parse_instruction_plane_descriptor,
    validate_agy_workspace_agent_descriptor,
    validate_cursor_workspace_addendum_descriptor,
    validate_grok_workspace_addendum_descriptor,
    validate_instruction_plane_descriptor,
)


def _fixture() -> dict:
    return {
        "schema": "puppet.instruction-plane/v1",
        "descriptor_id": "fixture-regular-coverage",
        "target": {
            "harness": "claude",
            "version": "2.1.215",
            "adapter_manifest_sha256": "0" * 64,
            "requested_model": "default",
            "observed_model": "unavailable",
            "config_fingerprint": "unavailable",
        },
        "plane": "per_run_additive",
        "status": {
            "surface": "factual",
            "activation": "qualification_only",
        },
        "materialize": [
            {
                "artifact_id": "effective_contract_file",
                "root_ref": "ephemeral_root",
                "relative_path": "puppet-instructions.md",
                "content_ref": "effective_contract",
                "write_mode": "create_only",
            },
        ],
        "launch_delta": {
            "cwd_ref": "workspace_root",
            "env": [
                {
                    "name": "CLAUDE_CONFIG_DIR",
                    "value_ref": "config_root_path",
                },
                {
                    "name": "CLAUDE_CODE_DISABLE_AUTO_MEMORY",
                    "value_ref": "true_literal",
                },
            ],
            "argv": [
                {"literal": "--append-system-prompt-file"},
                {"path_ref": "effective_contract_file"},
            ],
        },
        "rollback": {
            "owned_artifacts": ["effective_contract_file"],
            "preimage_sha256": [],
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
        self.assertEqual(
            descriptor_fingerprint(first), descriptor_fingerprint(_fixture())
        )

        reordered = {
            "blockers": ["blocker_coverage_001"],
            "assertions": ["assertions_coverage_001"],
            "schema": "puppet.instruction-plane/v1",
            "descriptor_id": "fixture-regular-coverage",
            "plane": "per_run_additive",
            "target": _fixture()["target"],
            "status": _fixture()["status"],
            "materialize": _fixture()["materialize"],
            "launch_delta": _fixture()["launch_delta"],
            "rollback": _fixture()["rollback"],
        }
        self.assertEqual(
            descriptor_fingerprint(first), descriptor_fingerprint(reordered)
        )

    def test_parse_from_json_text(self):
        payload = json.dumps(_fixture())
        parsed = parse_instruction_plane_descriptor(payload)
        self.assertEqual(parsed["plane"], "per_run_additive")
        self.assertEqual(parsed["status"]["surface"], "factual")

    def test_parse_rejects_duplicate_json_key(self):
        payload = (
            '{"schema":"puppet.instruction-plane/v1","schema":"puppet.instruction-plane/v1",'
            '"descriptor_id":"fixture-duplicate-key","target":{"harness":"codex",'
            '"version":"0.145.0","version":"0.145.0","adapter_manifest_sha256":"'
            + ("0" * 64)
            + '","requested_model":"default","observed_model":"unavailable",'
            '"config_fingerprint":"unavailable"},"plane":"harness_global",'
            '"status":{"surface":"factual","activation":"qualification_only"},'
            '"materialize":[{"artifact_id":"instruction_contract","root_ref":"config_root",'
            '"relative_path":"workspace/.puppet/contracts/instruction_contract.md",'
            '"content_ref":"effective_contract","write_mode":"create_only"}],'
            '"launch_delta":{"cwd_ref":"workspace_root","env":[],"argv":[]},'
            '"rollback":{"owned_artifacts":["instruction_contract"],"preimage_sha256":[],'
            '"retain_hash_only_proof":true},"assertions":[],"blockers":["blocker"]}'
        )
        with self.assertRaisesRegex(ValidationError, "duplicate JSON key"):
            parse_instruction_plane_descriptor(payload)

    def test_parse_rejects_oversized_text_before_json_decode(self):
        payload = '{"padding":"' + ("x" * 131072) + '"}'
        with self.assertRaisesRegex(ValidationError, "exceeds the size limit"):
            parse_instruction_plane_descriptor(payload)

    def test_parse_rejects_excessive_json_depth_before_shape_validation(self):
        payload = "[" * 2000 + "0" + "]" * 2000
        with self.assertRaisesRegex(ValidationError, "nesting exceeds"):
            parse_instruction_plane_descriptor(payload)

    def test_parse_rejects_shallow_non_object_with_shape_error(self):
        with self.assertRaisesRegex(ValidationError, "must be an object"):
            parse_instruction_plane_descriptor("[0]")

    def test_set_like_lists_do_not_change_fingerprint_when_reordered(self):
        first = _fixture()
        first["assertions"] = ["assertion_z", "assertion_a"]
        first["blockers"] = ["blocker_z", "blocker_a"]
        second = copy.deepcopy(first)
        second["assertions"].reverse()
        second["blockers"].reverse()
        self.assertEqual(descriptor_fingerprint(first), descriptor_fingerprint(second))

    def test_materialization_order_is_part_of_descriptor_identity(self):
        first = _fixture()
        first["status"] = {"surface": "factual", "activation": "disabled"}
        first["launch_delta"] = {"cwd_ref": None, "env": [], "argv": []}
        first["materialize"].append(
            {
                "artifact_id": "second_file",
                "root_ref": "ephemeral_root",
                "relative_path": "second-file.md",
                "content_ref": "effective_contract",
                "write_mode": "create_only",
            }
        )
        first["rollback"]["owned_artifacts"].append("second_file")
        second = copy.deepcopy(first)
        second["materialize"].reverse()
        self.assertNotEqual(
            descriptor_fingerprint(first), descriptor_fingerprint(second)
        )

    def test_target_version_with_revision_suffix_is_accepted(self):
        candidate = _fixture()
        candidate["target"]["harness"] = "cursor"
        candidate["target"]["version"] = "2026.07.17-3e2a980"
        candidate["plane"] = "workspace_addendum"
        candidate["status"] = {"surface": "factual", "activation": "disabled"}
        candidate["materialize"][0].update(
            {
                "root_ref": "workspace_root",
                "relative_path": ".cursor/rules/puppet.mdc",
            }
        )
        candidate["launch_delta"] = {
            "cwd_ref": "workspace_root",
            "env": [],
            "argv": [
                {"literal": "--workspace"},
                {"root_ref": "workspace_root"},
            ],
        }
        self.assertEqual(
            validate_instruction_plane_descriptor(candidate)["target"]["version"],
            "2026.07.17-3e2a980",
        )

    def test_unsupported_or_hypothesis_disabled_can_be_empty_and_is_blocker_required(
        self,
    ):
        candidate = _fixture()
        candidate["status"] = {"surface": "hypothesis", "activation": "disabled"}
        candidate["materialize"] = []
        candidate["launch_delta"] = {"cwd_ref": None, "env": [], "argv": []}
        candidate["rollback"] = {
            "owned_artifacts": [],
            "preimage_sha256": [],
            "retain_hash_only_proof": True,
        }
        candidate["assertions"] = []
        candidate["blockers"] = ["blocker_coverage_001"]
        self.assertEqual(
            validate_instruction_plane_descriptor(candidate)["materialize"], []
        )

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
                "status activation is unsupported",
            ),
            (
                "hypothesis_requires_disabled",
                lambda value: value["status"].update(
                    {"surface": "hypothesis", "activation": "qualification_only"}
                ),
                "unsupported or hypothesis descriptors cannot be activatable",
            ),
            (
                "unsupported_requires_blockers_when_disabled",
                lambda value: value.update(
                    {
                        "status": {"surface": "unsupported", "activation": "disabled"},
                        "materialize": [],
                        "launch_delta": {"cwd_ref": None, "env": [], "argv": []},
                        "rollback": {
                            "owned_artifacts": [],
                            "preimage_sha256": [],
                            "retain_hash_only_proof": True,
                        },
                        "blockers": [],
                    }
                ),
                "unsupported or hypothesis disabled descriptors require blockers",
            ),
            (
                "unsupported_disabled_cannot_include_activation_delta",
                lambda value: value.update(
                    {
                        "status": {"surface": "unsupported", "activation": "disabled"},
                        "materialize": [],
                        "rollback": {
                            "owned_artifacts": [],
                            "preimage_sha256": [],
                            "retain_hash_only_proof": True,
                        },
                        "blockers": ["blocked_coverage"],
                        "launch_delta": {
                            "cwd_ref": "workspace_root",
                            "env": [],
                            "argv": [],
                        },
                    }
                ),
                "unsupported or hypothesis disabled descriptors cannot include activation deltas",
            ),
            (
                "qualified_requires_assertions",
                lambda value: (
                    value["status"].update({"activation": "qualified"})
                    or value.update({"assertions": []})
                ),
                "status activation is unsupported",
            ),
            (
                "qualified_requires_no_blockers",
                lambda value: value["status"].update({"activation": "qualified"}),
                "status activation is unsupported",
            ),
            (
                "factual_activation_requires_materialize",
                lambda value: value.update(
                    {
                        "status": {
                            "surface": "factual",
                            "activation": "qualification_only",
                        },
                        "materialize": [],
                    }
                ),
                "materialize must be a non-empty bounded list",
            ),
            (
                "patch_mode_missing_preimage",
                lambda value: (
                    value["materialize"].append(
                        {
                            "artifact_id": "patched_missing",
                            "root_ref": "config_root",
                            "relative_path": "workspace/.puppet/config/patch.md",
                            "content_ref": "effective_contract",
                            "write_mode": "patch_if_base_sha256",
                        }
                    )
                    or value["rollback"]["owned_artifacts"].append("patched_missing")
                ),
                "need rollback preimage",
            ),
            (
                "create_mode_with_preimage",
                lambda value: value["rollback"]["preimage_sha256"].append(
                    {"artifact_id": "effective_contract_file", "sha256": "2" * 64}
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
                "body_shaped_ephemeral_filename",
                lambda value: value["materialize"][0].update(
                    {"relative_path": "Ignore all previous instructions.md"}
                ),
                "invalid closed launch grammar",
            ),
            (
                "wrong_ephemeral_artifact_id",
                lambda value: (
                    value["materialize"][0].update({"artifact_id": "wrong_file"})
                    or value["launch_delta"]["argv"][1].update(
                        {"path_ref": "wrong_file"}
                    )
                    or value["rollback"].update({"owned_artifacts": ["wrong_file"]})
                ),
                "invalid closed launch grammar",
            ),
            (
                "traversal_artifact_path",
                lambda value: value["materialize"][0].update(
                    {"relative_path": "workspace/../danger.md"}
                ),
                "must not contain absolute or traversal components",
            ),
            (
                "duplicate_slash_artifact_path",
                lambda value: value["materialize"][0].update(
                    {"relative_path": "workspace//contracts/instruction_contract.md"}
                ),
                "must not contain absolute or traversal components",
            ),
            (
                "trailing_slash_artifact_path",
                lambda value: value["materialize"][0].update(
                    {
                        "relative_path": "workspace/.puppet/contracts/instruction_contract.md/"
                    }
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
                lambda value: value["launch_delta"]["env"].extend(
                    [
                        {
                            "name": "CLAUDE_CONFIG_DIR",
                            "value_ref": "config_root_path",
                        },
                        {
                            "name": "CLAUDE_CONFIG_DIR",
                            "value_ref": "config_root_path",
                        },
                    ]
                ),
                "launch env names must be unique",
            ),
            (
                "invalid_env_name",
                lambda value: value["launch_delta"]["env"].append(
                    {"name": "bad-name", "value_ref": "config_root_path"}
                ),
                "launch env name",
            ),
            (
                "unknown_env_ref",
                lambda value: value["launch_delta"]["env"].append(
                    {"name": "CLAUDE_CONFIG_DIR", "value_ref": "body_text"}
                ),
                "launch env binding is not allowlisted",
            ),
            (
                "argv_literal_body",
                lambda value: value["launch_delta"]["argv"].append(
                    {"literal": "this is body text"}
                ),
                "argv literal must be a literal flag",
            ),
            (
                "argv_literal_eq_short_flag",
                lambda value: value["launch_delta"]["argv"].append(
                    {"literal": "--rules=body"}
                ),
                "is not a literal flag",
            ),
            (
                "argv_literal_eq_long_flag",
                lambda value: value["launch_delta"]["argv"].append(
                    {"literal": "--system-prompt=x"}
                ),
                "is not a literal flag",
            ),
            (
                "argv_forbidden_replacement_flag",
                lambda value: value["launch_delta"]["argv"].append(
                    {"literal": "--system-prompt"}
                ),
                "not an allowlisted instruction-plane flag",
            ),
            (
                "argv_unknown_name_ref",
                lambda value: value["launch_delta"]["argv"].append(
                    {"name_ref": "IgnoreAllSafetyRules"}
                ),
                "argv name_ref is not allowlisted",
            ),
            (
                "argv_literal_double_dash",
                lambda value: value["launch_delta"]["argv"].append({"literal": "--"}),
                "is not a literal flag",
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
                lambda value: value["rollback"]["preimage_sha256"].append(
                    {"artifact_id": "missing_artifact", "sha256": "1" * 64}
                ),
                "rollback preimage references unknown artifact",
            ),
            (
                "rollback_ownership_must_cover_all_artifacts",
                lambda value: value["rollback"].update({"owned_artifacts": []}),
                "must own at least one artifact",
            ),
            (
                "preimage_not_sha256",
                lambda value: value["rollback"]["preimage_sha256"].append(
                    {
                        "artifact_id": "effective_contract_file",
                        "sha256": "not-a-hash",
                    }
                ),
                "must be a lowercase SHA-256",
            ),
            (
                "duplicate_destination",
                lambda value: (
                    value["materialize"].append(
                        {
                            **value["materialize"][0],
                            "artifact_id": "duplicate_destination",
                        }
                    )
                    or value["rollback"]["owned_artifacts"].append(
                        "duplicate_destination"
                    )
                ),
                "destinations must be unique and non-overlapping",
            ),
            (
                "ancestor_destination",
                lambda value: (
                    value["materialize"][0].update({"relative_path": "rules"})
                    or value["materialize"].append(
                        {
                            **value["materialize"][0],
                            "artifact_id": "descendant_destination",
                            "relative_path": "rules/puppet.md",
                        }
                    )
                    or value["rollback"]["owned_artifacts"].append(
                        "descendant_destination"
                    )
                ),
                "destinations must be unique and non-overlapping",
            ),
            (
                "malformed_target_version",
                lambda value: value["target"].update({"version": "2..1"}),
                "not a valid version",
            ),
            (
                "surrogate_text",
                lambda value: value["target"].update({"observed_model": "\ud800"}),
                "printable Unicode",
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


class AgyWorkspaceDescriptorTests(unittest.TestCase):
    def setUp(self):
        self.adapter_hash = "a" * 64
        self.rendered_hash = "b" * 64
        self.descriptor = build_agy_workspace_agent_descriptor(
            adapter_manifest_sha256=self.adapter_hash,
            rendered_sha256=self.rendered_hash,
        )

    def test_exact_descriptor_is_hash_named_create_only_and_activation_disabled(self):
        expected_path = ".agents/agents/puppet-%s/agent.md" % self.rendered_hash
        artifact = self.descriptor["materialize"][0]
        self.assertEqual(self.descriptor["descriptor_id"], AGY_WORKSPACE_DESCRIPTOR_ID)
        self.assertEqual(self.descriptor["target"]["version"], AGY_CLI_VERSION)
        self.assertEqual(self.descriptor["target"]["requested_model"], "default")
        self.assertEqual(self.descriptor["target"]["observed_model"], "unavailable")
        self.assertEqual(self.descriptor["target"]["config_fingerprint"], "unavailable")
        self.assertEqual(self.descriptor["plane"], "workspace_addendum")
        self.assertEqual(
            self.descriptor["status"],
            {"surface": "factual", "activation": "disabled"},
        )
        self.assertEqual(artifact["artifact_id"], AGY_WORKSPACE_ARTIFACT_ID)
        self.assertEqual(artifact["root_ref"], "workspace_root")
        self.assertEqual(artifact["relative_path"], expected_path)
        self.assertEqual(artifact["write_mode"], "create_only")
        self.assertEqual(
            self.descriptor["launch_delta"],
            {
                "cwd_ref": "workspace_root",
                "env": [],
                "argv": [
                    {"literal": "--agent"},
                    {"name_ref": "puppet_agent_name"},
                ],
            },
        )
        self.assertEqual(
            self.descriptor["rollback"]["owned_artifacts"],
            [AGY_WORKSPACE_ARTIFACT_ID],
        )
        self.assertEqual(self.descriptor["blockers"], sorted(AGY_WORKSPACE_BLOCKERS))
        self.assertEqual(
            validate_agy_workspace_agent_descriptor(self.descriptor),
            self.descriptor,
        )
        self.assertEqual(
            descriptor_fingerprint(self.descriptor),
            descriptor_fingerprint(
                build_agy_workspace_agent_descriptor(
                    adapter_manifest_sha256=self.adapter_hash,
                    rendered_sha256=self.rendered_hash,
                )
            ),
        )

    def test_exact_descriptor_rejects_global_paths_activation_and_shape_drift(self):
        cases = (
            (
                "version",
                lambda value: value["target"].update({"version": "1.1.4"}),
            ),
            (
                "target",
                lambda value: value["target"].update({"harness": "claude"}),
            ),
            ("plane", lambda value: value.update({"plane": "harness_global"})),
            (
                "activation",
                lambda value: value["status"].update(
                    {"activation": "qualification_only"}
                ),
            ),
            (
                "global-root",
                lambda value: value["materialize"][0].update(
                    {"root_ref": "config_root"}
                ),
            ),
            (
                "global-filename",
                lambda value: value["materialize"][0].update(
                    {"relative_path": ".gemini/config/agents/puppet/agent.md"}
                ),
            ),
            (
                "unnamespaced-filename",
                lambda value: value["materialize"][0].update(
                    {"relative_path": ".agents/agents/puppet/agent.md"}
                ),
            ),
            (
                "write-mode",
                lambda value: value["materialize"][0].update(
                    {"write_mode": "patch_if_base_sha256"}
                ),
            ),
            (
                "env",
                lambda value: value["launch_delta"].update(
                    {"env": [{"name": "CODEX_HOME", "value_ref": "config_root_path"}]}
                ),
            ),
            (
                "argv",
                lambda value: value["launch_delta"].update({"argv": []}),
            ),
            (
                "blockers",
                lambda value: value.update({"blockers": ["caller_green"]}),
            ),
        )
        for case_id, mutate in cases:
            with self.subTest(case_id=case_id):
                candidate = copy.deepcopy(self.descriptor)
                mutate(candidate)
                with self.assertRaises(ValidationError):
                    validate_agy_workspace_agent_descriptor(candidate)

    def test_descriptor_builder_rejects_non_sha_inputs(self):
        for name, values in (
            (
                "manifest",
                {
                    "adapter_manifest_sha256": "not-a-hash",
                    "rendered_sha256": self.rendered_hash,
                },
            ),
            (
                "rendered",
                {
                    "adapter_manifest_sha256": self.adapter_hash,
                    "rendered_sha256": "A" * 64,
                },
            ),
        ):
            with self.subTest(name=name), self.assertRaises(ValidationError):
                build_agy_workspace_agent_descriptor(**values)

    def test_reserved_agy_id_is_exact_through_generic_mapping_and_json_parsers(self):
        cases = (
            (
                "config-root",
                lambda value: value["materialize"][0].update(
                    {"root_ref": "config_root"}
                ),
            ),
            (
                "selector",
                lambda value: value["launch_delta"]["argv"].__setitem__(
                    1, {"name_ref": "puppet_profile_name"}
                ),
            ),
            (
                "path",
                lambda value: value["materialize"][0].update(
                    {"relative_path": ".agents/agents/puppet/agent.md"}
                ),
            ),
            (
                "activation",
                lambda value: value["status"].update(
                    {"activation": "qualification_only"}
                ),
            ),
            ("blockers", lambda value: value.update({"blockers": []})),
        )
        for case_id, mutate in cases:
            candidate = copy.deepcopy(self.descriptor)
            mutate(candidate)
            with self.subTest(case_id=case_id, parser="mapping"):
                with self.assertRaises(ValidationError):
                    validate_instruction_plane_descriptor(candidate)
            with self.subTest(case_id=case_id, parser="json"):
                with self.assertRaises(ValidationError):
                    parse_instruction_plane_descriptor(json.dumps(candidate))


class CursorWorkspaceDescriptorTests(unittest.TestCase):
    def setUp(self):
        self.adapter_hash = "a" * 64
        self.rendered_hash = "b" * 64
        self.descriptor = build_cursor_workspace_addendum_descriptor(
            adapter_manifest_sha256=self.adapter_hash,
            rendered_sha256=self.rendered_hash,
        )

    def test_exact_descriptor_is_hash_named_create_only_and_disabled(self):
        artifact = self.descriptor["materialize"][0]
        self.assertEqual(
            self.descriptor["descriptor_id"], CURSOR_WORKSPACE_DESCRIPTOR_ID
        )
        self.assertEqual(self.descriptor["target"]["version"], CURSOR_AGENT_VERSION)
        self.assertEqual(self.descriptor["target"]["requested_model"], "default")
        self.assertEqual(self.descriptor["target"]["observed_model"], "unavailable")
        self.assertEqual(self.descriptor["target"]["config_fingerprint"], "unavailable")
        self.assertEqual(
            self.descriptor["status"],
            {"surface": "factual", "activation": "disabled"},
        )
        self.assertEqual(artifact["artifact_id"], CURSOR_WORKSPACE_ARTIFACT_ID)
        self.assertEqual(artifact["root_ref"], "workspace_root")
        self.assertEqual(
            artifact["relative_path"],
            ".cursor/rules/puppet-%s.mdc" % self.rendered_hash,
        )
        self.assertEqual(artifact["write_mode"], "create_only")
        self.assertEqual(
            self.descriptor["launch_delta"],
            {
                "cwd_ref": "workspace_root",
                "env": [],
                "argv": [
                    {"literal": "--workspace"},
                    {"root_ref": "workspace_root"},
                ],
            },
        )
        self.assertEqual(self.descriptor["blockers"], sorted(CURSOR_WORKSPACE_BLOCKERS))
        self.assertEqual(
            validate_cursor_workspace_addendum_descriptor(self.descriptor),
            self.descriptor,
        )

    def test_reserved_cursor_id_rejects_shape_drift_through_both_parsers(self):
        cases = (
            ("version", lambda value: value["target"].update({"version": "3.12.17"})),
            (
                "activation",
                lambda value: value["status"].update(
                    {"activation": "qualification_only"}
                ),
            ),
            (
                "path",
                lambda value: value["materialize"][0].update(
                    {"relative_path": ".cursor/rules/puppet.mdc"}
                ),
            ),
            ("selector", lambda value: value["launch_delta"].update({"argv": []})),
            ("blockers", lambda value: value.update({"blockers": ["caller_green"]})),
        )
        for case_id, mutate in cases:
            candidate = copy.deepcopy(self.descriptor)
            mutate(candidate)
            with self.subTest(case_id=case_id, parser="mapping"):
                with self.assertRaises(ValidationError):
                    validate_instruction_plane_descriptor(candidate)
            with self.subTest(case_id=case_id, parser="json"):
                with self.assertRaises(ValidationError):
                    parse_instruction_plane_descriptor(json.dumps(candidate))

    def test_builder_rejects_non_hash_inputs(self):
        with self.assertRaises(ValidationError):
            build_cursor_workspace_addendum_descriptor(
                adapter_manifest_sha256="not-a-hash",
                rendered_sha256=self.rendered_hash,
            )
        with self.assertRaises(ValidationError):
            build_cursor_workspace_addendum_descriptor(
                adapter_manifest_sha256=self.adapter_hash,
                rendered_sha256="A" * 64,
            )


class GrokWorkspaceDescriptorTests(unittest.TestCase):
    def setUp(self):
        self.adapter_hash = "a" * 64
        self.rendered_hash = "b" * 64
        self.descriptor = build_grok_workspace_addendum_descriptor(
            adapter_manifest_sha256=self.adapter_hash,
            rendered_sha256=self.rendered_hash,
        )

    def test_exact_descriptor_is_hash_named_create_only_and_deterministic(self):
        expected_path = ".grok/rules/puppet-%s.md" % self.rendered_hash
        artifact = self.descriptor["materialize"][0]
        self.assertEqual(self.descriptor["descriptor_id"], GROK_WORKSPACE_DESCRIPTOR_ID)
        self.assertEqual(self.descriptor["target"]["version"], GROK_BUILD_VERSION)
        self.assertEqual(
            self.descriptor["descriptor_id"],
            "grok-build-0.2.111-workspace-addendum",
        )
        self.assertEqual(self.descriptor["target"]["version"], "0.2.111")
        self.assertEqual(self.descriptor["target"]["requested_model"], "default")
        self.assertEqual(self.descriptor["target"]["observed_model"], "unavailable")
        self.assertEqual(
            self.descriptor["target"]["config_fingerprint"],
            "unavailable",
        )
        self.assertEqual(self.descriptor["plane"], "workspace_addendum")
        self.assertEqual(artifact["artifact_id"], GROK_WORKSPACE_ARTIFACT_ID)
        self.assertEqual(artifact["root_ref"], "workspace_root")
        self.assertEqual(artifact["relative_path"], expected_path)
        self.assertEqual(artifact["write_mode"], "create_only")
        self.assertEqual(
            self.descriptor["launch_delta"],
            {
                "cwd_ref": "workspace_root",
                "env": [
                    {
                        "name": "GROK_DISABLE_AUTOUPDATER",
                        "value_ref": "true_literal",
                    },
                    {"name": "GROK_HOME", "value_ref": "config_root_path"},
                ],
                "argv": [],
            },
        )
        self.assertEqual(
            validate_grok_workspace_addendum_descriptor(self.descriptor),
            self.descriptor,
        )
        self.assertEqual(
            descriptor_fingerprint(self.descriptor),
            descriptor_fingerprint(
                build_grok_workspace_addendum_descriptor(
                    adapter_manifest_sha256=self.adapter_hash,
                    rendered_sha256=self.rendered_hash,
                )
            ),
        )

    def test_exact_descriptor_rejects_cross_tuple_and_activation_drift(self):
        cases = (
            (
                "version",
                lambda value: value["target"].update({"version": "0.2.105"}),
            ),
            (
                "target",
                lambda value: value["target"].update({"harness": "claude"}),
            ),
            ("plane", lambda value: value.update({"plane": "harness_global"})),
            (
                "root",
                lambda value: value["materialize"][0].update(
                    {"root_ref": "config_root"}
                ),
            ),
            (
                "filename",
                lambda value: value["materialize"][0].update(
                    {"relative_path": ".grok/rules/puppet.md"}
                ),
            ),
            (
                "write-mode",
                lambda value: value["materialize"][0].update(
                    {"write_mode": "patch_if_base_sha256"}
                ),
            ),
            (
                "env",
                lambda value: value["launch_delta"].update({"env": []}),
            ),
            (
                "argv",
                lambda value: value["launch_delta"].update(
                    {"argv": [{"literal": "--cwd"}]}
                ),
            ),
            (
                "model",
                lambda value: value["target"].update({"observed_model": "grok-4.5"}),
            ),
            (
                "config",
                lambda value: value["target"].update({"config_fingerprint": "c" * 64}),
            ),
        )
        for case_id, mutate in cases:
            with self.subTest(case_id=case_id):
                candidate = copy.deepcopy(self.descriptor)
                mutate(candidate)
                with self.assertRaises(ValidationError):
                    validate_grok_workspace_addendum_descriptor(candidate)

    def test_descriptor_builder_rejects_non_sha_inputs(self):
        for name, values in (
            (
                "manifest",
                {
                    "adapter_manifest_sha256": "not-a-hash",
                    "rendered_sha256": self.rendered_hash,
                },
            ),
            (
                "rendered",
                {
                    "adapter_manifest_sha256": self.adapter_hash,
                    "rendered_sha256": "A" * 64,
                },
            ),
        ):
            with self.subTest(name=name), self.assertRaises(ValidationError):
                build_grok_workspace_addendum_descriptor(**values)


if __name__ == "__main__":
    unittest.main()
