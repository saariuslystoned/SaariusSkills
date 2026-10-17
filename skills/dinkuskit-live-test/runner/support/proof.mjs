import { writeFileSync } from "node:fs";
import { join } from "node:path";
import { config } from "./env.mjs";

const steps = [];
const facts = {};

/** Records one step's result; the report is rewritten after every step so a crash still leaves it. */
export function record(step, status, detail = "") {
  steps.push({ step, status, detail, at: new Date().toISOString() });
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

function write() {
  const verdict = steps.some(s => s.status === "FAIL") ? "FAIL" : steps.every(s => s.status === "PASS" || s.status === "SKIP") ? "PASS" : "INCOMPLETE";
  const report = { run: config.runId, mode: config.mode, store: config.store, ship: config.ship, verdict, facts, steps };
  writeFileSync(join(config.runDir, "report.json"), JSON.stringify(report, null, 2));
  const lines = [
    `# DinkusKit live test: ${verdict}`, "",
    `Run ${config.runId}, mode ${config.mode}, store ${config.store}.`, "",
    "| Step | Result | Detail |", "| --- | --- | --- |",
    ...steps.map(s => `| ${s.step} | ${s.status} | ${String(s.detail).replaceAll("|", "\\|").replaceAll("\n", " ")} |`),
    "", "## Facts", "",
    ...Object.entries(facts).map(([key, value]) => `- ${key}: ${value}`),
  ];
  writeFileSync(join(config.runDir, "PROOF.md"), lines.join("\n") + "\n");
}
