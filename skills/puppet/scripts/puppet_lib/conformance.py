"""Shared source-free real-harness conformance fixture contracts."""

from __future__ import annotations

import secrets
from pathlib import Path
from typing import Any, Dict

from .handoffs import PROTOCOL_FINGERPRINT
from .safety import atomic_write_json, canonical_json_bytes, sha256_bytes, validate_identifier


def create_fixture(root: Path, *, run_id: str, session: str, target: str) -> Dict[str, Any]:
    validate_identifier(run_id, "run id")
    validate_identifier(session, "session")
    if target not in {"agy", "cursor", "claude", "codex", "grok"}:
        raise ValueError("unsupported target")
    root = Path(root)
    root.mkdir(mode=0o700, parents=True, exist_ok=False)
    handoffs = root / "handoffs"
    handoffs.mkdir(mode=0o700)
    nonce = secrets.token_hex(16)
    contract = {
        "schema_version": 1,
        "checkpoint_kind": "conformance",
        "run_id": run_id,
        "session": session,
        "nonce": nonce,
        "target": target,
        "protocol_fingerprint": PROTOCOL_FINGERPRINT,
        "allowed_fixture_root": str(root.resolve(strict=True)),
        "allowed_actions": ["read_contract", "write_bounded_handoffs", "wait_for_halt"],
        "forbidden_actions": [
            "source_mutation",
            "repository_mutation",
            "account_change",
            "external_send",
            "system_change",
        ],
    }
    atomic_write_json(root / "contract.json", contract)
    return contract


def tree_fingerprint(root: Path, excluded_prefix: str = "handoffs") -> str:
    root = Path(root).resolve(strict=True)
    rows = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if (
            relative == excluded_prefix
            or relative.startswith(excluded_prefix + "/")
            or relative == ".git"
            or relative.startswith(".git/")
        ):
            continue
        if path.is_symlink():
            raise ValueError("fixture contains a symlink")
        if path.is_file():
            rows.append({"path": relative, "sha256": sha256_bytes(path.read_bytes())})
    return sha256_bytes(canonical_json_bytes(rows))
