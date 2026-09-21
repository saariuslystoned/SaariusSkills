#!/usr/bin/env node
import { readFileSync } from "node:fs";
import { isNormalized } from "../src/normalize-lines.mjs";

const check = process.argv.includes("--check");
const input = readFileSync(0, "utf8");
if (!check) {
  process.stderr.write("normalize-lines fixture supports --check only\n");
  process.exit(2);
}
if (isNormalized(input)) {
  process.stdout.write("OK\n");
  process.exit(0);
}
process.stdout.write("NON_NORMALIZED\n");
process.exit(1);
