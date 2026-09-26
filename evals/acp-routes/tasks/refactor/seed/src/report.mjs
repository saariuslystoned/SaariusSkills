// Turns CSV job logs (date,route,status,durationMs) into a Markdown summary.
export function buildReport(text) {
  var lines = String(text).split(/\r?\n/);
  var byRoute = {};
  var first = true;
  for (var i = 0; i < lines.length; i++) {
    var line = lines[i];
    if (line.trim() === "") continue;
    if (first) {
      first = false;
      if (line.trim().toLowerCase().indexOf("date") === 0) continue;
    }
    var parts = line.split(",");
    if (parts.length !== 4) continue;
    for (var j = 0; j < parts.length; j++) parts[j] = parts[j].trim();
    var d = Number(parts[3]);
    if (parts[3] === "" || !isFinite(d) || d < 0) continue;
    var route = parts[1];
    if (route === "") continue;
    var status = parts[2].toLowerCase();
    if (!byRoute[route]) byRoute[route] = { total: 0, completed: 0, durations: [] };
    byRoute[route].total++;
    if (status === "completed") byRoute[route].completed++;
    byRoute[route].durations.push(d);
  }
  var names = Object.keys(byRoute).sort();
  if (names.length === 0) return "No data.";
  var out = "| Route | Jobs | Success | Median |\n| --- | ---: | ---: | ---: |";
  for (var k = 0; k < names.length; k++) {
    var r = byRoute[names[k]];
    var ds = r.durations.slice().sort(function (a, b) { return a - b; });
    var mid = Math.floor(ds.length / 2);
    var median = ds.length % 2 ? ds[mid] : Math.round((ds[mid - 1] + ds[mid]) / 2);
    var rate = (r.completed / r.total) * 100;
    var medianText = median < 1000 ? median + " ms" : (median / 1000).toFixed(1) + " s";
    out += "\n| " + names[k] + " | " + r.total + " | " + rate.toFixed(1) + "% | " + medianText + " |";
  }
  return out;
}
