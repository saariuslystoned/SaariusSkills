from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "puppet" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from puppet_lib.contracts import Contract  # noqa: E402
from puppet_lib.errors import ValidationError  # noqa: E402
from puppet_lib.safety import (  # noqa: E402
    atomic_write_json,
    paths_overlap,
    validate_branch,
    validate_identifier,
)
from puppet_lib.state import transition  # noqa: E402


HARD_GATES = [
    "merge",
    "push",
    "deploy",
    "force_push",
    "global_install",
    "external_send",
    "spend",
    "secrets",
    "account_change",
    "destructive_cleanup",
]


def valid_contract(repo: Path):
    return {
        "schema_version": 1,
        "objective": "Run one bounded conformance fixture",
        "campaign_authorization_id": "campaign-1",
        "controller": "codex",
        "target": "agy",
        "task_profile": "conformance",
        "harness_trust": "unrestricted_required",
        "mutation_owner": "none",
        "repo": str(repo),
        "branch": "codex/example",
        "allowed_modes": ["read", "test"],
        "terminal_criteria": [{"id": "proof_green", "evidence": "validated_handoff"}],
        "hard_gates": list(HARD_GATES),
    }


class ContractTests(unittest.TestCase):
    def test_valid_contract_has_stable_fingerprint(self):
        with tempfile.TemporaryDirectory() as temporary:
            raw = valid_contract(Path(temporary))
            first = Contract.from_dict(raw)
            second = Contract.from_dict(dict(reversed(list(raw.items()))))
            self.assertEqual(first.fingerprint, second.fingerprint)
            self.assertEqual(first.target, "agy")

    def test_agy_default_session_profile_is_back_compatible(self):
        with tempfile.TemporaryDirectory() as temporary:
            raw = valid_contract(Path(temporary))
            contract = Contract.from_dict(raw)
            self.assertEqual(contract.target, "agy")
            self.assertEqual(contract.session_profile, "teamwork-preview")
            self.assertNotIn("session_profile", contract.raw)

    def test_explicit_session_profile_is_part_of_contract_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            raw = valid_contract(Path(temporary))
            defaulted = Contract.from_dict(raw)
            raw["session_profile"] = "teamwork-preview"
            explicit = Contract.from_dict(raw)
            self.assertEqual(defaulted.session_profile, explicit.session_profile)
            self.assertNotEqual(defaulted.fingerprint, explicit.fingerprint)

    def test_non_agy_default_session_profile_is_regular(self):
        with tempfile.TemporaryDirectory() as temporary:
            raw = valid_contract(Path(temporary))
            raw["target"] = "codex"
            raw["controller"] = "agy"
            contract = Contract.from_dict(raw)
            self.assertEqual(contract.target, "codex")
            self.assertEqual(contract.session_profile, "regular")

    def test_invalid_session_profile_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            raw = valid_contract(Path(temporary))
            raw["session_profile"] = "not-a-profile"
            with self.assertRaisesRegex(ValidationError, "unsupported session profile"):
                Contract.from_dict(raw)

    def test_missing_gate_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            raw = valid_contract(Path(temporary))
            raw["hard_gates"].remove("secrets")
            with self.assertRaisesRegex(ValidationError, "missing mandatory"):
                Contract.from_dict(raw)

    def test_read_only_owner_cannot_mutate(self):
        with tempfile.TemporaryDirectory() as temporary:
            raw = valid_contract(Path(temporary))
            raw["allowed_modes"].append("mutate")
            with self.assertRaisesRegex(ValidationError, "cannot authorize mutation"):
                Contract.from_dict(raw)

    def test_overlapping_supervisor_and_candidate_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            raw = valid_contract(repo)
            raw["mutation_owner"] = "target"
            raw["allowed_modes"] = ["read", "test", "mutate", "local_commit"]
            raw["supervisor_root"] = str(repo)
            raw["candidate_root"] = str(repo)
            with self.assertRaisesRegex(ValidationError, "overlap"):
                Contract.from_dict(raw)

    def test_identifier_and_branch_reject_hostile_values(self):
        for value in ("../escape", "bad;touch", "two words", ""):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                validate_identifier(value)
        for value in ("../escape", "main..evil", "topic//child", "topic/@{bad"):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                validate_branch(value)

    def test_path_overlap_is_symmetric(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            child = root / "child"
            child.mkdir()
            other = root.parent / (root.name + "-other")
            self.assertTrue(paths_overlap(root, child))
            self.assertTrue(paths_overlap(child, root))
            self.assertFalse(paths_overlap(root, other))

    def test_state_machine_rejects_illegal_acceptance(self):
        self.assertEqual(transition("NEW", "PREFLIGHTED"), "PREFLIGHTED")
        with self.assertRaisesRegex(ValidationError, "illegal lifecycle"):
            transition("ACTIVE", "ACCEPTED")
        with self.assertRaisesRegex(ValidationError, "illegal lifecycle"):
            transition("HALTED", "ACTIVE")

    def test_atomic_json_replaces_projection(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "state.json"
            atomic_write_json(path, {"version": 1})
            atomic_write_json(path, {"version": 2})
            self.assertEqual(path.read_text(encoding="utf-8"), '{"version":2}\n')


if __name__ == "__main__":
    unittest.main()
