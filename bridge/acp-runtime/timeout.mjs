export const MIN_TIMEOUT_MS = 1_000;
export const DEFAULT_TIMEOUT_MS = 3_600_000;
export const MAX_TIMEOUT_MS = 14_400_000;
export const TIMEOUT_ENV = "SAARIUS_ACP_TIMEOUT_MS";

export class BridgeError extends Error {
  constructor(code, message, details = {}) {
    super(message);
    this.name = "BridgeError";
    this.code = code;
    this.details = details;
  }
}

export function timeoutMsZod(z) {
  return z.number().int().min(MIN_TIMEOUT_MS).max(MAX_TIMEOUT_MS).optional();
}

export function parseTimeout(value) {
  if (value === undefined) return DEFAULT_TIMEOUT_MS;
  if (!Number.isInteger(value) || value < MIN_TIMEOUT_MS || value > MAX_TIMEOUT_MS) {
    throw new BridgeError(
      "INVALID_INPUT",
      `timeoutMs must be an integer between ${MIN_TIMEOUT_MS} and ${MAX_TIMEOUT_MS}`,
    );
  }
  return value;
}

export function resolveDefaultTimeoutMs(env = process.env) {
  const raw = env?.[TIMEOUT_ENV];
  if (raw === undefined) return DEFAULT_TIMEOUT_MS;
  if (typeof raw === "string") {
    const trimmed = raw.trim();
    if (trimmed === "") return DEFAULT_TIMEOUT_MS;
    if (/^\d+$/.test(trimmed)) {
      const parsed = Number(trimmed);
      if (Number.isSafeInteger(parsed) && parsed >= MIN_TIMEOUT_MS && parsed <= MAX_TIMEOUT_MS) {
        return parsed;
      }
    }
  }
  throw new BridgeError(
    "INVALID_CONFIG",
    `${TIMEOUT_ENV} must be a base-10 integer between ${MIN_TIMEOUT_MS} and ${MAX_TIMEOUT_MS} ms (got ${JSON.stringify(raw)})`,
    {
      env: TIMEOUT_ENV,
      value: raw,
      minTimeoutMs: MIN_TIMEOUT_MS,
      maxTimeoutMs: MAX_TIMEOUT_MS,
    },
  );
}
