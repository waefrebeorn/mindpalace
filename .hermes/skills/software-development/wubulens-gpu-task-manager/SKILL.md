---
name: wubulens-gpu-task-manager
description: Build the wubulens GPU lens and task manager in C11.
version: 1.0.0
author: WaefreBeorn
license: WaefreBeorn Umbrella License v3.0
metadata:
  hermes:
    tags: [gpu, nvml, task-manager, tui, c11, wubulens, monitoring]
    related_skills: [nvidia-nvml-gpu-monitoring, waefrebeorn-repo-creation]
---

# wubulens -- the WuBu lens and task manager

## When to use

- Building or extending `wubulens` (`/home/wubu/wubulens`): the per-app GPU
  lens, the system performance view, and the task manager operations.
- Adding a task-manager operation (end task, suspend, priority, startup
  toggle) or a new tab to its terminal interface.
- Answering "what is using my GPU right now, and why?" for this machine.

`wubulens` is BOTH the GPU lens and the task manager project -- one tool, not
two. The user's goal is explicitly the best task manager for the system, with
as many real operations as possible.

## Standing rules (this user's requirements)

1. **Research before designing.** For a build goal, survey what the
   references and competitors actually do -- their tabs, their columns,
   their operations -- before choosing ours. The user asks for "as much task
   manager operations as possible", not a minimal subset.
2. **Our own interface design.** Never copy the reference tool's layout.
   Read its behaviour and public interface; draw ours.
3. **Every number comes from the machine.** No fabricated metrics, no
   simulated process tables, no invented CPU/memory/GPU figures. When a
   source is unavailable the field is empty and the output SAYS so.
4. **A capability is not a reading.** "The card can attribute per-process
   data" and "a process is using the GPU" are different facts; record the
   capability even when the answer is "nothing right now".
5. **Every destructive operation asks first** (an explicit confirmation;
   anything else cancels) and reports its result. Permission failures are
   named as permission failures, never retried blindly.
6. **One concern per file, C11, opaque structs, minimal includes.** The build
   is clean at `-Wall -Wextra`; warnings are fixed by construction, never
   suppressed.

## Procedure

Build the layers in this order -- each is testable before the next exists:

1. **Data layer.** `perf.c` (/proc resources), `proc.c` (what a pid is),
   `gpu.c` (NVML + a scripted fake backend behind one interface). See the
   `nvidia-nvml-gpu-monitoring` skill for the NVML contract.
2. **`classify.c`** -- what a program is: a kind (ai/game/browser/desktop/
   dev/...) and a group key that collapses multi-process apps into one row.
3. **`narrate.c`** -- the plain-language headline and callouts, composed only
   from readings. Keep it testable with no GPU and no /proc.
4. **`snapshot.c`** -- one picture, two renderings: the text report and the
   JSON form (a schema number that only changes on a breaking change).
5. **`tui.c`** -- the interface. See `references/terminal-ui.md`.
6. **`ops.c`** -- the operations, then wire them into the interface with a
   confirmation.
7. **`session.c`** -- the machine's own start-up surface (autostart entries,
   service units), read from the filesystem.
8. **Gate.** Every layer gets a test that runs on any machine; the
   hardware-dependent ones skip gracefully and assert the explanation.

## Pitfalls

- **Delta rates need two samples.** CPU%, disk and network are differences
  between readings. The first sample after init reports zero rates; a test
  that samples once and asserts a number will fail. Prime, sleep, sample.
- **Filter whole disks and loopback.** `/proc/diskstats` lists partitions
  too (sum only `sdX`/`vdX`/`nvmeXnY`/`mmcblkX`, not `sdX1`/`nvmeXnYpZ`), and
  `/proc/net/dev` must skip `lo` or the numbers are nonsense.
- **`nvmlDeviceGetProcessUtilization` writes ZERO samples on `NOT_FOUND` and
  `GPU_IS_IDLE`** -- reading the buffer hands you garbage pids and absurd
  percentages. Only read the buffer on `SUCCESS`; grow and retry once on
  `INSUFFICIENT_SIZE`.
- **Per-process memory is a different call** from per-process utilisation.
  The utilisation samples carry percentages only.
- **End a whole app, not one pid.** A grouped app (Chromium's helpers,
  Steam's launcher) needs every pid in its group; carry the pid list on the
  app row and end them together.
- **A window whose state was never attached draws nothing.** The classic
  blank-window bug: the launcher creates the window but never sets
  `user_data`, so the draw callback bails on NULL. Attach the state at
  launch, in the same function that creates the window.
- **`-Wformat-truncation` is usually right.** When a bounded copy can still
  overflow, fix it with an explicit `memcpy` of a `strcspn`-measured length,
  not with a wider format or a suppression flag.
- **`usleep` is not in POSIX.1-2008.** Use `nanosleep`; with
  `-D_POSIX_C_SOURCE=200809L` `usleep` is an implicit declaration.
- **Gate the interface on `isatty`.** A terminal UI on a pipe corrupts the
  output and hangs; piped output must be the plain report, which is what
  scripts and agents want anyway.
- **A test that asserts on the wrong pid proves nothing.** Fork the subject
  inside the test and assert the kernel's own view (`/proc/<pid>/stat` state
  letter, nice value), not a shell background job's wrapper pid.
- **A test harness that stubs a symbol must drop the stub when the real
  module joins the link line.** A test that links only the module under test
  gets away with hand-rolled stubs for its dependencies; the moment the real
  dependency is added to that link line, the stub is a `multiple definition`
  and the link dies. Rule: the stub list and the link line are one decision --
  add the real source, remove its stubs in the same edit.
- **Settle before asserting on a child.** A forked child needs a moment to
  reach `setsid()`/`exec`: asserting its session, state or nice value the
  instant it returns races the child's own setup and fails intermittently.
  Wait a bounded interval (tens of ms) for the state to land, then assert.
- **Restore the terminal on a signal, not only on a key.** `ISIG` stays
  enabled, so Ctrl-C arrives as SIGINT and the default action kills the
  process with the alternate screen active and termios still raw -- the
  user's shell is left unusable. Install a handler that only sets a flag, let
  the loop notice it (`select` returns EINTR) and call `raw_off()` before
  leaving. Recipe in `references/terminal-ui.md`.

## Verification

- **The GPU path needs a real workload.** A scripted backend proves the
  pipeline, not the hardware: allocate and touch several hundred MB, then
  confirm the lens names the program and attributes its memory. Build the
  loader with `nvcc -gencode arch=compute_80,code=compute_80` on this box
  (CUDA 12.0 has no native sm_120; the driver JITs).
- **The operations need a real process.** Fork a child and assert the state
  letter goes to `T` on suspend, leaves `T` on resume, the nice value matches
  after `setpriority`, and the child is terminated after end task. A
  terminated child is a zombie until reaped -- accept `Z` as terminated.
- **The gate must pass with no GPU present.** The NVML half reports why it
  is absent instead of failing the build or the test run.

## Reference

`references/terminal-ui.md` -- the self-contained terminal interface recipe
(raw mode, alternate screen, refresh loop, input handling) and its pitfalls.
