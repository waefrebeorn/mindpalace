# Scheduler and timer invariants (`tasking.c`, `timer_wheel.c`)

Rules proven by `make test_tasking` / `make test_timer_wheel` / `make test_eevdf`.

## Timer wheel: advance, cascade, THEN fire
A hierarchical wheel must process one tick in this order:

1. `now++`
2. cascade every level whose boundary the new time crosses (`(now & ((1<<6l)-1)) == 0`)
3. fire level 0 for the new `now`

Both wrong orders look like an off-by-N latency, not a crash:

- **Fire before advancing the clock** → an entry with `expiry == T` appears to wake
  one tick late, and every latency assertion reads as late rather than wrong.
- **Cascade after firing** → entries cascaded down this tick land in a level-0 slot
  that was already swept, and wait a whole rotation (64 ticks) for the next pass.
  This only shows up when a test spans the coarse levels; a 200-tick span misses it.

Register the cascade count in the wheel struct and assert it is non-zero in the test —
a cascade that never runs still passes expiry checks that only use short deltas.

## EEVDF: idle is a fallback, not a competitor
When the picker scans the ready list, an idle task that is treated like any other
eligible task takes real share: with two runnable tasks the split came out 44.5/55.5
instead of 50/50, with ~11% going to idle. Handle it in a separate `idle_best` slot
that is used only when no real task is eligible.

Tie-breaking must also be explicit: two tasks with equal vruntime and equal deadline
will otherwise resolve in list order toward the same task. Break the tie on
`total_ticks` so the split stays even.

Priority → weight mapping keeps the old priority ordering alive under EEVDF:
`weight = 128 << prio`, `slice = 4*1024/weight`. A higher priority gets a smaller
slice and therefore an earlier deadline, which is why `task_schedule_next` still
picks it first.

## Real-time class is a separate branch, not a weight
`PRIO_REALTIME` must be selected ahead of every CFS task in the same tick and must
not simply be a larger weight (a big weight still loses to a smaller deadline). Keep
an `rt_best` candidate and return it before the CFS `best`; round-robin equal RT
tasks by vruntime.

## Test harness facts for kernel scheduling

- Hosted `task_yield` uses `setjmp`/`longjmp` on the HOST stack. No hosted task runs
  on `CTask.stack_base`, so stack-watermark, per-task TLS bases and anything needing
  a real stack switch cannot be honestly closed in hosted tests.
- `task_timer_tick` returns early when `g_current` is null, so a test cannot sleep a
  task by ticking. Split the operation: `task_arm_sleep(t, ticks)` (state + wheel
  entry) and `task_wake_expired()` (advance + wake). `task_sleep` = arm + yield, the
  tick = wake, and tests call the two halves — the criterion is then met through the
  real code with no duplicated accounting.
- Any test that loops over a huge tick range should print the iteration count; a
  loop that silently never runs reports the same "error 0" as an exact result.

## Goal accounting note
Tasking goals whose criterion names `make test_tasking` are closed only when that
binary measures the behaviour. A separate `test_<module>` that proves the same code
is an advance, not a closure — write `docs/<TOPIC>-STATUS.md` rather than marking done.
