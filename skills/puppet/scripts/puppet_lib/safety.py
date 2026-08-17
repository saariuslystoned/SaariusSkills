"""Containment, canonicalization, atomic-write, and input-safety primitives."""

from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
import re
import stat
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterator, Mapping, Optional

from .errors import ValidationError


IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
PANE_ID_RE = re.compile(r"^%[0-9]+$")
SHA1_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
BRANCH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,199}$")
SECRET_TEXT_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\b(?:ghp|github_pat|sk|xox[baprs])-[-A-Za-z0-9_]{12,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
)
FORBIDDEN_FIELD_PARTS = {
    "auth_log",
    "cookie",
    "credential",
    "environment",
    "pane",
    "password",
    "private_key",
    "prompt",
    "raw_log",
    "scrollback",
    "secret",
    "session_store",
    "token",
    "tool_argument",
    "transcript",
}
_TMUX_SOCKET_IDENTITY_FIELDS = frozenset({"device", "inode", "uid", "mode"})


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path, max_bytes: Optional[int] = None) -> str:
    path = Path(path)
    if path.is_symlink():
        raise ValidationError("refusing to hash a symlink")
    digest = hashlib.sha256()
    total = 0
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            total += len(block)
            if max_bytes is not None and total > max_bytes:
                raise ValidationError("file exceeds the allowed size")
            digest.update(block)
    return digest.hexdigest()


def canonical_tmux_socket_mode(mode: int) -> int:
    """Exclude only tmux's owner-execute attached-client state bit."""

    if type(mode) is not int or mode < 0:
        raise ValidationError("tmux socket mode is invalid")
    return stat.S_IMODE(mode) & ~stat.S_IXUSR


def tmux_socket_identities_match(first: Any, second: Any) -> bool:
    """Compare private tmux sockets while ignoring only owner-execute state."""

    if not isinstance(first, Mapping) or not isinstance(second, Mapping):
        return False
    if set(first) != _TMUX_SOCKET_IDENTITY_FIELDS or set(second) != set(first):
        return False
    if any(
        type(identity[field]) is not int
        or identity[field] < 0
        or (field == "mode" and identity[field] > 0o7777)
        for identity in (first, second)
        for field in _TMUX_SOCKET_IDENTITY_FIELDS
    ):
        return False
    first_mode = stat.S_IMODE(first["mode"])
    second_mode = stat.S_IMODE(second["mode"])
    if first_mode & 0o077 or second_mode & 0o077:
        return False
    return (
        first["device"] == second["device"]
        and first["inode"] == second["inode"]
        and first["uid"] == second["uid"]
        and canonical_tmux_socket_mode(first_mode)
        == canonical_tmux_socket_mode(second_mode)
    )


def validate_identifier(value: str, label: str = "identifier") -> str:
    if not isinstance(value, str) or not IDENTIFIER_RE.fullmatch(value):
        raise ValidationError("invalid %s" % label)
    return value


def validate_pane_id(value: str) -> str:
    if not isinstance(value, str) or not PANE_ID_RE.fullmatch(value):
        raise ValidationError("invalid tmux pane identity")
    return value


def canonical_tmux_socket_path(state_root: Path, session: str) -> Path:
    """Return a short, deterministic, user-private socket for a state/session pair."""
    validate_identifier(session, "session")
    root = Path(state_root).resolve(strict=True)
    base = Path("/tmp") / ("puppet-tmux-%d" % os.getuid())
    if base.exists() and base.is_symlink():
        raise ValidationError("tmux socket root must not be a symlink")
    base.mkdir(mode=0o700, exist_ok=True)
    details = base.stat()
    if details.st_uid != os.getuid() or details.st_mode & 0o077:
        raise ValidationError("tmux socket root is not user-private")
    digest = sha256_bytes((str(root) + "\x00" + session).encode("utf-8"))
    path = base / (digest[:32] + ".sock")
    if len(str(path).encode("utf-8")) > 100:
        raise ValidationError("tmux socket path exceeds the safe bound")
    return path


def validate_branch(value: str) -> str:
    if (
        not isinstance(value, str)
        or not BRANCH_RE.fullmatch(value)
        or ".." in value
        or "@{" in value
        or value.endswith("/")
        or "//" in value
    ):
        raise ValidationError("invalid branch")
    return value


def validate_sha1(value: str, label: str = "commit") -> str:
    if not isinstance(value, str) or not SHA1_RE.fullmatch(value):
        raise ValidationError("%s must be a full 40-character lowercase SHA" % label)
    return value


def validate_sha256(value: str, label: str = "fingerprint") -> str:
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        raise ValidationError("%s must be a lowercase SHA-256" % label)
    return value


def reject_symlink_components(path: Path, allow_missing_leaf: bool = False) -> None:
    """Reject a symlink leaf; callers enforce resolved-root containment.

    macOS exposes ordinary temporary roots through system symlinks such as
    `/var` -> `/private/var`. Resolving both the authority root and target is
    the portable containment boundary; rejecting every lexical ancestor would
    make safe system paths unusable.
    """
    path = Path(path)
    if path.exists() and path.is_symlink():
        raise ValidationError("symlink paths are not allowed")
    if not path.exists() and not allow_missing_leaf:
        raise ValidationError("path does not exist")
    if path.parent.exists():
        path.parent.resolve(strict=True)


def absolute_root(path: str, label: str = "root", must_exist: bool = True) -> Path:
    if not isinstance(path, str) or not path:
        raise ValidationError("%s must be an absolute path" % label)
    candidate = Path(path)
    if not candidate.is_absolute():
        raise ValidationError("%s must be absolute" % label)
    reject_symlink_components(candidate, allow_missing_leaf=not must_exist)
    if must_exist and not candidate.is_dir():
        raise ValidationError("%s is not an existing directory" % label)
    return candidate.resolve(strict=must_exist)


def ensure_within(path: Path, root: Path, must_exist: bool = True) -> Path:
    path = Path(path)
    root = Path(root).resolve(strict=True)
    reject_symlink_components(path, allow_missing_leaf=not must_exist)
    resolved = path.resolve(strict=must_exist)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValidationError("path escapes its declared root") from exc
    return resolved


def paths_overlap(first: Path, second: Path) -> bool:
    first = Path(first).resolve(strict=False)
    second = Path(second).resolve(strict=False)
    try:
        first.relative_to(second)
        return True
    except ValueError:
        pass
    try:
        second.relative_to(first)
        return True
    except ValueError:
        return False


def validate_bounded_json(
    value: Any,
    *,
    max_depth: int = 8,
    max_items: int = 64,
    max_string: int = 4096,
    reject_sensitive_fields: bool = False,
    _depth: int = 0,
) -> None:
    if _depth > max_depth:
        raise ValidationError("JSON nesting exceeds the limit")
    if isinstance(value, dict):
        if len(value) > max_items:
            raise ValidationError("JSON object exceeds the field limit")
        for key, item in value.items():
            if not isinstance(key, str) or len(key) > 80:
                raise ValidationError("invalid JSON field name")
            normalized = key.lower().replace("-", "_")
            if reject_sensitive_fields and any(part in normalized for part in FORBIDDEN_FIELD_PARTS):
                raise ValidationError("forbidden secret or transcript-shaped field")
            validate_bounded_json(
                item,
                max_depth=max_depth,
                max_items=max_items,
                max_string=max_string,
                reject_sensitive_fields=reject_sensitive_fields,
                _depth=_depth + 1,
            )
    elif isinstance(value, list):
        if len(value) > max_items:
            raise ValidationError("JSON list exceeds the item limit")
        for item in value:
            validate_bounded_json(
                item,
                max_depth=max_depth,
                max_items=max_items,
                max_string=max_string,
                reject_sensitive_fields=reject_sensitive_fields,
                _depth=_depth + 1,
            )
    elif isinstance(value, str):
        if len(value) > max_string:
            raise ValidationError("JSON string exceeds the size limit")
        if any(pattern.search(value) for pattern in SECRET_TEXT_PATTERNS):
            raise ValidationError("secret-shaped text is forbidden")
    elif value is not None and not isinstance(value, (bool, int, float)):
        raise ValidationError("unsupported JSON value type")
    elif isinstance(value, float):
        import math

        if not math.isfinite(value):
            raise ValidationError("non-finite JSON numbers are forbidden")


def read_json(
    path: Path, max_bytes: int = 65536, reject_sensitive_fields: bool = False
) -> Dict[str, Any]:
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValidationError("JSON input must be a regular non-symlink file")
    raw = path.read_bytes()
    if len(raw) > max_bytes:
        raise ValidationError("JSON input exceeds the size limit")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValidationError("invalid JSON input") from exc
    if not isinstance(value, dict):
        raise ValidationError("JSON root must be an object")
    validate_bounded_json(value, reject_sensitive_fields=reject_sensitive_fields)
    return value


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(str(path), os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def atomic_write_bytes(path: Path, payload: bytes, mode: int = 0o600) -> None:
    path = Path(path)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    reject_symlink_components(path, allow_missing_leaf=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".%s." % path.name, dir=str(path.parent))
    try:
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    except Exception:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temporary)
        raise


def atomic_write_json(path: Path, value: Dict[str, Any]) -> None:
    validate_bounded_json(value, max_items=256, max_string=8192)
    atomic_write_bytes(path, canonical_json_bytes(value) + b"\n")


@contextlib.contextmanager
def exclusive_lock(path: Path) -> Iterator[None]:
    path = Path(path)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    reject_symlink_components(path, allow_missing_leaf=True)
    flags = os.O_CREAT | os.O_RDWR
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(str(path), flags, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)
