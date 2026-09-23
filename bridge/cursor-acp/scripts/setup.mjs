#!/usr/bin/env node
// Installation health check; no Cursor session or model turn is started.
import { spawnSync } from "node:child_process";
import { mkdtemp, readFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const script = fileURLToPath(import.meta.url);
const root = path.resolve(path.dirname(script), "..");
const expected = ["readiness", "delegate", "status", "result", "steer", "cancel"]
  .map((name) => `cursor_acp_${name}`).sort();
const report = (value, code = 0) => {
  console.log(JSON.stringify(value));
  process.exitCode = code;
};

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
      report({ ok: false, code: "DEPENDENCY_INSTALL_FAILED", exitCode: install.status }, 2);
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
    report({ ok: false, code: "DEPENDENCIES_MISSING", repair: [process.execPath, script, "--install"] }, 2);
    return;
  }
  const { findReady, setupCommand } = await import("../../acp-runtime/runtime-store.mjs");
  const client = new Client({ name: "cursor-acp-setup", version: "1.0.0" });
  const pluginRoot = path.resolve(root, "../..");
  if (!(await findReady({ pluginRoot, bridge: "cursor-acp" }))) {
    report({
      ok: false,
      code: "RUNTIME_SETUP_REQUIRED",
      repair: [setupCommand("cursor-acp")],
      note: "Prepare the shared persistent ACP runtime after installing or refreshing the plugin; MCP startup does not install dependencies.",
    }, 2);
    return;
  }
  const config = JSON.parse(await readFile(path.join(pluginRoot, ".mcp.json"), "utf8"))
    .mcpServers["cursor-acp"];
  const stateRoot = await mkdtemp(path.join(tmpdir(), "cursor-acp-setup-"));
  const transport = new StdioClientTransport({
    command: config.command,
    args: config.args,
    cwd: path.resolve(pluginRoot, config.cwd ?? "."),
    env: {
      PATH: process.env.PATH ?? "",
      HOME: process.env.HOME ?? "",
      ...config.env,
      ...(process.env.SAARIUS_ACP_RUNTIME_ROOT ? { SAARIUS_ACP_RUNTIME_ROOT: process.env.SAARIUS_ACP_RUNTIME_ROOT } : {}),
      SAARIUS_CURSOR_ACP_STATE_DIR: stateRoot,
    },
    stderr: "pipe",
  });
  // Do not copy server diagnostics or potential payloads into setup output.
  transport.stderr?.resume();
  const timer = setTimeout(() => { void transport.close(); }, 15_000);
  try {
    await client.connect(transport);
    const tools = (await client.listTools()).tools.map((tool) => tool.name).sort();
    const ok = JSON.stringify(tools) === JSON.stringify(expected);
    report({ ok, code: ok ? "MCP_READY" : "TOOL_CATALOG_MISMATCH", tools, liveCursorChecked: false }, ok ? 0 : 2);
  } catch {
    report({ ok: false, code: "MCP_STARTUP_FAILED" }, 2);
  } finally {
    clearTimeout(timer);
    await client.close();
  }
}
main().catch(() => report({ ok: false, code: "SETUP_FAILED" }, 2));
