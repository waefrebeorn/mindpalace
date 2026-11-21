# Gauntlet Tooling Pitfalls (2026-09-04 → 2026-09-14)

The gauntlet_runner has several tooling traps that waste time. This file collects them.

## OOM — no fully reliable fix (2026-09-05 update)

Multiple approaches tried to prevent gauntlet OOM on large suites. None fully work.

**Workaround:** Accept partial results up to OOM point (~500 tests for gcc_torture). For complete runs, manually chunk the test array or use smaller suites.

## gauntlet_v3 vs gauntlet_runner — which is canonical (2026-09-20)

**`gauntlet_v3`** is the canonical scoring runner. It runs ALL tests (including ch18 struct tests) and reports the official `valid_pass_rate`. **`gauntlet_runner`** uses a different test list and filters some tests (e.g., extra_credit), so its score differs.

**Always report the `gauntlet_v3` score as the official score.** Use `gauntlet_runner` only for individual test debugging with `--dump-asm`.

**Pitfall**: The two runners can disagree on which tests fail. A test that fails in `gauntlet_v3` might pass in `gauntlet_runner` (or vice versa) due to different test lists and fork isolation. When comparing before/after scores, always use `gauntlet_v3`.

## Stale binary trap (CRITICAL — reinforced 2026-09-14)

**Symptom**: You fix a bug in source code, run the gauntlet, and the bug persists. Hours of debugging reveal the fix was correct — the binary just wasn't rebuilt.

**Root cause**: `make gauntlet_v3` Makefile target runs `rm -f gauntlet_runner` as its FIRST line, then rebuilds only `gauntlet_v3`. After editing source, `make gauntlet_v3` leaves `gauntlet_runner` as the OLD binary. Similarly, `make gauntlet_runner` does not rebuild `gauntlet_v3`.

**CRITICAL RULE**: After ANY source change, rebuild BOTH binaries:
```sh
rm -f gauntlet_runner gauntlet_v3 && make gauntlet_v3 && make gauntlet_runner
```

**Verify**: `stat -c '%Y' gauntlet_runner gauntlet_v3 source_file.c` — both binaries must be NEWER than the source files you changed.

**Real example (2026-09-14)**: Spent hours debugging why a struct copy fix didn't work. Source was correct, `gauntlet_v3` was rebuilt, but `gauntlet_runner` was stale (still had old code). The `--dump-asm` flag uses `gauntlet_runner`, not `gauntlet_v3`. After `rm -f gauntlet_runner && make gauntlet_runner`, the fix worked immediately.

**Real example (2026-09-07)**: Removed `movsxd rax,eax` from NEG instruction. Source was correct, but binary still had the old encoding. After `touch wubu_isa_x86_64.c && make gauntlet_runner`, NEG worked.

**Lesson**: When a fix doesn't change behavior, suspect stale binary FIRST. Always rebuild both binaries.

## --dump-asm uses the JIT

`--dump-asm <target> <src>` runs the JIT (compile + run), NOT the interpreter. To test the interpreter path, use `hd_eval_mir` or the MIR battery.

**IMPORTANT**: `--dump-asm` uses `gauntlet_runner`, NOT `gauntlet_v3`. After editing source, rebuild `gauntlet_runner` specifically.

## Target names use hyphens

`--target x86-64` (NOT `x86_64`). Other targets: `arm64`, `m68k`, `8086`, `6502`, `riscv`, `z80`, `8051`, `avr`, `pic`, `amdgpu`, `ptx`, `wasm`.

## Only x86-64 target works (2026-09-14)

All 13 non-x86-64 targets return wrong results for even `return 42`. The gauntlet score IS the x86-64 score. To increase the score, fix x86-64 failures only.

## MALLOC_MMAP_THRESHOLD_ for OOM prevention

Setting `MALLOC_MMAP_THRESHOLD_=2147483647` (INT_MAX) forces ALL glibc malloc to use `sbrk`, allowing `malloc_trim` to return memory to the OS.

**Pitfall — intermittent SIGFPE:** Rarely causes SIGFPE. Simply retry.

**Pitfall — smaller values crash:** ONLY use INT_MAX or don't set it at all.

## callps pos points to rel32, not call opcode

In the x86-64 JIT fixup loop, `callps[ncallp].pos` points to the rel32 operand of the `call` instruction, NOT the `call` opcode. The `call` opcode is at `pos - 1`.

## External function func_id resolution

Unknown functions (not in prog->n_funcs) were assigned func_id=0 (main) by the MIR builder, causing infinite recursion. Fix: Use func_id=0xFFFF for unknown functions, and patch the JIT fixup to replace the call with `xor eax, eax` + nops.

## Preprocessor string advance must match length exactly

When stripping keywords from source in the preprocessor, the pointer advance must match the string length exactly. Always verify the advance matches the string length.

## Exit code 8-bit truncation (2026-09-07)

**Symptom**: Tests like `return ~12;` (expected 243) fail even though the JIT computes the correct signed result.

**Root cause**: Linux process exit codes are 8-bit (0-255). The gauntlet compares the full 64-bit result to the 8-bit expected value.

**Fix**: Truncate JIT result to 8 bits before comparison: `result & 0xFF`.

## Patch tool duplicate case pitfall (2026-09-07)

**Symptom**: A patch intended for one `case` in a switch statement accidentally modifies a different `case`.

**Root cause**: The `patch` tool matches `old_string` by content, not by position.

**Prevention**:
1. Always include enough surrounding context to make the match unique
2. After patching a switch, verify the expected number of cases: `grep -c 'case HD_TOK' file.c`
3. If the switch has duplicate case names, use line-number-based context

**Recovery**: If a patch creates a duplicate case, `git checkout <file>` to restore, then re-patch with more specific context.

## Var table state leakage between functions (2026-09-20)

**Symptom**: A function works correctly when compiled alone but fails when other functions are present in the same source file.

**Root cause**: The var table (`g->vars[]`) persists across function compilations within a single `hd_build_mir` call. Flags set during one function's compilation leak into subsequent functions.

**Example**: Setting `is_ptr_array=1` for parameter `a` in `nested_array_param` leaks into `array_param` (which also has parameter `a`). The INDEX handler then skips loads for `array_param`'s `a`, producing wrong results.

**Prevention**: When setting a flag for a parameter, first clear it for ALL var table entries with that name:
```c
for (int j = 0; j < g.n_vars; j++) {
    if (strcmp(g.vars[j].name, param_name) == 0) {
        g.vars[j].new_flag = 0;
    }
}
```

**Also**: Initialize the flag to 0 in both `mir_decl_var_unsigned` and `mir_bind_var`.