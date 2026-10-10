import assert from "node:assert/strict";
import test from "node:test";
import { checkBatch, evaluate, HOSTED_ENDPOINT, resolveRoute } from "../client.mjs";

const KEY = "ts_test_not_a_real_key_0000";
const hosted = { kind: "typesafe-hosted", endpoint: HOSTED_ENDPOINT, model: "jev-latest", apiKey: KEY, timeoutMs: 2_000 };

const leftover = {
  state: { box: "Accept public guest POSTs to /checkout", locked: "Guest checkout is locked public." },
  questions: {
    box1: {
      type: "choice",
      instructions: "Label this leftover review box.",
      criteria: {
        repair: "The agent can fix it with code, tests or proof.",
        "owner-gate": "Only the owner can accept it.",
        "do-not-patch": "Fixing it would reverse a locked owner decision.",
      },
    },
  },
};

function fakeFetch(respond) {
  const calls = [];
  const impl = async (url, init) => {
    calls.push({ url, init, body: JSON.parse(init.body) });
    return respond(url, init);
  };
  return { impl, calls };
}

const json = (status, body) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

test("choice answer comes back in OpenClaw's shape with provenance", async () => {
  const { impl, calls } = fakeFetch(() =>
    json(200, {
      model: "jev-1.13.0",
      answers: {
        box1: {
          type: "choice",
          choice: "owner-gate",
          confidence: 0.81,
          probabilities: { repair: 0.1, "owner-gate": 0.81, "do-not-patch": 0.09 },
        },
      },
      usage: { input_tokens: 120, output_tokens: 1 },
    }),
  );
  const outcome = await evaluate(leftover, hosted, impl);
  assert.equal(outcome.status, "ok");
  assert.equal(outcome.result.answers.box1.choice, "owner-gate");
  assert.deepEqual(outcome.result.usage, { inputTokens: 120, outputTokens: 1 });
  assert.deepEqual(outcome.provenance, { judge: "jev", route: "typesafe-hosted", model: "jev-1.13.0" });
  assert.equal(calls[0].url, HOSTED_ENDPOINT);
  assert.equal(calls[0].init.headers.Authorization, `Bearer ${KEY}`);
  assert.equal(calls[0].body.model, "jev-latest");
  assert.deepEqual(calls[0].body.questions, leftover.questions);
});

test("boolean goes out as noul and comes back as probabilityTrue; score levels map to an array", async () => {
  const batch = {
    state: "x",
    questions: {
      b: { type: "boolean", instructions: "Is it locked?" },
      s: { type: "score", criteria: ["low", "mid", "high"] },
    },
  };
  const { impl, calls } = fakeFetch(() =>
    json(200, {
      model: "jev-latest",
      answers: {
        b: { type: "noul", noul: 0.92 },
        s: { type: "score", score: 1.4, confidence: 0.6, probabilities: { 0: 0.2, 1: 0.2, 2: 0.6 }, legend: { 0: "low", 1: "mid", 2: "high" } },
      },
      usage: { input_tokens: 10, output_tokens: 2 },
    }),
  );
  const outcome = await evaluate(batch, hosted, impl);
  assert.equal(calls[0].body.questions.b.type, "noul");
  assert.deepEqual(outcome.result.answers.b, { type: "boolean", probabilityTrue: 0.92 });
  assert.deepEqual(outcome.result.answers.s.probabilities, [0.2, 0.2, 0.6]);
});

test("every failure is an unavailable result with guidance, never a throw", async () => {
  const cases = [
    [() => json(401, {}), "authentication"],
    [() => json(403, {}), "authentication"],
    [() => json(429, {}), "rate-limited"],
    [() => json(422, {}), "unsupported-input"],
    [() => json(503, {}), "transport"],
    [() => { throw new TypeError("fetch failed"); }, "transport"],
    [() => new Response("not json", { status: 200 }), "invalid-response"],
    [() => json(200, { model: "m", answers: { box1: { type: "choice", choice: "merge", confidence: 1, probabilities: { merge: 1, x: 0 } } } }), "invalid-response"],
    [() => json(200, { model: "m", answers: {} }), "invalid-response"],
    [() => json(200, { echoed: KEY, answers: {} }), "invalid-response"],
  ];
  for (const [respond, reason] of cases) {
    const outcome = await evaluate(leftover, hosted, fakeFetch(respond).impl);
    assert.equal(outcome.status, "unavailable", reason);
    assert.equal(outcome.reason, reason);
    assert.match(outcome.guidance, /\S/);
    assert.ok(!JSON.stringify(outcome).includes(KEY));
  }
});

test("a judge that hangs gives up at the timeout instead of holding the rails", async () => {
  const hang = (_url, init) =>
    new Promise((_resolve, reject) => init.signal.addEventListener("abort", () => reject(init.signal.reason)));
  const started = performance.now();
  const outcome = await evaluate(leftover, { ...hosted, timeoutMs: 200 }, hang);
  assert.equal(outcome.reason, "transport");
  assert.ok(performance.now() - started < 2_000);
});

test("bad input is refused before anything is sent", async () => {
  const { impl, calls } = fakeFetch(() => json(200, {}));
  for (const bad of [
    undefined,
    { state: "x" },
    { state: "x", questions: {} },
    { state: "x", questions: { q: { type: "choice", criteria: { only: "one" } } } },
    { state: "x", questions: { q: { type: "score", criteria: ["one"] } } },
    { state: "x", questions: { q: { type: "maybe" } } },
    { state: 5, questions: { q: { type: "boolean" } } },
    { state: "x", questions: { q: { type: "boolean" } }, model: "pick-me" },
  ]) {
    const outcome = await evaluate(bad, hosted, impl);
    assert.equal(outcome.reason, "unsupported-input");
  }
  assert.equal(calls.length, 0);
  assert.equal(checkBatch(leftover), null);
});

test("routes resolve from local settings: disabled, local Kev, env key, Keychain, nothing", async () => {
  const noKeychain = async () => undefined;
  assert.equal((await resolveRoute({ JEV_DISABLED: "1", TYPESAFE_API_KEY: KEY }, noKeychain)).reason, "disabled");

  const kev = await resolveRoute({ TYPESAFE_BASE_URL: "http://127.0.0.1:8009" }, noKeychain);
  assert.deepEqual([kev.kind, kev.endpoint, kev.model, kev.apiKey], ["kev-local", "http://127.0.0.1:8009/v1/systemone", "kev-latest", undefined]);

  const remote = await resolveRoute({ TYPESAFE_BASE_URL: "http://evil.example:8009" }, noKeychain);
  assert.equal(remote.reason, "not-configured");

  const env = await resolveRoute({ TYPESAFE_API_KEY: KEY, JEV_TIMEOUT_MS: "999999" }, noKeychain);
  assert.deepEqual([env.kind, env.keySource, env.timeoutMs], ["typesafe-hosted", "env", 30_000]);

  let asked;
  const keychain = await resolveRoute({}, async (service) => ((asked = service), KEY));
  assert.deepEqual([keychain.keySource, asked], ["keychain", "typesafe-jev"]);

  assert.equal((await resolveRoute({}, noKeychain)).reason, "credentials-unavailable");
  const none = await evaluate(leftover, await resolveRoute({}, noKeychain), () => assert.fail("no call"));
  assert.equal(none.status, "unavailable");
  assert.equal(none.reason, "credentials-unavailable");
});

test("local Kev requests carry no Authorization header", async () => {
  const { impl, calls } = fakeFetch(() => json(503, {}));
  await evaluate(leftover, { kind: "kev-local", endpoint: "http://127.0.0.1:8009/v1/systemone", model: "kev-latest", timeoutMs: 1_000 }, impl);
  assert.equal(calls[0].init.headers.Authorization, undefined);
});
