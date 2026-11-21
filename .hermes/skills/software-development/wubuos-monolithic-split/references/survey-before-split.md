# Survey-Before-Split (monolith-busting triage, 2026-07-15)

The split itself is mechanical (see `split-tooling-pitfalls.md`). The expensive
mistake is *starting the wrong split* — or re-doing one already done.
Two traps burned a full prior session and were corrected this one:

## 1. Stale "frontier" pointers (memory / BATTLESHIP.md)
Memory and `BATTLESHIP.md` / `BATTLESHIP_GAPS.md` lag the tree.
Concrete misses this session:
- Memory claimed `hosted.c ~1220` was the frontier monolith. Reality:
  already **210 lines** (split into `hosted_render/pe/run/wayland_*`).
- `BATTLESHIP_GAPS.md` is **superseded** by `BATTLESHIP.md`.
- `BATTLESHIP.md` Part-1 "open gaps" (`wubu_bottles.c:173 winetricks`,
  `wubu_oci.c`, …) were **already CLOSED** — `wubu_bottles.c` is
  now 17 lines; its logic lives in `wubu_bottle_*.c`.
**Rule:** never trust a named file as "the monolith" from memory/a doc.
Grep the *current* tree first:
```bash
# is it actually big AND still a single unit (no _internal.h sibling)?
for f in $(find src -name '*.c' -size +20k -not -path '*/_legacy_bak/*' \
         -not -name '*_test.c'); do
  base="${f%.c}"; [ -f "${base}_internal.h" ] || echo "$(wc -l <"$f")  $f"
done | sort -rn | head
```
Pick the top hit that has NO `_internal.h` and NO clean sibling split yet.
(`styx.c`, 657 lines, no `_internal.h`, was the real 2026-07-15 target.)

## 2. Sandbox dead-ends (verify the gate, don't chase the loader)
The bare-metal kernel under `qemu -kernel` has a rodata/LMA quirk that
the `wubuos-build-recovery` skill itself flags as **unvalidatable in this
WSL env** (link-success is the bar; runtime boot can't be QEMU-checked).
A prior session spent a whole turn hand-debugging that loader offset — pure
wasted motion. The 9P/Styx namespace (`styx.c`) it was *trying*
to boot is the real, testable asset; split THAT instead.
**Rule:** before any deep debug, run the real gate and read its result:
```bash
make runtime && make hosted && make kernel && make test 2>&1 | tail
# trust: "All tests passed (all tiers)" + MAKE_TEST_EXIT=0
```
If the gate is already green, the "broken code" you were told about is
almost certainly already fixed (stale pointer) — go split a genuine
monolith, don't re-litigate a closed gap.

## 3. The split that actually shipped (this session)
`styx.c` (657) -> `styx_names.c` + `styx_enc.c` + `styx_serve.c`
+ `styx_parse.c` + `styx_internal.h`. All inter-module calls through
`styx.h`; `styx_internal.h` includes ONLY `styx.h`. Gate stayed green
(`test_styx` 29/29). The Makefile rewire is the S5 trap in
`split-tooling-pitfalls.md` (`.o`-as-list vs `.c`-as-source — TWO passes).
