import { chmod, mkdtemp, mkdir, readFile, writeFile } from "node:fs/promises";
import { spawn } from "node:child_process";
import os from "node:os";
import path from "node:path";
import assert from "node:assert/strict";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { AntigravityAcpBroker, BridgeError } from "../broker.mjs";
import { currentPlatformId, platformLaunch, settingsPath } from "../contract.mjs";

const model = "gemini-3.8-flash-high";
const here = path.dirname(fileURLToPath(import.meta.url));
const peerSource = path.join(here, "fixtures/persistent-synthetic-acp-peer.mjs");
const ownerSource = path.join(here, "fixtures/owner-broker-child.mjs");
const packageRoot = path.resolve(here, "..");

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function waitForFile(filePath, timeoutMs = 10_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try { return (await readFile(filePath, "utf8")).trim(); } catch {}
    await sleep(20);
  }
  throw new Error(`timed out waiting for ${filePath}`);
}

async function waitForHeartbeatAdvance(filePath, previous, timeoutMs = 5_000) {
  const deadline = Date.now() + timeoutMs;
  const previousCount = Number(previous.trim().split("\n").at(-1));
  while (Date.now() < deadline) {
    try {
      const current = await readFile(filePath, "utf8");
      const currentCount = Number(current.trim().split("\n").at(-1));
      if (Number.isFinite(currentCount) && currentCount > previousCount) return current;
    } catch {}
    await sleep(30);
  }
  throw new Error(`heartbeat did not advance: ${filePath}`);
}

function alive(pid) {
  try { process.kill(pid, 0); return true; } catch { return false; }
}

async function killExact(pid) {
  if (!Number.isInteger(pid) || pid <= 0 || !alive(pid)) return;
  try { process.kill(pid, "SIGKILL"); } catch {}
  const deadline = Date.now() + 2_000;
  while (Date.now() < deadline && alive(pid)) await sleep(20);
}

async function makeRuntimeDir(dir, peerPidFile, heartbeatFile) {
  const launch = platformLaunch(currentPlatformId());
  await mkdir(dir);
  const wrapper = path.join(dir, path.basename(launch.runtimeCommand));
  const helper = path.join(dir, path.basename(launch.helper));
  await writeFile(
    wrapper,
    `#!/bin/sh\nexec ${process.execPath} ${JSON.stringify(peerSource)} ${JSON.stringify(peerPidFile)} ${JSON.stringify(heartbeatFile)}\n`,
    { mode: 0o700 },
  );
  await writeFile(helper, "#!/bin/sh\nexit 0\n", { mode: 0o700 });
  await chmod(wrapper, 0o700);
  await chmod(helper, 0o700);
}

test("owner broker death does not recover unresolved cleanup or lift the same-workspace fence", { timeout: 60_000 }, async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "saarius-pr52-owner-death-"));
  const workspace = path.join(root, "workspace");
  const independentWorkspace = path.join(root, "independent-workspace");
  const stateRoot = path.join(root, "state");
  const geminiHome = path.join(root, "gemini-home");
  const runtime1 = path.join(root, "runtime-owner");
  const runtime2 = path.join(root, "runtime-replacement");
  const peerPidFile1 = path.join(root, "peer-owner.pid");
  const peerPidFile2 = path.join(root, "peer-replacement.pid");
  const peerHeartbeat1 = path.join(root, "peer-owner.heartbeat");
  const peerHeartbeat2 = path.join(root, "peer-replacement.heartbeat");
  let ownerProcess;
  let ownerPeerPid;
  let replacementPeerPid;
  let second;

  try {
    await mkdir(workspace);
    await mkdir(independentWorkspace);
    await mkdir(path.dirname(settingsPath(geminiHome)), { recursive: true });
    await writeFile(
      settingsPath(geminiHome),
      JSON.stringify({ auth: { type: "oauth-personal" }, useG1Credits: false }),
    );
    await makeRuntimeDir(runtime1, peerPidFile1, peerHeartbeat1);
    await makeRuntimeDir(runtime2, peerPidFile2, peerHeartbeat2);

    let ownerOutput = "";
    let ownerError = "";
    ownerProcess = spawn(process.execPath, [ownerSource, stateRoot, workspace, runtime1, geminiHome], {
      cwd: packageRoot,
      env: { PATH: process.env.PATH ?? "" },
      stdio: ["ignore", "pipe", "pipe"],
    });
    ownerProcess.stdout.setEncoding("utf8");
    ownerProcess.stderr.setEncoding("utf8");
    ownerProcess.stdout.on("data", (chunk) => { ownerOutput += chunk; });
    ownerProcess.stderr.on("data", (chunk) => { ownerError += chunk; });
    const exit = await new Promise((resolve, reject) => {
      ownerProcess.once("error", reject);
      ownerProcess.once("exit", (code, signal) => resolve({ code, signal }));
    });
    assert.deepEqual(exit, { code: 0, signal: null }, ownerError);
    const ownerRecord = JSON.parse(ownerOutput.trim());
    assert.equal(ownerRecord.status, "completed", ownerOutput);
    assert.equal(ownerRecord.complete, false, ownerOutput);
    assert.equal(ownerRecord.cleanup, "uncertain", ownerOutput);
    assert.equal(alive(ownerRecord.pid), false, `owner still alive: ${ownerRecord.pid}`);
    ownerPeerPid = Number(await waitForFile(peerPidFile1));
    const ownerHeartbeatBeforeRecovery = await waitForFile(peerHeartbeat1);
    const ownerHeartbeatAfterOwnerExit = await waitForHeartbeatAdvance(peerHeartbeat1, ownerHeartbeatBeforeRecovery);

    second = new AntigravityAcpBroker({
      stateRoot,
      runtimeDir: runtime2,
      geminiHome,
      processEnv: { PATH: process.env.PATH ?? "" },
      defaultHostConversationId: "conv-owner-death",
      defaultBinderId: "test-owner",
    });
    await second.init();
    const recovered = await second.result({ jobId: ownerRecord.jobId, waitMs: 0 });
    assert.notEqual(recovered.cleanup?.status, "recovered", JSON.stringify(recovered));
    assert.notEqual(recovered.cleanup?.observed, "owner_gone", JSON.stringify(recovered));
    assert.equal(recovered.cleanup?.status, "uncertain", JSON.stringify(recovered));
    assert.equal(recovered.complete, false, JSON.stringify(recovered));
    assert.equal(recovered.cleanupReady, false, JSON.stringify(recovered));

    await assert.rejects(
      () => second.delegate({
        workspace,
        model,
        prompt: "Same-workspace replacement must stay fenced after owner death.",
        timeoutMs: 30_000,
      }),
      (error) => error instanceof BridgeError &&
        error.code === "WORKSPACE_CLEANUP_PENDING" &&
        error.details?.jobId === ownerRecord.jobId,
    );

    const ownerHeartbeatAfterBlockedReplacement = await waitForHeartbeatAdvance(
      peerHeartbeat1,
      ownerHeartbeatAfterOwnerExit,
    );

    const independent = await second.delegate({
      workspace: independentWorkspace,
      model,
      prompt: "Independent workspace remains admissible after owner death.",
      timeoutMs: 30_000,
    });
    const independentResult = await second.result({ jobId: independent.jobId, waitMs: 30_000 });
    assert.equal(independentResult.status, "completed", JSON.stringify(independentResult));
    replacementPeerPid = Number(await waitForFile(peerPidFile2));
    await waitForFile(peerHeartbeat2);
    assert.match(ownerHeartbeatAfterBlockedReplacement.trim(), /\d+/);
    assert.equal(alive(ownerPeerPid), true, `owner peer died before exact cleanup: ${ownerPeerPid}`);
  } finally {
    await second?.close().catch(() => {});
    await killExact(ownerProcess?.pid);
    await killExact(ownerPeerPid);
    await killExact(replacementPeerPid);
  }
});
