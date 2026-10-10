import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import {
  BREAK_GLASS_PERMISSION_MODE,
  LIVE_PERMISSION_MODE,
  PERMISSION_MODE_ENV,
} from "../../antigravity-acp/host-policy.mjs";

// Issue #92: Claude Code launches the bridges from the inline mcpServers block
// in .claude-plugin/plugin.json, which replaces the same-named .mcp.json entry.
// The two files must not drift: every route must reach the launcher with the
// same policy env, and the shipped default must stay approve-reads.

const here = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(here, "../../..");
const EXPANSION = /^\$\{[A-Z0-9_]+(:-[^}]*)?\}$/;
const POLICY_PASSTHROUGH = `\${${PERMISSION_MODE_ENV}:-${LIVE_PERMISSION_MODE}}`;

async function readJson(relative) {
  return JSON.parse(await readFile(path.join(repoRoot, relative), "utf8"));
}

function isMachineLocal(value) {
  return typeof value === "string" && path.isAbsolute(value);
}

// jev-decision is a plain MCP server, not an ACP launcher route, so it carries
// no permission policy; its own manifest entries are checked below.
const NON_ACP_SERVERS = new Set(["jev-decision"]);

function acpRoutes(servers) {
  return Object.entries(servers).filter(([name]) => !NON_ACP_SERVERS.has(name));
}

test("plugin.json and .mcp.json declare the same launcher routes", async () => {
  const claude = await readJson(".claude-plugin/plugin.json");
  const codex = await readJson(".mcp.json");
  assert.deepEqual(Object.keys(claude.mcpServers).sort(), Object.keys(codex.mcpServers).sort());
  for (const [name, server] of acpRoutes(claude.mcpServers)) {
    assert.equal(server.command, "node", name);
    assert.deepEqual(server.args, ["${CLAUDE_PLUGIN_ROOT}/bridge/acp-runtime/launcher.mjs", name]);
    assert.deepEqual(codex.mcpServers[name].args, ["bridge/acp-runtime/launcher.mjs", name]);
  }
});

test("every Claude Code route carries the policy env and mirrors portable .mcp.json env keys", async () => {
  const claude = await readJson(".claude-plugin/plugin.json");
  const codex = await readJson(".mcp.json");
  for (const [name, server] of acpRoutes(claude.mcpServers)) {
    const env = server.env ?? {};
    assert.equal(
      env[PERMISSION_MODE_ENV],
      POLICY_PASSTHROUGH,
      `${name}: ${PERMISSION_MODE_ENV} must pass the host value through and default to ${LIVE_PERMISSION_MODE}`,
    );
    for (const [key, value] of Object.entries(env)) {
      assert.match(value, EXPANSION, `${name}: plugin.json env ${key} must be a \${VAR} or \${VAR:-default} expansion`);
      assert.doesNotMatch(value, /approve-all/, `${name}: ${BREAK_GLASS_PERMISSION_MODE} is break-glass, never a shipped default`);
    }
    // .mcp.json is the Codex install and may pin machine-local absolute paths
    // (the bridges resolve those defaults themselves). Every portable key it
    // declares must also reach the Claude Code launcher.
    const codexEnv = codex.mcpServers[name].env ?? {};
    const portable = Object.keys(codexEnv).filter((key) => !isMachineLocal(codexEnv[key])).sort();
    const expected = [...new Set([...portable, PERMISSION_MODE_ENV])].sort();
    assert.deepEqual(Object.keys(env).sort(), expected, `${name}: env keys drifted between plugin.json and .mcp.json`);
  }
});

test("jev-decision launches its own server in every manifest with no policy env", async () => {
  const claude = await readJson(".claude-plugin/plugin.json");
  const codex = await readJson(".mcp.json");
  const cursor = await readJson(".cursor-plugin/mcp.json");
  const routes = [
    [claude.mcpServers["jev-decision"], "${CLAUDE_PLUGIN_ROOT}/bridge/jev-decision/server.mjs"],
    [codex.mcpServers["jev-decision"], "bridge/jev-decision/server.mjs"],
    [cursor.mcpServers["jev-decision"], "${CURSOR_PLUGIN_ROOT}/bridge/jev-decision/server.mjs"],
  ];
  for (const [server, script] of routes) {
    assert.equal(server.command, "node");
    assert.deepEqual(server.args, [script]);
    assert.equal(server.env, undefined);
  }
});

test("plugin.json never ships machine-specific paths or a break-glass default", async () => {
  const text = await readFile(path.join(repoRoot, ".claude-plugin/plugin.json"), "utf8");
  assert.doesNotMatch(text, /\/Users\//);
  assert.doesNotMatch(text, /"approve-all"/);
});

test("no shipped manifest carries the break-glass; only the Claude Code manifest names the policy variable", async () => {
  // Issue #92 follow-up: the break-glass belongs in the host environment.
  // Codex reads .mcp.json, Cursor reads .cursor-plugin/mcp.json, and the
  // installed Claude Code plugin reads only .claude-plugin/plugin.json, whose
  // env is a ${VAR:-approve-reads} passthrough. GEMINI_HOME is a bridge
  // default, so .mcp.json must not carry a dead env block for it.
  for (const relative of [".mcp.json", ".cursor-plugin/mcp.json", ".claude-plugin/plugin.json"]) {
    const text = await readFile(path.join(repoRoot, relative), "utf8");
    assert.doesNotMatch(text, /approve-all/, `${relative} must never ship ${BREAK_GLASS_PERMISSION_MODE}`);
  }
  for (const relative of [".mcp.json", ".cursor-plugin/mcp.json"]) {
    const text = await readFile(path.join(repoRoot, relative), "utf8");
    assert.doesNotMatch(text, new RegExp(PERMISSION_MODE_ENV), `${relative} leaves the mode to the bridge default`);
  }
  const codex = await readJson(".mcp.json");
  assert.equal(
    codex.mcpServers["antigravity-acp"].env,
    undefined,
    ".mcp.json antigravity-acp env is dead config: GEMINI_HOME is the bridge default",
  );
});
