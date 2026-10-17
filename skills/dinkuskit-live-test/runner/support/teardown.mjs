import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { config } from "./env.mjs";

/** Prints the run's verdict last, after every journey has finished. */
export default async function teardown() {
  const file = join(config.runDir, "report.json");
  if (!existsSync(file)) return;
  const report = JSON.parse(readFileSync(file, "utf8"));
  console.log(`\n${report.journeys.map(entry => `${entry.name}: ${entry.verdict}`).join("\n")}`);
  console.log(`Verdict: ${report.verdict}. Proof: ${config.runDir}/PROOF.md\n`);
}
