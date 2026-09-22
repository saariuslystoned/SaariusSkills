import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { copyFileSync, mkdtempSync, mkdirSync, realpathSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { TOOL_NAMES } from "../contract.mjs";

const root = fileURLToPath(new URL("../", import.meta.url));
const script = path.join(root, "scripts/setup.mjs");
const run = (target, args = ["--check"]) => spawnSync(process.execPath, [target, ...args], {
  encoding: "utf8", timeout: 25_000,
});

test("copied plugin without dependencies reports its own exact repair path", () => {
  const fixture = mkdtempSync(path.join(tmpdir(), "antigravity-acp-uninstalled-test-"));
  try {
    mkdirSync(path.join(fixture, "scripts"));
    copyFileSync(path.join(root, "contract.mjs"), path.join(fixture, "contract.mjs"));
    const target = path.join(fixture, "scripts/setup.mjs");
    copyFileSync(script, target);
    const result = run(target);
    assert.equal(result.status, 2, result.stderr);
    const report = JSON.parse(result.stdout);
    assert.equal(report.code, "DEPENDENCIES_MISSING");
    assert.deepEqual(report.repair, [process.execPath, realpathSync(target), "--install"]);
    assert.equal(report.pin.version, "1.1.1");
    assert.equal(report.pin.acpxRelease, "0.19.0");
    assert.equal(
      report.pin.acpxNpmIntegrity,
      "sha512-sgG0CkhuvVxgfiksXjIPEl9hsHZW0CpxywPdQeoIP5D31gwZE4nrnddLUUqaSCLb1UIM7LFPBL5qdvy15/+B6Q==",
    );
    assert.ok(Array.isArray(report.runtimeRepair));
  } finally {
    rmSync(fixture, { recursive: true, force: true });
  }
});

test("installed setup initializes real MCP and lists six tools without Antigravity", () => {
  const result = run(script);
  assert.equal(result.status, 0, result.stderr);
  const report = JSON.parse(result.stdout);
  assert.equal(report.code, "MCP_READY");
  assert.equal(report.liveAntigravityChecked, false);
  assert.equal(report.runtime.silentlyInstalled, false);
  assert.deepEqual(report.tools, [...TOOL_NAMES].sort());
  assert.equal(report.pin.registryRevision, "81bf71b55e15f630c4fb8a86d20d3088071d2071");
  assert.ok(Array.isArray(report.runtime.repair));
  assert.equal(report.auth.ultraAttribution, "unclaimed");
});
