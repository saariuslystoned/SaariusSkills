#!/usr/bin/env node
import { readFileSync } from "node:fs";
import { isNormalized, normalizeLines } from "../src/normalize-lines.mjs";

const input = readFileSync(0, "utf8");

if (process.argv.slice(2).includes("--check")) {
  if (isNormalized(input)) {
    console.log("OK");
    process.exitCode = 0;
  } else {
    console.log("NON_NORMALIZED");
    process.exitCode = 1;
  }
} else {
  process.stdout.write(normalizeLines(input));
}
