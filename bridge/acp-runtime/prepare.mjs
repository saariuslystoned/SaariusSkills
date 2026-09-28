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
  // Fail closed by default; --replace-invalid quarantines (never deletes) an
  // invalid same-identity tree before preparing a fresh one.
  const replaceInvalid = args[2] === "--replace-invalid";
  if (args.length !== (replaceInvalid ? 3 : 2) || bridgeIndex !== 0 || !bridge || !bridgeNames().includes(bridge)) {
    report({ ok: false, code: "INVALID_ARGUMENT", usage: `prepare.mjs --bridge <${bridgeNames().join("|" )}> [--replace-invalid]` }, 2);
    return;
  }
  try {
    const result = await prepareRuntime({ pluginRoot: pluginRootFromModule(), bridge, replaceInvalid });
    report({
      ok: true,
      code: result.reused ? "RUNTIME_REUSED" : "RUNTIME_READY",
      bridge,
      root: result.root,
      identity: result.descriptor.identity,
      ...(result.quarantined ? { quarantined: result.quarantined } : {}),
    });
  } catch (error) {
    const details = error instanceof RuntimeStoreError ? { code: error.code, message: error.message, details: error.details } : { code: "RUNTIME_PREPARE_FAILED", message: error?.message ?? String(error) };
    report({ ok: false, ...details }, 2);
  }
}

main().catch((error) => report({ ok: false, code: "RUNTIME_PREPARE_FAILED", message: error?.message ?? String(error) }, 2));
