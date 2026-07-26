"""Bounded Cursor workspace-trust reducer and fail-closed navigation."""

from __future__ import annotations

import hashlib
import os
import re
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from .adapter_manifest import AdapterManifest
from .cursor_qualification import (
    cursor_probe_mapping_from_qualified,
    cursor_qualified_mapping,
    is_cursor_mapping_closure,
)
from .errors import IdentityError, ValidationError
from .profiles import CURSOR_STARTUP_GATE_REDUCER, cursor_gate_timing_policy
from .tmux import TmuxController


GATE_SCHEMA = "puppet.cursor-startup-gate/v1"
MAX_SCREEN_BYTES = 65536
MAX_PATH_LINES = 8
_MAX_POLL_ITERATIONS = 512

_TRUST_TITLE = "Workspace Trust Required"
_TRUST_EXECUTION = (
    "Cursor Agent can execute code and access files in this directory."
)
_TRUST_QUESTION = "Do you trust the contents of this directory?"
_TRUST_NAVIGATION = (
    "Use arrow keys to navigate, Enter to select, or press the key shown"
)
_TRUST_A = re.compile(r"^(?:▶|❯|>)?\s*\[a\]\s+Trust this workspace$")
_TRUST_Q = re.compile(r"^(?:▶|❯|>)?\s*\[q\]\s+Quit$")
_ANY_SHORTCUT = re.compile(r"\[[A-Za-z]\]")
_MCP_TRUST_MARKERS = (
    "[w]",
    "Trust this workspace, but don't enable all MCP servers",
    "This will also enable the MCP servers configured for this workspace.",
)
_FORBIDDEN_SCREEN_MARKERS = (
    "log in",
    "sign in",
    "authenticate",
    "terms of service",
    "privacy policy",
    "accept and continue",
    "permission request",
    "browser to log in",
    "allow access",
    "subscription required",
    "oauth",
)
_FATAL_REDUCTION_ERRORS = frozenset(
    {
        "pane screen is not strict UTF-8",
        "bounded pane screen exceeds the cap",
        "screen matches a forbidden non-allowlisted gate",
        "screen contains an MCP-expanded workspace trust gate",
        "screen contains an unresolved confirmation gate",
        "displayed workspace trust markers are duplicated",
        "displayed workspace trust markers are malformed",
        "displayed workspace path is missing",
        "displayed workspace path is malformed",
        "displayed workspace path does not match contract",
    }
)
_FORBIDDEN_RUNTIME_SELECTORS = frozenset(
    {
        "--worktree",
        "--worktree-base",
        "--add-dir",
        "--api-key",
        "--config",
        "--profile",
        "--model",
    }
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


def _screen_sha(captured: bytes) -> str:
    return hashlib.sha256(captured).hexdigest()


def _public_reduction(
    *,
    ok: bool,
    gate: str,
    pane_pid: int,
    worktree_match: bool,
    screen_bytes: int,
    screen_sha256: str,
    selected: Optional[str] = None,
    error: Optional[str] = None,
) -> Dict[str, Any]:
    if gate not in {"workspace_trust", "ready"}:
        gate = "unknown"
    if selected not in {None, "yes"}:
        selected = None
    result: Dict[str, Any] = {
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
        result["error"] = error
    return result


def _strip_box_border(line: str) -> str:
    """Remove only Ink's single outer vertical border and visual padding."""

    value = line.rstrip("\r").strip()
    if value.startswith("│"):
        value = value[1:].lstrip()
    if value.endswith("│"):
        value = value[:-1].rstrip()
    if value.startswith("⚠ "):
        value = value[2:].lstrip()
    return value


def _screen_lines(text: str) -> List[str]:
    return [_strip_box_border(line) for line in text.splitlines()]


def _marker_indices(lines: Sequence[str], marker: str) -> List[int]:
    return [index for index, line in enumerate(lines) if line == marker]


def _trust_screen_present(lines: Sequence[str]) -> bool:
    return any(
        marker in line
        for line in lines
        for marker in (_TRUST_TITLE, _TRUST_EXECUTION, _TRUST_QUESTION)
    )


def _trust_screen_complete(lines: Sequence[str]) -> bool:
    return all(
        len(_marker_indices(lines, marker)) == 1
        for marker in (
            _TRUST_TITLE,
            _TRUST_EXECUTION,
            _TRUST_QUESTION,
            _TRUST_NAVIGATION,
        )
    )


def _parse_trust_screen(
    lines: Sequence[str], *, expected_worktree: str
) -> Tuple[Optional[str], Optional[str]]:
    """Return the exact displayed workspace or a fatal parse reason."""

    title = _marker_indices(lines, _TRUST_TITLE)
    execution = _marker_indices(lines, _TRUST_EXECUTION)
    question = _marker_indices(lines, _TRUST_QUESTION)
    navigation = _marker_indices(lines, _TRUST_NAVIGATION)
    marker_groups = (title, execution, question, navigation)
    if any(len(group) > 1 for group in marker_groups):
        return None, "displayed workspace trust markers are duplicated"
    if any(len(group) != 1 for group in marker_groups):
        return None, "displayed workspace trust markers are malformed"

    a_choices = [index for index, line in enumerate(lines) if _TRUST_A.fullmatch(line)]
    q_choices = [index for index, line in enumerate(lines) if _TRUST_Q.fullmatch(line)]
    if len(a_choices) != 1 or len(q_choices) != 1:
        return None, "screen contains an unresolved confirmation gate"
    shortcut_lines = [
        line
        for line in lines
        if _ANY_SHORTCUT.search(line) is not None
    ]
    if len(shortcut_lines) != 2:
        return None, "screen contains an unresolved confirmation gate"

    if not (
        title[0] < execution[0] < question[0]
        < a_choices[0] < q_choices[0] < navigation[0]
    ):
        return None, "displayed workspace trust markers are malformed"
    path_lines = [
        line
        for line in lines[question[0] + 1 : a_choices[0]]
        if line
    ]
    if not path_lines:
        return None, "displayed workspace path is missing"
    if (
        len(path_lines) > MAX_PATH_LINES
        or not path_lines[0].startswith("/")
        or any(line.startswith("/") for line in path_lines[1:])
    ):
        return None, "displayed workspace path is malformed"
    displayed = "".join(path_lines)
    try:
        displayed = _absolute_normalized_worktree(
            displayed, label="displayed workspace"
        )
    except ValidationError:
        return None, "displayed workspace path is malformed"
    if displayed != expected_worktree:
        return displayed, "displayed workspace path does not match contract"
    return displayed, None


def _screen_contains_worktree(
    lines: Sequence[str], expected_worktree: str, *, start_index: int = 0
) -> bool:
    """Match a literal or hard-wrapped workspace footer without retaining it."""

    for index, line in enumerate(lines[start_index:], start_index):
        start = line.find("/")
        if start < 0:
            continue
        candidate = line[start:]
        if candidate == expected_worktree:
            return True
        for following in lines[index + 1 : index + MAX_PATH_LINES]:
            if not following:
                continue
            candidate += following
            if candidate == expected_worktree:
                return True
            if len(candidate) >= len(expected_worktree):
                break
    return False


def _ready_screen_matches(lines: Sequence[str], expected_worktree: str) -> bool:
    footer_indices = [
        index for index, line in enumerate(lines) if "Run Everything" in line
    ]
    if not footer_indices:
        return False
    footer_index = footer_indices[-1]
    trust_indices = [
        index
        for index, line in enumerate(lines)
        if line in {_TRUST_TITLE, _TRUST_QUESTION, _TRUST_NAVIGATION}
    ]
    if trust_indices and footer_index <= trust_indices[-1]:
        return False
    scan_start = trust_indices[-1] + 1 if trust_indices else 0
    has_auto_selector = any(
        re.search(r"(?:^|\s)Auto(?:\s|·|$)", line) is not None
        for line in lines[scan_start : footer_index + 1]
    )
    return (
        has_auto_selector
        and _screen_contains_worktree(
            lines, expected_worktree, start_index=footer_index
        )
    )


def _forbidden_reason(text: str) -> Optional[str]:
    lower = text.lower()
    if any(marker.lower() in lower for marker in _MCP_TRUST_MARKERS):
        return "screen contains an MCP-expanded workspace trust gate"
    if any(marker in lower for marker in _FORBIDDEN_SCREEN_MARKERS):
        return "screen matches a forbidden non-allowlisted gate"
    return None


def reduce_captured_cursor_startup_screen(
    captured: bytes,
    *,
    expected_worktree: str,
    pane_pid: int,
) -> Dict[str, Any]:
    """Reduce one bounded owned-pane capture to body-free startup metadata."""

    worktree = _absolute_normalized_worktree(expected_worktree, label="expected worktree")
    if not isinstance(captured, bytes) or not captured:
        return _public_reduction(
            ok=False,
            gate="unknown",
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
            pane_pid=pane_pid,
            worktree_match=False,
            screen_bytes=len(captured),
            screen_sha256=_screen_sha(captured),
            error="pane screen is not strict UTF-8",
        )
    digest = _screen_sha(captured)
    forbidden = _forbidden_reason(text)
    if forbidden is not None:
        return _public_reduction(
            ok=False,
            gate="unknown",
            pane_pid=pane_pid,
            worktree_match=False,
            screen_bytes=len(captured),
            screen_sha256=digest,
            error=forbidden,
        )
    lines = _screen_lines(text)
    if _ready_screen_matches(lines, worktree):
        return _public_reduction(
            ok=True,
            gate="ready",
            pane_pid=pane_pid,
            worktree_match=True,
            screen_bytes=len(captured),
            screen_sha256=digest,
        )
    if _trust_screen_present(lines):
        if not _trust_screen_complete(lines):
            if any(
                len(_marker_indices(lines, marker)) > 1
                for marker in (
                    _TRUST_TITLE,
                    _TRUST_EXECUTION,
                    _TRUST_QUESTION,
                    _TRUST_NAVIGATION,
                )
            ):
                error = "displayed workspace trust markers are duplicated"
                return _public_reduction(
                    ok=False,
                    gate="workspace_trust",
                    pane_pid=pane_pid,
                    worktree_match=False,
                    screen_bytes=len(captured),
                    screen_sha256=digest,
                    error=error,
                )
            return _public_reduction(
                ok=False,
                gate="unknown",
                pane_pid=pane_pid,
                worktree_match=False,
                screen_bytes=len(captured),
                screen_sha256=digest,
                error="startup screen is not yet classifiable",
            )
        displayed, error = _parse_trust_screen(
            lines, expected_worktree=worktree
        )
        if error is not None:
            fatal = error in _FATAL_REDUCTION_ERRORS
            return _public_reduction(
                ok=False,
                gate="workspace_trust" if fatal else "unknown",
                pane_pid=pane_pid,
                worktree_match=displayed == worktree,
                screen_bytes=len(captured),
                screen_sha256=digest,
                error=error,
            )
        return _public_reduction(
            ok=True,
            gate="workspace_trust",
            selected="yes",
            pane_pid=pane_pid,
            worktree_match=True,
            screen_bytes=len(captured),
            screen_sha256=digest,
        )
    return _public_reduction(
        ok=False,
        gate="unknown",
        pane_pid=pane_pid,
        worktree_match=False,
        screen_bytes=len(captured),
        screen_sha256=digest,
        error="startup screen is not yet classifiable",
    )


def _probe_mapping(mapping: Mapping[str, Any]) -> Dict[str, Any]:
    if is_cursor_mapping_closure(mapping):
        return cursor_probe_mapping_from_qualified(mapping)
    try:
        cursor_qualified_mapping(mapping)
    except (IdentityError, TypeError, ValueError) as exc:
        raise IdentityError("Cursor startup mapping is not the exact regular tuple") from exc
    return dict(mapping)


def validate_cursor_gate_manifest(manifest: AdapterManifest) -> None:
    if manifest.raw["target"] != "cursor":
        raise IdentityError("Cursor startup gates require a Cursor manifest")
    mapping = _probe_mapping(manifest.raw["yolo_mapping"])
    if (
        mapping.get("startup_settle_seconds")
        != cursor_gate_timing_policy()["startup_deadline_seconds"]
    ):
        raise ValidationError(
            "Cursor gate startup deadline is not bound to startup settle"
        )


def _validate_launch_argv(
    *,
    manifest: AdapterManifest,
    launch_argv: Sequence[str],
    expected_worktree: str,
) -> None:
    if isinstance(launch_argv, (str, bytes)) or not isinstance(
        launch_argv, Sequence
    ):
        raise ValidationError("Cursor launch argv is unavailable")
    mapping = _probe_mapping(manifest.raw["yolo_mapping"])
    base = list(mapping["launch_argv"])
    argv = list(launch_argv)
    expected = [*base, "--workspace", expected_worktree]
    if argv[: len(expected)] != expected:
        raise IdentityError("Cursor launch argv does not bind the exact workspace")
    if len(argv) not in {len(expected), len(expected) + 1}:
        raise IdentityError("Cursor launch argv has an unsupported suffix")
    if len(argv) == len(expected) + 1 and (
        not argv[-1] or argv[-1].startswith("-")
    ):
        raise IdentityError("Cursor positional activation trigger is invalid")
    if any(selector in argv for selector in _FORBIDDEN_RUNTIME_SELECTORS):
        raise IdentityError("Cursor launch argv includes a forbidden runtime selector")


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
    if not process_alive_fn():
        raise IdentityError("Cursor target process is unavailable during gate navigation")
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
        return reduce_captured_cursor_startup_screen(
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


def _poll_bound(timing: Mapping[str, float], *, transition: bool) -> int:
    deadline_name = (
        "transition_deadline_seconds" if transition else "startup_deadline_seconds"
    )
    interval_name = (
        "transition_poll_interval_seconds" if transition else "poll_interval_seconds"
    )
    deadline = timing[deadline_name]
    interval = timing[interval_name]
    if interval <= 0:
        return min(_MAX_POLL_ITERATIONS, max(16, int(deadline * 1000) + 8))
    return min(_MAX_POLL_ITERATIONS, int(deadline / interval) + 8)


def _poll_reduction(
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
    transition: bool,
    require_ready: bool,
) -> Dict[str, Any]:
    deadline_name = (
        "transition_deadline_seconds" if transition else "startup_deadline_seconds"
    )
    interval_name = (
        "transition_poll_interval_seconds" if transition else "poll_interval_seconds"
    )
    deadline = monotonic_fn() + timing[deadline_name]
    iterations = 0
    bound = _poll_bound(timing, transition=transition)
    while monotonic_fn() < deadline:
        iterations += 1
        if iterations > bound:
            raise IdentityError("Cursor startup gate poll iteration bound exceeded")
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
        if reduction["ok"] and (
            not require_ready or reduction["gate"] == "ready"
        ):
            return reduction
        if reduction["ok"] and require_ready:
            sleep_fn(timing[interval_name])
            continue
        if not _reduction_is_transient(reduction):
            raise IdentityError(
                reduction.get("error", "Cursor startup gate is ambiguous")
            )
        sleep_fn(timing[interval_name])
    phase = "transition" if transition else "startup"
    raise IdentityError("Cursor startup gate %s deadline exceeded" % phase)


def _body_free_step(reduction: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "gate": reduction["gate"],
        "selected": reduction.get("selected"),
        "worktree_match": reduction["worktree_match"],
        "screen_bytes": reduction["screen_bytes"],
        "screen_sha256": reduction["screen_sha256"],
        "raw_retained": False,
    }


def navigate_cursor_startup_gates(
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
    """Clear only Cursor's exact owned-workspace trust gate."""

    validate_cursor_gate_manifest(manifest)
    worktree = _absolute_normalized_worktree(expected_worktree, label="expected worktree")
    _validate_launch_argv(
        manifest=manifest,
        launch_argv=launch_argv,
        expected_worktree=worktree,
    )
    timing_policy = dict(timing or cursor_gate_timing_policy())
    poll = {
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
    first = _poll_reduction(
        **poll,
        transition=False,
        require_ready=False,
    )
    steps = [_body_free_step(first)]
    if first["gate"] == "workspace_trust":
        if not process_alive_fn():
            raise IdentityError(
                "Cursor target process is unavailable during gate navigation"
            )
        tmux.send_keys_verified(
            socket=socket,
            session=session,
            pane=pane,
            keys="a",
            expected_pane_pid=expected_pane_pid,
            server_identity=server_identity,
        )
        ready = _poll_reduction(
            **poll,
            transition=True,
            require_ready=True,
        )
        steps.append(_body_free_step(ready))
    elif first["gate"] != "ready":
        raise IdentityError("Cursor startup gate is outside the allowlist")
    return {
        "strategy": CURSOR_STARTUP_GATE_REDUCER,
        "final_gate": "ready",
        "steps": steps,
        "timing_policy": timing_policy,
        "raw_retained": False,
    }


def revalidate_cursor_ready_process(
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
    """Revalidate the exact process, pane, executable, cwd, and cleared gate."""

    validate_cursor_gate_manifest(manifest)
    if not process_alive_fn():
        raise IdentityError("Cursor target process is unavailable before prompt delivery")
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
        raise IdentityError("Cursor target process identity changed before prompt delivery")
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
        raise IdentityError("Cursor startup screen is not ready before prompt delivery")


def await_cursor_input_ready(
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
    return navigate_cursor_startup_gates(
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
