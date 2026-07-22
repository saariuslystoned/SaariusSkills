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
from puppet_lib.census import (  # noqa: E402
    DECLARED_MAPPINGS,
    _project_isolation_declared,
    _launch_flags,
    adapter_implementation_fingerprint,
    _sandbox_disable_declared,
)
from puppet_lib.errors import UnsupportedError, ValidationError  # noqa: E402
from puppet_lib.provenance import admission_fingerprint, validate_admission_rows  # noqa: E402
from tests.puppet_test_receipt import write_qualification_receipt  # noqa: E402


def manifest_raw():
    executable = Path("/bin/echo").resolve(strict=True)
    executable_details = executable.stat()
    return {
        "schema_version": 1,
        "target": "agy",
        "generated_at": "2026-07-22T02:00:00Z",
        "platform": {"system": "Darwin", "release": "25", "machine": "arm64"},
        "executable": {
            "requested_path": str(executable),
            "resolved_path": str(executable),
            "sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
            "version_sha256": "b" * 64,
            "help_sha256": "c" * 64,
            "device": executable_details.st_dev,
            "inode": executable_details.st_ino,
            "size": executable_details.st_size,
            "mtime_ns": executable_details.st_mtime_ns,
        },
        "adapter_fingerprint": "d" * 64,
        "protocol_fingerprint": "e" * 64,
        "yolo_mapping": {
            "complete": True,
            "launch_argv": [str(executable), "--dangerously-skip-permissions", "--new-project"],
            "permission_declared": True,
            "permission_flags": ["--dangerously-skip-permissions"],
            "prompt_transport": "tmux_stdin_buffer",
            "prompt_transport_declared": True,
            "sandbox_disable_declared": True,
            "sandbox_flags": [],
            "project_isolation_declared": True,
            "project_isolation_flags": ["--new-project"],
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
    def test_combined_permission_and_sandbox_switch_is_emitted_once(self):
        self.assertEqual(
            _launch_flags(DECLARED_MAPPINGS["codex"]),
            ["--dangerously-bypass-approvals-and-sandbox"],
        )
        self.assertEqual(
            _launch_flags(DECLARED_MAPPINGS["agy"]),
            ["--dangerously-skip-permissions", "--new-project"],
        )

    def test_adapter_fingerprint_binds_the_runtime_module_closure(self):
        fingerprint = adapter_implementation_fingerprint()
        adapters_only = hashlib.sha256(
            (SCRIPTS / "puppet_lib" / "adapters.py").read_bytes()
        ).hexdigest()
        self.assertEqual(len(fingerprint), 64)
        self.assertNotEqual(fingerprint, adapters_only)

    def test_sandbox_disable_mapping_distinguishes_omission_from_unknown(self):
        agy_help = "  --sandbox  Run in a sandbox with terminal restrictions enabled"
        self.assertTrue(
            _sandbox_disable_declared("agy", DECLARED_MAPPINGS["agy"], agy_help)
        )
        self.assertTrue(
            _sandbox_disable_declared(
                "claude",
                DECLARED_MAPPINGS["claude"],
                "  --dangerously-skip-permissions",
            )
        )
        self.assertFalse(
            _sandbox_disable_declared(
                "grok", DECLARED_MAPPINGS["grok"], "  --sandbox <PROFILE>"
            )
        )
        self.assertTrue(
            _project_isolation_declared(
                DECLARED_MAPPINGS["agy"], "  --new-project"
            )
        )
        self.assertFalse(
            _project_isolation_declared(
                {"project_isolation_flags": ["--new-project"]}, ""
            )
        )

    def test_agy_prefix_is_exactly_once(self):
        adapter = adapter_for("agy")
        self.assertEqual(adapter.envelope("Do the task"), "/teamwork-preview Do the task")
        self.assertEqual(
            adapter.graceful_halt_actions,
            ("tmux_pane_eof", "tmux_pane_eof"),
        )
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
        raw["capabilities"] = {
            name: "controller_verified" if name != "resume" else "unsupported"
            for name in raw["capabilities"]
        }
        raw["qualification"] = {
            "receipt_path": "/tmp/puppet-test-qualification.json",
            "receipt_sha256": "f" * 64,
        }
        manifest = AdapterManifest.from_dict(raw)
        argv = adapter_for("agy").build_launch_argv(manifest)
        self.assertEqual(
            argv,
            ["/bin/echo", "--dangerously-skip-permissions", "--new-project"],
        )
        self.assertNotIn("Do the task", argv)
        self.assertEqual(
            raw["yolo_mapping"]["launch_argv"],
            ["/bin/echo", "--dangerously-skip-permissions", "--new-project"],
        )

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

    def test_synthetic_structural_receipt_cannot_qualify_a_manifest(self):
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
            write_qualification_receipt(
                receipt_path,
                run_id="run-1",
                target="agy",
                controller="codex",
                executable_path=Path(raw["executable"]["resolved_path"]),
                executable_fingerprint=raw["executable"]["sha256"],
                version_fingerprint="b" * 64,
                platform_fingerprint=hashlib.sha256(
                    json.dumps(
                        raw["platform"],
                        sort_keys=True,
                        separators=(",", ":"),
                        ensure_ascii=False,
                    ).encode("utf-8")
                ).hexdigest(),
                adapter_fingerprint="d" * 64,
                protocol_fingerprint="e" * 64,
                yolo_mapping_sha256=mapping_hash,
                capabilities=[
                    "launch",
                    "send",
                    "status",
                    "wait",
                    "checkpoint",
                    "halt",
                ],
            )
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
            self.assertEqual(result.returncode, 2, result.stdout)
            self.assertFalse(out.exists())
            self.assertIn("authority", result.stderr)

    def test_agy_project_isolation_flag_set_is_required(self):
        raw = manifest_raw()
        with self.subTest("mismatched_flags"):
            mismatched = dict(raw)
            mismatched["yolo_mapping"] = dict(raw["yolo_mapping"])
            mismatched["yolo_mapping"]["project_isolation_flags"] = ["--other-project"]
            mismatched["yolo_mapping"]["launch_argv"] = [
                str(Path(raw["executable"]["resolved_path"])),
                "--dangerously-skip-permissions",
                "--other-project",
            ]
            with self.assertRaises(ValidationError):
                AdapterManifest.from_dict(mismatched)
        with self.subTest("missing_flags"):
            missing = dict(raw)
            missing["yolo_mapping"] = dict(raw["yolo_mapping"])
            missing["yolo_mapping"]["project_isolation_flags"] = []
            missing["yolo_mapping"]["launch_argv"] = [
                str(Path(raw["executable"]["resolved_path"])),
                "--dangerously-skip-permissions",
            ]
            with self.assertRaises(ValidationError):
                AdapterManifest.from_dict(missing)
        with self.subTest("duplicate_flags"):
            duplicate = dict(raw)
            duplicate["yolo_mapping"] = dict(raw["yolo_mapping"])
            duplicate["yolo_mapping"]["project_isolation_flags"] = [
                "--new-project",
                "--new-project",
            ]
            duplicate["yolo_mapping"]["launch_argv"] = [
                str(Path(raw["executable"]["resolved_path"])),
                "--dangerously-skip-permissions",
                "--new-project",
            ]
            with self.assertRaises(ValidationError):
                AdapterManifest.from_dict(duplicate)
        for bucket in ("permission_flags", "sandbox_flags"):
            with self.subTest("cross_bucket_duplicate", bucket=bucket):
                duplicate = dict(raw)
                duplicate["yolo_mapping"] = dict(raw["yolo_mapping"])
                duplicate["yolo_mapping"][bucket] = list(
                    raw["yolo_mapping"][bucket]
                ) + ["--new-project"]
                with self.assertRaisesRegex(
                    ValidationError, "overlap another semantic bucket"
                ):
                    AdapterManifest.from_dict(duplicate)

    def test_live_manifest_cannot_claim_unproved_resume(self):
        raw = manifest_raw()
        raw["doctor_only"] = False
        raw["capabilities"] = {
            name: "controller_verified" if name != "resume" else "declared"
            for name in raw["capabilities"]
        }
        raw["qualification"] = {
            "receipt_path": "/tmp/puppet-test-qualification.json",
            "receipt_sha256": "f" * 64,
        }
        with self.assertRaisesRegex(ValidationError, "fail closed"):
            AdapterManifest.from_dict(raw)

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
