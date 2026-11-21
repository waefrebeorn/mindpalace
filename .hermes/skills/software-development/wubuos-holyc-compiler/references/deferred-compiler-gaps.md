# Deferred compiler gaps + the compound-expression theme

WuBuOS HolyC compiler (`holyd_mir_eval.c` etc.). Topical depth for bugs that are
known, root-caused, but deferred; and the meta-pattern behind most of them.

## The recurring theme

Every type/pointer/struct bug in this compiler is the SAME class: **type info is
resolved by a different code path for a compound expression (ternary, call, chained
ADD/SUB, deref, nested index) than for a bare IDENT.** When a type-sensitive op
misbehaves ONLY on a compound operand but works on a scalar/bare-ident, the fix is to
extend the resolver to that node kind — do NOT add a one-off branch at the use site.
Resolvers to extend:
- `mir_node_ptr_scale(g,n)` — pointer byte-scale for any node (IDENT/CALL/DEREF/ADD/SUB/TERNARY).
- `mir_is_float_node(g,n)` — whether an expr holds a double (FLOAT_LIT/IDENT/CALL/arith/INDEX/DEREF/MEMBER).
- `mir_dot_struct_type(g,n)` — struct type name for a DOT/ARROW base (IDENT/INDEX/ADD/SUB/TERNARY/DEREF).
- `mir_lvalue_elem_type(g,n)` — element type of an lvalue (INDEX/DEREF/MEMBER/IDENT).

RULE: a pointer operand can arrive via ANY expression; and `*p` of a scalar pointer is
a VALUE (pointee), not a pointer — only `*pp`/`*parr` (ptr-to-ptr / ptr-to-array) yields
a pointer. Verify pointer-arith expected values with gcc — array indices are easy to
miscount.

A SECOND recurring class: **shadowing** — a var-NAME lookup that searches the table
forward resolves a shadowing local to a same-named global. Symptom: a function-local
array/pointer misbehaves ONLY when a same-named global exists, and reads the global's
dimensions. Fix: search from the END (most-recent wins), matching `mir_find_var_addr`.
See `mir-eval-correctness.md` ("Shadowing").

## Deferred gap 1 — struct member access on a ternary result (STILL OPEN)

`(cond?a:b).member` returns 0/garbage. Deeper than type resolution: a struct-valued
ternary does NOT multi-cell copy (`struct S c = (f?a:b);` is also wrong). So the
ternary yields a wrong value/address, not just a missing type. `mir_dot_struct_type`
handles TERNARY and the DOT/MEMBER value path has a general fallback that evals the
base — but struct-copy semantics for ternary / return-by-value is the real gap. Start
here if revisiting; do NOT just add another type-resolution branch.

## Deferred gap 2 — nested string initialization (SOLVED)

`char a[N][M]={"ab","cd"}` used to store wrong. SOLVED — see
`references/mir-eval-correctness.md` ("Nested char-array string initialization").
The row offset bug (single char read back a constant) was a write/read stride
mismatch: NESTED char arrays are cell-per-char (stride 8), not byte-packed. The
`partial_initialize_via_string` wcc test passes. Kept here only as the diagnostic
trail: read one byte via `(unsigned char)a[i][j]` and compare to the brace-init
path (`{{97,98},{99,100}}`) which always worked.

## Deferred gap 3 — fn-local char[] string INIT with a same-named global (STILL OPEN)

`int t(){char x[8]="hi"; ...} int x;` — the string init writes byte 0 only (x[0]
reads 0) when a same-named global exists. Manual assign and the no-global case both
work. Write-path (1-D string init), rarer than the read-path shadowing cases that
were fixed. See `mir-eval-correctness.md` ("Shadowing").

## Revert discipline

When a fix is not a clean win (produces wrong non-zero results, or needs a second
deeper fix), `git checkout <file>` and move on — never land a half-fix that could
regress the `make test` 195/195 + `gauntlet_runner --core` 247/247 gates.
