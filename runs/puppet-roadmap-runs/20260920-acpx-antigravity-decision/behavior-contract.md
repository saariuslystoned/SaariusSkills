# Antigravity lane comparison behavior contract

## User-visible goal

Compare the native AGY stream-json lane with the official Antigravity ACP
runtime on the same disposable task, without transcript retention or billing
fallbacks.

## Target

- Type: local CLI/runtime
- Access: installed native `agy` and pinned `agy_acp_server` + matching helper
- Credential source: existing personal Google OAuth profile only; no tokens or
  credential stores may be inspected
- Workspace: one disposable task-owned repository

## Checks

1. Verify both runtime identities and advertised model surfaces without sending
   a prompt.
2. With explicit authorization and overage disabled, run one tiny disposable
   task through each lane using the same model intent.
3. Compare observed model, session continuity, terminal result, question
   behavior, and owned-process halt.

## Expected behavior

- Native lane and ACP lane identify themselves distinctly.
- Requested model is acknowledged exactly; no silent substitution occurs.
- ACP uses personal OAuth through `GEMINI_HOME`; API-key/Cloud fallback is
  absent.
- ACP fixed-choice questions cancel and require a human answer; no option is
  auto-selected.
- Each lane produces bounded metadata only, and its owned process tree is
  confirmed stopped.
- No lane uses purchased credits or overage billing.

## Stop conditions

Stop before a model request if the ACP binary/helper is absent, OAuth is not
already ready, overage state cannot be confirmed disabled/never, model identity
is ambiguous, or the runtime requests interactive login.

## Evidence

Record only command names, exit codes, runtime/model/session identifiers,
bounded result status, process-identity/halt facts, and quota/overage state.
Never retain prompts, model output, question text/options, auth URLs, tokens,
cookies, or credential-store contents.
