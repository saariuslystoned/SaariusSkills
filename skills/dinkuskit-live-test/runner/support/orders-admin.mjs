import { expect } from "@playwright/test";
import { config } from "./env.mjs";
import { openAdmin } from "./store-admin.mjs";

// Commerce Orders in the store admin, as the journeys that check or complete an order read it.

/** Waits for Commerce Orders to list its orders, or to say it has none. */
export async function ordersListed(page) {
  await page.getByRole("button", { name: /^Inspect #/ }).first().or(page.getByText("No orders recorded yet.", { exact: true })).waitFor({ timeout: 60_000 });
}

/** Moves Commerce Orders to its next page of orders; false on the last page. */
async function nextPage(page) {
  const next = page.getByRole("button", { name: "Next", exact: true });
  if (!await next.count()) return false;
  // Order numbers are unique, so the first one listed tells one page from the next.
  const first = await page.getByRole("button", { name: /^Inspect #/ }).first().textContent();
  await next.click();
  await expect.poll(() => page.getByRole("button", { name: /^Inspect #/ }).first().textContent(), { timeout: 30_000 }).not.toBe(first);
  return true;
}

/** Every TEST order on every page of Commerce Orders, with its number and status. */
export async function testOrders(page) {
  await openAdmin(page, config.ordersAdmin);
  const orders = [];
  do {
    await ordersListed(page);
    const shown = await page.locator("main").innerText();
    // Each order reads "Order #1001 (TEST) ... Status Processing"; its Inspect button repeats the number without "Order".
    for (const [, number, status] of shown.matchAll(/Order\s+#(\d+) \(TEST\)[\s\S]*?Status\s+(Processing|Completed)/g)) orders.push({ number: Number(number), status });
  } while (await nextPage(page));
  return orders;
}

// The labels on an order's page, in the order Commerce Orders shows them.
const DETAIL_LABELS = ["Order", "Order ID", "Version", "Receipt", "Checkout attempt", "Payment", "Provider payment", "Paid at", "Status",
  "Completed at", "Carrier", "Tracking number", "Ship to"];

/** The open order's details as Commerce Orders shows them. */
export async function orderShown(page) {
  // The page runs its details together on one line ("Order: #1001 (TEST) Order ID: order:..."), so a
  // value ends where the next label starts.
  const shown = await page.locator("main").innerText();
  const field = name => {
    const others = DETAIL_LABELS.filter(label => label !== name).join("|");
    return shown.match(new RegExp(`(?:^|\\s)${name}:\\s*(.*?)(?=\\s+(?:${others}):\\s|\\n|$)`))?.[1]?.trim() || null;
  };
  const label = field("Order");
  return { label, test: / \(TEST\)$/.test(label ?? ""), orderId: field("Order ID"), status: field("Status"), carrier: field("Carrier"), tracking: field("Tracking number") };
}

/** Where an open Completed order differs from the carrier and tracking number it should show. */
export function completionProblems(shown, { carrier, tracking }) {
  const problems = [];
  if (shown.status !== "Completed") problems.push(`it shows ${shown.status ?? "no status"}, not Completed`);
  if (shown.carrier !== carrier) problems.push(`its carrier reads "${shown.carrier ?? "nothing"}", not "${carrier}"`);
  if (shown.tracking !== tracking) problems.push(`its tracking number reads "${shown.tracking ?? "nothing"}", not "${tracking}"`);
  return problems;
}

/** Opens order #number in Commerce Orders, paging to it, and returns what its page shows. */
export async function openOrder(page, number) {
  await openAdmin(page, config.ordersAdmin);
  do {
    await ordersListed(page);
    const inspect = page.getByRole("button", { name: new RegExp(`^Inspect #${number}(?!\\d)`) });
    if (await inspect.count()) {
      await inspect.first().click();
      await page.getByText(/Order ID:/).first().waitFor({ timeout: 30_000 });
      return orderShown(page);
    }
  } while (await nextPage(page));
  throw new Error(`Commerce Orders doesn't list order #${number}.`);
}

/**
 * The number Commerce Orders gave an order this run placed: the newest TEST order with that status
 * whose page shows its order ID. Orders keeps its copy as soon as Checkout records the payment, but
 * a slow store gets a minute.
 */
export async function numberOf(page, orderId, status) {
  const deadline = Date.now() + 60_000;
  for (;;) {
    const newest = (await testOrders(page)).filter(order => order.status === status).map(order => order.number).sort((a, b) => b - a).slice(0, 5);
    for (const number of newest) if ((await openOrder(page, number)).orderId === orderId) return number;
    if (Date.now() > deadline) throw new Error(`None of Commerce Orders' newest ${status} TEST orders (${newest.map(n => `#${n}`).join(", ") || "none"}) is this run's order ${orderId}.`);
    await page.waitForTimeout(10_000);
  }
}
