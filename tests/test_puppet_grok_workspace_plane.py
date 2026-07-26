from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "puppet" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from puppet_lib.adapter_manifest import (  # noqa: E402
    validate_grok_workspace_isolation,
    validate_terminal_workspace_isolation,
    workspace_isolation_target,
)
from puppet_lib.errors import (  # noqa: E402
    ConflictError,
    IdentityError,
    UnsupportedError,
    ValidationError,
)
from puppet_lib.grok_launch import (  # noqa: E402
    GROK_EXECUTABLE_SHA256,
    GROK_LAUNCH_AUTHORITY_BLOCKER,
    GROK_RUNTIME_BASENAME,
    GROK_WORKSPACE_BINDING_SCHEMA,
    GROK_WORKSPACE_BINDING_STATE,
)
from puppet_lib.grok_workspace_plane import (  # noqa: E402
    DESCRIPTOR_SCHEMA,
    FILESYSTEM_ABSENCE_PROOF,
    GROK_NO_BLEED_FS_SHORTCUT_BLOCKER,
    GROK_PUBLIC_LAUNCH_FENCED,
    GROK_QUALIFICATION_NONPROMOTABLE,
    LEGACY_MATERIALIZATION_RECEIPT_SCHEMA,
    LEGACY_ROLLBACK_RECEIPT_SCHEMA,
    MATCHED_CONTROL_PRECHECK_SCHEMA,
    MATCHED_CONTROL_SCHEMA,
    MATERIALIZATION_RECEIPT_SCHEMA,
    PAIRED_RUNTIME_PROOF,
    ROLLBACK_RECEIPT_SCHEMA,
    TERMINAL_SCHEMA,
    attest_grok_matched_control,
    build_artifact_relative_path,
    build_grok_entry_descriptor,
    build_grok_qualification_request,
    build_grok_terminal_workspace_isolation,
    grok_probe_mapping_from_qualified,
    grok_qualified_mapping,
    grok_regular_launch_argv,
    is_grok_workspace_mapping_closure,
    materialize_grok_workspace_rule,
    precheck_grok_ordinary_control_artifact_absence,
    reject_filesystem_only_no_bleed_claim,
    require_grok_public_launch_authority,
    require_grok_qualification_promotion,
    require_source_only_grok_binding,
    rollback_grok_workspace_rule,
    validate_grok_entry_descriptor,
    validate_grok_qualification_request,
    validate_grok_workspace_materialization_receipt,
    validate_grok_workspace_rollback_receipt,
    verify_grok_workspace_rule,
)
from puppet_lib.safety import canonical_json_bytes, sha256_bytes  # noqa: E402


def _git(repo: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *arguments],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _init_linked_pair(base: Path) -> tuple[Path, Path]:
    base.mkdir(parents=True, exist_ok=True)
    supervisor = base / "supervisor"
    supervisor.mkdir()
    _git(supervisor, "init", "-b", "main")
    _git(supervisor, "config", "user.email", "puppet@example.com")
    _git(supervisor, "config", "user.name", "Puppet")
    (supervisor / "README").write_text("supervisor\n", encoding="utf-8")
    _git(supervisor, "add", "README")
    _git(supervisor, "commit", "-m", "init")
    candidate = base / "candidate"
    _git(
        supervisor,
        "worktree",
        "add",
        "-b",
        "candidate/qualification",
        str(candidate),
        "main",
    )
    return supervisor, candidate


def _doctor_mapping(executable: Path) -> dict:
    return {
        "complete": False,
        "launch_argv": grok_regular_launch_argv(executable),
        "permission_declared": True,
        "permission_flags": ["--always-approve"],
        "prompt_transport": "interactive_tmux_load_buffer_stdin_declared",
        "prompt_transport_declared": True,
        "sandbox_disable_declared": True,
        "sandbox_flags": ["--sandbox", "off"],
        "project_isolation_declared": False,
        "project_isolation_flags": [],
        "session_profiles": {"regular": ""},
        "session_profiles_declared": True,
        "startup_settle_seconds": 8.0,
        "submit_settle_seconds": 1.0,
        "model_flag": "--model",
        "effort_flag": "--reasoning-effort",
    }


class GrokWorkspacePlaneTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.profile = self.base / "profile"
        self.profile.mkdir(mode=0o700)
        self.profile.chmod(0o700)
        self.executable = self.base / GROK_RUNTIME_BASENAME
        self.executable.write_bytes(b"synthetic-grok-0.2.111")
        self.contract_bytes = b"EFFECTIVE_CONTRACT_BODY_CANARY\n"
        self.content_sha = sha256_bytes(self.contract_bytes)
        self.relative = build_artifact_relative_path(self.content_sha)

    def test_regular_argv_has_no_model_or_effort_selector(self) -> None:
        argv = grok_regular_launch_argv(self.executable)
        self.assertEqual(
            argv,
            [str(self.executable), "--always-approve", "--sandbox", "off"],
        )
        self.assertNotIn("--model", argv)
        self.assertNotIn("--reasoning-effort", argv)

    def test_body_free_request_binds_source_and_derives_no_rule_path(self) -> None:
        cockpit, candidate = _init_linked_pair(self.base / "repo-pair")
        request = build_grok_qualification_request(
            workspace_root=candidate,
            cockpit_root=cockpit,
            controller="codex",
            campaign_id="campaign-grok-request",
            goal_fingerprint="1" * 64,
            executable_sha256="2" * 64,
            adapter_manifest_sha256="3" * 64,
            subscription_profile_root=self.profile,
        )
        self.assertEqual(
            validate_grok_qualification_request(
                request,
                expected_controller="codex",
                expected_campaign_id="campaign-grok-request",
                expected_goal_fingerprint="1" * 64,
                expected_executable_sha256="2" * 64,
                expected_adapter_manifest_sha256="3" * 64,
                expected_subscription_profile_root=self.profile,
            ),
            request,
        )
        self.assertNotIn("artifact_relative_path", request)
        self.assertNotIn("content", json.dumps(request, sort_keys=True))
        self.assertFalse(request["materialization_authorized"])
        self.assertFalse(request["launch_authorized"])
        self.assertFalse(request["qualification_authorized"])
        mutated = copy.deepcopy(request)
        mutated["candidate_head"] = "4" * 40
        with self.assertRaisesRegex(IdentityError, "stale|identity"):
            validate_grok_qualification_request(
                mutated,
                expected_controller="codex",
                expected_campaign_id="campaign-grok-request",
                expected_goal_fingerprint="1" * 64,
                expected_executable_sha256="2" * 64,
                expected_adapter_manifest_sha256="3" * 64,
                expected_subscription_profile_root=self.profile,
            )

    def test_mapping_closure_helpers_remain_exact_and_fail_closed(self) -> None:
        mapping = _doctor_mapping(self.executable)
        qualified = grok_qualified_mapping(mapping)
        self.assertTrue(qualified["complete"])
        self.assertTrue(qualified["project_isolation_declared"])
        self.assertTrue(is_grok_workspace_mapping_closure(qualified))
        workspace = {
            "schema": TERMINAL_SCHEMA,
            "terminal_state": "controller_verified_after_exact_halt",
            "descriptor_sha256": "1" * 64,
            "workspace_root": "/tmp/grok-candidate",
            "startup_cwd": "/tmp/grok-candidate",
            "artifact_relative_path": self.relative,
            "artifact_sha256": self.content_sha,
            "workspace_identity_sha256": "2" * 64,
            "matched_control_sha256": "3" * 64,
            "materialization_sha256": "4" * 64,
            "rollback_sha256": "5" * 64,
            "controller_contract_sha256": "6" * 64,
            "instruction_manifest_sha256": "7" * 64,
            "executable_sha256": "8" * 64,
            "subscription_profile_sha256": "9" * 64,
            "launch_plan_sha256": "a" * 64,
            "halt_receipt_sha256": "b" * 64,
            "observed_model": "unavailable",
        }
        self.assertEqual(
            grok_probe_mapping_from_qualified(
                qualified, workspace_isolation=workspace
            ),
            mapping,
        )
        with self.assertRaisesRegex(IdentityError, "terminal workspace proof"):
            grok_probe_mapping_from_qualified(qualified, workspace_isolation=None)

    def test_create_only_materialize_and_hash_guarded_rollback(self) -> None:
        positive = self.base / "positive"
        positive.mkdir(mode=0o700)
        positive.chmod(0o700)
        materialization = materialize_grok_workspace_rule(
            workspace_root=positive,
            relative_path=self.relative,
            content=self.contract_bytes,
            descriptor_sha256="c" * 64,
        )
        self.assertEqual(materialization["schema"], MATERIALIZATION_RECEIPT_SCHEMA)
        self.assertTrue(materialization["created"])
        self.assertEqual(
            [
                (item["relative_path"], item["created"])
                for item in materialization["parent_directories"]
            ],
            [(".grok", True), (".grok/rules", True)],
        )
        self.assertEqual(
            validate_grok_workspace_materialization_receipt(
                materialization,
                expected_workspace_root=positive,
                expected_relative_path=self.relative,
                expected_content_sha256=self.content_sha,
            ),
            materialization,
        )
        self.assertFalse(materialization["qualification_authorized"])
        self.assertFalse(materialization["launch_authorized"])
        verify_grok_workspace_rule(
            workspace_root=positive,
            relative_path=self.relative,
            expected_content_sha256=self.content_sha,
        )
        with self.assertRaisesRegex(ConflictError, "already exists"):
            materialize_grok_workspace_rule(
                workspace_root=positive,
                relative_path=self.relative,
                content=self.contract_bytes,
                descriptor_sha256="c" * 64,
            )
        with self.assertRaisesRegex(IdentityError, "hash mismatch|non-owned"):
            rollback_grok_workspace_rule(
                workspace_root=positive,
                relative_path=self.relative,
                expected_content_sha256="f" * 64,
            )
        rollback = rollback_grok_workspace_rule(
            workspace_root=positive,
            relative_path=self.relative,
            expected_content_sha256=self.content_sha,
            materialization_receipt=materialization,
        )
        self.assertEqual(rollback["schema"], ROLLBACK_RECEIPT_SCHEMA)
        self.assertTrue(rollback["removed"])
        self.assertEqual(
            rollback["created_parents_removed"], [".grok/rules", ".grok"]
        )
        self.assertTrue(rollback["parent_restoration_verified"])
        self.assertTrue(rollback["workspace_identity_restored"])
        self.assertEqual(
            validate_grok_workspace_rollback_receipt(
                rollback,
                materialization_receipt=materialization,
            ),
            rollback,
        )
        self.assertFalse(rollback["qualification_authorized"])
        artifact = positive.joinpath(*self.relative.split("/"))
        self.assertFalse(artifact.exists())
        self.assertFalse((positive / ".grok").exists())

        replay = rollback_grok_workspace_rule(
            workspace_root=positive,
            relative_path=self.relative,
            expected_content_sha256=self.content_sha,
            materialization_receipt=materialization,
        )
        self.assertFalse(replay["removed"])
        self.assertTrue(replay["workspace_identity_restored"])
        self.assertEqual(
            replay["created_parents_removed"], [".grok/rules", ".grok"]
        )

    def test_rollback_preserves_one_or_both_preexisting_parents(self) -> None:
        for label, create_rules in (("one", False), ("both", True)):
            with self.subTest(label=label):
                workspace = self.base / ("preexisting-" + label)
                workspace.mkdir(mode=0o700)
                grok_dir = workspace / ".grok"
                grok_dir.mkdir(mode=0o700)
                rules_dir = grok_dir / "rules"
                if create_rules:
                    rules_dir.mkdir(mode=0o700)
                materialization = materialize_grok_workspace_rule(
                    workspace_root=workspace,
                    relative_path=self.relative,
                    content=self.contract_bytes,
                    descriptor_sha256="d" * 64,
                )
                self.assertEqual(
                    [item["created"] for item in materialization["parent_directories"]],
                    [False, not create_rules],
                )
                rollback = rollback_grok_workspace_rule(
                    workspace_root=workspace,
                    relative_path=self.relative,
                    expected_content_sha256=self.content_sha,
                    materialization_receipt=materialization,
                )
                self.assertTrue(grok_dir.is_dir())
                self.assertEqual(
                    rollback["preexisting_parents_preserved"],
                    [".grok", ".grok/rules"] if create_rules else [".grok"],
                )
                if create_rules:
                    self.assertTrue(rules_dir.is_dir())
                else:
                    self.assertFalse(rules_dir.exists())
                self.assertTrue(rollback["workspace_identity_restored"])

    def test_nonempty_or_identity_drift_refuses_before_artifact_removal(self) -> None:
        nonempty = self.base / "nonempty"
        nonempty.mkdir(mode=0o700)
        materialization = materialize_grok_workspace_rule(
            workspace_root=nonempty,
            relative_path=self.relative,
            content=self.contract_bytes,
            descriptor_sha256="e" * 64,
        )
        artifact = nonempty.joinpath(*self.relative.split("/"))
        (nonempty / ".grok" / "rules" / "unowned.txt").write_text(
            "keep\n", encoding="utf-8"
        )
        with self.assertRaises((ConflictError, IdentityError)):
            rollback_grok_workspace_rule(
                workspace_root=nonempty,
                relative_path=self.relative,
                expected_content_sha256=self.content_sha,
                materialization_receipt=materialization,
            )
        self.assertTrue(artifact.is_file())

        drifted = self.base / "drifted"
        drifted.mkdir(mode=0o700)
        drifted_materialization = materialize_grok_workspace_rule(
            workspace_root=drifted,
            relative_path=self.relative,
            content=self.contract_bytes,
            descriptor_sha256="f" * 64,
        )
        drifted_rules = drifted / ".grok" / "rules"
        drifted_rules.chmod(0o755)
        with self.assertRaisesRegex(IdentityError, "identity|drifted|ownership"):
            rollback_grok_workspace_rule(
                workspace_root=drifted,
                relative_path=self.relative,
                expected_content_sha256=self.content_sha,
                materialization_receipt=drifted_materialization,
            )
        self.assertTrue(drifted.joinpath(*self.relative.split("/")).is_file())

    def test_symlink_and_ownership_substitution_are_fail_closed(self) -> None:
        workspace = self.base / "symlink-parent"
        workspace.mkdir(mode=0o700)
        outside = self.base / "outside"
        outside.mkdir(mode=0o700)
        (workspace / ".grok").symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(IdentityError, "real directory"):
            materialize_grok_workspace_rule(
                workspace_root=workspace,
                relative_path=self.relative,
                content=self.contract_bytes,
                descriptor_sha256="a" * 64,
            )

        substitution = self.base / "symlink-artifact"
        substitution.mkdir(mode=0o700)
        materialization = materialize_grok_workspace_rule(
            workspace_root=substitution,
            relative_path=self.relative,
            content=self.contract_bytes,
            descriptor_sha256="b" * 64,
        )
        artifact = substitution.joinpath(*self.relative.split("/"))
        artifact.unlink()
        outside_file = self.base / "outside-rule"
        outside_file.write_bytes(self.contract_bytes)
        artifact.symlink_to(outside_file)
        with self.assertRaisesRegex(IdentityError, "regular file|identity"):
            rollback_grok_workspace_rule(
                workspace_root=substitution,
                relative_path=self.relative,
                expected_content_sha256=self.content_sha,
                materialization_receipt=materialization,
            )
        self.assertEqual(outside_file.read_bytes(), self.contract_bytes)

        owned = self.base / "ownership-substitution"
        owned.mkdir(mode=0o700)
        owned_materialization = materialize_grok_workspace_rule(
            workspace_root=owned,
            relative_path=self.relative,
            content=self.contract_bytes,
            descriptor_sha256="c" * 64,
        )
        forged = copy.deepcopy(owned_materialization)
        forged["artifact_identity"]["uid"] += 1
        unsigned = {
            name: forged[name] for name in forged if name != "receipt_sha256"
        }
        forged["receipt_sha256"] = sha256_bytes(canonical_json_bytes(unsigned))
        with self.assertRaisesRegex(IdentityError, "identity changed"):
            rollback_grok_workspace_rule(
                workspace_root=owned,
                relative_path=self.relative,
                expected_content_sha256=self.content_sha,
                materialization_receipt=forged,
            )

    def test_legacy_rollback_is_artifact_only_and_nonpromotable(self) -> None:
        workspace = self.base / "legacy"
        workspace.mkdir(mode=0o700)
        materialization = materialize_grok_workspace_rule(
            workspace_root=workspace,
            relative_path=self.relative,
            content=self.contract_bytes,
            descriptor_sha256="c" * 64,
        )
        legacy = rollback_grok_workspace_rule(
            workspace_root=workspace,
            relative_path=self.relative,
            expected_content_sha256=self.content_sha,
        )
        self.assertEqual(legacy["schema"], LEGACY_ROLLBACK_RECEIPT_SCHEMA)
        self.assertTrue(legacy["absent_after"])
        self.assertFalse(legacy["parent_restoration_verified"])
        self.assertFalse(legacy["workspace_identity_restored"])
        self.assertTrue((workspace / ".grok" / "rules").is_dir())
        legacy_materialization = dict(materialization)
        legacy_materialization["schema"] = LEGACY_MATERIALIZATION_RECEIPT_SCHEMA
        with self.assertRaisesRegex(UnsupportedError, "legacy|non-promotable"):
            validate_grok_workspace_materialization_receipt(
                legacy_materialization,
                expected_workspace_root=workspace,
                expected_relative_path=self.relative,
                expected_content_sha256=self.content_sha,
            )
        with self.assertRaisesRegex(UnsupportedError, "legacy|non-promotable"):
            validate_grok_workspace_rollback_receipt(
                legacy,
                materialization_receipt=materialization,
            )

    def test_filesystem_absence_precheck_never_verifies_no_bleed(self) -> None:
        positive = self.base / "positive"
        ordinary = self.base / "ordinary"
        positive.mkdir(mode=0o700)
        ordinary.mkdir(mode=0o700)
        materialize_grok_workspace_rule(
            workspace_root=positive,
            relative_path=self.relative,
            content=self.contract_bytes,
            descriptor_sha256="c" * 64,
        )
        precheck = precheck_grok_ordinary_control_artifact_absence(
            positive_workspace_root=positive,
            ordinary_workspace_root=ordinary,
            positive_relative_path=self.relative,
            positive_content_sha256=self.content_sha,
            workspace_identity_join_sha256="e" * 64,
        )
        self.assertEqual(precheck["schema"], MATCHED_CONTROL_PRECHECK_SCHEMA)
        self.assertEqual(precheck["proof_strength"], FILESYSTEM_ABSENCE_PROOF)
        self.assertTrue(precheck["ordinary_artifact_absent"])
        self.assertFalse(precheck["no_bleed_verified"])
        self.assertFalse(precheck["qualification_authorized"])
        self.assertFalse(precheck["launch_authorized"])
        self.assertFalse(precheck["activation_authorized"])

        with self.assertRaisesRegex(
            UnsupportedError, "filesystem absence alone|paired subscription-backed"
        ):
            reject_filesystem_only_no_bleed_claim(precheck)

        forged = dict(precheck)
        forged["schema"] = MATCHED_CONTROL_SCHEMA
        forged["no_bleed_verified"] = True
        forged["proof_strength"] = FILESYSTEM_ABSENCE_PROOF
        with self.assertRaisesRegex(
            UnsupportedError, "filesystem absence alone|paired subscription-backed"
        ):
            reject_filesystem_only_no_bleed_claim(forged)

        with self.assertRaisesRegex(
            UnsupportedError, "filesystem absence alone|paired subscription-backed"
        ):
            attest_grok_matched_control(
                positive_workspace_root=positive,
                ordinary_workspace_root=ordinary,
                positive_relative_path=self.relative,
                positive_content_sha256=self.content_sha,
                workspace_identity_join_sha256="e" * 64,
            )

    def test_terminal_isolation_rejects_filesystem_only_matched_control(self) -> None:
        positive = self.base / "pos"
        ordinary = self.base / "ord"
        positive.mkdir(mode=0o700)
        ordinary.mkdir(mode=0o700)
        materialization = materialize_grok_workspace_rule(
            workspace_root=positive,
            relative_path=self.relative,
            content=self.contract_bytes,
            descriptor_sha256="1" * 64,
        )
        precheck = precheck_grok_ordinary_control_artifact_absence(
            positive_workspace_root=positive,
            ordinary_workspace_root=ordinary,
            positive_relative_path=self.relative,
            positive_content_sha256=self.content_sha,
            workspace_identity_join_sha256="2" * 64,
        )
        rollback = rollback_grok_workspace_rule(
            workspace_root=positive,
            relative_path=self.relative,
            expected_content_sha256=self.content_sha,
            materialization_receipt=materialization,
        )
        # Recreate rule so materialization record still joins content hash fields.
        materialization = materialize_grok_workspace_rule(
            workspace_root=positive,
            relative_path=self.relative,
            content=self.contract_bytes,
            descriptor_sha256="1" * 64,
        )
        rollback = rollback_grok_workspace_rule(
            workspace_root=positive,
            relative_path=self.relative,
            expected_content_sha256=self.content_sha,
            materialization_receipt=materialization,
        )
        descriptor = {
            "schema": DESCRIPTOR_SCHEMA,
            "target": "grok",
            "target_version": "0.2.111",
            "surface": "controller_proved_direct_and_cockpit_join",
            "qualification_authorized": False,
            "workspace_root": str(positive),
            "workspace_identity_sha256": "2" * 64,
            "direct_repository_root": str(positive),
            "cockpit_root": str(ordinary),
            "candidate_branch": "branch",
            "candidate_head": "3" * 40,
            "controller": "codex",
            "campaign_id": "campaign-1",
            "goal_fingerprint": "4" * 64,
            "executable_sha256": "5" * 64,
            "subscription_profile_root": str(self.profile),
            "artifact_relative_path": self.relative,
            "descriptor_sha256": "1" * 64,
        }
        with self.assertRaisesRegex(
            UnsupportedError, "filesystem absence alone|paired subscription-backed"
        ):
            build_grok_terminal_workspace_isolation(
                descriptor=descriptor,
                materialization=materialization,
                matched_control=precheck,
                rollback=rollback,
                startup_cwd=positive,
                controller_contract_sha256="7" * 64,
                instruction_manifest_sha256="8" * 64,
                executable_sha256="5" * 64,
                subscription_profile_sha256="9" * 64,
                launch_plan_sha256="a" * 64,
                observed_model="unavailable",
                halt_receipt_sha256="b" * 64,
            )
        # Even a forged no_bleed_verified=True on the precheck schema fails.
        forged = dict(precheck, no_bleed_verified=True)
        with self.assertRaisesRegex(
            UnsupportedError, "filesystem absence alone|paired subscription-backed"
        ):
            build_grok_terminal_workspace_isolation(
                descriptor=descriptor,
                materialization=materialization,
                matched_control=forged,
                rollback=rollback,
                startup_cwd=positive,
                controller_contract_sha256="7" * 64,
                instruction_manifest_sha256="8" * 64,
                executable_sha256="5" * 64,
                subscription_profile_sha256="9" * 64,
                launch_plan_sha256="a" * 64,
                observed_model="unavailable",
                halt_receipt_sha256="b" * 64,
            )
        # Paired-runtime schema without the runtime halt/attach hashes fails closed.
        incomplete_pair = {
            "schema": MATCHED_CONTROL_SCHEMA,
            "target": "grok",
            "target_version": "0.2.111",
            "positive_workspace_root": str(positive),
            "ordinary_workspace_root": str(ordinary),
            "positive_artifact_relative_path": self.relative,
            "positive_artifact_sha256": self.content_sha,
            "ordinary_artifact_absent": True,
            "workspace_identity_join_sha256": "2" * 64,
            "proof_strength": PAIRED_RUNTIME_PROOF,
            "no_bleed_verified": True,
            "activation_authorized": False,
            "launch_authorized": False,
            "qualification_authorized": False,
            "attestation_sha256": "c" * 64,
        }
        with self.assertRaisesRegex(ValidationError, "positive runtime halt|invalid"):
            build_grok_terminal_workspace_isolation(
                descriptor=descriptor,
                materialization=materialization,
                matched_control=incomplete_pair,
                rollback=rollback,
                startup_cwd=positive,
                controller_contract_sha256="7" * 64,
                instruction_manifest_sha256="8" * 64,
                executable_sha256="5" * 64,
                subscription_profile_sha256="9" * 64,
                launch_plan_sha256="a" * 64,
                observed_model="unavailable",
                halt_receipt_sha256="b" * 64,
            )

    def test_direct_and_cockpit_entries_join_same_workspace_identity(self) -> None:
        supervisor, candidate = _init_linked_pair(self.base / "repo-pair")
        descriptor = build_grok_entry_descriptor(
            workspace_root=candidate,
            cockpit_root=supervisor,
            controller="codex",
            campaign_id="campaign-1",
            goal_fingerprint="1" * 64,
            executable_sha256=GROK_EXECUTABLE_SHA256,
            subscription_profile_root=self.profile,
            artifact_relative_path=self.relative,
        )
        self.assertEqual(descriptor["schema"], DESCRIPTOR_SCHEMA)
        self.assertFalse(descriptor["qualification_authorized"])
        verified = validate_grok_entry_descriptor(
            descriptor,
            expected_controller="codex",
            expected_campaign_id="campaign-1",
            expected_goal_fingerprint="1" * 64,
            expected_executable_sha256=GROK_EXECUTABLE_SHA256,
            expected_subscription_profile_root=self.profile,
        )
        self.assertEqual(verified["descriptor_sha256"], descriptor["descriptor_sha256"])

    def test_binding_only_remains_non_promotable(self) -> None:
        require_source_only_grok_binding(
            {
                "schema": GROK_WORKSPACE_BINDING_SCHEMA,
                "state": GROK_WORKSPACE_BINDING_STATE,
                "activation_authorized": False,
                "launch_authorized": False,
                "qualification_authorized": False,
            }
        )
        with self.assertRaisesRegex(UnsupportedError, "cannot authorize"):
            require_source_only_grok_binding(
                {
                    "schema": GROK_WORKSPACE_BINDING_SCHEMA,
                    "state": GROK_WORKSPACE_BINDING_STATE,
                    "activation_authorized": True,
                    "launch_authorized": False,
                    "qualification_authorized": False,
                }
            )


class GrokPromotionFenceTests(unittest.TestCase):
    def test_public_qualify_is_nonpromotable_even_with_forged_isolation(self) -> None:
        import adapter_lab as puppet_adapter_lab

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            executable = root / GROK_RUNTIME_BASENAME
            executable.write_bytes(b"synthetic-grok")
            probe_mapping = _doctor_mapping(executable)
            mapping_path = root / "mapping.json"
            receipt_path = root / "receipt.json"
            out = root / "qualified.json"
            mapping_path.write_text(json.dumps(probe_mapping) + "\n", encoding="utf-8")
            receipt_path.write_text("{}\n", encoding="utf-8")
            terminal_workspace = {
                "schema": TERMINAL_SCHEMA,
                "terminal_state": "controller_verified_after_exact_halt",
                "descriptor_sha256": "1" * 64,
                "workspace_root": "/tmp/grok-candidate",
                "startup_cwd": "/tmp/grok-candidate",
                "artifact_relative_path": build_artifact_relative_path("c" * 64),
                "artifact_sha256": "c" * 64,
                "workspace_identity_sha256": "2" * 64,
                "matched_control_sha256": "3" * 64,
                "materialization_sha256": "4" * 64,
                "rollback_sha256": "5" * 64,
                "controller_contract_sha256": "6" * 64,
                "instruction_manifest_sha256": "7" * 64,
                "executable_sha256": "8" * 64,
                "subscription_profile_sha256": "9" * 64,
                "launch_plan_sha256": "a" * 64,
                "halt_receipt_sha256": "b" * 64,
                "observed_model": "unavailable",
            }
            receipt = {
                "target": "grok",
                "session_profile": "regular",
                "plane_activation": None,
                "workspace_isolation": terminal_workspace,
                "capabilities": [
                    "launch",
                    "send",
                    "status",
                    "wait",
                    "checkpoint",
                    "halt",
                ],
            }
            base = mock.Mock()
            base.raw = {
                "doctor_only": True,
                "target": "grok",
                "yolo_mapping": probe_mapping,
            }
            base.target = "grok"
            arguments = SimpleNamespace(
                manifest=root / "doctor.json",
                mapping=mapping_path,
                receipt=receipt_path,
                out=out,
            )
            with (
                mock.patch.object(
                    puppet_adapter_lab.AdapterManifest,
                    "from_path",
                    return_value=base,
                ),
                mock.patch.object(
                    puppet_adapter_lab,
                    "_verified_receipt",
                    return_value=receipt,
                ),
            ):
                with self.assertRaisesRegex(
                    UnsupportedError, "terminal paired-runtime"
                ):
                    puppet_adapter_lab._qualify(arguments)
            self.assertFalse(out.exists())

    def test_require_promotion_and_launch_helpers_fail_closed(self) -> None:
        with self.assertRaisesRegex(UnsupportedError, "non-promotable"):
            require_grok_qualification_promotion()
        with self.assertRaisesRegex(UnsupportedError, "fenced|paired"):
            require_grok_public_launch_authority()
        self.assertIn("non-promotable", GROK_QUALIFICATION_NONPROMOTABLE)
        self.assertIn("fenced", GROK_PUBLIC_LAUNCH_FENCED)
        self.assertIn("filesystem absence", GROK_NO_BLEED_FS_SHORTCUT_BLOCKER)

    def test_forged_ready_doctor_cannot_bypass_terminal_receipt(self) -> None:
        import puppet_lib.session as puppet_session

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            executable = root / GROK_RUNTIME_BASENAME
            executable.write_bytes(b"synthetic")
            proof = root / "proof"
            proof.mkdir()
            state = root / "state"
            state.mkdir()
            contract = SimpleNamespace(
                target="grok",
                fingerprint="c" * 64,
                session_profile="regular",
            )
            manifest = SimpleNamespace(
                fingerprint="d" * 64,
                verify_qualification=mock.Mock(
                    side_effect=UnsupportedError(
                        "terminal paired-runtime receipt required"
                    )
                ),
            )
            with (
                mock.patch.object(
                    puppet_session.Contract, "from_path", return_value=contract
                ),
                mock.patch.object(
                    puppet_session.AdapterManifest,
                    "from_path",
                    return_value=manifest,
                ),
                mock.patch.object(
                    puppet_session, "_authorization", return_value={}
                ),
                mock.patch.object(
                    puppet_session,
                    "_qualification_authority",
                    return_value={
                        "controller": "codex",
                        "campaign_id": "campaign",
                        "goal_fingerprint": "e" * 64,
                    },
                ),
                mock.patch.object(
                    puppet_session,
                    "doctor",
                    return_value={
                        "target": "grok",
                        "launch_ready": True,
                        "doctor_only": False,
                        "contract_fingerprint": contract.fingerprint,
                        "manifest_fingerprint": manifest.fingerprint,
                    },
                ),
            ):
                with self.assertRaisesRegex(
                    UnsupportedError, "terminal paired-runtime"
                ):
                    puppet_session.launch(
                        session="grok-fenced",
                        contract_path=root / "unused-contract.json",
                        manifest_path=root / "unused-manifest.json",
                        authorization_path=root / "unused-authorization.json",
                        proof_root=proof,
                        state_root=state,
                        supervisor_executable=executable,
                        prompt="must never launch",
                    )
            self.assertEqual(GROK_LAUNCH_AUTHORITY_BLOCKER.count("doctor-only"), 1)


class GrokProbeDescriptorFenceTests(unittest.TestCase):
    def test_probe_requires_positive_request_or_linked_ordinary_source(self) -> None:
        from puppet_lib import probe as probe_module

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            proof = root / "proof"
            proof.mkdir(mode=0o700)
            with self.assertRaisesRegex(
                UnsupportedError, "positive descriptor|linked ordinary"
            ):
                probe_module.run_probe(
                    target="grok",
                    profile=probe_module.PROBE_PROFILE,
                    session_profile="regular",
                    proof_root=proof,
                    manifest_path=root / "manifest.json",
                    mapping_path=root / "mapping.json",
                    authorization_path=root / "auth.json",
                    controller="codex",
                    goal_repo=root,
                    expected_campaign_id="c1",
                    expected_goal={
                        "repository": "r",
                        "commit": "a" * 40,
                        "path": "g.md",
                        "sha256": "b" * 64,
                    },
                )


if __name__ == "__main__":
    unittest.main()
