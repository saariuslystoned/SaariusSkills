/** The header cart link reads "Cart" when empty and "Cart, 2 items" otherwise; null when unreadable. */
export function cartCount(label) {
  if (label === "Cart") return 0;
  const count = label?.match(/^Cart, (\d+) items?$/)?.[1];
  return count === undefined ? null : Number(count);
}
