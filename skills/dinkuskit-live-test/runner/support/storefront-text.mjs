/** The header cart link reads "Cart" when empty and "Cart, 2 items" otherwise; null when unreadable. */
export function cartCount(label) {
  if (label === "Cart") return 0;
  const count = label?.match(/^Cart, (\d+) items?$/)?.[1];
  return count === undefined ? null : Number(count);
}

// What a page says when it claims a shopper can't buy: the template's demo banner, catalog
// notices, product notices and preview copy ("Purchases and checkout are unavailable", "It is not
// purchasable", "This product can't be bought right now", "Editorial previews cannot be purchased").
const CANT_BUY = /checkout\s+(?:is\s+|are\s+)?(?:currently\s+)?(?:un|not\s+)available|not\s+purchasable|cannot\s+be\s+purchased|can(?:no|'|\u2019)t\s+be\s+bought|purchasing\s+is\s+not\s+available|no\s+purchase\s+will\s+be\s+completed/i;

/** The sentences in a page's visible text that tell shoppers they can't check out or buy. */
export function cantBuyClaims(text) {
  const sentences = String(text ?? "").split(/\n+|(?<=[.!?])\s+/).map(part => part.replace(/\s+/g, " ").trim());
  return [...new Set(sentences.filter(sentence => CANT_BUY.test(sentence)))];
}

/** The first dollar amount in a text, in cents ("$1,234.50" is 123450); null when there is none. */
export function money(text) {
  const amount = String(text ?? "").match(/\$\s?(\d+(?:,\d{3})*)(?:\.(\d{1,2}))?/);
  if (!amount) return null;
  return Number(amount[1].replaceAll(",", "")) * 100 + Number((amount[2] ?? "0").padEnd(2, "0"));
}

/** Cents as the shopper reads them: 2500 is "$25.00". */
export const dollars = cents => `$${(cents / 100).toFixed(2)}`;

/**
 * The total a cart shows, from its visible text: { label, cents } for its "Subtotal", or for its
 * "Total" when it has no subtotal; null when it shows neither. The amount may sit on the label's
 * line ("Subtotal $25.00") or the next one, as in a list of totals.
 */
export function cartTotal(text) {
  const lines = String(text ?? "").split(/\n+/).map(line => line.trim()).filter(Boolean);
  const totals = lines.flatMap((line, i) => {
    const label = line.match(/^(?:(?:estimated|order|cart)\s+)?(?:sub)?total\b/i)?.[0];
    const cents = label === undefined ? null : money(line.slice(label.length)) ?? money(lines[i + 1]);
    return cents === null ? [] : [{ label: label[0].toUpperCase() + label.slice(1).toLowerCase(), cents }];
  });
  return totals.find(total => /subtotal/i.test(total.label)) ?? totals[0] ?? null;
}
