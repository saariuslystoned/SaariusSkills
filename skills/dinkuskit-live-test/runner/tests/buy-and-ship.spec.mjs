import { renderLabelPdf, showLabelPicture } from "../support/label-pdf.mjs";
import { createHash } from "node:crypto";
import { writeFileSync } from "node:fs";
import { join } from "node:path";
import { get, test, expect } from "../support/browser.mjs";
import { config } from "../support/env.mjs";
import { note, record } from "../support/proof.mjs";
import { journey, step } from "../support/steps.mjs";
import { openShip, openStoreAdmin } from "../support/signin.mjs";
import { placeTestOrder } from "../support/checkout.mjs";
import { numberOf, openOrder } from "../support/orders-admin.mjs";
import { thankYouShown } from "../support/checkout-text.mjs";
import { describePlugins } from "../support/store-plugins.mjs";

const sitePath = () => `/stores/${encodeURIComponent(config.siteId)}`;

let pluginsNoted = false;

/**
 * Opens Commerce Orders in the store admin, signing in if needed. The first time it gets in, it
 * also notes which plugin versions the store runs, so the proof says what it covers.
 */
async function openOrdersAdmin(page) {
  const signedIn = await openStoreAdmin(page, config.ordersAdmin, { waitForPerson: config.adminSignIn === "wait" });
  if (signedIn && !pluginsNoted) {
    pluginsNoted = true;
    try {
      const response = await get(page, `${config.store}/_emdash/api/admin/plugins`, { headers: { "X-EmDash-Request": "1" } });
      note("plugins", response.ok() ? describePlugins(await response.json()) : `couldn't read the plugin list (HTTP ${response.status()})`);
    } catch (error) {
      note("plugins", `couldn't read the plugin list (${error.message.split("\n")[0]})`);
    }
  }
  return signedIn;
}

/** Ship's orders list as rows: link, number text, TEST flag and status. */
async function shipOrders(page) {
  return page.locator("main table tbody tr").evaluateAll(rows => rows.map(row => {
    const link = row.querySelector("td a");
    const cells = row.querySelectorAll("td");
    return {
      href: link?.getAttribute("href") ?? "", name: link?.textContent?.trim() ?? "",
      test: !!row.querySelector(".tag.test"), status: cells[3]?.textContent?.trim() ?? "",
    };
  }));
}

function chooseOrder(rows, wanted) {
  if (wanted) {
    const match = rows.find(row => row.name === `#${wanted}` || decodeURIComponent(row.href.split("/").pop() ?? "") === wanted);
    if (!match) throw new Error(`Ship has no order ${wanted}. Ship lists: ${rows.map(r => `${r.name} (${r.status})`).join(", ") || "none"}. Open Commerce Orders once so Commerce sends it.`);
    return match;
  }
  const candidates = rows.filter(row => row.test && row.status !== "Completed");
  if (candidates.length !== 1) throw new Error(`Expected exactly one unfinished TEST order in Ship, found ${candidates.length}: ${rows.map(r => `${r.name} (${r.status})`).join(", ")}. Set DINKUS_E2E_ORDER.`);
  return candidates[0];
}

/**
 * Opens order #number in Commerce Orders and returns its page's text. Orders lists its orders by order
 * ID, 25 to a page, so a run's order can be on any page; openOrder pages to it.
 */
async function orderText(page, number) {
  await openOrder(page, number);
  return page.locator("main").innerText();
}

/** The first label row on Ship's order page. */
async function labelRow(page) {
  const row = page.locator("h2:has-text('Labels') + table tbody tr").first();
  if (!await row.count()) return null;
  const cells = row.locator("td");
  return {
    service: (await cells.nth(0).innerText()).trim(),
    tracking: (await cells.nth(1).innerText()).trim(),
    postage: (await cells.nth(3).innerText()).trim(),
    pdf: await row.getByRole("link", { name: /open pdf to print/i }).getAttribute("href").catch(() => null),
  };
}

// A TEST order from checkout to a sandbox label and Completed.
test("Buy and ship", { tag: "@running" }, journey(async ({ page }) => {
  expect(config.store, `Set DINKUS_E2E_STORE to the store's address (in ${config.settingsFile})`).not.toBe("");
  expect(config.siteId, `Set DINKUS_E2E_SITE_ID to the store's DinkusKit site id (in ${config.settingsFile})`).not.toBe("");
  let orderName = config.order;

  if (config.mode === "full") {
    let placed;
    orderName = await step(page, "Place a Stripe TEST order on the store", async () => {
      placed = await placeTestOrder(page);
      if (["pending", "failed", "expired", "cancelled", "canceled"].includes(placed.state)) throw new Error(`Commerce reports this checkout as "${placed.state}", not paid.`);
      note("order", placed.number ? `#${placed.number}` : placed.orderId ?? "unknown");
      if (placed.checkoutToken) note("stripe session", placed.checkoutToken);
      note("checkout state", placed.state);
      // The store only learns Commerce's order id; null falls back to "the only unfinished TEST order" in Ship.
      return placed.number ?? placed.orderId;
    });
    // Soft: a broken thank-you page fails the run, and the steps after it still show the rest.
    await step(page, "The thank-you page confirms the order and empties the cart", async () => thankYouShown(placed.thankYou), { soft: true });
    if (!await openOrdersAdmin(page)) {
      record("Commerce Orders shows the paid TEST order", "SKIP", "the saved profile has no store admin sign-in yet; Commerce's background check sends the order to Ship");
    } else await step(page, "Commerce Orders shows the paid TEST order", async () => {
      // Orders numbers orders as they are paid; this checkout's is among the newest Processing ones.
      const number = placed.number ?? await numberOf(page, placed.orderId, "Processing");
      const text = await orderText(page, number);
      orderName = String(number);
      if (placed.orderId) expect(text, `order #${number} should be this checkout's order`).toContain(placed.orderId);
      expect(text).toMatch(/Status:\s*Processing/);
      expect(text).toMatch(/Payment:\s*Provider-paid/);
      return `#${orderName} is TEST, provider-paid and Processing; opening Orders also sends it to Ship`;
    });
  } else {
    record("Place a Stripe TEST order on the store", "SKIP", "finish mode: starting from the order that already exists");
    record("The thank-you page confirms the order and empties the cart", "SKIP", "finish mode: no checkout in this run");
  }

  const order = await step(page, "Ship has the order", async () => {
    // A new order reaches Ship on Commerce's next background check (or when Commerce Orders opens).
    const deadline = Date.now() + (config.mode === "full" ? config.completeWaitMs : 0);
    for (;;) {
      await openShip(page, `${sitePath()}/orders`);
      try {
        const chosen = chooseOrder(await shipOrders(page), orderName);
        note("order", chosen.name);
        note("ship order page", config.ship + chosen.href);
        return chosen;
      } catch (error) {
        if (Date.now() >= deadline) throw error;
        await page.waitForTimeout(30_000);
      }
    }
  });
  orderName = order.name.replace(/^#/, "");
  // Ship's own page for the order. Once the store's Ship plugin has called Ship, the order's plain
  // address goes on to the store admin's Shipping page; ?view=full keeps Ship's page.
  const shipPage = new URL(order.href, config.ship);
  shipPage.searchParams.set("view", "full");

  await page.goto(shipPage.href);
  const already = /This order is Completed in Commerce/.test(await page.locator("main").innerText());
  let label = await labelRow(page);

  await step(page, "Make the Pitney Bowes sandbox label", async () => {
    if (already || (label && /TEST SANDBOX/.test(label.service))) return `already had a label: ${label?.service ?? "order Completed"}`;
    const text = await page.locator("main").innerText();
    expect(text, "Ship should treat this as a TEST order on the PB sandbox").toMatch(/free Pitney Bowes sandbox label/);
    for (const missing of [/Add your ship-from address/, /Add your box sizes/]) {
      if (missing.test(text)) throw new Error(`Ship Settings is missing something: ${text.match(missing)[0]}.`);
    }
    await page.locator("#service").selectOption(config.service);
    await page.getByRole("button", { name: "See prices" }).click();
    await page.waitForLoadState("domcontentloaded");
    const prices = await page.locator("#service option").allInnerTexts();
    note("sandbox prices", prices.join("; "));
    const error = page.locator("main p.error");
    if (await error.count()) throw new Error(`Prices: ${await error.innerText()}`);
    await page.locator("#service").selectOption(config.service);
    await page.getByRole("button", { name: "Make sandbox label" }).click();
    await page.waitForLoadState("domcontentloaded");
    if (await error.count()) throw new Error(`Ship refused the label: ${await error.innerText()}`);
    // A bought label sends the browser to the order's plain address, which can go on to the store admin.
    await page.goto(shipPage.href);
    label = await labelRow(page);
    if (!label) throw new Error("Ship shows no label after making one.");
    return `${label.service}, ${label.postage}`;
  });

  if (!already) {
    await step(page, "Label is a TEST SANDBOX label with a tracking number", async () => {
      expect(label.service).toMatch(/TEST SANDBOX/);
      expect(label.service).not.toMatch(/PRACTICE/);
      expect(label.tracking).toMatch(/^[A-Z0-9]{10,40}$/);
      note("label", label.service.replace(/\s+/g, " "));
      note("tracking", label.tracking);
      return label.tracking;
    });

    await step(page, "Label PDF downloads and renders", async () => {
      if (!label.pdf) throw new Error("No 'Open PDF to print' link.");
      const response = await get(page, new URL(label.pdf, config.ship).href);
      expect(response.status()).toBe(200);
      expect(response.headers()["content-type"]).toMatch(/application\/pdf/);
      const body = await response.body();
      expect(body.subarray(0, 5).toString()).toBe("%PDF-");
      const file = join(config.runDir, "label.pdf");
      writeFileSync(file, body);
      const sha = createHash("sha256").update(body).digest("hex");
      note("label pdf", `${body.length} bytes, sha256 ${sha}`);
      const picture = renderLabelPdf(file);
      note("label picture", `label.pdf.png, ${picture.width}×${picture.height}, sha256 ${picture.sha256}`);
      await showLabelPicture(page, picture);
      return `${body.length} bytes, sha256 ${sha.slice(0, 16)}…, shown ${picture.width}×${picture.height}`;
    });
  }

  // Ship's page says so once Commerce has marked the order Completed and told Ship.
  const completedOnShip = async () => {
    await page.goto(shipPage.href);
    return (await page.locator("main").innerText()).match(/This order is Completed in Commerce(?: with tracking (\S+?))?\./);
  };
  let done = await completedOnShip();
  const alreadyDone = !!done;

  // Two ways Commerce collects a label: its 5-minute background check, and an owner opening
  // Commerce Orders. The test waits for the first without touching the store admin, so the
  // proof shows whether it works on its own; then it opens Orders the way an owner would.
  await step(page, "Commerce's 5-minute check collects the label", async () => {
    if (alreadyDone) return "the order was already Completed";
    const started = Date.now(), deadline = started + config.completeWaitMs;
    while (!done && Date.now() < deadline) {
      await page.waitForTimeout(30_000);
      done = await completedOnShip();
    }
    if (!done) throw new Error(`Commerce had not collected the label after ${config.completeWaitMs / 1000}s without anyone opening Commerce Orders.`);
    return `collected ${Math.round((Date.now() - started) / 1000)}s into the wait`;
  }, { soft: true });

  if (!done) {
    await step(page, "Opening Commerce Orders collects the label", async () => {
      if (!await openOrdersAdmin(page)) {
        throw new Error("The store admin needs a sign-in the test can't make: its Access app offers no one-time PIN and the saved profile has no sign-in.");
      }
      // Loading the Orders list is what asks Ship for new labels.
      await expect(page.getByText(/#\d+ \(TEST\)/).first()).toBeVisible({ timeout: 60_000 });
      const deadline = Date.now() + 120_000;
      while (!(done = await completedOnShip()) && Date.now() < deadline) await page.waitForTimeout(15_000);
      if (!done) throw new Error("Ship still shows the order not Completed two minutes after Commerce Orders opened.");
      return "Completed right after Commerce Orders opened";
    });
  }

  await step(page, "Commerce marks the order Completed with the same tracking", async () => {
    const tracking = done[1];
    const expected = label?.tracking;
    if (expected) expect(tracking).toBe(expected);
    const emailState = await page.locator("main p.muted").filter({ hasText: /shipped email/i }).first().innerText().catch(() => "");
    if (emailState) note("shipped email", emailState);
    return `Completed with tracking ${tracking ?? "(none shown)"}`;
  });

  if (!await openOrdersAdmin(page)) {
    record("Commerce Orders shows Completed in the store admin", "SKIP", "the saved profile has no store admin sign-in yet; Ship's page already shows Commerce completed the order");
  } else await step(page, "Commerce Orders shows Completed in the store admin", async () => {
    const text = await orderText(page, orderName);
    expect(text).toMatch(/Status:\s*Completed/);
    const tracking = text.match(/Tracking number:\s*(\S+)/)?.[1];
    if (label?.tracking) expect(tracking).toBe(label.tracking);
    return `#${orderName} Completed in Commerce, carrier ${text.match(/Carrier:\s*(.+)/)?.[1]?.trim() ?? "not shown"}, tracking ${tracking ?? "not shown"}`;
  });
}));
