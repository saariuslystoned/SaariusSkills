# Linux label-PDF renderer qualification

Base: bdd71b7bb1f113a288d12223fccff7a2f26e1e58, current canonical main.
Branch: codex/dinkuskit-linux-label-pdf-20261018.

The canonical Buy and ship PDF step now renders the first page with Poppler's
pdftoppm on Linux and retains Quick Look on macOS. It checks the PNG signature
and nonzero dimensions, records dimensions/SHA256, and fails clearly when the
renderer is missing or does not produce a picture. It no longer silently omits
visual proof outside macOS. The journey uses the same downloaded label PDF;
no journey fork, store change or provider call was introduced.

25 offline Node tests pass, including5 renderer tests for Linux argv/time limit,
macOS behavior, missing renderer, absent/invalid/stale output and invalid input.

The exact proposed helper was copied to a disposable Linux proof directory
and executed by Node with system pdftoppm. It rendered a source-independent
synthetic sandbox PDF to934×1400 PNG. Input/helper/output hashes were compared
with local files. Visual inspection confirms legible sandbox warning, address
block and barcode-like bars, with no clipping. The fixture explicitly says
NOT VALID FOR SHIPPING. No real order, postage, tracking or provider was used.

Immutable synthetic evidence:
https://github.com/saari-co/public-oss-proof-assets/releases/tag/canonical-linux-label-20261018

The release holds sandbox-label.pdf, sandbox-label.pdf.png and asset-manifest.json
with source hash, provenance, dimensions, sizes and redaction statement.
Raw local run: runs/linux-label-pdf-runs/20261018/.

This qualifies PDF rasterization only. A real Pitney Bowes sandbox label and its
canonical Buy and ship journey still need later authorized live proof. Human
merge approval and exact-head review remain required.
