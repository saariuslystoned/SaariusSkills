import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

// Planted bugs (function -> source line range) in the seed src/money.mjs.
const PLANTED = { splitEvenly: [4, 8], formatCents: [11, 15], parseAmount: [18, 23] };
const DECOYS = ["sumCents", "applyDiscount"];

function findings() {
  let text = "";
  try { text = readFileSync(new URL("../REVIEW.md", import.meta.url), "utf8"); } catch { return []; }
  const block = /```(?:json)?\s*([\s\S]*?)```/.exec(text);
  const candidates = [block?.[1], text];
  for (const c of candidates) {
    if (!c) continue;
    const start = c.indexOf("["), end = c.lastIndexOf("]");
    if (start < 0 || end < start) continue;
    try {
      const parsed = JSON.parse(c.slice(start, end + 1));
      if (Array.isArray(parsed)) return parsed.filter((f) => f && typeof f === "object");
    } catch { /* try next */ }
  }
  return [];
}
const matches = (f, name) => {
  const [lo, hi] = PLANTED[name];
  const line = Number(f.line);
  return f.function === name || (Number.isFinite(line) && line >= lo - 1 && line <= hi + 1 && !DECOYS.includes(f.function));
};

test("REVIEW.md contains a JSON findings array", () => assert.ok(findings().length > 0));
for (const name of Object.keys(PLANTED)) {
  test(`finds the ${name} bug`, () => assert.ok(findings().some((f) => matches(f, name)), name));
}
test("at most one false positive", () => {
  const fp = findings().filter((f) => !Object.keys(PLANTED).some((n) => matches(f, n)));
  assert.ok(fp.length <= 1, `false positives: ${JSON.stringify(fp)}`);
});
