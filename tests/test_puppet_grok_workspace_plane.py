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
    MATCHED_CONTROL_PRECHECK_SCHEMA,
    MATCHED_CONTROL_SCHEMA,
    MATERIALIZATION_RECEIPT_SCHEMA,
    PAIRED_RUNTIME_PROOF,
    ROLLBACK_RECEIPT_SCHEMA,
    TERMINAL_SCHEMA,
    attest_grok_matched_control,
    build_artifact_relative_path,
    build_grok_entry_descriptor,
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
    verify_grok_workspace_rule,
)
from puppet_lib.safety import sha256_bytes  # noqa: E402


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
        )
        self.assertEqual(rollback["schema"], ROLLBACK_RECEIPT_SCHEMA)
        self.assertTrue(rollback["removed"])
        self.assertFalse(rollback["qualification_authorized"])
        artifact = positive.joinpath(*self.relative.split("/"))
        self.assertFalse(artifact.exists())

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
            "descriptor_sha256": "6" * 64,
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
                    UnsupportedError, "non-promotable|paired subscription-backed"
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

    def test_public_launch_remains_fenced_even_when_doctor_reports_ready(self) -> None:
        import puppet_lib.session as puppet_session

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            executable = root / GROK_RUNTIME_BASENAME
            executable.write_bytes(b"synthetic")
            proof = root / "proof"
            proof.mkdir()
            state = root / "state"
            state.mkdir()
            contract = SimpleNamespace(target="grok")
            with (
                mock.patch.object(
                    puppet_session.Contract, "from_path", return_value=contract
                ),
                mock.patch.object(
                    puppet_session,
                    "doctor",
                    return_value={
                        "target": "grok",
                        "launch_ready": True,
                        "doctor_only": False,
                    },
                ),
            ):
                with self.assertRaisesRegex(UnsupportedError, "doctor-only"):
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
    def test_probe_rejects_grok_workspace_descriptor_as_nonpromotable(self) -> None:
        from puppet_lib import probe as probe_module

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            descriptor = {
                "schema": DESCRIPTOR_SCHEMA,
                "target": "grok",
                "target_version": "0.2.111",
                "surface": "controller_proved_direct_and_cockpit_join",
                "qualification_authorized": False,
                "workspace_root": str(root),
                "workspace_identity_sha256": "1" * 64,
                "direct_repository_root": str(root),
                "cockpit_root": str(root),
                "candidate_branch": "main",
                "candidate_head": "2" * 40,
                "controller": "codex",
                "campaign_id": "c1",
                "goal_fingerprint": "3" * 64,
                "executable_sha256": "4" * 64,
                "subscription_profile_root": str(root / "profile"),
                "artifact_relative_path": build_artifact_relative_path("5" * 64),
                "descriptor_sha256": "6" * 64,
            }
            path = root / "descriptor.json"
            path.write_text(json.dumps(descriptor) + "\n", encoding="utf-8")
            proof = root / "proof"
            proof.mkdir(mode=0o700)
            with self.assertRaisesRegex(
                UnsupportedError, "non-promotable|paired subscription-backed"
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
                    plane_descriptor=path,
                )


if __name__ == "__main__":
    unittest.main()
