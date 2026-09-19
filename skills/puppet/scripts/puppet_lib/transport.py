"""Explicit Puppet run-transport binding. One transport per run; no fallback."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from .caller import TRANSPORT_BINDING_SCHEMA, make_blocker
from .errors import UnsupportedError, ValidationError


NAMED_TRANSPORTS = ("tmux", "herdr", "acp", "agy-print")
DEFAULT_TRANSPORT = "tmux"
IMPLEMENTED_TRANSPORT = "tmux"

# Capability/proof table. Structured transports are named and unsupported.
# Do not invent status, halt, or resume behavior for an unimplemented id.
TRANSPORT_CAPABILITIES: Dict[str, Dict[str, Any]] = {
    "tmux": {
        "id": "tmux",
        "implementation": "implemented",
        "status_proves": "pane_and_process_identity",
        "status_does_not_prove": "harness_turn_result",
        "halt_proves": "registered_pid_gone_and_pane_dead",
        "halt_authority": "puppet_owned_birth_and_exact_target",
        "resume_proves": "unsupported",
        "transport_independent": (
            "checkpoints",
            "review",
            "controller_acceptance",
            "human_gates",
        ),
        "qualification_evidence": "shared_transport_authority_scope",
    },
    "herdr": {
        "id": "herdr",
        "implementation": "unsupported",
        "status_proves": "unsupported",
        "status_does_not_prove": "unsupported",
        "halt_proves": "unsupported",
        "halt_authority": "unsupported",
        "resume_proves": "unsupported",
        "transport_independent": (
            "checkpoints",
            "review",
            "controller_acceptance",
            "human_gates",
        ),
        "qualification_evidence": "unsupported",
    },
    "acp": {
        "id": "acp",
        "implementation": "unsupported",
        "status_proves": "unsupported",
        "status_does_not_prove": "unsupported",
        "halt_proves": "unsupported",
        "halt_authority": "unsupported",
        "resume_proves": "unsupported",
        "transport_independent": (
            "checkpoints",
            "review",
            "controller_acceptance",
            "human_gates",
        ),
        "qualification_evidence": "unsupported",
    },
    "agy-print": {
        "id": "agy-print",
        "implementation": "unsupported",
        "status_proves": "unsupported",
        "status_does_not_prove": "unsupported",
        "halt_proves": "unsupported",
        "halt_authority": "unsupported",
        "resume_proves": "unsupported",
        "transport_independent": (
            "checkpoints",
            "review",
            "controller_acceptance",
            "human_gates",
        ),
        "qualification_evidence": "unsupported",
    },
}


def transport_capability_table() -> Dict[str, Dict[str, Any]]:
    """Return the per-transport capability and proof table."""

    return {
        name: {
            **dict(row),
            "transport_independent": list(row["transport_independent"]),
        }
        for name, row in TRANSPORT_CAPABILITIES.items()
    }


def _unsupported_transport_error(name: str) -> UnsupportedError:
    detail = (
        "transport %s is named but not implemented; tmux is the only bound "
        "Puppet run transport"
        % name
    )
    return UnsupportedError(
        detail,
        blocker=make_blocker(
            code="transport_unsupported",
            detail=detail,
            changed="requested transport %s is not an implemented Puppet run transport"
            % name,
        ),
    )


def normalize_transport_name(value: Any, *, label: str = "transport") -> str:
    if value is None:
        return DEFAULT_TRANSPORT
    if not isinstance(value, str) or not value.strip():
        raise ValidationError("%s is invalid" % label)
    name = value.strip()
    if name not in NAMED_TRANSPORTS:
        raise ValidationError("unsupported %s" % label)
    return name


def bind_run_transport(
    requested: Any = None,
    *,
    contract_transport: Any = None,
) -> Dict[str, str]:
    """Bind exactly one transport for a run. Never fall back to another id."""

    requested_name = (
        None if requested is None else normalize_transport_name(requested)
    )
    contract_name = (
        None
        if contract_transport is None
        else normalize_transport_name(contract_transport, label="contract transport")
    )
    if (
        requested_name is not None
        and contract_name is not None
        and requested_name != contract_name
    ):
        raise ValidationError("requested transport does not match the contract")
    name = requested_name or contract_name or DEFAULT_TRANSPORT
    if name != IMPLEMENTED_TRANSPORT:
        raise _unsupported_transport_error(name)
    return {"schema": TRANSPORT_BINDING_SCHEMA, "id": name}


def validate_transport_binding(value: Any) -> Dict[str, str]:
    if (
        not isinstance(value, Mapping)
        or set(value) != {"schema", "id"}
        or value.get("schema") != TRANSPORT_BINDING_SCHEMA
    ):
        raise ValidationError("transport binding fields do not match schema")
    name = normalize_transport_name(value.get("id"), label="bound transport")
    if name != IMPLEMENTED_TRANSPORT:
        raise _unsupported_transport_error(name)
    return {"schema": TRANSPORT_BINDING_SCHEMA, "id": name}


def record_transport_id(record: Mapping[str, Any]) -> str:
    binding = record.get("transport")
    if binding is None:
        raise ValidationError("session is missing its explicit transport binding")
    return validate_transport_binding(binding)["id"]


def transport_is_available(name: str) -> bool:
    from .tmux import TmuxController

    name = normalize_transport_name(name)
    if name != IMPLEMENTED_TRANSPORT:
        return False
    return TmuxController.available()


def open_run_transport(
    binding: Mapping[str, Any],
    registry_root: Path,
    **kwargs: Any,
):
    """Open the bound transport. Only tmux is implemented."""

    from .tmux import TmuxController

    validated = validate_transport_binding(binding)
    if validated["id"] != IMPLEMENTED_TRANSPORT:
        raise _unsupported_transport_error(validated["id"])
    return TmuxController(registry_root, **kwargs)


def open_bound_transport(
    record: Mapping[str, Any],
    registry_root: Path,
    **kwargs: Any,
) -> TmuxController:
    """Open the transport already bound on a session record."""

    return open_run_transport(record.get("transport"), registry_root, **kwargs)
