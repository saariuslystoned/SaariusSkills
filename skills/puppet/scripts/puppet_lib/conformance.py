"""Shared source-free real-harness conformance fixture contracts."""

from __future__ import annotations

import secrets
from pathlib import Path
from typing import Any, Dict

from .errors import UnsupportedError, ValidationError
from .handoffs import PROTOCOL_FINGERPRINT
from .safety import (
    atomic_write_bytes,
    atomic_write_json,
    canonical_json_bytes,
    sha256_bytes,
    validate_identifier,
)


CONFORMANCE_CONTRACT_SCHEMA_VERSION = 2
LEGACY_CONFORMANCE_CONTRACT_SCHEMA_VERSIONS = frozenset({1})
CONFORMANCE_CONTRACT_FIELDS = {
    "schema_version",
    "checkpoint_kind",
    "run_id",
    "session",
    "nonce",
    "target",
    "protocol_fingerprint",
    "allowed_fixture_root",
    "allowed_actions",
    "forbidden_actions",
}
ALLOWED_FIXTURE_ACTIONS = [
    "read_contract",
    "write_bounded_handoffs",
    "wait_for_halt",
]
FORBIDDEN_FIXTURE_ACTIONS = [
    "source_mutation",
    "repository_mutation",
    "account_change",
    "external_send",
    "system_change",
]
AGY_RUN_LOCAL_SYSTEM_ADDENDUM = b"""# Puppet-owned AGY run-local system addendum

This file applies only to this isolated Puppet conformance fixture. The
controller owns campaign state, proof indexing, and lifecycle summaries; this
bounded worker must not create `STATE.md`, `PROOF.md`, `events.jsonl`,
`heartbeat`, or a generic completion handoff unless the current task packet
names that exact path.

- Treat every exact artifact allowlist in the current task as a hard boundary.
- If the task says to write only one named path, create exactly that file.
- Never invent `conformance_handoff.json`, a summary, or a parallel checkpoint.
- A supplied `WRITE_*_JSON` value is the complete object. Never copy a prior
  handoff and patch selected fields; preserve every nested phase/status value.
- After the exact requested write, remain available and wait for controller
  steering or exact halt.
"""


def validate_fixture_contract(
    value: Any,
    *,
    root: Path,
    session: str,
    target: str,
) -> Dict[str, Any]:
    """Validate a current conformance contract and its v2 protocol binding."""

    if not isinstance(value, dict):
        raise ValidationError("conformance fixture contract root must be an object")
    schema_version = value.get("schema_version")
    if schema_version in LEGACY_CONFORMANCE_CONTRACT_SCHEMA_VERSIONS:
        raise UnsupportedError(
            "legacy conformance fixture contract lacks runtime execution identity"
        )
    if schema_version != CONFORMANCE_CONTRACT_SCHEMA_VERSION:
        raise ValidationError("unsupported conformance fixture contract schema")
    if set(value) != CONFORMANCE_CONTRACT_FIELDS:
        raise ValidationError("conformance fixture contract fields do not match schema")
    if value.get("checkpoint_kind") != "conformance":
        raise ValidationError("fixture is not a conformance contract")
    if value.get("session") != validate_identifier(session, "session"):
        raise ValidationError("fixture session identity mismatch")
    if target not in {"agy", "cursor", "claude", "codex", "grok"}:
        raise ValidationError("unsupported fixture target")
    if value.get("target") != target:
        raise ValidationError("fixture target identity mismatch")
    validate_identifier(value.get("run_id"), "run id")
    validate_identifier(value.get("nonce"), "nonce")
    if value.get("protocol_fingerprint") != PROTOCOL_FINGERPRINT:
        raise ValidationError("conformance fixture protocol version is mixed")
    expected_root = str(Path(root).resolve(strict=True))
    if value.get("allowed_fixture_root") != expected_root:
        raise ValidationError("fixture root identity mismatch")
    if value.get("allowed_actions") != ALLOWED_FIXTURE_ACTIONS:
        raise ValidationError("fixture allowed actions changed")
    if value.get("forbidden_actions") != FORBIDDEN_FIXTURE_ACTIONS:
        raise ValidationError("fixture forbidden actions changed")
    return dict(value)


def create_fixture(
    root: Path, *, run_id: str, session: str, target: str
) -> Dict[str, Any]:
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
        "schema_version": CONFORMANCE_CONTRACT_SCHEMA_VERSION,
        "checkpoint_kind": "conformance",
        "run_id": run_id,
        "session": session,
        "nonce": nonce,
        "target": target,
        "protocol_fingerprint": PROTOCOL_FINGERPRINT,
        "allowed_fixture_root": str(root.resolve(strict=True)),
        "allowed_actions": list(ALLOWED_FIXTURE_ACTIONS),
        "forbidden_actions": list(FORBIDDEN_FIXTURE_ACTIONS),
    }
    atomic_write_json(root / "contract.json", contract)
    if target == "agy":
        atomic_write_bytes(
            root / "GEMINI.md",
            AGY_RUN_LOCAL_SYSTEM_ADDENDUM,
        )
    return validate_fixture_contract(
        contract,
        root=root,
        session=session,
        target=target,
    )


def tree_fingerprint(
    root: Path, excluded_prefix: str | tuple[str, ...] = "handoffs"
) -> str:
    root = Path(root).resolve(strict=True)
    excluded = (
        (excluded_prefix,)
        if isinstance(excluded_prefix, str)
        else tuple(excluded_prefix)
    )
    rows = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if (
            any(
                relative == prefix or relative.startswith(prefix + "/")
                for prefix in excluded
            )
            or relative == ".git"
            or relative.startswith(".git/")
        ):
            continue
        if path.is_symlink():
            raise ValueError("fixture contains a symlink")
        if path.is_file():
            rows.append({"path": relative, "sha256": sha256_bytes(path.read_bytes())})
    return sha256_bytes(canonical_json_bytes(rows))
