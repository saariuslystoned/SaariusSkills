from __future__ import annotations

import unittest

from puppet_lib import teamwork as tw


EXPERIMENT_ID = "exp-teamwork-2026-07-23"
CAPABILITY_FINGERPRINT = "agy-cli-1.1.5-isolated"
CONTRACT_HASH = "a" * 64
SOURCE_HEAD = "deadbeefsourcehead"


def digest(label: str) -> str:
    return tw.keyed_digest("test", label, key_material=b"fixture-key-material")


class BaseTeamworkTest(unittest.TestCase):
    def make_ledger(self, caps: tw.HelperCaps | None = None) -> tw.TeamworkLedger:
        if caps is None:
            caps = tw.make_helper_caps(
                max_leaders=1,
                max_leaves_per_leader=2,
                max_total_helpers=3,
                max_simultaneous_leaves=2,
            )
        return tw.TeamworkLedger(
            experiment_id=EXPERIMENT_ID,
            capability_fingerprint=CAPABILITY_FINGERPRINT,
            contract_hash=CONTRACT_HASH,
            caps=caps,
        )

    def propose_leader(
        self, ledger: tw.TeamworkLedger, *, task_id="leader-1", leader_role="recon"
    ) -> tw.LeafRecord:
        return ledger.propose_leader(
            task_id=task_id,
            leader_role=leader_role,
            parent_task_id="agy-root",
            exact_source_head=SOURCE_HEAD,
            scope_digest=digest(f"scope-{leader_role}"),
            allowed_mode="observe",
            allowed_paths=["skills/puppet"],
            input_digest=digest(f"input-{task_id}"),
            expected_artifact_schema="task-plan-v1",
            timeout_budget=600,
            credit_budget_class="baseline",
        )

    def propose_leaf(
        self,
        ledger: tw.TeamworkLedger,
        *,
        task_id="leaf-1",
        leader_role="recon",
        leaf_role="leaf-role-1",
        scope_digest=None,
    ) -> tw.LeafRecord:
        return ledger.propose_leaf(
            task_id=task_id,
            leader_role=leader_role,
            leaf_role=leaf_role,
            parent_task_id="leader-1",
            exact_source_head=SOURCE_HEAD,
            scope_digest=scope_digest or digest(f"scope-{leaf_role}"),
            allowed_mode="observe",
            allowed_paths=["skills/puppet/references"],
            input_digest=digest(f"input-{task_id}"),
            expected_artifact_schema="finding-v1",
            timeout_budget=300,
            credit_budget_class="baseline",
        )

    def run_to_running(self, ledger: tw.TeamworkLedger, physical_attempt_id: str) -> None:
        ledger.transition_execution(physical_attempt_id, "admitted")
        ledger.transition_execution(physical_attempt_id, "dispatched")
        ledger.transition_execution(physical_attempt_id, "running")

    def complete_result_ready(
        self,
        ledger: tw.TeamworkLedger,
        physical_attempt_id: str,
        *,
        result_ref="skills/puppet/proof/leaf.json",
        result_digest=None,
    ) -> None:
        ledger.transition_execution(
            physical_attempt_id,
            "result_ready",
            result_ref=result_ref,
            result_digest=result_digest or digest(f"result-{physical_attempt_id}"),
        )


# ---------------------------------------------------------------------------
# Execution / accounting / decision transitions.
# ---------------------------------------------------------------------------


class ExecutionTransitionTests(BaseTeamworkTest):
    def test_valid_execution_lifecycle_reaches_result_ready(self) -> None:
        ledger = self.make_ledger()
        leader = self.propose_leader(ledger)
        self.run_to_running(ledger, leader.physical_attempt_id)
        self.complete_result_ready(ledger, leader.physical_attempt_id)
        self.assertEqual(leader.state.execution, "result_ready")
        self.assertIsNotNone(leader.terminal_at)
        self.assertIsNotNone(leader.relay_received_at)

    def test_invalid_execution_transition_raises(self) -> None:
        ledger = self.make_ledger()
        leader = self.propose_leader(ledger)
        with self.assertRaisesRegex(tw.TeamworkError, "invalid execution transition"):
            ledger.transition_execution(leader.physical_attempt_id, "running")

    def test_cannot_transition_out_of_terminal_state(self) -> None:
        ledger = self.make_ledger()
        leader = self.propose_leader(ledger)
        self.run_to_running(ledger, leader.physical_attempt_id)
        self.complete_result_ready(ledger, leader.physical_attempt_id)
        with self.assertRaisesRegex(tw.TeamworkError, "invalid execution transition"):
            ledger.transition_execution(leader.physical_attempt_id, "admitted")

    def test_blocked_execution_is_terminal_and_error_classed(self) -> None:
        ledger = self.make_ledger()
        leader = self.propose_leader(ledger)
        self.run_to_running(ledger, leader.physical_attempt_id)
        ledger.transition_execution(
            leader.physical_attempt_id, "blocked", error_class="dependency_blocked"
        )
        self.assertEqual(leader.state.execution, "blocked")
        self.assertEqual(leader.error_class, "dependency_blocked")
        self.assertIsNone(leader.result_ref)
        self.assertIsNone(leader.result_digest)

    def test_unknown_error_class_is_rejected(self) -> None:
        ledger = self.make_ledger()
        leader = self.propose_leader(ledger)
        self.run_to_running(ledger, leader.physical_attempt_id)
        with self.assertRaisesRegex(tw.TeamworkError, "error_class must be one of"):
            ledger.transition_execution(
                leader.physical_attempt_id, "killed", error_class="the model got confused"
            )

    def test_result_ready_with_error_class_is_rejected(self) -> None:
        ledger = self.make_ledger()
        leader = self.propose_leader(ledger)
        self.run_to_running(ledger, leader.physical_attempt_id)
        with self.assertRaisesRegex(tw.TeamworkError, "must not carry an error_class"):
            ledger.transition_execution(
                leader.physical_attempt_id,
                "result_ready",
                result_ref="skills/puppet/proof/leaf.json",
                result_digest=digest("r"),
                error_class="unknown",
            )

    def test_failed_execution_with_result_ref_is_rejected(self) -> None:
        ledger = self.make_ledger()
        leader = self.propose_leader(ledger)
        self.run_to_running(ledger, leader.physical_attempt_id)
        with self.assertRaisesRegex(
            tw.TeamworkError, "failed execution must not carry a result_ref"
        ):
            ledger.transition_execution(
                leader.physical_attempt_id,
                "timed_out",
                result_ref="skills/puppet/proof/leaf.json",
            )

    def test_failed_execution_can_still_be_accounted(self) -> None:
        ledger = self.make_ledger()
        leader = self.propose_leader(ledger)
        self.run_to_running(ledger, leader.physical_attempt_id)
        ledger.transition_execution(
            leader.physical_attempt_id, "killed", error_class="killed_by_controller"
        )
        ledger.transition_accounting(leader.physical_attempt_id, "leader_accounted")
        ledger.transition_accounting(leader.physical_attempt_id, "parent_accounted")
        self.assertEqual(leader.state.accounting, "parent_accounted")
        self.assertIsNone(leader.result_ref)
        self.assertIsNone(leader.result_digest)


class AccountingTransitionTests(BaseTeamworkTest):
    def test_invalid_accounting_transition_raises(self) -> None:
        ledger = self.make_ledger()
        leader = self.propose_leader(ledger)
        with self.assertRaisesRegex(tw.TeamworkError, "invalid accounting transition"):
            ledger.transition_accounting(leader.physical_attempt_id, "parent_accounted")

    def test_accounting_cannot_go_backward(self) -> None:
        ledger = self.make_ledger()
        leader = self.propose_leader(ledger)
        ledger.transition_accounting(leader.physical_attempt_id, "leader_accounted")
        with self.assertRaisesRegex(tw.TeamworkError, "invalid accounting transition"):
            ledger.transition_accounting(leader.physical_attempt_id, "unaccounted")


class DecisionTransitionTests(BaseTeamworkTest):
    def test_accept_requires_result_ready(self) -> None:
        ledger = self.make_ledger()
        leader = self.propose_leader(ledger)
        with self.assertRaisesRegex(
            tw.TeamworkError, "only a result_ready execution state may be accepted"
        ):
            ledger.decide(leader.physical_attempt_id, "accepted")

    def test_accept_after_result_ready_succeeds(self) -> None:
        ledger = self.make_ledger()
        leader = self.propose_leader(ledger)
        self.run_to_running(ledger, leader.physical_attempt_id)
        self.complete_result_ready(ledger, leader.physical_attempt_id)
        ledger.decide(leader.physical_attempt_id, "accepted")
        self.assertEqual(leader.state.decision, "accepted")

    def test_reject_does_not_require_result_ready(self) -> None:
        ledger = self.make_ledger()
        leader = self.propose_leader(ledger)
        self.run_to_running(ledger, leader.physical_attempt_id)
        ledger.transition_execution(leader.physical_attempt_id, "blocked")
        ledger.decide(leader.physical_attempt_id, "rejected")
        self.assertEqual(leader.state.decision, "rejected")

    def test_invalid_decision_transition_raises(self) -> None:
        ledger = self.make_ledger()
        leader = self.propose_leader(ledger)
        self.run_to_running(ledger, leader.physical_attempt_id)
        self.complete_result_ready(ledger, leader.physical_attempt_id)
        ledger.decide(leader.physical_attempt_id, "accepted")
        with self.assertRaisesRegex(tw.TeamworkError, "invalid decision transition"):
            ledger.decide(leader.physical_attempt_id, "rejected")


# ---------------------------------------------------------------------------
# Dedupe, retries, and double-acceptance.
# ---------------------------------------------------------------------------


class DedupeAndRetryTests(BaseTeamworkTest):
    def test_dedupe_key_is_stable_across_retries_and_excludes_physical_attempt(self) -> None:
        ledger = self.make_ledger()
        self.propose_leader(ledger)
        leaf = self.propose_leaf(ledger, task_id="leaf-1")
        self.run_to_running(ledger, leaf.physical_attempt_id)
        ledger.transition_execution(leaf.physical_attempt_id, "timed_out")
        ledger.transition_accounting(leaf.physical_attempt_id, "leader_accounted")
        retried = ledger.retry_leaf(leaf.physical_attempt_id)
        self.assertEqual(retried.dedupe_key, leaf.dedupe_key)
        self.assertNotEqual(retried.physical_attempt_id, leaf.physical_attempt_id)
        self.assertEqual(retried.attempt, 2)
        self.assertEqual(retried.retry_of, leaf.physical_attempt_id)

    def test_dedupe_key_is_deterministic_for_identical_inputs(self) -> None:
        ledger_a = self.make_ledger()
        ledger_b = self.make_ledger()
        self.propose_leader(ledger_a)
        self.propose_leader(ledger_b)
        leaf_a = self.propose_leaf(ledger_a, task_id="leaf-1")
        leaf_b = self.propose_leaf(ledger_b, task_id="leaf-1")
        self.assertEqual(leaf_a.dedupe_key, leaf_b.dedupe_key)
        self.assertEqual(leaf_a.physical_attempt_id, leaf_b.physical_attempt_id)

    def test_dedupe_key_differs_by_leader_scope_source_or_leader_role(self) -> None:
        ledger = self.make_ledger(
            caps=tw.make_helper_caps(
                max_leaders=1,
                max_leaves_per_leader=2,
                max_total_helpers=3,
                max_simultaneous_leaves=2,
            )
        )
        self.propose_leader(ledger)
        leaf_1 = self.propose_leaf(ledger, task_id="leaf-1", leaf_role="role-a")
        leaf_2 = self.propose_leaf(ledger, task_id="leaf-2", leaf_role="role-b")
        self.assertNotEqual(leaf_1.dedupe_key, leaf_2.dedupe_key)

    def test_second_retry_is_refused(self) -> None:
        ledger = self.make_ledger()
        self.propose_leader(ledger)
        leaf = self.propose_leaf(ledger, task_id="leaf-1")
        self.run_to_running(ledger, leaf.physical_attempt_id)
        ledger.transition_execution(leaf.physical_attempt_id, "timed_out")
        retried = ledger.retry_leaf(leaf.physical_attempt_id)
        self.run_to_running(ledger, retried.physical_attempt_id)
        ledger.transition_execution(retried.physical_attempt_id, "timed_out")
        with self.assertRaisesRegex(tw.TeamworkError, "at most one retry"):
            ledger.retry_leaf(retried.physical_attempt_id)

    def test_retry_before_terminal_is_refused(self) -> None:
        ledger = self.make_ledger()
        self.propose_leader(ledger)
        leaf = self.propose_leaf(ledger, task_id="leaf-1")
        self.run_to_running(ledger, leaf.physical_attempt_id)
        with self.assertRaisesRegex(tw.TeamworkError, "only a terminal attempt"):
            ledger.retry_leaf(leaf.physical_attempt_id)

    def test_retry_leaf_on_leader_row_is_refused(self) -> None:
        ledger = self.make_ledger()
        leader = self.propose_leader(ledger)
        self.run_to_running(ledger, leader.physical_attempt_id)
        ledger.transition_execution(leader.physical_attempt_id, "blocked")
        with self.assertRaisesRegex(tw.TeamworkError, "retry_leaf called on a leader row"):
            ledger.retry_leaf(leader.physical_attempt_id)

    def test_double_acceptance_across_physical_attempts_is_refused(self) -> None:
        # Two distinct leaves that happen to share leader, scope, source head,
        # and contract hash collapse onto the same logical dedupe key even
        # though they are two independent physical attempts. Only one may
        # ever supply the accepted logical result.
        ledger = self.make_ledger(
            caps=tw.make_helper_caps(
                max_leaders=1,
                max_leaves_per_leader=2,
                max_total_helpers=3,
                max_simultaneous_leaves=2,
            )
        )
        self.propose_leader(ledger)
        shared_scope = digest("shared-scope")
        leaf_1 = self.propose_leaf(
            ledger, task_id="leaf-1", leaf_role="role-a", scope_digest=shared_scope
        )
        leaf_2 = self.propose_leaf(
            ledger, task_id="leaf-2", leaf_role="role-b", scope_digest=shared_scope
        )
        self.assertEqual(leaf_1.dedupe_key, leaf_2.dedupe_key)
        self.assertNotEqual(leaf_1.physical_attempt_id, leaf_2.physical_attempt_id)

        self.run_to_running(ledger, leaf_1.physical_attempt_id)
        self.complete_result_ready(ledger, leaf_1.physical_attempt_id)
        ledger.decide(leaf_1.physical_attempt_id, "accepted")

        self.run_to_running(ledger, leaf_2.physical_attempt_id)
        self.complete_result_ready(ledger, leaf_2.physical_attempt_id)
        with self.assertRaisesRegex(
            tw.TeamworkError, "already supplied the accepted logical result"
        ):
            ledger.decide(leaf_2.physical_attempt_id, "accepted")

    def test_leader_retry_blocked_until_leaf_terminal_and_accounted(self) -> None:
        ledger = self.make_ledger()
        leader = self.propose_leader(ledger)
        leaf = self.propose_leaf(ledger, task_id="leaf-1")
        self.run_to_running(ledger, leader.physical_attempt_id)
        ledger.transition_execution(leader.physical_attempt_id, "blocked")
        with self.assertRaisesRegex(tw.TeamworkError, "leader may only be retried"):
            ledger.retry_leader(leader.physical_attempt_id)
        self.run_to_running(ledger, leaf.physical_attempt_id)
        ledger.transition_execution(leaf.physical_attempt_id, "timed_out")
        with self.assertRaisesRegex(tw.TeamworkError, "leader may only be retried"):
            ledger.retry_leader(leader.physical_attempt_id)
        ledger.transition_accounting(leaf.physical_attempt_id, "leader_accounted")
        retried_leader = ledger.retry_leader(leader.physical_attempt_id)
        self.assertEqual(retried_leader.dedupe_key, leader.dedupe_key)

    def test_no_hierarchy_wide_auto_retry_api(self) -> None:
        self.assertFalse(hasattr(tw.TeamworkLedger, "retry_hierarchy"))
        self.assertFalse(hasattr(tw.TeamworkLedger, "retry_all"))


# ---------------------------------------------------------------------------
# Caps.
# ---------------------------------------------------------------------------


class CapsTests(unittest.TestCase):
    def test_default_max_helpers_is_three(self) -> None:
        caps = tw.make_helper_caps(
            max_leaders=1,
            max_leaves_per_leader=2,
            max_total_helpers=3,
            max_simultaneous_leaves=2,
        )
        self.assertEqual(caps.max_helpers, 3)

    def test_override_must_be_named_and_from_allowed_set(self) -> None:
        with self.assertRaisesRegex(tw.TeamworkError, "override_max_helpers must be one of"):
            tw.make_helper_caps(
                max_leaders=2,
                max_leaves_per_leader=2,
                max_total_helpers=4,
                max_simultaneous_leaves=4,
                override_max_helpers=4,
            )

    def test_override_six_and_twenty_are_accepted(self) -> None:
        caps_2x2 = tw.make_helper_caps(
            max_leaders=2,
            max_leaves_per_leader=2,
            max_total_helpers=6,
            max_simultaneous_leaves=4,
            override_max_helpers=6,
        )
        self.assertEqual(caps_2x2.max_helpers, 6)
        caps_4x4 = tw.make_helper_caps(
            max_leaders=4,
            max_leaves_per_leader=4,
            max_total_helpers=20,
            max_simultaneous_leaves=16,
            override_max_helpers=20,
        )
        self.assertEqual(caps_4x4.max_helpers, 20)

    def test_subordinate_cap_exceeding_max_helpers_is_rejected(self) -> None:
        with self.assertRaisesRegex(tw.TeamworkError, "must not exceed max_helpers"):
            tw.make_helper_caps(
                max_leaders=4,
                max_leaves_per_leader=2,
                max_total_helpers=3,
                max_simultaneous_leaves=2,
            )

    def test_max_leaders_overflow_raises_on_admit(self) -> None:
        caps = tw.make_helper_caps(
            max_leaders=1,
            max_leaves_per_leader=1,
            max_total_helpers=2,
            max_simultaneous_leaves=1,
        )
        ledger = tw.TeamworkLedger(
            experiment_id=EXPERIMENT_ID,
            capability_fingerprint=CAPABILITY_FINGERPRINT,
            contract_hash=CONTRACT_HASH,
            caps=caps,
        )
        first = ledger.propose_leader(
            task_id="leader-1",
            leader_role="recon",
            parent_task_id="agy-root",
            exact_source_head=SOURCE_HEAD,
            scope_digest=digest("scope-recon"),
            allowed_mode="observe",
            allowed_paths=["skills/puppet"],
            input_digest=digest("input-leader-1"),
            expected_artifact_schema="task-plan-v1",
            timeout_budget=600,
            credit_budget_class="baseline",
        )
        ledger.transition_execution(first.physical_attempt_id, "admitted")
        second = ledger.propose_leader(
            task_id="leader-2",
            leader_role="verification",
            parent_task_id="agy-root",
            exact_source_head=SOURCE_HEAD,
            scope_digest=digest("scope-verification"),
            allowed_mode="observe",
            allowed_paths=["skills/puppet"],
            input_digest=digest("input-leader-2"),
            expected_artifact_schema="task-plan-v1",
            timeout_budget=600,
            credit_budget_class="baseline",
        )
        with self.assertRaisesRegex(tw.TeamworkError, "max_leaders exceeded"):
            ledger.transition_execution(second.physical_attempt_id, "admitted")

    def test_max_leaves_per_leader_overflow_raises_on_admit(self) -> None:
        caps = tw.make_helper_caps(
            max_leaders=1,
            max_leaves_per_leader=1,
            max_total_helpers=2,
            max_simultaneous_leaves=1,
        )
        ledger = tw.TeamworkLedger(
            experiment_id=EXPERIMENT_ID,
            capability_fingerprint=CAPABILITY_FINGERPRINT,
            contract_hash=CONTRACT_HASH,
            caps=caps,
        )
        ledger.propose_leader(
            task_id="leader-1",
            leader_role="recon",
            parent_task_id="agy-root",
            exact_source_head=SOURCE_HEAD,
            scope_digest=digest("scope-recon"),
            allowed_mode="observe",
            allowed_paths=["skills/puppet"],
            input_digest=digest("input-leader-1"),
            expected_artifact_schema="task-plan-v1",
            timeout_budget=600,
            credit_budget_class="baseline",
        )
        first_leaf = ledger.propose_leaf(
            task_id="leaf-1",
            leader_role="recon",
            leaf_role="role-a",
            parent_task_id="leader-1",
            exact_source_head=SOURCE_HEAD,
            scope_digest=digest("scope-role-a"),
            allowed_mode="observe",
            allowed_paths=["skills/puppet"],
            input_digest=digest("input-leaf-1"),
            expected_artifact_schema="finding-v1",
            timeout_budget=300,
            credit_budget_class="baseline",
        )
        ledger.transition_execution(first_leaf.physical_attempt_id, "admitted")
        second_leaf = ledger.propose_leaf(
            task_id="leaf-2",
            leader_role="recon",
            leaf_role="role-b",
            parent_task_id="leader-1",
            exact_source_head=SOURCE_HEAD,
            scope_digest=digest("scope-role-b"),
            allowed_mode="observe",
            allowed_paths=["skills/puppet"],
            input_digest=digest("input-leaf-2"),
            expected_artifact_schema="finding-v1",
            timeout_budget=300,
            credit_budget_class="baseline",
        )
        with self.assertRaisesRegex(tw.TeamworkError, "max_leaves_per_leader exceeded"):
            ledger.transition_execution(second_leaf.physical_attempt_id, "admitted")

    def test_max_helpers_hard_cap_overflow_raises_on_admit(self) -> None:
        caps = tw.make_helper_caps(
            max_leaders=1,
            max_leaves_per_leader=3,
            max_total_helpers=3,
            max_simultaneous_leaves=3,
        )
        ledger = tw.TeamworkLedger(
            experiment_id=EXPERIMENT_ID,
            capability_fingerprint=CAPABILITY_FINGERPRINT,
            contract_hash=CONTRACT_HASH,
            caps=caps,
        )
        leader = ledger.propose_leader(
            task_id="leader-1",
            leader_role="recon",
            parent_task_id="agy-root",
            exact_source_head=SOURCE_HEAD,
            scope_digest=digest("scope-recon"),
            allowed_mode="observe",
            allowed_paths=["skills/puppet"],
            input_digest=digest("input-leader-1"),
            expected_artifact_schema="task-plan-v1",
            timeout_budget=600,
            credit_budget_class="baseline",
        )
        ledger.transition_execution(leader.physical_attempt_id, "admitted")
        for index in range(2):
            leaf = ledger.propose_leaf(
                task_id=f"leaf-{index}",
                leader_role="recon",
                leaf_role=f"role-{index}",
                parent_task_id="leader-1",
                exact_source_head=SOURCE_HEAD,
                scope_digest=digest(f"scope-role-{index}"),
                allowed_mode="observe",
                allowed_paths=["skills/puppet"],
                input_digest=digest(f"input-leaf-{index}"),
                expected_artifact_schema="finding-v1",
                timeout_budget=300,
                credit_budget_class="baseline",
            )
            ledger.transition_execution(leaf.physical_attempt_id, "admitted")
        overflow_leaf = ledger.propose_leaf(
            task_id="leaf-overflow",
            leader_role="recon",
            leaf_role="role-overflow",
            parent_task_id="leader-1",
            exact_source_head=SOURCE_HEAD,
            scope_digest=digest("scope-role-overflow"),
            allowed_mode="observe",
            allowed_paths=["skills/puppet"],
            input_digest=digest("input-leaf-overflow"),
            expected_artifact_schema="finding-v1",
            timeout_budget=300,
            credit_budget_class="baseline",
        )
        with self.assertRaisesRegex(tw.TeamworkError, "max_helpers exceeded"):
            ledger.transition_execution(overflow_leaf.physical_attempt_id, "admitted")

    def test_max_simultaneous_leaves_overflow_raises_on_running(self) -> None:
        caps = tw.make_helper_caps(
            max_leaders=1,
            max_leaves_per_leader=2,
            max_total_helpers=3,
            max_simultaneous_leaves=1,
        )
        ledger = tw.TeamworkLedger(
            experiment_id=EXPERIMENT_ID,
            capability_fingerprint=CAPABILITY_FINGERPRINT,
            contract_hash=CONTRACT_HASH,
            caps=caps,
        )
        ledger.propose_leader(
            task_id="leader-1",
            leader_role="recon",
            parent_task_id="agy-root",
            exact_source_head=SOURCE_HEAD,
            scope_digest=digest("scope-recon"),
            allowed_mode="observe",
            allowed_paths=["skills/puppet"],
            input_digest=digest("input-leader-1"),
            expected_artifact_schema="task-plan-v1",
            timeout_budget=600,
            credit_budget_class="baseline",
        )
        leaf_a = ledger.propose_leaf(
            task_id="leaf-a",
            leader_role="recon",
            leaf_role="role-a",
            parent_task_id="leader-1",
            exact_source_head=SOURCE_HEAD,
            scope_digest=digest("scope-role-a"),
            allowed_mode="observe",
            allowed_paths=["skills/puppet"],
            input_digest=digest("input-leaf-a"),
            expected_artifact_schema="finding-v1",
            timeout_budget=300,
            credit_budget_class="baseline",
        )
        leaf_b = ledger.propose_leaf(
            task_id="leaf-b",
            leader_role="recon",
            leaf_role="role-b",
            parent_task_id="leader-1",
            exact_source_head=SOURCE_HEAD,
            scope_digest=digest("scope-role-b"),
            allowed_mode="observe",
            allowed_paths=["skills/puppet"],
            input_digest=digest("input-leaf-b"),
            expected_artifact_schema="finding-v1",
            timeout_budget=300,
            credit_budget_class="baseline",
        )
        ledger.transition_execution(leaf_a.physical_attempt_id, "admitted")
        ledger.transition_execution(leaf_a.physical_attempt_id, "dispatched")
        ledger.transition_execution(leaf_a.physical_attempt_id, "running")
        ledger.transition_execution(leaf_b.physical_attempt_id, "admitted")
        ledger.transition_execution(leaf_b.physical_attempt_id, "dispatched")
        with self.assertRaisesRegex(tw.TeamworkError, "max_simultaneous_leaves exceeded"):
            ledger.transition_execution(leaf_b.physical_attempt_id, "running")


# ---------------------------------------------------------------------------
# Path and digest validation.
# ---------------------------------------------------------------------------


class PathValidationTests(unittest.TestCase):
    def test_absolute_path_is_rejected(self) -> None:
        with self.assertRaisesRegex(tw.TeamworkError, "not absolute"):
            tw.validate_repo_relative_path("/etc/passwd", "path")

    def test_traversal_path_is_rejected(self) -> None:
        with self.assertRaisesRegex(tw.TeamworkError, "must not contain"):
            tw.validate_repo_relative_path("skills/../../../etc/passwd", "path")

    def test_valid_relative_path_is_accepted(self) -> None:
        self.assertEqual(
            tw.validate_repo_relative_path("skills/puppet/references/x.md", "path"),
            "skills/puppet/references/x.md",
        )

    def test_hex_digest_validation(self) -> None:
        self.assertEqual(tw.validate_hex_digest("a" * 40, "d"), "a" * 40)
        with self.assertRaises(tw.TeamworkError):
            tw.validate_hex_digest("not-hex", "d")
        with self.assertRaises(tw.TeamworkError):
            tw.validate_hex_digest("ABCDEF" * 4, "d")


# ---------------------------------------------------------------------------
# Completion barrier.
# ---------------------------------------------------------------------------


class BarrierTests(BaseTeamworkTest):
    def _complete_leader_and_leaf(self, ledger: tw.TeamworkLedger) -> tuple[str, str]:
        leader = self.propose_leader(ledger)
        leaf = self.propose_leaf(ledger, task_id="leaf-1")
        self.run_to_running(ledger, leaf.physical_attempt_id)
        self.complete_result_ready(ledger, leaf.physical_attempt_id)
        ledger.decide(leaf.physical_attempt_id, "accepted")
        ledger.transition_accounting(leaf.physical_attempt_id, "leader_accounted")
        ledger.transition_accounting(leaf.physical_attempt_id, "parent_accounted")
        ledger.mark_cleanup(leaf.physical_attempt_id, "clean")

        self.run_to_running(ledger, leader.physical_attempt_id)
        self.complete_result_ready(ledger, leader.physical_attempt_id)
        ledger.decide(leader.physical_attempt_id, "accepted")
        ledger.transition_accounting(leader.physical_attempt_id, "leader_accounted")
        ledger.transition_accounting(leader.physical_attempt_id, "parent_accounted")
        ledger.mark_cleanup(leader.physical_attempt_id, "clean")
        return leader.physical_attempt_id, leaf.physical_attempt_id

    def test_barrier_true_when_every_condition_holds(self) -> None:
        ledger = self.make_ledger()
        self._complete_leader_and_leaf(ledger)
        ok, unmet = ledger.hierarchy_complete(
            fully_idle=True,
            fixture_identity_stable=True,
            source_identity_stable=True,
        )
        self.assertTrue(ok)
        self.assertEqual(unmet, [])

    def test_barrier_reports_rows_not_terminal(self) -> None:
        ledger = self.make_ledger()
        self.propose_leader(ledger)
        ok, unmet = ledger.hierarchy_complete(
            fully_idle=True,
            fixture_identity_stable=True,
            source_identity_stable=True,
        )
        self.assertFalse(ok)
        self.assertIn("rows_not_terminal_or_parent_accounted", unmet)

    def test_barrier_reports_missing_result_reference(self) -> None:
        ledger = self.make_ledger()
        leader, leaf = self._complete_leader_and_leaf(ledger)
        # Force an accepted row to lose its result reference without going
        # through the guarded transition API, simulating ledger corruption.
        ledger._records[leaf].result_ref = None
        ok, unmet = ledger.hierarchy_complete(
            fully_idle=True,
            fixture_identity_stable=True,
            source_identity_stable=True,
        )
        self.assertFalse(ok)
        self.assertIn("result_reference_missing_or_invalid", unmet)

    def test_barrier_reports_active_counts_nonzero(self) -> None:
        ledger = self.make_ledger()
        leader = self.propose_leader(ledger)
        self.run_to_running(ledger, leader.physical_attempt_id)
        ok, unmet = ledger.hierarchy_complete(
            fully_idle=True,
            fixture_identity_stable=True,
            source_identity_stable=True,
        )
        self.assertFalse(ok)
        self.assertIn("active_counts_nonzero", unmet)

    def test_barrier_reports_not_fully_idle(self) -> None:
        ledger = self.make_ledger()
        self._complete_leader_and_leaf(ledger)
        ok, unmet = ledger.hierarchy_complete(
            fully_idle=False,
            fixture_identity_stable=True,
            source_identity_stable=True,
        )
        self.assertFalse(ok)
        self.assertIn("not_fully_idle", unmet)

    def test_barrier_reports_open_mutation_lease(self) -> None:
        ledger = self.make_ledger()
        self._complete_leader_and_leaf(ledger)
        ledger.open_mutation_lease("lease-1")
        ok, unmet = ledger.hierarchy_complete(
            fully_idle=True,
            fixture_identity_stable=True,
            source_identity_stable=True,
        )
        self.assertFalse(ok)
        self.assertIn("mutation_lease_open", unmet)
        ledger.close_mutation_lease()
        ok, unmet = ledger.hierarchy_complete(
            fully_idle=True,
            fixture_identity_stable=True,
            source_identity_stable=True,
        )
        self.assertTrue(ok)

    def test_barrier_reports_unstable_fixture_identity(self) -> None:
        ledger = self.make_ledger()
        self._complete_leader_and_leaf(ledger)
        ok, unmet = ledger.hierarchy_complete(
            fully_idle=True,
            fixture_identity_stable=False,
            source_identity_stable=True,
        )
        self.assertFalse(ok)
        self.assertIn("fixture_identity_unstable", unmet)

    def test_barrier_reports_unstable_source_identity(self) -> None:
        ledger = self.make_ledger()
        self._complete_leader_and_leaf(ledger)
        ok, unmet = ledger.hierarchy_complete(
            fully_idle=True,
            fixture_identity_stable=True,
            source_identity_stable=False,
        )
        self.assertFalse(ok)
        self.assertIn("source_identity_unstable", unmet)

    def test_barrier_reports_cleanup_incomplete(self) -> None:
        ledger = self.make_ledger()
        leader, leaf = self._complete_leader_and_leaf(ledger)
        ledger._records[leaf].cleanup_state = "reaper_handoff"
        ok, unmet = ledger.hierarchy_complete(
            fully_idle=True,
            fixture_identity_stable=True,
            source_identity_stable=True,
        )
        self.assertFalse(ok)
        self.assertIn("cleanup_incomplete", unmet)


# ---------------------------------------------------------------------------
# Sanitized telemetry.
# ---------------------------------------------------------------------------


class SanitizedTelemetryTests(BaseTeamworkTest):
    def test_summary_contains_only_counts_enums_ids_and_digests(self) -> None:
        ledger = self.make_ledger()
        leader = self.propose_leader(ledger)
        leaf = self.propose_leaf(ledger, task_id="leaf-1")
        self.run_to_running(ledger, leaf.physical_attempt_id)
        self.complete_result_ready(ledger, leaf.physical_attempt_id)
        ledger.decide(leaf.physical_attempt_id, "accepted")
        summary = tw.sanitized_summary(ledger)
        self.assertEqual(summary["experiment_id"], EXPERIMENT_ID)
        self.assertEqual(summary["counts"]["created"], 2)
        self.assertEqual(summary["counts"]["accepted"], 1)
        self.assertEqual(summary["results"][0]["task_id"], "leaf-1")

    def test_summary_rejects_injected_free_text_payload(self) -> None:
        ledger = self.make_ledger()
        self.propose_leader(ledger)
        summary = tw.sanitized_summary(ledger)
        summary["counts"]["note"] = "the operator said this leaf looked slow today"
        with self.assertRaisesRegex(tw.TeamworkError, "free-text or unbounded"):
            tw._assert_sanitized(summary, known_ids=tw._known_opaque_ids(ledger))

    def test_assert_sanitized_rejects_raw_prompt_text_directly(self) -> None:
        with self.assertRaisesRegex(tw.TeamworkError, "free-text or unbounded"):
            tw._assert_sanitized(
                {"transcript": "please write a haiku about the weather"}, known_ids=set()
            )

    def test_assert_sanitized_rejects_float_payload(self) -> None:
        with self.assertRaisesRegex(tw.TeamworkError, "unsupported type"):
            tw._assert_sanitized({"score": 0.5}, known_ids=set())


# ---------------------------------------------------------------------------
# Full lifecycle: 2x2 (override 6) and 4x4 (override 20).
# ---------------------------------------------------------------------------


class LifecycleTests(unittest.TestCase):
    def _run_hierarchy(self, *, leaders: int, leaves_per_leader: int, override: int) -> tw.TeamworkLedger:
        total = leaders * leaves_per_leader + leaders
        caps = tw.make_helper_caps(
            max_leaders=leaders,
            max_leaves_per_leader=leaves_per_leader,
            max_total_helpers=total,
            max_simultaneous_leaves=leaders * leaves_per_leader,
            override_max_helpers=override,
        )
        ledger = tw.TeamworkLedger(
            experiment_id=EXPERIMENT_ID,
            capability_fingerprint=CAPABILITY_FINGERPRINT,
            contract_hash=CONTRACT_HASH,
            caps=caps,
        )

        leaf_ids: list[str] = []
        for leader_index in range(leaders):
            leader_role = f"leader-{leader_index}"
            leader_task_id = f"leader-task-{leader_index}"
            leader = ledger.propose_leader(
                task_id=leader_task_id,
                leader_role=leader_role,
                parent_task_id="agy-root",
                exact_source_head=SOURCE_HEAD,
                scope_digest=digest(f"scope-{leader_role}"),
                allowed_mode="observe",
                allowed_paths=["skills/puppet"],
                input_digest=digest(f"input-{leader_task_id}"),
                expected_artifact_schema="task-plan-v1",
                timeout_budget=600,
                credit_budget_class="baseline",
            )
            ledger.transition_execution(leader.physical_attempt_id, "admitted")

            for leaf_index in range(leaves_per_leader):
                leaf_task_id = f"leaf-task-{leader_index}-{leaf_index}"
                leaf_role = f"leaf-role-{leader_index}-{leaf_index}"
                leaf = ledger.propose_leaf(
                    task_id=leaf_task_id,
                    leader_role=leader_role,
                    leaf_role=leaf_role,
                    parent_task_id=leader_task_id,
                    exact_source_head=SOURCE_HEAD,
                    scope_digest=digest(f"scope-{leaf_role}"),
                    allowed_mode="observe",
                    allowed_paths=["skills/puppet/references"],
                    input_digest=digest(f"input-{leaf_task_id}"),
                    expected_artifact_schema="finding-v1",
                    timeout_budget=300,
                    credit_budget_class="baseline",
                )
                ledger.transition_execution(leaf.physical_attempt_id, "admitted")
                ledger.transition_execution(leaf.physical_attempt_id, "dispatched")
                ledger.transition_execution(leaf.physical_attempt_id, "running")
                ledger.transition_execution(
                    leaf.physical_attempt_id,
                    "result_ready",
                    result_ref=f"skills/puppet/proof/{leaf_task_id}.json",
                    result_digest=digest(f"result-{leaf_task_id}"),
                )
                ledger.decide(leaf.physical_attempt_id, "accepted")
                ledger.transition_accounting(leaf.physical_attempt_id, "leader_accounted")
                ledger.transition_accounting(leaf.physical_attempt_id, "parent_accounted")
                ledger.mark_cleanup(leaf.physical_attempt_id, "clean")
                leaf_ids.append(leaf.physical_attempt_id)

            ledger.transition_execution(leader.physical_attempt_id, "dispatched")
            ledger.transition_execution(leader.physical_attempt_id, "running")
            ledger.transition_execution(
                leader.physical_attempt_id,
                "result_ready",
                result_ref=f"skills/puppet/proof/{leader_task_id}.json",
                result_digest=digest(f"result-{leader_task_id}"),
            )
            ledger.decide(leader.physical_attempt_id, "accepted")
            ledger.transition_accounting(leader.physical_attempt_id, "leader_accounted")
            ledger.transition_accounting(leader.physical_attempt_id, "parent_accounted")
            ledger.mark_cleanup(leader.physical_attempt_id, "clean")

        self.assertEqual(ledger.peak_active_helpers <= caps.max_helpers, True)
        return ledger

    def test_2x2_override_six_reaches_hierarchy_complete(self) -> None:
        ledger = self._run_hierarchy(leaders=2, leaves_per_leader=2, override=6)
        ok, unmet = ledger.hierarchy_complete(
            fully_idle=True,
            fixture_identity_stable=True,
            source_identity_stable=True,
        )
        self.assertTrue(ok)
        self.assertEqual(unmet, [])
        summary = tw.sanitized_summary(ledger)
        self.assertEqual(summary["counts"]["created"], 6)
        self.assertEqual(summary["counts"]["accepted"], 6)
        self.assertEqual(summary["counts"]["parent_accounted"], 6)

    def test_4x4_override_twenty_reaches_hierarchy_complete(self) -> None:
        ledger = self._run_hierarchy(leaders=4, leaves_per_leader=4, override=20)
        ok, unmet = ledger.hierarchy_complete(
            fully_idle=True,
            fixture_identity_stable=True,
            source_identity_stable=True,
        )
        self.assertTrue(ok)
        self.assertEqual(unmet, [])
        summary = tw.sanitized_summary(ledger)
        self.assertEqual(summary["counts"]["created"], 20)
        self.assertEqual(summary["counts"]["accepted"], 20)
        self.assertEqual(summary["counts"]["parent_accounted"], 20)
        self.assertEqual(ledger.caps.max_helpers, 20)


if __name__ == "__main__":
    unittest.main()
