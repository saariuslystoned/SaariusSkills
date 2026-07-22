from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "puppet" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from puppet_lib.adapter_manifest import (  # noqa: E402
    ADAPTER_MANIFEST_SCHEMA_VERSION,
    AdapterManifest,
    direct_execution_bundle,
)
from puppet_lib.errors import ValidationError  # noqa: E402
from puppet_lib.codex_launch import (  # noqa: E402
    EXPECTED_EXECUTABLE_PATH,
    EXPECTED_EXECUTABLE_SHA256,
    EXPECTED_VERSION_SHA256,
    EXPECTED_VERSION_TEXT,
    build_codex_launch_context,
)
from puppet_lib.census import adapter_implementation_fingerprint
from puppet_lib.handoffs import PROTOCOL_FINGERPRINT
from puppet_lib.profiles import (  # noqa: E402
    PROMPT_TRANSPORT,
    SUBMIT_SETTLE_SECONDS,
    session_profiles_for,
    startup_settle_seconds_for,
)
from puppet_lib.probe import PROBE_CAPABILITIES  # noqa: E402


def _manifest_payload():
    executable = Path(EXPECTED_EXECUTABLE_PATH)
    identity = {
        "requested_path": EXPECTED_EXECUTABLE_PATH,
        "resolved_path": EXPECTED_EXECUTABLE_PATH,
        "device": executable.stat().st_dev if executable.exists() else 12345,
        "inode": executable.stat().st_ino if executable.exists() else 12345,
        "size": executable.stat().st_size if executable.exists() else 1,
        "mtime_ns": executable.stat().st_mtime_ns if executable.exists() else 1,
        "sha256": EXPECTED_EXECUTABLE_SHA256,
        "version_sha256": EXPECTED_VERSION_SHA256,
        "help_sha256": "c" * 64,
    }
    return {
        "schema_version": ADAPTER_MANIFEST_SCHEMA_VERSION,
        "target": "codex",
        "generated_at": "2026-07-22T03:00:00Z",
        "platform": {"system": "Darwin", "release": "25", "machine": "arm64"},
        "executable": identity,
        "execution": direct_execution_bundle(identity),
        "adapter_fingerprint": adapter_implementation_fingerprint(),
        "protocol_fingerprint": PROTOCOL_FINGERPRINT,
        "yolo_mapping": {
            "complete": True,
            "launch_argv": [EXPECTED_EXECUTABLE_PATH],
            "permission_declared": True,
            "permission_flags": [],
            "prompt_transport": PROMPT_TRANSPORT,
            "prompt_transport_declared": True,
            "sandbox_disable_declared": True,
            "sandbox_flags": [],
            "project_isolation_declared": True,
            "project_isolation_flags": [],
            "session_profiles": session_profiles_for("codex"),
            "session_profiles_declared": True,
            "startup_settle_seconds": startup_settle_seconds_for("codex"),
            "submit_settle_seconds": SUBMIT_SETTLE_SECONDS,
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


def _candidate(pid: int):
    return {
        "identity_version": 2,
        "pid": pid,
        "start": "2026-07-22T00:00:00Z",
        "kernel_birth_id": "b%s" % pid,
        "command": "codex",
        "executable_path": EXPECTED_EXECUTABLE_PATH,
        "device": 12345,
        "inode": 5000 + pid,
    }


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
        self.manifest_path = self.base / "manifest.json"
        self.manifest_raw = _manifest_payload()
        self.manifest_path.write_text(json.dumps(self.manifest_raw) + "\n", encoding="utf-8")

    def _build(self, manifest_raw=None, **kwargs):
        if manifest_raw is not None:
            self.manifest_path.write_text(json.dumps(manifest_raw) + "\n", encoding="utf-8")
        workspace_root = kwargs.pop("workspace_root", self.workspace)
        codex_home = kwargs.pop("codex_home", self.codex_home)
        return build_codex_launch_context(
            manifest_path=self.manifest_path,
            lane_root=self.lane_root,
            workspace_root=workspace_root,
            codex_home=codex_home,
            **kwargs,
        )

    def test_build_context_binds_expected_identity(self):
        manifest = AdapterManifest.from_dict(self.manifest_raw)
        selectors = manifest.process_execution_selectors()
        called = {}

        def selector(target, observed):
            called["target"] = target
            called["selectors"] = observed
            return [_candidate(101), _candidate(202)]

        context = self._build(candidate_fn=selector)
        self.assertEqual(context.target, "codex")
        self.assertEqual(context.session_profile, "regular")
        self.assertEqual(context.version_text, EXPECTED_VERSION_TEXT)
        self.assertEqual(context.manifest_executable_sha256, EXPECTED_EXECUTABLE_SHA256)
        self.assertEqual(context.manifest_version_sha256, EXPECTED_VERSION_SHA256)
        self.assertEqual(context.executable_path, EXPECTED_EXECUTABLE_PATH)
        self.assertEqual(context.candidate_process_count, 2)
        self.assertEqual(context.candidate_process_pids, (101, 202))
        self.assertEqual(called["target"], "codex")
        self.assertEqual(called["selectors"], selectors)
        public = context.to_public_dict()
        self.assertEqual(public["process_local_CODEX_ACCESS_TOKEN"]["accepted"], False)
        self.assertEqual(public["process_local_CODEX_ACCESS_TOKEN"]["persisted"], False)
        self.assertEqual(public["auth_value_accepted"], False)
        self.assertEqual(public["auth_value_persisted"], False)
        self.assertEqual(context.environment["CODEX_HOME"], str(self.codex_home.resolve()))
        self.assertEqual(
            set(public["launch_identity"]["env_names"]),
            {"CODEX_HOME"},
        )

    def test_model_or_effort_selector_argv_is_blocked(self):
        raw = copy.deepcopy(self.manifest_raw)
        raw["yolo_mapping"]["model_flag"] = "--model"
        raw["yolo_mapping"]["effort_flag"] = "--effort"
        raw["yolo_mapping"]["launch_argv"].append("--model")
        context = self._build(raw, candidate_fn=lambda *args, **kwargs: [_candidate(101)])
        blockers = set(context.blockers)
        self.assertIn("native plane model selector remains unresolved", blockers)
        self.assertIn("native plane effort selector remains unresolved", blockers)
        self.assertIn("manifest launch argv includes model selector", blockers)

    def test_auth_token_blocker_and_no_leak(self):
        context = self._build(
            candidate_fn=lambda *args, **kwargs: [_candidate(101)],
            process_local_CODEX_ACCESS_TOKEN="s3cr3t-token",
        )
        payload = json.dumps(context.to_public_dict())
        self.assertFalse(context.auth_value_accepted)
        self.assertFalse(context.auth_value_persisted)
        self.assertNotIn("s3cr3t-token", payload)
        self.assertTrue(
            any(
                blocker.endswith("broker route for child launch")
                for blocker in context.blockers
            )
        )

    def test_no_candidate_processes_is_blocker(self):
        context = self._build(candidate_fn=lambda *args, **kwargs: [])
        self.assertEqual(context.candidate_process_count, 0)
        self.assertIn("no existing target candidate processes detected", context.blockers)

    def test_malformed_candidate_processes_are_rejected(self):
        def malformed(_target, _selectors):
            return [{"bad": "shape", "pid": 123}]

        with self.assertRaisesRegex(ValidationError, "candidate process lookup is malformed"):
            self._build(candidate_fn=malformed)

    def test_candidate_processes_reject_non_codex_target(self):
        raw = copy.deepcopy(self.manifest_raw)
        raw["target"] = "agy"
        raw["yolo_mapping"]["session_profiles"] = session_profiles_for("agy")
        raw["yolo_mapping"]["project_isolation_flags"] = ["--new-project"]
        raw["yolo_mapping"]["launch_argv"] = [EXPECTED_EXECUTABLE_PATH, "--new-project"]
        raw["yolo_mapping"]["startup_settle_seconds"] = startup_settle_seconds_for("agy")
        with self.assertRaisesRegex(ValidationError, "launch context requires target codex"):
            self._build(raw)

    def test_doctor_only_required(self):
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

    def test_root_bounds_enforced(self):
        with self.assertRaisesRegex(ValidationError, "must be a distinct child of the lane root"):
            self._build(
                workspace_root=self.lane_root,
                candidate_fn=lambda *args, **kwargs: [_candidate(101)],
            )

    def test_executable_and_version_hashes_are_validated(self):
        raw = copy.deepcopy(self.manifest_raw)
        raw["executable"]["version_sha256"] = "a" * 64
        with self.assertRaisesRegex(
            ValidationError, "manifest executable version hash is unexpected"
        ):
            self._build(raw, candidate_fn=lambda *args, **kwargs: [_candidate(101)])
