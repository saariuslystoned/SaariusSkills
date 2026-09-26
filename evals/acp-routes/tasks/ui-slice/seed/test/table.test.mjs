import test from "node:test";
import assert from "node:assert/strict";
import { renderTable } from "../src/table.mjs";

test("renders a table with a caption", () => {
  const html = renderTable([{ id: "a", route: "cursor", model: "m", status: "completed", durationMs: 1000 }]);
  assert.match(html, /<caption>Jobs \(1\)<\/caption>/);
});
