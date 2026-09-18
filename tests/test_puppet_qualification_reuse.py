from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from unittest import TestCase

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "puppet" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from puppet_lib.qualification_scope import (  # noqa: E402
    QUALIFICATION_SCOPE_SCHEMA,
    build_compatibility_scope,
    scope_source_paths,
)
from puppet_lib.errors import UnsupportedError, ValidationError  # noqa: E402
from puppet_lib.diagnostics import identity_blocker  # noqa: E402
from puppet_lib.instructions import compile_instruction_wrapper  # noqa: E402

sys.path.insert(0, str(SCRIPTS))
from adapter_lab import _scope_invalidations, build_parser  # noqa: E402


class QualificationReuseTests(TestCase):
    def test_target_scope_excludes_unrelated_harness_sources(self):
        agy_sources = set(scope_source_paths("agy"))
        cursor_sources = set(scope_source_paths("cursor"))

        self.assertIn("scripts/puppet_lib/agy_launch.py", agy_sources)
        self.assertNotIn("scripts/puppet_lib/cursor_qualification.py", agy_sources)
        self.assertIn("scripts/puppet_lib/cursor_qualification.py", cursor_sources)
        self.assertNotEqual(agy_sources, cursor_sources)

    def test_scope_binds_model_effort_semantics_and_manifest_identity(self):
        manifest = {
            "target": "agy",
            "executable": {"sha256": "e" * 64, "version_sha256": "d" * 64},
            "execution": {"execution_fingerprint": "b" * 64},
            "platform": {"system": "Darwin", "release": "1", "machine": "arm64"},
            "protocol_fingerprint": "c" * 64,
            "adapter_fingerprint": "a" * 64,
            "yolo_mapping": {
                "model_flag": "--model",
                "effort_flag": "--effort",
                "launch_argv": ["/usr/bin/agy", "--dangerously-skip-permissions"],
            },
        }
        scope = build_compatibility_scope(
            manifest,
            requested_model="gemini-3.8",
            requested_effort="high",
            instruction_policy_fingerprint="a" * 64,
            source_root=SCRIPTS.parent,
        )

        self.assertEqual(scope["schema"], QUALIFICATION_SCOPE_SCHEMA)
        self.assertEqual(scope["target"], "agy")
        self.assertEqual(scope["model_effort"], {
            "requested_model": "gemini-3.8",
            "requested_effort": "high",
            "model_flag": "--model",
            "effort_flag": "--effort",
        })
        self.assertEqual(len(scope["fingerprint"]), 64)

    def test_legacy_scope_cannot_be_promoted(self):
        with self.assertRaisesRegex(UnsupportedError, "legacy"):
            build_compatibility_scope(
                {"target": "agy"},
                requested_model=None,
                requested_effort=None,
                instruction_policy_fingerprint="a" * 64,
                source_root=SCRIPTS.parent,
                legacy=True,
            )

    def test_tampered_scope_is_rejected(self):
        manifest = {
            "target": "agy",
            "executable": {"sha256": "e" * 64, "version_sha256": "d" * 64},
            "execution": {"execution_fingerprint": "b" * 64},
            "platform": {"system": "Darwin", "release": "1", "machine": "arm64"},
            "protocol_fingerprint": "c" * 64,
            "adapter_fingerprint": "a" * 64,
            "yolo_mapping": {"model_flag": "--model", "effort_flag": "--effort"},
        }
        scope = build_compatibility_scope(
            manifest,
            requested_model=None,
            requested_effort=None,
            instruction_policy_fingerprint="a" * 64,
            source_root=SCRIPTS.parent,
        )
        tampered = copy.deepcopy(scope)
        tampered["model_effort"]["requested_effort"] = "low"
        with self.assertRaisesRegex(ValidationError, "fingerprint"):
            build_compatibility_scope(
                manifest,
                requested_model=None,
                requested_effort=None,
                instruction_policy_fingerprint="a" * 64,
                source_root=SCRIPTS.parent,
                existing_scope=tampered,
            )

    def test_invalidation_matrix_distinguishes_shared_runtime_and_selection_drift(self):
        scope = {
            "target": "agy",
            "source_fingerprint": "a" * 64,
            "identity": {
                "executable_fingerprint": "b" * 64,
                "execution_fingerprint": "c" * 64,
                "version_fingerprint": "d" * 64,
                "platform_fingerprint": "e" * 64,
                "protocol_fingerprint": "f" * 64,
            },
            "model_effort": {
                "requested_model": "gemini-3.8",
                "requested_effort": "high",
            },
            "instruction_policy_fingerprint": "1" * 64,
            "fingerprint": "2" * 64,
        }
        observed = copy.deepcopy(scope)
        observed["source_fingerprint"] = "3" * 64
        observed["identity"]["execution_fingerprint"] = "4" * 64
        observed["model_effort"]["requested_effort"] = "low"
        observed["fingerprint"] = "5" * 64
        reasons = _scope_invalidations(scope, observed)
        self.assertEqual(
            {item["reason"] for item in reasons},
            {
                "selected_target_source_changed",
                "runtime_identity_changed",
                "model_or_effort_selection_changed",
                "compatibility_scope_fingerprint_changed",
            },
        )

    def test_requalify_parser_is_plan_by_default_and_gate_is_explicit(self):
        args = build_parser().parse_args(
            [
                "requalify",
                "--target",
                "agy",
                "--manifest",
                "manifest.json",
                "--mapping",
                "mapping.json",
            ]
        )
        self.assertFalse(args.execute)
        self.assertFalse(args.ack_live_qualification)

    def test_identity_diagnostic_has_no_exception_or_command_payload(self):
        value = identity_blocker(
            check="same-target AGY process birth identity",
            remedy="re-run doctor after the process inventory is stable",
            pid=123,
            birth_identity="kernel-start-identity",
            terminal_association="tmux-session-bound",
        )
        self.assertEqual(value["pid"], 123)
        self.assertNotIn("argv", value)
        self.assertNotIn("exception", value)

    def test_selected_model_effort_are_bound_in_instruction_runtime_contract(self):
        compiled = compile_instruction_wrapper(
            target="agy",
            task="bounded qualification task",
            contract_identity={"contract": "selected"},
            workspace_identity={"workspace": "fixture"},
            run_identity={"run": "selected"},
            model_binding="installed-provider-id",
            effort_binding="high",
        )
        self.assertEqual(
            compiled.manifest["runtime_binding"],
            {"model": "installed-provider-id", "effort": "high"},
        )
