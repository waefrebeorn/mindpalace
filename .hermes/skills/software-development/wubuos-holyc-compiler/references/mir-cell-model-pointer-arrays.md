# MIR cell model (holyd_mir_eval.c) — pointer/array pitfalls + bug-hunting loop

Reference for the WuBuNOS HolyC compiler's MIR interpreter. The always-on rule
lives in SKILL.md; this file carries the topical depth.

## The cell model

The MIR interpreter stores values in 8-byte CELLS, not C bytes. Arrays are
cell-indexed; a `char[]` is byte-packed (1-byte stride). Always resolve the
element type through the AST chain before choosing a load/stride, or you read a
whole cell instead of a byte. Every fix below was verified against gcc.

## Pointer/array/char pitfalls (fixes landed)

- Inferred array size: `int a[]={...}` / `char s[]="..."` must set
  `array_size` + `size` from the init (brace `n_args`, or strlen+1 for a
  string). Parser VAR_DECL path (first + comma declarators).
- `*(a+i)` on a 1-D scalar array: DEREF-of-ADD must LOAD (only skip for a true
  sub-array, i.e. `ARRAY(ARRAY)` element). Returning the address gave the
  address value instead of the element.
- `(a+1)[0]`: `mir_address_of` needs ADD/SUB cases — the pointer VALUE of
  `a+1` IS the address to index from (no ADD case → garbage).
- Byte-load detection (DEREF + INDEX paths): resolve the pointee through
  IDENT, ADD, pre/post INC/DEC (`*s++`), and INDEX children (`d[0]`, `d[0][0]`).
  A `char*[]` element is `ARRAY(PTR(I8))` → base->base is the byte type.
- `d[i][j]` on an array of pointers: INDEX base-resolution `use_value=1` when
  the root var is `ARRAY` whose element is `PTR` (load the pointer, don't
  address the slot). Inner char* index strides by 1 (mir_index_stride past the
  array dims).
- `ptr - array`: an ARRAY name on the right of SUB decays to a pointer — mark
  `b_is_pointer` so the difference divides by scale (else it multiplies the
  base address by scale → garbage).
- `p += n` on a pointer: compound-assign must scale the RHS by pointee size
  (cell 8, char 1). `p = p + n` and `p++` already scaled; ADD_ASSIGN did not.
- Flat brace-init of a multi-dim array (`int a[2][2]={1,2,3,4}`): the per-row
  init loop assumes each init arg is a nested BRACE_INIT and bounds the loop by
  the outer dimension, so flat scalars only filled the FIRST row. Detect a flat
  scalar init on an ARRAY(ARRAY) type and store all scalars into consecutive
  cells (byte-packed for char); skip the row loop.
- char/u8 brace-init must BYTE-PACK: set `elem_sz=1` and store via
  `wubu_mir_store8` (NOT the full-cell `wubu_mir_store`), else consecutive
  elements clobber each other and `b[]={255,0,128}` loses `b[2]`. The read path
  already strides 1 for byte-packed arrays; the init path must match.
- `_Bool`: the C99 spelling was not a lexer keyword (only `bool`/`Bool` were) —
  add it as a BOOL alias. Then normalize nonzero→1 in BOTH the VAR_DECL init
  truncate path AND the CAST node (`mir_gen_cast` AND the `HD_AST_CAST` case are
  separate code paths; fixing one leaves the other broken).

## Fast single-test iteration (test_single)

Build `test_single` (`make test_single`) and run
`./test_single '<C source>' <expected_exit>`. It compiles+interprets via
hd_build_mir. VERIFY the expected value with gcc first
(`gcc -o /tmp/v /tmp/v.c && /tmp/v; echo $?`) — several "failures" were wrong
test expectations (`*p-- + *(p+1)` is 18, `*(p++)+*(p++)` is UB). Always run
`make test` (195/195) before committing a fix.

## Research-driven bug hunting (probe → gcc oracle → root fix)

When the user asks for research-driven compiler fixes ("online research... take a
lot of code from every compiler... actually knowing what you're doing"), do NOT
chase individual gauntlet failures one at a time. Instead:

1. Build `test_single` (`make test_single`).
2. Probe BATCHES of common C constructs with
   `./test_single '<C source>' <expected_exit>`, one probe per construct.
3. VERIFY every suspicious expected value with gcc first
   (`gcc -o /tmp/v /tmp/v.c && /tmp/v; echo $?`) before calling it a bug — a large
   fraction of "failures" are wrong test expectations (UB constructs like
   `*(p++)+*(p++)`, arithmetic errors, invalid C). gcc is the oracle.
4. Fix at the root in holyd_mir_eval.c / holyd_parse.c, not per-test.
5. `make test` (195/195) MUST be green before every commit.
6. Commit one fix per commit with the construct family named; push after a batch.

Batch across families (pointer arith, char byte-loads, char* arrays, brace init,
structs, unions, enums, floats, control flow) so one probing round surfaces many
bugs; group fixes that share a mechanism into one commit.

## gcc_torture gauntlet: EROR is mostly incomplete test excerpts, not parser bugs

The `gcc_torture` suite array is `{name, code, expected, cat, ?, timeout}`. MANY
entries' `code` field is only the `main` body excerpt and references helper
functions/globals (`foo`, `ok`, `test1`, ...) that are NOT in the code field.
Those compile-fail on undefined symbols → EROR (crash/timeout/parse), which is
NOT a HolyD parser bug — do not chase them as such. Only entries whose `code`
field is a COMPLETE translation unit (full helper defs + `main`) are real
parser/codegen targets. Before investigating an EROR test, read its `code`
field and confirm it is self-contained.

The runner is also SLOW (~93 tests / 120 s — each JIT-compiles + runs) and gets
killed (EXIT=143) at the tool's ~600 s cap long before finishing all 1183
gcc_torture tests; the visible PASS/FAIL/EROR tally on a killed run is a
partial prefix, not the real rate. To measure real improvement, probe complete
constructs directly with `test_single` + the gcc oracle rather than reading a
partial gauntlet tally.
