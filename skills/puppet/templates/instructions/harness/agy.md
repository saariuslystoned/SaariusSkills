## AGY harness overlay

- Apply the session contract exactly as declared by launch and wrapper parameters.
- Maintain progress with explicit milestone beacons and durable checkpoint checks.
- Do not stop after a partial checkpoint if target completion remains unsatisfied.
- Keep changes confined to the Puppet-owned session boundaries.
- Keep task evidence and manifest checksums intact.
- Treat exact artifact allowlists as hard boundaries: when the task says to
  atomically write only one named path, create exactly that file and no
  parallel summary or checkpoint artifact.
- Never synthesize `conformance_handoff.json` or another conventional handoff
  name unless the task packet explicitly names that exact path.
