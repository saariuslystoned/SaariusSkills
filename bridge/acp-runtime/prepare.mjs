#!/usr/bin/env node
import { prepareRuntime, pluginRootFromModule, bridgeNames, RuntimeStoreError } from "./runtime-store.mjs";

function report(value, code = 0) {
  console.log(JSON.stringify(value));
  process.exitCode = code;
}

async function main() {
  const args = process.argv.slice(2);
  const bridgeIndex = args.indexOf("--bridge");
  const bridge = bridgeIndex >= 0 ? args[bridgeIndex + 1] : undefined;
  if (args.length !== 2 || bridgeIndex !== 0 || !bridge || !bridgeNames().includes(bridge)) {
    report({ ok: false, code: "INVALID_ARGUMENT", usage: `prepare.mjs --bridge <${bridgeNames().join("|" )}>` }, 2);
    return;
  }
  try {
    const result = await prepareRuntime({ pluginRoot: pluginRootFromModule(), bridge });
    report({ ok: true, code: result.reused ? "RUNTIME_REUSED" : "RUNTIME_READY", bridge, root: result.root, identity: result.descriptor.identity });
  } catch (error) {
    const details = error instanceof RuntimeStoreError ? { code: error.code, message: error.message, details: error.details } : { code: "RUNTIME_PREPARE_FAILED", message: error?.message ?? String(error) };
    report({ ok: false, ...details }, 2);
  }
}

main().catch((error) => report({ ok: false, code: "RUNTIME_PREPARE_FAILED", message: error?.message ?? String(error) }, 2));
