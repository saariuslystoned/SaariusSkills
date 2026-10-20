import assert from "node:assert/strict";
import test from "node:test";
import { commerceSettings } from "../support/commerce-settings.mjs";

const list = items => ({ data: { items } });
const commerce = (extra = {}) => ({
  id: "r_commerce",
  name: "Commerce",
  registrySlug: "dinkus-commerce-beta",
  version: "0.3.0-beta.12",
  enabled: true,
  hasSettings: true,
  ...extra,
});

test("the one Commerce listing, release or beta, is the settings plugin", () => {
  const beta = commerceSettings(list([commerce(), { id: "r_pay", name: "Payments", registrySlug: "dinkus-payments-beta", version: "0.2.0", enabled: true, hasSettings: true }]));
  assert.deepEqual(beta, {
    id: "r_commerce",
    name: "Commerce",
    slug: "dinkus-commerce-beta",
    version: "0.3.0-beta.12",
    path: "/_emdash/admin/plugins-manager/r_commerce/settings",
  });
  const release = commerceSettings(list([commerce({ id: "r_release", registrySlug: "dinkus-commerce", version: "0.3.0" })]));
  assert.equal(release.slug, "dinkus-commerce");
  assert.equal(release.path, "/_emdash/admin/plugins-manager/r_release/settings");
  const spaced = commerceSettings(list([commerce({ id: "r a" })]));
  assert.equal(spaced.path, "/_emdash/admin/plugins-manager/r%20a/settings");
});

test("a payments plugin, or a slug that only starts like Commerce, is not Commerce settings", () => {
  const found = commerceSettings(list([
    { id: "r_pay", name: "Payments", registrySlug: "dinkus-payments-beta", version: "0.2.0", enabled: true, hasSettings: true },
    { id: "r_extra", name: "Commerce extra", registrySlug: "dinkus-commerce-beta-extra", version: "1.0.0", enabled: true, hasSettings: true },
  ]));
  assert.equal(found.error, "The store doesn't run Commerce (dinkus-commerce or dinkus-commerce-beta).");
  assert.equal(found.path, undefined);
});

test("Commerce settings stay closed unless Plugins would show that one form", () => {
  assert.match(commerceSettings(list([commerce({ enabled: false })])).error, /switched off/);
  const { hasSettings, ...withoutForm } = commerce();
  assert.match(commerceSettings(list([withoutForm])).error, /no settings form/);
  assert.match(commerceSettings(list([commerce(), commerce({ id: "r_release", registrySlug: "dinkus-commerce", version: "0.3.0" })])).error, /dinkus-commerce-beta, dinkus-commerce/);
  assert.match(commerceSettings(list([commerce({ id: "" })])).error, /without an id/);
  assert.match(commerceSettings(list([commerce({ name: "" })])).error, /without a name/);
  assert.match(commerceSettings(null).error, /couldn't be read/);
  assert.equal(commerceSettings(list([commerce({ enabled: false })])).path, undefined);
});
