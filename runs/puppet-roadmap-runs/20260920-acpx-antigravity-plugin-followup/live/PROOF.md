# Live Antigravity ACP smoke proof

Outcome: blocked
Runtime pin: antigravity-acp 1.1.1 / acpx 0.17.1

## Evidence

```json
{
  "pin": {
    "id": "antigravity-acp",
    "version": "1.1.1",
    "registryRevision": "81bf71b55e15f630c4fb8a86d20d3088071d2071",
    "acpxSourceCommit": "50a47ad10a75431cbc276ec9b555d11fe1f69c84",
    "acpxRelease": "0.17.1"
  },
  "geminiHome": "/Users/bobbybones/.local/state/saarius-skills/antigravity-acp/gemini-home",
  "forbiddenEnvNames": [],
  "runtime": {
    "present": false,
    "code": "RUNTIME_MISSING"
  }
}
```

## Bounded blocker

{
  "code": "RUNTIME_MISSING",
  "message": "Pinned antigravity-acp 1.1.1 runtime agy_acp_server.par is not installed",
  "repair": [
    "Download the pinned antigravity-acp 1.1.1 archive for darwin-aarch64: https://dl.google.com/agy-extensions/releases/macos/agy-acp-server-agy_acp_server_1.1.1-darwin-arm64.zip",
    "Extract it to a durable directory and keep agy_acp_server.par plus localharness_external from that same release together.",
    "chmod +x both files on Linux/macOS. Do not let setup download or update them.",
    "Set ANTIGRAVITY_ACP_RUNTIME_DIR to that directory, or ANTIGRAVITY_ACP_SERVER to the absolute runtime path.",
    "Set ANTIGRAVITY_HARNESS_PATH to the absolute matching helper if it is not beside the runtime.",
    "Set GEMINI_HOME to an explicit dedicated profile. Complete personal Google OAuth in an interactive ACP client using that profile.",
    "Write <GEMINI_HOME>/antigravity-acp/settings.json with {\"auth\":{\"type\":\"oauth-personal\"},\"useG1Credits\":false}.",
    "Remove GEMINI_API_KEY, GOOGLE_API_KEY, GOOGLE_CLOUD_PROJECT, GOOGLE_APPLICATION_CREDENTIALS, and other API/Cloud fallback variables from the MCP environment.",
    "Reload Codex or start a fresh task after repair. Do not claim Google AI Ultra quota attribution from this route."
  ]
}

Raw ACP transcripts, prompts, questions, credentials, and auth logs are intentionally not recorded. No login or billing change was attempted.
