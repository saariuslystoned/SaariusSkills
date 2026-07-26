from __future__ import annotations

import copy
import json
import os
import sys
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "puppet" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from puppet_lib import grok_qualification as qualification  # noqa: E402
from puppet_lib.adapter_manifest import (  # noqa: E402
    AdapterManifest,
    BEHAVIOR_CAPABILITIES,
    PROBE_CAPABILITIES,
)
from puppet_lib.authority import attest_qualification  # noqa: E402
from puppet_lib.errors import (  # noqa: E402
    ConflictError,
    IdentityError,
    UnsupportedError,
    ValidationError,
)
from puppet_lib.launch import build_launch_identity  # noqa: E402
from puppet_lib.safety import (  # noqa: E402
    canonical_json_bytes,
    sha256_bytes,
    sha256_file,
)


def write_json(path: Path, value) -> None:
    path.write_text(
        json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def directory_identity(path: Path) -> dict:
    details = path.stat()
    return {
        "path": str(path),
        "device": details.st_dev,
        "inode": details.st_ino,
        "uid": details.st_uid,
        "mode": details.st_mode & 0o777,
    }


def process(pid: int, *, executable: str = "/opt/grok") -> dict:
    return {
        "identity_version": 2,
        "pid": pid,
        "start": "darwin:100:%06d" % pid,
        "kernel_birth_id": "darwin:100:%06d" % pid,
        "command": "grok",
        "executable_path": executable,
        "device": 41,
        "inode": pid,
    }


def tmux_identity(root: Path, session: str, pid: int) -> dict:
    return {
        "socket": str(root / (session + ".tmux.sock")),
        "session": session,
        "target_id": "%%%d" % (pid % 100),
        "server_identity": process(pid + 1000, executable="/opt/tmux"),
        "tmux_binary_identity": {
            "path": "/opt/tmux",
            "device": 51,
            "inode": 52,
        },
    }


class GrokPairFixture:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.chmod(0o700)
        self.authority = self.root / "authority"
        self.authority.mkdir(mode=0o700)
        self.profile = self.root / "profile"
        self.profile.mkdir(mode=0o700)
        for name in ("home", "config", "tmp"):
            (self.profile / name).mkdir(mode=0o700)
        self.profile_binding = self._profile_binding()
        self.positive_root = self.root / "positive"
        self.ordinary_root = self.root / "ordinary"
        self.positive_workspace = self.root / "positive-workspace"
        self.ordinary_workspace = self.root / "ordinary-workspace"
        for path in (
            self.positive_root,
            self.ordinary_root,
            self.positive_workspace,
            self.ordinary_workspace,
        ):
            path.mkdir(mode=0o700)
        self.positive_path = self.positive_root / "receipt.json"
        self.ordinary_path = self.ordinary_root / "receipt.json"
        self.positive_view_path = self.positive_root / qualification.NATIVE_VIEW_NAME
        self.ordinary_view_path = self.ordinary_root / qualification.NATIVE_VIEW_NAME
        self.terminal_path = self.root / "grok-terminal.json"
        self.positive_process = process(2101)
        self.ordinary_process = process(2201)
        self.positive_tmux = tmux_identity(self.root, "grok-positive", 3101)
        self.ordinary_tmux = tmux_identity(self.root, "grok-ordinary", 3201)
        self.positive_vector = self._vector(
            self.positive_workspace, "grok-positive", "positive-run"
        )
        self.ordinary_vector = self._vector(
            self.ordinary_workspace, "grok-ordinary", "ordinary-run"
        )
        self.descriptor_sha = "11" * 32
        self.instruction_sha = "12" * 32
        self.instruction_relative = (
            ".grok/rules/puppet-%s.md" % self.instruction_sha
        )
        self._write_positive_artifacts()
        self._write_ordinary_artifacts()
        self.positive = self._receipt(
            run_id="positive-run",
            checkpoint="21" * 32,
            acceptance="22" * 32,
            halt="23" * 32,
        )
        self.positive["grok_pairing"] = qualification.build_grok_pair_member_source(
            role="positive",
            runtime_vector=self.positive_vector["record"],
            descriptor_sha256=self.descriptor_sha,
            instruction_artifact={
                "relative_path": self.instruction_relative,
                "sha256": self.instruction_sha,
            },
            ordinary_instruction_absent=False,
        )
        self.positive["grok_control_source"] = None
        self.positive["controller_attestation"] = attest_qualification(
            self.positive, authority_root=self.authority
        )
        write_json(self.positive_path, self.positive)
        control = qualification.build_grok_control_source(
            self.positive_path,
            authority_root=self.authority,
            current_manifest=None,
            _verify_receipt_fn=self.verify_receipt,
        )
        self.ordinary = self._receipt(
            run_id="ordinary-run",
            checkpoint="31" * 32,
            acceptance="32" * 32,
            halt="33" * 32,
        )
        self.ordinary["grok_pairing"] = qualification.build_grok_pair_member_source(
            role="ordinary_control",
            runtime_vector=self.ordinary_vector["record"],
            positive_receipt_path=self.positive_path,
            ordinary_absence_sha256=sha256_file(
                self.ordinary_root / "grok-ordinary-absence.json"
            ),
            ordinary_instruction_absent=True,
        )
        self.ordinary["grok_control_source"] = control
        self.ordinary["controller_attestation"] = attest_qualification(
            self.ordinary, authority_root=self.authority
        )
        write_json(self.ordinary_path, self.ordinary)
        self.artifacts = {
            str(self.positive_path): self._artifacts(
                positive=True,
                workspace=self.positive_workspace,
                vector=self.positive_vector,
                target_process=self.positive_process,
                tmux=self.positive_tmux,
                session="grok-positive",
                halt_sha=self.positive["halt_receipt_sha256"],
            ),
            str(self.ordinary_path): self._artifacts(
                positive=False,
                workspace=self.ordinary_workspace,
                vector=self.ordinary_vector,
                target_process=self.ordinary_process,
                tmux=self.ordinary_tmux,
                session="grok-ordinary",
                halt_sha=self.ordinary["halt_receipt_sha256"],
            ),
        }
        self._write_view(
            self.positive_view_path,
            receipt=self.positive,
            artifacts=self.artifacts[str(self.positive_path)],
            viewer_pid=5101,
            tty="/dev/ttys051",
        )
        self._write_view(
            self.ordinary_view_path,
            receipt=self.ordinary,
            artifacts=self.artifacts[str(self.ordinary_path)],
            viewer_pid=5201,
            tty="/dev/ttys052",
        )

    def _profile_binding(self) -> dict:
        executable = {
            "path": "/opt/grok",
            "device": 61,
            "inode": 62,
            "size": 100,
            "mtime_ns": 123,
            "sha256": "41" * 32,
        }
        directories = {
            name: directory_identity(self.profile / name)
            for name in ("home", "config", "tmp")
        }
        return {
            "schema": "puppet.subscription-launch-binding/v1",
            "target": "grok",
            "profile_root": str(self.profile),
            "root_identity": directory_identity(self.profile),
            "directory_identities": directories,
            "real_home_identity": directories["home"],
            "auth_route": "synthetic_profile_home",
            "manifest_path": str(self.profile / "profile.json"),
            "manifest_sha256": "42" * 32,
            "executable": executable,
            "launch_env_names": [
                "GROK_DISABLE_AUTOUPDATER",
                "GROK_HOME",
                "HOME",
                "LANG",
                "LC_ALL",
                "PATH",
                "TMPDIR",
            ],
            "login_only_env_names": [],
            "status": {
                "schema": "puppet.subscription-profile-status/v1",
                "target": "grok",
                "profile_root": str(self.profile),
                "auth_route": "synthetic_profile_home",
                "login_state": "logged_in",
                "method": "private_grok_home",
                "default_model": "grok-4.5",
                "status_exit": 0,
                "raw_output_retained": False,
                "login_performed": False,
                "model_launched": False,
            },
        }

    def _vector(self, workspace: Path, session: str, run_id: str) -> dict:
        return qualification.build_grok_runtime_vector(
            base_argv=["/opt/grok", "--always-approve", "--sandbox", "off"],
            subscription_binding=self.profile_binding,
            cwd=workspace,
            leader_socket=self.profile / "tmp" / ("%s.sock" % run_id),
            session_uuid=qualification.derive_grok_session_uuid(
                session=session, run_id=run_id
            ),
        )

    def _receipt(
        self, *, run_id: str, checkpoint: str, acceptance: str, halt: str
    ) -> dict:
        return {
            "schema_version": 5,
            "kind": "real_harness_conformance",
            "run_id": run_id,
            "target": "grok",
            "session_profile": "regular",
            "result": "accepted",
            "controller": "controller-worker",
            "campaign_id": "campaign-grok-pair",
            "goal_fingerprint": "51" * 32,
            "executable_fingerprint": "41" * 32,
            "execution_fingerprint": "52" * 32,
            "version_fingerprint": "53" * 32,
            "platform_fingerprint": "54" * 32,
            "adapter_fingerprint": "55" * 32,
            "protocol_fingerprint": "56" * 32,
            "yolo_mapping_sha256": "57" * 32,
            "launch_plan_sha256": "58" * 32,
            "subscription_profile_sha256": "59" * 32,
            "instruction_policy_fingerprint": "5a" * 32,
            "capabilities": list(PROBE_CAPABILITIES),
            "accepted_checkpoint_id": checkpoint,
            "acceptance_sha256": acceptance,
            "halt_receipt_sha256": halt,
            "plane_activation": None,
            "workspace_isolation": None,
            "codex_entry_source": None,
            "codex_control_source": None,
            "proof_refs": [],
        }

    def _write_positive_artifacts(self) -> None:
        write_json(
            self.positive_root / "workspace-descriptor.json",
            {"descriptor_sha256": self.descriptor_sha},
        )
        write_json(
            self.positive_root / "workspace-materialization.json",
            {
                "relative_path": self.instruction_relative,
                "content_sha256": self.instruction_sha,
                "created": True,
            },
        )
        write_json(
            self.positive_root / "workspace-rollback.json",
            {
                "expected_content_sha256": self.instruction_sha,
                "absent_after": True,
            },
        )

    def _write_ordinary_artifacts(self) -> None:
        write_json(
            self.ordinary_root / "grok-ordinary-absence.json",
            {
                "schema": "puppet.grok-ordinary-absence/v1",
                "target": "grok",
                "run_id": "ordinary-run",
                "workspace_root": str(self.ordinary_workspace),
                "puppet_rule_count_before": 0,
                "puppet_rule_count_after": 0,
                "ordinary_instruction_absent": True,
                "raw_retained": False,
            },
        )

    def _artifacts(
        self,
        *,
        positive: bool,
        workspace: Path,
        vector: dict,
        target_process: dict,
        tmux: dict,
        session: str,
        halt_sha: str,
    ) -> dict:
        environment = vector["environment"]
        launch = {
            "cwd": str(workspace),
            "argv": vector["argv"],
            "launch_identity": {
                "env_names": sorted(environment),
                "env_fingerprint": sha256_bytes(
                    canonical_json_bytes(
                        [(name, environment[name]) for name in sorted(environment)]
                    )
                ),
            },
        }
        child = process(target_process["pid"] + 1)
        evidence = {
            "process": target_process,
            "tmux": tmux,
            "active_target_processes_before_launch": [],
            "active_target_processes_after_halt": [],
            "observed_target_descendants": [
                {
                    "process": child,
                    "ancestry_chain": [
                        {"process": child, "parent_pid": target_process["pid"]},
                        {"process": target_process, "parent_pid": 1},
                    ],
                }
            ],
        }
        halt = {
            "signal": "exact_registered_pid_sigint",
            "cleanup_scope": "exact_new_target_only",
            "stopped": True,
            "target_pid": target_process["pid"],
        }
        paths = {}
        if positive:
            paths = {
                "workspace_descriptor": (
                    self.positive_root / "workspace-descriptor.json"
                ),
                "workspace_materialization": (
                    self.positive_root / "workspace-materialization.json"
                ),
                "workspace_rollback": (
                    self.positive_root / "workspace-rollback.json"
                ),
            }
        else:
            paths = {
                "grok_ordinary_absence": (
                    self.ordinary_root / "grok-ordinary-absence.json"
                )
            }
        return {
            "paths": paths,
            "state": {"run_id": "positive-run" if positive else "ordinary-run"},
            "session": session,
            "launch": launch,
            "profile": copy.deepcopy(self.profile_binding),
            "evidence": evidence,
            "halt": halt,
            "halt_sha": halt_sha,
        }

    @staticmethod
    def _attach_argv(artifacts: dict) -> list[str]:
        tmux = artifacts["evidence"]["tmux"]
        return [
            tmux["tmux_binary_identity"]["path"],
            "-f",
            os.devnull,
            "-S",
            tmux["socket"],
            "attach-session",
            "-r",
            "-E",
            "-t",
            tmux["session"],
        ]

    def _write_view(
        self,
        path: Path,
        *,
        receipt: dict,
        artifacts: dict,
        viewer_pid: int,
        tty: str,
    ) -> None:
        evidence = artifacts["evidence"]
        write_json(
            path,
            {
                "schema": qualification.NATIVE_VIEW_SCHEMA,
                "target": "grok",
                "run_id": receipt["run_id"],
                "session": artifacts["session"],
                "tmux_identity_sha256": sha256_bytes(
                    canonical_json_bytes(evidence["tmux"])
                ),
                "target_process_sha256": sha256_bytes(
                    canonical_json_bytes(evidence["process"])
                ),
                "attach_argv_sha256": sha256_bytes(
                    canonical_json_bytes(self._attach_argv(artifacts))
                ),
                "viewer": {
                    "pid": viewer_pid,
                    "tty": tty,
                    "read_only": True,
                    "session": artifacts["session"],
                },
                "read_only": True,
                "attached": True,
                "detached": True,
                "target_alive_after_detach": True,
                "body_capture_performed": False,
                "raw_retained": False,
            },
        )

    def verify_receipt(self, path, **_kwargs):
        selected = Path(path)
        if selected == self.positive_path:
            return copy.deepcopy(self.positive)
        if selected == self.ordinary_path:
            return copy.deepcopy(self.ordinary)
        raise AssertionError("unexpected Grok receipt")

    def patches(self):
        stack = ExitStack()
        stack.enter_context(
            patch.object(
                qualification,
                "_receipt_artifacts",
                side_effect=lambda path, _receipt: copy.deepcopy(
                    self.artifacts[str(Path(path))]
                ),
            )
        )
        return stack

    def build(self) -> dict:
        with self.patches():
            value = qualification.build_grok_terminal_qualification(
                positive_receipt_path=self.positive_path,
                ordinary_receipt_path=self.ordinary_path,
                positive_native_view_path=self.positive_view_path,
                ordinary_native_view_path=self.ordinary_view_path,
                private_profile_root=self.profile,
                authority_root=self.authority,
                _verify_receipt_fn=self.verify_receipt,
            )
        write_json(self.terminal_path, value)
        return value


class GrokRuntimeVectorTests(unittest.TestCase):
    def test_private_profile_bindings_survive_launch_identity_revalidation(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = GrokPairFixture(Path(temporary))
            source, bindings, profile_root = (
                qualification.subscription_binding_environment(
                    fixture.profile_binding,
                    expected_target="grok",
                )
            )

            environment, _ = build_launch_identity(
                target="grok",
                repo=fixture.positive_workspace,
                argv=fixture.positive_vector["argv"],
                source_environment=source,
                bindings=bindings,
                admitted_lane_root=profile_root,
            )

            self.assertEqual(
                environment,
                fixture.positive_vector["environment"],
            )
            self.assertIn("GROK_HOME", environment)
            self.assertIn("GROK_DISABLE_AUTOUPDATER", environment)

    def test_private_profile_vector_is_exact_and_default_bound(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = GrokPairFixture(Path(temporary))
            vector = fixture.positive_vector
            self.assertEqual(
                vector["argv"][-8:],
                [
                    "--no-leader",
                    "--trust",
                    "--cwd",
                    str(fixture.positive_workspace),
                    "--leader-socket",
                    str(fixture.profile / "tmp" / "positive-run.sock"),
                    "--session-id",
                    vector["record"]["session_uuid"],
                ],
            )
            self.assertEqual(vector["record"]["profile_root"], str(fixture.profile))
            self.assertNotIn("--model", vector["argv"])
            self.assertNotIn("--reasoning-effort", vector["argv"])
            self.assertEqual(
                qualification.validate_grok_runtime_vector(
                    vector["record"],
                    launch_plan=fixture.artifacts[str(fixture.positive_path)]["launch"],
                    subscription_binding=fixture.profile_binding,
                ),
                vector["record"],
            )

            launch = copy.deepcopy(
                fixture.artifacts[str(fixture.positive_path)]["launch"]
            )
            launch["argv"].extend(["--model", "attacker"])
            with self.assertRaisesRegex(IdentityError, "argv"):
                qualification.validate_grok_runtime_vector(
                    vector["record"],
                    launch_plan=launch,
                    subscription_binding=fixture.profile_binding,
                )
            binding = copy.deepcopy(fixture.profile_binding)
            binding["status"]["default_model"] = "attacker-model"
            with self.assertRaises((IdentityError, ValidationError)):
                qualification.validate_grok_runtime_vector(
                    vector["record"],
                    launch_plan=fixture.artifacts[str(fixture.positive_path)][
                        "launch"
                    ],
                    subscription_binding=binding,
                )
            binding["status"]["default_model"] = "unknown"
            with self.assertRaisesRegex(IdentityError, "qualified default"):
                qualification.validate_grok_runtime_vector(
                    vector["record"],
                    launch_plan=fixture.artifacts[str(fixture.positive_path)][
                        "launch"
                    ],
                    subscription_binding=binding,
                )

    def test_socket_uuid_cwd_and_existing_socket_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = GrokPairFixture(Path(temporary))
            record = copy.deepcopy(fixture.positive_vector["record"])
            record["session_uuid"] = "not-a-uuid"
            unsigned = dict(record)
            unsigned.pop("vector_sha256")
            record["vector_sha256"] = sha256_bytes(canonical_json_bytes(unsigned))
            with self.assertRaisesRegex((ValidationError, IdentityError), "UUID|argv"):
                qualification.validate_grok_runtime_vector(
                    record,
                    launch_plan=fixture.artifacts[str(fixture.positive_path)][
                        "launch"
                    ],
                    subscription_binding=fixture.profile_binding,
                )
            existing = fixture.profile / "tmp" / "existing.sock"
            existing.write_text("", encoding="utf-8")
            with self.assertRaises(ConflictError):
                qualification.build_grok_runtime_vector(
                    base_argv=[
                        "/opt/grok",
                        "--always-approve",
                        "--sandbox",
                        "off",
                    ],
                    subscription_binding=fixture.profile_binding,
                    cwd=fixture.positive_workspace,
                    leader_socket=existing,
                    session_uuid=qualification.derive_grok_session_uuid(
                        session="new-session", run_id="new-run"
                    ),
                )
            with self.assertRaisesRegex(IdentityError, "outside"):
                qualification.build_grok_runtime_vector(
                    base_argv=[
                        "/opt/grok",
                        "--always-approve",
                        "--sandbox",
                        "off",
                    ],
                    subscription_binding=fixture.profile_binding,
                    cwd=fixture.positive_workspace,
                    leader_socket=fixture.root / "ancestor-escape.sock",
                    session_uuid=qualification.derive_grok_session_uuid(
                        session="escape-session", run_id="escape-run"
                    ),
                )


class GrokNativeViewTests(unittest.TestCase):
    def test_probe_rendezvous_waits_for_and_revalidates_native_view(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = GrokPairFixture(Path(temporary))
            artifacts = fixture.artifacts[str(fixture.positive_path)]
            evidence = artifacts["evidence"]
            receipt = fixture.positive
            guards = []
            result = qualification.await_grok_native_view(
                run_root=fixture.positive_root,
                receipt=receipt,
                session=fixture.positive_tmux["session"],
                evidence=evidence,
                attach_argv=fixture._attach_argv(artifacts),
                runtime_guard=lambda: guards.append("guarded"),
                timeout=1.0,
            )
            self.assertTrue(result["read_only"])
            self.assertEqual(guards, ["guarded", "guarded"])

    def test_probe_rendezvous_fails_closed_without_native_view(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            ticks = iter([0.0, 0.0, 1.0])
            with self.assertRaisesRegex(UnsupportedError, "was not observed"):
                qualification.await_grok_native_view(
                    run_root=root,
                    receipt={"run_id": "missing-view"},
                    session="missing-view",
                    evidence={},
                    attach_argv=["tmux", "attach"],
                    runtime_guard=lambda: None,
                    timeout=0.5,
                    _sleep_fn=lambda _seconds: None,
                    _monotonic_fn=lambda: next(ticks),
                )

    def test_structural_read_only_attach_and_detach_without_capture(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            (root / "tmux-authority").mkdir(mode=0o700)
            target = process(4101)
            tmux = tmux_identity(root, "grok-live-view", 4201)
            write_json(
                root / "state.json",
                {
                    "target": "grok",
                    "run_id": "grok-live-run",
                    "phase": "ready_validated",
                    "attach_command": "tmux read-only attach",
                },
            )
            write_json(
                root / "evidence.json",
                {
                    "target": "grok",
                    "run_id": "grok-live-run",
                    "tmux": tmux,
                    "process": target,
                },
            )
            viewer = {
                "pid": 4301,
                "tty": "/dev/ttys043",
                "read_only": True,
                "session": "grok-live-view",
            }
            controller = SimpleNamespace()
            client_samples = iter([[], [viewer], []])
            controller.viewer_clients = lambda **_kwargs: next(client_samples)
            attach = GrokPairFixture._attach_argv(
                {"evidence": {"tmux": tmux}}
            )
            controller.attach_argv = lambda **_kwargs: attach
            ticks = iter([0.0, 0.1, 0.2, 0.3])

            def birth(pid: int) -> dict:
                if pid == target["pid"]:
                    return copy.deepcopy(target)
                result = process(pid, executable="/opt/tmux")
                result["device"] = 51
                result["inode"] = 52
                return result

            result = qualification.record_grok_native_view(
                run_root=root,
                timeout=1.0,
                _tmux_factory=lambda _root: controller,
                _process_birth_fn=birth,
                _sleep_fn=lambda _seconds: None,
                _monotonic_fn=lambda: next(ticks),
            )
            self.assertTrue(result["read_only"])
            self.assertTrue(result["attached"])
            self.assertTrue(result["detached"])
            self.assertFalse(result["body_capture_performed"])
            self.assertFalse(result["raw_retained"])

    def test_writable_or_multiple_viewer_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            (root / "tmux-authority").mkdir(mode=0o700)
            target = process(4401)
            tmux = tmux_identity(root, "grok-bad-view", 4501)
            write_json(
                root / "state.json",
                {
                    "target": "grok",
                    "run_id": "grok-bad-run",
                    "phase": "followup_validated",
                    "attach_command": "tmux attach",
                },
            )
            write_json(
                root / "evidence.json",
                {
                    "target": "grok",
                    "run_id": "grok-bad-run",
                    "tmux": tmux,
                    "process": target,
                },
            )
            controller = SimpleNamespace()
            bad = {
                "pid": 4601,
                "tty": "/dev/ttys046",
                "read_only": False,
                "session": "grok-bad-view",
            }
            samples = iter([[], [bad]])
            controller.viewer_clients = lambda **_kwargs: next(samples)
            controller.attach_argv = lambda **_kwargs: []
            ticks = iter([0.0, 0.1, 0.2])
            with self.assertRaisesRegex(IdentityError, "read-only"):
                qualification.record_grok_native_view(
                    run_root=root,
                    timeout=1.0,
                    _tmux_factory=lambda _root: controller,
                    _process_birth_fn=lambda _pid: target,
                    _sleep_fn=lambda _seconds: None,
                    _monotonic_fn=lambda: next(ticks),
                )


class GrokTerminalPairTests(unittest.TestCase):
    def test_terminal_pair_round_trip_and_independent_rebuild(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = GrokPairFixture(Path(temporary))
            value = fixture.build()
            self.assertTrue(value["qualification_authorized"])
            self.assertTrue(value["public_launch_authorized"])
            self.assertTrue(value["matched_control"]["no_bleed_verified"])
            self.assertEqual(
                value["profile_status"]["default_model"], "grok-4.5"
            )
            with fixture.patches():
                rebuilt = qualification.verify_grok_terminal_qualification(
                    fixture.terminal_path,
                    expected_private_profile_root=fixture.profile,
                    authority_root=fixture.authority,
                    _verify_receipt_fn=fixture.verify_receipt,
                )
            self.assertEqual(rebuilt, value)

    def test_manifest_terminal_branch_verifies_mapping_and_capabilities(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = GrokPairFixture(Path(temporary))
            value = fixture.build()
            platform = {"system": "Darwin", "release": "25", "machine": "arm64"}
            probe_mapping = {
                "complete": False,
                "project_isolation_declared": False,
            }
            qualified_mapping = {
                "complete": True,
                "project_isolation_declared": True,
            }
            value["platform_fingerprint"] = sha256_bytes(
                canonical_json_bytes(platform)
            )
            value["yolo_mapping_sha256"] = sha256_bytes(
                canonical_json_bytes(probe_mapping)
            )
            fake = SimpleNamespace(
                target="grok",
                raw={
                    "doctor_only": False,
                    "qualification": {
                        "receipt_path": str(fixture.terminal_path),
                        "receipt_sha256": sha256_file(fixture.terminal_path),
                        "session_profile": "regular",
                    },
                    "executable": {
                        "version_sha256": value["version_fingerprint"],
                    },
                    "platform": platform,
                    "yolo_mapping": qualified_mapping,
                    "capabilities": {
                        name: (
                            "controller_verified"
                            if name in PROBE_CAPABILITIES
                            else "unsupported"
                        )
                        for name in BEHAVIOR_CAPABILITIES
                    },
                },
                identity_matches=lambda **_kwargs: True,
            )
            with (
                patch.object(
                    qualification,
                    "verify_grok_terminal_qualification",
                    return_value=value,
                ),
                patch(
                    "puppet_lib.grok_workspace_plane.grok_qualified_mapping",
                    return_value=qualified_mapping,
                ) as closure,
            ):
                verified = AdapterManifest.verify_qualification(
                    fake, expected_session_profile="regular"
                )
            self.assertEqual(verified, value)
            closure.assert_called_once_with(probe_mapping)

    def test_pair_rejects_relinked_control_missing_view_and_shared_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = GrokPairFixture(Path(temporary))
            fixture.ordinary["grok_control_source"]["run_id"] = "relinked-run"
            with fixture.patches(), self.assertRaisesRegex(
                IdentityError, "relinked"
            ):
                qualification.build_grok_terminal_qualification(
                    positive_receipt_path=fixture.positive_path,
                    ordinary_receipt_path=fixture.ordinary_path,
                    positive_native_view_path=fixture.positive_view_path,
                    ordinary_native_view_path=fixture.ordinary_view_path,
                    private_profile_root=fixture.profile,
                    authority_root=fixture.authority,
                    _verify_receipt_fn=fixture.verify_receipt,
                )

        with tempfile.TemporaryDirectory() as temporary:
            fixture = GrokPairFixture(Path(temporary))
            fixture.ordinary_view_path.unlink()
            with self.assertRaisesRegex(ValidationError, "view"):
                fixture.build()

        with tempfile.TemporaryDirectory() as temporary:
            fixture = GrokPairFixture(Path(temporary))
            fixture.artifacts[str(fixture.ordinary_path)]["evidence"][
                "process"
            ] = copy.deepcopy(fixture.positive_process)
            with fixture.patches(), self.assertRaisesRegex(
                IdentityError, "identities"
            ):
                qualification.build_grok_terminal_qualification(
                    positive_receipt_path=fixture.positive_path,
                    ordinary_receipt_path=fixture.ordinary_path,
                    positive_native_view_path=fixture.positive_view_path,
                    ordinary_native_view_path=fixture.ordinary_view_path,
                    private_profile_root=fixture.profile,
                    authority_root=fixture.authority,
                    _verify_receipt_fn=fixture.verify_receipt,
                )

    def test_pair_rejects_baseline_drift_bad_halt_and_malformed_ancestry(self):
        for mutation, message in (
            ("baseline", "baseline|halt"),
            ("halt", "halt"),
            ("ancestry", "ancestry"),
        ):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                fixture = GrokPairFixture(Path(temporary))
                ordinary = fixture.artifacts[str(fixture.ordinary_path)]
                if mutation == "baseline":
                    ordinary["evidence"][
                        "active_target_processes_after_halt"
                    ] = [process(9991)]
                elif mutation == "halt":
                    ordinary["halt"]["stopped"] = False
                else:
                    ordinary["evidence"]["observed_target_descendants"][0][
                        "ancestry_chain"
                    ] = None
                with fixture.patches(), self.assertRaisesRegex(
                    (IdentityError, ValidationError), message
                ):
                    qualification.build_grok_terminal_qualification(
                        positive_receipt_path=fixture.positive_path,
                        ordinary_receipt_path=fixture.ordinary_path,
                        positive_native_view_path=fixture.positive_view_path,
                        ordinary_native_view_path=fixture.ordinary_view_path,
                        private_profile_root=fixture.profile,
                        authority_root=fixture.authority,
                        _verify_receipt_fn=fixture.verify_receipt,
                    )

    def test_synthetic_ordinary_absence_and_stale_manifest_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = GrokPairFixture(Path(temporary))
            member = copy.deepcopy(fixture.ordinary["grok_pairing"])
            member["ordinary_absence_sha256"] = None
            with self.assertRaises(ValidationError):
                qualification.validate_grok_pair_member_source(member)

            fixture.build()
            stale = SimpleNamespace(
                raw={
                    "executable": {
                        "sha256": "ff" * 32,
                        "version_sha256": fixture.positive[
                            "version_fingerprint"
                        ],
                    },
                    "adapter_fingerprint": fixture.positive[
                        "adapter_fingerprint"
                    ],
                    "protocol_fingerprint": fixture.positive[
                        "protocol_fingerprint"
                    ],
                    "platform": {},
                },
                execution_fingerprint=fixture.positive["execution_fingerprint"],
            )
            with fixture.patches(), self.assertRaisesRegex(
                IdentityError, "stale"
            ):
                qualification.verify_grok_terminal_qualification(
                    fixture.terminal_path,
                    expected_private_profile_root=fixture.profile,
                    authority_root=fixture.authority,
                    current_manifest=stale,
                    _verify_receipt_fn=fixture.verify_receipt,
                )


if __name__ == "__main__":
    unittest.main()
