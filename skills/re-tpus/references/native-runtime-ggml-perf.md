# Native C++17 Runtime, GGML Backends & Review Hardening

Architectural invariants, performance breakthroughs, and bug classes caught across clean-room C++ TPU runtimes (`libopenbuenos` -> `libopentpu`), `llama.cpp` GGML backends (`ggml-edgetpu`, `ggml-cloudtpu`, `ggml-rpc`), and iterative automated code reviews.

---

## 1. Core Clean-Room C++ Driver/Runtime Pattern (`libopenbuenos` -> `libopentpu`)

1. **Freeze the Pure C11 Public ABI First**:
   - Design `include/openbuenos.h` / `include/opentpu.h` cleanly (`context`, `buffer`, `graph`, `exec_handle`) and verify it with `clang -x c -std=c11 -fsyntax-only -Wall -Wextra -Werror`, `clang++ -x c++ -std=c++17`, and a C11 consumer shim (`openbuenos_shim.c`). Parallel `ggml-*` lanes build concurrently against the frozen header or `mock_mode`.
2. **Offline `mock_mode=1` Inside the Runtime**:
   - Wire `mock_mode=1` (`OPENBUENOS_MOCK=1` / `MockPJRT`) into `context_create` so buffer pools, IOVA/DMA-BUF accounting, LRU graph/executable caches, 16-credit async submission rings (`eventfd`, 32-bit `seq`, OOO demux, `ERR_BUSY` backpressure), and CPU exact-math fallbacks execute cleanly in host CI without hardware.
   - **Mock Parser Lesson (`ggml-cloudtpu`)**: If building `MockPJRT` for textual StableHLO MLIR, make signature/type parsing resilient to multi-line ops and trailing attributes (`indices_are_sorted = false`) or complex ops like `ROPE`/scatter will abort host tests.
3. **Zero Proprietary `DT_NEEDED` & Clean Build Flags**:
   - Build with `-fno-exceptions -fno-rtti -Wall -Wextra -Werror`, verify `llvm-readelf -d` shows `DT_NEEDED` = `[libdl.so, libm.so, libc.so]` only (`0` `dlopen`/`dlsym` to vendor `.so`s), and guard C11 shims with `#define _POSIX_C_SOURCE 200809L` for `clock_gettime`.
   - **GCC-15 Portability Trap**: GCC-15 `-Werror=extra` rejects mixed enum/unsigned ternaries like `flag_enum | (cond ? OB_STAT_FLAG_MOCK : 0u)` — assign then `|=` instead. Never pass `.a` archives to `clang -x c`.

---

## 2. Memory, Handle Limits & Performance Discipline

1. **Single-Copy Weight Residency (Avoid the `479 s` Cache-Thrash Cliff)**:
   - Never cache both host GGUF weights and duplicated device-packed weights (`~1.94x` RAM -> OOM/LMKD kill >4.5 GB) OR let a fixed small budget (`128 MiB`) evict active layers mid-decode (`Qwen2.5-32B` hit `99.62%` tile hits & `8.17 s` HW yet took **`479.75 s`** wall time due to token-by-token CPU repacking).
   - *Fix*: Pre-pack weights once into device layout, use dynamic budget `(MemAvailable + used) / 3`, and verify `w_evict == 0` under load.
2. **Bypass Firmware/Device Program Caps via `param_slice` / IOVA Swap**:
   - Firmware handle tables cap fast (e.g., Tensor G5 `769` live graphs / `1,024` handles). Cache **weight-agnostic shape executables** and swap parameter DMA-BUFs / IOVA descriptors (`Probe-A` `override_params`) + hold a single shared `8 MiB` zero-params buffer (`0.00%` evictions, `99.97%` cache hit).
3. **2-Tier Persistent DMA Slabs + Adaptive Spin + DVFS**:
   - Split small/large persistent DMA buffers (`4 KiB` / `128 KiB`) to eliminate 128 KiB cache flush/invalidate on `M=1` decode.
   - Check clock/power state first (`AcquireWakeLock` + `PM=5` unlocked `38.4 MHz -> 1,286.4 MHz`, `38.6x` speedup), and pair bounded spin (`SPIN_US=450`) before syscall wait (`poll_waits` `-98%`).
4. **Beat Heterogeneous CPU Barrier Thrashing with 1-Helper SPSC**:
   - Multi-thread `parallel_for` barriers across BIG+MID+LITTLE cores caused `~18,000` condvar bounces (`dequant_us` `2.29s -> 9.17s`).
   - *Fix*: Keep `M<=8` decode/quant/pack/submit inline on the calling BIG core, and offload heavy `M>8` prefill work across a **16-slot cache-line-padded SPSC ring** to **one** persistent helper pinned to `cpuinfo_max_freq > min_freq` (`~1` wakeup/call, `0%` idle CPU).
5. **Instrument Phase Timers From Day One**:
   - Export `hw_us`, `wall_us`, `quant_us`, `hash_us`, `pack_us`, `dma_sync_us`, `submit_us`, `wait_us`, `dequant_us`, `sat_retries`, `pool_hits/misses`, `w_hits/misses`, `w_evict`, `w_peak_bytes`. Whenever `hw_us << wall_us`, timers pinpoint the bottleneck immediately.

---

## 3. Quantization, Numerics & Fusion Safety

- **Heavy-Tailed Activation & Correlated Weight Guards**:
  - Real LLM layers exhibit attention-sink outliers (`40-sigma` spikes) and correlated non-zero-mean gate/up rows. Peel rare outliers onto FP32/NEON (`MAX_OUTLIER_COLS=160`), guard `W_gate`/`W_up` DC row sums (`asum > 5.5 * l2`) & pre-submit activation `rms_aq > 56` / `est > 250 * d_gate`, fallback `crest > 16` or narrow `M in [2..8]` cleanly to CPU (`M > 8` routes to `lt_64x*`), and snap scales on `2^(k/2)` / `1.5x`-step grids.
- **FP16 Accumulation & IEEE-754 Rounding Traps**:
  - Guard `|x| > 32768` prescale before `FP16` systolic ops (`W8A16(FP16)`). Use **64-bit accumulators** in reference simulators and enforce `FE_TONEAREST` around spline/integer synthesis.

---

## 4. `ggml` Backend & Deep Review Hardening Checklist

Subtle failure modes surfaced during multi-epoch automated and human reviews of `libopenbuenos`, `ggml-edgetpu`, `ggml-cloudtpu`, and `ggml-rpc`:

- [ ] **Async In-Flight Buffer Lifetime**: Retain every IOVA/DMA buffer attached to an async command (`buffer_retain` / `device_attach_inflight_buffers`) across timeouts/evictions (`detach_timed_out_buffers_locked`). Never free or unmap an IOVA/DMA-BUF while hardware fences remain pending or timed out.
- [ ] **Immutable Weight Versioning**: Track `ImmutableWeightRegion` + `weight_version`; explicitly invalidate cached device tiles when `set_tensor` / host-to-device copy mutates host memory. Never register unowned arbitrary host pointers silently without caller opt-in.
- [ ] **Typed Cache Keys**: Include full tile shape, stride, pack format, dtype, and parameter-swap slot index in cache keys; recheck capacity *after* insert under lock; use rounded slab allocation sizes for accounting.
- [ ] **Safe `ggml` Fusion (`use_counts` & Aliasing)**: Before fusing chains like `SwiGLU` (`gate`, `up`, `silu`, `mul`, `down`), check **graph-wide** `cgraph->use_counts` + `visited_hash_set` (later backend splits aren't in the current subgraph's `nodes[]`) AND unwrap `view_src` aliases and overlapping src/dst buffers. Also forbid `__restrict` on helpers whose input/output can alias.
- [ ] **`MUL_MAT_ID` & Tensor Indexing Hygiene**: Explicitly reject expert IDs `< -1` (treat negative non-`-1` IDs as errors, `-1` as skip/zero), validate `ne`/`nr` broadcast strides and non-contiguous permutations in `supports_op()`.
- [ ] **`test-backend-ops` Non-Happy-Path Coverage**: Specifically test 4D strided/broadcast `ADD` (`ne=[16,5,4,3], nr=[1,1,1,1]`) and `ROPE` across `mode=0/2`, `f32/f16`, and YaRN (`n_ctx_orig`, `beta_fast`) — these are the first ops that fail in `ggml-cloudtpu`.
- [ ] **`ggml-rpc` + Local Fallback & Preflight**: Standard `rpc-server -d EDGETPU` fails on glue ops; pair `ACCEL` + local `CPU` via `ggml_graph_view`, implement `device_get_memory` cleanly from `/proc/meminfo`, and verify USB/CDC-NCM link health before launching `llama-bench` (`ggml-rpc.cpp:696` aborts on transient link drop).
- [ ] **Deterministic Error & Env Parsing**: Check DMA-BUF sync/ioctl errors *before* retry loops; parse boolean env disables strictly (`strcmp(v, "1") == 0` where documented); isolate host unit tests from leaked caller env vars.
