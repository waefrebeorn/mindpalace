# Union Variable Support in MIR Codegen (2026-08-31)

## Problem
`union U { int x; int y; }; union U u; u.x = 42; return u.x;` returned 0 instead of 42.

Root cause: union types were not registered in the MIR generator's structs table, and union variables were not recognized as struct/union variables.

## Fix (3 changes)

### 1. Register union types during MIR setup
**File:** `holyd_mir_eval.c` (~line 1162)

```c
// BEFORE:
if (t && t->kind == HD_TYPE_STRUCT && t->n_members > 0) {

// AFTER:
if (t && (t->kind == HD_TYPE_STRUCT || t->kind == HD_TYPE_UNION) && t->n_members > 0) {
```

### 2. Recognize union variables in variable declaration
**File:** `holyd_mir_eval.c` (~line 360)

```c
// BEFORE:
if (k == HD_TYPE_STRUCT) {
    is_struct_var = 1;

// AFTER:
if (k == HD_TYPE_STRUCT || k == HD_TYPE_UNION) {
    is_struct_var = 1;
```

### 3. Set union size to 1 cell
**File:** `holyd_parse.c` (~line 324)

```c
// BEFORE:
t->size = max_size;  // in bytes
t->align = max_align;

// AFTER:
t->size = 1;  // union = 1 int64 cell (all members overlap at offset 0)
t->align = 1;
```

## Result
- Union member access works: `u.x = 42; return u.x;` → 42 ✅
- Core gauntlet: 247/247 preserved ✅
