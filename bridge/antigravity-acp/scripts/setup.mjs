#!/usr/bin/env node
// Installation health check; no Antigravity session or model turn is started.
import { spawnSync } from "node:child_process";
import { accessSync, constants } from "node:fs";
import { mkdtemp, readFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
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
  if (args.includes("--install")) {
    const install = spawnSync("npm", ["ci", "--ignore-scripts", "--no-audit", "--no-fund"], {
      cwd: root, timeout: 120_000, stdio: "ignore",
    });
    if (install.status !== 0) {
      report({
        ok: false,
        code: "DEPENDENCY_INSTALL_FAILED",
        exitCode: install.status,
        pin: RUNTIME_PIN,
        repair: ["npm ci --ignore-scripts --no-audit --no-fund"],
        runtimeRepair: runtimeRepair(),
      }, 2);
      return;
    }
  }
  let Client, StdioClientTransport;
  try {
    ({ Client } = await import("@modelcontextprotocol/sdk/client/index.js"));
    ({ StdioClientTransport } = await import("@modelcontextprotocol/sdk/client/stdio.js"));
    await import("acpx/runtime");
    await import("zod");
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
  const runtime = diagnoseLockedRuntime();
  const auth = await diagnoseAuthPolicy();
  const client = new Client({ name: "antigravity-acp-setup", version: "1.0.0" });
  const pluginRoot = path.resolve(root, "../..");
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
