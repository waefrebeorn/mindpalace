# The everything-hardware map (2026-08-04)

Full research: wubuwizard/research/ALL_HARDWARE_7HOP.md (corpus AN15).
The mandate: "AGI goes on everything in some way and has tools for
everything."

## The proof that the driver space scales

llama.cpp runs ONE GGUF model on 15 backends: CUDA (NVIDIA), HIP (AMD),
Metal (Apple), Vulkan (any GPU), WebGPU (any browser + Dawn native),
OpenCL (Adreno/mobile), SYCL (Intel), CANN (Ascend NPU), OpenVINO
(Intel CPU/GPU/NPU), MUSA (Moore Threads), Hexagon (Snapdragon DSP),
RPC (remote), BLAS/BLIS/ZenDNN (CPU). One model, N hardware targets =
our wubu_mir hourglass-neck pattern at AGI scale.

arXiv 2603.28793 (Universal GPU ISA): NVIDIA's PTX dominance "persists
not because of hardware superiority but because of software lock-in."
The compiler/driver layer is the unlock.

## The tiers (and the right tool for each)

1. **CPU tier** — native encoders + interpreters. DONE: x86-64 (JIT),
   m68k (interp). Next: riscv (RV64I), then 6502 as the 8-bit proof,
   then Z80/8051/PIC/AVR/MSP430. Every encoding oracle-verified.
2. **GPU tier** — PTX/GCN-RDNA/Xe/G13 are four more drivers, OR one
   Vulkan/WebGPU front covers them all (WuBuOS already has Vulkan
   compute for Bear RL). PTX is a VIRTUAL ISA — the natural next
   GPU driver (holyc_ptx.c already exists).
3. **MCU tier** — thin interpreters (the m68k interp ~200 lines is the
   template). The AGI runs on a $0.10 CH32V003 (WCH, RISC-V) — the
   cheapest chip on earth. SERV = world's smallest RISC-V (125 LUTs).
4. **DSP tier** — Hexagon: in-order 4-wide VLIW, 6-way SMT, HVX vector,
   runs compiled C. "Writing efficient code requires architecture-
   specific knowledge" = the compiler IS the product. Our mandate.
5. **NPU tier** — NOT an ISA; the GGUF/ONNX bridge (TensorRT/OpenVINO/
   CANN). TPU/Apple NE/Intel NPU (LeonRT scheduler + Movidius SHAVE
   DSPs, INT8/FP16) run the AGI's matrix multiply, not its control.

## Host detection → driver selection (tools/detect_hardware.sh)

- uname -m → ISA → driver name (x86-64/arm64/riscv/m68k/...)
- lscpu flags → the type-set ladder (avx/avx2/avx512/amx/f16c/fma)
- /dev/dxg (WSL GPU passthrough) → nvidia-smi.exe (Windows-side)
- lspci → NPU/accelerator presence
- Then: native driver if host ISA, interpreter if not, Vulkan/WebGPU
  for GPU, GGUF/ONNX for NPU. Detection → selection → differential
  self-test → run.

## The MCU hierarchy (where the AGI lives in things)

8051 (still shipping 40+ yrs, EFM8 72 MHz fastest 8-bit) → PIC16/18/24/32
→ AVR (Arduino) → MSP430 (16-bit low-power king) → STM8 → ARM Cortex-M0+
(now CHEAPER than 8-bit parts) → RISC-V MCUs (CH32V003 $0.10, GD32V,
ESP32-C, RP2350 Hazard3).

## Status in the repos

- wubuos: tools/detect_hardware.sh (DONE, verified on this box: x86_64
  AVX-512 RTX 4050), tools/verify_isa.sh (the oracle), test_drivers
  battery. Driver header maps all tiers.
- corpus: ALL_HARDWARE_7HOP.md (AN15) + ISA_7HOP.md (AN13) +
  M68K_DRIVER_7HOP.md (AN14).
