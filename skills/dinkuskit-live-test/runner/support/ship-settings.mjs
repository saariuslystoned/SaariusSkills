// Ship's settings, as EmDash's auto-generated form renders dinkuskit/ship emdash-plugin.jsonc
// admin.settingsSchema (emdash packages/admin/src/components/PluginSettings.tsx on main).
// siteId is "Store ID", a string. storeKey is "Store key", a secret: the form's password
// field stays empty, and the server never sends the stored key back.

export const SHIP_PLUGIN_NAME = "Ship";
export const STORE_ID_LABEL = "Store ID";
export const STORE_KEY_LABEL = "Store key";

// packages/admin/src/lib/plugin-links.ts kind "plugin-settings", under the admin basepath.
const SETTINGS_PATH = /^\/_emdash\/admin\/plugins-manager\/([^/]+)\/settings$/;

/** The settings form's path for a plugin id. The id is one path segment, so slashes are encoded. */
export function pluginSettingsPath(pluginId) {
  return `/_emdash/admin/plugins-manager/${encodeURIComponent(pluginId)}/settings`;
}

/**
 * The plugin id in a settings-form address on `store`, or null. Other admin pages (a plugin's own
 * pages, Shipping) are not this form. A query or hash is not this form either.
 */
export function pluginIdFromSettingsUrl(href, store) {
  if (!href || !store) return null;
  let url;
  let origin;
  try {
    origin = new URL(store).origin;
    url = new URL(href, origin);
  } catch {
    return null;
  }
  if (url.origin !== origin || url.search || url.hash) return null;
  const match = SETTINGS_PATH.exec(url.pathname);
  if (!match) return null;
  try {
    return decodeURIComponent(match[1]);
  } catch {
    return null;
  }
}

/**
 * Null when `shown` is the site id Commerce uses. Otherwise a problem that does not repeat `shown`,
 * so a value that is not the site id (including anything pasted into the wrong field) stays out of
 * the proof.
 */
export function storeIdProblem(shown, siteId) {
  const value = typeof shown === "string" ? shown.trim() : "";
  if (!siteId) return "Set DINKUS_E2E_SITE_ID to the store's DinkusKit site id.";
  if (value === siteId) return null;
  if (!value) return "Store ID is empty. It is the site id from the Set up Commerce box on DinkusKit.com, the same one Commerce uses. The test does not type it.";
  return "Store ID is not the site id Commerce uses. The test does not record the field or change it.";
}
