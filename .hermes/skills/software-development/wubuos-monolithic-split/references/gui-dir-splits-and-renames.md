# GUI directory splits & symbol renames (* / wubu_*)

Recurring shape: re-home GUI files into layer subdirs (`compositor/`, `wm/`,
`shell/`, `theme/`, ...) to mirror Mint (Muffin WM + Cinnamon panel) / Win11
(DWM+MIL retained compositor), and relabel symbols to match. Two poly-moves
train the same five lessons.

## 1. Include-path rewrite after a `git mv` is PER-FILE, not a blind replace

Do NOT rewrite `#include "foo.h"` with a global substring pass. A regex that
adds `shell/` after stripping `../gui/` double-prefixes some files
(`../../wm.h` from a two-level-deep subdir) and under-corrects others.
Files that already resolved via `-I` flags (a header living in `runtime/`,
`kernel/`, or `compiler/` pulled as a flat name) get deeper `../` that points
at the wrong directory, and a `SOCK_NONBLOCK`-style fixture change is a
separate concern entirely.

Instead, per moved file compute the true relative path:
```python
import os
fdir=os.path.dirname(p); target=os.path.join(gui_shell, base)
corr=os.path.relpath(target, fdir)   # resolves from the FILE's dir
# then replace the include's dir part with corr
```
And after the pass, **verify tree-wide**: re-scan every `#include ""` that
names a moved header and `os.path.exists` its resolved path from the including
file's own directory. Zero broken includes is the commit bar, not "it seemed
to fix most."

## 2. The both-sides rename collision guard (namespace, not just symbol)

Before relabeling a symbol namespace (`wm_*` → `wubu_wm_*`), grep the
TARGET prefix for definitions that ALREADY exist under it — an orphaned
"shadow" retained line can own `wubu_wm_create/init/render` with a DIFFERENT
window type (`WubuWin*` vs `DosGuiWindow*`). Blindly renaming 93 files / 307
mk refs toward the occupied namespace produces duplicate-symbol link failures
(or accepts a type mismatch silently).

Guard: list every definition in the target namespace, check its type against
the source, and only proceed when the names are free OR you reconcile the two
lines first (fold the retained compositor into the live render path, then drop
the redundant shadow). A mass rename is never a cosmetic find-and-replace on a
live hub; it is a reconcile decision.

## 3. `mk/objects.mk` is a SEPARATE build surface from `mk/tests.mk`

Moving a `.c` that is in GUI_OBJS requires updating `.o` tokens in
`mk/objects.mk` (flat → subdir path) AND the `.c` tokens in each `mk/tests.mk`
recipe. GUI_OBJS is a mixed list — some entries are `.o`, some are raw `.c`
(`wm_layout.c`, `shell/wm_icons.c`) compiled in-place. Skipping
one of the three places (objects.mk, tests.mk compile line, tests.mk run line)
gives a phantom `No rule` / stale-object failure that looks unrelated. When a
module is extracted into a NEW file (e.g. a shared transport), add its `.o` to
GUI_OBJS (or RT_OBJS) AND add a standalone `test_<module>` recipe spliced at
the END of tests.mk — never inside an existing rule's run line (tab-indented
lines attach to the nearest preceding rule; see split-wip-recovery).

## 4. Extracted wire/transport layers earn their OWN behavior gate

When the reusable concern is socket/JSON transport pulled out of a panel,
the new module deserves a `test_<module>` that drives the REAL buffering, not
a stub: exercise `recv_line` splitting/partial-hold over a `socketpair`
loopback. A line-buffer unit test that reads from a **blocking** socket hangs
forever waiting for data — create the pair with `SOCK_STREAM | SOCK_NONBLOCK`
so a second `recv_line` with no full line returns 0 instead of blocking. The
JSON getter is cheap to gate against daemon-shaped fixtures
(`{"event":"root-create","root_name":"alpine","state":"active"}`).

## 5. God-header / no-god-header check by include grain, not line count

A 500-line single-concern module is NOT a monolith (it stays); a 200-line file
that mixes transport + event dispatch + UI + tray callbacks IS one (it
splits). Judge by include count and concern mix, not LOC. When marking a file
for split, identify the one reusable seam (the transport), extract it, and
leave the panel thinner — the win is a shared module + smaller TU + faster
incremental rebuild, not just "fewer lines."
