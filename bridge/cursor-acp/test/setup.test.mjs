import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { copyFileSync, mkdtempSync, mkdirSync, realpathSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const root = fileURLToPath(new URL("../", import.meta.url));
const script = path.join(root, "scripts/setup.mjs");
const run = (target, args = ["--check"]) => spawnSync(process.execPath, [target, ...args], {
  encoding: "utf8", timeout: 25_000,
});

test("copied plugin without dependencies reports its own exact repair path", () => {
  const fixture = mkdtempSync(path.join(tmpdir(), "cursor-acp-uninstalled-test-"));
  try {
    mkdirSync(path.join(fixture, "scripts"));
    const target = path.join(fixture, "scripts/setup.mjs");
    copyFileSync(script, target);
    const result = run(target);
    assert.equal(result.status, 2, result.stderr);
    const report = JSON.parse(result.stdout);
    assert.equal(report.code, "DEPENDENCIES_MISSING");
    assert.deepEqual(report.repair, [process.execPath, realpathSync(target), "--install"]);
  } finally {
    rmSync(fixture, { recursive: true, force: true });
  }
});

test("installed setup initializes real MCP and lists six tools without Cursor", () => {
  const result = run(script);
  assert.equal(result.status, 0, result.stderr);
  const report = JSON.parse(result.stdout);
  assert.equal(report.code, "MCP_READY");
  assert.equal(report.liveCursorChecked, false);
  assert.deepEqual(report.tools, ["cancel", "delegate", "readiness", "result", "status", "steer"]
    .map((name) => `cursor_acp_${name}`));
});
