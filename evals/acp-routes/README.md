# ACP route benchmark

A small, re-runnable benchmark for the plugin's ACP delegation routes
(`cursor-acp`, `antigravity-acp`, `grok-acp`). Run it on your own machine to
see how each harness + model handles five fixed kinds of work before you
decide where to send a task.

## What it measures

| Task | Category | What the worker must do |
| --- | --- | --- |
| `quick-fix` | Quick fix | Fix `paginate()` against its documented contract. |
| `bounded-impl` | Bounded implementation | Implement an `LRUCache` from a written spec. |
| `refactor` | Long refactor | Split a tangled module into three without changing behaviour. |
| `ui-slice` | UI / design | Build an accessible sortable, filterable table renderer and wire a page. |
| `review` | Verification / review | Find three planted bugs, with decoys, and report them as JSON. |

Each task has a `seed/` repo the worker starts from, a `hidden/` test suite
the worker never sees, and a `reference/` solution. Grading is objective:

- every `.js`/`.mjs` file must pass `node --check` (catches corrupted writes);
- protected paths (for example the visible tests) must be unchanged;
- the score is the fraction of hidden tests that pass, or 0 when a gate fails;
- "solved" means every hidden and visible test passes.

The worker's own summary is recorded but never used for scoring.
`test/graders.test.mjs` proves each hidden suite fails on its seed and passes
on its reference; it runs offline in CI.

## Running it

Prepare the bridge runtimes first (see the plugin README), then:

```bash
node evals/acp-routes/run.mjs --permission approve-all --repeats 3
node evals/acp-routes/run.mjs --permission approve-all --routes antigravity --tasks ui-slice,review --repeats 3
node evals/acp-routes/run.mjs --dry-run            # print the plan only
```

- Attempts run **sequentially** (repeat → task → route), so timings are
  comparable and routes never compete for CPU or rate limits.
- Tasks write files, so the runner requires `--permission approve-all`. That
  sets the documented break-glass `SAARIUS_ACP_PERMISSION_MODE` only for the
  bridge processes the runner starts; your host's default stays
  `approve-reads`.
- Each attempt gets a fresh git workspace seeded from the task. Output goes
  to `~/.local/state/saarius-skills/acp-route-evals/<timestamp>/`
  (`results.jsonl`, `SUMMARY.md`, workspaces), or to `--out`.

## Reading the results

Treat results as a benchmark only for these five tasks on your machine and
subscription at that date. Tool calls and ACP events are recorded as cost
proxies; ACP does not report tokens or subscription usage. Model versions
change often, so re-run after upgrades. Dated baselines from the maintainer
live under `proof/acp-route-evals/`.
