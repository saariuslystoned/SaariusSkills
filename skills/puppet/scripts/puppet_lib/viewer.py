"""Short-lived, human-only native TUI viewer doorway."""

from __future__ import annotations

import os
import secrets
import shlex
import stat
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional, Sequence, Tuple

from .errors import ConflictError, UnsupportedError, ValidationError
from .safety import (
    absolute_root,
    atomic_write_bytes,
    atomic_write_json,
    canonical_json_bytes,
    ensure_within,
    read_json,
    sha256_bytes,
    sha256_file,
    validate_identifier,
    validate_pane_id,
)


TICKET_SCHEMA = "puppet.native-view-ticket/v1"
CLAIM_SCHEMA = "puppet.native-view-claim/v1"
REVOCATION_SCHEMA = "puppet.native-view-revocation/v1"
TICKET_TTL_SECONDS = 30
EXPECTED_IDENTITY_FIELDS = {
    "attach_argv_sha256",
    "pane",
    "pane_pid",
    "process_identity_sha256",
    "server_identity_sha256",
    "socket_identity_sha256",
    "tmux_binary_identity_sha256",
}
_TERMINAL_APPLICATIONS = {
    "iterm": ("iTerm", (Path("/Applications/iTerm.app"),)),
    "terminal": (
        "Terminal",
        (
            Path("/System/Applications/Utilities/Terminal.app"),
            Path("/Applications/Utilities/Terminal.app"),
        ),
    ),
}


def _select_terminal(
    requested: str,
    *,
    application_exists: Callable[[Path], bool],
) -> Tuple[str, Path]:
    if requested not in {"auto", *_TERMINAL_APPLICATIONS}:
        raise ValidationError("terminal application selector is unsupported")
    candidates = ("iterm", "terminal") if requested == "auto" else (requested,)
    for candidate in candidates:
        app_name, paths = _TERMINAL_APPLICATIONS[candidate]
        for path in paths:
            if application_exists(path):
                return app_name, path
    raise UnsupportedError("no supported visible terminal application is available")


def _private_view_root(state_root: Path) -> Path:
    root = absolute_root(str(state_root), "state root")
    details = root.stat()
    if details.st_uid != os.getuid() or stat.S_IMODE(details.st_mode) != 0o700:
        raise ValidationError("state root is not current-UID mode 0700")
    views = root / "views"
    if views.exists():
        if views.is_symlink() or not views.is_dir():
            raise ValidationError("viewer root is not a regular directory")
    else:
        views.mkdir(mode=0o700)
    view_details = views.stat()
    if (
        view_details.st_uid != os.getuid()
        or stat.S_IMODE(view_details.st_mode) != 0o700
    ):
        raise ValidationError("viewer root is not current-UID mode 0700")
    return views


def _regular_file_identity(path: Path, *, executable: bool = False) -> Dict[str, Any]:
    path = Path(path)
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise ValidationError("viewer executable identity is invalid")
    resolved = path.resolve(strict=True)
    details = resolved.stat()
    if executable and not os.access(resolved, os.X_OK):
        raise ValidationError("viewer executable identity is invalid")
    return {
        "path": str(resolved),
        "device": details.st_dev,
        "inode": details.st_ino,
        "uid": details.st_uid,
        "gid": details.st_gid,
        "mode": stat.S_IMODE(details.st_mode),
        "size": details.st_size,
        "sha256": sha256_file(resolved),
    }


def _directory_identity(path: Path) -> Dict[str, Any]:
    path = Path(path)
    if not path.is_absolute() or path.is_symlink() or not path.is_dir():
        raise UnsupportedError("selected terminal application identity is unavailable")
    resolved = path.resolve(strict=True)
    details = resolved.stat()
    return {
        "path": str(resolved),
        "device": details.st_dev,
        "inode": details.st_ino,
        "uid": details.st_uid,
        "gid": details.st_gid,
        "mode": stat.S_IMODE(details.st_mode),
    }


def _validate_expected_identity(value: Any) -> Dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != EXPECTED_IDENTITY_FIELDS:
        raise ValidationError("viewer expected identity fields are invalid")
    normalized = dict(value)
    for name in EXPECTED_IDENTITY_FIELDS - {"pane", "pane_pid"}:
        candidate = normalized.get(name)
        if (
            not isinstance(candidate, str)
            or len(candidate) != 64
            or any(character not in "0123456789abcdef" for character in candidate)
        ):
            raise ValidationError("viewer expected identity digest is invalid")
    validate_pane_id(normalized.get("pane"))
    pane_pid = normalized.get("pane_pid")
    if isinstance(pane_pid, bool) or not isinstance(pane_pid, int) or pane_pid <= 1:
        raise ValidationError("viewer expected process identity is invalid")
    return normalized


def _validate_command_argv(
    argv: Sequence[str],
    *,
    session: str,
    state_root: Path,
    ticket_path: Path,
) -> Tuple[str, ...]:
    if not isinstance(argv, (list, tuple)) or not argv:
        raise ValidationError("viewer command argv is invalid")
    normalized = tuple(argv)
    if any(
        not isinstance(value, str)
        or not value
        or len(value.encode("utf-8")) > 4096
        or any(marker in value for marker in ("\x00", "\n", "\r"))
        for value in normalized
    ):
        raise ValidationError("viewer command argv is invalid")
    if len(normalized) != 8 or normalized[2::2] != (
        "--state-root",
        "--session",
        "--ticket",
    ):
        raise ValidationError("viewer command authority grammar is invalid")
    interpreter = Path(normalized[0])
    helper = Path(normalized[1])
    if (
        _regular_file_identity(interpreter, executable=True)["path"] != normalized[0]
        or _regular_file_identity(helper)["path"] != normalized[1]
    ):
        raise ValidationError("viewer command executable identity is not canonical")
    if (
        normalized[3] != str(state_root.resolve(strict=True))
        or normalized[5] != session
        or normalized[7] != str(ticket_path)
    ):
        raise ValidationError("viewer command session binding changed")
    return normalized


def prepare_view_ticket(
    *,
    helper_argv: Sequence[str],
    ticket: Mapping[str, Any],
    state_root: Path,
    session: str,
) -> Dict[str, Any]:
    """Persist one short-lived ticket and return its exact helper command."""
    validate_identifier(session, "session")
    views = _private_view_root(state_root)
    if not isinstance(ticket, Mapping) or ticket.get("schema") != TICKET_SCHEMA:
        raise ValidationError("viewer ticket is invalid")
    nonce = ticket.get("nonce")
    validate_identifier(nonce, "viewer ticket nonce")
    ticket_path = views / (session + "-" + nonce + ".json")
    argv = _validate_command_argv(
        helper_argv,
        session=session,
        state_root=Path(state_root),
        ticket_path=ticket_path,
    )
    if ticket_path.exists():
        raise ConflictError("viewer ticket identity already exists")
    atomic_write_json(ticket_path, dict(ticket))
    details = ticket_path.stat()
    if (
        ticket_path.is_symlink()
        or not ticket_path.is_file()
        or details.st_uid != os.getuid()
        or stat.S_IMODE(details.st_mode) != 0o600
    ):
        raise ValidationError("viewer artifact identity is unsafe")
    return {
        "ticket_path": str(ticket_path),
        "ticket_sha256": sha256_file(ticket_path),
        "attach_command": shlex.join(argv),
    }


def prepare_operator_view(
    *,
    helper_argv: Sequence[str],
    ticket: Mapping[str, Any],
    state_root: Path,
    session: str,
    terminal: str,
    _application_exists: Optional[Callable[[Path], bool]] = None,
) -> Dict[str, Any]:
    """Persist a one-use, short-lived viewer doorway without opening it."""
    application_exists = _application_exists or (lambda path: path.is_dir())
    terminal_name, terminal_path = _select_terminal(
        terminal,
        application_exists=application_exists,
    )
    terminal_identity = _directory_identity(terminal_path)
    prepared = prepare_view_ticket(
        helper_argv=helper_argv,
        ticket=ticket,
        state_root=state_root,
        session=session,
    )
    ticket_path = Path(prepared["ticket_path"])
    command_path = ticket_path.with_suffix(".command")
    if command_path.exists():
        revoke_ticket(ticket_path)
        raise ConflictError("viewer command identity already exists")
    try:
        argv = _validate_command_argv(
            helper_argv,
            session=session,
            state_root=Path(state_root),
            ticket_path=ticket_path,
        )
        payload = (
            "#!/bin/sh\n"
            "set -eu\n"
            "# Human-only read-only native TUI viewer; Puppet never reads this pane.\n"
            "exec " + shlex.join(argv) + "\n"
        ).encode("utf-8")
        atomic_write_bytes(command_path, payload, mode=0o700)
        for path, mode in ((ticket_path, 0o600), (command_path, 0o700)):
            details = path.stat()
            if (
                path.is_symlink()
                or not path.is_file()
                or details.st_uid != os.getuid()
                or stat.S_IMODE(details.st_mode) != mode
            ):
                raise ValidationError("viewer artifact identity is unsafe")
    except BaseException:
        revoke_ticket(ticket_path)
        raise
    return {
        **prepared,
        "terminal_app": terminal_name,
        "terminal_app_path": terminal_identity["path"],
        "terminal_app_identity": terminal_identity,
        "viewer_command": str(command_path),
        "viewer_command_sha256": sha256_file(command_path),
    }


def dispatch_operator_view(
    prepared: Mapping[str, Any],
    *,
    _run: Optional[Callable[..., Any]] = None,
    _open_binary: Path = Path("/usr/bin/open"),
) -> None:
    """Submit one exact app/file request; attachment is verified elsewhere."""
    if not _open_binary.is_absolute() or not _open_binary.is_file():
        raise UnsupportedError("macOS open executable is unavailable")
    app_path = Path(str(prepared.get("terminal_app_path", "")))
    ticket_path = Path(str(prepared.get("ticket_path", "")))
    command_path = Path(str(prepared.get("viewer_command", "")))
    if (
        _directory_identity(app_path) != prepared.get("terminal_app_identity")
        or not ticket_path.is_absolute()
        or ticket_path.is_symlink()
        or not ticket_path.is_file()
        or sha256_file(ticket_path) != prepared.get("ticket_sha256")
        or not command_path.is_absolute()
        or command_path.is_symlink()
        or not command_path.is_file()
        or sha256_file(command_path) != prepared.get("viewer_command_sha256")
    ):
        raise ValidationError("viewer dispatch identity changed")
    runner = _run or subprocess.run
    result = runner(
        [str(_open_binary), "-a", str(app_path), str(command_path)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=10,
        check=False,
        env={"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"},
    )
    if result.returncode != 0:
        raise UnsupportedError("visible operator terminal launch request failed")


def build_view_ticket(
    *,
    session: str,
    state_root: Path,
    expected_identity: Mapping[str, Any],
    helper_path: Path,
    interpreter_path: Path,
    now: Optional[float] = None,
) -> Dict[str, Any]:
    validate_identifier(session, "session")
    root = absolute_root(str(state_root), "state root")
    helper_identity = _regular_file_identity(Path(helper_path))
    interpreter_identity = _regular_file_identity(
        Path(interpreter_path), executable=True
    )
    issued_at = time.time() if now is None else now
    if not isinstance(issued_at, (int, float)) or isinstance(issued_at, bool):
        raise ValidationError("viewer ticket clock is invalid")
    nonce = secrets.token_hex(16)
    return {
        "schema": TICKET_SCHEMA,
        "nonce": nonce,
        "session": session,
        "state_root_sha256": sha256_bytes(str(root).encode("utf-8")),
        "issued_at": float(issued_at),
        "expires_at": float(issued_at + TICKET_TTL_SECONDS),
        "helper_identity": helper_identity,
        "interpreter_identity": interpreter_identity,
        "expected_identity": _validate_expected_identity(expected_identity),
    }


def load_and_claim_ticket(
    *,
    ticket_path: Path,
    state_root: Path,
    session: str,
    helper_path: Path,
    interpreter_path: Path,
    claimant_pid: int,
    claimant_kernel_birth_id: str,
    now: Optional[float] = None,
) -> Dict[str, Any]:
    """Load and claim one short-lived ticket before runtime revalidation."""
    validate_identifier(session, "session")
    views = _private_view_root(state_root)
    ticket_path = ensure_within(Path(ticket_path), views)
    if ticket_path.parent != views or ticket_path.suffix != ".json":
        raise ValidationError("viewer ticket path is invalid")
    ticket = read_json(ticket_path, max_bytes=16384)
    required = {
        "schema",
        "nonce",
        "session",
        "state_root_sha256",
        "issued_at",
        "expires_at",
        "helper_identity",
        "interpreter_identity",
        "expected_identity",
    }
    if set(ticket) != required or ticket.get("schema") != TICKET_SCHEMA:
        raise ValidationError("viewer ticket fields are invalid")
    nonce = ticket.get("nonce")
    validate_identifier(nonce, "viewer ticket nonce")
    if ticket_path.name != session + "-" + nonce + ".json":
        raise ValidationError("viewer ticket filename identity changed")
    if ticket.get("session") != session:
        raise ValidationError("viewer ticket session changed")
    root = absolute_root(str(state_root), "state root")
    if ticket.get("state_root_sha256") != sha256_bytes(str(root).encode("utf-8")):
        raise ValidationError("viewer ticket state root changed")
    if ticket.get("helper_identity") != _regular_file_identity(Path(helper_path)):
        raise ValidationError("viewer helper identity changed")
    if ticket.get("interpreter_identity") != _regular_file_identity(
        Path(interpreter_path), executable=True
    ):
        raise ValidationError("viewer interpreter identity changed")
    _validate_expected_identity(ticket.get("expected_identity"))
    observed = time.time() if now is None else now
    issued_at = ticket.get("issued_at")
    expires_at = ticket.get("expires_at")
    if (
        not isinstance(issued_at, (int, float))
        or isinstance(issued_at, bool)
        or not isinstance(expires_at, (int, float))
        or isinstance(expires_at, bool)
        or issued_at > observed
        or expires_at <= observed
        or expires_at - issued_at != TICKET_TTL_SECONDS
    ):
        raise ValidationError("viewer ticket is expired or malformed")
    revoked = ticket_path.with_suffix(".revoked")
    if _marker_payload(revoked) is not None:
        raise ConflictError("viewer ticket was revoked")
    claimed = ticket_path.with_suffix(".claimed")
    claim = _validate_claim_identity(
        {
            "schema": CLAIM_SCHEMA,
            "pid": claimant_pid,
            "kernel_birth_id": claimant_kernel_birth_id,
        }
    )
    try:
        _create_marker(claimed, claim)
    except ConflictError as exc:
        raise ConflictError("viewer ticket was already claimed") from exc
    if _marker_payload(revoked) is not None:
        raise ConflictError("viewer ticket was revoked during claim")
    return ticket


def _validate_claim_identity(value: Any) -> Dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {
        "schema",
        "pid",
        "kernel_birth_id",
    }:
        raise ValidationError("viewer claim fields are invalid")
    if value.get("schema") != CLAIM_SCHEMA:
        raise ValidationError("viewer claim schema is invalid")
    pid = value.get("pid")
    birth = value.get("kernel_birth_id")
    if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 1:
        raise ValidationError("viewer claimant process identity is invalid")
    if (
        not isinstance(birth, str)
        or not birth
        or len(birth) > 200
        or any(marker in birth for marker in ("\x00", "\n", "\r"))
    ):
        raise ValidationError("viewer claimant birth identity is invalid")
    return dict(value)


def _marker_payload(path: Path) -> Optional[Dict[str, Any]]:
    path = Path(path)
    try:
        details = path.lstat()
    except FileNotFoundError:
        return None
    if (
        not stat.S_ISREG(details.st_mode)
        or details.st_uid != os.getuid()
        or stat.S_IMODE(details.st_mode) != 0o600
    ):
        raise ValidationError("viewer marker identity is unsafe")
    return read_json(path, max_bytes=1024)


def _create_marker(path: Path, payload: Mapping[str, Any]) -> None:
    path = Path(path)
    raw = canonical_json_bytes(dict(payload)) + b"\n"
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".viewer-marker.", dir=str(path.parent)
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        written = 0
        while written < len(raw):
            count = os.write(descriptor, raw[written:])
            if count <= 0:
                raise ValidationError("viewer marker write failed")
            written += count
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        details = temporary.lstat()
        if (
            not stat.S_ISREG(details.st_mode)
            or details.st_uid != os.getuid()
            or stat.S_IMODE(details.st_mode) != 0o600
        ):
            raise ValidationError("viewer temporary marker identity is unsafe")
        try:
            os.link(temporary, path, follow_symlinks=False)
        except FileExistsError as exc:
            _marker_payload(path)
            raise ConflictError("viewer marker identity already exists") from exc
        directory = os.open(str(path.parent), os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def revoke_ticket(ticket_path: Path) -> None:
    revoked = Path(ticket_path).with_suffix(".revoked")
    existing = _marker_payload(revoked)
    if existing is not None:
        if existing != {"schema": REVOCATION_SCHEMA}:
            raise ValidationError("viewer revocation marker is invalid")
        return
    try:
        _create_marker(revoked, {"schema": REVOCATION_SCHEMA})
    except ConflictError:
        existing = _marker_payload(revoked)
        if existing != {"schema": REVOCATION_SCHEMA}:
            raise ValidationError("viewer revocation marker is invalid")


def ticket_claim_identity(ticket_path: Path) -> Optional[Dict[str, Any]]:
    """Return the exact helper claimant identity without reading the target TUI."""
    payload = _marker_payload(Path(ticket_path).with_suffix(".claimed"))
    return None if payload is None else _validate_claim_identity(payload)


def ticket_is_revoked(ticket_path: Path) -> bool:
    payload = _marker_payload(Path(ticket_path).with_suffix(".revoked"))
    if payload is None:
        return False
    if payload != {"schema": REVOCATION_SCHEMA}:
        raise ValidationError("viewer revocation marker is invalid")
    return True
