# Observable behavior contracts

Define the contract without implementation details:

```text
goal: <observable outcome>
target: <web app|CLI|API|device|artifact and exact version/environment>
access: <authorized URL, command, device or file>
fixtures: <allowed test inputs and approved credential mechanism; no values>
tasks: <concrete user actions>
expected: <visible output and persistent state>
probes: <changed input, retry/reopen, obvious invalid or boundary case>
evidence: <screenshots, response/exit summaries, artifact checks>
excluded: <actions and claims outside scope>
```

For an API, verify response semantics, relevant freshness and state changes using authorized fixtures. For a CLI, verify standard streams, exit codes, non-interactive behavior and the actual dry-run boundary. For UI/device tasks, capture the action and resulting visible state, then persistence where relevant. For generated files, reopen them in a suitable viewer and inspect the claimed content.

A successful deploy/build is not proof of runtime behavior. Use only assigned test targets; the contract must state allowed mutations and communication. Source access needed to proceed is `blocked_source_required`, not an invitation to inspect implementation.
