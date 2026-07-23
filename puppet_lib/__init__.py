"""Stage-1 static contract harness for Puppet's Antigravity teamwork plan.

See plans/puppet/antigravity-teamwork.md.
"""

from __future__ import annotations

from puppet_lib.teamwork import (
    TeamworkError,
    HelperCaps,
    TeamworkState,
    LeafRecord,
    TeamworkLedger,
    make_helper_caps,
    sanitized_summary,
    validate_repo_relative_path,
    validate_hex_digest,
    validate_id,
    DEFAULT_MAX_HELPERS,
    ALLOWED_MAX_HELPERS_OVERRIDES,
)

__all__ = [
    "TeamworkError",
    "HelperCaps",
    "TeamworkState",
    "LeafRecord",
    "TeamworkLedger",
    "make_helper_caps",
    "sanitized_summary",
    "validate_repo_relative_path",
    "validate_hex_digest",
    "validate_id",
    "DEFAULT_MAX_HELPERS",
    "ALLOWED_MAX_HELPERS_OVERRIDES",
]
