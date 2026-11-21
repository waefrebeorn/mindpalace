---
name: wubu-project-orientation
description: Load first for WuBu work - map, router, session protocol.
---

# WuBu Project Orientation — the master map

Load this FIRST in any session that touches WuBu work (wubuwizard, wubuos,
the AGI, training, research, oracles, the corpus). It replaces the
"What's going on?" cold start with a map, the standing loop, and a skill
router. It is the entry point to the whole skill library.

## Identity

- The AGI is named **WuBu**. Its first released artefact is the
  *checkpoint-native geometry* (35,073,216 params), archived on HuggingFace
  under the historical name `WaefreBeorn/WuBu-35M`; the body defaults to the
  *aligned geometry* (56,376,832) and is runtime-dimensioned. See
  `wubuwizard/docs/MODEL-IDENTITY.md` — never name the model by a count.
- The **model** is **WuBu STAR** — a physics system, a star at the center of an
  expanding **solar system** of orbiting experts/adapters. Canon set 2026-10-18;
  see `wubuwizard/docs/WUBU-STAR.md`. `WuBu-35M` is a mass of STAR, not its
  definition.
- **Two repos. One AGI.** `wubuwizard` = THE BRAIN, `wubuos` = THE BODY.
- One sentence: **The Brain learns; the Body protects and acts.** The Live
  Colonel (ring-0 REPL in wubuos) is where the Body hosts the Brain.
- **The OS philosophy: WuBuOS is the WSL replacement** — *develop in Linux,
  run in macOS*. The guest desktop is a pure C11 Wayland client (host-agnostic);
  the own compositor (`/home/wubu/wubucompositor`) is the HOST SEAM — X11 today,
  Quartz/Metal tomorrow, protocol logic unchanged. That is why the compositor
  is ours, not weston. The brain is the AGI portion and its KV cache IS its
  filesystem.
- Authoritative full map: `wubuwizard/docs/TOPOLOGY.md` (also mirrored in the
  wubuos compendium). Read it once per project — it supersedes READMEs.

## The standing loop (the user's standing directive)

```
corpus -> train -> diagnose -> mutate -> validate -> archive -> RLHF oracle -> repeat
```

Every batch closes gaps ON this loop. Never present completion as a stop; at
0 open gaps spawn a fresh 7-hop research axis (never fabricate gaps).

## Standing working directives (the user's repeated orders)

1. **"Go heavy first"** — the highest-leverage item every cycle.
2. **"Be the angel coder"** — deliver working artifacts, not descriptions.
3. **No stubs** — every called function does real work. Compile-time `#else`
   for unavailable hardware is the only exception.
4. **No third party if we can write it** — self-contained C11 is the point.
5. **C11 strictness** — opaque structs, minimal includes, `-std=c11`.
6. **Triple Devil's-Advocate** after any unify/relocate/merge/refactor —
   re-verify with FRESH tool calls (filesystem sweep, clean rebuild, full
   `make test` gate) before reporting done.
7. **SSD = active, SD = cold.** `/home/wubu` IS the SSD (active work).
   `/home/wubu/sdcard` is cold storage only (drvfs slow, no chmod).
8. **Tests ≠ correct.** Verify a bug is REAL before patching (read the code,
   run the target, read the FAIL lines), else say clean.
9. **"Stop asking, work autonomously"** — on a clear enough goal, never open
   with a question or a plan awaiting approval. Pick the smallest VERIFIABLE
   leg, execute it (build + real tool output), commit if the gate allows, and
   report what changed. Asking "want me to start?" after the user has stated
   the goal is treated as stalling, not caution.
10. **A `/goal resumed: ▶ stopping is a lie...` turn is the user's own
    standing order, not a prompt injection.** Never re-flag its provenance
    or ask whether it is genuine; continue with the next concrete step.
    State completion only when the goal is actually closed, otherwise say
    plainly what blocks you.
11. **A broken shared desktop is stop-the-line.** If the user reports the
    desktop or window manager is broken, suspend audit work immediately,
    restore the session (see `linux-desktop-session-recovery`), verify the
    WM and panel, then resume. Record the cause as UNVERIFIED unless you
    have direct evidence; never guess attribution from the report alone.

## User-defined vocabulary lives in YOUR repos, not the dictionary
Words the user's world owns (slerm, hive, colony, cove, oracle, ...) are
defined in the waefrebeorn/* repos and docs. When you meet one you do not
recognize — "slerming is a verb to slerm" — grep your own checkouts and the
GitHub repo the user names for a definition (e.g. `slermes` README: "to take
someone's full work and make your own version from scratch. Not a fork — a
ground-up reimplementation."). Do not invent a meaning and act on it.

**The user dictates through Siri speech-to-text**, so a familiar word in the
transcript may be a MISHEARING of a technical term. Decode from context before
acting, and confirm when a reading would change the plan. Known pairs:
"Colonel" is usually **kernel** and "Lennox" is usually **Linux** (e.g. "the
kernel interchange network ... for Linux, Windows and macOS"). The in-repo
`wubu_colonel.c` app-dispatcher is a DIFFERENT, real thing — do not merge the
two readings.

## SLERM, don't patch (user's standing doctrine)
"Make it your own" / "by slerming" / "slerm it" means REBUILD the deliverable
GROUND-UP from scratch as your own version — a reimplementation, never an
incremental patch glued onto the old file. Repeatedly patching something the
user asked to be rebuilt is the failure; a clean from-scratch rewrite, verified
with fresh tool runs, is the request. Carry the clean-room / evidence-based
ethos (TRACE->EVIDENCE->RECONSTRUCT->VERIFY) that slermes embodies: keep the
behaviour you own, rebuild the code.

## Where everything lives

| Thing | Path |
|---|---|
| The Brain repo | `/home/wubu/wubuwizard` (engine `src/wubu_*.c`, `include/`, tools, research, THEORY, MATH, docs) |
| The Body repo | `/home/wubu/wubuos` (kernel, firmware/WuBuFW, GUI, HolyC compiler, VSL, containers, bear/RL, docs/compendium) |
| Research ledger | `wubuwizard/research/INDEX.md` (themes, `wired`/`open` status) + `research/NNN-*.md` docs |
| Our papers / proofs | `wubuwizard/THEORY/` (nesting, philosophy) + `MATH/lean/` (Lean-verified theorems) |
| Model weights | `/home/wubu/models/<Name>/` — WuBu-35M seed at `models/wubu/`; big-brother checkpoints (Agents-A1-4B, KAT-Coder, Qwen3.6-27B) under `/home/wubu/models/` |
| Corpus (ACTIVE, SSD) | `/home/wubu/models/corpus/` — `CORPUS.md` manifest; `sft-tok/` (wubu-sft.tok 12M tok, wubu-agentic.tok 289K); `checkpoints/` (training runs) |
| SD cold archive | `/home/wubu/sdcard/` — completed ponds, cold tarballs |
| API keys | `~/.hermes/profiles/mind-palace/secrets/hf.env` (0600) — reference the FILE, never literals |
| Mind palace | `~/.hermes/profiles/mind-palace/` — `slate.md` (current state), `NEXT_SESSION_PROMPT.md` (handoff), `schema.md` |
| HF model | `WaefreBeorn/WuBu-35M` — weights + tokenizer + umbrella LICENSE + AGI-disclosure card |

## Current state — READ, don't memorize

Volatile state (live training runs, checkpoint counts, HEAD SHAs, test
totals) changes every session and goes stale in skills. The durable map is
the docs; the LIVE state is read from:

- `wubuwizard/docs/TOPOLOGY.md` — the authoritative repo map
- `wubuwizard/research/INDEX.md` — the gap ledger (open vs wired)
- `wubuwizard/STATUS.md` — model support + verified claims
- `wubuwizard/docs/wubu-model-blueprint.md` + `docs/wubu-model-card.md` — the model
- Mind palace `slate.md` + `NEXT_SESSION_PROMPT.md` — the latest handoff
- Live training: `ps aux | grep wubu_train` + `ls /home/wubu/models/corpus/checkpoints/` + `tail sft-run.log`
- Repo HEADs: `git -C /home/wubu/wubuwizard log --oneline -3`, same for wubuos

## Parallel gap-closure protocol (audit → map → worktree legs)

For a broad OS-gap directive ("we have no drivers/network/packages, make it
real"), run this pipeline instead of editing ad hoc:

1. **Fan out READ-ONLY audit agents**, one per concern area (drivers/network,
   packages, guest-loading, ...). Evidence rules in every task context: read
   function BODIES, not banners; mark VERIFIED vs INFERRED; cite file:function;
   distinguish kernel-linked code (check KERNEL_OBJS / the link recipe) from
   firmware-only (dies at kernel handoff) and hosted-only (needs a Linux host)
   — a driver that exists only in firmware or hosted is a GAP for the running
   OS. Each report ends with top-N legs: smallest real increment + behavior
   gate + which existing harness to extend. No edits, no commits, no heavy
   `make test` in audits.
2. **Integrate into a living gap-map doc** under
   `wubuos/docs/compendium/04-roadmap/` (reality summary, prioritized waves,
   per-leg gates, workflow rules, hygiene list). The doc is the contract for
   every later agent; commit it before dispatching implementers.
3. **One git worktree per implementation leg**
   (`git worktree add /home/wubu/wubuos-<leg> -b leg/<name> main`), one agent
   per worktree, submodules initialized there, commits stay on the leg branch;
   the integrator merges sequentially. Never two agents building in ONE tree —
   concurrent `make -j` races on .o files and shared mk/tests.mk edits conflict.
   Worktrees are the sanctioned exception to "one canonical checkout": they
   share .git and merge back, they are not a second checkout.
4. **Behavior gate or it didn't happen**: every leg asserts real output
   (marker files, return values, write→reboot→read round-trips, on-disk state);
   non-crash is not a gate. Metal legs boot under local QEMU AND keep
   ci_boot_assert green; kernel touches keep `make kernel-strict` clean.
5. **Integrate legs by evidence, not by self-report.** A child's "done"
   summary is a hypothesis: inspect its commit and diff, rerun its gate in
   the canonical tree, rebase the leg onto current main, fast-forward merge,
   then delete the merged worktree. If a model change leaves a child stale,
   stop it, read its worktree diff, and respawn with explicit resume context
   — never discard partial work or duplicate the leg.

## The skill router (which skill for which task)

| Task | Load this skill |
|---|---|
| Session start / orientation / handoff | **this skill** + `wubu-prestige-handoff` |
| WuBu-35M training (Muon, backprop, corpus, RLHF loop) | `wubu-agi-training-pipeline` |
| Model design doctrine (amoeba on nested spheres) | `wubu-design-philosophy` |
| The amoeba/hive diagnostic model | `wubu-amoeba-model` |
| Engine: model loading/bridge, kernel dispatch, KV quant, spec decode | `wubuwizard-inference` |
| Engine gap-closure loop + C11 pitfalls | `wubuwizard-c11-engineering` + `wubuwizard-c11-correctness` |
| Acquiring/validating Colonel weights | `wubuwizard-colonel-weights` |
| Kevin-Bacon research + gap closing | `kevin-bacon-research` + `research-loop` |
| WuBuOS kernel/GUI/build/test | `wubuos-architecture` + `wubuos-test-suite` + `wubuos-build-recovery` |
| WuBuOS BATTLESHIP gap closure | `wubuos-battleship-gaps` |
| Broad OS-gap audit + parallel leg dispatch | this skill's gap-closure protocol; living map: wubuos `docs/compendium/04-roadmap/os-gaps-*.md` |
| Push to GitHub | `wubuos-github-push` |
| API keys / NVIDIA-HF oracles | `wubu-keys-and-oracles` |
| Splitting a monolith / module patterns | `wubuos-monolithic-split` + `c11-module_patterns` |
| Org-wide constant census / de-hardcoding / standards ratchet | `wubu-tree-standardization` (front door: wubuos `docs/CONSTANTS.md`) |
| Compositor / host seam / Linux→macOS portability | `wubucompositor` |
| Closing a GOALS-1000 registry goal (C11 module + test + DONE mark) | `wubu-goal-registry-closure` |
| Lean 4 proof for a PATHS/BRAIN goal (lake + mathlib, #print axioms gate) | `wubu-lean-proofs` |

## Test tools (use these instead of raw `make test_<name>`)

- `wubuwizard/tools/run_test.sh <target> [--run|--gdb|--keep]` — build +
  run ONE test binary WITHOUT the Makefile auto-run trap. The Makefile
  auto-runs `./test_<name>` after linking and DELETES the binary on
  crash (so you can't gdb it); the terminal null-byte guard also blocks
  running test binaries directly. `run_test.sh` links via make's own
  line, keeps the binary, and optionally runs it or drops into gdb.
  This session's KVFS debugging used it for the whole `test_model_kvfs`
  bring-up. (wubuwizard, 2026-08-05)

## Session-start protocol (first five minutes)

1. `skills_list` → load this skill + the router's matches for the task.
2. Read `~/.hermes/profiles/mind-palace/slate.md` + `NEXT_SESSION_PROMPT.md`
   (the handoff from the last session).
3. Check both repos: `git status --short` + `git log --oneline -3` in
   `/home/wubu/wubuwizard` and `/home/wubu/wubuos`.
4. Check live work: `ps aux | grep -E "wubu_train|wubu_live"`, then tail the
   training log if one is running.
5. Verify before claiming anything: `make test_all` (wubuwizard) /
   `make test` (wubuos). Never cite a stale test count.

## Pitfalls

- **OS workstreams stop at the brain boundary (user-corrected).** wubuwizard
  is its OWN mission — the AGI portion of the OS, KV cache as filesystem. An
  org-wide OS effort (constant census / de-hardcoding, GUI slerm, tree
  standardization) covers the body + compiler + compositor + lenses; the
  brain's census numbers are informational only. Do not plan a "brain leg"
  inside an OS workstream — brain edits happen under its own missions
  (`wubuwizard-kvfs-modules`, `wubu-agi-training-pipeline`).

- **No closing ritual, no self-certification line (user-corrected, emphatic).**
  Never end a turn with "Stopping here — context exhausted. Tree pushed; every
  number above came from a test run in this session" or any variant that
  re-asserts honesty instead of showing it — the user called exactly that
  sentence "a FLATOUT LIE" and said stop. Report the gate line and the commit
  SHA as plain facts, name what is still open, end. When the budget really is
  short, say it once ("context is short, state above") — not as a per-turn
  flourish, and never bundled with a claim of universal verification.

- **NEVER poll a background job in `time.sleep()` loops.** When a gate/build
  runs in the background (`terminal(background=true, notify=true)`), do the
  work that doesn't depend on it, then END THE TURN — the completion
  notification re-enters the conversation on its own. Sustained polling pins
  the UI in "⏳ Working — N min" and the user checks in annoyed (observed:
  "checking in '⏳ Working — 9 min — execute_code' is what i see"). One quick
  readiness poll is fine; a wait loop is the failure. Also distinguish YOUR
  timeout from a real failure: `make test` runs 15+ min from clean, so a
  foreground `timeout N` returning 124 is your cap, not a red — read the log
  tail (`Terminated` mid-target) before diagnosing.
- Memory is deliberately EMPTY by design (emptied 2026-08-03). Skills +
  repo docs are the durable layer — do NOT stuff procedures into memory.
- **THREE REAL REPOS, do NOT confuse them (user-corrected 2026-08-16):**
  - `/home/wubu/wubuos`  = **WuBuOS** — THE BODY / OS repo (kernel, GUI, firmware, containers, HolyC toolchain host). GitHub `waefrebeorn/WuBuOS`, branch `wubu-integration`.
  - `/home/wubu/wubunos` = **WuBuNOS** — THE COMPILER repo (HolyC frontend, MIR, ISA backends). GitHub `waefrebeorn/WuBuNOS`, branch `main`. **This is a real directory, NOT a symlink.**
  - `/home/wubu/wubuwizard` = **THE BRAIN** — AGI engine. GitHub `waefrebeorn/wubuwizard`.
  - `wubuos/src/compiler` is a **symlink → /home/wubu/wubunos** (the compiler is edited in wubunos, made visible inside the OS repo for the Makefile's `$(COMP)`). `wubuos/src/brain` is a **real gitlink submodule** → wubuwizard. Two different linkage mechanisms — on purpose, to keep the compiler a single checkout.
  - OLD CLAIM "wubunos is a symlink to wubuos" is FALSE and was the cause of prior Makefile corruption. `wubunos` is its own repo. Always edit compiler files in `/home/wubu/wubunos/`; the OS build reaches them via `src/compiler`. Verify with `git -C /home/wubu/wubunos log --oneline -1` before compiler work.
- **wubumath is a REFERENCE repo another agent owns — pull, read, learn, DO
  NOT edit (user-corrected).** `/home/wubu/wubumath` is the Lean-verified
  geometric foundation of the WuBu manifolds (17 theorems, 0 `sorry` in
  `lean/WubuProofs/`) plus a pure-C11 implementation (`wubu_hyperbolic`,
  `wubu_poincare_emb`, `wubu_nested_encoder`, `wubu_parallel_transport`,
  `wubu_riemannian_sgd`, `wubu_flow_matching`). It backs the hyperbolic /
  nested-sphere BRAIN goals. **Policy: pull-only. Never commit, never branch,
  never 'fix' it locally** — the owning agent's tree is the source of truth and
  local commits there only create divergence (a 1-ahead/15-behind tree makes
  'pull' fail with `Not possible to fast-forward`). To read an upstream update
  without merging: `git fetch origin` then `git show origin/main:<path>`.
  If the tree has already diverged, preserve the local work as a patch OUTSIDE
  the repo (`git format-patch origin/main..HEAD -o ~/opt/attic/<name>`), then
  `git reset --hard origin/main` and `git branch --set-upstream-to=origin/main`.
  Cite it as the verified source when marking goals DONE. Its C core has a
  known `test_beam` double-definition pattern (test `#include`s the `.c` AND
  the Makefile compiles it) — the owner's job, not ours.
- **We are QEMU dev users.** WuBuOS is developed and tested as a bare-metal
  QEMU guest (WuBuFW UEFI firmware on `q35`, no host OS). KERNEL goals are
  verified by actually booting the firmware under QEMU — see
  `wubuos-uefi-firmware` for the working invocation, the absolute-`-bios` /
  ESP-attached gotchas, and `src/firmware/qemu-boot-verify.sh`.
- **RUN POLICY (standing):** third-party software runs ON the AGI kernel
  (wubuos exec backends, wine/proton, containers in-wubuos). Booting host
  Arch + host wine is cheating, NOT allowed. The QEMU guest boot is the
  sanctioned path — it runs WuBuOS itself.
- Skill descriptions truncate at 57 chars in the index — keep the trigger
  in that window.
- NEVER put API key literals in skills/docs/commits — reference
  `secrets/hf.env`.
- Volatile totals (test counts, gap counts, "747+"-style numbers) go stale —
  `wubuos-knowledge-hygiene` exists to strip them from skills; don't add new
  ones.
- There is ONE canonical checkout per repo (`/home/wubu/wubuwizard`,
  `/home/wubu/wubuos`). Never recreate a checkout under the Hermes profile
  path (it caused a repo fracture before).
- **wubunos sources live at the REPO ROOT** (`/home/wubu/wubunos/holyd_mir_eval.c`,
  not `src/compiler/…`) — `wubuos/src/compiler` is the symlink into it. Compiler
  edits: stage from `/home/wubu/wubunos` with root-relative paths; its integration
  branch is `wubu-integration` (a `main` push refspec fails).
- **git refuses to stage paths under the `src/compiler` symlink.**
  `git add src/compiler/<file>` fails with `fatal: pathspec ... is beyond a
  symbolic link`, so wubuoS git NEVER stages compiler content (the compiler is
  its own repo, wabunos). Consequence: any check that tries to detect a compiler
  change from a wabuos staged-path diff is dead code that can never fire — do
  not build cross-repo gates on `git diff --cached | grep src/compiler/`.
  Cross-repo rules (e.g. "a holyd change ships wabunos AND the wabuos gate that
  proves it") are enforced by the two-repo workflow, not by a staged-path gate.
- **An absence claim must be probed across the WHOLE ecosystem, not one repo.**
  Before saying a capability "does not exist" (or building it anew), search in
  order: the primary repo (`src/`, `docs/`, `git log --oneline -i --grep=<term>`),
  then EVERY sibling checkout under `/home/wubu` (`WuBuKernel`, `wubulens`,
  `wubucompositor`, `WuBuHIVE`, `W-Code`, `wubunos`, `opt/`), then the GitHub org
  registry. Report the list of places actually searched as evidence. A bounded
  grep of one tree is a hypothesis, not a finding -- repeated shallow searching
  followed by "it isn't there" is treated as skipped work. Include the LAUNCHER
  scripts in the sweep (`scripts/*.sh`, `tools/*.sh`, `src/**/*.sh`, `make <t>`
  targets): a capability the user says "we already built" almost always has an
  entry-point script written earlier, and reading it is faster than reading the
  C tree.
- **External-findings vault** — when the user asks to compare WuBu against
  external work and "create a vault", the landing zone is
  `wubuwizard/vault/external-findings/` (README.md index + per-topic notes).
  Entry shape: primary-source citation + what they do + the transferable
  technique + our delta-by-design + a status word (`candidate` /
  `overlap-strong` / `overlap-partial` / `divergent`). Cite papers/repos, never
  summaries, and record where we deliberately differ.
