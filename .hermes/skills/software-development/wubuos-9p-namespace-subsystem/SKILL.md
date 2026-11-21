---
name: wubuos-9p-namespace-subsystem
description: "Use when adding a /n/* 9P subsystem to WuBuOS."
tags: [wubunos, styx, 9p, namespace, gui, runtime]
version: 1.0.0
author: wubu
license: MIT
metadata:
  hermes:
    tags: [wubunos, styx, 9p, namespace, gui, runtime]
    related_skills: [wubunos-hosted-capture-bridge, wubuos-build-recovery, wubuos-test-suite]
---

# Adding a WuBuOS `/n/*` 9P Namespace Subsystem

## When to Use
- Exposing a new kernel/Brain/companion resource as `/n/<name>/*` files.
- A render/GUI layer must push state into the namespace without a hard link
  dependency on the namespace bridge.
- Adding a persistent store behind a `/n` file that needs capability gating.

This is the recurring meta-layer move: a resource becomes a Styx/9P file,
introspectable from the shell (`cat /n/<name>/*`), gated by a capability.

## The pattern (copy `wubu_ns_dram.c` / `wubu_ns_kernel.c`)
A namespace subsystem is one `.c`+`.h` in `src/runtime/` named
`wubu_ns_<name>.c`. It:
1. Includes `wubu_ns_bridge.h`, `wubu_ns_bridge_internal.h` (which declares
   `g_ns_root`, `ns_mkdir`, `ns_write`), and its own header.
2. Renders its files from the LIVE subsystem state on every sync. **Prefer this
   over keeping a private mirror** in file-static variables: a mirror is a
   second copy that can disagree with its source, and a refresh that re-reads
   the live state cannot go stale. Keep a mirror ONLY when the source exposes
   no readable accessor (then the setters push into it and the sync writes it).
3. Exposes a `wubu_ns_<name>_sync()` (or `publish_*`) that calls
   `ns_mkdir("<name>")` then `ns_write("<name>/<file>", buf)` for each file.
   `ns_write` takes a RELATIVE sub-path (it prefixes `g_ns_root`).
4. Exposes setters (`wubu_ns_<name>_set_*`) the live subsystem pushes into
   each tick, plus getters that read the mirror back (only when you kept one).

**Keep it dependency-light.** Link ONLY `wubu_ns_fs.o` (the FS core that
provides `g_ns_root`/`ns_mkdir`/`ns_write`) — NOT the real subsystem renderer.
The namespace module owns its own mirror; the renderer pushes state in via
setters. Same discipline as `wubu_ns_dram` linking only `wubu_dram_hedge`,
not the DRAM controller. This keeps the standalone test small.

## A namespace control path is not a backdoor around a gate

A `/n` file that CHANGES state must call the SAME validated API the in-process
path calls — not a lower-level one. If a subsystem gates an operation (a schema
handshake, a capability check, a contract version), a namespace setter that
reaches past that gate to a bare `select`/`set`/`enable` turns the namespace
into a backdoor: an operator (or any agent that can write the file) gets the
privilege without the check. Same class as the AD01 rule below.

Test it: assert the namespace path REFUSES the same inputs the in-process path
refuses. A control path with no negative test is an unverified gate.

## `ns_write`/`ns_mkdir` take RELATIVE paths
`ns_write("bonzi/enabled", "1\n")` writes `<g_ns_root>/bonzi/enabled`.
Do NOT pass `g_ns_root`-absolute paths to these helpers — they prefix it
again. `g_ns_root` is set once by `wubu_ns_bridge_create(ns_root)`.

## `ns_write` does NOT create parent directories
`ns_write("sub", buf)` only writes the leaf file — it does not `mkdir` the
path leading to it. When a subsystem exposes per-item files under a nested
path (`experts/layer/<L>`, `hive/cell/<id>`, `kv/<layer>/<slot>`), call
`ns_mkdir` for EVERY intermediate directory before writing: the top
`ns_mkdir("experts")` does not create `experts/layer`. A missing parent
makes `ns_write` return -1 (its `fopen(path,"w")` fails) and the sync
returns -1 — the files simply never appear, with no other symptom. Mirror
the directory tree with one `ns_mkdir` per level.

## Someone must CALL the publisher, at boot
A publish/sync function with no caller is dead code: the subtree simply never
exists, and every consumer that mounts it sees nothing. Before believing a
`/n/<name>/` exists, grep the tree for the call:
```bash
grep -rn "wubu_ns_<name>_publish\|wubu_ns_<name>_sync" --include=*.c src/ | grep -v test
```
Wire the call where the namespace root is already set up (the boot path that
publishes the other subtrees), not in the module's own init — the root does
not exist yet there.

## The on-disk root is `$HOME/.wubu/n`
`g_ns_root` is a real directory tree, so `/n/<name>/<file>` is
`$HOME/.wubu/n/<name>/<file>` on disk. Checking `~/.wubu/<name>/` instead
reports "no such file" and sends you chasing a bug that is not there. A test
can point `g_ns_root` anywhere; the product uses the home-relative path.

## A path that must have children has to be a DIRECTORY
If the design puts per-item files under a path (`kv/world/tick_<N>`,
`experts/layer/<L>`), that path must be created with `ns_mkdir` — a flat
`ns_write("kv/world", ...)` file there silently blocks every child: the
writes fail with no other symptom and the items never appear. When a subtree
looks empty, check whether its parent is a file where a directory was meant.

## Guard the FS-core dependency in the test recipe
A standalone `test_ns_<name>` recipe compiles the test `.c` + the module
`.c` + links `$(RT)/wubu_ns_fs.o`. The compile line needs
`-I$(RT)` because `wubu_gnu_compat.h` lives in `src/runtime/` and the
`-include wubu_gnu_compat.h` flag is processed before other `-I` paths on
some gcc versions — a brain/other-tree `.c` added to the recipe needs
`-I$(RT)` too or it dies with `fatal error: wubu_gnu_compat.h: No such
file or directory`.

### A runtime module operating on a Brain-tree type: define the struct ONCE
When a `/n` module (in `src/runtime/`) manipulates a type defined in the
Brain tree (e.g. `wubu_agentic_mem_t` in `src/brain/include/wubu_vecsearch.h`),
put the exact struct layout in the MODULE's OWN header and include only that
header in the `.c`. Including BOTH the module header and the Brain header
yields `conflicting types for 'wubu_...'` even when the field lists are
identical — they are distinct type identities. The module's header
forward-declares the layout it needs; the `.c` never includes the Brain
header. Add the brain path vars to `mk/vars.mk`
(`BRAIN_INC = src/brain/include`, `BRAIN_SRC = src/brain/src`) and give
every `.c` in the recipe `-I$(RT) -I$(BRAIN_INC) -I$(BRAIN_SRC)`.

## Decouple GUI→namespace with WEAK symbols (do not edit a dozen link lines)
When a render/GUI loop (`wm_render.c`) must push state into a
namespace module that only SOME link lines carry, do NOT add the object to
every `wm_render.c` link line. Declare weak no-op defaults in the
render file; the real module `.o` overrides them at link time when present:
```c
__attribute__((weak)) void wubu_ns_<name>_set_pos(int x,int y){(void)x;(void)y;}
__attribute__((weak)) int  wubu_ns_<name>_sync(void){return -1;}
```
The sync function is already a safe no-op (`-1`) when `g_ns_root` is unset,
so the GUI renders whether or not the bridge is linked. This is the correct
coupling: the GUI never *requires* the namespace bridge to render. The
shipped build adds the module to `RT_OBJS` in `mk/objects.mk`; the weak
defs make test/capture link lines that omit it still link.

### Past ~3 weak symbols in one file, extract ONE observer — stop bolting
Weak no-ops are the right decoupling for ONE or TWO calls a render/GUI loop
makes into an optional module. They are the WRONG tool once the loop pushes
several related pieces of state (a `/n` mirror + an ambient-context module +
an activity state = 6-11 setters). At that point the render file carries a
wall of `__attribute__((weak))` one-liners plus a multi-call inline block,
and the GUI renderer now knows about `/n`, context modules, and activity
enums — knowledge that does not belong in a renderer.

When you reach the THIRD weak symbol for the same subsystem, STOP and
extract ONE observer function in the subsystem's own module:
```c
/* wubu_<sub>_observe.c -- reads live state, pushes to the meta-layer */
void wubu_<sub>_observe(void) { /* every setter call lives here */ }
```
The render file then has ONE include, ONE weak no-op (`wubu_<sub>_observe`),
and ONE call per frame. The real observer `.o` (linked in the shipped build)
drives every consumer; test/capture builds get the single no-op. The
GUI→namespace coupling stays at exactly one seam no matter how many
consumers grow behind it. Symptom you waited too long:
`grep -c '__attribute__((weak))' <render>.c` returns double digits. This is
the dejank anti-pattern — collapse it before adding the next consumer.

### A weak no-op must match the real prototype EXACTLY (enum types included)
When the render file `#include`s the real header, the weak no-op's signature
must be byte-identical to the declared prototype — including enum parameter
types. Declaring `__attribute__((weak)) const char *f(int a){...}` when the
header declares `const char *f(wubu_activity_t a)` fails with
`conflicting types for 'f'` because the enum and `int` are distinct types.
Use the header's exact type in the weak def (the enum name is in scope once
the header is included). If matching the type is awkward, the cleaner fix is
to NOT declare the weak no-op and instead add the module `.o` to the test
link line — but never leave a signature-mismatched weak def.

## The apps test stubs the GUI subsystem it doesn't link
`test_apps` links stub engines, not the real ones. If the render loop
newly calls a getter (`wubu_bonzi_x/y/w/h`, etc.) that the stub file lacks,
the apps test goes `undefined reference`. Add the missing getter stubs to
`src/apps/apps_test.c` (e.g. `int wubu_bonzi_x(void){return 0;}`) —
NOT to the Makefile.

## Two roots exist -- do not confuse them

WuBuOS has TWO on-disk roots and they are NOT the same place:

| Root | Default | Owns |
|---|---|---|
| `/n/*` namespace bridge (`g_ns_root`) | `$HOME/.wubu/n` | virtual files rendered by sync/publish (`wubu_ns_<name>_sync`) |
| Hosted Styx path mapping (`WUBU_GUEST_ROOT`) | `~/.local/share/wubu/guest` | where guest `"/"` lands when no 9P server is mounted (`styxfs_path_to_host` / `wubu_guest_root()`) |

A `/n/<name>/` subtree that looks empty is a PUBLISH problem (no caller), never a
missing directory. A guest `"/"` that shows the wrong contents is a MAPPING
problem. Confirm which root you are looking at before theorising.

## No app may address a HOST path

The user's standing objection is "you have linux reference for even more wrong
things": any location derived from `$HOME`, `$XDG_*`, or a bare host directory
means the guest shows the HOST operating system's files. On the hosted port the
following were each fixed for exactly this reason -- do not reintroduce them:

- File Manager started at `getenv("HOME")` and browsed the real Linux home.
- The Desktop directory preferred `$XDG_DESKTOP_DIR`, then `$HOME/Desktop`; New
  Folder / Shortcut / Text Document wrote into the host home.
- Both now resolve under `WUBU_GUEST_ROOT` (`WUBU_DESKTOP_DIR` /
  `WUBU_GUEST_ROOT` overrides).

Rule: a shell/app location is either an explicit `WUBU_*` override or a path
inside the guest sandbox. `$HOME` may be used to BUILD a default, never as the
location itself.

## Unify stores by canonicalising at EVERY public entry point

When two modules address one store with different spellings (a writer storing
BARE names like `Documents/report.txt`, a reader building SLASHED paths like
`/Documents/report.txt`), normalising in ONE place is not enough. Canonicalising
only the write made saves invisible to every reader using the other spelling --
the test caught it as a segfault inside `strcmp()` because a load returned zero
lines.

Normalise the key in EVERY public accessor: read, write, delete, exists, stat,
is_dir, mkdir, rmdir, rename, children. One canonical form at the boundary; a
single helper (`guest_norm_key`-style) that all of them call, so the next accessor
cannot forget. Verify with a test that writes through one spelling and reads
through the other.

Related traps in the same area:

- **Directory enumeration depth**: match DIRECT children only, on the canonical
  parent prefix. Comparing raw strings makes both the root listing and folder
  descent silently empty.
- **Collect names before deleting** in a recursive walk -- removing while
  enumerating shifts entries under the walk and leaves half the tree behind.
- **A reader with no size-query form**: if `read(name, NULL, 0, &len)` refuses a
  NULL buffer, get the length from `stat()` and verify the read returned exactly
  that many bytes. Otherwise copies silently produce empty files.

## A writer's fallback can hide a missing caller argument

`wm_write_desktop_shortcut(name, exec)` accepted NULL and substituted
`"wubu-app <name>"`, so a dialog that only asked for a NAME produced shortcuts
that looked created and could never launch. A fallback for a REQUIRED parameter
is a way for a caller bug to look like success.

Make the fallback impossible: require the argument, or make the failure loud.
When a caller passes NULL to a function whose output is user-visible, treat it as
a UI gap to close (the dialog must collect the field), not something the callee
should paper over.

## Tests ENCODE the old convention -- grep them before you change a path

Removing a host reference breaks tests that set the old variable. `test_wm` set
`XDG_DESKTOP_DIR` ten times; moving the Desktop into the guest sandbox failed nine
checks. The honest fix was to change the TESTS to `WUBU_DESKTOP_DIR` and rename
the labels -- they were asserting the Linux reference being removed. Do NOT keep
a backwards-compatible read of the old variable just to keep a test green: that
leaves the host path reachable.

Before changing any location/env var, run:
`grep -rn '<OLD_NAME>' src/ --include=*.c --include=*.h` and expect hits in test
files. Budget for updating them in the same commit.

## Persistent store behind a namespace file: gate with AD01
When the namespace file backs a persistent store (companion memory, etc.),
gate every read/write with `wubu_9p_cap_allowed(caller_subtree, path)`
(the AD01 capability check: path must be under the caller's subtree). The
subsystem owns its subtree; an unrelated agent is refused. In a standalone
test, `mkdir` a temp dir, call the module's `set_subtree(tmpdir)`, and pass
that dir as the caller subtree — do NOT use a literal `/n/<name>` path,
because `/n` is the ns-bridge root (set via `g_ns_root`), not a writable
filesystem path outside the harness, and `fopen` to it returns NULL →
segfault. A store save/load must NULL-check `fopen` before any `fwrite`;
an AD01-gated path whose `fopen` returns NULL must return -1, never
segfault on the FILE*.

## A test writing a persistent store: mkdir the temp dir, gate on a REAL path
A persistent-store test (`test_*_mem`) writes a file, so it must (1) `mkdir`
its temp directory with `<sys/stat.h>`'s `mkdir(path,0755)` before the first
save, (2) call the module's `set_subtree(tmpdir)` so the AD01 gate passes,
and (3) pass that same tmpdir as the `caller_subtree` argument to both save
and load. Passing a subtree the path is not under (or omitting the mkdir)
makes the AD01 check refuse every call — every assertion fails at once.
`rmdir` the temp dir at the end. Keep the store format self-describing
(magic + dims + counts) so a corrupt/wrong-magic file is rejected on load.

## Per-item / subtree files: the `<name>/<item>/<leaf>` recipe
A subsystem that exposes many items (`/n/experts/layer/<L>`,
`/n/hive/cell/<id>`, `/n/kv/<layer>/<slot>`) follows one shape: a setter
per item that fills a mirror slot, and a sync that loops the items writing
one file each under a pre-`ns_mkdir`'d subdir. Build multi-line bodies
(one line per sub-item) in a single buffer with a running offset, bounding
each `snprintf` so it can't overrun. See
`references/subtree-files.md` for the worked recipe and buffer bounds.

## Directory `Rread` pages by BYTE offset, from ONE entry list
`offset` in a 9P directory read is a byte offset into the directory stream, not
an entry index; a client advances by `nread`. Two failure modes follow from
getting this wrong, and both look like "it almost works":

- Enumerating mounts and host entries with ONE shared entry counter, then
  skipping `offset` entries, skips a different number of *visible* names
  depending on how many mount entries precede the host ones. Symptom: pages
  overlap (`duplicates`) at one `count` and drop entries at another — no `count`
  yields all N entries in the expected number of reads.
- Returning a `nread` that is not a multiple of record length lands the client
  mid-record on the next call.

Fix shape: build one ordered, de-duplicated name list (mount children first,
then host entries), encode records with a single shared encoder
(`styxfs_dir_encode(out, cap, name, is_dir, qidpath) -> bytes`), and copy whole
records while `rec_start + rl <= offset` is false and `buf_off + rl <= count`
holds. Put the encoder test first: for a 3-char name assert `len == 64`,
`size field == 62`, name length at offset 41 and name bytes at 43. The wire
helpers here are LITTLE-endian (`styx_put16`) — parse with `b[0] | b[1] << 8`,
not the reverse.

## `Tcreate` moves the fid onto the new node
After `styxfs_create_cb` succeeds the fid names the created file, so a second
create issued on the same fid resolves its parent as that file and returns
`ENOTDIR`. Tests that create several siblings must re-root the fid
(`free(f->file_state); f->file_state = strdup(parent)`) between cases.
Likewise a namespace path with no mount mapping has no host target — `create`
under `/n` fails with `ENOENT` until the test mounts a real directory at that
prefix.

## Callback tests need a fid, not a socket
`styxfs_read_cb` / `_write_cb` / `_create_cb` / `_stat_cb` can be driven
directly: `styxfs_init(&srv)`, `styx_fid_alloc(&srv.base, n)`, set
`f->file_state` to the namespace path and `f->qid.type`, then call the callback.
That harness closes read/write/create/stat goals without a client or a wire
round trip, and it is the cheapest place to assert EOF, short counts and mode
validation.

## Write-to-launch control files: weak probe + write seams in the callbacks

A `/n/<sub>/<name>/launch` file that must work for a NOT-YET-EXISTING item
needs two weak seams in styxfs_callbacks.c (real defs in the ns module,
linked via RT_OBJS + the gate recipe): `wubu_ns_guests_probe(path,&qid_type)`
consulted in walk when disk reachability fails (synthetic dir/file qids),
and `wubu_ns_guests_write(path,data,count,&nw)` consulted in write BEFORE
the disk write (1=handled ok, -1=handled refused -> Rerror, 0=fall through).
Match the subtree by COMPONENT scan (works for both "/" and "/n" mounts),
validate names as single components (reject whole ".." and "/"; embedded
dots like "a..b" are legal filenames, not traversal). The dispatch must call
the SAME validated API as the in-process path. Ownership: the module keeps
an owned-pointer list of what it launched; the lifecycle calls weak
sync (retire) + forget (before free); an in_sync guard makes
retire->sync->reap->destroy re-entrancy-safe, and wait/state must capture
return values into locals BEFORE retiring (the sync may free the ct).

## Socket framing: the size prefix is LITTLE-endian, and builders already frame
`styx_build_tversion`/`_tattach`/`_tread` etc. already write the 4-byte size
prefix, so a client sends the buffer **as-is** — prepending another header makes
the server read a bogus size. Read that prefix with `p[0] | p[1]<<8 | ...`, not
network order: big-endian parsing turns 19 into `0x13000000`, which the length
guard rejects *before* any diagnostic can print, so the failure surfaces as a
bare `-1` and looks like a hang. When a socket round trip dies silently, dump
the first four bytes (`printf("%02x%02x%02x%02x")`) before theorising — that is
what identified both this bug and the directory-record endianness bug.

## Verify
1. `make test_ns_<name>` → builds, runs, N checks / 0 failures.
2. `make a11y_shot` AND `make gui_shot` → EXIT=0 (the weak-linked render
   path still builds and captures).
3. `make check_dupes` → clean (a new `.c` whose basename duplicates a
   built file is flagged — a namespace module with a unique name is fine).
4. Full GUI gates: `test_wm`, `test_apps`.

## Casing on an enum you did not define: grep the real names first
When a new module maps a payload/type enum onto a category (e.g. a
`switch (payload_type)` returning an ABI), grep the enum's DEFINITION for
the exact spellings before writing the cases. Enums drift from intuition —
`WUBU_PAYLOAD_MACHO` is really `WUBU_PAYLOAD_MAC_MACHO`; a wrong case name
fails at compile, but a MISSING case silently falls to `default`. List the
enum block (`grep -nE 'WUBU_PAYLOAD_[A-Z_]+' <defining .h>`) and case on
every value you mean to handle, with an explicit `default`.

## Do not assert float equality at a tolerance boundary
`0.80f - 0.65f == 0.15f` is FALSE (the subtraction is 0.15000001). When a
test checks a gap/threshold decision at exactly the tolerance, pick inputs
clearly INSIDE the boundary (e.g. gap 0.10 vs tolerance 0.15), not exactly
on it. The `>` vs `>=` in the guard is correct; the test's "exactly at the
boundary" expectation is the fragile part.

## A new module's `.o` is not in the existing test link lines
When a render/exec file newly calls a freshly added module, the test/capture
recipes that build that file go `undefined reference to <new_symbol>`. Two
fixes, in preference order: (1) weak no-op defaults in the caller (see the
weak-symbols section) so every link line works without edits; (2) add the
`.o` to the specific recipes. Do NOT assume adding to `RT_OBJS` covers the
test recipes — those name their objects explicitly.

## Prefer folding a new GUI test into an existing suite over a standalone binary
A standalone `test_<thing>` that links only the engine often fails because
the engine pulls in globals from sibling modules (a theme/text-color `tc`,
etc.) you did not anticipate. If an existing suite (`test_wm`)
already links the full engine + deps and builds green, add the new test
FUNCTION to that suite's `.c` and its `main()` call list (TEST/PASS/FAIL/
CHECK macros, one call line) instead of crafting a new link line. Cheaper
and it inherits a known-good link set.

## Brain-tree tool tests: no `wubu_test.h`, and `/tools/test_*` is gitignored
Two wubuwizard-specific traps:
- `wubu_test.h` lives in the wubuos Body tree, NOT in wubuwizard. A
  wubuwizard `tools/test_*.c` must roll its own `static int checks, fails;`
  + a local `CHECK`/`FAIL` macro (see any `tools/test_toolreg.c`). Including
  `wubu_test.h` there is a `fatal error: no such file`.
- wubuwizard's `.gitignore` has `/tools/test_*`, so a new tool test is
  ignored. `git add -f tools/test_<name>.c` or the commit silently omits it.

## Related skills
- `wubunos-hosted-capture-bridge` — capture harness link lines, stub-vs-real
- `wubuos-build-recovery` — link-line triage, stale-object trap
- `wubuos-test-suite` — gate set + verification order