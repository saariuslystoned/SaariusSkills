from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "puppet" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from puppet_lib.agy_print import AgyPrintController
from puppet_lib.errors import UnsupportedError, ValidationError
from puppet_lib.tmux import TmuxController
from puppet_lib.transport import (
    DEFAULT_TRANSPORT,
    bind_run_transport,
    open_run_transport,
    record_transport_id,
    transport_capability_table,
    transport_is_available,
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
        self.assertEqual(table["agy-print"]["implementation"], "implemented")
        self.assertEqual(
            table["agy-print"]["resume_proves"],
            "matching_session_and_conversation_identity",
        )
        self.assertEqual(table["cursor-acp"]["implementation"], "implemented")
        self.assertEqual(
            table["cursor-acp"]["resume_proves"],
            "matching_session_and_conversation_identity",
        )
        for name in ("herdr", "acp"):
            self.assertEqual(table[name]["implementation"], "unsupported")
            with self.assertRaisesRegex(UnsupportedError, "not implemented"):
                bind_run_transport(name)
        with self.assertRaisesRegex(ValidationError, "does not match"):
            bind_run_transport("herdr", contract_transport="tmux")
        with self.assertRaisesRegex(ValidationError, "does not match"):
            bind_run_transport("agy-print", contract_transport="tmux")
        with self.assertRaisesRegex(ValidationError, "does not match"):
            bind_run_transport("cursor-acp", contract_transport="tmux")

    def test_session_record_requires_the_bound_transport(self):
        binding = validate_transport_binding(
            {"schema": "puppet.transport-binding/v1", "id": "tmux"}
        )
        self.assertEqual(record_transport_id({"transport": binding}), "tmux")
        with self.assertRaisesRegex(ValidationError, "missing"):
            record_transport_id({})
        agy_binding = validate_transport_binding(
            {"schema": "puppet.transport-binding/v1", "id": "agy-print"}
        )
        self.assertEqual(agy_binding["id"], "agy-print")
        with self.assertRaisesRegex(UnsupportedError, "not implemented"):
            validate_transport_binding(
                {"schema": "puppet.transport-binding/v1", "id": "acp"}
            )

    def test_agy_print_binds_without_falling_back_to_tmux(self):
        binding = bind_run_transport("agy-print")
        self.assertEqual(binding["id"], "agy-print")
        with tempfile.TemporaryDirectory() as temporary:
            controller = open_run_transport(binding, Path(temporary))
            self.assertIsInstance(controller, AgyPrintController)
            self.assertNotIsInstance(controller, TmuxController)
        with mock.patch.object(TmuxController, "available", return_value=False):
            self.assertFalse(transport_is_available("tmux"))
            self.assertEqual(bind_run_transport("agy-print")["id"], "agy-print")
        with mock.patch.object(AgyPrintController, "available", return_value=False):
            self.assertFalse(transport_is_available("agy-print"))
            self.assertEqual(bind_run_transport("agy-print")["id"], "agy-print")
        with mock.patch.object(TmuxController, "__init__", side_effect=AssertionError("tmux")):
            open_run_transport(
                {"schema": "puppet.transport-binding/v1", "id": "agy-print"},
                Path(tempfile.gettempdir()),
            )
