import { get, test } from "../support/browser.mjs";
import { config } from "../support/env.mjs";
import { countStoreRequest, paceStore, PAGE_ROOM } from "../support/pace.mjs";
import { notePlugins, openAdmin } from "../support/store-admin.mjs";
import { BETA_STORE, planUpdates, refusal } from "../support/store-updates.mjs";
import { journey, step } from "../support/steps.mjs";

const API = () => `${config.store}/_emdash/api/admin/plugins`;
const HEADERS = { "X-EmDash-Request": "1" };

/** EmDash's answer to an admin API GET, or an error naming the HTTP status. */
async function readApi(page, path) {
  const response = await get(page, `${API()}${path}`, { headers: HEADERS });
  if (!response.ok()) throw new Error(`The store answered HTTP ${response.status()} for /_emdash/api/admin/plugins${path}.`);
  return response.json();
}

const listed = plan => plan.map(p => `${p.name} ${p.installed}${p.update ? ` (newest ${p.latest})` : ""}${p.problem ? ` (${p.problem})` : ""}`).join(", ");

// Not one of the plan's journeys: it gets the beta store ready for them, and the Live journeys workflow
// runs it first (`npm run update-store`). It moves each DinkusKit beta plugin the store runs to the newest
// beta the Registry has, one at a time and in place, as the Update button on Plugins does, so the
// journeys test those. It agrees to nothing that button would ask the owner about: an update that asks
// for new permissions is refused, and the run stops for the owner to update it by hand.
test("Update the store", { tag: "@update" }, journey(async ({ page }) => {
  if (config.store !== BETA_STORE.store || config.siteId !== BETA_STORE.siteId) {
    throw new Error(`Only the beta store, ${BETA_STORE.store} (site ${BETA_STORE.siteId}), is updated before a run; this run is set to ${config.store || "no store"} (site ${config.siteId || "not set"}).`);
  }

  let plan;
  await step(page, "The owner can open Plugins", async () => {
    await openAdmin(page, `${config.store}/_emdash/admin/plugins-manager`);
    const list = await notePlugins(page);
    if (!list) throw new Error("The store's plugin list couldn't be read.");
    plan = planUpdates(list, await readApi(page, "/updates"));
    if (!plan.length) throw new Error("The store runs no DinkusKit beta plugin from the Registry.");
    const unchecked = plan.filter(p => p.problem);
    // A pass has to name the betas it really tested.
    if (unchecked.length) throw new Error(`The Registry couldn't be checked for ${unchecked.map(p => p.name).join(", ")}, so the newest betas aren't known.`);
    return listed(plan);
  });

  const updating = plan.filter(p => p.update);
  for (const plugin of updating) {
    await step(page, `Update ${plugin.name} to ${plugin.latest}`, async () => {
      const url = `${API()}/registry/${encodeURIComponent(plugin.id)}/update`;
      await paceStore();
      countStoreRequest(url);
      const response = await page.context().request.post(url, { headers: HEADERS, data: { version: plugin.latest }, maxRedirects: 0 });
      if (!response.ok()) throw new Error(`${plugin.name} stays on ${plugin.installed}, not ${plugin.latest}: ${refusal(response.status(), await response.json().catch(() => null))}.`);
      return `${plugin.name} updated from ${plugin.installed} to ${plugin.latest}`;
    });
  }

  await step(page, "The store runs the newest beta of each", async () => {
    await paceStore(PAGE_ROOM);
    await page.reload();
    const list = await notePlugins(page);
    if (!list) throw new Error("The store's plugin list couldn't be read after the update.");
    const now = planUpdates(list, { data: { items: plan.map(p => ({ pluginId: p.id, latest: p.latest })) } });
    // Each updated plugin shows its new version, and every other one the version it had.
    const wanted = new Map(plan.map(p => [p.id, p.update ? p.latest : p.installed]));
    const behind = now.filter(p => p.installed !== wanted.get(p.id));
    if (behind.length) throw new Error(`The store runs ${behind.map(p => `${p.name} ${p.installed}, not ${wanted.get(p.id) ?? "a version this run checked"}`).join("; ")}.`);
    return updating.length ? listed(now) : `${listed(now)}; each already the newest`;
  });
}));
