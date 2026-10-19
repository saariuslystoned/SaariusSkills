#!/usr/bin/env node
// Makes the test inbox's read-only Gmail key once and saves it straight into the repository's
// Actions secrets, so the "Live journeys" workflow can read sign-in emails without a Mac.
//
//   node scripts/gmail-authorize.mjs <client_secret.json> <inbox address> [owner/repo]
//
// The JSON is a Google OAuth client of type "Desktop app". A browser opens; sign in as the inbox
// and allow read-only access. Nothing secret is printed: the key goes to `gh secret set` on stdin.
import { execFileSync } from "node:child_process";
import { createHash, randomBytes } from "node:crypto";
import { readFileSync } from "node:fs";
import { createServer } from "node:http";
import { GMAIL_READONLY } from "../support/gmail.mjs";

const [file, inbox, repo = "saariuslystoned/SaariusSkills"] = process.argv.slice(2);
if (!file || !inbox) {
  console.error("Usage: node scripts/gmail-authorize.mjs <client_secret.json> <inbox address> [owner/repo]");
  process.exit(2);
}
const { installed } = JSON.parse(readFileSync(file, "utf8"));
if (!installed?.client_id || !installed?.client_secret) throw new Error(`${file} is not a "Desktop app" OAuth client.`);

const verifier = randomBytes(32).toString("base64url");
const state = randomBytes(16).toString("base64url");
let redirect;
const code = await new Promise((resolve, reject) => {
  const server = createServer((request, response) => {
    const url = new URL(request.url, "http://127.0.0.1");
    if (url.pathname !== "/") { response.writeHead(404).end(); return; }
    const error = url.searchParams.get("error");
    const ok = !error && url.searchParams.get("state") === state && url.searchParams.get("code");
    response.writeHead(ok ? 200 : 400, { "content-type": "text/plain" }).end(ok ? "Done. You can close this tab." : "Sign-in was not completed.");
    server.close();
    ok ? resolve(url.searchParams.get("code")) : reject(new Error(`Google sign-in failed (${error ?? "state mismatch"}).`));
  });
  server.listen(0, "127.0.0.1", () => {
    redirect = `http://127.0.0.1:${server.address().port}`;
    const auth = new URL("https://accounts.google.com/o/oauth2/v2/auth");
    auth.search = new URLSearchParams({
      client_id: installed.client_id, redirect_uri: redirect, response_type: "code", scope: GMAIL_READONLY,
      access_type: "offline", prompt: "consent", login_hint: inbox, state,
      code_challenge: createHash("sha256").update(verifier).digest("base64url"), code_challenge_method: "S256",
    });
    console.log(`Opening Google sign-in for ${inbox}. If no browser opens, visit:\n${auth}\n`);
    try { execFileSync(process.platform === "darwin" ? "open" : "xdg-open", [auth.href], { stdio: "ignore" }); } catch {}
  });
});

const response = await fetch("https://oauth2.googleapis.com/token", {
  method: "POST",
  headers: { "content-type": "application/x-www-form-urlencoded" },
  body: new URLSearchParams({ client_id: installed.client_id, client_secret: installed.client_secret, code, code_verifier: verifier, redirect_uri: redirect, grant_type: "authorization_code" }),
});
const tokens = await response.json();
if (!response.ok || !tokens.refresh_token) throw new Error(`Google gave no refresh token (${tokens.error ?? response.status}).`);
// Read-only and nothing else, so the saved key can never send, change or delete mail.
if (String(tokens.scope ?? "").split(" ").some(scope => scope !== GMAIL_READONLY)) throw new Error(`Google granted more than read-only access (${tokens.scope}). Nothing was saved.`);

// The key must belong to the test inbox, never another account the browser happened to be signed in to.
const profile = await (await fetch("https://gmail.googleapis.com/gmail/v1/users/me/profile", { headers: { authorization: `Bearer ${tokens.access_token}` } })).json();
if (String(profile.emailAddress).toLowerCase() !== inbox.toLowerCase()) throw new Error(`Signed in as ${profile.emailAddress}, not ${inbox}. Nothing was saved.`);

const secrets = {
  DINKUS_E2E_GMAIL_CLIENT_ID: installed.client_id,
  DINKUS_E2E_GMAIL_CLIENT_SECRET: installed.client_secret,
  DINKUS_E2E_GMAIL_REFRESH_TOKEN: tokens.refresh_token,
  DINKUS_E2E_OWNER_EMAIL: profile.emailAddress,
};
for (const [name, value] of Object.entries(secrets)) {
  execFileSync("gh", ["secret", "set", name, "--repo", repo], { input: value, stdio: ["pipe", "ignore", "inherit"] });
  console.log(`Saved ${name} in ${repo}.`);
}
