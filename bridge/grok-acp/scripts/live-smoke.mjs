#!/usr/bin/env node

import { appendFile, mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { redactSensitive } from "../broker.mjs";
import {
  createLiveSmokeBroker,
  requireLiveSmokePermission,
  waitForCleanup,
} from "./live-smoke-policy.mjs";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(scriptDir, "../../..");
const proofRoot = path.resolve(
  process.env.GROK_ACP_PROOF_ROOT ??
    path.join(repoRoot, "runs", "grok-acp-delegation-20260925", "live"),
);
const liveEvents = path.join(proofRoot, "events.jsonl");
const liveState = path.join(proofRoot, "STATE.md");
const liveProof = path.join(proofRoot, "PROOF.md");
const heartbeat = path.join(proofRoot, "heartbeat");

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

class StopSmoke extends Error {}

function safe(value, max = 800) {
  const text = redactSensitive(value).replace(/\s+/g, " ").trim();
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

async function event(event, details = {}) {
  const timestamp = new Date().toISOString();
  await appendFile(liveEvents, `${JSON.stringify({ timestamp, event, details })}\n`, {
    encoding: "utf8",
    mode: 0o600,
  });
  await writeFile(heartbeat, `${timestamp}\n`, { encoding: "utf8", mode: 0o600 });
}

async function waitForActive(broker, jobId, timeoutMs = 15_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (broker.active.get(jobId)?.turn) return true;
    await sleep(100);
  }
  return false;
}

async function requireCleanupReady(broker, jobId, label) {
  const cleanup = await waitForCleanup(broker, jobId);
  if (!cleanup.ready) {
    throw Object.assign(new StopSmoke(), {
      smokeFailure: {
        code: cleanup.code,
        message: `${label}: ${cleanup.message}`,
      },
    });
  }
  return cleanup.job;
}

async function main() {
  // Refuse before creating a broker/runtime. Live smoke exercises write/exec
  // approval and therefore requires the explicit break-glass environment flag.
  requireLiveSmokePermission(process.env);
  await mkdir(proofRoot, { recursive: true, mode: 0o700 });
  await writeFile(liveEvents, "", { encoding: "utf8", mode: 0o600 });
  await writeFile(
    liveState,
    [
      "# Live Grok ACP smoke",
      "",
      "Status: running",
      "Route: grok agent stdio",
      "Model: grok-4.7",
      `Proof root: ${proofRoot}`,
      "",
    ].join("\n"),
    { encoding: "utf8", mode: 0o600 },
  );
  await event("smoke_started", { proofRoot });

  const workspace = await mkdtemp(path.join(os.tmpdir(), "grok-acp-live-"));
  const smoke = createLiveSmokeBroker({
    stateRoot: path.join(proofRoot, "state"),
    defaultWorkspace: workspace,
  });
  const { broker, hostConversationId, binderId } = smoke;
  const evidence = { workspace, route: broker.grokExecutable, model: broker.model };
  let outcome = "passed";
  let failure = null;
  try {
    const readiness = await broker.discover({ workspace });
    evidence.readiness = {
      ready: readiness.ready,
      model: readiness.model,
      version: readiness.executable?.version,
      sessionOpened: Boolean(readiness.session),
    };
    await event("readiness", evidence.readiness);
    if (!readiness.ready) {
      outcome = "blocked";
      failure = readiness.error;
      throw new StopSmoke();
    }

    const completionJob = await broker.delegate({
      workspace,
      hostConversationId,
      binderId,
      timeoutMs: 180_000,
      prompt: [
        "Perform a read-only binding check in the supplied workspace.",
        "Run pwd once, do not modify files, do not access secrets or the network,",
        "and finish with the absolute workspace path, selected model if known,",
        "and a one-line bounded handoff.",
      ].join(" "),
    });
    const completion = await broker.result({ jobId: completionJob.jobId, waitMs: 180_000 });
    evidence.completion = {
      jobId: completion.jobId,
      status: completion.status,
      model: completion.model,
      handoff: completion.handoff,
      proof: completion.proof,
    };
    await event("completion", evidence.completion);
    if (completion.status !== "completed") {
      outcome = "blocked";
      failure = completion.error ?? { code: completion.status, message: "completion did not finish" };
      throw new StopSmoke();
    }
    const completionCleanup = await requireCleanupReady(
      broker,
      completionJob.jobId,
      "completion cleanup",
    );
    evidence.completion.cleanupReady = completionCleanup.cleanup;

    const steeringJob = await broker.delegate({
      workspace,
      hostConversationId,
      binderId,
      timeoutMs: 180_000,
      prompt: [
        "Run the local command sleep 12 in the supplied workspace.",
        "Do not edit files or access secrets/network.",
        "After the command, report only the bounded handoff.",
      ].join(" "),
    });
    if (!(await waitForActive(broker, steeringJob.jobId))) {
      outcome = "blocked";
      failure = { code: "STEER_NOT_ACTIVE", message: "live job did not expose an active ACP turn" };
      throw new StopSmoke();
    }
    let steeringCode;
    try {
      await broker.steer({
        jobId: steeringJob.jobId,
        message: "This request must refuse without enqueueing another turn.",
      });
    } catch (error) {
      steeringCode = error.code;
    }
    const steeringResult = await broker.result({ jobId: steeringJob.jobId, waitMs: 180_000 });
    evidence.steering = {
      refused: steeringCode === "STEERING_UNSUPPORTED",
      code: steeringCode,
      finalStatus: steeringResult.status,
      proof: steeringResult.proof,
    };
    await event("steering_refusal", evidence.steering);
    if (!evidence.steering.refused || steeringResult.status !== "completed") {
      outcome = "blocked";
      failure = steeringResult.error ?? { code: "STEER_REFUSAL_FAILED", message: "steering refusal/completion proof failed" };
      throw new StopSmoke();
    }
    const steeringCleanup = await requireCleanupReady(
      broker,
      steeringJob.jobId,
      "steering cleanup",
    );
    evidence.steering.cleanupReady = steeringCleanup.cleanup;

    const cancellationJob = await broker.delegate({
      workspace,
      hostConversationId,
      binderId,
      timeoutMs: 180_000,
      prompt: [
        "Run the local command sleep 30 in the supplied workspace.",
        "Do not edit files or access secrets/network, and report only after the command.",
      ].join(" "),
    });
    if (!(await waitForActive(broker, cancellationJob.jobId))) {
      outcome = "blocked";
      failure = { code: "CANCEL_NOT_ACTIVE", message: "live job did not expose an active ACP turn" };
      throw new StopSmoke();
    }
    const cancellation = await broker.cancel({
      jobId: cancellationJob.jobId,
      reason: "bounded cancellation proof",
    });
    const cancellationResult = await broker.result({ jobId: cancellationJob.jobId, waitMs: 60_000 });
    evidence.cancellation = {
      requested: cancellation.status === "cancellation-requested",
      finalStatus: cancellationResult.status,
      proof: cancellationResult.proof,
    };
    await event("cancellation", evidence.cancellation);
    if (cancellationResult.status !== "cancelled") {
      outcome = "blocked";
      failure = cancellationResult.error ?? { code: "CANCEL_FAILED", message: "cancellation proof failed" };
    } else {
      const cancellationCleanup = await requireCleanupReady(
        broker,
        cancellationJob.jobId,
        "cancellation cleanup",
      );
      evidence.cancellation.cleanupReady = cancellationCleanup.cleanup;
    }
  } catch (error) {
    if (error instanceof StopSmoke) {
      outcome = "blocked";
      failure = error.smokeFailure ?? failure ?? {
        code: "LIVE_SMOKE_BLOCKED",
        message: "Smoke stopped before its bounded proof completed.",
      };
    } else {
      outcome = "blocked";
      failure = { code: error?.code ?? "LIVE_SMOKE_FAILED", message: safe(error?.message ?? error) };
      await event("smoke_error", failure);
    }
  } finally {
    await broker.close();
    await rm(workspace, { recursive: true, force: true });
  }

  const proof = [
    "# Live Grok ACP smoke proof",
    "",
    `Outcome: ${outcome}`,
    `Route: ${evidence.route} acp`,
    `Model: ${evidence.model}`,
    `Disposable workspace: ${evidence.workspace}`,
    "",
    "## Evidence",
    "",
    "```json",
    JSON.stringify(evidence, null, 2),
    "```",
    "",
    failure ? `## Bounded blocker\n\n${JSON.stringify(failure, null, 2)}` : "",
    "",
    "Raw ACP transcripts, thought streams, credentials, and auth logs are intentionally not recorded.",
  ].join("\n");
  await writeFile(liveProof, `${proof}\n`, { encoding: "utf8", mode: 0o600 });
  await writeFile(
    liveState,
    [
      "# Live Grok ACP smoke",
      "",
      `Status: ${outcome}`,
      `Route: ${evidence.route} acp`,
      `Model: ${evidence.model}`,
      `Proof: ${liveProof}`,
    ].join("\n") + "\n",
    { encoding: "utf8", mode: 0o600 },
  );
  await event("smoke_finished", { outcome, proof: liveProof });
  process.stdout.write(`${JSON.stringify({ outcome, proof: liveProof, evidence })}\n`);
  if (outcome !== "passed") process.exitCode = 2;
}

await main();
