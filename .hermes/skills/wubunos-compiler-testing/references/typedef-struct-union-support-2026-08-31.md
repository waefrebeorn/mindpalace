# Typedef Struct/Union Support (2026-08-31)

## Problem
`typedef struct { int x; int y; } Point;` failed because:
1. Parser creates struct type with `name=""` (empty tag)
2. Struct is registered in `named_types` with empty name
3. Typedef `Point` → struct type (name="") is registered
4. When `Point p;` is declared, `mir_find_var_struct_name` returns ""
5. `mir_struct_member_offset` looks up "" in structs table → fails (offset=-1)

## Symptom
```c
typedef struct { int x; int y; } Point;
Point p; p.x = 3; p.y = 4;
return p.x + p.y;  // returns 0 instead of 7
```

## Fix (parser-level, NOT preprocessor)

**File:** `holyd_parse.c` (typedef handler, ~line 1061)

After parsing the typedef type and name:
```c
if (base->kind == HD_TYPE_STRUCT || base->kind == HD_TYPE_UNION) {
    if (base->name[0] == '\0') {
        strncpy(base->name, tdname, HD_MAX_IDENT_LEN - 1);
    }
    strncpy(n->ident, base->name, HD_MAX_IDENT_LEN - 1);
}
```

This sets:
- `base->name` = typedef name (so the type is findable by name)
- `n->ident` = typedef name (so the STRUCT_DECL handler registers it)

**File:** `holyd_mir_eval.c` (STRUCT_DECL handler, ~line 333)

Changed to also register union types:
```c
if (n->type && (n->type->kind == HD_TYPE_STRUCT || n->type->kind == HD_TYPE_UNION)) {
```

## Result
- `typedef struct { int x; int y; } Point;` → works ✅
- `typedef union { int x; int y; } U;` → works ✅
- Core gauntlet: 247/247 preserved ✅

## Failed approach: preprocessor macro substitution

An earlier attempt converted `typedef int Foo;` → `#define Foo int` in the preprocessor. This caused 9 regressions in core gauntlet because:
1. The preprocessor processes lines individually; `typedef struct { ... } Point;` on one line inside a block `{ ... }` loses the remaining statements after the typedef's `;`
2. The `strstr(tl, "typedef ")` approach for mid-line typedef required outputting text after `;`, which broke multi-statement lines
3. Debug removal scripts then broke multi-line fprintf statements, causing additional regressions

**Lesson**: Implement typedef in the PARSER (which already has a typedef handler), not the preprocessor. The parser knows the AST structure and can properly set type names and idents.
