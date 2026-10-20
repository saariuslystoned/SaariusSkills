import { versionAtLeast } from "./store-plugins.mjs";

// The publisher on the Payments and Ship manifests. A listing from anyone else is not this journey.
export const PUBLISHER_DID = "did:plc:ekk4pjmkh3k3ql2kfoex3qt4";

// Same shape as a beta listing in store-updates.mjs. A release listing is never installed here.
const BETA_LISTING = /^dinkus-[a-z0-9-]+-beta$/;

// What this journey installs when DINKUS_E2E_INSTALL is unset: the Ship beta that listing-passed.
const SHIP_BETA = "dinkus-ship-beta 0.1.0-beta.0";

/**
 * The betas to install, from "dinkus-ship-beta 0.1.0-beta.0" or several separated by commas.
 * An empty value is the Ship beta above.
 */
export function namedInstalls(text) {
  const value = String(text ?? "").trim() || SHIP_BETA;
  return value.split(",").map(part => {
    const item = part.trim();
    const [, name, version] = item.match(/^(\S+)[ @](\S+)$/) ?? [];
    if (!BETA_LISTING.test(name ?? "") || !versionAtLeast(version, "0.0.0-0")) {
      throw new Error(`"${item}" doesn't name a DinkusKit beta as "dinkus-<plugin>-beta <version>".`);
    }
    return { name, version };
  });
}

/**
 * Which of `wanted` the store does not already run, from EmDash's plugin list. One the store
 * already runs is left as it is, whichever version that is. This journey does not update or
 * downgrade. A plugin the owner switched off still counts as present, so it is not installed twice.
 */
export function planInstalls(list, wanted) {
  const items = list?.data?.items ?? [];
  return wanted.map(plugin => {
    const found = items.find(item => item.source === "registry" && item.registrySlug === plugin.name);
    if (!found) return { ...plugin, install: true };
    return { ...plugin, install: false, id: found.id, installed: found.version };
  });
}

/**
 * The body Accept & Install posts, from the verify route's answer. Verify is what the Install
 * button posts first. The fields are the permissions and signed-record ids the consent dialog shows.
 */
export function installBody(verified) {
  const data = verified?.data ?? verified;
  const verification = data?.verification;
  if (typeof data?.publisherDid !== "string" || typeof data?.slug !== "string" || typeof data?.version !== "string") {
    throw new Error("Verify didn't name the plugin.");
  }
  if (!Array.isArray(data.capabilities)) throw new Error("Verify didn't list the permissions the consent dialog shows.");
  if (typeof verification?.profileCid !== "string" || typeof verification?.releaseCid !== "string") {
    throw new Error("Verify didn't return the signed record ids the consent dialog shows.");
  }
  return {
    did: data.publisherDid,
    slug: data.slug,
    version: data.version,
    acknowledgedDeclaredAccess: data.capabilities,
    acknowledgedMcpTools: Array.isArray(data.mcpTools) ? data.mcpTools : [],
    acknowledgedPublicRoutes: Array.isArray(data.publicRoutes) ? data.publicRoutes : [],
    acknowledgedProfileCid: verification.profileCid,
    acknowledgedReleaseCid: verification.releaseCid,
  };
}

/** Why EmDash refused verify or install, from its HTTP status and error body. */
export function installRefusal(status, body) {
  const { code, message } = body?.error ?? {};
  return code ? `EmDash said ${code}${message ? `: ${message}` : ""} (HTTP ${status})` : `the store answered HTTP ${status}`;
}
