from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "puppet" / "scripts"))

from puppet_lib.errors import ConflictError, ValidationError  # noqa: E402
from puppet_lib.journal import Journal  # noqa: E402


class JournalTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
