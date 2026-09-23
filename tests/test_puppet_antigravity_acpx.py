from __future__ import annotations

import json
import os
import subprocess
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
from puppet_lib.antigravity_acp import (
    HOST_PERMISSION_DECISION_LIMIT,
    HOST_PERMISSION_SCHEMA,
    require_host_permission_outcome,
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
        lock = json.loads((ROOT / "bridge" / "antigravity-acp" / "package-lock.json").read_text(encoding="utf-8"))
        published = lock["packages"]["node_modules/acpx"]
        self.assertEqual(published["version"], "0.19.1")
        self.assertEqual(
            published["resolved"],
            "https://registry.npmjs.org/acpx/-/acpx-0.19.1.tgz",
        )
        self.assertEqual(
            published["integrity"],
            "sha512-zKVZVM6tHGXmdXU+sC30jdFLzz0ZpNLMorYKH+it3XcuEcvFl20sLbHPqfdjfsLfV+PmhRDEm1b9Np5KxgFHow==",
        )
        self.assertIn("acpx-0.18.0.tgz", ACPX_ARTIFACT_PATH)
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
            self.assertEqual(permission["decision_count"], 2)
            self.assertFalse(permission["decisions_truncated"])
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

    def test_turn_receipt_sink_type_safe_enums_bound_history_and_host_kinds(self):
        with tempfile.TemporaryDirectory() as temporary:
            isolated = _private_root(temporary)
            claim_isolated_root(
                isolated,
                owner="puppet-owner",
                session="agy-acp-session",
                conversation_id="conv-agy-acp-1",
            )
            extras = {
                "status": "completed",
                "permission": {
                    "schema": "not-a-host-schema",
                    "outcome": "allow_once",
                    "permission_id": "sk-live-secret",
                    "permission_kind": "fs_write_file",
                    "kind": ["edit"],
                    "kind_source": {"source": "standardized"},
                    "id_class": ["opaque"],
                    "path_source": {"path": "raw_input"},
                    "path_cardinality": ["one"],
                    "path_class": {"class": "intended"},
                    "reason": ["granted_once"],
                    "offered_option_kinds": [
                        ["allow_once"],
                        {"kind": "allow_once"},
                        "reject_once",
                        "allow_once",
                        "approve_all",
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
                    "decisions": [
                        {
                            "outcome": ["allow_once"],
                            "permission_kind": ["edit"],
                            "kind": ["edit"],
                            "offered_option_kinds": [["allow_once"], "allow_always"],
                        },
                        {
                            "outcome": "allow_once",
                            "permission_kind": "edit",
                            "kind": "edit",
                            "kind_source": "standardized",
                            "offered_option_kinds": [
                                "allow_once",
                                "allow_once",
                                "reject_once",
                            ],
                        },
                        {
                            "outcome": "denied",
                            "permission_kind": {"kind": "denied"},
                            "kind": {"name": "execute"},
                            "offered_option_kinds": {"0": "reject_once"},
                        },
                    ],
                },
            }
            persist_turn_receipt(
                isolated,
                session="agy-acp-session",
                conversation_id="conv-agy-acp-1",
                request_id="req-agy-acp-unsafe",
                extras=extras,
            )
            events = [
                json.loads(line)
                for line in (isolated / "ownership.events.jsonl").read_text().splitlines()
            ]
            permission = [
                item for item in events if item.get("event") == "runtime_turn_observed"
            ][-1]["permission"]
            self.assertNotIn("schema", permission)
            self.assertNotIn("permission_id", permission)
            self.assertNotIn("permission_kind", permission)
            self.assertNotIn("kind", permission)
            self.assertNotIn("kind_source", permission)
            self.assertNotIn("id_class", permission)
            self.assertNotIn("reason", permission)
            self.assertEqual(permission["offered_option_kinds"], ["reject_once", "allow_once"])
            self.assertEqual(len(permission["decisions"]), 2)
            self.assertEqual(permission["decisions"][0]["outcome"], "allow_once")
            self.assertEqual(permission["decisions"][0]["permission_kind"], "edit")
            self.assertEqual(
                permission["decisions"][0]["offered_option_kinds"],
                ["allow_once", "reject_once"],
            )
            self.assertEqual(permission["decisions"][1]["outcome"], "denied")
            self.assertNotIn("permission_kind", permission["decisions"][1])
            self.assertNotIn("kind", permission["decisions"][1])
            self.assertEqual(permission["decision_count"], 3)
            self.assertTrue(permission["decisions_truncated"])
            dumped = json.dumps(permission)
            self.assertNotIn("sk-live-secret", dumped)
            self.assertNotIn("fs_write_file", dumped)
            self.assertNotIn("approve_all", permission.get("offered_option_kinds", []))
            oversized = []
            for index in range(10_000):
                oversized.append(
                    {
                        "outcome": "allow_once" if index == 0 else "denied",
                        "permission_kind": "edit" if index == 0 else "denied",
                    }
                )
            persist_turn_receipt(
                isolated,
                session="agy-acp-session",
                conversation_id="conv-agy-acp-1",
                request_id="req-agy-acp-history",
                extras={
                    "status": "completed",
                    "permission": {
                        "schema": HOST_PERMISSION_SCHEMA,
                        "outcome": "denied",
                        "permission_id": "denied",
                        "permission_kind": "denied",
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
                        "decisions": oversized,
                    },
                },
            )
            events = [
                json.loads(line)
                for line in (isolated / "ownership.events.jsonl").read_text().splitlines()
            ]
            history = [
                item for item in events if item.get("event") == "runtime_turn_observed"
            ][-1]["permission"]
            self.assertEqual(history["schema"], HOST_PERMISSION_SCHEMA)
            self.assertEqual(history["permission_kind"], "denied")
            self.assertEqual(history["permission_id"], "denied")
            self.assertEqual(history["decision_count"], 10_000)
            self.assertTrue(history["decisions_truncated"])
            self.assertEqual(len(history["decisions"]), HOST_PERMISSION_DECISION_LIMIT)
            self.assertLess(len(history["decisions"]), history["decision_count"])
            self.assertEqual(history["grant_count"], 1)
            self.assertTrue(history["allowed"])
            self.assertNotIn("allow_once", [item["outcome"] for item in history["decisions"]])
            self.assertFalse(history["body_retained"])
            valid = {
                "schema": HOST_PERMISSION_SCHEMA,
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
                "offered_option_kinds": ["allow_once", "reject_once"],
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
                "decisions": [
                    {
                        "outcome": "allow_once",
                        "permission_kind": "edit",
                        "kind": "edit",
                        "kind_source": "standardized",
                        "id_class": "opaque",
                        "offered_option_kinds": ["allow_once", "reject_once"],
                        "reason": "granted_once",
                    },
                    {
                        "outcome": "denied",
                        "permission_kind": "denied",
                        "kind": "edit",
                        "kind_source": "standardized",
                        "id_class": "opaque",
                        "offered_option_kinds": ["reject_once"],
                        "reason": "replay",
                    },
                ],
            }
            persist_turn_receipt(
                isolated,
                session="agy-acp-session",
                conversation_id="conv-agy-acp-1",
                request_id="req-agy-acp-valid",
                extras={"status": "completed", "permission": valid},
            )
            events = [
                json.loads(line)
                for line in (isolated / "ownership.events.jsonl").read_text().splitlines()
            ]
            accepted = [
                item for item in events if item.get("event") == "runtime_turn_observed"
            ][-1]["permission"]
            self.assertEqual(accepted["permission_kind"], "edit")
            self.assertEqual(accepted["permission_id"], "edit")
            self.assertEqual(
                [item["outcome"] for item in accepted["decisions"]],
                ["allow_once", "denied"],
            )
            self.assertEqual(
                [item["permission_kind"] for item in accepted["decisions"]],
                ["edit", "denied"],
            )
            self.assertEqual(accepted["decision_count"], 2)
            self.assertFalse(accepted["decisions_truncated"])
            self.assertEqual(accepted["grant_count"], 1)
            self.assertTrue(accepted["allowed"])
            with self.assertRaisesRegex(ValidationError, "kind is invalid"):
                require_host_permission_outcome(
                    {
                        **valid,
                        "permission_kind": "fs_write_file",
                        "permission_id": "fs_write_file",
                    }
                )
            with self.assertRaisesRegex(ValidationError, "decision kind is invalid"):
                require_host_permission_outcome(
                    {
                        **valid,
                        "decisions": [
                            {"outcome": "allow_once", "permission_kind": ["edit"]}
                        ],
                    }
                )
            with self.assertRaisesRegex(ValidationError, "decision outcome is invalid"):
                require_host_permission_outcome(
                    {
                        **valid,
                        "decisions": [
                            {"outcome": ["denied"], "permission_kind": "denied"}
                        ],
                    }
                )

    def test_js_producer_and_python_sink_truncated_history_end_to_end(self):
        contract = ROOT / "bridge" / "antigravity-acp" / "host-permission-contract.mjs"
        script = """
import { bodyFreePermissionReceipt, HOST_PERMISSION_DECISION_LIMIT } from %s;
const decisions = Array.from({ length: 10000 }, (_, index) => ({
  outcome: index === 0 ? "allow_once" : "reject_once",
  permission_kind: index === 0 ? "edit" : "denied",
  kind: "edit",
  kind_source: "standardized",
  id_class: "opaque",
  path_source: "raw_input",
  path_cardinality: "one",
  path_class: index === 0 ? "intended" : "non_intended",
  offered_option_kinds: index === 0 ? ["allow_once", "reject_once"] : ["reject_once"],
  reason: index === 0 ? "granted_once" : "non_intended_path",
}));
const receipt = bodyFreePermissionReceipt({ sessionKey: "session-a", decisions });
process.stdout.write(JSON.stringify({
  receipt,
  limit: HOST_PERMISSION_DECISION_LIMIT,
}));
""" % (json.dumps(contract.as_posix()),)
        produced = json.loads(
            subprocess.check_output(
                ["node", "--input-type=module", "-e", script],
                cwd=str(ROOT),
                text=True,
            )
        )
        receipt = produced["receipt"]
        self.assertEqual(produced["limit"], HOST_PERMISSION_DECISION_LIMIT)
        self.assertEqual(receipt["decision_count"], 10_000)
        self.assertTrue(receipt["decisions_truncated"])
        self.assertEqual(len(receipt["decisions"]), HOST_PERMISSION_DECISION_LIMIT)
        self.assertLess(len(receipt["decisions"]), receipt["decision_count"])
        self.assertEqual(receipt["grant_count"], 1)
        self.assertTrue(receipt["allowed"])
        self.assertFalse(receipt["body_retained"])
        self.assertNotIn("rawInput", receipt)
        bounded = require_host_permission_outcome(receipt)
        self.assertEqual(bounded["decision_count"], 10_000)
        self.assertTrue(bounded["decisions_truncated"])
        self.assertEqual(len(bounded["decisions"]), HOST_PERMISSION_DECISION_LIMIT)
        self.assertEqual(bounded["grant_count"], 1)
        self.assertTrue(bounded["allowed"])
        self.assertEqual(bounded["permission_kind"], "denied")
        self.assertFalse(bounded["body_retained"])
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
                request_id="req-agy-acp-e2e",
                extras={"status": "completed", "permission": bounded},
            )
            events = [
                json.loads(line)
                for line in (isolated / "ownership.events.jsonl").read_text().splitlines()
            ]
            persisted = [
                item for item in events if item.get("event") == "runtime_turn_observed"
            ][-1]["permission"]
            self.assertEqual(persisted["decision_count"], 10_000)
            self.assertTrue(persisted["decisions_truncated"])
            self.assertEqual(len(persisted["decisions"]), HOST_PERMISSION_DECISION_LIMIT)
            self.assertLess(len(persisted["decisions"]), persisted["decision_count"])
            self.assertEqual(persisted["grant_count"], 1)
            self.assertTrue(persisted["allowed"])
            self.assertFalse(persisted["body_retained"])
            self.assertNotIn("rawInput", json.dumps(persisted))


if __name__ == "__main__":
    unittest.main()
