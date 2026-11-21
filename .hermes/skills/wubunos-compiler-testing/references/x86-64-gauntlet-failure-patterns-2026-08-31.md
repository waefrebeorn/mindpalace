# x86-64 JIT Gauntlet Failure Patterns (2026-08-31)

## Baseline: 961 pass / 1241 fail / 16886 error (full 19,088-test gauntlet)

## x86-64-specific FAILs (30 tests where JIT fails but interpreter passes)

### Pattern 1: `got=1` — branch/return value corruption (25+ tests)
The program returns 1 instead of expected 0. This is the dominant failure mode.

**Root cause (RESOLVED 2026-08-31):** `int foo(void)` was parsed as having 1 parameter of type `void` instead of 0 parameters. This caused a spurious parameter allocation (address VR, memory slot, argument register) that corrupted global variable access across function calls. Fixed by checking for `void)` as empty parameter list in `holyd_parse.c`. This resolved 9 JIT-specific failures.

**Remaining `got=1` failures:** Some tests still show `got=1` after the void fix. These have additional issues beyond the void param bug (e.g., `unsigned int` handling, complex expressions with global variables, struct member access).

**Example tests:**
- `gcc_torture_000089_20001111_1`, `gcc_torture_000122_20021010_2`, `gcc_torture_000172_pr83477`
- `gcc_torture_000179_960302_1` (modulo chain — RDX save/restore in place but still fails)
- `gcc_torture_000242_loop_2c`, `gcc_torture_000316_func_ptr_1`, `gcc_torture_000329_20030105_1`

### Pattern 2: Wrong computation (3 tests)
- `gcc_torture_000007_pr110115`: got=1024 (shift or multiply error)
- `gcc_torture_000360_pr100453`: got=34
- `gcc_torture_000399_pr91137`: got=5

### Pattern 3: Massive garbage (1 test)
- `gcc_torture_000639_pr108064`: got=104959369413264 (uninitialized memory / wrong pointer)

### Pattern 4: Alias tests (expected failures, ~3 tests)
- `gcc_torture_000256_alias_4`, `gcc_torture_000355_alias_3`, `gcc_torture_000676_alias_2`
- These use `__attribute__((alias))` — a linker feature not supported by JIT. Expected.

## ERROR analysis (16,886 total, ~1,671 JIT-specific)

Interpreter errors: ~15,215 (parse/MIR lowering failures shared across all targets)
x86-64 additional errors: ~1,671 (JIT-specific runtime crashes)

**JIT error likely causes:**
- Segfaults from wrong memory access patterns in LOAD/STORE
- Illegal instruction from bad x86-64 encoding
- Stack misalignment (SysV ABI requires 16-byte alignment before CALL)
- Entry trampoline landing on wrong address after function body emission

## Reg Allocator Bug (observed in debug output)

Debug output shows VRs 1, 2, 3 ALL assigned to reg 1 (x86 r11):
```
VR 0 -> spill slot off=5 spill_after=-959418687
VR 1 -> reg 1 (x86 r11) spill_after=0
VR 2 -> reg 1 (x86 r11) spill_after=0  <-- BUG: same register!
VR 3 -> reg 1 (x86 r11) spill_after=0  <-- BUG: same register!
```

The `spill_after=-959418687` (0xC7000001 as unsigned) is garbage — suggests
uninitialized memory or use-after-free. The reg allocator's `assign[]` is freed
at line ~1327 (`wubu_mir_free_alloc`) but debug prints read it at lines ~1374-1378.
This is a debug-only artifact but may indicate a real issue with the allocator.

## RDX Save/Restore (in place but modulo still fails)

The RDX clobber fix (commit `da8bf04`) adds `push rdx` before `cqo`/`idiv` and
`pop rdx` after in `wubu_isa_x86_64.c` lines 716-726. Physical reg index 8 (rdx)
is in the allocator pool. The save/restore protects any live VR assigned to rdx.

BUT: `gcc_torture_000179_960302_1` (modulo chain `a % 2 % 2 % 2...`) STILL fails
with `got=1`. This suggests either:
1. The save/restore isn't working correctly
2. The modulo chain failure is a different bug (comparison/branch inversion)
3. The RDX save/restore only protects physical rdx, but the VR assigned to rdx
   might be spilled/reloaded incorrectly

## Priority Fix Order (updated 2026-08-31)

1. **`got=1` pattern** (25+ tests) — PARTIALLY RESOLVED: `foo(void)` fix resolved 9 tests. Remaining failures have additional causes.
2. **Struct member access** — RESOLVED: member offsets now in cells (not bytes), comma-separated members work.
3. **ERROR crashes** (1,671 JIT-specific) — runtime stability
4. **Modulo chain** — verify RDX save/restore correctness
