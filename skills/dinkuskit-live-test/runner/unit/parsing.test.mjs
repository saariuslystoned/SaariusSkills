import assert from "node:assert/strict";
import test from "node:test";
import { clean, extract } from "../support/mail-patterns.mjs";
import { parseSettings } from "../support/settings-file.mjs";
import { describePlugins } from "../support/store-plugins.mjs";
import { cartCount } from "../support/storefront-text.mjs";

test("the DinkusKit sign-in link survives quoted-printable and HTML encoding", () => {
  const body = [
    "Sign in to DinkusKit",
    '<a href=3D"https://dinkuskit.com/api/auth/magic-link/verify?token=3Dtok_1&amp;callbackURL=3D%2Fac=',
    'count">Sign in</a>',
  ].join("\n");
  assert.deepEqual(extract.dinkuskit(clean(body)), ["https://dinkuskit.com/api/auth/magic-link/verify?token=tok_1&callbackURL=%2Faccount"]);
});

test("the Access code is the six digits after the word code, never a colour", () => {
  const body = '<td style="color:#333333">Here is your login code for example.cloudflareaccess.com:</td><td style="color: #445566">482913</td>';
  assert.deepEqual(extract.access(clean(body)), ["482913"]);
});

test("the Access code is found after PIN on its own line", () => {
  assert.deepEqual(extract.access("Your one-time PIN\n\n105729\n\nIt expires in 10 minutes."), ["105729"]);
});

test("longer numbers, dates and ids are not codes", () => {
  assert.deepEqual(extract.access("Order 1234567 placed 2026-10-17, ref ab123456, id=654321"), []);
});

test("the settings file takes only DINKUS_E2E_ keys", () => {
  const settings = parseSettings([
    "# this machine's test store",
    "DINKUS_E2E_STORE=https://store.example",
    "export DINKUS_E2E_SITE_ID='site-1'",
    'DINKUS_E2E_ACCESS_MAIL_QUERY="from:a@example.com newer_than:1h"',
    "DINKUS_E2E_PRODUCT_PATH=/p?x=1",
    "PATH=/tmp/evil",
    "NODE_OPTIONS=--require /tmp/evil.js",
    "",
  ].join("\n"));
  assert.deepEqual(settings, {
    DINKUS_E2E_STORE: "https://store.example",
    DINKUS_E2E_SITE_ID: "site-1",
    DINKUS_E2E_ACCESS_MAIL_QUERY: "from:a@example.com newer_than:1h",
    DINKUS_E2E_PRODUCT_PATH: "/p?x=1",
  });
});

test("the proof names each running plugin by its Registry slug and version", () => {
  const body = { success: true, data: { items: [
    { id: "r_commerce", name: "DinkusKit Commerce", version: "0.2.2", enabled: true, source: "registry", registrySlug: "dinkus-commerce" },
    { id: "r_payments", name: "DinkusKit Payments", version: "0.2.8", enabled: true, source: "registry", registrySlug: "dinkus-payments" },
    { id: "r_old", name: "Old plugin", version: "0.1.0", enabled: false, source: "registry", registrySlug: "old-plugin" },
    { id: "forms", name: "Forms", version: "1.0.0", enabled: true, source: "config" },
  ] } };
  assert.equal(describePlugins(body), "dinkus-commerce 0.2.2, dinkus-payments 0.2.8, Forms 1.0.0");
  assert.throws(() => describePlugins({ success: false }), /no items/);
});

test("the header cart count reads the storefront's cart link label", () => {
  assert.equal(cartCount("Cart"), 0);
  assert.equal(cartCount("Cart, 1 item"), 1);
  assert.equal(cartCount("Cart, 12 items"), 12);
  assert.equal(cartCount(null), null);
  assert.equal(cartCount("Basket"), null);
});
