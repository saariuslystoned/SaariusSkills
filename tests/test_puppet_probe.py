from __future__ import annotations

import json
import os
import platform
import socket as socket_module
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "puppet" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from puppet_lib.adapter_manifest import (  # noqa: E402
    AdapterManifest,
    PROBE_CAPABILITIES,
    verify_qualification_receipt,
)
from puppet_lib.authority import admit_session_lease  # noqa: E402
from puppet_lib.errors import ConflictError, IdentityError, ValidationError  # noqa: E402
from puppet_lib.handoffs import PROTOCOL_FINGERPRINT  # noqa: E402
from puppet_lib.probe import (  # noqa: E402
    _acquire_campaign_probe_lock,
    _release_campaign_probe_lock,
    recover_probe,
    run_probe,
)
from puppet_lib.safety import (  # noqa: E402
    canonical_json_bytes,
    sha256_bytes,
    sha256_file,
)


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")


def manifest_value(target: str = "codex"):
    executable = Path("/bin/cat").resolve(strict=True)
    details = executable.stat()
    mapping = {
        "complete": True,
        "launch_argv": [str(executable)],
        "permission_declared": True,
        "permission_flags": [],
        "prompt_transport": "interactive_tmux_buffer_declared",
        "prompt_transport_declared": True,
        "sandbox_disable_declared": True,
        "sandbox_flags": [],
    }
    raw = {
        "schema_version": 1,
        "target": target,
        "generated_at": "2026-07-22T04:00:00Z",
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
        },
        "executable": {
            "requested_path": str(executable),
            "resolved_path": str(executable),
            "device": details.st_dev,
            "inode": details.st_ino,
            "size": details.st_size,
            "mtime_ns": details.st_mtime_ns,
            "sha256": sha256_file(executable),
            "version_sha256": "b" * 64,
            "help_sha256": "c" * 64,
        },
        "adapter_fingerprint": "d" * 64,
        "protocol_fingerprint": PROTOCOL_FINGERPRINT,
        "yolo_mapping": mapping,
        "capabilities": {
            name: "declared"
            for name in ("launch", "send", "status", "wait", "checkpoint", "resume", "halt")
        },
        "doctor_only": True,
        "qualification": None,
    }
    return raw, mapping


def static_process_identity(pid: int):
    executable = Path("/bin/cat").resolve(strict=True)
    details = executable.stat()
    return {
        "pid": pid,
        "start": "Wed Jul 22 04:00:00 2026",
        "command": "cat",
        "executable_path": str(executable),
        "device": details.st_dev,
        "inode": details.st_ino,
    }


def controller_inputs(root: Path, *, target: str = "codex", override=False):
    raw, mapping = manifest_value(target)
    manifest = root / "doctor.json"
    mapping_path = root / "mapping.json"
    authorization = root / "campaign.json"
    write_json(manifest, raw)
    write_json(mapping_path, mapping)
    goal_repo = root / "goal-repo"
    goal_repo.mkdir()
    subprocess.run(["git", "init", "-q", str(goal_repo)], check=True)
    subprocess.run(
        ["git", "-C", str(goal_repo), "config", "user.email", "test@example.invalid"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(goal_repo), "config", "user.name", "Puppet Test"],
        check=True,
    )
    goal_path = goal_repo / "plans" / "puppet" / "codex-goal.md"
    goal_path.parent.mkdir(parents=True)
    goal_path.write_text("bounded test goal\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(goal_repo), "add", "."], check=True)
    subprocess.run(
        ["git", "-C", str(goal_repo), "commit", "-q", "-m", "goal"],
        check=True,
    )
    goal_commit = subprocess.run(
        ["git", "-C", str(goal_repo), "rev-parse", "HEAD"],
        check=True,
        stdout=subprocess.PIPE,
        text=True,
    ).stdout.strip()
    expected_goal = {
        "repository": "test/SaariusSkills",
        "commit": goal_commit,
        "path": "plans/puppet/codex-goal.md",
        "sha256": sha256_file(goal_path),
    }
    authorization_value = {
        "schema_version": 1,
        "campaign_id": "campaign-probe-test",
        "operator_identity": "tester",
        "acknowledged_at": "2026-07-22T04:00:00Z",
        "controller": "tester",
        "goal": expected_goal,
        "authorization": {
            "trust_profile": "unrestricted_required",
            "harnesses": [target],
            "disable_harness_sandbox_where_exposed": True,
            "ordinary_configured_model_provider_traffic": True,
            "scope": "bounded Puppet implementation and conformance campaign only",
        },
        "allowed_actions": [
            "read",
            "test",
            "mutate_isolated_worktrees",
            "local_commit",
            "internal_between_session_promotion",
        ],
        "hard_gates": [
            "merge",
            "push",
            "pull_request_creation",
            "release",
            "deploy",
            "publish",
            "global_install",
            "external_send",
            "spend",
            "delete_or_archive",
            "account_or_security_change",
            "secret_or_auth_data_access",
            "interference_with_preexisting_processes_or_sessions",
        ],
    }
    if override:
        authorization_value["authorization"]["parallel_target_override"] = {
            "target": target,
            "isolation": "unique_private_tmux_socket_and_session",
            "failure_cleanup_scope": "exact_new_target_only",
            "protected_session": "%s-existing" % target,
            "protected_processes": [static_process_identity(991)],
        }
    write_json(authorization, authorization_value)
    proof = root / "proof"
    proof.mkdir()
    authority = root / "authority"
    authority.mkdir(mode=0o700)
    return {
        "manifest": manifest,
        "mapping": mapping_path,
        "authorization": authorization,
        "proof": proof,
        "authority": authority,
        "goal_repo": goal_repo,
        "expected_goal": expected_goal,
        "campaign_id": authorization_value["campaign_id"],
        "raw": raw,
    }


class FakeTmux:
    def __init__(
        self,
        root: Path,
        *,
        synthesize=True,
        die_after_initial=False,
        extra_handoff=False,
        exit_after_first_control=False,
        bad_claim=False,
        interrupt_on_paste=False,
        interrupt_after_control=False,
    ):
        self.root = root
        self.socket_root = Path(tempfile.mkdtemp(prefix="pft-", dir="/tmp"))
        self.synthesize = synthesize
        self.die_after_initial = die_after_initial
        self.extra_handoff = extra_handoff
        self.exit_after_first_control = exit_after_first_control
        self.bad_claim = bad_claim
        self.interrupt_on_paste = interrupt_on_paste
        self.interrupt_after_control = interrupt_after_control
        self.alive = True
        self.preserved = True
        self.launch_argv = None
        self.repo = None
        self.payloads = []
        self.interrupts = []
        self.control_calls = []
        self.session = None
        self.pane = "%7"
        self.pid = 4242
        self.server = None
        executable = Path("/bin/cat").resolve(strict=True)
        executable_details = executable.stat()
        self.tmux_identity = {
            "path": str(executable),
            "device": executable_details.st_dev,
            "inode": executable_details.st_ino,
            "uid": executable_details.st_uid,
            "gid": executable_details.st_gid,
            "mode": stat.S_IMODE(executable_details.st_mode),
            "size": executable_details.st_size,
            "sha256": sha256_file(executable),
            "version": "fake-tmux 1",
        }
        self.server_process = static_process_identity(4343)

    def socket_path(self, session):
        return self.socket_root / (session + ".sock")

    def __del__(self):
        try:
            if self.server is not None:
                self.server.close()
            if self.session is not None:
                self.socket_path(self.session).unlink(missing_ok=True)
            self.socket_root.rmdir()
        except (OSError, AttributeError):
            pass

    def socket_identity(self, socket):
        details = Path(socket).stat()
        return {
            "device": details.st_dev,
            "inode": details.st_ino,
            "uid": details.st_uid,
            "mode": stat.S_IMODE(details.st_mode),
        }

    def launch(self, *, session, repo, argv):
        self.session = session
        self.repo = Path(repo)
        self.launch_argv = list(argv)
        socket_path = self.socket_path(session)
        socket_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.server = socket_module.socket(socket_module.AF_UNIX, socket_module.SOCK_STREAM)
        self.server.bind(str(socket_path))
        os.chmod(socket_path, 0o600)
        return {
            "socket": str(socket_path),
            "socket_identity": self.socket_identity(socket_path),
            "session": session,
            "pane": self.pane,
            "pane_pid": self.pid,
            "current_command": "cat",
            "pane_dead": False,
            "server_identity": self.server_process,
            "tmux_binary_identity": self.tmux_identity,
        }

    def assert_tmux_binary_identity(self, expected):
        if expected != self.tmux_identity:
            raise IdentityError("fake tmux binary drift")

    def assert_tmux_server_identity(self, socket, expected):
        if expected != self.server_process:
            raise IdentityError("fake tmux server drift")

    def bind_server_identity(self, socket, expected):
        self.assert_tmux_server_identity(socket, expected)

    def tmux_binary_identity(self):
        return dict(self.tmux_identity)

    def metadata(self, *, socket, session, pane=None, server_identity=None):
        return {
            "session": session,
            "pane": self.pane,
            "pane_pid": self.pid,
            "current_command": "cat",
            "pane_dead": not self.alive,
        }

    def metadata_for_session(self, *, socket, session, server_identity=None):
        return self.metadata(
            socket=socket,
            session=session,
            pane=self.pane,
            server_identity=server_identity,
        )

    @staticmethod
    def _exact_json(payload: bytes, marker: str):
        text = payload.decode("utf-8")
        for line in text.splitlines():
            if line.startswith(marker):
                return json.loads(line[len(marker) :])
        raise AssertionError("probe payload did not contain %s" % marker)

    def paste_bytes(
        self, *, socket, session, pane, buffer_name, payload, server_identity=None
    ):
        if self.interrupt_on_paste:
            raise KeyboardInterrupt()
        self.payloads.append(bytes(payload))
        if self.die_after_initial and len(self.payloads) == 1:
            self.alive = False
            return
        if not self.synthesize:
            return
        if len(self.payloads) == 1:
            value = self._exact_json(payload, "WRITE_READY_JSON=")
            destination = self.repo / "handoffs" / "ready.json"
        else:
            value = self._exact_json(payload, "WRITE_FOLLOWUP_JSON=")
            destination = self.repo / "handoffs" / "followup.json"
        if self.bad_claim:
            value["claims"] = []
        temporary = destination.with_suffix(".pending")
        write_json(temporary, value)
        temporary.replace(destination)
        if self.extra_handoff:
            write_json(self.repo / "handoffs" / "unexpected.json", {"unexpected": True})

    def interrupt(self, *, socket, session, pane=None, server_identity=None):
        self.interrupts.append((str(socket), session, pane))
        self.alive = False

    def send_control(
        self, *, socket, session, pane=None, key, server_identity=None
    ):
        self.control_calls.append((str(socket), session, pane, key))
        if self.interrupt_after_control:
            raise KeyboardInterrupt()
        if self.exit_after_first_control or len(self.control_calls) >= 2:
            self.alive = False

    def exists(self, socket, session, *, server_identity=None):
        return self.preserved

    def attach_command(
        self, *, socket, session, pane=None, server_identity=None
    ):
        return "tmux -S %s attach-session -r -t %s" % (socket, session)


def process_identity(fake: FakeTmux):
    return static_process_identity(fake.pid)


def execute(
    files,
    fake,
    *,
    target="codex",
    run_id="probe-test-1",
    active=None,
    timeout=1.0,
    observed_manifest=None,
    process_birth_fn=None,
    continuous_population_fn=None,
    expected_goal=None,
):
    return run_probe(
        target=target,
        profile="source-free-pass-b-v1",
        proof_root=files["proof"],
        manifest_path=files["manifest"],
        mapping_path=files["mapping"],
        authorization_path=files["authorization"],
        controller="tester",
        goal_repo=files["goal_repo"],
        expected_campaign_id=files["campaign_id"],
        expected_goal=expected_goal or files["expected_goal"],
        timeout=timeout,
        halt_timeout=0.1,
        run_id=run_id,
        _tmux_factory=lambda root: fake,
        _process_birth_fn=process_birth_fn or (lambda pid: process_identity(fake)),
        _server_process_birth_fn=lambda pid: fake.server_process,
        _process_alive_fn=lambda identity: fake.alive,
        _active_processes_fn=lambda selected: list(active or []),
        _continuous_population_fn=continuous_population_fn
        or (
            lambda selected: [
                *list(active or []),
                *([process_identity(fake)] if fake.alive else []),
            ]
        ),
        _adapter_fingerprint_fn=lambda: files["raw"]["adapter_fingerprint"],
        _census_target_fn=lambda selected, fingerprint: AdapterManifest.from_dict(
            observed_manifest or files["raw"]
        ),
        _sleep_fn=lambda interval: None,
        _authority_root=files["authority"],
    )


class ProbeTests(unittest.TestCase):
    def test_success_emits_accepted_receipt_without_prompt_argv_and_preserves_tmux(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            files = controller_inputs(root)
            fake = FakeTmux(root / "fake-tmux")
            result = execute(files, fake)
            self.assertEqual(result["result"], "accepted")
            self.assertEqual(fake.launch_argv, files["raw"]["yolo_mapping"]["launch_argv"])
            launch_text = "\x00".join(fake.launch_argv)
            self.assertNotIn("PUPPET_REAL_HARNESS", launch_text)
            self.assertEqual(len(fake.payloads), 2)
            self.assertTrue(all(b"PUPPET_REAL_HARNESS" in item for item in fake.payloads))
            receipt = json.loads(Path(result["receipt"]).read_text(encoding="utf-8"))
            self.assertEqual(receipt["capabilities"], list(PROBE_CAPABILITIES))
            self.assertNotIn("resume", receipt["capabilities"])
            halt = json.loads(
                (Path(result["run_root"]) / "halt.json").read_text(encoding="utf-8")
            )
            self.assertTrue(halt["tmux_preserved"])
            self.assertFalse(fake.alive)
            self.assertTrue(fake.preserved)
            self.assertEqual(len(fake.interrupts), 1)

    def test_accepted_receipt_qualifies_probe_capabilities_but_not_resume(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            files = controller_inputs(root)
            fake = FakeTmux(root / "fake-tmux")
            result = execute(files, fake, run_id="probe-test-qualify")
            receipt = json.loads(Path(result["receipt"]).read_text(encoding="utf-8"))
            raw = dict(files["raw"])
            raw["doctor_only"] = False
            raw["qualification"] = {
                "receipt_path": result["receipt"],
                "receipt_sha256": sha256_file(Path(result["receipt"])),
            }
            raw["capabilities"] = {
                name: "controller_verified" if name in receipt["capabilities"] else "unsupported"
                for name in raw["capabilities"]
            }
            manifest = AdapterManifest.from_dict(raw)
            self.assertEqual(manifest.raw["capabilities"]["resume"], "unsupported")
            self.assertEqual(
                manifest.verify_qualification(
                    _authority_root=files["authority"],
                    _current_manifest=AdapterManifest.from_dict(files["raw"]),
                    _server_process_fn=lambda pid: fake.server_process,
                    _tmux_factory=lambda root: fake,
                )["result"],
                "accepted",
            )

    def test_active_same_target_blocks_without_exact_override(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            files = controller_inputs(root)
            fake = FakeTmux(root / "fake-tmux")
            with self.assertRaises(ConflictError):
                execute(
                    files,
                    fake,
                    active=[static_process_identity(991)],
                    run_id="probe-blocked",
                )
            self.assertIsNone(fake.launch_argv)
            state = json.loads(
                (files["proof"] / "probes" / "probe-blocked" / "state.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(state["phase"], "failed")

    def test_fresh_zero_agent_census_drift_blocks_before_launch(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            files = controller_inputs(root)
            fake = FakeTmux(root / "fake-tmux")
            observed = json.loads(json.dumps(files["raw"]))
            observed["executable"]["version_sha256"] = "f" * 64
            with self.assertRaisesRegex(IdentityError, "fresh zero-agent census"):
                execute(
                    files,
                    fake,
                    run_id="probe-census-drift",
                    observed_manifest=observed,
                )
            self.assertIsNone(fake.launch_argv)

    def test_authorized_controller_identity_is_exact(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            files = controller_inputs(root)
            authorization = json.loads(files["authorization"].read_text(encoding="utf-8"))
            authorization["controller"] = "other-controller"
            write_json(files["authorization"], authorization)
            fake = FakeTmux(root / "fake-tmux")
            with self.assertRaisesRegex(IdentityError, "controller identity mismatch"):
                execute(files, fake, run_id="probe-controller-mismatch")
            self.assertIsNone(fake.launch_argv)

    def test_parallel_override_must_match_exact_protected_process_set(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            files = controller_inputs(root, override=True)
            fake = FakeTmux(root / "fake-tmux")
            with self.assertRaises(ConflictError):
                execute(
                    files,
                    fake,
                    active=[static_process_identity(992)],
                    run_id="probe-protected-process-mismatch",
                )
            self.assertIsNone(fake.launch_argv)

    def test_exact_parallel_override_allows_unique_private_probe(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            files = controller_inputs(root, override=True)
            fake = FakeTmux(root / "fake-tmux")
            protected = static_process_identity(991)
            result = execute(
                files, fake, active=[protected], run_id="probe-parallel"
            )
            self.assertEqual(result["result"], "accepted")
            evidence = json.loads(
                (Path(result["run_root"]) / "evidence.json").read_text(encoding="utf-8")
            )
            self.assertTrue(evidence["parallel_target_override"])
            self.assertEqual(
                evidence["active_target_processes_before_launch"], [protected]
            )
            self.assertEqual(
                evidence["active_target_processes_after_halt"], [protected]
            )
            self.assertEqual(evidence["protected_session"], "codex-existing")
            self.assertNotEqual(fake.session, evidence["protected_session"])

    def test_timeout_cleans_only_exact_new_target_and_keeps_dead_pane(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            files = controller_inputs(root)
            fake = FakeTmux(root / "fake-tmux", synthesize=False)
            with self.assertRaisesRegex(ValidationError, "timed out"):
                execute(files, fake, run_id="probe-timeout", timeout=0.001)
            self.assertEqual(len(fake.interrupts), 1)
            self.assertEqual(fake.interrupts[0][1], fake.session)
            halt = json.loads(
                (
                    files["proof"]
                    / "probes"
                    / "probe-timeout"
                    / "halt.json"
                ).read_text(encoding="utf-8")
            )
            self.assertEqual(halt["cleanup_scope"], "exact_new_target_only")
            self.assertTrue(halt["tmux_preserved"])

    def test_dead_target_failure_preserves_tmux_without_signaling_other_processes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            files = controller_inputs(root)
            fake = FakeTmux(root / "fake-tmux", synthesize=False, die_after_initial=True)
            with self.assertRaisesRegex(IdentityError, "stopped"):
                execute(files, fake, run_id="probe-dead")
            self.assertEqual(fake.interrupts, [])
            halt = json.loads(
                (
                    files["proof"] / "probes" / "probe-dead" / "halt.json"
                ).read_text(encoding="utf-8")
            )
            self.assertEqual(halt["signal"], "none_already_stopped")
            self.assertTrue(halt["tmux_preserved"])

    def test_agy_uses_exact_double_eof_graceful_halt(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            files = controller_inputs(root, target="agy")
            fake = FakeTmux(root / "fake-tmux")
            result = execute(
                files, fake, target="agy", run_id="probe-agy-double-eof"
            )
            self.assertEqual(result["result"], "accepted")
            self.assertEqual(fake.interrupts, [])
            self.assertEqual(len(fake.control_calls), 2)
            self.assertEqual([item[3] for item in fake.control_calls], ["C-d", "C-d"])
            halt = json.loads(
                (Path(result["run_root"]) / "halt.json").read_text(encoding="utf-8")
            )
            self.assertEqual(halt["signal"], "tmux_exact_pane_ctrl_d_twice")

    def test_agy_does_not_send_second_eof_after_exact_target_stops(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            files = controller_inputs(root, target="agy")
            fake = FakeTmux(root / "fake-tmux", exit_after_first_control=True)
            result = execute(files, fake, target="agy", run_id="probe-agy-one-eof")
            self.assertEqual(result["result"], "accepted")
            self.assertEqual(len(fake.control_calls), 1)
            halt = json.loads(
                (Path(result["run_root"]) / "halt.json").read_text(encoding="utf-8")
            )
            self.assertEqual(halt["signal"], "tmux_exact_pane_ctrl_d_once_target_stopped")

    def test_unexpected_handoff_artifact_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            files = controller_inputs(root)
            fake = FakeTmux(root / "fake-tmux", extra_handoff=True)
            with self.assertRaisesRegex(IdentityError, "unexpected artifacts"):
                execute(files, fake, run_id="probe-extra-handoff")
            self.assertFalse(fake.alive)

    def test_semantically_changed_handoff_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            files = controller_inputs(root)
            fake = FakeTmux(root / "fake-tmux", bad_claim=True)
            with self.assertRaisesRegex(IdentityError, "exact contract"):
                execute(files, fake, run_id="probe-bad-claim")
            self.assertFalse(fake.alive)

    def test_process_must_execute_the_fingerprinted_launcher(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            files = controller_inputs(root)
            fake = FakeTmux(root / "fake-tmux")
            different = Path("/bin/echo").resolve(strict=True)
            details = different.stat()
            wrong_process = dict(
                static_process_identity(fake.pid),
                executable_path=str(different),
                device=details.st_dev,
                inode=details.st_ino,
            )
            with self.assertRaisesRegex(IdentityError, "fingerprinted launcher"):
                execute(
                    files,
                    fake,
                    run_id="probe-process-mismatch",
                    process_birth_fn=lambda pid: wrong_process,
                )
            self.assertFalse(fake.alive)

    def test_process_birth_failure_cleans_the_exact_private_pane(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            files = controller_inputs(root)
            fake = FakeTmux(root / "fake-tmux")

            def unavailable(pid):
                raise IdentityError("process birth unavailable")

            with self.assertRaisesRegex(IdentityError, "process birth unavailable"):
                execute(
                    files,
                    fake,
                    run_id="probe-process-birth-failure",
                    process_birth_fn=unavailable,
                )
            self.assertFalse(fake.alive)
            halt = json.loads(
                (
                    files["proof"]
                    / "probes"
                    / "probe-process-birth-failure"
                    / "halt.json"
                ).read_text(encoding="utf-8")
            )
            self.assertEqual(halt["identity_binding"], "new_private_tmux_pane")

    def test_keyboard_interrupt_still_cleans_the_exact_new_target(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            files = controller_inputs(root)
            fake = FakeTmux(root / "fake-tmux", interrupt_on_paste=True)
            with self.assertRaises(KeyboardInterrupt):
                execute(files, fake, run_id="probe-keyboard-interrupt")
            self.assertFalse(fake.alive)

    def test_campaign_lock_serializes_real_harness_probes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            files = controller_inputs(root)
            fake = FakeTmux(root / "fake-tmux")
            descriptor, _ = _acquire_campaign_probe_lock(files["authority"])
            try:
                with self.assertRaisesRegex(ConflictError, "campaign lock"):
                    execute(files, fake, run_id="probe-lock-conflict")
            finally:
                _release_campaign_probe_lock(descriptor)
            self.assertIsNone(fake.launch_argv)

    def test_normal_session_lease_blocks_probe_across_proof_roots(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            files = controller_inputs(root)
            fake = FakeTmux(root / "fake-tmux")
            admit_session_lease(
                session="other-live-session",
                target="codex",
                controller="other-controller",
                owner={
                    "activity": "session",
                    "run_id": "other-live-run",
                    "campaign_id": files["campaign_id"],
                    "goal_fingerprint": sha256_bytes(
                        canonical_json_bytes(files["expected_goal"])
                    ),
                    "proof_root": str(files["proof"]),
                },
                authority_root=files["authority"],
            )
            with self.assertRaisesRegex(ConflictError, "controller lease"):
                execute(files, fake, run_id="probe-normal-lease-conflict")
            self.assertIsNone(fake.launch_argv)

    def test_receipt_rejects_mutated_bound_artifact(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            files = controller_inputs(root)
            fake = FakeTmux(root / "fake-tmux")
            result = execute(files, fake, run_id="probe-receipt-tamper")
            receipt_path = Path(result["receipt"])
            receipt = verify_qualification_receipt(
                receipt_path,
                _authority_root=files["authority"],
                _current_manifest=AdapterManifest.from_dict(files["raw"]),
                _server_process_fn=lambda pid: fake.server_process,
                _tmux_factory=lambda selected: fake,
            )
            evidence_ref = next(
                item for item in receipt["proof_refs"] if item["kind"] == "evidence"
            )
            evidence_path = receipt_path.parent / evidence_ref["path"]
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            evidence["result"] = "mutated"
            write_json(evidence_path, evidence)
            with self.assertRaisesRegex(ValidationError, "fingerprint changed"):
                verify_qualification_receipt(
                    receipt_path,
                    _authority_root=files["authority"],
                    _current_manifest=AdapterManifest.from_dict(files["raw"]),
                    _server_process_fn=lambda pid: fake.server_process,
                    _tmux_factory=lambda selected: fake,
                )

    def test_receipt_cannot_upgrade_resume_without_a_separate_contract(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            files = controller_inputs(root)
            fake = FakeTmux(root / "fake-tmux")
            result = execute(files, fake, run_id="probe-resume-upgrade")
            receipt_path = Path(result["receipt"])
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            receipt["capabilities"].insert(-1, "resume")
            write_json(receipt_path, receipt)
            with self.assertRaisesRegex(ValidationError, "capability receipt"):
                verify_qualification_receipt(
                    receipt_path,
                    _authority_root=files["authority"],
                    _current_manifest=AdapterManifest.from_dict(files["raw"]),
                    _server_process_fn=lambda pid: fake.server_process,
                    _tmux_factory=lambda selected: fake,
                )

    def test_terminal_state_mutation_invalidates_an_attested_receipt(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            files = controller_inputs(root)
            fake = FakeTmux(root / "fake-tmux")
            result = execute(files, fake, run_id="probe-terminal-state")
            receipt_path = Path(result["receipt"])
            state_path = Path(result["run_root"]) / "state.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["phase"] = "failed"
            state["result"] = "failed"
            write_json(state_path, state)
            with self.assertRaisesRegex(ValidationError, "terminal lifecycle"):
                verify_qualification_receipt(
                    receipt_path,
                    _authority_root=files["authority"],
                    _current_manifest=AdapterManifest.from_dict(files["raw"]),
                    _server_process_fn=lambda pid: fake.server_process,
                    _tmux_factory=lambda selected: fake,
                )

    def test_current_controller_identity_drift_invalidates_qualification(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            files = controller_inputs(root)
            fake = FakeTmux(root / "fake-tmux")
            result = execute(files, fake, run_id="probe-current-drift")
            drifted = json.loads(json.dumps(files["raw"]))
            drifted["adapter_fingerprint"] = "f" * 64
            with self.assertRaisesRegex(IdentityError, "current controller"):
                verify_qualification_receipt(
                    Path(result["receipt"]),
                    _authority_root=files["authority"],
                    _current_manifest=AdapterManifest.from_dict(drifted),
                    _server_process_fn=lambda pid: fake.server_process,
                    _tmux_factory=lambda selected: fake,
                )

    def test_terminal_tmux_pane_drift_invalidates_qualification(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            files = controller_inputs(root)
            fake = FakeTmux(root / "fake-tmux")
            result = execute(files, fake, run_id="probe-pane-drift")
            fake.pane = "%99"
            with self.assertRaisesRegex(ValidationError, "terminal tmux identity"):
                verify_qualification_receipt(
                    Path(result["receipt"]),
                    _authority_root=files["authority"],
                    _current_manifest=AdapterManifest.from_dict(files["raw"]),
                    _server_process_fn=lambda pid: fake.server_process,
                    _tmux_factory=lambda selected: fake,
                )

    def test_qualified_manifest_is_bound_to_campaign_controller_and_goal(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            files = controller_inputs(root)
            fake = FakeTmux(root / "fake-tmux")
            result = execute(files, fake, run_id="probe-authority-binding")
            receipt = json.loads(Path(result["receipt"]).read_text(encoding="utf-8"))
            raw = json.loads(json.dumps(files["raw"]))
            raw["doctor_only"] = False
            raw["qualification"] = {
                "receipt_path": result["receipt"],
                "receipt_sha256": sha256_file(Path(result["receipt"])),
            }
            raw["capabilities"] = {
                name: (
                    "controller_verified"
                    if name in receipt["capabilities"]
                    else "unsupported"
                )
                for name in raw["capabilities"]
            }
            manifest = AdapterManifest.from_dict(raw)
            common = {
                "expected_campaign_id": files["campaign_id"],
                "expected_goal_fingerprint": sha256_bytes(
                    canonical_json_bytes(files["expected_goal"])
                ),
                "_authority_root": files["authority"],
                "_current_manifest": AdapterManifest.from_dict(files["raw"]),
                "_server_process_fn": lambda pid: fake.server_process,
                "_tmux_factory": lambda selected: fake,
            }
            with self.assertRaisesRegex(IdentityError, "active campaign"):
                manifest.verify_qualification(
                    expected_controller="other-controller",
                    **common,
                )
            with self.assertRaisesRegex(IdentityError, "active campaign"):
                manifest.verify_qualification(
                    expected_controller="tester",
                    **dict(common, expected_goal_fingerprint="0" * 64),
                )

    def test_transient_same_target_process_invalidates_probe(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            files = controller_inputs(root)
            fake = FakeTmux(root / "fake-tmux")
            calls = {"count": 0}

            def population(selected):
                calls["count"] += 1
                baseline = [process_identity(fake)] if fake.alive else []
                if calls["count"] == 3:
                    baseline.append(static_process_identity(4999))
                return baseline

            with self.assertRaisesRegex(IdentityError, "population changed"):
                execute(
                    files,
                    fake,
                    run_id="probe-transient-process",
                    continuous_population_fn=population,
                )
            self.assertFalse(fake.alive)
            self.assertFalse(
                (
                    files["proof"]
                    / "probes"
                    / "probe-transient-process"
                    / "receipt.json"
                ).exists()
            )

    def test_unverified_goal_tuple_fails_before_tmux_launch(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            files = controller_inputs(root)
            fake = FakeTmux(root / "fake-tmux")
            wrong_goal = dict(files["expected_goal"], sha256="f" * 64)
            with self.assertRaisesRegex(IdentityError, "goal identity"):
                execute(
                    files,
                    fake,
                    run_id="probe-goal-mismatch",
                    expected_goal=wrong_goal,
                )
            self.assertIsNone(fake.launch_argv)

    def test_interrupted_probe_recovery_halts_exact_target_without_relaunch(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            files = controller_inputs(root)
            fake = FakeTmux(root / "fake-tmux")
            with patch(
                "puppet_lib.probe._halt_exact",
                side_effect=KeyboardInterrupt(),
            ):
                with self.assertRaises(KeyboardInterrupt):
                    execute(files, fake, run_id="probe-recovery")
            original_launch_argv = list(fake.launch_argv)
            run_root = files["proof"] / "probes" / "probe-recovery"
            state_path = run_root / "state.json"
            with self.assertRaises(ConflictError):
                admit_session_lease(
                    session="other-during-recovery",
                    target="codex",
                    controller="other-controller",
                    owner={
                        "activity": "session",
                        "run_id": "other-during-recovery",
                        "campaign_id": files["campaign_id"],
                        "goal_fingerprint": sha256_bytes(
                            canonical_json_bytes(files["expected_goal"])
                        ),
                        "proof_root": str(files["proof"]),
                    },
                    authority_root=files["authority"],
                )
            recovered = recover_probe(
                target="codex",
                proof_root=files["proof"],
                manifest_path=files["manifest"],
                mapping_path=files["mapping"],
                authorization_path=files["authorization"],
                controller="tester",
                goal_repo=files["goal_repo"],
                expected_campaign_id=files["campaign_id"],
                expected_goal=files["expected_goal"],
                run_id="probe-recovery",
                halt_timeout=0.1,
                _tmux_factory=lambda selected: fake,
                _process_birth_fn=lambda pid: process_identity(fake),
                _process_alive_fn=lambda identity: fake.alive,
                _server_process_birth_fn=lambda pid: fake.server_process,
                _active_processes_fn=lambda selected: [],
                _adapter_fingerprint_fn=lambda: files["raw"]["adapter_fingerprint"],
                _census_target_fn=lambda selected, fingerprint: AdapterManifest.from_dict(
                    files["raw"]
                ),
                _sleep_fn=lambda interval: None,
                _authority_root=files["authority"],
            )
            self.assertTrue(recovered["recovered"])
            self.assertEqual(recovered["result"], "interrupted_probe_reconciled")
            self.assertEqual(fake.launch_argv, original_launch_argv)
            self.assertEqual(len(fake.interrupts), 1)
            self.assertFalse(fake.alive)
            terminal = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(terminal["phase"], "failed")
            self.assertTrue((run_root / "recovery.json").is_file())

    def test_interrupted_agy_eof_is_ambiguous_and_never_resent(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            files = controller_inputs(root, target="agy")
            fake = FakeTmux(root / "fake-tmux", interrupt_after_control=True)
            with self.assertRaises(KeyboardInterrupt):
                execute(files, fake, target="agy", run_id="probe-agy-ambiguous")
            self.assertEqual(len(fake.control_calls), 1)
            fake.interrupt_after_control = False
            with self.assertRaisesRegex(IdentityError, "ambiguous"):
                recover_probe(
                    target="agy",
                    proof_root=files["proof"],
                    manifest_path=files["manifest"],
                    mapping_path=files["mapping"],
                    authorization_path=files["authorization"],
                    controller="tester",
                    goal_repo=files["goal_repo"],
                    expected_campaign_id=files["campaign_id"],
                    expected_goal=files["expected_goal"],
                    run_id="probe-agy-ambiguous",
                    halt_timeout=0.1,
                    _tmux_factory=lambda selected: fake,
                    _process_birth_fn=lambda pid: process_identity(fake),
                    _process_alive_fn=lambda identity: fake.alive,
                    _server_process_birth_fn=lambda pid: fake.server_process,
                    _active_processes_fn=lambda selected: [process_identity(fake)],
                    _adapter_fingerprint_fn=lambda: files["raw"]["adapter_fingerprint"],
                    _census_target_fn=lambda selected, fingerprint: AdapterManifest.from_dict(
                        files["raw"]
                    ),
                    _sleep_fn=lambda interval: None,
                    _authority_root=files["authority"],
                )
            self.assertEqual(len(fake.control_calls), 1)

    def test_probe_profile_is_fixed_before_launch(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            files = controller_inputs(root)
            fake = FakeTmux(root / "fake-tmux")
            with self.assertRaisesRegex(ValidationError, "fixed source-free Pass B"):
                run_probe(
                    target="codex",
                    profile="arbitrary",
                    proof_root=files["proof"],
                    manifest_path=files["manifest"],
                    mapping_path=files["mapping"],
                    authorization_path=files["authorization"],
                    controller="tester",
                    goal_repo=files["goal_repo"],
                    expected_campaign_id=files["campaign_id"],
                    expected_goal=files["expected_goal"],
                    _tmux_factory=lambda selected: fake,
                )
            self.assertIsNone(fake.launch_argv)


if __name__ == "__main__":
    unittest.main()
