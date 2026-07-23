from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "puppet" / "scripts"

sys.path.insert(0, str(SCRIPTS))

from puppet_lib.adapter_manifest import (  # noqa: E402
    ADAPTER_MANIFEST_SCHEMA_VERSION,
    BEHAVIOR_CAPABILITIES,
    direct_execution_bundle,
)
from puppet_lib.census import (  # noqa: E402
    DECLARED_MAPPINGS,
    adapter_implementation_fingerprint,
)
from puppet_lib.errors import IdentityError, ValidationError  # noqa: E402
from puppet_lib.handoffs import PROTOCOL_FINGERPRINT  # noqa: E402
from puppet_lib.profiles import (  # noqa: E402
    PROMPT_TRANSPORT,
    SUBMIT_SETTLE_SECONDS,
    session_profiles_for,
    startup_settle_seconds_for,
)
from puppet_lib.safety import sha256_file  # noqa: E402
from puppet_lib.subscription_onboarding import (  # noqa: E402
    ONBOARDING_SCHEMA,
    run_subscription_onboarding,
)


class SubscriptionOnboardingTests(unittest.TestCase):
    def _executable(self, root: Path) -> Path:
        executable = root / "fake-harness"
        executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        executable.chmod(0o700)
        return executable.resolve(strict=True)

    def _manifest(self, root: Path, *, target: str, executable: Path) -> Path:
        details = executable.stat()
        identity = {
            "requested_path": str(executable),
            "resolved_path": str(executable),
            "device": details.st_dev,
            "inode": details.st_ino,
            "size": details.st_size,
            "mtime_ns": details.st_mtime_ns,
            "sha256": sha256_file(executable),
            "version_sha256": "a" * 64,
            "help_sha256": "b" * 64,
        }
        declared = DECLARED_MAPPINGS[target]
        launch_flags = []
        for flag in (
            declared["permission_flags"]
            + declared["sandbox_flags"]
            + declared["project_isolation_flags"]
        ):
            if flag not in launch_flags:
                launch_flags.append(flag)
        mapping = {
            "complete": False,
            "launch_argv": [str(executable), *launch_flags],
            "permission_declared": True,
            "permission_flags": declared["permission_flags"],
            "prompt_transport": PROMPT_TRANSPORT,
            "prompt_transport_declared": True,
            "sandbox_disable_declared": bool(declared["sandbox_flags"]),
            "sandbox_flags": declared["sandbox_flags"],
            "project_isolation_declared": bool(
                declared["project_isolation_flags"]
            ),
            "project_isolation_flags": declared["project_isolation_flags"],
            "session_profiles": session_profiles_for(target),
            "session_profiles_declared": True,
            "startup_settle_seconds": startup_settle_seconds_for(target),
            "submit_settle_seconds": SUBMIT_SETTLE_SECONDS,
        }
        if "model_flag" in declared:
            mapping["model_flag"] = declared["model_flag"]
        if "effort_flag" in declared:
            mapping["effort_flag"] = declared["effort_flag"]
        value = {
            "schema_version": ADAPTER_MANIFEST_SCHEMA_VERSION,
            "target": target,
            "generated_at": "2026-07-23T17:40:00Z",
            "platform": {
                "system": "Darwin",
                "release": "test",
                "machine": "arm64",
            },
            "executable": identity,
            "execution": direct_execution_bundle(identity),
            "adapter_fingerprint": adapter_implementation_fingerprint(),
            "protocol_fingerprint": PROTOCOL_FINGERPRINT,
            "yolo_mapping": mapping,
            "capabilities": {
                name: "declared" for name in BEHAVIOR_CAPABILITIES
            },
            "doctor_only": True,
            "qualification": None,
        }
        path = root / (target + ".json")
        path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")
        return path

    def _status(self, profile_root: Path | str) -> dict:
        target = Path(profile_root).name
        states = {
            "codex": ("logged_in", "chatgpt"),
            "claude": ("logged_out", "claude.ai"),
            "grok": ("unknown", "private_grok_home"),
        }
        login_state, method = states[target]
        return {
            "login_state": login_state,
            "method": method,
            "status_exit": 0,
            "raw_output_retained": False,
        }

    def test_batch_reuses_ready_and_emits_only_needed_login_handoff(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve(strict=True)
            executable = self._executable(root)
            shelf = root / "profiles"
            shelf.mkdir(mode=0o700)
            manifests = {
                target: self._manifest(root, target=target, executable=executable)
                for target in ("agy", "claude", "codex", "cursor", "grok")
            }
            with (
                patch.dict(
                    os.environ,
                    {
                        "XAI_API_KEY": "PUPPET_ONBOARDING_SECRET_CANARY",
                        "ANTHROPIC_API_KEY": "PUPPET_ONBOARDING_SECRET_CANARY",
                        "CODEX_ACCESS_TOKEN": "PUPPET_ONBOARDING_SECRET_CANARY",
                    },
                ),
                patch(
                    "puppet_lib.subscription_onboarding.subscription_profile_status",
                    side_effect=self._status,
                ),
            ):
                result = run_subscription_onboarding(
                    profile_shelf=shelf,
                    manifest_paths=manifests,
                )

            self.assertEqual(result["schema"], ONBOARDING_SCHEMA)
            self.assertEqual(result["ready_targets"], ["codex"])
            self.assertEqual(result["enrollment_targets"], ["claude"])
            self.assertEqual(result["unknown_targets"], ["grok"])
            self.assertEqual(result["unsupported_targets"], ["agy", "cursor"])
            self.assertEqual(result["human_action_targets"], ["claude", "cursor"])
            self.assertTrue(result["human_action_required"])
            self.assertFalse(result["login_performed"])
            self.assertFalse(result["account_change_performed"])
            self.assertFalse(result["model_launched"])
            self.assertFalse(result["raw_output_retained"])

            self.assertEqual(result["results"]["codex"]["state"], "ready")
            self.assertNotIn("login_command", result["results"]["codex"])
            self.assertEqual(
                result["results"]["claude"]["state"], "enrollment_required"
            )
            self.assertIn("login_command", result["results"]["claude"])
            self.assertEqual(result["results"]["grok"]["state"], "status_unknown")
            self.assertNotIn("login_command", result["results"]["grok"])
            for target in ("agy", "cursor"):
                self.assertEqual(result["results"][target]["state"], "unsupported")
                self.assertFalse((shelf / target).exists())
            self.assertFalse(result["results"]["agy"]["human_action_required"])
            self.assertTrue(result["results"]["cursor"]["human_action_required"])
            self.assertEqual(
                result["results"]["cursor"]["next_action"],
                "human_approve_cursor_auth_isolation_probe",
            )
            for target in ("claude", "codex", "grok"):
                self.assertTrue((shelf / target / "profile.json").is_file())

            encoded = json.dumps(result, sort_keys=True)
            self.assertNotIn("PUPPET_ONBOARDING_SECRET_CANARY", encoded)
            self.assertNotIn("XAI_API_KEY", encoded)
            self.assertNotIn("ANTHROPIC_API_KEY", encoded)
            self.assertNotIn("CODEX_ACCESS_TOKEN", encoded)

    def test_status_failure_is_bounded_and_does_not_block_other_targets(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve(strict=True)
            executable = self._executable(root)
            shelf = root / "profiles"
            shelf.mkdir(mode=0o700)
            manifests = {
                target: self._manifest(root, target=target, executable=executable)
                for target in ("codex", "grok")
            }

            def status(profile_root):
                if Path(profile_root).name == "codex":
                    raise ValidationError("raw provider detail must not escape")
                return {
                    "login_state": "logged_in",
                    "method": "private_grok_home",
                    "default_model": "grok-4.5",
                    "status_exit": 0,
                    "raw_output_retained": False,
                }

            with patch(
                "puppet_lib.subscription_onboarding.subscription_profile_status",
                side_effect=status,
            ):
                result = run_subscription_onboarding(
                    profile_shelf=shelf,
                    manifest_paths=manifests,
                )

            self.assertEqual(result["ready_targets"], ["grok"])
            self.assertEqual(result["unknown_targets"], ["codex"])
            self.assertEqual(
                result["results"]["codex"]["status_error"], "validation_error"
            )
            self.assertNotIn(
                "raw provider detail",
                json.dumps(result, sort_keys=True),
            )

    def test_stale_manifest_fails_before_profile_creation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve(strict=True)
            executable = self._executable(root)
            shelf = root / "profiles"
            shelf.mkdir(mode=0o700)
            manifest = self._manifest(root, target="grok", executable=executable)
            value = json.loads(manifest.read_text(encoding="utf-8"))
            value["adapter_fingerprint"] = "d" * 64
            manifest.write_text(
                json.dumps(value, sort_keys=True) + "\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                IdentityError, "source fingerprint is stale"
            ):
                run_subscription_onboarding(
                    profile_shelf=shelf,
                    manifest_paths={"grok": manifest},
                )
            self.assertEqual(list(shelf.iterdir()), [])

    def test_shelf_must_be_real_private_and_current_user_owned(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve(strict=True)
            public = root / "public"
            public.mkdir(mode=0o755)
            with self.assertRaisesRegex(IdentityError, "mode-0700"):
                run_subscription_onboarding(
                    profile_shelf=public,
                    manifest_paths={"grok": root / "missing.json"},
                )
            private = root / "private"
            private.mkdir(mode=0o700)
            linked = root / "linked"
            linked.symlink_to(private, target_is_directory=True)
            with self.assertRaisesRegex(IdentityError, "real current-UID"):
                run_subscription_onboarding(
                    profile_shelf=linked,
                    manifest_paths={"grok": root / "missing.json"},
                )


if __name__ == "__main__":
    unittest.main()
