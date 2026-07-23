"""Deterministic stage-1 ledger, dedupe, barrier, and telemetry for Puppet's
hierarchical Antigravity teamwork plan.

Implements only what plans/puppet/antigravity-teamwork.md's "Staged adoption"
stage 1 requires: a deterministic ledger, dedupe, completion barrier, and
hostile-input safe transitions. No process is launched, no prompt or
transcript is stored, and no mutation lease is ever implicitly opened.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import re
from dataclasses import dataclass, field, replace
from typing import Any


class TeamworkError(RuntimeError):
    """A user-correctable ledger, cap, or transition error."""


# ---------------------------------------------------------------------------
# Identifiers, digests, and repository-relative paths.
# ---------------------------------------------------------------------------

ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
HEX_DIGEST_PATTERN = re.compile(r"^[0-9a-f]{16,64}$")
PATH_SEGMENT = r"[A-Za-z0-9][A-Za-z0-9._-]*"
REPO_RELATIVE_PATH_PATTERN = re.compile(rf"^{PATH_SEGMENT}(?:/{PATH_SEGMENT})*$")


def validate_id(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise TeamworkError(f"{label} must be a non-empty string")
    if not ID_PATTERN.fullmatch(value):
        raise TeamworkError(f"{label} must match {ID_PATTERN.pattern}: {value!r}")
    return value


def validate_hex_digest(value: Any, label: str) -> str:
    if not isinstance(value, str) or not HEX_DIGEST_PATTERN.fullmatch(value):
        raise TeamworkError(
            f"{label} must be a lower-case hex digest (16-64 chars): {value!r}"
        )
    return value


def validate_repo_relative_path(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise TeamworkError(f"{label} must be a non-empty string")
    if value.startswith("/"):
        raise TeamworkError(f"{label} must be repository-relative, not absolute: {value!r}")
    if any(segment == ".." for segment in value.split("/")):
        raise TeamworkError(f"{label} must not contain '..': {value!r}")
    if not REPO_RELATIVE_PATH_PATTERN.fullmatch(value):
        raise TeamworkError(f"{label} is not a valid repository-relative path: {value!r}")
    return value


def keyed_digest(domain: str, *parts: str, key_material: bytes) -> str:
    """Run-scoped, domain-separated keyed digest for low-entropy values."""
    hasher = hmac.new(key_material, digestmod=hashlib.sha256)
    hasher.update(domain.encode("utf-8"))
    for part in parts:
        hasher.update(b"\x00")
        hasher.update(part.encode("utf-8"))
    return hasher.hexdigest()


def _timestamp() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


# ---------------------------------------------------------------------------
# Enums.
# ---------------------------------------------------------------------------

EXECUTION_STATES = {
    "proposed",
    "admitted",
    "dispatched",
    "running",
    "result_ready",
    "blocked",
    "timed_out",
    "killed",
}
TERMINAL_EXECUTION_STATES = {"result_ready", "blocked", "timed_out", "killed"}
EXECUTION_TRANSITIONS: dict[str, set[str]] = {
    "proposed": {"admitted"},
    "admitted": {"dispatched"},
    "dispatched": {"running"},
    "running": {"result_ready", "blocked", "timed_out", "killed"},
}

ACCOUNTING_STATES = {"unaccounted", "leader_accounted", "parent_accounted"}
ACCOUNTING_TRANSITIONS: dict[str, set[str]] = {
    "unaccounted": {"leader_accounted"},
    "leader_accounted": {"parent_accounted"},
}

DECISION_STATES = {"pending", "accepted", "rejected", "deferred"}
DECISION_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"accepted", "rejected", "deferred"},
}

ALLOWED_MODES = {"observe", "suggest", "integrate"}
CREDIT_BUDGET_CLASSES = {"baseline"}
CLEANUP_STATES = {"pending", "clean", "reaper_handoff"}
ERROR_CLASSES = {
    "model_request_failed",
    "quota_exceeded",
    "timeout_budget_exceeded",
    "killed_by_controller",
    "validation_failed",
    "dependency_blocked",
    "unknown",
}

ALL_ENUM_VALUES: frozenset[str] = frozenset(
    EXECUTION_STATES
    | ACCOUNTING_STATES
    | DECISION_STATES
    | ALLOWED_MODES
    | CREDIT_BUDGET_CLASSES
    | CLEANUP_STATES
    | ERROR_CLASSES
)


def validate_error_class(value: Any) -> str:
    if value not in ERROR_CLASSES:
        raise TeamworkError(f"error_class must be one of {sorted(ERROR_CLASSES)}: {value!r}")
    return value


# ---------------------------------------------------------------------------
# Caps.
# ---------------------------------------------------------------------------

DEFAULT_MAX_HELPERS = 3
ALLOWED_MAX_HELPERS_OVERRIDES = frozenset({6, 20})


@dataclass(frozen=True)
class HelperCaps:
    max_helpers: int
    max_leaders: int
    max_leaves_per_leader: int
    max_total_helpers: int
    max_simultaneous_leaves: int


def make_helper_caps(
    *,
    max_leaders: int,
    max_leaves_per_leader: int,
    max_total_helpers: int,
    max_simultaneous_leaves: int,
    override_max_helpers: int | None = None,
) -> HelperCaps:
    """Build validated helper caps.

    max_helpers is the aggregate hard cap and defaults to 3. Raising it to 6
    (2x2) or 20 (4x4) requires the explicit `override_max_helpers` argument;
    any other value is refused. No subordinate cap may exceed max_helpers.
    """
    max_helpers = DEFAULT_MAX_HELPERS
    if override_max_helpers is not None:
        if override_max_helpers not in ALLOWED_MAX_HELPERS_OVERRIDES:
            raise TeamworkError(
                "override_max_helpers must be one of "
                f"{sorted(ALLOWED_MAX_HELPERS_OVERRIDES)}: {override_max_helpers!r}"
            )
        max_helpers = override_max_helpers
    for label, value in (
        ("max_leaders", max_leaders),
        ("max_leaves_per_leader", max_leaves_per_leader),
        ("max_total_helpers", max_total_helpers),
        ("max_simultaneous_leaves", max_simultaneous_leaves),
    ):
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise TeamworkError(f"{label} must be a positive integer")
        if value > max_helpers:
            raise TeamworkError(
                f"{label} ({value}) must not exceed max_helpers ({max_helpers})"
            )
    return HelperCaps(
        max_helpers=max_helpers,
        max_leaders=max_leaders,
        max_leaves_per_leader=max_leaves_per_leader,
        max_total_helpers=max_total_helpers,
        max_simultaneous_leaves=max_simultaneous_leaves,
    )


# ---------------------------------------------------------------------------
# Ledger record.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TeamworkState:
    """Three independent state dimensions. A failure never implies a result."""

    execution: str
    accounting: str
    decision: str


@dataclass
class LeafRecord:
    """One bounded ledger row for an admitted leader or leaf.

    Field order matches plans/puppet/antigravity-teamwork.md's "Leaf task
    ledger" code block exactly.
    """

    experiment_id: str
    capability_fingerprint: str
    task_id: str
    parent_task_id: str | None
    leader_role: str
    leaf_role: str | None
    exact_source_head: str
    scope_digest: str
    allowed_mode: str
    allowed_paths: tuple[str, ...]
    mutation_lease_id: str | None
    input_digest: str
    expected_artifact_schema: str
    timeout_budget: int
    credit_budget_class: str
    attempt: int
    physical_attempt_id: str
    dedupe_key: str
    retry_of: str | None
    state: TeamworkState
    result_ref: str | None = None
    result_digest: str | None = None
    relay_received_at: str | None = None
    error_class: str | None = None
    terminal_at: str | None = None
    cleanup_state: str = "pending"


# ---------------------------------------------------------------------------
# Ledger.
# ---------------------------------------------------------------------------


class TeamworkLedger:
    """Deterministic ledger for one experiment's helper hierarchy.

    Tracks admission caps, logical dedupe, retry limits, relay accounting,
    and the parent completion barrier. Owns no process, prompt, transcript,
    or credential state.
    """

    def __init__(
        self,
        *,
        experiment_id: str,
        capability_fingerprint: str,
        contract_hash: str,
        caps: HelperCaps,
    ) -> None:
        validate_id(experiment_id, "experiment_id")
        validate_id(capability_fingerprint, "capability_fingerprint")
        validate_hex_digest(contract_hash, "contract_hash")
        self.experiment_id = experiment_id
        self.capability_fingerprint = capability_fingerprint
        self.contract_hash = contract_hash
        self.caps = caps

        self._records: dict[str, LeafRecord] = {}
        self._task_ids: set[str] = set()
        self._task_to_physical: dict[str, list[str]] = {}
        self._by_dedupe: dict[str, list[str]] = {}
        self._accepted_physical: dict[str, str] = {}

        self._leader_roles: dict[str, str] = {}
        self._leaf_tasks_by_leader: dict[str, list[str]] = {}

        self._counted_task_ids: set[str] = set()
        self._counted_leader_task_ids: set[str] = set()
        self._counted_leaf_task_ids_by_leader: dict[str, set[str]] = {}

        self._active_leader_tasks: set[str] = set()
        self._active_leaf_tasks: set[str] = set()
        self.peak_active_helpers = 0

        self._mutation_lease_id: str | None = None

    # -- key material ------------------------------------------------------

    def _key_material(self) -> bytes:
        return hashlib.sha256(
            f"puppet-teamwork-run:{self.experiment_id}".encode("utf-8")
        ).digest()

    def _new_physical_attempt_id(self, task_id: str, attempt: int) -> str:
        return keyed_digest(
            "physical-attempt",
            self.experiment_id,
            task_id,
            str(attempt),
            key_material=self._key_material(),
        )

    def _dedupe_key(self, leader_role: str, scope_digest: str, exact_source_head: str) -> str:
        return keyed_digest(
            "dedupe",
            self.experiment_id,
            self.capability_fingerprint,
            leader_role,
            scope_digest,
            exact_source_head,
            self.contract_hash,
            key_material=self._key_material(),
        )

    # -- lookups -------------------------------------------------------------

    def _get(self, physical_attempt_id: str) -> LeafRecord:
        try:
            return self._records[physical_attempt_id]
        except KeyError as exc:
            raise TeamworkError(f"unknown physical_attempt_id: {physical_attempt_id}") from exc

    def latest_physical_attempt_id(self, task_id: str) -> str:
        try:
            return self._task_to_physical[task_id][-1]
        except KeyError as exc:
            raise TeamworkError(f"unknown task_id: {task_id}") from exc

    def records(self) -> list[LeafRecord]:
        return list(self._records.values())

    # -- proposal --------------------------------------------------------

    def propose_leader(
        self,
        *,
        task_id: str,
        leader_role: str,
        parent_task_id: str | None,
        exact_source_head: str,
        scope_digest: str,
        allowed_mode: str,
        allowed_paths: tuple[str, ...] | list[str],
        input_digest: str,
        expected_artifact_schema: str,
        timeout_budget: int,
        credit_budget_class: str,
        mutation_lease_id: str | None = None,
    ) -> LeafRecord:
        if leader_role in self._leader_roles:
            raise TeamworkError(f"leader_role already proposed: {leader_role}")
        record = self._propose(
            task_id=task_id,
            leader_role=leader_role,
            leaf_role=None,
            parent_task_id=parent_task_id,
            exact_source_head=exact_source_head,
            scope_digest=scope_digest,
            allowed_mode=allowed_mode,
            allowed_paths=allowed_paths,
            input_digest=input_digest,
            expected_artifact_schema=expected_artifact_schema,
            timeout_budget=timeout_budget,
            credit_budget_class=credit_budget_class,
            mutation_lease_id=mutation_lease_id,
        )
        self._leader_roles[leader_role] = task_id
        return record

    def propose_leaf(
        self,
        *,
        task_id: str,
        leader_role: str,
        leaf_role: str,
        parent_task_id: str | None,
        exact_source_head: str,
        scope_digest: str,
        allowed_mode: str,
        allowed_paths: tuple[str, ...] | list[str],
        input_digest: str,
        expected_artifact_schema: str,
        timeout_budget: int,
        credit_budget_class: str,
        mutation_lease_id: str | None = None,
    ) -> LeafRecord:
        if leader_role not in self._leader_roles:
            raise TeamworkError(f"unknown leader_role: {leader_role}")
        record = self._propose(
            task_id=task_id,
            leader_role=leader_role,
            leaf_role=leaf_role,
            parent_task_id=parent_task_id,
            exact_source_head=exact_source_head,
            scope_digest=scope_digest,
            allowed_mode=allowed_mode,
            allowed_paths=allowed_paths,
            input_digest=input_digest,
            expected_artifact_schema=expected_artifact_schema,
            timeout_budget=timeout_budget,
            credit_budget_class=credit_budget_class,
            mutation_lease_id=mutation_lease_id,
        )
        self._leaf_tasks_by_leader.setdefault(leader_role, []).append(task_id)
        return record

    def _propose(
        self,
        *,
        task_id: str,
        leader_role: str,
        leaf_role: str | None,
        parent_task_id: str | None,
        exact_source_head: str,
        scope_digest: str,
        allowed_mode: str,
        allowed_paths: tuple[str, ...] | list[str],
        input_digest: str,
        expected_artifact_schema: str,
        timeout_budget: int,
        credit_budget_class: str,
        mutation_lease_id: str | None,
    ) -> LeafRecord:
        validate_id(task_id, "task_id")
        if task_id in self._task_ids:
            raise TeamworkError(f"task_id already exists: {task_id}")
        validate_id(leader_role, "leader_role")
        if leaf_role is not None:
            validate_id(leaf_role, "leaf_role")
        if parent_task_id is not None:
            validate_id(parent_task_id, "parent_task_id")
        validate_id(exact_source_head, "exact_source_head")
        validate_hex_digest(scope_digest, "scope_digest")
        if allowed_mode not in ALLOWED_MODES:
            raise TeamworkError(f"allowed_mode must be one of {sorted(ALLOWED_MODES)}")
        paths = tuple(
            validate_repo_relative_path(item, "allowed_paths entry")
            for item in allowed_paths
        )
        validate_hex_digest(input_digest, "input_digest")
        validate_id(expected_artifact_schema, "expected_artifact_schema")
        if (
            not isinstance(timeout_budget, int)
            or isinstance(timeout_budget, bool)
            or timeout_budget <= 0
        ):
            raise TeamworkError("timeout_budget must be a positive integer")
        if credit_budget_class not in CREDIT_BUDGET_CLASSES:
            raise TeamworkError(
                f"credit_budget_class must be one of {sorted(CREDIT_BUDGET_CLASSES)}"
            )
        if mutation_lease_id is not None:
            validate_id(mutation_lease_id, "mutation_lease_id")

        dedupe_key = self._dedupe_key(leader_role, scope_digest, exact_source_head)
        physical_attempt_id = self._new_physical_attempt_id(task_id, 1)
        record = LeafRecord(
            experiment_id=self.experiment_id,
            capability_fingerprint=self.capability_fingerprint,
            task_id=task_id,
            parent_task_id=parent_task_id,
            leader_role=leader_role,
            leaf_role=leaf_role,
            exact_source_head=exact_source_head,
            scope_digest=scope_digest,
            allowed_mode=allowed_mode,
            allowed_paths=paths,
            mutation_lease_id=mutation_lease_id,
            input_digest=input_digest,
            expected_artifact_schema=expected_artifact_schema,
            timeout_budget=timeout_budget,
            credit_budget_class=credit_budget_class,
            attempt=1,
            physical_attempt_id=physical_attempt_id,
            dedupe_key=dedupe_key,
            retry_of=None,
            state=TeamworkState("proposed", "unaccounted", "pending"),
        )
        self._register(record)
        return record

    def _register(self, record: LeafRecord) -> None:
        self._task_ids.add(record.task_id)
        self._records[record.physical_attempt_id] = record
        self._task_to_physical.setdefault(record.task_id, []).append(
            record.physical_attempt_id
        )
        self._by_dedupe.setdefault(record.dedupe_key, []).append(
            record.physical_attempt_id
        )

    # -- admission caps ----------------------------------------------------

    def _apply_admission_caps(self, record: LeafRecord) -> None:
        task_id = record.task_id
        if task_id in self._counted_task_ids:
            return  # a retry reuses the logical slot counted at first admission
        is_leader = record.leaf_role is None
        if is_leader:
            if len(self._counted_leader_task_ids) + 1 > self.caps.max_leaders:
                raise TeamworkError("max_leaders exceeded")
        else:
            counted = self._counted_leaf_task_ids_by_leader.get(record.leader_role, set())
            if len(counted) + 1 > self.caps.max_leaves_per_leader:
                raise TeamworkError("max_leaves_per_leader exceeded")
        total = len(self._counted_task_ids)
        if total + 1 > self.caps.max_total_helpers or total + 1 > self.caps.max_helpers:
            raise TeamworkError("max_helpers exceeded")
        self._counted_task_ids.add(task_id)
        if is_leader:
            self._counted_leader_task_ids.add(task_id)
        else:
            self._counted_leaf_task_ids_by_leader.setdefault(
                record.leader_role, set()
            ).add(task_id)

    def _enter_running(self, record: LeafRecord) -> None:
        is_leader = record.leaf_role is None
        if is_leader:
            self._active_leader_tasks.add(record.task_id)
        else:
            if len(self._active_leaf_tasks) + 1 > self.caps.max_simultaneous_leaves:
                raise TeamworkError("max_simultaneous_leaves exceeded")
            self._active_leaf_tasks.add(record.task_id)
        active_total = len(self._active_leader_tasks) + len(self._active_leaf_tasks)
        if active_total > self.caps.max_helpers:
            raise TeamworkError("peak active helpers would exceed max_helpers")
        self.peak_active_helpers = max(self.peak_active_helpers, active_total)

    def _exit_active(self, record: LeafRecord) -> None:
        self._active_leader_tasks.discard(record.task_id)
        self._active_leaf_tasks.discard(record.task_id)

    # -- execution / accounting / decision transitions ----------------------

    def transition_execution(
        self,
        physical_attempt_id: str,
        new_state: str,
        *,
        result_ref: str | None = None,
        result_digest: str | None = None,
        error_class: str | None = None,
        at: str | None = None,
    ) -> LeafRecord:
        record = self._get(physical_attempt_id)
        current = record.state.execution
        allowed = EXECUTION_TRANSITIONS.get(current, set())
        if new_state not in allowed:
            raise TeamworkError(
                f"invalid execution transition for {physical_attempt_id}: "
                f"{current} -> {new_state}"
            )

        if new_state == "admitted":
            self._apply_admission_caps(record)
        elif new_state == "running":
            self._enter_running(record)

        if new_state == "result_ready":
            if error_class is not None:
                raise TeamworkError("result_ready must not carry an error_class")
            record.result_ref = (
                validate_repo_relative_path(result_ref, "result_ref")
                if result_ref is not None
                else None
            )
            record.result_digest = (
                validate_hex_digest(result_digest, "result_digest")
                if result_digest is not None
                else None
            )
            record.relay_received_at = at or _timestamp()
        elif new_state in TERMINAL_EXECUTION_STATES:
            if result_ref is not None or result_digest is not None:
                raise TeamworkError(
                    "failed execution must not carry a result_ref or result_digest"
                )
            record.result_ref = None
            record.result_digest = None
            if error_class is not None:
                record.error_class = validate_error_class(error_class)

        if new_state in TERMINAL_EXECUTION_STATES:
            record.terminal_at = at or _timestamp()
            self._exit_active(record)

        record.state = replace(record.state, execution=new_state)
        return record

    def transition_accounting(self, physical_attempt_id: str, new_state: str) -> LeafRecord:
        record = self._get(physical_attempt_id)
        current = record.state.accounting
        allowed = ACCOUNTING_TRANSITIONS.get(current, set())
        if new_state not in allowed:
            raise TeamworkError(
                f"invalid accounting transition for {physical_attempt_id}: "
                f"{current} -> {new_state}"
            )
        record.state = replace(record.state, accounting=new_state)
        return record

    def decide(self, physical_attempt_id: str, new_state: str) -> LeafRecord:
        record = self._get(physical_attempt_id)
        current = record.state.decision
        allowed = DECISION_TRANSITIONS.get(current, set())
        if new_state not in allowed:
            raise TeamworkError(
                f"invalid decision transition for {physical_attempt_id}: "
                f"{current} -> {new_state}"
            )
        if new_state == "accepted":
            if record.state.execution != "result_ready":
                raise TeamworkError(
                    "only a result_ready execution state may be accepted"
                )
            existing = self._accepted_physical.get(record.dedupe_key)
            if existing is not None and existing != record.physical_attempt_id:
                raise TeamworkError(
                    "a different physical attempt already supplied the accepted "
                    f"logical result for dedupe_key {record.dedupe_key}"
                )
            self._accepted_physical[record.dedupe_key] = record.physical_attempt_id
        record.state = replace(record.state, decision=new_state)
        return record

    def mark_cleanup(self, physical_attempt_id: str, state: str) -> LeafRecord:
        if state not in CLEANUP_STATES:
            raise TeamworkError(f"cleanup_state must be one of {sorted(CLEANUP_STATES)}")
        record = self._get(physical_attempt_id)
        record.cleanup_state = state
        return record

    # -- retry ---------------------------------------------------------------

    def retry_leaf(self, physical_attempt_id: str) -> LeafRecord:
        record = self._get(physical_attempt_id)
        if record.leaf_role is None:
            raise TeamworkError("retry_leaf called on a leader row; use retry_leader")
        return self._retry(record)

    def retry_leader(self, physical_attempt_id: str) -> LeafRecord:
        record = self._get(physical_attempt_id)
        if record.leaf_role is not None:
            raise TeamworkError("retry_leader called on a leaf row; use retry_leaf")
        for leaf_task_id in self._leaf_tasks_by_leader.get(record.leader_role, []):
            latest_id = self.latest_physical_attempt_id(leaf_task_id)
            latest = self._records[latest_id]
            if (
                latest.state.execution not in TERMINAL_EXECUTION_STATES
                or latest.state.accounting not in {"leader_accounted", "parent_accounted"}
            ):
                raise TeamworkError(
                    "a leader may only be retried after all of its leaves are "
                    "reconciled (terminal and at least leader-accounted)"
                )
        return self._retry(record)

    def _retry(self, original: LeafRecord) -> LeafRecord:
        if original.state.execution not in TERMINAL_EXECUTION_STATES:
            raise TeamworkError("only a terminal attempt may be retried")
        attempts = self._by_dedupe[original.dedupe_key]
        if len(attempts) >= 2:
            raise TeamworkError(
                f"at most one retry is permitted per leaf (dedupe_key {original.dedupe_key})"
            )
        new_attempt = original.attempt + 1
        new_physical_id = self._new_physical_attempt_id(original.task_id, new_attempt)
        new_record = replace(
            original,
            attempt=new_attempt,
            physical_attempt_id=new_physical_id,
            retry_of=original.physical_attempt_id,
            state=TeamworkState("proposed", "unaccounted", "pending"),
            result_ref=None,
            result_digest=None,
            relay_received_at=None,
            error_class=None,
            terminal_at=None,
            cleanup_state="pending",
        )
        self._register(new_record)
        return new_record

    # -- mutation lease --------------------------------------------------

    def open_mutation_lease(self, lease_id: str) -> None:
        validate_id(lease_id, "mutation_lease_id")
        if self._mutation_lease_id is not None:
            raise TeamworkError("a mutation lease is already open")
        self._mutation_lease_id = lease_id

    def close_mutation_lease(self) -> None:
        if self._mutation_lease_id is None:
            raise TeamworkError("no mutation lease is open")
        self._mutation_lease_id = None

    # -- completion barrier ------------------------------------------------

    def hierarchy_complete(
        self,
        *,
        fully_idle: bool,
        fixture_identity_stable: bool,
        source_identity_stable: bool,
    ) -> tuple[bool, list[str]]:
        """The AGY-root/controller completion barrier.

        Returns (True, []) only when every barrier condition in the plan's
        "Relay and parent completion barrier" section holds. Otherwise
        returns (False, [<unmet condition enum>, ...]).
        """
        unmet: list[str] = []

        for task_id in self._task_to_physical:
            latest = self._records[self.latest_physical_attempt_id(task_id)]
            if (
                latest.state.execution not in TERMINAL_EXECUTION_STATES
                or latest.state.accounting != "parent_accounted"
            ):
                unmet.append("rows_not_terminal_or_parent_accounted")
                break

        for task_id in self._task_to_physical:
            latest = self._records[self.latest_physical_attempt_id(task_id)]
            if latest.state.decision != "accepted":
                continue
            valid = latest.result_ref is not None and latest.result_digest is not None
            if valid:
                try:
                    validate_repo_relative_path(latest.result_ref, "result_ref")
                    validate_hex_digest(latest.result_digest, "result_digest")
                except TeamworkError:
                    valid = False
            if not valid:
                unmet.append("result_reference_missing_or_invalid")
                break

        active_total = len(self._active_leader_tasks) + len(self._active_leaf_tasks)
        if active_total != 0:
            unmet.append("active_counts_nonzero")

        if not fully_idle:
            unmet.append("not_fully_idle")

        if self._mutation_lease_id is not None:
            unmet.append("mutation_lease_open")

        if not fixture_identity_stable:
            unmet.append("fixture_identity_unstable")

        if not source_identity_stable:
            unmet.append("source_identity_unstable")

        for task_id in self._task_to_physical:
            latest = self._records[self.latest_physical_attempt_id(task_id)]
            if latest.cleanup_state != "clean":
                unmet.append("cleanup_incomplete")
                break

        return (len(unmet) == 0, unmet)


# ---------------------------------------------------------------------------
# Sanitized telemetry.
# ---------------------------------------------------------------------------


def _known_opaque_ids(ledger: TeamworkLedger) -> set[str]:
    known: set[str] = {ledger.experiment_id, ledger.capability_fingerprint, ledger.contract_hash}
    for record in ledger.records():
        known.add(record.task_id)
        known.add(record.physical_attempt_id)
        known.add(record.dedupe_key)
        known.add(record.leader_role)
        if record.leaf_role is not None:
            known.add(record.leaf_role)
        if record.parent_task_id is not None:
            known.add(record.parent_task_id)
        if record.retry_of is not None:
            known.add(record.retry_of)
        if record.mutation_lease_id is not None:
            known.add(record.mutation_lease_id)
    return known


def _assert_sanitized(value: Any, *, known_ids: set[str]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise TeamworkError(f"sanitized summary key must be a string: {key!r}")
            _assert_sanitized(item, known_ids=known_ids)
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            _assert_sanitized(item, known_ids=known_ids)
        return
    if isinstance(value, bool) or isinstance(value, int) or value is None:
        return
    if isinstance(value, str):
        if value in known_ids:
            return
        if value in ALL_ENUM_VALUES:
            return
        if HEX_DIGEST_PATTERN.fullmatch(value):
            return
        try:
            validate_repo_relative_path(value, "sanitized field")
        except TeamworkError:
            raise TeamworkError(
                "sanitized telemetry field carries a free-text or unbounded "
                f"payload: {value!r}"
            ) from None
        return
    raise TeamworkError(f"sanitized telemetry field has an unsupported type: {type(value)!r}")


def sanitized_summary(ledger: TeamworkLedger) -> dict[str, Any]:
    """Counts, enums, opaque IDs, and digests only. No prompts or transcripts."""
    known_ids = _known_opaque_ids(ledger)

    counts = {
        "created": 0,
        "admitted": 0,
        "running": 0,
        "terminal": 0,
        "leader_accounted": 0,
        "parent_accounted": 0,
        "accepted": 0,
        "cleaned": 0,
    }
    termination_reasons: dict[str, int] = {}
    results: list[dict[str, str]] = []

    for task_id in ledger._task_to_physical:  # sanitized projection of internal state
        latest = ledger._records[ledger.latest_physical_attempt_id(task_id)]
        counts["created"] += 1
        if latest.state.execution != "proposed":
            counts["admitted"] += 1
        if latest.state.execution == "running":
            counts["running"] += 1
        if latest.state.execution in TERMINAL_EXECUTION_STATES:
            counts["terminal"] += 1
            termination_reasons[latest.state.execution] = (
                termination_reasons.get(latest.state.execution, 0) + 1
            )
        if latest.state.accounting in {"leader_accounted", "parent_accounted"}:
            counts["leader_accounted"] += 1
        if latest.state.accounting == "parent_accounted":
            counts["parent_accounted"] += 1
        if latest.state.decision == "accepted":
            counts["accepted"] += 1
            if latest.result_ref is not None and latest.result_digest is not None:
                results.append(
                    {
                        "task_id": latest.task_id,
                        "result_ref": latest.result_ref,
                        "result_digest": latest.result_digest,
                    }
                )
        if latest.cleanup_state == "clean":
            counts["cleaned"] += 1

    summary: dict[str, Any] = {
        "experiment_id": ledger.experiment_id,
        "capability_fingerprint": ledger.capability_fingerprint,
        "counts": counts,
        "peak_active_helpers": ledger.peak_active_helpers,
        "termination_reasons": termination_reasons,
        "results": results,
    }
    _assert_sanitized(summary, known_ids=known_ids)
    return summary
