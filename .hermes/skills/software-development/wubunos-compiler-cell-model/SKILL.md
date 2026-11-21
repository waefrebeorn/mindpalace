---
name: wubunos-compiler-cell-model
description: Use when debugging WuBuNOS byte/stride/cell bugs.
---

# WuBuNOS compiler cell model

The WuBuNOS (HolyD) memory model allocates **1 cell = 8 bytes per element**, even for `char`/`int`. But C semantics need byte-addressable char and 4-byte int. This creates recurring stride/layout bugs. Load this before touching array indexing, pointer arithmetic, string handling, or sizeof.

## The core tension
- `char[8]` is allocated as **1 cell** (8 bytes) but C `sizeof` is 8 (bytes) — so byte-packed.
- `int[4]` is 4 cells (32 bytes) but C `sizeof` is 16 (4-byte ints). Allocation uses cells.
- A `char*` strides **1 byte**; an `int*` strides **8 bytes** (1 cell); a `char[]` array element strides **1 byte** (byte-packed).
- 2D char array `char n[2][6]`: string-init wants rows byte-packed (6 bytes), explicit-init `{{72,73,0}}` wants cell-strided rows (8 bytes) — SAME TYPE, conflicting layouts. Open architectural gap; do NOT assume one stride works for both.

## Where each stride lives (holyd_mir_eval.c)
- `mir_index_stride(g, n)` (~858): stride for `base[idx]`. char POINTER/ARRAY → 1, char*[] inner → 1, 2D char inner → 1, else 8. Walks to root IDENT.
- Pointer arithmetic `p+i` ptr_scale (~2711): resolves `ltype` from AST type OR var table (IDENTs often have no AST type). char*/unsigned char* → 1, else 8.
- INDEX char_elem byte-load (~3886): `n->type` I8/U8, or walk base IDENT, or INDEX/DEREF base walking to base IDENT (char*[] / 2D char).
- DEREF char_load (~3946): `*p` byte-loads when pointee I8/U8. Handles IDENT, ADD (`p[i]`), INDEX (`*s[i]` where s is char*[]) children.
- String literal gen (~3747): byte-packs via `wubu_mir_store8`, returns byte offset.
- char-array-from-string copy (~1665): byte-strided (stride 1), `wubu_mir_store8`.
- inc/dec PRE/POST (~2477/2551): IDENT path scales char* by 1, int* by 8; non-IDENT (INDEX/DEREF/MEMBER) via `mir_lvalue_addr` + load/add/store. Inc/dec through a non-IDENT lvalue (`a[i]++`, `++*p`, `s.x--`) was a silent no-op (returned the old value, stored nothing) until the general `mir_lvalue_addr` path was added — always handle INDEX/DEREF/MEMBER, not just IDENT.
- **Two-calls-to-same-function recursion** (`fib(n-1)+fib(n-2)`): a codegen bug in the x86 internal-call save/restore, NOT a stride/MIR bug (MIR is correct). See skill `wubunos-isa-call-conventions` → references/x86-64-jit-bug-fixes.md Bug #15.
- `~0u > 5` returned 0: BITNOT/NEG unary nodes have no `type`, so `mir_common_cmp_type` defaulted to signed and compared `~0u` as -1. The `u` suffix is lost through `~`. Fix (mir_common_cmp_type ~800): when a comparison operand is a BITNOT/NEG node with no type, descend to its child to recover the type. **Generalize: any type-preserving unary op (~, unary -) that drops its `type` silently reverts a comparison to signed** — check the operand chain, not just the literal.
- Pre-existing, NOT fixed: `0 < 4294967295` (no `u` suffix) compares signed — a literal exceeding INT_MAX without a `u` suffix isn't promoted to unsigned. Don't confuse this with the BITNOT bug.
- **Struct-typed member cell sizing** (holyd_parse.c regular-member path, ~line 511): a struct/union member occupies its CELL COUNT (member_type->size, which the parser keeps in cells), NOT `(hd_type_size(member_type)+7)/8`. `hd_type_size()` returns the TRUE C byte size (a 2-int inner struct = 8 bytes → /8 = 1 cell), which collapses a 2-member inner struct into 1 cell and makes the NEXT member alias the inner's last member. Generalize: for any aggregate member, size in cells = sum of member cell counts, never bytes/8. Symptom: `struct outer{struct{int i1;int i2;}t;int x;}` — writing `o.x=7` then reading `o.t.i2` returns 7 (they overlap).
- **Named member of an ANONYMOUS struct type needs synthetic registration** (holyd_mir_eval.c phase-1, ~line 5252): `struct{int i1;int i2;} t;` inside outer — the inner struct has no name so it is never in parse.named_types and member_type_names[t] stays empty, so `o.t.i1` cannot resolve the inner type (returns the wrong member or 0). Register the inner struct under a synthetic name `__anon_<outer>_<member>` and point member_type_names at it. (Truly anonymous members `struct{int b;};` with no name are already flattened by the parser — that case works; only the NAMED-member-of-anon-type case needs this.)

## MIR_TO_PTR (x86, wubu_isa_x86_64.c ~1742)
`wubu_mir_to_ptr` = mem_base + offset. Add mem_base (rbx) **exactly once** — a duplicate `add rax,rbx` corrupted every external string-arg call (segfault). The frontend emits MIR_TO_PTR before MIR_CALL when an arg is a string-literal / array / pointer, so BOTH backends get the converted pointer; external calls like strcmp/puts/strlen need it (copysign/abs, no string arg, mask the bug).

## Measurement discipline (gauntlet)
- `make gauntlet_runner` can say "up to date" and NOT rebuild after a `holyd_mir_eval.c` change (dependency tracking misses it) → stale binary → identical FAIL count before/after a real fix. Force `rm -f gauntlet_runner && make gauntlet_runner` before any measurement.
- Gauntlet runner flags: `--target x86-64` (a positional `x86-64` is IGNORED → runs all 14 ISAs); `--core` for the core suite; `--suite NAME` to run one suite (a bare positional suite name is IGNORED → always runs the full 4588).
- The full run is SIGKILLed (EXIT=143) at ~96 tests by the tool's process-lifetime cap (each test JIT-compiles + runs, ~93 tests/120s). For a complete measurement, redirect to a file and run in the background, or scope to `--suite`/`--core` which finish.
- EROR ≠ failure: ~2,469/4,588 ERORs are unrunnable snippets (undefined helpers test1/foo/ox/bug). Report **runnable pass rate** PASS/(PASS+FAIL), not raw — a 39% raw can be ~85% runnable. The gcc_torture/slimcc/wcc ERORs are mostly incomplete excerpts whose helper functions/macros (ASSERT/SASSERT) live in a harness preamble NOT in the code field — not parser bugs. 26 ptx-target FAILs are environmental (ptxas rc=65280), not compiler bugs.

## Pitfalls
- **Stale binaries**: `test_single`/`gauntlet_runner` give false PASS/FAIL if not rebuilt. `rm -f *.o test_single && make test_single` before trusting. Rebuild gauntlet with `rm -f gauntlet_runner && make gauntlet_runner` (plain `make` says "up to date" and skips the rebuild — the #1 false-measurement trap).
- **Gauntlet runs ALL 14 targets** unless `--target x86-64` (NOT positional). `--core` for core suite.
- **EROR ≠ failure**: ~2,469/4,588 ERORs are unrunnable snippets (undefined helpers test1/foo/ox/bug). Measure **runnable pass rate** PASS/(PASS+FAIL), not raw.
- **Walk-to-base-IDENT loses intermediate types**: `s[0][0]` where s is `char*[]` walks to base `s` (ARRAY(PTR(I8))), misses inner char. Resolve through the chain.
- **git stash dance loses changes (verify before committing)**: `git stash` → test-HEAD → `git stash pop` can silently fail to restore (empty stash, or pop conflicts), leaving your edit GONE while you believe it's staged. After ANY stash/pop or HEAD-comparison cycle, `grep -c '<unique string you added>' <file>` to confirm the edit survived BEFORE `git commit`. This bit twice in one session — a no-op commit and a lost fix. Safer pattern for a HEAD baseline test: `git stash`, test, `git stash pop`, then `grep -c` the marker; if 0, re-apply the patch from scratch rather than trusting the pop.
- **Regalloc call-crossing spill** (wubu_mir_regalloc.c Step 5, range_crosses_call): spill VRs whose live range crosses a MIR_CALL to a stack slot. Real but MODEST gauntlet win — the "329→142" figure once cited here was a FALSE measurement (see VERIFY COMPLETENESS below); true complete-run delta is ~14 tests. Correct discipline regardless.
- **Called-function epilogue is a TRADE-OFF, not a win**: making every called function run the full epilogue (mov rsp,rbp; pop r15..rbx,rbp; ret) fixes fib(2) but REGRESSES `x=5;y=f();return x` (the second call's result leaks into x) — FAIL 142→588. REVERTED. The recursion bug and the local-store-before-call bug are DIFFERENT bugs; the epilogue fix trades one for the other. Do not ship it. The residual recursion bug (fib(10), x=5;y=fib(1)) needs the operand-preservation-across-calls fix, NOT the epilogue.

## Compound assignment — two order/type pitfalls (both fixed)
- **Evaluate RHS before reading the LHS value**: `c -= (c += d)` loaded the LHS value BEFORE the RHS ran, so the inner assignment's side effect on `c` was invisible (got 3-7=-4, not 0). The lvalue ADDRESS is still computed once (before RHS), but load the lvalue VALUE after generating the RHS. Applies to every `X op= rhs` — the LHS may appear in the RHS.
- **Resolve a DEREF LHS pointee type for the float/int op choice**: `*p *= 1000` where p is `double*` did an INTEGER multiply on the double's bits, because is_float checked the DEREF node's `type` (NULL) and IDENT float vars but not a DEREF of a double-pointer var. When the compound-assign LHS is `*ident` and that ident is `PTR(F64)`, treat it as float.

## Function pointers (implemented 5122b1a)
- `int (*fp)(int)=f; fp(x)` works via `fn_ptr_func_id`: record the target func_id when a function-pointer var is initialized from a function name (BOTH the declaration-initializer path at holyd_mir_eval.c ~1342 AND plain assignment in the ASSIGN case ~2354). At the call site, if the callee IDENT isn't a direct function but is a var with fn_ptr_func_id>=0, resolve to that func_id (indirect call lowered to direct).
- The var's own memory value stays 0 (no real address stored) — only the call resolution uses fn_ptr_func_id. `fp!=0` is still wrong (reads the 0 value); only `fp(args)` works.

## __builtin_ prefix strip — OFF-BY-ONE (fixed d03c0db)
The preprocessor `strip_builtin_prefix()` in wubu_preproc.c removed 11 chars for `__builtin_` but the prefix is 10 chars, so `__builtin_abs`→`bs`, `__builtin_memcpy`→`emcpy` — every `__builtin_*` call dlsym'd a mangled name and returned 0. The frontend matches builtins by their STRIPPED name (strlen, memcpy, ...), so the preprocessor must strip exactly 10. When debugging a `__builtin_X` that returns 0, check the preprocessor strip FIRST (WUBU_DEBUG_CALL or the `[JIT] dlsym for <name>` stderr line reveals the mangled name).

## Recursion — SOLVED (per-call frame restore + JIT→interpreter routing)
Root cause (confirmed): params/locals live at FIXED `prog.mem` addresses allocated once at codegen; a recursive call reuses the same cells and clobbers the caller. The interpreter's `op_ret` restored only the VR file, not memory (comment: "Memory is NOT restored"). Earlier incremental mem-restore attempts regressed because they restored ALL memory (reverting persistent struct-return buffers) or used a byte boundary that doesn't exist (locals and struct-return buffers are interspersed).

**Working fix (both parts, ~90 lines, net-regression-free):**
1. **Interpreter reentrancy** (`wubu_mir_interp.c` + `wubu_mir.h` + codegen in `holyd_mir_eval.c`): codegen sets `prog->globals_end = total_mem` right before the first function body — everything allocated in the top-level block is GLOBAL (persists across calls), everything a function body allocates is FRAME memory. `op_call` snapshots the register file AND the frame cells (byte addr >= globals_end/8) into the per-call `call_frame_t`; `op_ret` restores register file + frame cells, leaving globals untouched. Store `frame_off`/`frame_cells` in the frame so save/restore mirror exactly. **Snapshot ONLY the frame region, not all memory** — full-mem copy is O(calls×mem) and fib(20) times out.
2. **JIT routing** (`hd_run_prog` in `holyd_mir_eval.c`): the x86-64 JIT still shares one flat `wubu_jit_mem_ptr` (deep codegen, unfixed). `prog_has_recursion()` builds the direct call graph from each function's MIR_CALL targets and detects any cycle via iterative DFS (direct + mutual + transitive recursion). Recursive programs route to `wubu_mir_interp` (the documented golden oracle, now reentrant); non-recursive programs keep the JIT. Safe: the interpreter IS the correctness oracle.

Result: fib(n) correct (fib(20)=6765), fact/sum/gcd/mutual-recursion pass; wcc suite FAILs 377→27. **The earlier "do NOT retry" guidance is OBSOLETE — the globals_end boundary is what the failed attempts were missing** (they had no way to separate persistent globals/struct-return-buffers from frame memory). To validate interp-only changes, build a throwaway binary: `gcc -O1 -o test_direct_interp test_direct.c holyd_*.c wubu_mir.c wubu_mir_interp.c wubu_mir_opt.c wubu_mir_regalloc.c wubu_softfloat.c stubs.c -lm` where stubs.c defines no-op `wubu_preprocess`, `wubu_mir_fuse/gvn/sccp/to_ssa`, `wubu_tgemm_f32_mir`. NOTE: `test_single` and `gauntlet_runner` use the x86-64 JIT (hd_run_prog with the x86-64 driver), NOT the interpreter.

### Known remaining recursion edge (rare)
Nested recursive call used as an argument — Ackermann `ack(m-1, ack(m,n-1))` — still miscomputes: the inner call's frame restore can clobber the outer frame's params before the outer call is set up. Uncommon in real code.

## Type-resolution coverage — the recurring bug class
Most wrong-result bugs here share ONE shape: **type/pointer/float info is resolved by a different code path for a compound expression than for a bare IDENT.** A helper handles IDENT/CALL/arith but not INDEX/DEREF/MEMBER/TERNARY, or not chained ADD/SUB, so the compound form silently falls back to a default (integer, scale 0, signed). Diagnostic: if a scalar works but the SAME operation on an array element / struct member / ternary / call result breaks, the node-kind coverage of the type resolver is the suspect — not the operation. Concrete fixes this class:
- **long/int64 collapsed to bool**: `mir_truncate_to_type` had `case HD_TYPE_I64: case HD_TYPE_U64:` falling through to the SAME code as `HD_TYPE_BOOL` (nonzero→1). Every value stored into a long (array elem, assign, deref) became 0/1. I64/U64 are full-width — return val unchanged; only BOOL normalizes. **Always separate I64/U64 from BOOL in a switch — case-label fall-through is the trap.**
- **double array not float**: `mir_is_float_node` handled FLOAT_LIT/IDENT/CALL/arith but not INDEX/DEREF/MEMBER, so `(int)a[i]` on double[] did integer truncation of the double bits (returned 0). For those node kinds resolve elem type via `mir_lvalue_elem_type` (descend sub-array types) + the double* pointee.
- **Pointer arithmetic through compound operands**: ADD/SUB only recognized a pointer operand as a direct IDENT/ADDR. `(arr+2)+1`, `1+(cond?a:b)`, `ge(arr)+1` (fn returning ptr), `(cond?a:b)-n` all treated as integer arithmetic; and `1+(*sip)` was WRONG because a deref'd VALUE was scaled as a pointer. Fix: `mir_node_ptr_scale(g,n)` resolves pointer byte-scale for ANY node — IDENT (var table), CALL (fn return type via `mir_find_func_return_type`), DEREF (ONLY when ptr-to-ptr/array, else `*p` is a VALUE, scale 0), descending ADD/SUB (leftmost pointer) and TERNARY (either branch). Wire into ADD left+right and SUB left. char/u8 pointee=1 else 8.
- **Nested char-array read byte-load**: `a[i][j]` on char[N][M] didn't byte-load (char_elem detection only handled IDENT/STRING/PTR/MEMBER bases, not a nested INDEX base). Resolve the INDEX base's lvalue element type, descending sub-array types, so the innermost char byte-loads.
- **Verify pointer-arith / index expectations with gcc before trusting a FAIL** — it is easy to miscount array indices (e.g. `1+(cond?arr+1:arr+2)` is arr+3, not arr+2).

## Nested char-array string init
`char a[N][M]={"ab","cd"}` (string-literal ROWS in a 2-D char array):
- The `flat_multi` initializer path treats STRING_LIT rows as scalar cells — exclude STRING_LIT from the flat_multi detection so it reaches the per-row loop.
- Per-row loop: byte-copy each string from its generated address into its row. **NESTED char arrays store ONE CHAR PER CELL (stride 8), matching brace-init layout and the a[i][j] read stride — NOT byte-packed like 1-D char[].** Zero-fill the rest of the row.
- 3-D+ (`mir_store_brace_leaves`): a STRING_LIT leaf inside nested braces stored as one cell; byte-copy chars into consecutive cells, advance `off+(slen+1)*8`.
- GOTCHA: 1-D `char[]="..."` is BYTE-PACKED (stride 1) but NESTED `char[N][M]` is CELL-PER-CHAR (stride 8). Don't assume byte-packing for nested arrays. (Second sub-array of a 3-D nested-string init still miscomputes — multi-dim offset bookkeeping; first row correct.)

## test_mir_battery — 6 known WRONG (NOT in `make test` gate; #102 unmarked)
`make test_mir_battery` = 117 total, 6 WRONG. NOT in the `make test` aggregate (line 121), so it does NOT gate 195/195. All 6 are representation-convention mismatches or deep scope bugs, not quick fixes:
- `float add` / `float a=1.5; a;`: float literals stored as **64-bit double bits** (holyd_mir_eval.c HD_AST_FLOAT_LIT ~2769: `union{double;uint64}`), but the battery interprets the return as **32-bit float** (`union{float;uint32_t}`). 1.5 → 0x3FF8000000000000 (double) not 0x3FC00000 (float). Deliberate double-for-precision choice; changing to 32-bit float risks many passing tests. Architectural float/double tension — same class as sizeof cell-vs-C-bytes.
- `string literal` `"hello"[0]`: returns the byte-offset/address (478560413032), not the char 104. String-literal indexing returns address not value.
- `scope shadow` `int x=1; {int x=2;} x;` → 2 (want 1): inner block scope-pop LOOKS correct (parse_block creates BLOCK without no_scope_pop; mir_eval HD_AST_BLOCK ~1167 pushes scope_var_start, pops n_vars ~1195; mir_find_var searches i<n_vars from end) yet outer x still resolves to inner value. Deeper than the pop logic — unresolved.
- `sizeof expr struct` / `sizeof in expr` `sizeof(struct S{int a;int b;})` → 16 (want 8): cell-vs-C-bytes (2 int cells × 8 = 16, C sizeof = 8). Documented tension.
- `struct in struct return`: nested struct return value.
Do NOT mark #102 ("selfhost_battery 155/155 + mir battery green") until all 6 pass. selfhost_battery IS 155/155; only the mir battery half is open.

## Gate before every push
`make test` (195/195) + `test_selfhost_battery` (155/155) + `test_fuzz_diff` (0 mismatches, x86 == interpreter). Never push a net regression — if a change fixes one case but breaks another, revert it and document as an architectural gap.

## Gauntlet measurement — VERIFY COMPLETENESS (critical)
A gauntlet run is only trustworthy if COMPLETE: `grep -a -c 'x86-64' <log>` must be ≈ 2,798 (the full x86-64 test count). A cut-short run (e.g. killed, or the `x86-64` positional arg ignored so it iterates all 14 ISAs and gets killed mid-way) UNDERCOUNTS failures dramatically — one incomplete run showed FAIL=142 when the true complete count was 329. ALWAYS check the x86-64 line count before reporting a FAIL number. Use `--target x86-64` (NOT positional `x86-64`), force-rebuild (`rm -f gauntlet_runner && make gauntlet_runner`), and confirm the run reached the end (EROR count ≈ 2,466, FAIL+EROR+PASS ≈ 2,798). The `[JIT] dlsym for X` stderr lines bloat the log and slow the run to ~5-6 min.
