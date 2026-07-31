from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from pathlib import Path
from typing import Any


MARKER_SCHEMA = "herdr-puppet.claude-hook-marker.v1"
RECEIPT_SCHEMA = "herdr-puppet.claude-hook-receipt.v1"
OVERFLOW_SCHEMA = "herdr-puppet.claude-hook-overflow.v1"
OVERFLOW_NAME = "overflow.json"
EVENT_LIMITS = {
    "session_start": 1,
    "user_prompt_submit": 2,
    "stop": 2,
    "stop_failure": 2,
}
MAX_MARKER_FILES = sum(EVENT_LIMITS.values()) + 1
MAX_MARKER_BYTES = 2048
MAX_HOOK_INPUT_BYTES = 2 * 1024 * 1024

_SAFE_RUN_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MARKER_NAME = re.compile(
    r"^(session_start|user_prompt_submit|stop|stop_failure)-([0-9]{4})\.json$"
)


class ClaudeHookMarkerError(RuntimeError):
    pass


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def marker_payload(
    *,
    run_id: str,
    probe_id: str,
    event: str,
    ordinal: int,
    prompt_sha256: str | None = None,
) -> dict[str, Any]:
    if event == "user_prompt_submit":
        if (
            not isinstance(prompt_sha256, str)
            or _SHA256.fullmatch(prompt_sha256) is None
        ):
            raise ClaudeHookMarkerError(
                "user prompt marker requires a prompt fingerprint"
            )
    elif prompt_sha256 is not None:
        raise ClaudeHookMarkerError(
            "only user prompt markers may carry a prompt fingerprint"
        )
    payload = {
        "schema": MARKER_SCHEMA,
        "run_id": run_id,
        "probe_id": probe_id,
        "event": event,
        "ordinal": ordinal,
        "stdin_read": event == "user_prompt_submit",
        "raw_input_retained": False,
    }
    if prompt_sha256 is not None:
        payload["prompt_sha256"] = prompt_sha256
    return payload


def _validate_identity(run_id: str, probe_id: str) -> None:
    if _SAFE_RUN_ID.fullmatch(run_id) is None:
        raise ClaudeHookMarkerError("invalid run id")
    if _SHA256.fullmatch(probe_id) is None:
        raise ClaudeHookMarkerError("invalid probe id")


def _normalized_root(value: str) -> Path:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ClaudeHookMarkerError("invalid marker root")
    root = Path(value)
    if not root.is_absolute() or root == Path("/"):
        raise ClaudeHookMarkerError("invalid marker root")
    if root != Path(os.path.normpath(value)) or root.name in {"", ".", ".."}:
        raise ClaudeHookMarkerError("invalid marker root")
    try:
        parent = root.parent.resolve(strict=True)
    except OSError as exc:
        raise ClaudeHookMarkerError("marker parent unavailable") from exc
    parent_stat = parent.stat()
    if not stat.S_ISDIR(parent_stat.st_mode) or parent_stat.st_uid != os.getuid():
        raise ClaudeHookMarkerError("marker parent is not caller-owned")
    return parent / root.name


def validate_absent_root(value: str) -> Path:
    root = _normalized_root(value)
    if root.exists() or root.is_symlink():
        raise ClaudeHookMarkerError("marker root must be absent")
    return root


def _validate_live_root(root: Path) -> None:
    if root.is_symlink():
        raise ClaudeHookMarkerError("marker root must not be a symlink")
    try:
        root_stat = root.stat()
    except OSError as exc:
        raise ClaudeHookMarkerError("marker root unavailable") from exc
    if (
        not stat.S_ISDIR(root_stat.st_mode)
        or root_stat.st_uid != os.getuid()
        or stat.S_IMODE(root_stat.st_mode) != 0o700
    ):
        raise ClaudeHookMarkerError("marker root is not an owned 0700 directory")


def _read_owned_marker(path: Path) -> bytes:
    descriptor: int | None = None
    try:
        flags = os.O_RDONLY
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        if hasattr(os, "O_NONBLOCK"):
            flags |= os.O_NONBLOCK
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(path, flags)
        path_stat = os.fstat(descriptor)
        if (
            not stat.S_ISREG(path_stat.st_mode)
            or path_stat.st_uid != os.getuid()
            or stat.S_IMODE(path_stat.st_mode) != 0o600
            or path_stat.st_size > MAX_MARKER_BYTES
        ):
            raise ClaudeHookMarkerError(
                "marker is not an owned bounded 0600 file"
            )
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            encoded = stream.read(MAX_MARKER_BYTES + 1)
        if len(encoded) > MAX_MARKER_BYTES:
            raise ClaudeHookMarkerError(
                "marker is not an owned bounded 0600 file"
            )
        return encoded
    except ClaudeHookMarkerError:
        raise
    except OSError as exc:
        raise ClaudeHookMarkerError("marker is unavailable") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _scan_markers(
    root: Path,
    *,
    run_id: str,
    probe_id: str,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    _validate_live_root(root)
    markers: list[dict[str, Any]] = []
    ordinals: dict[str, list[int]] = {event: [] for event in EVENT_LIMITS}
    try:
        entry_names: list[str] = []
        with os.scandir(root) as entries:
            for entry in entries:
                if len(entry_names) >= MAX_MARKER_FILES:
                    raise ClaudeHookMarkerError(
                        "marker root exceeds its bounded entry count"
                    )
                entry_names.append(entry.name)
    except OSError as exc:
        raise ClaudeHookMarkerError("marker root cannot be scanned") from exc
    for name in sorted(entry_names):
        path = root / name
        if name == OVERFLOW_NAME:
            raise ClaudeHookMarkerError(
                "marker root records an overflow or hook conflict"
            )
        matched = _MARKER_NAME.fullmatch(path.name)
        if matched is None:
            raise ClaudeHookMarkerError("marker root contains an unexpected entry")
        event = matched.group(1)
        ordinal = int(matched.group(2))
        if ordinal < 1 or ordinal > EVENT_LIMITS[event]:
            raise ClaudeHookMarkerError("marker ordinal exceeds its bound")
        try:
            encoded = _read_owned_marker(path)
            payload = json.loads(encoded.decode("utf-8"))
        except (
            UnicodeDecodeError,
            json.JSONDecodeError,
        ) as exc:
            raise ClaudeHookMarkerError(
                "marker content is not canonical"
            ) from exc
        if not isinstance(payload, dict):
            raise ClaudeHookMarkerError("marker content is not canonical")
        expected_fields = {
            "schema",
            "run_id",
            "probe_id",
            "event",
            "ordinal",
            "stdin_read",
            "raw_input_retained",
        }
        if event == "user_prompt_submit":
            expected_fields.add("prompt_sha256")
        if set(payload) != expected_fields:
            raise ClaudeHookMarkerError("marker content is not canonical")
        expected = canonical_bytes(
            marker_payload(
                run_id=run_id,
                probe_id=probe_id,
                event=event,
                ordinal=ordinal,
                prompt_sha256=payload.get("prompt_sha256"),
            )
        ) + b"\n"
        if encoded != expected:
            raise ClaudeHookMarkerError("marker content is not canonical")
        ordinals[event].append(ordinal)
        marker = {
            "event": event,
            "ordinal": ordinal,
            "sha256": sha256_bytes(encoded),
        }
        if event == "user_prompt_submit":
            marker["prompt_sha256"] = payload["prompt_sha256"]
        markers.append(marker)
    counts: dict[str, int] = {}
    for event, observed in ordinals.items():
        expected_ordinals = list(range(1, len(observed) + 1))
        if observed != expected_ordinals:
            raise ClaudeHookMarkerError("marker ordinals are not contiguous")
        counts[event] = len(observed)
    return markers, counts


def _write_overflow_sentinel(
    root: Path,
    *,
    run_id: str,
    probe_id: str,
    event: str,
) -> None:
    _validate_live_root(root)
    sentinel = root / OVERFLOW_NAME
    if sentinel.exists() and not sentinel.is_symlink():
        return
    encoded = canonical_bytes(
        {
            "schema": OVERFLOW_SCHEMA,
            "run_id": run_id,
            "probe_id": probe_id,
            "event": event,
            "raw_input_retained": False,
        }
    ) + b"\n"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(sentinel, flags, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb", closefd=False) as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(descriptor)
    finally:
        os.close(descriptor)
    directory_descriptor = os.open(root, os.O_RDONLY)
    try:
        os.fsync(directory_descriptor)
    finally:
        os.close(directory_descriptor)


def record_event(
    *,
    root_value: str,
    run_id: str,
    probe_id: str,
    event: str,
    prompt_sha256: str | None = None,
) -> None:
    _validate_identity(run_id, probe_id)
    if event not in EVENT_LIMITS:
        raise ClaudeHookMarkerError("unsupported hook event")
    if event == "user_prompt_submit":
        if (
            not isinstance(prompt_sha256, str)
            or _SHA256.fullmatch(prompt_sha256) is None
        ):
            raise ClaudeHookMarkerError(
                "user prompt hook input is unavailable"
            )
    elif prompt_sha256 is not None:
        raise ClaudeHookMarkerError(
            "non-prompt hook input must remain unread"
        )
    root = _normalized_root(root_value)
    if event == "session_start":
        if root.exists() or root.is_symlink():
            if root.exists() and not root.is_symlink():
                _write_overflow_sentinel(
                    root,
                    run_id=run_id,
                    probe_id=probe_id,
                    event=event,
                )
            raise ClaudeHookMarkerError("session marker root already exists")
        try:
            os.mkdir(root, 0o700)
            os.chmod(root, 0o700)
        except OSError as exc:
            raise ClaudeHookMarkerError("session marker root was not created") from exc
    markers, counts = _scan_markers(
        root,
        run_id=run_id,
        probe_id=probe_id,
    )
    del markers
    ordinal = counts[event] + 1
    if ordinal > EVENT_LIMITS[event]:
        _write_overflow_sentinel(
            root,
            run_id=run_id,
            probe_id=probe_id,
            event=event,
        )
        raise ClaudeHookMarkerError("hook event marker limit reached")
    marker_path = root / f"{event}-{ordinal:04d}.json"
    encoded = canonical_bytes(
        marker_payload(
            run_id=run_id,
            probe_id=probe_id,
            event=event,
            ordinal=ordinal,
            prompt_sha256=prompt_sha256,
        )
    ) + b"\n"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(marker_path, flags, 0o600)
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "wb", closefd=False) as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(descriptor)
        finally:
            os.close(descriptor)
        directory_descriptor = os.open(root, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except OSError as exc:
        raise ClaudeHookMarkerError("hook marker was not created") from exc


def observe(
    *,
    root_value: str,
    run_id: str,
    probe_id: str,
) -> dict[str, Any]:
    _validate_identity(run_id, probe_id)
    root = _normalized_root(root_value)
    markers, counts = _scan_markers(
        root,
        run_id=run_id,
        probe_id=probe_id,
    )
    return {
        "schema": RECEIPT_SCHEMA,
        "run_id": run_id,
        "probe_id": probe_id,
        "markers": markers,
        "counts": counts,
        "marker_set_sha256": sha256_bytes(canonical_bytes(markers)),
        "stdin_read": counts["user_prompt_submit"] > 0,
        "raw_input_retained": False,
        "transcript_read": False,
    }


def _prompt_sha256_from_stdin() -> str:
    stream = getattr(os.sys.stdin, "buffer", os.sys.stdin)
    encoded = stream.read(MAX_HOOK_INPUT_BYTES + 1)
    if isinstance(encoded, str):
        encoded = encoded.encode("utf-8")
    if len(encoded) > MAX_HOOK_INPUT_BYTES:
        raise ClaudeHookMarkerError("hook input exceeds its bound")
    try:
        payload = json.loads(encoded.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ClaudeHookMarkerError("hook input is malformed") from exc
    if (
        not isinstance(payload, dict)
        or payload.get("hook_event_name") != "UserPromptSubmit"
        or not isinstance(payload.get("prompt"), str)
    ):
        raise ClaudeHookMarkerError("user prompt hook input is invalid")
    prompt = payload["prompt"].encode("utf-8")
    if len(prompt) > 256 * 1024:
        raise ClaudeHookMarkerError("user prompt exceeds its bound")
    return sha256_bytes(prompt)


def main(argv: list[str] | None = None) -> int:
    args = list(argv if argv is not None else os.sys.argv[1:])
    operation = args[0] if args else None
    try:
        if len(args) not in {7, 9}:
            raise ClaudeHookMarkerError("invalid arguments")
        operation = args[0]
        pairs = args[1:]
        if len(pairs) % 2:
            raise ClaudeHookMarkerError("invalid arguments")
        values = dict(zip(pairs[::2], pairs[1::2], strict=True))
        if len(values) * 2 != len(pairs):
            raise ClaudeHookMarkerError("duplicate arguments")
        required = {"--root", "--run-id", "--probe-id"}
        if operation == "record":
            required.add("--event")
        if set(values) != required:
            raise ClaudeHookMarkerError("invalid arguments")
        if operation == "record":
            prompt_sha256 = (
                _prompt_sha256_from_stdin()
                if values["--event"] == "user_prompt_submit"
                else None
            )
            record_event(
                root_value=values["--root"],
                run_id=values["--run-id"],
                probe_id=values["--probe-id"],
                event=values["--event"],
                prompt_sha256=prompt_sha256,
            )
            return 0
        if operation == "observe":
            receipt = observe(
                root_value=values["--root"],
                run_id=values["--run-id"],
                probe_id=values["--probe-id"],
            )
            os.sys.stdout.buffer.write(canonical_bytes(receipt) + b"\n")
            return 0
        raise ClaudeHookMarkerError("unsupported operation")
    except Exception:
        # Proof collection is observational. A failed record must never reject
        # a prompt or keep Claude running; the missing marker makes the
        # controller receipt fail closed later.
        return 0 if operation == "record" else 2
