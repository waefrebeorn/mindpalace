# Hosted Binary → Incremental Object Linking (concrete recipe)

Concrete before/after from the 2026-07-09 session that turned `make hosted` from a
~63-file inline recompile into a one-object incremental relink. Drop into any WuBuOS
Makefile that still compiles the hosted/main binary inline.

## Before (the bottleneck)

```makefile
# OBJS line (built by pattern rules, then THROWN AWAY by the link step)
HOSTED_OBJS = $(HOSTED)/hosted.o $(RT)/styx.o … $(KERNEL)/vbe.o $(KERNEL)/memory.o \
              $(GUI)/wm.o … $(RT)/wubu_archd.o …

hosted: $(HOSTED_OBJS) $(HOSTED)/xdg-shell-private.o
	$(CC) $(CFLAGS) -DVBE_HOSTED -DWUBD_TEST_MAIN -I… \
		$(HOSTED)/hosted.c $(RT)/styx.c $(RT)/styxfs.c $(KERNEL)/vbe.c $(KERNEL)/memory.c \
		$(KERNEL)/input.c … $(GUI)/wm.c … $(COMP)/holyc_*.c … \
		$(RT)/wubu_archd.c … \
		$(HOSTED)/xdg-shell-private.o $(HOSTED)/primary-selection-private.o \
		-lwayland-client -lxkbcommon -lm -lsqlite3 -lzstd -lz -o $(HOSTED)/wubu
```

Problem: recompiles all 63 `.c` inline every `make hosted`, ignoring the `.o` already built.

## After (incremental)

```makefile
# Hosted variants compiled with default (PIE-capable) CFLAGS, NOT the bare-metal
# kernel flags. The hosted binary is a userspace PIE.
HOSTED_OBJS = \
	$(HOSTED)/hosted.o $(HOSTED)/vbe_hosted.o \
	$(RT)/styx.o $(RT)/styxfs.o \
	$(HOSTED)/memory_khosted.o $(HOSTED)/input_khosted.o $(HOSTED)/tasking_khosted.o \
	$(HOSTED)/interrupt_khosted.o $(HOSTED)/wubu_math_khosted.o \
	$(BRIDGE)/bridge.o $(BRIDGE)/wubu_syscall.o \
	$(GUI)/gui_dbuf.o … $(GUI)/wm.o … \
	$(COMP)/holyc_lexer.o … $(APPS)/repl.o $(APPS)/apps.o \
	$(JIT)/jit.o $(JIT)/wubu_x86.o $(JIT)/wubu_disasm.o $(JIT)/x86_regalloc.o $(JIT)/jit_minic.o \
	$(RT)/wubu_host_exec.o … $(RT)/wubu_container.o $(RT)/wubu_compat_db.o $(RT)/wubu_arch.o \
	$(HOSTED)/archd_hosted.o $(RT)/wubu_ramdisk.o $(RT)/wubu_spawn.o \
	$(RT)/oci/oci_http_client.o \
	$(HOSTED)/xdg-shell-private.o $(HOSTED)/primary-selection-private.o

# Kernel sources for the hosted (userspace PIE) binary.
$(HOSTED)/%_khosted.o: $(KERNEL)/%.c
	$(CC) $(CFLAGS) -I$(KERNEL) -I$(HOSTED) -I$(GUI) -I$(RT) -c $< -o $@

# vbe.c with -DVBE_HOSTED for the in-process hosted framebuffer.
$(HOSTED)/vbe_hosted.o: $(KERNEL)/vbe.c
	$(CC) $(CFLAGS) -DVBE_HOSTED -I$(KERNEL) -I$(HOSTED) -I$(GUI) -I$(RT) -c $< -o $@

# archd without its daemon main (the hosted shell owns main).
$(HOSTED)/archd_hosted.o: $(RT)/wubu_archd.c
	$(CC) $(CFLAGS) -DWUBD_TEST_MAIN -I$(RT) -I$(COMP) -I$(JIT) -c $< -o $@

# Link-only target: reuses the .o files above.
hosted: $(HOSTED_OBJS)
	$(CC) $(CFLAGS) -I$(HOSTED) -I$(KERNEL) -I$(RT) -I$(BRIDGE) -I$(GUI) -I$(COMP) -I$(JIT) -I$(APPS) \
		$(HOSTED_OBJS) \
		-lwayland-client -lxkbcommon -lm -lsqlite3 -lzstd -lz -ldl -o $(HOSTED)/wubu
	@echo "✅ WuBuOS hosted binary built (./src/hosted/wubu)"
```

## Timing proof

```text
make clean && time make hosted      → 8.96s   (full build, once)
touch src/gui/explorer.c && time make hosted → 0.51s (1 .o + relink)
```

`grep -cE 'gcc.*-c '` on the incremental run's log should equal **1** (only the touched file).

## Variant-rule pitfalls encountered

- The kernel pattern rule (`$(KERNEL)/%.o`) compiles with `-ffreestanding -nostdlib
  -fno-pie -mcmodel=kernel`. Those `.o` CANNOT link into the PIE hosted binary
  (`R_X86_64_32S against .rodata` relocation error). Hence the `*_khosted.o` variants
  compiled with plain `$(CFLAGS)`.
- `wubu_archd.c` and `wubu_holyd_lifecycle.c` guard `main` with `#ifndef WUBD_TEST_MAIN`.
  The old inline recipe compiled everything with `-DWUBD_TEST_MAIN`, so the daemon mains
  were suppressed. With pattern-rule `.o` (no such flag) you get a `multiple definition of
  'main'`. Fix: compile `archd` as `archd_hosted.o` with `-DWUBD_TEST_MAIN` and link that.
- `oci_http_client.o` was MISSING from the old inline recipe too — so the `repo_update`
  feature (real HTTP fetch) was silently unlinked (form≠function). Add it explicitly.

## Networking-test "hang" diagnostic

Tests that spawn `python3 -m http.server` + call real fetch code:
- Run with `stdbuf -oL -eL ./test_bin` so `RUN_TEST` progress prints flush.
- A prior interrupted run may leave a server child holding the port → new run appears to hang.
  `pkill -f http.server` before re-running.
- The test in this session was NOT hung — it completed 11/12 then 12/12 after fixes; the
  "hang" was buffering + a stale server child.
