#!/usr/bin/env node
// Prints the public part of a run's result: each journey and pass or fail, nothing else. The steps,
// screenshots and console output stay in the private proof.
//
//   node scripts/run-summary.mjs <proof folder> [where the private proof went]
import { readFileSync } from "node:fs";
import { join } from "node:path";

const [folder, proof = "the private proof store"] = process.argv.slice(2);
let report;
try { report = JSON.parse(readFileSync(join(folder, "report.json"), "utf8")); } catch { report = null; }
const journeys = report?.journeys ?? [];
const verdict = journeys.length ? report.verdict : "FAIL";
const lines = [
  `## Live journeys: ${verdict}`, "",
  "| Journey | Pass / fail |", "| --- | --- |",
  ...(journeys.length ? journeys.map(({ name, verdict }) => `| ${name} | ${verdict} |`) : ["| Test run | FAIL: no journey recorded a result |"]),
  "", `Steps, screenshots and console output: ${proof}.`,
];
console.log(lines.join("\n"));
process.exit(verdict === "PASS" ? 0 : 1);
