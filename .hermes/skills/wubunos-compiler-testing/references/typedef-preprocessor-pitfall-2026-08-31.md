# Typedef via Preprocessor — Pitfall (2026-08-31)

## Summary

Attempted to add `typedef` support by converting it to `#define` in the preprocessor (`wubu_preproc.c`). This caused 9 regressions in the core gauntlet (247→238) and was **reverted**.

## What was tried

1. **Simple typedef**: `typedef int Foo;` → `#define Foo int`
2. **Struct typedef**: `typedef struct { int x; int y; } Point;` → `struct Point { int x; int y; };` + `#define Point struct Point`
3. The typedef detection used `strstr(tl, "typedef ")` to find typedef anywhere in a line (since it can appear inside blocks after `{`)
4. Identifier scanning skipped `{...}` bodies and C keywords (`struct`, `int`, `long`, etc.) to find the alias name
5. Remaining text after the typedef's `;` was output to avoid losing subsequent statements

## Why it failed

1. **Identifier scanning was fragile**: The loop that finds the alias name had to skip C keywords, struct bodies, and handle edge cases like `typedef unsigned long UL;`
2. **Mid-line text loss**: When typedef appeared inside a block (e.g., `{ typedef struct {...} Point; Point p; ... }`), outputting the struct declaration and remaining text caused parsing issues
3. **Interaction with strip_compiler_keywords**: The typedef handling ran BEFORE the strip phase, which strips `signed`, `const`, `volatile`, etc. This changed the line contents unexpectedly
4. **9 core tests regressed**: Tests like `int_assign_chain`, `ctrl_if_nested`, `stress_fib`, `mem_array_assign` started returning 0 instead of expected values

## Root cause

The preprocessor-level approach is fundamentally fragile because:
- The preprocessor processes line-by-line, but typedef can span complex constructs
- Outputting generated code mid-line disrupts the lexer's expectation of well-formed input
- The identifier scanning heuristic (skip keywords, skip `{...}`) is error-prone for edge cases

## Recommended approach

Implement typedef as a **parser-level type alias**:
1. In `holyd_parse.c`, when parsing `typedef`, register the alias in a typedef registry
2. When `parse_type()` encounters an identifier, check the typedef registry first
3. This is how chibicc, lcc, and other small compilers handle it

## Lesson

**Do NOT attempt preprocessor-level typedef substitution again.** It causes regressions in unrelated code paths. The correct approach is parser-level type alias registration.
