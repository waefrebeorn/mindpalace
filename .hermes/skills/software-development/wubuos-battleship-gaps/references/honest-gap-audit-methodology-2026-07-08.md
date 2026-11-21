# Honest Gap-Audit Methodology (v22 — 2026-07-08)

## Why this exists
The canonical WuBuOS gap-scanner (`find_real_gaps.py`) was **broken for weeks**
and produced a fictional board. The 2026-07-08 re-audit established a reproducible
three-probe method that every future session must use instead of trusting a handoff
count or a stale BATTLESHIP number.

## The three probes (run in order)
```bash
cd /home/wubu/.hermes/profiles/mind-palace/home/myseed

# Probe 1 — baseline stub class (empty bodies + const-only-no-syscall)
python3 ~/.hermes/profiles/mind-palace/skills/software-development/wubuos-battleship-gaps/scripts/find_real_gaps.py src
#   EXPECT: EMPTY {} bodies: 0   CONST-ONLY no-syscall: 0
#   If >0, the board DRIFTED — re-audit before reporting.

# Probe 2 — live system() calls (REAL_GAP by rule; must become fork+exec)
grep -rEn '\bsystem\s*\(' src --include='*.c' | grep -vE '_test\.c|test_'
#   Then MANUALLY exclude "replaces system()" / "no system()" COMMENT lines.
#   Live invocations only. (2026-07-08: 10 live sites.)

# Probe 3 — stub-phrase marker grep, then triage
grep -rEni 'stub|not implemented|placeholder|for later' src --include='*.c' | grep -vE '_test'
#   Triage OUT: VSL 6-register ABI void casts, JIT rel32 backpatch slots
#   (emit_dword(e,0) resolved at runtime), #else hardware-absent stubs
#   (wubu_metal audio/X11), "replaces system()" closure comments, and the
#   intentional wubu_wayland_stub.c / apps/*/*_stub.c linkage shims.
```
A combined runner: `scripts/honest_gap_audit.py [WUBUOS_ROOT]`.

## The honest ~400 (user reclassification rule)
> "Rewriting from scratch in C is the point of the project. Anything that falls
> under that is reclassified as work REAL_GAP. This also goes for ReactOS gaps to
> WuBuOS."

- **~40 code-level** = 10 live `system()` + ~26-32 triaged stub-phrase funcs
  (range 36-42 — report the RANGE, not a fake-precise single number).
- **~370 parity marathons** = ReactOS NT **297** (syscalls mapped in
  `vsl_syscall_list.h`, 0 transliterated — `src/runtime/vsl/vsl_nt_bridge.h:376`
  `#define VSL_NT_MAP_STUB 0x08`) + SteamOS ~30 + Ubuntu/Arch ~20 + TempleOS ~15
  + ZealOS ~8. Each missing subsystem = a "rewrite in C from scratch" marathon.

## Scanner-A false-positive trap
The extended "real-work-but-hardcoded-return" scanner emits ~76 candidates but
**every one sampled is a false positive** (real work + `return 0` success). The
word "stub" in a comment + the live-`system()` grep are the only high-signal
finders. Always read the candidate body.

## The scanner bug that caused the fiction (so it never recurs)
`find_real_gaps.py` had:
1. A `SyntaxError`: `"EPERM" not r` should be `"EPERM" not in r` — made it crash.
2. No vendored-dir exclusion — it swept `reference/` (libsndfile/portaudio/flac),
   `reactos-study/`, `wubucontainer/` for **2329 false-positive** const-only returns.
Fixed 2026-07-08: `not in r` + a `VENDOR_DIRS` tuple (reference/, vendor/, extern/,
reactos-study/, wubucontainer/, venv_viz/, dist/, wiki/, os-studies/). Re-run on `src/`
→ 0. **Lesson: a broken audit tool invisibly manufactures a fake board. Trust the
scanner only after you've seen it print 0 on a known-good tree.**

## Triple-DA plumber deep-dive recipe (1:1 parity)
When auditing a parity target (SteamOS/Ubuntu/Arch/TempleOS/ZealOS), do not count
void casts. Instead:
1. State what the target OS actually DOES (boot → service manager → app launch flow).
2. State what WuBuOS has (read the daemon/test files; the daemons exist and are
   tested — Arch daemon 16/16, TempleOS DOS daemon 31/31).
3. Locate the INTEGRATION gap: the daemon is NOT wired as the Desktop's
   service/launcher/REPL backend. That integration layer is the missing 1:1 parity.
   (e.g. `wubu_archd` is a package backend only; terminal has a
   `[Container Session - Not Implemented]` branch at `term.c:642`.)

## Verification gate (run before declaring victory)
```bash
make runtime && make hosted && make test   # gate green; 64 targets / 747+ assertions
```
If `find_real_gaps.py src` reports >0 empty bodies, or the live `system()` count
rises, the board drifted — re-audit before reporting.

> NOTE: `scripts/honest_gap_audit.py` was written but NOT executed at authoring time
> (review-turn tool restriction). Its regex/triage mirror the empirically-verified
> 2026-07-08 counts; re-run it once in a normal turn to confirm output matches.
