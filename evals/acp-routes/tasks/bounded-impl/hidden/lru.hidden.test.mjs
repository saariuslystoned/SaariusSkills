import test from "node:test";
import assert from "node:assert/strict";
import { LRUCache } from "../src/lru.mjs";

test("rejects bad capacity", () => {
  for (const cap of [0, -1, 1.5, Number.NaN, "2", undefined]) assert.throws(() => new LRUCache(cap), RangeError, String(cap));
});
test("set is chainable and size tracks entries", () => {
  const c = new LRUCache(3);
  assert.equal(c.set("a", 1).set("b", 2), c);
  assert.equal(c.size, 2);
});
test("get marks recency", () => {
  const c = new LRUCache(2);
  c.set("a", 1).set("b", 2);
  c.get("a");
  c.set("c", 3);
  assert.equal(c.has("a"), true);
  assert.equal(c.has("b"), false);
});
test("has and peek do not mark recency", () => {
  const c = new LRUCache(2);
  c.set("a", 1).set("b", 2);
  c.has("a");
  assert.equal(c.peek("a"), 1);
  c.set("c", 3);
  assert.equal(c.has("a"), false);
});
test("updating an existing key refreshes it without growing", () => {
  const c = new LRUCache(2);
  c.set("a", 1).set("b", 2).set("a", 10).set("c", 3);
  assert.equal(c.size, 2);
  assert.equal(c.get("a"), 10);
  assert.equal(c.has("b"), false);
});
test("keys are most recently used first", () => {
  const c = new LRUCache(3);
  c.set("a", 1).set("b", 2).set("c", 3);
  c.get("a");
  assert.deepEqual([...c.keys()], ["a", "c", "b"]);
});
test("onEvict fires only for capacity evictions", () => {
  const evicted = [];
  const c = new LRUCache(1, { onEvict: (k, v) => evicted.push([k, v]) });
  c.set("a", 1).set("b", 2);
  c.delete("b");
  c.set("c", 3);
  c.clear();
  assert.deepEqual(evicted, [["a", 1]]);
});
test("delete reports whether it removed something", () => {
  const c = new LRUCache(2);
  c.set("a", 1);
  assert.equal(c.delete("a"), true);
  assert.equal(c.delete("a"), false);
  assert.equal(c.size, 0);
});
test("undefined values are still present", () => {
  const c = new LRUCache(2);
  c.set("u", undefined);
  assert.equal(c.has("u"), true);
  assert.equal(c.size, 1);
});
test("keys use SameValueZero", () => {
  const c = new LRUCache(3);
  const obj = {};
  c.set(Number.NaN, "nan").set(obj, "obj").set(0, "zero");
  assert.equal(c.get(Number.NaN), "nan");
  assert.equal(c.get(obj), "obj");
  assert.equal(c.get(-0), "zero");
  assert.equal(c.get({}), undefined);
});
test("capacity one keeps only the latest", () => {
  const c = new LRUCache(1);
  c.set("a", 1).set("b", 2);
  assert.deepEqual([...c.keys()], ["b"]);
});
test("clear empties the cache", () => {
  const c = new LRUCache(2);
  c.set("a", 1).set("b", 2).clear();
  assert.equal(c.size, 0);
  assert.equal(c.get("a"), undefined);
});
