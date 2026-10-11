import { randomUUID } from "node:crypto";
import { createServer } from "node:http";
import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js";
import { isInitializeRequest } from "@modelcontextprotocol/sdk/types.js";
import { BridgeError } from "./broker.mjs";

// Remote-shed transport: Streamable HTTP on loopback only. The operator
// publishes it through an outbound Cloudflare Tunnel with an Access
// application in front. Every request must carry a verified Access JWT for a
// known service token (see access-auth.mjs), so a tunnel or Access
// misconfiguration never yields an open endpoint.
export const TRANSPORT_ENV = "SAARIUS_ACP_TRANSPORT";
export const HTTP_HOST_ENV = "SAARIUS_ACP_HTTP_HOST";
export const HTTP_PORT_ENV = "SAARIUS_ACP_HTTP_PORT";
export const HTTP_PUBLIC_HOST_ENV = "SAARIUS_ACP_HTTP_PUBLIC_HOST";
export const HOP_ARGV_ENV = "SAARIUS_ACP_HOP_ARGV";
export const MCP_PATH = "/mcp";
export const DEFAULT_HTTP_PORT = 8765;
export const MAX_BODY_BYTES = 1024 * 1024;
export const MAX_SESSIONS = 32;
export const SESSION_IDLE_MS = 60 * 60 * 1000;
const LOOPBACK_HOSTS = new Set(["127.0.0.1", "::1", "localhost"]);

export function resolveTransport({ argv = [], env = process.env } = {}) {
  const flagIndex = argv.indexOf("--transport");
  const raw = (flagIndex >= 0 ? argv[flagIndex + 1] : env[TRANSPORT_ENV])?.trim() || "stdio";
  if (raw !== "stdio" && raw !== "http") {
    throw new BridgeError("TRANSPORT_INVALID", "transport must be stdio or http", { transport: raw });
  }
  if (raw === "http" && typeof env[HOP_ARGV_ENV] === "string" && env[HOP_ARGV_ENV].trim()) {
    throw new BridgeError("HTTP_HOP_REFUSED", `remote-shed http mode runs the worker locally; unset ${HOP_ARGV_ENV}`);
  }
  return raw;
}

export function resolveHttpConfig(env = process.env) {
  const host = env[HTTP_HOST_ENV]?.trim() || "127.0.0.1";
  if (!LOOPBACK_HOSTS.has(host)) {
    throw new BridgeError("HTTP_BIND_REFUSED", `${HTTP_HOST_ENV} must be a loopback address; publish through an authenticated tunnel`, { host });
  }
  const portRaw = env[HTTP_PORT_ENV]?.trim();
  const port = portRaw ? Number(portRaw) : DEFAULT_HTTP_PORT;
  if (!Number.isInteger(port) || port < 0 || port > 65_535) {
    throw new BridgeError("HTTP_PORT_INVALID", `${HTTP_PORT_ENV} must be a TCP port`, { port: portRaw });
  }
  const publicHosts = String(env[HTTP_PUBLIC_HOST_ENV] ?? "")
    .split(",")
    .map((value) => value.trim().toLowerCase())
    .filter(Boolean);
  return { host, port, publicHosts };
}

function hostAllowed(hostHeader, { port, publicHosts }) {
  const value = String(hostHeader ?? "").toLowerCase();
  if (!value) return false;
  const name = value.startsWith("[") ? value.slice(0, value.indexOf("]") + 1) : value.split(":")[0];
  if (publicHosts.includes(name)) return true;
  return ["127.0.0.1", "localhost", "[::1]"].includes(name) && (value === name || value === `${name}:${port}`);
}

function sendJson(res, status, body) {
  res.writeHead(status, { "content-type": "application/json" });
  res.end(JSON.stringify(body));
}

const rpcError = (message) => ({ jsonrpc: "2.0", error: { code: -32000, message }, id: null });

async function readJson(req) {
  const chunks = [];
  let size = 0;
  for await (const chunk of req) {
    size += chunk.length;
    if (size > MAX_BODY_BYTES) throw Object.assign(new Error("body too large"), { status: 413 });
    chunks.push(chunk);
  }
  if (size === 0) return undefined;
  try {
    return JSON.parse(Buffer.concat(chunks).toString("utf8"));
  } catch {
    throw Object.assign(new Error("invalid JSON"), { status: 400 });
  }
}

export async function startRemoteShedHost({ env = process.env, createServer: createMcp, authenticate, bridge, log = (line) => process.stderr.write(`${line}\n`) } = {}) {
  const config = resolveHttpConfig(env);
  if (typeof authenticate !== "function") throw new BridgeError("HTTP_AUTH_REQUIRED", "remote-shed host requires an authenticator");
  const sessions = new Map();

  const closeSession = async (id) => {
    const entry = sessions.get(id);
    if (!entry) return;
    sessions.delete(id);
    await entry.transport.close().catch(() => {});
    await entry.server.close().catch(() => {});
  };

  const sweep = setInterval(() => {
    const now = Date.now();
    for (const [id, entry] of sessions) if (now - entry.lastSeen > SESSION_IDLE_MS) void closeSession(id);
  }, 60_000);
  sweep.unref();

  const httpServer = createServer(async (req, res) => {
    try {
      const url = new URL(req.url ?? "/", "http://local");
      if (!hostAllowed(req.headers.host, config)) return sendJson(res, 403, rpcError("host not allowed"));
      if (url.pathname !== MCP_PATH) return sendJson(res, 404, rpcError("not found"));
      let caller;
      try {
        caller = await authenticate(req.headers);
      } catch (error) {
        const unavailable = error?.code === "ACCESS_UNAVAILABLE";
        return sendJson(res, unavailable ? 503 : 401, rpcError(unavailable ? "auth unavailable" : "unauthorized"));
      }
      const sessionId = req.headers["mcp-session-id"];
      const body = req.method === "POST" ? await readJson(req) : undefined;
      let entry = typeof sessionId === "string" ? sessions.get(sessionId) : undefined;
      if (!entry) {
        if (sessionId) return sendJson(res, 404, rpcError("unknown session"));
        if (req.method !== "POST" || !isInitializeRequest(body)) return sendJson(res, 400, rpcError("initialize first"));
        if (sessions.size >= MAX_SESSIONS) return sendJson(res, 503, rpcError("too many sessions"));
        const server = createMcp(caller);
        const transport = new StreamableHTTPServerTransport({
          sessionIdGenerator: () => randomUUID(),
          onsessioninitialized: (id) => sessions.set(id, entry),
        });
        entry = { server, transport, caller, lastSeen: Date.now() };
        transport.onclose = () => {
          if (transport.sessionId) sessions.delete(transport.sessionId);
        };
        await server.connect(transport);
      }
      // A session belongs to the caller that opened it.
      if (entry.caller.clientId !== caller.clientId) return sendJson(res, 403, rpcError("session belongs to another caller"));
      entry.lastSeen = Date.now();
      await entry.transport.handleRequest(req, res, body);
    } catch (error) {
      if (!res.headersSent) sendJson(res, error?.status ?? 500, rpcError(error?.status ? error.message : "internal error"));
      else res.end();
      if (!error?.status) log(JSON.stringify({ status: "error", bridge, code: "HTTP_REQUEST_FAILED" }));
    }
  });

  await new Promise((resolve, reject) => {
    httpServer.once("error", reject);
    httpServer.listen(config.port, config.host, resolve);
  });
  const address = httpServer.address();
  config.port = address.port; // port 0 binds an ephemeral port; Host checks use the real one
  log(JSON.stringify({ status: "listening", bridge, transport: "http", host: config.host, port: address.port, path: MCP_PATH }));

  return {
    port: address.port,
    sessions,
    close: async () => {
      clearInterval(sweep);
      for (const id of [...sessions.keys()]) await closeSession(id);
      await new Promise((resolve) => httpServer.close(() => resolve()));
    },
  };
}
