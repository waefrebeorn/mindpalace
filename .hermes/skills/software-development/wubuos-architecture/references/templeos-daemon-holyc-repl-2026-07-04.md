# TempleOS Daemon HolyC REPL Implementation

## Overview
Implementation of persistent HolyC compiler state, REPL mode, and macro expansion for the TempleOS Daemon (wubu_holyd.c).

## Key Components

### 1. Persistent Compiler State (HCCompiler)
Each HolyC session maintains an `HCCompiler` instance that persists across `eval()` calls:
- **Lexer (HCLexer)**: Tokenizes source, maintains position
- **Parser (HCParser)**: Recursive descent, maintains symbol table
- **Code Generator (HCGen)**: Maintains function table, symbols, extern functions

```c
typedef struct {
    HCLexer     lex;
    HCParser    parse;
    HCGen       gen;
    HCASTNode  *ast;
    bool        has_error;
    char        error[256];
} HCCompiler;
```

### 2. Session Integration
`WubuHolySession` stores a `void *compiler` pointer:
```c
typedef struct {
    // ... existing fields ...
    void *compiler;             /* HCCompiler* — actual type from holyc.h */
    bool compiler_initialized;
    // ... other fields ...
} WubuHolySession;
```

### 3. REPL API Functions
- `wubu_holyd_repl_start(d, session)` — Initialize compiler for session
- `wubu_holyd_repl_eval(d, session, code, output, out_size)` — Evaluate with persistent state
- `wubu_holyd_repl_stop(d, session)` — Free compiler state

### 4. Macro Expansion
Simple name→value macro storage per session:
```c
#define MAX_MACROS 64
typedef struct {
    char name[64];
    char value[1024];
} HolyMacro;

static HolyMacro session_macros[WUBU_HOLYD_MAX_SESSIONS][MAX_MACROS];
static int macro_counts[WUBU_HOLYD_MAX_SESSIONS] = {0};

int wubu_holyd_macro_define(WubuHoly *d, const char *session, const char *name, const char *value);
int wubu_holyd_macro_undef(WubuHoly *d, const char *session, const char *name);
```

## HolyC Compiler Modifications

### Exported Functions (holyc.h)
Added to public API:
```c
/* Statement/Expression Generation */
int gen_expr(HCGen *gen, const HCASTNode *node);
int gen_stmt(HCGen *gen, const HCASTNode *node);
void emit_prologue(HCGen *gen);
void emit_epilogue(HCGen *gen);

/* JIT Memory Management */
void *jit_alloc_exec(size_t size);
void jit_free_exec(void *ptr, size_t size);
```

### Implementation Changes (holyc_codegen.c)
Made internal functions non-static:
- `gen_expr` — expression code generation
- `gen_stmt` — statement code generation  
- `emit_prologue` — function prologue (push rbp; mov rbp, rsp)
- `emit_epilogue` — function epilogue (pop rbp; ret)

### Header Dependencies
`holyc.h` now includes `../jit/jit.h` for JIT memory management functions.

## Session Persistence Flow

1. **Session Created** → `wubu_holyd_session_create()` allocates session, `compiler = NULL`
2. **REPL Started** → `wubu_holyd_repl_start()` calls `holyd_get_compiler()` which allocates `HCCompiler` and initializes lexer/parser/generator
3. **REPL Eval** → `wubu_holyd_repl_eval()` uses persistent `HCCompiler`:
   - Re-lexes new code
   - Parses with existing symbol table
   - Generates code using persistent `HCGen` (keeps functions/symbols)
   - JIT compiles and executes
   - Frees executable memory but KEEPS compiler state
4. **REPL Stop** → `wubu_holyd_repl_stop()` frees `HCCompiler`, resets `compiler_initialized = false`
4. **Session Destroy** → Frees any remaining compiler state

## Test Results
All 31 tests passing:
- Config defaults, session create/destroy, window ops, input routing
- Session save/restore with compiler state
- HolyC eval: literals, arithmetic, session-not-found
- HolyC compile: valid code produces binary
- REPL mode evaluation

## Known Limitations
1. Macro expansion is simple string substitution (no token-based preprocessing)
2. No debugger integration yet (breakpoints, step, watch)
3. Macro expansion not yet integrated into lexer pipeline
4. Symbol table persistence works for functions/types but macro expansion not wired into parser

## Future Work
- Integrate macro expansion into lexer (`hc_lex_next`)
- Add `#define`/`#undef` token types to lexer
- Implement debugger commands (breakpoint, step, watch)
- Add symbol table inspection API