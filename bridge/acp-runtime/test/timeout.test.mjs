import assert from "node:assert/strict";
import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import {
  BridgeError,
  DEFAULT_TIMEOUT_MS,
  MAX_TIMEOUT_MS,
  MIN_TIMEOUT_MS,
  parseTimeout,
  resolveDefaultTimeoutMs,
  timeoutMsZod,
} from "../timeout.mjs";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const requireFromCursorBridge = createRequire(path.join(repoRoot, "bridge/cursor-acp/package.json"));
const { z } = requireFromCursorBridge("zod");

test("shared timeout constants match the ACP job timeout policy", () => {
  assert.equal(MIN_TIMEOUT_MS, 1_000);
  assert.equal(DEFAULT_TIMEOUT_MS, 3_600_000);
  assert.equal(MAX_TIMEOUT_MS, 14_400_000);
});

test("resolveDefaultTimeoutMs returns 3600000 when SAARIUS_ACP_TIMEOUT_MS is unset or empty after trim", () => {
  assert.equal(resolveDefaultTimeoutMs({}), 3_600_000);
  assert.equal(resolveDefaultTimeoutMs({ SAARIUS_ACP_TIMEOUT_MS: undefined }), 3_600_000);
  assert.equal(resolveDefaultTimeoutMs({ SAARIUS_ACP_TIMEOUT_MS: "" }), 3_600_000);
  assert.equal(resolveDefaultTimeoutMs({ SAARIUS_ACP_TIMEOUT_MS: "   " }), 3_600_000);
  assert.equal(resolveDefaultTimeoutMs({ SAARIUS_ACP_TIMEOUT_MS: "\t\n " }), 3_600_000);
});

test("resolveDefaultTimeoutMs accepts whitespace-trimmed valid base-10 integers and exact bounds", () => {
  assert.equal(resolveDefaultTimeoutMs({ SAARIUS_ACP_TIMEOUT_MS: "1000" }), MIN_TIMEOUT_MS);
  assert.equal(resolveDefaultTimeoutMs({ SAARIUS_ACP_TIMEOUT_MS: "14400000" }), MAX_TIMEOUT_MS);
  assert.equal(resolveDefaultTimeoutMs({ SAARIUS_ACP_TIMEOUT_MS: "3600000" }), DEFAULT_TIMEOUT_MS);
  assert.equal(resolveDefaultTimeoutMs({ SAARIUS_ACP_TIMEOUT_MS: "  120000  " }), 120_000);
  assert.equal(resolveDefaultTimeoutMs({ SAARIUS_ACP_TIMEOUT_MS: "\t45000\n" }), 45_000);
});

test("resolveDefaultTimeoutMs rejects out-of-range, negative, decimal, non-integer, and garbage values with SAARIUS_ACP_TIMEOUT_MS in the error", () => {
  const invalidValues = [
    "0",
    "999",
    "14400001",
    "999999999999999999999",
    "-1",
    "-1000",
    "+1000",
    "1000.5",
    "3600000.0",
    "1e6",
    "1_000",
    "1000ms",
    "abc",
    "NaN",
    "Infinity",
    "${SAARIUS_ACP_TIMEOUT_MS:-3600000}",
    1000,
    null,
  ];

  for (const bad of invalidValues) {
    assert.throws(
      () => resolveDefaultTimeoutMs({ SAARIUS_ACP_TIMEOUT_MS: bad }),
      (error) => {
        assert.ok(error instanceof BridgeError);
        assert.equal(error.code, "INVALID_CONFIG");
        assert.match(error.message, /SAARIUS_ACP_TIMEOUT_MS/);
        assert.match(error.message, /1000/);
        assert.match(error.message, /14400000/);
        assert.ok(error.message.includes(String(bad)), `expected error message "${error.message}" to include bad value "${String(bad)}"`);
        return true;
      },
    );
  }
});

test("parseTimeout and timeoutMsZod preserve per-call validation semantics", () => {
  const schema = z.object({ timeoutMs: timeoutMsZod(z) });
  assert.equal(schema.parse({}).timeoutMs, undefined);
  assert.equal(schema.parse({ timeoutMs: MIN_TIMEOUT_MS }).timeoutMs, MIN_TIMEOUT_MS);
  assert.equal(schema.parse({ timeoutMs: MAX_TIMEOUT_MS }).timeoutMs, MAX_TIMEOUT_MS);
  assert.throws(() => schema.parse({ timeoutMs: MIN_TIMEOUT_MS - 1 }));
  assert.throws(() => schema.parse({ timeoutMs: MAX_TIMEOUT_MS + 1 }));
  assert.throws(() => schema.parse({ timeoutMs: 1_500.5 }));

  assert.equal(parseTimeout(undefined), DEFAULT_TIMEOUT_MS);
  assert.equal(parseTimeout(MIN_TIMEOUT_MS), MIN_TIMEOUT_MS);
  assert.equal(parseTimeout(MAX_TIMEOUT_MS), MAX_TIMEOUT_MS);
  for (const invalid of [0, MIN_TIMEOUT_MS - 1, MAX_TIMEOUT_MS + 1, 1_500.5, "3600000", null]) {
    assert.throws(
      () => parseTimeout(invalid),
      (error) => error instanceof BridgeError &&
        error.code === "INVALID_INPUT" &&
        error.message === `timeoutMs must be an integer between ${MIN_TIMEOUT_MS} and ${MAX_TIMEOUT_MS}`,
    );
  }
});
