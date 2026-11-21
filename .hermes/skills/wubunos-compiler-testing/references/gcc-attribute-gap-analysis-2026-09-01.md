# GCC Attribute Gap Analysis (2026-09-01)

Detailed analysis of gauntlet test failures due to missing GCC `__attribute__` support.

## Failure Summary

Full gauntlet: ~390 failures on x86-64 native target
Root cause breakdown:

| Failure Type | Count | Tests Missing |
|--------------|-------|---------------|
| `__attribute__((noipa))` | ~30 | Prevents inlining optimization hints |
| `__attribute__((alias))` | ~50 | Function/variable aliasing |
| `__attribute__((noalias))` | ~30 | Pointer aliasing semantics |
| `__attribute__((aligned(N)))` | ~20 | Alignment attributes |
| `__builtin_strcmp` | ~5 | String compare builtin |
| `__builtin_strcpy` | ~5 | String copy builtin |
| `__inline__` | ~30 | Inline function semantics |
| Signed overflow UB | 13 | `stress_signed_overflow` expected=1 got=0 |

## Example Failing Tests

### `gcc_torture_000181_pr85156`
```c
__attribute__((noipa)) int foo(int z) {
    if (__builtin_expect(x ? y != 0 : 0, z++)) return 7;
    return z;
}
```
- Uses `__attribute__((noipa))` to prevent IPA (interprocedural analysis)
- Uses `__builtin_expect` for branch prediction hint
- **Status**: Attribute stripped, but behavior differs (inlining not suppressed)

### `gcc_torture_000256_alias_4`
```c
int a = 1;
extern int b __attribute__((alias("a")));
int c = 1;
extern int d __attribute__((alias("c")));
int main(int argc) {
    int *p = argc ? &a : &c;
    int *q = argc ? &b : &d;
    *p = 1;
    *q = 2;
    return (*p == 1) ? 1 : 0;
}
```
- Uses `__attribute__((alias))` for function aliasing
- Tests aliasing semantics: modifying `a` should modify `b` if they're the same symbol
- **Status**: Alias not supported; `b` and `d` are treated as separate variables

### `gcc_torture_000253_921117_1`
```c
__builtin_strcmp(p.text, "0123456789");
__builtin_strcpy(cell.text, "0123456789");
```
- String builtins not implemented
- **Status**: Should strip and replace with external function calls

## Preprocessor Fixes Applied

The preprocessor (`wubu_preproc.c`) now strips:
- `__attribute__((...))` annotations (nested paren handling)
- `__extension__`
- `__inline` / `__forceinline`
- `__declspec`
- `__asm__` / `__asm volatile("...")`
- Join line continuations (backslash-newline)

Added predefined macros:
- `__INT_MAX__` = 2147483647
- `__LONG_MAX__` = 9223372036854775807L
- `__CHAR_BIT__` = 8
- `__SIZEOF_INT__` = 4
- `__GNUC__` = 1
- `__STDC_VERSION__` = 201112L
- `__x86_64__`
- `__SIZE_TYPE__` = size_t

## Required Next Steps

1. **Implement attribute storage**: Track `__attribute__` info in AST rather than just stripping
2. **Alias support**: Implement symbol aliasing in linker/Garbage Collection phase
3. **Builtin expansion**: Replace `__builtin_*` calls with library function calls
4. **Inline semantics**: Implement proper inline function inlining in codegen
5. **Aligned attribute**: Emit proper alignment directives in generated code