# HolyD frontend correctness wave — char/string, pointer-arith, struct-member type resolution (R169–R182)

Generalizable rules extracted from the WuBuNOS compiler gauntlet-closure session.
The SKILL.md numbered-rule list is at its size ceiling; rules from this wave live
here and are referenced from SKILL.md. Despite the filename, this file now covers
more than chapter 16: char/string byte-addressability, pointer arithmetic,
switch promotion, call-site arg conversion, and struct-member float/type
resolution (chapter 18) — all the same class of "frontend handler missed a type
or width" bug.

## R169 — Every var-table lookup must search from the END

The fn-local-shadows-global bug class. `mir_find_var_addr`, `mir_index_stride`,
`char_elem` all search from the end, but `mir_var_is_array` still forward-searched.
A fn-local **array** shadowing a same-name global **scalar** then read garbage:
`mir_var_is_array` found the global scalar (`is_array=0`), so `mir_address_of` fell
through to `mir_load(global)` and used the global's VALUE (e.g. 5) as the base
pointer — `x[2]` read memory at byte offset 5+16.

Repro: `int t(){int x[4]={1,2,3,4};return x[2];} int x=5;` → 0 (want 3).

RULE: when adding or auditing any `for (i...) if (strcmp(g->vars[i].name, ...))`
lookup, default to `i = g->n_vars - 1; i >= 0; i--`. Forward search is correct ONLY
where you intentionally want the oldest declaration. Audit the whole family
(is_array / is_struct / is_unsigned / find_var_type / struct_name) together — they
are fixed as a set or the shadowing contract is broken.

## R170 — Sub-array decay: a[i] on a 2-D array returns an ADDRESS

`int a[M][N]` → `a[i]` is itself an ARRAY, so as a value it decays to `&a[i][0]`.
The INDEX handler in `mir_gen_expr` only decayed for `is_ptr_array` bases
(`int (*p)[N]`); a plain 2-D array's `a[i]` fell through to `wubu_mir_load` and used
the cell CONTENTS as the base pointer — `char *w = a[0]; strcmp(w, ...)` crashed
reading a garbage address. Fix: after computing `addr`, if the base IDENT's
var-table element type is `HD_TYPE_ARRAY` (base->base->kind == ARRAY),
`return addr` (decay).

Repro: `int a[3][3]={{1,2,3},{4,5,6},{7,8,9}}; int*w=a[0]; return w[0];` → 0 (want 1).

## R171 — Pointer-VARIABLE arg to an external (dlsym) call must be MIR_TO_PTR'd

In the FUNC_CALL arg loop, `arg_is_addr` is set for STRING_LIT, ARRAY/PTR AST
types, and array IDENTs — but a **pointer variable** `char *w` has a NULL AST type
and is not an array, so `arg_is_addr` stayed 0, `MIR_TO_PTR` was skipped, and the
raw byte offset (e.g. 8) was passed as rdi → `strcmp(w, ...)` / `strlen(w)`
dereferenced address 8 → deterministic segfault. Direct array/string args worked
(they set arg_is_addr). Fix: when the arg is an IDENT, also search the var table
(from end) for a `HD_TYPE_PTR` type and set arg_is_addr.

Repro: `char row[4]="yes"; char*w=row; return strcmp(w,"yes");` crashed; after fix returns 0.

RULE: any external-call argument that is a pointer value (not just a literal/array)
needs the offset→pointer conversion — check the var table for PTR-typed IDENTs,
since IDENT nodes carry no type.

## R172 — 2-D char arrays are CELL-packed (row stride = cells*8), NOT byte-contiguous

`char nested[3][3]={"yes","no","ok"}` stores one char per CELL (stride 8);
`&nested[1][0]-&nested[0][0]` = 24 (3 cells), not 3 bytes. So `(char*)nested` read as
a C string stops at the zero-filled tail of row 0 ("yes\0") and never sees row 1 —
`strcmp((char*)nested, "yesno")` returns nonzero, not 0. This is the known
architectural cell-vs-byte limitation for multi-dim char arrays; it is NOT the
sub-array-decay or pointer-arg bug. Do not "fix" the cell layout to chase the wcc
null-bytes test without a deliberate byte-packing migration — a separate, larger
change.

## R173 — Char/uint8 array element STORES must be store8 (1 byte), not full-cell store

In the byte-addressable model a char element occupies ONE byte, but the
HD_AST_ASSIGN and compound-assign handlers emitted a full 8-byte `wubu_mir_store`
for every lvalue. A store to `arr[1]` wrote bytes 1-8 and clobbered `arr[2]` and
every following element — so `signed char a[3]={10,20,30}; a[1]+=5;` returned 0 for
`a[2]`. Both handlers now emit `wubu_mir_store8` when the resolved LHS element type
is I8/U8 (assignment resolves lhs_type via AST/var-table/INDEX-walk; compound-assign
resolves via mir_lvalue_elem_type).

RULE: any store whose lvalue resolves to an I8/U8 element type must be store8 —
audit every `wubu_mir_store` reachable from a char-typed lvalue. The truncation
(mir_truncate_to_type) was already correct; only the store WIDTH was wrong.

## R174 — String-literal pointer arithmetic scales by 1 (byte), not 8

String literals are byte-packed (one char per byte, stride 1 — matching the INDEX
read path `"ab"[1]` and the store8 init). But the ADD and SUB handlers set
`ptr_scale = 8` for a STRING_LIT operand, so `"abcdefg" + 3` advanced 24 bytes and
`*ptr` / `ptr[i]` read the wrong characters. Fixed to `ptr_scale = 1` in both
HD_AST_ADD and HD_AST_SUB.

Repro: `char *p = "This is a string!" + 10; *p != 's'` failed; now passes.

RULE: string literals are byte-packed everywhere — scale, stride, store, and load
must all be 1.

## R175 — main()'s parameter VRs must be zeroed at entry

The entry point calls main with no arguments set, so v1..vN (which main's body
copies into its param slots) held whatever the JIT register file had — garbage.
The interpreter zeroes its register file (calloc) so it read argc=0 correctly, but
the native JIT did not: `int main(int c){return c;}` returned a garbage value on
x86-64. Fix: before `wubu_mir_call(main)`, emit `mov v(pi+1), 0` for each of main's
declared parameters, so both backends see argc=0/argv=NULL.

## R176 — Chained pointer subtraction (p+i)-(p+j) + ptr-to-array element scale

Two pointer-subtraction fixes in HD_AST_SUB:

1. Chained pointer on the RIGHT operand: `(p+3)-(p+1)` treated the right `(p+1)`
   as an integer (it has no IDENT/ADDR to detect) and multiplied it by ptr_scale
   instead of dividing the difference. Fix: ADD/SUB/TERNARY/CALL right-operands
   resolve their pointer scale recursively (mir_node_ptr_scale) and set
   b_is_pointer. Fixes int* `(p+3)-(p+1)` returning -96 (want 2).

2. Pointer-to-array element scale: a `double (*p)[5]` pointer (AST type or
   var-table type) now scales/divides by the sub-array's total byte size
   (array_size * 8), not 8. Matches the ADD handler.

Known remaining: pointer-to-array **parameter** diff (`get_diff3(m+3, m+1)`) still
miscomputes — the param binding doesn't carry the element scale through to the
function body. Deferred (narrow edge case, deep in param binding).

PITFALL hit while fixing this: adding pointer-to-array scaling to
`mir_node_ptr_scale`'s ARRAY-of-ARRAY branch regressed the plain int case
(`(p+3)-(p+1)` → -96). Keep the ARRAY branch returning 8 for scalar-element arrays;
only the PTR(ARRAY) branch scales by the sub-array size.

## R177 — Char/uint8 array element inc/dec must load8/store8 too

The post- and pre-inc/dec general-lvalue paths (`c[i]++`, `++c[i]`, via
`mir_lvalue_addr`) did a full-cell load and store, same class as R173. The load
returned the value plus 7 garbage high bytes, so `c[0]++` returned 8223867 instead
of 123 (the old value it must yield); the store clobbered following elements. Both
paths now use `load8`/`store8` and truncate the updated value to char width when
`mir_lvalue_elem_type(n->child)` is I8/U8. **RULE: EVERY read-modify-write of a
char-typed lvalue (assign, compound-assign, post-inc/dec, pre-inc/dec) must use
byte load/store — the bug class is "full-cell RMW on a byte element" and it appears
in each handler independently. Audit them as a set.**

## R178 — Arrays >= 16 bytes are 16-byte aligned

The VAR_DECL allocation aligned every variable to 8 bytes. The wcc alignment test
requires char arrays of >= 16 bytes to be 16-byte aligned. Fix: in the VAR_DECL
allocation, `align_to = (n_cells * 8 >= 16) ? 16 : 8` — large arrays get 16-byte
alignment, scalars/small aggregates keep 8. Watch for memory-layout shifts when
changing alignment (re-run the full gate; the shift moved several allocations).

## R179 — Switch integer promotion: extend cond to int, do NOT truncate case values

Per C 6.8.4.2p3 the switch controlling expression is promoted to int and each case
label is converted to that promoted type. The handler truncated BOTH the cond and
the case value to the switch's char type, so `char c=-56` (byte 0xC8) and
`case 200` (byte 0xC8) both became -56 and falsely matched. Fix: sign/zero-extend
only the cond to int width (char/short via mir_truncate_to_type on the resolved
cond type), and leave case values untruncated. Repro: `char c=-56; switch(c){case
33554632:...}` wrongly matched; now hits default. **RULE: integer promotion means
extend the narrow operand, never truncate the wide one to match — truncating both
sides to the narrow type destroys the distinction.**

## R180 — Call-site arg conversion: gate on param count, NOT func count (FIXED)

Symptom: `int f(int a,int b,int c){return c;} ... f(1,2,10.0)` returned 0 on the JIT
path but 10 on the interpreter path. Root cause was NOT a JIT regalloc bug (initial
misdiagnosis): the call-site argument type-conversion loop was gated on
`a < g->prog->n_funcs` — comparing the argument index against the FUNCTION count.
For `f(a,b,c)` with 2 functions (f, main), `n_funcs=2`, so the 3rd argument (a=2)
failed `2 < 2` and its double→int conversion was skipped. The interpreter appeared
correct only because it reads the raw arg slot; the frontend never emitted the
conversion for a≥n_funcs on either path.

Fix: remove the outer `a < g->prog->n_funcs` gate — the inner loop already
bounds-checks against the callee's `n_params`. **RULE: when gating per-argument
logic, bound against the callee's PARAMETER count (`func_ast[fid]->n_params`), never
the program's function count — they coincide only when a program has exactly as many
functions as the callee has params. Diagnostic that would have caught it faster:
interpreter-vs-JIT divergence where the interpreter is "right" often means the
frontend emitted different (fewer) MIR ops, not that the JIT is wrong — check the
frontend condition first.**

## R181 — mir_lvalue_elem_type must resolve struct member types (DOT/MEMBER/ARROW)

`mir_lvalue_elem_type` handled IDENT/INDEX/DEREF but NOT DOT/MEMBER/ARROW, so
`mir_is_float_node(s.double_member)` returned false. A direct cast or comparison on
a double struct member — `(int)s.d`, `s.d==1.0`, `s.d*2` — then truncated the raw
IEEE-754 bits instead of converting (DTOI), reading garbage. `d=s.d; (int)d` worked
only because the assignment detected float via the var type, not the member.

Fix: for DOT/MEMBER/ARROW, resolve the member's declared type from the struct
definition — `mir_dot_struct_type(g, n->left)` (the LEFT operand, not the DOT node
itself — a easy mistake) then look up the member kind in the mir_struct_t and
return a minimal HDType. **RULE: mir_lvalue_elem_type is the single type-resolution
choke point for lvalue float/width detection — it MUST cover every lvalue form
(IDENT, INDEX, DEREF, DOT, MEMBER, ARROW) or casts/comparisons/compound-assigns on
the uncovered form silently use integer ops on float data. Also: move struct-helper
forward decls above it so they're visible (C implicit-int conflict otherwise).**

## R182 — Compound-assign float detection must cover struct-member lvalues

The compound-assign `is_float` detection checked IDENT / DEREF-of-pointer / FLOAT_LIT
but NOT DOT/MEMBER/ARROW/INDEX, so `si.a += 10` on a double struct member used
integer ADD on the double bits (a no-op — `si.a` stayed 150). Fix: after the
literal/IDENT checks, if the left lvalue is DOT/MEMBER/ARROW/INDEX, set
`is_float = mir_is_float_node(g, n->left)` (which now resolves member types via
R181). R181 and R182 are a pair: fixing the type resolver alone is not enough —
every consumer that does its own float sniffing (compound-assign, cast, comparison)
must be pointed at the resolver too.

## Debugging recipe — isolating a HolyD frontend miscompute

The fastest path from a failing gauntlet test to the root cause, used repeatedly
this session with high yield:

1. **Extract the exact failing source** from the suite C file with a python regex
   on `"<test_name>", "<escaped src>", <expected>` and `.encode().decode('unicode_escape')`
   — do not retype the test from the FAIL line.
2. **Bisect by sub-check**: the wcc tests return a distinct code per failed `if`;
   run the whole file, read the returned code, then shrink to just that check.
3. **Shrink to a minimal repro** with a `probe()` shell helper
   (`r=$(timeout 10 ./test_single "$1" "$2" ...)`) testing one operation at a time.
4. **Store-vs-load vs use**: assign the member/element to a temp (`d=s.d; (int)d`)
   and compare to the direct form (`(int)s.d`). If the temp works and the direct
   form does not, the bug is downstream type detection (cast/comparison), not the
   load — this separated R181 (type resolver) from a phantom JIT bug.
5. **Interpreter-vs-JIT**: force the interpreter path by adding a recursive helper
   (routes via prog_has_recursion). If the interpreter is correct and the JIT is
   wrong, suspect the frontend emitted different MIR first (R180 was exactly this —
   a frontend condition, not a JIT regalloc bug). Check the frontend gate before
   blaming codegen.
6. **Debug print at the decision point**: add a one-line `fprintf(stderr,...)` at
   the handler's type/offset resolution (e.g. after `mir_struct_member_offset`) to
   confirm the resolved type/offset/base — restore from a backup copy after. This
   immediately showed R181's `struct_type`/`offset` were correct and the value was
   fine, pointing at the cast.

PITFALL: `test_single` compares the RAW 64-bit result, but the gauntlet truncates
to 8 bits (`& 0xFF`). A `return 100=='a'` looks like a compiler bug until you
remember `'a'`==97 — verify the expected value is what C says before investigating.
Several false alarms this session were wrong expected values, not miscompiles.

## R183 — Unsigned div/mod if EITHER operand is unsigned (usual arithmetic conversions)

The HD_AST_DIV and HD_AST_MOD handlers required BOTH operands to be unsigned to
emit MIR_UDIV/MIR_UMOD. Per C usual arithmetic conversions, if either operand is
unsigned the other converts to unsigned, so the operation is unsigned. Requiring
both made `unsigned_long % 2000` (int literal) use signed idiv and return -1
instead of 1615. Fix: use OR (`mir_is_unsigned_node(left) || mir_is_unsigned_node(right)`).
Signed operands stay signed (`-17 % 5 == -2` verified). **RULE: for any op whose
signedness follows the usual arithmetic conversions (div, mod, compare, shift
count), the result is unsigned if EITHER operand is unsigned — `&&` is almost
always wrong. Audit div/mod/compare together.**

PITFALL: `4294967295U % 1000` is 295, not 655 — recompute the expected value by
hand (4294967295 = 4294967*1000 + 295) before assuming a miscompile. The 32-bit
unsigned modulo was already correct; only the mixed signed/unsigned case was
broken.

## R184 — Same-tag struct/union redefinition on a var needs disambiguation

An inline struct/union definition on a var (`struct T{int x} s1;`) is NOT emitted as
a standalone HD_AST_STRUCT_DECL (only a bare `struct T{...};` is), and the parser
dedups `named_types` by tag (redefinition replaces). So a same-tag redefinition
with different members (`struct T{int x} s1; struct T{int y} s2;`) left only the
last layout registered — `s1.x` resolved via s2's layout and read 0. Same root
cause blocks `union tag` shadowing `struct tag` (union_shadows_struct) and nested
same-tag structs (c_testsuite_064722).

Fix: in the VAR_DECL handler, when the var's inline `n->type` has members and a
same-tag entry exists with different members (or none exists), register the var's
specific type under a disambiguated name (`tag#N`) and set the var's
`struct_name` to it, so each var uses its own declaration's layout. The var's
`struct_name` is what DOT/MEMBER offset resolution keys on, so disambiguating the
name is sufficient — no change to the lookup path. **RULE: the parser's
named_types table is a single-slot-per-tag map; any construct that declares a
struct/union inline on a var with a tag that may be redefined must register its
own layout under a unique key, or member offsets silently use the last
declaration's layout.**

## Debugging technique — fprintf at the resolver to find WHICH entry is returned

When a struct/union member reads the wrong value, add `fprintf(stderr,...)` inside
`mir_find_struct` printing the returned index, `n_structs`, and `member_names[0]`.
This immediately showed only ONE "tag" entry existed with the union's members
(x,y) — proving the struct entry was never registered (not a lookup-direction
bug). Without it, the natural assumption ("search finds the wrong one of two
entries") sends you auditing the search loop instead of the registration path.
Restore from a backup copy after (keep a `cp file.c /tmp/backup.c` before editing).

## R185 — Struct member float conversion on assignment + arrow complex-base resolution

Three related struct-member fixes:

1. Assignment to a struct member (`s.l = 58.207`, `s.l = g()/l`) did not resolve
   the LHS member type, so a double RHS assigned to a long/int member stored raw
   IEEE-754 bits instead of converting (DTOI). The assignment's `lhs_type`
   resolution covered AST/IDENT/INDEX but not DOT/MEMBER/ARROW — now uses
   `mir_lvalue_elem_type` (R181). Also `rhs_is_float` now falls back to
   `mir_is_float_node` (catches DIV-of-doubles / calls returning double, which
   have NULL type and aren't NEG-of-FLOAT_LIT).

2. `mir_dot_struct_type` now handles TERNARY (`(cond?p:q)->m`), ASSIGN
   (`(p=x)->m`), and CAST (`((struct T*)p)->m`) bases.

3. ARROW `mir_lvalue_addr` (`ps->m = val`) uses `mir_dot_struct_type` as a
   fallback when the base isn't a simple IDENT.

**RULE: the assignment handler's lhs_type/rhs_is_float resolution is a SECOND
type-resolution choke point (besides mir_lvalue_elem_type) — it must cover every
lvalue form and every float-yielding RHS, or member assignments silently store
raw bits. The rhs_is_float NEG-of-FLOAT_LIT special-case is not enough; use
mir_is_float_node as the general fallback.**

## R186 — mir_lvalue_elem_type must peel one dim per nested INDEX level

For a nested index a[i][j], mir_lvalue_elem_type recursed into the base a[i] and
returned its type AS-IS, leaving one ARRAY level too many: on double[M][N],
d[i][j] resolved to ARRAY(double) instead of double. The char_elem detection
(line ~4858) compensates with its own while-loop descent, but the FLOAT
detection (mir_is_float_node, used by `==` and compound-assign) did NOT — so
`d[i][j] == 1.0` and `d[i][j] += x` took the integer path and ditof'd the raw
double bits (MIR: `ditof v25 = v23` on the loaded double -> compares a denormal).
2-D long/int/char reads were unaffected (int low-byte coincidentally matched;
char has its own byte-load path).

Fix: for a nested INDEX base, recurse then peel one `.base` (the indexed
dimension) — a[i][j] on double[M][N] -> double (F64). **RULE: mir_lvalue_elem_type
is a THIRD type-resolution choke point (with the assign handler and
mir_is_float_node). Every consumer that keys off it for float/width decisions
must see the SCALAR element type, not an ARRAY. When a detection path has its
own compensating descent (like char_elem's while-loop), the bug hides there but
surfaces in the paths that don't (float). Diagnose nested-array float bugs by
dumping MIR (WUBU_DEBUG_MIR_AFTER=1) and looking for a stray ditof/floor on a
loaded value.**

Debug recipe that cracked it: `WUBU_DEBUG_MIR_AFTER=1 ./test_single '<src>' <exp>`
dumps the MIR; the stray `ditof v25 = v23` on the loaded d[i][j] immediately
revealed the value was being treated as an int, pointing straight at
mir_lvalue_elem_type.

## R187 — double-array brace-init int->double + DEREF(ptr-arith) float detection

Two related fixes (wcc chapter_15 compound_pointer_assignment, whose double_array
does `static double arr[6]={1..6}; double*ptr=arr; *(ptr+=5)`):

1. **Brace-init of a double array from int literals** stored the raw int bits,
   not doubles. The array-element conversion (brace-init path) skipped entirely
   when `base->kind==F64`, so `double d[3]={1,2,3}` stored int 1/2/3 and `d[1]`
   read a denormal (MIR: `store mem[..] = 2`). Fix: for an F64 array element,
   convert non-float elements int->double (DITOF); leave float literals alone.

2. **mir_lvalue_elem_type DEREF case** only handled DEREF(IDENT), so
   `*(ptr+5)` and `*(ptr+=5)` on a double* resolved to NULL type ->
   mir_is_float_node missed them -> `*(ptr+5) == 1.0` ditof'd the loaded double
   bits (compared a denormal; MIR: `ditof v55 = v53` on the loaded value). Fix:
   resolve the pointee from the ADD/SUB/ADD_ASSIGN/SUB_ASSIGN left operand
   (PTR, or ARRAY decay).

**RULE: mir_lvalue_elem_type + mir_is_float_node are THE recurring type-resolution
choke points. Every new lvalue/expression form must be handled in BOTH: nested
INDEX (R186), DEREF of pointer-arithmetic or compound-assign (R187). When a
float op misbehaves, dump MIR and look for a stray ditof/dtoi on a loaded value —
that always means the operand's type resolved to non-float.** Also: the
brace-init array-element conversion is a FOURTH conversion site (besides the
assign handler, compound-assign, and the cast) — it must convert int->double
for F64 element arrays.

## R188 — pointer-to-multi-dim-array: parser (var + first/non-first param) + ptr-arith scale

Full support for `double (*p)[3][5]` (pointer to a 2-D array) required four fixes
across holyd_parse.c and holyd_mir_eval.c:

1. **Variable declarator** `double (*p)[3][5]`: the ptr-to-array path consumed
   only one [N]; now consumes all bracket dims and builds nested
   PTR(ARRAY(ARRAY(...))).
2. **First function param** `f(double (*p)[3][5])`: the param parser's `(*`
   detection assumed function pointer; now distinguishes `(*name)(...)` [func ptr]
   from `(*name)[N]...` [ptr-to-array] by the token after `(*name)`.
3. **Non-first function param** `f(a, double (*p)[5])`: the comma-loop param
   parser (a SEPARATE code path) treated `(*name)` as a func ptr AND advanced
   past the name without strncpy — so the 2nd ptr-to-array param bound with an
   EMPTY name, and the SUB's b_is_pointer var-table lookup never matched it
   (pointer subtraction divided by 1 -> raw byte diff). Fixed to mirror the
   first-param path (store pname + ptr-to-array branch).
4. **Pointer arithmetic scale** (ADD + mir_node_ptr_scale): multi-dim array
   operands must scale by the FULL element byte size (product of inner dims * 8),
   not one dim. ADD used one dim (3*8=24) while SUB used the full product
   (3*5*8=120); the mismatch made (m[2]+4)-(m[2]+1) divide 72 by 120 -> 0.
   mir_node_ptr_scale also needed an INDEX case (arr[i] on a multi-dim array
   decays to a pointer to the sub-array).

**RULE: pointer-to-array support touches FOUR independent sites (var declarator,
first-param parser, non-first-param comma-loop parser, ptr-arith scale in both
ADD and mir_node_ptr_scale). The non-first-param comma loop is a duplicate of the
first-param logic and is easy to miss — always fix BOTH param paths together.
Debug recipe: fprintf the param name+typekind at the param-binding loop
(holyd_mir_eval.c ~6422) to catch an empty-name param, and the SUB's
ptr_scale/b_is_pointer right before do_divide (~3929) to catch a scale-0 or
b_is_ptr=0 subtraction.** wcc chapter_15 pointer_arithmetic_pointer_diff now
passes (int/long/double(*)[3][5]/double(*)[5] diffs).

## R189 — struct-member type resolution: RHS + PTR/ARRAY-of-struct members

Nested-struct member access (wcc chapter_18 scalar_member_access_nested_struct)
needed four fixes, all in the struct-member type-resolution family:

1. **Assignment RHS** `s.a = s.b` (double member = char/int member): rhs_type
   only resolved IDENT nodes, so the int->double DITOF didn't fire. Now resolves
   DOT/MEMBER/ARROW via mir_lvalue_elem_type. (5th conversion site.)

2. **member_type_names for PTR-to-struct / ARRAY-of-struct members**: the
   registration (TWO paths: HD_AST_STRUCT_DECL ~1590 AND the parser named_types
   path ~6326) required the member type's OWN name, but for `struct inner *p` /
   `struct inner arr[4]` the struct name is on the BASE (the PTR/ARRAY type's name
   is empty). Fixed both to record the base struct name.

3. **mir_dot_struct_type ARROW case**: ps->m (arrow through a pointer member)
   had no ARROW case -> offset -1 -> read 0. Added it (resolve base's pointee
   struct, then the member's type name).

4. **mir_node_ptr_scale ARROW case**: (sp->in_array + 3) must scale by
   sizeof(struct inner) (the array/pointer member's element struct size via
   member_type_names -> total_size*8), not 8/1 -- else it clobbered in_array[0].a.

**RULE: struct member type resolution is a recurring choke point with MANY
consumers (member_type_names registration [2 paths], mir_dot_struct_type,
mir_node_ptr_scale, mir_lvalue_elem_type, the assign handler's lhs/rhs_type,
mir_is_float_node). Each must handle PTR-to-struct and ARRAY-of-struct members
(name on the BASE), not just direct struct members. When adding a struct-member
feature, audit ALL these sites. Note the member_type_names registration exists
in TWO places (AST STRUCT_DECL and the parser named_types path) -- fix both.**
test_auto_dot/test_static_dot now pass; test_auto_arrow still has a *sp->
in_array->ptr deref-after-(in_array+3)-write crash (separate follow-up).

## OPEN (architectural) — malloc/calloc return real pointers the JIT can't deref

`int* vp = malloc(8); *vp = 80;` (and calloc) crashes. malloc/calloc are resolved
via dlsym and return REAL heap addresses, but the JIT's LOAD/STORE compute
`[rbx + offset]` where rbx = prog.mem base and `offset` is the VR's value. When
the VR holds a real heap address (0x5555...), `rbx + heap_addr` is a wild write →
segfault. `&local` works because that's a prog.mem byte-offset. This is the
inverse of the MIR_TO_PTR problem (R171): there, offsets needed converting TO
real pointers for external calls; here, real pointers from dlsym'd allocators are
used as memory bases but the JIT treats all values as offsets.

Blocks every malloc/calloc-using test (a large class, incl. wcc
scalar_member_access_arrow's calloc path, and many c_testsuite). Fixing it needs
the JIT to distinguish real-pointer VRs from offset VRs (a pointer-tagged memory
model) or route all allocation through prog.mem — a significant architectural
change, NOT a localized handler fix. Verified pre-existing (crashes on the base
commit). Do not chase individual malloc tests without addressing the model.

**RESOLVED 2026-10-14 (commit 55c6925) — see references/compiler-memory-model-7hop-2026-10-14.md.** The 7-hop research (chibicc/tcc/Glow/CompCert) converges on: pick ONE pointer model. Implemented Option B (managed heap, Glow-style): malloc/calloc/realloc/free return byte offsets into a 4 MB heap at the tail of prog.mem (wubu_mir.c bump allocator), routed from the JIT dlsym path. Heap pointers are first-class offsets — deref via MIR_LOAD/STORE works, MIR_TO_PTR gives libc the real address. Chose Option B over chibicc's real-addresses-everywhere because the interpreter oracle is offset-based too. gauntlet_v3 1536->1562 (58.5%). Gap CLOSED.

## R184 — Byte-packed char-array STRUCT MEMBER init must use byte stride, before the generic BRACE_INIT case

A byte-packed char/u8 ARRAY **struct member** initialized from a nested brace list
(`struct{signed char arr[3];} s = {{8,7,6}}`) fell into the generic
`if (elem->kind == HD_AST_BRACE_INIT)` branch, which stores each leaf at 8-byte
CELL stride via `mir_store_brace_leaves`. So `s.arr[1]`/`s.arr[2]` read offset+1/+2
(still 0) while only `arr[0]` survived. Fix: a `member_byte_array` branch that runs
BEFORE the generic BRACE_INIT case, storing each leaf at BYTE stride 1 (store8) from
the member offset. **RULE: the generic nested-brace leaf path assumes cell stride —
any byte-packed member (char/u8 array inside a struct) needs its own byte-stride
branch placed BEFORE that generic case, or it is swallowed by it. Same class as
R173/R177 (byte vs cell), now in the struct-init path.**

## R185 — Struct copy from an LVALUE RHS must resolve the source ADDRESS, not load the value

Struct copy — both `HD_AST_ASSIGN` (`s = big.sub`) and the VAR_DECL struct-init path
(`struct inner s = big.sub;`) — resolved the source by IDENT only
(`mir_find_var_addr`) and otherwise used `val = mir_gen_expr(rhs)`. For a struct
lvalue RHS (DOT/MEMBER/ARROW/INDEX/DEREF), `mir_gen_expr` loads the member VALUE and
the copy used it as a base pointer → garbage. Both paths now, for a
DOT/MEMBER/ARROW/INDEX/DEREF RHS, resolve `src = mir_address_of(g, rhs)` and copy
cell-by-cell from that address. **RULE: a struct copy source is an ADDRESS; whenever
the RHS is any lvalue form other than a bare IDENT, get its address with
mir_address_of — never mir_gen_expr, which yields the loaded value.**

Known remaining (deferred, architectural): copying a struct that CONTAINS a
byte-packed char-array member loses `arr[1]`/`arr[2]` — the cell-by-cell copy
undercounts the char array's cell span because `n->type->size` (struct size in
cells) doesn't round a byte-packed array member up to a cell boundary. Fixing it
needs the struct-size computation to account for byte-packed array members; that is
a cell-model layout change, not a localized handler fix.

