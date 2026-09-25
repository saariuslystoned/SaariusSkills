#!/usr/bin/env node
import path from "node:path";
import { findReady, pluginRootFromModule, setupCommand, RuntimeStoreError } from "./runtime-store.mjs";
import { HOP_WORKER_FLAG, HopError, resolveHop, spawnStdioChild } from "./hop.mjs";

const bridge = process.argv[2];
const workerMode = process.argv.slice(3).includes(HOP_WORKER_FLAG);
const pluginRoot = pluginRootFromModule();

function fail(error) {
  const details = error instanceof RuntimeStoreError
    ? { code: error.code, message: error.message, details: error.details }
    : error instanceof HopError
      ? { code: error.code, message: error.message, details: error.details }
      : { code: "RUNTIME_LOOKUP_FAILED", message: error?.message ?? String(error) };
  process.stderr.write(`${JSON.stringify({ status: "error", bridge, ...details, setup: setupCommand(bridge) })}\n`);
  process.exitCode = 2;
}

function attachChild(child, onError) {
  child.once("error", onError);
  child.once("exit", (code, signal) => {
    if (signal) process.kill(process.pid, signal);
    else process.exitCode = code ?? 1;
  });
}

if (!bridge) {
  fail(new RuntimeStoreError("INVALID_ARGUMENT", "bridge name is required"));
} else {
  try {
    const hop = resolveHop({ env: process.env, bridge, workerMode });
    if (hop.mode === "hop") {
      process.stderr.write(`${JSON.stringify({
        status: "hop",
        bridge,
        argvCount: hop.argv.length,
        identity: hop.identity,
      })}\n`);
      const child = spawnStdioChild({
        command: hop.argv[0],
        args: hop.argv.slice(1),
        cwd: process.cwd(),
        env: hop.childEnv,
      });
      attachChild(child, (error) => fail(new RuntimeStoreError("HOP_LAUNCH_FAILED", "host hop command could not start", {
        cause: error.code,
        identity: hop.identity,
      })));
    } else {
      const ready = await findReady({ pluginRoot, bridge });
      if (!ready) {
        fail(new RuntimeStoreError("RUNTIME_SETUP_REQUIRED", "persistent bridge runtime is not prepared or failed integrity validation"));
      } else {
        const entry = path.join(ready.root, "bridge", bridge, "server.mjs");
        const child = spawnStdioChild({
          command: process.execPath,
          args: [entry],
          cwd: process.cwd(),
          env: process.env,
        });
        attachChild(child, (error) => fail(new RuntimeStoreError("RUNTIME_LAUNCH_FAILED", "persistent bridge server could not start", {
          cause: error.code,
        })));
      }
    }
  } catch (error) {
    fail(error);
  }
}
