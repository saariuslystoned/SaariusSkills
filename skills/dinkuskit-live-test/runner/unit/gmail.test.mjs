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
  try { out = execFileSync(process.execPath, [script, folder, "0", "R2"], { encoding: "utf8" }); } catch (error) { out = error.stdout; status = error.status; }
  assert.equal(status, 1);
  assert.match(out, /Live journeys: FAIL/);
  assert.match(out, /\| Storefront \| PASS \|/);
  assert.match(out, /\| Cart \| FAIL \|/);
  assert.doesNotMatch(out, /private detail|#1030|Add to cart/);
});

test("the public summary names the plugin versions the store ran, and says when none were recorded", () => {
  const folder = mkdtempSync(join(tmpdir(), "summary-"));
  const script = new URL("../scripts/run-summary.mjs", import.meta.url).pathname;
  const report = { verdict: "PASS", journeys: [{ name: "Storefront", verdict: "PASS" }] };
  writeFileSync(join(folder, "report.json"), JSON.stringify({ ...report, facts: { plugins: "dinkus-commerce-beta 0.3.1-beta.2, dinkus-payments-beta 0.2.9-beta.0" } }));
  assert.match(execFileSync(process.execPath, [script, folder, "0"], { encoding: "utf8" }), /^Plugins tested: dinkus-commerce-beta 0\.3\.1-beta\.2, dinkus-payments-beta 0\.2\.9-beta\.0$/m);
  writeFileSync(join(folder, "report.json"), JSON.stringify(report));
  assert.match(execFileSync(process.execPath, [script, folder, "0"], { encoding: "utf8" }), /^Plugins tested: not recorded$/m);
});

test("when the store update stops, the summary says why and that no journey tested the plugins", () => {
  const folder = mkdtempSync(join(tmpdir(), "summary-"));
  const script = new URL("../scripts/run-summary.mjs", import.meta.url).pathname;
  writeFileSync(join(folder, "report.json"), JSON.stringify({
    verdict: "FAIL",
    journeys: [{ name: "Update the store", verdict: "FAIL" }],
    facts: { plugins: "dinkus-commerce-beta 0.3.1-beta.2", "update stopped": "dinkus-payments-beta stays on 0.2.9-beta.1, not 0.2.9-beta.2: it asks for new permissions (network:fetch)." },
  }));
  let out = "";
  try { execFileSync(process.execPath, [script, folder, "1"], { encoding: "utf8" }); } catch (error) { out = error.stdout; }
  assert.match(out, /^Update stopped: dinkus-payments-beta stays on 0\.2\.9-beta\.1, not 0\.2\.9-beta\.2: it asks for new permissions \(network:fetch\)\.$/m);
  assert.match(out, /^Plugins on the store \(no journeys ran\): dinkus-commerce-beta 0\.3\.1-beta\.2$/m);
  assert.doesNotMatch(out, /Plugins tested/);
});

test("a run that recorded nothing is a failure in the summary", () => {
  const folder = mkdtempSync(join(tmpdir(), "summary-"));
  const script = new URL("../scripts/run-summary.mjs", import.meta.url).pathname;
  assert.throws(() => execFileSync(process.execPath, [script, folder, "0"], { encoding: "utf8" }), error => error.status === 1 && /no journey recorded a result/.test(error.stdout));
});

test("a run cut off part way fails even when every journey it recorded passed", () => {
  const folder = mkdtempSync(join(tmpdir(), "summary-"));
  writeFileSync(join(folder, "report.json"), JSON.stringify({ verdict: "PASS", journeys: [{ name: "Storefront", verdict: "PASS" }] }));
  const script = new URL("../scripts/run-summary.mjs", import.meta.url).pathname;
  for (const [code, says] of [["", /was cut off/], ["1", /exited 1/]]) {
    assert.throws(() => execFileSync(process.execPath, [script, folder, code], { encoding: "utf8" }),
      error => error.status === 1 && /Live journeys: FAIL/.test(error.stdout) && says.test(error.stdout) && /\| Storefront \| PASS \|/.test(error.stdout));
  }
  assert.match(execFileSync(process.execPath, [script, folder, "0"], { encoding: "utf8" }), /Live journeys: PASS/);
});

test("one message that can't be read is skipped; only a poll with none readable fails", async () => {
  const fetcher = bad => async url => {
    if (url.includes("/messages?")) return json({ messages: [{ id: "a" }, { id: "b" }] });
    const id = url.split("/messages/")[1].split("?")[0];
    if (bad.includes(id)) return json({}, 503);
    return json({ payload: { mimeType: "text/plain", body: { data: encode(`code 48291${id === "a" ? 3 : 4}`) } } });
  };
  assert.deepEqual(await searchMail("at", "q", { fetcher: fetcher(["a"]) }), ["\ncode 482914"]);
  await assert.rejects(searchMail("at", "q", { fetcher: fetcher(["a", "b"]) }), /503/);
});
