const all = (text, pattern) => [...text.matchAll(pattern)].map(match => match[1] ?? match[0]);

/** How to pull the link or code out of each sign-in email, newest first. */
export const extract = {
  // Better Auth's magic link; the token is single use and expires after 5 minutes.
  dinkuskit: text => all(text, /https:\/\/dinkuskit\.com\/[^\s"'<>)\]]*(?:magic-link|verify)[^\s"'<>)\]]*/g),
  // Cloudflare Access's one-time PIN: the six digits after "code" or "PIN"; failing that,
  // any six digits standing alone (never a #333333 colour or part of a longer number).
  access: text => {
    const worded = all(text, /\b(?:code|PIN)\b[^0-9#]{0,120}?(?<![\w#=-])(\d{6})(?![\w-])/gi);
    return worded.length ? worded : all(text, /(?<![\w#=-])(\d{6})(?![\w-])/g);
  },
};

/**
 * The search for Cloudflare Access's code emails from the last hour. It names the store's host, as each code email
 * does, so a run never types a code another store sent to the same test inbox.
 */
export const accessQuery = store => `from:(notify.cloudflare.com OR cloudflareaccess.com) newer_than:1h${store ? ` "${new URL(store).hostname}"` : ""}`;

/** Undoes the encodings a mail body may still carry (HTML entities, quoted-printable). */
export function clean(text) {
  return text.replace(/=\r?\n/g, "").replace(/=3D/gi, "=").replaceAll("&amp;", "&");
}
