#!/usr/bin/env python3
"""Validate a GrillTrack live variant picker manifest."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


class PickerError(RuntimeError):
    pass


def nonempty(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PickerError(f"{label} must be a non-empty string")
    return value.strip()


def validate(manifest: Any) -> None:
    if not isinstance(manifest, dict):
        raise PickerError("manifest must be a JSON object")
    if manifest.get("schema_version") != "grilltrack-picker/v0.1":
        raise PickerError("schema_version must be grilltrack-picker/v0.1")
    nonempty(manifest.get("round_id"), "round_id")
    nonempty(manifest.get("canvas_ref"), "canvas_ref")
    active_slot = nonempty(manifest.get("active_slot"), "active_slot")

    candidates = manifest.get("candidates")
    if not isinstance(candidates, list) or len(candidates) != 5:
        raise PickerError("candidates must contain exactly five entries")
    candidate_ids: list[str] = []
    for index, candidate in enumerate(candidates, start=1):
        if not isinstance(candidate, dict):
            raise PickerError(f"candidate {index} must be an object")
        candidate_ids.append(nonempty(candidate.get("id"), f"candidate {index}.id"))
        nonempty(candidate.get("label"), f"candidate {index}.label")
        nonempty(candidate.get("delta_ref"), f"candidate {index}.delta_ref")
        if candidate.get("recommended") not in {None, False}:
            raise PickerError("picker candidates must be presented neutrally")
    if len(set(candidate_ids)) != 5:
        raise PickerError("candidate ids must be unique")

    slots = manifest.get("slots")
    if not isinstance(slots, list) or not slots:
        raise PickerError("slots must be a non-empty array")
    slot_ids: list[str] = []
    unresolved: list[str] = []
    for index, slot in enumerate(slots, start=1):
        if not isinstance(slot, dict):
            raise PickerError(f"slot {index} must be an object")
        slot_id = nonempty(slot.get("id"), f"slot {index}.id")
        slot_ids.append(slot_id)
        status = slot.get("status")
        if status not in {"locked", "unresolved"}:
            raise PickerError(f"slot {slot_id} has invalid status")
        if status == "locked":
            nonempty(slot.get("selection_ref"), f"slot {slot_id}.selection_ref")
        else:
            unresolved.append(slot_id)
    if len(slot_ids) != len(set(slot_ids)):
        raise PickerError("slot ids must be unique")
    if unresolved != [active_slot]:
        raise PickerError("exactly one unresolved slot must equal active_slot")

    controls = manifest.get("controls")
    if not isinstance(controls, dict):
        raise PickerError("controls must be an object")
    for control in ("keyboard", "pointer", "mobile"):
        if controls.get(control) is not True:
            raise PickerError(f"{control} controls must be enabled")
    if manifest.get("production") is not False:
        raise PickerError("picker must be marked production=false")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest")
    args = parser.parse_args(argv)
    path = Path(args.manifest)
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
        validate(manifest)
    except (OSError, json.JSONDecodeError, PickerError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print("valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
