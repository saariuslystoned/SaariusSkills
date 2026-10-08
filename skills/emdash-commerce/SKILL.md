---
name: emdash-commerce
description: Research major EmDash/DinkusKit Commerce and companion-plugin product, domain, API, or data-model decisions against relevant ecommerce platforms before a GrillTrack proposal or lock. Excludes routine fixes and implementation of settled locks unless material new evidence calls for reopening.
---

# EmDash Commerce

Prepare a compact, source-linked decision comparison before proposing or confirming a material commerce decision. Support the existing GrillTrack cycle; do not create a competing lifecycle or decide for the user.

## Decide whether research is needed

Use for choices that change merchant behavior, sellable identity, ownership, public contracts, persisted models, checkout/fulfillment semantics, or compatibility across Commerce and companion plugins. Examples include catalog modeling, pricing authority, inventory integration, discount composition, order transitions, and agent-facing commerce contracts.

Skip competitor research for a typo, ordinary bug repair, refactor preserving contracts, or implementation under an existing lock. If fresh evidence conflicts with a lock, name the evidence and affected dependencies and route a scoped reopening through GrillTrack. A competitor feature alone is not a reason to reopen. Explicit user requests for comparison still apply within their scope.

## Establish the decision baseline

- Read applicable repository instructions, charter, the current `.grilltrack/ledger.json` if present, and only the relevant current types, callers, tests, and proof. Inspect companion repositories only when in scope. Name the repository, branch, commit/version and runtime lane; disclose stale checkouts or candidate-only evidence.
- Reuse the current decision packet and its owner. Distinguish implemented behavior, persisted locks, explicit user choices awaiting persistence, proposals, deferrals, and unknowns. Preserve accepted choices and authorization, including direct user updates newer than a packet. Surface a mismatch with durable state without silently overwriting either.
- State the focused question and constraints. Research discoverable facts before asking product questions. Do not turn a prior deferral, such as bundles, into a permanent prohibition or treat a partial module as approval for product adoption.

## Compare relevant platforms

Normally compare WooCommerce on WordPress, Shopify, and BigCommerce. Target 3–5 genuinely relevant platforms; add one or two for the domain, such as Adobe Commerce for complex catalog/B2B or commercetools for composable typed contracts. Explain substitutions briefly. Do not claim a market-share ranking. Read [references/source-map.md](references/source-map.md) when selecting official starting points.

Use current official documentation, API schemas and release notes for claims. Reuse prior research only after checking its freshness and relevance. Record the check date and named API/package version where available; pin moving `latest` links when practical. Distinguish core functionality, extensions/apps, plan or permission gates, beta, announced features and unverified availability. Undocumented is not proof of unsupported.

Research only dimensions that can change this decision. For each consequential claim, link the supporting page and identify limits. Separate platform facts from your inference for EmDash. When evidence is inaccessible, try a relevant official schema or alternate official page, then state the coverage gap and confidence. Never invent findings or add superficial comparators to meet a quota. If a material gap prevents a sound proposal, hand back the bounded unresolved question.

## Translate evidence to EmDash

Evaluate applicable tradeoffs, rather than copying a platform's vocabulary or architecture:

- **Identity and ownership:** distinguish editorial/publication identity, canonical sellable identity, mutable merchant labels/SKUs, and provider identifiers. Map who may validate, write and read each fact; inspect actual companion-plugin contracts.
- **Domain distinctions:** separate descriptive attributes, sellable items/variants, shopper choices, fulfillment requirements and composition when relevant. Compare where a choice affects identity, price, stock or only presentation. Do not prescribe one product model, default variant, inheritance rule, bundle policy or physical/digital classification without the current user's decision.
- **Runtime fit:** test the proposed shape against the pinned EmDash native versus Registry/sandbox contract, storage/CAS, host-attested authorization, route/public projections, Block Kit versus native admin, bundle limits and allowed capabilities as applicable. Separate desired architecture from host-supported and locally proved behavior; an injected fixture is not installed production support.
- **Migration and merchant UX:** explain handling of existing IDs, records and orders, backward compatibility, ambiguous legacy values, editor complexity and common merchant tasks. Keep unresolved defaults explicit instead of filling them in from competitor behavior.
- **Agent interoperability:** include current AI/agent capabilities only when relevant and supported by official evidence. Distinguish documentation-search MCP from storefront/action tools, protocol/schema readiness from implemented integration, and announced/beta features from available support. Agents and human UI should use typed shared validation, canonical identity, permissions and authoritative services. Search results or generated suggestions never become alternate pricing, stock, payment or order authority.

Respect current project boundaries: Commerce owns authoritative catalog price/sellability and checkout/order orchestration; physical stock truth belongs to the configured inventory provider. Confirm the active charter and locks before translating any companion ownership. Do not infer a second ledger, provider fallback, cross-plugin runtime access, grants or live integrations from a competitor example.

## Hand evidence back to GrillTrack

Deliver a short packet or scoped update to the existing packet:

1. Focused question, source baseline, accepted constraints and unresolved choices.
2. A comparison table: platform/version/status, relevant behavior with source links, practical tradeoff and coverage limit. Avoid feature catalogs.
3. **Adopt / adapt / defer / reject** recommendations for the relevant patterns, each with rationale, migration/runtime implications and the decision still needed. These labels describe recommendations, not GrillTrack lifecycle states.
4. A bounded proposed decision and affected dependencies, or an explicit material evidence gap. Mark which evidence would change the recommendation.

Use the installed GrillTrack skill for proposals, shared-understanding confirmation, locks, reopening and downstream verification. Its CLI alone maintains ledger/event state; never hand-edit either or duplicate their history here. If that workflow is unavailable, deliver research only and identify the missing transition. Preserve an existing mutation/packet owner; do not dispatch or create a second writer merely to attach research.

Stop when the focused comparison is sufficient. Research does not itself lock a decision, authorize implementation or close a track. Preserve unresolved choices and existing user authorization; this skill grants no merge, publishing/deploy, secret/permission change, purchase or external-send authority. Store only public-safe material in public repositories.
