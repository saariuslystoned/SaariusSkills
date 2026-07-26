from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from importlib import import_module
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "puppet" / "scripts"
TEMPLATES = ROOT / "skills" / "puppet" / "templates" / "instructions"
sys.path.insert(0, str(SCRIPTS))

TARGETS = import_module("puppet_lib.contracts").TARGETS
sha256_bytes = import_module("puppet_lib.safety").sha256_bytes
ValidationError = import_module("puppet_lib.errors").ValidationError

puppet_instructions = import_module("puppet_lib.instructions")
CompiledInstruction = puppet_instructions.CompiledInstruction
compile_instruction_wrapper = puppet_instructions.compile_instruction_wrapper
instruction_policy_fingerprint = puppet_instructions.instruction_policy_fingerprint
validate_instruction_manifest = puppet_instructions.validate_instruction_manifest


BASE_CONTRACT_ID = {"contract": "contract-a"}
BASE_WORKSPACE_ID = {"repo": "repo", "path": "main"}
BASE_RUN_ID = {"run": "run-id"}


class InstructionCompilerTests(unittest.TestCase):
    def _base_kwargs(self):
        return {
            "contract_identity": BASE_CONTRACT_ID,
            "workspace_identity": BASE_WORKSPACE_ID,
            "run_identity": BASE_RUN_ID,
            "task": "run a bounded task",
            "model_binding": "default",
            "effort_binding": "default",
        }

    def test_compile_baseline_and_all_targets(self):
        for target in sorted(TARGETS):
            compiled = compile_instruction_wrapper(
                target=target,
                **self._base_kwargs(),
            )
            self.assertIsInstance(compiled, CompiledInstruction)

            text = compiled.rendered.decode("utf-8")
            self.assertIn("## universal", text)
            self.assertIn("## harness/%s" % target, text)
            self.assertIn("## model/default-unresolved", text)
            self.assertIn("## lifecycle/regular", text)
            self.assertIn("## runtime_contract", text)
            self.assertIn("## task_packet", text)

            manifest = compiled.manifest
            self.assertEqual(manifest["schema_version"], 1)
            self.assertEqual(manifest["kind"], "instruction_wrapper")
            self.assertEqual(
                manifest["compiler_id"], "puppet-instruction-compiler-core"
            )
            self.assertEqual(manifest["target"], target)
            self.assertEqual(manifest["session_profile"], "regular")
            self.assertEqual(manifest["instruction_plane"], "initial_message_wrapper")
            self.assertEqual(manifest["qualification_state"], "baseline_unqualified")
            self.assertEqual(
                manifest["delivery_transport"],
                {
                    "kind": "tmux_load_buffer_stdin",
                    "body_in_argv": False,
                    "materialization": "memory_only",
                    "native_config_writes": [],
                },
            )
            self.assertEqual(manifest["session_activation"], {"scope": "regular_only"})
            self.assertEqual(manifest["cleanup"], {"kind": "none"})
            self.assertEqual(
                manifest["model_observation"],
                {
                    "selection": "current_default",
                    "resolved_identity": "unavailable",
                    "effort": "unavailable",
                },
            )

            expected_layers = [
                ("universal", "universal"),
                ("harness/%s" % target, "harness"),
                ("model/default-unresolved", "model"),
                ("lifecycle/regular", "lifecycle"),
                ("runtime_contract", "runtime"),
                ("task_packet", "task"),
            ]
            self.assertEqual(
                [(item["name"], item["source"]) for item in manifest["ordered_layers"]],
                expected_layers,
            )
            self.assertEqual(len(manifest["ordered_layers"]), 6)
            self.assertEqual(len(manifest["contract_identity"]), len(BASE_CONTRACT_ID))
            self.assertEqual(manifest["contract_identity"], BASE_CONTRACT_ID)
            self.assertEqual(manifest["workspace_identity"], BASE_WORKSPACE_ID)
            self.assertEqual(manifest["run_identity"], BASE_RUN_ID)
            self.assertNotIn("/goal", text)
            self.assertNotIn("/loop", text)
            self.assertNotIn("/teamwork-preview", text)

    def test_policy_is_target_specific_and_task_independent(self):
        fingerprints = {
            target: instruction_policy_fingerprint(
                target=target,
                template_root=TEMPLATES,
            )
            for target in TARGETS
        }
        self.assertEqual(len(set(fingerprints.values())), len(TARGETS))

        first = compile_instruction_wrapper(target="codex", **self._base_kwargs())
        second = compile_instruction_wrapper(
            target="codex",
            **{**self._base_kwargs(), "task": "run a different bounded task"},
        )
        self.assertEqual(
            first.manifest["instruction_policy_fingerprint"],
            second.manifest["instruction_policy_fingerprint"],
        )
        self.assertNotEqual(
            first.manifest["effective_contract_fingerprint"],
            second.manifest["effective_contract_fingerprint"],
        )
        self.assertNotEqual(
            first.manifest["rendered_sha256"],
            second.manifest["rendered_sha256"],
        )

    def test_agy_overlay_forbids_undeclared_parallel_handoffs(self):
        compiled = compile_instruction_wrapper(
            target="agy",
            **self._base_kwargs(),
        )
        text = compiled.rendered.decode("utf-8")
        self.assertIn("exact artifact allowlists as hard boundaries", text)
        self.assertIn("create exactly that file", text)
        self.assertIn("Never synthesize `conformance_handoff.json`", text)

    def test_compile_with_addendum_and_task_hash_variation(self):
        compiled_base = compile_instruction_wrapper(
            target="codex",
            **self._base_kwargs(),
        )
        compiled_addendum = compile_instruction_wrapper(
            target="codex",
            task_addendum="extra context",
            **self._base_kwargs(),
        )

        base_fingerprint = compiled_base.manifest["effective_contract_fingerprint"]
        addendum_fingerprint = compiled_addendum.manifest[
            "effective_contract_fingerprint"
        ]
        self.assertNotEqual(base_fingerprint, addendum_fingerprint)
        self.assertEqual(len(compiled_addendum.manifest["ordered_layers"]), 7)
        self.assertEqual(
            compiled_addendum.manifest["ordered_layers"][-1]["name"],
            "user_addendum",
        )

    def test_manifest_validation_and_fingerprint_checks(self):
        compiled = compile_instruction_wrapper(
            target="grok",
            **self._base_kwargs(),
        )
        validated = validate_instruction_manifest(
            compiled.manifest, target="grok", template_root=TEMPLATES
        )
        self.assertEqual(validated, compiled.manifest)
        self.assertEqual(
            validated["instruction_policy_fingerprint"],
            instruction_policy_fingerprint(target="grok", template_root=TEMPLATES),
        )
        with self.assertRaises(ValidationError):
            validate_instruction_manifest(
                {"bad": True}, target="grok", template_root=TEMPLATES
            )

    def test_manifest_rejects_layer_order_and_duplicates_and_fingerprint_mismatch(self):
        compiled = compile_instruction_wrapper(
            target="claude",
            **self._base_kwargs(),
        )
        manifest = dict(compiled.manifest)

        bad_order = dict(manifest)
        bad_order["ordered_layers"] = list(reversed(manifest["ordered_layers"]))
        with self.assertRaises(ValidationError):
            validate_instruction_manifest(
                bad_order, target="claude", template_root=TEMPLATES
            )

        duplicate = dict(manifest)
        duplicate["ordered_layers"] = [manifest["ordered_layers"][0]] * 6
        with self.assertRaises(ValidationError):
            validate_instruction_manifest(
                duplicate, target="claude", template_root=TEMPLATES
            )

        random_hash = sha256_bytes(b"random")
        bad_effective = dict(manifest)
        bad_effective["effective_contract_fingerprint"] = random_hash
        with self.assertRaises(ValidationError):
            validate_instruction_manifest(
                bad_effective, target="claude", template_root=TEMPLATES
            )

    def test_manifest_rederives_shipped_and_runtime_layers(self):
        compiled = compile_instruction_wrapper(
            target="claude",
            runtime_contract_layer={"controller": "codex", "mode": "test"},
            **self._base_kwargs(),
        )

        bad_shipped = json.loads(json.dumps(compiled.manifest))
        bad_shipped["ordered_layers"][0]["sha256"] = sha256_bytes(b"forged")
        bad_shipped["effective_contract_fingerprint"] = (
            puppet_instructions._compute_effective_contract_fingerprint(bad_shipped)
        )
        with self.assertRaises(ValidationError):
            validate_instruction_manifest(
                bad_shipped,
                target="claude",
                template_root=TEMPLATES,
            )

        bad_runtime = json.loads(json.dumps(compiled.manifest))
        bad_runtime["orchestration_contract"]["mode"] = "mutate"
        bad_runtime["effective_contract_fingerprint"] = (
            puppet_instructions._compute_effective_contract_fingerprint(bad_runtime)
        )
        with self.assertRaises(ValidationError):
            validate_instruction_manifest(
                bad_runtime,
                target="claude",
                template_root=TEMPLATES,
            )

        bad_bytes = json.loads(json.dumps(compiled.manifest))
        bad_bytes["byte_count"] += 1
        bad_bytes["effective_contract_fingerprint"] = (
            puppet_instructions._compute_effective_contract_fingerprint(bad_bytes)
        )
        with self.assertRaises(ValidationError):
            validate_instruction_manifest(
                bad_bytes,
                target="claude",
                template_root=TEMPLATES,
            )

    def test_template_root_is_injectable(self):
        with tempfile.TemporaryDirectory() as temporary:
            override_root = Path(temporary) / "instructions"
            shutil.copytree(TEMPLATES, override_root)
            (override_root / "universal.md").write_text(
                "## universal\ncustom universal layer",
                encoding="utf-8",
            )
            compiled = compile_instruction_wrapper(
                target="cursor",
                **self._base_kwargs(),
                template_root=override_root,
            )
            text = compiled.rendered.decode("utf-8")
            self.assertIn("custom universal layer", text)

    def test_template_path_and_text_safety(self):
        def _copied_case(name: str) -> Path:
            case_root = Path(temporary) / name
            shutil.copytree(TEMPLATES, case_root)
            return case_root

        with tempfile.TemporaryDirectory() as temporary:
            override_root = _copied_case("escape")
            bad_catalog = json.loads(
                (override_root / "catalog.json").read_text("utf-8")
            )
            bad_catalog["shipped_layers"]["universal"]["path"] = "../outside.md"
            (override_root / "outside.md").write_text("outside", encoding="utf-8")
            (override_root / "catalog.json").write_text(
                json.dumps(bad_catalog), encoding="utf-8"
            )
            with self.assertRaises(ValidationError):
                compile_instruction_wrapper(
                    target="agy",
                    **self._base_kwargs(),
                    template_root=override_root,
                )

            override_root = _copied_case("symlink")
            bad_catalog = json.loads(
                (override_root / "catalog.json").read_text("utf-8")
            )
            real_payload = override_root / "real_root"
            real_payload.mkdir()
            link = override_root / "link"
            link.symlink_to(real_payload)
            (real_payload / "codex.md").write_text("safe", encoding="utf-8")
            bad_catalog["shipped_layers"]["harnesses"]["agy"] = "link/codex.md"
            (override_root / "catalog.json").write_text(
                json.dumps(bad_catalog), encoding="utf-8"
            )
            with self.assertRaises(ValidationError):
                compile_instruction_wrapper(
                    target="agy",
                    **self._base_kwargs(),
                    template_root=override_root,
                )

            override_root = _copied_case("invalid-utf8")
            bad_catalog = json.loads(
                (override_root / "catalog.json").read_text("utf-8")
            )
            (override_root / "universal.md").write_bytes(b"\xff\xfe\x00")
            with self.assertRaises(ValidationError):
                compile_instruction_wrapper(
                    target="agy",
                    **self._base_kwargs(),
                    template_root=override_root,
                )

            override_root = _copied_case("oversize")
            (override_root / "catalog.json").write_text(
                json.dumps(
                    json.loads((override_root / "catalog.json").read_text("utf-8"))
                ),
                encoding="utf-8",
            )
            (override_root / "universal.md").write_text("a" * 70000, encoding="utf-8")
            with self.assertRaises(ValidationError):
                compile_instruction_wrapper(
                    target="agy",
                    **self._base_kwargs(),
                    template_root=override_root,
                )

    def test_invalid_inputs_are_rejected(self):
        base_kwargs = self._base_kwargs()

        with self.assertRaises(ValidationError):
            compile_instruction_wrapper(target="invalid", **base_kwargs)

        with self.assertRaises(ValidationError):
            compile_instruction_wrapper(
                target="codex", session_profile="doctor", **base_kwargs
            )

        with self.assertRaises(ValidationError):
            compile_instruction_wrapper(
                target="codex",
                **{**base_kwargs, "task": "   "},
            )

        with self.assertRaises(ValidationError):
            compile_instruction_wrapper(
                target="codex",
                **{
                    **base_kwargs,
                    "contract_identity": {},
                    "workspace_identity": BASE_WORKSPACE_ID,
                    "run_identity": BASE_RUN_ID,
                },
            )

        with self.assertRaises(ValidationError):
            compile_instruction_wrapper(
                target="codex", **{**base_kwargs, "task": "run\u0000task"}
            )

        with self.assertRaises(ValidationError):
            compile_instruction_wrapper(
                target="codex", **{**base_kwargs, "task": "ghp-" + "A" * 24}
            )

        with self.assertRaises(ValidationError):
            compile_instruction_wrapper(
                target="codex", **{**base_kwargs, "task": "x" * 33000}
            )


if __name__ == "__main__":
    unittest.main()
