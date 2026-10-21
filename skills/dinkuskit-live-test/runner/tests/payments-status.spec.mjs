import { test } from "../support/browser.mjs";
import { config } from "../support/env.mjs";
import { note } from "../support/proof.mjs";
import {
  approvePayments, authorizeLink, nextPress, openPaymentsStatus, paymentsStatusAdmin, pressNamed, readPaymentsScreen, redact,
} from "../support/payments-status.mjs";
import { pluginVersion } from "../support/store-plugins.mjs";
import { notePlugins } from "../support/store-admin.mjs";
import { BETA_STORE } from "../support/store-updates.mjs";
import { journey, step } from "../support/steps.mjs";

// The connect address is a bearer for that approval. The step screenshots are the Payments status page,
// which does not show the address, and the journey leaves a blank page for Playwright's failure notes.
test.afterEach(async ({ page }) => {
  await page.goto("about:blank").catch(() => {});
});

// The owner opens Payments status. When the page asks to connect a DinkusKit account, the owner
// presses Connect, approves payments at DinkusKit, and comes back. A page that already shows
// Connected: Stripe test mode is left as it is: Reconnect and Set up or resume Stripe stay unpressed.
test("Payments status", { tag: "@next" }, journey(async ({ page }) => {
  // Connect and Approve payments change which DinkusKit account the store's Payments answers to.
  if (config.store !== BETA_STORE.store || config.siteId !== BETA_STORE.siteId) {
    throw new Error(`Only the beta store, ${BETA_STORE.store} (site ${BETA_STORE.siteId}), gets Payments connected; this run is set to ${config.store || "no store"} (site ${config.siteId || "not set"}).`);
  }
  let statusUrl;

  await step(page, "The Payments status page opens in the store admin", async () => {
    statusUrl = await paymentsStatusAdmin(page);
    await openPaymentsStatus(page, statusUrl);
    const plugin = new URL(statusUrl).pathname.split("/")[4];
    const version = pluginVersion(await notePlugins(page), plugin);
    note("payments status plugin", `${plugin} ${version ?? "(version not shown)"}`);
    return `Payment setup is open${version ? ` (${version})` : ""}`;
  });

  await step(page, "The page shows payment setup and no store key or session secret", async () => {
    const screen = await readPaymentsScreen(page);
    if (!screen.reading.header) throw new Error("Payments status did not show Payment setup.");
    const said = redact(screen.reading.connect || screen.reading.banner || "Payment setup");
    return said;
  });

  await step(page, "Connect is used only when the page asks for a DinkusKit account", async () => {
    let approved = false;
    let previous = "";
    for (let turn = 0; turn < 6; turn++) {
      const screen = await readPaymentsScreen(page);
      const decision = nextPress(screen.reading, screen.controls, { approved });
      if (decision.action === "leave") return decision.because;
      if (decision.action === "blocked") throw new Error(decision.because);
      const mark = `${decision.action}:${decision.name ?? ""}\n${screen.reading.banner}\n${screen.reading.connect}`;
      if (mark === previous) throw new Error(`Payments status still says "${redact(screen.reading.connect || screen.reading.banner)}" after ${decision.action === "authorize" ? "Approve payments" : decision.name}.`);
      previous = mark;
      if (decision.action === "authorize") {
        await approvePayments(page, await authorizeLink(page));
        approved = true;
      } else {
        await pressNamed(page, decision.name);
      }
      await openPaymentsStatus(page, statusUrl);
    }
    throw new Error("Payments status still asks for a connection after its connect controls were used.");
  });
}));
