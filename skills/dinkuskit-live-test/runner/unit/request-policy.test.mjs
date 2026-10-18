import assert from "node:assert/strict";
import test from "node:test";
import { requestPolicy, filterPage, filteredGet } from "../support/request-policy.mjs";

const settings = { store: "https://e2e.sm0ky.dev", accessOrigins: ["https://store-team.cloudflareaccess.com"] };
const policy = requestPolicy(settings);

test("only the selected store, required services and exact Access hosts are allowed", () => {
  for (const url of [settings.store, settings.store + "/_emdash/api/media/image?id=photo&w=3471",
    "https://checkout.stripe.com/c/pay/test", "https://js.stripe.com/v3", "https://b.stripecdn.com/file",
    "https://dinkuskit.com/account", "https://ship.dinkuskit.com/orders", settings.accessOrigins[0] + "/cdn-cgi/access/login"]) {
    assert.equal(policy.allows(url), true, url);
  }
  for (const url of ["https://beta.sm0ky.dev", "https://e2e-v2.sm0ky.dev", "https://other.cloudflareaccess.com",
    "https://store-team.cloudflareaccess.com.evil.test", "https://stripe.com.evil.test", "https://evilstripe.com",
    "http://e2e.sm0ky.dev", "https://e2e.sm0ky.dev:444", "https://user:password@e2e.sm0ky.dev", "file:///tmp/photo", "bad url"]) {
    assert.equal(policy.allows(url), false, url);
  }
});

test("photo dimensions do not narrow a store request", () => {
  for (const width of [1, 300, 347, 600, 1200, 8192]) {
    assert.ok(policy.allows(`${settings.store}/_emdash/api/media/image/photo.webp?w=${width}&h=${width + 7}`));
  }
});

test("malformed or wildcard origins cannot broaden the site list", () => {
  for (const store of ["https://e2e.sm0ky.dev/path", "https://x@y.test", "ftp://example.test", "https://e2e.sm0ky.dev?token=secret"]) {
    assert.throws(() => requestPolicy({ store }));
  }
  assert.throws(() => requestPolicy({ ...settings, accessOrigins: ["https://example.test"] }));
});

const guards = { route: async () => {}, routeWebSocket: async () => {} };

async function interceptor(cookies = []) {
  let paused;
  const commands = [];
  const session = { on: (_, fn) => { paused = fn; }, send: async (method, value) => { commands.push({ method, value }); } };
  const context = { newCDPSession: async () => session, cookies: async () => cookies, ...guards };
  await filterPage({ context: () => context, on: () => {} }, settings);
  return { paused: event => paused(event), commands };
}

test("third-party requests cannot inherit store auth headers", async () => {
  const { paused, commands } = await interceptor([{ name: "ship-session", value: "synthetic" }]);
  await paused({ requestId: "one", request: { url: "https://ship.dinkuskit.com/orders", headers: {
    Authorization: "synthetic-store-key", Cookie: "store-session=synthetic; ship-session=synthetic", "CF-Access-Client-Secret": "synthetic", Accept: "text/html",
  } } });
  const forwarded = commands.at(-1);
  assert.equal(forwarded.method, "Fetch.continueRequest");
  assert.deepEqual(Object.fromEntries(forwarded.value.headers.map(({ name, value }) => [name, value])),
    { Accept: "text/html", Cookie: "ship-session=synthetic" });
});

test("each redirect hop is separately checked with scoped headers", async () => {
  const { paused, commands } = await interceptor();
  await paused({ requestId: "same-hop-id", request: { url: settings.store + "/go", headers: { Authorization: "synthetic" } } });
  assert.equal(commands.at(-1).value.headers[0].value, "synthetic");
  await paused({ requestId: "same-hop-id", request: { url: "https://dinkuskit.com/account", headers: { Authorization: "synthetic" } } });
  assert.deepEqual(commands.at(-1).value.headers, []);
  await paused({ requestId: "same-hop-id", request: { url: "https://e2e-v2.sm0ky.dev", headers: {} } });
  assert.equal(commands.at(-1).method, "Fetch.failRequest");
});

test("off-list request is stopped before forwarding headers", async () => {
  const { paused, commands } = await interceptor();
  await paused({ requestId: "blocked", request: { url: "https://e2e-v2.sm0ky.dev", headers: { Authorization: "synthetic" } } });
  assert.deepEqual(commands.at(-1), { method: "Fetch.failRequest", value: { requestId: "blocked", errorReason: "BlockedByClient" } });
});

test("a reused persistent page has one interceptor", async () => {
  let sessions = 0;
  const context = { ...guards, newCDPSession: async () => {
    sessions++;
    return { on: () => {}, send: async () => {} };
  } };
  const page = { context: () => context, on: () => {} };
  await Promise.all([filterPage(page, settings), filterPage(page, settings)]);
  await filterPage(page, settings);
  assert.equal(sessions, 1);
});

test("direct probes check redirect destinations and do not forward store headers", async () => {
  const calls = [];
  const client = { get: async (url, options) => {
    calls.push({ url, options });
    return { status: () => calls.length === 1 ? 302 : 200,
      headers: () => ({ location: "https://ship.dinkuskit.com/label.pdf" }), dispose: async () => {} };
  } };
  await filteredGet(client, settings.store + "/label", settings, { headers: { Authorization: "synthetic", Accept: "application/pdf" } });
  assert.equal(calls.length, 2);
  assert.equal(calls[0].options.maxRedirects, 0);
  assert.deepEqual(calls[1].options.headers, { Accept: "application/pdf" });
});

test("direct probes never contact an off-list redirect or initial address", async () => {
  let calls = 0;
  const client = { get: async () => { calls++; return { status: () => 302,
    headers: () => ({ location: "https://e2e-v2.sm0ky.dev/private" }), dispose: async () => {} }; } };
  await assert.rejects(filteredGet(client, settings.store + "/go", settings), /left the selected sites/);
  assert.equal(calls, 1);
  await assert.rejects(filteredGet(client, "https://example.com/", settings), /left the selected sites/);
  assert.equal(calls, 1);
});

test("the filter does not add a cookie the browser omitted", async () => {
  const { paused, commands } = await interceptor([{ name: "private-session", value: "synthetic" }]);
  await paused({ requestId: "no-cookie", request: { url: "https://ship.dinkuskit.com/orders", headers: { Accept: "text/html" } } });
  assert.deepEqual(commands.at(-1).value.headers, [{ name: "Accept", value: "text/html" }]);
});
