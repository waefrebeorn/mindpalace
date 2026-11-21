# HolyD JIT codegen bugs: the four that mattered (2026-09-30)

All found by driving `hd_eval` through `selfhost_battery`
(`isa-test/selfhost_battery.c`). Battery is now **155/155**.

Method that worked: build a standalone probe linking the same sources as
`test_battery`, then break in gdb on the exact line and read AST/buffer state.
Use `scripts/build-holyd-probe.sh <probe.c>` to build it (encodes the source
list, flags, and the two gdb incantations below).
Two rules that would have saved hours:

1. **Dump the PREPROCESSED text first.** Twice the bug was in
   `wubu_preprocess`, not the parser or codegen. Seeing
   `source="(0)?0:42;"` vs `effective="(0)?0;"` ended the search instantly.
2. **Disassemble, don't hand-decode bytes.** `gdb -ex 'dump binary memory
   /tmp/code.bin gen.code gen.code+gen.code_size'` then
   `objdump -D -b binary -m i386:x86-64 -M intel`. I misread `0f 18 05` as
   an SBB twice; it was a prefetchnta's opcode. Three wrong theories
   (cell/byte offset mismatch, qword rounding, missing HD_AST_ADDR case) all
   came from misreading hex dumps.

## The two size functions -- do not conflate them

The single subtlest bug. Two representations are both legitimately in use:

- `hd_type_size()` = **true C byte size**. `sizeof` depends on this;
  `sizeof(struct S{int a;int b;})` must be 8.
- `hd_type_alloc_size()` (new, `holyd_parse_ast.c`) = **bytes to reserve**,
  cell-inflated for structs: `t->size * 8`.

The parser lays structs out in CELLS: `t->size += ceil(hd_type_size(member)/8)`
per member (`holyd_parse.c` ~line 407), and `members[].offset` stores that
running cell count. Codegen addresses a member as `offset * 8`
(`holyd_codegen_expr.c` lines 1563/1594 do `* 8`; `emit_lvalue_addr` line 369
relies on the `add rax, off*8` at line 380).

Using `hd_type_size` for allocation gave a struct 8 bytes while addressing
`members[1]` at byte 8 -- one past the end -- so it aliased the next global.
Symptom: `struct S s; s.b=20; int* p=&s.b; *p;` returned garbage while
`s.b`, `*(&s.b)` and `(long)&x` were all fine. The stack-local path in
`gen_stmt` had been special-casing `t->size*8` by hand; that convention is
now `hd_type_alloc_size()` for both sites.

Tell-tale: gdb shows `data_size=16` but `s` at global_offset 0 and `p` at 8.

## The other three

1. **`strip_bitfields()` deleted ternary else-branches.** It stripped `:` +
   digits whenever the preceding non-blank char was alnum/underscore (its
   test for a bit-field width `int x : 3;`). In `(0)?0:42` that char is the
   digit `0`, so `:42` was deleted. Parser then built a ternary with
   `else_branch == NULL` and EVERY conditional returned the THEN value.
   Fixed with a per-line pending-conditional depth.

2. **Label bodies dropped / trailing label treated as an expression.**
   `gen_stmt`'s `HD_AST_LABEL` registered the offset but never emitted
   `node->body` (the parser attaches the labelled statement there), and a
   trailing `label: expr;` fell through `hd_eval`'s last-statement chain
   into `gen_expr`, which emits nothing for a LABEL. `goto loop` jumped into
   nothing at 99.9% CPU. `mir_gen_stmt` already did both right -- the JIT was
   the outlier. Use the MIR interpreter as the semantic oracle.

3. **`selfhost_battery` could not finish.** `run_isolated` did a blocking
   `read()` with no deadline, so one spinning child hung `make test`
   forever with no output. Now a 5s `select()` budget + SIGKILL.

## Test-expectation bugs are real bugs

`ptr cast` asserted `(int)(long)(void*)(long)&x == 0`. False in gcc too.
The battery's header *claims* it cross-checks every expectation against gcc
("a WRONG expected in the battery is caught (we learn both ways)") -- that
check was documented but never implemented, which is how the placeholder
survived. Verified HolyD against gcc before editing anything.

A raw address is not reproducible under ASLR, so such probes must assert a
**property** (e.g. `*(int*)(long)(void*)(long)&x` == 42), never a literal.

## Still open

None in this battery. `make test` progress is tracked in
`references/make-test-triage.md`.