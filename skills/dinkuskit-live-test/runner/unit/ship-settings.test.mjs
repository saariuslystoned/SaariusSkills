import assert from "node:assert/strict";
import test from "node:test";
import { pluginIdFromSettingsUrl, pluginSettingsPath, storeIdProblem } from "../support/ship-settings.mjs";

const store = "https://store.example";
const siteId = "858232f9-bc07-44f6-b3de-259a8055a9dd";

test("the settings path is EmDash's plugin-settings page, and it reads back the same plugin id", () => {
  for (const pluginId of ["r_x7k2", "did:plc:abc/dinkus-ship"]) {
    const path = pluginSettingsPath(pluginId);
    assert.equal(path.includes("//"), false);
    assert.equal(pluginIdFromSettingsUrl(path, store), pluginId);
    assert.equal(pluginIdFromSettingsUrl(`${store}${path}`, store), pluginId);
  }
});

test("only the settings form's address counts, not Shipping or another site", () => {
  const path = pluginSettingsPath("r_x7k2");
  for (const href of [
    `${store}/_emdash/admin/plugins/r_x7k2/shipping`,
    `${store}/_emdash/admin/plugins/r_x7k2`,
    `${store}/_emdash/admin/plugins-manager/r_x7k2`,
    `${store}${path}?token=secret`,
    `${store}${path}#key`,
    `https://other.example${path}`,
    "http://[not a url",
    "",
  ]) assert.equal(pluginIdFromSettingsUrl(href, store), null, href);
});

test("Store ID matches only the site id Commerce uses, and a mismatch is not repeated", () => {
  assert.equal(storeIdProblem(siteId, siteId), null);
  assert.equal(storeIdProblem(`  ${siteId}  `, siteId), null);
  const pasted = "sk_live_not_for_the_proof";
  const problem = storeIdProblem(pasted, siteId);
  assert.equal(problem.includes(pasted), false);
  assert.match(problem, /does not record the field/);
  assert.match(storeIdProblem("", siteId), /does not type it/);
  assert.match(storeIdProblem("   ", siteId), /does not type it/);
  assert.match(storeIdProblem(siteId, ""), /DINKUS_E2E_SITE_ID/);
});
