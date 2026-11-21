---
name: wubu-slerm-workflow
description: Use when slerming an external project into own C11.
version: 1.0.0
author: WaefreBeorn
license: Waefrebeorn Umbrella License v3.0
metadata:
  hermes:
    tags: [slerm, c11, port, reimplementation, attribution]
    related_skills: [wubu-github-ecosystem, wubuos-test-suite]
---

# Slerming an external project into own C11

## What a slerm is

A **slerm** is a ground-up reimplementation of someone else's work as your
own. A fork or a patch is NOT a slerm. The user's term, from the `slermes`
project README: rewrite it from scratch, in your own idiom, until the result
is yours -- while still crediting where the design came from.

Own work is C11, self-contained, zero third-party unless explicitly adopted
as a backbone. Third-party imports are marked in the README, never passed off.

## When to Use

- The user names an external repo and says they want it slermed.
- An external project is the inspiration for a module you must build yourself.
- A port/reimplementation of any non-C11 codebase (Rust, TS, C++, Python) into
  the WuBuOS C11 tree.

## Procedure

1. **Read the source before writing anything.** Clone it, then read the CORE
   module -- the one that actually produces the output -- before any wrapper,
   UI, or binding. For an engine that is the render/step function and the
   state struct it mutates. Note the exact operation order: a port that
   reassociates float math silently changes the output.
2. **Port the math helpers first, header-only.** Deterministic math, PRNG,
   smoothing, clamping. These are pure, testable, and everything else depends
   on them. Reproduce the source's semantics exactly -- including its
   JavaScript/quirk helpers (`js_min`/`js_max` NaN propagation,
   `Math.round` halves-up) if the original had them, because callers depend on
   the quirk.
3. **Port one concern per file.** Source (oscillator/glottis) -> tract/network
   -> voice/engine. Never a `port.c` monolith. Match the tree's
   `_name.c` + public `.h` + `_internal.h` shape.
4. **Expose what the gate needs.** A helper that is `static` in the original
   often has to become non-static so a behavior test can drive it. Prefer a
   public function with a clear name over a test-only backdoor.
5. **Gate with real behavior, not assertions on internals.** Drive the model
   with real inputs and check physical/contractual bounds: output is bounded,
   a gate opens under the right condition and closes without it, a cycle count
   matches the frequency. "It did not crash" is not a gate.
6. **Wire it into the product, then into the build.** A port that nothing calls
   is a museum piece. Find the product's real entry point and call it there.
7. **Commit in coherent batches** and keep the attribution with the code.

## Slerming a giant upstream (QEMU-class scope decision)

When the upstream is enormous (emulator, kernel, browser), slerm its ROLE,
not its line count: build a behavior-gated BACKBONE of the subset the
mission needs, and roadmap the rest in the README. Rules that made the
WEMU slerm land in one session:
- **Found it on a real gap you own.** The first implemented features should
  be the ones whose absence actually bit you (e.g. the exact instructions
  that faulted your CI). The founding story is the scope argument.
- **Gate differentially against an independent model** — native execution
  of the same bytes, or an independent C implementation of the semantics.
  Then EXPAND the gate (more ops, widths, flag combinations, carry-in)
  until it catches real bugs: a differential gate that only covers what you
  remembered to implement is survivorship bias, and the expansion is where
  the missing instructions surface.
- **Adopt the upstream project's OWN testing standard as the acceptance
  bar.** Research its testing docs before declaring the backbone done
  (QEMU's own guidance: static busybox for smoke, LTP for syscall
  coverage). Hand-picked toy gates prove mechanism, not mission.
- **Honesty surfaces are part of the subset**: an emulator must claim
  (CPUID/feature probes) exactly what it executes and implement the
  enablement chain, or guests never use the features you built. Unimplemented
  = honest fault, never a fake success.
- Clean-room provenance section as always: behaviour/design inspired by the
  upstream, semantics from the official manuals, zero upstream code.

## Pitfalls

- **Check which branch holds the code before you build.** A repo's default
  branch can be an emptied stub while the real project lives on another
  branch. `git ls-remote --heads` then `git ls-tree -r --name-only
  origin/<branch> | wc -l`. Building on the stub branch produces confident
  work attached to nothing.
- **License the derived work, and keep the boundary explicit.** A port of a
  GPL program is a derived work and carries that license. Put it on an
  archive branch with an `ATTRIBUTION.md` naming the upstream, its license,
  and the commit it came from -- do NOT mix it into a mainline under a
  different license. A published scientific model (e.g. a classic speech
  model) is not copyrighted code; say so rather than inventing a license.
- **Do not trust your memory of the original's constants.** Read them out of
  the source at port time. Off-by-a-factor errors (a shape function peaking at
  the wrong phase, a threshold in the wrong units) pass a compile and fail
  only by ear or by a bound check.
- **A port's first gate will fail on a wrong mental model, not a typo.** When
  a bound check fails, re-read the original's math before "fixing" your C.
  The recurring categories, each of which has cost a port a wrong "fix":
  - **winding / handedness** -- an inside/outside or left/right test depends
    on which way the original winds its polygon; match its convention and
    state yours in the gate.
  - **ordering** -- results come back in the original's traversal order, not
    sorted; compare as a set.
  - **interpolation vs approximation** -- an interpolating spline (Catmull-Rom)
    overshoots its control polygon; an approximating one (Bezier) does not.
    "Stays inside the control polygon" is only a valid check for the latter.
  - **angle conventions** -- read the quadrant and the reference axis off the
    source; do not assume "up" means pi/2.
- **Graphics ports: gate the sample grid and the rounding, not just the shape.**
  Two real catches from the impossible-os gfx slerm (wubuos src/gui/gfx):
  (1) supersampled AA coverage must sample at pixel_origin + {1,3,5,7}/8, NOT
  pixel_center + offset — double-counting the half-pixel breaks mirror
  symmetry, and a symmetry assertion over both axes catches it instantly;
  (2) integer box blur truncates, so an energy-conservation gate must assert
  a rounding bound (<=1 lost per touched pixel per pass), not exact equality.
  Write the symmetry/invariant checks first; they find the port's mental-model
  bugs before any screenshot does.
- **Deleted code is usually in history.** If the upstream work was removed
  before you started, `git log --all --oneline -- <path>` and
  `git checkout <commit> -- <path>` restore it. Check before rewriting.
- **An external project's build may be clang-only.** A C11 tree that builds
  with clang can fail under gcc on macOS-only headers, missing `M_PI` (needs
  a feature macro or `-std=gnu11`), and bare `bool` without `<stdbool.h>`.
  Fix the portability gaps in the source, not the build flags.

## References

- `references/c11-port-order.md` -- the concrete module order, what to expose,
  and the bound-check shapes that catch a wrong mental model.
