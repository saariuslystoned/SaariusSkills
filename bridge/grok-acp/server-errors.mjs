import { BridgeError, safeMessage } from "./broker.mjs";

function redactDetails(value, seen = new WeakSet()) {
  if (typeof value === "string") return safeMessage(value);
  if (!value || typeof value !== "object") return value;
  if (seen.has(value)) return "[circular]";
  seen.add(value);
  if (Array.isArray(value)) return value.slice(0, 20).map((entry) => redactDetails(entry, seen));
  return Object.fromEntries(
    Object.entries(value).slice(0, 30).map(([key, entry]) => [
      key,
      /token|secret|password|credential|authorization|private|api[-_]?key/i.test(key)
        ? "[redacted]"
        : redactDetails(entry, seen),
    ]),
  );
}

export function serializeFailure(error) {
  if (!(error instanceof BridgeError)) {
    return { code: "BRIDGE_ERROR", message: "Grok ACP request failed." };
  }
  const payload = {
    code: safeMessage(typeof error.code === "string" ? error.code : "BRIDGE_ERROR", 80),
    message: safeMessage(error.message),
  };
  if (error.details && typeof error.details === "object" && Object.keys(error.details).length > 0) {
    payload.details = redactDetails(error.details);
  }
  return payload;
}
