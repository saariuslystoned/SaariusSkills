from __future__ import annotations

import json
import os
import shlex
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "puppet" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from puppet_lib.errors import ConflictError, IdentityError, UnsupportedError  # noqa: E402
from puppet_lib.subscription_profiles import (  # noqa: E402
    MAX_STATUS_OUTPUT_BYTES,
    PROFILE_SCHEMA,
    execute_subscription_profile_login,
    initialize_subscription_profile,
    subscription_profile_status,
)


class SubscriptionProfileTests(unittest.TestCase):
    def _executable(self, temporary: str) -> Path:
        path = Path(temporary) / "fake harness"
        path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        path.chmod(0o700)
        return path

    def test_init_creates_private_profile_and_human_only_login_handoff(self):
        with tempfile.TemporaryDirectory() as temporary:
            executable = self._executable(temporary)
            profile = Path(temporary) / "profile"
            result = initialize_subscription_profile(
                target="cursor",
                profile_root=profile,
                executable_path=executable,
            )
            self.assertEqual(result["schema"], PROFILE_SCHEMA)
            self.assertEqual(result["target"], "cursor")
            self.assertFalse(result["login_performed"])
            self.assertFalse(result["account_change_authorized"])
            self.assertEqual(result["bindings"]["AGENT_CLI_CREDENTIAL_STORE"], "file")
            self.assertEqual(result["bindings"]["NO_OPEN_BROWSER"], "1")
            self.assertIn("profile_login.py", result["login_command"])
            self.assertIn("/usr/bin/env -i", result["login_command"])
            self.assertIn(" -E -s -S ", result["login_command"])
            self.assertNotIn("token", result["login_command"].lower())
            self.assertEqual(stat.S_IMODE(profile.stat().st_mode), 0o700)
            self.assertEqual(
                stat.S_IMODE((profile / "profile.json").stat().st_mode), 0o600
            )
            for name in ("home", "config", "data", "tmp"):
                self.assertEqual(stat.S_IMODE((profile / name).stat().st_mode), 0o700)

    def test_init_is_idempotent_but_rejects_target_or_executable_drift(self):
        with tempfile.TemporaryDirectory() as temporary:
            executable = self._executable(temporary)
            other = Path(temporary) / "other"
            other.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            other.chmod(0o700)
            profile = Path(temporary) / "profile"
            first = initialize_subscription_profile(
                target="codex", profile_root=profile, executable_path=executable
            )
            second = initialize_subscription_profile(
                target="codex", profile_root=profile, executable_path=executable
            )
            self.assertEqual(first, second)
            with self.assertRaises(ConflictError):
                initialize_subscription_profile(
                    target="claude", profile_root=profile, executable_path=executable
                )
            with self.assertRaises(IdentityError):
                initialize_subscription_profile(
                    target="codex", profile_root=profile, executable_path=other
                )

    def test_init_rejects_unowned_root_content_and_agy(self):
        with tempfile.TemporaryDirectory() as temporary:
            executable = self._executable(temporary)
            profile = Path(temporary) / "profile"
            profile.mkdir(mode=0o700)
            (profile / "unowned").write_text("x", encoding="utf-8")
            with self.assertRaises(ConflictError):
                initialize_subscription_profile(
                    target="codex", profile_root=profile, executable_path=executable
                )
            self.assertFalse((profile / ".profile-init.lock").exists())
            with self.assertRaises(UnsupportedError):
                initialize_subscription_profile(
                    target="agy",
                    profile_root=Path(temporary) / "agy",
                    executable_path=executable,
                )

    def test_preexisting_empty_or_malformed_root_is_not_mutated(self):
        with tempfile.TemporaryDirectory() as temporary:
            executable = self._executable(temporary)
            empty = Path(temporary) / "empty"
            empty.mkdir(mode=0o700)
            with self.assertRaises(ConflictError):
                initialize_subscription_profile(
                    target="codex", profile_root=empty, executable_path=executable
                )
            self.assertEqual(list(empty.iterdir()), [])

            malformed = Path(temporary) / "malformed"
            malformed.mkdir(mode=0o700)
            (malformed / "profile.json").write_text("{}\n", encoding="utf-8")
            with self.assertRaises(Exception):
                initialize_subscription_profile(
                    target="codex", profile_root=malformed, executable_path=executable
                )
            self.assertEqual(
                [item.name for item in malformed.iterdir()], ["profile.json"]
            )

    def test_root_replacement_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            executable = self._executable(temporary)
            profile = Path(temporary) / "profile"
            initialize_subscription_profile(
                target="codex", profile_root=profile, executable_path=executable
            )
            original = Path(temporary) / "original"
            profile.rename(original)
            profile.mkdir(mode=0o700)
            for child in list(original.iterdir()):
                child.rename(profile / child.name)
            with self.assertRaises(IdentityError):
                initialize_subscription_profile(
                    target="codex", profile_root=profile, executable_path=executable
                )

    def test_delayed_login_handoff_revalidates_helper_before_exec(self):
        with tempfile.TemporaryDirectory() as temporary:
            executable = self._executable(temporary)
            helper = Path(temporary) / "helper.py"
            helper.write_text(
                "import os, sys\n"
                "sys.exit(91 if os.environ.get('PUPPET_SECRET_CANARY') else 0)\n",
                encoding="utf-8",
            )
            profile = Path(temporary) / "profile"
            initialized = initialize_subscription_profile(
                target="codex",
                profile_root=profile,
                executable_path=executable,
                helper_path=helper,
            )
            canary = subprocess.run(
                shlex.split(initialized["login_command"]),
                env={
                    "PUPPET_SECRET_CANARY": "must-not-cross",
                    "PYTHONPATH": "/untrusted/python/path",
                    "PYTHONHOME": "/untrusted/python/home",
                },
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(canary.returncode, 0, canary.stderr.decode())
            helper.write_text("# drifted helper\n", encoding="utf-8")
            with self.assertRaises(IdentityError):
                execute_subscription_profile_login(
                    profile_root=profile,
                    helper_path=helper,
                    interpreter_path=sys.executable,
                    _execve=lambda *_args: self.fail("login was executed"),
                )

    def test_status_discards_raw_cursor_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            executable = self._executable(temporary)
            profile = Path(temporary) / "profile"
            initialize_subscription_profile(
                target="cursor", profile_root=profile, executable_path=executable
            )
            raw = json.dumps(
                {
                    "status": "unauthenticated",
                    "isAuthenticated": False,
                    "hasAccessToken": False,
                    "hasRefreshToken": False,
                    "message": "Not logged in",
                }
            ).encode()
            completed = subprocess.CompletedProcess([], 0, stdout=raw, stderr=None)
            with patch(
                "puppet_lib.subscription_profiles._bounded_status_run",
                return_value=completed,
            ):
                result = subscription_profile_status(profile_root=profile)
            self.assertEqual(result["login_state"], "logged_out")
            self.assertEqual(result["method"], "private_file_store")
            self.assertFalse(result["raw_output_retained"])
            self.assertNotIn("message", result)
            self.assertNotIn("hasAccessToken", result)

    def test_nonzero_claimed_login_is_unknown_and_output_is_memory_bounded(self):
        with tempfile.TemporaryDirectory() as temporary:
            executable = self._executable(temporary)
            profile = Path(temporary) / "profile"
            initialize_subscription_profile(
                target="cursor", profile_root=profile, executable_path=executable
            )
            raw = json.dumps(
                {"status": "authenticated", "isAuthenticated": True}
            ).encode()
            completed = subprocess.CompletedProcess([], 1, stdout=raw, stderr=None)
            with patch(
                "puppet_lib.subscription_profiles._bounded_status_run",
                return_value=completed,
            ):
                result = subscription_profile_status(profile_root=profile)
            self.assertEqual(result["login_state"], "unknown")

            noisy = Path(temporary) / "noisy harness"
            noisy.write_text(
                f"#!/bin/sh\nprintf '%*s' {MAX_STATUS_OUTPUT_BYTES + 2} x\n",
                encoding="utf-8",
            )
            noisy.chmod(0o700)
            noisy_profile = Path(temporary) / "noisy-profile"
            initialize_subscription_profile(
                target="cursor", profile_root=noisy_profile, executable_path=noisy
            )
            with self.assertRaisesRegex(Exception, "exceeds the cap"):
                subscription_profile_status(profile_root=noisy_profile)

    def test_status_fails_closed_on_profile_identity_drift(self):
        with tempfile.TemporaryDirectory() as temporary:
            executable = self._executable(temporary)
            profile = Path(temporary) / "profile"
            initialize_subscription_profile(
                target="grok", profile_root=profile, executable_path=executable
            )
            os.chmod(profile / "config", 0o755)
            with self.assertRaisesRegex(Exception, "mode-0700"):
                subscription_profile_status(profile_root=profile)


if __name__ == "__main__":
    unittest.main()
