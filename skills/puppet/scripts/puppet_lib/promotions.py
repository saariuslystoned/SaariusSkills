"""Bootstrap promotion boundary."""

from .errors import UnsupportedError


def promote_bootstrap(*args, **kwargs):
    raise UnsupportedError(
        "promote is unsupported by bootstrap Puppet N until its campaign qualification passes"
    )


def close_bootstrap(*args, **kwargs):
    raise UnsupportedError("close is unsupported by bootstrap Puppet N")
