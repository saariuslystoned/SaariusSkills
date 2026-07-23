from __future__ import annotations

import ast
import inspect
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "puppet" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import adapter_lab  # noqa: E402
from puppet_lib import adapter_manifest as adapter_manifest_module  # noqa: E402
from puppet_lib import agy_launch as agy_launch_module  # noqa: E402
from puppet_lib import probe as puppet_probe  # noqa: E402
from puppet_lib import session as puppet_session  # noqa: E402
from puppet_lib.adapter_manifest import AdapterManifest  # noqa: E402
from puppet_lib.agy_launch import (  # noqa: E402
    AGY_NON_REGULAR_AUTHORITY_BLOCKER_ID,
    AGY_REGULAR_AUTHORITY_BLOCKERS,
    AGY_REGULAR_VERDICT_SCHEMA,
    agy_authority_blockers,
    agy_regular_verdict,
    require_agy_regular_launch_authority,
)
from puppet_lib.errors import UnsupportedError  # noqa: E402
from puppet_lib.instructions import instruction_policy_fingerprint  # noqa: E402
from puppet_lib.probe import PROBE_PROFILE, run_probe  # noqa: E402
from puppet_lib.safety import sha256_file  # noqa: E402


class AgyRegularFenceTests(unittest.TestCase):
    def test_pure_body_free_verdict_has_exact_immutable_blockers(self):
        verdict = agy_regular_verdict()
        self.assertEqual(
            verdict,
            {
                "schema": AGY_REGULAR_VERDICT_SCHEMA,
                "target": "agy",
                "session_profile": "regular",
                "status": "unsupported_planner_only",
                "launch_authorized": False,
                "qualification_authorized": False,
                "blockers": AGY_REGULAR_AUTHORITY_BLOCKERS,
            },
        )
        self.assertIsInstance(verdict["blockers"], tuple)
        self.assertEqual(
            verdict["blockers"],
            (
                "agy_config_root_isolation_unproved",
                "agy_sandbox_off_unproved",
                "agy_native_instruction_plane_unqualified",
                "agy_default_model_unobserved",
                "agy_ordinary_session_no_bleed_unproved",
            ),
        )
        serialized = json.dumps(verdict, sort_keys=True)
        for canary in (
            "PUPPET_TASK_BODY_CANARY",
            "operator prompt",
            "authentication value",
            "configuration value",
        ):
            self.assertNotIn(canary, serialized)

        source = inspect.getsource(agy_launch_module)
        tree = ast.parse(source)
        imported_roots = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_roots.update(
                    alias.name.split(".", 1)[0] for alias in node.names
                )
            elif isinstance(node, ast.ImportFrom):
                imported_roots.add((node.module or "").split(".", 1)[0])
        self.assertTrue(imported_roots <= {"__future__", "typing", "errors"})
        for forbidden in (
            "subprocess",
            "os.environ",
            "active_target_processes",
            "process_birth_identity",
            "SessionRegistry",
            "TmuxController",
            "read_json",
            "write_text",
        ):
            self.assertNotIn(forbidden, source)

    def test_doctor_keeps_exact_blockers_under_qualified_override(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            executable = root / "synthetic-agy"
            executable.write_bytes(b"synthetic")
            contract = SimpleNamespace(
                target="agy",
                controller="codex",
                campaign_authorization_id="campaign-agy-fence",
                session_profile="regular",
                requested_model=None,
                requested_effort=None,
                repo=root,
                branch="codex/agy-fence",
                fingerprint="a" * 64,
            )
            manifest = SimpleNamespace(
                target="agy",
                fingerprint="b" * 64,
                raw={
                    "executable": {
                        "resolved_path": str(executable),
                        "sha256": sha256_file(executable),
                    },
                    "yolo_mapping": {"complete": True},
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
                },
                verify_qualification=mock.Mock(
                    return_value={
                        "instruction_policy_fingerprint": instruction_policy_fingerprint(
                            target="agy"
                        )
                    }
                ),
            )
            active = [{"pid": 404}]
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
                    puppet_session,
                    "_authorization",
                    return_value={"campaign_id": "campaign-agy-fence", "goal": {}},
                ),
                mock.patch.object(
                    puppet_session,
                    "_qualification_authority",
                    return_value={
                        "controller": "codex",
                        "campaign_id": "campaign-agy-fence",
                        "goal_fingerprint": "c" * 64,
                    },
                ),
                mock.patch.object(
                    puppet_session,
                    "_workspace_snapshot",
                    return_value={
                        "branch": contract.branch,
                        "head": "d" * 40,
                        "tree": "e" * 40,
                        "dirty": False,
                    },
                ),
                mock.patch.object(
                    puppet_session.TmuxController, "available", return_value=True
                ),
                mock.patch.object(
                    puppet_session, "_active_processes", return_value=active
                ) as process_query,
                mock.patch.object(
                    puppet_session,
                    "_parallel_target_override",
                    return_value=True,
                ) as override,
            ):
                report = puppet_session.doctor(
                    contract_path=root / "contract.json",
                    manifest_path=root / "manifest.json",
                    authorization_path=root / "authorization.json",
                    proof_root=root,
                    state_root=root,
                )
            process_query.assert_called_once_with("agy", manifest)
            override.assert_called_once_with(mock.ANY, "agy", active)
            self.assertTrue(report["parallel_target_override"])
            self.assertFalse(report["launch_ready"])
            for blocker in AGY_REGULAR_AUTHORITY_BLOCKERS:
                self.assertIn(blocker, report["blockers"])

    def test_non_regular_profiles_cannot_borrow_regular_authority(self):
        for profile in (None, "goal", "teamwork-preview", "caller-profile"):
            with self.subTest(profile=profile):
                with self.assertRaisesRegex(UnsupportedError, "non-regular"):
                    require_agy_regular_launch_authority(profile)
                self.assertEqual(
                    agy_authority_blockers(profile),
                    AGY_REGULAR_AUTHORITY_BLOCKERS
                    + (AGY_NON_REGULAR_AUTHORITY_BLOCKER_ID,),
                )
        with self.assertRaisesRegex(UnsupportedError, "planner-only"):
            require_agy_regular_launch_authority("regular")
        self.assertEqual(
            agy_authority_blockers("regular"), AGY_REGULAR_AUTHORITY_BLOCKERS
        )

    def test_launch_rejects_before_doctor_process_environment_or_tmux(self):
        contract = SimpleNamespace(target="agy", session_profile="regular")
        doctor = mock.Mock(side_effect=AssertionError("doctor must not run"))
        process_query = mock.Mock(
            side_effect=AssertionError("process query must not run")
        )
        environment = mock.Mock(
            side_effect=AssertionError("launch environment must not build")
        )
        tmux = mock.Mock(side_effect=AssertionError("tmux must not construct"))
        process_birth = mock.Mock(
            side_effect=AssertionError("process callback must not run")
        )
        sleep = mock.Mock(side_effect=AssertionError("sleep callback must not run"))
        execution_sleep = mock.Mock(
            side_effect=AssertionError("execution sleep callback must not run")
        )
        monotonic = mock.Mock(
            side_effect=AssertionError("monotonic callback must not run")
        )
        with (
            mock.patch.object(
                puppet_session.Contract, "from_path", return_value=contract
            ),
            mock.patch.object(puppet_session, "doctor", doctor),
            mock.patch.object(puppet_session, "_active_processes", process_query),
            mock.patch.object(puppet_session, "build_launch_identity", environment),
            mock.patch.object(puppet_session, "TmuxController", tmux),
        ):
            with self.assertRaisesRegex(UnsupportedError, "planner-only"):
                puppet_session.launch(
                    session="puppet-agy-fenced",
                    contract_path=Path("/does/not/matter/contract.json"),
                    manifest_path=Path("/does/not/matter/manifest.json"),
                    authorization_path=Path("/does/not/matter/authorization.json"),
                    proof_root=Path("/does/not/matter/proof"),
                    state_root=Path("/does/not/matter/state"),
                    supervisor_executable=Path("/does/not/matter/supervisor"),
                    prompt="PUPPET_TASK_BODY_CANARY",
                    _sleep_fn=sleep,
                    _execution_sleep_fn=execution_sleep,
                    _execution_monotonic_fn=monotonic,
                    _process_birth_fn=process_birth,
                )
        for sentinel in (
            doctor,
            process_query,
            environment,
            tmux,
            process_birth,
            sleep,
            execution_sleep,
            monotonic,
        ):
            sentinel.assert_not_called()

    def test_probe_rejects_before_mapping_census_process_proof_or_tmux(self):
        with tempfile.TemporaryDirectory() as temporary:
            proof_root = Path(temporary).resolve() / "must-not-exist"
            mapping = mock.Mock(side_effect=AssertionError("mapping must not run"))
            census = mock.Mock(side_effect=AssertionError("census must not run"))
            active = mock.Mock(side_effect=AssertionError("process query must not run"))
            tmux = mock.Mock(side_effect=AssertionError("tmux must not construct"))
            adapter = mock.Mock(
                side_effect=AssertionError("adapter fingerprint must not run")
            )
            population = mock.Mock(
                side_effect=AssertionError("population callback must not run")
            )
            process_birth = mock.Mock(
                side_effect=AssertionError("process callback must not run")
            )
            with mock.patch.object(puppet_probe, "_validated_mapping", mapping):
                with self.assertRaisesRegex(UnsupportedError, "planner-only"):
                    run_probe(
                        target="agy",
                        profile=PROBE_PROFILE,
                        session_profile="regular",
                        proof_root=proof_root,
                        manifest_path=Path("/does/not/matter/manifest.json"),
                        mapping_path=Path("/does/not/matter/mapping.json"),
                        authorization_path=Path("/does/not/matter/authorization.json"),
                        controller="codex",
                        goal_repo=Path("/does/not/matter/repo"),
                        expected_campaign_id="campaign-agy-fence",
                        expected_goal={
                            "repository": "saariuslystoned/SaariusSkills",
                            "commit": "a" * 40,
                            "path": "plans/puppet/codex-goal-regular-qualification.md",
                            "sha256": "b" * 64,
                        },
                        _tmux_factory=tmux,
                        _process_birth_fn=process_birth,
                        _active_processes_fn=active,
                        _continuous_population_fn=population,
                        _population_snapshot_fn=population,
                        _census_target_fn=census,
                        _adapter_fingerprint_fn=adapter,
                    )
            for sentinel in (
                mapping,
                census,
                active,
                tmux,
                adapter,
                population,
                process_birth,
            ):
                sentinel.assert_not_called()
            self.assertFalse(proof_root.exists())

    def test_manifest_and_qualify_reject_fallback_wrapper_agy(self):
        synthetic_qualified = AdapterManifest(
            raw={"target": "agy", "doctor_only": False}
        )
        with self.assertRaisesRegex(UnsupportedError, "planner-only"):
            synthetic_qualified.verify_qualification()

        base = SimpleNamespace(target="agy", raw={"doctor_only": True})
        fallback_receipt = {
            "target": "agy",
            "plane_activation": None,
            "instruction_wrapper": {
                "delivery_transport": "interactive_fallback_wrapper"
            },
        }
        verified = mock.Mock(return_value=fallback_receipt)
        args = SimpleNamespace(
            manifest=Path("/does/not/matter/manifest.json"),
            mapping=Path("/does/not/matter/mapping.json"),
            receipt=Path("/does/not/matter/receipt.json"),
            out=Path("/does/not/matter/out.json"),
        )
        with (
            mock.patch.object(
                adapter_lab.AdapterManifest, "from_path", return_value=base
            ),
            mock.patch.object(adapter_lab, "_verified_receipt", verified),
        ):
            with self.assertRaisesRegex(UnsupportedError, "planner-only"):
                adapter_lab._qualify(args)
        verified.assert_not_called()

    def test_manifest_authority_requires_explicit_regular_profile_before_receipt_io(
        self,
    ):
        manifest = AdapterManifest(
            raw={
                "target": "agy",
                "doctor_only": False,
                "qualification": {
                    "session_profile": "regular",
                    "receipt_path": "/does/not/matter/receipt.json",
                    "receipt_sha256": "a" * 64,
                },
            }
        )
        receipt_read = mock.Mock(
            side_effect=AssertionError("explicit regular may reach receipt IO")
        )

        def future_authority(profile):
            if profile != "regular":
                raise UnsupportedError("non-regular profile stays fenced")

        with (
            mock.patch.object(
                adapter_manifest_module,
                "require_agy_regular_launch_authority",
                side_effect=future_authority,
            ) as authority,
            mock.patch.object(adapter_manifest_module, "sha256_file", receipt_read),
        ):
            for profile in (None, "", "goal", "teamwork-preview", "caller-profile"):
                with self.subTest(profile=profile):
                    with self.assertRaisesRegex(UnsupportedError, "non-regular"):
                        manifest.verify_qualification(expected_session_profile=profile)
            receipt_read.assert_not_called()
            self.assertEqual(
                [call.args[0] for call in authority.call_args_list],
                [None, "", "goal", "teamwork-preview", "caller-profile"],
            )

            with self.assertRaisesRegex(
                AssertionError, "explicit regular may reach receipt IO"
            ):
                manifest.verify_qualification(expected_session_profile="regular")
            receipt_read.assert_called_once()


if __name__ == "__main__":
    unittest.main()
