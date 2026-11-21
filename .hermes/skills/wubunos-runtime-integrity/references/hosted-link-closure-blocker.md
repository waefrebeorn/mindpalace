# test_metal / test_hosted: link closure measured, blocker identified

Both were called "structural" because their recipes were tiny next to a
sibling's ~576 sources. The real situation is specific.

## test_metal closure (measured, then reverted)

Undefined symbols walked 16 -> 57 -> 33 -> 13 -> 6 by adding ONLY real
implementations (never test stubs). The residual is the actual blocker:

    _kernel_start, _stack_top          linker-provided (crt0.S)
    wubu_smp_tramp_start / _end        real, in wubu_smp_tramp.S
    inb, outb                          privileged x86 IN/OUT

## Why inb/outb cannot be fixed by linking

`ps2.c`, `wubu_rtc.c`, `wubu_wdt.c` define `inb`/`outb` as `static inline`
with real `in`/`out` instructions. Those #GP-fault in user space, and there is
NO hosted port-I/O shim anywhere under src/hosted/ (verified).

Closing test_metal therefore needs NEW infrastructure -- a hosted port-I/O
HAL -- before the remaining link work (which is mechanical) can proceed.
Same conclusion as test_hosted. Both stay in the orphan baseline.

## Reusable resolver

/tmp/resolve.py maps undefined symbols to their defining file, EXCLUDING any
`*_test.c` so a stub is never selected:

    python3 /tmp/resolve.py <symbol-list> <out-file>

Prints per-file counts plus symbols with no real definition. Rebuild it from
this spec if the scratch dir is pruned.