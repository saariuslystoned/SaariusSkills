from __future__ import annotations

import copy
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "puppet" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import puppet_launch as launcher  # noqa: E402
from puppet_lib.campaign import (  # noqa: E402
    ALLOWED_ACTIONS as CAMPAIGN_ALLOWED_ACTIONS,
    HARD_GATES as CAMPAIGN_HARD_GATES,
)
from puppet_lib.errors import IdentityError, UnsupportedError, ValidationError  # noqa: E402
from tests.test_puppet_operator_plan import (  # noqa: E402
    _commit,
    _initialize_repo,
    _manifest,
    _write_json,
)


def _git(repo: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *arguments],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return result.stdout.strip()


def _rewrite_campaign(path: Path, mutate) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    mutate(value)
    value["campaign_sha256"] = launcher.sha256_bytes(
        launcher.canonical_json_bytes(launcher._campaign_unhashed(value))
    )
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")
    path.chmod(0o600)
    return value


def _rewrite_campaign_without_rehash(path: Path, mutate) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    mutate(value)
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")
    path.chmod(0o600)
    return value


def _initialize_controller_repo(root: Path) -> tuple[Path, tuple[Path, ...], str]:
    repo = _initialize_repo(root)
    scripts = repo / "skills" / "puppet" / "scripts"
    scripts.mkdir(parents=True)
    paths = tuple(
        scripts / name
        for name in ("puppet_launch.py", "puppet_fanout.py", "puppet.py")
    )
    for path in paths:
        path.write_text("# tracked controller fixture\n", encoding="utf-8")
    _commit(repo, "add controller fixture")
    return repo, paths, _git(repo, "rev-parse", "HEAD")


class LauncherFixture:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve(strict=True)
        self.private = self.root / "private"
        self.private.mkdir(mode=0o700)
        self.private.chmod(0o700)
        self.catalog = self.private / "warm-catalog.json"
        self.source = _initialize_repo(self.root / "source")
        self.commit = _git(self.source, "rev-parse", "HEAD")
        self.worktrees = self.root / "worktrees"
        self.worktrees.mkdir()
        self.campaigns = self.root / "campaigns"
        self.campaigns.mkdir()
        self.prompt = self.root / "launch-prompt.txt"
        self.prompt_canary = "PUPPET_LAUNCH_PROMPT_CANARY_d4fcd409\n"
        self.prompt.write_text(self.prompt_canary, encoding="utf-8")
        self.authorization = self.private / "authorization.json"
        _write_json(
            self.authorization,
            {
                "schema_version": 1,
                "campaign_id": "warm-campaign",
                "operator_identity": "operator",
                "controller": "controller",
                "goal": {
                    "repository": "saariuslystoned/SaariusSkills",
                    "commit": self.commit,
                    "path": "plans/puppet/codex-goal.md",
                    "sha256": "2" * 64,
                },
                "acknowledged_at": "2026-07-28T10:00:00Z",
                "authorization": {
                    "harnesses": list(launcher.TARGET_ORDER),
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
        self.manifests: dict[str, Path] = {}
        self.profiles: dict[str, Path] = {}
        manifest_root = self.private / "manifests"
        manifest_root.mkdir(mode=0o700)
        for target in launcher.TARGET_ORDER:
            value = _manifest(target)
            value["doctor_only"] = False
            value["capabilities"] = {
                name: (
                    "unsupported" if name == "resume" else "controller_verified"
                )
                for name in value["capabilities"]
            }
            value["qualification"] = {
                "receipt_path": str(self.private / ("%s-receipt.json" % target)),
                "receipt_sha256": "d" * 64,
                "session_profile": "regular",
            }
            path = manifest_root / ("%s.json" % target)
            _write_json(path, value)
            self.manifests[target] = path
            if target != "agy":
                profile = self.private / ("profile-%s" % target)
                profile.mkdir(mode=0o700)
                profile.chmod(0o700)
                self.profiles[target] = profile

    def catalog_arguments(self) -> dict:
        return {
            "output_path": self.catalog,
            "authorization_path": self.authorization,
            "manifest_assignments": [
                "%s=%s" % (target, self.manifests[target])
                for target in launcher.TARGET_ORDER
            ],
            "profile_assignments": [
                "%s=%s" % (target, self.profiles[target])
                for target in launcher.TARGET_ORDER
                if target != "agy"
            ],
        }

    def initialize_catalog(self) -> dict:
        def qualification(manifest, **_kwargs):
            profile = self.profiles.get(manifest.target)
            return {
                "schema": "test-qualification",
                "target": manifest.target,
                "private_profile_root": str(profile) if profile is not None else None,
            }

        with mock.patch.object(
            launcher.AdapterManifest,
            "verify_qualification",
            autospec=True,
            side_effect=qualification,
        ):
            return launcher.initialize_catalog(**self.catalog_arguments())

    def prepare_arguments(
        self,
        *,
        launch_id: str = "launch-one",
        targets: tuple[str, ...] = ("all",),
        modes: tuple[str, ...] = (),
    ) -> dict:
        return {
            "catalog_path": self.catalog,
            "target_values": targets,
            "source_repo": self.source,
            "source_commit": self.commit,
            "prompt_path": self.prompt,
            "launch_id": launch_id,
            "campaign_root": self.campaigns / launch_id,
            "worktree_parent": self.worktrees,
            "mode_values": modes,
            "task_profile": "smoke",
            "_controller_identity_validator": lambda _source: None,
        }

    def run_argv(
        self,
        *,
        launch_id: str,
        targets: tuple[str, ...] = ("all",),
    ) -> list[str]:
        result = [
            "run",
            "--catalog",
            str(self.catalog),
        ]
        for target in targets:
            result.extend(["--target", target])
        result.extend(
            [
                "--repo",
                str(self.source),
                "--commit",
                self.commit,
                "--prompt-file",
                str(self.prompt),
                "--launch-id",
                launch_id,
                "--campaign-root",
                str(self.campaigns / launch_id),
                "--worktree-parent",
                str(self.worktrees),
                "--task-profile",
                "smoke",
                "--allow-live-launch",
            ]
        )
        return result


class CheckpointRunner:
    def __init__(
        self,
        campaign: dict,
        *,
        timeout_targets: set[str] | None = None,
        delivery_by_target: dict[str, str] | None = None,
        imported_targets: set[str] | None = None,
        send_barrier: threading.Barrier | None = None,
    ) -> None:
        self.campaign = campaign
        self.timeout_targets = timeout_targets or set()
        self.delivery_by_target = delivery_by_target or {}
        self.imported_targets = imported_targets or set()
        self.send_barrier = send_barrier
        self.calls: list[tuple[str, str]] = []
        self._lock = threading.Lock()
        self._targets = {
            row["session"]: target
            for target, row in campaign["lanes"].items()
        }

    def _reference(self, target: str) -> dict:
        binding = self.campaign["lanes"][target]["source_checkpoint"]
        assignment = json.loads(
            Path(binding["assignment"]["path"]).read_text(encoding="utf-8")
        )
        identity = dict(assignment["handoff"]["fixed_fields"])
        identity.pop("schema_version")
        identity["candidate_commit"] = self.campaign["source"]["commit"]
        checkpoint_path = Path(binding["path"])
        artifact_sha256 = (
            launcher.sha256_file(checkpoint_path)
            if checkpoint_path.exists()
            else "a" * 64
        )
        return {
            "checkpoint_id": "b" * 64,
            "artifact_sha256": artifact_sha256,
            "checkpoint_kind": "source",
            "identity": identity,
            "path": binding["path"],
            "validation": "valid",
        }

    @staticmethod
    def _completed(argv: list[str], value: dict) -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess(
            argv,
            0,
            stdout=(json.dumps(value, sort_keys=True) + "\n").encode("utf-8"),
            stderr=b"",
        )

    def __call__(self, argv_value) -> subprocess.CompletedProcess[bytes]:
        argv = list(argv_value)
        action = argv[3]
        session = argv[argv.index("--session") + 1]
        target = self._targets[session]
        with self._lock:
            self.calls.append((target, action))
        if action == "status":
            return self._completed(
                argv,
                {
                    "ok": True,
                    "session": session,
                    "state": (
                        "SOURCE_CHECKPOINT_READY"
                        if target in self.imported_targets
                        else "ACTIVE"
                    ),
                    "last_checkpoint": (
                        self._reference(target)
                        if target in self.imported_targets
                        else None
                    ),
                },
            )
        if action == "send":
            if self.send_barrier is not None:
                self.send_barrier.wait(timeout=3)
            if target not in self.timeout_targets:
                output = Path(
                    self.campaign["lanes"][target]["source_checkpoint"]["path"]
                )
                if not output.exists():
                    output.write_bytes(b"{}\n")
                    output.chmod(0o600)
            return self._completed(
                argv,
                {
                    "ok": True,
                    "session": session,
                    "delivery": self.delivery_by_target.get(
                        target,
                        "submitted",
                    ),
                    "content_sha256": self.campaign["lanes"][target][
                        "source_checkpoint"
                    ]["delivery_sha256"],
                },
            )
        if action == "checkpoint":
            return self._completed(
                argv,
                {"ok": True, **self._reference(target)},
            )
        if action == "wait":
            return self._completed(
                argv,
                {
                    "ok": True,
                    "session": session,
                    "condition": "checkpoint",
                    "matched": True,
                    "state": "SOURCE_CHECKPOINT_READY",
                    "last_checkpoint": self._reference(target),
                },
            )
        raise AssertionError("unexpected controller action: %s" % action)


class PuppetLaunchTests(unittest.TestCase):
    def test_controller_identity_accepts_exact_clean_git_worktree(self):
        with tempfile.TemporaryDirectory() as temporary:
            repo, paths, commit = _initialize_controller_repo(
                Path(temporary) / "controller"
            )
            source = launcher._source_identity(repo, commit)

            observed = launcher._validate_executing_controller(
                source,
                controller_paths=paths,
            )

            self.assertEqual(observed["root"], str(repo))
            self.assertEqual(observed["commit"], commit)
            self.assertEqual(
                observed["files"],
                [
                    "skills/puppet/scripts/puppet_launch.py",
                    "skills/puppet/scripts/puppet_fanout.py",
                    "skills/puppet/scripts/puppet.py",
                ],
            )

    def test_controller_identity_rejects_copied_non_git_runtime(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve(strict=True)
            repo, paths, commit = _initialize_controller_repo(root / "controller")
            source = launcher._source_identity(repo, commit)
            copied = root / "copied-release"
            shutil.copytree(paths[0].parent, copied)

            with self.assertRaisesRegex(
                IdentityError,
                "not inside a Git worktree",
            ):
                launcher._validate_executing_controller(
                    source,
                    controller_paths=tuple(copied / path.name for path in paths),
                )

    def test_controller_identity_rejects_untracked_runtime_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            repo, paths, commit = _initialize_controller_repo(
                Path(temporary) / "controller"
            )
            source = launcher._source_identity(repo, commit)
            untracked = paths[0].parent / "untracked.py"
            untracked.write_text("# untracked\n", encoding="utf-8")

            with self.assertRaisesRegex(IdentityError, "not tracked"):
                launcher._validate_executing_controller(
                    source,
                    controller_paths=(paths[0], paths[1], untracked),
                )

    def test_controller_identity_rejects_dirty_runtime_worktree(self):
        with tempfile.TemporaryDirectory() as temporary:
            repo, paths, commit = _initialize_controller_repo(
                Path(temporary) / "controller"
            )
            source = launcher._source_identity(repo, commit)
            paths[2].write_text("# dirty controller fixture\n", encoding="utf-8")

            with self.assertRaisesRegex(IdentityError, "not clean"):
                launcher._validate_executing_controller(
                    source,
                    controller_paths=paths,
                )

    def test_controller_identity_rejects_wrong_head(self):
        with tempfile.TemporaryDirectory() as temporary:
            repo, paths, commit = _initialize_controller_repo(
                Path(temporary) / "controller"
            )
            source = launcher._source_identity(repo, commit)
            (repo / "README.md").write_text("advanced\n", encoding="utf-8")
            _commit(repo, "advance controller head")

            with self.assertRaisesRegex(IdentityError, "HEAD differs"):
                launcher._validate_executing_controller(
                    source,
                    controller_paths=paths,
                )

    def test_controller_identity_rejects_supervisor_root_mismatch(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve(strict=True)
            source_repo, _source_paths, source_commit = _initialize_controller_repo(
                root / "source"
            )
            other_repo, other_paths, _other_commit = _initialize_controller_repo(
                root / "other"
            )
            source = launcher._source_identity(source_repo, source_commit)

            with self.assertRaisesRegex(
                IdentityError,
                "differs from the supervisor root",
            ):
                launcher._validate_executing_controller(
                    source,
                    controller_paths=other_paths,
                )
            self.assertNotEqual(source_repo, other_repo)

    def test_controller_identity_failure_precedes_campaign_and_worktree_allocation(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = LauncherFixture(Path(temporary))
            fixture.initialize_catalog()
            arguments = fixture.prepare_arguments(targets=("agy",))
            validator = mock.Mock(
                side_effect=IdentityError("forced controller identity failure")
            )
            arguments["_controller_identity_validator"] = validator
            real_git = launcher._git
            git_arguments: list[list[str]] = []

            def observe_git(git, repo, command, **kwargs):
                git_arguments.append(list(command))
                return real_git(git, repo, command, **kwargs)

            with (
                mock.patch.object(launcher, "_git", side_effect=observe_git),
                self.assertRaisesRegex(IdentityError, "forced controller"),
            ):
                launcher.prepare_campaign(**arguments)

            validator.assert_called_once()
            self.assertFalse(Path(arguments["campaign_root"]).exists())
            self.assertFalse((fixture.worktrees / "launch-one-agy").exists())
            self.assertFalse(
                any(command[:2] == ["worktree", "add"] for command in git_arguments)
            )

    def test_catalog_init_verifies_every_target_once_and_is_body_free(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = LauncherFixture(Path(temporary))
            calls: list[str] = []

            def qualification(manifest, **kwargs):
                calls.append(manifest.target)
                self.assertEqual(kwargs["expected_controller"], "controller")
                self.assertEqual(kwargs["expected_campaign_id"], "warm-campaign")
                self.assertEqual(kwargs["expected_session_profile"], "regular")
                profile = fixture.profiles.get(manifest.target)
                return {
                    "target": manifest.target,
                    "private_profile_root": (
                        str(profile) if profile is not None else None
                    ),
                }

            with mock.patch.object(
                launcher.AdapterManifest,
                "verify_qualification",
                autospec=True,
                side_effect=qualification,
            ):
                result = launcher.initialize_catalog(**fixture.catalog_arguments())

            self.assertEqual(sorted(calls), sorted(launcher.TARGET_ORDER))
            self.assertEqual(result["state"], "warm")
            self.assertEqual(list(result["targets"]), list(launcher.TARGET_ORDER))
            self.assertNotIn(
                fixture.prompt_canary.strip(),
                fixture.catalog.read_text(encoding="utf-8"),
            )
            self.assertEqual(fixture.catalog.stat().st_mode & 0o777, 0o600)
            self.assertEqual(
                launcher._load_catalog(fixture.catalog)["catalog_sha256"],
                result["catalog_sha256"],
            )

    def test_catalog_init_rejects_source_only_manifest_before_publication(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = LauncherFixture(Path(temporary))
            value = json.loads(
                fixture.manifests["cursor"].read_text(encoding="utf-8")
            )
            value["doctor_only"] = True
            value["qualification"] = None
            value["capabilities"] = {
                name: "declared" for name in value["capabilities"]
            }
            _write_json(fixture.manifests["cursor"], value)
            with self.assertRaises(IdentityError):
                fixture.initialize_catalog()
            self.assertFalse(fixture.catalog.exists())

    def test_catalog_is_create_only(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = LauncherFixture(Path(temporary))
            fixture.initialize_catalog()
            original = fixture.catalog.read_bytes()
            with self.assertRaises(ValidationError):
                fixture.initialize_catalog()
            self.assertEqual(fixture.catalog.read_bytes(), original)

    def test_prepare_all_compiles_concurrently_and_fanout_accepts_exact_plans(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = LauncherFixture(Path(temporary))
            fixture.initialize_catalog()
            real_compile = launcher.compile_operator_plan
            barrier = threading.Barrier(len(launcher.TARGET_ORDER))

            def compile_plan(**kwargs):
                barrier.wait(timeout=5)
                return real_compile(**kwargs)

            with mock.patch.object(
                launcher,
                "compile_operator_plan",
                side_effect=compile_plan,
            ):
                result = launcher.prepare_campaign(**fixture.prepare_arguments())

            self.assertEqual(result["state"], "ready")
            self.assertEqual(result["targets"], list(launcher.TARGET_ORDER))
            self.assertEqual(
                result["request"]["mutation_owner"],
                "none",
            )
            plans = [
                Path(result["lanes"][target]["plan"])
                for target in result["targets"]
            ]
            loaded = launcher.puppet_fanout.load_lane_plans(plans)
            self.assertEqual(
                [lane.target for lane in loaded],
                sorted(launcher.TARGET_ORDER),
            )
            for target in launcher.TARGET_ORDER:
                lane = result["lanes"][target]
                repo = Path(lane["repository"])
                self.assertEqual(_git(repo, "rev-parse", "HEAD"), fixture.commit)
                self.assertEqual(_git(repo, "branch", "--show-current"), lane["branch"])
                self.assertEqual(_git(repo, "status", "--porcelain=v1"), "")
            encoded = json.dumps(result, sort_keys=True)
            self.assertNotIn(fixture.prompt_canary.strip(), encoded)
            state = json.loads(
                (Path(result["roots"]["campaign"]) / "prepare-state.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(state["state"], "ready")
            self.assertFalse(state["automatic_cleanup"])

    def test_prepare_selected_mix_allocates_only_requested_targets(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = LauncherFixture(Path(temporary))
            fixture.initialize_catalog()
            result = launcher.prepare_campaign(
                **fixture.prepare_arguments(
                    targets=("claude,cursor",),
                )
            )
            self.assertEqual(result["targets"], ["claude", "cursor"])
            self.assertEqual(set(result["lanes"]), {"claude", "cursor"})
            self.assertFalse((fixture.worktrees / "launch-one-agy").exists())

    def test_prepare_prebinds_exact_transcript_free_checkpoint_assignments(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = LauncherFixture(Path(temporary))
            fixture.initialize_catalog()
            result = launcher.prepare_campaign(
                **fixture.prepare_arguments(targets=("agy,codex",))
            )
            for target in result["targets"]:
                binding = result["lanes"][target]["source_checkpoint"]
                assignment_path = Path(binding["assignment"]["path"])
                assignment = json.loads(
                    assignment_path.read_text(encoding="utf-8")
                )
                self.assertEqual(assignment["target"], target)
                self.assertEqual(
                    assignment["output"]["path"],
                    binding["path"],
                )
                self.assertEqual(
                    assignment["handoff"]["exact_fields"],
                    sorted(launcher.SOURCE_FIELDS),
                )
                self.assertEqual(
                    assignment["handoff"]["fixed_fields"]["session"],
                    result["lanes"][target]["session"],
                )
                constraints = assignment["handoff"]["agent_field_constraints"]
                self.assertIn("40-character", constraints["candidate_commit"])
                self.assertIn("timezone", constraints["timestamp"])
                self.assertIn("nonempty", constraints["summary"])
                self.assertIn("list", constraints["claims"])
                self.assertIn("remain in the interactive harness", " ".join(
                    assignment["instructions"]
                ))
                self.assertFalse(Path(binding["path"]).exists())
                self.assertEqual(assignment_path.stat().st_mode & 0o777, 0o600)
                encoded = json.dumps(assignment, sort_keys=True)
                self.assertNotIn(fixture.prompt_canary.strip(), encoded)
                self.assertNotIn("transcript", encoded.lower())

    def test_checkpoint_collects_two_lanes_concurrently_without_review_or_accept(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = LauncherFixture(Path(temporary))
            fixture.initialize_catalog()
            campaign = launcher.prepare_campaign(
                **fixture.prepare_arguments(targets=("codex,claude",))
            )
            runner = CheckpointRunner(
                campaign,
                send_barrier=threading.Barrier(2),
            )
            result = launcher.collect_checkpoints(
                campaign=campaign,
                timeout=0.5,
                _runner=runner,
                _poll_interval=0.001,
            )
            self.assertTrue(result["ok"])
            self.assertEqual(result["state"], "complete")
            self.assertEqual(
                result["succeeded_targets"],
                ["codex", "claude"],
            )
            self.assertFalse(result["automatic_review"])
            self.assertFalse(result["automatic_accept"])
            self.assertFalse(result["automatic_halt"])
            self.assertFalse(result["raw_output_retained"])
            for target in result["targets"]:
                self.assertEqual(
                    [action for lane, action in runner.calls if lane == target],
                    ["status", "send", "checkpoint", "wait"],
                )
                self.assertEqual(
                    result["lanes"][target]["checkpoint"]["path"],
                    campaign["lanes"][target]["source_checkpoint"]["path"],
                )
            self.assertFalse(
                {"review", "accept", "halt"} & {action for _, action in runner.calls}
            )
            encoded = json.dumps(result, sort_keys=True)
            self.assertNotIn(fixture.prompt_canary.strip(), encoded)

    def test_checkpoint_timeout_is_lane_local_and_returns_partial_result(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = LauncherFixture(Path(temporary))
            fixture.initialize_catalog()
            campaign = launcher.prepare_campaign(
                **fixture.prepare_arguments(targets=("cursor,grok",))
            )
            runner = CheckpointRunner(
                campaign,
                timeout_targets={"grok"},
            )
            result = launcher.collect_checkpoints(
                campaign=campaign,
                timeout=0.03,
                _runner=runner,
                _poll_interval=0.005,
            )
            self.assertFalse(result["ok"])
            self.assertEqual(result["state"], "partial")
            self.assertEqual(result["succeeded_targets"], ["cursor"])
            self.assertEqual(result["failed_targets"], ["grok"])
            self.assertEqual(
                result["lanes"]["grok"]["error"],
                "checkpoint_timeout",
            )
            self.assertEqual(
                [action for lane, action in runner.calls if lane == "grok"],
                ["status", "send"],
            )
            self.assertEqual(
                [action for lane, action in runner.calls if lane == "cursor"],
                ["status", "send", "checkpoint", "wait"],
            )

    def test_checkpoint_rejects_stale_output_before_import(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = LauncherFixture(Path(temporary))
            fixture.initialize_catalog()
            campaign = launcher.prepare_campaign(
                **fixture.prepare_arguments(targets=("agy",))
            )
            output = Path(
                campaign["lanes"]["agy"]["source_checkpoint"]["path"]
            )
            output.write_bytes(b"{}\n")
            output.chmod(0o600)
            first_runner = CheckpointRunner(
                campaign,
                delivery_by_target={"agy": "already_submitted"},
            )
            first = launcher.collect_checkpoints(
                campaign=campaign,
                timeout=0.1,
                _runner=first_runner,
                _poll_interval=0.001,
            )
            self.assertEqual(first["state"], "failed")
            self.assertEqual(
                first["lanes"]["agy"]["error"],
                "stale_checkpoint_path",
            )
            self.assertEqual(first_runner.calls, [("agy", "status")])
            second_runner = CheckpointRunner(
                campaign,
                delivery_by_target={"agy": "already_submitted"},
            )
            second = launcher.collect_checkpoints(
                campaign=campaign,
                timeout=0.1,
                _runner=second_runner,
                _poll_interval=0.001,
            )
            self.assertEqual(
                second["lanes"]["agy"]["error"],
                "stale_checkpoint_path",
            )
            self.assertEqual(second_runner.calls, [("agy", "status")])

    def test_checkpoint_recovers_after_prior_assignment_delivery(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = LauncherFixture(Path(temporary))
            fixture.initialize_catalog()
            campaign = launcher.prepare_campaign(
                **fixture.prepare_arguments(targets=("claude",))
            )
            first_runner = CheckpointRunner(
                campaign,
                timeout_targets={"claude"},
            )
            first = launcher.collect_checkpoints(
                campaign=campaign,
                timeout=0.02,
                _runner=first_runner,
                _poll_interval=0.005,
            )
            self.assertEqual(
                first["lanes"]["claude"]["error"],
                "checkpoint_timeout",
            )
            binding = campaign["lanes"]["claude"]["source_checkpoint"]
            self.assertTrue(Path(binding["delivery_receipt"]).is_file())
            output = Path(binding["path"])
            output.write_bytes(b"{}\n")
            output.chmod(0o600)
            campaign_path = (
                Path(campaign["roots"]["campaign"]) / "campaign.json"
            )
            campaign = launcher._load_campaign(campaign_path)
            second_runner = CheckpointRunner(
                campaign,
                delivery_by_target={"claude": "already_submitted"},
            )
            second = launcher.collect_checkpoints(
                campaign=campaign,
                timeout=0.1,
                _runner=second_runner,
                _poll_interval=0.001,
            )
            self.assertTrue(second["ok"])
            self.assertEqual(
                [action for _, action in second_runner.calls],
                ["status", "send", "checkpoint", "wait"],
            )

    def test_checkpoint_is_idempotent_after_exact_import(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = LauncherFixture(Path(temporary))
            fixture.initialize_catalog()
            campaign = launcher.prepare_campaign(
                **fixture.prepare_arguments(targets=("codex",))
            )
            lane = launcher.puppet_fanout.load_lane_plans(
                [Path(campaign["lanes"]["codex"]["plan"])]
            )[0]
            binding = campaign["lanes"]["codex"]["source_checkpoint"]
            launcher._publish_checkpoint_delivery_receipt(
                campaign=campaign,
                lane=lane,
                binding=binding,
            )
            output = Path(
                binding["path"]
            )
            output.write_bytes(b"{}\n")
            output.chmod(0o600)
            runner = CheckpointRunner(
                campaign,
                imported_targets={"codex"},
            )
            result = launcher.collect_checkpoints(
                campaign=campaign,
                timeout=0,
                _runner=runner,
            )
            self.assertTrue(result["ok"])
            self.assertEqual(
                result["lanes"]["codex"]["delivery"],
                "already_imported",
            )
            self.assertEqual(runner.calls, [("codex", "status")])

    def test_checkpoint_already_imported_requires_delivery_receipt(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = LauncherFixture(Path(temporary))
            fixture.initialize_catalog()
            campaign = launcher.prepare_campaign(
                **fixture.prepare_arguments(targets=("agy",))
            )
            output = Path(
                campaign["lanes"]["agy"]["source_checkpoint"]["path"]
            )
            output.write_bytes(b"{}\n")
            output.chmod(0o600)
            runner = CheckpointRunner(
                campaign,
                imported_targets={"agy"},
            )
            result = launcher.collect_checkpoints(
                campaign=campaign,
                timeout=0,
                _runner=runner,
            )
            self.assertFalse(result["ok"])
            self.assertEqual(
                result["lanes"]["agy"]["error"],
                "checkpoint_delivery_receipt_missing",
            )
            self.assertEqual(runner.calls, [("agy", "status")])

    def test_checkpoint_already_imported_rejects_tampered_current_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = LauncherFixture(Path(temporary))
            fixture.initialize_catalog()
            campaign = launcher.prepare_campaign(
                **fixture.prepare_arguments(targets=("cursor",))
            )
            lane = launcher.puppet_fanout.load_lane_plans(
                [Path(campaign["lanes"]["cursor"]["plan"])]
            )[0]
            binding = campaign["lanes"]["cursor"]["source_checkpoint"]
            launcher._publish_checkpoint_delivery_receipt(
                campaign=campaign,
                lane=lane,
                binding=binding,
            )
            output = Path(
                binding["path"]
            )
            output.write_bytes(b'{"a":1}\n')
            output.chmod(0o600)
            runner = CheckpointRunner(
                campaign,
                imported_targets={"cursor"},
            )
            recorded_reference = runner._reference("cursor")
            output.write_bytes(b'{"b":2}\n')
            output.chmod(0o600)
            with mock.patch.object(
                runner,
                "_reference",
                return_value=recorded_reference,
            ):
                result = launcher.collect_checkpoints(
                    campaign=campaign,
                    timeout=0,
                    _runner=runner,
                )
            self.assertFalse(result["ok"])
            self.assertEqual(
                result["lanes"]["cursor"]["error"],
                "checkpoint_artifact_changed",
            )
            self.assertEqual(runner.calls, [("cursor", "status")])

    def test_checkpoint_assignment_or_output_path_tamper_fails_closed(self):
        for label in ("assignment", "output_path"):
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temporary:
                fixture = LauncherFixture(Path(temporary))
                fixture.initialize_catalog()
                campaign = launcher.prepare_campaign(
                    **fixture.prepare_arguments(targets=("grok",))
                )
                campaign_path = (
                    Path(campaign["roots"]["campaign"]) / "campaign.json"
                )
                if label == "assignment":
                    assignment_path = Path(
                        campaign["lanes"]["grok"]["source_checkpoint"][
                            "assignment"
                        ]["path"]
                    )
                    assignment = json.loads(
                        assignment_path.read_text(encoding="utf-8")
                    )
                    assignment["output"]["max_bytes"] -= 1
                    assignment_path.write_text(
                        json.dumps(assignment, sort_keys=True) + "\n",
                        encoding="utf-8",
                    )
                    assignment_path.chmod(0o600)
                else:
                    _rewrite_campaign(
                        campaign_path,
                        lambda value: value["lanes"]["grok"][
                            "source_checkpoint"
                        ].__setitem__(
                            "path",
                            str(Path(value["roots"]["campaign"]) / "other.json"),
                        ),
                    )
                with self.assertRaises(IdentityError):
                    launcher._load_campaign(campaign_path)

    def test_prepare_mutating_mix_derives_target_ownership(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = LauncherFixture(Path(temporary))
            fixture.initialize_catalog()
            result = launcher.prepare_campaign(
                **fixture.prepare_arguments(
                    targets=("codex",),
                    modes=("read", "test", "mutate", "local_commit"),
                )
            )
            self.assertEqual(result["request"]["mutation_owner"], "codex")
            plan = json.loads(
                Path(result["lanes"]["codex"]["plan"]).read_text(encoding="utf-8")
            )
            contract = json.loads(
                Path(plan["artifacts"]["contract"]["path"]).read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(contract["mutation_owner"], "target")
            self.assertEqual(
                contract["supervisor_root"],
                str(fixture.source),
            )

    def test_prepare_multi_target_mutation_has_one_owner_and_read_only_support(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = LauncherFixture(Path(temporary))
            fixture.initialize_catalog()
            arguments = fixture.prepare_arguments(
                targets=("codex,claude,cursor",),
                modes=("read", "test", "mutate", "local_commit"),
            )
            arguments["mutation_owner_target"] = "claude"
            result = launcher.prepare_campaign(**arguments)

            self.assertEqual(result["request"]["mutation_owner"], "claude")
            for target in result["targets"]:
                plan = json.loads(
                    Path(result["lanes"][target]["plan"]).read_text(
                        encoding="utf-8"
                    )
                )
                contract = json.loads(
                    Path(plan["artifacts"]["contract"]["path"]).read_text(
                        encoding="utf-8"
                    )
                )
                if target == "claude":
                    self.assertEqual(contract["mutation_owner"], "target")
                    self.assertEqual(
                        set(contract["allowed_modes"]),
                        {"read", "test", "mutate", "local_commit"},
                    )
                else:
                    self.assertEqual(contract["mutation_owner"], "none")
                    self.assertEqual(
                        set(contract["allowed_modes"]),
                        {"read", "test"},
                    )

    def test_branch_collision_fails_before_second_campaign_root_exists(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = LauncherFixture(Path(temporary))
            fixture.initialize_catalog()
            launcher.prepare_campaign(
                **fixture.prepare_arguments(targets=("grok",))
            )
            arguments = fixture.prepare_arguments(targets=("grok",))
            arguments["campaign_root"] = fixture.campaigns / "second-root"
            with self.assertRaises(ValidationError):
                launcher.prepare_campaign(**arguments)
            self.assertFalse((fixture.campaigns / "second-root").exists())

    def test_dirty_source_fails_before_campaign_or_worktree_creation(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = LauncherFixture(Path(temporary))
            fixture.initialize_catalog()
            (fixture.source / "dirty.txt").write_text("dirty\n", encoding="utf-8")
            with self.assertRaises(IdentityError):
                launcher.prepare_campaign(
                    **fixture.prepare_arguments(targets=("agy",))
                )
            self.assertFalse((fixture.campaigns / "launch-one").exists())
            self.assertFalse((fixture.worktrees / "launch-one-agy").exists())

    def test_source_may_be_an_existing_sibling_under_worktree_parent(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = LauncherFixture(Path(temporary))
            fixture.initialize_catalog()
            sibling_source = fixture.worktrees / "operator-source"
            _git(
                fixture.source,
                "worktree",
                "add",
                "-b",
                "codex/operator-source",
                str(sibling_source),
                fixture.commit,
            )
            arguments = fixture.prepare_arguments(targets=("agy",))
            arguments["source_repo"] = sibling_source
            result = launcher.prepare_campaign(**arguments)

            self.assertEqual(result["source"]["repo"], str(sibling_source))
            self.assertEqual(
                result["lanes"]["agy"]["repository"],
                str(fixture.worktrees / "launch-one-agy"),
            )
            plan = json.loads(
                Path(result["lanes"]["agy"]["plan"]).read_text(encoding="utf-8")
            )
            contract = json.loads(
                Path(plan["artifacts"]["contract"]["path"]).read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(contract["supervisor_root"], str(sibling_source))

    def test_partial_worktree_failure_is_preserved_without_cleanup(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = LauncherFixture(Path(temporary))
            fixture.initialize_catalog()
            real_git = launcher._git
            worktree_adds = 0

            def failing_git(git, repo, arguments, **kwargs):
                nonlocal worktree_adds
                if arguments[:2] == ["worktree", "add"]:
                    worktree_adds += 1
                    if worktree_adds == 2:
                        raise ValidationError("forced worktree failure")
                return real_git(git, repo, arguments, **kwargs)

            with (
                mock.patch.object(launcher, "_git", side_effect=failing_git),
                self.assertRaises(ValidationError),
            ):
                launcher.prepare_campaign(
                    **fixture.prepare_arguments(targets=("agy", "codex"))
                )
            state = json.loads(
                (fixture.campaigns / "launch-one" / "prepare-state.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(state["state"], "blocked")
            self.assertEqual(len(state["created_worktrees"]), 1)
            self.assertEqual(len(state["attempted_worktrees"]), 2)
            self.assertEqual(
                [row["target"] for row in state["ambiguous_worktrees"]],
                ["codex"],
            )
            self.assertFalse(state["automatic_cleanup"])
            self.assertTrue((fixture.worktrees / "launch-one-agy").is_dir())

    def test_post_add_probe_failure_records_created_worktree(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = LauncherFixture(Path(temporary))
            fixture.initialize_catalog()
            real_git_text = launcher._git_text
            candidate = fixture.worktrees / "launch-one-agy"

            def failing_git_text(git, repo, arguments):
                if repo == candidate and arguments == ["rev-parse", "HEAD"]:
                    raise ValidationError("forced post-add probe failure")
                return real_git_text(git, repo, arguments)

            with (
                mock.patch.object(
                    launcher,
                    "_git_text",
                    side_effect=failing_git_text,
                ),
                self.assertRaises(ValidationError),
            ):
                launcher.prepare_campaign(
                    **fixture.prepare_arguments(targets=("agy",))
                )

            state = json.loads(
                (fixture.campaigns / "launch-one" / "prepare-state.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(state["state"], "blocked")
            self.assertEqual(
                [row["target"] for row in state["attempted_worktrees"]],
                ["agy"],
            )
            self.assertEqual(
                [row["target"] for row in state["created_worktrees"]],
                ["agy"],
            )
            self.assertEqual(state["ambiguous_worktrees"], [])
            self.assertTrue(candidate.is_dir())

    def test_worktree_add_interrupt_records_ambiguous_candidate(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = LauncherFixture(Path(temporary))
            fixture.initialize_catalog()
            real_git = launcher._git

            def interrupted_git(git, repo, arguments, **kwargs):
                if arguments[:2] == ["worktree", "add"]:
                    raise KeyboardInterrupt
                return real_git(git, repo, arguments, **kwargs)

            with (
                mock.patch.object(launcher, "_git", side_effect=interrupted_git),
                self.assertRaises(KeyboardInterrupt),
            ):
                launcher.prepare_campaign(
                    **fixture.prepare_arguments(targets=("agy",))
                )

            state = json.loads(
                (fixture.campaigns / "launch-one" / "prepare-state.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(state["state"], "blocked")
            self.assertEqual(state["error"], "operator_interrupted")
            self.assertEqual(state["created_worktrees"], [])
            self.assertEqual(
                [row["target"] for row in state["ambiguous_worktrees"]],
                ["agy"],
            )
            self.assertFalse(state["automatic_cleanup"])

    def test_run_executes_one_exact_fanout_after_preparation(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = LauncherFixture(Path(temporary))
            fixture.initialize_catalog()
            captured: list[list[str]] = []
            stdout = io.StringIO()
            stderr = io.StringIO()
            argv = fixture.run_argv(
                launch_id="run-mix",
                targets=("agy,codex,claude",),
            )
            argv.append("--open-views")
            with (
                contextlib.redirect_stdout(stdout),
                contextlib.redirect_stderr(stderr),
                mock.patch.object(
                    launcher,
                    "execute_fanout",
                    side_effect=lambda value: captured.append(list(value)),
                ),
                mock.patch.object(
                    launcher,
                    "_validate_executing_controller",
                    return_value=None,
                ),
            ):
                self.assertEqual(launcher.main(argv), 0)

            self.assertEqual(len(captured), 1)
            command = captured[0]
            self.assertEqual(command[2], "launch")
            self.assertIn("--allow-live-launch", command)
            self.assertIn("--open-views", command)
            self.assertEqual(command.count("--plan"), 3)
            campaign = fixture.campaigns / "run-mix" / "campaign.json"
            self.assertTrue(campaign.is_file())
            canary = fixture.prompt_canary.strip()
            self.assertNotIn(canary, "\n".join(command))
            self.assertNotIn(canary, stdout.getvalue())
            self.assertNotIn(canary, stderr.getvalue())
            for artifact in campaign.parent.rglob("*.json"):
                self.assertNotIn(
                    canary,
                    artifact.read_text(encoding="utf-8"),
                    str(artifact),
                )

    def test_run_without_live_acknowledgement_creates_nothing(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = LauncherFixture(Path(temporary))
            fixture.initialize_catalog()
            argv = fixture.run_argv(launch_id="no-ack", targets=("claude",))
            argv.remove("--allow-live-launch")
            with mock.patch.object(launcher, "execute_fanout") as execute:
                self.assertEqual(launcher.main(argv), 2)
            execute.assert_not_called()
            self.assertFalse((fixture.campaigns / "no-ack").exists())

    def test_lifecycle_uses_only_exact_campaign_plan_set(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = LauncherFixture(Path(temporary))
            fixture.initialize_catalog()
            result = launcher.prepare_campaign(
                **fixture.prepare_arguments(targets=("cursor,grok",))
            )
            campaign_path = Path(result["roots"]["campaign"]) / "campaign.json"
            captured: list[list[str]] = []
            with mock.patch.object(
                launcher,
                "execute_fanout",
                side_effect=lambda value: captured.append(list(value)),
            ):
                self.assertEqual(
                    launcher.main(["halt", "--campaign", str(campaign_path)]),
                    0,
                )
            self.assertEqual(captured[0][2], "halt")
            self.assertEqual(captured[0].count("--plan"), 2)
            self.assertNotIn("--allow-live-launch", captured[0])

    def test_all_five_campaign_loads_and_delegates_exactly_five_plans(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = LauncherFixture(Path(temporary))
            fixture.initialize_catalog()
            result = launcher.prepare_campaign(**fixture.prepare_arguments())
            campaign_path = Path(result["roots"]["campaign"]) / "campaign.json"

            loaded = launcher._load_campaign(campaign_path)
            self.assertEqual(loaded["targets"], list(launcher.TARGET_ORDER))
            captured: list[list[str]] = []
            with mock.patch.object(
                launcher,
                "execute_fanout",
                side_effect=lambda value: captured.append(list(value)),
            ):
                self.assertEqual(
                    launcher.main(["status", "--campaign", str(campaign_path)]),
                    0,
                )
            self.assertEqual(len(captured), 1)
            self.assertEqual(captured[0][2], "status")
            self.assertEqual(captured[0].count("--plan"), 5)
            expected_plans = [
                result["lanes"][target]["plan"] for target in launcher.TARGET_ORDER
            ]
            actual_plans = [
                captured[0][index + 1]
                for index, value in enumerate(captured[0])
                if value == "--plan"
            ]
            self.assertEqual(actual_plans, expected_plans)

    def test_campaign_cannot_swap_to_another_campaign_plan_or_session(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = LauncherFixture(Path(temporary))
            fixture.initialize_catalog()
            first = launcher.prepare_campaign(
                **fixture.prepare_arguments(
                    launch_id="campaign-a",
                    targets=("agy",),
                )
            )
            second = launcher.prepare_campaign(
                **fixture.prepare_arguments(
                    launch_id="campaign-b",
                    targets=("agy",),
                )
            )
            first_path = Path(first["roots"]["campaign"]) / "campaign.json"

            def swap(value):
                value["lanes"]["agy"] = copy.deepcopy(second["lanes"]["agy"])
                value["plan_set_sha256"] = second["plan_set_sha256"]

            _rewrite_campaign(first_path, swap)
            with self.assertRaises(IdentityError):
                launcher._load_campaign(first_path)
            with mock.patch.object(launcher, "execute_fanout") as execute:
                self.assertEqual(
                    launcher.main(["halt", "--campaign", str(first_path)]),
                    2,
                )
            execute.assert_not_called()

    def test_campaign_plan_or_controller_tamper_never_reaches_fanout_exec(self):
        cases = {
            "campaign": lambda _fixture, _result, path: (
                _rewrite_campaign_without_rehash(
                    path,
                    lambda value: value.__setitem__("state", "blocked"),
                )
            ),
            "plan": lambda _fixture, result, _path: Path(
                result["lanes"]["agy"]["plan"]
            ).write_text(
                Path(result["lanes"]["agy"]["plan"]).read_text(encoding="utf-8")
                + " ",
                encoding="utf-8",
            ),
            "launcher": lambda _fixture, _result, path: _rewrite_campaign(
                path,
                lambda value: value["launcher"].__setitem__("sha256", "e" * 64),
            ),
            "fanout": lambda _fixture, _result, path: _rewrite_campaign(
                path,
                lambda value: value["launcher"].__setitem__(
                    "fanout_sha256",
                    "e" * 64,
                ),
            ),
        }
        for label, tamper in cases.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temporary:
                fixture = LauncherFixture(Path(temporary))
                fixture.initialize_catalog()
                result = launcher.prepare_campaign(
                    **fixture.prepare_arguments(targets=("agy",))
                )
                campaign_path = (
                    Path(result["roots"]["campaign"]) / "campaign.json"
                )
                tamper(fixture, result, campaign_path)
                stdout = io.StringIO()
                stderr = io.StringIO()
                with (
                    contextlib.redirect_stdout(stdout),
                    contextlib.redirect_stderr(stderr),
                    mock.patch.object(launcher, "execute_fanout") as execute,
                ):
                    self.assertEqual(
                        launcher.main(
                            ["status", "--campaign", str(campaign_path)]
                        ),
                        2,
                    )
                execute.assert_not_called()
                self.assertNotIn(fixture.prompt_canary.strip(), stdout.getvalue())
                self.assertNotIn(fixture.prompt_canary.strip(), stderr.getvalue())

    def test_campaign_artifacts_are_private_create_only_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = LauncherFixture(Path(temporary))
            fixture.initialize_catalog()
            result = launcher.prepare_campaign(
                **fixture.prepare_arguments(targets=("agy,codex",))
            )
            campaign_root = Path(result["roots"]["campaign"])
            self.assertEqual(fixture.catalog.stat().st_mode & 0o777, 0o600)
            for path in campaign_root.rglob("*"):
                if path.is_dir():
                    self.assertEqual(
                        path.stat().st_mode & 0o777,
                        0o700,
                        str(path),
                    )
                elif path.is_file():
                    self.assertEqual(
                        path.stat().st_mode & 0o777,
                        0o600,
                        str(path),
                    )
            campaign_path = campaign_root / "campaign.json"
            original = campaign_path.read_bytes()
            with self.assertRaises(ValidationError):
                launcher._create_only_json(
                    campaign_path,
                    {"replacement": True},
                )
            self.assertEqual(campaign_path.read_bytes(), original)

    def test_catalog_prompt_and_campaign_symlinks_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = LauncherFixture(Path(temporary))
            fixture.initialize_catalog()
            catalog_link = fixture.root / "catalog-link.json"
            catalog_link.symlink_to(fixture.catalog)
            with self.assertRaises(IdentityError):
                launcher._load_catalog(catalog_link)

            prompt_link = fixture.root / "prompt-link.txt"
            prompt_link.symlink_to(fixture.prompt)
            arguments = fixture.prepare_arguments(targets=("agy",))
            arguments["prompt_path"] = prompt_link
            with self.assertRaises(IdentityError):
                launcher.prepare_campaign(**arguments)
            self.assertFalse(Path(arguments["campaign_root"]).exists())

            result = launcher.prepare_campaign(
                **fixture.prepare_arguments(
                    launch_id="real-campaign",
                    targets=("agy",),
                )
            )
            campaign_path = Path(result["roots"]["campaign"]) / "campaign.json"
            campaign_link = fixture.root / "campaign-link.json"
            campaign_link.symlink_to(campaign_path)
            with mock.patch.object(launcher, "execute_fanout") as execute:
                self.assertEqual(
                    launcher.main(
                        ["status", "--campaign", str(campaign_link)]
                    ),
                    2,
                )
            execute.assert_not_called()

    def test_launcher_source_is_outside_adapter_authority_fingerprint(self):
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary).resolve() / "puppet"
            shutil.copytree(ROOT / "skills" / "puppet", copied)
            before = launcher.adapter_implementation_fingerprint(copied)
            launch_copy = copied / "scripts" / "puppet_launch.py"
            launch_copy.write_text(
                launch_copy.read_text(encoding="utf-8")
                + "\n# test-only launcher change\n",
                encoding="utf-8",
            )
            after = launcher.adapter_implementation_fingerprint(copied)
            self.assertEqual(before, after)

    def test_execute_fanout_delegates_exact_argv_via_execv(self):
        argv = ["/exact/python", "/exact/fanout.py", "status", "--plan", "/p"]
        with mock.patch.object(launcher.os, "execv", return_value=None) as execv:
            with self.assertRaisesRegex(AssertionError, "execv returned"):
                launcher.execute_fanout(argv)
        execv.assert_called_once_with(argv[0], argv)

    def test_campaign_rejects_catalog_or_prompt_drift(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = LauncherFixture(Path(temporary))
            fixture.initialize_catalog()
            result = launcher.prepare_campaign(
                **fixture.prepare_arguments(targets=("agy",))
            )
            campaign_path = Path(result["roots"]["campaign"]) / "campaign.json"
            fixture.prompt.write_text("changed\n", encoding="utf-8")
            with self.assertRaises(IdentityError):
                launcher._load_campaign(campaign_path)

    def test_catalog_rejects_self_consistent_authority_mismatch(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = LauncherFixture(Path(temporary))
            result = fixture.initialize_catalog()
            result["controller"] = "other-controller"
            unhashed = dict(result)
            unhashed.pop("catalog_sha256")
            result["catalog_sha256"] = launcher.sha256_bytes(
                launcher.canonical_json_bytes(unhashed)
            )
            fixture.catalog.write_text(
                json.dumps(result, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            with self.assertRaises(IdentityError):
                launcher._load_catalog(fixture.catalog)

    def test_target_selection_and_modes_fail_closed(self):
        self.assertEqual(
            launcher._selected_targets(["grok,agy"]),
            ("agy", "grok"),
        )
        for values in (["all", "agy"], ["agy", "agy"], ["pi"], []):
            with self.subTest(values=values), self.assertRaises(ValidationError):
                launcher._selected_targets(values)
        for modes in (["read", "read"], ["deploy"], ["read", "deploy"]):
            with self.subTest(modes=modes), self.assertRaises(ValidationError):
                launcher._validate_modes(modes)
        with self.assertRaises(ValidationError):
            launcher._mutation_owner(
                ("agy", "codex"),
                ("mutate",),
                None,
            )
        with self.assertRaises(ValidationError):
            launcher._mutation_owner(
                ("agy", "codex"),
                ("read", "test"),
                "agy",
            )
        with self.assertRaises(ValidationError):
            launcher._mutation_owner(
                ("agy", "codex"),
                ("read", "mutate"),
                "grok",
            )
        with self.assertRaises(ValidationError):
            launcher._mutation_owner(
                ("agy", "codex"),
                ("mutate",),
                "codex",
            )

    def test_cli_duplicate_or_unknown_targets_fail_before_preparation(self):
        selections = (
            ("agy", "agy"),
            ("agy,agy",),
            ("all", "grok"),
            ("pi",),
        )
        for index, targets in enumerate(selections):
            with (
                self.subTest(targets=targets),
                tempfile.TemporaryDirectory() as temporary,
            ):
                fixture = LauncherFixture(Path(temporary))
                fixture.initialize_catalog()
                argv = fixture.run_argv(
                    launch_id="bad-target-%d" % index,
                    targets=targets,
                )
                with mock.patch.object(launcher, "execute_fanout") as execute:
                    self.assertEqual(launcher.main(argv), 2)
                execute.assert_not_called()
                self.assertFalse(
                    (fixture.campaigns / ("bad-target-%d" % index)).exists()
                )

    def test_missing_catalog_target_fails_before_campaign_creation(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = LauncherFixture(Path(temporary))
            result = fixture.initialize_catalog()
            result["targets"].pop("grok")
            unhashed = copy.deepcopy(result)
            unhashed.pop("catalog_sha256")
            result["catalog_sha256"] = launcher.sha256_bytes(
                launcher.canonical_json_bytes(unhashed)
            )
            fixture.catalog.write_text(
                json.dumps(result, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            arguments = fixture.prepare_arguments(targets=("grok",))
            with self.assertRaises(UnsupportedError):
                launcher.prepare_campaign(**arguments)
            self.assertFalse(Path(arguments["campaign_root"]).exists())


if __name__ == "__main__":
    unittest.main()
