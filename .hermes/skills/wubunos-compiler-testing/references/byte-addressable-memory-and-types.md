# Byte-Addressable Memory + Type-System Fixes (chapter_16 gauntlet wave)

Distilled root causes from closing the char/string/pointer/array cluster of the
writing-c-compiler chapter_16 suite (measured 16->18/33 with a per-test batch
harness). Every fix was verified against the x86-vs-interpreter differential
oracle (`make test_fuzz_diff` = 0 mismatches) and the full gate (`make test`
195/195, selfhost battery 155/155). These are generalizable memory-model and
type-inference rules, not one-off incidents.

## The measure-diagnose-fix-verify loop (highest-leverage workflow)

Do NOT ship thin modules and narrate progress. For a gauntlet failure cluster:
1. **Measure the real pass rate** with a batch harness that runs each valid
   test through `test_single <source> <expected>` and tallies. Parse each
   test's ACTUAL `return` expression for the expected value (char literals ->
   ASCII, int literals -> literal, complex -> skip) -- assuming expected=0 is
   WRONG for char/string tests (`return 'c'` == 99).
2. **Bisect to the minimal failing construct** with `test_single`, not the
   whole file. Reduce to the smallest snippet that still fails.
3. **Diagnose the root cause** (parser type? regalloc? interp-vs-JIT?) before
   editing. Print the relevant type-kind / VR / offset with a temporary
   `getenv("WUBU_DBG_X")` fprintf, then REMOVE it.
4. **Fix, rebuild, re-measure** the batch. A fix that doesn't move the batch
   number is not done.

## Byte-load width: movzx vs movsx (signed vs unsigned char)

A `char` (signed, HD_TYPE_I8) byte through a char* must SIGN-extend (movsx,
0F BE); `unsigned char` (HD_TYPE_U8) must ZERO-extend (movzx, 0F B6). A
zero-extending load of byte 0x80 gives 128, not -128 -- breaks reading the sign
byte of a double (`(char*)&-0.0` p[7] was 128, not -128).

Pattern: MIR_LOAD `imm` selects width -- `imm==1` zero-extend, `imm==2`
sign-extend. `wubu_mir_load8` (imm=1) / `wubu_mir_load8s` (imm=2). The frontend
DEREF/INDEX char-load sites pick signed for I8, unsigned for U8. The
interpreter must match (`(int64_t)(signed char)mem[addr]` for imm==2) or
fuzz_diff diverges. Rule: whenever you add a load width, update BOTH the x86
backend AND the interpreter in the same commit.

## Stride vs storage must agree (byte-packed strings)

String literals were cell-packed (each char at `addr + i*8`) but char* reads
them byte-strided (addr + i*1), so `s[1]` read the wrong byte. Fix: store
string literals BYTE-PACKED via `wubu_mir_store8` (stride 1), matching C
semantics and the char-pointer byte-stride. The char-array-from-string init
copy must then byte-LOAD the (byte-packed) source into cell-strided array
elements. Rule: pick ONE layout for a data structure and make every reader
agree; cell-model arrays and byte-packed strings are two different layouts.

## char ARRAY element access must be byte-native too (not just char-pointer)

The char_elem detection in the INDEX handler (the switch that picks byte-load
vs full-cell load) only matched a char POINTER base (`g->vars[i].type->kind ==
HD_TYPE_PTR` whose base is I8/U8). A char ARRAY base (`char s[8]`, an IDENT
whose var type is `HD_TYPE_ARRAY` of I8/U8) fell through to the full-cell load,
so `char s[8]="abcdef"; s[3]` read a full 8-byte cell, not byte 3. Fix: when
the base var type is ARRAY, check the ARRAY's element (`type->base`), not the
var type itself -- a var of kind ARRAY never has kind I8, so the naive
`et = type` check silently misses every char array. Manual element stores
(`s[3]=100`) roundtrip correctly (stride 1 is already right); only the
string-literal INIT copy and the array-read byte-load were wrong.

## Const-VR address arithmetic in copy loops reads byte 0 for every offset

UNRESOLVED at HEAD. The char-array-from-string copy loop reads the source with
`src_elem = MIR_ADD(src_addr_const, m)` then `load8(src_elem)`. `src_addr_const`
is the const VR returned by `wubu_mir_alloc` (the byte address of the
byte-packed literal). The pointer-read path (`char *s="abcdef"; s[i]`) reads
all bytes correctly because it loads the pointer var's VALUE then adds
`idx*stride`; the copy path adds a small int `m` directly to the const VR.
Symptom: for `"abcdef"` the copy writes 'a' to byte 0 AND byte 2, byte 1 stays
0 -- i.e. `src_addr + 1` and `src_addr + 2` both resolve to byte 0. This is the
SAME family as the known large-64-bit-AND const-VR/regalloc interaction bug: a
const operand + small-int offset does not advance as expected. Diagnose it
BEFORE touching stride/width again -- `char s[8]="abcdef"; s[3]` returning 0 at
HEAD is a copy-loop const-arithmetic bug, not a stride or load-width bug.

## Partial byte-native changes regress working short strings -- revert

Making only SOME of {copy store, array read, element load} byte-native corrupts
constructs that already worked via the cell-stride path. At HEAD,
`char s[]="abc"` (<=3 chars) passes via cell-strided copy; a byte-store copy
attempt produced garbage (6513249) and a byte-array-read attempt truncated
long strings while regressing short ones. When a byte-native experiment
regresses a previously-passing construct, REVERT to HEAD
(`git checkout HEAD -- <file>`, drop the broken stash) rather than ship the
regression, and document the precise unblocked next step (here: the copy-loop
const-arithmetic above). The gate at clean HEAD stays 195/195 + selfhost
155/155 + fuzz_diff 0.

## char-pointer arithmetic stride = 1

A char/uint8 POINTER strides by 1 byte per element, not the 8-byte cell.
`mir_index_stride` must return 1 for a char-pointer pointee BEFORE the array
logic (which forces a minimum 8-byte stride). Same for a char[] struct/union
member (`u.arr[i]`): resolve the member element base kind and return 1.

## Pointer-to-array `int (*p)[N]` -- parser builds the WRONG type

`int (*p)[3]` was mis-parsed as ARRAY(PTR(int),3) (array-of-pointers) because
the `(*name)` declarator path set is_ptr, then the `[N]` array loop wrapped the
pointer. Fix: in the `(*name)` path, detect a following `[N]` and build
PTR(ARRAY(base,N)) directly; guard the generic array-declarator loop and the
plain-pointer wrap so they don't re-wrap. `*p` on a ptr-to-array must return
the sub-array ADDRESS (decay), not load the first element. Mark local
`int (*p)[N]` vars with is_ptr_array=1 + array_stride so p[i][j] decays
correctly. Verified: `(*p)[1]==20`, `p[0][1]==20`, `int *q=*p; q[1]==20`.

## Hex literals with bit 63 set -- strtoll saturates

`0x8000000000000000LL` parsed with `strtoll` saturates at LLONG_MAX
(0x7FFFFFFFFFFFFFFF) because the value exceeds it, corrupting the bit pattern.
Then `< 0`, `>> 63`, and AND-with-mask are all wrong. Fix: parse hex with
`strtoull` (full 64 bits) and cast to int64_t (two's-complement reinterpret).
Rule: any 64-bit hex literal with the high bit set needs strtoull, not strtoll.

## Float-builtin return typing (int->double conversion on store)

`fabs`/`copysign`/`sqrt`/... results stored to a double variable were
int->double converted (MIR_DITOF), corrupting the float bit pattern, because
`mir_is_float_node` didn't recognize these builtins/externals (not in
func_ast) so the assignment saw an integer RHS. Fix: recognize float-returning
math functions by name in `mir_is_float_node` (a CALL whose callee name is in
the float set) so the double store keeps the bits. The fabs builtin itself is
`MIR_AND(x, 0x7FFFFFFFFFFFFFFF)` (clear sign bit) -- correct once the mask
literal parses (see hex-literal rule).

## Float comparison operand truncation when AST type is unset

`1.0/a < 0` (division result compared directly to an int) was wrong: the DIV
node's AST type is NULL, so `mir_binop_result_type` didn't detect the operand
as f64 and returned I32, triggering a 32-bit truncation of the comparison
operand -- corrupting the double bit pattern (`1.0/-0.0 < 0` was false).
Storing to a variable first worked because the variable's type IS f64. Fix:
`mir_binop_result_type` detects float operands via `mir_is_float_node` when the
AST type is unset (DIV/NEG-of-float-literal nodes). Rule: any binop-result-type
inference must fall back to `mir_is_float_node` for untyped expression nodes.

## 3D+ arrays broken by uninitialized vla_dims (BROAD bug)

`int vla_dims[8]` was declared but never zeroed; only `vla_dims[n]=1` was set
when a dim WAS a VLA. For a 3D+ array with no VLA dimension, `vla_dims[2]` held
stack garbage, so `has_vla` was wrongly true and the VLA path wrapped the array
type in PTR instead of leaving it ARRAY -- mir_eval then allocated only 1 cell
and mis-typed the array. ALL 3D+ arrays were silently broken. Fix: `memset`
vla_dims (alongside the existing vla_exprs memset). Rule: a flags array read in
a loop `for d < n` MUST be zeroed for the indices the loop reads; garbage past
the last set index is a silent wrong-branch, not a crash.

## Nested brace-init flattening must be RECURSIVE

The brace-init element store flattened only 2 levels, so 3D+ arrays
(`{{{...},{...}}}`) couldn't store a leaf whose element was itself a brace.
Replace with a recursive helper that walks arbitrary depth, storing every
scalar leaf at its flat 8-byte cell offset. Precondition: the array must be
allocated with enough cells (see the vla_dims rule) or the stores land out of
bounds.

## The cell-vs-byte tension is the recurring root cause of char/array gaps

Most char/string/array wrong-result bugs are ONE root cause wearing many
masks: the memory model allocates 1 cell (8 bytes) per array element, but C
char data is 1 byte per element and sub-cell rows (char[2][6], char[8]) are
smaller than a cell. When a fix makes only SOME paths (stride, load, copy,
row-layout) byte-native while others stay cell-native, a construct that worked
via the cell path regresses. Two rules:
- A fix is only safe when it makes a WHOLE access path (stride + load-width +
  copy + row-layout) agree on ONE layout. Partial byte-native changes regress
  working short strings / explicit 2D char arrays (revert and document, below).
- 2D char array rows (char n[][6]) must be byte-packed (6 bytes/row) for
  string-literal init but cell-strided (8 bytes/row) for explicit brace init
  of the SAME type -- an unresolved layout inconsistency, not a localized bug.
  Needs architectural work, not a stride patch.
- char*[] multi-level indexing (`s[0][0]`, `*s[0]` where s is char*[]) needs
  per-level type tracking through the intermediate char* element. The
  walk-to-base-IDENT in the INDEX char_elem detection loses the intermediate
  pointer type (resolves s as ARRAY(PTR(I8)) and checks the wrong level), so
  the inner index falls to full-cell load/stride-8. A stride-only patch
  regresses explicit 2D char arrays; this needs the type resolved per level.

## MIR_TO_PTR double-add corrupts EVERY external string call (BROAD)

The x86-64 MIR_TO_PTR handler emitted `add rax, rbx` (rbx = mem_base) TWICE
(an identical duplicated line), producing `offset + 2*mem_base` instead of
`offset + mem_base`. The frontend emits MIR_TO_PTR before external calls whose
arg is a STRING_LIT / ARRAY / PTR, so EVERY such call passed a pointer
mem_base bytes past the real string -> libc dereferenced invalid memory ->
segfault. `copysign`/`abs` (no string arg) worked, masking it; `strcmp`/
`puts`/`strlen` with string args core-dumped. Symptom: dlsym resolves, then
the process "dumped core" with no PASS/FAIL line. Fix: emit the mem_base add
ONCE. Rule: any duplicated `add reg, reg` line in a hand-written JIT handler
is a smell -- verify by testing an external call that TAKES a pointer arg
(strcmp/puts), not just one that doesn't (copysign).

## char*/ptr array brace-init stores the POINTER, not the raw offset

`char *s[] = {"yes","no"}` brace-initializers stored the raw byte offset that
`mir_gen_expr` returns for a STRING_LIT (a small int), not a real pointer, so
deref (`*s[0]`) and `strcmp(s[0],...)` dereferenced a small integer ->
segfault. Fix: for a pointer-typed array element initialized from a string
literal, emit MIR_TO_PTR (offset -> mem_base+offset) before storing. This
turns the array_of_strings core-dump into a clean FAIL (runs strcmp without
crashing); the deref VALUE still needs the string offset resolved
consistently (see the char*[] multi-level rule above).

## gcc is the oracle — verify the expected value before calling it a bug

When probing constructs with `test_single`, a large fraction of apparent
failures are WRONG TEST EXPECTATIONS, not compiler bugs. Verify EVERY
suspicious expected value with gcc first: `gcc -o /tmp/v /tmp/v.c && /tmp/v; echo $?`.
Common traps: UB constructs (`*(p++)+*(p++)`, `*(p--)+*(p+1)` — gcc's answer is
one legal value, not the one you assumed); the shell exit code is 8-bit so a
`return 383` shows as 127 (re-test with a byte-fitting value); arithmetic
errors in the expected constant; invalid C (duplicate identifiers, struct cast
to array). A session burned significant time on `*p-- + *(p+1)` (compiler gave
18, "expected" 30 — gcc agreed 18) and `unsigned char b[]={255,0,128}` b[0]+b[2]
(255, shown truncated). Gate every "fix" on a gcc-confirmed mismatch.

**More expectation traps hit this session:** `strlen("yes")` is 3, not 4 (the
probe `strlen(char* w)` "failed" at 3 because the expected was wrong — the
char[] init DOES store the NUL). The gauntlet compares exit codes masked
`& 0xFF`, while `test_single` compares the raw 64-bit result — a correct
`return INT_MIN` (0xFFFFFFFF80000000) "fails" test_single at -2147483648 but
the gauntlet scores it via the low byte. Always check whether the harness
masks before concluding a value is wrong.

## main()'s parameter VRs must be zeroed at the entry call

The entry emits `wubu_mir_call(main)` with no arguments set, so `v1..vN`
(which main's body copies into its param slots) held whatever the JIT register
file had — garbage. The interpreter `calloc`s its register file to zero, so it
read argc=0 correctly; the native JIT did not: `int main(int c){return c;}`
returned a garbage value on x86-64 while the same program routed through the
interpreter (recursion) returned 0. Fix: before the entry `wubu_mir_call`,
emit `mov v(pi+1), 0` for each of main's declared parameters (hosted main with
no CLI args ⇒ argc=0, argv=NULL). Diagnostic: a value differs between the JIT
and interpreter path for a no-arg-entry program ⇒ uninitialized entry VRs.

## Gauntlet FAIL triage — separate compiler bugs from harness limits

Of ~192 valid FAILs the two biggest buckets (gcc_torture ~72, extern_gcc ~48)
are mostly (a) scattered PR-specific edge cases and (b) **multi-TU tests
needing external `.o` files** — the extern_gcc `main_N` cluster calls
`nonpic_nothing()`/`pic_addr()` etc. from `pic-nothing.o`/`nonpic-addr.o` that
the single-source gauntlet runner cannot link, so they are a harness
limitation, not a compiler bug. Do NOT spend cycles chasing those. The
tractable clusters are the `wcc_chapter_15`/`wcc_chapter_16` pointer & char
tests. Workflow: dump the FAIL names
(`grep -a '^  FAIL ' <log> | sed -E 's/.*_([0-9]+)_(.*)/\2/' | sort | uniq -c`),
group by suite, extract the exact failing test source from
`test_gauntlet/suites/*.c` (JSON-escaped C strings — decode with a python
`re.search` + `unicode_escape`), and bisect it with `./test_single` before
assuming a compiler defect.

## Pointer-arithmetic / byte-load rule set (cell-model fixes)

These fixes all share one root: the MIR interpreter is an 8-byte CELL model, so
every place that must choose cell vs byte, load vs address, or scale an operand
has to resolve the element type through the whole AST chain. Distilled rules:

- **DEREF-of-ADD on a scalar array must LOAD.** `*(a+i)` on `int a[N]` is a
  scalar — only skip the load when the element is ITSELF an array
  (`ARRAY(ARRAY)`); treating every `*(array+i)` as a decaying sub-array returned
  the address instead of the element.
- **mir_address_of needs ADD/SUB cases.** The pointer VALUE of `a+1` IS the
  address to index from; with no ADD case, `(a+1)[0]` read garbage.
- **Byte-load detection must resolve the pointee through EVERY operand shape**:
  IDENT, ADD (`*(p+i)`), PRE/POST INC/DEC (`*s++` — without it `while(*s++)n++`
  over-reads, condition never sees a cell-boundary zero), and INDEX
  (`d[0]`, `d[0][0]` on char*[] — pointee is ARRAY(PTR(I8)) base->base). Grep
  every `n->child->kind ==` in the DEREF and INDEX handlers when extending it.
- **Array-of-pointers base: use_value=1.** For `d[0][j]` where d is char*[N],
  when the ultimate base var is an ARRAY whose element is a PTR, load the
  pointer rather than address the slot, else you read the slot's own bytes.
- **Stride past the array dims.** `d[i][j]` on char* d[N]: the inner index into
  byte-packed char strides by 1, not the cell 8 — in mir_index_stride, when the
  spine reaches a PTR-to-I8/U8 past the array dims, return 1.
- **Array name in subtraction decays to a pointer** (either operand): `p - a`
  marked the array as a plain int and multiplied its base address by the scale
  (garbage). Mark b_is_pointer for ARRAY/is_array operands; divide the
  difference by the scale.
- **Chained pointer on the RIGHT of `-` needs b_is_pointer via recursion.**
  `(p+3)-(p+1)` — the right operand is an ADD with no IDENT/ADDR, so
  b_is_pointer stayed false and the code MULTIPLIED `(p+1)` by ptr_scale
  instead of dividing the difference (int* returned -96, want 2). Resolve the
  right operand's pointer scale recursively (`mir_node_ptr_scale`) for
  ADD/SUB/TERNARY/CALL right-operands and set b_is_pointer. The LEFT-operand
  chained case already did this; the RIGHT was the gap.
- **Pointer-to-array pointee scale in SUB = array_size*8, not 8.**
  `double (*p)[5]` must divide the byte difference by the sub-array's total
  byte size (array_size * 8, product of inner dims), in BOTH the AST-type
  branch AND the var-table PTR branch of the SUB handler. The ADD handler
  already did this; the SUB handler used a flat 8. KNOWN GAP: a
  pointer-to-array PARAMETER (`get_diff3(m+3,m+1)` with `double(*)[5]` params)
  still miscomputes — the param binding does not carry the element scale into
  the function body. Deferred (narrow edge case).
- **Pointer compound assign scales the integer.** `p += n` on a pointer added
  the raw int; scale the RHS by pointee size (cell 8, char 1, ptr-to-array
  row) in ADD_ASSIGN/SUB_ASSIGN (`p = p + n` and `p++` already did).
- **Inferred array size in the parser.** `int a[]={...}` / `char s[]="..."`
  left array_size at the 1-element placeholder; infer it from the brace
  `n_args` or `strlen+1` for a string literal and recompute `size`, in BOTH the
  first declarator and the comma-declarator path.
- **char/u8 brace init must BYTE-PACK.** elem_sz=8 + full-cell store made
  `unsigned char b[]={255,0,128}` lose b[2]; set elem_sz=1 and use
  `wubu_mir_store8` so elements pack into one cell without clobbering siblings.
- **member_type_names must record PTR-to-struct members** (`struct B* pb`) at
  ALL struct-registration sites (record base->name), else nested `->` through a
  struct-pointer member can't resolve the type. Type-resolution prerequisite
  only — inline `a.pb->w` reads may still need a deeper MIR SSA fix (assign to
  a typed var first works).

## Stale-binary trap (this session's #1 time-waster -- REINFORCED)

Multiple "bugs" this session were stale `test_single` binaries: a fix landed
in source but the test still failed, then passed after `rm -f *.o test_single
&& make test_single`. When a construct that "passed earlier" now fails, or a
fix "didn't work", suspect the binary FIRST. Force a clean rebuild before
concluding a fix failed. (This extends the existing gauntlet_runner/gauntlet_v3
stale-binary note to `test_single` and all per-target test binaries.) The
gauntlet_runner binary is the worst offender: a gauntlet run against a binary
built hours before the source edits reports failures for constructs that pass
via a freshly built test_single -- rebuild gauntlet_runner before trusting any
gauntlet FAIL.

## Type-system element-access rules (long/int64 collapse + double-array float)

Two more "scalar works, array/struct element broken" bugs, same diagnostic
family as the char-array rules above: a type-sensitive op resolves the type by
a different path for INDEX/DEREF/MEMBER than for IDENT/scalar.

- **mir_truncate_to_type: never let I64/U64 fall through to the BOOL case.** A
  `case HD_TYPE_I64: case HD_TYPE_U64: case HD_TYPE_BOOL:` fall-through
  normalizes nonzero->1, so EVERY value stored into a long/long long (array
  element, brace init, assign, deref) collapsed to 0/1 — while int/short/
  unsigned (separate cases) were fine and long SCALARS slipped through. Fix:
  give I64/U64 their own `return val;` (full-width, no normalization). Rule:
  whenever a type case is added to a switch that shares a body with BOOL,
  check for case-label fall-through.
- **mir_is_float_node must cover INDEX/DEREF/MEMBER/ARROW.** It handled
  FLOAT_LIT/IDENT/CALL/arithmetic but not element access, so `(int)a[i]` on a
  `double[]` did integer truncation of the double's bit pattern (returned 0)
  and double-array comparisons were inconsistent (`a[1]>2.4` true but
  `a[1]<2.6` false). Storing to a `double` temp first masked it. Fix: for those
  node kinds resolve the element type via `mir_lvalue_elem_type` (and the
  `double*` pointee) and report F64. Diagnostic: if a cast/compare works on a
  scalar but returns garbage on an array/struct element, the type-detection
  helper is missing that node kind.

## gauntlet_runner invocation quirks (affects the measure step)

- `./gauntlet_runner SUITE` IGNORES a bare positional suite arg — it always
  runs the full 4588-test set. Use `--suite NAME`.
- `--core` runs the small built-in 247/247 gate (all 14 targets) — the fast
  correctness check that must stay green before any push.
- The FULL run is SIGKILLed (EXIT=143) at ~96 tests under the tool's 600s
  process cap (each test JIT-compiles + runs, ~93 tests/120s throughput). A
  partial/EROR-heavy tally is a killed run, not a result — for a bounded
  measurement run `--suite <name>` under `timeout`.
- gcc_torture / slimcc / wcc ERORs are mostly INCOMPLETE test excerpts: the
  suite entry's code field references undefined helper functions and custom
  ASSERT/SASSERT macros that live in a harness preamble NOT in the code field,
  so they can't compile standalone — harness gaps, not parser bugs. Confirm by
  probing the individual construct with test_single.
