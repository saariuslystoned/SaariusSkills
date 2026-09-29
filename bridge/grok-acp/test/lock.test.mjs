import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { lstat, mkdir, mkdtemp, readFile, readdir, rename, rm, symlink, writeFile } from "node:fs/promises";
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

test("an older stale reclaimer cannot erase a newer reclaim generation", { timeout: 10_000 }, async () => {
  const { stateRoot } = await makeState();
  const lockPath = path.join(stateRoot, "jobs", `${STALE_JOB}.json.lock`);
  const reclaimPath = `${lockPath}.reclaim`;
  const stale = { brokerId: "dead-owner", pid: DEAD_PID, startTime: "old" };
  await writeFile(lockPath, JSON.stringify(stale));
  const newer = new GrokAcpBroker({
    stateRoot,
    runtime: {},
    brokerId: "broker-b",
    startTime: "newer",
    inspectProcess: async () => ({ status: "missing" }),
  });
  let replaced = false;
  let newerFence;
  const older = new GrokAcpBroker({
    stateRoot,
    runtime: {},
    brokerId: "broker-a",
    startTime: "older",
    inspectProcess: async (pid) => {
      if (pid === DEAD_PID && !replaced) {
        replaced = true;
        assert.equal(await newer.tryAcquireLockReclaim(reclaimPath), null);
        newerFence = await newer.tryAcquireLockReclaim(reclaimPath);
        assert.ok(newerFence?.token);
      }
      return { status: "missing" };
    },
  });

  await older.reclaimJobLock(lockPath, reclaimPath, { observed: stale, unreadable: false });
  assert.equal(JSON.parse(await readFile(path.join(reclaimPath, "owner.json"))).brokerId, "broker-b");
  await newer.releaseLockReclaim(reclaimPath, newerFence);
  await assert.rejects(
    () => readFile(path.join(reclaimPath, "owner.json")),
    (error) => error?.code === "ENOENT",
  );
});

test("a stale holder observation cannot detach a newer reclaim generation", { timeout: 10_000 }, async () => {
  const { stateRoot } = await makeState();
  const reclaimPath = path.join(stateRoot, "jobs", `${STALE_JOB}.json.lock.reclaim`);
  const stale = { brokerId: "dead-owner", pid: DEAD_PID, startTime: "old", reclaimToken: "old-token" };
  await mkdir(reclaimPath, { recursive: true });
  await writeFile(path.join(reclaimPath, "owner.json"), `${JSON.stringify(stale)}\n`);
  const newer = new GrokAcpBroker({
    stateRoot,
    runtime: {},
    brokerId: "broker-b",
    startTime: "newer",
    inspectProcess: async () => ({ status: "missing" }),
  });
  let newerFence;
  const older = new GrokAcpBroker({
    stateRoot,
    runtime: {},
    brokerId: "broker-a",
    startTime: "older",
    inspectProcess: async (pid) => {
      if (pid === DEAD_PID && !newerFence) {
        assert.equal(await newer.tryAcquireLockReclaim(reclaimPath), null);
        newerFence = await newer.tryAcquireLockReclaim(reclaimPath);
      }
      return { status: "missing" };
    },
  });

  await older.tryAcquireLockReclaim(reclaimPath);
  if (!newerFence) newerFence = await newer.tryAcquireLockReclaim(reclaimPath);
  assert.equal(JSON.parse(await readFile(path.join(reclaimPath, "owner.json"))).brokerId, "broker-b");
  await newer.releaseLockReclaim(reclaimPath, newerFence);
});

test("release removes only its generation after canonical replacement", { timeout: 10_000 }, async () => {
  const { stateRoot } = await makeState();
  const reclaimPath = path.join(stateRoot, "jobs", `${STALE_JOB}.json.lock.reclaim`);
  const broker = new GrokAcpBroker({
    stateRoot,
    runtime: {},
    brokerId: "broker-a",
    startTime: "older",
    inspectProcess: async () => ({ status: "missing" }),
  });
  const olderFence = await broker.tryAcquireLockReclaim(reclaimPath);
  assert.ok(olderFence?.uniquePath);
  const detachedPath = `${reclaimPath}.stale.test`;
  await rename(reclaimPath, detachedPath);
  await rm(detachedPath, { recursive: true, force: true });
  const newerFence = await broker.tryAcquireLockReclaim(reclaimPath);
  assert.ok(newerFence?.uniquePath);
  await broker.releaseLockReclaim(reclaimPath, olderFence);
  assert.equal(JSON.parse(await readFile(path.join(reclaimPath, "owner.json"))).brokerId, "broker-a");
  await broker.releaseLockReclaim(reclaimPath, newerFence);
});

test("an existing malformed reclaim generation stays fenced", { timeout: 10_000 }, async () => {
  const { root } = await makeState();
  const reclaimPath = path.join(root, "job.lock.reclaim");
  const generationPath = `${reclaimPath}.generation`;
  await mkdir(generationPath);
  await writeFile(path.join(generationPath, "owner.json"), "{incomplete\n");
  await symlink(generationPath, reclaimPath, "dir");
  const broker = new GrokAcpBroker({
    stateRoot: root,
    runtime: {},
    brokerId: "contender",
    startTime: "contender",
    inspectProcess: async () => ({ status: "missing" }),
  });

  assert.equal(await broker.tryAcquireLockReclaim(reclaimPath), null);
  assert.equal(await readFile(path.join(generationPath, "owner.json"), "utf8"), "{incomplete\n");
  assert.equal(await readFile(path.join(reclaimPath, "owner.json"), "utf8"), "{incomplete\n");
});

test("a reclaim probe error preserves the existing generation", { timeout: 10_000 }, async () => {
  const { root } = await makeState();
  const reclaimPath = path.join(root, "job.lock.reclaim");
  const generationPath = `${reclaimPath}.generation`;
  await mkdir(generationPath);
  await writeFile(
    path.join(generationPath, "owner.json"),
    `${JSON.stringify({ brokerId: "owner", pid: 12345, startTime: "owner", reclaimToken: "owner-token" })}\n`,
  );
  await symlink(generationPath, reclaimPath, "dir");
  const broker = new GrokAcpBroker({
    stateRoot: root,
    runtime: {},
    brokerId: "contender",
    startTime: "contender",
    inspectProcess: async () => { throw new Error("probe unavailable"); },
  });

  assert.equal(await broker.tryAcquireLockReclaim(reclaimPath), null);
  assert.equal(await lstat(generationPath).then((stats) => stats.isDirectory()), true);
  assert.equal(JSON.parse(await readFile(path.join(reclaimPath, "owner.json"), "utf8")).reclaimToken, "owner-token");
});

test("a genuinely dangling reclaim generation is cleaned", { timeout: 10_000 }, async () => {
  const { root } = await makeState();
  const reclaimPath = path.join(root, "job.lock.reclaim");
  await symlink(`${reclaimPath}.missing`, reclaimPath, "dir");
  const broker = new GrokAcpBroker({
    stateRoot: root,
    runtime: {},
    brokerId: "contender",
    startTime: "contender",
    inspectProcess: async () => ({ status: "missing" }),
  });

  assert.equal(await broker.tryAcquireLockReclaim(reclaimPath), null);
  const acquired = await broker.tryAcquireLockReclaim(reclaimPath);
  assert.ok(acquired?.uniquePath);
  await broker.releaseLockReclaim(reclaimPath, acquired);
});

test("a killed reclaim mutex holder does not strand stale-lock recovery", { timeout: 15_000 }, async () => {
  const { root, stateRoot } = await makeState();
  const lockPath = path.join(stateRoot, "jobs", `${STALE_JOB}.json.lock`);
  const reclaimPath = `${lockPath}.reclaim`;
  const readyPath = path.join(root, "mutex-ready");
  await writeFile(lockPath, JSON.stringify({ brokerId: "dead-owner", pid: DEAD_PID, startTime: "old" }));
  const script = `
import { writeFile } from "node:fs/promises";
import { GrokAcpBroker } from ${JSON.stringify(brokerModule)};
const broker = new GrokAcpBroker({ stateRoot: process.env.STATE_ROOT, runtime: {}, brokerId: "crashed-mutex-owner", startTime: "crashed" });
const mutex = broker.acquireLockReclaimMutex(process.env.RECLAIM_PATH);
if (!mutex) process.exit(2);
await writeFile(process.env.READY_PATH, "locked\\n");
setInterval(() => {}, 1000);
await new Promise(() => {});
`;
  const child = spawn(process.execPath, ["--input-type=module", "-e", script], {
    env: {
      PATH: process.env.PATH ?? "/usr/bin:/bin",
      TMPDIR: os.tmpdir(),
      HOME: os.homedir(),
      STATE_ROOT: stateRoot,
      RECLAIM_PATH: reclaimPath,
      READY_PATH: readyPath,
    },
    stdio: ["ignore", "ignore", "pipe"],
  });
  const stderr = [];
  child.stderr.on("data", (chunk) => stderr.push(chunk));
  for (let attempt = 0; attempt < 100; attempt += 1) {
    try {
      await readFile(readyPath);
      break;
    } catch {
      await sleep(10);
    }
    if (attempt === 99) assert.fail(`child did not acquire reclaim mutex: ${Buffer.concat(stderr).toString("utf8")}`);
  }
  child.kill("SIGKILL");
  const exit = await new Promise((resolve, reject) => {
    child.once("exit", (code, signal) => resolve({ code, signal }));
    child.once("error", reject);
  });
  assert.equal(exit.signal, "SIGKILL");

  const holdersDir = path.join(root, "post-crash-holders");
  const resultDir = path.join(root, "post-crash-overlap");
  const startPath = path.join(root, "post-crash-start");
  await mkdir(holdersDir);
  await mkdir(resultDir);
  const contenderScript = `
import { access, mkdir, readdir, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { GrokAcpBroker } from ${JSON.stringify(brokerModule)};
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const broker = new GrokAcpBroker({ stateRoot: process.env.STATE_ROOT, runtime: {}, brokerId: process.env.BROKER_ID, grokExecutable: process.execPath });
while (true) {
  try { await access(process.env.START_PATH); break; } catch { await sleep(10); }
}
await broker.withJobLock(process.env.JOB_ID, async () => {
  const marker = path.join(process.env.HOLDERS_DIR, String(process.pid));
  await writeFile(marker, "1");
  const holders = await readdir(process.env.HOLDERS_DIR);
  await writeFile(path.join(process.env.RESULT_DIR, "overlap-" + process.pid), String(holders.length));
  await sleep(200);
  await rm(marker, { force: true });
}, { timeoutMs: 8_000 });
`;
  const spawnContender = (brokerId) => spawn(process.execPath, ["--input-type=module", "-e", contenderScript], {
    env: {
      PATH: process.env.PATH ?? "/usr/bin:/bin",
      TMPDIR: os.tmpdir(),
      HOME: os.homedir(),
      STATE_ROOT: stateRoot,
      JOB_ID: STALE_JOB,
      HOLDERS_DIR: holdersDir,
      RESULT_DIR: resultDir,
      START_PATH: startPath,
      BROKER_ID: brokerId,
    },
    stdio: ["ignore", "ignore", "pipe"],
  });
  const contenders = [spawnContender("broker-b"), spawnContender("broker-c")];
  const failures = [];
  for (const contender of contenders) contender.stderr.on("data", (chunk) => failures.push(chunk));
  await writeFile(startPath, "go\n");
  const exits = await Promise.all(contenders.map((contender) => new Promise((resolve, reject) => {
    contender.once("exit", (code, signal) => resolve({ code, signal }));
    contender.once("error", reject);
  })));
  const stderrText = Buffer.concat(failures).toString("utf8");
  for (const exit of exits) assert.equal(exit.code, 0, stderrText);
  const overlapFiles = (await readdir(resultDir)).filter((name) => name.startsWith("overlap-"));
  assert.equal(overlapFiles.length, 2, stderrText);
  for (const name of overlapFiles) assert.equal(await readFile(path.join(resultDir, name), "utf8"), "1", stderrText);
});

test("a legacy mkdir mutex marker does not block SQLite recovery", { timeout: 10_000 }, async () => {
  const { root } = await makeState();
  const reclaimPath = path.join(root, "job.lock.reclaim");
  await mkdir(`${reclaimPath}.mutex`);
  const broker = new GrokAcpBroker({ stateRoot: root, runtime: {}, brokerId: "upgraded", startTime: "upgraded", inspectProcess: async () => ({ status: "missing" }) });
  const fence = await broker.tryAcquireLockReclaim(reclaimPath);
  assert.ok(fence?.uniquePath);
  await broker.releaseLockReclaim(reclaimPath, fence);
});

test("release waits for a busy mutex and then permits stale-job recovery", { timeout: 15_000 }, async () => {
  const { stateRoot } = await makeState();
  const reclaimPath = path.join(stateRoot, "job.lock.reclaim");
  const broker = new GrokAcpBroker({ stateRoot, runtime: {}, brokerId: "owner", startTime: "owner", inspectProcess: async () => ({ status: "missing" }) });
  const fence = await broker.tryAcquireLockReclaim(reclaimPath);
  assert.ok(fence?.uniquePath);
  const heldMutex = broker.acquireLockReclaimMutex(reclaimPath);
  assert.ok(heldMutex);
  const releasePromise = broker.releaseLockReclaim(reclaimPath, fence);
  await sleep(50);
  assert.equal((await readFile(path.join(reclaimPath, "owner.json"), "utf8")).length > 0, true);
  broker.releaseLockReclaimMutex(heldMutex);
  await releasePromise;
  await assert.rejects(() => readFile(path.join(reclaimPath, "owner.json")), (error) => error?.code === "ENOENT");

  const lockPath = path.join(stateRoot, `${STALE_JOB}.json.lock`);
  await writeFile(lockPath, JSON.stringify({ brokerId: "dead-owner", pid: DEAD_PID, startTime: "old" }));
  let entered = false;
  await broker.withJobLock(STALE_JOB, async () => { entered = true; }, { timeoutMs: 8_000 });
  assert.equal(entered, true);
});

test("an unrelated absolute reclaim target is preserved", { timeout: 10_000 }, async () => {
  const { root } = await makeState();
  const reclaimPath = path.join(root, "job.lock.reclaim");
  const unrelatedPath = path.join(root, "unrelated");
  await mkdir(unrelatedPath);
  await writeFile(path.join(unrelatedPath, "owner.json"), `${JSON.stringify({ brokerId: "dead", pid: DEAD_PID, startTime: "old", reclaimToken: "unrelated" })}\n`);
  await writeFile(path.join(unrelatedPath, "keep.txt"), "preserve me\n");
  await symlink(unrelatedPath, reclaimPath, "dir");
  const broker = new GrokAcpBroker({ stateRoot: root, runtime: {}, brokerId: "contender", startTime: "contender", inspectProcess: async () => ({ status: "missing" }) });

  assert.equal(await broker.tryAcquireLockReclaim(reclaimPath), null);
  assert.equal(await readFile(path.join(unrelatedPath, "keep.txt"), "utf8"), "preserve me\n");
});

test("a relative legitimate generation target is resolved and cleaned", { timeout: 10_000 }, async () => {
  const { root } = await makeState();
  const reclaimPath = path.join(root, "job.lock.reclaim");
  const token = "12345678-1234-4123-8123-123456789abc";
  const generationPath = `${reclaimPath}.${token}`;
  await mkdir(generationPath);
  await writeFile(path.join(generationPath, "owner.json"), `${JSON.stringify({ brokerId: "dead", pid: DEAD_PID, startTime: "old", reclaimToken: token })}\n`);
  await symlink(path.basename(generationPath), reclaimPath, "dir");
  const broker = new GrokAcpBroker({ stateRoot: root, runtime: {}, brokerId: "contender", startTime: "contender", inspectProcess: async () => ({ status: "missing" }) });

  assert.equal(await broker.tryAcquireLockReclaim(reclaimPath), null);
  await assert.rejects(() => lstat(generationPath), (error) => error?.code === "ENOENT");
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
