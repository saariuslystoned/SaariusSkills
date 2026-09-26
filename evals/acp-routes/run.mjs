#!/usr/bin/env node
// evals/acp-routes runner: fixed tasks × routes × repeats, strictly sequential.
// Drives this plugin's own bridge/acp-runtime/launcher.mjs over MCP stdio, the
// same command a host (Codex, Cursor, Claude Code) starts, then grades each
// attempt objectively with lib/grade.mjs. The worker's summary is recorded but
// never used for scoring.
//
// Writes need the documented break-glass policy. The runner refuses to start
// unless --permission approve-all is passed; it sets
// SAARIUS_ACP_PERMISSION_MODE only for the bridge processes it spawns and does
// not change any host configuration.
import { spawn, spawnSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { appendFile, cp, mkdir, readdir, writeFile } from "node:fs/promises";
import { homedir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { grade, loadTask } from "./lib/grade.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const PLUGIN_ROOT = path.resolve(HERE, "..", "..");
export const ROUTES = Object.freeze({
  cursor: { bridge: "cursor-acp", prefix: "cursor_acp" },
  antigravity: { bridge: "antigravity-acp", prefix: "antigravity_acp" },
  grok: { bridge: "grok-acp", prefix: "grok_acp" },
});
const TERMINAL = new Set(["completed", "failed", "cancelled", "needs-input"]);

function parseArgs(argv) {
  const a = { routes: Object.keys(ROUTES), tasks: null, repeats: 3, out: null, permission: null, dryRun: false };
  for (let i = 0; i < argv.length; i++) {
    const k = argv[i], v = argv[i + 1];
    if (k === "--routes") { a.routes = v.split(","); i++; }
    else if (k === "--tasks") { a.tasks = v.split(","); i++; }
    else if (k === "--repeats") { a.repeats = Number(v); i++; }
    else if (k === "--out") { a.out = path.resolve(v); i++; }
    else if (k === "--permission") { a.permission = v; i++; }
    else if (k === "--dry-run") a.dryRun = true;
    else throw new Error(`unknown argument ${k}`);
  }
  for (const r of a.routes) if (!ROUTES[r]) throw new Error(`unknown route ${r}`);
  if (!Number.isInteger(a.repeats) || a.repeats < 1) throw new Error("--repeats must be a positive integer");
  if (!a.dryRun && a.permission !== "approve-all") {
    throw new Error("benchmark tasks write files: pass --permission approve-all (break-glass, scoped to this run's bridge processes)");
  }
  return a;
}

class McpClient {
  constructor(bridge, cwd, env) {
    this.child = spawn(process.execPath, [path.join(PLUGIN_ROOT, "bridge", "acp-runtime", "launcher.mjs"), bridge], {
      cwd, env, stdio: ["pipe", "pipe", "pipe"],
    });
    this.stderr = "";
    this.child.stderr.on("data", (d) => { this.stderr = (this.stderr + d).slice(-4000); });
    this.pending = new Map();
    this.id = 0;
    let buf = "";
    this.child.stdout.on("data", (d) => {
      buf += d;
      let i;
      while ((i = buf.indexOf("\n")) >= 0) {
        const line = buf.slice(0, i); buf = buf.slice(i + 1);
        if (!line.trim()) continue;
        let msg; try { msg = JSON.parse(line); } catch { continue; }
        this.pending.get(msg.id)?.(msg);
      }
    });
    this.exited = new Promise((r) => this.child.once("exit", r));
  }
  rpc(method, params, timeoutMs = 120_000) {
    const n = ++this.id;
    return new Promise((resolve, reject) => {
      const t = setTimeout(() => { this.pending.delete(n); reject(new Error(`${method} timed out`)); }, timeoutMs);
      this.pending.set(n, (m) => { clearTimeout(t); this.pending.delete(n); resolve(m); });
      this.child.stdin.write(`${JSON.stringify({ jsonrpc: "2.0", id: n, method, params })}\n`);
    });
  }
  async init() {
    await this.rpc("initialize", { protocolVersion: "2025-06-18", capabilities: {}, clientInfo: { name: "saarius-acp-route-evals", version: "1" } });
    this.child.stdin.write(`${JSON.stringify({ jsonrpc: "2.0", method: "notifications/initialized" })}\n`);
  }
  async call(name, args, timeoutMs) {
    const r = await this.rpc("tools/call", { name, arguments: args }, timeoutMs);
    const text = r.result?.content?.[0]?.text;
    try { return JSON.parse(text); } catch { return { status: "bridge-error", raw: text ?? null, error: r.error ?? null }; }
  }
  async close() { this.child.stdin.end(); this.child.kill(); await Promise.race([this.exited, new Promise((r) => setTimeout(r, 3000))]); }
}

async function seedWorkspace(task, dir) {
  await mkdir(dir, { recursive: true });
  await cp(path.join(task.dir, "seed"), dir, { recursive: true });
  const git = (...args) => spawnSync("git", args, { cwd: dir, encoding: "utf8" });
  git("init", "-q");
  git("add", "-A");
  git("-c", "user.name=acp-route-evals", "-c", "user.email=evals@local", "commit", "-qm", "seed");
}

async function attempt({ route, task, repeat, runDir, env }) {
  const { bridge, prefix } = ROUTES[route];
  const workspace = path.join(runDir, "workspaces", `${route}-${task.id}-${repeat}`);
  await seedWorkspace(task, workspace);
  const record = { route, task: task.id, category: task.category, repeat, workspace, startedAt: new Date().toISOString() };
  const client = new McpClient(bridge, workspace, env);
  const t0 = Date.now();
  try {
    await client.init();
    const ready = await client.call(`${prefix}_readiness`, { workspace });
    record.ready = ready.ready === true;
    record.model = ready.model?.selectedModelId ?? ready.route?.model ?? null;
    if (!record.ready) { record.outcome = "not-ready"; return record; }
    const job = await client.call(`${prefix}_delegate`, {
      workspace, prompt: task.prompt, timeoutMs: task.timeoutMs, hostConversationId: `acp-route-evals-${randomUUID()}`,
    });
    record.jobId = job.jobId ?? null;
    let result = job;
    const deadline = t0 + task.timeoutMs + 120_000;
    while (record.jobId && !TERMINAL.has(result.status) && Date.now() < deadline) {
      result = await client.call(`${prefix}_result`, { jobId: record.jobId, waitMs: 60_000 }, 180_000);
    }
    if (record.jobId && !TERMINAL.has(result.status)) {
      await client.call(`${prefix}_cancel`, { jobId: record.jobId }).catch(() => {});
      result = { ...result, status: "harness-timeout" };
    }
    Object.assign(record, {
      outcome: result.status,
      stopReason: result.stopReason ?? null,
      errorCode: result.error?.code ?? null,
      jobWallMs: result.startedAt && result.updatedAt ? Date.parse(result.updatedAt) - Date.parse(result.startedAt) : null,
      toolCallCount: result.toolCallCount ?? null,
      eventCount: result.eventCount ?? null,
      cleanup: result.cleanup?.status ?? (result.cleanupReady ? "completed" : null),
      handoffChars: typeof result.handoff === "string" ? result.handoff.length : null,
    });
  } catch (error) {
    record.outcome = "runner-error";
    record.runnerError = String(error?.message ?? error).slice(0, 300);
  } finally {
    record.totalWallMs = Date.now() - t0;
    await client.close();
  }
  record.grade = await grade(workspace, task);
  return record;
}

function median(xs) {
  const s = xs.filter((x) => Number.isFinite(x)).sort((a, b) => a - b);
  if (!s.length) return null;
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}

export function summarize(records) {
  const groups = new Map();
  for (const r of records) {
    const k = `${r.route}|${r.model ?? "?"}|${r.task}`;
    if (!groups.has(k)) groups.set(k, []);
    groups.get(k).push(r);
  }
  const rows = [...groups.entries()].map(([k, list]) => {
    const [route, model, task] = k.split("|");
    return {
      route, model, task, category: list[0].category, n: list.length,
      solved: list.filter((r) => r.grade?.solved).length,
      meanScore: list.reduce((s, r) => s + (r.grade?.score ?? 0), 0) / list.length,
      medianJobWallMs: median(list.map((r) => r.jobWallMs)),
      medianToolCalls: median(list.map((r) => r.toolCallCount)),
      syntaxFailures: list.filter((r) => r.grade && !r.grade.syntaxOk).length,
      protectedViolations: list.filter((r) => r.grade && !r.grade.protectedOk).length,
      nonCompleted: list.filter((r) => r.outcome !== "completed").map((r) => r.errorCode ?? r.outcome),
    };
  });
  return rows.sort((a, b) => a.task.localeCompare(b.task) || a.route.localeCompare(b.route));
}

export function renderMarkdown(meta, rows) {
  const fmt = (ms) => (ms == null ? "—" : ms < 90_000 ? `${(ms / 1000).toFixed(0)}s` : `${Math.floor(ms / 60000)}m ${String(Math.round((ms % 60000) / 1000)).padStart(2, "0")}s`);
  const lines = [
    `# ACP route benchmark — ${meta.startedAt.slice(0, 10)}`,
    "",
    `Plugin commit \`${meta.pluginCommit}\`, host ${meta.host}, node ${meta.node}. Sequential, ${meta.repeats} repeat(s) per route × task.`,
    `Permission: \`${meta.permission}\` scoped to the runner's bridge processes. Scores are hidden-test pass fractions (0 when a gate fails).`,
    "",
    "| Task | Route | Model | Solved | Mean score | Median job time | Median tool calls | Syntax fails | Protected edits | Non-completed |",
    "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
  ];
  for (const r of rows) {
    lines.push(`| ${r.task} | ${r.route} | ${r.model} | ${r.solved}/${r.n} | ${r.meanScore.toFixed(2)} | ${fmt(r.medianJobWallMs)} | ${r.medianToolCalls ?? "—"} | ${r.syntaxFailures} | ${r.protectedViolations} | ${r.nonCompleted.join(", ") || "—"} |`);
  }
  return `${lines.join("\n")}\n`;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const taskIds = args.tasks ?? (await readdir(path.join(HERE, "tasks"), { withFileTypes: true })).filter((d) => d.isDirectory()).map((d) => d.name).sort();
  const tasks = await Promise.all(taskIds.map((id) => loadTask(path.join(HERE, "tasks", id))));
  const startedAt = new Date().toISOString();
  const runDir = args.out ?? path.join(homedir(), ".local", "state", "saarius-skills", "acp-route-evals", startedAt.replace(/[:.]/g, "-"));
  await mkdir(runDir, { recursive: true });
  const meta = {
    startedAt, runDir, repeats: args.repeats, routes: args.routes, tasks: taskIds, permission: args.permission ?? "dry-run",
    pluginCommit: spawnSync("git", ["rev-parse", "--short", "HEAD"], { cwd: PLUGIN_ROOT, encoding: "utf8" }).stdout.trim() || "unknown",
    host: `${process.platform}-${process.arch}`, node: process.version,
  };
  await writeFile(path.join(runDir, "meta.json"), `${JSON.stringify(meta, null, 2)}\n`);
  // Order: repeat-major, then task, then route, so each route sees tasks in the same order.
  const plan = [];
  for (let repeat = 1; repeat <= args.repeats; repeat++) for (const task of tasks) for (const route of args.routes) plan.push({ route, task, repeat });
  process.stderr.write(`acp-route-evals: ${plan.length} attempts → ${runDir}\n`);
  if (args.dryRun) { for (const p of plan) process.stdout.write(`${p.repeat} ${p.task.id} ${p.route}\n`); return; }
  const env = { ...process.env, SAARIUS_ACP_PERMISSION_MODE: "approve-all" };
  const records = [];
  for (const [i, p] of plan.entries()) {
    const record = await attempt({ ...p, runDir, env });
    records.push(record);
    await appendFile(path.join(runDir, "results.jsonl"), `${JSON.stringify(record)}\n`);
    process.stderr.write(`[${i + 1}/${plan.length}] ${p.route} ${p.task.id} #${p.repeat}: ${record.outcome} solved=${record.grade?.solved} score=${record.grade?.score?.toFixed(2)} ${Math.round((record.jobWallMs ?? record.totalWallMs) / 1000)}s\n`);
  }
  await writeFile(path.join(runDir, "SUMMARY.md"), renderMarkdown(meta, summarize(records)));
  process.stderr.write(`done: ${path.join(runDir, "SUMMARY.md")}\n`);
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch((error) => { process.stderr.write(`acp-route-evals: ${error.message}\n`); process.exitCode = 2; });
}
