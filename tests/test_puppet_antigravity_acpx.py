from __future__ import annotations

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


if __name__ == "__main__":
    unittest.main()
