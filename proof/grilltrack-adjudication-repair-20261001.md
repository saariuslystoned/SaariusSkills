# GrillTrack adjudication repair

Public verification record for the PR110 merge repair.

- Regression before the fix: composed dependency-cycle planning incorrectly
  exited `0`; the test failed because it expected fail-closed planning.
- Regression after the fix: planning rejects the composed cycle with
  `dependency cycle includes`, writes no project state, and exits nonzero.
- A valid mixed-role adjudication selects incoming and current records,
  applies successfully, retains source snapshots, and validates successfully.
- The independent-history suite and existing shared-ledger adjudication,
  approval binding, and interrupted-recovery coverage remain green.

No private repository, ledger, credential, operator, or delivery artifacts are
included in this proof.

Validation: 30 reconciliation tests and 111 repository Python tests passed.
The parent independently reran all 111 Python tests, reproduced the original
red regression, and confirmed both new regression tests pass. Compile, CLI
help, picker smoke, and staged diff checks passed.
