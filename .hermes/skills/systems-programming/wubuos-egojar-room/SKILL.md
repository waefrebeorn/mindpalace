---
name: wubuos-egojar-room
description: Use when POSIX includes are scattered and wubunos is coming.
---

# The egojar room

WuBuOS builds with gcc today and must build with **wubunos** tomorrow. The
blocker is never logic -- it is hundreds of `#include <unistd.h>` lines and
`-D_POSIX_C_SOURCE` flags scattered across the makefiles.

The fix is an **egojar room**: a small set of headers that carry every
feature-test macro and every POSIX/Linux/libc-extension include. Nothing else.
No declarations, no code, no `static inline`. Standard C (`<stdio.h>`,
`<string.h>`, `<stdint.h>`) does NOT belong in a jar -- any compiler has it.

## The shelves

| shelf | carries |
|---|---|
| `src/egojar.h` | core: files, processes, threads, memory, signals, mounts, inotify, epoll, feature-test macros |
| `src/egojar_net.h` | sockets, addresses, net devices |

**One god-jar does not work.** `<sys/socket.h>` drags in `<net/if.h>`,
which redefines `struct ifreq` / `ifmap` / `IFF_*` and collides with
`<linux/if.h>` -- and half the tree legitimately includes `<linux/if.h>`.
Split by concern so a file pays only for what it uses.

## When to Use

- POSIX or Linux includes are scattered across many files.
- The tree must compile under a different compiler (wubunos).
- A makefile carries dozens of `-D_POSIX_C_SOURCE` / `-D_GNU_SOURCE` flags.

## Rules

1. **Include the jar FIRST.** Feature-test macros only take effect before the
   first system header. A jar included after `<time.h>` is already too late.
2. **A header whose struct crosses a TU boundary must include the jar**, or
   callers see different macros and compute different layouts. This silently
   segfaults: `wubu_clipboard_internal.h` defined `ClipboardState`; the library
   TU had the jar, the test TU did not, and the test read a garbage pointer out
   of a global. Fix the header, not the caller.
3. **Name clashes are renamed, not shimmed.** The project's `shutdown()`
   collided with socket `shutdown()` once the jar made `<sys/socket.h>`
   visible. Renamed the project's function to `wubu_shutdown()` -- definition,
   declaration, every caller -- and verified no bare `shutdown(` remained.
   The socket keeps its meaning; the OS name now says what it is.
4. **Deleting the makefile flags is gated on the FULL GATE, not on the build.**
   A tree can compile cleanly with zero `-D_POSIX_C_SOURCE` flags and still
   segfault lean test binaries: each test recipe is its own TU set, and any TU
   that reaches a POSIX symbol through a header without the jar gets a
   different feature surface than its sibling -- a different struct layout or
   an implicit declaration that truncates a pointer. Observed class: removing
   the flags broke `test_holyc` / `test_wet*` / `test_tutorial` at runtime
   while `make hosted` stayed green. Rule: remove the flags only after the
   FULL `make -k -j24 test` is green WITHOUT them; if a red appears, restore
   the flags and fix the TU that needed the macro, then retry. Never leave the
   flags removed on the strength of a successful build.
5. **A jar shelf that pulls ALSA or PulseAudio needs a feature macro of its
   own.** `<alsa/asoundlib.h>` redefines `struct timeval` / `struct timespec`
   unless a POSIX feature macro is in effect, and Pulse's headers pull in
   `<time.h>` first -- the two collide as `redefinition of 'struct timeval'`.
   Defining `_POSIX_C_SOURCE 200809L` at the very top of the file, BEFORE any
   system header, settles it. This is exactly the scattered-flag practice the
   jar exists to end, so if the shelf must carry it, the jar is the right home
   for it -- not the module.

## Sweeping a tree

1. Count first: `grep -rc` the POSIX headers, sort by file.
2. Convert in bulk: strip the POSIX includes, insert the jar as the first
   include. Compute the relative path per file depth.
3. Add headers until the gate is green -- each round reveals the next missing
   one (`sys/epoll.h`, `sys/utsname.h`, `sys/sysinfo.h`, ...).
4. Re-run the FULL gate after every batch. Never trust a single target.
5. Remove the flags by deleting ONLY the flag token plus ONE following space,
   with a regex like `-D\s*_POSIX_C_SOURCE=\S+ ?`. NEVER collapse whitespace
   (`re.sub(r'[ \t]+', ' ', s)`) -- that eats the recipe tabs and every target
   breaks with `missing separator`. Keep a backup of each `mk/*.mk` first; the
   first attempt at this has destroyed a makefile.

## Do not sweep submodules

Submodules are separate repos. A bulk rewrite dirties them, and they often
already hold uncommitted work. If it happens, revert ONLY the files where your
change is the entire diff -- compare `git diff` per file and `git checkout --`
those, leaving everything else alone.

## The goal

The seam becomes N headers wide. When wubunos is the compiler, those headers
are what change; the other ~5,000 files keep compiling untouched.
