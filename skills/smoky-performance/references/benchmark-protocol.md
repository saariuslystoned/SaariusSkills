# Benchmark protocol

Use the repository’s supported test or benchmark command and preserve its
selector, fixtures, assertions, and coverage configuration.

1. Inventory the repository’s supported commands first (`README`, contributor
   docs, package metadata, Make targets, and workflow files). Use the narrowest
   existing command that answers the question; do not create a generic runner.
2. Freeze source, config, runtime/tool versions, environment, dependency
   inputs, cache identity/state, selector, and exact argv.
3. Measure the baseline with phase timings where the runner exposes them.
   Collect wall time and, when useful, CPU, RSS, import/setup timing, test
   timing, coverage timing, and queue/setup timing.
4. Repeat comparable runs if variance can change the conclusion. Explain
   outliers; do not silently replace them.
5. Change one root cause. Re-run the identical protocol and verify the same
   semantic and coverage surface.
6. Compare absolute and percentage deltas, then classify the result:
   `success`, `failure`, `cancelled`, `stale`, `partial`, or `inconclusive`.
   Missing REQUIRED execution evidence is `partial`; missing optional metrics
   are not a false failure. A missing phase is `N/A` or `unknown`, not a reason
   to invalidate an otherwise successful local command.

Interpret CPU/user/sys, wall, RSS, import time, and queue/setup separately.
Treat RSS growth as a leak only when retention evidence supports it. Report
timing separately from billed or metered resource use, and include the
execution class (free, public, or self-hosted) when cost is discussed.

## Preferred capture

On macOS or Linux, with Python 3, measure the supported command with
[capture-contract.md](capture-contract.md). Pass its exact argv after `--`.
Do not put a shell around that argv. Copy `summary.md` and the matching
`capture.json` fields. Unknown cost stays `unknown`.

Use the shell recipes below only when Python 3 or `scripts/capture.py` cannot
run. Report those runs from `exit-code.txt`, `metrics.txt`, and the stream
files. Do not hand-type summary numbers from either path.

## Portable shell capture recipes

After inventorying the supported command, substitute its exact argv for
`<repo-command> [args...]` in the single `set --` binding. These recipes keep
stdout, child stderr, metrics, and the command exit code separate; they
deliberately do not use a `tee` pipeline, whose final command can mask the test
exit. The inner shell sends the child’s stderr to fd 4 while `/usr/bin/time`
keeps its own diagnostics in the metrics file. `argv.nul` is the exact argv
receipt: each argument's raw bytes are followed by one NUL
byte (`\0`), so it is machine-readable rather than a newline- or delimiter-
escaped display.

macOS:

```sh
set +e
set -- <repo-command> [args...]
printf '%s\000' "$@" >argv.nul
/usr/bin/time -l sh -c 'exec "$@" 2>&4' sh "$@" \
  >stdout.txt 2>metrics.txt 4>stderr.txt
exit_code=$?
printf '%s\n' "$exit_code" > exit-code.txt
set -e
exit "$exit_code"
```

Linux:

```sh
set +e
set -- <repo-command> [args...]
printf '%s\000' "$@" >argv.nul
/usr/bin/time -v sh -c 'exec "$@" 2>&4' sh "$@" \
  >stdout.txt 2>metrics.txt 4>stderr.txt
exit_code=$?
printf '%s\n' "$exit_code" > exit-code.txt
set -e
exit "$exit_code"
```

Use shell quoting appropriate to the actual argv (or a small wrapper script
with an argv array) rather than interpolating untrusted input. The files
should include the exact argv, runtime/tool and OS/CPU identity, cache state,
dependency/build setup, stdout/stderr, exit code, and `/usr/bin/time` output.
These wrappers measure the process tree as reported by the platform tool; CPU
and RSS attribution for grandchildren may be incomplete. Do not claim a child
caused a wall-time change without runner-level or child-level evidence.

The final `exit "$exit_code"` is required when the recipe is saved as a
standalone wrapper: otherwise the later `set -e` can make a failed child look
successful to the outer shell. If using the commands interactively, run them
in a subshell (or omit only the final `exit` and inspect `exit-code.txt`) so
recording a failure does not terminate the caller's shell. The macOS recipe
was executed against a local fixture for child statuses 0 and 7; the Linux
`/usr/bin/time -v` recipe is documented but unexecuted in this environment.

“Cold” means a documented fresh dependency/build state for this repository
(for example a new isolated checkout or an explicitly empty task-local build
directory). Never delete shared caches to manufacture cold data. “Warm” repeats
the same command in the same environment after the documented setup. Record
which state was used; cold and warm numbers are not interchangeable.

For a paired comparison, keep the command and environment fixed:

```text
baseline: status=0, wall=12.4s, user=10.8s, sys=0.7s, max_rss=420MB
candidate: status=0, wall=10.1s, user=8.9s, sys=0.6s, max_rss=418MB
delta: -2.3s (-18.5% wall), same selector/coverage, setup=N/A
classification: success
```

The numbers above only show the report shape. A real report copies its values
from the capture receipt or the shell raw files.

Report at minimum: source revision, exact argv, OS/CPU, runtime/tool versions,
cache/dependency/build state, setup and phase fields (`N/A`/`unknown` when
unavailable), wall/user/sys, max RSS, exit code, semantic/coverage result,
comparison delta, and classification.

Retain rejected candidates and their evidence. Stop after the target is
meaningfully demonstrated or after the remaining candidates have no worthwhile
return. Do not force a speedup or trade away correctness for a noisy win.

## Adapted upstream ideas

The command-inventory and separate wall/CPU/RSS comparison ideas are adapted
from OpenClaw’s
[test-performance skill](https://github.com/openclaw/openclaw/blob/99c28bd1862dbb0234887a1550ef2ef577bd40d5/.agents/skills/openclaw-test-performance/SKILL.md)
at commit `99c28bd1862dbb0234887a1550ef2ef577bd40d5`.
The distinction between test-runtime diagnosis and CI-capacity work is adapted
from OpenClaw’s
[CI-limits skill](https://github.com/openclaw/openclaw/blob/33f8c93b5032bd2d6e3d999d38bcd3c0b3930c2d/.agents/skills/openclaw-ci-limits/SKILL.md)
at commit `33f8c93b5032bd2d6e3d999d38bcd3c0b3930c2d`. These are provenance
references only: no OpenClaw quota, runner policy, or command contract is
imported.
