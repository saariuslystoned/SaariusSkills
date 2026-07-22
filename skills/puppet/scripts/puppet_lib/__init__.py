"""Puppet's standard-library lifecycle and adapter control plane."""

from .errors import ConflictError, PuppetError, UnsupportedError, ValidationError
from .plane_activation import (
    ActivationPlan,
    ActivationRecovery,
    load_activation_plan,
    materialize_activation,
    plan_activation,
    recover_activation,
    rollback_activation,
    verify_activation,
)

__all__ = [
    "ConflictError",
    "PuppetError",
    "UnsupportedError",
    "ValidationError",
    "ActivationPlan",
    "ActivationRecovery",
    "load_activation_plan",
    "materialize_activation",
    "plan_activation",
    "recover_activation",
    "rollback_activation",
    "verify_activation",
]

__version__ = "0.1.0-bootstrap"
