# Gauntlet JIT Architecture Gaps and Failure Patterns

This document catalogs the known architectural limitations of the HolyD x86-64 JIT
that prevent gauntlet tests from passing, and the specific failure patterns they produce.

## 1. Flat Memory Model — No Per-Function Isolation

**Architecture**: All functions share a single `prog.mem` buffer. Parameters and
local variables are stored at fixed byte offsets into this buffer. There are no
stack frames — all invocations of a function write to the same memory addresses.

**Failure mode**: When function A calls function B (especially recursively), function
B's parameter stores overwrite function A's parameters in `prog.mem`. After B returns,
A's parameters have the wrong values.

**Symptom**: `double fun(double x) { ... double ret = fun(x+2); return ret+x; }` returns
6 instead of 4 — `x` is 3.0 (from the recursive call) instead of 1.0.

**Tests affected**: `use_arg_after_fun_call` (ch13), any test with recursive functions
where the parameter is used after the recursive call.

**Fix direction**: Implement stack frames. Each function CALL (not function def)
needs its own memory region. Approaches attempted and failed:
- **Per-function static buffer** (one `calloc(256)` per function index): FAILS for
  recursion — all invocations of the same function share the same buffer, so the
  recursive call overwrites the caller's locals. Emitting `push rbx; mov rbx, buf`
  at function entry and `pop rbx` at return is correct for non-recursive calls but
  doesn't help recursion.
- **`rep movsq` save/restore of prog.mem around calls**: FAILS — `rep movsq` uses
  `rcx` as the counter, but `rcx` (reg index 1) is in the allocator pool and may
  hold a live VR. After `rep movsq`, `rcx`=0, corrupting any live value in it.
  Also `rsi`/`rdi` conflict with JIT memory access registers. Stack misalignment
  from mixing `sub rsp` with `push` further corrupts state.
- **Correct approach**: Allocate a NEW buffer per function CALL (not per function
  definition). Use a simple heap allocator (malloc/free) called from JIT code, or
  maintain a frame stack in JIT code. The prologue emits `call malloc`, moves the
  result to `rbx`, and saves the old `rbx` on the C stack. The epilogue restores
  `rbx` and calls `free`. Alternatively, use the hardware stack (`sub rsp, N`)
  for frame storage — but this requires changing LOAD/STORE addressing from
  `[rbx+offset]` to `[rbp-offset]` for locals.

**Key insight**: The MIR generator stores parameters at fixed prog.mem addresses
via `wubu_mir_store(prog, addr, v(pi+1))` at function entry. The callee's store
overwrites the caller's value at the same address. The fix must give each CALL
its own address space, not each function definition.

## 2. 8-Byte Cell Model — No Byte-Addressable Memory

**Architecture**: `prog.mem` is an array of int64_t cells. Each cell is 8 bytes.
LOAD/STORE always operate on 8-byte aligned boundaries. There are no byte loads/stores
(movb, movzbl, etc.).

**Failure mode**: `char` and `unsigned char` operations use 64-bit arithmetic. C requires
8-bit wrapping for char types. `char c = 128;` should give -128 but gives 128.

**Symptom**: All ch16 (char/string) tests fail. `char` pointer access reads 8 bytes
instead of 1. String literals stored as 8-byte cells can't be accessed byte-by-byte.

**Fix direction**: Add byte-addressable memory. Options:
- Change `prog.mem` to uint8_t array with 1/2/4/8 byte load/store variants
- Add a char overlay layer that packs/unpacks bytes within cells
- Add MIR byte-load/store ops (MIR_LOADB, MIR_STOREB) with x86 `movzbl`/`movb`

## 3. dlsym Returns Host Pointers — Incompatible with Offset-Based Memory

**Architecture**: External functions (malloc, calloc, free, etc.) are resolved via
dlsym. These return real host pointers (e.g., 0x7f...). The JIT's memory model uses
byte offsets into `prog.mem`. When `malloc` returns a host pointer, subsequent
LOAD/STORE use `rbx + host_ptr` which accesses invalid memory.

**Failure mode**: `void *p = malloc(32); p[0] = 42;` segfaults or returns wrong value
because `p` is a host pointer, not an offset into `prog.mem`.

**Symptom**: ch17 (void pointer) tests crash or return wrong values. Tests that work
are those where `malloc` returns 0 (NULL) and 0 maps to offset 0 in `prog.mem`.

**Fix direction**: Implement a JIT-internal heap allocator that allocates from
`prog.mem` and returns byte offsets. Intercept malloc/calloc/realloc/free/aligned_alloc
before they reach dlsym.

## 4. Gauntlet State Leakage — Tests Pass Individually but Fail in Gauntlet

**Architecture**: The gauntlet runner forks a grandchild process for each test.
Each grandchild builds MIR and runs it. This should provide full isolation.

**Failure mode**: Some tests pass individually (via `--dump-asm`) but fail in the
gauntlet runner. The cause is NOT fully understood. Two hypotheses:

1. **Genuine flat-memory-model bugs**: The test may pass individually because
   `--dump-asm` runs in a fresh process with clean memory, but the SAME test
   in the gauntlet runner might interact with the flat memory model differently
   (e.g., the test's MIR code leaves prog.mem in a state that affects itself).
   The `--dump-asm` path builds MIR fresh each time; the gauntlet also builds
   fresh per grandchild. So this should be identical.

2. **JIT global state**: The `wubu_jit_mem_ptr` global is set in `x86_run` before
   each JIT execution. If `x86_run` is called multiple times in the same process
   (which it shouldn't be in the grandchild model), the pointer should still be
   valid. The `libm_loaded` static variable in the JIT is a one-time flag and
   shouldn't cause issues.

3. **MIR generator static state**: The `HDMirGen` struct is stack-allocated in
   `hd_build_mir`, so it should be fresh each time. But the parser (`HDParser`)
   may have static state that persists. Check `named_types`, `enum_consts`, and
   any other parser globals.

**Symptom**: ch15 tests (array_as_argument, initialization_automatic,
pointer_arithmetic_pointer_add, subscripting_addition_subscript_equivalence,
subscripting_subscript_pointer) all pass individually but fail in gauntlet.

**Diagnostic approach**:
- Add a debug print in `hd_build_mir` to log the test name and the MIR prog's
  total_mem, n_funcs, n_vars for both individual and gauntlet runs.
- Compare the MIR output (instruction count, VR assignments) between individual
  and gauntlet runs of the same test.
- Check if the gauntlet runner's pipe read is getting corrupted data (wrong
  number of bytes, stale buffer from a previous test).
- Run `gauntlet_v3 --target x86-64` and compare the FAIL list with individual
  `--dump-asm` results for each failing test.

**Fix direction**: Root-cause whether this is genuine MIR/gen bug or infrastructure
issue. If infrastructure, fix the gauntlet runner. If MIR bug, fix the specific
pattern that fails only in gauntlet context.

## 5. DEREF of Array ADD — Sub-array Decay (FIXED 2026-09-19)

**Architecture**: `*(arr + i)` for a multi-dimensional array should return the
sub-array (which decays to a pointer to its first element). The DEREF handler
was loading the first element instead of returning the address.

**Fix applied**:
1. Modified DEREF handler to detect `*(array_var + expr)` pattern: if the
   child is HD_AST_ADD with a direct HD_AST_IDENT base that is an array variable,
   return the address VR without emitting a LOAD.
2. Modified ADD handler to detect DEREF-of-array on the left side: when
   computing `*(arr + i) + j`, apply element-size scaling (8 bytes) rather than
   array-stride scaling (inner_dim * 8). This requires walking the DEREF's child
   ADD to find the root array IDENT and checking `is_array` in the var table.

**Pattern**: For `int x[M][N]`, `*(x + i)` returns `x + i*N*8` (address of row i).
`*(*(x + i) + j)` then accesses `x[i][j]` correctly.

**Key rule**: DEREF of a pointer-to-array is a no-op (returns the address).
DEREF of a pointer-to-scalar loads the value. The distinction is made by
checking if the child expression's root is an array variable.

**Tests fixed**: `addition_subscript_equivalence` (x[i] == *(x+i)),
`subscript_pointer` (ptr[0] on pointer-to-pointer), 2D array access patterns.
Note: These pass individually but may still fail in gauntlet due to state leakage
(see section 4).

## 6. Register Allocator — No Callee-Saved Register Awareness

**Architecture**: The linear scan register allocator assigns 9 integer registers
(r10-r15, r8, r9, rdx) to virtual registers. All 9 are treated equally — there
is no distinction between caller-saved and callee-saved registers.

**Failure mode**: Values live across function calls may be placed in registers
that the callee clobbers. The save/restore around calls preserves all 8 registers
(except r10), but the allocator doesn't prioritize callee-saved registers for
values that are live across calls.

**Symptom**: Complex nested function calls may produce wrong results when values
are implicitly clobbered.

**Fix direction**: Teach the register allocator about callee-saved vs
caller-saved registers. Prioritize callee-saved registers for values live
across calls. Or implement proper spill/reload for call sites.

## Build and Test Commands

```bash
# Build the gauntlet runner (always use rm -f to avoid stale binary)
cd /home/wubu/wubunos && rm -f gauntlet_runner && make gauntlet_runner

# Run full gauntlet (all targets, all tests)
timeout 300 ./gauntlet_v3

# Run single target
timeout 300 ./gauntlet_v3 --target x86-64

# Dump assembly for a test (debug aid)
./gauntlet_runner --dump-asm x86-64 "<source code>"

# Run interpreter for a test
./gauntlet_runner --dump-asm riscv "<source code>"
```

## Score Tracking

As of 2026-09-19: **1,262/2,668 (47.3%)** — x86-64 JIT only. All other 13 targets
return wrong results for `return 42` (they're interpreter-based and not the focus).

The gauntlet counts test-target pairs. 572 tests × 14 targets = 8,008 total pairs,
but only 2,668 are "valid" (the rest are extra-credit or skipped).
