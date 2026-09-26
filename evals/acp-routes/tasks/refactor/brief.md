Refactor `src/report.mjs` without changing its behaviour. It turns CSV job logs into a Markdown summary table, and today everything is tangled into one function.

Split it into three modules:
- `src/parse.mjs` exporting `parseCsv(text)`: returns an array of row objects `{ date, route, status, durationMs }` with exactly the rows the current code keeps.
- `src/aggregate.mjs` exporting `aggregate(rows)`: returns an array of `{ route, total, completed, successRate, medianMs }`, sorted by route, with the same numbers the current code computes.
- `src/format.mjs` exporting `formatMarkdown(aggregates)`: returns exactly the string the current code produces for those aggregates.

`src/report.mjs` must keep exporting `buildReport(text)` with identical output for every input, implemented by composing the three modules, and must be at most 25 lines long.

Preserve every existing edge-case behaviour, even ones that look odd. Use only the standard library. Do not change the files under `test/` or `package.json`. Run `node --test` before you finish. Do not commit.
