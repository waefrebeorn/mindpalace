# HolyC → MIR → ISA Driver Bridge

The compiler has TWO evaluation paths:
1. **Direct JIT** (`hc_eval`): HolyC → AST → x86-64 machine code → execute. Fast, native, single-target. Playbook lives in SKILL.md.
2. **MIR bridge** (`holyd_mir_eval.c`): HolyC → AST → MIR → ISA driver → compile → run. Cross-target. **This file.**

The MIR bridge is the gauntlet's path for every target. It is a separate
lowerer from the direct JIT — a bug fixed in one path is usually still live
in the other. When a gauntlet test fails, the bug is almost always here.

## Current API (supersedes the older `hc_eval_mir` name)

```c
wubu_mir_prog_t prog;
if (hd_build_mir(source, &prog) != 0) return 2;   // parse+lower failure
int64_t result = hd_run_prog(&prog, drv);            // compile via driver + run
```

## Single-test reproduction (the highest-leverage debug tool)

`gauntlet_runner --dump-asm <target> "<source>"` builds the source string,
compiles through the named driver, prints the emitted bytes and `result=`.
Feed it the failing test file's contents:

```bash
./gauntlet_runner --dump-asm x86-64 "$(cat path/to/test.c)"
```

Then bisect with minimal repros (`unsigned a[2]={4294967294U,0};\nint main(void){ a[0] += 2; return a[0]; }`). `gauntlet_runner --core\n--target x86-64` runs the ~247-test core suite; `gauntlet_v3` runs the full\n~4400-test set and prints a JSON summary line with the valid pass rate.\n\n## What the bridge supports (corrected — the old "not supported" list is stale)\n\nThe bridge lowers the full C11 subset the gauntlet exercises: INDEX\n(multi-dimensional), MEMBER/ARROW, DEREF, compound assignment, PRE/POST\ninc/dec on computed lvalues, struct-by-value return, float arithmetic.\nIf a construct genuinely fails, treat it as a BUG in the bridge, not an\nunsupported feature.\n\n## MIR generation rules\n\n- **vr 0** = return value register.\n- **Literals**: `wubu_mir_const(prog, val)`.\n- **Binops**: `wubu_mir_binop(prog, MIR_ADD, l, r)`; floats use MIR_DADD/DSUB/DMUL/DDIV.\n- **Comparisons**: MIR_EQ/NE/LT/LE/GT/GE producing 0/1.\n- **Control flow**: labels + `wubu_mir_jz`/`wubu_mir_jmp`/`wubu_mir_place_label`.\n- **Memory**: `wubu_mir_load`/`wubu_mir_store` (full 8-byte cell), `wubu_mir_load8`/\n  `load8s`/`store8` for char-sized elements (zero/sign-extend, mask).\n\n## The computed-lvalue bug family (all five fixed, one root shape)\n\nEvery one of these is the SAME mistake: a lowering path that resolves the\nLHS type only from `n->left->ident[0]` (a scalar variable name) or\n`n->left->type`. For a computed lvalue — `a[i]`, `*p`, `s.f`, nested\n`a[i][j]` — both are NULL/empty, so the path silently skips type-dependent\nbehavior. Symptom shape: the scalar version works, the array/pointer version\nis wrong. **Whenever you touch a lowering path that keys off the LHS type, ask\n"what does this do when the LHS is an INDEX/DEREF/MEMBER?"**\n\n1. **Compound assign never truncates to the element type.** `unsigned a[4]=\n   {1,4294967294U,...}; a[1] += 2;` gave 4294967296, not 0 — the result\n   accumulated at 64-bit and never wrapped. Fix: resolve the element type\n   from the base variable's ARRAY base (or pointer pointee) and run\n   `mir_truncate_to_type` on the result (U32 = `& 0xFFFFFFFF`, no sign\n   extension; I32 = mask + SEXT32).\n\n2. **Float compound-assign back-conversion has the same blind spot.**\n   `a[2] -= 10.0` on an unsigned array: the double result was never\n   converted back to the element's integer width/signedness. Resolve the\n   element type the same way, then DTOI vs DTOI_U by signedness.\n\n3. **`mir_promote_to_float` must promote every lvalue kind.** It only\n   promoted IDENT/binop/literal nodes; INDEX/DEREF/MEMBER/ARROW fell through\n   to "return val unchanged", so a mixed float compound assign on `a[i]`\n   did DSUB on an un-promoted integer lhs. Add all four kinds.\n\n4. **Multi-dimensional stride must walk the ARRAY type spine.** For\n   `int a[D0][D1][D2]`, the depth-1 index `a[i]` strides by D1*D2 cells,\n   depth-2 `[j]` by D2, depth-3 (innermost) `[k]` by 1. A single\n   `array_stride` field for the outer index plus a flat 8-byte stride for\n   all inner indices reads `a[1][1][1]` as the wrong element. Collect the\n   per-dimension sizes down the type spine and multiply the inner dims.\n\n5. **++/-- on a computed float lvalue must use float ops.** `double *p;\n   ++(*p)` and `++a[i]` on a `double[]` emitted integer ADD/SUB, corrupting\n   the double. The general-lvalue inc/dec paths had no float detection at\n   all (only the scalar IDENT path did). Detect via the lvalue's resolved\n   element type (double* pointee / double array base) and emit\n   MIR_DADD/MIR_DSUB with the double-bit-pattern constant 1.0.\n\n## Debugging driver (non-x86-64) failures\n\nIf a driver fails on simple arithmetic (`1+2`, `6*7`):\n1. The bridge is correct — the MIR is trivial (CONST, ADD, RET).\n2. The bug is in the driver's interpreter or encoder.\n3. Isolate with a minimal MIR probe; compare against the x86-64 driver.\n\n## Regression discipline for bridge edits\n\nThe bridge shares the frontend with the direct-JIT path and the gauntlet.\nAfter ANY `holyd_mir_eval.c` change, run all three:\n\n```bash\nmake test_mir_battery       # 111/117; 6 WRONG are PRE-EXISTING — diff before/after\nmake test_selfhost_battery  # 155/155\n./gauntlet_runner --core --target x86-64   # 247/247\n```\n\nA change is clean only if the MIR battery's WRONG set is byte-identical\nbefore and after (`... | grep WRONG | sort` both sides, `diff`).\n