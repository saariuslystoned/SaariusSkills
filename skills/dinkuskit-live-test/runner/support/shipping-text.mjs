// What the Ship plugin's Shipping page says, read as text (dinkuskit/ship src/pages.ts and src/admin.ts).

/** Where a plugin's Shipping page sits in the store admin. */
const SHIPPING_PATH = /^\/_emdash\/admin\/plugins\/[^/]+\/shipping$/;

/** The Shipping pages among the store admin's menu links (absolute URLs), each once. */
export function shippingPages(hrefs, store) {
  const pages = new Set();
  for (const href of hrefs) {
    let url;
    try { url = new URL(href, store); } catch { continue; }
    if (url.origin === store && SHIPPING_PATH.test(url.pathname) && !url.search && !url.hash) pages.add(url.href);
  }
  return [...pages];
}

/** The price and tracking number in the Shipping page's "Label bought" message for a sandbox label, or null. */
export function boughtMessage(text) {
  const [, price, tracking] = /^Label bought, (\$\d+\.\d\d) sandbox\. Tracking ([A-Z0-9]+)\.$/.exec(String(text).trim()) ?? [];
  return tracking ? { price, tracking } : null;
}

/** The price a Service option shows for `service` after a quote ("USPS Ground Advantage: $5.12"), or null. */
export function servicePrice(options, service) {
  for (const option of options) {
    const price = String(option).trim().startsWith(`${service}: `) && /: (\$\d+\.\d\d)$/.exec(String(option).trim())?.[1];
    if (price) return price;
  }
  return null;
}

const ounces = (text, pattern) => {
  const found = pattern.exec(String(text ?? "").trim())?.[1];
  return found === undefined ? NaN : Number(found);
};

/**
 * The package weight the label form should start with: the items' weight ("12.5 oz") plus the
 * chosen box's empty weight ("Mailer: 10 × 8 × 2 in, 3 oz empty"), to a tenth of an ounce and within
 * Ship's 0.1 to 1120 oz. Null when either can't be read.
 */
export function expectedWeight(items, box) {
  const total = ounces(items, /^(\d+(?:\.\d+)?) oz$/) + ounces(box, /, (\d+(?:\.\d+)?) oz empty$/);
  return Number.isFinite(total) ? Math.max(0.1, Math.min(1120, Math.round(total * 10) / 10)) : null;
}

/** Where a sandbox label's fields on an order's page differ from the label Ship sold. */
export function labelProblems(fields, { service, tracking, price }) {
  if (!fields) return ["the order's page shows no label"];
  const wanted = { Service: service, "Tracking number": `${tracking} (test, not trackable)`, Postage: `${price} sandbox price, nothing charged` };
  return Object.entries(wanted).filter(([name, value]) => fields[name] !== value)
    .map(([name, value]) => `its ${name} reads "${fields[name] ?? "nothing"}", not "${value}"`);
}
