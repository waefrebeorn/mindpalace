# Bare-Metal Boot Debugging via QEMU QMP

When the WuBuOS `kernel.elf` boot stalls (serial trace dies mid-way, e.g.
`MPGCE` with no `W`/`X`/`J`), you need ground truth on guest state. The serial
trace is the primary signal, but when it's silent you must inspect live CPU/mem.
**QMP (JSON) over a unix socket is the only reliable channel in this environment.**

## Reliable recipe (Python client)

```python
import socket, json, time

def qmp(cmd, args=None):
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.connect('/tmp/qmp.sock'); s.settimeout(3); s.recv(4096)
    def send(o):
        s.sendall((json.dumps(o)+'\n').encode()); time.sleep(0.2)
        buf=b''; resp=None
        while True:
            try: d=s.recv(4096)
            except socket.timeout: break
            if not d: break
            buf+=d
            for ln in buf.split(b'\n'):
                if ln.strip():
                    try:
                        o=json.loads(ln)
                        if 'return' in o or 'error' in o: resp=o
                    except: pass
            if resp: break
        return resp
    send({"execute":"qmp_capabilities"})
    obj={"execute":cmd}
    if args: obj["arguments"]=args
    r=send(obj); s.close(); return r

def hmc(c):  # human-monitor-command passthrough (reliable, no echo bug)
    return (qmp("human-monitor-command",{"command-line":c}) or {}).get("return","")

# Boot the guest with: qemu-system-x86_64 -kernel src/kernel/kernel.elf \
#   -serial file:/tmp/kg.log -display none -m 128 -no-reboot -S -qmp unix:/tmp/qmp.sock,server,nowait
qmp("cont"); time.sleep(1.0)
print(hmc("info registers"))          # EIP/EBX/CR3/EFER — smoking gun
print(hmc("x /4xw 0x300000"))         # PML4 (page tables @ base+0x200000)
qmp("pmemsave", {"val":0x300000,"size":0x6000,"filename":"/tmp/pt.bin"})  # dump to file
```

Then parse `/tmp/pt.bin` with `struct.unpack_from('<Q', data, off)`.

## Channels to AVOID (proven flaky here)
- **gdbstub (`-s`)**: `int3`/breakpoints triple-fault because the guest has no
  IDT yet; `stepi` round-trips to GDB are so slow that 120–350 steps exceed
  any reasonable timeout; often reports "target running" / can't break.
- **HMP socket monitor (`-monitor unix:...`)**: it *echoes every keystroke*, so
  typed commands get interleaved with echoed garbage → `invalid char 't' in
  expression` and corrupted `pmemsave` paths. Never use it for input.
- **`pmemsave` via HMP**: corrupted by the echo bug. Use QMP `pmemsave` instead
  (clean JSON args).

## The multiboot `entry_addr` quirk (root cause of the 2026-07-16 saga)
`crt0.S` `mb1_hdr` `entry_addr` MUST equal `load_addr + sizeof(mb1_hdr)`
(= `0x100020`), NOT the ELF-VMA-derived `_start` address (the loader placed
`mb1_hdr` at `load_addr 0x100000` and `_start` immediately after it). If wrong,
the loader jumps **into the middle of `_start`**, skipping
`movl $0x100000,%esi; movl %esi,%ebx` → `EBX` stays the loader's multiboot info
ptr (`~0x9500`) → page tables built at a garbage base → **all zeros** → triple
fault at paging-on. Symptom: serial `MPGCE`, QMP `info registers` shows
`EBX=0x9500, CR3=0x9500` (should be `0x300000`). Fix: set `entry_addr=0x100020`.

## Triage order when boot dies
1. `cat /tmp/kg.log` — which markers printed? (`M P G C E W X Y J K S I Q Z A..`)
2. If dies at/after `E`/`W` (paging on), QMP `info registers` + dump
   `0x300000` (PML4) — are tables zero? If zero, check `EBX`/`CR3` and the
   `entry_addr` quirk above.
3. If `G` prints but tables zero → registers never set → entry-point offset bug.

## Expected page-table layout (base = PML4 phys = 0x300000)
- PML4[0]      = 0x301003  (→ PDP_ident @ +0x1000)
- PDP_ident[0] = 0x302003  (→ PD_ident  @ +0x2000)
- PD_ident[0]  = 0x000083, [1] = 0x200083 (2MB identity, 0..1GB)
- PDP_high[510]= 0x304003  (→ PD_high   @ +0x4000)
- PD_high[0]   = 0x305003  (→ PT_high   @ +0x5000)
- PT_high[256] = 0x100003  (hi-half VA → image PA)
