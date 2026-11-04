# Assigned-workspace reuse

The worktree core now checks an existing assignment before provisioning.
Workers verify and reuse their supplied checkout; multi-repository work stays
inside each owning Git repository. The policy distinguishes helpers that
fetch from helpers that branch off local HEAD and warns that a runtime start
command may not adopt an existing workspace.

This is portable source guidance. It introduces no runtime, host, private
repository, installation, or activation requirement. Existing single-writer,
trusted-base, preservation and cleanup boundaries remain intact.

Validation: `python3 -m unittest tests.test_portable_skills tests.test_packaging -q`
passed 34 tests. `git diff --check` passed. Source review covered fresh
single-repository setup, new multi-repository setup, existing-session reuse,
and an already assigned worker; only the first two may need provisioning.
No live task or installed skill was changed. Runtime behavior and profile
bindings remain owned by their implementing projects.

## Specialist boundary clarification

Follow-up source review found that “another worktree or worker” could be read
as prohibiting permitted specialist subtasks. The core now prohibits duplicate
top-level assignments and extra writable workspaces while preserving bounded
specialists under the same lead. Each child carries scope, permissions, source,
identity, results and proof; the lead owns integration and final verification.
Conflicting slices have one writer, expansion returns to the coordinator, and
replacement requires stopped-writer evidence for the prior writer and children.
Unproved lifecycle support requires supervised or read-only children.

Aligned against the public coordinator at
`6834f0fafa3c85dc8c03ad31e650e2250ba350ee` (PR213, observed open). No coordinator
source changed. No worker, runtime, installation or external service was launched.

Validation: `python3 -m unittest tests.test_portable_skills tests.test_packaging -q`
passed 34 tests from this repository; `git diff --check` passed. An initial
invocation from the workspace root could not import `tests`; the repository-local
invocation above is the valid result. Static scenario review: assigned lead
reuses its checkout; permitted bounded child keeps the parent assignment;
conflicting writers or new writable territory require handoff/adjudication;
parent exit alone cannot establish child termination. This is source guidance,
not proof of a runtime's child cancellation support.

Source commit: `66df73c` (full identity available in Git).
