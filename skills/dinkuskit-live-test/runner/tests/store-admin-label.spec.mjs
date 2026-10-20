import { join } from "node:path";
import { test, expect } from "../support/browser.mjs";
import { placeTestOrder } from "../support/checkout.mjs";
import { config } from "../support/env.mjs";
import { renderLabelPdf, showLabelPicture } from "../support/label-pdf.mjs";
import { completionProblems, numberOf, openOrder } from "../support/orders-admin.mjs";
import { PAGE_ROOM, paceStore } from "../support/pace.mjs";
import { note } from "../support/proof.mjs";
import { afterPress, chosen, choose, openEarlierLabels, openRow, openShipping, openShippingOrder, optionsOf, orderFields, printLabel, refusalShown,
  rowStatus, SANDBOX_KIND, SERVICES, shippingAdmin, shippingRow, weightField } from "../support/shipping-admin.mjs";
import { boughtMessage, expectedWeight, labelProblems, servicePrice } from "../support/shipping-text.mjs";
import { notePlugins } from "../support/store-admin.mjs";
import { pluginVersion } from "../support/store-plugins.mjs";
import { journey, step } from "../support/steps.mjs";

// What the cancel dialog says for a sandbox label, and what an order's page says once Commerce has
// completed the order and it has no live label (dinkuskit/ship src/pages.ts).
const SANDBOX_CANCEL = "The sandbox label is voided with Pitney Bowes. The order stays as it is in Commerce.";
const COMPLETED_NOTE = /^This order is Completed in Commerce, so Ship makes no label for it\./;

// Ship's print link opens the label for five minutes with no sign-in, and Playwright's trace records
// every page, link and request the run makes, so this journey keeps no trace. Its step screenshots and
// notes are its proof.
test.use({ trace: "off" });

// On a failure Playwright also writes down the open page, links included (error-context.md), after the
// test's own screenshot. A blank page by then leaves no print link to write down.
test.afterEach(async ({ page }) => {
  await page.goto("about:blank").catch(() => {});
});

// An owner ships a paid TEST order from the store admin's Shipping page, which the Ship plugin draws
// from hosted Ship: see prices, buy a Pitney Bowes sandbox label, print it from Ship's 5-minute link,
// let Commerce complete the order, print it again, then cancel the label. It gates the Ship plugin's
// first final release.
test("Buy a label in the store admin", { tag: "@next" }, journey(async ({ page }) => {
  expect(config.store, `Set DINKUS_E2E_STORE to the store's address (in ${config.settingsFile})`).not.toBe("");
  const service = SERVICES[config.service];
  expect(service, `DINKUS_E2E_SERVICE reads "${config.service}"; set it to GA, PM or EM (in ${config.settingsFile})`).toBeTruthy();
  const soft = { soft: true };
  // It waits up to DINKUS_E2E_COMPLETE_WAIT_SECONDS twice, for Ship to list the order and for Commerce to
  // complete it, so its own deadlines always pass before Playwright's would stop it mid-step.
  test.info().setTimeout(test.info().timeout + 2 * config.completeWaitMs);
  let shipping;

  // Without the Shipping page there is nothing to test, so this step stops the journey.
  await step(page, "The Shipping page lists Ship's orders in the store admin", async () => {
    shipping = await shippingAdmin(page);
    await openShipping(page, shipping);
    const plugin = new URL(shipping).pathname.split("/")[4];
    const version = pluginVersion(await notePlugins(page), plugin);
    note("store admin label plugin", `${plugin} ${version ?? "(version not shown)"}`);
    return `the Ship plugin${version ? ` ${version}` : ""} shows Ship's orders`;
  });

  // An order that wasn't placed can't get a label, so a failed order stops the journey.
  let placed;
  await step(page, "A shopper places a Stripe TEST order", async () => {
    placed = await placeTestOrder(page);
    if (placed.state !== "paid") throw new Error(`Commerce reports this checkout as "${placed.state}", not paid.`);
    if (!placed.orderId) throw new Error("Commerce's checkout status named no order.");
    note("store admin label order", placed.orderId);
    return `Commerce recorded the payment for ${placed.orderId}`;
  });

  let number;
  await step(page, "Commerce Orders lists the order as Processing", async () => {
    // Opening Commerce Orders also sends Ship the paid orders it doesn't have yet.
    number = await numberOf(page, placed.orderId, "Processing");
    note("store admin label order number", `#${number}`);
    return `#${number} (TEST) is Processing`;
  });

  await step(page, "The Shipping page lists the order with no label", async () => {
    await openShipping(page, shipping);
    // Commerce sends a new order to Ship when Commerce Orders opens, or on its 5-minute check.
    const row = await shippingRow(page, shipping, number, config.completeWaitMs);
    if (!row) throw new Error(`Shipping still doesn't list #${number} (TEST) ${config.completeWaitMs / 1000}s after Commerce Orders opened.`);
    const status = await rowStatus(row);
    if (status !== "No label") throw new Error(`Shipping lists #${number} as "${status}", not "No label".`);
    await openRow(page, row, number);
    return `#${number} (TEST) is listed with "No label"`;
  });

  // Soft: a wrong weight or field fails the run, and pressing See prices still shows whether the form works.
  await step(page, "The order's page offers a free sandbox label for the package's weight", async () => {
    const main = page.locator("main");
    const refusal = await refusalShown(page);
    if (refusal) throw new Error(refusal);
    const { order, label } = await orderFields(page);
    if (!order) throw new Error("The order's page shows no Ship to, Items or Status.");
    if (label) throw new Error(`The order's page already shows a label, tracking ${label["Tracking number"]}.`);
    if (order.Status !== "No label") throw new Error(`The order's page says "${order.Status}", not "No label".`);
    if (!await main.getByText("TEST order", { exact: true }).count()) throw new Error("The order's page doesn't say it's a TEST order.");
    // Ship offers only practice labels for TEST orders when its Settings turn sandbox labels off.
    if (await chosen(page, "Label kind") !== SANDBOX_KIND) throw new Error(`The label form offers "${await chosen(page, "Label kind")}", not a free Pitney Bowes sandbox label; turn TEST sandbox labels on in Ship Settings.`);
    const box = await chosen(page, "Box");
    const weight = (await weightField(page).inputValue()).trim();
    const expected = expectedWeight(order["Items' weight"], box);
    if (expected === null) throw new Error(`The test couldn't read the items' weight ("${order["Items' weight"]}") or the box's empty weight ("${box}").`);
    if (Number(weight) !== expected) throw new Error(`The weight field reads "${weight}", not the items' ${order["Items' weight"]} plus the box's empty weight, ${expected} oz.`);
    return `ships to ${order["Ship to"]}; ${box}; weight ${weight} oz filled in`;
  }, soft);

  // Without prices there is no label to buy, so this step stops the journey.
  let prices;
  await step(page, "See prices quotes USPS services for the package", async () => {
    const main = page.locator("main");
    const refusal = await refusalShown(page);
    if (refusal) throw new Error(refusal);
    // The browser sends no form with a value its own check refuses, so the press would do nothing.
    const weight = weightField(page);
    const refused = await weight.evaluate(input => input.validationMessage);
    if (refused) throw new Error(`The browser won't send the label form: it refuses the weight "${await weight.inputValue()}" ("${refused}").`);
    await main.getByRole("button", { name: "See prices", exact: true }).click();
    await afterPress(page, main.getByRole("combobox", { name: "Service", exact: true }));
    prices = await optionsOf(page, "Service");
    note("store admin label prices", prices.join("; "));
    if (!servicePrice(prices, service)) throw new Error(`Ship quoted no price for ${service}: ${prices.join("; ")}.`);
    return prices.join("; ");
  });

  // Every step after this one needs the label, so it stops the journey.
  let bought;
  await step(page, "Buy label buys the sandbox label at the quoted price", async () => {
    const main = page.locator("main");
    const price = servicePrice(prices, service);
    await choose(page, "Service", `${service}: ${price}`);
    await main.getByRole("button", { name: "Buy label", exact: true }).click();
    const said = await afterPress(page, main.getByText(/^Label bought, /));
    const toast = boughtMessage(said);
    if (!toast) throw new Error(`The Shipping page said "${said}" after Buy label, not "Label bought, $X.XX sandbox. Tracking ...".`);
    if (toast.price !== price) throw new Error(`The Shipping page says the label cost ${toast.price}, not the ${price} Ship quoted.`);
    const { order, label } = await orderFields(page);
    const problems = labelProblems(label, { service, ...toast });
    if (order?.Status !== "Label bought") problems.push(`the order's Status reads "${order?.Status ?? "nothing"}", not "Label bought"`);
    if (problems.length) throw new Error(`Ship sold the label, but ${problems.join(" and ")}.`);
    bought = toast;
    note("store admin label tracking", toast.tracking);
    return `${service}, ${toast.price} sandbox price, tracking ${toast.tracking}`;
  });

  let printed;
  await step(page, "Print label opens the label's PDF from Ship", async () => {
    const file = join(config.runDir, "store-admin-label.pdf");
    printed = await printLabel(page, file);
    note("store admin label pdf", `${printed.bytes} bytes, sha256 ${printed.sha256}`);
    const picture = renderLabelPdf(file);
    note("store admin label picture", `store-admin-label.pdf.png, ${picture.width}×${picture.height}, sha256 ${picture.sha256}`);
    await showLabelPicture(page, picture);
    return `${printed.bytes} bytes, sha256 ${printed.sha256.slice(0, 16)}…, shown ${picture.width}×${picture.height}`;
  }, soft);

  // The checks after this one are about a Completed order, so a label Commerce never collects stops the journey.
  await step(page, "Opening Commerce Orders collects the label and completes the order", async () => {
    // Commerce asks Ship for new labels each time Commerce Orders opens, and every 5 minutes.
    const deadline = Date.now() + config.completeWaitMs;
    await paceStore(PAGE_ROOM);
    let shown = await openOrder(page, number);
    while (shown.status !== "Completed" && Date.now() < deadline) {
      await page.waitForTimeout(30_000);
      await paceStore(PAGE_ROOM);
      shown = await openOrder(page, number);
    }
    if (shown.status !== "Completed") throw new Error(`#${number} still shows ${shown.status ?? "no status"} in Commerce Orders ${config.completeWaitMs / 1000}s after the label was bought.`);
    const problems = completionProblems(shown, { carrier: "USPS", tracking: bought.tracking });
    if (problems.length) throw new Error(`Commerce completed #${number}, but ${problems.join(" and ")}.`);
    return `#${number} Completed with carrier ${shown.carrier} and tracking ${shown.tracking}`;
  });

  // Commerce tells Ship as it completes the order, and before ship#45 the Shipping page lost the label then.
  await step(page, "Print label still opens the same PDF once the order is Completed", async () => {
    await openShipping(page, shipping);
    const row = await shippingRow(page, shipping, number);
    if (!row) throw new Error(`Shipping no longer lists #${number} (TEST).`);
    const status = await rowStatus(row);
    if (status !== "Label bought") throw new Error(`Shipping lists the Completed #${number} as "${status}", not "Label bought".`);
    await openRow(page, row, number);
    const { label } = await orderFields(page);
    if (!label) throw new Error(`#${number}'s page shows no label once the order is Completed, so it can't be printed or cancelled there.`);
    const problems = labelProblems(label, { service, ...bought });
    if (problems.length) throw new Error(`The Completed order's label differs from the one bought: ${problems.join(" and ")}.`);
    const again = await printLabel(page, join(config.runDir, "store-admin-label-completed.pdf"));
    note("store admin label pdf once Completed", `${again.bytes} bytes, sha256 ${again.sha256}`);
    if (printed && again.sha256 !== printed.sha256) {
      throw new Error(`Print label opened a different PDF (sha256 ${again.sha256.slice(0, 16)}…) from the one it opened before the order was Completed (${printed.sha256.slice(0, 16)}…).`);
    }
    return `listed "Label bought"; Print label opened ${printed ? "the same" : "a"} ${again.bytes}-byte PDF`;
  }, soft);

  // Cancelling is the last change the journey makes, so the check after it needs it to have worked.
  await step(page, "Cancel label voids the sandbox label and the order stays Completed", async () => {
    const main = page.locator("main");
    await openShippingOrder(page, shipping, number);
    const cancel = main.getByRole("button", { name: "Cancel label", exact: true });
    if (!await cancel.count()) throw new Error(`#${number}'s page offers no Cancel label.`);
    await cancel.click();
    const dialog = page.getByRole("dialog").or(page.getByRole("alertdialog")).first();
    await dialog.waitFor({ timeout: 15_000 });
    const asked = (await dialog.innerText()).replace(/\s+/g, " ").trim();
    if (!asked.includes(SANDBOX_CANCEL)) throw new Error(`The cancel dialog says "${asked}", not "${SANDBOX_CANCEL}"`);
    await dialog.getByRole("button", { name: "Cancel label", exact: true }).click();
    const said = await afterPress(page, main.getByText(/^Label cancelled\./));
    // A sandbox label's postage was never paid, so there is no refund to promise.
    if (said !== "Label cancelled.") throw new Error(`The Shipping page said "${said}", not "Label cancelled.".`);
    const { order, label } = await orderFields(page);
    if (label) throw new Error(`#${number}'s page still shows a live label after the cancel, tracking ${label["Tracking number"]}.`);
    if (order?.Status !== "Label cancelled") throw new Error(`#${number}'s Status reads "${order?.Status ?? "nothing"}", not "Label cancelled".`);
    if (!await main.getByText(COMPLETED_NOTE).count()) throw new Error(`#${number}'s page doesn't say the order is Completed in Commerce.`);
    if (!await openEarlierLabels(page)) throw new Error(`#${number}'s page lists no earlier labels, so the cancelled label isn't shown.`);
    const cancelled = (await orderFields(page)).earlier.find(fields => fields["Tracking number"] === `${bought.tracking} (test, not trackable)`);
    if (!cancelled?.Cancelled) throw new Error(`#${number}'s earlier labels show no cancelled label with tracking ${bought.tracking}.`);
    if (/refund/i.test(cancelled.Cancelled)) throw new Error(`The cancelled sandbox label reads "Cancelled ${cancelled.Cancelled}", promising a refund for postage nobody paid.`);
    return `"Label cancelled."; the label is under Earlier labels, cancelled ${cancelled.Cancelled}; the page says the order is Completed in Commerce`;
  });

  await step(page, "Shipping lists the order as Label cancelled and Commerce keeps it Completed", async () => {
    await openShipping(page, shipping);
    const row = await shippingRow(page, shipping, number);
    const status = row && await rowStatus(row);
    if (status !== "Label cancelled") throw new Error(`Shipping lists #${number} as "${status ?? "missing"}", not "Label cancelled".`);
    await paceStore(PAGE_ROOM);
    const problems = completionProblems(await openOrder(page, number), { carrier: "USPS", tracking: bought.tracking });
    if (problems.length) throw new Error(`After the cancel, Commerce Orders' #${number} ${problems.join(" and ")}.`);
    return `Shipping lists "Label cancelled"; Commerce Orders still shows #${number} Completed with tracking ${bought.tracking}`;
  }, soft);
}));
