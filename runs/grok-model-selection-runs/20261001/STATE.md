# Native Grok model selection

Status: VERIFIED — independent Grok96, packaging14, shared20 passed; PR preparation.
Repo: saariuslystoned/SaariusSkills
Worktree: <USER_HOME>/Developer/worktrees/SaariusSkills-grok-model-selection-20261001
Branch: codex/grok-model-selection-20261001
Base: b2ec4896d0532e6c9a149c114cf3054433be5e7e (fresh origin/main)
Worker lane: native Cursor ACP, explicit Grok4.7; user authorized ACP implementation.

Acceptance implemented:
- Optional `model` and `fallbackModels` (max 2 exact ids) on Grok readiness and delegate.
- Omitted model prefers advertised grok-4.7, then grok-4.6, then grok-4.5.
- Supplied fallbackModels replace those alternatives. Empty list is strict grok-4.7.
- Explicit model stays exact. Explicit constructor pin stays strict unless a per-job model or fallbackModels is supplied.
- Readiness returns the full catalog, catalogReady, selectionReady, requested policy, and selected model.
- The resolved id is bound per job and rechecked immediately before the prompt. Catalog drift does not switch models or send a prompt.
- Broker `model` is not mutated by a job.

Tests: `node --test bridge/grok-acp/test/*.test.mjs` 96 pass / 0 fail. `python3 -m unittest tests.test_packaging -q` 14 pass / 0 fail. No live Grok prompt.
