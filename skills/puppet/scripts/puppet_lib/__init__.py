"""Puppet's standard-library lifecycle and adapter control plane."""

from .errors import ConflictError, PuppetError, UnsupportedError, ValidationError

__all__ = [
    "ConflictError",
    "PuppetError",
    "UnsupportedError",
    "ValidationError",
]

__version__ = "0.1.0-bootstrap"
