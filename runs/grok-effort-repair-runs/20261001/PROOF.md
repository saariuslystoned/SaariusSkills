# PR113 reasoning effort repair proof

## Follow-up (coherent pre-prompt invariant)

Parent strengthened the primary public delegate test with `assert.equal(runtime.turns[0].model, completed.model)`. On the first repair that failed `grok-4.5` vs recorded `grok-4.7` (`parent-model-invariant-red.*`, retained). Cause: the success fixture drifted the model after every effort setter, so `applyReasoningEffort` confirmed High on a changed model and `recheckBoundModel` persisted the stale confirmExactModel snapshot.

Repair: after bound-model reconfirmation and effort application, passively inspect the final status for the exact bound advertised/current model AND required effort. No extra model setter (it resets effort). No renegotiation or retry. Fail closed with zero prompts if either check cannot be confirmed. Persist the coherent actual model/effort from that inspect. Inherit still only reads.

Success fixture now drifts once after the initial High confirmation and before the pre-prompt check, not on every setter. Separate coupled every-setter fixture fails closed. Unsupported / unavailable / refused and inherit cases remain.

No repository-local `AGENTS.md` or `REPO_HYGIENE.md`. Applied `CONTRIBUTING.md`, `skills/grok-acp-delegation/SKILL.md`, and the supplied task constraints. No secrets inspected. No plugin install.

## Source

Uncommitted production change is `bridge/grok-acp/broker.mjs` only:

- `recheckBoundModel()` still confirms the exact bound model, then applies configured effort.
- New `inspectPrePromptInvariant()` then `getStatus` only: advertised+current must equal the bound id; required effort must still be current (inherit records current, no setter).
- `job.model` current/available/effort come from that inspect, not the pre-effort snapshot.
- Shared `reasoningEffortFromStatus()` reuses the existing option parse and `REASONING_EFFORT_*` / `MODEL_*` codes.

Tests only in `bridge/grok-acp/test/reasoning-effort.test.mjs`. `published-controls.test.mjs` was not modified.

Temporary symlink `bridge/grok-acp/node_modules` -> prepared ACPx 0.19.4 tree `.../1bc2f751d791b81bf192419c3dac4e13df7248dad217451bea7f989329e52904/bridge/grok-acp/node_modules` was created for tests and removed after. No installs. Shared dependency tree untouched. Isolated f929 fixture `/tmp/grok-effort-f929-coherent.1tFpZb` overlaid only the new test file; fixture `broker.mjs` compared equal to f929. Existing base fixture `/tmp/grok-effort-base-fixture.1mFL13` remains task-owned; fixture `broker.mjs` compared equal to b2ec489; only the test file was overlaid.

## Red on unchanged f929a25 (strengthened primary)

cwd: `/tmp/grok-effort-f929-coherent.1tFpZb/bridge/grok-acp`
argv: `node --test --test-name-pattern=pre-prompt model reselection keeps required High effort at startTurn test/reasoning-effort.test.mjs`
exitCode: 1
stderr: empty
raw: `runs/grok-effort-repair-runs/20261001/red-f929a25-strengthened-primary/`

f929 `recheckBoundModel` reseeds the bound model (resetting effort to Low) and does not restore High:

```
✖ pre-prompt model reselection keeps required High effort at startTurn (83.485667ms)
ℹ tests 1
ℹ pass 0
ℹ fail 1
  AssertionError [ERR_ASSERTION]: Expected values to be strictly equal:
  'low' !== 'high'
    actual: 'low',
    expected: 'high',
```

## Green on original base without production edits

Isolated fixture `/tmp/grok-effort-base-fixture.1mFL13` from `git archive b2ec4896d0532e6c9a149c114cf3054433be5e7e`. Fixture `broker.mjs` compared equal to base. Same node_modules symlink target. Same argv overlaying only the strengthened test.

exitCode: 0
stderr: empty
raw: `runs/grok-effort-repair-runs/20261001/green-base-b2ec489-strengthened-primary/`

```
✔ pre-prompt model reselection keeps required High effort at startTurn (72.844959ms)
ℹ tests 1
ℹ pass 1
ℹ fail 0
```

Base `runJob` skips a second model path when the delegate handle is already present. One-time drift is armed after the initial High confirmation status and is never consumed, so startTurn stays grok-4.7 + High.

## Green after coherent repair

`node --test test/reasoning-effort.test.mjs`:
exitCode: 0
pass 9 / fail 0
raw: `runs/grok-effort-repair-runs/20261001/green-regressions-coherent/`

`node --test test/*.test.mjs`:
exitCode: 0
pass 100 / fail 0
duration_ms 7510.50375
stderr: empty
raw: `runs/grok-effort-repair-runs/20261001/green-all-grok-coherent/`

Primary public delegate test: actual startTurn model `grok-4.7` == completed.model == persisted selected/current, effort High. Coupled every-setter drift: `MODEL_SELECTION_UNCONFIRMED`, zero prompts. No provider prompts. PR111 temporary-exec startup fixture was not modified or relaxed.

## Earlier proof retained

- First P2 effort-reset red/green: `red-f929a25/`, `green-base-b2ec489/`, `green-regressions/`, `green-all-grok/`, `regressions-tmpdir-import-fail/`
- Parent model-invariant red on the every-setter fixture: `parent-model-invariant-red.*`

## Stop

Ready for parent inspect, verify, commit, and PR113 update. This worker did not commit, push, or change the PR.

## Parent acceptance after main sync

Source commit 5a4a184 repaired effort and coherent model/effort pre-prompt confirmation. Main f04b056 integrated by branch-sync merge c83b5d86. Independent Grok100/100 and packaging14/14 passed. Shared identity/lifecycle/runtime-store117/118 passed; dependency-timeout SIGTERM-exit fixture failed waiting for its npm-exited marker. First shared attempt lacked other lane dependencies; second used task-only0.19.4 symlinks, all removed. Both raw results retained, no assertion relaxed. Exact source/test commands in parent-post-main-summary.json and parent-post-main-shared-deps.json. Linux startup CI race investigation remains separate. ACP job cd420a5d-e1c7-4736-bd6e-0d41f28e63f8 completed and cleanupReady=true.

Parent review: accepted P2 Low-at-start reproduction; base strengthened test passes; final test proves actual bound model and High at startTurn plus persisted proof. Accepted coupled setter drift concern repaired with one passive coherent final snapshot; zero prompts on mismatch; no reselection after effort verification. No self-merge or plugin installation.

## Separate Linux startup CI blocker

ACP investigation ed32761b-5c20-453b-8fb7-88508218421a completed and cleanupReady=true. No production or fixture changes. Public CLI ordering repro rejects pre-response, single-write, and next-request synchronization; the owned creation window is not exposed. timer0 smoke passes locally21/21 but cannot qualify the race. Full proof remains in <USER_HOME>/Developer/worktrees/SaariusSkills-acp-startup-ci-20261001/runs/acp-startup-ci-runs/20261001/. Exact blocker copied here as startup-qualification-blocker.json. No assertions weakened or dependency patched.

## Current-head CI and review closeout

Pushed14c840c079dce5f4d32b41851071f9ddd8af0f8e to PR113; source diff includes repair5a4a184 and mainf04b056 sync. ci-current-final.json confirms all4check success for exacthead. ci-current-linux-node.json binds raw log hash and passing actual High/bound-model startTurn regressions. Original Linux race remains qualification-blocked despite this smoke pass. Spark materialization validates clean detached exacthead/base. Comprehensive Claude review epoch2 accepted under req-20261002T024648Z-327928717642; first terminal status fetch50s timed out. Queue status diagnosis pending. Parent accepted P2; do not claim externalreview clean without terminal tuple-qualified proof.

## Review blocker

Direct bounded metadata established needs-human for exact14c840c/basef04, epoch2, comprehensive/P3 request. review-current-bounded-result.json retains result exit1, correct(0.75),1findings, applied_max_priority=P3. Finding text is unavailable after bounded wrapper status/queue fetches and direct bounded reads through LAN and DNS routes. Both aliases proved hostname spark-2/account <REVIEW_ACCOUNT>. The final task-owned control connection probe succeeded, but finding read exited255; no task-owned socket remained. No other operator processes touched. Classification: review reported one unadjudicated finding; terminal clean proof unavailable. Source P2 regression repaired and CI4/4passes; no review-clean/merge/install claim.
