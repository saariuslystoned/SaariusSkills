# Subscription profiles

Subscription authentication for Puppet-owned private profiles is durable
and isolation-scoped. Onboarding and status checks are body-free and
never perform login on their own. A login handoff is always a
human-only account action that Puppet only presents, never runs
unattended.

## Durable private profiles

Subscription authentication is isolation-scoped and durable. With a
private-home selector, use one stable Puppet-owned mode-0700 home/config
root per user, harness, and account selection, never inside a disposable
run, proof, or campaign root. `profile-init` creates that root once and
idempotently rejoins it. It may atomically refresh the profile's
non-secret, exact launcher authority after a compatible harness or
Puppet update without replacing the profile directories or their
authentication state. Rejoining or refreshing a profile is not a
request to log in. Puppet silently checks native status before each
launch and reuses a logged-in profile without a human prompt. A human
login handoff is allowed only for initial enrollment or after the
provider reports that the session was invalidated, revoked, or logged
out. Puppet does not copy an existing credential or perform login
itself. For Claude specifically, an enrolled, stable Puppet-owned
profile may present the ready startup screen immediately on later runs,
so the startup-screen reducer reaches ready without navigating
intermediate gates; a fresh, un-enrolled profile instead shows the
logged-out screen, which the reducer treats as a fail-closed forbidden
gate, so Puppet neither copies auth into it nor runs an unattended login
and only presents the one-time human enrollment handoff. A
harness-native operating-system keyring may instead be reused only when
its non-secret configuration and session state remain separately
isolated and the exact adapter proves that boundary.

Prefer safe adoption of an already-authorized operator subscription when
the harness exposes a qualified auth-only selector or broker. Do not
adopt an operator-global home merely because it is logged in: that can
also import unrelated instructions, configuration, plugins, sessions,
and logs. When safe adoption is unavailable, group the one-time profile
enrollments into first-use Puppet onboarding instead of interrupting
later runs with repeated prompts.

## Onboarding

Run first-use or recovery onboarding for the selected harnesses:

```bash
python3 <skill-root>/scripts/puppet.py onboard \
  --profile-shelf <durable-private-shelf> \
  --manifest agy=<current-agy-manifest> \
  --manifest codex=<current-codex-manifest> \
  --manifest claude=<current-claude-manifest> \
  --manifest grok=<current-grok-manifest> \
  --manifest cursor=<current-cursor-manifest>
```

Reuse every `ready` profile without prompting. Present `login_command`
only for an `enrollment_required` profile, then rerun `onboard` to
verify it. `status_unknown`, `status_unavailable`,
`native_reuse_candidate`, and `unsupported` are blockers, not reasons to
guess or log in blindly. `native_reuse_candidate` specifically means the
subscription reuse mechanism is known but the remaining runtime
isolation is not qualified. The login handoff is an explicit account
action and never runs unattended. `profile-init` and `profile-status`
remain the low-level single-target equivalents.

## Per-harness authentication notes

Use `onboard` with the current adapter manifest for every selected
harness and one durable mode-0700 profile shelf. It prepares or rejoins
supported profiles, runs body-free native status checks, silently marks
logged-in profiles ready, and emits a login handoff only for a profile
reported logged out. It never runs that handoff, launches a model, or
changes an account. A status failure remains local to that harness so
the other selected subscriptions still classify. AGY reports
`native_reuse_candidate`: its vendor route silently reuses a valid
operating-system keyring profile, but Puppet does not probe the current
account or emit a login action while AGY's separate
configuration/no-bleed boundary is unqualified. Cursor uses an exact
private HOME/config/data root and file-backed credential selector. Its
native status probe runs with browser opening disabled, retains only
the allowlisted login classification, and emits the one-time login
handoff only when that isolated profile reports logged out. This
qualifies authentication isolation, not Cursor's remaining workspace,
default-model, process-population, or lifecycle behavior.

After the operator completes that account action, use `profile-status`
to retain only an allowlisted login state. Codex, Claude, Cursor, and
Grok have public private-profile recipes. Cursor's recipe fixes
`AGENT_CLI_CREDENTIAL_STORE=file`, isolates HOME/config/data, and keeps
`NO_OPEN_BROWSER=1` on status and login-handoff preparation; Puppet
itself never runs the handoff. AGY does not need credential copying or
a second Puppet-owned login profile: its installed CLI can reuse the
operator's native keyring. It remains non-launchable until Puppet can
isolate AGY's global configuration, instructions, plugins, sessions, and
logs independently of that keyring.

`doctor` and `launch` require the selected profile explicitly. `launch`
passes only that profile's closed home/config environment to the exact
target and revalidates its manifest, executable, directory identities,
login state, and environment fingerprint immediately before target
start. It never falls back to an operator-global harness home.
