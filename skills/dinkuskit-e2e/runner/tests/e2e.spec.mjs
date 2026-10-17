import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { test, expect } from "../support/browser.mjs";
import { config } from "../support/env.mjs";
import { note, record, shot } from "../support/proof.mjs";
import { openShip, openStoreAdmin } from "../support/signin.mjs";
import { placeTestOrder } from "../support/checkout.mjs";

const sitePath = () => `/stores/${encodeURIComponent(config.siteId)}`;

/**
 * Runs one step, recording PASS or FAIL with the reason and a screenshot. A `soft` step's
 * failure is recorded and the run goes on; it returns undefined.
 */
async function step(page, name, body, { soft = false } = {}) {
  return test.step(name, async () => {
    try {
      const detail = await body();
      await shot(page, name.toLowerCase().replace(/[^a-z0-9]+/g, "-"));
      record(name, "PASS", detail && typeof detail === "object" ? JSON.stringify(detail) : detail ?? "");
      return detail;
    } catch (error) {
      await shot(page, `fail-${name.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`);
      record(name, "FAIL", error.message.split("\n")[0]);
      if (!soft) throw error;
    }
  });
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

/** Opens one order in Commerce Orders (already on the Orders page) and returns its detail text. */
async function inspectOrder(page, number) {
  await page.getByRole("button", { name: new RegExp(`^Inspect #${number}\\b`) }).first().click();
  await expect(page.getByText(/Order ID:/).first()).toBeVisible({ timeout: 30_000 });
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

test("DinkusKit live e2e: TEST order to sandbox label to Completed", async ({ page }) => {
  expect(config.siteId, "DINKUS_E2E_SITE_ID must name the store's DinkusKit site id").not.toBe("");
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
    if (!await openStoreAdmin(page, config.ordersAdmin, { waitForPerson: config.adminSignIn === "wait" })) {
      record("Commerce Orders shows the paid TEST order", "SKIP", "the saved profile has no store admin sign-in yet; Commerce's background check sends the order to Ship");
    } else await step(page, "Commerce Orders shows the paid TEST order", async () => {
      await expect(page.getByText(/#\d+ \(TEST\)/).first()).toBeVisible({ timeout: 60_000 });
      if (orderName && !/^\d+$/.test(orderName)) {
        // Orders numbers orders as they are paid, so the newest TEST order has the highest number.
        const numbers = [...(await page.locator("main").innerText()).matchAll(/#(\d+) \(TEST\)/g)].map(m => Number(m[1]));
        orderName = String(Math.max(...numbers));
      }
      const text = await inspectOrder(page, orderName);
      if (placed.orderId) expect(text, "the newest TEST order should be this checkout's order").toContain(placed.orderId);
      expect(text).toMatch(/Status:\s*Processing/);
      expect(text).toMatch(/Payment:\s*Provider-paid/);
      return `#${orderName} is TEST, provider-paid and Processing; opening Orders also sends it to Ship`;
    });
  } else {
    record("Place a Stripe TEST order on the store", "SKIP", "finish mode: starting from the order that already exists");
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

  await page.goto(config.ship + order.href);
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

    await step(page, "Label PDF downloads and is a real PDF", async () => {
      if (!label.pdf) throw new Error("No 'Open PDF to print' link.");
      const response = await page.context().request.get(new URL(label.pdf, config.ship).href);
      expect(response.status()).toBe(200);
      expect(response.headers()["content-type"]).toMatch(/application\/pdf/);
      const body = await response.body();
      expect(body.subarray(0, 5).toString()).toBe("%PDF-");
      const file = join(config.runDir, "label.pdf");
      writeFileSync(file, body);
      const sha = createHash("sha256").update(body).digest("hex");
      note("label pdf", `${body.length} bytes, sha256 ${sha}`);
      // macOS Quick Look renders a picture of the label for the report; skipped quietly elsewhere.
      try { execFileSync("qlmanage", ["-t", "-s", "1400", "-o", config.runDir, file], { stdio: "ignore", timeout: 30_000 }); note("label picture", "label.pdf.png"); } catch {}
      return `${body.length} bytes, sha256 ${sha.slice(0, 16)}…`;
    });
  }

  // Ship's page says so once Commerce has marked the order Completed and told Ship.
  const shipPage = config.ship + order.href;
  const completedOnShip = async () => {
    await page.goto(shipPage);
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
      if (!await openStoreAdmin(page, config.ordersAdmin, { waitForPerson: config.adminSignIn === "wait" })) {
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

  if (!await openStoreAdmin(page, config.ordersAdmin, { waitForPerson: config.adminSignIn === "wait" })) {
    record("Commerce Orders shows Completed in the store admin", "SKIP", "the saved profile has no store admin sign-in yet; Ship's page already shows Commerce completed the order");
  } else await step(page, "Commerce Orders shows Completed in the store admin", async () => {
    const text = await inspectOrder(page, orderName);
    expect(text).toMatch(/Status:\s*Completed/);
    const tracking = text.match(/Tracking number:\s*(\S+)/)?.[1];
    if (label?.tracking) expect(tracking).toBe(label.tracking);
    return `#${orderName} Completed in Commerce, carrier ${text.match(/Carrier:\s*(.+)/)?.[1]?.trim() ?? "not shown"}, tracking ${tracking ?? "not shown"}`;
  });

  const report = JSON.parse(readFileSync(join(config.runDir, "report.json"), "utf8"));
  console.log(`\nVerdict: ${report.verdict}. Proof: ${config.runDir}/PROOF.md\n`);
  // A step that failed softly still fails the run, so "run the test" exits non-zero.
  expect(report.verdict, `see ${config.runDir}/PROOF.md`).toBe("PASS");
});
