# New module name collisions (multiple definition, two signatures)

When adding substrate modules during gap-closure sweeps, a new `.c`/`.h` can
silently overwrite an existing module of the same name, or collide with an
identically-named struct/function in a committed module. Both produce
`multiple definition` linker errors, for different reasons.

## Signature A — overwritten module

`write_file("src/wubu_vision.c", ...)` when that file ALREADY EXISTS in HEAD
silently replaces the committed original. Symptoms:

- Link fails with `multiple definition of 'wubu_vision_init' /
  'wubu_vision_encode'` where the SAME symbols appear twice in
  `src/wubu_vision.c` (old) plus whatever still links the old version.
- The original module's public API is gone.

Fix: check existence FIRST, and rename rather than overwrite:

    git show HEAD:src/wubu_<name>.c 2>/dev/null && echo "EXISTS IN HEAD" || echo "NEW"

Then update ALL references: `.c`/`.h` includes, `CORE_OBJ` `.o` entries, test
target prereqs, and any `#define`s renamed with the module.

## Signature B — name collision, no overwrite

You define `wubu_replay_t` in `include/wubu_replay.h`, but
`include/wubu_metagame2.h` (already in `CORE_OBJ`) also defines `wubu_replay_t`
with a DIFFERENT layout, and both define `wubu_replay_add` with different
signatures. Symptoms:

- `multiple definition of 'wubu_replay_add'`, with the two sites reported as
  `src/wubu_replay.c` vs `src/wubu_metagame2.o`.

This is a genuine API collision. Rename your struct and functions, and do NOT
try to reconcile them with `#ifdef` — the existing module owns the name.

## Prevention (run before `write_file`)

    NAME=wubu_<newmod>
    git show HEAD:src/$NAME.c 2>/dev/null && echo "COLLISION-IN-HEAD: rename" || echo OK
    grep -rln "$NAME" src/ include/ tools/ 2>/dev/null \
      | grep -v "src/$NAME\|include/$NAME\|tools/test_<newmod>"

The second grep catches both pre-existing definitions AND stale `.o` rules
left in the Makefile. If anything outside your new files matches, the name is
taken — rename before writing.

Corollary: a link error naming a source you never touched this session is a
collision, not a missing object. Check `git log` for that file before
debugging your own change.