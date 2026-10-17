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
