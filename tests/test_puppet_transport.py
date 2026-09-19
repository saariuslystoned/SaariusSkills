from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "puppet" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from puppet_lib.errors import UnsupportedError, ValidationError
from puppet_lib.transport import (
    DEFAULT_TRANSPORT,
    bind_run_transport,
    record_transport_id,
    transport_capability_table,
    validate_transport_binding,
)


class TransportBoundaryTests(unittest.TestCase):
    def test_default_binding_is_tmux_and_never_falls_back(self):
        binding = bind_run_transport()
        self.assertEqual(binding["id"], DEFAULT_TRANSPORT)
        self.assertEqual(binding["schema"], "puppet.transport-binding/v1")
        table = transport_capability_table()
        self.assertEqual(table["tmux"]["implementation"], "implemented")
        self.assertEqual(table["tmux"]["halt_authority"], "puppet_owned_birth_and_exact_target")
        self.assertEqual(table["tmux"]["resume_proves"], "unsupported")
        for name in ("herdr", "acp", "agy-print"):
            self.assertEqual(table[name]["implementation"], "unsupported")
            with self.assertRaisesRegex(UnsupportedError, "not implemented"):
                bind_run_transport(name)
        with self.assertRaisesRegex(ValidationError, "does not match"):
            bind_run_transport("herdr", contract_transport="tmux")

    def test_session_record_requires_the_bound_transport(self):
        binding = validate_transport_binding(
            {"schema": "puppet.transport-binding/v1", "id": "tmux"}
        )
        self.assertEqual(record_transport_id({"transport": binding}), "tmux")
        with self.assertRaisesRegex(ValidationError, "missing"):
            record_transport_id({})
        with self.assertRaisesRegex(UnsupportedError, "not implemented"):
            validate_transport_binding(
                {"schema": "puppet.transport-binding/v1", "id": "agy-print"}
            )
