#!/usr/bin/env node
import path from "node:path";
import { inspectRuntime, pluginRootFromModule, setupCommand, RuntimeStoreError } from "./runtime-store.mjs";
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
      const ready = await inspectRuntime({ pluginRoot, bridge });
      if (ready.state === "missing") {
        // Identity includes the Node version, so a Node upgrade lands here too.
        fail(new RuntimeStoreError("RUNTIME_SETUP_REQUIRED", "persistent bridge runtime is not prepared for this plugin source and Node runtime", {
          state: "missing",
          identity: ready.descriptor.identity,
          nodeVersion: ready.descriptor.platform.nodeVersion,
        }));
      } else if (ready.state === "invalid") {
        fail(new RuntimeStoreError("RUNTIME_SETUP_REQUIRED", "persistent bridge runtime failed integrity validation", {
          state: "invalid",
          root: ready.root,
          ...ready.failure,
          recovery: setupCommand(bridge, { replaceInvalid: true }),
        }));
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
