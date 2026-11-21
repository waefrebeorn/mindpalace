---
name: wubuos-jit-self-hosted
description: WuBuOS self-hosted JIT stack — x86-64 encoder, disassembler, register allocator, mini C compiler
category: systems-programming
version: 1.2
---

# WuBuOS JIT Self-Hosted Stack

## Kernel Heap (memory.c)

- `mem_walk()` — Bloom filter scan: walks `g_heap_base..g_heap_end` in 8-byte steps, matching `MEM_USED_SIGNATURE` at offset 0
- `mem_bloom_scan(sig, cb, ctx)` — SWAR-like linear scan, also checks offset 8 for `MEM_UNUSED_SIGNATURE` (CMemUnused overlay)
- `mem_check_redzones(ptr)` — validates `MEM_CANARY_FRONT`/`MEM_CANARY_BACK` around allocation (16B each side)
- `mem_validate_all()` — scans all blocks for corrupted canaries
- `mem_debug_dump()` — visual box-drawing heap state to stderr
- `mem_walk_stats()` — counts used/free blocks via bloom scan
- Red zone layout: `[CMemUsed header] [front canary 16B] [user data] [back canary 16B]`
- CMemUnused overlay issue: `u->next` (8B pointer at offset 0) overlaps CMemUsed.signature (4B at offset 0) + CMemUsed.size (4B at offset 4). After free, both signature and size are destroyed by the next pointer. Bloom scan at offset 8 finds `MEM_UNUSED_SIGNATURE` there (it's the CMemUnused.signature field at CMemUnused offset 8).
- **General rule for union-style heap node reuse**: when free-node fields overlay used-node fields, any field below the free-node's own size is corrupted. Always re-read from the free-node layout, not the used-node layout, after a block is freed.
- `mu->size` always trimmed to `total` (requested allocation including header + red zones) before writing canaries

## Vulkan Software Fallback (bear_vulkan_soft.c)

- `#ifdef HAS_VULKAN` → real GPU path in bear_vulkan.c (SPIR-V shaders in bear_vulkan_shaders/)
- `#else` → CPU fallback in bear_vulkan_soft.c (pure C compute)
- bear_vulkan.h: opaque VkBuffer/VkDeviceMemory types when no Vulkan SDK
- Software kernels: GEMM, elementwise add, ReLU, sigmoid, softmax, tanh, GAE, env step
- Forward pass: walks `net->layers[]` array, applies `layer->param->weight/bias` with GEMM + activation
- GAE: reverse scan with delta = r + gamma * V' * (1-done) - V, last_gae = delta + gamma * lam * (1-done) * last_gae

The JIT runtime is fully self-hosted — zero external deps. Four components:

1. **wubu_x86.h/c** — Wx86Enc buffer-based x86-64 encoder (40+ instructions, REX.W, ModRM, SIB, rel32 backpatching)
2. **wubu_disasm.h/c** — Trivial x86-64 disassembler (wdisasm_one, wdisasm_dump, handles the encoded subset)
3. **x86_regalloc.h/c** — Linear-scan register allocator (16 GP regs, caller/callee-saved split)
4. **jit_minic.c** — Self-hosted C-to-x86-64 compiler (replaces MIR/c2m external dep)

## jit_minic.c Details

- **Tokenizer**: Two-token lookahead (cur/peek), handles keywords (int/long/I64/U8/void/return/if/else/while), identifiers, numbers, all C operators
- **Parser**: Recursive descent — expressions → comparisons → additive → multiplicative → primary
- **Expression result**: Always in RAX, pushed/popped for binary ops
- **SysV AMD64 ABI**: Args in RDI,RSI,RDX,RCX,R8,R9; return in RAX
- **Stack layout**: Args pushed from n-1 down to 0; arg[i] at [rbp - 8*n + 8*i]
- **Stack allocation**: SUB RSP, 256 pre-allocated to prevent push clobbering locals
- **Jumps**: Jcc/JMP use rel32 with backpatching via wx86_patch_rel32
- **SETcc + MOVZX**: For comparison results (setcc al; movzx rax, al)

## JIT executable-memory model (W^X, WSL2/modern kernels — 2026-08-19)

`jit_alloc_exec` / `jit_lock_exec` / `jit_free_exec` (in `src/jit/jit.c`) must produce an
**executable** mapping. The portable, kernel-agnostic approach is the **memfd dual-map**:

- `#define _GNU_SOURCE` MUST be at the very TOP of jit.c (before any `#include`), so
  `memfd_create()` / `MAP_SHARED` are declared. Defining it later (after system includes)
  makes the declaration implicitly-int and returns a truncated `int fd` → silent failure.
- `jit_alloc_exec(size)`: `memfd_create("wubu_jit", MFD_CLOEXEC)` → `ftruncate(fd, size)`
  → `mmap(RW, MAP_SHARED, fd)` for writing code+data. Return the RW pointer.
- `jit_lock_exec(ptr, size)`: `munmap` the RW mapping, then `mmap(RX, MAP_SHARED, fd)`
  at the SAME fd for execution. Keep a `jit_map[]` table (ptr↔fd↔size) so `free` finds it.
- `jit_free_exec(ptr, size)`: look up the table, `munmap` both, `close(fd)`.

**W^X trap (the actual 2026-08-19 crash):** generated code that writes its OWN data section
at runtime (e.g. `mov [rip+disp], rax` to store a global) CANNOT run on a dual-map page,
because the code page is RX (read-only to the store) while the data lives in the separate RW
page. On this WSL2 host `mmap(RWX)` is in fact writable AND executable (W^X is NOT enforced),
so the simplest robust primary is `mmap(RWX)` anonymous — code+data RWX in one page, runs
and self-writes fine. Keep memfd as a fallback for strict-W^X systems (with the caveat that
runtime self-modifying/self-writing code won't run there — a separate-data-region change is
needed). **Do NOT use `mmap(RWX)` + `mprotect(RX)`** — WSL2 silently drops the W bit, leaving
an RX page that crashes on the first instruction's store (or, for pure-code buffers, on `push`).

The HolyC REPL (`wubu_holyd_eval`) keeps the RWX page (never `jit_lock_exec`s it) precisely
because REPL globals are stored at runtime into the data section. `test_holyd` / `test_holyc_agi`
MUST be built with `-DWUBU_HOSTED` or `jit_alloc_exec` returns a plain non-executable `malloc`
and the JIT page SIGSEGVs on entry.

## Global-variable codegen convention (off-by-one, 2026-08-19)

Symbols for module-level globals are stored as `stack_offset = -(global_offset + 1)` in
HCGen (see VAR_DECL in `holyc_codegen_stmt.c`). To recover the real data-section offset:
**`global_offset = -off - 1`**, NOT `-off`. The `emit_lvalue_addr` / `emit_base_addr` paths
already do this correctly. The inline IDENT-load path in `holyc_codegen_expr.c` had the bug:
it used `data_offset = -off` (off by one) so a load of `x` (global_offset 0 → symbol
stack_offset -1) fetched `data[1]` instead of `data[0]` → returned 0. Fix: `int32_t global_off
= -off - 1;` use it for both the prefetch and the `global_patches[].global_offset`. Symptom:
`x + 10` after `I64 x = 123;` returns 10 (x read as 0), but the store and the persistence
(`data[0]==123` survives across evals) are correct — the bug is purely the load offset.

## Key Pitfalls

- **Push order**: Push args from n-1 DOWN to 0, so arg[0] ends at [rbp-8*n]
- **Stack clobbering**: Without SUB RSP before locals, push/pop in expressions overwrites local variable slots
- **Disassembler gaps**: wdisasm doesn't decode memory-operand MOVs (0x89/0x8B with ModRM mod=1) — shows as `db 0x89`; functional code is still correct
- **JIT_LANG_EXPR=3**: New enum for raw expressions — minic wraps them as function definitions automatically
- **JIT_SRCS**: Makefile variable bundles jit.c + wubu_x86.c + wubu_disasm.c + jit_minic.c for all link lines

## Build & Test

```bash
cd /home/wubu/wubuos
make all          # Full build
make test_jit     # 82 JIT tests
make test         # Full test suite
```

## Backend Dispatch

- **MMAP** (default): Hand-encoded x86 for simple expressions (a+b, a*b, etc.)
- **MIR**: C source → self-hosted minic compiler → x86-64 machine code; falls back to gcc+dlopen for HolyC
- **ASMJIT**: Assembly text → Wx86Enc encoder with label backpatching → executable

## References

- `references/holyc-repl-persistent-var-fix-2026-07-06.md` — HolyC REPL persistent variable bug fix across multiple evals. Root cause: global var loads with stack_offset==0 treated as locals, missing runtime patches for IDENT loads, stale global_patches preserved across compilations.
