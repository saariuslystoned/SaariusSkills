from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "puppet" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import adapter_lab as puppet_adapter_lab  # noqa: E402
from puppet_lib.adapter_manifest import (  # noqa: E402
    ADAPTER_MANIFEST_SCHEMA_VERSION,
    ACTIVATION_QUALIFICATION_PROOF_KINDS,
    ACTIVATION_LIFECYCLE_SCOPE,
    AdapterManifest,
    CURSOR_REQUIRED_PATH_TOOLS,
    QUALIFICATION_EVIDENCE_SCHEMA_VERSION,
    QUALIFICATION_PROFILE,
    QUALIFICATION_PROOF_KINDS,
    QUALIFICATION_STATE_SCHEMA_VERSION,
    PROBE_PLANE_ACTIVATION_SCHEMA,
    _RECEIPT_FIELDS,
    _ACCEPTED_EVIDENCE_FIELDS,
    _qualification_artifacts,
    _verify_qualification_instruction_authority,
    direct_execution_bundle,
    execution_file_identity,
    QUALIFICATION_RECEIPT_SCHEMA_VERSION,
    validate_qualification_evidence_schema,
    validate_qualification_state_schema,
    validate_probe_plane_activation,
    verify_qualification_receipt,
)
from puppet_lib.adapters import adapter_for  # noqa: E402
from puppet_lib.contracts import MANDATORY_HARD_GATES  # noqa: E402
from puppet_lib.census import (  # noqa: E402
    CENSUS_SCHEMA_VERSION,
    CURSOR_STATIC_LAUNCHER_LAYOUTS,
    DECLARED_MAPPINGS,
    _cursor_execution_bundle,
    _execution_bundle,
    _project_isolation_declared,
    _launch_flags,
    adapter_implementation_fingerprint,
    census_target,
    _sandbox_disable_declared,
    ZERO_AGENT_SESSION_PROFILES,
    ZERO_AGENT_SESSION_PROFILES_DECLARED,
    ZERO_AGENT_STARTUP_SETTLE_SECONDS,
)
from puppet_lib.profiles import (  # noqa: E402
    PROMPT_TRANSPORT,
    SUBMIT_SETTLE_SECONDS,
    session_profiles_for,
    startup_settle_seconds_for,
)
from puppet_lib.errors import IdentityError, UnsupportedError, ValidationError  # noqa: E402
from puppet_lib.provenance import admission_fingerprint, validate_admission_rows  # noqa: E402
from tests.puppet_test_receipt import write_qualification_receipt  # noqa: E402


def manifest_raw(target="agy"):
    executable = Path("/bin/echo").resolve(strict=True)
    executable_details = executable.stat()
    executable_identity = {
        "requested_path": str(executable),
        "resolved_path": str(executable),
        "sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
        "version_sha256": "b" * 64,
        "help_sha256": "c" * 64,
        "device": executable_details.st_dev,
        "inode": executable_details.st_ino,
        "size": executable_details.st_size,
        "mtime_ns": executable_details.st_mtime_ns,
    }
    return {
        "schema_version": ADAPTER_MANIFEST_SCHEMA_VERSION,
        "target": target,
        "generated_at": "2026-07-22T02:00:00Z",
        "platform": {"system": "Darwin", "release": "25", "machine": "arm64"},
        "executable": executable_identity,
        "execution": direct_execution_bundle(executable_identity),
        "adapter_fingerprint": "d" * 64,
        "protocol_fingerprint": "e" * 64,
        "yolo_mapping": {
            "complete": True,
            "launch_argv": (
                [
                    str(executable),
                    "--dangerously-skip-permissions",
                    "--new-project",
                ]
                if target == "agy"
                else [str(executable), "--dangerously-bypass-approvals-and-sandbox"]
            ),
            "permission_declared": True,
            "permission_flags": (
                ["--dangerously-skip-permissions"]
                if target == "agy"
                else ["--dangerously-bypass-approvals-and-sandbox"]
            ),
            "prompt_transport": PROMPT_TRANSPORT,
            "prompt_transport_declared": True,
            "sandbox_disable_declared": True,
            "sandbox_flags": (
                []
                if target == "agy"
                else ["--dangerously-bypass-approvals-and-sandbox"]
            ),
            "project_isolation_declared": True,
            "project_isolation_flags": ["--new-project"] if target == "agy" else [],
            "session_profiles": session_profiles_for(target),
            "session_profiles_declared": True,
            "startup_settle_seconds": startup_settle_seconds_for(target),
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


class AdapterTests(unittest.TestCase):
    def test_qualification_instruction_authority_is_fully_joined(self):
        manifest = {
            "contract_identity": {
                "fingerprint": "1" * 64,
                "controller": "tester",
                "target": "codex",
                "task_profile": "source-free-pass-b-v2",
            },
            "workspace_identity": {
                "fixture_fingerprint": "2" * 64,
                "workspace": "isolated_conformance_fixture",
            },
            "run_identity": {
                "session": "session-1",
                "run_id": "run-1",
                "nonce": "nonce-1",
            },
            "orchestration_contract": {
                "mutation_owner": "none",
                "allowed_modes": ["read", "test"],
                "hard_gates": sorted(MANDATORY_HARD_GATES),
            },
            "runtime_binding": {"model": "default", "effort": "default"},
            "rendered_sha256": "3" * 64,
        }
        kwargs = {
            "instruction_manifest": manifest,
            "receipt": {
                "controller": "tester",
                "target": "codex",
                "run_id": "run-1",
            },
            "evidence": {"fixture_fingerprint_before": "2" * 64},
            "ready_identity": {
                "session": "session-1",
                "nonce": "nonce-1",
            },
            "review": {"contract_fingerprint": "1" * 64},
            "review_summary": {"initial_payload_sha256": "3" * 64},
        }
        _verify_qualification_instruction_authority(**kwargs)
        mutations = {
            "contract": ("instruction_manifest", "contract_identity", "fingerprint"),
            "task_profile": (
                "instruction_manifest",
                "contract_identity",
                "task_profile",
            ),
            "workspace": (
                "instruction_manifest",
                "workspace_identity",
                "workspace",
            ),
            "run_nonce": ("instruction_manifest", "run_identity", "nonce"),
            "orchestration": (
                "instruction_manifest",
                "orchestration_contract",
                "mutation_owner",
            ),
            "model": ("instruction_manifest", "runtime_binding", "model"),
            "delivered_payload": (
                "review_summary",
                "initial_payload_sha256",
            ),
        }
        for label, path in mutations.items():
            with self.subTest(label=label):
                changed = copy.deepcopy(kwargs)
                target = changed[path[0]]
                for part in path[1:-1]:
                    target = target[part]
                target[path[-1]] = "changed"
                with self.assertRaises(ValidationError):
                    _verify_qualification_instruction_authority(**changed)

    def test_qualification_receipt_without_launch_plan_binding_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            receipt_path = Path(temporary) / "receipt.json"
            receipt = {field: None for field in _RECEIPT_FIELDS}
            receipt["schema_version"] = QUALIFICATION_RECEIPT_SCHEMA_VERSION
            receipt.pop("launch_plan_sha256")
            receipt_path.write_text(
                json.dumps(receipt, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValidationError, "fields do not match schema"):
                verify_qualification_receipt(receipt_path)

    def test_native_activation_authority_requires_distinct_bound_trigger(self):
        activation = {
            "schema": PROBE_PLANE_ACTIVATION_SCHEMA,
            "qualification_scope": ACTIVATION_LIFECYCLE_SCOPE,
            "terminal_state": "rolled_back",
            "descriptor_sha256": "1" * 64,
            "plan_sha256": "2" * 64,
            "intent_sha256": "3" * 64,
            "materialization_receipt_sha256": "4" * 64,
            "launch_context_sha256": "5" * 64,
            "artifact_sha256": "6" * 64,
            "initial_trigger_sha256": "7" * 64,
            "rollback_intent_sha256": "8" * 64,
            "rollback_receipt_sha256": "9" * 64,
        }
        manifest = {
            "contract_identity": {
                "fingerprint": "a" * 64,
                "controller": "tester",
                "target": "claude",
                "task_profile": "source-free-pass-b-v2",
            },
            "workspace_identity": {
                "fixture_fingerprint": "b" * 64,
                "workspace": "isolated_conformance_fixture",
            },
            "run_identity": {
                "session": "session-1",
                "run_id": "run-1",
                "nonce": "nonce-1",
            },
            "orchestration_contract": {
                "mutation_owner": "none",
                "allowed_modes": ["read", "test"],
                "hard_gates": sorted(MANDATORY_HARD_GATES),
            },
            "runtime_binding": {"model": "default", "effort": "default"},
            "rendered_sha256": activation["artifact_sha256"],
        }
        kwargs = {
            "instruction_manifest": manifest,
            "receipt": {
                "controller": "tester",
                "target": "claude",
                "run_id": "run-1",
                "plane_activation": activation,
            },
            "evidence": {"fixture_fingerprint_before": "b" * 64},
            "ready_identity": {"session": "session-1", "nonce": "nonce-1"},
            "review": {"contract_fingerprint": "a" * 64},
            "review_summary": {
                "initial_payload_sha256": activation["initial_trigger_sha256"]
            },
        }
        _verify_qualification_instruction_authority(**kwargs)
        duplicated = copy.deepcopy(kwargs)
        duplicated["review_summary"]["initial_payload_sha256"] = activation[
            "artifact_sha256"
        ]
        with self.assertRaisesRegex(ValidationError, "native instruction delivery"):
            _verify_qualification_instruction_authority(**duplicated)

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

    def test_adapter_fingerprint_binds_instruction_templates(self):
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "puppet"
            shutil.copytree(ROOT / "skills" / "puppet", copied)
            before = adapter_implementation_fingerprint(copied)
            template = copied / "templates" / "instructions" / "universal.md"
            template.write_text(
                template.read_text(encoding="utf-8") + "\nTemplate drift.\n",
                encoding="utf-8",
            )
            after = adapter_implementation_fingerprint(copied)
            self.assertNotEqual(before, after)

    def test_adapter_fingerprint_binds_native_viewer_helper(self):
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "puppet"
            shutil.copytree(ROOT / "skills" / "puppet", copied)
            before = adapter_implementation_fingerprint(copied)
            helper = copied / "scripts" / "viewer_attach.py"
            helper.write_text(
                helper.read_text(encoding="utf-8") + "\n# viewer drift\n",
                encoding="utf-8",
            )
            after = adapter_implementation_fingerprint(copied)
            self.assertNotEqual(before, after)

    def test_adapter_fingerprint_binds_subscription_login_helper(self):
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "puppet"
            shutil.copytree(ROOT / "skills" / "puppet", copied)
            before = adapter_implementation_fingerprint(copied)
            helper = copied / "scripts" / "profile_login.py"
            helper.write_text(
                helper.read_text(encoding="utf-8") + "\n# profile helper drift\n",
                encoding="utf-8",
            )
            after = adapter_implementation_fingerprint(copied)
            self.assertNotEqual(before, after)

    def test_sandbox_disable_mapping_distinguishes_omission_from_unknown(self):
        agy_help = "  --sandbox  Run in a sandbox with terminal restrictions enabled"
        self.assertFalse(
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
            _project_isolation_declared(DECLARED_MAPPINGS["agy"], "  --new-project")
        )
        self.assertFalse(
            _project_isolation_declared(
                {"project_isolation_flags": ["--new-project"]}, ""
            )
        )
        for false_positive in (
            "  --new-projectish  Not the requested flag",
            "This prose mentions --new-project but does not declare it.",
        ):
            with self.subTest(false_positive=false_positive):
                self.assertFalse(
                    _project_isolation_declared(
                        {"project_isolation_flags": ["--new-project"]},
                        false_positive,
                    )
                )

    def test_empty_project_flags_never_prove_isolation(self):
        self.assertFalse(
            _project_isolation_declared({"project_isolation_flags": []}, "")
        )

    def test_cursor_exact_shell_layout_binds_bundled_runtime_and_entrypoint(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            launcher = root / "cursor-agent"
            node = root / "node"
            entrypoint = root / "index.js"
            launcher.write_bytes(CURSOR_STATIC_LAUNCHER_LAYOUTS[0])
            node.write_bytes(b"synthetic bundled node")
            entrypoint.write_bytes(b"synthetic cursor entrypoint")
            launcher_file = execution_file_identity(launcher)
            executable = {
                "requested_path": launcher_file["path"],
                "resolved_path": launcher_file["path"],
                "device": launcher_file["device"],
                "inode": launcher_file["inode"],
                "size": launcher_file["size"],
                "mtime_ns": launcher_file["mtime_ns"],
                "sha256": launcher_file["sha256"],
                "version_sha256": "b" * 64,
                "help_sha256": "c" * 64,
            }
            execution = _cursor_execution_bundle(launcher, executable)
            self.assertEqual(execution["transition"], "same_pid_exec")
            self.assertEqual(
                execution["runtime_executable"]["path"], str(node.resolve())
            )
            self.assertEqual(
                [item["path"] for item in execution["support_files"]],
                [str(entrypoint.resolve())],
            )
            self.assertEqual(
                {
                    Path(item["path"]).name
                    for item in execution["transient_executables"]
                },
                {"env", *CURSOR_REQUIRED_PATH_TOOLS},
            )
            cursor_manifest = AdapterManifest(
                {"target": "cursor", "execution": execution}
            )
            bash_path = next(
                Path(item["path"])
                for item in execution["transient_executables"]
                if Path(item["path"]).name == "bash"
            )
            cursor_path = os.environ["PATH"]
            cursor_manifest.verify_launch_execution_environment({"PATH": cursor_path})
            with self.assertRaisesRegex(IdentityError, "cwd-dependent"):
                cursor_manifest.verify_launch_execution_environment(
                    {"PATH": "bin" + os.pathsep + str(bash_path.parent)}
                )
            wrong_bin = root / "wrong-bin"
            wrong_bin.mkdir()
            wrong_bash = wrong_bin / "bash"
            wrong_bash.write_bytes(b"not the declared interpreter")
            wrong_bash.chmod(0o700)
            with self.assertRaisesRegex(IdentityError, "not declared"):
                cursor_manifest.verify_launch_execution_environment(
                    {"PATH": str(wrong_bin)}
                )
            with (
                patch.dict(
                    os.environ,
                    {"PATH": "bin" + os.pathsep + str(bash_path.parent)},
                ),
                self.assertRaisesRegex(ValidationError, "cwd-dependent"),
            ):
                _cursor_execution_bundle(launcher, executable)

    def test_cursor_census_validates_before_probe_and_never_executes_wrapper(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            launcher = root / "cursor-agent"
            node = root / "node"
            entrypoint = root / "index.js"
            launcher.write_bytes(CURSOR_STATIC_LAUNCHER_LAYOUTS[0])
            node.write_bytes(b"synthetic bundled node")
            entrypoint.write_bytes(b"synthetic cursor entrypoint")
            real_which = shutil.which

            def discovered(command, path=None):
                if command == "cursor-agent":
                    return str(launcher)
                return real_which(command, path=path)

            with (
                patch("puppet_lib.census.shutil.which", side_effect=discovered),
                patch(
                    "puppet_lib.census._bounded_run",
                    side_effect=[
                        b"cursor-agent 1\n",
                        b"--yolo --sandbox disabled\n",
                    ],
                ) as bounded_run,
            ):
                census_target("cursor", "d" * 64)
            self.assertEqual(
                [call.args[0] for call in bounded_run.call_args_list],
                [
                    [str(node.resolve()), str(entrypoint.resolve()), "--version"],
                    [str(node.resolve()), str(entrypoint.resolve()), "--help"],
                ],
            )

            launcher.write_bytes(
                CURSOR_STATIC_LAUNCHER_LAYOUTS[0].replace(
                    b"set -euo pipefail\n",
                    b"set -euo pipefail\nexport PATH=/attacker-controlled-bin\n",
                )
            )
            with (
                patch("puppet_lib.census.shutil.which", side_effect=discovered),
                patch("puppet_lib.census._bounded_run") as bounded_run,
                self.assertRaisesRegex(ValidationError, "recognized shell layout"),
            ):
                census_target("cursor", "d" * 64)
            bounded_run.assert_not_called()

    def test_unknown_cursor_and_grok_shell_wrappers_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            launcher = root / "wrapper"
            launcher.write_text(
                '#!/usr/bin/env bash\nexec /usr/bin/false "$@"\n',
                encoding="utf-8",
            )
            launcher_file = execution_file_identity(launcher)
            executable = {
                "requested_path": launcher_file["path"],
                "resolved_path": launcher_file["path"],
                "device": launcher_file["device"],
                "inode": launcher_file["inode"],
                "size": launcher_file["size"],
                "mtime_ns": launcher_file["mtime_ns"],
                "sha256": launcher_file["sha256"],
                "version_sha256": "b" * 64,
                "help_sha256": "c" * 64,
            }
            with self.assertRaisesRegex(ValidationError, "recognized shell layout"):
                _cursor_execution_bundle(launcher, executable)
            with self.assertRaisesRegex(ValidationError, "no exact runtime resolver"):
                _execution_bundle("grok", launcher, executable)

            launcher.write_bytes(
                CURSOR_STATIC_LAUNCHER_LAYOUTS[0].replace(
                    b'NODE_BIN="$SCRIPT_DIR/node"\n',
                    b'NODE_BIN="$SCRIPT_DIR/node"\nNODE_BIN=/usr/bin/false\n',
                )
            )
            changed_launcher_file = execution_file_identity(launcher)
            changed_executable = dict(executable)
            changed_executable.update(
                requested_path=changed_launcher_file["path"],
                resolved_path=changed_launcher_file["path"],
                device=changed_launcher_file["device"],
                inode=changed_launcher_file["inode"],
                size=changed_launcher_file["size"],
                mtime_ns=changed_launcher_file["mtime_ns"],
                sha256=changed_launcher_file["sha256"],
            )
            with self.assertRaisesRegex(ValidationError, "recognized shell layout"):
                _cursor_execution_bundle(launcher, changed_executable)

    def test_agy_prefix_is_explicit_and_closed(self):
        adapter = adapter_for("agy")
        self.assertEqual(adapter.envelope("Do the task"), "Do the task")
        self.assertEqual(
            adapter.envelope("Do the task", session_profile="goal", initial=True),
            "/goal Do the task",
        )
        self.assertEqual(
            adapter.envelope("Do the task", session_profile="goal", initial=False),
            "Do the task",
        )
        self.assertEqual(
            adapter.envelope(
                "Do the task", session_profile="teamwork-preview", initial=True
            ),
            "/teamwork-preview Do the task",
        )
        self.assertEqual(
            adapter.envelope(
                "Do the task", session_profile="teamwork-preview", initial=False
            ),
            "Do the task",
        )
        self.assertEqual(
            adapter.graceful_halt_actions,
            ("tmux_pane_eof", "tmux_pane_eof"),
        )
        with self.assertRaises(ValidationError):
            adapter.envelope("Do the task", session_profile="invalid")
        for value in (
            "/teamwork-preview duplicate",
            "/goal duplicate",
            "/btw side",
            "/side side",
            "",
        ):
            with self.subTest(value=value):
                with self.assertRaises(ValidationError):
                    adapter.envelope(value)

    def test_codex_and_claude_profile_selection_is_explicit(self):
        codex = adapter_for("codex")
        claude = adapter_for("claude")
        self.assertEqual(codex.envelope("Do the task"), "Do the task")
        self.assertEqual(
            codex.envelope("Do the task", session_profile="goal", initial=True),
            "/goal Do the task",
        )
        self.assertEqual(
            codex.envelope("Do the task", session_profile="goal", initial=False),
            "Do the task",
        )
        with self.assertRaises(ValidationError):
            codex.envelope("Do the task", session_profile="loop")
        self.assertEqual(claude.envelope("Do the task"), "Do the task")
        self.assertEqual(
            claude.envelope("Do the task", session_profile="loop", initial=True),
            "/loop Do the task",
        )
        self.assertEqual(
            claude.envelope("Do the task", session_profile="goal", initial=True),
            "/goal Do the task",
        )
        self.assertEqual(
            claude.envelope("Do the task", session_profile="goal", initial=False),
            "Do the task",
        )
        with self.assertRaises(ValidationError):
            claude.envelope("/loop task", session_profile="loop")

    def test_cursor_and_grok_are_regular_only(self):
        for target in ("cursor", "grok"):
            adapter = adapter_for(target)
            self.assertEqual(adapter.envelope("Do the task"), "Do the task")
            with self.assertRaises(ValidationError):
                adapter.envelope("Do the task", session_profile="goal")

    def test_caller_supplied_slash_commands_are_rejected(self):
        for target in ("agy", "cursor", "claude", "codex", "grok"):
            with (
                self.subTest(target=target),
                self.assertRaisesRegex(ValidationError, "slash commands"),
            ):
                adapter_for(target).envelope("/help", initial=False)

    def test_zero_agent_session_profile_mapping_is_explicit(self):
        self.assertTrue(ZERO_AGENT_SESSION_PROFILES_DECLARED)
        self.assertEqual(
            ZERO_AGENT_SESSION_PROFILES,
            {
                "agy": ["regular", "goal", "teamwork-preview"],
                "cursor": ["regular"],
                "claude": ["regular", "loop", "goal"],
                "codex": ["regular", "goal"],
                "grok": ["regular"],
            },
        )
        self.assertEqual(
            ZERO_AGENT_STARTUP_SETTLE_SECONDS,
            {
                target: startup_settle_seconds_for(target)
                for target in ("agy", "cursor", "claude", "codex", "grok")
            },
        )

    def test_doctor_only_manifest_cannot_launch(self):
        manifest = AdapterManifest.from_dict(manifest_raw())
        with self.assertRaises(UnsupportedError):
            adapter_for("agy").build_launch_argv(manifest)

    def test_runtime_manifest_schema_versions_fail_closed(self):
        current_manifest = AdapterManifest.from_dict(manifest_raw())
        selectors = current_manifest.process_execution_selectors()
        self.assertEqual(len(selectors), 1)
        self.assertEqual(
            selectors[0]["path"], current_manifest.raw["executable"]["resolved_path"]
        )

        legacy = manifest_raw()
        legacy["schema_version"] = 1
        with self.assertRaisesRegex(UnsupportedError, "legacy adapter manifest"):
            AdapterManifest.from_dict(legacy)

        future = manifest_raw()
        future["schema_version"] = ADAPTER_MANIFEST_SCHEMA_VERSION + 1
        with self.assertRaisesRegex(ValidationError, "unsupported adapter manifest"):
            AdapterManifest.from_dict(future)

        mixed = manifest_raw()
        mixed.pop("execution")
        with self.assertRaisesRegex(ValidationError, "fields"):
            AdapterManifest.from_dict(mixed)

    def test_census_scaffold_schema_versions_and_mixed_bundle_fail_closed(self):
        current = {
            "schema_version": CENSUS_SCHEMA_VERSION,
            "zero_agent": True,
            "manifests": {"agy": manifest_raw()},
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            census_path = root / "census.json"
            cases = {
                "current": (current, None, None),
                "legacy": (
                    dict(current, schema_version=1),
                    UnsupportedError,
                    "legacy zero-agent census",
                ),
                "future": (
                    dict(current, schema_version=CENSUS_SCHEMA_VERSION + 1),
                    ValidationError,
                    "unsupported zero-agent census",
                ),
                "mixed": (
                    dict(current, zero_agent=False),
                    ValidationError,
                    "invalid zero-agent census bundle",
                ),
            }
            for name, (bundle, error, message) in cases.items():
                census_path.write_text(json.dumps(bundle) + "\n", encoding="utf-8")
                arguments = SimpleNamespace(
                    census=census_path,
                    out=root / ("scaffold-" + name),
                )
                with self.subTest(name=name):
                    if error is None:
                        result = puppet_adapter_lab._scaffold(arguments)
                        self.assertTrue(result["ok"])
                        self.assertEqual(len(result["manifests"]), 1)
                    else:
                        with self.assertRaisesRegex(error, message):
                            puppet_adapter_lab._scaffold(arguments)

    def test_qualification_receipt_schema_versions_fail_before_inference(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "receipt.json"
            for version, error, message in (
                (1, UnsupportedError, "legacy qualification receipt"),
                (2, UnsupportedError, "legacy qualification receipt"),
                (3, UnsupportedError, "legacy qualification receipt"),
                (
                    QUALIFICATION_RECEIPT_SCHEMA_VERSION + 1,
                    ValidationError,
                    "unsupported qualification receipt",
                ),
                (
                    QUALIFICATION_RECEIPT_SCHEMA_VERSION,
                    ValidationError,
                    "fields do not match",
                ),
            ):
                with self.subTest(version=version):
                    path.write_text(
                        json.dumps({"schema_version": version}) + "\n",
                        encoding="utf-8",
                    )
                    with self.assertRaisesRegex(error, message):
                        verify_qualification_receipt(path)

            legacy_shape = {
                name: None
                for name in _RECEIPT_FIELDS
                if name != "execution_fingerprint"
            }
            legacy_shape["schema_version"] = 1
            path.write_text(json.dumps(legacy_shape) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(UnsupportedError, "legacy qualification"):
                verify_qualification_receipt(path)

            current_missing_execution = {name: None for name in _RECEIPT_FIELDS}
            current_missing_execution["schema_version"] = (
                QUALIFICATION_RECEIPT_SCHEMA_VERSION
            )
            current_missing_execution.pop("execution_fingerprint")
            path.write_text(
                json.dumps(current_missing_execution) + "\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(ValidationError, "fields do not match"):
                verify_qualification_receipt(path)

    def test_qualification_evidence_schema_versions_and_mixed_shape_fail_closed(self):
        current = {name: None for name in _ACCEPTED_EVIDENCE_FIELDS}
        current.update(
            schema_version=QUALIFICATION_EVIDENCE_SCHEMA_VERSION,
            execution_fingerprint="a" * 64,
            subscription_profile_sha256="b" * 64,
        )
        self.assertEqual(validate_qualification_evidence_schema(current), current)

        accepted_without_profile = dict(
            current,
            result="accepted",
            subscription_profile_sha256=None,
        )
        with self.assertRaisesRegex(
            ValidationError, "subscription profile fingerprint"
        ):
            validate_qualification_evidence_schema(accepted_without_profile)

        for legacy_version in (1, 2, 3):
            with self.subTest(legacy_version=legacy_version):
                with self.assertRaisesRegex(
                    UnsupportedError, "legacy qualification evidence"
                ):
                    validate_qualification_evidence_schema(
                        dict(current, schema_version=legacy_version)
                    )
        with self.assertRaisesRegex(ValidationError, "unsupported qualification"):
            validate_qualification_evidence_schema(
                dict(
                    current,
                    schema_version=QUALIFICATION_EVIDENCE_SCHEMA_VERSION + 1,
                )
            )
        mixed = dict(current)
        mixed.pop("execution_fingerprint")
        with self.assertRaisesRegex(ValidationError, "fields do not match"):
            validate_qualification_evidence_schema(mixed)

    def test_probe_plane_activation_shape_is_exact_and_nonduplicative(self):
        activation = {
            "schema": PROBE_PLANE_ACTIVATION_SCHEMA,
            "qualification_scope": ACTIVATION_LIFECYCLE_SCOPE,
            "terminal_state": "rolled_back",
            "descriptor_sha256": "1" * 64,
            "plan_sha256": "2" * 64,
            "intent_sha256": "3" * 64,
            "materialization_receipt_sha256": "4" * 64,
            "launch_context_sha256": "5" * 64,
            "artifact_sha256": "6" * 64,
            "initial_trigger_sha256": "7" * 64,
            "rollback_intent_sha256": "8" * 64,
            "rollback_receipt_sha256": "9" * 64,
        }
        self.assertIsNone(validate_probe_plane_activation(None))
        self.assertEqual(validate_probe_plane_activation(activation), activation)
        for mutation in (
            {**activation, "unexpected": True},
            {
                name: value
                for name, value in activation.items()
                if name != "plan_sha256"
            },
            {**activation, "terminal_state": "active"},
            {
                **activation,
                "initial_trigger_sha256": activation["artifact_sha256"],
            },
        ):
            with self.subTest(mutation=mutation):
                with self.assertRaises(ValidationError):
                    validate_probe_plane_activation(mutation)

    def test_activation_receipts_require_the_exact_additional_proof_kinds(self):
        activation = {
            "schema": PROBE_PLANE_ACTIVATION_SCHEMA,
            "qualification_scope": ACTIVATION_LIFECYCLE_SCOPE,
            "terminal_state": "rolled_back",
            "descriptor_sha256": "1" * 64,
            "plan_sha256": "2" * 64,
            "intent_sha256": "3" * 64,
            "materialization_receipt_sha256": "4" * 64,
            "launch_context_sha256": "5" * 64,
            "artifact_sha256": "6" * 64,
            "initial_trigger_sha256": "7" * 64,
            "rollback_intent_sha256": "8" * 64,
            "rollback_receipt_sha256": "9" * 64,
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            receipt_path = root / "receipt.json"
            receipt_path.write_text("{}\n", encoding="utf-8")
            kinds = QUALIFICATION_PROOF_KINDS + ACTIVATION_QUALIFICATION_PROOF_KINDS
            refs = []
            for kind in kinds:
                artifact = root / (kind + ".json")
                artifact.write_text("{}\n", encoding="utf-8")
                refs.append(
                    {
                        "kind": kind,
                        "path": artifact.name,
                        "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
                    }
                )
            receipt = {"plane_activation": activation, "proof_refs": refs}
            self.assertEqual(
                set(_qualification_artifacts(receipt_path, receipt)), set(kinds)
            )

            missing = copy.deepcopy(receipt)
            missing["proof_refs"].pop()
            with self.assertRaisesRegex(ValidationError, "references are incomplete"):
                _qualification_artifacts(receipt_path, missing)

            nonactivated = copy.deepcopy(receipt)
            nonactivated["plane_activation"] = None
            with self.assertRaisesRegex(ValidationError, "references are incomplete"):
                _qualification_artifacts(receipt_path, nonactivated)

    def test_qualification_state_schema_versions_and_profile_fail_closed(self):
        current = {
            "schema_version": QUALIFICATION_STATE_SCHEMA_VERSION,
            "profile": QUALIFICATION_PROFILE,
        }
        self.assertEqual(validate_qualification_state_schema(current), current)
        for legacy_version in (1, 2, 3):
            with self.subTest(legacy_version=legacy_version):
                with self.assertRaisesRegex(
                    UnsupportedError, "legacy qualification state"
                ):
                    validate_qualification_state_schema(
                        dict(current, schema_version=legacy_version)
                    )
        with self.assertRaisesRegex(ValidationError, "unsupported qualification"):
            validate_qualification_state_schema(
                dict(
                    current,
                    schema_version=QUALIFICATION_STATE_SCHEMA_VERSION + 1,
                )
            )
        with self.assertRaisesRegex(ValidationError, "schema and profile are mixed"):
            validate_qualification_state_schema(
                dict(current, profile="source-free-pass-b-v1")
            )

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
            "session_profile": "teamwork-preview",
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

    def test_option_shaped_model_and_effort_values_cannot_inject_launch_flags(self):
        raw = manifest_raw()
        raw["doctor_only"] = False
        raw["capabilities"] = {
            name: "controller_verified" if name != "resume" else "unsupported"
            for name in raw["capabilities"]
        }
        raw["qualification"] = {
            "receipt_path": "/tmp/puppet-test-qualification.json",
            "receipt_sha256": "f" * 64,
            "session_profile": "teamwork-preview",
        }
        raw["yolo_mapping"].update(
            model_flag="--model",
            effort_flag="--effort",
        )
        manifest = AdapterManifest.from_dict(raw)
        with self.assertRaisesRegex(ValidationError, "requested model is invalid"):
            adapter_for("agy").build_launch_argv(
                manifest, requested_model="--new-project"
            )
        with self.assertRaisesRegex(ValidationError, "requested effort is invalid"):
            adapter_for("agy").build_launch_argv(
                manifest, requested_effort="--new-project"
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
            raw = manifest_raw(target="codex")
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
                target="codex",
                controller="agy",
                executable_path=Path(raw["executable"]["resolved_path"]),
                executable_fingerprint=raw["executable"]["sha256"],
                execution_fingerprint=raw["execution"]["execution_fingerprint"],
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
                launch_argv=raw["yolo_mapping"]["launch_argv"],
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

    def test_adapter_lab_refuses_activation_lifecycle_only_receipt(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            raw = manifest_raw(target="codex")
            manifest_path = root / "doctor.json"
            mapping_path = root / "mapping.json"
            receipt_path = root / "receipt.json"
            out = root / "qualified.json"
            manifest_path.write_text(json.dumps(raw) + "\n", encoding="utf-8")
            mapping_path.write_text(
                json.dumps(raw["yolo_mapping"]) + "\n",
                encoding="utf-8",
            )
            receipt_path.write_text("{}\n", encoding="utf-8")
            arguments = SimpleNamespace(
                manifest=manifest_path,
                mapping=mapping_path,
                receipt=receipt_path,
                out=out,
            )
            with patch.object(
                puppet_adapter_lab,
                "_verified_receipt",
                return_value={"plane_activation": {"terminal_state": "rolled_back"}},
            ):
                with self.assertRaisesRegex(
                    UnsupportedError,
                    "cannot qualify a live adapter without matched no-bleed",
                ):
                    puppet_adapter_lab._qualify(arguments)
            self.assertFalse(out.exists())

    def test_adapter_lab_probe_and_recover_accept_optional_plane_descriptor(self):
        descriptor = Path("claude-plane.json")
        subscription_profile = Path("claude-subscription-profile")
        shared = [
            "--target",
            "claude",
            "--proof-root",
            "proof",
            "--manifest",
            "doctor.json",
            "--mapping",
            "mapping.json",
            "--authorization",
            "campaign.json",
            "--controller",
            "tester",
            "--campaign-id",
            "campaign-1",
            "--goal-repo",
            "goal-repo",
            "--goal-repository",
            "test/repo",
            "--goal-commit",
            "a" * 40,
            "--goal-path",
            "goal.md",
            "--goal-sha256",
            "b" * 64,
            "--plane-descriptor",
            str(descriptor),
        ]
        probe = puppet_adapter_lab.build_parser().parse_args(
            [
                "probe",
                "--profile",
                QUALIFICATION_PROFILE,
                "--session-profile",
                "regular",
                "--subscription-profile-root",
                str(subscription_profile),
                *shared,
            ]
        )
        recovery = puppet_adapter_lab.build_parser().parse_args(
            ["recover", "--run-id", "probe-1", *shared]
        )
        self.assertEqual(probe.plane_descriptor, descriptor)
        self.assertEqual(probe.subscription_profile_root, subscription_profile)
        self.assertEqual(recovery.plane_descriptor, descriptor)

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
        for selector in ("model_flag", "effort_flag"):
            with self.subTest("selector_duplicate", selector=selector):
                duplicate = dict(raw)
                duplicate["yolo_mapping"] = dict(raw["yolo_mapping"])
                duplicate["yolo_mapping"][selector] = "--new-project"
                with self.assertRaisesRegex(
                    ValidationError, "selector flags overlap another semantic bucket"
                ):
                    AdapterManifest.from_dict(duplicate)

    def test_model_and_effort_selector_flags_must_be_distinct(self):
        raw = manifest_raw()
        raw["yolo_mapping"].update(
            model_flag="--selector",
            effort_flag="--selector",
        )
        with self.assertRaisesRegex(
            ValidationError, "model and effort selector flags overlap"
        ):
            AdapterManifest.from_dict(raw)

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
            "session_profile": "teamwork-preview",
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
