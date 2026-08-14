"""Source-owned exact-tree halt planning for Grok Build regular sessions.

This module does not signal a process or grant launch authority.  It binds the
only topology Puppet is willing to admit: an exact retained root plus
birth-bound same-runtime descendants, disjoint from an immutable protected
population.  A future live consumer must still deliver the exact root SIGINT
and prove the complete bound tree stopped.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Any, Callable, Dict, Mapping

from .contracts import TARGET_POPULATION_POLICY
from .errors import IdentityError, ValidationError
from .grok_launch import (
    GROK_BUILD_VERSION,
    GROK_LAUNCH_AUTHORITY_BLOCKERS,
    GrokLaunchContext,
    _private_context_identity,
    _revalidate_context_roots,
    _validated_grok_doctor_manifest,
)
from .grok_evidence import GROK_PASS_A_LIMITATIONS
from .registry import (
    process_alive,
    process_tree_alive,
    validate_process_identity_shape,
)
from .safety import (
    canonical_json_bytes,
    sha256_bytes,
    validate_bounded_json,
    validate_sha256,
)
from .target_population import (
    MAX_ANCESTRY_DEPTH,
    MAX_TARGET_ANCESTRY_NODES,
    MAX_TARGET_DESCENDANTS,
    MAX_TARGET_POPULATION,
    validated_target_population,
)


GROK_HALT_PLAN_SCHEMA = "puppet.grok-halt-authority-plan/v1"
GROK_HALT_PLAN_STATE = "source_only"
GROK_HALT_BINDING_SCHEMA = "puppet.grok-halt-runtime-binding/v1"
GROK_HALT_BINDING_STATE = "runtime_tree_bound"
GROK_HALT_RECEIPT_SCHEMA = "puppet.grok-halt-completion/v1"
GROK_HALT_STRATEGY = "exact_root_sigint_then_wait_for_bound_tree"
GROK_HALT_RUNTIME_BLOCKER = "grok_leader_child_halt_runtime_unproved"
GROK_CURRENT_SOURCE_BLOCKERS = tuple(
    GROK_HALT_RUNTIME_BLOCKER
    if item == "grok_leader_child_halt_authority_unmodeled"
    else item
    for item in GROK_PASS_A_LIMITATIONS
)
_SOCKET_IDENTITY_FIELDS = {
    "path",
    "device",
    "inode",
    "uid",
    "mode",
    "ctime_ns",
}
_EXECUTABLE_SELECTOR_FIELDS = {"path", "device", "inode"}
_PLAN_FIELDS = {
    "schema",
    "state",
    "target",
    "target_version",
    "target_population_policy",
    "launch_context_sha256",
    "leader_socket",
    "executable_selector",
    "protected_processes",
    "protected_population_sha256",
    "halt_strategy",
    "limits",
    "blockers",
    "launch_authorized",
    "qualification_authorized",
    "plan_sha256",
}
_BINDING_FIELDS = {
    "schema",
    "state",
    "target",
    "target_version",
    "plan_sha256",
    "target_population_policy",
    "leader_socket_identity",
    "root_process",
    "protected_processes",
    "descendants",
    "ancestry_chains",
    "halt_delivery",
    "launch_authorized",
    "qualification_authorized",
    "binding_sha256",
}


def _process(value: Any, *, label: str) -> Dict[str, Any]:
    try:
        return dict(validate_process_identity_shape(value, label))
    except ValidationError as exc:
        raise IdentityError("%s identity is invalid" % label) from exc


def _processes(value: Any, *, label: str) -> list[Dict[str, Any]]:
    if not isinstance(value, list) or len(value) > MAX_TARGET_POPULATION:
        raise IdentityError("%s exceeds its bound" % label)
    result = [_process(item, label="%s process" % label) for item in value]
    result.sort(key=lambda item: item["pid"])
    pids = [item["pid"] for item in result]
    births = [item["kernel_birth_id"] for item in result]
    if len(pids) != len(set(pids)) or len(births) != len(set(births)):
        raise IdentityError("%s contains duplicate identities" % label)
    return result


def _ancestry_chains(
    value: Any,
    *,
    root: Dict[str, Any],
    descendants: list[Dict[str, Any]],
    protected: list[Dict[str, Any]],
) -> list[list[Dict[str, Any]]]:
    if not isinstance(value, list) or len(value) != len(descendants):
        raise ValidationError("Grok halt ancestry chains are invalid")
    protected_pids = {item["pid"] for item in protected}
    expected_descendants = {item["pid"]: item for item in descendants}
    result = []
    observed_descendants = set()
    for raw_chain in value:
        if (
            not isinstance(raw_chain, list)
            or len(raw_chain) < 2
            or len(raw_chain) > MAX_ANCESTRY_DEPTH
        ):
            raise ValidationError("Grok halt ancestry chain is invalid")
        chain = []
        seen = set()
        for node in raw_chain:
            if (
                not isinstance(node, Mapping)
                or set(node) != {"process", "parent_pid"}
                or isinstance(node.get("parent_pid"), bool)
                or not isinstance(node.get("parent_pid"), int)
                or node["parent_pid"] < 0
            ):
                raise ValidationError("Grok halt ancestry node is invalid")
            process = _process(node["process"], label="Grok ancestry")
            if process["pid"] in seen or process["pid"] in protected_pids:
                raise IdentityError("Grok halt ancestry crosses a protected identity")
            seen.add(process["pid"])
            chain.append({"process": process, "parent_pid": node["parent_pid"]})
        descendant = chain[0]["process"]
        if (
            expected_descendants.get(descendant["pid"]) != descendant
            or descendant["pid"] in observed_descendants
            or chain[-1]["process"] != root
            or any(
                chain[index]["parent_pid"] != chain[index + 1]["process"]["pid"]
                for index in range(len(chain) - 1)
            )
        ):
            raise IdentityError("Grok halt ancestry is not rooted in the exact runtime")
        observed_descendants.add(descendant["pid"])
        result.append(chain)
    result.sort(key=lambda chain: chain[0]["process"]["pid"])
    if observed_descendants != set(expected_descendants) or result != value:
        raise IdentityError("Grok halt ancestry chains are not canonical")
    return result


def _selector(value: Any) -> Dict[str, Any]:
    if (
        not isinstance(value, Mapping)
        or set(value) != _EXECUTABLE_SELECTOR_FIELDS
        or not isinstance(value.get("path"), str)
        or not Path(value["path"]).is_absolute()
        or any(
            isinstance(value.get(name), bool)
            or not isinstance(value.get(name), int)
            or value[name] <= 0
            for name in ("device", "inode")
        )
    ):
        raise ValidationError("Grok executable selector is invalid")
    return dict(value)


def _selector_for_process(value: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "path": value["executable_path"],
        "device": value["device"],
        "inode": value["inode"],
    }


def _plan_digest(value: Mapping[str, Any]) -> str:
    payload = dict(value)
    payload.pop("plan_sha256", None)
    return sha256_bytes(canonical_json_bytes(payload))


def _binding_digest(value: Mapping[str, Any]) -> str:
    payload = dict(value)
    payload.pop("binding_sha256", None)
    return sha256_bytes(canonical_json_bytes(payload))


def validate_grok_halt_authority_plan(value: Any) -> Dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _PLAN_FIELDS:
        raise ValidationError("Grok halt authority plan fields are invalid")
    result = dict(value)
    if (
        result["schema"] != GROK_HALT_PLAN_SCHEMA
        or result["state"] != GROK_HALT_PLAN_STATE
        or result["target"] != "grok"
        or result["target_version"] != GROK_BUILD_VERSION
        or result["target_population_policy"] != TARGET_POPULATION_POLICY
        or result["halt_strategy"] != GROK_HALT_STRATEGY
        or result["blockers"] != [GROK_HALT_RUNTIME_BLOCKER]
        or result["launch_authorized"] is not False
        or result["qualification_authorized"] is not False
    ):
        raise ValidationError("Grok halt authority plan is not source-only exact")
    validate_sha256(result["launch_context_sha256"], "Grok launch context")
    selector = _selector(result["executable_selector"])
    protected = _processes(
        result["protected_processes"], label="Grok protected population"
    )
    if any(_selector_for_process(item) != selector for item in protected):
        raise IdentityError(
            "Grok protected population differs from the planned executable"
        )
    if (
        not isinstance(result["leader_socket"], str)
        or not Path(result["leader_socket"]).is_absolute()
        or result["protected_processes"] != protected
        or result["protected_population_sha256"]
        != sha256_bytes(canonical_json_bytes(protected))
        or result["limits"]
        != {
            "max_population": MAX_TARGET_POPULATION,
            "max_descendants": MAX_TARGET_DESCENDANTS,
            "max_ancestry_nodes": MAX_TARGET_ANCESTRY_NODES,
        }
        or result["plan_sha256"] != _plan_digest(result)
    ):
        raise IdentityError("Grok halt authority plan identity changed")
    validate_bounded_json(
        result,
        max_depth=5,
        max_items=256,
        max_string=4096,
        reject_sensitive_fields=True,
    )
    return result


def build_grok_halt_authority_plan(
    context: GrokLaunchContext,
    *,
    protected_processes: list[Dict[str, Any]],
    process_alive_fn: Callable[[Dict[str, Any]], bool] = process_alive,
) -> Dict[str, Any]:
    """Bind the protected baseline and exact future root/descendant policy."""

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
    ):
        raise IdentityError("Grok launch context changed before halt planning")
    executable_identity = manifest.raw["execution"]["runtime_executable"]
    selector = {
        "path": executable_identity["path"],
        "device": executable_identity["device"],
        "inode": executable_identity["inode"],
    }
    protected = _processes(
        protected_processes, label="Grok protected population"
    )
    if len(protected) >= MAX_TARGET_POPULATION:
        raise IdentityError("Grok protected population leaves no root capacity")
    if any(
        _selector_for_process(item) != selector or not process_alive_fn(item)
        for item in protected
    ):
        raise IdentityError("Grok protected population is not exact and live")
    result = {
        "schema": GROK_HALT_PLAN_SCHEMA,
        "state": GROK_HALT_PLAN_STATE,
        "target": "grok",
        "target_version": GROK_BUILD_VERSION,
        "target_population_policy": TARGET_POPULATION_POLICY,
        "launch_context_sha256": sha256_bytes(
            canonical_json_bytes(_private_context_identity(context))
        ),
        "leader_socket": str(context.leader_socket),
        "executable_selector": selector,
        "protected_processes": protected,
        "protected_population_sha256": sha256_bytes(
            canonical_json_bytes(protected)
        ),
        "halt_strategy": GROK_HALT_STRATEGY,
        "limits": {
            "max_population": MAX_TARGET_POPULATION,
            "max_descendants": MAX_TARGET_DESCENDANTS,
            "max_ancestry_nodes": MAX_TARGET_ANCESTRY_NODES,
        },
        "blockers": [GROK_HALT_RUNTIME_BLOCKER],
        "launch_authorized": False,
        "qualification_authorized": False,
    }
    result["plan_sha256"] = _plan_digest(result)
    return validate_grok_halt_authority_plan(result)


def _live_socket_identity(path: Path) -> Dict[str, Any]:
    try:
        details = os.lstat(path)
    except OSError as exc:
        raise IdentityError("Grok leader socket is unavailable") from exc
    if (
        stat.S_ISLNK(details.st_mode)
        or not stat.S_ISSOCK(details.st_mode)
        or details.st_uid != os.getuid()
        or details.st_mode & 0o077
    ):
        raise IdentityError("Grok leader socket identity is not private and exact")
    return {
        "path": str(path),
        "device": details.st_dev,
        "inode": details.st_ino,
        "uid": details.st_uid,
        "mode": stat.S_IMODE(details.st_mode),
        "ctime_ns": details.st_ctime_ns,
    }


def _validate_socket_identity(value: Any) -> Dict[str, Any]:
    if (
        not isinstance(value, Mapping)
        or set(value) != _SOCKET_IDENTITY_FIELDS
        or not isinstance(value.get("path"), str)
        or not Path(value["path"]).is_absolute()
        or any(
            isinstance(value.get(name), bool)
            or not isinstance(value.get(name), int)
            or value[name] < 0
            for name in ("device", "inode", "uid", "mode", "ctime_ns")
        )
        or value["device"] <= 0
        or value["inode"] <= 0
        or value["mode"] & 0o077
    ):
        raise ValidationError("Grok leader socket identity is invalid")
    return dict(value)


def validate_grok_halt_runtime_binding(value: Any) -> Dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _BINDING_FIELDS:
        raise ValidationError("Grok halt runtime binding fields are invalid")
    result = dict(value)
    if (
        result["schema"] != GROK_HALT_BINDING_SCHEMA
        or result["state"] != GROK_HALT_BINDING_STATE
        or result["target"] != "grok"
        or result["target_version"] != GROK_BUILD_VERSION
        or result["target_population_policy"] != TARGET_POPULATION_POLICY
        or result["launch_authorized"] is not False
        or result["qualification_authorized"] is not False
    ):
        raise ValidationError("Grok halt runtime binding is not exact")
    validate_sha256(result["plan_sha256"], "Grok halt plan")
    socket_identity = _validate_socket_identity(result["leader_socket_identity"])
    root = _process(result["root_process"], label="Grok root")
    protected = _processes(
        result["protected_processes"], label="Grok protected population"
    )
    descendants = _processes(
        result["descendants"], label="Grok descendant population"
    )
    if result["protected_processes"] != protected or result["descendants"] != descendants:
        raise IdentityError("Grok halt runtime populations are not canonical")
    ancestry_chains = _ancestry_chains(
        result["ancestry_chains"],
        root=root,
        descendants=descendants,
        protected=protected,
    )
    runtime_selector = _selector_for_process(root)
    all_processes = [*protected, root, *descendants]
    if (
        any(_selector_for_process(item) != runtime_selector for item in all_processes)
        or len({item["pid"] for item in all_processes}) != len(all_processes)
        or len({item["kernel_birth_id"] for item in all_processes})
        != len(all_processes)
    ):
        raise IdentityError("Grok halt runtime population is not exact and disjoint")
    halt_delivery = result["halt_delivery"]
    if halt_delivery != {
        "target_process": root,
        "actions": ["exact_pid_sigint"],
        "broad_signal_allowed": False,
        "force_kill_allowed": False,
    }:
        raise IdentityError("Grok halt delivery authority changed")
    if (
        result["leader_socket_identity"] != socket_identity
        or result["ancestry_chains"] != ancestry_chains
    ):
        raise IdentityError("Grok leader socket identity changed")
    if result["binding_sha256"] != _binding_digest(result):
        raise IdentityError("Grok halt runtime binding identity changed")
    validate_bounded_json(
        result,
        max_depth=7,
        max_items=1024,
        max_string=4096,
        reject_sensitive_fields=True,
    )
    return result


def bind_grok_halt_runtime_tree(
    plan: Mapping[str, Any],
    *,
    root_process: Dict[str, Any],
    snapshot: Dict[str, Any],
    process_alive_fn: Callable[[Dict[str, Any]], bool] = process_alive,
    process_tree_alive_fn: Callable[[Dict[str, Any]], bool] = process_tree_alive,
) -> Dict[str, Any]:
    """Bind one retained Grok root and every admitted same-runtime descendant."""

    normalized_plan = validate_grok_halt_authority_plan(plan)
    root = _process(root_process, label="Grok root")
    protected = normalized_plan["protected_processes"]
    if (
        _selector_for_process(root) != normalized_plan["executable_selector"]
        or root["pid"] in {item["pid"] for item in protected}
        or not process_alive_fn(root)
    ):
        raise IdentityError("Grok root process is not the exact new runtime")
    socket_identity = _live_socket_identity(
        Path(normalized_plan["leader_socket"])
    )
    observation = validated_target_population(
        snapshot=snapshot,
        protected=protected,
        registered=root,
        process_alive_fn=process_alive_fn,
        process_tree_alive_fn=process_tree_alive_fn,
    )
    result = {
        "schema": GROK_HALT_BINDING_SCHEMA,
        "state": GROK_HALT_BINDING_STATE,
        "target": "grok",
        "target_version": GROK_BUILD_VERSION,
        "plan_sha256": normalized_plan["plan_sha256"],
        "target_population_policy": TARGET_POPULATION_POLICY,
        "leader_socket_identity": socket_identity,
        "root_process": root,
        "protected_processes": protected,
        "descendants": observation["descendants"],
        "ancestry_chains": observation["ancestry_chains"],
        "halt_delivery": {
            "target_process": root,
            "actions": ["exact_pid_sigint"],
            "broad_signal_allowed": False,
            "force_kill_allowed": False,
        },
        "launch_authorized": False,
        "qualification_authorized": False,
    }
    result["binding_sha256"] = _binding_digest(result)
    return validate_grok_halt_runtime_binding(result)


def verify_grok_halt_completion(
    plan: Mapping[str, Any],
    binding: Mapping[str, Any],
    *,
    snapshot_after: Dict[str, Any],
    process_alive_fn: Callable[[Dict[str, Any]], bool] = process_alive,
    process_tree_alive_fn: Callable[[Dict[str, Any]], bool] = process_tree_alive,
) -> Dict[str, Any]:
    """Prove the bound new tree stopped and the protected population survived."""

    normalized_plan = validate_grok_halt_authority_plan(plan)
    normalized = validate_grok_halt_runtime_binding(binding)
    if (
        normalized["plan_sha256"] != normalized_plan["plan_sha256"]
        or normalized["protected_processes"]
        != normalized_plan["protected_processes"]
        or normalized["leader_socket_identity"]["path"]
        != normalized_plan["leader_socket"]
        or _selector_for_process(normalized["root_process"])
        != normalized_plan["executable_selector"]
    ):
        raise IdentityError("Grok halt binding differs from its authority plan")
    protected = normalized["protected_processes"]
    stopped = [normalized["root_process"], *normalized["descendants"]]
    if any(process_alive_fn(item) for item in stopped):
        raise IdentityError("Grok bound runtime tree survived exact halt")
    if not isinstance(snapshot_after, dict) or set(snapshot_after) != {
        "processes",
        "ancestry_nodes",
    }:
        raise IdentityError("Grok post-halt population snapshot is invalid")
    observed = _processes(
        snapshot_after["processes"], label="Grok post-halt population"
    )
    if observed != protected:
        raise IdentityError("Grok protected population changed after exact halt")
    nodes = snapshot_after["ancestry_nodes"]
    if not isinstance(nodes, list) or len(nodes) > MAX_TARGET_ANCESTRY_NODES:
        raise IdentityError("Grok post-halt ancestry snapshot exceeds its bound")
    nodes_by_pid = {}
    for node in nodes:
        if (
            not isinstance(node, dict)
            or set(node) != {"process", "parent_pid"}
            or node.get("process") not in protected
            or isinstance(node.get("parent_pid"), bool)
            or not isinstance(node.get("parent_pid"), int)
            or node["parent_pid"] < 0
            or node["process"]["pid"] in nodes_by_pid
            or not process_tree_alive_fn(node)
        ):
            raise IdentityError("Grok post-halt ancestry node is invalid")
        nodes_by_pid[node["process"]["pid"]] = node
    if set(nodes_by_pid) != {item["pid"] for item in protected} or any(
        not process_alive_fn(item) for item in protected
    ):
        raise IdentityError("Grok protected population is not exact after halt")
    socket_path = Path(normalized["leader_socket_identity"]["path"])
    if socket_path.exists() or socket_path.is_symlink():
        raise IdentityError("Grok leader socket survived exact halt")
    receipt = {
        "schema": GROK_HALT_RECEIPT_SCHEMA,
        "state": "halted",
        "target": "grok",
        "binding_sha256": normalized["binding_sha256"],
        "target_population_policy": TARGET_POPULATION_POLICY,
        "stopped_processes": stopped,
        "protected_processes": protected,
        "leader_socket_removed": True,
        "broad_signal_used": False,
        "force_kill_used": False,
        "halt_authority_proved": True,
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
    "GROK_HALT_BINDING_SCHEMA",
    "GROK_HALT_BINDING_STATE",
    "GROK_CURRENT_SOURCE_BLOCKERS",
    "GROK_HALT_PLAN_SCHEMA",
    "GROK_HALT_PLAN_STATE",
    "GROK_HALT_RECEIPT_SCHEMA",
    "GROK_HALT_RUNTIME_BLOCKER",
    "GROK_HALT_STRATEGY",
    "bind_grok_halt_runtime_tree",
    "build_grok_halt_authority_plan",
    "validate_grok_halt_authority_plan",
    "validate_grok_halt_runtime_binding",
    "verify_grok_halt_completion",
]
