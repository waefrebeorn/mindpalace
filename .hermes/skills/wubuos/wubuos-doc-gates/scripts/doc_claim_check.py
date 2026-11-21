#!/usr/bin/env python3
"""doc_claim_check.py -- audit `make <target>` claims in WuBuOS docs.

The front-door doc gate (test_docs) checks that every PATH a guarded doc names
exists. It does not check that a `make <target>` command the doc tells the
reader to run is a real target, so a doc can print a build command that has no
rule. This script is the audit that precedes wiring that check into the gate.

Usage:
    python3 scripts/doc_claim_check.py [doc ...]

With no arguments it scans the guarded docs (the set test_docs covers).
Set WUBUOS_ROOT to the checkout if it is not /home/wubu/wubuos.

Exit code is 1 when any claim does not resolve, so it can gate a build.
"""
import glob
import os
import re
import sys

DEFAULT_ROOT = "/home/wubu/wubuos"
GUARDED = [
    "README.md",
    "docs/MIND_PALACE.md",
    "docs/SAGA.md",
    "docs/MODULES.md",
    "docs/ECOSYSTEM.md",
    "docs/BUILDING.md",
    "TESTING.md",
    "src/spells/README.md",
]

# A real target line in Makefile / mk/*.mk: `name:` at column 0.
# Pattern rules (`%.o:`) and .PHONY are skipped by the first-character class.
TARGET_RE = re.compile(r"^[a-zA-Z0-9_][a-zA-Z0-9_./-]*\s*:")
# Only backticked `make X` is an explicit command claim; bare prose is not.
MAKE_RE = re.compile(r"`make\s+([a-zA-Z0-9_][a-zA-Z0-9_./-]*)`")


def build_targets(root):
    targets = set()
    files = ["Makefile"] + sorted(glob.glob(os.path.join(root, "mk", "*.mk")))
    for path in files:
        if not os.path.exists(path):
            continue
        with open(path, errors="ignore") as fh:
            for line in fh:
                if TARGET_RE.match(line):
                    targets.add(line.split(":", 1)[0].strip())
    return targets


def is_prose(token):
    """Filter non-targets: `make CC=gcc`, `make test-module`, `make test_...`."""
    if token.endswith("_") or token.endswith(".") or "..." in token:
        return True
    if token.isalpha() and token.isupper():
        return True  # ALL-CAPS variable assignment (CC, CXX, CFLAGS)
    return False


def main():
    root = os.environ.get("WUBUOS_ROOT", DEFAULT_ROOT)
    if not os.path.isdir(root):
        root = os.getcwd()
    os.chdir(root)

    docs = sys.argv[1:] or GUARDED
    targets = build_targets(root)
    missing = []
    for doc in docs:
        if not os.path.exists(doc):
            print("  (skip, absent: %s)" % doc)
            continue
        with open(doc, errors="ignore") as fh:
            for lineno, line in enumerate(fh, 1):
                for match in MAKE_RE.finditer(line):
                    token = match.group(1)
                    if is_prose(token):
                        continue
                    if token not in targets:
                        missing.append((doc, lineno, token))

    if not missing:
        print("OK: every `make <target>` claim in the scanned docs resolves.")
        return 0
    print("%d `make` claim(s) with no such target:" % len(missing))
    for doc, lineno, token in missing:
        print("  %s:%d: make %s" % (doc, lineno, token))
    return 1


if __name__ == "__main__":
    sys.exit(main())
