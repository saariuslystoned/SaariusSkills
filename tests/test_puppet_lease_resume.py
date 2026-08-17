from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "skills" / "herdr-puppet" / "scripts"
sys.path.insert(0, str(LIB))

from herdr_puppet_lib.core import (  # noqa: E402
    RESUMABLE_PRESERVE_REASONS,
    create_qualification_tab,
    preserve_lease,
    resume_lease,
    validate_lease,
)
from herdr_puppet_lib.errors import HerdrPuppetError  # noqa: E402
from herdr_puppet_lib.herdr_client import load_json  # noqa: E402
from herdr_puppet_lib.journal import initialize_journal  # noqa: E402

from tests.test_herdr_puppet import (  # noqa: E402
    FakeClient,
    make_plan,
    refresh_selected_authority,
)


class LeaseResumeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = FakeClient()
        self.plan = make_plan(self.client)
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.run_root = self.root / "run"
        self.plan["proof_root"] = str(self.run_root.resolve())
        refresh_selected_authority(self.plan)
        self.lease_path = self.root / "lease.json"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def create_lease(self) -> dict[str, Any]:
        initialize_journal(self.run_root, self.plan)
        return create_qualification_tab(
            self.client,
            plan_payload=self.plan,
            lease_path=self.lease_path,
            allow_live=True,
            run_root=self.run_root,
            settle_seconds=0.1,
        )

    def preserve(self, lease: dict[str, Any], reason: str) -> dict[str, Any]:
        preserve_lease(
            lease_payload=lease,
            lease_path=self.lease_path,
            reason=reason,
            run_root=self.run_root,
        )
        return load_json(self.lease_path)

    def test_resume_reactivates_human_gate_preserved_lease_and_journals(
        self,
    ) -> None:
        lease = self.create_lease()
        preserved = self.preserve(lease, "human_gate")
        self.assertEqual(preserved["state"], "preserved")
        self.assertEqual(preserved["preserved_reason"], "human_gate")

        result = resume_lease(
            lease_payload=preserved,
            lease_path=self.lease_path,
            client=self.client,
            allow_live=True,
            run_root=self.run_root,
        )

        self.assertEqual(result["result"], "ok")
        self.assertEqual(result["state"], "active")
        self.assertEqual(result["resumed_from_reason"], "human_gate")
        self.assertFalse(result["already_active"])
        self.assertFalse(result["herdr_mutated"])

        updated = load_json(self.lease_path)
        self.assertEqual(updated["state"], "active")
        self.assertEqual(updated["resumed_from_reason"], "human_gate")
        self.assertIn("resumed_at", updated)
        # Historical preservation fields must be retained, not erased.
        self.assertEqual(updated["preserved_reason"], "human_gate")
        self.assertIn("preserved_at", updated)
        # A resumed lease must still validate cleanly (schema round-trip).
        validate_lease(updated)
        # next_seq is untouched by resume; the next send continues where it
        # left off.
        self.assertEqual(updated["next_seq"], preserved["next_seq"])

        events = (self.run_root / "events.jsonl").read_text(encoding="utf-8")
        self.assertIn('"kind":"lease.resumed"', events)
        self.assertIn('"resumed_from_reason":"human_gate"', events)

    def test_resume_reactivates_operator_stop_preserved_lease(self) -> None:
        lease = self.create_lease()
        preserved = self.preserve(lease, "operator_stop")

        result = resume_lease(
            lease_payload=preserved,
            lease_path=self.lease_path,
            client=self.client,
            allow_live=True,
        )

        self.assertEqual(result["state"], "active")
        self.assertEqual(result["resumed_from_reason"], "operator_stop")
        self.assertEqual(load_json(self.lease_path)["state"], "active")

    def test_resume_is_idempotent_on_an_already_active_lease(self) -> None:
        lease = self.create_lease()
        self.assertEqual(lease["state"], "active")

        # Break structural status so a real check would fail; the idempotent
        # short-circuit must never reach it.
        self.client.tab_rows = []
        self.client.pane_rows = []

        result = resume_lease(
            lease_payload=lease,
            lease_path=self.lease_path,
            client=self.client,
            allow_live=True,
        )

        self.assertTrue(result["already_active"])
        self.assertFalse(result["herdr_mutated"])
        self.assertEqual(result["state"], "active")
        # No mutation: the persisted lease is unchanged.
        self.assertEqual(load_json(self.lease_path), lease)

    def test_resume_rejects_terminal_preserve_reasons(self) -> None:
        for reason in sorted({"milestone_complete", "route_superseded"}):
            with self.subTest(reason=reason):
                self.assertNotIn(reason, RESUMABLE_PRESERVE_REASONS)
                # Each iteration gets its own isolated client/run-root/lease
                # so a prior iteration's owned tab and journal cannot bleed
                # into the next one.
                client = FakeClient()
                plan = make_plan(client)
                run_root = self.root / f"run-{reason}"
                plan["proof_root"] = str(run_root.resolve())
                refresh_selected_authority(plan)
                lease_path = self.root / f"lease-{reason}.json"

                initialize_journal(run_root, plan)
                lease = create_qualification_tab(
                    client,
                    plan_payload=plan,
                    lease_path=lease_path,
                    allow_live=True,
                    run_root=run_root,
                    settle_seconds=0.1,
                )
                preserve_lease(
                    lease_payload=lease,
                    lease_path=lease_path,
                    reason=reason,
                    run_root=run_root,
                )
                preserved = load_json(lease_path)

                with self.assertRaises(HerdrPuppetError) as caught:
                    resume_lease(
                        lease_payload=preserved,
                        lease_path=lease_path,
                        client=client,
                        allow_live=True,
                    )
                self.assertEqual(caught.exception.code, "lease_not_resumable")
                self.assertEqual(
                    caught.exception.details.get("preserved_reason"),
                    reason,
                )
                # Rejection must not mutate the lease.
                self.assertEqual(
                    load_json(lease_path)["state"],
                    "preserved",
                )

    def test_resume_blocked_by_structural_status(self) -> None:
        lease = self.create_lease()
        preserved = self.preserve(lease, "human_gate")

        self.client.tab_rows = []
        self.client.pane_rows = []

        with self.assertRaises(HerdrPuppetError) as caught:
            resume_lease(
                lease_payload=preserved,
                lease_path=self.lease_path,
                client=self.client,
                allow_live=True,
            )
        self.assertEqual(caught.exception.code, "resume_structural_blocked")
        self.assertIn("blockers", caught.exception.details)
        # Rejection must not mutate the lease.
        self.assertEqual(
            load_json(self.lease_path)["state"],
            "preserved",
        )

    def test_resume_requires_the_live_qualification_flag(self) -> None:
        lease = self.create_lease()
        preserved = self.preserve(lease, "human_gate")

        with self.assertRaises(HerdrPuppetError) as caught:
            resume_lease(
                lease_payload=preserved,
                lease_path=self.lease_path,
                client=self.client,
                allow_live=False,
            )
        self.assertEqual(
            caught.exception.code,
            "live_qualification_not_authorized",
        )
        self.assertEqual(
            load_json(self.lease_path)["state"],
            "preserved",
        )


if __name__ == "__main__":
    unittest.main()
