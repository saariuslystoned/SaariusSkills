# Sources and dependency status

1. Existing JevSweeper skill and three references at
   `74c13e997555911a803281742c8fbd7637d84fbf`, plus `CONTRIBUTING.md` and the
   existing packaging checks. These establish the preserved labels, fallback,
   authorization separation, packaging surface, and allowed scope.
2. Canonical review-skill commit
   `ad244204a2a6331b9b58f2aad2f36d4a2bfa57d9` in `saari-co/SmokySkills`.
   Read directly with `git show` at that revision after the review worker's
   commit: [SKILL.md](https://github.com/saari-co/SmokySkills/blob/ad244204a2a6331b9b58f2aad2f36d4a2bfa57d9/skills/smoky-openclaw-autoreview/SKILL.md)
   and [native-queue-review.md](https://github.com/saari-co/SmokySkills/blob/ad244204a2a6331b9b58f2aad2f36d4a2bfa57d9/skills/smoky-openclaw-autoreview/references/native-queue-review.md).
   These establish signed intake, approved metadata-only inspection, separate
   CI/comprehensive/native gates, generation-aware retry, publication readback,
   captured-base applicability, and single-owner bounded waits. Deferred work
   is stored as `pending`; intake refusal can retire without a review.
   This alignment is paired with
   [SmokySkills PR #33](https://github.com/saari-co/SmokySkills/pull/33) at that
   exact head, supplied by the coordinating owner before this commit.
3. Coordinating owner's source correction, attributed to `spark-dgx`
   `548f186a2a7763da1d84c8c7ab28e2b8a307d2ef`: `dispatch-host.ts` does not
   compare the live base SHA in `obsoleteReason`; `validate-native.py` checks
   the default base branch and matching head, not latest-main SHA equality.
   Therefore default-branch advance alone must not require a rebase or retry.
   Queue completion can carry executor failure. This worker did not execute
   or independently inspect that runtime source.
4. Supplied native observation link:
   https://github.com/saari-co/spark-dgx/issues/269#issuecomment-6291726259
   and canonical dependency link:
   https://github.com/saari-co/SmokySkills/blob/main/skills/smoky-openclaw-autoreview/SKILL.md.
   Public web reads returned 404 on 2026-10-20; that is not evidence of absence
   for private repositories. Authenticated read-only `gh api` confirmed the
   canonical path and URL, with current-main blob
   `271a499bfae32037732b9742ea784669e21159f3`;
   [metadata receipt](canonical-contract-link.json). That receipt verifies the
   pointer, not the pending review-skill changes or public availability.

The skill does not copy the queue runbook or assume universal retirement of
legacy paths. The exact target contract governs applicability and rollout.
