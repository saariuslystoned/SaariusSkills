"""Typed user-correctable Puppet errors."""


class PuppetError(Exception):
    """Base error with a stable machine-readable category."""

    category = "puppet_error"

    def as_dict(self):
        return {"ok": False, "error": self.category, "detail": str(self)}


class ValidationError(PuppetError):
    category = "validation_error"


class ConflictError(PuppetError):
    category = "conflict"


class IdentityError(PuppetError):
    category = "identity_mismatch"


class UnsupportedError(PuppetError):
    category = "unsupported"
