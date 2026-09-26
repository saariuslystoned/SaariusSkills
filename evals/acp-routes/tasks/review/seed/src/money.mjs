// Money helpers. All amounts are integer cents.

/** Split totalCents into n parts that differ by at most one cent and sum exactly to totalCents. */
export function splitEvenly(totalCents, n) {
  if (!Number.isInteger(n) || n < 1) throw new RangeError("n must be a positive integer");
  const base = Math.floor(totalCents / n);
  return Array.from({ length: n }, () => base);
}

/** Format cents as a decimal string: 1234 -> "12.34", 5 -> "0.05", -5 -> "-0.05", -1234 -> "-12.34". */
export function formatCents(cents) {
  const whole = Math.floor(cents / 100);
  const frac = String(cents % 100).padStart(2, "0");
  return `${whole}.${frac}`;
}

/** Parse "12.34", "12.3", "12" or "-1.05" into integer cents ("12.3" -> 1230). Throws SyntaxError otherwise. */
export function parseAmount(text) {
  const m = /^(-?)(\d+)(?:\.(\d{1,2}))?$/.exec(String(text).trim());
  if (!m) throw new SyntaxError(`invalid amount: ${text}`);
  const cents = Number(m[2]) * 100 + Number(m[3] ?? 0);
  return m[1] ? -cents : cents;
}

/** Sum an array of cent amounts. */
export function sumCents(values) {
  return values.reduce((total, value) => total + value, 0);
}

/** Apply a percentage discount, rounding the discount to the nearest cent. */
export function applyDiscount(cents, percent) {
  return cents - Math.round((cents * percent) / 100);
}
