export function normalizeLines(text) {
  return text
    .split(/\r?\n/)
    .map((line) => line.replace(/[ \t]+$/, ''))
    .filter((line) => line.trim() !== '')
    .join('\n');
}
