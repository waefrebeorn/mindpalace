# MIR optimizer debugging recipe (WuBuNOS `wubu_mir_opt.c`)

Captured 2026-08-19 while root-causing three optimizer bugs that corrupted canonical MIR.

## The failure signature
Tests pass through the reference interpreter `wubu_mir_interp` but fail when the optimizer
runs (or fail intermittently — a Heisenbug masking real corruption). Classic tells:
- result flips when you add/remove a `printf` (memory corruption / uninit, not magic)
- a `JNZ`/`JMP`/`ADD` instruction in a dump has `op` changed to `CONST` (op=1)
- control-flow collapses (`||` returns wrong branch), or pointer/`p[i]` returns 0

## The isolation harness (the method that worked)
Build a TINY standalone `repro.c` that links ONLY the compiler frontend + optimizer, NOT the
codegen/codegen_emit/codegen_expr (those pull in `emit_*` x86 symbols you don't need):
```
gcc -O0 -g -std=c11 -D_POSIX_C_SOURCE=200809L -DWUBU_HOSTED -include wubu_gnu_compat.h \
  -I. wubu_mir.c wubu_mir_opt.c wubu_mir_lower.c wubu_mir_regalloc.c wubu_mir_interp.c \
  x86_peephole.c holyc_lexer.c holyc_parse.c holyc_parse_ast.c holyc_runtime.c \
  holyc_mir_eval.c wubu_preproc.c repro.c -lm -o repro
```
Then dump MIR numerically and apply optimizer passes ONE AT A TIME:
```c
hc_build_mir(src, &p0);                          /* now optimizes internally */
hc_build_mir(src, &p1); wubu_mir_optimize(&p1, MIR_OPT_FOLD);    show("FOLD", &p1);
hc_build_mir(src, &p2); wubu_mir_optimize(&p2, MIR_OPT_STRENGTH); show("STRENGTH", &p2);
hc_build_mir(src, &p3); wubu_mir_optimize(&p3, MIR_OPT_DCE);     show("DCE", &p3);
/* ... COMBINE, CSE ... */
```
Each pass prints `[TAG] ADD@i dst=.. a=.. b=..` / `CONST dst=.. imm=.. (ADD clobbered)` so you
see EXACTLY which pass corrupts which instruction. DCE converts a dead instruction to
`op=CONST; imm=0; a=0; b=0` — that is the smoking gun.

## Gotchas that waste time
- `hc_build_mir` optimizes INTERNALLY. To inspect TRUE RAW lowering, temporarily comment out the
  `wubu_mir_optimize(...)` call inside `hc_build_mir` (it sits near the end). A "raw" dump that
  still shows corruption means the BUG IS IN THE OPTIMIZER, not the frontend.
- ASan (`-fsanitize=address`) gives clean runs for these bugs because its allocator layout masks the
  Heisenbug. Use ASan only to confirm NO UB after the fix; it won't localize the logic bug.
- The `wubu_mir_alloc` helper does NOT emit a `MIR_ALLOC` instruction — it just computes a base
  address from `p->total_mem` and returns a `CONST`. So memory IS sized (total_mem accumulates);
  array/pointer failures are a LOWERING or optimizer issue, not an alloc bug.

## The three bugs found + fixes (in `wubu_mir_opt.c`)
1. **DCE delete-guard omission** — `MIR_JZ` listed in the `continue` guard but `MIR_JNZ`/
   `MIR_BREAK`/`MIR_CONTINUE` missing → JNZ branches converted to CONST 0. Add them to the guard.
2. **Fold folds phi-merges** — `fold_dce_pass` folded a vr defined more than once (two branch arms
   write the merge vr) and picked one arm's value. Fix: `def_count[dst]++;` over the program, then
   skip fold when `def_count[dst] > 1` (and `def_count[a] <= 1 && def_count[b] <= 1` for binops).
3. **DCE marking skips LOAD address** — marking loop did `if (op==MIR_ALLOC || MIR_LOAD) continue`
   without marking `used[in->a]` for LOAD. The address-computing ADD feeding the LOAD got deleted.
   Fix: `MIR_LOAD` must `used[in->a] = 1` (MIR_ALLOC has no inputs, stays skipped).

## General DCE correctness rule (encode in every optimizer pass)
An instruction is "live" if ANY other instruction reads its `dst`. Special cases that MUST be
treated as having live inputs / never deleted:
- Control flow: `MIR_JZ MIR_JNZ MIR_JMP MIR_BREAK MIR_CONTINUE` (read `a`/label, no value dst)
- Memory: `MIR_LOAD` reads `a` as an ADDRESS (mark `used[a]`), `MIR_STORE` reads `a` (addr) AND
  `b` (value). Both must be marked so the address/value computations are never deleted.
- `MIR_ALLOC` has no inputs (survives via the delete-guard) but marks nothing.
- After deleting an instruction, convert it to `MIR_CONST; imm=0; a=0; b=0` (never truly remove,
  or reindex vrs). Then a later pass must not fold the converted CONST incorrectly.

## x86-64 JIT NULL pointer trap (2026-08-28)

**Symptom**: x86-64 JIT crashes with SIGSEGV on LOAD/STORE instructions, even though the
interpreter runs the same MIR correctly.

**Root cause**: The JIT embeds `p->mem` as an absolute immediate in `movabs rdi, (uint64_t)p->mem`.
But `wubu_mir_init()` zeroes the struct, so `p->mem = NULL` at compile time. The JIT generates
code that dereferences NULL.

**Fix pattern**: Allocate mem BEFORE calling the JIT compiler, and pass it through the `arg`
parameter:
```c
int64_t *mem_ptr = prog->mem;
if (mem_ptr == NULL) {
    mem_ptr = calloc(mem_size, sizeof(int64_t));
}
wubu_mir_prog_t prog_copy = *prog;
prog_copy.mem = mem_ptr;
driver->compile(&prog_copy, &code, &csize);
driver->run(code, csize, (int64_t)mem_ptr);
```

**Lesson**: Any JIT that embeds pointers from the MIR struct as immediates must ensure those
pointers are valid at compile time. The interpreter can allocate lazily; the JIT cannot.

## Optimizer folding pitfall: SHL/SHR sign-extension pattern (2026-09-07)

**Symptom**: `(int)x` cast compiles but returns the wrong value — the sign extension is silently removed.

**Root cause**: The `SHL k >> k` pattern (shift left to sign bit, then arithmetic shift right) is treated as a no-op by the optimizer's constant folder in 64-bit arithmetic. The folder computes `(val << 32) >> 32 = val` and deletes both instructions.

**Why this matters**: The pattern IS a no-op in pure 64-bit arithmetic, but NOT when the intent is to sign-extend from 32 bits. The optimizer doesn't know the type semantics.

**Fix**: Use dedicated MIR ops (`MIR_SEXT8/16/32`) that the optimizer recognizes as non-foldable:
```c
// In fold_pass and fold_dce_pass, BEFORE the fold switch:
if (in->op == MIR_SEXT32 || in->op == MIR_SEXT16 || in->op == MIR_SEXT8 || in->op == MIR_ZEXT32)
    continue;
```

**JIT encodings**:
- SEXT8:  `48 0F BE C0` = `movsx rax, al`
- SEXT16: `48 0F BF C0` = `movsx rax, ax`
- SEXT32: `48 63 C0`    = `movsxd rax, eax`

**Lesson**: When a MIR pattern relies on bit-width semantics (not pure arithmetic), the optimizer will fold it away. Use dedicated ops with explicit fold guards.

## Goto label + optimizer interaction (2026-09-07)

**Symptom**: `goto label; return 0; label: return 1;` returns 0 instead of 1. The MIR before optimization is correct (jmp to L2, label at L2, return 1 after label), but after optimization the label and its following code are gone.

**Root cause**: Two compounding issues:
1. **Block codegen breaks after RETURN** — `mir_gen_stmt` for `HD_AST_BLOCK` has `if (stmts[i]->kind == HD_AST_RETURN) break;` which stops generating all statements after a return. If a label comes after a return, it's never emitted.
2. **Optimizer removes unreachable code** — Even after fixing #1, the DCE pass doesn't track jump targets. Code after a label that is a goto target can be removed because DCE sees it as unreachable (it only follows sequential flow, not jump edges).

**Partial fix (block codegen)**: Don't break after RETURN if there are LABEL statements ahead:
```c
if (n->stmts[i]->kind == HD_AST_RETURN) {
    int has_label_ahead = 0;
    for (uint32_t j = i + 1; j < n->n_stmts; j++) {
        if (n->stmts[j]->kind == HD_AST_LABEL) { has_label_ahead = 1; break; }
    }
    if (!has_label_ahead) break;
}
```

**Open issue**: The optimizer still removes goto target code. The DCE pass needs to track which labels are jump targets and preserve all code from a label to the next label (or to the end of the block). This requires building a label-reachability graph before running DCE.

**Debugging tip**: Always compare MIR BEFORE and AFTER optimization (`WUBU_DEBUG_MIR_BEFORE` and `WUBU_DEBUG_MIR_AFTER` env vars). If the BEFORE MIR is correct but AFTER is wrong, the bug is in the optimizer, not the frontend.
