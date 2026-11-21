# 8086 DOS Shim — `step()` Prefix-Loop Hang (2026-07-19)

## Symptom
`make test_dos_emu_smoke` (or any `.COM` run) **HANGS** — the process never
returns, `timeout 60 ...` kills it with exit **124** (timeout), NOT a segfault.
The smoke test builds and links fine; it just never finishes. In this
session the hang was a real infinite loop, not a teardown reap (which is a
different class — see `wubuos-build-recovery` Mode "reap-hang").

## Root cause
`step()` in `src/runtime/wubu_dos_emu_decode.c` scans instruction prefixes with
a `for(;;)` loop but had **no `break`/`return` after the prefix checks** — when
it read a real opcode it fell through to the next `continue` and treated the
opcode as *another* prefix, looping forever while consuming the program bytes:

```c
int step(WubuDosEmu *e) {
    e->seg_prefix = 0; e->rep_prefix = 0;
    for (;;) {
        uint8_t op = fetch8(e);
        if (op == 0x26) { e->seg_prefix = 1; continue; }
        ...
        if (op == 0xF3) { e->rep_prefix = 1; continue; }
        /* BUG: no break/return here -> every opcode loops as a prefix */
    }
}
```

`wubu_dos_emu_run()` has a `max_steps` hard-cap, but `max_steps == 0` means
"unbounded" and even the bounded cap never trips because `e->steps` is only
incremented in the run loop *after* a successful `step()` returns — a step that
never returns never advances the counter, so the cap is unreachable.

## Fix
Add the return once prefixes are exhausted:
```c
        if (op == 0xF3) { e->rep_prefix = 1; continue; }
        /* Not a prefix: this is the real opcode. Hand it to the decoder. */
        return decode_main(e, op);
    }
}
```

## Companion dead-API stubs that shipped alongside (same session)
The public API had two no-op functions that compiled but did nothing:
- `wubu_dos_emu_step()` — just `e->steps++;` with a **missing `return`**. Fix:
  `int r = step(e); e->steps++; return r;`
- `wubu_dos_emu_peek16()` — empty body, `if (!e) return 0;` then **no return**.
  Fix: `return rd16((WubuDosEmu *)e, seg, off);`

Also removed a stray `fprintf(stderr, "[callfar] ...")` debug line from the
CALL-far path in `decode_main` (`case 0xFF` GRP5 op2==3) — it sprayed stderr
on every far call.

## Diagnosis recipe (hang vs crash)
```sh
timeout 30 ./src/runtime/wubu_dos_emu_smoke; echo "rc=$?"   # 124 = hang
# If you suspect a loop, not teardown: the run loop counter never moves.
# Look for a control-flow path in step()/decode_main() that can spin without
# advancing e->ip or e->steps.
```

## Verification (after the fix)
```sh
make test_dos_emu_smoke   # RESULT: PASS  (no longer hangs)
make test_dos_emu        # 22/22 regression tests pass
make runtime              # clean under -O2
```

## Makefile sub-pattern: tests that load a data file by relative path
`wubu_manifest_test.c` does `wubu_manifest_load("src/runtime/wubu_manifest/
wubu_manifest.json")` — a path relative to the **repo root**. A test recipe
that runs the binary from wherever `make` invoked it will fail to open the
file. Fix: `cd $(CURDIR) && $(RT)/<test>` in the recipe so the relative path
resolves. Model:
```makefile
test_manifest:
	$(CC) ... src/runtime/wubu_manifest/*.c -o $(RT)/wubu_manifest_test
	cd $(CURDIR) && $(RT)/wubu_manifest_test
```
