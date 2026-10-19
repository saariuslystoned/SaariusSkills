// Reads the test inbox through the Gmail API with a read-only key, for computers without gogcli,
// such as a GitHub runner. Nothing here can send, change or delete mail: the key only has
// Gmail's read-only scope.

export const GMAIL_READONLY = "https://www.googleapis.com/auth/gmail.readonly";
const API = "https://gmail.googleapis.com/gmail/v1/users/me";
const TOKEN = "https://oauth2.googleapis.com/token";

/** Trades the saved refresh token for a short-lived access token. */
export async function accessToken({ clientId, clientSecret, refreshToken }, fetcher = fetch) {
  const response = await fetcher(TOKEN, {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ client_id: clientId, client_secret: clientSecret, refresh_token: refreshToken, grant_type: "refresh_token" }),
    redirect: "manual",
  });
  const body = await response.json().catch(() => ({}));
  // Google's error names say what to fix (invalid_grant: the key was revoked or expired) and carry no secret.
  if (!response.ok || !body.access_token) throw new Error(`Google refused the inbox key (${response.status} ${body.error ?? "no access token"}).`);
  return body.access_token;
}

/** The newest messages matching a Gmail search, newest first, as plain text a sign-in pattern can read. */
export async function searchMail(token, query, { max = 3, fetcher = fetch } = {}) {
  const get = async path => {
    const response = await fetcher(`${API}${path}`, { headers: { authorization: `Bearer ${token}` }, redirect: "manual" });
    if (!response.ok) throw new Error(`Gmail answered ${response.status} for ${path.split("?")[0]}.`);
    return response.json();
  };
  const list = await get(`/messages?${new URLSearchParams({ q: query, maxResults: String(max) })}`);
  const texts = [];
  let lastError;
  // As gogcli's script does, a message that can't be read is skipped, so the others still count.
  for (const { id } of list.messages ?? []) {
    try { texts.push(messageText(await get(`/messages/${encodeURIComponent(id)}?format=full`))); } catch (error) { lastError = error; }
  }
  if (lastError && !texts.length) throw lastError;
  return texts;
}

/** A message's subject and every text or HTML body part, decoded. */
export function messageText(message) {
  const headers = message.payload?.headers ?? [];
  const subject = headers.find(header => header.name.toLowerCase() === "subject")?.value ?? "";
  const parts = [];
  const walk = part => {
    if (!part) return;
    if (/^text\/(plain|html)$/i.test(part.mimeType ?? "") && part.body?.data) parts.push(Buffer.from(part.body.data, "base64url").toString("utf8"));
    for (const child of part.parts ?? []) walk(child);
  };
  walk(message.payload);
  return [subject, ...parts].join("\n");
}
