from __future__ import annotations

import copy
import inspect
import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "puppet" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from puppet_lib import codex_launch as codex_launch_module  # noqa: E402
from puppet_lib.adapter_manifest import (  # noqa: E402
    ADAPTER_MANIFEST_SCHEMA_VERSION,
    AdapterManifest,
    direct_execution_bundle,
    execution_file_identity,
)
from puppet_lib.census import adapter_implementation_fingerprint  # noqa: E402
from puppet_lib.codex_launch import build_codex_launch_context  # noqa: E402
from puppet_lib.errors import IdentityError, ValidationError  # noqa: E402
from puppet_lib.handoffs import PROTOCOL_FINGERPRINT  # noqa: E402
from puppet_lib.profiles import (  # noqa: E402
    PROMPT_TRANSPORT,
    SUBMIT_SETTLE_SECONDS,
    session_profiles_for,
    startup_settle_seconds_for,
)
from puppet_lib.probe import PROBE_CAPABILITIES  # noqa: E402


def _manifest_payload(
    *, requested_path: Path, resolved_identity: dict[str, Any]
) -> dict[str, Any]:
    executable = {
        "requested_path": str(requested_path),
        "resolved_path": resolved_identity["path"],
        "device": resolved_identity["device"],
        "inode": resolved_identity["inode"],
        "size": resolved_identity["size"],
        "mtime_ns": resolved_identity["mtime_ns"],
        "sha256": resolved_identity["sha256"],
        "version_sha256": codex_launch_module.EXPECTED_VERSION_SHA256,
        "help_sha256": "c" * 64,
    }
    return {
        "schema_version": ADAPTER_MANIFEST_SCHEMA_VERSION,
        "target": "codex",
        "generated_at": "2026-07-22T03:00:00Z",
        "platform": {"system": "Darwin", "release": "25", "machine": "arm64"},
        "executable": executable,
        "execution": direct_execution_bundle(executable),
        "adapter_fingerprint": adapter_implementation_fingerprint(),
        "protocol_fingerprint": PROTOCOL_FINGERPRINT,
        "yolo_mapping": {
            "complete": False,
            "launch_argv": [
                resolved_identity["path"],
                codex_launch_module.EXPECTED_UNRESTRICTED_FLAG,
            ],
            "permission_declared": True,
            "permission_flags": [codex_launch_module.EXPECTED_UNRESTRICTED_FLAG],
            "prompt_transport": PROMPT_TRANSPORT,
            "prompt_transport_declared": True,
            "sandbox_disable_declared": True,
            "sandbox_flags": [codex_launch_module.EXPECTED_UNRESTRICTED_FLAG],
            "project_isolation_declared": False,
            "project_isolation_flags": [],
            "session_profiles": session_profiles_for("codex"),
            "session_profiles_declared": True,
            "startup_settle_seconds": startup_settle_seconds_for("codex"),
            "submit_settle_seconds": SUBMIT_SETTLE_SECONDS,
            "model_flag": "--model",
        },
        "capabilities": {
            "launch": "declared",
            "send": "declared",
            "status": "declared",
            "wait": "declared",
            "checkpoint": "declared",
            "resume": "declared",
            "halt": "declared",
        },
        "doctor_only": True,
        "qualification": None,
    }


def _candidate(
    pid: int,
    selector: dict[str, Any],
    *,
    command: str = "codex",
    start: str | None = None,
    kernel_birth_id: str | None = None,
) -> dict[str, Any]:
    return {
        "identity_version": 2,
        "pid": pid,
        "start": start or "2026-07-22T00:00:%02dZ" % (pid % 60),
        "kernel_birth_id": kernel_birth_id or "birth-%s" % pid,
        "command": command,
        "executable_path": selector["path"],
        "device": selector["device"],
        "inode": selector["inode"],
    }


def _all_mapping_keys(value: Any) -> list[str]:
    keys = []
    if isinstance(value, dict):
        for key, item in value.items():
            keys.append(key)
            keys.extend(_all_mapping_keys(item))
    elif isinstance(value, list):
        for item in value:
            keys.extend(_all_mapping_keys(item))
    return keys


class CodexLaunchContextTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.lane_root = self.base / "lane-root"
        self.workspace = self.lane_root / "workspace"
        self.codex_home = self.lane_root / "codex-home"
        for value in (self.lane_root, self.workspace, self.codex_home):
            value.mkdir(mode=0o700)
            value.chmod(0o700)

        install_root = self.base / "install"
        requested_root = self.base / "bin"
        install_root.mkdir()
        requested_root.mkdir()
        self.resolved_executable = install_root / "codex-aarch64-apple-darwin"
        self.resolved_executable.write_bytes(b"#!/bin/sh\nexit 0\n")
        self.resolved_executable.chmod(0o755)
        self.requested_executable = requested_root / "codex"
        self.requested_executable.symlink_to(self.resolved_executable)
        self.execution_identity = execution_file_identity(self.resolved_executable)

        patches = (
            mock.patch.object(
                codex_launch_module,
                "EXPECTED_REQUESTED_EXECUTABLE_PATH",
                str(self.requested_executable),
            ),
            mock.patch.object(
                codex_launch_module,
                "EXPECTED_RESOLVED_EXECUTABLE_PATH",
                self.execution_identity["path"],
            ),
            mock.patch.object(
                codex_launch_module,
                "EXPECTED_EXECUTABLE_SHA256",
                self.execution_identity["sha256"],
            ),
        )
        for patcher in patches:
            patcher.start()
            self.addCleanup(patcher.stop)

        self.manifest_path = self.base / "manifest.json"
        self.manifest_raw = _manifest_payload(
            requested_path=self.requested_executable,
            resolved_identity=self.execution_identity,
        )
        self._write_manifest(self.manifest_raw)

    def _write_manifest(self, manifest_raw: dict[str, Any]) -> None:
        self.manifest_path.write_text(json.dumps(manifest_raw) + "\n", encoding="utf-8")

    def _build(self, manifest_raw=None, **kwargs):
        if manifest_raw is not None:
            self._write_manifest(manifest_raw)
        workspace_root = kwargs.pop("workspace_root", self.workspace)
        codex_home = kwargs.pop("codex_home", self.codex_home)
        return build_codex_launch_context(
            manifest_path=self.manifest_path,
            lane_root=self.lane_root,
            workspace_root=workspace_root,
            codex_home=codex_home,
            **kwargs,
        )

    def test_build_context_binds_requested_and_resolved_identity(self):
        manifest = AdapterManifest.from_dict(self.manifest_raw)
        selectors = manifest.process_execution_selectors()
        called = {}

        def selector(target, observed):
            called["target"] = target
            called["selectors"] = observed
            return []

        context = self._build(candidate_fn=selector)
        self.assertEqual(context.target, "codex")
        self.assertEqual(context.session_profile, "regular")
        self.assertEqual(
            context.version_text, codex_launch_module.EXPECTED_VERSION_TEXT
        )
        self.assertEqual(
            context.manifest_executable_sha256,
            self.execution_identity["sha256"],
        )
        self.assertEqual(
            context.manifest_version_sha256,
            codex_launch_module.EXPECTED_VERSION_SHA256,
        )
        self.assertEqual(
            context.requested_executable_path, str(self.requested_executable)
        )
        self.assertEqual(
            context.resolved_executable_path, self.execution_identity["path"]
        )
        self.assertEqual(
            context.argv,
            [
                self.execution_identity["path"],
                "--dangerously-bypass-approvals-and-sandbox",
            ],
        )
        self.assertEqual(context.model_selection, "current_default")
        self.assertEqual(context.effort_selection, "current_default")
        self.assertEqual(called["target"], "codex")
        self.assertEqual(called["selectors"], selectors)

    def test_public_context_is_value_free_and_never_authorizes_launch(self):
        context = self._build(candidate_fn=lambda _target, _selectors: [])
        public = context.to_public_dict()
        self.assertFalse(context.launch_authorized)
        self.assertFalse(public["launch_authorized"])
        self.assertEqual(public["auth_route"], "process_local_access_token_broker")
        self.assertRegex(public["auth_route"], r"^[a-z0-9_]+$")
        self.assertEqual(public["model_selection"], "current_default")
        self.assertEqual(public["effort_selection"], "current_default")
        self.assertNotIn("environment", public)
        self.assertFalse(hasattr(context, "environment"))
        self.assertFalse(hasattr(context, "_environment_items"))
        for key in _all_mapping_keys(public):
            if key == "auth_route":
                continue
            self.assertIsNone(
                re.search(r"token|secret|credential|password|auth_value", key, re.I)
            )

    def test_alternate_model_or_effort_parameters_are_impossible(self):
        parameters = inspect.signature(build_codex_launch_context).parameters
        self.assertNotIn("requested_model", parameters)
        self.assertNotIn("requested_effort", parameters)
        for name, value in (
            ("requested_model", "alternate-model"),
            ("requested_effort", "high"),
        ):
            with self.subTest(name=name):
                with self.assertRaisesRegex(TypeError, "unexpected keyword argument"):
                    self._build(**{name: value})

    def test_declared_model_flag_is_capability_not_selection(self):
        context = self._build(candidate_fn=lambda _target, _selectors: [])
        self.assertEqual(self.manifest_raw["yolo_mapping"]["model_flag"], "--model")
        self.assertNotIn("--model", context.argv)
        self.assertEqual(context.model_selection, "current_default")
        self.assertNotIn("model selector", " ".join(context.blockers))

    def test_actual_model_effort_profile_and_config_argv_are_rejected(self):
        overrides = (
            ["--model", "alternate-model"],
            ["--model=alternate-model"],
            ["--effort", "high"],
            ["--profile", "alternate-profile"],
            ["-c", "model_reasoning_effort=high"],
            ["--config", "model=alternate-model"],
        )
        for override in overrides:
            with self.subTest(override=override):
                raw = copy.deepcopy(self.manifest_raw)
                raw["yolo_mapping"]["launch_argv"].extend(override)
                with self.assertRaisesRegex(
                    ValidationError,
                    "exact Codex regular unrestricted mapping",
                ):
                    self._build(raw, candidate_fn=lambda _target, _selectors: [])

    def test_permission_and_sandbox_mapping_are_exact(self):
        mutations = (
            ("permission_declared", False),
            ("permission_flags", []),
            ("sandbox_disable_declared", False),
            ("sandbox_flags", []),
            ("project_isolation_flags", ["-C"]),
            ("model_flag", "--another-model-flag"),
        )
        for name, value in mutations:
            with self.subTest(name=name):
                raw = copy.deepcopy(self.manifest_raw)
                raw["yolo_mapping"][name] = value
                with self.assertRaises(ValidationError):
                    self._build(raw, candidate_fn=lambda _target, _selectors: [])

    def test_source_only_blockers_are_unconditional_for_complete_mapping(self):
        raw = copy.deepcopy(self.manifest_raw)
        raw["yolo_mapping"]["complete"] = True
        raw["yolo_mapping"]["project_isolation_declared"] = True
        context = self._build(raw, candidate_fn=lambda _target, _selectors: [])
        self.assertEqual(
            set(context.blockers), set(codex_launch_module.SOURCE_ONLY_BLOCKERS)
        )
        self.assertNotIn(
            codex_launch_module.MAPPING_INCOMPLETE_BLOCKER, context.blockers
        )
        self.assertFalse(context.launch_authorized)

    def test_incomplete_mapping_blocker_is_preserved(self):
        context = self._build(candidate_fn=lambda _target, _selectors: [])
        self.assertIn(codex_launch_module.MAPPING_INCOMPLETE_BLOCKER, context.blockers)
        self.assertTrue(
            set(codex_launch_module.SOURCE_ONLY_BLOCKERS) <= set(context.blockers)
        )

    def test_zero_ambient_environment_is_selected(self):
        with mock.patch.dict(
            os.environ,
            {
                "HOME": "/ambient/home-must-not-flow",
                "PATH": "/ambient/path-must-not-flow",
                "TERM": "ambient-term-must-not-flow",
            },
            clear=False,
        ):
            context = self._build(candidate_fn=lambda _target, _selectors: [])
        public = context.to_public_dict()
        self.assertEqual(public["launch_identity"]["env_names"], ["CODEX_HOME"])
        self.assertNotIn("environment", public["launch_identity"])

    def test_multiple_processes_may_share_the_declared_executable(self):
        def candidates(_target, selectors):
            return [_candidate(202, selectors[0]), _candidate(101, selectors[0])]

        context = self._build(candidate_fn=candidates)
        self.assertEqual(context.candidate_process_count, 2)
        self.assertEqual(context.candidate_process_pids, (101, 202))
        self.assertIn("existing target candidate processes detected", context.blockers)

    def test_candidate_fingerprint_binds_every_complete_identity_field(self):
        first = self._build(
            candidate_fn=lambda _target, selectors: [
                _candidate(101, selectors[0], command="codex first")
            ]
        )
        second = self._build(
            candidate_fn=lambda _target, selectors: [
                _candidate(101, selectors[0], command="codex second")
            ]
        )
        self.assertNotEqual(
            first.candidate_process_fingerprint,
            second.candidate_process_fingerprint,
        )

    def test_empty_candidate_population_is_not_a_candidate_blocker(self):
        context = self._build(candidate_fn=lambda _target, _selectors: [])
        self.assertEqual(context.candidate_process_count, 0)
        self.assertNotIn(
            "existing target candidate processes detected", context.blockers
        )

    def test_malformed_candidate_processes_are_rejected(self):
        with self.assertRaisesRegex(
            ValidationError, "candidate process lookup is malformed"
        ):
            self._build(
                candidate_fn=lambda _target, _selectors: [{"bad": "shape", "pid": 123}]
            )

    def test_candidate_selector_mismatch_is_rejected(self):
        def mismatched(_target, selectors):
            sample = _candidate(101, selectors[0])
            sample["device"] += 1
            return [sample]

        with self.assertRaisesRegex(
            ValidationError, "candidate process lookup is malformed"
        ):
            self._build(candidate_fn=mismatched)

    def test_duplicate_candidate_pid_is_rejected(self):
        def duplicated(_target, selectors):
            return [
                _candidate(101, selectors[0], kernel_birth_id="birth-a"),
                _candidate(101, selectors[0], kernel_birth_id="birth-b"),
            ]

        with self.assertRaisesRegex(
            ValidationError, "candidate process lookup is malformed"
        ):
            self._build(candidate_fn=duplicated)

    def test_duplicate_candidate_birth_identity_is_rejected(self):
        def duplicated(_target, selectors):
            return [
                _candidate(
                    101,
                    selectors[0],
                    start="2026-07-22T00:00:00Z",
                    kernel_birth_id="same-birth",
                ),
                _candidate(
                    202,
                    selectors[0],
                    start="2026-07-22T00:00:00Z",
                    kernel_birth_id="same-birth",
                ),
            ]

        with self.assertRaisesRegex(
            ValidationError, "candidate process lookup is malformed"
        ):
            self._build(candidate_fn=duplicated)

    def test_current_resolved_execution_drift_is_rejected(self):
        self.resolved_executable.write_bytes(b"#!/bin/sh\nexit 9\n")
        with self.assertRaises(IdentityError):
            self._build(candidate_fn=lambda _target, _selectors: [])

    def test_self_consistent_forged_manifest_execution_is_rejected(self):
        self.resolved_executable.write_bytes(b"#!/bin/sh\nexit 8\n")
        forged_identity = execution_file_identity(self.resolved_executable)
        raw = _manifest_payload(
            requested_path=self.requested_executable,
            resolved_identity=forged_identity,
        )
        with self.assertRaisesRegex(ValidationError, "executable hash is unexpected"):
            self._build(raw, candidate_fn=lambda _target, _selectors: [])

    def test_requested_symlink_target_drift_is_rejected(self):
        replacement = self.base / "replacement-codex"
        replacement.write_bytes(b"#!/bin/sh\nexit 7\n")
        replacement.chmod(0o755)
        self.requested_executable.unlink()
        self.requested_executable.symlink_to(replacement)
        with self.assertRaisesRegex(IdentityError, "symlink target changed"):
            self._build(candidate_fn=lambda _target, _selectors: [])

    def test_forged_requested_or_resolved_manifest_path_is_rejected(self):
        mutations = (
            ("requested_path", str(self.base / "forged-request")),
            ("resolved_path", str(self.base / "forged-resolution")),
        )
        for name, value in mutations:
            with self.subTest(name=name):
                raw = copy.deepcopy(self.manifest_raw)
                raw["executable"][name] = value
                if name == "resolved_path":
                    raw["execution"] = direct_execution_bundle(raw["executable"])
                    raw["yolo_mapping"]["launch_argv"][0] = value
                with self.assertRaisesRegex(
                    ValidationError, "executable path is unexpected"
                ):
                    self._build(raw, candidate_fn=lambda _target, _selectors: [])

    def test_non_codex_target_is_rejected(self):
        raw = copy.deepcopy(self.manifest_raw)
        raw["target"] = "agy"
        raw["yolo_mapping"]["session_profiles"] = session_profiles_for("agy")
        raw["yolo_mapping"]["project_isolation_flags"] = ["--new-project"]
        raw["yolo_mapping"]["launch_argv"] = [
            self.execution_identity["path"],
            codex_launch_module.EXPECTED_UNRESTRICTED_FLAG,
            "--new-project",
        ]
        raw["yolo_mapping"]["startup_settle_seconds"] = startup_settle_seconds_for(
            "agy"
        )
        with self.assertRaisesRegex(
            ValidationError, "launch context requires target codex"
        ):
            self._build(raw)

    def test_doctor_only_manifest_is_required(self):
        raw = copy.deepcopy(self.manifest_raw)
        receipt = self.base / "receipt.json"
        receipt.write_text("{}", encoding="utf-8")
        raw["doctor_only"] = False
        raw["qualification"] = {
            "receipt_path": str(receipt),
            "receipt_sha256": "d" * 64,
            "session_profile": "regular",
        }
        raw["capabilities"] = {
            name: "controller_verified" for name in raw["capabilities"]
        }
        raw["capabilities"]["resume"] = "unsupported"
        for capability in PROBE_CAPABILITIES:
            raw["capabilities"][capability] = "controller_verified"
        with self.assertRaisesRegex(
            ValidationError,
            "source-only Codex launch requires doctor-only manifest",
        ):
            self._build(raw)

    def test_private_root_bounds_are_enforced(self):
        with self.assertRaisesRegex(
            ValidationError, "must be a distinct child of the lane root"
        ):
            self._build(
                workspace_root=self.lane_root,
                candidate_fn=lambda _target, _selectors: [],
            )

    def test_version_hash_is_revalidated(self):
        raw = copy.deepcopy(self.manifest_raw)
        raw["executable"]["version_sha256"] = "a" * 64
        with self.assertRaisesRegex(
            ValidationError, "manifest executable version hash is unexpected"
        ):
            self._build(raw, candidate_fn=lambda _target, _selectors: [])

    def test_adapter_and_protocol_fingerprints_are_revalidated(self):
        for name in ("adapter_fingerprint", "protocol_fingerprint"):
            with self.subTest(name=name):
                raw = copy.deepcopy(self.manifest_raw)
                raw[name] = "a" * 64
                with self.assertRaisesRegex(
                    ValidationError, "fingerprint is unexpected"
                ):
                    self._build(raw, candidate_fn=lambda _target, _selectors: [])
