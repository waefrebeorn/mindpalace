# Hand-written MIR loop probes: SSA traps that fake backend bugs

## The rule

x86-64, PTX and `wubu_mir_interp` AGREE on every loop construct tested
(plain counted loop, break, continue, nested). If a hand-built loop probe
disagrees across backends, the probe is wrong before you suspect a backend.

MIR is SSA and has no phi opcode. Two consequences trap you:

1. `dst = ...` inside a loop creates a NEW vr each iteration. The loop
   condition keeps reading the pre-loop vr, so the loop never terminates and
   the probe HANGS (exit 124). Loop-carried values must be merged back with
   `wubu_mir_mov_to(&p, orig_vr, new_vr)`.

2. An instruction is EVALUATED where it appears, not conditionally. Writing
   `acc_next = acc + i; if (cond) goto cont;` computes the add on BOTH
   paths -- the branch cannot skip it. To express "add only sometimes" you
   need both values computed and a select/merge, not a branch around the
   computation.

An undefined read (branch to a label where the destination vr was never
assigned on that path) gives a garbage number that LOOKS like a backend bug.
This produced a bogus "x86-64 returns 288 instead of 25" finding that cost
real time; all backends were correct.

## Verification discipline

- Always assert the interpreter and at least two compiled backends agree
  before believing any divergence.
- Check the binary mtime against the source after every rebuild (see
  stale-build-artifacts.md) -- a stale binary makes a fix look ineffective.
- A hang (timeout) means trap 1, not a backend bug.