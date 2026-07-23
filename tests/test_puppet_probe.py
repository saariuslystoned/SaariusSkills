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

import puppet_lib.probe as puppet_probe  # noqa: E402
from puppet_lib.adapters import adapter_for  # noqa: E402
from puppet_lib.adapter_manifest import (  # noqa: E402
    ADAPTER_MANIFEST_SCHEMA_VERSION,
    AdapterManifest,
    PROBE_CAPABILITIES,
    _validate_ancestry_node_coherence,
    _validated_ancestry_chain,
    build_execution_bundle,
    direct_execution_bundle,
    execution_file_identity,
    verify_qualification_receipt,
)
from puppet_lib.authority import (  # noqa: E402
    admit_session_lease,
    current_session_lease,
    transition_session_lease,
)
from puppet_lib.errors import ConflictError, IdentityError, ValidationError  # noqa: E402
from puppet_lib.halt_control import deliver_halt_actions  # noqa: E402
from puppet_lib.handoffs import PROTOCOL_FINGERPRINT  # noqa: E402
from puppet_lib.journal import Journal  # noqa: E402
from puppet_lib.launch import public_launch_identity  # noqa: E402
from puppet_lib.plane_activation import CLAUDE_NATIVE_TRIGGER  # noqa: E402
from puppet_lib.census import adapter_implementation_fingerprint  # noqa: E402
from puppet_lib.probe import (  # noqa: E402
    PROBE_PROFILE,
    _acquire_campaign_probe_lock,
    _release_campaign_probe_lock,
    _validated_target_population,
    recover_probe,
    run_probe,
)
from puppet_lib.contracts import TARGET_POPULATION_POLICY  # noqa: E402
from puppet_lib.profiles import (  # noqa: E402
    PROMPT_TRANSPORT,
    SUBMIT_SETTLE_SECONDS,
    default_session_profile,
    session_profiles_for,
    startup_settle_seconds_for,
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
    permission_flags = []
    project_isolation_flags = []
    if target == "agy":
        permission_flags = ["--dangerously-skip-permissions"]
        project_isolation_flags = ["--new-project"]
    mapping = {
        "complete": True,
        "launch_argv": (
            [str(executable)]
            + ([] if target == "agy" else ["-"])
            + permission_flags
            + project_isolation_flags
        ),
        "permission_declared": True,
        "permission_flags": permission_flags,
        "prompt_transport": PROMPT_TRANSPORT,
        "prompt_transport_declared": True,
        "sandbox_disable_declared": True,
        "sandbox_flags": [],
        "project_isolation_declared": True,
        "project_isolation_flags": project_isolation_flags,
        "session_profiles": session_profiles_for(target),
        "session_profiles_declared": True,
        "startup_settle_seconds": startup_settle_seconds_for(target),
        "submit_settle_seconds": SUBMIT_SETTLE_SECONDS,
    }
    executable_identity = {
        "requested_path": str(executable),
        "resolved_path": str(executable),
        "device": details.st_dev,
        "inode": details.st_ino,
        "size": details.st_size,
        "mtime_ns": details.st_mtime_ns,
        "sha256": sha256_file(executable),
        "version_sha256": "b" * 64,
        "help_sha256": "c" * 64,
    }
    raw = {
        "schema_version": ADAPTER_MANIFEST_SCHEMA_VERSION,
        "target": target,
        "generated_at": "2026-07-22T04:00:00Z",
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
        },
        "executable": executable_identity,
        "execution": direct_execution_bundle(executable_identity),
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
    return raw, mapping


def static_process_identity(pid: int):
    executable = Path("/bin/cat").resolve(strict=True)
    details = executable.stat()
    return {
        "identity_version": 2,
        "pid": pid,
        "start": "Wed Jul 22 04:00:00 2026",
        "kernel_birth_id": "test:%d" % pid,
        "command": "cat",
        "executable_path": str(executable),
        "device": details.st_dev,
        "inode": details.st_ino,
    }


def process_tree_node(process, parent_pid):
    return {"process": process, "parent_pid": parent_pid}


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


def claude_activation_inputs(root: Path):
    files = controller_inputs(root, target="claude")
    raw = files["raw"]
    raw["adapter_fingerprint"] = adapter_implementation_fingerprint()
    raw["executable"]["version_sha256"] = (
        "3c95eff850dac10d40c5692a73957f526b54a74767163913dc858c4f8d4c8c63"
    )
    mapping = {
        "complete": False,
        "launch_argv": [
            raw["executable"]["resolved_path"],
            "--dangerously-skip-permissions",
        ],
        "permission_declared": True,
        "permission_flags": ["--dangerously-skip-permissions"],
        "prompt_transport": PROMPT_TRANSPORT,
        "prompt_transport_declared": True,
        "sandbox_disable_declared": True,
        "sandbox_flags": [],
        "project_isolation_declared": False,
        "project_isolation_flags": [],
        "session_profiles": session_profiles_for("claude"),
        "session_profiles_declared": True,
        "startup_settle_seconds": startup_settle_seconds_for("claude"),
        "submit_settle_seconds": SUBMIT_SETTLE_SECONDS,
        "model_flag": "--model",
        "effort_flag": "--effort",
    }
    raw["yolo_mapping"] = mapping
    write_json(files["manifest"], raw)
    write_json(files["mapping"], mapping)
    descriptor = {
        "schema": "puppet.instruction-plane/v1",
        "descriptor_id": "claude-native-qualification",
        "target": {
            "harness": "claude",
            "version": "2.1.215",
            "adapter_manifest_sha256": AdapterManifest.from_dict(raw).fingerprint,
            "requested_model": "default",
            "observed_model": "unavailable",
            "config_fingerprint": "unavailable",
        },
        "plane": "per_run_additive",
        "status": {
            "surface": "factual",
            "activation": "qualification_only",
        },
        "materialize": [
            {
                "artifact_id": "effective_contract_file",
                "root_ref": "ephemeral_root",
                "relative_path": "puppet-instructions.md",
                "content_ref": "effective_contract",
                "write_mode": "create_only",
            }
        ],
        "launch_delta": {
            "cwd_ref": "workspace_root",
            "env": [
                {
                    "name": "CLAUDE_CONFIG_DIR",
                    "value_ref": "config_root_path",
                },
                {
                    "name": "CLAUDE_CODE_DISABLE_AUTO_MEMORY",
                    "value_ref": "true_literal",
                },
            ],
            "argv": [
                {"literal": "--append-system-prompt-file"},
                {"path_ref": "effective_contract_file"},
            ],
        },
        "rollback": {
            "owned_artifacts": ["effective_contract_file"],
            "preimage_sha256": [],
            "retain_hash_only_proof": True,
        },
        "assertions": ["claude_native_instruction_seen"],
        "blockers": ["matched_no_bleed_not_yet_proven"],
    }
    descriptor_path = root / "claude-plane.json"
    write_json(descriptor_path, descriptor)
    files.update(raw=raw, descriptor=descriptor_path)
    return files


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
        terminal_pid_drift=False,
        regular_socket=False,
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
        self.terminal_pid_drift = terminal_pid_drift
        self.regular_socket = regular_socket
        self.alive = True
        self.preserved = True
        self.launch_argv = None
        self.launch_environment = None
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

    def launch(
        self,
        *,
        session,
        target,
        repo,
        argv,
        environment,
        admitted_lane_root=None,
        before_start=None,
        before_target_start=None,
    ):
        if before_start is not None:
            before_start()
        self.session = session
        self.repo = Path(repo)
        self.launch_argv = list(argv)
        self.launch_environment = dict(environment)
        socket_path = self.socket_path(session)
        socket_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.regular_socket:
            socket_path.touch(mode=0o600)
        else:
            self.server = socket_module.socket(
                socket_module.AF_UNIX, socket_module.SOCK_STREAM
            )
            self.server.bind(str(socket_path))
        os.chmod(socket_path, 0o600)
        if before_target_start is not None:
            refreshed = before_target_start()
            self.launch_argv = list(refreshed.argv)
            self.launch_environment = dict(refreshed.environment)
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
            "launch_identity": public_launch_identity(
                repo=self.repo,
                argv=self.launch_argv,
                environment=self.launch_environment,
                admitted_lane_root=admitted_lane_root,
            ),
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
            "pane_pid": (
                self.pid + 1 if self.terminal_pid_drift and not self.alive else self.pid
            ),
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
            instruction_payload = payload
            if payload == (CLAUDE_NATIVE_TRIGGER + "\n").encode("utf-8"):
                artifact_flag = self.launch_argv.index("--append-system-prompt-file")
                instruction_payload = Path(
                    self.launch_argv[artifact_flag + 1]
                ).read_bytes()
            value = self._exact_json(instruction_payload, "WRITE_READY_JSON=")
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

    def exact_sigint(self, identity):
        self.interrupts.append(("exact_pid_sigint", identity["pid"], None))
        self.alive = False

    def send_control(
        self,
        *,
        socket,
        session,
        pane=None,
        key,
        server_identity=None,
        expected_pane_pid=None,
    ):
        if expected_pane_pid is not None and expected_pane_pid != self.pid:
            raise IdentityError("fake pane process drift")
        self.control_calls.append((str(socket), session, pane, key))
        if self.interrupt_after_control:
            raise KeyboardInterrupt()
        if self.exit_after_first_control or len(self.control_calls) >= 2:
            self.alive = False

    def exists(self, socket, session, *, server_identity=None):
        return self.preserved

    def attach_command(self, *, socket, session, pane=None, server_identity=None):
        return "tmux -f %s -S %s attach-session -r -E -t %s" % (
            os.devnull,
            socket,
            session,
        )


def process_identity(fake: FakeTmux):
    return static_process_identity(fake.pid)


def execute(
    files,
    fake,
    *,
    target="codex",
    session_profile=None,
    run_id="probe-test-1",
    active=None,
    timeout=1.0,
    observed_manifest=None,
    process_birth_fn=None,
    continuous_population_fn=None,
    population_snapshot_fn=None,
    active_processes_fn=None,
    expected_goal=None,
    sleep_fn=None,
    plane_descriptor=None,
):
    return run_probe(
        target=target,
        profile=PROBE_PROFILE,
        session_profile=(
            default_session_profile(target)
            if session_profile is None
            else session_profile
        ),
        proof_root=files["proof"],
        manifest_path=files["manifest"],
        mapping_path=files["mapping"],
        authorization_path=files["authorization"],
        controller="tester",
        goal_repo=files["goal_repo"],
        expected_campaign_id=files["campaign_id"],
        expected_goal=expected_goal or files["expected_goal"],
        plane_descriptor=plane_descriptor,
        timeout=timeout,
        halt_timeout=0.1,
        run_id=run_id,
        _tmux_factory=lambda root: fake,
        _process_birth_fn=process_birth_fn or (lambda pid: process_identity(fake)),
        _server_process_birth_fn=lambda pid: fake.server_process,
        _process_alive_fn=lambda identity: fake.alive,
        _process_tree_alive_fn=lambda identity: fake.alive,
        _exact_sigint_fn=fake.exact_sigint,
        _active_processes_fn=active_processes_fn
        or (lambda selected: list(active or [])),
        _continuous_population_fn=continuous_population_fn
        or (
            lambda selected: [
                *list(active or []),
                *([process_identity(fake)] if fake.alive else []),
            ]
        ),
        _population_snapshot_fn=population_snapshot_fn,
        _adapter_fingerprint_fn=lambda: files["raw"]["adapter_fingerprint"],
        _census_target_fn=lambda selected, fingerprint: AdapterManifest.from_dict(
            observed_manifest or files["raw"]
        ),
        _sleep_fn=sleep_fn or (lambda interval: None),
        _execution_sleep_fn=lambda interval: None,
        _authority_root=files["authority"],
    )


def recover_execute(files, *, run_id, tmux_factory=None, plane_descriptor=None):
    return recover_probe(
        target="claude",
        proof_root=files["proof"],
        manifest_path=files["manifest"],
        mapping_path=files["mapping"],
        authorization_path=files["authorization"],
        controller="tester",
        goal_repo=files["goal_repo"],
        expected_campaign_id=files["campaign_id"],
        expected_goal=files["expected_goal"],
        run_id=run_id,
        plane_descriptor=plane_descriptor,
        halt_timeout=0.1,
        _tmux_factory=tmux_factory or (lambda root: FakeTmux(root)),
        _process_alive_fn=lambda identity: False,
        _active_processes_fn=lambda selected: [],
        _adapter_fingerprint_fn=lambda: files["raw"]["adapter_fingerprint"],
        _census_target_fn=lambda selected, fingerprint: AdapterManifest.from_dict(
            files["raw"]
        ),
        _sleep_fn=lambda interval: None,
        _authority_root=files["authority"],
    )


class ProbeTests(unittest.TestCase):
    def test_incomplete_claude_mapping_requires_plane_descriptor(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            files = claude_activation_inputs(root)
            fake = FakeTmux(root / "fake-tmux", regular_socket=True)
            with self.assertRaisesRegex(ValidationError, "mapping is incomplete"):
                execute(
                    files,
                    fake,
                    target="claude",
                    run_id="probe-claude-no-descriptor",
                )
            self.assertIsNone(fake.launch_argv)

    def test_claude_activation_uses_native_trigger_and_rolls_back_before_receipt(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            files = claude_activation_inputs(root)
            fake = FakeTmux(root / "fake-tmux", regular_socket=True)
            run_id = "probe-claude-native"
            revalidate = puppet_probe.revalidate_activation_launch_context
            with (
                patch.object(
                    puppet_probe,
                    "revalidate_activation_launch_context",
                    wraps=revalidate,
                ) as revalidate_call,
                patch.object(
                    puppet_probe,
                    "verify_qualification_receipt",
                    return_value={},
                ),
            ):
                result = execute(
                    files,
                    fake,
                    target="claude",
                    run_id=run_id,
                    plane_descriptor=files["descriptor"],
                )
            self.assertEqual(result["result"], "accepted")
            self.assertEqual(revalidate_call.call_count, 1)
            self.assertEqual(
                fake.payloads[0],
                (CLAUDE_NATIVE_TRIGGER + "\n").encode("utf-8"),
            )
            run_root = files["proof"] / "probes" / run_id
            evidence = json.loads(
                (run_root / "evidence.json").read_text(encoding="utf-8")
            )
            receipt = json.loads(
                (run_root / "receipt.json").read_text(encoding="utf-8")
            )
            activation = evidence["plane_activation"]
            self.assertIsNone(evidence["failure"])
            self.assertEqual(
                activation["qualification_scope"], "activation_lifecycle_only"
            )
            self.assertEqual(activation, receipt["plane_activation"])
            self.assertNotEqual(
                activation["initial_trigger_sha256"],
                activation["artifact_sha256"],
            )
            self.assertEqual(
                {reference["kind"] for reference in receipt["proof_refs"]}
                - {
                    "authorization",
                    "evidence",
                    "launch_plan",
                    "instructions",
                    "halt",
                    "ready",
                    "followup",
                    "review",
                    "acceptance",
                },
                {
                    "plane_descriptor",
                    "activation_intent",
                    "activation_receipt",
                    "activation_context",
                    "activation_rollback_intent",
                    "activation_rollback",
                },
            )
            intent = json.loads(
                (
                    run_root
                    / "activation-lane"
                    / "transaction"
                    / "activation-intent.json"
                ).read_text(encoding="utf-8")
            )
            artifact = (
                run_root
                / "activation-lane"
                / "ephemeral"
                / intent["plan"]["artifact_relative_path"]
            )
            self.assertFalse(artifact.exists())
            self.assertEqual(
                Path(intent["plan"]["workspace_root"]["path"]).parent.parent,
                run_root,
            )
            self.assertEqual(
                Path(intent["plan"]["workspace_root"]["path"]).parent,
                run_root / "activation-lane",
            )
            self.assertEqual(
                Path(intent["plan"]["ephemeral_root"]["path"]).parent,
                run_root / "activation-lane",
            )
            with patch.object(
                puppet_probe,
                "verify_qualification_receipt",
                return_value=receipt,
            ) as verify_recovered_receipt:
                recovered = recover_execute(files, run_id=run_id)
            self.assertEqual(recovered["result"], "accepted")
            self.assertFalse(recovered["recovered"])
            self.assertEqual(
                verify_recovered_receipt.call_args.args,
                (run_root / "receipt.json",),
            )

    def test_activation_failure_distinguishes_server_and_target_attempts(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            files = claude_activation_inputs(root)
            fake = FakeTmux(root / "fake-tmux", regular_socket=True)
            run_id = "probe-claude-revalidation-failure"
            with patch.object(
                puppet_probe,
                "revalidate_activation_launch_context",
                side_effect=IdentityError("activation context drift"),
            ):
                with self.assertRaisesRegex(IdentityError, "activation context drift"):
                    execute(
                        files,
                        fake,
                        target="claude",
                        run_id=run_id,
                        plane_descriptor=files["descriptor"],
                    )
            evidence = json.loads(
                (files["proof"] / "probes" / run_id / "evidence.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertTrue(evidence["failure"]["server_attempted"])
            self.assertFalse(evidence["failure"]["target_launch_attempted"])
            self.assertFalse(evidence["failure"]["launch_attempted"])
            self.assertEqual(
                puppet_probe.recover_activation(
                    files["proof"]
                    / "probes"
                    / run_id
                    / "activation-lane"
                    / "transaction"
                ).state,
                "rolled_back",
            )

    def test_recovery_rejects_transaction_without_canonical_descriptor_snapshot(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            files = claude_activation_inputs(root)
            fake = FakeTmux(root / "fake-tmux", regular_socket=True)
            run_id = "probe-claude-missing-descriptor"
            with patch.object(
                puppet_probe,
                "revalidate_activation_launch_context",
                side_effect=IdentityError("activation context drift"),
            ):
                with self.assertRaises(IdentityError):
                    execute(
                        files,
                        fake,
                        target="claude",
                        run_id=run_id,
                        plane_descriptor=files["descriptor"],
                    )
            snapshot = files["proof"] / "probes" / run_id / "plane-descriptor.json"
            snapshot.unlink()
            with self.assertRaisesRegex(IdentityError, "canonical descriptor snapshot"):
                recover_execute(
                    files,
                    run_id=run_id,
                    plane_descriptor=files["descriptor"],
                )

    def test_recovery_rolls_back_active_prelease_activation_without_relaunch(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            files = claude_activation_inputs(root)
            fake = FakeTmux(root / "fake-tmux", regular_socket=True)
            run_id = "probe-claude-active-recovery"
            with (
                patch.object(
                    puppet_probe,
                    "build_activation_launch_context",
                    side_effect=IdentityError("context join interrupted"),
                ),
                patch.object(
                    puppet_probe,
                    "rollback_activation",
                    side_effect=IdentityError("rollback deferred to recovery"),
                ),
            ):
                with self.assertRaisesRegex(IdentityError, "context join interrupted"):
                    execute(
                        files,
                        fake,
                        target="claude",
                        run_id=run_id,
                        plane_descriptor=files["descriptor"],
                    )
            transaction = (
                files["proof"] / "probes" / run_id / "activation-lane" / "transaction"
            )
            self.assertEqual(
                puppet_probe.recover_activation(transaction).state,
                "active",
            )

            def reject_relaunch(root):
                raise AssertionError("recovery must not construct a tmux launcher")

            recovered = recover_execute(
                files,
                run_id=run_id,
                tmux_factory=reject_relaunch,
            )
            recovery = json.loads(
                Path(recovered["recovery"]).read_text(encoding="utf-8")
            )
            self.assertEqual(recovery["plane_activation_state"], "rolled_back")
            self.assertFalse(recovery["server_attempted"])
            self.assertFalse(recovery["target_launch_attempted"])
            self.assertEqual(
                puppet_probe.recover_activation(transaction).state,
                "rolled_back",
            )

    def test_recovery_preserves_prepared_activation_without_relaunch(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            files = claude_activation_inputs(root)
            fake = FakeTmux(root / "fake-tmux", regular_socket=True)
            run_id = "probe-claude-prepared-recovery"

            def leave_prepared(plan, *, effective_contract):
                puppet_probe.atomic_write_json(
                    plan.intent_path,
                    {
                        "schema": "puppet.plane-activation-intent/v2",
                        "plan": plan.to_dict(),
                    },
                )
                raise ValidationError("materialization interrupted after intent")

            with patch.object(
                puppet_probe,
                "materialize_activation",
                side_effect=leave_prepared,
            ):
                with self.assertRaisesRegex(
                    ValidationError, "materialization interrupted after intent"
                ):
                    execute(
                        files,
                        fake,
                        target="claude",
                        run_id=run_id,
                        plane_descriptor=files["descriptor"],
                    )
            transaction = (
                files["proof"] / "probes" / run_id / "activation-lane" / "transaction"
            )
            before = sorted(path.name for path in transaction.iterdir())
            recovered = recover_execute(
                files,
                run_id=run_id,
                tmux_factory=lambda root: (_ for _ in ()).throw(
                    AssertionError("recovery must not relaunch")
                ),
            )
            recovery = json.loads(
                Path(recovered["recovery"]).read_text(encoding="utf-8")
            )
            self.assertEqual(recovery["plane_activation_state"], "prepared")
            self.assertEqual(
                sorted(path.name for path in transaction.iterdir()),
                before,
            )

    def test_launched_activation_rolls_back_only_after_exact_failure_cleanup(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            files = claude_activation_inputs(root)
            fake = FakeTmux(root / "fake-tmux", regular_socket=True)
            run_id = "probe-claude-launched-failure"
            events = []
            halt_exact = puppet_probe._halt_exact
            rollback = puppet_probe.rollback_activation

            def traced_halt(*args, **kwargs):
                result = halt_exact(*args, **kwargs)
                events.append("halt_complete")
                return result

            def traced_population(selected):
                if not fake.alive:
                    events.append("baseline_restored")
                return []

            def traced_rollback(plan):
                events.append("rollback")
                return rollback(plan)

            with (
                patch.object(
                    puppet_probe,
                    "record_acceptance",
                    side_effect=ValidationError("late acceptance failure"),
                ),
                patch.object(
                    puppet_probe,
                    "_halt_exact",
                    side_effect=traced_halt,
                ),
                patch.object(
                    puppet_probe,
                    "rollback_activation",
                    side_effect=traced_rollback,
                ),
            ):
                with self.assertRaisesRegex(ValidationError, "late acceptance failure"):
                    execute(
                        files,
                        fake,
                        target="claude",
                        run_id=run_id,
                        plane_descriptor=files["descriptor"],
                        active_processes_fn=traced_population,
                    )
            self.assertLess(
                events.index("halt_complete"), events.index("baseline_restored")
            )
            self.assertLess(events.index("baseline_restored"), events.index("rollback"))
            run_root = files["proof"] / "probes" / run_id
            evidence = json.loads(
                (run_root / "evidence.json").read_text(encoding="utf-8")
            )
            self.assertTrue(evidence["failure"]["server_attempted"])
            self.assertTrue(evidence["failure"]["target_launch_attempted"])
            self.assertFalse((run_root / "receipt.json").exists())
            self.assertEqual(
                puppet_probe.recover_activation(
                    run_root / "activation-lane" / "transaction"
                ).state,
                "rolled_back",
            )

    def test_ambiguous_launched_cleanup_preserves_active_activation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            files = claude_activation_inputs(root)
            fake = FakeTmux(root / "fake-tmux", regular_socket=True)
            run_id = "probe-claude-ambiguous-cleanup"
            rollback = puppet_probe.rollback_activation
            with (
                patch.object(
                    puppet_probe,
                    "record_acceptance",
                    side_effect=ValidationError("late acceptance failure"),
                ),
                patch.object(
                    puppet_probe,
                    "_halt_exact",
                    side_effect=IdentityError("exact halt identity ambiguous"),
                ),
                patch.object(
                    puppet_probe,
                    "rollback_activation",
                    wraps=rollback,
                ) as rollback_call,
            ):
                with self.assertRaisesRegex(ValidationError, "late acceptance failure"):
                    execute(
                        files,
                        fake,
                        target="claude",
                        run_id=run_id,
                        plane_descriptor=files["descriptor"],
                    )
            run_root = files["proof"] / "probes" / run_id
            evidence = json.loads(
                (run_root / "evidence.json").read_text(encoding="utf-8")
            )
            self.assertIn(
                "exact halt identity ambiguous", evidence["failure"]["cleanup_error"]
            )
            self.assertTrue(evidence["failure"]["target_launch_attempted"])
            self.assertEqual(rollback_call.call_count, 0)
            self.assertTrue(fake.alive)
            self.assertFalse((run_root / "receipt.json").exists())
            self.assertEqual(
                puppet_probe.recover_activation(
                    run_root / "activation-lane" / "transaction"
                ).state,
                "active",
            )

    def test_authorization_snapshot_failure_is_durably_terminal(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            files = controller_inputs(root)
            fake = FakeTmux(root / "fake-tmux")
            run_id = "probe-authorization-snapshot-failure"
            original_write = puppet_probe.atomic_write_json

            def fail_authorization_snapshot(path, value):
                if Path(path).name == "authorization.json":
                    raise ValidationError("authorization snapshot failed")
                return original_write(path, value)

            with patch.object(
                puppet_probe,
                "atomic_write_json",
                side_effect=fail_authorization_snapshot,
            ):
                with self.assertRaisesRegex(
                    ValidationError, "authorization snapshot failed"
                ):
                    execute(files, fake, run_id=run_id)
            run_root = files["proof"] / "probes" / run_id
            state = json.loads((run_root / "state.json").read_text(encoding="utf-8"))
            evidence = json.loads(
                (run_root / "evidence.json").read_text(encoding="utf-8")
            )
            self.assertEqual((state["phase"], state["result"]), ("failed", "failed"))
            self.assertEqual(evidence["result"], "failed")
            self.assertEqual(evidence["failure"]["type"], "ValidationError")
            self.assertIsNone(current_session_lease(files["authority"], target="codex"))
            self.assertIsNone(fake.launch_argv)

    def test_pre_admission_preparation_failure_is_durably_terminal(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            files = controller_inputs(root)
            fake = FakeTmux(root / "fake-tmux")
            run_id = "probe-pre-admission-failure"
            with patch(
                "puppet_lib.probe.create_fixture",
                side_effect=ValidationError("fixture preparation failed"),
            ):
                with self.assertRaisesRegex(
                    ValidationError, "fixture preparation failed"
                ):
                    execute(files, fake, run_id=run_id)
            run_root = files["proof"] / "probes" / run_id
            state = json.loads((run_root / "state.json").read_text(encoding="utf-8"))
            evidence = json.loads(
                (run_root / "evidence.json").read_text(encoding="utf-8")
            )
            self.assertEqual((state["phase"], state["result"]), ("failed", "failed"))
            self.assertEqual(evidence["result"], "failed")
            self.assertEqual(evidence["failure"]["type"], "ValidationError")
            self.assertIsNone(current_session_lease(files["authority"], target="codex"))
            self.assertIsNone(fake.launch_argv)

    def test_startup_settle_precedes_initial_delivery(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            files = controller_inputs(root)
            fake = FakeTmux(root / "fake-tmux")
            sleeps = []

            def settle(interval):
                if not sleeps:
                    self.assertEqual(fake.payloads, [])
                sleeps.append(interval)

            execute(
                files,
                fake,
                run_id="probe-input-settle-order",
                sleep_fn=settle,
            )
            self.assertGreaterEqual(len(sleeps), 1)
            self.assertEqual(sleeps[0], startup_settle_seconds_for("codex"))
            self.assertEqual(len(fake.payloads), 2)

    def test_process_death_during_startup_settle_prevents_delivery(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            files = controller_inputs(root)
            fake = FakeTmux(root / "fake-tmux")

            def die_during_settle(_interval):
                fake.alive = False

            with self.assertRaises(IdentityError):
                execute(
                    files,
                    fake,
                    run_id="probe-input-settle-death",
                    sleep_fn=die_during_settle,
                )
            self.assertEqual(fake.payloads, [])

    def test_instruction_manifest_drift_during_settle_prevents_delivery(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            files = controller_inputs(root)
            fake = FakeTmux(root / "fake-tmux")
            run_id = "probe-instruction-settle-drift"

            def tamper_during_settle(_interval):
                path = (
                    files["proof"] / "probes" / run_id / "effective-instructions.json"
                )
                manifest = json.loads(path.read_text(encoding="utf-8"))
                manifest["rendered_sha256"] = "0" * 64
                write_json(path, manifest)

            with self.assertRaisesRegex(
                IdentityError, "instruction manifest fingerprint changed"
            ):
                execute(
                    files,
                    fake,
                    run_id=run_id,
                    sleep_fn=tamper_during_settle,
                )
            self.assertEqual(fake.payloads, [])
            self.assertFalse(fake.alive)

    def test_population_policy_accepts_only_exact_registered_descendants(self):
        protected = [static_process_identity(991)]
        registered = static_process_identity(4242)
        child = static_process_identity(4999)
        grandchild = static_process_identity(5000)
        protected_node = process_tree_node(protected[0], 1)
        root_node = process_tree_node(registered, 1)
        child_node = process_tree_node(child, registered["pid"])
        grandchild_node = process_tree_node(grandchild, child["pid"])

        direct = _validated_target_population(
            snapshot={
                "processes": [protected[0], registered, child],
                "ancestry_nodes": [protected_node, root_node, child_node],
            },
            protected=protected,
            registered=registered,
            process_alive_fn=lambda identity: True,
            process_tree_alive_fn=lambda identity: True,
        )
        self.assertEqual(direct["descendants"], [child])
        self.assertEqual(direct["ancestry_chains"], [[child_node, root_node]])

        nested = _validated_target_population(
            snapshot={
                "processes": [protected[0], registered, child, grandchild],
                "ancestry_nodes": [
                    protected_node,
                    root_node,
                    child_node,
                    grandchild_node,
                ],
            },
            protected=protected,
            registered=registered,
            process_alive_fn=lambda identity: True,
            process_tree_alive_fn=lambda identity: True,
        )
        self.assertEqual(nested["descendants"], [child, grandchild])
        self.assertEqual(
            nested["ancestry_chains"],
            [[child_node, root_node], [grandchild_node, child_node, root_node]],
        )

        disappeared = _validated_target_population(
            snapshot={
                "processes": [protected[0], registered],
                "ancestry_nodes": [protected_node, root_node],
            },
            protected=protected,
            registered=registered,
            process_alive_fn=lambda identity: True,
            process_tree_alive_fn=lambda identity: True,
        )
        self.assertEqual(disappeared["descendants"], [])

    def test_population_policy_rejects_unproved_or_drifted_extras(self):
        protected = [static_process_identity(991)]
        registered = static_process_identity(4242)
        child = static_process_identity(4999)
        protected_node = process_tree_node(protected[0], 1)
        root_node = process_tree_node(registered, 1)
        unrelated = static_process_identity(7777)
        cycle = static_process_identity(5000)
        cases = {
            "unrelated": (
                [
                    process_tree_node(child, 7777),
                    process_tree_node(unrelated, 1),
                ],
                child,
                lambda identity: True,
            ),
            "protected": (
                [process_tree_node(child, 991)],
                child,
                lambda identity: True,
            ),
            "missing": (
                [process_tree_node(child, 7777)],
                child,
                lambda identity: True,
            ),
            "cycle": (
                [
                    process_tree_node(child, 5000),
                    process_tree_node(cycle, 4999),
                ],
                child,
                lambda identity: True,
            ),
            "pid_reuse": (
                [process_tree_node(child, 4242)],
                child,
                lambda identity: identity["pid"] != 4999,
            ),
            "executable_drift": (
                [process_tree_node(dict(child, inode=child["inode"] + 1), 4242)],
                dict(child, inode=child["inode"] + 1),
                lambda identity: True,
            ),
        }
        for name, (nodes, extra, alive) in cases.items():
            with self.subTest(name=name), self.assertRaises(IdentityError):
                _validated_target_population(
                    snapshot={
                        "processes": [protected[0], registered, extra],
                        "ancestry_nodes": [protected_node, root_node, *nodes],
                    },
                    protected=protected,
                    registered=registered,
                    process_alive_fn=alive,
                    process_tree_alive_fn=lambda identity: True,
                )

        with self.assertRaisesRegex(IdentityError, "identity changed"):
            _validated_target_population(
                snapshot={
                    "processes": [
                        protected[0],
                        dict(registered, start="different birth"),
                    ],
                    "ancestry_nodes": [
                        protected_node,
                        process_tree_node(dict(registered, start="different birth"), 1),
                    ],
                },
                protected=protected,
                registered=registered,
                process_alive_fn=lambda identity: True,
                process_tree_alive_fn=lambda identity: True,
            )

        intermediate = dict(static_process_identity(4888), command="helper")
        with self.assertRaisesRegex(IdentityError, "ancestry node"):
            _validated_target_population(
                snapshot={
                    "processes": [protected[0], registered, child],
                    "ancestry_nodes": [
                        protected_node,
                        root_node,
                        process_tree_node(child, intermediate["pid"]),
                        process_tree_node(intermediate, registered["pid"]),
                    ],
                },
                protected=protected,
                registered=registered,
                process_alive_fn=lambda identity: True,
                process_tree_alive_fn=lambda node: (
                    node["process"]["kernel_birth_id"]
                    != intermediate["kernel_birth_id"]
                ),
            )

    def test_receipt_ancestry_rejects_protected_splice_and_node_conflict(self):
        registered = static_process_identity(4242)
        protected = static_process_identity(991)
        child = static_process_identity(4999)
        protected_splice = [
            process_tree_node(child, protected["pid"]),
            process_tree_node(protected, registered["pid"]),
            process_tree_node(registered, 1),
        ]
        with self.assertRaisesRegex(ValidationError, "ancestry edge identity"):
            _validated_ancestry_chain(
                protected_splice,
                "receipt",
                registered=registered,
                protected_pids={protected["pid"]},
            )

        intermediate_a = dict(
            static_process_identity(4888), kernel_birth_id="test:intermediate-a"
        )
        intermediate_b = dict(
            static_process_identity(4888), kernel_birth_id="test:intermediate-b"
        )
        root_node = process_tree_node(registered, 1)
        first = _validated_ancestry_chain(
            [
                process_tree_node(child, 4888),
                process_tree_node(intermediate_a, registered["pid"]),
                root_node,
            ],
            "receipt",
            registered=registered,
            protected_pids=set(),
        )
        second = _validated_ancestry_chain(
            [
                process_tree_node(static_process_identity(5000), 4888),
                process_tree_node(intermediate_b, registered["pid"]),
                root_node,
            ],
            "receipt",
            registered=registered,
            protected_pids=set(),
        )
        with self.assertRaisesRegex(ValidationError, "node identity conflicts"):
            _validate_ancestry_node_coherence([first, second], "last target population")

    def test_success_emits_accepted_receipt_without_prompt_argv_and_preserves_tmux(
        self,
    ):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            files = controller_inputs(root)
            fake = FakeTmux(root / "fake-tmux")
            result = execute(files, fake)
            self.assertEqual(result["result"], "accepted")
            self.assertEqual(
                fake.launch_argv, files["raw"]["yolo_mapping"]["launch_argv"]
            )
            launch_text = "\x00".join(fake.launch_argv)
            self.assertNotIn("PUPPET_REAL_HARNESS", launch_text)
            self.assertEqual(len(fake.payloads), 2)
            self.assertTrue(
                all(b"PUPPET_REAL_HARNESS" in item for item in fake.payloads)
            )
            receipt = json.loads(Path(result["receipt"]).read_text(encoding="utf-8"))
            self.assertEqual(receipt["capabilities"], list(PROBE_CAPABILITIES))
            self.assertEqual(
                receipt["execution_fingerprint"],
                files["raw"]["execution"]["execution_fingerprint"],
            )
            self.assertNotIn("resume", receipt["capabilities"])
            evidence = json.loads(
                (Path(result["run_root"]) / "evidence.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                Path(evidence["campaign_probe_lock"]["path"]).name,
                "real-harness.codex.lock",
            )
            self.assertEqual(
                evidence["execution_fingerprint"], receipt["execution_fingerprint"]
            )
            self.assertIsNone(evidence["plane_activation"])
            self.assertIsNone(receipt["plane_activation"])
            self.assertIsNone(evidence["failure"])
            wrapper = evidence["instruction_wrapper"]
            self.assertEqual(
                receipt["instruction_policy_fingerprint"],
                wrapper["instruction_policy_fingerprint"],
            )
            self.assertEqual(wrapper["instruction_plane"], "initial_message_wrapper")
            self.assertEqual(wrapper["session_profile"], "regular")
            self.assertEqual(wrapper["delivery_transport"]["native_config_writes"], [])
            instruction_ref = next(
                item for item in receipt["proof_refs"] if item["kind"] == "instructions"
            )
            instruction_path = Path(result["run_root"]) / instruction_ref["path"]
            self.assertTrue(instruction_path.is_file())
            marker = b"PUPPET_REAL_HARNESS_CONFORMANCE_V2"
            for path in Path(result["run_root"]).rglob("*"):
                if path.is_file():
                    with self.subTest(no_raw_initial_body=path):
                        self.assertNotIn(marker, path.read_bytes())
            halt = json.loads(
                (Path(result["run_root"]) / "halt.json").read_text(encoding="utf-8")
            )
            self.assertTrue(halt["tmux_preserved"])
            self.assertFalse(fake.alive)
            self.assertTrue(fake.preserved)
            self.assertEqual(len(fake.interrupts), 1)

    def test_probe_evidence_binds_the_stable_final_runtime(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            files = controller_inputs(root)
            fake = FakeTmux(root / "fake-tmux")
            runtime = root / "synthetic-runtime"
            transient = root / "synthetic-transient"
            support = root / "synthetic-index.js"
            runtime.write_bytes(b"runtime")
            transient.write_bytes(b"transient")
            support.write_bytes(b"support")
            raw = json.loads(json.dumps(files["raw"]))
            launcher = raw["executable"]
            raw["execution"] = build_execution_bundle(
                launcher={
                    "path": launcher["resolved_path"],
                    "device": launcher["device"],
                    "inode": launcher["inode"],
                    "size": launcher["size"],
                    "mtime_ns": launcher["mtime_ns"],
                    "sha256": launcher["sha256"],
                },
                transition="same_pid_exec",
                runtime_executable=execution_file_identity(runtime),
                transient_executables=[execution_file_identity(transient)],
                support_files=[execution_file_identity(support)],
                settle_timeout_seconds=1.0,
            )
            files["raw"] = AdapterManifest.from_dict(raw).raw
            write_json(files["manifest"], files["raw"])
            runtime_file = execution_file_identity(runtime)
            runtime_process = dict(
                static_process_identity(fake.pid),
                command=runtime.name,
                executable_path=runtime_file["path"],
                device=runtime_file["device"],
                inode=runtime_file["inode"],
            )
            result = execute(
                files,
                fake,
                run_id="probe-final-runtime-evidence",
                process_birth_fn=lambda pid: runtime_process,
                continuous_population_fn=lambda target: (
                    [runtime_process] if fake.alive else []
                ),
            )
            evidence = json.loads(
                (Path(result["run_root"]) / "evidence.json").read_text(encoding="utf-8")
            )
            receipt = json.loads(Path(result["receipt"]).read_text(encoding="utf-8"))
            self.assertEqual(evidence["process"], runtime_process)
            self.assertEqual(
                evidence["execution_fingerprint"],
                files["raw"]["execution"]["execution_fingerprint"],
            )
            self.assertEqual(
                receipt["execution_fingerprint"], evidence["execution_fingerprint"]
            )

    def test_launch_environment_values_are_hash_only_in_probe_proof(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            files = controller_inputs(root)
            fake = FakeTmux(root / "fake-tmux")
            private_value = "launch-value-that-must-remain-private"
            with patch.dict(
                os.environ,
                {
                    "CODEX_HOME": private_value,
                    "PUPPET_PARENT_CANARY": "ambient-value-that-must-not-cross",
                },
                clear=False,
            ):
                result = execute(
                    files,
                    fake,
                    run_id="probe-private-launch-environment",
                )
            self.assertNotIn("CODEX_HOME", fake.launch_environment)
            self.assertNotIn("PUPPET_PARENT_CANARY", fake.launch_environment)
            run_root = Path(result["run_root"])
            evidence = json.loads(
                (run_root / "evidence.json").read_text(encoding="utf-8")
            )
            identity = evidence["launch_identity"]
            self.assertEqual(
                set(identity),
                {"cwd", "argv_sha256", "env_names", "env_fingerprint"},
            )
            self.assertNotIn("CODEX_HOME", identity["env_names"])
            self.assertNotIn("launch_environment", evidence)
            for path in run_root.rglob("*"):
                if path.is_file():
                    with self.subTest(no_launch_environment_value=path):
                        content = path.read_bytes()
                        self.assertNotIn(private_value.encode(), content)
                        self.assertNotIn(b"ambient-value-that-must-not-cross", content)

    def test_probe_accepts_same_binary_descendant_and_records_ancestry(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            files = controller_inputs(root)
            fake = FakeTmux(root / "fake-tmux")
            child = static_process_identity(4999)
            root_process = process_identity(fake)
            root_node = process_tree_node(root_process, 1)
            child_node = process_tree_node(child, fake.pid)

            def population(_target):
                if not fake.alive:
                    return {"processes": [], "ancestry_nodes": []}
                return {
                    "processes": [root_process, child],
                    "ancestry_nodes": [root_node, child_node],
                }

            result = execute(
                files,
                fake,
                run_id="probe-descendant",
                population_snapshot_fn=population,
            )
            evidence = json.loads(
                (Path(result["run_root"]) / "evidence.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                evidence["target_population_policy"], TARGET_POPULATION_POLICY
            )
            self.assertEqual(
                evidence["observed_target_descendants"],
                [
                    {
                        "process": child,
                        "ancestry_chain": [child_node, root_node],
                    }
                ],
            )
            self.assertEqual(
                evidence["last_target_population"]["ancestry_chains"],
                [[child_node, root_node]],
            )

    def test_transient_descendant_keeps_historical_chain_in_accepted_receipt(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            files = controller_inputs(root)
            fake = FakeTmux(root / "fake-tmux")
            child = static_process_identity(4999)
            root_process = process_identity(fake)
            root_node = process_tree_node(root_process, 1)
            child_node = process_tree_node(child, fake.pid)
            calls = {"count": 0}

            def population(_target):
                if not fake.alive:
                    return {"processes": [], "ancestry_nodes": []}
                calls["count"] += 1
                if calls["count"] == 1:
                    return {
                        "processes": [root_process, child],
                        "ancestry_nodes": [root_node, child_node],
                    }
                return {
                    "processes": [root_process],
                    "ancestry_nodes": [root_node],
                }

            result = execute(
                files,
                fake,
                run_id="probe-transient-descendant",
                population_snapshot_fn=population,
            )
            self.assertEqual(result["result"], "accepted")
            evidence = json.loads(
                (Path(result["run_root"]) / "evidence.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                evidence["observed_target_descendants"],
                [
                    {
                        "process": child,
                        "ancestry_chain": [child_node, root_node],
                    }
                ],
            )
            self.assertEqual(
                evidence["last_target_population"],
                {
                    "policy": TARGET_POPULATION_POLICY,
                    "processes": [root_process],
                    "ancestry_chains": [],
                    "accepted": True,
                },
            )

    def test_probe_rejects_same_target_descendant_that_survives_exact_halt(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            files = controller_inputs(root)
            fake = FakeTmux(root / "fake-tmux")
            child = static_process_identity(4999)
            active_calls = {"count": 0}

            def active_after_halt(_target):
                active_calls["count"] += 1
                return [] if active_calls["count"] <= 2 else [child]

            def population(_target):
                root_process = process_identity(fake)
                return {
                    "processes": [root_process, child],
                    "ancestry_nodes": [
                        process_tree_node(root_process, 1),
                        process_tree_node(child, fake.pid),
                    ],
                }

            with self.assertRaisesRegex(
                IdentityError, "protected same-target process population changed"
            ):
                execute(
                    files,
                    fake,
                    run_id="probe-descendant-survives-halt",
                    population_snapshot_fn=population,
                    active_processes_fn=active_after_halt,
                )
            self.assertFalse(fake.alive)
            self.assertEqual(len(fake.interrupts), 1)
            self.assertEqual(
                current_session_lease(files["authority"], target="codex")["state"],
                "halting",
            )

    def test_late_proof_failure_keeps_lease_fenced_if_a_descendant_appears(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            files = controller_inputs(root)
            fake = FakeTmux(root / "fake-tmux")
            child = static_process_identity(4999)
            active_calls = {"count": 0}
            survivor_present = {"value": True}

            def active_during_failed_attestation(_target):
                active_calls["count"] += 1
                return (
                    []
                    if active_calls["count"] <= 3 or not survivor_present["value"]
                    else [child]
                )

            with patch(
                "puppet_lib.probe.attest_qualification",
                side_effect=ValidationError("injected attestation failure"),
            ):
                with self.assertRaisesRegex(
                    ValidationError, "injected attestation failure"
                ):
                    execute(
                        files,
                        fake,
                        run_id="probe-late-proof-failure-descendant",
                        active_processes_fn=active_during_failed_attestation,
                    )

            self.assertFalse(fake.alive)
            self.assertEqual(
                current_session_lease(files["authority"], target="codex")["state"],
                "halting",
            )
            with self.assertRaises(ConflictError):
                admit_session_lease(
                    session="other-after-late-proof-failure",
                    target="codex",
                    controller="other-controller",
                    owner={
                        "activity": "session",
                        "run_id": "other-after-late-proof-failure",
                        "campaign_id": files["campaign_id"],
                        "goal_fingerprint": sha256_bytes(
                            canonical_json_bytes(files["expected_goal"])
                        ),
                        "proof_root": str(files["proof"]),
                        "state_root": str(files["proof"]),
                    },
                    instruction_manifest_sha256=sha256_file(files["manifest"]),
                    authority_root=files["authority"],
                )

            def recover():
                return recover_probe(
                    target="codex",
                    proof_root=files["proof"],
                    manifest_path=files["manifest"],
                    mapping_path=files["mapping"],
                    authorization_path=files["authorization"],
                    controller="tester",
                    goal_repo=files["goal_repo"],
                    expected_campaign_id=files["campaign_id"],
                    expected_goal=files["expected_goal"],
                    run_id="probe-late-proof-failure-descendant",
                    halt_timeout=0.1,
                    _tmux_factory=lambda selected: fake,
                    _process_birth_fn=lambda pid: process_identity(fake),
                    _process_alive_fn=lambda identity: fake.alive,
                    _exact_sigint_fn=fake.exact_sigint,
                    _server_process_birth_fn=lambda pid: fake.server_process,
                    _active_processes_fn=active_during_failed_attestation,
                    _adapter_fingerprint_fn=lambda: files["raw"]["adapter_fingerprint"],
                    _census_target_fn=lambda selected, fingerprint: (
                        AdapterManifest.from_dict(files["raw"])
                    ),
                    _sleep_fn=lambda interval: None,
                    _authority_root=files["authority"],
                )

            with self.assertRaisesRegex(
                IdentityError, "protected same-target process population changed"
            ):
                recover()
            self.assertEqual(
                current_session_lease(files["authority"], target="codex")["state"],
                "halting",
            )

            survivor_present["value"] = False
            recovered = recover()
            self.assertEqual(recovered["result"], "interrupted_probe_reconciled")
            self.assertEqual(
                current_session_lease(files["authority"], target="codex")["state"],
                "failed",
            )

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
                "session_profile": receipt["session_profile"],
            }
            raw["capabilities"] = {
                name: "controller_verified"
                if name in receipt["capabilities"]
                else "unsupported"
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
            with self.assertRaisesRegex(IdentityError, "session profile"):
                manifest.verify_qualification(
                    expected_session_profile="goal",
                    _authority_root=files["authority"],
                    _current_manifest=AdapterManifest.from_dict(files["raw"]),
                    _server_process_fn=lambda pid: fake.server_process,
                    _tmux_factory=lambda selected: fake,
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
            authorization = json.loads(
                files["authorization"].read_text(encoding="utf-8")
            )
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
            result = execute(files, fake, active=[protected], run_id="probe-parallel")
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
            self.assertEqual(fake.interrupts[0], ("exact_pid_sigint", fake.pid, None))
            halt = json.loads(
                (files["proof"] / "probes" / "probe-timeout" / "halt.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(halt["cleanup_scope"], "exact_new_target_only")
            self.assertTrue(halt["tmux_preserved"])

    def test_dead_target_failure_preserves_tmux_without_signaling_other_processes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            files = controller_inputs(root)
            fake = FakeTmux(
                root / "fake-tmux", synthesize=False, die_after_initial=True
            )
            with self.assertRaisesRegex(IdentityError, "stopped"):
                execute(files, fake, run_id="probe-dead")
            self.assertEqual(fake.interrupts, [])
            halt = json.loads(
                (files["proof"] / "probes" / "probe-dead" / "halt.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(halt["signal"], "none_already_stopped")
            self.assertTrue(halt["tmux_preserved"])

    def test_halt_rejects_a_dead_pane_with_changed_process_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            files = controller_inputs(root)
            fake = FakeTmux(root / "fake-tmux", terminal_pid_drift=True)
            with self.assertRaisesRegex(IdentityError, "preserved dead evidence pane"):
                execute(files, fake, run_id="probe-terminal-pane-drift")
            self.assertFalse(fake.alive)
            self.assertEqual(
                current_session_lease(files["authority"], target="codex")["state"],
                "halting",
            )

    def test_agy_uses_exact_double_eof_graceful_halt(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            alive = {"value": True}
            sent = []

            def deliver(action):
                sent.append(action)
                if len(sent) == 2:
                    alive["value"] = False

            submitted = deliver_halt_actions(
                journal=Journal(root / "halt-journal"),
                session="probe-agy-double-eof",
                target_identity=static_process_identity(991),
                actions=list(adapter_for("agy").graceful_halt_actions),
                process_alive=lambda: alive["value"],
                deliver_action=deliver,
            )
            self.assertEqual(submitted, ["tmux_pane_eof", "tmux_pane_eof"])
            self.assertEqual(sent, ["tmux_pane_eof", "tmux_pane_eof"])

    def test_agy_does_not_send_second_eof_after_exact_target_stops(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            alive = {"value": True}
            sent = []

            def deliver(action):
                sent.append(action)
                alive["value"] = False

            submitted = deliver_halt_actions(
                journal=Journal(root / "halt-journal"),
                session="probe-agy-one-eof",
                target_identity=static_process_identity(991),
                actions=list(adapter_for("agy").graceful_halt_actions),
                process_alive=lambda: alive["value"],
                deliver_action=deliver,
            )
            self.assertEqual(submitted, ["tmux_pane_eof"])
            self.assertEqual(sent, ["tmux_pane_eof"])

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

    def test_wrong_launcher_remains_fenced_without_any_halt_action(self):
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
            with self.assertRaisesRegex(IdentityError, "not declared"):
                execute(
                    files,
                    fake,
                    run_id="probe-process-mismatch",
                    process_birth_fn=lambda pid: wrong_process,
                )
            self.assertTrue(fake.alive)
            self.assertEqual(fake.payloads, [])
            self.assertEqual(fake.interrupts, [])
            self.assertEqual(fake.control_calls, [])
            self.assertEqual(
                current_session_lease(files["authority"], target="codex")["state"],
                "launching",
            )

    def test_process_birth_failure_remains_fenced_without_any_halt_action(self):
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
            self.assertTrue(fake.alive)
            self.assertEqual(fake.payloads, [])
            self.assertEqual(fake.interrupts, [])
            self.assertEqual(fake.control_calls, [])
            run_root = files["proof"] / "probes" / "probe-process-birth-failure"
            self.assertFalse((run_root / "halt.json").exists())
            evidence = json.loads(
                (run_root / "evidence.json").read_text(encoding="utf-8")
            )
            self.assertIn("remains unbound", evidence["failure"]["cleanup_error"])
            self.assertEqual(
                current_session_lease(files["authority"], target="codex")["state"],
                "launching",
            )

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
            descriptor, _ = _acquire_campaign_probe_lock(
                files["authority"], target="codex"
            )
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
                    "state_root": str(files["proof"]),
                },
                instruction_manifest_sha256=sha256_file(files["manifest"]),
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

    def test_receipt_rejects_mutated_instruction_manifest(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            files = controller_inputs(root)
            fake = FakeTmux(root / "fake-tmux")
            result = execute(files, fake, run_id="probe-instruction-tamper")
            receipt_path = Path(result["receipt"])
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            instruction_ref = next(
                item for item in receipt["proof_refs"] if item["kind"] == "instructions"
            )
            instruction_path = receipt_path.parent / instruction_ref["path"]
            instruction = json.loads(instruction_path.read_text(encoding="utf-8"))
            instruction["rendered_sha256"] = "0" * 64
            write_json(instruction_path, instruction)
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

    def test_current_execution_identity_drift_invalidates_qualification(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            files = controller_inputs(root)
            fake = FakeTmux(root / "fake-tmux")
            result = execute(files, fake, run_id="probe-current-execution-drift")
            drifted = json.loads(json.dumps(files["raw"]))
            drifted["execution"] = direct_execution_bundle(
                drifted["executable"], settle_timeout_seconds=3.0
            )
            with self.assertRaisesRegex(IdentityError, "execution_fingerprint"):
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
                "session_profile": receipt["session_profile"],
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

            with self.assertRaisesRegex(IdentityError, "ancestry chain"):
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

    def test_launch_context_build_failure_does_not_admit_target_lease(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            files = controller_inputs(root)
            fake = FakeTmux(root / "fake-tmux")
            with patch.object(
                puppet_probe,
                "build_launch_identity",
                side_effect=ValidationError("injected launch context failure"),
            ):
                with self.assertRaisesRegex(ValidationError, "injected launch context"):
                    execute(
                        files,
                        fake,
                        run_id="probe-launch-context-failure",
                    )
            self.assertIsNone(fake.launch_argv)
            self.assertIsNone(current_session_lease(files["authority"], target="codex"))

            validation_fake = FakeTmux(root / "validation-fake-tmux")
            with patch.object(
                validation_fake,
                "launch",
                side_effect=ValidationError("injected tmux validation failure"),
            ):
                with self.assertRaisesRegex(ValidationError, "tmux validation"):
                    execute(
                        files,
                        validation_fake,
                        run_id="probe-tmux-validation-failure",
                    )
            self.assertIsNone(validation_fake.launch_argv)
            self.assertIsNone(current_session_lease(files["authority"], target="codex"))

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
                        "state_root": str(files["proof"]),
                    },
                    instruction_manifest_sha256=sha256_file(files["manifest"]),
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
                _exact_sigint_fn=fake.exact_sigint,
                _server_process_birth_fn=lambda pid: fake.server_process,
                _active_processes_fn=lambda selected: [],
                _adapter_fingerprint_fn=lambda: files["raw"]["adapter_fingerprint"],
                _census_target_fn=lambda selected, fingerprint: (
                    AdapterManifest.from_dict(files["raw"])
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
            recovery = json.loads(
                (run_root / "recovery.json").read_text(encoding="utf-8")
            )
            self.assertTrue(recovery["launch_attempted"])

    def test_complete_probe_recovery_finishes_deferred_terminal_lease(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            files = controller_inputs(root)
            fake = FakeTmux(root / "fake-tmux")
            original_transition = transition_session_lease

            def defer_terminal_lease(**kwargs):
                if kwargs["state"] == "halted":
                    return current_session_lease(files["authority"], target="codex")
                return original_transition(**kwargs)

            with patch(
                "puppet_lib.probe.transition_session_lease",
                side_effect=defer_terminal_lease,
            ):
                result = execute(
                    files,
                    fake,
                    run_id="probe-complete-deferred-terminal-lease",
                )

            self.assertEqual(result["result"], "accepted")
            self.assertEqual(
                current_session_lease(files["authority"], target="codex")["state"],
                "halting",
            )
            controls_before = list(fake.interrupts)
            survivor_present = {"value": True}
            survivor = static_process_identity(4999)

            def recover():
                return recover_probe(
                    target="codex",
                    proof_root=files["proof"],
                    manifest_path=files["manifest"],
                    mapping_path=files["mapping"],
                    authorization_path=files["authorization"],
                    controller="tester",
                    goal_repo=files["goal_repo"],
                    expected_campaign_id=files["campaign_id"],
                    expected_goal=files["expected_goal"],
                    run_id="probe-complete-deferred-terminal-lease",
                    halt_timeout=0.1,
                    _tmux_factory=lambda selected: fake,
                    _process_birth_fn=lambda pid: process_identity(fake),
                    _process_alive_fn=lambda identity: fake.alive,
                    _exact_sigint_fn=fake.exact_sigint,
                    _server_process_birth_fn=lambda pid: fake.server_process,
                    _active_processes_fn=lambda selected: (
                        [survivor] if survivor_present["value"] else []
                    ),
                    _adapter_fingerprint_fn=lambda: files["raw"]["adapter_fingerprint"],
                    _census_target_fn=lambda selected, fingerprint: (
                        AdapterManifest.from_dict(files["raw"])
                    ),
                    _sleep_fn=lambda interval: None,
                    _authority_root=files["authority"],
                )

            with self.assertRaisesRegex(
                IdentityError, "protected target population changed"
            ):
                recover()
            self.assertEqual(
                current_session_lease(files["authority"], target="codex")["state"],
                "halting",
            )
            self.assertEqual(fake.interrupts, controls_before)

            survivor_present["value"] = False
            recovered = recover()
            self.assertTrue(recovered["recovered"])
            self.assertEqual(recovered["result"], "accepted")
            self.assertEqual(
                current_session_lease(files["authority"], target="codex")["state"],
                "halted",
            )
            self.assertEqual(fake.interrupts, controls_before)

            admit_session_lease(
                session="unrelated-after-complete-recovery",
                target="codex",
                controller="other-controller",
                owner={
                    "activity": "session",
                    "run_id": "unrelated-after-complete-recovery",
                    "campaign_id": files["campaign_id"],
                    "goal_fingerprint": sha256_bytes(
                        canonical_json_bytes(files["expected_goal"])
                    ),
                    "proof_root": str(files["proof"]),
                    "state_root": str(files["proof"]),
                },
                instruction_manifest_sha256=sha256_file(files["manifest"]),
                authority_root=files["authority"],
            )
            unrelated = current_session_lease(files["authority"], target="codex")
            with self.assertRaisesRegex(IdentityError, "controller session lease"):
                recover()
            self.assertEqual(
                current_session_lease(files["authority"], target="codex"), unrelated
            )

    def test_recovery_never_reconstructs_an_unpersisted_socket_occupant(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            files = controller_inputs(root)
            fake = FakeTmux(root / "fake-tmux")
            with patch(
                "puppet_lib.probe._halt_exact",
                side_effect=KeyboardInterrupt(),
            ):
                with self.assertRaises(KeyboardInterrupt):
                    execute(files, fake, run_id="probe-unpersisted-recovery")
            run_root = files["proof"] / "probes" / "probe-unpersisted-recovery"
            evidence_path = run_root / "evidence.json"
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            lease_before = current_session_lease(files["authority"], target="codex")
            controls_before = list(fake.control_calls)
            signals_before = list(fake.interrupts)

            def recover():
                return recover_probe(
                    target="codex",
                    proof_root=files["proof"],
                    manifest_path=files["manifest"],
                    mapping_path=files["mapping"],
                    authorization_path=files["authorization"],
                    controller="tester",
                    goal_repo=files["goal_repo"],
                    expected_campaign_id=files["campaign_id"],
                    expected_goal=files["expected_goal"],
                    run_id="probe-unpersisted-recovery",
                    halt_timeout=0.1,
                    _tmux_factory=lambda selected: fake,
                    _process_birth_fn=lambda pid: process_identity(fake),
                    _process_alive_fn=lambda identity: fake.alive,
                    _exact_sigint_fn=fake.exact_sigint,
                    _server_process_birth_fn=lambda pid: fake.server_process,
                    _active_processes_fn=lambda selected: [process_identity(fake)],
                    _adapter_fingerprint_fn=lambda: files["raw"]["adapter_fingerprint"],
                    _census_target_fn=lambda selected, fingerprint: (
                        AdapterManifest.from_dict(files["raw"])
                    ),
                    _sleep_fn=lambda interval: None,
                    _authority_root=files["authority"],
                )

            replacement = json.loads(json.dumps(evidence))
            replacement["process"]["kernel_birth_id"] = "test:replacement"
            write_json(evidence_path, replacement)
            with self.assertRaisesRegex(IdentityError, "controller lease"):
                recover()
            self.assertEqual(fake.control_calls, controls_before)
            self.assertEqual(fake.interrupts, signals_before)

            evidence["tmux"] = None
            evidence["process"] = None
            write_json(evidence_path, evidence)
            with self.assertRaisesRegex(IdentityError, "remains fenced"):
                recover()
            self.assertEqual(
                current_session_lease(files["authority"], target="codex"),
                lease_before,
            )
            self.assertEqual(fake.control_calls, controls_before)
            self.assertEqual(fake.interrupts, signals_before)
            recovery = json.loads(
                (run_root / "recovery.json").read_text(encoding="utf-8")
            )
            self.assertEqual(recovery["result"], "interrupted_probe_fenced")

    def test_prelaunch_recovery_preserves_authorized_parallel_population(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            files = controller_inputs(root, override=True)
            fake = FakeTmux(root / "fake-tmux")
            protected = [static_process_identity(991)]

            def admit_then_interrupt(**kwargs):
                admit_session_lease(**kwargs)
                raise KeyboardInterrupt()

            with patch(
                "puppet_lib.probe.admit_session_lease",
                side_effect=admit_then_interrupt,
            ):
                with self.assertRaises(KeyboardInterrupt):
                    execute(
                        files,
                        fake,
                        run_id="probe-protected-prelaunch-crash",
                        active=protected,
                    )
            self.assertIsNone(fake.launch_argv)
            run_root = files["proof"] / "probes" / "probe-protected-prelaunch-crash"
            evidence = json.loads(
                (run_root / "evidence.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                evidence["active_target_processes_before_launch"], protected
            )
            self.assertEqual(
                current_session_lease(files["authority"], target="codex")["state"],
                "launching",
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
                run_id="probe-protected-prelaunch-crash",
                halt_timeout=0.1,
                _tmux_factory=lambda selected: fake,
                _process_birth_fn=lambda pid: process_identity(fake),
                _process_alive_fn=lambda identity: fake.alive,
                _exact_sigint_fn=fake.exact_sigint,
                _server_process_birth_fn=lambda pid: fake.server_process,
                _active_processes_fn=lambda selected: list(protected),
                _adapter_fingerprint_fn=lambda: files["raw"]["adapter_fingerprint"],
                _census_target_fn=lambda selected, fingerprint: (
                    AdapterManifest.from_dict(files["raw"])
                ),
                _sleep_fn=lambda interval: None,
                _authority_root=files["authority"],
            )
            self.assertTrue(recovered["recovered"])
            self.assertFalse(recovered["tmux_preserved"])
            self.assertEqual(
                current_session_lease(files["authority"], target="codex")["state"],
                "failed",
            )
            recovery = json.loads(
                (run_root / "recovery.json").read_text(encoding="utf-8")
            )
            self.assertFalse(recovery["launch_attempted"])

    def test_interrupted_agy_eof_is_ambiguous_and_never_resent(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            sent = []

            def interrupt(action):
                sent.append(action)
                raise KeyboardInterrupt()

            journal = Journal(root / "halt-journal")
            identity = static_process_identity(991)
            with self.assertRaises(KeyboardInterrupt):
                deliver_halt_actions(
                    journal=journal,
                    session="probe-agy-ambiguous",
                    target_identity=identity,
                    actions=list(adapter_for("agy").graceful_halt_actions),
                    process_alive=lambda: True,
                    deliver_action=interrupt,
                )
            with self.assertRaisesRegex(IdentityError, "ambiguous"):
                deliver_halt_actions(
                    journal=journal,
                    session="probe-agy-ambiguous",
                    target_identity=identity,
                    actions=list(adapter_for("agy").graceful_halt_actions),
                    process_alive=lambda: True,
                    deliver_action=lambda action: sent.append(action),
                )
            self.assertEqual(sent, ["tmux_pane_eof"])

    def test_probe_profile_is_fixed_before_launch(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            files = controller_inputs(root)
            fake = FakeTmux(root / "fake-tmux")
            self.assertEqual(PROBE_PROFILE, "source-free-pass-b-v2")
            with self.assertRaisesRegex(ValidationError, "fixed source-free Pass B"):
                run_probe(
                    target="codex",
                    profile="arbitrary",
                    session_profile=default_session_profile("codex"),
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
            with self.assertRaisesRegex(ValidationError, "limited to regular"):
                run_probe(
                    target="codex",
                    profile=PROBE_PROFILE,
                    session_profile="goal",
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
