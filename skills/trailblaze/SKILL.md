---
name: trailblaze
description: Operate Trailblaze for natural-language device control and replayable UI journeys across Android, iOS, and web. Use for Trailblaze or `trailblaze` CLI requests, `.trail.yaml` files, device snapshots and actions, saved sessions, deterministic replay, trace reports, self-heal, trailmaps, waypoints, custom typed tools, Android Studio or CI UI tests, and recording Pixel Use or PhoneProof flows. Do not activate merely for a one-off phone screenshot when no Trailblaze recording, replay, report, or authoring work is requested.
---

# Trailblaze

Treat the installed Trailblaze CLI as the version-matched runtime authority.
Keep this skill as the durable routing and proof boundary; do not duplicate the
CLI's evolving command manual here.

## Load the live contract

1. Read the target repository's `AGENTS.md` and its test or proof contract.
2. Check for `trailblaze` on `PATH`. If it is absent, stop with
   `TRAILBLAZE_SETUP_REQUIRED`; do not invent commands or install software
   without approval.
3. Record `trailblaze --version`.
4. Run `trailblaze skill show`, read its complete output, and follow it as the
   command-level source of truth for the installed version.
5. Prefer the installed skill over remembered syntax or a copied web example.
   If the binary and its skill disagree, stop and report the exact mismatch.

Use official Block documentation only when the installed skill does not answer
a setup question. Do not silently fall back to an older Trailblaze surface.

## Select the rung

- **Drive:** inspect or act on a connected Android, iOS, or web target. Use the
  installed skill's device, target, snapshot, toolbox, and tool loop.
- **Save and replay:** retain a successful flow as `.trail.yaml`, replay it,
  and produce an inspectable report.
- **Compose:** author or repair a trailmap, waypoint, or typed custom tool so a
  stable app-level verb replaces repeated primitive actions.

Load only the installed reference material for the selected rung. Do not make
every exploratory device action into a committed regression test.

## Run a bounded device loop

1. Resolve the exact device and target. When several devices can match, require
   an explicit selection; never choose the first device implicitly.
2. Establish the allowed actions, reset state, test data, expected outcome, and
   restore condition before mutation.
3. Start or bind the Trailblaze session using the live contract.
4. Snapshot before acting. Prefer semantic references and app-level tools over
   coordinates.
5. Attach a natural-language step objective to every meaningful action. State
   what the user should observe, not the coordinate or selector used.
6. Re-observe after each meaningful transition. Preserve the first failing
   state instead of overwriting it with a later success.
7. Save only a flow whose terminal state was actually verified. Replay the
   saved trail against its declared starting conditions.
8. Export the report or trace artifact required by the route, then restore the
   device or app to the agreed state.

Use `--self-heal` only when the route explicitly prefers assisted repair over a
fail-loud replay. Treat a healed recording as changed test source that requires
review and a fresh replay.

## Close with truthful proof

Record:

- Trailblaze version, device class, target, and driver;
- source revision and build artifact identity when testing a product build;
- trail path and digest, session identifier, and report paths;
- replay command, terminal result, and restore result;
- whether any bare step, vision verification, self-heal, or other LLM-backed
  behavior ran;
- remaining gates and unproved claims.

A fully recorded replay without vision verification or self-heal can be
deterministic and LLM-free. Do not extend that claim to authoring, bare steps,
vision assertions, or healing without checking the installed contract.

Treat screenshots, hierarchies, logs, video, prompts, tool arguments, and
reports as potentially sensitive. Keep raw run output in its governed proof
root, sanitize selected artifacts before publication, and never place secrets,
account identifiers, private messages, or device serials in a committed trail.

## Compose with the phone stack

Read [references/phone-stack.md](references/phone-stack.md) when the route also
uses Pixel Use, PhoneProof, a physical phone, Android Studio, Vysor, or another
human mirror. Choose exactly one mutation chain and record it in the proof.

Trailblaze makes a behavior replayable; it does not by itself establish that a
capture came from the intended physical display, bind proof to the reviewed APK,
apply consequence gates, sanitize public evidence, or provide an independent
validator.

## Preserve action gates

- Do not install or upgrade Trailblaze without explicit approval.
- Do not use a test runner as authority to send external communications, make
  purchases, change accounts or security, weaken device protections, mutate a
  non-test device, deploy, merge, or perform destructive cleanup.
- Keep one controller responsible for every device mutation. Observers and
  human mirrors remain read-only unless the route explicitly transfers control.
- Stop on target ambiguity, unexplained device state, missing restore authority,
  or evidence that would expose private content.
