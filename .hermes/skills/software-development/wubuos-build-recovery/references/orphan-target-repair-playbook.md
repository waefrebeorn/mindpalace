# Repairing a test target nothing was running

Reachability first (see `test-suite-honesty-gates.md` Gate 1): a `test_*`
target not reachable from `make test` rots silently until you wire it up. Once
you do, expect the failure to be a WIRING or FIXTURE problem far more often
than a logic bug. Work the order below; each step assumes the previous passed.

## 0. Decide mechanical vs structural before touching the recipe

Compare the failing recipe's source count against a WORKING SIBLING that serves
the same role. Same order of magnitude (576 vs 28) is mechanical: keep adding
missing sources. An order of magnitude apart is STRUCTURAL — the target
deliberately uses a different source set and will never converge by appending
files. Each file you add drags in its own transitive deps; four rounds of that
is the signal to stop and make a decision instead.

**Corollary: a recipe may reference make variables that are defined nowhere.**
They expand to nothing, so the recipe silently links none of the sources it
appears to name. That is a broken recipe, not missing flags.

### Track the closure; STOP when it oscillates

Record (undefined symbols, cumulative files added) every round. Reaching ZERO
undefined references does NOT mean you converged — a recipe can link
completely and still be unsalvageable:

| round | undefined | files linked | added |
|---|---|---|---|
| start | 128 (45 distinct) | 2 | - |
| hand-resolve every symbol | 0 (links!) | 27 | 25 |
| next round | 110 | - | 58 |
| copy a sibling's GUI list | 3 | 61 | 34 |
| add those 3 | 45 (the SAME ones) | - | 22 more |

45 -> 3 -> 45 is a CYCLE over the whole application stack. Stop rule: if the
next round needs more than ~15 new files, or the symbol count does not
STRICTLY decrease, revert. Two rounds at similar counts is the signal.

### Never resolve symbols to a test stub

Many files define the "missing" symbols as no-op doubles — `hosted_test.c`,
`wm_test_stub.c`, `cmd_test_stub.c`, `wubu_hc_eval_stub.c`,
`test_agi_kernel_stub.c`, and every `*_test_support.c` / `*_test_stubs.c`.
Linking one makes the test PASS VACUOUSLY, which is strictly worse than
failing because it converts a visible defect into permanent green. Filter
paths matching `_test`, `_stub`, `_support` before resolving.

### Pick the sibling by what it LINKS, not by name

Rank candidates by how many sources of the relevant kind their recipe links,
then RUN the top one to confirm it passes before copying from it. Name
similarity lies: `test_styxfs` shares the `$(HOSTED_TEST_OBJS)` variable with
`test_hosted` but links compiler + JIT + StyxFS and NO GUI, so it is useless as
a template for a desktop target. `test_wm` (28 GUI sources, 33/33) was
the real template.

Prefer `make -n <working-sibling>` and diff the object lists over reading the
recipe text — it shows the exact expansion, including objects that came from a
variable.

## 1. Missing symbols: find the real home, don't guess

    for s in wubu_popen_read wubu_atan2; do
      echo "$s -> $(grep -rlE "^[a-z_ *]+$s *\(" src/kernel/*.c src/runtime/*.c | head -1)"
    done

Prefer the DEFINITION over the first caller. A regex will happily match the
call site instead (`klog_printf` lives in `klog.c`, not `interrupt.c`), and
adding the caller's file drags in a dependency tree you did not want.

Before appending the compiler source set (MIR passes, wasm, spirv, vulkan,
host_tensor, tgemm_avx512, `-lm -ldl -fopenmp -lpthread`), check the recipe has
`-I$(COMP)`. `wubu_isa_wasm.h` includes `wubu_isa_driver.h`, so a recipe lacking
that include path fails with a confusing missing-header error.

Add each library independently — checking only `-lm` misses that `-fopenmp` is
a separate requirement (it is what satisfies the `omp_*` calls in
`tgemm_avx512`), as is `-ldl` and `-lpthread`.

## 2. A generated file under the wrong extension blocks everything

`No rule to make target 'src/hosted/xdg-shell-private.c'` — the
wayland-scanner output had been saved as `.code`, so no pattern rule could
build it and the target was structurally impossible. Rename to what the build
expects.

**Check what includes it by name before renaming anything.** A sibling was
included as `xdg-shell-client.header` from `hosted.c`, so renaming it to `.h`
broke a build that had just been fixed:

    grep -rn 'xdg-shell-private\|xdg-shell-client' src/ | head

## 3. Fixtures that were never unpacked

A test reading a data file that exists only inside a committed archive fails
with what looks like a code defect. Check the payload before debugging the
loader:

    python3 -c "import zipfile;print([n for n in zipfile.ZipFile('X.zip').namelist() if n.endswith('.exe')])"

If the archive contains exactly the path the test wants, add the extraction to
the recipe (and the archive to its prerequisites) rather than editing the test:

```make
	@mkdir -p vendor/games/openarena_extract
	@python3 -c "import zipfile; z=zipfile.ZipFile('vendor/games/openarena-0.8.8.zip'); d='vendor/games/openarena_extract'; [z.extract(n,d) for n in z.namelist() if n.endswith('.exe')]"
```

Not all fixtures are missing — check each path individually. One of the two
existed already; only the extracted one was absent.

## 4. Tests that write into the USER's real data directory

A count-based assertion fails based on what else is installed:

    FAIL: scan = 6, want 3 (junk skipped)

Here the scanner was CORRECT — it found three real games installed months
earlier. The test wrote its fixtures into `~/.wubu/games` and then counted every
file there, polluting real data and making its result machine-dependent.

Make the path overridable and point the test at scratch:

```c
#define GAMES_DIR_DEFAULT "/home/wubu/.wubu/games"
static const char *games_dir(void)
{
    const char *e = getenv("WUBU_GAMES_DIR");
    return (e && *e) ? e : GAMES_DIR_DEFAULT;
}
```

```make
	-rm -rf /tmp/scratch_dir && mkdir -p /tmp/scratch_dir
	WUBU_GAMES_DIR=/tmp/scratch_dir ./$(GUI)/test_foo
```

Have the test REFUSE to run without the variable rather than silently falling
back to the real directory. Verify afterwards that the real directory is clean
— the fake fixtures should be gone from it.

## 5. The test is right and the code is a stub

Once a target finally builds and runs, a remaining assertion failure may not be
a wiring problem at all — it may be testing behavior that was never implemented.

    ❌ GAME mode entered (line 82)

Read the function the test calls before touching the recipe:

    (void)hosted;      /* the desktop state argument, ignored entirely */

A discarded parameter is a documented feature nobody built. The function's own
header comment claimed the launch "is recorded in the session's game session
context"; that had never been true. Fix the CODE, not the test.

Two ordering decisions to make deliberately rather than to satisfy the
assertion:

- **When does the state transition happen relative to validation?** Putting the
  mode switch FIRST is usually correct when the switch is the observable effect
  the caller asked for: a failed launch must still leave the shell it was told
  to bypass. Doing it after validation leaves the desktop showing, which is the
  opposite of what "Play" was asked to do. The test may only pin this down
  because it passes a NULL name — read why before choosing.
- **Is the missing function's contract inferable?** A test calling
  `wubu_session_mode_name()` that exists NOWHERE in the tree is not rot — it was
  never written. A `static inline` beside the enum it names is the smallest
  honest fix.

## 6. Two modules, one basename, different directories

    undefined reference to `wubu_theme_current'

After adding the file whose basename matched, the symbol was still undefined:
`src/gui/wubu_theme.c` and `src/kernel/wubu_theme.c` are DIFFERENT modules and
only the GUI one provides the applets' symbols. Resolve the undefined symbol to
a DEFINITION before choosing which file to add, and confirm which directory
the recipe's flags actually search:

```sh
grep -n 'wubu_theme_current' --include=*.c --include=*.h src/ | head
```

**Two files with the same basename in different packages** (`src/gui/wubu_theme.c`
vs `src/kernel/wubu_theme.c`) are different modules, and picking the wrong one
produces a NEW undefined symbol for the very function you were chasing.

Checklist for any "I added the file and it still doesn't link": the symbol may
live in a same-named sibling, the header may need an `-I` path the recipe lacks
(the GUI applets include `wubu_world.h` for a TYPE only — no `wubu_world`
symbol is referenced, because the design injects a fake provider, so that is an
include-path fix and not a new link dependency).

## 7. A target that compiles no test source at all

    error: no input files

The recipe linked only library sources, so there was nothing to assert. Check
whether a real test for that subsystem exists under another target name before
writing a new one — here `test_zip_extract` duplicated `test_zip`, which
decompresses a real member out of a 425MB archive using the kernel's own
inflate. Delegate instead of duplicating:

```make
test_zip_extract: test_zip
	@echo "test_zip_extract is the same kernel-ZIP-reader test as test_zip (see mk/tests.mk)"
```

## 8. Stale API references hide under the layers you just cleared

Each fix exposes the next. `test_hosted` had a missing prerequisite, then an
API drift (`wubu_holyd_eval` → `wubu_holyd_agent_eval`) from a rename earlier
that day, then a full desktop-shell link missing a dozen modules. Expect N
rounds; re-run and re-read the log after each rather than assuming the next
error is the same category.

## 9. The test's own checker is the bug, not the code

A failure naming two values that "must not conflict" or "must not overlap"
can be the ORACLE miscomputing liveness, not the allocator misbehaving.
Before touching the code under test, print what the code actually produced:

```
v0->0  v1->1  v2->2  v3->3  v4->4  v5->4      # allocator output
```

If the assignment is provably correct for the dataflow, the checker is wrong.
In a forward-liveness walk, a kill step that deliberately spares `def_dst`
(correct: an SSA redefinition stays alive) followed by an UNCONDITIONAL
re-add means a value with `first_def == last_use` -- dead the instant it is
produced -- is resurrected at its own definition and stays live forever:

```c
if (last_use[av] == i && av != def_dst) continue;   /* spares def_dst */
if (has_dst) vrset_add(&live, in->dst);             /* ...then re-adds it */
```

Fix by adding a def only when it is read later (`last_use[dst] > i`), which
matches how the real allocator assigns. See the negative-control rule: inject
a deliberate violation and confirm the checker still catches it, or you have
traded a visible defect for permanent green.

## 10. Concurrent builds in one tree fake a mass regression

Two `make` invocations against the same tree contend and produce thousands of
bogus failures that look exactly like a real regression:

```
TOTAL  pass=24940   fail=5908    error=33384
FAIL gcc_torture_000003_950809_1 x86-64     expected=0 got=1
```

Do not report that as a regression or start reverting. Two tells: the
failures name a backend you did not touch, and every one is the SAME trivial
mismatch. Re-run the affected target ALONE after the other job exits, and
compare against the known baseline -- it came back `pass=3458 fail=0`, exactly
matching. Only the clean serial number is reportable.

Corollary: never launch a background job and a foreground build over the same
tree. If you need both, run them serially, or give the second a separate
`git worktree`.

A recipe is ONE shell command joined by `\`. Two hazards:

- **Never tokenise on whitespace and rejoin.** Collapsing the continuations
  turns the compiler into a prerequisite:
  `make: *** No rule to make target 'gcc'.`
- **Anchor the insert on `\s-o\s`, then read the diff.** A patch can swallow an
  adjacent line (an `-o <output>` flag silently became a source argument) while
  still reporting success.
- **Use literal `src/...` paths, not guessed `$(VAR)` forms.** `$(GUI)`,
  `$(KERNEL)`, `$(RT)`, `$(COMP)`, `$(HOSTED)` are defined in mk/vars.mk;
  `$(SRC)` is NOT and expands to nothing, leaving `//filename.c` debris.
- **Insert as its OWN tab-indented continuation line ending in `\`**, never
  append into an existing long line — appending lands on the wrong token and
  concatenates paths (`wubu_spawn.c/hosted`).

Verify the continuation count is unchanged after every edit:

```python
print("continuations:", body.count('\\\\\n'))
```

Then run the mechanical checks, which catch the corruption modes above:

```sh
make -n <target> | grep -oE '[^ ]*//[a-z0-9_]+\.c'   # must be EMPTY
grep -c '$(SRC)/' mk/tests.mk                          # must be 0
git diff --stat mk/tests.mk                           # intended line count
```

A target line carrying a LEADING TAB is not a target at all — make parses it
as a recipe command of the rule above it and tries to execute it
(`make: test_kvfs:: No such file or directory`, Error 127). The line then
vanishes from the prerequisite graph, which is why the wiring gate flags it as
a NEW orphan after you fix the tab. Sweep for others:

```python
for i, l in enumerate(lines):
    if re.match(r'^[a-zA-Z_][\w-]*:', l) and not lines[i+1].startswith('\t'):
        print(i+1, l)
```

## Typos worth grepping for wholesale

    grep -n '^\s*t\$(CC)' mk/tests.mk      # stray char before the compiler

A stray character before `$(CC)` makes make try to execute a program named
`<char>gcc`. Sweep for it across the file rather than fixing one site.

## Finally: exit 0 is not a result

After the target builds, confirm it REPORTS something. Exit-code-only passes are
exactly the class of bug this whole exercise is about:

    timeout 300 make -s test_foo 2>/dev/null | tail -5

If a "passing" target prints nothing, you have found another vacuous test, not
a fixed one.
