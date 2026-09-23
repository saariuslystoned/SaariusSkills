#!/usr/bin/env node
import { spawn } from "node:child_process";
import path from "node:path";
import { findReady, pluginRootFromModule, setupCommand, RuntimeStoreError } from "./runtime-store.mjs";

const bridge = process.argv[2];
const pluginRoot = pluginRootFromModule();

function fail(error) {
  const details = error instanceof RuntimeStoreError
    ? { code: error.code, message: error.message, details: error.details }
    : { code: "RUNTIME_LOOKUP_FAILED", message: error?.message ?? String(error) };
  process.stderr.write(`${JSON.stringify({ status: "error", bridge, ...details, setup: setupCommand(bridge) })}\n`);
  process.exitCode = 2;
}

if (!bridge) {
  fail(new RuntimeStoreError("INVALID_ARGUMENT", "bridge name is required"));
} else {
  try {
    const ready = await findReady({ pluginRoot, bridge });
    if (!ready) {
      fail(new RuntimeStoreError("RUNTIME_SETUP_REQUIRED", "persistent bridge runtime is not prepared or failed integrity validation"));
    } else {
      const entry = path.join(ready.root, "bridge", bridge, "server.mjs");
      const child = spawn(process.execPath, [entry], {
        cwd: process.cwd(),
        env: process.env,
        stdio: "inherit",
      });
      const forward = (signal) => { if (!child.killed) child.kill(signal); };
      const onSigint = () => forward("SIGINT");
      const onSigterm = () => forward("SIGTERM");
      process.once("SIGINT", onSigint);
      process.once("SIGTERM", onSigterm);
      child.once("error", (error) => fail(new RuntimeStoreError("RUNTIME_LAUNCH_FAILED", "persistent bridge server could not start", { cause: error.code })));
      child.once("exit", (code, signal) => {
        process.removeListener("SIGINT", onSigint);
        process.removeListener("SIGTERM", onSigterm);
        if (signal) process.kill(process.pid, signal);
        else process.exitCode = code ?? 1;
      });
    }
  } catch (error) {
    fail(error);
  }
}
