# Multi-Agent Orchestration, `/swarm`, & Clean-Room OSS Gate

Operational lessons for scaling TPU reverse engineering across `/swarm` workers, independent parallel sessions, hardware-truth model qualification, and public OSS CI gates.

---

## 1. Orchestration Topology: `/swarm` vs Parallel Independent Sessions

Pairing an **Orchestrator** with `/swarm` (inside one shared repo/device loop) AND parallel independent sessions (for separate long-running deliverables) maximizes throughput without write races:

| Pattern | Use When... | Hard Guardrails |
| --- | --- | --- |
| **Native `/swarm`** (`swarm` tool + shared board) | Parallelizing tightly coupled phases inside one repo (e.g., Phase 0 `intake` -> Phase 1 read-only RE across `kernel-abi/`, `litert-abi/`, `darwinn-isa/`, `gxp-abi/` -> synthesis; or writer + dedicated device runner + verifier). | **One writer** per slice/file (`workspace="share"` for concurrent writers, `inherit` for readers/verifiers); freeze C headers (`openbuenos.h`) first as the contract; **kill stale Phase N workers** before starting Phase N+1 so old assumptions don't drift; dedicate ONE lane for physical hardware access (`/dev/edgetpu-soc` contention breaks concurrent runners). |
| **Parallel Independent Sessions** | Independent deliverables taking 30+ tool steps each (e.g., `libopentpu.so` bare-metal VFIO track alongside `ggml-cloudtpu` PJRT backend track, or separate Colab probes & ops CDI toolkits). | Give each session its own isolated branch/worktree + **separate Colab cache config** (`<lane-unique>/sessions.json`) + explicit upstream ABI seam (`GetPjrtApi()`); keep the main checkout untouched. |
| **Parallel Extraction (`run_workflow`)** | Fan-out read-only synthesis over N transcripts, N binary targets, or N review files (`model="flash"`). | Keep extractors strictly read-only writing only to isolated report paths or returning structured schemas via `finish`. |

---

## 2. Clean-Room OSS & Review Discipline

1. **Maintain a Hard Air-Gap Between Private RE & Public OSS**:
   - Keep raw binary dumps, vendor `.so`/`.bin`/`.dgc0` files, CDP captures, and internal decompilations strictly in private/gitignored storage with SHA-256 manifests.
   - Export ONLY clean-room C/C++ implementations, clean-room hardware register/ABI/ISA specs, synthetic `--self-test` / `mock_mode=1` suites, and sanitized device proof summaries to public repos.
2. **CI Clean-Room Audit Checklist**:
   - Zero forbidden binaries/magic bytes (`.so`, `.ko`, `.img`, `.apk`, `.gguf`, `.tflite`, `.dgc0`, `.dmg0`, `*.bin`, `\x7fELF`, `TFL3`, `GGUF`, `DGC0`, `DWS0`, `DGD0`, `DMG0`).
   - Zero forbidden strings: local home paths, private org names, private device serials/`soc.id`, `file://` links, personal emails, cloud project IDs, internal changelist tags, or internal scratch paths in `docs/`, `tools/`, or `tests/`.
   - **Pre-Public Privacy Sweep**: Always grep before flipping a private repo public and avoid cross-repo URLs until targets are live.
3. **Serialized Critical-Path Landing & Minimal Diffs**:
   - Do **not** blast 6+ interdependent PRs into a single-slot automated review queue concurrently — serialize critical-path PRs (`base -> stacked`).
   - Fix root causes or prune dead wrappers/scripts rather than bolting on defensive layers; check `cmake` availability cleanly (macOS SDK `cmake` often sits outside default non-login `PATH`, so ship working `Makefile` targets alongside `CMakeLists.txt`).

---

## 3. Hardware-Truth Model Qualification (Before Benchmarking or Downloading)

Never trust secondary estimates or model cards alone for RAM or TPU compatibility — verify directly against HF `config.json` + `?blobs=true` GGUF sizes + silicon constraints:

- On Tensor G5 (`buenos_a0`), require `K % 32 == 0` and strict block-32 symmetric quantization (`Q8_0` or `Q4_0`; `< 4-bit` `Q2_K`/`Q3_K`/`IQ*` and mixed QAT fail compiler checks; `*-qat-q4_0-gguf` works).
- Verify true parameter count (e.g., Per-Layer Embeddings `PLE` made `gemma-4-E4B-it` `4.80 GB` `Q4_0`, not `2.25 GB`), true `num_key_value_heads` (`Phi-4-mini` has `kv_heads=8`, needing `1–2 GB` KV at 16k rather than `6.00 GB`), and host LMKD single-copy RAM ceiling (`~11 GiB` per 16 GB phone vs `~30.4 GiB` across dual-Pixel RPC).

---

## 4. Silicon Target Quick Reference

| Target | Userspace Interface | Key Verified Facts & Envelope |
| --- | --- | --- |
| **Pixel Tensor G5 (`buenos_a0`)** | `/dev/edgetpu-soc` (Litebuf VII `0xED`) + `/dev/dma_heap/system` | RV64 X280 DIVE VM (`ext[1]`), `1,286.4 MHz` DVFS + WakeLock, `~27.96 GB/s` INT8 ceiling (`W4`/Huffman DMA inactive), native `W8A16(FP16/BF16)`, `libopenbuenos` + `ggml-edgetpu` |
| **Pixel Tensor G6** | Cross-gen diff baseline (`vendor`/`KERNEL_ABI`) | Next edge target beyond `buenos_a0`'s 1 B/weight decode ceiling |
| **Cloud TPU `v5e-1`** | `/dev/vfio/<group>` (`0x1ae0:0x0063`, `class=0xff0000`) | `BAR0=4 GiB`, `BAR4=16 MiB`, `128` MSI-X, `15.748 GiB` HBM2e (`656 GB/s`), `~180 TF/s` BF16 / `~357 TOPS` INT8, `~127 us` PJRT sync / `32 us` pipelined |
| **Cloud TPU `v6e` (Trillium)** | `/dev/vfio/<group>` (`0x1ae0:0x006f`; note `00:05.0` may be gVNIC `0x0042`) | `31.25 GiB`/chip HBM (`250 GiB` on `v6e-8`), requires `IPC_LOCK` + unlimited `memlock` + `--net=host` CDI |
| **Cloud TPU `tpu7x` (Ironwood)** | VFIO / PJRT (`GetPjrtApi()`) | Next datacenter target; needs Workspace/org quota & `tpu.googleapis.com` aware provisioning |
