from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "puppet" / "scripts"))

from puppet_lib.errors import ValidationError  # noqa: E402
from puppet_lib.handoffs import (  # noqa: E402
    CONFORMANCE_PROTOCOL_DESCRIPTOR,
    PROTOCOL_FINGERPRINT,
    validate_handoff,
)
from puppet_lib.safety import canonical_json_bytes  # noqa: E402


FP = "a" * 64


def base_handoff():
    return {
        "schema_version": 1,
        "checkpoint_kind": "conformance",
        "session": "agy-proof",
        "run_id": "run-1",
        "nonce": "nonce-1",
        "phase": "ready",
        "sequence": 0,
        "executable_fingerprint": FP,
        "adapter_fingerprint": "b" * 64,
        "protocol_fingerprint": "c" * 64,
        "timestamp": "2026-07-22T02:00:00Z",
        "claims": [],
        "evidence_refs": ["evidence/identity.json"],
        "decisions_requested": [],
        "limitations": [],
    }


def write_json(path: Path, value):
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")


class HandoffTests(unittest.TestCase):
    def test_protocol_fingerprint_binds_the_canonical_schema_descriptor(self):
        self.assertEqual(
            PROTOCOL_FINGERPRINT,
            hashlib.sha256(
                canonical_json_bytes(CONFORMANCE_PROTOCOL_DESCRIPTOR)
            ).hexdigest(),
        )
        self.assertNotEqual(
            PROTOCOL_FINGERPRINT,
            hashlib.sha256(b"PUPPET_CONFORMANCE_V1").hexdigest(),
        )

    def test_ready_conformance_is_source_free(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "ready.json"
            write_json(path, base_handoff())
            result = validate_handoff(path, allowed_roots=[root])
            self.assertEqual(result.identity["phase"], "ready")
            self.assertNotIn("candidate_commit", result.identity)
            self.assertEqual(len(result.checkpoint_id), 64)

    def test_followup_binds_message_and_prior_hash(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            value = base_handoff()
            value.update(
                {
                    "phase": "followup",
                    "sequence": 1,
                    "message_id": "message-1",
                    "prior_checkpoint_sha256": "d" * 64,
                }
            )
            path = root / "followup.json"
            write_json(path, value)
            result = validate_handoff(path, allowed_roots=[root])
            self.assertEqual(result.identity["message_id"], "message-1")

    def test_conformance_rejects_candidate_commit(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            value = base_handoff()
            value["candidate_commit"] = "1" * 40
            path = root / "bad.json"
            write_json(path, value)
            with self.assertRaisesRegex(ValidationError, "fields"):
                validate_handoff(path, allowed_roots=[root])

    def test_source_requires_full_commit(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            value = base_handoff()
            value.pop("phase")
            value.pop("sequence")
            value["checkpoint_kind"] = "source"
            value["candidate_commit"] = "abc123"
            value["summary"] = "Bounded change"
            value["suggested_next_assignment"] = "Review it"
            path = root / "source.json"
            write_json(path, value)
            with self.assertRaisesRegex(ValidationError, "full 40"):
                validate_handoff(path, allowed_roots=[root])
            value["candidate_commit"] = "1" * 40
            write_json(path, value)
            result = validate_handoff(path, allowed_roots=[root])
            self.assertEqual(result.identity["candidate_commit"], "1" * 40)

    def test_identity_drift_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "ready.json"
            write_json(path, base_handoff())
            with self.assertRaisesRegex(ValidationError, "adapter_fingerprint"):
                validate_handoff(
                    path,
                    allowed_roots=[root],
                    expected={"adapter_fingerprint": "f" * 64},
                )

    def test_out_of_root_and_transcript_fields_are_rejected(self):
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            allowed = Path(first)
            path = Path(second) / "ready.json"
            write_json(path, base_handoff())
            with self.assertRaisesRegex(ValidationError, "outside"):
                validate_handoff(path, allowed_roots=[allowed])
            value = base_handoff()
            value["claims"] = [{"transcript": "not allowed"}]
            path = allowed / "bad.json"
            write_json(path, value)
            with self.assertRaisesRegex(ValidationError, "forbidden"):
                validate_handoff(path, allowed_roots=[allowed])

    def test_oversized_and_unknown_fields_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            value = base_handoff()
            value["unknown"] = "x"
            path = root / "bad.json"
            write_json(path, value)
            with self.assertRaisesRegex(ValidationError, "fields"):
                validate_handoff(path, allowed_roots=[root])
            path.write_bytes(b"{" + b"x" * 70000 + b"}")
            with self.assertRaisesRegex(ValidationError, "size"):
                validate_handoff(path, allowed_roots=[root])


if __name__ == "__main__":
    unittest.main()
