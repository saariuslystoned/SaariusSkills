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

test("a configured Ship and DinkusKit.com replace the default ones", () => {
  const staging = requestPolicy({ ...settings, ship: "https://ship.staging.test", account: "https://account.staging.test" });
  assert.equal(staging.allows("https://ship.staging.test/orders"), true);
  assert.equal(staging.allows("https://account.staging.test/account"), true);
  assert.equal(staging.allows("https://ship.dinkuskit.com/orders"), false);
  assert.equal(staging.allows("https://dinkuskit.com/account"), false);
  assert.throws(() => requestPolicy({ ...settings, ship: "http://ship.staging.test" }));
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

const guards = { route: async () => {}, routeWebSocket: async () => {}, on: () => {} };

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
    Authorization: "synthetic-store-key", Cookie: "store-session=synthetic; ship-session=synthetic", "CF-Access-Client-Secret": "synthetic", "X-Commerce-Guest-Capability": "synthetic", Accept: "text/html",
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

test("same-named cookies keep the order the browser sent them in", async () => {
  const { paused, commands } = await interceptor([{ name: "session", value: "root" }, { name: "session", value: "account" }]);
  await paused({ requestId: "order", request: { url: "https://dinkuskit.com/account", headers: { Cookie: "session=account; session=root" } } });
  assert.deepEqual(commands.at(-1).value.headers, [{ name: "Cookie", value: "session=account; session=root" }]);
});

async function contextRoute() {
  let handler;
  let listener;
  const context = { newCDPSession: async () => ({ on: () => {}, send: async () => {} }), cookies: async () => [],
    route: async (_, fn) => { handler = fn; }, routeWebSocket: async () => {}, on: (event, fn) => { if (event === "response") listener = fn; } };
  await filterPage({ context: () => context, on: () => {} }, settings);
  let lastRequest;
  const answer = async (url, method = "GET", requestHeaders = {}) => {
    const outcome = {};
    lastRequest = { url: () => url, method: () => method, frame: () => null, headers: () => ({}),
      headerValue: async name => requestHeaders[name] ?? null, timing: () => ({ startTime: Date.now(), responseStart: -1 }) };
    await handler({
      request: () => lastRequest,
      fulfill: async value => { outcome.fulfilled = value; },
      fallback: async value => { outcome.fallback = value ?? true; },
      abort: async reason => { outcome.aborted = reason; },
    });
    return outcome;
  };
  const loaded = (url, headers, { status = 200, body = Buffer.from("synthetic"), requestHeaders = {}, request, responseStart = -1 } = {}) => {
    const sent = Date.now();
    return listener({
      url: () => url, status: () => status, headers: () => headers, body: async () => body,
      request: () => request ?? { method: () => "GET", headerValue: async name => requestHeaders[name] ?? null,
        timing: () => ({ startTime: sent, responseStart }) },
    });
  };
  return { answer, loaded, lastRequest: () => lastRequest };
}

const immutable = { "cache-control": "public, max-age=31536000, immutable" };

test("the store's immutable files are answered from the run's copy after their first load", async () => {
  const { answer, loaded } = await contextRoute();
  const script = settings.store + "/_astro/guest-cart-client.synthetic.js";
  assert.deepEqual(await answer(script), { fallback: true });
  await loaded(script, { ...immutable, "content-type": "text/javascript", "content-encoding": "br", "content-length": "9" });
  const { fulfilled } = await answer(script);
  assert.equal(fulfilled.status, 200);
  assert.equal(fulfilled.body.toString(), "synthetic");
  assert.deepEqual(fulfilled.headers, { ...immutable, "content-type": "text/javascript" });
});

test("pages, files the store wants rechecked and other sites still reach the network", async () => {
  const { answer, loaded } = await contextRoute();
  const page = settings.store + "/products/synthetic";
  await loaded(page, { "cache-control": "public, max-age=0, must-revalidate" });
  assert.deepEqual(await answer(page), { fallback: true });
  const missing = settings.store + "/_astro/missing.synthetic.js";
  await loaded(missing, immutable, { status: 404 });
  assert.deepEqual(await answer(missing), { fallback: true });
  const stripe = "https://js.stripe.com/v3/synthetic.js";
  await loaded(stripe, immutable);
  assert.deepEqual(await answer(stripe), { fallback: true });
  const script = settings.store + "/_astro/kept.synthetic.js";
  await loaded(script, immutable);
  assert.deepEqual(await answer(script, "POST"), { fallback: true });
  for (const value of ["max-age=31536000, no-store, immutable", "public, max-age=31536000, immutable, no-cache",
    "max-age=31536000, immutable, no-cache=\"set-cookie\""]) {
    const unstored = settings.store + `/_astro/${encodeURIComponent(value)}.synthetic.js`;
    await loaded(unstored, { "cache-control": value });
    assert.deepEqual(await answer(unstored), { fallback: true }, value);
  }
});

test("a kept copy lasts only while the store says the file is fresh", async () => {
  const { answer, loaded } = await contextRoute();
  for (const headers of [{ "cache-control": "public, max-age=0, must-revalidate, immutable" },
    { "cache-control": "max-age=60, immutable", age: "60" }, { "cache-control": "immutable" }]) {
    const stale = settings.store + `/_astro/${encodeURIComponent(JSON.stringify(headers))}.synthetic.js`;
    await loaded(stale, headers);
    assert.deepEqual(await answer(stale), { fallback: true }, JSON.stringify(headers));
  }
  const script = settings.store + "/_astro/short.synthetic.js";
  await loaded(script, { "cache-control": "max-age=60, immutable", age: "30" });
  assert.equal((await answer(script)).fulfilled.status, 200);
  const now = Date.now;
  Date.now = () => now() + 31_000;
  try {
    assert.deepEqual(await answer(script), { fallback: true });
    await loaded(script, { "cache-control": "max-age=60, immutable" });
    assert.equal((await answer(script)).fulfilled.status, 200);
  } finally {
    Date.now = now;
  }
});

test("a kept copy's age counts from its Date and the time it took to arrive", async () => {
  const { answer, loaded } = await contextRoute();
  const dated = settings.store + "/_astro/dated.synthetic.js";
  await loaded(dated, { "cache-control": "max-age=60, immutable", date: new Date(Date.now() - 120_000).toUTCString(), age: "0" });
  assert.deepEqual(await answer(dated), { fallback: true });
  const slow = settings.store + "/_astro/slow.synthetic.js";
  await loaded(slow, { "cache-control": "max-age=60, immutable", age: "50" }, { responseStart: 20_000 });
  assert.deepEqual(await answer(slow), { fallback: true });
  const script = settings.store + "/_astro/recent.synthetic.js";
  await loaded(script, { "cache-control": "max-age=60, immutable", date: new Date(Date.now() - 30_000).toUTCString() });
  assert.equal((await answer(script)).fulfilled.status, 200);
  const now = Date.now;
  Date.now = () => now() + 31_000;
  try {
    assert.deepEqual(await answer(script), { fallback: true });
  } finally {
    Date.now = now;
  }
});

test("a page asking for a younger or longer-lasting copy than the kept one asks the store again", async () => {
  const { answer, loaded } = await contextRoute();
  const replays = { "max-age=300": true, "min-fresh=300": true, "max-age=60": false, "min-fresh=500": false, "max-age=soon": false };
  const file = asked => settings.store + `/_astro/${encodeURIComponent(asked)}.synthetic.js`;
  for (const asked of Object.keys(replays)) await loaded(file(asked), { "cache-control": "max-age=600, immutable" });
  const now = Date.now;
  Date.now = () => now() + 120_000;
  try {
    for (const [asked, replayed] of Object.entries(replays)) {
      assert.equal(Boolean((await answer(file(asked), "GET", { "cache-control": asked })).fulfilled), replayed, asked);
    }
  } finally {
    Date.now = now;
  }
});

test("a kept copy that varies answers only requests asking for the same version", async () => {
  const { answer, loaded } = await contextRoute();
  const script = settings.store + "/_astro/varies.synthetic.js";
  await loaded(script, { ...immutable, vary: "Accept-Encoding, Accept" }, { requestHeaders: { accept: "text/javascript", "accept-encoding": "br" } });
  assert.equal((await answer(script, "GET", { accept: "text/javascript", "accept-encoding": "gzip" })).fulfilled.status, 200);
  assert.deepEqual(await answer(script, "GET", { accept: "*/*", "accept-encoding": "br" }), { fallback: true });
  assert.equal((await answer(script, "GET", { accept: "text/javascript" })).fulfilled.status, 200);
  // The other version's answer from the store takes the copy's place.
  await loaded(script, { ...immutable, vary: "Accept" }, { body: Buffer.from("any"), requestHeaders: { accept: "*/*" } });
  assert.equal((await answer(script, "GET", { accept: "*/*" })).fulfilled.body.toString(), "any");
  const any = settings.store + "/_astro/any.synthetic.js";
  await loaded(any, { ...immutable, vary: "*" });
  assert.deepEqual(await answer(any), { fallback: true });
});

test("a request the page sends with no-cache asks the store again, and its answer replaces the copy", async () => {
  const { answer, loaded } = await contextRoute();
  const script = settings.store + "/_astro/refresh.synthetic.js";
  await loaded(script, immutable, { body: Buffer.from("old") });
  assert.equal((await answer(script)).fulfilled.body.toString(), "old");
  assert.deepEqual(await answer(script, "GET", { "cache-control": "no-cache" }), { fallback: true });
  await loaded(script, immutable, { body: Buffer.from("new"), requestHeaders: { "cache-control": "no-cache" } });
  assert.equal((await answer(script)).fulfilled.body.toString(), "new");
  for (const asked of [{ pragma: "no-cache" }, { "cache-control": "max-age=0" }, { "cache-control": "no-store" }]) {
    assert.deepEqual(await answer(script, "GET", asked), { fallback: true }, JSON.stringify(asked));
  }
  await loaded(script, immutable, { requestHeaders: { "cache-control": "no-store" } });
  assert.deepEqual(await answer(script), { fallback: true });
});

test("only the newest store answer from the network can be the copy, and it replaces the old one even when not kept", async () => {
  const { answer, loaded } = await contextRoute();
  const script = settings.store + "/_astro/newest.synthetic.js";
  await loaded(script, { ...immutable, vary: "Accept" }, { body: Buffer.from("old"), requestHeaders: { accept: "text/javascript" } });
  assert.deepEqual(await answer(script, "GET", { accept: "*/*" }), { fallback: true });
  await loaded(script, { "cache-control": "no-cache", vary: "*" }, { requestHeaders: { accept: "*/*" } });
  assert.deepEqual(await answer(script, "GET", { accept: "text/javascript" }), { fallback: true });
  let release;
  const older = loaded(script, immutable, { body: new Promise(resolve => { release = () => resolve(Buffer.from("older")); }) });
  await loaded(script, immutable, { body: Buffer.from("newer") });
  release();
  await older;
  assert.equal((await answer(script)).fulfilled.body.toString(), "newer");
  await loaded(script, immutable, { status: 404 });
  assert.deepEqual(await answer(script), { fallback: true });
});

test("a replayed answer never makes its copy last longer", async () => {
  const { answer, loaded, lastRequest } = await contextRoute();
  const script = settings.store + "/_astro/replayed.synthetic.js";
  await loaded(script, { "cache-control": "max-age=60, immutable" });
  const now = Date.now;
  try {
    Date.now = () => now() + 31_000;
    assert.equal((await answer(script)).fulfilled.status, 200);
    await loaded(script, { "cache-control": "max-age=60, immutable" }, { request: lastRequest() });
    Date.now = () => now() + 61_000;
    assert.deepEqual(await answer(script), { fallback: true });
  } finally {
    Date.now = now;
  }
});

test("quoted Cache-Control numbers count", async () => {
  const { answer, loaded } = await contextRoute();
  const script = settings.store + "/_astro/quoted.synthetic.js";
  await loaded(script, { "cache-control": 'public, max-age="31536000", immutable' });
  assert.equal((await answer(script)).fulfilled.status, 200);
  assert.deepEqual(await answer(script, "GET", { "cache-control": 'max-age="0"' }), { fallback: true });
});
