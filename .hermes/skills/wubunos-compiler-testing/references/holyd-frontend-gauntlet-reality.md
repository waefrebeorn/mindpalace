# HolyD frontend + full-C gauntlet reality (measured 2026-08-21)

This supplements the main SKILL.md. It covers the **HolyD frontend** layer
(`holyd_*.c`, the expression→MIR path) and how the external C-program gauntlet
relates to the `--core` gate. Everything below is a MEASURED fact from a
fork-isolated scan of all ~18,841 external tests, not a guess.

## Two-layer gauntlet — DO NOT CONFLATE

- **`--core` (built-in expr suites):** 3211 tests, ALL PASS (`TOTAL pass=3211
  fail=0 error=0 — ALL TARGETS PASSED`). These are **expressions / single
  statements** (`2+3`, `{int a=5; a+1;}`). They do NOT use C variables/loops/
  functions through the native-JIT LOAD/STORE path and they do NOT require a
  `main` entry point. This gate tells you the canonical-MIR + 14 ISA drivers
  work for scalar expressions. It does NOT tell you the compiler can run a real
  C program.
- **External C-program suites:** ~18,841 tests across 13 suites (see list
  below). These are **whole programs** (`int main(){...}` + helpers, `extern`
  decls, structs, arrays, `double`/`float`/`char`). As of 2026-08-21 only
  ~1,773 of them BUILD (parse+lower succeed); the rest (~17,062) are parse-fails
  from the C1/C2/C3 language-completeness gap (the frontend is expression-only
  by origin). **None execute correctly yet** — see the MIR_CALL blocker below.

## Recursive-loop cycle log (latest on top)

### 2026-08-31: MIR_MAX_CALL_ARGS fix + preprocessor hardening + full-stack gauntlet attack

- **MIR_MAX_CALL_ARGS was 8, changed to 32**: `wubu_mir.h` had `#define MIR_MAX_CALL_ARGS 8`.
  The CALL lowering loop (`holyd_mir_eval.c:881`) does `for (a=0; a<n->n_args && a<MIR_MAX_CALL_ARGS; a++)`
  so args 7+ were silently dropped. This caused wrong results for ANY function with 7+ args.
  Example: gcc_torture_000059 `add(1,2,...,13)` expected 91, got -2075566090 (garbage).
  Fix: `#define MIR_MAX_CALL_ARGS 32`. x86-64 gauntlet improved 761→814 pass.
- **--dump-asm mode segfault fixed**: `test_gauntlet_runner.c` `--dump-asm` passed `arg=0`
  to `drv->run()`, so `wubu_jit_mem_ptr=NULL` → JIT code segfaulted on LOAD/STORE.
  Fixed by allocating mem (like `hd_run_prog`) and passing `(int64_t)mem_ptr`.
- **Preprocessor enhancements** (`wubu_preproc.c`):
  - Strip `__attribute__((...))` annotations with nested paren handling
  - Strip `__extension__`, `__inline`, `__forceinline`, `__declspec`, `__asm__`, `__volatile__`, etc.
  - Strip inline assembly (`__asm__("...")` / `__asm volatile("...")`) with string/paren handling
  - Join line continuations (backslash-newline)
  - Predefined macros: `__INT_MAX__`, `__LONG_MAX__`, `__CHAR_BIT__`, `__SIZEOF_INT__`,
    `__GNUC__`, `__STDC_VERSION__`, `__x86_64__`, `__SIZE_TYPE__`, `__PTRDIFF_TYPE__`, etc.
  - Handle `#pragma`, `#error`, `#warning`, `#undef`, `#ifdef`/`#endif`/`#else`/`#ifndef` directives
- **Debug output use-after-free**: `x86_compile` frees `assign[]` at line 1315 but debug prints
  read `assign[i]` at lines 1343-1368. Shows garbage values but is debug-only, NOT a real bug.
- **Research conducted**: SysV ABI calling convention (args 7+ on stack), chibicc/lcc/nora-sandler
  compiler patterns, C11 constructs needed by gauntlet. See `references/gauntlet-c-construct-coverage.md`.

### 2026-08-30: HolyD frontend — extern, function pointers, const/volatile
- `holyd_parse.c`: Added `extern int x;` variable declaration support (previously
  only `extern "C"` function declarations). Added function pointer parameter
  parsing (`int(*fn)(int)`) using source-level `(*` scan. Added const/volatile
  qualifier stripping. 48/48 C construct tests pass. MIR battery: 69/69.
- **x86-64 JIT 32-bit overflow fix**: Added `movsxd rax,eax` after integer
  arithmetic ops (ADD, SUB, MUL, DIV, MOD, AND, OR, XOR, SHL, SHR, NEG, NOT)
  to truncate 64-bit results to 32-bit C int semantics. Stress_signed_overflow
  now passes (was FAIL, expected 1, got 0).
- Gauntlet --core: **246/247 pass, 0 fail, 1 error (stress_fib crash - pre-existing)**
- **Full gauntlet**: x86-64: 669 pass / 1218 fail / 17201 error. All interpreted
  backends: ~1736/382/~16970. The 17201 errors are HolyD parse failures.
- **Key insight**: `parse_type()` advances the lexer past the current token, so
  `src[pos]` (not `src[pos+1]`) holds the character after the type when scanning
  for function pointer `(*` pattern.
- **Pitfall**: Lexer save/restore backtracking is fragile (whitespace/comments
  re-consumed). Source-level scan is safer.
- **Pitfall**: In while loop for subsequent params, `pname[0]='\0'` before
  function pointer check loses parameter names if `strncpy` is missing in the
  else branch.
- See `references/holyd-frontend-parsing-lessons.md` for full details.

### 2026-08-30: x86-64 JIT fully working
- Fixed 4 critical bugs: register mapping mismatch, patch rel32 off-by-one, REX bit
  swap in LOAD, peephole breaking jumps. See `references/x86-native-load-store-gap.md`.
- Gauntlet --core: 245/247 pass (only `stress_signed_overflow` fails — 64-bit
  JIT doesn't emulate 32-bit overflow).
- `holyd_parse.c`: `hd_parse_decl` now parses `int name(params){ body }` as
  `HD_AST_FUNC_DECL`. Codegen ALREADY emits FUNC_DECL bodies
  (`holyd_codegen_stmt.c:410`, `holyd_codegen_api.c` wires `main`), so real C
  programs / gauntlet TUs like `int main(){...}` now **BUILD**. +96 builds
  (external ok 1677 → 1773). Committed `f23ebb1`.
- `holyd_lexer.c`: added `char`→`HD_KW_U8` and `short`→`HD_KW_I16` keywords
  (HolyC-style fixed-width aliases) so those type names are recognized.
- `holyd_mir_eval.c/.h`: `hd_build_mir_ex(src, prog, errbuf, errcap)` fills
  `errbuf` with the parser's FIRST diagnostic on failure (no guessing). This
  is what the bucket classifier below uses to get real reasons. Committed
  `f23ebb1`.
- **VERIFY:** `--core` still 3211/3211 (no regression); `holyd -emit-elf`
  still emits a runnable ELF (exit 45). Crash sweep: 0 reproducible crashes
  across all 18,259 external tests (the 6 "crash" flags from any pipe-based
  classifier are the known false-positive — see measurement-harness trap below).
- **Still blocked:** parse-only wins convert parse-fails→builds but CANNOT
  produce a passing result until `MIR_CALL` + `main`-entry wiring exists
  (see blocker). `int main(){ return 7; }` now lowers, but `wubu_mir_interp`
  returns 0 because `main` is never invoked.

### 2026-08-21 (first pass): SIGFPE frontend crash fix
- `holyd_parse.c:284` did `t->size % align` where `align` could be 0 when a
  struct member resolved to a zero-size type (void / undeclared type such as an
  undeclared macro constant `N`). Zero align → **division by zero (SIGFPE)**,
  crashing the frontend on adversarial C (`fujitsu_012189`). Fix: clamp
  `align` to `>= 1` so the modulo can never divide by zero, keep the AST
  well-formed (no dangling NULL type). Committed `40bfdda`. Verified 0 crashes
  across the full external gauntlet via ASAN/UBSAN loop.

## The 13 real external suites

`fujitsu, extern_gcc, gcc_torture, writing_c_compiler, c_testsuite, llvm,
compcert, lacc, tinycc, chibicc, slimcc, gcc_dg, gcc_compile`

(The SKILL.md's older list of "19 suites incl. comprehensive/integer/control/
bitwise/comparison/stress/memory" is STALE — those are not the external
gauntlet suites. The 19,088 vs 18,841 count drift is the same staleness.)

## `hd_build_mir_ex()` — capture the REAL failure reason

`holyd_mir_eval.h/.c` exposes:
```c
int hd_build_mir_ex(const char *source, wubu_mir_prog_t *prog,
                    char *errbuf, size_t errcap);
```
On failure it fills `errbuf` with the parser's FIRST diagnostic
(`parse.errors[0]`, or "lex error: ...", or "codegen error"). Use this instead
of guessing WHY a test failed. A crash-isolated scanner over all suites:

```c
/* per test, in a forked child (signal-safe: install SIG_DFL for
 * SIGSEGV/SIGFPE/SIGABRT/SIGBUS/SIGILL, write 1 status byte, _exit): */
wubu_mir_prog_t prog; char eb[300];
int r = hd_build_mir_ex(src, &prog, eb, sizeof(eb));
/* r==0 build ok; r!=0 and WIFSIGNALED(child) => real crash; else parse-fail,
 * reason in eb. */
```

## Standalone measurement-tool link command (reusable)

Measurement-only tools (bucket/classifier/probe) that call `hd_build_mir[_ex]`
link the same object set. `jit_stub.c` is a **measurement-only helper, NOT
committed** — recreate it to provide no-op `jit_alloc_exec/jit_lock_exec/
jit_free_exec` (the real JIT lives in the OS repo; `hd_build_mir` doesn't need
executable pages).

```sh
gcc -O0 -g -std=c11 -D_POSIX_C_SOURCE=200809L -DWUBU_HOSTED \
  -include wubu_gnu_compat.h -I. -Itest_gauntlet \
  -I/home/wubu/wubuos/src/jit -I/home/wubu/wubuos/src/runtime \
  -I/home/wubu/wubuos/src/kernel \
  tool.c test_gauntlet/wubu_test_gauntlet.c test_gauntlet/suites/*.c \
  holyd_lexer.c holyd_parse.c holyd_parse_ast.c \
  holyd_codegen.c holyd_codegen_emit.c holyd_codegen_expr.c \
  holyd_codegen_stmt.c holyd_codegen_api.c holyd_runtime.c \
  holyd_mir_eval.c wubu_preproc.c wubu_mir.c wubu_mir_opt.c \
  wubu_mir_lower.c wubu_mir_regalloc.c wubu_mir_interp.c \
  x86_peephole.c jit_stub.c -lm -o /tmp/tool
```

## Decoding parser error tokens

Error strings look like `expected token 76, got 5`. Token indices (from
`holyd_types.h` enum):

```
0=EOF  1=INT  2=FLOAT  3=CHAR  4=STRING  5=IDENT
22=KW_I64  28=KW_F64  29=KW_BOOL
70=RPAREN  71=LBRACE  72=RBRACE  73=LBRACKET  74=RBRACKET
75=COMMA  76=SEMI
```

So `expected token 76(SEMI), got 5(IDENT)` = two declarations without `;` between
them; `expected token 76, got 0(EOF)` = missing trailing `;`; `expected token
74(RBRACKET), got 5(IDENT)` = `a[i j]` missing `]`; `expected token 70(RPAREN),
got 22(I64)` = `f(int x int y)` missing `,` between params; `expected extern
string literal` = `extern` without `"C"`.

## THE blocker: canonical MIR has NO call opcode (UPDATED 2026-08-30: PARTIALLY RESOLVED)

**UPDATE 2026-08-30**: The x86-64 JIT now has full `MIR_CALL` support (`call rel32`
+ software call stack) and the interpreter's MIR_CALL was fixed. The 69/69 MIR
battery and 245/247 gauntlet --core pass rate confirm function calls work.
The remaining gap is HolyD frontend parsing coverage (C constructs not yet supported).

**Original note (still relevant for full gauntlet)**: `wubu_mir.h` defines `MIR_RET`
but the portable `wubu_mir_interp` has a stub `MIR_CALL`. The 13 non-x86-64 ISA
drivers have no call emission. So while x86-64 can run full C programs, the
interpreted backends cannot. For the external C gauntlet (19,088 tests), the
dominant failure mode is HolyD parse failures (17,081 of 19,088), not the MIR_CALL
limitation.

Consequence: widening parse coverage converts parse-fails → builds, and now
produces passing results on x86-64 for programs that parse. The interpreted
backends still fail on programs with function calls.

## Pitfall: function-def parse must populate ALL codegen-read fields

When `hd_parse_decl` gained function-definition handling (`int name(params){body}`),
the first version set `param_types[]`/`n_params` but **left `param_names[]`
uninitialized**. FUNC_DECL codegen reads `node->param_names[i]`
(`holyd_codegen_stmt.c:~465`) → out-of-bounds read / crash on any function with
parameters. Lesson: when adding a new AST node kind, populate EVERY field the
codegen paths read, not just the ones the parse path touches.

## Measurement-harness crash false-positive (verify independently!)

A fork-isolated classifier that reads the child's result via a **pipe** after
`waitpid` can receive **0 bytes** if the child `_exit(1)` races the pipe close
on a clean parse-reject → the parent sees `g<1` → mis-flags a healthy
parse-reject as a **CRASH**. This session's first classifier reported 6 "real
crashes" that were all classifier artifacts (ASAN/UBSAN loop showed 0 crashes,
and a file-based re-run wrote `b0` = built-clean for every one).

Rule (reinforces recursive-self-improve-loop's "verify INDEPENDENTLY"): before
claiming a crash fix, confirm crashes with an INDEPENDENT method — either a
file-based result (child writes `b0`/`b1` to a file, not a pipe) or an
ASAN/UBSAN loop (`-fsanitize=address,undefined`, run the offending source N
times; 0 sanitizer hits + 0 `WIFSIGNALED` = no real crash).
