from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "puppet" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import adapter_lab  # noqa: E402
from puppet_lib.claude_paired_qualification import (  # noqa: E402
    NATIVE_VIEW_NAME,
    PAIRED_RECEIPT_NAME,
    _pair_value,
    build_claude_control_source,
    claude_probe_mapping_from_qualified,
    claude_qualified_mapping,
    observe_native_view,
    validate_native_view,
    validate_pairing_shape,
    verify_claude_pairing,
)
from puppet_lib.errors import (  # noqa: E402
    ConflictError,
    IdentityError,
    UnsupportedError,
    ValidationError,
)
from puppet_lib.safety import canonical_json_bytes, sha256_bytes, sha256_file  # noqa: E402
from tests.test_puppet_probe import manifest_value  # noqa: E402


def write_json(path: Path, value) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")


def process(pid: int, executable: str = "/bin/cat") -> dict:
    path = Path(executable).resolve(strict=True)
    details = path.stat()
    return {
        "identity_version": 2,
        "pid": pid,
        "start": "test-start-%s" % pid,
        "kernel_birth_id": "test:%s" % pid,
        "command": path.name,
        "executable_path": str(path),
        "device": details.st_dev,
        "inode": details.st_ino,
    }


def claude_mapping() -> dict:
    executable = str(Path("/bin/cat").resolve(strict=True))
    return {
        "complete": False,
        "launch_argv": [executable, "--dangerously-skip-permissions"],
        "permission_declared": True,
        "permission_flags": ["--dangerously-skip-permissions"],
        "prompt_transport": "tmux_load_buffer_stdin_then_paste",
        "prompt_transport_declared": True,
        "sandbox_disable_declared": True,
        "sandbox_flags": [],
        "project_isolation_declared": False,
        "project_isolation_flags": [],
        "session_profiles": ["regular"],
        "session_profiles_declared": True,
        "startup_settle_seconds": 3.0,
        "submit_settle_seconds": 1.0,
        "model_flag": "--model",
        "effort_flag": "--effort",
    }


class FakeTmux:
    def __init__(self, root: Path, *, target: dict, viewer: dict):
        self.root = root
        self.target = target
        self.viewer = viewer

    def assert_tmux_binary_identity(self, value):
        self.binary = value

    def bind_server_identity(self, socket, server):
        self.server = server

    def metadata_for_session(self, *, socket, session, server_identity):
        return {
            "session": session,
            "pane": "%1",
            "pane_pid": self.target["pid"],
            "pane_dead": False,
        }

    def viewer_clients(self, *, socket, session, server_identity):
        return [
            {
                "pid": self.viewer["pid"],
                "tty": "/dev/ttys001",
                "read_only": True,
                "session": session,
            }
        ]

    def attach_argv(self, *, socket, session, pane, server_identity):
        return [
            "/usr/bin/tmux",
            "-f",
            os.devnull,
            "-S",
            str(socket),
            "attach-session",
            "-r",
            "-E",
            "-t",
            session,
        ]


class ClaudePairedQualificationTests(unittest.TestCase):
    def test_mapping_closure_is_exact_and_round_trips(self):
        raw = claude_mapping()
        qualified = claude_qualified_mapping(raw)
        self.assertTrue(qualified["complete"])
        self.assertTrue(qualified["project_isolation_declared"])
        self.assertEqual(qualified["project_isolation_flags"], [])
        self.assertEqual(claude_probe_mapping_from_qualified(qualified), raw)
        with self.assertRaisesRegex(ValidationError, "incomplete census tuple"):
            claude_qualified_mapping(qualified)

    def test_control_source_binds_activation_without_body_content(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            receipt_path = root / "receipt.json"
            evidence_path = root / "evidence.json"
            write_json(evidence_path, {"process": process(4201)})
            receipt = {
                "target": "claude",
                "session_profile": "regular",
                "plane_activation": {"terminal_state": "rolled_back"},
                "run_id": "activation-run",
                "controller": "tester",
                "campaign_id": "campaign-one",
                "goal_fingerprint": "1" * 64,
                "subscription_profile_sha256": "2" * 64,
                "controller_attestation": {"ledger_sequence": 4},
                "proof_refs": [
                    {
                        "kind": "evidence",
                        "path": "evidence.json",
                        "sha256": sha256_file(evidence_path),
                    }
                ],
            }
            write_json(receipt_path, receipt)
            source = build_claude_control_source(
                receipt_path,
                verify_receipt_fn=lambda *args, **kwargs: receipt,
            )
            self.assertEqual(source["run_id"], "activation-run")
            self.assertEqual(source["process_sha256"], sha256_bytes(
                canonical_json_bytes(process(4201))
            ))
            encoded = json.dumps(source, sort_keys=True)
            for forbidden in ("prompt", "instruction", "transcript", "reply"):
                self.assertNotIn(forbidden, encoded)

    def test_native_view_observation_is_structural_create_only(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run_root = root / "probes" / "control-run"
            target = process(4301)
            viewer = process(4302)
            tmux = {
                "socket": str(run_root / "tmux.sock"),
                "session": "probe-claude-test",
                "target_id": "%1",
                "socket_identity": {
                    "device": 1,
                    "inode": 2,
                    "uid": os.getuid(),
                    "mode": 0o600,
                },
                "server_identity": process(4303),
                "tmux_binary_identity": {
                    "path": "/usr/bin/tmux",
                    "device": 1,
                    "inode": 2,
                    "uid": 0,
                    "gid": 0,
                    "mode": 0o755,
                    "size": 1,
                    "sha256": "3" * 64,
                    "version": "tmux test",
                },
            }
            state = {
                "run_id": "control-run",
                "target": "claude",
                "controller": "tester",
                "result": "running",
                "phase": "settling_input",
                "tmux": tmux,
                "process": target,
            }
            evidence = {
                "run_id": "control-run",
                "target": "claude",
                "campaign_id": "campaign-one",
                "goal_fingerprint": "4" * 64,
                "tmux": tmux,
                "process": target,
            }
            write_json(run_root / "state.json", state)
            write_json(run_root / "evidence.json", evidence)
            controller = FakeTmux(root, target=target, viewer=viewer)
            result = observe_native_view(
                proof_root=root,
                run_id="control-run",
                tmux_factory=lambda unused: controller,
                process_birth_fn=lambda pid: {
                    target["pid"]: target,
                    viewer["pid"]: viewer,
                }[pid],
                authority_root=root / "authority",
            )
            observation = json.loads(Path(result["native_view"]).read_text())
            self.assertFalse(observation["body_capture_performed"])
            self.assertEqual(observation["viewer_process"], viewer)
            self.assertNotIn("pane", json.dumps(observation, sort_keys=True))
            tampered = json.loads(json.dumps(observation))
            tampered["viewer"]["tty"] = "/dev/ttys999"
            with self.assertRaisesRegex(IdentityError, "attestation binding"):
                validate_native_view(
                    tampered,
                    receipt_path=None,
                    receipt=None,
                    evidence=evidence,
                    launch_plan=None,
                    authority_root=root / "authority",
                )
            with self.assertRaisesRegex(ConflictError, "already exists"):
                observe_native_view(
                    proof_root=root,
                    run_id="control-run",
                    tmux_factory=lambda unused: controller,
                    process_birth_fn=lambda pid: {
                        target["pid"]: target,
                        viewer["pid"]: viewer,
                    }[pid],
                    authority_root=root / "authority",
                )

    def test_pair_verifier_requires_linked_distinct_body_free_runs(self):
        with tempfile.TemporaryDirectory() as temporary:
            probes = Path(temporary) / "probes"
            activation_path = probes / "activation-run" / "receipt.json"
            control_path = probes / "control-run" / "receipt.json"
            pair_path = control_path.parent / PAIRED_RECEIPT_NAME
            activation_path.parent.mkdir(parents=True)
            control_path.parent.mkdir(parents=True)
            write_json(activation_path, {"run": "activation"})
            write_json(control_path, {"run": "control"})
            write_json(activation_path.parent / NATIVE_VIEW_NAME, {"view": "activation"})
            write_json(control_path.parent / NATIVE_VIEW_NAME, {"view": "control"})
            common = {
                "target": "claude",
                "session_profile": "regular",
                "controller": "tester",
                "campaign_id": "campaign-one",
                "goal_fingerprint": "1" * 64,
                "executable_fingerprint": "2" * 64,
                "execution_fingerprint": "3" * 64,
                "version_fingerprint": "4" * 64,
                "platform_fingerprint": "5" * 64,
                "adapter_fingerprint": "6" * 64,
                "protocol_fingerprint": "7" * 64,
                "yolo_mapping_sha256": sha256_bytes(
                    canonical_json_bytes(claude_mapping())
                ),
                "subscription_profile_sha256": "8" * 64,
                "instruction_policy_fingerprint": "9" * 64,
            }
            activation = dict(
                common,
                run_id="activation-run",
                plane_activation={"terminal_state": "rolled_back"},
                controller_attestation={"ledger_sequence": 1},
            )
            control = dict(
                common,
                run_id="control-run",
                plane_activation=None,
                controller_attestation={"ledger_sequence": 2},
            )
            activation_process = process(4401)
            control_process = process(4402)
            instructions = {
                "runtime_binding": {"model": "default", "effort": "default"},
                "model_observation": {
                    "selection": "current_default",
                    "resolved_identity": "unavailable",
                    "effort": "unavailable",
                },
            }
            activation_evidence = {
                "process": activation_process,
                "tmux": {"session": "activation-session", "socket": "/tmp/a"},
                "active_target_processes_before_launch": [],
                "active_target_processes_after_halt": [],
            }
            control_evidence = {
                "process": control_process,
                "tmux": {"session": "control-session", "socket": "/tmp/c"},
                "active_target_processes_before_launch": [],
                "active_target_processes_after_halt": [],
            }
            activation_plan = {
                "cwd": "/tmp/activation-workspace",
                "argv": claude_mapping()["launch_argv"],
            }
            control_plan = {
                "cwd": "/tmp/control-workspace",
                "argv": claude_mapping()["launch_argv"],
            }
            source = {"schema": "source"}
            write_json(
                control_path.parent / "state.json",
                {"claude_control_source": source},
            )
            pair = _pair_value(
                activation_path=activation_path.resolve(),
                activation=activation,
                activation_evidence=activation_evidence,
                activation_plan=activation_plan,
                activation_view_path=(
                    activation_path.parent / NATIVE_VIEW_NAME
                ).resolve(),
                control_path=control_path.resolve(),
                control=control,
                control_evidence=control_evidence,
                control_plan=control_plan,
                control_view_path=(control_path.parent / NATIVE_VIEW_NAME).resolve(),
                qualified_mapping_sha256=sha256_bytes(
                    canonical_json_bytes(
                        claude_qualified_mapping(claude_mapping())
                    )
                ),
            )
            paired = dict(
                control,
                claude_pairing=pair,
                controller_attestation={"ledger_sequence": 3},
            )
            write_json(pair_path, paired)

            def verify(path, **kwargs):
                return (
                    activation
                    if Path(path).resolve() == activation_path.resolve()
                    else control
                )

            with (
                patch(
                    "puppet_lib.claude_paired_qualification._load_run",
                    side_effect=[
                        (activation_evidence, activation_plan, instructions),
                        (control_evidence, control_plan, instructions),
                    ],
                ),
                patch(
                    "puppet_lib.claude_paired_qualification.build_claude_control_source",
                    return_value=source,
                ),
                patch(
                    "puppet_lib.claude_paired_qualification.validate_native_view"
                ),
            ):
                verified = verify_claude_pairing(
                    pair,
                    paired_receipt=paired,
                    paired_receipt_path=pair_path,
                    verify_receipt_fn=verify,
                    current_manifest=SimpleNamespace(
                        raw={"yolo_mapping": claude_mapping()}
                    ),
                )
            self.assertTrue(verified["no_bleed"]["verified"])
            tampered = json.loads(json.dumps(pair))
            tampered["no_bleed"]["distinct_processes"] = False
            with self.assertRaisesRegex(ValidationError, "no-bleed"):
                validate_pairing_shape(tampered)

    def test_unpaired_claude_control_remains_non_promotable(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            raw, mapping = manifest_value("claude")
            manifest_path = root / "doctor.json"
            mapping_path = root / "mapping.json"
            receipt_path = root / "receipt.json"
            write_json(manifest_path, raw)
            write_json(mapping_path, mapping)
            write_json(receipt_path, {})
            arguments = SimpleNamespace(
                manifest=manifest_path,
                mapping=mapping_path,
                receipt=receipt_path,
                out=root / "qualified.json",
            )
            receipt = {
                "target": "claude",
                "session_profile": "regular",
                "plane_activation": None,
                "claude_pairing": None,
            }
            with patch.object(adapter_lab, "_verified_receipt", return_value=receipt):
                with self.assertRaisesRegex(
                    UnsupportedError, "ordinary Claude control proof cannot qualify"
                ):
                    adapter_lab._qualify(arguments)

    def test_public_cli_exposes_control_view_and_pair_paths(self):
        parser = adapter_lab.build_parser()
        probe = parser.parse_args(
            [
                "probe",
                "--target",
                "claude",
                "--profile",
                "source-free-pass-b-v2",
                "--session-profile",
                "regular",
                "--proof-root",
                "/tmp/proof",
                "--manifest",
                "/tmp/manifest",
                "--mapping",
                "/tmp/mapping",
                "--authorization",
                "/tmp/authorization",
                "--controller",
                "tester",
                "--campaign-id",
                "campaign",
                "--goal-repo",
                "/tmp/repo",
                "--goal-repository",
                "owner/repo",
                "--goal-commit",
                "1" * 40,
                "--goal-path",
                "goal.md",
                "--goal-sha256",
                "2" * 64,
                "--paired-activation-receipt",
                "/tmp/activation/receipt.json",
            ]
        )
        self.assertEqual(
            probe.paired_activation_receipt,
            Path("/tmp/activation/receipt.json"),
        )
        self.assertEqual(
            parser.parse_args(
                [
                    "observe-claude-view",
                    "--proof-root",
                    "/tmp/proof",
                    "--run-id",
                    "control-run",
                ]
            ).command,
            "observe-claude-view",
        )
        self.assertEqual(
            parser.parse_args(
                [
                    "pair-claude",
                    "--manifest",
                    "/tmp/manifest",
                    "--mapping",
                    "/tmp/mapping",
                    "--activation-receipt",
                    "/tmp/a/receipt.json",
                    "--control-receipt",
                    "/tmp/c/receipt.json",
                ]
            ).command,
            "pair-claude",
        )


if __name__ == "__main__":
    unittest.main()
