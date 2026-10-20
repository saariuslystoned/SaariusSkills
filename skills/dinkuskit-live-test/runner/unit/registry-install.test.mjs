import assert from "node:assert/strict";
import test from "node:test";
import { installBody, installRefusal, namedInstalls, planInstalls } from "../support/registry-install.mjs";

const list = items => ({ data: { items } });
const ship = { id: "r_ship", source: "registry", registrySlug: "dinkus-ship-beta", version: "0.1.0-beta.0" };

test("an empty install list is the Ship beta that listing-passed", () => {
  assert.deepEqual(namedInstalls(""), [{ name: "dinkus-ship-beta", version: "0.1.0-beta.0" }]);
  assert.deepEqual(namedInstalls(" dinkus-payments-beta 0.2.10-beta.1, dinkus-ship-beta@0.1.0-beta.0 "), [
    { name: "dinkus-payments-beta", version: "0.2.10-beta.1" },
    { name: "dinkus-ship-beta", version: "0.1.0-beta.0" },
  ]);
  for (const bad of ["dinkus-ship 0.1.0", "dinkus-ship-beta latest", "someone-beta 1.0.0"]) {
    assert.throws(() => namedInstalls(bad), /doesn't name a DinkusKit beta/);
  }
});

test("a beta the store already runs is left alone, including one the owner switched off", () => {
  const wanted = namedInstalls("dinkus-ship-beta 0.1.0-beta.0, dinkus-commerce-beta 0.3.0-beta.4");
  const plan = planInstalls(list([ship, { id: "r_commerce", source: "registry", registrySlug: "dinkus-commerce-beta", version: "0.3.0-beta.9", enabled: false }]), wanted);
  assert.deepEqual(plan, [
    { name: "dinkus-ship-beta", version: "0.1.0-beta.0", install: false, id: "r_ship", installed: "0.1.0-beta.0" },
    { name: "dinkus-commerce-beta", version: "0.3.0-beta.4", install: false, id: "r_commerce", installed: "0.3.0-beta.9" },
  ]);
  assert.deepEqual(planInstalls(list([]), wanted.slice(0, 1)), [
    { name: "dinkus-ship-beta", version: "0.1.0-beta.0", install: true },
  ]);
});

test("the install body is what Accept & Install posts, and a verify answer without consent evidence is refused", () => {
  const body = installBody({ data: {
    publisherDid: "did:plc:ekk4pjmkh3k3ql2kfoex3qt4",
    slug: "dinkus-ship-beta",
    version: "0.1.0-beta.0",
    capabilities: ["network:request"],
    mcpTools: [],
    publicRoutes: [],
    verification: { profileCid: "bafyprofile", releaseCid: "bafyrelease" },
  } });
  assert.equal(body.acknowledgedDeclaredAccess[0], "network:request");
  assert.equal(body.acknowledgedProfileCid, "bafyprofile");
  assert.equal(body.acknowledgedReleaseCid, "bafyrelease");
  assert.throws(() => installBody({ data: { publisherDid: "did:plc:x", slug: "dinkus-ship-beta", version: "0.1.0-beta.0", capabilities: [] } }), /signed record ids/);
  assert.match(installRefusal(409, { error: { code: "ALREADY_INSTALLED", message: "Installed" } }), /ALREADY_INSTALLED/);
});
