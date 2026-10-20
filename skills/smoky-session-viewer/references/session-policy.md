# Private session inspection

Use only an explicitly identified, authorized JSONL input. Supported common message shapes are extracted locally; malformed lines remain visible with a warning. Do not search unrelated session roots, auth logs, browser state, credential stores or shell history.

Write to a separate private output path. The HTML is self-contained and uses no remote assets. Open it only when local viewing is requested. Preserve the input transcript and avoid replacing an existing output without explicit intent.

Redaction is best-effort pattern replacement, not a privacy certification. The file can still contain raw/unrecognized messages, instruction text, paths, identities and other sensitive details. Even a redacted preview remains private. Sharing requires separate authorization and a review of the exact artifact.

Return source, output, event count, parse warnings, redaction mode, opened yes/no and privacy limits. This helper neither discovers sessions nor manages processes.

```text
source:
output:
events:
format:
private: yes
opened: yes|no
warnings:
```
