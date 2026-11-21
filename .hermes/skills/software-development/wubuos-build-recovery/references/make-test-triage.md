# make test triage

`make test` is a flat list of targets; it aborts at the FIRST build failure, so
one dead target hides every target after it. Fix them in order and re-run.

## Status: GREEN

`make test` exits 0 with 52 result sets and no errors. Verify with

    make test > /tmp/full.log 2>&1; echo "MAKE_EXIT=$?" > /tmp/full.exit

and check BOTH the exit file and `grep -acE 'Error [0-9]|error:'` on the log.
The `echo` lands in the wrapper's stdout, not the log file, so grepping the log
for an exit marker never works.

Dead targets found and fixed along the way: `wubu_snapshot_copy` (FTW_* macro
conflict), `test_holyd`, `test_holyd_agi`, `test_syscall`, `test_wm`,
`test_holyc`, `test_battery`, `test_manifest`.

## Dead targets: verify the binary before quoting its score

`test_gauntlet` linked and ran for the first time; its recipe had been missing
14 of the suite files the runner references, 8 further sources
(`wubu_mir_ssa/sccp/gvn/fuse`, `wubu_isa_vulkan`, `wubu_isa_spirv`,
`wubu_host_tensor`, `jit/wubu_isa_wasm.c`), and the AVX-512 object. Prefer
`test_gauntlet/suites/*.c` over naming suites individually.

A target that fails to link yields NO results, so a quoted score can predate
the current source entirely. Confirm the build is current before trusting any
number -- see `references/dead-test-targets.md` for the mtime/stale-binary
checks, reused-log traps, and why a `notify_on_complete` notification is not
evidence of current state.

## Reading a run

- `grep -ac 'Results:' log` counts completing suites; compare across runs to
  confirm progress rather than eyeballing the tail.
- `grep -aE 'make: \*\*\*'` names the blocking target. Its absence means the
  suite ran to completion.
- `WRONG`/`CRASH` lines from the battery are indented two spaces; top-level
  `PASS:`/`WRONG:`/`TOTAL:` belong to the battery's own summary block.
- Snapshot ids and object counts contain the substring `failed`
  (e.g. `snap-3bde8c29-0-4567 failed`). Never grep bare `failed` to judge a
  run -- grep `[0-9]+ failed` and check the numbers, or grep `Results:`.

## Link errors that recur

- A target that consumes `$(HOLYD_SRC)` needs `-lm -fopenmp -lpthread`:
  `powf`/`cosf`/`sinf`/`roundf` come from libm, and `wubu_tgemm_avx512.o`
  references `GOMP_parallel`/`omp_get_max_threads`. Consumers:
  test_holyd, test_holyd_agi, test_syscall, test_holyc, test_battery,
  test_hedge, test_album, test_wubu, test_styxfs.
- `wubu_tgemm_avx512.c` must be built via its `mk/pattern-rules.mk` target
  (adds `-mavx512f -dq -vl -bf16`) and listed as a prerequisite. Compiling the
  `.c` inline fails with `always_inline` target-mismatch.
- On this box CUDA's `libm.so.6` shadows the system libm, so a missing `-lm`
  surfaces as `DSO missing from command line` rather than a clean undefined ref.
- A recipe using `-include wubu_gnu_compat.h` must also pass `-Isrc/runtime`,
  or the compiler cannot find the header it was told to include.

## Over-linked test recipes: map the module's real calls BEFORE touching the graph

A launcher/exec test that fails across the compiler graph is usually OVER-LINKED
(recipe lists `$(COMP_OBJS) $(JIT_OBJS) $(RT_OBJS)` + oci/archd wholesale), not
missing a symbol. `era_apps.c` calls only
`wubu_exec_win_pe/holyc/linux_elf/macho` + `wubu_dos_proc_launch` — zero
`wubu_isa_*`, `wubu_tgemm*`, `wubu_mir_*`. Linking the whole `COMP_OBJS` drags
`wubu_isa_vulkan/ptx/amdgpu` + `wubu_tgemm` → `tgemm_avx512` and (if it ever
built) GPU code that cannot compile or run on the CPU-only AVX2 host.

- Map the module's real external deps first: `grep -oE 'wubu_[a-z0-9_]+\('`
  over its `.c`. Re-scope the recipe to the minimal exec set + a HolyC stub (
  `wubu_hc_eval_stub.c` provides `hd_eval` returning -1), never the compiler zoo.
- Completing `COMP_OBJS` is NOT the fix — it is a stale SUBSET of the wubunos
  compiler repo, and a whole-family expansion that adds non-building GPU
  backends regresses every other COMP-consuming target. Sound single-module
  adds are real (`wubu_softfloat.o`→COMP_OBJS, `wubu_image_names.o`→RT_OBJS);
  a Google-group expansion that pulls non-building backends is the failure shape.
- Dry-compile any GPU ISA candidate with the project's real CFLAGS before
  trusting a single-file link; "can't build here" is a host-capability bound,
  not a missing dependency, so completing the shared list is guaranteed
  regression. `wubu_tgemm_avx512.c` can only build via its pattern-rules.mk
  target (see the `-mavx512f` rule above) — the generic `$(COMP)/%.o` rule
  cannot compile it.

## Rename breakage

The `holyc`->`holyd` rename renamed sources but left build lines AND struct
members behind. Two distinct failure shapes:

- stale build lines: `wubu_holyc_agi*`, `wm_holyc_term.c`
- stale FIELD references: `emit_holyc_ffi()` read `m->entries[i].holyd` while
  the struct member is `holyc`. A rename of a .c file never renames the struct
  it uses. After any mass rename, grep for both `\.old`/`->old` and the bare
  identifier -- not just build lines.

To find stale build lines, extract every `$(VAR)/file.c` token from
`mk/tests.mk` and stat it. Var -> path mapping in `mk/vars.mk`:
`KERNEL=src/kernel`, `RT=src/runtime`, `TOOLS=src/tools`, `COMP=src/compiler`,
`JIT=src/jit`, `GUI=src/gui`.

## Test targets that hang the suite

A test target whose child process can spin will stall `make test` FOREVER with
no output, because it blocks in `read()` with no deadline. Any target that
forks children needs a `select()` budget plus SIGKILL. Suspect this whenever
`make test` produces no new output for minutes rather than failing -- see
`references/holyd-codegen-gaps.md` for the `run_isolated` instance.

## HolyD codegen bugs

The `test_holyc` / `test_battery` runtime failures (a literal `42` returning a
code address, and every ternary returning its THEN branch) are NOT build
issues -- both link and run. They are preprocessor and codegen bugs, diagnosed
and fixed; see `references/holyd-codegen-gaps.md` for the causes and the
debugging method.