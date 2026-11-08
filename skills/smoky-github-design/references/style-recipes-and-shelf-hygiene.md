# Visual Style Recipes & Asset-Shelf Hygiene

This reference grows as new repository banners, marks, and organization systems are proven. Add new reusable style recipes here without hard-coding private project names, credentials, or internal URLs.

---

## 1. Proven Banner & Mark Style Recipes

### Recipe 1 — Split Dark-Slate Telemetry Banner (`16:9` Hero + `2:1` Social Preview)
- **Composition:** Left `55%` holds clean left-aligned typography on `#11151B`–`#141A18` obsidian slate overlaid with ultra-subtle `6–10%` opacity schematic/astrolabe/PCB trace linework; Right `45%` holds the 3D lighted emblem, instrument, or character bust with rim lighting.
- **Left Typography Stack:**
  1. Monospace eyebrow (`ORG // DOMAIN` or `CATEGORY // LAYER`, warm brass `#D8A34A` or muted ash, wide letter-spacing).
  2. Bold geometric display wordmark (`1–2` lines, warm chalk `#F2EFE9`, tight tracking).
  3. **3-Dot Verb Triad**: Three luminous telemetry dots (e.g., emerald `#3ECF8E`, amber `#F0B44C`, cyan `#38BDF8`) followed by three crisp uppercase capability verbs (`OBSERVE · INFER · PROVE` or `GUARD · BRIEF · FIX`).
- **Safe-Zone Adaptation for `1280×640` (`2:1`) Social Preview:** Keep horizontal margins `>= 100px` and vertical margins `>= 60px` (`1080×520` safe box) so OpenGraph crops on X, Discord, Slack, and iMessage never clip the wordmark or emblem crown.

### Recipe 2 — Dual-Mode Archival Blueprint Banner (`prefers-color-scheme: light` Companion)
- **Composition:** Warm archival vellum/washi stock (`#F3F0E8`) with faint `24px` drafting grid lines (`#D7D9CD`), `1.5px` inked registration marks in the corners, dark pine/indigo display typography (`#1D241E`), botanical-emerald or vermilion stamp accents, and an architectural line-art / shaded-instrument rendering of the same mark on the right.
- **Why It Matters:** Pairing Recipe 2 (`light`) with Recipe 1 (`dark`) inside a GitHub `<picture>` element makes the README feel native to GitHub's Light theme by default while delivering the dramatic obsidian bench aesthetic in Dark mode.

### Recipe 3 — GrokBot / Muse "Character-Mark" (Logo *Is* the Character)
- **Silhouette Rules:**
  - Pure geometric outer container (circular aperture ring, split chamfered cube, squircle oscilloscope bezel, vernier shield, or astrolabe sphere).
  - Subtle expressive "eyes" formed from **instrument primitives** (dual crosshair reticles, phosphor waveform blips, twin iris shutters, or pixel-bar telemetry) recessed inside a dark glass visor.
  - **Zero arms, zero legs, zero clothing/props, zero text** inside the mark.
- **Dual-Scale Payoff:**
  - Scales down to a `24×24` monochrome/duotone inline `<svg>` in site navbars and favicons using `3–6` geometric primitives (`<rect>`, `<circle>`, `<path>`).
  - Scales up to a tactile `512×512` 3D avatar and `16:9` banner focal piece without needing a full 73-frame sprite rig.

### Recipe 4 — Tactile Precision Instrument (`ClawSweeper` Object Pattern)
- **Composition:** When even subtle visor eyes feel too playful for a strict infrastructure or compliance repository, render a single iconic physical tool or mechanism (e.g., precision caliper, optical prism splitting a beam into 3 layers, sweeper brush clearing status cards) diagonally across the right half of the banner.

### Recipe 5 — Seamless GitHub App `[bot]` Badge (`512×512` PNG)
- **Problem:** Full waist-up portraits shrink to an unreadable `12px` head inside GitHub's `40×40` PR timeline avatar, and unvignetted backgrounds leave sharp rectangular seams on dark/light UI cards.
- **Fix:** Crop tightly around the head/visor (`~65%` width occupancy) and apply a smooth outer radial alpha/obsidian vignette (`r = 0.38 -> 0.50`) while staying strictly under `1,048,576` bytes (`< 1 MB`).

---

## 2. Public vs. Private Asset-Shelf Decision Matrix

| Repo Visibility | Asset Shelf Policy | Why |
| --- | --- | --- |
| `PRIVATE` | Upload binary banners/avatars/zips to an immutable private asset-release repo (or repo-designated shelf) and reference release download URLs (or GitHub's authenticated repo asset URLs). | Prevents bloating source git history with multi-MB binaries while keeping private imagery private. |
| `PUBLIC` | Host README/profile banners and OpenGraph images **only** on publicly reachable URLs (`HTTP 200` unauthenticated): either a designated public release-asset repo or compact (`< 250 KB`) optimized assets in `.github/assets/` or `public/`. | Links to a private release repo return `404` to every external reader, star-gazer, and social-cardunfurler. |
