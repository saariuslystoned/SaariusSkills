from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping

from .errors import HerdrPuppetError


DESTINATION_RECEIPT_SCHEMA = "herdr-puppet.destination-selection-receipt.v1"
SELECTED_AUTHORITY_SCHEMA = "herdr-puppet.selected-authority.v1"


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def deterministic_owned_label(run_id: str, harness: str, ordinal: int) -> str:
    safe_harness = re.sub(r"[^a-z0-9]+", "-", harness.lower()).strip("-")
    safe_run = re.sub(r"[^a-z0-9]+", "", run_id.lower())
    if not safe_harness or not safe_run:
        raise HerdrPuppetError(
            "invalid_label_material",
            "Run ID and harness must produce a deterministic label.",
        )
    run_digest = hashlib.sha256(run_id.encode("utf-8")).hexdigest()[:6]
    return f"puppet-{safe_harness}-{safe_run[:8]}-{run_digest}-{ordinal}"


def _legacy_destination_selection(record: Mapping[str, Any]) -> dict[str, Any]:
    owned_label = record.get("owned_label")
    workspace = record.get("workspace")
    if not isinstance(owned_label, str) or not isinstance(workspace, Mapping):
        raise HerdrPuppetError(
            "legacy_destination_selection_unavailable",
            "Historical destination authority cannot be derived safely.",
        )
    ordinal_match = re.search(r"-(\d+)$", owned_label)
    workspace_label = workspace.get("label")
    if ordinal_match is None or not isinstance(workspace_label, str):
        raise HerdrPuppetError(
            "legacy_destination_selection_unavailable",
            "The historical lease tab ordinal cannot be derived safely.",
        )
    return {
        "schema": DESTINATION_RECEIPT_SCHEMA,
        "mode": "legacy_explicit",
        "machine": None,
        "workspace_label": workspace_label,
        "tab": {"request": "fresh", "ordinal": int(ordinal_match.group(1))},
        "legacy_ordinal_alias": True,
        "catalog_path_retained": False,
        "ssh_target_retained": False,
        "existing_tab_adoption": False,
    }


def destination_selection_for_record(
    record: Mapping[str, Any],
) -> dict[str, Any]:
    selection = record.get("destination_selection")
    if isinstance(selection, Mapping):
        return json.loads(json.dumps(selection))
    return _legacy_destination_selection(record)


def selected_authority(record: Mapping[str, Any]) -> dict[str, Any]:
    ssh = record.get("ssh")
    if "expected_ssh_target" in record:
        ssh_target = record.get("expected_ssh_target")
    elif isinstance(ssh, Mapping):
        ssh_target = ssh.get("target")
    else:
        ssh_target = None
    binding = record.get("harness_binding")
    if not isinstance(binding, Mapping):
        raise HerdrPuppetError(
            "selected_authority_unavailable",
            "Selected authority requires a complete harness binding.",
        )
    selection = destination_selection_for_record(record)
    return {
        "schema": SELECTED_AUTHORITY_SCHEMA,
        "run_id": record.get("run_id"),
        "harness": record.get("harness"),
        "session": record.get("session"),
        "destination": {
            "machine": selection["machine"],
            "workspace_label": selection["workspace_label"],
            "tab": selection["tab"],
        },
        "workspace": record.get("workspace"),
        "owned_label": record.get("owned_label"),
        "ssh_target": ssh_target,
        "source": record.get("source"),
        "proof_root": record.get("proof_root"),
        "harness_binding": binding,
        "model_identity": binding.get("model_observation"),
    }


def selected_authority_sha256(record: Mapping[str, Any]) -> str:
    return canonical_sha256(selected_authority(record))
