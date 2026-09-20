import path from "node:path";
import { homedir } from "node:os";

export const RUNTIME_ID = "antigravity-acp";
export const RUNTIME_VERSION = "1.1.1";
export const REGISTRY_REVISION = "81bf71b55e15f630c4fb8a86d20d3088071d2071";
export const ACPX_SOURCE_COMMIT = "50a47ad10a75431cbc276ec9b555d11fe1f69c84";
export const ACPX_RELEASE = "0.17.1";
export const PROFILE_ENV = "GEMINI_HOME";
export const AUTH_MODE = "oauth-personal";
export const DEFAULT_STATE_DIR_NAME = "antigravity-acp-delegation";
export const DEFAULT_PROFILE_DIR_NAME = "gemini-home";

export const RUNTIME_PIN = Object.freeze({
  id: RUNTIME_ID,
  version: RUNTIME_VERSION,
  registryRevision: REGISTRY_REVISION,
  acpxSourceCommit: ACPX_SOURCE_COMMIT,
  acpxRelease: ACPX_RELEASE,
});

export const PLATFORM_COMMANDS = Object.freeze({
  "darwin-aarch64": {
    runtimeCommand: "./agy_acp_server.par",
    runtimeArgs: [],
    helper: "localharness_external",
  },
  "linux-aarch64": {
    runtimeCommand: "./agy_acp_server.par",
    runtimeArgs: ["--uid="],
    helper: "localharness_external",
  },
  "linux-x86_64": {
    runtimeCommand: "./agy_acp_server.par",
    runtimeArgs: ["--uid="],
    helper: "localharness_external",
  },
  "windows-aarch64": {
    runtimeCommand: "./agy_acp_server.exe",
    runtimeArgs: [],
    helper: "localharness_external.exe",
  },
  "windows-x86_64": {
    runtimeCommand: "./agy_acp_server.exe",
    runtimeArgs: [],
    helper: "localharness_external.exe",
  },
});

export const PLATFORM_ARCHIVES = Object.freeze({
  "darwin-aarch64":
    "https://dl.google.com/agy-extensions/releases/macos/agy-acp-server-agy_acp_server_1.1.1-darwin-arm64.zip",
  "linux-aarch64":
    "https://dl.google.com/agy-extensions/releases/linux/agy-acp-server-agy_acp_server_1.1.1-linux-arm64.zip",
  "linux-x86_64":
    "https://dl.google.com/agy-extensions/releases/linux/agy-acp-server-agy_acp_server_1.1.1-linux-x86_64.zip",
  "windows-aarch64":
    "https://dl.google.com/agy-extensions/releases/windows/agy-acp-server-agy_acp_server_1.1.1-windows-arm64.zip",
  "windows-x86_64":
    "https://dl.google.com/agy-extensions/releases/windows/agy-acp-server-agy_acp_server_1.1.1-windows-x86_64.zip",
});

export const FORBIDDEN_ENV_NAMES = Object.freeze([
  "GEMINI_API_KEY",
  "GOOGLE_API_KEY",
  "GOOGLE_CLOUD_PROJECT",
  "CLOUDSDK_CORE_PROJECT",
  "GCLOUD_PROJECT",
  "GOOGLE_APPLICATION_CREDENTIALS",
  "ANTIGRAVITY_API_KEY",
  "GOOGLE_GENAI_USE_VERTEXAI",
]);

export const BODY_KEYS = Object.freeze([
  "prompt",
  "output",
  "content",
  "text",
  "transcript",
  "title",
  "options",
]);

export const TOOL_NAMES = Object.freeze([
  "antigravity_acp_readiness",
  "antigravity_acp_delegate",
  "antigravity_acp_status",
  "antigravity_acp_result",
  "antigravity_acp_steer",
  "antigravity_acp_cancel",
]);

export function currentPlatformId(platform = process.platform, arch = process.arch) {
  const os =
    platform === "darwin"
      ? "darwin"
      : platform === "win32"
        ? "windows"
        : platform === "linux"
          ? "linux"
          : platform;
  const cpu = arch === "arm64" ? "aarch64" : arch === "x64" ? "x86_64" : arch;
  return `${os}-${cpu}`;
}

export function platformLaunch(platformId = currentPlatformId()) {
  const launch = PLATFORM_COMMANDS[platformId];
  if (!launch) return undefined;
  return {
    platformId,
    runtimeCommand: launch.runtimeCommand,
    runtimeArgs: [...launch.runtimeArgs],
    helper: launch.helper,
    archive: PLATFORM_ARCHIVES[platformId],
  };
}

export function defaultGeminiHome() {
  return path.join(
    homedir(),
    ".local",
    "state",
    "saarius-skills",
    "antigravity-acp",
    DEFAULT_PROFILE_DIR_NAME,
  );
}

export function defaultStateRoot() {
  return path.join(homedir(), ".local", "state", "saarius-skills", DEFAULT_STATE_DIR_NAME);
}

export function settingsPath(geminiHome) {
  return path.join(geminiHome, "antigravity-acp", "settings.json");
}

export function presentForbiddenEnvNames(env = process.env) {
  return FORBIDDEN_ENV_NAMES.filter((name) => {
    const value = env[name];
    return typeof value === "string" && value.trim().length > 0;
  });
}

export function runtimeRepair(platformId = currentPlatformId()) {
  const launch = platformLaunch(platformId);
  if (!launch) {
    return [
      `This host platform ${platformId} is not in the pinned antigravity-acp 1.1.1 launch contract.`,
    ];
  }
  return [
    `Download the pinned antigravity-acp ${RUNTIME_VERSION} archive for ${platformId}: ${launch.archive}`,
    `Extract it to a durable directory and keep ${path.basename(launch.runtimeCommand)} plus ${launch.helper} from that same release together.`,
    `chmod +x both files on Linux/macOS. Do not let setup download or update them.`,
    `Set ANTIGRAVITY_ACP_RUNTIME_DIR to that directory, or ANTIGRAVITY_ACP_SERVER to the absolute runtime path.`,
    `Set ANTIGRAVITY_HARNESS_PATH to the absolute matching helper if it is not beside the runtime.`,
    `Set GEMINI_HOME to an explicit dedicated profile. Complete personal Google OAuth in an interactive ACP client using that profile.`,
    `Write ${path.join("<GEMINI_HOME>", "antigravity-acp", "settings.json")} with {"auth":{"type":"oauth-personal"},"useG1Credits":false}.`,
    "Remove GEMINI_API_KEY, GOOGLE_API_KEY, GOOGLE_CLOUD_PROJECT, GOOGLE_APPLICATION_CREDENTIALS, and other API/Cloud fallback variables from the MCP environment.",
    "Reload Codex or start a fresh task after repair. Do not claim Google AI Ultra quota attribution from this route.",
  ];
}

export function authRepair(geminiHome) {
  return [
    `Use an explicit ${PROFILE_ENV} profile at ${geminiHome}.`,
    `Complete personal Google OAuth in an interactive ACP client that uses this exact ${PROFILE_ENV}.`,
    `Write ${settingsPath(geminiHome)} with {"auth":{"type":"oauth-personal"},"useG1Credits":false}.`,
    "Do not use an API key, Cloud project, alternate account, paid-credit, or overage fallback.",
    "This bridge will not start a login or invent account/entitlement evidence.",
  ];
}
