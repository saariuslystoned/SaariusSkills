from __future__ import annotations

import copy
import json
import os
import shlex
import signal
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "puppet"
SCRIPTS = SKILL / "scripts"
FANOUT_CLI = SCRIPTS / "puppet_fanout.py"
PUPPET_CLI = SCRIPTS / "puppet.py"

sys.path.insert(0, str(SCRIPTS))
import puppet_fanout as fanout  # noqa: E402
from puppet_lib.census import adapter_implementation_fingerprint  # noqa: E402
from puppet_lib.contracts import MANDATORY_HARD_GATES  # noqa: E402
from puppet_lib.errors import IdentityError, ValidationError  # noqa: E402
from puppet_lib.handoffs import PROTOCOL_FINGERPRINT  # noqa: E402
from puppet_lib.safety import canonical_json_bytes, sha256_bytes, sha256_file  # noqa: E402
from tests.test_puppet_operator_plan import OperatorPlanFixture  # noqa: E402


def _write(path: Path, value: str) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def _artifact(path: Path) -> dict:
    return {
        "path": str(path),
        "sha256": sha256_file(path),
        "bytes": path.stat().st_size,
    }


def _success(argv, value):
    return subprocess.CompletedProcess(
        list(argv),
        0,
        stdout=(json.dumps(value, sort_keys=True) + "\n").encode("utf-8"),
        stderr=b"",
    )


def _launch_success(argv, session):
    _, attach_command = _ticketed_attach(argv, session)
    return _success(
        argv,
        {
            "ok": True,
            "session": session,
            "state": "ACTIVE",
            "instruction_policy_fingerprint": "a" * 64,
            "effective_contract_fingerprint": "b" * 64,
            "attach_command": attach_command,
            "attach_ticket_ttl_seconds": 30,
        },
    )


def _attach_success(argv, session):
    ticket_path, attach_command = _ticketed_attach(argv, session)
    return _success(
        argv,
        {
            "ok": True,
            "session": session,
            "attach_command": attach_command,
            "ticket_path": ticket_path,
            "ticket_ttl_seconds": 30,
            "read_only": True,
            "execution_time_identity_check": True,
        },
    )


def _ticketed_attach(argv, session):
    state_root = Path(argv[argv.index("--state-root") + 1]).resolve(strict=True)
    ticket_path = state_root / "views" / ("%s-%s.json" % (session, "a" * 32))
    command = shlex.join(
        [
            str(Path(sys.executable).resolve(strict=True)),
            str((SCRIPTS / "viewer_attach.py").resolve(strict=True)),
            "--state-root",
            str(state_root),
            "--session",
            session,
            "--ticket",
            str(ticket_path),
        ]
    )
    return str(ticket_path), command


def _status_success(argv, lane, state="ACTIVE"):
    return _success(
        argv,
        {
            "ok": True,
            "session": lane.session,
            "controller": lane.contract.controller,
            "target": lane.target,
            "session_profile": lane.contract.session_profile,
            "repo": str(lane.repository),
            "branch": lane.contract.branch,
            "mutation_owner": lane.contract.mutation_owner,
            "state": state,
            "target_process_alive": state != "HALTED",
            "tmux_alive": True,
            "blocker": None,
        },
    )


def _view_success(argv, session):
    return _success(
        argv,
        {
            "ok": True,
            "session": session,
            "read_only": True,
            "native_tui": True,
            "controller_attached": False,
            "terminal_app": "iTerm",
            "terminal_app_path": "/Applications/iTerm.app",
            "open_request_submitted": True,
            "viewer_attached": True,
            "new_read_only_clients": 1,
            "ticket_revoked": True,
        },
    )


def _halt_success(argv, session):
    return _success(
        argv,
        {
            "ok": True,
            "session": session,
            "state": "HALTED",
            "signal_sent": True,
            "tmux_preserved": True,
        },
    )


def _failure(argv, category="unsupported", detail="lane blocked"):
    return subprocess.CompletedProcess(
        list(argv),
        2,
        stdout=b"",
        stderr=(
            json.dumps(
                {"ok": False, "error": category, "detail": detail},
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8"),
    )


class PlanFactory:
    def __init__(self, root: Path):
        self.root = root
        self.plans = {}

    def create(
        self,
        target: str,
        *,
        session: str | None = None,
        run_root: Path | None = None,
    ) -> Path:
        session = session or ("fanout-%s" % target)
        lane = self.root / target
        repo = lane / "repo"
        repo.mkdir(mode=0o700, parents=True)
        run = run_root or (lane / "run")
        run.mkdir(mode=0o700, parents=True, exist_ok=True)
        proof = run / "proof"
        state = run / "state"
        proof.mkdir(mode=0o700, exist_ok=True)
        state.mkdir(mode=0o700, exist_ok=True)
        profile = None
        if target != "agy":
            profile = lane / "profile"
            profile.mkdir(mode=0o700)

        contract_path = lane / "contract.json"
        manifest_path = lane / "manifest.json"
        authorization_path = lane / "authorization.json"
        input_path = lane / "task.txt"
        contract = {
            "schema_version": 1,
            "objective": "Exercise %s through the fanout coordinator" % target,
            "campaign_authorization_id": "fanout-campaign",
            "controller": "controller",
            "target": target,
            "session_profile": "regular",
            "task_profile": "review",
            "harness_trust": "unrestricted_required",
            "mutation_owner": "none",
            "repo": str(repo),
            "branch": "codex/fanout-%s" % target,
            "max_helpers": 0,
            "allowed_modes": ["read", "test"],
            "terminal_criteria": [
                {"id": "review_complete", "evidence": "validated_handoff"}
            ],
            "hard_gates": sorted(MANDATORY_HARD_GATES),
            "run_id": "run-%s" % target,
            "nonce": "nonce-%s" % target,
            "proof_path_prefixes": ["proof/"],
        }
        _write(contract_path, json.dumps(contract, sort_keys=True) + "\n")
        _write(manifest_path, "{}\n")
        _write(authorization_path, "{}\n")
        _write(input_path, "Perform the bounded task.\n")

        interpreter = Path(sys.executable).resolve(strict=True)
        cli = PUPPET_CLI.resolve(strict=True)
        controller = {
            "version": "0.1.0-bootstrap",
            "adapter_implementation_sha256": adapter_implementation_fingerprint(),
            "protocol_sha256": PROTOCOL_FINGERPRINT,
            "interpreter": str(interpreter),
            "interpreter_sha256": sha256_file(interpreter),
            "cli": str(cli),
            "cli_sha256": sha256_file(cli),
        }
        base = [str(interpreter), str(cli), "--json"]
        common = [
            "--contract",
            str(contract_path),
            "--manifest",
            str(manifest_path),
            "--authorization",
            str(authorization_path),
            "--proof-root",
            str(proof),
            "--state-root",
            str(state),
        ]
        if profile is not None:
            common.extend(["--profile-root", str(profile)])
        session_base = ["--state-root", str(state), "--session", session]
        commands = {
            "doctor": [*base, "doctor", *common],
            "launch": [
                *base,
                "launch",
                "--session",
                session,
                *common,
                "--prompt-file",
                str(input_path),
            ],
            "status": [*base, "status", *session_base],
            "waits": {},
            "attach_command": [*base, "attach-command", *session_base],
            "open_view": [
                *base,
                "open-view",
                *session_base,
                "--terminal",
                "auto",
            ],
            "halt": [*base, "halt", *session_base, "--timeout", "10.0"],
            "profile": {"supported": profile is not None},
        }
        plan = {
            "schema": "puppet.operator-run-plan/v1",
            "state": "planning_only",
            "entry_mode": "cockpit_explicit",
            "target": target,
            "session_profile": "regular",
            "session": session,
            "branch": contract["branch"],
            "launch_authorized": False,
            "blockers": [
                "operator_plan_is_not_launch_authority",
                "doctor_must_pass_at_execution_time",
                *(
                    []
                    if target == "agy"
                    else [
                        "private_profile_must_be_authenticated_at_execution_time"
                    ]
                ),
                "adapter_qualification_must_be_current",
                "human_must_choose_to_execute_launch",
            ],
            "controller": controller,
            "repository": {"repo": str(repo)},
            "supervisor_repository": None,
            "roots": {
                "run": str(run),
                "proof": str(proof),
                "state": str(state),
                "profile": str(profile) if profile is not None else None,
            },
            "artifacts": {
                "contract": _artifact(contract_path),
                "manifest": _artifact(manifest_path),
                "authorization": _artifact(authorization_path),
                "input_payload": _artifact(input_path),
            },
            "commands": commands,
        }
        plan["plan_sha256"] = sha256_bytes(canonical_json_bytes(plan))
        plan_path = lane / "operator-plan.json"
        _write(plan_path, json.dumps(plan, sort_keys=True) + "\n")
        self.plans[target] = plan
        return plan_path


class PuppetFanoutTests(unittest.TestCase):
    def test_five_launches_overlap_and_output_is_target_sorted(self):
        with tempfile.TemporaryDirectory() as temporary:
            factory = PlanFactory(Path(temporary).resolve())
            targets = ("agy", "codex", "claude", "cursor", "grok")
            lanes = fanout.load_lane_plans(
                [factory.create(target) for target in targets]
            )
            barrier = threading.Barrier(len(targets))

            def runner(argv):
                action = argv[3]
                session = argv[argv.index("--session") + 1]
                if action == "launch":
                    barrier.wait(timeout=3)
                    return _launch_success(argv, session)
                if action == "attach-command":
                    return _attach_success(argv, session)
                raise AssertionError("unexpected action %s" % action)

            plans = {lane.session: lane.raw for lane in lanes}
            with mock.patch.object(
                fanout,
                "compile_operator_plan",
                side_effect=lambda **kwargs: copy.deepcopy(plans[kwargs["session"]]),
            ):
                result = fanout.run_fanout(
                    lanes,
                    action="launch",
                    runner=runner,
                )
            self.assertTrue(result["ok"])
            self.assertEqual(list(result["lanes"]), sorted(targets))
            self.assertEqual(result["succeeded_targets"], sorted(targets))
            self.assertEqual(
                result["controller"]["fanout_sha256"],
                sha256_file(FANOUT_CLI),
            )
            self.assertEqual(
                set(result["plans"]),
                set(targets),
            )
            self.assertEqual(len(result["plan_set_sha256"]), 64)
            self.assertFalse(result["automatic_requalification"])
            self.assertFalse(result["automatic_sibling_halt"])
            for target in targets:
                self.assertNotIn(
                    "attach_command",
                    result["lanes"][target]["result"],
                )
                self.assertFalse(
                    result["lanes"][target]["result"][
                        "initial_attach_command_exposed"
                    ]
                )
                self.assertTrue(result["lanes"][target]["viewer"]["ok"])
                self.assertIn(
                    "attach_command",
                    result["lanes"][target]["viewer"]["result"],
                )

    def test_partial_failure_is_lane_local_and_never_halts_siblings(self):
        with tempfile.TemporaryDirectory() as temporary:
            factory = PlanFactory(Path(temporary).resolve())
            lanes = fanout.load_lane_plans(
                [
                    factory.create("codex"),
                    factory.create("claude"),
                    factory.create("grok"),
                ]
            )
            actions = []

            def runner(argv):
                action = argv[3]
                actions.append(action)
                session = argv[argv.index("--session") + 1]
                if action == "launch" and session.endswith("claude"):
                    return _failure(argv, detail="qualification is stale")
                if action == "launch":
                    return _launch_success(argv, session)
                if action == "status":
                    return _failure(argv, detail="session not registered")
                if action == "attach-command":
                    return _attach_success(argv, session)
                raise AssertionError("unexpected action")

            plans = {lane.session: lane.raw for lane in lanes}
            with mock.patch.object(
                fanout,
                "compile_operator_plan",
                side_effect=lambda **kwargs: copy.deepcopy(plans[kwargs["session"]]),
            ):
                result = fanout.run_fanout(
                    lanes,
                    action="launch",
                    runner=runner,
                )
            self.assertFalse(result["ok"])
            self.assertTrue(result["partial"])
            self.assertEqual(result["failed_targets"], ["claude"])
            self.assertEqual(result["succeeded_targets"], ["codex", "grok"])
            self.assertNotIn("halt", actions)
            self.assertEqual(actions.count("attach-command"), 2)

    def test_attach_refresh_waits_until_every_launch_has_settled(self):
        with tempfile.TemporaryDirectory() as temporary:
            factory = PlanFactory(Path(temporary).resolve())
            lanes = fanout.load_lane_plans(
                [factory.create(target) for target in ("agy", "codex", "grok")]
            )
            lock = threading.Lock()
            launches_finished = 0

            def runner(argv):
                nonlocal launches_finished
                action = argv[3]
                session = argv[argv.index("--session") + 1]
                if action == "launch":
                    with lock:
                        launches_finished += 1
                    return _launch_success(argv, session)
                if action == "attach-command":
                    with lock:
                        self.assertEqual(launches_finished, len(lanes))
                    return _attach_success(argv, session)
                raise AssertionError("unexpected action")

            plans = {lane.session: lane.raw for lane in lanes}
            with mock.patch.object(
                fanout,
                "compile_operator_plan",
                side_effect=lambda **kwargs: copy.deepcopy(plans[kwargs["session"]]),
            ):
                result = fanout.run_fanout(
                    lanes,
                    action="launch",
                    runner=runner,
                )
            self.assertTrue(result["ok"])

    def test_overlap_and_command_tampering_fail_before_child_execution(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            shared_run = root / "shared-run"
            factory = PlanFactory(root)
            first = factory.create("codex", run_root=shared_run)
            second = factory.create("grok", run_root=shared_run)
            with self.assertRaisesRegex(ValidationError, "ownership roots"):
                fanout.load_lane_plans([first, second])

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            factory = PlanFactory(root)
            first = factory.create("codex")
            cross_lane_run = root / "codex" / "repo" / "grok-run"
            second = factory.create("grok", run_root=cross_lane_run)
            with self.assertRaisesRegex(ValidationError, "across lanes"):
                fanout.load_lane_plans([first, second])

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            factory = PlanFactory(root)
            plan_path = factory.create("codex")
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            plan["commands"]["launch"][3] = "halt"
            plan_without_hash = dict(plan)
            plan_without_hash.pop("plan_sha256")
            plan["plan_sha256"] = sha256_bytes(
                canonical_json_bytes(plan_without_hash)
            )
            _write(plan_path, json.dumps(plan, sort_keys=True) + "\n")
            with self.assertRaisesRegex(IdentityError, "launch command"):
                fanout.load_lane_plan(plan_path)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            factory = PlanFactory(root)
            plan_path = factory.create("codex")
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            replacement = root / "codex" / "run" / "other-state"
            replacement.mkdir(mode=0o700)
            plan["roots"]["state"] = str(replacement)
            plan_without_hash = dict(plan)
            plan_without_hash.pop("plan_sha256")
            plan["plan_sha256"] = sha256_bytes(
                canonical_json_bytes(plan_without_hash)
            )
            _write(plan_path, json.dumps(plan, sort_keys=True) + "\n")
            with self.assertRaisesRegex(IdentityError, "proof and state roots"):
                fanout.load_lane_plan(plan_path)

    def test_view_failure_preserves_active_launch_result(self):
        with tempfile.TemporaryDirectory() as temporary:
            factory = PlanFactory(Path(temporary).resolve())
            lanes = fanout.load_lane_plans([factory.create("codex")])

            def runner(argv):
                session = argv[argv.index("--session") + 1]
                if argv[3] == "launch":
                    return _launch_success(argv, session)
                if argv[3] == "open-view":
                    return _failure(argv, detail="viewer unavailable")
                raise AssertionError("unexpected action")

            with mock.patch.object(
                fanout,
                "compile_operator_plan",
                return_value=copy.deepcopy(lanes[0].raw),
            ):
                result = fanout.run_fanout(
                    lanes,
                    action="launch",
                    runner=runner,
                    open_views=True,
                )
            self.assertFalse(result["ok"])
            self.assertTrue(result["action_ok"])
            self.assertTrue(result["partial"])
            self.assertEqual(result["viewer_failed_targets"], ["codex"])
            self.assertEqual(result["lanes"]["codex"]["state"], "ACTIVE")
            self.assertFalse(result["lanes"]["codex"]["viewer"]["ok"])

    def test_nonlaunchable_lane_blocks_every_launch_before_runner_submission(self):
        with tempfile.TemporaryDirectory() as temporary:
            factory = PlanFactory(Path(temporary).resolve())
            source_only_path = factory.create("claude")
            source_only = json.loads(source_only_path.read_text(encoding="utf-8"))
            source_only["commands"]["launch"] = {
                "supported": False,
                "reason": "qualification_required",
            }
            unhashed = dict(source_only)
            unhashed.pop("plan_sha256")
            source_only["plan_sha256"] = sha256_bytes(
                canonical_json_bytes(unhashed)
            )
            _write(source_only_path, json.dumps(source_only, sort_keys=True) + "\n")
            lanes = fanout.load_lane_plans(
                [source_only_path, factory.create("codex")]
            )
            plans = {lane.session: lane.raw for lane in lanes}
            calls = []

            def runner(argv):
                calls.append(list(argv))
                raise AssertionError("no controller may start")

            with mock.patch.object(
                fanout,
                "compile_operator_plan",
                side_effect=lambda **kwargs: copy.deepcopy(plans[kwargs["session"]]),
            ):
                result = fanout.run_fanout(
                    lanes,
                    action="launch",
                    runner=runner,
                )
            self.assertFalse(result["ok"])
            self.assertFalse(result["partial"])
            self.assertEqual(calls, [])
            self.assertEqual(
                result["lanes"]["claude"]["error"],
                "launch_unsupported",
            )
            self.assertEqual(
                result["lanes"]["codex"]["error"],
                "peer_preflight_failed",
            )

    def test_extra_blockers_and_target_gate_are_not_warm_launch_plans(self):
        with tempfile.TemporaryDirectory() as temporary:
            factory = PlanFactory(Path(temporary).resolve())
            plan_path = factory.create("agy")
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            plan["blockers"].append("agy_regular_authority_missing")
            plan["target_gate"] = {"state": "qualification_required"}
            unhashed = dict(plan)
            unhashed.pop("plan_sha256")
            plan["plan_sha256"] = sha256_bytes(canonical_json_bytes(unhashed))
            _write(plan_path, json.dumps(plan, sort_keys=True) + "\n")
            with self.assertRaisesRegex(ValidationError, "warm qualified"):
                fanout.load_lane_plan(plan_path)

    def test_body_shaped_child_json_is_never_reemitted(self):
        with tempfile.TemporaryDirectory() as temporary:
            factory = PlanFactory(Path(temporary).resolve())
            lanes = fanout.load_lane_plans([factory.create("codex")])
            canary = "PUPPET_PRIVATE_BODY_0d9c"

            def runner(argv):
                return _success(
                    argv,
                    {
                        "ok": True,
                        "session": lanes[0].session,
                        "state": "ACTIVE",
                        "prompt": canary,
                    },
                )

            result = fanout.run_fanout(
                lanes,
                action="status",
                runner=runner,
            )
            self.assertFalse(result["ok"])
            self.assertNotIn(canary, json.dumps(result, sort_keys=True))
            self.assertEqual(
                result["lanes"]["codex"]["error"],
                "controller_output_invalid",
            )

            def success_with_ignored_body(argv):
                payload = json.loads(
                    _status_success(argv, lanes[0]).stdout.decode("utf-8")
                )
                payload["detail"] = canary
                return _success(argv, payload)

            result = fanout.run_fanout(
                lanes,
                action="status",
                runner=success_with_ignored_body,
            )
            self.assertTrue(result["ok"])
            self.assertNotIn(canary, json.dumps(result, sort_keys=True))
            self.assertNotIn(
                "detail",
                result["lanes"]["codex"]["result"],
            )

            result = fanout.run_fanout(
                lanes,
                action="status",
                runner=lambda argv: _failure(
                    argv,
                    category=canary,
                    detail=canary,
                ),
            )
            self.assertFalse(result["ok"])
            self.assertNotIn(canary, json.dumps(result, sort_keys=True))
            self.assertEqual(
                result["lanes"]["codex"]["error"],
                "controller_rejected",
            )

            for action, helper in (
                ("attach", _attach_success),
                ("view", _view_success),
            ):
                def success_with_extra_state(argv, _helper=helper):
                    payload = json.loads(
                        _helper(argv, lanes[0].session).stdout.decode("utf-8")
                    )
                    payload["state"] = canary
                    return _success(argv, payload)

                with self.subTest(action=action):
                    result = fanout.run_fanout(
                        lanes,
                        action=action,
                        runner=success_with_extra_state,
                    )
                    self.assertTrue(result["ok"])
                    self.assertEqual(
                        result["lanes"]["codex"]["state"],
                        "ready",
                    )
                    self.assertNotIn(canary, json.dumps(result, sort_keys=True))

            blocked_lane = fanout.load_lane_plans(
                [factory.create("grok")]
            )[0]

            def blocked_status(argv):
                payload = json.loads(
                    _status_success(
                        argv,
                        blocked_lane,
                        state="BLOCKED",
                    ).stdout.decode("utf-8")
                )
                payload["target_process_alive"] = False
                payload["blocker"] = {
                    "code": "launch_incomplete",
                    "target_process_alive": False,
                    "cleanup_stopped": True,
                    "cleanup_error": canary,
                }
                return _success(argv, payload)

            result = fanout.run_fanout(
                [blocked_lane],
                action="status",
                runner=blocked_status,
            )
            self.assertTrue(result["ok"])
            self.assertNotIn(canary, json.dumps(result, sort_keys=True))
            blocker = result["lanes"]["grok"]["result"]["blocker"]
            self.assertTrue(blocker["cleanup_error_present"])
            self.assertTrue(blocker["dead_lease_reconciliation_candidate"])

    def test_timeout_is_lane_local_and_emits_exact_recovery_commands(self):
        with tempfile.TemporaryDirectory() as temporary:
            factory = PlanFactory(Path(temporary).resolve())
            lanes = fanout.load_lane_plans([factory.create("codex")])

            def runner(argv):
                if argv[3] == "launch":
                    raise subprocess.TimeoutExpired(argv, 1.0)
                return _failure(argv, detail="session state unavailable")

            with mock.patch.object(
                fanout,
                "compile_operator_plan",
                return_value=copy.deepcopy(lanes[0].raw),
            ):
                result = fanout.run_fanout(
                    lanes,
                    action="launch",
                    runner=runner,
                )
            lane = result["lanes"]["codex"]
            self.assertEqual(lane["state"], "recovery_required")
            self.assertEqual(lane["error"], "controller_timeout")
            self.assertEqual(lane["recovery"]["status"][3], "status")
            self.assertEqual(lane["recovery"]["halt_after_status"][3], "halt")
            self.assertIn("reconciliation", lane)

    def test_malformed_launch_reconciliation_is_lane_local(self):
        with tempfile.TemporaryDirectory() as temporary:
            factory = PlanFactory(Path(temporary).resolve())
            lanes = fanout.load_lane_plans(
                [factory.create("claude"), factory.create("codex")]
            )

            def runner(argv):
                action = argv[3]
                session = argv[argv.index("--session") + 1]
                if action == "launch" and session.endswith("claude"):
                    return _failure(argv)
                if action == "launch":
                    return _launch_success(argv, session)
                if action == "status":
                    return _success(
                        argv,
                        {
                            "ok": True,
                            "session": session,
                            "target": "claude",
                            "state": [],
                            "target_process_alive": False,
                            "tmux_alive": False,
                        },
                    )
                if action == "attach-command":
                    return _attach_success(argv, session)
                raise AssertionError("unexpected action")

            plans = {lane.session: lane.raw for lane in lanes}
            with mock.patch.object(
                fanout,
                "compile_operator_plan",
                side_effect=lambda **kwargs: copy.deepcopy(plans[kwargs["session"]]),
            ):
                result = fanout.run_fanout(
                    lanes,
                    action="launch",
                    runner=runner,
                )
            self.assertFalse(result["ok"])
            self.assertTrue(result["partial"])
            self.assertEqual(result["succeeded_targets"], ["codex"])
            reconciliation = result["lanes"]["claude"]["reconciliation"]
            self.assertFalse(reconciliation["ok"])
            self.assertEqual(
                reconciliation["error"],
                "controller_status_result_invalid",
            )

    def test_default_runner_bounds_and_interrupts_an_isolated_stub(self):
        command = [
            sys.executable,
            "-c",
            (
                "import subprocess,sys,time;"
                "subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)']);"
                "time.sleep(30)"
            ),
        ]
        started = time.monotonic()
        with (
            mock.patch.object(fanout, "CHILD_TIMEOUT_SECONDS", 0.05),
            mock.patch.object(fanout, "CHILD_INTERRUPT_GRACE_SECONDS", 0.1),
            mock.patch.object(fanout, "CHILD_TERMINATE_GRACE_SECONDS", 0.5),
            self.assertRaises(subprocess.TimeoutExpired),
        ):
            fanout._default_runner(command)
        self.assertLess(time.monotonic() - started, 2.0)

    def test_operator_cancel_shortens_an_in_progress_timeout_grace(self):
        command = [
            sys.executable,
            "-c",
            (
                "import signal,time;"
                "signal.signal(signal.SIGINT,signal.SIG_IGN);"
                "time.sleep(30)"
            ),
        ]

        def cancel_during_grace():
            time.sleep(0.15)
            fanout._OPERATOR_INTERRUPT.set()

        canceller = threading.Thread(target=cancel_during_grace)
        canceller.start()
        started = time.monotonic()
        try:
            with (
                mock.patch.object(fanout, "CHILD_TIMEOUT_SECONDS", 0.05),
                mock.patch.object(fanout, "CHILD_INTERRUPT_GRACE_SECONDS", 5.0),
                mock.patch.object(
                    fanout,
                    "CHILD_OPERATOR_INTERRUPT_GRACE_SECONDS",
                    0.2,
                ),
                mock.patch.object(
                    fanout,
                    "CHILD_TERMINATE_GRACE_SECONDS",
                    0.2,
                ),
                self.assertRaises(subprocess.TimeoutExpired),
            ):
                fanout._default_runner(command)
        finally:
            canceller.join(timeout=1.0)
            fanout._OPERATOR_INTERRUPT.clear()
        self.assertLess(time.monotonic() - started, 1.0)

    def test_successful_parent_cannot_leave_pipe_holding_descendant(self):
        command = [
            sys.executable,
            "-c",
            (
                "import subprocess,sys;"
                "subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)']);"
                "print('{\"ok\":true}')"
            ),
        ]
        started = time.monotonic()
        with mock.patch.object(
            fanout,
            "CHILD_TERMINATE_GRACE_SECONDS",
            0.5,
        ):
            result = fanout._default_runner(command)
        self.assertLess(time.monotonic() - started, 2.0)
        self.assertIsNone(fanout._safe_child_json(result.stdout))

    def test_escaped_pipe_holder_cannot_pin_runner_cleanup(self):
        command = [
            sys.executable,
            "-c",
            (
                "import subprocess,sys;"
                "subprocess.Popen("
                "[sys.executable,'-c','import time;time.sleep(1.5)'],"
                "start_new_session=True);"
                "print('{\"ok\":true}')"
            ),
        ]
        started = time.monotonic()
        result = fanout._default_runner(command)
        self.assertLess(time.monotonic() - started, 1.75)
        self.assertIsNone(fanout._safe_child_json(result.stdout))

    def test_preexisting_batch_cancel_never_starts_a_child(self):
        fanout._OPERATOR_INTERRUPT.set()
        try:
            with (
                mock.patch.object(fanout.subprocess, "Popen") as popen,
                self.assertRaises(subprocess.TimeoutExpired),
            ):
                fanout._default_runner([sys.executable, "-c", "pass"])
            popen.assert_not_called()
        finally:
            fanout._OPERATOR_INTERRUPT.clear()

    def test_repeated_interrupt_is_idempotent_during_cleanup(self):
        fanout._OPERATOR_INTERRUPT.clear()
        try:
            with self.assertRaises(KeyboardInterrupt):
                fanout._operator_sigint(signal.SIGINT, None)
            fanout._operator_sigint(signal.SIGINT, None)
        finally:
            fanout._OPERATOR_INTERRUPT.clear()

    def test_default_runner_continuously_drains_and_caps_both_streams(self):
        command = [
            sys.executable,
            "-c",
            (
                "import sys;"
                "sys.stdout.buffer.write(b'x'*(2*1024*1024));"
                "sys.stdout.buffer.flush();"
                "sys.stderr.buffer.write(b'y'*(2*1024*1024));"
                "sys.stderr.buffer.flush()"
            ),
        ]
        started = time.monotonic()
        result = fanout._default_runner(command)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(
            len(result.stdout),
            fanout.MAX_CHILD_OUTPUT_BYTES + 1,
        )
        self.assertEqual(
            len(result.stderr),
            fanout.MAX_CHILD_OUTPUT_BYTES + 1,
        )
        self.assertIsNone(fanout._safe_child_json(result.stdout))
        self.assertIsNone(fanout._safe_child_json(result.stderr))
        self.assertLess(time.monotonic() - started, 2.0)

    def test_all_lifecycle_actions_fan_out_exact_selected_sessions(self):
        with tempfile.TemporaryDirectory() as temporary:
            factory = PlanFactory(Path(temporary).resolve())
            lanes = fanout.load_lane_plans(
                [factory.create("codex"), factory.create("grok")]
            )
            lane_by_session = {lane.session: lane for lane in lanes}
            expected = {
                "status": "status",
                "attach": "attach-command",
                "view": "open-view",
                "halt": "halt",
            }
            for action, child_action in expected.items():
                calls = []

                def runner(argv, _child_action=child_action):
                    self.assertEqual(argv[3], _child_action)
                    session = argv[argv.index("--session") + 1]
                    calls.append(
                        (
                            argv[argv.index("--state-root") + 1],
                            session,
                        )
                    )
                    if _child_action == "status":
                        return _status_success(
                            argv,
                            lane_by_session[session],
                        )
                    if _child_action == "attach-command":
                        return _attach_success(argv, session)
                    if _child_action == "open-view":
                        return _view_success(argv, session)
                    return _halt_success(argv, session)

                with self.subTest(action=action):
                    result = fanout.run_fanout(
                        lanes,
                        action=action,
                        runner=runner,
                    )
                    self.assertTrue(result["ok"])
                    self.assertEqual(
                        set(calls),
                        {(str(lane.state_root), lane.session) for lane in lanes},
                    )

    def test_attach_phase_budget_cannot_expire_a_sibling_ticket(self):
        with tempfile.TemporaryDirectory() as temporary:
            factory = PlanFactory(Path(temporary).resolve())
            lane = fanout.load_lane_plans([factory.create("codex")])[0]
            limits = fanout._runner_limits(
                fanout._lane_command(lane, "attach")
            )
            self.assertEqual(
                limits,
                (
                    fanout.ATTACH_CHILD_TIMEOUT_SECONDS,
                    fanout.ATTACH_INTERRUPT_GRACE_SECONDS,
                    fanout.ATTACH_TERMINATE_GRACE_SECONDS,
                ),
            )
            self.assertLess(
                fanout.ATTACH_PHASE_MAX_SECONDS,
                fanout.TICKET_TTL_SECONDS,
            )

    def test_missing_attach_ticket_is_lane_local(self):
        with tempfile.TemporaryDirectory() as temporary:
            factory = PlanFactory(Path(temporary).resolve())
            lanes = fanout.load_lane_plans(
                [factory.create("codex"), factory.create("grok")]
            )

            def runner(argv):
                session = argv[argv.index("--session") + 1]
                completed = _attach_success(argv, session)
                if session.endswith("grok"):
                    payload = json.loads(completed.stdout.decode("utf-8"))
                    payload.pop("ticket_path")
                    return _success(argv, payload)
                return completed

            result = fanout.run_fanout(
                lanes,
                action="attach",
                runner=runner,
            )
            self.assertFalse(result["ok"])
            self.assertTrue(result["partial"])
            self.assertEqual(result["succeeded_targets"], ["codex"])
            self.assertEqual(
                result["lanes"]["grok"]["error"],
                "controller_attach_result_invalid",
            )

    def test_deep_json_failure_is_lane_local(self):
        with tempfile.TemporaryDirectory() as temporary:
            factory = PlanFactory(Path(temporary).resolve())
            lanes = fanout.load_lane_plans(
                [factory.create("codex"), factory.create("grok")]
            )
            lane_by_session = {lane.session: lane for lane in lanes}

            def runner(argv):
                session = argv[argv.index("--session") + 1]
                if session.endswith("grok"):
                    return subprocess.CompletedProcess(
                        list(argv),
                        0,
                        stdout=(
                            b"[" * 2000
                            + b"0"
                            + b"]" * 2000
                        ),
                        stderr=b"",
                    )
                return _status_success(argv, lane_by_session[session])

            result = fanout.run_fanout(
                lanes,
                action="status",
                runner=runner,
            )
            self.assertFalse(result["ok"])
            self.assertTrue(result["partial"])
            self.assertEqual(result["succeeded_targets"], ["codex"])
            self.assertEqual(
                result["lanes"]["grok"]["error"],
                "controller_output_invalid",
            )

    def test_uncertain_halt_is_reconciled_without_retrying_halt(self):
        with tempfile.TemporaryDirectory() as temporary:
            factory = PlanFactory(Path(temporary).resolve())
            lanes = fanout.load_lane_plans(
                [factory.create("codex"), factory.create("grok")]
            )
            lane_by_session = {lane.session: lane for lane in lanes}
            actions = []

            def runner(argv):
                action = argv[3]
                session = argv[argv.index("--session") + 1]
                actions.append((action, session))
                if action == "halt" and session.endswith("grok"):
                    raise subprocess.TimeoutExpired(argv, 1.0)
                if action == "halt":
                    return _halt_success(argv, session)
                if action == "status":
                    return _status_success(
                        argv,
                        lane_by_session[session],
                    )
                raise AssertionError("unexpected action")

            result = fanout.run_fanout(
                lanes,
                action="halt",
                runner=runner,
            )
            self.assertFalse(result["ok"])
            self.assertTrue(result["partial"])
            failed = result["lanes"]["grok"]
            self.assertEqual(failed["state"], "recovery_required")
            self.assertEqual(failed["error"], "controller_timeout")
            self.assertIn("reconciliation", failed)
            self.assertEqual(
                [action for action, session in actions if session.endswith("grok")],
                ["halt", "status"],
            )

    def test_lifecycle_success_claims_require_action_specific_proof(self):
        with tempfile.TemporaryDirectory() as temporary:
            factory = PlanFactory(Path(temporary).resolve())
            lanes = fanout.load_lane_plans([factory.create("codex")])
            for action in ("status", "attach", "view", "halt"):
                with self.subTest(action=action):
                    result = fanout.run_fanout(
                        lanes,
                        action=action,
                        runner=lambda argv: _success(
                            argv,
                            {
                                "ok": True,
                                "session": lanes[0].session,
                                "state": (
                                    "HALTED" if action == "halt" else "ACTIVE"
                                ),
                            },
                        ),
                    )
                    self.assertFalse(result["ok"])
                    self.assertIn(
                        "result_invalid",
                        result["lanes"]["codex"]["error"],
                    )

    def test_launch_success_requires_active_state_and_initial_ticket(self):
        with tempfile.TemporaryDirectory() as temporary:
            factory = PlanFactory(Path(temporary).resolve())
            lanes = fanout.load_lane_plans([factory.create("codex")])

            def runner(argv):
                if argv[3] == "launch":
                    return _success(
                        argv,
                        {
                            "ok": True,
                            "session": lanes[0].session,
                            "state": "ACTIVE",
                        },
                    )
                return _failure(argv)

            with mock.patch.object(
                fanout,
                "compile_operator_plan",
                return_value=copy.deepcopy(lanes[0].raw),
            ):
                result = fanout.run_fanout(
                    lanes,
                    action="launch",
                    runner=runner,
                )
            self.assertEqual(
                result["lanes"]["codex"]["error"],
                "controller_launch_result_invalid",
            )
            self.assertEqual(
                result["lanes"]["codex"]["state"],
                "recovery_required",
            )

    def test_cli_partial_and_interrupt_exit_codes_are_structured(self):
        with tempfile.TemporaryDirectory() as temporary:
            factory = PlanFactory(Path(temporary).resolve())
            plan_path = factory.create("codex")
            lanes = fanout.load_lane_plans([plan_path])
            partial = {
                "ok": False,
                "partial": True,
                "schema": fanout.RESULT_SCHEMA,
            }
            with (
                mock.patch.object(fanout, "load_lane_plans", return_value=lanes),
                mock.patch.object(fanout, "run_fanout", return_value=partial),
                mock.patch("builtins.print") as printed,
            ):
                self.assertEqual(
                    fanout.main(["status", "--plan", str(plan_path)]),
                    4,
                )
                self.assertTrue(printed.called)

            stub = [
                sys.executable,
                "-c",
                "import time;time.sleep(30)",
            ]

            def interrupt_main():
                time.sleep(0.1)
                os.kill(os.getpid(), signal.SIGINT)

            interrupter = threading.Thread(target=interrupt_main)
            interrupter.start()
            started = time.monotonic()
            with (
                mock.patch.object(fanout, "load_lane_plans", return_value=lanes),
                mock.patch.object(fanout, "_lane_command", return_value=stub),
                mock.patch.object(
                    fanout,
                    "CHILD_OPERATOR_INTERRUPT_GRACE_SECONDS",
                    0.2,
                ),
                mock.patch.object(
                    fanout,
                    "CHILD_TERMINATE_GRACE_SECONDS",
                    0.2,
                ),
                mock.patch("builtins.print") as printed,
            ):
                self.assertEqual(
                    fanout.main(["status", "--plan", str(plan_path)]),
                    130,
                )
                payload = json.loads(printed.call_args.args[0])
                self.assertEqual(payload["error"], "operator_interrupted")
                self.assertIn("codex", payload["recovery"])
            interrupter.join(timeout=1.0)
            self.assertLess(time.monotonic() - started, 2.0)

    def test_genuine_compiled_v1_plan_round_trips_without_path_or_argv_drift(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = OperatorPlanFixture(
                Path(temporary) / "fixture",
                target="claude",
            )
            manifest = json.loads(fixture.manifest.read_text(encoding="utf-8"))
            manifest["doctor_only"] = False
            manifest["capabilities"] = {
                name: ("unsupported" if name == "resume" else "controller_verified")
                for name in manifest["capabilities"]
            }
            manifest["qualification"] = {
                "receipt_path": str(
                    Path(temporary) / "qualification-receipt.json"
                ),
                "receipt_sha256": "d" * 64,
                "session_profile": "regular",
            }
            _write(fixture.manifest, json.dumps(manifest, sort_keys=True) + "\n")
            fixture.profile.mkdir(mode=0o700)
            plan = fanout.compile_operator_plan(
                **fixture.kwargs(),
                repo=fixture.repo,
            )
            plan_path = Path(temporary) / "compiled-plan.json"
            _write(plan_path, json.dumps(plan, sort_keys=True) + "\n")

            lane = fanout.load_lane_plan(plan_path)
            self.assertEqual(lane.commands["launch"][:4], [
                str(Path(sys.executable).resolve(strict=True)),
                str(PUPPET_CLI.resolve(strict=True)),
                "--json",
                "launch",
            ])
            self.assertEqual(
                fanout._recompile_launch_plan(lane)["state"],
                "preflight_ready",
            )

    def test_fast_coordinator_is_outside_adapter_authority_fingerprint(self):
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary).resolve() / "puppet"
            shutil.copytree(SKILL, copied)
            before = adapter_implementation_fingerprint(copied)
            fanout_copy = copied / "scripts" / "puppet_fanout.py"
            fanout_copy.write_text(
                fanout_copy.read_text(encoding="utf-8") + "\n# test-only change\n",
                encoding="utf-8",
            )
            after = adapter_implementation_fingerprint(copied)
            self.assertEqual(before, after)

    def test_cli_requires_explicit_live_launch_acknowledgement(self):
        result = subprocess.run(
            [
                sys.executable,
                str(FANOUT_CLI),
                "launch",
                "--plan",
                "/tmp/not-opened.json",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("--allow-live-launch", result.stderr)


if __name__ == "__main__":
    unittest.main()
