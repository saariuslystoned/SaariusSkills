import { redactSensitive } from "./broker.mjs";

// Redaction pass for the read-only session viewer. Everything the viewer
// renders (HTML or JSON) goes through redactDeep first. This is defence in
// depth on top of the bridge's input secret refusal: agent output, tool
// inputs and tool outputs can echo files or environments we never asked for.
const RULES = [
  // PEM private keys (RSA, EC, OPENSSH, ENCRYPTED, ...), including truncated blocks.
  [/-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----[\s\S]*?(?:-----END [A-Z0-9 ]*PRIVATE KEY-----|$)/g, "[redacted private key]"],
  // Cloudflare Access service-token headers / fields.
  [/\b(cf-access-client-secret|cf_access_client_secret|access[_-]?client[_-]?secret|client[_-]?secret)(["']?\s*[:=]\s*["']?)[^\s"',;]+/gi, "$1$2[redacted]"],
  [/\b(cf-access-client-id|cf_access_client_id)(["']?\s*[:=]\s*["']?)[^\s"',;]+/gi, "$1$2[redacted]"],
  [/\b(cf-access-jwt-assertion|cf_authorization)(["']?\s*[:=]\s*["']?)[^\s"',;]+/gi, "$1$2[redacted]"],
  // Cloudflare API tokens / global key passed as headers or env.
  [/\b(x-auth-key|x-auth-user-service-key)(["']?\s*[:=]\s*["']?)[^\s"',;]+/gi, "$1$2[redacted]"],
  [/\b((?:CLOUDFLARE|CF)_[A-Z0-9_]*(?:TOKEN|KEY|SECRET)[A-Z0-9_]*)(["']?\s*[:=]\s*["']?)[^\s"',;]+/g, "$1$2[redacted]"],
  // Authorization headers of any scheme.
  [/\b(authorization|proxy-authorization)(["']?\s*[:=]\s*["']?)(?:Bearer|Basic|token|Bot)\s+[^\s"',;]+/gi, "$1$2[redacted]"],
  [/\bBearer\s+[A-Za-z0-9._~+/=-]{6,}/gi, "Bearer [redacted]"],
  // GitHub tokens (classic + fine-grained) and similar vendor-prefixed tokens.
  [/\bgithub_pat_[A-Za-z0-9_]{20,}/g, "[redacted github token]"],
  [/\bgh[pousr]_[A-Za-z0-9]{20,}/g, "[redacted github token]"],
  [/\b(?:sk|rk|pk)-(?:live-|test-|proj-|ant-)?[A-Za-z0-9_-]{16,}/g, "[redacted token]"],
  [/\bxox[abprs]-[A-Za-z0-9-]{10,}/g, "[redacted token]"],
  [/\bAIza[0-9A-Za-z_-]{30,}/g, "[redacted token]"],
  // AWS access key ids and secret keys.
  [/\b(?:AKIA|ASIA|AGPA|AIDA|AROA|ANPA)[0-9A-Z]{16}\b/g, "[redacted aws key id]"],
  [/\b(aws_secret_access_key|aws_session_token|secretaccesskey)(["']?\s*[:=]\s*["']?)[^\s"',;]+/gi, "$1$2[redacted]"],
  // JWTs (Access assertions, OAuth id tokens).
  [/\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}/g, "[redacted jwt]"],
  // Credentials embedded in URLs.
  [/\b([a-z][a-z0-9+.-]*:\/\/)[^\s/:@]+:[^\s/@]+@/gi, "$1[redacted]@"],
  // Generic env / config lines: FOO_KEY=..., API_TOKEN: ..., DB_PASSWORD="...".
  [/\b((?:export\s+)?(?:[A-Za-z0-9]+[_-])*(?:KEY|TOKEN|SECRET|PASSWORD|PASSWD|PASS|CREDENTIALS?|APIKEY|PRIVATE_KEY)(?:[_-][A-Za-z0-9]+)*)(["']?[ \t]*[:=][ \t]*["']?)(?!\[redacted)[^\s"',;]+/gi, "$1$2[redacted]"],
];

export function redactText(value) {
  let text = String(value ?? "");
  for (const [pattern, replacement] of RULES) text = text.replace(pattern, replacement);
  return redactSensitive(text);
}

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
