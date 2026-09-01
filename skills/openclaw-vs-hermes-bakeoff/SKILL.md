---
name: openclaw-vs-hermes-bakeoff
description: Use this when someone wants to try OpenClaw and Hermes Agent in Chrome on Grok Bot's computer, click around both UIs, and pick a winner before installing either on their own hardware.
---

# OpenClaw vs Hermes bakeoff

Prepare two Chrome tabs on Grok Bot's computer—OpenClaw Control UI and Hermes
dashboard—both verified on Grok (`grok-4.6` via xAI OAuth), then hand the
desktop over for a side-by-side UI comparison. Success is a human clicking
around both agents, not proof that CLIs or containers exist in the background.

## Done when

- OpenClaw Control UI is open in Chrome at `http://127.0.0.1:18789`, primary
  model is `xai/grok-4.6`, and a Grok chat responds.
- Hermes dashboard is open in Chrome at `http://127.0.0.1:9119`, main model on
  the Models page is `grok-4.6`, chat finished loading (no spinner), and a
  Grok chat responds.
- Both tabs are visible and Grok Bot's desktop is handed over for the human to
  explore and pick a winner.

## Hard rules

1. **Section 0 always runs first.** Health checks and container-state probes
   precede any install, pin, or OAuth work.
2. **Skip install when named containers are already Up.** Do not recreate
   running stacks.
3. **Skip OAuth when xAI credentials are already present** in live container
   config (see Section 0).
4. **Read live config inside containers**, not host bind-mount stubs:
   - OpenClaw: `docker exec <openclaw-container> cat /home/node/.openclaw/openclaw.json`
   - Hermes auth: `docker exec <hermes-container> cat /opt/data/auth.json`
   - Host path `/home/box/.openclaw/openclaw.json` may be a truncated stub;
     never treat it as authoritative.
5. **Docker on Grok Bot's computer:** `DOCKER_HOST=tcp://127.0.0.1:2375`.
   Containers use `--network host`. Bind mounts resolve through overlay
   UpperDir paths the host daemon sees—not as `/home/box/...` on the host
   filesystem.
6. **Do not hand over while Hermes shows** "Loading chat…", a pairing gate, New
   Tab onboarding, or Claude as the active model.
7. **No secrets in chat output.** Do not paste tokens, emails, team IDs, or
   full auth payloads. Confirm presence and model IDs only.

## 0. Already running (always first)

Run these checks before anything else:

```bash
curl -sf http://127.0.0.1:18789/healthz    # OpenClaw Control UI
curl -sf http://127.0.0.1:8642/health      # OpenClaw gateway (if present)
curl -sf http://127.0.0.1:9119/            # Hermes dashboard (GET; HEAD returns 405)
```

Inspect container state (adjust names to match the running stack):

```bash
export DOCKER_HOST=tcp://127.0.0.1:2375
docker ps --format '{{.Names}}\t{{.Status}}\t{{.Image}}'
```

Decision matrix:

| Signal | Action |
| --- | --- |
| Named OpenClaw container **Up** + `18789/healthz` OK | Skip Section 4 (install OpenClaw) |
| Named Hermes container **Up** + `9119` responds to GET | Skip Section 3 (install Hermes) |
| xAI OAuth already in live `openclaw.json` / `auth.json` | Skip Section 5 (OAuth) |
| Health OK but model not Grok | Continue to Sections 5–6 to fix auth/model |

Verify xAI presence from **inside** containers (redact values in logs):

```bash
docker exec <openclaw-container> cat /home/node/.openclaw/openclaw.json
docker exec <hermes-container> cat /opt/data/auth.json
```

## 1. Environment

- Target: Grok Bot's computer (remote desktop handoff environment).
- Browser: Chrome, two tabs side by side or easy to flip between.
- Docker API: `DOCKER_HOST=tcp://127.0.0.1:2375`.
- Network: `--network host` for both agent containers so `127.0.0.1` ports
  match what Chrome opens.
- Confirm Chrome can reach `127.0.0.1:18789` and `127.0.0.1:9119` before
  declaring done.

## 2. Pin stables

Use these exact images unless the operator explicitly requests a bump:

| Agent | Image | UI port | Notes |
| --- | --- | --- | --- |
| OpenClaw | `ghcr.io/openclaw/openclaw:2026.8.1` | `18789` | Control UI |
| Hermes | `nousresearch/hermes-agent:v2026.8.31` | `9119` | v0.21.0; dashboard env vars below |

Hermes dashboard requires:

```bash
HERMES_DASHBOARD=1
HERMES_DASHBOARD_HOST=127.0.0.1
```

## 3. Install Hermes (skip if Up)

Skip entirely when Section 0 shows the Hermes container Up and `9119` healthy.

When installing:

1. Pull `nousresearch/hermes-agent:v2026.8.31`.
2. Run with `--network host` and dashboard env vars from Section 2.
3. Persist auth under `/opt/data` inside the container (bind mount as required
   by the stack, remembering overlay UpperDir semantics from Hard rules).
4. **Model selection is not YAML-default sufficient.** After start, ensure the
   CLI/runtime uses explicit flags:
   `--provider xai-oauth --model grok-4.6`
   YAML defaults listing `grok-4.6` / `xai-oauth` alone do not guarantee the
   active session model.
5. Open the Models page in the dashboard and confirm **main** is `grok-4.6`.
   Leftover Claude entries in the catalog are acceptable; active model must be
   Grok.

## 4. Install OpenClaw (skip if Up)

Skip entirely when Section 0 shows the OpenClaw container Up and
`18789/healthz` healthy.

When installing:

1. Pull `ghcr.io/openclaw/openclaw:2026.8.1`.
2. Run with `--network host`.
3. Confirm Control UI serves on port `18789`.
4. Set primary model to `xai/grok-4.6` in live config inside the container
   (`/home/node/.openclaw/openclaw.json`).

## 5. xAI OAuth (skip if authed)

Skip when Section 0 confirms xAI OAuth already present in live container config.

When OAuth is needed:

1. Complete xAI OAuth through each agent's documented flow.
2. Re-read live config inside containers to confirm credentials landed.
3. Do not rely on host stub at `/home/box/.openclaw/openclaw.json`.

**OpenClaw token entry (Control UI):**

- Focus the token field, press **Ctrl+A**, **Delete**, paste the token, **Enter**.
- The Connect button is unreliable; Enter after paste is the dependable path.
- Placeholder text can mask a stale value—always clear with Ctrl+A Delete before
  pasting.

**Hermes:**

- Ensure `--provider xai-oauth --model grok-4.6` is applied for the session, not
  only declared in YAML defaults.

## 6. Open UIs, verify Grok, hand over

1. Open Chrome tab 1: `http://127.0.0.1:18789` (OpenClaw Control UI).
   - Confirm primary model `xai/grok-4.6`.
   - Send a short Grok test message; confirm a reply.

2. Open Chrome tab 2: `http://127.0.0.1:9119` (Hermes dashboard).
   - Wait until **"Loading chat…"** finishes completely.
   - Confirm Models page main model is `grok-4.6`.
   - Send a short Grok test message; confirm a reply.

3. **Pre-handoff checklist (both tabs):**
   - No Hermes spinner, pairing screen, or New Tab onboarding.
   - Hermes active model is Grok, not Claude.
   - Both agents responded to a Grok test prompt.

4. Arrange tabs for easy comparison and **hand Grok Bot's desktop over** to the
   human evaluator.

## 7. Gotchas

- **Outcome is UI comparison, not infra smoke.** Two healthy health endpoints
  without working Grok chats in Chrome is a failure.
- **HEAD on Hermes dashboard returns 405**—use GET for the Section 0 probe.
- **Host bind paths lie.** Always `docker exec` into containers for authoritative
  `openclaw.json` and `auth.json`.
- **OpenClaw Connect button:** prefer Enter after token paste; stale placeholders
  need Ctrl+A Delete first.
- **Hermes YAML vs CLI:** defaults in config files are not enough; explicit
  `--provider xai-oauth --model grok-4.6` and Models-page verification are
  required.
- **Claude in Hermes catalog is fine** as long as Grok is the active main model.
- **Do not hand over on Hermes loading states**—wait out "Loading chat…" and any
  pairing or onboarding flows first.
- **Overlay bind mounts:** files visible inside containers may not appear at
  `/home/box/...` on the host when inspected outside Docker.
