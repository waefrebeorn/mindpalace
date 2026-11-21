# Compiler parser-feature fixes & binary execution legs

Two clusters of compiler/runtime work. Both hold the core gauntlet at 247/247
(3458 runs) — never trade the gate for a feature.

## Parser-feature fixes (designators, qualifiers, old-style defs)

C11/GCC feature bugs cluster in the parser + the MIR offset path.

- **Array/struct member `offset` is a BYTE offset; each cell is 8 bytes.** A
  designated initializer `a[i]=v` (and any index→offset conversion) must scale
  by element size: `offset = (int64)index * elem_sz` (elem_sz=8). Using the raw
  index as the byte offset stores to the wrong cell (`int a[3]={[0]=5,...}`
  returned 460293). The MIR `addr` is byte-addressed; the struct registry's
  `member_offsets[]` are in CELLS and the codegen does `*8` — keep those two
  unit conventions straight and never mix them in one expression.
- **`parse_expr` IS `parse_comma` — it eats element separators.** Parsing each
  initializer element (compound literals, any brace list) with `parse_expr`
  consumes the commas between elements, so `{10,20,30}` collapses to ONE node
  (the last operand's value) and every element stores to cell 0. Use
  `parse_assign` for each element (it stops at commas); reserve `parse_expr`
  for a whole comma expression. Symptom: `(struct T){10,20,30}` → all members =
  30, sum 30 not 60.
- **A freshly `parse_type`'d cast type has member offsets ALL ZERO** —
  `parse_type` does not run the struct-registry offset computation, so
  `n->type->members[].offset` is 0 for every member in a compound literal /
  cast type. `*8` won't help (still 0). Route the offset through the struct
  registry (`mir_struct_member_offset_by_index` by name+index — the same source
  the working normal-init path uses), with `members[].offset*8` only as a
  fallback.
- **Order-independent type qualifiers need BOTH orders handled.** `double
  _Complex` (base first) and `_Complex double` (qualifier first) are both
  valid. The base-type switch cases (`HD_KW_F64`, `HD_KW_I32`) must consume a
  TRAILING `_Complex`; the `_Complex` case consumes a trailing base type. Miss
  the base-first form and the qualifier token is left unconsumed → build fails.
  (Qualifier-first-with-double can still be gated by the declaration parser —
  verify which form the declaration entry accepts before assuming a switch fix
  is enough.)
- **K&R function definitions: detect a bare-identifier first parameter,
  collect names, then parse the post-`)` declaration list.** Old-style
  `int add(a, b) int a; int b; { }` must be detected BEFORE `parse_type` (which
  chokes on a bare ident), collect the param names, then after `)` parse the
  `int a; int b;` decl list to assign types (unlisted params default to int).
  There may be TWO function-declaration handlers in the parser (a primary and a
  secondary); confirm which one the source actually reaches before patching —
  a debug `fprintf` that never fires means you edited the unreachable one.
- **`typedef name[expr]` (VLA typedef) needs an array-suffix loop in the
  typedef parser.** After the typedef name, consume `[size]` and wrap the base
  in an ARRAY type (size 0 for a variable length), updating the typedef
  registry entry to the array type. Without it the typedef parser's
  `expect(SEMI)` hits `[` and fails.
- **A duplicate `case` for the same token is an immediate compile error** —
  when adding a qualifier branch, check the switch already has a `case` for
  that token elsewhere (e.g. `HD_KW_I32` at the plain-int case) and extend THAT
  case rather than adding a second.
- **Struct field offset is CELLS in the parser path but the codegen MIR `addr`
  is bytes** — the working normal-init path multiplies registry offsets by 8; a
  new path that uses `members[].offset` directly (or multiplies an
  already-cell value again) double- or under-scales. Reuse the exact registry
  helper the working path uses instead of re-deriving the arithmetic.
- **Kernel/module test files (`tools/test_*.c`) are often GITIGNORED** by a
  repo-wide rule — `git add` reports "paths are ignored", the commit lands
  without the test, and the gate is silently broken. After committing a new
  module+test, `git ls-files tools/ | grep <mod>`; if the test is absent,
  `git add -f` it and verify. A committed module whose test file never landed
  is a broken gate.

## Binary execution legs (ELF / PE / Mach-O / DOS)

The runtime "third-party runs ON the AGI kernel" legs are one loader module per
format, all the same shape. Verify each against a REAL binary from a real
toolchain, never only a hand-built image.

- **Common loader shape (all four):** validate the header
  (magic/class/endian/machine/filetype), two-pass over the segment/section
  table — pass 1 computes the page-aligned image extent and bounds-checks the
  arena once, pass 2 copies file bytes into `arena[vaddr-lo]` and zero-fills the
  `filesize..memsize` remainder as BSS — then compute the entry point and
  fail-closed on truncation/bad-machine/arena-too-small. Zero the arena with one
  `memset(image_size)` before the copy pass so BSS is correct without
  per-segment zeroing.
- **Entry = base + (entry_field − lowest_mapped_addr)**, where `base` is the
  address of the arena slot that `arena[0]` (vaddr `lo`) maps to. Getting this
  sign wrong (base + raw entry) is the classic off-by-image bug; test entry with
  a nonzero `lo` to catch it.
- **Verify each leg against a REAL binary, and know which toolchain is on the
  box:** ELF — `gcc -static`; PE32+ — `x86_64-w64-mingw32-gcc`; Mach-O 64 —
  `clang -target x86_64-apple-darwin -c` (object only; a real .o has no
  `LC_SEGMENT_64` so the loader correctly reports no-entry); DOS MZ — `nasm -f
  bin` produces raw code with NO header, so package it under a hand-built MZ
  header in the test. Assert on the real image's fields (segment count, entry,
  image size), not just that load returned OK.
- **PE `SizeOfRawData` is FileAlignment-rounded and MAY exceed `VirtualSize`** —
  clamp the copy to `min(SizeOfRawData, VirtualSize)`; a real MinGW PE (19
  sections) trips the naive `rawsz > vsize → error` check on a perfectly valid
  section. BSS is represented by `VirtualSize > SizeOfRawData`.
- **Mach-O `MH_MAGIC_64` = `0xfeedfacf`** (bytes `cf fa ed fe`);
  `CPU_TYPE_X86_64` = `0x01000007`. Accepted filetypes MH_EXECUTE/DYLIB/BUNDLE;
  MH_OBJECT has no segments (NOENTRY is the correct verdict, not an error to
  suppress).
- **A real DOS payload needs a correct MZ header bolted on** — load-module size
  is `e_cp*512 − (512−e_cblp)` when `e_cblp` is set; relocations live at
  `e_lfarlc` in the header area BEFORE the load module (a table overrunning
  `load_offset` is a layout error); entry is linear `load_seg*16 + IP` with CS
  relative to the load segment.
