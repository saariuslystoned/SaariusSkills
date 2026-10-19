import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { accessToken, messageText, searchMail } from "../support/gmail.mjs";
import { clean, extract } from "../support/mail-patterns.mjs";

const encode = text => Buffer.from(text).toString("base64url");
const json = (body, status = 200) => ({ ok: status < 300, status, json: async () => body });

test("a Gmail message's subject and every text and HTML part are decoded", () => {
  const message = { payload: {
    headers: [{ name: "Subject", value: "Sign in to DinkusKit" }],
    mimeType: "multipart/alternative",
    parts: [
      { mimeType: "text/plain", body: { data: encode("Open https://dinkuskit.com/api/auth/magic-link/verify?token=tok_1") } },
      { mimeType: "text/html", body: { data: encode("<p>Your login code is 482913</p>") } },
      { mimeType: "image/png", body: { data: encode("not text") } },
    ],
  } };
  const text = messageText(message);
  assert.match(text, /^Sign in to DinkusKit\n/);
  assert.deepEqual(extract.dinkuskit(clean(text)), ["https://dinkuskit.com/api/auth/magic-link/verify?token=tok_1"]);
  assert.deepEqual(extract.access(clean(text)), ["482913"]);
  assert.doesNotMatch(text, /not text/);
});

test("the inbox key is traded for an access token, and a refusal names Google's error only", async () => {
  const calls = [];
  const token = await accessToken({ clientId: "id", clientSecret: "shh", refreshToken: "rt" }, async (url, options) => {
    calls.push({ url, body: String(options.body) });
    return json({ access_token: "at" });
  });
  assert.equal(token, "at");
  assert.equal(calls[0].url, "https://oauth2.googleapis.com/token");
  assert.match(calls[0].body, /grant_type=refresh_token/);
  await assert.rejects(accessToken({ clientId: "id", clientSecret: "shh", refreshToken: "rt" }, async () => json({ error: "invalid_grant" }, 400)),
    error => /400 invalid_grant/.test(error.message) && !/shh|rt\b/.test(error.message));
});

test("a search reads the newest matches in Gmail's order, with read-only calls only", async () => {
  const seen = [];
  const fetcher = async (url, options) => {
    seen.push({ url, method: options.method ?? "GET" });
    if (url.includes("/messages?")) return json({ messages: [{ id: "new" }, { id: "old" }] });
    const id = url.split("/messages/")[1].split("?")[0];
    return json({ payload: { headers: [{ name: "Subject", value: id }], mimeType: "text/plain", body: { data: encode(`body ${id}`) } } });
  };
  const texts = await searchMail("at", 'from:accounts@dinkuskit.com newer_than:1h', { fetcher });
  assert.deepEqual(texts, ["new\nbody new", "old\nbody old"]);
  assert.ok(seen.every(call => call.method === "GET"));
  assert.equal(new URL(seen[0].url).searchParams.get("q"), "from:accounts@dinkuskit.com newer_than:1h");
  assert.equal(new URL(seen[0].url).searchParams.get("maxResults"), "3");
});

test("the public summary shows each journey's pass or fail and nothing from its steps", () => {
  const folder = mkdtempSync(join(tmpdir(), "summary-"));
  writeFileSync(join(folder, "report.json"), JSON.stringify({
    verdict: "FAIL",
    journeys: [{ name: "Storefront", verdict: "PASS" }, { name: "Cart", verdict: "FAIL" }],
    steps: [{ journey: "Cart", step: "Add to cart", status: "FAIL", detail: "private detail" }],
    facts: { order: "#1030" },
  }));
  const script = new URL("../scripts/run-summary.mjs", import.meta.url).pathname;
  let out = "", status = 0;
  try { out = execFileSync(process.execPath, [script, folder, "R2"], { encoding: "utf8" }); } catch (error) { out = error.stdout; status = error.status; }
  assert.equal(status, 1);
  assert.match(out, /Live journeys: FAIL/);
  assert.match(out, /\| Storefront \| PASS \|/);
  assert.match(out, /\| Cart \| FAIL \|/);
  assert.doesNotMatch(out, /private detail|#1030|Add to cart/);
});

test("a run that recorded nothing is a failure in the summary", () => {
  const folder = mkdtempSync(join(tmpdir(), "summary-"));
  const script = new URL("../scripts/run-summary.mjs", import.meta.url).pathname;
  assert.throws(() => execFileSync(process.execPath, [script, folder], { encoding: "utf8" }), error => error.status === 1 && /no journey recorded a result/.test(error.stdout));
});
