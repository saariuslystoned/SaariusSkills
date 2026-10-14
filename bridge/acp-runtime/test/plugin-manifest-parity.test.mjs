import assert from "node:assert/strict";
import { access, readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");

// Every ACP bridge server receives SAARIUS_ACP_PERMISSION_MODE via the Claude
// manifest so the operator can set the break-glass env var on the parent
// process without editing plugin.json. The default is always approve-reads.
const ACP_SERVERS = new Set(["cursor-acp", "antigravity-acp", "grok-acp", "muse-acp"]);
const PERMISSION_MODE_ENV = "SAARIUS_ACP_PERMISSION_MODE";
const PERMISSION_MODE_DEFAULT = "${SAARIUS_ACP_PERMISSION_MODE:-approve-reads}";
const TIMEOUT_ENV = "SAARIUS_ACP_TIMEOUT_MS";
const TIMEOUT_DEFAULT = "${SAARIUS_ACP_TIMEOUT_MS:-3600000}";

async function readJson(relativePath) {
  return JSON.parse(await readFile(path.join(repoRoot, relativePath), "utf8"));
}

function normalizeClaudeArg(arg) {
  return arg.replace(/^\$\{CLAUDE_PLUGIN_ROOT\}\//, "");
}

// Values pointing into a local user home (e.g. /Users/<name>/... or /home/<name>/...)
// are machine-specific and belong only in the local-checkout .mcp.json, never in the
// distributed Claude plugin manifest.
function isMachineLocal(value) {
  return typeof value === "string" && /^\/(?:Users|home)\//.test(value);
}

test("Claude plugin manifest mcpServers stay in lockstep with Codex .mcp.json", async () => {
  const claude = await readJson(".claude-plugin/plugin.json");
  const codex = await readJson(".mcp.json");

  assert.ok(claude.mcpServers && typeof claude.mcpServers === "object", ".claude-plugin/plugin.json must declare mcpServers");
  assert.ok(codex.mcpServers && typeof codex.mcpServers === "object", ".mcp.json must declare mcpServers");

  const claudeNames = Object.keys(claude.mcpServers).sort();
  const codexNames = Object.keys(codex.mcpServers).sort();
  assert.deepEqual(claudeNames, codexNames, "mcpServers key set must match between .claude-plugin/plugin.json and .mcp.json");

  for (const name of codexNames) {
    const claudeEntry = claude.mcpServers[name];
    const codexEntry = codex.mcpServers[name];

    assert.equal(claudeEntry.command, codexEntry.command, `${name}: command mismatch`);
    assert.ok(Array.isArray(claudeEntry.args) && claudeEntry.args.length > 0, `${name}: claude args must be non-empty array`);
    for (const arg of claudeEntry.args) {
      assert.ok(!arg.startsWith("./") && !arg.startsWith("../"), `${name}: claude arg "${arg}" must not use a CWD-relative path`);
    }
    assert.ok(
      claudeEntry.args[0].startsWith("${CLAUDE_PLUGIN_ROOT}/"),
      `${name}: first arg "${claudeEntry.args[0]}" must be anchored with \${CLAUDE_PLUGIN_ROOT}/`,
    );
    assert.deepEqual(
      claudeEntry.args.map(normalizeClaudeArg),
      codexEntry.args,
      `${name}: args must match .mcp.json once \${CLAUDE_PLUGIN_ROOT}/ is stripped`,
    );

    const env = claudeEntry.env ?? {};
    for (const [key, value] of Object.entries(env)) {
      assert.ok(!isMachineLocal(value), `${name}: claude env ${key}="${value}" must not hardcode a machine-local home path`);
    }
    const codexEnv = codexEntry.env ?? {};
    const portable = Object.keys(codexEnv).filter((key) => !isMachineLocal(codexEnv[key])).sort();
    if (ACP_SERVERS.has(name)) {
      assert.equal(
        env[PERMISSION_MODE_ENV],
        PERMISSION_MODE_DEFAULT,
        `${name}: must forward ${PERMISSION_MODE_ENV} with approve-reads default`,
      );
      assert.equal(
        env[TIMEOUT_ENV],
        TIMEOUT_DEFAULT,
        `${name}: claude manifest must forward ${TIMEOUT_ENV} with 3600000 default`,
      );
      assert.equal(
        codexEnv[TIMEOUT_ENV],
        TIMEOUT_DEFAULT,
        `${name}: .mcp.json must forward ${TIMEOUT_ENV} with 3600000 default`,
      );
      const expected = [...new Set([...portable, PERMISSION_MODE_ENV])].sort();
      assert.deepEqual(
        Object.keys(env).sort(),
        expected,
        `${name}: claude env keys must equal portable .mcp.json keys plus ${PERMISSION_MODE_ENV}`,
      );
    } else {
      assert.equal(
        env[PERMISSION_MODE_ENV],
        undefined,
        `${name}: non-ACP server must not receive ${PERMISSION_MODE_ENV}`,
      );
      assert.equal(
        env[TIMEOUT_ENV],
        undefined,
        `${name}: non-ACP server must not receive ${TIMEOUT_ENV}`,
      );
      assert.equal(
        codexEnv[TIMEOUT_ENV],
        undefined,
        `${name}: non-ACP server in .mcp.json must not receive ${TIMEOUT_ENV}`,
      );
      assert.deepEqual(
        Object.keys(env).sort(),
        portable,
        `${name}: claude env keys must equal portable .mcp.json keys`,
      );
    }
  }
});

test("every script referenced by .claude-plugin/plugin.json exists on disk", async () => {
  const claude = await readJson(".claude-plugin/plugin.json");
  for (const [name, entry] of Object.entries(claude.mcpServers)) {
    for (const arg of entry.args) {
      if (!arg.startsWith("${CLAUDE_PLUGIN_ROOT}/")) continue;
      const resolved = path.join(repoRoot, normalizeClaudeArg(arg));
      await access(resolved);
    }
    assert.ok(name.length > 0);
  }
});

test("Cursor and Codex manifests do not carry dead GEMINI_HOME env overrides", async () => {
  // GEMINI_HOME is resolved inside bridge/antigravity-acp/contract.mjs to the
  // same default path when unset. And Cursor's .cursor-plugin/mcp.json does not
  // expand ${HOME}, so setting "${HOME}/..." there spawns the child with a
  // literal "${HOME}" directory name. Keep both manifests free of GEMINI_HOME.
  const codex = await readJson(".mcp.json");
  const cursor = await readJson(".cursor-plugin/mcp.json");

  assert.equal(
    codex.mcpServers["antigravity-acp"].env?.GEMINI_HOME,
    undefined,
    ".mcp.json antigravity-acp env must not set dead GEMINI_HOME config",
  );
  assert.equal(
    cursor.mcpServers["antigravity-acp"].env,
    undefined,
    ".cursor-plugin/mcp.json must not pass unexpanded ${HOME} to antigravity-acp",
  );
});
