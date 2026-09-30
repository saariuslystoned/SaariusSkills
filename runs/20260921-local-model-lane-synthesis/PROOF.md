# PROOF

## Local evidence

- `git log -1 --oneline` at start: `df52f45 Merge pull request #65 ...`.
- Parent plan read from `plans/puppet/vm-wrapper-plan-20260921.md`.
- Cursor ACP readiness: ready; exact route `/Users/bobbybones/.local/bin/cursor-agent acp`; selected model `grok-4.6[effort=high,fast=true]`.
- Antigravity ACP readiness: ready; pinned runtime `antigravity-acp 1.1.1`, `acpx 0.17.1`; selected model `gemini-3.8-flash-high`; effort unsupported; personal OAuth session opened, no API key/cloud credentials present, Ultra attribution unclaimed.
- Worker jobs submitted with bounded `480000ms` timeouts and separate detached worktrees.
- Cursor canonical result observed: `completed`, `complete:true`, handoff says `CLEANUP_READY`; worker report identifies ACPX main `b224278f3e34a61668964b879efe4d37b17571cb` and release `v0.18.0`.
- Antigravity canonical result observed: `completed`, `taskComplete:true`, `cleanupReady:true`; cleanup observed as local worker termination; backend session discard was unsupported but did not prevent cleanup-ready completion.
- Final artifact checks: required run files present; `git diff --check` passed; no VM/model/network/credential/upstream operation performed.
- Final checkpoint: branch `codex/puppet-local-model-research-20260921`, worktree `/Users/bobbybones/.codex/worktrees/ead7/SaariusSkills`, head `5df9864`, draft PR <https://github.com/saariuslystoned/SaariusSkills/pull/67>; PR attached to the task.

## Primary source set

- ACPX registry and custom agents: <https://github.com/openclaw/acpx/blob/main/docs/agents.md>
- ACPX CLI/custom agent semantics: <https://github.com/openclaw/acpx/blob/main/docs/CLI.md>
- OpenCode ACP: <https://opencode.ai/v2/docs/cli/acp/>
- OpenCode local providers: <https://opencode.ai/docs/providers>
- Ollama OpenAI compatibility: <https://github.com/ollama/ollama/blob/main/docs/api/openai-compatibility.mdx>
- Ollama GPU support: <https://github.com/ollama/ollama/blob/main/docs/gpu.mdx>
- llama.cpp server: <https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md>
- MLX install and unified memory: <https://ml-explore.github.io/mlx/build/html/install.html>, <https://ml-explore.github.io/mlx/build/html/usage/unified_memory.html>
- Parallels GPU boundary: <https://kb.parallels.com/en/122807>
- Parallels Desktop 26 requirements/guest OS list: <https://kb.parallels.com/en/131103>
- Apple Virtualization graphics API: <https://developer.apple.com/documentation/virtualization/graphics>
- Qwen Code local provider support: <https://github.com/QwenLM/qwen-code/blob/main/docs/users/configuration/model-providers.md>
