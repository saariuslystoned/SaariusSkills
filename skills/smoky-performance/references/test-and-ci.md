# Test and CI performance

Use the main skill's measurement and acceptance rules with the repository's
existing test commands and CI workflows. For command inventory, baseline
capture, shell fallbacks and result classification, read
[the benchmark protocol](benchmark-protocol.md). For workflow, cache and
selector changes, also read [CI efficiency](ci-efficiency.md).

Test-runtime work covers imports, setup, builds, tests and coverage. Retain
assertions, coverage meaning and relevant integration proof. CI work covers
queueing, setup, restore, builds, tests and workflow overhead while preserving
required checks, status semantics and failure visibility.

Use the canonical command's environment. Isolate credentials without adding
feature-disable flags that change fixture behavior. Pin the requested runtime
before the baseline. Keep other-runtime attempts as incomparable history.
Resolve the working directory to the intended repository and use a writable
task-local temporary directory. Fixtures whose tools search parent directories
must not inherit an unrelated checkout as their repository root.

Attribute queue, setup, build, import, test and post-test/coverage phases when
the runner exposes them. Test counts and unchanged assertions do not establish
instrumented coverage. A present `dist` directory does not establish build
freshness. Verify its producing command and source/config inputs. Keep long
test selectors owned by the canonical build or test command. Use an explicitly
owned prebuilt invocation when appropriate instead of copying selectors to
skip a required build.

Before an expensive benchmark, capture one harmless failing command with the
[capture helper](capture-contract.md) and verify its status and stream
separation. The helper executes one command without a shell. It retains the
`smoky-ci-performance.capture.v1` schema so existing receipt readers continue
to work under the consolidated skill name.

For selector changes, uncertain change data must conservatively retain the
required proof. Never hide failures, remove assertions, narrow required
selectors or make required status optional for speed. Classify results as
success, failure, cancelled, stale, partial or inconclusive according to the
actual execution. Keep rejected experiments and evidence.

Timing and cost are separate claims. Include whether execution is free,
public or self-hosted when discussing cost, and leave monetary values unknown
without a billing source. Cache comparisons include producer, restore and
miss costs along with hit verification and invalidation.

When repeatable repository guidance is useful, keep a small reviewable profile
with the source/runtime, existing baseline and candidate commands, verification
commands, relevant config/dependency/cache identities, metrics, conservative
selector and stop condition. Keep secrets and private payloads out. Use
repository-relative source and proof paths where authorized. Public profiles
must not contain private machine paths, topology or account details.

Stop when the meaningful target is demonstrated or no worthwhile candidate
remains. Structural checks or a skill scaffold do not establish a performance
improvement without comparable execution evidence.
