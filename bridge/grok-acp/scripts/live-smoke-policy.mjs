import { GrokAcpBroker } from "../broker.mjs";
import {
  BREAK_GLASS_PERMISSION_MODE,
  HostPolicyError,
  PERMISSION_MODE_ENV,
  resolveBinderId,
  resolveHostConversationId,
} from "../host-policy.mjs";

export function requireLiveSmokePermission(env = process.env) {
  const mode = typeof env?.[PERMISSION_MODE_ENV] === "string"
    ? env[PERMISSION_MODE_ENV].trim()
    : "";
  if (mode !== BREAK_GLASS_PERMISSION_MODE) {
    throw new HostPolicyError(
      "LIVE_SMOKE_PERMISSION_REQUIRED",
      `Live smoke requires explicit ${PERMISSION_MODE_ENV}=${BREAK_GLASS_PERMISSION_MODE} break-glass approval`,
      { required: BREAK_GLASS_PERMISSION_MODE },
    );
  }
  return { permissionMode: BREAK_GLASS_PERMISSION_MODE, breakGlass: true };
}

export function resolveLiveSmokeIdentity(env = process.env) {
  return {
    hostConversationId: resolveHostConversationId(undefined, env, "conv-grok-live-smoke"),
    binderId: resolveBinderId(undefined, env, "smoke-owner"),
  };
}

export function createLiveSmokeBroker(options = {}) {
  const processEnv = options.processEnv ?? process.env;
  requireLiveSmokePermission(processEnv);
  const identity = resolveLiveSmokeIdentity(processEnv);
  const broker = new GrokAcpBroker({
    ...options,
    processEnv,
    defaultHostConversationId: options.defaultHostConversationId ?? identity.hostConversationId,
    defaultBinderId: options.defaultBinderId ?? identity.binderId,
  });
  return { broker, ...identity };
}
