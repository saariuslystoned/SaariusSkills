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

/** Runs one step, recording PASS or FAIL with the reason and a screenshot. */
async function step(page, name, body) {
  return test.step(name, async () => {
    try {
      const detail = await body();
      await shot(page, name.toLowerCase().replace(/[^a-z0-9]+/g, "-"));
      record(name, "PASS", detail && typeof detail === "object" ? JSON.stringify(detail) : detail ?? "");
      return detail;
    } catch (error) {
      await shot(page, `fail-${name.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`);
      record(name, "FAIL", error.message.split("\n")[0]);
      throw error;
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
    orderName = await step(page, "Place a Stripe TEST order on the store", async () => {
      const placed = await placeTestOrder(page);
      note("order", `#${placed.number}`);
      return placed.number;
    });
    await step(page, "Commerce Orders shows the paid TEST order", async () => {
      await openStoreAdmin(page, config.ordersAdmin);
      const row = page.getByText(`#${orderName}`, { exact: false }).first();
      await expect(row).toBeVisible({ timeout: 60_000 });
      const text = await page.locator("main").innerText();
      expect(text).toMatch(/TEST/);
      expect(text).toMatch(/Processing/i);
      return `#${orderName} listed as TEST and Processing; opening Orders also sends it to Ship`;
    });
  } else {
    record("Place a Stripe TEST order on the store", "SKIP", "finish mode: starting from the order that already exists");
  }

  const order = await step(page, "Ship has the order", async () => {
    await openShip(page, `${sitePath()}/orders`);
    const chosen = chooseOrder(await shipOrders(page), orderName);
    note("order", chosen.name);
    note("ship order page", config.ship + chosen.href);
    return chosen;
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

  await step(page, "Commerce marks the order Completed with the same tracking", async () => {
    const shipPage = config.ship + order.href;
    const completedText = async () => {
      await page.goto(shipPage);
      const text = await page.locator("main").innerText();
      return text.match(/This order is Completed in Commerce(?: with tracking (\S+?))?\./);
    };
    let done = await completedText();
    const deadline = Date.now() + config.completeWaitMs;
    let nudged = false;
    while (!done && Date.now() < deadline) {
      // Commerce collects labels on its 5-minute background check, or when someone opens Commerce Orders.
      if (!nudged && Date.now() > deadline - config.completeWaitMs / 2) {
        const opened = await openStoreAdmin(page, config.ordersAdmin, { waitForPerson: false }).catch(() => false);
        note("Commerce Orders opened to collect the label", opened ? "yes" : "no (store admin not signed in)");
        nudged = true;
      }
      await page.waitForTimeout(30_000);
      done = await completedText();
    }
    if (!done) throw new Error(`Ship still shows the order not Completed after ${config.completeWaitMs / 1000}s.`);
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
    await expect(page.getByText(`#${orderName}`).first()).toBeVisible({ timeout: 60_000 });
    const text = await page.locator("body").innerText();
    expect(text).toMatch(/Completed/i);
    return "order listed as Completed";
  });

  const report = JSON.parse(readFileSync(join(config.runDir, "report.json"), "utf8"));
  console.log(`\nVerdict: ${report.verdict}. Proof: ${config.runDir}/PROOF.md\n`);
});
