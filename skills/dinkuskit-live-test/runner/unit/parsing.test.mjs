import assert from "node:assert/strict";
import test from "node:test";
import { clean, extract } from "../support/mail-patterns.mjs";
import { parseSettings } from "../support/settings-file.mjs";

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
