import test from "node:test";
import assert from "node:assert/strict";
import { buildReport } from "../src/report.mjs";

test("summarises routes", () => {
  const csv = "date,route,status,durationMs\n2026-09-01,cursor,completed,1200\n2026-09-01,cursor,failed,1800\n2026-09-02,grok,completed,800\n";
  assert.equal(
    buildReport(csv),
    "| Route | Jobs | Success | Median |\n| --- | ---: | ---: | ---: |\n| cursor | 2 | 50.0% | 1.5 s |\n| grok | 1 | 100.0% | 800 ms |",
  );
});

test("empty input", () => assert.equal(buildReport(""), "No data."));
