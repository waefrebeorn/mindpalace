---
name: wubukernel-driver-model
description: Use when working in WuBuKernel or on its WuBuOS bridge.
version: 1.0.0
---

# WuBuKernel / WuBuDriver

Repo: github.com/Waefrebeorn/WuBuKernel, local `/home/wubu/WuBuKernel`.
Consumed by WuBuOS as submodule `src/kernel/WuBuKernel` (bridge gate:
`make test_kernel_bridge` in wubuos).

## Pieces
- `include/wubudriver.h` + `src/wubudriver.c`: device/driver registry.
  Device carries class id; driver claims via probe (0 = claimed). Bind order
  = registration order (deterministic). Lifecycle: bind/detach/shutdown/
  suspend/resume, refcounted open/release.
- `include/wubukcore.h` + `src/wubukcore.c`: COM1 console with injectable
  sink, bounded arena allocator (`wubu_heap_init(base,bytes)`, refuses
  oversized/zero), `wubu_panic`, tick counter.
- `include/wubukernel_pmm.h` + `src/wubukernel_pmm.c`: physical memory manager.
  Bitmap over caller-supplied boot regions in one index space; bases rounded up
  to a frame; alloc never repeats a frame and returns 0 when exhausted; free
  ignores foreign/unaligned pages and does not refund an already-free frame.
  `make test` runs its contract gate (`src/wubukernel_pmm_test.c`).

## Rules
- Strict C11 freestanding, no libc headers. Gate both:
  `make test` (hosted behaviour) and `make freestanding`
  (`-ffreestanding -nostdinc` compile proof).
- After editing the kernel repo from wubuos, bump the submodule:
  `cd src/kernel/WuBuKernel && git fetch origin main && git reset --hard origin/main`
  then commit the pointer in wubuos.
- Binding order is the API contract: never sort or hash the registry.

## Known trap
`wubu_bus_detach_all` must clear state even when the driver has NO detach hook
(a hook-less driver was left stuck BOUND until the wubuos bridge caught it).
