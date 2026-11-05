# Bounded use-case checks

These are manual applications of the authored decision rules to synthetic inputs,
with executable negative controls in [use_cases.py](use_cases.py). They are not
a claim that a harness executed the skill autonomously or that general behavior
is proved. Consumer: coordinator/reviewers evaluating the two new public cores.

## Code cleanup: independent permission boundary

Input: generated `read_record` has an owner guard, a comment explaining its
independent plugin entry point, and “Return the record” narration. Its main
caller checks permission too; plugins call the handler directly. Requested scope:
changed hunks only.

Applied decision: remove only narration; retain the guard and rationale. The
script calls the before/after handlers directly with authorized, unauthorized
and malformed inputs. It compares returned values and exception type/message.
A deliberately unsafe candidate removes the guard; the same check detects the
unauthorized-result difference. Thus this is not just a search for safety words.

## Staged-only cleanup: overlapping functional edit

Input: HEAD returns 1, the index returns 2 with narration, the working tree also
contains an unrelated unstaged change to return 3. A staged-only cleanup must
inspect the index and overlap, not stage the whole working-tree file. Manual
application: identify HEAD/index/working tree separately, preserve the functional
edits, arrange selected owned hunk staging only, inspect the cached diff again.
No stash/reset/extra worker is justified. This scenario is reasoned, not executed
against a live index; index mechanics are standard Git, not new skill code.

## Documentation rewrite: literal, gate and status

Source facts: parser accepts `tool export --preview`; the operation requires
owner approval. The feature is implemented and locally tested, not deployed.
Automatic export is planned. The original and rewritten paragraphs are in the
script. Manual comparison confirms all five distinctions and the approval
condition survive; no claim of deployment or available automation is added.

The script parses the exact documented literal with the synthetic owning parser,
compares selected modes, and checks its safe help surface. A plausible shorter
candidate drops `--preview`; the check detects the mode change even though the
shorter command is accepted by the parser. No export handler exists or executes.
Status/approval truth is checked against the stated source facts, not inferred
from parser success. In a real task the owning source and dated evidence replace
these synthetic facts.

## Agent-policy review: aliases do not create permission

Input: CONTRIBUTING declares POLICY.md canonical; AGENTS.md points there.
`publish-preview` calls a wrapper that still requires owner approval. Requested
scope is report-only review of one README paragraph describing preview as
ungated. Manual application: report the mismatch with wrapper/policy evidence;
preserve canonical/alias mapping; do not normalize aliases, change policy, edit
in report-only mode or audit the rest of the tree.

## Independent advisory attempt

`decision_evaluate` received only public draft rules and these four synthetic
scenarios with competing actions. It returned `status: unavailable`,
`reason: credentials-unavailable`; the judge did **not** run. No credential
inspection/change or alternate provider was attempted. Manual rubric choices:
guard B, staged C, docs A, alias B. These are author reasoning, not independent
judge output, and grant no authority.

## Actual outcome

`python3 proof/smoky-deslop-docs-20261105/use_cases.py`: both executable checks
and both negative controls passed. Manual status/gate/alias comparisons passed
within these bounded examples. Broader autonomous forward-testing remains
unproved; repository CI and required external reviews remain separate gates.

## Optimization-safe proof repair (2026-11-05)

Copilot identified that `assert` checks disappear with Python optimization.
Reproduction: substitute the unsafe handler for the cleanup result; ordinary
Python failed, but `python3 -O` printed PASS and exited 0. This was a genuine
proof defect, not a defect in the authored skill rules.

All proof predicates now use explicit checks that exit nonzero with a reason.
`tests/test_cleanup_documentation_proof.py` runs the safe fixtures and five
fault injections under normal Python, `-O`, `-OO` and `PYTHONOPTIMIZE=1` (24
subprocess cases). Unsafe guard removal, an ineffective guard-removal negative
control, a dropped-preview rewrite, an ineffective documentation negative
control, and a wrong executable each fail before their stage reports PASS.
The safe examples pass in every mode. No gated command or service is invoked.
