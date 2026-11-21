# wubuos-monolithic-split — references index (partial)

The SKILL.md body is at the 100KB write ceiling, so new pointers can't be
patched into it atomically. This file tracks references added after the
ceiling was hit.

- `references/extraction-split-techniques.md` (added 2026-07-13): the
  `wubu_metal.c` DRM/KMS split learnings — `read_file`+`execute_code`
  extraction near-miss (almost wiped the facade dispatch; rescued by
  `git checkout --`), dead-macro (`WUBU_USE_DRM`) detection, wiring the new
  TU into every Makefile compile site, and test targets broken independent
  of a split. Embed these into the SKILL.md PITFALLS section once the body
  is slimmed below 100KB (e.g. move older verbose references into their own
  files).
- `references/survey-before-split.md` (added 2026-07-15): TRIAGE
  before touching the saw. (1) Stale "frontier" pointers — memory /
  BATTLESHIP.md / BATTLESHIP_GAPS.md lag the tree; `hosted.c` (1200→210)
  and `wubu_bottles.c` (monolith→17) were ALREADY split, so grep the
  *current* tree for a big `.c` with NO `_internal.h` sibling before assuming
  a named file is still the monolith. (2) Sandbox dead-ends — the
  `qemu -kernel` bare-metal rodata/LMA quirk is unvalidatable here
  (per `wubuos-build-recovery`); run `make runtime && make hosted &&
  make kernel && make test` FIRST and trust "All tests passed"; if green,
  the "broken code" is a closed gap — split a real monolith instead of
  re-litigating a loader. (3) The `styx.c`→4-module split that
  shipped (gate stayed green, test_styx 29/29).
