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
const notice = configOptions => JSON.stringify({ jsonrpc: "2.0", method: "session/update", params: {
  sessionId: "reused-backend", update: { sessionUpdate: "config_option_update", configOptions } } });
const oldOnly = () => [{ ...option(), options: [{ value: "old-model", name: "Old" }] }];
createInterface({ input: process.stdin }).on("line", line => {
  const { id, method, params } = JSON.parse(line);
  appendFileSync(trace, JSON.stringify({ pid: process.pid, method, value: params?.value ?? params?.modelId }) + "\n");
  if (id === undefined) return;
  if (method === "initialize") return reply(id, { protocolVersion: params.protocolVersion,
    agentCapabilities: { loadSession: true, sessionCapabilities: { close: {} } }, authMethods: [] });
  if (method === "session/new" || method === "session/load") {
    const result = { ...(method === "session/new" ? { sessionId: "reused-backend" } : {}), ...catalog() };
    // Exec applies the session/new snapshot. A later notification is not ordered
    // against that snapshot, so startup/removed advertise the initial catalog only.
    if (scenario === "startup" || scenario === "bound-remove") result.configOptions = [option()];
    if (scenario === "removed" || scenario === "bound-add") result.configOptions = oldOnly();
    if (scenario === "startup" || scenario === "removed" || scenario === "bound-add" || scenario === "bound-remove") delete result.models;
    return reply(id, result);
  }
  if (method === "session/set_mode" && (scenario === "bound-add" || scenario === "bound-remove")) {
    const response = JSON.stringify({ jsonrpc: "2.0", id, result: {} });
    // set_mode is sent only after ensureSession binds. One write is handled
    // before that request continuation, so the catalog change is owned.
    process.stdout.write(notice(scenario === "bound-remove" ? [] : [option()]) + "\n" + response + "\n");
    return;
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
