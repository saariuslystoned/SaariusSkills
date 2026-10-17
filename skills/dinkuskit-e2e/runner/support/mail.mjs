import { execFileSync } from "node:child_process";
import { config } from "./env.mjs";

/** What each sign-in email looks like, and what to pull out of it. */
export const MAIL = {
  dinkuskit: {
    query: "from:accounts@dinkuskit.com subject:\"Sign in to DinkusKit\" newer_than:1h",
    // Better Auth's magic link; the token is single use and expires after 5 minutes.
    pattern: /https:\/\/dinkuskit\.com\/[^\s"'<>)\]]*(?:magic-link|verify)[^\s"'<>)\]]*/g,
  },
};

const sleep = ms => new Promise(done => setTimeout(done, ms));

/** Undoes the encodings a mail body may still carry (HTML entities, quoted-printable). */
function clean(text) {
  return text.replace(/=\r?\n/g, "").replace(/=3D/gi, "=").replaceAll("&amp;", "&");
}

/** Runs the mail command for one kind of email and returns every match, newest first. */
export function readMail(kind) {
  if (!config.mailCmd) return [];
  const { query, pattern } = MAIL[kind];
  const out = execFileSync("/bin/bash", ["-lc", config.mailCmd], {
    env: { ...process.env, DINKUS_MAIL_QUERY: query, DINKUS_MAIL_KIND: kind },
    encoding: "utf8", timeout: 60_000, maxBuffer: 8 * 1024 * 1024,
  });
  return [...clean(out).matchAll(pattern)].map(match => match[1] ?? match[0]);
}

/** Matches already in the mailbox before the email is requested, so an old link is never reused. */
export function mailBaseline(kind) {
  try { return new Set(readMail(kind)); } catch { return new Set(); }
}

/** Waits for a new link or code of this kind. Returns null when no mail command is set (a person signs in instead). */
export async function waitForMail(kind, baseline, timeoutMs = 180_000) {
  if (!config.mailCmd) return null;
  const deadline = Date.now() + timeoutMs;
  let lastError;
  while (Date.now() < deadline) {
    await sleep(8_000);
    try {
      const fresh = readMail(kind).find(value => !baseline.has(value));
      if (fresh) return fresh;
    } catch (error) { lastError = error; }
  }
  throw new Error(`No new ${kind} email arrived within ${timeoutMs / 1000}s${lastError ? ` (mail command: ${lastError.message.split("\n")[0]})` : ""}.`);
}
