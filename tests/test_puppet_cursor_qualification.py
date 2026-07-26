from __future__ import annotations

import copy
import json
import sys
import unittest
from argparse import Namespace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "puppet" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from puppet_lib.adapter_manifest import AdapterManifest, PROBE_CAPABILITIES  # noqa: E402
from puppet_lib.cursor_qualification import (  # noqa: E402
    CURSOR_NATIVE_TRIGGER_SHA256,
    NATIVE_VIEW_SCHEMA,
    TERMINAL_QUALIFICATION_SCHEMA,
    build_cursor_activation_context,
    build_cursor_qualification_descriptor,
    build_cursor_qualification_request,
    build_cursor_terminal_qualification,
    cursor_probe_mapping_from_qualified,
    cursor_qualified_mapping,
    cursor_regular_launch_argv,
    materialize_cursor_activation,
    plan_cursor_activation,
    public_cursor_activation_context,
    record_cursor_native_view,
    revalidate_cursor_activation_context,
    render_cursor_mdc_wrapper,
    rollback_cursor_activation,
    validate_cursor_terminal_activation,
)
from puppet_lib.errors import (  # noqa: E402
    ConflictError,
    IdentityError,
    UnsupportedError,
    ValidationError,
)
from puppet_lib.instructions import compile_instruction_wrapper  # noqa: E402
from puppet_lib.plane_activation import (  # noqa: E402
    ACTIVATION_LIFECYCLE_SCOPE,
    PROBE_PLANE_ACTIVATION_SCHEMA,
)
from puppet_lib.safety import (  # noqa: E402
    atomic_write_json,
    canonical_json_bytes,
    sha256_bytes,
    sha256_file,
)
from tests.test_puppet_cursor_workspace_plane import _adapter_manifest  # noqa: E402
import adapter_lab  # noqa: E402


class CursorQualificationLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.workspace = self.root / "workspace"
        self.transaction = self.root / "transaction"
        self.profile = self.root / "profile"
        for path in (self.workspace, self.transaction, self.profile):
            path.mkdir(mode=0o700)
            path.chmod(0o700)
        (self.workspace / "fixture.json").write_text("{}\n", encoding="utf-8")
        for name in ("home", "config", "data"):
            path = self.profile / name
            path.mkdir(mode=0o700)
            path.chmod(0o700)
        self.manifest = _adapter_manifest()
        self.contract = compile_instruction_wrapper(
            target="cursor",
            task="write one bounded qualification handoff",
            contract_identity={
                "fingerprint": "1" * 64,
                "controller": "cursor-controller",
                "target": "cursor",
                "task_profile": "source-free-pass-b-v2",
            },
            workspace_identity={
                "fixture_fingerprint": "2" * 64,
                "workspace": "isolated_conformance_fixture",
            },
            run_identity={
                "session": "cursor-session",
                "run_id": "cursor-run",
                "nonce": "cursor-nonce",
            },
            model_binding="default",
            effort_binding="default",
        )
        self.descriptor = build_cursor_qualification_descriptor(
            adapter_manifest_sha256=AdapterManifest.from_dict(
                self.manifest
            ).fingerprint,
            mdc_wrapper_sha256=sha256_bytes(
                render_cursor_mdc_wrapper(self.contract.rendered)
            ),
        )
        self.execution_patch = mock.patch.object(
            AdapterManifest, "verify_execution_files", autospec=True
        )
        self.launch_execution_patch = mock.patch.object(
            AdapterManifest,
            "verify_launch_execution_environment",
            autospec=True,
        )
        self.execution_patch.start()
        self.launch_execution_patch.start()
        self.addCleanup(self.execution_patch.stop)
        self.addCleanup(self.launch_execution_patch.stop)

    def _plan(self):
        return plan_cursor_activation(
            descriptor=self.descriptor,
            adapter_manifest=self.manifest,
            effective_contract=self.contract.rendered,
            workspace_root=self.workspace,
            transaction_root=self.transaction,
        )

    def _context(self, plan, receipt):
        return build_cursor_activation_context(
            plan,
            materialization_receipt=receipt,
            adapter_manifest=self.manifest,
            session="cursor-session",
            run_id="cursor-run",
            source_environment={"HOME": str(self.profile / "home")},
            bindings={
                "CURSOR_CONFIG_DIR": str(self.profile / "config"),
                "CURSOR_DATA_DIR": str(self.profile / "data"),
                "AGENT_CLI_CREDENTIAL_STORE": "file",
            },
            admitted_lane_root=self.profile,
        )

    @staticmethod
    def _halt():
        return {
            "schema_version": 1,
            "timestamp": "2026-07-26T00:00:00Z",
            "session": "cursor-session",
            "target_pid": 4242,
            "reason": "accepted_probe_halt",
            "signal": "exact_registered_pid_sigint",
            "signal_sent": True,
            "stopped": True,
            "tmux_preserved": True,
            "cleanup_scope": "exact_new_target_only",
        }

    def test_create_only_context_exact_halt_and_rollback_round_trip(self):
        plan = self._plan()
        self.assertEqual(
            self.descriptor["materialize"][0]["content_ref"],
            "cursor_mdc_always_apply_wrapper",
        )
        self.assertIn(
            "cursor_workspace_mdc_always_apply_wrapper_hash_named",
            self.descriptor["assertions"],
        )
        self.assertIn(
            "cursor_workspace_effective_contract_body_hash_bound",
            self.descriptor["assertions"],
        )
        receipt = materialize_cursor_activation(
            plan, effective_contract=self.contract.rendered
        )
        artifact = self.workspace / plan["artifact"]["relative_path"]
        wrapper = render_cursor_mdc_wrapper(self.contract.rendered)
        self.assertEqual(artifact.read_bytes(), wrapper)
        self.assertTrue(
            wrapper.startswith(
                b"---\n"
                b'description: "Puppet-managed qualification contract; '
                b'remove after the exact owned session halts."\n'
                b'globs: "**/*"\n'
                b"alwaysApply: true\n"
                b"---\n\n"
            )
        )
        self.assertEqual(
            plan["artifact"]["wrapper_sha256"], sha256_bytes(wrapper)
        )
        self.assertEqual(
            plan["artifact"]["effective_contract_sha256"],
            self.contract.manifest["rendered_sha256"],
        )
        self.assertEqual(
            receipt["artifact"]["wrapper_sha256"],
            plan["artifact"]["wrapper_sha256"],
        )
        self.assertEqual(
            receipt["artifact"]["effective_contract_sha256"],
            plan["artifact"]["effective_contract_sha256"],
        )
        self.assertEqual(artifact.stat().st_mode & 0o777, 0o600)
        with self.assertRaises(ConflictError):
            materialize_cursor_activation(
                plan, effective_contract=self.contract.rendered
            )
        context = self._context(plan, receipt)
        self.assertEqual(
            context["argv"][-2:], ["--workspace", str(self.workspace)]
        )
        self.assertEqual(
            revalidate_cursor_activation_context(
                context,
                plan,
                materialization_receipt=receipt,
                adapter_manifest=self.manifest,
                session="cursor-session",
                run_id="cursor-run",
                source_environment={"HOME": str(self.profile / "home")},
                bindings={
                    "CURSOR_CONFIG_DIR": str(self.profile / "config"),
                    "CURSOR_DATA_DIR": str(self.profile / "data"),
                    "AGENT_CLI_CREDENTIAL_STORE": "file",
                },
                admitted_lane_root=self.profile,
            ),
            context,
        )
        rollback = rollback_cursor_activation(
            plan,
            materialization_receipt=receipt,
            exact_halt_receipt=self._halt(),
        )
        self.assertEqual(rollback["state"], "rolled_back_after_exact_halt")
        self.assertFalse(artifact.exists())
        self.assertFalse((self.workspace / ".cursor").exists())

        intent = json.loads(
            (self.transaction / "activation-intent.json").read_text()
        )
        stored_receipt = json.loads(
            (self.transaction / "activation-receipt.json").read_text()
        )
        rollback_intent = json.loads(
            (self.transaction / "rollback-intent.json").read_text()
        )
        stored_rollback = json.loads(
            (self.transaction / "rollback-receipt.json").read_text()
        )
        public_context = public_cursor_activation_context(context)
        summary = {
            "schema": PROBE_PLANE_ACTIVATION_SCHEMA,
            "qualification_scope": ACTIVATION_LIFECYCLE_SCOPE,
            "terminal_state": "rolled_back",
            "descriptor_sha256": plan["descriptor_sha256"],
            "plan_sha256": plan["plan_sha256"],
            "intent_sha256": sha256_bytes(canonical_json_bytes(intent)),
            "materialization_receipt_sha256": sha256_bytes(
                canonical_json_bytes(stored_receipt)
            ),
            "launch_context_sha256": sha256_bytes(
                canonical_json_bytes(public_context)
            ),
            "artifact_sha256": plan["artifact"]["effective_contract_sha256"],
            "initial_trigger_sha256": CURSOR_NATIVE_TRIGGER_SHA256,
            "rollback_intent_sha256": sha256_bytes(
                canonical_json_bytes(rollback_intent)
            ),
            "rollback_receipt_sha256": sha256_bytes(
                canonical_json_bytes(stored_rollback)
            ),
        }
        self.assertEqual(
            validate_cursor_terminal_activation(
                summary,
                descriptor=self.descriptor,
                intent=intent,
                materialization_receipt=stored_receipt,
                context=public_context,
                launch_plan=context["admitted_launch_plan"],
                rollback_intent=rollback_intent,
                rollback_receipt=stored_rollback,
            ),
            summary,
        )

    def test_rollback_rejects_self_minted_halt_and_preserves_rule(self):
        plan = self._plan()
        receipt = materialize_cursor_activation(
            plan, effective_contract=self.contract.rendered
        )
        forged = self._halt()
        forged["signal_sent"] = False
        with self.assertRaisesRegex(ValidationError, "exact halt"):
            rollback_cursor_activation(
                plan,
                materialization_receipt=receipt,
                exact_halt_receipt=forged,
            )
        self.assertTrue(
            (self.workspace / plan["artifact"]["relative_path"]).is_file()
        )

    def test_frontmatter_body_and_post_plan_substitution_fail_closed(self):
        plan = self._plan()
        substituted = self.contract.rendered + b"\nPOST_PLAN_SUBSTITUTION\n"
        with self.assertRaisesRegex(IdentityError, "changed after planning"):
            materialize_cursor_activation(
                plan,
                effective_contract=substituted,
            )
        self.assertFalse((self.workspace / ".cursor").exists())

        for label, mutate in (
            (
                "frontmatter",
                lambda payload: payload.replace(
                    b"alwaysApply: true", b"alwaysApply: false", 1
                ),
            ),
            (
                "body",
                lambda payload: payload[:-2] + b"X\n",
            ),
        ):
            with self.subTest(label=label):
                transaction = self.root / ("transaction-" + label)
                transaction.mkdir(mode=0o700)
                transaction.chmod(0o700)
                descriptor = build_cursor_qualification_descriptor(
                    adapter_manifest_sha256=AdapterManifest.from_dict(
                        self.manifest
                    ).fingerprint,
                    mdc_wrapper_sha256=sha256_bytes(
                        render_cursor_mdc_wrapper(self.contract.rendered)
                    ),
                )
                plan = plan_cursor_activation(
                    descriptor=descriptor,
                    adapter_manifest=self.manifest,
                    effective_contract=self.contract.rendered,
                    workspace_root=self.workspace,
                    transaction_root=transaction,
                )
                receipt = materialize_cursor_activation(
                    plan, effective_contract=self.contract.rendered
                )
                artifact = self.workspace / plan["artifact"]["relative_path"]
                original = artifact.read_bytes()
                artifact.write_bytes(mutate(original))
                artifact.chmod(0o600)
                with self.assertRaises(IdentityError):
                    self._context(plan, receipt)
                artifact.write_bytes(original)
                artifact.chmod(0o600)
                rollback_cursor_activation(
                    plan,
                    materialization_receipt=receipt,
                    exact_halt_receipt=self._halt(),
                )

    def test_rollback_preserves_rule_when_activation_root_gains_foreign_content(self):
        plan = self._plan()
        receipt = materialize_cursor_activation(
            plan, effective_contract=self.contract.rendered
        )
        foreign = self.workspace / ".cursor" / "foreign"
        foreign.write_text("do not remove\n", encoding="utf-8")
        with self.assertRaisesRegex(ConflictError, "foreign content"):
            rollback_cursor_activation(
                plan,
                materialization_receipt=receipt,
                exact_halt_receipt=self._halt(),
            )
        self.assertTrue(
            (self.workspace / plan["artifact"]["relative_path"]).is_file()
        )
        self.assertEqual(foreign.read_text(encoding="utf-8"), "do not remove\n")

    def test_workspace_collision_and_artifact_replacement_fail_closed(self):
        (self.workspace / ".cursor").mkdir()
        with self.assertRaisesRegex(ConflictError, "absent"):
            self._plan()
        (self.workspace / ".cursor").rmdir()
        plan = self._plan()
        receipt = materialize_cursor_activation(
            plan, effective_contract=self.contract.rendered
        )
        artifact = self.workspace / plan["artifact"]["relative_path"]
        # Keep the original inode allocated while creating the replacement.
        # Some Linux filesystems immediately reuse an unlinked inode, which
        # makes an unlink/create fixture indistinguishable at the vnode layer.
        artifact.rename(artifact.with_name(artifact.name + ".replaced"))
        artifact.write_bytes(render_cursor_mdc_wrapper(self.contract.rendered))
        artifact.chmod(0o600)
        with self.assertRaisesRegex(IdentityError, "vnode changed"):
            self._context(plan, receipt)

    def test_mapping_closure_and_dynamic_launch_are_exact(self):
        doctor = self.manifest["yolo_mapping"]
        qualified = cursor_qualified_mapping(doctor)
        self.assertTrue(qualified["complete"])
        self.assertTrue(qualified["project_isolation_declared"])
        self.assertEqual(cursor_probe_mapping_from_qualified(qualified), doctor)
        argv = cursor_regular_launch_argv(
            qualified,
            base_argv=qualified["launch_argv"],
            workspace_root=self.workspace,
        )
        self.assertEqual(argv[-2:], ["--workspace", str(self.workspace)])
        with self.assertRaises(IdentityError):
            cursor_regular_launch_argv(
                qualified,
                base_argv=[*qualified["launch_argv"], "--model", "auto"],
                workspace_root=self.workspace,
            )

    def test_request_is_body_free_and_grants_no_authority(self):
        request = build_cursor_qualification_request(
            adapter_manifest_sha256=AdapterManifest.from_dict(
                self.manifest
            ).fingerprint
        )
        self.assertEqual(request["activation"], "qualification_only")
        self.assertFalse(request["materialization_authorized"])
        self.assertFalse(request["launch_authorized"])
        self.assertFalse(request["qualification_authorized"])
        self.assertNotIn(
            self.contract.manifest["rendered_sha256"],
            json.dumps(request, sort_keys=True),
        )


class CursorNativeViewTests(unittest.TestCase):
    def test_structural_read_only_attach_and_detach_receipt(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "tmux-authority").mkdir(mode=0o700)
            tmux = {
                "socket": str(root / "tmux-authority" / "cursor.sock"),
                "session": "cursor-session",
                "server_identity": {"pid": 123, "start": "birth"},
            }
            atomic_write_json(
                root / "state.json",
                {
                    "target": "cursor",
                    "run_id": "cursor-run",
                    "attach_command": "tmux -r attach",
                },
            )
            atomic_write_json(
                root / "evidence.json",
                {"target": "cursor", "run_id": "cursor-run", "tmux": tmux},
            )
            controller = mock.Mock()
            controller.viewer_clients.side_effect = [
                [],
                [
                    {
                        "pid": 456,
                        "tty": "/dev/ttys001",
                        "read_only": True,
                        "session": "cursor-session",
                    }
                ],
                [],
            ]
            ticks = iter([0.0, 0.1, 0.2, 0.3])
            result = record_cursor_native_view(
                run_root=root,
                timeout=1.0,
                _tmux_factory=lambda _authority: controller,
                _sleep_fn=lambda _seconds: None,
                _monotonic_fn=lambda: next(ticks),
            )
            self.assertEqual(result["schema"], NATIVE_VIEW_SCHEMA)
            self.assertTrue(result["read_only"])
            self.assertTrue(result["attached"])
            self.assertTrue(result["detached"])
            self.assertTrue((root / "cursor-native-view.json").is_file())


class CursorTerminalJoinTests(unittest.TestCase):
    def _receipt(self, *, run_id: str, activated: bool):
        return {
            "target": "cursor",
            "run_id": run_id,
            "controller": "controller-a",
            "campaign_id": "campaign-a",
            "goal_fingerprint": "1" * 64,
            "executable_fingerprint": "2" * 64,
            "execution_fingerprint": "3" * 64,
            "version_fingerprint": "4" * 64,
            "platform_fingerprint": "5" * 64,
            "adapter_fingerprint": "6" * 64,
            "protocol_fingerprint": "7" * 64,
            "yolo_mapping_sha256": "8" * 64,
            "subscription_profile_sha256": "9" * 64,
            "instruction_policy_fingerprint": "a" * 64,
            "session_profile": "regular",
            "capabilities": list(PROBE_CAPABILITIES),
            "accepted_checkpoint_id": "b" * 64,
            "acceptance_sha256": "c" * 64,
            "halt_receipt_sha256": "d" * 64,
            "plane_activation": (
                {"terminal_state": "rolled_back"} if activated else None
            ),
        }

    def test_pair_requires_activation_control_profile_and_native_view_join(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            activated_root = root / "activated"
            ordinary_root = root / "ordinary"
            activated_root.mkdir()
            ordinary_root.mkdir()
            activated_path = activated_root / "receipt.json"
            ordinary_path = ordinary_root / "receipt.json"
            atomic_write_json(activated_path, {"placeholder": "activated"})
            atomic_write_json(ordinary_path, {"placeholder": "ordinary"})
            activated = self._receipt(run_id="activated-run", activated=True)
            ordinary = self._receipt(run_id="ordinary-run", activated=False)
            activated_tmux = {
                "socket": "/private/cursor.sock",
                "session": "activated-session",
            }
            attach = "tmux -r attach -t activated-session"
            atomic_write_json(
                activated_root / "state.json",
                {
                    "session": "activated-session",
                    "attach_command": attach,
                },
            )
            atomic_write_json(
                activated_root / "evidence.json",
                {
                    "tmux": activated_tmux,
                    "launch_identity": {"cwd": "/private/activated"},
                    "fixture_fingerprint_before": "e" * 64,
                    "fixture_fingerprint_after": "e" * 64,
                },
            )
            atomic_write_json(
                ordinary_root / "evidence.json",
                {
                    "launch_identity": {"cwd": "/private/ordinary"},
                    "fixture_fingerprint_before": "f" * 64,
                    "fixture_fingerprint_after": "f" * 64,
                },
            )
            native_view_path = activated_root / "cursor-native-view.json"
            atomic_write_json(
                native_view_path,
                {
                    "schema": NATIVE_VIEW_SCHEMA,
                    "target": "cursor",
                    "run_id": "activated-run",
                    "session": "activated-session",
                    "tmux_identity_sha256": sha256_bytes(
                        canonical_json_bytes(activated_tmux)
                    ),
                    "attach_command_sha256": sha256_bytes(
                        canonical_json_bytes(attach)
                    ),
                    "viewer": {
                        "pid": 99,
                        "tty": "/dev/ttys001",
                        "read_only": True,
                        "session": "activated-session",
                    },
                    "read_only": True,
                    "attached": True,
                    "detached": True,
                },
            )
            with (
                mock.patch(
                    "puppet_lib.adapter_manifest.verify_qualification_receipt",
                    side_effect=[activated, ordinary],
                ),
                mock.patch(
                    "puppet_lib.authority.attest_qualification",
                    return_value={"attested": True},
                ),
            ):
                terminal = build_cursor_terminal_qualification(
                    activated_receipt_path=activated_path,
                    ordinary_receipt_path=ordinary_path,
                    native_view_path=native_view_path,
                    authority_root=root / "authority",
                )
            self.assertEqual(terminal["schema"], TERMINAL_QUALIFICATION_SCHEMA)
            self.assertEqual(
                terminal["terminal_state"],
                "paired_control_verified_after_exact_halt_and_rollback",
            )
            self.assertEqual(
                terminal["subscription_profile_sha256"],
                activated["subscription_profile_sha256"],
            )
            self.assertTrue(terminal["no_bleed"]["ordinary_activation_absent"])
            self.assertEqual(terminal["default_model"]["observed"], "unavailable")

            mismatched = copy.deepcopy(ordinary)
            mismatched["subscription_profile_sha256"] = "0" * 64
            with (
                mock.patch(
                    "puppet_lib.adapter_manifest.verify_qualification_receipt",
                    side_effect=[activated, mismatched],
                ),
                self.assertRaisesRegex(IdentityError, "authority differs"),
            ):
                build_cursor_terminal_qualification(
                    activated_receipt_path=activated_path,
                    ordinary_receipt_path=ordinary_path,
                    native_view_path=native_view_path,
                )

    def test_adapter_lab_promotes_only_terminal_pair(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest_path = root / "cursor.json"
            mapping_path = root / "mapping.json"
            receipt_path = root / "terminal.json"
            out = root / "qualified.json"
            raw = _adapter_manifest()
            atomic_write_json(manifest_path, raw)
            atomic_write_json(mapping_path, raw["yolo_mapping"])
            atomic_write_json(receipt_path, {"terminal": True})
            terminal = {
                "schema": TERMINAL_QUALIFICATION_SCHEMA,
                "target": "cursor",
                "session_profile": "regular",
                "capabilities": list(PROBE_CAPABILITIES),
            }
            args = Namespace(
                manifest=manifest_path,
                mapping=mapping_path,
                receipt=receipt_path,
                out=out,
            )
            with (
                mock.patch.object(
                    adapter_lab, "_verified_receipt", return_value=terminal
                ),
                mock.patch.object(
                    AdapterManifest,
                    "verify_qualification",
                    autospec=True,
                    return_value=terminal,
                ),
            ):
                result = adapter_lab._qualify(args)
            qualified = AdapterManifest.from_path(out)
            self.assertEqual(result["target"], "cursor")
            self.assertFalse(qualified.raw["doctor_only"])
            self.assertTrue(qualified.raw["yolo_mapping"]["complete"])
            self.assertTrue(
                qualified.raw["yolo_mapping"]["project_isolation_declared"]
            )

            generic = {
                "target": "cursor",
                "session_profile": "regular",
                "capabilities": list(PROBE_CAPABILITIES),
                "plane_activation": None,
            }
            with (
                mock.patch.object(
                    adapter_lab, "_verified_receipt", return_value=generic
                ),
                self.assertRaisesRegex(UnsupportedError, "terminal paired"),
            ):
                adapter_lab._qualify(
                    Namespace(
                        manifest=manifest_path,
                        mapping=mapping_path,
                        receipt=receipt_path,
                        out=root / "must-not-exist.json",
                    )
                )

    def test_adapter_lab_cursor_request_is_create_only(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest_path = root / "cursor.json"
            request_path = root / "cursor-request.json"
            atomic_write_json(manifest_path, _adapter_manifest())
            result = adapter_lab._cursor_request(
                Namespace(manifest=manifest_path, out=request_path)
            )
            self.assertEqual(result["authority"], "request_only")
            request = json.loads(request_path.read_text(encoding="utf-8"))
            self.assertFalse(request["materialization_authorized"])
            with self.assertRaisesRegex(ValidationError, "already exists"):
                adapter_lab._cursor_request(
                    Namespace(manifest=manifest_path, out=request_path)
                )


if __name__ == "__main__":
    unittest.main()
