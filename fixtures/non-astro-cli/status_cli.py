#!/usr/bin/env python3
"""Tiny non-Astro/no-GitHub renderer used by GrillTrack evaluations."""

from __future__ import annotations

import argparse
import json


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--format", choices=("compact", "detailed"), default="compact")
    args = parser.parse_args()
    state = {"service": "fixture", "status": "ready", "jobs": 2}
    if args.format == "compact":
        print("fixture: ready (2 jobs)")
    else:
        print(json.dumps(state, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
