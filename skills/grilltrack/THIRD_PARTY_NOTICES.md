# Third-party notices

GrillTrack is a clean-room implementation influenced by the workflows below.
No endorsement is implied.

## Matt Pocock skills

Pinned source: <https://github.com/mattpocock/skills/tree/9603c1cc8118d08bc1b3bf34cf714f62178dea3b>

Relevant skills:

- `skills/productivity/grilling`
- `skills/in-progress/batch-grill-me`
- `skills/engineering/grill-with-docs`
- `skills/engineering/domain-modeling`

License: MIT. Copyright (c) 2026 Matt Pocock.

GrillTrack credits the one-question-at-a-time decision tree, dependency-frontier
batch questioning, recommendations, fact-finding, user-owned decisions,
shared-understanding gate, durable vocabulary, and selective decision
documentation as behavioral influences.

Workflow refresh comparison pin:
<https://github.com/mattpocock/skills/tree/5b15a47f2d7150f545fbcacbfe381787fc0230dc>

Relevant current engineering skills:

- `skills/engineering/grill-with-docs`
- `skills/engineering/implement`
- `skills/engineering/tdd`
- `skills/engineering/code-review`
- `skills/engineering/to-spec`
- `skills/engineering/to-tickets`
- `skills/engineering/wayfinder`
- `skills/engineering/wizard`

The refresh credits typed workflow transitions, source-linked context-boundary
artifacts, separate standards/source-intent review axes, exact-source review
identity, multi-session decision maps, and human-guided setup gates as
behavioral comparisons. GrillTrack does not bundle or invoke these upstream
skills.

Recommendation-question wording pin:
<https://github.com/mattpocock/skills/blob/5beb35b040e3de97e54fa9e386d7e42d15c295c2/skills/productivity/grilling/SKILL.md>

The protocol's recommendation-question wording rule is a narrow adaptation
from `skills/productivity/grilling/SKILL.md` at this pin. No other changes at
this pin are claimed as incorporated.

## Will Ness frontend prototyping skill

Pinned source: <https://github.com/will-ness-ai/skills/tree/131c397a7731b6b0ce398a5b3bb8db8768136bc5>

Relevant skill: `skills/engineering/grilling-frontend-prototyping`.

License: MIT. The pinned fork retains Matt Pocock’s copyright notice.

GrillTrack credits the five-live-variant frontend picker as a behavioral
influence.

## Agent Skills

- Specification: <https://agentskills.io/specification>
- Creation guidance: <https://agentskills.io/skill-creation/best-practices>
- Evaluation guidance: <https://agentskills.io/skill-creation/evaluating-skills>

These materials influenced the portable directory shape, progressive
disclosure, skill boundary, and evaluation approach.

## pstack (Cursor)

Pinned source: <https://github.com/cursor/plugins/tree/a66a8931c2dd71f1ed6abf6a52b1898a9f389ae4/pstack/skills>

Vendored cherry-picks live only under `vendor/pstack/skills/` and are loaded directly by plugin manifests:
`architect`, `automate-me`, `blast-radius`, `create-verification-skill`, `how`, `maintain-verification-skill`, `reflect`, `tdd`, `unslop`, `why`.

License: follow the Cursor plugins repository license for those files. Copyright remains with the upstream authors. `bobby-mode` and `pstack-playbooks` are authored Saarius skills in root `skills/`, not Cursor files.

`backnotprop/pstack` is a third-party mirror and is not the pin.

## Comparison-only systems

The following systems are comparisons, not dependencies:

- Matt Pocock’s Wayfinder:
  <https://github.com/mattpocock/skills/blob/9603c1cc8118d08bc1b3bf34cf714f62178dea3b/skills/engineering/wayfinder/SKILL.md>
- Gemini CLI Conductor:
  <https://github.com/gemini-cli-extensions/conductor>
- GitHub Spec Kit:
  <https://github.github.com/spec-kit/reference/workflows.html>

## EmDash skills

The four EmDash mechanics skills derive from
<https://github.com/emdash-cms/skills/tree/15dcb07160fb321aab93fa67c6d0cbfc1c33e90f>.
License: MIT, Copyright (c) 2026 Cloudflare, Inc. The full license is preserved
in `vendor/emdash-skills/LICENSE` and each packaged upstream skill.
`vendor/emdash-skills/UPSTREAM.json` records the provenance and file hashes.
The vendor mirror is verbatim; packaged `creating-plugins` examples include
reviewed handler-context and email-transport corrections.
`emdash-sites` is separately maintained guidance, not an upstream skill.

## `dithercn` and `@chenglou/pretext` (`emdash-surface-fx`)

- **`dithercn`**: <https://dithercn.dev> — License: MIT. `skills/emdash-surface-fx/assets/dither.js` provides a clean-room vanilla WebGL1 / 2D Canvas / SVG port of Bayer 4x4 and 8x8 ordered dithering patterns, CSS mask helpers, and `tokens.css` (`light-dark()`) color resolution for Astro and EmDash storefronts.
- **`@chenglou/pretext`**: <https://github.com/chenglou/pretext> — License: MIT, Copyright (c) Cheng Lou. Referenced for zero-DOM canvas-measured obstacle text layout (`prepare`, `layoutNextLine`) alongside the standalone helper in `skills/emdash-surface-fx/assets/surface-micro.js`.
- **Teknium WebDev Catalog**: <https://webdev.teknium.io> — Referenced for the 16-family surface and micro-interaction taxonomy in `skills/emdash-surface-fx/references/teknium-catalog-and-astro-recipes.md`.

The full MIT license and copyright notices for `emdash-surface-fx` are preserved in `skills/emdash-surface-fx/LICENSE`.

