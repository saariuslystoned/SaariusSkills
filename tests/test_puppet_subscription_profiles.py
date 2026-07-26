from __future__ import annotations

import json
import os
import pwd
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
    CLAUDE_LEGACY_PROFILE_MIGRATION_BLOCKER,
    CLAUDE_NATIVE_KEYRING_AUTH_ROUTE,
    LAUNCH_BINDING_SCHEMA,
    MAX_STATUS_OUTPUT_BYTES,
    PROFILE_HUMAN_LOGIN_POLICY,
    PROFILE_OPERATOR_GLOBAL_ADOPTION,
    PROFILE_REUSE_SCOPE,
    PROFILE_SCHEMA,
    PROFILE_STATUS_POLICY,
    STATUS_SCHEMA,
    SYNTHETIC_PROFILE_HOME_AUTH_ROUTE,
    build_subscription_launch_binding,
    execute_subscription_profile_login,
    initialize_subscription_profile,
    subscription_profile_launch_context,
    subscription_binding_environment,
    subscription_profile_status,
    validate_subscription_launch_binding,
)


class SubscriptionProfileTests(unittest.TestCase):
    def _real_user_home(self) -> Path:
        return Path(pwd.getpwuid(os.getuid()).pw_dir).resolve(strict=True)

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
            self.assertEqual(result["reuse_scope"], PROFILE_REUSE_SCOPE)
            self.assertEqual(result["status_policy"], PROFILE_STATUS_POLICY)
            self.assertEqual(
                result["human_login_policy"], PROFILE_HUMAN_LOGIN_POLICY
            )
            self.assertEqual(
                result["operator_global_adoption"],
                PROFILE_OPERATOR_GLOBAL_ADOPTION,
            )
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

    def test_init_is_idempotent_and_refreshes_launcher_without_reenrollment(self):
        with tempfile.TemporaryDirectory() as temporary:
            executable = self._executable(temporary)
            other = Path(temporary) / "other"
            other.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            other.chmod(0o700)
            profile = Path(temporary) / "profile"
            first = initialize_subscription_profile(
                target="codex", profile_root=profile, executable_path=executable
            )
            opaque_profile_state = profile / "home" / "opaque-state"
            opaque_profile_state.write_text("preserve\n", encoding="utf-8")
            opaque_state_identity = opaque_profile_state.stat()
            second = initialize_subscription_profile(
                target="codex", profile_root=profile, executable_path=executable
            )
            self.assertEqual(first, second)
            with self.assertRaises(ConflictError):
                initialize_subscription_profile(
                    target="claude", profile_root=profile, executable_path=executable
                )
            refreshed = initialize_subscription_profile(
                target="codex", profile_root=profile, executable_path=other
            )
            self.assertEqual(refreshed["root"], first["root"])
            self.assertEqual(refreshed["directories"], first["directories"])
            self.assertEqual(
                refreshed["executable"]["path"], str(other.resolve(strict=True))
            )
            self.assertNotEqual(
                refreshed["manifest_sha256"], first["manifest_sha256"]
            )
            self.assertEqual(
                opaque_profile_state.read_text(encoding="utf-8"), "preserve\n"
            )
            self.assertEqual(
                opaque_profile_state.stat().st_ino, opaque_state_identity.st_ino
            )
            self.assertEqual(
                initialize_subscription_profile(
                    target="codex", profile_root=profile, executable_path=other
                ),
                refreshed,
            )
            with self.assertRaisesRegex(
                IdentityError, "does not match adapter"
            ):
                subscription_profile_launch_context(
                    profile_root=profile,
                    expected_target="codex",
                    expected_executable_path=executable,
                )
            context = subscription_profile_launch_context(
                profile_root=profile,
                expected_target="codex",
                expected_executable_path=other,
            )
            self.assertEqual(context.profile_root, profile.resolve(strict=True))

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
            self.assertEqual(result["reuse_scope"], PROFILE_REUSE_SCOPE)
            self.assertEqual(result["status_policy"], PROFILE_STATUS_POLICY)
            self.assertEqual(
                result["human_login_policy"], PROFILE_HUMAN_LOGIN_POLICY
            )
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

    def test_launch_context_separates_login_only_values_and_binds_adapter(self):
        with tempfile.TemporaryDirectory() as temporary:
            executable = self._executable(temporary)
            other = Path(temporary) / "other harness"
            other.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            other.chmod(0o700)
            profile = Path(temporary) / "profile"
            initialize_subscription_profile(
                target="cursor", profile_root=profile, executable_path=executable
            )
            context = subscription_profile_launch_context(
                profile_root=profile,
                expected_target="cursor",
                expected_executable_path=executable,
            )
            self.assertEqual(context.public_binding["schema"], LAUNCH_BINDING_SCHEMA)
            self.assertEqual(
                set(context.source_environment),
                {"HOME", "TMPDIR", "PATH", "LANG", "LC_ALL"},
            )
            self.assertEqual(context.bindings["AGENT_CLI_CREDENTIAL_STORE"], "file")
            self.assertIn("CURSOR_CONFIG_DIR", context.bindings)
            self.assertIn("CURSOR_DATA_DIR", context.bindings)
            self.assertNotIn("NO_OPEN_BROWSER", context.bindings)
            self.assertEqual(
                context.public_binding["login_only_env_names"],
                ["NO_OPEN_BROWSER"],
            )
            binding = build_subscription_launch_binding(
                context,
                {
                    "schema": STATUS_SCHEMA,
                    "target": "cursor",
                    "profile_root": str(context.profile_root),
                    "auth_route": SYNTHETIC_PROFILE_HOME_AUTH_ROUTE,
                    "login_state": "logged_in",
                    "method": "private_file_store",
                    "status_exit": 0,
                    "raw_output_retained": False,
                    "login_performed": False,
                    "model_launched": False,
                },
            )
            validated = validate_subscription_launch_binding(
                binding, expected_target="cursor"
            )
            source, launch_bindings, lane_root = subscription_binding_environment(
                validated, expected_target="cursor"
            )
            self.assertEqual(source["HOME"], str(context.profile_root / "home"))
            self.assertEqual(launch_bindings["AGENT_CLI_CREDENTIAL_STORE"], "file")
            self.assertNotIn("NO_OPEN_BROWSER", launch_bindings)
            self.assertEqual(lane_root, context.profile_root)
            tampered = json.loads(json.dumps(binding))
            tampered["status"]["login_state"] = "logged_out"
            with self.assertRaisesRegex(IdentityError, "not authenticated"):
                validate_subscription_launch_binding(tampered)
            with self.assertRaisesRegex(IdentityError, "target does not match"):
                subscription_profile_launch_context(
                    profile_root=profile,
                    expected_target="codex",
                    expected_executable_path=executable,
                )
            with self.assertRaisesRegex(IdentityError, "does not match adapter"):
                subscription_profile_launch_context(
                    profile_root=profile,
                    expected_target="cursor",
                    expected_executable_path=other,
                )

    def test_claude_init_records_native_keyring_route_and_real_home(self):
        with tempfile.TemporaryDirectory() as temporary:
            executable = self._executable(temporary)
            profile = Path(temporary) / "profile"
            result = initialize_subscription_profile(
                target="claude",
                profile_root=profile,
                executable_path=executable,
            )
            real_home = self._real_user_home()
            self.assertEqual(result["auth_route"], CLAUDE_NATIVE_KEYRING_AUTH_ROUTE)
            self.assertEqual(result["real_home"]["path"], str(real_home))
            self.assertEqual(result["real_home"]["uid"], os.getuid())
            self.assertEqual(result["bindings"]["HOME"], str(real_home))
            self.assertNotEqual(
                result["bindings"]["HOME"], result["directories"]["home"]["path"]
            )
            self.assertEqual(
                result["bindings"]["CLAUDE_CONFIG_DIR"],
                result["directories"]["config"]["path"],
            )
            self.assertEqual(result["bindings"]["CLAUDE_CODE_DISABLE_AUTO_MEMORY"], "1")
            self.assertEqual(set(result["bindings"]), {
                "HOME",
                "TMPDIR",
                "PATH",
                "LANG",
                "LC_ALL",
                "CLAUDE_CONFIG_DIR",
                "CLAUDE_CODE_DISABLE_AUTO_MEMORY",
            })

    def test_codex_keeps_synthetic_home_auth_route(self):
        with tempfile.TemporaryDirectory() as temporary:
            executable = self._executable(temporary)
            profile = Path(temporary) / "profile"
            result = initialize_subscription_profile(
                target="codex",
                profile_root=profile,
                executable_path=executable,
            )
            synthetic_home = str((profile / "home").resolve(strict=True))
            self.assertEqual(result["auth_route"], SYNTHETIC_PROFILE_HOME_AUTH_ROUTE)
            self.assertEqual(result["bindings"]["HOME"], synthetic_home)
            self.assertEqual(result["real_home"]["path"], synthetic_home)

    def test_claude_status_discards_raw_output_and_classifies_route(self):
        with tempfile.TemporaryDirectory() as temporary:
            executable = self._executable(temporary)
            profile = Path(temporary) / "profile"
            initialize_subscription_profile(
                target="claude",
                profile_root=profile,
                executable_path=executable,
            )
            raw = json.dumps(
                {
                    "loggedIn": True,
                    "authMethod": "claude.ai",
                    "apiProvider": "firstParty",
                }
            ).encode()
            completed = subprocess.CompletedProcess([], 0, stdout=raw, stderr=None)
            with patch(
                "puppet_lib.subscription_profiles._bounded_status_run",
                return_value=completed,
            ):
                result = subscription_profile_status(profile_root=profile)
            self.assertEqual(result["auth_route"], CLAUDE_NATIVE_KEYRING_AUTH_ROUTE)
            self.assertEqual(result["login_state"], "logged_in")
            self.assertEqual(result["method"], "claude.ai")
            self.assertEqual(result["provider"], "firstParty")
            self.assertFalse(result["raw_output_retained"])
            self.assertNotIn("accountId", result)

    def test_legacy_claude_synthetic_manifest_fails_closed_until_refresh(self):
        with tempfile.TemporaryDirectory() as temporary:
            executable = self._executable(temporary)
            profile = Path(temporary) / "profile"
            initialize_subscription_profile(
                target="claude",
                profile_root=profile,
                executable_path=executable,
            )
            manifest_path = profile / "profile.json"
            legacy = json.loads(manifest_path.read_text(encoding="utf-8"))
            legacy.pop("auth_route")
            legacy.pop("real_home")
            legacy["bindings"]["HOME"] = legacy["directories"]["home"]["path"]
            legacy["bindings"]["CLAUDE_CODE_DISABLE_AUTO_MEMORY"] = "true"
            manifest_path.write_text(json.dumps(legacy, sort_keys=True) + "\n", encoding="utf-8")
            with self.assertRaises(UnsupportedError) as raised:
                subscription_profile_status(profile_root=profile)
            self.assertEqual(str(raised.exception), CLAUDE_LEGACY_PROFILE_MIGRATION_BLOCKER)
            refreshed = initialize_subscription_profile(
                target="claude",
                profile_root=profile,
                executable_path=executable,
            )
            self.assertEqual(refreshed["auth_route"], CLAUDE_NATIVE_KEYRING_AUTH_ROUTE)
            self.assertEqual(
                refreshed["bindings"]["HOME"],
                refreshed["real_home"]["path"],
            )

    def test_claude_launch_binding_reconstructs_closed_native_keyring_environment(self):
        with tempfile.TemporaryDirectory() as temporary:
            executable = self._executable(temporary)
            profile = Path(temporary) / "profile"
            initialize_subscription_profile(
                target="claude",
                profile_root=profile,
                executable_path=executable,
            )
            context = subscription_profile_launch_context(
                profile_root=profile,
                expected_target="claude",
                expected_executable_path=executable,
            )
            real_home = self._real_user_home()
            self.assertEqual(context.source_environment["HOME"], str(real_home))
            self.assertEqual(context.public_binding["auth_route"], CLAUDE_NATIVE_KEYRING_AUTH_ROUTE)
            binding = build_subscription_launch_binding(
                context,
                {
                    "schema": STATUS_SCHEMA,
                    "target": "claude",
                    "profile_root": str(context.profile_root),
                    "auth_route": CLAUDE_NATIVE_KEYRING_AUTH_ROUTE,
                    "login_state": "logged_in",
                    "method": "claude.ai",
                    "provider": "firstParty",
                    "status_exit": 0,
                    "raw_output_retained": False,
                    "login_performed": False,
                    "model_launched": False,
                },
            )
            validated = validate_subscription_launch_binding(
                binding, expected_target="claude"
            )
            source, launch_bindings, lane_root = subscription_binding_environment(
                validated, expected_target="claude"
            )
            self.assertEqual(source["HOME"], str(real_home))
            self.assertEqual(launch_bindings["CLAUDE_CODE_DISABLE_AUTO_MEMORY"], "1")
            self.assertEqual(lane_root, context.profile_root)

    def test_claude_real_home_drift_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            executable = self._executable(temporary)
            profile = Path(temporary) / "profile"
            initialize_subscription_profile(
                target="claude",
                profile_root=profile,
                executable_path=executable,
            )
            manifest_path = profile / "profile.json"
            tampered = json.loads(manifest_path.read_text(encoding="utf-8"))
            tampered["real_home"] = dict(tampered["directories"]["home"])
            tampered["bindings"]["HOME"] = tampered["real_home"]["path"]
            manifest_path.write_text(
                json.dumps(tampered, sort_keys=True) + "\n", encoding="utf-8"
            )
            with self.assertRaises(IdentityError):
                subscription_profile_status(profile_root=profile)


if __name__ == "__main__":
    unittest.main()
