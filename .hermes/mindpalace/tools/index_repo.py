#!/usr/bin/env python3
"""index_repo.py -- build the Mind Palace INDEX.md with SHA-256 provenance.

Usage: python tools/index_repo.py [--root DIR] [--write] [--out FILE]
"""
import argparse, hashlib, os, sys

DEFAULT_SKIP_DIRS = {
    ".git", ".hg", ".svn", "__pycache__", "node_modules", ".testbin",
    ".ccache", ".venv", "venv", "dist", "build-out",
}
DEFAULT_SKIP_FILES = {".DS_Store", "thumbs.db"}


def sha12(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:12]


def scan(root, skip_dirs, skip_files, max_bytes):
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in skip_dirs)
        for name in sorted(filenames):
            if name in skip_files:
                continue
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            try:
                size = os.path.getsize(full)
                digest = sha12(full) if size <= max_bytes else "SKIPPED_LARGE"
            except OSError as exc:
                print(f"WARN unreadable {rel}: {exc}", file=sys.stderr)
                continue
            out.append((rel, digest, size))
    return out


def main():
    ap = argparse.ArgumentParser()
    here = os.path.dirname(os.path.abspath(__file__))
    ap.add_argument("--root", default=os.path.dirname(here))
    ap.add_argument("--out", default=None)
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--skip-dir", action="append", default=[])
    ap.add_argument("--max-bytes", type=int, default=64 * 1024 * 1024)
    args = ap.parse_args()

    root = os.path.abspath(args.root)
    skip = DEFAULT_SKIP_DIRS | set(args.skip_dir)
    rows = scan(root, skip, DEFAULT_SKIP_FILES, args.max_bytes)
    total_bytes = sum(r[2] for r in rows)

    lines = ["# Mind Palace Index", "", f"Files: {len(rows)}",
             f"Bytes: {total_bytes}", ""]
    lines += [f"- `{rel}` [{digest}]" for rel, digest, _ in rows]
    text = "\n".join(lines) + "\n"

    out = args.out or os.path.join(root, "INDEX.md")
    if args.write:
        with open(out, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        print(f"INDEX written: {out}")
    else:
        sys.stdout.write(text)
    print(f"Indexed {len(rows)} files / {total_bytes} bytes under {root}")


if __name__ == "__main__":
    main()
