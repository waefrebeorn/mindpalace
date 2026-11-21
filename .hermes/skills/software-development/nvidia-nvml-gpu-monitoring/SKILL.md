---
name: nvidia-nvml-gpu-monitoring
description: Monitor NVIDIA GPUs via NVML -- metrics + per-process.
version: 1.0.0
author: WaefreBeorn
license: WaefreBeorn Umbrella License v3.0
metadata:
  hermes:
    tags: [nvidia, nvml, gpu, monitoring, c11, dlopen]
    related_skills: [wubuos-gpu-shim, wubuos-gpu-emissions]
---

# Monitoring NVIDIA GPUs through NVML

## When to use

- Building any tool that must answer "what is using my GPU right now": a
  monitor, a lens, a per-app attribution view, a status line.
- Reading per-process GPU utilisation or video memory for a pid.
- Diagnosing why a card shows busy with nothing attributed.

## Standing rules

1. **Load NVML at run time with `dlopen("libnvidia-ml.so.1")`, never link it.**
   The binary then builds and starts on any machine with no NVML headers or
   development package, and reports what is missing instead of failing to
   start. `dlopen` the v2 names first and fall back to the v1 names
   (`nvmlInit` / `nvmlDeviceGetCount` / `nvmlDeviceGetHandleByIndex`).
2. **Declare the minimal ABI yourself** (the two sample structs, the handle
   and return types) so the build has no header dependency. Read
   `/usr/include/nvml.h` for the EXACT enum values -- they are an ABI, not a
   convention, and a wrong constant reads a wrong field. The values used by
   this workflow are in `references/nvml-api.md`.
3. **A capability is not a reading.** "The card can report per-process data"
   and "a process is using the GPU" are different facts. Record the
   capability even when the answer is "nothing right now", and say so in the
   output rather than reporting a zero as if it were a measurement.
4. **Per-process VIDEO MEMORY does not come from the utilisation samples.**
   Those carry percentages only. Memory comes from
   `nvmlDeviceGetComputeRunningProcesses_v3` +
   `nvmlDeviceGetGraphicsRunningProcesses_v3` (`usedGpuMemory`), merged by pid.
5. **Never read a sample buffer the driver did not write.** On the
   "nothing to report" returns the driver writes ZERO samples and leaves the
   count untouched -- reading `count` entries is uninitialised memory and
   surfaces as garbage pids and absurd percentages.
6. **A process the driver lists but that has done no work is a real row**
   (memory-only, no percentage). Those rows are the "idle but hogging"
   callout; do not drop them.

## Procedure

1. `dlopen` + `dlsym` the functions you use; keep the pointers in an opaque
   backend struct. Missing optional functions (encoder, PCIe, process list)
   degrade a field to zero, never to a link error.
2. `nvmlInit` (v2, else v1), then `nvmlDeviceGetCount_v2` and
   `nvmlDeviceGetHandleByIndex_v2` per GPU. Cap the count.
3. Sample the card: name, utilisation, memory, power, temperature, clocks,
   PCIe throughput, encoder/decoder utilisation.
4. Per-process utilisation: `nvmlDeviceGetProcessUtilization(dev, buf, &n,
   lastSeenTicks)`. Grow and retry once on `INSUFFICIENT_SIZE` (the driver
   sets `n` to the size it needs). Only read `n` entries on `SUCCESS`.
5. Per-process memory: the two running-process list calls; merge into the
   utilisation rows by pid, and append pids that have memory but no sample.
6. Track `lastSeenTicks` per GPU so each call asks only for newer samples.

## Pitfalls

- **The error code IS the contract.** `NOT_SUPPORTED` (3) = the card cannot
  attribute; `NOT_FOUND` (6) = it can, but wrote no samples; `GPU_IS_IDLE`
  (15) = same, phrased as idleness; `INSUFFICIENT_SIZE` (7) = grow and retry.
  Treating 6 or 15 as a failure makes a healthy card look broken; reading the
  buffer after 6 hands you garbage.
- **The sample struct is padded.** `pid` (u32), `timeStamp` (u64), then four
  u32 utilisation fields: declare them in that order with the same widths or
  every field after `pid` reads from the wrong offset. A mismatch shows up as
  `pid == 0xFFFFFFFF` and percentages above 100.
- **Declare each dlsym'd function's pointer type from the header's ARITY, not
  from memory.** An extra argument in the call occupies the next register:
  `nvmlDeviceGetClockInfo(dev, type, 0, &mhz)` passes `0` as the pointer and
  the clock write goes nowhere, so the field reads 0 while `nvidia-smi` shows
  the real value. Check the signature's parameter count, not only the enum
  values -- a wrong constant reads a wrong field, a wrong arity writes
  nowhere.
- **A laptop GPU may report no power limit**
  (`nvmlDeviceGetPowerManagementLimit` returns 0 or not-supported). Treat the
  limit as best-effort; assert on the draw, not the limit.
- **Per-process attribution is absent on some cards** (older, MIG, vGPU).
  Report that in the headline instead of inventing figures, and fall back to
  card-level numbers plus memory-only rows.
- **Verify against a real workload, not the fake backend.** A scripted GPU
  proves the pipeline, not the hardware path: allocate and touch several
  hundred MB, then confirm the lens names the program and attributes the
  memory. On this box `nvcc -gencode arch=compute_80,code=compute_80` builds a
  working loader (no native sm_120 in CUDA 12.0 -- the driver JITs).

## Reference

`references/nvml-api.md` -- the constants, the two sample structs, the
function signatures and the exact meaning of each return code.
