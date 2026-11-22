---
name: re-tpus
description: Reverse engineer Edge and Cloud TPUs (Tensor G5/G6, Colab/GCP v5e, v6e, tpu7x), run differential ISA/VFIO/causal-falsification probes, and build clean-room /dev/vfio/* drivers and C++17 PJRT/GGML runtimes.
---

# Reverse Engineering TPUs (`re-tpus`)

Methodology, silicon traps, runtime patterns, and multi-agent orchestration playbook distilled across clean-room Edge TPU (`buenos_a0`) bare-metal bring-up (`libopenbuenos`, `ggml-edgetpu`) and Cloud TPU (`v5e`, `v6e`, `tpu7x`) exploration (`ggml-cloudtpu`, `libopentpu.so`).

**Goal:** Break proprietary userspace lock-in (`libedgetpu*`, `libtpu.so`, Python/JAX) by shipping clean-room, bit-exact C11/C++17 drivers and `llama.cpp` backends proved directly on physical silicon.

## The 7-Stage TPU RE Loop

1. **Surface & Topology Recon (Never Hardcode BDFs or Assumptions)**
   - Scan `/sys/bus/pci/devices/*` for `vendor=0x1ae0`, `class=0xff0000`, `driver=vfio-pci` -> resolve `iommu_group` -> `/dev/vfio/<group>` (Cloud TPU), or inspect kernel UAPI headers and `/dev/edgetpu-soc` (Edge TPU). On `v6e-1`, `0000:00:05.0` is gVNIC (`0x1ae0:0x0042`), not the TPU.
   - Pre-scan large vendor binaries (`75–600 MB`) with `llvm-readelf`, `llvm-nm`, `llvm-objdump`, and string/protobuf/TOC walkers before heavyweight decompilation (`morluto/rea` or Ghidra).
2. **Compiler / Proprietary Driver as Black-Box Oracle**
   - Treat `libtpu.so` (`GetPjrtApi()`) and `libedgetpu_tflite_compiler.so` as reference oracles. Verify symbols, struct ABI sizes, and dead-code-eliminated paths first (e.g., `LoadCustomKernelDatabase()` stubbed on device; `CompileTfliteFlatbuffer` tail-calling `CompileTfliteFlatbuffer2`).
3. **1-Param Paired-Twin Differential Probes**
   - Feed minimal `1`-op workloads (`add`, `matmul`, `conv2d`, `bf16` cast) varying **one** dimension, dtype, zero-point, or scale factor at a time while holding `.ref.bin` constant where possible.
   - On closed VFIO blobs (`libtpu.so`), pair black-box probes with `VFIO_DEVICE_GET_REGION_INFO`, `VFIO_DEVICE_GET_IRQ_INFO`, non-destructive `BAR` reads, `ptrace`, and MMIO bus taps (`vfio_bus_tap`) to isolate ioctls, doorbells, and DMA rings.
4. **Causal Falsification Before Optimization**
   - When static strings or `.binarypb` configs suggest a fast path (e.g., hardware Huffman `0x0cc0`, native `W4` DMA unpack), design a single **poison/fault falsification probe** before writing runtime code. On `buenos_a0`, raw-fallback poisoning + SMMU faults proved Huffman & `W4` unpack inactive, saving wasted weeks and redirecting effort to SPSC async NEON + `W8A16(FP16)`.
5. **Host Bit-Exact Simulator & `mock_mode=1` First**
   - Lock an FP32/FP64 host simulator (`spline_0x640.py`, `MockPJRT`, `ob_config_t::mock_mode=1`) to `0`-error parity against captured golden outputs before spending scarce silicon or cloud quota.
6. **ABI-First Clean-Room C++17 Runtime & `GGML` Hardening**
   - Freeze the pure C11 header (`openbuenos.h` / `opentpu.h`) first (`-Wall -Wextra -Werror` under C11 & C++17) so upper `ggml-*` lanes build in parallel.
   - Bake in refcounted async DMA/IOVA rings, single-copy weight residency, shape-keyed executable caching (`param_slice` / IOVA descriptor swap), perf-core SPSC async workers, and phase timers (`hw_us` vs `wall_us`).
   - Treat `llama.cpp` `test-backend-ops` (`MUL_MAT`, `MUL_MAT_ID`, strided/broadcast 4D `ADD`, all `ROPE` modes/dtypes, view aliases, `use_counts`) as the non-negotiable parity bar.
7. **Causal Proof, Clean-Room Audit & Teardown**
   - Verify ELF linkage (`llvm-readelf -d` `DT_NEEDED`, `0` vendor `.so` `dlopen`) AND live process maps (`/proc/<pid>/maps`: `MAPS_GOOGLE=0`, `MAPS_LIBTPU=0`, `MAPS_LIBPYTHON=0`).
   - Run automated CI clean-room audits before every commit, tear down ephemeral Colab/GCP runtimes (`0` idle burn), and land critical-path PRs serially.

## Non-Negotiable Rules

- **Silicon & Process Proof:** Never claim bare-metal execution or Python removal without `DT_NEEDED`, `/proc/<pid>/maps`, and exact `max_abs_err` / `NMSE` proof.
- **Isolated Worktrees Always:** Never edit a repository's main checkout directly. Use an isolated branch/worktree per writer and keep raw captures out of tracked history.
- **Clean-Room OSS Boundary:** Public repositories contain only original code, specs, offline tests, and sanitized summaries — zero `.so`/`.bin`/`.dgc0`/ELF blobs, zero decompiled vendor source, zero local home paths, personal emails, or project IDs.
- **Compute Cost Hygiene:** Prefer `mock_mode=1` locally, then zero-spend Colab R&D runtimes (`V5E1` primary) with auto-stop + strict remote cleanup. Escalate to Flex-Start/Spot cloud VMs only with explicit owner approval when `dmesg`, eBPF, or multi-chip ICI is required.

## Reference Routing (`references/`)

Read only the references needed for your current task:

| Reference | Read When... |
| --- | --- |
| [`references/differential-isa-vfio-re.md`](./references/differential-isa-vfio-re.md) | Dissecting `.dgc0`/VLIW/MMIO packets, using `rea` / compiler-oracle / `ptrace` VFIO taps, running 1-param differential sweeps, or designing causal falsification probes. |
| [`references/cloud-tpu-colab-gcp-pjrt.md`](./references/cloud-tpu-colab-gcp-pjrt.md) | Targeting Cloud TPUs (`v5e`, `v6e`, `tpu7x`), probing `/dev/vfio/*`, driving headless Colab (`colab` CLI / MCP) or GCP VMs/quotas/CDI, calling `GetPjrtApi()` / `StableHLO` in C++, or running bare-metal `v5e-1` direct-in-IMEM execution without `libtpu.so`. |
| [`references/native-runtime-ggml-perf.md`](./references/native-runtime-ggml-perf.md) | Designing `libopentpu` / `libopenbuenos`, fixing weight-cache thrashing or handle caps, building `ggml-cloudtpu` / `ggml-edgetpu` / `ggml-rpc`, tuning quantization/SwiGLU/W8A16/SPSC, or avoiding review regressions. |
| [`references/orchestration-swarm-cleanroom.md`](./references/orchestration-swarm-cleanroom.md) | Choosing `/swarm` vs independent parallel sessions, coordinating tracks around a C ABI seam, passing clean-room CI, qualifying models against hardware truth, or landing stacked PRs. |
