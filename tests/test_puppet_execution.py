from __future__ import annotations

import copy
import os
import platform
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "puppet" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from puppet_lib.adapter_manifest import (  # noqa: E402
    ADAPTER_MANIFEST_SCHEMA_VERSION,
    AdapterManifest,
    build_execution_bundle,
    direct_execution_bundle,
    execution_file_identity,
    launcher_execution_identity,
)
from puppet_lib.errors import IdentityError, ValidationError  # noqa: E402
from puppet_lib.handoffs import PROTOCOL_FINGERPRINT  # noqa: E402
from puppet_lib.profiles import (  # noqa: E402
    PROMPT_TRANSPORT,
    SUBMIT_SETTLE_SECONDS,
    session_profiles_for,
    startup_settle_seconds_for,
)
from puppet_lib.registry import (  # noqa: E402
    ExecTransitionSamplingError,
    bind_runtime_process,
)


def launcher_manifest(path: Path) -> dict:
    identity = execution_file_identity(path)
    return {
        "requested_path": identity["path"],
        "resolved_path": identity["path"],
        "device": identity["device"],
        "inode": identity["inode"],
        "size": identity["size"],
        "mtime_ns": identity["mtime_ns"],
        "sha256": identity["sha256"],
        "version_sha256": "b" * 64,
        "help_sha256": "c" * 64,
    }


def manifest_raw(
    launcher: Path,
    *,
    runtime: Path | None = None,
    transients: list[Path] | None = None,
    support: list[Path] | None = None,
    timeout: float = 1.0,
) -> dict:
    executable = launcher_manifest(launcher)
    if runtime is None:
        execution = direct_execution_bundle(executable, settle_timeout_seconds=timeout)
    else:
        execution = build_execution_bundle(
            launcher={
                "path": executable["resolved_path"],
                "device": executable["device"],
                "inode": executable["inode"],
                "size": executable["size"],
                "mtime_ns": executable["mtime_ns"],
                "sha256": executable["sha256"],
            },
            transition="same_pid_exec",
            runtime_executable=execution_file_identity(runtime),
            transient_executables=sorted(
                [execution_file_identity(item) for item in (transients or [])],
                key=lambda item: item["path"],
            ),
            support_files=sorted(
                [execution_file_identity(item) for item in (support or [])],
                key=lambda item: item["path"],
            ),
            settle_timeout_seconds=timeout,
        )
    target = "codex"
    mapping = {
        "complete": True,
        "launch_argv": [executable["resolved_path"]],
        "permission_declared": True,
        "permission_flags": [],
        "prompt_transport": PROMPT_TRANSPORT,
        "prompt_transport_declared": True,
        "sandbox_disable_declared": True,
        "sandbox_flags": [],
        "project_isolation_declared": True,
        "project_isolation_flags": [],
        "session_profiles": session_profiles_for(target),
        "session_profiles_declared": True,
        "startup_settle_seconds": startup_settle_seconds_for(target),
        "submit_settle_seconds": SUBMIT_SETTLE_SECONDS,
    }
    return {
        "schema_version": ADAPTER_MANIFEST_SCHEMA_VERSION,
        "target": target,
        "generated_at": "2026-07-22T13:00:00Z",
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
        },
        "executable": executable,
        "execution": execution,
        "adapter_fingerprint": "d" * 64,
        "protocol_fingerprint": PROTOCOL_FINGERPRINT,
        "yolo_mapping": mapping,
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


def process(pid: int, path: Path, birth: str = "birth-1") -> dict:
    identity = execution_file_identity(path)
    return {
        "identity_version": 2,
        "pid": pid,
        "start": "Wed Jul 22 13:00:00 2026",
        "kernel_birth_id": birth,
        "command": path.name,
        "executable_path": identity["path"],
        "device": identity["device"],
        "inode": identity["inode"],
    }


class Clock:
    def __init__(self):
        self.value = 0.0

    def monotonic(self):
        return self.value

    def sleep(self, interval):
        self.value += max(float(interval), 0.001)


class ExecutionKernelTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.launcher = self.root / "launcher"
        self.runtime = self.root / "runtime"
        self.transient = self.root / "transient"
        self.support = self.root / "index.js"
        for path, content in (
            (self.launcher, b"launcher"),
            (self.runtime, b"runtime"),
            (self.transient, b"transient"),
            (self.support, b"support"),
        ):
            path.write_bytes(content)

    def same_exec_manifest(self, *, timeout=1.0):
        return AdapterManifest.from_dict(
            manifest_raw(
                self.launcher,
                runtime=self.runtime,
                transients=[self.transient],
                support=[self.support],
                timeout=timeout,
            )
        )

    def test_manifest_fingerprint_and_all_execution_files_are_strict(self):
        manifest = self.same_exec_manifest()
        self.assertEqual(len(manifest.execution_fingerprint), 64)
        launcher_identity = execution_file_identity(self.launcher)
        runtime_identity = execution_file_identity(self.runtime)
        transient_identity = execution_file_identity(self.transient)
        self.assertEqual(
            manifest.process_execution_selectors(),
            [
                {
                    "path": launcher_identity["path"],
                    "device": launcher_identity["device"],
                    "inode": launcher_identity["inode"],
                },
                {
                    "path": runtime_identity["path"],
                    "device": runtime_identity["device"],
                    "inode": runtime_identity["inode"],
                },
                {
                    "path": transient_identity["path"],
                    "device": transient_identity["device"],
                    "inode": transient_identity["inode"],
                },
            ],
        )
        drifted = copy.deepcopy(manifest.raw)
        drifted["execution"]["execution_fingerprint"] = "0" * 64
        with self.assertRaisesRegex(ValidationError, "execution fingerprint"):
            AdapterManifest.from_dict(drifted)
        self.support.write_bytes(b"changed support")
        with self.assertRaisesRegex(IdentityError, "support"):
            manifest.verify_execution_files()

    def test_direct_with_support_requires_direct_runtime_and_support_provenance(self):
        raw = manifest_raw(self.launcher)
        raw["execution"] = build_execution_bundle(
            launcher=launcher_execution_identity(raw["executable"]),
            transition="direct_with_support",
            runtime_executable=execution_file_identity(self.launcher),
            transient_executables=[],
            support_files=[execution_file_identity(self.support)],
            settle_timeout_seconds=1.0,
        )
        manifest = AdapterManifest.from_dict(raw)
        self.assertEqual(
            manifest.raw["execution"]["transition"], "direct_with_support"
        )

        for label, transients, support in (
            ("transient", [execution_file_identity(self.transient)], [
                execution_file_identity(self.support)
            ]),
            ("support", [], []),
        ):
            with self.subTest(label=label):
                changed = copy.deepcopy(raw)
                changed["execution"] = build_execution_bundle(
                    launcher=launcher_execution_identity(changed["executable"]),
                    transition="direct_with_support",
                    runtime_executable=execution_file_identity(self.launcher),
                    transient_executables=transients,
                    support_files=support,
                    settle_timeout_seconds=1.0,
                )
                with self.assertRaisesRegex(
                    ValidationError, "direct-with-support"
                ):
                    AdapterManifest.from_dict(changed)

        changed = copy.deepcopy(raw)
        changed["execution"] = build_execution_bundle(
            launcher=launcher_execution_identity(changed["executable"]),
            transition="direct_with_support",
            runtime_executable=execution_file_identity(self.runtime),
            transient_executables=[],
            support_files=[execution_file_identity(self.support)],
            settle_timeout_seconds=1.0,
        )
        with self.assertRaisesRegex(ValidationError, "direct-with-support"):
            AdapterManifest.from_dict(changed)

    def test_execution_file_identity_rejects_path_replacement_after_open(self):
        original = self.root / "replaceable"
        replacement = self.root / "replacement"
        original.write_bytes(b"original")
        replacement.write_bytes(b"replacement")
        real_open = os.open

        def open_then_replace(path, flags):
            descriptor = real_open(path, flags)
            os.replace(replacement, original)
            return descriptor

        with (
            patch("puppet_lib.adapter_manifest.os.open", side_effect=open_then_replace),
            self.assertRaisesRegex(ValidationError, "path changed"),
        ):
            execution_file_identity(original)

    def test_execution_file_roles_reject_hard_link_aliases(self):
        hard_link = self.root / "transient-support-alias"
        os.link(self.transient, hard_link)
        raw = copy.deepcopy(self.same_exec_manifest().raw)
        execution = raw["execution"]
        raw["execution"] = build_execution_bundle(
            launcher=launcher_execution_identity(raw["executable"]),
            transition=execution["transition"],
            runtime_executable=execution["runtime_executable"],
            transient_executables=execution["transient_executables"],
            support_files=[execution_file_identity(hard_link)],
            settle_timeout_seconds=execution["settle_timeout_seconds"],
        )
        with self.assertRaisesRegex(ValidationError, "roles overlap"):
            AdapterManifest.from_dict(raw)

    def test_direct_runtime_binds_only_after_two_stable_samples(self):
        manifest = AdapterManifest.from_dict(manifest_raw(self.launcher))
        samples = [process(4242, self.launcher), process(4242, self.launcher)]
        owners = []
        bound = bind_runtime_process(
            4242,
            manifest,
            lambda pid: owners.append(pid),
            process_sample_fn=lambda pid: samples.pop(0),
            sleep_fn=lambda interval: None,
        )
        self.assertEqual(bound["executable_path"], str(self.launcher.resolve()))
        self.assertFalse(samples)
        self.assertGreaterEqual(len(owners), 5)

    def test_same_pid_launcher_transition_and_exec_sampling_are_accepted(self):
        manifest = self.same_exec_manifest()
        transient = process(4242, self.transient)
        final = process(4242, self.runtime)
        samples = [transient, final, final]
        bound = bind_runtime_process(
            4242,
            manifest,
            lambda pid: None,
            process_sample_fn=lambda pid: samples.pop(0),
            sleep_fn=lambda interval: None,
        )
        self.assertEqual(bound, final)

        samples = [
            ExecTransitionSamplingError(
                "crossed exec",
                pid=4242,
                kernel_birth_id="birth-1",
                executable_before={
                    "executable_path": transient["executable_path"],
                    "device": transient["device"],
                    "inode": transient["inode"],
                },
                executable_after={
                    "executable_path": final["executable_path"],
                    "device": final["device"],
                    "inode": final["inode"],
                },
            ),
            final,
            final,
        ]

        def sample(_pid):
            value = samples.pop(0)
            if isinstance(value, BaseException):
                raise value
            return value

        self.assertEqual(
            bind_runtime_process(
                4242,
                manifest,
                lambda pid: None,
                process_sample_fn=sample,
                sleep_fn=lambda interval: None,
            ),
            final,
        )

    def test_exec_sampling_rejects_direct_and_undeclared_crossings(self):
        direct = AdapterManifest.from_dict(manifest_raw(self.launcher))
        launcher = process(4242, self.launcher)

        def transition(before, after):
            return ExecTransitionSamplingError(
                "crossed exec",
                pid=4242,
                kernel_birth_id="birth-1",
                executable_before={
                    "executable_path": before["executable_path"],
                    "device": before["device"],
                    "inode": before["inode"],
                },
                executable_after={
                    "executable_path": after["executable_path"],
                    "device": after["device"],
                    "inode": after["inode"],
                },
            )

        with self.assertRaisesRegex(IdentityError, "direct runtime"):
            direct_transition = transition(launcher, launcher)

            def sample_direct(_pid):
                raise direct_transition

            bind_runtime_process(
                4242,
                direct,
                lambda pid: None,
                process_sample_fn=sample_direct,
                sleep_fn=lambda interval: None,
            )
        same_exec = self.same_exec_manifest()
        transient = process(4242, self.transient)
        undeclared = process(4242, self.support)
        with self.assertRaisesRegex(IdentityError, "undeclared executable"):
            undeclared_transition = transition(transient, undeclared)

            def sample_undeclared(_pid):
                raise undeclared_transition

            bind_runtime_process(
                4242,
                same_exec,
                lambda pid: None,
                process_sample_fn=sample_undeclared,
                sleep_fn=lambda interval: None,
            )

    def test_final_runtime_on_first_sample_still_requires_stability(self):
        manifest = self.same_exec_manifest()
        first = process(4242, self.runtime)
        changed = dict(first, command="changed")
        samples = [first, changed]
        with self.assertRaisesRegex(IdentityError, "not stable"):
            bind_runtime_process(
                4242,
                manifest,
                lambda pid: None,
                process_sample_fn=lambda pid: samples.pop(0),
                sleep_fn=lambda interval: None,
            )

    def test_birth_drift_and_unknown_executable_fail_closed(self):
        manifest = self.same_exec_manifest()
        samples = [
            process(4242, self.transient, "birth-1"),
            process(4242, self.runtime, "birth-2"),
        ]
        with self.assertRaisesRegex(IdentityError, "birth identity changed"):
            bind_runtime_process(
                4242,
                manifest,
                lambda pid: None,
                process_sample_fn=lambda pid: samples.pop(0),
                sleep_fn=lambda interval: None,
            )
        with self.assertRaisesRegex(IdentityError, "not declared"):
            bind_runtime_process(
                4242,
                manifest,
                lambda pid: None,
                process_sample_fn=lambda pid: process(4242, self.support),
                sleep_fn=lambda interval: None,
            )

    def test_timeout_and_fork_without_exec_never_bind(self):
        manifest = self.same_exec_manifest(timeout=0.2)
        invalid_timing = manifest_raw(self.launcher)
        invalid_timing["execution"]["settle_timeout_seconds"] = float("nan")
        with self.assertRaisesRegex(ValidationError, "settle timeout"):
            AdapterManifest.from_dict(invalid_timing)
        with self.assertRaisesRegex(ValidationError, "timing"):
            bind_runtime_process(
                4242,
                manifest,
                lambda pid: None,
                timeout=float("nan"),
                process_sample_fn=lambda pid: process(4242, self.transient),
            )
        clock = Clock()
        with self.assertRaisesRegex(IdentityError, "timeout"):
            bind_runtime_process(
                4242,
                manifest,
                lambda pid: None,
                timeout=0.2,
                process_sample_fn=lambda pid: process(4242, self.transient),
                monotonic_fn=clock.monotonic,
                sleep_fn=clock.sleep,
                sample_interval=0.1,
            )
        with self.assertRaisesRegex(IdentityError, "forked child"):
            bind_runtime_process(
                4242,
                manifest,
                lambda pid: None,
                process_sample_fn=lambda pid: process(4243, self.runtime),
                sleep_fn=lambda interval: None,
            )

    def test_pane_owner_is_rechecked_on_every_sample(self):
        manifest = self.same_exec_manifest()
        final = process(4242, self.runtime)
        calls = []

        def owner(pid):
            calls.append(pid)
            return len(calls) < 3

        with self.assertRaisesRegex(IdentityError, "pane"):
            bind_runtime_process(
                4242,
                manifest,
                owner,
                process_sample_fn=lambda pid: final,
                sleep_fn=lambda interval: None,
            )


if __name__ == "__main__":
    unittest.main()
