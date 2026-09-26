/**
 * COLUMNS = [
 *   { key: "id", label: "Job" }, { key: "route", label: "Route" },
 *   { key: "model", label: "Model" }, { key: "status", label: "Status" },
 *   { key: "durationMs", label: "Duration", numeric: true },
 * ]  (export this constant)
 *
 * sortRows(rows, key, dir)
 *   - Returns a NEW array; never mutates `rows`.
 *   - dir is "asc" or "desc". Numbers compare numerically; everything else
 *     compares as strings with localeCompare (base sensitivity, so case-insensitive).
 *   - Stable: rows that compare equal keep their original relative order in
 *     BOTH directions.
 *   - Missing values (undefined/null) always sort last, in both directions.
 *
 * renderTable(rows, { sortKey = null, sortDir = "asc", filter = "" } = {})
 *   - Returns an HTML string for one <table class="jobs">.
 *   - First child is <caption>Jobs (N)</caption> where N is the number of rows
 *     shown after filtering.
 *   - <thead> has one <th scope="col"> per column, in COLUMNS order. Each th has
 *     aria-sort="ascending" / "descending" on the sorted column and
 *     aria-sort="none" on the others, and contains
 *     <button type="button" data-sort-key="KEY">LABEL</button>.
 *   - Numeric columns' th and td elements carry class="num".
 *   - Filtering: case-insensitive substring match against every column's
 *     displayed value; an empty or whitespace-only filter shows everything.
 *   - Duration cells display seconds with one decimal and an "s" suffix
 *     (224600 -> "224.6 s"). Filtering matches this displayed text.
 *   - When no rows remain, <tbody> contains exactly one
 *     <tr><td colspan="5">No matching jobs</td></tr>.
 *   - Every value from `rows` must be HTML-escaped (& < > " ').
 */
export const COLUMNS = [];
export function sortRows(rows, key, dir) { throw new Error("not implemented"); }
export function renderTable(rows, options) { throw new Error("not implemented"); }
