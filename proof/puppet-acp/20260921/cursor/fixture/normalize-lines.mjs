/**
 * Disposable proof fixture. Intentionally broken baseline:
 * CRLF becomes LF, but lone CR is left unchanged.
 * A later worker may fix only this file. Do not edit the tests.
 */
export function normalizeLines(text) {
  return String(text).replace(/\r\n/g, "\n");
}
