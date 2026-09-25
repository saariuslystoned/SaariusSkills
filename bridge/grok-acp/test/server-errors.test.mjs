import assert from "node:assert/strict";
import test from "node:test";
import { BridgeError } from "../broker.mjs";
import { serializeFailure } from "../server-errors.mjs";

test("unknown MCP failures do not expose raw exception messages", () => {
  const result = serializeFailure(new Error("provider sentinel should not cross the MCP boundary"));
  assert.deepEqual(result, {
    code: "BRIDGE_ERROR",
    message: "Grok ACP request failed.",
  });
  assert.doesNotMatch(JSON.stringify(result), /provider sentinel/);
});

test("BridgeError code survives while message and details are redacted", () => {
  const sentinel = "authorization: Bearer ghp_FAKE_SENTINEL_VALUE";
  const result = serializeFailure(new BridgeError("HOST_POLICY", sentinel, {
    nested: sentinel,
    values: [sentinel],
    apiKey: "fake-api-key-sentinel",
  }));
  assert.equal(result.code, "HOST_POLICY");
  assert.doesNotMatch(JSON.stringify(result), /ghp_FAKE_SENTINEL_VALUE/);
  assert.equal(result.message, "authorization=[redacted]");
  assert.equal(result.details.nested, "authorization=[redacted]");
  assert.deepEqual(result.details.values, ["authorization=[redacted]"]);
  assert.equal(result.details.apiKey, "[redacted]");
});
