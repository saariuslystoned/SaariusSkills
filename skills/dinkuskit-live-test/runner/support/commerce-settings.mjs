// Commerce's settings form is EmDash's auto-generated one (admin.settingsSchema in
// dinkuskit/commerce emdash-plugin.jsonc), not the plugin's own Commerce Settings page.
// Labels and descriptions are that schema: both are pasted from the Set up Commerce box.

export const CHECKOUT_SETTINGS = {
  label: "Checkout settings",
  description: "Paste from the Set up Commerce box on DinkusKit.com. Empty or switched off keeps checkout unavailable.",
};

export const STORE_KEY = {
  label: "Store key",
  description: "Paste from the Set up Commerce box on DinkusKit.com. Commerce trades it there for short passes to Payments and Ship; Replace key on DinkusKit.com stops this one.",
};

// The release listing and the beta listing are the same plugin. A store runs one of them.
const COMMERCE_SLUG = /^dinkus-commerce(-beta)?$/;

/** EmDash admin route for the auto-generated form: /plugins-manager/$pluginId/settings. */
export function commerceSettingsPath(id) {
  return `/_emdash/admin/plugins-manager/${encodeURIComponent(id)}/settings`;
}

/**
 * The Commerce plugin whose Settings control Plugins shows, from EmDash's plugin list
 * (GET /_emdash/api/admin/plugins). Anything else is an error and no path: the journey
 * stops instead of opening another plugin, switching Commerce on, or installing it.
 * The list names plugins, versions and ids, never a store key.
 */
export function commerceSettings(list) {
  const items = list?.data?.items;
  if (!Array.isArray(items)) return { error: "The store's plugin list couldn't be read." };
  const matches = items.filter(item => COMMERCE_SLUG.test(item?.registrySlug ?? ""));
  if (!matches.length) return { error: "The store doesn't run Commerce (dinkus-commerce or dinkus-commerce-beta)." };
  if (matches.length > 1) {
    return { error: `The store runs more than one Commerce plugin (${matches.map(item => item.registrySlug).join(", ")}).` };
  }
  const plugin = matches[0];
  const slug = plugin.registrySlug;
  const version = typeof plugin.version === "string" ? plugin.version : "(no version)";
  const named = `${slug} ${version}`;
  if (plugin.enabled === false) {
    return { error: `Commerce (${named}) is switched off, so Plugins doesn't show Settings for it. The test doesn't switch it on.` };
  }
  if (plugin.hasSettings !== true) return { error: `Commerce (${named}) has no settings form on Plugins.` };
  if (typeof plugin.id !== "string" || plugin.id === "") return { error: `Commerce (${named}) is listed without an id, so its settings page can't be opened.` };
  if (typeof plugin.name !== "string" || plugin.name === "") return { error: `Commerce (${named}) is listed without a name, so its card can't be picked out on Plugins.` };
  return { id: plugin.id, name: plugin.name, slug, version, path: commerceSettingsPath(plugin.id) };
}
