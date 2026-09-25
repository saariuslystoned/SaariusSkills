# Optional local-model Parallels lane — research recommendation

Date: 2026-09-21  
Status: provisional synthesis; no VM or live inference proof performed.  
Parent plan: `plans/puppet/vm-wrapper-plan-20260921.md` at `df52f452d4ece595255f5614efa01ab620bc0df3`.

## Recommendation

Go for an optional, late-stage architecture-2 proof: keep the ACP-capable coding harness in the guest, run inference natively on the Mac host, and expose one narrowly scoped, authenticated model endpoint to that guest. Start with an ACPX custom launcher for OpenCode plus Ollama or `llama-server`; use a small non-secret fixture and a locally loaded coding model. This can avoid placing a cloud-provider credential in the VM, but it does not eliminate trust, authorization, workspace-content exposure, or host network risk.

Do not make guest-local inference the default. Parallels documents virtual graphics acceleration, but the sources reviewed do not establish guest access to Apple Metal/MPS/MLX compute or CUDA. Do not claim that Cursor or Antigravity can consume arbitrary local models: their ACP readiness proves their ACP routes, not a local-provider interface. Do not treat an OpenAI-compatible endpoint as ACP or as a tool-capable coding agent.

The first proof is a conditional GO only after the exact host chip, macOS, Parallels edition/version, guest OS, network path, model, quantization, and context budget are recorded. Current hardware facts are intentionally unknown.

## Verified documentation versus inference

### Verified

- The current ACPX main snapshot used by the research worker is `b224278f3e34a61668964b879efe4d37b17571cb` (release `v0.18.0`), and its registry includes `opencode` → `npx -y opencode-ai acp` and `qwen` → `qwen --acp`, alongside the other named adapters. ACPX also documents custom launchers and session scope by resolved command. Source: <https://github.com/openclaw/acpx/blob/b224278f3e34a61668964b879efe4d37b17571cb/docs/agents.md> and <https://github.com/openclaw/acpx/blob/b224278f3e34a61668964b879efe4d37b17571cb/docs/custom-agents.md>.
- OpenCode documents `opencode acp` as an ACP agent speaking newline-delimited JSON-RPC over stdio and using a private OpenCode server for that process. Source: <https://opencode.ai/v2/docs/cli/acp/>.
- OpenCode documents local Ollama, LM Studio, and llama.cpp providers through OpenAI-compatible base URLs. Its provider documentation also warns that tool calls may need a larger Ollama context and exposes model/provider configuration. Source: <https://opencode.ai/docs/providers>.
- Ollama documents OpenAI-compatible chat-completions support including tools, vision, streaming, and reasoning controls; its local API on `http://localhost:11434` does not require authentication. Source: <https://github.com/ollama/ollama/blob/main/docs/api/openai-compatibility.mdx> and <https://github.com/ollama/ollama/blob/main/docs/api/authentication.mdx>.
- llama.cpp documents an OpenAI-compatible server, function calling/tool use, multimodal support, parallel decoding, and CORS/API-key guidance. Its tool/MCP features run code with server privileges and are not a sandbox. Source: <https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md>.
- Ollama documents Metal GPU acceleration on Apple devices. MLX documents Apple-silicon CPU/GPU devices, unified memory, and macOS 14+ requirements. Source: <https://github.com/ollama/ollama/blob/main/docs/gpu.mdx>, <https://ml-explore.github.io/mlx/build/html/usage/unified_memory.html>, and <https://ml-explore.github.io/mlx/build/html/install.html>.
- Parallels documents that the VM does not access the Mac's physical graphics card directly; it uses a virtual adapter and translation for graphics acceleration. Its current system-requirements page lists Apple-silicon ARM guests and edition/version-dependent support. Source: <https://kb.parallels.com/en/122807> and <https://kb.parallels.com/en/131103>.
- Apple documents graphics devices and a ParavirtualizedGraphics framework for macOS virtualization, but those pages do not prove that an arbitrary Parallels guest exposes Metal compute or MPS/MLX-compatible acceleration to a model runtime. Source: <https://developer.apple.com/documentation/virtualization/graphics> and <https://developer.apple.com/documentation/paravirtualizedgraphics>.
- Qwen Code documents OpenAI-compatible local self-hosted endpoints such as Ollama, vLLM, and LM Studio, with model-provider configuration and tool-capable agent routing. Source: <https://github.com/QwenLM/qwen-code/blob/main/docs/users/configuration/model-providers.md>.

### Estimates and hypotheses

- Rough resident weight sizes are parameter-count × bytes/parameter plus metadata/runtime overhead: Q4 commonly begins near 0.5 bytes/parameter, so 7B ≈ 3.5–5 GiB, 14B ≈ 7–10 GiB, 32B ≈ 16–22 GiB, and 70B ≈ 35–50 GiB. BF16 is roughly 2 bytes/parameter before overhead. These are planning ranges, not measured model sizes.
- KV cache is model-architecture-, dtype-, context-, and concurrency-dependent. A useful planning formula is `2 × layers × KV-heads × head-dim × bytes-per-KV-element × tokens × sequences`; at long context it can consume several to tens of GiB even when weights fit. The formula is illustrative, not a universal benchmark.
- A “128GB M5 MacBook” describes host unified memory, not 128GB of guest GPU memory. Guest-assigned RAM and host-native model memory draw from the same physical pool; macOS, Parallels, the guest, model weights, KV cache, filesystem cache, and other VMs contend for it. Exact M5 SKU/core count, memory bandwidth, and usable headroom are unknown.
- Quality and tool reliability are likely to decline before raw model loading fails: quantization, context truncation, malformed tool calls, weak planning, and long-turn drift matter more than a successful `/v1/chat/completions` smoke test. No tokens/sec or model maximum is claimed.

## Architecture comparison

| Architecture | Documented support | Practical limits | Auth/trust implication | Verdict |
| --- | --- | --- | --- | --- |
| 1. Harness + inference inside guest | CPU inference is generally possible in software; MLX has a Linux CPU package. Parallels graphics support is not proof of Metal/MPS/CUDA compute. | Guest CPU-only inference is likely too slow for long coding tasks; macOS guest GPU compute remains unproven; Windows/Linux virtual GPU support is graphics/API-specific. Guest RAM is a host budget. | No cloud key is needed for a truly local model, but guest still sees workspace and model files. | No-go as default; only a later measured experiment. |
| 2. Harness in guest, model server on Mac host | Strongest documented composition: ACPX custom launcher → OpenCode/Qwen Code ACP → host Ollama/llama.cpp/MLX-compatible HTTP endpoint. Host Ollama and llama.cpp have native local APIs/tool features; OpenCode/Qwen Code document local providers. | Requires a guest-to-host route. The model server must be reachable without exposing the whole host; host memory is shared with the VM; model-specific tool behavior still needs proof. | Avoids cloud-provider credential delivery into guest if the host server is local-only. It does not remove endpoint authorization, prompt/workspace disclosure to host, SSRF/reachability, or host compromise risk. | GO for first optional proof after narrow network/auth design. |
| 3. Harness in guest, inference on separate LAN host | Same protocol composition, with model memory moved off the Mac; OpenCode/Qwen Code support custom remote base URLs. | Adds latency, outages, LAN scheduling, version skew, and multi-tenant isolation. Must prove host identity and endpoint auth. | Strongest resource separation, weakest default privacy/trust boundary; guest contents leave the Mac. | Optional later lane for a deliberately managed inference host. |

## Candidate complete combinations

### Rank 1: OpenCode ACP + host Ollama; optional llama.cpp server variant

Composition: `acpx --agent "opencode acp"` (or a structured custom `argv`) in the guest; OpenCode provider points to the host's Ollama `/v1` endpoint. Replace Ollama with `llama-server` when explicit GGUF, context, parallelism, CORS, API-key, or MCP controls are required.

Why credible: OpenCode is explicitly an ACP server and explicitly documents Ollama and llama.cpp local providers. Ollama and llama.cpp document OpenAI-compatible APIs and tool/function calling. Remaining gaps: the exact guest-to-host route and model-specific tool reliability are untested.

### Rank 2: Qwen Code ACPX custom target + host Ollama/llama.cpp

Composition: `acpx --agent "qwen --acp"` only if the installed Qwen Code build advertises the expected ACP mode; configure its documented OpenAI-compatible provider against the host server and use a non-secret placeholder only where the local server requires one. This is a candidate, not a claimed ready command: the exact installed Qwen ACP surface and model/tool compatibility must be discovered during proof.

Why credible: Qwen Code documents local self-hosted OpenAI-compatible providers, model-specific configuration, and tool-capable agent routing. Remaining gaps: Qwen's tool behavior varies by model and API dialect; no local run was performed.

## Coding and operations limitations

- Coding competence: small edits, tests, and deterministic fixtures are plausible for a good quantized coding model; repository-scale refactors and subtle debugging are not inferred from API compatibility.
- Long tasks/context: weights are only the first memory term. KV cache grows with context and concurrency; a 128k configuration can consume materially more memory than a 16k run depending on architecture. Set and verify a modest context first.
- Tools: ACP gives the harness transport and session/tool envelope. The model endpoint only returns text/tool calls; the harness executes file and terminal tools. A local model that emits malformed or semantically poor tool calls can fail despite a healthy ACP handshake.
- Vision/computer use: Ollama/llama.cpp may document multimodal inputs, but this does not confer desktop/computer-use semantics or an ACP computer-use capability. Keep visual proof as a later, separate lane.
- Concurrency: one VM plus one model server first. Parallel guests multiply KV cache and host memory pressure; do not extrapolate single-run success to fan-out.
- Offline/privacy/licensing: weights can be local and cloud credentials absent, but model licenses vary; local server logs, prompt contents, model files, and host telemetry still require policy review. A LAN endpoint is not “offline.”

## Smallest safe proof

Prerequisites, recorded without secrets: exact host chip/memory, macOS, Parallels version/edition, guest OS/architecture, guest RAM/vCPU, model/server/harness versions, quantization, context/concurrency limits, and the guest-to-host endpoint path. Do not change networking as part of this research task.

1. Use one disposable non-secret fixture and one guest ACP custom launcher for OpenCode.
2. Run Ollama or llama.cpp natively on the Mac host with one already-approved local coding model; no cloud fallback or provider credential in the guest.
3. Expose only the required endpoint to the guest through the existing host/guest route, with an explicit authorization boundary. Do not bind a no-auth local API broadly.
4. Prove ACP initialize/session creation, one model response, one file edit, one test, and one intentional tool call. Capture endpoint/model identity, logs without content/secrets, patch, and independent test output.
5. Independently verify that the guest cannot reach unrelated host services, the server made no cloud request, the model/tool call stayed within the fixture, and all guest/harness/server processes are terminated.
6. Repeat once with a distinct run identity before considering the lane repeatable.

Acceptance criteria: same-task ACP/session/workspace identities; local-only inference; no cloud credential or auth file in the guest; successful edit/test; bounded context/memory; explicit endpoint authorization; independent cleanup; and no unresolved remote cleanup or reachability finding.

Go/no-go: GO for architecture 2 after all criteria pass. NO-GO for architecture 1 if compute acceleration is merely inferred from graphics support, if the model server cannot enforce a narrow endpoint, if tool calls are unreliable, if memory contention causes eviction/OOM, or if any cloud path is unproven. Stop and retain the fence on disconnect or cleanup uncertainty, following the parent VM plan.

## Top unknowns

1. Exact M5 SKU, host memory pressure, and available headroom under Parallels plus native inference.
2. Exact Parallels edition/version and guest OS; current docs do not establish guest Metal/MPS/MLX/CUDA compute.
3. Whether the selected installed OpenCode/Qwen build and pinned ACPX revision accept the custom launcher as expected.
4. Guest-to-host routing and authorization semantics in the chosen Parallels network mode.
5. Model-specific tool-call format, context/KV behavior, and coding quality under the chosen quantization.
6. Whether the host server has any configured cloud fallback, telemetry, or persistence that violates the intended privacy policy.

## Worker evidence

Worker reports are required corroboration, not authority over these claims:

- Cursor/Grok lane: job `17c86fb8-7eb0-46c9-bcdb-11c801a739ac`, workspace `/Users/bobbybones/.codex/worktrees/ead7-cursor-local-model-research`, route readiness resolved to `grok-4.6[effort=high,fast=true]`; canonical result `completed`, cleanup `CLEANUP_READY`; worker report at `runs/20260921-local-model-cursor/REPORT.md`.
- Antigravity lane: job `9eede715-5b6e-41b0-883d-5f59e03f206e`, workspace `/Users/bobbybones/.codex/worktrees/ead7-agy-local-model-research`, route pin `antigravity-acp 1.1.1` / `acpx 0.17.1`, model `gemini-3.8-flash-high`, effort omitted; canonical result `completed`, cleanup `CLEANUP_READY`; worker report at `/Users/bobbybones/.codex/worktrees/ead7-agy-local-model-research/runs/20260921-local-model-agy/REPORT.md`.

### Worker adjudication

Accepted corroboration from both lanes: OpenCode/Qwen are credible ACP harness choices when paired with a documented local OpenAI-compatible provider; Cursor and Antigravity are not thereby converted into arbitrary-local-model harnesses; host-native inference is the practical default; and no live VM/inference proof was performed.

Not carried as verified facts: the Antigravity report's exact Metal working-set percentage, Parallels edition/RAM caps, claims that all guest OSes have no usable compute path, exact 10–16× slowdowns, exact model footprints/headroom, specific model quality claims, and the assertion that an SSH reverse tunnel is the only safe topology. Those require version-specific primary evidence or measurement. They remain hypotheses/possible proof inputs, not acceptance claims. The report's claimed repository test run is unrelated to local-model feasibility and was not used as proof.

Antigravity cleanup was observed as local worker termination while backend session discard was unsupported; the bridge still returned `cleanupReady:true`. No replacement was started.

## Checkpoint

- Branch: `codex/puppet-local-model-research-20260921`
- Worktree: `/Users/bobbybones/.codex/worktrees/ead7/SaariusSkills`
- Final head: `5df9864`
- Draft PR: <https://github.com/saariuslystoned/SaariusSkills/pull/67>
- Merge: not performed.
