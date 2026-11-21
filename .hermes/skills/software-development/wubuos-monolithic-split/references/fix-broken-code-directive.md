# Fix Broken Code — Standing Order (imprinted from 2026-07-11 session)

This is a USER STANDING ORDER captured verbatim-ish: *"fix the broken code
thats always a good move"* and *"imprint this into your souls."* It governs
every split/fix task in this repo. It could not be added to the (already
100k-char) SKILL.md body, so it lives here — treat it as part of the skill.

## The rule
1. **Fix broken code. Always.** A broken build target, test recipe, or linkage
   is a REAL bug. Do not end the session with a known break, and do not dismiss
   it as "pre-existing / not my regression." Recover it.
2. **Recovery > deletion.** If a Makefile target references a `.c` that was
   deleted by some earlier commit (e.g. a "purge orphan files" commit), the
   fix is almost always to recover the genuine source:
   ```bash
   git show <deleting-commit>^:<path> > <path>
   ```
   Then verify every symbol it calls still exists, build, and RUN a few iters
   to prove it does real work (finite output, accumulating state, exit 0).
3. **Imprint the lesson into the skill, not memory.** After closing a bug or
   discovering a gotcha, patch the relevant SKILL.md or reference file so the
   next session inherits it. The user explicitly redirected away from memory
   for procedural learning: *memory = who/what/state; skills = how-to +
   pitfalls.* (See `use-skills-not-memory` skill for the same directive.)

## Why this is a skill matter, not memory
The user has corrected this repeatedly across sessions: don't re-derive
fragile ad-hoc fixes while a rich skill with the exact gotchas sits unread;
don't store procedures/credentials in memory as a persistence hack. Encode
the how-to so future sessions start already knowing it.

## What this session imprinted (already in split-wip-recovery.md §6/§7)
- §6: broken build targets are real bugs — recover deleted source from git,
  don't skip. (The `bear_train` case: `045ed3a` purged `bear_train.c` but the
  Makefile still referenced `bear_train.o`; recovered 193-line source, it built
  AND ran 3 PPO iters with finite returns.)
- §7: incomplete include in a split module — after any split, add the header
  the new module actually uses (e.g. `bear_cudnn_cublas.c` needed
  `bear_simd.h` for `bear_gemm`). "Minimal includes" = include what you USE.
- A reusable smoke runner ships at `scripts/wubu_split_smoke.sh`.
