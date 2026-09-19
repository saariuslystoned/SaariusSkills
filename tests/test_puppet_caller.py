from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "puppet" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from puppet_lib.caller import (
    blocker_from_error,
    caller_projection,
    doctor_blocker,
    final_outcome,
    make_blocker,
    progress_cursor,
)
from puppet_lib.errors import IdentityError, UnsupportedError
from puppet_lib.registry import ProcessExecutableUnavailable
from puppet_lib.transport import bind_run_transport


class CallerContractTests(unittest.TestCase):
    def test_blockers_are_actionable_and_body_safe(self):
        blocker = doctor_blocker(
            "process_identity_unavailable",
            "process executable identity is unavailable",
            pid=4242,
            kernel_birth_id="linux:boot:99",
            pane="%7",
        )
        self.assertEqual(blocker["schema"], "puppet.caller-blocker/v1")
        self.assertEqual(blocker["pid"], 4242)
        self.assertIn("halt only the exact recorded pid", blocker["remedy"])
        self.assertNotIn("\n", blocker["changed"])
        error = ProcessExecutableUnavailable(
            "process executable identity is unavailable",
            pid=99,
        )
        payload = error.as_dict()
        self.assertEqual(payload["blocker"]["pid"], 99)
        self.assertEqual(payload["blocker"]["code"], "process_identity_unavailable")
        wrapped = blocker_from_error(
            IdentityError("registered tmux pane no longer owns the target process"),
            pid=12,
            pane="%1",
        )
        self.assertEqual(wrapped["pid"], 12)
        self.assertEqual(wrapped["pane"], "%1")

    def test_progress_and_outcomes_stay_distinct(self):
        record = {
            "session": "session-1",
            "target": "agy",
            "state": "ACTIVE",
            "process": {"pid": 8, "kernel_birth_id": "darwin:1:8"},
            "last_checkpoint": None,
            "last_beacon": None,
            "last_validated_at": None,
            "transport": bind_run_transport(),
        }
        cursor = progress_cursor(record)
        self.assertEqual(cursor["beacon_sequence"], 0)
        self.assertIsNone(cursor["checkpoint_id"])
        self.assertIsNone(final_outcome(record, transport_id="tmux"))
        record["last_checkpoint"] = {"checkpoint_id": "a" * 64}
        record["last_beacon"] = {"sequence": 2}
        record["last_validated_at"] = "2026-09-18T00:00:00Z"
        record["state"] = "SOURCE_ACCEPTED"
        projection = caller_projection(record, transport_id="tmux")
        self.assertEqual(projection["progress_cursor"]["beacon_sequence"], 2)
        self.assertEqual(projection["caller_outcome"]["worker_completion"], "reported")
        self.assertEqual(projection["caller_outcome"]["controller_acceptance"], "none")
        self.assertEqual(projection["caller_outcome"]["halt"], "none")
        self.assertIsNone(projection["final_outcome"])
        record["state"] = "ACCEPTED"
        accepted = caller_projection(record, transport_id="tmux")
        self.assertEqual(
            accepted["caller_outcome"]["controller_acceptance"], "accepted"
        )
        self.assertEqual(accepted["caller_outcome"]["halt"], "none")
        self.assertIn("controller accepted", accepted["final_outcome"]["summary"])
        record["state"] = "HALTED"
        halted = caller_projection(record, transport_id="tmux", halt_confirmed=True)
        self.assertEqual(halted["caller_outcome"]["halt"], "confirmed")
        self.assertEqual(
            halted["caller_outcome"]["controller_acceptance"], "none"
        )
        self.assertEqual(halted["final_outcome"]["process"]["pid"], 8)

    def test_unsupported_transport_error_includes_remedy(self):
        with self.assertRaises(UnsupportedError) as raised:
            bind_run_transport("acp")
        payload = raised.exception.as_dict()
        self.assertEqual(payload["blocker"]["code"], "transport_unsupported")
        self.assertIn("no fallback", payload["blocker"]["remedy"])
        self.assertEqual(
            make_blocker(code="tmux_unavailable", detail="tmux is unavailable")[
                "remedy"
            ].startswith("install tmux"),
            True,
        )
