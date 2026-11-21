# Byte-Addressable Memory Model — IMPLEMENTED (2026-09-13 → 2026-09-14)

## Status: IMPLEMENTED — Cell-Based Hybrid with uint8_t* Memory

The memory model uses `uint8_t *mem` (byte-addressable) with a **cell-based allocation strategy**: every array element and struct member occupies 1 cell (8 bytes). This avoids width-aware LOAD/STORE (which HolyD lacks) while supporting byte-level addressing for future packed-struct work.

**Score: 1,190/2,668 (45.0%) — parity with baseline (1,188), ahead on writing_c_compiler_full (423 vs 421).**

## Architecture

### Memory Layout
- `prog.mem` is `uint8_t *` (byte-addressable)
- `prog.total_mem` tracks bytes allocated
- `wubu_mir_alloc(n_bytes)` returns byte address, 8-byte aligned
- LOAD/STORE operate on 8 bytes (int64) — no `shl rax, 3` in JIT
- All pointer arithmetic scales by 8 (cell stride)

### Array Allocation
- 1 cell (8 bytes) per element regardless of element type
- `int arr[3]` → 3 cells (24 bytes), `char str[6]` → 6 cells (48 bytes)
- Stride always 8 in `mir_index_stride()`
- Avoids int64 store overlap (writing 8 bytes at offset 0 doesn't corrupt offset 8)

### String Literals
- Stored cell-by-cell: char `i` at byte offset `i * 8`
- `char *x = "Hello"` → x[0] at offset 0, x[1] at offset 8, etc.
- Consistent with array allocation (both use 1 cell per element)

### Char Array Initialization from String Literals
- Special case in VAR_DECL handler: detect `char arr[] = "..."`
- Copy string data cell-by-cell (up to string length)
- **Zero remaining elements** (C standard: uninitialized elements = 0)
- Reallocate array if size not yet determined (`arr_size == 0`)

### Pointer Arithmetic
- ADD handler scales by 8 for: `HD_TYPE_PTR`, `is_ptr_struct`, `is_array` (decay), and `HD_AST_STRING_LIT`
- SUB handler scales by 8 for: `HD_TYPE_PTR`, `is_array`, and `HD_AST_STRING_LIT`
- PRE_INC/POST_INC/PRE_DEC/POST_DEC scale by 8 for pointer types (checked via var table `type->kind == HD_TYPE_PTR`)
- Non-pointer increment/decrement still uses scale 1
- **Pitfall**: SUB handler initially only checked `n->left->type->kind == HD_TYPE_PTR` — IDENT nodes have NULL type, so `ptr - idx` where `ptr` is an int* variable didn't scale. Fix: add var table lookup for `HD_TYPE_PTR` and `is_array`, plus `HD_AST_STRING_LIT` check.
- **Pitfall**: `"string" + N` didn't scale because STRING_LIT nodes don't have `type->kind == HD_TYPE_PTR`. Fix: explicit `n->left->kind == HD_AST_STRING_LIT` check in both ADD and SUB handlers.

### Struct Parameter Copy
- Struct-by-value parameter copy uses `byte_off = m * 8` (not `m`) since addresses are byte offsets
- **Pitfall**: Original code used `m` as offset (cell index), but after byte-addressable rewrite, addresses are byte offsets. Using `m` instead of `m * 8` caused struct members to overlap — `int x` at offset 0, `double y` at offset 1 (byte) instead of offset 8.

### Nested DOT Member Offset
- `mir_address_of` walks DOT chain from right to left
- Accumulates byte offsets using `st->member_offsets[mi] * 8` (cells → bytes)
- Uses root struct type for first lookup, then follows member types
- **Pitfall**: Original code used `mir_dot_struct_type(n->left)` which returned the type of the EXPRESSION (e.g., `inner` for `x.i`), not the containing struct (`s`). Fix: walk the chain from the root IDENT.

### Struct Copy
- Cell-by-cell copy using `total_size` (cells) with `byte_off = m * 8`
- Three copy paths: assignment, initializer, designated initializer — all use same pattern

## Key Files Changed

- `wubu_mir.h`: `int64_t *mem` → `uint8_t *mem`, `total_mem` in bytes
- `wubu_mir.c`: `wubu_mir_alloc(n_bytes)` returns byte address with 8-byte alignment
- `wubu_isa_x86_64.c`: Removed `shl rax, 3` from LOAD/STORE/MIR_TO_PTR
- `wubu_mir_interp.c`: `uint8_t *mem`, byte-addressed LOAD/STORE
- `holyd_mir_eval.c`: All address computations in bytes, pointer scaling, string literal copy, char array init
- `holyd_parse.c`: Member offsets still in cells (×8 at use sites)
- `test_gauntlet_runner.c`: `uint8_t *mem_ptr`

## Pitfalls Encountered

### 1. Inconsistent pointer scaling (most common)
When adding pointer arithmetic scaling, ALL paths must be updated:
- ADD handler (line ~2368)
- SUB handler
- PRE_INC/PRE_DEC handlers
- POST_INC/POST_DEC handlers
- Array-to-pointer decay in ADD (checking `is_array` in var table)

Missing one path causes `ptr++` and `ptr+1` to produce different results.

### 2. Variable shadowing in pointer increment
The PRE_INC handler had TWO `ptr_inc_scale` variables — one at outer scope (set to 8) and one inside the `else` block (set based on `hd_type_size`). The inner one shadowed the outer, causing `int *p` to increment by 4 instead of 8. **Always check for variable shadowing when adding scoped variables.**

### 3. String literal storage must match array storage
String literals stored byte-by-byte (offset `i`) but arrays indexed with stride 8 caused `x[1]` to read byte 1 (within cell 0) instead of byte 8 (cell 1). Fix: store string literals at offset `i * 8`.

### 4. Char array init reads beyond string literal
`char s[2] = ""` — string literal has 1 char, array has 2 elements. Copying `arr_size` cells reads beyond the string literal's allocation. Fix: copy `min(string_length, arr_size)` cells, zero the rest.

### 5. Array decay must scale in ADD
`arr + 1` where `arr` is an array variable didn't scale because the ADD handler only checked `HD_TYPE_PTR` and `is_ptr_struct`, not `is_array`. Fix: add `is_array` check in var table lookup.

### 6. 8-byte alignment in wubu_mir_alloc
`wubu_mir_alloc` aligns base to 8 bytes: `if (base & 7) base += 8 - (base & 7)`. Without this, byte-addressed LOAD/STORE misaligns.

### 7. Cell-based model wastes memory but avoids width-aware LOAD/STORE
HolyD's MIR LOAD/STORE always operate on 8 bytes. Packing elements tighter (e.g., 4 bytes for int) causes stores to overlap. The cell-based model (8 bytes per element) is the pragmatic choice until width-aware MIR ops are added.

### 8. Gauntlet multi-target crash propagation
The gauntlet child process runs ALL 14 targets sequentially. If ANY target crashes (SIGSEGV, SIGILL, etc.), the child dies before writing results to the pipe. The parent reads 0 bytes and records ERROR for ALL targets — including x86-64 which may have passed. **A single broken target (8086, 6502, etc.) can mask x86-64 passes as ERROR.** Always verify x86-64 correctness with `gauntlet_runner --dump-asm x86-64` directly, not through `gauntlet_v3`.

### 9. Struct parameter copy used cell offsets
After the byte-addressable rewrite, struct-by-value parameter copy loop used `m` (cell index) instead of `m * 8` (byte offset). This caused `double y` member to be written at byte offset 1 instead of 8, overlapping with `int x`. All copy loops (struct param, struct assignment, struct initializer) must use `byte_off = m * 8`.

## Score Impact

- Baseline (cell-based, int64_t*): 1,188 PASS
- After byte-addressable rewrite: 1,197 PASS (+9)
- writing_c_compiler_full: 425/571 (74.4%) vs baseline 421/571
- Net effect: ahead of baseline, foundation for future struct/char improvements

## Remaining Work for Full Byte-Addressable Semantics

1. **Width-aware LOAD/STORE**: Add MIR ops for 1/2/4-byte access (MIR_LOAD8/16/32, STORE8/16/32)
2. **Packed structs**: Member offsets in bytes with proper alignment/padding
3. **Char arrays**: True byte-packed storage (1 byte per char, not 8)
4. **Struct copy by bytes**: Copy actual byte size, not cell count
5. **sizeof accuracy**: `sizeof(struct { int a; char b; })` = 8, not 16

These require width-aware MIR ops — a significant but well-scoped project.
