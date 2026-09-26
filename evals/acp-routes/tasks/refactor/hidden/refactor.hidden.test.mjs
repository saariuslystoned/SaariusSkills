import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { buildReport } from "../src/report.mjs";

// Behaviour pinned from the original implementation, including odd edge cases.
const cases = [
  ["header is optional", "2026-09-01,cursor,completed,100", "| Route | Jobs | Success | Median |\n| --- | ---: | ---: | ---: |\n| cursor | 1 | 100.0% | 100 ms |"],
  ["only the first non-empty line may be a header", "\n\nDATE,route,status,durationMs\ndate,cursor,completed,5", "| Route | Jobs | Success | Median |\n| --- | ---: | ---: | ---: |\n| cursor | 1 | 100.0% | 5 ms |"],
  ["CRLF, whitespace and case", "date,route,status,durationMs\r\n 2026-09-01 , agy , COMPLETED , 2000 \r\n", "| Route | Jobs | Success | Median |\n| --- | ---: | ---: | ---: |\n| agy | 1 | 100.0% | 2.0 s |"],
  ["skips bad rows", "a,cursor,completed,\nb,cursor,completed,-1\nc,cursor,completed,abc\nd,,completed,5\ne,cursor,completed,1,extra\nf,cursor,completed", "No data."],
  ["even-count median rounds", "x,r,completed,1\nx,r,failed,2", "| Route | Jobs | Success | Median |\n| --- | ---: | ---: | ---: |\n| r | 2 | 50.0% | 2 ms |"],
  ["999.5 ms boundary", "x,r,completed,999\nx,r,completed,1000", "| Route | Jobs | Success | Median |\n| --- | ---: | ---: | ---: |\n| r | 2 | 100.0% | 1.0 s |"],
  ["routes sort by code point", "x,b,completed,1\nx,B,completed,1\nx,a,completed,1", "| Route | Jobs | Success | Median |\n| --- | ---: | ---: | ---: |\n| B | 1 | 100.0% | 1 ms |\n| a | 1 | 100.0% | 1 ms |\n| b | 1 | 100.0% | 1 ms |"],
  ["one-decimal success rate", "x,r,completed,1\nx,r,failed,1\nx,r,failed,1", "| Route | Jobs | Success | Median |\n| --- | ---: | ---: | ---: |\n| r | 3 | 33.3% | 1 ms |"],
  ["fractional durations are kept", "x,r,completed,1.5", "| Route | Jobs | Success | Median |\n| --- | ---: | ---: | ---: |\n| r | 1 | 100.0% | 1.5 ms |"],
];
for (const [name, input, expected] of cases) test(`buildReport: ${name}`, () => assert.equal(buildReport(input), expected));

test("parseCsv returns kept rows only", async () => {
  const { parseCsv } = await import("../src/parse.mjs");
  assert.deepEqual(parseCsv("date,route,status,durationMs\n2026-09-01, cursor ,Completed,10\nbad,row\n2026-09-02,grok,failed,-5"), [
    { date: "2026-09-01", route: "cursor", status: "completed", durationMs: 10 },
  ]);
});

// The brief asks for "the same numbers the current code computes", and the
// original computes the rate as a percentage, so either a 0-1 fraction or a
// 0-100 percentage is accepted, as long as aggregate() and formatMarkdown()
// agree with each other.
const ROWS = [
  { date: "d", route: "z", status: "completed", durationMs: 10 },
  { date: "d", route: "a", status: "failed", durationMs: 4 },
  { date: "d", route: "a", status: "completed", durationMs: 1 },
];

test("aggregate computes totals, rate and median, sorted by route", async () => {
  const { aggregate } = await import("../src/aggregate.mjs");
  const out = aggregate(ROWS);
  const scale = out[1]?.successRate === 100 ? 100 : 1;
  assert.deepEqual(out, [
    { route: "a", total: 2, completed: 1, successRate: 0.5 * scale, medianMs: 3 },
    { route: "z", total: 1, completed: 1, successRate: 1 * scale, medianMs: 10 },
  ]);
});

test("formatMarkdown matches the original table for aggregate's output", async () => {
  const { aggregate } = await import("../src/aggregate.mjs");
  const { formatMarkdown } = await import("../src/format.mjs");
  assert.equal(formatMarkdown([]), "No data.");
  const one = aggregate([
    { date: "d", route: "cursor", status: "completed", durationMs: 1200 },
    { date: "d", route: "cursor", status: "failed", durationMs: 1800 },
  ]);
  assert.equal(
    formatMarkdown(one),
    "| Route | Jobs | Success | Median |\n| --- | ---: | ---: | ---: |\n| cursor | 2 | 50.0% | 1.5 s |",
  );
});

test("report.mjs is a thin composition", () => {
  const src = readFileSync(new URL("../src/report.mjs", import.meta.url), "utf8");
  assert.ok(src.trimEnd().split("\n").length <= 25, "report.mjs must be at most 25 lines");
  for (const mod of ["parse.mjs", "aggregate.mjs", "format.mjs"]) assert.match(src, new RegExp(mod.replace(".", "\\.")));
});
