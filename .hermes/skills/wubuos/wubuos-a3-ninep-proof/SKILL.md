---
name: wubuos-a3-ninep-proof
description: A3 on-kernel 9P proof — fetch module over COM2 and run it.
---
# WuBuOS A3 — booted kernel fetches a module over 9P and runs it

GAP_ROADMAP A3: the hardware-gated proof that the WuBuOS AGI kernel, booted
under WuBuFW/QEMU, opens a 9P session to a HOST-exported /n server, walks
`/apps/<mod>`, reads the bytes, runs them through `wubu_zx_run`, and prints a
real `RESULT: PASS -- ... entry=N` on the COM1 serial log. All the hosted
pieces exist (w9pc = kernel-clean client, wubu_zx_run/wubu_zxreg = loader,
styxfs_serve = server); A3 is wiring them onto the booted kernel via a UART.

## The transport: 9P-over-a-dedicated-COM2 (architectural decision)

COM1 carries the klog/debug stream. Do NOT multiplex 9P onto COM1 — dedicate
COM2 (0x2F8) to the /n channel so frames and log text never interleave. Poll
COM2 (no IRQ): init 115200 8N1 + FIFO, bounded TX/RX polls (never busy-forever
— a quiet host must not hang the boot).

Framing is the key contract: `w9_tx()` passes `*rsplen=0` and does NOT hand the
transport the out-buffer capacity, so a transport must cap the reply by the
size of the buffer IT allocated (c->out), never by the incoming `*rsplen`.
Make the out buffer >= msize + header (a read reply carrying N data bytes is
~11+N; use 16KB). This exact trap produced a fake "server replied empty" — the
reply was fine; the transport had clamped n to 0.

## Host side: QEMU socket roles (gotcha)

`agi-9p-server.c` (host) is the LISTENER (bind+listen+accept) and serves each
connection's length-framed 9P through the SAME `styxfs_serve` the hosted test
uses. QEMU must therefore be the socket CLIENT on COM2:
`-serial unix:<path>` (NO `server=on`). Start the server BEFORE qemu, then qemu
connects. Both directions are [u32 LE length][9P msg]; styxfs_serve still sees
the raw message (content after the outer length). Always frame_send whatever
styxfs_serve produced even when rc!=0; do NOT send a 0-length outer frame
(client reads header 0 and fails), and Rread replies must make olen nonzero.

## The module (mkmod.c) — self-contained PE, no imports

`wubu_zx_run` accepts a PE32 (magic 0x10B) with a single `.text` section and NO
import directory; imports are optional (`wubu_pe_snap_iat` returns 0 with none),
and it runs at any base (`mov eax,imm; ret;` has no absolute addrs to fix).
`tools/mkmod.c` emits exactly the layout the loader already parses (mirror the
hand-built PE in `src/kernel/test/w9pc_test.c`, minus .idata). Section table at
opt+optsize; entry = image_base + entry_rva.

## On-kernel IMPORT/call-back (the strength-gap a Triple-DA exposes)

A constant-returning module proves the loader but not the on-kernel
symbol-registry path. To prove a real /n app can call into the OS: make the
module import a kernel export and call it back. `mkmod` has an import mode
(`mkmod <out> <const> <dll> <name>`) emitting a 2-section PE32 (.text + .idata)
whose entry is `mov ebx,<const>; call [rip+disp->IAT]; add eax,ebx; ret` -
the result is (kernel_export() + const). Kernel side: register the export with
wubu_modsym_register (e.g. NTOSKRNL.EXE!U9_MAGIC -> a real kernel fn returning
6) BEFORE wubu_zx_run, and pass resolve=NULL (zx defaults to wubu_modsym_resolve
-> wabu_pe_snap_iat patches the module's IAT slot with the kernel fn's address;
call then jumps into kernel text, same ring-0 address space). Host-verify first
with a variant that registers two export values and checks the result flips
(modify the export -> a DIFFERENT result proves the call is live, not a
hardcoded constant). Negative on-kernel: a failed snap -> WUBU_ZX_ERR_IAT ->
'A3: RESULT: FAIL', so a broken import path can't fake the PASS.

PITFALL -- rip-relative call disp offset: the import entry has a 5-byte
`mov ebx` prefix BEFORE the 6-byte `call [rip+disp]`, so the call sits at
ENTRY_RVA+5 and rip-after-call is ENTRY_RVA+11. disp = IAT_RVA - (ENTRY_RVA
+11), NOT (ENTRY_RVA+6). Off-by-five lands the target 5 bytes past the IAT
slot -> the module reads garbage and segfaults (host crash, not a QEMU-only
failure). The w9pc_test formula (no mov prefix) is +6; the import version needs
+11. Validate the module on host with a plain loader run before QEMU.

## A4: SESSION-LAUNCH via the module registry (P3-on-kernel)

To go from "runs a blob" to "launches an app that persists", load through the
module registry, NOT a raw wubu_zx_run. `wubu_zxreg_load_bytes(ops, bytes, n,
path, base, resolve, out)` is the kernel-clean primitive: register + run an
already-fetched image with SHA-256 dedup, refcount, and a cached entry result.
It is the on-kernel twin of the hosted `wubu_applaunch_as_session_launcher`
contract; `wubu_zxreg_load(path)` (hosted) delegates to it. The old kernel path
of `wubu_zxreg_load` was a dead `WUBU_ZX_ERR_MAP` -- that is the A4 gap.

Kernel flow: 9P-fetch the bytes (wubu_n9) -> `wubu_zxreg_load_bytes` (register
+ run) -> a SECOND identical load must dedup to the SAME registry row and
re-serve the cached entry result (entry runs once) -> one unload leaves the app
registered at ref=1 (a live session-resident app). Report registered/ref/dedup.

PITFALL -- the -nostdlib kernel lacks `memcmp` and the fortify `__strncpy_chk`
redirect (only part of the `*_chk` set exists in libc.c). Any kernel object
that starts using strncpy/memcmp after your change will fail the kernel link
with those two undefined refs. Add `memcmp` (byte-loop) and `__strncpy_chk`
(-> strncpy) to `src/kernel/libc.c` following the existing `__memcpy_chk` stub
pattern -- both belong to the kernel's bare-metal libc, and hosted tests use
glibc so they're unaffected. This bit me the moment wubu_zxreg gained a real
kernel load path.

## Kernel map: do NOT map at 0x400000 (heap collision)

The demo module declares image_base 0x00400000, but the kernel's phys heap
grows from 0x400000. The `wubu_zx_ops.map` must allocate phys pages
(`wubu_vmm_alloc_pages`) and map them at a fixed HIGH-half VA (use
0xffffffff90000000) with flags 3 (RW+present; no NX in this kernel so it
executes), RETURNING that VA. Do it after wubu_vmm_init. Zero the span (zx
wants a zeroed image).

## Wiring
- Add `wubu_9pc.o` + `wubu_n9.o` to `mk/objects.mk` KERNEL_OBJS (after
  wubu_zxreg.o).
- Call `wubu_n9_boot()` in `metal_main.c` right after the "AGI kernel booted"
  klog (COM2 is polled, independent of COM1's IRQ init).
- Harness `src/firmware/run-agi9p.sh`: build kernel+firmware+chainloader+ESP
  EXACTLY like run-agi.sh, then build server+module, start server (listener),
  boot qemu with `-serial stdio` (COM1) + `-serial unix:...` (COM2), drive
  `exit` on COM1, grep for `A4: RESULT: PASS` + `registered=1 ref=1 dedup=1`
  + `entry=55` + `AGI kernel booted`. Post-exit sleep 16s (loader+boot+span
  flood).

## Pitfalls (all cost a debug cycle)
- mkesp ESP path quoting: single backslash `'\EFI\BOOT\BOOTX64.EFI'` (ONE
  `\`). Double (`'\\EFI...'`) makes mkesp create an empty-named intermediate
  dir -> firmware says "no bootable EFI application found" and the kernel never
  boots. Write the harness with a raw file, not a JSON-escaped heredoc, or
you'll double it.
- w9_transport capacity trap (above): never cap by `*rsplen`.
- QEMU COM2 socket: server=LISTENER, qemu=CLIENT; reverse = connect refused.
- Validate module+server+client+loader ON HOST first (checkmod: zx_run the
  mkmod output -> 55; check9p: framed fetch over unix socket -> run -> 55)
  before booting qemu — fix framing bugs on localhost, not under the QEMU window.
- Validate the published module file really exists on disk — a rejected
  `&`-foreground command silently skipped mkdir, so the walk fabricated qids
  and the read's open() found nothing, pinning blame on the server instead.
- The hook runs once, never blocks the boot (bounded polls), and leaks a few
  vmm pages at boot — acceptable for a one-shot proof.
