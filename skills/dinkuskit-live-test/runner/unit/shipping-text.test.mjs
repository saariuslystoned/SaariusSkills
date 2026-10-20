import assert from "node:assert/strict";
import test from "node:test";
import { boughtMessage, expectedWeight, labelProblems, servicePrice, shippingPages } from "../support/shipping-text.mjs";

const store = "https://store.example";

test("the admin menu's Shipping links name each of the store's Shipping pages once", () => {
  assert.deepEqual(shippingPages([
    "/_emdash/admin/plugins/dinkus-ship/shipping",
    `${store}/_emdash/admin/plugins/dinkus-ship/shipping`,
    "https://store.example/_emdash/admin/plugins/r_x7k2/shipping",
  ], store), [
    `${store}/_emdash/admin/plugins/dinkus-ship/shipping`,
    `${store}/_emdash/admin/plugins/r_x7k2/shipping`,
  ]);
});

test("no other link counts as a Shipping page", () => {
  assert.deepEqual(shippingPages([
    "https://other.example/_emdash/admin/plugins/dinkus-ship/shipping",
    "/_emdash/admin/plugins/dinkus-ship/shipping?order=1001",
    "/_emdash/admin/plugins/dinkus-ship/shipping#top",
    "/_emdash/admin/plugins/dinkus-ship/shipping/1001",
    "/_emdash/admin/plugins/dinkus-ship/settings",
    "/_emdash/admin/shipping",
    "http://[not a url",
  ], store), []);
});

test("the bought message for a sandbox label gives its price and tracking number", () => {
  assert.deepEqual(boughtMessage("Label bought, $5.12 sandbox. Tracking Z9TEST41."), { price: "$5.12", tracking: "Z9TEST41" });
  assert.deepEqual(boughtMessage("  Label bought, $10.40 sandbox. Tracking T42.\n"), { price: "$10.40", tracking: "T42" });
});

test("a live label, a half price or anything else is not a sandbox label's bought message", () => {
  for (const text of [
    "Label bought, $5.12. Tracking Z9TEST41.",
    "Label bought, $5.1 sandbox. Tracking Z9TEST41.",
    "Label bought, $5.12 sandbox. Tracking z9test41.",
    "Label bought, $5.12 sandbox. Tracking Z9TEST41. Refund requested.",
    "Label cancelled.",
    "",
    undefined,
  ]) assert.equal(boughtMessage(text), null, String(text));
});

test("the Service select gives the quoted price of exactly the service asked for", () => {
  const options = ["USPS Priority Mail Express: $30.45", "USPS Priority Mail: $9.85", " USPS Ground Advantage: $5.12 "];
  assert.equal(servicePrice(options, "USPS Ground Advantage"), "$5.12");
  assert.equal(servicePrice(options, "USPS Priority Mail"), "$9.85");
  assert.equal(servicePrice(options, "USPS Priority Mail Express"), "$30.45");
});

test("a service with no quoted price has no price", () => {
  assert.equal(servicePrice(["USPS Ground Advantage", "USPS Ground Advantage: $5.1"], "USPS Ground Advantage"), null);
  assert.equal(servicePrice(["USPS Priority Mail Express: $30.45"], "USPS Priority Mail"), null);
  assert.equal(servicePrice([], "USPS Ground Advantage"), null);
});

test("the label form starts with the items' weight plus the box's, to a tenth of an ounce", () => {
  assert.equal(expectedWeight("12.5 oz", "Mailer: 10 × 8 × 2 in, 3 oz empty"), 15.5);
  assert.equal(expectedWeight("0.1 oz", "Envelope: 9 × 6 × 1 in, 0.2 oz empty"), 0.3);
  assert.equal(expectedWeight("8 oz", "Small box: 8 × 6 × 4 in, 4 oz empty"), 12);
});

test("the starting weight stays within Ship's 0.1 to 1120 ounces", () => {
  assert.equal(expectedWeight("0 oz", "Envelope: 9 × 6 × 1 in, 0 oz empty"), 0.1);
  assert.equal(expectedWeight("1200 oz", "Crate: 30 × 20 × 20 in, 40 oz empty"), 1120);
});

test("a weight the page doesn't give in ounces has no starting weight", () => {
  assert.equal(expectedWeight("12.5 lb", "Mailer: 10 × 8 × 2 in, 3 oz empty"), null);
  assert.equal(expectedWeight("12.5 oz", "Mailer: 10 × 8 × 2 in"), null);
  assert.equal(expectedWeight(undefined, "Mailer: 10 × 8 × 2 in, 3 oz empty"), null);
  assert.equal(expectedWeight("12.5 oz", ""), null);
});

test("a label's fields match the label Ship sold", () => {
  const sold = { service: "USPS Ground Advantage", tracking: "Z9TEST41", price: "$5.12" };
  const fields = {
    Service: "USPS Ground Advantage",
    "Tracking number": "Z9TEST41 (test, not trackable)",
    Box: "Mailer",
    Postage: "$5.12 sandbox price, nothing charged",
  };
  assert.deepEqual(labelProblems(fields, sold), []);
  assert.deepEqual(labelProblems({ ...fields, Service: "USPS Priority Mail", Postage: undefined }, sold), [
    'its Service reads "USPS Priority Mail", not "USPS Ground Advantage"',
    'its Postage reads "nothing", not "$5.12 sandbox price, nothing charged"',
  ]);
  assert.deepEqual(labelProblems({ ...fields, "Tracking number": "Z9TEST41" }, sold), [
    'its Tracking number reads "Z9TEST41", not "Z9TEST41 (test, not trackable)"',
  ]);
  assert.deepEqual(labelProblems(null, sold), ["the order's page shows no label"]);
});
