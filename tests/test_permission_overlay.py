"""Focused offline CI-portable unit tests for permission overlay verification."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

VERIFIER_PATH = Path(__file__).resolve().parents[1] / "proof/cursor-model-selection/20260930/compare-installed-source.py"
PLAN_PATH = Path(__file__).resolve().parents[1] / "proof/cursor-model-selection/20260930/install-reload-plan.md"


def load_verifier_module(path: Path | None = None):
    p = path or VERIFIER_PATH
    spec = importlib.util.spec_from_file_location("compare_installed_source", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def extract_inline_runner_script() -> str:
    text = PLAN_PATH.read_text(encoding="utf-8")
    m = re.search(r"python3\s+-\s+<<'EOF'\n(.*?)\n\s*EOF", text, re.DOTALL)
    if not m:
        raise ValueError("Could not extract inline runner script from install-reload-plan.md")
    return textwrap.dedent(m.group(1))


def extract_step3_bash_block() -> str:
    text = PLAN_PATH.read_text(encoding="utf-8")
    m = re.search(r"3\.\s+\*\*Verify Maintained Source BEFORE Plugin Refresh\*\*.*?[ \t]*```bash\n(.*?)\n[ \t]*```", text, re.DOTALL)
    if not m:
        raise ValueError("Could not extract Step 3 bash block from install-reload-plan.md")
    return textwrap.dedent(m.group(1))


class PermissionOverlayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.verifier = load_verifier_module()
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp_dir.name).resolve()

        # Set up a temporary git worktree
        cls.worktree = cls.root / "worktree"
        cls.worktree.mkdir()
        cls._git("init", "-b", cls.verifier.BRANCH)
        cls._git("config", "user.name", "Test Committer")
        cls._git("config", "user.email", "test@example.com")

        # Base commit
        dummy = cls.worktree / "README.md"
        dummy.write_text("base\n", encoding="utf-8")
        cls._git("add", "README.md")
        cls._git("commit", "-m", "base commit")
        cls.base_commit = cls._git("rev-parse", "HEAD").stdout.strip()

        # Place verifier script fixture inside test worktree with BASE adjusted solely in this fixture
        script_dest = cls.worktree / "proof" / "cursor-model-selection" / "20260930"
        script_dest.mkdir(parents=True, exist_ok=True)
        cls.fixture_script = script_dest / "compare-installed-source.py"
        verifier_content = VERIFIER_PATH.read_text(encoding="utf-8")
        fixture_content = verifier_content.replace(
            'BASE = "cc4070ebd7861f07ca3e24f7744d779fb13a472f"',
            f'BASE = "{cls.base_commit}"',
        )
        cls.fixture_script.write_text(fixture_content, encoding="utf-8")

        # Head commit adding plugin files
        cls.mcp_clean = {
            "mcpServers": {
                "cursor-acp": {
                    "command": "node",
                    "args": ["bridge/acp-runtime/launcher.mjs", "cursor-acp"],
                    "cwd": ".",
                    "env": {
                        "CURSOR_AGENT_EXECUTABLE": "/custom/bin/cursor-agent"
                    }
                },
                "antigravity-acp": {
                    "command": "node",
                    "args": ["bridge/acp-runtime/launcher.mjs", "antigravity-acp"],
                    "cwd": "."
                },
                "grok-acp": {
                    "command": "node",
                    "args": ["bridge/acp-runtime/launcher.mjs", "grok-acp"],
                    "cwd": "."
                }
            }
        }
        (cls.worktree / ".mcp.json").write_text(json.dumps(cls.mcp_clean, indent=2) + "\n", encoding="utf-8")

        bridge_dir = cls.worktree / "bridge" / "acp-runtime"
        bridge_dir.mkdir(parents=True)
        (bridge_dir / "launcher.mjs").write_text("// canonical bridge launcher\n", encoding="utf-8")

        cls._git("add", ".mcp.json", "bridge")
        cls._git("commit", "-m", "plugin head commit")
        cls.head_commit = cls._git("rev-parse", "HEAD").stdout.strip()

        # Approved policy file
        cls.policy_data = {
            "authorization": "Bobby explicitly requests persistent approve-all on personal computer",
            "lanes": [
                "cursor-acp",
                "antigravity-acp",
                "grok-acp"
            ],
            "mode": "approve-all"
        }
        policy_bytes = json.dumps(cls.policy_data, indent=2).encode("utf-8")
        cls.policy_file = cls.root / "approved-policy.json"
        cls.policy_file.write_bytes(policy_bytes)
        cls.policy_sha256 = hashlib.sha256(policy_bytes).hexdigest()

    @classmethod
    def tearDownClass(cls):
        cls.temp_dir.cleanup()

    @classmethod
    def _git(cls, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git", "-C", str(cls.worktree), *args],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

    def setUp(self):
        # Patch BASE in imported module to isolated test base for in-process calls
        self.verifier.BASE = self.base_commit
        self.installed_dir = self.root / f"installed-{self._testMethodName}"
        self.installed_dir.mkdir(parents=True, exist_ok=True)

        # Populate installed with clean files by default
        (self.installed_dir / ".mcp.json").write_text(json.dumps(self.mcp_clean, indent=2) + "\n", encoding="utf-8")
        inst_bridge = self.installed_dir / "bridge" / "acp-runtime"
        inst_bridge.mkdir(parents=True, exist_ok=True)
        (inst_bridge / "launcher.mjs").write_text("// canonical bridge launcher\n", encoding="utf-8")

    def _apply_approved_overlay(self) -> Path:
        mcp_overlay = copy.deepcopy(self.mcp_clean)
        for lane in ("cursor-acp", "antigravity-acp", "grok-acp"):
            mcp_overlay["mcpServers"][lane].setdefault("env", {})["SAARIUS_ACP_PERMISSION_MODE"] = "approve-all"
        p = self.installed_dir / ".mcp.json"
        p.write_text(json.dumps(mcp_overlay, indent=2) + "\n", encoding="utf-8")
        return p

    def test_production_source_base_literal_unaffected_by_env(self):
        """Production BASE literal must remain cc4070e and cannot be overridden by environment variables."""
        source_text = VERIFIER_PATH.read_text(encoding="utf-8")
        self.assertIn('BASE = "cc4070ebd7861f07ca3e24f7744d779fb13a472f"', source_text)
        self.assertNotIn("SAARIUS_VERIFIER_BASE", source_text)

        # Loading module with SAARIUS_VERIFIER_BASE set has no effect
        old_env = os.environ.get("SAARIUS_VERIFIER_BASE")
        try:
            os.environ["SAARIUS_VERIFIER_BASE"] = "deadbeef" * 5
            fresh_mod = load_verifier_module()
            self.assertEqual(fresh_mod.BASE, "cc4070ebd7861f07ca3e24f7744d779fb13a472f")
            self.assertEqual(fresh_mod.BRANCH, "codex/cursor-luna-model-selection-20260930")
        finally:
            if old_env is None:
                os.environ.pop("SAARIUS_VERIFIER_BASE", None)
            else:
                os.environ["SAARIUS_VERIFIER_BASE"] = old_env

    def test_clean_fixture_passes_without_policy(self):
        compared = self.verifier.verify(
            worktree=self.worktree,
            commit=self.head_commit,
            installed=self.installed_dir,
        )
        self.assertEqual(compared, 2)

    def test_approved_three_lane_overlay_passes_with_policy(self):
        self._apply_approved_overlay()
        compared = self.verifier.verify(
            worktree=self.worktree,
            commit=self.head_commit,
            installed=self.installed_dir,
            approved_policy=self.policy_file,
            approved_policy_sha256=self.policy_sha256,
        )
        self.assertEqual(compared, 2)

    def test_overlay_without_policy_fails(self):
        self._apply_approved_overlay()
        with self.assertRaises(SystemExit) as cm:
            self.verifier.verify(
                worktree=self.worktree,
                commit=self.head_commit,
                installed=self.installed_dir,
            )
        self.assertEqual(cm.exception.code, 1)

    def test_overlay_with_wrong_policy_digest_fails(self):
        self._apply_approved_overlay()
        wrong_sha = "0" * 64
        with self.assertRaises(SystemExit) as cm:
            self.verifier.verify(
                worktree=self.worktree,
                commit=self.head_commit,
                installed=self.installed_dir,
                approved_policy=self.policy_file,
                approved_policy_sha256=wrong_sha,
            )
        self.assertEqual(cm.exception.code, 1)

    def test_overlay_with_missing_policy_file_fails(self):
        self._apply_approved_overlay()
        missing_file = self.root / "nonexistent-policy.json"
        with self.assertRaises(SystemExit) as cm:
            self.verifier.verify(
                worktree=self.worktree,
                commit=self.head_commit,
                installed=self.installed_dir,
                approved_policy=missing_file,
                approved_policy_sha256=self.policy_sha256,
            )
        self.assertEqual(cm.exception.code, 1)

    def test_policy_without_digest_or_digest_without_policy_fails(self):
        self._apply_approved_overlay()
        with self.assertRaises(SystemExit) as cm:
            self.verifier.verify(
                worktree=self.worktree,
                commit=self.head_commit,
                installed=self.installed_dir,
                approved_policy=self.policy_file,
                approved_policy_sha256=None,
            )
        self.assertEqual(cm.exception.code, 1)

        with self.assertRaises(SystemExit) as cm:
            self.verifier.verify(
                worktree=self.worktree,
                commit=self.head_commit,
                installed=self.installed_dir,
                approved_policy=None,
                approved_policy_sha256=self.policy_sha256,
            )
        self.assertEqual(cm.exception.code, 1)

    def test_policy_missing_or_empty_authorization_fails(self):
        self._apply_approved_overlay()
        bad_policy = copy.deepcopy(self.policy_data)
        bad_policy["authorization"] = ""
        bad_bytes = json.dumps(bad_policy).encode("utf-8")
        bad_file = self.root / "bad-auth-policy.json"
        bad_file.write_bytes(bad_bytes)
        bad_sha = hashlib.sha256(bad_bytes).hexdigest()

        with self.assertRaises(SystemExit) as cm:
            self.verifier.verify(
                worktree=self.worktree,
                commit=self.head_commit,
                installed=self.installed_dir,
                approved_policy=bad_file,
                approved_policy_sha256=bad_sha,
            )
        self.assertEqual(cm.exception.code, 1)

    def test_policy_mode_mismatch_fails(self):
        self._apply_approved_overlay()
        bad_policy = copy.deepcopy(self.policy_data)
        bad_policy["mode"] = "ask"
        bad_bytes = json.dumps(bad_policy).encode("utf-8")
        bad_file = self.root / "bad-mode-policy.json"
        bad_file.write_bytes(bad_bytes)
        bad_sha = hashlib.sha256(bad_bytes).hexdigest()

        with self.assertRaises(SystemExit) as cm:
            self.verifier.verify(
                worktree=self.worktree,
                commit=self.head_commit,
                installed=self.installed_dir,
                approved_policy=bad_file,
                approved_policy_sha256=bad_sha,
            )
        self.assertEqual(cm.exception.code, 1)

    def test_policy_lanes_mismatch_fails(self):
        self._apply_approved_overlay()
        bad_policy = copy.deepcopy(self.policy_data)
        bad_policy["lanes"] = ["cursor-acp", "antigravity-acp"]
        bad_bytes = json.dumps(bad_policy).encode("utf-8")
        bad_file = self.root / "bad-lanes-policy.json"
        bad_file.write_bytes(bad_bytes)
        bad_sha = hashlib.sha256(bad_bytes).hexdigest()

        with self.assertRaises(SystemExit) as cm:
            self.verifier.verify(
                worktree=self.worktree,
                commit=self.head_commit,
                installed=self.installed_dir,
                approved_policy=bad_file,
                approved_policy_sha256=bad_sha,
            )
        self.assertEqual(cm.exception.code, 1)

    def test_partial_overlay_fails(self):
        mcp_partial = copy.deepcopy(self.mcp_clean)
        mcp_partial["mcpServers"]["cursor-acp"]["env"]["SAARIUS_ACP_PERMISSION_MODE"] = "approve-all"
        mcp_partial["mcpServers"]["antigravity-acp"]["env"] = {"SAARIUS_ACP_PERMISSION_MODE": "approve-all"}
        (self.installed_dir / ".mcp.json").write_text(json.dumps(mcp_partial, indent=2) + "\n", encoding="utf-8")

        with self.assertRaises(SystemExit) as cm:
            self.verifier.verify(
                worktree=self.worktree,
                commit=self.head_commit,
                installed=self.installed_dir,
                approved_policy=self.policy_file,
                approved_policy_sha256=self.policy_sha256,
            )
        self.assertEqual(cm.exception.code, 1)

    def test_permission_value_tamper_fails(self):
        mcp_tampered = copy.deepcopy(self.mcp_clean)
        for lane in ("cursor-acp", "antigravity-acp", "grok-acp"):
            mcp_tampered["mcpServers"][lane].setdefault("env", {})["SAARIUS_ACP_PERMISSION_MODE"] = "approve-all"
        mcp_tampered["mcpServers"]["cursor-acp"]["env"]["SAARIUS_ACP_PERMISSION_MODE"] = "ask"
        (self.installed_dir / ".mcp.json").write_text(json.dumps(mcp_tampered, indent=2) + "\n", encoding="utf-8")

        with self.assertRaises(SystemExit) as cm:
            self.verifier.verify(
                worktree=self.worktree,
                commit=self.head_commit,
                installed=self.installed_dir,
                approved_policy=self.policy_file,
                approved_policy_sha256=self.policy_sha256,
            )
        self.assertEqual(cm.exception.code, 1)

    def test_unrelated_env_tamper_fails(self):
        mcp_tampered = copy.deepcopy(self.mcp_clean)
        for lane in ("cursor-acp", "antigravity-acp", "grok-acp"):
            mcp_tampered["mcpServers"][lane].setdefault("env", {})["SAARIUS_ACP_PERMISSION_MODE"] = "approve-all"
        mcp_tampered["mcpServers"]["cursor-acp"]["env"]["EXTRA_UNAPPROVED_VAR"] = "arbitrary_value"
        (self.installed_dir / ".mcp.json").write_text(json.dumps(mcp_tampered, indent=2) + "\n", encoding="utf-8")

        with self.assertRaises(SystemExit) as cm:
            self.verifier.verify(
                worktree=self.worktree,
                commit=self.head_commit,
                installed=self.installed_dir,
                approved_policy=self.policy_file,
                approved_policy_sha256=self.policy_sha256,
            )
        self.assertEqual(cm.exception.code, 1)

    def test_command_or_args_tamper_fails(self):
        mcp_tampered = copy.deepcopy(self.mcp_clean)
        for lane in ("cursor-acp", "antigravity-acp", "grok-acp"):
            mcp_tampered["mcpServers"][lane].setdefault("env", {})["SAARIUS_ACP_PERMISSION_MODE"] = "approve-all"
        mcp_tampered["mcpServers"]["cursor-acp"]["command"] = "bash"
        (self.installed_dir / ".mcp.json").write_text(json.dumps(mcp_tampered, indent=2) + "\n", encoding="utf-8")

        with self.assertRaises(SystemExit) as cm:
            self.verifier.verify(
                worktree=self.worktree,
                commit=self.head_commit,
                installed=self.installed_dir,
                approved_policy=self.policy_file,
                approved_policy_sha256=self.policy_sha256,
            )
        self.assertEqual(cm.exception.code, 1)

        # Args tamper
        mcp_tampered["mcpServers"]["cursor-acp"]["command"] = "node"
        mcp_tampered["mcpServers"]["cursor-acp"]["args"] = ["bridge/acp-runtime/launcher.mjs", "tampered"]
        (self.installed_dir / ".mcp.json").write_text(json.dumps(mcp_tampered, indent=2) + "\n", encoding="utf-8")
        with self.assertRaises(SystemExit) as cm:
            self.verifier.verify(
                worktree=self.worktree,
                commit=self.head_commit,
                installed=self.installed_dir,
                approved_policy=self.policy_file,
                approved_policy_sha256=self.policy_sha256,
            )
        self.assertEqual(cm.exception.code, 1)

    def test_changed_bridge_bytes_fails(self):
        self._apply_approved_overlay()
        inst_bridge = self.installed_dir / "bridge" / "acp-runtime" / "launcher.mjs"
        inst_bridge.write_text("// tampered bridge launcher\n", encoding="utf-8")

        with self.assertRaises(SystemExit) as cm:
            self.verifier.verify(
                worktree=self.worktree,
                commit=self.head_commit,
                installed=self.installed_dir,
                approved_policy=self.policy_file,
                approved_policy_sha256=self.policy_sha256,
            )
        self.assertEqual(cm.exception.code, 1)

    def test_strict_types_boolean_number_distinction(self):
        """JSON numbers and booleans must not be treated as equal (e.g. 1 != True)."""
        mcp_tampered = copy.deepcopy(self.mcp_clean)
        for lane in ("cursor-acp", "antigravity-acp", "grok-acp"):
            mcp_tampered["mcpServers"][lane].setdefault("env", {})["SAARIUS_ACP_PERMISSION_MODE"] = "approve-all"
        # Substitute an integer 1 for a string value
        mcp_tampered["mcpServers"]["cursor-acp"]["env"]["SAARIUS_ACP_PERMISSION_MODE"] = 1
        (self.installed_dir / ".mcp.json").write_text(json.dumps(mcp_tampered, indent=2) + "\n", encoding="utf-8")

        with self.assertRaises(SystemExit) as cm:
            self.verifier.verify(
                worktree=self.worktree,
                commit=self.head_commit,
                installed=self.installed_dir,
                approved_policy=self.policy_file,
                approved_policy_sha256=self.policy_sha256,
            )
        self.assertEqual(cm.exception.code, 1)

        # Also verify strict_typed_equal directly distinguishes 1 and True
        self.assertFalse(self.verifier.strict_typed_equal(1, True))
        self.assertFalse(self.verifier.strict_typed_equal(0, False))
        self.assertFalse(self.verifier.strict_typed_equal({"a": 1}, {"a": True}))
        self.assertTrue(self.verifier.strict_typed_equal({"a": True}, {"a": True}))

    def test_duplicate_key_rejection(self):
        # JSON with duplicate keys must be rejected with generic diagnostic without echoing the key
        raw_duplicate_json = (
            '{\n'
            '  "mcpServers": {\n'
            '    "cursor-acp": {\n'
            '      "command": "node",\n'
            '      "command": "node",\n'
            '      "args": ["bridge/acp-runtime/launcher.mjs", "cursor-acp"],\n'
            '      "cwd": ".",\n'
            '      "env": {\n'
            '        "CURSOR_AGENT_EXECUTABLE": "/custom/bin/cursor-agent",\n'
            '        "SAARIUS_ACP_PERMISSION_MODE": "approve-all"\n'
            '      }\n'
            '    },\n'
            '    "antigravity-acp": {\n'
            '      "command": "node",\n'
            '      "args": ["bridge/acp-runtime/launcher.mjs", "antigravity-acp"],\n'
            '      "cwd": ".",\n'
            '      "env": {"SAARIUS_ACP_PERMISSION_MODE": "approve-all"}\n'
            '    },\n'
            '    "grok-acp": {\n'
            '      "command": "node",\n'
            '      "args": ["bridge/acp-runtime/launcher.mjs", "grok-acp"],\n'
            '      "cwd": ".",\n'
            '      "env": {"SAARIUS_ACP_PERMISSION_MODE": "approve-all"}\n'
            '    }\n'
            '  }\n'
            '}\n'
        )
        (self.installed_dir / ".mcp.json").write_text(raw_duplicate_json, encoding="utf-8")

        with self.assertRaises(SystemExit) as cm:
            self.verifier.verify(
                worktree=self.worktree,
                commit=self.head_commit,
                installed=self.installed_dir,
                approved_policy=self.policy_file,
                approved_policy_sha256=self.policy_sha256,
            )
        self.assertEqual(cm.exception.code, 1)

    def test_wrapper_standalone_equivalence_clean(self):
        """Standalone verifier and extracted inline runner match on clean fixture."""
        inline_script = extract_inline_runner_script()

        env = {
            **os.environ,
            "WORKTREE": str(self.worktree),
            "SAARIUS_PLUGIN_ROOT": str(self.installed_dir),
            "REVIEWED_COMMIT": self.head_commit,
        }
        env.pop("APPROVED_POLICY", None)
        env.pop("APPROVED_POLICY_SHA256", None)

        cmd = [
            sys.executable,
            str(self.fixture_script),
            "--worktree", str(self.worktree),
            "--commit", self.head_commit,
            "--installed", str(self.installed_dir),
        ]
        standalone_res = subprocess.run(
            cmd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        wrapper_res = subprocess.run(
            [sys.executable, "-c", inline_script],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        self.assertEqual(standalone_res.returncode, 0)
        self.assertEqual(wrapper_res.returncode, 0)
        self.assertEqual(standalone_res.stdout, wrapper_res.stdout)
        self.assertEqual(standalone_res.stderr, wrapper_res.stderr)
        self.assertIn(f"OK 2 paths commit={self.head_commit}", standalone_res.stdout)

    def test_wrapper_standalone_equivalence_approved_overlay(self):
        """Standalone verifier and extracted inline runner match on approved overlay fixture."""
        self._apply_approved_overlay()
        inline_script = extract_inline_runner_script()

        env = {
            **os.environ,
            "WORKTREE": str(self.worktree),
            "SAARIUS_PLUGIN_ROOT": str(self.installed_dir),
            "REVIEWED_COMMIT": self.head_commit,
            "APPROVED_POLICY": str(self.policy_file),
            "APPROVED_POLICY_SHA256": self.policy_sha256,
        }

        cmd = [
            sys.executable,
            str(self.fixture_script),
            "--worktree", str(self.worktree),
            "--commit", self.head_commit,
            "--installed", str(self.installed_dir),
            "--approved-policy", str(self.policy_file),
            "--approved-policy-sha256", self.policy_sha256,
        ]
        standalone_res = subprocess.run(
            cmd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        wrapper_res = subprocess.run(
            [sys.executable, "-c", inline_script],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        self.assertEqual(standalone_res.returncode, 0)
        self.assertEqual(wrapper_res.returncode, 0)
        self.assertEqual(standalone_res.stdout, wrapper_res.stdout)
        self.assertEqual(standalone_res.stderr, wrapper_res.stderr)
        self.assertIn("MATCH_APPROVED_OVERLAY .mcp.json", standalone_res.stdout)

    def test_inline_standalone_parity_incomplete_policy_clean_fixture(self):
        """Both standalone and extracted inline runner must fail on incomplete policy pairs on clean fixture."""
        inline_script = extract_inline_runner_script()

        # Case 1: Policy provided without SHA256
        env_policy_only = {
            **os.environ,
            "WORKTREE": str(self.worktree),
            "SAARIUS_PLUGIN_ROOT": str(self.installed_dir),
            "REVIEWED_COMMIT": self.head_commit,
            "APPROVED_POLICY": str(self.policy_file),
        }
        env_policy_only.pop("APPROVED_POLICY_SHA256", None)

        cmd_policy_only = [
            sys.executable,
            str(self.fixture_script),
            "--worktree", str(self.worktree),
            "--commit", self.head_commit,
            "--installed", str(self.installed_dir),
            "--approved-policy", str(self.policy_file),
        ]
        standalone_p = subprocess.run(
            cmd_policy_only,
            env=env_policy_only,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        wrapper_p = subprocess.run(
            [sys.executable, "-c", inline_script],
            env=env_policy_only,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        self.assertEqual(standalone_p.returncode, 1)
        self.assertEqual(wrapper_p.returncode, 1)
        self.assertIn("both --approved-policy and --approved-policy-sha256 must be provided together", standalone_p.stderr)
        self.assertEqual(standalone_p.stderr, wrapper_p.stderr)

        # Case 2: SHA256 provided without policy file
        env_sha_only = {
            **os.environ,
            "WORKTREE": str(self.worktree),
            "SAARIUS_PLUGIN_ROOT": str(self.installed_dir),
            "REVIEWED_COMMIT": self.head_commit,
            "APPROVED_POLICY_SHA256": self.policy_sha256,
        }
        env_sha_only.pop("APPROVED_POLICY", None)

        cmd_sha_only = [
            sys.executable,
            str(self.fixture_script),
            "--worktree", str(self.worktree),
            "--commit", self.head_commit,
            "--installed", str(self.installed_dir),
            "--approved-policy-sha256", self.policy_sha256,
        ]
        standalone_s = subprocess.run(
            cmd_sha_only,
            env=env_sha_only,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        wrapper_s = subprocess.run(
            [sys.executable, "-c", inline_script],
            env=env_sha_only,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        self.assertEqual(standalone_s.returncode, 1)
        self.assertEqual(wrapper_s.returncode, 1)
        self.assertIn("both --approved-policy and --approved-policy-sha256 must be provided together", standalone_s.stderr)
        self.assertEqual(standalone_s.stderr, wrapper_s.stderr)


    def test_step3_bash_block_preflight_argv(self):
        """Step 3 bash block must assign variables before invoking python3 with correct, non-blank argv."""
        step3_bash = extract_step3_bash_block()

        # Set up a private fixture with a harmless fake python3 executable that emits argv
        fixture_dir = self.root / "fake-python-fixture"
        fake_bin = fixture_dir / "bin"
        fake_bin.mkdir(parents=True, exist_ok=True)
        captured_file = fixture_dir / "captured_argv.json"

        fake_python = fake_bin / "python3"
        fake_python_script = textwrap.dedent(f"""\
            #!{sys.executable}
            import json
            import sys

            with open({repr(str(captured_file))}, "w", encoding="utf-8") as f:
                json.dump(sys.argv[1:], f)
            sys.exit(0)
        """)
        fake_python.write_text(fake_python_script, encoding="utf-8")
        fake_python.chmod(0o755)

        # Start with all Step 3 variables unset
        step3_vars = {
            "WORKTREE",
            "MAINTAINED_PATH",
            "REVIEWED_COMMIT",
            "APPROVED_POLICY",
            "APPROVED_POLICY_SHA256",
        }
        clean_env = {k: v for k, v in os.environ.items() if k not in step3_vars}
        for var in step3_vars:
            self.assertNotIn(var, clean_env)
        # Put fake_bin first in PATH
        clean_env["PATH"] = f"{fake_bin}:{clean_env.get('PATH', '')}"

        # Execute extracted Step 3 bash block in a clean shell
        res = subprocess.run(
            ["bash", "-c", step3_bash],
            env=clean_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.assertEqual(res.returncode, 0, f"Step 3 bash execution failed: stderr={res.stderr}")
        self.assertTrue(captured_file.is_file(), "Fake python3 was not invoked by Step 3 bash block")

        captured_argv = json.loads(captured_file.read_text(encoding="utf-8"))

        # Assert correct non-blank absolute script path
        script_arg = captured_argv[0]
        expected_worktree = "/Users/bobbybones/Developer/worktrees/saariusskills-cursor-luna-model-selection-20260930"
        expected_script = os.path.join(
            expected_worktree,
            "proof/cursor-model-selection/20260930/compare-installed-source.py",
        )
        self.assertTrue(os.path.isabs(script_arg), f"Script path is not absolute: {script_arg}")
        self.assertEqual(script_arg, expected_script)
        self.assertNotIn("//", script_arg)

        # Assert no blank flags or empty values
        for idx, arg in enumerate(captured_argv):
            self.assertTrue(len(arg) > 0, f"Argument at index {idx} is blank: {captured_argv}")

        # Assert expected argument flags and values
        expected_pairs = {
            "--worktree": expected_worktree,
            "--commit": "<40-character-hex-commit-hash>",
            "--installed": "/Users/bobbybones/Developer/worktrees/saariusskills-plugin-107-merged",
            "--approved-policy": "/Users/bobbybones/Developer/_machine-runs/acpx-0193-followup-20260929/personal-acp-permission-policy.json",
            "--approved-policy-sha256": "6df86276b4ecb212e0230266bebcc352b8ba5f63759a279ff1bdf8c40bfa7139",
        }
        for flag, val in expected_pairs.items():
            self.assertIn(flag, captured_argv, f"Missing flag {flag} in {captured_argv}")
            flag_idx = captured_argv.index(flag)
            self.assertLess(flag_idx + 1, len(captured_argv), f"Flag {flag} has no value in {captured_argv}")
            self.assertEqual(captured_argv[flag_idx + 1], val)


if __name__ == "__main__":
    unittest.main()
