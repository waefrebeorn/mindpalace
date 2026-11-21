# Chronological Bug-Fix Log (moved out of SKILL.md to keep it under size)

A dated log of individual compiler bug fixes. Kept for archaeology; the
generalizable RULES extracted from these live in SKILL.md and in
`references/byte-addressable-memory-and-types.md`. New entries: prefer adding a
RULE to a topical reference over appending a dated incident here.

1. **Assignment dangling if** (2026-09-01): Debug fprintf removal exposed nested `if` bug in `HD_AST_ASSIGN`
2. **Float D->F ops** (2026-09-01): Changed MIR_DADD->MIR_FADD etc. for correct f32 arithmetic
3. **Float literal storage** (2026-09-01): f64 bits -> f32 bits via union pattern
4. **Union support** (2026-08-31): Union types registered, size=1 cell
5. **Typedef struct/union** (2026-08-31): Parser sets type name/ident for typedef'd types
6. **64-bit arithmetic bug** (2026-08-31): JIT truncating to 32-bit (partial fix: SHL/SHR now 64-bit)
7. **Struct member offset fix** (2026-08-31): Parser tracks struct size in cells, not bytes
8. **Save/restore all regs around CALL** (2026-08-30): Fix for global variable corruption
9. **32-bit overflow fix** (2026-08-30): `movsxd rax,eax` after integer ops
10. **void() parameter parsing** (2026-08-31): `foo(void)` now correctly parsed as 0 params
11. **External function crash fix** (2026-09-04): Unknown functions use func_id=0xFFFF, JIT patches to `xor eax, eax`
12. **asm volatile stripping** (2026-09-05): `strip_inline_asm()` now matches plain `asm` (not just `__asm`)
13. **GCC designated initializer `fieldname:`** (2026-09-05): Parser handles `field: val` syntax (GCC extension)
14. **asm stripping off-by-one** (2026-09-05): `p += 2` -> `p += 3` for `"asm"` -- unlocked hundreds of tests
15. **unsigned type combos** (2026-09-05): `parse_type` for `unsigned` now checks for `char`/`short`/`long long`
16. **Casts at unary level** (2026-09-05): `parse_unary` -> `parse_cast` for `(`, void* in cast detection
17. **Bit field stripping** (2026-09-05): `: <width>` removed from struct members
18. **`__builtin_` prefix + `__complex__` stripping** (2026-09-05): `__builtin_memcpy` -> `memcpy`, `__complex__` removed
19. **Long literal suffixes** (2026-09-05): `L`/`LL`/`U`/`UL`/`ULL` skipped after integer literals
20. **Mixed struct declarators** (2026-09-05): Additional-declarators loop handles `*ident` and `ident[N]`
21. **Variadic function parameters** (2026-09-05): Lexer `...` tokenization, parser `...` in param lists
22. **External function name tracking** (2026-09-05): `wubu_mir_call_ext()` + `instr->func_name` for future libc resolution
23. **Gauntlet v2 fork+timeout runner** (2026-09-05): New fork per test with 10s SIGKILL timeout
24. **Compound literal parsing** (2026-09-05 session 6): Parse `(type){initializer}`, allocate memory, store at offsets
25. **strlen compile-time builtin** (2026-09-05 session 6): `strlen("literal")` computed at compile time
26. **Variadic argument copying** (2026-09-05 session 6): Copy v1..v8 to `wubu_va_args[0..7]` at function entry
27. **GCC type macros** (2026-09-05 session 6): Added `__INT8_TYPE__` through `__UINT64_TYPE__`
30. **dlsym-based libc calls** (2026-09-06): x86-64 JIT resolves libc functions via dlsym at compile time, emits real SysV ABI calls. Works for 1-arg integer functions (abs, labs, putchar). 2+ arg functions crash (unresolved).
31. **emit_mov_reg encoding pitfall** (2026-09-06): `emit_mov_reg` uses x86-64 register encodings (0=rax, 7=rdi), NOT MIR allocator encodings (13=rdi). Passing wrong encoding silently emits wrong register moves.
32. **gauntlet_v3 multi-threaded runner** (2026-09-06): pthread-based parallel fork+timeout runner. ~9x speedup. MAX_TESTS=20000.
33. **Repo path correction** (2026-09-06): Compiler repo is `/home/wubu/wubunos/` (NOT `/home/wubu/wubuos/src/compiler/`). Both `wubuos` and `wubunos` exist as separate directories. `cd` to wrong path silently fails but `grep`/`patch` operate on wrong files.
34. **MIR_TO_PTR instruction** (2026-09-06): MIR variables hold cell offsets, not pointers. External libc calls need actual pointers. Added `MIR_TO_PTR`: `dst = rbx + a * 8`. Generated for string literals, array types, pointer types, and `mir_var_is_array()`.
35. **`is_array` detection bug** (2026-09-06): `char src[] = "hello"` not detected as array because `is_array` checked `arr_size > 0` but unspecified-size arrays have `arr_size=0`. Fixed by checking `n->type->kind == HD_TYPE_ARRAY`.
36. **gauntlet_v3 fork-child double-free** (2026-09-06): Forked children calling `wubu_mir_free` corrupts parent heap metadata (COW). Fix: `run_single_test_nofree` skips free in children.
37. **gauntlet_v2 hanging** (2026-09-06): Single-threaded gauntlet_v2 can get stuck on hanging tests. The 10s SIGKILL timeout should kill them, but some tests hang in a way that blocks the parent. Monitor with `ps aux | grep gauntlet` and kill if stuck >3min at same progress.
38. **VLA support** (2026-09-06): Parser handles runtime expressions in array declarators. Codegen allocates fixed 256-cell block per VLA in prog.mem. Verified: `int a[n]`, 2D VLA, VLA with function params all work.
39. **gauntlet_v3 double-free fix** (2026-09-06): Forked children must NOT call `wu_bu_mir_free` -- it corrupts parent heap metadata. Created `run_single_test_nofree` for forked children.
40. **DMake depot system** (2026-09-06): `scripts/dmake.py` manages test acquisition from upstream repos. 758 tests from 5 sources. Never concatenate multi-file tests.
41. **gauntlet_v3 worker 0 fix** (2026-09-06): Main loop must waitpid() BEFORE reading result file. In fork+file IPC, always synchronize before reading shared resources.
42. **Decimal float stripping DELETED** (2026-09-07): Removed decimal-float stripping from preprocessor -- user rejected stripping as cheat. Replaced with legitimate feature implementations (_Decimal32/64/128 -> F64, df/dd/dl suffixes).
48. **64-bit arithmetic -- full cleanup** (2026-09-07): Removed ALL truncation: optimizer WRAP32() from constant folding; JIT `movsxd rax,eax` after every arithmetic op; second-operand register rdi -> rcx; SHL/SHR 64-bit counts (`b & 63`). Added I32/U32 cast (AND with mask). Verified `1000000000000L / 16`, `40l << 40`.
49. **fold_pass vs fold_dce_pass** (2026-09-07): `fold_pass()` is defined but NEVER CALLED. Only `fold_dce_pass()` runs. When debugging constant folding, check `fold_dce_pass()` -- the active one.
50. **gauntlet_runner build stale** (2026-09-07): `make gauntlet_runner` can fail with stale references to deleted suites. Update `test_gauntlet_runner.c` AND `test_gauntlet/wubu_test_gauntlet.h` together. Use `gauntlet_v3` for full runs.
51. **Variable scoping fix** (2026-09-07): `mir_find_var`/`mir_find_var_addr` must search from the END (most recent first) for shadowing. All blocks must push/pop scopes; the old `!g->in_function_body` check prevented inner-block scopes.
52. **Sign extension via SEXT ops** (2026-09-07): `(char)x` etc. use dedicated `MIR_SEXT8/16/32`, NOT `SHL k >> k` (optimizer folds it). Guard SEXT/ZEXT from folding in both fold passes.
53. **JIT second-operand register** (2026-09-07): Binary ops use `rcx` (not `rdi`) to avoid clobbering rax. Encoding: `0xC8` ModRM for `add rax,rcx`.
54. **Exit code truncation** (2026-09-07): Linux exit codes are 8-bit. Truncate JIT result with `& 0xFF` before comparing to expected (all expected values are 0-255).
55. **unsigned long = U64** (2026-09-07): Parser mapped `unsigned long` to U32 -- wrong. `unsigned` + `long` -> HD_TYPE_U64.
56. **Unsigned constant parsing** (2026-09-07): `strtoll` returns INT64_MAX for unsigned constants > INT64_MAX. Scan suffix first, use `strtoull` for U/UL/ULL. (Same root cause as the hex-literal strtoull rule.)
57. **Escape sequences in char constants** (2026-09-07): Added `\a \b \f \v \?` to `hd_scan_string`. Without them `'\a'` parsed as `'a'` (97) instead of BEL(7).
58. **NEG/NOT 32-bit truncation** (2026-09-07): Removed `movsxd rax,eax` after `neg rax`/`not rax` (truncated 64-bit results).
59. **Duplicate HD_TOK_CHAR case** (2026-09-07): `parse_primary` had two `case HD_TOK_CHAR` -- a patch accidentally changed an `HD_TOK_INT` to `HD_TOK_CHAR`, so integer literals parsed as chars. Restored the INT case.
60. **64-bit division -- RESOLVED** (2026-09-07): Was a STALE BINARY (movsxd removed from NEG but not rebuilt). After forced rebuild it worked. The encoding was always correct.
43. **Comment handling fix** (2026-09-07): holyd_lexer.c block-comment skip had impossible `c=='*' && c=='/'`. Replaced with `hd_skip_comment()` state machine.
44. **Float literal exponent support** (2026-09-07): Exponent parsing (`1.0e10`, `2.0E-3`) and float suffixes in the number scanner.
45. **__builtin_ implementations** (2026-09-07): MIR-level prefetch/expect/constant_p/offsetof/ffs/ctz/clz/mul_overflow/add_overflow/fabs/fabsf.
46. **_Complex/__real__/__imag__ support** (2026-09-07): _Complex -> F64, __real__ -> operand, __imag__ -> 0.
47. **Error pattern analysis** (2026-09-07): 1,853 errors mostly from incomplete test extraction, GCC harness macros, _Decimal types, complex vector ops. writing_c_compiler's 413 errors mostly truncated sources.
