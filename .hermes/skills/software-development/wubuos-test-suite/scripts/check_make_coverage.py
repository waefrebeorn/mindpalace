#!/usr/bin/env python3
"""Report test targets that exist but are UNREACHABLE from the aggregate target.

A repo can declare hundreds of `test_*` rules while `make test` depends on a
hand-written handful of tier targets. Everything outside that closure never runs
in the gate, so it rots silently.

Usage:
  python3 check_make_coverage.py [makefile...] [--aggregate test] [--quiet]

Exits 1 when any declared test target is unreachable (wire them or say why).
"""
from __future__ import annotations

import argparse
import re
import sys

RULE = re.compile(r'^([A-Za-z0-9_.$()/%-]+):\s*(.*)$')


def parse(paths: list[str]) -> dict[str, list[str]]:
    deps: dict[str, list[str]] = {}
    for path in paths:
        try:
            text = open(path, encoding='utf-8', errors='replace').read()
        except OSError:
            continue
        for line in text.splitlines():
            if line.startswith('\t') or line.startswith('#'):
                continue
            m = RULE.match(line)
            if not m:
                continue
            target, rest = m.group(1), m.group(2).split('#')[0]
            if '$' in target:
                continue
            deps.setdefault(target, []).extend(re.findall(r'[A-Za-z0-9_.-]+', rest))
    return deps


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('makefiles', nargs='*', default=['Makefile'])
    ap.add_argument('--aggregate', default='test')
    ap.add_argument('--quiet', action='store_true')
    a = ap.parse_args()

    deps = parse(a.makefiles)
    tests = {t for t in deps if t.startswith(('test_', 'check_'))}
    seen: set[str] = set()
    stack = [a.aggregate]
    while stack:
        t = stack.pop()
        if t in seen:
            continue
        seen.add(t)
        stack.extend(d for d in deps.get(t, []) if d in deps)

    unreachable = sorted(tests - seen)
    print(f'declared test targets: {len(tests)}  reachable from {a.aggregate!r}: '
          f'{len(tests & seen)}  unreachable: {len(unreachable)}')
    if not a.quiet and unreachable:
        for t in unreachable[:40]:
            print('  ', t)
        if len(unreachable) > 40:
            print(f'   ... {len(unreachable) - 40} more')
    if unreachable:
        print('\nFix: generate an ALL_TESTS list and depend on it, or add the target to a tier.')
    return 0 if not unreachable else 1


if __name__ == '__main__':
    sys.exit(main())
