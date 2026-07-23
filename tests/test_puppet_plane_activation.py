from __future__ import annotations

import copy
import hashlib
import inspect
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
from puppet_lib.adapter_manifest import (  # noqa: E402
    ADAPTER_MANIFEST_SCHEMA_VERSION,
    AdapterManifest,
    direct_execution_bundle,
)
from puppet_lib.census import adapter_implementation_fingerprint  # noqa: E402
from puppet_lib.errors import (  # noqa: E402
    ConflictError,
    IdentityError,
    UnsupportedError,
    ValidationError,
)
from puppet_lib.instruction_planes import descriptor_fingerprint  # noqa: E402
from puppet_lib.instructions import compile_instruction_wrapper  # noqa: E402
from puppet_lib.matched_control import (  # noqa: E402
    ACTIVATION_MARKER_JOIN_RESULT,
    ACTIVATION_MARKER_JOIN_SCHEMA,
    ACTIVATION_MARKER_JOIN_SCOPE,
    bind_claude_marker_activation_plan,
    compile_claude_marker_instruction,
    validate_claude_marker_activation_join,
)
from puppet_lib.matched_control_authority import (  # noqa: E402
    ACTIVATION_MARKER_ATTESTATION_EVENT_SCHEMA,
    ACTIVATION_MARKER_ATTESTATION_SCHEMA_VERSION,
    attest_claude_marker_activation_join,
    verify_claude_marker_activation_join_attestation,
)
from puppet_lib.plane_activation import (  # noqa: E402
    ACTIVATION_LIFECYCLE_SCOPE,
    ActivationPlan,
    CLAUDE_NATIVE_TRIGGER_SHA256,
    INTENT_FILENAME,
    PROBE_PLANE_ACTIVATION_SCHEMA,
    RECEIPT_FILENAME,
    build_activation_launch_context,
    load_activation_plan,
    materialize_activation,
    plan_activation,
    recover_activation,
    revalidate_activation_launch_context,
    rollback_activation,
    validate_activation_plan_manifest,
    validate_terminal_activation_evidence,
    verify_activation,
)
from puppet_lib.safety import canonical_json_bytes, sha256_bytes  # noqa: E402
from puppet_lib.profiles import (  # noqa: E402
    PROMPT_TRANSPORT,
    SUBMIT_SETTLE_SECONDS,
    session_profiles_for,
    startup_settle_seconds_for,
)


ADAPTER_IMPLEMENTATION_SHA256 = adapter_implementation_fingerprint()
VERSION_OBSERVATION_SHA256 = (
    "3c95eff850dac10d40c5692a73957f526b54a74767163913dc858c4f8d4c8c63"
)


def _descriptor(adapter_manifest_sha256: str) -> dict:
    return {
        "schema": "puppet.instruction-plane/v1",
        "descriptor_id": "claude-native-qualification",
        "target": {
            "harness": "claude",
            "version": "2.1.215",
            "adapter_manifest_sha256": adapter_manifest_sha256,
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


def _adapter_manifest() -> dict:
    executable = Path(sys.executable).resolve()
    executable_details = executable.stat()
    executable_hash = hashlib.sha256(executable.read_bytes()).hexdigest()
    raw = {
        "schema_version": ADAPTER_MANIFEST_SCHEMA_VERSION,
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
        "execution": direct_execution_bundle(
            {
                "requested_path": str(executable),
                "resolved_path": str(executable),
                "sha256": executable_hash,
                "version_sha256": VERSION_OBSERVATION_SHA256,
                "help_sha256": "c" * 64,
                "device": executable_details.st_dev,
                "inode": executable_details.st_ino,
                "size": executable_details.st_size,
                "mtime_ns": executable_details.st_mtime_ns,
            }
        ),
        "adapter_fingerprint": ADAPTER_IMPLEMENTATION_SHA256,
        "protocol_fingerprint": "d" * 64,
        "yolo_mapping": {
            # Real Claude census is incomplete only because it has no native
            # project-isolation selector. The activation's exact workspace,
            # config, and admitted-lane roots close that one dimension.
            "complete": False,
            "launch_argv": [
                str(executable),
                "--dangerously-skip-permissions",
            ],
            "permission_declared": True,
            "permission_flags": ["--dangerously-skip-permissions"],
            "prompt_transport": PROMPT_TRANSPORT,
            "prompt_transport_declared": True,
            "sandbox_disable_declared": True,
            "sandbox_flags": [],
            "project_isolation_declared": False,
            "project_isolation_flags": [],
            "session_profiles": session_profiles_for("claude"),
            "session_profiles_declared": True,
            "startup_settle_seconds": startup_settle_seconds_for("claude"),
            "submit_settle_seconds": SUBMIT_SETTLE_SECONDS,
            "model_flag": "--model",
            "effort_flag": "--effort",
        },
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
        self.adapter_manifest = _adapter_manifest()
        self.adapter_manifest_sha256 = AdapterManifest.from_dict(
            self.adapter_manifest
        ).fingerprint
        self.descriptor = _descriptor(self.adapter_manifest_sha256)
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
            "_current_manifest": self.adapter_manifest,
        }
        arguments.update(overrides)
        return plan_activation(descriptor or self.descriptor, **arguments)

    def _activate(self):
        return materialize_activation(
            self.plan, effective_contract=self.compiled.rendered
        )

    def _launch_context(self, **overrides):
        arguments = {
            "adapter_manifest": self.adapter_manifest,
            "session": "claude-native-session",
            "run_id": "claude-native-run",
            "session_profile": "regular",
            "workspace_root": self.workspace,
            "config_root": self.config,
            "admitted_lane_root": self.base,
            "source_environment": {
                "HOME": "/safe/home",
                "PATH": "/usr/bin:/bin",
                "PUPPET_PARENT_CANARY": "must-not-cross",
            },
        }
        arguments.update(overrides)
        return build_activation_launch_context(self.plan, **arguments)

    def _marker_plan(self):
        marker = compile_claude_marker_instruction(
            descriptor=self.descriptor,
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
        )
        plan = self._plan(
            instruction_manifest=marker.manifest,
            effective_contract=marker.rendered,
        )
        return marker, plan

    def test_marker_compilation_joins_exact_activation_plan_without_runtime_authority(
        self,
    ):
        marker, plan = self._marker_plan()
        joined = bind_claude_marker_activation_plan(
            marker,
            activation_plan=plan,
            descriptor=self.descriptor,
            adapter_manifest=self.adapter_manifest,
        )
        self.assertEqual(joined["schema"], ACTIVATION_MARKER_JOIN_SCHEMA)
        self.assertEqual(joined["scope"], ACTIVATION_MARKER_JOIN_SCOPE)
        self.assertEqual(joined["result"], ACTIVATION_MARKER_JOIN_RESULT)
        self.assertEqual(joined["activation_plan_sha256"], plan.plan_sha256)
        self.assertEqual(
            joined["adapter_manifest_sha256"],
            AdapterManifest.from_dict(self.adapter_manifest).fingerprint,
        )
        self.assertEqual(joined["delivery_scope"], "activation_lifecycle_only")
        self.assertIs(joined["delivery_authorized"], False)
        for absent in ("controller", "campaign_id", "goal_fingerprint", "authority_id"):
            self.assertNotIn(absent, joined)
        for name in (
            "runtime_scan_authorized",
            "checkpoint_observed",
            "no_bleed_evaluated",
            "no_bleed_verified",
            "qualification_authorized",
            "promotion_authorized",
        ):
            self.assertIs(joined[name], False)
        durable = json.dumps(joined, sort_keys=True)
        self.assertNotIn("PUPPET_CLAUDE_MATCHED_CONTROL_MARKER", durable)
        self.assertNotIn("Write the bounded", durable)
        self.assertEqual(
            validate_claude_marker_activation_join(
                joined,
                marker,
                activation_plan=plan,
                descriptor=self.descriptor,
                adapter_manifest=self.adapter_manifest,
            ),
            joined,
        )

        changed_join = dict(joined, activation_plan_sha256="e" * 64)
        with self.assertRaisesRegex(IdentityError, "saved activation"):
            validate_claude_marker_activation_join(
                changed_join,
                marker,
                activation_plan=plan,
                descriptor=self.descriptor,
                adapter_manifest=self.adapter_manifest,
            )

        changed_descriptor = copy.deepcopy(self.descriptor)
        changed_descriptor["descriptor_id"] = "claude-native-other"
        with self.assertRaisesRegex(IdentityError, "join identity"):
            bind_claude_marker_activation_plan(
                marker,
                activation_plan=plan,
                descriptor=changed_descriptor,
                adapter_manifest=self.adapter_manifest,
            )

        def rehash_plan(**changes):
            value = plan.to_dict()
            value.update(changes)
            value.pop("plan_sha256")
            value["plan_sha256"] = sha256_bytes(canonical_json_bytes(value))
            return ActivationPlan.from_dict(value)

        mismatches = (
            {"descriptor_id": "caller-other-descriptor"},
            {"artifact_id": "caller-other-artifact"},
            {"effective_contract_bytes": len(marker.rendered) + 1},
            {"version_observation_sha256": "f" * 64},
        )
        for changes in mismatches:
            with self.subTest(changes=changes):
                with self.assertRaisesRegex(
                    IdentityError, "join identity|version observation"
                ):
                    bind_claude_marker_activation_plan(
                        marker,
                        activation_plan=rehash_plan(**changes),
                        descriptor=self.descriptor,
                        adapter_manifest=self.adapter_manifest,
                    )

        changed_path = plan.to_dict()
        changed_path["artifact_relative_path"] = "caller-other.md"
        changed_path["launch"]["argv"][-1] = str(self.ephemeral / "caller-other.md")
        changed_path["launch_plan_sha256"] = sha256_bytes(
            canonical_json_bytes(changed_path["launch"])
        )
        changed_path.pop("plan_sha256")
        changed_path["plan_sha256"] = sha256_bytes(canonical_json_bytes(changed_path))
        with self.assertRaisesRegex(IdentityError, "join identity"):
            bind_claude_marker_activation_plan(
                marker,
                activation_plan=ActivationPlan.from_dict(changed_path),
                descriptor=self.descriptor,
                adapter_manifest=self.adapter_manifest,
            )

        with mock.patch.object(
            AdapterManifest,
            "verify_execution_files",
            side_effect=IdentityError("execution files stale"),
        ):
            with self.assertRaisesRegex(IdentityError, "execution files stale"):
                bind_claude_marker_activation_plan(
                    marker,
                    activation_plan=plan,
                    descriptor=self.descriptor,
                    adapter_manifest=self.adapter_manifest,
                )

        with mock.patch(
            "puppet_lib.matched_control.validate_activation_plan_manifest",
            side_effect=UnsupportedError("mapping is not activation-safe"),
        ):
            with self.assertRaisesRegex(UnsupportedError, "activation-safe"):
                bind_claude_marker_activation_plan(
                    marker,
                    activation_plan=plan,
                    descriptor=self.descriptor,
                    adapter_manifest=self.adapter_manifest,
                )

        old_schema = dict(joined, schema="puppet.claude-activation-marker-join/v1")
        with self.assertRaisesRegex(IdentityError, "saved activation"):
            validate_claude_marker_activation_join(
                old_schema,
                marker,
                activation_plan=plan,
                descriptor=self.descriptor,
                adapter_manifest=self.adapter_manifest,
            )

    def test_marker_plan_attestation_is_body_free_fixed_root_and_non_authorizing(self):
        marker, plan = self._marker_plan()
        authority_root = self.base / "controller-authority"
        authority_root.mkdir(mode=0o700)
        with mock.patch(
            "puppet_lib.matched_control_authority.controller_authority_root",
            return_value=authority_root,
        ):
            first = attest_claude_marker_activation_join(
                marker,
                activation_plan=plan,
                descriptor=self.descriptor,
                adapter_manifest=self.adapter_manifest,
            )
            second = attest_claude_marker_activation_join(
                marker,
                activation_plan=plan,
                descriptor=self.descriptor,
                adapter_manifest=self.adapter_manifest,
            )
            self.assertEqual(first, second)
            self.assertEqual(
                first["schema_version"],
                ACTIVATION_MARKER_ATTESTATION_SCHEMA_VERSION,
            )
            row = verify_claude_marker_activation_join_attestation(
                first,
                marker,
                activation_plan=plan,
                descriptor=self.descriptor,
                adapter_manifest=self.adapter_manifest,
            )
        self.assertEqual(
            row["event"]["schema"], ACTIVATION_MARKER_ATTESTATION_EVENT_SCHEMA
        )
        for name in (
            "delivery_authorized",
            "runtime_scan_authorized",
            "checkpoint_observed",
            "no_bleed_evaluated",
            "no_bleed_verified",
            "qualification_authorized",
            "promotion_authorized",
        ):
            self.assertIs(row["event"][name], False)
        durable = json.dumps(
            {
                "attestation": first,
                "row": row,
            },
            sort_keys=True,
        )
        self.assertNotIn("PUPPET_CLAUDE_MATCHED_CONTROL_MARKER", durable)
        self.assertNotIn("Write the bounded", durable)
        self.assertNotIn("marker_sha256", durable)

        for function in (
            attest_claude_marker_activation_join,
            verify_claude_marker_activation_join_attestation,
        ):
            parameters = inspect.signature(function).parameters
            for forbidden in (
                "marker",
                "digest",
                "event",
                "journal",
                "rows",
                "authority_root",
            ):
                self.assertNotIn(forbidden, parameters)

        changed = dict(first, ledger_entry_hash="e" * 64)
        with mock.patch(
            "puppet_lib.matched_control_authority.controller_authority_root",
            return_value=authority_root,
        ):
            with self.assertRaisesRegex(IdentityError, "unavailable"):
                verify_claude_marker_activation_join_attestation(
                    changed,
                    marker,
                    activation_plan=plan,
                    descriptor=self.descriptor,
                    adapter_manifest=self.adapter_manifest,
                )
        bool_schema = dict(first, schema_version=True)
        with mock.patch(
            "puppet_lib.matched_control_authority.controller_authority_root",
            return_value=authority_root,
        ):
            with self.assertRaisesRegex(ValidationError, "schema"):
                verify_claude_marker_activation_join_attestation(
                    bool_schema,
                    marker,
                    activation_plan=plan,
                    descriptor=self.descriptor,
                    adapter_manifest=self.adapter_manifest,
                )
        other_root = self.base / "other-controller-authority"
        other_root.mkdir(mode=0o700)
        with mock.patch(
            "puppet_lib.matched_control_authority.controller_authority_root",
            return_value=other_root,
        ):
            with self.assertRaisesRegex(IdentityError, "authority changed"):
                verify_claude_marker_activation_join_attestation(
                    first,
                    marker,
                    activation_plan=plan,
                    descriptor=self.descriptor,
                    adapter_manifest=self.adapter_manifest,
                )

    def test_plan_manifest_rejects_paired_false_version_observation(self):
        changed_manifest = copy.deepcopy(self.adapter_manifest)
        changed_manifest["executable"]["version_sha256"] = "f" * 64
        changed_manifest = AdapterManifest.from_dict(changed_manifest)
        changed_plan = self.plan.to_dict()
        changed_plan["adapter_manifest_sha256"] = changed_manifest.fingerprint
        changed_plan["version_observation_sha256"] = "f" * 64
        changed_plan.pop("plan_sha256")
        changed_plan["plan_sha256"] = sha256_bytes(canonical_json_bytes(changed_plan))
        with self.assertRaisesRegex(IdentityError, "version observation"):
            validate_activation_plan_manifest(
                changed_manifest,
                ActivationPlan.from_dict(changed_plan),
            )

    def _revalidate_context(self, context, **overrides):
        arguments = {
            "adapter_manifest": self.adapter_manifest,
            "workspace_root": self.workspace,
            "config_root": self.config,
            "admitted_lane_root": self.base,
            "argv": context.argv,
            "environment": context.environment,
            "admitted_launch_plan": context.admitted_launch_plan,
            "public_context": context.to_public_dict(),
        }
        arguments.update(overrides)
        return revalidate_activation_launch_context(
            context,
            self.plan,
            **arguments,
        )

    @staticmethod
    def _json_file(path):
        return json.loads(path.read_text(encoding="utf-8"))

    def _terminal_activation_family(self):
        self._activate()
        context = self._launch_context()
        rollback_activation(self.plan)
        intent = self._json_file(self.plan.intent_path)
        receipt = self._json_file(self.plan.receipt_path)
        rollback_intent = self._json_file(self.plan.rollback_intent_path)
        rollback_receipt = self._json_file(self.plan.rollback_receipt_path)
        public_context = context.to_public_dict()
        activation = {
            "schema": PROBE_PLANE_ACTIVATION_SCHEMA,
            "qualification_scope": ACTIVATION_LIFECYCLE_SCOPE,
            "terminal_state": "rolled_back",
            "descriptor_sha256": descriptor_fingerprint(self.descriptor),
            "plan_sha256": self.plan.plan_sha256,
            "intent_sha256": sha256_bytes(canonical_json_bytes(intent)),
            "materialization_receipt_sha256": sha256_bytes(
                canonical_json_bytes(receipt)
            ),
            "launch_context_sha256": sha256_bytes(canonical_json_bytes(public_context)),
            "artifact_sha256": self.plan.raw["effective_contract_sha256"],
            "initial_trigger_sha256": CLAUDE_NATIVE_TRIGGER_SHA256,
            "rollback_intent_sha256": sha256_bytes(
                canonical_json_bytes(rollback_intent)
            ),
            "rollback_receipt_sha256": sha256_bytes(
                canonical_json_bytes(rollback_receipt)
            ),
        }
        return {
            "activation": activation,
            "descriptor": copy.deepcopy(self.descriptor),
            "intent": intent,
            "materialization_receipt": receipt,
            "public_context": public_context,
            "admitted_launch_plan": context.admitted_launch_plan,
            "rollback_intent": rollback_intent,
            "rollback_receipt": rollback_receipt,
        }

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
            sha256_bytes(
                activation_module._canonical_json_with_newline(self.compiled.manifest)
            ),
        )
        self.assertEqual(
            raw["effective_contract_fingerprint"],
            self.compiled.manifest["effective_contract_fingerprint"],
        )
        self.assertEqual(
            raw["effective_contract_sha256"], sha256_bytes(self.compiled.rendered)
        )
        self.assertEqual(raw["adapter_manifest_sha256"], self.adapter_manifest_sha256)
        self.assertEqual(
            raw["adapter_implementation_sha256"],
            ADAPTER_IMPLEMENTATION_SHA256,
        )
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

    def test_plan_binds_exact_manifest_but_ignores_fresh_census_timestamp(self):
        self.assertNotEqual(
            self.adapter_manifest_sha256,
            ADAPTER_IMPLEMENTATION_SHA256,
        )
        fresh = copy.deepcopy(self.adapter_manifest)
        fresh["generated_at"] = "2026-07-22T03:00:01Z"
        self.assertNotEqual(
            AdapterManifest.from_dict(fresh).fingerprint,
            self.adapter_manifest_sha256,
        )
        plan = self._plan(_current_manifest=fresh)
        self.assertEqual(
            plan.raw["adapter_manifest_sha256"], self.adapter_manifest_sha256
        )
        self.assertEqual(
            plan.raw["adapter_implementation_sha256"],
            ADAPTER_IMPLEMENTATION_SHA256,
        )

        implementation_bound = copy.deepcopy(self.descriptor)
        implementation_bound["target"]["adapter_manifest_sha256"] = (
            ADAPTER_IMPLEMENTATION_SHA256
        )
        with self.assertRaisesRegex(IdentityError, "exact supplied adapter manifest"):
            self._plan(implementation_bound, _current_manifest=fresh)

    def test_real_shaped_claude_activation_builds_body_free_prelease_context(self):
        receipt = self._activate()
        before = {
            "config": list(self.config.iterdir()),
            "ephemeral": [item.name for item in self.ephemeral.iterdir()],
            "transaction": [item.name for item in self.transaction.iterdir()],
        }
        with mock.patch.object(
            activation_module,
            "census_target",
            side_effect=AssertionError("launch context must remain process-free"),
        ):
            context = self._launch_context()
        after = {
            "config": list(self.config.iterdir()),
            "ephemeral": [item.name for item in self.ephemeral.iterdir()],
            "transaction": [item.name for item in self.transaction.iterdir()],
        }
        self.assertEqual(before, after)

        expected_argv = [
            str(Path(sys.executable).resolve()),
            "--dangerously-skip-permissions",
            "--append-system-prompt-file",
            str(self.plan.artifact_path),
        ]
        expected_environment = {
            "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "true",
            "CLAUDE_CONFIG_DIR": str(self.config.resolve(strict=True)),
            "HOME": "/safe/home",
            "PATH": "/usr/bin:/bin",
        }
        self.assertEqual(context.argv, expected_argv)
        self.assertEqual(context.environment, expected_environment)
        self.assertNotIn("PUPPET_PARENT_CANARY", context.environment)
        admitted = context.admitted_launch_plan
        self.assertEqual(admitted["kind"], "puppet.admitted-launch-plan/v1")
        self.assertEqual(admitted["argv"], expected_argv)
        self.assertNotIn("environment", admitted)
        self.assertEqual(
            context.launch_identity,
            {
                "cwd": admitted["cwd"],
                "argv_sha256": sha256_bytes(canonical_json_bytes(expected_argv)),
                "env_names": admitted["env_names"],
                "env_fingerprint": admitted["env_fingerprint"],
            },
        )

        public = context.to_public_dict()
        self.assertEqual(public["schema"], activation_module.LAUNCH_CONTEXT_SCHEMA)
        self.assertEqual(public["activation_plan_sha256"], self.plan.plan_sha256)
        self.assertEqual(
            public["activation_receipt_sha256"],
            sha256_bytes(canonical_json_bytes(receipt)),
        )
        self.assertEqual(
            public["activation_delta_sha256"],
            self.plan.raw["launch_plan_sha256"],
        )
        self.assertEqual(
            public["adapter_manifest_sha256"], self.adapter_manifest_sha256
        )
        self.assertEqual(
            public["adapter_implementation_sha256"],
            ADAPTER_IMPLEMENTATION_SHA256,
        )
        self.assertEqual(
            public["project_isolation"],
            "subscription_profile_config_plus_isolated_activation_roots",
        )
        persistable = canonical_json_bytes(public) + canonical_json_bytes(admitted)
        for forbidden in (
            self.compiled.rendered,
            self.body_marker.encode(),
            str(self.config).encode(),
            str(self.config.resolve(strict=True)).encode(),
            b"/safe/home",
            b"/usr/bin:/bin",
            b"true",
            b"must-not-cross",
        ):
            self.assertNotIn(forbidden, persistable)
            self.assertNotIn(forbidden.decode("utf-8"), repr(context))

    def test_launch_context_requires_verified_activation_before_resolution(self):
        with mock.patch.object(activation_module, "build_launch_identity") as builder:
            with self.assertRaisesRegex(ConflictError, "not in active state"):
                self._launch_context()
        builder.assert_not_called()

    def test_launch_context_joins_separate_profile_and_activation_roots(self):
        profile_root = self.base / "subscription-profile"
        profile_config = profile_root / "config"
        activation_root = self.base / "activation-run"
        activation_ephemeral = activation_root / "ephemeral"
        activation_transaction = activation_root / "transaction"
        for path in (
            profile_root,
            profile_config,
            activation_root,
            activation_ephemeral,
            activation_transaction,
        ):
            path.mkdir(mode=0o700)
            path.chmod(0o700)
        plan = self._plan(
            config_root=profile_config,
            ephemeral_root=activation_ephemeral,
            transaction_root=activation_transaction,
        )
        materialize_activation(plan, effective_contract=self.compiled.rendered)
        context = build_activation_launch_context(
            plan,
            adapter_manifest=self.adapter_manifest,
            session="claude-profile-joined-session",
            run_id="claude-profile-joined-run",
            session_profile="regular",
            workspace_root=self.workspace,
            config_root=profile_config,
            admitted_lane_root=profile_root,
            source_environment={"HOME": "/safe/home", "PATH": "/usr/bin:/bin"},
        )
        self.assertEqual(
            context.environment["CLAUDE_CONFIG_DIR"],
            str(profile_config.resolve(strict=True)),
        )
        self.assertTrue(plan.artifact_path.is_relative_to(activation_root))
        self.assertFalse(plan.artifact_path.is_relative_to(profile_root))

    def test_launch_context_rejects_manifest_argv_and_environment_drift(self):
        self._activate()
        context = self._launch_context()

        changed_manifest = copy.deepcopy(self.adapter_manifest)
        changed_manifest["generated_at"] = "2026-07-22T03:00:02Z"
        with self.assertRaisesRegex(IdentityError, "adapter manifest changed"):
            self._launch_context(adapter_manifest=changed_manifest)

        changed_base_argv = copy.deepcopy(self.adapter_manifest)
        changed_base_argv["yolo_mapping"]["launch_argv"].append("--argv-drift")
        with self.assertRaisesRegex(IdentityError, "adapter manifest changed"):
            self._launch_context(adapter_manifest=changed_base_argv)

        argv = context.argv
        argv[-1] = str(self.base / "different-artifact")
        with self.assertRaisesRegex(IdentityError, "launch argv changed"):
            context.verify_launch_values(argv=argv, environment=context.environment)

        environment = context.environment
        environment["CLAUDE_CONFIG_DIR"] = str(self.workspace.resolve(strict=True))
        with self.assertRaisesRegex(IdentityError, "launch environment changed"):
            context.verify_launch_values(argv=context.argv, environment=environment)

        with self.assertRaisesRegex(UnsupportedError, "regular profile"):
            self._launch_context(session_profile="goal")

    def test_launch_context_rejects_receipt_artifact_and_root_drift(self):
        self._activate()
        original_receipt = self.plan.receipt_path.read_bytes()
        receipt = json.loads(original_receipt.decode("utf-8"))
        receipt["plan_sha256"] = "f" * 64
        self.plan.receipt_path.write_bytes(canonical_json_bytes(receipt) + b"\n")
        self.plan.receipt_path.chmod(0o600)
        with self.assertRaisesRegex(IdentityError, "receipt binding changed"):
            self._launch_context()
        self.plan.receipt_path.write_bytes(original_receipt)
        self.plan.receipt_path.chmod(0o600)

        changed_body = b"X" * len(self.compiled.rendered)
        self.plan.artifact_path.write_bytes(changed_body)
        self.plan.artifact_path.chmod(0o600)
        with self.assertRaisesRegex(IdentityError, "artifact identity or content"):
            self._launch_context()
        self.plan.artifact_path.write_bytes(self.compiled.rendered)
        self.plan.artifact_path.chmod(0o600)

        wrong_workspace = self.base / "wrong-workspace"
        wrong_workspace.mkdir(mode=0o700)
        with self.assertRaisesRegex(
            IdentityError, "does not match the activation plan"
        ):
            self._launch_context(workspace_root=wrong_workspace)

        with self.assertRaisesRegex(IdentityError, "subscription profile parent"):
            self._launch_context(admitted_lane_root=self.base.parent)
        original_lane_mode = stat.S_IMODE(self.base.stat().st_mode)
        self.base.chmod(0o755)
        try:
            with self.assertRaisesRegex(IdentityError, "current-UID 0700"):
                self._launch_context()
        finally:
            self.base.chmod(original_lane_mode)

        retired_config = self.base / "retired-config"
        self.config.rename(retired_config)
        self.config.mkdir(mode=0o700)
        try:
            with self.assertRaisesRegex(IdentityError, "config root identity changed"):
                self._launch_context()
        finally:
            self.config.rmdir()
            retired_config.rename(self.config)

    def test_immediate_revalidator_rebuilds_the_exact_consumable_context(self):
        self._activate()
        context = self._launch_context()
        with mock.patch.object(
            activation_module,
            "census_target",
            side_effect=AssertionError("revalidation must remain process-free"),
        ):
            current = self._revalidate_context(context)
        self.assertIsNot(current, context)
        self.assertEqual(current.argv, context.argv)
        self.assertEqual(current.environment, context.environment)
        self.assertEqual(
            current.admitted_launch_plan,
            context.admitted_launch_plan,
        )
        self.assertEqual(current.to_public_dict(), context.to_public_dict())
        self.assertEqual(
            current.public_context_sha256,
            context.public_context_sha256,
        )

    def test_immediate_revalidator_rejects_post_context_authority_drift(self):
        self._activate()
        context = self._launch_context()

        original_receipt = self.plan.receipt_path.read_bytes()
        receipt = json.loads(original_receipt.decode("utf-8"))
        receipt["plan_sha256"] = "f" * 64
        self.plan.receipt_path.write_bytes(canonical_json_bytes(receipt) + b"\n")
        self.plan.receipt_path.chmod(0o600)
        with self.assertRaisesRegex(IdentityError, "receipt binding changed"):
            self._revalidate_context(context)
        self.plan.receipt_path.write_bytes(original_receipt)
        self.plan.receipt_path.chmod(0o600)

        self.plan.artifact_path.write_bytes(b"X" * len(self.compiled.rendered))
        self.plan.artifact_path.chmod(0o600)
        with self.assertRaisesRegex(IdentityError, "artifact identity or content"):
            self._revalidate_context(context)
        self.plan.artifact_path.write_bytes(self.compiled.rendered)
        self.plan.artifact_path.chmod(0o600)

        retired_config = self.base / "post-context-config"
        self.config.rename(retired_config)
        self.config.mkdir(mode=0o700)
        try:
            with self.assertRaisesRegex(IdentityError, "config root identity changed"):
                self._revalidate_context(context)
        finally:
            self.config.rmdir()
            retired_config.rename(self.config)

        retired_transaction = self.base / "post-context-transaction"
        self.transaction.rename(retired_transaction)
        self.transaction.mkdir(mode=0o700)
        try:
            with self.assertRaisesRegex(
                IdentityError, "transaction root identity changed"
            ):
                self._revalidate_context(context)
        finally:
            self.transaction.rmdir()
            retired_transaction.rename(self.transaction)

        changed_manifest = copy.deepcopy(self.adapter_manifest)
        changed_manifest["generated_at"] = "2026-07-22T03:00:03Z"
        with self.assertRaisesRegex(IdentityError, "adapter manifest changed"):
            self._revalidate_context(
                context,
                adapter_manifest=changed_manifest,
            )
        with mock.patch.object(
            activation_module,
            "adapter_implementation_fingerprint",
            return_value="f" * 64,
        ):
            with self.assertRaisesRegex(
                IdentityError, "adapter implementation changed"
            ):
                self._revalidate_context(context)

    def test_immediate_revalidator_rejects_private_and_public_binding_drift(self):
        self._activate()
        context = self._launch_context()

        argv = context.argv
        argv[-1] = str(self.base / "post-context-prompt-drift")
        with self.assertRaisesRegex(IdentityError, "launch argv changed"):
            self._revalidate_context(context, argv=argv)

        environment = context.environment
        environment["CLAUDE_CONFIG_DIR"] = str(self.workspace.resolve(strict=True))
        with self.assertRaisesRegex(IdentityError, "launch environment changed"):
            self._revalidate_context(context, environment=environment)

        admitted = context.admitted_launch_plan
        admitted["argv"][-1] = str(self.base / "post-context-plan-drift")
        with self.assertRaisesRegex(IdentityError, "admitted launch plan changed"):
            self._revalidate_context(context, admitted_launch_plan=admitted)

        public = context.to_public_dict()
        public["activation_receipt_sha256"] = "f" * 64
        with self.assertRaisesRegex(IdentityError, "public context changed"):
            self._revalidate_context(context, public_context=public)

    def test_only_project_isolation_may_be_closed_by_activation_roots(self):
        incomplete_dimensions = (
            "permission_declared",
            "sandbox_disable_declared",
            "prompt_transport_declared",
            "session_profiles_declared",
        )
        for dimension in incomplete_dimensions:
            with self.subTest(dimension=dimension):
                candidate = copy.deepcopy(self.adapter_manifest)
                candidate["yolo_mapping"][dimension] = False
                manifest = AdapterManifest.from_dict(candidate)
                descriptor = copy.deepcopy(self.descriptor)
                descriptor["target"]["adapter_manifest_sha256"] = manifest.fingerprint
                plan = self._plan(
                    descriptor,
                    adapter_manifest=manifest,
                    _current_manifest=manifest,
                )
                with self.assertRaisesRegex(
                    UnsupportedError,
                    "only the missing project-isolation dimension",
                ):
                    activation_module._context_manifest(manifest, plan)

    def test_terminal_activation_evidence_proves_exact_rolled_back_family(self):
        family = self._terminal_activation_family()
        normalized = validate_terminal_activation_evidence(**family)
        self.assertEqual(normalized, family["activation"])
        self.assertFalse(self.plan.artifact_path.exists())
        self.assertEqual(list(self.ephemeral.iterdir()), [])
        serialized = canonical_json_bytes(normalized)
        self.assertNotIn(self.compiled.rendered, serialized)
        self.assertNotIn(self.body_marker.encode(), serialized)

    def test_terminal_activation_evidence_rejects_hash_and_trigger_forgery(self):
        family = self._terminal_activation_family()
        for name in (
            "descriptor_sha256",
            "plan_sha256",
            "intent_sha256",
            "materialization_receipt_sha256",
            "launch_context_sha256",
            "artifact_sha256",
            "rollback_intent_sha256",
            "rollback_receipt_sha256",
        ):
            with self.subTest(name=name):
                candidate = copy.deepcopy(family)
                candidate["activation"][name] = "f" * 64
                with self.assertRaises((IdentityError, ValidationError)):
                    validate_terminal_activation_evidence(**candidate)

        duplicate = copy.deepcopy(family)
        duplicate["activation"]["initial_trigger_sha256"] = self.plan.raw[
            "effective_contract_sha256"
        ]
        with self.assertRaises((IdentityError, ValidationError)):
            validate_terminal_activation_evidence(**duplicate)

    def test_terminal_activation_evidence_rejects_incomplete_or_resurrected_state(self):
        family = self._terminal_activation_family()
        incomplete = copy.deepcopy(family)
        incomplete["rollback_receipt"].pop("artifact_state")
        with self.assertRaisesRegex(IdentityError, "transaction evidence changed"):
            validate_terminal_activation_evidence(**incomplete)

        context_drift = copy.deepcopy(family)
        context_drift["public_context"].pop("activation_receipt_sha256")
        with self.assertRaisesRegex(ValidationError, "public context fields"):
            validate_terminal_activation_evidence(**context_drift)

        self.plan.artifact_path.write_bytes(self.compiled.rendered)
        self.plan.artifact_path.chmod(0o600)
        with self.assertRaises((ConflictError, IdentityError)):
            validate_terminal_activation_evidence(**family)

    def test_terminal_activation_evidence_reopens_roots_and_transaction_files(self):
        family = self._terminal_activation_family()
        retired_config = self.base / "terminal-retired-config"
        self.config.rename(retired_config)
        self.config.mkdir(mode=0o700)
        try:
            with self.assertRaisesRegex(IdentityError, "config root identity changed"):
                validate_terminal_activation_evidence(**family)
        finally:
            self.config.rmdir()
            retired_config.rename(self.config)

        original = self.plan.rollback_receipt_path.read_bytes()
        changed = self._json_file(self.plan.rollback_receipt_path)
        changed["artifact_state"] = "present"
        self.plan.rollback_receipt_path.write_bytes(
            canonical_json_bytes(changed) + b"\n"
        )
        self.plan.rollback_receipt_path.chmod(0o600)
        try:
            with self.assertRaisesRegex(IdentityError, "transaction evidence changed"):
                validate_terminal_activation_evidence(**family)
        finally:
            self.plan.rollback_receipt_path.write_bytes(original)
            self.plan.rollback_receipt_path.chmod(0o600)

    def test_v2_load_and_recovery_reject_legacy_future_and_mixed_families(self):
        current_plan = self.plan.to_dict()
        cases = (
            (
                "legacy-intent",
                {
                    "schema": "puppet.plane-activation-intent/v1",
                    "plan": current_plan,
                },
                "activation intent schema",
            ),
            (
                "future-intent",
                {
                    "schema": "puppet.plane-activation-intent/v3",
                    "plan": current_plan,
                },
                "activation intent schema",
            ),
            (
                "mixed-plan",
                {
                    "schema": activation_module.INTENT_SCHEMA,
                    "plan": {
                        **current_plan,
                        "schema": "puppet.plane-activation-plan/v1",
                    },
                },
                "activation plan schema",
            ),
        )
        for label, value, message in cases:
            with self.subTest(label=label):
                self.plan.intent_path.write_bytes(canonical_json_bytes(value) + b"\n")
                self.plan.intent_path.chmod(0o600)
                with self.assertRaisesRegex(ValidationError, message):
                    load_activation_plan(self.transaction)
                with self.assertRaisesRegex(ValidationError, message):
                    recover_activation(self.transaction)
                self.plan.intent_path.unlink()

        self._activate()
        self.assertEqual(load_activation_plan(self.transaction), self.plan)
        self.assertEqual(recover_activation(self.transaction).state, "active")
        original_receipt = self.plan.receipt_path.read_bytes()
        receipt = json.loads(original_receipt.decode("utf-8"))
        receipt["schema"] = "puppet.plane-activation-receipt/v1"
        self.plan.receipt_path.write_bytes(canonical_json_bytes(receipt) + b"\n")
        self.plan.receipt_path.chmod(0o600)
        with self.assertRaisesRegex(ValidationError, "activation receipt schema"):
            recover_activation(self.transaction)

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

    def test_config_root_is_required_and_revalidated_at_use_time(self):
        with mock.patch.object(activation_module, "census_target") as census:
            with self.assertRaisesRegex(ValidationError, "config root is required"):
                self._plan(config_root=None, _current_manifest=None)
        census.assert_not_called()

        original_config = self.base / "original-config"
        self.config.rename(original_config)
        self.config.mkdir(mode=0o700)
        with self.assertRaises(IdentityError):
            self._activate()

        with TemporaryDirectory() as raw:
            base = Path(raw)
            roots = {
                name: base / name
                for name in ("workspace", "ephemeral", "transaction", "config")
            }
            for path in roots.values():
                path.mkdir(mode=0o700)
            plan = self._plan(
                workspace_root=roots["workspace"],
                ephemeral_root=roots["ephemeral"],
                transaction_root=roots["transaction"],
                config_root=roots["config"],
            )
            materialize_activation(plan, effective_contract=self.compiled.rendered)
            roots["config"].rename(base / "retired-config")
            roots["config"].mkdir(mode=0o700)
            with self.assertRaises(IdentityError):
                verify_activation(plan)

    @unittest.skipUnless(Path("/dev/fd").is_dir(), "/dev/fd is unavailable")
    def test_partial_root_and_child_open_failures_do_not_leak_fds_or_residue(self):
        before = len(os.listdir("/dev/fd"))
        missing = self.base / "missing-config"
        for _ in range(8):
            with self.assertRaises(ValidationError):
                self._plan(config_root=missing)
        self.assertEqual(len(os.listdir("/dev/fd")), before)

        root_descriptor = os.open(
            self.ephemeral,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
        )
        try:
            child_before = len(os.listdir("/dev/fd"))
            with mock.patch.object(
                activation_module.os,
                "fchmod",
                side_effect=OSError("injected fchmod failure"),
            ):
                with self.assertRaises(IdentityError):
                    activation_module._open_or_create_parents(
                        root_descriptor, ["created-parent"]
                    )
            self.assertEqual(len(os.listdir("/dev/fd")), child_before)
            self.assertFalse((self.ephemeral / "created-parent").exists())
        finally:
            os.close(root_descriptor)

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

    @unittest.skipUnless(Path("/dev/fd").is_dir(), "/dev/fd is unavailable")
    def test_artifact_mode_setup_failure_cleans_exact_leaf_and_can_retry(self):
        before = len(os.listdir("/dev/fd"))
        original = activation_module.os.fchmod
        calls = 0

        def fail_artifact_mode(descriptor, mode):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("injected artifact mode failure")
            return original(descriptor, mode)

        with mock.patch.object(
            activation_module.os, "fchmod", side_effect=fail_artifact_mode
        ):
            with self.assertRaises(OSError):
                self._activate()
        self.assertEqual(list(self.ephemeral.iterdir()), [])
        self.assertEqual(len(os.listdir("/dev/fd")), before)
        self.assertEqual(self._activate(), verify_activation(self.plan))

    @unittest.skipUnless(Path("/dev/fd").is_dir(), "/dev/fd is unavailable")
    def test_artifact_first_identity_failure_recovers_cleanup_and_retry(self):
        before = len(os.listdir("/dev/fd"))
        original = activation_module._new_leaf_identity
        calls = 0

        def fail_first_capture(descriptor):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise OSError("injected first identity failure")
            return original(descriptor)

        with mock.patch.object(
            activation_module,
            "_new_leaf_identity",
            side_effect=fail_first_capture,
        ):
            with self.assertRaises(OSError):
                self._activate()
        self.assertEqual(list(self.ephemeral.iterdir()), [])
        self.assertEqual(len(os.listdir("/dev/fd")), before)
        self.assertEqual(self._activate(), verify_activation(self.plan))

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
        drifted_version["executable"]["version_sha256"] = "f" * 64
        with self.assertRaises(IdentityError):
            self._plan(adapter_manifest=drifted_version)
        fake_executable = copy.deepcopy(self.adapter_manifest)
        fake_executable["executable"]["resolved_path"] = str(self.workspace)
        with self.assertRaises((IdentityError, ValidationError)):
            self._plan(adapter_manifest=fake_executable)
        with self.assertRaises(IdentityError):
            self._plan(effective_contract=self.compiled.rendered + b"changed")
        old_version = copy.deepcopy(self.descriptor)
        old_version["target"]["version"] = "2.1.214"
        with self.assertRaises(UnsupportedError):
            self._plan(old_version)
        self.assertEqual(list(self.ephemeral.iterdir()), [])
        self.assertEqual(list(self.transaction.iterdir()), [])

    def test_default_plan_path_recensuses_exact_current_manifest(self):
        with mock.patch.object(
            activation_module,
            "census_target",
            return_value=AdapterManifest.from_dict(self.adapter_manifest),
        ) as census:
            self._plan(_current_manifest=None)
        census.assert_called_once_with("claude", ADAPTER_IMPLEMENTATION_SHA256)

    def test_rollback_intent_is_durable_before_any_cleanup(self):
        self._activate()
        original = activation_module._persist_immutable_json

        def fail_intent(root_descriptor, name, value, *, label):
            if name == activation_module.ROLLBACK_INTENT_FILENAME:
                self.assertTrue(self.plan.artifact_path.exists())
                raise OSError("injected rollback intent failure")
            return original(root_descriptor, name, value, label=label)

        with mock.patch.object(
            activation_module,
            "_persist_immutable_json",
            side_effect=fail_intent,
        ):
            with self.assertRaises(OSError):
                rollback_activation(self.plan)
        self.assert_artifact_preserved()
        self.assertFalse(self.plan.rollback_intent_path.exists())
        self.assertEqual(recover_activation(self.transaction).state, "active")

        with mock.patch.object(
            activation_module,
            "_perform_rollback_cleanup",
            side_effect=OSError("injected post-intent crash"),
        ):
            with self.assertRaises(OSError):
                rollback_activation(self.plan)
        self.assertTrue(self.plan.rollback_intent_path.exists())
        self.assert_artifact_preserved()
        self.assertEqual(recover_activation(self.transaction).state, "active")
        rollback_activation(self.plan)
        self.assertEqual(recover_activation(self.transaction).state, "rolled_back")

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

    def test_module_has_no_direct_subprocess_or_recursive_path_cleanup(self):
        source = (SCRIPTS / "puppet_lib" / "plane_activation.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("import subprocess", source)
        self.assertNotIn("subprocess.", source)
        self.assertNotIn(".rglob(", source)
        self.assertNotIn("rmtree(", source)


if __name__ == "__main__":
    unittest.main()
