# Struct Member Offset Fix (2026-08-31)

## Bug
Struct member offsets were computed in **bytes** by the parser (`t->size += msz` where `msz` is byte size from `hd_type_size`), but the MIR memory model uses **int64 cells** (8 bytes each). This caused member accesses to use wrong offsets:
- `struct Point { int x; int y; }` → `x` at offset 0, `y` at offset 4 (bytes)
- But MIR treats offset as int64 cell index, so `y` was accessed at mem[base + 4] = mem[base + 32 bytes] instead of mem[base + 1] = mem[base + 8 bytes]

## Symptom
Tests with multi-member structs returned wrong values (e.g., `p.x + p.y` returned 0 instead of 7).

## Fix
**File:** `holyd_parse.c` (struct parsing, line ~293)

Changed:
```c
// BEFORE (byte-based):
t->members[t->n_members].offset = t->size;
t->size += msz;  // msz = hd_type_size(member_type) in bytes

// AFTER (cell-based):
t->members[t->n_members].offset = t->size;
t->size += 1;  // each member = 1 int64 cell in MIR memory
t->align = 1;  // all members are 1 cell (8 bytes)
```

Also removed the alignment rounding code (no longer needed since all members are 1 cell).

## Union size
Unions were also affected. Fixed:
```c
// BEFORE:
t->size = max_size;  // in bytes
t->align = max_align;

// AFTER:
t->size = 1;  // union = 1 int64 cell (all members overlap at offset 0)
t->align = 1;
```

## Comma-separated members
Added support for `int x, y;` syntax in struct member declarations:
```c
// AFTER parsing first member, check for commas:
while (match(p, HD_TOK_COMMA)) {
    if (peek(p) != HD_TOK_IDENT) { parse_error(...); break; }
    if (t->n_members < HD_MAX_PARAMS) {
        strncpy(t->members[t->n_members].name, p->lex->tok.text, ...);
        advance(p);
        t->members[t->n_members].offset = t->size;
        t->size += 1;
        t->align = 1;
        t->members[t->n_members].type = member_type;
        t->n_members++;
    }
}
```

## Result
- Core gauntlet: 247/247 preserved ✅
- Full gauntlet: +5 passes / -8 errors
- Tests like `struct Point { int x, y; }; p.x = 3; p.y = 4; return p.x + p.y;` now return 7 ✅

## Lesson
When the MIR memory model uses fixed-size cells (int64), the parser's struct layout must also use cells, not bytes. Mixing byte-based offsets with cell-based addressing causes silent data corruption.

## Byte-Addressable Memory Dead End (2026-09-12)

Attempted to change struct member offsets from cells to bytes to fix C struct padding (e.g., `struct { int a; char b; }` should be 8 bytes with padding, not 16). Parser change made `sizeof` correct (8 bytes) but broke ALL struct member access — the MIR code uses member offsets directly as cell indices, so byte offsets like 4 (for `char b`) would access cell 4 (= 32 bytes into the struct) instead of extracting byte 4 from cell 0.

**Why it's fundamental**: HolyD's memory model is cell-based (8-byte units). LOAD/STORE use `shl rax, 3` to convert address to byte offset. Proper byte-addressable memory requires:
1. Removing `shl rax, 3` from LOAD/STORE in `wubu_isa_x86_64.c` (lines ~1459, 1483)
2. Changing all address computation to use byte offsets directly
3. Handling sub-cell member access with bit masking/shifting OR ensuring all struct members are cell-aligned

**Result**: Reverted after losing 14 tests (1,211→1,097). This is a multi-session architectural effort.

**Pitfall: Parser `t->size` mixes bytes and cells.** The parser computes member offsets in bytes (`t->members[i].offset = t->size`) but increments `t->size` by cells (`t->size += member_cells`). This means member offsets after the first are wrong — they're in cell units, not bytes. The comment says "byte offset" but the value is in cells.
