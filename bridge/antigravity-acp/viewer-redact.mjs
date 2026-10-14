import { redactSensitive, redactText } from "./broker.mjs";

export { redactText };

// Redaction pass for the read-only session viewer. Everything the viewer
// renders (HTML or JSON) goes through redactDeep first. This is defence in
// depth on top of the bridge's input secret refusal: agent output, tool
// inputs and tool outputs can echo files or environments we never asked for.
export function redactDeep(value, depth = 0) {
  if (depth > 20) return "[truncated]";
  if (typeof value === "string") return redactText(value);
  if (Array.isArray(value)) return value.map((item) => redactDeep(item, depth + 1));
  if (value && typeof value === "object") {
    const out = {};
    for (const [key, item] of Object.entries(value)) {
      out[key] = /^(?:.*(?:secret|password|passwd|token|apikey|api_key|authorization|cookie|private_?key).*)$/i.test(key) && typeof item === "string"
        ? "[redacted]"
        : redactDeep(item, depth + 1);
    }
    return out;
  }
  return value;
}
