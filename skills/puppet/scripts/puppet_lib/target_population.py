"""Exact protected/root/descendant population admission for harness targets."""

from __future__ import annotations

from typing import Any, Callable, Dict

from .contracts import PROCESS_IDENTITY_FIELDS
from .errors import IdentityError


MAX_TARGET_POPULATION = 64
MAX_TARGET_DESCENDANTS = 32
MAX_TARGET_ANCESTRY_NODES = 512
MAX_ANCESTRY_DEPTH = 64


def validated_target_population(
    *,
    snapshot: Dict[str, Any],
    protected: list[Dict[str, Any]],
    registered: Dict[str, Any],
    process_alive_fn: Callable[[Dict[str, Any]], bool],
    process_tree_alive_fn: Callable[[Dict[str, Any]], bool],
) -> Dict[str, Any]:
    """Admit only exact protected/root identities plus exact root descendants."""

    if not isinstance(snapshot, dict) or set(snapshot) != {
        "processes",
        "ancestry_nodes",
    }:
        raise IdentityError("same-target process snapshot fields are invalid")
    observed = snapshot["processes"]
    nodes = snapshot["ancestry_nodes"]
    if (
        not isinstance(observed, list)
        or len(observed) > MAX_TARGET_POPULATION
        or not isinstance(nodes, list)
        or len(nodes) > MAX_TARGET_ANCESTRY_NODES
    ):
        raise IdentityError("same-target process snapshot exceeds its bound")
    for identity in [*protected, registered, *observed]:
        if not isinstance(identity, dict) or set(identity) != PROCESS_IDENTITY_FIELDS:
            raise IdentityError("same-target process identity fields are invalid")
    nodes_by_pid = {}
    for node in nodes:
        if (
            not isinstance(node, dict)
            or set(node) != {"process", "parent_pid"}
            or not isinstance(node["process"], dict)
            or set(node["process"]) != PROCESS_IDENTITY_FIELDS
            or isinstance(node["parent_pid"], bool)
            or not isinstance(node["parent_pid"], int)
            or node["parent_pid"] < 0
            or node["process"]["pid"] in nodes_by_pid
            or not process_tree_alive_fn(node)
        ):
            raise IdentityError("same-target ancestry node is invalid")
        nodes_by_pid[node["process"]["pid"]] = node
    expected = [*protected, registered]
    expected_pids = [item["pid"] for item in expected]
    observed_pids = [item["pid"] for item in observed]
    if len(expected_pids) != len(set(expected_pids)) or len(observed_pids) != len(
        set(observed_pids)
    ):
        raise IdentityError("same-target process snapshot contains duplicate PIDs")
    observed_by_pid = {item["pid"]: item for item in observed}
    if any(
        nodes_by_pid.get(identity["pid"], {}).get("process") != identity
        for identity in observed
    ):
        raise IdentityError("same-target process lacks an exact ancestry node")
    for identity in expected:
        if observed_by_pid.get(identity["pid"]) != identity or not process_alive_fn(
            identity
        ):
            raise IdentityError("protected or registered process identity changed")

    protected_pids = {item["pid"] for item in protected}
    executable_identity = {
        name: registered[name] for name in ("executable_path", "device", "inode")
    }
    descendants = []
    chains = []
    for identity in observed:
        if identity["pid"] in expected_pids:
            continue
        if {
            name: identity[name] for name in ("executable_path", "device", "inode")
        } != executable_identity or not process_alive_fn(identity):
            raise IdentityError(
                "same-target extra lacks the registered executable identity"
            )
        chain = [nodes_by_pid[identity["pid"]]]
        seen = {identity["pid"]}
        current = nodes_by_pid[identity["pid"]]
        for _ in range(MAX_ANCESTRY_DEPTH):
            parent_pid = current["parent_pid"]
            if parent_pid <= 1 or parent_pid in seen:
                raise IdentityError(
                    "same-target extra lacks an exact registered-target ancestry chain"
                )
            parent = nodes_by_pid.get(parent_pid)
            if parent is None:
                raise IdentityError(
                    "same-target extra lacks an exact registered-target ancestry chain"
                )
            chain.append(parent)
            if parent["process"] == registered:
                break
            if parent_pid in protected_pids:
                raise IdentityError(
                    "same-target extra descends from a protected process"
                )
            seen.add(parent_pid)
            current = parent
        else:
            raise IdentityError("same-target ancestry exceeds the depth bound")
        if chain[-1]["process"] != registered:
            raise IdentityError(
                "same-target extra is unrelated to the registered target"
            )
        descendants.append(identity)
        chains.append(chain)
        if len(descendants) > MAX_TARGET_DESCENDANTS:
            raise IdentityError("same-target descendants exceed the count bound")
    return {
        "processes": sorted(observed, key=lambda item: item["pid"]),
        "descendants": sorted(descendants, key=lambda item: item["pid"]),
        "ancestry_chains": sorted(chains, key=lambda chain: chain[0]["process"]["pid"]),
    }


__all__ = [
    "MAX_ANCESTRY_DEPTH",
    "MAX_TARGET_ANCESTRY_NODES",
    "MAX_TARGET_DESCENDANTS",
    "MAX_TARGET_POPULATION",
    "validated_target_population",
]
