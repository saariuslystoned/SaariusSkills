import { execFile } from "node:child_process";

// Same request and result contract as OpenClaw's core `decision_evaluate` tool,
// so a skill can call either one and read the answer the same way.
// Every failure is an `unavailable` result, never a thrown error: a missing or
// broken judge must not stop the caller's own fallback.

export const HOSTED_ENDPOINT = "https://api.typesafe.ai/v1/systemone";
export const DEFAULT_KEYCHAIN_SERVICE = "typesafe-jev";
export const DEFAULT_MODEL = "jev-latest";
export const LOCAL_MODEL = "kev-latest";
export const DEFAULT_TIMEOUT_MS = 15_000;
const MAX_TIMEOUT_MS = 30_000;
const MAX_JSON_BYTES = 1024 * 1024;
const MAX_QUESTIONS = 256;
const LOOPBACK = /^https?:\/\/(?:localhost|127\.0\.0\.1|\[::1\])(?::[0-9]{1,5})?\/?$/;

const GUIDANCE = {
  disabled: "JEV_DISABLED is set. Apply the rubric by hand and say Jev did not run.",
  "not-configured":
    "No Jev route on this machine. Apply the rubric by hand and say Jev did not run.",
  "credentials-unavailable":
    "No TypeSafe key in the environment or Keychain. Apply the rubric by hand and say Jev did not run.",
  authentication: "TypeSafe rejected the key. Apply the rubric by hand; ask the owner to check the key.",
  "rate-limited": "TypeSafe is rate limited. Apply the rubric by hand; do not loop on retries.",
  transport: "Jev could not be reached in time. Apply the rubric by hand and say Jev did not run.",
  "unsupported-input": "Jev refused the input. Send one box per question with shorter state.",
  "invalid-response": "Jev returned an answer that did not match the questions. Apply the rubric by hand.",
};

export function unavailable(reason, extra = {}) {
  return { status: "unavailable", reason, guidance: GUIDANCE[reason], ...extra };
}

/** Pick a route from local settings only; never touches the network. */
export async function resolveRoute(env = process.env, readKeychain = keychainSecret) {
  if (env.JEV_DISABLED === "1") return { kind: "none", reason: "disabled" };
  const timeoutMs = clampTimeout(env.JEV_TIMEOUT_MS);
  if (env.TYPESAFE_BASE_URL) {
    if (!LOOPBACK.test(env.TYPESAFE_BASE_URL.trim())) {
      return { kind: "none", reason: "not-configured", note: "TYPESAFE_BASE_URL must be a loopback origin." };
    }
    const origin = new URL(env.TYPESAFE_BASE_URL.trim()).origin;
    return { kind: "kev-local", endpoint: `${origin}/v1/systemone`, model: LOCAL_MODEL, timeoutMs };
  }
  let apiKey = env.TYPESAFE_API_KEY?.trim();
  let keySource = "env";
  if (!apiKey) {
    apiKey = await readKeychain(env.JEV_KEYCHAIN_SERVICE || DEFAULT_KEYCHAIN_SERVICE);
    keySource = "keychain";
  }
  if (!apiKey) return { kind: "none", reason: "credentials-unavailable" };
  return {
    kind: "typesafe-hosted",
    endpoint: HOSTED_ENDPOINT,
    model: env.JEV_MODEL?.trim() || DEFAULT_MODEL,
    apiKey,
    keySource,
    timeoutMs,
  };
}

/** macOS Keychain lookup; any other platform or a missing item is simply no key. */
export function keychainSecret(service) {
  if (process.platform !== "darwin") return Promise.resolve(undefined);
  return new Promise((resolve) => {
    execFile(
      "/usr/bin/security",
      ["find-generic-password", "-s", service, "-w"],
      { timeout: 3_000 },
      (error, stdout) => resolve(error ? undefined : stdout.trim() || undefined),
    );
  });
}

function clampTimeout(value) {
  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed < 1_000) return DEFAULT_TIMEOUT_MS;
  return Math.min(parsed, MAX_TIMEOUT_MS);
}

// Text, a JSON object or array, or null (typeof null is "object").
const isEntry = (value) => typeof value === "string" || typeof value === "object";

/** Validate the OpenClaw-shaped batch; returns an error string or null. */
export function checkBatch(batch) {
  if (!batch || typeof batch !== "object" || Array.isArray(batch)) return "Supply state and questions.";
  if (Object.keys(batch).some((key) => key !== "state" && key !== "questions")) {
    return "Only state and questions are accepted.";
  }
  if (!("state" in batch) || !isEntry(batch.state)) return "state must be text, a JSON object or array, or null.";
  const questions = batch.questions;
  if (!questions || typeof questions !== "object" || Array.isArray(questions)) {
    return "questions must be a map of question ids to questions.";
  }
  const entries = Object.entries(questions);
  if (entries.length < 1 || entries.length > MAX_QUESTIONS) return "Ask between 1 and 256 questions.";
  for (const [, q] of entries) {
    if (!q || typeof q !== "object" || Array.isArray(q)) return "Each question must be an object.";
    if (Object.keys(q).some((key) => !["type", "instructions", "criteria"].includes(key))) {
      return "Questions accept only type, instructions and criteria.";
    }
    if ("instructions" in q && !isEntry(q.instructions)) return "instructions must be text, JSON or null.";
    if (q.type === "choice") {
      const c = q.criteria;
      if (!c || typeof c !== "object" || Array.isArray(c) || Object.keys(c).length < 2) {
        return "A choice question needs at least two labels in criteria.";
      }
    } else if (q.type === "score") {
      if (!Array.isArray(q.criteria) || q.criteria.length < 2 || q.criteria.length > 10) {
        return "A score question needs 2 to 10 ordered levels in criteria.";
      }
    } else if (q.type === "boolean") {
      const c = q.criteria;
      if (c !== undefined && c !== null) {
        if (typeof c !== "object" || Array.isArray(c) || Object.keys(c).some((k) => k !== "true" && k !== "false")) {
          return "Boolean criteria may hold only true and false descriptions.";
        }
      }
    } else {
      return "type must be boolean, choice or score.";
    }
  }
  if (Buffer.byteLength(JSON.stringify(batch)) > MAX_JSON_BYTES) return "Input is over 1 MiB.";
  return null;
}

/** OpenClaw says boolean; TypeSafe's wire format says noul. */
function toWire(batch, model) {
  const questions = Object.fromEntries(
    Object.entries(batch.questions).map(([id, q]) => [id, q.type === "boolean" ? { ...q, type: "noul" } : q]),
  );
  return { state: batch.state, questions, model };
}

const isProbability = (n) => typeof n === "number" && Number.isFinite(n) && n >= 0 && n <= 1;

/** Map TypeSafe answers back to OpenClaw's shape; null when they do not match the questions. */
export function fromWire(response, batch) {
  if (!response || typeof response !== "object" || !response.answers || typeof response.answers !== "object") {
    return null;
  }
  const ids = Object.keys(batch.questions);
  if (Object.keys(response.answers).length !== ids.length) return null;
  const answers = {};
  for (const id of ids) {
    const q = batch.questions[id];
    const a = response.answers[id];
    if (!a || typeof a !== "object") return null;
    if (q.type === "boolean") {
      if (a.type !== "noul" || !isProbability(a.noul)) return null;
      answers[id] = { type: "boolean", probabilityTrue: a.noul };
      continue;
    }
    if (a.type !== q.type || !a.probabilities || typeof a.probabilities !== "object") return null;
    const labels = q.type === "choice" ? Object.keys(q.criteria) : q.criteria.map((_, i) => String(i));
    const keys = Object.keys(a.probabilities);
    if (keys.length !== labels.length || labels.some((label) => !isProbability(a.probabilities[label]))) {
      return null;
    }
    if (q.type === "choice") {
      if (!labels.includes(a.choice)) return null;
      answers[id] = { type: "choice", choice: a.choice, confidence: a.confidence, probabilities: a.probabilities };
    } else {
      if (typeof a.score !== "number" || a.score < 0 || a.score > labels.length - 1) return null;
      answers[id] = {
        type: "score",
        score: a.score,
        confidence: a.confidence,
        probabilities: labels.map((label) => a.probabilities[label]),
      };
    }
  }
  const usage = response.usage && {
    inputTokens: response.usage.input_tokens,
    outputTokens: response.usage.output_tokens,
  };
  return { model: response.model, answers, ...(usage ? { usage } : {}) };
}

function httpReason(status) {
  if (status === 401 || status === 403) return "authentication";
  if (status === 429) return "rate-limited";
  if (status === 400 || status === 413 || status === 422) return "unsupported-input";
  return "transport";
}

/** Evaluate one batch through the resolved route. Always resolves; never throws. */
export async function evaluate(batch, route, fetchImpl = globalThis.fetch) {
  const problem = checkBatch(batch);
  if (problem) return unavailable("unsupported-input", { note: problem });
  if (route.kind === "none") return unavailable(route.reason, route.note ? { note: route.note } : {});
  const provenance = { judge: "jev", route: route.kind, model: route.model };
  // A held timer (not AbortSignal.timeout, which is unref'd) so a hung judge always ends the call.
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), route.timeoutMs);
  const { signal } = controller;
  try {
    const response = await fetchImpl(route.endpoint, {
      method: "POST",
      redirect: "error",
      signal,
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        ...(route.apiKey ? { Authorization: `Bearer ${route.apiKey}` } : {}),
      },
      body: JSON.stringify(toWire(batch, route.model)),
    });
    if (!response.ok) {
      // Error bodies can echo the request or the key; never read them.
      await response.body?.cancel?.().catch(() => {});
      return unavailable(httpReason(response.status), { provenance });
    }
    const text = await response.text();
    if (Buffer.byteLength(text) > 4 * MAX_JSON_BYTES) return unavailable("invalid-response", { provenance });
    if (route.apiKey && text.includes(route.apiKey)) return unavailable("invalid-response", { provenance });
    let parsed;
    try {
      parsed = JSON.parse(text);
    } catch {
      return unavailable("invalid-response", { provenance });
    }
    const result = fromWire(parsed, batch);
    if (!result) return unavailable("invalid-response", { provenance });
    return { status: "ok", result, provenance: { ...provenance, model: result.model ?? route.model } };
  } catch {
    return unavailable("transport", { provenance });
  } finally {
    clearTimeout(timer);
  }
}

/** What a caller needs to know about this machine's route, without the key. */
export function describeRoute(route) {
  if (route.kind === "none") return { ready: false, reason: route.reason, guidance: GUIDANCE[route.reason], ...(route.note ? { note: route.note } : {}) };
  return {
    ready: true,
    route: route.kind,
    model: route.model,
    timeoutMs: route.timeoutMs,
    ...(route.keySource ? { keySource: route.keySource } : {}),
  };
}
