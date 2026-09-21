import assert from "node:assert/strict";
import { existsSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { normalizeLines } from "../src/normalize-lines.mjs";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const bin = path.join(root, "bin", "normalize-lines.mjs");

test("normalizeLines converts CRLF and trailing spaces", () => {
  assert.equal(normalizeLines("ok  \r\n"), "ok\n");
});

test("bin/normalize-lines.mjs --check command is present", () => {
  assert.equal(existsSync(bin), true, "missing bin/normalize-lines.mjs --check command");
});
