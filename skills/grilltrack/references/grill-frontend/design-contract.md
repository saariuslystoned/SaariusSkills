# Greenfield design contract

Require a durable design contract when GrillTrack is building a new website,
app, or other whole-product frontend from scratch. Default to `design.md` at the
repository root. When the repository already declares a canonical versioned or
nested design document, update that file and point to it from the repository's
front-door instructions instead of creating a competing root copy.

Create the contract before the first visual implementation that could become a
product default. It may begin with product intent, known constraints, and
explicitly unresolved directions. Do not infer a final visual language from a
neutral scaffold, framework starter, placeholder, or unselected candidate.

## Minimum contents

Keep the document useful to a future user or agent without reproducing the
ledger. Include:

- document version or update date, scope, and canonical-path declaration;
- product intent, audience, design principles, and hard constraints;
- provenance and references that materially influence the system;
- accepted directions and meaningful rejected or superseded directions;
- verified foundations such as color, typography, spacing, shape, elevation,
  layout, grid, breakpoints, and responsive behavior;
- component anatomy, states, interaction, accessibility, and content rules;
- imagery, iconography, motion, and asset status when those domains are known;
- unresolved design decisions and the GrillTrack decision or proof references
  needed to settle them;
- verification expectations for the real product surface.

Link to deeper assets, token sources, or component documentation rather than
copying large generated inventories into `design.md`.

## Cumulative update rule

After each verified visual cycle, update the design contract in the same
bounded implementation:

1. Promote the verified selection and its constraints into the contract.
2. Preserve meaningful rejected or superseded directions when they prevent
   later backsliding.
3. Keep still-unresolved domains labeled unresolved.
4. Reconcile contradictions with the ledger and real implementation.
5. Reference the applicable proof without embedding private or generated run
   output.

When a design decision is reopened, preserve its prior state and mark affected
contract sections provisional until the replacement is verified. The ledger
owns decision history; the design contract owns the current implementable
design language.

## Closeout rule

Do not cleanly close a greenfield whole-product frontend track when the
canonical design contract is missing or contradicts verified visual decisions.
If the product genuinely has no verified visual direction yet, the contract
must say so and retain only confirmed constraints; do not fabricate tokens or
components to make the document appear complete.

Do not impose this requirement on CLI, API, document, device, or bounded
maintenance cycles that are not establishing a new product-wide frontend.
