from __future__ import annotations

import ast
import copy
import inspect
import os
import socket
import sys
import tempfile
import unittest
from pathlib import Path
from types import MappingProxyType, SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "puppet" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import puppet_lib.grok_shared_leader as shared_module  # noqa: E402
from puppet_lib.errors import IdentityError  # noqa: E402
from puppet_lib.grok_launch import (  # noqa: E402
    GROK_LAUNCH_AUTHORITY_BLOCKERS,
    GrokLaunchContext,
)
from puppet_lib.grok_shared_leader import (  # noqa: E402
    GROK_SHARED_CLIENT_BINDING_STATE,
    GROK_SHARED_CLIENT_COMPLETION_SCHEMA,
    GROK_SHARED_CLIENT_HALT_STRATEGY,
    GROK_SHARED_LEADER_BINDING_STATE,
    GROK_SHARED_LEADER_HUMAN_ACTION,
    GROK_SHARED_LEADER_PLAN_STATE,
    bind_grok_shared_client_runtime,
    bind_grok_shared_leader_runtime,
    build_grok_shared_leader_plan,
    validate_grok_shared_client_binding,
    validate_grok_shared_leader_binding,
    validate_grok_shared_leader_plan,
    verify_grok_shared_client_completion,
)


def process(pid: int, executable: Path) -> dict:
    details = executable.stat()
    return {
        "identity_version": 2,
        "pid": pid,
        "start": "darwin:200:%06d" % pid,
        "kernel_birth_id": "darwin:200:%06d" % pid,
        "command": "grok",
        "executable_path": str(executable),
        "device": details.st_dev,
        "inode": details.st_ino,
    }


def node(value: dict, parent_pid: int) -> dict:
    return {"process": value, "parent_pid": parent_pid}


class GrokSharedLeaderTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.executable = self.root / "grok-0.2.111-macos-aarch64"
        self.executable.write_bytes(b"synthetic Grok runtime")
        self.executable.chmod(0o700)
        self.lane = self.root / "lane"
        self.home = self.lane / "home"
        self.grok_home = self.lane / "grok-home"
        self.control = self.lane / "control"
        self.workspace = self.root / "workspace"
        for path in (
            self.lane,
            self.home,
            self.grok_home,
            self.control,
            self.workspace,
        ):
            path.mkdir(mode=0o700)
        self.leader_socket = self.control / "leader.sock"
        self.manifest_path = self.root / "manifest.json"
        self.manifest_path.write_text("{}\n", encoding="utf-8")
        details = self.executable.stat()
        self.selector = {
            "path": str(self.executable),
            "device": details.st_dev,
            "inode": details.st_ino,
        }
        self.manifest = SimpleNamespace(
            fingerprint="m" * 64,
            raw={
                "adapter_fingerprint": "a" * 64,
                "execution": {
                    "runtime_executable": {
                        **self.selector,
                        "size": details.st_size,
                        "mtime_ns": details.st_mtime_ns,
                        "sha256": "e" * 64,
                    }
                },
            },
        )
        session_id = "12345678-1234-4234-9234-123456789abc"
        empty = MappingProxyType({})
        environment = MappingProxyType(
            {
                "GROK_DISABLE_AUTOUPDATER": "true",
                "GROK_HOME": str(self.grok_home),
                "HOME": str(self.home),
                "LANG": "C",
                "LC_ALL": "C",
                "PATH": "/usr/bin:/bin",
            }
        )
        argv = (
            str(self.executable),
            "--always-approve",
            "--sandbox",
            "off",
            "--cwd",
            str(self.workspace),
            "--leader-socket",
            str(self.leader_socket),
            "--session-id",
            session_id,
        )
        self.context = GrokLaunchContext(
            doctor_manifest=self.manifest_path,
            doctor_manifest_fingerprint=self.manifest.fingerprint,
            adapter_fingerprint=self.manifest.raw["adapter_fingerprint"],
            executable=self.executable,
            admitted_lane_root=self.lane,
            home=self.home,
            grok_home=self.grok_home,
            cwd=self.workspace,
            leader_socket=self.leader_socket,
            admitted_lane_root_identity=empty,
            home_root_identity=empty,
            workspace_root_identity=empty,
            config_root_identity=empty,
            contract_identity=empty,
            run_identity=empty,
            controller_session="puppet-grok",
            run_id="grok-run",
            grok_session_id=session_id,
            argv=argv,
            environment=environment,
            launch_identity=empty,
            admitted_plan=empty,
            blockers=GROK_LAUNCH_AUTHORITY_BLOCKERS,
            launch_authorized=False,
        )
        self.leader = process(301, self.executable)
        self.leader_child = process(302, self.executable)
        self.client = process(401, self.executable)
        self.client_child = process(402, self.executable)
        self.alive = {
            value["kernel_birth_id"]
            for value in (
                self.leader,
                self.leader_child,
                self.client,
                self.client_child,
            )
        }
        self.tree_alive = set(self.alive)
        self.plan_patches = (
            patch.object(
                shared_module, "_revalidate_context_roots", return_value=None
            ),
            patch.object(
                shared_module,
                "_validated_grok_doctor_manifest",
                return_value=(self.manifest_path, self.manifest, self.executable),
            ),
        )

    def _is_alive(self, value: dict) -> bool:
        return value["kernel_birth_id"] in self.alive

    def _tree_is_alive(self, value: dict) -> bool:
        return value["process"]["kernel_birth_id"] in self.tree_alive

    def _plan(self, baseline=None):
        with self.plan_patches[0], self.plan_patches[1]:
            return build_grok_shared_leader_plan(
                self.context,
                baseline_processes=[] if baseline is None else baseline,
            )

    def _bind_socket(self):
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(str(self.leader_socket))
        os.chmod(self.leader_socket, 0o600)
        self.addCleanup(listener.close)
        return listener

    def _leader_snapshot(self):
        return {
            "processes": [self.leader, self.leader_child],
            "ancestry_nodes": [
                node(self.leader, 42),
                node(self.leader_child, self.leader["pid"]),
            ],
        }

    def _client_snapshot(self):
        return {
            "processes": [
                self.leader,
                self.leader_child,
                self.client,
                self.client_child,
            ],
            "ancestry_nodes": [
                node(self.leader, 42),
                node(self.leader_child, self.leader["pid"]),
                node(self.client, 52),
                node(self.client_child, self.client["pid"]),
            ],
        }

    def _bindings(self):
        plan = self._plan()
        self._bind_socket()
        leader = bind_grok_shared_leader_runtime(
            plan,
            leader_process=self.leader,
            snapshot=self._leader_snapshot(),
            process_alive_fn=self._is_alive,
            process_tree_alive_fn=self._tree_is_alive,
        )
        client = bind_grok_shared_client_runtime(
            plan,
            leader,
            client_process=self.client,
            snapshot=self._client_snapshot(),
            process_alive_fn=self._is_alive,
            process_tree_alive_fn=self._tree_is_alive,
        )
        return plan, leader, client

    def test_plan_emits_exact_human_handoff_and_closed_client(self):
        plan = self._plan()
        self.assertEqual(plan["state"], GROK_SHARED_LEADER_PLAN_STATE)
        self.assertEqual(
            plan["human_gate"]["action"], GROK_SHARED_LEADER_HUMAN_ACTION
        )
        self.assertEqual(
            plan["leader_start_argv"],
            [
                str(self.executable),
                "agent",
                "leader",
                "--no-exit-on-disconnect",
                "--relay-on-demand",
                "--no-auto-update",
                "--leader-socket",
                str(self.leader_socket),
            ],
        )
        self.assertEqual(plan["client_argv"], list(self.context.argv))
        self.assertEqual(
            plan["lifecycle_policy"]["client_halt_strategy"],
            GROK_SHARED_CLIENT_HALT_STRATEGY,
        )
        self.assertFalse(plan["lifecycle_policy"]["puppet_may_start_leader"])
        self.assertFalse(plan["lifecycle_policy"]["puppet_may_signal_leader"])
        self.assertFalse(plan["launch_authorized"])
        self.assertFalse(plan["qualification_authorized"])
        self.assertEqual(validate_grok_shared_leader_plan(plan), plan)

        with self.assertRaisesRegex(IdentityError, "empty same-target baseline"):
            self._plan([self.leader])

    def test_leader_binding_is_structural_and_grants_no_owner_claim(self):
        plan = self._plan()
        self._bind_socket()
        binding = bind_grok_shared_leader_runtime(
            plan,
            leader_process=self.leader,
            snapshot=self._leader_snapshot(),
            process_alive_fn=self._is_alive,
            process_tree_alive_fn=self._tree_is_alive,
        )
        self.assertEqual(binding["state"], GROK_SHARED_LEADER_BINDING_STATE)
        self.assertEqual(binding["leader_process"], self.leader)
        self.assertEqual(binding["leader_descendants"], [self.leader_child])
        self.assertFalse(binding["socket_owner_proved"])
        self.assertFalse(binding["client_launch_authorized"])
        self.assertFalse(binding["leader_signal_authorized"])
        self.assertEqual(validate_grok_shared_leader_binding(binding), binding)

    def test_client_binding_protects_leader_and_authorizes_no_broad_halt(self):
        _plan, leader, client = self._bindings()
        self.assertEqual(client["state"], GROK_SHARED_CLIENT_BINDING_STATE)
        self.assertEqual(
            client["protected_leader_processes"],
            [self.leader, self.leader_child],
        )
        self.assertEqual(client["client_process"], self.client)
        self.assertEqual(client["client_descendants"], [self.client_child])
        self.assertEqual(
            client["halt_delivery"],
            {
                "target_process": self.client,
                "actions": ["exact_pid_sigint"],
                "broad_signal_allowed": False,
                "force_kill_allowed": False,
                "preserve_leader": True,
                "preserve_socket": True,
            },
        )
        self.assertFalse(client["leader_signal_authorized"])
        self.assertEqual(validate_grok_shared_client_binding(client), client)
        self.assertFalse(leader["qualification_authorized"])

    def test_client_binding_rejects_different_runtime_and_socket_replacement(self):
        plan = self._plan()
        listener = self._bind_socket()
        leader = bind_grok_shared_leader_runtime(
            plan,
            leader_process=self.leader,
            snapshot=self._leader_snapshot(),
            process_alive_fn=self._is_alive,
            process_tree_alive_fn=self._tree_is_alive,
        )
        wrong = copy.deepcopy(self.client)
        wrong["inode"] += 1
        with self.assertRaisesRegex(IdentityError, "not exact and new"):
            bind_grok_shared_client_runtime(
                plan,
                leader,
                client_process=wrong,
                snapshot=self._client_snapshot(),
                process_alive_fn=self._is_alive,
                process_tree_alive_fn=self._tree_is_alive,
            )

        listener.close()
        self.leader_socket.unlink()
        replacement = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        replacement.bind(str(self.leader_socket))
        os.chmod(self.leader_socket, 0o600)
        self.addCleanup(replacement.close)
        with self.assertRaisesRegex(IdentityError, "socket changed"):
            bind_grok_shared_client_runtime(
                plan,
                leader,
                client_process=self.client,
                snapshot=self._client_snapshot(),
                process_alive_fn=self._is_alive,
                process_tree_alive_fn=self._tree_is_alive,
            )

    def test_completion_requires_client_gone_and_leader_socket_unchanged(self):
        plan, leader, client = self._bindings()
        self.alive.remove(self.client["kernel_birth_id"])
        self.alive.remove(self.client_child["kernel_birth_id"])
        self.tree_alive.remove(self.client["kernel_birth_id"])
        self.tree_alive.remove(self.client_child["kernel_birth_id"])
        after = {
            "processes": [self.leader, self.leader_child],
            "ancestry_nodes": [
                node(self.leader, 42),
                node(self.leader_child, self.leader["pid"]),
            ],
        }
        receipt = verify_grok_shared_client_completion(
            plan,
            leader,
            client,
            snapshot_after=after,
            process_alive_fn=self._is_alive,
            process_tree_alive_fn=self._tree_is_alive,
        )
        self.assertEqual(receipt["schema"], GROK_SHARED_CLIENT_COMPLETION_SCHEMA)
        self.assertTrue(receipt["client_halt_boundary_observed"])
        self.assertFalse(receipt["leader_signal_used"])
        self.assertFalse(receipt["leader_socket_owner_proved"])
        self.assertFalse(receipt["no_bleed_proved"])
        self.assertFalse(receipt["qualification_authorized"])

        self.alive.remove(self.leader_child["kernel_birth_id"])
        with self.assertRaisesRegex(IdentityError, "leader population changed"):
            verify_grok_shared_client_completion(
                plan,
                leader,
                client,
                snapshot_after=after,
                process_alive_fn=self._is_alive,
                process_tree_alive_fn=self._tree_is_alive,
            )

    def test_module_has_no_process_start_signal_or_store_read_surface(self):
        source = inspect.getsource(shared_module)
        tree = ast.parse(source)
        called = {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        self.assertFalse(
            called
            & {
                "execve",
                "kill",
                "open",
                "Popen",
                "run",
                "system",
            }
        )
        for forbidden in (
            "auth.json",
            "config.toml",
            "read_json",
            "read_text",
            "subprocess",
            "TmuxController",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
