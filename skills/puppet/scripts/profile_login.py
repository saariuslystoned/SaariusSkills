#!/usr/bin/env python3
"""Execution-time-validated human subscription-login handoff."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from puppet_lib.errors import PuppetError
from puppet_lib.subscription_profiles import execute_subscription_profile_login


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="puppet-profile-login")
    parser.add_argument("--profile-root", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        execute_subscription_profile_login(
            profile_root=args.profile_root,
            helper_path=Path(__file__),
            interpreter_path=Path(sys.executable),
        )
    except PuppetError as exc:
        print(json.dumps(exc.as_dict(), sort_keys=True), file=sys.stderr)
        return 2
    return 0  # pragma: no cover - successful execution replaces this process


if __name__ == "__main__":
    raise SystemExit(main())
