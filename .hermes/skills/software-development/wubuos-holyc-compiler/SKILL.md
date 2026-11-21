---
name: wubuos-holyc-compiler
description: Debug and fix the WuBuOS "My Seed" HolyC compiler (lexer → parser → JIT codegen → runtime) in src/compiler. Covers the empirical workflow for hangs, JIT crashes, and wrong-result bugs in hc_eval, the recurring structural gotchas (token-name mismatch, missing stack frame, scope persistence, unpatched global relocations, the lexer pos-vs-token trap), the partial-ABI discipline (gate the new path so the legacy path is consistent on the bypass), and the kernel-critical C11 gap-closing pattern via the selfhost battery (sizeof, switch, goto, multi-dim arrays, array decay, nested pointer access, ≤8B struct-by-value return).
category: software-development
---

# WuBuOS HolyC Compiler — Debug & Fix Playbook

The compiler lives in `src/compiler/`:
- `holyc_lexer.c` — tokenizer. Emits tokens; `hc_lex_init` primes the first token.
- `holyc_parse.c` — recursive-descent parser. Entry points: `hc_parse_expr`, `hc_parse_stmt`, `hc_parse_block`, `hc_parse_compilation_unit`. Helpers `peek/advance/match/expect`.
- `holyc_codegen*.c` — expression/stmt/api codegen to x86-64 bytes into `HCGen.code`.
- `holyc_codegen_emit.c` — low-level emitters (`emit_byte`, `emit_prologue`, `emit_epilogue`, instruction patterns). `JIT_CALL(exec)` runs the buffer.
- `holyc_codegen_api.c` — `hc_eval` / `hc_compile` / `hc_compile_func` public API.
- `holyc_types.h` — token enum (`HCTokenType`), AST kinds (`HCASTKind`), `HCGen` struct.

`hc_eval(source)` is the test harness entry: parses (expr first, else wraps in a block), emits prologue, generates, emits epilogue, `JIT_CALL`s the buffer, returns `rax`.

## Empirical Triaging Workflow (DO THIS BEFORE EDITING)

Never trust a handoff's subsystem label. Localize the bug to lexer → parser → codegen → runtime:

1. **Lexer check** — compile a tiny probe that calls `hc_lex_init` + loops `hc_lex_next`, printing `tok.type`/`tok.text`. Confirms tokenization (e.g. `++` → token 65).
2. **Parser hang vs. codegen crash** — run the failing source under `hc_eval` with `alarm(N)` in a small C probe; if it times out, it's a parser/allocator loop. Get a GDB backtrace: `gdb -batch -ex run -ex bt` with `handle SIGALRM stop` and an `alarm()` in the probe. An infinite loop shows the spinning frame (e.g. `parse_block`→`parse_stmt` allocating `EXPR_STMT` forever = parser didn't advance).
3. **JIT crash** (segfault at `JIT_CALL`) — temporarily dump `gen.code` bytes (hex) right before `JIT_CALL` in `hc_eval`, decode by hand (push rbp / mov rax,imm64 / mov [rbp-off],rax / inc / ret). Garbage constants across tests = missing stack frame; writes to `rip+0` = unpatched global relocation.
4. **Parser bisect** — wrap candidate sub-expressions (`{ ++x; }`, `{ I64 x=5; }`, `{ I64 x=5; x; }`, `{ I64 x=5; x++; }`) each in a `hc_parse_stmt` probe with `alarm()` to find which one hangs.

Reference recipe for building a standalone probe: see `references/holyc-debug-probe.md`.

## Structural Gotchas (recurring root causes)

- **Lexer↔parser token-name mismatch.** If the lexer emits one token constant for an operator but the parser checks a *different* constant name, the operator is silently never recognized. Symptom: parser infinite-loop on that operator (errors without consuming → `expect(SEMI)` fails without advancing → `parse_block` spins). Fix: make the lexer emit the name the parser already uses. (2026-07-07: `HC_TOK_INC`/`HC_TOK_DEC` → `HC_TOK_PLUS_PLUS`/`HC_TOK_MINUS_MINUS`.)
- **`hc_scan_number` must detect a decimal point.** If the number scanner only reads digits (no `.` branch), `3.14` lexes as `HC_TOK_INT` (value 3) and the trailing `.14` becomes a stray `DOT` token → parse error / wrong cast. Fix: in the digit loop, when `c=='.'` and not hex/bin, set `is_float=true`, consume the dot + trailing digits, `strtod()` into `tok.float_val`, emit `HC_TOK_FLOAT`. (2026-07-07: `(I64)3.14` returned 0 → fixed.)
- **`hc_scan_string` double-consume of the opening quote.** `hc_lex_next` already does `c = hc_advance(lex)` to consume the first char (the `"`/`'`) and dispatches to `hc_scan_string`. The scanner must NOT `hc_advance` again — reading the quote a second time swallows the first *content* char and, worse, makes `quote` wrong so it returns `HC_TOK_CHAR` instead of `HC_TOK_STRING` (the test "string literal (got 3)" = `HC_TOK_CHAR` enum value). Fix: set `lex->tok.text[0] = c` right after the outer advance in `hc_lex_next`, and in the scanner capture the quote from `lex->tok.text[0]` (do NOT re-advance). (2026-07-07: fixed.)
- **Missing stack frame.** A prologue that is only `push rbp; mov rbp, rsp` (no `sub rsp, N`) leaves locals at `[rbp-8]` in unowned stack space → clobbered → every local-var eval returns the same garbage constant. Fix: reserve a frame (`sub rsp, 256`) in `emit_prologue` and restore it in `emit_epilogue` with `leave; ret` (0xC9 0xC3).
- **Global variable address VR collides with argument registers (2026-08-30).** `wubu_mir_alloc` returned a low VR (instruction index) for variable addresses. The first global got VR_1, which is ALSO the first argument register. When a 1-param function accessed the global, the argument overwrote the address → wrong memory access. **Fix: use `mir_new_vr()` (high VR ≥65536) for addresses, store the actual memory address via `wubu_mir_const_to`.** Same pattern as function parameters already use. Symptom: interpreter works (flat memory model), JIT crashes (register model) or returns wrong value.
- **Interpreter memory save/restore on function calls undoes global modifications (2026-08-30).** The interpreter's CALL handler saved the entire `mem` array; RET restored it. This discarded any changes the callee made to globals. **Fix: remove `memcpy(mem, f->mem_save, ...)` from `op_ret`** — only restore the VR file. Globals and locals use disjoint addresses (`wubu_mir_alloc`), so changes persist correctly without save/restore. Symptom: `w++` inside a function has no effect after the function returns; `mem[global_addr]` unchanged post-call.
- **Register allocator must extend live ranges across CALL instructions (2026-08-30).** Same pattern as the loop back-edge fix (Step 1b): for each CALL, find VRs defined before and used after, extend their `last_use` past the call. Without this, the allocator assigns caller-saved registers to VRs that must survive function calls (e.g., global variable addresses). **Symptom: JIT returns wrong value or crashes when a global is accessed after a function call.** Implementation: add Step 1c after the existing Step 1b in `wubu_mir_alloc_regs`.
- **x86-64 JIT must save/restore caller-saved registers around CALL (2026-08-30).** The JIT's register pool includes caller-saved registers (r10, r11, r8, r9, rdx). When a CALL is emitted, these are clobbered by the callee. **Fix: emit push r10,r11,r8,r9,rdx before CALL and pop in same order after.** Stack layout: pushes go below the return address (call pushes it), so after `ret` the stack top is the first push — pop in same order as push. Symptom: JIT crashes (SIGSEGV) or returns wrong value after function calls; interpreter works fine.
- **Parameter allocation must initialize slot_addr with actual memory address (2026-08-30).** The old parameter allocation created `slot_addr` as a high VR but never initialized it with the actual memory address. `base` was set to the VR ID of `slot_addr` (not the address value), so `mem[base]` accessed the wrong location. **Fix: use `mir_new_vr()` + `wubu_mir_const_to(addr, mem_addr)` pattern** (same as global/local var allocation). Allocate memory from `prog->total_mem`, store the actual address in the VR. Symptom: JIT SIGSEGV when a function with parameters is called; parameters read/write wrong memory.
- **JIT segfault even with correct emitted bytes — MISSING `-DWUBU_HOSTED` on the test link line (2026-08-16, systemic).** The hardest-to-diagnose JIT crash class: `gen.code` is byte-perfect (`push rbp; mov rax,42; leave; ret`), `jit_alloc_exec` returns a valid pointer, `mprotect`/memfd mappings look right in gdb, yet `JIT_CALL(exec)` SIGSEGVs on the *very first instruction* with `rip` inside the JIT page. Root cause is almost always **NOT codegen** — it's that the translation unit compiled `jit.c` WITHOUT `-DWUBU_HOSTED`, so the `#else` (self-hosted) branch is live: `jit_alloc_exec` returns a plain `malloc`'d buffer (RW, never executable) and `jit_lock_exec` is a no-op (`return ptr`). The buffer holds correct bytes but the page is not executable → execute-disable SIGSEGV. Check `mk/tests.mk` recipes: every test target that links `$(JIT_SRCS)` and calls `hc_eval`/`JIT_CALL` MUST have `-DWUBU_HOSTED -include wubu_gnu_compat.h -I$(RT)` — `test_holyc`, `test_battery`, `test_hedge` historically MISSING it (2026-08-16 fixed them). `holyc` and `test_holyd` had it; the gap targets didn't. **Triaging fingerprint (read in order):** (a) dump `gen.code` hex before `JIT_CALL` — if bytes are correct, skip codegen; (b) check the compile line for `-DWUBU_HOSTED` — missing = the buffer is RW heap, guaranteed crash; (c) if `WUBU_HOSTED` IS set, inspect `info proc mappings` under gdb — a `memfd:wubu_jit (deleted)` region must be `r-x` (RX); if only an `rwxp [heap]` or `rw-p` alias exists, the memfd `mmap(RX)` failed and `jit_lock_exec` returned a non-executable alias. See `references/jit-memory-backend-gotchas.md`.
- **Scope persistence across `hc_eval` calls (double-free + stale offsets).** `hc_gen_init` preserves `gen->symbols`, `functions`, AND `gen->data` (a malloc'd buffer) for REPL persistence; `hc_eval` frees `gen.data` at the end. If you reset only `symbols`/`n_functions` but leave `data` as the restored (already-freed) pointer, the next `hc_eval` frees it again → `free(): double free`. Also, without resetting `symbols`, `stack_size` accumulates across calls and later vars' offsets overflow the 256-byte frame → garbage. Fix: in `hc_eval`, after `hc_gen_init`, reset `memset(&gen.symbols,0,sizeof(gen.symbols)); gen.n_functions=0; gen.n_global_patches=0; gen.data=NULL; gen.data_size=0; gen.data_cap=0;` so each eval allocates its own data and frees NULL safely. (2026-07-07: `free(): double free` on `struct A { I64 x; }` test.)
- **Module-level vs local var discriminator — `has_prologue` is the WRONG signal (2026-07-07 fix).** `gen_stmt` VAR_DECL must route a declaration to either a **global** (data-section; persists across evals → required for REPL/holyd state) or a **local** (stack). The old signal `is_module_level = (code_size==0 || n_locals==0) && !gen->has_prologue` is **incorrect and reintroduces a real bug**: `wubu_holyd_eval` calls `emit_prologue()` *before* `gen_stmt()`, so `has_prologue` is already `true` at module level. Every top-level `I64 x = 123;` then gets misclassified as a stack local (`mov [rbp-8], rax`) instead of a data-section global. On the next eval the symbol still resolves to `[rbp-8]` — a fresh, uninitialized frame — so `x+10` returns garbage (`136637487570954` instead of `133`); `test_holyd` "persistent variable across evals" fails. **Correct fix: add `bool in_function` to `struct HCGen` (holyc_types.h), set it true just before and false just after emitting the `FUNC_DECL` body, and use `is_module_level = !gen->in_function`.** This keeps module-level vars as true globals (so persistence works) and only stack-allocates inside function bodies. The global-patch math in `wubu_holyd_eval` (`disp32 = code_size + global_offset - patch_pos - 4`) is correct — the bug was misclassification, never the relocation.
- **Global relocations ARE patched in the holyd eval path.** `VAR_DECL` global path records `global_patches[]`; `wubu_holyd_eval` applies them, so module-level globals work and persist across evals. The bug class is *misrouting to the stack path via a wrong `is_module_level` test*, NOT the global path itself. When you see a wrong-result bug after a top-level var decl, check `is_module_level`/`in_function` routing first.
- **Global-LOAD off-by-one (`-off` vs `-off-1`) — REAL wrong-result bug (2026-08-19, `test_holyd` "persistent variable" was still failing after the persistence/data fixes).** Symbol table stores a module-level global's location as `stack_offset = -(global_offset + 1)` (see VAR_DECL in `holyc_codegen_stmt.c`). To recover the data-section offset you MUST compute `global_offset = -off - 1`, NOT `-off`. The `emit_lvalue_addr` / `emit_base_addr` paths already do this correctly, but the **inline IDENT-load branch** in `holyc_codegen_expr.c` (the `gen_expr` `HC_AST_IDENT` case, ~line 516) used `data_offset = -off`. For `x` (global_offset 0 → symbol stack_offset -1) it then fetched `data[1]` instead of `data[0]` → returned 0. **Symptom that distinguishes it from a persistence bug:** the STORE works (`x=123` is written and survives across evals — `data[0]==123`), but `x+10` reads `x` as 0. If you see that exact pattern, fix the load's offset formula (`int32_t global_off = -off - 1;`) and use it for both the prefetch and `global_patches[].global_offset`. The `-DWUBU_HOSTED` on the test link line and the keep-data-section rule are still required for the store/persistence half; this is the load half.
- **`jit_lock_exec` makes the data section RX → SIGSEGV on global stores (2026-07-07 fix).** `hc_eval` (holyc_codegen_api.c) called `jit_lock_exec(exec, total)` which `mprotect`s the whole code+DATA page to `PROT_READ|PROT_EXEC`. But a module-level global (`I64 x = 5`) stores into the data section *at runtime* via `mov [rip+disp], rax`. Writing to an RX page → SIGSEGV. `wubu_holyd_eval` never calls `jit_lock_exec` (keeps the RWX page from `jit_alloc_exec`), which is why holyd globals worked but standalone `hc_eval` crashed on the first block-with-var-decl (`{ I64 x=5; x; }`). **Fix: in `hc_eval`, only call `jit_lock_exec` when `gen.data_size == 0` (pure-code buffer, no writable globals); when a data section exists, leave the page RWX so runtime stores succeed.** Symptom is a SIGSEGV at the store instruction (`mov %rax,0xN(%rip)`) with `rax` already holding the correct value — confirm with `gdb -batch -ex run -ex "x/12i \$pc-10"`; the faulting PC is inside the JIT buffer at the global-store op. (`jit_alloc_exec` already `mmap`s RWX, so NOT locking is safe for the test JIT.)
- **Global var access (PRE/POST `++`/`--` and `&x`) must emit RIP-relative load/store/lea — NOT `[rbp-off]` (2026-07-07 fix).** A module-level `VAR_DECL` goes to the data section (`off <= 0` ⇒ `global_offset = -off`). The four Inc/Dec cases (`HC_AST_PRE_INC/PRE_DEC/POST_INC/POST_DEC`) and the `&x` (`HC_AST_ADDR`) case in `holyc_codegen_expr.c` only emitted stack-local `mov rax,[rbp-off]` / `lea rax,[rbp-off]` — so a top-level `++x` built `mov [rbp - (negative)]` = a bogus high stack slot → crash/corruption. **Fix: dispatch on `off <= 0`: for globals call the new `emit_global_load_rax(gen, go)` / `emit_global_store_rax(gen, go)` (and for `&x` a RIP-relative `lea rax,[rip+disp32]`), which record a `global_patches[]` entry (`patch_pos = code_size+3`, the disp32 start). Stack locals keep the `[rbp-off]` path.** The shared patch formula `disp32 = code_size + global_offset - patch_pos - 4` (applied in BOTH `hc_eval` and `wubu_holyd_eval`) covers load, store, and lea — all are 7-byte `48 XX 05 disp32` instructions, so RIP-after = `patch_pos+4` and the `-4` cancels the 7-byte length. `hc_eval` MUST also apply the patch loop (holyd already did; standalone `hc_eval` previously did not, which is why globals crashed there even before the lock issue).

- **Unregistered extern in `hc_eval` → `call 0` → SIGSEGV (2026-07-22 fix).** `holyc_codegen_expr.c`'s call emitter has a real extern mechanism: `gen->extern_funcs[32]` records `{name, addr}` pairs (registered via `hc_register_extern`); for a resolved identifier it emits `mov rax, imm64(addr); call rax`. But the **fallback for an UNresolved identifier was `emit_mov_rax_imm64(gen, 0); call rax`** — i.e. `call 0`, a NULL-pointer indirect call. Any HolyC program that calls a function the JIT doesn't recognize (the era demo's `Print()`/`FpWriteFile()`, from `demos/era/holyc_era_demo.hc`) lands here → SIGSEGV inside the JIT page with `rax=0`. This is a genuine bug, NOT a stub — there is a legitimate HolyC runtime (host effects) the demo expects. **Fix (three parts):** (a) create `src/compiler/holyc_runtime.c` with real host implementations — `int64_t wubu_print(const char *s)` (fputs + flush), `int64_t wubu_fp_write_file(const char *path, const char *data)` (fopen/fwrite), etc.; (b) in `hc_eval`, after `hc_gen_init`, call `hc_register_holyc_runtime()` which registers `Print→wubu_print`, `FpWriteFile→wubu_fp_write_file`, … via `hc_register_extern`; (c) harden the JIT fallback so it NEVER emits `call 0` — emit `mov rdi, rax` (name ptr) then `call hc_unresolved_trap` (a real `void hc_unresolved_trap(const char*)` that `fprintf(stderr)`s `"unresolved function: %s\n"` and returns), so a still-unknown call fails loudly instead of SIGSEGVing. The `hc_register_holyc_runtime` symbol means **every link recipe that compiles `holyc_codegen_api.c` must now also carry `holyc_runtime.o`** (see `wubuos-build-recovery` Mode H). Symptom of the pre-fix crash: gdb shows `call *%rax` with `rax=0` at a `rwxp` JIT address, `rdi` pointing at a BSS string like `"runtime"` (the first `Print("...")` arg). **Triage fingerprint (all three JIT-SIGSEGV classes + the gdb one-liner):** see [`references/holyc-jit-sigsegv-fingerprint.md`](references/holyc-jit-sigsegv-fingerprint.md).

Reference recipe for the global SIGSEGV (RX-data-page + missing RIP-relative Inc/Dec/`&x`): `references/holyc-global-sigsegv-fix.md`.

Reference recipe for global variables across function calls (5 bugs: interpreter mem save/restore, VR collision, parameter slot_addr, regalloc live ranges, caller-saved save/restore): `references/holyd-global-vars-across-calls-2026-08-30.md`.

Reference recipe for AVX-512 GEMM Zen 4 tuning (K-unroll, panel-parallel, NC tuning, prefetch): `references/gemm-zen4-tuning-2026-08-30.md`.

Reproduce recipe + minimal gdb probe for the 2026-07-20 `parse_block` SIGSEGV
(garbage input) and the lost-persistent-global bug: `references/holyc-eval-sigsegv-persist-fix.md`.

## Fix-Then-Verify Loop

Reference recipe for the persistent-variable bug (module-global vs stack-local
misrouting via `has_prologue`): `references/holyc-persistent-var-repro.md`.

### Gauntlet failures live in the MIR bridge, not the direct JIT
When a gauntlet test fails, the bug is almost always in the MIR bridge
(`holyd_mir_eval.c`), a SEPARATE lowerer from the direct-JIT `hc_eval` path
this playbook mostly documents — a fix in one path is usually still live in the
other. Reproduce a single test with
`./gauntlet_runner --dump-asm x86-64 "$(cat test.c)"`, then bisect with minimal
repros. The recurring root shape there is the **computed-lvalue bug family**
(lowering paths that resolve the LHS type only from a scalar `ident`, so
`a[i]`/`*p`/`s.f` silently skip truncation / float-conversion / promotion /
stride logic). Full bridge map, the five fixed instances, and the three-gate
regression check: `references/holyc-mir-bridge-2026-08-16.md`.

1. Reproduce with a probe, get the exact failing construct.
2. Apply the minimal real fix (no stubs).
3. `make clean && make runtime && make hosted` then `make test_holyc`.
4. **Run the FULL gate (`make test`), not just `test_holyc`.** The compiler/lexer
   are SHARED with `test_holyd` (which compiles via `hc_eval`) and other targets.
   This session, a correct `hc_eval` fix regressed `test_holyd` (`eval x+10 returns
   133`) because holyd's eval path shared the same codegen — caught only by the
   full gate. Confirm the previously-hanging/target completes AND every other
   target still passes (regression check across the full `make test` gate).

## Two more root-cause fixes (2026-07-20 session)

### A. `parse_block` infinite loop → OOM → NULL-deref SIGSEGV on garbage input
**Symptom:** `wubu_holyd_eval("this is not holyc @@@")` died with **SIGKILL (137)** under the test's `ulimit -v`/JIT cap; under plain `gdb` it was a clean `SIGSEGV` at `holyc_parse.c:572 n->child = expr;` inside `parse_block`→`parse_stmt`. The real cause was NOT the JIT — it was the parser: on an unparseable token, `parse_stmt` returns a non-NULL node **without advancing the lexer**, so `parse_block`'s `while` loop never terminates → spins forever → exhausts memory → `hc_ast_new()` returns NULL → `n->child = NULL_ptr` derefs → crash. Under a memory cap the OOM manifests as SIGKILL, which masks the true NULL-deref.

**Fix (defense-in-depth, in `parse_block`):**
```c
int start_pos = p->lex->pos;
hc_ast_add_stmt(block, parse_stmt(p));
if (!p->has_error && p->lex->pos == start_pos) {
    parse_error(p, "unexpected token in block");   /* bail cleanly */
    break;
}
if (p->has_error) break;
```
KEY: set `start_pos` **after** the `expect(LBRACE)` that opens the block (the brace already advanced `pos`; capturing it *before* the first statement made the guard fire spuriously on valid input). The guard fires only when a statement makes ZERO progress.

### B. Persistent global vars LOST across evals (returned garbage)
**Symptom:** `eval "I64 acc = 10; 0"` then `eval "acc + 32"` returned `32` (not `42`) — the load of `acc` yielded 0. Root cause: `wubu_holyd_eval` freed `gen.data` (the data section that holds module-level globals) after every eval:
```c
free(compiler->gen.data);  compiler->gen.data = NULL;
compiler->gen.data_size = 0;  compiler->gen.data_cap = 0;
```
`hc_gen_init` already `memset`s `gen` then restores `gen.data` (it is the persistent REPL state), so freeing it discards globals between evals. **Fix: keep `gen.data`/`data_size`/`data_cap` across evals; only free the freshly-generated `gen.code` + `exec`.** The RIP-relative global-load math (`disp32 = code_size + global_offset - patch_pos - 4`) is then correct and the value survives.

### C. Garbage-input eval must be wrapped as a BLOCK, not a bare expr (REPL semantics)
The old `wubu_holyd_eval` tried `hc_parse_expr` first, then a statement parse, then a block wrap — a brittle dual-parse heuristic that left the parser in a corrupt state. **Fix:** wrap the whole source in `{ %s; }` (append `;` only when it doesn't already end in `;`/`}`), then `hc_parse_block` once. This uniformly handles bare exprs (`1+2+3`), decl+expr (`I64 sq(I64 n){ return n*n; } 0` → the trailing `0` is the return value in RAX), and pure decls, and the progress guard (A) turns garbage into a clean parse error instead of a crash. Verified by `test_holyc_agi` going 11/11.

## Differential testing vs gcc (the bug-bank harness — 2026-08-04)

`tools/compiler_diff.c` (in the wubuos repo): compile the SAME expression with
OUR compiler (`hc_eval`) AND with gcc (generated C file + subprocess), run both,
compare. Every divergence is a FINDING — either we're wrong (fix ours) or gcc is
(the Csmith doctrine applied to ourselves). Its first runs caught **6 real
codegen bugs** — this is the single highest-leverage compiler-debugging tool.

Build (links the compiler + all jit objects):
```
gcc -O0 -g -Isrc/compiler -Isrc/jit src/jit/jit.c src/jit/jit_encode.c \
  src/jit/wubu_x86.c src/jit/wubu_disasm.c src/jit/x86_regalloc.c \
  src/jit/jit_minic.c src/jit/jit_minic_token.c src/runtime/wubu_spawn.c \
  src/compiler/holyc_lexer.c holyc_parse.c holyc_parse_ast.c holyc_codegen.c \
  holyc_codegen_emit.c holyc_codegen_expr.c holyc_codegen_stmt.c \
  holyc_codegen_api.c holyc_runtime.c tools/compiler_diff.c -o src/compiler/compiler_diff -ldl
```
Usage: `compiler_diff "1|2&4" 1` — prints ours/gcc, flags `⚠ FINDING` on
divergence. Run a battery of ~33 expressions (arithmetic, precedence, nested
parens, shifts, comparisons, bitwise) with known expected values; the harness
teaches you C precedence as a bonus (a wrong expected value in the TEST is a
finding too — verify against gcc's answer before blaming the compiler).

The maintained battery lives in `tools/compiler_diff_battery.sh` (one
command, 33 expressions, exit code 0 only when all pass) — run it after ANY
codegen change instead of hand-rolling the list.

### THE rdi-CLOBBER BINOP FAMILY (6 bugs, one root cause — HIGH VALUE)

The binop codegen in `holyc_codegen_expr.c` parked the LEFT operand in `rdi`
via `emit_mov_rdi_rax`, then evaluated the RIGHT operand — which, being itself a
binop, **clobbered rdi**. The saved left was destroyed. Symptoms (all "wrong
result, no crash"):
- `1|2&4` → 4 (should be 1 — the inner `2&4` clobbered the `1` in rdi)
- `1+(2*3)` → 9 (should be 7)
- `10-(3*2)` → -4 (should be 4)
- all SHL/SHR/comparisons had it too (the right operand's eval clobbers rdi)
The bug only fires when the RIGHT operand is a compound expression — the 
The original tests with literal right operands all passed, hiding it for months.

Two emitter-level binop bugs found when the minic JIT backend went live (2026-08-13): `0x81` opcode-extension mismatch (SUB emitted SBB — pass the literal `/5` extension, never a register) and variadic `jit_callv` reorders forwarded args (drain into an array first, dispatch through typed `jit_callN`). See `references/jit-emitter-binop-bugs.md`. The full machine-op encoding wave (div-by-constant Granlund–Montgomery magic — `p` starts at 63, negative-magic compensation `hi+=x` when M's sign bit is set, sign-correction `q-=(x>>63)`; lea SIB scale is 2 bits so only *3/*5/*9 are lea-able; CMOVcc DST is the REG field; test-vs-cmp for x==0; Souper-style `tools/peephole_superopt.c` discovery engine) lives in `references/jit-machine-op-encodings-2nd-wave.md`.

**Correct fix pattern (ALL binops, uniform):**
```c
gen_expr(node->left);  emit_byte(0x50);   /* push rax (left) */
gen_expr(node->right);                    /* rax=right; may clobber rdi */
emit_byte(0x5F);        /* pop rdi  (rdi=left) */
emit_xchg_rax_rdi(gen); /* rax=left, rdi=right — REQUIRED */
<op> rax, rdi;
```
The `xchg` is **REQUIRED for the non-commutative ops** (SUB/DIV/MOD/SHR) —
dropping it REVERSES the operands (`10-(3*2)` → -4). Our own first fix dropped
it and the differential harness caught the regression immediately. Never remove
the xchg; for commutative ops it's a harmless no-op of sorts, for the rest it's
the difference between `a-b` and `b-a`.

## The holyc CLI + the compiler-flags doctrine (2026-08-04)

`tools/holyc.c` (built by `make holyc`) is the compiler front-end that
SHIPS the user's joke as real flags:
- `holyc <file.hc>` — C11, the sacred tongue (hc_eval, silent dignity).
- `holyc -c_developer <f>` — the C18/C2* exception (blessing spoken,
  then hc_eval as usual).
- `holyc -i_make_shit_code <f>` — any other language, because we ballin:
  the roast prints, then the source is fed to hc_eval anyway.
- `holyc -brainfuck <src>` — the meme, compiled for REAL: `bf_run()`
  from `src/compiler/brainfuck.c` (8 commands → x86-64 JIT, tape in
  RBX/R12, real jnz loops). Build with `-DHOLYC_BF_EMBEDDED` so
  brainfuck.c's `main` is excluded and `bf_run` is callable.

**The extern-alias pattern (makes "-i_make_shit_code work")**: an
unresolved function call in hc_eval previously emitted `call 0` →
SIGSEGV (the fixed 2026-07-22 trap). For the joke path, `holyc_runtime.c`
registers lowercase aliases (`print`, `puts` → `wubu_print`) alongside
the HolyC personality (`Print`, `FpWriteFile`), so ANY submitted
language's most common call resolves instead of crashing. When adding a
language alias: register the lowercase name in
`hc_register_holyc_runtime` (the extern table is capped at 32 entries).

The full compiler doctrine + language taxonomy (the six buckets: C11 /
C18-C2\* via -c_developer / assembly / HolyC / brainfuck / everything
else via -i_make_shit_code) lives in
`docs/compendium/02-architecture/compiler-doctrine.md` in the wubuos
repo — the 7-hop research that produced it is summarized there too.

## JIT loop-patch rel32 math (brainfuck JIT — 2026-08-04)

`src/compiler/brainfuck.c` (the `-brainfuck` meme flag, a real 8-command →
x86-64 JIT): `[` emits `cmp byte [r12+rbx],0` (5 bytes) + `jz rel32` (6 bytes:
`0F 84` + 4-byte rel), `]` emits the same cmp + `jnz rel32`. When patching the
rel32s:
- `jz` jumps PAST the matching `jnz` → target = `jnz_rel + 4` (the jnz ends at
  jnz_rel+4). Correct.
- `jnz` jumps BACK to the cmp before the jz → target = **`jz_rel - 7`**, NOT
  `jz_rel - 5`: the jz is `0F 84` (2 bytes) + rel (4 bytes) = 6 bytes, and the
  cmp before it is 5 bytes → cmp starts at `jz_rel - 2 - 5 = jz_rel - 7`. The
  naive `-5` lands MID-CMP → garbage execution → segfault.
**Triage fingerprint for a JIT loop crash:** if a loop-containing program
segfaults but loop-free ones run, suspect the back-jump rel32 target, and
recount the instruction lengths before the target (opcode bytes + rel field +
any preceding instruction), not just the immediate predecessor's size.

## Bulk file-mutation script safety (the 20-file wipe — 2026-08-04)

When a Python/sed script rewrites MANY files at once (e.g. stripping a feature
macro from every `.c`), a one-line bug can silently EMPTY them. This session:
`out, i, n = [], len(lines), 0` — `n = 0` instead of `n = len(lines)` made the
loop never run and `"".join(out)` wrote every file as EMPTY (20+ files, caught
only when the build failed with `undefined reference`). Rules:
1. **Guard the write**: `if not new.strip() and src.strip(): refuse` — never
   write an empty output for a non-empty input.
2. **Verify after the batch**: `git status --short | awk '$1=="M"{print $2}' |
   while read f; do [ ! -s "$f" ] && echo "EMPTY: $f"; done` — catch empties
   before building.
3. **Recovery is instant**: `git checkout -- <file>` on every emptied file
   restores it (files were never committed empty — the index still has the
   originals). Then redo the mutation with the fixed script.
4. Feature-macro strip keep-list must be COMPLETE: symbols hidden by the build's
   global `-D_POSIX_C_SOURCE=200809L` (`FTW_DEPTH`, `CLONE_NEW*`, `DT_DIR`,
   `st_atime`) legitimately need `_GNU_SOURCE` — stripping them breaks the build;
   a cargo-cult `#ifndef _GNU_SOURCE / #define / #endif` guard stripped only
   partway leaves a DANGLING `#endif` (`#endif without #if`). Check for both
   after the strip: build the repo + `head -12` any modified file for a leading
   `#endif`.

## Multi-ISA driver space: one MIR, N backends (2026-08-04)

The full everything-hardware map (all CPU/GPU/MCU/DSP/NPU tiers, the
llama.cpp 15-backend proof, the host-detection tool) lives in
`references/holyc-everything-hardware.md`. The 8086 driver (the x86
root, reusing the repo's in-process DOS emulator) is a DIAGNOSED WIP
with the full encoding table + bug hypothesis in
`references/holyc-8086-driver-wip.md`. The driver-space pattern:

1. The HolyC frontend lowers AST → `wubu_mir_prog_t` (MIR) — the **hourglass
   neck**. MIR is ISA-neutral: virtual registers, `.L` operands, condition-
   producing compares, label-relative jumps.
2. Each ISA is a **driver** in `wubu_isa_driver_t` (`wubu_isa_driver.c/.h`):
   `{name, family, exec, compile, run, describe}`. Register each as an
   `extern const wubu_isa_driver_t`.
3. `wubu_isa_find(name)` maps "x86-64" / "riscv" / "m68k" / "68000" to a
   driver. The test harness compiles the SAME MIR with every driver and
   differential-execs to prove equivalence.
4. `exec = WUBU_ISA_NATIVE` → `mmap`+mprotect-executable (x86-64 JIT);
   `exec = WUBU_ISA_INTERPRETED` → a bundled interpreter decodes the driver's
   own emitted bytes (RISC-V, m68k). The interpreter is the **verification
   oracle** — it proves the bytes mean what the encoder intended.
5. The 68000 driver (`wubu_isa_m68k.c`, 1979 CISC): big-endian, D0-D7/A0-A7,
   flat 24-bit address space. `LINK A6` opens frame, each vr at `(A6 - (vr+1)*4)`
   (**NEGATIVE displacement** — LINK allocates BELOW the fp; positive offsets
   hit the caller's stack → SIGSEGV), `UNLK A6/RTS` closes. `.L` arithmetic —
   `.W` for MULS/DIVS (16-bit result).
6. **Verify every encoding against GNU binutils**: `tools/verify_isa.sh`
   (the permanent in-repo oracle) packs hex words and disassembles with the
   multiarch objdump (`m68k:68000`). NO GUESSED OPCODES — the oracle caught
   a wrong MOVE field layout in minutes (`0x2000` = `movel %d0,%d0`, NOT
   0x2004; size is bits 13-12, dest 11-9+8-6, src 5-3+2-0). The full
   verified table + format + the battery's two extra catches live in
   `references/holyc-m68k-oracle-encodings.md`.

The battery (`tools/mir_driver_test.c`) asserts all 3 drivers agree on a 30-expr
arithmetic set. Any divergence is a FINDING in that ISA's encoder.
The 8086 driver is a DIAGNOSED WIP (2/33; RET-vs-INT20h termination, unsigned
MUL/DIV) — full encoding table + diagnosis in
`references/holyc-8086-driver-wip.md`; the everything-hardware map (all
CPU/GPU/MCU/DSP/NPU tiers + the llama.cpp 15-backend proof of this pattern) in
`references/holyc-everything-hardware.md`.

## Macro patch-tracking: use inline helpers, NOT `#define` (2026-08-04 pitfall)

When a JIT backend records forward/backward jumps for a second patch pass,
the temptation is a `#define` macro that pushes into a patch array:
```c
#define PATCH_AT(pos, cond, lbl) do { \
    patches[np].pos = (pos); patches[np].cc = (cond); \
    /* ... */ \
} while (0)
#define PATCH(cond, lbl) PATCH_AT(e.n, (cond), (lbl))
```
This **breaks under C11** when the macro references function-local variables
(`e`, `patches`, `np`, `cp`) and is expanded deep inside a `switch` case. The
symptoms are maddening and point at the WRONG place:
```
wubu_isa_m68k.c:173:16: error: 'm68k_patch_t' has no member named 'e'
wubu_isa_m68k.c:178:38: error: expected identifier before '(' token
```
GCC expands `patches[np].pos = (e.n)` and, because `e` and `patches` are ALSO
captured by name inside the macro body, the parser reinterprets the member-
access chain — reporting `m68k_patch_t has no member named 'e'` (the `e` of
`e.n` is swallowed into the `patches[np].` deref) and `expected identifier`
where the macro-parameter name collides with a struct-member name.

**The fix is to use an inline helper FUNCTION, not a macro.** Pass the
patch-state by pointer; the function owns its locals cleanly:
```c
static void patch_push(m68k_patch_t **patches, size_t *np, size_t *cap,
                       size_t pos, uint16_t cc, uint32_t label, size_t direct)
{ if (*np == *cap) { *cap = *cap ? *cap * 2 : 16;
    *patches = realloc(*patches, *cap * sizeof(m68k_patch_t)); } /* fill fields */ }
/* caller: #define PATCH(cond, lbl) patch_push(&patches, &np, &cp, e.n, (cond), (lbl), (size_t)-1) */
```
The macro then becomes a ONE-LINE trampoline (`patch_push(&patches, &np, &cp, …)`) —
it has no `patches[np].` deref and no struct-member-name collision, so it expands
cleanly. See `references/holyc-macro-patch-pitfall.md` for the full repro.
`BRA_CC(cc)` with a parameter named `cc` adds a second collision with a local
`uint16_t cc` variable in the compare case — rename macro params to `cond`.

## Pitfalls (additions for 2026-08-16 gauntlet + symlink session)

- **CRITICAL PATH CONFUSION — `wubuos` (OS) vs `wubuos` (compiler).** The OS repo is `/home/wubu/wubuos/`. The compiler repo is `/home/wubu/wubuos/`. They are DIFFERENT directories with DIFFERENT git remotes. The OS imports the compiler via a symlink: `wubuos/src/compiler -> /home/wubu/wubuos`. **Edit compiler files ONLY in `/home/wubu/wubuos/`.** When the user says "wubuos" they mean the compiler. When they say "wubuos" they mean the OS. If unsure, ask — guessing wrong wastes a full iteration. See `references/repo-topology-symlink-2026-08-16.md`.
- **Gauntlet runner must NOT call `hc_eval` twice per test.** The old failure-recheck called `run_test_x86_64()` a second time after the target loop, doubling JIT executions → segfault at ~132/157 tests. Save `x86_result`/`x86_actual` from the target loop, reuse for display.
- **32-bit overflow needs `cdqe` after integer ADD/SUB only.** Emit `48 63 C0` after `emit_add_rax_rdi`/`emit_sub_rax_rdi` when `pointer_elem_scale <= 1` (not pointer arithmetic). Do NOT emit before epilogue (breaks unsigned literals like `2147483648`). Do NOT emit after MUL (breaks `42*1`).
- **POST_INC/DEC on non-IDENT lvalues (`a[i]++`, `*p++`):** use `emit_base_addr` → `rdi` = address, sized load (`mov eax,[rdi]` for int), save old in `rsi` (NOT `rdi`), inc/dec + cdqe, sized store (`mov [rdi],eax`), return old in `rax`. Qword load/store corrupts adjacent array elements.
- **Braced initializers `{1,2,3}`:** parser `case HC_TOK_LBRACE` in `parse_primary` creates `HC_AST_BRACE_INIT`. VAR_DECL stores elements at consecutive `i*elem_size` offsets from array base. Single-element in expr context evaluates directly; multi-element returns 0.
- **Unsigned comparison:** `HC_AST_GT` must use `seta` (unsigned) when left operand type is `HC_TYPE_U32/U16/U8`, not `setg` (signed). Without this, `{unsigned x=0; x--; x>0}` returns 0 instead of 1.

## Multi-declarator type inheritance + array/pointer lvalue codegen (gauntlet 2026-10-12)

Gauntlet wcc/extern/gcc_torture failures surfaced a cluster of HolyD->MIR
(`holyd_mir_eval.c`) and parser (`holyd_parse.c`) bugs on COMPUTED lvalues
and multi-declarators. Root causes + fixes (all pushed, core gauntlet 247/247,
MIR battery 111/117 [6 pre-existing], selfhost 155/155, v3 1262->1371 pass,
valid_pass_rate 47.3%->51.4%):

- **Multi-declarator scalar-after-array inherits ARRAY type.** `hd_parse_decl`'s
  first-declarator array handling reassigns the local `type` to an ARRAY type
  (`type = base_type`). Additional declarators did `HDType *vtype = type`, so
  `int a[2], b;` gave b the array type -> b marked is_array -> reads as a
  pointer (returns garbage like 32). Scalar-first (`int b, a[2]`) worked. Fix:
  capture `HDType *elem_type = type;` BEFORE the array mutation and use
  `elem_type` for additional declarators. SAME bug in struct-member decls
  (`int *sp, fc, *sc, a[2]`) — the parser shares the path.
- **Compound-assign on INDEX/DEREF lvalue never truncated to element type.**
  The truncation lookup only handled scalar IDENT lvalues, so an unsigned
  32-bit array element accumulated at 64-bit and never wrapped
  (`a[1]=4294967294U; a[1]+=2` -> 4294967296 not 0). Fix: `mir_lvalue_elem_type()`
  resolves INDEX/DEREF element types from the base var's array base or pointer
  pointee; use it in both the truncation block and the float back-conversion
  block (`a[i] -= 10.0`).
- **`mir_promote_to_float` only promoted IDENT/binop/literal nodes.**
  INDEX/DEREF/MEMBER/ARROW fell through to `return val unchanged`, so a mixed
  float compound assign on `a[i]` did DSUB on an un-promoted integer lhs.
  Fix: add those kinds to the promote switch.
- **Multi-dimensional array stride was flat for 3D+.** `mir_index_stride` used
  `array_stride` (one level) for the outermost index and a flat 8-byte stride
  for ALL inner indices, so `int a[2][2][2]` read `a[1][1][1]` as 5 not 8.
  Fix: walk the ARRAY type spine; the depth-d index strides by the product of
  the inner dimension sizes (a[i]->D1*D2, [j]->D2, [k]->1 cells).
- **++/-- on a computed float lvalue used integer ADD/SUB.** `*p` where p is
  `double*`, `++a[i]` on `double[]` — the general-lvalue inc/dec paths had no
  float detection (only the scalar IDENT path did). Fix: `mir_lvalue_is_float()`
  -> emit MIR_DADD/MIR_DSUB when the lvalue holds a double.

Repro tool: `make gauntlet_runner` then `./gauntlet_runner --dump-asm x86-64
"<C source>"` prints `result=N` (the program's exit code) or `build failed`.
Bisect a failing test by shrinking to the minimal construct — a combo that
fails while each piece alone passes points at a SHARED parse path (both the
multi-declarator and non-first-param bugs were exactly this). The full
gauntlet is `./gauntlet_v3` (4431 tests, 6 workers, ~2min, JSON summary).

Two more 2026-10-12 parser bugs (both v3-verified, core 247/247, selfhost
155/155, MIR 111/117):
- **Multi-declarator POINTER (`, *q`) after the first declarator failed to
  build.** The additional-declarator loop required an IDENT right after the
  comma, so `int *p, *q;` / `int a, *b;` / `struct S *p, *q;` hit "expected
  ident after comma" — extremely common. Fix: consume leading `*` tokens and
  wrap the element type in that many PTR levels. (v3 +31 tests, 51.4->52.5%.)
- **Array dims on a NON-first function parameter failed to build.**
  `int f(int n, int array[])` / `int f(int n, int a[2][3])` — the param comma
  loop did parse_type+IDENT and never consumed trailing `[N]`, so
  expect(RPAREN) failed. Array-first worked (hid it). Fix: consume `[N]` dims
  in the subsequent-param loop and convert to a pointer (array-param decay).
  VLA dims with a side-effect expr (`array[i++]`) parse+discard the expr.

Three more 2026-10-12 struct/type parser bugs (all v3-verified, core 247/247,
selfhost 155/155, MIR 111/117):
- **Anonymous bit-field `unsigned : 12;` (padding, no name) failed to build.**
  The struct-member parser required an IDENT after the type, so `:` with no
  name hit "expected member name". Fix: detect `:` right after the type as an
  anonymous bit-field, consume the width, skip (advances layout, no member).
- **Bit-field width as a constant expression** (`int s : (sizeof(int)*8-2)`,
  `int s : (30-2)`) failed — only a literal INT was accepted after `:`. Fix:
  fold simple constant arithmetic for the width; default to 32 if unfoldable.
- **Trailing `int` after `long long` / `unsigned long long`** (`long long int`,
  `unsigned long long int`) failed — parse_type consumed the two `long`s but
  not the redundant trailing `int`. Fix: consume a trailing I32 in the I64 and
  U32 type cases.

### Bit-fields were silently stripped by the preprocessor (2026-10-12, commit 993b718)
The single highest-impact find of the gauntlet wave. `wubu_preproc.c`'s
`strip_bitfields()` DELETED `:N` from every bit-field declaration before the
lexer saw it — a legacy workaround from when the compiler had NO bit-field
support. Once the parser grew real bit-field handling, this stripping became
actively harmful: `int :4` lost its `:4`, and `int a:4` was silently degraded
to a plain int member (which coincidentally gave correct results for small
values, hiding the bug). Three coordinated fixes:
1. **Remove `strip_bitfields()` entirely** — bit-fields now flow to the parser.
   (The ternary guard it carried is moot once the strip is gone; verify
   ternaries still work after removing it.)
2. **Anonymous bit-field `unsigned : N;`** now advances the bit layout (pack
   into the word, respect 32-bit boundaries, grow `t->size`) and registers no
   member, instead of erroring. Bit-field member `offset` = the CELL index
   (`bit_offset/64`) so the codegen's `mir_struct_member_offset` (`*8`) and the
   bit-shift compose correctly — all bit-fields in the first cell share
   offset 0 and `bit_offset` positions within the loaded 8-byte cell.
3. **Phase-1 struct registration copies `member_bit_widths`/`member_bit_offsets`.**
   It copied every other member field but these two, so the bit-field
   read/write paths never triggered (bw==0 -> plain 8-byte cell load ->
   sibling bit-fields clobbered each other). Struct brace-initializers now
   pack bit-field values with a read-modify-write instead of overwriting the
   whole cell.

Debugging lesson: when a feature "half-works" (named bit-field reads correct
for small values but anon bit-fields build-fail and multi-bitfield structs
clobber), suspect a PREPROCESSOR or earlier stage silently transforming the
source — dump the token stream (`fprintf` after `parse_type`) to see what the
parser actually receives vs. what you wrote. Here the token after `int` was
`;` not `:`, revealing the `:4` never reached the lexer.

Known remaining edge: an anonymous bit-field BETWEEN named fields in a brace
initializer (`int a:4; int :4; int b:4;` x={2,3}) misaligns the init value
index (the anon field occupies a member slot but has no init value).

### Multi-declarator bit-fields, anon members, wide literals (2026-10-12, commits 1873389/435e82b/62b97f6)
Three more parser/lexer gaps, all v3-verified (core 247/247, selfhost 155/155,
MIR 111/117):
- **Bit-field width on an additional struct declarator** (`int a:4, b:4;`,
  `unsigned long long a:8, b:32;`) failed — the additional-declarator loop
  handled `*ident`/`ident[N]` but not `ident:N`. Fix: parse `:N` there and
  pack like the first declarator (advance `t->bit_pos`, cell index =
  `bit_pos/64`).
- **Anonymous struct/union member** (`union { int b; };` with no name) hit
  "expected member name". Fix: flatten the inner members into the outer
  struct at the current offset (C11 anonymous member transparency) so
  `foo.b` resolves directly.
- **Wide literal prefix** `L"..."`/`L'...'` (and u/U) — the lexer had no
  prefix handling, so `L` lexed as an identifier and the quote became a
  separate token. Fix: when the leading char is L/u/U and the next is a
  quote, consume the prefix and scan the literal (wide==narrow for ASCII).
  `L` as a plain identifier still works. Added `wchar_t` -> int to the
  preprocessor builtin typedefs.

### Pre/post-inc/dec on a bit-field member must RMW (2026-10-12, commit 8ef4e1b)
`arr[i].n++` / `x.n++` on a struct bit-field loaded the whole cell, inc'd, and
stored back — clobbering sibling bit-fields (m became 0 after n++). Single-field
structs worked, hiding it. Fix: `mir_lvalue_bitfield()` detects
DOT/MEMBER/ARROW whose base resolves to a registered struct with a non-zero
member bit-width; both POST_INC and PRE_INC general-lvalue paths then RMW
(extract field via mask+shift, +/-1, mask to width, shift back, clear the
field's bits, OR in the new value). Pre-inc returns the new masked field value.
Note: `mir_lvalue_bitfield` needs forward decls of `mir_find_struct`/
`mir_dot_struct_type`/`mir_find_var_struct_name` (it's defined earlier).
Signed bit-field overflow wraps correctly (7-bit `n=63; n++` -> -64).

### Anonymous-struct bit-field registration + sizeof() in width (2026-10-12, commit 161e7bf)
Two more bit-field gaps:
- **Anonymous-struct registration in VAR_DECL** copied every member field
  (names, offsets, is_unsigned, is_ptr, type kinds, type names) but NOT
  `member_bit_widths`/`member_bit_offsets` — so an anonymous struct's
  bit-fields never triggered the bit-field read/write (plain cell load,
  siblings clobbered). Named structs worked (phase-1 path), hiding it. This is
  the THIRD place struct members get copied — ALL THREE must copy the two
  bit-field fields (phase-1 named, HD_AST_STRUCT_DECL, and the VAR_DECL
  anon path). When adding a member field to `mir_struct_t`, grep every
  `s->member_` copy site and update all of them.
- **sizeof() in a bit-field width const-expr** (`int s:(sizeof(int)*8-2)`)
  folded to nothing (sizeof skipped as unknown ident) → defaulted to 32.
  Fix: `sizeof` is a KEYWORD (`HD_KW_SIZEOF`), not an IDENT — check the token
  type, not `tok.text`. Fold `sizeof(type)` to the type's byte size
  (int/long=8, short=2, char=1).

### total_mem byte/cell unit mismatch clobbered struct returns (2026-10-12, commit c3f3a40)
A latent allocator bug with wide blast radius. `prog->total_mem` is shared by
two allocators that disagreed on UNITS: the eval-side local/param/guard/va
allocations advanced it in CELLS (`cell_idx = total_mem+1; total_mem = cell_idx
+ n - 1`), while `wubu_mir_alloc` (string literals, struct-return buffers,
VLAs, compound literals) advanced it in BYTES. A struct-return buffer
(`mir_alloc`) could therefore land on top of a live local's cells; the
forward struct-return copy (`m=0..n`) then read cells the buffer had already
overwritten — `g().c` returned a's value (cell 0) instead of c (cell 2) for
any struct with >2 cells. 2-cell structs worked, hiding it.

Fix: make every eval-side total_mem site use BYTES, consistent with
`wubu_mir_alloc`. Locals/params/guards/va advance total_mem by n*8 bytes from
an 8-aligned base; cell-based `mir_alloc` callers (arr_size, ret_struct_size,
vla_block, n_cells) now pass *8.

Lesson: when one shared counter (`total_mem`) is advanced by multiple code
paths, GREP every assignment and confirm they use the same unit. A
cell/byte mismatch is invisible until two allocations collide. Debugging a
wrong struct-return value: dump the copy's src/dst VRs AND the byte addresses
they hold — if they overlap, the copy direction or the unit is wrong.

**After the fix, grep for the OLD pattern name and confirm ZERO matches.**
A script-based `str.replace()` silently misses sites with different variable
scoping (`&g` vs `g`, `prog` vs `g->prog`) — two cell-based sites (param-struct
and va_args allocation) survived the first fix and caused an 11-test v3
regression. Grep `cell_idx` across the file after the change; any hit is an
unfixed site.

**Run v3 (not just the three standard gates) after any allocator or
memory-layout change.** The three gates (MIR battery, selfhost, core gauntlet)
all stayed green through the first fix while v3 dropped 1483→1472 — v3's
broader corpus catches allocator collisions the narrow gates miss.

**Reverse-loop diagnostic for memory overlap:** if a forward copy
(`m=0..n`) reads stale cells, reverse it (`m=n-1..0`). If the reverse fixes
it, the source and destination overlap and the copy direction was the
proximal bug (the root cause is the allocator units, but the reverse loop
confirms the diagnosis in one build).

### Designated initializer with nested brace value (2026-10-12, commit 379572e)
`.c = {1,2,3}` (designated field init whose value is a brace list) called
`mir_gen_expr` on the BRACE_INIT child, yielding one bogus scalar stored at the
field offset — the array elements were never written. Scalar designated init
(`.b = 5`) worked, hiding it. Fix: when the designated init's child is a
BRACE_INIT, store each leaf at consecutive cells from the field offset via the
existing `mir_store_brace_leaves` (the same helper multi-dim array inits use).
Also covers the GCC `fieldname: {..}` extension form.

### String literal subscript is byte-addressed (2026-10-12, commit e3ee55d)
`"ab"[1]` returned 0 — `mir_index_stride` defaulted a STRING_LIT base to
stride 8 (cells) and the element load was a full-cell load, but string literals
are byte-packed (stride 1). Subscripting via a `char*` variable worked (that
path sets stride 1 + byte load), hiding it. Also broke adjacent concatenation
+ subscript (`"ab" "cd"[2]`). Fix: in `mir_index_stride`, a STRING_LIT root
strides by 1; in the INDEX codegen, a STRING_LIT base sets `char_elem` so the
load is a byte load. MIR battery improved 111->112.

### Function pointer via &f and (*fp)() deref call (2026-10-12, commit 24da733)
Function-pointer resolution only recognized a bare function IDENT as the
target, so `int (*fp)(int) = &f; fp(5)` and `s.fn = &add` left
`fn_ptr_func_id` unset (no indirect call), and `(*fp)(5)` had a DEREF callee the
call resolver ignored. `fp = f` (implicit decay) worked, hiding it. Fix: (1)
the init and assign `fn_ptr_func_id` paths now also accept `&f` (ADDR of an
IDENT) as the target; (2) the call resolver handles a DEREF callee `(*fp)` by
resolving the inner IDENT's `fn_ptr_func_id`, and a bare-IDENT callee `f(x)`
(f a func-ptr var/param) by that IDENT's `fn_ptr_func_id`.

### Function pointer passed as a PARAMETER — cross-function pre-pass (SHIPPED)
`call(add,3,4)` where `call`'s body does `f(x,y)`: the callee body is compiled
once and the param `f`'s func_id is set at the CALL SITE, not in `call`'s
scope. Fix: a per-func map `param_fnptr[callee][pi]` built by a PRE-PASS that
walks every call `callee(fn, ...)` — when `fn` names a function and callee's
param `pi` is a PTR→FUNC type, record `param_fnptr[callee][pi]=func_id(fn)`.
When a body binds params, seed each func-ptr param var's `fn_ptr_func_id` from
the map and CLEAR it to -1 when absent (else a stale func_id from another
function's same-named var leaks). `MIR_CALL` still carries a static func_id;
the map supplies the right one per callee. (The old note that a per-func map
"is NOT enough" was WRONG — it IS enough for single-hop propagation, verified
call(add,3,4)=7, apply(dbl,21)=42. TRANSITIVE `b(inc)→a(f)→f()` needs a
fixpoint over the map.) This propagation also lets cooperative C11
`thrd_create`/`thrd_join` resolve the callee — see
`references/cooperative-threads-builtins.md`.

### Recursive-call live-range spill / call-frame architecture — KNOWN OPEN (diagnosed)

The fib/fact recursion wrong-result bug (fib(10)=-80, `f(x)+x` after a
recursive call reads the clobbered param). CONFIRMED root cause: the
`holyd_mir_eval.c` param prologue allocates each param's memory cell from
`prog->total_mem` at COMPILE time (one fixed byte address per param), NOT a
per-invocation frame — so every call reuses the same param cell. Same
architectural gap as #37. **NOT a single-bug fix** — needs a runtime call-stack
frame (frame-pointer-relative params+locals), which also fixes the JIT
live-range overlap and the interpreter. Full diagnosis, the interpreter
memory-scope variant, and the fix direction:
`references/holyd-recursion-call-frame.md`.

Known remaining edges (documented, not claimed): (1) a NAMED member whose type
is an anonymous struct (`struct outer { struct { int i1; } t; }` then
`x.t.i1`) fails — struct resolution is name-based and the anon inner struct
has no name; needs offset-based member resolution. (2) a wide string into a
`wchar_t[]` (4-byte element) packs bytes contiguously instead of one char per
cell. (3) anon bit-field between named fields in a brace initializer
misaligns the init value index. (4) compound literals with statement
expressions (`({ ... })`). (5) `__INTPTR_TYPE__`/`__INTPTR_MAX__`/`__SIZE_TYPE__`
and similar GCC predefined macros are undefined (only `__CHAR_BIT__` is
defined). (6) VLA typedefs (`typedef int c[i+2]`) and `_Complex`.
(7) function pointer passed as a parameter (see above).

Deprioritized (rare/legacy, not worth the parser risk): K&R function
definitions (`int f(x) int x; {...}`), nested function definitions, `asm
volatile`, `__builtin_*`, `extern inline`, compound literals with statement-
expressions, LTO, parenthesized declarators `int(return_3)(void)`, abstract
declarator casts `(unsigned long(*))0`. These are advanced-feature tests, not
fundamental C.

### Variadic functions were fully broken (three bugs, one feature — 2026-10-12)
`int f(int n, ...)` + `va_arg` failed three independent ways; all fixed (commit
`8a01e77`, v3-verified, core 247/247, selfhost 155/155, MIR 111/117):
1. **Parser discarded fixed params on `...`.** The param comma loop set
   `fn->n_params = 0` when it hit `...`, throwing away the already-parsed
   fixed params — so `f(int n, ...)` had 0 params and `n` never bound
   (`f(3,99)` returned 0). Fix: keep the fixed-param count; only set
   `is_variadic`.
2. **Codegen copied the wrong args into `wubu_va_args`.** The variadic
   prologue copied v1..v8 (starting at the first FIXED param), so `va_arg`
   read `n` instead of the first vararg. Fix: copy from `v{n_fixed+1}` so
   `wubu_va_args[0]` is the first variadic argument.
3. **Preprocessor registered function-like builtins as object macros.**
   `va_start`/`va_arg`/`va_end` were added with the literal name INCLUDING
   parens (`va_arg(ap, type)`) and `fn_like=0`, so the call site
   `va_arg(ap, int)` never matched. Fix: detect `(` in the builtin name,
   register `fn_like=1`, and split the parameter NAMES into `m.params[]` so
   the function-like expansion substitutes them (`va_arg(ap,int)` ->
   `wubu_va_args[ap++]`). The varargs model: `va_list`=int index,
   `va_start`=`(ap=0)`, `va_arg`=`wubu_va_args[ap++]`, and the variadic
   prologue copies the post-fixed args into the global `wubu_va_args[32]`.

## Pitfalls (additions for 2026-10-12 gauntlet wave)


- **modrm/disp width mismatch** (8086 driver, systemic): emit functions
  used `e16()` (16-bit displacement) with modrm bytes encoding mod=01
  (8-bit disp). Every slot load/store consumed an extra byte as a fake
  displacement, scrambling the instruction stream (`1+2 → 206 = 0xCE`).
  Fix: use `e8()` for 8-bit disp8 with modrm bytes that encode mod=01.
- **Shift opcode scrambling** in the DOS emulator (`wubu_dos_emu_alu.c`):
  `do_shift8`/`do_shift16` mapped SHL (/4) as right-shift, merged ROL+ROR,
  merged RCL+RCR, and dropped SAL (/6). Canonical 8086 mapping:
  /0=ROL /1=ROR /2=RCL /3=RCR /4=SHL /5=SHR /6=SAL /7=SAR.
- **CWD (0x99) sign-extension**: must check bit 15 of AX (`(int16_t)ax < 0`),
  NOT byte 7 (`(int8_t)(ax & 0xFF)`). The latter is CBW, not CWD.
  Broke `IDIV` for negative dividends.
- **IDIV vs DIV**: the 8086 driver must use `CWD` + `IDIV` for signed
  division, matching x86-64 and m68k backends. `xor dx,dx` + `DIV` is
  unsigned only.
- **wubu_fast_attn_decode_q8 normalization**: the Q8 attention decode path
  must divide by `sum_exp` and write to the output buffer, matching the F32
  path. Missing normalization causes values to explode at large context sizes.
- **PolarQuant angle normalization**: the encoder uses level-dependent theta
  mapping (full-circle for level 0, half-range for deeper levels). The decoder
  must match — a single mapping for all levels corrupts angle reconstruction
  beyond level 0.
- **CHECK THE REPO + SKILL LIBRARY BEFORE DOWNLOADING ANYTHING (user, 2026-08-04, stated sharply: "check our skill sets you were re-downloading things we already have this is disgusting").** When the driver space needed an 8086 interpreter and a RISC-V oracle, the session downloaded qemu-user-static + riscv binutils to /tmp — but the repo ALREADY had `src/runtime/wubu_dos_emu.c` (a 22/22-tested in-process 8086 interpreter, NO QEMU needed) and `~/opt/binutils-multiarch` ALREADY had the objdump oracle covering riscv/aarch64/arm/mips/ppc/sparc/s390/loongarch. Doctrine: (1) grep the repo for an existing interpreter/emulator/oracle BEFORE writing or downloading one — `find src -name '*emu*' -o -name '*interp*'`; (2) check `~/opt/` before `apt-get download`; (3) NO temporary-directory tools — everything lives in the repo `tools/` or `~/opt/`. The multiarch objdump extraction already lives at `~/opt/binutils-multiarch` (extract recipe: `cd /tmp && apt-get download binutils-multiarch && dpkg -x *.deb ~/opt/binutils-multiarch`).
- **The repo's in-process interpreters ARE the drivers' interpreters.** The 8086 driver (`wubu_isa_8086.c`, the x86 root) emits real 8086 bytes and runs them through `wubu_dos_emu.c` — its API is `create → load_com(data,size) → run(max_steps) → regs(&ax,…)`; result is AX, sign-extended from int16. The m68k driver carries its own interpreter (`wubu_m68k_interp.c`). A new ISA driver should FIRST look for an existing in-repo interpreter; only write a fresh one for ISAs with no in-repo emulator.
- **8086 conditional jumps are rel8 ONLY** (74/75/7C/7D/7F/7E/EB = one disp byte; the rel16 `0F 84` form is 386+, NOT valid on 8086). Only `JMP E9` is rel16. The patch pass must branch on this. Also: a .COM terminates with `INT 20h` (CD 20), NOT `ret` (C3) — `ret` pops garbage from the PSP area → the 2/33 battery symptom (`1+2` → 0xCE). Signed operands need IMUL/IDIV (F7 EB/FB), and `xor dx,dx` (31 D2) MUST precede `div bx` (F7 F3) because DIV divides DX:AX. Full verified 8086 table + diagnosis: `references/holyc-8086-driver-wip.md`.
- **A C enum name misspelling is a SILENT wrong constant, not a compile error.** `bitxor_ops[] = {{HC_TOK_CARET, HC_AST_XOR}}` used a name that doesn't exist in the enum (`HC_AST_BITXOR` is correct) → the parser emitted garbage AST kind 58 → `5^3` = 0 on EVERY driver. When a whole-expression result is uniformly wrong across all backends, suspect the parser/lowerer enum constant first — the drivers were all right.
- **Subtraction flags ≠ addition flags.** Reusing the ADD overflow formula with `~b+1` computes V=1 for `1-2` (no overflow) → signed LT/GT break on any ISA with flag-based branches. SUB/CMP need `V = (dst^src) & (dst^res) & 0x80000000`, C = borrow (`dst < src`).
- **Frame pointers mean NEGATIVE offsets, always.** Both the x86-64 driver (slots at `[rbp+off]`) and the first m68k draft (slots at `(A6 + off)`) had the same bug: the frame is allocated BELOW the pointer, so positive offsets write into the CALLER's stack → SIGSEGV at `leave; ret`/`unlk`. Symptom fingerprint: segfault on return, works for expressions with few vrs (frame small) and crashes with many.
- **The oracle verifies opcodes; the battery verifies programs.** objdump proves each byte decodes as intended; `make test_drivers` (33 exprs × every driver vs gcc values) proves the whole program runs. Run both; they catch disjoint bug classes.
- **Partial ABI support: GATE it, don't let it crash on what it can't
  handle.** When implementing a partial SysV ABI feature (e.g. struct
  return sret only for ≤8 bytes), the natural first draft is "let the
  larger sizes fall through to the legacy path" — but the legacy path is
  SILENTLY WRONG (stores 8 bytes, caller reads expecting full struct),
  which means the CALLER of a >8B-returning function will deliver a
  corrupt copy to the callee → SIGSEGV. **The correct discipline is to
  EXPLICITLY gate the new path AND refuse the cases it can't handle
  (e.g. `bool can_sret = ret_sz > 0 && ret_sz <= 8`)** so the legacy path
  is hit only when the legacy semantics are correct. For partial ABIs in
  general, ask: "for every input that bypasses my new path, does the
  legacy path produce a CORRECT (not just uncrashing) result?" If no, the
  new path must extend to cover those inputs before it ships — OR
  document them as a hard error in `hc_eval` rather than a silent wrong
  answer. The sret `(*p).a` debugging session (2026-08-13) caught this
  pattern: a 12-byte struct return crashed BECAUSE the legacy path's 8-byte
  store + 8-byte-only arg passing created an inconsistent ABI between
  caller and callee.
- **NEVER free the persistent data section in `wubu_holyd_eval`.** Module-level `I64 acc = 10;` lives there and MUST survive across evals for REPL state. `hc_gen_init` already saves/restores it. Freeing `gen.data` is the silent-garbage-return bug (fix B).
- **A bare trailing expression is a statement that needs a terminating `;`.** Wrapping `"1+2+3"` as `"{ 1+2+3 }"` leaves an EXPR_STMT with no `;`, and `parse_stmt`'s `expect(SEMI)` then fails immediately (hitting the `}`), so always append `;` unless the source already ends in `;`/`}`.
- Under a memory cap (`ulimit -v`), an OOM *looks* like SIGKILL (137) but may be a NULL-deref underneath. Reproduce under plain `gdb` (`gdb -batch -ex run -ex bt`) to see the true fault — the cap masks it.
- `hc_gen_init` preserves `symbols` for REPL persistence by `memset(gen,0,sizeof(*gen))` then restoring `symbols`/`functions`/`data`. Don't break that for the REPL; isolate resets to `hc_eval`.
- Don't add `sub rsp, N` sized to `stack_size` at prologue time (size unknown then). A fixed generous reservation (256 B = 32 I64 locals) is correct and simple for the test JIT.
- **Parser-feature fixes (designators, qualifiers, K&R, VLA-typedef) and the binary execution legs (ELF/PE/Mach-O/DOS loaders):** see `references/parser-feature-and-exec-legs.md`.

## Tailslayer DRAM-hedge — implicit `prefetchnta` before every load

Software-prefetch shim: emit `prefetchnta` before every JIT memory load so the
DRAM read overlaps tREFI refresh. The one real bug: compute `patch_pos` AFTER
emitting the 7-byte prefetch, not before. Full encodings table, the wiring map
(global IDENT read is INLINE `48 8B 05`, easy to miss), the `make test_hedge`
counter gate, the kernel worker-pool deadlock fix, and the honest "hedged pool
is SLOWER on non-contended host" benchmark:
`references/tailslayer-dram-hedge.md`.

## Function-pointer declarator parse (`int (*op)(params)=add;`) — 2026-08-13

The selfhost battery reached 78/78 partly by fixing `int (*op)(int,int)=add;
op(20,22)` (was returning 0). Two independent bugs:

1. **Parser: the `(*name)` LPAREN branch never set `is_func_ptr`.** The
   declarator parser checked `peek==LPAREN` after matching `(*`, but the next
   token was the identifier `op`, not another `(`, so it fell into the plain
   `*p` pointer path, then saw `(params)` and got misrouted into FUNC_DECL
   with a garbage name → `add` was never registered → `op` held a 0 address.
   Fix: when you see `(`, peek inside for `*`; if `(*name)` then consume
   `( * name )`, then check for `(params)` to set `is_func_ptr`. A clean
   three-way branch (`*p` / `(*name)(params)` / plain `name`) fixes it.
2. **Codegen: `resolve_var` searched only locals; when `n_locals==0` a bare
   function name (`add;`) emitted 0.** Add the function-table lookup to the
   `n_locals==0` branch of the IDENT read (it already existed in the
   `n_locals>0` `!found` branch). A function name used as a value resolves to
   its `gen->functions[i].func_ptr`.
3. **`fn->param_types` is `HCType**` (NULL after calloc) — it must be
   allocated** (`calloc(HC_MAX_PARAMS, sizeof(HCType*))`) before
   `fn->param_types[pi] = parse_type(p)` or you get a NULL-deref SIGSEGV in
   `hc_parse_decl`. This was the crash, not a parse-logic bug.

The battery's `run_isolated` takes a `Probe*` now and supports a `nonzero`
flag (for "function name as value returns a real address, not a specific
number"). Battery went 74→78 (added func call / func ptr assign / func ptr
self / bare-func-name-nonzero probes).

## THE LEXER pos-vs-token TRAP — systemic recurring root cause (2026-08-13)

This bit the session THREE times (sizeof paren, goto label lookahead, and
parse_cast's not-a-cast paren path). Memorize it: **when the current token is
`(`, `p->lex->pos` already points PAST it** (at the next char). So capturing
`saved = p->lex->pos` while token==`(` and later doing
`p->lex->pos = saved; hc_lex_next(...)` restores the lexer to the token AFTER
`(`, not to `(` — the restore lands on the wrong char, the parse silently
mis-tokenizes, `has_error=1` fires, and `hc_eval` returns 0 with NO codegen
DEBUG running (parse reached the construct, codegen never did).

Three distinct correct fixes, pick per context:
- **Do NOT backtrack.** After consuming `(`, just parse forward: if next is a
  type keyword → `parse_type`; else → `parse_expr; expect(RPAREN)`. Cleanest
  for `sizeof(x)` — no restore at all.
- **Capture the token/text BEFORE advancing.** For `ident:` label detection,
  save the `HCToken` struct + `pos`, advance, check for `:`, and on failure
  restore by **direct token assignment** (`p->lex->tok = saved_tok;
  p->lex->pos = saved_pos`) — NOT pos-restore + re-lex, which lands wrong.
- **Rewind one char to land on the `(`** (`p->lex->pos = saved_pos - 1`) and
  delegate to `parse_postfix`. This is the parse_cast not-a-cast fix: it
  parses `(expr)` as a primary AND applies trailing postfix so `(*p).a`
  keeps `.a`, while the caller's binop loop still applies `*4` to
  `(2+3)*4`. (Returning `parse_primary` drops the postfix; returning
  `parse_expr` + `expect(RPAREN)` double-consumes the `)`.) The TRAP here
  is that the *wrong* restore (`pos = saved_pos` instead of `saved_pos - 1`)
  silently parses `(2+3)*4` as `2+3)` plus a stray `*4`, so paren
  arithmetic regresses. Always re-verify paren battery probes
  (`paren`, `prec paren`, `2d sizeof row`) after touching parse_cast.

**Diagnosis recipe (the `(*p).a` instance, took 6 iterations):** when a
nested postfix is being orphaned (`.a` dropped, `->a` returning the wrong
member), `fprintf(stderr, "DBG restore: peek=%d text='%s'\n", peek(p),
p->lex->tok.text)` right after the restore + `hc_lex_next` shows EXACTLY
where the restore landed. If it shows `2` instead of `(`, the pos restore
is off. **Print the AST kind chain too** for the failing expr — kind=61
`HC_AST_DEREF` with no MEMBER child under it = parse-state bug; kind=9
`HC_AST_MEMBER` with the right child = codegen bug. The AST shape tells
you which side owns the bug without further debugging.

Triage fingerprint: `hc_eval` returns 0, parser `has_error=1`, but
`parse_stmt`/parse-construct DEBUG *does* print → parse-state bug, not codegen.

## `sizeof` + `switch` — two kernel-critical gaps (2026-08-13, battery 78→91)

The self-host battery went **78 → 91 probes, 91/91 PASS** by adding `sizeof`
and `switch`, both previously broken (sizeof lexed as garbage → returned 0;
switch was unparsed → returned 0). Both are essential for compiling the
kernel (every driver uses `sizeof(struct…)` and `switch(dispatch)`).

### sizeof — three forms, one enum-slot trick
- `holyc_types.h`: **reused the `HC_KW_UNUSED` enum slot** as `HC_KW_SIZEOF`
  (no enum-value churn — nothing referenced the dummy), plus `HC_AST_SIZEOF`
  (reuses the `type` field the struct/cast work already populates).
- `holyc_lexer.c`: `"sizeof"` keyword.
- `holyc_parse.c` `parse_primary`: three forms — `sizeof(type)` (peek after
  `(` is a type keyword → `parse_type`), `sizeof(expr)` (paren), `sizeof expr`.
- `holyc_codegen_expr.c`: `HC_AST_SIZEOF` emits `mov rax, imm64` from
  `hc_type_size(type)` or `expr_static_type(child)`.

**THE PAREN-BACKTRACK PITFALL (real bug, cost most of the session):**
my first `sizeof(x)` paren path captured `saved = p->lex->pos`, consumed `(`,
decided it wasn't a type, and did `p->lex->pos = saved; hc_lex_next(...)` to
re-parse the paren. But `saved` was captured **while the current token was
already `(`, so `lex->pos` points PAST the `(`** (at the inner expr) — the
restore lands on the wrong char, the block parse then fails with
`has_error=1` BEFORE codegen runs, and `hc_eval` returns 0 with no codegen
DEBUG firing. **Fix: do NOT backtrack mid-token.** After consuming `(`:
- if next is a type keyword → `parse_type`, `expect(RPAREN)`
- else → `n->child = parse_expr(p); expect(RPAREN); return n`

Do NOT route the paren-expr through `parse_cast` either — its
cast-disambiguation path consumes the closing `)` itself and then expects a
SECOND `)` (double-consume → error). The inline `parse_expr; expect(RPAREN)`
avoids both problems. Triage fingerprint: `hc_eval` returns 0, parser
`has_error=1`, but `parse_stmt`/`parse sizeof` DEBUG *does* print — parse
reached the construct, codegen never ran → a parse-state bug, not codegen.

Verified (gcc-agreed): sizeof(int)=4, char=1, struct{a;b;}=8, array=12,
member=4, nested `struct Q{P p; int b;}`=8 (4+4, no padding needed for
4-byte-aligned members). **If the compiler's sizeof disagrees with your
expectation, run gcc FIRST — the test expectation may be the wrong one.**

### switch — linear compare+je dispatch, break targets AFTER the pop
- AST: `HC_AST_SWITCH` (cond=switch expr, body=block of `HC_AST_CASE` nodes),
  `HC_AST_CASE` (cond=case value expr, NULL=default; body=stmts block).
- Parse in `parse_stmt`: `switch(expr){ case V: stmts … default: stmts }` —
  statements after a `case`/`default` label attach to the current CASE's body.
- Codegen (`holyc_codegen_stmt.c` `HC_AST_SWITCH`):
  1. `gen_expr(cond)` → rax; `push rax` (`[rsp]` = switch value).
  2. Dispatch chain per case: `gen case value → rax; mov rdi,rax; mov
     rax,[rsp]; cmp rdi,rax; je <body>` — case value moved to rdi BEFORE the
     switch value is reloaded into rax, so a full-expression case value
     (e.g. `case 1+1`) works.
  3. no-match `jmp` → default body (or end if none).
  4. Case bodies emitted contiguously → **fallthrough is natural, free**.
  5. `end:` = `add rsp, 8` (pop switch value); **break targets AFTER the pop**
     so every exit path (fallthrough AND break) balances rsp.
- `HC_AST_CASE` standalone emits nothing (only valid inside a switch).
- New emitters: `emit_push_rax/pop_rax/mov_rax_mem_rsp/cmp_rax_rdi/add_rsp_8`.

Verified: case match, default, no-match ± default, fallthrough, expression
cases, switch-in-function, multi-statement cases. Note: **"no-match,
no-default → returns the var's initialized value" is CORRECT C semantics**
(skip the whole body), not a bug.

**Honest remainder (documented, not claimed):** no duplicate-case detection,
linear O(n) dispatch (no jump-table optimization), no VLA sizeof, no
struct-by-value >8B return, no struct-by-value >8B arg. (`f().a` on a
struct-return call IS now closed — see the sret/`f().a` section below.)

Battery additions: 7 `sizeof` + 6 `switch` probes. Wired a `test_battery`
target (mirror of `test_holyc` recipe) into `test_high_bear`. Doc:
`docs/compendium/02-architecture/holyc-sizeof-switch.md`. Gates: battery
91/91, test_holyc 84/84, test_holyc_agi 11/11.

## Struct-by-value return (≤8 bytes) — rep movsb sret (2026-08-13, battery 108→112)

Battery **108 → 112 probes, 112/112 PASS** by closing the ≤8-byte slice of
struct-by-value return (the kernel's most common struct idiom: a couple of
int fields). The fix is a small memory-return ABI: callee writes to a
.data slot, returns `rax = &slot`; caller does `rep movsb` from `&slot` to
the LHS.

**Callee RETURN path (`HC_AST_RETURN`, struct-typed child + local IDENT
+ `ret_sz <= 8`):**
1. Reserve a 16-byte-aligned slot in `.data` (sized to `ret_sz`).
2. `lea rsi, [rbp - off]` — src is the local struct.
3. `mov rdi, slot_addr; mov rcx, ret_sz; rep movsb` — memcpy in.
4. `mov rax, slot_addr` — return value = pointer to struct copy.
5. Emit epilogue.

**Caller ASSIGN path (`HC_AST_ASSIGN`, struct LHS + FUNC_CALL RHS):**
1. `gen_expr(FUNC_CALL)` returns `rax = &slot` (from the callee's RETURN).
2. `push rax`; `lea rax, [&lhs]` (rbp-local or rip-global via
   `global_patches[]`); `pop rsi`; `xchg rax, rdi` → `rdi=&lhs`,
   `rsi=&slot`, `rax=&slot` (preserved for chained rvalue).
3. `mov rcx, lhs_sz; rep movsb` → `&lhs <- &slot` byte-exact.

Added `emit_rep_movsb` (`F3 48 A4`); exposed `resolve_var` across the
codegen submodules (was `static` in expr.c).

**The size-≤8 gate is the lesson — see "Partial ABI support" pitfall in
the Pitfalls section.** Without the gate, the >8B case fell into the
legacy 8-byte-store path AND the legacy 8-byte-arg-passing path on the
caller side, producing a caller/callee ABI mismatch that crashed on every
>8B struct return. Gating the new path on `ret_sz <= 8` and letting the
>8B case fall through to a path the legacy code already gets wrong
*the same way* on both sides makes the partial ABI consistent. For >8B,
full SysV sret (hidden first-arg pointer + callee write-through + same
arg-passing logic for >8B params) is the proper fix and is documented as
honest remainder.

Battery additions: 4 sret probes (`ret struct a` / `b` / `single field` /
`sum`). Doc: `docs/compendium/02-architecture/holyc-sizeof-switch.md`.

## `goto` + multi-dim arrays + array decay + nested pointer access (2026-08-13, battery 78→108)

Battery went **78 → 108 probes, 108/108 PASS** by closing four more
kernel-critical gaps before the sret wave (which brought it to 112). All
four are essential for compiling the kernel (every driver's error path
uses `goto fail;`, matrices use 2D arrays, every linked list uses
`p->next->value`).

### goto — label patch registry
- AST: `HC_AST_GOTO` (ident=label name, emits a jmp placeholder) +
  `HC_AST_LABEL` (ident=label name, records current code position and patches
  any pending forward gotos).
- `HCGen` gains a label registry: `{name, offset} labels[128]` +
  `{patch_pos, label_idx} label_patches[512]`. `hc_gen_init` memsets the
  whole gen, so the registry is naturally scoped per `hc_eval` (labels are
  function-local). Backward gotos patch immediately (offset already known);
  forward gotos record a patch resolved when the label is placed.
- Label detection needs a 2-token lookahead: `ident:` at statement position.
  **Capture the `HCToken` struct + pos BEFORE advancing; restore by direct
  token assignment** on the not-a-label path (pos-restore lands wrong — the
  same lexer trap).

### Multi-dimensional arrays — RIGHTMOST dim is INNERMOST
`int a[2][3]` must build `ARRAY(ARRAY(int,3),2)` (2 rows of 3), NOT
`ARRAY(ARRAY(int,2),3)`. The array declarator must **collect all `[N]` sizes
then build the type innermost→outermost** (iterate `dims` from `n_dims-1`
down to 0), NOT stack them in source order. Source-order stacking reversed
the dims → `sizeof a` was wrong. Verified: `sizeof a`=24, `sizeof a[0]`=12
(gcc agrees).
- **Nested INDEX scale via `expr_static_type` on the base.** The outer
  `a[0][0]` INDEX's `node->left` is an inner INDEX node whose `.type` is NULL
  (not an IDENT), so the scale fell to 1 instead of the element size. Fix:
  when `node->left->type` is absent, resolve via `expr_static_type` (handles
  nested INDEX/IDENT/MEMBER). Apply in BOTH `gen_expr`'s INDEX case AND
  `emit_lvalue_addr`/`emit_base_addr`'s INDEX case.

### Array-to-pointer decay — VAR_DECL init
`int* p = a;` / `int* p = a[0];` must store the ADDRESS of the array (or
row), not load its first element. `gen_expr(init)` loads the value — detect
the case (declared type is PTR + init static type is ARRAY) and emit
`emit_base_addr` instead. Apply in BOTH the module-level (global) and
local VAR_DECL init paths. **Requires exporting `expr_static_type` and
`emit_base_addr` across codegen submodules** (they were `static` in
`holyc_codegen_expr.c`; add non-static declarations to
`holyc_codegen_internal.h` and drop `static`).

### Nested pointer / deref member access
`p->a`, `(*p).a`, `q.p->a` (arrow through a pointer member), and WRITES to
all of them. Two root causes:
1. **`emit_base_addr` on a nested composite must dispatch on static type:**
   pointer → LOAD the value (the pointer IS the address, e.g. `q.p->a` where
   `q.p` is a `struct P*` member — computing `&q.p` is wrong); struct/array →
   compute the ADDRESS (recurse `emit_lvalue_addr`).
2. **`(*p).a` parse: parse_cast's not-a-cast paren path orphaned trailing
   postfix.** Fix: rewind to the `(` (`p->lex->pos = saved_pos - 1`) and
   delegate to `parse_postfix`, which parses `(expr)` as a primary AND
   applies `.a`. The caller's binop loop still applies `*4` to `(2+3)*4`.
   Verify paren arithmetic (battery `paren`, `prec paren`) still passes
   after any parse_cast change — this fix preserved it, but a wrong variant
   (parse_primary, or parse_expr+expect) broke it first.

### `f().a` — member access on a struct-return call (SHIPPED 2026-08-13, battery 112→117)

The sibling gap to nested pointer access above: MEMBER on a FUNC_CALL that
returns a struct used to treat `rax` as the scalar value (the first 8 bytes
of the struct, taken literally), NOT as a pointer to the returned struct.
After the ≤8B sret fix the callee sets `rax = &slot`, but MEMBER on the raw
call result couldn't resolve the callee's return type so it returned the
slot *address* (a big 64-bit pointer value, e.g. `110068974031296` instead
of 42). Closed with two small pieces:

1. **`HCFunction` gains a `ret_type` field** (`holyc_types.h`), recorded
   from the FUNC_DECL's declared return type (`node->type`) when the
   function is compiled (in `HC_AST_FUNC_DECL` codegen, alongside
   `func_ptr`/`n_params`).
2. **`expr_static_type` gains a FUNC_CALL case** that looks up the named
   callee's `ret_type` in `gen->functions` (match on `node->callee->ident`).

With the static type resolvable, the EXISTING MEMBER path works unchanged:
`emit_base_addr(FUNC_CALL)` evaluates the call → `rax = &slot`, then
`emit_sized_load_rax_off(off, msz)` loads `[rax + off]` = the member. No
new dispatch logic needed in MEMBER — the missing piece was purely
`expr_static_type(FUNC_CALL)`. (Precondition: the callee must already be in
`gen->functions` with `ret_type` set, which it is for any function declared
earlier in the same eval.)

Triage fingerprint when a struct-return call used as a MEMBER base returns
the *address*: `expr_static_type(FUNC_CALL)` returns NULL → the MEMBER
member-lookup loop is skipped and `rax` keeps the base (slot) pointer. Check
that the FUNC_CALL case exists AND that the callee's `ret_type` was actually
recorded (a function returning a type that isn't a struct/union will resolve
to a non-container type and MEMBER will skip the loop too — that's correct).

Verified: `f().a`, `f().b`, `f().a+f().b`, `f(g().a)` (nested call, member
as an arg), `f().a*f().b`. Battery additions: 5 `call member *` probes.
Doc: `docs/compendium/02-architecture/holyc-sizeof-switch.md` (removed
`f().a` from honest remainder).

**Honest remainder (documented, not claimed):** **struct-by-value RETURN is
partially supported — ≤8 bytes via rep movsb sret; >8 bytes need full
SysV ABI.** That ABI requires (a) callee RETURN writes through a hidden
sret first-arg pointer the caller passed in, AND (b) caller-side ARG
passing for structs >8 bytes also uses a hidden pointer (or stack-memcpy).
The partial fix is gated on `ret_sz <= 8` so it NEVER *introduces* a crash
on the cases it can't handle — for >8B returns the legacy 8-byte store is
used silently (bytes past offset 8 lost, not crash). Workaround for the
>8B case: `struct S r; r=f();` and read `r.a` — assignment DOES land the
correct first 8 bytes. The class of gap is **"calls into a >8B-returning
function still crash because arg passing only delivers 8 bytes"** —
documented in `docs/compendium/02-architecture/holyc-sizeof-switch.md`.
**Next step to close this fully: implement the hidden sret first-arg pointer
contract on BOTH sides of the call** (a non-trivial ABI change spanning
parse/codegen/ABI runtime).
Gates: battery 112/112, test_holyc 84/84, test_holyc_agi 11/11.

## FULL SysV sret — >8B struct return + arg passing (2026-08-13, battery 117→130)

Closed the >8B struct-by-value gap ENTIRELY (return AND arg passing).
Battery **117 → 130 probes, 130/130 PASS**. Four real fixes — three were
subtle enough to cost real debugging time:

1. **Local struct slots MUST be sized to the struct AND the offset must
   grow by the slot size.** `struct S{int a;int b;int c;}` local (12B)
   got an 8-byte slot, so writing `s.c` at offset 8 stomped the saved rbp
   at [rbp+0] → corrupted frame → crash on leave/ret. The natural first
   fix (round the reservation up) was WRONG because the offset formula
   stayed `offset = stack_size + 8` — a 12-byte struct at offset 8 still
   occupies [rbp-8..rbp+3], hitting [rbp+0]. **Fix both: `slot =
   (size+7)&~7; offset = stack_size + slot; stack_size += slot;`.**
   Triage fingerprint: member write past offset 8 of a local struct
   crashes on function RETURN (leave/ret), not at the write itself.

2. **`long long` = TWO `HC_KW_I64` tokens.** `long long x;` lexes as two
   `long` tokens; parse_type consumed one and the second broke the type
   (`sizeof(long long)` returned 0, struct with ll members got size 0).
   Fix: after consuming I64, optionally consume a second I64 (both 64-bit
   on x86-64). Same pattern applies to any multi-keyword type.

3. **Struct-by-value ARG passing >8B by address + a SECOND prologue pass.**
   The call site emits the struct's ADDRESS for >8B struct args (not the
   packed value). The callee param prologue must deref-copy it into the
   param slot — but doing that INSIDE the register-store loop CLOBBERS the
   later param registers (param 0's deref-copy does `mov rsi,[rdi]` before
   param 1's `mov [rbp-off1], rsi` has run). **Do the deref-copy in a
   SECOND loop after ALL registers are stored.** Also size param slots to
   the struct, and record the param's `.type` in the symbol table (it was
   NULL → member loads defaulted to 8 bytes → `x.a` read the packed qword).

The return path just drops the `ret_sz <= 8` gate once slots are sized
correctly — the gate existed only because the local slot overflow made
>8B look unsupported. Honest caveat: this ABI is internally consistent
within our compiler but does NOT match gcc's exact register convention
for interop with separately compiled C (irrelevant for self-hosting).

Battery additions: 13 `full SysV sret` probes. Doc:
`docs/compendium/02-architecture/holyc-sizeof-switch.md`.

## Runtime correctness wave — 8 bug clusters (2026-08-13, battery 130→147)

The battery went 130→147 by closing REAL RUNTIME bugs, not just C11
construct coverage. These are the kinds of bugs that make compiled kernel
code silently corrupt state. Memorize these root causes:

1. **Function bodies can't see module globals unless you PRESERVE them.**
   The FUNC_DECL prologue `memset(&gen->symbols, 0, ...)` wiped the whole
   symbol table, so `int g=7; int f(){return g;}` read a stack slot
   (implicit local) → 0. Fix: copy the `stack_offset <= 0` entries
   (globals) into the fresh table before compiling the body.
2. **Function-body global RIP fixups are NEVER applied by the main loop.**
   Each function copies to its OWN exec buffer; `hc_eval`'s patch loop only
   fixes the main code+data buffer. So a global load/store inside a
   function referenced the wrong address → garbage. Fix: `HCFunction`
   records its own `global_patches[]` (captured after the restore-memcpy,
   iterating from the saved `n_global_patches`); `hc_eval` patches each
   function exec copy AFTER the main exec+data base is known:
   `disp32 = data_base + go - (func_ptr + patch_pos + 4)`. CRITICAL: roll
   back `gen->n_global_patches` after each body so a function's patches
   (whose positions are relative to its OWN buffer) never leak into the
   main-code patch loop — or the main loop will write garbage into the
   main exec at the function's positions.
3. **Pointer `++`/`--` must scale by element size AND use 64-bit add.**
   `p++` adding 1 (not `sizeof(int)`) is wrong, but the WRONG fix is the
   32-bit `add eax,imm8` (`83 C0 04`) — it ZEROES the pointer's upper 32
   bits → SIGSEGV. Correct: `48 83 C0 imm8` (add rax,imm8) for ++ and
   `48 83 E8 imm8` (sub rax,imm8) for --. Scalar keeps `inc rax`(48 FF C0)
   / `dec rax`(48 FF C8). Extract to a helper (`emit_incdec_rax`) — you'll
   use it in all 4 Inc/Dec cases (PRE/POST × global/local).
4. **Compound-assign `x op= y` must park `left` on the STACK, not `rdi`.**
   The classic binop dance saves left in rdi, but if the RHS is an array
   INDEX (`s += a[i]`), the INDEX codegen uses `rdi` internally for the
   base address → left destroyed → garbage. Push/pop survives any RHS
   register usage.
5. **`&expr` only handled IDENT children.** `&s.b`, `&a[i]`, `&*p`,
   `&p->x` emitted 0. Route non-IDENT lvalues to `emit_lvalue_addr`.
6. **`*p` must load sized by the pointee type.** `int* p; *p` loading 8
   bytes (packed qword) instead of 4 is a silent corruption. Use
   `expr_static_type(DEREF)` → pointee type → `mov eax,[rax]` for int,
   `movzx eax,byte/word [rax]` for char/short, `mov rax,[rax]` for 8B.
7. **libc string/memory externs must be registered** or `strlen`/`strcmp`/
   `memcpy`/`memset`/`memcmp`/`strcpy` hit the unresolved trap → crash.
   Add real host wrappers + register in `hc_register_holyc_runtime`.
8. **void functions leave rax undefined.** `void f(){} f()` returned a
   stale address. Emit `xor eax,eax` (31 C0) before the epilogue when the
   function's return type is void.

Also this wave: `sizeof(long long)` needed `long long` = two `HC_KW_I64`
tokens handled in parse_type (consume the optional second `long`).

## Multi-arg calls + function-pointer struct members (2026-08-13, battery 147→155)

Battery went 147→155. Four more gaps — the key ones:

1. **SysV stack args (i≥6) are never read by the callee's param prologue.**
   The register-arg switch (rdi..r9, i=0..5) has no default case, so args
   7+ (which the caller pushed) were silently dropped. Fix: default case
   reads arg i from `[rbp + 16 + (i-6)*8]` (rbp+8=return addr, rbp+16=arg6)
   into rax, stores to the local slot. Triage: a function with 7+ args
   drops/garble the 6th+ arg.
2. **Non-IDENT callees trap.** FUNC_CALL only resolved `IDENT` callees;
   `s.fn(3,4)`, `p->fn(...)`, `(*fp)(...)`, `arr[i].fn(...)` hit the
   unresolved trap → 0. Fix: evaluate the function-pointer expression FIRST
   and push it — arg setup clobbers rdi/rsi for INDEX/MEMBER bases, so the
   callee value MUST be parked before args are placed. Pop into rax right
   before `call rax`.
3. **Function-pointer struct members (`int (*fn)(int,int);`) didn't
   parse** — "expected member name", because the name is inside `(*...)`
   so after parse_type the next token is `(`. Fix: the struct member loop
   detects `(*`, builds a PTR(FUNC(...)) type, consumes `)` + `(params)`.
4. **Struct trailing padding.** sizeof `{int (*fn)(int,int); int n;}` was
   12; gcc gives 16 (struct aligns to 8 via the pointer member). Fix:
   after the member loop, round `t->size` up to a multiple of `t->align`.

Battery additions: 8 `multi-arg / fn-ptr member` probes.

## THE SELF-HOSTING BATTERY — enumerate every gap, then fix (2026-08-12)

`tools/selfhost_battery.c` is a **crash-proof differential enumerator**: ~74 C11 constructs our kernel+desktop need, each run in a forked child so a crash isolates without killing the run. It is the "find all the bugs by knowing where we aren't" engine. It took the compiler from **44/74 PASS to 74/74 PASS** in one session. Build/run:

```bash
gcc -O0 -g -Isrc/compiler -Isrc/jit src/jit/*.c src/runtime/wubu_spawn.c \
  src/compiler/holyc_lexer.c holyc_parse.c holyc_parse_ast.c holyc_codegen.c \
  holyc_codegen_emit.c holyc_codegen_expr.c holyc_codegen_stmt.c \
  holyc_codegen_api.c holyc_runtime.c wubu_preproc.c tools/selfhost_battery.c \
  -o build/selfhost_battery -ldl
build/selfhost_battery   # PASS/WRONG/CRASH counts
```
It reports PASS (correct), WRONG (ran but bad value = codegen/parser bug), CRASH (child died). A **WRONG expected value in the battery is also a finding** — verify against gcc before blaming the compiler.

### What was broken (all real, none stubs) — the gap clusters

1. **ASSIGN + all compound-assigns crashed on module-level globals.** `x=42` / `x+=1` where `x` is a data-section global (negative stack_offset) emitted `mov [rbp-off]` unconditionally → wrote to a garbage high stack slot → heap corruption → SIGSEGV in `hc_eval`'s `free()`. Fix: shared `resolve_var`/`emit_var_load`/`emit_var_store` dispatch on `off<=0` to the RIP-relative `emit_global_{load,store}_rax` (the same fix Inc/Dec/`&x` already had).
2. **6 compound ops had no parser case.** `parse_assign` only mapped `= += -= *= /=`; `%= <<= >>= &= |= ^=` fell to `default: return left` (never parsed as assignment → wrong result). Add all 6.
3. **6 compound ops had no emitter.** `emit_mod/shl/shr/and/or/xor_rax_rdi` didn't exist. MOD = cqo;idiv;mov rax,rdx. SHL/SHR must move count to `rcx`/`cl` first.
4. **char literal:** parser read `tok.int_val` (only set for INT); the scanner puts the decoded char in `tok.str_val[0]`. Read `str_val[0]` into both `int_val` and `str_val`. **string literal:** parser copied `tok.text` (raw span) not `tok.str_val` (decoded, escapes handled).
5. **float→int cast was a no-op** — `(I64)3.14` emitted the raw F64 bit pattern. Add `emit_cvt_f64_to_i64` / `emit_cvt_i64_to_f64`. **CRITICAL ENCODING QUIRK: `movq xmm0,rax` (48 0F 6E C0) silently NO-OPs in the JIT and leaves xmm0 zeroed** → cvttsd2si always returns 0. The reliable pattern is a stack round-trip: `push rax; movsd xmm0,[rsp]; add rsp,8; cvttsd2si rax,xmm0` (verified against gcc's `F2 48 0F 2C C0`). Same for int→float.
6. **`for(int i=0;...)` didn't parse** — `parse_expr` on the init fails (a type keyword isn't an expression). Route a type-keyword-start init to `hc_parse_decl`. **`do while` had no parser case at all** (lexed `HC_KW_DO` but `parse_stmt` never matched it).
7. **Self-recursion crashed** — `fib(n-1)` inside `fib()` trapped as unresolved because fib isn't registered in `gen->functions` until after its body is compiled. Fix: `gen.current_function` + `self_call_patches[]`; a call matching the function being defined emits `call rel32` placeholder, patched to `exec+0` after the body is copied (disp32 = `-(pos+5)`).
8. **ASan-discovered latent heap overflow (HIGH VALUE — probably caused many mystery crashes):** `hc_eval`'s `"{ %s }"` wrap buffer was `malloc(len+3)` but needs `len+5` (2 braces + 2 spaces + NUL). Every multi-statement eval overflowed the heap by 2 bytes, silently corrupting malloc metadata → INTERMITTENT crashes in unrelated later allocations. **When hunting flaky segfaults, build with `-fsanitize=address` (LD_PRELOAD libasan) first.**
9. **No struct type registry** — `struct S{...}` defined members but `struct S x;` built a fresh EMPTY struct with the same tag, so `s.a` resolved no offset → read 0. Add a named-type registry to `HCParser`. **CRITICAL: the reference lookup must NOT `return t` early — it skips the trailing `while(*)` pointer loop**, so `struct S* p;` never consumed the `*`. Use `goto struct_done` to fall through.
10. **No array declarators** — `int x[3]` left `[3]` unparsed → `x` degraded to scalar. Parse `name[N]` into `HC_TYPE_ARRAY`.
11. **ASSIGN/compound only handled IDENT targets** — `x[0]=42`, `s.a=42`, `*p=42` were silently dropped (returned 0). Fix: `emit_lvalue_addr` (computes target address for IDENT/INDEX/MEMBER/ARROW/DEREF) + `emit_base_addr` (base decay). **A struct/array IDENT base decays to its ADDRESS (lea), not its loaded value.** `emit_base_addr` recurses into `emit_lvalue_addr` for nested bases (`q.p.x`).
12. **Array-to-pointer decay missing in the IDENT load path** — `x+1` loaded x's value, not its address. An ARRAY ident yields `&x[0]`. Then **pointer arithmetic scales the index by the element size** (`x+1` = `&x[1]`, not `&x[0]+1`): `imul rdi,rdi,imm8`.
13. **Symbol table had an unused `type` field** — populate it from `VAR_DECL` and resolve via `resolve_var_type`/`expr_static_type` (walks IDENT/MEMBER/ARROW/INDEX/DEREF) so nested/typed access works even though the parser doesn't attach types to nodes.

### The preprocessor (final 3 gaps)

Real kernel source is full of `#define`; the lexer had no `#`. Added `src/compiler/wubu_preproc.c/.h`: object macros + function-like macros (param substitution), strips `#include/#ifdef/#endif`. `hc_eval` preprocesses before lexing (malloc'd buffer, freed on EVERY return path incl. the block-wrap and early-error paths). **Wiring requirement: every link recipe that compiles `holyc_codegen_api.c` must now ALSO carry `wubu_preproc.c`** — `mk/tests.mk` (replace-all) + `COMP_OBJS` in `mk/objects.mk`.

### Cast test was asserting the bug
`test_holyc` asserted `(I64)3.14 == 4614253070214989087LL` (the raw bit pattern). After the cast fix the correct answer is `3`. Update the test to assert correct C semantics, don't "fix" the compiler back to the bug.

**Final gate after this session:** battery 74/74, test_holyc 84/84, test_holyd 33/32, test_drivers 33/33, test_holyc_agi 11/11, full suite 215/215 — all green.


## MIR-evaluator correctness — always-on rules

The full bug-class playbook (shadowing, type fall-through, float recognition,
pointer-arithmetic node-scale, nested char-array string init, the recursion
call-frame architecture, lexer/parser additions, gauntlet_runner gotchas,
deferred rabbit-holes) lives in **`references/mir-eval-correctness.md`** —
load it when debugging wrong-result / crash bugs in `holyd_mir_eval.c`,
`wubu_mir_interp.c`, or the gauntlet. The always-on essentials:

- Cell model: all values are 8-byte cells; scalar pointer scale 8, char/u8
  byte-packed scale 1. Verify expected values with gcc as the oracle first.
- Diagnostic: scalar works but array/struct element breaks -> the type is
  resolved by a different code path for the compound node; grep the resolver
  for the missing node kind.
- Var-NAME lookups (type/stride/flag) must search the var table from the END
  (most-recent wins) or a shadowing local loses to a same-named global.
- `mir_node_ptr_scale` resolves a pointer operand from ANY expression
  (arithmetic/ternary/call/deref-of-ptr-to-ptr); `*p` of a scalar pointer is a
  VALUE, not a pointer.
- Keep I64/U64 cases separate from BOOL in type switches (no fall-through).
- 1-D `char[]="..."` is byte-packed (stride 1); NESTED `char[N][M]` is
  cell-per-char (stride 8).
- `test_single`/`gauntlet_runner` run the x86-64 JIT, not the interpreter;
  interp-only changes need a throwaway interp binary to validate (recipe in the
  reference).

## Infinite loops, crashes, and diagnostics

- A parse "hang" is usually a loop that calls `parse_type()` on a token it does
  not consume. Give every such loop a progress guard (compare `p->lex->pos`
  before/after and advance on no progress); do not try to fix it by adding cases.
- **Get a backtrace even when `gdb -p` is blocked** (`ptrace_scope=1`, WSL). Run
  the program under gdb and interrupt it from a Python timer:
  `threading.Thread(target=… gdb.post_event(lambda: gdb.execute("interrupt")))`
  with `gdb -batch -x timer.py -ex run -ex 'bt 12'`. This found the K&R loop in
  minutes after hours of bisecting.
- `parse_type()` must not recurse on a token the switch did not consume. Gate the
  multi-word-type fold on `p->lex->pos != entry_pos`, or a missing case (e.g.
  `void`/`HD_KW_I0`) turns into stack exhaustion, which presents as SIGSEGV not a
  hang.
- Multi-word specifiers need explicit folding: the lexer maps `signed`->I32 and
  `unsigned`->U32, so `signed char` arrives as two keywords.
- `parse_cast` has its OWN list of tokens that can start a cast, separate from
  `parse_type`. It must include `const`, `volatile` and `void`: omitting them made
  `(volatile unsigned short*)0x7f14` parse as a parenthesised expression and fail
  at the base type. Fixing this alone moved the gauntlet 59.3% -> 62.0%.
- The gauntlet harness must be able to dump the exact source it ran
  (`HD_DIAG=2` -> `/tmp/failcases/<name>.c`). Extracting a test by name from a
  suite file repeatedly produced text that did not match what executed, which
  sends you debugging a construct the harness never sees.
- Classification work: make the diagnostic carry the offending token text
  (`expected token 85, got 80 ('{')`). A count of numeric messages is unusable.
- Gauntlet variance comes from TIMEOUTS, not load. Once no source hangs, repeated
  runs are byte-identical (three runs gave 2031/210/427 exactly) and the noise
  band is 0, so a single run is enough to judge a change. While hangs remain the
  band can exceed 60 passes and single-run comparisons mean nothing.
- `HD_DIAG=1` on the gauntlet writes a ~2 GB log; redirect to scratch and delete
  it after classification.
- `tools/compile_diag` must run `wubu_preprocess()` first. Parsing raw text
  produces phantom `#include` diagnostics.
- Use `compile_diag <file> --dump-pp` to see the text the parser actually reads.
  Diagnostic line numbers are preprocessed line numbers, so without the dump you
  will read the wrong source line. Do NOT build a standalone preprocessor
  harness: a binary linking only `wubu_preproc.c` crashes, while the same call
  inside the full front end works.
- The 4,921-source extracted corpus measures **hang/crash safety** well and
  parser correctness poorly: many entries are statement fragments that open with
  `{`. Never rank diagnostics on it.
- Corpus/build plumbing (`.PHONY` test targets, mangled suite sources, parameter
  caps, noise band): `references/gauntlet-measurement.md`.
- Full details in `references/parser-hang-and-diagnostics.md`.
