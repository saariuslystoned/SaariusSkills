from __future__ import annotations

import copy
import inspect
import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "puppet" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import puppet_lib.agy_workspace_plane as agy_module  # noqa: E402
from puppet_lib.adapter_manifest import (  # noqa: E402
    ADAPTER_MANIFEST_SCHEMA_VERSION,
    BEHAVIOR_CAPABILITIES,
    AdapterManifest,
    QUALIFICATION_PROFILE,
    direct_execution_bundle,
)
from puppet_lib.agy_workspace_plane import (  # noqa: E402
    AGY_EXECUTABLE_SHA256,
    AGY_HELP_SHA256,
    AGY_VERSION,
    AGY_VERSION_OBSERVATION_SHA256,
    BINDING_SCHEMA,
    BINDING_STATE,
    bind_agy_workspace_plane,
    capture_agy_workspace_identity,
    require_agy_workspace_lifecycle_authority,
)
from puppet_lib.errors import IdentityError, UnsupportedError, ValidationError  # noqa: E402
from puppet_lib.instruction_planes import (  # noqa: E402
    AGY_WORKSPACE_BLOCKERS,
    build_agy_workspace_agent_descriptor,
)
from puppet_lib.instructions import compile_instruction_wrapper  # noqa: E402
from puppet_lib.profiles import (  # noqa: E402
    PROMPT_TRANSPORT,
    SUBMIT_SETTLE_SECONDS,
    session_profiles_for,
    startup_settle_seconds_for,
)


ADAPTER_SHA256 = "a" * 64
PROTOCOL_SHA256 = "b" * 64


def _adapter_manifest(
    *,
    adapter_fingerprint: str = ADAPTER_SHA256,
    protocol_fingerprint: str = PROTOCOL_SHA256,
) -> dict:
    path = "/opt/agy/agy"
    executable = {
        "requested_path": path,
        "resolved_path": path,
        "device": 41,
        "inode": 17,
        "size": 987654,
        "mtime_ns": 1700000000000000017,
        "sha256": AGY_EXECUTABLE_SHA256,
        "version_sha256": AGY_VERSION_OBSERVATION_SHA256,
        "help_sha256": AGY_HELP_SHA256,
    }
    return AdapterManifest.from_dict(
        {
            "schema_version": ADAPTER_MANIFEST_SCHEMA_VERSION,
            "target": "agy",
            "generated_at": "2026-07-23T06:40:00Z",
            "platform": {
                "system": "Darwin",
                "release": "test",
                "machine": "arm64",
            },
            "executable": executable,
            "execution": direct_execution_bundle(executable),
            "adapter_fingerprint": adapter_fingerprint,
            "protocol_fingerprint": protocol_fingerprint,
            "yolo_mapping": {
                "complete": True,
                "launch_argv": [
                    path,
                    "--dangerously-skip-permissions",
                    "--sandbox=false",
                    "--new-project",
                ],
                "permission_declared": True,
                "permission_flags": ["--dangerously-skip-permissions"],
                "prompt_transport": PROMPT_TRANSPORT,
                "prompt_transport_declared": True,
                "sandbox_disable_declared": True,
                "sandbox_flags": ["--sandbox=false"],
                "project_isolation_declared": True,
                "project_isolation_flags": ["--new-project"],
                "session_profiles": session_profiles_for("agy"),
                "session_profiles_declared": True,
                "startup_settle_seconds": startup_settle_seconds_for("agy"),
                "submit_settle_seconds": SUBMIT_SETTLE_SECONDS,
                "model_flag": "--model",
                "effort_flag": "--effort",
            },
            "capabilities": {name: "declared" for name in BEHAVIOR_CAPABILITIES},
            "doctor_only": True,
            "qualification": None,
        }
    ).raw


class AgyWorkspacePlaneBindingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.lane = Path(self.temporary.name) / "lane"
        self.workspace = self.lane / "workspace"
        for path in (self.lane, self.workspace):
            path.mkdir(mode=0o700)
            path.chmod(0o700)
        self.body_marker = "AGY_PRIVATE_CONTRACT_BODY_5c7e"
        self.contract_identity = {
            "fingerprint": "3" * 64,
            "controller": "agy-controller",
            "target": "agy",
            "task_profile": QUALIFICATION_PROFILE,
        }
        self.workspace_identity = capture_agy_workspace_identity(
            admitted_lane_root=self.lane,
            workspace_root=self.workspace,
        )
        self.run_identity = {
            "session": "agy-session",
            "run_id": "agy-run",
            "nonce": "agy-nonce-0123456789",
        }
        self.compiled = compile_instruction_wrapper(
            target="agy",
            task=self.body_marker + " produce one bounded checkpoint",
            contract_identity=self.contract_identity,
            workspace_identity=self.workspace_identity,
            run_identity=self.run_identity,
            model_binding="default",
            effort_binding="default",
        )
        self.manifest = _adapter_manifest()
        self.manifest_sha256 = AdapterManifest.from_dict(self.manifest).fingerprint
        self.descriptor = build_agy_workspace_agent_descriptor(
            adapter_manifest_sha256=self.manifest_sha256,
            rendered_sha256=self.compiled.manifest["rendered_sha256"],
        )

    def _arguments(self, **overrides):
        arguments = {
            "descriptor": self.descriptor,
            "instruction_manifest": self.compiled.manifest,
            "effective_contract": self.compiled.rendered,
            "adapter_manifest": self.manifest,
            "admitted_lane_root": self.lane,
            "workspace_root": self.workspace,
            "expected_contract_identity": self.contract_identity,
            "expected_workspace_identity": self.workspace_identity,
            "expected_run_identity": self.run_identity,
        }
        arguments.update(overrides)
        return arguments

    def _bind(
        self,
        *,
        current_adapter: str = ADAPTER_SHA256,
        current_protocol: str = PROTOCOL_SHA256,
        verify_side_effect=None,
        **overrides,
    ):
        with (
            mock.patch.object(
                agy_module,
                "adapter_implementation_fingerprint",
                return_value=current_adapter,
            ),
            mock.patch.object(
                agy_module,
                "PROTOCOL_FINGERPRINT",
                current_protocol,
            ),
            mock.patch.object(
                AdapterManifest,
                "verify_execution_files",
                autospec=True,
                side_effect=verify_side_effect,
            ) as verify_files,
        ):
            binding = bind_agy_workspace_plane(**self._arguments(**overrides))
        return binding, verify_files

    def _record(
        self,
        binding,
        *,
        current_adapter: str = ADAPTER_SHA256,
        current_protocol: str = PROTOCOL_SHA256,
        verify_side_effect=None,
    ):
        with (
            mock.patch.object(
                agy_module,
                "adapter_implementation_fingerprint",
                return_value=current_adapter,
            ),
            mock.patch.object(
                agy_module,
                "PROTOCOL_FINGERPRINT",
                current_protocol,
            ),
            mock.patch.object(
                AdapterManifest,
                "verify_execution_files",
                autospec=True,
                side_effect=verify_side_effect,
            ) as verify_files,
        ):
            record = binding.record
        return record, verify_files

    def test_exact_binding_is_body_free_hash_named_and_non_authoritative(self):
        binding, verify_files = self._bind()
        record, record_verify = self._record(binding)
        rendered_sha = self.compiled.manifest["rendered_sha256"]
        self.assertEqual(record["schema"], BINDING_SCHEMA)
        self.assertEqual(record["state"], BINDING_STATE)
        self.assertEqual(record["target_version"], AGY_VERSION)
        self.assertEqual(record["selector_name"], "puppet-%s" % rendered_sha)
        self.assertEqual(
            record["artifact"]["relative_path"],
            ".agents/agents/puppet-%s/agent.md" % rendered_sha,
        )
        self.assertEqual(record["blockers"], sorted(AGY_WORKSPACE_BLOCKERS))
        for field in (
            "materialization_authorized",
            "activation_authorized",
            "launch_authorized",
            "qualification_authorized",
        ):
            self.assertFalse(record[field])
        with (
            mock.patch.object(
                agy_module,
                "adapter_implementation_fingerprint",
                return_value=ADAPTER_SHA256,
            ),
            mock.patch.object(agy_module, "PROTOCOL_FINGERPRINT", PROTOCOL_SHA256),
            mock.patch.object(
                AdapterManifest,
                "verify_execution_files",
                autospec=True,
            ),
        ):
            public = json.dumps(binding.to_public_dict(), sort_keys=True)
        self.assertNotIn(self.body_marker, public)
        self.assertNotIn(self.body_marker, repr(binding))
        self.assertNotIn("task", record)
        verify_files.assert_called_once()
        record_verify.assert_called_once()

    def test_record_rederives_current_adapter_protocol_and_execution(self):
        binding, _ = self._bind()
        with (
            mock.patch.object(
                agy_module,
                "adapter_implementation_fingerprint",
                return_value=ADAPTER_SHA256,
            ),
            mock.patch.object(agy_module, "PROTOCOL_FINGERPRINT", PROTOCOL_SHA256),
            mock.patch.object(
                AdapterManifest,
                "verify_execution_files",
                autospec=True,
            ) as verify_files,
        ):
            self.assertEqual(binding.record, binding.record)
        self.assertEqual(verify_files.call_count, 2)

        for label, adapter, protocol in (
            ("adapter", "9" * 64, PROTOCOL_SHA256),
            ("protocol", ADAPTER_SHA256, "8" * 64),
        ):
            with self.subTest(label=label), self.assertRaises(IdentityError):
                self._record(
                    binding,
                    current_adapter=adapter,
                    current_protocol=protocol,
                )

    def test_compiler_bytes_and_every_identity_are_cross_bound(self):
        cases = []
        changed_contract = dict(self.contract_identity)
        changed_contract["fingerprint"] = "5" * 64
        cases.append(("contract", {"expected_contract_identity": changed_contract}))
        changed_workspace = dict(self.workspace_identity)
        changed_workspace["inode"] += 1
        cases.append(("workspace", {"expected_workspace_identity": changed_workspace}))
        changed_run = dict(self.run_identity)
        changed_run["run_id"] = "other-run"
        cases.append(("run", {"expected_run_identity": changed_run}))
        cases.append(
            (
                "bytes",
                {"effective_contract": self.compiled.rendered + b"\nchanged"},
            )
        )
        for label, overrides in cases:
            with self.subTest(label=label), self.assertRaises(IdentityError):
                self._bind(**overrides)

    def test_descriptor_and_runtime_default_drift_fail_closed(self):
        descriptor = copy.deepcopy(self.descriptor)
        descriptor["target"]["adapter_manifest_sha256"] = "7" * 64
        with self.assertRaises((IdentityError, ValidationError)):
            self._bind(descriptor=descriptor)

        for model, effort in (("unavailable", "default"), ("default", "unavailable")):
            compiled = compile_instruction_wrapper(
                target="agy",
                task=self.body_marker + " drift",
                contract_identity=self.contract_identity,
                workspace_identity=self.workspace_identity,
                run_identity=self.run_identity,
                model_binding=model,
                effort_binding=effort,
            )
            descriptor = build_agy_workspace_agent_descriptor(
                adapter_manifest_sha256=self.manifest_sha256,
                rendered_sha256=compiled.manifest["rendered_sha256"],
            )
            with (
                self.subTest(model=model, effort=effort),
                self.assertRaises((IdentityError, ValidationError)),
            ):
                self._bind(
                    descriptor=descriptor,
                    instruction_manifest=compiled.manifest,
                    effective_contract=compiled.rendered,
                )

    def test_self_consistent_manifest_tuple_drift_is_rejected(self):
        cases = (
            (
                "version-observation",
                lambda raw: raw["executable"].update({"version_sha256": "7" * 64}),
            ),
            (
                "help",
                lambda raw: raw["executable"].update({"help_sha256": "8" * 64}),
            ),
            (
                "sandbox-claim",
                lambda raw: raw["yolo_mapping"].update(
                    {
                        "sandbox_flags": ["--sandbox=true"],
                        "launch_argv": [
                            raw["executable"]["resolved_path"],
                            "--dangerously-skip-permissions",
                            "--sandbox=true",
                            "--new-project",
                        ],
                    }
                ),
            ),
        )
        for label, mutate in cases:
            raw = copy.deepcopy(self.manifest)
            mutate(raw)
            changed_manifest = AdapterManifest.from_dict(raw).raw
            changed_hash = AdapterManifest.from_dict(changed_manifest).fingerprint
            changed_descriptor = build_agy_workspace_agent_descriptor(
                adapter_manifest_sha256=changed_hash,
                rendered_sha256=self.compiled.manifest["rendered_sha256"],
            )
            with self.subTest(label=label), self.assertRaises(IdentityError):
                self._bind(
                    descriptor=changed_descriptor,
                    adapter_manifest=changed_manifest,
                )

    def test_workspace_replacement_and_symlink_fail_closed(self):
        binding, _ = self._bind()
        original = self.lane / "workspace-original"
        self.workspace.rename(original)
        self.workspace.mkdir(mode=0o700)
        self.workspace.chmod(0o700)
        with self.assertRaises(IdentityError):
            self._record(binding)

        linked = self.lane / "linked-workspace"
        linked.symlink_to(original, target_is_directory=True)
        linked_identity = dict(self.workspace_identity)
        linked_identity["path"] = str(linked)
        linked_identity["lane_relative_path"] = linked.name
        with self.assertRaises(IdentityError):
            self._bind(
                workspace_root=linked,
                expected_workspace_identity=linked_identity,
            )

    def test_regular_fence_is_rederived_and_constructor_has_no_record_injection(self):
        changed_verdict = agy_module.agy_regular_verdict()
        changed_verdict["launch_authorized"] = False
        with (
            mock.patch.object(
                agy_module,
                "agy_regular_verdict",
                return_value=changed_verdict,
            ),
            self.assertRaises(IdentityError),
        ):
            self._bind()

        parameters = inspect.signature(bind_agy_workspace_plane).parameters
        for forbidden in (
            "record",
            "plan",
            "binding",
            "authority",
            "launch_context",
        ):
            self.assertNotIn(forbidden, parameters)

    def test_binding_is_immutable_and_stored_source_tampering_is_detected(self):
        binding, _ = self._bind()
        with self.assertRaises(AttributeError):
            binding.anything = "changed"
        object.__setattr__(
            binding,
            "_AgyWorkspacePlaneBinding__effective_contract",
            self.compiled.rendered + b"tampered",
        )
        with self.assertRaises(IdentityError):
            self._record(binding)

    def test_lifecycle_is_unconditionally_unavailable_and_module_is_source_only(self):
        with self.assertRaisesRegex(UnsupportedError, "remain disabled"):
            require_agy_workspace_lifecycle_authority(
                guidance=self.compiled.rendered,
                launch=True,
            )
        source = inspect.getsource(agy_module)
        for forbidden in (
            "subprocess",
            "TmuxController",
            "SessionRegistry",
            "atomic_write",
            "unlink(",
            "rmdir(",
            "os.environ",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
