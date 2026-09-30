import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { access, chmod, cp, lstat, mkdir, readFile, readdir, realpath, rename, rm, symlink, writeFile } from "node:fs/promises";
import { mkdtemp } from "node:fs/promises";
import { createRequire } from "node:module";
import { spawnSync } from "node:child_process";
import { homedir, tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { findReady, inspectRuntime, prepareRuntime } from "../runtime-store.mjs";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const bridges = ["cursor-acp", "antigravity-acp", "grok-acp"];
const expectedTools = {
  "cursor-acp": ["cancel", "delegate", "readiness", "result", "status", "steer"].map((name) => `cursor_acp_${name}`),
  "antigravity-acp": ["cancel", "delegate", "readiness", "result", "status", "steer"].map((name) => `antigravity_acp_${name}`),
  "grok-acp": ["cancel", "delegate", "readiness", "result", "status", "steer"].map((name) => `grok_acp_${name}`),
};
const defaultRuntimeRoot = path.join(homedir(), ".local", "state", "saarius-skills", "acp-runtime");

// Every runtime these tests prepare must live in a fresh temp directory, never
// the operator's store (the default root, or wherever it is linked from).
async function isolatedRuntimeEnv(runtimeRoot) {
  // Resolve through the nearest existing ancestor so a link cannot hide the target.
  const requested = path.resolve(runtimeRoot);
  let existing = requested;
  for (;;) {
    try {
      await access(existing);
      break;
    } catch {
      existing = path.dirname(existing);
    }
  }
  const resolved = path.join(await realpath(existing), path.relative(existing, requested));
  assert.ok(resolved.startsWith(`${await realpath(tmpdir())}${path.sep}`), `runtime root must be a temp fixture: ${runtimeRoot}`);
  assert.ok(!resolved.startsWith(defaultRuntimeRoot), `runtime root must not be the default store: ${runtimeRoot}`);
  return { SAARIUS_ACP_RUNTIME_ROOT: runtimeRoot };
}

// Fixture mutations resolve through here: the real target must stay inside the
// fixture, so a linked node_modules can never carry a write into a real store.
async function fixturePath(fixtureRoot, filePath) {
  const target = await realpath(filePath);
  assert.ok(target.startsWith(`${await realpath(fixtureRoot)}${path.sep}`), `fixture write escapes ${fixtureRoot}: ${target}`);
  return target;
}

async function appendInsideFixture(fixtureRoot, filePath, text) {
  await writeFile(await fixturePath(fixtureRoot, filePath), text, { flag: "a" });
}

async function makePluginSnapshot(bridge, { includeLauncher = false } = {}) {
  const pluginRoot = await mkdtemp(path.join(tmpdir(), `saarius-${bridge}-snapshot-`));
  const sourceRoot = path.join(repoRoot, "bridge", bridge);
  const targetRoot = path.join(pluginRoot, "bridge", bridge);
  await mkdir(targetRoot, { recursive: true });
  for (const relativePath of ["package.json", "package-lock.json", "server.mjs", ...(bridge === "grok-acp" ? ["server-errors.mjs"] : []), "broker.mjs", "host-policy.mjs", ...(bridge === "antigravity-acp" ? ["contract.mjs"] : [])]) {
    await cp(path.join(sourceRoot, relativePath), path.join(targetRoot, relativePath));
  }
  const sharedRoot = path.join(pluginRoot, "bridge", "acp-runtime");
  await mkdir(sharedRoot, { recursive: true });
  for (const file of ["lifecycle.mjs", "recovery.mjs"]) {
    await cp(path.join(repoRoot, "bridge", "acp-runtime", file), path.join(sharedRoot, file));
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
import { appendFile, cp, symlink, writeFile } from "node:fs/promises";
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
if (${JSON.stringify(mode)} === "link") {
  await symlink(process.env.SAARIUS_TEST_NODE_MODULES, path.join(process.cwd(), "node_modules"));
} else {
  // Dereference: a checkout whose node_modules links into a prepared store must
  // still yield a private copy, or fixture writes land in that store.
  await cp(process.env.SAARIUS_TEST_NODE_MODULES, path.join(process.cwd(), "node_modules"), { recursive: true, dereference: true });
}
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

function npmEnv(bridge, counterPath, nodeModules = path.join(repoRoot, "bridge", bridge, "node_modules")) {
  return {
    SAARIUS_TEST_NODE_MODULES: nodeModules,
    SAARIUS_TEST_NPM_COUNTER: counterPath,
  };
}

async function prepareSnapshot({ bridge, pluginRoot, runtimeRoot, command, counterPath, nodeModules, replaceInvalid, recoveryLockTimeoutMs }) {
  return prepareRuntime({
    pluginRoot,
    bridge,
    env: await isolatedRuntimeEnv(runtimeRoot),
    npmCommand: command,
    npmEnv: npmEnv(bridge, counterPath, nodeModules),
    replaceInvalid,
    recoveryLockTimeoutMs,
  });
}

// Minimal dependency tree with the pinned versions and the imports the store
// requires; integrity tests need its shape, not the real packages.
async function makeSyntheticNodeModules(bridge) {
  const nodeModules = await mkdtemp(path.join(tmpdir(), `saarius-${bridge}-synthetic-modules-`));
  const { dependencies } = JSON.parse(await readFile(path.join(repoRoot, "bridge", bridge, "package.json"), "utf8"));
  for (const [name, version] of Object.entries(dependencies)) {
    await mkdir(path.join(nodeModules, name), { recursive: true });
    await writeFile(path.join(nodeModules, name, "package.json"), `${JSON.stringify({ name, version })}\n`);
  }
  for (const relativePath of [
    "@modelcontextprotocol/sdk/dist/esm/server/mcp.js",
    "@modelcontextprotocol/sdk/dist/esm/server/stdio.js",
    "@modelcontextprotocol/sdk/dist/esm/client/index.js",
    "@modelcontextprotocol/sdk/dist/esm/client/stdio.js",
    "acpx/dist/runtime.js",
    "acpx/README.md",
    "zod/index.js",
  ]) {
    await mkdir(path.dirname(path.join(nodeModules, relativePath)), { recursive: true });
    await writeFile(path.join(nodeModules, relativePath), "export {};\n");
  }
  return nodeModules;
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
    await appendInsideFixture(pluginRoot, path.join(pluginRoot, "bridge", "cursor-acp", "broker.mjs"), "\n// identity drift fixture\n");
    const second = await prepareSnapshot({ bridge: "cursor-acp", pluginRoot, runtimeRoot: fixtureRoot, command: fake.command, counterPath });
    assert.notEqual(first.root, second.root);
    assert.equal(await countLines(counterPath), 2);

    const failing = await makeFakeNpm({ mode: "fail" });
    await assert.rejects(
      async () => prepareRuntime({
        pluginRoot,
        bridge: "cursor-acp",
        env: await isolatedRuntimeEnv(path.join(fixtureRoot, "failed")),
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
    await appendInsideFixture(fixtureRoot, runtimeFile, "\n// dependency payload drift fixture\n");
    assert.equal(await findReady({ pluginRoot, bridge: "cursor-acp", env: await isolatedRuntimeEnv(fixtureRoot) }), null);
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
      async () => prepareRuntime({
        pluginRoot,
        bridge: "cursor-acp",
        env: await isolatedRuntimeEnv(fixtureRoot),
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
      async () => prepareRuntime({
        pluginRoot,
        bridge: "cursor-acp",
        env: await isolatedRuntimeEnv(fixtureRoot),
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
            ...(await isolatedRuntimeEnv(fixtureRoot)),
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
            ...(await isolatedRuntimeEnv(fixtureRoot)),
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
        ...(await isolatedRuntimeEnv(fixtureRoot)),
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
        ...(await isolatedRuntimeEnv(fixtureRoot)),
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

// Planted in every mutation below; no diagnostic may echo it back.
const CONTENT_MARKER = "saarius-content-marker-7f3a";
const driftedRuntimeFile = "bridge/cursor-acp/node_modules/acpx/dist/runtime.js";

async function editJsonInsideFixture(fixtureRoot, filePath, change) {
  const target = await fixturePath(fixtureRoot, filePath);
  const value = JSON.parse(await readFile(target, "utf8"));
  change(value);
  await writeFile(target, JSON.stringify(value));
}

async function replaceTreeWithDanglingLink(fixtureRoot, root) {
  await rm(await fixturePath(fixtureRoot, root), { recursive: true, force: true });
  await symlink(path.join(fixtureRoot, "no-such-runtime"), root);
}

const integrityCases = [
  {
    name: "dangling runtime root link",
    mutate: ({ fixtureRoot, at }) => replaceTreeWithDanglingLink(fixtureRoot, at(".")),
    expected: { check: "runtime_root", path: ".", kind: "symlink" },
  },
  {
    name: "missing bridge source file",
    mutate: async ({ fixtureRoot, at }) => rm(await fixturePath(fixtureRoot, at("bridge/cursor-acp/broker.mjs"))),
    expected: { check: "source_file", path: "bridge/cursor-acp/broker.mjs", kind: "missing" },
  },
  {
    name: "linked dependency root",
    mutate: async ({ fixtureRoot, at }) => {
      const outside = path.join(fixtureRoot, "linked-node_modules");
      await rename(await fixturePath(fixtureRoot, at("bridge/cursor-acp/node_modules")), outside);
      await symlink(outside, at("bridge/cursor-acp/node_modules"));
    },
    expected: { check: "dependency_root", path: "bridge/cursor-acp/node_modules", kind: "symlink" },
  },
  {
    name: "missing required import",
    mutate: async ({ fixtureRoot, at }) => rm(await fixturePath(fixtureRoot, at("bridge/cursor-acp/node_modules/zod/index.js"))),
    expected: { check: "required_import", path: "bridge/cursor-acp/node_modules/zod/index.js", kind: "missing" },
  },
  {
    name: "bridge package version",
    mutate: ({ fixtureRoot, at }) => editJsonInsideFixture(fixtureRoot, at("bridge/cursor-acp/package.json"), (value) => { value.version = CONTENT_MARKER; }),
    expected: { check: "package_version", path: "bridge/cursor-acp/package.json", kind: "mismatch" },
  },
  {
    name: "pinned dependency version",
    mutate: ({ fixtureRoot, at }) => editJsonInsideFixture(fixtureRoot, at("bridge/cursor-acp/node_modules/acpx/package.json"), (value) => { value.version = CONTENT_MARKER; }),
    expected: { check: "dependency_version", path: "bridge/cursor-acp/node_modules/acpx/package.json", kind: "mismatch" },
  },
  {
    name: "bridge source bytes",
    mutate: ({ fixtureRoot, at }) => appendInsideFixture(fixtureRoot, at("bridge/cursor-acp/broker.mjs"), `\n// ${CONTENT_MARKER}\n`),
    expected: { check: "source_integrity", path: "bridge/cursor-acp/broker.mjs", kind: "changed" },
  },
  {
    name: "missing dependency record",
    mutate: async ({ fixtureRoot, at }) => rm(await fixturePath(fixtureRoot, at("DEPENDENCIES.json"))),
    expected: { check: "dependency_record", path: "DEPENDENCIES.json", kind: "unreadable" },
  },
  {
    name: "dependency record identity",
    mutate: ({ fixtureRoot, at }) => editJsonInsideFixture(fixtureRoot, at("DEPENDENCIES.json"), (value) => { value.identity = CONTENT_MARKER; }),
    expected: { check: "dependency_record", path: "DEPENDENCIES.json", kind: "identity" },
  },
  {
    name: "dependency record digest",
    mutate: ({ fixtureRoot, at }) => editJsonInsideFixture(fixtureRoot, at("DEPENDENCIES.json"), (value) => { value.files.pop(); }),
    expected: { check: "dependency_record", path: "DEPENDENCIES.json", kind: "digest" },
  },
  {
    name: "garbled dependency record entries",
    mutate: ({ fixtureRoot, at }) => editJsonInsideFixture(fixtureRoot, at("DEPENDENCIES.json"), (value) => {
      value.files = [null];
      value.digest = createHash("sha256").update(JSON.stringify(value.files)).digest("hex");
    }),
    expected: { check: "unexpected", path: ".", kind: "error" },
  },
  {
    name: "changed dependency payload",
    mutate: ({ fixtureRoot, at }) => appendInsideFixture(fixtureRoot, at(driftedRuntimeFile), `\n// ${CONTENT_MARKER}\n`),
    expected: { check: "dependency_inventory", path: driftedRuntimeFile, kind: "changed" },
  },
  {
    name: "added dependency file",
    mutate: async ({ fixtureRoot, at }) => writeFile(
      path.join(await fixturePath(fixtureRoot, at("bridge/cursor-acp/node_modules/acpx/dist")), "extra.js"),
      `// ${CONTENT_MARKER}\n`,
    ),
    expected: { check: "dependency_inventory", path: "bridge/cursor-acp/node_modules/acpx/dist/extra.js", kind: "added" },
  },
  {
    name: "removed dependency file",
    mutate: async ({ fixtureRoot, at }) => rm(await fixturePath(fixtureRoot, at("bridge/cursor-acp/node_modules/acpx/README.md"))),
    expected: { check: "dependency_inventory", path: "bridge/cursor-acp/node_modules/acpx/README.md", kind: "removed" },
  },
  {
    name: "missing ready record",
    mutate: async ({ fixtureRoot, at }) => rm(await fixturePath(fixtureRoot, at("READY.json"))),
    expected: { check: "ready_record", path: "READY.json", kind: "unreadable" },
  },
  {
    name: "ready record platform",
    mutate: ({ fixtureRoot, at }) => editJsonInsideFixture(fixtureRoot, at("READY.json"), (value) => { value.platform.nodeVersion = CONTENT_MARKER; }),
    expected: { check: "ready_record", path: "READY.json", kind: "platform" },
  },
];

test("each integrity check names its first failure with a tree-relative path and no contents", async (t) => {
  const fake = await makeFakeNpm();
  const nodeModules = await makeSyntheticNodeModules("cursor-acp");
  const pluginRoot = await makePluginSnapshot("cursor-acp");
  try {
    const emptyRoot = await mkdtemp(path.join(tmpdir(), "saarius-acp-integrity-missing-"));
    const missing = await inspectRuntime({ pluginRoot, bridge: "cursor-acp", env: await isolatedRuntimeEnv(emptyRoot) });
    assert.equal(missing.state, "missing");
    assert.equal(missing.failure, undefined);
    await rm(emptyRoot, { recursive: true, force: true });

    for (const { name, mutate, expected } of integrityCases) {
      await t.test(name, async () => {
        const fixtureRoot = await mkdtemp(path.join(tmpdir(), "saarius-acp-integrity-check-"));
        try {
          const prepared = await prepareSnapshot({ bridge: "cursor-acp", pluginRoot, runtimeRoot: fixtureRoot, command: fake.command, counterPath: path.join(fixtureRoot, "npm.count"), nodeModules });
          await mutate({ fixtureRoot, at: (relativePath) => path.join(prepared.root, ...relativePath.split("/")) });
          const inspection = await inspectRuntime({ pluginRoot, bridge: "cursor-acp", env: await isolatedRuntimeEnv(fixtureRoot) });
          assert.equal(inspection.state, "invalid");
          assert.equal(inspection.root, prepared.root);
          assert.deepEqual(inspection.failure, expected);
          assert.equal(await findReady({ pluginRoot, bridge: "cursor-acp", env: await isolatedRuntimeEnv(fixtureRoot) }), null);
        } finally {
          await rm(fixtureRoot, { recursive: true, force: true });
        }
      });
    }
  } finally {
    await rm(pluginRoot, { recursive: true, force: true });
    await rm(nodeModules, { recursive: true, force: true });
    await rm(fake.fixtureRoot, { recursive: true, force: true });
  }
});

test("a linked node_modules never becomes a runtime, so test writes cannot reach a real store", async () => {
  const fixtureRoot = await mkdtemp(path.join(tmpdir(), "saarius-acp-linked-modules-"));
  const fake = await makeFakeNpm({ mode: "link" });
  const nodeModules = await makeSyntheticNodeModules("cursor-acp");
  const pluginRoot = await makePluginSnapshot("cursor-acp");
  const linkedFile = path.join(nodeModules, "acpx", "dist", "runtime.js");
  try {
    const before = await readFile(linkedFile);
    await assert.rejects(
      () => prepareSnapshot({ bridge: "cursor-acp", pluginRoot, runtimeRoot: fixtureRoot, command: fake.command, counterPath: path.join(fixtureRoot, "npm.count"), nodeModules }),
      (error) => {
        assert.equal(error.code, "READY_INTEGRITY_MISMATCH");
        assert.deepEqual(error.details, { check: "dependency_root", path: "bridge/cursor-acp/node_modules", kind: "symlink" });
        return true;
      },
    );
    assert.equal((await inspectRuntime({ pluginRoot, bridge: "cursor-acp", env: await isolatedRuntimeEnv(fixtureRoot) })).state, "missing");
    assert.deepEqual(await readdir(path.join(fixtureRoot, ".staging")), []);

    const escape = path.join(fixtureRoot, "escape");
    await symlink(nodeModules, escape);
    await assert.rejects(() => appendInsideFixture(fixtureRoot, path.join(escape, "acpx", "dist", "runtime.js"), CONTENT_MARKER), /fixture write escapes/);
    await assert.rejects(() => isolatedRuntimeEnv(defaultRuntimeRoot), /runtime root must be a temp fixture/);
    assert.deepEqual(await readFile(linkedFile), before);
  } finally {
    await rm(pluginRoot, { recursive: true, force: true });
    await rm(fixtureRoot, { recursive: true, force: true });
    await rm(nodeModules, { recursive: true, force: true });
    await rm(fake.fixtureRoot, { recursive: true, force: true });
  }
});

test("an invalid same-identity runtime fails closed until --replace-invalid quarantines it", async () => {
  const fixtureRoot = await mkdtemp(path.join(tmpdir(), "saarius-acp-replace-invalid-"));
  const counterPath = path.join(fixtureRoot, "npm.count");
  const fake = await makeFakeNpm();
  const nodeModules = await makeSyntheticNodeModules("cursor-acp");
  const pluginRoot = await makePluginSnapshot("cursor-acp");
  const expected = { check: "dependency_inventory", path: driftedRuntimeFile, kind: "changed" };
  const prepare = (options = {}) => prepareSnapshot({ bridge: "cursor-acp", pluginRoot, runtimeRoot: fixtureRoot, command: fake.command, counterPath, nodeModules, ...options });
  try {
    const prepared = await prepare();
    const runtimeFile = path.join(prepared.root, ...driftedRuntimeFile.split("/"));
    await appendInsideFixture(fixtureRoot, runtimeFile, `\n// ${CONTENT_MARKER}\n`);
    const drifted = await readFile(runtimeFile);

    await assert.rejects(() => prepare(), (error) => {
      assert.equal(error.code, "RUNTIME_IDENTITY_CONFLICT");
      const { recovery, ...details } = error.details;
      assert.deepEqual(details, { root: prepared.root, ...expected });
      assert.match(recovery, /prepare\.mjs --bridge cursor-acp --replace-invalid$/);
      assert.doesNotMatch(JSON.stringify(error.details), new RegExp(CONTENT_MARKER));
      return true;
    });
    assert.deepEqual(await readFile(runtimeFile), drifted, "fail-closed prepare must leave the invalid tree untouched");

    const replaced = await prepare({ replaceInvalid: true });
    assert.equal(replaced.reused, false);
    assert.equal(replaced.root, prepared.root);
    const { destination, record, ...failure } = replaced.quarantined;
    assert.deepEqual(failure, expected);
    assert.equal(path.dirname(destination), path.join(fixtureRoot, ".quarantine", "cursor-acp"));
    assert.equal(record, `${destination}.json`);
    assert.deepEqual(await readFile(path.join(destination, ...driftedRuntimeFile.split("/"))), drifted, "quarantine keeps the evidence byte-for-byte");
    const quarantineRecord = JSON.parse(await readFile(record, "utf8"));
    assert.equal(quarantineRecord.schema, "saarius.acp.quarantine.v1");
    assert.equal(quarantineRecord.from, prepared.root);
    assert.deepEqual(quarantineRecord.failure, expected);
    assert.ok(await findReady({ pluginRoot, bridge: "cursor-acp", env: await isolatedRuntimeEnv(fixtureRoot) }));

    const reused = await prepare({ replaceInvalid: true });
    assert.equal(reused.reused, true);
    assert.equal(reused.quarantined, undefined);
    assert.equal((await readdir(path.join(fixtureRoot, ".quarantine", "cursor-acp"))).length, 2);
    assert.equal(await countLines(counterPath), 2);
  } finally {
    await rm(pluginRoot, { recursive: true, force: true });
    await rm(fixtureRoot, { recursive: true, force: true });
    await rm(nodeModules, { recursive: true, force: true });
    await rm(fake.fixtureRoot, { recursive: true, force: true });
  }
});

test("prepare.mjs and the launcher name the failing check for an invalid runtime", async () => {
  const fixtureRoot = await mkdtemp(path.join(tmpdir(), "saarius-acp-cli-invalid-"));
  const fake = await makeFakeNpm();
  const nodeModules = await makeSyntheticNodeModules("cursor-acp");
  const pluginRoot = await makePluginSnapshot("cursor-acp", { includeLauncher: true });
  const env = {
    PATH: `${fake.fixtureRoot}:${process.env.PATH ?? ""}`,
    HOME: process.env.HOME ?? "",
    ...npmEnv("cursor-acp", path.join(fixtureRoot, "npm.count"), nodeModules),
    ...(await isolatedRuntimeEnv(fixtureRoot)),
  };
  const run = (script, args) => spawnSync(process.execPath, [path.join(pluginRoot, "bridge", "acp-runtime", script), ...args], {
    encoding: "utf8",
    input: "",
    timeout: 30_000,
    env,
  });
  const expected = { check: "dependency_inventory", path: driftedRuntimeFile, kind: "changed" };
  try {
    const missing = run("launcher.mjs", ["cursor-acp"]);
    assert.equal(missing.status, 2, missing.stderr);
    const missingError = JSON.parse(missing.stderr);
    assert.equal(missingError.code, "RUNTIME_SETUP_REQUIRED");
    assert.equal(missingError.details.state, "missing");
    assert.equal(missingError.details.nodeVersion, process.versions.node);
    assert.match(missingError.details.identity, /^[0-9a-f]{64}$/);

    const badArgs = run("prepare.mjs", ["--bridge", "cursor-acp", "--force"]);
    assert.equal(badArgs.status, 2);
    assert.equal(JSON.parse(badArgs.stdout).code, "INVALID_ARGUMENT");
    assert.match(JSON.parse(badArgs.stdout).usage, /\[--replace-invalid\]$/);

    const ready = run("prepare.mjs", ["--bridge", "cursor-acp"]);
    assert.equal(ready.status, 0, ready.stdout);
    const { root } = JSON.parse(ready.stdout);
    await appendInsideFixture(fixtureRoot, path.join(root, ...driftedRuntimeFile.split("/")), `\n// ${CONTENT_MARKER}\n`);

    const invalid = run("launcher.mjs", ["cursor-acp"]);
    assert.equal(invalid.status, 2, invalid.stderr);
    assert.doesNotMatch(invalid.stderr, new RegExp(CONTENT_MARKER));
    const invalidError = JSON.parse(invalid.stderr);
    assert.equal(invalidError.code, "RUNTIME_SETUP_REQUIRED");
    const { recovery: launcherRecovery, ...launcherDetails } = invalidError.details;
    assert.deepEqual(launcherDetails, { state: "invalid", root, ...expected });
    assert.match(launcherRecovery, /prepare\.mjs --bridge cursor-acp --replace-invalid$/);

    const conflict = run("prepare.mjs", ["--bridge", "cursor-acp"]);
    assert.equal(conflict.status, 2, conflict.stdout);
    assert.doesNotMatch(conflict.stdout, new RegExp(CONTENT_MARKER));
    const conflictReport = JSON.parse(conflict.stdout);
    assert.equal(conflictReport.code, "RUNTIME_IDENTITY_CONFLICT");
    const { recovery, ...conflictDetails } = conflictReport.details;
    assert.deepEqual(conflictDetails, { root, ...expected });
    assert.equal(recovery, launcherRecovery);

    const replaced = run("prepare.mjs", ["--bridge", "cursor-acp", "--replace-invalid"]);
    assert.equal(replaced.status, 0, replaced.stdout);
    const replacedReport = JSON.parse(replaced.stdout);
    assert.equal(replacedReport.code, "RUNTIME_READY");
    assert.equal(replacedReport.root, root);
    const { destination, record, ...failure } = replacedReport.quarantined;
    assert.deepEqual(failure, expected);
    await access(path.join(destination, ...driftedRuntimeFile.split("/")));
    await access(record);
    assert.equal((await inspectRuntime({ pluginRoot, bridge: "cursor-acp", env: await isolatedRuntimeEnv(fixtureRoot) })).state, "ready");
  } finally {
    await rm(pluginRoot, { recursive: true, force: true });
    await rm(fixtureRoot, { recursive: true, force: true });
    await rm(nodeModules, { recursive: true, force: true });
    await rm(fake.fixtureRoot, { recursive: true, force: true });
  }
});

test("--replace-invalid repairs a dangling runtime root link instead of treating it as missing", async () => {
  const fixtureRoot = await mkdtemp(path.join(tmpdir(), "saarius-acp-dangling-root-"));
  const fake = await makeFakeNpm();
  const nodeModules = await makeSyntheticNodeModules("cursor-acp");
  const pluginRoot = await makePluginSnapshot("cursor-acp");
  const expected = { check: "runtime_root", path: ".", kind: "symlink" };
  const prepare = (options = {}) => prepareSnapshot({ bridge: "cursor-acp", pluginRoot, runtimeRoot: fixtureRoot, command: fake.command, counterPath: path.join(fixtureRoot, "npm.count"), nodeModules, ...options });
  try {
    const prepared = await prepare();
    await replaceTreeWithDanglingLink(fixtureRoot, prepared.root);
    await assert.rejects(() => prepare(), (error) => {
      assert.equal(error.code, "RUNTIME_IDENTITY_CONFLICT");
      assert.deepEqual({ check: error.details.check, path: error.details.path, kind: error.details.kind }, expected);
      return true;
    });
    const replaced = await prepare({ replaceInvalid: true });
    assert.equal(replaced.reused, false);
    const { destination, record, ...failure } = replaced.quarantined;
    assert.deepEqual(failure, expected);
    assert.ok((await lstat(destination)).isSymbolicLink(), "the link itself is kept in quarantine");
    assert.ok((await lstat(prepared.root)).isDirectory());
    assert.ok(await findReady({ pluginRoot, bridge: "cursor-acp", env: await isolatedRuntimeEnv(fixtureRoot) }));
    await access(record);
  } finally {
    await rm(pluginRoot, { recursive: true, force: true });
    await rm(fixtureRoot, { recursive: true, force: true });
    await rm(nodeModules, { recursive: true, force: true });
    await rm(fake.fixtureRoot, { recursive: true, force: true });
  }
});

test("concurrent recoveries are serialized and never take a valid runtime away", async () => {
  const fixtureRoot = await mkdtemp(path.join(tmpdir(), "saarius-acp-recovery-race-"));
  const counterPath = path.join(fixtureRoot, "npm.count");
  const fake = await makeFakeNpm({ delayMs: 50 });
  const nodeModules = await makeSyntheticNodeModules("cursor-acp");
  const pluginRoot = await makePluginSnapshot("cursor-acp");
  const env = await isolatedRuntimeEnv(fixtureRoot);
  const prepare = (options = {}) => prepareSnapshot({ bridge: "cursor-acp", pluginRoot, runtimeRoot: fixtureRoot, command: fake.command, counterPath, nodeModules, ...options });
  try {
    const prepared = await prepare();
    await appendInsideFixture(fixtureRoot, path.join(prepared.root, ...driftedRuntimeFile.split("/")), `\n// ${CONTENT_MARKER}\n`);

    // Watch the runtime path the way a launcher would reach it: the drifted
    // tree may leave once, but after that the path must never go missing.
    let watching = true;
    const presence = [];
    const watcher = (async () => {
      while (watching) {
        let present;
        try {
          await lstat(path.join(prepared.root, "READY.json"));
          present = true;
        } catch {
          present = false;
        }
        if (presence.at(-1) !== present) presence.push(present);
        await new Promise((resolve) => setImmediate(resolve));
      }
    })();
    const results = await Promise.all([1, 2, 3].map(() => prepare({ replaceInvalid: true })));
    watching = false;
    await watcher;

    assert.deepEqual(presence, [true, false, true], "the runtime path went missing after it held a valid tree");
    assert.deepEqual(results.map((result) => result.root), [prepared.root, prepared.root, prepared.root]);
    assert.deepEqual(results.map((result) => Boolean(result.quarantined)).sort(), [false, false, true]);
    assert.equal(await countLines(counterPath), 2, "exactly one reinstall");
    assert.ok(await findReady({ pluginRoot, bridge: "cursor-acp", env }));
    const quarantine = await readdir(path.join(fixtureRoot, ".quarantine", "cursor-acp"));
    assert.equal(quarantine.filter((name) => name.endsWith(".json")).length, 1);
    assert.deepEqual(await readdir(path.join(fixtureRoot, ".locks")), []);
    assert.deepEqual(await readdir(path.join(fixtureRoot, ".staging")), []);
  } finally {
    await rm(pluginRoot, { recursive: true, force: true });
    await rm(fixtureRoot, { recursive: true, force: true });
    await rm(nodeModules, { recursive: true, force: true });
    await rm(fake.fixtureRoot, { recursive: true, force: true });
  }
});

test("a held or abandoned recovery lock leaves the invalid runtime untouched", async () => {
  const fixtureRoot = await mkdtemp(path.join(tmpdir(), "saarius-acp-recovery-lock-"));
  const counterPath = path.join(fixtureRoot, "npm.count");
  const fake = await makeFakeNpm();
  const nodeModules = await makeSyntheticNodeModules("cursor-acp");
  const pluginRoot = await makePluginSnapshot("cursor-acp");
  const prepare = (options = {}) => prepareSnapshot({ bridge: "cursor-acp", pluginRoot, runtimeRoot: fixtureRoot, command: fake.command, counterPath, nodeModules, ...options });
  try {
    const prepared = await prepare();
    const runtimeFile = path.join(prepared.root, ...driftedRuntimeFile.split("/"));
    await appendInsideFixture(fixtureRoot, runtimeFile, `\n// ${CONTENT_MARKER}\n`);
    const drifted = await readFile(runtimeFile);
    const lock = path.join(fixtureRoot, ".locks", `cursor-acp-${prepared.descriptor.identity}.lock`);
    await mkdir(lock, { recursive: true });

    await writeFile(path.join(lock, "owner.json"), JSON.stringify({ pid: process.pid }));
    await assert.rejects(() => prepare({ replaceInvalid: true, recoveryLockTimeoutMs: 300 }), (error) => {
      assert.equal(error.code, "RUNTIME_RECOVERY_BUSY");
      assert.deepEqual(error.details, { lock, pid: process.pid });
      return true;
    });

    await writeFile(path.join(lock, "owner.json"), JSON.stringify({ pid: 8_888_888 }));
    await assert.rejects(() => prepare({ replaceInvalid: true }), (error) => {
      assert.equal(error.code, "RUNTIME_RECOVERY_LOCK_STALE");
      assert.deepEqual(error.details, { lock, pid: 8_888_888 });
      return true;
    });
    await access(lock);
    assert.deepEqual(await readFile(runtimeFile), drifted, "no recovery ran while the lock was held");
    await assert.rejects(() => readdir(path.join(fixtureRoot, ".quarantine")), { code: "ENOENT" });

    await rm(lock, { recursive: true });
    const replaced = await prepare({ replaceInvalid: true });
    assert.ok(replaced.quarantined);
    assert.ok(await findReady({ pluginRoot, bridge: "cursor-acp", env: await isolatedRuntimeEnv(fixtureRoot) }));
  } finally {
    await rm(pluginRoot, { recursive: true, force: true });
    await rm(fixtureRoot, { recursive: true, force: true });
    await rm(nodeModules, { recursive: true, force: true });
    await rm(fake.fixtureRoot, { recursive: true, force: true });
  }
});

test("a waiting recovery re-validates under the lock and leaves a repaired runtime in place", async () => {
  const fixtureRoot = await mkdtemp(path.join(tmpdir(), "saarius-acp-recovery-wait-"));
  const counterPath = path.join(fixtureRoot, "npm.count");
  const fake = await makeFakeNpm();
  const nodeModules = await makeSyntheticNodeModules("cursor-acp");
  const pluginRoot = await makePluginSnapshot("cursor-acp");
  const env = await isolatedRuntimeEnv(fixtureRoot);
  const prepare = (options = {}) => prepareSnapshot({ bridge: "cursor-acp", pluginRoot, runtimeRoot: fixtureRoot, command: fake.command, counterPath, nodeModules, ...options });
  try {
    const prepared = await prepare();
    await appendInsideFixture(fixtureRoot, path.join(prepared.root, ...driftedRuntimeFile.split("/")), `\n// ${CONTENT_MARKER}\n`);
    const lock = path.join(fixtureRoot, ".locks", `cursor-acp-${prepared.descriptor.identity}.lock`);
    await mkdir(lock, { recursive: true });
    await writeFile(path.join(lock, "owner.json"), JSON.stringify({ pid: process.pid }));

    // The slow recovery has already seen the invalid tree and now waits.
    const slow = prepare({ replaceInvalid: true });
    await new Promise((resolve) => setTimeout(resolve, 300));
    // Meanwhile the lock holder repairs the runtime.
    await rename(await fixturePath(fixtureRoot, prepared.root), path.join(fixtureRoot, "set-aside"));
    assert.equal((await prepare()).reused, false);
    const repairedReady = await readFile(path.join(prepared.root, "READY.json"));

    let watching = true;
    let wentMissing = false;
    const watcher = (async () => {
      while (watching) {
        try {
          await lstat(path.join(prepared.root, "READY.json"));
        } catch {
          wentMissing = true;
        }
        await new Promise((resolve) => setImmediate(resolve));
      }
    })();
    await rm(lock, { recursive: true });
    const result = await slow;
    watching = false;
    await watcher;

    assert.equal(wentMissing, false, "the repaired runtime was moved away");
    assert.deepEqual({ reused: result.reused, quarantined: result.quarantined }, { reused: true, quarantined: undefined });
    assert.deepEqual(await readFile(path.join(prepared.root, "READY.json")), repairedReady);
    assert.equal(await countLines(counterPath), 2, "the waiting recovery did not reinstall");
    await assert.rejects(() => readdir(path.join(fixtureRoot, ".quarantine")), { code: "ENOENT" });
    assert.ok(await findReady({ pluginRoot, bridge: "cursor-acp", env }));
  } finally {
    await rm(pluginRoot, { recursive: true, force: true });
    await rm(fixtureRoot, { recursive: true, force: true });
    await rm(nodeModules, { recursive: true, force: true });
    await rm(fake.fixtureRoot, { recursive: true, force: true });
  }
});
