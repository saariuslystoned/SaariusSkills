---
name: smoky-github-design
description: Design and upgrade GitHub repository and organization front doors — dual-theme `<picture>` README hero banners, `1280x640` OpenGraph social previews, `512x512` logos/character-marks and seamless GitHub App badges, top-starred README above-the-fold layout, and `.github/profile/README.md` organization styling. Use when making any repository, GitHub App, or GitHub organization look cohesive and distinctive, with optional character handoff to `smoky-character-studio`.
---

# Smoky GitHub Design (`smoky-github-design`)

Make any GitHub repository, GitHub App, or GitHub organization front door feel intentional, scannable, and iconic — grounded in the structural patterns of GitHub's most-starred open-source projects and an extensible shelf of artwork recipes.

Keep full mascot/pet-rig production separate: this skill owns **GitHub surfaces, marks, banners, social previews, README above-the-fold hierarchy, and organization `.github` profiles**. Delegate to [`../smoky-character-studio/SKILL.md`](../smoky-character-studio/SKILL.md) only when the user opts into a full multi-angle character identity or `sprite_version: 2` extended pet rig.

Read:
- [references/top10-github-anatomy.md](references/top10-github-anatomy.md) for the live-audited structural patterns across GitHub's top-starred repositories and `.github/profile/README.md` organization pages.
- [references/style-recipes-and-shelf-hygiene.md](references/style-recipes-and-shelf-hygiene.md) for the evolving visual recipe catalog (Banner Layouts, GrokBot/Muse Character-Marks, Precision Instrument Objects, Full Mascot Compositions) and public-vs-private asset-shelf rules.

---

## 1. Choose the Identity Mode First (Grill Lightly Before Rendering)

Every repository deserves a strong banner and front door; **not every repository needs a full mascot**. Align on one of four identity modes before generating artwork:

| Mode | Visual Centerpiece | Best Fit | Companion Handoff |
| --- | --- | --- | --- |
| **Mode A — Typographic / Architectural Diagram** | Crisp vector mark + `<picture>` dark/light typographic banner + inline SVG system flow diagram | Spec repos, libraries, CLI tools, clean-room catalogs | None |
| **Mode B — Precision Instrument / Tactile Object** | Stylized 3D hardware tool, lens, broom, prism, or circuit assembly (`ClawSweeper` pattern) | Developer tools, linters, CI/review rails, infra brokers | None |
| **Mode C — Logo-as-Character ("Character-Mark")** | Minimalist geometric/optical emblem with subtle visor, aperture, or waveform "eyes" (`GrokBot` / `Muse` pattern — zero limbs/clutter) | Productized CLIs, research labs, AI tools needing both a `24×24` SVG favicon/navbar mark and a `16:9` hero emblem | Optional later promotion to `smoky-character-studio` |
| **Mode D — Full Mascot / Bot Persona** | Expressive 3D character bust/hero (`Blaze` / `Smoky Oracle` pattern) | GitHub Apps (`[bot]` PR commenters), control-plane agents, flagship mascots | Use [`smoky-character-studio`](../smoky-character-studio/SKILL.md) for 5-archetype funnel, turnaround sheets, or `73`-frame pet rig |

When locking a new visual mark (Mode B or Mode C), run a **5-candidate `1:1` square GrillTrack concept round** on a consistent neutral studio backdrop so the user compares silhouette and small-size (`24×24` / `40×40`) legibility before rendering wide banners.

---

## 2. Standard GitHub Asset Pack & Exact Dimensions

Produce only the surfaces the target repository, GitHub App, or organization actually uses, and validate every file with `scripts/verify_github_assets.py`:

| Surface | Aspect / Pixels | Format & Byte Cap | Critical Framing Rule |
| --- | --- | --- | --- |
| **README Hero Banner (Dark + Light)** | `16:9` (`1600×900` or `1376×768`) or `3.2:1` (`1600×500`) | `.jpg` / `.webp` / `.png` (`< 500 KB` target; `< 1 MB` hard cap) | Pair `prefers-color-scheme: dark` and `light` in `<picture>` whenever a dark backdrop would clash on Light GitHub (`#ffffff`), or give dark banners a clean rounded border/frame. |
| **Repo OpenGraph Social Preview** | Exact `2:1` (`1280×640`) | `.png`, `.jpg`, or `.gif` (**`< 1 MB` GitHub hard limit** — SVG/WebP rejected by GitHub upload) | Keep all title typography and hero focal points inside the central **`1080×520` safe zone** so X/Discord/Slack cards never clip edges. |
| **GitHub App / Org Avatar** | `1:1` (`512×512` & `1024×1024`) | `.png`, `.jpg`, or `.gif` (`< 1 MB` GitHub hard limit) | High-contrast silhouette legible at `64×64` org header and `32×32` commit/timeline badges. |
| **GitHub App PR-Comment Seamless Badge** | `1:1` (`512×512`) | `.png` (`< 1 MB`) | Tight facial/visor crop (`~65%` frame fill) with a **feathered radial edge vignette** into `#0D1117` / transparent so `40×40` circular/rounded-square `[bot]` PR badges never show harsh crop seams. |
| **Vector Favicon / Navbar Mark** | `1:1` (`viewBox="0 0 24 24"` or `32 32`) | `.svg` (`< 8 KB`) | Derived cleanly from the locked Mode A/B/C silhouette using `currentColor` or semantic CSS tokens. |

---

## 3. Above-the-Fold README & Org `.github` Architecture

Grounded in the live top-starred GitHub audit ([references/top10-github-anatomy.md](references/top10-github-anatomy.md) — `openclaw`, `morluto/rea`, `build-your-own-x`, `developer-roadmap`, `opencode`):

1. **Dual-Theme `<picture>` Hero**:
   ```html
   <p align="center">
     <picture>
       <source media="(prefers-color-scheme: dark)" srcset="<dark-banner-url>">
       <source media="(prefers-color-scheme: light)" srcset="<light-banner-url>">
       <img alt="<Repo Name> — <One-line thesis>" src="<dark-banner-url>" width="100%">
     </picture>
   </p>
   ```
2. **Restrained Signal Row (`<= 6` `flat-square` Shields + Dot-Nav)**:
   - Keep badges strictly factual (CI workflow status, package version, runtime engine, license, docs/live site). Never add vanity counters or broken third-party badges.
   - Follow immediately with a centered dot-separated quick-nav (`Website · Docs · Architecture · Contributing`) and a **one-line Positioning Thesis**.
3. **60-Second Quickstart + System Diagram**:
   - Place the primary copy-paste install/verify block within the first scroll, paired with either a clean architecture table (`Layer 1 / Layer 2 / Layer 3`) or a crisp inline/linked SVG flow figure.
4. **Organization `.github/profile/README.md` Cohesion**:
   - When styling an organization (`<org>/.github/profile/README.md`), reuse the organization's typographic divider motif (for example `* * *`), a cohesive header banner, and a compact `<table>` or categorized matrix linking flagship public repositories with 1-line role descriptions. Never list private repositories or internal hostnames on a public `.github` profile.

---

## 4. Public vs. Private Asset-Shelf Hygiene (Fail-Closed)

Before writing image URLs into `README.md` or `.github/profile/README.md`, check repository visibility (`gh repo view <owner/repo> --json visibility`):

- **Private Repository**: Host multi-hundred-KB binary banners/packs on the owner's designated immutable asset-release repository (or git-tracked `docs/assets/` only if no external release shelf is configured), keeping source repositories lean.
- **Public Repository**: **Never link an asset hosted on a `PRIVATE` GitHub repository's release URL** — anonymous visitors and OpenGraph crawlers receive `404` broken images. Use either:
  1. A designated **public** immutable release shelf (`200 OK` verified without auth cookies/headers), or
  2. Small, optimized tracked assets (`< 250 KB` `.webp`/`.jpg`/`.svg` under `public/` or `.github/assets/`), respecting the target repository's `AGENTS.md` and `REPO_HYGIENE.md` clean-room rules.
- **Clean-Room Sibling Rule**: When a public catalog/product repository shares a visual motif with a private research/workbench sibling, never copy private target lists, internal hostnames, or workbench codenames onto the public banner or README.

---

## 5. Deterministic Asset & Markdown Verification

Always run the bundled standard-library verifier before opening a PR or uploading to GitHub App / Repo settings:

```bash
python3 skills/smoky-github-design/scripts/verify_github_assets.py \
  --readme <path/to/README.md> \
  --repo-visibility <PUBLIC|PRIVATE> \
  --forbid-in-public <org/private-asset-shelf> \
  --banner <path/to/banner-16x9.jpg> \
  --social <path/to/social-1280x640.png> \
  --avatar <path/to/avatar-512x512.png> \
  --mark <path/to/logo.svg>
```

It validates PNG/JPEG/WebP/GIF/SVG dimensions without third-party dependencies, enforces GitHub's `< 1,048,576`-byte cap and PNG/JPEG/GIF format rules on `--social` and `--avatar` uploads (while allowing WebP/SVG for `--banner` and `--mark`), checks `<picture>` `prefers-color-scheme` dark/light sources and `alt` attributes, and fails closed in `PUBLIC` mode on both `--forbid-in-public` patterns and any external GitHub release/raw shelf URL not explicitly verified and passed via `--allow-public-shelf <owner/repo>`.

This skill owns design and verification judgment only; repository commits, release uploads, GitHub App/Settings mutations, and merges follow the active repository's authorization gates.
