#!/usr/bin/env node

import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { AntigravityAcpBroker } from "./broker.mjs";
import { createAntigravityMcpServer } from "./tools.mjs";
import { createShedMcpServer } from "./shed-tools.mjs";
import { ShedTaskRunner } from "./shed-tasks.mjs";
import { createAccessAuthenticator, createViewerAuthenticator } from "./access-auth.mjs";
import { resolveTransport, startRemoteShedHost } from "./http-host.mjs";

const transportMode = resolveTransport({ argv: process.argv.slice(2), env: process.env });
const broker = await new AntigravityAcpBroker().init();

let closeHost = async () => {};
let museBroker;
if (transportMode === "http") {
  // Remote shed: Streamable HTTP on loopback only, published by the
  // operator's Cloudflare Tunnel + Access. Only the narrow shed_task_* tools
  // are served; broker contracts (pinned runtime, oauth-personal, no API-key
  // fallback, permission mode from this process env) are unchanged.
  const { MuseAcpBroker } = await import("../muse-acp/broker.mjs");
  museBroker = await new MuseAcpBroker().init();
  const authenticate = createAccessAuthenticator({ env: process.env });
  const runner = await new ShedTaskRunner({
    brokers: { antigravity: broker, muse: museBroker },
    env: process.env,
  }).init();
  const host = await startRemoteShedHost({
    env: process.env,
    bridge: "antigravity-acp",
    authenticate,
    // Read-only session viewer; disabled (404) unless the viewer Access env is set.
    viewerAuthenticate: createViewerAuthenticator({ env: process.env }),
    viewSession: (sessionId) => runner.viewSession(sessionId),
    createServer: (caller) => createShedMcpServer(runner, caller),
  });
  closeHost = host.close;
} else {
  const server = createAntigravityMcpServer(broker);
  await server.connect(new StdioServerTransport());
}

const shutdown = async () => {
  await closeHost();
  await Promise.allSettled([broker.close(), museBroker?.close?.()]);
  process.exit(0);
};
process.once("SIGINT", shutdown);
process.once("SIGTERM", shutdown);
