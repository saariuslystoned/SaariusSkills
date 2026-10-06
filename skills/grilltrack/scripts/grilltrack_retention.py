"""Pure content-addressed Merkle directory codec for historical retention.

The codec stores file bytes and canonical JSON directory descriptors in one
hash-addressed object map.  Directory traversal is bounded to 256 levels when
packing and unpacking; this is intentionally separate from the existing reconciliation
recursion bound of 32. Logical expansion is limited to 100,000 files and
256 MiB of file bytes plus ASCII path bytes; oversized inputs fail before
materializing aliases, without truncating historical content.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Dict, Mapping, Tuple


SCHEMA = "grilltrack/retention-tree/v1"
MAX_DIRECTORY_DEPTH = 256
MAX_EXPANDED_FILES = 100_000
MAX_EXPANDED_BYTES = 256 * 1024 * 1024
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


def _check_expansion(count: int, byte_count: int) -> None:
    if count > MAX_EXPANDED_FILES or byte_count > MAX_EXPANDED_BYTES:
        raise ValueError("retention expansion exceeds file or byte budget")


def pack(files: Mapping[str, bytes]) -> Tuple[str, Dict[str, bytes]]:
    """Pack a path-to-bytes mapping into a root hash and immutable objects."""
    if not isinstance(files, Mapping):
        raise ValueError("files must be a mapping")

    root: dict = {}
    byte_count = 0
    _check_expansion(len(files), 0)
    for path, data in files.items():
        parts = _safe_path(path)
        if len(parts) - 1 > MAX_DIRECTORY_DEPTH:
            raise ValueError("directory depth exceeds 256")
        if not isinstance(data, bytes):
            raise ValueError(f"file {path!r} must contain bytes")
        byte_count += len(data) + len(path.encode("ascii"))
        _check_expansion(len(files), byte_count)
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

    # Count aliases arithmetically over the DAG before constructing expanded
    # paths. A tiny shared DAG can otherwise request exponentially many files.
    sizes = {}
    nodes = {}
    sizing = set()
    verified_files = set()

    def measure(tree_hash: str, depth: int):
        if depth > MAX_DIRECTORY_DEPTH:
            raise ValueError("directory depth exceeds 256")
        if tree_hash in sizing:
            raise ValueError("cyclic tree reference")
        if tree_hash in sizes:
            count, payload, path_bytes, height = sizes[tree_hash]
            if depth + height > MAX_DIRECTORY_DEPTH:
                raise ValueError("directory depth exceeds 256")
            return sizes[tree_hash]
        sizing.add(tree_hash)
        try:
            descriptor = _parse_tree(objects.get(tree_hash), tree_hash)
            nodes[tree_hash] = descriptor["entries"]
            count = payload = path_bytes = height = 0
            for name, reference in descriptor["entries"].items():
                child_hash = reference["sha256"]
                if reference["kind"] == "file":
                    raw = objects.get(child_hash)
                    if raw is None:
                        raise ValueError(f"missing object {child_hash}")
                    if child_hash not in verified_files:
                        if _sha256(raw) != child_hash:
                            raise ValueError(f"object hash mismatch for {child_hash}")
                        verified_files.add(child_hash)
                    count += 1
                    payload += len(raw)
                    path_bytes += len(name)
                else:
                    child_count, child_payload, child_paths, child_height = measure(child_hash, depth + 1)
                    count += child_count
                    payload += child_payload
                    path_bytes += child_paths + (len(name) + 1) * child_count
                    height = max(height, child_height + 1)
                _check_expansion(count, payload + path_bytes)
            sizes[tree_hash] = (count, payload, path_bytes, height)
            return sizes[tree_hash]
        finally:
            sizing.remove(tree_hash)

    measure(root_sha256, 0)
    result: Dict[str, bytes] = {}

    def expand(tree_hash: str, prefix: str) -> None:
        # Closure, depth and total expanded size are already proven. Retain
        # only final paths, rather than every ancestor's expanded path list.
        # Empty aliased subtrees require no path materialization at all.
        if not sizes[tree_hash][0]:
            return
        for name, reference in sorted(nodes[tree_hash].items()):
            path = f"{prefix}/{name}" if prefix else name
            if reference["kind"] == "file":
                result[path] = objects[reference["sha256"]]
            else:
                expand(reference["sha256"], path)

    expand(root_sha256, "")
    return result
