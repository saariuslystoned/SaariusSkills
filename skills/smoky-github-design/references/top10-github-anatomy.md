# Top-Starred GitHub Repository & Organization Front-Door Anatomy

Synthesized from live inspection of GitHub's highest-starred repositories (`codecrafters-io/build-your-own-x`, `sindresorhus/awesome`, `public-apis/public-apis`, `freeCodeCamp/freeCodeCamp`, `morluto/rea`, `EbookFoundation/free-programming-books`, `openclaw/openclaw`, `donnemartin/system-design-primer`, `nilbuild/developer-roadmap`, `jwasham/coding-interview-university`) plus modern developer-tool exemplars (`anomalyco/opencode`, `n8n-io/n8n`, `emdash-cms/emdash`, `github/.github`, `microsoft/.github`).

---

## 1. Four Proven Archetypes Among Top-Starred Repos

| Archetype | Exemplars | Above-the-Fold Stack | When to Use |
| --- | --- | --- | --- |
| **1. Dual-Theme Product Hero** | `openclaw/openclaw`, `anomalyco/opencode` | `# Title — Tagline` (or `<picture>` ornate mark) → `<picture>` `prefers-color-scheme: light` + `dark` full-width banner → centered `style=flat-square` shield bar → bold 2-sentence thesis → `Website · Docs · Getting started · Vision` dot-nav → 1-command install | Flagship apps, frameworks, AI agents, CLI platforms |
| **2. Centered Technical Authority + Flow Figure** | `morluto/rea`, `donnemartin/system-design-primer` | `<div align="center">` H1 + H3 value prop → `flat-square` capability/version badges → dot-separated quick-links → inline `npx` setup → crisp SVG investigation/system architecture flow diagram | Protocol/MCP servers, compilers, reverse-engineering & developer infrastructure |
| **3. Clickable Editorial Banner + Curated Index** | `codecrafters-io/build-your-own-x`, `freeCodeCamp/freeCodeCamp` | Full-width clickable hero banner `[![Alt](banner)](url)` → memorable epigraph or 2-sentence mission → scannable categorized index / TOC | Research catalogs, curated indexes, educational curricula, multi-target workbenches |
| **4. Compact Mark + Pill Nav + Visual Showcase Grid** | `nilbuild/developer-roadmap`, `sindresorhus/awesome`, `emdash-cms/emdash` | Compact centered SVG/PNG mark (`height="70"`) or clean H1 → monochrome pill links (`#0a0a0a` `style=flat`) → 3-column HTML `<table>` visual template/feature cards with real screenshots | CMS ecosystems, starter kits, multi-package monorepos, `.github/profile/README.md` org front doors |

---

## 2. High-Signal Rules That Separate Top-10 Repos from Slop

1. **Theme-Adaptive `<picture>` Over Raw Dark Rectangles**:
   - GitHub renders `README.md` on `#ffffff` (Light default) and `#0d1117` (Dark default).
   - Provide `<source media="(prefers-color-scheme: dark)">` and `<source media="(prefers-color-scheme: light)">` inside `<picture>`. When shipping a single rich cinematic `16:9` banner (such as a dark bench scene), pair it with a light-mode editorial variant *or* compose it with intentional framing so it reads like a framed plate on `#ffffff` rather than an accidental dark cutout.
2. **Badge Restraint (`3–6` Badges Max, `style=flat-square`)**:
   - Mix only live, verifiable facts: CI status, published package version, runtime requirement, license, and primary community/site link.
   - Never mix 4 different badge heights (`for-the-badge` next to `plastic` next to `flat`) in the same row.
3. **Dot-Separated Quick Navigation (`·` or `&middot;`)**:
   - A single centered line (`[Website](...) · [Catalog](...) · [Architecture](#...) · [Submit](...)`) outperforms deep nested Markdown TOC bullets above the fold.
4. **Honest Visual Evidence Below the Hero**:
   - `emdash-cms/emdash`, `morluto/rea`, and `n8n-io/n8n` follow the hero with **one** truthful artifact: an SVG pipeline diagram or real Desktop screenshot grid (`<table><tr><td width="33%">...`). Never paste marketing fluff before showing how the software works.
5. **Organization `.github/profile/README.md` Discipline**:
   - Keep `<org>/.github/profile/README.md` under ~60 lines: one org banner or typographic signature, a 2-sentence charter explaining how the packages fit together, and a crisp table/list of public entrypoints.
