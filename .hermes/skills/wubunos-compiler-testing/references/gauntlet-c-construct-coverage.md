# Gauntlet C-Construct Coverage Map (2026-08-31)

This maps the gap between what gcc_torture/external gauntlet tests need and what
the HolyD frontend currently handles. Derived from analyzing the first 30 failing
tests + the error taxonomy (17113 errors = parse fails).

## Failure taxonomy (19,088 tests, x86-64 target)

| Bucket | Count | Root cause |
|--------|-------|------------|
| Parse fail (HolyD can't handle C construct) | ~17113 | Frontend gaps |
| Wrong result (parses but lowers incorrectly) | ~1161 | Lowering + JIT bugs |
| Pass (correct result) | ~814 | Working |

## C constructs needed by failing tests (from research)

### HIGH IMPACT (unblocks hundreds of tests each)

1. **`__attribute__((noinline,noclone,noipa))`** — Strip these. Tests use them heavily.
   Status: ✅ Fixed 2026-08-31 (preprocessor strip_attributes)

2. **`volatile` keyword** — Must parse and either honor or strip. Used in many tests.
   Status: ✅ Parser handles it (stripped as qualifier)

3. **`__asm__("...")` inline assembly** — Must strip. Used in many tests.
   Status: ✅ Fixed 2026-08-31 (strip_inline_asm)

4. **Predefined macros** — `__INT_MAX__`, `__LONG_MAX__`, `__CHAR_BIT__`, etc.
   Status: ✅ Fixed 2026-08-31 (predefined macro table)

5. **Function calls with 7+ args** — MIR_MAX_CALL_ARGS was 8 (dropped args 7+).
   Status: ✅ Fixed 2026-08-31 (changed to 32)

6. **Global variables across function calls** — Must work through LOAD/STORE to mem[].
   Status: ✅ Works (interpreter saves/restores mem on CALL)

### MEDIUM IMPACT (unblocks tens of tests)

7. **Switch statements** — Parsed but codegen may be incomplete.
   Status: Needs verification

8. **Struct initialization** — `struct S v = {'X', 8, 9};`
   Status: Needs implementation

9. **Designated initializers** — `struct S v = {.f1='X', .f2={8,9}};`
   Status: Not yet parsed

10. **Compound literals** — `(struct S){.x=1}` or `(int){5}`
    Status: Not yet parsed

11. **Post-increment in complex expressions** — `foo(n++, m-1)`
    Status: Needs verification

12. **Deep recursion** — 1000-level call chain
    Status: Works (interpreter has call stack)

13. **Void functions** — `void foo() {}`
    Status: ✅ Parsed

14. **Static local variables** — `static int x = 0;`
    Status: ✅ Parsed (static stripped)

15. **External function declarations** — `extern void abort(void);`
    Status: ✅ Parsed

### LOWER IMPACT (unblocks a few tests)

16. **`_Bool` type** — C99 boolean
    Status: ✅ Parsed (Bool keyword)

17. **`_Static_assert`** — Compile-time assertion
    Status: Should be stripped

18. **`_Alignas`/`_Alignof`** — Alignment
    Status: Should be stripped

19. **`_Noreturn`** — Function attribute
    Status: Should be stripped

20. **`_Generic`** — C11 type-generic expressions
    Status: Not parsed

21. **Compound assignment with pointers** — `*p += 1`
    Status: ✅ Works (2026-09-13)

22. **Negative constants** — `-__INT_MAX__ - 1`
    Status: ✅ Works

23. **Cast to unsigned** — `(unsigned char) f`
    Status: ✅ Parsed

24. **Array initialization with designated indices** — `int a[1] = {[0]=1}`
    Status: ✅ Parsed (2026-09-13)

25. **Multi-dimensional arrays** — `int arr[2][2] = {{1,2},{3,4}}`
    Status: ✅ Works (2026-09-13: nested brace-init flattening + depth-aware stride)

26. **Array parameters** — `int f(int a[5])`
    Status: ✅ Works (2026-09-13: adjusted to pointer per C standard)

27. **Null statements** — `;` and `for(;;)`
    Status: ✅ Works (2026-09-13)

28. **Reverse subscript** — `3[arr]`
    Status: Needs verification

29. **Abstract declarators in casts** — `(int (*)) 0`
    Status: ❌ Not parsed

30. **Switch without braces** — `switch(x) case 1: stmt;`
    Status: ❌ Not parsed (parser requires `{` after switch expr)

## SysV x86-64 ABI (for future native calling convention)

Current design: flat mem[] array, args in v1..vN (virtual regs), interpreter saves/restores.
Future optimization: use real registers per SysV ABI:
- Args 1-6: rdi, rsi, rdx, rcx, r8, r9
- Args 7+: pushed on stack in reverse order
- Return: rax
- Caller-saved: rax, rcx, rdx, rsi, rdi, r8-r11
- Callee-saved: rbx, rbp, r12-r15

## Reference: how production compilers handle these

- **chibicc** (rui314): multi-pass, full C11, passes Git/SQLite/libpng tests
- **lcc** (Fraser+Hanson): "A Retargetable C Compiler" book, clean code generation
- **nora sandler** (norasandler.com): step-by-step compiler blog series
- **TCC** (Fabrice Bellard): one-pass, fast, but less optimized
- Key pattern: all use AST → IR → codegen pipeline, all handle structs via
  byte offsets, all use stack frames with proper calling conventions
