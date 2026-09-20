import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { access, mkdtemp, mkdir, readFile, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { CursorAcpBroker } from "../broker.mjs";

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const brokerModule = new URL("../broker.mjs", import.meta.url).href;
const DEAD_PID = 8_888_888;

async function waitUntil(predicate, timeoutMs = 3_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (await predicate()) return;
    await sleep(10);
  }
  assert.fail("condition did not become true before timeout");
}

async function makeState() {
  const root = await mkdtemp(path.join(os.tmpdir(), "saarius-cursor-acp-recovery-"));
  return { root, stateRoot: path.join(root, "state") };
}

async function writeOwnerLease(stateRoot, owner, { released = false } = {}) {
  if (!owner?.brokerId) return;
  const ownersRoot = path.join(stateRoot, "owners");
  await mkdir(ownersRoot, { recursive: true, mode: 0o700 });
  await writeFile(
    path.join(ownersRoot, `${owner.brokerId}.json`),
    `${JSON.stringify({ schema: "saarius.cursor-acp.owner.v1", ...owner, heartbeatAt: new Date().toISOString(), released }, null, 2)}\n`,
  );
}

async function writeSyntheticJob(stateRoot, {
  jobId = "11111111-1111-4111-8111-111111111111",
  status = "running",
  owner,
  error,
  handoff,
  writeLease = Boolean(owner),
} = {}) {
  const runDir = path.join(stateRoot, "runs", jobId);
  await mkdir(runDir, { recursive: true, mode: 0o700 });
  await mkdir(path.join(stateRoot, "jobs"), { recursive: true, mode: 0o700 });
  const job = {
    schema: "saarius.cursor-acp.job.v1",
    jobId,
    status,
    workspace: stateRoot,
    runDir,
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
    route: { agent: "cursor", transport: "acp", executable: "synthetic", argv: ["synthetic"], model: "synthetic" },
    request: { promptSha256: "synthetic", promptChars: 9 },
    owner,
    proof: {
      state: path.join(runDir, "STATE.md"),
      events: path.join(runDir, "events.jsonl"),
      proof: path.join(runDir, "PROOF.md"),
    },
  };
  if (error) job.error = error;
  if (handoff) job.handoff = handoff;
  await writeFile(path.join(stateRoot, "jobs", `${jobId}.json`), `${JSON.stringify(job, null, 2)}\n`);
  if (writeLease && owner) await writeOwnerLease(stateRoot, owner);
  return job;
}

async function readJob(stateRoot, jobId) {
  return JSON.parse(await readFile(path.join(stateRoot, "jobs", `${jobId}.json`), "utf8"));
}

function makeSecondBroker(stateRoot, extras = {}) {
  return new CursorAcpBroker({
    stateRoot,
    runtime: {},
    cursorExecutable: process.execPath,
    execFile: async () => ({ stdout: "2026.08.11-e8db854\n", stderr: "" }),
    ...extras,
  });
}

async function spawnOwnerProcess({ stateRoot, mode }) {
  const readyPath = path.join(stateRoot, `ready-${mode}.json`);
  const jobId = mode === "stay"
    ? "22222222-2222-4222-8222-222222222222"
    : "33333333-3333-4333-8333-333333333333";
  const script = `
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { CursorAcpBroker } from ${JSON.stringify(brokerModule)};

const stateRoot = process.env.STATE_ROOT;
const readyPath = process.env.READY_PATH;
const jobId = process.env.JOB_ID;
const broker = await new CursorAcpBroker({
  stateRoot,
  runtime: {},
  cursorExecutable: process.execPath,
}).init();
const runDir = path.join(stateRoot, "runs", jobId);
await mkdir(runDir, { recursive: true, mode: 0o700 });
const job = {
  schema: "saarius.cursor-acp.job.v1",
  jobId,
  status: "running",
  workspace: stateRoot,
  runDir,
  createdAt: new Date().toISOString(),
  updatedAt: new Date().toISOString(),
  route: { agent: "cursor", transport: "acp", executable: "synthetic", argv: ["synthetic"], model: "synthetic" },
  request: { promptSha256: "synthetic", promptChars: 9 },
  owner: broker.ownerIdentity(),
  proof: {
    state: path.join(runDir, "STATE.md"),
    events: path.join(runDir, "events.jsonl"),
    proof: path.join(runDir, "PROOF.md"),
  },
};
await broker.saveJob(job);
await writeFile(readyPath, JSON.stringify({ owner: job.owner, pid: process.pid }) + "\\n");
if (process.env.CHILD_MODE === "exit") process.exit(0);
await new Promise((resolve) => {
  process.stdin.on("end", resolve);
  process.stdin.resume();
});
process.exit(0);
`;
  const child = spawn(process.execPath, ["--input-type=module", "-e", script], {
    env: {
      PATH: process.env.PATH ?? "/usr/bin:/bin",
      TMPDIR: os.tmpdir(),
      HOME: os.homedir(),
      STATE_ROOT: stateRoot,
      READY_PATH: readyPath,
      JOB_ID: jobId,
      CHILD_MODE: mode,
    },
    stdio: ["pipe", "pipe", "pipe"],
  });
  const stderr = [];
  child.stderr.on("data", (chunk) => stderr.push(chunk));
  await waitUntil(async () => {
    try {
      await access(readyPath);
      return true;
    } catch {
      return child.exitCode !== null && mode === "exit" ? true : false;
    }
  }, 8_000);
  if (child.exitCode && child.exitCode !== 0) {
    assert.fail(`owner child failed: ${Buffer.concat(stderr).toString("utf8")}`);
  }
  try {
    await access(readyPath);
  } catch {
    assert.fail(`owner child produced no ready file: ${Buffer.concat(stderr).toString("utf8")}`);
  }
  const ready = JSON.parse(await readFile(readyPath, "utf8"));
  return { child, jobId, ready, stderr };
}

test("unknown ownership is left unchanged during initialization", async () => {
  const { stateRoot } = await makeState();
  const written = await writeSyntheticJob(stateRoot, { owner: undefined });
  const broker = makeSecondBroker(stateRoot);
  await broker.init();
  const after = await readJob(stateRoot, written.jobId);
  assert.equal(after.status, "running");
  assert.equal(after.error, undefined);
  await broker.close();
});

test("incomplete owner identity with a missing PID is left unchanged", async () => {
  const { stateRoot } = await makeState();
  const written = await writeSyntheticJob(stateRoot, {
    owner: { brokerId: "incomplet-0000-4000-8000-000000000001", pid: DEAD_PID },
  });
  const broker = makeSecondBroker(stateRoot);
  await broker.init();
  const after = await readJob(stateRoot, written.jobId);
  assert.equal(after.status, "running");
  assert.equal(after.error, undefined);
  await broker.close();
});

test("a demonstrably dead owner is recovered as BRIDGE_RESTARTED", async () => {
  const { stateRoot } = await makeState();
  const written = await writeSyntheticJob(stateRoot, {
    owner: { brokerId: "dead0000-0000-4000-8000-000000000001", pid: DEAD_PID, startTime: "Sun Jan  1 00:00:00 2023" },
  });
  const broker = makeSecondBroker(stateRoot);
  await broker.init();
  const after = await broker.result({ jobId: written.jobId });
  assert.equal(after.status, "failed");
  assert.equal(after.error.code, "BRIDGE_RESTARTED");
  await broker.close();
});

test("a dead PID without a matching owner lease is left unchanged", async () => {
  const { stateRoot } = await makeState();
  const written = await writeSyntheticJob(stateRoot, {
    owner: { brokerId: "nolease0-0000-4000-8000-000000000001", pid: DEAD_PID, startTime: "Sun Jan  1 00:00:00 2023" },
    writeLease: false,
  });
  const broker = makeSecondBroker(stateRoot);
  await broker.init();
  const after = await readJob(stateRoot, written.jobId);
  assert.equal(after.status, "running");
  assert.equal(after.error, undefined);
  await broker.close();
});

test("a lease that does not match the job owner is left unchanged", async () => {
  const { stateRoot } = await makeState();
  const owner = { brokerId: "mismatch-0000-4000-8000-000000000001", pid: DEAD_PID, startTime: "Sun Jan  1 00:00:00 2023" };
  const written = await writeSyntheticJob(stateRoot, { owner, writeLease: false });
  await writeOwnerLease(stateRoot, { ...owner, startTime: "different-start" });
  const broker = makeSecondBroker(stateRoot);
  await broker.init();
  const after = await readJob(stateRoot, written.jobId);
  assert.equal(after.status, "running");
  assert.equal(after.error, undefined);
  await broker.close();
});

test("proven PID reuse with a mismatched start time is recovered as BRIDGE_RESTARTED", async () => {
  const { stateRoot } = await makeState();
  const written = await writeSyntheticJob(stateRoot, {
    owner: {
      brokerId: "reuse000-0000-4000-8000-000000000001",
      pid: process.pid,
      startTime: "Thu Jan  1 00:00:00 1970",
    },
  });
  const broker = makeSecondBroker(stateRoot);
  await broker.init();
  const after = await broker.result({ jobId: written.jobId });
  assert.equal(after.status, "failed");
  assert.equal(after.error.code, "BRIDGE_RESTARTED");
  await broker.close();
});

test("proven PID reuse without a matching owner lease is left unchanged", async () => {
  const { stateRoot } = await makeState();
  const written = await writeSyntheticJob(stateRoot, {
    owner: {
      brokerId: "reusenol-0000-4000-8000-000000000001",
      pid: process.pid,
      startTime: "Thu Jan  1 00:00:00 1970",
    },
    writeLease: false,
  });
  const broker = makeSecondBroker(stateRoot);
  await broker.init();
  const after = await readJob(stateRoot, written.jobId);
  assert.equal(after.status, "running");
  assert.equal(after.error, undefined);
  await broker.close();
});

test("PID reuse cannot be proved from bare PID existence and fails safe", async () => {
  const { stateRoot } = await makeState();
  const written = await writeSyntheticJob(stateRoot, {
    owner: { brokerId: "opaque00-0000-4000-8000-000000000001", pid: process.pid, startTime: "Sun Sep 20 13:00:00 2026" },
  });
  const broker = makeSecondBroker(stateRoot, {
    startTime: "second-broker",
    inspectProcess: async (pid) => {
      if (pid === process.pid) return { status: "alive" };
      return { status: "unknown" };
    },
  });
  await broker.init();
  const after = await readJob(stateRoot, written.jobId);
  assert.equal(after.status, "running");
  assert.equal(after.error, undefined);
  await broker.close();
});

test("already-terminal jobs stay terminal even when their owner is dead", async () => {
  const { stateRoot } = await makeState();
  const cases = [
    { jobId: "aaaaaaa1-0000-4000-8000-000000000001", status: "completed", handoff: "done" },
    { jobId: "aaaaaaa2-0000-4000-8000-000000000002", status: "failed", error: { code: "TIMEOUT", message: "expired" } },
    { jobId: "aaaaaaa3-0000-4000-8000-000000000003", status: "cancelled", handoff: "stopped" },
    { jobId: "aaaaaaa4-0000-4000-8000-000000000004", status: "needs-input", error: { code: "INPUT_REQUIRED", message: "login" } },
  ];
  const deadOwner = { brokerId: "deadterm-0000-4000-8000-000000000001", pid: DEAD_PID, startTime: "old" };
  for (const item of cases) await writeSyntheticJob(stateRoot, { ...item, owner: deadOwner });
  const broker = makeSecondBroker(stateRoot);
  await broker.init();
  for (const item of cases) {
    const after = await readJob(stateRoot, item.jobId);
    assert.equal(after.status, item.status);
    assert.notEqual(after.error?.code, "BRIDGE_RESTARTED");
  }
  await broker.close();
});

test("recovery loses a terminal-state race instead of overwriting completion", { timeout: 8_000 }, async () => {
  const { stateRoot } = await makeState();
  const writer = makeSecondBroker(stateRoot, { brokerId: "writer00-0000-4000-8000-000000000001", startTime: "writer" });
  await writer.init();
  const written = await writeSyntheticJob(stateRoot, {
    owner: { brokerId: "racer000-0000-4000-8000-000000000001", pid: DEAD_PID, startTime: "gone" },
  });
  let releaseInspect;
  const inspectGate = new Promise((resolve) => {
    releaseInspect = resolve;
  });
  let sawDeadOwner;
  const started = new Promise((resolve) => {
    sawDeadOwner = resolve;
  });
  const recovering = makeSecondBroker(stateRoot, {
    brokerId: "recover0-0000-4000-8000-000000000001",
    startTime: "recoverer",
    inspectProcess: async (pid) => {
      if (pid === DEAD_PID) {
        sawDeadOwner();
        await inspectGate;
        return { status: "missing" };
      }
      return { status: "alive", startTime: "recoverer" };
    },
  });
  const initPromise = recovering.init();
  await Promise.race([
    started,
    sleep(3_000).then(() => {
      throw new Error("recovery inspect did not observe the dead owner");
    }),
  ]);
  const current = await writer.getJob(written.jobId);
  current.status = "completed";
  current.handoff = "finished before recovery";
  delete current.error;
  await writer.saveJob(current);
  releaseInspect();
  await initPromise;
  const after = await readJob(stateRoot, written.jobId);
  assert.equal(after.status, "completed");
  assert.equal(after.handoff, "finished before recovery");
  assert.equal(after.error, undefined);
  await writer.close();
  await recovering.close();
});

test("status and result observe another live owner; cancel stays owner-local", async () => {
  const { stateRoot } = await makeState();
  const first = makeSecondBroker(stateRoot, { brokerId: "live0000-0000-4000-8000-000000000001" });
  await first.init();
  const written = await writeSyntheticJob(stateRoot, {
    owner: first.ownerIdentity(),
  });
  const second = makeSecondBroker(stateRoot, { brokerId: "other000-0000-4000-8000-000000000001" });
  await second.init();
  const status = await second.status({ jobId: written.jobId });
  assert.equal(status.status, "running");
  assert.equal(status.error, undefined);
  const result = await second.result({ jobId: written.jobId });
  assert.equal(result.status, "running");
  assert.equal(result.complete, false);
  await assert.rejects(
    () => second.cancel({ jobId: written.jobId }),
    (error) => error.code === "JOB_NOT_ACTIVE",
  );
  const afterCancel = await readJob(stateRoot, written.jobId);
  assert.equal(afterCancel.status, "running");
  await first.close();
  await second.close();
});

test("separate OS broker processes preserve a live owner and recover a dead one", { timeout: 20_000 }, async () => {
  const { stateRoot } = await makeState();
  await mkdir(stateRoot, { recursive: true });
  let live;
  let dead;
  try {
    live = await spawnOwnerProcess({ stateRoot, mode: "stay" });
    const observer = makeSecondBroker(stateRoot);
    await observer.init();
    const preserved = await readJob(stateRoot, live.jobId);
    assert.equal(preserved.status, "running");
    assert.equal(preserved.error, undefined);
    assert.equal(preserved.owner.pid, live.ready.pid);
    live.child.stdin.end();
    await new Promise((resolve, reject) => {
      live.child.once("exit", resolve);
      live.child.once("error", reject);
    });
    await observer.close();

    dead = await spawnOwnerProcess({ stateRoot, mode: "exit" });
    await new Promise((resolve, reject) => {
      if (dead.child.exitCode !== null) return resolve(dead.child.exitCode);
      dead.child.once("exit", resolve);
      dead.child.once("error", reject);
    });
    const recoverer = makeSecondBroker(stateRoot);
    await recoverer.init();
    const recovered = await readJob(stateRoot, dead.jobId);
    assert.equal(recovered.status, "failed");
    assert.equal(recovered.error.code, "BRIDGE_RESTARTED");
    const stillPreserved = await readJob(stateRoot, live.jobId);
    assert.equal(stillPreserved.status, "failed");
    assert.equal(stillPreserved.error.code, "BRIDGE_RESTARTED");
    await recoverer.close();
  } finally {
    for (const child of [live?.child, dead?.child]) {
      if (child && child.exitCode === null && child.signalCode === null) child.kill("SIGKILL");
    }
  }
});
