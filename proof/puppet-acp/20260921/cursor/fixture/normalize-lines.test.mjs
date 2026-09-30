import assert from "node:assert/strict";
import test from "node:test";
import { normalizeLines } from "./normalize-lines.mjs";

test("converts CRLF to LF without removing blank lines", () => {
  assert.equal(normalizeLines("a\r\n\r\nb\r\n"), "a\n\nb\n");
});

test("preserves existing LF and blank lines", () => {
  assert.equal(normalizeLines("a\n\nb\n"), "a\n\nb\n");
});

test("converts lone CR to LF without removing blank lines", () => {
  assert.equal(normalizeLines("a\r\rb\r"), "a\n\nb\n");
});
