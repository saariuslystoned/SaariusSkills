/**
 * Reads the runner's settings file: one KEY=value per line, # comments, an optional
 * `export` and optional quotes. Only DINKUS_E2E_ keys are taken, so the file can never
 * change PATH, NODE_OPTIONS or anything else the run depends on.
 */
export function parseSettings(text) {
  const settings = {};
  for (const raw of text.split(/\r?\n/)) {
    const match = raw.trim().match(/^(?:export\s+)?(DINKUS_E2E_[A-Z0-9_]+)\s*=\s*(.*)$/);
    if (!match) continue;
    const value = match[2].trim();
    settings[match[1]] = /^(["']).*\1$/.test(value) ? value.slice(1, -1) : value;
  }
  return settings;
}
