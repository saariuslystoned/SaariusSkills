import assert from "node:assert/strict";
import { normalizeLines } from "./normalize.mjs";
assert.equal(normalizeLines("a  \r\n\n b \n"), "a\n b");
assert.equal(normalizeLines(""), "");
assert.equal(normalizeLines(" \n\t"), "");
assert.equal(normalizeLines("one\ntwo\n"), "one\ntwo");
console.log("4 normalization cases passed");
