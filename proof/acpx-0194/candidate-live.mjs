// Candidate-only MCP client. Never changes installed plugin or shared runtimes.
// prepare is provider-free; run requires an explicit parent-reviewed launch gate.
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { mkdir, readFile, writeFile, stat } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { Client } from "../../bridge/cursor-acp/node_modules/@modelcontextprotocol/sdk/dist/esm/client/index.js";
import { StdioClientTransport } from "../../bridge/cursor-acp/node_modules/@modelcontextprotocol/sdk/dist/esm/client/stdio.js";
import { prepareRuntime, inspectRuntime } from "../../bridge/acp-runtime/runtime-store.mjs";

const repo = fileURLToPath(new URL("../../", import.meta.url));
const root = path.join(repo, "runs/acpx-0194-upgrade-runs/20261001/candidate-live");
const hostConversationId = "01a0f779-3c25-7a30-aafc-9e63f3f3d766";
const lanes = ["cursor-acp", "antigravity-acp", "grok-acp"];
const digest = bytes => createHash("sha256").update(bytes).digest("hex");
const env = { ...process.env, SAARIUS_ACP_RUNTIME_ROOT: path.join(root, "runtime"),
  SAARIUS_ACP_PERMISSION_MODE: "approve-all", SAARIUS_ACP_HOST_CONVERSATION_ID: hostConversationId };
const fixtureSource = 'export function normalizeLines(text) { return text; }\n';
const protectedTest = `import assert from "node:assert/strict";
import { normalizeLines } from "./normalize.mjs";
assert.equal(normalizeLines("a  \\r\\n\\n b \\n"), "a\\n b");
assert.equal(normalizeLines(""), "");
assert.equal(normalizeLines(" \\n\\t"), "");
assert.equal(normalizeLines("one\\ntwo\\n"), "one\\ntwo");
console.log("4 normalization cases passed");
`;
const prompt = "Fix normalize.mjs in this fixture only. normalizeLines(text) must split LF/CRLF, remove trailing whitespace on each line, drop whitespace-only lines, and join remaining lines with LF without a final newline. Preserve leading whitespace on nonblank lines. Run node protected-test.mjs. Do not edit protected-test.mjs or any other file. Do not access secrets, credentials, auth logs, .env files, network, or files outside this fixture. Return changed file, test result, and limitation in a short bounded handoff.";

async function save(lane, name, value) {
  const directory = path.join(root, lane);
  await mkdir(directory, { recursive: true });
  await writeFile(path.join(directory, name), JSON.stringify(value, null, 2) + "\n");
}

if (process.argv[2] === "prepare") {
  await mkdir(root, { recursive: true });
  for (const lane of lanes) {
    const workspace = path.join(root, lane, "fixture");
    await mkdir(workspace, { recursive: true });
    // Exclusive creation: rerunning prepare never overwrites a used fixture.
    for (const [name, content, mode] of [["normalize.mjs", fixtureSource, 0o644], ["protected-test.mjs", protectedTest, 0o444]]) {
      const file = path.join(workspace, name);
      try { await writeFile(file, content, { flag: "wx", mode }); }
      catch (error) { if (error.code !== "EEXIST") throw error; assert.equal(await readFile(file, "utf8"), content); }
    }
    try { await stat(path.join(root, lane, "LAUNCHED")); throw new Error("Fixture was already launched"); }
    catch (error) { if (error.code !== "ENOENT") throw error; }
    const prepared = await prepareRuntime({ pluginRoot: repo, bridge: lane, env });
    const manifest = JSON.parse(await readFile(path.join(prepared.root, "bridge", lane, "node_modules/acpx/package.json"), "utf8"));
    assert.equal(manifest.version, "0.19.4");
    await save(lane, "prepared.json", { lane, workspace, runtimeRoot: prepared.root,
      identity: prepared.descriptor.identity, acpx: manifest.version,
      protectedTestSha256: digest(Buffer.from(protectedTest)), promptSha256: digest(Buffer.from(prompt)),
      timeoutMs: 300000, maxPrompts: 1, permissionMode: "approve-all", transport: "candidate-supported-stdio-MCP-launcher",
      installedNativeRuntime: "0.19.3", launchGate: "independent source/driver review plus explicit candidate-client authorization" });
  }
  console.log(JSON.stringify({ status: "prepared", root, prompts: 0 }));
} else if (process.argv[2] === "run") {
  const lane = process.argv[3]; assert.ok(lanes.includes(lane));
  assert.equal(process.env.SAARIUS_0194_REVIEWED_LAUNCH, "approved", "Candidate client requires parent-reviewed explicit authorization");
  const admitted = JSON.parse(await readFile(path.join(root, lane, "prepared.json"), "utf8"));
  const checked = await inspectRuntime({ pluginRoot: repo, bridge: lane, env });
  assert.equal(checked.state, "ready"); assert.equal(checked.descriptor.identity, admitted.identity);
  const selected = lane === "cursor-acp" ? { model: "gpt-5.6-luna", effort: "medium" }
    : lane === "antigravity-acp" ? { model: "gemini-3.8-flash-high" } : {};
  const childEnv = { ...env,
    SAARIUS_CURSOR_ACP_STATE_DIR: path.join(root, lane, "state"),
    SAARIUS_ANTIGRAVITY_ACP_STATE_DIR: path.join(root, lane, "state"),
    SAARIUS_GROK_ACP_STATE_DIR: path.join(root, lane, "state") };
  const transport = new StdioClientTransport({ command: process.execPath,
    args: [path.join(repo, "bridge/acp-runtime/launcher.mjs"), lane], env: childEnv, stderr: "ignore" });
  const client = new Client({ name: "saarius-acpx-0194-reviewed-proof", version: "1" });
  const call = async (suffix, args) => {
    const response = await client.callTool({ name: lane.replaceAll("-", "_") + "_" + suffix, arguments: args }, undefined,
      { timeout: 60000 });
    const parsed = JSON.parse(response.content.find(item => item.type === "text").text);
    if (response.isError) throw Object.assign(new Error(parsed.error?.message ?? "MCP failure"), { code: parsed.error?.code });
    return parsed;
  };
  let submitted;
  try {
    await client.connect(transport);
    const ready = await call("readiness", { workspace: admitted.workspace, ...selected });
    // Save only control facts, never raw ACP bodies, auth logs or credentials.
    await save(lane, "readiness.json", { ready: ready.ready, route: ready.route, model: ready.model,
      permission: ready.permission, error: ready.error });
    assert.equal(ready.ready, true, JSON.stringify(ready.error));
    assert.equal(ready.permission.permissionMode, "approve-all");
    assert.equal(ready.model.selectedModelId, ready.model.currentModelId);
    assert.equal(digest(await readFile(path.join(admitted.workspace, "protected-test.mjs"))), admitted.protectedTestSha256);
    // An exclusive launch fence prevents retries, including after an uncertain result.
    await writeFile(path.join(root, lane, "LAUNCHED"), new Date().toISOString() + "\n", { flag: "wx" });
    submitted = await call("delegate", { workspace: admitted.workspace, hostConversationId, timeoutMs: 300000, prompt, ...selected });
    await save(lane, "submission.json", submitted);
    const deadline = Date.now() + 315000;
    let result;
    do {
      result = await call("result", { jobId: submitted.jobId, waitMs: 10000 });
      await save(lane, "result.json", result);
    } while (!result.complete && result.cleanup?.status !== "uncertain" && Date.now() < deadline);
    assert.equal(result.taskComplete, true); assert.equal(result.cleanupReady, true); assert.equal(result.complete, true);
    assert.equal(result.status, "completed");
    assert.equal(digest(await readFile(path.join(admitted.workspace, "protected-test.mjs"))), admitted.protectedTestSha256);
    assert.equal((await stat(path.join(admitted.workspace, "protected-test.mjs"))).mode & 0o777, 0o444);
    const { execFile } = await import("node:child_process"), { promisify } = await import("node:util");
    const tested = await promisify(execFile)(process.execPath, ["protected-test.mjs"], { cwd: admitted.workspace, timeout: 10000 });
    await save(lane, "verification.json", { tests: tested.stdout.trim(), protectedTestSha256: admitted.protectedTestSha256,
      cleanup: result.cleanup, acpx: "0.19.4", runtimeIdentity: admitted.identity });
    console.log(JSON.stringify({ lane, status: "passed", jobId: submitted.jobId, proof: path.join(root, lane) }));
  } finally {
    // Close only this task's own MCP client. Persist unknown cleanup; never clear fences.
    await client.close();
  }
} else throw new Error("Usage: candidate-live.mjs prepare | run <lane>");
