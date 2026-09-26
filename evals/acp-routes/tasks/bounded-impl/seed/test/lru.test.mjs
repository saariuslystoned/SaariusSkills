import test from "node:test";
import assert from "node:assert/strict";
import { LRUCache } from "../src/lru.mjs";

test("stores and reads a value", () => {
  const c = new LRUCache(2);
  c.set("a", 1);
  assert.equal(c.get("a"), 1);
});

test("evicts the least recently used entry", () => {
  const c = new LRUCache(2);
  c.set("a", 1).set("b", 2).set("c", 3);
  assert.equal(c.has("a"), false);
});
