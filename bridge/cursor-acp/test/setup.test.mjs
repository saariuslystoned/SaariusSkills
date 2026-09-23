import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { copyFileSync, mkdtempSync, mkdirSync, readFileSync, realpathSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { CursorAcpBroker } from "../broker.mjs";

const root = fileURLToPath(new URL("../", import.meta.url));
const script = path.join(root, "scripts/setup.mjs");
const runtimeRoot = mkdtempSync(path.join(tmpdir(), "cursor-acp-runtime-store-test-"));
const runtimeSetup = path.join(root, "../acp-runtime/prepare.mjs");
let runtimeReady = false;
function ensureRuntime() {
  if (runtimeReady) return;
  const result = spawnSync(process.execPath, [runtimeSetup, "--bridge", "cursor-acp"], {
    encoding: "utf8",
    timeout: 120_000,
    env: { ...process.env, SAARIUS_ACP_RUNTIME_ROOT: runtimeRoot },
  });
  assert.equal(result.status, 0, result.stderr || result.stdout);
  runtimeReady = true;
}
const run = (target, args = ["--check"], extraEnv = {}) => spawnSync(process.execPath, [target, ...args], {
  encoding: "utf8",
  timeout: 25_000,
  env: { ...process.env, SAARIUS_ACP_RUNTIME_ROOT: runtimeRoot, ...extraEnv },
});

test.after(() => rmSync(runtimeRoot, { recursive: true, force: true }));

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
  ensureRuntime();
  const result = run(script);
  assert.equal(result.status, 0, result.stderr);
  const report = JSON.parse(result.stdout);
  assert.equal(report.code, "MCP_READY");
  assert.equal(report.liveCursorChecked, false);
  assert.deepEqual(report.tools, ["cancel", "delegate", "readiness", "result", "status", "steer"]
    .map((name) => `cursor_acp_${name}`));
});

function writeEligibleDeadOwnerFixture(fixture, jobId, brokerId) {
  const jobsRoot = path.join(fixture, "jobs");
  const ownersRoot = path.join(fixture, "owners");
  const runDir = path.join(fixture, "runs", jobId);
  mkdirSync(jobsRoot, { recursive: true });
  mkdirSync(ownersRoot, { recursive: true });
  mkdirSync(runDir, { recursive: true });
  const owner = {
    brokerId,
    pid: 8_888_888,
    startTime: "Sun Jan  1 00:00:00 2023",
  };
  const job = {
    schema: "saarius.cursor-acp.job.v1",
    jobId,
    status: "running",
    workspace: fixture,
    runDir,
    route: { executable: "synthetic", model: "synthetic" },
    request: { promptSha256: "synthetic", promptChars: 9 },
    owner,
    proof: {
      state: path.join(runDir, "STATE.md"),
      events: path.join(runDir, "events.jsonl"),
      proof: path.join(runDir, "PROOF.md"),
    },
  };
  writeFileSync(path.join(jobsRoot, `${jobId}.json`), `${JSON.stringify(job, null, 2)}\n`);
  writeFileSync(
    path.join(ownersRoot, `${brokerId}.json`),
    `${JSON.stringify({ schema: "saarius.cursor-acp.owner.v1", ...owner, heartbeatAt: new Date().toISOString() }, null, 2)}\n`,
  );
  return path.join(jobsRoot, `${jobId}.json`);
}

test("setup --check uses isolated state and does not invalidate an eligible dead-owner fixture", async () => {
  ensureRuntime();
  const fixture = mkdtempSync(path.join(tmpdir(), "cursor-acp-setup-job-"));
  const control = mkdtempSync(path.join(tmpdir(), "cursor-acp-setup-control-"));
  try {
    const jobId = "44444444-4444-4444-8444-444444444444";
    const jobPath = writeEligibleDeadOwnerFixture(
      fixture,
      jobId,
      "deadsetup-0000-4000-8000-000000000001",
    );
    const controlJobId = "55555555-5555-4555-8555-555555555555";
    writeEligibleDeadOwnerFixture(
      control,
      controlJobId,
      "deadctrl0-0000-4000-8000-000000000001",
    );
    const result = run(script, ["--check"], {
      SAARIUS_CURSOR_ACP_STATE_DIR: fixture,
      PLUGIN_DATA: fixture,
    });
    assert.equal(result.status, 0, result.stderr);
    assert.equal(JSON.parse(result.stdout).code, "MCP_READY");
    const afterCheck = JSON.parse(readFileSync(jobPath, "utf8"));
    assert.equal(afterCheck.status, "running");
    assert.equal(afterCheck.error, undefined);

    const broker = new CursorAcpBroker({
      stateRoot: control,
      runtime: {},
      cursorExecutable: process.execPath,
      execFile: async () => ({ stdout: "2026.08.11-e8db854\n", stderr: "" }),
    });
    await broker.init();
    const recovered = JSON.parse(readFileSync(path.join(control, "jobs", `${controlJobId}.json`), "utf8"));
    assert.equal(recovered.status, "failed");
    assert.equal(recovered.error?.code, "BRIDGE_RESTARTED");
    const stillUntouched = JSON.parse(readFileSync(jobPath, "utf8"));
    assert.equal(stillUntouched.status, "running");
    assert.equal(stillUntouched.error, undefined);
    await broker.close();
  } finally {
    rmSync(fixture, { recursive: true, force: true });
    rmSync(control, { recursive: true, force: true });
  }
});
