export function aggregate(rows) {
  const byRoute = new Map();
  for (const r of rows) {
    if (!byRoute.has(r.route)) byRoute.set(r.route, { total: 0, completed: 0, durations: [] });
    const g = byRoute.get(r.route);
    g.total++;
    if (r.status === "completed") g.completed++;
    g.durations.push(r.durationMs);
  }
  return [...byRoute.keys()].sort().map((route) => {
    const g = byRoute.get(route);
    const ds = [...g.durations].sort((a, b) => a - b);
    const mid = Math.floor(ds.length / 2);
    const medianMs = ds.length % 2 ? ds[mid] : Math.round((ds[mid - 1] + ds[mid]) / 2);
    return { route, total: g.total, completed: g.completed, successRate: g.completed / g.total, medianMs };
  });
}
