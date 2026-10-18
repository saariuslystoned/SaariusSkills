/** The selected store and the services its canonical journeys use, never sibling stores. */
const PRIVATE_HEADERS = /^(authorization|proxy-authorization|cookie|cf-access-client-id|cf-access-client-secret|x-api-key|x-emdash-key)$/i;
const loopback = hostname => ["localhost", "127.0.0.1", "[::1]"].includes(hostname);

function siteOrigin(value) {
  const url = new URL(value);
  if (url.username || url.password || url.pathname !== "/" || url.search || url.hash
      || (url.protocol !== "https:" && !(url.protocol === "http:" && loopback(url.hostname)))) {
    throw new Error("The request filter needs a site origin, without a path or credentials.");
  }
  return url.origin;
}

export function requestPolicy({ store, accessOrigins = [] }) {
  const selected = siteOrigin(store);
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
    if (url.origin === selected) return true;
    if (url.protocol !== "https:" || url.port) return false;
    return ["https://dinkuskit.com", "https://ship.dinkuskit.com"].includes(url.origin)
      || url.hostname === "stripe.com" || url.hostname.endsWith(".stripe.com")
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
const frames = new WeakMap();
const guarded = new WeakMap();

/** Chromium pauses every hop, including redirects; install before navigating. */
export function filterPage(page, settings) {
  if (!installed.has(page)) installed.set(page, install(page, requestPolicy(settings), settings));
  return installed.get(page);
}

async function install(page, policy, settings) {
  await guardContext(page.context(), policy, settings);
  page.on("frameattached", frame => { filterFrame(frame, policy); });
  await intercept(await page.context().newCDPSession(page), page.context(), policy);
  return page;
}

/** A cross-site frame runs in its own renderer, which the page's interceptor never sees. */
function filterFrame(frame, policy) {
  if (!frames.has(frame)) frames.set(frame, frame.page().context().newCDPSession(frame)
    .then(session => intercept(session, frame.page().context(), policy))
    .catch(() => {})); // A same-site frame has no session of its own and is already covered.
  return frames.get(frame);
}

/**
 * Popups the site opens and cross-site frames start before an interceptor can attach. The context
 * checks every first request and holds it until its page or frame has an interceptor, so the
 * redirect hops that follow are checked too.
 */
function guardContext(context, policy, settings) {
  if (!guarded.has(context)) guarded.set(context, (async () => {
    await context.route("**/*", async route => {
      const request = route.request();
      if (!policy.allows(request.url())) return route.abort("blockedbyclient");
      let frame = null;
      try { frame = request.frame(); } catch {} // A worker's request belongs to its page's interceptor.
      if (frame) {
        await filterPage(frame.page(), settings);
        if (frame !== frame.page().mainFrame()) await filterFrame(frame, policy);
      }
      return route.fallback();
    });
    // Chromium's Fetch interception never pauses a WebSocket handshake.
    await context.routeWebSocket(url => !policy.allows(url.href.replace(/^ws/, "http")), ws => ws.close());
  })());
  return guarded.get(context);
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
      const sent = new Set(received.split(";").map(value => value.trim()));
      const cookies = (await context.cookies(request.url))
        .map(({ name, value }) => `${name}=${value}`).filter(value => sent.has(value));
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
