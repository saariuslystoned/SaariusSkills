#!/usr/bin/env node
// Distil candidate lessons from evidence files into the lessons schema.
//
//   node distill.mjs --benchmark <results.jsonl> [--case-study <case-study.jsonl>]
//
// Prints one candidate lesson per line (JSON). Candidates are evidence
// summaries, not verdicts: an orchestrator reviews them, edits the note, and
// appends the ones worth keeping to references/lessons.jsonl.
import { readFile } from "node:fs/promises";

const args = process.argv.slice(2);
const opt = (name) => { const i = args.indexOf(name); return i >= 0 ? args[i + 1] : null; };

async function readJsonl(file) {
  if (!file) return [];
  return (await readFile(file, "utf8")).split("\n").filter((l) => l.trim()).map((l) => JSON.parse(l));
}

const median = (xs) => {
  const s = xs.filter(Number.isFinite).sort((a, b) => a - b);
  if (!s.length) return null;
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
};
const secs = (ms) => (ms == null ? "?" : `${Math.round(ms / 1000)}s`);

export function benchmarkCandidates(records, at = new Date().toISOString()) {
  const groups = new Map();
  for (const r of records) {
    const key = `${r.route}|${r.model}|${r.task}`;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(r);
  }
  return [...groups.values()].map((list) => {
    const { route, model, task, category } = list[0];
    const n = list.length;
    const solved = list.filter((r) => r.grade?.solved).length;
    const syntax = list.filter((r) => r.grade && !r.grade.syntaxOk).length;
    const tamper = list.filter((r) => r.grade && !r.grade.protectedOk).length;
    const meanScore = list.reduce((s, r) => s + (r.grade?.score ?? 0), 0) / n;
    const kind = solved === n ? "strength" : solved === 0 ? "weakness" : "observation";
    const issues = [syntax && `${syntax} syntax-broken`, tamper && `${tamper} edited protected files`].filter(Boolean);
    return {
      at, lane: route, model, category, kind, source: "benchmark", n,
      note: `${category}: solved ${solved}/${n} (mean score ${meanScore.toFixed(2)})${issues.length ? `; ${issues.join(", ")}` : ""}.`,
      evidence: `evals/acp-routes task ${task}: median job ${secs(median(list.map((r) => r.jobWallMs)))}, median ${median(list.map((r) => r.toolCallCount)) ?? "?"} tool calls.`,
      jobIds: list.map((r) => r.jobId).filter(Boolean),
    };
  });
}

const LANE = { agy: "antigravity", cursor: "cursor", grok: "grok" };
export function caseStudyCandidates(rows, at = new Date().toISOString()) {
  const groups = new Map();
  for (const r of rows) {
    const lane = LANE[r.lane] ?? r.lane;
    if (!groups.has(lane)) groups.set(lane, []);
    groups.get(lane).push(r);
  }
  return [...groups.entries()].map(([lane, list]) => {
    const n = list.length;
    const firstPass = list.filter((r) => r.gate === "pass" && r.dom === "pass" && !r.repair).length;
    const repaired = list.filter((r) => r.repair).length;
    const defects = list.filter((r) => r.defects).map((r) => `r${r.round}: ${r.defects}`);
    return {
      at, lane, model: list[0].model, category: "Multi-round UI build", kind: "observation", source: "case-study", n,
      note: `Chained cockpit build: ${firstPass}/${n} rounds passed first time, ${repaired} needed a repair.`,
      evidence: `median ${Math.round(median(list.map((r) => r.wallS)) ?? 0)}s and ${median(list.map((r) => r.toolCalls)) ?? "?"} tool calls per round${defects.length ? `; defects ${defects.join("; ")}` : ""}.`,
      jobIds: list.map((r) => r.jobId),
    };
  });
}

if (process.argv[1]?.endsWith("distill.mjs")) {
  const out = [
    ...benchmarkCandidates(await readJsonl(opt("--benchmark"))),
    ...caseStudyCandidates(await readJsonl(opt("--case-study"))),
  ];
  for (const c of out) process.stdout.write(`${JSON.stringify(c)}\n`);
}
