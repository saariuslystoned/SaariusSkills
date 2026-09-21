"""Disabled synthetic-only Puppet adapter for merged, unreleased acpx source.

Binds the existing named local Cursor transport ``cursor-acp``. Ordinary
launch, native defaults, MCP broker policy, and live qualification stay
unchanged and unavailable. The public-runtime boundary is the documented
``createAcpRuntime`` options from openclaw/acpx merged main
``f8883645c261e07b2df7f9c3b4ad243b62d8168a`` (``#678``). That commit is
exact-source proof only; published ``acpx@0.18.0`` does not contain it.
Historical ``#648`` and refresh ``ce8c3689...`` identities remain rejected
fences. Private internals are not imported. The existing
``cursor-acp`` controller consumes runtime-derived observations; this
adapter keeps ownership, pin, and cutover contracts.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional, Sequence

from puppet_lib.authority import AUTHORITY_ID
from puppet_lib.caller import make_blocker
from puppet_lib.cursor_acp import (
    TRANSPORT_ID,
    VERIFIED_CURSOR_ACP_CATALOG,
    caller_fields_from_observation,
    fixture_observation,
    prove_cursor_acp_observation,
    prove_resume_identity,
    prove_shutdown,
    qualify_cursor_acp_lifecycle,
    require_cursor_acp_target,
    require_unsupported_question_outcome,
    validate_cursor_acp_observation,
)
from puppet_lib.errors import ConflictError, IdentityError, UnsupportedError, ValidationError
from puppet_lib.safety import (
    FORBIDDEN_FIELD_PARTS,
    absolute_root,
    atomic_write_json,
    canonical_json_bytes,
    exclusive_lock,
    read_json,
    sha256_bytes,
    sha256_file,
    validate_bounded_json,
    validate_identifier,
    validate_sha1,
    validate_sha256,
)


GENERIC_ACP_ID = "acp"
TARGET = "cursor"
ADAPTER_ID = "cursor-acpx"
DEPENDENCY_SCHEMA = "puppet.cursor-acpx-dependency/v1"
BOUNDARY_SCHEMA = "puppet.cursor-acpx-public-runtime/v1"
OWNERSHIP_SCHEMA = "puppet.cursor-acpx-ownership/v1"
EVIDENCE_SCHEMA = "puppet.cursor-acpx-evidence/v1"
CALLBACK_SCHEMA = "puppet.cursor-acpx-callback-rejection/v1"
QUESTION_SCHEMA = "puppet.cursor-acpx-question/v1"
PROCESS_SCHEMA = "puppet.cursor-acpx-process/v1"

ACPX_SOURCE = (
    "https://github.com/openclaw/acpx/commit/f8883645c261e07b2df7f9c3b4ad243b62d8168a"
)
ACPX_MERGE_COMMIT = "f8883645c261e07b2df7f9c3b4ad243b62d8168a"
ACPX_SOURCE_COMMIT = ACPX_MERGE_COMMIT
ACPX_SOURCE_TREE = "f4a4d33b33cdf5b57345e8420f24992953aed5e0"
ACPX_HEAD = ACPX_MERGE_COMMIT
ACPX_PR_HEAD = "706aeadd9c62550ee7e6ddceffe3d31ede5494d1"
ACPX_PR_BASE = "cc9b96388d682f8dbb17dde6015a5467e3f563fc"
ACPX_NPM_GIT_HEAD = "8699be1b6428fa7584acc6f07d87f5aec8945f58"
ACPX_STATUS = "merged_unreleased"
ACPX_ORDINARY_PINNED_PACKAGE = "0.16.0"
ACPX_CANDIDATE_PACKAGE_VERSION = "0.18.0"
ACPX_PUBLISHED_NPM_VERSION = "0.18.0"
ACPX_ARTIFACT_SHA256 = (
    "642d4c299bd58b275ca1a360196f3077fc4f84997e2654542f492b1e0001c162"
)
ACPX_ARTIFACT_PATH = (
    "runs/puppet-dual-acp-controller-runs/20260921/artifacts/acpx-0.18.0.tgz"
)
ACPX_ARTIFACT_KIND = "local_exact_source_tarball"
ACPX_PUBLIC_SURFACE = "acpx/runtime"
ACPX_CONSTRUCTOR = "createAcpRuntime"
ACPX_QUALIFICATION = "synthetic_only"
CUTOVER_SCHEMA = "puppet.cursor-acpx-cutover/v1"
HISTORICAL_ACPX_SOURCE = "https://github.com/openclaw/acpx/pull/648"
HISTORICAL_ACPX_MERGE_COMMIT = "ac22c3c8f6d077b542f19524afbe5409e46c56e8"
HISTORICAL_ACPX_PR_HEAD = "8de4219c4e87af4dbbc468f0056970d2cda343a2"
HISTORICAL_ACPX_PR_BASE = "4e4dcf5bdf4689509169861fefe5cea3a334d5f8"
HISTORICAL_ACPX_ARTIFACT_SHA256 = (
    "fe9ba256bc562b01bff007a2e63017a28daebb2dbc460806a6e7ad0f58d32d29"
)
HISTORICAL_ACPX_ARTIFACT_PATH = (
    "runs/puppet-acpx-merged648-runs/20260921/artifacts/acpx-0.18.0.tgz"
)
HISTORICAL_REFRESH_ACPX_SOURCE = (
    "https://github.com/openclaw/acpx/commit/ce8c3689fe830fd5c6199a8a683dc979d180af1d"
)
HISTORICAL_REFRESH_ACPX_MERGE_COMMIT = "ce8c3689fe830fd5c6199a8a683dc979d180af1d"
HISTORICAL_REFRESH_ACPX_SOURCE_TREE = "04661dbf3af3b3c2a11d16c3061b40e20ce29f4a"
HISTORICAL_REFRESH_ACPX_PR_HEAD = "c64b2751f0b8ca6e9d5613e98f7ed87f778de1b5"
HISTORICAL_REFRESH_ACPX_PR_BASE = "7879505dcf79448cd71cafd82a21aa6c937a3f3e"
HISTORICAL_REFRESH_ACPX_ARTIFACT_SHA256 = (
    "ad9bc677a6687268010da9c57b83fd96d2d35eddafdb55a6e043fd70679cc342"
)
HISTORICAL_REFRESH_ACPX_ARTIFACT_PATH = (
    "runs/puppet-acpx-refresh-runs/20260921/artifacts/acpx-0.18.0.tgz"
)
HISTORICAL_REFRESH_ACPX_CANDIDATE_RUNTIME_ROOT = (
    "runs/puppet-acpx-refresh-runs/20260921/runtime"
)
HISTORICAL_REFRESH_HEADS = frozenset(
    {
        HISTORICAL_REFRESH_ACPX_MERGE_COMMIT,
        HISTORICAL_REFRESH_ACPX_PR_HEAD,
        HISTORICAL_REFRESH_ACPX_PR_BASE,
    }
)
OBSOLETE_DRAFT_HEADS = frozenset(
    {
        "02c03c7abeee0324a71e2114e6b1b4cf7b0785ff",
        "2b7627a6b91b4c94c8a83ad0cc4863f72e8f14de",
    }
)
HISTORICAL_MERGED_HEADS = frozenset(
    {
        HISTORICAL_ACPX_MERGE_COMMIT,
        HISTORICAL_ACPX_PR_HEAD,
        HISTORICAL_ACPX_PR_BASE,
    }
)

PUBLIC_RUNTIME_OPTIONS = (
    "cwd",
    "sessionStore",
    "agentRegistry",
    "fs",
    "terminal",
    "timeoutMs",
    "processLifecycle",
    "probeAgent",
)
BROKER_POLICY_OPTIONS = frozenset(
    {
        "permissionMode",
        "nonInteractivePermissions",
        "permissionPolicy",
        "onPermissionRequest",
        "mcpServers",
        "sessionPermissions",
        "elicitationModes",
        "agentProcessEnv",
    }
)
FORBIDDEN_RUNTIME_OPTIONS = frozenset(
    {
        "permissionMode",
        "nonInteractivePermissions",
        "permissionPolicy",
        "onPermissionRequest",
        "mcpServers",
        "sessionPermissions",
        "elicitationModes",
        "agentProcessEnv",
    }
)
FORBIDDEN_CALLBACKS = frozenset(
    {"fs/read", "fs/write", "terminal", "terminal/create", "terminal/write"}
)
BODY_FIELD_NAMES = frozenset(
    {
        "prompt",
        "response",
        "output",
        "content",
        "text",
        "transcript",
        "title",
        "options",
        "messages",
        "rawInput",
        "rawOutput",
        "body",
    }
)
OWNERSHIP_KEYS = frozenset(
    {
        "schema",
        "authority_id",
        "adapter",
        "transport",
        "target",
        "owner",
        "isolated_root",
        "session",
        "conversation_id",
        "lease",
        "ordinary_launch",
        "qualification",
        "available",
        "cleanup",
        "replacement_blocked",
        "acpx",
    }
)

ProcessQuery = Callable[[Mapping[str, Any]], Mapping[str, Any]]


def _blocker(code: str, detail: str, **identity: Any) -> Dict[str, Any]:
    return make_blocker(code=code, detail=detail, **identity)


def _raise_identity(code: str, detail: str, **identity: Any) -> None:
    raise IdentityError(detail, blocker=_blocker(code, detail, **identity))


def _raise_unsupported(code: str, detail: str) -> None:
    raise UnsupportedError(detail, blocker=_blocker(code, detail))


def _raise_conflict(detail: str) -> None:
    raise ConflictError(
        detail,
        blocker=_blocker("isolated_root_owned", detail),
    )


def _reject_body_keys(value: Any, label: str = "artifact") -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            normalized = str(key).lower().replace("-", "_")
            if key in BODY_FIELD_NAMES or normalized in BODY_FIELD_NAMES:
                raise ValidationError("%s contains body-bearing field %s" % (label, key))
            if normalized in FORBIDDEN_FIELD_PARTS:
                raise ValidationError("%s contains forbidden field %s" % (label, key))
            _reject_body_keys(nested, label)
    elif isinstance(value, list):
        for nested in value:
            _reject_body_keys(nested, label)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _metadata_integrity_hash(value: Mapping[str, Any]) -> str:
    body = {key: item for key, item in value.items() if key not in {"schema", "integrity"}}
    return sha256_bytes(canonical_json_bytes(body))


def acpx_dependency_identity() -> Dict[str, Any]:
    """Return the merged-unreleased exact-source pin. Not an npm release."""

    pin = {
        "source": ACPX_SOURCE,
        "head": ACPX_HEAD,
        "merge_commit": ACPX_MERGE_COMMIT,
        "source_commit": ACPX_SOURCE_COMMIT,
        "source_tree": ACPX_SOURCE_TREE,
        "pr_head": ACPX_PR_HEAD,
        "pr_base": ACPX_PR_BASE,
        "npm_git_head": ACPX_NPM_GIT_HEAD,
        "status": ACPX_STATUS,
        "ordinary_pinned_package": ACPX_ORDINARY_PINNED_PACKAGE,
        "candidate_package_version": ACPX_CANDIDATE_PACKAGE_VERSION,
        "published_npm_version": ACPX_PUBLISHED_NPM_VERSION,
        "published_npm_contains_merge": False,
        "ordinary_route_unchanged": True,
        "qualification": ACPX_QUALIFICATION,
        "merged": True,
        "released": False,
        "public_surface": ACPX_PUBLIC_SURFACE,
        "constructor": ACPX_CONSTRUCTOR,
        "artifact_kind": ACPX_ARTIFACT_KIND,
        "artifact_path": ACPX_ARTIFACT_PATH,
        "artifact_sha256": ACPX_ARTIFACT_SHA256,
    }
    return {
        "schema": DEPENDENCY_SCHEMA,
        **pin,
        "integrity": ACPX_ARTIFACT_SHA256,
    }


def validate_acpx_dependency_identity(value: Any) -> Dict[str, Any]:
    """Fail closed on draft, release, or metadata-hash provenance claims."""

    if not isinstance(value, Mapping):
        raise ValidationError("acpx dependency identity is invalid")
    _reject_body_keys(value, "acpx identity")
    if value.get("status") == "draft":
        _raise_identity(
            "identity_mismatch",
            "acpx draft-state identity is obsolete",
        )
    if value.get("merged") is not True:
        _raise_identity(
            "identity_mismatch",
            "acpx source is not the merged commit",
        )
    if value.get("released") is True:
        _raise_identity(
            "identity_mismatch",
            "acpx candidate is not a released package",
        )
    if value.get("qualification") != ACPX_QUALIFICATION:
        raise ValidationError("cursor-acpx cannot claim live qualification")
    if value.get("published_npm_contains_merge") is True:
        _raise_identity(
            "identity_mismatch",
            "published npm acpx@0.18.0 does not contain the merge",
        )
    if value.get("ordinary_pinned_package") != ACPX_ORDINARY_PINNED_PACKAGE:
        _raise_identity(
            "identity_mismatch",
            "ordinary production pin must stay 0.16.0",
        )
    if value.get("candidate_package_version") != ACPX_CANDIDATE_PACKAGE_VERSION:
        _raise_identity(
            "identity_mismatch",
            "candidate package version drifted",
        )
    merge_commit = value.get("merge_commit")
    source_commit = value.get("source_commit")
    source_tree = value.get("source_tree")
    head = value.get("head")
    pr_head = value.get("pr_head")
    pr_base = value.get("pr_base")
    npm_git_head = value.get("npm_git_head")
    for label, commit in (
        ("merge commit", merge_commit),
        ("source commit", source_commit),
        ("source tree", source_tree),
        ("bound head", head),
        ("PR head", pr_head),
        ("PR base", pr_base),
        ("npm gitHead", npm_git_head),
    ):
        validate_sha1(commit, label)
    if merge_commit != source_commit or head != merge_commit:
        _raise_identity(
            "identity_mismatch",
            "merge and source commit must be the exact merged acpx commit",
        )
    if source_tree == merge_commit:
        _raise_identity(
            "identity_mismatch",
            "source tree is not the merge commit",
        )
    if merge_commit == npm_git_head:
        _raise_identity(
            "identity_mismatch",
            "stale npm gitHead is not the merge commit",
        )
    if merge_commit == pr_head or merge_commit == pr_base:
        _raise_identity(
            "identity_mismatch",
            "PR head or base is not the merge commit",
        )
    if {
        merge_commit,
        pr_head,
        pr_base,
        npm_git_head,
    } & OBSOLETE_DRAFT_HEADS:
        _raise_identity(
            "identity_mismatch",
            "acpx draft-state identity is obsolete",
        )
    if (
        {merge_commit, source_commit, head} & HISTORICAL_MERGED_HEADS
        or value.get("artifact_sha256") == HISTORICAL_ACPX_ARTIFACT_SHA256
        or value.get("artifact_path") == HISTORICAL_ACPX_ARTIFACT_PATH
        or value.get("source") == HISTORICAL_ACPX_SOURCE
    ):
        _raise_identity(
            "identity_mismatch",
            "historical #648 candidate identity is not the current pin",
        )
    if (
        {merge_commit, source_commit, head} & HISTORICAL_REFRESH_HEADS
        or value.get("artifact_sha256") == HISTORICAL_REFRESH_ACPX_ARTIFACT_SHA256
        or value.get("artifact_path") == HISTORICAL_REFRESH_ACPX_ARTIFACT_PATH
        or value.get("source") == HISTORICAL_REFRESH_ACPX_SOURCE
        or value.get("source_tree") == HISTORICAL_REFRESH_ACPX_SOURCE_TREE
    ):
        _raise_identity(
            "identity_mismatch",
            "historical refresh candidate identity is not the current pin",
        )
    artifact = validate_sha256(value.get("artifact_sha256"), "acpx artifact")
    integrity = validate_sha256(value.get("integrity"), "acpx integrity")
    if integrity == _metadata_integrity_hash(value):
        _raise_identity(
            "identity_mismatch",
            "acpx artifact integrity must not be a hash of descriptive metadata",
        )
    if integrity != artifact:
        _raise_identity(
            "identity_mismatch",
            "acpx artifact integrity must be the tarball digest",
        )
    expected = acpx_dependency_identity()
    if dict(value) != expected:
        _raise_identity("identity_mismatch", "acpx source identity drifted")
    return expected


def prove_local_artifact(artifact_path: Optional[Path] = None) -> Dict[str, Any]:
    """Prove the on-disk tarball digest. Not an npm release claim."""

    path = Path(artifact_path) if artifact_path is not None else _repo_root() / ACPX_ARTIFACT_PATH
    digest = sha256_file(path)
    if digest != ACPX_ARTIFACT_SHA256:
        _raise_identity(
            "identity_mismatch",
            "local acpx artifact digest drifted",
        )
    return {
        "kind": ACPX_ARTIFACT_KIND,
        "path": ACPX_ARTIFACT_PATH if artifact_path is None else str(path),
        "artifact_sha256": digest,
        "candidate_package_version": ACPX_CANDIDATE_PACKAGE_VERSION,
        "released": False,
        "published_npm_contains_merge": False,
    }


def cutover_safeguards() -> Dict[str, Any]:
    """Explicit gates that keep this candidate experimental and unreleased."""

    return {
        "schema": CUTOVER_SCHEMA,
        "available": False,
        "ordinary_launch": "unavailable",
        "ordinary_pinned_package": ACPX_ORDINARY_PINNED_PACKAGE,
        "candidate_package_version": ACPX_CANDIDATE_PACKAGE_VERSION,
        "released": False,
        "published_npm_contains_merge": False,
        "qualification": ACPX_QUALIFICATION,
        "live_qualification": False,
        "production_enabled": False,
        "public_pr": False,
        "ordinary_route_unchanged": True,
    }


def validate_cutover_safeguards(value: Any = None) -> Dict[str, Any]:
    expected = cutover_safeguards()
    current = expected if value is None else value
    if not isinstance(current, Mapping) or dict(current) != expected:
        _raise_identity("identity_mismatch", "cursor-acpx cutover safeguards drifted")
    if (
        current["available"] is not False
        or current["production_enabled"] is not False
        or current["released"] is not False
        or current["public_pr"] is not False
        or current["live_qualification"] is not False
        or current["ordinary_launch"] != "unavailable"
    ):
        _raise_identity(
            "identity_mismatch",
            "cursor-acpx must not enable production or ordinary launch",
        )
    return expected


def public_runtime_boundary() -> Dict[str, Any]:
    """Thinnest documented public-runtime options. Private internals stay out."""

    return {
        "schema": BOUNDARY_SCHEMA,
        "surface": ACPX_PUBLIC_SURFACE,
        "constructor": ACPX_CONSTRUCTOR,
        "allowed_options": list(PUBLIC_RUNTIME_OPTIONS),
        "forbidden_options": sorted(FORBIDDEN_RUNTIME_OPTIONS),
        "fs": False,
        "terminal": False,
        "permission_policy": "not_imported",
        "mcp_broker_policy": "not_imported",
        "approve_all": False,
        "private_internals": False,
        "ordinary_launch": "unavailable",
        "available": False,
        "qualification": ACPX_QUALIFICATION,
        "live_qualification": False,
        "merged_callback_options": ["fs", "terminal"],
        "callback_omit_default": "enabled",
        "callback_persisted": False,
        "os_sandbox": False,
    }


def validate_public_runtime_options(value: Any) -> Dict[str, Any]:
    """Accept only the public createAcpRuntime allowlist with callbacks off."""

    if not isinstance(value, Mapping):
        raise ValidationError("public runtime options are invalid")
    if set(value) & BROKER_POLICY_OPTIONS:
        raise ValidationError("approve-all or MCP broker policy is not imported")
    unknown = set(value) - set(PUBLIC_RUNTIME_OPTIONS)
    if unknown:
        raise ValidationError("public runtime options include private fields")
    if value.get("fs") is not False:
        raise ValidationError("filesystem callbacks must stay disabled")
    if value.get("terminal") is not False:
        raise ValidationError("terminal callbacks must stay disabled")
    cwd = value.get("cwd")
    if not isinstance(cwd, str) or not cwd:
        raise ValidationError("public runtime cwd is invalid")
    if "sessionStore" not in value or "agentRegistry" not in value:
        raise ValidationError("public runtime identity is incomplete")
    return {
        "cwd": cwd,
        "sessionStore": "memory_only",
        "agentRegistry": "synthetic_peer",
        "fs": False,
        "terminal": False,
        "timeoutMs": value.get("timeoutMs"),
        "processLifecycle": "observed_or_unknown",
        "probeAgent": value.get("probeAgent"),
    }


def _ownership_path(isolated_root: Path) -> Path:
    return isolated_root / "ownership.json"


def _evidence_path(isolated_root: Path) -> Path:
    return isolated_root / "evidence.json"


def _events_path(isolated_root: Path) -> Path:
    return isolated_root / "events.jsonl"


def _lock_path(isolated_root: Path) -> Path:
    return isolated_root / "ownership.lock"


def _require_private_root(isolated_root: Path) -> Path:
    root = absolute_root(str(isolated_root), "isolated state root")
    mode = stat.S_IMODE(root.stat().st_mode)
    if root.stat().st_uid != os.getuid() or mode != 0o700:
        raise ValidationError("isolated state root is not current-UID mode 0700")
    return root


def _write_event(isolated_root: Path, event: Mapping[str, Any]) -> None:
    _reject_body_keys(event, "event")
    validate_bounded_json(event, max_items=64, max_string=400)
    payload = canonical_json_bytes(dict(event)) + b"\n"
    path = _events_path(isolated_root)
    flags = os.O_CREAT | os.O_APPEND | os.O_WRONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(str(path), flags, 0o600)
    try:
        os.write(descriptor, payload)
    finally:
        os.close(descriptor)


def validate_ownership(value: Any) -> Dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != OWNERSHIP_KEYS:
        raise ValidationError("isolated-root ownership fields do not match schema")
    if value.get("schema") != OWNERSHIP_SCHEMA:
        raise ValidationError("isolated-root ownership schema is invalid")
    if value.get("authority_id") != AUTHORITY_ID:
        _raise_identity("identity_mismatch", "Puppet authority identity drifted")
    if value.get("adapter") != ADAPTER_ID:
        _raise_identity("identity_mismatch", "cursor-acpx adapter identity drifted")
    if value.get("transport") != TRANSPORT_ID:
        _raise_identity("identity_mismatch", "cursor-acp transport identity drifted")
    if value.get("transport") == GENERIC_ACP_ID:
        _raise_identity("identity_mismatch", "generic acp is not a Cursor transport")
    require_cursor_acp_target(value.get("target"))
    if value.get("lease") != "not_admitted":
        raise ValidationError("cursor-acpx must not admit an ordinary lease")
    if value.get("ordinary_launch") != "unavailable" or value.get("available") is not False:
        raise ValidationError("cursor-acpx ordinary launch must stay unavailable")
    if value.get("qualification") != ACPX_QUALIFICATION:
        raise ValidationError("cursor-acpx cannot claim live qualification")
    cleanup = value.get("cleanup")
    if cleanup not in {"owned", "unknown", "confirmed_absent"}:
        raise ValidationError("isolated-root cleanup state is invalid")
    if not isinstance(value.get("replacement_blocked"), bool):
        raise ValidationError("replacement block flag is invalid")
    acpx = validate_acpx_dependency_identity(value.get("acpx"))
    _reject_body_keys(value, "ownership")
    return {
        "schema": OWNERSHIP_SCHEMA,
        "authority_id": AUTHORITY_ID,
        "adapter": ADAPTER_ID,
        "transport": TRANSPORT_ID,
        "target": TARGET,
        "owner": validate_identifier(value.get("owner"), "isolated-root owner"),
        "isolated_root": _bounded_path(value.get("isolated_root")),
        "session": validate_identifier(value.get("session"), "cursor-acp session"),
        "conversation_id": validate_identifier(
            value.get("conversation_id"), "cursor-acp conversation"
        ),
        "lease": "not_admitted",
        "ordinary_launch": "unavailable",
        "qualification": ACPX_QUALIFICATION,
        "available": False,
        "cleanup": cleanup,
        "replacement_blocked": value["replacement_blocked"],
        "acpx": acpx,
    }


def _bounded_path(value: Any) -> str:
    if not isinstance(value, str) or not value or len(value) > 1024:
        raise ValidationError("isolated-root path is invalid")
    if any(character in value for character in "\x00\n\r"):
        raise ValidationError("isolated-root path is invalid")
    return value


def claim_isolated_root(
    isolated_root: Path,
    *,
    owner: str,
    session: str,
    conversation_id: str,
) -> Dict[str, Any]:
    """Claim one isolated state root. Duplicate owners are rejected."""

    root = _require_private_root(isolated_root)
    owner = validate_identifier(owner, "isolated-root owner")
    session = validate_identifier(session, "cursor-acp session")
    conversation_id = validate_identifier(conversation_id, "cursor-acp conversation")
    claim = {
        "schema": OWNERSHIP_SCHEMA,
        "authority_id": AUTHORITY_ID,
        "adapter": ADAPTER_ID,
        "transport": TRANSPORT_ID,
        "target": TARGET,
        "owner": owner,
        "isolated_root": str(root),
        "session": session,
        "conversation_id": conversation_id,
        "lease": "not_admitted",
        "ordinary_launch": "unavailable",
        "qualification": ACPX_QUALIFICATION,
        "available": False,
        "cleanup": "owned",
        "replacement_blocked": False,
        "acpx": acpx_dependency_identity(),
    }
    validate_ownership(claim)
    with exclusive_lock(_lock_path(root)):
        path = _ownership_path(root)
        if path.exists():
            existing = validate_ownership(read_json(path))
            if existing["owner"] != owner:
                _raise_conflict(
                    "isolated state root is already owned by a different adapter"
                )
            if existing["cleanup"] == "unknown" or existing["replacement_blocked"]:
                _raise_identity(
                    "cleanup_unknown",
                    "process-query failure left cleanup unknown; replacement is blocked",
                )
            if (
                existing["session"] != session
                or existing["conversation_id"] != conversation_id
            ):
                _raise_identity(
                    "session_identity_mismatch",
                    "isolated-root session identity does not match the bound session",
                )
            return existing
        atomic_write_json(path, claim)
        _write_event(
            root,
            {
                "event": "ownership_claimed",
                "owner": owner,
                "session": session,
                "conversation_id": conversation_id,
            },
        )
        return claim


def load_isolated_root(isolated_root: Path) -> Dict[str, Any]:
    root = _require_private_root(isolated_root)
    path = _ownership_path(root)
    if not path.is_file():
        _raise_unsupported("proof_missing", "isolated-root ownership proof is missing")
    return validate_ownership(read_json(path))


def mark_cleanup_unknown(isolated_root: Path) -> Dict[str, Any]:
    root = _require_private_root(isolated_root)
    with exclusive_lock(_lock_path(root)):
        current = validate_ownership(read_json(_ownership_path(root)))
        current["cleanup"] = "unknown"
        current["replacement_blocked"] = True
        atomic_write_json(_ownership_path(root), current)
        _write_event(
            root,
            {
                "event": "cleanup_unknown",
                "session": current["session"],
                "conversation_id": current["conversation_id"],
                "replacement_blocked": True,
            },
        )
        return current


def persist_evidence(isolated_root: Path, evidence: Mapping[str, Any]) -> Dict[str, Any]:
    root = _require_private_root(isolated_root)
    payload = validate_evidence(evidence)
    atomic_write_json(_evidence_path(root), payload)
    _write_event(
        root,
        {
            "event": "evidence_persisted",
            "session": payload["session"],
            "conversation_id": payload["conversation_id"],
            "worker_completion": payload["worker_completion"],
            "controller_acceptance": payload["controller_acceptance"],
            "halt": payload["halt"],
        },
    )
    return payload


def validate_evidence(value: Any) -> Dict[str, Any]:
    _reject_body_keys(value, "evidence")
    if not isinstance(value, Mapping):
        raise ValidationError("cursor-acpx evidence is invalid")
    required = {
        "schema",
        "transport",
        "target",
        "session",
        "conversation_id",
        "workspace",
        "model",
        "terminal_result",
        "worker_completion",
        "controller_acceptance",
        "halt",
        "question",
        "callbacks",
        "cleanup",
        "live_claimed",
        "prompt_retained",
        "response_retained",
        "acpx",
    }
    if set(value) != required:
        raise ValidationError("cursor-acpx evidence fields do not match schema")
    if value.get("schema") != EVIDENCE_SCHEMA:
        raise ValidationError("cursor-acpx evidence schema is invalid")
    if value.get("transport") != TRANSPORT_ID or value.get("target") != TARGET:
        _raise_identity("identity_mismatch", "cursor-acpx evidence identity drifted")
    if value.get("live_claimed") is not False:
        raise ValidationError("cursor-acpx must not claim a live run")
    if value.get("prompt_retained") is not False or value.get("response_retained") is not False:
        raise ValidationError("cursor-acpx durable evidence retained a body")
    acpx = validate_acpx_dependency_identity(value.get("acpx"))
    return {
        "schema": EVIDENCE_SCHEMA,
        "transport": TRANSPORT_ID,
        "target": TARGET,
        "session": validate_identifier(value.get("session"), "cursor-acp session"),
        "conversation_id": validate_identifier(
            value.get("conversation_id"), "cursor-acp conversation"
        ),
        "workspace": dict(value["workspace"]),
        "model": dict(value["model"]),
        "terminal_result": dict(value["terminal_result"]),
        "worker_completion": value["worker_completion"],
        "controller_acceptance": value["controller_acceptance"],
        "halt": value["halt"],
        "question": dict(value["question"]),
        "callbacks": dict(value["callbacks"]),
        "cleanup": value["cleanup"],
        "live_claimed": False,
        "prompt_retained": False,
        "response_retained": False,
        "acpx": acpx,
    }


def audit_durable_artifacts(isolated_root: Path) -> Dict[str, Any]:
    """Fail closed if any durable Puppet/bridge/runtime artifact retains a body."""

    root = _require_private_root(isolated_root)
    inspected = 0
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name.endswith(".lock"):
            continue
        inspected += 1
        raw = path.read_bytes()
        if path.suffix in {".json", ".jsonl"}:
            text = raw.decode("utf-8")
            for line in text.splitlines():
                if not line.strip():
                    continue
                payload = json.loads(line)
                _reject_body_keys(payload, str(path.name))
                validate_bounded_json(payload, max_items=256, max_string=8192)
        else:
            raise ValidationError("isolated-root contains a non-evidence artifact")
    if inspected == 0:
        _raise_unsupported("proof_missing", "durable cursor-acpx proof is missing")
    return {"ok": True, "inspected": inspected, "body_retained": False}


class SyntheticAcpxPeer:
    """Deterministic noncompliant peer. Never answers questions or writes files."""

    def __init__(
        self,
        *,
        session: str,
        conversation_id: str,
        workspace_root: Path,
        requested_callbacks: Sequence[str] = (),
        question: Optional[Mapping[str, Any]] = None,
    ):
        self.session = session
        self.conversation_id = conversation_id
        self.workspace_root = Path(workspace_root)
        self.requested_callbacks = tuple(requested_callbacks)
        self.question = None if question is None else dict(question)
        self.side_effects: list[str] = []
        self.rejected: list[str] = []

    def attempt_forbidden_callbacks(self) -> Dict[str, Any]:
        for method in self.requested_callbacks:
            if method not in FORBIDDEN_CALLBACKS:
                raise ValidationError("synthetic peer requested an unknown callback")
            marker = self.workspace_root / ("%s.side-effect" % method.replace("/", "-"))
            if marker.exists():
                self.side_effects.append(str(marker))
            self.rejected.append(method)
        return {
            "schema": CALLBACK_SCHEMA,
            "fs": False,
            "terminal": False,
            "rejected": list(self.rejected),
            "local_side_effect": False,
        }


class SyntheticAcpxRuntime:
    """Public-runtime fixture. Memory-only store; no private acpx internals."""

    def __init__(
        self,
        *,
        isolated_root: Path,
        peer: SyntheticAcpxPeer,
        options: Optional[Mapping[str, Any]] = None,
        process_query: Optional[ProcessQuery] = None,
        process_identity: Optional[Mapping[str, Any]] = None,
    ):
        self.isolated_root = Path(isolated_root)
        self.peer = peer
        self._sessions: Dict[str, Dict[str, str]] = {}
        self.process_query = process_query
        self.process_identity = dict(process_identity or {})
        self.options = validate_public_runtime_options(
            options
            or {
                "cwd": str(self.isolated_root),
                "sessionStore": object(),
                "agentRegistry": object(),
                "fs": False,
                "terminal": False,
            }
        )
        self.cancelled = False
        self.halted = False

    def ensure_session(self, session: str, conversation_id: str) -> Dict[str, str]:
        handle = {
            "session": validate_identifier(session, "cursor-acp session"),
            "conversation_id": validate_identifier(
                conversation_id, "cursor-acp conversation"
            ),
        }
        self._sessions[handle["session"]] = dict(handle)
        return dict(handle)

    def load_session(self, session: str, conversation_id: str) -> Dict[str, str]:
        stored = self._sessions.get(session)
        if stored is None:
            _raise_unsupported("proof_missing", "synthetic runtime session proof is missing")
        if (
            stored["session"] != session
            or stored["conversation_id"] != conversation_id
        ):
            _raise_identity(
                "session_identity_mismatch",
                "reconnect did not retain the exact session identity",
            )
        return dict(stored)

    def query_process(self) -> Dict[str, Any]:
        if self.process_query is None:
            _raise_unsupported("proof_missing", "process-query proof is missing")
        try:
            result = self.process_query(self.process_identity)
        except Exception as exc:
            mark_cleanup_unknown(self.isolated_root)
            raise IdentityError(
                "process query failed; cleanup is unknown",
                blocker=_blocker(
                    "cleanup_unknown",
                    "process query failed; cleanup is unknown",
                ),
            ) from exc
        if not isinstance(result, Mapping) or "alive" not in result:
            mark_cleanup_unknown(self.isolated_root)
            _raise_identity(
                "cleanup_unknown",
                "process query left cleanup unknown; replacement is blocked",
            )
        return {
            "schema": PROCESS_SCHEMA,
            "alive": bool(result["alive"]),
            "cleanup": "owned" if result["alive"] is False else "owned",
        }


class CursorAcpxAdapter:
    """Disabled Puppet adapter. Fixtures never make ordinary launch available."""

    def __init__(
        self,
        isolated_root: Path,
        *,
        owner: str,
        session: str,
        conversation_id: str,
        workspace: Mapping[str, Any],
        runtime: Optional[SyntheticAcpxRuntime] = None,
        catalog: Optional[Mapping[str, Any]] = None,
    ):
        self.isolated_root = _require_private_root(isolated_root)
        self.owner = validate_identifier(owner, "isolated-root owner")
        self.session = validate_identifier(session, "cursor-acp session")
        self.conversation_id = validate_identifier(
            conversation_id, "cursor-acp conversation"
        )
        self.workspace = dict(workspace)
        self.catalog = catalog if catalog is not None else VERIFIED_CURSOR_ACP_CATALOG
        self.runtime = runtime
        self.ownership = claim_isolated_root(
            self.isolated_root,
            owner=self.owner,
            session=self.session,
            conversation_id=self.conversation_id,
        )

    @staticmethod
    def available() -> bool:
        return False

    @staticmethod
    def ordinary_launch_available() -> bool:
        return False

    def require_runtime(self) -> SyntheticAcpxRuntime:
        if self.runtime is None:
            _raise_unsupported(
                "transport_unavailable",
                "cursor-acpx public runtime fixture is unavailable",
            )
        return self.runtime

    def bind_session(self) -> Dict[str, str]:
        handle = self.require_runtime().ensure_session(self.session, self.conversation_id)
        if handle["session"] != self.session or handle["conversation_id"] != self.conversation_id:
            _raise_identity(
                "session_identity_mismatch",
                "cursor-acpx session identity does not match the bound session",
            )
        return handle

    def reconnect(self) -> Dict[str, str]:
        ownership = load_isolated_root(self.isolated_root)
        if (
            ownership["session"] != self.session
            or ownership["conversation_id"] != self.conversation_id
        ):
            _raise_identity(
                "session_identity_mismatch",
                "reconnect/load did not retain the exact session identity",
            )
        return self.require_runtime().load_session(self.session, self.conversation_id)

    def reject_callbacks(self) -> Dict[str, Any]:
        runtime = self.require_runtime()
        rejected = runtime.peer.attempt_forbidden_callbacks()
        if rejected["local_side_effect"] or runtime.peer.side_effects:
            _raise_identity(
                "identity_mismatch",
                "forbidden callback produced a local side effect",
            )
        for method in runtime.peer.requested_callbacks:
            marker = runtime.peer.workspace_root / (
                "%s.side-effect" % method.replace("/", "-")
            )
            if marker.exists():
                _raise_identity(
                    "identity_mismatch",
                    "forbidden callback produced a local side effect",
                )
        return rejected

    def require_human_question(self, question: Mapping[str, Any]) -> Dict[str, Any]:
        return require_unsupported_question_outcome(question)

    def complete(
        self,
        observation: Mapping[str, Any],
        *,
        expected_result_state: str = "completed",
        expected_result_id: Optional[str] = None,
        record_state: Optional[str] = None,
    ) -> Dict[str, Any]:
        observation = validate_cursor_acp_observation(observation)
        proved = prove_cursor_acp_observation(
            observation,
            expected_session=self.session,
            expected_conversation_id=self.conversation_id,
            expected_workspace=self.workspace,
            expected_result_state=expected_result_state,
            expected_result_id=expected_result_id,
            catalog=self.catalog,
        )
        lifecycle = qualify_cursor_acp_lifecycle(
            observation,
            expected_session=self.session,
            expected_conversation_id=self.conversation_id,
            expected_workspace=self.workspace,
            expected_result_state=expected_result_state,
            expected_result_id=expected_result_id,
            record_state=record_state,
            catalog=self.catalog,
        )
        fields = caller_fields_from_observation(observation, record_state=record_state)
        if (
            fields["caller_outcome"]["worker_completion"] == "reported"
            and fields["caller_outcome"]["controller_acceptance"] == "accepted"
            and record_state != "ACCEPTED"
        ):
            _raise_identity(
                "result_identity_mismatch",
                "worker completion is not controller acceptance",
            )
        return {
            "ok": True,
            "available": False,
            "ordinary_launch": "unavailable",
            "live_claimed": False,
            "binding": proved,
            "lifecycle": lifecycle,
            "caller_outcome": fields["caller_outcome"],
            "final_outcome": fields["final_outcome"],
        }

    def request_cancel(self) -> Dict[str, Any]:
        runtime = self.require_runtime()
        runtime.cancelled = True
        _write_event(
            self.isolated_root,
            {
                "event": "cancel_requested",
                "session": self.session,
                "conversation_id": self.conversation_id,
                "halt": "none",
            },
        )
        return {
            "status": "cancellation-requested",
            "session": self.session,
            "conversation_id": self.conversation_id,
            "halt": "none",
        }

    def observe_halt(self, observation: Mapping[str, Any]) -> Dict[str, Any]:
        runtime = self.require_runtime()
        if runtime.cancelled and observation.get("halt") is None:
            _raise_identity(
                "session_identity_mismatch",
                "cancellation is not independently observed halt",
            )
        halt = prove_shutdown(
            observation,
            expected_session=self.session,
            expected_conversation_id=self.conversation_id,
        )
        resume = prove_resume_identity(
            observation,
            expected_session=self.session,
            expected_conversation_id=self.conversation_id,
        )
        if resume["session"] != halt["session"]:
            _raise_identity(
                "session_identity_mismatch",
                "halt identity does not match the bound session",
            )
        runtime.halted = True
        return halt

    def persist_lifecycle(
        self,
        observation: Mapping[str, Any],
        *,
        question: Optional[Mapping[str, Any]] = None,
        record_state: Optional[str] = None,
        require_halt: bool = False,
    ) -> Dict[str, Any]:
        observation = validate_cursor_acp_observation(observation)
        completed = self.complete(observation, record_state=record_state)
        halt_state = completed["caller_outcome"]["halt"]
        if require_halt:
            self.observe_halt(observation)
            halt_state = "confirmed"
        callbacks = (
            self.reject_callbacks()
            if self.runtime is not None
            else {"schema": CALLBACK_SCHEMA, "fs": False, "terminal": False, "rejected": [], "local_side_effect": False}
        )
        question_state = (
            self.require_human_question(question)
            if question is not None
            else {
                "schema": QUESTION_SCHEMA,
                "state": "none",
                "interaction_id": None,
                "human_required": False,
                "outcome": None,
                "invented_answer": None,
            }
        )
        evidence = persist_evidence(
            self.isolated_root,
            {
                "schema": EVIDENCE_SCHEMA,
                "transport": TRANSPORT_ID,
                "target": TARGET,
                "session": self.session,
                "conversation_id": self.conversation_id,
                "workspace": dict(self.workspace),
                "model": dict(completed["binding"]["model"]),
                "terminal_result": dict(completed["binding"]["terminal_result"]),
                "worker_completion": completed["caller_outcome"]["worker_completion"],
                "controller_acceptance": completed["caller_outcome"]["controller_acceptance"],
                "halt": halt_state,
                "question": question_state,
                "callbacks": callbacks,
                "cleanup": load_isolated_root(self.isolated_root)["cleanup"],
                "live_claimed": False,
                "prompt_retained": False,
                "response_retained": False,
                "acpx": acpx_dependency_identity(),
            },
        )
        audit_durable_artifacts(self.isolated_root)
        return {
            **completed,
            "ownership": load_isolated_root(self.isolated_root),
            "evidence": evidence,
            "acpx": acpx_dependency_identity(),
            "boundary": public_runtime_boundary(),
        }


def fixture_runtime(
    isolated_root: Path,
    *,
    session: str = "cursor-acp-session",
    conversation_id: str = "conv-cursor-acp-1",
    workspace_root: Optional[Path] = None,
    requested_callbacks: Sequence[str] = (),
    process_query: Optional[ProcessQuery] = None,
    process_identity: Optional[Mapping[str, Any]] = None,
) -> SyntheticAcpxRuntime:
    peer = SyntheticAcpxPeer(
        session=session,
        conversation_id=conversation_id,
        workspace_root=workspace_root or isolated_root,
        requested_callbacks=requested_callbacks,
    )
    return SyntheticAcpxRuntime(
        isolated_root=isolated_root,
        peer=peer,
        process_query=process_query,
        process_identity=process_identity,
    )


__all__ = [
    "ADAPTER_ID",
    "ACPX_ARTIFACT_PATH",
    "ACPX_ARTIFACT_SHA256",
    "ACPX_CANDIDATE_PACKAGE_VERSION",
    "ACPX_HEAD",
    "ACPX_MERGE_COMMIT",
    "ACPX_NPM_GIT_HEAD",
    "ACPX_ORDINARY_PINNED_PACKAGE",
    "ACPX_PR_BASE",
    "ACPX_PR_HEAD",
    "ACPX_SOURCE",
    "ACPX_SOURCE_COMMIT",
    "ACPX_SOURCE_TREE",
    "ACPX_STATUS",
    "HISTORICAL_ACPX_ARTIFACT_PATH",
    "HISTORICAL_ACPX_ARTIFACT_SHA256",
    "HISTORICAL_ACPX_MERGE_COMMIT",
    "HISTORICAL_REFRESH_ACPX_ARTIFACT_PATH",
    "HISTORICAL_REFRESH_ACPX_ARTIFACT_SHA256",
    "HISTORICAL_REFRESH_ACPX_MERGE_COMMIT",
    "AUTHORITY_ID",
    "CursorAcpxAdapter",
    "FORBIDDEN_CALLBACKS",
    "GENERIC_ACP_ID",
    "SyntheticAcpxPeer",
    "SyntheticAcpxRuntime",
    "TARGET",
    "TRANSPORT_ID",
    "acpx_dependency_identity",
    "audit_durable_artifacts",
    "claim_isolated_root",
    "cutover_safeguards",
    "fixture_observation",
    "fixture_runtime",
    "load_isolated_root",
    "mark_cleanup_unknown",
    "prove_local_artifact",
    "public_runtime_boundary",
    "validate_acpx_dependency_identity",
    "validate_cutover_safeguards",
    "validate_public_runtime_options",
]
