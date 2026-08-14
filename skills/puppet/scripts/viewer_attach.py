#!/usr/bin/env python3
"""Internal one-use human viewer ticket consumer."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from puppet_lib.errors import PuppetError
from puppet_lib.session import attach_viewer


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="puppet-viewer-attach",
        description="Consume one short-lived Puppet native-view ticket.",
    )
    parser.add_argument("--state-root", required=True, type=Path)
    parser.add_argument("--session", required=True)
    parser.add_argument("--ticket", required=True, type=Path)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        attach_viewer(
            state_root=args.state_root,
            session=args.session,
            ticket_path=args.ticket,
        )
    except PuppetError as exc:
        print(json.dumps(exc.as_dict(), sort_keys=True), file=sys.stderr)
        return 2
    return 70


if __name__ == "__main__":
    raise SystemExit(main())
