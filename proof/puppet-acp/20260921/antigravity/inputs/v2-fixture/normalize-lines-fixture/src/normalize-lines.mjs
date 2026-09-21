export function normalizeLines(text) {
  return String(text).replace(/\r\n/g, "\n").replace(/[ \t]+$/gm, "");
}

export function isNormalized(text) {
  return text === normalizeLines(text);
}
