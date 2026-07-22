"""Puppet's standard-library lifecycle and adapter control plane."""

from .errors import ConflictError, PuppetError, UnsupportedError, ValidationError
from .plane_activation import (
    ActivationLaunchContext,
    ActivationPlan,
    ActivationRecovery,
    build_activation_launch_context,
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
    "ActivationLaunchContext",
    "ActivationPlan",
    "ActivationRecovery",
    "build_activation_launch_context",
    "load_activation_plan",
    "materialize_activation",
    "plan_activation",
    "recover_activation",
    "rollback_activation",
    "verify_activation",
]

__version__ = "0.1.0-bootstrap"
