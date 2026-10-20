---
name: send-to-cua
description: Write a computer-use prompt for Bobby's cua (the Codex app's Computer Use on his MacBook) and launch it there, instead of handing him a prompt to copy and paste. Use when he says "send it to cua", "send it to a cua", "launch a cua", "give me a prompt for a computer use agent", or asks for dashboard, Cloudflare, Stripe, R2, Worker secret or deploy steps his cua should do.
---

# Send to cua

Bobby's cua is the Codex desktop app (ChatGPT.app) with the bundled
Computer Use plugin (`computer-use@openai-bundled`) on his MacBook. It
drives his signed-in browser and Terminal: Cloudflare Access, Workers and R2,
Stripe dashboards, GitHub secrets, store admins, deploys. Before this skill,
agents wrote him a prompt and he copied it into Codex by hand, more than 20
times. This skill writes the prompt the way those prompts worked best and
opens Codex with it already typed in.

His cua model is **GPT-6.1 Sol, Medium effort, Fast** (his default in the
Codex app). A Codex deep link cannot pick the model, effort, speed or
permission mode, so the new chat uses whatever the app's picker last had. If
the picker shows anything else, he switches it before pressing Enter.

## 1. Write the prompt

Follow [the prompt pattern](references/prompt-pattern.md), learned from the
21 prompts and 8 reports so far. In short:

- One opening paragraph: the job, the one target, what not to touch, and
  "Work start to finish. Stop only where a step says STOP."
- Ground rules: STOP and report back before any deploy, secret set or
  change, publish, payment or delete a step does not name exactly, and at
  every permission grant or consent screen (the launcher adds this rule to
  every prompt too); also STOP on new tokens, another account, passwords,
  2FA or passkeys, live mode or real personal details; no secret value
  written anywhere; if a command fails, stop and show it.
- The facts it cannot guess (account ids, Worker names, URLs, exact screen
  text), then numbered steps with what each should show, read-only checks
  first, rollback target recorded before any change.
- Steps only Bobby can do are labelled as his.
- A report-back table, never containing a key, code or link.

Cover every step he named in one prompt. Say the pitfalls in the reference
up front when they apply (wrong Cloudflare account, "Retry build", the
encryption key command, Stripe test values, Access exact paths, Node via mise).

## 2. Send it

**On his Mac** (a local Claude Code, Codex or Remote Control session): save
the prompt to a file and run

```bash
skills/send-to-cua/scripts/send-to-cua.sh <prompt-file> --name <short-slug>
```

The script puts the `@Computer Use` attachment and fixed ground rules at the
top (STOP before any deploy, secret change, publish, payment or delete a step
does not name, and at every permission grant), a report rule at the bottom,
keeps a copy in `~/.cua/outbox/`, puts the prompt on the clipboard, starts
Codex if it is not running, and opens `codex://new?prompt=...&path=<workspace>`.
The workspace is `~/Developer/side-quests/x-api` or `CUA_WORKSPACE`; the
script refuses to run if it is missing rather than open Codex on the whole
home folder. A prompt too long for the link (`CUA_MAX_URL`, 16000 bytes)
opens an empty chat and he pastes. Codex never sends a deep-linked prompt by
itself: Bobby presses Enter, and picks Full access if Codex asks. If the
composer comes up empty, he pastes. `--dry-run` prints the paths and the link
without opening anything.

**From a cloud thread** (no shell on his Mac):

1. Show the prompt in the thread once, as a `writing_draft_v0` card, so
   there is a record and he can read it.
2. When he says "send it" (or asked for that up front), call
   `start_rc_session` with his message as `message_id` and his approved Mac
   folder from `list_devices`. In `instructions`, give the prompt verbatim
   and tell the session to:
   - write it to `~/.cua/inbox/<slug>.md` with its file-write tool, never
     with echo or a heredoc (prompts hold backticks and `$(...)`), with a
     slug of only `a-z0-9-`;
   - run the launcher he installed (`~/.cua/bin/send-to-cua.sh`, see below)
     as `~/.cua/bin/send-to-cua.sh ~/.cua/inbox/<slug>.md --name '<slug>'`;
     never download or pull a newer one itself;
   - report one line (the script's output, or the exact error), and nothing
     else.
3. Wait for that line. Then tell him in one line what is left for his hand:
   allow the Remote Control card if one came up, check the picker shows
   GPT-6.1 Sol, Medium, Fast, pick Full access if Codex asks, and press
   Enter (or paste first, if the script said the prompt was too long).

**Installing the launcher** is Bobby's step, once per change, because his
Mac's safety check rightly refuses to download and run code it has not
seen. He runs, in Terminal, from his SaariusSkills clone on `main`:
`mkdir -p ~/.cua/bin && cp skills/send-to-cua/scripts/send-to-cua.sh ~/.cua/bin/`.

If his Mac's safety check blocks a command, report its exact text and give
him the one command to run in Terminal himself. If Remote Control cannot
start, fall back to the card: he copies it into Codex as before.

## 3. Get the report

The cua writes its report to `~/.cua/reports/<stamp>-<slug>.md` and copies
it to the clipboard, so Bobby can paste it back as "from CUA: ...". A thread
that has a Remote Control session can read the report file itself with his
go. Treat the report as the cua's claim: check what can be checked (HTTP
status, version ids, a GitHub secret's name) before calling a step done.

## Limits

- Codex needs Full access and the Computer Use plugin installed and allowed.
  The cua acts as Bobby in his signed-in browser, so the STOP rules are the
  only brake: never drop them to make a prompt shorter.
- Nothing is sent without Bobby pressing Enter. That is intended: the cua
  changes real accounts.
- One cua job at a time against the same store, Worker or dashboard, and
  never while a Live journeys run uses that store.
- ACP lanes (Cursor, Grok, Antigravity, Muse) are coding workers with no
  computer use, and the Codex CLI has no official computer use yet
  (openai/codex#20851), so this skill uses the app's deep link instead.
