# Preprocessor Source Stripping Techniques

The HolyD preprocessor (`wubu_preproc.c`) strips unsupported C constructs before the parser sees them. This is the fastest way to fix gauntlet parse errors — no parser/codegen changes needed.

## Principle

When a construct is used purely for compiler hints (attributes, asm, builtins) or is a superset of what HolyD supports (bit fields, long suffixes), strip it in the preprocessor rather than implementing full semantics. The test compiles and runs; results may differ from GCC for optimization-sensitive tests but correctness tests pass.

## Stripping functions (in `wubu_preproc.c`)

| Function | What it strips | Mechanism |
|----------|---------------|-----------|
| `strip_attributes()` | `__attribute__((...))` | Balanced paren counting |
| `strip_inline_asm()` | `asm`, `__asm`, `__asm__` with optional `volatile`/`inline`/`goto` | Find keyword, skip to `(`, balanced paren removal |
| `strip_bitfields()` | `: <width>` after identifiers | Look for `:` + digit, check preceded by ident |
| `strip_builtin_prefix()` | `__builtin_` prefix + `__complex__`/`__real__`/`__imag__` | `strstr` + `memmove` |
| Integer literal suffixes | `L`, `LL`, `U`, `UL`, `ULL` | Lexer skips trailing `[Lu]+` after digits |
| Builtin defines | `va_list`, `va_start`, `va_arg`, `va_end` | `#define` macros for variadic support |

## Variadic function support (2026-09-05)

Full `...` support requires changes in three files:

**Lexer** (`holyd_lexer.c`): Tokenize `...` as `HD_TOK_ELLIPSIS`. In the `.` case, check if the next two chars are also `.` and advance past all three.

**Parser** (`holyd_parse.c`): Handle `...` in function param lists. Two locations: (1) before the param parsing loop for `void f(...)`, (2) inside the comma loop for `void f(int n, ...)`. **Critical:** Set `fn_params_void_consumed = 1` when consuming `)` in the ellipsis path — the `done_params` label checks this flag to avoid double-consuming `)`.

**Preprocessor** (`wubu_preproc.c`): Define `va_list=void*`, `va_start(ap,last)=""`, `va_arg(ap,type)=*(type*)0`, `va_end(ap)=""`. These make variadic tests compile; `va_arg` returns 0 which is incorrect for real use but prevents crashes.

## Pitfall: strip functions must write back

A strip function that only advances a read pointer WITHOUT writing to the output buffer does nothing. Use the `strip_attributes()` pattern: read from `p`, write to `out`, `*out++ = *p++`, and skip characters by advancing `p` without writing.

## Pitfall: advance must match string length

`strip_inline_asm()` used `p += 2` for `"asm"` (3 chars). The unconsumed `m` caused the function to only work when followed by a recognized keyword. **Always verify `p += strlen(keyword)`.**

## When to strip vs implement

**Strip when:** the construct is a hint (attribute), a no-op (asm with empty template), or a superset (bit fields → regular fields).

**Implement when:** the construct affects correctness (complex numbers, variadic macros, nested functions). Stripping these produces wrong results.

## Adding a new strip function

1. Add the function in `wubu_preproc.c`
2. Call it in `wubu_preprocess()` after `strip_inline_asm()` and before `pp_expand_line()`
3. Test with `./gauntlet_runner --dump-asm x86-64 "<src using construct>"`
4. Verify the full gauntlet suite still passes