"""Strict task-contract parsing and immutable identity binding."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Dict, FrozenSet, Optional, Tuple

from .errors import ValidationError
from .safety import (
    absolute_root,
    canonical_json_bytes,
    paths_overlap,
    read_json,
    sha256_bytes,
    validate_branch,
    validate_identifier,
)


TARGETS = frozenset({"agy", "cursor", "claude", "codex", "grok"})
TARGET_POPULATION_POLICY = "protected-plus-root-plus-birth-bound-descendants-v2"
PROCESS_IDENTITY_FIELDS = frozenset(
    {
        "identity_version",
        "pid",
        "start",
        "kernel_birth_id",
        "command",
        "executable_path",
        "device",
        "inode",
    }
)
ALLOWED_MODES = frozenset({"read", "test", "mutate", "local_commit"})
MANDATORY_HARD_GATES = frozenset(
    {
        "merge",
        "push",
        "deploy",
        "force_push",
        "global_install",
        "external_send",
        "spend",
        "secrets",
        "account_change",
        "destructive_cleanup",
    }
)


@dataclass(frozen=True)
class Contract:
    schema_version: int
    objective: str
    campaign_authorization_id: str
    controller: str
    target: str
    requested_model: Optional[str]
    requested_effort: Optional[str]
    max_helpers: int
    run_id: Optional[str]
    nonce: Optional[str]
    proof_path_prefixes: Tuple[str, ...]
    task_profile: str
    harness_trust: str
    mutation_owner: str
    repo: Path
    branch: str
    allowed_modes: FrozenSet[str]
    terminal_criteria: Tuple[Dict[str, Any], ...]
    hard_gates: FrozenSet[str]
    supervisor_root: Optional[Path]
    candidate_root: Optional[Path]
    raw: Dict[str, Any]

    @classmethod
    def from_dict(cls, value: Dict[str, Any]) -> "Contract":
        allowed = {
            "schema_version",
            "objective",
            "campaign_authorization_id",
            "controller",
            "target",
            "requested_model",
            "requested_effort",
            "task_profile",
            "harness_trust",
            "mutation_owner",
            "repo",
            "branch",
            "max_helpers",
            "allowed_modes",
            "terminal_criteria",
            "hard_gates",
            "supervisor_root",
            "candidate_root",
            "run_id",
            "nonce",
            "proof_path_prefixes",
        }
        unknown = set(value) - allowed
        if unknown:
            raise ValidationError("unknown contract fields: %s" % ", ".join(sorted(unknown)))
        if value.get("schema_version") != 1:
            raise ValidationError("unsupported contract schema")
        objective = value.get("objective")
        if not isinstance(objective, str) or not objective.strip() or len(objective) > 1000:
            raise ValidationError("invalid contract objective")
        campaign = validate_identifier(
            value.get("campaign_authorization_id"), "campaign authorization id"
        )
        controller = validate_identifier(value.get("controller"), "controller")
        target = value.get("target")
        if target not in TARGETS:
            raise ValidationError("unsupported target")
        if controller == target:
            raise ValidationError("controller and target must be different identities")
        requested_model = value.get("requested_model")
        if requested_model is not None and (
            not isinstance(requested_model, str)
            or not requested_model.strip()
            or len(requested_model) > 200
            or any(char in requested_model for char in "\x00\n\r")
        ):
            raise ValidationError("invalid requested model")
        requested_effort = value.get("requested_effort")
        if requested_effort is not None and (
            not isinstance(requested_effort, str)
            or not requested_effort.strip()
            or len(requested_effort) > 80
            or any(char in requested_effort for char in "\x00\n\r")
        ):
            raise ValidationError("invalid requested effort")
        max_helpers = value.get("max_helpers", 0)
        if isinstance(max_helpers, bool) or not isinstance(max_helpers, int) or not 0 <= max_helpers <= 32:
            raise ValidationError("max_helpers must be an integer from zero to 32")
        run_id = value.get("run_id")
        nonce = value.get("nonce")
        if bool(run_id) != bool(nonce):
            raise ValidationError("run_id and nonce must appear together")
        if run_id:
            run_id = validate_identifier(run_id, "run id")
            nonce = validate_identifier(nonce, "nonce")
        proof_prefixes_raw = value.get("proof_path_prefixes", [])
        if not isinstance(proof_prefixes_raw, list) or len(proof_prefixes_raw) > 16:
            raise ValidationError("proof_path_prefixes must be a bounded list")
        proof_prefixes = []
        for prefix in proof_prefixes_raw:
            if (
                not isinstance(prefix, str)
                or not prefix
                or len(prefix) > 200
                or prefix.startswith("/")
                or "\\" in prefix
                or ".." in PurePosixPath(prefix).parts
                or not prefix.endswith("/")
            ):
                raise ValidationError("invalid proof path prefix")
            proof_prefixes.append(prefix)
        profile = validate_identifier(value.get("task_profile"), "task profile")
        if value.get("harness_trust") != "unrestricted_required":
            raise ValidationError("Puppet live contracts require unrestricted_required")
        mutation_owner = value.get("mutation_owner")
        if mutation_owner not in {"none", "target"}:
            raise ValidationError("unsupported mutation owner")
        repo = absolute_root(value.get("repo"), "repo")
        branch = validate_branch(value.get("branch"))
        modes_raw = value.get("allowed_modes")
        if not isinstance(modes_raw, list) or not modes_raw:
            raise ValidationError("allowed_modes must be a non-empty list")
        modes = frozenset(modes_raw)
        if len(modes) != len(modes_raw):
            raise ValidationError("allowed_modes contains duplicates")
        if not modes <= ALLOWED_MODES:
            raise ValidationError("contract contains an unsupported mode")
        if mutation_owner == "none" and modes & {"mutate", "local_commit"}:
            raise ValidationError("read-only ownership cannot authorize mutation")
        criteria = value.get("terminal_criteria")
        if not isinstance(criteria, list) or not criteria or len(criteria) > 32:
            raise ValidationError("terminal_criteria must be a bounded non-empty list")
        normalized_criteria = []
        criterion_ids = set()
        for criterion in criteria:
            if not isinstance(criterion, dict) or set(criterion) != {"id", "evidence"}:
                raise ValidationError("invalid terminal criterion")
            validate_identifier(criterion["id"], "terminal criterion id")
            validate_identifier(criterion["evidence"], "terminal criterion evidence")
            if criterion["id"] in criterion_ids:
                raise ValidationError("terminal criterion ids must be unique")
            criterion_ids.add(criterion["id"])
            normalized_criteria.append(dict(criterion))
        gates_raw = value.get("hard_gates")
        if not isinstance(gates_raw, list):
            raise ValidationError("hard_gates must be a list")
        gates = frozenset(gates_raw)
        if len(gates) != len(gates_raw):
            raise ValidationError("hard_gates contains duplicates")
        if not MANDATORY_HARD_GATES <= gates:
            missing = sorted(MANDATORY_HARD_GATES - gates)
            raise ValidationError("missing mandatory hard gates: %s" % ", ".join(missing))
        supervisor = value.get("supervisor_root")
        candidate = value.get("candidate_root")
        if bool(supervisor) != bool(candidate):
            raise ValidationError("supervisor_root and candidate_root must appear together")
        supervisor_root = None
        candidate_root = None
        if supervisor:
            supervisor_root = absolute_root(supervisor, "supervisor root")
            candidate_root = absolute_root(candidate, "candidate root")
            if paths_overlap(supervisor_root, candidate_root):
                raise ValidationError("supervisor and candidate roots overlap")
            if candidate_root != repo:
                raise ValidationError("candidate_root must match the contract repo")
        return cls(
            schema_version=1,
            objective=objective.strip(),
            campaign_authorization_id=campaign,
            controller=controller,
            target=target,
            requested_model=requested_model.strip() if requested_model else None,
            requested_effort=requested_effort.strip() if requested_effort else None,
            max_helpers=max_helpers,
            run_id=run_id,
            nonce=nonce,
            proof_path_prefixes=tuple(proof_prefixes),
            task_profile=profile,
            harness_trust="unrestricted_required",
            mutation_owner=mutation_owner,
            repo=repo,
            branch=branch,
            allowed_modes=modes,
            terminal_criteria=tuple(normalized_criteria),
            hard_gates=gates,
            supervisor_root=supervisor_root,
            candidate_root=candidate_root,
            raw=dict(value),
        )

    @classmethod
    def from_path(cls, path: Path) -> "Contract":
        return cls.from_dict(read_json(Path(path)))

    @property
    def fingerprint(self) -> str:
        return sha256_bytes(canonical_json_bytes(self.raw))


def assert_controller(contract: Contract, actor: str) -> None:
    if actor != contract.controller:
        raise ValidationError("only the recorded controller may perform this action")
