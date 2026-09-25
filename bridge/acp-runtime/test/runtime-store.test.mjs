import assert from "node:assert/strict";
import { access, chmod, cp, mkdir, readFile, readdir, rm, writeFile } from "node:fs/promises";
import { mkdtemp } from "node:fs/promises";
import { createRequire } from "node:module";
import { spawnSync } from "node:child_process";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { findReady, prepareRuntime } from "../runtime-store.mjs";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const bridges = ["cursor-acp", "antigravity-acp", "grok-acp"];
const expectedTools = {
  "cursor-acp": ["cancel", "delegate", "readiness", "result", "status", "steer"].map((name) => `cursor_acp_${name}`),
  "antigravity-acp": ["cancel", "delegate", "readiness", "result", "status", "steer"].map((name) => `antigravity_acp_${name}`),
  "grok-acp": ["cancel", "delegate", "readiness", "result", "status", "steer"].map((name) => `grok_acp_${name}`),
};

async function makePluginSnapshot(bridge, { includeLauncher = false } = {}) {
  const pluginRoot = await mkdtemp(path.join(tmpdir(), `saarius-${bridge}-snapshot-`));
  const sourceRoot = path.join(repoRoot, "bridge", bridge);
  const targetRoot = path.join(pluginRoot, "bridge", bridge);
  await mkdir(targetRoot, { recursive: true });
  for (const relativePath of ["package.json", "package-lock.json", "server.mjs", ...(bridge === "grok-acp" ? ["server-errors.mjs"] : []), "broker.mjs", "host-policy.mjs", ...(bridge === "antigravity-acp" ? ["contract.mjs"] : [])]) {
    await cp(path.join(sourceRoot, relativePath), path.join(targetRoot, relativePath));
  }
  if (includeLauncher) {
    await mkdir(path.join(targetRoot, "scripts"), { recursive: true });
    await cp(path.join(sourceRoot, "scripts", "setup.mjs"), path.join(targetRoot, "scripts", "setup.mjs"));
    const runtimeTarget = path.join(pluginRoot, "bridge", "acp-runtime");
    await mkdir(runtimeTarget, { recursive: true });
    for (const relativePath of ["runtime-store.mjs", "launcher.mjs", "hop.mjs", "prepare.mjs"]) {
      await cp(path.join(repoRoot, "bridge", "acp-runtime", relativePath), path.join(runtimeTarget, relativePath));
    }
    await cp(path.join(repoRoot, ".mcp.json"), path.join(pluginRoot, ".mcp.json"));
    await mkdir(path.join(pluginRoot, ".cursor-plugin"), { recursive: true });
    await cp(path.join(repoRoot, ".cursor-plugin", "mcp.json"), path.join(pluginRoot, ".cursor-plugin", "mcp.json"));
  }
  return pluginRoot;
}

async function makeFakeNpm({ mode = "copy", delayMs = 0, signalDelayMs = 0 } = {}) {
  const fixtureRoot = await mkdtemp(path.join(tmpdir(), "saarius-acp-fake-npm-"));
  const command = path.join(fixtureRoot, "npm");
  await writeFile(command, `#!/usr/bin/env node
import { appendFile, cp, writeFile } from "node:fs/promises";
import path from "node:path";

const delayMs = Number(process.env.SAARIUS_TEST_NPM_DELAY_MS || ${delayMs});
const signalDelayMs = Number(process.env.SAARIUS_TEST_NPM_SIGNAL_DELAY_MS || ${signalDelayMs});
if (signalDelayMs > 0) process.once("SIGTERM", () => {
  setTimeout(async () => {
    if (process.env.SAARIUS_TEST_NPM_EXIT_MARKER) await writeFile(process.env.SAARIUS_TEST_NPM_EXIT_MARKER, "exited\\n");
    process.exit(0);
  }, signalDelayMs);
});
if (delayMs > 0) await new Promise((resolve) => setTimeout(resolve, delayMs));
if (process.env.SAARIUS_TEST_NPM_COUNTER) await appendFile(process.env.SAARIUS_TEST_NPM_COUNTER, "1\\n");
if (${JSON.stringify(mode)} === "fail") {
  process.stderr.write("authorization=Bearer sk-test-token secret=do-not-leak\\n");
  process.exit(7);
}
await cp(process.env.SAARIUS_TEST_NODE_MODULES, path.join(process.cwd(), "node_modules"), { recursive: true });
`);
  await chmod(command, 0o755);
  return { command, fixtureRoot };
}

async function waitForFile(filePath, timeoutMs = 3_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      await access(filePath);
      return;
    } catch {
      await new Promise((resolve) => setTimeout(resolve, 10));
    }
  }
  throw new Error(`timed out waiting for ${filePath}`);
}

async function countLines(filePath) {
  try {
    return (await readFile(filePath, "utf8")).trim().split("\n").filter(Boolean).length;
  } catch {
    return 0;
  }
}

function npmEnv(bridge, counterPath) {
  return {
    SAARIUS_TEST_NODE_MODULES: path.join(repoRoot, "bridge", bridge, "node_modules"),
    SAARIUS_TEST_NPM_COUNTER: counterPath,
  };
}

async function prepareSnapshot({ bridge, pluginRoot, runtimeRoot, command, counterPath }) {
  return prepareRuntime({
    pluginRoot,
    bridge,
    env: { SAARIUS_ACP_RUNTIME_ROOT: runtimeRoot },
    npmCommand: command,
    npmEnv: npmEnv(bridge, counterPath),
  });
}

test("clean plugin snapshots prepare each bridge and reuse without reinstalling", async () => {
  const fixtureRoot = await mkdtemp(path.join(tmpdir(), "saarius-acp-clean-snapshot-"));
  const counterPath = path.join(fixtureRoot, "npm.count");
  const fake = await makeFakeNpm();
  try {
    for (const bridge of bridges) {
      const pluginRoot = await makePluginSnapshot(bridge);
      const runtimeRoot = path.join(fixtureRoot, bridge);
      await assert.rejects(() => readFile(path.join(pluginRoot, "bridge", bridge, "node_modules")), { code: "ENOENT" });
      const first = await prepareSnapshot({ bridge, pluginRoot, runtimeRoot, command: fake.command, counterPath });
      const second = await prepareSnapshot({ bridge, pluginRoot, runtimeRoot, command: fake.command, counterPath });
      assert.equal(first.reused, false);
      assert.equal(second.reused, true);
      await rm(pluginRoot, { recursive: true, force: true });
    }
    assert.equal(await countLines(counterPath), bridges.length);
  } finally {
    await rm(fixtureRoot, { recursive: true, force: true });
    await rm(fake.fixtureRoot, { recursive: true, force: true });
  }
});

test("concurrent preparation converges on one atomic runtime", async () => {
  const fixtureRoot = await mkdtemp(path.join(tmpdir(), "saarius-acp-concurrent-"));
  const counterPath = path.join(fixtureRoot, "npm.count");
  const fake = await makeFakeNpm({ delayMs: 50 });
  const pluginRoot = await makePluginSnapshot("cursor-acp");
  try {
    const results = await Promise.all([
      prepareSnapshot({ bridge: "cursor-acp", pluginRoot, runtimeRoot: fixtureRoot, command: fake.command, counterPath }),
      prepareSnapshot({ bridge: "cursor-acp", pluginRoot, runtimeRoot: fixtureRoot, command: fake.command, counterPath }),
    ]);
    assert.deepEqual(results.map((result) => result.root), [results[0].root, results[0].root]);
    assert.deepEqual(results.map((result) => result.reused).sort(), [false, true]);
    assert.equal(await countLines(counterPath), 2);
    assert.deepEqual(await readdir(path.join(fixtureRoot, ".staging")), []);
  } finally {
    await rm(pluginRoot, { recursive: true, force: true });
    await rm(fixtureRoot, { recursive: true, force: true });
    await rm(fake.fixtureRoot, { recursive: true, force: true });
  }
});

test("source identity drift creates a new runtime and failed installs redact diagnostics", async () => {
  const fixtureRoot = await mkdtemp(path.join(tmpdir(), "saarius-acp-integrity-"));
  const counterPath = path.join(fixtureRoot, "npm.count");
  const fake = await makeFakeNpm();
  const pluginRoot = await makePluginSnapshot("cursor-acp");
  try {
    const first = await prepareSnapshot({ bridge: "cursor-acp", pluginRoot, runtimeRoot: fixtureRoot, command: fake.command, counterPath });
    await writeFile(path.join(pluginRoot, "bridge", "cursor-acp", "broker.mjs"), "\n// identity drift fixture\n", { flag: "a" });
    const second = await prepareSnapshot({ bridge: "cursor-acp", pluginRoot, runtimeRoot: fixtureRoot, command: fake.command, counterPath });
    assert.notEqual(first.root, second.root);
    assert.equal(await countLines(counterPath), 2);

    const failing = await makeFakeNpm({ mode: "fail" });
    await assert.rejects(
      () => prepareRuntime({
        pluginRoot,
        bridge: "cursor-acp",
        env: { SAARIUS_ACP_RUNTIME_ROOT: path.join(fixtureRoot, "failed") },
        npmCommand: failing.command,
        npmEnv: npmEnv("cursor-acp", path.join(fixtureRoot, "failed.count")),
      }),
      (error) => {
        assert.equal(error.code, "DEPENDENCY_INSTALL_FAILED");
        assert.match(error.details.stderr, /redacted/);
        assert.doesNotMatch(error.details.stderr, /sk-test-token|do-not-leak/);
        return true;
      },
    );
    await rm(failing.fixtureRoot, { recursive: true, force: true });
  } finally {
    await rm(pluginRoot, { recursive: true, force: true });
    await rm(fixtureRoot, { recursive: true, force: true });
    await rm(fake.fixtureRoot, { recursive: true, force: true });
  }
});

test("dependency payload drift invalidates a prepared runtime even when package versions remain pinned", async () => {
  const fixtureRoot = await mkdtemp(path.join(tmpdir(), "saarius-acp-dependency-drift-"));
  const counterPath = path.join(fixtureRoot, "npm.count");
  const fake = await makeFakeNpm();
  const pluginRoot = await makePluginSnapshot("cursor-acp");
  try {
    const prepared = await prepareSnapshot({ bridge: "cursor-acp", pluginRoot, runtimeRoot: fixtureRoot, command: fake.command, counterPath });
    const runtimeFile = path.join(prepared.root, "bridge", "cursor-acp", "node_modules", "acpx", "dist", "runtime.js");
    await writeFile(runtimeFile, "\n// dependency payload drift fixture\n", { flag: "a" });
    assert.equal(await findReady({ pluginRoot, bridge: "cursor-acp", env: { SAARIUS_ACP_RUNTIME_ROOT: fixtureRoot } }), null);
  } finally {
    await rm(pluginRoot, { recursive: true, force: true });
    await rm(fixtureRoot, { recursive: true, force: true });
    await rm(fake.fixtureRoot, { recursive: true, force: true });
  }
});

test("dependency timeout waits for owned SIGTERM exit before staging cleanup", async () => {
  const fixtureRoot = await mkdtemp(path.join(tmpdir(), "saarius-acp-timeout-"));
  const counterPath = path.join(fixtureRoot, "npm.count");
  const exitMarker = path.join(fixtureRoot, "npm-exited");
  const fake = await makeFakeNpm({ signalDelayMs: 150 });
  const pluginRoot = await makePluginSnapshot("cursor-acp");
  const startedAt = Date.now();
  try {
    await assert.rejects(
      () => prepareRuntime({
        pluginRoot,
        bridge: "cursor-acp",
        env: { SAARIUS_ACP_RUNTIME_ROOT: fixtureRoot },
        npmCommand: fake.command,
        npmEnv: { ...npmEnv("cursor-acp", counterPath), SAARIUS_TEST_NPM_EXIT_MARKER: exitMarker },
        timeoutMs: 1_000,
        npmTerminationTimeoutMs: 500,
      }),
      (error) => error.code === "DEPENDENCY_INSTALL_TIMEOUT",
    );
    assert.ok(Date.now() - startedAt >= 1_100, "preparation returned before the owned installer exited");
    await waitForFile(exitMarker);
    assert.deepEqual(await readdir(path.join(fixtureRoot, ".staging")), []);
  } finally {
    await waitForFile(exitMarker);
    await rm(pluginRoot, { recursive: true, force: true });
    await rm(fixtureRoot, { recursive: true, force: true });
    await rm(fake.fixtureRoot, { recursive: true, force: true });
  }
});

test("unconfirmed dependency termination preserves the staging fence until the writer exits", async () => {
  const fixtureRoot = await mkdtemp(path.join(tmpdir(), "saarius-acp-timeout-uncertain-"));
  const counterPath = path.join(fixtureRoot, "npm.count");
  const exitMarker = path.join(fixtureRoot, "npm-exited");
  const fake = await makeFakeNpm({ signalDelayMs: 1_000 });
  const pluginRoot = await makePluginSnapshot("cursor-acp");
  let stagingRoot;
  try {
    await assert.rejects(
      () => prepareRuntime({
        pluginRoot,
        bridge: "cursor-acp",
        env: { SAARIUS_ACP_RUNTIME_ROOT: fixtureRoot },
        npmCommand: fake.command,
        npmEnv: { ...npmEnv("cursor-acp", counterPath), SAARIUS_TEST_NPM_EXIT_MARKER: exitMarker },
        timeoutMs: 1_000,
        npmTerminationTimeoutMs: 50,
      }),
      (error) => {
        assert.equal(error.code, "DEPENDENCY_INSTALL_TERMINATION_UNCERTAIN");
        stagingRoot = error.details.stagingRoot;
        assert.equal(error.details.cleanupSafe, false);
        return true;
      },
    );
    await access(stagingRoot);
    await waitForFile(exitMarker);
    await rm(stagingRoot, { recursive: true, force: true });
  } finally {
    await waitForFile(exitMarker);
    await rm(pluginRoot, { recursive: true, force: true });
    await rm(fixtureRoot, { recursive: true, force: true });
    await rm(fake.fixtureRoot, { recursive: true, force: true });
  }
});

test("separate dependency-free plugin snapshots launch each manifest path from an external cwd", async () => {
  const fixtureRoot = await mkdtemp(path.join(tmpdir(), "saarius-acp-mcp-"));
  const externalCwd = await mkdtemp(path.join(tmpdir(), "saarius-acp-external-cwd-"));
  const counterPath = path.join(fixtureRoot, "npm.count");
  const fake = await makeFakeNpm();
  const requireFromBridge = createRequire(path.join(repoRoot, "bridge/cursor-acp/package.json"));
  const { Client } = requireFromBridge("@modelcontextprotocol/sdk/client/index.js");
  const { StdioClientTransport } = requireFromBridge("@modelcontextprotocol/sdk/client/stdio.js");
  try {
    const launchCases = [
      { bridge: "cursor-acp", manifest: ".mcp.json", server: "cursor-acp", stateEnv: "SAARIUS_CURSOR_ACP_STATE_DIR" },
      { bridge: "antigravity-acp", manifest: ".cursor-plugin/mcp.json", server: "antigravity-acp", stateEnv: "SAARIUS_ANTIGRAVITY_ACP_STATE_DIR" },
      { bridge: "grok-acp", manifest: ".cursor-plugin/mcp.json", server: "grok-acp", stateEnv: "SAARIUS_GROK_ACP_STATE_DIR" },
    ];
    for (const { bridge, manifest, server, stateEnv } of launchCases) {
      const pluginRoot = await makePluginSnapshot(bridge, { includeLauncher: true });
      try {
        const setup = spawnSync(process.execPath, [path.join(pluginRoot, "bridge", bridge, "scripts", "setup.mjs"), "--install"], {
          cwd: externalCwd,
          encoding: "utf8",
          timeout: 30_000,
          env: {
            ...process.env,
            ...npmEnv(bridge, counterPath),
            PATH: `${fake.fixtureRoot}:${process.env.PATH ?? ""}`,
            SAARIUS_ACP_RUNTIME_ROOT: fixtureRoot,
          },
        });
        assert.equal(setup.status, 0, setup.stderr || setup.stdout);
        assert.equal(JSON.parse(setup.stdout).code, "MCP_READY");
        await assert.rejects(() => readFile(path.join(pluginRoot, "bridge", bridge, "node_modules")), { code: "ENOENT" });
        const manifestRoot = JSON.parse(await readFile(path.join(pluginRoot, manifest), "utf8"));
        const config = manifestRoot.mcpServers[server];
        const launcherPath = path.join(pluginRoot, "bridge", "acp-runtime", "launcher.mjs");
        const stateRoot = await mkdtemp(path.join(tmpdir(), `${bridge}-mcp-state-`));
        const transport = new StdioClientTransport({
          command: config.command,
          args: [launcherPath, ...config.args.slice(1)],
          cwd: externalCwd,
          env: {
            PATH: process.env.PATH ?? "",
            HOME: process.env.HOME ?? "",
            ...config.env,
            [stateEnv]: stateRoot,
            SAARIUS_ACP_RUNTIME_ROOT: fixtureRoot,
          },
          stderr: "pipe",
        });
        transport.stderr?.resume();
        const client = new Client({ name: "acp-runtime-store-test", version: "1.0.0" });
        try {
          await client.connect(transport);
          assert.deepEqual((await client.listTools()).tools.map((tool) => tool.name).sort(), expectedTools[bridge]);
        } finally {
          await client.close();
        }
      } finally {
        await rm(pluginRoot, { recursive: true, force: true });
      }
    }
    assert.equal(await countLines(counterPath), launchCases.length);
  } finally {
    await rm(fixtureRoot, { recursive: true, force: true });
    await rm(externalCwd, { recursive: true, force: true });
    await rm(fake.fixtureRoot, { recursive: true, force: true });
  }
});

test("parent hop argv lists the same six tools through a worker launcher", async () => {
  const fixtureRoot = await mkdtemp(path.join(tmpdir(), "saarius-acp-hop-mcp-"));
  const externalCwd = await mkdtemp(path.join(tmpdir(), "saarius-acp-hop-cwd-"));
  const counterPath = path.join(fixtureRoot, "npm.count");
  const fake = await makeFakeNpm();
  const requireFromBridge = createRequire(path.join(repoRoot, "bridge/cursor-acp/package.json"));
  const { Client } = requireFromBridge("@modelcontextprotocol/sdk/client/index.js");
  const { StdioClientTransport } = requireFromBridge("@modelcontextprotocol/sdk/client/stdio.js");
  const pluginRoot = await makePluginSnapshot("antigravity-acp", { includeLauncher: true });
  try {
    const setup = spawnSync(process.execPath, [path.join(pluginRoot, "bridge", "antigravity-acp", "scripts", "setup.mjs"), "--install"], {
      cwd: externalCwd,
      encoding: "utf8",
      timeout: 30_000,
      env: {
        ...process.env,
        ...npmEnv("antigravity-acp", counterPath),
        PATH: `${fake.fixtureRoot}:${process.env.PATH ?? ""}`,
        SAARIUS_ACP_RUNTIME_ROOT: fixtureRoot,
      },
    });
    assert.equal(setup.status, 0, setup.stderr || setup.stdout);
    const launcherPath = path.join(pluginRoot, "bridge", "acp-runtime", "launcher.mjs");
    const stateRoot = await mkdtemp(path.join(tmpdir(), "antigravity-acp-hop-state-"));
    const transport = new StdioClientTransport({
      command: process.execPath,
      args: [launcherPath, "antigravity-acp"],
      cwd: externalCwd,
      env: {
        PATH: process.env.PATH ?? "",
        HOME: process.env.HOME ?? "",
        SAARIUS_ANTIGRAVITY_ACP_STATE_DIR: stateRoot,
        SAARIUS_ACP_RUNTIME_ROOT: fixtureRoot,
        SAARIUS_ACP_HOP_ARGV: JSON.stringify([process.execPath, launcherPath, "antigravity-acp"]),
      },
      stderr: "pipe",
    });
    transport.stderr?.resume();
    const client = new Client({ name: "acp-hop-test", version: "1.0.0" });
    try {
      await client.connect(transport);
      assert.deepEqual(
        (await client.listTools()).tools.map((tool) => tool.name).sort(),
        expectedTools["antigravity-acp"],
      );
    } finally {
      await client.close();
    }
  } finally {
    await rm(pluginRoot, { recursive: true, force: true });
    await rm(fixtureRoot, { recursive: true, force: true });
    await rm(externalCwd, { recursive: true, force: true });
    await rm(fake.fixtureRoot, { recursive: true, force: true });
  }
});
