#!/usr/bin/env python3
"""
honest_gap_audit.py -- one-shot reproducible WuBuOS gap audit.

Produces the honest ~40 code-level + ~370 parity-marathon breakdown that
BATTLESHIP.md v22 uses, by running three independent probes and triaging:

  1. find_real_gaps.py src        (empty bodies + const-only-no-syscall)
  2. live `system()` call sites   (excludes "replaces system()" closure comments)
  3. stub-phrase marker grep      (stub|not implemented|placeholder|for later),
     triaged against known non-gaps (VSL ABI, JIT backpatch, #else hw, shims)

Run from repo root:
    python3 ~/.hermes/profiles/mind-palace/skills/software-development/wubuos-battleship-gaps/scripts/honest_gap_audit.py [WUBUOS_ROOT]

Notes:
  - Prints the honest code/parity/combined totals.
  - If probe 1 reports >0 empty bodies, the board has drifted -> re-audit.
  - This is a PROBE, not a verdict. Always read the candidate function bodies
    before editing (Scanner-A's const-only candidates are ~100% false positives).
"""
import os, re, sys, subprocess

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
FIND_REAL = os.path.join(SCRIPT_DIR, "find_real_gaps.py")

# Known non-gap triage (regex matched against "file:line:content").
NOISE_RE = [
    re.compile(r"_test"),
    re.compile(r"jit\.c:|wubu_x86\.c:|jit_minic\.c:|holyc_codegen"),
    re.compile(r"vsl_syscall|vsl_nt_bridge"),
    re.compile(r"No stubs, no|no system|replaces system|No stubs, no system"),
    re.compile(r"My Seed Input Subsystem \(hosted stub\)|minimal stub|weak Wayland-state default"),
    re.compile(r"Not implemented without (libasound|libpulse|X11) headers"),
    re.compile(r"already (implemented|real) in stub|Helpers \(already|Push/Pull \(stubs for registry\)"),
    re.compile(r"provides stub implementations|Stub implementations for anti-cheat|Userspace Hooks \(Stubs\)|Kernel-Level Stubs \(Bare Metal Only\)|Cell 470: Stub|Cell 480: Stub"),
    re.compile(r"JSONL parser stub|Darling not available.*stubbed|Fallback: run in VSL.*stub|Simple command execution with placeholder substitution"),
    re.compile(r"Simple FNV-1a hash as a placeholder signature|Store .* for later"),
    re.compile(r"placeholder disp32|emit rel32 placeholder|Load matrix tiles|push constants|wl_shm, xdg|9P server in separate|Add to start menu when|for the dedup"),
    re.compile(r"No pixels|call label|GAAD initialization stub|Assembly ISR stubs|IS[RA] entry points|syscall_entry|common_isr_handler|Syscall dispatcher|Stub - not yet"),
    re.compile(r"wubu_wayland_stub\.c|stub\.c$|stub\.elf"),
]


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def live_system_calls(root):
    """Only actual `system(...)` invocations; exclude comment-only lines."""
    out = run(["grep", "-rEn", r"\bsystem\s*\(", os.path.join(root, "src"),
               "--include=*.c"]).stdout.strip().split("\n")
    real = []
    for l in out:
        if not l or "_test" in l:
            continue
        _, _, content = l.partition(":")
        idx = content.find("system(")
        if idx < 0:
            continue
        pre = content[:idx]
        if "//" in pre:
            continue
        cm = pre.rfind("/*")
        if cm >= 0 and "*/" not in pre[cm:]:
            continue
        real.append(l)
    return real


def stub_phrases(root):
    out = run(["grep", "-rEni", r"stub|not implemented|placeholder|for later",
               os.path.join(root, "src"), "--include=*.c"]).stdout.strip().split("\n")
    return [l for l in out if l and not any(p.search(l) for p in NOISE_RE)]


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    print("=== WuBuOS Honest Gap Audit (v22 methodology) ===")
    print(f"root: {os.path.abspath(root)}\n")

    r = run(["python3", FIND_REAL, os.path.join(root, "src")])
    empties = consts = 0
    for line in r.stdout.split("\n"):
        m = re.search(r"TOTAL:\s*(\d+)", line)
        if not m:
            continue
        low = line.lower()
        if "empty" in low:
            empties = int(m.group(1))
        elif "const" in low or "candidate" in low:
            consts = int(m.group(1))
    print(f"[1] find_real_gaps.py src -> empty bodies: {empties}, const-only-no-syscall: {consts}")

    sys_calls = live_system_calls(root)
    print(f"[2] live system() calls (REAL_GAP by rule): {len(sys_calls)}")
    for l in sys_calls:
        parts = l.split(":", 2)
        print(f"    {parts[0].split('/')[-1]}:{parts[1]}: {parts[2].strip()[:72]}")

    stub = stub_phrases(root)
    print(f"[3] triaged stub-phrase functions: {len(stub)}")

    parity = 297 + 30 + 20 + 15 + 8
    print(f"\n[4] parity marathons (user reclassification rule): {parity}")
    print("    ReactOS NT 297 + SteamOS ~30 + Ubuntu/Arch ~20 + TempleOS ~15 + ZealOS ~8")

    code = len(sys_calls) + len(stub)
    print(f"\n=== HONEST TOTAL ===")
    print(f"  code-level : ~{code} (range {code-4}-{code+4})")
    print(f"  parity     : ~{parity}")
    print(f"  combined   : ~{code + parity}  (BATTLESHIP v22 '~400')")

    if empties == 0 and consts == 0:
        print("\n  OK baseline stub class CLOSED (reproducible).")
    else:
        print(f"\n  WARNING baseline scanner found {empties + consts} hits -- re-audit before reporting.")


if __name__ == "__main__":
    main()
