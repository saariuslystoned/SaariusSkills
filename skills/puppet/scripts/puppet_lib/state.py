"""Versioned Puppet lifecycle transitions."""

from __future__ import annotations

from typing import Dict, FrozenSet

from .errors import ValidationError


STATES = frozenset(
    {
        "NEW",
        "PREFLIGHTED",
        "STARTING",
        "ACTIVE",
        "WAITING_EXTERNAL",
        "CONFORMANCE_READY",
        "CONFORMANCE_CHECKPOINT_READY",
        "AWAITING_CONFORMANCE_REVIEW",
        "SOURCE_CHECKPOINT_READY",
        "AWAITING_SOURCE_REVIEW",
        "SOURCE_ACCEPTED",
        "PROOF_CHECKPOINT_READY",
        "TARGET_DONE",
        "AWAITING_CONTROLLER_REVIEW",
        "ACCEPTED",
        "BLOCKED",
        "FAILED",
        "HALTED",
        "CLOSED",
    }
)

TRANSITIONS: Dict[str, FrozenSet[str]] = {
    "NEW": frozenset({"PREFLIGHTED", "BLOCKED", "FAILED"}),
    "PREFLIGHTED": frozenset({"STARTING", "BLOCKED", "FAILED"}),
    "STARTING": frozenset({"ACTIVE", "BLOCKED", "FAILED", "HALTED"}),
    "ACTIVE": frozenset(
        {
            "WAITING_EXTERNAL",
            "CONFORMANCE_READY",
            "CONFORMANCE_CHECKPOINT_READY",
            "SOURCE_CHECKPOINT_READY",
            "BLOCKED",
            "FAILED",
            "HALTED",
        }
    ),
    "WAITING_EXTERNAL": frozenset({"ACTIVE", "BLOCKED", "FAILED", "HALTED"}),
    "CONFORMANCE_READY": frozenset({"ACTIVE", "BLOCKED", "FAILED", "HALTED"}),
    "CONFORMANCE_CHECKPOINT_READY": frozenset(
        {"AWAITING_CONFORMANCE_REVIEW", "BLOCKED", "FAILED", "HALTED"}
    ),
    "AWAITING_CONFORMANCE_REVIEW": frozenset(
        {"ACCEPTED", "BLOCKED", "FAILED", "HALTED"}
    ),
    "SOURCE_CHECKPOINT_READY": frozenset(
        {"AWAITING_SOURCE_REVIEW", "BLOCKED", "FAILED", "HALTED"}
    ),
    "AWAITING_SOURCE_REVIEW": frozenset(
        {"ACTIVE", "SOURCE_ACCEPTED", "BLOCKED", "FAILED", "HALTED"}
    ),
    "SOURCE_ACCEPTED": frozenset(
        {"PROOF_CHECKPOINT_READY", "BLOCKED", "FAILED", "HALTED"}
    ),
    "PROOF_CHECKPOINT_READY": frozenset(
        {"TARGET_DONE", "BLOCKED", "FAILED", "HALTED"}
    ),
    "TARGET_DONE": frozenset(
        {"AWAITING_CONTROLLER_REVIEW", "BLOCKED", "FAILED", "HALTED"}
    ),
    "AWAITING_CONTROLLER_REVIEW": frozenset(
        {"ACTIVE", "ACCEPTED", "BLOCKED", "FAILED", "HALTED"}
    ),
    "ACCEPTED": frozenset({"HALTED"}),
    "BLOCKED": frozenset({"HALTED"}),
    "FAILED": frozenset({"HALTED"}),
    "HALTED": frozenset({"CLOSED"}),
    "CLOSED": frozenset(),
}


def validate_state(value: str) -> str:
    if value not in STATES:
        raise ValidationError("unknown lifecycle state")
    return value


def transition(current: str, requested: str) -> str:
    validate_state(current)
    validate_state(requested)
    if requested not in TRANSITIONS[current]:
        raise ValidationError("illegal lifecycle transition: %s -> %s" % (current, requested))
    return requested


def is_terminal(value: str) -> bool:
    validate_state(value)
    return value in {"ACCEPTED", "BLOCKED", "FAILED", "HALTED", "CLOSED"}
