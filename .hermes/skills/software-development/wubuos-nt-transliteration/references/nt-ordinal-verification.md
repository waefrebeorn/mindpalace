# NT Syscall Ordinal Verification (WuBuOS E1)

## The rule
In `reactos-study/reactos/ntoskrnl/sysfuncs.lst`, the **line number is the 1-based
NT syscall ordinal**. There is NO separate number column — the name + arity are all
that's on the line. So:
```bash
grep -n "NtDelayExecution" reactos-study/reactos/ntoskrnl/sysfuncs.lst
# 62: NtDelayExecution 2    => ordinal 62 (0x3E)
```
The `NT_SYSCALL_NT*` macros in `src/runtime/vsl/vsl_nt_bridge.h` AND the
`g_nt_dispatch[<N>-1]` indices in `vsl_syscall_nt.c` MUST equal this ordinal.
`sysfuncs.lst` is the AUTHORITATIVE source — **NOT the header macro**. The macros
themselves drift from sysfuncs.lst (Batch 3 shipped four wrong macros: 0x25/0x27/0x7F/
0xC1 vs the correct 0x3E/0x26/0x79/0xC0). Always derive the ordinal from sysfuncs.lst
first, then fix the macro to match, then wire the dispatch index to the same number.
Never hand-derive ordinals from memory.

## Bulk verification (the BLITZ method — proven 66→88 in one push)
When closing many gaps at once, verify ALL candidate ordinals before writing code:
```python
import re, glob
sysf = open("reactos-study/reactos/ntoskrnl/sysfuncs.lst").read().splitlines()
syscalls = {m.group(1): i+1 for i,l in enumerate(sysf,1)
            if (m := re.match(r"^(Nt\w+)\s+(\d+)", l.strip()))}
wired = set()
for f in glob.glob("src/runtime/vsl/vsl_nt_*.c"):
    wired |= {int(x) for x in re.findall(r"tbl\[(\d+)-1\]", open(f).read())}
for c in candidates:
    print(c, syscalls.get(c), "WIRED" if syscalls.get(c) in wired else "")
```
Skip any already wired. Skip names NOT found in sysfuncs.lst (don't invent). Skip
syscalls that can't be done honestly in one push (e.g. `NtGetContextThread` = real
register capture, `NtDeviceIoControlFile` = 10-arg device ioctl).

## Why this matters (real incident)
Batch 3 was committed with off-by-one header macros. The test "passed 63/0" only
because it dispatched against the SAME wrong numbers — internally consistent but
wrong vs the real NT ABI. A real ReactOS `.exe` issuing the correct ordinal (e.g.
#62 for `NtDelayExecution`) would have hit `vsl_nt_nosys`. Corrected ordinals
(hex = decimal):
```
NtDelayExecution   0x3E = 62   (was wrongly 0x25)
NtCreateEvent      0x26 = 38   (was wrongly 0x27)
NtOpenEvent        0x79 = 121  (was wrongly 0x7F)
NtReadFile         0xC0 = 192  (was wrongly 0xC1)
```
All four were fixed against `sysfuncs.lst`; re-run reported 74/0 green. **Always
cross-check BOTH the header macro AND the dispatch index before committing, and treat
sysfuncs.lst as the source of truth even when the macro disagrees.**

## Current Wired State (2026-07-21): 296/297

### Wired Ordinals (296 of 297)
All ordinals 1-297 EXCEPT:
- **188**: `NtQueryVolumeInformationFile` — registered in `vsl_nt_io.c` but handler not implemented
- **279**: `NtVdmControl` — registered in `vsl_nt_misc.c` but handler not implemented

### Verification Command
```bash
python3 -c "
import re, glob
t = set()
for f in glob.glob('src/runtime/vsl/vsl_nt_*.c'):
    with open(f) as fp:
        t.update(int(x) for x in re.findall(r'tbl\[(\d+)-1\]', fp.read()))
print(f'{len(t)} of 297')
if len(t) <= 297:
    missing = [i for i in range(1, 298) if i not in t]
    print('Missing:', missing)
"
```

## Corrected Ordinals (from sysfuncs.lst line numbers)
Key corrections from Batch 3 and Blitz:
| Syscall | Macro Hex | Correct Ordinal |
|---------|-----------|-----------------|
| NtCreateProcess | 0x0030 | 50 |
| NtCreateProcessEx | 0x0031 | 51 |
| NtCreateThread | 0x0036 | 56 |
| NtUnmapViewOfSection | — | 278 |
| NtVdmControl | — | 279 |

## Verification Protocol
```bash
# 1. Get wired ordinals
grep -hoE 'tbl\[[0-9]+-1\]' src/runtime/vsl/vsl_nt_*.c | sed 's/tbl\[\([0-9]*\)-1\]/\1/' | sort -n | uniq > wired.txt

# 2. Cross-check against sysfuncs.lst
python3 -c "
import sys
with open('reactos-study/reactos/ntoskrnl/sysfuncs.lst') as f:
    sysfuncs = [line.strip().split()[0] for line in f if line.strip()]
wired = set(int(x) for x in open('wired.txt').read().split())
missing = [i for i in range(1, 298) if i not in wired]
for m in missing:
    print(f'{m}: {sysfuncs[m-1]}')
"
```

## Missing Ordinal Details
| Ordinal | Syscall | Status |
|---------|---------|--------|
| 188 | NtQueryVolumeInformationFile | Registered, not implemented |
| 279 | NtVdmControl | Registered, not implemented |

## Next Steps
1. Implement `NtQueryVolumeInformationFile` in `vsl_nt_io.c`
2. Implement `NtVdmControl` in `vsl_nt_misc.c`
3. Verify 297/297 wired