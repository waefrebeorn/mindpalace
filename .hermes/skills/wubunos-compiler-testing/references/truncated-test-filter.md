# Truncated/Invalid Test Filter (2026-09-08)

## Problem

35% of gauntlet tests are invalid extractions — truncated sources, missing code,
GCC test harness dependencies. These tests fail to compile (ERROR) regardless of
compiler quality, inflating the ERROR count and deflating the pass rate.

## Detection Heuristics

A test is likely invalid if its source:
- Starts with `{` (truncated mid-function)
- Has no `main` function (extracted fragment, not complete program)
- Has brace mismatch (`{` count != `}` count)
- Starts with a keyword like `if`, `for`, `while`, `return` (truncated)

## Implementation

Add `is_invalid_test()` to `test_gauntlet_v3.c` before the fork:

```c
static int is_invalid_test(const char *source) {
    if (!source || !source[0]) return 1;
    const char *p = source;
    while (*p == ' ' || *p == '\t' || *p == '\n' || *p == '\r') p++;
    if (*p == '{') return 1;
    if (strncmp(p, "if ", 3) == 0 || strncmp(p, "if(", 3) == 0) return 1;
    if (strncmp(p, "for ", 4) == 0 || strncmp(p, "for(", 4) == 0) return 1;
    if (strncmp(p, "while ", 6) == 0 || strncmp(p, "while(", 6) == 0) return 1;
    if (strncmp(p, "return", 6) == 0) return 1;
    if (strncmp(p, "else", 4) == 0) return 1;
    if (strncmp(p, "do ", 3) == 0 || strncmp(p, "do{", 3) == 0) return 1;
    if (strncmp(p, "switch", 6) == 0) return 1;
    if (strncmp(p, "case ", 5) == 0) return 1;
    if (strncmp(p, "default", 7) == 0) return 1;
    if (strncmp(p, "typedef", 7) == 0) return 1;
    if (!strstr(source, "main")) return 1;
    int depth = 0;
    for (const char *q = source; *q; q++) {
        if (*q == '{') depth++;
        else if (*q == '}') depth--;
    }
    if (depth != 0) return 1;
    return 0;
}
```

In the worker loop, skip invalid tests with code 3:
```c
if (is_invalid_test(all_tests[i].source)) {
    fprintf(f, "3 %s\n", all_tests[i].name);
    fflush(f);
    continue;
}
```

Update result counting to track `worker_skip` and report `valid_total = total - skip`.

## Impact (2026-09-08)

| Metric | Before Filter | After Filter |
|--------|--------------|--------------|
| Total tests | 4,431 | 4,431 |
| Skipped | 0 | 1,763 (40%) |
| Valid tests | 4,431 | 2,668 |
| PASS | 2,500 | 1,163 |
| FAIL | 384 | 328 |
| ERROR | 1,547 | 1,177 |
| Pass rate (all) | 56.5% | 43.6% (valid) |
| writing_c_compiler_full | 383/572 (67%) | 383/571 (67.1%) |

## Suite-Level Breakdown (after filter)

| Suite | Valid | PASS | Pass Rate |
|-------|-------|------|-----------|
| writing_c_compiler_full | 571 | 383 | 67.1% |
| gcc_torture | 726 | 345 | 47.5% |
| extern_gcc | 931 | 250 | 26.9% |

## Interpretation

The filter reveals that `extern_gcc` and `gcc_torture` suites are heavily
contaminated with truncated extractions. The `writing_c_compiler_full` suite
has only 1 invalid test and is the most reliable indicator of compiler quality.

**Pitfall**: Do NOT use the filtered pass rate to claim improvement — the filter
removes noise, not real failures. A real improvement shows as increased PASS
on VALID tests, not just a higher percentage from filtering.

## Root Cause of Truncation

GCC/LLVM/LACC test suites use a custom test harness with macros like
`dg-final`, `bfin`, `FAILURE`, `CONVERT`. The extraction scripts that generate
gauntlet suites don't fully expand these macros, leaving truncated sources.
The `writing_c_compiler_full` suite was extracted with full source files and
has minimal truncation.
