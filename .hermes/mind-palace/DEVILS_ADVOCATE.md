# Devil's Advocate loop (four phases)

Each of the 1000 review steps runs all four phases. A step that skips a phase
is not a step; it is an opinion.

## Phase 0 -- ORIENT

1. Read the slate and the index. List every path the claim depends on.
2. Verify each state claim against its artifact: `git rev-parse`, gate log,
   file content, running process. A path named in a doc that does not exist
   is a build failure.
2b. Verify reachability in the built product: does the object export symbols
   (`nm -g --defined-only`)? Is there a caller? Does the binary exist and run?
   A source file with a green harness but no caller is a claim, not a port.
3. Research the state of the art on the SAME problem (primary sources only):
   what path did reference systems choose, and what is their smoke standard?
4. Write the claim as a falsifiable sentence.

## Phase 1 -- ATTACK

1. Probe for bug-class siblings: one fix implies the same class lives nearby.
2. Widen gates across ops, widths, flags, direction, ordering and permissions.
3. Run an independent oracle (host tool, native execution, second implementation).
4. Check the security/contract surface: fail-closed tables, pointer
   boundaries, dispatch collisions, shape-vs-value assertions.
4b. Attack the metric: survey ALL objects with the same shape, not just the
   one under review. A detector + tracked baseline catches new dead credit
   that a single inspection misses. Strip redundant claims; keep live owners.
5. **Run the negative control against the PRE-FIX implementation.** A gate
   that passes with and without the fix is not a gate.

## Phase 2 -- CLOSE

1. Implement the smallest real increment. No stubs. No relabeled sensors.
2. Reuse the existing owner; do not duplicate a function that already exists.
3. Pair every positive assertion with a differential or value assertion.
4. Run the narrow gate, then the full gate, then the product gate.
5. Record STATUS: CLOSED (with gate) or IN-FLIGHT (owner + worktree + gate).

## Phase 3 -- PRESTIGE

1. Update `slate.md`, `INDEX.md` and the step log.
2. Write the next phase-plane coordinate: capability radius x review depth.
3. Verify local HEAD equals remote HEAD after every push.
4. Keep working on the next step. Writing the handoff is not completion.

## Finding template

```markdown
### Step NNNN -- <title>
- Claim:
- Evidence (command + real output):
- Negative control (old code / forced failure):
- Smallest real increment:
- Gate run (exact target + result):
- STATUS: CLOSED | IN-FLIGHT(owner, worktree, gate) | VERIFIED_NEGATIVE
- Next phase-plane coordinate:
```
