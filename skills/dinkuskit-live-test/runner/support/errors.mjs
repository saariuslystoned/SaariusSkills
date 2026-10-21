/**
 * Text with each address's query and fragment cut off, where sign-in links, connect addresses and
 * Ship's sign-in code carry their secret, whether the address is whole or starts at the site's root
 * (as a link's markup gives it), and with the token cut from a Ship print link, which carries it in
 * the path.
 */
export const withoutQueries = text => String(text)
  .replace(/(https?:\/\/[^\s"'<>?#]+|(?<![^\s"'(=])\/[^\s"'<>?#]*)[?#][^\s"'<>]*/g, "$1")
  .replace(/(\/print\/)[^\s"'<>?#]+/g, "$1");

/**
 * What the proof keeps of a failure, or of anything else thrown: its first line with words on it, without
 * the terminal colours Playwright's assertions use or any address's query.
 */
export const firstLine = error => withoutQueries(String(error?.message ?? error).replace(/\u001b\[[0-9;]*m/g, "").split("\n").find(line => line.trim()) ?? "");

/**
 * The error as the proof may keep it: its first line and nothing else. Playwright puts what went wrong
 * on that line, and below it lists what it saw: for a request the test sends itself, every header sent
 * and received, the store's Cloudflare Access and DinkusKit.com sign-in cookies among them; for a page
 * load or a wait, the addresses the page went to; each element a locator matched, links included; what
 * an assertion expected and received. A failed assertion also carries a snapshot of the page, with its
 * links and what its fields hold, and an error can carry its cause. A failure's proof (console.log,
 * Playwright's report, error-context.md, report.json) prints the error, so all of that goes, and the
 * first line loses each address's query. Returns the same error, or, when it can't be changed, a copy
 * of the same kind.
 */
export function forProof(error) {
  if (Object(error) !== error || typeof error.message !== "string") return error;
  const kept = firstLine(error);
  if (kept === error.message && !("matcherResult" in error) && !("cause" in error)) return error;
  // As Playwright rewrites its own errors: the stack keeps its frames and takes the new message, so the
  // old one doesn't stay behind in it.
  const frames = String(error.stack ?? "").split("\n").filter(line => line.startsWith("    at "));
  const stack = [`${error.name}: ${kept}`, ...frames].join("\n");
  try {
    error.message = kept;
    error.stack = stack;
    delete error.matcherResult;
    delete error.cause;
    return error;
  } catch {
    const { matcherResult, cause, ...own } = error;
    return Object.assign(Object.setPrototypeOf(new Error(kept), Object.getPrototypeOf(error)), own, { name: error.name, stack });
  }
}
