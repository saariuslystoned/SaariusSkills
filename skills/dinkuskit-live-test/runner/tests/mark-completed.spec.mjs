import { test, expect } from "../support/browser.mjs";
import { placeTestOrder } from "../support/checkout.mjs";
import { config } from "../support/env.mjs";
import { note, record } from "../support/proof.mjs";
import { numberOf, openOrder, orderShown, ordersListed, testOrders } from "../support/orders-admin.mjs";
import { confirmed, notePlugins, openAdmin } from "../support/store-admin.mjs";
import { journey, step } from "../support/steps.mjs";

// What an order's page in Commerce Orders shows for a carrier or tracking number nobody gave.
const NOT_RECORDED = "Not recorded";

/** Places a Stripe TEST order, or takes the order DINKUS_E2E_ORDERS_TO_COMPLETE names for this part of the journey. */
async function orderToComplete(page, name, given, who) {
  if (given) {
    record(name, "SKIP", `completing order #${given} from DINKUS_E2E_ORDERS_TO_COMPLETE instead of placing one`);
    return { number: given };
  }
  let placed;
  await step(page, name, async () => {
    placed = await placeTestOrder(page);
    if (placed.state !== "paid") throw new Error(`Commerce reports this checkout as "${placed.state}", not paid.`);
    if (!placed.orderId) throw new Error("Commerce's checkout status named no order.");
    note(`${who}'s order`, placed.orderId);
    return `Commerce recorded the payment for ${placed.orderId}`;
  });
  return { orderId: placed.orderId };
}

/** Where an open Completed order differs from the carrier and tracking number it should show. */
function completionProblems(shown, { carrier, tracking }) {
  const problems = [];
  if (shown.status !== "Completed") problems.push(`it shows ${shown.status ?? "no status"}, not Completed`);
  if (shown.carrier !== carrier) problems.push(`its carrier reads "${shown.carrier ?? "nothing"}", not "${carrier}"`);
  if (shown.tracking !== tracking) problems.push(`its tracking number reads "${shown.tracking ?? "nothing"}", not "${tracking}"`);
  return problems;
}

/** Commerce's orders API, beside Commerce Orders: where agents and the CLI read and complete orders. */
function ordersApi() {
  const api = config.ordersAdmin.replace("/_emdash/admin/plugins/", "/_emdash/api/plugins/");
  if (api === config.ordersAdmin) throw new Error("DINKUS_E2E_ORDERS_ADMIN isn't a plugin page in the store admin, so the test can't tell where Commerce's orders API is.");
  // The agent's key belongs to the store, so it is never sent anywhere else.
  if (new URL(api).origin !== config.store) throw new Error("DINKUS_E2E_ORDERS_ADMIN is on another site than DINKUS_E2E_STORE, so the test won't send the store's key there.");
  return api;
}

const hostOf = location => { try { return new URL(location ?? "", config.store).hostname; } catch { return "an unreadable address"; } };
const redirected = response => response.status >= 300 && response.status < 400;

/**
 * A call from the test itself rather than from its browser, so neither the agent's key nor the
 * answer that carries it ever reaches the browser's trace. A failure names only what went wrong.
 */
async function send(url, init, what) {
  return fetch(url, { ...init, redirect: "manual", signal: AbortSignal.timeout(30_000) })
    .catch(error => { throw new Error(`The test couldn't reach ${what} (${error.cause?.code ?? error.name}).`); });
}

/** A refused call's HTTP status and the reason EmDash or Commerce gave, or where it was sent instead. */
function refusal(response, answer) {
  if (redirected(response)) return `HTTP ${response.status} to ${hostOf(response.headers.get("location"))}`;
  const reason = answer?.error?.message;
  return `HTTP ${response.status}${typeof reason === "string" ? `, "${reason.slice(0, 200)}"` : ""}`;
}

/** The cookies the owner's browser sends to one store address: its EmDash sign-in, and its Access sign-in when Access fronts it. */
async function ownerCookies(page, url) {
  return (await page.context().cookies(url)).map(cookie => `${cookie.name}=${cookie.value}`).join("; ");
}

/** How a key the test couldn't delete ends, for the finding. */
const keyLeft = ({ name, expiresAt }) => `It stops working at ${expiresAt.slice(11, 16)} UTC on its own; to end it sooner, revoke "${name}" under Settings, API Tokens in the store admin.`;

/** Deletes a key by its ID as the signed-in owner; a refusal fails with its reason. */
async function revokeKey(page, id) {
  const url = `${config.store}/_emdash/api/admin/api-tokens/${encodeURIComponent(id)}`;
  const response = await send(url, { method: "DELETE", headers: { cookie: await ownerCookies(page, url), "X-EmDash-Request": "1" } }, "EmDash's API tokens");
  const answer = await response.json().catch(() => null);
  if (!response.ok || answer?.data?.revoked !== true) throw new Error(`EmDash didn't delete the agent's key (${refusal(response, answer)}).`);
}

/**
 * Asks EmDash, as the signed-in owner, for an admin key that stops working after an hour; EmDash
 * lets a key call a plugin's private routes only with the admin scope. Only the key's name and when
 * it stops working ever reach the proof.
 */
async function makeAgentKey(page, name) {
  const url = `${config.store}/_emdash/api/admin/api-tokens`;
  const expiresAt = new Date(Date.now() + 60 * 60 * 1000).toISOString();
  const response = await send(url, { method: "POST", body: JSON.stringify({ name, scopes: ["admin"], expiresAt }),
    headers: { cookie: await ownerCookies(page, url), "content-type": "application/json", "X-EmDash-Request": "1" } }, "EmDash's API tokens")
    .catch(error => { throw new Error(`${error.message} EmDash may have made the key anyway. ${keyLeft({ name, expiresAt })}`); });
  const answer = await response.json().catch(() => null);
  const made = answer?.data;
  const id = made?.info?.id;
  if (response.status === 201 && typeof made?.token === "string" && id) return { name, expiresAt, id, key: made.token };
  if (response.status !== 201) throw new Error(`EmDash didn't make the agent's key (${refusal(response, answer)}).`);
  // A key the test can't use is deleted at once rather than left working for its hour.
  const left = id
    ? await revokeKey(page, id).then(() => "The test deleted it again.", error => `${error.message} ${keyLeft({ name, expiresAt })}`)
    : keyLeft({ name, expiresAt });
  throw new Error(`EmDash said it made the agent's key but sent none the test could use. ${left}`);
}

/**
 * One call to Commerce's orders API as an agent makes it, with the key and nothing of the owner's
 * sign-in. When Cloudflare Access fronts the store's API too, the call also carries the test's
 * Access sign-in, as an agent's Access service token would; EmDash still goes by the key alone.
 */
async function agentCall(page, agent, input) {
  const headers = { authorization: `Bearer ${agent.key}`, "content-type": "application/json", ...(agent.access && { cookie: agent.access }) };
  const response = await send(agent.api, { method: "POST", headers, body: JSON.stringify(input) }, "Commerce's orders API");
  if (!agent.access && redirected(response) && hostOf(response.headers.get("location")).endsWith(".cloudflareaccess.com")) {
    const access = (await page.context().cookies(agent.api)).find(cookie => cookie.name === "CF_Authorization");
    if (!access) throw new Error("Cloudflare Access sends the agent's calls to its sign-in page, and the test has no Access sign-in to carry for the store's API.");
    agent.access = `${access.name}=${access.value}`;
    note("agent's Access sign-in", "Cloudflare Access fronts the store's API, so the agent's calls carry the test's Access sign-in beside the key");
    return agentCall(page, agent, input);
  }
  return { response, answer: await response.json().catch(() => null) };
}

/** What Commerce's orders API answers the agent; a refusal fails with its reason. */
async function agentAsk(page, agent, input) {
  const { response, answer } = await agentCall(page, agent, input);
  if (!response.ok || answer?.success !== true) throw new Error(`Commerce's orders API refused the agent's "${input.action}" (${refusal(response, answer)}).`);
  return answer.data;
}

/** The agent's view of an order, giving Orders a minute to keep its copy of a new one; null when it never does. */
async function agentOrder(page, agent, orderId) {
  const deadline = Date.now() + 60_000;
  for (;;) {
    const { order } = await agentAsk(page, agent, { action: "show", orderId });
    if (order || Date.now() > deadline) return order ?? null;
    await page.waitForTimeout(5_000);
  }
}

/** Deletes the agent's key as the signed-in owner, then checks that a call with it is refused. */
async function deleteAgentKey(page, agent) {
  await revokeKey(page, agent.id).catch(error => { throw new Error(`${error.message} ${keyLeft(agent)}`); });
  const after = await agentCall(page, agent, { action: "show", orderId: agent.orderId ?? "order:none" })
    .catch(error => { throw new Error(`EmDash deleted the agent's key, but the test couldn't try the key again: ${error.message}`); });
  if (after.response.status !== 401 || after.answer?.error?.code !== "INVALID_TOKEN") {
    throw new Error(`EmDash deleted the agent's key, but a call with it got ${refusal(after.response, after.answer)} instead of HTTP 401 for an unknown key. ${keyLeft(agent)}`);
  }
  return `EmDash deleted "${agent.name}", and a call with it now gets HTTP 401`;
}

// Completing an order without a label: the owner marks a paid TEST order completed in Commerce
// Orders, typing a carrier and tracking number, and an agent completes another through Commerce's
// orders API, sending neither. Both end Completed.
test("Mark as completed", { tag: "@running" }, journey(async ({ page }) => {
  expect(config.store, `Set DINKUS_E2E_STORE to the store's address (in ${config.settingsFile})`).not.toBe("");
  // Every action gets a limit, so a control that never shows fails its step instead of holding the run.
  page.context().setDefaultTimeout(60_000);
  const stamp = new Date().toISOString().replace(/^\d{4}-(\d\d)-(\d\d)T(\d\d):(\d\d):(\d\d).*$/, "$1$2-$3$4$5");
  // Unique to the second and plainly the live test's, so one run's tracking number never passes for another's.
  const typed = { carrier: "USPS", tracking: `LIVE-TEST-${stamp}` };
  // A typo in the orders to complete stops the run before it places or completes any order. Entries
  // are compared as the order numbers they pick, so "1003,01003" counts as the same order twice.
  const given = config.ordersToComplete.map(number => /^#?\d+$/.test(number) ? Number(number.replace(/^#/, "")) : NaN);
  expect(given.length <= 2 && given.every(number => Number.isSafeInteger(number) && number > 0) && new Set(given).size === given.length,
    `DINKUS_E2E_ORDERS_TO_COMPLETE reads "${config.ordersToComplete.join(",")}"; set it to one or two different order numbers like 1003,1004, or leave it empty to place new orders (in ${config.settingsFile})`).toBe(true);
  const [ownerGiven, agentGiven] = given;
  const soft = { soft: true };

  // Without Commerce Orders nothing can be marked completed, so this step stops the journey.
  await step(page, "The owner can open Commerce Orders", async () => {
    await openAdmin(page, config.ordersAdmin);
    await ordersListed(page);
    await notePlugins(page);
    return "Commerce Orders opened in the store admin";
  });

  // An order that wasn't placed can't be completed, so a failed order stops the journey.
  const ownerOrder = await orderToComplete(page, "A shopper places a Stripe TEST order for the owner to complete", ownerGiven, "owner");

  let ownerNumber;
  await step(page, "The owner marks the order completed with a carrier and tracking number", async () => {
    const number = ownerOrder.number ?? await numberOf(page, ownerOrder.orderId, "Processing");
    const before = await openOrder(page, number);
    // The test only ever completes TEST orders.
    if (!before.test) throw new Error(`Order #${number} isn't a TEST order, so the test leaves it alone.`);
    if (before.status !== "Processing") throw new Error(`Order #${number} shows ${before.status ?? "no status"}, not Processing, so it can't be marked completed.`);
    ownerNumber = number;
    note("owner's order number", `#${number}`);
    await page.getByRole("button", { name: "Complete order", exact: true }).click();
    await page.getByRole("textbox", { name: "Carrier (optional)", exact: true }).fill(typed.carrier);
    await page.getByRole("textbox", { name: "Tracking number (optional)", exact: true }).fill(typed.tracking);
    await page.getByRole("button", { name: "Complete order", exact: true }).click();
    await confirmed(page, "Order completed");
    const problems = completionProblems(await orderShown(page), typed);
    if (problems.length) throw new Error(`Commerce said "Order completed", but ${problems.join(" and ")}.`);
    return `#${number} Completed with carrier ${typed.carrier} and tracking number ${typed.tracking}`;
  }, soft);

  if (!ownerNumber) record("Commerce Orders keeps the owner's order Completed", "SKIP", "the owner's order wasn't marked completed");
  else await step(page, "Commerce Orders keeps the owner's order Completed", async () => {
    const listed = (await testOrders(page)).find(order => order.number === ownerNumber);
    if (listed?.status !== "Completed") throw new Error(`Commerce Orders lists #${ownerNumber} as ${listed?.status ?? "missing"}, not Completed.`);
    const problems = completionProblems(await openOrder(page, ownerNumber), typed);
    if (problems.length) throw new Error(`Opened again, #${ownerNumber} ${problems.join(" and ")}.`);
    return `listed Completed, and its page still shows carrier ${typed.carrier} and tracking number ${typed.tracking}`;
  }, soft);

  // The agent works with an admin key the test makes from the owner's sign-in and deletes at the end.
  let agent;
  try {
    // Without a key the agent can do nothing, so this step stops the journey.
    await step(page, "The test makes a one-hour key for the agent", async () => {
      const api = ordersApi();
      agent = { ...await makeAgentKey(page, `Live test agent ${stamp}`), api };
      note("agent's key", `"${agent.name}", stops working at ${agent.expiresAt}`);
      return `EmDash made the admin key "${agent.name}", which stops working at ${agent.expiresAt.slice(11, 16)} UTC`;
    });

    const agentPlaced = await orderToComplete(page, "A shopper places a second Stripe TEST order for the agent to complete", agentGiven, "agent");

    let agentDone;
    await step(page, "An agent marks the order completed through Commerce's orders API, sending no carrier or tracking number", async () => {
      const orderId = agentPlaced.orderId ?? (await openOrder(page, agentPlaced.number)).orderId;
      if (!orderId) throw new Error(`Order #${agentPlaced.number}'s page in Commerce Orders shows no order ID for the agent to use.`);
      agent.orderId = orderId;
      const before = await agentOrder(page, agent, orderId);
      if (!before) throw new Error(`Commerce's orders API still doesn't know order ${orderId} a minute later.`);
      const label = before.number ? `#${before.number}` : orderId;
      // The test only ever completes TEST orders.
      if (before.test !== true) throw new Error(`Order ${label} isn't a TEST order, so the test leaves it alone.`);
      if (before.status !== "processing") throw new Error(`Commerce's orders API says order ${label} is ${before.status ?? "in no status"}, not processing, so it can't be marked completed.`);
      const { result, order } = await agentAsk(page, agent, { action: "complete", orderId, version: before.version });
      if (result !== "saved") throw new Error(`Commerce answered "${result}", not "saved", to completing ${label} at version ${before.version}.`);
      const problems = [];
      if (order?.status !== "completed") problems.push(`the order is ${order?.status ?? "missing"}, not completed`);
      if (order?.version !== before.version + 1) problems.push(`its version is ${order?.version ?? "missing"}, not ${before.version + 1}`);
      if (!order?.completed?.at) problems.push("it has no completion time");
      if (order?.completed?.carrier || order?.completed?.tracking) problems.push("it has a carrier or tracking number the agent never sent");
      if (problems.length) throw new Error(`Commerce saved the agent's change, but ${problems.join(" and ")}.`);
      agentDone = { orderId, number: order.number };
      return `${label} completed at version ${order.version}, with no carrier or tracking number`;
    }, soft);

    if (!agentDone) record("Commerce Orders shows the agent's order Completed", "SKIP", "the agent's order wasn't marked completed");
    else await step(page, "Commerce Orders shows the agent's order Completed", async () => {
      // Orders numbers an order when its page next opens, so one the agent completed first may have no number yet.
      const number = agentDone.number ?? await numberOf(page, agentDone.orderId, "Completed");
      note("agent's order number", `#${number}`);
      const listed = (await testOrders(page)).find(order => order.number === number);
      if (listed?.status !== "Completed") throw new Error(`Commerce Orders lists #${number} as ${listed?.status ?? "missing"}, not Completed.`);
      const problems = completionProblems(await openOrder(page, number), { carrier: NOT_RECORDED, tracking: NOT_RECORDED });
      if (problems.length) throw new Error(`Opened, #${number} ${problems.join(" and ")}.`);
      return `#${number} is listed Completed, and its page shows carrier and tracking number "${NOT_RECORDED}"`;
    }, soft);
  } finally {
    if (agent) await step(page, "The test deletes the agent's key", () => deleteAgentKey(page, agent), soft);
  }
}));
