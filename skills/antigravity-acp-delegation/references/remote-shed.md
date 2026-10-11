# Remote shed: run Antigravity tasks on your own always-on machine

Remote-shed mode lets an agent that runs somewhere else (for example a Grok
Bot agent on its cloud Linux box) hand a coding task to **your own**
always-on machine (an "AI Shed", such as a Mac mini). Antigravity runs there,
under your own Google sign-in, and the result comes back as a **draft PR**.

v1 supports Antigravity only.

## What the remote endpoint can do

Only three tools. There is no shell, exec, file, or raw ACP tool on the
remote endpoint.

| Tool | What it does |
| --- | --- |
| `shed_task_run` | Run one coding task in an allowlisted GitHub repo on a new `shed/<taskId>` branch, then open a draft PR. |
| `shed_task_status` | Read one task (status, branch, PR URL, redacted summary). With no `taskId`, says whether the shed is `idle` or `busy`. |
| `shed_task_cancel` | Cancel the running task. No PR is opened. |

`shed_task_run` takes `owner`, `repo`, `task`, `requested_by` (the bot that
asked, for the audit log), and optional `baseBranch` (default `main`) and
`title`.

The shed runs **one task at a time**. Callers get a clear answer to fall back on:

- `{"status":"busy","activeTaskId":...}`: another task is running.
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

The examples use `shed.sm0ky.dev`. Use any hostname on a zone in your own
Cloudflare account.

1. **Prepare the bridge and sign in to Antigravity** (same as Local mode):

   ```sh
   cd <plugin>/bridge/antigravity-acp
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
   export SAARIUS_ACP_ACCESS_TEAM_DOMAIN=<team>.cloudflareaccess.com
   export SAARIUS_ACP_ACCESS_AUD=<aud tag>
   export SAARIUS_ACP_REMOTE_CALLERS=<client-id>.access=acp-runner
   export SAARIUS_ACP_REMOTE_REPO_OWNERS=saariuslystoned,saari-co,dinkuskit
   export SAARIUS_ACP_REMOTE_REPOS_ROOT=$HOME/Shed/repos
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

## Example

```json
{"name":"shed_task_run","arguments":{
  "owner":"saari-co","repo":"site",
  "task":"Fix the typo in the README heading",
  "requested_by":"acp-runner"}}
```

Then poll `shed_task_status` with the returned `taskId` until it reaches
`pr_opened` (with `prUrl`), `no_changes`, `failed`, or `cancelled`.
