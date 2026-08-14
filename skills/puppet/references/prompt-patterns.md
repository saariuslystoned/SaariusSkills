# Puppet prompt and handoff patterns

## Initial instruction wrapper

For the regular baseline, compile the initial message in this fixed order:
universal Puppet policy, harness overlay, unresolved-default-model overlay,
regular lifecycle overlay, runtime contract, task packet, and optional user
addendum. Tell the target to respect repository instructions,
`mutation_owner`, `allowed_modes`, `hard_gates`, and terminal criteria, and to
publish only bounded structured checkpoints. State that helper reports, tests,
commits, transport success, and target claims are not controller acceptance.
Require the target to remain available until exact halt.

Never put the prompt body in process arguments. Use stdin, a protected prompt
file, or a session-qualified tmux buffer. Store only a content hash and delivery
state. The current compiler renders in memory and persists only
`effective-instructions.json`, a sanitized manifest containing layer hashes,
byte counts, policy/effective/rendered fingerprints, bounded identities, and a
no-config-write transport declaration. Bind its file hash in the lease,
registry, launch journal, Pass B evidence, and qualification receipt, and
revalidate it before every later session operation.

`initial_message_wrapper` is composition/transport fallback, not proof of a
harness-native global, workspace, or per-run instruction plane. Native-plane
qualification uses a separate descriptor and receipt.

## Conformance handoff

Use `checkpoint_kind: conformance`. Bind schema version, session, run ID,
nonce, phase, sequence, optional message ID and prior checkpoint hash, exact
executable/adapter/protocol fingerprints, timestamp, bounded claims, evidence
references, requested decisions, and limitations. Omit `candidate_commit`.

Ready is sequence zero and nonterminal. Follow-up is sequence one, acknowledges
the controller message ID, and binds the ready artifact hash.

## Source handoff

Use `checkpoint_kind: source` and include the full exact candidate commit plus
the same run and fingerprint identities. Include a concise summary and
suggested next assignment. A changed head invalidates review and acceptance.

Reject unknown or oversized fields, absolute/out-of-root references,
transcripts, logs, prompts, tool arguments, or secret-shaped data.
