from __future__ import annotations

import copy
import hashlib
import json
import os
import stat
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "puppet" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import puppet_lib.plane_activation as activation_module  # noqa: E402
from puppet_lib.adapter_manifest import AdapterManifest  # noqa: E402
from puppet_lib.errors import (  # noqa: E402
    ConflictError,
    IdentityError,
    UnsupportedError,
    ValidationError,
)
from puppet_lib.instruction_planes import descriptor_fingerprint  # noqa: E402
from puppet_lib.instructions import compile_instruction_wrapper  # noqa: E402
from puppet_lib.plane_activation import (  # noqa: E402
    INTENT_FILENAME,
    RECEIPT_FILENAME,
    load_activation_plan,
    materialize_activation,
    plan_activation,
    recover_activation,
    rollback_activation,
    verify_activation,
)
from puppet_lib.safety import canonical_json_bytes, sha256_bytes  # noqa: E402
from puppet_lib.profiles import (  # noqa: E402
    PROMPT_TRANSPORT,
    SUBMIT_SETTLE_SECONDS,
    default_session_profile,
    session_profiles_for,
    startup_settle_seconds_for,
)


ADAPTER_SHA256 = "a" * 64
VERSION_OBSERVATION_SHA256 = "b" * 64


def _descriptor() -> dict:
    return {
        "schema": "puppet.instruction-plane/v1",
        "descriptor_id": "claude-native-qualification",
        "target": {
            "harness": "claude",
            "version": "2.1.215",
            "adapter_manifest_sha256": ADAPTER_SHA256,
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
        "assertions": ["claude_native_instruction_seen"],
        "blockers": ["live_qualification_not_yet_run"],
    }

def _adapter_manifest(receipt_path: Path) -> dict:
    executable = Path(sys.executable).resolve()
    executable_details = executable.stat()
    executable_hash = hashlib.sha256(executable.read_bytes()).hexdigest()
    raw = {
        "schema_version": 1,
        "target": "claude",
        "generated_at": "2026-07-22T03:00:00Z",
        "platform": {
            "system": "Darwin",
            "release": "test",
            "machine": "test",
        },
        "executable": {
            "requested_path": str(executable),
            "resolved_path": str(executable),
            "sha256": executable_hash,
            "version_sha256": VERSION_OBSERVATION_SHA256,
            "help_sha256": "c" * 64,
            "device": executable_details.st_dev,
            "inode": executable_details.st_ino,
            "size": executable_details.st_size,
            "mtime_ns": executable_details.st_mtime_ns,
        },
        "adapter_fingerprint": ADAPTER_SHA256,
        "protocol_fingerprint": "d" * 64,
        "yolo_mapping": {
            "complete": True,
            "launch_argv": [str(executable)],
            "permission_declared": True,
            "permission_flags": ["--test-owned-process"],
            "prompt_transport": PROMPT_TRANSPORT,
            "prompt_transport_declared": True,
            "sandbox_disable_declared": True,
            "sandbox_flags": [],
            "project_isolation_declared": True,
            "project_isolation_flags": [],
            "session_profiles": session_profiles_for("claude"),
            "session_profiles_declared": True,
            "startup_settle_seconds": startup_settle_seconds_for("claude"),
            "submit_settle_seconds": SUBMIT_SETTLE_SECONDS,
        },
        "capabilities": {
            "launch": "controller_verified",
            "send": "controller_verified",
            "status": "controller_verified",
            "wait": "controller_verified",
            "checkpoint": "controller_verified",
            "resume": "unsupported",
            "halt": "controller_verified",
        },
        "doctor_only": False,
        "qualification": {
            "receipt_path": str(receipt_path),
            "receipt_sha256": "e" * 64,
            "session_profile": default_session_profile("claude"),
        },
    }
    return AdapterManifest.from_dict(raw).raw



class PlaneActivationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.workspace = self.base / "workspace"
        self.config = self.base / "config"
        self.ephemeral = self.base / "ephemeral"
        self.transaction = self.base / "transaction"
        self.qualification_receipt = self.base / "qualification-receipt.json"
        for path in (self.workspace, self.config, self.ephemeral, self.transaction):
            path.mkdir(mode=0o700)
            path.chmod(0o700)
        self.body_marker = "PUPPET_NATIVE_BODY_MUST_NOT_ENTER_JSON_9f31"
        self.compiled = compile_instruction_wrapper(
            target="claude",
            task="Perform one bounded qualification. " + self.body_marker,
            contract_identity={"contract_id": "claude-native-contract"},
            workspace_identity={"workspace_id": "claude-native-workspace"},
            run_identity={"run_id": "claude-native-run"},
        )
        self.descriptor = _descriptor()
        self.adapter_manifest = _adapter_manifest(self.qualification_receipt)
        self.plan = self._plan()

    def _plan(self, descriptor=None, **overrides):
        arguments = {
            "instruction_manifest": self.compiled.manifest,
            "adapter_manifest": self.adapter_manifest,
            "effective_contract": self.compiled.rendered,
            "workspace_root": self.workspace,
            "ephemeral_root": self.ephemeral,
            "transaction_root": self.transaction,
            "config_root": self.config,
        }
        arguments.update(overrides)
        return plan_activation(descriptor or self.descriptor, **arguments)

    def _activate(self):
        return materialize_activation(
            self.plan, effective_contract=self.compiled.rendered
        )

    def assert_artifact_preserved(self):
        self.assertTrue(
            self.plan.artifact_path.exists() or self.plan.artifact_path.is_symlink()
        )

    def test_planning_is_pure_body_free_and_binds_all_authorities(self):
        before = {
            path: (path.stat().st_dev, path.stat().st_ino, path.stat().st_nlink)
            for path in (self.workspace, self.config, self.ephemeral, self.transaction)
        }
        second = self._plan()
        after = {
            path: (path.stat().st_dev, path.stat().st_ino, path.stat().st_nlink)
            for path in (self.workspace, self.config, self.ephemeral, self.transaction)
        }
        self.assertEqual(before, after)
        self.assertEqual(list(self.ephemeral.iterdir()), [])
        self.assertEqual(list(self.transaction.iterdir()), [])
        self.assertEqual(second.to_dict(), self.plan.to_dict())

        raw = self.plan.raw
        serialized = canonical_json_bytes(raw)
        self.assertNotIn(self.body_marker.encode(), serialized)
        self.assertNotIn(self.compiled.rendered, serialized)
        self.assertEqual(
            raw["descriptor_sha256"], descriptor_fingerprint(self.descriptor)
        )
        self.assertEqual(
            raw["instruction_manifest_sha256"],
            sha256_bytes(activation_module._canonical_json_with_newline(self.compiled.manifest)),
        )
        self.assertEqual(
            raw["effective_contract_fingerprint"],
            self.compiled.manifest["effective_contract_fingerprint"],
        )
        self.assertEqual(
            raw["effective_contract_sha256"], sha256_bytes(self.compiled.rendered)
        )
        self.assertEqual(raw["adapter_manifest_sha256"], ADAPTER_SHA256)
        self.assertEqual(raw["version_observation_sha256"], VERSION_OBSERVATION_SHA256)
        self.assertEqual(raw["created_directory_paths"], [])
        self.assertEqual(
            raw["launch"]["argv"],
            ["--append-system-prompt-file", str(self.plan.artifact_path)],
        )
        self.assertEqual(
            raw["launch"]["env"],
            [
                {
                    "name": "CLAUDE_CODE_DISABLE_AUTO_MEMORY",
                    "value_ref": "true_literal",
                },
                {"name": "CLAUDE_CONFIG_DIR", "value_ref": "config_root_path"},
            ],
        )
        self.assertEqual(
            raw["launch_plan_sha256"], sha256_bytes(canonical_json_bytes(raw["launch"]))
        )

    def test_success_intent_precedes_write_and_rollback_is_separate_and_idempotent(
        self,
    ):
        original_writer = activation_module._write_contract_bytes

        def observing_writer(descriptor, payload):
            self.assertTrue(self.plan.intent_path.is_file())
            self.assertFalse(self.plan.receipt_path.exists())
            return original_writer(descriptor, payload)

        with mock.patch.object(
            activation_module, "_write_contract_bytes", side_effect=observing_writer
        ):
            receipt = self._activate()

        self.assertEqual(self.plan.artifact_path.read_bytes(), self.compiled.rendered)
        details = self.plan.artifact_path.stat()
        self.assertEqual(stat.S_IMODE(details.st_mode), 0o600)
        self.assertEqual(details.st_uid, os.getuid())
        self.assertEqual(details.st_nlink, 1)
        self.assertEqual(
            {item.name for item in self.transaction.iterdir()},
            {INTENT_FILENAME, RECEIPT_FILENAME},
        )
        self.assertEqual(load_activation_plan(self.transaction), self.plan)
        self.assertEqual(verify_activation(self.plan), receipt)
        self.assertEqual(recover_activation(self.transaction).state, "active")
        self.assertEqual(self._activate(), receipt)

        self.assertTrue(self.plan.intent_path.exists())
        self.assertTrue(self.plan.receipt_path.exists())

        original = activation_module._persist_immutable_json

        def fail_rollback_receipt(root_descriptor, name, value, *, label):
            if name == activation_module.ROLLBACK_FILENAME:
                raise OSError("injected rollback receipt failure")
            return original(root_descriptor, name, value, label=label)

        with mock.patch.object(
            activation_module,
            "_persist_immutable_json",
            side_effect=fail_rollback_receipt,
        ):
            with self.assertRaises(OSError):
                rollback_activation(self.plan)
        self.assertFalse(self.plan.rollback_receipt_path.exists())
        self.assertTrue(self.plan.rollback_intent_path.exists())
        self.assertFalse(self.plan.artifact_path.exists())
        self.assertEqual(list(self.ephemeral.iterdir()), [])
        recovery = recover_activation(self.transaction)
        self.assertEqual(recovery.state, "rolled_back")
        rollback = rollback_activation(self.plan)
        self.assertEqual(rollback["artifact_state"], "absent")
        self.assertEqual(recovery.rollback_receipt, rollback)
        self.assertEqual(rollback_activation(self.plan), rollback)

        with self.assertRaises(ConflictError):
            self._activate()

    def test_existing_root_content_is_a_collision_and_is_never_deleted(self):
        collision = self.ephemeral / "occupied.txt"
        collision.write_text("operator-owned", encoding="utf-8")
        with self.assertRaises(ConflictError):
            self._activate()
        self.assertEqual(collision.read_text(encoding="utf-8"), "operator-owned")
        self.assertTrue(self.plan.intent_path.exists())
        self.assertFalse(self.plan.receipt_path.exists())
        with self.assertRaises(ConflictError):
            recover_activation(self.transaction)

    def test_private_root_requirements_and_root_symlinks_are_rejected(self):
        self.ephemeral.chmod(0o755)
        with self.assertRaises(IdentityError):
            self._plan()
        self.ephemeral.chmod(0o700)
        self.transaction.chmod(0o755)
        with self.assertRaises(IdentityError):
            self._plan()
        self.transaction.chmod(0o700)

        alternate = self.base / "alternate"
        alternate.mkdir(mode=0o700)
        root_link = self.base / "root-link"
        root_link.symlink_to(alternate, target_is_directory=True)
        with self.assertRaises(IdentityError):
            self._plan(ephemeral_root=root_link)
        transaction_link = self.base / "transaction-link"
        transaction_link.symlink_to(alternate, target_is_directory=True)
        with self.assertRaises(IdentityError):
            self._plan(transaction_root=transaction_link)

    def test_config_root_overlap_is_rejected(self):
        with self.assertRaises(ConflictError):
            self._plan(config_root=self.workspace)

    def test_activation_roots_reject_pairwise_overlap_and_ancestry(self):
        base_template = {
            "workspace": "workspace",
            "ephemeral": "ephemeral",
            "transaction": "transaction",
            "config": "config",
        }
        for left, right in (
            ("workspace", "ephemeral"),
            ("workspace", "transaction"),
            ("workspace", "config"),
            ("ephemeral", "transaction"),
            ("ephemeral", "config"),
            ("transaction", "config"),
        ):
            for relation in ("equal", "left_is_parent", "right_is_parent"):
                with TemporaryDirectory() as raw:
                    base = Path(raw)
                    assigned = {}
                    for key, name in base_template.items():
                        candidate = base / name
                        candidate.mkdir(mode=0o700)
                        assigned[key] = candidate

                    if relation == "equal":
                        assigned[right] = assigned[left]
                    elif relation == "left_is_parent":
                        assigned[right] = assigned[left] / f"{right}-child"
                        assigned[right].mkdir(parents=True, mode=0o700)
                    else:
                        assigned[left] = assigned[right] / f"{left}-child"
                        assigned[left].mkdir(parents=True, mode=0o700)

                    with self.assertRaises(
                        ConflictError,
                        msg=f"{left}-{right}-{relation} should be rejected",
                    ):
                        self._plan(
                            workspace_root=assigned["workspace"],
                            ephemeral_root=assigned["ephemeral"],
                            transaction_root=assigned["transaction"],
                            config_root=assigned["config"],
                        )

    def test_fd_walk_rejects_parent_symlink(self):
        outside = self.base / "outside-directory"
        outside.mkdir(mode=0o700)
        (self.ephemeral / "linked-parent").symlink_to(outside, target_is_directory=True)
        root_descriptor = os.open(
            self.ephemeral,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
        )
        try:
            with self.assertRaises(IdentityError):
                activation_module._open_parent_from_root(
                    root_descriptor, ("linked-parent",)
                )
        finally:
            os.close(root_descriptor)
        self.assertTrue((self.ephemeral / "linked-parent").is_symlink())

    def test_artifact_leaf_symlink_collision_is_never_followed_or_deleted(self):
        outside = self.base / "outside.txt"
        outside.write_text("outside-owned", encoding="utf-8")
        self.plan.artifact_path.symlink_to(outside)
        with self.assertRaises(ConflictError):
            self._activate()
        self.assertTrue(self.plan.artifact_path.is_symlink())
        self.assertEqual(outside.read_text(encoding="utf-8"), "outside-owned")

    def test_root_workspace_and_transaction_replacement_are_detected(self):
        original_ephemeral = self.base / "original-ephemeral"
        self.ephemeral.rename(original_ephemeral)
        self.ephemeral.mkdir(mode=0o700)
        with self.assertRaises(IdentityError):
            self._activate()
        self.assertEqual(list(self.ephemeral.iterdir()), [])
        self.assertEqual(list(original_ephemeral.iterdir()), [])

        # A fresh fixture proves workspace and transaction binding independently.
        with TemporaryDirectory() as raw:
            base = Path(raw)
            workspace = base / "workspace"
            ephemeral = base / "ephemeral"
            transaction = base / "transaction"
            config = base / "config"
            for path in (workspace, ephemeral, transaction, config):
                path.mkdir(mode=0o700)
            plan = self._plan(
                workspace_root=workspace,
                ephemeral_root=ephemeral,
                transaction_root=transaction,
                config_root=config,
            )
            original_workspace = base / "original-workspace"
            workspace.rename(original_workspace)
            workspace.mkdir(mode=0o700)
            with self.assertRaises(IdentityError):
                materialize_activation(plan, effective_contract=self.compiled.rendered)
            self.assertEqual(list(ephemeral.iterdir()), [])
            self.assertEqual(list(transaction.iterdir()), [])

        with TemporaryDirectory() as raw:
            base = Path(raw)
            workspace = base / "workspace"
            ephemeral = base / "ephemeral"
            transaction = base / "transaction"
            config = base / "config"
            for path in (workspace, ephemeral, transaction, config):
                path.mkdir(mode=0o700)
            plan = self._plan(
                workspace_root=workspace,
                ephemeral_root=ephemeral,
                transaction_root=transaction,
                config_root=config,
            )
            original_transaction = base / "original-transaction"
            transaction.rename(original_transaction)
            transaction.mkdir(mode=0o700)
            with self.assertRaises(IdentityError):
                materialize_activation(plan, effective_contract=self.compiled.rendered)
            self.assertEqual(list(ephemeral.iterdir()), [])

    def test_root_replacement_after_receipt_blocks_verify_and_rollback(self):
        self._activate()
        original = self.base / "original-active-root"
        self.ephemeral.rename(original)
        self.ephemeral.mkdir(mode=0o700)
        with self.assertRaises(IdentityError):
            verify_activation(self.plan)
        with self.assertRaises(IdentityError):
            rollback_activation(self.plan)
        self.assertTrue((original / "puppet-instructions.md").exists())
        self.assertEqual(list(self.ephemeral.iterdir()), [])

    def test_body_and_hash_drift_blocks_rollback_without_deletion(self):
        self._activate()
        changed = b"X" * len(self.compiled.rendered)
        self.plan.artifact_path.write_bytes(changed)
        self.plan.artifact_path.chmod(0o600)
        with self.assertRaises(IdentityError):
            verify_activation(self.plan)
        with self.assertRaises(IdentityError):
            rollback_activation(self.plan)
        self.assertEqual(self.plan.artifact_path.read_bytes(), changed)

    def test_mode_drift_blocks_rollback_without_deletion(self):
        self._activate()
        self.plan.artifact_path.chmod(0o644)
        with self.assertRaises(IdentityError):
            verify_activation(self.plan)
        with self.assertRaises(IdentityError):
            rollback_activation(self.plan)
        self.assert_artifact_preserved()

    def test_inode_replacement_with_same_body_blocks_rollback(self):
        self._activate()
        original_inode = self.plan.artifact_path.stat().st_ino
        self.plan.artifact_path.unlink()
        self.plan.artifact_path.write_bytes(self.compiled.rendered)
        self.plan.artifact_path.chmod(0o600)
        self.assertNotEqual(self.plan.artifact_path.stat().st_ino, original_inode)
        with self.assertRaises(IdentityError):
            verify_activation(self.plan)
        with self.assertRaises(IdentityError):
            rollback_activation(self.plan)
        self.assert_artifact_preserved()

    def test_symlink_replacement_after_receipt_blocks_rollback(self):
        self._activate()
        outside = self.base / "replacement-body"
        outside.write_bytes(self.compiled.rendered)
        outside.chmod(0o600)
        self.plan.artifact_path.unlink()
        self.plan.artifact_path.symlink_to(outside)
        with self.assertRaises(IdentityError):
            verify_activation(self.plan)
        with self.assertRaises(IdentityError):
            rollback_activation(self.plan)
        self.assertTrue(self.plan.artifact_path.is_symlink())
        self.assertEqual(outside.read_bytes(), self.compiled.rendered)

    def test_nlink_drift_blocks_rollback_without_deleting_either_link(self):
        self._activate()
        second_link = self.base / "second-link"
        os.link(self.plan.artifact_path, second_link)
        self.assertEqual(self.plan.artifact_path.stat().st_nlink, 2)
        with self.assertRaises(IdentityError):
            verify_activation(self.plan)
        with self.assertRaises(IdentityError):
            rollback_activation(self.plan)
        self.assertTrue(self.plan.artifact_path.exists())
        self.assertTrue(second_link.exists())

    def test_contract_write_failure_cleans_exact_artifact_and_can_retry(self):
        def fail_after_prefix(descriptor, payload):
            os.write(descriptor, payload[:17])
            raise OSError("injected contract write failure")

        with mock.patch.object(
            activation_module,
            "_write_contract_bytes",
            side_effect=fail_after_prefix,
        ):
            with self.assertRaises(OSError):
                self._activate()
        self.assertEqual(list(self.ephemeral.iterdir()), [])
        self.assertTrue(self.plan.intent_path.exists())
        self.assertFalse(self.plan.receipt_path.exists())
        self.assertEqual(recover_activation(self.transaction).state, "prepared")
        receipt = self._activate()
        self.assertEqual(verify_activation(self.plan), receipt)

    def test_receipt_failure_cleans_artifact_and_can_retry_from_intent(self):
        original = activation_module._persist_immutable_json

        def fail_receipt(root_descriptor, name, value, *, label):
            if name == RECEIPT_FILENAME:
                raise OSError("injected receipt failure")
            return original(root_descriptor, name, value, label=label)

        with mock.patch.object(
            activation_module,
            "_persist_immutable_json",
            side_effect=fail_receipt,
        ):
            with self.assertRaises(OSError):
                self._activate()
        self.assertEqual(list(self.ephemeral.iterdir()), [])
        self.assertTrue(self.plan.intent_path.exists())
        self.assertFalse(self.plan.receipt_path.exists())
        self.assertEqual(recover_activation(self.transaction).state, "prepared")
        self.assertEqual(self._activate(), verify_activation(self.plan))

    def test_partial_receipt_write_is_unlinked_and_artifact_is_cleaned(self):
        original = activation_module._write_all

        def fail_receipt_write(descriptor, payload):
            if activation_module.RECEIPT_SCHEMA.encode() in payload:
                os.write(descriptor, payload[:23])
                raise OSError("injected partial receipt write")
            return original(descriptor, payload)

        with mock.patch.object(
            activation_module, "_write_all", side_effect=fail_receipt_write
        ):
            with self.assertRaises(OSError):
                self._activate()
        self.assertFalse(self.plan.receipt_path.exists())
        self.assertEqual(list(self.ephemeral.iterdir()), [])
        self.assertEqual(recover_activation(self.transaction).state, "prepared")

    def test_post_commit_verification_failure_never_cleans_receipted_artifact(self):
        original = activation_module._verify_active_with_root
        calls = 0

        def fail_second_verification(plan, receipt):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise IdentityError("injected post-commit verification failure")
            return original(plan, receipt)

        with mock.patch.object(
            activation_module,
            "_verify_active_with_root",
            side_effect=fail_second_verification,
        ):
            with self.assertRaises(IdentityError):
                self._activate()
        self.assertTrue(self.plan.intent_path.exists())
        self.assertTrue(self.plan.receipt_path.exists())
        self.assert_artifact_preserved()
        self.assertEqual(recover_activation(self.transaction).state, "active")

    def test_receipt_mismatch_refuses_rollback_and_preserves_artifact(self):
        self._activate()
        receipt = json.loads(self.plan.receipt_path.read_text(encoding="utf-8"))
        receipt["artifact"]["inode"] += 1
        self.plan.receipt_path.write_text(
            json.dumps(receipt, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        self.plan.receipt_path.chmod(0o600)
        with self.assertRaises(IdentityError):
            rollback_activation(self.plan)
        self.assert_artifact_preserved()

    def test_recovery_fails_closed_when_artifact_exists_without_receipt(self):
        self._activate()
        self.plan.receipt_path.unlink()
        with self.assertRaises((ConflictError, IdentityError)):
            recover_activation(self.transaction)
        with self.assertRaises(ConflictError):
            rollback_activation(self.plan)
        self.assert_artifact_preserved()

    def test_missing_artifact_and_root_mode_drift_are_blockers_not_cleanup_authority(
        self,
    ):
        self._activate()
        self.plan.artifact_path.unlink()
        with self.assertRaises(IdentityError):
            verify_activation(self.plan)
        with self.assertRaises(IdentityError):
            rollback_activation(self.plan)
        self.assertFalse(self.plan.rollback_receipt_path.exists())

        # Use a new transaction to show root metadata is independently bound.
        with TemporaryDirectory() as raw:
            base = Path(raw)
            workspace = base / "workspace"
            ephemeral = base / "ephemeral"
            transaction = base / "transaction"
            config = base / "config"
            for path in (workspace, ephemeral, transaction, config):
                path.mkdir(mode=0o700)
            plan = self._plan(
                workspace_root=workspace,
                ephemeral_root=ephemeral,
                transaction_root=transaction,
                config_root=config,
            )
            materialize_activation(plan, effective_contract=self.compiled.rendered)
            ephemeral.chmod(0o755)
            with self.assertRaises(IdentityError):
                verify_activation(plan)
            with self.assertRaises(IdentityError):
                rollback_activation(plan)
            self.assertTrue(plan.artifact_path.exists())

    def test_intent_symlink_collision_is_not_followed(self):
        outside = self.base / "outside-intent"
        outside.write_text("operator-owned", encoding="utf-8")
        self.plan.intent_path.symlink_to(outside)
        with self.assertRaises(IdentityError):
            self._activate()
        self.assertTrue(self.plan.intent_path.is_symlink())
        self.assertEqual(outside.read_text(encoding="utf-8"), "operator-owned")
        self.assertEqual(list(self.ephemeral.iterdir()), [])

    def test_authority_and_body_mismatches_fail_before_materialization(self):
        drifted_manifest = copy.deepcopy(self.adapter_manifest)
        drifted_manifest["adapter_fingerprint"] = "c" * 64
        with self.assertRaises(IdentityError):
            self._plan(adapter_manifest=drifted_manifest)
        drifted_version = copy.deepcopy(self.adapter_manifest)
        drifted_version["executable"]["version_sha256"] = "not-a-hash"
        with self.assertRaises(ValidationError):
            self._plan(adapter_manifest=drifted_version)
        with self.assertRaises(IdentityError):
            self._plan(effective_contract=self.compiled.rendered + b"changed")
        old_version = copy.deepcopy(self.descriptor)
        old_version["target"]["version"] = "2.1.214"
        with self.assertRaises(UnsupportedError):
            self._plan(old_version)
        self.assertEqual(list(self.ephemeral.iterdir()), [])
        self.assertEqual(list(self.transaction.iterdir()), [])

    def test_unsupported_descriptor_forms_remain_closed(self):
        cases = []

        candidate = copy.deepcopy(self.descriptor)
        candidate["materialize"][0]["artifact_id"] = "another_file"
        candidate["rollback"]["owned_artifacts"] = ["another_file"]
        candidate["launch_delta"]["argv"][1] = {"path_ref": "another_file"}
        cases.append(candidate)

        candidate = copy.deepcopy(self.descriptor)
        candidate["materialize"][0]["relative_path"] = "nested/contract.md"
        cases.append(candidate)

        candidate = copy.deepcopy(self.descriptor)
        candidate["materialize"][0]["root_ref"] = "workspace_root"
        cases.append(candidate)

        candidate = copy.deepcopy(self.descriptor)
        candidate["materialize"][0]["root_ref"] = "config_root"
        cases.append(candidate)

        candidate = copy.deepcopy(self.descriptor)
        candidate["materialize"][0]["write_mode"] = "patch_if_base_sha256"
        candidate["rollback"]["preimage_sha256"] = [
            {"artifact_id": "effective_contract_file", "sha256": "d" * 64}
        ]
        cases.append(candidate)

        candidate = copy.deepcopy(self.descriptor)
        candidate["materialize"].append(
            {
                "artifact_id": "second_file",
                "root_ref": "ephemeral_root",
                "relative_path": "second.md",
                "content_ref": "effective_contract",
                "write_mode": "create_only",
            }
        )
        candidate["rollback"]["owned_artifacts"].append("second_file")
        cases.append(candidate)

        candidate = copy.deepcopy(self.descriptor)
        candidate["launch_delta"]["env"] = []
        cases.append(candidate)

        candidate = copy.deepcopy(self.descriptor)
        candidate["status"]["activation"] = "qualified"
        cases.append(candidate)

        candidate = copy.deepcopy(self.descriptor)
        candidate["target"].update({"harness": "codex", "version": "0.145.0"})
        cases.append(candidate)

        for index, value in enumerate(cases):
            with self.subTest(index=index):
                with self.assertRaises((UnsupportedError, ValidationError)):
                    self._plan(value)
        self.assertEqual(list(self.ephemeral.iterdir()), [])
        self.assertEqual(list(self.transaction.iterdir()), [])

    def test_internal_reverse_walk_removes_only_exact_empty_created_directories(self):
        root_descriptor = os.open(
            self.ephemeral,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
        )
        try:
            parent, created = activation_module._open_or_create_parents(
                root_descriptor, ["first", "first/second"]
            )
            os.close(parent)
            created = [
                activation_module._directory_live_at(root_descriptor, path)
                for path in ("first", "first/second")
            ]
            activation_module._remove_created_directories(
                root_descriptor, created, compare_nlink=False
            )
            self.assertEqual(os.listdir(root_descriptor), [])
        finally:
            os.close(root_descriptor)

    def test_module_has_no_subprocess_or_recursive_path_cleanup(self):
        source = (SCRIPTS / "puppet_lib" / "plane_activation.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("import subprocess", source)
        self.assertNotIn("subprocess.", source)
        self.assertNotIn(".rglob(", source)
        self.assertNotIn("rmtree(", source)


if __name__ == "__main__":
    unittest.main()
