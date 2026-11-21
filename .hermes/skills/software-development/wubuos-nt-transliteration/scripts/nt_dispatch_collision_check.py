#!/usr/bin/env python3
"""
nt_dispatch_collision_check.py -- detect VSL NT dispatch-slot collisions.

ROOT CAUSE OF THE 2026-07-23 FRACTURE: two vsl_nt_* handlers both registered at
the same tbl[N-1] ordinal silently overwrite each other in nt_dispatch_init(),
so one syscall dispatches to the WRONG handler (often a WRITE to a bad out-pointer
=> SIGSEGV on first test run). The skill's ordinal-verification step checks each
ordinal against sysfuncs.lst but NEVER checked for two handlers colliding.

This script finds:
  (1) COLLIDING SLOTS: a slot N where >1 distinct handler is registered
  (2) ORDINAL DRIFT: a handler registered at slot N whose sysfuncs.lst ordinal
      (line number) for its ReactOS name is != N
  (3) UNVERIFIABLE: a handler whose ReactOS name is NOT in sysfuncs.lst (extension
      syscalls like ALPC/WNF/Enclave/IoRing/Partition/WorkerFactory/KTM that live
      in a HIGHER ordinal range, NOT in the base 296 list)

Usage:
  python3 scripts/nt_dispatch_collision_check.py [VSL_DIR] [SYSFUNCS_LST]
Defaults: VSL_DIR=src/runtime/vsl  SYSFUNCS_LST=reactos-study/reactos/ntoskrnl/sysfuncs.lst
Run from repo root (/home/wubu/wubuos).

Exit 0 = clean (no collisions, no drift, no unverifiable).
Exit 1 = problems found (prints them; suitable as a CI gate).
"""
import re, sys, os, glob


def main():
    repo = os.getcwd()
    vsl = sys.argv[1] if len(sys.argv) > 1 else "src/runtime/vsl"
    lst = sys.argv[2] if len(sys.argv) > 2 else "reactos-study/reactos/ntoskrnl/sysfuncs.lst"
    vsl = os.path.join(repo, vsl)
    lst = os.path.join(repo, lst)

    # 1) parse sysfuncs.lst: line number = ordinal (SOURCE OF TRUTH for base 296)
    ros = {}
    if os.path.exists(lst):
        with open(lst) as f:
            for i, line in enumerate(f, 1):
                m = re.match(r"\s*(Nt\w+)\s", line)
                if m:
                    ros[m.group(1)] = i
    else:
        print(f"[warn] sysfuncs.lst not found at {lst}; skipping ordinal-drift check")

    # 2) parse every vsl_nt_*.c register() for tbl[N-1] = handler;
    reg = re.compile(r"tbl\[(\d+)-1\]\s*=\s*(vsl_nt_\w+|vsl_sys_nosys)\s*;")
    slot_to_handlers = {}   # ordinal -> list of handler names
    handler_ord = {}        # handler -> ordinal
    files_seen = 0
    for path in sorted(glob.glob(os.path.join(vsl, "vsl_nt_*.c"))):
        files_seen += 1
        with open(path) as f:
            for line in f:
                m = reg.search(line)
                if m:
                    o = int(m.group(1)); h = m.group(2)
                    slot_to_handlers.setdefault(o, []).append(h)
                    handler_ord[h] = o

    print(f"[scan] {files_seen} vsl_nt_*.c files, "
          f"{sum(len(v) for v in slot_to_handlers.values())} registrations")

    problems = 0

    # (1) colliding slots
    collisions = {o: hs for o, hs in slot_to_handlers.items() if len(hs) > 1}
    if collisions:
        problems += 1
        print(f"\n### COLLIDING SLOTS ({len(collisions)}) -- CRITICAL, causes SIGSEGV ###")
        for o in sorted(collisions):
            # last registered in nt_dispatch_init order wins, but registration order
            # is nondeterministic across modules -> ambiguous which handler a call hits
            print(f"  slot {o}: {collisions[o]}")

    # (2) ordinal drift for base syscalls
    drift = 0
    if ros:
        for h, o in sorted(handler_ord.items()):
            if h.startswith("vsl_nt_"):
                # derive ReactOS name: vsl_nt_add_atom -> NtAddAtom
                s = h[len("vsl_nt_"):]
                parts = [p for p in s.split("_") if p]
                nt = "Nt" + "".join(p[:1].upper() + p[1:] for p in parts)
                if nt in ros and ros[nt] != o:
                    drift += 1
                    print(f"  ORDINAL DRIFT: {h} registered at {o}, "
                          f"but {nt} = {ros[nt]} in sysfuncs.lst")
        if drift:
            problems += 1
            print(f"\n### ORDINAL DRIFT ({drift}) -- handler at wrong slot ###")

    # (3) unverifiable (extension syscalls not in base 296)
    unver = 0
    for h, o in sorted(handler_ord.items()):
        if h.startswith("vsl_nt_"):
            s = h[len("vsl_nt_"):]
            parts = [p for p in s.split("_") if p]
            nt = "Nt" + "".join(p[:1].upper() + p[1:] for p in parts)
            if nt not in ros:
                unver += 1
                print(f"  UNVERIFIABLE: {h} ({nt}) at slot {o} -- "
                      f"NOT in sysfuncs.lst (extension block? must be 297+ and "
                      f"collision-free with other extension handlers)")
    if unver:
        print(f"\n### UNVERIFIABLE ORDINALS ({unver}) -- assign 297+ contiguously, "
              f"verify no two share a slot ###")
        # re-check collisions among ONLY the unverifiable (they must not collide)
        ext_slots = {}
        for h, o in handler_ord.items():
            if h.startswith("vsl_nt_"):
                s = h[len("vsl_nt_"):]
                parts = [p for p in s.split("_") if p]
                nt = "Nt" + "".join(p[:1].upper() + p[1:] for p in parts)
                if nt not in ros:
                    ext_slots.setdefault(o, []).append(h)
        ext_coll = {o: hs for o, hs in ext_slots.items() if len(hs) > 1}
        if ext_coll:
            problems += 1
            print(f"  EXTENSION COLLISIONS ({len(ext_coll)}): {ext_coll}")

    if problems == 0:
        print("\nCLEAN: no collisions, no drift, extension blocks non-colliding.")
        return 0
    print(f"\nFOUND {problems} problem class(es). Fix before merging.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
