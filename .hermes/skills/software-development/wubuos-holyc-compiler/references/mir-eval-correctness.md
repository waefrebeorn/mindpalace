# MIR evaluator correctness — bug classes & fixes (holyd_mir_eval.c / wubu_mir_interp.c)

Distilled from the compiler-correctness sessions. Organized by bug CLASS, not
session. Each rule is a generalizable pattern + why. The cell model underlies
everything: **all values live in 8-byte cells; addresses are cells.** Scalar
pointer arithmetic scales by 8, char/u8 byte-packed data by 1.

## The diagnostic pattern that cracks most of these

When a construct works as a SCALAR but breaks as an ARRAY/STRUCT ELEMENT, the
type (or pointer-ness) is resolved by a *different code path* for the compound
node than for a bare IDENT. Grep the type/stride/float/pointer resolver for the
node kind that's missing. Probe `long a[3];a[1]=8;return (int)a[1]` and the same
via a temp to localize write-vs-read.

Always verify the expected value with **gcc as the behavioral oracle** before
declaring a compiler bug — array-index miscounts and UB (`a+++a++`) have
produced several false alarms where the compiler was already correct.

## Shadowing: var-NAME lookups must search from the END

A recurring class: var-table lookups that iterated `for (i=0; i<n; i++)` resolved
a shadowing local to a same-named GLOBAL registered earlier. Fixed sites:
`mir_index_stride` array-stride lookup, the INDEX `char_elem` IDENT-base
detection, and the INDEX `is_ptr_array` (sub-array decay) check. All now search
`for (i = g->n_vars - 1; i >= 0; i--)`, matching `mir_find_var_addr`.

RULE: any var-NAME lookup for type/stride/flag must search from the END
(most-recent declaration wins). When auditing the many `for (int i = 0; i <
g->n_vars; ...)` loops, the var-NAME ones are the shadowing risk; struct/enum/
member-name lookups are not. Symptom signature: a function-local array/pointer
misbehaves ONLY when a same-named global exists, and reads the global's
dimensions (e.g. `&local[1][0]-&local[0][0]` gives the global's row width).

DEFERRED sub-case: a function-local `char x[8]="hi"` string *init* still
mis-writes when a same-named global exists (manual assign and the no-global case
both work). Write-path (1-D string init), rarer than the read-path cases above.

## Type-system: case-label fall-through in mir_truncate_to_type

`long`/`int64` was collapsed to bool because `case HD_TYPE_I64: case HD_TYPE_U64:`
fell through to the `HD_TYPE_BOOL` body, which normalizes nonzero->1. Every value
stored into a long/long long (array element, brace init, assign, deref) became
0/1, while int/short/unsigned (separate cases) were fine and long *scalars*
slipped through. Fix: I64/U64 are full-width — return val unchanged; only BOOL
normalizes.

RULE: when adding a `case` to a type switch, never let I64/U64 share a body with
BOOL. Separate them explicitly.

## Float recognition: mir_is_float_node node-kind coverage

`mir_is_float_node` handled FLOAT_LIT / IDENT / CALL / arithmetic but not
INDEX / DEREF / MEMBER / ARROW. So `(int)a[i]` on a `double[]` did integer
truncation of the double's bit pattern (returned 0), and double-array
comparisons were inconsistent (`>2.4` true, `<2.6` false). Storing to a double
temp first masked it. Fix: for INDEX/DEREF/MEMBER/ARROW resolve the element type
via `mir_lvalue_elem_type` (descending sub-array types) plus the `double*`
pointee, and report F64.

## Pointer arithmetic: operands arrive via ANY expression

ADD/SUB only recognized a pointer operand as a direct IDENT / ADDR / DEREF-of-ADD.
Compound pointers have no AST type, so they were treated as integer arithmetic:
`(arr+2)+1`, `1+(cond?a:b)`, `ge(arr)+1` (fn returning a pointer), `(cond?a:b)-n`
all broke. And `1+(*sip)` was wrong because `*sip` (a dereferenced *value*) was
scaled as a pointer. Fix: `mir_node_ptr_scale(g,n)` resolves the pointer
byte-scale for ANY node — IDENT (var table), CALL (fn return type via
`mir_find_func_return_type`), DEREF (ONLY when pointer-to-pointer/array, else `*p`
is a VALUE, scale 0), and descends ADD/SUB (leftmost pointer) and TERNARY (either
branch). Wire it into ADD (left+right) and SUB (left). char/u8 pointee = 1 byte,
else 8.

RULE: never assume a pointer operand is a bare IDENT — it can arrive via
arithmetic, ternary, a call, or a deref-of-pointer-to-pointer. And `*p` of a
scalar pointer is a VALUE, not a pointer.

## Nested char-array string initialization

`char a[N][M]={"ab","cd"}` (string-literal ROWS in a 2-D char array):
- Exclude STRING_LIT args from the `flat_multi` initializer detection so the
  per-row loop runs.
- Per-row loop: byte-copy each string from its generated address into its row.
  **NESTED char arrays store ONE CHAR PER CELL (stride 8)**, matching brace-init
  layout and the `a[i][j]` read stride — NOT byte-packed like 1-D `char[]`.
  Zero-fill the rest of the row.
- Read `a[i][j]` on `char[N][M]` didn't byte-load: the `char_elem` detection
  lacked a nested-INDEX base. Resolve via `mir_lvalue_elem_type`, DESCENDING
  through sub-array types (a[0]'s element is `char[4]`; you need its base char).
- 3-D+ (`mir_store_brace_leaves`): a STRING_LIT leaf inside nested braces stored
  as one cell. Byte-copy chars into consecutive cells, zero-fill the whole
  innermost row, and advance by the FULL row width (pass the innermost dim in),
  not by string length — otherwise the next sub-array starts too early.

GOTCHA: 1-D `char[]="..."` is BYTE-PACKED (stride 1) but NESTED `char[N][M]` is
CELL-PER-CHAR (stride 8). Do not assume byte-packing for nested arrays.

## Recursion — the call-frame architecture (SOLVED)

Root cause: BOTH backends shared one flat memory buffer with FIXED compile-time
addresses for params/locals, so a recursive call reused the same cells and
clobbered the caller's params/locals (fib(10) read back -80; fact(5)=16).

Two-part fix:
1. **Interpreter reentrancy** (`wubu_mir_interp.c` + `wubu_mir.h` +
   `holyd_mir_eval.c`): codegen sets `prog->globals_end = total_mem` right before
   the first function body (everything allocated in the top-level block is global;
   everything a func body allocates is frame memory). `op_call` snapshots the
   register file AND the frame cells (byte addr >= globals_end/8 — NOT all memory,
   which was O(calls*mem) and made fib(20) time out). `op_ret` restores the
   register file + frame cells; globals below the boundary persist across calls.
   Store `frame_off`/`frame_cells` in `call_frame_t` so save/restore mirror
   exactly.
2. **JIT routing** (`hd_run_prog` in `holyd_mir_eval.c`): the x86-64 JIT still
   uses one flat `wubu_jit_mem_ptr` (deep codegen, unfixed). `prog_has_recursion()`
   builds the direct call graph from each function's MIR_CALL targets and detects
   any cycle via iterative DFS (direct + mutual + transitive). Recursive programs
   route to `wubu_mir_interp` (the golden oracle, now reentrant); non-recursive
   programs keep the JIT.

VALIDATION: `test_single` and `gauntlet_runner` use the x86-64 JIT
(`hd_run_prog` with the x86-64 driver), NOT the interpreter. To validate an
interpreter-only change, build a throwaway binary:
`gcc -O1 -o test_direct_interp test_direct.c holyd_*.c wubu_mir.c
wubu_mir_interp.c wubu_mir_opt.c wubu_mir_regalloc.c wubu_softfloat.c stubs.c -lm`
where stubs.c defines the missing no-op syms (wubu_preprocess, wubu_mir_fuse/gvn/
sccp/to_ssa, wubu_tgemm_f32_mir).

KNOWN EDGE (rare, unfixed): a nested recursive call used as an argument —
Ackermann `ack(m-1, ack(m,n-1))` miscomputes; the inner call's frame restore can
clobber the outer frame's params before the outer call is set up.

## Lexer / parser additions

- C14 digit separators `1'000'000`, `0xFF'FF`: the number scanner skips a `'`
  only when a valid digit follows (decimal/hex/bin) and i>0, so it never eats a
  char-literal quote. Look ahead via `lex->src[lex->pos + 1]` (there is no
  `hd_peek2`).
- `alignof` (C23): alias of `_Alignof` in the alignment-query primary-expr path.
- `_Bool`: lexer keyword + normalize (val!=0)->1 in `mir_truncate_to_type`,
  VAR_DECL init, and the CAST node.
- Flat multi-dim init `int a[2][2]={1,2,3,4}`: store scalars into consecutive
  cells (byte-pack for char), skip the per-row BRACE_INIT loop.

## gauntlet_runner gotchas

- `./gauntlet_runner SUITE` IGNORES the bare arg (always runs the full set). Use
  `--suite NAME`. The full run is SIGKILLed at ~96 tests by the tool's process
  cap (~93 tests/120s; each JIT-compiles + runs). Run a bounded slice to get a
  number that completes.
- gcc_torture ERORs are mostly INCOMPLETE excerpts: the suite entry's code field
  references undefined helpers (`foo`/`ok`/custom ASSERT macros) that live in a
  harness preamble NOT in the code field, so they can't compile standalone. Not
  parser bugs. slimcc/wcc use ASSERT/SASSERT macros the same way.
- Remaining silent-crash parser gaps: parenthesized declarators
  `int(return_3)(void)`, abstract declarator casts `(unsigned long(*))0`.
- 26 ptx-target failures: ptxas returns a nonzero rc — environmental (PTX
  codegen/assembler), not CPU-compiler bugs.

## Deferred (root-caused, not fixed)

- **Struct member access / copy on a ternary result**: `(cond?a:b).member`,
  `struct S c=(cond?a:b)` — a struct ternary doesn't multi-cell copy; member
  access on a ternary base reads garbage. Needs struct-value copy semantics.
- **Function-local `char x[8]="hi"` init with a same-named global** (see
  Shadowing above).
