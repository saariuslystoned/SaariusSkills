# CLI interface contract

Use the repository's established conventions when they exist. Otherwise prefer:

- `-h`/`--help` produces useful help; `--version` identifies the executable.
- Data on stdout; diagnostics and progress on stderr. JSON output remains parseable on successful calls.
- No interactive prompt when stdin is not a terminal or `--no-input` is set; report missing input clearly.
- Preview/dry-run makes its side effects explicit. Force/confirmation options do not replace authorization.
- Respect color and terminal accessibility preferences. Handle interruption with recoverable state.
- Keep credentials out of argv and logs; use an approved consumer mechanism.

A suggested exit map is 0 success, 1 general failure, 2 usage/config error, 3 unavailable dependency, 4 required authority or unsafe state, 5 failed behavior verification. Prefer an existing stable map over renumbering callers.

Specify configuration precedence explicitly, for example flags > process environment > project configuration > user configuration > defaults. Check in only non-secret configuration.

For orchestration commands distinguish intent, provider mechanics, current status, evidence and cleanup. Preserve provider-native identifiers and show source freshness. For deploy/release commands identify the target environment and verify the claimed observable result.

A spec includes purpose; command tree and usage; inputs/options; state changes; standard streams and schemas; exit codes; config precedence; authorization/preview behavior; examples; and compatibility risks. Verify both a representative successful call and an obvious failure without invoking consequential external actions just to test help or parsing.

```text
name and purpose:
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
