from __future__ import annotations

import inspect
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "puppet" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from puppet_lib.agy_print import (
    AgyPrintController,
    LIFECYCLE_PHASES,
    ProcessIdentityFixture,
    fixture_observation,
    owned_identity_map,
    process_table_from_observation,
    prove_process_tree,
    prove_shutdown,
    qualify_agy_print_lifecycle,
    validate_agy_print_observation,
)
from puppet_lib.errors import IdentityError
from puppet_lib.operator_plan import compile_operator_plan
from puppet_lib.transport import transport_capability_table


def _workspace(**overrides):
    workspace = {
        "path": "/tmp/agy-print-workspace",
        "branch": "codex/example",
        "head": "a" * 40,
        "tree": "b" * 40,
    }
    workspace.update(overrides)
    return workspace


def _child(pid=4243, birth="darwin:100:00004243"):
    return {"pid": pid, "kernel_birth_id": birth}


def _halted_observation(**overrides):
    payload = dict(
        owned_children=[_child()],
        terminal_state="halted",
        record_state="HALTED",
        last_checkpoint={"checkpoint_id": "c" * 64},
        last_beacon={"sequence": 4},
        last_validated_at="2026-09-18T00:00:00Z",
        halt={
            "pid": 4242,
            "kernel_birth_id": "darwin:100:00004242",
            "pid_gone": True,
            "signaled_pids": [4242, 4243],
        },
    )
    payload.update(overrides)
    return fixture_observation(**payload)


class AgyPrintLifecycleTests(unittest.TestCase):
    def test_lifecycle_proves_start_resume_result_and_distinct_outcomes(self):
        accepted = fixture_observation(
            last_checkpoint={"checkpoint_id": "c" * 64},
            last_beacon={"sequence": 3},
            last_validated_at="2026-09-18T00:00:00Z",
            record_state="ACCEPTED",
        )
        qualified = qualify_agy_print_lifecycle(
            accepted,
            expected_session="agy-print-session",
            expected_conversation_id="conv-agy-print-1",
            expected_workspace=_workspace(),
            requested_model="gemini-3.7-flash-high",
        )
        self.assertEqual(qualified["schema"], "puppet.agy-print-lifecycle/v1")
        self.assertEqual(qualified["phase_order"], list(LIFECYCLE_PHASES))
        self.assertFalse(qualified["live_agy_claimed"])
        self.assertFalse(AgyPrintController.available())
        phases = qualified["phases"]
        self.assertEqual(
            phases["start_bound"]["model"]["observed_model"],
            "gemini-3.7-flash-high",
        )
        self.assertEqual(phases["resume_matched"]["conversation_id"], "conv-agy-print-1")
        self.assertEqual(phases["terminal_result"]["state"], "completed")
        self.assertEqual(phases["worker_completion"], "reported")
        self.assertEqual(phases["controller_acceptance"], "accepted")
        self.assertIsNone(phases["confirmed_halt"])
        self.assertIsNotNone(phases["final_outcome"])
        self.assertEqual(qualified["caller_outcome"]["halt"], "none")
        self.assertIn("controller accepted", phases["final_outcome"]["summary"])

    def test_halted_lifecycle_confirms_owned_tree_and_bounded_outcome(self):
        observation = _halted_observation()
        table = process_table_from_observation(observation)
        qualified = qualify_agy_print_lifecycle(
            observation,
            expected_session="agy-print-session",
            expected_conversation_id="conv-agy-print-1",
            expected_workspace=_workspace(),
            process_table=table,
        )
        halt = qualified["phases"]["confirmed_halt"]
        self.assertEqual(qualified["caller_outcome"]["worker_completion"], "reported")
        self.assertEqual(qualified["caller_outcome"]["controller_acceptance"], "none")
        self.assertEqual(qualified["caller_outcome"]["halt"], "confirmed")
        self.assertEqual(halt["pid"], 4242)
        self.assertEqual(
            halt["signaled_identities"],
            [
                {"pid": 4242, "kernel_birth_id": "darwin:100:00004242"},
                {"pid": 4243, "kernel_birth_id": "darwin:100:00004243"},
            ],
        )
        self.assertEqual(table.signaled, halt["signaled_identities"])
        self.assertEqual(qualified["phases"]["final_outcome"]["process"]["pid"], 4242)
        self.assertFalse(qualified["live_agy_claimed"])

    def test_worker_completion_is_not_controller_acceptance(self):
        observation = fixture_observation(
            last_checkpoint={"checkpoint_id": "c" * 64},
            record_state="SOURCE_ACCEPTED",
        )
        qualified = qualify_agy_print_lifecycle(
            observation,
            expected_session="agy-print-session",
            expected_conversation_id="conv-agy-print-1",
            expected_workspace=_workspace(),
        )
        self.assertEqual(qualified["phases"]["worker_completion"], "reported")
        self.assertEqual(qualified["phases"]["controller_acceptance"], "none")
        self.assertIsNone(qualified["phases"]["confirmed_halt"])
        self.assertIsNone(qualified["phases"]["final_outcome"])

    def test_resume_mismatch_fails_before_halt(self):
        observation = _halted_observation()
        with self.assertRaisesRegex(IdentityError, "session and conversation"):
            qualify_agy_print_lifecycle(
                observation,
                expected_session="agy-print-session",
                expected_conversation_id="conv-other",
                expected_workspace=_workspace(),
            )


class ProcessIdentityRaceTests(unittest.TestCase):
    def test_owned_map_rejects_duplicate_and_colliding_pids(self):
        observation = fixture_observation(
            owned_children=[_child(), _child(pid=4242, birth="darwin:100:child")]
        )
        with self.assertRaisesRegex(IdentityError, "ambiguous"):
            validate_agy_print_observation(observation)
        duplicate_children = fixture_observation(
            owned_children=[_child(), _child()]
        )
        with self.assertRaisesRegex(IdentityError, "ambiguous"):
            owned_identity_map(duplicate_children["process"])

    def test_shutdown_records_birth_for_each_signaled_pid(self):
        observation = _halted_observation()
        proof = prove_shutdown(
            observation,
            expected_process=observation["process"],
        )
        self.assertEqual(
            proof["signaled_identities"],
            [
                {"pid": 4242, "kernel_birth_id": "darwin:100:00004242"},
                {"pid": 4243, "kernel_birth_id": "darwin:100:00004243"},
            ],
        )

    def test_pid_reuse_fails_closed_and_does_not_signal(self):
        observation = _halted_observation()
        table = process_table_from_observation(observation)
        reused = table.reuse_pid(4242, "linux:boot:9999")
        self.assertEqual(reused["pid"], 4242)
        self.assertEqual(table.current(4242)["kernel_birth_id"], "linux:boot:9999")
        with self.assertRaisesRegex(IdentityError, "process identity changed"):
            prove_process_tree(
                observation,
                expected_process=observation["process"],
                process_table=table,
            )
        self.assertEqual(table.signaled, [])

    def test_stale_identity_fails_closed(self):
        observation = _halted_observation()
        table = process_table_from_observation(observation)
        table.vanish(4243)
        with self.assertRaisesRegex(IdentityError, "process identity is stale"):
            table.revalidate(_child())
        self.assertEqual(table.signaled, [])

    def test_ambiguous_identity_fails_closed(self):
        table = ProcessIdentityFixture()
        table.spawn(4242, "darwin:100:00004242")
        table.mark_ambiguous(4242)
        with self.assertRaisesRegex(IdentityError, "ambiguous"):
            table.revalidate({"pid": 4242, "kernel_birth_id": "darwin:100:00004242"})
        self.assertEqual(table.signaled, [])

    def test_signal_race_reusing_pid_does_not_touch_the_new_occupant(self):
        observation = _halted_observation()
        table = process_table_from_observation(observation)

        def reuse(_table):
            _table.reuse_pid(4243, "linux:boot:reused-child")

        with self.assertRaisesRegex(IdentityError, "process identity changed"):
            table.signal_owned_tree(
                {"pid": 4242, "kernel_birth_id": "darwin:100:00004242"},
                [_child()],
                signaled_pids=[4242, 4243],
                race=reuse,
            )
        self.assertEqual(table.signaled, [])
        self.assertEqual(table.current(4243)["kernel_birth_id"], "linux:boot:reused-child")

    def test_signal_rejects_unrelated_pid(self):
        observation = _halted_observation()
        table = process_table_from_observation(observation)
        table.spawn(9999, "darwin:100:foreign")
        with self.assertRaisesRegex(IdentityError, "not confined"):
            table.signal_owned_tree(
                {"pid": 4242, "kernel_birth_id": "darwin:100:00004242"},
                [_child()],
                signaled_pids=[4242, 9999],
            )
        self.assertEqual(table.signaled, [])
        self.assertEqual(table.current(9999)["kernel_birth_id"], "darwin:100:foreign")

    def test_extra_live_descendant_is_not_owned_authority(self):
        observation = _halted_observation()
        table = process_table_from_observation(observation)
        table.spawn(7777, "darwin:100:extra", parent_pid=4242)
        with self.assertRaisesRegex(IdentityError, "not confined"):
            table.revalidate_owned_tree(
                {"pid": 4242, "kernel_birth_id": "darwin:100:00004242"},
                [_child()],
            )

    def test_lifecycle_halt_race_does_not_signal(self):
        observation = _halted_observation()
        table = process_table_from_observation(observation)

        def reuse(_table):
            _table.reuse_pid(4242, "linux:boot:new-root")

        with self.assertRaisesRegex(IdentityError, "process identity changed"):
            qualify_agy_print_lifecycle(
                observation,
                expected_session="agy-print-session",
                expected_conversation_id="conv-agy-print-1",
                expected_workspace=_workspace(),
                process_table=table,
                race=reuse,
            )
        self.assertEqual(table.signaled, [])

    def test_capability_and_operator_plan_stay_unchanged(self):
        table = transport_capability_table()
        self.assertEqual(table["agy-print"]["implementation"], "implemented")
        self.assertEqual(table["agy-print"]["status_does_not_prove"], "live_agy_lifecycle")
        self.assertEqual(table["herdr"]["implementation"], "unsupported")
        self.assertEqual(table["acp"]["implementation"], "unsupported")
        self.assertEqual(table["tmux"]["implementation"], "implemented")
        self.assertFalse(AgyPrintController.available())
        params = inspect.signature(compile_operator_plan).parameters
        self.assertNotIn("transport", params)
        self.assertNotIn("requested_transport", params)
