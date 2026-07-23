"""Body-free source plan for reusing an operator Grok subscription."""

from __future__ import annotations

from typing import Any, Dict, Tuple


GROK_SUBSCRIPTION_ADOPTION_SCHEMA = "puppet.grok-subscription-adoption/v1"
GROK_SUBSCRIPTION_ADOPTION_BLOCKERS: Tuple[str, ...] = (
    "grok_operator_leader_auth_boundary_unproved",
    "grok_leader_client_configuration_no_bleed_unproved",
    "grok_broker_socket_ownership_and_lifecycle_unproved",
)
GROK_AGENT_HELP_SHA256 = (
    "80eca1cc827e677c5d4310fe60ccaa941627cc688189405742e69e4f4ec734d3"
)
GROK_AGENT_LEADER_HELP_SHA256 = (
    "5d0199eb0b874a66a899c34e305719e3f52eb816d3799f9b3510301fdf0455d7"
)


def grok_subscription_adoption_plan() -> Dict[str, Any]:
    """Return candidates without reading auth, config, sessions, or processes."""

    return {
        "schema": GROK_SUBSCRIPTION_ADOPTION_SCHEMA,
        "target": "grok",
        "target_version": "0.2.111",
        "state": "source_candidate_unqualified",
        "preferred_candidate": "process_local_shared_leader",
        "routes": {
            "durable_private_profile": {
                "status": "supported_after_one_time_enrollment",
                "reuse": "native_refreshable_cached_session",
            },
            "process_local_shared_leader": {
                "status": "discovered_unqualified",
                "auth_owner": "attended_operator_process",
                "client_boundary": "exact_unix_socket",
                "private_material_projection_required": False,
                "surfaces": [
                    "grok agent --leader",
                    "grok agent leader",
                    "--leader-socket",
                ],
            },
            "external_auth_provider": {
                "status": "not_a_native_cache_bridge",
                "reason": "requires_separately_provisioned_token_provider",
                "private_material_projection_required": False,
            },
        },
        "evidence": {
            "zero_agent": True,
            "agent_help_sha256": GROK_AGENT_HELP_SHA256,
            "agent_leader_help_sha256": GROK_AGENT_LEADER_HELP_SHA256,
        },
        "blockers": list(GROK_SUBSCRIPTION_ADOPTION_BLOCKERS),
        "human_action_required": False,
        "next_action": "qualify_grok_process_local_shared_leader",
        "private_store_accessed": False,
        "private_material_projected": False,
        "login_performed": False,
        "account_change_performed": False,
        "model_launched": False,
        "raw_output_retained": False,
        "launch_authorized": False,
        "qualification_authorized": False,
    }


__all__ = [
    "GROK_AGENT_HELP_SHA256",
    "GROK_AGENT_LEADER_HELP_SHA256",
    "GROK_SUBSCRIPTION_ADOPTION_BLOCKERS",
    "GROK_SUBSCRIPTION_ADOPTION_SCHEMA",
    "grok_subscription_adoption_plan",
]
