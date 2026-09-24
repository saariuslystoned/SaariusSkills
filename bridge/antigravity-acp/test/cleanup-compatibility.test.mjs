import { chmod, mkdtemp, mkdir, readFile, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import assert from "node:assert/strict";
import test from "node:test";
import { fileURLToPath } from "node:url";
import {
  AntigravityAcpBroker,
  BridgeError,
  createDefaultRuntime,
  createProcessLifecycleTracker,
  isUnsupportedBackendSessionClose,
  processIdentitiesMatch,
} from "../broker.mjs";
import { currentPlatformId, platformLaunch, settingsPath } from "../contract.mjs";

const model = "gemini-3.8-flash-high";
const here = path.dirname(fileURLToPath(import.meta.url));
const ephemeralPeer = path.join(here, "fixtures/ephemeral-synthetic-acp-peer.mjs");
const persistentPeer = path.join(here, "fixtures/persistent-synthetic-acp-peer.mjs");

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function alive(pid) {
  try { process.kill(pid, 0); return true; } catch { return false; }
}

async function killExact(pid) {
  if (!Number.isInteger(pid) || pid <= 0 || !alive(pid)) return;
  try { process.kill(pid, "SIGKILL"); } catch {}
  const deadline = Date.now() + 2_000;
  while (Date.now() < deadline && alive(pid)) await sleep(20);
}

async function waitForFile(filePath, timeoutMs = 10_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try { return (await readFile(filePath, "utf8")).trim(); } catch {}
    await sleep(20);
  }
  throw new Error(`timed out waiting for ${filePath}`);
}

async function waitUntilDead(pid, timeoutMs = 10_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (!alive(pid)) return;
    await sleep(20);
  }
  throw new Error(`process ${pid} stayed alive`);
}

async function makeHarness({ peerSource }) {
  const root = await mkdtemp(path.join(os.tmpdir(), "saarius-antigravity-cleanup-compat-"));
  const workspace = path.join(root, "workspace");
  const independentWorkspace = path.join(root, "independent-workspace");
  const stateRoot = path.join(root, "state");
  const geminiHome = path.join(root, "gemini-home");
  const runtimeDir = path.join(root, "runtime");
  const peerPidFile = path.join(root, "peer.pid");
  const heartbeatFile = path.join(root, "peer.heartbeat");
  const launch = platformLaunch(currentPlatformId());
  await mkdir(workspace);
  await mkdir(independentWorkspace);
  await mkdir(runtimeDir);
  await mkdir(path.dirname(settingsPath(geminiHome)), { recursive: true });
  await writeFile(
    settingsPath(geminiHome),
    JSON.stringify({ auth: { type: "oauth-personal" }, useG1Credits: false }),
  );
  const helper = path.join(runtimeDir, path.basename(launch.helper));
  await writeFile(helper, "#!/bin/sh\nexit 0\n", { mode: 0o700 });
  await chmod(helper, 0o700);
  const harness = {
    root,
    workspace,
    independentWorkspace,
    stateRoot,
    geminiHome,
    runtimeDir,
    peerPidFile,
    heartbeatFile,
  };
  await writeRuntimeWrapper(harness, peerSource, [heartbeatFile]);
  return harness;
}

test("pinned public createAcpRuntime reports matched onSpawned/onExit after unsupported session/close", { timeout: 60_000 }, async () => {
  const harness = await makeHarness({ peerSource: ephemeralPeer });
  const tracker = createProcessLifecycleTracker();
  const runtime = createDefaultRuntime({
    stateRoot: harness.stateRoot,
    launch: {
      command: path.join(harness.runtimeDir, path.basename(platformLaunch(currentPlatformId()).runtimeCommand)),
      args: [],
      helper: path.join(harness.runtimeDir, path.basename(platformLaunch(currentPlatformId()).helper)),
    },
    geminiHome: harness.geminiHome,
    timeoutMs: 30_000,
    processEnv: { PATH: process.env.PATH ?? "" },
    processLifecycle: tracker.processLifecycle,
  });
  const sessionKey = "antigravity-acp-compat:direct";
  let peerPid;
  try {
    const handle = await runtime.ensureSession({
      sessionKey,
      agent: "antigravity",
      mode: "oneshot",
      cwd: harness.workspace,
    });
    peerPid = Number(await waitForFile(harness.peerPidFile));
    const spawned = tracker.ownedSpawned(sessionKey);
    assert.equal(spawned.length, 1, JSON.stringify(tracker.spawned));
    assert.equal(spawned[0].pid, peerPid);
    assert.equal(spawned[0].scope.kind, "runtime-session");
    assert.equal(spawned[0].scope.sessionKey, sessionKey);
    let closeError;
    try {
      await runtime.close({
        handle,
        reason: "direct unsupported-close repro",
        discardPersistentState: true,
      });
    } catch (error) {
      closeError = error;
    }
    assert.equal(isUnsupportedBackendSessionClose(closeError), true, String(closeError?.message));
    const proof = await tracker.waitForOwnedExit(sessionKey, { timeoutMs: 10_000 });
    assert.equal(proof.status, "exited", JSON.stringify(proof));
    assert.equal(processIdentitiesMatch(spawned[0], proof.exits[0]), true);
    assert.equal(proof.exits[0].pid, peerPid);
    assert.equal(proof.exits[0].startedAt, spawned[0].startedAt);
    assert.equal(proof.exits[0].launchId, spawned[0].launchId);
    await waitUntilDead(peerPid);
    assert.equal(alive(peerPid), false);
  } finally {
    await runtime.shutdown().catch(() => {});
    await killExact(peerPid);
  }
});

test("broker cleanup becomes ready only after exact owned worker-exit proof", { timeout: 60_000 }, async () => {
  const harness = await makeHarness({ peerSource: ephemeralPeer });
  const tracker = createProcessLifecycleTracker();
  const broker = new AntigravityAcpBroker({
    stateRoot: harness.stateRoot,
    runtimeDir: harness.runtimeDir,
    geminiHome: harness.geminiHome,
    processEnv: { PATH: process.env.PATH ?? "" },
    processLifecycleTracker: tracker,
    defaultHostConversationId: "conv-cleanup-compat",
    defaultBinderId: "test-owner",
  });
  const fixturePids = [];
  try {
    await broker.init();
    const submitted = await broker.delegate({
      workspace: harness.workspace,
      model,
      prompt: "Complete one synthetic bounded task against an ephemeral peer.",
      timeoutMs: 30_000,
    });
    const completed = await broker.result({ jobId: submitted.jobId, waitMs: 30_000 });
    const peerPid = Number(await waitForFile(harness.peerPidFile));
    fixturePids.push(peerPid);
    assert.equal(completed.status, "completed", JSON.stringify(completed));
    assert.equal(completed.cleanupReady, true, JSON.stringify(completed));
    assert.equal(completed.complete, true, JSON.stringify(completed));
    assert.equal(completed.cleanup.status, "completed", JSON.stringify(completed));
    assert.equal(
      completed.cleanup.observed,
      "local_worker_terminated_backend_session_discard_unsupported",
    );
    assert.equal(completed.cleanup.backendSessionDiscard, "unsupported");
    assert.match(completed.cleanup.message, /backend session discard unsupported/);
    const sessionKey = completed.cleanup.handle.sessionKey;
    const proof = tracker.snapshotOwned(sessionKey);
    assert.equal(proof.started.length, 1);
    assert.equal(proof.exits.length, 1);
    assert.equal(processIdentitiesMatch(proof.started[0], proof.exits[0]), true);
    assert.equal(proof.started[0].pid, peerPid);
    assert.equal(completed.cleanup.worker.pid, peerPid);
    assert.equal(completed.cleanup.worker.startedAt, proof.started[0].startedAt);
    assert.equal(completed.cleanup.worker.launchId, proof.started[0].launchId);
    assert.equal(alive(peerPid), false, `owned worker still alive: ${peerPid}`);

    const replacement = await broker.delegate({
      workspace: harness.workspace,
      model,
      prompt: "Same workspace replacement is allowed after observed local cleanup.",
      timeoutMs: 30_000,
    });
    const replaced = await broker.result({ jobId: replacement.jobId, waitMs: 30_000 });
    fixturePids.push(Number(await waitForFile(harness.peerPidFile)));
    assert.equal(replaced.status, "completed", JSON.stringify(replaced));
    assert.equal(replaced.cleanupReady, true, JSON.stringify(replaced));
  } finally {
    await broker.close().catch(() => {});
    for (const pid of fixturePids) await killExact(pid);
  }
});

test("surviving peer or injected unsupported close stays uncertain and fenced", { timeout: 60_000 }, async () => {
  const harness = await makeHarness({ peerSource: persistentPeer });
  const tracker = createProcessLifecycleTracker();
  const broker = new AntigravityAcpBroker({
    stateRoot: harness.stateRoot,
    runtimeDir: harness.runtimeDir,
    geminiHome: harness.geminiHome,
    processEnv: { PATH: process.env.PATH ?? "" },
    processLifecycleTracker: tracker,
    defaultHostConversationId: "conv-cleanup-compat",
    defaultBinderId: "test-owner",
    runtimeFactory: (options) => {
      const runtime = createDefaultRuntime(options);
      runtime.close = async () => {
        await sleep(50);
        const error = new Error("Agent does not support session/close for surviving-peer.");
        error.code = "ACP_BACKEND_UNSUPPORTED_CONTROL";
        throw error;
      };
      return runtime;
    },
  });
  const fixturePids = [];
  try {
    await broker.init();
    const submitted = await broker.delegate({
      workspace: harness.workspace,
      model,
      prompt: "Leave the owned worker alive after injected unsupported close.",
      timeoutMs: 30_000,
    });
    const failedCleanup = await broker.result({ jobId: submitted.jobId, waitMs: 30_000 });
    const peerPid = Number(await waitForFile(harness.peerPidFile));
    fixturePids.push(peerPid);
    assert.equal(failedCleanup.status, "completed", JSON.stringify(failedCleanup));
    assert.equal(failedCleanup.cleanupReady, false, JSON.stringify(failedCleanup));
    assert.equal(failedCleanup.complete, false, JSON.stringify(failedCleanup));
    assert.equal(failedCleanup.cleanup.status, "uncertain", JSON.stringify(failedCleanup));
    assert.equal(failedCleanup.cleanup.observed, "runtime_close_failed");
    assert.equal(alive(peerPid), true, `surviving peer died before exact cleanup: ${peerPid}`);
    assert.equal(tracker.snapshotOwned(failedCleanup.cleanup.handle.sessionKey).exits.length, 0);
    await assert.rejects(
      () => broker.delegate({
        workspace: harness.workspace,
        model,
        prompt: "Same-workspace replacement must stay fenced.",
        timeoutMs: 30_000,
      }),
      (error) => error instanceof BridgeError && error.code === "WORKSPACE_CLEANUP_PENDING",
    );
    const independent = await broker.delegate({
      workspace: harness.independentWorkspace,
      model,
      prompt: "Independent workspace remains admissible while another is fenced.",
      timeoutMs: 30_000,
    });
    const independentResult = await broker.result({ jobId: independent.jobId, waitMs: 30_000 });
    fixturePids.push(Number(await waitForFile(harness.peerPidFile)));
    assert.equal(independentResult.status, "completed", JSON.stringify(independentResult));
    assert.equal(alive(peerPid), true, `surviving peer was swept: ${peerPid}`);
  } finally {
    await broker.close().catch(() => {});
    for (const pid of fixturePids) await killExact(pid);
  }
});

test("readiness close does not leak the exact owned probe worker", { timeout: 60_000 }, async () => {
  const harness = await makeHarness({ peerSource: ephemeralPeer });
  const tracker = createProcessLifecycleTracker();
  const broker = new AntigravityAcpBroker({
    stateRoot: harness.stateRoot,
    runtimeDir: harness.runtimeDir,
    geminiHome: harness.geminiHome,
    processEnv: { PATH: process.env.PATH ?? "" },
    processLifecycleTracker: tracker,
    defaultHostConversationId: "conv-cleanup-compat",
    defaultBinderId: "test-owner",
  });
  const fixturePids = [];
  try {
    await broker.init();
    const report = await broker.discover({ workspace: harness.workspace, model });
    const peerPid = Number(await waitForFile(harness.peerPidFile));
    fixturePids.push(peerPid);
    assert.equal(report.ready, true, JSON.stringify(report));
    const sessionKey = report.session.sessionKey;
    const proof = await tracker.waitForOwnedExit(sessionKey, { timeoutMs: 10_000 });
    assert.equal(proof.status, "exited", JSON.stringify(proof));
    assert.equal(processIdentitiesMatch(proof.started[0], proof.exits[0]), true);
    assert.equal(proof.started[0].pid, peerPid);
    await waitUntilDead(peerPid);
    assert.equal(alive(peerPid), false, `readiness worker leaked: ${peerPid}`);
    const submitted = await broker.delegate({
      workspace: harness.workspace,
      model,
      prompt: "Readiness must not fence or leak into a later same-workspace job.",
      timeoutMs: 30_000,
    });
    const completed = await broker.result({ jobId: submitted.jobId, waitMs: 30_000 });
    fixturePids.push(Number(await waitForFile(harness.peerPidFile)));
    assert.equal(completed.status, "completed", JSON.stringify(completed));
    assert.equal(completed.cleanupReady, true, JSON.stringify(completed));
  } finally {
    await broker.close().catch(() => {});
    for (const pid of fixturePids) await killExact(pid);
  }
});

async function writeRuntimeWrapper(harness, peerSource, extraArgs = []) {
  const launch = platformLaunch(currentPlatformId());
  const wrapper = path.join(harness.runtimeDir, path.basename(launch.runtimeCommand));
  const argv = [peerSource, harness.peerPidFile, ...extraArgs];
  await writeFile(
    wrapper,
    `#!/bin/sh\nexec ${process.execPath} ${argv.map((value) => JSON.stringify(value)).join(" ")}\n`,
    { mode: 0o700 },
  );
  await chmod(wrapper, 0o700);
}
