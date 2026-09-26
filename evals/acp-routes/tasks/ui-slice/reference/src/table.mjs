export const COLUMNS = [
  { key: "id", label: "Job" },
  { key: "route", label: "Route" },
  { key: "model", label: "Model" },
  { key: "status", label: "Status" },
  { key: "durationMs", label: "Duration", numeric: true },
];
const esc = (v) => String(v).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
const display = (col, v) => (v == null ? "" : col.key === "durationMs" ? `${(v / 1000).toFixed(1)} s` : String(v));

export function sortRows(rows, key, dir) {
  const sign = dir === "desc" ? -1 : 1;
  return rows.map((row, i) => ({ row, i })).sort((a, b) => {
    const x = a.row[key], y = b.row[key];
    const xm = x == null, ym = y == null;
    if (xm || ym) return xm === ym ? a.i - b.i : xm ? 1 : -1;
    const c = typeof x === "number" && typeof y === "number" ? x - y : String(x).localeCompare(String(y), undefined, { sensitivity: "base" });
    return c === 0 ? a.i - b.i : sign * c;
  }).map((e) => e.row);
}

export function renderTable(rows, { sortKey = null, sortDir = "asc", filter = "" } = {}) {
  const f = filter.trim().toLowerCase();
  let shown = f ? rows.filter((r) => COLUMNS.some((c) => display(c, r[c.key]).toLowerCase().includes(f))) : rows;
  if (sortKey) shown = sortRows(shown, sortKey, sortDir);
  const head = COLUMNS.map((c) => {
    const sort = c.key === sortKey ? (sortDir === "desc" ? "descending" : "ascending") : "none";
    return `<th scope="col" aria-sort="${sort}"${c.numeric ? ' class="num"' : ""}><button type="button" data-sort-key="${c.key}">${esc(c.label)}</button></th>`;
  }).join("");
  const body = shown.length
    ? shown.map((r) => `<tr>${COLUMNS.map((c) => `<td${c.numeric ? ' class="num"' : ""}>${esc(display(c, r[c.key]))}</td>`).join("")}</tr>`).join("")
    : '<tr><td colspan="5">No matching jobs</td></tr>';
  return `<table class="jobs"><caption>Jobs (${shown.length})</caption><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
}
