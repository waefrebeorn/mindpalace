# `holyd` build — hive integration (2026-08-19)

## Symptom

`make holyd` failed to link with `undefined reference to wubu_hive_new /
wubu_hive_first / wubu_hive_next / wubu_hive_clear / wubu_hive_erase /
wubu_hive_insert` (plus `wubu_runtime_set_personality`, `wubu_run_program`).

The kernel **hive** is *used* by `wubu_runtime.c` but had NO definition anywhere
in the compiler repo — a dangling dependency. The user's directive: integrate
the real hive, do NOT stub it.

## Fix — link the real kernel objects (no stubs)

The hive lives in the OS kernel as freestanding C11 (`wubu_hive.c` only needs
stddef/stdint/string — integrates cleanly into the standalone compiler build):

```
HOLYD_RT  = $(OS_ROOT)/runtime/wubu_runtime.c \
            $(OS_ROOT)/runtime/wubu_runtime_personalities.c \  # wubu_runtime_set_personality
            $(OS_ROOT)/runtime/wubu_spawn.c                    # wubu_run_program (used by jit.c)
HOLYD_HIVE = $(OS_ROOT)/kernel/wubu_hive.c                    # the hive
holyd: $(FRONT) $(MIR) $(ISA) $(INTERP) $(OS_INTERP) $(JIT_SRC) \
       holyd.c holyd_bf_stub.c holyd_elf.c holyd_pe.c holyd_bin.c \
       $(HOLYD_RT) $(HOLYD_HIVE)
	$(CC) $(CFLAGS) -I. -I$(OS_ROOT)/kernel -I$(OS_ROOT)/runtime $^ $(LDFLAGS) -o $@
```

`holyd_bf_stub.c` provides a minimal `bf_run` so `holyd.c` links without pulling
in `brainfuck.c`'s `main` (link `brainfuck.c -DHOLYC_BF_EMBEDDED` to enable the
`-brainfuck` meme for real).

## Verified

`holyd` links (1 MB binary, no stubs) and emits a REAL host-runnable ELF64:
- `int main(){ return 2+3; }`  → `/tmp/t.elf` runs, exit code **5**
- `while(i<10){s=s+i;i=i+1;}`  → exit code **45**

`holyd -emit-elf` is the proven path; `-emit <target>` / `-emit-all` extend it
(see SKILL.md "Emit for all hardware").
