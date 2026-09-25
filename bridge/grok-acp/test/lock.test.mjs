import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { mkdir, mkdtemp, readFile, readdir, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { GrokAcpBroker } from "../broker.mjs";

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const brokerModule = new URL("../broker.mjs", import.meta.url).href;
const DEAD_PID = 8_888_888;
const STALE_JOB = "11111111-1111-4111-8111-111111111111";
const INTERRUPT_JOB = "22222222-2222-4222-8222-222222222222";

function gate() {
  let resolve;
  const promise = new Promise((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

async function makeState() {
  const root = await mkdtemp(path.join(os.tmpdir(), "saarius-grok-acp-lock-"));
  const stateRoot = path.join(root, "state");
  await mkdir(path.join(stateRoot, "jobs"), { recursive: true, mode: 0o700 });
  return { root, stateRoot };
}

async function writeOwnerLease(stateRoot, owner, { released = false } = {}) {
  const ownersRoot = path.join(stateRoot, "owners");
  await mkdir(ownersRoot, { recursive: true, mode: 0o700 });
  await writeFile(
    path.join(ownersRoot, `${owner.brokerId}.json`),
    `${JSON.stringify({ schema: "saarius.grok-acp.owner.v1", ...owner, heartbeatAt: new Date().toISOString(), released }, null, 2)}\n`,
  );
}

async function writeSyntheticJob(stateRoot, { jobId, owner, status = "running" }) {
  const runDir = path.join(stateRoot, "runs", jobId);
  await mkdir(runDir, { recursive: true, mode: 0o700 });
  const job = {
    schema: "saarius.grok-acp.job.v1",
    jobId,
    status,
    workspace: stateRoot,
    runDir,
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
    route: { agent: "grok-build", transport: "acp", executable: "synthetic", argv: ["synthetic"], model: "synthetic" },
    request: { promptSha256: "synthetic", promptChars: 9 },
    owner,
    proof: {
      state: path.join(runDir, "STATE.md"),
      events: path.join(runDir, "events.jsonl"),
      proof: path.join(runDir, "PROOF.md"),
    },
  };
  await writeFile(path.join(stateRoot, "jobs", `${jobId}.json`), `${JSON.stringify(job, null, 2)}\n`);
  if (owner) await writeOwnerLease(stateRoot, owner);
  return job;
}

function inspectLiveUnless(stalePid, onStale) {
  return async (pid) => {
    if (pid === stalePid) {
      if (onStale) await onStale();
      return { status: "missing" };
    }
    return { status: "alive", startTime: "live" };
  };
}

test("two stale-lock reclaimers keep mutual exclusion across takeover and release", { timeout: 10_000 }, async () => {
  const { stateRoot } = await makeState();
  const stale = { brokerId: "dead-owner", pid: DEAD_PID, startTime: "old" };
  const cProbing = gate();
  const releaseCProbe = gate();
  const bEntered = gate();
  const releaseB = gate();
  const cEntered = gate();
  const releaseC = gate();
  const b = new GrokAcpBroker({
    stateRoot,
    runtime: {},
    brokerId: "broker-b",
    startTime: "live",
    inspectProcess: inspectLiveUnless(DEAD_PID),
  });
  const c = new GrokAcpBroker({
    stateRoot,
    runtime: {},
    brokerId: "broker-c",
    startTime: "live",
    inspectProcess: inspectLiveUnless(DEAD_PID, async () => {
      cProbing.resolve();
      await releaseCProbe.promise;
    }),
  });
  await writeFile(b.jobLockPath(STALE_JOB), JSON.stringify(stale));
  let concurrent = 0;
  let maximum = 0;
  let cInside = false;
  const cRun = c.withJobLock(STALE_JOB, async () => {
    cInside = true;
    maximum = Math.max(maximum, ++concurrent);
    cEntered.resolve();
    await releaseC.promise;
    concurrent -= 1;
  });
  await cProbing.promise;
  const bRun = b.withJobLock(STALE_JOB, async () => {
    maximum = Math.max(maximum, ++concurrent);
    bEntered.resolve();
    await releaseB.promise;
    concurrent -= 1;
  });
  await bEntered.promise;
  assert.equal(JSON.parse(await readFile(b.jobLockPath(STALE_JOB), "utf8")).brokerId, "broker-b");
  releaseCProbe.resolve();
  await sleep(150);
  assert.equal(cInside, false);
  assert.equal(JSON.parse(await readFile(b.jobLockPath(STALE_JOB), "utf8")).brokerId, "broker-b");
  releaseB.resolve();
  await bRun;
  await cEntered.promise;
  assert.equal(maximum, 1);
  assert.equal(JSON.parse(await readFile(c.jobLockPath(STALE_JOB), "utf8")).brokerId, "broker-c");
  releaseC.resolve();
  await cRun;
});

test("separate OS processes serialize stale-lock reclamation", { timeout: 20_000 }, async () => {
  const { root, stateRoot } = await makeState();
  const jobId = STALE_JOB;
  const holdersDir = path.join(root, "holders");
  const resultDir = path.join(root, "overlap");
  const startPath = path.join(root, "start");
  await mkdir(holdersDir, { recursive: true });
  await mkdir(resultDir, { recursive: true });
  await writeFile(
    path.join(stateRoot, "jobs", `${jobId}.json.lock`),
    JSON.stringify({ brokerId: "dead-owner", pid: DEAD_PID, startTime: "old" }),
  );
  const script = `
import { access, mkdir, readdir, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { GrokAcpBroker } from ${JSON.stringify(brokerModule)};
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const stateRoot = process.env.STATE_ROOT;
const jobId = process.env.JOB_ID;
const holdersDir = process.env.HOLDERS_DIR;
const resultDir = process.env.RESULT_DIR;
const startPath = process.env.START_PATH;
const broker = await new GrokAcpBroker({
  stateRoot,
  runtime: {},
  brokerId: process.env.BROKER_ID,
  grokExecutable: process.execPath,
}).init();
await mkdir(holdersDir, { recursive: true });
await mkdir(resultDir, { recursive: true });
while (true) {
  try { await access(startPath); break; } catch { await sleep(10); }
}
await broker.withJobLock(jobId, async () => {
  const marker = path.join(holdersDir, String(process.pid));
  await writeFile(marker, "1");
  const holders = await readdir(holdersDir);
  await writeFile(path.join(resultDir, \`overlap-\${process.pid}\`), String(holders.length));
  await sleep(200);
  await rm(marker, { force: true });
}, { timeoutMs: 8_000 });
`;
  const spawnContender = (brokerId) => spawn(process.execPath, ["--input-type=module", "-e", script], {
    env: {
      PATH: process.env.PATH ?? "/usr/bin:/bin",
      TMPDIR: os.tmpdir(),
      HOME: os.homedir(),
      STATE_ROOT: stateRoot,
      JOB_ID: jobId,
      HOLDERS_DIR: holdersDir,
      RESULT_DIR: resultDir,
      START_PATH: startPath,
      BROKER_ID: brokerId,
    },
    stdio: ["ignore", "pipe", "pipe"],
  });
  const first = spawnContender("broker-b");
  const second = spawnContender("broker-c");
  const failures = [];
  for (const child of [first, second]) {
    child.stderr.on("data", (chunk) => failures.push(chunk));
  }
  await writeFile(startPath, "go\n");
  const exits = await Promise.all([first, second].map((child) => new Promise((resolve, reject) => {
    child.once("exit", (code, signal) => resolve({ code, signal }));
    child.once("error", reject);
  })));
  const stderr = Buffer.concat(failures).toString("utf8");
  for (const exit of exits) {
    assert.equal(exit.code, 0, stderr);
  }
  const overlapFiles = (await readdir(resultDir)).filter((name) => name.startsWith("overlap-"));
  assert.equal(overlapFiles.length, 2, stderr);
  for (const name of overlapFiles) {
    assert.equal(await readFile(path.join(resultDir, name), "utf8"), "1", stderr);
  }
});

test("a leftover empty lock with a dead owner is recovered without JOB_LOCK_TIMEOUT", { timeout: 15_000 }, async () => {
  const { stateRoot } = await makeState();
  const script = `
import { open } from "node:fs/promises";
import { GrokAcpBroker } from ${JSON.stringify(brokerModule)};
const broker = await new GrokAcpBroker({
  stateRoot: process.env.STATE_ROOT,
  runtime: {},
  grokExecutable: process.execPath,
}).init();
await broker.saveJob({
  jobId: process.env.JOB_ID,
  status: "running",
  workspace: process.env.STATE_ROOT,
  runDir: process.env.STATE_ROOT,
  createdAt: new Date().toISOString(),
  route: { agent: "grok-build", transport: "acp", executable: "synthetic", argv: ["synthetic"], model: "synthetic" },
  request: { promptSha256: "synthetic", promptChars: 9 },
  owner: broker.ownerIdentity(),
  proof: { state: process.env.STATE_PATH, events: process.env.EVENTS_PATH, proof: process.env.PROOF_PATH },
});
await open(broker.jobLockPath(process.env.JOB_ID), "wx", 0o600);
process.exit(0);
`;
  const runDir = path.join(stateRoot, "runs", INTERRUPT_JOB);
  await mkdir(runDir, { recursive: true, mode: 0o700 });
  const child = spawn(process.execPath, ["--input-type=module", "-e", script], {
    env: {
      PATH: process.env.PATH ?? "/usr/bin:/bin",
      TMPDIR: os.tmpdir(),
      HOME: os.homedir(),
      STATE_ROOT: stateRoot,
      JOB_ID: INTERRUPT_JOB,
      STATE_PATH: path.join(runDir, "STATE.md"),
      EVENTS_PATH: path.join(runDir, "events.jsonl"),
      PROOF_PATH: path.join(runDir, "PROOF.md"),
    },
    stdio: ["ignore", "pipe", "pipe"],
  });
  const stderr = [];
  child.stderr.on("data", (chunk) => stderr.push(chunk));
  const exit = await new Promise((resolve, reject) => {
    child.once("exit", (code, signal) => resolve({ code, signal }));
    child.once("error", reject);
  });
  assert.equal(exit.code, 0, Buffer.concat(stderr).toString("utf8"));
  const lockPath = path.join(stateRoot, "jobs", `${INTERRUPT_JOB}.json.lock`);
  assert.equal((await readFile(lockPath)).length, 0);
  const broker = new GrokAcpBroker({
    stateRoot,
    runtime: {},
    grokExecutable: process.execPath,
    execFile: async () => ({ stdout: "2026.08.11-e8db854\n", stderr: "" }),
  });
  await broker.init();
  const after = await broker.readJobRecord(INTERRUPT_JOB);
  assert.equal(after.status, "failed");
  assert.equal(after.error.code, "BRIDGE_RESTARTED");
  let acquired = false;
  await broker.withJobLock(INTERRUPT_JOB, async () => {
    acquired = true;
  }, { timeoutMs: 1_000 });
  assert.equal(acquired, true);
  await broker.close();
});

test("interruption before lock publication does not leave an unreadable lock", { timeout: 15_000 }, async () => {
  const { stateRoot } = await makeState();
  const job = await writeSyntheticJob(stateRoot, {
    jobId: INTERRUPT_JOB,
    owner: { brokerId: "prep0000-0000-4000-8000-000000000001", pid: DEAD_PID, startTime: "old" },
  });
  const script = `
import { GrokAcpBroker } from ${JSON.stringify(brokerModule)};
const broker = new GrokAcpBroker({
  stateRoot: process.env.STATE_ROOT,
  runtime: {},
  brokerId: "interrupt-0000-4000-8000-000000000001",
  startTime: "child",
  onJobLockPrepared: async () => { process.exit(0); },
});
await broker.withJobLock(process.env.JOB_ID, async () => {});
`;
  const child = spawn(process.execPath, ["--input-type=module", "-e", script], {
    env: {
      PATH: process.env.PATH ?? "/usr/bin:/bin",
      TMPDIR: os.tmpdir(),
      HOME: os.homedir(),
      STATE_ROOT: stateRoot,
      JOB_ID: job.jobId,
    },
    stdio: ["ignore", "pipe", "pipe"],
  });
  const stderr = [];
  child.stderr.on("data", (chunk) => stderr.push(chunk));
  const exit = await new Promise((resolve, reject) => {
    child.once("exit", (code, signal) => resolve({ code, signal }));
    child.once("error", reject);
  });
  assert.equal(exit.code, 0, Buffer.concat(stderr).toString("utf8"));
  const lockPath = path.join(stateRoot, "jobs", `${job.jobId}.json.lock`);
  let lockBytes = null;
  try {
    const raw = await readFile(lockPath);
    lockBytes = raw.length;
    assert.ok(raw.length > 0, "canonical lock must not be published empty");
    JSON.parse(raw.toString("utf8"));
  } catch (error) {
    assert.equal(error?.code, "ENOENT");
  }
  const broker = new GrokAcpBroker({
    stateRoot,
    runtime: {},
    grokExecutable: process.execPath,
    execFile: async () => ({ stdout: "2026.08.11-e8db854\n", stderr: "" }),
  });
  const began = Date.now();
  let acquired = false;
  await broker.withJobLock(job.jobId, async () => {
    acquired = true;
  }, { timeoutMs: 1_000 });
  assert.equal(acquired, true);
  assert.ok(Date.now() - began < 1_000);
  assert.equal(lockBytes, null);
  await broker.close();
});
