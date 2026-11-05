# CLI interface contract

## Interface choices

Use established repository conventions first; the following are design defaults, not a requirement to retrofit every command.

- Keep command names and noun/verb ordering consistent with adjacent commands. Use positionals for obvious operands, named options for less obvious inputs, and explicit stable aliases rather than ambiguous abbreviations. Define types, defaults, required inputs, stdin/file handling and invalid combinations for changed arguments.
- Make `-h`/`--help` useful at the relevant command level, with common examples and recovery guidance for missing/invalid input. Preserve parser-specific help precedence. Use the existing version surface to identify the executable when applicable.
- Give humans concise readable output. Put primary data on stdout and diagnostics/progress on stderr. Offer machine-readable output such as JSON or stable plain text for actual consumers, preserving existing schemas and empty-result semantics. Define error-mode output too; never contaminate a promised JSON stream with banners or progress.
- In unattended use or an explicit no-input mode, never wait on a prompt, pager or interactive selector. Missing required input/confirmation fails promptly with an actionable diagnostic and nonzero exit. Piped stdin alone is neither consent nor proof that interaction is unavailable: a caller may explicitly request a selector or pager that consumes piped data and interacts through a separate terminal. Permit that only when the terminal is available and no-input mode is off; otherwise fail promptly if interaction is required. Never infer consent from input data. Add a new `--no-input` flag only if it serves the interface.
- For preview/dry-run, state what is planned, what checks run, and whether it reads the network or writes local artifacts. It must not perform the mutation it claims to preview; don't imply remote readiness from an offline plan. Force/confirmation options do not replace authorization or required human gates.
- Respect terminal/color accessibility preferences without escape codes or animations in machine output. Bound network waits and interruption cleanup where relevant; explain retry safety or partial state after failure.
- Keep credentials out of argv, output and logs; use the approved consumer mechanism, not a new authentication convention.

Use 0 for success and nonzero for failure. Keep an existing stable exit map; do not renumber callers. For a new interface, 1 for general failure and 2 for usage errors are common starting points. Add distinctions only when consumers can use them, and document empty results, partial failure and unavailable dependencies as applicable.

Specify configuration precedence explicitly, for example flags > process environment > project configuration > user configuration > defaults. Check in only non-secret configuration.

## Conditional provenance

When a command reads cached or replicated data, distinguish local data from live reads and any refresh operation. Expose truthful source and freshness in the interface consumers use: observation/refresh time and coverage where known, or explicitly unknown/stale/partial. A cache read is not a live check; an attempted refresh is not a successful one. Explain refresh side effects and failure/fallback behavior. This does not require SQLite, a cache layer, automatic synchronization or a new freshness flag/schema for every CLI.

For orchestration commands distinguish intent, provider mechanics, status, evidence and cleanup; preserve provider-native IDs. For deploy/release interfaces identify the target and what would verify the visible result, without performing gated actions merely to prove parsing.

## Proportionate specification

Use only the fields relevant to the request. For an existing command, document the delta and preserved contract rather than redesigning the tree. Include a normal-use example and a useful failure/unattended example; add piped, configuration or mutation examples only where they clarify the workflow.

```text
name, audience and existing-surface gap:
usage and subcommands:
flags and state changes:
stdout schema:
stderr diagnostics:
exit codes:
config/environment precedence:
preview and authorization:
examples:
compatibility risks:
```

## Verification choices

Use the repository's test harness and safe synthetic fixtures or an approved disposable target. Exercise the actual entry point and a representative end-to-end task, checking useful results, stdout/stderr, exit status and state changes. Add failure cases for touched behavior: malformed/missing input, unavailable dependency, missing authority, empty/partial results or conflicting config. Verify unattended behavior in separate cases:

- Default execution without a controlling terminal and without an explicit no-input flag: use closed/piped stdin and a bounded timeout; require no prompts, pagers or selectors, and fail promptly with actionable diagnostics and a nonzero exit if required input/confirmation is missing.
- Where an explicit no-input mode is supported, test it separately with both closed/piped stdin and terminal-backed stdin, including a controlling terminal available. Bound each case with a timeout and supply no interactive responses; require the same noninteractive behavior and actionable nonzero failure for missing required input/confirmation. Terminal-backed stdin catches commands that improperly prompt only when stdin itself is a terminal.

Test explicitly requested terminal-backed interaction separately with a terminal available and no-input mode off; piping stdin alone does not make a call unattended. Verify previews leave the promised target unchanged. Do not perform consequential external actions just to test help or parsing; name any live verification gap.

Preserve regression coverage for old invocations and machine consumers. For cache-backed commands, test applicable local/live selection and stale, unknown or failed-refresh reporting. For generators/templates, generate representative affected variants and validate the resulting artifacts with their intended consumer: build generated code/CLIs where applicable and exercise their commands and failure paths; parse or load configuration and check reports for useful, correct content. Template snapshots alone cannot prove usable generated output.

Golden tests are useful when deterministic, offline, auth-free command output or a generated artifact is a stable contract that should survive refactors. Capture the smallest contract-shaped subset; control incidental time/order/path variation without masking semantic differences. Prefer focused tests for branch logic or one-field semantics. Inspect intentional fixture changes; never update goldens just to make a regression pass or capture private data.

Report mechanical validation separately from interface judgment. A passing parser/build/test suite does not establish that the workflow is useful or that breaking compatibility is acceptable. For a specification-only request, walk through representative invocations and failure outcomes, but mark implementation/runtime verification as not performed.
