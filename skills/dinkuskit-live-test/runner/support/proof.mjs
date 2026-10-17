import { readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { config } from "./env.mjs";

const reportFile = join(config.runDir, "report.json");
let journeys, steps, facts;
let current = "";

/**
 * Loads the run's report so far. Playwright starts a new worker after a journey fails, so the next
 * journey's worker carries on from it instead of writing an empty report over it.
 */
function load() {
  const earlier = (() => { try { return JSON.parse(readFileSync(reportFile, "utf8")); } catch { return {}; } })();
  journeys = (earlier.journeys ?? []).map(entry => entry.name);
  steps = earlier.steps ?? [];
  facts = earlier.facts ?? {};
}
load();

/** Starts a journey; the steps recorded after it belong to it until the next one starts. */
export function startJourney(name) {
  current = name;
  // A journey run again under the same run id replaces its earlier steps.
  steps = steps.filter(s => s.journey !== name);
  if (!journeys.includes(name)) journeys.push(name);
  write();
}

/**
 * Fails a journey in the proof when Playwright failed it but the journey recorded no failure of its
 * own, as when the saved profile wouldn't open before its first step. The reporter runs this once
 * every worker has finished.
 */
export function failUnrecorded(name, step, detail) {
  load();
  if (journeyVerdict(name) === "FAIL") return;
  current = name;
  if (!journeys.includes(name)) journeys.push(name);
  record(step, "FAIL", detail);
}

/** The run's verdict and each journey's, as the report on disk has them. */
export function verdicts() {
  load();
  const results = journeys.map(name => ({ name, verdict: journeyVerdict(name) }));
  return { verdict: verdictOf(results.map(r => r.verdict)), journeys: results };
}

/** Records one step's result; the report is rewritten after every step so a crash still leaves it. */
export function record(step, status, detail = "") {
  steps.push({ journey: current, step, status, detail, at: new Date().toISOString() });
  write();
}

/** Remembers a fact for the report (order number, tracking number, PDF hash...). */
export function note(key, value) {
  facts[key] = value;
  write();
}

export async function shot(page, name) {
  const file = join(config.runDir, `${String(steps.length + 1).padStart(2, "0")}-${name}.png`);
  await page.screenshot({ path: file, fullPage: true }).catch(() => {});
  return file;
}

/** PASS only when every step passed or was skipped for a stated reason; a journey with no steps yet is INCOMPLETE. */
function verdictOf(results) {
  if (results.some(r => r === "FAIL")) return "FAIL";
  return results.length && results.every(r => r === "PASS" || r === "SKIP") ? "PASS" : "INCOMPLETE";
}

/** A journey's verdict from the steps it has recorded so far. */
export function journeyVerdict(name) {
  return verdictOf(steps.filter(s => s.journey === name).map(s => s.status));
}

const cell = value => String(value).replaceAll("|", "\\|").replaceAll("\n", " ");

function write() {
  const results = journeys.map(name => ({ name, verdict: journeyVerdict(name) }));
  const verdict = verdictOf(results.map(r => r.verdict));
  const report = { run: config.runId, mode: config.mode, store: config.store, ship: config.ship, verdict, journeys: results, facts, steps };
  writeFileSync(join(config.runDir, "report.json"), JSON.stringify(report, null, 2));
  const lines = [
    `# DinkusKit live test: ${verdict}`, "",
    `Run ${config.runId}, mode ${config.mode}, store ${config.store}.`, "",
    "| Journey | Result |", "| --- | --- |",
    ...results.map(r => `| ${cell(r.name)} | ${r.verdict} |`),
    ...results.flatMap(r => [
      "", `## ${r.name}: ${r.verdict}`, "",
      "| Step | Result | Detail |", "| --- | --- | --- |",
      ...steps.filter(s => s.journey === r.name).map(s => `| ${cell(s.step)} | ${s.status} | ${cell(s.detail)} |`),
    ]),
    "", "## Facts", "",
    ...Object.entries(facts).map(([key, value]) => `- ${key}: ${value}`),
  ];
  writeFileSync(join(config.runDir, "PROOF.md"), lines.join("\n") + "\n");
}
