# Proof — Muse ACP lane (`muse-agent-acp`, ACP -> MSP)

Status: implementation complete and locally proven as far as this sandbox
allows. Authenticated remote-shed proof through real Cloudflare Access is
deferred to the operator/GrokBot step below.

## Scope built

- `bridge/muse-acp/adapter/` — `muse-agent-acp` adapter translating ACP to
  Muse Session Protocol (MSP) over `muse serve` stdio
  (server/msp-client/translate), with standalone shim
  `bridge/muse-agent-acp/server.mjs` for direct ACP-client use.
- `bridge/muse-acp/` — MCP bridge (six tools) cloned from `grok-acp` with
  host-default model policy (no hard-coded ids), `muse serve` readiness,
  MSP reasoning tiers, acpx registry override to the in-bridge adapter, and
  the remote-shed HTTP lane (`shed_task_*`, session viewer) cloned from
  `antigravity-acp`.
- `bridge/acp-runtime/runtime-store.mjs` — `muse-acp` prepared-runtime spec.
- Manifests for Codex/Claude/Cursor/AGY, `skills/muse-acp-delegation/`,
  umbrella `acp-delegation` row, `docs/muse-acp-delegation.md`, README,
  packaging tests, CI bridge loop, plugin version 0.5.0.
- acpx fork (`saariuslystoned/acpx`, separate worktree/branch): built-in
  `muse` -> `muse-agent-acp` registry entry, `agents/Muse.md`,
  `docs/agents.md`, registry tests.

## Worktrees

```text
repo:      saariuslystoned/SaariusSkills
worktree:  ~/Developer/SaariusSkills-muse-acp-20261012
branch:    muse/muse-acp-20261012 (base origin/main dd4dfad, fetched+verified)
repo:      saariuslystoned/acpx (fork of openclaw/acpx)
worktree:  ~/Developer/openclaw/acpx-muse-20261012
branch:    muse/muse-agent-20261012 (base origin/main 42bcbf2)
```

## Verified (observed output, 2026-10-13)

- MSP wire probe vs `muse serve --provider echo`: newline JSON-RPC;
  initialize fingerprint matches exported schema:
  `sha256:6de32db08bbbe0deb478d2bfcaba001e9fb490986bc80db3aceb4d996abf7df9`
  (Muse 1.4.7). Full session/start -> turn/start -> item/delta ->
  turn/completed loop observed.
- Adapter tests (`bridge/muse-agent-acp/test/`): **10/10 pass** — unit
  translation tests, fake-MSP integration (streamed text, approval
  round-trip with fail-closed deny), `session/close`.
- Bridge tests (`bridge/muse-acp`, `npm test`): **117/124 pass**. The 7
  failures are sandbox-environment, proven by control: the same 5
  PID-recovery tests fail identically in pristine `bridge/grok-acp` here,
  1 lock test likewise, and the remote-endpoint test cannot `listen`
  (`EPERM`) under this sandbox. Re-run expected green in CI.
- Setup tests: **3/3 pass** (with npm cache redirected out of the sandboxed
  `~/.npm`). `prepare.mjs --bridge muse-acp` -> `RUNTIME_READY`,
  identity `ea5eab6b93f7d2da674edc6177e59f898a5974f50045925268e6f64e8d0e7a34`.
- Python suite (`python -m unittest discover -s tests`): **OK**
  (packaging 20/20 including new muse packaging test).
- acpx registry: esbuild-bundled `src/agent-registry.ts` assertions pass:
  `acpx registry muse entry OK: pi,openclaw,codex,claude,gemini,cursor,copilot,antigravity,devin,droid,fast-agent,fx,grok-build,iflow,junie,kilocode,kimi,kiro,mcode,muse,mux,opencode,pool,qoder,qwen,trae,zeroclaw`.
  Full `pnpm install`/test could not run here (sandbox fetch failure); CI
  or an unsandboxed run must confirm.
- **Local route** (MCP client -> launcher -> prepared bridge -> acpx ->
  adapter -> real `muse serve` echo):
  `readiness ready:true policy:host version "Muse 1.4.7"`, submitted job
  `220ac92b-…`, `backendSessionId: 01a134fe-bb3a-7ba0-b954-b05f937752c4`,
  `RESULT status: completed complete: true`, handoff
  `"echo: Reply with a one-line greeting for the local route proof."`
- **Hop mechanics** (same probe with `SAARIUS_ACP_HOP_ARGV` execing the
  worker launcher with `--worker`, worker state dir overridden): parent
  logged `{"status":"hop","bridge":"muse-acp","identity":"4fce41fb5c62c218"}`,
  job `c2970871-…` completed, and its job record landed in the **worker**
  state root (`/tmp/muse-acp-hop-state/jobs/`), not the parent's.
- **Always-on mechanics** are the same prepared-launcher stdio path as
  Local (placement differs only by host); no separate code path exists to
  prove. A CP-1-labelled live receipt (like `proof/a1-live-dogfood/`) has
  not been captured for this lane.
- **Tunnel shed, local**: HTTP mode without Access env fails closed
  (`ACCESS_TEAM_DOMAIN_REQUIRED`, then `ACCESS_AUD_REQUIRED`). With valid-
  shaped dummy Access env, the host binds loopback (escalated run; sandbox
  blocks `listen`): `POST /mcp` no-JWT **401**, bad-JWT **401**, viewer
  unset **404**, deny log `ACCESS_DENIED` reasons `missing`/`malformed`.
- **Live non-echo turn**: ACP prompt through adapter to real `muse serve`
  (meta provider): catalog `muse-wonder-1.0` (current),
  `muse-wonder-full-1.0`, `muse-spark-1.3`, `muse-spark-1.2`;
  `stopReason: end_turn`; streamed text exactly `MUSE ACP LIVE OK`.

## Not proven here — operator / GrokBot steps

1. Authenticated `shed_task_run` through real Cloudflare Access on
   `shed.sm0ky.dev` (or a muse-specific hostname such as
   `shed-muse.sm0ky.dev`): needs the Access app + AUD tag, the `acp-runner`
   service token, CP-1 launchd env from
   `skills/muse-acp-delegation/references/remote-shed.md`, and the GrokBot
   connector pointed at `https://<host>/mcp` with the `CF-Access-Client-*`
   headers. Suggested GrokBot proof: one `shed_task_run` hello task in an
   allowlisted repo, poll `shed_task_status` to a draft PR, capture the
   receipt under `proof/` like the Antigravity dogfood receipts.
2. True cross-machine Hop receipt (carry laptop -> CP-1 over SSH).
3. GitHub CI green (`node-bridges` now includes `muse-acp` + adapter tests)
   and the acpx fork's full `pnpm` check.
4. Optional upstream PR of the `muse` registry entry to `openclaw/acpx`
   (upstream currently has zero Muse mentions; verified by registry source,
   published 0.19.4, and code search).

## Known limitations (documented in the lane doc)

- ACP `mcpServers` on `session/new` are ignored (MSP session-config mapping
  not implemented); fixed-choice `userInput/request` is declined
  fail-closed; MSP `session/resume` replay is not exposed; `muse-acp`
  remote shed needs its own hostname/port/Access app if run beside another
  lane's shed.
