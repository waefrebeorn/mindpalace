# Repo-view Devil's Advocate — the sauce

This adversarial pattern caught a whole porting campaign optimizing the wrong
number. It plugs into phases 0–3 of `DEVILS_ADVOCATE.md`; it does not replace them.

## The evidence ladder (highest rung wins)

1. Source text / annotation — a **claim**, never evidence.
2. Compiled object — `nm -g --defined-only <obj>`: zero exported symbols means
   the linker discards it; it cannot affect the product.
3. Wired build graph — `objects.mk` membership without (2) is theater.
4. Running binary — does the artifact exist and execute? Source != binary.
5. Differential oracle against live upstream truth — behavior, not shape.
6. Water-cup / path parity — catches a right answer reached by the wrong route.
7. Negative control — the pre-fix implementation must FAIL the same gate.

A green result at rung 1 or 2 cannot be reported as progress at rung 4+.

## The failure mode (observed, not hypothetical)

Four waves shipped 64 ported functions with 16 green leaf oracles. Every `.o`
exported zero symbols; no caller existed; no binary existed. The scanner's
PORTED count rose while runtime behavior stayed identical. The repo's own DA
worklist had named the real fronts; the work queue came from the wrong instrument.

## Phase 0 — ORIENT with the right instrument

- Start from the body-level reality scoreboard, not a coverage headline.
- Ask: where does the artifact actually run? What calls this function?
- Find the existing owner before writing anything; reuse beats adding.
- Write the claim falsifiably: "reachable and behaves like live reference under X".

## Phase 1 — ATTACK the metric itself

- `nm -g --defined-only` on the object. Zero symbols → dead credit.
- `grep` the tree for callers. No caller → no runtime effect.
- A second live file claiming the same functions → strip the dead one.
- Survey ALL objects with the same shape, not one-off inspection.
- Run the negative control against the OLD implementation.

## Phase 2 — CLOSE with real reachability

- Re-port **in place** in the existing, wired, caller-bearing file. Never add a
  parallel `*_flow*.c` only a harness calls.
- Preserve the C ABI; callers depend on it.
- Pair every positive assertion with a differential assertion.
- If reachability cannot be established, strip the claim; do not relabel it.

## Phase 3 — PRESTIGE with an enforced gate

- Baseline known dead claims so the guard fails only on NEW ones.
- Wire the guard into pre-dispatch / pre-commit, not a doc:
  reality → dead-credit guard → build health → commit.
- Update slate, step log, index; verify no doc path is dead.
- Hand off the next step, then take it. Writing the handoff is not completion.

## Continuous execution

Keep taking concrete bites until the work is done; do not pause at a status
report. Background agents are a batching mechanism, not a stopping point.
Never report a rising/falling claim count as progress; report the gate output
and the running artifact.

**One-line rule:** a port is not done until it is reachable, differential,
gated, and capable of running in the product — and the gate fails on old code.
