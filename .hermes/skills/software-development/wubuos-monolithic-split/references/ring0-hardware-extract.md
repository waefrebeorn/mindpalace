# Extracting a ring-0 hardware concern into a host-testable sibling module

Pattern used 2026-07-16 when splitting `src/kernel/interrupt.c` (735 lines):
the 8259 PIC layer (`pic_remap`/`pic_eoi`) and the IRQ-routing linked list
(`IRQRoute`, `irq_route_add`/`irq_route_remove`) were extracted to a
self-contained `interrupt_pic.{c,h}`. Goal: keep the module unit-testable on
the host (no ring-0), while preserving the real hardware poke under metal.

## The key trick: gate the hardware poke, not the whole function

WRONG (the function is dead on the host — can't be unit-tested):
```c
int irq_route_add(...) {
#ifdef MYSEED_METAL
    IRQRoute *r = mem_alloc(...); ... g_irq_routes = r;
    if (src_irq < g_ioapic_irq_count) ioapic_route_irq(...);  // ring-0 poke
    return 0;
#else
    return -1;   // host build does nothing -> untestable
#endif
}
```

RIGHT (bookkeeping is mode-agnostic; ONLY the hardware call is gated):
```c
int irq_route_add(...) {
    IRQRoute *r = mem_alloc(...); ... g_irq_routes = r;   // pure logic, testable both ways
#ifdef MYSEED_METAL
    if (src_irq < g_ioapic_irq_count) ioapic_route_irq(...);  // ring-0 poke, metal only
#endif
    return 0;
}
```
Now a host unit test (`gcc -I src/kernel interrupt_pic.c interrupt_pic_test.c`)
exercises add/remove/duplicate-remove without needing root or a real APIC.
The test must still `extern`-declare / define `ioapic_route_irq` and
`g_ioapic_irq_count` (from `interrupt_apic.h`) so the link resolves, but with
`g_ioapic_irq_count=0` the poke never runs.

## PIC port I/O (outb/inb) is NOT host-safe

`pic_remap` does `inb(PICx_DATA)` / `outb(PICx_CMD, ...)` — raw port I/O faults
( SIGSEGV ) under Linux ring-3. So `pic_remap`/`pic_eoi` are only callable in
the metal build (verified by the bare-metal boot, not by a host unit test). The
*unit-testable* part of the PIC concern is the IRQ-routing list, not the ICW
programming. Document that boundary in the test header comment.

## Minimal header, no god-header

`interrupt_pic.h` holds ONLY: PIC port macros, ICW constants, `pic_remap` /
`pic_eoi` prototypes, the `IRQRoute` opaque struct, and `irq_route_add` /
`irq_route_remove` prototypes. It includes `interrupt_io.h` (port-I/O
helpers) + `interrupt_apic.h` (for `ioapic_route_irq`, `g_ioapic_irq_count`)
so the sibling module pulls exactly what it needs.

## Makefile wiring (kernel)

KERNEL_OBJS already has a `$(KERNEL)/%.o: $(KERNEL)/%.c` pattern rule, so just
add the new object to the list:
```
KERNEL_OBJS = ... $(KERNEL)/interrupt.o $(KERNEL)/interrupt_pic.o $(KERNEL)/interrupt_apic.o ...
```
No new rule needed. The bare-metal recipe (`make kernel`) then links it
automatically; verify with `make kernel && qemu -kernel ...` that the boot
trace is unchanged.

## EOI delegation

After extraction, the original `interrupt_eoi` (in interrupt.c) delegates the
PIC half to the new module:
```c
void interrupt_eoi(uint8_t irq) {
#ifdef MYSEED_METAL
    pic_eoi(irq);                       // now in interrupt_pic.c
    if (g_ioapic_base && (irq-32) < g_ioapic_irq_count) lapic_eoi();
#else
    interrupt_count(irq);
#endif
}
```
