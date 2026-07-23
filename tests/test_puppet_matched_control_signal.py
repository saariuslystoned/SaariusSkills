from __future__ import annotations

import inspect
import json
import os
import re
import sys
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "puppet" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import adapter_lab as puppet_adapter_lab  # noqa: E402
from puppet_lib import adapter_manifest, matched_control_signal, probe  # noqa: E402
from puppet_lib.adapter_manifest import AdapterManifest  # noqa: E402
from puppet_lib.errors import (  # noqa: E402
    ConflictError,
    IdentityError,
)
from puppet_lib.matched_control import (  # noqa: E402
    CLAUDE_MARKER_CONFORMANCE_TASK,
    MARKER_SIGNAL_RELATIVE_PATH,
    compile_claude_marker_instruction,
)
from puppet_lib.matched_control_authority import (  # noqa: E402
    attest_claude_marker_activation_join,
)
from puppet_lib.matched_control_signal import (  # noqa: E402
    MARKER_SIGNAL_OBSERVATION_EVENT_SCHEMA,
    MARKER_SIGNAL_OBSERVATION_SCHEMA_VERSION,
    prepare_claude_marker_signal,
    verify_claude_marker_signal_observation,
)
from puppet_lib.plane_activation import plan_activation  # noqa: E402
from tests.test_puppet_plane_activation import (  # noqa: E402
    _adapter_manifest,
    _descriptor,
)


MARKER_PATTERN = re.compile(rb"PUPPET_CLAUDE_MATCHED_CONTROL_MARKER_V1=[0-9a-f]{64}")


class MarkerSignalCase:
    def __init__(self, base: Path):
        self.base = Path(base)
        self.workspace = self.base / "workspace"
        self.config = self.base / "config"
        self.ephemeral = self.base / "ephemeral"
        self.transaction = self.base / "transaction"
        self.authority = self.base / "authority"
        for path in (
            self.workspace,
            self.config,
            self.ephemeral,
            self.transaction,
            self.authority,
        ):
            path.mkdir(mode=0o700)
            path.chmod(0o700)
        self.handoffs = self.workspace / "handoffs"
        self.handoffs.mkdir(mode=0o700)
        self.handoffs.chmod(0o700)
        self.manifest = _adapter_manifest()
        manifest_sha = AdapterManifest.from_dict(self.manifest).fingerprint
        self.descriptor = _descriptor(manifest_sha)
        self.compiled = compile_claude_marker_instruction(
            descriptor=self.descriptor,
            contract_identity={
                "fingerprint": "b" * 64,
                "controller": "codex",
                "target": "claude",
                "task_profile": "source-free-pass-b-v2",
            },
            workspace_identity={
                "fixture_fingerprint": "c" * 64,
                "workspace": "isolated_conformance_fixture",
            },
            run_identity={
                "session": "claude-activated",
                "run_id": "run-activated",
                "nonce": "nonce-activated-0123456789",
            },
        )
        self.plan = plan_activation(
            self.descriptor,
            instruction_manifest=self.compiled.manifest,
            adapter_manifest=self.manifest,
            effective_contract=self.compiled.rendered,
            workspace_root=self.workspace,
            ephemeral_root=self.ephemeral,
            transaction_root=self.transaction,
            config_root=self.config,
            _current_manifest=self.manifest,
        )
        with self.authority_patches():
            self.attestation = attest_claude_marker_activation_join(
                self.compiled,
                activation_plan=self.plan,
                descriptor=self.descriptor,
                adapter_manifest=self.manifest,
            )

    @property
    def marker(self) -> bytes:
        match = MARKER_PATTERN.search(self.compiled.rendered)
        if match is None:  # pragma: no cover - source compiler invariant
            raise AssertionError("compiled marker unavailable")
        return match.group(0)

    @property
    def signal_path(self) -> Path:
        return self.workspace / MARKER_SIGNAL_RELATIVE_PATH

    def authority_patches(self) -> ExitStack:
        stack = ExitStack()
        stack.enter_context(
            mock.patch(
                "puppet_lib.matched_control_authority.controller_authority_root",
                return_value=self.authority,
            )
        )
        stack.enter_context(
            mock.patch(
                "puppet_lib.matched_control_signal.controller_authority_root",
                return_value=self.authority,
            )
        )
        return stack

    def prepare(self):
        with self.authority_patches():
            return prepare_claude_marker_signal(
                self.compiled,
                activation_plan=self.plan,
                descriptor=self.descriptor,
                adapter_manifest=self.manifest,
                activation_attestation=self.attestation,
            )

    def write_signal(self, payload: bytes | None = None, *, mode: int = 0o600):
        descriptor = os.open(
            self.signal_path,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            mode,
        )
        try:
            os.fchmod(descriptor, mode)
            os.write(descriptor, self.marker if payload is None else payload)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


class ClaudeMarkerSignalTests(unittest.TestCase):
    def test_exact_signal_is_unlinked_before_hash_only_journal_and_verifies(self):
        with tempfile.TemporaryDirectory() as temporary:
            case = MarkerSignalCase(Path(temporary))
            guard = case.prepare()
            case.write_signal()
            with case.authority_patches():
                observation = guard.consume()
                row = verify_claude_marker_signal_observation(
                    observation,
                    case.compiled,
                    activation_plan=case.plan,
                    descriptor=case.descriptor,
                    adapter_manifest=case.manifest,
                    activation_attestation=case.attestation,
                )
            self.assertFalse(case.signal_path.exists())
            self.assertEqual(
                observation["schema_version"],
                MARKER_SIGNAL_OBSERVATION_SCHEMA_VERSION,
            )
            self.assertEqual(
                row["event"]["schema"], MARKER_SIGNAL_OBSERVATION_EVENT_SCHEMA
            )
            self.assertTrue(row["event"]["signal_consumed"])
            for name in (
                "delivery_authorized",
                "runtime_scan_authorized",
                "checkpoint_observed",
                "lease_bound",
                "no_bleed_evaluated",
                "no_bleed_verified",
                "qualification_authorized",
                "promotion_authorized",
            ):
                self.assertIs(row["event"][name], False)
            durable = b"".join(
                path.read_bytes()
                for path in case.authority.rglob("*")
                if path.is_file()
            )
            self.assertNotIn(case.marker, durable)
            self.assertNotIn(CLAUDE_MARKER_CONFORMANCE_TASK.encode(), durable)
            self.assertNotIn(MARKER_SIGNAL_RELATIVE_PATH.encode(), durable)
            self.assertNotIn(case.marker, repr(guard).encode())
            with self.assertRaisesRegex(IdentityError, "closed"):
                guard.consume()
            changed_request = dict(observation, request_id="alternate-request")
            with case.authority_patches():
                with self.assertRaisesRegex(IdentityError, "activation join changed"):
                    verify_claude_marker_signal_observation(
                        changed_request,
                        case.compiled,
                        activation_plan=case.plan,
                        descriptor=case.descriptor,
                        adapter_manifest=case.manifest,
                        activation_attestation=case.attestation,
                    )
            with self.assertRaisesRegex(ConflictError, "already exists for this join"):
                case.prepare()

    def test_public_surfaces_expose_no_signal_or_authority_injection_hooks(self):
        self.assertFalse(hasattr(matched_control_signal, "ClaudeMarkerSignalGuard"))
        self.assertNotIn("ClaudeMarkerSignalGuard", matched_control_signal.__all__)
        for function in (
            prepare_claude_marker_signal,
            verify_claude_marker_signal_observation,
        ):
            parameters = inspect.signature(function).parameters
            for forbidden in (
                "marker",
                "digest",
                "signal_path",
                "file_descriptor",
                "event",
                "journal",
                "rows",
                "authority_root",
            ):
                self.assertNotIn(forbidden, parameters)

    def test_preexisting_leaf_fails_without_modification(self):
        with tempfile.TemporaryDirectory() as temporary:
            case = MarkerSignalCase(Path(temporary))
            case.write_signal(b"PREEXISTING_CANARY")
            before = case.signal_path.read_bytes()
            with self.assertRaisesRegex(ConflictError, "already exists"):
                case.prepare()
            self.assertEqual(case.signal_path.read_bytes(), before)

    def test_invalid_signal_shapes_fail_closed_and_remain_unconsumed(self):
        cases = (
            ("wrong_bytes", lambda case: case.write_signal(b"x" * len(case.marker))),
            ("trailing_newline", lambda case: case.write_signal(case.marker + b"\n")),
            ("wrong_mode", lambda case: case.write_signal(mode=0o644)),
            (
                "symlink",
                lambda case: case.signal_path.symlink_to(case.base / "missing"),
            ),
            ("directory", lambda case: case.signal_path.mkdir(mode=0o700)),
            ("hardlink", self._write_hardlinked_signal),
        )
        for label, writer in cases:
            with self.subTest(label=label):
                with tempfile.TemporaryDirectory() as temporary:
                    case = MarkerSignalCase(Path(temporary))
                    guard = case.prepare()
                    writer(case)
                    with self.assertRaisesRegex(
                        IdentityError, "marker signal (leaf|file|bytes)"
                    ):
                        guard.consume()
                    self.assertTrue(
                        case.signal_path.exists() or case.signal_path.is_symlink()
                    )
                    guard.close()

    @staticmethod
    def _write_hardlinked_signal(case: MarkerSignalCase) -> None:
        case.write_signal()
        os.link(case.signal_path, case.base / "second-link")

    def test_parent_swap_and_leaf_race_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            case = MarkerSignalCase(Path(temporary))
            guard = case.prepare()
            old_parent = case.workspace / "old-handoffs"
            case.handoffs.rename(old_parent)
            case.handoffs.mkdir(mode=0o700)
            case.handoffs.chmod(0o700)
            with self.assertRaisesRegex(
                IdentityError, "(workspace identity|parent path) changed"
            ):
                guard.consume()
            guard.close()

        with tempfile.TemporaryDirectory() as temporary:
            case = MarkerSignalCase(Path(temporary))
            guard = case.prepare()
            case.write_signal()
            real_read = os.read
            replaced = False

            def replace_after_read(descriptor, count):
                nonlocal replaced
                block = real_read(descriptor, count)
                if not replaced:
                    replaced = True
                    case.signal_path.unlink()
                    case.write_signal()
                return block

            with mock.patch(
                "puppet_lib.matched_control_signal.os.read",
                side_effect=replace_after_read,
            ):
                with self.assertRaisesRegex(IdentityError, "changed during"):
                    guard.consume()
            self.assertTrue(case.signal_path.exists())
            guard.close()

        with tempfile.TemporaryDirectory() as temporary:
            case = MarkerSignalCase(Path(temporary))
            guard = case.prepare()
            case.write_signal()
            retained = case.handoffs / "retained-marker"
            real_unlink = os.unlink

            def retain_opened_inode_and_unlink_replacement(path, *, dir_fd=None):
                os.rename(
                    path,
                    retained.name,
                    src_dir_fd=dir_fd,
                    dst_dir_fd=dir_fd,
                )
                case.write_signal()
                real_unlink(path, dir_fd=dir_fd)

            with mock.patch(
                "puppet_lib.matched_control_signal.os.unlink",
                side_effect=retain_opened_inode_and_unlink_replacement,
            ):
                with self.assertRaisesRegex(IdentityError, "retained links"):
                    guard.consume()
            self.assertEqual(retained.read_bytes(), case.marker)
            self.assertFalse(case.signal_path.exists())
            self.assertFalse(
                (
                    case.authority
                    / "claude-marker-signal-observations"
                    / "events.jsonl"
                ).exists()
            )

    def test_journal_failure_happens_after_unlink_and_cannot_retry_signal(self):
        with tempfile.TemporaryDirectory() as temporary:
            case = MarkerSignalCase(Path(temporary))
            guard = case.prepare()
            case.write_signal()
            with mock.patch(
                "puppet_lib.matched_control_signal.Journal.append",
                side_effect=OSError("JOURNAL_FAILURE_CANARY"),
            ):
                with self.assertRaisesRegex(OSError, "JOURNAL_FAILURE_CANARY"):
                    guard.consume()
            self.assertFalse(case.signal_path.exists())
            with self.assertRaisesRegex(IdentityError, "closed"):
                guard.consume()
            with self.assertRaisesRegex(ConflictError, "reservation already exists"):
                case.prepare()

    def test_production_probe_handoff_and_qualification_remain_disconnected(self):
        for module in (probe, adapter_manifest, puppet_adapter_lab):
            source = inspect.getsource(module)
            self.assertNotIn("matched_control_signal", source)
        self.assertNotIn(
            MARKER_SIGNAL_RELATIVE_PATH,
            json.dumps(probe._handoff_value.__code__.co_consts, default=str),
        )


if __name__ == "__main__":
    unittest.main()
