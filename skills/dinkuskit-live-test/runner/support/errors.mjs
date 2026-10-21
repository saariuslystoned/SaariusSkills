/**
 * The error without the call log Playwright adds to its own. For a request the test sends itself the
 * log lists every header sent and received, the store's Cloudflare Access and DinkusKit.com sign-in
 * cookies among them; for a page load or a wait, the addresses the page went to; for a click, the
 * page's markup. A failure's proof (console.log, Playwright's report, error-context.md) prints the
 * error whole, so the run keeps only what Playwright says went wrong. Returns the same error, or,
 * when its message can't be changed, a plain one with the shorter message.
 */
export function withoutCallLog(error) {
  const message = error?.message;
  if (typeof message !== "string") return error;
  const kept = message.replace(/\n+Call log:\n[\s\S]*$/, "");
  if (kept === message) return error;
  try {
    error.message = kept;
    if (typeof error.stack === "string") error.stack = error.stack.replace(message, () => kept);
    return error;
  } catch {
    return new Error(kept);
  }
}

/** An error's first line, each address in it cut to its site: for an emailed sign-in link, the address is the sign-in. */
export function siteOnlyReason(error) {
  return String(error?.message ?? error).split("\n")[0]
    .replace(/https?:\/\/[^\s"'<>]+/g, address => { try { return new URL(address).origin; } catch { return "an address"; } });
}
