"""Bounded Claude startup gate reducer and fail-closed navigation."""

from __future__ import annotations

import hashlib
import os
import re
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from .adapter_manifest import AdapterManifest
from .errors import IdentityError, ValidationError
from .profiles import CLAUDE_STARTUP_GATE_REDUCER, claude_gate_timing_policy
from .tmux import TmuxController


GATE_SCHEMA = "puppet.claude-startup-gate/v1"
CLAUDE_VERSION = "2.1.215"
CLAUDE_VERSION_OBSERVATION_SHA256 = (
    "3c95eff850dac10d40c5692a73957f526b54a74767163913dc858c4f8d4c8c63"
)
MAX_SCREEN_BYTES = 65536
MAX_METADATA_BYTES = 8192
CAPTURE_HISTORY_LINES = 80
MAX_GATE_STEPS = 8
_MAX_POLL_ITERATIONS = 512

_ALLOWLISTED_GATES = frozenset(
    {"security_notice", "workspace_trust", "bypass_warning", "ready"}
)
_SELECTED_VALUES = frozenset({"yes", "no", "unresolved"})
_FATAL_REDUCTION_ERRORS = frozenset(
    {
        "pane screen is not strict UTF-8",
        "bounded pane screen exceeds the cap",
        "screen matches a forbidden non-allowlisted gate",
        "screen contains an unresolved confirmation gate",
        "screen matches multiple allowlisted startup states",
        "displayed workspace label is duplicated",
        "displayed workspace path is missing",
        "displayed workspace path is malformed",
    }
)

_SECURITY_MARKERS = (
    "Security notes:",
    "Claude can make mistakes.",
    "Due to prompt injection risks",
    "Press Enter to continue",
    "https://code.claude.com/docs/en/security",
)
_TRUST_TAIL_MARKERS = (
    "Quick safety check:",
    "1. Yes, I trust this folder",
    "2. No, exit",
    "Enter to confirm",
)
_BYPASS_MARKERS = (
    "In Bypass Permissions mode",
    "you accept all responsibility",
    "1. No, exit",
    "2. Yes, I accept",
    "Enter to confirm",
    "https://code.claude.com/docs/en/security",
)
_READY_MARKERS = (
    "? for shortcuts",
    "Bypass permissions on",
    "bypass permissions on",
    'Try "',
)
_WORKSPACE_LABEL = "Accessing workspace:"
_FORBIDDEN_SCREEN_MARKERS = (
    "Log in",
    "Sign in",
    "sign in to",
    "authenticate",
    "Terms of Service",
    "Privacy Policy",
    "Accept and continue",
    "subscription required",
    "OAuth",
    "browser to log in",
    "permission request",
    "Allow access",
)


def _absolute_normalized_worktree(path: Path | str, *, label: str) -> str:
    try:
        raw = os.fspath(path)
    except TypeError as exc:
        raise ValidationError("%s must be a filesystem path" % label) from exc
    if (
        not isinstance(raw, str)
        or not raw
        or "\x00" in raw
        or len(raw) > 4096
        or not os.path.isabs(raw)
    ):
        raise ValidationError("%s must be an absolute path" % label)
    normalized = os.path.normpath(raw)
    if normalized != raw:
        raise ValidationError("%s must be normalized" % label)
    return normalized


def _normalize_screen_text(text: str) -> str:
    return re.sub(r"[ \t]+", " ", text)


def _workspace_label_line_indices(lines: Sequence[str]) -> List[int]:
    indices: List[int] = []
    for index, line in enumerate(lines):
        if line.strip().startswith(_WORKSPACE_LABEL):
            indices.append(index)
    return indices


def _parse_displayed_workspace_path(text: str) -> Tuple[Optional[str], Optional[str]]:
    """Parse exactly one displayed workspace value from raw pane text."""

    lines = text.splitlines()
    label_indices = _workspace_label_line_indices(lines)
    if not label_indices:
        return None, None
    if len(label_indices) > 1:
        return None, "displayed workspace label is duplicated"
    label_index = label_indices[0]
    label_line = lines[label_index]
    label_offset = label_line.find(_WORKSPACE_LABEL)
    if label_offset < 0:
        return None, "displayed workspace path is malformed"
    candidate = label_line[label_offset + len(_WORKSPACE_LABEL) :].strip()
    if not candidate:
        for follow_line in lines[label_index + 1 :]:
            display_line = follow_line.strip()
            if display_line:
                candidate = display_line
                break
    if not candidate:
        return None, "displayed workspace path is missing"
    try:
        return _absolute_normalized_worktree(candidate, label="displayed workspace"), None
    except ValidationError:
        return None, "displayed workspace path is malformed"


def _displayed_workspace_path(text: str) -> Optional[str]:
    displayed, error = _parse_displayed_workspace_path(text)
    if error is not None:
        return None
    return displayed


def _public_reduction(
    *,
    ok: bool,
    gate: str,
    selected: Optional[str],
    pane_pid: int,
    worktree_match: bool,
    screen_bytes: int,
    screen_sha256: str,
    error: Optional[str] = None,
) -> Dict[str, Any]:
    if gate not in _ALLOWLISTED_GATES:
        gate = "unknown"
    if selected is not None and selected not in _SELECTED_VALUES:
        selected = "unresolved"
    payload: Dict[str, Any] = {
        "schema": GATE_SCHEMA,
        "ok": ok,
        "gate": gate,
        "selected": selected,
        "pane_pid": pane_pid,
        "worktree_match": worktree_match,
        "screen_bytes": screen_bytes,
        "screen_sha256": screen_sha256,
        "raw_retained": False,
    }
    if error is not None:
        payload["error"] = error
    return payload


def _selected_choice(normalized: str, gate: str) -> Optional[str]:
    if gate == "workspace_trust":
        if re.search(r"❯\s*1\.\s*Yes, I trust this folder", normalized):
            return "yes"
        if re.search(r"❯\s*2\.\s*No, exit", normalized):
            return "no"
        return "unresolved"
    if gate == "bypass_warning":
        if re.search(r"❯\s*1\.\s*No, exit", normalized):
            return "no"
        if re.search(r"❯\s*2\.\s*Yes, I accept", normalized):
            return "yes"
        return "unresolved"
    return None


def _security_matches(normalized: str) -> bool:
    return all(marker in normalized for marker in _SECURITY_MARKERS)


def _trust_matches(text: str, *, expected_worktree: str) -> Tuple[bool, bool]:
    normalized = _normalize_screen_text(text)
    displayed, _ = _parse_displayed_workspace_path(text)
    worktree_match = displayed == expected_worktree
    matched = (
        _WORKSPACE_LABEL in text
        and worktree_match
        and all(marker in normalized for marker in _TRUST_TAIL_MARKERS)
    )
    return matched, worktree_match


def _bypass_matches(normalized: str) -> bool:
    return all(marker in normalized for marker in _BYPASS_MARKERS)


def _trust_screen_present(normalized: str) -> bool:
    return "Accessing workspace:" in normalized and all(
        marker in normalized for marker in _TRUST_TAIL_MARKERS
    )


def _ready_matches(normalized: str) -> bool:
    return (
        "Claude Code" in normalized
        and not _security_matches(normalized)
        and not _trust_screen_present(normalized)
        and not _bypass_matches(normalized)
        and "Enter to confirm" not in normalized
        and "Press Enter to continue" not in normalized
        and any(marker in normalized for marker in _READY_MARKERS)
    )


def _gate_matches(
    text: str, normalized: str, *, expected_worktree: str
) -> Tuple[str, ...]:
    trust, _worktree_match = _trust_matches(text, expected_worktree=expected_worktree)
    matches = []
    if _security_matches(normalized):
        matches.append("security_notice")
    if trust:
        matches.append("workspace_trust")
    if _bypass_matches(normalized):
        matches.append("bypass_warning")
    if _ready_matches(normalized):
        matches.append("ready")
    return tuple(matches)


def _forbidden_screen_reason(normalized: str) -> Optional[str]:
    lowered = normalized.lower()
    for marker in _FORBIDDEN_SCREEN_MARKERS:
        if marker.lower() in lowered:
            return "screen matches a forbidden non-allowlisted gate"
    if "claude code" in lowered and "enter to confirm" in lowered:
        if not any(
            marker.lower() in lowered
            for marker in (
                "yes, i trust this folder",
                "yes, i accept",
                "press enter to continue",
            )
        ):
            return "screen contains an unresolved confirmation gate"
    return None


def reduce_captured_claude_startup_screen(
    captured: bytes,
    *,
    expected_worktree: str,
    pane_pid: int,
) -> Dict[str, Any]:
    """Reduce one bounded pane capture to a body-free allowlisted verdict."""

    worktree = _absolute_normalized_worktree(expected_worktree, label="expected worktree")
    if not isinstance(captured, bytes) or not captured:
        return _public_reduction(
            ok=False,
            gate="unknown",
            selected=None,
            pane_pid=pane_pid,
            worktree_match=False,
            screen_bytes=0,
            screen_sha256=hashlib.sha256(b"").hexdigest(),
            error="bounded pane screen is unavailable",
        )
    if len(captured) > MAX_SCREEN_BYTES:
        return _public_reduction(
            ok=False,
            gate="unknown",
            selected=None,
            pane_pid=pane_pid,
            worktree_match=False,
            screen_bytes=len(captured),
            screen_sha256=hashlib.sha256(captured[:MAX_SCREEN_BYTES]).hexdigest(),
            error="bounded pane screen exceeds the cap",
        )
    try:
        text = captured.decode("utf-8", "strict")
    except UnicodeDecodeError:
        return _public_reduction(
            ok=False,
            gate="unknown",
            selected=None,
            pane_pid=pane_pid,
            worktree_match=False,
            screen_bytes=len(captured),
            screen_sha256=hashlib.sha256(captured).hexdigest(),
            error="pane screen is not strict UTF-8",
        )
    normalized = _normalize_screen_text(text)
    screen_sha256 = hashlib.sha256(captured).hexdigest()
    forbidden = _forbidden_screen_reason(normalized)
    if forbidden is not None:
        return _public_reduction(
            ok=False,
            gate="unknown",
            selected=None,
            pane_pid=pane_pid,
            worktree_match=False,
            screen_bytes=len(captured),
            screen_sha256=screen_sha256,
            error=forbidden,
        )
    if _trust_screen_present(normalized):
        displayed, parse_error = _parse_displayed_workspace_path(text)
        if parse_error is not None:
            return _public_reduction(
                ok=False,
                gate="workspace_trust",
                selected=_selected_choice(normalized, "workspace_trust"),
                pane_pid=pane_pid,
                worktree_match=False,
                screen_bytes=len(captured),
                screen_sha256=screen_sha256,
                error=parse_error,
            )
        if displayed != worktree:
            return _public_reduction(
                ok=False,
                gate="workspace_trust",
                selected=_selected_choice(normalized, "workspace_trust"),
                pane_pid=pane_pid,
                worktree_match=False,
                screen_bytes=len(captured),
                screen_sha256=screen_sha256,
                error="displayed workspace path does not match contract",
            )
    matches = _gate_matches(text, normalized, expected_worktree=worktree)
    if len(matches) > 1:
        return _public_reduction(
            ok=False,
            gate="unknown",
            selected=None,
            pane_pid=pane_pid,
            worktree_match=False,
            screen_bytes=len(captured),
            screen_sha256=screen_sha256,
            error="screen matches multiple allowlisted startup states",
        )
    if len(matches) != 1:
        return _public_reduction(
            ok=False,
            gate="unknown",
            selected=None,
            pane_pid=pane_pid,
            worktree_match=False,
            screen_bytes=len(captured),
            screen_sha256=screen_sha256,
            error="startup screen is not yet classifiable",
        )
    gate = matches[0]
    selected = _selected_choice(normalized, gate)
    _, worktree_match = _trust_matches(text, expected_worktree=worktree)
    if gate == "workspace_trust" and not worktree_match:
        return _public_reduction(
            ok=False,
            gate="workspace_trust",
            selected=selected,
            pane_pid=pane_pid,
            worktree_match=False,
            screen_bytes=len(captured),
            screen_sha256=screen_sha256,
            error="displayed workspace path does not match contract",
        )
    return _public_reduction(
        ok=True,
        gate=gate,
        selected=selected,
        pane_pid=pane_pid,
        worktree_match=worktree_match,
        screen_bytes=len(captured),
        screen_sha256=screen_sha256,
    )


def validate_claude_gate_manifest(manifest: AdapterManifest) -> None:
    """Bind gate navigation to the exact qualified Claude executable tuple."""

    raw = manifest.raw
    if raw["target"] != "claude":
        raise IdentityError("Claude startup gates require a Claude manifest")
    if raw["executable"]["version_sha256"] != CLAUDE_VERSION_OBSERVATION_SHA256:
        raise IdentityError("Claude startup gate version observation is unsupported")
    mapping = raw["yolo_mapping"]
    permission_flags = mapping.get("permission_flags")
    if not isinstance(permission_flags, list) or not permission_flags:
        raise ValidationError("Claude permission flags are unavailable")
    argv = mapping.get("launch_argv")
    if not isinstance(argv, list) or not argv:
        raise ValidationError("Claude launch argv is unavailable")
    if not all(flag in argv for flag in permission_flags):
        raise IdentityError("Claude launch argv does not authorize bypass permissions")
    timing = claude_gate_timing_policy()
    if mapping.get("startup_settle_seconds") != timing["startup_deadline_seconds"]:
        raise ValidationError("Claude gate startup deadline is not bound to startup settle")


def _authorize_bypass(
    launch_argv: Sequence[str], permission_flags: Sequence[str]
) -> bool:
    if not permission_flags:
        return False
    return all(flag in launch_argv for flag in permission_flags)


def _assert_process_alive(process_alive_fn: Callable[[], bool]) -> None:
    if not process_alive_fn():
        raise IdentityError("Claude target process is unavailable during gate navigation")


def _capture_and_reduce(
    tmux: TmuxController,
    *,
    socket: Path,
    session: str,
    pane: str,
    expected_pane_pid: int,
    expected_worktree: str,
    server_identity: Optional[Mapping[str, Any]],
    process_alive_fn: Callable[[], bool],
) -> Dict[str, Any]:
    _assert_process_alive(process_alive_fn)
    runtime = tmux.pane_runtime_identity(
        socket=socket,
        session=session,
        pane=pane,
        expected_pane_pid=expected_pane_pid,
        expected_worktree=expected_worktree,
        server_identity=server_identity,
    )
    captured = tmux.capture_pane_bytes(
        socket=socket,
        session=session,
        pane=pane,
        expected_pane_pid=runtime["pane_pid"],
        server_identity=server_identity,
    )
    try:
        return reduce_captured_claude_startup_screen(
            captured,
            expected_worktree=expected_worktree,
            pane_pid=runtime["pane_pid"],
        )
    finally:
        del captured


def _reduction_is_transient(reduction: Mapping[str, Any]) -> bool:
    error = reduction.get("error")
    if error in _FATAL_REDUCTION_ERRORS:
        return False
    return error in {
        "bounded pane screen is unavailable",
        "startup screen is not yet classifiable",
    }


def _poll_iteration_bound(timing: Mapping[str, float], *, phase: str) -> int:
    if phase == "startup":
        deadline = timing["startup_deadline_seconds"]
        interval = timing["poll_interval_seconds"]
    else:
        deadline = timing["transition_deadline_seconds"]
        interval = timing["transition_poll_interval_seconds"]
    if interval <= 0:
        return min(_MAX_POLL_ITERATIONS, max(16, int(deadline * 1000) + 8))
    return min(_MAX_POLL_ITERATIONS, int(deadline / interval) + 8)


def _poll_startup_reduction(
    tmux: TmuxController,
    *,
    socket: Path,
    session: str,
    pane: str,
    expected_pane_pid: int,
    expected_worktree: str,
    server_identity: Optional[Mapping[str, Any]],
    process_alive_fn: Callable[[], bool],
    timing: Mapping[str, float],
    sleep_fn: Callable[[float], None],
    monotonic_fn: Callable[[], float],
) -> Dict[str, Any]:
    deadline = monotonic_fn() + timing["startup_deadline_seconds"]
    iteration_bound = _poll_iteration_bound(timing, phase="startup")
    iterations = 0
    while monotonic_fn() < deadline:
        iterations += 1
        if iterations > iteration_bound:
            raise IdentityError("Claude startup gate poll iteration bound exceeded")
        reduction = _capture_and_reduce(
            tmux,
            socket=socket,
            session=session,
            pane=pane,
            expected_pane_pid=expected_pane_pid,
            expected_worktree=expected_worktree,
            server_identity=server_identity,
            process_alive_fn=process_alive_fn,
        )
        if reduction["ok"]:
            return reduction
        if not _reduction_is_transient(reduction):
            raise IdentityError(
                reduction.get("error", "Claude startup gate is ambiguous")
            )
        sleep_fn(timing["poll_interval_seconds"])
    raise IdentityError("Claude startup gate startup deadline exceeded")


def _poll_transition(
    tmux: TmuxController,
    *,
    socket: Path,
    session: str,
    pane: str,
    expected_pane_pid: int,
    expected_worktree: str,
    server_identity: Optional[Mapping[str, Any]],
    process_alive_fn: Callable[[], bool],
    timing: Mapping[str, float],
    sleep_fn: Callable[[float], None],
    monotonic_fn: Callable[[], float],
    expect_gate: Optional[str] = None,
    expect_selected: Optional[str] = None,
    reject_gate: Optional[str] = None,
) -> Dict[str, Any]:
    deadline = monotonic_fn() + timing["transition_deadline_seconds"]
    iteration_bound = _poll_iteration_bound(timing, phase="transition")
    iterations = 0
    while monotonic_fn() < deadline:
        iterations += 1
        if iterations > iteration_bound:
            raise IdentityError(
                "Claude startup gate transition poll iteration bound exceeded"
            )
        reduction = _capture_and_reduce(
            tmux,
            socket=socket,
            session=session,
            pane=pane,
            expected_pane_pid=expected_pane_pid,
            expected_worktree=expected_worktree,
            server_identity=server_identity,
            process_alive_fn=process_alive_fn,
        )
        if not reduction["ok"]:
            if _reduction_is_transient(reduction):
                sleep_fn(timing["transition_poll_interval_seconds"])
                continue
            raise IdentityError(
                reduction.get("error", "Claude startup gate transition failed")
            )
        if reject_gate is not None and reduction["gate"] == reject_gate:
            sleep_fn(timing["transition_poll_interval_seconds"])
            continue
        if expect_gate is not None and reduction["gate"] != expect_gate:
            sleep_fn(timing["transition_poll_interval_seconds"])
            continue
        if expect_selected is not None and reduction.get("selected") != expect_selected:
            sleep_fn(timing["transition_poll_interval_seconds"])
            continue
        return reduction
    raise IdentityError("Claude startup gate transition deadline exceeded")


def _send_gate_input(
    tmux: TmuxController,
    *,
    socket: Path,
    session: str,
    pane: str,
    expected_pane_pid: int,
    keys: str,
    server_identity: Optional[Mapping[str, Any]],
    process_alive_fn: Callable[[], bool],
) -> None:
    _assert_process_alive(process_alive_fn)
    tmux.send_keys_verified(
        socket=socket,
        session=session,
        pane=pane,
        keys=keys,
        expected_pane_pid=expected_pane_pid,
        server_identity=server_identity,
    )


def _body_free_step(reduction: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "gate": reduction["gate"],
        "selected": reduction.get("selected"),
        "screen_bytes": reduction["screen_bytes"],
        "screen_sha256": reduction["screen_sha256"],
        "raw_retained": False,
    }


def navigate_claude_startup_gates(
    tmux: TmuxController,
    *,
    manifest: AdapterManifest,
    socket: Path,
    session: str,
    pane: str,
    expected_worktree: Path | str,
    expected_pane_pid: int,
    launch_argv: Sequence[str],
    server_identity: Optional[Mapping[str, Any]] = None,
    process_alive_fn: Callable[[], bool],
    sleep_fn: Callable[[float], None] = time.sleep,
    monotonic_fn: Callable[[], float] = time.monotonic,
    timing: Optional[Mapping[str, float]] = None,
) -> Dict[str, Any]:
    """Navigate allowlisted Claude startup gates until a ready screen is confirmed."""

    validate_claude_gate_manifest(manifest)
    timing_policy = dict(timing or claude_gate_timing_policy())
    worktree = _absolute_normalized_worktree(expected_worktree, label="expected worktree")
    permission_flags = list(manifest.raw["yolo_mapping"]["permission_flags"])
    if not _authorize_bypass(launch_argv, permission_flags):
        raise IdentityError(
            "launch contract does not authorize Claude bypass-permissions argv"
        )
    steps: List[Dict[str, Any]] = []
    security_enter_sent = False
    poll_kwargs = {
        "tmux": tmux,
        "socket": socket,
        "session": session,
        "pane": pane,
        "expected_pane_pid": expected_pane_pid,
        "expected_worktree": worktree,
        "server_identity": server_identity,
        "process_alive_fn": process_alive_fn,
        "timing": timing_policy,
        "sleep_fn": sleep_fn,
        "monotonic_fn": monotonic_fn,
    }

    for _ in range(MAX_GATE_STEPS):
        reduction = _poll_startup_reduction(**poll_kwargs)
        gate = reduction["gate"]
        steps.append(_body_free_step(reduction))

        if gate == "ready":
            return {
                "strategy": CLAUDE_STARTUP_GATE_REDUCER,
                "final_gate": "ready",
                "steps": steps,
                "timing_policy": timing_policy,
                "raw_retained": False,
            }

        if gate == "security_notice":
            if security_enter_sent:
                raise IdentityError("Claude security notice did not clear after Enter")
            _send_gate_input(
                tmux,
                socket=socket,
                session=session,
                pane=pane,
                expected_pane_pid=expected_pane_pid,
                keys="Enter",
                server_identity=server_identity,
                process_alive_fn=process_alive_fn,
            )
            security_enter_sent = True
            _poll_transition(**poll_kwargs, reject_gate="security_notice")
            continue

        if gate == "workspace_trust":
            if not reduction["worktree_match"]:
                raise IdentityError("Claude workspace trust path does not match contract")
            selected = reduction.get("selected")
            if selected == "no":
                _send_gate_input(
                    tmux,
                    socket=socket,
                    session=session,
                    pane=pane,
                    expected_pane_pid=expected_pane_pid,
                    keys="Up",
                    server_identity=server_identity,
                    process_alive_fn=process_alive_fn,
                )
                _poll_transition(
                    **poll_kwargs,
                    expect_gate="workspace_trust",
                    expect_selected="yes",
                )
            elif selected != "yes":
                raise IdentityError("Claude workspace trust selection is unresolved")
            _send_gate_input(
                tmux,
                socket=socket,
                session=session,
                pane=pane,
                expected_pane_pid=expected_pane_pid,
                keys="Enter",
                server_identity=server_identity,
                process_alive_fn=process_alive_fn,
            )
            _poll_transition(**poll_kwargs, reject_gate="workspace_trust")
            continue

        if gate == "bypass_warning":
            selected = reduction.get("selected")
            if selected == "no":
                _send_gate_input(
                    tmux,
                    socket=socket,
                    session=session,
                    pane=pane,
                    expected_pane_pid=expected_pane_pid,
                    keys="Down",
                    server_identity=server_identity,
                    process_alive_fn=process_alive_fn,
                )
                _poll_transition(
                    **poll_kwargs,
                    expect_gate="bypass_warning",
                    expect_selected="yes",
                )
            elif selected != "yes":
                raise IdentityError("Claude bypass warning selection is unresolved")
            _send_gate_input(
                tmux,
                socket=socket,
                session=session,
                pane=pane,
                expected_pane_pid=expected_pane_pid,
                keys="Enter",
                server_identity=server_identity,
                process_alive_fn=process_alive_fn,
            )
            _poll_transition(**poll_kwargs, reject_gate="bypass_warning")
            continue

        raise IdentityError("Claude startup gate is outside the allowlist")

    raise IdentityError("Claude startup gate navigation exceeded the step bound")


def revalidate_claude_ready_process(
    *,
    manifest: AdapterManifest,
    tmux: TmuxController,
    socket: Path,
    session: str,
    pane: str,
    expected_pane_pid: int,
    expected_worktree: Path | str,
    process: Mapping[str, Any],
    server_identity: Optional[Mapping[str, Any]],
    process_alive_fn: Callable[[], bool],
) -> None:
    """Revalidate manifest/process/pane lease immediately before prompt delivery."""

    validate_claude_gate_manifest(manifest)
    if not process_alive_fn():
        raise IdentityError("Claude target process is unavailable before prompt delivery")
    worktree = _absolute_normalized_worktree(expected_worktree, label="expected worktree")
    runtime = tmux.pane_runtime_identity(
        socket=socket,
        session=session,
        pane=pane,
        expected_pane_pid=expected_pane_pid,
        expected_worktree=worktree,
        server_identity=server_identity,
    )
    if runtime["pane_pid"] != process["pid"]:
        raise IdentityError("Claude target process identity changed before prompt delivery")
    manifest.verify_process_executable(process)
    ready = _capture_and_reduce(
        tmux,
        socket=socket,
        session=session,
        pane=pane,
        expected_pane_pid=expected_pane_pid,
        expected_worktree=worktree,
        server_identity=server_identity,
        process_alive_fn=process_alive_fn,
    )
    if not ready["ok"] or ready["gate"] != "ready":
        raise IdentityError("Claude startup screen is not ready before prompt delivery")


def await_claude_input_ready(
    tmux: TmuxController,
    *,
    manifest: AdapterManifest,
    socket: Path,
    session: str,
    pane: str,
    expected_worktree: Path | str,
    expected_pane_pid: int,
    launch_argv: Sequence[str],
    server_identity: Optional[Mapping[str, Any]] = None,
    process_alive_fn: Callable[[], bool],
    sleep_fn: Callable[[float], None] = time.sleep,
    monotonic_fn: Callable[[], float] = time.monotonic,
    timing: Optional[Mapping[str, float]] = None,
) -> Dict[str, Any]:
    """Fail-closed Claude-only readiness gate before any prompt may enter the pane."""

    return navigate_claude_startup_gates(
        tmux,
        manifest=manifest,
        socket=socket,
        session=session,
        pane=pane,
        expected_worktree=expected_worktree,
        expected_pane_pid=expected_pane_pid,
        launch_argv=launch_argv,
        server_identity=server_identity,
        process_alive_fn=process_alive_fn,
        sleep_fn=sleep_fn,
        monotonic_fn=monotonic_fn,
        timing=timing,
    )
