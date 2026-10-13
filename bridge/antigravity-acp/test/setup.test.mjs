import assert from "node:assert/strict";
import { spawn, spawnSync } from "node:child_process";
import { copyFileSync, mkdtempSync, mkdirSync, realpathSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { TOOL_NAMES } from "../contract.mjs";

const root = fileURLToPath(new URL("../", import.meta.url));
const script = path.join(root, "scripts/setup.mjs");
const runtimeRoot = mkdtempSync(path.join(tmpdir(), "antigravity-acp-runtime-store-test-"));
const runtimeSetup = path.join(root, "../acp-runtime/prepare.mjs");
let runtimeReady = false;
function ensureRuntime() {
  if (runtimeReady) return;
  const result = spawnSync(process.execPath, [runtimeSetup, "--bridge", "antigravity-acp"], {
    encoding: "utf8",
    timeout: 120_000,
    env: { ...process.env, SAARIUS_ACP_RUNTIME_ROOT: runtimeRoot },
  });
  assert.equal(result.status, 0, result.stderr || result.stdout);
  runtimeReady = true;
}
const run = (target, args = ["--check"]) => spawnSync(process.execPath, [target, ...args], {
  encoding: "utf8",
  timeout: 25_000,
  env: { ...process.env, SAARIUS_ACP_RUNTIME_ROOT: runtimeRoot },
});

test.after(() => rmSync(runtimeRoot, { recursive: true, force: true }));

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
    assert.equal(report.pin.acpxRelease, "0.19.4");
    assert.equal(report.pin.acpxSourceCommit, "8e396609238086dee6a407fdb3b3ac46dbdedd70");
    assert.equal(report.pin.acpxNpmGitHead, null);
    assert.equal(
      report.pin.lastInspectedSourceCommit,
      "50a47ad10a75431cbc276ec9b555d11fe1f69c84",
    );
    assert.equal(report.pin.lastInspectedSourceRelease, "0.17.1");
    assert.equal(
      report.pin.acpxNpmIntegrity,
      "sha512-fN1c3Ype4LrwZoeJwcZEnyO+1ArThgymwswmJyd52dHKaz+3hjkR6lYdlyBPOZYIIcCVARezcfvkFUNxsylSBA==",
    );
    assert.ok(Array.isArray(report.runtimeRepair));
  } finally {
    rmSync(fixture, { recursive: true, force: true });
  }
});

test("installed setup initializes real MCP and lists six tools without Antigravity", () => {
  ensureRuntime();
  const result = run(script);
  assert.equal(result.status, 0, result.stderr);
  const report = JSON.parse(result.stdout);
  assert.equal(report.code, "MCP_READY");
  assert.equal(report.liveAntigravityChecked, false);
  assert.equal(report.runtime.silentlyInstalled, false);
  assert.deepEqual(report.tools, [...TOOL_NAMES].sort());
  assert.equal(report.pin.registryRevision, "81bf71b55e15f630c4fb8a86d20d3088071d2071");
  assert.equal(report.pin.acpxSourceCommit, "8e396609238086dee6a407fdb3b3ac46dbdedd70");
  assert.equal(report.pin.acpxNpmGitHead, null);
  assert.equal(report.pin.lastInspectedSourceRelease, "0.17.1");
  assert.ok(Array.isArray(report.runtime.repair));
  assert.equal(report.auth.ultraAttribution, "unclaimed");
});

test("prepared antigravity-acp starts entrypoint in http mode without ERR_MODULE_NOT_FOUND", async () => {
  ensureRuntime();
  const runtimeStore = await import("../../acp-runtime/runtime-store.mjs");
  const ready = await runtimeStore.inspectRuntime({
    pluginRoot: path.resolve(root, "../.."),
    bridge: "antigravity-acp",
    env: { ...process.env, SAARIUS_ACP_RUNTIME_ROOT: runtimeRoot },
  });
  assert.equal(ready.state, "ready");
  const entry = path.join(ready.root, "bridge", "antigravity-acp", "server.mjs");
  const stateRoot = mkdtempSync(path.join(tmpdir(), "antigravity-acp-http-state-"));
  try {
    const child = spawn(process.execPath, [entry, "--transport", "http"], {
      stdio: ["ignore", "pipe", "pipe"],
      env: {
        ...process.env,
        SAARIUS_ACP_RUNTIME_ROOT: runtimeRoot,
        SAARIUS_ANTIGRAVITY_ACP_STATE_DIR: stateRoot,
        SAARIUS_MUSE_ACP_STATE_DIR: path.join(stateRoot, "muse"),
        SAARIUS_ACP_HTTP_PORT: "0",
      },
    });
    let stderr = "";
    const started = new Promise((resolve, reject) => {
      child.stderr.setEncoding("utf8");
      child.stderr.on("data", (chunk) => {
        stderr += chunk;
        if (stderr.includes('"listening"') || stderr.includes("ERR_MODULE_NOT_FOUND")) {
          resolve();
        }
      });
      child.once("error", reject);
      child.once("exit", () => {
        resolve();
      });
    });
    const timeout = new Promise((_, reject) =>
      setTimeout(() => reject(new Error(`Timed out waiting for startup; stderr: ${stderr}`)), 15_000),
    );
    await Promise.race([started, timeout]);
    child.kill("SIGTERM");
    await new Promise((resolve) => child.once("exit", resolve));

    assert.ok(!stderr.includes("ERR_MODULE_NOT_FOUND"), `entrypoint failed with ERR_MODULE_NOT_FOUND: ${stderr}`);
    assert.ok(stderr.includes('"listening"'), `expected listening confirmation on startup, got: ${stderr}`);
  } finally {
    rmSync(stateRoot, { recursive: true, force: true });
  }
});
