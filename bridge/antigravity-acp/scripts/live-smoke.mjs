#!/usr/bin/env node

import { appendFile, mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { AntigravityAcpBroker, redactSensitive } from "../broker.mjs";
import { RUNTIME_PIN, presentForbiddenEnvNames } from "../contract.mjs";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(scriptDir, "../../..");
const proofRoot = path.resolve(
  process.env.ANTIGRAVITY_ACP_PROOF_ROOT ??
    path.join(repoRoot, "runs", "puppet-roadmap-runs", "20260920-acpx-antigravity-plugin-followup", "live"),
);
const liveEvents = path.join(proofRoot, "events.jsonl");
const liveState = path.join(proofRoot, "STATE.md");
const liveProof = path.join(proofRoot, "PROOF.md");
const heartbeat = path.join(proofRoot, "heartbeat");

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

async function main() {
  await mkdir(proofRoot, { recursive: true, mode: 0o700 });
  await writeFile(liveEvents, "", { encoding: "utf8", mode: 0o600 });
  const broker = new AntigravityAcpBroker({
    stateRoot: path.join(proofRoot, "state"),
  });
  const evidence = {
    pin: RUNTIME_PIN,
    geminiHome: broker.geminiHome,
    forbiddenEnvNames: presentForbiddenEnvNames(broker.processEnv),
  };
  let outcome = "blocked";
  let failure = {
    code: "LIVE_SMOKE_GATED",
    message: "Live Antigravity smoke requires already-authorized personal OAuth and proven overage-disabled controls without account switching or billing changes.",
  };
  try {
    await event("smoke_preflight", {
      pin: RUNTIME_PIN,
      ultraAttribution: "unclaimed",
    });
    let launch;
    try {
      launch = await broker.resolveLaunch();
      evidence.runtime = { present: true, command: launch.command, helper: launch.helper };
    } catch (error) {
      evidence.runtime = { present: false, code: error.code };
      failure = { code: error.code, message: safe(error.message), repair: error.details?.repair };
      throw error;
    }
    try {
      evidence.auth = await broker.diagnoseAuth();
    } catch (error) {
      evidence.auth = {
        code: error.code,
        accountState: error.details?.accountState ?? "unproven",
        overageState: error.details?.overageState ?? "unproven",
        settingsAuthType: error.details?.settingsAuthType,
        forbiddenEnvNames: error.details?.forbiddenEnvNames ?? [],
      };
      failure = { code: error.code, message: safe(error.message), repair: error.details?.repair };
      throw error;
    }
    failure = {
      code: "LIVE_SMOKE_NOT_AUTHORIZED_HERE",
      message: "Preflight found a local runtime and policy files, but this follow-up will not send a live model request or complete login from the plugin worker.",
    };
  } catch (error) {
    if (!failure.code) {
      failure = { code: error?.code ?? "LIVE_SMOKE_FAILED", message: safe(error?.message ?? error) };
    }
    await event("smoke_blocked", { code: failure.code });
  } finally {
    await broker.close();
  }

  const proof = [
    "# Live Antigravity ACP smoke proof",
    "",
    `Outcome: ${outcome}`,
    `Runtime pin: ${RUNTIME_PIN.id} ${RUNTIME_PIN.version} / acpx ${RUNTIME_PIN.acpxRelease}`,
    "",
    "## Evidence",
    "",
    "```json",
    JSON.stringify(evidence, null, 2),
    "```",
    "",
    `## Bounded blocker`,
    "",
    JSON.stringify(failure, null, 2),
    "",
    "Raw ACP transcripts, prompts, questions, credentials, and auth logs are intentionally not recorded. No login or billing change was attempted.",
  ].join("\n");
  await writeFile(liveProof, `${proof}\n`, { encoding: "utf8", mode: 0o600 });
  await writeFile(
    liveState,
    [
      "# Live Antigravity ACP smoke",
      "",
      `Status: ${outcome}`,
      `Runtime: ${RUNTIME_PIN.id} ${RUNTIME_PIN.version}`,
      `Proof: ${liveProof}`,
    ].join("\n") + "\n",
    { encoding: "utf8", mode: 0o600 },
  );
  await event("smoke_finished", { outcome, proof: liveProof });
  process.stdout.write(`${JSON.stringify({ outcome, proof: liveProof, evidence, failure })}\n`);
  process.exitCode = 2;
}

await main();
