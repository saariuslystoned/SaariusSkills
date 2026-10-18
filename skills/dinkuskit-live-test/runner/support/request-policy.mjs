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

/** Chromium pauses every hop, including redirects; install before navigating. */
export function filterPage(page, settings) {
  if (!installed.has(page)) installed.set(page, install(page, requestPolicy(settings)));
  return installed.get(page);
}

async function install(page, policy) {
  const session = await page.context().newCDPSession(page);
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
      const cookies = (await page.context().cookies(request.url))
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
  return page;
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
