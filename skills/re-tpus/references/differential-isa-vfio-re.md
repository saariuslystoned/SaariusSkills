# Differential ISA, Compiler-Oracle & VFIO Black-Box RE

Proven techniques for cracking closed accelerator stacks (Edge Tensor G5/G6 & Cloud TPU `/dev/vfio/*`) without shipping proprietary blobs.

---

## 1. Binary Triage & Pre-Scan Pipeline (Before Heavy Decompilation)

Large vendor compiler/driver shared libraries (`libedgetpu_tflite_compiler.so` ~80 MB, `libtpu.so` ~600 MB) choke naive full-binary auto-analysis. Triage fast first:

1. **NDK / LLVM CLI triage**:
   - Run `llvm-readelf -d`, `llvm-nm -D`, and `llvm-strings` to check `DT_NEEDED`, exported C symbols (`GetPjrtApi`, `CompileTfliteFlatbuffer2`), debug flags, and embedded string/enum tables (for example, recovering all 76 `platforms::darwinn::dive::OperationInfo` opcodes `0..75` directly from `ext[1]`).
   - Write targeted scanners for `.init_array` constructors, `filewrapper_toc` embedded resource tables, and `TcParseTable` protobuf descriptors (validate recovered `.proto` files with `protoc --descriptor_set_out=/dev/null`).
2. **Disassemble accelerator control-core code early**:
   - Never assume 32-bit vs 64-bit control ISA (`llvm-objdump` proved Tensor G5 `ext[1]` DIVE VM is **RV64 SiFive X280** via `addiw`, plus `.bss` requirements, not RV32).
3. **`morluto/rea` (`>= 6.10.1`) & Ghidra headless**:
   - Use `rea` (`reverse-engineer-anything`) MCP/CLI for symbol, ELF, and JS/transport teardown; keep Ghidra headless scripts (`analyzeHeadless`) in private disposable project dirs so parallel runs never lock shared project databases.

---

## 2. Compiler & Driver as Black-Box Oracle

When source or IR compilers exist as a standalone binary (`libedgetpu_tflite_compiler.so`, or `libtpu.so` via `GetPjrtApi()` / XLA):

1. **Test if custom-IR backdoors are actually wired**: Check call sites before relying on strings. `LoadCustomKernelDatabase()` was dead-code-eliminated (`absl::UnimplementedError`) and `custom_kernel.pbtxt` / `.mlir` stripped even though parser symbols lingered in RTTI.
2. **Check compiler debug flags first**: e.g., Android system props (`vendor.darwinn.force_darwinn_odc_dump_mlir`, `vendor.darwinn.dump_compiler_options`) or PJRT/XLA dump flags reveal intermediate lowering cleanly.
3. **1-Param Paired-Twin Differential Probes**:
   - Construct tiny micro-graphs (`1x16x16` matmul/add, `bf16` cast, single DMA copy) differing in **one** parameter (e.g., `K: 16 -> 32`, `INT8` vs `UINT8`, `per-tensor` vs `per-channel` sharing an identical `.ref.bin`).
   - Diff emitted executables (`bitstream_diff.py`, FlatBuffer slot inspector `dgc0_dump.py`) or host VFIO call traces to recover closed-form formulas for buffer sizes, strides, bitfields, zero-points, and CSRs (`77/77` DMA/TTU & `81/81` multi-tile parity verified on `buenos_a0`).
4. **Watch out for non-zero alignment padding & mislabeled fields**:
   - Tensor G5 inter-buffer 64 B alignment gaps use **`0x0a`** (not `0x00`), and `DWS0.id 15` holds a `447 B` `CompilerOptions` protobuf rather than CSRs. Assume nothing until validated by emission round-trip.

---

## 3. Causal Falsification Protocol (Save Weeks on Dead Ends)

Documentation strings, `.binarypb` configs, and compiler hints frequently describe **disabled or half-wired silicon features**. Falsify speculative features early with minimal 1-shot experiments:

1. **Hypothesis**: Does hardware feature `X` actually execute in silicon, or is a fallback silently answering?
   - **Test 1 — Raw-Fallback Poisoning**: Put known wrong data (all `0x00`s) in the legacy field and valid compressed/special data in the new field. *Lesson (`buenos_a0` Huffman):* Hardware computed against the poisoned `0x00` fallback (`max_err=0` vs raw zero-weight math), proving `bit499=1` and Huffman metadata fields `7..9` are ignored on `buenos_a0`.
   - **Test 2 — Undersized Buffer / SMMU Fault**: Shrink the backing DMA buffer to the compressed size only. If the engine still reads uncompressed length and triggers an IOMMU/SMMU read fault (`write=0 not mapped`), DMA compression is physically inactive.
   - **Test 3 — Bitfield Mismatch Stall**: On `buenos_a0`, `0x980` `bit21=1` (`w4a8` / `w4a16` hunch) proved to be **`1:2` `UINT8 -> BF16` unpack**, NOT 4-bit nibble unpack (`CSR 0x56[6:4]=7` expects twice the bytes -> permanent fence timeout until feeding full 1 B/weight `u8` + FP32 scales -> `W8A16(FP16/BF16)`).
2. **Never trust synthetic mocks without checking scaling bias**: Unscaled `[0..15]-8` synthetic INT4 tests carry `-0.5` expectation bias compounding across deep networks (`16.0` max error at 32L). Always validate with zero-centered / per-block scales.

---

## 4. Bare-Metal VFIO Observation Strategy (for Closed `libtpu.so`)

Since Cloud TPUs expose **no** small `.dgc0` compiler files — everything lives inside `libtpu.so` talking directly to `/dev/vfio/vfio` and `/dev/vfio/<group>` — use black-box syscall/MMIO observation:

1. **M1 Region & IRQ Audit (`MAPS_LIBTPU=0`)**:
   - Open `/dev/vfio/vfio` + `/dev/vfio/<group>`, attach container (`VFIO_SET_IOMMU` / Type1v2), call `VFIO_DEVICE_GET_INFO`, `VFIO_DEVICE_GET_REGION_INFO` (BAR0..BAR5 + PCI config), and `VFIO_DEVICE_GET_IRQ_INFO` (128 MSI-X vectors on `v5e-1`).
   - Test `VFIO_IOMMU_MAP_DMA` (`--ulimit memlock=-1:-1`, `CAP_IPC_LOCK`) and safe 32/64-bit MMIO reads on BAR0 vs BAR4 before touching writes. Check early whether firmware is hypervisor-prebooted or host-loaded during `PjrtClient` init.
2. **Syscall + `ptrace` + MMIO Write Tap (`vfio_bus_tap`)**:
   - Trace `libtpu.so` running minimal `1x64x32` and `128x128` PJRT programs under `ptrace` (capturing `ioctl` VFIO commands, `mmap` offsets correlated via `/proc/<pid>/maps`, `pread64`/`pwrite64`, `eventfd` wait patterns) and non-invasive MMIO page-fault taps (`mprotect(PROT_READ)` trap-and-step on BAR pages) to log exact register write sequences, ring head/tail doorbell updates, and IOVA DMA descriptors.
3. **Differential Sweep Through Minimal PJRT Programs**:
   - Run two minimal C++ PJRT programs (`tpu_pjrt_bench` style) differing in **one** tensor size, buffer address (`H2D`), or op (zero-copy `H2D -> D2H` first for M2 DMA round-trip, then `128x128` `bf16` matmul for M3). Diff the captured MMIO/DMA ring packets to isolate opcodes and HBM addresses cleanly.

---

## 5. Offline Simulator + Minimax Approximation Before Silicon

Before firing real hardware:
- Build a host exact reference in pure C++/Python matching hardware rounding (`std::fesetround(FE_TONEAREST)` / IEEE-754 RNE, exact integer divider/right-shift semantics). Example: initial `0x640` spline simulator differed on `17/4096` inputs until matching exact FP32-RNE Horner evaluation and `stream125` `mul[44:13]` / `fclip` bit positions (`4096/4096` bit-exact once fixed).
- Compute polynomial LUT approximations (8-segment degree-4 Remez minimax for `SiLU`, `GELU`, `exp`) offline in NumPy verifying `< 0.5` LSB worst-case error (`0.00045–0.00234` LSB) prior to hardware runs.
