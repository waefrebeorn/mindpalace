---
name: wubu-lean-proofs
description: Write, verify Lean 4 proofs in the wubuwizard lake.
category: software-development
---

# Lean 4 proofs (wubuwizard MATH/lean/wubu_proofs)

**Use when** a PATHS/BRAIN goal calls for a formal proof (e.g. "Lean proof:
containment preserves safety"), or when the mathlib lake project at
`MATH/lean/wubu_proofs` needs building/verifying. Do NOT use for the hyperbolic /
nested-sphere BRAIN proofs — those are the other agent's wubumath domain.

Formal proofs for PATHS goals (containment safety, proof-gate soundness) live in
`wubuwizard/MATH/lean/wubu_proofs/` — a lake project with mathlib4 v4.29.1
already fetched. BRAIN hyperbolic/MLA proofs are the OTHER agent's wubumath
domain — do not author those; pull/read/cite them only.

## Toolchain (elan)

- `lean --version` hanging on a download usually means a stale lock file:
  `rm -f ~/.elan/toolchains/*.lock`.
- Use the installed toolchain: `elan override set leanprover/lean4:v4.29.1` from
  inside the project dir (or `elan default leanprover/lean4:v4.29.1` globally).
  `lean --version` and `lake --version` must both answer afterward.
- The mathlib first build is long — run `lake build` as a background job with
  notify, or give a generous timeout. Incremental rebuild after a one-file edit
  is seconds.

## Procedure

1. Write `WubuProofs/<GoalName>.lean` inside `namespace WuBuProofs` (plus a
   nested namespace for the domain type). Keep it self-contained — `omega`,
   `Nat.le_antisymm`, and plain case analysis cover most PATHS-style proofs; no
   Mathlib import needed there.
2. Add the import to `WubuProofs.lean` (the library entry point).
3. `lake build WubuProofs` — target "Build completed successfully".
4. **Verify with `#print axioms`** for every headline theorem via a temporary
   check file run with the built lib on LEAN_PATH, then delete the file (never
   commit it):
   ```
   LEAN_PATH=.lake/build/lib/lean lean check_axioms.lean
   ```
   Acceptable axioms: `propext`, `Quot.sound` (they ride in on `omega`/`simp`).
   `sorryAx` = the proof is a placeholder — not done.
5. Mark the goal DONE per `wubu-goal-registry-closure` (registry commit),
   citing "Lean 4 proof, no sorryAx".

## Lean 4 tactic pitfalls (each one cost a rebuild cycle)

- **Never define a separate `def le` behind an `LE` instance**
  (`instance : LE T where le a b := le a b`). `unfold LE.le` then yields
  `instLE.1 a b`, which no `unfold`/`simp` can reach the inner `le` through, and
  `simp_all [LE.le]` recurses to maxRecDepth. Put the definition INLINE in the
  instance (`le a b := a.toNat ≤ b.toNat`), then rewrite the goal into Nat
  arithmetic with `show a.toNat ≤ b.toNat` (or `have h' : a.toNat ≤ b.toNat := h`)
  and close with `omega`.
- **`decide` only works when the goal is hypothesis-free.** Transitivity and
  antisymmetry need the hypotheses: extract them with `have`, then close with
  `omega` / `Nat.le_antisymm`.
- **`deriving DecidableEq` fails on a structure with `Prop` fields** — use
  `deriving Repr` only; get decidability from `inferInstanceAs` on the field
  props where needed.
- **`Monotone f` as a theorem statement** hits universe-polymorphism friction in
  small settings; state the explicit `∀ a b, a ≤ b → f a ≤ f b` instead.
- **`IO.println "=" * 60` fails** (no HMul instance for IO Unit) in the lake
  executable — use `IO.println (String.mk (List.replicate 60 '='))`.
- When case analysis leaves `a = b` goals, close with `first | rfl | omega`
  after `simp_all [toNat]` — never put `LE.le` in the simp set.
