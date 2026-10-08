# URLs And Commerce

Use this reference when building an SEO-sound, agent-ready EmDash commerce
site. Verify behavior against the resolved EmDash version; these rules capture
the 1.2 URL behavior and the safer site-level workarounds.

## URL structure

- Never put `/` in an EmDash slug. EmDash 1.2's
  `interpolateUrlPattern` in `i18n/resolve.ts` applies `encodeURIComponent` to
  the whole slug, while matching assumes one segment per placeholder. Upstream
  tracked this as [emdash-cms/emdash #677](https://github.com/emdash-cms/emdash/pull/677).
  Keep one collection per URL prefix: `products` at
  `/products/{slug}`, `collections` at `/collections/{slug}`, `learn` at
  `/learn/{slug}`, and plain `pages` at `/{slug}`. The upstream portfolio
  template uses the same collection-per-prefix shape (`projects` at
  `/work/{slug}`).
- Avoid patching EmDash's hashed distribution bundles with `patch-package`;
  the patch breaks on upgrades. Report the upstream defect and work around it
  in the site.
- Give each product one canonical URL at `/products/{slug}`, never a
  category-nested product URL. Canonicalize alternate paths there. This matches
  [Google's ecommerce URL guidance](https://developers.google.com/search/docs/specialty/ecommerce/designing-a-url-structure-for-ecommerce-sites)
  and Shopify's model; WooCommerce commonly uses `/product/{slug}/`.
- Serve the homepage only at `/`. Redirect `/home` to `/` and omit `/home`
  from the sitemap; EmDash has no front-page setting, and the upstream
  marketing template 301s `home.astro`.
- Choose one trailing-slash policy (for example `trailingSlash: "never"`).
  Links, sitemap locations, redirects and canonical tags must agree.
- Use EmDash's built-in sitemap and `robots.txt`. Do not create a custom
  replacement: an upstream `hasUserDefinedPublicRoute` check can cause it to
  override the built-in behavior.

## Product data for agents

- Every product has a permanent Commerce SKU/itemId that never changes. The
  slug is only a URL; feeds, orders, structured data and future agent
  integrations key on the permanent ID.
- Every product page emits schema.org `Product`/`Offer` JSON-LD matching the
  visible page: name, SKU, GTIN when available, price, availability,
  `shippingDetails`, and `hasMerchantReturnPolicy`.
- Define shipping and return policies once. Both rendered policy pages and
  product structured data read that shared source.
- Export product data as a feed for Google Merchant Center and Meta Catalog,
  with enough stable fields to support later agent catalogs such as OpenAI ACP
  or Google UCP without rebuilding the product model.
- Record allowed channels on every product. Feeds and integrations read explicit
  eligibility rather than guessing from category or slug. Verify current platform
  policies and the merchant's product restrictions before enabling a channel.

## Safe redirects and proof

- Test a new redirect as a 302 first. Once confirmed, promote it through
  EmDash's redirect table; never cache a permanent redirect as `immutable` or
  with an unnecessarily long max-age.
- Maintain a route inventory and repeatable checks as described in
  [site verification](verification.md). Follow the project's deployment gates.
