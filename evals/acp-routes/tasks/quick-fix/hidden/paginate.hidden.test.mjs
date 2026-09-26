import test from "node:test";
import assert from "node:assert/strict";
import { paginate } from "../src/paginate.mjs";

const ten = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10];

test("first page", () => assert.deepEqual(paginate(ten, 1, 3).items, [1, 2, 3]));
test("middle page", () => assert.deepEqual(paginate(ten, 2, 3).items, [4, 5, 6]));
test("last partial page", () => {
  const r = paginate(ten, 4, 3);
  assert.deepEqual(r.items, [10]);
  assert.equal(r.hasNext, false);
  assert.equal(r.hasPrev, true);
});
test("exact multiple has no extra page", () => {
  const r = paginate([1, 2, 3, 4, 5, 6], 2, 3);
  assert.equal(r.totalPages, 2);
  assert.equal(r.hasNext, false);
});
test("empty list has one empty page", () => {
  const r = paginate([], 1, 5);
  assert.deepEqual(r.items, []);
  assert.equal(r.totalPages, 1);
  assert.equal(r.hasNext, false);
  assert.equal(r.hasPrev, false);
});
test("page beyond range returns empty items", () => {
  const r = paginate(ten, 9, 3);
  assert.deepEqual(r.items, []);
  assert.equal(r.hasPrev, true);
  assert.equal(r.hasNext, false);
});
test("hasNext on a non-last page", () => assert.equal(paginate(ten, 3, 3).hasNext, true));
test("totals are reported", () => {
  const r = paginate(ten, 1, 4);
  assert.equal(r.totalItems, 10);
  assert.equal(r.totalPages, 3);
  assert.equal(r.pageSize, 4);
  assert.equal(r.page, 1);
});
test("rejects non-positive and non-integer arguments", () => {
  for (const [p, s] of [[0, 3], [1, 0], [-1, 3], [1.5, 3], [1, 2.5], [Number.NaN, 3]]) {
    assert.throws(() => paginate(ten, p, s), RangeError, `${p},${s}`);
  }
});
test("does not mutate input", () => {
  const copy = [...ten];
  paginate(ten, 2, 3);
  assert.deepEqual(ten, copy);
});
