import { createPublicKey, verify as verifySignature } from "node:crypto";
import { BridgeError } from "./broker.mjs";

// Per-caller authentication for remote-shed mode. Cloudflare Access sits in
// front of the tunnel and only admits requests that present a service token
// (CF-Access-Client-Id / CF-Access-Client-Secret). Access then forwards a
// signed JWT in Cf-Access-Jwt-Assertion whose common_name is the service
// token's client id. The bridge verifies that JWT against the team's public
// keys and maps the client id to a caller label from operator config. Only
// the label is ever logged; tokens and secrets never are.
export const ACCESS_TEAM_DOMAIN_ENV = "SAARIUS_ACP_ACCESS_TEAM_DOMAIN";
export const ACCESS_AUD_ENV = "SAARIUS_ACP_ACCESS_AUD";
export const REMOTE_CALLERS_ENV = "SAARIUS_ACP_REMOTE_CALLERS";
export const ACCESS_JWT_HEADER = "cf-access-jwt-assertion";
const TEAM_DOMAIN_PATTERN = /^[a-z0-9-]+\.cloudflareaccess\.com$/;
const LABEL_PATTERN = /^[A-Za-z0-9_.@-]{1,64}$/;
const CLIENT_ID_PATTERN = /^[A-Za-z0-9._-]{8,128}$/;
const JWKS_TTL_MS = 10 * 60 * 1000;
const CLOCK_SKEW_S = 60;

export function parseRemoteCallers(raw) {
  const callers = new Map();
  for (const entry of String(raw ?? "").split(/[\s,]+/).filter(Boolean)) {
    const index = entry.indexOf("=");
    const clientId = entry.slice(0, index);
    const label = entry.slice(index + 1);
    if (index <= 0 || !CLIENT_ID_PATTERN.test(clientId) || !LABEL_PATTERN.test(label)) {
      throw new BridgeError("REMOTE_CALLERS_INVALID", `${REMOTE_CALLERS_ENV} entries must be <access-client-id>=<label>`);
    }
    callers.set(clientId, label);
  }
  if (callers.size === 0) {
    throw new BridgeError("REMOTE_CALLERS_REQUIRED", `${REMOTE_CALLERS_ENV} must name at least one Access service token`);
  }
  return callers;
}

export function resolveAccessConfig(env = process.env) {
  const teamDomain = env[ACCESS_TEAM_DOMAIN_ENV]?.trim().toLowerCase().replace(/^https:\/\//, "").replace(/\/+$/, "");
  if (!teamDomain || !TEAM_DOMAIN_PATTERN.test(teamDomain)) {
    throw new BridgeError("ACCESS_TEAM_DOMAIN_REQUIRED", `${ACCESS_TEAM_DOMAIN_ENV} must be <team>.cloudflareaccess.com`);
  }
  const audiences = String(env[ACCESS_AUD_ENV] ?? "").split(/[\s,]+/).filter(Boolean);
  if (audiences.length === 0 || audiences.some((aud) => !/^[a-f0-9]{32,128}$/i.test(aud))) {
    throw new BridgeError("ACCESS_AUD_REQUIRED", `${ACCESS_AUD_ENV} must be the Access application's AUD tag`);
  }
  return { teamDomain, issuer: `https://${teamDomain}`, audiences, callers: parseRemoteCallers(env[REMOTE_CALLERS_ENV]) };
}

const b64urlJson = (part) => JSON.parse(Buffer.from(part, "base64url").toString("utf8"));

export function createAccessAuthenticator({ env = process.env, config = resolveAccessConfig(env), fetchJwks, now = () => Date.now() } = {}) {
  const loadJwks = fetchJwks ?? (async () => {
    const response = await fetch(`${config.issuer}/cdn-cgi/access/certs`, { signal: AbortSignal.timeout(10_000) });
    if (!response.ok) throw new Error(`certs ${response.status}`);
    return response.json();
  });
  let cache = { keys: new Map(), fetchedAt: 0 };

  async function keyFor(kid) {
    const fresh = now() - cache.fetchedAt < JWKS_TTL_MS;
    if (!fresh || !cache.keys.has(kid)) {
      const jwks = await loadJwks();
      const keys = new Map();
      for (const jwk of jwks?.keys ?? []) {
        if (jwk?.kid && jwk.kty === "RSA") keys.set(jwk.kid, createPublicKey({ key: jwk, format: "jwk" }));
      }
      cache = { keys, fetchedAt: now() };
    }
    return cache.keys.get(kid);
  }

  const refuse = (reason) => {
    throw new BridgeError("ACCESS_DENIED", "Cloudflare Access identity was not accepted", { reason });
  };

  // Returns { label, clientId } or throws ACCESS_DENIED.
  return async function authenticate(headers) {
    const token = headers?.[ACCESS_JWT_HEADER];
    if (typeof token !== "string" || token.length > 8_192) refuse("missing");
    const parts = token.split(".");
    if (parts.length !== 3) refuse("malformed");
    let header;
    let claims;
    try {
      header = b64urlJson(parts[0]);
      claims = b64urlJson(parts[1]);
    } catch {
      refuse("malformed");
    }
    if (header.alg !== "RS256" || typeof header.kid !== "string") refuse("algorithm");
    let key;
    try {
      key = await keyFor(header.kid);
    } catch {
      throw new BridgeError("ACCESS_UNAVAILABLE", "Cloudflare Access public keys could not be loaded");
    }
    if (!key) refuse("unknown_key");
    const signed = Buffer.from(`${parts[0]}.${parts[1]}`);
    if (!verifySignature("RSA-SHA256", signed, key, Buffer.from(parts[2], "base64url"))) refuse("signature");
    const nowS = Math.floor(now() / 1000);
    if (claims.iss !== config.issuer) refuse("issuer");
    const aud = Array.isArray(claims.aud) ? claims.aud : [claims.aud];
    if (!aud.some((value) => config.audiences.includes(value))) refuse("audience");
    if (typeof claims.exp !== "number" || claims.exp + CLOCK_SKEW_S < nowS) refuse("expired");
    if (typeof claims.nbf === "number" && claims.nbf - CLOCK_SKEW_S > nowS) refuse("not_yet_valid");
    const clientId = claims.common_name;
    const label = typeof clientId === "string" ? config.callers.get(clientId) : undefined;
    if (!label) refuse("unknown_caller");
    return { label, clientId };
  };
}
