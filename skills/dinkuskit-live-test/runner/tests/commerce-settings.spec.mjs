import { test, expect } from "../support/browser.mjs";
import { CHECKOUT_SETTINGS, STORE_KEY, commerceSettings } from "../support/commerce-settings.mjs";
import { config } from "../support/env.mjs";
import { note } from "../support/proof.mjs";
import { notePlugins, openAdmin } from "../support/store-admin.mjs";
import { journey, step } from "../support/steps.mjs";

// Checkout settings is pasted setup text, and the Store key is write-only. A trace would keep the
// settings response, so this journey keeps none. It never types, clears or saves either field.
test.use({ trace: "off" });

// Playwright's failure notes include the open page. Leave a blank one, as the label journey does.
test.afterEach(async ({ page }) => {
  await page.goto("about:blank").catch(() => {});
});

const settingsWrite = (request, id) => {
  if (request.method() === "GET" || request.method() === "HEAD") return false;
  let path;
  try { path = decodeURIComponent(new URL(request.url()).pathname); } catch { return false; }
  return path === `/_emdash/api/admin/plugins/${id}/settings`;
};

/** Empties the form's fields in the page only, so a screenshot can't keep a pasted value. Nothing is saved. */
async function blankFields(page) {
  await page.locator("#plugin-settings-form").locator("input, textarea").evaluateAll(fields => {
    for (const field of fields) field.value = "";
  });
}

// The owner opens Commerce's settings from Plugins. The Store key field is shown empty and left alone.
test("Commerce settings", { tag: "@next" }, journey(async ({ page }) => {
  expect(config.store, `Set DINKUS_E2E_STORE to the store's address (in ${config.settingsFile})`).not.toBe("");
  let plugin;

  await step(page, "The owner can open Plugins", async () => {
    await openAdmin(page, `${config.store}/_emdash/admin/plugins-manager`);
    const found = commerceSettings(await notePlugins(page));
    if (found.error) throw new Error(found.error);
    plugin = found;
    note("commerce settings plugin", `${plugin.slug} ${plugin.version}`);
    return `${plugin.slug} ${plugin.version} is on, with settings`;
  });

  await step(page, "Commerce settings opens from Plugins, with Checkout settings and an empty Store key", async () => {
    const writes = [];
    const onRequest = request => { if (settingsWrite(request, plugin.id)) writes.push(request.method()); };
    page.on("request", onRequest);
    try {
      // PluginManager renders this gear only when the plugin is on and has settings. Its href is
      // /plugins-manager/$pluginId/settings. The card is the plugin's own heading plus that link.
      const heading = page.getByRole("heading", { level: 3, name: plugin.name, exact: true });
      const cards = await heading.count();
      if (cards !== 1) throw new Error(`Plugins shows ${cards} cards named "${plugin.name}", not one.`);
      const row = page.locator("div").filter({ has: heading }).filter({ has: page.getByRole("link", { name: "Settings", exact: true }) }).last();
      const gear = row.getByRole("link", { name: "Settings", exact: true });
      if (await gear.count() !== 1) throw new Error("Plugins doesn't show Commerce's Settings control.");
      const href = decodeURIComponent(await gear.getAttribute("href") ?? "");
      if (!href.includes(`/plugins-manager/${plugin.id}/settings`)) throw new Error("Commerce's Settings control doesn't open its settings page.");
      await gear.click();
      const form = page.locator("#plugin-settings-form");
      await form.waitFor();
      const storeKey = form.getByLabel(STORE_KEY.label);
      const keyShown = await storeKey.count() === 1;
      const keyType = keyShown ? await storeKey.getAttribute("type") : null;
      const keyEmpty = keyShown ? (await storeKey.inputValue()) === "" : false;
      const placeholder = keyShown ? await storeKey.getAttribute("placeholder") : null;
      // Blank before any later check can fail: the step's screenshot is this page.
      await blankFields(page);
      if (decodeURIComponent(new URL(page.url()).pathname) !== plugin.path) throw new Error("Commerce's Settings control didn't open its settings page.");
      if (writes.length) throw new Error("Commerce settings was written. The test does not save.");
      if (!keyShown) throw new Error("The Store key field is not on the form.");
      if (keyType !== "password") throw new Error("Store key is not a password field, so this step stopped before keeping it.");
      if (!keyEmpty) throw new Error("The Store key field was not empty. Nothing was typed or saved.");
      if (placeholder?.includes("Will be cleared")) throw new Error("Store key is marked to be cleared. The test doesn't change it.");
      const checkout = form.getByLabel(CHECKOUT_SETTINGS.label);
      if (await checkout.count() !== 1) throw new Error("Checkout settings is not on the form.");
      if (await checkout.getAttribute("type") === "password") throw new Error("Checkout settings is a password field.");
      if (!await form.getByText(CHECKOUT_SETTINGS.description, { exact: true }).isVisible()) throw new Error("Checkout settings doesn't show its Set up Commerce description.");
      if (!await form.getByText(STORE_KEY.description, { exact: true }).isVisible()) throw new Error("Store key doesn't show its Set up Commerce description.");
      const headingName = `${plugin.name} Settings`;
      if (await page.getByRole("heading", { level: 1, name: headingName, exact: true }).count() !== 1) throw new Error(`The page isn't headed "${headingName}".`);
      if (await page.getByRole("button", { name: "Save Settings" }).count() < 1) throw new Error("Save Settings isn't on the form. Nothing was saved.");
      const stored = placeholder?.includes("Currently set") ? "A store key is already stored."
        : placeholder?.includes("Not set") ? "No store key is stored."
          : "The Store key field is empty.";
      return `Checkout settings is on the form. The Store key field is empty. ${stored}`
    } finally {
      page.off("request", onRequest);
    }
  });
}));
