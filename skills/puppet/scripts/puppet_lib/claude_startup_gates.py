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
from .profiles import CLAUDE_STARTUP_GATE_REDUCER
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

_ALLOWLISTED_GATES = frozenset(
    {"security_notice", "workspace_trust", "bypass_warning", "ready"}
)
_SELECTED_VALUES = frozenset({"yes", "no", "unresolved"})

_SECURITY_MARKERS = (
    "Security notes:",
    "Claude can make mistakes.",
    "Due to prompt injection risks",
    "Press Enter to continue",
    "https://code.claude.com/docs/en/security",
)
_TRUST_MARKERS = (
    "Accessing workspace:",
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
    'Bypass permissions on',
    "bypass permissions on",
    'Try "',
)
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


def _gate_matches(normalized: str, *, expected_worktree: str) -> Tuple[str, ...]:
    security = all(marker in normalized for marker in _SECURITY_MARKERS)
    trust = all(
        marker in normalized
        for marker in (
            *_TRUST_MARKERS[:1],
            expected_worktree,
            *_TRUST_MARKERS[1:],
        )
    )
    bypass = all(marker in normalized for marker in _BYPASS_MARKERS)
    ready = (
        "Claude Code" in normalized
        and not any((security, trust, bypass))
        and "Enter to confirm" not in normalized
        and "Press Enter to continue" not in normalized
        and any(marker in normalized for marker in _READY_MARKERS)
    )
    return tuple(
        name
        for name, matched in (
            ("security_notice", security),
            ("workspace_trust", trust),
            ("bypass_warning", bypass),
            ("ready", ready),
        )
        if matched
    )


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
    matches = _gate_matches(normalized, expected_worktree=worktree)
    if len(matches) != 1:
        return _public_reduction(
            ok=False,
            gate="unknown",
            selected=None,
            pane_pid=pane_pid,
            worktree_match=worktree in normalized,
            screen_bytes=len(captured),
            screen_sha256=screen_sha256,
            error="screen does not match exactly one allowlisted startup state",
        )
    gate = matches[0]
    selected = _selected_choice(normalized, gate)
    worktree_match = gate != "workspace_trust" or worktree in normalized
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


def _authorize_bypass(
    launch_argv: Sequence[str], permission_flags: Sequence[str]
) -> bool:
    if not permission_flags:
        return False
    argv = list(launch_argv)
    return all(flag in argv for flag in permission_flags)


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
    settle_after_input_seconds: float = 0.05,
) -> Dict[str, Any]:
    """Navigate allowlisted Claude startup gates until a ready screen is confirmed."""

    validate_claude_gate_manifest(manifest)
    worktree = _absolute_normalized_worktree(expected_worktree, label="expected worktree")
    permission_flags = list(manifest.raw["yolo_mapping"]["permission_flags"])
    if not _authorize_bypass(launch_argv, permission_flags):
        raise IdentityError(
            "launch contract does not authorize Claude bypass-permissions argv"
        )
    steps: List[Dict[str, Any]] = []
    security_enter_sent = False

    for _ in range(MAX_GATE_STEPS):
        reduction = _capture_and_reduce(
            tmux,
            socket=socket,
            session=session,
            pane=pane,
            expected_pane_pid=expected_pane_pid,
            expected_worktree=worktree,
            server_identity=server_identity,
            process_alive_fn=process_alive_fn,
        )
        if not reduction["ok"]:
            raise IdentityError(reduction.get("error", "Claude startup gate is ambiguous"))

        gate = reduction["gate"]
        steps.append(_body_free_step(reduction))

        if gate == "ready":
            return {
                "strategy": CLAUDE_STARTUP_GATE_REDUCER,
                "final_gate": "ready",
                "steps": steps,
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
            sleep_fn(settle_after_input_seconds)
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
                sleep_fn(settle_after_input_seconds)
                selected_reduction = _capture_and_reduce(
                    tmux,
                    socket=socket,
                    session=session,
                    pane=pane,
                    expected_pane_pid=expected_pane_pid,
                    expected_worktree=worktree,
                    server_identity=server_identity,
                    process_alive_fn=process_alive_fn,
                )
                if (
                    not selected_reduction["ok"]
                    or selected_reduction["gate"] != "workspace_trust"
                    or selected_reduction.get("selected") != "yes"
                ):
                    raise IdentityError(
                        "Claude workspace trust yes selection is not confirmed"
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
            sleep_fn(settle_after_input_seconds)
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
                sleep_fn(settle_after_input_seconds)
                selected_reduction = _capture_and_reduce(
                    tmux,
                    socket=socket,
                    session=session,
                    pane=pane,
                    expected_pane_pid=expected_pane_pid,
                    expected_worktree=worktree,
                    server_identity=server_identity,
                    process_alive_fn=process_alive_fn,
                )
                if (
                    not selected_reduction["ok"]
                    or selected_reduction["gate"] != "bypass_warning"
                    or selected_reduction.get("selected") != "yes"
                ):
                    raise IdentityError(
                        "Claude bypass warning yes selection is not confirmed"
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
            sleep_fn(settle_after_input_seconds)
            continue

        raise IdentityError("Claude startup gate is outside the allowlist")

    raise IdentityError("Claude startup gate navigation exceeded the step bound")


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
    )
