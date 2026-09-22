from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "puppet" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from antigravity_acpx import (
    ACPX_ARTIFACT_PATH,
    ACPX_ARTIFACT_SHA256,
    ACPX_MERGE_COMMIT,
    ADAPTER_ID,
    TARGET,
    TRANSPORT_ID,
    claim_isolated_root,
    load_isolated_root,
    mark_cleanup_unknown,
    persist_turn_receipt,
    require_antigravity_acp_target,
    validate_ownership,
)
from puppet_lib.authority import AUTHORITY_ID
from puppet_lib.errors import ConflictError, IdentityError, UnsupportedError, ValidationError
from puppet_lib.transport import DEFAULT_TRANSPORT, bind_run_transport, transport_is_available


def _private_root(temporary: str, name: str = "isolated") -> Path:
    root = Path(temporary).resolve() / name
    root.mkdir(mode=0o700)
    os.chmod(root, 0o700)
    return root


class AntigravityAcpxOwnershipTests(unittest.TestCase):
    def test_ordinary_launch_stays_unavailable_and_pins_remain_frozen(self):
        self.assertEqual(TRANSPORT_ID, "antigravity-acp")
        self.assertEqual(TARGET, "agy")
        self.assertEqual(ADAPTER_ID, "antigravity-acpx")
        self.assertEqual(ACPX_MERGE_COMMIT, "2e05de525dd1ab62e9e74bf02d91e3638920fcf3")
        self.assertEqual(
            ACPX_ARTIFACT_SHA256,
            "5df327172d83644b5f44925386095c8facce28eb78d1ea81f243d7b100d6e614",
        )
        self.assertEqual(
            ACPX_ARTIFACT_PATH,
            "runs/puppet-dual-acp-controller-runs/20260921/artifacts-refresh-2e05de52/acpx-0.18.0.tgz",
        )
        self.assertEqual(DEFAULT_TRANSPORT, "tmux")
        self.assertEqual(bind_run_transport()["id"], "tmux")
        self.assertFalse(transport_is_available(TRANSPORT_ID))
        with self.assertRaisesRegex(ValidationError, "requires target agy"):
            require_antigravity_acp_target("cursor")

    def test_claim_rejects_foreign_owner_and_session_mismatch(self):
        with tempfile.TemporaryDirectory() as temporary:
            isolated = _private_root(temporary)
            first = claim_isolated_root(
                isolated,
                owner="puppet-owner",
                session="agy-acp-session",
                conversation_id="conv-agy-acp-1",
            )
            self.assertEqual(first["authority_id"], AUTHORITY_ID)
            self.assertFalse(first["available"])
            self.assertEqual(first["ordinary_launch"], "unavailable")
            self.assertEqual(first["cleanup"], "owned")
            with self.assertRaises(ConflictError):
                claim_isolated_root(
                    isolated,
                    owner="other-owner",
                    session="agy-acp-session",
                    conversation_id="conv-agy-acp-1",
                )
            with self.assertRaisesRegex(IdentityError, "session identity"):
                claim_isolated_root(
                    isolated,
                    owner="puppet-owner",
                    session="other-session",
                    conversation_id="conv-agy-acp-1",
                )

    def test_uncertain_cleanup_blocks_replacement(self):
        with tempfile.TemporaryDirectory() as temporary:
            isolated = _private_root(temporary)
            claim_isolated_root(
                isolated,
                owner="puppet-owner",
                session="agy-acp-session",
                conversation_id="conv-agy-acp-1",
            )
            marked = mark_cleanup_unknown(isolated)
            self.assertEqual(marked["cleanup"], "unknown")
            self.assertTrue(marked["replacement_blocked"])
            with self.assertRaisesRegex(IdentityError, "replacement is blocked"):
                claim_isolated_root(
                    isolated,
                    owner="puppet-owner",
                    session="agy-acp-session",
                    conversation_id="conv-agy-acp-1",
                )
            loaded = load_isolated_root(isolated)
            self.assertEqual(loaded["cleanup"], "unknown")

    def test_missing_ownership_is_unsupported_and_schema_stays_exact(self):
        with tempfile.TemporaryDirectory() as temporary:
            isolated = _private_root(temporary)
            with self.assertRaises(UnsupportedError):
                load_isolated_root(isolated)
            claim = claim_isolated_root(
                isolated,
                owner="puppet-owner",
                session="agy-acp-session",
                conversation_id="conv-agy-acp-1",
            )
            drifted = dict(claim)
            drifted["available"] = True
            with self.assertRaisesRegex(ValidationError, "ordinary launch"):
                validate_ownership(drifted)
            drifted = dict(claim)
            drifted["qualification"] = "qualified"
            with self.assertRaisesRegex(ValidationError, "live qualification"):
                validate_ownership(drifted)

    def test_turn_receipt_sink_drops_non_enum_permission_diagnostics(self):
        with tempfile.TemporaryDirectory() as temporary:
            isolated = _private_root(temporary)
            claim_isolated_root(
                isolated,
                owner="puppet-owner",
                session="agy-acp-session",
                conversation_id="conv-agy-acp-1",
            )
            persist_turn_receipt(
                isolated,
                session="agy-acp-session",
                conversation_id="conv-agy-acp-1",
                request_id="req-agy-acp-1",
                extras={
                    "status": "completed",
                    "stop_reason": "end_turn",
                    "permission": {
                        "schema": "puppet.antigravity-acp-host-permission/v1",
                        "outcome": "allow_once",
                        "permission_id": "edit",
                        "permission_kind": "edit",
                        "kind": "edit",
                        "kind_source": "standardized",
                        "id_class": "opaque",
                        "path_source": "raw_input",
                        "path_cardinality": "one",
                        "path_class": "intended",
                        "reason": "granted_once",
                        "offered_option_kinds": [
                            "allow_once",
                            "reject_once",
                            "allow_once",
                            "approve_all",
                            "rm -rf /tmp",
                            "/secret/bin/normalize-lines.mjs",
                            "allow_always",
                            "reject_always",
                            "yes",
                            "allow_once",
                        ],
                        "grant_count": 1,
                        "allowed": True,
                        "persisted": False,
                        "approve_all": False,
                        "os_sandbox": False,
                        "fs": False,
                        "terminal": False,
                        "ordinary_launch": "unavailable",
                        "body_retained": False,
                        "invented_decision": None,
                        "title": "write /secret/bin/normalize-lines.mjs",
                        "path": "/secret/bin/normalize-lines.mjs",
                        "label": "Delete production",
                        "command": "cat /etc/passwd",
                        "input": {"path": "/secret/token"},
                        "decisions": [
                            {
                                "outcome": "allow_once",
                                "permission_kind": "edit",
                                "kind": "edit",
                                "kind_source": "inferred",
                                "id_class": "tool-call-id-abc",
                                "path_source": "/Users/bobbybones/.env",
                                "path_cardinality": "one",
                                "path_class": "non_intended",
                                "reason": "cat /etc/shadow",
                                "offered_option_kinds": [
                                    "allow_always",
                                    "allow_always",
                                    "yes",
                                    "allow_once",
                                    "curl http://evil.example",
                                ],
                                "title": "evil title",
                                "command": "curl http://evil.example",
                                "label": "secret-label",
                            },
                            {
                                "outcome": "denied",
                                "permission_kind": "denied",
                                "kind": "execute; rm -rf /",
                                "kind_source": "standardized",
                                "id_class": "opaque",
                                "path_source": "locations",
                                "path_cardinality": "one",
                                "path_class": "intended",
                                "reason": "non_intended_path",
                                "offered_option_kinds": ["reject_once", "reject_once"],
                            },
                        ],
                    },
                },
            )
            events = [
                json.loads(line)
                for line in (isolated / "ownership.events.jsonl").read_text().splitlines()
            ]
            turn_events = [
                item for item in events if item.get("event") == "runtime_turn_observed"
            ]
            self.assertEqual(len(turn_events), 1)
            receipt = turn_events[0]
            permission = receipt["permission"]
            self.assertEqual(receipt["status"], "completed")
            self.assertEqual(receipt["stop_reason"], "end_turn")
            self.assertEqual(permission["outcome"], "allow_once")
            self.assertEqual(permission["permission_kind"], "edit")
            self.assertEqual(permission["kind"], "edit")
            self.assertEqual(permission["kind_source"], "standardized")
            self.assertEqual(permission["id_class"], "opaque")
            self.assertEqual(permission["path_source"], "raw_input")
            self.assertEqual(permission["path_cardinality"], "one")
            self.assertEqual(permission["path_class"], "intended")
            self.assertEqual(permission["reason"], "granted_once")
            self.assertEqual(
                permission["offered_option_kinds"],
                ["allow_once", "reject_once", "allow_always", "reject_always"],
            )
            self.assertFalse(permission["approve_all"])
            self.assertEqual(permission["grant_count"], 1)
            self.assertEqual(len(permission["decisions"]), 2)
            first = permission["decisions"][0]
            self.assertEqual(first["outcome"], "allow_once")
            self.assertEqual(first["permission_kind"], "edit")
            self.assertEqual(first["kind"], "edit")
            self.assertEqual(first["kind_source"], "inferred")
            self.assertNotIn("id_class", first)
            self.assertNotIn("path_source", first)
            self.assertEqual(first["path_cardinality"], "one")
            self.assertEqual(first["path_class"], "non_intended")
            self.assertNotIn("reason", first)
            self.assertEqual(first["offered_option_kinds"], ["allow_always", "allow_once"])
            self.assertNotIn("title", first)
            self.assertNotIn("command", first)
            second = permission["decisions"][1]
            self.assertEqual(second["outcome"], "denied")
            self.assertEqual(second["permission_kind"], "denied")
            self.assertNotIn("kind", second)
            self.assertEqual(second["kind_source"], "standardized")
            self.assertEqual(second["id_class"], "opaque")
            self.assertEqual(second["path_source"], "locations")
            self.assertEqual(second["reason"], "non_intended_path")
            self.assertEqual(second["offered_option_kinds"], ["reject_once"])
            dumped = json.dumps(receipt)
            self.assertNotIn("/secret/", dumped)
            self.assertNotIn("/etc/passwd", dumped)
            self.assertNotIn("/etc/shadow", dumped)
            self.assertNotIn(".env", dumped)
            self.assertNotIn("approve_all", permission["offered_option_kinds"])
            self.assertNotIn("tool-call-id-abc", dumped)
            self.assertNotIn("evil title", dumped)
            self.assertNotIn("Delete production", dumped)
            self.assertNotIn("http://evil.example", dumped)
            self.assertNotIn("rm -rf", dumped)
            self.assertNotIn("write /secret", dumped)
            with self.assertRaisesRegex(ValidationError, "body-bearing field"):
                persist_turn_receipt(
                    isolated,
                    session="agy-acp-session",
                    conversation_id="conv-agy-acp-1",
                    request_id="req-agy-acp-2",
                    extras={
                        "status": "completed",
                        "permission": {
                            "outcome": "denied",
                            "grant_count": 0,
                            "allowed": False,
                            "persisted": False,
                            "approve_all": False,
                            "os_sandbox": False,
                            "fs": False,
                            "terminal": False,
                            "ordinary_launch": "unavailable",
                            "body_retained": False,
                            "invented_decision": None,
                            "rawInput": {"path": "/secret/bin/normalize-lines.mjs"},
                        },
                    },
                )


if __name__ == "__main__":
    unittest.main()
