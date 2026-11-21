# Opcode coverage per backend, and the "no case = silent wrong answer" family (2026-09-30)

## The recurring bug class

Three separate incidents, one root cause: **an opcode with no `case` in a
backend's switch is not an error — the instruction is silently dropped and
the program computes a plausible wrong answer.**

1. `wubu_mir_interp.c` — positional computed-goto `labels[]` had 100 entries
   for a 104-value enum, omitting `MIR_TO_PTR` and the integer-extend ops.
   `MIR_SEXT32` (47) ran `op_fne`, so `127 + 1` returned 1.
2. `wubu_isa_ptx.c` — no case for `MIR_SEXT32/16/8`, `MIR_ZEXT32`, `MIR_TO_PTR`.
   All 195 ptx failures returned the same constant `0x0100000000000000`,
   which is uninitialized device memory, not a computed value.
3. `wubu_isa_spirv.c` — no case for `MIR_MOV`, the four casts, `MIR_TO_PTR`,
   or `MIR_NEG`. Every Vulkan program returned 0; `-1` returned 0.

## Audit this way

Use the build-time gate rather than an ad-hoc grep:

    python3 scripts/check_opcode_coverage.py                      # report
    python3 scripts/check_opcode_coverage.py --write-baseline \
        scripts/opcode_coverage_baseline.txt                     # after a
                                                                 # deliberate
                                                                 # change

It is wired as a prerequisite of `test_gauntlet`, so a regression fails the
build. Regenerate the baseline **only** when coverage was meant to change.

Note the enum is **104 opcodes**, not 84 -- an earlier hand-rolled regex
missed the f16/bf16 and quantized-int8 group and understated every backend's
gap. Use the script's number.

**A C `sizeof`/`typedef` guard does not work here.** A designated-initializer
table's size comes from its initializer list, so adding an enum member does
not change that size and the check passes silently. Verified by trying it:
inserting a new opcode left the guard green. A missing designated entry is
also legal C -- it just defaults to NULL. This has to be a script.

Measured coverage (104 opcodes), as of 2026-09-30:

    x86_64    94/104   missing 10
    ptx       82/104   missing 22
    spirv     62/104   missing 42
    riscv     40/104   missing 64
    mips      37/104   missing 67
    arm64     28/104   missing 76

The vulkan/spirv row was 41 and is now 62: the f64 core, integer
div/mod/shift/not, unary negate, and the casts were added. Remaining there:
f16/bf16, int8 quantization, control flow (BREAK/CONTINUE/CALL), four tensor
ops, and the i8 GEMM/attention kernels.

**The gauntlet does not catch this.** Every backend except x86-64 and ptx
routes through `wubu_mir_interp`, and `hd_run_prog` silently falls back to
the interpreter when `compile()` fails:

```c
if (driver->compile && driver->compile(...) == 0 && code) { ...run... }
return wubu_mir_interp(prog);   /* silent fallback */
```

`arm64_compile` returns -1 on any non-aarch64 host, so arm64 "passes"
247/247 on x86-64 without executing one ARM64 instruction.

## Rules

- After adding an opcode to `wubu_mir_op_t`, re-run the coverage audit above.
  A new opcode silently miscompiles in every backend that skipped the update.
- Prefer designated initializers (or a compile-time check) over positional
  tables so drift is a build error.
- If a whole suite returns ONE repeated value, suspect an uninitialized
  buffer or a dropped instruction, not 195 independent failures.

## SPIR-V-specific traps

- `OpConstant` must be in the **global constants section**. The `cmts[]`
  table is flushed before the instruction loop, so registering a constant
  during the instruction switch gives it an id but no definition
  (`spirv-val`: "ID N has not been defined"), and emitting it inline gives
  "Constant cannot appear in a function declaration". Both make the driver
  report `VK_ERROR_OUT_OF_HOST_MEMORY` (-13) — a misleading code.
- Validate every generated module with `spirv-val`; it catches what the
  driver reports as generic OOM.
- `(x ^ sign) - sign` is WRONG for sign-extending a value already held in a
  u64: bits 32..63 are zero, so the borrow does not propagate down from bit
  63. Correct: mask, then broadcast the sign bit by multiplying 0/1 by
  `0xFFFFFFFF00000000`, then OR.
- A negative `MIR_CONST` is already stored sign-extended in its 64-bit
  OpConstant field; narrowing it again corrupts the value.
- `dzn` (WSL iGPU) is non-conformant and prints driver chatter to stdout.
  `lavapipe` (`VK_ICD_FILENAMES=/usr/share/vulkan/icd.d/lvp_icd.json`) is the
  conformant CPU fallback for testing.

## C API misuse that type-checks

`vkCreateComputePipelines` was passed the `VkPipelineCache` in the
`pAllocator` slot. Both are pointers, so C accepted it and gcc emitted only
an incompatible-pointer *warning*. At runtime every later argument shifted by
one and the driver called through a garbage `VkPipeline*` — SIGSEGV at
`0x100000010` inside `libvulkan_dzn.so`.

**Read the warning.** A pointer-into-pointer-slot mistake is invisible to the
compiler's type system and shows up only as a wild jump.
