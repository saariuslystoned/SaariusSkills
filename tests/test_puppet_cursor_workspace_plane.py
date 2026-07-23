from __future__ import annotations

import copy
import inspect
import json
import sys
import unittest
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "puppet" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import puppet_lib.cursor_workspace_plane as cursor_module  # noqa: E402
from puppet_lib.adapter_manifest import (  # noqa: E402
    ADAPTER_MANIFEST_SCHEMA_VERSION,
    BEHAVIOR_CAPABILITIES,
    AdapterManifest,
    QUALIFICATION_PROFILE,
    build_execution_bundle,
)
from puppet_lib.cursor_workspace_plane import (  # noqa: E402
    BINDING_SCHEMA,
    BINDING_STATE,
    BLOCKERS,
    CURSOR_ENTRYPOINT_SHA256,
    CURSOR_HELP_SHA256,
    CURSOR_LAUNCHER_SHA256,
    CURSOR_RUNTIME_SHA256,
    CURSOR_VERSION,
    CURSOR_VERSION_OBSERVATION_SHA256,
    CursorWorkspacePlan,
    bind_cursor_workspace_plane,
    derive_cursor_workspace_launch_argv,
    materialize_cursor_workspace_plane,
    plan_cursor_workspace_plane,
    recover_cursor_workspace_plane,
    revalidate_cursor_workspace_plan,
    rollback_cursor_workspace_plane,
    verify_cursor_workspace_plane,
)
from puppet_lib.errors import (  # noqa: E402
    ConflictError,
    IdentityError,
    UnsupportedError,
    ValidationError,
)
from puppet_lib.instruction_planes import (  # noqa: E402
    build_cursor_workspace_addendum_descriptor,
)
from puppet_lib.instructions import compile_instruction_wrapper  # noqa: E402
from puppet_lib.profiles import (  # noqa: E402
    PROMPT_TRANSPORT,
    SUBMIT_SETTLE_SECONDS,
    session_profiles_for,
    startup_settle_seconds_for,
)
from puppet_lib.safety import canonical_json_bytes, sha256_bytes  # noqa: E402


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


def _adapter_manifest(
    *,
    generated_at: str = "2026-07-22T12:00:00Z",
    adapter_fingerprint: str = ADAPTER_IMPLEMENTATION_SHA256,
    protocol_fingerprint: str = PROTOCOL_SHA256,
) -> dict:
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
        "generated_at": generated_at,
        "platform": {
            "system": "Darwin",
            "release": "test",
            "machine": "arm64",
        },
        "executable": launcher,
        "execution": execution,
        "adapter_fingerprint": adapter_fingerprint,
        "protocol_fingerprint": protocol_fingerprint,
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
        for path in (self.lane, self.workspace):
            path.mkdir(mode=0o700)
            path.chmod(0o700)
        self.body_marker = "CURSOR_PRIVATE_GUIDANCE_BODY_7f62"
        self.guidance = (
            "---\ndescription: Puppet Cursor workspace qualification\n"
            "alwaysApply: true\n---\n\n" + self.body_marker + "\n"
        ).encode("utf-8")
        self.manifest = _adapter_manifest()
        self.manifest_sha256 = AdapterManifest.from_dict(self.manifest).fingerprint

    @contextmanager
    def _current_authority(
        self,
        *,
        adapter_fingerprint: str = ADAPTER_IMPLEMENTATION_SHA256,
        protocol_fingerprint: str = PROTOCOL_SHA256,
        verify_side_effect=None,
    ):
        with (
            mock.patch.object(
                cursor_module,
                "adapter_implementation_fingerprint",
                return_value=adapter_fingerprint,
            ) as fingerprint,
            mock.patch.object(
                cursor_module, "PROTOCOL_FINGERPRINT", protocol_fingerprint
            ),
            mock.patch.object(
                AdapterManifest,
                "verify_execution_files",
                autospec=True,
                side_effect=verify_side_effect,
            ) as verify_files,
        ):
            yield fingerprint, verify_files

    def _plan_arguments(self, **overrides):
        arguments = {
            "adapter_manifest": self.manifest,
            "expected_manifest_sha256": self.manifest_sha256,
            "expected_adapter_implementation_sha256": (ADAPTER_IMPLEMENTATION_SHA256),
            "observed_version": CURSOR_VERSION,
            "admitted_lane_root": self.lane,
            "workspace_root": self.workspace,
            "scope_id": "qualification-01",
            "guidance": self.guidance,
        }
        arguments.update(overrides)
        return arguments

    def _plan(
        self,
        *,
        _current_adapter: str = ADAPTER_IMPLEMENTATION_SHA256,
        _current_protocol: str = PROTOCOL_SHA256,
        _verify_side_effect=None,
        **overrides,
    ) -> CursorWorkspacePlan:
        with self._current_authority(
            adapter_fingerprint=_current_adapter,
            protocol_fingerprint=_current_protocol,
            verify_side_effect=_verify_side_effect,
        ):
            return plan_cursor_workspace_plane(**self._plan_arguments(**overrides))

    def _revalidate(
        self,
        plan: CursorWorkspacePlan,
        *,
        _current_adapter: str = ADAPTER_IMPLEMENTATION_SHA256,
        _current_protocol: str = PROTOCOL_SHA256,
        _verify_side_effect=None,
    ) -> CursorWorkspacePlan:
        with self._current_authority(
            adapter_fingerprint=_current_adapter,
            protocol_fingerprint=_current_protocol,
            verify_side_effect=_verify_side_effect,
        ):
            return revalidate_cursor_workspace_plan(
                plan,
                adapter_manifest=self.manifest,
            )

    def _binding_arguments(self):
        workspace_identity = self._plan().raw["workspace_root"]
        contract_identity = {
            "fingerprint": "3" * 64,
            "controller": "cursor-controller",
            "target": "cursor",
            "task_profile": QUALIFICATION_PROFILE,
        }
        run_identity = {
            "session": "cursor-session",
            "run_id": "cursor-run",
            "nonce": "cursor-nonce-0123456789",
        }
        compiled = compile_instruction_wrapper(
            target="cursor",
            task="CURSOR_BINDING_BODY_CANARY produce one bounded handoff",
            contract_identity=contract_identity,
            workspace_identity=workspace_identity,
            run_identity=run_identity,
            model_binding="default",
            effort_binding="default",
        )
        descriptor = build_cursor_workspace_addendum_descriptor(
            adapter_manifest_sha256=self.manifest_sha256,
            rendered_sha256=compiled.manifest["rendered_sha256"],
        )
        return {
            "descriptor": descriptor,
            "instruction_manifest": compiled.manifest,
            "effective_contract": compiled.rendered,
            "adapter_manifest": self.manifest,
            "admitted_lane_root": self.lane,
            "workspace_root": self.workspace,
            "expected_contract_identity": contract_identity,
            "expected_workspace_identity": workspace_identity,
            "expected_run_identity": run_identity,
        }

    def _bind(self, values=None):
        arguments = self._binding_arguments() if values is None else values
        with self._current_authority():
            return bind_cursor_workspace_plane(**arguments)

    def _binding_record(self, binding):
        with self._current_authority():
            return binding.record

    def _launch_argv(self, plan, *, manifest=None):
        with self._current_authority():
            return derive_cursor_workspace_launch_argv(
                plan,
                adapter_manifest=self.manifest if manifest is None else manifest,
            )

    def test_compiler_binding_is_deterministic_body_free_and_authority_disabled(self):
        values = self._binding_arguments()
        first = self._bind(values)
        second = self._bind(values)
        record = self._binding_record(first)
        self.assertEqual(record, self._binding_record(second))
        self.assertEqual(record["schema"], BINDING_SCHEMA)
        self.assertEqual(record["state"], BINDING_STATE)
        self.assertEqual(record["target"], "cursor")
        self.assertEqual(record["target_version"], CURSOR_VERSION)
        self.assertEqual(record["requested_model"], "default")
        self.assertEqual(record["observed_model"], "unavailable")
        self.assertEqual(record["config_fingerprint"], "unavailable")
        self.assertEqual(
            record["artifact"]["relative_path"],
            ".cursor/rules/puppet-%s.mdc" % record["effective_contract_sha256"],
        )
        plan = self._plan()
        launch_argv = self._launch_argv(plan)
        self.assertEqual(
            launch_argv,
            (
                self.manifest["executable"]["resolved_path"],
                "--yolo",
                "--sandbox",
                "disabled",
                "--workspace",
                str(self.workspace),
            ),
        )
        self.assertEqual(
            record["launch_argv_sha256"],
            sha256_bytes(canonical_json_bytes(list(launch_argv))),
        )
        for name in (
            "activation_authorized",
            "launch_authorized",
            "qualification_authorized",
        ):
            self.assertIs(record[name], False)
        encoded = json.dumps(record, sort_keys=True)
        self.assertNotIn("CURSOR_BINDING_BODY_CANARY", encoded)
        self.assertNotIn(str(self.workspace), encoded)
        self.assertNotIn("--yolo", encoded)
        self.assertNotIn("--sandbox", encoded)
        self.assertNotIn("--model", encoded)
        self.assertNotIn("--profile", encoded)
        self.assertNotIn("CURSOR_BINDING_BODY_CANARY", repr(first))
        self.assertFalse(hasattr(first, "from_dict"))

    def test_exact_launch_vector_rejects_selector_and_forbidden_flag_drift(self):
        plan = self._plan()
        cases = (
            ("missing-workspace", []),
            (
                "duplicate-workspace",
                [
                    "--workspace",
                    str(self.workspace),
                    "--workspace",
                    str(self.workspace),
                ],
            ),
            ("saved-workspace", ["--workspace", "saved-workspace"]),
            ("worktree", ["--worktree", str(self.workspace)]),
            ("worktree-base", ["--worktree-base", "main"]),
            ("add-dir", ["--add-dir", str(self.workspace)]),
            ("api-key", ["--api-key", "opaque"]),
            ("model", ["--model", "auto"]),
            ("profile", ["--profile", "puppet"]),
            ("config", ["--config", "puppet"]),
            ("system-prompt", ["--system-prompt", "body"]),
        )
        for case_id, delta in cases:
            raw = plan.to_dict()
            raw["launch_delta"] = {"argv": delta}
            forged = CursorWorkspacePlan(raw=raw)
            with (
                self.subTest(case_id=case_id),
                self.assertRaises((IdentityError, ValidationError)),
            ):
                self._launch_argv(forged)

    def test_launch_vector_rejects_self_consistent_base_argv_drift(self):
        plan = self._plan()
        forbidden_flags = (
            ["--model", "auto"],
            ["--api-key", "opaque"],
            ["--profile", "puppet"],
            ["--config", "puppet"],
            ["--system-prompt", "body"],
            ["--add-dir", str(self.workspace)],
            ["--worktree", str(self.workspace)],
        )
        for extra in forbidden_flags:
            changed = copy.deepcopy(self.manifest)
            changed["yolo_mapping"]["launch_argv"].extend(extra)
            changed = AdapterManifest.from_dict(changed).raw
            with self.subTest(extra=extra), self.assertRaises(IdentityError):
                self._launch_argv(plan, manifest=changed)

    def test_binding_rejects_contract_run_workspace_and_descriptor_replay(self):
        cases = ("contract", "run", "workspace", "descriptor", "bytes", "model")
        for case in cases:
            with self.subTest(case=case):
                values = self._binding_arguments()
                if case == "contract":
                    values["expected_contract_identity"] = {
                        **values["expected_contract_identity"],
                        "controller": "alternate-controller",
                    }
                elif case == "run":
                    values["expected_run_identity"] = {
                        **values["expected_run_identity"],
                        "run_id": "alternate-run",
                    }
                elif case == "workspace":
                    values["expected_workspace_identity"] = {
                        **values["expected_workspace_identity"],
                        "inode": values["expected_workspace_identity"]["inode"] + 1,
                    }
                elif case == "descriptor":
                    descriptor = copy.deepcopy(values["descriptor"])
                    descriptor["materialize"][0]["relative_path"] = (
                        ".cursor/rules/puppet-%s.mdc" % ("f" * 64)
                    )
                    values["descriptor"] = descriptor
                elif case == "bytes":
                    values["effective_contract"] += b"\ntampered"
                else:
                    manifest = copy.deepcopy(values["instruction_manifest"])
                    manifest["runtime_binding"]["model"] = "unavailable"
                    values["instruction_manifest"] = manifest
                with self.assertRaises((IdentityError, ValidationError)):
                    self._bind(values)

    def test_binding_rederivation_rejects_same_path_workspace_replacement(self):
        binding = self._bind()
        original = self.lane / "workspace-binding-original"
        self.workspace.rename(original)
        self.workspace.mkdir(mode=0o700)
        self.workspace.chmod(0o700)
        with self.assertRaises(IdentityError):
            self._binding_record(binding)

    def test_success_is_body_free_current_bound_and_planner_only(self):
        plan = self._plan()
        self.assertEqual(
            plan.raw["launch_delta"],
            {"argv": ["--workspace", str(self.workspace)]},
        )
        self.assertFalse(plan.raw["launch_authorized"])
        self.assertFalse(plan.raw["materialization_supported"])
        self.assertFalse(plan.raw["rollback_supported"])
        self.assertFalse(plan.raw["recovery_supported"])
        self.assertEqual(
            plan.raw["status"], {"surface": "hypothesis", "activation": "disabled"}
        )
        self.assertEqual(plan.raw["blockers"], list(BLOCKERS))
        self.assertEqual(
            plan.raw["planned_artifact"]["relative_path"],
            ".cursor/rules/puppet-qualification-01.mdc",
        )
        self.assertEqual(
            plan.raw["planned_artifact"]["write_mode"],
            "create_only_if_lifecycle_is_later_proved",
        )
        self.assertNotIn(self.body_marker, json.dumps(plan.to_dict()))
        self.assertEqual(list(self.workspace.iterdir()), [])
        self.assertFalse(plan.planned_artifact_path.exists())
        self.assertEqual(self._revalidate(plan).to_dict(), plan.to_dict())

    def test_production_path_calls_current_fingerprint_protocol_and_file_verifier(self):
        with (
            mock.patch.object(
                cursor_module,
                "adapter_implementation_fingerprint",
                return_value=ADAPTER_IMPLEMENTATION_SHA256,
            ) as fingerprint,
            mock.patch.object(cursor_module, "PROTOCOL_FINGERPRINT", PROTOCOL_SHA256),
            mock.patch.object(
                AdapterManifest, "verify_execution_files", autospec=True
            ) as verify_files,
        ):
            plan = plan_cursor_workspace_plane(**self._plan_arguments())
        fingerprint.assert_called_once_with()
        verify_files.assert_called_once()
        self.assertEqual(
            plan.raw["adapter_implementation_sha256"],
            ADAPTER_IMPLEMENTATION_SHA256,
        )
        self.assertEqual(plan.raw["adapter_protocol_sha256"], PROTOCOL_SHA256)

    def test_nonexistent_synthetic_execution_identity_is_not_current_proof(self):
        with (
            mock.patch.object(
                cursor_module,
                "adapter_implementation_fingerprint",
                return_value=ADAPTER_IMPLEMENTATION_SHA256,
            ),
            mock.patch.object(cursor_module, "PROTOCOL_FINGERPRINT", PROTOCOL_SHA256),
        ):
            with self.assertRaisesRegex(IdentityError, "unavailable"):
                plan_cursor_workspace_plane(**self._plan_arguments())

    def test_stale_but_self_consistent_manifest_is_rejected(self):
        stale_adapter = "d" * 64
        stale = _adapter_manifest(adapter_fingerprint=stale_adapter)
        stale_hash = AdapterManifest.from_dict(stale).fingerprint
        with self.assertRaisesRegex(IdentityError, "adapter authority is stale"):
            self._plan(
                adapter_manifest=stale,
                expected_manifest_sha256=stale_hash,
                expected_adapter_implementation_sha256=stale_adapter,
            )

    def test_live_execution_drift_from_current_manifest_is_rejected(self):
        with self.assertRaisesRegex(IdentityError, "live execution drift"):
            self._plan(_verify_side_effect=IdentityError("live execution drift"))

    def test_revalidation_repeats_every_current_authority_check(self):
        plan = self._plan()
        with self._current_authority() as (fingerprint, verify_files):
            self.assertEqual(
                revalidate_cursor_workspace_plan(
                    plan,
                    adapter_manifest=self.manifest,
                ).to_dict(),
                plan.to_dict(),
            )
        fingerprint.assert_called_once_with()
        verify_files.assert_called_once()

        with self.assertRaisesRegex(IdentityError, "adapter authority is stale"):
            self._revalidate(plan, _current_adapter="d" * 64)
        with self.assertRaisesRegex(IdentityError, "protocol authority is stale"):
            self._revalidate(plan, _current_protocol="e" * 64)
        with self.assertRaisesRegex(IdentityError, "live execution drift"):
            self._revalidate(
                plan,
                _verify_side_effect=IdentityError("live execution drift"),
            )

    def test_stale_adapter_and_protocol_authority_are_rejected(self):
        with self.assertRaisesRegex(IdentityError, "adapter authority is stale"):
            self._plan(_current_adapter="d" * 64)
        with self.assertRaisesRegex(IdentityError, "protocol authority is stale"):
            self._plan(_current_protocol="e" * 64)

    def test_wrong_version_manifest_and_exact_tuple_are_rejected(self):
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

    def test_existing_content_symlink_escape_and_private_mode_fail_closed(self):
        foreign = self.workspace / "ordinary.txt"
        foreign.write_text("not owned\n", encoding="utf-8")
        with self.assertRaisesRegex(ConflictError, "empty Puppet-owned scope"):
            self._plan()
        self.assertEqual(foreign.read_text(encoding="utf-8"), "not owned\n")
        foreign.unlink()

        outside = self.base / "outside"
        outside.mkdir(mode=0o700)
        linked = self.lane / "linked-workspace"
        linked.symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(IdentityError, "linked"):
            self._plan(workspace_root=linked)

        escaping = Path(str(self.lane / ".." / "outside"))
        with self.assertRaisesRegex(ValidationError, "normalized"):
            self._plan(workspace_root=escaping)

        self.workspace.chmod(0o755)
        with self.assertRaisesRegex(IdentityError, "current-UID 0700"):
            self._plan()

    def test_read_only_revalidation_rejects_root_and_preimage_drift(self):
        plan = self._plan()
        original = self.lane / "workspace-original"
        self.workspace.rename(original)
        self.workspace.mkdir(mode=0o700)
        with self.assertRaisesRegex(IdentityError, "root identity changed"):
            self._revalidate(plan)

        self.workspace.rmdir()
        original.rename(self.workspace)
        foreign = self.workspace / "foreign.txt"
        foreign.write_text("drift\n", encoding="utf-8")
        with self.assertRaisesRegex(ConflictError, "empty Puppet-owned scope"):
            self._revalidate(plan)
        self.assertEqual(foreign.read_text(encoding="utf-8"), "drift\n")

    def test_mutating_lifecycle_is_unconditionally_disabled(self):
        plan = self._plan()
        with (
            mock.patch.object(cursor_module.os, "unlink") as unlink,
            mock.patch.object(cursor_module.os, "rmdir") as rmdir,
            mock.patch.object(cursor_module.os, "mkdir") as mkdir,
        ):
            for operation in (
                lambda: materialize_cursor_workspace_plane(
                    plan, guidance=self.guidance, adapter_manifest=self.manifest
                ),
                lambda: verify_cursor_workspace_plane(
                    plan, receipt={}, adapter_manifest=self.manifest
                ),
                lambda: rollback_cursor_workspace_plane(
                    plan,
                    {},
                    exact_halt_proof={"exact_halt": True},
                    adapter_manifest=self.manifest,
                ),
                lambda: recover_cursor_workspace_plane(
                    plan,
                    rollback_record={"terminal_state": "rolled_back"},
                    adapter_manifest=self.manifest,
                ),
            ):
                with self.assertRaisesRegex(UnsupportedError, "remain disabled"):
                    operation()
        unlink.assert_not_called()
        rmdir.assert_not_called()
        mkdir.assert_not_called()
        self.assertEqual(list(self.workspace.iterdir()), [])

    def test_adversarial_path_swap_cannot_delete_an_unreceipted_replacement(self):
        plan = self._plan()
        replacement = self.workspace / ".cursor"
        replacement.mkdir()
        marker = replacement / "unreceipted.txt"
        marker.write_text("must survive\n", encoding="utf-8")
        forged_receipt = {
            "schema": "puppet.cursor-workspace-plane-receipt/v1",
            "artifact": {
                "relative_path": ".cursor/rules/puppet-qualification-01.mdc",
                "inode": marker.stat().st_ino,
            },
        }
        with (
            mock.patch.object(cursor_module.os, "unlink") as unlink,
            mock.patch.object(cursor_module.os, "rmdir") as rmdir,
        ):
            with self.assertRaisesRegex(UnsupportedError, "remain disabled"):
                rollback_cursor_workspace_plane(
                    plan,
                    forged_receipt,
                    exact_halt_proof={"exact_halt": True},
                    adapter_manifest=self.manifest,
                )
        unlink.assert_not_called()
        rmdir.assert_not_called()
        self.assertEqual(marker.read_text(encoding="utf-8"), "must survive\n")

    def test_canonical_forged_rollback_and_self_minted_halt_are_rejected(self):
        plan = self._plan()
        forged_rollback = {
            "artifact_sha256": plan.raw["planned_artifact"]["content_sha256"],
            "materialization_receipt_sha256": "c" * 64,
            "plan_sha256": plan.plan_sha256,
            "schema": "puppet.cursor-workspace-plane-rollback/v1",
            "simulated_exact_halt_proof_sha256": "d" * 64,
            "terminal_state": "rolled_back",
        }
        # Canonical JSON shape does not create authority.
        canonical = json.loads(
            json.dumps(forged_rollback, sort_keys=True, separators=(",", ":"))
        )
        with self.assertRaisesRegex(UnsupportedError, "remain disabled"):
            recover_cursor_workspace_plane(plan, rollback_record=canonical)
        with self.assertRaisesRegex(UnsupportedError, "remain disabled"):
            rollback_cursor_workspace_plane(
                plan,
                {},
                exact_halt_proof={
                    "target": "cursor",
                    "simulation": True,
                    "exact_halt": True,
                },
            )
        self.assertFalse(hasattr(cursor_module, "simulated_exact_halt_proof"))

    def test_plan_schema_tampering_and_scope_traversal_are_rejected(self):
        plan = self._plan()
        changed = plan.to_dict()
        changed["launch_authorized"] = True
        with self.assertRaisesRegex(UnsupportedError, "cannot authorize launch"):
            CursorWorkspacePlan.from_dict(changed)
        changed = plan.to_dict()
        changed["materialization_supported"] = True
        with self.assertRaisesRegex(UnsupportedError, "must remain disabled"):
            CursorWorkspacePlan.from_dict(changed)
        with self.assertRaisesRegex(ValidationError, "invalid Cursor plane scope"):
            self._plan(scope_id="../escape")

    def test_module_has_no_mutation_live_or_recursive_operation_surface(self):
        source = (SCRIPTS / "puppet_lib" / "cursor_workspace_plane.py").read_text(
            encoding="utf-8"
        )
        for forbidden in (
            "os.unlink(",
            "os.rmdir(",
            "os.mkdir(",
            "os.rename(",
            "os.replace(",
            "O_CREAT",
            "simulated_exact_halt_proof",
            "census_target",
            "import subprocess",
            "subprocess.",
            "from .tmux",
            "import socket",
            "os.system",
            "os.popen",
            ".rglob(",
            "rmtree(",
            "_current_authority_test_hook",
            "_CursorCurrentAuthorityTestHook",
        ):
            self.assertNotIn(forbidden, source)
        self.assertNotIn(
            "_current_authority_test_hook",
            inspect.signature(plan_cursor_workspace_plane).parameters,
        )
        self.assertNotIn(
            "_current_authority_test_hook",
            inspect.signature(revalidate_cursor_workspace_plan).parameters,
        )


if __name__ == "__main__":
    unittest.main()
