---
name: wubu-compiler-roadmap
description: "WuBuOS compiler: every target, C11 pure, steal their tests."
category: software-development
---

# WuBuOS Compiler Roadmap

## Mission
Build the best compiler for every compute target: CPU, GPU, NPU, Accelerator, Console.
C11 pure. Self-hosted. Direct binary emission. Steal their test gauntlets.

## Why We Win
- C11 purity vs their C++ bloat (LLVM=500MB, GCC=500MB, we=200KB)
- 14 ISAs from ONE MIR vs their separate backends per ISA
- Self-hosted vs their OS dependency
- Direct binary emission vs their linker dependency
- Zero external deps vs their cmake/python/autotools

## Target Platforms
CPU: x86-64, ARM64, RISC-V, MIPS, 6502, Z80, 8086, 68K, 8051, AVR, PIC
GPU: NVIDIA, AMD, Intel
Accelerator: NPU, TPU, FPGA, DSP
Console: Nintendo, PlayStation, Xbox, Retro

## 4-Phase Roadmap (~2560 lines)
Phase 1: Speed (arena, interning, 2-pass, packing, error cold, indices) ~510
Phase 2: Quality (SSA, SCCP, GVN, regalloc, peephole) ~700
Phase 3: Language (types, memory, preprocessor) ~950
Phase 4: Targets (float, GPU binary) ~400

## GPU Float Emissions (Phase 4 — in progress)
See `references/gauntlet_differential_battery.md` for concrete PTX and AMDGPU
float emission patterns. Key learnings:
- PTX: f32 bits live in low 32 of `.b64` VRs; use shared-memory bridge (`s[8]`)
  to extract f32 bits (PTX `mov.b32` cannot truncate `.b64`→`.b32`).
- PTX FNEG must use source operand (`neg.f32 %f<fd>, %f<fa>`), not dest.
- PTX SHL/SHR: count must be `.u32` (extract via `cvt.u32.u64` + `and.b32`).
- AMDGPU: emits text only (no real GPU exec); float ops use `v_add_f32` etc.
  with `v_cmp_*` + `v_cndmask_b32` for comparisons.
- **Pitfall**: the `patch` tool double-escapes `\n` in C strings — use
  `execute_code` with Python `str.replace` for assembly/text emission edits.

## Language feature closure (HolyD parser — holyd_parse.c / holyd_mir_eval.c)

Gauntlet-driven: each feature lands behind `./gauntlet_runner --dump-asm x86-64 '<src>'`
returning the expected `result=<N>`, then the full `--core x86-64` gate must stay
247/247 (no regressions) before commit. Recurring parser gotchas that each cost a
debug cycle:

- **`parse_expr` == `parse_comma`**: it consumes the element-separator commas, so
  an initializer/compound-literal element parsed with it swallows the whole
  `a, b, c` list as ONE comma-expression (last operand wins). Per-element lists
  MUST use `parse_assign` (stops at commas), not `parse_expr`.
- **Two function-declaration handlers exist** in holyd_parse.c (~line 1941 and a
  second ~2197). Grep for BOTH before patching param parsing — the wrong one
  edits dead code and the build silently keeps the old behavior.
- **Struct-member offsets are in CELLS** (each cell = 8 bytes) via the
  `g->structs` registry (`member_offsets*8`); MIR addresses are byte-addressed.
  A freshly-`parse_type`'d cast type has all `members[].offset == 0` — route
  compound-literal/struct writes through `mir_struct_member_offset_by_index`,
  not the parsed type's offsets.
- **Designated array init `[i]=v`**: `offset` is a BYTE offset, so scale
  `offset = i * elem_sz` (elem_sz=8). Unscaled it lands every element in cell 0.
- **K&R function defs** (`int f(a,b) int a; int b; {...}`): detect a bare IDENT
  (not a type keyword) as the first param, collect names, then parse the decl
  list between `)` and `{`; unlisted params default to int.
- **`_Complex` / `_Atomic` qualifier ORDER**: the base-type cases (`double`,
  `int`) must also consume a trailing qualifier (`double _Complex`), not just
  the qualifier-first form. `__atomic_*` builtins
  (load_n/store_n/fetch_add/fetch_sub/exchange_n/fence) take a pointer arg —
  emit load/store/add through the address VR; fences are no-ops.
- **VLA typedef** `typedef int arr_t[i]`: the typedef parser must consume a
  `[size]` suffix after the name and wrap the base in an ARRAY type (size 0 for
  a variable length), updating the registry entry.
- **After a partial `.o` rebuild, stale binaries lie**: a full
  `make gauntlet_runner` is required, or the old binary re-reports the old
  wrong result and you think the fix failed.

## Research
~/vault/MANIFESTO.md
~/vault/research/MEGA_RESEARCH_COMPILER_IMPROVEMENTS_2026-08-15.md
