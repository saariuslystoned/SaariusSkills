import { test } from "../support/browser.mjs";
import { config } from "../support/env.mjs";
import { countStoreRequest, paceStore } from "../support/pace.mjs";
import { note } from "../support/proof.mjs";
import { consentsOf, installBody, installRefusal, namedInstalls, planInstalls, PUBLISHER_DID } from "../support/registry-install.mjs";
import { notePlugins, openAdmin } from "../support/store-admin.mjs";
import { BETA_STORE } from "../support/store-updates.mjs";
import { journey, step } from "../support/steps.mjs";

const API = () => `${config.store}/_emdash/api/admin/plugins`;
const HEADERS = { "X-EmDash-Request": "1", "Content-Type": "application/json" };
// EmDash gives the Registry and the download the same room an update gets.
const CALL_TIME = 180_000;
// Long enough that a person watching the Plugins page can read the list. A film sets DINKUS_E2E_VIDEO=1.
const FOLLOW = 2_000;

/** Verify or install, the posts the Registry detail page makes. A refusal names EmDash's code. */
async function postApi(page, path, data) {
  const url = `${API()}${path}`;
  await paceStore();
  countStoreRequest(url);
  const response = await page.context().request.post(url, { headers: HEADERS, data, maxRedirects: 0, timeout: CALL_TIME })
    .catch(error => error);
  if (response instanceof Error) throw new Error(`No answer from ${path} (${response.message.split("\n")[0]}).`);
  if (!response.ok()) throw new Error(installRefusal(response.status(), await response.json().catch(() => null)));
  return response.json().catch(() => ({}));
}

const listed = plan => plan.map(plugin => plugin.install
  ? `${plugin.name} ${plugin.version} (not installed)`
  : `${plugin.listing ?? plugin.name} ${plugin.installed} (already running)`).join(", ");

// Installs a DinkusKit beta the beta store does not already run. Update the store cannot: it only
// moves a plugin the store already runs. The Registry browse page loads its catalog from the
// aggregator in the browser, and this runner's request filter does not allow that origin, so this
// journey does not click through that page. It posts the same verify and install calls the Install
// button and Accept & Install send, then shows the result on Plugins. It never types a store key.
test("Install the Registry plugins", { tag: "@next" }, journey(async ({ page }) => {
  if (config.store !== BETA_STORE.store || config.siteId !== BETA_STORE.siteId) {
    throw new Error(`Only the beta store, ${BETA_STORE.store} (site ${BETA_STORE.siteId}), gets a Registry install; this run is set to ${config.store || "no store"} (site ${config.siteId || "not set"}).`);
  }
  let wanted;
  try { wanted = namedInstalls(process.env.DINKUS_E2E_INSTALL); } catch (error) { throw new Error(error.message); }

  let list;
  await step(page, "The owner can open Plugins", async () => {
    await openAdmin(page, `${config.store}/_emdash/admin/plugins-manager`);
    await page.waitForTimeout(FOLLOW);
    list = await notePlugins(page);
    if (!list) throw new Error("The store's plugin list couldn't be read.");
    return "Plugins opened";
  });

  let plan;
  await step(page, "See which named betas the store already runs", async () => {
    plan = planInstalls(list, wanted);
    note("registry install", listed(plan));
    return listed(plan);
  });

  for (const plugin of plan.filter(item => item.install)) {
    await step(page, `Install ${plugin.name} ${plugin.version}`, async () => {
      const verified = await postApi(page, "/registry/verify", { did: PUBLISHER_DID, slug: plugin.name, version: plugin.version });
      const body = installBody(verified);
      if (body.slug !== plugin.name || body.version !== plugin.version) {
        throw new Error(`Verify named ${body.slug} ${body.version}, not ${plugin.name} ${plugin.version}.`);
      }
      note(`registry install consents ${plugin.name}`, consentsOf(body));
      const installed = await postApi(page, "/registry/install", body);
      const id = installed?.data?.pluginId ?? installed?.pluginId;
      note("registry install id", id ? `${plugin.name} ${id}` : `${plugin.name} (id not in the answer)`);
      await openAdmin(page, `${config.store}/_emdash/admin/plugins-manager`);
      await page.waitForTimeout(FOLLOW);
      return `${plugin.name} ${plugin.version} installed`;
    });
  }

  await step(page, "Plugins lists each named beta", async () => {
    await paceStore();
    const after = await notePlugins(page);
    if (!after) throw new Error("The store's plugin list couldn't be read after the install.");
    const have = planInstalls(after, wanted);
    const missing = have.filter(plugin => plugin.install);
    if (missing.length) throw new Error(`Plugins still doesn't list ${missing.map(plugin => `${plugin.name} ${plugin.version}`).join(", ")}.`);
    const moved = have.filter(plugin => plugin.installed !== plugin.version && plan.find(item => item.name === plugin.name)?.install);
    if (moved.length) throw new Error(`Plugins lists ${moved.map(plugin => `${plugin.name} ${plugin.installed}, not ${plugin.version}`).join("; ")}.`);
    await page.waitForTimeout(FOLLOW);
    return have.map(plugin => `${plugin.name} ${plugin.installed}`).join(", ");
  });
}));
