"""Pure content-addressed Merkle directory codec for historical retention.

The codec stores file bytes and canonical JSON directory descriptors in one
hash-addressed object map.  Directory traversal is bounded to 256 levels when
packing and unpacking; this is intentionally separate from the existing reconciliation
recursion bound of 32.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Dict, Mapping, Tuple


SCHEMA = "grilltrack/retention-tree/v1"
MAX_DIRECTORY_DEPTH = 256
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_NAME = re.compile(r"[A-Za-z0-9._-]+\Z")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe_path(path: str) -> Tuple[str, ...]:
    if not isinstance(path, str):
        raise ValueError("path must be a string")
    if not path or path.startswith("/") or "\\" in path or "\x00" in path:
        raise ValueError(f"unsafe path: {path!r}")
    parts = path.split("/")
    if any(not part or part in {".", ".."} for part in parts):
        raise ValueError(f"unsafe path: {path!r}")
    for part in parts:
        if not _NAME.fullmatch(part):
            raise ValueError(f"unsafe path component: {part!r}")
    return tuple(parts)


def _tree_bytes(entries: Mapping[str, Mapping[str, str]]) -> bytes:
    descriptor = {"schema": SCHEMA, "entries": dict(sorted(entries.items()))}
    return json.dumps(
        descriptor, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    ).encode("ascii")


def pack(files: Mapping[str, bytes]) -> Tuple[str, Dict[str, bytes]]:
    """Pack a path-to-bytes mapping into a root hash and immutable objects."""
    if not isinstance(files, Mapping):
        raise ValueError("files must be a mapping")

    root: dict = {}
    for path, data in files.items():
        parts = _safe_path(path)
        if len(parts) - 1 > MAX_DIRECTORY_DEPTH:
            raise ValueError("directory depth exceeds 256")
        if not isinstance(data, bytes):
            raise ValueError(f"file {path!r} must contain bytes")
        directory = root
        for component in parts[:-1]:
            child = directory.get(component)
            if child is None:
                child = {}
                directory[component] = child
            elif not isinstance(child, dict):
                raise ValueError(f"file/directory path collision at {path!r}")
            directory = child
        leaf = parts[-1]
        if leaf in directory:
            if isinstance(directory[leaf], dict):
                raise ValueError(f"file/directory path collision at {path!r}")
            raise ValueError(f"duplicate path: {path!r}")
        directory[leaf] = data

    objects: Dict[str, bytes] = {}

    def encode_tree(directory: dict) -> str:
        entries: Dict[str, dict] = {}
        for name in sorted(directory):
            value = directory[name]
            if isinstance(value, dict):
                child_hash = encode_tree(value)
                entries[name] = {"kind": "tree", "sha256": child_hash}
            else:
                child_hash = _sha256(value)
                objects.setdefault(child_hash, value)
                entries[name] = {"kind": "file", "sha256": child_hash}
        encoded = _tree_bytes(entries)
        tree_hash = _sha256(encoded)
        objects.setdefault(tree_hash, encoded)
        return tree_hash

    return encode_tree(root), objects


def _reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def _parse_tree(raw: bytes, expected_hash: str) -> dict:
    if not isinstance(raw, bytes):
        raise ValueError(f"object {expected_hash} is not bytes")
    if _sha256(raw) != expected_hash:
        raise ValueError(f"object hash mismatch for {expected_hash}")
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=lambda name: (_ for _ in ()).throw(
                ValueError(f"invalid JSON constant: {name}")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"invalid tree object {expected_hash}: {exc}") from exc
    if not isinstance(value, dict) or set(value) != {"schema", "entries"}:
        raise ValueError(f"invalid tree schema at {expected_hash}")
    if value["schema"] != SCHEMA or not isinstance(value["entries"], dict):
        raise ValueError(f"invalid tree schema at {expected_hash}")
    if _tree_bytes(value["entries"]) != raw:
        raise ValueError(f"non-canonical tree object {expected_hash}")

    for name, reference in value["entries"].items():
        if not isinstance(name, str) or not _NAME.fullmatch(name):
            raise ValueError(f"unsafe tree entry name: {name!r}")
        if name in {".", ".."}:
            raise ValueError(f"unsafe tree entry name: {name!r}")
        if not isinstance(reference, dict) or set(reference) != {"kind", "sha256"}:
            raise ValueError(f"invalid tree reference for {name!r}")
        if not isinstance(reference["kind"], str) or reference["kind"] not in {"file", "tree"}:
            raise ValueError(f"invalid tree reference kind for {name!r}")
        if not isinstance(reference["sha256"], str) or not _HASH.fullmatch(
            reference["sha256"]
        ):
            raise ValueError(f"invalid tree reference hash for {name!r}")
    return value


def unpack(root_sha256: str, objects: Mapping[str, bytes]) -> Dict[str, bytes]:
    """Validate and unpack every object reachable from a directory root."""
    if not isinstance(root_sha256, str) or not _HASH.fullmatch(root_sha256):
        raise ValueError("invalid root hash")
    if not isinstance(objects, Mapping):
        raise ValueError("objects must be a mapping")
    for object_hash, raw in objects.items():
        if not isinstance(object_hash, str) or not _HASH.fullmatch(object_hash):
            raise ValueError("invalid object map hash")
        if not isinstance(raw, bytes):
            raise ValueError(f"object {object_hash} is not bytes")
    if root_sha256 not in objects:
        raise ValueError(f"missing object {root_sha256}")

    result: Dict[str, bytes] = {}
    active = set()
    memo = {}

    def walk_tree(tree_hash: str, prefix: str, depth: int) -> None:
        if depth > MAX_DIRECTORY_DEPTH:
            raise ValueError("directory depth exceeds 256")
        if tree_hash in active:
            raise ValueError("cyclic tree reference")
        if tree_hash in memo:
            files, height = memo[tree_hash]
            if depth + height > MAX_DIRECTORY_DEPTH:
                raise ValueError("directory depth exceeds 256")
            for path, data in files:
                result[f"{prefix}/{path}" if prefix else path] = data
            return
        active.add(tree_hash)
        try:
            descriptor = _parse_tree(objects.get(tree_hash), tree_hash)
            local = []
            height = 0
            for name in sorted(descriptor["entries"]):
                reference = descriptor["entries"][name]
                child_hash = reference["sha256"]
                path = f"{prefix}{name}" if not prefix else f"{prefix}/{name}"
                if reference["kind"] == "file":
                    raw = objects.get(child_hash)
                    if raw is None:
                        raise ValueError(f"missing object {child_hash}")
                    if _sha256(raw) != child_hash:
                        raise ValueError(f"object hash mismatch for {child_hash}")
                    result[path] = raw
                    local.append((name, raw))
                else:
                    walk_tree(child_hash, path, depth + 1)
                    child_files, child_height = memo[child_hash]
                    height = max(height, child_height + 1)
                    for suffix, data in child_files:
                        local.append((f"{name}/{suffix}", data))
            memo[tree_hash] = (tuple(local), height)
        finally:
            active.remove(tree_hash)

    root = _parse_tree(objects[root_sha256], root_sha256)
    # The root must be walked through the same closure checks as every child.
    del root
    walk_tree(root_sha256, "", 0)
    return result
