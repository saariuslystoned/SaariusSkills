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

---

## 3. Headless Google Colab Control Planes & Traps

Two sanctioned programmatic paths exist (strictly R&D/benchmarking only — never production APIs per Colab ToS):

### Path A: `google-colab-cli` (User Account / Isolated Cache)
- **Session Isolation (Critical for Parallel Agents)**: Always pass `--config <lane-unique>/sessions.json` and unique session prefixes (e.g. `tpu-vfio-<ts>-$$`) so concurrent agents never clobber or stop each other's TPU assignments.
- **Flags & Version Drift (`0.8.0`)**: `google-colab-cli 0.8.0` removed `--no-public-api` and `test-public-api`; always probe `colab --help` dynamically rather than hardcoding legacy flags, and pass `--accelerator` alongside `--variant=TPU` (`GET /tun/m/assign?variant=TPU` without accelerator returns `400 Bad Request`).
- **Capacity `503`s & `ReadTimeout` Handling**: `V6E1` and `V5E1` frequently return HTTP `503 Service Unavailable` or hang `45–90s` (`ReadTimeout` / `RemoteDisconnected`) on `/tun/m/assign`. Wrap `colab run` with bounded retries (`COLAB_CLI_ASSIGN_RETRIES`), fallback (`v6e1 -> v5e1` or vice versa, catching *both* `ColabRequestError` and `ReadTimeout`), `colab usage` CU check, `colab log -o proof.ipynb`, and **mandatory remote teardown (`colab stop`)** on every exit path. Disconnect idle browser notebook tabs promptly (`~3.17 CUs/hr`).

### Path B: Official Colab MCP (`colaboratory`)
- Requires both the `colaboratory` OAuth scope and `gcloud services enable colaboratory.googleapis.com --project=<gcp-project-id>` (plus `X-Goog-User-Project` header). Without API enablement, it returns `403 SERVICE_DISABLED` / `Forbidden`. When enabled under `PRO_PLUS`, `list_runtime_specs`, `create_runtime` (`VARIANT_TPU`), `execute_code`, and `delete_runtime` provide a clean backup if `google-colab-cli` endpoints flake.

---

## 4. GCP Multi-Chip VMs, Quotas & Cloud Shell Lessons

- **Prefer `tpu.googleapis.com` (`gcloud compute tpus tpu-vm`)** for `v6e-*`/`v5litepod-*` when GCE `CPUS_ALL_REGIONS` quota is tight; GCE `ct6e-standard-*` and `tpu7x-standard-*` require global/regional vCPU quotas *on top* of TPU quotas.
- **Standalone / New GCP Project Limits**: Newly created consumer projects without a Workspace/Cloud Identity org often face `tpu7x` throttling (`reconciling: True`, `grantedValue: 0`), DWS Calendar Mode blocks, and Standard Support eligibility limits.
- **Cost-Locked Ephemeral Runs**: Always use Spot / `DWS Flex-Start` with `--max-run-duration=25m --instance-termination-action=DELETE` and verify `0` leftover VMs across both `tpu-vm list` and `compute instances list`.
- **Cloud Shell Bridge Traps**: `gcloud cloud-shell ssh` shares the browser VM/`tmux` and port-8080 `/_cloudshell/{file,ls}` HTTP sidecar. Always **base64-frame** remote commands (`ssh.py` splits args on spaces) and renew `AuthorizeEnvironment()` keepalive before `28m` (`1,680s`) so tunnels never drop silently.
