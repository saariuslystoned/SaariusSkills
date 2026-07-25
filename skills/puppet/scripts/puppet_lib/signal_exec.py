#!/usr/bin/env python3
"""Normalize Puppet's graceful-halt signal before directly executing a target."""

from __future__ import annotations

import os
import signal
import stat
import sys
from pathlib import Path
from typing import Sequence


def _validated_target(argv: Sequence[str]) -> list[str]:
    normalized = list(argv)
    if not normalized or not all(isinstance(item, str) and item for item in normalized):
        raise ValueError("signal exec requires a non-empty target argv")
    executable = Path(normalized[0])
    if not executable.is_absolute():
        raise ValueError("signal exec target must be absolute")
    try:
        details = executable.stat()
    except OSError as exc:
        raise ValueError("signal exec target is unavailable") from exc
    if not stat.S_ISREG(details.st_mode) or not os.access(executable, os.X_OK):
        raise ValueError("signal exec target must be an executable regular file")
    return normalized


def exec_with_default_sigint(argv: Sequence[str]) -> None:
    """Replace this helper with one exact target after normalizing SIGINT."""

    target = _validated_target(argv)
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    signal.pthread_sigmask(signal.SIG_UNBLOCK, {signal.SIGINT})
    os.execve(target[0], target, dict(os.environ))


def main() -> int:
    try:
        exec_with_default_sigint(sys.argv[1:])
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 64
    return 70  # pragma: no cover - a successful exec never returns


if __name__ == "__main__":
    raise SystemExit(main())
