import { expect, test } from "../support/browser.mjs";
import { config } from "../support/env.mjs";
import { PAGE_ROOM, paceStore } from "../support/pace.mjs";
import { note } from "../support/proof.mjs";
import {
  SHIP_PLUGIN_NAME, STORE_ID_LABEL, STORE_KEY_LABEL, pluginIdFromSettingsUrl, pluginSettingsPath, storeIdProblem,
} from "../support/ship-settings.mjs";
import { openAdmin } from "../support/store-admin.mjs";
import { journey, step } from "../support/steps.mjs";

// EmDash draws this form from admin.settingsSchema (packages/admin/src/components/PluginSettings.tsx).
// Plugins lists an enabled plugin's Settings link to /plugins-manager/$pluginId/settings
// (PluginManager.tsx). The secret field is a password input whose value stays empty. This journey
// never types, saves, or clears a setting, and it never buys a label. It leaves a blank page for
// Playwright's failure notes, as Commerce settings does.
test.afterEach(async ({ page }) => {
  await page.goto("about:blank").catch(() => {});
});

test("Ship settings", { tag: "@next" }, journey(async ({ page }) => {
  expect(config.store, `Set DINKUS_E2E_STORE to the store's address (in ${config.settingsFile})`).not.toBe("");
  expect(config.siteId, `Set DINKUS_E2E_SITE_ID to the store's DinkusKit site id (in ${config.settingsFile})`).not.toBe("");
  const soft = { soft: true };

  // Without the form there is nothing to read, so this step stops the journey.
  await step(page, "The owner opens Ship settings from Plugins", async () => {
    try {
      await paceStore(PAGE_ROOM);
      await openAdmin(page, `${config.store}/_emdash/admin/plugins-manager`);
      const ship = page.getByRole("heading", { level: 3, name: SHIP_PLUGIN_NAME });
      const empty = page.getByRole("heading", { name: "No plugins configured", exact: true });
      const failed = page.getByText(/^Failed to load plugins/);
      await ship.or(empty).or(failed).first().waitFor({ timeout: 30_000 }).catch(() => {});
      if (await failed.count()) throw new Error("Plugins did not load. The test does not install or change anything.");
      if (await empty.count() && !await ship.count()) throw new Error("Plugins has no plugins, so Ship's settings are not there.");
      const shipCount = await ship.count();
      if (shipCount !== 1) {
        throw new Error(shipCount
          ? `Plugins lists ${shipCount} Ship plugins; the test will not pick one.`
          : "Plugins has no Ship or Ship Beta plugin. The test does not install one.");
      }
      const opened = await shipSettingsLink(page);
      if (!opened) {
        throw new Error("Ship is listed, but no Settings control opens /_emdash/admin/plugins-manager/<plugin>/settings. The test does not enable the plugin or change its settings.");
      }
      const shipName = (await ship.innerText()).trim();
      await opened.link.click();
      await page.locator("#plugin-settings-form").waitFor({ timeout: 30_000 });
      await page.getByRole("heading", { name: `${shipName} Settings`, exact: true }).waitFor();
      const pluginId = pluginIdFromSettingsUrl(page.url(), config.store);
      if (pluginId !== opened.pluginId) throw new Error("Ship's Settings control opened a different page than its own settings form.");
      note("ship settings plugin", pluginId);
      return pluginSettingsPath(pluginId);
    } finally {
      await blankPasswordFields(page);
    }
  });

  await step(page, "Store ID is the site id Commerce uses", async () => {
    try {
      const field = page.getByLabel(STORE_ID_LABEL, { exact: true });
      if ((await field.count()) !== 1) throw new Error(`Ship settings has no single ${STORE_ID_LABEL} field.`);
      const problem = storeIdProblem(await field.inputValue(), config.siteId);
      if (problem) {
        await field.evaluate(input => { input.value = ""; });
        throw new Error(problem);
      }
      return "Store ID is the site id Commerce uses";
    } finally {
      await blankPasswordFields(page);
    }
  }, soft);

  await step(page, "Store key is a visible empty field", async () => {
    try {
      const field = page.getByLabel(STORE_KEY_LABEL, { exact: true });
      if ((await field.count()) !== 1) throw new Error(`Ship settings has no single ${STORE_KEY_LABEL} field.`);
      if (!await field.isVisible()) throw new Error("Store key field is not visible.");
      // The value stays in the page. Only a yes/no comes back, so the proof never receives the key.
      const emptyPassword = await field.evaluate(input =>
        input instanceof HTMLInputElement && input.type === "password" && input.value === "");
      if (!emptyPassword) throw new Error("Store key must be a visible empty password field. The test does not type, save, or record it.");
      return "Store key field is empty";
    } finally {
      await blankPasswordFields(page);
    }
  }, soft);
}));

/** Ship's Settings link, when it points at EmDash's settings form. Null when Ship has no such link. */
async function shipSettingsLink(page) {
  const found = [];
  for (const link of await page.getByRole("link", { name: "Settings", exact: true }).all()) {
    const pluginId = pluginIdFromSettingsUrl(await link.getAttribute("href"), config.store);
    if (!pluginId) continue;
    const card = link.locator("xpath=ancestor::*[.//h3][1]");
    const named = card.getByRole("heading", { level: 3, name: SHIP_PLUGIN_NAME });
    if (await named.count() === 1) found.push({ link, pluginId });
  }
  if (found.length > 1) throw new Error(`Plugins has ${found.length} Ship settings links; the test will not pick one.`);
  return found[0] ?? null;
}

/** Clears password fields in the page, without an input event, so a screenshot cannot show a store key. */
async function blankPasswordFields(page) {
  await page.locator("input[type='password']").evaluateAll(inputs => {
    for (const input of inputs) input.value = "";
  }).catch(() => {});
}
