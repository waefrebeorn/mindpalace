# SPIR-V instruction-selection traps (2026-09-30)

Found by building the Vulkan leg, not by reading specs. Each cost a
debugging cycle; all are now encoded in `wubu_isa_spirv.c`.

## C's `%` is truncating; SPIR-V's OpSMod is floor-based

Use **OpSRem (138)**, not OpSMod (139):

    -100 % 7  ==  -2   in C   (because -100 / 7 == -14)
    OpSMod(-100, 7) == 5         <- wrong

The asymmetry that makes this easy to get backwards: **OpSDiv (135) IS
truncating and does match C.** Only the modulo differs. I initially
"corrected" 138 to 139 believing SMod was the truncating one, which
introduced the exact bug I was chasing.

**A wrong modulo looks like a lane race and is not.** Chasing
`(-100) % 7 -> 5` led to a bogus "64 lanes all store to cell 0" diagnosis
that survived several rounds. Order of checks that actually resolved it:

1. disassemble the module and evaluate the instruction chain by hand;
2. run the same `.spv` on **lavapipe** and on **dzn** — both returning 5
   proved it was codegen, not the driver;
3. only then consider concurrency.

## Verify opcode numbers, don't recall them

Assemble a reference module and decode the words:

    spirv-as --target-env vulkan1.0 x.spvasm -o x.spv
    # opcode = (word0 & 0xFFFF) at each instruction header

Confirmed this way: 43 OpConstant, 128 OpIAdd, 130 OpISub, 132 OpIMul,
134 OpUDiv, 135 OpSDiv, 137 OpUMod, 138 OpSRem, 139 OpSMod, 170 OpIEqual,
194 OpShiftRightLogical, 195 OpShiftRightArithmetic, 196 OpShiftLeftLogical,
200 OpNot, 224 OpControlBarrier, 246 OpSelectionMerge, 249 OpLabel,
250 OpBranchConditional.

**When the emitter already has the opcode, use ITS name.** The file defines
descriptive macros -- `OPCODE_SHIFT_RIGHT_LOGICAL`, `OPCODE_IADD`,
`OPCODE_ACCESS_CHAIN`, not `OPCODE_SHR`/`OPCODE_ADD`/`OPCODE_ACCESS`. Writing
a plausible short alias (`OPCODE_SHR`) yields an undefined identifier that
looks like a missing feature rather than a typo, and it survives review
because the NUMBER was right:

```sh
grep -nE '#define OPCODE_' src/compiler/wubu_isa_spirv.c
```

Run that BEFORE writing a new instruction, not after the build fails. If the
opcode is genuinely absent, add the macro beside its neighbours.

A new `OpConstant` needs THREE coordinated edits, not one: reserve an id
(`s.c_x = nid(&s)`), declare the field in the `S` struct, and emit the
`OP_CONSTANT` in the global constants section (below). Missing the id
reservation silently reuses another constant's id.

## OpConstant placement

Must be in the **global constants section**. The `cmts[]` table is flushed
before the instruction loop, so registering a constant during the
instruction switch gives it an id but no definition (`spirv-val`: "ID N
has not been defined"); emitting it inline gives "Constant cannot appear
in a function declaration". Both make the driver report
`VK_ERROR_OUT_OF_HOST_MEMORY` (-13) — a misleading code that sends you
hunting for a memory problem you do not have.

**Validate every generated module with `spirv-val`.** It catches what the
driver reports as generic OOM.

## Workgroup width

`LocalSize 64` exists for `MIR_T_GEMM`'s cross-lane reduction. A *scalar*
module run at 64 wide has all 64 invocations store to mem cell 0 — the
result is whichever lane finished last. Emit **LocalSize 1** unless the
program contains a `MIR_T_GEMM`.

An `OpSelectionMerge` lane guard looks like the cleaner fix and is worse:
emitting the merge block after the body orphans the existing `OpLoopMerge`,
`spirv-val` rejects the module, and every program returns -13.

## Drivers on this box

- `dzn` — the WSL iGPU path. **Non-conformant, testing only**; prints
  chatter to stdout. Works, but do not trust it alone.
- `lavapipe` (`lvp`) — Mesa's conformant CPU implementation. Use it as the
  oracle: `VK_ICD_FILENAMES=/usr/share/vulkan/icd.d/lvp_icd.json`.
  Agreement between dzn and lavapipe localises a bug to codegen.
