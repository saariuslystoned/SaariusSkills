"""Bounded, non-secret diagnostics for operator-visible preflight blockers."""

from __future__ import annotations

from typing import Any, Dict, Iterable, Optional

from .errors import ValidationError
from .safety import validate_sha256


TERMINAL_SOURCES = frozenset(
    {"controller_protocol_failure", "provider_execution_error", "exact_process_exit"}
)


def agy_overage_advisory(
    *, executable_fingerprint: str, current_surface_validated: bool
) -> Dict[str, Any]:
    validate_sha256(executable_fingerprint, "executable fingerprint")
    return {
        "code": "agy_ai_overage_credits_exhausted",
        "scope": executable_fingerprint,
        "evidence": "current_surface_validated" if current_surface_validated else "dated_untrusted_fixture",
        "authority": "advisory",
        "terminal": False,
        "diagnostic_required": False,
    }


def terminal_verdict(facts: Iterable[Dict[str, Any]]) -> str:
    terminal = []
    for fact in facts:
        if not isinstance(fact, dict):
            raise ValidationError("diagnostic facts must be objects")
        if fact.get("terminal") and fact.get("source") in TERMINAL_SOURCES:
            terminal.append(fact)
    if not terminal:
        return "continue"
    outcomes = {fact.get("outcome") for fact in terminal}
    if "failed" in outcomes:
        return "failed"
    if "blocked" in outcomes:
        return "blocked"
    return "stopped"


def identity_blocker(
    *,
    check: str,
    remedy: str,
    pid: Optional[int] = None,
    birth_identity: Optional[str] = None,
    terminal_association: Optional[str] = None,
) -> Dict[str, Any]:
    """Return safe diagnostic fields without serializing an exception or argv."""

    for value, label in ((check, "check"), (remedy, "remedy")):
        if not isinstance(value, str) or not value or len(value) > 200:
            raise ValidationError("diagnostic %s is invalid" % label)
    if pid is not None and (
        isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0
    ):
        raise ValidationError("diagnostic pid is invalid")
    for value, label in (
        (birth_identity, "birth identity"),
        (terminal_association, "terminal association"),
    ):
        if value is not None and (
            not isinstance(value, str) or not value or len(value) > 200
        ):
            raise ValidationError("diagnostic %s is invalid" % label)
    return {
        "check": check,
        "remedy": remedy,
        "pid": pid,
        "birth_identity": birth_identity,
        "terminal_association": terminal_association,
    }
