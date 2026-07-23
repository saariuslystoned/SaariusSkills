from __future__ import annotations

import copy
import inspect
import json
import re
import sys
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "puppet" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from puppet_lib.errors import IdentityError, ValidationError  # noqa: E402
from puppet_lib.contracts import MANDATORY_HARD_GATES  # noqa: E402
from puppet_lib.instructions import compile_instruction_wrapper  # noqa: E402
from puppet_lib.matched_control import (  # noqa: E402
    COMPILED_MARKER_BINDING_SCHEMA,
    COMPILED_MARKER_RESULT,
    COMPILED_MARKER_SCOPE,
    CompiledMarkerInstruction,
    compile_claude_marker_instruction,
    validate_compiled_marker_binding,
)
from puppet_lib.safety import canonical_json_bytes, sha256_bytes  # noqa: E402


MARKER_PATTERN = re.compile(rb"PUPPET_CLAUDE_MATCHED_CONTROL_MARKER_V1=[0-9a-f]{64}")


def descriptor() -> dict:
    return {
        "schema": "puppet.instruction-plane/v1",
        "descriptor_id": "claude-marker-binding",
        "target": {
            "harness": "claude",
            "version": "2.1.215",
            "adapter_manifest_sha256": "a" * 64,
            "requested_model": "default",
            "observed_model": "unavailable",
            "config_fingerprint": "unavailable",
        },
        "plane": "per_run_additive",
        "status": {"surface": "factual", "activation": "qualification_only"},
        "materialize": [
            {
                "artifact_id": "effective_contract_file",
                "root_ref": "ephemeral_root",
                "relative_path": "puppet-instructions.md",
                "content_ref": "effective_contract",
                "write_mode": "create_only",
            }
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
        "assertions": ["matched_control_compile_binding"],
        "blockers": ["matched_control_runtime_not_built"],
    }


def compile_binding(**overrides):
    values = {
        "descriptor": descriptor(),
        "task": "TASK_BODY_CANARY: write the bounded conformance handoff.",
        "contract_identity": {
            "fingerprint": "b" * 64,
            "controller": "codex",
            "target": "claude",
            "task_profile": "source-free-pass-b-v2",
        },
        "workspace_identity": {
            "fixture_fingerprint": "c" * 64,
            "workspace": "isolated_conformance_fixture",
        },
        "run_identity": {
            "session": "claude-activated",
            "run_id": "run-activated",
            "nonce": "nonce-activated-0123456789",
        },
    }
    values.update(overrides)
    return compile_claude_marker_instruction(**values)


class CompiledMarkerBindingTests(unittest.TestCase):
    def test_source_owned_marker_is_exactly_once_and_binding_is_body_free(self):
        result = compile_binding()
        matches = MARKER_PATTERN.findall(result.rendered)
        self.assertEqual(len(matches), 1)
        binding = result.binding
        self.assertEqual(binding["schema"], COMPILED_MARKER_BINDING_SCHEMA)
        self.assertEqual(binding["scope"], COMPILED_MARKER_SCOPE)
        self.assertEqual(binding["result"], COMPILED_MARKER_RESULT)
        self.assertEqual(binding["marker_sha256"], sha256_bytes(matches[0]))
        self.assertEqual(
            binding["instruction_manifest_sha256"],
            sha256_bytes(canonical_json_bytes(result.manifest) + b"\n"),
        )
        for name in (
            "runtime_scan_authorized",
            "promotion_authorized",
            "qualification_authorized",
            "delivered",
            "checkpoint_observed",
            "lease_bound",
            "no_bleed_evaluated",
            "no_bleed_verified",
        ):
            self.assertIs(binding[name], False)

        durable = json.dumps(binding, sort_keys=True)
        self.assertNotIn("TASK_BODY_CANARY", durable)
        self.assertNotIn(matches[0].decode("ascii"), durable)
        self.assertNotIn("PUPPET_CLAUDE_MATCHED_CONTROL_MARKER", durable)
        self.assertNotIn("TASK_BODY_CANARY", repr(result))
        self.assertNotIn("PUPPET_CLAUDE_MATCHED_CONTROL_MARKER", repr(result))

    def test_public_api_has_no_marker_digest_hook_or_runtime_authority_input(self):
        parameters = inspect.signature(compile_claude_marker_instruction).parameters
        for forbidden in (
            "marker",
            "marker_sha256",
            "compiled",
            "journal",
            "event",
            "rows",
            "process",
            "lease",
            "checkpoint",
            "hook",
            "runtime_contract_layer",
        ):
            self.assertNotIn(forbidden, parameters)

    def test_nonce_and_descriptor_are_bound_and_cross_run_replay_changes_marker(self):
        first = compile_binding()
        second = compile_binding(
            run_identity={
                "session": "claude-control",
                "run_id": "run-control",
                "nonce": "nonce-control-9876543210",
            }
        )
        self.assertNotEqual(
            first.binding["marker_sha256"], second.binding["marker_sha256"]
        )
        self.assertNotEqual(
            first.binding["run_identity_sha256"],
            second.binding["run_identity_sha256"],
        )

        changed_descriptor = descriptor()
        changed_descriptor["descriptor_id"] = "claude-marker-binding-two"
        third = compile_binding(descriptor=changed_descriptor)
        self.assertNotEqual(
            first.binding["descriptor_sha256"], third.binding["descriptor_sha256"]
        )
        self.assertNotEqual(
            first.binding["marker_sha256"], third.binding["marker_sha256"]
        )

    def test_exact_run_shape_and_exact_claude_plane_are_required(self):
        with self.assertRaisesRegex(ValidationError, "run identity fields"):
            compile_binding(
                run_identity={
                    "session": "claude-activated",
                    "run_id": "run-activated",
                    "nonce": "nonce-activated-0123456789",
                    "marker": "caller-minted",
                }
            )

        wrong = descriptor()
        wrong["status"] = {"surface": "factual", "activation": "disabled"}
        with self.assertRaisesRegex(ValidationError, "exact unobserved-default"):
            compile_binding(descriptor=wrong)

        observed = descriptor()
        observed["target"]["observed_model"] = "caller-authored body channel"
        with self.assertRaisesRegex(ValidationError, "exact unobserved-default"):
            compile_binding(descriptor=observed)

        future = descriptor()
        future["target"]["version"] = "9.9.9"
        with self.assertRaisesRegex(ValidationError, "exact unobserved-default"):
            compile_binding(descriptor=future)

    def test_contract_and_workspace_body_channels_are_rejected(self):
        with self.assertRaisesRegex(ValidationError, "contract identity fields"):
            compile_binding(
                contract_identity={
                    "fingerprint": "b" * 64,
                    "controller": "codex",
                    "target": "claude",
                    "task_profile": "source-free-pass-b-v2",
                    "checkpoint": "CALLER_CHECKPOINT_CLAIM",
                }
            )
        with self.assertRaisesRegex(ValidationError, "workspace identity fields"):
            compile_binding(
                workspace_identity={
                    "fixture_fingerprint": "c" * 64,
                    "workspace": "isolated_conformance_fixture",
                    "path": "/caller/body/channel",
                }
            )

    def test_short_task_cannot_false_positive_against_binding_keys(self):
        result = compile_binding(task="x")
        self.assertEqual(result.binding["result"], COMPILED_MARKER_RESULT)

    def test_preexisting_or_missing_marker_fails_closed(self):
        initial = compile_binding()
        token = MARKER_PATTERN.search(initial.rendered)
        self.assertIsNotNone(token)
        with self.assertRaisesRegex(IdentityError, "exactly once"):
            compile_binding(
                task="caller tried to preinsert " + token.group(0).decode("ascii")
            )

        ordinary = compile_instruction_wrapper(
            target="claude",
            task="ordinary task without an activated marker",
            contract_identity={
                "fingerprint": "b" * 64,
                "controller": "codex",
                "target": "claude",
                "task_profile": "source-free-pass-b-v2",
            },
            workspace_identity={
                "fixture_fingerprint": "c" * 64,
                "workspace": "isolated_conformance_fixture",
            },
            run_identity={
                "session": "claude-activated",
                "run_id": "run-activated",
                "nonce": "nonce-activated-0123456789",
            },
            model_binding="default",
            effort_binding="default",
            runtime_contract_layer={
                "mutation_owner": "none",
                "allowed_modes": ["read", "test"],
                "hard_gates": sorted(MANDATORY_HARD_GATES),
            },
        )
        with mock.patch(
            "puppet_lib.matched_control.compile_instruction_wrapper",
            return_value=ordinary,
        ):
            with self.assertRaisesRegex(IdentityError, "exactly once"):
                compile_binding()

    def test_returned_manifest_and_binding_are_detached_copies(self):
        result = compile_binding()
        binding = result.binding
        manifest = result.manifest
        binding["result"] = "caller_green"
        manifest["target"] = "grok"
        self.assertEqual(result.binding["result"], COMPILED_MARKER_RESULT)
        self.assertEqual(result.manifest["target"], "claude")

    def test_saved_binding_is_rejoined_to_exact_in_memory_marker_bytes(self):
        result = compile_binding()
        self.assertEqual(validate_compiled_marker_binding(result), result.binding)

        forged_binding = result.binding
        forged_binding["marker_sha256"] = "f" * 64
        forged = CompiledMarkerInstruction(
            _rendered=result.rendered,
            _manifest_json=canonical_json_bytes(result.manifest),
            _binding_json=canonical_json_bytes(forged_binding),
        )
        with self.assertRaisesRegex(IdentityError, "binding identity"):
            validate_compiled_marker_binding(forged)

        arbitrary_marker = b"PUPPET_CLAUDE_MATCHED_CONTROL_MARKER_V1=" + b"f" * 64
        arbitrary = compile_instruction_wrapper(
            target="claude",
            task="caller-authored marker " + arbitrary_marker.decode("ascii"),
            contract_identity={
                "fingerprint": "b" * 64,
                "controller": "codex",
                "target": "claude",
                "task_profile": "source-free-pass-b-v2",
            },
            workspace_identity={
                "fixture_fingerprint": "c" * 64,
                "workspace": "isolated_conformance_fixture",
            },
            run_identity={
                "session": "claude-activated",
                "run_id": "run-activated",
                "nonce": "nonce-activated-0123456789",
            },
            model_binding="default",
            effort_binding="default",
            runtime_contract_layer={
                "mutation_owner": "none",
                "allowed_modes": ["read", "test"],
                "hard_gates": sorted(MANDATORY_HARD_GATES),
            },
        )
        forged_binding = result.binding
        forged_binding.update(
            instruction_manifest_sha256=sha256_bytes(
                canonical_json_bytes(arbitrary.manifest) + b"\n"
            ),
            rendered_sha256=arbitrary.manifest["rendered_sha256"],
            marker_sha256=sha256_bytes(arbitrary_marker),
            instruction_policy_fingerprint=arbitrary.manifest[
                "instruction_policy_fingerprint"
            ],
            effective_contract_fingerprint=arbitrary.manifest[
                "effective_contract_fingerprint"
            ],
        )
        forged = CompiledMarkerInstruction(
            _rendered=arbitrary.rendered,
            _manifest_json=canonical_json_bytes(arbitrary.manifest),
            _binding_json=canonical_json_bytes(forged_binding),
        )
        with self.assertRaisesRegex(IdentityError, "exactly once"):
            validate_compiled_marker_binding(forged)

    def test_binding_changes_with_contract_workspace_and_task(self):
        first = compile_binding()
        changed_contract = compile_binding(
            contract_identity={
                "fingerprint": "d" * 64,
                "controller": "codex",
                "target": "claude",
                "task_profile": "source-free-pass-b-v2",
            }
        )
        changed_workspace = compile_binding(
            workspace_identity={
                "fixture_fingerprint": "e" * 64,
                "workspace": "isolated_conformance_fixture",
            }
        )
        changed_task = compile_binding(task="different task body")
        self.assertNotEqual(
            first.binding["contract_identity_sha256"],
            changed_contract.binding["contract_identity_sha256"],
        )
        self.assertNotEqual(
            first.binding["workspace_identity_sha256"],
            changed_workspace.binding["workspace_identity_sha256"],
        )
        self.assertNotEqual(
            first.binding["rendered_sha256"], changed_task.binding["rendered_sha256"]
        )
        self.assertNotEqual(
            first.binding["instruction_manifest_sha256"],
            changed_task.binding["instruction_manifest_sha256"],
        )

    def test_input_mappings_are_not_retained_or_mutated(self):
        plane = descriptor()
        contract = {
            "fingerprint": "b" * 64,
            "controller": "codex",
            "target": "claude",
            "task_profile": "source-free-pass-b-v2",
        }
        workspace = {
            "fixture_fingerprint": "c" * 64,
            "workspace": "isolated_conformance_fixture",
        }
        run = {
            "session": "claude-activated",
            "run_id": "run-activated",
            "nonce": "nonce-activated-0123456789",
        }
        originals = copy.deepcopy((plane, contract, workspace, run))
        compile_binding(
            descriptor=plane,
            contract_identity=contract,
            workspace_identity=workspace,
            run_identity=run,
        )
        self.assertEqual((plane, contract, workspace, run), originals)


if __name__ == "__main__":
    unittest.main()
