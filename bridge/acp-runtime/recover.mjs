#!/usr/bin/env node
// Explicit operator utility. Planning does not initialize/reconcile all jobs.
import { pathToFileURL } from "node:url";
import path from "node:path";
import { realpathSync } from "node:fs";
import { inspectRuntime, pluginRootFromModule, setupCommand, RuntimeStoreError } from "./runtime-store.mjs";

export async function main(argv = process.argv.slice(2)) {
  if (argv.includes("--help")) {
    console.log("Usage: node bridge/acp-runtime/recover.mjs --lane antigravity|cursor|grok --state-root ABSOLUTE --job UUID --conversation ID --expected-binder ID [--apply]\nDefaults to a plan. Apply only after human approval of exact ownership evidence. Never kills processes.");
    return;
  }
  const options = {};
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === "--apply") options.apply = true;
    else if (["--lane", "--state-root", "--job", "--conversation", "--expected-binder"].includes(argv[i])) {
      if (!argv[i + 1] || argv[i + 1].startsWith("--")) throw new Error(`Missing value for ${argv[i]}`);
      options[argv[i].slice(2)] = argv[++i];
    } else throw new Error(`Unknown argument ${argv[i]}`);
  }
  if (!["antigravity", "cursor", "grok"].includes(options.lane) || !options["state-root"]?.startsWith("/")) throw new Error("Explicit lane and absolute state root required");
  const bridge = `${options.lane}-acp`;
  const ready = await inspectRuntime({ pluginRoot: pluginRootFromModule(), bridge });
  if (ready.state !== "ready") throw new RuntimeStoreError("RUNTIME_SETUP_REQUIRED", "Recovery requires the prepared, integrity-checked bridge runtime", {
    state: ready.state, setup: setupCommand(bridge), ...(ready.failure ?? {}),
  });
  const module = await import(pathToFileURL(path.join(ready.root, "bridge", bridge, "broker.mjs")).href);
  const Broker = module[{ antigravity: "AntigravityAcpBroker", cursor: "CursorAcpBroker", grok: "GrokAcpBroker" }[options.lane]];
  const broker = new Broker({ stateRoot: options["state-root"], runtime: {} });
  const probe = await broker.inspectProcess(process.pid);
  if (probe.status !== "alive" || !probe.startTime) throw new Error("Recovery process identity unobservable");
  broker.startTime = probe.startTime;
  console.log(JSON.stringify(await broker.recoverConversation({
    jobId: options.job, hostConversationId: options.conversation,
    expectedBinderId: options["expected-binder"], apply: options.apply ?? false,
  }), null, 2));
}
if (process.argv[1] && import.meta.url === pathToFileURL(realpathSync(process.argv[1])).href) {
  main().catch((error) => { console.error(JSON.stringify({ code: error.code ?? "RECOVERY_ERROR", message: error.message, details: error.details })); process.exitCode = 1; });
}
