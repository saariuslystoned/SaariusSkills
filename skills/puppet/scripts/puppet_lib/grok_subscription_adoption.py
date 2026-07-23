"""Body-free source plan for reusing an operator Grok subscription."""

from __future__ import annotations

from typing import Any, Dict, Tuple


GROK_SUBSCRIPTION_ADOPTION_SCHEMA = "puppet.grok-subscription-adoption/v1"
GROK_SHARED_LEADER_PLAN_SCHEMA = "puppet.grok-shared-leader-plan/v1"
GROK_SHARED_CLIENT_COMPLETION_SCHEMA = "puppet.grok-shared-client-completion/v1"
GROK_SHARED_LEADER_HUMAN_ACTION = "human_start_attended_operator_grok_leader"
GROK_SHARED_LEADER_BLOCKERS: Tuple[str, ...] = (
    "grok_attended_operator_leader_start_requires_human",
    "grok_leader_socket_process_ownership_unproved",
    "grok_tui_shared_leader_attach_semantics_unproved",
    "grok_leader_client_configuration_no_bleed_unproved",
    "grok_shared_leader_client_halt_live_unproved",
)
GROK_SUBSCRIPTION_ADOPTION_BLOCKERS = GROK_SHARED_LEADER_BLOCKERS
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
                "status": "source_plan_available",
                "auth_owner": "attended_operator_process",
                "client_boundary": "exact_unix_socket",
                "private_material_projection_required": False,
                "source_plan_schema": GROK_SHARED_LEADER_PLAN_SCHEMA,
                "client_completion_schema": GROK_SHARED_CLIENT_COMPLETION_SCHEMA,
                "live_human_gate": {
                    "required": True,
                    "action": GROK_SHARED_LEADER_HUMAN_ACTION,
                    "puppet_may_execute": False,
                },
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
        "next_action": (
            "compile_grok_shared_leader_plan_then_request_human_start"
        ),
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
    "GROK_SHARED_CLIENT_COMPLETION_SCHEMA",
    "GROK_SHARED_LEADER_BLOCKERS",
    "GROK_SHARED_LEADER_HUMAN_ACTION",
    "GROK_SHARED_LEADER_PLAN_SCHEMA",
    "GROK_SUBSCRIPTION_ADOPTION_BLOCKERS",
    "GROK_SUBSCRIPTION_ADOPTION_SCHEMA",
    "grok_subscription_adoption_plan",
]
