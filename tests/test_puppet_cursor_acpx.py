from __future__ import annotations

import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "puppet" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from puppet_lib.authority import AUTHORITY_ID
from puppet_lib.cursor_acp import VERIFIED_CURSOR_ACP_CATALOG, fixture_observation
from cursor_acpx import (
    ACPX_HEAD,
    ACPX_SOURCE,
    ACPX_STATUS,
    ADAPTER_ID,
    CursorAcpxAdapter,
    FORBIDDEN_CALLBACKS,
    acpx_dependency_identity,
    audit_durable_artifacts,
    claim_isolated_root,
    fixture_runtime,
    load_isolated_root,
    public_runtime_boundary,
    validate_public_runtime_options,
)
from puppet_lib.errors import ConflictError, IdentityError, UnsupportedError, ValidationError
from puppet_lib.qualification_scope import (
    shared_source_paths,
    target_source_paths,
)
from puppet_lib.transport import (
    DEFAULT_TRANSPORT,
    bind_run_transport,
    transport_capability_table,
    transport_is_available,
)


def _workspace():
    return {
        "path": "/tmp/cursor-acp-workspace",
        "branch": "codex/example",
        "head": "a" * 40,
        "tree": "b" * 40,
    }


def _private_root(temporary: str, name: str = "isolated") -> Path:
    root = Path(temporary).resolve() / name
    root.mkdir(mode=0o700)
    os.chmod(root, 0o700)
    return root


class CursorAcpxAdapterTests(unittest.TestCase):
    def test_pin_and_public_boundary_stay_disabled(self):
        pin = acpx_dependency_identity()
        self.assertEqual(pin["source"], ACPX_SOURCE)
        self.assertEqual(pin["head"], ACPX_HEAD)
        self.assertEqual(pin["status"], ACPX_STATUS)
        self.assertFalse(pin["merged"])
        self.assertFalse(pin["released"])
        self.assertEqual(pin["qualification"], "synthetic_only")
        self.assertEqual(len(pin["integrity"]), 64)
        self.assertEqual(pin["integrity"], acpx_dependency_identity()["integrity"])
        boundary = public_runtime_boundary()
        self.assertFalse(boundary["available"])
        self.assertFalse(boundary["fs"])
        self.assertFalse(boundary["terminal"])
        self.assertFalse(boundary["approve_all"])
        self.assertEqual(boundary["permission_policy"], "not_imported")
        self.assertEqual(boundary["mcp_broker_policy"], "not_imported")
        self.assertEqual(boundary["ordinary_launch"], "unavailable")
        self.assertFalse(CursorAcpxAdapter.available())
        self.assertFalse(CursorAcpxAdapter.ordinary_launch_available())
        self.assertFalse(transport_is_available("cursor-acp"))
        self.assertEqual(DEFAULT_TRANSPORT, "tmux")
        self.assertEqual(bind_run_transport()["id"], "tmux")
        self.assertEqual(transport_capability_table()["cursor-acp"]["implementation"], "implemented")
        self.assertNotIn("scripts/cursor_acpx.py", shared_source_paths())
        self.assertNotIn("scripts/cursor_acpx.py", target_source_paths("cursor"))
        self.assertNotIn(
            "scripts/cursor_acpx.py",
            target_source_paths("cursor", transport="cursor-acp"),
        )

    def test_public_runtime_rejects_broker_policy_and_private_options(self):
        accepted = validate_public_runtime_options(
            {
                "cwd": "/tmp/isolated",
                "sessionStore": object(),
                "agentRegistry": object(),
                "fs": False,
                "terminal": False,
            }
        )
        self.assertEqual(accepted["sessionStore"], "memory_only")
        with self.assertRaisesRegex(ValidationError, "approve-all or MCP"):
            validate_public_runtime_options(
                {
                    "cwd": "/tmp/isolated",
                    "sessionStore": object(),
                    "agentRegistry": object(),
                    "fs": False,
                    "terminal": False,
                    "permissionMode": "approve-all",
                }
            )
        with self.assertRaisesRegex(ValidationError, "private fields"):
            validate_public_runtime_options(
                {
                    "cwd": "/tmp/isolated",
                    "sessionStore": object(),
                    "agentRegistry": object(),
                    "fs": False,
                    "terminal": False,
                    "_internalClient": object(),
                }
            )
        with self.assertRaisesRegex(ValidationError, "approve-all or MCP"):
            validate_public_runtime_options(
                {
                    "cwd": "/tmp/isolated",
                    "sessionStore": object(),
                    "agentRegistry": object(),
                    "fs": False,
                    "terminal": False,
                    "mcpServers": [],
                }
            )
        with self.assertRaisesRegex(ValidationError, "filesystem callbacks"):
            validate_public_runtime_options(
                {
                    "cwd": "/tmp/isolated",
                    "sessionStore": object(),
                    "agentRegistry": object(),
                    "fs": True,
                    "terminal": False,
                }
            )

    def test_completion_is_distinct_from_controller_acceptance(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = _private_root(temporary)
            workspace = Path(temporary).resolve() / "workspace"
            workspace.mkdir()
            runtime = fixture_runtime(root, workspace_root=workspace)
            adapter = CursorAcpxAdapter(
                root,
                owner="puppet-owner",
                session="cursor-acp-session",
                conversation_id="conv-cursor-acp-1",
                workspace=_workspace(),
                runtime=runtime,
                catalog=VERIFIED_CURSOR_ACP_CATALOG,
            )
            adapter.bind_session()
            completed = adapter.complete(
                fixture_observation(
                    last_checkpoint={"checkpoint_id": "c" * 64},
                    record_state="ACTIVE",
                )
            )
            self.assertEqual(completed["caller_outcome"]["worker_completion"], "reported")
            self.assertEqual(completed["caller_outcome"]["controller_acceptance"], "none")
            self.assertIsNone(completed["final_outcome"])
            accepted = adapter.complete(
                fixture_observation(
                    last_checkpoint={"checkpoint_id": "c" * 64},
                    last_beacon={"sequence": 1},
                    last_validated_at="2026-09-20T00:00:00Z",
                    record_state="ACCEPTED",
                ),
                record_state="ACCEPTED",
            )
            self.assertEqual(accepted["caller_outcome"]["worker_completion"], "reported")
            self.assertEqual(accepted["caller_outcome"]["controller_acceptance"], "accepted")
            self.assertNotEqual(
                accepted["caller_outcome"]["worker_completion"],
                accepted["caller_outcome"]["controller_acceptance"],
            )
            self.assertFalse(accepted["available"])
            self.assertEqual(accepted["ordinary_launch"], "unavailable")

    def test_reconnect_load_retains_exact_session_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = _private_root(temporary)
            runtime = fixture_runtime(root)
            adapter = CursorAcpxAdapter(
                root,
                owner="puppet-owner",
                session="cursor-acp-session",
                conversation_id="conv-cursor-acp-1",
                workspace=_workspace(),
                runtime=runtime,
            )
            first = adapter.bind_session()
            loaded = adapter.reconnect()
            self.assertEqual(first, loaded)
            self.assertEqual(loaded["session"], "cursor-acp-session")
            self.assertEqual(loaded["conversation_id"], "conv-cursor-acp-1")
            ownership = load_isolated_root(root)
            self.assertEqual(ownership["session"], "cursor-acp-session")
            self.assertEqual(ownership["conversation_id"], "conv-cursor-acp-1")
            self.assertEqual(ownership["authority_id"], AUTHORITY_ID)
            self.assertEqual(ownership["lease"], "not_admitted")
            runtime._sessions["cursor-acp-session"] = {
                "session": "other-session",
                "conversation_id": "conv-cursor-acp-1",
            }
            with self.assertRaisesRegex(IdentityError, "exact session identity"):
                adapter.reconnect()

    def test_cancellation_is_not_observed_halt(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = _private_root(temporary)
            runtime = fixture_runtime(root)
            adapter = CursorAcpxAdapter(
                root,
                owner="puppet-owner",
                session="cursor-acp-session",
                conversation_id="conv-cursor-acp-1",
                workspace=_workspace(),
                runtime=runtime,
            )
            adapter.bind_session()
            requested = adapter.request_cancel()
            self.assertEqual(requested["status"], "cancellation-requested")
            self.assertEqual(requested["halt"], "none")
            with self.assertRaisesRegex(IdentityError, "not independently observed halt"):
                adapter.observe_halt(fixture_observation(terminal_state="completed"))
            halt = adapter.observe_halt(
                fixture_observation(
                    terminal_state="halted",
                    halt={
                        "session": "cursor-acp-session",
                        "conversation_id": "conv-cursor-acp-1",
                        "halted": True,
                    },
                )
            )
            self.assertTrue(halt["halted"])
            self.assertEqual(halt["session"], "cursor-acp-session")
            self.assertTrue(runtime.halted)

    def test_unsupported_question_requires_human_and_cancels_without_answer(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = _private_root(temporary)
            adapter = CursorAcpxAdapter(
                root,
                owner="puppet-owner",
                session="cursor-acp-session",
                conversation_id="conv-cursor-acp-1",
                workspace=_workspace(),
                runtime=fixture_runtime(root),
            )
            cancelled = adapter.require_human_question(
                {
                    "state": "interaction_required",
                    "interaction_id": "question-1",
                    "human_required": True,
                    "outcome": "cancelled",
                    "invented_answer": None,
                }
            )
            self.assertEqual(cancelled["outcome"], "cancelled")
            self.assertIsNone(cancelled["invented_answer"])
            with self.assertRaisesRegex(ValidationError, "invent"):
                adapter.require_human_question(
                    {
                        "state": "interaction_required",
                        "interaction_id": "question-1",
                        "human_required": True,
                        "outcome": "cancelled",
                        "invented_answer": "yes",
                    }
                )
            with self.assertRaisesRegex(ValidationError, "human"):
                adapter.require_human_question(
                    {
                        "state": "interaction_required",
                        "interaction_id": "question-1",
                        "human_required": False,
                        "outcome": "cancelled",
                        "invented_answer": None,
                    }
                )

    def test_forbidden_callbacks_have_no_local_side_effect(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = _private_root(temporary)
            workspace = Path(temporary).resolve() / "workspace"
            workspace.mkdir()
            runtime = fixture_runtime(
                root,
                workspace_root=workspace,
                requested_callbacks=tuple(sorted(FORBIDDEN_CALLBACKS)),
            )
            adapter = CursorAcpxAdapter(
                root,
                owner="puppet-owner",
                session="cursor-acp-session",
                conversation_id="conv-cursor-acp-1",
                workspace=_workspace(),
                runtime=runtime,
            )
            rejected = adapter.reject_callbacks()
            self.assertFalse(rejected["local_side_effect"])
            self.assertEqual(set(rejected["rejected"]), FORBIDDEN_CALLBACKS)
            self.assertEqual(list(workspace.iterdir()), [])
            self.assertFalse((workspace / "fs-write.side-effect").exists())

    def test_durable_artifacts_stay_body_free_and_missing_proof_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = _private_root(temporary)
            runtime = fixture_runtime(root)
            adapter = CursorAcpxAdapter(
                root,
                owner="puppet-owner",
                session="cursor-acp-session",
                conversation_id="conv-cursor-acp-1",
                workspace=_workspace(),
                runtime=runtime,
            )
            adapter.bind_session()
            persisted = adapter.persist_lifecycle(
                fixture_observation(
                    last_checkpoint={"checkpoint_id": "c" * 64},
                    record_state="ACCEPTED",
                ),
                record_state="ACCEPTED",
            )
            self.assertFalse(persisted["evidence"]["prompt_retained"])
            self.assertFalse(persisted["evidence"]["response_retained"])
            audit = audit_durable_artifacts(root)
            self.assertTrue(audit["ok"])
            raw_ownership = (root / "ownership.json").read_text(encoding="utf-8")
            raw_evidence = (root / "evidence.json").read_text(encoding="utf-8")
            raw_events = (root / "events.jsonl").read_text(encoding="utf-8")
            for blob in (raw_ownership, raw_evidence, raw_events):
                self.assertNotIn("Make the change", blob)
                self.assertNotIn('"prompt"', blob)
                self.assertNotIn('"transcript"', blob)
                self.assertNotIn('"messages"', blob)
            empty = _private_root(temporary, "empty")
            with self.assertRaisesRegex(UnsupportedError, "proof is missing"):
                audit_durable_artifacts(empty)
            leaked = json.loads(raw_evidence)
            leaked["prompt"] = "do not persist this body"
            (root / "evidence.json").write_text(json.dumps(leaked), encoding="utf-8")
            with self.assertRaisesRegex(ValidationError, "body-bearing"):
                audit_durable_artifacts(root)

    def test_process_query_failure_leaves_cleanup_unknown_and_blocks_replacement(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = _private_root(temporary)

            def fail_query(_identity):
                raise OSError("process query failed")

            runtime = fixture_runtime(root, process_query=fail_query)
            adapter = CursorAcpxAdapter(
                root,
                owner="puppet-owner",
                session="cursor-acp-session",
                conversation_id="conv-cursor-acp-1",
                workspace=_workspace(),
                runtime=runtime,
            )
            with self.assertRaisesRegex(IdentityError, "cleanup is unknown"):
                runtime.query_process()
            ownership = load_isolated_root(root)
            self.assertEqual(ownership["cleanup"], "unknown")
            self.assertTrue(ownership["replacement_blocked"])
            with self.assertRaisesRegex(IdentityError, "replacement is blocked"):
                claim_isolated_root(
                    root,
                    owner="puppet-owner",
                    session="cursor-acp-session",
                    conversation_id="conv-cursor-acp-1",
                )
            self.assertEqual(adapter.ownership["session"], "cursor-acp-session")

    def test_duplicate_isolated_root_ownership_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = _private_root(temporary)
            claim_isolated_root(
                root,
                owner="puppet-owner",
                session="cursor-acp-session",
                conversation_id="conv-cursor-acp-1",
            )
            with self.assertRaisesRegex(ConflictError, "already owned"):
                claim_isolated_root(
                    root,
                    owner="other-owner",
                    session="cursor-acp-session",
                    conversation_id="conv-cursor-acp-1",
                )
            same = claim_isolated_root(
                root,
                owner="puppet-owner",
                session="cursor-acp-session",
                conversation_id="conv-cursor-acp-1",
            )
            self.assertEqual(same["owner"], "puppet-owner")
            self.assertEqual(same["adapter"], ADAPTER_ID)
            self.assertEqual(stat.S_IMODE(root.stat().st_mode), 0o700)


if __name__ == "__main__":
    unittest.main()
