from __future__ import annotations

import copy
import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "grilltrack" / "scripts" / "validate_picker.py"
FIXTURE = ROOT / "fixtures" / "frontend-picker" / "manifest.json"

SPEC = importlib.util.spec_from_file_location("validate_picker", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class PickerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def test_valid_fixture(self) -> None:
        MODULE.validate(self.manifest)

    def test_requires_exactly_five_candidates(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        manifest["candidates"].pop()
        with self.assertRaisesRegex(MODULE.PickerError, "exactly five"):
            MODULE.validate(manifest)

    def test_rejects_candidate_recommendation(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        manifest["candidates"][0]["recommended"] = True
        with self.assertRaisesRegex(MODULE.PickerError, "neutrally"):
            MODULE.validate(manifest)

    def test_requires_one_active_unresolved_slot(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        manifest["slots"][0]["status"] = "unresolved"
        manifest["slots"][0].pop("selection_ref")
        with self.assertRaisesRegex(MODULE.PickerError, "exactly one"):
            MODULE.validate(manifest)

    def test_rejects_production_picker(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        manifest["production"] = True
        with self.assertRaisesRegex(MODULE.PickerError, "production=false"):
            MODULE.validate(manifest)


if __name__ == "__main__":
    unittest.main()
