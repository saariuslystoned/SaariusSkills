import assert from "node:assert/strict";
import test from "node:test";
import { namedBeta, notOffered, planUpdates, refusal } from "../support/store-updates.mjs";

const list = items => ({ data: { items } });
const commerce = { id: "r_commerce", source: "registry", registrySlug: "dinkus-commerce-beta", version: "0.3.0-beta.9" };
const payments = { id: "r_payments", source: "registry", registrySlug: "dinkus-payments-beta", version: "0.2.9-beta.1" };

test("only DinkusKit beta listings from the Registry are planned; a release listing or anything else is left alone", () => {
  const plan = planUpdates(list([
    commerce,
    { id: "r_stable", source: "registry", registrySlug: "dinkus-ship", version: "0.1.0" },
    { id: "r_other", source: "registry", registrySlug: "someone-beta", version: "1.0.0-beta.1" },
    { id: "forms", source: "config", name: "forms", version: "1.0.0" },
  ]), list([{ pluginId: "r_commerce", latest: "0.3.0-beta.10" }, { pluginId: "r_stable", latest: "0.2.0" }]));
  assert.deepEqual(plan, [{ id: "r_commerce", name: "dinkus-commerce-beta", installed: "0.3.0-beta.9", latest: "0.3.0-beta.10", update: true }]);
});

test("a beta plugin the owner switched off is left off", () => {
  const plan = planUpdates(list([{ ...commerce, enabled: false }, payments]), list([
    { pluginId: "r_commerce", latest: "0.3.0-beta.10" }, { pluginId: "r_payments", latest: "0.2.9-beta.2" },
  ]));
  assert.deepEqual(plan.map(p => p.name), ["dinkus-payments-beta"]);
});

test("a release names its beta, and the run waits until the Registry offers it or a later one", () => {
  assert.deepEqual(namedBeta(" dinkus-payments-beta 0.2.9-beta.3 "), { name: "dinkus-payments-beta", version: "0.2.9-beta.3" });
  assert.deepEqual(namedBeta("dinkus-commerce-beta@0.3.1-beta.0"), { name: "dinkus-commerce-beta", version: "0.3.1-beta.0" });
  assert.equal(namedBeta(""), null);
  for (const bad of ["dinkus-payments 0.2.9", "dinkus-payments-beta latest", "someone-beta 1.0.0", "dinkus-payments-beta"]) assert.throws(() => namedBeta(bad), /doesn't name a DinkusKit beta/);
  const beta = { name: "dinkus-payments-beta", version: "0.2.9-beta.3" };
  const plan = latest => planUpdates(list([commerce, payments]), list([{ pluginId: "r_commerce", latest: "0.3.0-beta.9" }, { pluginId: "r_payments", latest }]));
  assert.equal(notOffered(plan("0.2.9-beta.2"), beta), "the Registry offers dinkus-payments-beta 0.2.9-beta.2, not 0.2.9-beta.3 yet");
  assert.equal(notOffered(plan("0.2.9-beta.3"), beta), null);
  assert.equal(notOffered(plan("0.2.9-beta.10"), beta), null);
  assert.equal(notOffered(plan("0.2.9-beta.1"), { ...beta, version: "0.2.9-beta.1" }), null);
  assert.equal(notOffered(plan("0.2.9-beta.3"), { name: "dinkus-ship-beta", version: "0.1.0-beta.0" }), "the store doesn't run dinkus-ship-beta");
});

test("an update goes only forward in semver order, never back down to an older Registry version", () => {
  const plan = planUpdates(list([commerce, payments]), list([
    { pluginId: "r_commerce", latest: "0.3.0-beta.8", hasUpdate: true },
    { pluginId: "r_payments", latest: "0.2.9-beta.1", hasUpdate: false },
  ]));
  assert.deepEqual(plan.map(p => [p.name, p.update]), [["dinkus-commerce-beta", false], ["dinkus-payments-beta", false]]);
});

test("a beta plugin the update check left out can't pass for up to date", () => {
  const plan = planUpdates(list([commerce, payments]), list([{ pluginId: "r_payments", latest: "0.2.9-beta.2" }]));
  assert.match(plan[0].problem, /left it out \(the Registry couldn't be reached, or its newest release was withdrawn\)/);
  assert.equal(plan[0].update, undefined);
  assert.equal(plan[1].update, true);
  assert.ok(planUpdates(list([commerce]), null)[0].problem);
});

test("a refusal names what the update asks for, or EmDash's code and status", () => {
  assert.match(refusal(403, { error: { code: "CAPABILITY_ESCALATION", details: { capabilityChanges: { added: ["network:fetch"] } } } }), /new permissions \(network:fetch\).*by hand/);
  assert.match(refusal(403, { error: { code: "ROUTE_VISIBILITY_ESCALATION", details: { routeVisibilityChanges: { newlyPublic: ["webhook"] } } } }), /\(webhook\).*Access app/);
  assert.match(refusal(400, { error: { code: "MCP_TOOL_CONSENT_REQUIRED" } }), /tools it offers agents/);
  assert.equal(refusal(500, { error: { code: "UPDATE_FAILED", message: "Failed to update plugin" } }), "EmDash said UPDATE_FAILED: Failed to update plugin (HTTP 500)");
  assert.equal(refusal(302, null), "the store answered HTTP 302");
});
