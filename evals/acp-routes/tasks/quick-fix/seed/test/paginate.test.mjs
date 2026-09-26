import test from "node:test";
import assert from "node:assert/strict";
import { paginate } from "../src/paginate.mjs";

test("first page of ten items, size 3", () => {
  const r = paginate([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 1, 3);
  assert.deepEqual(r.items, [1, 2, 3]);
  assert.equal(r.totalPages, 4);
});
