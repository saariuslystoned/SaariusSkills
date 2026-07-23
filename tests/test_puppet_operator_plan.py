from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "puppet" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import puppet as puppet_cli  # noqa: E402
from puppet_lib.adapter_manifest import (  # noqa: E402
    ADAPTER_MANIFEST_SCHEMA_VERSION,
    direct_execution_bundle,
)
from puppet_lib.campaign import (  # noqa: E402
    ALLOWED_ACTIONS as CAMPAIGN_ALLOWED_ACTIONS,
    HARD_GATES as CAMPAIGN_HARD_GATES,
)
from puppet_lib.census import adapter_implementation_fingerprint  # noqa: E402
from puppet_lib.contracts import MANDATORY_HARD_GATES  # noqa: E402
from puppet_lib.errors import IdentityError, ValidationError  # noqa: E402
from puppet_lib.handoffs import PROTOCOL_FINGERPRINT  # noqa: E402
from puppet_lib.operator_plan import compile_operator_plan  # noqa: E402
from puppet_lib.profiles import (  # noqa: E402
    PROMPT_TRANSPORT,
    SUBMIT_SETTLE_SECONDS,
    session_profiles_for,
    startup_settle_seconds_for,
)
from puppet_lib.safety import canonical_json_bytes, sha256_bytes  # noqa: E402


def _git(repo: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *arguments],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return result.stdout.strip()


def _commit(repo: Path, message: str) -> str:
    _git(repo, "add", "-A")
    _git(
        repo,
        "-c",
        "user.name=Puppet Test",
        "-c",
        "user.email=puppet@example.invalid",
        "commit",
        "-q",
        "-m",
        message,
    )
    return _git(repo, "rev-parse", "HEAD")


def _initialize_repo(path: Path, branch: str = "main") -> Path:
    path.mkdir()
    subprocess.run(
        ["git", "init", "-q", "-b", branch, str(path)],
        check=True,
    )
    nested = path / "nested"
    nested.mkdir()
    (nested / "fixture.txt").write_text("fixture\n", encoding="utf-8")
    _commit(path, "initialize fixture")
    return path.resolve(strict=True)


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")


def _manifest(target: str) -> dict:
    executable = Path("/bin/echo").resolve(strict=True)
    details = executable.stat()
    executable_identity = {
        "requested_path": str(executable),
        "resolved_path": str(executable),
        "device": details.st_dev,
        "inode": details.st_ino,
        "size": details.st_size,
        "mtime_ns": details.st_mtime_ns,
        "sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
        "version_sha256": "b" * 64,
        "help_sha256": "c" * 64,
    }
    if target == "agy":
        launch_argv = [
            str(executable),
            "--dangerously-skip-permissions",
            "--new-project",
        ]
        permission_flags = ["--dangerously-skip-permissions"]
        sandbox_flags = []
        project_flags = ["--new-project"]
    else:
        launch_argv = [str(executable), "--dangerously-bypass-approvals-and-sandbox"]
        permission_flags = ["--dangerously-bypass-approvals-and-sandbox"]
        sandbox_flags = ["--dangerously-bypass-approvals-and-sandbox"]
        project_flags = []
    return {
        "schema_version": ADAPTER_MANIFEST_SCHEMA_VERSION,
        "target": target,
        "generated_at": "2026-07-23T07:30:00Z",
        "platform": {"system": "Darwin", "release": "test", "machine": "arm64"},
        "executable": executable_identity,
        "execution": direct_execution_bundle(executable_identity),
        "adapter_fingerprint": adapter_implementation_fingerprint(),
        "protocol_fingerprint": PROTOCOL_FINGERPRINT,
        "yolo_mapping": {
            "complete": True,
            "launch_argv": launch_argv,
            "permission_declared": True,
            "permission_flags": permission_flags,
            "prompt_transport": PROMPT_TRANSPORT,
            "prompt_transport_declared": True,
            "sandbox_disable_declared": True,
            "sandbox_flags": sandbox_flags,
            "project_isolation_declared": True,
            "project_isolation_flags": project_flags,
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


class OperatorPlanFixture:
    def __init__(
        self,
        root: Path,
        *,
        target: str = "codex",
        mutating: bool = False,
        linked: bool = True,
    ) -> None:
        self.root = root
        root.mkdir(parents=True, exist_ok=True)
        self.target = target
        if mutating and linked:
            self.supervisor = _initialize_repo(root / "supervisor")
            self.repo = (root / "candidate").resolve(strict=False)
            _git(
                self.supervisor,
                "worktree",
                "add",
                "-q",
                "-b",
                "codex/operator-plan",
                str(self.repo),
            )
            self.repo = self.repo.resolve(strict=True)
        else:
            self.repo = _initialize_repo(root / "repo")
            self.supervisor = (
                _initialize_repo(root / "supervisor") if mutating else None
            )
        self.branch = _git(self.repo, "branch", "--show-current")
        contract = {
            "schema_version": 1,
            "objective": "Compile an exact body-free regular operator run plan",
            "campaign_authorization_id": "campaign-plan",
            "controller": "orchestrator",
            "target": target,
            "session_profile": "regular",
            "task_profile": "source" if mutating else "conformance",
            "harness_trust": "unrestricted_required",
            "mutation_owner": "target" if mutating else "none",
            "repo": str(self.repo),
            "branch": self.branch,
            "allowed_modes": (
                ["read", "test", "mutate", "local_commit"]
                if mutating
                else ["read", "test"]
            ),
            "terminal_criteria": [
                {"id": "plan_ready", "evidence": "operator_plan"}
            ],
            "hard_gates": sorted(MANDATORY_HARD_GATES),
        }
        if mutating:
            contract.update(
                supervisor_root=str(self.supervisor),
                candidate_root=str(self.repo),
            )
        self.contract = root / "contract.json"
        _write_json(self.contract, contract)
        self.manifest = root / "manifest.json"
        _write_json(self.manifest, _manifest(target))
        self.authorization = root / "authorization.json"
        _write_json(
            self.authorization,
            {
                "schema_version": 1,
                "campaign_id": "campaign-plan",
                "operator_identity": "operator",
                "controller": "orchestrator",
                "goal": {
                    "repository": "saariuslystoned/SaariusSkills",
                    "commit": "1" * 40,
                    "path": "plans/puppet/codex-goal.md",
                    "sha256": "2" * 64,
                },
                "acknowledged_at": "2026-07-23T07:30:00Z",
                "authorization": {
                    "harnesses": [target],
                    "trust_profile": "unrestricted_required",
                    "disable_harness_sandbox_where_exposed": True,
                    "ordinary_configured_model_provider_traffic": True,
                    "scope": (
                        "bounded Puppet implementation and conformance campaign only"
                    ),
                },
                "allowed_actions": CAMPAIGN_ALLOWED_ACTIONS,
                "hard_gates": CAMPAIGN_HARD_GATES,
            },
        )
        self.prompt_body = "PUPPET_OPERATOR_PLAN_BODY_CANARY_7b9a4e97\n"
        self.prompt = root / "launch-prompt.txt"
        self.prompt.write_text(self.prompt_body, encoding="utf-8")
        self.run = root / "run"
        self.proof = self.run / "proof"
        self.state = self.run / "state"
        for directory in (self.run, self.proof, self.state):
            directory.mkdir()
            directory.chmod(0o700)
        self.profile = root / "profiles" / target
        self.profile.parent.mkdir()

    def kwargs(self) -> dict:
        return {
            "contract_path": self.contract,
            "manifest_path": self.manifest,
            "authorization_path": self.authorization,
            "profile_root": self.profile,
            "prompt_path": self.prompt,
            "session": "operator-plan-1",
            "run_root": self.run,
        }


class OperatorPlanTests(unittest.TestCase):
    def test_direct_mode_infers_git_root_and_emits_exact_body_free_commands(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = OperatorPlanFixture(Path(temporary))
            real_run = subprocess.run
            calls = []

            def observed_run(*args, **kwargs):
                calls.append(args[0])
                return real_run(*args, **kwargs)

            with patch(
                "puppet_lib.operator_plan.subprocess.run",
                side_effect=observed_run,
            ):
                plan = compile_operator_plan(
                    **fixture.kwargs(),
                    current_directory=fixture.repo / "nested",
                )

            self.assertEqual(plan["schema"], "puppet.operator-run-plan/v1")
            self.assertEqual(plan["state"], "planning_only")
            self.assertEqual(plan["entry_mode"], "direct_git_root")
            self.assertFalse(plan["launch_authorized"])
            self.assertEqual(plan["repository"]["repo"], str(fixture.repo))
            self.assertEqual(plan["repository"]["branch"], fixture.branch)
            self.assertTrue(calls)
            self.assertTrue(all(Path(command[0]).name == "git" for command in calls))
            encoded = json.dumps(plan, sort_keys=True)
            self.assertNotIn(fixture.prompt_body.strip(), encoded)
            self.assertEqual(
                plan["artifacts"]["input_payload"]["sha256"],
                hashlib.sha256(fixture.prompt.read_bytes()).hexdigest(),
            )
            self.assertNotIn("prompt", plan["artifacts"])
            command = plan["commands"]["launch"]
            self.assertEqual(command[:4], [
                str(Path(sys.executable).resolve(strict=True)),
                str((SCRIPTS / "puppet.py").resolve(strict=True)),
                "--json",
                "launch",
            ])
            self.assertEqual(command[4:6], ["--session", "operator-plan-1"])
            self.assertEqual(
                plan["commands"]["waits"]["done"][-4:],
                ["--until", "done", "--timeout", "60.0"],
            )
            self.assertTrue(plan["commands"]["profile"]["supported"])
            digest_plan = dict(plan)
            digest = digest_plan.pop("plan_sha256")
            self.assertEqual(digest, sha256_bytes(canonical_json_bytes(digest_plan)))

    def test_cockpit_mode_requires_exact_explicit_repo(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = OperatorPlanFixture(Path(temporary))
            plan = compile_operator_plan(**fixture.kwargs(), repo=fixture.repo)
            self.assertEqual(plan["entry_mode"], "cockpit_explicit")
            other = _initialize_repo(Path(temporary) / "other")
            with self.assertRaisesRegex(
                IdentityError,
                "selected repository differs",
            ):
                compile_operator_plan(**fixture.kwargs(), repo=other)

    def test_branch_and_manifest_target_are_bound(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture = OperatorPlanFixture(root)
            contract = json.loads(fixture.contract.read_text(encoding="utf-8"))
            contract["branch"] = "wrong-branch"
            _write_json(fixture.contract, contract)
            with self.assertRaisesRegex(IdentityError, "branch differs"):
                compile_operator_plan(**fixture.kwargs(), repo=fixture.repo)
            contract["branch"] = fixture.branch
            _write_json(fixture.contract, contract)
            _write_json(fixture.manifest, _manifest("claude"))
            with self.assertRaisesRegex(IdentityError, "manifest target differs"):
                compile_operator_plan(**fixture.kwargs(), repo=fixture.repo)

    def test_mutating_plan_requires_clean_linked_worktree(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            linked = OperatorPlanFixture(root / "linked", mutating=True)
            plan = compile_operator_plan(**linked.kwargs(), repo=linked.repo)
            self.assertTrue(plan["repository"]["linked_worktree"])
            self.assertFalse(plan["repository"]["dirty"])
            (linked.repo / "dirty.txt").write_text("dirty\n", encoding="utf-8")
            with self.assertRaisesRegex(IdentityError, "clean linked Git worktree"):
                compile_operator_plan(**linked.kwargs(), repo=linked.repo)

        with tempfile.TemporaryDirectory() as temporary:
            unlinked = OperatorPlanFixture(
                Path(temporary),
                mutating=True,
                linked=False,
            )
            with self.assertRaisesRegex(IdentityError, "clean linked Git worktree"):
                compile_operator_plan(**unlinked.kwargs(), repo=unlinked.repo)

    def test_mutating_plan_binds_candidate_to_named_supervisor(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture = OperatorPlanFixture(root, mutating=True)
            plan = compile_operator_plan(**fixture.kwargs(), repo=fixture.repo)
            self.assertEqual(
                plan["repository"]["git_common_dir"],
                plan["supervisor_repository"]["git_common_dir"],
            )
            unrelated = _initialize_repo(root / "unrelated")
            contract = json.loads(fixture.contract.read_text(encoding="utf-8"))
            contract["supervisor_root"] = str(unrelated)
            _write_json(fixture.contract, contract)
            with self.assertRaisesRegex(
                IdentityError,
                "does not belong to the contract supervisor",
            ):
                compile_operator_plan(**fixture.kwargs(), repo=fixture.repo)

    def test_repository_fsmonitor_is_never_executed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture = OperatorPlanFixture(root)
            sentinel = root / "fsmonitor-ran"
            hook = root / "fsmonitor-hook"
            hook.write_text(
                "#!/bin/sh\n"
                + "touch '"
                + str(sentinel)
                + "'\n"
                + "printf '2\\n'\n",
                encoding="utf-8",
            )
            hook.chmod(0o700)
            _git(fixture.repo, "config", "core.fsmonitor", str(hook))
            plan = compile_operator_plan(**fixture.kwargs(), repo=fixture.repo)
            self.assertEqual(plan["repository"]["repo"], str(fixture.repo))
            self.assertFalse(sentinel.exists())

    def test_profile_root_cannot_overlap_run_state_or_proof(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = OperatorPlanFixture(Path(temporary))
            for profile in (fixture.run, fixture.state, fixture.proof):
                with self.subTest(profile=profile):
                    kwargs = fixture.kwargs()
                    kwargs["profile_root"] = profile
                    with self.assertRaisesRegex(
                        ValidationError,
                        "ownership roots must not overlap",
                    ):
                        compile_operator_plan(**kwargs, repo=fixture.repo)

    def test_agy_plan_keeps_private_profile_setup_unsupported(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = OperatorPlanFixture(Path(temporary), target="agy")
            plan = compile_operator_plan(**fixture.kwargs(), repo=fixture.repo)
            self.assertEqual(
                plan["commands"]["profile"],
                {
                    "supported": False,
                    "reason": "agy_private_subscription_profile_unsupported",
                },
            )
            self.assertIn(
                "agy_private_subscription_profile_unsupported",
                plan["blockers"],
            )

    def test_existing_profile_root_must_remain_private(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = OperatorPlanFixture(Path(temporary))
            fixture.profile.mkdir(mode=0o700)
            compile_operator_plan(**fixture.kwargs(), repo=fixture.repo)
            fixture.profile.chmod(0o755)
            with self.assertRaisesRegex(IdentityError, "current-UID 0700"):
                compile_operator_plan(**fixture.kwargs(), repo=fixture.repo)
            fixture.profile.chmod(0o700)
            fixture.profile.rmdir()
            fixture.profile.write_text("not a profile\n", encoding="utf-8")
            with self.assertRaisesRegex(ValidationError, "private directory"):
                compile_operator_plan(**fixture.kwargs(), repo=fixture.repo)

    def test_cli_exposes_plan_without_an_output_side_effect(self):
        parser = puppet_cli.build_parser()
        args = parser.parse_args(
            [
                "plan",
                "--contract",
                "/tmp/contract.json",
                "--manifest",
                "/tmp/manifest.json",
                "--authorization",
                "/tmp/authorization.json",
                "--profile-root",
                "/tmp/profile",
                "--prompt-file",
                "/tmp/prompt.txt",
                "--session",
                "session-1",
                "--run-root",
                "/tmp/run",
            ]
        )
        self.assertIs(args.handler, puppet_cli._plan)
        self.assertIsNone(args.repo)
        self.assertFalse(hasattr(args, "out"))


if __name__ == "__main__":
    unittest.main()
