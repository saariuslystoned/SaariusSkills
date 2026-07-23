from __future__ import annotations

import copy
import hashlib
import inspect
import json
import os
import sys
import tempfile
import unittest
from contextlib import ExitStack
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "puppet" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import puppet_lib.campaign as campaign  # noqa: E402
import puppet_lib.grok_launch as grok_launch  # noqa: E402
import puppet_lib.session as puppet_session  # noqa: E402
from puppet_lib.adapter_manifest import (  # noqa: E402
    ADAPTER_MANIFEST_SCHEMA_VERSION,
    AdapterManifest,
    BEHAVIOR_CAPABILITIES,
    direct_execution_bundle,
)
from puppet_lib.census import (  # noqa: E402
    adapter_implementation_fingerprint,
    census_target,
)
from puppet_lib.errors import (  # noqa: E402
    IdentityError,
    UnsupportedError,
    ValidationError,
)
from puppet_lib.grok_launch import (  # noqa: E402
    GROK_CENSUS_VERSION_OUTPUT_SHA256,
    GROK_DISABLE_AUTOUPDATER_VALUE,
    GROK_EXECUTABLE_SHA256,
    GROK_ISOLATED_VERSION_OUTPUT_SHA256,
    GROK_LAUNCH_AUTHORITY_BLOCKER,
    GROK_MAIN_HELP_SHA256,
    GROK_RUNTIME_BASENAME,
    GROK_SAFE_PATH_COMPONENTS,
    GROK_WORKSPACE_BINDING_SCHEMA,
    GROK_WORKSPACE_BINDING_STATE,
    bind_grok_workspace_plane,
    build_grok_launch_context,
    require_live_grok_launch,
)
from puppet_lib.handoffs import PROTOCOL_FINGERPRINT  # noqa: E402
from puppet_lib.instruction_planes import (  # noqa: E402
    build_grok_workspace_addendum_descriptor,
)
from puppet_lib.instructions import compile_instruction_wrapper  # noqa: E402
from puppet_lib.plane_activation import plan_activation  # noqa: E402
from puppet_lib.profiles import (  # noqa: E402
    PROMPT_TRANSPORT,
    SUBMIT_SETTLE_SECONDS,
    session_profiles_for,
    startup_settle_seconds_for,
)


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


class GrokLaunchAuthorityTests(unittest.TestCase):
    def test_current_source_tuple_is_exact_grok_0_2_111_census(self):
        self.assertEqual(
            GROK_EXECUTABLE_SHA256,
            "e1fafdfffe14f339460befaf194360e8f90bfd02efe8a4f24cfa1c7aea657ffe",
        )
        self.assertEqual(
            GROK_CENSUS_VERSION_OUTPUT_SHA256,
            "056584a715a3f6cdb882797e20c49495c1dc8874d83eb4c62d474a1fb188f15d",
        )
        self.assertEqual(
            GROK_ISOLATED_VERSION_OUTPUT_SHA256,
            "580e7f325a2b1c0807e2eca5ad4bceac313dee481c3e66c06af08013ef89430d",
        )
        self.assertEqual(
            GROK_MAIN_HELP_SHA256,
            "d11f1815c770a69d87a05f394c6f7759562738c7de4e29a043f9f06c0aeba1c1",
        )
        self.assertEqual(GROK_RUNTIME_BASENAME, "grok-0.2.111-macos-aarch64")

    def _manifest_raw(self, executable: Path) -> dict:
        details = executable.stat()
        executable_identity = {
            "requested_path": str(executable),
            "resolved_path": str(executable),
            "device": details.st_dev,
            "inode": details.st_ino,
            "size": details.st_size,
            "mtime_ns": details.st_mtime_ns,
            "sha256": GROK_EXECUTABLE_SHA256,
            "version_sha256": GROK_CENSUS_VERSION_OUTPUT_SHA256,
            "help_sha256": GROK_MAIN_HELP_SHA256,
        }
        return {
            "schema_version": ADAPTER_MANIFEST_SCHEMA_VERSION,
            "target": "grok",
            "generated_at": "2026-07-22T02:00:00Z",
            "platform": {
                "system": "Darwin",
                "release": "25",
                "machine": "arm64",
            },
            "executable": executable_identity,
            "execution": direct_execution_bundle(executable_identity),
            "adapter_fingerprint": adapter_implementation_fingerprint(),
            "protocol_fingerprint": PROTOCOL_FINGERPRINT,
            "yolo_mapping": {
                "complete": False,
                "launch_argv": [str(executable), "--always-approve"],
                "permission_declared": True,
                "permission_flags": ["--always-approve"],
                "prompt_transport": PROMPT_TRANSPORT,
                "prompt_transport_declared": True,
                "sandbox_disable_declared": False,
                "sandbox_flags": [],
                "project_isolation_declared": False,
                "project_isolation_flags": [],
                "session_profiles": session_profiles_for("grok"),
                "session_profiles_declared": True,
                "startup_settle_seconds": startup_settle_seconds_for("grok"),
                "submit_settle_seconds": SUBMIT_SETTLE_SECONDS,
                "model_flag": "--model",
                "effort_flag": "--reasoning-effort",
            },
            "capabilities": {name: "declared" for name in BEHAVIOR_CAPABILITIES},
            "doctor_only": True,
            "qualification": None,
        }

    @staticmethod
    def _write_manifest(path: Path, raw: dict) -> None:
        path.write_text(json.dumps(raw, sort_keys=True) + "\n", encoding="utf-8")

    @staticmethod
    def _build_context(layout: dict[str, object], **overrides):
        values = dict(layout)
        values.update(overrides)
        with patch.object(AdapterManifest, "verify_execution_files", return_value=None):
            return build_grok_launch_context(**values)

    def _layout(self, root: Path) -> dict[str, object]:
        executable = root / "grok-0.2.111-macos-aarch64"
        executable.write_bytes(b"synthetic grok executable")
        executable.chmod(0o700)
        manifest = root / "grok-doctor-manifest.json"
        self._write_manifest(manifest, self._manifest_raw(executable))
        lane = root / "lane"
        lane.mkdir(mode=0o700)
        home = lane / "home"
        home.mkdir(mode=0o700)
        grok_home = lane / "grok-home"
        grok_home.mkdir(mode=0o700)
        control = lane / "control"
        control.mkdir(mode=0o700)
        workspace = root / "workspace"
        workspace.mkdir()
        return {
            "manifest_path": manifest,
            "admitted_lane_root": lane,
            "home": home,
            "grok_home": grok_home,
            "cwd": workspace,
            "leader_socket": control / "leader.sock",
            "contract_identity": {
                "fingerprint": "c" * 64,
                "controller": "codex",
                "target": "grok",
                "task_profile": "source-free-pass-b-v2",
            },
            "run_identity": {
                "session": "puppet-grok-source-only",
                "run_id": "grok-source-only-run",
                "nonce": "grok-plane-binding-nonce-0123456789",
            },
            "grok_session_id": "12345678-1234-4234-9234-123456789abc",
        }

    def test_body_free_plan_binds_exact_private_grok_context(self):
        with tempfile.TemporaryDirectory() as temporary:
            layout = self._layout(Path(temporary).resolve())
            ambient = {
                "HOME": "/ambient/operator/home",
                "PATH": "/ambient/operator/bin",
                "SSH_AUTH_SOCK": "/ambient/operator/agent.sock",
                "SHELL": "/ambient/operator/shell",
                "USER": "ambient-operator",
                "LOGNAME": "ambient-operator",
                "TMPDIR": "/ambient/operator/tmp",
                "LANG": "ambient_LOCALE",
                "LC_ALL": "ambient_LOCALE",
                "GROK_HOME": "/ambient/operator/grok-home",
                "GROK_DISABLE_AUTOUPDATER": "false",
                "PUPPET_TASK_BODY_CANARY": "must-not-cross",
                "OPENAI_API_KEY": "credential-channel-canary",
            }
            with patch.dict(os.environ, ambient, clear=True):
                context = self._build_context(layout)
            expected_argv = (
                str(
                    Path(layout["manifest_path"]).parent / "grok-0.2.111-macos-aarch64"
                ),
                "--always-approve",
                "--sandbox",
                "off",
                "--cwd",
                str(layout["cwd"]),
                "--leader-socket",
                str(layout["leader_socket"]),
                "--session-id",
                layout["grok_session_id"],
            )
            self.assertEqual(context.argv, expected_argv)
            self.assertEqual(context.environment["HOME"], str(layout["home"]))
            self.assertEqual(context.environment["GROK_HOME"], str(layout["grok_home"]))
            self.assertEqual(
                context.environment["GROK_DISABLE_AUTOUPDATER"],
                GROK_DISABLE_AUTOUPDATER_VALUE,
            )
            self.assertEqual(
                dict(context.environment),
                {
                    "GROK_DISABLE_AUTOUPDATER": GROK_DISABLE_AUTOUPDATER_VALUE,
                    "GROK_HOME": str(layout["grok_home"]),
                    "HOME": str(layout["home"]),
                    "LANG": "C",
                    "LC_ALL": "C",
                    "PATH": os.pathsep.join(GROK_SAFE_PATH_COMPONENTS),
                },
            )
            self.assertNotIn("PUPPET_TASK_BODY_CANARY", context.environment)
            self.assertNotIn("SSH_AUTH_SOCK", context.environment)
            self.assertNotIn("OPENAI_API_KEY", context.environment)
            self.assertNotIn("/ambient/operator", repr(context.environment))
            self.assertNotIn("--model", context.argv)
            self.assertNotIn("--reasoning-effort", context.argv)
            for slash_command in ("/goal", "/loop", "/teamwork-preview"):
                self.assertNotIn(slash_command, context.argv)
            self.assertEqual(context.admitted_plan["target"], "grok")
            self.assertEqual(context.admitted_plan["argv"], expected_argv)
            self.assertEqual(context.doctor_manifest, layout["manifest_path"])
            self.assertEqual(
                context.adapter_fingerprint, adapter_implementation_fingerprint()
            )
            for identity in (
                context.admitted_lane_root_identity,
                context.home_root_identity,
                context.workspace_root_identity,
                context.config_root_identity,
            ):
                self.assertEqual(
                    set(identity),
                    {"path", "device", "inode", "uid", "mode", "nlink"},
                )
            self.assertEqual(
                dict(context.contract_identity), layout["contract_identity"]
            )
            self.assertEqual(dict(context.run_identity), layout["run_identity"])
            self.assertFalse(context.launch_authorized)
            self.assertTrue(context.blockers)
            with self.assertRaisesRegex(UnsupportedError, "doctor-only"):
                require_live_grok_launch(context)

    def test_private_roots_reject_escape_symlink_overlap_and_public_mode(self):
        cases = ("outside", "symlink", "overlap", "public")
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary).resolve()
                layout = self._layout(root)
                if case == "outside":
                    outside = root / "outside-grok-home"
                    outside.mkdir(mode=0o700)
                    layout["grok_home"] = outside
                elif case == "symlink":
                    link = Path(layout["admitted_lane_root"]) / "linked-home"
                    link.symlink_to(layout["home"], target_is_directory=True)
                    layout["home"] = link
                elif case == "overlap":
                    nested = Path(layout["home"]) / "grok-home"
                    nested.mkdir(mode=0o700)
                    layout["grok_home"] = nested
                else:
                    Path(layout["admitted_lane_root"]).chmod(0o755)
                with self.assertRaises(ValidationError):
                    self._build_context(layout)

    def test_source_owned_path_policy_rejects_relative_components(self):
        with tempfile.TemporaryDirectory() as temporary:
            layout = self._layout(Path(temporary).resolve())
            with (
                patch.object(
                    grok_launch,
                    "GROK_SAFE_PATH_COMPONENTS",
                    ("relative/bin", "/usr/bin"),
                ),
                self.assertRaisesRegex(ValidationError, "existing absolute"),
            ):
                self._build_context(layout)

    def test_launch_context_rejects_open_or_cross_target_authority_identities(self):
        cases = (
            ("target", "contract_identity", "target", "claude"),
            ("profile", "contract_identity", "task_profile", "other-profile"),
            ("contract-extra", "contract_identity", "extra", "open-schema"),
            ("run-extra", "run_identity", "extra", "open-schema"),
        )
        for case, identity_name, field, changed in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                layout = self._layout(Path(temporary).resolve())
                identity = dict(layout[identity_name])
                identity[field] = changed
                layout[identity_name] = identity
                with self.assertRaises(ValidationError):
                    self._build_context(layout)

    def test_workspace_socket_and_uuid_collisions_fail_closed(self):
        cases = ("workspace", "socket-home", "socket-exists", "uuid")
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary).resolve()
                layout = self._layout(root)
                if case == "workspace":
                    workspace = Path(layout["admitted_lane_root"]) / "workspace"
                    workspace.mkdir()
                    layout["cwd"] = workspace
                elif case == "socket-home":
                    layout["leader_socket"] = Path(layout["home"]) / "leader.sock"
                elif case == "socket-exists":
                    Path(layout["leader_socket"]).write_text(
                        "collision", encoding="utf-8"
                    )
                else:
                    layout["grok_session_id"] = "not-a-uuid"
                with self.assertRaises(ValidationError):
                    self._build_context(layout)

    def test_plan_rejects_wrong_grok_doctor_manifest_tuple(self):
        cases = (
            "malformed",
            "target",
            "doctor-only",
            "qualification",
            "binary-hash",
            "version-hash",
            "isolated-version-hash",
            "help-hash",
            "adapter-hash",
            "protocol-hash",
        )
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary).resolve()
                layout = self._layout(root)
                manifest_path = Path(layout["manifest_path"])
                raw = json.loads(manifest_path.read_text(encoding="utf-8"))
                if case == "malformed":
                    manifest_path.write_text("{}\n", encoding="utf-8")
                elif case == "target":
                    raw["target"] = "cursor"
                    self._write_manifest(manifest_path, raw)
                elif case == "doctor-only":
                    raw["doctor_only"] = False
                    self._write_manifest(manifest_path, raw)
                elif case == "qualification":
                    raw["qualification"] = {}
                    self._write_manifest(manifest_path, raw)
                elif case == "binary-hash":
                    raw["executable"]["sha256"] = "0" * 64
                    raw["execution"] = direct_execution_bundle(raw["executable"])
                    self._write_manifest(manifest_path, raw)
                elif case == "version-hash":
                    raw["executable"]["version_sha256"] = "0" * 64
                    self._write_manifest(manifest_path, raw)
                elif case == "isolated-version-hash":
                    raw["executable"][
                        "version_sha256"
                    ] = GROK_ISOLATED_VERSION_OUTPUT_SHA256
                    self._write_manifest(manifest_path, raw)
                elif case == "help-hash":
                    raw["executable"]["help_sha256"] = "0" * 64
                    self._write_manifest(manifest_path, raw)
                elif case == "adapter-hash":
                    raw["adapter_fingerprint"] = "0" * 64
                    self._write_manifest(manifest_path, raw)
                else:
                    raw["protocol_fingerprint"] = "0" * 64
                    self._write_manifest(manifest_path, raw)
                with self.assertRaises(
                    (IdentityError, UnsupportedError, ValidationError)
                ):
                    self._build_context(layout)

    def test_plan_rechecks_current_grok_executable_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            layout = self._layout(Path(temporary).resolve())
            with self.assertRaisesRegex(IdentityError, "identity changed"):
                build_grok_launch_context(**layout)

    def test_census_help_does_not_promote_grok_parser_facts_to_live_authority(self):
        with tempfile.TemporaryDirectory() as temporary:
            executable = Path(temporary).resolve() / "grok-0.2.111-macos-aarch64"
            executable.write_bytes(b"synthetic grok executable")
            executable.chmod(0o700)
            with (
                patch("puppet_lib.census.shutil.which", return_value=str(executable)),
                patch(
                    "puppet_lib.census._bounded_run",
                    side_effect=[
                        b"grok 0.2.111\n",
                        (
                            b"--always-approve --sandbox off --cwd "
                            b"--leader-socket --session-id\n"
                        ),
                    ],
                ),
            ):
                manifest = census_target("grok", "d" * 64)
            self.assertTrue(manifest.raw["doctor_only"])
            self.assertIsNone(manifest.raw["qualification"])
            self.assertFalse(manifest.raw["yolo_mapping"]["complete"])
            self.assertFalse(manifest.raw["yolo_mapping"]["sandbox_disable_declared"])
            self.assertFalse(manifest.raw["yolo_mapping"]["project_isolation_declared"])

    def test_same_name_transient_vnode_is_not_a_runtime_match(self):
        runtime_selector = {
            "path": "/opt/runtime/grok-macos-aarch64",
            "device": 10,
            "inode": 20,
        }
        transient_selector = {
            "path": "/opt/transient/grok-macos-aarch64",
            "device": 11,
            "inode": 21,
        }
        matching = process_identity(
            101,
            command="grok",
            executable_path=runtime_selector["path"],
            device=runtime_selector["device"],
            inode=runtime_selector["inode"],
        )
        mismatched = process_identity(
            102,
            command="grok-macos-aarch64",
            executable_path=transient_selector["path"],
            device=transient_selector["device"],
            inode=transient_selector["inode"],
        )
        manifest = SimpleNamespace(
            raw={
                "executable": {
                    "resolved_path": "/opt/launcher/grok-macos-aarch64",
                    "device": 13,
                    "inode": 23,
                },
                "execution": {
                    "runtime_executable": runtime_selector,
                    "transient_executables": [transient_selector],
                },
            }
        )
        with (
            patch.object(
                campaign,
                "_target_process_rows",
                return_value=[
                    (matching["pid"], matching["command"]),
                    (mismatched["pid"], mismatched["command"]),
                ],
            ),
            patch.object(
                campaign,
                "process_birth_identity",
                side_effect=[matching, mismatched],
            ),
        ):
            population = puppet_session._grok_population(manifest)
        self.assertEqual(population["candidates"], [matching, mismatched])
        self.assertEqual(population["matching"], [matching])
        self.assertEqual(population["mismatched"], [mismatched])

    def test_versioned_runtime_basename_is_fixed_and_identity_classified(self):
        basename = "grok-0.2.111-macos-aarch64"
        runtime_selector = {
            "path": "/opt/runtime/%s" % basename,
            "device": 10,
            "inode": 20,
        }
        matching = process_identity(
            101,
            command=basename,
            executable_path=runtime_selector["path"],
            device=runtime_selector["device"],
            inode=runtime_selector["inode"],
        )
        mismatched = process_identity(
            102,
            command=basename,
            executable_path="/opt/other/%s" % basename,
            device=11,
            inode=21,
        )
        rows = [
            (matching["pid"], matching["command"]),
            (mismatched["pid"], mismatched["command"]),
        ]
        with (
            patch.object(
                campaign,
                "_target_process_rows",
                return_value=rows,
            ) as process_rows,
            patch.object(
                campaign,
                "process_birth_identity",
                side_effect=[matching, mismatched],
            ),
        ):
            population = campaign.grok_process_population(
                runtime_selector=runtime_selector
            )

        process_rows.assert_called_once_with(
            {
                "grok",
                "grok-macos-aarch64",
                "grok-0.2.111-macos-aarch64",
            },
            set(),
            error_prefix="Grok candidate process inventory",
        )
        self.assertEqual(population["candidates"], [matching, mismatched])
        self.assertEqual(population["matching"], [matching])
        self.assertEqual(population["mismatched"], [mismatched])
        _, override, blockers = puppet_session._assess_grok_population(
            {"authorization": {}},
            population,
        )
        self.assertFalse(override)
        self.assertIn(
            "a live Grok candidate has a different executable identity and blocks launch",
            blockers,
        )

    def test_transient_bash_row_is_not_a_grok_candidate(self):
        grok_selector = {
            "path": "/opt/grok-macos-aarch64",
            "device": 10,
            "inode": 20,
        }
        grok = process_identity(
            202,
            command="/opt/grok-macos-aarch64",
            executable_path=grok_selector["path"],
            device=grok_selector["device"],
            inode=grok_selector["inode"],
        )
        ps_result = SimpleNamespace(
            returncode=0,
            stdout=(
                "201 %d /bin/bash\n202 %d /opt/grok-macos-aarch64\n"
                % (os.getuid(), os.getuid())
            ),
        )
        with (
            patch.object(campaign.sys, "platform", "linux"),
            patch.object(campaign.subprocess, "run", return_value=ps_result),
            patch.object(campaign, "process_birth_identity", return_value=grok),
        ):
            population = campaign.grok_process_population(
                runtime_selector=grok_selector
            )
        self.assertEqual(population["candidates"], [grok])
        self.assertEqual(population["matching"], [grok])
        self.assertEqual(population["mismatched"], [])

    def test_session_filters_launcher_and_transient_roles_from_grok_matching(self):
        runtime = {
            "path": "/opt/runtime/grok-macos-aarch64",
            "device": 10,
            "inode": 20,
        }
        manifest = SimpleNamespace(
            raw={
                "execution": {
                    "runtime_executable": {
                        **runtime,
                        "size": 100,
                        "mtime_ns": 200,
                        "sha256": "a" * 64,
                    },
                    "transient_executables": [
                        {
                            "path": "/opt/transient/grok-macos-aarch64",
                            "device": 11,
                            "inode": 21,
                        },
                        {"path": "/bin/bash", "device": 12, "inode": 22},
                    ],
                }
            }
        )
        expected = {"candidates": [], "matching": [], "mismatched": []}
        with patch.object(
            puppet_session,
            "grok_process_population",
            return_value=expected,
        ) as population:
            self.assertEqual(puppet_session._grok_population(manifest), expected)
        population.assert_called_once_with(runtime_selector=runtime)

    def test_session_assessment_requires_exact_override_and_rejects_mismatch(self):
        matching = process_identity(
            101,
            command="grok",
            executable_path="/opt/grok-macos-aarch64",
            device=10,
            inode=20,
        )
        population = {
            "candidates": [matching],
            "matching": [matching],
            "mismatched": [],
        }
        active, override, blockers = puppet_session._assess_grok_population(
            {"authorization": {}}, population
        )
        self.assertEqual(active, [matching])
        self.assertFalse(override)
        self.assertTrue(any("exact parallel" in item for item in blockers))

        authorization = {
            "authorization": {
                "parallel_target_override": {
                    "target": "grok",
                    "isolation": "unique_private_tmux_socket_and_session",
                    "failure_cleanup_scope": "exact_new_target_only",
                    "protected_session": "operator-grok",
                    "protected_processes": [matching],
                }
            }
        }
        _, override, blockers = puppet_session._assess_grok_population(
            authorization, population
        )
        self.assertTrue(override)
        self.assertEqual(blockers, [])

        mismatched = dict(matching, executable_path="/other/grok", inode=21)
        mismatched_population = {
            "candidates": [mismatched],
            "matching": [],
            "mismatched": [mismatched],
        }
        _, override, blockers = puppet_session._assess_grok_population(
            authorization, mismatched_population
        )
        self.assertFalse(override)
        self.assertTrue(any("different executable" in item for item in blockers))

    def test_doctor_and_launch_keep_grok_fenced(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            executable = root / "grok-0.2.111-macos-aarch64"
            executable.write_bytes(b"synthetic grok executable")
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
            manifest = SimpleNamespace(
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
                patch.object(
                    puppet_session.Contract, "from_path", return_value=contract
                ),
                patch.object(
                    puppet_session.AdapterManifest, "from_path", return_value=manifest
                ),
                patch.object(
                    puppet_session,
                    "_authorization",
                    return_value={"authorization": {}},
                ),
                patch.object(
                    puppet_session,
                    "_workspace_snapshot",
                    return_value={
                        "branch": contract.branch,
                        "head": "c" * 40,
                        "tree": "d" * 40,
                        "dirty": False,
                    },
                ),
                patch.object(
                    puppet_session, "_grok_population", return_value=population
                ),
                patch.object(
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
            self.assertEqual(report["candidate_target_pids"], [])

            with (
                patch.object(
                    puppet_session.Contract, "from_path", return_value=contract
                ),
                patch.object(
                    puppet_session,
                    "doctor",
                    return_value={"target": "grok", "launch_ready": True},
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


class GrokWorkspacePlaneBindingTests(unittest.TestCase):
    _manifest_raw = GrokLaunchAuthorityTests._manifest_raw
    _write_manifest = staticmethod(GrokLaunchAuthorityTests._write_manifest)
    _build_context = staticmethod(GrokLaunchAuthorityTests._build_context)
    _layout = GrokLaunchAuthorityTests._layout

    def _binding_fixture(self, root: Path) -> dict:
        layout = self._layout(root)
        context = self._build_context(layout)
        manifest = AdapterManifest.from_path(Path(layout["manifest_path"]))
        compiled = compile_instruction_wrapper(
            target="grok",
            task="TASK_BODY_CANARY: write one bounded source-free handoff.",
            contract_identity=context.contract_identity,
            workspace_identity=context.workspace_root_identity,
            run_identity=context.run_identity,
        )
        descriptor = build_grok_workspace_addendum_descriptor(
            adapter_manifest_sha256=manifest.fingerprint,
            rendered_sha256=compiled.manifest["rendered_sha256"],
        )
        return {
            "descriptor": descriptor,
            "instruction_manifest": compiled.manifest,
            "effective_contract": compiled.rendered,
            "adapter_manifest": manifest,
            "manifest_path": context.doctor_manifest,
            "admitted_lane_root": context.admitted_lane_root,
            "home": context.home,
            "grok_home": context.grok_home,
            "cwd": context.cwd,
            "leader_socket": context.leader_socket,
            "grok_session_id": context.grok_session_id,
            "expected_contract_identity": dict(context.contract_identity),
            "expected_run_identity": dict(context.run_identity),
            "expected_lane_root_identity": dict(context.admitted_lane_root_identity),
            "expected_home_root_identity": dict(context.home_root_identity),
            "expected_workspace_root_identity": dict(context.workspace_root_identity),
            "expected_config_root_identity": dict(context.config_root_identity),
            "launch_context": context,
        }

    @staticmethod
    def _bind(values: dict):
        arguments = dict(values)
        arguments.pop("launch_context")
        with patch.object(AdapterManifest, "verify_execution_files", return_value=None):
            return bind_grok_workspace_plane(**arguments)

    @staticmethod
    def _record(binding):
        with patch.object(AdapterManifest, "verify_execution_files", return_value=None):
            return binding.record

    def test_binding_joins_exact_context_and_exposes_only_body_free_metadata(self):
        with tempfile.TemporaryDirectory() as temporary:
            values = self._binding_fixture(Path(temporary).resolve())
            first = self._bind(values)
            second = self._bind(values)
            record = self._record(first)
            self.assertEqual(record, self._record(second))
            self.assertEqual(record["schema"], GROK_WORKSPACE_BINDING_SCHEMA)
            self.assertEqual(record["state"], GROK_WORKSPACE_BINDING_STATE)
            self.assertEqual(record["target"], "grok")
            self.assertEqual(record["target_version"], "0.2.111")
            self.assertEqual(record["plane"], "workspace_addendum")
            self.assertEqual(
                record["adapter_manifest_sha256"],
                values["adapter_manifest"].fingerprint,
            )
            self.assertEqual(
                record["effective_contract_sha256"],
                hashlib.sha256(values["effective_contract"]).hexdigest(),
            )
            self.assertEqual(
                record["effective_contract_bytes"],
                len(values["effective_contract"]),
            )
            self.assertEqual(
                record["artifact"]["relative_path"],
                ".grok/rules/puppet-%s.md" % record["effective_contract_sha256"],
            )
            self.assertEqual(record["artifact"]["root_ref"], "workspace_root")
            self.assertEqual(record["artifact"]["write_mode"], "create_only")
            for field in (
                "activation_authorized",
                "launch_authorized",
                "qualification_authorized",
            ):
                self.assertIs(record[field], False)

            public_json = json.dumps(record, sort_keys=True)
            context = values["launch_context"]
            for forbidden in (
                "TASK_BODY_CANARY",
                str(context.cwd),
                str(context.grok_home),
                str(context.home),
                str(context.leader_socket),
                str(context.executable),
                context.grok_session_id,
                "--always-approve",
                "--sandbox",
                "GROK_HOME",
                "GROK_DISABLE_AUTOUPDATER",
            ):
                self.assertNotIn(forbidden, public_json)
            self.assertFalse(hasattr(first, "_effective_contract"))
            self.assertNotIn("TASK_BODY_CANARY", repr(first))
            detached = self._record(first)
            detached["state"] = "caller-green"
            self.assertEqual(self._record(first)["state"], GROK_WORKSPACE_BINDING_STATE)
            with self.assertRaisesRegex(TypeError, "dataclass instances"):
                replace(first, context_sha256="f" * 64)
            direct_arguments = dict(values)
            direct_arguments.pop("launch_context")
            with patch.object(
                AdapterManifest,
                "verify_execution_files",
                return_value=None,
            ):
                direct = grok_launch.GrokWorkspacePlaneBinding(**direct_arguments)
            self.assertEqual(self._record(direct), record)
            constructor_parameters = inspect.signature(
                grok_launch.GrokWorkspacePlaneBinding
            ).parameters
            for bypass in (
                "source_provenance",
                "factory_key",
                "context_sha256",
                "expected_record_sha256",
                "record",
                "record_json",
            ):
                self.assertNotIn(bypass, constructor_parameters)
            serialized = json.loads(json.dumps(self._record(first)))
            self.assertFalse(
                hasattr(grok_launch.GrokWorkspacePlaneBinding, "from_dict")
            )
            with self.assertRaisesRegex(ValidationError, "launch context is invalid"):
                require_live_grok_launch(serialized)
            with self.assertRaisesRegex(UnsupportedError, "doctor-only"):
                require_live_grok_launch(context)

    def test_public_binder_rebuilds_context_and_rejects_candidate_injection(self):
        parameters = inspect.signature(bind_grok_workspace_plane).parameters
        self.assertNotIn("launch_context", parameters)
        self.assertTrue(
            {
                "manifest_path",
                "admitted_lane_root",
                "home",
                "grok_home",
                "cwd",
                "leader_socket",
                "grok_session_id",
                "expected_contract_identity",
                "expected_run_identity",
                "expected_lane_root_identity",
                "expected_home_root_identity",
                "expected_workspace_root_identity",
                "expected_config_root_identity",
            }.issubset(parameters)
        )
        with tempfile.TemporaryDirectory() as temporary:
            values = self._binding_fixture(Path(temporary).resolve())
            context = values["launch_context"]
            mutated_contract = dict(context.contract_identity)
            mutated_contract["controller"] = "attacker-controller"
            replaced_context = replace(
                context,
                contract_identity=mutated_contract,
            )
            arguments = dict(values)
            arguments.pop("launch_context")
            with (
                patch.object(
                    AdapterManifest,
                    "verify_execution_files",
                    return_value=None,
                ),
                self.assertRaisesRegex(TypeError, "launch_context"),
            ):
                bind_grok_workspace_plane(
                    **arguments,
                    launch_context=replaced_context,
                )

    def test_binding_rejects_same_path_root_replacement_on_bind_and_record_read(self):
        for case in ("lane", "home", "workspace", "config"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary).resolve()
                values = self._binding_fixture(root)
                context = values["launch_context"]
                binding = self._bind(values)
                self.assertEqual(
                    self._record(binding)["state"], GROK_WORKSPACE_BINDING_STATE
                )

                replaced = {
                    "lane": context.admitted_lane_root,
                    "home": context.home,
                    "workspace": context.cwd,
                    "config": context.grok_home,
                }[case]
                replacement_source = root / (case + "-original")
                replaced.rename(replacement_source)
                replaced.mkdir(mode=0o700)

                changed_identity = {
                    "lane": "admitted Grok lane root identity changed",
                    "home": "Grok lane HOME identity changed",
                    "workspace": "Grok workspace root identity changed",
                    "config": "Grok config root identity changed",
                }[case]
                with self.assertRaisesRegex(IdentityError, changed_identity):
                    self._bind(values)
                with self.assertRaisesRegex(IdentityError, changed_identity):
                    self._record(binding)

    def test_binding_rejects_structurally_valid_contract_and_run_replays(self):
        cases = (
            ("target", "contract", "target", "claude"),
            ("controller", "contract", "controller", "agy"),
            ("fingerprint", "contract", "fingerprint", "d" * 64),
            ("profile", "contract", "task_profile", "other-profile"),
            ("nonce", "run", "nonce", "other-grok-nonce"),
            ("session", "run", "session", "other-grok-session"),
            ("run-id", "run", "run_id", "other-grok-run"),
            ("contract-extra", "contract", "extra", "closed-schema"),
            ("run-extra", "run", "extra", "closed-schema"),
        )
        for case, identity_name, field, changed in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                values = self._binding_fixture(Path(temporary).resolve())
                context = values["launch_context"]
                contract_identity = dict(context.contract_identity)
                run_identity = dict(context.run_identity)
                identity = (
                    contract_identity if identity_name == "contract" else run_identity
                )
                identity[field] = changed
                compiled = compile_instruction_wrapper(
                    target="grok",
                    task="TASK_BODY_CANARY: structurally valid replay.",
                    contract_identity=contract_identity,
                    workspace_identity=context.workspace_root_identity,
                    run_identity=run_identity,
                )
                values["instruction_manifest"] = compiled.manifest
                values["effective_contract"] = compiled.rendered
                values["descriptor"] = build_grok_workspace_addendum_descriptor(
                    adapter_manifest_sha256=values["adapter_manifest"].fingerprint,
                    rendered_sha256=compiled.manifest["rendered_sha256"],
                )
                with self.assertRaises((IdentityError, ValidationError)):
                    self._bind(values)

    def test_binding_rejects_manifest_bytes_hash_adapter_and_model_drift(self):
        cases = (
            "manifest-target",
            "bytes",
            "filename-hash",
            "adapter-manifest",
            "model",
        )
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                values = self._binding_fixture(Path(temporary).resolve())
                if case == "manifest-target":
                    instruction = copy.deepcopy(values["instruction_manifest"])
                    instruction["target"] = "claude"
                    values["instruction_manifest"] = instruction
                elif case == "bytes":
                    values["effective_contract"] += b"\ntampered"
                elif case == "filename-hash":
                    values["descriptor"] = build_grok_workspace_addendum_descriptor(
                        adapter_manifest_sha256=values["adapter_manifest"].fingerprint,
                        rendered_sha256="f" * 64,
                    )
                elif case == "adapter-manifest":
                    raw = copy.deepcopy(values["adapter_manifest"].raw)
                    raw["generated_at"] = "2026-07-22T02:00:01Z"
                    values["adapter_manifest"] = AdapterManifest.from_dict(raw)
                else:
                    context = values["launch_context"]
                    compiled = compile_instruction_wrapper(
                        target="grok",
                        task="TASK_BODY_CANARY: wrong selected model binding.",
                        contract_identity=context.contract_identity,
                        workspace_identity=context.workspace_root_identity,
                        run_identity=context.run_identity,
                        model_binding="default",
                    )
                    values["instruction_manifest"] = compiled.manifest
                    values["effective_contract"] = compiled.rendered
                    values["descriptor"] = build_grok_workspace_addendum_descriptor(
                        adapter_manifest_sha256=values["adapter_manifest"].fingerprint,
                        rendered_sha256=compiled.manifest["rendered_sha256"],
                    )
                with self.assertRaises((IdentityError, ValidationError)):
                    self._bind(values)

    def test_binding_rejects_cross_root_argv_environment_and_config(self):
        cases = ("root", "argv", "environment", "config")
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary).resolve()
                values = self._binding_fixture(root)
                context = values["launch_context"]
                if case == "root":
                    other = root / "other-workspace"
                    other.mkdir()
                    values["cwd"] = other
                elif case == "argv":
                    changed_context = replace(
                        context,
                        argv=context.argv + ("--model", "grok-4.5"),
                    )
                elif case == "environment":
                    environment = dict(context.environment)
                    environment["GROK_DISABLE_AUTOUPDATER"] = "false"
                    changed_context = replace(
                        context,
                        environment=environment,
                    )
                else:
                    descriptor = copy.deepcopy(values["descriptor"])
                    descriptor["target"]["config_fingerprint"] = "e" * 64
                    values["descriptor"] = descriptor
                if case in {"argv", "environment"}:
                    with (
                        patch.object(
                            grok_launch,
                            "build_grok_launch_context",
                            return_value=changed_context,
                        ),
                        self.assertRaises((IdentityError, ValidationError)),
                    ):
                        self._bind(values)
                else:
                    with self.assertRaises((IdentityError, ValidationError)):
                        self._bind(values)

    def test_binding_does_not_write_spawn_or_enter_session_surfaces(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            values = self._binding_fixture(root)
            before = sorted(
                (str(path.relative_to(root)), path.stat().st_mode, path.stat().st_size)
                for path in root.rglob("*")
            )
            guarded = (
                "pathlib.Path.mkdir",
                "pathlib.Path.write_bytes",
                "pathlib.Path.write_text",
                "pathlib.Path.unlink",
                "subprocess.Popen",
                "subprocess.run",
                "puppet_lib.adapter_manifest.AdapterManifest.verify_qualification",
                "puppet_lib.plane_activation.materialize_activation",
                "puppet_lib.session.launch",
                "puppet_lib.tmux.TmuxController.launch",
            )
            with ExitStack() as stack:
                calls = [
                    stack.enter_context(
                        patch(
                            name,
                            side_effect=AssertionError(
                                "forbidden binding side effect: " + name
                            ),
                        )
                    )
                    for name in guarded
                ]
                result = self._bind(values)
            after = sorted(
                (str(path.relative_to(root)), path.stat().st_mode, path.stat().st_size)
                for path in root.rglob("*")
            )
            self.assertEqual(before, after)
            self.assertFalse((Path(values["launch_context"].cwd) / ".grok").exists())
            self.assertEqual(self._record(result)["state"], "binding_only")
            for call in calls:
                call.assert_not_called()

    def test_generic_plane_activation_still_rejects_exact_grok_descriptor(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            values = self._binding_fixture(root)
            with self.assertRaisesRegex(UnsupportedError, "only Claude 2.1.215"):
                plan_activation(
                    values["descriptor"],
                    instruction_manifest=values["instruction_manifest"],
                    adapter_manifest=values["adapter_manifest"],
                    effective_contract=values["effective_contract"],
                    workspace_root=values["launch_context"].cwd,
                    ephemeral_root=values["launch_context"].home,
                    transaction_root=values["launch_context"].admitted_lane_root,
                    config_root=values["launch_context"].grok_home,
                )


if __name__ == "__main__":
    unittest.main()
