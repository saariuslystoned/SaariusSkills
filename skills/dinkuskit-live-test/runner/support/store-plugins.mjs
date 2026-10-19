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
 * Whether `version` ("0.3.0-beta.4", "0.3.0-rc.1", "0.3.0") is `floor` or later, in semver's order: a
 * release comes after its pre-releases, whose parts compare one by one, numbers as numbers and before
 * words, and build details after "+" don't count. A version that isn't semver is never late enough.
 */
export function versionAtLeast(version, floor) {
  const parse = value => {
    const [, core, pre] = String(value).match(/^(\d+\.\d+\.\d+)(?:-([0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?$/) ?? [];
    return core === undefined ? null : { core: core.split(".").map(Number), pre: pre?.split(".") ?? [] };
  };
  const [have, need] = [parse(version), parse(floor)];
  if (!have || !need) return false;
  for (let i = 0; i < 3; i++) if (have.core[i] !== need.core[i]) return have.core[i] > need.core[i];
  if (!have.pre.length || !need.pre.length) return !have.pre.length;
  for (let i = 0; i < Math.max(have.pre.length, need.pre.length); i++) {
    const [mine, theirs] = [have.pre[i], need.pre[i]];
    // With every part before it equal, the pre-release with fewer parts comes first.
    if (mine === undefined || theirs === undefined) return theirs === undefined;
    if (mine === theirs) continue;
    const [mineNumber, theirsNumber] = [/^\d+$/.test(mine), /^\d+$/.test(theirs)];
    if (mineNumber && theirsNumber) return Number(mine) > Number(theirs);
    return mineNumber || theirsNumber ? theirsNumber : mine > theirs;
  }
  return true;
}
