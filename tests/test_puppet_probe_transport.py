from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "puppet" / "scripts"
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(SCRIPTS))

from puppet_lib.adapter_manifest import AdapterManifest
from puppet_lib.errors import IdentityError, UnsupportedError, ValidationError
from puppet_lib.probe import (
    _bind_qualification_probe_transport,
    _require_exercised_qualification_transport,
    recover_probe,
)
from test_puppet_probe import (
    FakeTmux,
    controller_inputs,
    execute,
    process_identity,
)


def _refuse_tmux(root):
    raise AssertionError(
        "unimplemented qualification transport must not construct tmux"
    )


class ProbeTransportQualificationTests(unittest.TestCase):
    def test_agy_print_selection_fails_closed_before_fake_tmux(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            files = controller_inputs(root)
            fake = FakeTmux(root / "fake-tmux")
            with self.assertRaisesRegex(
                UnsupportedError, "qualification probe transport agy-print"
            ):
                execute(
                    files,
                    fake,
                    run_id="probe-agy-print-refused",
                    transport="agy-print",
                    tmux_factory=_refuse_tmux,
                )
            self.assertIsNone(fake.launch_argv)
            run_root = files["proof"] / "probes" / "probe-agy-print-refused"
            self.assertFalse((run_root / "receipt.json").exists())
            self.assertFalse(run_root.exists())

    def test_cursor_acp_and_named_unsupported_transports_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            files = controller_inputs(root)
            fake = FakeTmux(root / "fake-tmux")
            with self.assertRaisesRegex(
                UnsupportedError, "qualification probe transport cursor-acp"
            ):
                execute(
                    files,
                    fake,
                    run_id="probe-cursor-acp-refused",
                    transport="cursor-acp",
                    tmux_factory=_refuse_tmux,
                )
            with self.assertRaisesRegex(UnsupportedError, "not implemented"):
                execute(
                    files,
                    fake,
                    run_id="probe-herdr-refused",
                    transport="herdr",
                    tmux_factory=_refuse_tmux,
                )
            with self.assertRaisesRegex(ValidationError, "unsupported"):
                execute(
                    files,
                    fake,
                    run_id="probe-unknown-refused",
                    transport="not-a-transport",
                    tmux_factory=_refuse_tmux,
                )
            self.assertIsNone(fake.launch_argv)
            self.assertFalse((files["proof"] / "probes").exists())

    def test_public_tmux_receipt_stamps_only_the_exercised_transport(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            files = controller_inputs(root)
            fake = FakeTmux(root / "fake-tmux")
            result = execute(
                files,
                fake,
                run_id="probe-tmux-receipt-transport",
                transport="tmux",
            )
            self.assertEqual(result["result"], "accepted")
            self.assertIsNotNone(fake.launch_argv)
            receipt = json.loads(
                Path(result["receipt"]).read_text(encoding="utf-8")
            )
            self.assertEqual(receipt["compatibility_scope"]["transport"], "tmux")
            self.assertEqual(receipt["result"], "accepted")

    def test_default_probe_receipt_does_not_claim_agy_print(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            files = controller_inputs(root)
            fake = FakeTmux(root / "fake-tmux")
            result = execute(files, fake, run_id="probe-default-receipt-transport")
            receipt = json.loads(
                Path(result["receipt"]).read_text(encoding="utf-8")
            )
            self.assertEqual(receipt["compatibility_scope"]["transport"], "tmux")
            self.assertNotEqual(
                receipt["compatibility_scope"]["transport"], "agy-print"
            )

    def test_recovery_refuses_agy_print_before_tmux(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            files = controller_inputs(root)
            fake = FakeTmux(root / "fake-tmux")
            with patch(
                "puppet_lib.probe._halt_exact",
                side_effect=KeyboardInterrupt(),
            ):
                with self.assertRaises(KeyboardInterrupt):
                    execute(files, fake, run_id="probe-transport-recovery")
            original_launch_argv = list(fake.launch_argv)
            constructed = []

            def factory(selected):
                constructed.append(selected)
                return fake

            with self.assertRaisesRegex(
                UnsupportedError, "qualification probe transport agy-print"
            ):
                recover_probe(
                    target="codex",
                    proof_root=files["proof"],
                    manifest_path=files["manifest"],
                    mapping_path=files["mapping"],
                    authorization_path=files["authorization"],
                    controller="tester",
                    goal_repo=files["goal_repo"],
                    expected_campaign_id=files["campaign_id"],
                    expected_goal=files["expected_goal"],
                    run_id="probe-transport-recovery",
                    halt_timeout=0.1,
                    transport="agy-print",
                    _tmux_factory=factory,
                    _process_birth_fn=lambda pid: process_identity(fake),
                    _process_alive_fn=lambda identity: fake.alive,
                    _exact_sigint_fn=fake.exact_sigint,
                    _server_process_birth_fn=lambda pid: fake.server_process,
                    _active_processes_fn=lambda selected: [],
                    _adapter_fingerprint_fn=lambda: files["raw"][
                        "adapter_fingerprint"
                    ],
                    _census_target_fn=lambda selected, fingerprint: (
                        AdapterManifest.from_dict(files["raw"])
                    ),
                    _sleep_fn=lambda interval: None,
                    _authority_root=files["authority"],
                )
            self.assertEqual(constructed, [])
            self.assertEqual(fake.launch_argv, original_launch_argv)
            self.assertFalse(
                (
                    files["proof"]
                    / "probes"
                    / "probe-transport-recovery"
                    / "recovery.json"
                ).is_file()
            )

    def test_recovery_preserves_tmux_reconciliation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            files = controller_inputs(root)
            fake = FakeTmux(root / "fake-tmux")
            with patch(
                "puppet_lib.probe._halt_exact",
                side_effect=KeyboardInterrupt(),
            ):
                with self.assertRaises(KeyboardInterrupt):
                    execute(
                        files,
                        fake,
                        run_id="probe-tmux-recovery",
                        transport="tmux",
                    )
            original_launch_argv = list(fake.launch_argv)
            recovered = recover_probe(
                target="codex",
                proof_root=files["proof"],
                manifest_path=files["manifest"],
                mapping_path=files["mapping"],
                authorization_path=files["authorization"],
                controller="tester",
                goal_repo=files["goal_repo"],
                expected_campaign_id=files["campaign_id"],
                expected_goal=files["expected_goal"],
                run_id="probe-tmux-recovery",
                halt_timeout=0.1,
                transport="tmux",
                _tmux_factory=lambda selected: fake,
                _process_birth_fn=lambda pid: process_identity(fake),
                _process_alive_fn=lambda identity: fake.alive,
                _exact_sigint_fn=fake.exact_sigint,
                _server_process_birth_fn=lambda pid: fake.server_process,
                _active_processes_fn=lambda selected: [],
                _adapter_fingerprint_fn=lambda: files["raw"]["adapter_fingerprint"],
                _census_target_fn=lambda selected, fingerprint: (
                    AdapterManifest.from_dict(files["raw"])
                ),
                _sleep_fn=lambda interval: None,
                _authority_root=files["authority"],
            )
            self.assertTrue(recovered["recovered"])
            self.assertEqual(recovered["result"], "interrupted_probe_reconciled")
            self.assertEqual(fake.launch_argv, original_launch_argv)
            self.assertFalse(fake.alive)

    def test_bind_helper_accepts_only_matching_probe_transport(self):
        self.assertEqual(_bind_qualification_probe_transport(None), "tmux")
        self.assertEqual(_bind_qualification_probe_transport("tmux"), "tmux")
        with self.assertRaisesRegex(UnsupportedError, "agy-print"):
            _bind_qualification_probe_transport("agy-print")
        with self.assertRaisesRegex(UnsupportedError, "cursor-acp"):
            _bind_qualification_probe_transport("cursor-acp")
        with self.assertRaisesRegex(UnsupportedError, "not implemented"):
            _bind_qualification_probe_transport("acp")

    def test_receipt_helper_refuses_unexercised_or_mismatched_transport(self):
        self.assertEqual(
            _require_exercised_qualification_transport("tmux", "tmux"), "tmux"
        )
        with self.assertRaisesRegex(IdentityError, "was not exercised"):
            _require_exercised_qualification_transport("tmux", None)
        with self.assertRaisesRegex(IdentityError, "does not match"):
            _require_exercised_qualification_transport("agy-print", "tmux")


if __name__ == "__main__":
    unittest.main()
