# SaariusSkills issue #15 Phase 2 2x2 proof

schema: smoky.swarm.route_terminal_proof.v1
result: passed
route_id: route_20260726_015101_58925_saariusskills-custom-agent-2x2
repo: saariuslystoned/SaariusSkills
base_sha: 23f3b0c8062c7cffaadabee3154477285ccac0f3
source_head_sha: d78ce73c10e673e47be6935559a89a564b4da1c6
run_id: saariusskills-issue15-phase2-2x2-20260726

## Result

The guarded ordinary-custom-agent surface passed two independent 2x2 rounds:

- one exact-count-admitted custom parent per round;
- two `subagent: true` custom children per parent;
- both independently grounded hidden child markers written before profile
  quarantine;
- an OS-locked parent join still empty at controller release;
- one exact parent join written after release with both returned child markers;
- strict verification and exact scoped postflight in both rounds.

The three profiles were byte-identical across fresh workspaces. Each round used
a fresh challenge and produced distinct child and join hashes. Both parent
processes exited `0`; no timeout, guard failure, unexpected file, raw retention,
or foreign-state contact occurred.

## Qualified claim and limit

This qualifies functional two-branch fan-out and parent join for ordinary
Antigravity custom subagents under the exact fingerprint in
`capability-fingerprint.json`.

The frozen parent contract requires one `invoke_subagent` call with one
two-entry `Subagents` array, which the official CLI documentation defines as
concurrent invocation. This proof intentionally did not inspect a tool trace
or transcript. Scheduler concurrency and exact internal tool-call count are
therefore documented semantics, not independently observed internals.

Teamwork Preview was not invoked, installed, or depended on. It is not required
for this qualified surface. PR #6 remains unchanged historical research at
`baea84b2bb0d21ff749ce65d077a76cc76f2e1de`.

## External oracle

The controller admitted the parent only after bounded discovery returned its
exact name once. Child result files existed and were writable, but their random
paths and hidden markers were absent from the parent profile. The parent join
directory and file were OS-unwritable.

After both child files became non-empty, the controller:

1. quarantined the complete `.agents` tree;
2. made the workspace root read-only;
3. confirmed the join was still empty;
4. unlocked only the existing join path.

The join changed afterward. Exact validators then matched both children, the
fresh challenge, all three hidden markers, join order, three result files, and
three unchanged quarantined profiles.

## Evidence

- `capability-fingerprint.json`
- `behavior-report.json`
- `runtime-preflight.json`
- `round-a-fixture.json`
- `round-a-runtime.json`
- `round-a-verification.json`
- `round-a-postflight.json`
- `round-b-fixture.json`
- `round-b-runtime.json`
- `round-b-verification.json`
- `round-b-postflight.json`
- `cleanup.json`
- `STATE.md`
- `events.jsonl`

The executed harness SHA-256 was
`63fc21cff44e060cd86c6be42ea5cd603d0912a55a397a56c5631eacdc83cc5c`.
It is the exact `fanout_harness.py` copy from source head
`d78ce73c10e673e47be6935559a89a564b4da1c6`.

## Commands and verification

The frozen source passed:

```text
python3 -m py_compile plans/custom-agents/scripts/phase1_harness.py plans/custom-agents/scripts/fanout_harness.py
python3 -m unittest tests.test_custom_agent_fanout_harness -v
python3 -m unittest discover -s tests -v
```

Result: `76` repository tests passed.

Each live round used only these harness surfaces against the exact disposable
workspace:

```text
fanout_harness.py build-fixture
fanout_harness.py run-print --sandbox --model gemini-3.6-flash-low --effort low
fanout_harness.py verify
fanout_harness.py postflight
```

The runner invoked AGY `1.1.7` by exact binary hash with absolute
`--add-dir`, a challenge-only `--print` argument, `accept-edits`, sandbox
enabled, and no permission bypass.

## Budget and cleanup

- parent CLI processes: `2 / 2`;
- declared nested child branches: `4 / 4`;
- maximum agent sessions: `6`;
- admitted model-invocation envelope: `12`;
- observed round durations: approximately `10.8` and `11.4` seconds;
- timeouts: `0`;
- raw stdout/stderr/log content retained: `false`;
- foreign state touched: `false`.

After the eight bounded JSON reports were copied, the three exact remote roots
were inventoried as `23` files, `20` directories, `0` symlinks, `0` special
files, and `138132` bytes. Those disposable roots were removed and verified
absent. The deletion is not recoverable; committed reports retain the bounded
proof.

## Next gate

The 2x2 gate is satisfied. A separately frozen and admitted 4x4 reliability
campaign may now test four fresh rounds, failure containment, timeout behavior,
and retry/join policy. No 4x4 session was launched on this route.
