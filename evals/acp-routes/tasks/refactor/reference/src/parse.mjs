export function parseCsv(text) {
  const rows = [];
  let first = true;
  for (const line of String(text).split(/\r?\n/)) {
    if (line.trim() === "") continue;
    if (first) {
      first = false;
      if (line.trim().toLowerCase().startsWith("date")) continue;
    }
    const parts = line.split(",").map((p) => p.trim());
    if (parts.length !== 4) continue;
    const durationMs = Number(parts[3]);
    if (parts[3] === "" || !Number.isFinite(durationMs) || durationMs < 0 || parts[1] === "") continue;
    rows.push({ date: parts[0], route: parts[1], status: parts[2].toLowerCase(), durationMs });
  }
  return rows;
}
