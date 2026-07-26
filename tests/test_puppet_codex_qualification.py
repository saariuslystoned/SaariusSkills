from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "puppet" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from puppet_lib import codex_qualification as qualification  # noqa: E402
from puppet_lib.authority import attest_qualification  # noqa: E402
from puppet_lib.errors import (  # noqa: E402
    ConflictError,
    IdentityError,
    ValidationError,
)
from puppet_lib.safety import (  # noqa: E402
    canonical_json_bytes,
    sha256_bytes,
)


def write_json(path: Path, value) -> None:
    path.write_text(
        json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def process(pid: int) -> dict:
    return {
        "identity_version": 2,
        "pid": pid,
        "start": "2026-07-26T12:00:%02dZ" % (pid % 60),
        "kernel_birth_id": "fixture:%d" % pid,
        "command": "codex",
        "executable_path": "/opt/codex",
        "device": 10,
        "inode": pid,
    }


def tmux_identity(root: Path, session: str, pid: int) -> dict:
    return {
        "socket": str(root / (session + ".sock")),
        "session": session,
        "target_id": "%%%d" % (pid % 100),
        "server_identity": process(pid + 1000),
        "tmux_binary_identity": {
            "path": "/opt/tmux",
            "device": 20,
            "inode": 30,
        },
    }


class PairFixture:
    def __init__(self, root: Path):
        self.root = root
        root.chmod(0o700)
        self.authority = root / "authority"
        self.authority.mkdir(mode=0o700)
        self.profile = root / "profile"
        self.profile.mkdir(mode=0o700)
        self.proof = root / "proof"
        self.proof.mkdir(mode=0o700)
        self.probes = self.proof / "probes"
        self.probes.mkdir(mode=0o700)
        self.positive_root = self.probes / "positive-run"
        self.control_root = self.probes / "control-run"
        self.positive_root.mkdir(mode=0o700)
        self.control_root.mkdir(mode=0o700)
        self.positive_path = self.positive_root / "receipt.json"
        self.control_path = self.control_root / "receipt.json"
        self.native_path = self.positive_root / qualification.NATIVE_VIEW_NAME
        self.entry_path = root / "operator-plan.json"
        self.out = root / "codex-paired-receipt.json"
        self.workspace = root / "candidate"
        self.workspace.mkdir(mode=0o700)
        self.supervisor = root / "supervisor"
        self.supervisor.mkdir(mode=0o700)
        self.control_workspace = self.control_root / "fixture"
        self.control_workspace.mkdir(mode=0o700)

        self.positive_process = process(2101)
        self.control_process = process(2201)
        self.positive_tmux = tmux_identity(root, "positive-session", 3101)
        self.control_tmux = tmux_identity(root, "control-session", 3201)
        self.workspace_receipt = {
            "schema": "puppet.codex-direct-worktree-receipt/v1",
            "terminal_state": "controller_verified_after_exact_halt",
            "descriptor_sha256": "1" * 64,
            "candidate_root": str(self.workspace),
            "candidate_branch": "codex/positive",
            "candidate_head": "1" * 40,
            "startup_cwd": str(self.workspace),
            "controller_contract_sha256": "2" * 64,
            "instruction_manifest_sha256": "3" * 64,
            "executable_sha256": "4" * 64,
            "subscription_profile_sha256": "5" * 64,
            "launch_plan_sha256": "6" * 64,
        }
        self.positive = self._receipt(
            run_id="positive-run",
            checkpoint="7" * 64,
            workspace=self.workspace_receipt,
        )
        self.control = self._receipt(
            run_id="control-run",
            checkpoint="8" * 64,
            workspace=None,
        )
        self.artifacts = {
            str(self.positive_path): self._artifacts(
                self.workspace,
                self.positive_process,
                self.positive_tmux,
                descriptor={
                    "surface": "controller_proved_direct_worktree_cwd",
                    "descriptor_sha256": self.workspace_receipt[
                        "descriptor_sha256"
                    ],
                    "candidate_root": str(self.workspace),
                    "candidate_branch": self.workspace_receipt[
                        "candidate_branch"
                    ],
                    "candidate_head": self.workspace_receipt["candidate_head"],
                    "supervisor_root": str(self.supervisor),
                },
            ),
            str(self.control_path): self._artifacts(
                self.control_workspace,
                self.control_process,
                self.control_tmux,
                descriptor=None,
            ),
        }
        self._write_entry_plan()
        self.entry_source = {
            "schema": qualification.ENTRY_SOURCE_SCHEMA,
            "target": "codex",
            "entry_mode": "direct_git_root",
            "operator_plan": {
                "path": str(self.entry_path),
                "sha256": qualification.sha256_file(self.entry_path),
                "plan_sha256": json.loads(
                    self.entry_path.read_text(encoding="utf-8")
                )["plan_sha256"],
            },
            "run_id": "positive-run",
            "session": "positive-session",
            "controller": "controller-worker",
            "campaign_id": "campaign-codex-pair",
            "goal_fingerprint": "a" * 64,
            "contract": {
                "path": str(self.root / "contract.json"),
                "sha256": "41" * 32,
                "fingerprint": "42" * 32,
            },
            "manifest": {
                "path": str(self.root / "manifest.json"),
                "sha256": "43" * 32,
                "fingerprint": "44" * 32,
            },
            "authorization": {
                "path": str(self.root / "authorization.json"),
                "sha256": "45" * 32,
            },
            "profile": {
                "root": str(self.profile),
                "sha256": "5" * 64,
            },
            "workspace": {
                "descriptor_sha256": self.workspace_receipt["descriptor_sha256"],
                "candidate_root": str(self.workspace),
                "candidate_branch": self.workspace_receipt["candidate_branch"],
                "candidate_head": self.workspace_receipt["candidate_head"],
            },
        }
        self.positive["codex_entry_source"] = copy.deepcopy(self.entry_source)
        self.positive["controller_attestation"] = attest_qualification(
            self.positive, authority_root=self.authority
        )
        write_json(self.positive_path, self.positive)
        write_json(
            self.positive_root / "state.json",
            {
                **self._state("positive-run", "positive-session"),
                "codex_entry_source": self.entry_source,
            },
        )
        self._write_native()
        with self.patches():
            source = qualification.build_codex_control_source(
                self.positive_path,
                authority_root=self.authority,
                _verify_receipt_fn=self.verify_receipt,
                _terminal_lease_fn=self.terminal_lease,
            )
        self.control["codex_control_source"] = copy.deepcopy(source)
        self.control["controller_attestation"] = attest_qualification(
            self.control, authority_root=self.authority
        )
        write_json(self.control_path, self.control)
        state = self._state("control-run", "control-session")
        state["codex_control_source"] = source
        write_json(self.control_root / "state.json", state)

    def _receipt(self, *, run_id: str, checkpoint: str, workspace) -> dict:
        return {
            "schema_version": 5,
            "kind": "real_harness_conformance",
            "run_id": run_id,
            "target": "codex",
            "session_profile": "regular",
            "result": "accepted",
            "controller": "controller-worker",
            "campaign_id": "campaign-codex-pair",
            "goal_fingerprint": "a" * 64,
            "executable_fingerprint": "4" * 64,
            "execution_fingerprint": "b" * 64,
            "version_fingerprint": "c" * 64,
            "platform_fingerprint": "d" * 64,
            "adapter_fingerprint": "e" * 64,
            "protocol_fingerprint": "f" * 64,
            "yolo_mapping_sha256": "0" * 64,
            "launch_plan_sha256": (
                "6" * 64 if workspace is not None else "9" * 64
            ),
            "subscription_profile_sha256": "5" * 64,
            "instruction_policy_fingerprint": "a1" * 32,
            "capabilities": [
                "launch",
                "send",
                "status",
                "wait",
                "checkpoint",
                "halt",
            ],
            "accepted_checkpoint_id": checkpoint,
            "acceptance_sha256": (
                "b1" * 32 if workspace is not None else "b2" * 32
            ),
            "halt_receipt_sha256": (
                "c1" * 32 if workspace is not None else "c2" * 32
            ),
            "plane_activation": None,
            "workspace_isolation": workspace,
            "codex_entry_source": None,
            "codex_control_source": None,
            "proof_refs": [],
        }

    @staticmethod
    def _state(run_id: str, session: str) -> dict:
        return {
            "schema_version": 5,
            "profile": "source-free-pass-b-v2",
            "run_id": run_id,
            "session": session,
        }

    def _artifacts(self, cwd: Path, target_process: dict, tmux: dict, descriptor):
        return {
            "paths": {},
            "launch": {
                "cwd": str(cwd),
                "argv": ["/opt/codex", "--dangerously-bypass-approvals-and-sandbox"],
                "launch_identity": {
                    "env_names": [
                        "CODEX_HOME",
                        "HOME",
                        "LANG",
                        "LC_ALL",
                        "PATH",
                        "TMPDIR",
                    ],
                    "env_fingerprint": "9f" * 32,
                },
            },
            "profile": {"profile_root": str(self.profile)},
            "evidence": {
                "process": target_process,
                "tmux": tmux,
                "active_target_processes_before_launch": [],
                "active_target_processes_after_halt": [],
                "ready": {"checkpoint_id": "d1" * 32},
            },
            "instructions": {
                "runtime_binding": {"model": "default", "effort": "default"},
                "model_observation": {
                    "selection": "current_default",
                    "resolved_identity": "unavailable",
                    "effort": "unavailable",
                },
            },
            "descriptor": descriptor,
        }

    def _write_entry_plan(self) -> None:
        plan = {
            "schema": "puppet.operator-run-plan/v1",
            "state": "planning_only",
            "entry_mode": "direct_git_root",
            "target": "codex",
            "session_profile": "regular",
            "launch_authorized": False,
            "repository": {
                "repo": str(self.workspace),
                "branch": self.workspace_receipt["candidate_branch"],
                "head": self.workspace_receipt["candidate_head"],
                "tree": "2" * 40,
                "linked_worktree": True,
                "dirty": False,
            },
        }
        plan["plan_sha256"] = sha256_bytes(canonical_json_bytes(plan))
        write_json(self.entry_path, plan)

    def _write_native(self, *, read_only: bool = True) -> None:
        evidence = self.artifacts[str(self.positive_path)]["evidence"]
        viewer_client = {
            "pid": 5101,
            "tty": "/dev/ttys051",
            "read_only": read_only,
            "session": "positive-session",
        }
        viewer_process = process(5101)
        viewer_process.update(
            {
                "command": "tmux",
                "executable_path": "/opt/tmux",
                "device": 20,
                "inode": 30,
            }
        )
        record = {
            "schema": qualification.NATIVE_VIEW_SCHEMA,
            "target": "codex",
            "run_id": self.positive["run_id"],
            "controller": self.positive["controller"],
            "campaign_id": self.positive["campaign_id"],
            "goal_fingerprint": self.positive["goal_fingerprint"],
            "session": "positive-session",
            "state": "read_only_attached_and_detached",
            "ready_checkpoint_id": evidence["ready"]["checkpoint_id"],
            "attach_argv_sha256": sha256_bytes(
                canonical_json_bytes(qualification._native_attach_argv(evidence))
            ),
            "tmux_sha256": sha256_bytes(
                canonical_json_bytes(evidence["tmux"])
            ),
            "target_process_sha256": sha256_bytes(
                canonical_json_bytes(evidence["process"])
            ),
            "viewer_client_sha256": sha256_bytes(
                canonical_json_bytes(viewer_client)
            ),
            "viewer_process_sha256": sha256_bytes(
                canonical_json_bytes(viewer_process)
            ),
            "viewer_client": viewer_client,
            "viewer_process": viewer_process,
            "read_only": read_only,
            "attached": True,
            "detached": True,
            "target_alive_after_detach": True,
            "body_capture_performed": False,
            "raw_retained": False,
        }
        record["controller_attestation"] = qualification._attest_native_view(
            record,
            authority_root=self.authority,
        )
        write_json(self.native_path, record)

    def terminal_lease(self, **kwargs):
        positive = Path(kwargs["receipt_path"]) == self.positive_path
        return {
            "session": (
                "positive-session" if positive else "control-session"
            ),
            "generation": 1 if positive else 2,
            "state": "halted",
            "lease_sha256": ("11" if positive else "12") * 32,
            "owner_sha256": ("21" if positive else "22") * 32,
            "process_sha256": sha256_bytes(
                canonical_json_bytes(
                    self.positive_process if positive else self.control_process
                )
            ),
            "ledger_sequence": 1 if positive else 5,
            "ledger_entry_hash": ("31" if positive else "32") * 32,
        }

    def verify_receipt(self, path, **kwargs):
        del kwargs
        selected = Path(path)
        if selected == self.positive_path:
            return copy.deepcopy(self.positive)
        if selected == self.control_path:
            return copy.deepcopy(self.control)
        raise AssertionError("unexpected receipt")

    def patches(self):
        stack = ExitStack()
        stack.enter_context(
            patch.object(
                qualification,
                "_receipt_artifacts",
                side_effect=lambda path, receipt: copy.deepcopy(
                    self.artifacts[str(Path(path))]
                ),
            )
        )
        def validate_entry(value):
            if value != self.entry_source:
                raise IdentityError("Codex positive-entry source changed")
            if qualification.sha256_file(self.entry_path) != value[
                "operator_plan"
            ]["sha256"]:
                raise IdentityError("Codex operator entry artifact fingerprint changed")
            return copy.deepcopy(value)

        stack.enter_context(
            patch.object(
                qualification,
                "validate_codex_entry_source",
                side_effect=validate_entry,
            )
        )
        return stack

    def create(self):
        with self.patches():
            return qualification.create_codex_regular_pair_receipt(
                out=self.out,
                positive_receipt_path=self.positive_path,
                ordinary_receipt_path=self.control_path,
                native_view_path=self.native_path,
                private_profile_root=self.profile,
                authority_root=self.authority,
                _verify_receipt_fn=self.verify_receipt,
                _terminal_lease_fn=self.terminal_lease,
            )

    def verify(self, value_or_path=None):
        with self.patches():
            return qualification.verify_codex_regular_pair_receipt(
                self.out if value_or_path is None else value_or_path,
                expected_private_profile_root=self.profile,
                _authority_root=self.authority,
                _verify_receipt_fn=self.verify_receipt,
                _terminal_lease_fn=self.terminal_lease,
            )


class CodexQualificationTests(unittest.TestCase):
    def fixture(self, temporary: str) -> PairFixture:
        return PairFixture(Path(temporary).resolve())

    def test_create_only_pair_is_attested_verified_and_non_promotable(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self.fixture(temporary)
            result = fixture.create()
            self.assertEqual(result["result"], "paired_evidence_only")
            self.assertFalse(result["public_launch_authorized"])
            self.assertFalse(result["promotion_authorized"])
            pair = fixture.verify()
            self.assertEqual(pair["entry_claim"]["mode"], "direct_git_root")
            self.assertEqual(
                pair["runtime_binding"],
                {
                    "model_selection": "current_default",
                    "effort_selection": "current_default",
                    "resolved_model": "unavailable",
                    "resolved_effort": "unavailable",
                    "explicit_selector": False,
                },
            )
            self.assertFalse(pair["raw_retained"])
            with self.assertRaises(ConflictError):
                fixture.create()

    def test_forged_pair_and_receipt_drift_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self.fixture(temporary)
            fixture.create()
            forged = fixture.verify()
            forged = copy.deepcopy(forged)
            forged["promotion_authorized"] = True
            with self.assertRaises(ValidationError):
                fixture.verify(forged)
            fixture.positive_path.write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(IdentityError, "fingerprint changed"):
                fixture.verify()

    def test_same_process_session_tmux_or_workspace_is_rejected(self):
        mutators = {
            "process": lambda fixture: fixture.artifacts[
                str(fixture.control_path)
            ]["evidence"].update(process=fixture.positive_process),
            "session": lambda fixture: write_json(
                fixture.control_root / "state.json",
                {
                    **json.loads(
                        (fixture.control_root / "state.json").read_text(
                            encoding="utf-8"
                        )
                    ),
                    "session": "positive-session",
                },
            ),
            "tmux": lambda fixture: fixture.artifacts[
                str(fixture.control_path)
            ]["evidence"].update(tmux=fixture.positive_tmux),
            "workspace": lambda fixture: fixture.artifacts[
                str(fixture.control_path)
            ]["launch"].update(cwd=str(fixture.workspace)),
        }
        for label, mutate in mutators.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temporary:
                fixture = self.fixture(temporary)
                mutate(fixture)
                with self.assertRaises(IdentityError):
                    fixture.create()

    def test_missing_or_non_read_only_native_view_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self.fixture(temporary)
            fixture.native_path.unlink()
            with self.assertRaises(ValidationError):
                fixture.create()
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self.fixture(temporary)
            fixture._write_native(read_only=False)
            with self.assertRaisesRegex(ValidationError, "native-view terminal"):
                fixture.create()
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self.fixture(temporary)
            record = json.loads(fixture.native_path.read_text(encoding="utf-8"))
            record["viewer_client"]["tty"] = "/dev/ttys099"
            record["viewer_client_sha256"] = sha256_bytes(
                canonical_json_bytes(record["viewer_client"])
            )
            write_json(fixture.native_path, record)
            with self.assertRaisesRegex(IdentityError, "not attested"):
                fixture.create()

    def test_pair_requires_same_profile_and_current_default_vector(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self.fixture(temporary)
            fixture.artifacts[str(fixture.control_path)]["profile"][
                "profile_root"
            ] = str(fixture.root / "different-profile")
            with self.assertRaisesRegex(IdentityError, "profile binding"):
                fixture.create()
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self.fixture(temporary)
            for path in (fixture.positive_path, fixture.control_path):
                fixture.artifacts[str(path)]["launch"]["argv"].extend(
                    ["--model", "forged-selector"]
                )
            with self.assertRaisesRegex(IdentityError, "default/no-selector"):
                fixture.create()

    def test_missing_halt_entry_source_drift_and_mapping_drift_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self.fixture(temporary)
            fixture.positive["halt_receipt_sha256"] = None
            with self.assertRaises(ValidationError):
                fixture.create()
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self.fixture(temporary)
            plan = json.loads(fixture.entry_path.read_text(encoding="utf-8"))
            plan["entry_mode"] = "cockpit_explicit"
            write_json(fixture.entry_path, plan)
            with self.assertRaisesRegex(IdentityError, "artifact fingerprint"):
                fixture.create()
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self.fixture(temporary)
            plan = json.loads(fixture.entry_path.read_text(encoding="utf-8"))
            plan["repository"]["head"] = "f" * 40
            unsigned = dict(plan)
            unsigned.pop("plan_sha256")
            plan["plan_sha256"] = sha256_bytes(canonical_json_bytes(unsigned))
            write_json(fixture.entry_path, plan)
            with self.assertRaisesRegex(IdentityError, "artifact fingerprint"):
                fixture.create()
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self.fixture(temporary)

            def stale_verifier(path, **kwargs):
                if Path(path) == fixture.positive_path:
                    raise IdentityError(
                        "qualification is stale for the current controller "
                        "identity: yolo_mapping_sha256"
                    )
                return fixture.verify_receipt(path, **kwargs)

            with fixture.patches(), self.assertRaisesRegex(
                IdentityError, "yolo_mapping_sha256"
            ):
                qualification.create_codex_regular_pair_receipt(
                    out=fixture.out,
                    positive_receipt_path=fixture.positive_path,
                    ordinary_receipt_path=fixture.control_path,
                    native_view_path=fixture.native_path,
                    private_profile_root=fixture.profile,
                    authority_root=fixture.authority,
                    _verify_receipt_fn=stale_verifier,
                    _terminal_lease_fn=fixture.terminal_lease,
                )

    def test_cockpit_entry_mode_is_derived_from_receipt_bound_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self.fixture(temporary)
            plan = json.loads(fixture.entry_path.read_text(encoding="utf-8"))
            plan["entry_mode"] = "cockpit_explicit"
            unsigned = dict(plan)
            unsigned.pop("plan_sha256")
            plan["plan_sha256"] = sha256_bytes(canonical_json_bytes(unsigned))
            write_json(fixture.entry_path, plan)
            fixture.entry_source["entry_mode"] = "cockpit_explicit"
            fixture.entry_source["operator_plan"]["sha256"] = (
                qualification.sha256_file(fixture.entry_path)
            )
            fixture.entry_source["operator_plan"]["plan_sha256"] = plan[
                "plan_sha256"
            ]
            fixture.positive["codex_entry_source"] = copy.deepcopy(
                fixture.entry_source
            )
            fixture.create()
            self.assertEqual(
                fixture.verify()["entry_claim"]["mode"], "cockpit_explicit"
            )

    def test_posthoc_entry_plan_and_unrelated_entry_identities_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self.fixture(temporary)
            fixture.positive["codex_entry_source"] = None
            with self.assertRaises(IdentityError):
                fixture.create()
        for field, value in (
            ("session", "unrelated-session"),
            ("controller", "unrelated-controller"),
        ):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as temporary:
                fixture = self.fixture(temporary)
                fixture.entry_source[field] = value
                fixture.positive["codex_entry_source"] = copy.deepcopy(
                    fixture.entry_source
                )
                with self.assertRaisesRegex(IdentityError, "positive-entry"):
                    fixture.create()
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self.fixture(temporary)
            fixture.entry_source["profile"]["root"] = str(
                fixture.root / "unrelated-profile"
            )
            fixture.positive["codex_entry_source"] = copy.deepcopy(
                fixture.entry_source
            )
            with self.assertRaisesRegex(IdentityError, "positive-entry"):
                fixture.create()

    def test_completed_control_cannot_be_relinked(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self.fixture(temporary)
            fixture.control["codex_control_source"]["run_id"] = "other-positive"
            with self.assertRaisesRegex(IdentityError, "not linked"):
                fixture.create()

    def test_native_observer_records_only_distinct_structural_identities(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            root.chmod(0o700)
            proof = root / "proof"
            proof.mkdir(mode=0o700)
            probes = proof / "probes"
            probes.mkdir(mode=0o700)
            run_root = probes / "view-run"
            run_root.mkdir(mode=0o700)
            authority = root / "authority"
            authority.mkdir(mode=0o700)
            target = process(6101)
            server = process(6102)
            tmux = tmux_identity(root, "view-session", 6101)
            tmux["server_identity"] = server
            viewer_client = {
                "pid": 6103,
                "tty": "/dev/ttys061",
                "read_only": True,
                "session": "view-session",
            }
            viewer_process = process(6103)
            viewer_process.update(
                {
                    "command": "tmux",
                    "executable_path": "/opt/tmux",
                    "device": 20,
                    "inode": 30,
                }
            )
            write_json(
                run_root / "state.json",
                {
                    "run_id": "view-run",
                    "target": "codex",
                    "controller": "controller-worker",
                    "session": "view-session",
                    "phase": "ready_validated",
                },
            )
            evidence = {
                "campaign_id": "campaign-codex-pair",
                "goal_fingerprint": "a" * 64,
                "process": target,
                "tmux": tmux,
                "ready": {"checkpoint_id": "d1" * 32},
            }
            write_json(run_root / "evidence.json", evidence)

            class ObserverTmux:
                def __init__(self, _root):
                    self.client_calls = 0

                def assert_tmux_binary_identity(self, value):
                    self.asserted_binary = value

                def bind_server_identity(self, _socket, value):
                    self.bound_server = value

                def attach_argv(self, **_kwargs):
                    return qualification._native_attach_argv(evidence)

                def metadata_for_session(self, **_kwargs):
                    return {
                        "session": "view-session",
                        "pane": tmux["target_id"],
                        "pane_pid": target["pid"],
                        "pane_dead": False,
                    }

                def viewer_clients(self, **_kwargs):
                    self.client_calls += 1
                    if self.client_calls == 1:
                        return []
                    if self.client_calls == 2:
                        return [viewer_client]
                    return []

            clock = {"value": 0.0}

            def monotonic():
                clock["value"] += 0.1
                return clock["value"]

            def birth(pid):
                if pid == target["pid"]:
                    return copy.deepcopy(target)
                if pid == viewer_client["pid"]:
                    return copy.deepcopy(viewer_process)
                raise AssertionError("unexpected process lookup")

            result = qualification.observe_codex_native_view(
                proof_root=proof,
                run_id="view-run",
                _tmux_factory=ObserverTmux,
                _process_birth_fn=birth,
                _sleep_fn=lambda _seconds: None,
                _monotonic_fn=monotonic,
                _authority_root=authority,
            )
            self.assertTrue(result["read_only"])
            self.assertFalse(result["body_capture_performed"])
            self.assertFalse(result["raw_retained"])
            record = json.loads(
                Path(result["native_view"]).read_text(encoding="utf-8")
            )
            self.assertEqual(record["viewer_client"], viewer_client)
            self.assertEqual(record["viewer_process"], viewer_process)
            self.assertNotEqual(
                record["viewer_process"]["pid"], target["pid"]
            )
            self.assertNotEqual(
                record["viewer_process"]["pid"], server["pid"]
            )


if __name__ == "__main__":
    unittest.main()
