"""Non-promotable Codex regular-session paired qualification substrate.

One accepted Codex worktree receipt is never public launch authority.  This
module can bind that positive run to a later ordinary-control run, one
structurally observed read-only native viewer, exact terminal lease history,
and the same private subscription profile.  The resulting create-only paired
receipt is controller-attested but deliberately has no manifest, launch, or
promotion consumer.

No function in this module reads a pane, transcript, prompt, auth value, or
configuration content.
"""

from __future__ import annotations

import os
import stat
import time
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional

from .authority import (
    AUTHORITY_ID,
    attest_qualification,
    controller_authority_root,
    lease_owner,
    verify_qualification_attestation,
)
from .errors import ConflictError, IdentityError, UnsupportedError, ValidationError
from .journal import Journal
from .safety import (
    canonical_json_bytes,
    ensure_within,
    paths_overlap,
    read_json,
    reject_symlink_components,
    sha256_bytes,
    sha256_file,
    validate_bounded_json,
    validate_identifier,
    validate_sha1,
    validate_sha256,
)


PAIR_SCHEMA_VERSION = 5
PAIR_KIND = "codex_regular_paired_qualification_substrate"
CONTROL_SOURCE_SCHEMA = "puppet.codex-ordinary-control-source/v1"
NATIVE_VIEW_SCHEMA = "puppet.codex-native-view-observation/v1"
NATIVE_VIEW_STATE = "read_only_attached_and_detached"
NATIVE_VIEW_NAME = "codex-native-view.json"
NATIVE_VIEW_ATTESTATION_SCHEMA_VERSION = 1

PAIR_BLOCKERS = (
    "paired receipt requires independent controller verification",
    "paired receipt is not accepted by adapter qualification",
    "public Codex launch remains fenced",
)

_PROCESS_FIELDS = {
    "identity_version",
    "pid",
    "start",
    "kernel_birth_id",
    "command",
    "executable_path",
    "device",
    "inode",
}
_LEASE_REF_FIELDS = {
    "session",
    "generation",
    "state",
    "lease_sha256",
    "owner_sha256",
    "process_sha256",
    "ledger_sequence",
    "ledger_entry_hash",
}
_CONTROL_SOURCE_FIELDS = {
    "schema",
    "positive_receipt",
    "run_id",
    "session",
    "controller",
    "campaign_id",
    "goal_fingerprint",
    "subscription_profile_sha256",
    "yolo_mapping_sha256",
    "candidate_head",
    "process_sha256",
    "tmux_sha256",
    "terminal_lease",
    "receipt_attestation_sequence",
}
_NATIVE_VIEW_FIELDS = {
    "schema",
    "target",
    "run_id",
    "controller",
    "campaign_id",
    "goal_fingerprint",
    "session",
    "state",
    "ready_checkpoint_id",
    "attach_argv_sha256",
    "tmux_sha256",
    "target_process_sha256",
    "viewer_client_sha256",
    "viewer_process_sha256",
    "viewer_client",
    "viewer_process",
    "read_only",
    "attached",
    "detached",
    "target_alive_after_detach",
    "body_capture_performed",
    "raw_retained",
    "controller_attestation",
}
_RECEIPT_REF_FIELDS = {
    "path",
    "sha256",
    "run_id",
    "session",
    "launch_plan_sha256",
    "accepted_checkpoint_id",
    "acceptance_sha256",
    "halt_receipt_sha256",
    "process_sha256",
    "tmux_sha256",
    "terminal_lease",
}
_POSITIVE_REF_FIELDS = _RECEIPT_REF_FIELDS | {"workspace_isolation"}
_PAIR_FIELDS = {
    "schema_version",
    "kind",
    "run_id",
    "target",
    "session_profile",
    "result",
    "controller",
    "campaign_id",
    "goal_fingerprint",
    "executable_fingerprint",
    "execution_fingerprint",
    "version_fingerprint",
    "platform_fingerprint",
    "adapter_fingerprint",
    "protocol_fingerprint",
    "yolo_mapping_sha256",
    "launch_plan_sha256",
    "subscription_profile_sha256",
    "instruction_policy_fingerprint",
    "capabilities",
    "accepted_checkpoint_id",
    "acceptance_sha256",
    "halt_receipt_sha256",
    "private_profile_root",
    "runtime_binding",
    "positive",
    "ordinary_control",
    "native_view",
    "entry_claim",
    "no_bleed",
    "receipt_attestation_order",
    "public_launch_authorized",
    "promotion_authorized",
    "independent_verification_required",
    "raw_retained",
    "blockers",
    "controller_attestation",
}


def _pair_sha(first: Any, second: Any) -> str:
    return sha256_bytes(canonical_json_bytes([first, second]))


def _canonical_file(path: Path | str, label: str) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = candidate.resolve(strict=True)
    if candidate.is_symlink() or not candidate.is_file():
        raise ValidationError("%s is unavailable or a symlink" % label)
    resolved = candidate.resolve(strict=True)
    if resolved != candidate or os.path.normpath(str(candidate)) != str(candidate):
        raise IdentityError("%s is not canonical" % label)
    return resolved


def _current_repository_tree(repository: Path) -> str:
    from .operator_plan import _git_executable, _git_output

    return validate_sha1(
        _git_output(
            _git_executable(),
            repository,
            ["rev-parse", "HEAD^{tree}"],
        ),
        "current repository tree",
    )


def _validated_entry_plan(
    path: Path,
    *,
    workspace_isolation: Mapping[str, Any],
) -> Dict[str, Any]:
    """Bind the exact direct-repository/cockpit planning claim to the worktree."""

    from .operator_plan import OPERATOR_PLAN_SCHEMA, OPERATOR_PLAN_STATE

    plan = read_json(path, max_bytes=1024 * 1024, reject_sensitive_fields=True)
    if not isinstance(plan, Mapping):
        raise ValidationError("Codex operator entry plan is invalid")
    mode = plan.get("entry_mode")
    repository = plan.get("repository")
    supplied_sha = plan.get("plan_sha256")
    unsigned = dict(plan)
    unsigned.pop("plan_sha256", None)
    if (
        plan.get("schema") != OPERATOR_PLAN_SCHEMA
        or plan.get("state") != OPERATOR_PLAN_STATE
        or plan.get("target") != "codex"
        or plan.get("session_profile") != "regular"
        or plan.get("launch_authorized") is not False
        or mode not in {"direct_git_root", "cockpit_explicit"}
        or not isinstance(repository, Mapping)
        or repository.get("repo") != workspace_isolation["candidate_root"]
        or repository.get("branch") != workspace_isolation["candidate_branch"]
        or repository.get("head") != workspace_isolation["candidate_head"]
        or repository.get("tree")
        != _current_repository_tree(Path(workspace_isolation["candidate_root"]))
        or repository.get("linked_worktree") is not True
        or repository.get("dirty") is not False
        or supplied_sha != sha256_bytes(canonical_json_bytes(unsigned))
    ):
        raise IdentityError(
            "Codex direct-repository/cockpit entry evidence is not exact"
        )
    validate_sha256(supplied_sha, "operator entry plan fingerprint")
    return {
        "mode": mode,
        "operator_plan": {
            "path": str(path),
            "sha256": sha256_file(path, max_bytes=1024 * 1024),
            "plan_sha256": supplied_sha,
        },
        "repository": {
            "repo": repository["repo"],
            "branch": repository["branch"],
            "head": repository["head"],
            "tree": repository["tree"],
            "linked_worktree": True,
            "dirty": False,
        },
    }


def _canonical_directory(path: Path | str, label: str) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = candidate.resolve(strict=True)
    if candidate.is_symlink() or not candidate.is_dir():
        raise ValidationError("%s is unavailable or a symlink" % label)
    resolved = candidate.resolve(strict=True)
    if resolved != candidate or os.path.normpath(str(candidate)) != str(candidate):
        raise IdentityError("%s is not canonical" % label)
    return resolved


def _write_new_json(path: Path, value: Mapping[str, Any]) -> tuple[int, int]:
    """Durably create one JSON artifact without replacing any preimage."""

    validate_bounded_json(
        value,
        max_depth=12,
        max_items=320,
        max_string=4096,
        reject_sensitive_fields=True,
    )
    path = Path(path)
    if not path.is_absolute():
        raise ValidationError("create-only artifact path must be absolute")
    parent = path.parent.resolve(strict=True)
    parent_details = parent.stat()
    if (
        parent.is_symlink()
        or not parent.is_dir()
        or parent_details.st_uid != os.getuid()
        or stat.S_IMODE(parent_details.st_mode) != 0o700
    ):
        raise IdentityError("create-only artifact parent must be current-UID 0700")
    reject_symlink_components(path, allow_missing_leaf=True)
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(str(path), flags, 0o600)
    except FileExistsError as exc:
        raise ConflictError("%s already exists" % path.name) from exc
    created_details = os.fstat(descriptor)
    created_identity = (created_details.st_dev, created_details.st_ino)
    try:
        payload = canonical_json_bytes(dict(value)) + b"\n"
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        directory = os.open(str(parent), os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        details = path.lstat()
        if not stat.S_ISREG(details.st_mode):
            raise IdentityError("create-only artifact identity changed")
        if (details.st_dev, details.st_ino) != created_identity:
            raise IdentityError("create-only artifact identity changed")
        return created_identity
    except BaseException:
        try:
            details = path.lstat()
            if (
                stat.S_ISREG(details.st_mode)
                and (details.st_dev, details.st_ino) == created_identity
            ):
                path.unlink()
        except FileNotFoundError:
            pass
        raise


def _receipt_session(receipt_path: Path, receipt: Mapping[str, Any]) -> str:
    from .adapter_manifest import validate_qualification_state_schema

    state = validate_qualification_state_schema(
        read_json(
            receipt_path.parent / "state.json",
            max_bytes=131072,
            reject_sensitive_fields=True,
        )
    )
    if state.get("run_id") != receipt.get("run_id"):
        raise IdentityError("Codex qualification state run changed")
    return validate_identifier(state.get("session"), "Codex qualification session")


def _receipt_artifacts(
    receipt_path: Path, receipt: Mapping[str, Any]
) -> Dict[str, Any]:
    from .adapter_manifest import _qualification_artifacts
    from .instructions import validate_instruction_manifest
    from .launch import validate_admitted_launch_plan

    paths = _qualification_artifacts(receipt_path, dict(receipt))
    session = _receipt_session(receipt_path, receipt)
    launch = validate_admitted_launch_plan(
        read_json(
            paths["launch_plan"],
            max_bytes=131072,
            reject_sensitive_fields=True,
        ),
        expected_target="codex",
        expected_session=session,
        expected_run_id=receipt["run_id"],
    )
    profile = read_json(
        paths["subscription_profile"],
        max_bytes=131072,
        reject_sensitive_fields=True,
    )
    evidence = read_json(
        paths["evidence"],
        max_bytes=131072,
        reject_sensitive_fields=True,
    )
    instructions = validate_instruction_manifest(
        read_json(
            paths["instructions"],
            max_bytes=131072,
            reject_sensitive_fields=True,
        ),
        target="codex",
    )
    descriptor = (
        read_json(
            paths["workspace_descriptor"],
            max_bytes=131072,
            reject_sensitive_fields=True,
        )
        if "workspace_descriptor" in paths
        else None
    )
    return {
        "paths": paths,
        "launch": launch,
        "profile": profile,
        "evidence": evidence,
        "instructions": instructions,
        "descriptor": descriptor,
    }


def _attestation_sequence(receipt: Mapping[str, Any], label: str) -> int:
    attestation = receipt.get("controller_attestation")
    sequence = (
        attestation.get("ledger_sequence")
        if isinstance(attestation, Mapping)
        else None
    )
    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence <= 0:
        raise ValidationError("%s receipt attestation sequence is invalid" % label)
    return sequence


def _validate_lease_ref(value: Any) -> Dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _LEASE_REF_FIELDS:
        raise ValidationError("Codex terminal lease reference is invalid")
    result = dict(value)
    validate_identifier(result.get("session"), "terminal lease session")
    generation = result.get("generation")
    sequence = result.get("ledger_sequence")
    if (
        isinstance(generation, bool)
        or not isinstance(generation, int)
        or generation <= 0
        or isinstance(sequence, bool)
        or not isinstance(sequence, int)
        or sequence <= 0
        or result.get("state") != "halted"
    ):
        raise ValidationError("Codex terminal lease state is invalid")
    for name in (
        "lease_sha256",
        "owner_sha256",
        "process_sha256",
        "ledger_entry_hash",
    ):
        validate_sha256(result.get(name), name.replace("_", " "))
    return result


def _terminal_lease_ref(
    *,
    receipt_path: Path,
    receipt: Mapping[str, Any],
    artifacts: Mapping[str, Any],
    session: str,
    authority_root: Optional[Path],
) -> Dict[str, Any]:
    """Find the exact halted lease row for one already terminal probe."""

    run_root = receipt_path.parent
    if run_root.parent.name != "probes":
        raise IdentityError("Codex receipt is outside the canonical probe topology")
    proof_root = run_root.parent.parent
    expected_owner = lease_owner(
        activity="probe",
        run_id=receipt["run_id"],
        campaign_id=receipt["campaign_id"],
        goal_fingerprint=receipt["goal_fingerprint"],
        proof_root=proof_root,
        state_root=run_root,
    )
    expected_instruction = sha256_file(
        artifacts["paths"]["instructions"], max_bytes=131072
    )
    expected_process = artifacts["evidence"].get("process")
    if (
        not isinstance(expected_process, Mapping)
        or set(expected_process) != _PROCESS_FIELDS
    ):
        raise ValidationError("Codex receipt target process identity is invalid")
    root = controller_authority_root(authority_root)
    rows = Journal(root / "session-lease-history.codex").snapshot()
    matches = []
    for row in rows:
        event = row.get("event")
        lease = event.get("lease") if isinstance(event, Mapping) else None
        if (
            event != {"kind": "session_lease", "lease": lease}
            or not isinstance(lease, Mapping)
            or lease.get("session") != session
            or lease.get("target") != "codex"
            or lease.get("controller") != receipt["controller"]
            or lease.get("owner") != expected_owner
            or lease.get("instruction_manifest_sha256") != expected_instruction
            or lease.get("state") != "halted"
            or lease.get("process") != expected_process
        ):
            continue
        matches.append((row, dict(lease)))
    if len(matches) != 1:
        raise IdentityError("Codex receipt lacks one exact terminal lease row")
    row, lease = matches[0]
    return _validate_lease_ref(
        {
            "session": session,
            "generation": lease["generation"],
            "state": "halted",
            "lease_sha256": sha256_bytes(canonical_json_bytes(lease)),
            "owner_sha256": sha256_bytes(canonical_json_bytes(expected_owner)),
            "process_sha256": sha256_bytes(canonical_json_bytes(expected_process)),
            "ledger_sequence": row["sequence"],
            "ledger_entry_hash": row["entry_hash"],
        }
    )


def build_codex_control_source(
    positive_receipt_path: Path | str,
    *,
    authority_root: Optional[Path] = None,
    current_manifest: Optional[Any] = None,
    server_process_fn: Optional[Any] = None,
    tmux_factory: Optional[Any] = None,
    _verify_receipt_fn: Optional[Callable[..., Dict[str, Any]]] = None,
    _terminal_lease_fn: Callable[..., Dict[str, Any]] = _terminal_lease_ref,
) -> Dict[str, Any]:
    """Bind an ordinary control to one earlier positive terminal run."""

    from .adapter_manifest import verify_qualification_receipt

    verify_receipt_fn = _verify_receipt_fn or verify_qualification_receipt
    path = _canonical_file(positive_receipt_path, "positive Codex receipt")
    receipt = verify_receipt_fn(
        path,
        _authority_root=authority_root,
        _current_manifest=current_manifest,
        _server_process_fn=server_process_fn,
        _tmux_factory=tmux_factory,
    )
    if (
        receipt.get("target") != "codex"
        or receipt.get("session_profile") != "regular"
        or receipt.get("workspace_isolation") is None
        or receipt.get("plane_activation") is not None
    ):
        raise ValidationError(
            "Codex ordinary control requires one positive worktree receipt"
        )
    artifacts = _receipt_artifacts(path, receipt)
    session = _receipt_session(path, receipt)
    lease = _terminal_lease_fn(
        receipt_path=path,
        receipt=receipt,
        artifacts=artifacts,
        session=session,
        authority_root=authority_root,
    )
    process = artifacts["evidence"].get("process")
    tmux = artifacts["evidence"].get("tmux")
    workspace = receipt["workspace_isolation"]
    value = {
        "schema": CONTROL_SOURCE_SCHEMA,
        "positive_receipt": {
            "path": str(path),
            "sha256": sha256_file(path, max_bytes=131072),
        },
        "run_id": receipt["run_id"],
        "session": session,
        "controller": receipt["controller"],
        "campaign_id": receipt["campaign_id"],
        "goal_fingerprint": receipt["goal_fingerprint"],
        "subscription_profile_sha256": receipt["subscription_profile_sha256"],
        "yolo_mapping_sha256": receipt["yolo_mapping_sha256"],
        "candidate_head": workspace["candidate_head"],
        "process_sha256": sha256_bytes(canonical_json_bytes(process)),
        "tmux_sha256": sha256_bytes(canonical_json_bytes(tmux)),
        "terminal_lease": lease,
        "receipt_attestation_sequence": _attestation_sequence(receipt, "positive"),
    }
    return validate_codex_control_source(value)


def validate_codex_control_source(value: Any) -> Dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _CONTROL_SOURCE_FIELDS:
        raise ValidationError("Codex ordinary-control source fields are invalid")
    result = dict(value)
    if result.get("schema") != CONTROL_SOURCE_SCHEMA:
        raise ValidationError("unsupported Codex ordinary-control source schema")
    reference = result.get("positive_receipt")
    if (
        not isinstance(reference, Mapping)
        or set(reference) != {"path", "sha256"}
        or not Path(str(reference.get("path", ""))).is_absolute()
    ):
        raise ValidationError("Codex positive receipt reference is invalid")
    validate_sha256(reference.get("sha256"), "positive receipt fingerprint")
    for name in ("run_id", "session", "controller", "campaign_id"):
        validate_identifier(result.get(name), name.replace("_", " "))
    for name in (
        "goal_fingerprint",
        "subscription_profile_sha256",
        "yolo_mapping_sha256",
        "process_sha256",
        "tmux_sha256",
    ):
        validate_sha256(result.get(name), name.replace("_", " "))
    validate_sha1(result.get("candidate_head"), "positive candidate head")
    result["terminal_lease"] = _validate_lease_ref(result.get("terminal_lease"))
    sequence = result.get("receipt_attestation_sequence")
    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence <= 0:
        raise ValidationError("positive receipt attestation sequence is invalid")
    validate_bounded_json(
        result,
        max_depth=5,
        max_items=64,
        max_string=4096,
        reject_sensitive_fields=True,
    )
    return result


def _native_attach_argv(evidence: Mapping[str, Any]) -> list[str]:
    tmux = evidence.get("tmux")
    if not isinstance(tmux, Mapping):
        raise ValidationError("Codex native-view tmux identity is unavailable")
    binary = tmux.get("tmux_binary_identity")
    if not isinstance(binary, Mapping):
        raise ValidationError("Codex native-view tmux executable is unavailable")
    return [
        binary["path"],
        "-f",
        os.devnull,
        "-S",
        tmux["socket"],
        "attach-session",
        "-r",
        "-E",
        "-t",
        tmux["session"],
    ]


def _native_view_event(core: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "schema_version": NATIVE_VIEW_ATTESTATION_SCHEMA_VERSION,
        "kind": "codex_native_view_observation",
        "observation_digest": sha256_bytes(canonical_json_bytes(core)),
        "run_id": core["run_id"],
        "session": core["session"],
        "target_process_sha256": core["target_process_sha256"],
        "tmux_sha256": core["tmux_sha256"],
        "viewer_client_sha256": core["viewer_client_sha256"],
        "viewer_process_sha256": core["viewer_process_sha256"],
    }


def _attest_native_view(
    core: Mapping[str, Any], *, authority_root: Optional[Path]
) -> Dict[str, Any]:
    root = controller_authority_root(authority_root)
    event = _native_view_event(core)
    request_id = "codex-view-%s" % event["observation_digest"][:40]
    row = Journal(root / "codex-native-view-observations").append(
        request_id=request_id,
        event=event,
    )
    return {
        "schema_version": NATIVE_VIEW_ATTESTATION_SCHEMA_VERSION,
        "authority_id": AUTHORITY_ID,
        "authority_root": str(root),
        "request_id": request_id,
        "ledger_sequence": row["sequence"],
        "ledger_entry_hash": row["entry_hash"],
        "observation_digest": event["observation_digest"],
    }


def _verify_native_view_attestation(
    core: Mapping[str, Any],
    attestation: Any,
    *,
    authority_root: Optional[Path],
) -> None:
    expected_fields = {
        "schema_version",
        "authority_id",
        "authority_root",
        "request_id",
        "ledger_sequence",
        "ledger_entry_hash",
        "observation_digest",
    }
    root = controller_authority_root(authority_root)
    if (
        not isinstance(attestation, Mapping)
        or set(attestation) != expected_fields
        or attestation.get("schema_version")
        != NATIVE_VIEW_ATTESTATION_SCHEMA_VERSION
        or attestation.get("authority_id") != AUTHORITY_ID
        or attestation.get("authority_root") != str(root)
    ):
        raise ValidationError("Codex native-view controller attestation is invalid")
    validate_identifier(
        attestation.get("request_id"), "native-view attestation request"
    )
    for name in ("ledger_entry_hash", "observation_digest"):
        validate_sha256(attestation.get(name), name.replace("_", " "))
    sequence = attestation.get("ledger_sequence")
    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence <= 0:
        raise ValidationError("Codex native-view attestation sequence is invalid")
    event = _native_view_event(core)
    if attestation["observation_digest"] != event["observation_digest"]:
        raise IdentityError("Codex native-view observation is not attested")
    row = Journal(root / "codex-native-view-observations").lookup(
        attestation["request_id"]
    )
    if (
        row is None
        or row.get("sequence") != sequence
        or row.get("entry_hash") != attestation["ledger_entry_hash"]
        or row.get("event") != event
    ):
        raise IdentityError("Codex native-view attestation is unavailable")


def _validate_native_view_core(
    result: Dict[str, Any],
    *,
    receipt: Mapping[str, Any],
    session: str,
    evidence: Mapping[str, Any],
    attach_argv: list[str],
) -> Dict[str, Any]:
    if (
        result.get("schema") != NATIVE_VIEW_SCHEMA
        or result.get("target") != "codex"
        or result.get("run_id") != receipt.get("run_id")
        or result.get("controller") != receipt.get("controller")
        or result.get("campaign_id") != receipt.get("campaign_id")
        or result.get("goal_fingerprint") != receipt.get("goal_fingerprint")
        or result.get("session") != session
        or result.get("state") != NATIVE_VIEW_STATE
        or result.get("ready_checkpoint_id")
        != evidence.get("ready", {}).get("checkpoint_id")
        or result.get("read_only") is not True
        or result.get("attached") is not True
        or result.get("detached") is not True
        or result.get("target_alive_after_detach") is not True
        or result.get("body_capture_performed") is not False
        or result.get("raw_retained") is not False
    ):
        raise ValidationError("Codex native-view terminal state is invalid")
    viewer_client = result.get("viewer_client")
    viewer_process = result.get("viewer_process")
    target_process = evidence.get("process")
    tmux = evidence.get("tmux")
    server_process = tmux.get("server_identity") if isinstance(tmux, Mapping) else None
    binary = (
        tmux.get("tmux_binary_identity") if isinstance(tmux, Mapping) else None
    )
    if (
        not isinstance(viewer_client, Mapping)
        or set(viewer_client) != {"pid", "tty", "read_only", "session"}
        or viewer_client.get("read_only") is not True
        or viewer_client.get("session") != session
        or not isinstance(viewer_client.get("tty"), str)
        or not viewer_client["tty"].startswith("/dev/")
        or not isinstance(viewer_process, Mapping)
        or set(viewer_process) != _PROCESS_FIELDS
        or viewer_process.get("pid") != viewer_client.get("pid")
        or viewer_client.get("pid")
        in {
            (target_process or {}).get("pid"),
            (server_process or {}).get("pid"),
        }
        or not isinstance(binary, Mapping)
        or viewer_process.get("executable_path") != binary.get("path")
        or viewer_process.get("device") != binary.get("device")
        or viewer_process.get("inode") != binary.get("inode")
    ):
        raise IdentityError(
            "Codex target, tmux server, and viewer identities are not distinct"
        )
    for name in (
        "ready_checkpoint_id",
        "goal_fingerprint",
        "attach_argv_sha256",
        "tmux_sha256",
        "target_process_sha256",
        "viewer_client_sha256",
        "viewer_process_sha256",
    ):
        validate_sha256(result.get(name), name.replace("_", " "))
    expected = {
        "attach_argv_sha256": sha256_bytes(canonical_json_bytes(attach_argv)),
        "tmux_sha256": sha256_bytes(canonical_json_bytes(evidence.get("tmux"))),
        "target_process_sha256": sha256_bytes(
            canonical_json_bytes(evidence.get("process"))
        ),
        "viewer_client_sha256": sha256_bytes(
            canonical_json_bytes(viewer_client)
        ),
        "viewer_process_sha256": sha256_bytes(
            canonical_json_bytes(viewer_process)
        ),
    }
    if any(result[name] != digest for name, digest in expected.items()):
        raise IdentityError("Codex native-view runtime identity changed")
    validate_bounded_json(
        result,
        max_depth=2,
        max_items=32,
        max_string=4096,
        reject_sensitive_fields=True,
    )
    return result


def validate_native_view_record(
    value: Any,
    *,
    receipt: Mapping[str, Any],
    session: str,
    evidence: Mapping[str, Any],
    attach_argv: list[str],
    authority_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Validate one body-free, controller-attested native-view rendezvous."""

    if not isinstance(value, Mapping) or set(value) != _NATIVE_VIEW_FIELDS:
        raise ValidationError("Codex native-view fields do not match schema")
    result = dict(value)
    attestation = result.pop("controller_attestation")
    core = _validate_native_view_core(
        result,
        receipt=receipt,
        session=session,
        evidence=evidence,
        attach_argv=attach_argv,
    )
    _verify_native_view_attestation(
        core,
        attestation,
        authority_root=authority_root,
    )
    result["controller_attestation"] = dict(attestation)
    validate_bounded_json(
        result,
        max_depth=4,
        max_items=64,
        max_string=4096,
        reject_sensitive_fields=True,
    )
    return result


def observe_codex_native_view(
    *,
    proof_root: Path,
    run_id: str,
    timeout: float = 30.0,
    _tmux_factory: Optional[Callable[[Path], Any]] = None,
    _process_birth_fn: Optional[Callable[[int], Dict[str, Any]]] = None,
    _sleep_fn: Callable[[float], None] = time.sleep,
    _monotonic_fn: Callable[[], float] = time.monotonic,
    _authority_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Observe an actual read-only tmux client attach and detach, structurally."""

    from .campaign import process_birth_identity
    from .tmux import TmuxController

    if (
        isinstance(timeout, bool)
        or not isinstance(timeout, (int, float))
        or timeout <= 0
    ):
        raise ValidationError("native-view timeout is invalid")
    proof = _canonical_directory(proof_root, "probe proof root")
    run_id = validate_identifier(run_id, "native-view run id")
    run_root = ensure_within(
        proof / "probes" / run_id,
        proof,
        must_exist=True,
    )
    state_path = run_root / "state.json"
    evidence_path = run_root / "evidence.json"
    state = read_json(state_path, max_bytes=131072, reject_sensitive_fields=True)
    evidence = read_json(
        evidence_path, max_bytes=131072, reject_sensitive_fields=True
    )
    tmux_value = evidence.get("tmux")
    process = evidence.get("process")
    ready = evidence.get("ready")
    if (
        state.get("run_id") != run_id
        or state.get("target") != "codex"
        or state.get("session") != (tmux_value or {}).get("session")
        or state.get("phase")
        not in {
            "ready_validated",
            "followup_validated",
            "accepted_awaiting_halt",
        }
        or not isinstance(tmux_value, Mapping)
        or not isinstance(process, Mapping)
        or set(process) != _PROCESS_FIELDS
        or not isinstance(ready, Mapping)
    ):
        raise ValidationError("Codex probe is not in a native-view live phase")
    process_birth_fn = _process_birth_fn or process_birth_identity
    tmux_factory = _tmux_factory or TmuxController
    socket = Path(tmux_value["socket"])
    session = tmux_value["session"]
    server = tmux_value["server_identity"]
    controller = tmux_factory(run_root / "tmux-authority")
    controller.assert_tmux_binary_identity(tmux_value["tmux_binary_identity"])
    controller.bind_server_identity(socket, server)
    attach_argv = controller.attach_argv(
        socket=socket,
        session=session,
        pane=tmux_value["target_id"],
        server_identity=server,
    )

    def runtime_check() -> None:
        current_state = read_json(
            state_path, max_bytes=131072, reject_sensitive_fields=True
        )
        current_evidence = read_json(
            evidence_path, max_bytes=131072, reject_sensitive_fields=True
        )
        metadata = controller.metadata_for_session(
            socket=socket,
            session=session,
            server_identity=server,
        )
        if (
            current_state.get("run_id") != run_id
            or current_state.get("phase")
            not in {
                "ready_validated",
                "followup_validated",
                "accepted_awaiting_halt",
            }
            or current_evidence.get("tmux") != tmux_value
            or current_evidence.get("process") != process
            or process_birth_fn(process["pid"]) != process
            or metadata.get("session") != session
            or metadata.get("pane") != tmux_value["target_id"]
            or metadata.get("pane_pid") != process["pid"]
            or metadata.get("pane_dead") is not False
        ):
            raise IdentityError("Codex native-view target identity changed")

    runtime_check()
    if controller.viewer_clients(
        socket=socket, session=session, server_identity=server
    ):
        raise IdentityError("Codex native-view observation started with a client")
    deadline = _monotonic_fn() + float(timeout)
    viewer: Optional[Dict[str, Any]] = None
    viewer_process: Optional[Dict[str, Any]] = None
    while _monotonic_fn() < deadline:
        runtime_check()
        clients = controller.viewer_clients(
            socket=socket, session=session, server_identity=server
        )
        if clients:
            if len(clients) != 1 or clients[0].get("read_only") is not True:
                raise IdentityError("Codex native-view client is not exactly read-only")
            viewer = dict(clients[0])
            viewer_process = process_birth_fn(viewer["pid"])
            binary = tmux_value["tmux_binary_identity"]
            if (
                viewer.get("session") != session
                or not isinstance(viewer.get("tty"), str)
                or not viewer["tty"].startswith("/dev/")
                or viewer["pid"] in {process["pid"], server.get("pid")}
                or viewer_process.get("pid") != viewer["pid"]
                or viewer_process.get("executable_path") != binary["path"]
                or viewer_process.get("device") != binary["device"]
                or viewer_process.get("inode") != binary["inode"]
            ):
                raise IdentityError("Codex native-view client identity is invalid")
            break
        _sleep_fn(0.1)
    if viewer is None or viewer_process is None:
        raise ValidationError("Codex native-view attach was not observed")
    while _monotonic_fn() < deadline:
        runtime_check()
        clients = controller.viewer_clients(
            socket=socket, session=session, server_identity=server
        )
        if not clients:
            runtime_check()
            break
        if clients != [viewer]:
            raise IdentityError("Codex native-view client identity changed")
        _sleep_fn(0.1)
    else:
        raise ValidationError("Codex native-view detach was not observed")
    record = {
        "schema": NATIVE_VIEW_SCHEMA,
        "target": "codex",
        "run_id": run_id,
        "controller": state["controller"],
        "campaign_id": evidence["campaign_id"],
        "goal_fingerprint": evidence["goal_fingerprint"],
        "session": session,
        "state": NATIVE_VIEW_STATE,
        "ready_checkpoint_id": ready["checkpoint_id"],
        "attach_argv_sha256": sha256_bytes(canonical_json_bytes(attach_argv)),
        "tmux_sha256": sha256_bytes(canonical_json_bytes(tmux_value)),
        "target_process_sha256": sha256_bytes(canonical_json_bytes(process)),
        "viewer_client_sha256": sha256_bytes(canonical_json_bytes(viewer)),
        "viewer_process_sha256": sha256_bytes(canonical_json_bytes(viewer_process)),
        "viewer_client": viewer,
        "viewer_process": viewer_process,
        "read_only": True,
        "attached": True,
        "detached": True,
        "target_alive_after_detach": True,
        "body_capture_performed": False,
        "raw_retained": False,
    }
    _validate_native_view_core(
        record,
        receipt={
            "run_id": run_id,
            "controller": state["controller"],
            "campaign_id": evidence["campaign_id"],
            "goal_fingerprint": evidence["goal_fingerprint"],
        },
        session=session,
        evidence=evidence,
        attach_argv=attach_argv,
    )
    record["controller_attestation"] = _attest_native_view(
        record,
        authority_root=_authority_root,
    )
    validate_native_view_record(
        record,
        receipt={
            "run_id": run_id,
            "controller": state["controller"],
            "campaign_id": evidence["campaign_id"],
            "goal_fingerprint": evidence["goal_fingerprint"],
        },
        session=session,
        evidence=evidence,
        attach_argv=attach_argv,
        authority_root=_authority_root,
    )
    destination = run_root / NATIVE_VIEW_NAME
    _write_new_json(destination, record)
    return {
        "ok": True,
        "target": "codex",
        "run_id": run_id,
        "native_view": str(destination),
        "native_view_sha256": sha256_file(destination, max_bytes=65536),
        "read_only": True,
        "body_capture_performed": False,
        "raw_retained": False,
    }


def _default_launch_is_exact(
    launch: Mapping[str, Any],
    instructions: Mapping[str, Any],
) -> bool:
    argv = launch.get("argv")
    return (
        instructions.get("runtime_binding") == {"model": "default", "effort": "default"}
        and instructions.get("model_observation")
        == {
            "selection": "current_default",
            "resolved_identity": "unavailable",
            "effort": "unavailable",
        }
        and isinstance(argv, list)
        and len(argv) == 2
        and all(
            selector not in argv
            for selector in (
                "--model",
                "-m",
                "--profile",
                "-p",
                "--config",
                "-c",
                "--effort",
            )
        )
        and launch.get("launch_identity", {}).get("env_names") == ["CODEX_HOME"]
    )


def _receipt_ref(
    *,
    path: Path,
    receipt: Mapping[str, Any],
    session: str,
    artifacts: Mapping[str, Any],
    lease: Mapping[str, Any],
    positive: bool,
) -> Dict[str, Any]:
    for name in (
        "launch_plan_sha256",
        "accepted_checkpoint_id",
        "acceptance_sha256",
        "halt_receipt_sha256",
    ):
        validate_sha256(receipt.get(name), name.replace("_", " "))
    result = {
        "path": str(path),
        "sha256": sha256_file(path, max_bytes=131072),
        "run_id": receipt["run_id"],
        "session": session,
        "launch_plan_sha256": receipt["launch_plan_sha256"],
        "accepted_checkpoint_id": receipt["accepted_checkpoint_id"],
        "acceptance_sha256": receipt["acceptance_sha256"],
        "halt_receipt_sha256": receipt["halt_receipt_sha256"],
        "process_sha256": sha256_bytes(
            canonical_json_bytes(artifacts["evidence"]["process"])
        ),
        "tmux_sha256": sha256_bytes(
            canonical_json_bytes(artifacts["evidence"]["tmux"])
        ),
        "terminal_lease": dict(lease),
    }
    if positive:
        result["workspace_isolation"] = receipt["workspace_isolation"]
    return result


def _verify_receipt_pair(
    *,
    positive_receipt_path: Path,
    ordinary_receipt_path: Path,
    private_profile_root: Path,
    native_view_path: Path,
    entry_plan_path: Path,
    authority_root: Optional[Path],
    current_manifest: Optional[Any],
    server_process_fn: Optional[Any],
    tmux_factory: Optional[Any],
    verify_receipt_fn: Optional[Callable[..., Dict[str, Any]]],
    terminal_lease_fn: Callable[..., Dict[str, Any]],
) -> Dict[str, Any]:
    from .adapter_manifest import verify_qualification_receipt

    verifier = verify_receipt_fn or verify_qualification_receipt
    positive = verifier(
        positive_receipt_path,
        _authority_root=authority_root,
        _current_manifest=current_manifest,
        _server_process_fn=server_process_fn,
        _tmux_factory=tmux_factory,
    )
    positive_artifacts = _receipt_artifacts(positive_receipt_path, positive)
    positive_session = _receipt_session(positive_receipt_path, positive)
    positive_lease = terminal_lease_fn(
        receipt_path=positive_receipt_path,
        receipt=positive,
        artifacts=positive_artifacts,
        session=positive_session,
        authority_root=authority_root,
    )
    control_state = read_json(
        ordinary_receipt_path.parent / "state.json",
        max_bytes=131072,
        reject_sensitive_fields=True,
    )
    persisted_source = validate_codex_control_source(
        control_state.get("codex_control_source")
    )
    expected_source = build_codex_control_source(
        positive_receipt_path,
        authority_root=authority_root,
        current_manifest=current_manifest,
        server_process_fn=server_process_fn,
        tmux_factory=tmux_factory,
        _verify_receipt_fn=verifier,
        _terminal_lease_fn=terminal_lease_fn,
    )
    if persisted_source != expected_source:
        raise IdentityError("Codex ordinary control is not linked to the positive run")
    ordinary = verifier(
        ordinary_receipt_path,
        _authority_root=authority_root,
        _current_manifest=current_manifest,
        _server_process_fn=server_process_fn,
        _tmux_factory=tmux_factory,
        _codex_control_source=expected_source,
    )
    if (
        positive.get("target") != "codex"
        or positive.get("workspace_isolation") is None
        or ordinary.get("target") != "codex"
        or ordinary.get("workspace_isolation") is not None
        or positive.get("plane_activation") is not None
        or ordinary.get("plane_activation") is not None
        or positive.get("session_profile") != "regular"
        or ordinary.get("session_profile") != "regular"
    ):
        raise UnsupportedError(
            "Codex pair requires one worktree run and one ordinary control"
        )
    shared_fields = (
        "target",
        "session_profile",
        "controller",
        "campaign_id",
        "goal_fingerprint",
        "executable_fingerprint",
        "execution_fingerprint",
        "version_fingerprint",
        "platform_fingerprint",
        "adapter_fingerprint",
        "protocol_fingerprint",
        "yolo_mapping_sha256",
        "subscription_profile_sha256",
        "instruction_policy_fingerprint",
        "capabilities",
    )
    if any(positive.get(name) != ordinary.get(name) for name in shared_fields):
        raise IdentityError("Codex positive and ordinary control identities differ")
    positive_sequence = _attestation_sequence(positive, "positive")
    ordinary_sequence = _attestation_sequence(ordinary, "ordinary control")
    if positive_sequence >= ordinary_sequence:
        raise IdentityError("Codex receipt attestation order is invalid")
    if (
        positive["run_id"] == ordinary["run_id"]
        or positive["accepted_checkpoint_id"] == ordinary["accepted_checkpoint_id"]
    ):
        raise IdentityError("Codex positive and ordinary control are not independent")

    ordinary_artifacts = _receipt_artifacts(ordinary_receipt_path, ordinary)
    ordinary_session = _receipt_session(ordinary_receipt_path, ordinary)
    ordinary_lease = terminal_lease_fn(
        receipt_path=ordinary_receipt_path,
        receipt=ordinary,
        artifacts=ordinary_artifacts,
        session=ordinary_session,
        authority_root=authority_root,
    )
    if (
        positive_lease["generation"] == ordinary_lease["generation"]
        or positive_lease["ledger_sequence"] >= ordinary_lease["ledger_sequence"]
    ):
        raise IdentityError("Codex terminal leases are not distinct and ordered")
    expected_profile = str(private_profile_root)
    if (
        positive_artifacts["profile"].get("profile_root") != expected_profile
        or ordinary_artifacts["profile"].get("profile_root") != expected_profile
        or positive["subscription_profile_sha256"]
        != ordinary["subscription_profile_sha256"]
    ):
        raise IdentityError("Codex qualification private profile binding differs")
    positive_launch = positive_artifacts["launch"]
    ordinary_launch = ordinary_artifacts["launch"]
    positive_workspace = positive["workspace_isolation"]
    if (
        positive_launch["cwd"] != positive_workspace["startup_cwd"]
        or positive_launch["cwd"] != positive_workspace["candidate_root"]
        or ordinary_launch["cwd"] == positive_launch["cwd"]
        or paths_overlap(Path(positive_launch["cwd"]), Path(ordinary_launch["cwd"]))
        or positive_launch["argv"] != ordinary_launch["argv"]
        or positive_launch["launch_identity"]["env_names"]
        != ordinary_launch["launch_identity"]["env_names"]
        or positive_launch["launch_identity"]["env_fingerprint"]
        != ordinary_launch["launch_identity"]["env_fingerprint"]
        or not _default_launch_is_exact(
            positive_launch, positive_artifacts["instructions"]
        )
        or not _default_launch_is_exact(
            ordinary_launch, ordinary_artifacts["instructions"]
        )
    ):
        raise IdentityError("Codex default/no-selector workspace join is invalid")
    positive_evidence = positive_artifacts["evidence"]
    ordinary_evidence = ordinary_artifacts["evidence"]
    positive_process = positive_evidence.get("process")
    ordinary_process = ordinary_evidence.get("process")
    positive_tmux = positive_evidence.get("tmux")
    ordinary_tmux = ordinary_evidence.get("tmux")
    if (
        positive_evidence.get("active_target_processes_before_launch") != []
        or positive_evidence.get("active_target_processes_after_halt") != []
        or ordinary_evidence.get("active_target_processes_before_launch") != []
        or ordinary_evidence.get("active_target_processes_after_halt") != []
        or positive_process == ordinary_process
        or positive_session == ordinary_session
        or not isinstance(positive_tmux, Mapping)
        or not isinstance(ordinary_tmux, Mapping)
        or positive_tmux == ordinary_tmux
        or positive_tmux.get("socket") == ordinary_tmux.get("socket")
        or positive_tmux.get("server_identity")
        == ordinary_tmux.get("server_identity")
    ):
        raise IdentityError("Codex paired process/tmux no-bleed evidence is incomplete")
    native_raw = read_json(
        native_view_path, max_bytes=65536, reject_sensitive_fields=True
    )
    native = validate_native_view_record(
        native_raw,
        receipt=positive,
        session=positive_session,
        evidence=positive_evidence,
        attach_argv=_native_attach_argv(positive_evidence),
        authority_root=authority_root,
    )
    descriptor = positive_artifacts["descriptor"]
    if (
        not isinstance(descriptor, Mapping)
        or descriptor.get("surface") != "controller_proved_direct_worktree_cwd"
        or descriptor.get("descriptor_sha256")
        != positive_workspace["descriptor_sha256"]
        or descriptor.get("candidate_root") != positive_workspace["candidate_root"]
        or descriptor.get("candidate_head") != positive_workspace["candidate_head"]
    ):
        raise IdentityError("Codex direct-worktree entry claim is not evidence-backed")
    entry_claim = _validated_entry_plan(
        entry_plan_path,
        workspace_isolation=positive_workspace,
    )
    entry_claim.update(
        {
            "surface": descriptor["surface"],
            "descriptor_sha256": positive_workspace["descriptor_sha256"],
        }
    )
    return {
        "positive": positive,
        "ordinary": ordinary,
        "positive_artifacts": positive_artifacts,
        "ordinary_artifacts": ordinary_artifacts,
        "positive_session": positive_session,
        "ordinary_session": ordinary_session,
        "positive_lease": positive_lease,
        "ordinary_lease": ordinary_lease,
        "positive_sequence": positive_sequence,
        "ordinary_sequence": ordinary_sequence,
        "native": native,
        "entry_claim": entry_claim,
    }


def _pair_core(
    *,
    verified: Mapping[str, Any],
    positive_path: Path,
    ordinary_path: Path,
    native_path: Path,
    entry_plan_path: Path,
    profile_root: Path,
) -> Dict[str, Any]:
    positive = verified["positive"]
    ordinary = verified["ordinary"]
    positive_artifacts = verified["positive_artifacts"]
    ordinary_artifacts = verified["ordinary_artifacts"]
    positive_ref = _receipt_ref(
        path=positive_path,
        receipt=positive,
        session=verified["positive_session"],
        artifacts=positive_artifacts,
        lease=verified["positive_lease"],
        positive=True,
    )
    ordinary_ref = _receipt_ref(
        path=ordinary_path,
        receipt=ordinary,
        session=verified["ordinary_session"],
        artifacts=ordinary_artifacts,
        lease=verified["ordinary_lease"],
        positive=False,
    )
    pair_id = sha256_bytes(
        canonical_json_bytes(
            [
                positive_ref["sha256"],
                ordinary_ref["sha256"],
                sha256_file(native_path, max_bytes=65536),
                sha256_file(entry_plan_path, max_bytes=1024 * 1024),
            ]
        )
    )
    positive_population = positive_artifacts["evidence"][
        "active_target_processes_before_launch"
    ]
    ordinary_population = ordinary_artifacts["evidence"][
        "active_target_processes_before_launch"
    ]
    return {
        "schema_version": PAIR_SCHEMA_VERSION,
        "kind": PAIR_KIND,
        "run_id": "codex-pair-" + pair_id[:24],
        "target": "codex",
        "session_profile": "regular",
        "result": "paired_evidence_only",
        "controller": positive["controller"],
        "campaign_id": positive["campaign_id"],
        "goal_fingerprint": positive["goal_fingerprint"],
        "executable_fingerprint": positive["executable_fingerprint"],
        "execution_fingerprint": positive["execution_fingerprint"],
        "version_fingerprint": positive["version_fingerprint"],
        "platform_fingerprint": positive["platform_fingerprint"],
        "adapter_fingerprint": positive["adapter_fingerprint"],
        "protocol_fingerprint": positive["protocol_fingerprint"],
        "yolo_mapping_sha256": positive["yolo_mapping_sha256"],
        "launch_plan_sha256": _pair_sha(
            positive["launch_plan_sha256"], ordinary["launch_plan_sha256"]
        ),
        "subscription_profile_sha256": positive[
            "subscription_profile_sha256"
        ],
        "instruction_policy_fingerprint": positive[
            "instruction_policy_fingerprint"
        ],
        "capabilities": list(positive["capabilities"]),
        "accepted_checkpoint_id": _pair_sha(
            positive["accepted_checkpoint_id"], ordinary["accepted_checkpoint_id"]
        ),
        "acceptance_sha256": _pair_sha(
            positive["acceptance_sha256"], ordinary["acceptance_sha256"]
        ),
        "halt_receipt_sha256": _pair_sha(
            positive["halt_receipt_sha256"], ordinary["halt_receipt_sha256"]
        ),
        "private_profile_root": str(profile_root),
        "runtime_binding": {
            "model": "provider_default",
            "effort": "provider_default",
            "observed_identity": "unresolved",
            "explicit_selector": False,
        },
        "positive": positive_ref,
        "ordinary_control": ordinary_ref,
        "native_view": {
            "path": str(native_path),
            "sha256": sha256_file(native_path, max_bytes=65536),
            "record": verified["native"],
        },
        "entry_claim": verified["entry_claim"],
        "no_bleed": {
            "positive_cwd": positive_artifacts["launch"]["cwd"],
            "ordinary_control_cwd": ordinary_artifacts["launch"]["cwd"],
            "positive_population_sha256": sha256_bytes(
                canonical_json_bytes(positive_population)
            ),
            "ordinary_control_population_sha256": sha256_bytes(
                canonical_json_bytes(ordinary_population)
            ),
            "empty_baselines_and_terminal_populations": True,
            "distinct_non_overlapping_workspaces": True,
            "distinct_processes": True,
            "distinct_tmux_servers_sockets_sessions": True,
            "distinct_terminal_leases": True,
            "same_launch_argv": True,
            "same_closed_profile_context": True,
        },
        "receipt_attestation_order": {
            "positive": verified["positive_sequence"],
            "ordinary_control": verified["ordinary_sequence"],
        },
        "public_launch_authorized": False,
        "promotion_authorized": False,
        "independent_verification_required": True,
        "raw_retained": False,
        "blockers": list(PAIR_BLOCKERS),
    }


def create_codex_regular_pair_receipt(
    *,
    out: Path,
    positive_receipt_path: Path | str,
    ordinary_receipt_path: Path | str,
    native_view_path: Path | str,
    entry_plan_path: Path | str,
    private_profile_root: Path | str,
    authority_root: Optional[Path] = None,
    _current_manifest: Optional[Any] = None,
    _server_process_fn: Optional[Any] = None,
    _tmux_factory: Optional[Any] = None,
    _verify_receipt_fn: Optional[Callable[..., Dict[str, Any]]] = None,
    _terminal_lease_fn: Callable[..., Dict[str, Any]] = _terminal_lease_ref,
) -> Dict[str, Any]:
    """Create and controller-attest one explicitly non-promotable pair."""

    positive_path = _canonical_file(positive_receipt_path, "positive receipt")
    ordinary_path = _canonical_file(
        ordinary_receipt_path, "ordinary control receipt"
    )
    native_path = _canonical_file(native_view_path, "native-view record")
    entry_path = _canonical_file(entry_plan_path, "operator entry plan")
    profile_root = _canonical_directory(private_profile_root, "private profile root")
    if positive_path == ordinary_path:
        raise IdentityError("Codex paired receipts must be distinct")
    verified = _verify_receipt_pair(
        positive_receipt_path=positive_path,
        ordinary_receipt_path=ordinary_path,
        private_profile_root=profile_root,
        native_view_path=native_path,
        entry_plan_path=entry_path,
        authority_root=authority_root,
        current_manifest=_current_manifest,
        server_process_fn=_server_process_fn,
        tmux_factory=_tmux_factory,
        verify_receipt_fn=_verify_receipt_fn,
        terminal_lease_fn=_terminal_lease_fn,
    )
    core = _pair_core(
        verified=verified,
        positive_path=positive_path,
        ordinary_path=ordinary_path,
        native_path=native_path,
        entry_plan_path=entry_path,
        profile_root=profile_root,
    )
    bundle = dict(
        core,
        controller_attestation=attest_qualification(
            core, authority_root=authority_root
        ),
    )
    destination = Path(out)
    created_identity = _write_new_json(destination, bundle)
    try:
        verify_codex_regular_pair_receipt(
            destination,
            expected_private_profile_root=profile_root,
            _authority_root=authority_root,
            _current_manifest=_current_manifest,
            _server_process_fn=_server_process_fn,
            _tmux_factory=_tmux_factory,
            _verify_receipt_fn=_verify_receipt_fn,
            _terminal_lease_fn=_terminal_lease_fn,
        )
    except BaseException:
        try:
            details = destination.lstat()
            if (
                stat.S_ISREG(details.st_mode)
                and (details.st_dev, details.st_ino) == created_identity
            ):
                destination.unlink()
        except FileNotFoundError:
            pass
        raise
    return {
        "ok": True,
        "target": "codex",
        "result": "paired_evidence_only",
        "receipt": str(destination),
        "receipt_sha256": sha256_file(destination, max_bytes=131072),
        "public_launch_authorized": False,
        "promotion_authorized": False,
        "independent_verification_required": True,
        "raw_retained": False,
    }


def verify_codex_regular_pair_receipt(
    value_or_path: Mapping[str, Any] | Path | str,
    *,
    expected_private_profile_root: Path | str,
    _authority_root: Optional[Path] = None,
    _current_manifest: Optional[Any] = None,
    _server_process_fn: Optional[Any] = None,
    _tmux_factory: Optional[Any] = None,
    _verify_receipt_fn: Optional[Callable[..., Dict[str, Any]]] = None,
    _terminal_lease_fn: Callable[..., Dict[str, Any]] = _terminal_lease_ref,
) -> Dict[str, Any]:
    """Independently rebuild the pair from current terminal source evidence."""

    if isinstance(value_or_path, Mapping):
        value = dict(value_or_path)
    else:
        path = _canonical_file(value_or_path, "Codex paired receipt")
        value = read_json(path, max_bytes=131072, reject_sensitive_fields=True)
    if not isinstance(value, dict) or set(value) != _PAIR_FIELDS:
        raise ValidationError("Codex paired receipt fields do not match schema")
    if (
        value.get("schema_version") != PAIR_SCHEMA_VERSION
        or value.get("kind") != PAIR_KIND
        or value.get("target") != "codex"
        or value.get("session_profile") != "regular"
        or value.get("result") != "paired_evidence_only"
        or value.get("public_launch_authorized") is not False
        or value.get("promotion_authorized") is not False
        or value.get("independent_verification_required") is not True
        or value.get("raw_retained") is not False
        or value.get("blockers") != list(PAIR_BLOCKERS)
    ):
        raise ValidationError("Codex paired receipt state is invalid")
    if (
        not isinstance(value.get("positive"), Mapping)
        or set(value["positive"]) != _POSITIVE_REF_FIELDS
        or not isinstance(value.get("ordinary_control"), Mapping)
        or set(value["ordinary_control"]) != _RECEIPT_REF_FIELDS
    ):
        raise ValidationError("Codex paired receipt references are invalid")
    native_ref = value.get("native_view")
    if not isinstance(native_ref, Mapping) or set(native_ref) != {
        "path",
        "sha256",
        "record",
    }:
        raise ValidationError("Codex native-view reference is invalid")
    receipt_core = dict(value)
    attestation = receipt_core.pop("controller_attestation")
    verified_attestation = verify_qualification_attestation(
        receipt_core, attestation, authority_root=_authority_root
    )
    profile_root = _canonical_directory(
        value.get("private_profile_root"), "private profile root"
    )
    expected_profile = _canonical_directory(
        expected_private_profile_root, "expected private profile root"
    )
    if profile_root != expected_profile:
        raise IdentityError("Codex paired receipt private profile root changed")
    positive_path = _canonical_file(value["positive"]["path"], "positive receipt")
    ordinary_path = _canonical_file(
        value["ordinary_control"]["path"], "ordinary control receipt"
    )
    native_path = _canonical_file(native_ref["path"], "native-view record")
    entry_claim = value.get("entry_claim")
    entry_reference = (
        entry_claim.get("operator_plan")
        if isinstance(entry_claim, Mapping)
        else None
    )
    if (
        not isinstance(entry_reference, Mapping)
        or set(entry_reference) != {"path", "sha256", "plan_sha256"}
    ):
        raise ValidationError("Codex operator entry-plan reference is invalid")
    entry_path = _canonical_file(
        entry_reference["path"], "Codex operator entry plan"
    )
    for path, reference, maximum in (
        (positive_path, value["positive"], 131072),
        (ordinary_path, value["ordinary_control"], 131072),
        (native_path, native_ref, 65536),
        (entry_path, entry_reference, 1024 * 1024),
    ):
        validate_sha256(reference.get("sha256"), "Codex paired artifact")
        if sha256_file(path, max_bytes=maximum) != reference["sha256"]:
            raise IdentityError("Codex paired artifact fingerprint changed")
    verified = _verify_receipt_pair(
        positive_receipt_path=positive_path,
        ordinary_receipt_path=ordinary_path,
        private_profile_root=profile_root,
        native_view_path=native_path,
        entry_plan_path=entry_path,
        authority_root=_authority_root,
        current_manifest=_current_manifest,
        server_process_fn=_server_process_fn,
        tmux_factory=_tmux_factory,
        verify_receipt_fn=_verify_receipt_fn,
        terminal_lease_fn=_terminal_lease_fn,
    )
    expected_core = _pair_core(
        verified=verified,
        positive_path=positive_path,
        ordinary_path=ordinary_path,
        native_path=native_path,
        entry_plan_path=entry_path,
        profile_root=profile_root,
    )
    if receipt_core != expected_core:
        raise IdentityError("Codex paired receipt drifted from terminal evidence")
    pair_sequence = verified_attestation["sequence"]
    if verified["ordinary_sequence"] >= pair_sequence:
        raise IdentityError("Codex paired controller attestation order is invalid")
    validate_identifier(value.get("run_id"), "Codex paired run id")
    validate_bounded_json(
        value,
        max_depth=12,
        max_items=320,
        max_string=4096,
        reject_sensitive_fields=True,
    )
    return value


__all__ = [
    "CONTROL_SOURCE_SCHEMA",
    "NATIVE_VIEW_NAME",
    "NATIVE_VIEW_SCHEMA",
    "PAIR_BLOCKERS",
    "PAIR_KIND",
    "build_codex_control_source",
    "create_codex_regular_pair_receipt",
    "observe_codex_native_view",
    "validate_codex_control_source",
    "validate_native_view_record",
    "verify_codex_regular_pair_receipt",
]
