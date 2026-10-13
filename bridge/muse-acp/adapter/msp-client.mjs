// Minimal Muse Session Protocol (MSP) client for `muse serve` stdio hosts.
//
// MSP is newline-delimited JSON-RPC 2.0. The client owns the child process's
// stdin/stdout; stderr passes through untouched. Server-initiated requests
// (`approval/request`, `userInput/request`) are dispatched to a handler whose
// return value becomes the JSON-RPC result (for MSP these results are
// presentation receipts; decisions travel as separate commands).

import { spawn } from "node:child_process";

export class MspError extends Error {
  constructor(message, { code, data } = {}) {
    super(message);
    this.name = "MspError";
    this.code = code;
    this.data = data;
  }
}

export function resolveMuseServeArgv(env = process.env) {
  const executable = env.MUSE_EXECUTABLE?.trim() || "muse";
  const args = ["serve"];
  const provider = env.MUSE_AGENT_ACP_PROVIDER?.trim();
  if (provider) args.push("--provider", provider);
  const model = env.MUSE_AGENT_ACP_MODEL?.trim();
  if (model) args.push("--model", model);
  const extra = env.MUSE_AGENT_ACP_SERVE_ARGS?.trim();
  if (extra) {
    let parsed;
    try {
      parsed = JSON.parse(extra);
    } catch {
      throw new MspError("MUSE_AGENT_ACP_SERVE_ARGS must be a JSON array of strings");
    }
    if (!Array.isArray(parsed) || parsed.some((v) => typeof v !== "string")) {
      throw new MspError("MUSE_AGENT_ACP_SERVE_ARGS must be a JSON array of strings");
    }
    args.push(...parsed);
  }
  return { executable, args };
}

export class MspClient {
  constructor({ executable, args, cwd, env = process.env, onNotification, onServerRequest, onExit } = {}) {
    this.pending = new Map();
    this.nextId = 1;
    this.buffer = "";
    this.closed = false;
    this.onNotification = onNotification ?? (() => {});
    this.onServerRequest = onServerRequest ?? (async () => ({}));
    this.onExit = onExit ?? (() => {});
    this.proc = spawn(executable, args, { cwd, env, stdio: ["pipe", "pipe", "inherit"] });
    this.proc.stdout.setEncoding("utf8");
    this.proc.stdout.on("data", (chunk) => this.#onData(chunk));
    this.proc.on("error", (error) => this.#fail(new MspError(`muse serve spawn failed: ${error.message}`)));
    this.proc.on("exit", (code, signal) => {
      this.#fail(new MspError(`muse serve exited (code=${code ?? "null"} signal=${signal ?? "null"})`));
      this.onExit(code, signal);
    });
  }

  #onData(chunk) {
    this.buffer += chunk;
    let idx;
    while ((idx = this.buffer.indexOf("\n")) >= 0) {
      const line = this.buffer.slice(0, idx).trim();
      this.buffer = this.buffer.slice(idx + 1);
      if (line) this.#onLine(line);
    }
  }

  #onLine(line) {
    let msg;
    try {
      msg = JSON.parse(line);
    } catch {
      return; // Non-JSON output never reaches the protocol handlers.
    }
    if (typeof msg?.method === "string" && msg.id !== undefined) {
      // Server-initiated request.
      Promise.resolve()
        .then(() => this.onServerRequest(msg.method, msg.params ?? {}))
        .then((result) => this.#write({ jsonrpc: "2.0", id: msg.id, result: result ?? {} }))
        .catch((error) =>
          this.#write({
            jsonrpc: "2.0",
            id: msg.id,
            error: { code: -32603, message: error?.message ?? "handler failed" },
          }),
        );
      return;
    }
    if (typeof msg?.method === "string") {
      this.onNotification(msg.method, msg.params ?? {});
      return;
    }
    if (msg?.id !== undefined && this.pending.has(msg.id)) {
      const { resolve, reject } = this.pending.get(msg.id);
      this.pending.delete(msg.id);
      if (msg.error) reject(new MspError(msg.error.message ?? "MSP error", { code: msg.error.code, data: msg.error.data }));
      else resolve(msg.result);
    }
  }

  #write(obj) {
    if (!this.closed) this.proc.stdin.write(JSON.stringify(obj) + "\n");
  }

  #fail(error) {
    if (this.closed) return;
    this.closed = true;
    for (const { reject } of this.pending.values()) reject(error);
    this.pending.clear();
  }

  request(method, params) {
    if (this.closed) return Promise.reject(new MspError("muse serve connection is closed"));
    const id = this.nextId++;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.#write({ jsonrpc: "2.0", id, method, params });
    });
  }

  notify(method, params) {
    this.#write({ jsonrpc: "2.0", method, params });
  }

  close() {
    if (this.closed) return;
    this.#fail(new MspError("muse serve connection closed by adapter"));
    try {
      this.proc.stdin.end();
    } catch { /* already gone */ }
    this.proc.kill("SIGTERM");
  }
}
