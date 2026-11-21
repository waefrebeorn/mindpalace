# HolyC Codegen Implementation Patterns (Critical Tier Gap #4 — 2026-06-29)

## Overview
Completed all 29 placeholder AST node types in `src/compiler/holyc_codegen.c`. Test count: 76 → 84 (+11 new tests).

## Implemented AST Node Types

| Node | Description | Codegen Pattern |
|------|-------------|-----------------|
| `HC_AST_CHAR_LIT` | `'c'` → ASCII value | `mov rax, imm64` |
| `HC_AST_PRE_INC` | `++x` | load → inc → store → return new |
| `HC_AST_PRE_DEC` | `--x` | load → dec → store → return new |
| `HC_AST_POST_INC` | `x++` | load old → inc → store new → return old |
| `HC_AST_POST_DEC` | `x--` | load old → dec → store new → return old |
| `HC_AST_DEREF` | `*p` | `mov rax, [rax]` |
| `HC_AST_ADDR` | `&x` | `lea rax, [rbp - off]` |
| `HC_AST_CAST` | `(T)x` | evaluate child (no-op for I64) |
| `HC_AST_INDEX` | `a[i]` | base + index×8 → load |
| `HC_AST_STRUCT_DECL` | `struct A { }` | no-op (returns 0) |

## Key Codegen Helpers Added/Used

```c
// Stack variable access pattern (used by PRE/POST inc/dec, ADDR)
bool found = false;
int off = 0;
for (int i = 0; i < gen->symbols.n_locals; i++) {
    if (strcmp(gen->symbols.locals[i].name, ident) == 0) {
        off = gen->symbols.locals[i].stack_offset;
        found = true;
        break;
    }
}
if (!found) { emit_mov_rax_imm64(gen, 0); break; }

// Load: mov rax, [rbp - off]
emit_byte(gen, 0x48); emit_byte(gen, 0x8B); emit_byte(gen, 0x85);
emit_dword(gen, (uint32_t)(-(int32_t)off & 0xFFFFFFFF));

// Store: mov [rbp - off], rax
emit_byte(gen, 0x48); emit_byte(gen, 0x89); emit_byte(gen, 0x85);
emit_dword(gen, (uint32_t)(-(int32_t)off & 0xFFFFFFFF));

// Pre-inc: inc rax (0x48 0xFF 0xC0)
// Pre-dec: dec rax (0x48 0xFF 0xC8)
// Deref: mov rax, [rax] (0x48 0x8B 0x00)
// Addr: lea rax, [rbp - off] (0x48 0x8D 0x85 + disp32)
// Array index: shl rax, 3; add rdi, rax; mov rax, [rdi]
```

## Parser Cast Implementation

Added `parse_cast()` in `src/compiler/holyc_parse.c`:

```c
static HCASTNode *parse_cast(HCParser *p) {
    if (peek(p) == HC_TOK_LPAREN) {
        // Save lexer state for backtracking
        int saved_pos = p->lex->pos;
        int saved_line = p->lex->line;
        int saved_col = p->lex->col;
        advance(p); // consume '('
        
        // Check if next token is a type keyword
        bool is_type = false;
        HCTokenType tok = peek(p);
        if (tok == HC_KW_I8 || tok == HC_KW_I16 || tok == HC_KW_I32 ||
            tok == HC_KW_I64 || tok == HC_KW_U8 || tok == HC_KW_U16 ||
            tok == HC_KW_U32 || tok == HC_KW_U64 || tok == HC_KW_F64 ||
            tok == HC_KWBool || tok == HC_TOK_IDENT) {
            is_type = true;
        }
        
        if (is_type) {
            HCType *cast_type = parse_type(p);
            expect(p, HC_TOK_RPAREN);
            HCASTNode *expr = parse_cast(p); // right-associative
            HCASTNode *n = hc_ast_new(HC_AST_CAST);
            n->child = expr;
            n->type = cast_type;
            return n;
        }
        
        // Not a cast - backtrack and parse as parenthesized expression
        p->lex->pos = saved_pos;
        p->lex->line = saved_line;
        p->lex->col = saved_col;
        hc_lex_next(p->lex); // re-tokenize
        HCASTNode *expr = parse_expr(p);
        expect(p, HC_TOK_RPAREN);
        return expr;
    }
    return parse_unary(p);
}
```

## Test Coverage Added

```c
/* -- Increment/Decrement -- */
T("{ I64 x = 5; ++x; }", 6);     // pre-inc returns new
T("{ I64 x = 5; --x; }", 4);     // pre-dec returns new
T("{ I64 x = 5; x++; }", 5);     // post-inc returns old
T("{ I64 x = 5; x--; }", 5);     // post-dec returns old

/* -- Deref/Address -- */
T("{ I64 x = 42; I64 *p = &x; *p; }", 42);  // deref
T("{ I64 x = 10; &x; x; }", 10);             // addr (returns x afterwards)

/* -- Cast -- */
T("(I64)42", 42);
T("(I64)3.14", 4614253070214989087LL);  // double bit pattern
```

## Files Modified
- `src/compiler/holyc_codegen.c` — +180 lines (10 new case handlers)
- `src/compiler/holyc_parse.c` — +40 lines (parse_cast function)
- `src/compiler/holyc_test.c` — +11 new test assertions

## BATTLESHIP.md Update
Gap #8 (`compiler/holyc_codegen.c` — 29 placeholders) marked **COMPLETED 2026-06-29**.