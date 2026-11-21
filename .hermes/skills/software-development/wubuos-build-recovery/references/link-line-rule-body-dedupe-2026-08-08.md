# Adding an object to "every link line that uses X" — rule-body-aware dedupe (2026-08-08)

When a source file gains a new dependency, every test/hosted link line that
compiles the changed file must add the new object. This session added
`wubu_archd_util.c` to every line using `wubu_arch.c`, and
`wubu_archd_svc_super.c` to every line using `wubu_archd_svc.c`/the archd
objects. Two DIFFERENT failure modes bit in sequence:

## Failure mode 1: `undefined reference` (missing object)
`test_proton2` linked `wubu_arch.c` but not `wubu_archd_util.c` — the new
`run_argv`/`run_chroot_argv` symbols had no definition. Symptom:
```
undefined reference to `run_argv'
make: *** [mk/tests.mk:939: test_proton2] Error 1
```

## Failure mode 2: `multiple definition` (object added twice)
The naive fix — grep each physical line for `wubu_archd_util.c`, append
where missing — added the object TWICE to rules whose objects are spread
across CONTINUATION lines. Example: `test_ns_bridge` had
`wubu_archd_util.c` on the `wubu_archd_daemon.c wubu_archd_svc.c` line AND
the fix added it again on the `wubu_arch.c` line. A "whole physical line
already contains it" check misses the case where the file appears on a
DIFFERENT continuation line of the same rule body. Symptom:
```
multiple definition of `run_argv'
make: *** [mk/tests.mk:1037: test_ns_bridge] Error 1
```

## The reliable fix: parse rule BODIES, not physical lines
A rule body = a block from a `\t`-leading prereq line until the first line
that does NOT end with `\` (the final line carries the recipe opener). For
each body: if it references the changed file (e.g. `wubu_arch.c`) AND the
dependency object (`wubu_archd_util.c`) does NOT appear ANYWHERE in the
body, inject it once after the changed file's reference. Python sketch:

```python
lines = content.split('\n')
out = []
i = 0
while i < len(lines):
    out.append(lines[i]); i += 1
    if i < len(lines) and (lines[i].startswith('\t') or lines[i-1].endswith('\\')):
        body_start = i
        j = i
        while j < len(lines) and lines[j].rstrip().endswith('\\'):
            j += 1
        body_end = j                      # inclusive
        body = lines[body_start:body_end+1]
        body_text = '\n'.join(body)
        if 'wubu_arch.c' in body_text and 'wubu_archd_util.c' not in body_text:
            # inject once, after the first wubu_arch.c reference
            ...
        out.extend(body)
        i = body_end + 1
```

Run this ONCE over the file; don't layer sed passes. Note the second
injection pass (archd_daemon.o/loop.o/svc.o consumers needing
svc_super.o) used the same body-aware loop.

## Verification
After any such edit, run the FULL gate (`make test`) and grep the output
for BOTH `undefined reference` AND `multiple definition` — the colorized
tail hides both, and fixing one mode can introduce the other. The
`test_archd_n1`/`test_svc_super` targets themselves also need the util/super
sources on their own link lines.

## Failure mode 3: rewriting the makefile by JOINING continuation lines
A script that reads the file, joins every `\`-continued block into one physical
line and re-emits it destroys the makefile -- recipes lose their structure and
make dies with `missing separator` (observed as a 1375-insertion / 3551-deletion
`git diff --stat` on `mk/tests.mk`). The body-aware injection above edits
tokens in place and preserves the original line structure; do that instead.
If you have already destroyed the file, `git checkout mk/tests.mk` and redo the
edit with the body-aware pass -- never try to repair a joined makefile by hand.
Verify any such edit with `make -n <target>` (parses without running) before
running the gate.

## Failure mode 4: the duplicate is NOT adjacent

A whole-file `str.replace(old, old + " " + new)` over `mk/tests.mk` inserts
the new object after every reference to the changed file -- including lines
that ALREADY carried it. If the token appears twice with ANOTHER token between
them, a consecutive-run dedupe regex (`(tok)(?:\s+\1)+`) finds nothing:

```
$(GUI)/wubu_image_ffmpeg.c $(GUI)/shell/wubu_wallpaper.c $(GUI)/wubu_image_ffmpeg.c
```

Rule: after any bulk object edit, check `line.count(token) > 1` PER PHYSICAL
LINE and keep only the first occurrence. Never trust a "runs of the same
token" regex for this -- the duplicate can straddle an unrelated token.

## Failure mode 5: an app-registry launcher that drags in the WM

`apps.c` references one launcher per desktop icon. When a new launcher pulls
in the window manager (`wubu_petdex_open` -> `wm_destroy`,
`chrome_draw_window`, `vbe_rect_rounded`), EVERY target that links `apps.c`
breaks -- including the lean ones that deliberately carry no WM.

Declare the launcher `__attribute__((weak))` at its use site in `apps.c`
and null-check it in the wrapper:

```c
__attribute__((weak)) DosGuiWindow* wubu_petdex_open(void);

DosGuiWindow* launch_petdex(void) {
    if (!wubu_petdex_open) return NULL;
    return wubu_petdex_open();
}
```

A weak declaration resolves to NULL when the object is absent, so the lean
targets link. `test_apps_weak` exists precisely to prove this: it links
`apps.c` WITHOUT the real module, so it is the gate that catches a missing
weak guard. Do NOT add the module's source to `test_apps_weak` to "fix" a
link error there -- that destroys the test's meaning.

## Failure mode 6: satisfying a new call by adding the PROVIDER everywhere

When an existing `.c` grows a call into another module, the tempting fix is to add
the provider's source to every link line that compiles it. Before doing that, check
what the provider itself drags in.

Observed: `wm_desktop.c` needed to know the guest sandbox root, so it called
`styxfs_guest_root()` -- which lives in `styxfs_host.c`, which references
`g_styxfs_server` from the 9P layer. Adding `$(RT)/styxfs_host.c` to every recipe
that links `wm_desktop.c` made three UNRELATED test targets go red on a missing
symbol, just to read one path. A blanket split-and-prefix over `mk/tests.mk`
multiplied the damage: it prefixed 14 sites at once, including targets that did not
need it, and had to be reverted (`git checkout mk/tests.mk`) before re-editing
target by target.

Rule: if the piece you need is small and dependency-free, EXTRACT IT INTO A LEAF
module (`<name>.h`/`<name>.c`, stdlib only) that both the heavy provider and your
caller include. The heavy provider keeps a shim for existing callers. One owner,
and no caller pays for globals it does not use.

Corollary for bulk edits: enumerate the affected recipes with
`grep -n '<source>\.c' mk/tests.mk`, then edit ONE recipe at a time anchored on a
unique token inside that recipe. Never a whole-file `str.replace` or a
split-and-prefix across a makefile -- `mk/tests.mk` has hundreds of similarly
shaped recipes and the blast radius is invisible until several gates are red.

## Related
- `wubuos-battleship-gaps`: N1 popen→argv-exec closure (92319ce) and
  N2-N4 supervisor wiring (228b75f) — the dependency additions this
  technique was needed for.
