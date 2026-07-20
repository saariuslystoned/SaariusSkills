# Live variant picker

## Renderer choice

Prefer a captured, self-contained, development-only sidecar:

1. Build or serve the real project.
2. Capture the accepted layout.
3. Localize required styles, fonts, and assets.
4. Remove or isolate production behavior that corrupts the sidecar.
5. Inject one picker shell and one variant engine.
6. Express five candidates as deltas against the shared canvas.
7. Reuse the harness across slots and rounds.

Use a project-native development route when capture loses behavior material to
the decision. Fidelity and iteration cost matter more than one universal
renderer.

## Picker state

Represent:

- a stable round identifier;
- exactly five candidate identifiers;
- one active unresolved slot;
- locked slots and their selected values;
- the shared canvas reference;
- candidate delta references;
- target viewport and browser requirements.

Validate the state with `scripts/validate_picker.py` before use.

## Interaction

- Support keyboard, pointer, and mobile selection.
- Make candidate labels neutral.
- Keep the active slot obvious.
- Keep locked choices visible.
- Collapse or move picker chrome when it obscures a mobile viewport.
- Replay only the active motion slot when replay is offered.

## Hybrids

Do not generate or recommend hybrids. When the user explicitly describes a
precise hybrid, render it in cumulative context and ask for confirmation. Remove
the original five from the active picker while preserving their history. If the
request is ambiguous, clarify it or start a new round of exactly five with the
user’s direction.

## Verification

Inspect rendered screenshots directly. Test WebKit and Chromium when the target
product makes both relevant. Verify the real production result after selection;
the picker itself must not enter the production build.
