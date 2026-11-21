---
name: wubuos-lapic-tick-chain
version: 1.0
author: WaefreBeorn + Hermes
license: MIT
description: Use when WuBuOS ticks freeze. EOI first; QEMU lapic debug.
metadata:
  hermes:
    tags: [wubuos, kernel, lapic, interrupts, timer, eoi]
    related_skills: [wubuos-architecture, wubuos-build-recovery]
---

# wubuos-lapic-tick-chain

## When to Use
- The WuBuOS bare-metal tick chain is frozen: uptime/task_tick not advancing, tasks never wake from task_sleep, no bonzi heartbeat, GUI has no time source.
- You are editing pit_handler / interrupt_eoi / wubu_apic_enable / run-agi.sh.
- A wubuos IRQ handler might preempt (call task_switch_asm).

## The bug class (proven 2026-10-20)
A preemptive context switch FROM INSIDE an interrupt handler abandons the handler frame mid-flight. If the EOI has not run yet, the LAPIC keeps the vector IN-SERVICE forever and blocks that entire priority class: the timer fires once, then silence. No #PF, no panic -- the console keeps answering (serial is polled), so it looks alive.

Rule: pit_handler sends interrupt_eoi(32) as its FIRST statement and has NO trailing EOI. The IDT gates are interrupt gates (IF=0 in the handler body), so EOI-first cannot re-enter before iretq.

## Scheduler discipline (the deeper layers, all proven the same day)
The EOI fix alone left the chain freezing at 1-4 ticks. Full fix set (commit 4aaba3a6):
- The timer IRQ NEVER context-switches. Rotation is deferred to task edges (task_yield, idle hlt+wake). An in-IRQ switch is unfixable in both directions: with a trampoline sti it re-arms nested IRQ delivery inside an abandoned handler (runaway nesting until the ISR depth guard trips -- measured tick=4, overruns=2); without it every first-run task runs IF=0 forever.
- task_trampoline STIs before calling the entry: the assembly switch lands there with IF=0 (its trailing cli). The primed rflags.IF=1 states the intent -- a running task takes interrupts.
- A resumed task ALWAYS runs with IF=1 (unconditional sti after task_switch_asm in task_yield). A faithful flags restore PROPAGATES a leaked cli into every task's saved flags: the yield/switch rotation then spins deaf at full speed with RFL=0x02 while IRR 32 sits pending (measured twice via monitor snapshots at vsprintf+0x62e and task_switch_asm+0xac).
- task_insert/task_remove/task_yield's pick+switch run with interrupts off (pushfq/popq/cli save-restore helpers): a tick landing mid-insert made task_schedule_next walk a half-linked ring into a half-primed task.
- task_idle is hlt + task_yield per wake: an idle that never yields starves every sleeping task once the in-IRQ switch is retired.
Every long-running task loop must reach a yield (the console REPL, the supervisor loop, task_sleep); a spinner is caught by the stall watchdog.

## interrupt_eoi must cover LAPIC-owned vectors
In APIC mode every delivered interrupt came THROUGH the LAPIC (LINT0 masked kills the legacy PIC path; the I/O APIC routing is unused). ioapic_routed alone is wrong -- the LAPIC TIMER itself is not I/O-APIC-routed. Condition: ioapic_routed OR g_lapic_base, then lapic_eoi() (self-guards on NULL).

## The other frozen-tick signature: clock source configured with no handler
A tick chain that advances for a handful of interrupts and then goes silent can
ALSO mean the configured clock was never wired, not that EOI is stuck.

- `interrupt_init_full()` initialised the LAPIC periodic timer on vector 240
  (`lapic_timer_init(100, 240)`) but NO handler was ever registered for 240 --
  the configured clock could never tick the kernel.
- Firmware paths (WuBuFW) leave the 8259 IMR at 0xFF; the PIT unmask clears
  bit 0 only, so a few IRQ0s get through and then the master mask stops them.
  GRUB/QEMU `-kernel` paths leave the PIC usable, which is why this is invisible
  unless you boot through our own firmware.

Rule: one shared body, both sources dispatch to it, and exactly one is live:
```c
void wubu_clock_tick(void);              /* scheduler, wdt, vDSO, supervisor, TX ring */
void pit_handler(...)          { wubu_clock_tick(); interrupt_eoi(irq); }
void apic_timer_handler(...)   { wubu_clock_tick(); lapic_eoi(); }
int   wubu_clock_use_apic(void);         /* registers 240, programs the LAPIC timer */
```
Verify `interrupt_register(<vector>, handler, NULL)` actually ran for every
timer vector you program -- a timer with no handler is a silent clock.

## Diagnosing a frozen tick (ordered, cheapest first)
1. Count invocations inside the handler (static counter + klog). If the count
   stalls, the interrupt is not being delivered.
2. Read the 8259 mask directly: `inb(0x21)` / `inb(0xA1)`. `0xff/0xff` means
   every PIC IRQ is masked regardless of what your init wrote.
3. Trap writes: wrap the `outb` inline in `interrupt_io.h` to log any write to
   `PIC1_DATA`. That names the writer immediately instead of guessing from
   code reading.
4. Trace vectors in `isr_dispatch` (first-seen bitmap + vector number) to tell
   "hardware stopped delivering" from "delivered but dispatched elsewhere".
5. Do not trust a task-side sampling loop as proof: `task_sleep` does not block
   when ticks are dead, so a per-iteration debug print runs flat out and makes
   uptime look frozen even after the fix lands.

Kernel printf pitfall while doing this: it does NOT implement `%lu`/`%llx`.
Cast to `unsigned` and print `%u`/`%x` (or split a u64 into two `%x` halves);
the literal specifier shifts every later argument and reads like a real bug.

## Ground-truth debug: QEMU HMP monitor over a unix socket
Do not theorize about interrupt state -- ask QEMU. Launch with `-serial stdio -monitor unix:build/mon.sock,server,nowait`, then from python connect AF_UNIX and send:
- `info lapic` -- ISR/IRR/PPR/LVTT/Timer counts are the device truth. ISR 32 stuck plus IRR 32 pending plus PPR 0x20 = the abandoned-EOI signature.
- `info registers` -- RFL bit 9 = IF, CR3.
- `xp /Ngx <phys>` -- walk guest page tables without the kernel (PML4 0x300000, PDP 0x301000; APIC window = PDP[3]).
Send exit-newline on stdin after ~1.5s to boot the firmware shell into the chain.

## Loader handoff ABI
wubu_loader_handoff_t at 0x91000 starts with magic (u64) THEN version (u32). Reading hd[0] as a bare uint32 grabs the magic low half -- read the struct. The version check must accept the loader current version range (1..2), not `!= 1`.

## Boot-test script structure (run-agi.sh)
- Stream QEMU stdout continuously (select/os.read) while it runs: an undrained 64KB pipe silently stalls the guest serial writes.
- Never race a blind fixed sleep against boot time: poll the accumulated log for the proof line (bonzi heartbeat) with a deadline (~25s), then terminate. Boot time varies with machine load; the first heartbeat needs kernel init plus 1000ms of supervisor uptime.

## Loud-failure doctrine
wubu_apic_enable() reads back LAPIC_LVT_TIMER after programming and returns -1 (boot panic) on mismatch: a clobbered 0xFEE00000 mapping swallows every EOI write with no fault, and must refuse loudly, not hang mute.