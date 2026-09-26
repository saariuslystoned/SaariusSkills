import test from "node:test";
import assert from "node:assert/strict";
import { COLUMNS, renderTable, sortRows } from "../src/table.mjs";

const rows = [
  { id: "a1", route: "cursor", model: "grok-4.6", status: "completed", durationMs: 224600 },
  { id: "b2", route: "Antigravity", model: "gemini-3.8-flash-high", status: "failed", durationMs: 81000 },
  { id: "c3", route: "grok", model: "grok-4.7", status: "completed", durationMs: 26600 },
];
const ths = (html) => [...html.matchAll(/<th\b[^>]*>/g)].map((m) => m[0]);

test("COLUMNS are exported in order", () => {
  assert.deepEqual(COLUMNS.map((c) => c.key), ["id", "route", "model", "status", "durationMs"]);
  assert.equal(COLUMNS.find((c) => c.key === "durationMs").numeric, true);
});
test("sortRows numeric asc/desc and immutability", () => {
  const copy = structuredClone(rows);
  assert.deepEqual(sortRows(rows, "durationMs", "asc").map((r) => r.id), ["c3", "b2", "a1"]);
  assert.deepEqual(sortRows(rows, "durationMs", "desc").map((r) => r.id), ["a1", "b2", "c3"]);
  assert.deepEqual(rows, copy);
});
test("sortRows string compare is case-insensitive", () => {
  assert.deepEqual(sortRows(rows, "route", "asc").map((r) => r.id), ["b2", "a1", "c3"]);
});
test("sortRows is stable in both directions", () => {
  const eq = [{ id: "x", status: "done" }, { id: "y", status: "done" }, { id: "z", status: "done" }];
  assert.deepEqual(sortRows(eq, "status", "asc").map((r) => r.id), ["x", "y", "z"]);
  assert.deepEqual(sortRows(eq, "status", "desc").map((r) => r.id), ["x", "y", "z"]);
});
test("missing values sort last in both directions", () => {
  const m = [{ id: "n", durationMs: null }, { id: "a", durationMs: 5 }, { id: "u" }, { id: "b", durationMs: 1 }];
  assert.deepEqual(sortRows(m, "durationMs", "asc").map((r) => r.id).slice(0, 2), ["b", "a"]);
  assert.deepEqual(sortRows(m, "durationMs", "desc").map((r) => r.id).slice(0, 2), ["a", "b"]);
});
test("thead has scoped headers with sort buttons and aria-sort", () => {
  const html = renderTable(rows, { sortKey: "durationMs", sortDir: "desc" });
  const heads = ths(html);
  assert.equal(heads.length, 5);
  for (const th of heads) assert.match(th, /scope="col"/);
  assert.equal(heads.filter((t) => /aria-sort="descending"/.test(t)).length, 1);
  assert.equal(heads.filter((t) => /aria-sort="none"/.test(t)).length, 4);
  assert.match(heads[4], /aria-sort="descending"/);
  for (const c of COLUMNS) assert.match(html, new RegExp(`<button type="button" data-sort-key="${c.key}">`));
});
test("sorted output follows sortKey and sortDir", () => {
  const html = renderTable(rows, { sortKey: "durationMs", sortDir: "asc" });
  assert.ok(html.indexOf("c3") < html.indexOf("b2") && html.indexOf("b2") < html.indexOf("a1"));
});
test("numeric column cells carry class num", () => {
  const html = renderTable(rows);
  assert.match(ths(html)[4], /class="num"/);
  assert.equal([...html.matchAll(/<td\b[^>]*class="num"[^>]*>/g)].length, 3);
});
test("duration displays seconds with one decimal", () => {
  const html = renderTable(rows);
  assert.match(html, /224\.6 s/);
  assert.match(html, /26\.6 s/);
});
test("filter is case-insensitive across columns and updates caption", () => {
  const html = renderTable(rows, { filter: "GROK" });
  assert.match(html, /<caption>Jobs \(2\)<\/caption>/);
  assert.doesNotMatch(html, /b2/);
  assert.match(renderTable(rows, { filter: "81.0 s" }), /<caption>Jobs \(1\)<\/caption>/);
  assert.match(renderTable(rows, { filter: "   " }), /<caption>Jobs \(3\)<\/caption>/);
});
test("empty result renders one message row", () => {
  const html = renderTable(rows, { filter: "nothing-matches" });
  assert.match(html, /<caption>Jobs \(0\)<\/caption>/);
  assert.match(html, /<tbody>\s*<tr>\s*<td colspan="5">No matching jobs<\/td>\s*<\/tr>\s*<\/tbody>/);
});
test("escapes all five characters", () => {
  const html = renderTable([{ id: `<img src=x onerror="alert('1')">&`, route: "r", model: "m", status: "s", durationMs: 1 }]);
  assert.doesNotMatch(html, /<img/);
  assert.match(html, /&lt;img src=x onerror=&quot;alert\(&#39;1&#39;\)&quot;&gt;&amp;/);
});
