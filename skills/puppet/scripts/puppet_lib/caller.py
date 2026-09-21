"""Caller-facing Puppet contract: blockers, cursor, and distinct outcomes."""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

from .errors import PuppetError


CALLER_BLOCKER_SCHEMA = "puppet.caller-blocker/v1"
PROGRESS_CURSOR_SCHEMA = "puppet.progress-cursor/v1"
CALLER_OUTCOME_SCHEMA = "puppet.caller-outcome/v1"
FINAL_OUTCOME_SCHEMA = "puppet.final-outcome/v1"
TRANSPORT_BINDING_SCHEMA = "puppet.transport-binding/v1"

WORKER_COMPLETION_NONE = "none"
WORKER_COMPLETION_REPORTED = "reported"
CONTROLLER_ACCEPTANCE_NONE = "none"
CONTROLLER_ACCEPTANCE_ACCEPTED = "accepted"
CONTROLLER_ACCEPTANCE_BLOCKED = "blocked"
CONTROLLER_ACCEPTANCE_FAILED = "failed"
HALT_NONE = "none"
HALT_CONFIRMED = "confirmed"

_BLOCKER_FIELDS = (
    "schema",
    "code",
    "changed",
    "remedy",
    "detail",
    "pid",
    "kernel_birth_id",
    "pane",
)
_MAX_BLOCKER_TEXT = 400
_MAX_SUMMARY = 240

_REMEDIES = {
    "process_identity_unavailable": (
        "halt only the exact recorded pid and kernel birth if this controller "
        "owns them; otherwise stop and preserve. Re-run doctor after the stale "
        "or foreign process is gone. Do not reuse a PID."
    ),
    "identity_mismatch": (
        "re-run doctor; if the recorded birth or pane drifted, halt the exact "
        "owned target or recover the exact lease. Do not reuse a stale PID."
    ),
    "qualification_receipt_invalid": (
        "run adapter_lab.py requalify --target <target> --manifest <manifest> "
        "--mapping <mapping>; live probe and qualify only after an explicit "
        "operator gate"
    ),
    "transport_unsupported": (
        "bind transport=tmux, transport=agy-print, transport=cursor-acp, or "
        "transport=antigravity-acp; herdr and generic acp remain explicitly "
        "unsupported with no fallback"
    ),
    "transport_target_mismatch": (
        "bind cursor-acp only for the cursor target and antigravity-acp only "
        "for the agy target; generic acp remains unsupported for every target "
        "and never falls back to tmux or agy-print"
    ),
    "transport_unavailable": (
        "restore the bound transport or its structured observer with no "
        "fallback to another named transport"
    ),
    "tmux_unavailable": (
        "install tmux and re-run doctor; do not select herdr, acp, or "
        "agy-print as a fallback"
    ),
    "model_observation_selector_only": (
        "prove the executed model from runtime, process, or session "
        "metadata; a requested selector is not observed model proof"
    ),
    "model_observation_mismatch": (
        "re-run doctor against the observed runtime model; do not treat "
        "the requested selector as the executed model"
    ),
    "workspace_identity_mismatch": (
        "bind the exact checkout path, branch, head, and tree; a path "
        "alone is not workspace proof"
    ),
    "session_identity_mismatch": (
        "resume only the matching session and conversation identity; do "
        "not resume from a selector or path alone"
    ),
    "result_identity_mismatch": (
        "prove the worker terminal result from structured ACP runtime "
        "metadata; do not treat a requested selector as the result"
    ),
    "process_identity_mismatch": (
        "halt only the exact recorded pid and kernel birth if this "
        "controller owns them; otherwise stop and preserve"
    ),
    "process_tree_unowned": (
        "halt only the owned pid, birth, and recorded children; do not "
        "signal an unrelated process"
    ),
    "subscription_profile_required": (
        "pass --profile-root <private-profile> for this non-AGY target"
    ),
    "subscription_profile_invalid": (
        "repair or re-init the exact private profile, then re-run "
        "profile-status and doctor"
    ),
    "subscription_profile_unauthenticated": (
        "complete the human-gated login for the exact private profile, then "
        "re-run profile-status and doctor"
    ),
    "agy_private_profile_unsupported": (
        "omit --profile-root for AGY; AGY does not isolate a private profile"
    ),
    "regular_session_required": (
        "set session_profile=regular; other session profiles remain deferred"
    ),
    "model_effort_deferred": (
        "omit requested_model and requested_effort; observed model proof is "
        "a later stage"
    ),
    "yolo_mapping_incomplete": (
        "complete the exact YOLO, sandbox-off, and argv-free prompt mapping "
        "before launch"
    ),
    "qualification_required": (
        "run adapter_lab.py requalify --target <target> --manifest <manifest> "
        "--mapping <mapping>; live probe and qualify only after an explicit "
        "operator gate"
    ),
    "worktree_dirty": "commit or reset the candidate worktree, then re-run doctor",
    "branch_mismatch": "check out the contract branch, then re-run doctor",
    "executable_unavailable": (
        "restore the resolved non-symlink executable named by the manifest"
    ),
    "executable_fingerprint_drifted": (
        "re-census the current executable and requalify the drifted target"
    ),
    "proof_root_unwritable": "make the proof root writable by the current UID",
    "state_root_unwritable": "make the state root writable by the current UID",
    "state_root_not_private": "chmod the state root to current-UID mode 0700",
    "viewer_root_invalid": "remove or recreate the state-root views directory",
    "viewer_root_not_private": "chmod the views directory to current-UID mode 0700",
    "active_target_population": (
        "halt only an exact owned same-target process, or supply the exact "
        "parallel isolation override. Do not signal a foreign PID."
    ),
    "mismatched_target_population": (
        "stop and preserve; a live same-name process has a different "
        "executable identity"
    ),
    "grok_launch_authority": (
        "complete Grok paired qualification before public launch"
    ),
}


def _bounded_text(value: Any, *, maximum: int = _MAX_BLOCKER_TEXT) -> str:
    if not isinstance(value, str):
        value = str(value)
    cleaned = value.replace("\x00", "").replace("\r", " ").replace("\n", " ").strip()
    if len(cleaned) > maximum:
        return cleaned[: maximum - 3] + "..."
    return cleaned


def _optional_pid(value: Any) -> Optional[int]:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int) and value > 1:
        return value
    return None


def _optional_text(value: Any, *, maximum: int = 200) -> Optional[str]:
    if value is None:
        return None
    text = _bounded_text(value, maximum=maximum)
    return text or None


def make_blocker(
    *,
    code: str,
    detail: str,
    changed: Optional[str] = None,
    remedy: Optional[str] = None,
    pid: Any = None,
    kernel_birth_id: Any = None,
    pane: Any = None,
) -> Dict[str, Any]:
    """Return one body-safe, actionable caller blocker."""

    code = _bounded_text(code, maximum=80)
    detail = _bounded_text(detail)
    return {
        "schema": CALLER_BLOCKER_SCHEMA,
        "code": code,
        "changed": _bounded_text(changed or detail),
        "remedy": _bounded_text(remedy or _REMEDIES.get(code) or "stop and preserve"),
        "detail": detail,
        "pid": _optional_pid(pid),
        "kernel_birth_id": _optional_text(kernel_birth_id),
        "pane": _optional_text(pane, maximum=32),
    }


def doctor_blocker(code: str, detail: str, **identity: Any) -> Dict[str, Any]:
    return make_blocker(code=code, detail=detail, **identity)


def blocker_from_error(
    exc: BaseException,
    *,
    pid: Any = None,
    kernel_birth_id: Any = None,
    pane: Any = None,
) -> Dict[str, Any]:
    existing = getattr(exc, "blocker", None)
    if isinstance(existing, Mapping) and existing.get("schema") == CALLER_BLOCKER_SCHEMA:
        blocker = dict(existing)
        if blocker.get("pid") is None and _optional_pid(pid) is not None:
            blocker["pid"] = _optional_pid(pid)
        if blocker.get("kernel_birth_id") is None and kernel_birth_id:
            blocker["kernel_birth_id"] = _optional_text(kernel_birth_id)
        if blocker.get("pane") is None and pane:
            blocker["pane"] = _optional_text(pane, maximum=32)
        return blocker
    category = getattr(exc, "category", None)
    code = {
        "identity_mismatch": "identity_mismatch",
        "unsupported": "transport_unsupported",
        "validation_error": "validation_error",
        "conflict": "conflict",
    }.get(category, "caller_error")
    detail = _bounded_text(exc)
    if "process executable identity is unavailable" in detail:
        code = "process_identity_unavailable"
    elif "qualification" in detail:
        code = "qualification_receipt_invalid"
    return make_blocker(
        code=code,
        detail=detail,
        pid=pid if pid is not None else getattr(exc, "pid", None),
        kernel_birth_id=kernel_birth_id
        if kernel_birth_id is not None
        else getattr(exc, "kernel_birth_id", None),
        pane=pane if pane is not None else getattr(exc, "pane", None),
    )


def attach_process_identity(exc: PuppetError, *, pid: int) -> PuppetError:
    """Add body-safe process identity to an error that escaped without it."""

    if getattr(exc, "pid", None) is None:
        exc.pid = pid
    exc.blocker = blocker_from_error(exc, pid=pid)
    return exc


def progress_cursor(record: Mapping[str, Any]) -> Dict[str, Any]:
    """Return the monotonic caller cursor derived from validated progress."""

    checkpoint = record.get("last_checkpoint")
    beacon = record.get("last_beacon")
    checkpoint_id = None
    if isinstance(checkpoint, Mapping):
        raw_id = checkpoint.get("checkpoint_id")
        if isinstance(raw_id, str) and raw_id:
            checkpoint_id = raw_id
    beacon_sequence = 0
    if isinstance(beacon, Mapping):
        raw_sequence = beacon.get("sequence")
        if isinstance(raw_sequence, int) and not isinstance(raw_sequence, bool):
            beacon_sequence = max(0, raw_sequence)
    validated_at = record.get("last_validated_at")
    if validated_at is not None and not isinstance(validated_at, str):
        validated_at = None
    return {
        "schema": PROGRESS_CURSOR_SCHEMA,
        "checkpoint_id": checkpoint_id,
        "beacon_sequence": beacon_sequence,
        "validated_at": validated_at,
    }


def caller_outcome(
    record: Mapping[str, Any],
    *,
    halt_confirmed: Optional[bool] = None,
) -> Dict[str, Any]:
    """Distinct worker, controller, and halt states. Do not collapse them."""

    checkpoint = record.get("last_checkpoint")
    worker = (
        WORKER_COMPLETION_REPORTED
        if isinstance(checkpoint, Mapping) and checkpoint.get("checkpoint_id")
        else WORKER_COMPLETION_NONE
    )
    state = record.get("state")
    if state == "ACCEPTED":
        acceptance = CONTROLLER_ACCEPTANCE_ACCEPTED
    elif state == "BLOCKED":
        acceptance = CONTROLLER_ACCEPTANCE_BLOCKED
    elif state == "FAILED":
        acceptance = CONTROLLER_ACCEPTANCE_FAILED
    else:
        acceptance = CONTROLLER_ACCEPTANCE_NONE
    if halt_confirmed is True or state == "HALTED":
        halt = HALT_CONFIRMED
    else:
        halt = HALT_NONE
    return {
        "schema": CALLER_OUTCOME_SCHEMA,
        "worker_completion": worker,
        "controller_acceptance": acceptance,
        "halt": halt,
    }


def _process_projection(record: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    process = record.get("process")
    if not isinstance(process, Mapping):
        return None
    pid = _optional_pid(process.get("pid"))
    birth = _optional_text(process.get("kernel_birth_id"))
    if pid is None or birth is None:
        return None
    return {"pid": pid, "kernel_birth_id": birth}


def final_outcome(
    record: Mapping[str, Any],
    *,
    transport_id: str,
    halt_confirmed: Optional[bool] = None,
) -> Optional[Dict[str, Any]]:
    """Speak-safe terminal summary. Absent until acceptance or confirmed halt."""

    outcome = caller_outcome(record, halt_confirmed=halt_confirmed)
    if (
        outcome["controller_acceptance"] == CONTROLLER_ACCEPTANCE_NONE
        and outcome["halt"] == HALT_NONE
    ):
        return None
    cursor = progress_cursor(record)
    session = record.get("session")
    target = record.get("target")
    summary = _bounded_text(
        "session %s: worker %s; controller %s; halt %s"
        % (
            session,
            outcome["worker_completion"],
            outcome["controller_acceptance"],
            outcome["halt"],
        ),
        maximum=_MAX_SUMMARY,
    )
    return {
        "schema": FINAL_OUTCOME_SCHEMA,
        "summary": summary,
        "session": session if isinstance(session, str) else None,
        "transport": transport_id,
        "target": target if isinstance(target, str) else None,
        "worker_completion": outcome["worker_completion"],
        "controller_acceptance": outcome["controller_acceptance"],
        "halt": outcome["halt"],
        "checkpoint_id": cursor["checkpoint_id"],
        "process": _process_projection(record),
    }


def caller_projection(
    record: Mapping[str, Any],
    *,
    transport_id: str,
    halt_confirmed: Optional[bool] = None,
) -> Dict[str, Any]:
    """Caller fields that sit beside existing lifecycle status."""

    return {
        "transport": {
            "schema": TRANSPORT_BINDING_SCHEMA,
            "id": transport_id,
        },
        "progress_cursor": progress_cursor(record),
        "caller_outcome": caller_outcome(record, halt_confirmed=halt_confirmed),
        "final_outcome": final_outcome(
            record,
            transport_id=transport_id,
            halt_confirmed=halt_confirmed,
        ),
    }
