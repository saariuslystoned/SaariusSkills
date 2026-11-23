# Cloud TPU Internals: Colab, GCP, VFIO & Native C++ PJRT

Observed hardware contracts, headless control-plane gotchas, and C++ `PJRT_Api` / `VFIO` design rules across Colab `v5e-1` / `v6e-1` and GCP `v6e-8` (Trillium) / `tpu7x` (Ironwood).

---

## 1. Observed Cloud TPU PCIe & VFIO Geometry

- **Device Nodes**: Cloud TPU VMs expose **no `/dev/accel*` or `/dev/tpu*`** in userspace — only `/dev/vfio/vfio` and `/dev/vfio/<iommu_group>` bound to kernel `vfio-pci`.
- **Dynamic PCI Discovery (Required)**:
  - Scan `/sys/bus/pci/devices/*` for `vendor == 0x1ae0`, `class == 0xff0000`, `driver == vfio-pci`, then read the `iommu_group` symlink -> `/dev/vfio/<group>`.
  - **Trap**: Never hardcode PCI BDF `0000:00:05.0`. On Colab `v5e-1`, `0000:00:05.0` is the TPU (`0x1ae0:0x0063`); on `v6e-1`, `0000:00:05.0` is **gVNIC** (`0x1ae0:0x0042`).
- **Measured Chip Envelopes (`v5e` vs `v6e`)**:
  - `v5e-1` (`0x1ae0:0x0063`): `BAR0 = 4096.00 MiB`, `BAR4 = 16.00 MiB`, `128` MSI-X vectors, `16 MiB` VMEM (`16–128 MiB` logical/chip hierarchy), `1 MiB` SMEM, `4` MXUs, `15.748 GiB` usable HBM2e (`~179 TFLOP/s` BF16 / `~357 TOPS` INT8 / `652–656 GB/s` HBM BW measured).
  - `v6e-8` (`0x1ae0:0x006f`, 8 chips/VM): `31.25 GiB`/chip (`250 GiB` usable HBM/host). `Qwen3-235B-FP8` misses by `272 MiB/chip` during MoE requantization; `gpt-oss-120b` (`MXFP4`) requires `tpu7x` or SparseCore env overrides (`MOE_TC_PERMUTE=1`, `ONEHOT_MOE_PERMUTE_THRESHOLD=32768`, `USE_MOE_EP_KERNEL=1`).
- **Container / `VFIO` Permissions**:
  - Unprivileged VFIO DMA pinning fails without `--cap-add=IPC_LOCK` and `--ulimit memlock=-1:-1` (use CNCF CDI `v0.6.0` `/etc/cdi/*.json` with OCI hooks). Multi-chip PJRT coordinator sockets (`[::]:8353`) also need `--net=host` and `--shm-size=16G`.

---

## 2. Native C++ `PJRT_Api` (Zero Python / Zero JAX)

Pure C++17 PJRT probing (`tpu_pjrt_bench.cpp`) proved Cloud TPUs work identically to CUDA's `libcuda.so`:

1. **`dlopen("libtpu.so")` -> `GetPjrtApi()`**: Returns `const PJRT_Api*` (`struct_size=1144`, `version=0.116`, `MAPS_LIBPYTHON=0`, zero `libpython` in `ldd`). Keep all callers above `GetPjrtApi()` so `./libopentpu.so` drops in via `TPU_LIBRARY_PATH` later.
2. **Zero-Python StableHLO Emission**: Emit textual StableHLO MLIR + serialized `CompileOptionsProto` directly from C++ into `PJRT_Client_Compile`, caching `PJRT_LoadedExecutable*` in an LRU cache by op signature + shapes.
3. **Hide the `~127 us` Dispatch Floor**:
   - Single synchronous op launch on `v5e-1` floors at **`114–135 us`** (`126.94 us` C++ vs `114–135 us` JAX — proving the bottleneck is PJRT/TFRT/hardware, not Python).
   - Pipelining 100 async steps overlaps host enqueue (`28.86 us`), dropping amortized launch to **`32.00 us`** (`3.97x` speedup) and reaching **`180.36 TFLOP/s`** BF16 (`91.6%` of `197 TFLOP/s`, `max_abs_err = 0.0`).
   - Fusing ops + double-buffered async VMEM DMA (`pltpu.make_async_copy`) closes `~94%` of XLA speed (`135.5 TFLOP/s`) and beats XLA `3.05x–3.24x` on `W4A16` decode.

### Live `v5e-1` PJRT + Textual StableHLO Lessons (`ggml-cloudtpu`)
- **Textual MLIR Works Directly in `libtpu.so` (`0.0.50`, PJRT `0.116`)**: `PJRT_Program{ .format = "mlir" }` compiles pure C++-emitted textual StableHLO MLIR directly (zero MLIR/libprotobuf/Python dependencies, `MAPS_LIBPYTHON=0`). Requires non-empty `CompileOptionsProto` (e.g. 11-byte `ExecutableBuildOptionsProto` with `num_replicas=1, num_partitions=1, use_spmd_partitioning=1, use_shardy_partitioner=1`; empty options fail with `Requested total cores: 0`).
- **Single-Chip `execute_device` Must Be `nullptr`**: `PJRT_LoadedExecutable_Execute_Args.execute_device` must be `nullptr` on single-chip `libtpu.so` (passing `devices_[0]` triggers `execute_device not supported` because device assignment is baked at compile time).
- **Mandatory Row-Major `host_layout` on `PJRT_Buffer_ToHostBuffer`**: Passing `host_layout = nullptr` causes `libtpu.so` to copy out in the TPU device buffer's XLA-chosen minor-to-major dimension order — silently transposing non-multiple-of-8 (`ROPE` `[1,2,52,128]`) and batched (`MUL_MAT` `[4,6,1,16]`) outputs. Always query `PJRT_Buffer_Dimensions` and pass an untiled `PJRT_Buffer_MemoryLayout_Type_Tiled` with `minor_to_major = {R-1, ..., 0}, num_tiles = 0`.
- **Dequantize `Q4_0`/`Q8_0` to `F32` Before `F32` `dot_general`**: Dequantizing split `Q4_0`/`Q8_0` weights to `BF16` and upcasting `BF16 -> F32` before `dot_general` fails `test-backend-ops` (`Q4_0` NMSE `~1.9`, `Q8_0` NMSE `~0.005`); dequantizing directly to `F32` when activations are `F32` achieves 100% `v5e-1` parity (`NMSE < 5e-4`).
- **GCC 13+ `-Wchanges-meaning` on `pjrt_c_api.h`**: Mark `third_party/openxla` as `SYSTEM` include and add `-Wno-changes-meaning` on GCC 13+ (`libstdc++` also requires explicit `<stdexcept>` / `<string>`).

---

## 3. Headless Google Colab Control Planes & Traps

Two sanctioned programmatic paths exist (strictly R&D/benchmarking only — never production APIs per Colab ToS):

### Path A: `google-colab-cli` (User Account / Isolated Cache)
- **Session Isolation (Critical for Parallel Agents)**: Always pass `--config <lane-unique>/sessions.json` and unique session prefixes (e.g. `tpu-vfio-<ts>-$$`) so concurrent agents never clobber or stop each other's TPU assignments.
- **Flags & Version Drift (`0.8.0`)**: `google-colab-cli 0.8.0` removed `--no-public-api` and `test-public-api`; always probe `colab --help` dynamically rather than hardcoding legacy flags, and pass `--accelerator` alongside `--variant=TPU` (`GET /tun/m/assign?variant=TPU` without accelerator returns `400 Bad Request`).
- **Capacity `503`s, `TooManyAssignmentsError` (`412`) & `ReadTimeout` Handling**: `V6E1` and `V5E1` frequently return HTTP `503 Service Unavailable`, `TooManyAssignmentsError` (HTTP `412`, indicating either too many active/orphaned assignments **or** a temporary usage/capacity limit for the requested runtime), or hang `45–90s` (`ReadTimeout` / `RemoteDisconnected`, raised by Requests as `requests.exceptions.ConnectionError`) on `/tun/m/assign`. Carry the **launch authentication options** (`--auth <oauth2|adc>` and, when used, `--client-oauth-config <path>`, since `--config` selects only the local sessions file) through every `colab` command (`whoami`, `run`, `new`, `sessions`, `stop`, `usage`), and **record and re-verify the effective Google account email** via `colab <auth-opts> whoami` at launch and before cleanup or accepting an empty assignment inventory (in `0.8.0`, OAuth reads a shared keyring entry regardless of `--client-oauth-config` and ADC resolves from the current environment, so an account switch would otherwise hide a billable runtime on the original account). Inspect server-side assignments with `colab <auth-opts> --config <lane-unique>/sessions.json sessions` (not `colab list`, unavailable in `0.8.0`), and stop tracked runtimes with `colab <auth-opts> --config <lane-unique>/sessions.json stop -s <name>`. When `--config` is empty (including right after `colab run` removes its local entry), `colab sessions` catches `SystemExit` auth errors (such as an ADC refresh failure) and prints `[colab] No active sessions found on server.` with exit status `0`—never accept that as teardown proof without verifying account identity and zero auth errors, or query directly via an authenticated `colab_cli.client.Client(Prod(), get_credentials(...)).list_assignments()` call for the verified launch account. Because `colab stop` resolves names only from the selected local `--config` file, `?` in `colab sessions` only means an endpoint is absent from *that* sessions file—under per-lane `--config` isolation, another parallel agent's active runtime on the same account also appears as `?`. Independently verify ownership and confirm no active lane owns a `?` endpoint before releasing it; once confirmed orphaned (e.g., remote allocation succeeded before local state was saved, or `colab run`'s best-effort teardown swallowed an `unassign` failure and removed the local session entry), release it by endpoint via `colab_cli.client.Client(Prod(), get_credentials(...)).unassign(<endpoint>)` inside the `google-colab-cli` environment for that verified Google account or via Colab's **Manage sessions** UI. For `colab run -s <unique-run-name>` / `colab new` retries and accelerator fallback (`v6e1 <-> v5e1`), configure `COLAB_CLI_ASSIGN_RETRIES` (note `Client.assign()`'s built-in retry loop excludes `requests.exceptions.ConnectionError` / `RemoteDisconnected`) and handle failures at the caller boundary: CLI wrappers inspect non-zero exit status plus stderr (`[colab] Allocation refused (precondition failed).` with exit code `1` for HTTP `412`, `503`, timeouts, and `RemoteDisconnected` / `ConnectionError` drops), whereas direct Python `Client` callers catch `TooManyAssignmentsError`, `ColabRequestError`, `requests.exceptions.ReadTimeout`, and `requests.exceptions.ConnectionError`. Because neither `colab sessions` nor `list_assignments()` exposes `notebook_hash`, an uncertain POST drop/timeout can leave a live runtime with no local record: direct Python `Client` callers should retain and reuse the original `notebook_hash` UUID on retry (so `Client.assign()`'s initial `GET` recovers the existing assignment rather than allocating a second billable runtime), while CLI wrappers (which generate a fresh UUID per invocation) should pause automatic retries whenever an unrecognized server-side assignment's ownership across parallel lanes remains unresolved. Pair runs with `colab <auth-opts> usage` CU checks and **mandatory remote teardown verification** on every exit path: stop tracked `colab new` sessions with `colab <auth-opts> --config <lane-unique>/sessions.json stop -s <name>`, and after **every** `colab run -s <unique-run-name>` (even exit `0`, since `_teardown` catches `unassign` errors, prunes local state, and still prints `Session terminated.`) use a fresh per-attempt session name (history logs append by name across runs and `--config` files), export only the filtered creation event (`colab log -s <unique-run-name> -t session_created -o <private-path>.jsonl`, since plain `colab log -s <name>` omits the endpoint whereas unfiltered `.ipynb` export includes executed code, outputs, and literal `--env` values under default file permissions—restrict full notebook exports to a private destination after secret review), verify under the recorded launch account via authenticated `client.list_assignments()` (or identity- and auth-verified `colab <auth-opts> sessions`) that its endpoint is gone—running endpoint-based cleanup if it remains—and if no current-attempt `session_created` event was logged, reconcile directly against that authenticated assignment inventory before retrying. Disconnect idle browser notebook tabs promptly (`~3.17 CUs/hr`).
- **Python Probe Execution Traps**:
  - **Avoid nested `python3 -c "..."` escaping**: inline double-quoted scripts across shells/SSH/`colab run` routinely fail with `SyntaxError: unexpected character after line continuation character`. Prefer a script file, single-quoted heredoc `python3 - <<'PY'`, or base64-framed payload.
  - **Run simulators inside an environment that provides `numpy`**: bare host `python3` may lack `numpy` (`ModuleNotFoundError: No module named 'numpy'`). Verify `python3 -c 'import numpy'` in the same interpreter that will run the simulator, activate the repo venv before running it, or launch directly with `uv run --with numpy python simulator.py`.
  - **Match profiler cleanup to the active API**: an overlapping `jax.profiler.start_trace()` raises `RuntimeError` — always pair `start_trace()`/`stop_trace()` in `try/finally` (call `jax.profiler.stop_trace()` to release an active JAX trace without resetting the runtime). Separately, avoid overlapping CPython `cProfile` instances: on CPython `3.12+` a concurrent `cProfile` raises `ValueError` (the exact message varies across `3.12`/`3.13`/`3.14` patch releases), while on CPython `3.11` (like `sys.setprofile`) enabling a second `cProfile` replaces the thread's existing callback and can silently truncate the first capture's measurements. Always pair `profiler.enable()`/`profiler.disable()` in `try/finally` (or call `sys.setprofile(None)` for a legacy hook), resetting the runtime only if the owning profiler handle was lost.

### Path B: Official Colab MCP (`colaboratory`)
- Requires both the `colaboratory` OAuth scope and `gcloud services enable colaboratory.googleapis.com --project=<gcp-project-id>` (plus `X-Goog-User-Project` header). Without API enablement, it returns `403 SERVICE_DISABLED` / `Forbidden`. When enabled under `PRO_PLUS`, `list_runtime_specs`, `create_runtime` (`VARIANT_TPU`), `execute_code`, and `delete_runtime` provide a clean backup if `google-colab-cli` endpoints flake.

---

## 4. GCP Multi-Chip VMs, Quotas & Cloud Shell Lessons

- **Prefer `tpu.googleapis.com` (`gcloud compute tpus tpu-vm`)** for `v6e-*`/`v5litepod-*` when GCE `CPUS_ALL_REGIONS` quota is tight; GCE `ct6e-standard-*` and `tpu7x-standard-*` require global/regional vCPU quotas *on top* of TPU quotas.
- **Standalone / New GCP Project Limits**: Newly created consumer projects without a Workspace/Cloud Identity org often face `tpu7x` throttling (`reconciling: True`, `grantedValue: 0`), DWS Calendar Mode blocks, and Standard Support eligibility limits.
- **Cost-Locked Ephemeral Runs**: Always use Spot / `DWS Flex-Start` with `--max-run-duration=25m --instance-termination-action=DELETE` and verify `0` leftover VMs across both `tpu-vm list` and `compute instances list`.
- **Cloud Shell Bridge Traps**: `gcloud cloud-shell ssh` shares the browser VM/`tmux` and port-8080 `/_cloudshell/{file,ls}` HTTP sidecar. Always **base64-frame** remote commands (`ssh.py` splits args on spaces) and renew `AuthorizeEnvironment()` keepalive before `28m` (`1,680s`) so tunnels never drop silently.

---

## 5. Clean-Room Bare-Metal `v5e-1` Direct-in-IMEM Execution (Zero `libtpu.so`)

Proven 100% zero-blob on live Cloud TPU `v5e-1` (`0x1ae0:0x0063`) via `/dev/vfio/*` + `BAR0 + 0x10000` SQ/CQ rings (`libopentpu.so`, `MAPS_LIBTPU=0`, `MAPS_LIBPYTHON=0`):

- **Minimal Bring-Up (No `BAR0+0x0a...`, No `0x10090`, No `0x161`)**:
  - `VFIO_DEVICE_RESET` + 256-slot SQ (`0x0`), CQ (`0x8000`), Status (`0xa000`) ring init at `BAR0 + 0x10000`.
  - **Direct Host -> IMEM DMA (`0x1000_00000000`)**: Upload `120` 512-bit VLIW bundles (`7,680 B` = `15 x 512 B`) directly from host staging IOVA using `op=0x04` (`dst_flags_hi=0x10000000`, `w28=0x130`, `w29=0x04000000`) — zero HBM bounce buffer needed. **Alignment trap**: IMEM DMA length MUST be a multiple of `512 B` (`8` bundles; `100` bundles times out, `104/112/120/128` pass).
  - **Core Start**: Single `op=0x03 d[8]=0x121` starts execution at IMEM `PC=0`.
- **Direct-in-IMEM Resident Poller + Matmul Loop (`120` bundles, Zero `prog_hbm` Reload)**:
  - **Fixed Slot-0 Launch Descriptor (`0x3fff00000`)**: Omitting the ring-index increment pins every call to HBM `0x3fff00000` (infinite calls, no 2048-slot wrap). Only 4 `uint32_t` fields are causally read: `+0x170 = rhs_hbm >> 9`, `+0x174 = lhs_hbm >> 9`, `+0x190 = out_hbm >> 9`, `+0x1e8 = exec_seq`.
  - **Doorbell & Completion Handshake**: Host uploads `512 B` `OtV5eLaunchDesc` to `0x3fff00000` with `w28=0x0001fb10, w29=0x01000000` (`+16` to sync flag `0x1fb`), then submits `op=0x06 d[8]=0x41 d[10]=0x010101f9` and asserts `cq[4] == 1 && cq[5] == exec_seq`.
  - **Mandatory Causal Sync Gates (All 3 Falsified on Silicon)**:
    1. `sync[0x1fb]` doorbell wait/sub (`>=16` / `-=16`): omitting causes the core to free-spin while host is idle.
    2. `sync[0x1ff]` 512 B `ldesc` HBM->SMEM DMA wait/sub + scalar fence (`0x55700900`): omitting causes `16384/16384` mismatches.
    3. `sync[0x33]` 32 KiB LHS HBM->VMEM DMA wait/sub/clear (`w12=(flag&0x3f)<<26`, `w13=((bytes/32)<<14)|(flag>>6)`): omitting causes intermittent `512–2303/16384` HBM race corruption. Also patch `s1` predicate `w14[28:24]` to `0x0e` (always-true, `w14=0x4e01bee8`) to eliminate the `+0x1a8` guard.
  - **Loop-Back**: Unconditional absolute jump `br_abs(0)` (`w13=0, w15=0x55700400`) + 4 delay-slot NOPs returns to `PC=0` (writes `SMEM[+0x1e8]` -> `sync[0x1f9]`, then blocks on `sync[0x1fb]`).
- **Verified Silicon Proof**:
  - `100/100` consecutive zero-blob calls (`avg_dt = 133.1 us`, `cq_fails=0`, `0/819,200` mismatches / `max_diff=0.0` on dyadic `0.125`-step random BF16; `max_diff=0.015625` <= 1 BF16 ULP on arbitrary continuous uniform `[-1, 1]` BF16 due to MXU reduction-tree ties).
  - Live `libopentpu.so` (`readelf -d`: `NEEDED = [libc.so.6, ld-linux-x86-64.so.2]` only, `0` vendor strings) + `opentpu_matmul_proof`: `0/16384` mismatches (`max_diff=0.000000`) across `5/5` C API `ot_matmul_bf16` + chained `(A@B)@D` (`594–648 us` warm) AND `5/5` fresh `dlopen("./libopentpu.so") -> GetPjrtApi()` (`334–359 us` warm), `MAPS_LIBTPU=0`, `MAPS_LIBPYTHON=0`.
