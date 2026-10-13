#!/usr/bin/env node
// Standalone muse-agent-acp entry (the argv an ACP client registry runs).
// The implementation lives in bridge/muse-acp/adapter/ so the prepared
// SaariusSkills runtime tree resolves @agentclientprotocol/sdk from the
// muse-acp bridge's own node_modules.
import "../muse-acp/adapter/server.mjs";
