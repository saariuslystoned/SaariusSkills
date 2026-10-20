import { get, test } from "../support/browser.mjs";
import { config } from "../support/env.mjs";
import { countStoreRequest, paceStore } from "../support/pace.mjs";
import { note } from "../support/proof.mjs";
import { notePlugins, openAdmin } from "../support/store-admin.mjs";
import { pluginVersion } from "../support/store-plugins.mjs";
import { aimAt, BETA_STORE, cantTest, namedBeta, notOffered, planUpdates, refusal } from "../support/store-updates.mjs";
import { journey, step } from "../support/steps.mjs";

const API = () => `${config.store}/_emdash/api/admin/plugins`;
const HEADERS = { "X-EmDash-Request": "1" };
// EmDash gives the Registry up to 30 seconds for each check, and an update up to 30 more for the
// Registry and 45 for the download before it stores and starts the new version.
const CHECK_TIME = 120_000;
const UPDATE_TIME = 180_000;
// How long a run started by a release waits for the Registry to offer the beta that release published.
const OFFER_WAIT = 15 * 60_000;
const OFFER_POLL = 30_000;
// Room for the sign-in, that wait and an update of each plugin.
const UPDATE_LIMIT = 45 * 60_000;

/** EmDash's answer to an admin API GET, or an error naming the HTTP status. */
async function readApi(page, path, options = {}) {
  await paceStore();
  const response = await get(page, `${API()}${path}`, { headers: HEADERS, ...options });
  if (!response.ok()) throw new Error(`The store answered HTTP ${response.status()} for /_emdash/api/admin/plugins${path}.`);
  return response.json();
}

/**
 * Fails the step with `reason`, which also goes in the run's public summary (as "update stopped"), since
 * it's what the owner needs to update by hand. It names plugins, versions and what an update asks for,
 * never anything secret.
 */
function stop(reason) {
  note("update stopped", reason);
  throw new Error(reason);
}

const listed = plan => plan.map(p => `${p.name} ${p.installed}${p.update ? ` (to ${p.latest})` : ""}${p.problem ? ` (${p.problem})` : ""}`).join(", ");

// Not one of the plan's journeys: it gets the beta store ready for them, and the Live journeys workflow
// runs it first (`npm run update-store`; other runs leave it out, see playwright.config.mjs). It moves
// each DinkusKit beta plugin the store runs to the newest beta the Registry has, one at a time and in
// place, as the Update button on Plugins does, so the journeys test those. It agrees to nothing that
// button would ask the owner about: an update that asks for new permissions is refused, and the run
// stops for the owner to update it by hand. A run a release started (DINKUS_E2E_BETA, the workflow's
// `beta` input) first waits for the Registry to offer the beta that release published, and installs
// exactly that one, even if a later beta is out.
test("Update the store", { tag: "@update" }, journey(async ({ page }) => {
  test.setTimeout(UPDATE_LIMIT);
  if (config.store !== BETA_STORE.store || config.siteId !== BETA_STORE.siteId) {
    throw new Error(`Only the beta store, ${BETA_STORE.store} (site ${BETA_STORE.siteId}), is updated before a run; this run is set to ${config.store || "no store"} (site ${config.siteId || "not set"}).`);
  }
  let beta;
  try { beta = namedBeta(process.env.DINKUS_E2E_BETA); } catch (error) { stop(error.message); }

  let list;
  await step(page, "The owner can open Plugins", async () => {
    await openAdmin(page, `${config.store}/_emdash/admin/plugins-manager`);
    list = await notePlugins(page);
    if (!list) throw new Error("The store's plugin list couldn't be read.");
    return "Plugins opened";
  });

  let plan;
  await step(page, beta ? `The Registry offers ${beta.name} ${beta.version}` : "Check the Registry for newer betas", async () => {
    const since = Date.now();
    for (;;) {
      plan = planUpdates(list, await readApi(page, "/updates", { timeout: CHECK_TIME }));
      if (!beta) break;
      const cant = cantTest(plan, beta);
      if (cant) stop(`The release named ${beta.name} ${beta.version}, but ${cant}.`);
      const waiting = notOffered(plan, beta);
      if (!waiting) {
        plan = aimAt(plan, beta);
        break;
      }
      // A release's own check reads the publisher's record, which the Registry lists a little later.
      if (Date.now() - since > OFFER_WAIT) stop(`After ${OFFER_WAIT / 60_000} minutes ${waiting}.`);
      await page.waitForTimeout(OFFER_POLL);
    }
    if (!plan.length) stop("The store runs no DinkusKit beta plugin from the Registry.");
    const unchecked = plan.filter(p => p.problem);
    // A pass has to name the betas it really tested.
    if (unchecked.length) stop(`EmDash's update check left out ${unchecked.map(p => p.name).join(", ")} (the Registry couldn't be reached, or its newest release was withdrawn), so the newest betas aren't known.`);
    return listed(plan);
  });

  const updating = plan.filter(p => p.update);
  for (const plugin of updating) {
    await step(page, `Update ${plugin.name} to ${plugin.latest}`, async () => {
      const url = `${API()}/registry/${encodeURIComponent(plugin.id)}/update`;
      await paceStore();
      countStoreRequest(url);
      const response = await page.context().request.post(url, { headers: HEADERS, data: { version: plugin.latest }, maxRedirects: 0, timeout: UPDATE_TIME })
        .catch(error => error);
      if (response instanceof Error) {
        // The store may still have finished, so say what it runs now.
        const now = await readApi(page, "", { timeout: CHECK_TIME }).then(body => pluginVersion(body, plugin.id), () => null);
        stop(`${plugin.name}'s update to ${plugin.latest} got no answer (${response.message.split("\n")[0]}); the store now runs ${plugin.name} ${now ?? "(couldn't read its version)"}.`);
      }
      if (!response.ok()) stop(`${plugin.name} stays on ${plugin.installed}, not ${plugin.latest}: ${refusal(response.status(), await response.json().catch(() => null))}.`);
      return `${plugin.name} updated from ${plugin.installed} to ${plugin.latest}`;
    });
  }

  await step(page, "The store runs the newest beta of each", async () => {
    // EmDash's plugin list reads each plugin's saved state, so it shows an update at once.
    await paceStore();
    const after = await notePlugins(page);
    if (!after) stop("The store's plugin list couldn't be read after the update.");
    // Each updated plugin shows its new version, and every other one the version it had.
    const wanted = p => p.update ? p.latest : p.installed;
    const behind = plan.filter(p => pluginVersion(after, p.id) !== wanted(p));
    if (behind.length) stop(`The store runs ${behind.map(p => `${p.name} ${pluginVersion(after, p.id) ?? "(no longer listed)"}, not ${wanted(p)}`).join("; ")}.`);
    const now = plan.map(p => ({ ...p, installed: wanted(p), update: false }));
    return updating.length ? listed(now) : `${listed(now)}; each already the newest`;
  });
}));
