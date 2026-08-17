#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import os
import re
import stat
import sys
from pathlib import Path
from typing import Any


MAX_IMPLEMENTATION_BYTES = 256 * 1024
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _failure_code(args: list[str]) -> int:
    return 0 if args and args[0] == "record" else 2


def _verified_implementation(expected_sha256: str) -> tuple[Path, bytes]:
    path = Path(__file__).resolve(strict=True).parent / (
        "herdr_puppet_lib/claude_hook_marker.py"
    )
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
        file_stat = os.fstat(descriptor)
        if (
            not stat.S_ISREG(file_stat.st_mode)
            or file_stat.st_uid != os.getuid()
            or file_stat.st_size > MAX_IMPLEMENTATION_BYTES
        ):
            raise RuntimeError("unsafe Claude hook implementation")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            encoded = stream.read(MAX_IMPLEMENTATION_BYTES + 1)
        if (
            len(encoded) > MAX_IMPLEMENTATION_BYTES
            or hashlib.sha256(encoded).hexdigest() != expected_sha256
        ):
            raise RuntimeError("Claude hook implementation fingerprint changed")
        return path, encoded
    finally:
        if descriptor is not None:
            os.close(descriptor)


def main(argv: list[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    try:
        if args.count("--implementation-sha256") != 1:
            raise RuntimeError("missing implementation fingerprint")
        index = args.index("--implementation-sha256")
        if index + 1 >= len(args):
            raise RuntimeError("missing implementation fingerprint")
        expected_sha256 = args[index + 1]
        if _SHA256.fullmatch(expected_sha256) is None:
            raise RuntimeError("invalid implementation fingerprint")
        implementation_args = args[:index] + args[index + 2 :]
        path, encoded = _verified_implementation(expected_sha256)
        namespace: dict[str, Any] = {
            "__builtins__": __builtins__,
            "__file__": str(path),
            "__name__": "_herdr_puppet_claude_hook_marker",
            "__package__": None,
        }
        exec(compile(encoded, str(path), "exec"), namespace)
        implementation_main = namespace.get("main")
        if not callable(implementation_main):
            raise RuntimeError("Claude hook implementation entrypoint missing")
        result = implementation_main(implementation_args)
        if isinstance(result, bool) or not isinstance(result, int):
            raise RuntimeError("Claude hook implementation result invalid")
        return result
    except Exception:
        return _failure_code(args)


if __name__ == "__main__":
    raise SystemExit(main())
