import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { copyFileSync, mkdtempSync, mkdirSync, readFileSync, realpathSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const root = fileURLToPath(new URL("../", import.meta.url));
const script = path.join(root, "scripts/setup.mjs");
const run = (target, args = ["--check"], extraEnv = {}) => spawnSync(process.execPath, [target, ...args], {
  encoding: "utf8",
  timeout: 25_000,
  env: { ...process.env, ...extraEnv },
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

test("setup --check uses isolated state and does not invalidate an active fixture job", () => {
  const fixture = mkdtempSync(path.join(tmpdir(), "cursor-acp-setup-job-"));
  try {
    const jobsRoot = path.join(fixture, "jobs");
    const runDir = path.join(fixture, "runs", "44444444-4444-4444-8444-444444444444");
    mkdirSync(jobsRoot, { recursive: true });
    mkdirSync(runDir, { recursive: true });
    const jobId = "44444444-4444-4444-8444-444444444444";
    const jobPath = path.join(jobsRoot, `${jobId}.json`);
    const job = {
      schema: "saarius.cursor-acp.job.v1",
      jobId,
      status: "running",
      workspace: fixture,
      runDir,
      route: { executable: "synthetic", model: "synthetic" },
      request: { promptSha256: "synthetic", promptChars: 9 },
      owner: {
        brokerId: "deadsetup-0000-4000-8000-000000000001",
        pid: 8_888_888,
        startTime: "Sun Jan  1 00:00:00 2023",
      },
      proof: {
        state: path.join(runDir, "STATE.md"),
        events: path.join(runDir, "events.jsonl"),
        proof: path.join(runDir, "PROOF.md"),
      },
    };
    writeFileSync(jobPath, `${JSON.stringify(job, null, 2)}\n`);
    const result = run(script, ["--check"], {
      SAARIUS_CURSOR_ACP_STATE_DIR: fixture,
      PLUGIN_DATA: fixture,
    });
    assert.equal(result.status, 0, result.stderr);
    assert.equal(JSON.parse(result.stdout).code, "MCP_READY");
    const after = JSON.parse(readFileSync(jobPath, "utf8"));
    assert.equal(after.status, "running");
    assert.equal(after.error, undefined);
  } finally {
    rmSync(fixture, { recursive: true, force: true });
  }
});
