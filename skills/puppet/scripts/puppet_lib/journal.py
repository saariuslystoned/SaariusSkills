"""Hash-chained, idempotent, append-only Puppet event journal."""

from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from .errors import ConflictError, ValidationError
from .safety import (
    atomic_write_json,
    canonical_json_bytes,
    exclusive_lock,
    read_json,
    sha256_bytes,
    validate_bounded_json,
    validate_identifier,
)


ZERO_HASH = "0" * 64


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class Journal:
    def __init__(self, root: Path):
        requested_root = Path(root)
        requested_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if requested_root.is_symlink():
            raise ValidationError("journal root must not be a symlink")
        self.root = requested_root.resolve(strict=True)
        self.events_path = self.root / "events.jsonl"
        self.head_path = self.root / "journal-head.json"
        self.lock_path = self.root / ".journal.lock"

    def replay(self) -> List[Dict[str, Any]]:
        if not self.events_path.exists():
            return []
        if self.events_path.is_symlink():
            raise ValidationError("journal must not be a symlink")
        rows = []
        previous = ZERO_HASH
        with self.events_path.open("rb") as handle:
            for number, raw in enumerate(handle, start=1):
                if not raw.endswith(b"\n"):
                    raise ValidationError("journal contains a truncated row")
                try:
                    row = json.loads(raw.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise ValidationError("journal contains invalid JSON") from exc
                if not isinstance(row, dict) or row.get("sequence") != number:
                    raise ValidationError("journal sequence is invalid")
                if row.get("previous_hash") != previous:
                    raise ValidationError("journal hash chain is invalid")
                entry_hash = row.get("entry_hash")
                unsigned = dict(row)
                unsigned.pop("entry_hash", None)
                expected = sha256_bytes(canonical_json_bytes(unsigned))
                if entry_hash != expected:
                    raise ValidationError("journal entry hash is invalid")
                rows.append(row)
                previous = entry_hash
        return rows

    def _expected_head(self, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not rows:
            return {"sequence": 0, "entry_hash": ZERO_HASH}
        return {"sequence": rows[-1]["sequence"], "entry_hash": rows[-1]["entry_hash"]}

    def _read_head(self) -> Optional[Dict[str, Any]]:
        if not self.head_path.exists():
            return None
        head = read_json(self.head_path, max_bytes=4096)
        if not isinstance(head, dict):
            raise ValidationError("journal head is invalid")
        if set(head.keys()) != {"sequence", "entry_hash"}:
            raise ValidationError("journal head is invalid")
        if not isinstance(head.get("sequence"), int) or head["sequence"] < 0:
            raise ValidationError("journal head is invalid")
        if not isinstance(head.get("entry_hash"), str):
            raise ValidationError("journal head is invalid")
        return head

    def _repair_head(self, rows: List[Dict[str, Any]]) -> None:
        expected = self._expected_head(rows)
        head = self._read_head()

        if head is None:
            atomic_write_json(self.head_path, expected)
            return

        if head == expected:
            return

        if not rows:
            raise ValidationError("journal head does not match append history")

        if head["sequence"] > expected["sequence"]:
            raise ValidationError("journal head does not match append history")

        if head["sequence"] > 0:
            claimed = rows[head["sequence"] - 1]
            if claimed["entry_hash"] != head["entry_hash"]:
                raise ValidationError("journal head does not match append history")
        elif head["entry_hash"] != ZERO_HASH:
            raise ValidationError("journal head does not match append history")

        atomic_write_json(self.head_path, expected)

    def lookup(self, request_id: str) -> Optional[Dict[str, Any]]:
        validate_identifier(request_id, "request id")
        with exclusive_lock(self.lock_path):
            rows = self.replay()
            self._repair_head(rows)
            for row in rows:
                if row["request_id"] == request_id:
                    return row
            return None

    def snapshot(self) -> List[Dict[str, Any]]:
        with exclusive_lock(self.lock_path):
            rows = self.replay()
            self._repair_head(rows)
            return list(rows)

    def append(
        self,
        *,
        request_id: str,
        event: Dict[str, Any],
        timestamp: Optional[str] = None,
    ) -> Dict[str, Any]:
        validate_identifier(request_id, "request id")
        if not isinstance(event, dict) or not event:
            raise ValidationError("journal event must be a non-empty object")
        validate_bounded_json(
            event, max_items=128, max_string=4096, reject_sensitive_fields=True
        )
        with exclusive_lock(self.lock_path):
            rows = self.replay()
            self._repair_head(rows)
            for row in rows:
                if row["request_id"] == request_id:
                    if row["event"] != event:
                        raise ConflictError("request id was already used for another event")
                    return row
            previous = rows[-1]["entry_hash"] if rows else ZERO_HASH
            unsigned = {
                "schema_version": 1,
                "sequence": len(rows) + 1,
                "previous_hash": previous,
                "request_id": request_id,
                "timestamp": timestamp or _utc_now(),
                "event": event,
            }
            row = dict(unsigned)
            row["entry_hash"] = sha256_bytes(canonical_json_bytes(unsigned))
            payload = canonical_json_bytes(row) + b"\n"
            flags = os.O_CREAT | os.O_APPEND | os.O_WRONLY
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            descriptor = os.open(str(self.events_path), flags, 0o600)
            try:
                offset = 0
                while offset < len(payload):
                    offset += os.write(descriptor, payload[offset:])
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            atomic_write_json(
                self.head_path,
                {"sequence": row["sequence"], "entry_hash": row["entry_hash"]},
            )
            return row
