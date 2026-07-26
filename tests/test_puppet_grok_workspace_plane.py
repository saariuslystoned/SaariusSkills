from __future__ import annotations

import copy
import hashlib
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "puppet" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from puppet_lib.adapter_manifest import (  # noqa: E402
    AdapterManifest,
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
    MATCHED_CONTROL_SCHEMA,
    MATERIALIZATION_RECEIPT_SCHEMA,
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
    require_source_only_grok_binding,
    rollback_grok_workspace_rule,
    validate_grok_entry_descriptor,
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
        with self.assertRaisesRegex(IdentityError, "0.2.111 runtime basename"):
            grok_regular_launch_argv(self.base / "grok")

    def test_only_terminal_qualification_can_close_grok_mapping(self) -> None:
        mapping = _doctor_mapping(self.executable)
        qualified = grok_qualified_mapping(mapping)
        self.assertTrue(qualified["complete"])
        self.assertTrue(qualified["project_isolation_declared"])
        self.assertEqual(qualified["project_isolation_flags"], [])
        self.assertEqual(qualified["launch_argv"], mapping["launch_argv"])
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
        nonterminal = dict(workspace, terminal_state="preflight")
        with self.assertRaisesRegex(ValidationError, "not terminal"):
            grok_probe_mapping_from_qualified(
                qualified, workspace_isolation=nonterminal
            )
        drifted = copy.deepcopy(qualified)
        drifted["launch_argv"] = list(drifted["launch_argv"]) + ["--model", "x"]
        with self.assertRaisesRegex(IdentityError, "incomplete tuple|exact regular"):
            grok_probe_mapping_from_qualified(
                drifted, workspace_isolation=workspace
            )
        incomplete_declared = copy.deepcopy(mapping)
        incomplete_declared["project_isolation_declared"] = True
        with self.assertRaisesRegex(IdentityError, "incomplete tuple"):
            grok_qualified_mapping(incomplete_declared)

    def test_terminal_isolation_schema_is_canonical_without_live_root(self) -> None:
        missing = str(self.base / "missing-candidate")
        workspace = {
            "schema": TERMINAL_SCHEMA,
            "terminal_state": "controller_verified_after_exact_halt",
            "descriptor_sha256": "1" * 64,
            "workspace_root": missing,
            "startup_cwd": missing,
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
        self.assertEqual(validate_grok_workspace_isolation(workspace), workspace)
        self.assertEqual(validate_terminal_workspace_isolation(workspace), workspace)
        self.assertEqual(workspace_isolation_target(workspace), "grok")
        self.assertFalse(Path(missing).exists())
        for root in (
            "relative/candidate",
            str(self.base / "candidate") + "/",
            str(self.base / "candidate") + "\nignored",
            "//tmp/candidate",
        ):
            with self.subTest(root=repr(root)):
                with self.assertRaisesRegex(ValidationError, "normalized and absolute"):
                    validate_grok_workspace_isolation(
                        dict(workspace, workspace_root=root, startup_cwd=root)
                    )
        with self.assertRaisesRegex(ValidationError, "cwd binding"):
            validate_grok_workspace_isolation(
                dict(workspace, startup_cwd=str(self.base / "other"))
            )
        for model in ("", "grok-4", "self-reported-winner"):
            with self.subTest(model=model):
                with self.assertRaisesRegex(ValidationError, "observed model"):
                    validate_grok_workspace_isolation(
                        dict(workspace, observed_model=model)
                    )

    def test_create_only_materialize_matched_control_and_hash_guarded_rollback(
        self,
    ) -> None:
        positive = self.base / "positive"
        ordinary = self.base / "ordinary"
        positive.mkdir(mode=0o700)
        ordinary.mkdir(mode=0o700)
        positive.chmod(0o700)
        ordinary.chmod(0o700)
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
        self.assertFalse(materialization["activation_authorized"])
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
        wrong_name = build_artifact_relative_path("d" * 64)
        with self.assertRaisesRegex(IdentityError, "filename does not match"):
            materialize_grok_workspace_rule(
                workspace_root=ordinary,
                relative_path=wrong_name,
                content=self.contract_bytes,
                descriptor_sha256="c" * 64,
            )
        matched = attest_grok_matched_control(
            positive_workspace_root=positive,
            ordinary_workspace_root=ordinary,
            positive_relative_path=self.relative,
            positive_content_sha256=self.content_sha,
            workspace_identity_join_sha256="e" * 64,
        )
        self.assertEqual(matched["schema"], MATCHED_CONTROL_SCHEMA)
        self.assertTrue(matched["no_bleed_verified"])
        self.assertFalse(matched["qualification_authorized"])
        bleed = ordinary / ".grok" / "rules"
        bleed.mkdir(parents=True)
        (bleed / Path(self.relative).name).write_bytes(self.contract_bytes)
        with self.assertRaisesRegex(IdentityError, "instruction bleed|Puppet"):
            attest_grok_matched_control(
                positive_workspace_root=positive,
                ordinary_workspace_root=ordinary,
                positive_relative_path=self.relative,
                positive_content_sha256=self.content_sha,
                workspace_identity_join_sha256="e" * 64,
            )
        (bleed / Path(self.relative).name).unlink()
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
        self.assertTrue(rollback["absent_after"])
        self.assertFalse(rollback["qualification_authorized"])
        artifact = positive.joinpath(*self.relative.split("/"))
        self.assertFalse(artifact.exists())
        second = rollback_grok_workspace_rule(
            workspace_root=positive,
            relative_path=self.relative,
            expected_content_sha256=self.content_sha,
        )
        self.assertFalse(second["removed"])
        self.assertTrue(second["absent_after"])

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
        self.assertEqual(descriptor["target"], "grok")
        self.assertEqual(descriptor["direct_repository_root"], str(candidate))
        self.assertEqual(descriptor["workspace_root"], str(candidate))
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
        forged = dict(descriptor, controller="claude")
        forged["descriptor_sha256"] = sha256_bytes(
            canonical_json_bytes(
                {name: forged[name] for name in forged if name != "descriptor_sha256"}
            )
        )
        with self.assertRaisesRegex(IdentityError, "authority changed"):
            validate_grok_entry_descriptor(
                forged,
                expected_controller="codex",
                expected_campaign_id="campaign-1",
                expected_goal_fingerprint="1" * 64,
                expected_executable_sha256=GROK_EXECUTABLE_SHA256,
                expected_subscription_profile_root=self.profile,
            )

    def test_binding_only_and_activation_only_remain_non_promotable(self) -> None:
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
        with self.assertRaisesRegex(UnsupportedError, "cannot authorize"):
            require_source_only_grok_binding(
                {
                    "schema": GROK_WORKSPACE_BINDING_SCHEMA,
                    "state": "promoted",
                    "activation_authorized": False,
                    "launch_authorized": False,
                    "qualification_authorized": False,
                }
            )

    def test_terminal_isolation_requires_matched_control_and_rollback(self) -> None:
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
        matched = attest_grok_matched_control(
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
        terminal = build_grok_terminal_workspace_isolation(
            descriptor=descriptor,
            materialization=materialization,
            matched_control=matched,
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
        self.assertEqual(terminal["schema"], TERMINAL_SCHEMA)
        self.assertEqual(terminal["observed_model"], "unavailable")
        self.assertEqual(validate_grok_workspace_isolation(terminal), terminal)
        bad_matched = dict(matched, no_bleed_verified=False)
        with self.assertRaisesRegex(ValidationError, "matched ordinary control"):
            build_grok_terminal_workspace_isolation(
                descriptor=descriptor,
                materialization=materialization,
                matched_control=bad_matched,
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


class GrokPublicQualifyPathTests(unittest.TestCase):
    def test_public_qualify_closes_mapping_only_with_terminal_isolation(self) -> None:
        import puppet_lib.grok_workspace_plane as grok_workspace_module
        import adapter_lab as puppet_adapter_lab
        from types import SimpleNamespace

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            executable = root / GROK_RUNTIME_BASENAME
            executable.write_bytes(b"synthetic-grok")
            probe_mapping = _doctor_mapping(executable)
            raw = {
                "schema_version": 2,
                "target": "grok",
                "generated_at": "2026-07-26T00:00:00Z",
                "platform": {
                    "system": "Darwin",
                    "release": "25.5.0",
                    "machine": "arm64",
                },
                "executable": {
                    "requested_path": str(executable),
                    "resolved_path": str(executable),
                    "device": 1,
                    "inode": 2,
                    "size": executable.stat().st_size,
                    "mtime_ns": 3,
                    "sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
                    "version_sha256": "1" * 64,
                    "help_sha256": "2" * 64,
                },
                "execution": {
                    "transition": "direct",
                    "runtime_executable": {
                        "path": str(executable),
                        "device": 1,
                        "inode": 2,
                        "size": executable.stat().st_size,
                        "mtime_ns": 3,
                        "sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
                    },
                    "transient_executables": [],
                    "support_files": [],
                    "settle_timeout_seconds": 2.0,
                    "execution_fingerprint": "3" * 64,
                },
                "adapter_fingerprint": "4" * 64,
                "protocol_fingerprint": "5" * 64,
                "yolo_mapping": probe_mapping,
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
            # AdapterManifest.from_dict validates heavily; keep this test focused on
            # the qualify transition by mocking the manifest load and receipt path.
            manifest_path = root / "doctor.json"
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
                "executable_sha256": raw["executable"]["sha256"],
                "subscription_profile_sha256": "8" * 64,
                "launch_plan_sha256": "9" * 64,
                "halt_receipt_sha256": "a" * 64,
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
            base.raw = raw
            base.target = "grok"
            arguments = SimpleNamespace(
                manifest=manifest_path,
                mapping=mapping_path,
                receipt=receipt_path,
                out=out,
            )
            qualified_mapping = grok_qualified_mapping(probe_mapping)

            def _fake_from_dict(value):
                instance = mock.Mock()
                instance.raw = value
                instance.target = value["target"]
                instance.fingerprint = "q" * 64

                def _save(path):
                    Path(path).write_text(
                        json.dumps(value) + "\n", encoding="utf-8"
                    )

                instance.save.side_effect = _save
                instance.verify_qualification.return_value = receipt
                return instance

            with (
                mock.patch.object(
                    puppet_adapter_lab.AdapterManifest,
                    "from_path",
                    return_value=base,
                ),
                mock.patch.object(
                    puppet_adapter_lab.AdapterManifest,
                    "from_dict",
                    side_effect=_fake_from_dict,
                ),
                mock.patch.object(
                    puppet_adapter_lab,
                    "_verified_receipt",
                    return_value=receipt,
                ),
            ):
                result = puppet_adapter_lab._qualify(arguments)
            self.assertTrue(result["ok"])
            saved = json.loads(out.read_text(encoding="utf-8"))
            self.assertFalse(saved["doctor_only"])
            self.assertTrue(saved["yolo_mapping"]["complete"])
            self.assertTrue(saved["yolo_mapping"]["project_isolation_declared"])
            self.assertEqual(saved["yolo_mapping"]["launch_argv"], qualified_mapping["launch_argv"])

            arguments_missing = SimpleNamespace(
                manifest=manifest_path,
                mapping=mapping_path,
                receipt=receipt_path,
                out=root / "blocked.json",
            )
            blocked_receipt = dict(receipt, workspace_isolation=None)
            with (
                mock.patch.object(
                    puppet_adapter_lab.AdapterManifest,
                    "from_path",
                    return_value=base,
                ),
                mock.patch.object(
                    puppet_adapter_lab,
                    "_verified_receipt",
                    return_value=blocked_receipt,
                ),
            ):
                with self.assertRaisesRegex(
                    UnsupportedError, "terminal controller-verified workspace isolation"
                ):
                    puppet_adapter_lab._qualify(arguments_missing)


class GrokSessionFenceTests(unittest.TestCase):
    def test_doctor_only_remains_fenced_qualified_path_not_hard_blocked(self) -> None:
        import puppet_lib.session as puppet_session
        from types import SimpleNamespace

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            executable = root / GROK_RUNTIME_BASENAME
            executable.write_bytes(b"synthetic")
            candidate = root / "candidate"
            candidate.mkdir()
            proof = root / "proof"
            proof.mkdir()
            state = root / "state"
            state.mkdir()
            contract = SimpleNamespace(
                target="grok",
                repo=candidate,
                branch="codex/grok-fenced",
                session_profile="regular",
                requested_model=None,
                requested_effort=None,
                fingerprint="a" * 64,
            )
            doctor_manifest = SimpleNamespace(
                target="grok",
                raw={
                    "executable": {
                        "resolved_path": str(executable),
                        "sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
                    },
                    "yolo_mapping": {"complete": True},
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
                },
                fingerprint="b" * 64,
            )
            population = {"candidates": [], "matching": [], "mismatched": []}
            with (
                mock.patch.object(
                    puppet_session.Contract, "from_path", return_value=contract
                ),
                mock.patch.object(
                    puppet_session.AdapterManifest,
                    "from_path",
                    return_value=doctor_manifest,
                ),
                mock.patch.object(
                    puppet_session,
                    "_authorization",
                    return_value={"authorization": {}},
                ),
                mock.patch.object(
                    puppet_session,
                    "_workspace_snapshot",
                    return_value={
                        "branch": contract.branch,
                        "head": "c" * 40,
                        "tree": "d" * 40,
                        "dirty": False,
                    },
                ),
                mock.patch.object(
                    puppet_session, "_grok_population", return_value=population
                ),
                mock.patch.object(
                    puppet_session.TmuxController, "available", return_value=True
                ),
            ):
                report = puppet_session.doctor(
                    contract_path=root / "contract.json",
                    manifest_path=root / "manifest.json",
                    authorization_path=root / "authorization.json",
                    proof_root=proof,
                    state_root=state,
                )
            self.assertFalse(report["launch_ready"])
            self.assertIn(GROK_LAUNCH_AUTHORITY_BLOCKER, report["blockers"])

            with (
                mock.patch.object(
                    puppet_session.Contract, "from_path", return_value=contract
                ),
                mock.patch.object(
                    puppet_session,
                    "doctor",
                    return_value={"target": "grok", "launch_ready": False},
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


if __name__ == "__main__":
    unittest.main()
