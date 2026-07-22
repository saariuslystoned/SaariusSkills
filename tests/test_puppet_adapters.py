from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "puppet" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from puppet_lib.adapter_manifest import AdapterManifest  # noqa: E402
from puppet_lib.adapters import adapter_for  # noqa: E402
from puppet_lib.errors import UnsupportedError, ValidationError  # noqa: E402
from puppet_lib.provenance import admission_fingerprint, validate_admission_rows  # noqa: E402


def manifest_raw():
    return {
        "schema_version": 1,
        "target": "agy",
        "generated_at": "2026-07-22T02:00:00Z",
        "platform": {"system": "Darwin", "release": "25", "machine": "arm64"},
        "executable": {
            "requested_path": "/bin/echo",
            "resolved_path": "/bin/echo",
            "sha256": "a" * 64,
            "version_sha256": "b" * 64,
            "help_sha256": "c" * 64,
            "device": 1,
            "inode": 2,
            "size": 3,
            "mtime_ns": 4,
        },
        "adapter_fingerprint": "d" * 64,
        "protocol_fingerprint": "e" * 64,
        "yolo_mapping": {
            "complete": True,
            "launch_argv": ["/bin/echo", "--safe-test-flag"],
            "permission_declared": True,
            "permission_flags": ["--safe-test-flag"],
            "prompt_transport": "tmux_stdin_buffer",
            "prompt_transport_declared": True,
            "sandbox_disable_declared": True,
            "sandbox_flags": ["--safe-test-flag"],
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


class AdapterTests(unittest.TestCase):
    def test_agy_prefix_is_exactly_once(self):
        adapter = adapter_for("agy")
        self.assertEqual(adapter.envelope("Do the task"), "/teamwork-preview Do the task")
        for value in ("/teamwork-preview duplicate", "/btw side", "/side side", ""):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                adapter.envelope(value)

    def test_doctor_only_manifest_cannot_launch(self):
        manifest = AdapterManifest.from_dict(manifest_raw())
        with self.assertRaises(UnsupportedError):
            adapter_for("agy").build_launch_argv(manifest)

    def test_verified_manifest_builds_argv_without_prompt(self):
        raw = manifest_raw()
        raw["doctor_only"] = False
        raw["capabilities"] = {name: "controller_verified" for name in raw["capabilities"]}
        raw["qualification"] = {
            "receipt_path": "/tmp/puppet-test-qualification.json",
            "receipt_sha256": "f" * 64,
        }
        manifest = AdapterManifest.from_dict(raw)
        argv = adapter_for("agy").build_launch_argv(manifest)
        self.assertEqual(argv, ["/bin/echo", "--safe-test-flag"])
        self.assertNotIn("Do the task", argv)
        self.assertEqual(raw["yolo_mapping"]["launch_argv"], ["/bin/echo", "--safe-test-flag"])

    def test_manifest_cannot_fingerprint_one_executable_and_launch_another(self):
        raw = manifest_raw()
        raw["yolo_mapping"]["launch_argv"][0] = "/bin/false"
        with self.assertRaisesRegex(ValidationError, "fingerprinted path"):
            AdapterManifest.from_dict(raw)

    def test_bootstrap_cli_returns_unsupported_for_promote_and_close(self):
        cli = SCRIPTS / "puppet.py"
        for command in ("promote", "close"):
            result = subprocess.run(
                [sys.executable, str(cli), command],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 3)
            self.assertIn('"error": "unsupported"', result.stderr)

    def test_qualification_binds_mapping_and_real_harness_receipt(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            raw = manifest_raw()
            manifest_path = root / "doctor.json"
            mapping_path = root / "mapping.json"
            receipt_path = root / "receipt.json"
            out = root / "qualified.json"
            manifest_path.write_text(json.dumps(raw) + "\n", encoding="utf-8")
            mapping_path.write_text(
                json.dumps(raw["yolo_mapping"], sort_keys=True) + "\n", encoding="utf-8"
            )
            mapping_hash = hashlib.sha256(
                json.dumps(
                    raw["yolo_mapping"],
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                ).encode("utf-8")
            ).hexdigest()
            receipt = {
                "schema_version": 1,
                "kind": "real_harness_conformance",
                "run_id": "run-1",
                "target": "agy",
                "result": "accepted",
                "controller": "codex",
                "executable_fingerprint": "a" * 64,
                "adapter_fingerprint": "d" * 64,
                "protocol_fingerprint": "e" * 64,
                "yolo_mapping_sha256": mapping_hash,
                "capabilities": [
                    "launch",
                    "send",
                    "status",
                    "wait",
                    "checkpoint",
                    "resume",
                    "halt",
                ],
                "accepted_checkpoint_id": "1" * 64,
                "acceptance_sha256": "2" * 64,
                "halt_receipt_sha256": "3" * 64,
                "proof_refs": ["proof/agy-conformance"],
            }
            receipt_path.write_text(json.dumps(receipt) + "\n", encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "adapter_lab.py"),
                    "qualify",
                    "--manifest",
                    str(manifest_path),
                    "--mapping",
                    str(mapping_path),
                    "--receipt",
                    str(receipt_path),
                    "--out",
                    str(out),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            qualified = AdapterManifest.from_path(out)
            self.assertFalse(qualified.raw["doctor_only"])
            self.assertEqual(qualified.verify_qualification()["run_id"], "run-1")

    def test_provenance_requires_license_for_extraction(self):
        row = {
            "source_identity": "public/example",
            "revision": "1" * 40,
            "date": "2026-07-22",
            "owner": "example",
            "invariant": "atomic state",
            "proof_artifact": "proof/example.json",
            "proof_strength": "deterministic",
            "mechanism_version_match": True,
            "portability": "portable",
            "operator_assumptions": [],
            "license_path": "MIT",
            "decision": "extract_with_attribution",
            "deterministic_tests": ["test_atomic"],
            "remaining_live_delta": "composition",
        }
        self.assertEqual(len(admission_fingerprint([row])), 64)
        row["license_path"] = ""
        with self.assertRaisesRegex(ValidationError, "license"):
            validate_admission_rows([row])


if __name__ == "__main__":
    unittest.main()
