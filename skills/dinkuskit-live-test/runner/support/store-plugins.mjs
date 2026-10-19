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

/** The version of the plugin with runtime id `id` (r_...) in EmDash's admin plugin list; null when the list doesn't have it. */
export function pluginVersion(body, id) {
  const item = (body?.data?.items ?? []).find(entry => entry.id === id);
  return typeof item?.version === "string" ? item.version : null;
}

/**
 * Whether `version` ("0.3.0-beta.4", "0.3.0") is `floor` or later. A release comes after its betas;
 * a version it can't read is never late enough.
 */
export function versionAtLeast(version, floor) {
  const parse = value => {
    const [, major, minor, patch, beta] = String(value).match(/^(\d+)\.(\d+)\.(\d+)(?:-beta\.(\d+))?$/) ?? [];
    return major === undefined ? null : [major, minor, patch, beta ?? Infinity].map(Number);
  };
  const [have, need] = [parse(version), parse(floor)];
  if (!have || !need) return false;
  for (let i = 0; i < have.length; i++) if (have[i] !== need[i]) return have[i] > need[i];
  return true;
}
