"""Source-only admission for a human-owned Grok shared leader.

This module never starts or signals Grok.  It binds the exact attended leader
handoff, one private Unix socket, the closed Puppet client context, and the
only acceptable client halt result: the client tree stops while the attended
leader tree and socket remain unchanged.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, Mapping

from .contracts import PROCESS_IDENTITY_FIELDS, TARGET_POPULATION_POLICY
from .errors import IdentityError, ValidationError
from .grok_halt import (
    _ancestry_chains,
    _live_socket_identity,
    _process,
    _processes,
    _selector,
    _selector_for_process,
    _validate_socket_identity,
)
from .grok_launch import (
    GROK_BUILD_VERSION,
    GROK_DISABLE_AUTOUPDATER_VALUE,
    GROK_LAUNCH_AUTHORITY_BLOCKERS,
    GROK_SAFE_PATH_COMPONENTS,
    GrokLaunchContext,
    _private_context_identity,
    _revalidate_context_roots,
    _validated_grok_doctor_manifest,
)
from .grok_subscription_adoption import (
    GROK_SHARED_CLIENT_COMPLETION_SCHEMA,
    GROK_SHARED_LEADER_BLOCKERS,
    GROK_SHARED_LEADER_HUMAN_ACTION,
    GROK_SHARED_LEADER_PLAN_SCHEMA,
    GROK_SUBSCRIPTION_ADOPTION_SCHEMA,
    grok_subscription_adoption_plan,
)
from .registry import (
    process_alive,
    process_tree_alive,
)
from .safety import (
    canonical_json_bytes,
    sha256_bytes,
    validate_bounded_json,
    validate_sha256,
)
from .target_population import validated_target_population


GROK_SHARED_LEADER_PLAN_STATE = "waiting_for_attended_leader"
GROK_SHARED_LEADER_BINDING_SCHEMA = "puppet.grok-shared-leader-binding/v1"
GROK_SHARED_LEADER_BINDING_STATE = "leader_structurally_bound"
GROK_SHARED_CLIENT_BINDING_SCHEMA = "puppet.grok-shared-client-binding/v1"
GROK_SHARED_CLIENT_BINDING_STATE = "client_tree_bound"
GROK_SHARED_CLIENT_HALT_STRATEGY = (
    "exact_client_root_sigint_preserve_attended_leader_and_socket"
)

_PLAN_FIELDS = {
    "schema",
    "state",
    "target",
    "target_version",
    "adoption_schema",
    "adoption_plan_sha256",
    "launch_context_sha256",
    "target_population_policy",
    "executable_selector",
    "leader_socket",
    "baseline_processes",
    "leader_start_argv",
    "client_argv",
    "client_env_names",
    "leader_env_policy",
    "lifecycle_policy",
    "blockers",
    "human_gate",
    "launch_authorized",
    "qualification_authorized",
    "plan_sha256",
}
_LEADER_BINDING_FIELDS = {
    "schema",
    "state",
    "target",
    "target_version",
    "plan_sha256",
    "target_population_policy",
    "leader_socket_identity",
    "leader_process",
    "leader_descendants",
    "leader_ancestry_chains",
    "socket_owner_proved",
    "client_launch_authorized",
    "leader_signal_authorized",
    "qualification_authorized",
    "binding_sha256",
}
_CLIENT_BINDING_FIELDS = {
    "schema",
    "state",
    "target",
    "target_version",
    "plan_sha256",
    "leader_binding_sha256",
    "target_population_policy",
    "leader_socket_identity",
    "protected_leader_processes",
    "client_process",
    "client_descendants",
    "client_ancestry_chains",
    "halt_delivery",
    "leader_signal_authorized",
    "qualification_authorized",
    "binding_sha256",
}


def _digest(value: Mapping[str, Any], field: str) -> str:
    payload = dict(value)
    payload.pop(field, None)
    return sha256_bytes(canonical_json_bytes(payload))


def _expected_leader_argv(executable: str, socket_path: str) -> list[str]:
    return [
        executable,
        "agent",
        "leader",
        "--no-exit-on-disconnect",
        "--relay-on-demand",
        "--no-auto-update",
        "--leader-socket",
        socket_path,
    ]


def _expected_client_argv(context: GrokLaunchContext) -> list[str]:
    return [
        str(context.executable),
        "--always-approve",
        "--sandbox",
        "off",
        "--cwd",
        str(context.cwd),
        "--leader-socket",
        str(context.leader_socket),
        "--session-id",
        context.grok_session_id,
    ]


def _expected_client_values(context: GrokLaunchContext) -> Dict[str, str]:
    return {
        "GROK_DISABLE_AUTOUPDATER": GROK_DISABLE_AUTOUPDATER_VALUE,
        "GROK_HOME": str(context.grok_home),
        "HOME": str(context.home),
        "LANG": "C",
        "LC_ALL": "C",
        "PATH": ":".join(GROK_SAFE_PATH_COMPONENTS),
    }


def _validate_plan_argv(result: Mapping[str, Any]) -> None:
    selector = _selector(result["executable_selector"])
    expected_leader = _expected_leader_argv(
        selector["path"], result["leader_socket"]
    )
    if result["leader_start_argv"] != expected_leader:
        raise IdentityError("Grok shared leader handoff changed")
    client = result["client_argv"]
    if (
        not isinstance(client, list)
        or len(client) != 10
        or client[0] != selector["path"]
        or client[1:5] != ["--always-approve", "--sandbox", "off", "--cwd"]
        or client[6:8] != ["--leader-socket", result["leader_socket"]]
        or client[8] != "--session-id"
        or not isinstance(client[5], str)
        or not Path(client[5]).is_absolute()
        or not isinstance(client[9], str)
        or any(
            item in client
            for item in (
                "--agent",
                "--continue",
                "--debug",
                "--debug-file",
                "--model",
                "--plugin-dir",
                "--prompt-file",
                "--reauth",
                "--reasoning-effort",
                "--resume",
                "--rules",
                "--system-prompt-override",
            )
        )
    ):
        raise IdentityError("Grok shared client vector changed")


def validate_grok_shared_leader_plan(value: Any) -> Dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _PLAN_FIELDS:
        raise ValidationError("Grok shared leader plan fields are invalid")
    result = dict(value)
    if (
        result["schema"] != GROK_SHARED_LEADER_PLAN_SCHEMA
        or result["state"] != GROK_SHARED_LEADER_PLAN_STATE
        or result["target"] != "grok"
        or result["target_version"] != GROK_BUILD_VERSION
        or result["adoption_schema"] != GROK_SUBSCRIPTION_ADOPTION_SCHEMA
        or result["target_population_policy"] != TARGET_POPULATION_POLICY
        or result["baseline_processes"] != []
        or result["client_env_names"]
        != [
            "GROK_DISABLE_AUTOUPDATER",
            "GROK_HOME",
            "HOME",
            "LANG",
            "LC_ALL",
            "PATH",
        ]
        or result["leader_env_policy"]
        != {
            "owner": "attended_operator",
            "values_recorded": False,
            "store_read_by_puppet": False,
        }
        or result["lifecycle_policy"]
        != {
            "client_halt_strategy": GROK_SHARED_CLIENT_HALT_STRATEGY,
            "leader_survives_client": True,
            "socket_survives_client": True,
            "puppet_may_start_leader": False,
            "puppet_may_signal_leader": False,
        }
        or result["blockers"] != list(GROK_SHARED_LEADER_BLOCKERS)
        or result["human_gate"]
        != {
            "required": True,
            "action": GROK_SHARED_LEADER_HUMAN_ACTION,
            "account_change": False,
            "login_performed_by_puppet": False,
        }
        or result["launch_authorized"] is not False
        or result["qualification_authorized"] is not False
    ):
        raise ValidationError("Grok shared leader plan is not exact")
    validate_sha256(result["adoption_plan_sha256"], "Grok adoption plan")
    validate_sha256(result["launch_context_sha256"], "Grok launch context")
    _selector(result["executable_selector"])
    if (
        not isinstance(result["leader_socket"], str)
        or not Path(result["leader_socket"]).is_absolute()
        or result["plan_sha256"] != _digest(result, "plan_sha256")
    ):
        raise IdentityError("Grok shared leader plan identity changed")
    _validate_plan_argv(result)
    validate_bounded_json(
        result,
        max_depth=5,
        max_items=96,
        max_string=4096,
        reject_sensitive_fields=True,
    )
    return result


def build_grok_shared_leader_plan(
    context: GrokLaunchContext,
    *,
    baseline_processes: list[Dict[str, Any]],
) -> Dict[str, Any]:
    """Bind an attended leader handoff without starting or authenticating it."""

    if type(context) is not GrokLaunchContext:
        raise ValidationError("Grok launch context is invalid")
    if context.launch_authorized is not False or tuple(context.blockers) != tuple(
        GROK_LAUNCH_AUTHORITY_BLOCKERS
    ):
        raise IdentityError("Grok launch context authority changed")
    _revalidate_context_roots(context)
    _bound_manifest, manifest, executable = _validated_grok_doctor_manifest(
        context.doctor_manifest
    )
    if (
        executable != context.executable
        or manifest.fingerprint != context.doctor_manifest_fingerprint
        or manifest.raw["adapter_fingerprint"] != context.adapter_fingerprint
        or context.leader_socket.exists()
        or context.leader_socket.is_symlink()
        or list(context.argv) != _expected_client_argv(context)
        or dict(context.environment) != _expected_client_values(context)
    ):
        raise IdentityError("Grok shared leader launch context changed")
    baseline = _processes(
        baseline_processes, label="Grok shared leader baseline"
    )
    if baseline:
        raise IdentityError(
            "Grok shared leader requires an empty same-target baseline"
        )
    runtime = manifest.raw["execution"]["runtime_executable"]
    selector = {
        "path": runtime["path"],
        "device": runtime["device"],
        "inode": runtime["inode"],
    }
    if selector["path"] != str(executable):
        raise IdentityError("Grok shared leader runtime selector changed")
    adoption = grok_subscription_adoption_plan()
    result = {
        "schema": GROK_SHARED_LEADER_PLAN_SCHEMA,
        "state": GROK_SHARED_LEADER_PLAN_STATE,
        "target": "grok",
        "target_version": GROK_BUILD_VERSION,
        "adoption_schema": adoption["schema"],
        "adoption_plan_sha256": sha256_bytes(canonical_json_bytes(adoption)),
        "launch_context_sha256": sha256_bytes(
            canonical_json_bytes(_private_context_identity(context))
        ),
        "target_population_policy": TARGET_POPULATION_POLICY,
        "executable_selector": selector,
        "leader_socket": str(context.leader_socket),
        "baseline_processes": baseline,
        "leader_start_argv": _expected_leader_argv(
            str(executable), str(context.leader_socket)
        ),
        "client_argv": list(context.argv),
        "client_env_names": sorted(context.environment),
        "leader_env_policy": {
            "owner": "attended_operator",
            "values_recorded": False,
            "store_read_by_puppet": False,
        },
        "lifecycle_policy": {
            "client_halt_strategy": GROK_SHARED_CLIENT_HALT_STRATEGY,
            "leader_survives_client": True,
            "socket_survives_client": True,
            "puppet_may_start_leader": False,
            "puppet_may_signal_leader": False,
        },
        "blockers": list(GROK_SHARED_LEADER_BLOCKERS),
        "human_gate": {
            "required": True,
            "action": GROK_SHARED_LEADER_HUMAN_ACTION,
            "account_change": False,
            "login_performed_by_puppet": False,
        },
        "launch_authorized": False,
        "qualification_authorized": False,
    }
    result["plan_sha256"] = _digest(result, "plan_sha256")
    return validate_grok_shared_leader_plan(result)


def validate_grok_shared_leader_binding(value: Any) -> Dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _LEADER_BINDING_FIELDS:
        raise ValidationError("Grok shared leader binding fields are invalid")
    result = dict(value)
    if (
        result["schema"] != GROK_SHARED_LEADER_BINDING_SCHEMA
        or result["state"] != GROK_SHARED_LEADER_BINDING_STATE
        or result["target"] != "grok"
        or result["target_version"] != GROK_BUILD_VERSION
        or result["target_population_policy"] != TARGET_POPULATION_POLICY
        or result["socket_owner_proved"] is not False
        or result["client_launch_authorized"] is not False
        or result["leader_signal_authorized"] is not False
        or result["qualification_authorized"] is not False
    ):
        raise ValidationError("Grok shared leader binding is not exact")
    validate_sha256(result["plan_sha256"], "Grok shared leader plan")
    socket_identity = _validate_socket_identity(result["leader_socket_identity"])
    leader = _process(result["leader_process"], label="Grok shared leader")
    descendants = _processes(
        result["leader_descendants"], label="Grok shared leader descendants"
    )
    ancestry = _ancestry_chains(
        result["leader_ancestry_chains"],
        root=leader,
        descendants=descendants,
        protected=[],
    )
    selector = _selector_for_process(leader)
    if (
        any(_selector_for_process(item) != selector for item in descendants)
        or result["leader_socket_identity"] != socket_identity
        or result["leader_descendants"] != descendants
        or result["leader_ancestry_chains"] != ancestry
        or result["binding_sha256"] != _digest(result, "binding_sha256")
    ):
        raise IdentityError("Grok shared leader binding identity changed")
    validate_bounded_json(
        result,
        max_depth=7,
        max_items=1024,
        max_string=4096,
        reject_sensitive_fields=True,
    )
    return result


def bind_grok_shared_leader_runtime(
    plan: Mapping[str, Any],
    *,
    leader_process: Dict[str, Any],
    snapshot: Dict[str, Any],
    process_alive_fn: Callable[[Dict[str, Any]], bool] = process_alive,
    process_tree_alive_fn: Callable[[Dict[str, Any]], bool] = process_tree_alive,
) -> Dict[str, Any]:
    """Record structural leader/socket evidence without claiming ownership."""

    normalized_plan = validate_grok_shared_leader_plan(plan)
    leader = _process(leader_process, label="Grok shared leader")
    if (
        _selector_for_process(leader) != normalized_plan["executable_selector"]
        or not process_alive_fn(leader)
    ):
        raise IdentityError("Grok shared leader process is not exact and live")
    socket_identity = _live_socket_identity(
        Path(normalized_plan["leader_socket"])
    )
    observation = validated_target_population(
        snapshot=snapshot,
        protected=[],
        registered=leader,
        process_alive_fn=process_alive_fn,
        process_tree_alive_fn=process_tree_alive_fn,
    )
    result = {
        "schema": GROK_SHARED_LEADER_BINDING_SCHEMA,
        "state": GROK_SHARED_LEADER_BINDING_STATE,
        "target": "grok",
        "target_version": GROK_BUILD_VERSION,
        "plan_sha256": normalized_plan["plan_sha256"],
        "target_population_policy": TARGET_POPULATION_POLICY,
        "leader_socket_identity": socket_identity,
        "leader_process": leader,
        "leader_descendants": observation["descendants"],
        "leader_ancestry_chains": observation["ancestry_chains"],
        "socket_owner_proved": False,
        "client_launch_authorized": False,
        "leader_signal_authorized": False,
        "qualification_authorized": False,
    }
    result["binding_sha256"] = _digest(result, "binding_sha256")
    return validate_grok_shared_leader_binding(result)


def validate_grok_shared_client_binding(value: Any) -> Dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _CLIENT_BINDING_FIELDS:
        raise ValidationError("Grok shared client binding fields are invalid")
    result = dict(value)
    if (
        result["schema"] != GROK_SHARED_CLIENT_BINDING_SCHEMA
        or result["state"] != GROK_SHARED_CLIENT_BINDING_STATE
        or result["target"] != "grok"
        or result["target_version"] != GROK_BUILD_VERSION
        or result["target_population_policy"] != TARGET_POPULATION_POLICY
        or result["leader_signal_authorized"] is not False
        or result["qualification_authorized"] is not False
    ):
        raise ValidationError("Grok shared client binding is not exact")
    validate_sha256(result["plan_sha256"], "Grok shared leader plan")
    validate_sha256(
        result["leader_binding_sha256"], "Grok shared leader binding"
    )
    socket_identity = _validate_socket_identity(result["leader_socket_identity"])
    protected = _processes(
        result["protected_leader_processes"],
        label="Grok protected shared leader population",
    )
    client = _process(result["client_process"], label="Grok shared client")
    descendants = _processes(
        result["client_descendants"], label="Grok shared client descendants"
    )
    ancestry = _ancestry_chains(
        result["client_ancestry_chains"],
        root=client,
        descendants=descendants,
        protected=protected,
    )
    selector = _selector_for_process(client)
    population = [*protected, client, *descendants]
    if (
        not protected
        or any(_selector_for_process(item) != selector for item in population)
        or len({item["pid"] for item in population}) != len(population)
        or result["leader_socket_identity"] != socket_identity
        or result["protected_leader_processes"] != protected
        or result["client_descendants"] != descendants
        or result["client_ancestry_chains"] != ancestry
        or result["halt_delivery"]
        != {
            "target_process": client,
            "actions": ["exact_pid_sigint"],
            "broad_signal_allowed": False,
            "force_kill_allowed": False,
            "preserve_leader": True,
            "preserve_socket": True,
        }
        or result["binding_sha256"] != _digest(result, "binding_sha256")
    ):
        raise IdentityError("Grok shared client binding identity changed")
    validate_bounded_json(
        result,
        max_depth=7,
        max_items=1024,
        max_string=4096,
        reject_sensitive_fields=True,
    )
    return result


def bind_grok_shared_client_runtime(
    plan: Mapping[str, Any],
    leader_binding: Mapping[str, Any],
    *,
    client_process: Dict[str, Any],
    snapshot: Dict[str, Any],
    process_alive_fn: Callable[[Dict[str, Any]], bool] = process_alive,
    process_tree_alive_fn: Callable[[Dict[str, Any]], bool] = process_tree_alive,
) -> Dict[str, Any]:
    """Bind a client tree while treating the leader tree as protected."""

    normalized_plan = validate_grok_shared_leader_plan(plan)
    leader = validate_grok_shared_leader_binding(leader_binding)
    if leader["plan_sha256"] != normalized_plan["plan_sha256"]:
        raise IdentityError("Grok shared leader binding belongs to another plan")
    current_socket = _live_socket_identity(
        Path(normalized_plan["leader_socket"])
    )
    if current_socket != leader["leader_socket_identity"]:
        raise IdentityError("Grok shared leader socket changed before client bind")
    protected = _processes(
        [leader["leader_process"], *leader["leader_descendants"]],
        label="Grok protected shared leader population",
    )
    client = _process(client_process, label="Grok shared client")
    if (
        _selector_for_process(client) != normalized_plan["executable_selector"]
        or client["pid"] in {item["pid"] for item in protected}
        or not process_alive_fn(client)
    ):
        raise IdentityError("Grok shared client process is not exact and new")
    observation = validated_target_population(
        snapshot=snapshot,
        protected=protected,
        registered=client,
        process_alive_fn=process_alive_fn,
        process_tree_alive_fn=process_tree_alive_fn,
    )
    result = {
        "schema": GROK_SHARED_CLIENT_BINDING_SCHEMA,
        "state": GROK_SHARED_CLIENT_BINDING_STATE,
        "target": "grok",
        "target_version": GROK_BUILD_VERSION,
        "plan_sha256": normalized_plan["plan_sha256"],
        "leader_binding_sha256": leader["binding_sha256"],
        "target_population_policy": TARGET_POPULATION_POLICY,
        "leader_socket_identity": current_socket,
        "protected_leader_processes": protected,
        "client_process": client,
        "client_descendants": observation["descendants"],
        "client_ancestry_chains": observation["ancestry_chains"],
        "halt_delivery": {
            "target_process": client,
            "actions": ["exact_pid_sigint"],
            "broad_signal_allowed": False,
            "force_kill_allowed": False,
            "preserve_leader": True,
            "preserve_socket": True,
        },
        "leader_signal_authorized": False,
        "qualification_authorized": False,
    }
    result["binding_sha256"] = _digest(result, "binding_sha256")
    return validate_grok_shared_client_binding(result)


def _validated_after_nodes(
    value: Any,
    *,
    protected: list[Dict[str, Any]],
    process_tree_alive_fn: Callable[[Dict[str, Any]], bool],
) -> Dict[int, Dict[str, Any]]:
    if not isinstance(value, list) or len(value) > 512:
        raise IdentityError("Grok shared client post-halt ancestry is invalid")
    nodes: Dict[int, Dict[str, Any]] = {}
    for item in value:
        if (
            not isinstance(item, Mapping)
            or set(item) != {"process", "parent_pid"}
            or not isinstance(item.get("process"), Mapping)
            or set(item["process"]) != PROCESS_IDENTITY_FIELDS
            or isinstance(item.get("parent_pid"), bool)
            or not isinstance(item.get("parent_pid"), int)
            or item["parent_pid"] < 0
        ):
            raise IdentityError("Grok shared client post-halt node is invalid")
        process = _process(item["process"], label="Grok post-halt process")
        node = {"process": process, "parent_pid": item["parent_pid"]}
        if process["pid"] in nodes or not process_tree_alive_fn(node):
            raise IdentityError("Grok shared client post-halt node changed")
        nodes[process["pid"]] = node
    for process in protected:
        if nodes.get(process["pid"], {}).get("process") != process:
            raise IdentityError("Grok protected leader ancestry changed")
    return nodes


def verify_grok_shared_client_completion(
    plan: Mapping[str, Any],
    leader_binding: Mapping[str, Any],
    client_binding: Mapping[str, Any],
    *,
    snapshot_after: Dict[str, Any],
    process_alive_fn: Callable[[Dict[str, Any]], bool] = process_alive,
    process_tree_alive_fn: Callable[[Dict[str, Any]], bool] = process_tree_alive,
) -> Dict[str, Any]:
    """Prove only the client tree stopped and the leader/socket survived."""

    normalized_plan = validate_grok_shared_leader_plan(plan)
    leader = validate_grok_shared_leader_binding(leader_binding)
    client = validate_grok_shared_client_binding(client_binding)
    if (
        leader["plan_sha256"] != normalized_plan["plan_sha256"]
        or client["plan_sha256"] != normalized_plan["plan_sha256"]
        or client["leader_binding_sha256"] != leader["binding_sha256"]
    ):
        raise IdentityError("Grok shared client evidence belongs to another plan")
    stopped = [client["client_process"], *client["client_descendants"]]
    if any(process_alive_fn(item) for item in stopped):
        raise IdentityError("Grok shared client tree survived exact halt")
    if not isinstance(snapshot_after, Mapping) or set(snapshot_after) != {
        "processes",
        "ancestry_nodes",
    }:
        raise IdentityError("Grok shared client post-halt snapshot is invalid")
    protected = client["protected_leader_processes"]
    observed = _processes(
        snapshot_after["processes"],
        label="Grok post-halt protected leader population",
    )
    if observed != protected or any(
        not process_alive_fn(item) for item in protected
    ):
        raise IdentityError("Grok protected leader population changed")
    _validated_after_nodes(
        snapshot_after["ancestry_nodes"],
        protected=protected,
        process_tree_alive_fn=process_tree_alive_fn,
    )
    current_socket = _live_socket_identity(
        Path(normalized_plan["leader_socket"])
    )
    if (
        current_socket != leader["leader_socket_identity"]
        or current_socket != client["leader_socket_identity"]
    ):
        raise IdentityError("Grok shared leader socket changed after client halt")
    receipt = {
        "schema": GROK_SHARED_CLIENT_COMPLETION_SCHEMA,
        "state": "client_halted_leader_preserved",
        "target": "grok",
        "client_binding_sha256": client["binding_sha256"],
        "stopped_client_processes": stopped,
        "protected_leader_processes": protected,
        "leader_socket_identity": current_socket,
        "leader_signal_used": False,
        "broad_signal_used": False,
        "force_kill_used": False,
        "client_halt_boundary_observed": True,
        "leader_socket_owner_proved": False,
        "no_bleed_proved": False,
        "qualification_authorized": False,
    }
    validate_bounded_json(
        receipt,
        max_depth=5,
        max_items=512,
        max_string=4096,
        reject_sensitive_fields=True,
    )
    return receipt


__all__ = [
    "GROK_SHARED_CLIENT_BINDING_SCHEMA",
    "GROK_SHARED_CLIENT_BINDING_STATE",
    "GROK_SHARED_CLIENT_COMPLETION_SCHEMA",
    "GROK_SHARED_CLIENT_HALT_STRATEGY",
    "GROK_SHARED_LEADER_BINDING_SCHEMA",
    "GROK_SHARED_LEADER_BINDING_STATE",
    "GROK_SHARED_LEADER_BLOCKERS",
    "GROK_SHARED_LEADER_HUMAN_ACTION",
    "GROK_SHARED_LEADER_PLAN_SCHEMA",
    "GROK_SHARED_LEADER_PLAN_STATE",
    "bind_grok_shared_client_runtime",
    "bind_grok_shared_leader_runtime",
    "build_grok_shared_leader_plan",
    "validate_grok_shared_client_binding",
    "validate_grok_shared_leader_binding",
    "validate_grok_shared_leader_plan",
    "verify_grok_shared_client_completion",
]
