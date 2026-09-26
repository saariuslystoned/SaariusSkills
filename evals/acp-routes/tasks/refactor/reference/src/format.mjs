export function formatMarkdown(aggregates) {
  if (aggregates.length === 0) return "No data.";
  const lines = ["| Route | Jobs | Success | Median |", "| --- | ---: | ---: | ---: |"];
  for (const a of aggregates) {
    const median = a.medianMs < 1000 ? `${a.medianMs} ms` : `${(a.medianMs / 1000).toFixed(1)} s`;
    lines.push(`| ${a.route} | ${a.total} | ${(a.successRate * 100).toFixed(1)}% | ${median} |`);
  }
  return lines.join("\n");
}
