/** Text with each address's query and fragment cut off, where sign-in links, connect addresses and Ship's sign-in code carry their secret. */
export const withoutQueries = text => String(text).replace(/(https?:\/\/[^\s"'<>?#]+)[?#][^\s"'<>]*/g, "$1");

/**
 * The error as the proof may keep it. Playwright ends its own errors with a call log: for a request
 * the test sends itself, every header sent and received, the store's Cloudflare Access and
 * DinkusKit.com sign-in cookies among them; for a page load or a wait, the addresses the page went
 * to; for a click, the page's markup. A failure's proof (console.log, Playwright's report,
 * error-context.md, report.json) prints the error, so it keeps what went wrong without the call log,
 * and each address in it without its query. Returns the same error, or, when its message can't be
 * changed, a plain one with the shorter message.
 */
export function forProof(error) {
  const message = error?.message;
  if (typeof message !== "string") return error;
  const kept = withoutQueries(message.replace(/\n+Call log:\n[\s\S]*$/, ""));
  if (kept === message) return error;
  try {
    error.message = kept;
    if (typeof error.stack === "string") error.stack = error.stack.replace(message, () => kept);
    return error;
  } catch {
    return new Error(kept);
  }
}
