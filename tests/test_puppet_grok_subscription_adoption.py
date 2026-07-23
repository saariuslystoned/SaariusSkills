from __future__ import annotations

import ast
import inspect
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "puppet" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from puppet_lib import grok_subscription_adoption as adoption_module  # noqa: E402
from puppet_lib.grok_subscription_adoption import (  # noqa: E402
    GROK_AGENT_HELP_SHA256,
    GROK_AGENT_LEADER_HELP_SHA256,
    GROK_SUBSCRIPTION_ADOPTION_BLOCKERS,
    GROK_SUBSCRIPTION_ADOPTION_SCHEMA,
    grok_subscription_adoption_plan,
)


class GrokSubscriptionAdoptionTests(unittest.TestCase):
    def test_plan_prefers_no_copy_shared_leader_and_rejects_false_broker_claim(self):
        plan = grok_subscription_adoption_plan()
        self.assertEqual(plan["schema"], GROK_SUBSCRIPTION_ADOPTION_SCHEMA)
        self.assertEqual(plan["preferred_candidate"], "process_local_shared_leader")
        self.assertEqual(
            plan["blockers"], list(GROK_SUBSCRIPTION_ADOPTION_BLOCKERS)
        )
        self.assertEqual(
            plan["routes"]["process_local_shared_leader"]["status"],
            "discovered_unqualified",
        )
        self.assertFalse(
            plan["routes"]["process_local_shared_leader"][
                "private_material_projection_required"
            ]
        )
        self.assertEqual(
            plan["routes"]["external_auth_provider"]["status"],
            "not_a_native_cache_bridge",
        )
        self.assertEqual(
            plan["evidence"],
            {
                "zero_agent": True,
                "agent_help_sha256": GROK_AGENT_HELP_SHA256,
                "agent_leader_help_sha256": GROK_AGENT_LEADER_HELP_SHA256,
            },
        )
        for field in (
            "human_action_required",
            "private_store_accessed",
            "private_material_projected",
            "login_performed",
            "account_change_performed",
            "model_launched",
            "raw_output_retained",
            "launch_authorized",
            "qualification_authorized",
        ):
            self.assertFalse(plan[field])

    def test_plan_is_pure_body_free_and_has_no_runtime_or_store_access(self):
        source = inspect.getsource(adoption_module)
        tree = ast.parse(source)
        imported_roots = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_roots.update(
                    alias.name.split(".", 1)[0] for alias in node.names
                )
            elif isinstance(node, ast.ImportFrom):
                imported_roots.add((node.module or "").split(".", 1)[0])
        self.assertTrue(imported_roots <= {"__future__", "typing"})
        for forbidden in (
            "subprocess",
            "os.environ",
            "auth.json",
            "config.toml",
            "read_text",
            "read_json",
            "SessionRegistry",
            "TmuxController",
        ):
            self.assertNotIn(forbidden, source)
        encoded = json.dumps(grok_subscription_adoption_plan(), sort_keys=True)
        for canary in (
            "PUPPET_GROK_SECRET_CANARY",
            "access_token",
            "refresh_token",
            "operator prompt",
        ):
            self.assertNotIn(canary, encoded)
