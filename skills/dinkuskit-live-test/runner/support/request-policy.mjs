/** The selected store and the services its canonical journeys use, never sibling stores. */
const PRIVATE_HEADERS = /^(authorization|proxy-authorization|cookie|cf-access-client-id|cf-access-client-secret|x-api-key|x-emdash-key|x-commerce-guest-capability)$/i;
const loopback = hostname => ["localhost", "127.0.0.1", "[::1]"].includes(hostname);

function siteOrigin(value) {
  const url = new URL(value);
  if (url.username || url.password || url.pathname !== "/" || url.search || url.hash
      || (url.protocol !== "https:" && !(url.protocol === "http:" && loopback(url.hostname)))) {
    throw new Error("The request filter needs a site origin, without a path or credentials.");
  }
  return url.origin;
}

export function requestPolicy({ store, accessOrigins = [], ship = "https://ship.dinkuskit.com", account = "https://dinkuskit.com" }) {
  const selected = siteOrigin(store);
  // The Ship and DinkusKit.com the run is set to use (DINKUS_E2E_SHIP, DINKUS_E2E_ACCOUNT), exactly.
  const services = new Set([siteOrigin(ship), siteOrigin(account)]);
  const access = new Set(accessOrigins.map(value => {
    const origin = siteOrigin(value);
    if (!new URL(origin).hostname.endsWith(".cloudflareaccess.com")) {
      throw new Error("Access origins must name the store's exact Cloudflare Access host.");
    }
    return origin;
  }));
  const allowed = value => {
    let url;
    try { url = new URL(value); } catch { return false; }
    if (url.username || url.password) return false;
    if (url.origin === selected || services.has(url.origin)) return true;
    if (url.protocol !== "https:" || url.port) return false;
    return url.hostname === "stripe.com" || url.hostname.endsWith(".stripe.com")
      || url.hostname === "stripecdn.com" || url.hostname.endsWith(".stripecdn.com")
      || access.has(url.origin);
  };
  return {
    allows: allowed,
    isStore: value => { try { return new URL(value).origin === selected; } catch { return false; } },
    // Browser cookies remain scoped by their jar when no explicit header is supplied.
    publicHeaders: headers => Object.fromEntries(Object.entries(headers).filter(([key]) => !PRIVATE_HEADERS.test(key))),
  };
}

const installed = new WeakMap();
const guarded = new WeakMap();

/** Chromium pauses every hop, including redirects; install before navigating. */
export function filterPage(page, settings) {
  if (!installed.has(page)) installed.set(page, install(page, requestPolicy(settings), settings));
  return installed.get(page);
}

async function install(page, policy, settings) {
  await guardContext(page.context(), policy, settings);
  await intercept(await page.context().newCDPSession(page), page.context(), policy);
  return page;
}

/**
 * The page's interceptor sees its own requests and redirects, but not a cross-site frame's (Chromium
 * gives those their own renderer) or a popup's first one, sent before the popup's interceptor exists.
 * The context route sees every request's first hop from any of them: it refuses an off-list
 * destination, removes store headers, and holds a popup's request until its interceptor is ready.
 */
function guardContext(context, policy, settings) {
  if (!guarded.has(context)) guarded.set(context, (async () => {
    const copies = immutableCopies(context, policy);
    await context.route("**/*", async route => {
      const request = route.request();
      if (!policy.allows(request.url())) return route.abort("blockedbyclient");
      let frame = null;
      try { frame = request.frame(); } catch {} // A worker's request belongs to its page's interceptor.
      try {
        if (frame) await filterPage(frame.page(), settings);
      } catch {
        // No interceptor could attach (the page is closing, say), so nothing would check a redirect.
        return route.abort("blockedbyclient").catch(() => {});
      }
      if (policy.isStore(request.url())) {
        const copy = request.method() === "GET" ? await copies.answer(request) : undefined;
        return copy ? route.fulfill(copy) : route.fallback();
      }
      // This first request left before its interceptor attached, so strip store headers here too.
      const headers = request.headers();
      const kept = policy.publicHeaders(Object.fromEntries(Object.entries(headers).filter(([name]) => name.toLowerCase() !== "cookie")));
      const cookie = Object.entries(headers).find(([name]) => name.toLowerCase() === "cookie");
      if (Object.keys(kept).length + (cookie ? 1 : 0) === Object.keys(headers).length) return route.fallback();
      return route.fallback({ headers: cookie ? { ...kept, [cookie[0]]: cookie[1] } : kept });
    });
    // Chromium's Fetch interception never pauses a WebSocket handshake.
    await context.routeWebSocket(url => !policy.allows(url.href.replace(/^ws/, "http")), ws => ws.close());
  })());
  return guarded.get(context);
}

/**
 * Playwright turns Chromium's HTTP cache off while any route is set, so the run would fetch every
 * store script on every page view, far more often than a shopper's browser, and cross the store's
 * per-visitor request limit. A store file sent as immutable (its hashed /_astro/ build files) is
 * answered from this context's own copy after its first load, for as long as it stays fresh, as the
 * browser's cache would answer it. Copies stay with their context, so a new shopper's browser starts
 * empty, as a new shopper's does.
 */
function immutableCopies(context, policy) {
  const copies = new Map();
  context.on("response", async response => {
    try {
      const url = response.url();
      if (copies.has(url) || !policy.isStore(url) || response.status() !== 200 || response.request().method() !== "GET") return;
      const headers = response.headers();
      const directives = new Map((headers["cache-control"] ?? "").toLowerCase().split(",").map(part => {
        const [name, value = ""] = part.split("=");
        return [name.trim(), value.trim()];
      }));
      // immutable never overrides a store's no-store or no-cache, and holds only while the file is fresh.
      const fresh = Number(directives.get("max-age")) - (Number(headers.age) || 0);
      if (!directives.has("immutable") || directives.has("no-store") || directives.has("no-cache") || !(fresh > 0)) return;
      // A file that varies answers only requests sending the same values for the headers it names. The
      // kept body is already decoded, so Accept-Encoding never matters, and Playwright sets its length.
      const vary = (headers.vary ?? "").toLowerCase().split(",").map(name => name.trim()).filter(name => name && name !== "accept-encoding");
      if (vary.includes("*")) return;
      const chosenBy = await Promise.all(vary.map(async name => [name, await response.request().headerValue(name)]));
      const kept = Object.fromEntries(Object.entries(headers).filter(([name]) =>
        !["content-encoding", "content-length", "transfer-encoding", "set-cookie"].includes(name)));
      const until = Date.now() + fresh * 1000;
      copies.set(url, { until, chosenBy, answer: { status: 200, headers: kept, body: await response.body() } });
    } catch {} // The page closed before the body arrived, say; the next load fetches the file again.
  });
  return {
    /** The copy to answer this request with, if any; a stale copy is dropped so the next load is kept. */
    async answer(request) {
      const copy = copies.get(request.url());
      if (!copy || copy.until <= Date.now()) return void copies.delete(request.url());
      for (const [name, value] of copy.chosenBy) if (await request.headerValue(name) !== value) return;
      return copy.answer;
    },
  };
}

async function intercept(session, context, policy) {
  const handle = async ({ requestId, request }) => {
    if (!policy.allows(request.url)) {
      await session.send("Fetch.failRequest", { requestId, errorReason: "BlockedByClient" });
      return;
    }
    const headers = policy.isStore(request.url) ? request.headers : policy.publicHeaders(request.headers);
    if (!policy.isStore(request.url)) {
      // Rebuild only the destination's browser cookies, never a store Cookie override.
      const received = Object.entries(request.headers).find(([name]) => name.toLowerCase() === "cookie")?.[1] ?? "";
      // Keep the browser's order: a server reading the first of two same-named cookies must get the same one.
      const jar = new Set((await context.cookies(request.url)).map(({ name, value }) => `${name}=${value}`));
      const cookies = received.split(";").map(value => value.trim()).filter(value => jar.has(value));
      if (cookies.length) headers.Cookie = cookies.join("; ");
    }
    await session.send("Fetch.continueRequest", {
      requestId, headers: Object.entries(headers).map(([name, value]) => ({ name, value: String(value) })),
    });
  };
  session.on("Fetch.requestPaused", event => handle(event).catch(() =>
    session.send("Fetch.failRequest", { requestId: event.requestId, errorReason: "Failed" }).catch(() => {})));
  await session.send("Fetch.enable", { patterns: [{ urlPattern: "*", requestStage: "Request" }] });
}

/** Direct photo/link/PDF probes use the same sites and check redirects before following. */
export async function filteredGet(client, address, settings, options = {}) {
  const policy = requestPolicy(settings);
  let url = address;
  for (let hop = 0; hop < 6; hop++) {
    if (!policy.allows(url)) throw new Error("A direct request left the selected sites.");
    const headers = policy.isStore(url) ? options.headers : policy.publicHeaders(options.headers ?? {});
    const response = await client.get(url, { ...options, headers, maxRedirects: 0 });
    const location = response.headers().location;
    if (![301, 302, 303, 307, 308].includes(response.status()) || !location) return response;
    const next = new URL(location, url).href;
    await response.dispose();
    if (!policy.isStore(next)) options = { ...options, headers: policy.publicHeaders(options.headers ?? {}) };
    url = next;
  }
  throw new Error("Too many redirects in a direct site request.");
}
