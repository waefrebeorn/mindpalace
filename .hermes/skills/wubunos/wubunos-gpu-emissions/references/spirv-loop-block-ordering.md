# SPIR-V loops: what WORKS, what is impossible, and how not to lose a day

## Verified correct (from the second attempt, before it was reverted)

These five block-ordering fixes are all correct and each was confirmed with
`spirv-val`. Together they got a loop module to VALIDATE and even EXECUTE
(`spirv` returned 0 instead of -1):

1. `lbl_exit` must be the already-assigned `lbl_ssa` of the MIR label that
   FOLLOWS the loop -- NOT a freshly allocated id. Start the forward scan at
   `q+1`, not `q`, or you match the header itself.
2. A jump to a loop header occurring BEFORE that header has been emitted is
   entry flow, not a back-edge. Gate on `hdr_emitted[label]`. Without this the
   continue block opens in the entry function and you get `OpBranch %self`.
3. A MIR label that is the continue target must open the block `OpLoopMerge`
   named -- resolve `lbl_cont` to the nearest preceding MIR label.
4. The header needs a DEDICATE body block: `OpLabel %hdr; OpLoopMerge %m %c
   None; OpBranch %body; OpLabel %body`. Branching to `lbl_ssa[hdr]` makes the
   header branch to itself.
5. Do NOT emit `OpLabel lbl_exit` in the latch. The merge block is the MIR
   label following the loop and is opened by its own MIR_LABEL. Opening it
   twice is exactly "Id N is defined more than once".

## The dominance problem is NOT solvable by hoisting

    ID 'N' defined in block 'A' does not dominate its use in block 'B'

A VR defined in the body and read after it needs an OpPhi. Hoisting an initial
OpCopyObject into the header does NOT help: the body re-assigns the same vr
each iteration and emits a NEW %id inside the loop, so the merge still reads
the body-local id.

## The spill approach (promising, unfinished) and its ordering trap

The right answer is to spill loop-carried VRs to the StorageBuffer the emitter
already has: store at the back-edge, reload in the merge block. A load from
memory depends on nothing defined in the body, so dominance is satisfied. This
is the only route that fits a streaming emitter.

I got it building but not validating. The trap is EMISSION ORDER:

- The emitter streams: `OpFunction` is emitted at ~line 1136, but the
  `lbl_is_loop_header` prepass runs at ~line 1190 -- AFTER it.
- `OpConstant` must be at MODULE scope, so spill index constants cannot be
  created inside the function body.
- Therefore the loop-carried analysis must be MIR-ONLY (no `lbl_*` arrays) and
  run BEFORE the constants, which run before `OpFunction`.

Getting this order wrong gives confusing errors:
  - constants inside the function -> "Invalid instruction word count: 0"
  - `loop_carried` all zero       -> spills never fire, dominance error returns

I then corrupted the file with repeated block-slicing edits (39 compile
errors) and reverted. If you attempt this again, use a SCRIPT FILE and verify
each move compiles, not a chain of inline string replacements.

## Hard-won environment facts

- `execute_code` intermittently raises FileNotFoundError on /home/wubu paths
  even though `ls` shows the file. Retry, or do the edit with a script file
  invoked from `terminal`.
- Verify the emitter's real emission order in the source before moving blocks;
  do not assume prepass-before-function.