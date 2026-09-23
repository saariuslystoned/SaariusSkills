#!/usr/bin/env node
// Installation health check; no Antigravity session or model turn is started.
import { accessSync, constants } from "node:fs";
import { mkdtemp, readFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import {
  PROFILE_ENV,
  RUNTIME_PIN,
  TOOL_NAMES,
  authRepair,
  currentPlatformId,
  defaultGeminiHome,
  defaultRuntimeDir,
  platformLaunch,
  presentForbiddenEnvNames,
  runtimeRepair,
  settingsPath,
} from "../contract.mjs";

const script = fileURLToPath(import.meta.url);
const root = path.resolve(path.dirname(script), "..");
const expected = [...TOOL_NAMES].sort();
const report = (value, code = 0) => {
  console.log(JSON.stringify(value));
  process.exitCode = code;
};

function present(filePath) {
  try {
    accessSync(filePath, constants.X_OK);
    return true;
  } catch {
    return false;
  }
}

function diagnoseLockedRuntime(env = process.env) {
  const platformId = currentPlatformId();
  const launch = platformLaunch(platformId);
  const repair = runtimeRepair(platformId);
  if (!launch) {
    return {
      present: false,
      platformId,
      pin: RUNTIME_PIN,
      helperPresent: false,
      repair,
    };
  }
  const basename = path.basename(launch.runtimeCommand);
  const helperName = path.basename(launch.helper);
  const runtimeDir = env.ANTIGRAVITY_ACP_RUNTIME_DIR?.trim() || defaultRuntimeDir(platformId);
  const runtimeServer = env.ANTIGRAVITY_ACP_SERVER?.trim();
  const helperOverride = env.ANTIGRAVITY_HARNESS_PATH?.trim();
  const command = runtimeServer
    ? path.resolve(runtimeServer)
    : runtimeDir
      ? path.resolve(runtimeDir, basename)
      : undefined;
  const helper = helperOverride
    ? path.resolve(helperOverride)
    : command
      ? path.join(path.dirname(command), helperName)
      : undefined;
  return {
    present: Boolean(command && present(command)),
    helperPresent: Boolean(helper && present(helper)),
    platformId,
    command: command ?? basename,
    helper: helper ?? helperName,
    pin: RUNTIME_PIN,
    archive: launch.archive,
    silentlyInstalled: false,
    repair,
  };
}

async function diagnoseAuthPolicy(env = process.env) {
  const geminiHome = path.resolve(
    env.SAARIUS_ANTIGRAVITY_ACP_GEMINI_HOME?.trim() || env.GEMINI_HOME?.trim() || defaultGeminiHome(),
  );
  const forbidden = presentForbiddenEnvNames(env);
  let settingsAuthType = "missing";
  let overageState = "unproven";
  try {
    const parsed = JSON.parse(await readFile(settingsPath(geminiHome), "utf8"));
    settingsAuthType = typeof parsed?.auth?.type === "string" ? parsed.auth.type : "missing";
    overageState =
      parsed?.useG1Credits === false ? "never" : parsed?.useG1Credits === true ? "enabled" : "unproven";
  } catch {
    // Absence is a setup diagnosis, not a credential read.
  }
  return {
    profileEnv: PROFILE_ENV,
    profilePath: geminiHome,
    mode: "oauth-personal",
    settingsAuthType,
    overageState,
    forbiddenEnvNames: forbidden,
    ultraAttribution: "unclaimed",
    repair: authRepair(geminiHome),
  };
}

async function main() {
  const args = process.argv.slice(2);
  if (args.some((arg) => !["--check", "--install"].includes(arg))) {
    report({ ok: false, code: "INVALID_ARGUMENT", usage: "setup.mjs [--check|--install]" }, 2);
    return;
  }
  const pluginRoot = path.resolve(root, "../..");
  let runtimeStore;
  try {
    runtimeStore = await import("../../acp-runtime/runtime-store.mjs");
  } catch {
    report({
      ok: false,
      code: "DEPENDENCIES_MISSING",
      repair: [process.execPath, script, "--install"],
      pin: RUNTIME_PIN,
      runtimeRepair: runtimeRepair(),
    }, 2);
    return;
  }
  const { findReady, prepareRuntime, setupCommand } = runtimeStore;
  let ready = await findReady({ pluginRoot, bridge: "antigravity-acp" });
  if (args.includes("--install")) {
    try {
      ready = await prepareRuntime({ pluginRoot, bridge: "antigravity-acp" });
    } catch (error) {
      report({
        ok: false,
        code: error?.code ?? "DEPENDENCY_INSTALL_FAILED",
        details: error?.details,
        pin: RUNTIME_PIN,
        runtimeRepair: runtimeRepair(),
        repair: [setupCommand("antigravity-acp")],
      }, 2);
      return;
    }
  }
  const runtime = diagnoseLockedRuntime();
  const auth = await diagnoseAuthPolicy();
  if (!ready) {
    report({
      ok: false,
      code: "RUNTIME_SETUP_REQUIRED",
      repair: [setupCommand("antigravity-acp")],
      runtime,
      auth,
      note: "Prepare the shared persistent ACP runtime after installing or refreshing the plugin; MCP startup does not install dependencies.",
    }, 2);
    return;
  }
  const runtimeBridgeRoot = path.join(ready.root, "bridge", "antigravity-acp");
  let Client, StdioClientTransport;
  try {
    ({ Client } = await import(pathToFileURL(path.join(runtimeBridgeRoot, "node_modules/@modelcontextprotocol/sdk/dist/esm/client/index.js")).href));
    ({ StdioClientTransport } = await import(pathToFileURL(path.join(runtimeBridgeRoot, "node_modules/@modelcontextprotocol/sdk/dist/esm/client/stdio.js")).href));
    await import(pathToFileURL(path.join(runtimeBridgeRoot, "node_modules/acpx/dist/runtime.js")).href);
    await import(pathToFileURL(path.join(runtimeBridgeRoot, "node_modules/zod/index.js")).href);
  } catch {
    report({
      ok: false,
      code: "RUNTIME_SETUP_REQUIRED",
      repair: [setupCommand("antigravity-acp")],
      pin: RUNTIME_PIN,
      runtimeRepair: runtimeRepair(),
    }, 2);
    return;
  }
  const client = new Client({ name: "antigravity-acp-setup", version: "1.0.0" });
  const config = JSON.parse(await readFile(path.join(pluginRoot, ".mcp.json"), "utf8"))
    .mcpServers["antigravity-acp"];
  if (!config) {
    report({
      ok: false,
      code: "MCP_SERVER_UNREGISTERED",
      repair: ["Add a separately named antigravity-acp server to root .mcp.json"],
      pin: RUNTIME_PIN,
      runtime,
      auth,
    }, 2);
    return;
  }
  const stateRoot = await mkdtemp(path.join(tmpdir(), "antigravity-acp-setup-"));
  const transport = new StdioClientTransport({
    command: config.command,
    args: config.args,
    cwd: path.resolve(pluginRoot, config.cwd ?? "."),
    env: {
      PATH: process.env.PATH ?? "",
      HOME: process.env.HOME ?? "",
      ...config.env,
      ...(process.env.SAARIUS_ACP_RUNTIME_ROOT ? { SAARIUS_ACP_RUNTIME_ROOT: process.env.SAARIUS_ACP_RUNTIME_ROOT } : {}),
      SAARIUS_ANTIGRAVITY_ACP_STATE_DIR: stateRoot,
    },
    stderr: "pipe",
  });
  transport.stderr?.resume();
  const timer = setTimeout(() => { void transport.close(); }, 15_000);
  try {
    await client.connect(transport);
    const tools = (await client.listTools()).tools.map((tool) => tool.name).sort();
    const ok = JSON.stringify(tools) === JSON.stringify(expected);
    report({
      ok,
      code: ok ? "MCP_READY" : "TOOL_CATALOG_MISMATCH",
      tools,
      liveAntigravityChecked: false,
      pin: RUNTIME_PIN,
      runtime,
      auth,
      note: "MCP_READY proves server startup and the six-tool catalog, not native-tool reload, login, or a model turn. Setup never downloads the Google runtime.",
    }, ok ? 0 : 2);
  } catch {
    report({
      ok: false,
      code: "MCP_STARTUP_FAILED",
      pin: RUNTIME_PIN,
      runtime,
      auth,
      repair: runtime.repair,
    }, 2);
  } finally {
    clearTimeout(timer);
    await client.close();
  }
}
main().catch(() => report({ ok: false, code: "SETUP_FAILED", pin: RUNTIME_PIN }, 2));
