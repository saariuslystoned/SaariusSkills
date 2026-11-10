# Proof: Harden EmDash Stitch, Sites, CI Deploy, and Surface FX Skills

## Summary

Distills field-verified EmDash, Stitch, Cloudflare Workers, and Playground guardrails into `emdash-stitch-design`, `emdash-sites`, `emdash-ci-deploy`, and `emdash-surface-fx` without modifying the four verbatim upstream EmDash vendor mirrors (`building-emdash-site`, `creating-plugins`, `emdash-cli`, `upgrading-emdash`).

## Changes

- **`skills/emdash-stitch-design/`**:
  - `references/grilltrack-visual-cycle.md`: Forbids bare macOS Chrome CLI `--headless=new --window-size=390,844` (`NSWindow` `500px` minimum width clamp crops `110px` off the right edge); requires Playwright `page.setViewportSize` or CDP `Emulation.setDeviceMetricsOverride` asserting `window.innerWidth === 390`, and distinguishes Stitch `DESKTOP` export multi-column overflow from capture clipping.
  - `references/taste-and-prompts.md` & `SKILL.md`: Bans decorative telemetry strips and faux-CAD blueprint cosplay (`.preflight-strip`, `[DATUM_A]`, `+00,00`, `FIG. 01`, QA pass-rate badges) and adds closeout verification for external social/community links (Discord, GitHub, social icons).
- **`skills/emdash-sites/` & `skills/emdash-ci-deploy/`**:
  - `references/cloudflare-hosting.md`, `emdash-sites/SKILL.md`, `emdash-ci-deploy/SKILL.md`, `references/onboard-and-troubleshoot.md`: Documents cold D1 first-request migration subrequest exhaustion (~migration `039` across `40+` core migrations) requiring out-of-band `wrangler d1 execute --remote` schema/seed initialization, fail-closed pre-Access `401` `/_emdash*` guards + stateless `301` redirect Workers, and zero-login per-visitor Durable Object playgrounds (`playgroundDatabase` / `EmDashPreviewDB`, `locals.user.createdAt` hydration, `session: { driver: "memory" }`, Turnstile + Rate Limiter on `POST /_playground/init`, stale-cookie auto-recovery, `noindex`, and `~56px` bottom safe-area clearance beneath the floating Playground pill).
  - `references/plugin-surfaces.md` & `references/scenario-checks.md`: Documents `ctx.http.fetch` loopback IP rejection (`globalThis.fetch` for trusted loopback/pinned `PLAYGROUND_*` upstreams while preserving `ctx.http.fetch` SSRF checks on user-supplied URLs), `exports["./native"].workerd` Node-free bundling, and Playground `env` secret isolation (`PLAYGROUND_LOCK=1`, `SHA-256(emdash_playground)` session namespacing).
- **`skills/emdash-surface-fx/SKILL.md`**:
  - Updates Mode B placement guidance for HUD-free 3-plate depth stages (`chrome: 'stage-only'`) and adds `Surface Restraint: Craft Replaces Telemetry Clutter` while preserving zero `/\bany\b/u` matches.
- **`tests/test_packaging.py`**:
  - Adds `test_emdash_stitch_sites_and_deploy_hardenings_are_packaged` verifying line budgets, relative markdown link integrity, public-repo path hygiene, and presence of each named guardrail.

## Verification Commands & Results

1. `python3 -m unittest discover -s tests -q` -> `Ran 231 tests in 288.698s — OK`
2. `python3 skills/grilltrack/scripts/grilltrack_ledger.py --help` -> exit `0`
3. `python3 skills/grilltrack/scripts/validate_picker.py fixtures/frontend-picker/manifest.json` -> `valid` (exit `0`)
4. `python3 skills/smoky-skill-cleaner/scripts/audit-skills --skill skills/<name> --json` across `emdash-stitch-design`, `emdash-sites`, `emdash-ci-deploy`, and `emdash-surface-fx` -> `packaging_errors: []` on all four skills.

## Gates

- Merge remains human-gated. No live deployments, secret reads, or vendor-mirror edits performed.
