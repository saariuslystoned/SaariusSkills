import assert from "node:assert/strict";
import { chmod, cp, mkdir, readFile, readdir, rm, writeFile } from "node:fs/promises";
import { mkdtemp } from "node:fs/promises";
import { spawnSync } from "node:child_process";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { prepareRuntime } from "../runtime-store.mjs";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const bridges = ["cursor-acp", "antigravity-acp"];
const expectedTools = {
  "cursor-acp": ["cancel", "delegate", "readiness", "result", "status", "steer"].map((name) => `cursor_acp_${name}`),
  "antigravity-acp": ["cancel", "delegate", "readiness", "result", "status", "steer"].map((name) => `antigravity_acp_${name}`),
};

async function makePluginSnapshot(bridge) {
  const pluginRoot = await mkdtemp(path.join(tmpdir(), `saarius-${bridge}-snapshot-`));
  const sourceRoot = path.join(repoRoot, "bridge", bridge);
  const targetRoot = path.join(pluginRoot, "bridge", bridge);
  await mkdir(targetRoot, { recursive: true });
  for (const relativePath of ["package.json", "package-lock.json", "server.mjs", "broker.mjs", ...(bridge === "antigravity-acp" ? ["contract.mjs"] : [])]) {
    await cp(path.join(sourceRoot, relativePath), path.join(targetRoot, relativePath));
  }
  return pluginRoot;
}

async function makeFakeNpm({ mode = "copy", delayMs = 0 } = {}) {
  const fixtureRoot = await mkdtemp(path.join(tmpdir(), "saarius-acp-fake-npm-"));
  const command = path.join(fixtureRoot, "npm");
  await writeFile(command, `#!/usr/bin/env node
import { appendFile, cp } from "node:fs/promises";
import path from "node:path";

const delayMs = Number(process.env.SAARIUS_TEST_NPM_DELAY_MS || ${delayMs});
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

test("clean plugin snapshots prepare both bridges and reuse without reinstalling", async () => {
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
    assert.equal(await countLines(counterPath), 2);
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

test("prepared dependency-free plugin sources launch both real MCP servers and list six tools", async () => {
  const fixtureRoot = await mkdtemp(path.join(tmpdir(), "saarius-acp-mcp-"));
  const counterPath = path.join(fixtureRoot, "npm.count");
  const fake = await makeFakeNpm();
  try {
    for (const bridge of bridges) {
      await prepareSnapshot({
        bridge,
        pluginRoot: repoRoot,
        runtimeRoot: fixtureRoot,
        command: fake.command,
        counterPath,
      });
      const setup = spawnSync(process.execPath, [path.join(repoRoot, "bridge", bridge, "scripts", "setup.mjs"), "--check"], {
        cwd: repoRoot,
        encoding: "utf8",
        timeout: 30_000,
        env: { ...process.env, SAARIUS_ACP_RUNTIME_ROOT: fixtureRoot },
      });
      assert.equal(setup.status, 0, setup.stderr);
      const report = JSON.parse(setup.stdout);
      assert.equal(report.code, "MCP_READY");
      assert.deepEqual(report.tools, expectedTools[bridge]);
    }
  } finally {
    await rm(fixtureRoot, { recursive: true, force: true });
    await rm(fake.fixtureRoot, { recursive: true, force: true });
  }
});
