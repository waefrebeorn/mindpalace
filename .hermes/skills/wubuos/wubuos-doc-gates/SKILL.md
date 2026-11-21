---
name: wubuos-doc-gates
category: wubuos
version: 1.0.0
author: WaefreBeorn
license: Waefrebeorn Umbrella License v3.0
description: "Making docs honest: audit dead refs; gate the front door."
metadata:
  hermes:
    tags: [wubuos, docs, readmes, gates, audit]
    related_skills: [wubu-module-registry, wubuos-architecture]
---

# Docs that cannot lie

## When to Use

Load this when working on WuBuOS documentation or READMEs: a user asks to make
docs "explanatory and sane", a README reads like schizophrenia, or a doc names
paths that may be dead. Also load it before ANY bulk doc edit -- an unanchored
replace corrupts silently and prose numbers are not gate-defended.

The user's rule: docs must inform on FUNCTION and GOAL, not read like
schizophrenia. Three moves, all proven 2026-11-11 on WuBuOS.

## 1. Audit first, don't guess

Extract every path-like token from the docs and check it exists in the real
tree. The WuBuOS audit found **264 dead refs in 20 docs** -- whole subsystem
maps (docs/MODULES.md) named files that were never written. Walk the tree with
`followlinks=True` (src/compiler is a symlink to the wubunos repo and gets
reported dead otherwise), collapse `src/src/` doubling, and only check tokens
that end in a known extension (`.c .h .md .py .sh .lua .json .conf .mk
.spell`). Skip templated layouts like `<book>/<genre>/<spell>.spell` and bare
binary names -- false positives.

## 2. The front door is a gate

`test_docs` runs a tiny C checker against the FEW docs that describe the system
as a whole (mind palace, saga, module map, ecosystem, README, spell book) and
fails the build when a named path stops existing -- glob-aware via `*`. Decide
deliberately: an auto-generated catalogue is only honest if its generator
ships; whatever is not regenerated is a fossil, so replace it with a short
truthful map rather than keep it for size.

## 3. Structure every doc: purpose first, then contents

- First three lines say what the thing is FOR.
- No orphan claims: if a doc names a file, the file exists.
- No aspiration presented as fact: planned work is marked planned.
- A short accurate doc beats a long flattering one.

The project story (docs/SAGA.md) is mined from `git log`, not memory.
The ecosystem map (docs/ECOSYSTEM.md) is mined from every repo's README via
the GitHub token.

## 4. The gate defends PATHS, not CLAIMS

`test_docs` extracts path tokens and checks they exist. It does NOT check
`make <target>` claims, so the front door can pass while the build command a
README prints is false -- `make wubu_gui_shot` was claimed in the mind palace
and in the architecture skill with no such target. Extend the checker to extract `` `make <target>` ``
tokens and diff them against the target set parsed from `Makefile` + `mk/*.mk`
(`grep -nE '^[a-zA-Z0-9_./-]+:'`); a target token that should resolve and does
not is a failed build, exactly like a dead path. `scripts/doc_claim_check.py`
runs that audit over the guarded docs today.

The same blind spot covers "verified by <script>.sh" claims: a doc can cite a
verification script that no longer exists. Check the file before repeating the
instruction.

## Pitfalls

- **A sed/regex replace that is not anchored is silent corruption.** Updating
  one file count with a broad pattern rewrote EVERY count line in the mind
  palace (firmware 54->58, kernel 911->58). The doc gate checks PATHS, not
  prose numbers, so it passed. Anchor replaces to unique context; after any
  bulk edit, grep before/after to confirm exactly the intended lines changed.
- **A doc that documents a COMMAND must show the command's real output.**
  When a README lists a probe like `find src -name '*.c' | wc -l` with a result
  comment, run that exact command and put its actual answer there — this
  session the doc said 2463 but the command returns 3357 (find does not follow
  the src/compiler symlink to the wubunos repo). A doc telling a reader to run
  a command and get a different number is worse than a stale one: it teaches a
  wrong tool and proves nobody ran it. If a command is so slow it was never
  run, say "run me", do not invent a result.
- **A prose number is a snapshot, not a fact the gate defends.** Counts in docs
  go stale by nature; the gate keeps paths true, only the writer keeps numbers
  true.
- **The gate catches the author too.** It rejected the one dead path I cited in
  my own prose about the missing tool -- which is the point: a doc that names a
  file which should exist and does not is a failed build.
- Never check in a claim about a path in the form `<x>/<y>.spell` -- that is a
  template, not a file.
- **A tree reorganization silently breaks generators that compute their own
  root.** Two failure shapes: the Makefile still calls the old tool path (so
  `make docs` dies immediately), and the tool moved deeper but its
  `dirname(dirname(__file__))` was not deepened (so it scans the wrong tree and
  reports `src/hosted` missing from `tools/`). After ANY directory reorg: run
  every tool/doc target the docs cite, and grep `mk/*.mk` plus scripts for
  paths that no longer resolve. Cheap check, and it is the difference between a
  documented command and a fossil.
- **A target claim outlives its target.** `wubu_gui_shot`, `boot-audit`, and a
  firmware `qemu-boot-verify.sh` were all still cited by docs and skills after
  they stopped existing. Settle a command claim with one call (`make -n
  <target>`, or run it) before repeating it -- "No rule to make target" is the
  cheapest finding there is. (`make hosted` was on this list too until it was
  restored as a real target -- re-run the check before re-adding any name; the
  list moves in both directions.)
