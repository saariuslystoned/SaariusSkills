from __future__ import annotations

import copy
import json
import shutil
import sys
import tempfile
from pathlib import Path
from unittest import TestCase

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "puppet" / "scripts"
SKILL_ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

from adapter_lab import _requalify, build_parser  # noqa: E402
from puppet_lib.adapter_manifest import (  # noqa: E402
    ADAPTER_MANIFEST_SCHEMA_VERSION,
    PROBE_CAPABILITIES,
    QUALIFICATION_PROFILE,
    QUALIFICATION_RECEIPT_SCHEMA_VERSION,
    QUALIFICATION_STATE_SCHEMA_VERSION,
    _RECEIPT_FIELDS,
    AdapterManifest,
    _bind_expected_qualification_authority,
    direct_execution_bundle,
    verify_qualification_receipt,
)
from puppet_lib.authority import attest_qualification  # noqa: E402
from puppet_lib.agy_launch import (  # noqa: E402
    AGY_REGULAR_PERMISSION_FLAGS,
    AGY_REGULAR_PROJECT_ISOLATION_FLAGS,
    AGY_REGULAR_SANDBOX_FLAGS,
    agy_regular_launch_argv,
)
from puppet_lib.errors import IdentityError, UnsupportedError, ValidationError  # noqa: E402
from puppet_lib.handoffs import PROTOCOL_FINGERPRINT  # noqa: E402
from puppet_lib.instructions import (  # noqa: E402
    compile_instruction_wrapper,
    instruction_policy_fingerprint,
)
from puppet_lib.profiles import (  # noqa: E402
    PROMPT_TRANSPORT,
    SUBMIT_SETTLE_SECONDS,
    default_session_profile,
    session_profiles_for,
    startup_settle_seconds_for,
)
from puppet_lib.qualification_scope import (  # noqa: E402
    QUALIFICATION_SCOPE_SCHEMA,
    TASK_SCOPE_SCHEMA,
    build_compatibility_scope,
    build_task_scope,
    compare_qualification_compatibility,
    compatibility_invalidations,
    evaluate_qualification_reuse,
    scope_source_paths,
    shared_source_paths,
    target_source_paths,
    validate_compatibility_scope,
)
from puppet_lib.safety import canonical_json_bytes, sha256_bytes, sha256_file  # noqa: E402


def _manifest(target: str = "agy", *, protocol: str = PROTOCOL_FINGERPRINT) -> dict:
    executable = Path("/bin/echo").resolve(strict=True)
    details = executable.stat()
    identity = {
        "requested_path": str(executable),
        "resolved_path": str(executable),
        "sha256": sha256_file(executable),
        "version_sha256": "b" * 64,
        "help_sha256": "c" * 64,
        "device": details.st_dev,
        "inode": details.st_ino,
        "size": details.st_size,
        "mtime_ns": details.st_mtime_ns,
    }
    mapping = {
        "complete": True,
        "launch_argv": (
            agy_regular_launch_argv(executable)
            if target == "agy"
            else [str(executable), "--dangerously-bypass-approvals-and-sandbox"]
        ),
        "permission_declared": True,
        "permission_flags": (
            list(AGY_REGULAR_PERMISSION_FLAGS)
            if target == "agy"
            else ["--dangerously-bypass-approvals-and-sandbox"]
        ),
        "prompt_transport": PROMPT_TRANSPORT,
        "prompt_transport_declared": True,
        "sandbox_disable_declared": True,
        "sandbox_flags": list(AGY_REGULAR_SANDBOX_FLAGS) if target == "agy" else [],
        "project_isolation_declared": target == "agy",
        "project_isolation_flags": (
            list(AGY_REGULAR_PROJECT_ISOLATION_FLAGS) if target == "agy" else []
        ),
        "session_profiles": session_profiles_for(target),
        "session_profiles_declared": True,
        "startup_settle_seconds": startup_settle_seconds_for(target),
        "submit_settle_seconds": SUBMIT_SETTLE_SECONDS,
        "model_flag": "--model",
        "effort_flag": "--effort",
    }
    return {
        "schema_version": ADAPTER_MANIFEST_SCHEMA_VERSION,
        "target": target,
        "generated_at": "2026-09-18T00:00:00Z",
        "platform": {"system": "Darwin", "release": "25", "machine": "arm64"},
        "executable": identity,
        "execution": direct_execution_bundle(identity),
        "adapter_fingerprint": "d" * 64,
        "protocol_fingerprint": protocol,
        "yolo_mapping": mapping,
        "capabilities": {
            name: "declared"
            for name in (
                "launch",
                "send",
                "status",
                "wait",
                "checkpoint",
                "resume",
                "halt",
            )
        },
        "doctor_only": True,
        "qualification": None,
    }


def _write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")


def _write_attested_scoped_receipt(
    receipt_path: Path,
    *,
    manifest: dict,
    scope: dict,
    authority_root: Path,
) -> dict:
    """Smallest accepted scoped receipt that reaches verify's compatibility check."""

    receipt_core = {
        "schema_version": QUALIFICATION_RECEIPT_SCHEMA_VERSION,
        "kind": "real_harness_conformance",
        "run_id": "scope-runtime-run",
        "target": manifest["target"],
        "session_profile": default_session_profile(manifest["target"]),
        "result": "accepted",
        "controller": "controller-a",
        "campaign_id": "campaign-one",
        "goal_fingerprint": "7" * 64,
        "executable_fingerprint": manifest["executable"]["sha256"],
        "execution_fingerprint": manifest["execution"]["execution_fingerprint"],
        "version_fingerprint": manifest["executable"]["version_sha256"],
        "platform_fingerprint": sha256_bytes(canonical_json_bytes(manifest["platform"])),
        "adapter_fingerprint": manifest["adapter_fingerprint"],
        "protocol_fingerprint": manifest["protocol_fingerprint"],
        "yolo_mapping_sha256": sha256_bytes(
            canonical_json_bytes(manifest["yolo_mapping"])
        ),
        "launch_plan_sha256": "a" * 64,
        "subscription_profile_sha256": "b" * 64,
        "instruction_policy_fingerprint": scope["instruction_policy_fingerprint"],
        "capabilities": list(PROBE_CAPABILITIES),
        "accepted_checkpoint_id": "c" * 64,
        "acceptance_sha256": "d" * 64,
        "halt_receipt_sha256": "e" * 64,
        "plane_activation": None,
        "workspace_isolation": None,
        "codex_entry_source": None,
        "codex_control_source": None,
        "proof_refs": [],
        "compatibility_scope": scope,
        "requested_model": None,
        "requested_effort": None,
    }
    receipt = dict(
        receipt_core,
        controller_attestation=attest_qualification(
            receipt_core, authority_root=authority_root
        ),
    )
    _write_json(receipt_path, receipt)
    _write_json(
        receipt_path.parent / "state.json",
        {
            "schema_version": QUALIFICATION_STATE_SCHEMA_VERSION,
            "profile": QUALIFICATION_PROFILE,
        },
    )
    return receipt


class QualificationReuseTests(TestCase):
    def test_target_scope_excludes_unrelated_harness_sources(self):
        agy_sources = set(scope_source_paths("agy"))
        cursor_sources = set(scope_source_paths("cursor"))
        shared = set(shared_source_paths())

        self.assertTrue(shared <= agy_sources)
        self.assertTrue(shared <= cursor_sources)
        self.assertIn("scripts/puppet_lib/caller.py", shared)
        self.assertIn("scripts/puppet_lib/transport.py", shared)
        self.assertIn("scripts/puppet_lib/authority.py", shared)
        self.assertIn("scripts/puppet_lib/subscription_profiles.py", shared)
        self.assertIn("scripts/puppet_lib/beacons.py", shared)
        self.assertIn("scripts/puppet_lib/signal_exec.py", shared)
        self.assertIn("scripts/puppet_lib/instruction_planes.py", shared)
        self.assertNotIn("scripts/puppet_lib/subscription_onboarding.py", shared)
        self.assertNotIn("scripts/puppet_lib/viewer.py", shared)
        self.assertNotIn("scripts/puppet_lib/run_observations.py", shared)
        self.assertNotIn(
            "scripts/puppet_lib/beacons.py",
            set(target_source_paths("agy"))
            | set(target_source_paths("cursor"))
            | set(target_source_paths("claude"))
            | set(target_source_paths("codex"))
            | set(target_source_paths("grok")),
        )
        self.assertNotIn(
            "scripts/puppet_lib/signal_exec.py",
            set(target_source_paths("agy"))
            | set(target_source_paths("cursor"))
            | set(target_source_paths("claude"))
            | set(target_source_paths("codex"))
            | set(target_source_paths("grok")),
        )
        self.assertNotIn(
            "scripts/puppet_lib/instruction_planes.py",
            set(target_source_paths("agy"))
            | set(target_source_paths("cursor"))
            | set(target_source_paths("claude"))
            | set(target_source_paths("codex"))
            | set(target_source_paths("grok")),
        )
        self.assertNotIn(
            "scripts/puppet_lib/subscription_profiles.py",
            set(target_source_paths("agy"))
            | set(target_source_paths("cursor"))
            | set(target_source_paths("claude"))
            | set(target_source_paths("codex"))
            | set(target_source_paths("grok")),
        )
        self.assertIn("scripts/puppet_lib/agy_launch.py", agy_sources)
        self.assertIn("scripts/puppet_lib/agy_print.py", agy_sources)
        self.assertNotIn("scripts/puppet_lib/agy_print.py", shared)
        self.assertNotIn("scripts/puppet_lib/cursor_qualification.py", agy_sources)
        self.assertIn("scripts/puppet_lib/cursor_qualification.py", cursor_sources)
        self.assertIn("scripts/puppet_lib/cursor_acp.py", cursor_sources)
        self.assertNotIn("scripts/puppet_lib/cursor_acp.py", shared)
        self.assertNotIn("scripts/puppet_lib/cursor_acp.py", agy_sources)
        grok_sources = set(scope_source_paths("grok"))
        codex_sources = set(scope_source_paths("codex"))
        self.assertIn("scripts/puppet_lib/grok_admission.py", grok_sources)
        self.assertNotIn("scripts/puppet_lib/grok_admission.py", shared)
        self.assertNotIn("scripts/puppet_lib/grok_admission.py", cursor_sources)
        self.assertNotIn("scripts/puppet_lib/grok_admission.py", agy_sources)
        self.assertNotIn("scripts/puppet_lib/cursor_acp.py", grok_sources)
        self.assertIn("scripts/puppet_lib/codex_admission.py", codex_sources)
        self.assertNotIn("scripts/puppet_lib/codex_admission.py", shared)
        self.assertNotIn("scripts/puppet_lib/codex_admission.py", grok_sources)
        self.assertNotIn("scripts/puppet_lib/codex_admission.py", cursor_sources)
        self.assertNotIn("scripts/puppet_lib/codex_admission.py", agy_sources)
        self.assertNotIn("scripts/puppet_lib/grok_admission.py", codex_sources)
        claude_sources = set(scope_source_paths("claude"))
        self.assertIn("scripts/puppet_lib/claude_admission.py", claude_sources)
        self.assertNotIn("scripts/puppet_lib/claude_admission.py", shared)
        self.assertNotIn("scripts/puppet_lib/claude_admission.py", grok_sources)
        self.assertNotIn("scripts/puppet_lib/claude_admission.py", codex_sources)
        self.assertNotIn("scripts/puppet_lib/claude_admission.py", cursor_sources)
        self.assertNotIn("scripts/puppet_lib/claude_admission.py", agy_sources)
        self.assertNotIn("scripts/puppet_lib/grok_admission.py", claude_sources)
        self.assertNotIn("scripts/puppet_lib/codex_admission.py", claude_sources)
        self.assertEqual(agy_sources - shared, set(target_source_paths("agy")))

    def test_scope_binds_requested_selectors_without_observed_model_claim(self):
        scope = build_compatibility_scope(
            _manifest(),
            requested_model="installed-selector-a",
            requested_effort="high",
            instruction_policy_fingerprint="a" * 64,
            source_root=SKILL_ROOT,
        )

        self.assertEqual(scope["schema"], QUALIFICATION_SCOPE_SCHEMA)
        self.assertEqual(scope["target"], "agy")
        model_effort = scope["harness_scope"]["model_effort"]
        self.assertEqual(model_effort["requested_model"], "installed-selector-a")
        self.assertEqual(model_effort["requested_effort"], "high")
        self.assertIsNone(model_effort["observed_model"])
        self.assertIsNone(model_effort["observed_effort"])
        self.assertNotIn("adapter_fingerprint", scope)
        self.assertNotIn("adapter_fingerprint", scope["harness_scope"]["identity"])
        compiled = compile_instruction_wrapper(
            target="agy",
            task="bounded qualification task",
            contract_identity={"contract": "selected"},
            workspace_identity={"workspace": "fixture"},
            run_identity={"run": "selected"},
        )
        self.assertEqual(
            compiled.manifest["model_observation"]["resolved_identity"], "unavailable"
        )
        self.assertEqual(compiled.manifest["runtime_binding"]["model"], "unavailable")
        with self.assertRaisesRegex(ValidationError, "model binding"):
            compile_instruction_wrapper(
                target="agy",
                task="bounded qualification task",
                contract_identity={"contract": "selected"},
                workspace_identity={"workspace": "fixture"},
                run_identity={"run": "selected"},
                model_binding="installed-selector-a",
                effort_binding="high",
            )

    def test_legacy_and_tampered_scope_are_rejected(self):
        manifest = _manifest()
        with self.assertRaisesRegex(UnsupportedError, "legacy"):
            build_compatibility_scope(
                manifest,
                requested_model=None,
                requested_effort=None,
                instruction_policy_fingerprint="a" * 64,
                source_root=SKILL_ROOT,
                legacy=True,
            )
        scope = build_compatibility_scope(
            manifest,
            requested_model=None,
            requested_effort=None,
            instruction_policy_fingerprint="a" * 64,
            source_root=SKILL_ROOT,
        )
        tampered = copy.deepcopy(scope)
        tampered["harness_scope"]["model_effort"]["requested_effort"] = "low"
        with self.assertRaisesRegex(ValidationError, "fingerprint"):
            validate_compatibility_scope(tampered)
        with self.assertRaisesRegex(ValidationError, "fingerprint"):
            build_compatibility_scope(
                manifest,
                requested_model=None,
                requested_effort=None,
                instruction_policy_fingerprint="a" * 64,
                source_root=SKILL_ROOT,
                existing_scope=tampered,
            )

    def test_invalidation_matrix_and_task_authority_are_not_reusable(self):
        manifest = _manifest()
        policy = "1" * 64
        stored = build_compatibility_scope(
            manifest,
            requested_model="installed-selector-a",
            requested_effort="high",
            instruction_policy_fingerprint=policy,
            source_root=SKILL_ROOT,
        )
        observed = copy.deepcopy(stored)
        observed["harness_scope"]["target_source_fingerprint"] = "3" * 64
        observed["transport_authority_scope"]["shared_source_fingerprint"] = "4" * 64
        observed["harness_scope"]["identity"]["execution_fingerprint"] = "5" * 64
        observed["harness_scope"]["model_effort"]["requested_effort"] = "low"
        observed["fingerprint"] = "6" * 64
        first_task = build_task_scope(
            controller="controller-a",
            campaign_id="campaign-one",
            goal_fingerprint="7" * 64,
        )
        second_task = build_task_scope(
            controller="controller-a",
            campaign_id="campaign-two",
            goal_fingerprint="8" * 64,
        )
        drifted_reasons = {
            item["reason"] for item in compatibility_invalidations(stored, observed)
        }
        self.assertEqual(
            drifted_reasons,
            {
                "selected_target_source_changed",
                "transport_or_shared_authority_changed",
                "runtime_identity_changed",
                "model_or_effort_selection_changed",
                "compatibility_scope_fingerprint_changed",
            },
        )
        reused = evaluate_qualification_reuse(
            stored_compatibility=stored,
            stored_task=first_task,
            current_compatibility=stored,
            new_task=second_task,
        )
        self.assertTrue(reused["compatibility_reusable"])
        self.assertFalse(reused["task_authority_reusable"])
        self.assertEqual(reused["task_authority"], "fresh_required")
        self.assertEqual(reused["invalidations"], [])
        self.assertEqual(first_task["schema"], TASK_SCOPE_SCHEMA)
        self.assertEqual(
            compatibility_invalidations(None, stored)[0]["reason"],
            "legacy_or_unscoped_qualification",
        )

    def test_census_scope_receipt_path_ignores_unrelated_harness_and_keeps_shared_invalidation(
        self,
    ):
        manifest = _manifest()
        policy = instruction_policy_fingerprint(target="agy")
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "puppet"
            shutil.copytree(SKILL_ROOT, copied)
            baseline = build_compatibility_scope(
                manifest,
                requested_model=None,
                requested_effort=None,
                instruction_policy_fingerprint=policy,
                source_root=copied,
            )
            cursor_source = (
                copied / "scripts" / "puppet_lib" / "cursor_qualification.py"
            )
            cursor_source.write_text(
                cursor_source.read_text(encoding="utf-8") + "\n# cursor-only drift\n",
                encoding="utf-8",
            )
            after_cursor = compare_qualification_compatibility(
                stored_scope=baseline,
                current_manifest=manifest,
                instruction_policy_fingerprint=policy,
                source_root=copied,
            )
            self.assertEqual(after_cursor["invalidations"], [])
            current_with_global_drift = dict(manifest)
            current_with_global_drift["adapter_fingerprint"] = "f" * 64
            still_reusable = compare_qualification_compatibility(
                stored_scope=baseline,
                current_manifest=current_with_global_drift,
                instruction_policy_fingerprint=policy,
                source_root=copied,
            )
            self.assertEqual(still_reusable["invalidations"], [])
            reuse = evaluate_qualification_reuse(
                stored_compatibility=baseline,
                stored_task=build_task_scope(
                    controller="controller-a",
                    campaign_id="campaign-one",
                    goal_fingerprint="7" * 64,
                ),
                current_compatibility=still_reusable["current_scope"],
                new_task=build_task_scope(
                    controller="controller-a",
                    campaign_id="campaign-two",
                    goal_fingerprint="8" * 64,
                ),
            )
            self.assertTrue(reuse["compatibility_reusable"])
            self.assertFalse(reuse["task_authority_reusable"])
            self.assertEqual(reuse["task_authority"], "fresh_required")
            authority_source = copied / "scripts" / "puppet_lib" / "authority.py"
            authority_source.write_text(
                authority_source.read_text(encoding="utf-8") + "\n# shared drift\n",
                encoding="utf-8",
            )
            after_shared = compare_qualification_compatibility(
                stored_scope=baseline,
                current_manifest=current_with_global_drift,
                instruction_policy_fingerprint=policy,
                source_root=copied,
            )
            self.assertIn(
                "transport_or_shared_authority_changed",
                {item["reason"] for item in after_shared["invalidations"]},
            )
            agy_source = copied / "scripts" / "puppet_lib" / "agy_launch.py"
            agy_source.write_text(
                agy_source.read_text(encoding="utf-8") + "\n# agy drift\n",
                encoding="utf-8",
            )
            after_agy = compare_qualification_compatibility(
                stored_scope=baseline,
                current_manifest=current_with_global_drift,
                instruction_policy_fingerprint=policy,
                source_root=copied,
            )
            reasons = {item["reason"] for item in after_agy["invalidations"]}
            self.assertIn("selected_target_source_changed", reasons)
            self.assertIn("transport_or_shared_authority_changed", reasons)

    def test_agy_print_source_drift_invalidates_agy_without_weakening_shared_tmux(self):
        agy_manifest = _manifest("agy")
        cursor_manifest = _manifest("cursor")
        agy_policy = instruction_policy_fingerprint(target="agy")
        cursor_policy = instruction_policy_fingerprint(target="cursor")
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "puppet"
            shutil.copytree(SKILL_ROOT, copied)
            agy_baseline = build_compatibility_scope(
                agy_manifest,
                requested_model=None,
                requested_effort=None,
                instruction_policy_fingerprint=agy_policy,
                source_root=copied,
            )
            cursor_baseline = build_compatibility_scope(
                cursor_manifest,
                requested_model=None,
                requested_effort=None,
                instruction_policy_fingerprint=cursor_policy,
                source_root=copied,
            )
            cursor_source = copied / "scripts" / "puppet_lib" / "cursor_acp.py"
            cursor_source.write_text(
                cursor_source.read_text(encoding="utf-8") + "\n# cursor-only drift\n",
                encoding="utf-8",
            )
            after_cursor = compare_qualification_compatibility(
                stored_scope=agy_baseline,
                current_manifest=agy_manifest,
                instruction_policy_fingerprint=agy_policy,
                source_root=copied,
            )
            self.assertEqual(after_cursor["invalidations"], [])
            agy_print_source = copied / "scripts" / "puppet_lib" / "agy_print.py"
            agy_print_source.write_text(
                agy_print_source.read_text(encoding="utf-8") + "\n# agy-print drift\n",
                encoding="utf-8",
            )
            after_agy_print = compare_qualification_compatibility(
                stored_scope=agy_baseline,
                current_manifest=agy_manifest,
                instruction_policy_fingerprint=agy_policy,
                source_root=copied,
            )
            agy_reasons = {item["reason"] for item in after_agy_print["invalidations"]}
            self.assertIn("selected_target_source_changed", agy_reasons)
            self.assertNotIn("transport_or_shared_authority_changed", agy_reasons)
            cursor_after_agy_print = compare_qualification_compatibility(
                stored_scope=cursor_baseline,
                current_manifest=cursor_manifest,
                instruction_policy_fingerprint=cursor_policy,
                source_root=copied,
            )
            self.assertNotIn(
                "transport_or_shared_authority_changed",
                {item["reason"] for item in cursor_after_agy_print["invalidations"]},
            )
            tmux_source = copied / "scripts" / "puppet_lib" / "tmux.py"
            tmux_source.write_text(
                tmux_source.read_text(encoding="utf-8") + "\n# shared tmux drift\n",
                encoding="utf-8",
            )
            after_tmux = compare_qualification_compatibility(
                stored_scope=agy_baseline,
                current_manifest=agy_manifest,
                instruction_policy_fingerprint=agy_policy,
                source_root=copied,
            )
            tmux_reasons = {item["reason"] for item in after_tmux["invalidations"]}
            self.assertIn("transport_or_shared_authority_changed", tmux_reasons)
            cursor_after_tmux = compare_qualification_compatibility(
                stored_scope=cursor_baseline,
                current_manifest=cursor_manifest,
                instruction_policy_fingerprint=cursor_policy,
                source_root=copied,
            )
            self.assertIn(
                "transport_or_shared_authority_changed",
                {item["reason"] for item in cursor_after_tmux["invalidations"]},
            )

    def test_subscription_profile_authority_drift_invalidates_while_unrelated_harness_stays_reusable(
        self,
    ):
        manifest = _manifest()
        policy = instruction_policy_fingerprint(target="agy")
        first_task = build_task_scope(
            controller="controller-a",
            campaign_id="campaign-one",
            goal_fingerprint="7" * 64,
        )
        second_task = build_task_scope(
            controller="controller-a",
            campaign_id="campaign-two",
            goal_fingerprint="8" * 64,
        )
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "puppet"
            shutil.copytree(SKILL_ROOT, copied)
            baseline = build_compatibility_scope(
                manifest,
                requested_model=None,
                requested_effort=None,
                instruction_policy_fingerprint=policy,
                source_root=copied,
            )
            cursor_source = (
                copied / "scripts" / "puppet_lib" / "cursor_qualification.py"
            )
            cursor_source.write_text(
                cursor_source.read_text(encoding="utf-8") + "\n# cursor-only drift\n",
                encoding="utf-8",
            )
            after_unrelated = compare_qualification_compatibility(
                stored_scope=baseline,
                current_manifest=manifest,
                instruction_policy_fingerprint=policy,
                source_root=copied,
            )
            self.assertEqual(after_unrelated["invalidations"], [])
            unrelated_reuse = evaluate_qualification_reuse(
                stored_compatibility=baseline,
                stored_task=first_task,
                current_compatibility=after_unrelated["current_scope"],
                new_task=second_task,
            )
            self.assertTrue(unrelated_reuse["compatibility_reusable"])
            self.assertFalse(unrelated_reuse["task_authority_reusable"])
            self.assertEqual(unrelated_reuse["task_authority"], "fresh_required")
            subscription_source = (
                copied / "scripts" / "puppet_lib" / "subscription_profiles.py"
            )
            subscription_source.write_text(
                subscription_source.read_text(encoding="utf-8")
                + "\n# subscription authority drift\n",
                encoding="utf-8",
            )
            after_subscription = compare_qualification_compatibility(
                stored_scope=baseline,
                current_manifest=manifest,
                instruction_policy_fingerprint=policy,
                source_root=copied,
            )
            subscription_reasons = {
                item["reason"] for item in after_subscription["invalidations"]
            }
            self.assertIn("transport_or_shared_authority_changed", subscription_reasons)
            self.assertNotIn("selected_target_source_changed", subscription_reasons)
            subscription_reuse = evaluate_qualification_reuse(
                stored_compatibility=baseline,
                stored_task=first_task,
                current_compatibility=after_subscription["current_scope"],
                new_task=second_task,
            )
            self.assertFalse(subscription_reuse["compatibility_reusable"])
            self.assertFalse(subscription_reuse["task_authority_reusable"])
            authority_source = copied / "scripts" / "puppet_lib" / "authority.py"
            authority_source.write_text(
                authority_source.read_text(encoding="utf-8") + "\n# shared authority drift\n",
                encoding="utf-8",
            )
            after_shared = compare_qualification_compatibility(
                stored_scope=baseline,
                current_manifest=manifest,
                instruction_policy_fingerprint=policy,
                source_root=copied,
            )
            self.assertIn(
                "transport_or_shared_authority_changed",
                {item["reason"] for item in after_shared["invalidations"]},
            )
            grok_source = copied / "scripts" / "puppet_lib" / "grok_admission.py"
            grok_source.write_text(
                grok_source.read_text(encoding="utf-8") + "\n# grok-only drift\n",
                encoding="utf-8",
            )
            after_grok = compare_qualification_compatibility(
                stored_scope=baseline,
                current_manifest=manifest,
                instruction_policy_fingerprint=policy,
                source_root=copied,
            )
            grok_reasons = {item["reason"] for item in after_grok["invalidations"]}
            self.assertIn("transport_or_shared_authority_changed", grok_reasons)
            self.assertNotIn("selected_target_source_changed", grok_reasons)

    def test_shared_runtime_beacon_and_signal_exec_drift_invalidates_comparison_and_receipt(
        self,
    ):
        manifest = _manifest()
        policy = instruction_policy_fingerprint(target="agy")
        current = AdapterManifest.from_dict(manifest)
        first_task = build_task_scope(
            controller="controller-a",
            campaign_id="campaign-one",
            goal_fingerprint="7" * 64,
        )
        second_task = build_task_scope(
            controller="controller-a",
            campaign_id="campaign-two",
            goal_fingerprint="8" * 64,
        )
        omitted = (
            ("scripts/puppet_lib/beacons.py", "# beacon runtime drift\n"),
            ("scripts/puppet_lib/signal_exec.py", "# signal exec drift\n"),
        )
        for relative, note in omitted:
            with self.subTest(relative=relative):
                with tempfile.TemporaryDirectory() as temporary:
                    copied = Path(temporary) / "puppet"
                    shutil.copytree(SKILL_ROOT, copied)
                    authority_root = Path(temporary) / "authority"
                    receipt_path = Path(temporary) / "receipt.json"
                    baseline = build_compatibility_scope(
                        manifest,
                        requested_model=None,
                        requested_effort=None,
                        instruction_policy_fingerprint=policy,
                        source_root=copied,
                    )
                    cursor_source = (
                        copied / "scripts" / "puppet_lib" / "cursor_qualification.py"
                    )
                    cursor_source.write_text(
                        cursor_source.read_text(encoding="utf-8")
                        + "\n# cursor-only drift\n",
                        encoding="utf-8",
                    )
                    grok_source = copied / "scripts" / "puppet_lib" / "grok_admission.py"
                    grok_source.write_text(
                        grok_source.read_text(encoding="utf-8") + "\n# grok-only drift\n",
                        encoding="utf-8",
                    )
                    after_unrelated = compare_qualification_compatibility(
                        stored_scope=baseline,
                        current_manifest=manifest,
                        instruction_policy_fingerprint=policy,
                        source_root=copied,
                    )
                    self.assertEqual(after_unrelated["invalidations"], [])
                    unrelated_reuse = evaluate_qualification_reuse(
                        stored_compatibility=baseline,
                        stored_task=first_task,
                        current_compatibility=after_unrelated["current_scope"],
                        new_task=second_task,
                    )
                    self.assertTrue(unrelated_reuse["compatibility_reusable"])
                    self.assertFalse(unrelated_reuse["task_authority_reusable"])
                    _write_attested_scoped_receipt(
                        receipt_path,
                        manifest=manifest,
                        scope=baseline,
                        authority_root=authority_root,
                    )
                    with self.assertRaisesRegex(
                        ValidationError, "terminal lifecycle commit"
                    ):
                        verify_qualification_receipt(
                            receipt_path,
                            _authority_root=authority_root,
                            _current_manifest=current,
                            _source_root=copied,
                        )
                    runtime_source = copied.joinpath(*relative.split("/"))
                    runtime_source.write_text(
                        runtime_source.read_text(encoding="utf-8") + note,
                        encoding="utf-8",
                    )
                    after_runtime = compare_qualification_compatibility(
                        stored_scope=baseline,
                        current_manifest=manifest,
                        instruction_policy_fingerprint=policy,
                        source_root=copied,
                    )
                    runtime_reasons = {
                        item["reason"] for item in after_runtime["invalidations"]
                    }
                    self.assertIn(
                        "transport_or_shared_authority_changed", runtime_reasons
                    )
                    self.assertNotIn("selected_target_source_changed", runtime_reasons)
                    with self.assertRaisesRegex(
                        IdentityError,
                        "compatibility scope is stale: .*transport_or_shared_authority_changed",
                    ):
                        verify_qualification_receipt(
                            receipt_path,
                            _authority_root=authority_root,
                            _current_manifest=current,
                            _source_root=copied,
                        )

    def test_instruction_plane_launch_grammar_drift_invalidates_comparison_and_receipt(
        self,
    ):
        """Disable a real shared launch-grammar branch and require invalidation.

        instruction_policy_fingerprint hashes wrapper templates/catalog and
        compiler metadata, not instruction_planes.py. probe.py plus AGY/Cursor/
        Grok workspace-plane code import those validators, so an early return
        in ``_validate_qualification_launch_grammar`` must change the shared
        fingerprint.

        The attested scoped fixture is incomplete. Before the mutation,
        verify_qualification_receipt reaches the later terminal-lifecycle-
        commit error; that is not an accepted receipt. After the mutation the
        scoped compare must fail first.

        Remaining candidates stay excluded from shared ownership:
        viewer.py is the human-only TUI ticket/dispatch doorway used by
        session attach, not receipt or compatibility authority. The executed
        attach helper is already scoped as viewer_attach.py and is not
        changed here. run_observations.py records body-free zero-agent/doctor
        observations and supplies Claude planning blocker labels to
        operator_plan and target-local claude_admission;
        verify_qualification_receipt and compare_qualification_compatibility
        do not import or execute it.
        """

        manifest = _manifest()
        policy = instruction_policy_fingerprint(target="agy")
        current = AdapterManifest.from_dict(manifest)
        first_task = build_task_scope(
            controller="controller-a",
            campaign_id="campaign-one",
            goal_fingerprint="7" * 64,
        )
        second_task = build_task_scope(
            controller="controller-a",
            campaign_id="campaign-two",
            goal_fingerprint="8" * 64,
        )
        validator = (
            "def _validate_qualification_launch_grammar(\n"
            "    *,\n"
            "    target: Mapping[str, Any],\n"
            "    plane: str,\n"
            "    materialize: Sequence[Mapping[str, Any]],\n"
            "    launch_delta: Mapping[str, Any],\n"
            ") -> None:\n"
            '    """Keep v1 activation authority to exact, closed native tuples."""\n'
        )
        disabled = validator + "    return\n"
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "puppet"
            shutil.copytree(SKILL_ROOT, copied)
            authority_root = Path(temporary) / "authority"
            receipt_path = Path(temporary) / "receipt.json"
            baseline = build_compatibility_scope(
                manifest,
                requested_model=None,
                requested_effort=None,
                instruction_policy_fingerprint=policy,
                source_root=copied,
            )
            cursor_source = (
                copied / "scripts" / "puppet_lib" / "cursor_qualification.py"
            )
            cursor_source.write_text(
                cursor_source.read_text(encoding="utf-8")
                + "\n# cursor-only drift\n",
                encoding="utf-8",
            )
            grok_source = copied / "scripts" / "puppet_lib" / "grok_admission.py"
            grok_source.write_text(
                grok_source.read_text(encoding="utf-8") + "\n# grok-only drift\n",
                encoding="utf-8",
            )
            after_unrelated = compare_qualification_compatibility(
                stored_scope=baseline,
                current_manifest=manifest,
                instruction_policy_fingerprint=policy,
                source_root=copied,
            )
            self.assertEqual(after_unrelated["invalidations"], [])
            unrelated_reuse = evaluate_qualification_reuse(
                stored_compatibility=baseline,
                stored_task=first_task,
                current_compatibility=after_unrelated["current_scope"],
                new_task=second_task,
            )
            self.assertTrue(unrelated_reuse["compatibility_reusable"])
            self.assertFalse(unrelated_reuse["task_authority_reusable"])
            _write_attested_scoped_receipt(
                receipt_path,
                manifest=manifest,
                scope=baseline,
                authority_root=authority_root,
            )
            with self.assertRaisesRegex(
                ValidationError, "terminal lifecycle commit"
            ):
                verify_qualification_receipt(
                    receipt_path,
                    _authority_root=authority_root,
                    _current_manifest=current,
                    _source_root=copied,
                )
            plane_source = (
                copied / "scripts" / "puppet_lib" / "instruction_planes.py"
            )
            original = plane_source.read_text(encoding="utf-8")
            self.assertIn(validator, original)
            plane_source.write_text(
                original.replace(validator, disabled, 1),
                encoding="utf-8",
            )
            after_planes = compare_qualification_compatibility(
                stored_scope=baseline,
                current_manifest=manifest,
                instruction_policy_fingerprint=policy,
                source_root=copied,
            )
            plane_reasons = {item["reason"] for item in after_planes["invalidations"]}
            self.assertIn("transport_or_shared_authority_changed", plane_reasons)
            self.assertNotIn("selected_target_source_changed", plane_reasons)
            self.assertNotIn("instruction_policy_changed", plane_reasons)
            with self.assertRaisesRegex(
                IdentityError,
                "compatibility scope is stale: .*transport_or_shared_authority_changed",
            ):
                verify_qualification_receipt(
                    receipt_path,
                    _authority_root=authority_root,
                    _current_manifest=current,
                    _source_root=copied,
                )

    def test_verify_qualification_receipt_uses_scope_instead_of_aggregate_adapter_hash(
        self,
    ):
        receipt = {field: None for field in _RECEIPT_FIELDS}
        receipt["schema_version"] = QUALIFICATION_RECEIPT_SCHEMA_VERSION
        receipt["kind"] = "real_harness_conformance"
        receipt["result"] = "accepted"
        receipt["target"] = "agy"
        receipt["compatibility_scope"] = {
            "schema": "puppet.qualification-scope/v0",
            "target": "agy",
        }
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "receipt.json"
            _write_json(path, receipt)
            with self.assertRaisesRegex(
                (UnsupportedError, ValidationError),
                "legacy or unsupported|fields do not match",
            ):
                verify_qualification_receipt(path)

    def test_requalify_parser_is_plan_by_default_and_live_gate_is_explicit(self):
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
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = _manifest()
            policy = instruction_policy_fingerprint(target="agy")
            scope = build_compatibility_scope(
                manifest,
                requested_model=None,
                requested_effort=None,
                instruction_policy_fingerprint=policy,
                source_root=SKILL_ROOT,
            )
            raw = dict(manifest, qualification_scope=scope)
            AdapterManifest.from_dict(raw)
            manifest_path = root / "manifest.json"
            mapping_path = root / "mapping.json"
            _write_json(manifest_path, raw)
            _write_json(mapping_path, raw["yolo_mapping"])
            planned = _requalify(
                build_parser().parse_args(
                    [
                        "requalify",
                        "--target",
                        "agy",
                        "--manifest",
                        str(manifest_path),
                        "--mapping",
                        str(mapping_path),
                    ]
                )
            )
            self.assertEqual(planned["mode"], "plan")
            self.assertTrue(planned["compatibility_reusable"])
            self.assertFalse(planned["task_authority_reusable"])
            self.assertFalse(planned["observed_model_claimed"])
            self.assertEqual(planned["scope_state"], "current")
            self.assertNotIn("argv", planned)
            self.assertNotIn("exception", planned)
            with self.assertRaisesRegex(ValidationError, "requires --execute"):
                _requalify(
                    build_parser().parse_args(
                        [
                            "requalify",
                            "--target",
                            "agy",
                            "--manifest",
                            str(manifest_path),
                            "--mapping",
                            str(mapping_path),
                            "--execute",
                        ]
                    )
                )
            with self.assertRaisesRegex(UnsupportedError, "probe and qualify"):
                _requalify(
                    build_parser().parse_args(
                        [
                            "requalify",
                            "--target",
                            "agy",
                            "--manifest",
                            str(manifest_path),
                            "--mapping",
                            str(mapping_path),
                            "--execute",
                            "--ack-live-qualification",
                        ]
                    )
                )

    def test_doctor_manifest_round_trip_keeps_scope_off_task_authority(self):
        raw = _manifest()
        raw["qualification_scope"] = build_compatibility_scope(
            raw,
            requested_model=None,
            requested_effort=None,
            instruction_policy_fingerprint=instruction_policy_fingerprint(target="agy"),
            source_root=SKILL_ROOT,
        )
        manifest = AdapterManifest.from_dict(raw)
        self.assertEqual(manifest.raw["qualification_scope"]["target"], "agy")
        self.assertNotIn("campaign_id", manifest.raw["qualification_scope"])
        self.assertIsNone(manifest.raw["qualification"])

    def test_validation_path_reuses_compatibility_without_task_authority(self):
        scope = build_compatibility_scope(
            _manifest(),
            requested_model=None,
            requested_effort=None,
            instruction_policy_fingerprint="a" * 64,
            source_root=SKILL_ROOT,
        )
        receipt = {
            "compatibility_scope": scope,
            "controller": "controller-a",
            "campaign_id": "campaign-one",
            "goal_fingerprint": "7" * 64,
        }
        _bind_expected_qualification_authority(
            receipt,
            expected_controller="controller-a",
            expected_campaign_id="campaign-two",
            expected_goal_fingerprint="8" * 64,
        )
        with self.assertRaisesRegex(IdentityError, "controller"):
            _bind_expected_qualification_authority(
                receipt,
                expected_controller="controller-b",
                expected_campaign_id="campaign-two",
                expected_goal_fingerprint="8" * 64,
            )
        legacy = {
            "controller": "controller-a",
            "campaign_id": "campaign-one",
            "goal_fingerprint": "7" * 64,
        }
        with self.assertRaisesRegex(IdentityError, "campaign_id"):
            _bind_expected_qualification_authority(
                legacy,
                expected_controller="controller-a",
                expected_campaign_id="campaign-two",
                expected_goal_fingerprint="8" * 64,
            )
