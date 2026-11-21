# Repo-view Devil's Advocate — the sauce

This is the adversarial pattern that caught a whole porting campaign optimizing
the wrong number. It plugs into phases 0–3 of `DEVILS_ADVOCATE.md`; it does not
replace them.

## The evidence ladder (highest rung wins)

1. Source text / annotation — a **claim**, never evidence.
2. Compiled object — check `nm -g --defined-only <obj>`: zero exported symbols
   means the linker discards it. It cannot affect the product.
3. Wired build graph — `objects.mk` membership without (2) is theater.
4. Running binary — does the artifact exist and execute? Source ≠ binary.
5. Differential oracle against live upstream truth — behavior, not shape.
6. Water-cup / path parity — catches a right answer reached by the wrong route.
7. Negative control — the pre-fix implementation must FAIL the same gate.

A green result at rung 1 or 2 cannot be reported as progress at rung 4+.

## The failure mode (observed, not hypothetical)

Four waves shipped 64 ported functions with 16 green leaf oracles. Every `.o`
exported zero symbols; no caller existed; no binary existed. The scanner's
PORTED count rose while runtime behavior stayed identical. The repo's own
devil's-advocate worklist had already named the real fronts (stub bodies,
false-green reporting, built-link criterion). The work queue came from the
wrong instrument.

## Phase 0 — ORIENT with the right instrument

- Start from the **body-level reality scoreboard**, not a coverage headline.
- Ask: where does the artifact actually run? What calls this function?
- Find the existing owner before writing anything; reuse beats adding.
- Write the claim falsifiably: "this function is reachable and behaves like
  the live reference under gate X".

## Phase 1 — ATTACK the metric itself

- `nm -g --defined-only` on the object. Zero symbols → dead credit.
- `grep` the tree for callers. No caller → no runtime effect.
- Check whether a second, live file already claims the same functions →
  redundant claim; strip the dead one, keep the live one.
- Widen the attack beyond the change: if one object is dead, survey all
  objects with the same shape (baseline + detector, not one-off inspection).
- Run the negative control against the OLD implementation.

## Phase 2 — CLOSE with real reachability

- Re-port **in place** in the existing, wired, caller-bearing file.
  Do not add a parallel `*_flow*.c` that only a harness calls.
- Preserve the C ABI; callers depend on it.
- Pair each positive assertion with a differential assertion.
- If reachability cannot be established, strip the claim; do not relabel it.

## Phase 3 — PRESTIGE with an enforced gate

- Add a baseline of known dead claims so the guard fails only on NEW ones.
- Wire the guard into the pre-dispatch / pre-commit check, not a doc:
  reality → dead-credit guard → build health → commit.
- Update slate, step log, index; verify no doc path is dead.
- Hand off the next step, then take it. Writing the handoff is not completion.

## Continuous execution

The user's standing order is to keep taking concrete bites until the work is
done, not to pause at a status report. Background agents are a batching
mechanism, not a stopping point: while they run, do independent work from the
same front. Never report a falling/rising claim count as progress; report the
gate output and the running artifact.

## One-line rule

**A port is not done until it is reachable, differential, gated, and capable of
running in the product — and the gate that proves it fails on the old code.**
