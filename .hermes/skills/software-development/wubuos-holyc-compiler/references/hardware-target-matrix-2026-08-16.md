# Hardware Target Matrix — Past, Present, Future (2026-08-16)

WuBuOS targets ALL compute hardware. From Pentium+DDR1 to RISC-V+chiplet.

## Era 1: PAST (1995-2005) — "Make it run on anything"

### Minimum Target: Intel Pentium 100MHz + 16MB EDO RAM
- x86-32 code (our x86-64 driver emits 32-bit compat)
- 64KB L1 cache fits our interpreter
- No FPU required (integer only)
- Boots from floppy (our ELF is 138 bytes)

### Retro Consoles (all covered by existing ISA drivers)
| Console | CPU | ISA | Status |
|---------|-----|-----|--------|
| NES (1985) | MOS 6502 | 8-bit 6502 | ✅ wubu_isa_6502 |
| SMS (1985) | Z80 | Z80 | ✅ wubu_isa_z80 |
| Genesis (1988) | M68K | 32-bit M68K | ✅ wubu_isa_m68k |
| PS1 (1994) | MIPS R3000A | MIPS-I | ✅ wubu_isa_mips |
| SNES (1990) | WDC 65C816 | 6502 superset | ⚠️ partial |
| N64 (1996) | MIPS R4300i | MIPS-III | ⚠️ partial |
| Dreamcast (1998) | SH-4 | SH-4 | ⬜ planned |
| PS2 (2000) | Emotion Engine | MIPS-III+VU | ⬜ planned |
| GBA (2001) | ARM7TDMI | ARMv4T | ⬜ planned |
| GameCube (2001) | Gekko | PowerPC 750 | ⬜ planned |

### Pentium III + DDR1 (1999 baseline)
- Clock: 400MHz-1.4GHz, ISA: IA-32 + MMX + SSE
- L1: 32KB, L2: 128-512KB
- RAM: 64-512MB DDR1 (100-133MHz, 1.6-3.2 GB/s)
- WuBu: ✅ x86-64 driver (compat mode)

### Pentium 4 + DDR1 (2000 baseline)
- Clock: 1.3-3.8GHz, ISA: IA-32 + SSE2 + (x86-64 late)
- RAM: 128MB-1GB DDR1
- WuBu: ✅ x86-64 driver

## Era 2: PRESENT (2020-2026) — "Make it fast everywhere"

### x86-64 Desktop (2024)
- Intel Core i9 / AMD Ryzen 9, 3.0-6.0 GHz
- ISA: x86-64 + SSE4.2 + AVX2 + (AVX-512 some)
- RAM: 16-128GB DDR4/DDR5
- GPU: RTX 4090 / RX 7900 XTX
- WuBu: ✅ x86-64 JIT + PTX + AMDGPU

### ARM64 Laptop (2024)
- Apple M3 / Qualcomm X Elite / AWS Graviton
- ISA: ARMv8.6-A / ARMv9-A + NEON + SVE (some)
- RAM: 8-64GB LPDDR5
- WuBu: ✅ wubu_isa_arm64 native JIT

### RISC-V Development Board (2024)
- SiFive FU740 / StarFive JH7110 / T-Head C910
- ISA: RV64GC (IMAFDC) + V extension (some)
- RAM: 4-16GB DDR4
- WuBu: ✅ wubu_isa_riscv (encoder + interpreter)

### NVIDIA GPU (2024)
- RTX 4090 (AD102) / H100 (Hopper)
- ISA: PTX 8.0 / SASS SM89/SM90
- WuBu: ✅ PTX text emission (binary coming)

### AMD GPU (2024)
- RX 7900 XTX (Navi 31) / MI300X
- ISA: AMDGPU gfx1100
- WuBu: ✅ AMDGPU assembly text (binary coming)

### NPU (2024)
- Intel AI Boost / AMD XDNA / Qualcomm Hexagon
- WuBu: ⬜ Future — one MIR → NPU ISA

## Era 3: FUTURE (2026-2040) — "Make it everywhere"

### RISC-V Mainstream (2026-2030)
- RV64GCV (vector) SoC, 2.0-4.0 GHz, 4-32 cores
- WuBu: ⬜ V extension driver (RV64I done)

### ARMv9 + SVE2 Server (2026-2030)
- AWS Graviton4 / AmpereOne / Fujitsu A64FX
- ARMv9-A + SVE2 (256-bit vector), 64-128 cores
- WuBu: ⬜ SVE/SVE2 codegen (NEON done)

### Chiplet / 3D Stacked (2028+)
- Mixed ISA chiplets (x86 + ARM + RISC-V + NPU) via UCIe
- WuBu: ⬜ Multi-ISA MIR dispatch

### Optical / Photonic / Quantum / Neuromorphic (2030+)
- Lightmatter / IBM Quantum / Intel Loihi / IBM NorthPole
- WuBu: ⬜ Research — new ISA paradigms

## The Complete ISA Map

### Tier 1: Production Ready
| ISA | Driver | Status | Era |
|-----|--------|--------|-----|
| x86-64 | wubu_isa_x86_64.c | ✅ Native JIT | Past+Present |
| ARM64 | wubu_isa_arm64.c | ✅ Native JIT | Present |
| MIPS | wubu_isa_mips.c | ✅ Interpreter | Past+Present |
| 6502 | wubu_isa_6502.c | ✅ Interpreter | Past (retro) |
| Z80 | wubu_isa_z80.c | ✅ Interpreter | Past (retro) |
| 8086 | wubu_isa_8086.c | ✅ DOS emulator | Past |
| M68K | wubu_isa_m68k.c | ✅ Interpreter | Past (retro) |
| 8051 | wubu_isa_8051.c | ✅ Interpreter | Past (embedded) |
| AVR | wubu_isa_avr.c | ✅ Interpreter | Present (embedded) |
| PIC | wubu_isa_pic.c | ✅ Interpreter | Present (embedded) |
| RISC-V | wubu_isa_riscv.c | ✅ Encoder + Interpreter | Present+Future |

### Tier 2: Text Emission (needs binary encoder)
| ISA | Driver | Status | Era |
|-----|--------|--------|-----|
| NVIDIA PTX | wubu_isa_ptx.c | ✅ Text / ⬜ Binary | Present |
| AMD GPU | wubu_isa_amdgpu.c | ✅ Text / ⬜ Binary | Present |

### Tier 3: Planned
| ISA | Status | Era |
|-----|--------|-----|
| RISC-V V (vector) | ⬜ Planned | Future |
| ARM SVE/SVE2 | ⬜ Planned | Future |
| Intel GEN/Xe | ⬜ Planned | Present |
| NPU (IVPU/AMDXDNA/QAIC) | ⬜ Planned | Present+Future |
| FPGA bitstream | ⬜ Planned | Future |
| PowerPC | ⬜ Planned | Past (console) |
| SH-4 | ⬜ Planned | Past (Dreamcast) |

## C18 Policy (2026-08-15)

**C18 accepted, nothing higher.**
- C18 = C11 + ISO/IEC 9899:2018 defect reports (bugfix release, no new features)
- No C23, no C2x, no GNU extensions, no C++
- Jens Gustedt: "no normative changes (but one), lots of clarifications"
- Key C18 changes: atomics, threads, _Generic, alignment, sequence points, infinite loops, realloc(ptr,0), clock(), math errors

**Language router policies:**
| Language | Policy |
|----------|--------|
| HolyC | ACCEPT (native, all 14 ISAs) |
| C18 | ACCEPT (HolyC C-subset mode) |
| Brainfuck | ACCEPT \| MEME \| AGI_READY |
| Python/JS | TEMPLATE \| WASM_FALLBACK |
| C++/Rust/Go/Java/Swift/Fortran/Ada/COBOL | CONTAINER |
| Unknown | REJECT (helpful message) |

## Walkway (next work)

### Wave 1: Wire Real Compilation into Gauntlet
- Wire holyc_compile_and_run() into gauntlet runner
- Run extracted GCC torture tests (1918 files)
- Run CompCert tests (221 files)

### Wave 2: C18 HolyC Patches
- _Alignas/_Alignof, _Generic fix, sequence points, infinite loops, realloc(ptr,0)

### Wave 3: Type System + Memory Model
- Types in MIR (i8-i64, float, ptr, array, struct)
- MIR_LOAD/MIR_STORE/MIR_ALLOCA/MIR_GEP

### Wave 4: SSA + Optimizations
- Braun's SSA, SCCP, GVN, LICM, peephole

### Wave 5: Speed Techniques
- Arena allocator, string interning, 2-pass assembly, error cold path

### Wave 6: C Preprocessor
- #include, #define, #ifdef, ##, #pragma

### Wave 7: GPU Binary Emission
- Cubin encoder (NVIDIA), code object (AMD)

### Wave 8: New ISAs
- RISC-V V, ARM SVE/SVE2, Intel GEN/Xe, NPU, FPGA, console ISAs

Full detail: `~/vault/WALKWAY.md`
Research: `~/vault/research/MEGA_RESEARCH_COMPILER_IMPROVEMENTS_2026-08-15.md`
