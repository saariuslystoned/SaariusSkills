import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { existsSync, mkdtempSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { createAcpRuntime } from "acpx/runtime";
import { createAgentRegistry } from "acpx/agent-registry";
import {
  ACPX_NPM_INTEGRITY,
  ACPX_RELEASE,
  ACPX_RUNTIME_JS_SHA256,
  ACPX_TARBALL_SHA256,
} from "../contract.mjs";

const root = fileURLToPath(new URL("../", import.meta.url));
const installedPackage = path.join(root, "node_modules/acpx/package.json");
const installedRuntime = path.join(root, "node_modules/acpx/dist/runtime.js");
const lockfile = path.join(root, "package-lock.json");

function requirePublishedInstall() {
  assert.equal(
    existsSync(installedPackage),
    true,
    "published acpx@0.19.0 must be installed by local npm ci in this bridge",
  );
}

test("native pin exercises published acpx 0.19.0 public runtime and agent-registry exports", async () => {
  requirePublishedInstall();
  const manifest = JSON.parse(readFileSync(installedPackage, "utf8"));
  const lock = JSON.parse(readFileSync(lockfile, "utf8"));
  const pinned = lock.packages["node_modules/acpx"];
  const runtimeDigest = createHash("sha256").update(readFileSync(installedRuntime)).digest("hex");

  assert.equal(manifest.version, "0.19.0");
  assert.equal(manifest.version, ACPX_RELEASE);
  assert.equal(manifest.gitHead, undefined);
  assert.equal(pinned.version, "0.19.0");
  assert.equal(pinned.integrity, ACPX_NPM_INTEGRITY);
  assert.equal(runtimeDigest, ACPX_RUNTIME_JS_SHA256);
  assert.equal(ACPX_TARBALL_SHA256, "5a61820401cfed668ce3ad77a2feaebdd9e496a037ba28b2afca3224e7505c6d");
  assert.equal(typeof createAcpRuntime, "function");
  assert.equal(typeof createAgentRegistry, "function");

  const registry = createAgentRegistry({
    overrides: { antigravity: [process.execPath, "--version"] },
  });
  const sessions = new Map();
  const cwd = mkdtempSync(path.join(tmpdir(), "acpx-0190-agy-"));
  const runtime = createAcpRuntime({
    cwd,
    sessionStore: {
      async load(id) {
        const record = sessions.get(id);
        return record === undefined ? undefined : structuredClone(record);
      },
      async save(record) {
        sessions.set(record.acpxRecordId, structuredClone(record));
      },
    },
    agentRegistry: registry,
    fs: false,
    terminal: false,
  });
  assert.equal(typeof runtime.ensureSession, "function");
  assert.equal(typeof runtime.getStatus, "function");
  assert.equal(typeof runtime.startTurn, "function");
  assert.equal(typeof runtime.close, "function");
  assert.equal(typeof runtime.shutdown, "function");
  await runtime.shutdown();
});
