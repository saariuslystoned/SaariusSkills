/**
 * The plugins a store runs, as "dinkus-commerce 0.2.2, dinkus-payments 0.2.8", from the body of
 * EmDash's admin plugin list (GET /_emdash/api/admin/plugins). Registry plugins go by their
 * Registry slug, so a beta install (dinkus-commerce-beta) reads differently from the release.
 */
export function describePlugins(body) {
  const items = body?.data?.items;
  if (!Array.isArray(items)) throw new Error("the plugin list has no items");
  const running = items.filter(item => item.enabled !== false);
  return running.map(item => `${item.registrySlug || item.name || item.id} ${item.version ?? "(no version)"}`).join(", ") || "none";
}
