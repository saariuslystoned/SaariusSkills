from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "puppet" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from puppet_lib.authority import AUTHORITY_ID
from puppet_lib.cursor_acp import VERIFIED_CURSOR_ACP_CATALOG, fixture_observation
from puppet_lib.safety import canonical_json_bytes, sha256_bytes
from cursor_acpx import (
    ACPX_ARTIFACT_PATH,
    ACPX_ARTIFACT_SHA256,
    ACPX_CANDIDATE_PACKAGE_VERSION,
    ACPX_HEAD,
    ACPX_MERGE_COMMIT,
    ACPX_NPM_GIT_HEAD,
    ACPX_ORDINARY_PINNED_PACKAGE,
    ACPX_PR_BASE,
    ACPX_PR_HEAD,
    ACPX_SOURCE,
    ACPX_SOURCE_COMMIT,
    ACPX_STATUS,
    ADAPTER_ID,
    CursorAcpxAdapter,
    FORBIDDEN_CALLBACKS,
    acpx_dependency_identity,
    audit_durable_artifacts,
    claim_isolated_root,
    cutover_safeguards,
    fixture_runtime,
    load_isolated_root,
    prove_local_artifact,
    public_runtime_boundary,
    validate_acpx_dependency_identity,
    validate_cutover_safeguards,
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


def _metadata_hash(pin):
    body = {key: value for key, value in pin.items() if key not in {"schema", "integrity"}}
    return sha256_bytes(canonical_json_bytes(body))


class CursorAcpxAdapterTests(unittest.TestCase):
    def test_pin_and_public_boundary_stay_disabled(self):
        pin = validate_acpx_dependency_identity(acpx_dependency_identity())
        self.assertEqual(pin["source"], ACPX_SOURCE)
        self.assertEqual(pin["head"], ACPX_HEAD)
        self.assertEqual(pin["status"], "merged_unreleased")
        self.assertEqual(pin["status"], ACPX_STATUS)
        self.assertTrue(pin["merged"])
        self.assertFalse(pin["released"])
        self.assertEqual(pin["qualification"], "synthetic_only")
        self.assertEqual(pin["ordinary_pinned_package"], ACPX_ORDINARY_PINNED_PACKAGE)
        self.assertEqual(len(pin["integrity"]), 64)
        self.assertEqual(pin["integrity"], pin["artifact_sha256"])
        self.assertEqual(pin["artifact_sha256"], ACPX_ARTIFACT_SHA256)
        self.assertNotEqual(pin["integrity"], _metadata_hash(pin))
        self.assertEqual(pin["integrity"], acpx_dependency_identity()["integrity"])
        boundary = public_runtime_boundary()
        self.assertFalse(boundary["available"])
        self.assertFalse(boundary["fs"])
        self.assertFalse(boundary["terminal"])
        self.assertFalse(boundary["approve_all"])
        self.assertEqual(boundary["permission_policy"], "not_imported")
        self.assertEqual(boundary["mcp_broker_policy"], "not_imported")
        self.assertEqual(boundary["ordinary_launch"], "unavailable")
        self.assertEqual(boundary["merged_callback_options"], ["fs", "terminal"])
        self.assertEqual(boundary["callback_omit_default"], "enabled")
        self.assertFalse(boundary["callback_persisted"])
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

    def test_merged_unreleased_provenance_is_exact_and_fail_closed(self):
        pin = acpx_dependency_identity()
        self.assertEqual(pin["merge_commit"], ACPX_MERGE_COMMIT)
        self.assertEqual(pin["source_commit"], ACPX_SOURCE_COMMIT)
        self.assertEqual(pin["head"], ACPX_MERGE_COMMIT)
        self.assertEqual(pin["pr_head"], ACPX_PR_HEAD)
        self.assertEqual(pin["pr_base"], ACPX_PR_BASE)
        self.assertEqual(pin["npm_git_head"], ACPX_NPM_GIT_HEAD)
        self.assertEqual(pin["candidate_package_version"], ACPX_CANDIDATE_PACKAGE_VERSION)
        self.assertEqual(pin["published_npm_version"], "0.18.0")
        self.assertFalse(pin["published_npm_contains_merge"])
        distinct = {
            pin["merge_commit"],
            pin["pr_head"],
            pin["pr_base"],
            pin["npm_git_head"],
        }
        self.assertEqual(len(distinct), 4)
        self.assertNotEqual(pin["candidate_package_version"], pin["ordinary_pinned_package"])
        self.assertEqual(
            validate_acpx_dependency_identity(pin)["artifact_sha256"],
            ACPX_ARTIFACT_SHA256,
        )
        draft = dict(pin, status="draft", merged=False)
        with self.assertRaisesRegex(IdentityError, "draft-state"):
            validate_acpx_dependency_identity(draft)
        released = dict(pin, released=True)
        with self.assertRaisesRegex(IdentityError, "not a released package"):
            validate_acpx_dependency_identity(released)
        npm_as_merge = dict(pin, merge_commit=ACPX_NPM_GIT_HEAD, source_commit=ACPX_NPM_GIT_HEAD, head=ACPX_NPM_GIT_HEAD)
        with self.assertRaisesRegex(IdentityError, "stale npm gitHead"):
            validate_acpx_dependency_identity(npm_as_merge)
        metadata_integrity = dict(pin, integrity=_metadata_hash(pin))
        with self.assertRaisesRegex(IdentityError, "descriptive metadata"):
            validate_acpx_dependency_identity(metadata_integrity)
        published_merge = dict(pin, published_npm_contains_merge=True)
        with self.assertRaisesRegex(IdentityError, "does not contain the merge"):
            validate_acpx_dependency_identity(published_merge)
        live = dict(pin, qualification="live")
        with self.assertRaisesRegex(ValidationError, "live qualification"):
            validate_acpx_dependency_identity(live)

    def test_local_artifact_is_exact_source_and_exposes_callback_controls(self):
        proved = prove_local_artifact()
        self.assertEqual(proved["artifact_sha256"], ACPX_ARTIFACT_SHA256)
        self.assertEqual(proved["path"], ACPX_ARTIFACT_PATH)
        self.assertFalse(proved["released"])
        self.assertFalse(proved["published_npm_contains_merge"])
        artifact = ROOT / ACPX_ARTIFACT_PATH
        with tarfile.open(artifact) as tarball:
            runtime = tarball.extractfile("package/dist/runtime.d.ts")
            self.assertIsNotNone(runtime)
            text = runtime.read().decode("utf-8")
            package = tarball.extractfile("package/package.json")
            manifest = json.loads(package.read().decode("utf-8"))
        self.assertIn("fs?: boolean", text)
        self.assertIn("terminal?: boolean", text)
        self.assertIn("createAcpRuntime", text)
        self.assertIn("processLifecycle", text)
        self.assertEqual(manifest["version"], ACPX_CANDIDATE_PACKAGE_VERSION)
        self.assertNotEqual(manifest.get("gitHead"), ACPX_MERGE_COMMIT)
        with tempfile.TemporaryDirectory() as temporary:
            decoy = Path(temporary) / "acpx-0.18.0.tgz"
            decoy.write_bytes(b"not-the-merged-source")
            with self.assertRaisesRegex(IdentityError, "artifact digest drifted"):
                prove_local_artifact(decoy)

    def test_python_and_js_identity_and_cutover_parity(self):
        script = (
            "import { acpxDependencyIdentity, cutoverSafeguards } "
            "from './bridge/cursor-acp/puppet-adapter.mjs'; "
            "process.stdout.write(JSON.stringify({"
            "identity: acpxDependencyIdentity(), "
            "cutover: cutoverSafeguards()"
            "}))"
        )
        raw = subprocess.check_output(
            ["node", "--input-type=module", "-e", script],
            cwd=ROOT,
        )
        payload = json.loads(raw)
        self.assertEqual(payload["identity"], acpx_dependency_identity())
        self.assertEqual(payload["cutover"], cutover_safeguards())

    def test_cutover_safeguards_keep_ordinary_route_disabled(self):
        gates = validate_cutover_safeguards()
        self.assertFalse(gates["available"])
        self.assertEqual(gates["ordinary_launch"], "unavailable")
        self.assertEqual(gates["ordinary_pinned_package"], "0.16.0")
        self.assertEqual(gates["candidate_package_version"], "0.18.0")
        self.assertFalse(gates["released"])
        self.assertFalse(gates["published_npm_contains_merge"])
        self.assertFalse(gates["production_enabled"])
        self.assertFalse(gates["public_pr"])
        self.assertFalse(gates["live_qualification"])
        self.assertTrue(gates["ordinary_route_unchanged"])
        opened = dict(gates, available=True, production_enabled=True)
        with self.assertRaisesRegex(IdentityError, "cutover safeguards"):
            validate_cutover_safeguards(opened)
        self.assertFalse(transport_is_available("cursor-acp"))
        self.assertEqual(bind_run_transport()["id"], "tmux")

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
