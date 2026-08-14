from __future__ import annotations

import copy
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

import puppet_lib.grok_halt as grok_halt  # noqa: E402
from puppet_lib.errors import IdentityError  # noqa: E402
from puppet_lib.grok_halt import (  # noqa: E402
    GROK_HALT_BINDING_STATE,
    GROK_HALT_PLAN_STATE,
    GROK_HALT_RUNTIME_BLOCKER,
    bind_grok_halt_runtime_tree,
    build_grok_halt_authority_plan,
    validate_grok_halt_authority_plan,
    validate_grok_halt_runtime_binding,
    verify_grok_halt_completion,
)
from puppet_lib.grok_launch import (  # noqa: E402
    GROK_LAUNCH_AUTHORITY_BLOCKERS,
    GrokLaunchContext,
)


def process(pid: int, executable: Path, *, command: str = "grok") -> dict:
    details = executable.stat()
    return {
        "identity_version": 2,
        "pid": pid,
        "start": "darwin:100:%06d" % pid,
        "kernel_birth_id": "darwin:100:%06d" % pid,
        "command": command,
        "executable_path": str(executable),
        "device": details.st_dev,
        "inode": details.st_ino,
    }


def node(value: dict, parent_pid: int) -> dict:
    return {"process": value, "parent_pid": parent_pid}


class GrokHaltAuthorityTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.executable = self.root / "grok-0.2.112-macos-aarch64"
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
        empty = MappingProxyType({})
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
            grok_session_id="12345678-1234-4234-9234-123456789abc",
            argv=(str(self.executable),),
            environment=empty,
            launch_identity=empty,
            admitted_plan=empty,
            blockers=GROK_LAUNCH_AUTHORITY_BLOCKERS,
            launch_authorized=False,
        )
        self.protected = process(101, self.executable)
        self.root_process = process(201, self.executable)
        self.child = process(202, self.executable)
        self.alive = {
            self.protected["kernel_birth_id"],
            self.root_process["kernel_birth_id"],
            self.child["kernel_birth_id"],
        }
        self.tree_alive = {
            self.protected["kernel_birth_id"],
            self.root_process["kernel_birth_id"],
            self.child["kernel_birth_id"],
        }
        self.plan_patches = (
            patch.object(grok_halt, "_revalidate_context_roots", return_value=None),
            patch.object(
                grok_halt,
                "_validated_grok_doctor_manifest",
                return_value=(self.manifest_path, self.manifest, self.executable),
            ),
        )

    def _is_alive(self, value: dict) -> bool:
        return value["kernel_birth_id"] in self.alive

    def _tree_is_alive(self, value: dict) -> bool:
        return value["process"]["kernel_birth_id"] in self.tree_alive

    def _plan(self, protected=None):
        with self.plan_patches[0], self.plan_patches[1]:
            return build_grok_halt_authority_plan(
                self.context,
                protected_processes=(
                    [self.protected] if protected is None else protected
                ),
                process_alive_fn=self._is_alive,
            )

    def _snapshot(self):
        return {
            "processes": [self.protected, self.root_process, self.child],
            "ancestry_nodes": [
                node(self.protected, 1),
                node(self.root_process, 42),
                node(self.child, self.root_process["pid"]),
            ],
        }

    def _bind_socket(self):
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(str(self.leader_socket))
        os.chmod(self.leader_socket, 0o600)
        self.addCleanup(listener.close)
        return listener

    def _binding(self):
        plan = self._plan()
        self._bind_socket()
        binding = bind_grok_halt_runtime_tree(
            plan,
            root_process=self.root_process,
            snapshot=self._snapshot(),
            process_alive_fn=self._is_alive,
            process_tree_alive_fn=self._tree_is_alive,
        )
        return plan, binding

    def test_plan_is_body_free_and_binds_only_exact_protected_population(self):
        plan = self._plan()
        self.assertEqual(plan["state"], GROK_HALT_PLAN_STATE)
        self.assertEqual(plan["protected_processes"], [self.protected])
        self.assertEqual(plan["blockers"], [GROK_HALT_RUNTIME_BLOCKER])
        self.assertFalse(plan["launch_authorized"])
        self.assertNotIn("prompt", repr(plan).lower())

        wrong = copy.deepcopy(self.protected)
        wrong["inode"] += 1
        with self.assertRaisesRegex(IdentityError, "not exact and live"):
            self._plan([wrong])

        changed = copy.deepcopy(plan)
        changed["leader_socket"] = str(self.control / "other.sock")
        with self.assertRaisesRegex(IdentityError, "identity changed"):
            validate_grok_halt_authority_plan(changed)

    def test_runtime_binding_admits_retained_root_and_exact_descendants(self):
        _plan, binding = self._binding()
        self.assertEqual(binding["state"], GROK_HALT_BINDING_STATE)
        self.assertEqual(binding["root_process"], self.root_process)
        self.assertEqual(binding["descendants"], [self.child])
        self.assertEqual(
            binding["ancestry_chains"],
            [[node(self.child, self.root_process["pid"]), node(self.root_process, 42)]],
        )
        self.assertEqual(
            binding["halt_delivery"],
            {
                "target_process": self.root_process,
                "actions": ["exact_pid_sigint"],
                "broad_signal_allowed": False,
                "force_kill_allowed": False,
            },
        )

    def test_runtime_binding_rejects_unrelated_or_different_runtime_children(self):
        plan = self._plan()
        self._bind_socket()
        unrelated = self._snapshot()
        unrelated["ancestry_nodes"][2] = node(self.child, 9999)
        with self.assertRaisesRegex(IdentityError, "ancestry chain"):
            bind_grok_halt_runtime_tree(
                plan,
                root_process=self.root_process,
                snapshot=unrelated,
                process_alive_fn=self._is_alive,
                process_tree_alive_fn=self._tree_is_alive,
            )

        different = self._snapshot()
        different_child = copy.deepcopy(self.child)
        different_child["inode"] += 1
        different["processes"][2] = different_child
        different["ancestry_nodes"][2] = node(
            different_child, self.root_process["pid"]
        )
        with self.assertRaisesRegex(IdentityError, "registered executable"):
            bind_grok_halt_runtime_tree(
                plan,
                root_process=self.root_process,
                snapshot=different,
                process_alive_fn=self._is_alive,
                process_tree_alive_fn=self._tree_is_alive,
            )

    def test_runtime_binding_rejects_forged_delivery_or_public_socket(self):
        plan = self._plan()
        self._bind_socket()
        binding = bind_grok_halt_runtime_tree(
            plan,
            root_process=self.root_process,
            snapshot=self._snapshot(),
            process_alive_fn=self._is_alive,
            process_tree_alive_fn=self._tree_is_alive,
        )
        forged = copy.deepcopy(binding)
        forged["halt_delivery"]["broad_signal_allowed"] = True
        with self.assertRaisesRegex(IdentityError, "delivery authority"):
            validate_grok_halt_runtime_binding(forged)

        self.leader_socket.unlink()
        public = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        public.bind(str(self.leader_socket))
        os.chmod(self.leader_socket, 0o666)
        self.addCleanup(public.close)
        with self.assertRaisesRegex(IdentityError, "private and exact"):
            bind_grok_halt_runtime_tree(
                plan,
                root_process=self.root_process,
                snapshot=self._snapshot(),
                process_alive_fn=self._is_alive,
                process_tree_alive_fn=self._tree_is_alive,
            )

    def test_completion_requires_whole_new_tree_gone_and_protected_unchanged(self):
        plan, binding = self._binding()
        self.alive.remove(self.root_process["kernel_birth_id"])
        self.alive.remove(self.child["kernel_birth_id"])
        self.tree_alive.remove(self.root_process["kernel_birth_id"])
        self.tree_alive.remove(self.child["kernel_birth_id"])
        self.leader_socket.unlink()
        after = {
            "processes": [self.protected],
            "ancestry_nodes": [node(self.protected, 1)],
        }
        receipt = verify_grok_halt_completion(
            plan,
            binding,
            snapshot_after=after,
            process_alive_fn=self._is_alive,
            process_tree_alive_fn=self._tree_is_alive,
        )
        self.assertTrue(receipt["halt_authority_proved"])
        self.assertFalse(receipt["broad_signal_used"])
        self.assertFalse(receipt["qualification_authorized"])

    def test_completion_fails_closed_on_survivor_socket_or_population_drift(self):
        plan, binding = self._binding()
        after = {
            "processes": [self.protected],
            "ancestry_nodes": [node(self.protected, 1)],
        }
        with self.assertRaisesRegex(IdentityError, "survived"):
            verify_grok_halt_completion(
                plan,
                binding,
                snapshot_after=after,
                process_alive_fn=self._is_alive,
                process_tree_alive_fn=self._tree_is_alive,
            )

        self.alive.remove(self.root_process["kernel_birth_id"])
        self.alive.remove(self.child["kernel_birth_id"])
        self.tree_alive.remove(self.root_process["kernel_birth_id"])
        self.tree_alive.remove(self.child["kernel_birth_id"])
        with self.assertRaisesRegex(IdentityError, "socket survived"):
            verify_grok_halt_completion(
                plan,
                binding,
                snapshot_after=after,
                process_alive_fn=self._is_alive,
                process_tree_alive_fn=self._tree_is_alive,
            )

        self.leader_socket.unlink()
        with self.assertRaisesRegex(IdentityError, "protected population changed"):
            verify_grok_halt_completion(
                plan,
                binding,
                snapshot_after={"processes": [], "ancestry_nodes": []},
                process_alive_fn=self._is_alive,
                process_tree_alive_fn=self._tree_is_alive,
            )


if __name__ == "__main__":
    unittest.main()
