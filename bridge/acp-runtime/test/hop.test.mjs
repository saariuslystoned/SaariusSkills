import assert from "node:assert/strict";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { spawnSync } from "node:child_process";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import {
  HOP_ARGV_ENV,
  HOP_ROLE_ENV,
  HOP_WORKER_FLAG,
  HOP_WORKER_ROLE,
  HopError,
  resolveHop,
  spawnStdioChild,
} from "../hop.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const launcher = path.join(here, "../launcher.mjs");
const hopPeer = path.join(here, "fixtures/hop-peer.mjs");

function hopEnv(overrides = {}) {
  const env = { ...overrides };
  return env;
}

test("unset hop argv stays a local parent launch", () => {
  const hop = resolveHop({ env: hopEnv({}), bridge: "antigravity-acp" });
  assert.equal(hop.mode, "local");
  assert.equal(hop.role, "parent");
});

test("whitespace hop argv stays local", () => {
  const hop = resolveHop({ env: hopEnv({ [HOP_ARGV_ENV]: "   " }), bridge: "antigravity-acp" });
  assert.equal(hop.mode, "local");
});

test("valid hop argv strips the hop env and marks the child a worker", () => {
  const argv = [process.execPath, hopPeer, "antigravity-acp"];
  const hop = resolveHop({
    env: hopEnv({ [HOP_ARGV_ENV]: JSON.stringify(argv), HOME: "/tmp" }),
    bridge: "antigravity-acp",
  });
  assert.equal(hop.mode, "hop");
  assert.deepEqual(hop.argv, argv);
  assert.equal(hop.childEnv[HOP_ARGV_ENV], undefined);
  assert.equal(hop.childEnv[HOP_ROLE_ENV], HOP_WORKER_ROLE);
  assert.equal(hop.childEnv.HOME, "/tmp");
  assert.match(hop.identity, /^[0-9a-f]{16}$/);
});

test("invalid hop argv fails closed instead of launching locally", () => {
  assert.throws(
    () => resolveHop({ env: hopEnv({ [HOP_ARGV_ENV]: "{not-json" }), bridge: "antigravity-acp" }),
    (error) => error instanceof HopError && error.code === "HOP_ARGV_INVALID",
  );
  assert.throws(
    () => resolveHop({ env: hopEnv({ [HOP_ARGV_ENV]: "[]" }), bridge: "antigravity-acp" }),
    (error) => error instanceof HopError && error.code === "HOP_ARGV_INVALID",
  );
  assert.throws(
    () => resolveHop({ env: hopEnv({ [HOP_ARGV_ENV]: JSON.stringify(["ssh", 22]) }), bridge: "antigravity-acp" }),
    (error) => error instanceof HopError && error.code === "HOP_ARGV_INVALID",
  );
});

test("acpx and --agent hop argv are refused", () => {
  assert.throws(
    () => resolveHop({ env: hopEnv({ [HOP_ARGV_ENV]: JSON.stringify(["acpx", "--agent", "ssh"]) }), bridge: "antigravity-acp" }),
    (error) => error instanceof HopError && error.code === "HOP_ACPX_REFUSED",
  );
  assert.throws(
    () => resolveHop({
      env: hopEnv({ [HOP_ARGV_ENV]: JSON.stringify(["/usr/local/bin/acpx", "antigravity"]) }),
      bridge: "antigravity-acp",
    }),
    (error) => error instanceof HopError && error.code === "HOP_ACPX_REFUSED",
  );
  assert.throws(
    () => resolveHop({
      env: hopEnv({ [HOP_ARGV_ENV]: JSON.stringify(["ssh", "-T", "host", "--agent"]) }),
      bridge: "antigravity-acp",
    }),
    (error) => error instanceof HopError && error.code === "HOP_ACPX_REFUSED",
  );
});

test("token-shaped hop argv is refused", () => {
  assert.throws(
    () => resolveHop({
      env: hopEnv({ [HOP_ARGV_ENV]: JSON.stringify(["ssh", "-T", "host", "sk-testdummy"]) }),
      bridge: "antigravity-acp",
    }),
    (error) => error instanceof HopError && error.code === "HOP_SECRET_REFUSED",
  );
});

test("a worker role cannot hop again", () => {
  assert.throws(
    () => resolveHop({
      env: hopEnv({
        [HOP_ROLE_ENV]: HOP_WORKER_ROLE,
        [HOP_ARGV_ENV]: JSON.stringify([process.execPath, hopPeer]),
      }),
      bridge: "antigravity-acp",
    }),
    (error) => error instanceof HopError && error.code === "HOP_NESTED",
  );
});

test("spawnStdioChild forwards the worker env to the hop command", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "saarius-hop-child-"));
  const marker = path.join(root, "marker.json");
  try {
    const argv = [process.execPath, hopPeer];
    const hop = resolveHop({
      env: hopEnv({
        [HOP_ARGV_ENV]: JSON.stringify(argv),
        SAARIUS_TEST_HOP_MARKER: marker,
      }),
    });
    const child = spawnStdioChild({
      command: hop.argv[0],
      args: hop.argv.slice(1),
      env: hop.childEnv,
      cwd: root,
      stdio: "ignore",
    });
    const code = await new Promise((resolve, reject) => {
      child.once("error", reject);
      child.once("exit", (exitCode) => resolve(exitCode));
    });
    assert.equal(code, 0);
    assert.deepEqual(JSON.parse(await readFile(marker, "utf8")), {
      hopArgv: null,
      role: HOP_WORKER_ROLE,
      bridgeArg: null,
    });
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("launcher hops without a local prepared runtime", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "saarius-hop-launcher-"));
  const marker = path.join(root, "marker.json");
  try {
    const launched = spawnSync(process.execPath, [launcher, "antigravity-acp"], {
      cwd: root,
      encoding: "utf8",
      timeout: 10_000,
      env: {
        PATH: process.env.PATH ?? "",
        HOME: root,
        SAARIUS_ACP_RUNTIME_ROOT: path.join(root, "missing-runtime"),
        SAARIUS_TEST_HOP_MARKER: marker,
        [HOP_ARGV_ENV]: JSON.stringify([process.execPath, hopPeer, "antigravity-acp"]),
      },
    });
    assert.equal(launched.status, 0, launched.stderr || launched.stdout);
    assert.match(launched.stderr, /"status":"hop"/);
    assert.doesNotMatch(launched.stderr, /RUNTIME_SETUP_REQUIRED/);
    assert.deepEqual(JSON.parse(await readFile(marker, "utf8")), {
      hopArgv: null,
      role: HOP_WORKER_ROLE,
      bridgeArg: "antigravity-acp",
    });
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("launcher without hop still requires a prepared runtime", () => {
  const launched = spawnSync(process.execPath, [launcher, "antigravity-acp"], {
    encoding: "utf8",
    timeout: 10_000,
    env: {
      PATH: process.env.PATH ?? "",
      HOME: tmpdir(),
      SAARIUS_ACP_RUNTIME_ROOT: path.join(tmpdir(), "saarius-hop-unprepared"),
    },
  });
  assert.equal(launched.status, 2);
  assert.match(launched.stderr, /RUNTIME_SETUP_REQUIRED/);
});

test("launcher refuses an acpx hop argv before spawn", () => {
  const launched = spawnSync(process.execPath, [launcher, "antigravity-acp"], {
    encoding: "utf8",
    timeout: 10_000,
    env: {
      PATH: process.env.PATH ?? "",
      HOME: tmpdir(),
      [HOP_ARGV_ENV]: JSON.stringify(["acpx", "--agent", "ssh host"]),
    },
  });
  assert.equal(launched.status, 2);
  assert.match(launched.stderr, /HOP_ACPX_REFUSED/);
});

test("launcher worker mode survives an independent transport environment", () => {
  const nested = [process.execPath, "-e", "console.log('NESTED_HOP_EXECUTED')"];
  const transport = [
    "const { spawnSync } = require('node:child_process');",
    `const result = spawnSync(process.execPath, ${JSON.stringify([launcher, "antigravity-acp", HOP_WORKER_FLAG])}, {`,
    "  encoding: 'utf8',",
    "  env: {",
    `    PATH: ${JSON.stringify(process.env.PATH ?? "")},`,
    `    HOME: ${JSON.stringify(tmpdir())},`,
    `    ${JSON.stringify(HOP_ARGV_ENV)}: ${JSON.stringify(JSON.stringify(nested))},`,
    "  },",
    "});",
    "process.stdout.write(result.stdout);",
    "process.stderr.write(result.stderr);",
    "process.exitCode = result.status;",
  ].join("\n");
  const launched = spawnSync(process.execPath, [launcher, "antigravity-acp"], {
    encoding: "utf8",
    timeout: 10_000,
    env: {
      PATH: process.env.PATH ?? "",
      HOME: tmpdir(),
      [HOP_ARGV_ENV]: JSON.stringify([process.execPath, "-e", transport]),
    },
  });
  assert.equal(launched.status, 2, launched.stderr || launched.stdout);
  assert.match(launched.stderr, /HOP_NESTED/);
  assert.doesNotMatch(launched.stdout, /NESTED_HOP_EXECUTED/);
});
