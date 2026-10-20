import { createHash } from "node:crypto";
import { writeFileSync } from "node:fs";
import { get } from "./browser.mjs";
import { config } from "./env.mjs";
import { shippingPages } from "./shipping-text.mjs";
import { openAdmin } from "./store-admin.mjs";

// The Ship plugin's Shipping page in the store admin, as the journeys that buy labels there read it. The
// plugin draws each page from hosted Ship's answer on every click (dinkuskit/ship docs/contracts/ship-plugin-v1.md).

export const SERVICES = { GA: "USPS Ground Advantage", PM: "USPS Priority Mail", EM: "USPS Priority Mail Express" };
export const SANDBOX_KIND = "Free Pitney Bowes sandbox label (real sandbox price, nothing charged)";
// The label form's weight field ("Package weight in ounces, items plus box (0.1 to 1120)").
const WEIGHT_FIELD = /^Package weight\b/;

// What the Shipping page shows in place of Ship's orders when it can't use Ship, and what puts it right.
const PROBLEMS = {
  "DinkusKit.com did not sign a pass": "DinkusKit.com has to sign this store's passes for the Ship plugin.",
  "Ship could not be reached": "",
  "Ship could not be used": "",
  "Order not at Ship": "",
  "Something went wrong": "",
  "Connect Ship": "Paste the store's Store ID and store key from the Set up Commerce box on DinkusKit.com into the Ship plugin's settings.",
  "Ship settings need a look": "Paste the Store ID and store key again from the Set up Commerce box on DinkusKit.com.",
  "Shipping is for Editors and Administrators": "The test's store admin sign-in has to be an Editor or an Administrator.",
};
// What an order's page shows when Ship refused the last press, or can't make a label for the order yet.
const REFUSALS = ["No label bought", "Not done", "This address cannot take a label yet", "Set up Ship first", "Connect your Pitney Bowes account first"];

const exactly = titles => new RegExp(`^(?:${titles.map(title => title.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})$`);
const PROBLEM_TITLE = exactly(Object.keys(PROBLEMS));
const REFUSAL_TITLE = exactly(REFUSALS);

/** The store admin's Shipping page: DINKUS_E2E_SHIPPING_ADMIN, or the one Shipping page in the admin's menu. */
export async function shippingAdmin(page) {
  if (config.shippingAdmin) {
    if (new URL(config.shippingAdmin).origin !== config.store) throw new Error(`DINKUS_E2E_SHIPPING_ADMIN is on another site than DINKUS_E2E_STORE (in ${config.settingsFile}).`);
    return config.shippingAdmin;
  }
  await openAdmin(page, `${config.store}/_emdash/admin`);
  const links = page.getByRole("link", { name: "Shipping", exact: true });
  // The menu lists plugins' pages once the admin has read its plugins.
  await links.first().waitFor({ timeout: 30_000 }).catch(() => {});
  const pages = shippingPages(await links.evaluateAll(anchors => anchors.map(anchor => anchor.href)), config.store);
  if (pages.length === 1) return pages[0];
  if (pages.length) throw new Error(`The store admin's menu has ${pages.length} Shipping pages; set DINKUS_E2E_SHIPPING_ADMIN to the Ship plugin's (in ${config.settingsFile}).`);
  throw new Error("The store admin's menu has no Shipping page, so the Ship plugin isn't installed or is switched off. On the beta store, install dinkus-ship-beta from the Registry.");
}

/** The line the page shows under `title`, read from the page's text. */
async function lineAfter(page, title) {
  const lines = (await page.locator("main").innerText()).split("\n").map(line => line.trim()).filter(Boolean);
  return lines[lines.indexOf(title) + 1] ?? "";
}

/** Fails with what the Shipping page says when it shows why it can't use Ship. */
async function problemShown(page) {
  const title = (await page.locator("main").getByText(PROBLEM_TITLE).first().textContent({ timeout: 1_000 }).catch(() => null))?.trim();
  if (!title) return;
  const said = await lineAfter(page, title);
  const hint = PROBLEMS[title];
  throw new Error(`The Shipping page says "${title}"${said ? `: ${said}` : "."}${hint ? ` ${hint}` : ""}`);
}

/** Ship's reason, when an order's page shows that it refused the last press or can't make a label yet; else null. */
export async function refusalShown(page) {
  const title = (await page.locator("main").getByText(REFUSAL_TITLE).first().textContent({ timeout: 1_000 }).catch(() => null))?.trim();
  if (!title) return null;
  const said = await lineAfter(page, title);
  return `The order's page says "${title}"${said ? `: ${said}` : ""}`;
}

/**
 * Waits for what a press on the Shipping page should bring (`wanted`), and returns its text. When the page
 * shows a refusal or why it can't use Ship instead, fails with what it says.
 */
export async function afterPress(page, wanted) {
  const main = page.locator("main");
  await wanted.or(main.getByText(REFUSAL_TITLE)).or(main.getByText(PROBLEM_TITLE)).first().waitFor({ timeout: 60_000 })
    .catch(() => { throw new Error("The Shipping page showed nothing new within a minute."); });
  await problemShown(page);
  if (!await wanted.first().isVisible()) throw new Error(await refusalShown(page));
  return (await wanted.first().innerText()).trim();
}

/** Opens the Shipping page's list of orders, failing with what the page says when it can't use Ship. */
export async function openShipping(page, url) {
  await openAdmin(page, url);
  await afterPress(page, page.locator("main").getByRole("button", { name: "Refresh", exact: true }));
}

/**
 * The open Shipping list's row for TEST order #number, opening the list again every 15 seconds for up
 * to `waitMs` until Ship has the order; null when it never does.
 */
export async function shippingRow(page, url, number, waitMs = 0) {
  const deadline = Date.now() + waitMs;
  for (;;) {
    const row = page.locator("main").getByRole("row").filter({ has: page.getByRole("cell", { name: `#${number} (TEST)`, exact: true }) });
    if (await row.count()) return row.first();
    if (Date.now() >= deadline) return null;
    await page.waitForTimeout(15_000);
    await openShipping(page, url);
  }
}

/** The status a Shipping list row shows ("No label", "Label bought", "Label cancelled", "Completed", "Fix address"). */
export async function rowStatus(row) {
  return (await row.getByRole("cell").nth(3).innerText()).trim();
}

/** Opens TEST order #number from its row in the Shipping list and waits for the order's page. */
export async function openRow(page, row, number) {
  await row.getByRole("button", { name: "Open", exact: true }).click();
  await afterPress(page, page.locator("main").getByRole("heading", { name: `Order #${number} (TEST)`, exact: true }));
}

/** Opens TEST order #number from the Shipping list. */
export async function openShippingOrder(page, url, number) {
  await openShipping(page, url);
  const row = await shippingRow(page, url, number);
  if (!row) throw new Error(`Shipping doesn't list #${number} (TEST).`);
  await openRow(page, row, number);
}

/**
 * The open order's fields, as the page groups them: `order` (Ship to, Items, Items' weight, Status), the
 * live label's (`label`, or null) and each earlier label's (`earlier`, once that list is open).
 */
export async function orderFields(page) {
  const groups = await page.locator("main").evaluate(main => {
    const earlier = [...main.querySelectorAll("button")].find(button => /^Earlier labels \(\d+\)$/.test(button.textContent.trim()));
    const found = [];
    // A fields block is a grid of label and value pairs; the plugin draws one for the order and one per label.
    for (const grid of main.querySelectorAll("div")) {
      const cells = [...grid.children];
      if (!cells.length || !cells.every(cell => cell.children.length === 2 && cell.children[1].hasAttribute("title"))) continue;
      found.push({
        fields: Object.fromEntries(cells.map(cell => [cell.children[0].textContent.trim(), cell.children[1].textContent.trim()])),
        earlier: Boolean(earlier && earlier.compareDocumentPosition(grid) & Node.DOCUMENT_POSITION_FOLLOWING),
      });
    }
    return found;
  });
  const labels = groups.filter(group => "Tracking number" in group.fields);
  return {
    order: groups.find(group => "Items' weight" in group.fields)?.fields ?? null,
    label: labels.find(group => !group.earlier)?.fields ?? null,
    earlier: labels.filter(group => group.earlier).map(group => group.fields),
  };
}

/** Opens the order page's Earlier labels list, when it has one; false when it has none. */
export async function openEarlierLabels(page) {
  const toggle = page.locator("main").getByRole("button", { name: /^Earlier labels \(\d+\)$/ });
  if (!await toggle.count()) return false;
  if (await toggle.getAttribute("aria-expanded") !== "true") await toggle.click();
  await page.waitForFunction(() => [...document.querySelectorAll("main button")].some(button =>
    /^Earlier labels \(\d+\)$/.test(button.textContent.trim()) && button.getAttribute("aria-expanded") === "true"), null, { timeout: 15_000 });
  return true;
}

/** The label form's weight field: a text field since ship#45, a number field before. */
export const weightField = page => {
  const main = page.locator("main");
  return main.getByRole("textbox", { name: WEIGHT_FIELD }).or(main.getByRole("spinbutton", { name: WEIGHT_FIELD }));
};

/** What the label form's select named `label` shows now. */
export async function chosen(page, label) {
  return (await page.locator("main").getByRole("combobox", { name: label, exact: true }).innerText()).trim();
}

/** The options of the label form's select named `label`, as it lists them ("USPS Ground Advantage: $5.12"). */
export async function optionsOf(page, label) {
  await page.locator("main").getByRole("combobox", { name: label, exact: true }).click();
  const options = page.getByRole("option");
  await options.first().waitFor({ timeout: 15_000 });
  const shown = (await options.allInnerTexts()).map(option => option.trim());
  await page.keyboard.press("Escape");
  await options.first().waitFor({ state: "hidden", timeout: 15_000 }).catch(() => {});
  return shown;
}

/** Picks the option reading exactly `option` in the label form's select named `label`, unless it shows it already. */
export async function choose(page, label, option) {
  if (await chosen(page, label) === option) return;
  const shown = await optionsOf(page, label);
  if (!shown.includes(option)) throw new Error(`The label form's ${label} offers no "${option}": ${shown.map(text => `"${text}"`).join(", ") || "nothing"}.`);
  await page.locator("main").getByRole("combobox", { name: label, exact: true }).click();
  await page.getByRole("option", { name: option, exact: true }).click();
  if (await chosen(page, label) !== option) throw new Error(`The label form's ${label} wouldn't take "${option}".`);
}

const hostOf = href => { try { return new URL(href).host || "nowhere"; } catch { return "an unreadable address"; } };
// Ship answers a print link with this while it is still fetching a just-bought label's PDF from Pitney Bowes.
const NOT_READY = 503;

/**
 * Presses Print label, which opens Ship's 5-minute print link in a new tab, then reads the same link and
 * checks it answers with the label's PDF, saved to `file`. The link opens the label without a sign-in, so
 * no note or error carries it; a failed journey's trace can, and it opens only the PDF saved here.
 */
export async function printLabel(page, file) {
  const link = page.locator("main").getByRole("link", { name: "Print label", exact: true });
  if (!await link.count()) throw new Error("The order's page has no Print label.");
  const href = await link.getAttribute("href");
  if (!href?.startsWith(`${config.ship}/print/`)) throw new Error(`Print label opens ${hostOf(href)}, not a print link from Ship (${new URL(config.ship).host}).`);
  const opened = page.context().waitForEvent("page", { timeout: 15_000 }).catch(() => null);
  await link.click();
  const tab = await opened;
  if (!tab) throw new Error("Print label opened no new tab.");
  await tab.close().catch(() => {});
  const read = () => get(page, href).catch(error => {
    throw new Error(`Ship's print link didn't answer (${error.message.split("\n")[0].replaceAll(href, "the print link")}).`);
  });
  let response = await read();
  // Ship fetches a new label's PDF from Pitney Bowes after the sale; the link lasts long enough to wait.
  for (const deadline = Date.now() + 120_000; response.status() === NOT_READY && Date.now() < deadline;) {
    await page.waitForTimeout(15_000);
    response = await read();
  }
  const type = response.headers()["content-type"] ?? "";
  if (response.status() === NOT_READY) throw new Error("Ship's print link still says the label's PDF isn't ready two minutes after Print label.");
  if (response.status() !== 200) throw new Error(`Ship's print link answered HTTP ${response.status()}, not the label's PDF.`);
  if (!/^application\/pdf\b/.test(type)) throw new Error(`Ship's print link answered ${type || "with no content type"}, not a PDF.`);
  const body = await response.body();
  if (body.subarray(0, 5).toString() !== "%PDF-") throw new Error("Ship's print link answered something that isn't a PDF.");
  writeFileSync(file, body);
  return { bytes: body.length, sha256: createHash("sha256").update(body).digest("hex") };
}
