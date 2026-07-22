from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "puppet" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from puppet_lib.adapter_manifest import (  # noqa: E402
    ADAPTER_MANIFEST_SCHEMA_VERSION,
    BEHAVIOR_CAPABILITIES,
    AdapterManifest,
    build_execution_bundle,
)
from puppet_lib.cursor_workspace_plane import (  # noqa: E402
    BLOCKERS,
    CURSOR_ENTRYPOINT_SHA256,
    CURSOR_HELP_SHA256,
    CURSOR_LAUNCHER_SHA256,
    CURSOR_RUNTIME_SHA256,
    CURSOR_VERSION,
    CURSOR_VERSION_OBSERVATION_SHA256,
    INTENT_FILENAME,
    RECEIPT_FILENAME,
    ROLLBACK_FILENAME,
    CursorWorkspacePlan,
    materialize_cursor_workspace_plane,
    plan_cursor_workspace_plane,
    recover_cursor_workspace_plane,
    rollback_cursor_workspace_plane,
    simulated_exact_halt_proof,
    verify_cursor_workspace_plane,
)
from puppet_lib.errors import (  # noqa: E402
    ConflictError,
    IdentityError,
    UnsupportedError,
    ValidationError,
)
from puppet_lib.profiles import (  # noqa: E402
    PROMPT_TRANSPORT,
    SUBMIT_SETTLE_SECONDS,
    session_profiles_for,
    startup_settle_seconds_for,
)


ADAPTER_IMPLEMENTATION_SHA256 = "a" * 64
PROTOCOL_SHA256 = "b" * 64


def _execution_file(path: str, *, inode: int, sha256: str) -> dict:
    return {
        "path": path,
        "device": 41,
        "inode": inode,
        "size": 1000 + inode,
        "mtime_ns": 1700000000000000000 + inode,
        "sha256": sha256,
    }


def _adapter_manifest() -> dict:
    version_root = Path("/opt/cursor-agent/versions") / CURSOR_VERSION
    launcher_path = str(version_root / "cursor-agent")
    launcher = {
        "requested_path": launcher_path,
        "resolved_path": launcher_path,
        "device": 41,
        "inode": 11,
        "size": 1074,
        "mtime_ns": 1700000000000000011,
        "sha256": CURSOR_LAUNCHER_SHA256,
        "version_sha256": CURSOR_VERSION_OBSERVATION_SHA256,
        "help_sha256": CURSOR_HELP_SHA256,
    }
    execution = build_execution_bundle(
        launcher={
            "path": launcher_path,
            "device": launcher["device"],
            "inode": launcher["inode"],
            "size": launcher["size"],
            "mtime_ns": launcher["mtime_ns"],
            "sha256": launcher["sha256"],
        },
        transition="same_pid_exec",
        runtime_executable=_execution_file(
            str(version_root / "node"), inode=12, sha256=CURSOR_RUNTIME_SHA256
        ),
        transient_executables=[
            _execution_file("/usr/bin/env", inode=13, sha256="c" * 64)
        ],
        support_files=[
            _execution_file(
                str(version_root / "index.js"),
                inode=14,
                sha256=CURSOR_ENTRYPOINT_SHA256,
            )
        ],
        settle_timeout_seconds=5.0,
    )
    raw = {
        "schema_version": ADAPTER_MANIFEST_SCHEMA_VERSION,
        "target": "cursor",
        "generated_at": "2026-07-22T12:00:00Z",
        "platform": {
            "system": "Darwin",
            "release": "test",
            "machine": "arm64",
        },
        "executable": launcher,
        "execution": execution,
        "adapter_fingerprint": ADAPTER_IMPLEMENTATION_SHA256,
        "protocol_fingerprint": PROTOCOL_SHA256,
        "yolo_mapping": {
            "complete": False,
            "launch_argv": [
                launcher_path,
                "--yolo",
                "--sandbox",
                "disabled",
            ],
            "permission_declared": True,
            "permission_flags": ["--yolo"],
            "prompt_transport": PROMPT_TRANSPORT,
            "prompt_transport_declared": True,
            "sandbox_disable_declared": True,
            "sandbox_flags": ["--sandbox", "disabled"],
            "project_isolation_declared": False,
            "project_isolation_flags": [],
            "session_profiles": session_profiles_for("cursor"),
            "session_profiles_declared": True,
            "startup_settle_seconds": startup_settle_seconds_for("cursor"),
            "submit_settle_seconds": SUBMIT_SETTLE_SECONDS,
            "model_flag": "--model",
        },
        "capabilities": {name: "declared" for name in BEHAVIOR_CAPABILITIES},
        "doctor_only": True,
        "qualification": None,
    }
    return AdapterManifest.from_dict(raw).raw


class CursorWorkspacePlaneTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.lane = self.base / "lane"
        self.workspace = self.lane / "workspace"
        self.transaction = self.lane / "transaction"
        for path in (self.lane, self.workspace, self.transaction):
            path.mkdir(mode=0o700)
            path.chmod(0o700)
        self.body_marker = "CURSOR_PRIVATE_GUIDANCE_BODY_7f62"
        self.guidance = (
            "---\ndescription: Puppet Cursor workspace qualification\n"
            "alwaysApply: true\n---\n\n" + self.body_marker + "\n"
        ).encode("utf-8")
        self.manifest = _adapter_manifest()
        self.manifest_sha256 = AdapterManifest.from_dict(self.manifest).fingerprint

    def _plan(self, **overrides) -> CursorWorkspacePlan:
        arguments = {
            "adapter_manifest": self.manifest,
            "expected_manifest_sha256": self.manifest_sha256,
            "expected_adapter_implementation_sha256": (ADAPTER_IMPLEMENTATION_SHA256),
            "observed_version": CURSOR_VERSION,
            "admitted_lane_root": self.lane,
            "workspace_root": self.workspace,
            "transaction_root": self.transaction,
            "scope_id": "qualification-01",
            "guidance": self.guidance,
        }
        arguments.update(overrides)
        return plan_cursor_workspace_plane(**arguments)

    def _materialize(self, plan: CursorWorkspacePlan) -> dict:
        return materialize_cursor_workspace_plane(
            plan, guidance=self.guidance, adapter_manifest=self.manifest
        )

    def test_success_is_body_free_launch_disabled_and_exactly_rolled_back(self):
        plan = self._plan()
        self.assertEqual(
            plan.raw["launch_delta"],
            {"argv": ["--workspace", str(self.workspace)]},
        )
        self.assertFalse(plan.raw["launch_authorized"])
        self.assertEqual(
            plan.raw["status"], {"surface": "hypothesis", "activation": "disabled"}
        )
        self.assertEqual(plan.raw["blockers"], list(BLOCKERS))
        self.assertEqual(
            plan.raw["artifact"]["relative_path"],
            ".cursor/rules/puppet-qualification-01.mdc",
        )
        self.assertNotIn(self.body_marker, json.dumps(plan.to_dict()))
        self.assertEqual(list(self.workspace.iterdir()), [])
        self.assertEqual(list(self.transaction.iterdir()), [])

        receipt = self._materialize(plan)
        artifact = plan.artifact_path
        self.assertEqual(artifact.read_bytes(), self.guidance)
        self.assertEqual(stat_mode(artifact), 0o600)
        self.assertEqual(stat_mode(artifact.parent), 0o700)
        self.assertEqual(
            verify_cursor_workspace_plane(
                plan, receipt=receipt, adapter_manifest=self.manifest
            ),
            receipt,
        )
        persisted_public = b"".join(
            (self.transaction / name).read_bytes()
            for name in (INTENT_FILENAME, RECEIPT_FILENAME)
        )
        self.assertNotIn(self.body_marker.encode("utf-8"), persisted_public)

        halt = simulated_exact_halt_proof(plan, receipt)
        rollback = rollback_cursor_workspace_plane(
            plan,
            receipt,
            exact_halt_proof=halt,
            adapter_manifest=self.manifest,
        )
        self.assertEqual(rollback["terminal_state"], "rolled_back")
        self.assertTrue(rollback["retain_hash_only_terminal_proof"])
        self.assertEqual(list(self.workspace.iterdir()), [])
        self.assertFalse(artifact.exists())
        self.assertNotIn(
            self.body_marker.encode("utf-8"),
            (self.transaction / ROLLBACK_FILENAME).read_bytes(),
        )
        recovered = recover_cursor_workspace_plane(plan, adapter_manifest=self.manifest)
        self.assertEqual(recovered.state, "rolled_back")
        self.assertEqual(recovered.rollback_receipt, rollback)
        self.assertEqual(
            rollback_cursor_workspace_plane(
                plan,
                receipt,
                exact_halt_proof=halt,
                adapter_manifest=self.manifest,
            ),
            rollback,
        )

    def test_existing_guidance_scope_is_never_overwritten(self):
        existing = self.workspace / ".cursor" / "rules" / "ordinary.mdc"
        existing.parent.mkdir(parents=True)
        existing.write_text("ordinary user rule\n", encoding="utf-8")
        with self.assertRaisesRegex(ConflictError, "empty Puppet-owned scope"):
            self._plan()
        self.assertEqual(existing.read_text(encoding="utf-8"), "ordinary user rule\n")

    def test_post_plan_collision_and_symlink_fail_before_intent(self):
        plan = self._plan()
        outside = self.base / "outside"
        outside.mkdir()
        (self.workspace / ".cursor").symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(IdentityError, "preimage drifted"):
            self._materialize(plan)
        self.assertEqual(list(self.transaction.iterdir()), [])
        self.assertTrue((self.workspace / ".cursor").is_symlink())

    def test_symlink_workspace_and_escaping_root_are_rejected(self):
        outside = self.base / "outside"
        outside.mkdir(mode=0o700)
        linked = self.lane / "linked-workspace"
        linked.symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(IdentityError, "linked"):
            self._plan(workspace_root=linked)

        escaping = Path(str(self.lane / ".." / "outside"))
        with self.assertRaisesRegex(ValidationError, "normalized"):
            self._plan(workspace_root=escaping)

    def test_root_replacement_and_mode_drift_fail_closed(self):
        plan = self._plan()
        original = self.lane / "workspace-original"
        self.workspace.rename(original)
        self.workspace.mkdir(mode=0o700)
        with self.assertRaisesRegex(IdentityError, "workspace root identity changed"):
            self._materialize(plan)

        self.workspace.rmdir()
        original.rename(self.workspace)
        self.workspace.chmod(0o755)
        with self.assertRaisesRegex(IdentityError, "current-UID 0700"):
            self._materialize(plan)

    def test_artifact_content_inode_mode_and_parent_drift_fail_closed(self):
        plan = self._plan()
        receipt = self._materialize(plan)
        artifact = plan.artifact_path

        artifact.write_bytes(self.guidance + b"drift\n")
        with self.assertRaisesRegex(IdentityError, "identity or content changed"):
            verify_cursor_workspace_plane(
                plan, receipt=receipt, adapter_manifest=self.manifest
            )

        artifact.write_bytes(self.guidance)
        artifact.chmod(0o644)
        with self.assertRaisesRegex(IdentityError, "current-UID 0600"):
            verify_cursor_workspace_plane(
                plan, receipt=receipt, adapter_manifest=self.manifest
            )

        artifact.chmod(0o600)
        artifact.unlink()
        artifact.write_bytes(self.guidance)
        artifact.chmod(0o600)
        with self.assertRaisesRegex(IdentityError, "identity or content changed"):
            verify_cursor_workspace_plane(
                plan, receipt=receipt, adapter_manifest=self.manifest
            )

        artifact.unlink()
        rules = artifact.parent
        rules.rmdir()
        outside_rules = self.base / "outside-rules"
        outside_rules.mkdir()
        rules.symlink_to(outside_rules, target_is_directory=True)
        with self.assertRaisesRegex(IdentityError, "linked or replaced"):
            verify_cursor_workspace_plane(
                plan, receipt=receipt, adapter_manifest=self.manifest
            )

    def test_wrong_version_manifest_and_adapter_bindings_are_rejected(self):
        with self.assertRaisesRegex(UnsupportedError, "version is unsupported"):
            self._plan(observed_version="2026.07.16-other")

        changed = copy.deepcopy(self.manifest)
        changed["generated_at"] = "2026-07-22T12:00:01Z"
        with self.assertRaisesRegex(IdentityError, "manifest fingerprint changed"):
            self._plan(adapter_manifest=changed)

        changed_tuple = copy.deepcopy(self.manifest)
        changed_tuple["executable"]["version_sha256"] = "d" * 64
        changed_tuple = AdapterManifest.from_dict(changed_tuple).raw
        changed_tuple_hash = AdapterManifest.from_dict(changed_tuple).fingerprint
        with self.assertRaisesRegex(IdentityError, "exact supported build"):
            self._plan(
                adapter_manifest=changed_tuple,
                expected_manifest_sha256=changed_tuple_hash,
            )

        with self.assertRaisesRegex(IdentityError, "adapter implementation"):
            self._plan(expected_adapter_implementation_sha256="e" * 64)

    def test_rollback_requires_caller_supplied_exact_halt_and_exact_receipt(self):
        plan = self._plan()
        receipt = self._materialize(plan)
        with self.assertRaisesRegex(ValidationError, "exact-halt proof fields"):
            rollback_cursor_workspace_plane(
                plan,
                receipt,
                exact_halt_proof={},
                adapter_manifest=self.manifest,
            )
        self.assertTrue(plan.artifact_path.exists())

        wrong_receipt = copy.deepcopy(receipt)
        wrong_receipt["artifact"]["sha256"] = "f" * 64
        halt = simulated_exact_halt_proof(plan, receipt)
        with self.assertRaisesRegex(IdentityError, "artifact binding changed"):
            rollback_cursor_workspace_plane(
                plan,
                wrong_receipt,
                exact_halt_proof=halt,
                adapter_manifest=self.manifest,
            )
        self.assertTrue(plan.artifact_path.exists())

    def test_rollback_never_removes_unreceipted_workspace_content(self):
        plan = self._plan()
        receipt = self._materialize(plan)
        foreign = self.workspace / ".cursor" / "ordinary-user-file"
        foreign.write_text("not Puppet-owned\n", encoding="utf-8")
        halt = simulated_exact_halt_proof(plan, receipt)

        with self.assertRaisesRegex(IdentityError, "guidance scope changed"):
            rollback_cursor_workspace_plane(
                plan,
                receipt,
                exact_halt_proof=halt,
                adapter_manifest=self.manifest,
            )
        self.assertEqual(foreign.read_text(encoding="utf-8"), "not Puppet-owned\n")
        self.assertTrue(plan.artifact_path.exists())

    def test_materialization_is_idempotent_but_partial_recovery_is_ambiguous(self):
        plan = self._plan()
        first = self._materialize(plan)
        self.assertEqual(self._materialize(plan), first)
        (self.transaction / RECEIPT_FILENAME).unlink()
        with self.assertRaisesRegex(ConflictError, "recovery is ambiguous"):
            recover_cursor_workspace_plane(plan, adapter_manifest=self.manifest)
        with self.assertRaisesRegex(ConflictError, "recovery is ambiguous"):
            self._materialize(plan)

    def test_preimage_drift_and_scope_traversal_fail_closed(self):
        plan = self._plan()
        foreign = self.workspace / "foreign.txt"
        foreign.write_text("not owned\n", encoding="utf-8")
        with self.assertRaisesRegex(IdentityError, "preimage drifted"):
            self._materialize(plan)
        self.assertEqual(foreign.read_text(encoding="utf-8"), "not owned\n")
        self.assertEqual(list(self.transaction.iterdir()), [])

        foreign.unlink()
        with self.assertRaisesRegex(ValidationError, "invalid Cursor plane scope"):
            self._plan(scope_id="../escape")

    def test_module_has_no_live_or_recursive_operation_surface(self):
        source = (SCRIPTS / "puppet_lib" / "cursor_workspace_plane.py").read_text(
            encoding="utf-8"
        )
        for forbidden in (
            "import subprocess",
            "subprocess.",
            "from .census",
            "from .tmux",
            "import socket",
            "os.system",
            "os.popen",
            ".rglob(",
            "rmtree(",
        ):
            self.assertNotIn(forbidden, source)


def stat_mode(path: Path) -> int:
    return path.stat().st_mode & 0o7777


if __name__ == "__main__":
    unittest.main()
