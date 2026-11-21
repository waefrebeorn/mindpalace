# WuBuOS HolyC Compiler Modular Refactor — 2026-07-05

## Session Summary

Split the monolithic `holyc.c` (and related headers) into a clean modular architecture with opaque structs, minimal includes, and C11 compliance. The original `holyc.h` was a 509-line "god header" containing all types, functions, and implementations. The refactor produces:

```
src/compiler/
├── holyc.h          # Facade (includes all below)
├── holyc_types.h    # Core types: token types, AST kinds, structs, enums
├── holyc_lexer.h    # Lexer API
├── holyc_lexer.c    # Lexer implementation
├── holyc_parser.h   # Parser API
├── holyc_parser.c   # Parser implementation
├── holyc_ast.h      # AST node struct + utilities
├── holyc_codegen.h  # Codegen API
├── holyc_codegen.c  # Codegen implementation
└── holyc_ptx.c/h    # PTX codegen (unchanged)
```

## Key Structural Changes

### 1. Type Definitions → `holyc_types.h`
All token types, AST node kinds, struct definitions (HCLexer, HCParser, HCGen, HCCompiler, HCASTNode, HCSymbol, HCSymTab, HCFunction, HCType, HCSymTab, HCFunction), and enums consolidated here. This is the single source of truth for all types.

### 2. Opaque Structs with Full Definitions in Types Header
- Public headers (`holyc_lexer.h`, `holyc_parser.h`, `holyc_codegen.h`, `holyc_ast.h`) forward-declare structs
- Full struct definitions live in `holyc_types.h` (required by implementation files)
- This maintains the opaque pattern while allowing implementation files full access

### 3. API Segregation
Each module has a focused header with only its public API:
- `holyc_lexer.h`: hc_lex_init, hc_lex_next, hc_lex_peek, hc_lex_expect
- `holyc_parser.h`: hc_parse_init, hc_parse_expr, hc_parse_stmt, hc_parse_decl, hc_parse_compilation_unit, hc_parse_block, hc_parse_peek
- `holyc_codegen.h`: hc_gen_init, hc_gen_node, hc_gen_function, gen_expr, gen_stmt, emit_prologue, emit_epilogue, jit_alloc_exec, jit_free_exec, hc_compile, hc_eval
- `holyc_ast.h`: HCASTNode struct + utilities (hc_ast_new, hc_ast_free, etc.)

### 4. Facade Header
`holyc.h` includes all modular headers for backward compatibility.

## Critical Fixes Applied During Refactor

### 1. Parser.c Corruption Recovery
The original `holyc_parse.c` was corrupted during an earlier split attempt (all functions became `parse_block`). Restored by:
- Reverting to clean forward declarations: `static HCASTNode *parse_expr(HCParser *p);` etc.
- Making `parse_block` non-static and declaring in `holyc_parser.h`
- Fixing `HC_KWBool` → `HC_KW_BOOL` mismatch in parse_type
- Fixing token name mismatches: `HC_TOK_PLUS_EQ` → `HC_TOK_PLUS_ASSIGN`

### 2. Codegen.c Fixes
- Added `#include "holyc_parser.h"` for `hc_parse_block` declaration
- Changed `parse_block(&parse)` → `hc_parse_block(&parse)` in `hc_eval` and `hc_compile`
- Fixed `HC_AST_BOOL_LIT` missing from enum (added to HCASTKind)
- Fixed `HC_AST_DEREF`, `HC_AST_ADDR` missing from enum

### 3. Lexer.c Fixes
- Added `#include <stdarg.h>` for `hc_lex_error` variadic
- Fixed token names: `HC_TOK_PLUS_EQ` → `HC_TOK_PLUS_ASSIGN`, etc.
- Fixed `HC_KWBool` → `HC_KW_BOOL` in keyword table
- Added `#include <stdarg.h>` for `va_list`/`va_start`/`va_end`

### 4. Token Type Enum Cleanup
- Added `HC_TOK_SHL`, `HC_TOK_SHR` separate from `HC_TOK_LSHIFT`/`HC_TOK_RSHIFT` (parser uses both)
- Added `HC_TOK_PLUS_PLUS`, `HC_TOK_MINUS_MINUS` for pre/post inc/dec
- Added `HC_TOK_SHL_ASSIGN`, `HC_TOK_SHR_ASSIGN`
- Removed duplicate `HC_AST_POST_INC`/`HC_AST_POST_DEC`/`HC_AST_BITXOR` from HCASTKind

### 5. Type System Fixes
- Added `name` field to `HCType` struct for struct/enum/typedef names
- Added `array_size` to `HCType` for arrays
- Fixed `HC_KWBool` → `HC_KW_BOOL` in keyword enum

### 6. Parser Token Name Consistency
- `HC_TOK_PLUS_EQ` → `HC_TOK_PLUS_ASSIGN` throughout parser.c
- `HC_TOK_MINUS_EQ` → `HC_TOK_MINUS_ASSIGN`
- `HC_TOK_STAR_EQ` → `HC_TOK_STAR_ASSIGN`
- `HC_TOK_SLASH_EQ` → `HC_TOK_SLASH_ASSIGN`
- `HC_KWBool` → `HC_KW_BOOL` in parse_type

### 7. HCASTKind Cleanup
- Removed duplicate `HC_AST_POST_INC`/`HC_AST_POST_DEC`/`HC_AST_BITXOR` (defined in two places)
- Added missing AST kinds: `HC_AST_FUNC_CALL`, `HC_AST_MEMBER`, `HC_AST_DEREF`, `HC_AST_ADDR`, `HC_AST_POST_INC`, `HC_AST_POST_DEC`, `HC_AST_BOOL_LIT`, `HC_AST_XOR`, `HC_AST_BITXOR`, assignment operators

### 8. Parse_block Export
Made `parse_block` non-static and declared in `holyc_parser.h` so it can be called from `holyc_codegen.c` and `wubu_holyd.c`.

## Common Errors and Fixes Reference

| Error | Fix |
|-------|-----|
| `static declaration follows non-static declaration` | Remove `static` from the forward declaration in .c, OR remove the declaration from internal header |
| `undefined reference to 'fn_name'` | Forward declare + remove `static` from function definition |
| `conflicting types for 'fn_name'` | Function signature mismatch between .h declaration and .c definition |
| `redefinition of typedef` | Don't redefine what's already in the included header |
| `redeclaration of enumerator` | Enum values defined twice in the same enum — check for duplicates after merge |
| `implicit declaration of function 'parse_block'` | Function used before declaration — add proper declaration in header, or include parser.h |
| `assignment to 'HCASTNode *' from 'int' makes pointer from integer without a cast` | Implicit int return from undeclared function — declare function in header |

## Pattern: When Modular Refactor Breaks Build

1. **Enum duplication**: After merging split headers, check for duplicate enum values (especially AST kinds, token types)
2. **Function declaration mismatch**: Ensure internal header declares functions as `extern` (not static), .c file definitions match (non-static)
3. **Token name drift**: Parser uses specific names — ensure lexer.h enum and lexer.c both use identical names
4. **Missing includes**: After modular split, each .c must include all needed headers (parser.h for parse_block, etc.)
5. **stdarg.h**: Add to any file using va_list/va_start/va_end
6. **Forward declarations**: Ensure all non-static functions called across modules are declared in a public header

## Makefile Updates

Added `holyc_ast.o` to `COMP_OBJS`:
```makefile
COMP_OBJS = $(COMP)/holyc_lexer.o $(COMP)/holyc_parse.o $(COMP)/holyc_codegen.o $(COMP)/holyc_ptx.o $(COMP)/holyc_ast.o
```

## Test Verification

All tests pass: `make test_holyd` → 32/32 tests passing (31/31 + persistent variable test)