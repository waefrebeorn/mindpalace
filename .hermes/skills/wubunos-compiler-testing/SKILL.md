---
name: wubunos-compiler-testing
description: WuBuNOS compiler gates gauntlet_runner + test_isa_driver. Covers the HolyD C compiler frontend, MIR intermediate representation, x86-64 JIT, gauntlet test infrastructure, and all known codegen patterns and pitfalls.
category: software-development
---

# WuBuNOS Compiler Testing — the universal correctness gate

Owns the compiler repo's TWO test gates: gauntlet_runner + test_isa_driver.
Body-side gate: the `wubuos-test-suite` skill — verify its claims by running
the target, never trust an "all green" note. Frontend: **HolyD** (HD_ prefix,
holyd_*.c). Encoder/interpreter opcode contract rule (one shared opcode
header per ISA, executor numbering is the contract, comparison-battery
coverage): `references/opcode-contract.md`.

**MIR self-hosting battery — 142 probes, expect 0 WRONG, 0 crash** (one known
  deferred case: `float add`, which needs true f32). For how to MEASURE results
  honestly here — the gauntlet's ~60-pass noise band (six runs of one binary: 1519–1581, median ~1559 — see `references/measurement-and-hangs.md`), extracting diagnostics from
  a rejected test, and classifying rejections before changing rules — see
  `references/measurement-and-diagnostics.md`.

The HolyD→MIR→interpreter self-hosting battery (`tools/test_mir_battery.c`) is **117/117 PASS, 0 WRONG, 0 crash**. Covers: arithmetic, bitwise, comparisons, logical, ternary, compound assignment, variables, functions (nested/recursive/multi-arg), control flow (if/else/while/for/do-while/break/continue), arrays, pointers, structs, sizeof, string/char literals, float arithmetic, scope shadowing, comma operator, type inference (auto), global vars.

## DMake — Gauntlet Depot Build System (2026-09-06)

The gauntlet test depot is managed by `scripts/dmake.py` — a Python build system that acquires, generates, and manages test suites from upstream sources.

### Depot structure
```
test_gauntlet/
  depot/                  # upstream repo clones (gitignored)
    fujitsu/upstream/     # Fujitsu Compiler Test Suite
    c-testsuite/upstream/ # c-testsuite
    writing-c-compiler/upstream/
    incremental/upstream/ # AMLeng/incremental_c_compiler_tests
    compcert/upstream/    # AbsInt/CompCert-small-tests
    8cc/upstream/         # rui314/8cc
    csmith/               # csmith-project/csmith
  suites/                 # generated gauntlet C files (tracked)
    gauntlet_fujitsu_proper.c
    gauntlet_fujitsu_proper_outputs.c
    gauntlet_c_testsuite_single.c
    gauntlet_incremental.c
    gauntlet_compcert_regression.c
    ...
```

### Commands
```sh
python3 scripts/dmake.py acquire    # clone/update upstream repos
python3 scripts/dmake.py generate   # produce gauntlet C files from upstream
python3 scripts/dmake.py status     # show depot status
python3 scripts dmake.py clean      # remove generated files
python3 scripts/dmake.py clean-all  # remove everything including upstream clones
```

### CRITICAL — Never concatenate multi-file tests

Multi-file tests (Fujitsu, etc.) are designed as separate translation units with specific linkage. Concatenating them destroys test semantics. Only single-source tests should be extracted for gauntlet suites. For multi-file tests, compile each `.c` file separately and link them together.

### Acquired test inventory (2026-09-06)
- Fujitsu: 104 single-source tests with reference outputs
- c-testsuite: 220 single-file tests
- writing-c-compiler: 157 valid tests
- incremental: 207 stage tests
- compcert: 70 regression tests
- **Total: 758 properly-acquired tests from 5 upstream sources**

### Test format types
1. **Return-value**: `main()` returns expected int64 (most suites)
2. **Output-comparison**: stdout compared against reference output (Fujitsu proper, c-testsuite single, compcert regression)

Output-comparison tests use a separate `_outputs.c` file with expected output strings.

## Current Scorecard (2026-09-17)

**Gauntlet v3 (6 workers, complete):**
- **1,257 PASS / 275 FAIL / 1,136 ERROR / 1,763 SKIP = 4,431 tests**
- **Valid tests: 2,668 (after filtering truncated/invalid extractions)**
- **Pass rate on valid tests: 47.1%**
- **Baseline (pre-rewrite, commit 0081fb2): 1,212 PASS**

**IMPORTANT: Only x86-64 target works on this host.** All other 13 targets return wrong results for basic `return 42`. Gauntlet counts test-target pairs, NOT tests.

## Verified current state (re-derive these exact commands, do not refold old claims)

Run the real gates below and report the tools' own RESULT output. A README or memory claim of "make test GREEN" is stale the moment a single `make test_*` assembly fails.

- **Gauntlet v3** (`./gauntlet_v3 --jobs 6` from `/home/wubu/wubunos`): **1,257 PASS / 275 FAIL / 1,136 ERROR / 1,763 SKIP = 4,431 tests**; valid tests 2,668 → **47.1%**. Only `x86-64` target works on this host; the other 13 return wrong results for `return 42`. Gauntlet scores vary ±3-6 between runs (timing-sensitive, fork-per-test); run 3× and take the median before calling anything a regression.
- **Open blocker — the full `make test` gate is NOT green.** At the wubunos root, `make test` links `test_tgemm` against the OS-side JIT runtime and **segfaults under `-O3`** (Makefile CFLAGS: `-O3 -march=native -mavx2 -mfma -frename-registers -funroll-loops`). The same sources at `-O0 -g` give **576/576** entries vs naive C GEMM; `-O1` gives green. The `-O3` crash is an optimizer-sensitive miscompile in the x86-64 JIT/run path that is **still open** — I did not resolve it this session. The compiler gates (`all` = test_isa_driver + test_mir_opt) are green, but the shared `make test` target that exercises the OS JIT runtime is red on one target.
- **wubuwizard `test_codec`** (research/067 universal codec): broke at link with `5× undefined gelu`. The image-encoder source calls `gelu()` while `include/wubu_activations.h` exports `wubu_gelu()`. Fix: `gelu()` → `wubu_gelu()` in `src/wubu_imgenc.c`. `make test_codec` then **PASSED** (audio→image→ViT tokens, ratio 0.82) — verified green, worth re-running after any wubuwizard edit.

**Latest confirmed fixes (2026-09-17):**
- **Score: 1,257/2668 (47.1%)** — up from 1,235
- **Char array init from float**: `char arr[] = {4.0}` now correctly stores 4 (was 0). Added DTOI conversion + truncation in brace-init flattening code for both nested and flat initializers. Pitfall: `mir_truncate_to_type` ANDs with 0xFF which is wrong for raw IEEE 754 bits — must convert float→int FIRST with MIR_DTOI.
- **Char dimension in array decl**: Lexer now sets `int_val` for char tokens. `array['\n']` evaluates to 10 (was garbage from uninitialized int_val). Without this, array dimensions using char constants are random.
- **Assignment to char array elements**: `array[1] = 128` now correctly stores -128 (was 128). Looks up element type from array variable for INDEX LHS nodes. Pitfall: INDEX nodes have NULL type — must walk to root IDENT and look up `g->vars[i].type->base`.
- **Float-to-int detection for NULL rhs_type**: `-2.6` (NEG of float literal) has NULL type. Added AST walk: if `rhs_type` is NULL, check if RHS is `HD_AST_NEG` → `HD_AST_FLOAT_LIT`. Without this, float values assigned to int/char variables skip DTOI conversion.
- **ldexp JIT calling convention**: `ldexp(double x, int n)` passes `n` in RDI (not XMM1). Known external libc functions with no body are now routed as `func_id=0xFFFF` (external) instead of internal calls.
- **Pointer subtraction with ADDR(DOT)**: `&s.b - &s.a` returns 1 (was 8). SUB handler checks ADDR nodes and looks up var type from var table to determine `ptr_scale`.
**Byte-addressable memory + type-system wave (chapter_16 -- see `references/byte-addressable-memory-and-types.md`):** signed-char movsx load, byte-packed string literals, char-pointer stride=1, pointer-to-array `int (*p)[N]` (parser built the wrong type), hex literals with bit 63 set (strtoll saturates -> strtoull), float-builtin return typing, float-compare operand truncation, 3D+ arrays broken by uninitialized `vla_dims`, recursive brace-init flattening, static char array from string, and the **MIR_TO_PTR double-add** that core-dumped EVERY external call with a string arg (strcmp/puts/strlen -- masked because copysign/abs have no string arg). chapter_16 measured 16->17->18/33 on fresh binaries. All gated: `make test` 195/195, selfhost 155/155, fuzz_diff 0 mismatches.
- **Known remaining blockers (post byte-addressable-memory wave)**: char/string byte-addressable memory, pointer-to-array, and 2D-array member byte access are LARGELY CLOSED. 3D+ arrays are CLOSED (recursive brace-init flattening + zeroed `vla_dims` -- a flags array read in a `for d < n` loop must be memset or garbage past the last set index is a silent wrong-branch). External calls with string args are CLOSED (MIR_TO_PTR single-add + char*[] brace-init stores pointer). Remaining, all architectural not localized: (1) 2D char array rows need consistent byte-packing (char n[][6] string-init wants 6-byte rows, explicit brace-init wants 8-byte cells -- same type, unresolved); (2) char*[] multi-level indexing `s[0][0]`/`*s[0]` needs per-level type tracking through the intermediate char* (walk-to-base-IDENT loses it); (3) 4-byte-int byte-layout tests need a cell-model change; (4) struct layout (~24 tests); (5) register allocator (~2 tests, incl. the large-64-bit AND const-VR interaction). Library-only files with no `main` are unrunnable (harness limitation, not a compiler bug). See `references/byte-addressable-memory-and-types.md`.

## Known Failure Categories

**MIR battery:** 117/117 PASS

## VLA (Variable Length Arrays) — Implemented (2026-09-06)

VLAs are supported in HolyD via a fixed-block allocation strategy within `prog.mem`.

### Implementation

**Parser** (`holyd_parse.c` ~line 1735): Array declarators now parse runtime expressions for dimensions:
- `int a[5]` — constant size, handled as before
- `int a[n]` — VLA: parses `n` as expression, marks `is_vla=1`

**AST** (`holyd_ast.h`): New fields on `HDASTNode`:
- `int is_vla` — 1 if this var_decl is a VLA
- `HDASTNode *vla_size_expr` — runtime expression for total element count

**Codegen** (`holyd_mir_eval.c` ~line 1024): VLA allocation:
- Allocates a fixed 256-cell block per VLA in `prog.mem` via `wubu_mir_alloc`
- Stores base address as the variable's value
- Marks var as `is_vla_ptr=1` (not `is_array`) for correct access patterns
- Variable type converted from `HD_TYPE_ARRAY` to `HD_TYPE_PTR`

**Limitations:**
- Fixed 256-cell block per VLA (not runtime-sized) — sufficient for gauntlet tests
- Multiple VLAs in same function share the flat prog.mem space (no stack discipline)
- Does not support VLAs in recursive functions (no frame cleanup)

### Verified working
```c
int main() { int n = 5; int a[n]; a[0] = 42; return a[0]; }        // result=42
int main() { int n = 3; int a[n]; a[0]=1; a[1]=2; a[2]=3; return a[0]+a[1]+a[2]; } // result=6
int f(int n) { int a[n]; a[0] = 7; return a[0]; } int main() { return f(5); } // result=7
int main() { int n = 3; int a[n][n]; a[1][1] = 99; return a[1][1]; } // result=99
```

## gauntlet_v3 Fork+File Double-Free Fix (2026-09-06)

**Bug:** gauntlet_v3's `run_single_test` called `wubu_mir_free` in forked children. Freeing in a forked child corrupts the parent's heap metadata (copy-on-write), causing double-free crashes.

**Fix:** Created `run_single_test_nofree` — same as `run_single_test` but skips `wubu_mir_free`. Forked children call `_exit(0)` without freeing. Memory is reclaimed by the OS when the child exits.

**Result:** gauntlet_v3 no longer crashes with double-free on full runs.

**Worker 0 fix (2026-09-06):** The main loop must `waitpid()` BEFORE reading the result file. Reading before waiting produces empty results because the worker hasn't finished writing yet.

## User Vision: HolyD + DMake → AGI Forward Path

The user's standing goal: **get out of JIT hell by beating everything in JIT, then learn how to actually compile.** The path is:

1. **HLE (Holy Language Engine)** = HolyD frontend + MIR + x86-64 JIT — current state
2. **Beat all gauntlet tests in JIT** — prove codegen correctness
3. **LLE (Low-Level Engine)** = real backend compiler — the next step after JIT parity

**HolyD and DMake are the way for AGI to forward.** The compiler IS the AGI's foundation. Every gap closed in the gauntlet is a step toward LLE.

### Key principle: We make the framework ourselves

- Don't rely on upstream CMake or test frameworks
- Build our own test acquisition (DMake), our own runners (gauntlet_v2/v3), our own compiler (HolyD)
- Never concatenate multi-file tests — it destroys test semantics
- Properly acquire tests: single-source extraction, reference output comparison
- The gauntlet tests ARE compiler testers — the work is building the compiler, not doing "prework"

### Strategic direction

The user explicitly rejected "prework for the compiler" — the gauntlet infrastructure work IS the compiler work. The goal is to get out of JIT hell by:
1. Beating everything in JIT (prove correctness)
2. Learning how to actually compile (build LLE)
3. Using HolyD + DMake as the AGI's forward path

## Multi-threaded Runner (gauntlet_v3)

For faster iteration, use `gauntlet_v3` which uses fork-per-test within worker processes:

```sh
cd /home/wubu/wubunos
./gauntlet_v3 --jobs 6
```

Each worker process runs a subset of tests sequentially, forking a child per test for crash isolation. Workers run in parallel.

## Build path criticalities

**CRITICAL:** The project root is `/home/wubu/wubunos` (NOT `/home/wubu/wubuos`). 
The file tree has:
- `/home/wubu/wubuos` — old/branch wubuos namespace
- `/home/wubu/wubunos` — active compiler repo with test suites in `test_gauntlet/`

Always run builds from `/home/wubu/wubunos` or use absolute paths. The test suite files 
(`gauntlet_gcc_torture.c`, etc.) are in `/home/wubu/wubunos/test_gauntlet/suites/`.

## Debug removal pitfall (2026-08-31 → updated 2026-09-01)

**CRITICAL PITFALL:** Removing debug `fprintf` statements can create a "dangling if" bug:

```c
if (n->left && n->left->kind == HD_AST_MEMBER)
    fprintf(stderr, "...");
if (addr) { store ... }
```

When the fprintf is removed, this becomes:

```c
if (n->left && n->left->kind == HD_AST_MEMBER)
if (addr) { store ... }
```

The second `if` becomes nested inside the first! Assignment to IDENT targets (e.g., `x = 42`)
skips the store entirely because `HD_AST_IDENT` doesn't match `HD_AST_MEMBER`.

**Fix:** Always verify after debug removal:

```sh
./gauntlet_runner --core --target x86-64
```

Verify 247/247 BEFORE running full gauntlet.

## External function crash fix (2026-09-04)

**Problem:** Tests calling undefined functions (abort, exit, printf, malloc, etc.) crashed the JIT. The MIR builder assigned func_id=0 (main) to unknown functions, so the JIT emitted `call rel32` to main — infinite recursion or stack corruption.

**Fix (two parts):**
1. `holyd_mir_eval.c` line ~1916: Unknown functions now use `func_id = 0xFFFF` instead of 0:
   ```c
   uint32_t call_fid = (fid >= 0) ? (uint32_t)fid : 0xFFFF;
   wubu_mir_call(g->prog, call_fid);
   ```
2. `wubu_isa_x86_64.c` JIT fixup: When `func_id == 0xFFFF`, replace the 5-byte `call rel32` with `xor eax, eax` (return 0) + nops.

**Result:** +205 PASS, -1,181 ERROR across the full gauntlet.

## callps pos pitfall (2026-09-04)

In the x86-64 JIT fixup loop, `callps[ncallp].pos` points to the rel32 operand of the `call` instruction, NOT the `call` opcode itself. The `call` opcode is at `pos - 1`. When patching a `call rel32` (5 bytes: E8 xx xx xx xx), write to `pos - 1` through `pos + 3`, not `pos` through `pos + 4`. Writing to `pos` overwrites the rel32 bytes and leaves the E8 opcode intact, which decodes as a garbled instruction.

## Patch tool truncation pitfall (2026-09-05)

The `patch` tool (and `execute_file` writes) TRUNCATE large content. When inserting >~200 lines of code via a single patch call, the tool returns success but the file ends up with a truncation marker instead of the actual content.

**Symptom:** File compiles with `missing terminating "` character` or `expected ',' or ';' before` errors at the truncation point.

**Fix:** For large code insertions, write the content to a separate file first (via `write_file` or a Python script), then use smaller patches or `sed` to incorporate it. Never put >100 lines of code in a single `old_string`/`new_string` patch call.

**Recovery:** If truncation occurs, `git checkout <file>` to restore, then use a different approach.

## Gauntlet scoring is non-deterministic (2026-09-09)

The gauntlet pass count varies by ±3-6 between runs due to timing-sensitive tests and the fork-per-test runner. A single run showing 2,497 might show 2,503 on the next run with identical code. **NEVER trust a single gauntlet run as evidence of regression or improvement.** Run 3+ times and take the mode/median. If the fail/error split changes between runs (e.g., 387/1547 vs 389/1545), the difference is flaky tests, not code changes.

**Pitfall**: Spending hours "debugging" a regression that is actually gauntlet noise. Before investigating a score change, run the gauntlet 3 times at the old commit and 3 times at the new commit. Only investigate if the median differs by >2.

**Pitfall**: Multiple uncommitted changes interacting. When you make several changes at once (e.g., NaN handling + float conversion + call-site conversion), you cannot tell which change caused a regression. **Test each change individually**: commit, run gauntlet 3x, then add the next change.

## Stale binary trap (2026-09-08, reinforced 2026-09-09)

After editing `.c` files, `make` sometimes does NOT rebuild the binary (especially when switching between `gauntlet_runner`, `gauntlet_v3`, etc.). Multiple sessions have lost hours debugging "bugs" that were already fixed in source but not in the binary. **ALWAYS force rebuild after source changes:** `rm -f gauntlet_runner gauntlet_v3 *.o && make <target>`. Verify with `--dump-asm` on a known test case before running the full gauntlet. If results don't match expectations after a fix, suspect stale binary FIRST.

**CRITICAL MAKEFILE TRAP**: The `gauntlet_v3` Makefile target ends with `rm -f gauntlet_runner`. Building `gauntlet_v3` DELETES the `gauntlet_runner` binary. The two binaries are separate build targets sharing the same source files. After editing source:
1. `make gauntlet_v3` — builds gauntlet_v3, deletes gauntlet_runner
2. `make gauntlet_runner` — builds gauntlet_runner (needed for `--dump-asm` debugging)

Always rebuild BOTH after source changes. A stale `gauntlet_runner` produces output from OLD code, making you think your fix didn't work.

## Pipe read pitfall (2026-09-04)

When the gauntlet grandchild crashes (stack-smash, segfault) before writing to the result pipe, the child's `read()` blocks forever waiting for data that will never come. The 20s watchdog kills the grandchild but the child is already stuck in `read()`.

**Fix:** Always set pipe reads to `O_NONBLOCK` in fork-and-pipe loops:

```c
fcntl(pfd[0], F_SETFL, O_NONBLOCK);
```

With `O_NONBLOCK`, `read()` returns 0 (EOF) when the grandchild dies without writing, and the child records ERROR and continues.

## OOM prevention (CRITICAL — batch forking)

The old `gauntlet_runner` forks batch children (MAX_TESTS_PER_CHILD=100). Each batch child forks grandchildren. The parent accumulates COW page tables across thousands of forks → OOM at ~3.5GB RSS.

**Fix:** Use `gauntlet_v2` which forks a fresh child per test with `mallopt(M_MMAP_THRESHOLD, 0)` and a 10-second `SIGKILL` timeout. Each child exits immediately — no COW accumulation.

## Fork+timeout pitfall: alarm() does NOT work for JIT hangs

Using `alarm(5)` + `sigsetjmp`/`siglongjmp` to detect JIT hangs DOES NOT WORK. Signals are not delivered while the JIT runs a tight infinite loop — `siglongjmp` never fires and the parent hangs forever.

**Fix:** Fork a child per test. Parent runs a `waitpid(pid, &status, WNOHANG)` loop with `usleep(100000)` (100ms) for N iterations. After timeout, `kill(pid, SIGKILL)` then `waitpid(pid, &status, 0)` to reap. The child dies, the parent continues. This is what `gauntlet_v2` does.

## HolyD pointer type limitation (2026-09-05) — BYPASSABLE via dlsym

The HolyD compiler does NOT support pointer types in function signatures or variable declarations. `U8*`, `void*`, `I32*` all fail to parse. This blocks implementing libc functions (memcpy, memset, strcmp, strlen, malloc) as HolyD builtin functions.

**Bypass via dlsym:** The x86-64 JIT can call libc functions directly via `dlsym` + SysV calling convention (see "dlsym-based libc calls" section). This bypasses HolyD entirely — the compiler never sees pointer types because the call is generated at the JIT level, not the HolyD level. Works for 1-arg functions; 2+ args crash (unresolved).

## dlsym-based libc calls (2026-09-06) — WORKS for 1-2 arg functions

The x86-64 JIT resolves libc functions via `dlsym(RTLD_DEFAULT, name)` at compile time and emits real calls with proper x86-64 SysV calling convention. Works for 1-arg integer functions (`abs`, `labs`, `putchar`) and 2-arg pointer functions (`strcmp`). 3+ arg functions (`memset`, `memcpy`) crash — root cause: MIR_TO_PTR conversion needed for pointer arguments.

**How it works:**
1. When MIR_CALL has func_id=0xFFFF and func_name is set, call `dlsym(RTLD_DEFAULT, name)` then `dlsym(RTLD_NEXT, name)` as fallback
2. Read VR1/VR2/VR3 physical register encodings via `VR_ENC_SAFE(n)` BEFORE saving registers
3. Save 8 caller-sysv registers: r11, r12, r13, r14, r15, r8, r9, rdx (push)
4. Move arguments: `emit_mov_reg(&e, 7, vr1)` (rdi←VR1), `emit_mov_reg(&e, 6, vr2)` (rsi←VR2), `emit_mov_reg(&e, 2, vr3)` (rdx←VR3)
5. `movabs rax, <dlsym result>; call rax`
6. `emit_mov_reg(&e, VR_ENC_SAFE(0), 0)` (VR0_home←rax)
7. Restore 8 registers (pop in reverse order)

**CRITICAL PITFALL — `emit_mov_reg` uses x86-64 register encodings, NOT MIR allocator encodings:**

`emit_mov_reg(dst, src)` expects x86-64 register numbers (0=rax, 7=rdi, 6=rsi, 2=rdx, 11=r11, etc.) — the SAME encodings that `VR_ENC_SAFE()` returns. Do NOT pass MIR allocator pool indices (where 13=rdi, 12=r10, 11=rsi). Passing MIR encoding 13 when you mean x86-64 encoding 7 (rdi) emits `mov r13, r11` instead of `mov rdi, r11` — silent corruption.

```c
// CORRECT: x86-64 encodings
emit_mov_reg(&e, 7, vr1);   // rdi = VR1
emit_mov_reg(&e, 6, vr2);   // rsi = VR2
emit_mov_reg(&e, 2, vr3);   // rdx = VR3

// WRONG: MIR allocator encodings (13=rdi in MIR pool, but 13=r13 in x86-64)
emit_mov_reg(&e, 13, vr1);  // emits mov r13, ... — WRONG
```

### JIT register conflict: rdi vs rcx for second operand

**PITFALL:** In `wubu_isa_x86_64.c`, binary operations (ADD/SUB/MUL/DIV/MOD/AND/OR/XOR/SHL/SHR) load the second operand into `rcx`, NOT `rdi`. This is because `rdi` (x86 encoding 7) is also used by `emit_mov_rax_from_vr` when the source VR happens to be assigned to rax (encoding 0) — but the `mov rcx, b_reg` instruction would clobber rax if b_reg were rax.

The correct register for the second operand is `rcx` (x86 encoding 1):
```c
case MIR_ADD: rex(&e,1,0,0,0); e8(&e, 0x01); e8(&e, 0xC8); break; /* add rax,rcx */
```

When adding new binary ops to the JIT, always use `rcx` for the second operand, never `rdi`.

MIR variables hold offsets into `prog.mem` (cell indices), not actual pointers. When passing arrays/string literals to libc functions, the JIT must convert these offsets to real pointers via a `MIR_TO_PTR` instruction: `dst = rbx + a * 8` (where rbx = `wubu_jit_mem_ptr`).

The MIR builder (`holyd_mir_eval.c`) generates MIR_TO_PTR before external calls when the argument is `HD_AST_STRING_LIT`, `HD_TYPE_ARRAY`, `HD_TYPE_PTR`, or `mir_var_is_array()`.

**PITFALL — `is_array` flag not set for string literal initializers:**

`char src[] = "hello"` was NOT detected as an array because `is_array` was based on `arr_size > 0`, but unspecified-size arrays have `arr_size=0`. Fix: check `n->type->kind == HD_TYPE_ARRAY` instead. Without this fix, MIR_TO_PTR is never generated for string arrays, and libc functions receive garbage offsets instead of pointers.

**Status (2026-09-06):**
- 1-arg integer functions: WORK (`abs(-5)`=5, `labs(-42)`=42, `putchar('A')`=65)
- 2-arg pointer functions: WORK (`strcmp("hello","hello")`=0)
- 3+ arg functions: CRASH (`memset`, `memcpy` — MIR_TO_PTR helps but crash persists)
- Float functions: WRONG RESULT (`fmax` — needs xmm registers, not rdi/rsi)

## User preference: NO truncation as band-aid — implement width-aware codegen

The user explicitly REJECTS truncation as a gap-closing strategy: **"truncation is a cheat fix"**. The correct approach is **width-aware codegen** — emit `movl`/`addl` (32-bit) for 32-bit types and `movq`/`addq` (64-bit) for 64-bit types, matching what GCC/chibicc do.

Research confirms: GCC uses `movl` (32-bit) for `int` operations and `movq` (64-bit) for `long` operations. On x86-64, 32-bit arithmetic automatically zero-extends to 64 bits (correct for `unsigned int`).

The truncation approach (`mir_truncate_to_type`) is a **temporary fallback** — it works but is inefficient (extra AND+SEXT instructions after every op). The permanent fix requires:
1. Adding `width` field to `wubu_mir_instr_t`
2. Width-aware `wubu_mir_binop_w()` / `wubu_mir_unop_w()`
3. x86-64 JIT emits 32-bit instructions (no REX.W) when width==3
4. Only for arithmetic/comparison ops — NOT pointer arithmetic

See `references/implicit-type-conversion.md` for the full research and implementation plan.

## User preference: feature addition over stripping

The user explicitly REJECTS stripping C constructs as a gap-closing strategy: **"I do not approve of stripping I only approve of being actually scrupulous. I want there to be more features not less features."** The correct approach is to IMPLEMENT features properly — parser support, codegen, preprocessor semantics — not to remove constructs from test sources.

Stripping that already exists in the preprocessor (`strip_inline_asm`, `strip_attributes`, `strip_bitfields`, `strip_builtin_prefix`) is accepted infrastructure, but do NOT add new stripping to close gaps. Instead, implement the missing feature.

**The key insight:** Removing `__Atomic` from source text (cheating) ≠ implementing `_Atomic` parsing (proper). The cheating approach gives superficial test improvements but doesn't build a real compiler.

## Full gauntlet run procedure

Use `gauntlet_v2` (fork+timeout runner) — NOT the old `gauntlet_runner` which OOMs on large suites.

```sh
cd /home/wubu/wubunos
./gauntlet_v2 --suite gcc_torture
```

`gauntlet_v2` forks a fresh child per test with a 10-second `SIGKILL` timeout. No OOM because each child exits immediately. Hanging tests are killed and marked ERROR.

**PITFALL — gauntlet_v2 can hang on certain tests:** The 10s SIGKILL timeout kills the grandchild, but the child may already be stuck in a blocking `read()` call. Monitor progress with `grep 'pass=' <log>` every few minutes. If progress stalls for >3 minutes at the same test count, the runner is stuck — kill it and restart with a different suite or use gauntlet_v3 with `--jobs 1`.

**PITFALL — gauntlet_v3 double-free:** The JIT's global state (`wubu_jit_mem_ptr`) is NOT thread-safe. gauntlet_v3 crashes with double-free on full runs. Only use gauntlet_v3 for quick per-suite checks with small test counts, or with `--jobs 1`.

Run all suites:

```sh
cd /home/wubu/wubunos
for suite in gcc_torture extern_gcc c_testsuite llvm lacc fujitsu; do
  ./gauntlet_v2 --suite $suite > /tmp/gauntlet_v2_${suite}.log 2>&1
done
# Aggregate:
for f in /tmp/gauntlet_v2_*.log; do tail -1 $f; done
```

### Multi-threaded faster runs (limited use)

```sh
cd /home/wubu/wubunos
./gauntlet_v3 --jobs 1 --suite gcc_torture  # jobs=1 avoids double-free
```

### Single-target run (recommended for debugging)

Use `--target <name>` to run one ISA at a time. Target names use HYPHENS: `x86-64`, `arm64`, `m68k` (NOT `x86_64`).

```sh
cd /home/wubu/wubunos
./gauntlet_runner --target x86-64 > /tmp/gauntlet_x86-64.log 2>&1
```

### Interpreter vs JIT debugging

`--dump-asm <target> <src>` runs the JIT (compile via `drv->compile` + run via `drv->run`), NOT the interpreter. To run the interpreter, call `wubu_mir_interp` directly (e.g., via `hd_eval_mir`). When a test FAILs in the gauntlet (JIT path) but the interpreter gives a different result, the bug is in the JIT codegen/regalloc, not the frontend.

**Critical:** The gauntlet grandchild uses the JIT path (`hd_run_prog` → `drv->compile` + `drv->run`). The `--dump-asm` flag also uses the JIT path. To debug frontend vs JIT bugs:
1. Run `./gauntlet_runner --dump-asm x86-64 "<src>"` — if this gives the expected result, the frontend is correct
2. If `--dump-asm` gives wrong result but the MIR battery (interpreter) gives right result → JIT bug
3. If both give wrong result → frontend bug

**BIT FIELD PITFALL:** The interpreter (`wubu_mir_interp`) does NOT handle bit fields — it has no bit shift/mask logic. The bit field read/write code is only in the MIR builder (`holyd_mir_eval.c`, JIT path). When testing bit fields with `--dump-asm`, you're testing the JIT path, not the interpreter. If bit fields give wrong results in `--dump-asm`, the bug is in the MIR builder's bit field codegen, not the interpreter. Use `gauntlet_v2` (which uses the JIT path) as the authoritative test.

## Failure categories (as of 2026-09-09, post-truncated-test-filter)

| Category | Count | Type | Cause |
|----------|-------|------|-------|
| Truncated/incomplete test sources | ~1,763 | SKIP | Filtered by `is_invalid_test()` — truncated extractions, missing helper functions |
| Codegen bugs (wrong result) | ~328 | FAIL | JIT produces wrong values — regalloc, control flow, float handling, pointer codegen |
| Struct params/returns (ch18) | ~35 | FAIL | Struct-by-value calling convention not implemented — needs proper C struct layout with byte offsets and padding |
| Char/string (ch16) | ~18 | FAIL | Byte-addressable memory model needed — all types currently 8-byte cells |
| Pointers (ch15) | ~16 | FAIL | Pointer arithmetic & dereferencing — nested indexing, 2D arrays |
| Float edge cases (ch13) | ~13 | FAIL | 9+ arg calling convention, rounding edge cases near 2^63, ternary common type, function pointers |
| sizeof/void* (ch17) | ~11 | FAIL | Compile-time sizeof, void* support |
| Static/extern (ch10) | ~4 | FAIL | Extern scoping (global vs local), stack frame for recursion |
| Double comparisons | DONE | — | SSE2 ucomisd with correct encoding + NaN handling |
| Float literals | DONE | — | Leading-dot (.5, .01e+2) and integer exponent (1E0) work |
| Static locals | DONE | — | Guard-based init-once pattern |
| Struct initializer conversion | DONE | — | mir_gen_cast() in BRACE_INIT handler |
| Unsigned→double conversion | DONE | — | MIR_DITOF_U with exact high/low 32-bit split algorithm |
| I64/U64 float↔int conversion | DONE | — | All handlers (VAR_DECL, assignment, return, compound) now handle I64/U64 |
| Return int→double conversion | DONE | — | Return handler emits MIR_DITOF/DITOF_U for F64 return type with integer expression |
| Recursive functions | DONE | — | Interpreter frame restore (globals_end boundary) + JIT→interp routing via prog_has_recursion |
| Ternary common type | DONE | — | Both float conversion (per-branch ditof) and integer zero-extension (32-bit only) implemented |

**Key insight**: The remaining ~328 FAIL tests on VALID sources require major architectural changes (stack frame, byte-addressable memory, struct-by-value calling convention). Each carries regression risk. The easy wins are exhausted.

### Error pattern analysis (2026-09-07)

The 1,536 errors break down by root cause:

| Root Cause | ~Count | Fixable? | Notes |
|---|---|---|---|
| GCC test harness (bfin, dg-final, etc.) | ~500 | No | Platform-specific or GCC infrastructure |
| Pointer types in function params/vars | ~600 | Partial | parse_type handles `*`, but codegen fails for complex pointer patterns |
| Truncated test extraction | ~97 | Yes | New full-source suite still has some undefined references |
| abort() calls | ~442 | Done | Now no-op |
| _Complex type | ~107 | Done | Maps to F64 |
| _Decimal types | ~140 | Done | Maps to F64 |
| printf | ~500 | Done | Builtin with format string parsing |
| vector_size | ~50 | No | Requires SIMD codegen |
| 64-bit arithmetic | MANY | Done | WRAP32 + movsxd removed |
| unsigned long types | MANY | Done | Now U64 |
| unsigned constants > INT64_MAX | MANY | Done | strtoull for U/UL/ULL |
| Exit code comparison | MANY | Done | Truncate with & 0xFF |
| Variable scoping | MANY | Done | Search from end + all blocks push scope |
| Sign extension | MANY | Done | SEXT8/16/32 ops |
| Escape sequences | MANY | Done | \a \b \f \v \? added to lexer |
| Implicit type conversion | MANY | Done | All truncation points covered (assign/compound/binary/shift/return/incdec/switch) |
| 32-bit arithmetic | MANY | Done | Binary ops + shifts truncate to 32-bit |
| Constant suffix types | MANY | Done | u/l/UL propagate to AST; large constants get U64 |
| For-loop scoping | ~1 | Done | Init variable scoped to loop |
| Goto label targets | ~6 | Done | Block codegen preserves labels after RETURN |

### Test extraction improvement needed (2026-09-07)

The `generate_writing_c_compiler()` function in `scripts/dmake.py` extracts tests from `chapter_XX/valid/*.c` but does NOT include helper functions from:
- `chapter_XX/valid/libraries/*.c` (helper functions called by tests)
- `chapter_XX/helper_libs/*.c` (chapter-specific helpers)

This causes ~413 errors because tests reference undefined functions like `check_one_int()`, `id()`, `target()`.

**Fix**: Modify `generate_writing_c_compiler()` to:
1. Include all `libraries/*.c` files from each chapter directory
2. Concatenate helper sources with test sources (helper first, then test)
3. Or skip tests that reference undefined symbols

### Gauntlet suite analysis (2026-09-07)

| Suite | Tests | PASS | FAIL | ERROR | Biggest issues |
|---|---|---|---|---|---|
| extern_gcc | 1444 | 704 | 95 | 645 | bfin(355), dg_final(319), FAILURE(182) |
| gcc_torture | 1182 | 712 | 95 | 375 | abort(442), pointer(598), vector(39) |
| writing_c_compiler_full | 572 | 369 | 83 | 120 | float (ch13), unions (ch18), pointers (ch15), char (ch16), static (ch10) |
| llvm | 303 | - | - | - | pointer(123), abort(24) |
| c_testsuite | 203 | 164 | 14 | 25 | pointer(55), printf(35) |
| incremental | 207 | - | - | - | mostly clean |
| lacc | 237 | - | - | - | pointer(27) |
| compcert | 80 | - | - | - | printf(143) |
| compcert_regression | 70 | - | - | - | printf(469), pointer(114) |
| fujitsu_proper | 104 | - | - | - | printf(174), _Complex(32) |

### Still open (valid tests only, post-filter):
- **Struct params/returns** (ch18, ~33 failures): Struct-by-value calling convention — needs proper C struct layout with byte offsets and padding
- **Char/string** (ch16, ~16 failures): Byte-addressable memory model needed — all types currently 8-byte cells
- **Pointers** (ch15, ~16 failures): Pointer arithmetic & dereferencing — nested indexing, 2D arrays
- **Float edge cases** (ch13, ~7 failures): 9+ arg calling convention, NaN helper library, function pointers
- **sizeof/void*** (ch17, ~9 failures): Compile-time sizeof (side-effect suppression), void* support
- **Static/extern** (ch10, ~4 failures): Extern scoping (global vs local), stack frame for recursion
- **Recursive functions** — CLOSED (see rule 104: interpreter frame restore + JIT→interp routing).

## Key bugs fixed (chronological)

Moved to `references/bug-fix-log.md` to keep this file under the size limit.
That log is dated incident narration for archaeology only -- the GENERALIZABLE
RULES extracted from these fixes live in the Scorecard / Never-Ship / Byte-
Addressable Memory sections above and in
`references/byte-addressable-memory-and-types.md`. When you fix a new bug,
add a RULE to the topical reference, not a dated incident to the log.

## Multi-argument function call bug — diagnostic signature (2026-09-04: interpreter FIXED)

The MIR interpreter multi-arg bug is FIXED (n_args + DCE). The JIT path may still have issues. When investigating function call failures:
- 1 parameter: works (returns correct value)
- 2+ parameters with SAME values: works
- 2+ parameters with DIFFERENT values: interpreter now returns correct; if JIT returns wrong value → codegen/regalloc bug
- JIT mode with multi-arg: times out (infinite loop in callee)

Test command:
```sh
./gauntlet_runner --dump-asm x86-64 \
    "int test(int q5, int nd) { return q5; } int main() { return test(42, 0); }"
# Interpreter (n_args fix): result=42 ✅
# JIT: may still be wrong
```

Diagnostic methodology:
1. Run with `--dump-asm` (interpreter) to confirm the bug pattern
2. If interpreter gives wrong value → check optimizer + MIR generation
3. If interpreter is correct but JIT gives wrong value → codegen/regalloc
4. If JIT times out → infinite loop, suspect callee not returning (frame/rsp corruption)

61. **Stale binary trap** (2026-09-07): After editing `.c` files, `make` sometimes does NOT rebuild the binary (especially when switching between `gauntlet_runner`, `gauntlet_v3`, etc.). Hours were spent debugging a "bug" that was already fixed in source but not in the binary. **ALWAYS force rebuild after source changes:** `touch <file> && make <target>`. Verify with `--dump-asm` on a known test case before running the full gauntlet. If results don't match expectations after a fix, suspect stale binary FIRST.

**Pitfall — a failed `git stash pop` can silently drop a fix**: `git stash` / `git stash pop` around a before/after HEAD comparison can leave the working tree back at HEAD with the change gone (pop reports nothing, or lands in a conflict you skim past). A subsequent `git add <file> && git commit` then stages a NO-OP and still reports success. After any stash round-trip, verify the change is present before committing — `grep -c '<unique new token>' <file>` must be > 0 — and never trust a commit that staged zero lines. Re-apply from a known-good patch rather than assuming the pop restored it.

62. **Goto label + optimizer interaction** (2026-09-07): The DCE pass skips `MIR_LABEL` instructions, but code AFTER a label that is a goto target can still be removed because the block-level codegen loop breaks after `RETURN`. Fix: don't break after RETURN if there are LABEL statements ahead (goto can jump past return). Additionally, the optimizer's `fold_dce_pass` can remove instructions between a `jmp` and its target label if it considers them unreachable. This is still an OPEN issue — goto tests in chapter 6 still fail because the optimizer removes the label target code.

63. **Duplicate case in switch** (2026-09-07): The `patch` tool matches `old_string` by content, not by position. When a switch has multiple similar cases (e.g., two `case HD_TOK_CHAR`), a patch intended for one can modify the other — or worse, a patch can change the WRONG case entirely (e.g., changing `case HD_TOK_INT` to `case HD_TOK_CHAR`). Always include enough surrounding context (the full case block) to make the match unique. After patching, verify the switch still has the expected number of cases.

64. **Exit code 8-bit truncation** (2026-09-07): The gauntlet compares JIT result to expected using `result == expected`. Linux process exit codes are 8-bit (0-255), and the expected values from the test suite are OS-level exit codes. Must truncate JIT result with `& 0xFF` before comparison: `int64_t exit_code = result & 0xFF; return (exit_code == expected) ? 0 : 1;`. All expected values in the JSON are 0-255 (none exceed 255). Without this fix, tests like `return ~12;` (expected 243 = -13 & 0xFF) and `return -5;` (expected 251 = -5 & 0xFF) fail.

65. **Implicit type conversion on assignment** (2026-09-09): HolyD stores all values as 64-bit. When assigning to narrower types (char/short/int), the value must be truncated. Added `mir_truncate_to_type()` helper emitting AND+SEXT for signed types and AND for unsigned types. Applied in both assignment (`HD_AST_ASSIGN`) and variable declaration (`HD_AST_VAR_DECL`) handlers. Only for scalar integer types — not pointers, structs, or arrays. **Limitation**: only truncates on store, not after arithmetic operations.

66. **Goto label targets — fully fixed** (2026-09-09): Chapter 6 goto tests now pass. The block codegen fix (don't break after RETURN if labels ahead) combined with the optimizer's existing label preservation (DCE skips MIR_LABEL) resolves all 6 chapter 6 goto failures.

67. **Function argument type conversion** (2026-09-09): When passing `long` to an `int` parameter, the argument must be truncated. Implemented by adding a truncation pass AFTER all arguments are copied from registers to local slots. **CRITICAL**: Must happen after the copy loop, NOT during it — the JIT uses `rcx` as the second-operand register for AND/SEXT, and `rcx` is also the x86-64 4th argument register. Truncating during the copy loop clobbers `rcx` and corrupts the 4th+ arguments. See `references/implicit-type-conversion.md` for details.

68. **Float literal 32-bit storage is intentional** (2026-09-09): HolyD stores `HD_TOK_FLOAT` literals as 32-bit IEEE 754 float bits (via `union { float f; uint32_t u; }`), NOT 64-bit double bits. Changing to 64-bit storage breaks existing float tests (chapter 13) because the float arithmetic pipeline (MIR_FADD/FSUB/FMUL/FDIV, MIR_ITOF/FTOI) uses 32-bit SSE instructions (`cvtsi2ss`, `cvttss2si`). The `MIR_DADD/SUB/MUL/DIV` and `MIR_DITOF/DTOI` ops exist for true double-precision but the float literal path doesn't use them. **Do NOT change float literal storage to 64-bit** unless you also convert the entire float pipeline to double-precision SSE2 instructions.

68b. **Float/double updated to 64-bit** (2026-09-09 session): Float literals now store 64-bit double bits, cast handler uses MIR_DITOF/DTOI, arithmetic uses MIR_DADD/DSUB/DMUL/DDIV, negation uses MIR_DNEG. This fixes double precision arithmetic but NaN handling and float-to-int in function args remain open.

69. **Type-aware binary op truncation** (2026-09-09): Added `mir_binop_result_type()` helper that implements C usual arithmetic conversions. Binary ops (ADD/SUB/MUL/DIV/MOD/AND/OR/XOR) truncate to 32-bit when both operands are 32-bit integers. Shift ops (SHL/SHR) truncate to left operand type. This fixes `unsigned int * unsigned int` wrapping at 32 bits and `unsigned int << long` wrapping at 32 bits.

70. **Return type truncation** (2026-09-09): Added `fn_ret_type` field to `HDMirGen` struct, set from `fn->type` when entering function body. Return values are truncated to the function's declared return type. Fixes `char foo() { return 200; }` returning -56 instead of 200.

71. **Pre/post inc/dec truncation** (2026-09-09): Increment/decrement operations now truncate the updated value to the variable's type before storing. Fixes `unsigned int i=0; i--` wrapping to UINT_MAX (was giving -1 in 64-bit).

72. **Switch case truncation** (2026-09-09): Case values in switch statements are truncated to match the switch expression's type. Looks up IDENT type from var table. Fixes `case 34359738378ul` matching `unsigned int` variable with value 10.

73. **Parameter type storage** (2026-09-09): `fn->param_types[pi]` is now stored in `g->vars[i].type` when binding parameters. This enables type-aware codegen inside function bodies where IDENT nodes don't carry type annotations.

74. **For-loop scoping** (2026-09-09): For-loop init variable is now scoped to the loop body (`int scope_start = g->n_vars` before init, `g->n_vars = scope_start` after body). Fixes `for_shadow` test where inner `shadow` leaked to outer scope.

75. **Constant suffix type propagation** (2026-09-09): Added `is_unsigned`/`is_long` fields to `HDToken`. Lexer stores suffix info when scanning integer constants. Parser propagates to `HD_AST_INT_LIT.type` — large unsigned constants (>0xFFFFFFFF) get `HD_TYPE_U64` instead of being truncated to 32 bits. Fixes `68719476736u` (2^36) being treated as U64.

76. **Break in switch fix** (2026-09-09): Switch handler now pushes `break_label` onto `g->loop_done[]` BEFORE generating case bodies (was after). This ensures `break` inside a switch correctly jumps to after the switch, not falling through to the next case.

77. **Width-aware codegen attempt** (2026-09-09): Added `width` field to `wubu_mir_instr_t` and `wubu_mir_binop_w()` to emit 32-bit x86-64 instructions for 32-bit types. REVERTED because it broke pointer arithmetic — applying 32-bit ops to address calculations truncated pointers. The correct approach is to only make arithmetic/comparison ops width-aware while keeping pointer arithmetic as 64-bit. See `references/implicit-type-conversion.md` for the full research and implementation plan.

78. **User correction: truncation is a cheat** (2026-09-09): The user explicitly rejected truncation as a band-aid fix. The proper fix is width-aware codegen (movl vs movq). Research confirmed GCC/chibicc use type-width-specific instructions. The truncation approach is a temporary fallback while the proper width-aware approach is refined.

79. **Comparison truncation** (2026-09-09): Comparison operators must truncate both operands to common type before comparing. Uses `mir_binop_result_type()` + `mir_truncate_to_type()` on both sides. Fixes `(int)(-1) < (unsigned int)(0)` and similar mixed-sign comparisons.

80. **sizeof uses var table type** (2026-09-09): `sizeof` on scalar variables now uses `g->vars[i].type` via `hd_type_size()` instead of always returning 4. Fixes `sizeof d` where d is double (now returns 8).

81. **Float/double 64-bit update** (2026-09-09): Changed float literal storage to 64-bit double, cast handler to MIR_DITOF/DTOI, arithmetic to MIR_DADD/DSUB/DMUL/DDIV, negation to MIR_DNEG. Fixes double precision arithmetic. NaN handling and float-to-int in function args remain open.

82. **Forward declaration pitfall** (2026-09-09): Skipping forward declarations in `mir_collect_funcs` causes score drop because some tests rely on them being in the func table. The correct approach is to collect all functions but prefer ones with bodies when resolving calls. Track a `has_body` flag per function entry.

83. **Stale binary trap** (2026-09-08, reinforced 2026-09-09): After editing `.c` files, `make` sometimes does NOT rebuild the binary (especially when switching between `gauntlet_runner`, `gauntlet_v3`, etc.). Multiple sessions have lost hours debugging "bugs" that were already fixed in source but not in the binary. **ALWAYS force rebuild after source changes:** `rm -f gauntlet_runner gauntlet_v3 *.o && make <target>`. Verify with `--dump-asm` on a known test case before running the full gauntlet. If results don't match expectations after a fix, suspect stale binary FIRST.

84. **Nested indexing pitfall** (2026-09-08): `ptr_ptr[0][0]` (double pointer dereference) and `arr[1][2]` (2D array) require different handling in the INDEX handler. Using `mir_gen_expr(n->left)` fixes pointers but breaks arrays. Using `mir_address_of(n->left)` fixes arrays but breaks pointers. The correct fix requires distinguishing array vs pointer types in the INDEX handler — arrays need the address (for further indexing), pointers need the value (to dereference). See `references/implicit-type-conversion.md`.

85. **cvttsd2si indefinite value** (2026-09-08): The `cvttsd2si rax, xmm0` instruction returns `0x80000000` (-2147483648) for double values > INT_MAX, even with REX.W prefix. This is the "indefinite integer value" per Intel spec. For `(long)(2147483648.0)`, the result is -2147483648 instead of 2147483648. Needs range checking before conversion or alternative approach for large double-to-long conversions.

86. **Float parameter is_float flag** (2026-09-09): Function parameters of type `double` were not marked as float in the var table (`mir_bind_var` sets `is_float=0`). This caused `mir_is_float_node()` to return false for float parameters, preventing the cast handler from generating MIR_DTOI for `(long)d` or `(int)d` casts on float parameters. Fix: after `mir_bind_var` for parameters, check if `param_types[pi]->kind == HD_TYPE_F64` and set `is_float=1`.

87. **cvtsi2sd REX.W prefix** (2026-09-09): The `cvtsi2sd xmm0, eax` instruction (F2 0F 2A C0) only converts 32-bit integers to double. For `long` values, the lower 32 bits were being converted instead of the full 64-bit value. Fix: emit `F2 48 0F 2A C0` (cvtsi2sd xmm0, rax) with REX.W prefix. This fixes `(double)(-9007199254751227l)` and other large-long-to-double conversions.

88. **Forward declaration resolution** (2026-09-09): When a function has both a forward declaration and a definition, `mir_collect_funcs` collects both. Function call resolution now searches from the END of the function table (most recent first) to find the definition (with body) instead of the forward declaration (without body). **PITFALL**: Do NOT skip forward declarations in `mir_collect_funcs` — some tests rely on them being in the func table (e.g., `putchar` forward decl). Collect all, resolve to last.

89. **Alternate type specifier orderings** (2026-09-09): C allows type specifiers in any order (`int unsigned`, `long unsigned`, `long int unsigned`, `signed long`, etc.). HolyD's `parse_type` now handles these combinations after the base type token. Without this, tests using `int unsigned u;` or `long unsigned ul;` fail to parse. The fix adds follow-up token checks in the `HD_KW_I32` and `HD_KW_I64` cases.

90. **Preprocessor `signed` strip conflict** (2026-09-09): `wubu_preproc.c` `strip_compiler_keywords` strips `signed` and `_signed` as compiler keywords. This conflicts with `(signed)` cast syntax — `(signed)ui` becomes `()ui` after stripping, causing parse failure. **DO NOT remove `signed` from the strip list** — 1036+ tests need it stripped (for `__signed__` and other GCC extensions), while only 1 test uses `(signed)` cast. The cost of breaking 1036 tests outweighs the benefit of fixing 1 test. If you need `(signed)` cast support, make the strip smarter (context-aware) rather than removing it.

92. **Static local variables** (2026-09-09): `static int x = 5;` inside a function now persists across calls. Uses a guard variable pattern: allocate both `x` and a guard cell in global memory, then emit `if (guard == 0) { x = 5; guard = 1; }` at the function's declaration point. The parser marks `HD_AST_VAR_DECL.is_static = 1` when `static` is seen. The MIR generator checks `n->is_static && g->in_function_body` to apply the guard pattern (global `static` vars are unaffected). **PITFALL**: The guard check must be emitted inside the function body (at the declaration point), NOT at program start — the init expression may reference other locals or constants that are only valid inside the function scope. **PITFALL**: Only works for scalar types; static arrays with brace initializers fall through to normal init (re-initialized each call — known limitation).

93. **ERROR test reality check** (2026-09-09, updated 2026-09-08): The 1,177 ERROR tests on valid sources are compilation failures from unsupported features (pointers, chars, structs as params). The 1,763 SKIP tests are filtered truncated extractions. Focus improvement efforts on the `writing_c_compiler_full` suite which has proper complete tests requiring real compiler features.

92. **Stale binary trap — reinforced** (2026-09-09): After editing `.c` files, `make` sometimes does NOT rebuild the binary. This session lost hours debugging "bugs" that were already fixed in source but not in the binary. **ALWAYS force rebuild**: `rm -f gauntlet_runner gauntlet_v3 *.o && make <target>`. Verify with `--dump-asm` on a known test case before running the full gauntlet. If results don't match expectations after a fix, suspect stale binary FIRST.

94. **Lexer dot dispatch — character consumed before switch** (2026-09-09): The main lexer loop (`hd_lex_next`) calls `hd_advance(lex)` BEFORE the `switch (c)` at line 420. This means by the time `case '.'` is reached, the dot is ALREADY consumed and `lex->pos` points to the NEXT character. When checking for `.digit` float literals, check `lex->src[lex->pos]` (the first digit after the dot), NOT `lex->src[lex->pos + 1]` (the second digit). Calling `hd_scan_number` from the `.` case passes the wrong starting position — the dot is gone but `hd_scan_number` expects to start at a digit. Solution: handle leading-dot floats inline in the `.` case rather than delegating to `hd_scan_number`.

95. **Float literals with leading dot** (2026-09-09): `.5`, `.125`, `.01e+2`, `.01E-3` are valid C float literals. The lexer's `case '.'` now checks if the next character is a digit and, if so, parses the float inline: consume `.` (already consumed by main loop), then digits, then optional exponent, then optional suffix. Without this, `.5` is parsed as DOT followed by `5` (integer), causing parse failures in float contexts.

96. **Integer literals with exponent** (2026-09-09): `1E0`, `2e+3`, `5E-2` are valid C float literals (no decimal point needed). After parsing an integer and its suffixes, the lexer now checks for `e`/`E` and, if found, consumes the exponent and converts to float via `strtod`. Without this, `1E0` is parsed as integer `1` followed by identifier `E0`, causing parse failures.

97. **Static local guard pattern — extern shadowing limitation** (2026-09-09): The guard-based static local pattern works for most cases but fails when `extern int i;` appears inside a function to shadow a static local `static int i;`. The `extern` declaration should bring the global `i` into scope, but the var table lookup resolves to the wrong variable. This is a scoping issue in `mir_find_var_addr` — it searches from the end and finds the static local instead of the global brought in by `extern`. Fix requires tracking extern declarations as separate scope entries.

98. **REX prefix byte ordering — both orderings work for MOVQ** (2026-09-09, corrected): When encoding `movq xmm, rax` (66 0F 6E /r), BOTH `66 48` (legacy-first) and `48 66` (REX-first) orderings produce correct results. Testing confirmed: `66 48 0F 6E C0` → works, `48 66 0F 6E C0` → also works. The JIT currently uses REX-first (`rex(&e,1,0,0,0); e8(&e,0x66)`) and achieves 2,503 PASS. Do NOT "fix" this — both orderings are valid for MOVQ. For `ucomisd xmm0, xmm1`, use `66 0F 2E C1` (no REX prefix needed). The real encoding pitfall is the ModRM byte: `C0` = xmm0+rax, `C8` = xmm1+rax — getting this wrong silently compares wrong registers.

99. **Double (f64) comparisons via SSE2 ucomisd** (2026-09-09): Added MIR_DGT/DLT/DGE/DLE/DEQ/DNE operations for correct IEEE 754 double comparisons. The JIT emits: load operands into xmm0/xmm1 via `movq xmm, rax` (REX.W + 66 0F 6E /r), then `ucomisd xmm0, xmm1` (66 0F 2E C1), then `setcc al` (0F 97 C0 for seta/dgt, 0F 94 C0 for sete/deq, etc.), then `movzx rax, al`. The MIR generator selects double comparison ops when either operand is f64 (via `mir_cmp_op()` helper). **CRITICAL**: `mir_binop_result_type()` must return NULL for F64 operands (treat F64 as 64-bit) — otherwise the comparison operands get truncated to 32 bits before the double comparison, producing wrong results. Without this fix, `for(double d=100.0; d>0.0; d-=1.0)` loops 0 times instead of 100. **VERIFIED WORKING**: `for(double d=100.0; d>0.0; d-=1.0)` loops 100 times ✓, `2.0*2.0 == 4.0` returns true ✓, `4.0 == 4.0` returns true ✓.

101. **mir_binop_result_type must treat F64 as 64-bit** (2026-09-09): The `mir_binop_result_type()` helper determines the C result type for binary operations. It must return NULL (meaning "no truncation needed") when either operand is `HD_TYPE_F64`. Without this check, F64 operands get treated as 32-bit integers, causing `AND 0xFFFFFFFF` + `SEXT32` truncation before double comparisons. Fix: add `lt->kind == HD_TYPE_F64 || rt->kind == HD_TYPE_F64` to the 64-bit check (alongside I64/U64). This is separate from the width-aware codegen `width` field — it's about preventing truncation, not about emitting different-width instructions.

102. **Double-to-int conversion on function return** (2026-09-09): When `main()` returns a double expression (e.g., `return fun(1.0)` where `fun` returns `double`), the return handler must emit `MIR_DTOI` to convert the double to an integer BEFORE the 32-bit truncation (AND + SEXT32). Without this, the raw IEEE 754 bits are masked with `0xFFFFFFFF`, producing wrong results (e.g., `0x4010000000000000` → `0x00000000` = 0 instead of 4). The check: if `fn_ret_type` is an integer type AND `mir_is_float_node(n->child)` is true, emit `MIR_DTOI`. **PITFALL**: `mir_is_float_node` does NOT detect function calls returning double — it checks `n->type->kind == HD_TYPE_F64` but function call nodes don't have their type set. Must also check if `n->child->kind == HD_AST_FUNC_CALL` and look up the callee's return type from `g->func_ast`.

103. **Unsigned int-to-double conversion (MIR_DITOF_U)** (2026-09-09): `cvtsi2sd` treats the source as a SIGNED integer. For unsigned values > LONG_MAX (e.g., `10223372036854775816ul`), this produces wrong results. Added `MIR_DITOF_U` op using the `(val>>1)*2 + (val&1)` algorithm: if sign bit is clear, use `cvtsi2sd` directly; otherwise split into `(val>>1)*2.0 + (val&1)`. The MIR builder emits `MIR_DITOF_U` when the source type is unsigned (`HD_TYPE_U32/U64/U8/U16`). **LIMITATION**: The split-and-multiply approach loses precision for values exactly between two representable doubles (rounding edge cases). Correct IEEE 754 rounding requires more sophisticated logic. **JIT ENCODING PITFALL**: `cvtsi2sd` opcode is `0F 2A` (NOT `0F 2C` which is `cvttsd2si`). Using the wrong opcode silently converts in the wrong direction. For `movq xmm, rax`: use `66 48 0F 6E C0` (operand-size, REX.W, opcode, ModRM). For `movq xmm1, rax`: use `66 48 0F 6E C8` (ModRM `C8` = reg=001/xmm1, rm=000/rax). **CRITICAL**: Do NOT use REX.B (0x49) for `movq xmm1, rax` — REX.B extends the RM field to r8 instead of rax. Use plain REX.W (0x48) with ModRM `C8`.

104. **Recursive function limitation — fixed memory addresses — SOLVED via interpreter frame restore + JIT→interp routing** (root-caused 2026-10-12; resolved same session): The JIT addresses ALL variables in one flat `prog.mem` array at FIXED byte offsets (`rbx` = mem base from `wubu_jit_mem_ptr`; LOAD/STORE compute `[rbx + byte_offset]`), and functions share the caller's stack frame — a callee entered via MIR_CALL does a BARE ret (no per-call rbp frame). So every recursive invocation reuses the SAME variable slots; the callee clobbers the caller's locals AND parameters (`fib(10)` = -80; `int x=n*100; f(n-1); return x` returns the inner frame's x; `int r=f(n-1); return n` returns 0). The INTERPRETER (`wubu_mir_interp.c`) handles this correctly via per-call `mem` snapshots (`mem_save`, `call_stack`) — so the bug is JIT-only. **RESOLVED (the frame-base rewrite was abandoned — do NOT attempt it):** the interpreter was made reentrant instead. Codegen sets `prog->globals_end = total_mem` right before the first function body (everything allocated in the top-level block is global; everything a func body allocates is frame memory). `op_call` snapshots the register file + the frame cells (byte addr >= globals_end/8 — NOT all memory, that was O(calls*mem) and fib(20) timed out); `op_ret` restores them; globals below the boundary persist across calls. `hd_run_prog` then detects recursion via a call-graph cycle DFS (`prog_has_recursion`) and routes recursive programs to `wubu_mir_interp` (the golden oracle, now reentrant) while non-recursive programs keep the JIT. Verified: fib(20)=6765, fact(5)=120, sum/gcd/mutual recursion, recursive double; wcc suite FAILs 377→27. Gates: make test 195/195, --core 247/247. KNOWN EDGE (rare): nested recursive call used as an argument (Ackermann `ack(m-1,ack(m,n-1))`) still miscomputes — the inner call's frame restore can clobber the outer frame before the outer call is set up.

### x86-64 JIT frame-emission pitfalls (from the frame-base attempt)

- **Double REX prefix**: opcodes that carry their own REX.W (`48 8B`, `48 01`, `48 B9` movabs) must NOT also call the `rex()` helper — that emits a second `48` and decodes as garbage. Call `rex()` only for short-form opcodes (`89`, `01`).
- **Never clobber call-arg registers** in any prologue/call-adjacent helper: args live in rdi/rsi/rdx, so frame push/pop must use only rax/rcx.
- **Stack alignment**: the shared-frame bare-ret model means you cannot add odd machine-stack pushes around a call without re-deriving the 16-byte alignment at the `call` site — prefer a global save array over the machine stack.

105. **Extern variable declaration handling** (2026-09-10, IMPLEMENTED): `extern int foo;` inside a function should refer to an existing variable with that name, not create a new one. Implementation: parser sets `is_extern=1` on `HD_AST_VAR_DECL` node; MIR generator checks `n->is_extern` BEFORE calling `mir_decl_var_unsigned`, searches existing vars from end (most recent first), and if found, reuses the existing address via `goto extern_done` (skipping allocation + init). **LIMITATION**: Searching from end finds the most recent local with that name, not the global — when a local shadows a global and `extern` is used to re-declare the global, the lookup incorrectly finds the local. Fixing this requires scope-aware lookup (track global vs local separately). The 3 tests fixed by this (`static_then_extern`, `switch_on_extern`, `switch_skip_extern_decl`) all have the existing variable as the most recent, so the simple approach works.

106. **cvtsi2sd vs cvttsd2si opcode confusion** (2026-09-09): Two different SSE2 conversion opcodes are easy to confuse:

107. **IDENT nodes have no type — always look up var table** (2026-09-09): `HD_AST_IDENT` nodes have `type = NULL` (set in parser line 588). When you need the type of a variable reference (for assignment conversion, return type detection, etc.), you MUST look it up from `g->vars[i].type` via `mir_find_var_type()`. Search from the end for correct shadowing. This also means function call nodes (`HD_AST_FUNC_CALL`) don't know their return type — look up `g->func_ast[fid]->type` to find the callee's return type.

108. **JIT forward jump position MUST be size_t, never uint8_t** (2026-09-09): When emitting forward jumps (JP, JMP, JZ, JNZ) in the JIT, the position variable for patching MUST be `size_t` (same type as `e.n`). Declaring it as `uint8_t` silently truncates positions >255 bytes, causing the rel32 offset to be written to the wrong address. This produces crashes that look like random memory corruption. **Symptom:** Code works for small functions (<255 bytes) but crashes for larger ones. **Fix:** Always use `size_t` for jump patch positions: `size_t jp_patch_pos = e.n;`

109. **NaN handling via JP jump after ucomisd** (2026-09-09): SSE2 `ucomisd` sets PF=1 (parity flag) when either operand is NaN. All ordered comparisons (lt/le/gt/ge/eq) return false for NaN; only `!=` returns true. Implementation: after `ucomisd`, emit `JP nan_case` (0F 8A rel32). At `nan_case`: emit `mov al, 1` for DNE or `mov al, 0` for all others. The ordered case falls through to normal `setcc`. **CRITICAL:** The JP jump target position MUST be `size_t` (see rule 108). Using `uint8_t` causes crashes on functions >255 bytes.

110. **Call-site argument type conversion** (2026-09-09): Function arguments must be converted to parameter types at the CALL SITE, not in the function body. After placing each argument in VR(a+1), look up `g->func_ast[fid]->param_types[a]` and emit `MIR_DTOI` (double→int) or `MIR_DITOF` (int→double) as needed. **Type inference for arguments:** IDENT nodes have `type=NULL`, integer literals have type set by parser, but expressions like `-6` (HD_AST_NEG) have `type=NULL`. Use this fallback chain: (1) `n->args[a]->type`, (2) `mir_find_var_type()` for IDENT, (3) `mir_is_float_node()` ? F64 : I32. Without proper type inference, `-6` passed to a `double` parameter won't get converted.

111. **VAR_DECL initializer needs float/int conversion** (2026-09-09): Variable declaration initializers (`double d = i`) need the same float/int conversion as assignments. The `HD_AST_VAR_DECL` handler at line ~1164 emits `mir_gen_expr(g, n->init)` then stores directly without conversion. Add the same conversion logic: check `n->type` (var type) vs `n->init->type` (or var table lookup for IDENT), emit `MIR_DTOI` or `MIR_DITOF` as needed. **PITFALL:** `n->init->type` is NULL for IDENT nodes — must use `mir_find_var_type()`.

112. **ModRM encoding for XMM registers** (2026-09-09): The ModRM byte encodes both the destination register and source register. For `movq xmmN, rax`: `C0` = xmm0+rax (reg=000, rm=000), `C8` = xmm1+rax (reg=001, rm=000), `D0` = xmm2+rax (reg=010, rm=000). Getting this wrong silently moves data between wrong registers. For `ucomisd xmm0, xmm1`: use `C1` (reg=001/xmm1, rm=000/xmm0 — note the operand order). **VERIFIED:** `66 48 0F 6E C0` = movq xmm0, rax ✓; `66 48 0F 6E C8` = movq xmm1, rax ✓; `66 0F 2E C1` = ucomisd xmm0, xmm1 ✓.

108. **Call-site argument type conversion** (2026-09-09): Function arguments must be converted to parameter types at the CALL SITE, not in the function body. After placing each argument in VR(a+1), look up `g->func_ast[fid]->param_types[a]` and emit `MIR_DTOI` (double→int) or `MIR_DITOF` (int→double) as needed. The function body receives already-converted values.

109. **Assignment type conversion requires var table lookup for both sides** (2026-09-09): When `i = d` (int = double), the assignment handler must emit `MIR_DTOI` before storing. But both LHS (`i`) and RHS (`d`) are IDENT nodes with `type = NULL`. You must look up BOTH types from the var table: `mir_find_var_type(g, n->left->ident)` for LHS and `mir_find_var_type(g, n->right->ident)` for RHS. Without this, `i = d` stores raw IEEE 754 bits instead of the truncated integer value.
- `F2 0F 2A /r` = `cvtsi2sd xmm, r/m64` — signed integer TO double (used in MIR_DITOF)
- `F2 0F 2C /r` = `cvttsd2si r64, xmm` — double TO signed integer (used in MIR_DTOI)
Using `0F 2C` when you mean `0F 2A` (or vice versa) silently converts in the wrong direction, producing garbage results. When adding new float conversion code, double-check the opcode against the Intel manual.

113. **Gauntlet scoring is non-deterministic** (2026-09-09): Pass count varies by ±3-6 between runs due to timing-sensitive tests and fork-per-test runner. Never trust a single run as evidence of regression. Run 3+ times and compare medians. A score change of ≤2 is noise, not a real regression.

114. **Function call return type lookup pattern** (2026-09-09): Since `n` is `const` in `mir_gen_expr`, you CANNOT set `n->type` on function call nodes. Instead, look up the callee's return type at each use site: iterate `g->func_ast[]` matching `ident`, return `((HDASTNode*)g->func_ast[i])->type`. Needed for: VAR_DECL initializer conversion, assignment RHS conversion, call-site argument conversion.

116. **Incremental change testing discipline** (2026-09-09): When making multiple changes, test each individually (commit + 3x gauntlet) before combining. Bundling changes makes it impossible to isolate which caused a regression, and gauntlet noise (±3-6) masks small regressions.

117. **Truncated test filter** (2026-09-08): 35% of gauntlet tests are invalid extractions (truncated sources, missing code). Added `is_invalid_test()` to gauntlet_v3 that skips tests starting with `{`, missing `main`, or with brace mismatch. This gives an accurate pass rate on valid tests only. See `references/truncated-test-filter.md`.

118. **Byte-addressable memory — IMPLEMENTED** (2026-09-13 → 2026-09-14): Cell-based hybrid with `uint8_t *mem`. 1 cell (8 bytes) per array element regardless of type. String literals stored cell-by-cell (offset `i*8`). Pointer arithmetic/ADD/SUB/INC/DEC all scale by 8. Array-to-pointer decay in ADD scales by 8 (check `is_array` in var table). Char array init from string literal: copy cell-by-cell + zero remaining. Nested DOT offset accumulation fixed (walk chain from root IDENT, use `st->member_offsets[mi] * 8`). Score: 1,188 (baseline) → 1,190 (current). See `references/byte-addressable-memory-model.md`.

119. **Struct initializer type conversion** (2026-09-09): Brace initializer lists for structs (`struct pair2 r = {a*2, b*2}`) must convert each element to the member's declared type. Added `mir_gen_cast()` helper that handles int↔float conversion and integer truncation. Applied in the `HD_AST_BRACE_INIT` handler after `mir_gen_expr(g, elem)`. Without this, `int` expressions stored in `double` members produce garbage (raw integer bits interpreted as IEEE 754). See `references/implicit-type-conversion.md`.

120. **Stale binary trap — Makefile mechanism** (2026-09-09): The `gauntlet_v3` Makefile target ends with `rm -f gauntlet_runner`. Building `gauntlet_v3` DELETES `gauntlet_runner`. Always rebuild both: `make gauntlet_v3 && make gauntlet_runner` after source changes. A stale `gauntlet_runner` produces output from OLD code, making you think your fix didn't work — this has cost multiple sessions hours of debugging.

121. **MIR_DITOF_U exact algorithm — high/low 32-bit split** (2026-09-09, updated 2026-09-10): The unsigned int-to-double JIT handler for `MIR_DITOF_U` uses an EXACT high/low 32-bit split algorithm: `(double)(val>>32) * 2^32 + (double)(uint32_t)val`. This is exact for ALL 64-bit unsigned values (no rounding loss). The old `(val>>1)*2 + (val&1)` algorithm lost precision for values near midpoints between representable doubles. **JIT encoding**: `shr rcx, 32` → `mov edx, ecx` → `cvtsi2sd xmm0, rdx` → load `0x41F0000000000000` (2^32) into xmm2 → `mulsd xmm0, xmm2` → `mov ecx, eax` → `mov edx, ecx` → `cvtsi2sd xmm1, rdx` → `addsd xmm0, xmm1`. **CRITICAL PITFALL**: Use `mov edx, ecx` (NOT `xor edx, edx`) for the low part — `xor edx, edx` zeros the register before `cvtsi2sd`, losing the low 32 bits. The `mov edx, ecx` must come AFTER `mov ecx, eax` loads the low bits. **addsd opcode**: `66 0F 58 C1` (NOT `subsd` `66 0F 5C C1`).

122. **I64/U64 missing from type conversion checks** (2026-09-09): The float↔int conversion handlers in VAR_DECL, assignment, return, and compound assignment only checked for `HD_TYPE_I8/U8/I16/U16/I32/U32` — missing `HD_TYPE_I64` and `HD_TYPE_U64`. This caused `long l = 4611686018427389440.;` to store raw IEEE 754 bits truncated to 32 bits instead of properly converting double→long. When adding a type conversion check, ALWAYS include all 8 integer types: I8/U8/I16/U16/I32/U32/I64/U64.

123. **Return handler int→double conversion** (2026-09-09): When a function returns `double` but the return expression is an integer (e.g., `return 18446744073709551586ul;`), the return handler must emit `MIR_DITOF` or `MIR_DITOF_U` to convert the integer to double. Without this, the raw integer bits are stored as the return value, and the caller interprets them as IEEE 754 double bits — producing garbage. Check `g->fn_ret_type->kind == HD_TYPE_F64` and the child node type; use `MIR_DITOF_U` for unsigned sources.

124. **VAR_DECL unsigned→double uses MIR_DITOF_U** (2026-09-09): When initializing a double from an unsigned integer (`double d = 18446744073709551586ul;`), the VAR_DECL handler must use `MIR_DITOF_U` (not `MIR_DITOF`) for unsigned source types. `MIR_DITOF` uses `cvtsi2sd` which treats the source as signed — for values > LONG_MAX, the signed interpretation gives wrong results. Check `init_k` for unsigned types and select the correct MIR op.

125. **Ternary common type — IMPLEMENTED** (2026-09-11): The ternary operator now converts both branches to their common type. Float branches: convert integer branch via ditof/ditof_u per-branch. 32-bit integer branches with mixed signedness: zero-extend both with AND 0xFFFFFFFF. 64-bit branches: no conversion needed. The conversion happens per-branch inside the ternary handler, not at the merge point.

126. **Assignment to long from double needs DTOI** (2026-09-09): `long l = 4611686018427389440.;` requires double→long conversion (MIR_DTOI), not just storing raw IEEE 754 bits. The assignment handler's float→int conversion check must include `HD_TYPE_I64` and `HD_TYPE_U64`. Without this, the raw double bits are AND'd with 0xFFFFFFFF (32-bit mask), producing garbage like 2048 instead of 4611686018427389952. Same fix needed in VAR_DECL, return, and compound assignment handlers — any place that converts float to integer.

127. **Float-int promotion in binary operations** (2026-09-09): When a binary operation (ADD/SUB/MUL/DIV) has one float operand and one integer operand, the integer must be promoted to double BEFORE the operation. Without this, `e + 1.0` (int + double) adds the integer bits directly to the double bits, producing garbage. Added `mir_promote_to_float()` helper that safely promotes only clearly-integer nodes (INT_LIT, IDENT, NEG, ADD, SUB, MUL, DIV, etc.) without promoting ambiguous nodes (DEREF, ADDR, INDEX). Applied in all 4 binary operation handlers. **PITFALL**: Do NOT add promotion to comparison handlers — it broke sizeof and pointer tests (chapter 14, 17). Comparisons use a different code path that doesn't need promotion.

128. **Float increment/decrement** (2026-09-09): `d++` and `d--` on double variables must use `MIR_DADD`/`MIR_DSUB` with `1.0` (double bits), NOT integer ADD/SUB with `1`. Without this, `d++` on `double d = 0.75` adds integer 1 to the IEEE 754 bits, producing garbage. The POST_INC/POST_DEC and PRE_INC/PRE_DEC handlers must check `g->vars[i].is_float` and select float vs integer arithmetic accordingly.

129. **FUNC_CALL in mir_is_float_node** (2026-09-09): `mir_is_float_node()` must handle `HD_AST_FUNC_CALL` by looking up the callee's return type from `g->func_ast[]`. Without this, function calls returning double (e.g., `int_to_double(-100000)`) are not detected as float, causing `mir_promote_to_float()` to emit spurious `MIR_DITOF` on the already-double result — corrupting the value. Search `g->func_ast[]` matching `n->callee->ident`, return `fn->type->kind == HD_TYPE_F64`.

130. **VAR_DECL float initializer detection** (2026-09-09): When `init_type` is NULL (common for `HD_AST_NEG` of float literals like `-2e308`), the VAR_DECL handler defaults `init_k` to `HD_TYPE_I32`, causing spurious `MIR_DITOF` on already-float values. Fix: when `init_type` is NULL, use `mir_is_float_node(g, n->init)` to detect float expressions and set `init_k = HD_TYPE_F64`. This prevents `double d = -2e308` from being corrupted.

131. **Compound assignment float promotion** (2026-09-09): `d += 1000` (double += int) requires promoting the RHS to float before the operation. Added `mir_promote_to_float(g, rhs, n->right)` in the compound assignment handler when `is_float` is true. Without this, the integer 1000 is interpreted as IEEE 754 bits and added to the double, producing garbage.

132. **Stale binary trap — gauntlet_v3 deletes gauntlet_runner** (2026-09-09, reinforced 2026-09-11): The `gauntlet_v3` Makefile target ends with `rm -f gauntlet_runner`. Building `gauntlet_v3` DELETES the `gauntlet_runner` binary. **ALWAYS** force rebuild after source changes: `rm -f gauntlet_runner gauntlet_v3 && make gauntlet_v3 && make gauntlet_runner`. Verify with `--dump-asm` on a known test case before running the full gauntlet. A stale `gauntlet_runner` produces output from OLD code, making you think your fix didn't work. This single pitfall has cost multiple sessions dozens of hours of debugging.

133. **Comparison promotion pitfall** (2026-09-09): Adding `mir_promote_to_float()` to comparison handlers (EQ/NE/LT/LE/GT/GE) broke sizeof and pointer tests (chapters 14, 17). The comparison path uses `mir_binop_result_type()` for truncation which interacts badly with promotion. REVERTED. Only apply float promotion to binary arithmetic operations (ADD/SUB/MUL/DIV), not comparisons.

134. **Unsigned constant type determination** (2026-09-10): When determining the type of an unsigned integer constant in the parser, use the UNSIGNED value (`uint64_t uv = (uint64_t)v`) for range checks, NOT the signed value (`int64_t v`). For `9223372036854777850ul`, `v` overflows to negative, which would incorrectly pass `v <= 0xFFFFFFFF` and assign `U32` type. With `uv`, the check `uv <= 0xFFFFFFFF` correctly fails, assigning `U64`. This only affects the `unsigned` (non-long) case where the value exceeds `INT64_MAX`.

135. **MIR_DITOF_U exact algorithm** (2026-09-10): Replaced lossy `(val>>1)*2+(val&1)` with exact high/low 32-bit split: `(double)(val>>32)*2^32+(double)(uint32_t)val`. Fixes all unsigned→double edge cases. See `references/float-int-promotion.md`.

136. **Extern variable declaration** (2026-09-10): `extern int foo;` no longer creates a shadow variable. Parser sets `is_extern=1` on the AST node; MIR generator searches existing vars from end and reuses address. +3 tests (chapter 10: 7→4 failures). LIMITATION: can't re-declare a global when a local with the same name shadows it (scope-aware lookup needed).

137. **Float promotion in compound assignments** (2026-09-10): `d += 100` (double += int) promotes RHS to float before operation. Added `mir_promote_to_float(g, rhs, n->right)` in compound assignment handler when `is_float`.

138. **FUNC_CALL return type lookup for float detection** (2026-09-10): `mir_is_float_node` now handles `HD_AST_FUNC_CALL` by looking up callee's return type from `g->func_ast[]`. Prevents spurious `MIR_DITOF` on already-double function results. +1 test.

139. **Unsigned double-to-int conversion (MIR_DTOI_U)** (2026-09-10): For unsigned LHS + float RHS in compound assignments (e.g., `ul -= 1.5E19`), the result must be converted back to unsigned integer using `MIR_DTOI_U` instead of `MIR_DTOI`. `MIR_DTOI` uses `cvttsd2si` which gives wrong results for values > INT64_MAX. `MIR_DTOI_U` uses the same instruction but is semantically unsigned — for values < 2^63 the result is identical, but the op name documents intent and enables future split-algorithm optimization. Added to: wubu_mir.h, wubu_mir.c, wubu_mir_interp.c, wubu_mir_regalloc.c, wubu_isa_x86_64.c, holyd_mir_eval.c.

140. **Unsigned division/modulo (MIR_UDIV/MIR_UMOD)** (2026-09-10): `idiv` (signed) gives wrong results for unsigned operands > INT64_MAX (e.g., `18446744073709551605ul % 100` = -11 instead of 5). Added `MIR_UDIV` and `MIR_UMOD` ops using `xor rdx,rdx` + `div rcx` (unsigned division). The MIR builder emits unsigned ops when BOTH operands are unsigned (checked via `mir_is_unsigned_node()` which looks at AST type and var table). JIT encoding: `rex(&e,1,0,0,0); e8(&e,0x31); e8(&e,0xD2)` (xor rdx,rdx) then `rex(&e,1,0,0,0); e8(&e,0xF7); e8(&e,0xF1)` (div rcx). Added to all 6 MIR files + JIT + regalloc. +2 tests (ch12 unsigned arithmetic, ch17 sizeof with unsigned long).

141. **mir_promote_to_float must look up var table for IDENT** (2026-09-10): IDENT nodes have `type=NULL`, so `mir_promote_to_float` cannot determine signedness from `n->type`. Added fallback: for IDENT nodes, search `g->vars[]` from end and check `g->vars[i].type->kind` for unsigned types. Without this, `unsigned long ul = 18446744073709551586ul; ul -= 1.5E19` uses `MIR_DITOF` (signed) instead of `MIR_DITOF_U` (unsigned), giving wrong results for values > INT64_MAX. **ALSO**: For ternary branches, `mir_promote_to_float` must look up the branch's unsignedness from the var table when `type` is NULL — otherwise `flag ? 5.0 : unsigned_val` uses signed ditof on the unsigned branch.

142. **Struct array member size in cells** (2026-09-10): The struct member size formula `(total_bytes+7)/8` undercounts array members. For `int sub[2]`, total_bytes=8, `(8+7)/8=1` cell, but the array needs 2 cells (one per element). Fix: for array members, compute `array_size * ceil(element_size/8)` cells. Without this fix, `struct S { int v; int sub[2]; }` has size 2 cells instead of 3, causing `sub[1]` to overlap with the next variable. +3 tests (ch18 struct copy/return).

143. **sizeof(func()) return type lookup** (2026-09-10): `sizeof(foo())` requires looking up the function's return type. The function name is in `n->child->callee->ident` (NOT `n->child->ident` which is empty for FUNC_CALL nodes). Search `g->func_ast[]` matching the name, return `fn->type`. Added `mir_find_func()` and `mir_find_func_return_type()` helpers. Without this, `sizeof(foo())` defaults to 8 (pointer size) instead of the actual return type size.

144. **sizeof(assignment) uses LHS type** (2026-09-10): `sizeof(c = 10.0)` where `c` is `unsigned char` should return 1, not 8. Added `HD_AST_ASSIGN` case in sizeof handler: look up LHS variable type from var table. The assignment expression's result type is the type of the LHS per C standard.

145. **Compound assignment unsigned LHS + float RHS** (2026-09-10): `ul -= 1.5E19` (unsigned long -= double) requires: (1) promote LHS to float via `mir_promote_to_float` (which uses DITOF_U for unsigned), (2) perform DSUB, (3) convert result back to unsigned integer via MIR_DTOI_U. Without step 1, the unsigned long bits are interpreted as double bits. Without step 3, the double result is stored as-is (raw IEEE 754 bits). The compound assignment handler now checks `is_float` and promotes LHS + converts result back to integer type.

146. **Comparison common type via mir_common_cmp_type()** (2026-09-10): Per C usual arithmetic conversions, comparison operators (LT/LE/GT/GE) must determine signedness from the COMMON TYPE of both operands, not from individual operands. `unsigned int u; long l; u > l` — common type is `long` (signed), so use MIR_GT not MIR_UGT. Implemented `mir_common_cmp_type()` helper that returns the common type kind. For mixed 32/64-bit: if either is 64-bit, common type is the 64-bit type. For both 32-bit: if either is unsigned, use U32. **PITFALL**: This change alone doesn't fix all common-type failures — the ternary handler also needs updating to convert both branches to the common type. Without ternary support, `flag ? -30 : 10ul` still produces wrong results because the selected branch value isn't converted to the common type.

147. **Ternary common type — IMPLEMENTED** (2026-09-11): The ternary handler now converts both branches to the common type. For float: convert integer branch via ditof/ditof_u (per-branch, inside ternary handler). For 32-bit integer with mixed signedness: zero-extend both branches with AND 0xFFFFFFFF. For 64-bit: no conversion needed (cast/return handler uses ditof_u). The key insight is that the conversion must happen PER-BRANCH inside the ternary handler, not at the merge point, because the selected branch's value must already be in the common type.

148. **FUNC_CALL ident is in callee->ident, not ident** (2026-09-10): `HD_AST_FUNC_CALL` nodes store the function name in `n->callee->ident`, NOT `n->ident` (which is empty). When looking up function return types (for sizeof, type conversion, float detection), always use `n->callee->ident`. This affects `mir_find_func_return_type()`, `mir_is_float_node()`, and any other code that resolves function names from FUNC_CALL nodes.

149. **Ternary float conversion** (2026-09-10): When either branch of a ternary is float, the integer branch must be converted to float at runtime. Added `either_float` check in ternary handler: if either branch `mir_is_float_node()`, convert the other branch using `MIR_DITOF`/`MIR_DITOF_U` (unsigned detection via branch type or var table lookup). WITHOUT this, `flag ? 5.0 : 9223372036854777850ul` interprets the unsigned long bits as double, producing garbage. The conversion happens inside the ternary handler (per-branch) rather than at the cast/return site, because the ternary merge register holds the final value.

150. **mir_is_float_node ternary support** (2026-09-10): `mir_is_float_node()` must handle `HD_AST_TERNARY` by checking if EITHER branch is float. Without this, a ternary with one float branch is not detected as float, causing the return handler to skip float-to-int conversion (for `int x = flag ? 5.0 : 3`) or the cast handler to skip ditof. Check `n->then_branch && mir_is_float_node(g, n->then_branch)` and same for `else_branch`.

151. **Return handler ternary unsigned detection** (2026-09-10): When a function returns `double` and the return expression is a ternary with an unsigned branch, the return handler must use `MIR_DITOF_U` (not `MIR_DITOF`). Added check: if `n->child->kind == HD_AST_TERNARY`, check if either branch has unsigned type. Also added `mir_find_func()` and `mir_find_func_return_type()` helpers for looking up function return types from `g->func_ast[]` (function name is in `n->callee->ident`, NOT `n->ident`).

152. **Cast handler ternary unsigned detection** (2026-09-10): When casting a ternary to double `(double)(flag ? -30 : 10ul)`, the cast handler must use `MIR_DITOF_U` if either branch is unsigned. Added check: if `n->child->kind == HD_AST_TERNARY`, check both branches for unsigned types. Without this, `(double)(flag ? -30 : 10ul)` uses `cvtsi2sd` (signed) on the unsigned long value, producing wrong results for values > INT64_MAX.

153. **Parser ternary type annotation** (2026-09-10): The parser now sets the ternary node's `type` field to the common type of both branches (per C usual arithmetic conversions). For IDENT branches, `type` is looked up from the var table at MIR generation time (IDENT nodes have `type=NULL` at parse time). This enables downstream handlers (assignment, return, cast) to make correct signedness decisions. **LIMITATION**: IDENT branches have `type=NULL` in the parser, so the common type can only be set when both branches have explicit type annotations (literals, expressions). For `flag ? i : ui` where both are IDENT, the type is not set.

154. **Ternary zero-extension — IMPLEMENTED** (2026-09-11): Zero-extension with `AND 0xFFFFFFFF` works when applied PER-BRANCH in the ternary handler, only for 32-bit common types. The check `!then_is_64 && !else_is_64 && common_unsigned` ensures we don't corrupt 64-bit values. For `flag ? i : ui` (both 32-bit), both branches are zero-extended. For `flag ? -30 : 10ul` (mixed 32/64-bit), zero-extension is skipped and the cast/return handler uses ditof_u instead.

155. **Stale binary trap — gauntlet_v3 deletes gauntlet_runner** (2026-09-10): The `gauntlet_v3` Makefile target ends with `rm -f gauntlet_runner`. Building `gauntlet_v3` DELETES the `gauntlet_runner` binary. Always rebuild both after source changes: `rm -f gauntlet_runner gauntlet_v3 && make gauntlet_v3 && make gauntlet_runner`. A stale `gauntlet_runner` produces output from OLD code.

156. **Goto + static local pre-existing crash** (2026-09-10): `goto` jumping over a `static int x = 10;` declaration crashes in `--dump-asm` mode (not in gauntlet mode). This is a pre-existing bug, NOT caused by recent changes. The gauntlet path handles this correctly. When debugging, use the gauntlet runner (not `--dump-asm`) for goto tests.

163. **Ternary integer zero-extension** (2026-09-11): Mixed signed/unsigned 32-bit ternary branches zero-extended with AND 0xFFFFFFFF. Only applies when both branches are 32-bit (not 64-bit). +2 tests (ch12, ch16 common_type).

164. **sizeof INDEX/DEREF/binary/unary** (2026-09-11): sizeof(arr[i]) and sizeof(*arr) return element size (4 for int) not cell size (8). sizeof(binary_op) uses mir_binop_result_type; sizeof(unary_op) uses operand type. +2 tests (gcc_torture, extern_gcc array length).

157. **Ternary integer common type zero-extension** (2026-09-11): When a ternary has mixed signed/unsigned 32-bit integer branches, BOTH branches must be zero-extended with `AND 0xFFFFFFFF` in the ternary handler. This ensures the common type (`unsigned int`) is correctly applied. The ternary handler checks `mir_is_unsigned_node()` for each branch (which looks up the var table for IDENT nodes) and applies zero-extension when `common_unsigned = then_unsigned || else_unsigned`. **CRITICAL**: Only apply zero-extension when BOTH branches are 32-bit (not 64-bit). For `flag ? -30 : 10ul`, the `10ul` is 64-bit so zero-extension is NOT applied — the cast handler uses `ditof_u` instead. For `flag ? i : ui` (both 32-bit), zero-extension IS applied. The distinction is checked by looking at `n->then_branch->type->kind` and `n->else_branch->type->kind` for I64/U64.

158. **sizeof for INDEX and DEREF expressions** (2026-09-11): `sizeof(arr[i])` and `sizeof(*arr)` must return the element type size (4 bytes for int), NOT the cell size (8 bytes). Added `HD_AST_INDEX` case: traverse INDEX chain to root IDENT, look up `is_array` flag, return 4 for int arrays. Added `HD_AST_DEREF` case: look up the dereferenced variable's type from var table. Without these, `sizeof(a)/sizeof(a[0])` gives wrong results (32/8=4 instead of 32/4=8), breaking array length computations.

159. **Cast handler ternary unsigned detection via mir_is_unsigned_node** (2026-09-11): When casting a ternary to double `(double)(flag ? -30 : 10ul)`, the cast handler must use `MIR_DITOF_U` if either branch is unsigned. Uses `mir_is_unsigned_node(g, n->child->then_branch) || mir_is_unsigned_node(g, n->child->else_branch)` which handles IDENT branches via var table lookup. Without this, the signed `cvtsi2sd` is used on unsigned values > INT64_MAX, producing wrong results.

160. **Return handler ternary unsigned detection** (2026-09-11): When a function returns `double` and the return expression is a ternary with an unsigned branch, the return handler must use `MIR_DITOF_U`. Added check: if `n->child->kind == HD_AST_TERNARY`, check both branches via `mir_is_unsigned_node()`. Without this, `double foo() { return flag ? 5.0 : 9223372036854777850ul; }` uses signed ditof on the unsigned branch.

161. **mir_is_unsigned_node() helper** (2026-09-11): Checks if an AST node evaluates to an unsigned type. First checks `n->type` for U8/U16/U32/U64. For IDENT nodes (type=NULL), looks up `g->vars[i].type` from var table (search from end for shadowing). Used by: ternary handler, cast handler, return handler, division handler. This is the canonical way to determine unsignedness of arbitrary expressions at MIR generation time.

162. **Ternary zero-extension only for 32-bit common type** (2026-09-11): Zero-extension with `AND 0xFFFFFFFF` is ONLY correct when the common type is 32-bit (`unsigned int`). For 64-bit common types (`unsigned long`), zero-extension would corrupt the value. The check: `!then_is_64 && !else_is_64 && common_unsigned` where `then_is_64` checks if the branch type is I64/U64. For mixed 32/64-bit ternaries (e.g., `flag ? -30 : 10ul`), the common type is 64-bit so zero-extension is skipped — the cast/return handler uses `ditof_u` instead.

165. **Switch+continue in loop** (2026-09-12): When a `switch` is nested inside a loop, `continue` inside the switch must jump to the enclosing loop's continue label, NOT the switch's break label. The switch pushes a pseudo-loop level (`g->n_loops++`) for `break` handling, which shifts `g->loop_top[g->n_loops - 1]` to the wrong level. Fix: also save and restore `g->loop_top[g->n_loops]` when pushing/popping the switch level, copying the outer loop's `loop_top` so `continue` finds the correct label.

166. **sizeof(ternary)** (2026-09-12): `sizeof(cond ? a : b)` returns the common type size of the two branches. For integer literals, this is 4 (int). If either branch is `long`, it's 8. Default to 4 unless either branch has type I64/U64.

167. **Forward declaration function call resolution — DO NOT treat all forward decls as external** (2026-09-14 → updated 2026-09-16): When `mir_collect_funcs` finds a function with no body (forward declaration), treating it as an external call (func_id=0xFFFF) breaks tests where the function IS defined later in the same file. The search-from-end approach correctly finds the definition first (it appears later in the func table). Only functions with NO definition anywhere should be treated as external. Reverted: this change cost -17 tests (1,252 → 1,234). **Gauntlet-only regression pattern:** The 5 broken tests (`wcc_chapter_18_valid_no_structure_parameters_*`) passed individually via `--dump-asm` but failed in full gauntlet runs. This is a deterministic interaction effect from parallel workers sharing global state (function table ordering, memory layout), NOT a flaky test. Always verify changes with the FULL gauntlet, not just individual tests.

168. **sizeof string literal — array length including null terminator** (2026-09-16): `sizeof "Hello, World!"` must return 14 (13 chars + null terminator), NOT 8 (pointer size). The sizeof handler in `holyd_mir_eval.c` had no case for `HD_AST_STRING_LIT`, so it fell through to the default `size = 8`. Added explicit case: `size = strlen(n->child->str_val) + 1`. Empty string `""` returns 1 (null terminator only). This fixed `wcc_chapter_17_valid_sizeof_sizeof_array`.

169. **EVERY var-table lookup must search from the END (most recent declaration wins)** (2026-10-14): The fn-local-shadows-global bug class. `mir_find_var_addr`, `mir_index_stride`, `char_elem` all search from the end (fixed 2026-10-11/12), but `mir_var_is_array` still forward-searched. A fn-local **array** shadowing a same-name global **scalar** then read garbage: `mir_var_is_array` found the global scalar (`is_array=0`), so `mir_address_of` fell through to `mir_load(global)` and used the global's VALUE (e.g. 5) as the base pointer — `x[2]` read memory at byte offset 5+16. Repro: `int t(){int x[4]={1,2,3,4};return x[2];} int x=5;` → 0 (want 3). **RULE: when adding or auditing any `for (i...) if (strcmp(g->vars[i].name, ...))` lookup, default to `i = g->n_vars - 1; i >= 0; i--`.** Forward search is correct ONLY where you intentionally want the oldest declaration. Audit the whole family (is_array / is_struct / is_unsigned / find_var_type / struct_name) together — they are fixed as a set or the shadowing contract is broken.

170. **Sub-array decay: a[i] on a 2-D array returns an ADDRESS, not a loaded value** (2026-10-14): `int a[M][N]` → `a[i]` is itself an ARRAY, so as a value it decays to `&a[i][0]`. The INDEX handler in `mir_gen_expr` only decayed for `is_ptr_array` bases (`int (*p)[N]`); a plain 2-D array's `a[i]` fell through to `wubu_mir_load` and used the cell CONTENTS as the base pointer — `char *w = a[0]; strcmp(w, ...)` crashed reading a garbage address. Fix: after computing `addr`, if the base IDENT's var-table element type is `HD_TYPE_ARRAY` (base->base->kind == ARRAY), `return addr` (decay). Repro: `int a[3][3]={{1,2,3},{4,5,6},{7,8,9}}; int*w=a[0]; return w[0];` → 0 (want 1).

171. **Pointer-VARIABLE arg to an external (dlsym) call must be MIR_TO_PTR'd** (2026-10-14): In the FUNC_CALL arg loop, `arg_is_addr` is set for STRING_LIT, ARRAY/PTR AST types, and array IDENTs — but a **pointer variable** `char *w` has a NULL AST type and is not an array, so `arg_is_addr` stayed 0, `MIR_TO_PTR` was skipped, and the raw byte offset (e.g. 8) was passed as rdi → `strcmp(w, ...)` / `strlen(w)` dereferenced address 8 → deterministic segfault. Direct array/string args worked (they set arg_is_addr). Fix: when the arg is an IDENT, also search the var table (from end) for a `HD_TYPE_PTR` type and set arg_is_addr. Repro: `char row[4]="yes"; char*w=row; return strcmp(w,"yes");` crashed; after fix returns 0. **Rule: any external-call argument that is a pointer value (not just a literal/array) needs the offset→pointer conversion — check the var table for PTR-typed IDENTs, since IDENT nodes carry no type.**

172. **2-D char arrays are CELL-packed (row stride = cells*8), NOT byte-contiguous** (2026-10-14, reconfirmed): `char nested[3][3]={"yes","no","ok"}` stores one char per CELL (stride 8); `&nested[1][0]-&nested[0][0]` = 24 (3 cells), not 3 bytes. So `(char*)nested` read as a C string stops at the zero-filled tail of row 0 ("yes\0") and never sees row 1 — `strcmp((char*)nested, "yesno")` returns nonzero, not 0. This is the known architectural cell-vs-byte limitation for multi-dim char arrays (see byte-addressable-memory reference); it is NOT the sub-array-decay or pointer-arg bug. Do not "fix" the cell layout to chase the wcc null-bytes test without a deliberate byte-packing migration — that is a separate, larger change.

## References

- `references/chapter16-char-string-and-ptr-sub-wave.md` — HolyD frontend correctness wave, rules R169–R185: end-searching var-table lookups, sub-array decay, pointer-var external-call TO_PTR, 2-D char cell-packing, char-array store8/load8 (assign, compound-assign, inc/dec, struct-member init), string-literal byte scale, main() param zeroing, chained pointer subtraction, switch integer promotion, call-site arg conversion (param-count gate), struct-member type resolution + compound-assign float detection, unsigned div/mod (either-operand rule), struct copy from lvalue RHS, plus a frontend-miscompile debugging recipe. (Rules from this wave live here; SKILL.md numbered list is at its size ceiling.)
- `references/holyd-frontend-parsing-lessons.md` — extern/func-ptr/const-var parsing, designated array-init byte-offset scaling, `_Static_assert` enforcement + parser error-swallowing (fatal_error flag), stale-binary-after-`make <obj>` trap
- `references/statement-expression-and-atomic-implementation.md` — Details on implementing `({...})` statement expressions and `_Atomic` type qualifier parsing
- `references/dlsym-libc-calls.md` — dlsym-based libc calls in x86-64 JIT, register encoding pitfall, calling convention
- `references/multi-threaded-gauntlet-runner.md` — gauntlet_v3 pthread-based parallel test runner
- `references/mir-memory-model-and-pointers.md` — MIR memory layout, MIR_TO_PTR instruction, char type limitation, thread safety
- `references/dmake-depot-system.md` — DMake gauntlet depot build system, test acquisition rules, upstream sources
- `references/implicit-type-conversion.md` — HolyD narrowing conversion on assignment, truncation patterns, optimizer guard
- `references/static-local-variables.md` — Static local variable implementation, guard-based init-once pattern
- `references/float-literal-parsing.md` — Float literal forms: leading dot (.5), integer exponent (1E0), suffixes
- `references/truncated-test-filter.md` — 35% of gauntlet tests are invalid extractions; `is_invalid_test()` filter implementation and impact
- `references/x86-64-jit-encoding-pitfalls.md` — x86-64 encoding bugs: uint8_t jump truncation, ModRM XMM encoding, REX ordering, NaN handling, opcode confusion
- `references/float-int-promotion.md` — Float-int mixed-type operations: promotion rules, mir_promote_to_float() helper, pitfalls (don't promote comparisons, don't promote DEREF/ADDR/INDEX)
- `references/unsigned-arithmetic.md` — Unsigned division/modulo (MIR_UDIV/UMOD), unsigned double-to-int (MIR_DTOI_U), struct array member sizing, sizeof with function calls and assignments
- `references/common-type-conversions.md` — C usual arithmetic conversions for comparisons and ternary expressions, mir_common_cmp_type() helper, pitfalls of ternary branch truncation
- `references/gauntlet-scoring-and-architecture-ceiling.md` — Gauntlet counts test-target pairs (not tests), non-runnable targets, sizeof(double) return bug, architectural ceiling analysis, diminishing returns signal
- `references/byte-addressable-memory-model.md` — Byte-addressable memory model (uint8_t* mem), pitfalls (16-byte alignment, static local brace init, array stride), remaining work