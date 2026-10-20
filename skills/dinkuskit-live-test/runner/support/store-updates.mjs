import { versionAtLeast } from "./store-plugins.mjs";

// The only store a run may update: the beta store runs the newest betas, and every other test store
// stays on what its owner put there.
export const BETA_STORE = { store: "https://beta.sm0ky.dev", siteId: "858232f9-bc07-44f6-b3de-259a8055a9dd" };

// A DinkusKit plugin's beta listing (dinkus-commerce-beta). Each listing keeps its own storage, so a
// plugin is only ever moved along its own listing, never switched to the release one.
const BETA_LISTING = /^dinkus-[a-z0-9-]+-beta$/;

/**
 * What to do with each DinkusKit beta plugin the store runs, from EmDash's plugin list
 * (GET /_emdash/api/admin/plugins) and its update check (GET /_emdash/api/admin/plugins/updates):
 * `update` to the newer `latest` the Registry has of that listing, or keep it. EmDash leaves a plugin
 * out of its update check when it can't ask the Registry about it or its newest release was withdrawn,
 * and lists none when the Registry is down, so such a plugin carries a `problem` instead of passing for
 * up to date. A plugin the owner switched off is left off: EmDash's update would switch it back on.
 */
export function planUpdates(list, updates) {
  const checks = new Map((updates?.data?.items ?? []).map(item => [item.pluginId, item]));
  return (list?.data?.items ?? [])
    .filter(item => item.source === "registry" && item.enabled !== false && BETA_LISTING.test(item.registrySlug ?? ""))
    .map(item => {
      const plugin = { id: item.id, name: item.registrySlug, installed: item.version };
      const latest = checks.get(item.id)?.latest;
      if (typeof latest !== "string" || !latest) return { ...plugin, problem: "EmDash's update check left it out (the Registry couldn't be reached, or its newest release was withdrawn)" };
      // EmDash offers any version that differs, so a Registry whose newest is older is never followed back down.
      return { ...plugin, latest, update: latest !== item.version && versionAtLeast(latest, item.version) };
    });
}

// What EmDash's own Update button asks the owner about first. The run never agrees to any of it.
const ASKS = {
  CAPABILITY_ESCALATION: details => `it asks for new permissions (${(details?.capabilityChanges?.added ?? []).join(", ") || "not named"})`,
  ROUTE_VISIBILITY_ESCALATION: details => `it opens routes to visitors who aren't signed in (${(details?.routeVisibilityChanges?.newlyPublic ?? []).join(", ") || "not named"}), which the beta store's Access app also needs an exception for`,
  MCP_TOOL_CONSENT_REQUIRED: () => "it changes the tools it offers agents",
  RECORD_CONSENT_REQUIRED: () => "it asks to confirm its publisher's signed records",
  RECORD_VERIFICATION_DRIFT: () => "its publisher's signed records changed",
};

/** Why EmDash refused an update, from its HTTP status and error body. */
export function refusal(status, body) {
  const { code, message, details } = body?.error ?? {};
  if (ASKS[code]) return `${ASKS[code](details)}; update it by hand from Plugins once you've read what it asks`;
  return code ? `EmDash said ${code}${message ? `: ${message}` : ""} (HTTP ${status})` : `the store answered HTTP ${status}`;
}

/**
 * The beta a release just published, from "dinkus-payments-beta 0.2.9-beta.3" (or with "@"), as the
 * Live journeys workflow's `beta` input names it; null when none is named.
 */
export function namedBeta(text) {
  const value = String(text ?? "").trim();
  if (!value) return null;
  const [, name, version] = value.match(/^(\S+)[ @](\S+)$/) ?? [];
  if (!BETA_LISTING.test(name ?? "") || !versionAtLeast(version, "0.0.0-0")) throw new Error(`"${value}" doesn't name a DinkusKit beta as "dinkus-<plugin>-beta <version>".`);
  return { name, version };
}

/** Why `plan` doesn't offer the named beta yet, or null once the Registry has it (or a later one). */
export function notOffered(plan, beta) {
  const plugin = plan.find(p => p.name === beta.name);
  if (!plugin) return `the store doesn't run ${beta.name}`;
  if (versionAtLeast(plugin.installed, beta.version) || (plugin.latest && versionAtLeast(plugin.latest, beta.version))) return null;
  return `the Registry offers ${beta.name} ${plugin.latest ?? "nothing"}, not ${beta.version} yet`;
}
