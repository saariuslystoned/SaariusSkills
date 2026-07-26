from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any

from .errors import HerdrPuppetError
from .herdr_client import HerdrClient, load_json
from .journal import (
    append_event,
    atomic_json,
    make_event,
    now,
    read_events,
    refresh_state,
    require_initialized_journal,
    sha256_text,
)


SUPPORTED_HERDR_VERSION = "0.7.3"
SUPPORTED_HERDR_PROTOCOL = 16
CHECKPOINT_KINDS = ("STATUS", "ACTION_REQUIRED", "DONE")
PRESERVE_REASONS = {
    "checkpoint_failed",
    "human_gate",
    "milestone_complete",
    "operator_stop",
    "route_superseded",
}

LEASE_WAIT_REVISION_FIELDS = (
    "schema",
    "run_id",
    "harness",
    "session",
    "workspace",
    "owned_label",
    "tab_id",
    "pane_id",
    "terminal_id",
    "ssh",
    "next_seq",
    "source",
    "proof_root",
)


def _require_string(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise HerdrPuppetError(
            "invalid_record",
            f"Required string field is missing: {key}",
        )
    return value


def validate_plan(payload: dict[str, Any]) -> None:
    if payload.get("schema") != "herdr-puppet.plan.v1":
        raise HerdrPuppetError("invalid_plan_schema", "Unsupported plan schema.")
    if payload.get("state") != "planned":
        raise HerdrPuppetError("invalid_plan_state", "The plan is not in planned state.")
    for key in (
        "run_id",
        "harness",
        "expected_ssh_target",
        "owned_label",
        "proof_root",
    ):
        _require_string(payload, key)
    for key in ("session", "workspace", "source", "safety"):
        if not isinstance(payload.get(key), dict):
            raise HerdrPuppetError(
                "invalid_plan",
                f"Required object field is missing: {key}",
            )
    safety = payload["safety"]
    if safety.get("parent_session_mutation") is not False:
        raise HerdrPuppetError(
            "parent_session_mutation_forbidden",
            "A plan may not authorize parent-session mutation.",
        )
    if safety.get("adopt_existing_tab") is not False:
        raise HerdrPuppetError(
            "existing_tab_adoption_forbidden",
            "A plan may not authorize existing-tab adoption.",
        )
    if safety.get("ordinary_transcript_read") is not False:
        raise HerdrPuppetError(
            "ordinary_transcript_read_forbidden",
            "A plan may not authorize ordinary transcript reads.",
        )
    session = payload["session"]
    if session.get("incarnation_proven") is not False:
        raise HerdrPuppetError(
            "server_incarnation_claim_forbidden",
            "Herdr 0.7.3 does not expose a server-incarnation authority field.",
        )


def validate_lease(payload: dict[str, Any]) -> None:
    if payload.get("schema") != "herdr-puppet.lease.v1":
        raise HerdrPuppetError("invalid_lease_schema", "Unsupported lease schema.")
    if payload.get("state") not in {"active", "preserved"}:
        raise HerdrPuppetError(
            "invalid_lease_state",
            "The lease state is neither active nor preserved.",
        )
    for key in (
        "run_id",
        "harness",
        "owned_label",
        "tab_id",
        "pane_id",
        "terminal_id",
        "proof_root",
    ):
        _require_string(payload, key)
    if not isinstance(payload.get("next_seq"), int) or payload["next_seq"] < 1:
        raise HerdrPuppetError("invalid_next_seq", "Lease next_seq must be positive.")
    for key in ("session", "workspace", "ssh", "source"):
        if not isinstance(payload.get(key), dict):
            raise HerdrPuppetError(
                "invalid_lease",
                f"Required object field is missing: {key}",
            )
    if payload["session"].get("incarnation_proven") is not False:
        raise HerdrPuppetError(
            "server_incarnation_claim_forbidden",
            "Herdr 0.7.3 does not expose a server-incarnation authority field.",
        )
    if "cleanup_state" in payload:
        if (
            payload["state"] != "preserved"
            or payload.get("cleanup_state") != "closed"
            or not isinstance(payload.get("cleanup_verified_at"), str)
            or not payload["cleanup_verified_at"]
            or not isinstance(payload.get("cleanup_reconciled_absence"), bool)
        ):
            raise HerdrPuppetError(
                "invalid_cleanup_record",
                "A closed cleanup record requires a preserved lease and "
                "complete verification fields.",
            )


def _version_from_text(version_text: str) -> str:
    match = re.fullmatch(r"herdr\s+([0-9]+\.[0-9]+\.[0-9]+)", version_text.strip())
    if not match:
        raise HerdrPuppetError(
            "invalid_herdr_version",
            "Herdr returned an unrecognized version string.",
        )
    return match.group(1)


def doctor(
    client: HerdrClient,
    session: str,
    *,
    facts: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if facts is None:
        version_text = client.version_text()
        server = client.server_status(session)
        sessions = client.sessions()
    else:
        version_text = _require_string(facts, "version_text")
        server = facts.get("server_status")
        sessions = facts.get("sessions")
        if not isinstance(server, dict) or not isinstance(sessions, list):
            raise HerdrPuppetError(
                "invalid_doctor_facts",
                "Doctor fixture is missing server_status or sessions.",
            )

    version = _version_from_text(version_text)
    matches = [item for item in sessions if item.get("name") == session]
    blockers: list[str] = []
    if version != SUPPORTED_HERDR_VERSION:
        blockers.append("unsupported_herdr_version")
    if server.get("version") != SUPPORTED_HERDR_VERSION:
        blockers.append("server_version_mismatch")
    if server.get("protocol") != SUPPORTED_HERDR_PROTOCOL:
        blockers.append("unsupported_herdr_protocol")
    if server.get("session") != session:
        blockers.append("server_session_mismatch")
    if server.get("running") is not True or server.get("status") != "running":
        blockers.append("server_not_running")
    if server.get("compatible") is not True:
        blockers.append("server_incompatible")
    if not isinstance(server.get("socket"), str) or not server["socket"]:
        blockers.append("server_socket_missing")
    if len(matches) != 1 or matches[0].get("running") is not True:
        blockers.append("session_inventory_ambiguous")

    return {
        "schema": "herdr-puppet.doctor.v1",
        "result": "ok" if not blockers else "blocked",
        "session": session,
        "version": version,
        "protocol": server.get("protocol"),
        "socket": server.get("socket"),
        "blockers": blockers,
        "safety": {
            "mutated": False,
            "pane_read": False,
            "parent_session_mutation": False,
        },
    }


def _find_workspace(
    workspaces: list[dict[str, Any]],
    workspace_id: str,
    workspace_label: str,
) -> dict[str, Any]:
    matches = [
        item
        for item in workspaces
        if item.get("workspace_id") == workspace_id
        and item.get("label") == workspace_label
    ]
    if len(matches) != 1:
        raise HerdrPuppetError(
            "workspace_capability_mismatch",
            "The exact workspace ID and label did not resolve once.",
            details={"workspace_id": workspace_id, "workspace_label": workspace_label},
        )
    return matches[0]


def _label(run_id: str, harness: str, ordinal: int) -> str:
    safe_harness = re.sub(r"[^a-z0-9]+", "-", harness.lower()).strip("-")
    safe_run = re.sub(r"[^a-z0-9]+", "", run_id.lower())
    if not safe_harness or not safe_run:
        raise HerdrPuppetError(
            "invalid_label_material",
            "Run ID and harness must produce a deterministic label.",
        )
    run_digest = hashlib.sha256(run_id.encode("utf-8")).hexdigest()[:6]
    return f"puppet-{safe_harness}-{safe_run[:8]}-{run_digest}-{ordinal}"


def plan(
    client: HerdrClient,
    *,
    session: str,
    workspace_id: str,
    workspace_label: str,
    expected_ssh_target: str,
    run_id: str,
    harness: str,
    repo: str,
    worktree: str,
    proof_root: str,
    ordinal: int = 1,
    live_mutation_authorized: bool = False,
    facts: dict[str, Any] | None = None,
) -> dict[str, Any]:
    doctor_facts = facts.get("doctor") if facts else None
    doctor_result = doctor(client, session, facts=doctor_facts)
    if doctor_result["result"] != "ok":
        raise HerdrPuppetError(
            "doctor_blocked",
            "Herdr doctor must pass before planning.",
            details={"blockers": doctor_result["blockers"]},
        )
    if facts is None:
        workspaces = client.snapshot(session)["workspaces"]
    else:
        workspaces = facts.get("workspaces")
        if not isinstance(workspaces, list):
            raise HerdrPuppetError(
                "invalid_plan_facts",
                "Plan fixture is missing workspaces.",
            )
    _find_workspace(workspaces, workspace_id, workspace_label)
    payload = {
        "schema": "herdr-puppet.plan.v1",
        "state": "planned",
        "run_id": run_id,
        "harness": harness,
        "session": {
            "name": session,
            "version": doctor_result["version"],
            "protocol": doctor_result["protocol"],
            "socket": doctor_result["socket"],
            "incarnation_proven": False,
        },
        "workspace": {"id": workspace_id, "label": workspace_label},
        "expected_ssh_target": expected_ssh_target,
        "owned_label": _label(run_id, harness, ordinal),
        "source": {"repo": repo, "worktree": worktree},
        "proof_root": proof_root,
        "safety": {
            "parent_session_mutation": False,
            "adopt_existing_tab": False,
            "ordinary_transcript_read": False,
            "live_mutation_authorized": bool(live_mutation_authorized),
        },
    }
    validate_plan(payload)
    return payload


def _expected_ssh_process(
    process_info: dict[str, Any],
    expected_target: str,
) -> dict[str, Any]:
    processes = process_info.get("foreground_processes")
    if not isinstance(processes, list):
        raise HerdrPuppetError(
            "invalid_foreground_processes",
            "Foreground process inventory is missing.",
        )
    matches = []
    for item in processes:
        argv = item.get("argv")
        if not isinstance(argv, list) or not argv:
            continue
        executable = Path(str(argv[0])).name
        if executable == "ssh" and expected_target in argv[1:]:
            matches.append(item)
    if len(matches) != 1:
        raise HerdrPuppetError(
            "ssh_identity_mismatch",
            "The pane does not contain exactly one expected foreground SSH process.",
            details={"expected_target": expected_target},
        )
    if not isinstance(matches[0].get("pid"), int) or matches[0]["pid"] < 1:
        raise HerdrPuppetError("invalid_ssh_pid", "The SSH PID is invalid.")
    return matches[0]


def structural_status(
    client: HerdrClient,
    *,
    plan_payload: dict[str, Any] | None = None,
    lease_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if (plan_payload is None) == (lease_payload is None):
        raise HerdrPuppetError(
            "status_record_ambiguous",
            "Provide exactly one plan or lease to status.",
        )
    payload = lease_payload if lease_payload is not None else plan_payload
    assert payload is not None
    if lease_payload is not None:
        validate_lease(payload)
    else:
        validate_plan(payload)
    session = payload["session"]["name"]
    doctor_result = doctor(client, session)
    if doctor_result["result"] != "ok":
        return {
            "schema": "herdr-puppet.status.v1",
            "result": "blocked",
            "run_id": payload["run_id"],
            "blockers": doctor_result["blockers"],
            "transcript_read": False,
        }
    snapshot = client.snapshot(session)
    workspaces = snapshot["workspaces"]
    _find_workspace(
        workspaces,
        payload["workspace"]["id"],
        payload["workspace"]["label"],
    )
    tabs = [
        item
        for item in snapshot["tabs"]
        if item.get("workspace_id") == payload["workspace"]["id"]
    ]
    panes = [
        item
        for item in snapshot["panes"]
        if item.get("workspace_id") == payload["workspace"]["id"]
    ]
    snapshot_blockers: list[str] = []
    if doctor_result["socket"] != payload["session"]["socket"]:
        snapshot_blockers.append("server_socket_drift")
    if snapshot.get("version") != payload["session"]["version"]:
        snapshot_blockers.append("snapshot_version_drift")
    if snapshot.get("protocol") != payload["session"]["protocol"]:
        snapshot_blockers.append("snapshot_protocol_drift")
    if lease_payload is None:
        label_matches = [
            item for item in tabs if item.get("label") == payload["owned_label"]
        ]
        return {
            "schema": "herdr-puppet.status.v1",
            "result": "ok" if not label_matches and not snapshot_blockers else "blocked",
            "run_id": payload["run_id"],
            "state": "planned",
            "blockers": snapshot_blockers
            + ([] if not label_matches else ["owned_label_already_exists"]),
            "workspace": payload["workspace"],
            "owned_label": payload["owned_label"],
            "transcript_read": False,
        }

    tab_matches = [
        item
        for item in tabs
        if item.get("tab_id") == payload["tab_id"]
        and item.get("workspace_id") == payload["workspace"]["id"]
    ]
    pane_matches = [
        item
        for item in panes
        if item.get("pane_id") == payload["pane_id"]
        and item.get("tab_id") == payload["tab_id"]
        and item.get("workspace_id") == payload["workspace"]["id"]
    ]
    blockers: list[str] = list(snapshot_blockers)
    if len(tab_matches) != 1:
        blockers.append("leased_tab_missing_or_ambiguous")
    elif tab_matches[0].get("label") != payload["owned_label"]:
        blockers.append("leased_tab_label_drift")
    if len(pane_matches) != 1:
        blockers.append("leased_pane_missing_or_ambiguous")
    elif pane_matches[0].get("terminal_id") != payload["terminal_id"]:
        blockers.append("leased_terminal_drift")
    process: dict[str, Any] | None = None
    if not blockers:
        process_info = client.process_info(session, payload["pane_id"])
        try:
            process = _expected_ssh_process(
                process_info,
                payload["ssh"]["target"],
            )
        except HerdrPuppetError as exc:
            blockers.append(exc.code)
        if process and (
            process.get("pid") != payload["ssh"]["pid"]
            or process.get("argv") != payload["ssh"]["argv"]
        ):
            blockers.append("leased_ssh_process_drift")
    return {
        "schema": "herdr-puppet.status.v1",
        "result": "ok" if not blockers else "blocked",
        "run_id": payload["run_id"],
        "state": payload["state"],
        "blockers": blockers,
        "workspace_id": payload["workspace"]["id"],
        "tab_id": payload["tab_id"],
        "pane_id": payload["pane_id"],
        "terminal_id": payload["terminal_id"],
        "ssh_pid": process.get("pid") if process else None,
        "next_seq": payload["next_seq"],
        "transcript_read": False,
    }


def maintenance_checkpoint(
    client: HerdrClient,
    *,
    lease_payload: dict[str, Any],
    run_root: Path,
) -> dict[str, Any]:
    validate_lease(lease_payload)
    require_initialized_journal(
        run_root,
        run_id=lease_payload["run_id"],
    )
    session = lease_payload["session"]["name"]
    doctor_result = doctor(client, session)
    blockers: list[str] = list(doctor_result["blockers"])
    tab_state = "unverified"
    pane_state = "unverified"
    terminal_state = "unverified"
    ssh_state = "unverified"

    if doctor_result["result"] == "ok":
        snapshot = client.snapshot(session)
        if doctor_result["socket"] != lease_payload["session"]["socket"]:
            blockers.append("server_socket_drift")
        if snapshot.get("version") != lease_payload["session"]["version"]:
            blockers.append("snapshot_version_drift")
        if snapshot.get("protocol") != lease_payload["session"]["protocol"]:
            blockers.append("snapshot_protocol_drift")

        workspace_matches = [
            item
            for item in snapshot["workspaces"]
            if item.get("workspace_id") == lease_payload["workspace"]["id"]
        ]
        if (
            len(workspace_matches) != 1
            or workspace_matches[0].get("label")
            != lease_payload["workspace"]["label"]
        ):
            blockers.append("workspace_capability_mismatch")

        tab_matches = [
            item
            for item in snapshot["tabs"]
            if item.get("tab_id") == lease_payload["tab_id"]
        ]
        pane_matches = [
            item
            for item in snapshot["panes"]
            if item.get("pane_id") == lease_payload["pane_id"]
        ]

        if not tab_matches:
            tab_state = "missing"
        elif len(tab_matches) > 1:
            tab_state = "duplicate"
            blockers.append("leased_tab_duplicate")
        elif tab_matches[0].get("workspace_id") != lease_payload["workspace"]["id"]:
            tab_state = "moved"
            blockers.append("leased_tab_moved")
        elif tab_matches[0].get("label") != lease_payload["owned_label"]:
            tab_state = "label_drift"
            blockers.append("leased_tab_label_drift")
        else:
            tab_state = "present"

        if not pane_matches:
            pane_state = "missing"
        elif len(pane_matches) > 1:
            pane_state = "duplicate"
            blockers.append("leased_pane_duplicate")
        elif (
            pane_matches[0].get("workspace_id")
            != lease_payload["workspace"]["id"]
            or pane_matches[0].get("tab_id") != lease_payload["tab_id"]
        ):
            pane_state = "moved"
            blockers.append("leased_pane_moved")
        elif pane_matches[0].get("terminal_id") != lease_payload["terminal_id"]:
            pane_state = "present"
            terminal_state = "drifted"
            blockers.append("leased_terminal_drift")
        else:
            pane_state = "present"
            terminal_state = "present"

        exact_structure_present = (
            tab_state == "present"
            and pane_state == "present"
            and terminal_state == "present"
        )
        if exact_structure_present and not blockers:
            try:
                process = _expected_ssh_process(
                    client.process_info(session, lease_payload["pane_id"]),
                    lease_payload["ssh"]["target"],
                )
            except HerdrPuppetError as exc:
                blockers.append(exc.code)
            else:
                if (
                    process.get("pid") != lease_payload["ssh"]["pid"]
                    or process.get("argv") != lease_payload["ssh"]["argv"]
                ):
                    blockers.append("leased_ssh_process_drift")
                    ssh_state = "drifted"
                else:
                    ssh_state = "present"

    stale_structure = (
        doctor_result["result"] == "ok"
        and not blockers
        and tab_state == "missing"
        and pane_state == "missing"
    )
    exact_live_structure = (
        doctor_result["result"] == "ok"
        and not blockers
        and tab_state == "present"
        and pane_state == "present"
        and terminal_state == "present"
        and ssh_state == "present"
    )
    if stale_structure:
        classification = "stale"
    elif exact_live_structure:
        classification = lease_payload["state"]
    else:
        classification = "ambiguous"

    cleanup_recorded = lease_payload.get("cleanup_state") == "closed"
    maintenance_candidate = (
        classification == "ambiguous"
        or classification == "stale"
        and not cleanup_recorded
    )
    recommended_action = (
        "none"
        if classification == "stale" and cleanup_recorded
        else
        "preserve_lease"
        if classification == "stale" and lease_payload["state"] == "active"
        else "owner_specific_cleanup_review"
        if classification == "stale"
        else "human_review"
        if classification == "ambiguous"
        else "retain_or_route_exact_cleanup"
        if classification == "preserved"
        else "continue_bounded_run"
    )
    resources = {
        "tab": {"id": lease_payload["tab_id"], "state": tab_state},
        "pane": {"id": lease_payload["pane_id"], "state": pane_state},
        "terminal": {
            "id": lease_payload["terminal_id"],
            "state": terminal_state,
        },
        "ssh": {
            "pid": lease_payload["ssh"]["pid"],
            "state": ssh_state,
        },
    }
    append_event(
        run_root,
        make_event(
            lease_payload["run_id"],
            "maintenance.checkpoint",
            "repair" if maintenance_candidate else "observed",
            data={
                "classification": classification,
                "lease_state": lease_payload["state"],
                "resources": resources,
                "blockers": blockers,
                "maintenance_candidate": maintenance_candidate,
                "recommended_action": recommended_action,
                "cleanup_authorized": False,
                "cleanup_performed": False,
                "herdr_mutated": False,
                "transcript_read": False,
            },
        ),
    )
    return {
        "schema": "herdr-puppet.maintenance-checkpoint.v1",
        "result": "ok",
        "run_id": lease_payload["run_id"],
        "classification": classification,
        "lease_state": lease_payload["state"],
        "resources": resources,
        "blockers": blockers,
        "maintenance_candidate": maintenance_candidate,
        "recommended_action": recommended_action,
        "cleanup_authorized": False,
        "cleanup_performed": False,
        "herdr_mutated": False,
        "transcript_read": False,
    }


def cleanup_preserved_tab(
    client: HerdrClient,
    *,
    lease_payload: dict[str, Any],
    lease_path: Path,
    run_root: Path,
    confirm_tab_id: str,
    allow_live_cleanup: bool,
) -> dict[str, Any]:
    validate_lease(lease_payload)
    if lease_payload["state"] != "preserved":
        raise HerdrPuppetError(
            "cleanup_lease_not_preserved",
            "Exact tab cleanup requires a preserved lease.",
        )
    if not allow_live_cleanup:
        raise HerdrPuppetError(
            "live_cleanup_not_authorized",
            "The command flag must explicitly authorize live tab cleanup.",
        )
    if confirm_tab_id != lease_payload["tab_id"]:
        raise HerdrPuppetError(
            "cleanup_tab_confirmation_mismatch",
            "The confirmed tab ID does not match the exact leased tab.",
            details={
                "confirmed_tab_id": confirm_tab_id,
                "leased_tab_id": lease_payload["tab_id"],
            },
        )
    require_initialized_journal(
        run_root,
        run_id=lease_payload["run_id"],
    )
    current = load_json(lease_path)
    _assert_wait_lease_revision(lease_payload, current)
    if current["state"] != "preserved":
        raise HerdrPuppetError(
            "cleanup_lease_not_preserved",
            "The on-disk lease is not preserved.",
        )

    inventory = maintenance_checkpoint(
        client,
        lease_payload=current,
        run_root=run_root,
    )
    if inventory["classification"] == "ambiguous":
        raise HerdrPuppetError(
            "cleanup_identity_ambiguous",
            "Exact tab cleanup requires an unambiguous live or absent identity.",
            details={"blockers": inventory["blockers"]},
        )

    already_absent = inventory["classification"] == "stale"
    if current.get("cleanup_state") == "closed":
        if already_absent:
            if not client.wait_pid_absence(current["ssh"]["pid"]):
                raise HerdrPuppetError(
                    "cleanup_ssh_pid_absence_not_verified",
                    "The leased foreground SSH PID is not absent.",
                    details={"ssh_pid": current["ssh"]["pid"]},
                )
            refresh_state(run_root, current)
            return {
                "schema": "herdr-puppet.cleanup-preserved-tab.v1",
                "result": "ok",
                "run_id": current["run_id"],
                "tab_id": current["tab_id"],
                "pane_id": current["pane_id"],
                "cleanup_performed": False,
                "already_closed": True,
                "absence_verified": True,
                "ssh_pid_absence_verified": True,
                "transcript_read": False,
            }
        raise HerdrPuppetError(
            "cleanup_record_conflict",
            "A lease recorded as closed resolved to a live exact identity.",
        )

    append_event(
        run_root,
        make_event(
            current["run_id"],
            "cleanup.requested",
            "observed",
            data={
                "tab_id": current["tab_id"],
                "pane_id": current["pane_id"],
                "confirmed_tab_id": confirm_tab_id,
                "cleanup_authorized": True,
                "transcript_read": False,
            },
        ),
    )

    cleanup_performed = False
    if not already_absent:
        client.close_tab(
            current["session"]["name"],
            current["tab_id"],
        )
        cleanup_performed = True
        after = client.snapshot(current["session"]["name"])
        tab_matches = [
            item
            for item in after["tabs"]
            if item.get("tab_id") == current["tab_id"]
        ]
        pane_matches = [
            item
            for item in after["panes"]
            if item.get("pane_id") == current["pane_id"]
        ]
        if tab_matches or pane_matches:
            raise HerdrPuppetError(
                "cleanup_close_not_verified",
                "Herdr accepted tab close but the exact leased identity remains.",
                details={
                    "tab_present": bool(tab_matches),
                    "pane_present": bool(pane_matches),
                },
            )
    if not client.wait_pid_absence(current["ssh"]["pid"]):
        raise HerdrPuppetError(
            "cleanup_ssh_pid_absence_not_verified",
            "The leased foreground SSH PID is not absent after tab cleanup.",
            details={"ssh_pid": current["ssh"]["pid"]},
        )

    updated = json.loads(json.dumps(current))
    updated["cleanup_state"] = "closed"
    updated["cleanup_verified_at"] = now()
    updated["cleanup_reconciled_absence"] = already_absent
    atomic_json(lease_path, updated)
    append_event(
        run_root,
        make_event(
            updated["run_id"],
            "cleanup.closed",
            "ok",
            data={
                "tab_id": updated["tab_id"],
                "pane_id": updated["pane_id"],
                "cleanup_performed": cleanup_performed,
                "already_absent": already_absent,
                "absence_verified": True,
                "ssh_pid_absence_verified": True,
                "transcript_read": False,
            },
        ),
    )
    refresh_state(run_root, updated)
    return {
        "schema": "herdr-puppet.cleanup-preserved-tab.v1",
        "result": "ok",
        "run_id": updated["run_id"],
        "tab_id": updated["tab_id"],
        "pane_id": updated["pane_id"],
        "cleanup_performed": cleanup_performed,
        "already_closed": already_absent,
        "absence_verified": True,
        "ssh_pid_absence_verified": True,
        "transcript_read": False,
    }


def _live_gate(plan_payload: dict[str, Any], allow_live: bool) -> None:
    if not allow_live or plan_payload["safety"].get("live_mutation_authorized") is not True:
        raise HerdrPuppetError(
            "live_qualification_not_authorized",
            "Both the plan capability and command flag must authorize live qualification.",
        )


def create_qualification_tab(
    client: HerdrClient,
    *,
    plan_payload: dict[str, Any],
    lease_path: Path,
    allow_live: bool,
    settle_seconds: float = 10.0,
    run_root: Path | None = None,
) -> dict[str, Any]:
    validate_plan(plan_payload)
    _live_gate(plan_payload, allow_live)
    if run_root is not None:
        require_initialized_journal(
            run_root,
            run_id=plan_payload["run_id"],
        )
    before_status = structural_status(client, plan_payload=plan_payload)
    if before_status["result"] != "ok":
        raise HerdrPuppetError(
            "prelaunch_status_blocked",
            "Structural status blocked tab creation.",
            details={"blockers": before_status["blockers"]},
        )
    if lease_path.exists():
        raise HerdrPuppetError(
            "lease_path_exists",
            "Refusing to overwrite an existing lease.",
            details={"lease_path": str(lease_path)},
        )
    session = plan_payload["session"]["name"]
    workspace_id = plan_payload["workspace"]["id"]
    before_tabs = {
        item.get("tab_id")
        for item in client.snapshot(session)["tabs"]
        if item.get("workspace_id") == workspace_id and item.get("tab_id")
    }
    client.create_tab(session, workspace_id, plan_payload["owned_label"])

    deadline = time.monotonic() + settle_seconds
    new_tab: dict[str, Any] | None = None
    new_pane: dict[str, Any] | None = None
    ssh_process: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        snapshot = client.snapshot(session)
        tabs = [
            item
            for item in snapshot["tabs"]
            if item.get("workspace_id") == workspace_id
        ]
        candidates = [
            item
            for item in tabs
            if item.get("tab_id") not in before_tabs
            and item.get("label") == plan_payload["owned_label"]
            and item.get("workspace_id") == workspace_id
        ]
        if len(candidates) == 1:
            panes = [
                item
                for item in snapshot["panes"]
                if item.get("tab_id") == candidates[0].get("tab_id")
                and item.get("workspace_id") == workspace_id
            ]
            if len(panes) == 1:
                try:
                    process_info = client.process_info(session, panes[0]["pane_id"])
                    ssh_process = _expected_ssh_process(
                        process_info,
                        plan_payload["expected_ssh_target"],
                    )
                except HerdrPuppetError:
                    time.sleep(0.2)
                    continue
                new_tab = candidates[0]
                new_pane = panes[0]
                break
        time.sleep(0.2)
    if new_tab is None or new_pane is None or ssh_process is None:
        raise HerdrPuppetError(
            "candidate_tab_not_qualified",
            "The new tab did not resolve to one expected SSH pane in time.",
        )
    lease = {
        "schema": "herdr-puppet.lease.v1",
        "state": "active",
        "run_id": plan_payload["run_id"],
        "harness": plan_payload["harness"],
        "session": plan_payload["session"],
        "workspace": plan_payload["workspace"],
        "owned_label": plan_payload["owned_label"],
        "tab_id": new_tab["tab_id"],
        "pane_id": new_pane["pane_id"],
        "terminal_id": new_pane["terminal_id"],
        "ssh": {
            "pid": ssh_process["pid"],
            "argv": ssh_process["argv"],
            "target": plan_payload["expected_ssh_target"],
        },
        "next_seq": 1,
        "source": plan_payload["source"],
        "proof_root": plan_payload["proof_root"],
    }
    validate_lease(lease)
    atomic_json(lease_path, lease)
    if run_root is not None:
        append_event(
            run_root,
            make_event(
                lease["run_id"],
                "qualification.tab-created",
                "ok",
                data={
                    "tab_id": lease["tab_id"],
                    "pane_id": lease["pane_id"],
                    "terminal_id": lease["terminal_id"],
                    "ssh_pid": lease["ssh"]["pid"],
                },
            ),
        )
    return lease


def qualification_send(
    client: HerdrClient,
    *,
    lease_payload: dict[str, Any],
    lease_path: Path,
    seq: int,
    text: str,
    allow_live: bool,
    run_root: Path | None = None,
) -> dict[str, Any]:
    validate_lease(lease_payload)
    if not allow_live:
        raise HerdrPuppetError(
            "live_qualification_not_authorized",
            "The command flag must authorize live qualification.",
        )
    if lease_payload["state"] != "active":
        raise HerdrPuppetError("lease_not_active", "The lease is not active.")
    if seq != lease_payload["next_seq"]:
        raise HerdrPuppetError(
            "send_sequence_mismatch",
            "Send sequence is stale, skipped, duplicate, or replayed.",
            details={"expected": lease_payload["next_seq"], "received": seq},
        )
    status = structural_status(client, lease_payload=lease_payload)
    if status["result"] != "ok":
        raise HerdrPuppetError(
            "presend_status_blocked",
            "Structural status blocked the send.",
            details={"blockers": status["blockers"]},
        )
    socket_path = lease_payload["session"]["socket"]
    pane_id = lease_payload["pane_id"]
    client.run_input(socket_path, pane_id, text)
    digest = sha256_text(text)
    updated = json.loads(json.dumps(lease_payload))
    updated["next_seq"] = seq + 1
    atomic_json(lease_path, updated)
    if run_root is not None:
        append_event(
            run_root,
            make_event(
                updated["run_id"],
                "qualification.send",
                "ok",
                seq=seq,
                prompt_sha256=digest,
                data={
                    "pane_id": pane_id,
                    "input_request": "pane.send_input",
                    "transport_acknowledged": True,
                    "acceptance_scope": "herdr_pane_input_only",
                    "outcome": "pane_input_accepted",
                    "harness_readiness": "unverified",
                    "harness_acceptance": "unverified",
                },
            ),
        )
    return {
        "schema": "herdr-puppet.qualification-send.v1",
        "result": "ok",
        "run_id": updated["run_id"],
        "pane_id": pane_id,
        "seq": seq,
        "next_seq": updated["next_seq"],
        "prompt_sha256": digest,
        "transport_acknowledged": True,
        "acceptance_scope": "herdr_pane_input_only",
        "outcome": "pane_input_accepted",
        "harness_readiness": "unverified",
        "harness_acceptance": "unverified",
        "prompt_persisted": False,
        "transcript_read": False,
    }


def qualification_reconcile_send(
    client: HerdrClient,
    *,
    lease_payload: dict[str, Any],
    lease_path: Path,
    seq: int,
    text: str,
    evidence: str,
    confirm_applied: bool,
    run_root: Path | None = None,
) -> dict[str, Any]:
    validate_lease(lease_payload)
    if lease_payload["state"] != "active":
        raise HerdrPuppetError("lease_not_active", "The lease is not active.")
    if not confirm_applied:
        raise HerdrPuppetError(
            "partial_send_not_confirmed",
            "Reconciliation requires explicit evidence that the text was applied.",
        )
    if seq != lease_payload["next_seq"]:
        raise HerdrPuppetError(
            "send_sequence_mismatch",
            "Send sequence is stale, skipped, duplicate, or replayed.",
            details={"expected": lease_payload["next_seq"], "received": seq},
        )
    if not evidence.strip():
        raise HerdrPuppetError(
            "partial_send_evidence_missing",
            "Reconciliation requires a concise structural evidence label.",
        )
    status = structural_status(client, lease_payload=lease_payload)
    if status["result"] != "ok":
        raise HerdrPuppetError(
            "reconcile_status_blocked",
            "Structural status blocked partial-send reconciliation.",
            details={"blockers": status["blockers"]},
        )
    digest = sha256_text(text)
    updated = json.loads(json.dumps(lease_payload))
    updated["next_seq"] = seq + 1
    atomic_json(lease_path, updated)
    if run_root is not None:
        append_event(
            run_root,
            make_event(
                updated["run_id"],
                "qualification.send-reconciled",
                "observed",
                seq=seq,
                prompt_sha256=digest,
                data={
                    "pane_id": updated["pane_id"],
                    "evidence": evidence,
                    "herdr_mutated": False,
                },
            ),
        )
    return {
        "schema": "herdr-puppet.qualification-send-reconciled.v1",
        "result": "ok",
        "run_id": updated["run_id"],
        "pane_id": updated["pane_id"],
        "seq": seq,
        "next_seq": updated["next_seq"],
        "prompt_sha256": digest,
        "evidence": evidence,
        "herdr_mutated": False,
        "transcript_read": False,
    }


def qualification_token_probe(
    client: HerdrClient,
    *,
    lease_payload: dict[str, Any],
    nonce: str,
    allow_live: bool,
    lines: int = 40,
    timeout_ms: int = 30_000,
    run_root: Path | None = None,
) -> dict[str, Any]:
    validate_lease(lease_payload)
    if lease_payload["state"] != "active":
        raise HerdrPuppetError("lease_not_active", "The lease is not active.")
    if not allow_live:
        raise HerdrPuppetError(
            "live_qualification_not_authorized",
            "The command flag must authorize the qualification token probe.",
        )
    if lines < 1 or lines > 80:
        raise HerdrPuppetError(
            "invalid_probe_window",
            "Qualification token probe lines must be between 1 and 80.",
        )
    if timeout_ms < 1 or timeout_ms > 300_000:
        raise HerdrPuppetError(
            "invalid_probe_timeout",
            "Qualification token probe timeout must be between 1 and 300000 ms.",
        )
    status = structural_status(client, lease_payload=lease_payload)
    if status["result"] != "ok":
        raise HerdrPuppetError(
            "preprobe_status_blocked",
            "Structural status blocked the token probe.",
            details={"blockers": status["blockers"]},
        )
    wait_result = client.wait_output(
        lease_payload["session"]["name"],
        lease_payload["pane_id"],
        nonce,
        lines,
        timeout_ms,
    )
    matched = (
        wait_result is not None
        and wait_result.get("type") == "output_matched"
    )
    revision = wait_result.get("revision") if matched else None
    timeout_source = (
        wait_result.get("timeout_source")
        if wait_result is not None
        and wait_result.get("type") == "output_timeout"
        else None
    )
    nonce_digest = hashlib.sha256(nonce.encode("utf-8")).hexdigest()
    if run_root is not None:
        append_event(
            run_root,
            make_event(
                lease_payload["run_id"],
                "qualification.token-probe",
                "ok" if matched else "failed",
                nonce_sha256=nonce_digest,
                data={
                    "pane_id": lease_payload["pane_id"],
                    "matched": matched,
                    "revision": revision,
                    "timeout_source": timeout_source,
                    "wait": "herdr.wait.output",
                },
            ),
        )
    return {
        "schema": "herdr-puppet.qualification-token-probe.v1",
        "result": "ok" if matched else "not_matched",
        "run_id": lease_payload["run_id"],
        "pane_id": lease_payload["pane_id"],
        "matched": matched,
        "nonce_sha256": nonce_digest,
        "pane_text_emitted": False,
        "bounded_lines": lines,
        "timeout_ms": timeout_ms,
        "timeout_source": timeout_source,
        "revision": revision,
    }


def _assert_wait_lease_revision(
    expected: dict[str, Any],
    current: dict[str, Any],
) -> None:
    validate_lease(current)
    drifted = [
        field
        for field in LEASE_WAIT_REVISION_FIELDS
        if current.get(field) != expected.get(field)
    ]
    if drifted:
        raise HerdrPuppetError(
            "lease_changed_during_wait",
            "The lease changed while the checkpoint wait was active.",
            details={"fields": drifted},
        )


def _reject_terminal_nonce_replay(run_root: Path, nonce_digest: str) -> None:
    for event in read_events(run_root):
        checkpoint = (
            event.get("data", {}).get("checkpoint")
            if isinstance(event.get("data"), dict)
            else None
        )
        if (
            event.get("kind") == "qualification.beacon"
            and event.get("nonce_sha256") == nonce_digest
            and checkpoint in {"ACTION_REQUIRED", "DONE"}
        ):
            raise HerdrPuppetError(
                "terminal_beacon_nonce_reused",
                "A terminal checkpoint nonce may not be waited again.",
            )


def qualification_beacon_wait(
    client: HerdrClient,
    *,
    lease_payload: dict[str, Any],
    lease_path: Path,
    nonce: str,
    allow_live: bool,
    lines: int = 40,
    timeout_ms: int = 300_000,
    run_root: Path,
) -> dict[str, Any]:
    validate_lease(lease_payload)
    if lease_payload["state"] != "active":
        raise HerdrPuppetError("lease_not_active", "The lease is not active.")
    if not allow_live:
        raise HerdrPuppetError(
            "live_qualification_not_authorized",
            "The command flag must authorize the qualification beacon wait.",
        )
    if not re.fullmatch(r"[A-Za-z0-9._:-]{8,128}", nonce):
        raise HerdrPuppetError(
            "invalid_beacon_nonce",
            "Beacon nonce must be 8-128 safe identifier characters.",
        )
    if lines < 1 or lines > 80:
        raise HerdrPuppetError(
            "invalid_probe_window",
            "Qualification beacon lines must be between 1 and 80.",
        )
    if timeout_ms < 1 or timeout_ms > 3_600_000:
        raise HerdrPuppetError(
            "invalid_beacon_timeout",
            "Qualification beacon timeout must be between 1 and 3600000 ms.",
        )
    require_initialized_journal(
        run_root,
        run_id=lease_payload["run_id"],
    )
    nonce_digest = sha256_text(nonce)
    _reject_terminal_nonce_replay(run_root, nonce_digest)
    current_before_wait = load_json(lease_path)
    _assert_wait_lease_revision(lease_payload, current_before_wait)
    if current_before_wait["state"] != "active":
        raise HerdrPuppetError("lease_not_active", "The lease is not active.")
    status = structural_status(client, lease_payload=lease_payload)
    if status["result"] != "ok":
        raise HerdrPuppetError(
            "prewait_status_blocked",
            "Structural status blocked the beacon wait.",
            details={"blockers": status["blockers"]},
        )
    pattern = (
        r"^HERDR_PUPPET_("
        + "|".join(CHECKPOINT_KINDS)
        + r") "
        + re.escape(nonce)
        + r"$"
    )
    wait_result = client.wait_output(
        lease_payload["session"]["name"],
        lease_payload["pane_id"],
        pattern,
        lines,
        timeout_ms,
        regex=True,
    )
    matched_line = (
        wait_result.get("matched_line")
        if wait_result is not None
        and wait_result.get("type") == "output_matched"
        else None
    )
    match = re.fullmatch(pattern, matched_line) if isinstance(matched_line, str) else None
    checkpoint = match.group(1) if match else None
    revision = (
        wait_result.get("revision")
        if wait_result is not None
        and wait_result.get("type") == "output_matched"
        else None
    )
    timeout_source = (
        wait_result.get("timeout_source")
        if wait_result is not None
        and wait_result.get("type") == "output_timeout"
        else None
    )
    result = (
        "human_gate"
        if checkpoint == "ACTION_REQUIRED"
        else "ok"
        if checkpoint == "DONE"
        else "observed"
        if checkpoint == "STATUS"
        else "failed"
    )
    current_after_wait = load_json(lease_path)
    _assert_wait_lease_revision(lease_payload, current_after_wait)
    append_event(
        run_root,
        make_event(
            lease_payload["run_id"],
            "qualification.beacon",
            result,
            nonce_sha256=nonce_digest,
            data={
                "pane_id": lease_payload["pane_id"],
                "checkpoint": checkpoint,
                "revision": revision,
                "timeout_source": timeout_source,
                "wait": "herdr.wait.output.regex",
            },
        ),
    )
    auto_preserved = checkpoint in {"ACTION_REQUIRED", "DONE"}
    if auto_preserved:
        preserve_lease(
            lease_payload=current_after_wait,
            lease_path=lease_path,
            reason=(
                "human_gate"
                if checkpoint == "ACTION_REQUIRED"
                else "milestone_complete"
            ),
            run_root=run_root,
        )
    return {
        "schema": "herdr-puppet.qualification-beacon-wait.v1",
        "result": result if checkpoint else "not_matched",
        "run_id": lease_payload["run_id"],
        "pane_id": lease_payload["pane_id"],
        "checkpoint": checkpoint,
        "matched": checkpoint is not None,
        "nonce_sha256": nonce_digest,
        "pane_text_emitted": False,
        "bounded_lines": lines,
        "timeout_ms": timeout_ms,
        "timeout_source": timeout_source,
        "revision": revision,
        "auto_preserved": auto_preserved,
        "lease_state": (
            "preserved" if auto_preserved else current_after_wait["state"]
        ),
    }


def preserve_lease(
    *,
    lease_payload: dict[str, Any],
    lease_path: Path,
    reason: str,
    run_root: Path | None = None,
) -> dict[str, Any]:
    validate_lease(lease_payload)
    if reason not in PRESERVE_REASONS:
        raise HerdrPuppetError(
            "invalid_preserve_reason",
            "Lease preservation requires a supported bounded reason.",
            details={"supported": sorted(PRESERVE_REASONS)},
        )
    if lease_payload["state"] == "preserved":
        return {
            "schema": "herdr-puppet.lease-preserve.v1",
            "result": "ok",
            "run_id": lease_payload["run_id"],
            "state": "preserved",
            "reason": lease_payload.get("preserved_reason", reason),
            "already_preserved": True,
            "herdr_mutated": False,
        }
    updated = json.loads(json.dumps(lease_payload))
    updated["state"] = "preserved"
    updated["preserved_reason"] = reason
    updated["preserved_at"] = now()
    atomic_json(lease_path, updated)
    if run_root is not None:
        append_event(
            run_root,
            make_event(
                updated["run_id"],
                "lease.preserved",
                "human_gate" if reason == "human_gate" else "observed",
                data={"reason": reason, "herdr_mutated": False},
            ),
        )
    return {
        "schema": "herdr-puppet.lease-preserve.v1",
        "result": "ok",
        "run_id": updated["run_id"],
        "state": "preserved",
        "reason": reason,
        "already_preserved": False,
        "herdr_mutated": False,
    }
