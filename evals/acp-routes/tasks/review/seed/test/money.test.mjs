import test from "node:test";
import assert from "node:assert/strict";
import { applyDiscount, formatCents, parseAmount, splitEvenly, sumCents } from "../src/money.mjs";

test("happy paths", () => {
  assert.deepEqual(splitEvenly(300, 3), [100, 100, 100]);
  assert.equal(formatCents(1234), "12.34");
  assert.equal(parseAmount("12.34"), 1234);
  assert.equal(sumCents([1, 2, 3]), 6);
  assert.equal(applyDiscount(1000, 10), 900);
});
