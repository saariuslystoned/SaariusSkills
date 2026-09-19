"""Typed user-correctable Puppet errors."""

from __future__ import annotations

from typing import Any, Dict, Optional


class PuppetError(Exception):
    """Base error with a stable machine-readable category."""

    category = "puppet_error"

    def __init__(self, detail: object = "", *, blocker: Optional[Dict[str, Any]] = None):
        super().__init__(detail)
        self.blocker = blocker

    def as_dict(self) -> Dict[str, Any]:
        payload = {"ok": False, "error": self.category, "detail": str(self)}
        if self.blocker is not None:
            payload["blocker"] = dict(self.blocker)
        return payload


class ValidationError(PuppetError):
    category = "validation_error"


class ConflictError(PuppetError):
    category = "conflict"


class IdentityError(PuppetError):
    category = "identity_mismatch"


class UnsupportedError(PuppetError):
    category = "unsupported"
