from __future__ import annotations

import ast
import io
import inspect
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "puppet" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import adapter_lab  # noqa: E402
import puppet as puppet_cli  # noqa: E402
import puppet_lib.campaign as campaign  # noqa: E402
from puppet_lib import adapter_manifest as adapter_manifest_module  # noqa: E402
from puppet_lib import agy_launch as agy_launch_module  # noqa: E402
from puppet_lib import probe as puppet_probe  # noqa: E402
from puppet_lib import session as puppet_session  # noqa: E402
from puppet_lib.adapter_manifest import AdapterManifest  # noqa: E402
from puppet_lib.agy_launch import (  # noqa: E402
    AGY_NON_REGULAR_AUTHORITY_BLOCKER_ID,
    AGY_REGULAR_AUTHORITY_BLOCKERS,
    AGY_REGULAR_VERDICT_SCHEMA,
    AGY_SHARED_VENDOR_AUTH_LIMITATION,
    agy_authority_blockers,
    agy_regular_verdict,
    require_agy_regular_launch_authority,
)
from puppet_lib.errors import IdentityError, UnsupportedError, ValidationError  # noqa: E402
from puppet_lib.probe import PROBE_PROFILE, run_probe  # noqa: E402


def process_identity(
    pid: int,
    *,
    command: str,
    executable_path: str,
    device: int,
    inode: int,
) -> dict:
    return {
        "identity_version": 2,
        "pid": pid,
        "start": "darwin:100:000001",
        "kernel_birth_id": "darwin:100:000001",
        "command": command,
        "executable_path": executable_path,
        "device": device,
        "inode": inode,
    }


class AgyRegularFenceTests(unittest.TestCase):
    def test_pure_body_free_verdict_has_exact_immutable_blockers(self):
        verdict = agy_regular_verdict()
        self.assertEqual(
            verdict,
            {
                "schema": AGY_REGULAR_VERDICT_SCHEMA,
                "target": "agy",
                "session_profile": "regular",
                "status": "shared_vendor_auth_config_route",
                "launch_authorized": True,
                "qualification_authorized": False,
                "blockers": AGY_REGULAR_AUTHORITY_BLOCKERS,
                "route": "shared_vendor_auth_config_route",
                "limitation": AGY_SHARED_VENDOR_AUTH_LIMITATION,
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
        self.assertTrue(imported_roots <= {"", "__future__", "typing", "errors", "os", "pathlib", "subprocess", "adapter_manifest"})
        for forbidden in (
            "os.environ",
            "active_target_processes",
            "process_birth_identity",
            "SessionRegistry",
            "TmuxController",
            "read_json",
            "write_text",
        ):
            self.assertNotIn(forbidden, source)

    def test_population_is_current_uid_argv_free_and_exactly_classified(self):
        runtime_selector = {
            "path": "/opt/current/agy",
            "device": 10,
            "inode": 20,
        }
        matching = process_identity(
            101,
            command="/opt/current/agy",
            executable_path=runtime_selector["path"],
            device=runtime_selector["device"],
            inode=runtime_selector["inode"],
        )
        mismatched = process_identity(
            102,
            command="agy",
            executable_path="/opt/other/agy",
            device=11,
            inode=21,
        )
        ps_result = SimpleNamespace(
            returncode=0,
            stdout=(
                "101 %d /opt/current/agy\n"
                "102 %d agy\n"
                "103 %d agy\n"
                "104 %d agy-helper\n"
                % (os.getuid(), os.getuid(), os.getuid() + 1, os.getuid())
            ),
        )
        with (
            mock.patch.object(campaign.sys, "platform", "linux"),
            mock.patch.object(
                campaign.subprocess, "run", return_value=ps_result
            ) as process_rows,
            mock.patch.object(
                campaign,
                "process_birth_identity",
                side_effect=[matching, mismatched],
            ) as process_birth,
        ):
            population = campaign.agy_process_population(
                runtime_selector=runtime_selector
            )

        self.assertEqual(
            process_rows.call_args.args[0],
            ["ps", "-axo", "pid=,uid=,comm="],
        )
        self.assertEqual(
            [call.args[0] for call in process_birth.call_args_list],
            [101, 102],
        )
        self.assertEqual(population["candidates"], [matching, mismatched])
        self.assertEqual(population["matching"], [matching])
        self.assertEqual(population["mismatched"], [mismatched])

    def test_population_candidate_name_is_fixed_not_selector_derived(self):
        runtime_selector = {
            "path": "/opt/runtime/renamed-agy-v115",
            "device": 10,
            "inode": 20,
        }
        with mock.patch.object(
            campaign, "_target_process_rows", return_value=[]
        ) as process_rows:
            population = campaign.agy_process_population(
                runtime_selector=runtime_selector
            )

        process_rows.assert_called_once_with(
            {"agy"},
            set(),
            error_prefix="AGY candidate process inventory",
        )
        self.assertEqual(
            population,
            {"candidates": [], "matching": [], "mismatched": []},
        )

    def test_population_identity_failure_is_narrow_only_for_vanished_pid(self):
        rows = [(101, "agy")]
        with (
            mock.patch.object(campaign, "_target_process_rows", return_value=rows),
            mock.patch.object(
                campaign,
                "process_birth_identity",
                side_effect=IdentityError("candidate identity unavailable"),
            ),
            mock.patch.object(campaign, "_pid_still_exists", return_value=False),
        ):
            self.assertEqual(
                campaign.agy_process_population(
                    runtime_selector={
                        "path": "/opt/current/agy",
                        "device": 10,
                        "inode": 20,
                    }
                ),
                {"candidates": [], "matching": [], "mismatched": []},
            )

        with (
            mock.patch.object(campaign, "_target_process_rows", return_value=rows),
            mock.patch.object(
                campaign,
                "process_birth_identity",
                side_effect=IdentityError("candidate identity unavailable"),
            ),
            mock.patch.object(campaign, "_pid_still_exists", return_value=True),
            self.assertRaisesRegex(IdentityError, "candidate identity unavailable"),
        ):
            campaign.agy_process_population(
                runtime_selector={
                    "path": "/opt/current/agy",
                    "device": 10,
                    "inode": 20,
                }
            )

    def test_session_population_uses_only_exact_runtime_selector(self):
        runtime = {
            "path": "/opt/current/agy",
            "device": 10,
            "inode": 20,
        }
        manifest = SimpleNamespace(
            raw={
                "executable": {
                    "resolved_path": "/opt/launcher/agy",
                    "device": 11,
                    "inode": 21,
                },
                "execution": {
                    "runtime_executable": {
                        **runtime,
                        "size": 100,
                        "mtime_ns": 200,
                        "sha256": "a" * 64,
                    },
                    "transient_executables": [
                        {
                            "path": "/opt/transient/agy",
                            "device": 12,
                            "inode": 22,
                        }
                    ],
                },
            }
        )
        expected = {"candidates": [], "matching": [], "mismatched": []}
        with mock.patch.object(
            puppet_session,
            "agy_process_population",
            return_value=expected,
        ) as population:
            self.assertEqual(puppet_session._agy_population(manifest), expected)
        population.assert_called_once_with(runtime_selector=runtime)

    def test_mismatch_cannot_be_hidden_by_exact_parallel_override(self):
        matching = process_identity(
            101,
            command="agy",
            executable_path="/opt/current/agy",
            device=10,
            inode=20,
        )
        authorization = {
            "authorization": {
                "parallel_target_override": {
                    "target": "agy",
                    "isolation": "unique_private_tmux_socket_and_session",
                    "failure_cleanup_scope": "exact_new_target_only",
                    "protected_session": "operator-agy",
                    "protected_processes": [matching],
                }
            }
        }
        matching_only = {
            "candidates": [matching],
            "matching": [matching],
            "mismatched": [],
        }
        active, override, blockers = puppet_session._assess_agy_population(
            {"authorization": {}}, matching_only
        )
        self.assertEqual(active, [matching])
        self.assertFalse(override)
        self.assertTrue(any("exact parallel" in item for item in blockers))

        active, override, blockers = puppet_session._assess_agy_population(
            authorization, matching_only
        )
        self.assertEqual(active, [matching])
        self.assertTrue(override)
        self.assertEqual(blockers, [])

        mismatched = dict(
            matching,
            pid=102,
            executable_path="/opt/other/agy",
            device=11,
            inode=21,
        )
        population = {
            "candidates": [matching, mismatched],
            "matching": [matching],
            "mismatched": [mismatched],
        }
        active, override, blockers = puppet_session._assess_agy_population(
            authorization, population
        )
        self.assertEqual(active, [matching])
        self.assertFalse(override)
        self.assertTrue(any("different executable" in item for item in blockers))

    def test_doctor_rejects_after_contract_before_manifest_or_machine_state(self):
        contract = SimpleNamespace(target="agy", session_profile="goal")
        forbidden = {
            "manifest": mock.Mock(side_effect=AssertionError("manifest must not read")),
            "authorization": mock.Mock(
                side_effect=AssertionError("authorization must not read")
            ),
            "root": mock.Mock(side_effect=AssertionError("root must not resolve")),
            "executable": mock.Mock(
                side_effect=AssertionError("executable must not hash")
            ),
            "profile": mock.Mock(
                side_effect=AssertionError("profile must not inspect")
            ),
            "tmux": mock.Mock(side_effect=AssertionError("tmux must not inspect")),
            "workspace": mock.Mock(
                side_effect=AssertionError("workspace must not inspect")
            ),
            "processes": mock.Mock(
                side_effect=AssertionError("process census must not run")
            ),
            "population": mock.Mock(
                side_effect=AssertionError("AGY population census must not run")
            ),
            "override": mock.Mock(
                side_effect=AssertionError("parallel override must not inspect")
            ),
            "qualification": mock.Mock(
                side_effect=AssertionError("qualification must not inspect")
            ),
            "policy": mock.Mock(
                side_effect=AssertionError("instruction policy must not inspect")
            ),
            "access": mock.Mock(side_effect=AssertionError("state must not inspect")),
        }
        with (
            mock.patch.object(
                puppet_session.Contract, "from_path", return_value=contract
            ) as contract_read,
            mock.patch.object(
                puppet_session.AdapterManifest,
                "from_path",
                forbidden["manifest"],
            ),
            mock.patch.object(
                puppet_session, "_authorization", forbidden["authorization"]
            ),
            mock.patch.object(puppet_session, "absolute_root", forbidden["root"]),
            mock.patch.object(puppet_session, "sha256_file", forbidden["executable"]),
            mock.patch.object(
                puppet_session, "_profile_doctor_state", forbidden["profile"]
            ),
            mock.patch.object(
                puppet_session.TmuxController, "available", forbidden["tmux"]
            ),
            mock.patch.object(
                puppet_session, "_workspace_snapshot", forbidden["workspace"]
            ),
            mock.patch.object(
                puppet_session, "_active_processes", forbidden["processes"]
            ),
            mock.patch.object(
                puppet_session, "_agy_population", forbidden["population"]
            ),
            mock.patch.object(
                puppet_session,
                "_parallel_target_override",
                forbidden["override"],
            ),
            mock.patch.object(
                puppet_session,
                "_qualification_authority",
                forbidden["qualification"],
            ),
            mock.patch.object(
                puppet_session,
                "instruction_policy_fingerprint",
                forbidden["policy"],
            ),
            mock.patch.object(puppet_session.os, "access", forbidden["access"]),
        ):
            with self.assertRaisesRegex(UnsupportedError, "non-regular"):
                puppet_session.doctor(
                    contract_path=Path("/does/not/matter/contract.json"),
                    manifest_path=Path("/does/not/matter/manifest.json"),
                    authorization_path=Path("/does/not/matter/authorization.json"),
                    proof_root=Path("/does/not/matter/proof"),
                    state_root=Path("/does/not/matter/state"),
                    profile_root=Path("/does/not/matter/profile"),
                )
        contract_read.assert_called_once_with(Path("/does/not/matter/contract.json"))
        for sentinel in forbidden.values():
            sentinel.assert_not_called()

    def test_cli_doctor_returns_structured_unsupported_before_manifest(self):
        contract = SimpleNamespace(target="agy", session_profile="goal")
        manifest = mock.Mock(side_effect=AssertionError("manifest must not read"))
        stderr = io.StringIO()
        with (
            mock.patch.object(
                puppet_session.Contract, "from_path", return_value=contract
            ),
            mock.patch.object(
                puppet_session.AdapterManifest,
                "from_path",
                manifest,
            ),
            redirect_stderr(stderr),
        ):
            exit_code = puppet_cli.main(
                [
                    "doctor",
                    "--contract",
                    "/does/not/matter/contract.json",
                    "--manifest",
                    "/does/not/matter/manifest.json",
                    "--authorization",
                    "/does/not/matter/authorization.json",
                    "--proof-root",
                    "/does/not/matter/proof",
                    "--state-root",
                    "/does/not/matter/state",
                    "--profile-root",
                    "/does/not/matter/profile",
                ]
            )
        self.assertEqual(exit_code, 3)
        payload = json.loads(stderr.getvalue())
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"], "unsupported")
        self.assertIn("non-regular", payload["detail"])
        manifest.assert_not_called()

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
        self.assertIsNone(require_agy_regular_launch_authority("regular"))
        self.assertEqual(
            agy_authority_blockers("regular"), AGY_REGULAR_AUTHORITY_BLOCKERS
        )

    def test_launch_rejects_before_doctor_process_environment_or_tmux(self):
        contract = SimpleNamespace(target="agy", session_profile="goal")
        doctor = mock.Mock(side_effect=AssertionError("doctor must not run"))
        process_query = mock.Mock(
            side_effect=AssertionError("process query must not run")
        )
        population_query = mock.Mock(
            side_effect=AssertionError("AGY population census must not run")
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
            mock.patch.object(puppet_session, "_agy_population", population_query),
            mock.patch.object(puppet_session, "build_launch_identity", environment),
            mock.patch.object(puppet_session, "TmuxController", tmux),
        ):
            with self.assertRaisesRegex(UnsupportedError, "non-regular"):
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
            population_query,
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
                with self.assertRaisesRegex(UnsupportedError, "non-regular"):
                    run_probe(
                        target="agy",
                        profile=PROBE_PROFILE,
                        session_profile="goal",
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
        with self.assertRaisesRegex(UnsupportedError, "non-regular"):
            synthetic_qualified.verify_qualification(expected_session_profile="goal")

        base = SimpleNamespace(target="agy", raw={"doctor_only": True})
        fallback_receipt = {
            "target": "agy",
            "plane_activation": None,
            "instruction_wrapper": {
                "delivery_transport": "interactive_fallback_wrapper"
            },
        }
        verified = mock.Mock(return_value=fallback_receipt)
        population = mock.Mock(
            side_effect=AssertionError("AGY population census must not run")
        )
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
            mock.patch.object(puppet_session, "_agy_population", population),
        ):
            with self.assertRaisesRegex(UnsupportedError, "non-regular"):
                adapter_lab._qualify(args)
        verified.assert_not_called()
        population.assert_not_called()

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


class AgyRegularLaunchValidationTests(unittest.TestCase):
    def test_regular_profile_admitted_without_error(self):
        self.assertIsNone(require_agy_regular_launch_authority("regular"))

    def test_non_regular_profiles_fail_closed(self):
        for profile in ("goal", "teamwork-preview", "loop", "/goal", "unbound"):
            with self.subTest(profile=profile):
                with self.assertRaises(UnsupportedError):
                    agy_launch_module.validate_agy_regular_launch_params(
                        session_profile=profile,
                        argv=["agy", "--dangerously-skip-permissions", "--new-project", "--log-file", "/dev/null"],
                    )

    def test_explicit_model_flag_or_selection_fails_closed(self):
        with self.assertRaises(ValidationError):
            agy_launch_module.validate_agy_regular_launch_params(
                session_profile="regular",
                argv=["agy", "--dangerously-skip-permissions", "--new-project", "--log-file", "/dev/null"],
                requested_model="gemini-3.6-flash",
            )
        with self.assertRaises(ValidationError):
            agy_launch_module.validate_agy_regular_launch_params(
                session_profile="regular",
                argv=["agy", "--dangerously-skip-permissions", "--new-project", "--log-file", "/dev/null", "--model", "gemini-3.6-flash"],
            )

    def test_non_null_log_destination_fails_closed(self):
        with self.assertRaises(ValidationError):
            agy_launch_module.validate_agy_regular_launch_params(
                session_profile="regular",
                argv=["agy", "--dangerously-skip-permissions", "--new-project", "--log-file", "/tmp/agy.log"],
            )
        with self.assertRaises(ValidationError):
            agy_launch_module.validate_agy_regular_launch_params(
                session_profile="regular",
                argv=["agy", "--dangerously-skip-permissions", "--new-project", "--log-file", "/dev/null"],
                log_destination="/tmp/agy.log",
            )

    def test_missing_new_project_fails_closed(self):
        with self.assertRaises(ValidationError):
            agy_launch_module.validate_agy_regular_launch_params(
                session_profile="regular",
                argv=["agy", "--dangerously-skip-permissions", "--log-file", "/dev/null"],
            )

    def test_missing_permission_bypass_fails_closed(self):
        with self.assertRaises(ValidationError):
            agy_launch_module.validate_agy_regular_launch_params(
                session_profile="regular",
                argv=["agy", "--new-project", "--log-file", "/dev/null"],
            )

    def test_extra_argv_fails_closed(self):
        with self.assertRaises(ValidationError):
            agy_launch_module.validate_agy_regular_launch_params(
                session_profile="regular",
                argv=["agy", "--dangerously-skip-permissions", "--new-project", "--log-file", "/dev/null", "--extra-flag"],
            )
        with self.assertRaises(ValidationError):
            agy_launch_module.validate_agy_regular_launch_params(
                session_profile="regular",
                argv=["agy", "--dangerously-skip-permissions", "--new-project", "--log-file", "/dev/null", "bare_arg"],
            )

    def test_slash_commands_fail_closed(self):
        with self.assertRaises(ValidationError):
            agy_launch_module.validate_agy_regular_launch_params(
                session_profile="regular",
                argv=["agy", "--dangerously-skip-permissions", "--new-project", "--log-file", "/dev/null", "/goal"],
            )

    def test_valid_argv_grammar_with_dev_null_passes(self):
        self.assertIsNone(
            agy_launch_module.validate_agy_regular_launch_params(
                session_profile="regular",
                argv=["/usr/bin/agy", "--dangerously-skip-permissions", "--new-project", "--log-file", "/dev/null"],
                executable_path="/usr/bin/agy",
            )
        )

    def test_profile_root_claim_fails_closed(self):
        with self.assertRaises(ValidationError):
            agy_launch_module.validate_agy_regular_launch_params(
                session_profile="regular",
                argv=["agy", "--dangerously-skip-permissions", "--new-project", "--log-file", "/dev/null"],
                profile_root=Path("/some/profile/root"),
            )

    def test_status_preflight_failure_fails_closed(self):
        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = mock.Mock(returncode=1)
            with self.assertRaises(IdentityError):
                agy_launch_module.run_agy_status_preflight(executable_path=Path("/bin/echo"))

    def test_updater_replacement_between_preflight_and_start_fails_closed(self):
        manifest_exec = {
            "resolved_path": "/bin/echo",
            "device": 1,
            "inode": 2,
            "sha256": "a" * 64,
        }
        with mock.patch("puppet_lib.adapter_manifest.execution_file_identity") as mock_ident:
            mock_ident.return_value = {
                "resolved_path": "/bin/echo",
                "device": 1,
                "inode": 9999,  # Inode changed! Updater race detected!
                "sha256": "b" * 64,
            }
            with self.assertRaises(IdentityError):
                agy_launch_module.verify_agy_executable_not_updated(manifest_exec)


if __name__ == "__main__":
    unittest.main()
