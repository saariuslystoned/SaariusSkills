from __future__ import annotations

import os
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "puppet" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from puppet_lib.agy_print import (
    AgyPrintController,
    agy_print_launch_argv,
    installed_agy_print_runtime,
    parse_agy_stream_event,
    reduce_agy_stream_event,
    persist_agy_print_session,
    probe_agy_print_runtime,
)
from puppet_lib.errors import IdentityError, UnsupportedError
from puppet_lib.session import accept_checkpoint, halt, send_message, status, wait_for


FAKE_AGY_C = r"""
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

static volatile sig_atomic_t stop_now = 0;

static void on_int(int signo) {
    (void)signo;
    stop_now = 1;
}

static const char *arg_after(int argc, char **argv, const char *flag) {
    int index;
    for (index = 1; index + 1 < argc; index += 1) {
        if (strcmp(argv[index], flag) == 0) {
            return argv[index + 1];
        }
    }
    return NULL;
}

static int minimal_init_requested(void) {
    const char *flag = getenv("PUPPET_AGY_TEST_MINIMAL_INIT");
    return flag != NULL && strcmp(flag, "1") == 0;
}

int main(int argc, char **argv) {
    int index;
    const char *model;
    const char *session;
    const char *conversation;
    const char *child;
    const char *hold;
    char cwd[4096];
    char line[8];

    for (index = 1; index < argc; index += 1) {
        if (strcmp(argv[index], "--help") == 0) {
            fputs("  --conversation\n  --input-format stream-json\n  --output-format stream-json\n  --print\n", stdout);
            return 0;
        }
        if (strcmp(argv[index], "--continue") == 0) {
            return 2;
        }
    }
    model = getenv("PUPPET_AGY_TEST_MODEL");
    if (model == NULL || model[0] == '\0') {
        model = "gemini-3.7-flash-high";
    }
    session = getenv("PUPPET_AGY_TEST_SESSION");
    if (session == NULL) {
        session = "agy-print-session";
    }
    conversation = getenv("PUPPET_AGY_TEST_CONVERSATION");
    if (conversation == NULL) {
        conversation = arg_after(argc, argv, "--conversation");
    }
    if (conversation == NULL) {
        conversation = "conv-agy-print-1";
    }
    child = getenv("PUPPET_AGY_TEST_CHILD");
    if (child != NULL && strcmp(child, "1") == 0) {
        if (fork() == 0) {
            execl("/bin/sleep", "sleep", "30", (char *)NULL);
            _exit(127);
        }
    }
    if (getcwd(cwd, sizeof cwd) == NULL) {
        return 1;
    }
    if (minimal_init_requested()) {
        printf("{\"type\":\"system\",\"subtype\":\"init\"}\n");
    } else {
        printf(
            "{\"type\":\"system\",\"subtype\":\"init\",\"model\":\"%s\",\"session_id\":\"%s\",\"conversation_id\":\"%s\",\"cwd\":\"%s\"}\n",
            model,
            session,
            conversation,
            cwd
        );
    }
    fflush(stdout);
    (void)fgets(line, sizeof line, stdin);
    printf(
        "{\"type\":\"result\",\"subtype\":\"success\",\"is_error\":false,\"session_id\":\"%s\",\"conversation_id\":\"%s\"}\n",
        session,
        conversation
    );
    fflush(stdout);
    hold = getenv("PUPPET_AGY_TEST_HOLD");
    if (hold != NULL && strcmp(hold, "1") == 0) {
        signal(SIGINT, on_int);
        while (!stop_now) {
            pause();
        }
    }
    return 0;
}
"""


def _write_fake(root: Path) -> Path:
    source = root / "fake-agy.c"
    path = root / "fake-agy"
    source.write_text(FAKE_AGY_C, encoding="utf-8")
    compiled = subprocess.run(
        ["cc", "-O0", "-o", str(path), str(source)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if compiled.returncode != 0 or not path.is_file():
        raise RuntimeError(compiled.stderr.decode("utf-8", errors="replace"))
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def _workspace(path: Path):
    return {
        "path": str(path),
        "branch": "codex/example",
        "head": "a" * 40,
        "tree": "b" * 40,
    }


class AgyPrintRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.executable = _write_fake(self.root)
        self.workspace = (self.root / "workspace")
        self.workspace.mkdir()
        self.workspace = self.workspace.resolve()
        self.controller = AgyPrintController(self.root, executable=self.executable)
        self._held = []

    def tearDown(self):
        for controller in [self.controller, *self._held]:
            runtime = getattr(controller, "runtime", None)
            process = getattr(runtime, "process", None) if runtime is not None else None
            if process is None:
                continue
            try:
                os.killpg(process.pid, 9)
            except OSError:
                if process.poll() is None:
                    process.kill()
            try:
                process.wait(timeout=1)
            except Exception:
                pass
            for handle in (process.stdin, process.stdout, process.stderr):
                if handle is not None:
                    try:
                        handle.close()
                    except OSError:
                        pass
        self.temporary.cleanup()

        time.sleep(0.4)

    def test_probe_and_fixtures_do_not_claim_live_success(self):
        probe = probe_agy_print_runtime(self.executable)
        self.assertTrue(probe["available"])
        self.assertFalse(probe["live_agy_claimed"])
        observation = self.controller.start(
            session="agy-print-session",
            prompt="bounded task",
            expected_workspace=_workspace(self.workspace),
            requested_model="gemini-3.7-flash-high",
        )
        self.assertTrue(observation["process_backed"])
        self.assertFalse(observation["live_agy_claimed"])
        self.assertFalse(observation["lifecycle"]["live_agy_claimed"])
        with mock.patch(
            "puppet_lib.agy_print.shutil.which", return_value=None
        ), mock.patch(
            "puppet_lib.agy_print.DEFAULT_AGY_EXECUTABLE", self.root / "missing"
        ):
            self.assertIsNone(installed_agy_print_runtime())
            self.assertFalse(AgyPrintController.available())
        self.assertTrue(AgyPrintController.available(self.executable))

    def test_help_without_stream_json_is_unavailable(self):
        bare = self.root / "bare"
        bare.write_text("#!/bin/sh\necho usage\n", encoding="utf-8")
        bare.chmod(bare.stat().st_mode | stat.S_IXUSR)
        probe = probe_agy_print_runtime(bare)
        self.assertFalse(probe["available"])
        self.assertFalse(AgyPrintController.available(bare))

    def test_native_agy_nested_event_shapes_reduce_to_safe_metadata(self):
        conversation = "240fd464-782d-4a70-a56c-d4ca7ca18e52"
        init = parse_agy_stream_event(
            '{"event":"init","conversation_id":"%s","init":{"model":"gemini-3.8-flash-high","cwd":"%s","tools":["discarded"]}}'
            % (conversation, self.workspace)
        )
        step = parse_agy_stream_event(
            '{"event":"step_update","step_update":{"conversation_id":"%s","step_type":"tool_call","step":2,"message":"discarded"}}'
            % conversation
        )
        result = parse_agy_stream_event(
            '{"event":"result","result":{"conversation_id":"%s","status":"SUCCESS","output":"discarded"}}'
            % conversation
        )
        self.assertEqual(init["type"], "init")
        self.assertEqual(init["model"], "gemini-3.8-flash-high")
        self.assertEqual(init["cwd"], str(self.workspace))
        self.assertEqual(step["type"], "step_update")
        self.assertEqual(step["step"], "2")
        self.assertEqual(result["type"], "result")
        self.assertEqual(result["status"], "SUCCESS")
        self.assertNotIn("message", step)
        self.assertNotIn("output", result)
        state = {"observed_model": None, "conversation_id": None, "session_id": None,
                 "cwd": None, "terminal_state": "active", "failed": False,
                 "step_count": 0, "last_step": None, "tools": [], "result_seen": False}
        for event in (init, step, result):
            state = reduce_agy_stream_event(state, event)
        self.assertEqual(state["observed_model"], "gemini-3.8-flash-high")
        self.assertEqual(state["conversation_id"], conversation)
        self.assertEqual(state["step_count"], 1)
        self.assertEqual(state["terminal_state"], "completed")
        self.assertTrue(state["result_seen"])

    def test_unknown_and_mismatched_model_fail_closed(self):
        with self.assertRaisesRegex(IdentityError, "unknown or unqualified"):
            self.controller.start(
                session="agy-print-session",
                prompt="bounded task",
                expected_workspace=_workspace(self.workspace),
                requested_model="not-an-installed-model",
                known_models=("gemini-3.7-flash-high",),
            )
        env = {**os.environ, "PUPPET_AGY_TEST_MODEL": "other-model"}
        mismatched = AgyPrintController(self.root, executable=self.executable)
        with self.assertRaisesRegex(IdentityError, "does not match"):
            mismatched.start(
                session="agy-print-session",
                prompt="bounded task",
                expected_workspace=_workspace(self.workspace),
                requested_model="gemini-3.7-flash-high",
                environment=env,
            )
        selector_only_env = {**os.environ, "PUPPET_AGY_TEST_MINIMAL_INIT": "1"}
        mute = AgyPrintController(self.root, executable=self.executable)
        with self.assertRaisesRegex(IdentityError, "requested selector"):
            mute.start(
                session="agy-print-session",
                prompt="bounded task",
                expected_workspace=_workspace(self.workspace),
                requested_model="gemini-3.7-flash-high",
                environment=selector_only_env,
            )

    def test_resume_requires_exact_conversation_and_refuses_continue(self):
        started = self.controller.start(
            session="agy-print-session",
            prompt="first turn",
            expected_workspace=_workspace(self.workspace),
            requested_model="gemini-3.7-flash-high",
        )
        conversation = started["agy_print"]["resume"]["conversation_id"]
        resumed = self.controller.send(
            session="agy-print-session",
            message="second turn",
            expected_workspace=_workspace(self.workspace),
            requested_model="gemini-3.7-flash-high",
        )
        self.assertEqual(resumed["agy_print"]["resume"]["conversation_id"], conversation)
        with self.assertRaisesRegex(UnsupportedError, "--continue"):
            agy_print_launch_argv(
                self.executable, conversation_id=conversation, extra_flags=("--continue",)
            )
        with self.assertRaisesRegex(UnsupportedError, "--continue"):
            self.controller.send(
                session="agy-print-session",
                message="please --continue this",
                expected_workspace=_workspace(self.workspace),
            )
        env = {**os.environ, "PUPPET_AGY_TEST_CONVERSATION": "conv-wrong"}
        mismatched = AgyPrintController(self.root, executable=self.executable)
        mismatched.start(
            session="other-session",
            prompt="first turn",
            expected_workspace=_workspace(self.workspace),
            requested_model="gemini-3.7-flash-high",
        )
        with self.assertRaisesRegex(IdentityError, "session and conversation"):
            mismatched.start(
                session="other-session",
                prompt="second turn",
                expected_workspace=_workspace(self.workspace),
                requested_model="gemini-3.7-flash-high",
                conversation_id="conv-agy-print-1",
                environment=env,
            )

    def test_steering_refuses_without_conversation_identity(self):
        self.controller.start(
            session="agy-print-session",
            prompt="first turn",
            expected_workspace=_workspace(self.workspace),
            requested_model="gemini-3.7-flash-high",
        )
        stored = self.controller.require_session("agy-print-session")
        persist_agy_print_session(self.root, dict(stored, conversation_id=""))
        with self.assertRaisesRegex(UnsupportedError, "steering is unsupported"):
            self.controller.send(
                session="agy-print-session",
                message="second turn",
                expected_workspace=_workspace(self.workspace),
            )

    def test_stale_qualification_fails_closed(self):
        stored_scope = {
            "schema": "puppet.qualification-scope/v1",
            "target": "agy",
            "fingerprint": "1" * 64,
        }
        current_scope = {
            "schema": "puppet.qualification-scope/v1",
            "target": "agy",
            "fingerprint": "2" * 64,
        }
        with self.assertRaisesRegex(IdentityError, "qualification is stale"):
            self.controller.start(
                session="agy-print-session",
                prompt="first turn",
                expected_workspace=_workspace(self.workspace),
                requested_model="gemini-3.7-flash-high",
                qualification_scope=stored_scope,
                current_qualification_scope=current_scope,
            )

    def test_public_status_accept_wait_and_owned_halt(self):
        env = {
            **os.environ,
            "PUPPET_AGY_TEST_HOLD": "1",
            "PUPPET_AGY_TEST_CHILD": "1",
        }
        held = AgyPrintController(self.root, executable=self.executable)
        self._held.append(held)
        started = held.start(
            session="agy-print-session",
            prompt="hold for halt",
            expected_workspace=_workspace(self.workspace),
            requested_model="gemini-3.7-flash-high",
            environment=env,
        )
        pid = started["agy_print"]["process"]["pid"]
        self.assertTrue(status(state_root=self.root, session="agy-print-session")["target_process_alive"])
        held.record_checkpoint("agy-print-session", "c" * 64, beacon_sequence=2)
        with self.assertRaisesRegex(Exception, "contract|evidence"):
            accept_checkpoint(
                state_root=self.root,
                session="agy-print-session",
                checkpoint_id="c" * 64,
                actor="controller",
                evidence_path=self.root / "unused.json",
            )
        foreign = os.spawnlp(os.P_NOWAIT, "sleep", "sleep", "30")
        halted = halt(state_root=self.root, session="agy-print-session")
        self.assertEqual(halted["caller_outcome"]["halt"], "confirmed")
        self.assertFalse(halted["live_agy_claimed"])
        waited = wait_for(
            state_root=self.root,
            session="agy-print-session",
            condition="target-stopped",
            timeout=2.0,
        )
        self.assertTrue(waited["matched"])
        try:
            os.kill(foreign, 0)
            foreign_alive = True
        except OSError:
            foreign_alive = False
        self.assertTrue(foreign_alive)
        os.kill(foreign, 15)
        self.assertNotEqual(halted["agy_print"]["process"]["pid"], foreign)
        self.assertEqual(halted["agy_print"]["process"]["pid"], pid)

    def test_public_send_refuses_side_channel_and_uses_store(self):
        self.controller.start(
            session="agy-print-session",
            prompt="first turn",
            expected_workspace=_workspace(self.workspace),
            requested_model="gemini-3.7-flash-high",
        )
        with self.assertRaisesRegex(Exception, "side-channel"):
            send_message(
                state_root=self.root,
                session="agy-print-session",
                message="/btw leaked",
                request_id="req-1",
            )
        sent = send_message(
            state_root=self.root,
            session="agy-print-session",
            message="second turn",
            request_id="req-2",
        )
        self.assertTrue(sent["ok"])
        self.assertFalse(sent["live_agy_claimed"])
        self.assertEqual(sent["request_id"], "req-2")

    def test_public_send_refusal_does_not_poison_delivery_ledger(self):
        env = {**os.environ, "PUPPET_AGY_TEST_HOLD": "1"}
        held = AgyPrintController(self.root, executable=self.executable)
        self._held.append(held)
        held.start(
            session="agy-print-session",
            prompt="first turn",
            expected_workspace=_workspace(self.workspace),
            requested_model="gemini-3.7-flash-high",
            environment=env,
        )
        process = held.runtime.process
        process.terminate()
        process.wait(timeout=2)
        with self.assertRaisesRegex(UnsupportedError, "explicit halt"):
            send_message(
                state_root=self.root,
                session="agy-print-session",
                message="refused before delivery",
                request_id="refused-1",
            )
        stored = held.require_session("agy-print-session")
        self.assertNotIn("refused-1", stored.get("send_requests", {}))

    def test_public_send_history_is_not_silently_evicted(self):
        self.controller.start(
            session="agy-print-session",
            prompt="first turn",
            expected_workspace=_workspace(self.workspace),
            requested_model="gemini-3.7-flash-high",
        )
        process = self.controller.runtime.process
        process.terminate()
        process.wait(timeout=2)
        stored = self.controller.require_session("agy-print-session")
        stored["held"] = False
        stored["send_requests"] = {
            "historical-%02d" % index: {
                "message_sha256": "%064d" % index,
                "phase": "submitted",
                "result": {"ok": True},
            }
            for index in range(64)
        }
        persist_agy_print_session(self.root, stored)
        with self.assertRaisesRegex(Exception, "ledger is full"):
            send_message(
                state_root=self.root,
                session="agy-print-session",
                message="new request",
                request_id="new-request",
            )
        current = self.controller.require_session("agy-print-session")
        self.assertEqual(len(current["send_requests"]), 64)
        self.assertIn("historical-00", current["send_requests"])

    def test_resume_failure_hook_runs_after_lease_admission(self):
        self.controller.start(
            session="agy-print-session",
            prompt="first turn",
            expected_workspace=_workspace(self.workspace),
            requested_model="gemini-3.7-flash-high",
        )
        process = self.controller.runtime.process
        process.terminate()
        process.wait(timeout=2)
        stored = self.controller.require_session("agy-print-session")
        stored["held"] = False
        persist_agy_print_session(self.root, stored)
        events = []
        with mock.patch.object(
            self.controller, "start", side_effect=RuntimeError("launch failed")
        ):
            with self.assertRaisesRegex(RuntimeError, "launch failed"):
                self.controller.send(
                    session="agy-print-session",
                    message="resume turn",
                    expected_workspace=_workspace(self.workspace),
                    request_id="resume-failure",
                    before_resume=lambda: events.append("admitted"),
                    on_resume_failure=lambda: events.append("reconciled"),
                )
        self.assertEqual(events, ["admitted", "reconciled"])
        current = self.controller.require_session("agy-print-session")
        self.assertEqual(
            current["send_requests"]["resume-failure"]["phase"], "intent"
        )

    def test_reused_process_identity_fails_closed(self):
        env = {**os.environ, "PUPPET_AGY_TEST_HOLD": "1"}
        held = AgyPrintController(self.root, executable=self.executable)
        self._held.append(held)
        held.start(
            session="agy-print-session",
            prompt="first turn",
            expected_workspace=_workspace(self.workspace),
            requested_model="gemini-3.7-flash-high",
            environment=env,
        )
        stored = held.require_session("agy-print-session")
        observation = stored["observation"]
        observation["process"]["kernel_birth_id"] = "linux:boot:reused"
        persist_agy_print_session(
            self.root,
            dict(stored, observation=observation, held=True),
        )
        with self.assertRaisesRegex(IdentityError, "process identity"):
            AgyPrintController(self.root, executable=self.executable).status(
                session="agy-print-session"
            )


if __name__ == "__main__":
    unittest.main()
