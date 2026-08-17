#!/usr/bin/env python3
"""Check the browser acceptance fixture without claiming live browser proof."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = SKILL_ROOT / "fixtures" / "verification_studio.html"

REQUIRED_IDS = (
    "agent-codename",
    "agent-email",
    "agent-paradigm",
    "agent-directives",
    "cap-sync",
    "cap-vector",
    "cap-telemetry",
    "btn-apply",
    "btn-reset",
    "passport-hud",
    "canvas-studio",
    "stroke-count",
    "drag-key",
    "drop-zone",
    "telemetry-log",
)

REQUIRED_HOOKS = (
    "function applyDirectives()",
    "function drawStarburstPreset()",
    "function drawSpiralPreset()",
    "function handleDragStart(e)",
    "function handleDrop(e)",
    "TOKEN_779_AUTHORIZED",
    "TOKEN_779 ACCEPTED",
)


def inspect_fixture(fixture_path: Path = FIXTURE_PATH) -> dict[str, object]:
    """Return a static integrity report for the HTML acceptance fixture."""
    if not fixture_path.is_file():
        raise FileNotFoundError(f"verification fixture missing: {fixture_path}")

    content = fixture_path.read_text(encoding="utf-8")
    missing_ids = [item for item in REQUIRED_IDS if f'id="{item}"' not in content]
    missing_hooks = [item for item in REQUIRED_HOOKS if item not in content]
    passed = not missing_ids and not missing_hooks
    return {
        "schema": "browser.fixture-check/v1",
        "scope": "static_fixture_only",
        "status": "PASS" if passed else "FAIL",
        "fixture": str(fixture_path),
        "required_ids": list(REQUIRED_IDS),
        "missing_ids": missing_ids,
        "required_hooks": list(REQUIRED_HOOKS),
        "missing_hooks": missing_hooks,
        "live_browser_verified": False,
        "note": (
            "This check does not launch Chrome, execute interactions, or capture "
            "screenshots. Run references/verification_suite.md for live proof."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check static integrity of the browser acceptance fixture."
    )
    parser.add_argument("--fixture", type=Path, default=FIXTURE_PATH)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        report = inspect_fixture(args.fixture)
    except (OSError, UnicodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"[{report['status']}] static browser fixture integrity")
        print(report["note"])
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
