---
name: wubuos-battleship-gaps
description: Understanding WuBuOS BATTLESHIP.md gap analysis — form≠function REAL_GAPs (void-cast/return-const/stub on success path) vs defensive guards. v21 = ~400 sprint board + 5 parity epics. How to read and prioritize.
category: software-development
---

# WuBuOS BATTLESHIP Gap Analysis Skill

## The Numbers (v22 — 2026-07-08, HONEST RE-AUDIT — Triple DA)
- **~25 verifiable code-level REAL_GAPs** currently OPEN in `src/` (post-cycle 2026-07-08: 0 `system()` + 19 stub-phrase + 6 bare-metal no-op). Started at ~40; 10 `system()` + 4 stub-phrases (gamelib start-menu, vulkan memtype, container registry, term container PTY) + the E3 archd-service-manager integration are now CLOSED with regression tests. This is the TRUE reproducible sprint board — confirmed by reading each function body.
- **~370 parity-marathon REAL_GAPs** (ReactOS NT 297 + SteamOS ~30 + Ubuntu/Arch ~20 + TempleOS ~15 + ZealOS ~8), reclassified per the user's rule *"rewriting from scratch in C = REAL_GAP, including ReactOS gaps to WuBuOS."*
- **~400 total** = ~40 code + ~370 parity. (The v21 "~400 sprint" was NOT reproducible — the canonical scanner was broken; fixed 2026-07-08.)
- **Baseline stub class is CLOSED**: `find_real_gaps.py src` → **0 empty bodies, 0 const-only-no-syscall gaps** in `src/`. Scanner A's 76 "candidates" are all false positives (real work + `return 0` success).
- **Test gate = green build + `make test` pass.** Live target/assertion counts grow as suites land — run `make test` (and `make runtime`/`make hosted`) to verify rather than citing a fixed total.

### The test gate is INCREMENTAL — never `make clean` before a gate/ship (2026-11-07)
Many `test_*` recipes link SHARED prebuilt `.o` (referenced by LITERAL path in the
recipe, inline, NOT as prerequisites): `$(WUBU_DOS_EMU_OBJS)` (wubu_dos_emu*.o),
`vsl/vsl_*.o`, shell, gui/settings objects, styxfs_host.o, archd/bottle pieces. A
full `make clean` deletes them and every such target then fails to link with
`cannot find src/runtime/X.o` — the gate was NEVER clean-buildable. To run the
gate (or a pre-push ship.sh) after any clean, FIRST `make runtime` (materialize
the shared objects), THEN `make test-module`. A test recipe that lists a shared
`.o` inline will only link whatever is on disk: to make a specific target robust
to a clean tree, swap that `.o` to its `.c` in the recipe (it compiles with the
recipe's flags). Grep with `grep -nE "\.o\b" mk/tests.mk` to find them.

### The owned-surface manifest: "a module without a test = NOT owned" (GAP-C1/C2)
`scripts/owned_surface.py` derives the OWNED-vs-VENDORED inventory from the
Makefile recipes, not prose: a product `.c` is OWNED iff its basename appears in
any `test_*:` recipe (so it is compiled into a test binary = exercised).
- `scripts/owned_surface.py --write` regenerates `docs/owned-surface.md`.
- `scripts/owned_surface.py --check` (wired as `make test_owned_surface` into
  test-module) FAILS if an OWNED module lost its test recipe, or if the committed
  manifest went stale vs the recipes. This enforces the rule and catches drift.
- This is the honest quantitative lens on the "junk drawer" debt: most product
  sources are VENDORED (no recipe), e.g. a ~1322-unproven baseline. Use it to
  classify before deciding what needs a test, not a hand-count.

### Reproducible audit recipe (2026-07-08 — the board must be PROVABLE, not estimated)
Do NOT trust a handoff count or a stale "~400". Run the combined runner, then report
the RANGE (not a fake-precise single number):
```bash
cd /home/wubu/wubuos
python3 ~/.hermes/profiles/mind-palace/skills/software-development/wubuos-battleship-gaps/scripts/honest_gap_audit.py .
# Probe1 find_real_gaps.py src -> expect 0/0
# Probe2 live system() calls (comments excluded) -> 10
# Probe3 triaged stub-phrase funcs -> ~30
# Prints: code-level ~40 (range 36-42) + parity ~370 = ~400
```
Full method + the "scanner was lying" post-mortem + Scanner-A false-positive trap +
plumber deep-dive recipe: `references/honest-gap-audit-methodology-2026-07-08.md`.
**Critical**: a broken audit tool (`find_real_gaps.py` had a `SyntaxError` + swept
vendored libs for 2329 false hits) invisibly manufactured the old fake board. Trust
the scanner only after you've seen it print 0 on `src/`.

### How the ~400 was honestly derived (2026-07-08)
1. Fixed `scripts/find_real_gaps.py`: it had a `SyntaxError` (`"EPERM" not r`) and swept vendored `reference/`/`reactos-study/` libs (2329 false hits). Added `VENDOR_DIRS` exclusion + `not in r` fix → now 0 in `src/`.
2. Ran it on `src/`: 0 empty `{}`, 0 const-only-no-syscall. Baseline stub class closed.
3. Marker grep (`stub|not implemented|placeholder|for later`) + manual read → 23 genuine stub-phrase funcs.
4. `grep '\bsystem\s*\('` (excluding `replaces system` comments) → 10 live `system()` calls (REAL_GAPs by rule).
5. Bare-metal no-ops (`tasking.c` preempt/ctx-switch, `wubu_metal.c` `#else` audio/X11) → 6 (4 are correct `#else`).
6. Reclassified 5 parity epics as marathons per the reclassification rule → ~370.
7. Total ≈ 40 + 370 = ~410, rounded to ~400.

## The Key Insight (Triple DA Verified)
> "The bridge doesn't span the river." WuBuOS claims to be the BRIDGE between ReactOS NT (297 syscalls), SteamOS, Ubuntu/Arch, TempleOS, ZealOS — but the middle sections are MISSING. Parity epics capture THAT. The ~400 sprint board captures the concrete form≠function functions.

**Re-measurement (2026-07-07, src excluding *_test):**
- 455 `(void)param;` → ~180 real (rest = 6-register ABI / defensive)
- 1166 `return -1/0/NULL;` → ~90 real (rest = error-path guards)
- 99 stub phrases (TODO/FIXME/placeholder/hack/not-implemented/…) → ~80 real
- 0 empty `{}` bodies (already closed), 0 `system()` in src (all replaced)
- **Deduped → ~400 REAL_GAPs on the sprint board.**

**NOT gaps (don't count):**
- Defensive null checks / input validation on error paths.
- 6-register ABI void casts in `vsl_syscall.c` (d,e,f unused by convention) — 173 of them, verified NOT gaps.
- Test-file stubs (harness, not product).

## Stale Handoffs & Noisy Per-File Counts (HARD-WON, 2026-07-07)

BATTLESHIP's per-file "~53 open/creat/truncate mode/flags unused" style counts and the
handoff "NEXT OPEN REDS" list are **routinely stale/noisy**. Verified this session:

- **`vsl_syscall_fileio.c` is ~97% REAL.** `open`/`openat`/`creat`/`truncate` already
  pass `flags`+`mode` through to `vsl_open`/`open`. Its ~46 `(void)d;...` lines are
  correct-by-design (6-arg syscall shims must discard 5 unused slots). The "~53" was
  void-cast noise + the 6-arg shard, NOT unimplemented params. Don't take "~53" as a
  to-do list — read the function first.
- **Handoff "NEXT OPEN REDS" are ROUTINELY STALE.** The 2026-07-07 handoff listed
  `test_pkgmgr 8/11` and `test_network 114/139` as open — BOTH WERE ALREADY GREEN
  (11/11 via `b4d9b2d`, 139/139 via the network `p->enabled=true` fix). **Always
  re-run `make <target>` before trusting a handoff's red list.** A stale "open red" in
  the prompt does NOT mean you must fix it — confirm first.
- **Empty-body scans include test stubs.** `grep -n '{}'` flags ~27 `*_test_stub.c`
  linker shims (intentionally empty) + a few legit no-op lifecycle fns
  (`bridge_shutdown`, `task_preempt_disable/enable`). Exclude `src/**/*_test*.c` and
  known no-op lifecycle fns before counting.

### Stale repo PLAN/ROADMAP docs are false signals too (2026-07-19)
The "Stale Handoffs" rule above covers handoff red-lists. The **same trap applies
to in-repo plan/roadmap docs** — `DESKTOP_FIXUP_PLAN.md`, `DESKTOP_VISION_PLAN.md`,
`STATE.md`, `BATTLESHIP.md`, `slate.md`. This session a pasted
DESKTOP_FIXUP_PLAN.md claimed: (a) `ctx_action_*` functions were "empty stubs /
notify-only" (sort_by_name, create_shortcut, view, New→Folder all listed as
unimplemented); (b) `DOSGUI_MAX_ICONS=16` was a "hard limit"; (c) NT syscall
surface was "~20/297 transliterated". **All three were false against the actual
tree**: the ctx actions were fully wired real implementations, the cap was
already 64, and 148/297 NT handlers were done. Acting on the doc's claims would
have meant re-implementing working code (form-without-function churn).
**Rule:** before acting on a pasted or in-repo plan, run `git log --oneline -15`
and READ THE ACTUAL FUNCTION BODIES the plan names. Treat the doc as a *hypothesis
to verify*, not a status report. If the code already does what the doc says is
missing, say so and move to the next real gap. (This is the flip side of the
"Stub banner comments are false signals" pitfall — here the FALSE signal is an
entire roadmap doc, not just a banner.)

### How to mine the board for a REAL gap (reproducible probe)

Don't chase the ~400 by per-file grep count — most is noise. To find a concrete,
testable gap, run the bundled probe (excludes test/stub files + ABI void-casts + known
no-op lifecycle fns, then surfaces empty bodies and const-only-return fns that make NO
host syscall call):

```bash
cd /home/wubu/wubuos
python3 ~/.hermes/profiles/mind-palace/skills/software-development/wubuos-battleship-gaps/scripts/find_real_gaps.py . --dirs runtime/vsl runtime gui kernel bridge styx
```

Then for each candidate, READ THE ACTUAL FUNCTION: confirm it's on a success path that
should do work (not an error guard, not a no-op lifecycle fn). This method found the
real one this session — `vsl_sys_getresuid`/`getresgid` backfilled `suid`/`sgid` from a
**host** `getresuid(NULL,NULL,&s)` call (no `suid`/`sgid` on `VSL_PROC` at all) → fixed
in `e89c828`. The board's top-of-list files (wubu_metal, vsl_syscall_net, styxfs) are
dominated by void-cast/error-path noise too — verify per-function.

### Dropped-buffer heuristic (highest-signal probe, 2026-07-07)
Beyond empty-body / const-only, the best form≠function detector is: **a function
that takes a `*buf`/`out`/`data`/`result` output pointer but never writes to it,
and makes no host syscall that writes** (no `stat`/`fstatat`/`lstat`/`read`/
`pread`/`readlink`/`getdents`). Such a function silently swallows its output —
true gap. In this session the probe found **ZERO** such cases across
`styx.c`/`styxfs.c`/`wubu_network.c`/`wubu_snapshot.c`/`jit/wubu_x86.c` — they
all write or call a real host syscall. The ~400 board is dominated by noise.

### Concrete per-file verdicts (gate-tested layer, 2026-07-07) — READ BEFORE COUNTING
- `vsl_syscall_fileio.c` — REAL. `open`/`openat`/`creat`/`truncate` already
  pass `flags`+`mode` to `vsl_open`/`open`. "~53" = void-cast noise + the 6-arg shard.
- `vsl_syscall_memory.c` — REAL. `mmap`/`mprotect`/`shm*`/`mremap` forward args; 0 dropped-buffer gaps.
- `wubu_network.c` — REAL in-memory impl; `TODO-NET` block = *documented limitations*, not stubs.
- `styx.c`/`styxfs.c` — REAL. 9P callbacks write via `memcpy`/`stat`/`read`; 0 pure-return stubs.
- `vsl_syscall_net.c` — REAL. "return const" greps false-positive on the legit `result<0?-errno:result` pattern.
- `wubu_x86.c` "placeholder" = rel32 backpatch slots, NOT empty stubs.

### Real gaps actually closed this session (proof the method works)
- `vsl_sys_getresuid`/`getresgid` (commit **e89c828**): backfilled `suid`/`sgid`
  from a HOST `getresuid(NULL,NULL,&s)` — no `suid`/`sgid` on `VSL_PROC`. Fixed via
  struct field + per-process tracking at spawn + persistence in *set* handlers.
  The test caught it (pre-fix 2 FAILs in WSL where host saved-set ≠ euid).
- `wubu_proton2.c::wubu_proton_verify_installation` (commit **b33ca26**): returned
  0 whenever `container_running`, never checked Wine/prefix existed. Fixed with
  `access(X_OK)` + `stat(S_ISDIR)`.
- `wubu_bottles.c::wubu_bottle_install_deps` (commit **17a79e8**): returned 0
  without applying anything — deps never marked installed, no prefix validated.
  Fixed by rejecting missing `WINEPREFIX` dir (`stat S_ISDIR`), recording the
  prefix path, and marking deps + bottle `installed=true`. NOTE: `wubu_bottles.c`
  opens with a *"Stub implementation"* banner comment but is otherwise COMPLETE —
  trust the empty-body scan, not the banner (see pitfall below).

### Pitfall: "Stub" banner comments are false signals
`wubu_bottles.c` declares "Cell 480: Stub implementation" at the top but is
fully implemented except the one empty `install_deps`. Likewise
`wubu_proton2.c`'s "TODO-NET" block is *documented limitations*, not empty
stubs. Before counting a file as "thin/stub," run an empty-body scan
(`scripts/find_real_gaps.py`) and read the actual functions. BATTLESHIP's
per-file bottle count "~20 lifecycle thin" is inflated by the misleading
header. Full before/after in `references/bottles-gap-closure-patterns.md`.

### Pitfall: the gap-scanner itself can lie (2026-07-08)
`scripts/find_real_gaps.py` was broken for weeks: a `SyntaxError` (`"EPERM" not r`
instead of `"EPERM" not in r`) made it crash, and it swept vendored `reference/`
libsndfile/portaudio/flac + `reactos-study/` for **2329 false-positive** const-only
returns. The v21 "~400 sprint" board was built on this broken output. **Fix applied
2026-07-08**: `not in r` correction + a `VENDOR_DIRS` exclusion tuple. Re-run on
`src/` now yields **0 empty bodies, 0 const-only-no-syscall gaps**. **Always run the
scanner on `src/` (not `.`) and trust the 0 count** — if it ever reports >0 empty
bodies, the board has drifted; re-audit.

### User reclassification rule (2026-07-08 — load-bearing)
> *"Rewriting from scratch in C is the point of the project. Anything that falls
> under that is reclassified as work REAL_GAP. This also goes for ReactOS gaps to
> WuBuOS."*
This means the honest ~400 = **~40 verifiable code-level gaps + ~370 parity marathons**
(ReactOS NT 297 syscalls + SteamOS/Ubuntu-Arch/TempleOS/ZealOS missing subsystems).
Do NOT micro-count void casts to reach 400 — that was the v20/v21 error. The parity
epics ARE the bulk of the work; treat each missing subsystem as a "rewrite in C"
marathon.

### Pitfall: two parallel Proton modules
`wubu_proton.c` (legacy, `make test_proton`, `wubu_proton_t`) ≠ `wubu_proton2.c`
(Arch container + GameScope, `make test_proton2`, `WubuProtonManager`). A Proton
gap in `wubu_proton2.c` is NOT covered by `test_proton` — target the right module
and add the assertion to `wubu_proton2_test.c`. See
`references/real-gap-probe-methodology.md` for the full probe + verdict detail.

### Closure Technique: system()→fork+exec (2026-07-08, session a74dd7b)
Closing a live `system("cmd")` = replace with a shared, **dependency-free**
`wubu_run_program(file, argv[], silent)` (fork+execvp, no `/bin/sh`), defined in
its own `src/runtime/wubu_spawn.c` (+ `wubu_spawn.h`). Do NOT define it in
`wubu_exec.c` — that drags in container/compiler/HolyC objects and cascades a
link explosion. Full pattern + 5 concrete pitfalls below:

- **PITFALL — quote-termination in a hand tokenizer.** When splitting
  `system("x 'a b c'")` into argv yourself, a naive `if (*p=='\''){in_q=!in_q;p++;continue;}`
  leaves the `'` INSIDE the token (`argv[1]="a b c'"`). You must `*p='\0'; argv[argc++]=tok;`
  AT the closing quote. Test: `net_cmd("touch 'a b c'")` creates exactly one file
  `a b c` (no word-split, no `>` redirect — `>` stays a literal arg).
- **PITFALL — Makefile link cascade.** Every direct-link target using the helper
  must add `$(RT)/wubu_spawn.c` to ITS link line or you get
  `undefined reference to wubu_run_program`. That includes all `$(JIT_SRCS)`
  targets (grep for them) + self-contained ones (`wubu_image_ops.c`,
  `wubu_netlink.c`, `wubu_codec.c`). Also add it to `RT_OBJS`. After edits:
  `make clean && make runtime && make hosted && make test`, and grep `make test`
  output for `error|undefined reference` (the colorized tail hides them).
- **PITFALL — qsort of `T*` needs a double-deref comparator.** `ga=(T*)a` is
  wrong when sorting an array of `T*`; use `ga=*(const T*const*)a`. A 1-element
  array masks this (qsort no-op) — test with ≥2.
- **PITFALL — static `filtered[]` buffer vs. live instance.** A function that
  reads `g_gamelib.games[]` through `list_games()`'s static `filtered[]` can
  resolve to a different `g_gamelib` than the caller (cross-TU static global),
  yielding empty/garbage fields. Prefer iterating `g_gamelib.games[]` directly
  in the caller.
- **Exit codes:** a missing program returns **127** (exec failed), not -1;
  propagate `WEXITSTATUS`. The regression test must assert 127, not -1.
- Every closure needs a FIXED-BEHAVIOR test (`test_spawn`, `test_container_registry`,
  extended `wubu_gamelib_test.c`), not just non-crash.

Full detail + code: `references/system-fork-exec-closure-2026-07-08.md`.

### TLS Migration: mbedTLS → OpenSSL (2026-07-24)
The OCI HTTP client's mbedTLS backend was unavailable on the build system. Migrated to OpenSSL (system `libssl-dev` available). See `references/tls-openssl-migration-2026-07-24.md` for the complete pattern including:
- Shared `SSL_CTX` initialization
- `SSL_new`/`SSL_connect`/`SSL_read`/`SSL_write`/`SSL_shutdown` lifecycle
- Proper `SSL_get_error` handling for `WANT_READ`/`WANT_WRITE`
- Makefile link flag updates (`-lssl -lcrypto`)
- Test verification via `make test_oci` and `make test_pkgmgr`

### Closure Technique: wire an existing daemon as the Desktop backend (E3, 2026-07-08, commit 8b4b74f)
"Existing daemon exists but NOT wired as the Desktop's X" is a form≠function gap
(daemon-as-backend parity). The fix is a real integration layer, not a socket client:
- A Desktop-side manager module (`service_mgr.c`/`.h`) holds the live daemon
  instance (`static WubuArchd g_archd;`) + Desktop-specific bookkeeping (autostart
  list), and calls the daemon's REAL API (`wubu_archd_init`/`svc_start`/`svc_stop`/
  `shutdown`).
- Wire it into the Desktop lifecycle: `desktop_init()` →
  `service_mgr_init()` + `_boot()`; `desktop_shutdown()` →
  `service_mgr_shutdown()`. That is what makes it "wired", not just callable.
- Regression test asserts behavior your module OWNS (init creates a live handle,
  registration dedup + invalid-reject, `boot()` iterates every entry and calls the
  daemon API once per entry recording per-entry results, clean shutdown + idempotent
  re-init) — NOT the (sandbox-unavailable) side effect like `arch-chroot systemctl
  start`. Assert the *attempt* happened, not that systemd started.
- **PITFALL — the daemon `.c` has its own `main()`.** `wubu_archd.c` guards it with
  `#ifndef WUBD_TEST_MAIN`; linking it into `hosted`/a GUI test (which have their own
  `main`) gives `multiple definition of 'main'`. Add `-DWUBD_TEST_MAIN` to every link
  line that includes `wubu_archd.c`. (`hosted.c`'s `main` is NOT guarded, so the define
  only suppresses archd's — correct.)
- **PITFALL — dep cascade.** `wubu_archd.c` pulls `wubu_arch.c`/`wubu_ramdisk.c`/
  `wubu_container.c`/`styx.c`/`styxfs.c`/`wubu_host_exec.c`/`wubu_ct_isolate.c`. Every
  target gaining the module must list `wubu_archd.c` + those deps or you get
  `undefined reference to wubu_archd_init`/`wubu_arch_bootstrap`. Affected this
  session: `hosted`, `test_hosted`, `test_daemon_panel`, `test_service_mgr`.
- **PITFALL — pre-existing broken targets.** `test_hosted` was ALREADY broken at
  baseline (missing `wubu_welcome.c`, `wubu_wallpaper.c`, `hc_eval`, … present in the
  working `hosted` binary but absent from `test_hosted`'s link line). Confirm with
  `git stash` + run at baseline before assuming your change broke it; then align the
  object list with `hosted`. `test_hosted` is NOT in the `make test` aggregate.

Full recipe + Makefile fragments: `references/daemon-desktop-integration-e3-2026-07-08.md`.

### Closure Technique: embed a daemon REPL as a PTY-backed process in a terminal tab (E4, 2026-07-08, commit 7c1cfe1)
"A terminal tab shows a placeholder instead of the real daemon REPL" is a
form≠function gap (REPL-as-Desktop-backend parity). The fix is to host the daemon's
REAL in-process eval API as a live PTY process in the tab — NOT to write a second REPL:
- Add a `--repl` TTY mode to the daemon's `main` (`wubu_holyd_lifecycle.c`): create a
  session, `wubu_holyd_repl_start`, then `while(fgets) wubu_holyd_repl_eval(...)`. This
  reuses the genuine compiler path; `echo '1+2*3' | wubu_holyd --repl` → `9`.
- Build a REPL binary target (`wubu_holyd_bin`) WITHOUT `-DWUBD_TEST_MAIN` so the daemon
  `main` is the entry; link the daemon `.c` + `holyc_*.c` + `JIT_SRCS` + `wubu_spawn.c`.
- Make the tab's session struct **embed a `TermPtySession pty`** (drop the opaque
  `holyc_term` field) and spawn `wubu_holyd --repl` via `term_pty_spawn`. Route
  render/key/IO to that PTY by reusing the shell-tab paths.
- **PITFALL — `term_pty_spawn` needs an argv param.** It only took a single shell string
  (`execvp(shell,{"shell","-l"})`); extend with `const char *const *extra_argv` (NULL =
  default `{"-l"}`) so `wubu_holyd --repl` works. Update ALL callers + BOTH header decls.
- **PITFALL — daemon `.c` has its own `main()`** (guarded by `#ifndef WUBD_TEST_MAIN`):
  add `-DWUBD_TEST_MAIN` to every link line that includes the daemon `.c`, or you get
  `multiple definition of 'main'`. (Same trap as E3's `wubu_archd.c`.)
- **PITFALL — dep cascade**: the daemon `.c` pulls holyd + compiler (`holyc_*.c`) +
  `JIT_SRCS`; any target gaining the REPL module must list them or get
  `undefined reference to wubu_holyd_*`. Affected: `wubu_holyd_bin`, `hosted`,
  `test_hosted`, `test_term`.
- **PITFALL — pre-existing broken `test_hosted`** (missing `wubu_welcome.c`,
  `wubu_wallpaper.c`, `hc_eval`): confirm at baseline with `git stash` before assuming
  your change broke it; then align its object list with `hosted`. `test_hosted` is NOT in
  the `make test` aggregate.
- Regression test `test_holyc_embed` (in `test_term`) asserts the TERMINAL-LAYER
  wiring: HolyC tab spawns a REPL PTY (`ptm_fd >= 0`) and routes keystrokes to it — not
  just non-crash. The REPL's eval itself is covered by `make test_holyd`.

Full recipe + Makefile fragment: `references/embed-daemon-repl-in-terminal-e4-2026-07-08.md`.

### Closure Technique: ReactOS NT syscall transliteration into real VSL handlers (E1, 2026-07-08→09, commits a15b04e + a4ae8a9 + 2026-07-24 blitz)

"297 NT syscalls mapped in `vsl_nt_bridge.h` but 0 wired to real work" is the single
largest parity block. Each closure = write a REAL VSL handler in C (genuine OS
work, not a stub) + wire it into TWO dispatch tables + add a fixed-behavior
regression check. The dispatch path is `vsl_nt_syscall_dispatch(&ctx, NN, args, n)`
(backed by local `g_nt_dispatch[]` in `vsl_syscall_nt.c`), and the canonical
`vsl_syscall_table[]` (backed by `vsl_sys_nosys` slots in `vsl_syscall_table.c`).

**Status: E1 COMPLETE (2026-07-24)** — all 296 ReactOS NT syscalls transliterated
with real POSIX implementations. Test suite: `test_vsl_nt` — 251 checks pass,
all asserting real work (eventfd, mmap, fork, pthread, ioctl, fcntl, etc.).

**Recipe (per syscall):**
1. Pick the NT number from `vsl_nt_bridge.h` `#define NT_SYSCALL_NT<NAME> 0x00NN`
   and CROSS-CHECK against `reactos-study/reactos/ntoskrnl/sysfuncs.lst` (the
   bridge.h numbers ARE the ReactOS ordinals — 9/256/266 all verified). Wrong
   ordinal = handler in the wrong dispatch slot.
2. Add the forward decl `int64_t vsl_nt_<name>(uint64_t,uint64_t,uint64_t,uint64_t,uint64_t,uint64_t);`
   to `vsl_syscall_nt.c` AND the matching `extern` in `vsl_syscall_table.c`.
3. Wire BOTH tables: `g_nt_dispatch[NN-1] = vsl_nt_<name>;` in `nt_dispatch_init`,
   and replace `vsl_sys_nosys,  // NN: Nt<Name>` with `vsl_nt_<name>,  // NN: Nt<Name>`
   in `vsl_syscall_table[]`. Both required — local backs the unit test, canonical
   backs `make runtime`.
4. Implement real work; return `NT_STATUS_SUCCESS` or negative errno (dispatch
   wraps it via `vsl_errno_to_nt_status`).
5. Add fixed-behavior CHECKs to `vsl_syscall_nt_test.c`; run `make runtime && make hosted && make test`.

**Handler patterns that worked:** atom table (process-local `g_nt_atoms[]`); 
`NtAllocateUuids` = `getrandom` + RFC4122 v4/variant bits; `NtSetUuidSeed` = global
seed → deterministic xorshift bytes; `NtClearEvent` = `write(eventfd,&zero)`;
`NtAlertThread` = `syscall(SYS_futex, FUTEX_WAKE)`; `NtCancelIoFile` = `shutdown()`;
`NtAreMappedFilesTheSame` = `stat` inode/dev compare; `NtFlushWriteBuffer` =
`fdatasync` (tolerate EINVAL/EROFS on pipes).
- **PITFALL — job objects MUST use an isolated sentinel-child process group.**
  `NtTerminateJobObject` does `kill(-pgid, SIGKILL)`. If you make the CALLER its
  own group leader (`setpgid(0,0)` → `pgid == getpid()`), terminating the job
  SIGKILLs the test → silent exit 137 with no output. CORRECT: `NtCreateJobObject`
  forks a sentinel child that `setpgid(0,0)`+`pause()`s, records `child_pid` as
  the job `pgid`; terminate does `kill(-child_pid, SIGKILL)` + `waitpid` to reap.
  Caller survives. Regression: create→open(same id)→terminate→open-after = NOT_FOUND.
- **PITFALL — cross-handler `static` state must be file-scope, declared BEFORE its
  first use** (e.g. `g_nt_uuid_seed` read inside `vsl_nt_allocate_uuids` early in
  the file). A later `static` decl → "undeclared (first use)". Declare near the
  forward decls block.
- **PITFALL — WSL link weight.** `make test_vsl_nt` links `-lvulkan -lcuda`; a
  single-shot run can look "Killed" (OOM 137) or "hang" (the 180s timeout was just
  the heavy link compile, NOT a hang). Re-run the built binary directly:
  `timeout 25 stdbuf -oL ./src/runtime/wubu_vsl_nt_test`. Distinguish self-kill (dies
  mid-test after "NtCreateJobObject") from OOM (dies at link/startup).
- **Next batch:** `grep -nE 'vsl_sys_nosys,  // [0-9]+: Nt' src/runtime/vsl/vsl_syscall_table.c`
  for stubbed slots; pick ones mapping to a real host primitive. Regression count:
  `vsl_syscall_nt_test.c` went 25 → 49 → 149 → **251 checks**.
- Full recipe + pitfalls: `references/reactos-nt-transliteration-e1-2026-07-09.md`.

### Parity Technique: theme-driven chrome — post-98 visuals never leak into Win98 Classic
Desktop-shell parity work (XP, Zune, Media Center, WuBu) is a THEME problem,
not a rewrite problem. The theme engine already discriminates:
`const WubuThemeColors *tc(void)` and `const WubuTheme *theme(void)` are both
exported from `wm_internal.h`, and `theme()->Luna_start_button` is true
for every post-98 theme. Guard each parity visual with it so Win98 Classic keeps
its authentic 3D chrome:

```c
if (theme()->Luna_start_button) {
    /* XP-flavored drawing (flat taskbar buttons, red close, green orb) */
} else {
    /* original Win98 3D drawing */
}
```

Rules that make parity work verify itself:
- **One visual identity per element, not a gradient of them.** XP's signatures
  are discrete: close = red rounded rect + white bold X; start orb = green pill
  + vertical gradient + flag emblem + bold white "start"; taskbar buttons =
  flat, active gets a pale-blue face with a 1px Luna-blue edge. Implement each
  as a whole look, then gate it.
- **Run `make test_wm` after every chrome change** — the WM suite
  (33 checks) exercises the taskbar/chrome/icon paths and catches color or
  layout regressions.
- **Verify visually, not by eye:** `make gui_shot` captures real frames of every
  theme phase (00_desktop_win98 … 05_apps_wubu) to `/tmp/wubu_gui_shots/`.
  If that target does not build or crashes, fix it FIRST — it is the only
  honest visual gate for GUI parity (build/run procedure:
  `wubunos-hosted-capture-bridge`).

Remaining surfaces for a "complete XP parity" pass, in dependency order:
window title-bar gradients, minimize/maximize glyphs, start-menu flyout,
XP welcome/logon screen.

### Closure Technique: desktop delete → Recycle Bin (ReactOS CDesktopFolder::Delete), 2026-07-19, commit a4338a9
"Right-click Delete hides the icon but the file stays on disk and returns on
Refresh" is a form≠function gap. The fix is NOT to re-implement delete — the
Recycle Bin helper `wubu_trash_move()` already exists; the gap was that (1) the
delete handler never called it, and (2) `wubu_trash_init()` was only called by
the trash unit test, so in production `g_trash.trash_dir` was empty and the move
silently no-op'd.
- `desktop_init()` → `wubu_trash_init()` (boot wiring; trash dir exists at startup).
- `dialog_delete_on_key` confirm → `wubu_trash_move(icon->target)` then `alive=false`;
  also loop every `alive && selected` icon (multi-select delete).
- Add `wm_compact_icons()` to compact dead entries after delete.
- Regression: `test_icon_delete_moves_to_trash` + `test_icon_multiselect_delete`.
- PITFALL (test fixtures): don't name a fixture with the same prefix as the trash
  dir (`Trash.desktop` vs `.../Trash`) — `wubu_trash_move` refuses to trash the
  trash dir itself and returns -1. Use `Note.desktop`.
- PITFALL (link cascade): any test recipe compiling `wm_ctxmenu.c` must add
  `wubu_trash.c` + `wubu_arch.c` to its link line (trash → arch mkdir_p + settings)
  or you get `undefined reference to wubu_trash_move`. Affected: `test_wm`,
  `test_control`.
Full recipe + fixture pitfall: `references/desktop-delete-to-trash-2026-07-19.md`.

### Pitfall: dangling orphaned headers are MASSIVE form≠function gaps (2026-07-07)
A half-finished legacy purge can leave the **header behind while deleting the
`.c` body** — a gap the auto-probe and the gate BOTH miss. Concrete case: the
Stream-5 purge deleted `src/gui/wm.c` / `theme.c` / `startmenu.c` / `desktop.c`
(and `wm_test.c`, `vbe_legacy.h`) but left `src/gui/wm.h` / `theme.h` /
`startmenu.h` in place. 11 files still `#include` the orphaned headers and call
the OLD API (`WmWindow` struct, `wm_create_window`, `wm_invalidate`,
`startmenu_init`, `theme_color`) whose real impls are the `*` /
`wubu_theme_*` versions. This survives a GREEN gate only because `CFLAGS` carries
`-Wno-implicit-function-declaration` (which suppresses the missing-declaration
errors) — at link time the symbols are silently absent, and the gate never links
those app/`tools` files (see gate-coverage blindness in `wubuos-test-suite`).
**Detection recipe** when a purge/refactor deletes a `.c`:
1. After deleting `X.c`, find every `#include "X.h"` (and sibling/`../gui/X.h`
   variants): `grep -rln '#include "X.h"' src --include=*.c --include=*.h`.
2. For each includer, check whether the symbols it uses still have a definition
   ANYWHERE in the tree (`grep -rn '^<ret> <sym>(' src --include=*.c`). If the
   `.c` body is gone and there is no shim, that includer is now a latent break.
3. Either DELETE the orphaned header + repoint includers to the live header, or
   provide a thin compat `#define` shim (old name → new `*` name). Don't
   leave the header dangling — that's form≠function by omission.
4. Then run `make <app-target>` / `make tools` (not just `make test`) to prove
   the formerly-orphaned files still compile+link. The gate will NOT catch it.

### COMPLETED closure — orphaned-header purge (2026-07-07, commit db217fe)
The orphaned-header gap described above was **fully closed this session** (it is
NO LONGER dangling / a latent break). What was actually done:
- **`wm.h` → compat shim** (NOT a delete): it now `#include "wm.h"` +
  `#include "wubu_theme.h"`, `typedef`s `WmWindow = DosGuiWindow`,
  `WinFlags = DosGuiWinFlags`, maps `WM_*`/`WIN_*` constants, and aliases ONLY
  the genuine old-WM entry points (`wm_create_window`→`wm_create`,
  `wm_invalidate`→`wm_invalidate`, `wm_render`, `wm_handle_mouse`, …).
  **CRITICAL: do NOT use a catch-all `#define wm_ wm_`** — that would
  corrupt Wayland `xdg_wm_base_*` symbols in `src/hosted/hosted.c` (the substring
  `wm_base` matches). Alias only the specific old-WM functions the apps call.
- **Deleted orphan `theme.h`** (zero includers — verified with
  `grep -rln '#include "theme.h"'`, which matched only `wubu_theme.h`).
- **Deleted orphan `startmenu.h` + dead `startmenu_test.c`** — `startmenu_test.c`
  was NEVER compiled by any Makefile target (the real start-menu gate target is
  `test_startmenu`, which builds `startmenu_test.c` and calls
  `startmenu_*`); it only referenced the removed `startmenu_*` API, so it
  was dead code. `startmenu.h` was included ONLY by that dead file.
- **6 apps** (`notepad/doom/explorer/terminal/paint/control`) had their draw
  callbacks changed `void *fb` → `uint32_t *fb` to match the live
  `DosGuiWindow.on_draw` signature (the shim's `WmWindow=DosGuiWindow` alone
  isn't enough — the callback fn-pointer types must match too). All 6 compile.
- **Weak-symbol defaults added to `wm.c`** so standalone app binaries
  (paint/doom) link without the hosted Wayland stack:
  `__attribute__((weak)) void platform_shutdown(void){}` and
  `void shutdown(void){}`. `hosted.c` provides the real (non-weak)
  definitions; the linker picks those when present, the weak no-op otherwise.
- **Stray includes fixed**: `hosted.c` / `wubu_demo_record.c` had
  `#include "../gui/startmenu.h"` (deleted) → repointed to `startmenu.h`
  (they already included it alongside; the old include was redundant/harmless
  but broke after the delete).
- **Real invalidate API** added (not a no-op): `wm_invalidate(win)` tracks
  a per-window dirty ring, `wm_invalidate_all()` flags full-redraw,
  `wm_poll_dirty(out_id)` drains (-1 = redraw-all),
  `wm_dirty_count()` returns -1 if full-redraw pending. Covered by
  `test_invalidate_tracking` in `wm_test.c` (now 19/19).

**Reusable compat-shim recipe** (old-API → live-API purge closure):
1. Keep the old header as a *shim* that includes the live header and re-aliases
   the old identifiers (`typedef`, `#define`) — don't delete it if live code
   still `#include`s it.
2. Alias ONLY the genuine old symbols (verify with a precise regex that excludes
   ``/`xdg_`/`wl_` prefixes so you don't corrupt unrelated tokens).
3. If the live struct has a stricter callback signature (e.g. `uint32_t *fb`
   vs `void *fb`), you MUST patch the callback definitions, not just the typedef.
4. For symbols that only make sense in the full hosted binary (platform shutdown,
   Wayland globals), provide **weak no-op defaults** in the core lib so standalone
   binaries link and degrade gracefully.
5. Delete headers that have ZERO includers (verify first!) and dead source files
   that no Makefile target compiles.
6. Prove it: `make tools` + compile each affected app `-c` + full gate.

**RESOLVED (2026-07-12):** `make paint` / `make doom` no longer exist. The
Wolfenstein-3D `doom.c` raycaster (a CLONE, not the accepted FreeDoom) and the
MS-Paint `paint.c` toy were **deleted**; `make canvas` now builds
`src/apps/canvas_standalone.c` (real `main()` driving the `wubu_canvas` engine),
and the shell Paint icon (`DESK_ICON_PAINT`) launches the real WuBu Canvas
editor. All builds + `make test` gate are green. The old "just add $(GUI_OBJS)"
rabbit-hole diagnosis is moot — those clones are gone.

### User standard: delete toy/clone impls, REPOINT to the real engine (2026-07-12)
When the user rejects a fake/clone/toy implementation (e.g. "delete the wolf3d
raycaster, we only accept FreeDoom" or "paint is an MS-Paint toy, replace it with
a real editor"), the deletion is NOT finished until every reference is fixed.
Half-deleting leaves form≠function landmines the gate won't catch. Full checklist:
1. **Delete the source**: `git rm` the `.c` + `.h` (and any `apps_standalone.c`
   shim that only wrapped it).
2. **Makefile — every reference**: remove the target, the link line's
   `$(APPS)/X.c` mention, the `X` entry from `APP_OBJS`/`APP_RT_OBJS`/object
   lists, the `$(APPS)/X/%.o` pattern rule, and the `X` binary from `clean`'s
   `rm`. Grep `Makefile` for `X` to be sure.
3. **Shell app registry** (`src/apps/apps.c`): repoint the desktop icon
   to launch the REAL engine (e.g. `DESK_ICON_PAINT` → `launch_canvas`).
4. **Dead header decls** (`app_draw.h`, etc.): remove `app_draw_X` / `app_X_init`
   prototypes that no longer have a definition. (Keep the real engine's hooks.)
5. **Test suite**: the deleted API's unit tests must be rewritten against the
   REAL engine (e.g. old `paint_create`/`paint_add_shape` tests →
   `wubu_cv_create`/`wubu_cv_layer_add`/`wubu_cv_brush`/`wubu_cv_undo` tests).
   Don't leave orphaned `test_X_*` referencing deleted symbols — the gate WILL
   fail to compile them.
6. **Provide a real standalone entry** if a `make X` binary is expected: write a
   `X_standalone.c` with a real `main()` driving the real engine (boot VBE + WM +
   render loop), like `canvas_standalone.c`.
7. **Verify**: `make clean && make runtime && make hosted && make apps && make
   canvas && make test` — all green.

**Open gap flagged (not fixed):** `app_draw_canvas` is declared in `app_draw.h`
but NEVER defined — the in-shell WuBu Canvas editor has no actual `on_draw`
render binding yet (the standalone `canvas` binary composites directly to the fb,
so it works; the desktop-launched editor does not render). This is a real
form≠function gap for the in-shell editor. Future session: implement
`app_draw_canvas` to composite `wubu_canvas` into the window fb.
| Parity Target | Gap % | Key Missing |
|---------------|-------|-------------|
| SteamOS | 95% | CEF UI, Steam Input, Steam Networking, Proton, gamescope, Pressure Vessel |
| Ubuntu/Arch | 80-95% | systemd, apt/pacman, NetworkManager, Polkit, D-Bus, PipeWire, CUPS, AppArmor |
| TempleOS | 70% | HolyC JIT AOT+JIT, Doc/DolDoc, Compiler-as-lib, RedSea FS, Ring-0 |
| ZealOS | 67% | Identity-mapped memory, VGA/VESA direct, PC speaker |
| ReactOS NT | 7% implemented (2026-07-09) | 297 syscalls mapped → **20 transliterated** to real VSL handlers (batch 1 = 10, batch 2 = 10); 277 remain. See "Closure Technique: ReactOS NT syscall transliteration (E1)" |

**But defensive null checks in error paths are NOT gaps** — the happy path works.

## Gap Categories (v21 — Triple DA, form≠function)

**Sprint board (~400, actionable):** void-cast/return-const/stub on success path across 73 files. Top: wubu_metal(70), vsl_syscall_net(67), styxfs(65), interrupt(54), vsl_syscall_fileio(53), vsl_syscall_proc(47), wubu_network(46), styx(45), wubu_syscall(36), wubu_snapshot(34). Full list in BATTLESHIP.md.

**Parity epics (5, marathons, NOT in 400):** SteamOS / Ubuntu-Arch / TempleOS / ZealOS / ReactOS. Each = "rewrite the subsystem in C". Tracked as streams with child-gap estimates; not micro-counted.

## Comprehensive Audit Methodology (v21 — Triple DA)

The audit combines **code-level stub hunt** + **architectural parity audit**:

### Phase 1: Code-Level Stub Hunt (automated)
```python
# Patterns scanned across 349 WuBuOS source files:
PATTERNS = [
    (r'^\s*\(\s*void\s*\)\s*\w+\s*;\s*$', 'void_cast_only'),
    (r'^\s*\{\s*\}\s*$', 'empty_body'),
    (r'^\s*return\s+[-]?\d+\s*;\s*(//.*)?$', 'return_constant'),
    (r'//\s*(TODO|FIXME|STUB|XXX|HACK|PLACEHOLDER|NOT\s+IMPLEMENTED)\b', 'comment_todo'),
    (r'/\*.*(TODO|FIXME|STUB|XXX|HACK|PLACEHOLDER|NOT\s+IMPLEMENTED).*\*/', 'block_todo'),
    (r'\b(for later|for brevity|scaffolding|placeholder|not implemented|stub for extension|for extension|to be implemented|TBD|NYI)\b', 'stub_keyword'),
    (r'\bUNIMPLEMENTED\b', 'unimplemented_macro'),
]
```

### Phase 2: Architectural Parity Audit (Devil's Advocate)
For each parity target, ask:
1. "What does [SteamOS/Ubuntu/TempleOS] actually DO?"
2. "What does WuBuOS have?"
3. "Is the gap a different design, or missing implementation?"

**Triple DA Verdict**: These ARE gaps — WuBuOS claims to be the bridge but doesn't span them.

### Phase 3: Deep Dive Plumber Audit
Function-level parity check on critical paths:
- Read actual implementation vs. parity target requirements
- UX flow comparison (boot, app launch, file mgmt, audio, networking, updates, input, security)
- Every critical function shows: **form exists, function missing**

## Prioritization Strategy (v20 — Parallel Execution)

**NO PICK ONE — PARALLEL UNTIL 3000 → 0**

| Stream | Target | Gaps | Key Missing |
|--------|--------|------|-------------|
| **A** | SteamOS Parity | ~400 | CEF UI, Steam Input, Steam Networking, Proton, gamescope, Pressure Vessel |
| **B** | Ubuntu/Arch Parity | ~450 | systemd, apt/pacman, NetworkManager, Polkit, D-Bus, PipeWire, CUPS |
| **C** | TempleOS Parity | ~350 | HolyC JIT AOT+JIT, Doc/DolDoc, Compiler-as-lib, RedSea FS, Ring-0 |
| **D** | ZealOS Parity | ~200 | Identity-mapped memory, VGA/VESA direct, PC speaker |
| **E** | ReactOS NT Emulation | ~162 | 297 syscalls → VSL/Styx9/ZealOS/TempleOS pipeline |
| **F** | Code-Level Gaps | 1,423 | Every `system()`, `{}`, `(void)`, `TODO`, `return -1` in 73 files |

**Rule**: Every gap = "rewriting from scratch in C" — that IS the work.

## Gap Categories (from BATTLESHIP.md v16 — 2026-07-04)

| Category | Files | REAL_GAPs | Severity |
|----------|-------|-----------|----------|
| Runtime (VSL, OCI, network, snapshot, daemon, anticheat, archd) | 14 | ~450 | 🔴 CRITICAL |
| Kernel (interrupt, FAT32, tasking, memory, AHCI, TXFS, math) | 7 | ~230 | 🔴 CRITICAL |
| GUI (WM, desktop, startmenu, explorer, terminal, proton, gamelib, theme, notify, canvas, clipboard) | 12 | ~0 | 🟠 HIGH |
| Bear RL (NN, PPO, GAAD, Vulkan, CUDA, cuDNN, env) | 8 | ~190 | 🟠 HIGH |
| Hosted (metal, vulkan, display, DRM, GBM, Wayland, gamescope) | 6 | ~120 | 🟠 HIGH |
| Compiler (HolyC lexer, parser, codegen, PTX) | 5 | ~25 | 🟡 MEDIUM |
| Apps (editor, canvas, codec, freedoom, terminal, calc, control, pkgmgr, AUR, tracker) | 8 | ~55 | 🟡 MEDIUM |
| Audio (Furnace 12 chips, SF2, Ardour DAW, AI plugins) | 2 | ~150 | 🟡 MEDIUM |
| Container (bwrap, isolate, seccomp, namespaces) | 2 | ~100 | 🟡 MEDIUM |
| Shell (unified shell) | 1 | 0 | 🔵 LOW |
| Tools (ISO9660, screenshot, weight_check) | 3 | 0 | 🔵 LOW |
| JIT (encoder/disasm/ASMJIT/MIR/minic) | 5 | ~222 | 🔵 LOW |
| **TOTAL** | **73** | **1,562** | |
## User's Angel Coder Philosophy — Load-Bearing Workflow Rule

The user has repeatedly and emphatically stated the following principles. They are NOT preferences — they are rules for how gap-closing work is performed:

### "Be the Angel Coder" — Fix Broken Code First, Don't Plan Around It

When you find a stub, a `(void)param; return -1;`, or a function that doesn't do what its signature promises:
- **Fix it now.** Don't write a plan, a TODO, or a "for later" comment. Don't add a scaffolding layer on top. Fix the broken function body.
- **Time is irrelevant.** This is agentic AI work. "It takes minutes." Never say "this would take too long" or "let's prioritize that later." The user considers time-based excuses a form of lying. If you can do the work, do it now.
- **Maximum effort, always.** This is a software project at the scale of an operating system. Every function must do real work. "Go heavy first and you conquer more."
- **No third party if we can write it ourselves.** If you can implement it in C11, do it. There is no "third party" — only code we write or code we don't write yet.
- **Stubs are REAL_GAPs, not technical debt.** A function that returns -1 with its parameters cast to void is a bug, not a placeholder. Every stub found must be either implemented (preferred) or explicitly documented as a known limitation with a regression test asserting the current behavior.

### "Go Heavy First" — Prioritization Rule

When facing multiple gaps:
1. **Highest-leverage, highest-visibility work first.** User-facing features before internal cosmetics. Real implementations before refactoring.
2. **"Small wastes time first but is great polished and makes excellent work."** Small, focused, polished work is the end goal, but the initial approach must be heavy — implement the core functionality completely, then polish.
3. **Do not skip work by claiming it's too large.** "Time is irrelevant and it takes minutes." If a gap exists, close it.
4. **Do not lie about time scale.** "Stop lying about time scale to skip work." If you catch yourself thinking "this is too much for one session" — stop that thought. Do the work.

### Opaque Structs + Minimal Includes + C11 Only — Architectural Constraint

Every new source file must follow:
- **Opaque structs**: Forward-declare in `.h`, define fully in `.c`. Only expose factory/accessor functions publicly.
- **Minimal includes**: Headers include ONLY what they need for type declarations and function signatures. No transitive includes.
- **No god headers**: Never create a header that includes the entire subsystem. Split into per-module headers.
- **Self-contained modules**: Each `.c` includes its own `.h` first, then system headers, then direct dependencies.
- **C11 only**: No GNU extensions, no C++, no assembly in headers. Standard C11 throughout.

This applies to ALL new code. For existing code being refactored, move toward this standard with every edit.

### macOS Syscall Layer Pattern (2026-07-22) — Following VSL Design for New Subsystem

This session created a new macOS syscall layer following the VSL pattern established for Linux and NT. The pattern is reproducible for any new binary format:

1. **Numbers-only header**: `vsl_syscall_numbers_mac.h` — pure `#define` constants, ZERO includes. Defines syscall encoding (class bits + number), all known syscall numbers.
2. **Loader module**: `vsl_macho.h` / `vsl_macho.c` — validates, loads segments, resolves entry point. Independent of syscall dispatch.
3. **Dispatch module**: `vsl_syscall_mac.c` — handler functions + dispatch table. Each handler is a static `mac_sys_<name>(uint64_t a-f)` that does real work.
4. **Process integration**: `vsl_create_process_macho()` in `vsl_process.c` — loads binary via loader, sets up VSL process state with flags signaling macOS dispatch.
5. **Wire into VSL dispatch**: `vsl_syscall_dispatch()` checks `num & 0xFF000000` to route to macOS table vs Linux table.

Key differences from Linux VSL:
- macOS has THREE syscall classes (Mach traps=class0, BSD=class2, MachDep=class1) encoded in the top byte of RAX
- Mach-O binary format vs ELF
- Callback pattern for optional dependencies (test targets don't all link VSL)
- `__attribute__((weak))` symbols for fallback when VSL loader isn't linked

Full implementation detail: `references/macos-syscall-layer-2026-07-22.md`.

## Comprehensive Audit Methodology (Phase 16)

The comprehensive Triple DA audit found **915 new gaps** from full codebase scan (356 files, 111K LOC):
1. **Void cast audit**: 1,256 `(void)param;` instances → filtered for success-path only (was 505)
2. **System() call audit**: 76 `system()` calls → all REAL_GAPs (must reimplement in C) (was 34)
3. **Comment audit**: 200+ stub/TODO/placeholder/for-later comments on success paths
4. **Placeholder pattern audit**: 69 JIT/codegen/Vulkan placeholder patterns (HolyC codegen rel32, Vulkan stub blocks)
5. **Weak alias audit**: 26 `__attribute__((weak))` test stubs
5. **Empty bodies audit**: 23 empty `{}` on success paths
6. **Not implemented returns**: 13 `return -1` without work (not null guards)
7. **Architectural gaps**: Audio (0 implemented), SteamOS (95% missing), Ubuntu/Arch (80-95%), TempleOS (60-95%)

**Key audit rule**: "Rewriting from scratch in C" = REAL_GAP. If it falls under that, it IS the work.

## How to Read a Gap Entry
Example from `wubu_network.c`:
```
Line 120: if (!mgr) return -1;
Line 138: return 0;
```
## How to Read a Gap Entry
Example from `wubu_network.c`:
```
Line 120: if (!mgr) return -1;
Line 138: return 0;
```
These are **input validation** and **stub returns** — not broken features.

## Prioritization Strategy
1. **Don't fix defensive returns** — they're correct behavior (fail fast on bad input)
2. **Focus on happy-path stubs** — functions that return 0/-1 on SUCCESS path
3. **Eliminate system() calls** — every `system("...")` = REAL_GAP (must reimplement in C)
4. **Eliminate void casts on success path** — `(void)param;` as sole statement = REAL_GAP
5. **Eliminate empty bodies on success path** — `{}` or `{ return 0; }` = REAL_GAP
6. **Eliminate stub/TODO/placeholder comments on success path** — REAL_GAP
7. **Eliminate weak alias stubs** — `__attribute__((weak))` test stubs = REAL_GAP
8. **Eliminate placeholder patterns** — JIT backpatching, codegen stubs = REAL_GAP
9. **Triple DA audit** — verify each gap: is it actually called in tests? Does test pass?
10. **Test-first** — if a test exercises the code and passes, the gap is cosmetic

## How to Read a Gap Entry
Example from `wubu_proton.c`:
```c
Line 360: system("wine ...");  // REAL_GAP: must replace with fork+exec
Line 399: setenv("WINEDEBUG", "-all", 1);  // REAL_GAP: parameter used
```

These are **system() calls** and **unused parameters on success path** — REAL_GAPs to close.

## Reference Files

- `references/proton-gap-closure-patterns.md` — Before/after patterns for closing void-cast REAL_GAPs in wubu_proton.c (map_sections, exec, create_prefix)
- `references/desktop-gap-closure-patterns.md` — GAAD snap, virtual desktop patterns, HolyC terminal keys, zune theme for wm.c
- `references/netlink-mbedtls-patterns.md` — Netlink rtnetlink + mbedTLS patterns for network/OCI
- `references/nftw-filesystem-patterns.md` — nftw/unlinkat recursive filesystem operations for snapshots/images
- `references/dxvk-ini-config-patterns.md` — DXVK INI config parsing/writing patterns
- `references/mbedtls-tls-integration-2026-06-28.md` — mbedTLS TLS integration for HTTPS
- `references/nftw-filesystem-patterns-2026-06-28.md` — Extended nftw patterns
- `references/phase14-da-audit.md` — Phase 14 comprehensive audit methodology
- `references/phase16-da-audit.md` — Phase 16 full codebase scan methodology (1,562 gaps)
- `references/vsl-syscall-implementation-patterns.md` — VSL syscall implementation patterns (15 syscalls + statx fix)
- `references/cudnn-cpu-fallback-patterns.md` — CPU fallback patterns for cuBLAS/cuDNN void casts using bear_simd.h
- `references/wayland-callback-closure-patterns.md` — Wayland callback closure patterns for hosted.c (registry_global_remove, keyboard_enter/leave, keyboard_modifiers, pointer_leave/frame, pointer_axis_source/stop/discrete, keyboard_repeat_info)
- `references/syscall-bridge-closure-patterns.md` — Syscall bridge closure patterns for bridge/wubu_syscall.c (file handlers fd-based, Styx offset tracking, container fork+exec via bwrap, trampolines)
- `references/zip-mounting-patterns.md` — Real zip archive mounting patterns for explorer.c
- `references/clipboard-gap-closure-patterns.md` — Multi-MIME clipboard implementation patterns for wubu_clipboard.c (17 tests passing)
- `references/startmenu-gap-closure-patterns.md` — Dynamic .desktop parsing, category mapping, core app preservation, shutdown wiring, MIME launch integration for startmenu.c (4 tests passing)
- `references/daemon-desktop-integration-e3-2026-07-08.md` — Wire existing daemon (wubu_archd, 16/16) as Desktop service/autostart manager: module design, Desktop-lifecycle wiring, Makefile `-DWUBD_TEST_MAIN` + dep-cascade pitfalls, sandbox-safe regression test
- `references/embed-daemon-repl-in-terminal-e4-2026-07-08.md` — Embed a daemon REPL (wubu_holyd) as a PTY-backed process in a terminal tab: `--repl` TTY mode, `wubu_holyd_bin` target, `term_pty_spawn` argv extension, render/key/IO routing, `test_holyc_embed`
- `references/control-panel-gap-closure-patterns.md` — Win98-style control panel 9-tab implementation for apps/control.c (3 tests passing)
- `references/reactos-desktop-fixup-patterns.md` — Learn-from-ReactOS desktop fixup: real BMP wallpaper decode → XRGB8888, 5 ReactOS PLACEMENT modes wired to wubu_settings, dead-code purge workflow (2026-07-07, 18/18 wallpaper tests green)
## How to Read a Gap Entry
Example from `wubu_proton.c`:
```c
Line 360: system("wine ...");  // REAL_GAP: must replace with fork+exec
Line 399: setenv("WINEDEBUG", "-all", 1);  // REAL_GAP: parameter used
```

These are **system() calls** and **unused parameters on success path** — REAL_GAPs to close.

### OCI/snapshot Gap Closure Patterns (2026-06-28)

**OCI Layer Blob Copy** (`wubu_oci.c`):
```c
// BEFORE (REAL_GAP: system call)
char cmd[2048];
snprintf(cmd, sizeof(cmd), "cp '%s' '%s' 2>/dev/null", src_path, dst_path);
system(cmd);

// AFTER (real C: sendfile kernel copy)
int src_fd = open(src_path, O_RDONLY);
struct stat st; fstat(src_fd, &st);
int dst_fd = open(dst_path, O_WRONLY | O_CREAT | O_TRUNC, 0644);
off_t offset = 0;
ssize_t sent = sendfile(dst_fd, src_fd, &offset, st.st_size);
close(src_fd); close(dst_fd = close(dst_fd);
if (sent != st.st_size) unlink(dst_path);
```

**ZFS Snapshot** (`wubu_snapshot.c`):
```c
// BEFORE (REAL_GAP: system call)
char cmd[2048];
snprintf(cmd, sizeof(cmd), "zfs snapshot %s@%s 2>/dev/null", dataset, snapshot);
system(cmd);

// AFTER (real C: fork+execvp)
pid_t pid = fork();
if (pid == 0) {
    execlp("zfs", "zfs", "snapshot", dataset, snapshot, (char *)NULL);
    _exit(127);
}
waitpid(pid, &status, 0);
```

**btrfs Snapshot** (`wubu_snapshot.c`):
```c
// Real ioctl (no system call ever needed)
struct btrfs_ioctl_vol_args_v2 args = {0};
const char *src_base = basename((char *)src);
size_t name_len = strlen(src_base);
if (name_len >= BTRFS_PATH_NAME_MAX) name_len = BTRFS_PATH_NAME_MAX - 1;
memcpy(args.name, src_base, name_len);
args.name[name_len] = '\\0';
args.flags = 0;  // read-only
ioctl(fd, BTRFS_IOC_SNAP_CREATE_V2, &args);
```

### Real Zip Archive Mounting in explorer (Option C - 2026-06-28)

**Gap**: `explorer_mount_zip()` was a stub returning `false` with comment "Not implemented".

**Implementation** (`src/gui/explorer.c`):

| Component | Approach |
|-----------|----------|
| **Primary** | Try libzip via `dlopen("libzip.so.4")` — use `zip_open`, `zip_get_num_entries`, `zip_get_name`, `zip_close` |
| **Fallback** | Raw zip central directory parser using zlib structures (no headers needed) |

**Key Structures**:
```c
#pragma pack(push, 1)
typedef struct { uint32_t signature; ... } ZipCentralDirHeader;
typedef struct { uint32_t signature; ... } ZipEndCentralDir;
#pragma pack(pop)

typedef struct {
    char name[256];
    uint64_t uncompressed_size, compressed_size;
    uint32_t crc32;
    uint16_t compression_method;
    time_t modified;
    int central_dir_index;
    bool is_directory;
} ExZipEntry;
```

**Functions Added**:
| Function | Purpose |
|----------|---------|
| `ex_libzip_load()` | `dlopen` libzip.so.4 + resolve symbols |
| `ex_zip_read_central_directory(path)` | Raw parser: finds EOCD, reads CD entries, converts DOS timestamps |
| `ex_zip_populate_entries()` | Converts `ExZipEntry[]` → `ExEntry[]` for explorer UI |
| `explorer_mount_zip(path)` | Tries libzip first, falls back to raw parser |
| `explorer_unmount_zip()` | Clears cache, navigates up |

**ZIP Format Details**:
- Signatures: Local=0x04034b50, Central=0x02014b50, EOCD=0x06054b50
- EOCD search: last 64KB of file
- DOS time conversion: bits for year/month/day/hour/min/2sec
- Directory detection: trailing '/' or zero size

**Test Added** (`explorer_test.c`):
```c
bool ret = explorer_mount_zip("/tmp/test.zip");
TEST_ASSERT(ret, "mount_zip returns true for real zip");
TEST_ASSERT(explorer_is_in_zip(), "in_zip_archive is true after mount");
TEST_ASSERT(ex->entry_count > 0, "entries populated from zip");
explorer_unmount_zip();
TEST_ASSERT(!ex->in_zip_archive, "unmount_zip clears flag");
ret = explorer_mount_zip("/fake/archive.zip");
TEST_ASSERT(!ret, "mount_zip returns false for missing file");
```

**Verification**: `make test_explorer` → 74/74 pass (real zip mount/unmount)

### Option C Feature Complete — All Items Done

| Item | Status | Location |
|------|--------|----------|
| **libzip integration** (zip mount) | ✅ Complete | `explorer.c` |
| **PTY + ANSI parser** (terminal) | ✅ Already complete | `term.c` |
| **.desktop parser** (start menu) | ✅ Already complete | `wubu_mime.c` (scans XDG dirs) |
| **Notification history + actions** | ✅ Already complete | `wubu_notify.c` |

**Verification**: `make test` (and the isolation-specific targets) must pass. Run for the live target/assertion count; do not cite a fixed total.

## Verification Commands
```bash
cd /home/wubu/wubuos

# Core test suites (all passing as of 2026-07-03)
make test_clipboard      # 17/17 pass
make test_wm      # 16/16 pass
make test_explorer # 74/74 pass
make test_startmenu # 4/4 pass
make test_vsl            # 62/62 pass
make test_syscall        # 5/5 pass
make test_styxfs         # 11/11 pass
make test_memory         # all pass
make test_gaad           # 17/17 pass
make test_audio          # all pass
make test_holyc          # 76/76 pass
make test_metal          # all pass
make test_apps2          # 16/16 pass
make test_high_gui       # WM, desktop, startmenu, explorer, terminal, clipboard

# Check if a specific file's functions are tested
grep -r "wubu_proton" src/runtime/*_test.c

# Run related tests to verify functionality
make test_proton         # 32/32 pass (15 REAL_GAPs remain)
make test_proton2        # 14/14 pass
make test_snapshot       # 132/132 pass
make test_oci            # 10/10 pass
make test_network        # 139/139 pass
make test_vsl            # 62/62 pass
make test_holyd          # 31/30 pass
make test_wm      # 16/16 pass
make test_startmenu # 4/4 pass
make test_explorer  # 74/74 pass
make test_term    # 4/4 pass
make all                 # Full build verification
```

### Session 2026-07-04: Orientation & Gap Count Precision

**Context**: User requested "continue from last session and get oriented — it was a dumb model moment"

**Key Learning — DA Gap Count Precision**:
- Old BATTLESHIP.md said "runtime/wubu_vsl.c — 347 void casts" (monolithic file before VSL modular split)
- After VSL modular split into 9 files (`src/runtime/vsl/`), the actual syscall handlers are in `vsl_syscall.c` with **173 void casts**
- Most are legitimate unused params on happy paths (handlers take 6 args but use 1-2 for actual work)
- The 347 count included void casts in helper functions and wrapper layers
- **Verification**: `grep -c "\(void\)" src/runtime/vsl/vsl_syscall.c` → 173

**Wayland Callback Completion** (Critical Tier Priority #4 — COMPLETE):
- All ~30 remaining Wayland void casts in `hosted.c` implemented:
  - **xdg_popup listener**: `configure`, `popup_done`, `repositioned` callbacks
  - **xdg_toplevel**: `configure_bounds` and `wm_capabilities` handlers
  - **wl_data_device DnD**: Full drag-and-drop callbacks with clipboard integration
  - **wl_touch**: Frame/cancel proper handling with seat capabilities
  - **Seat capabilities**: Touch listener enabled when `WL_SEAT_CAPABILITY_TOUCH` advertised
  - **wl_output**: `geometry`, `mode`, `done`, `scale` events
  - **Tablet manager**: Stubbed with logging (stable headers not in system)

**DnD Integration with Clipboard** (via `wubu_clipboard.c`):
- New API: `wubu_clipboard_handle_dnd_enter/leave/motion/drop()`
- Updated `ClipboardDnDCallback` signature: `(bool entered, int x, int y)`
- Wayland callbacks in hosted.c now call clipboard DnD handlers for full integration

**State Additions** (`hosted_state_t`):
- Popup: `popup_x`, `popup_y`, `popup_width`, `popup_height`, `popup_mapped`
- DnD: `dnd_offer`, `dnd_x`, `dnd_y`
- Toplevel: `max_width`, `max_height`, `wm_caps`
- Touch device: `touch` pointer

**Wayland State Additions** (`wayland_state_t`):
- `tablet_manager`, `output`, `touch`, `data_device`

**Pitfalls Encountered & Fixes**:
- `zwp_tablet_manager_v1_interface` missing: System headers lack tablet protocol — skip binding with comment, keep stub handlers
- `wl_data_device_manager_listener` missing: System headers lack listener type — remove listener registration, use runtime binding
- `xdg_popup_listener` member names: `.done` → `.popup_done` (per wayland-scanner generated header)
- Forward declaration needed: `seat_capabilities` must be declared before `wl_seat_listener` because `touch_listener` is defined later
- `wl_output`/`wl_touch` destroy: Add cleanup in `hosted_shutdown()` for new Wayland objects
- Tablet manager destroy: Remove `zwp_tablet_manager_v1_destroy()` call (protocol not available)

**Test Results**: `make test`, `make test_vsl`, `make test_high_gui` must pass. Run them for live status; assertion totals grow as suites land — do not cite a fixed count.

**Updated Gap Totals** (v21 — 2026-07-07 re-audit):
- Foundation + Campaign streams CLOSED (~684 gaps) — see `vault/ACCOMPLISHMENTS_2026-07-07.md`.
- Re-measured sprint board: **~400 form≠function REAL_GAPs** (filtered defensive + ABI).
- 5 parity epics tracked separately as marathons.
- **Test gate green** — run `make test` for the live target/assertion count.

**All Tests Verified Green**:
```bash
make test_vsl       # 52/52 PASS  (NOTE: vsl count varies; trust `make test` green)
make test_high_gui  # WM, desktop, startmenu, explorer, terminal, clipboard, wallpaper ✅
make test           # run for the live target/assertion count — all tiers green = the gate
```