# Optional local-model VM lane

Research conclusion for the host-owned Parallels ACP wrapper plan: the credible first shape is architecture 2 — ACP-capable harness in the guest, local inference server on the Mac host, and a narrowly scoped authenticated guest-to-host endpoint. This avoids copying cloud-provider credentials into the VM when the host server is genuinely local-only; it does not remove trust, authorization, workspace-content exposure, or host memory/network risks.

Use the current ACPX `opencode` (`npx -y opencode-ai acp`) or `qwen` (`qwen --acp`) target only after its ACP surface is verified. OpenCode documents both ACP stdio transport and local Ollama/llama.cpp/LM Studio providers. Ollama and llama.cpp document OpenAI-compatible tool-capable APIs. ACPX also documents custom launcher escape hatches; Cursor and Antigravity ACP readiness does not prove arbitrary local-model support.

Do not infer guest Metal/MPS/MLX/CUDA compute from Parallels 3D graphics. Parallels documents virtual graphics and translation rather than direct physical GPU access; exact guest OS, Parallels version/edition, and M5 SKU remain admission inputs. Treat guest-local inference as an experiment, not the default.

The smallest proof is one non-secret fixture, one guest harness, one host-local model, one tool call, one independent test, explicit endpoint authorization, local-only egress evidence, and independent cleanup; repeat once before calling it repeatable. See the full evidence packet at [`runs/20260921-local-model-lane-synthesis/REPORT.md`](../../runs/20260921-local-model-lane-synthesis/REPORT.md).
