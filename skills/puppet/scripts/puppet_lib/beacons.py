"""Bounded sanitized target-beacon parsing."""

from __future__ import annotations

import json
from typing import Any, Dict

from .errors import ValidationError
from .safety import validate_bounded_json


PREFIXES = {
    "PUPPET_STATUS": "status_claim",
    "PUPPET_ACTION_REQUIRED": "action_claim",
    "PUPPET_CONFORMANCE_READY": "checkpoint_claim",
    "PUPPET_CHECKPOINT": "checkpoint_claim",
    "PUPPET_HANDOFF_READY": "handoff_claim",
    "PUPPET_DONE": "completion_claim",
}


def parse_beacon(line: str) -> Dict[str, Any]:
    if not isinstance(line, str) or "\n" in line or len(line.encode("utf-8")) > 4096:
        raise ValidationError("beacon must be one bounded line")
    prefix, separator, body = line.partition(" ")
    if not separator or prefix not in PREFIXES:
        raise ValidationError("unknown beacon prefix")
    try:
        value = json.loads(body)
    except json.JSONDecodeError as exc:
        raise ValidationError("beacon body is invalid JSON") from exc
    if not isinstance(value, dict):
        raise ValidationError("beacon body must be an object")
    validate_bounded_json(
        value,
        max_depth=4,
        max_items=32,
        max_string=512,
        reject_sensitive_fields=True,
    )
    return {
        "prefix": prefix,
        "kind": PREFIXES[prefix],
        "authority": "target_claim",
        "data": value,
    }
