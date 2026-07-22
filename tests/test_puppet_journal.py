from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "puppet" / "scripts"))

from puppet_lib.errors import ConflictError, IdentityError, ValidationError  # noqa: E402
from puppet_lib.halt_control import deliver_halt_actions  # noqa: E402
from puppet_lib.journal import Journal  # noqa: E402


class JournalTests(unittest.TestCase):
    @staticmethod
    def _process_identity(kernel_birth_id="test:4242"):
        return {
            "identity_version": 2,
            "pid": 4242,
            "start": "Wed Jul 22 04:00:00 2026",
            "kernel_birth_id": kernel_birth_id,
            "command": "agy",
            "executable_path": "/opt/bin/agy",
            "device": 1,
            "inode": 2,
        }

    def test_append_replay_and_idempotency(self):
        with tempfile.TemporaryDirectory() as temporary:
            journal = Journal(Path(temporary))
            first = journal.append(
                request_id="request-1",
                timestamp="2026-07-22T02:00:00Z",
                event={"kind": "launch", "content_sha256": "a" * 64},
            )
            same = journal.append(
                request_id="request-1",
                timestamp="2026-07-22T03:00:00Z",
                event={"kind": "launch", "content_sha256": "a" * 64},
            )
            self.assertEqual(first, same)
            self.assertEqual(len(journal.replay()), 1)

    def test_duplicate_request_with_different_event_conflicts(self):
        with tempfile.TemporaryDirectory() as temporary:
            journal = Journal(Path(temporary))
            journal.append(request_id="request-1", event={"kind": "launch"})
            with self.assertRaises(ConflictError):
                journal.append(request_id="request-1", event={"kind": "halt"})

    def test_tampered_chain_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            journal = Journal(root)
            journal.append(request_id="request-1", event={"kind": "launch"})
            row = json.loads(journal.events_path.read_text(encoding="utf-8"))
            row["event"]["kind"] = "tampered"
            journal.events_path.write_text(json.dumps(row) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValidationError, "entry hash"):
                journal.replay()

    def test_truncated_append_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            journal = Journal(Path(temporary))
            journal.events_path.write_bytes(b'{"sequence":1}')
            with self.assertRaisesRegex(ValidationError, "truncated"):
                journal.replay()

    def test_head_mismatch_fails_before_append(self):
        with tempfile.TemporaryDirectory() as temporary:
            journal = Journal(Path(temporary))
            journal.append(request_id="request-1", event={"kind": "launch"})
            journal.head_path.write_text(
                '{"entry_hash":"%s","sequence":9}\n' % ("f" * 64),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValidationError, "head"):
                journal.append(request_id="request-2", event={"kind": "send"})

    def test_missing_head_is_recovered_after_valid_replay(self):
        with tempfile.TemporaryDirectory() as temporary:
            journal = Journal(Path(temporary))
            journal.append(request_id="request-1", event={"kind": "launch"})
            journal.append(request_id="request-2", event={"kind": "launch"})
            journal.head_path.unlink()
            journal.append(request_id="request-3", event={"kind": "send"})
            rows = journal.replay()
            self.assertEqual(len(rows), 3)
            self.assertEqual(journal.lookup("request-1"), rows[0])
            self.assertEqual(journal.snapshot()[1]["request_id"], "request-2")

    def test_stale_head_is_recovered_if_it_matches_existing_history(self):
        with tempfile.TemporaryDirectory() as temporary:
            journal = Journal(Path(temporary))
            first = journal.append(request_id="request-1", event={"kind": "launch"})
            journal.append(request_id="request-2", event={"kind": "launch"})
            journal.head_path.write_text(
                json.dumps(
                    {"sequence": first["sequence"], "entry_hash": first["entry_hash"]}
                )
                + "\n",
                encoding="utf-8",
            )
            third = journal.append(request_id="request-3", event={"kind": "send"})
            self.assertEqual(third["sequence"], 3)
            self.assertEqual(journal.replay()[2]["request_id"], "request-3")

    def test_invalid_head_claim_not_present_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            journal = Journal(Path(temporary))
            journal.append(request_id="request-1", event={"kind": "launch"})
            journal.append(request_id="request-2", event={"kind": "launch"})
            # Keep rows valid so replay succeeds and we can detect stale/missing head safety checks.
            journal.head_path.write_text(
                json.dumps({"sequence": 3, "entry_hash": "f" * 64}) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValidationError, "does not match"):
                journal.append(request_id="request-4", event={"kind": "send"})

    def test_sensitive_event_field_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            journal = Journal(Path(temporary))
            with self.assertRaisesRegex(ValidationError, "forbidden"):
                journal.append(
                    request_id="request-1",
                    event={"kind": "send", "prompt_body": "must not persist"},
                )

    def test_kernel_birth_id_is_not_secret_shaped_but_token_field_is(self):
        with tempfile.TemporaryDirectory() as temporary:
            journal = Journal(Path(temporary))
            recorded = journal.append(
                request_id="request-birth",
                event={
                    "kind": "identity",
                    "kernel_birth_id": "darwin:1784700000:001234",
                },
            )
            self.assertEqual(
                recorded["event"]["kernel_birth_id"],
                "darwin:1784700000:001234",
            )
            with self.assertRaisesRegex(ValidationError, "forbidden"):
                journal.append(
                    request_id="request-token",
                    event={"kind": "identity", "birth_token": "not-a-secret"},
                )

    def test_interrupted_exact_signal_attempt_is_never_resent(self):
        with tempfile.TemporaryDirectory() as temporary:
            journal = Journal(Path(temporary))
            attempts = []

            def interrupt_after_attempt(action):
                attempts.append(action)
                raise KeyboardInterrupt()

            with self.assertRaises(KeyboardInterrupt):
                deliver_halt_actions(
                    journal=journal,
                    session="exact-sigint",
                    target_identity=self._process_identity(),
                    actions=["exact_pid_sigint"],
                    process_alive=lambda: True,
                    deliver_action=interrupt_after_attempt,
                )
            with self.assertRaisesRegex(IdentityError, "ambiguous"):
                deliver_halt_actions(
                    journal=journal,
                    session="exact-sigint",
                    target_identity=self._process_identity(),
                    actions=["exact_pid_sigint"],
                    process_alive=lambda: True,
                    deliver_action=lambda action: attempts.append(action),
                )
            self.assertEqual(attempts, ["exact_pid_sigint"])

    def test_halt_journal_rejects_same_pid_with_a_new_birth_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            journal = Journal(Path(temporary))
            alive = {"value": True}
            attempted = []

            def stop_after_first(action):
                attempted.append(action)
                alive["value"] = False

            deliver_halt_actions(
                journal=journal,
                session="agy-birth-bound",
                target_identity=self._process_identity("test:first"),
                actions=["tmux_pane_eof", "tmux_pane_eof"],
                process_alive=lambda: alive["value"],
                deliver_action=stop_after_first,
            )
            self.assertEqual(attempted, ["tmux_pane_eof"])

            with self.assertRaisesRegex(IdentityError, "identity changed"):
                deliver_halt_actions(
                    journal=journal,
                    session="agy-birth-bound",
                    target_identity=self._process_identity("test:replacement"),
                    actions=["tmux_pane_eof", "tmux_pane_eof"],
                    process_alive=lambda: True,
                    deliver_action=lambda action: attempted.append(action),
                )
            self.assertEqual(attempted, ["tmux_pane_eof"])


if __name__ == "__main__":
    unittest.main()
