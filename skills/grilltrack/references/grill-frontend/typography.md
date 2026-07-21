# Typography and fonts

Grill typography as a complete role system, not as isolated family specimens.
Keep the accepted layout, copy, content lengths, states, and motion present so
the user judges what the product will actually become.

## Before the round

- Record confirmed constraints in the canonical design contract: product voice,
  reading density, required scripts or languages, licensing, asset ownership,
  runtime privacy or performance rules, and framework delivery constraints.
- Identify the real roles the system must fill. Typical roles are display,
  reading, labels or serials, numeric data, code, branding, and animated text.
- Preserve the current verified system as the baseline until a replacement is
  selected, implemented, and verified.

## Five candidates

- Present exactly five complete typographic systems in the one active slot.
- Make candidates materially distinct through role pairing, texture, width,
  rhythm, and voice—not tiny weight or tracking changes to one family.
- State each role mapping neutrally. Do not label one candidate recommended in
  the picker.
- Use real candidate fonts in the evaluation renderer. If the prototype uses a
  remote font service, disclose that evaluation-only boundary and keep it out
  of production.
- Exercise representative long titles, summaries, navigation, buttons,
  metadata, status labels, numbers, and any text animation on desktop and
  mobile.

## Production implementation

- Declare exact families, real weights and styles, fallback stacks, and required
  subsets. Do not rely on synthetic bold or italic faces.
- Use the product's confirmed delivery policy. Prefer a stable framework font
  pipeline or locally controlled licensed assets when same-origin delivery is
  required.
- For Astro projects using the Fonts API, configure the provider, CSS variables,
  weights, styles, subsets, and fallbacks; render the shared `Font` components;
  and serve the generated assets from the built site.
- Map semantic role variables in shared styles so components and embedded
  packages do not silently retain incidental typography.
- Preserve content authority and behavior. A font decision does not authorize
  copy, layout, schema, motion, dependency, or delivery changes outside the
  confirmed slice.

## Verification and contract update

- Wait for the browser font set, then verify loaded faces and computed families
  for every role. These probes supplement, not replace, direct visual review.
- Inspect full-page desktop and mobile screenshots for hierarchy, reflow,
  clipping, overflow, tap targets, and dense-component fit.
- Recheck animated text and reduced motion with the selected display metrics.
- Capture runtime font requests and inspect built assets when delivery policy
  matters. Confirm that evaluation-only providers do not ship.
- Run the product's cumulative accessibility and acceptance checks.
- Update `design.md` with the selected roles, exact faces, weights/styles,
  fallbacks, subset coverage, delivery method, proof reference, and meaningful
  rejected alternatives. Keep unresolved iconography and imagery explicit.
