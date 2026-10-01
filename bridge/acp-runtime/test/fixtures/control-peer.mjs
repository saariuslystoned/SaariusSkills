// Provider-free wire peer. Each launch owns its own state and a reused backend ID.
import { appendFileSync, existsSync, writeFileSync } from "node:fs";
import { createInterface } from "node:readline";
const [scenario, trace, marker] = process.argv.slice(3);
const exact = "fixture-model[reasoning=medium]";
let selected = "old-model";
const option = () => ({ id: "model", name: "Model", type: "select", currentValue: selected,
  options: [{ value: "old-model", name: "Old" }, { value: exact, name: "Fixture" }] });
const catalog = () => ({ models: { currentModelId: selected,
  availableModels: [{ modelId: "old-model", name: "Old" }, { modelId: exact, name: "Fixture" }] },
  ...(scenario === "alias" ? {} : { configOptions: [option()] }) });
const send = message => process.stdout.write(JSON.stringify(message) + "\n");
const reply = (id, result) => send({ jsonrpc: "2.0", id, result });
const update = configOptions => send({ jsonrpc: "2.0", method: "session/update", params: {
  sessionId: "reused-backend", update: { sessionUpdate: "config_option_update", configOptions } } });
createInterface({ input: process.stdin }).on("line", line => {
  const { id, method, params } = JSON.parse(line);
  appendFileSync(trace, JSON.stringify({ pid: process.pid, method, value: params?.value ?? params?.modelId }) + "\n");
  if (id === undefined) return;
  if (method === "initialize") return reply(id, { protocolVersion: params.protocolVersion,
    agentCapabilities: { loadSession: true, sessionCapabilities: { close: {} } }, authMethods: [] });
  if (method === "session/new" || method === "session/load") {
    const result = { ...(method === "session/new" ? { sessionId: "reused-backend" } : {}), ...catalog() };
    if (scenario === "startup" || scenario === "removed") {
      const latest = scenario === "removed" ? [] : [option()];
      // Smoke delivery after the response; this does not prove the owned
      // creation window. Independent review retains that qualification blocker.
      setTimeout(() => update(latest), 0);
      result.configOptions = scenario === "removed" ? [option()]
        : [{ ...option(), options: [{ value: "old-model", name: "Old" }] }];
      delete result.models;
    }
    return reply(id, result);
  }
  if (method === "session/set_config_option" || method === "session/set_model") {
    if (scenario === "timeout" && existsSync(marker)) return;
    selected = params.value ?? params.modelId;
    // Deliberately omit the catalog/current value: accepted alias must resolve.
    if (scenario === "non-list") return reply(id, { configOptions: null });
    if (scenario === "omitted" || scenario === "alias") return reply(id, {});
    return reply(id, { ...(scenario === "alias" ? {} : { configOptions: [option()] }) });
  }
  if (method === "session/prompt") {
    if (scenario === "timeout") writeFileSync(marker, "timeout-on-next-selection");
    send({ jsonrpc: "2.0", method: "session/update", params: { sessionId: params.sessionId,
      update: { sessionUpdate: "agent_message_chunk", content: { type: "text", text: selected } } } });
    reply(id, { stopReason: "end_turn" });
    if (["alias", "omitted", "non-list", "timeout"].includes(scenario)) setTimeout(() => process.exit(0), 20);
    return;
  }
  return reply(id, {});
});
