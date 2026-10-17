# Remote shed: run Antigravity tasks on your own always-on machine

Remote-shed mode lets an agent that runs somewhere else (for example a Grok
Bot agent on its cloud Linux box) hand a coding task to **your own**
always-on machine (an "AI Shed", such as a Mac mini). Antigravity runs there,
under your own Google sign-in, and the result comes back as a **draft PR**.

v1 supports Antigravity only.

## What the remote endpoint can do

Only five narrow task tools. There is no shell, exec, file, or raw ACP tool on the
remote endpoint.

| Tool | What it does |
| --- | --- |
| `shed_task_run` | Run one coding task in an allowlisted GitHub repo on a new `shed/<taskId>` branch, then open a draft PR. |
| `shed_task_status` | Read one task by `taskId` (status, branch, PR URL, redacted summary). With no `taskId`, returns shed state (`idle` / `available` / `busy`), `running`, `maxConcurrent`, and every running task (`taskId`, `repo`, `branch`, `requestedBy`, `startedAt`). |
| `shed_task_cancel` | Cancel a running task by `taskId`. No PR is opened. |
| `shed_task_steer` | Send a follow-up instruction (`{ taskId, instruction, requested_by }`) into a running task's ACP session. Refuses non-running tasks and secrets. |
| `shed_task_result` | Read the final outcome (`{ taskId }`) of a finished task from its task record: redacted `summary`, `prUrl`, `headSha`, `harness`, `model`, and `session_url`. |

`shed_task_run` takes `owner`, `repo`, `task`, `requested_by` (the bot that
asked, for the audit log), and optional `baseBranch` (default `main`),
`headBranch`, `forge`, `title`, `harness` (`antigravity` or `muse`), and
`model` (validated against the harness's advertised models).

The shed runs up to `SAARIUS_ACP_REMOTE_MAX_CONCURRENT` tasks at once
(default 1, max 16). Each task gets its own git worktree under
`<repos root>/.saarius-shed/worktrees/<taskId>`, removed when the task ends or
is cancelled. The bridge keeps **no queue**; callers queue themselves.
Callers get a clear answer to queue or fall back on:

- `{"status":"busy","running":N,"maxConcurrent":N,"tasks":[...],"message":...}`:
  the cap is reached; nothing was started. Queue and resubmit later.
- Error `BRANCH_BUSY` (`details.taskId`): the same repo + `headBranch` already
  has a running task. Wait for it or cancel it.
- `{"status":"unavailable","reason":...}`: Antigravity isn't ready (sign-in,
  runtime, readiness), or the repo isn't cloned on the shed.

Task statuses: `running`, `opening_pr`, `pr_opened`, `no_changes`,
`cancelled`, `failed`, `unavailable`.

## How it stays safe

- **No inbound ports.** The bridge listens on `127.0.0.1` only, and refuses
  any other bind address. A Cloudflare Tunnel (`cloudflared`) on the shed
  makes the only outbound connection.
- **Authenticated callers only.** A Cloudflare Access application on the
  hostname admits only requests with a service token. The bridge then checks
  the signed Access JWT itself (issuer, AUD, expiry, signature against your
  team's public keys) and maps the token's client id to a caller label from
  `SAARIUS_ACP_REMOTE_CALLERS`. Unknown tokens get 401. An MCP session stays
  tied to the caller that opened it.
- **Repo allowlist.** Tasks run only in repos whose owner is on
  `SAARIUS_ACP_REMOTE_REPO_OWNERS`, cloned under
  `SAARIUS_ACP_REMOTE_REPOS_ROOT/<owner>/<repo>`, and every git remote of
  the worktree must point at an allowed GitHub owner.
- **New branch, draft PR, never force or merge.** Each task gets a fresh git
  worktree on `shed/<taskId>` from `origin/<baseBranch>`. The agent is told
  not to commit or push. The shed commits, does a plain `git push -u`, and
  runs `gh pr create --draft`. It never force-pushes and never merges.
- **No secrets in or out.** Task text and titles that look like tokens or
  keys are refused (`SECRET_REFUSED`). Summaries and PR bodies are redacted.
  The audit log (`<state dir>/tasks.jsonl`) records task id, caller,
  `requested_by`, repo, branch, status, and PR URL. It never records the
  task text or any credential.
- **Same bridge contracts.** Pinned runtime, `oauth-personal`, no API-key or
  Cloud-credential fallback, and the permission mode read from the shed's
  own `SAARIUS_ACP_PERMISSION_MODE`. Callers can't change any of these.
  Antigravity runs under your own Google account on your own machine. No
  credentials are copied anywhere.
- **No Hop here.** HTTP mode refuses `SAARIUS_ACP_HOP_ARGV`; the worker and
  ACpx run locally on the shed.

## Setup (on the shed)

The shed service code lives in
[saari-co/ai-shed](https://github.com/saari-co/ai-shed); run it from a clone of
that repo (`<ai-shed checkout>` below), not from `saarius-skills`.

The examples use `shed.sm0ky.dev`. Use any hostname on a zone in your own
Cloudflare account.

1. **Prepare the bridge and sign in to Antigravity** (same as Local mode):

   ```sh
   cd <ai-shed checkout>/antigravity-acp
   npm run setup && npm run setup-runtime && npm run doctor
   ```

2. **Clone the repos** the shed may work on, and make sure `git push` and
   `gh` work for them as you:

   ```sh
   mkdir -p ~/Shed/repos/saari-co && cd ~/Shed/repos/saari-co
   gh repo clone saari-co/<repo>
   gh auth status
   ```

3. **Cloudflare (in your account; nothing here is automated):**
   - Create a tunnel (`cloudflared tunnel create shed`) with a public
     hostname `shed.sm0ky.dev` → `http://127.0.0.1:8765`.
   - Zero Trust → Access → Applications: add a self-hosted app for
     `shed.sm0ky.dev` with one **Service Auth** policy that allows only your
     service token(s). Note the app's **AUD tag**.
   - Service Auth → create a service token (for example `acp-runner`). Note
     the Client ID and Client Secret. The secret stays in the caller's
     connector config; the shed only needs the Client ID.

4. **Start the bridge** (from a launchd agent so it survives reboots):

   ```sh
   export SAARIUS_ACP_TRANSPORT=http
   export SAARIUS_ACP_HTTP_PORT=8765
   export SAARIUS_ACP_HTTP_PUBLIC_HOST=shed.sm0ky.dev
   export SAARIUS_ACP_ACCESS_TEAM_DOMAIN=<team>.cloudflareaccess.com   # e.g. sm0kydev.cloudflareaccess.com; must match the JWT iss exactly
   export SAARIUS_ACP_ACCESS_AUD=<aud tag>
   export SAARIUS_ACP_REMOTE_CALLERS=<client-id>.access=acp-runner
   export SAARIUS_ACP_REMOTE_REPO_OWNERS=saariuslystoned,saari-co,dinkuskit
   export SAARIUS_ACP_REMOTE_REPOS_ROOT=$HOME/Shed/repos
   export SAARIUS_ACP_REMOTE_MAX_CONCURRENT=5   # optional, default 1
   export SAARIUS_ACP_PERMISSION_MODE=approve-all
   npm run serve
   ```

   One service token (one dispatcher bot) is the default. Add more
   `<client-id>=<label>` pairs, comma-separated, to give each bot its own.

5. **Point the caller at it.** For example, a Grok Bot remote MCP connector:
   - URL: `https://shed.sm0ky.dev/mcp`
   - Static headers: `CF-Access-Client-Id: <client id>` and
     `CF-Access-Client-Secret: <client secret>`

   Calls must pass `requested_by`.

## Read-only session viewer (`/s/<sessionId>`)

Every task gets a read-only web page showing what the agent is doing:
task metadata (repo, branch, requested_by, status, PR link), the prompt,
the plan, each agent step and tool call, and the final result.

- `shed_task_run` waits up to ~10s for ACP `session/new`. If the session
  starts in time, its first response carries `session_id` (the ACP session
  UUID) and `session_url` (`https://shed.sm0ky.dev/s/<session_id>`). If it
  stalls, the response has `sessionPending: true` and `shed_task_status`
  returns both fields once ready (per task and in the running list).
- `GET /s/<id>` serves HTML; `GET /s/<id>.json` serves the same view as JSON.
  While a task runs the page polls the JSON every 3s and refreshes on change.
  After it finishes the page renders from the stored transcript at
  `<stateDir>/sessions/<id>.json` (mode 0600), so it keeps working with no
  live ACP process and across bridge restarts.
- Ids must be lowercase UUIDs; anything else (path tricks, query strings,
  extra segments) is 400/404. Only `GET`/`HEAD` are accepted. The viewer has
  no route that starts, cancels, or sends input to a task.
- Everything shown is passed through a redaction pass first (GitHub
  `ghp_`/`gho_`/`github_pat_` tokens, Cloudflare API tokens and global keys,
  `CF-Access-Client-Id/Secret`, `Authorization`/Bearer headers, AWS key ids
  and secret keys, PEM private keys, JWTs, URL credentials, and generic
  `*_KEY=` / `*_TOKEN=` / `*_SECRET=` / `*_PASSWORD=` lines).
- Responses carry `X-Robots-Tag: noindex, nofollow, noarchive, nosnippet`,
  `<meta name="robots" content="noindex, ...">`,
  `Cache-Control: no-store, private, max-age=0` (plus `CDN-Cache-Control` /
  `Cloudflare-CDN-Cache-Control: no-store`), a strict nonce CSP,
  `Referrer-Policy: no-referrer`, and `X-Frame-Options: DENY`.

### Bridge config

| Env | Meaning |
| --- | --- |
| `SAARIUS_ACP_VIEWER_ACCESS_AUD` | AUD tag of the **viewer** Access application (below). |
| `SAARIUS_ACP_VIEWER_EMAILS` | Comma-separated emails allowed to view: `ryan@smokyproduct.co`. |
| `SAARIUS_ACP_SESSION_BASE_URL` | Optional; default `https://shed.sm0ky.dev`. Must be https. |

If the two viewer variables are unset, `/s/*` answers 404: the viewer is off,
never open. The bridge re-verifies the Access JWT on every viewer request
(team keys, issuer, viewer AUD, `email` in the allowlist) and refuses service
tokens there; `/mcp` keeps its own AUD and service-token check and refuses a
human login.

### Cloudflare Access setup (operator step; not applied by this change)

Add a second, more specific self-hosted Access application in front of the
same tunnel hostname. Access matches the most specific path, so `/s/*` gets
the login policy and `/mcp` keeps the service-token-only application.

1. **Existing app (unchanged): "AI Shed MCP"**, domain `shed.sm0ky.dev/mcp`
   (or the whole host as today). Policy: action **Service Auth**, include
   *Service Token* = the shed caller tokens. No email/login rule. Starting
   and cancelling tasks stays here, service-token only.
2. **New app: "AI Shed session viewer"**, type Self-hosted,
   domain `shed.sm0ky.dev`, path `s/*`. Session duration 24h or shorter.
   Identity provider: one-time PIN (or the team's IdP). Policy
   "Ryan only": action **Allow**, include *Emails* = `ryan@smokyproduct.co`.
   No service-token rule, no Bypass, no Everyone.
   Optional hardening: enable "HTTP-only" and "Same-site: Lax" cookie
   settings; turn off "Enable automatic cloudflared authentication".
3. Copy the new app's **Application Audience (AUD) tag** into
   `SAARIUS_ACP_VIEWER_ACCESS_AUD`, set
   `SAARIUS_ACP_VIEWER_EMAILS=ryan@smokyproduct.co`, and restart the bridge.
4. Optional: a Cache Rule for `shed.sm0ky.dev/s/*` set to **Bypass cache**
   (the bridge already sends `no-store`).

Sending input into a session is out of scope; the viewer is view-only.

## Example

```json
{"name":"shed_task_run","arguments":{
  "owner":"saari-co","repo":"site",
  "task":"Fix the typo in the README heading",
  "requested_by":"acp-runner"}}
```

Then poll `shed_task_status` with the returned `taskId` until it reaches
`pr_opened` (with `prUrl`), `no_changes`, `failed`, or `cancelled`.
