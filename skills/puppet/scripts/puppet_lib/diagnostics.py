"""Version-scoped advisory and terminal-evidence separation."""

from __future__ import annotations

from typing import Any, Dict, Iterable

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
