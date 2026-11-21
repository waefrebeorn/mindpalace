#!/usr/bin/env python3
"""index_project.py -- SHA-256 index of a git repo's tracked SOURCE files.

Generated test artifacts and binaries are excluded so the index stays usable.
Usage: python tools/index_project.py --root REPO --out FILE
"""
import argparse, concurrent.futures, hashlib, os, subprocess, sys

BIN_EXT = {".o", ".obj", ".a", ".lib", ".so", ".dll", ".dylib", ".exe",
           ".pyc", ".pdb", ".pyd", ".class", ".jar", ".zip", ".gz",
           ".tar", ".7z", ".png", ".jpg", ".jpeg", ".gif", ".ico",
           ".woff", ".woff2", ".ttf", ".eot", ".pdf", ".db", ".sqlite"}
DEFAULT_EXCLUDES = ["tests/watercup/gates/", ".testbin/", "tests/watercup/build/",
                    "__pycache__/", "node_modules/", ".git/"]


def sha12(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:12]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--exclude", action="append", default=[])
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--git", default="git",
                    help="git executable (native path if launched from Python)")
    args = ap.parse_args()
    root = os.path.abspath(args.root)
    ex = DEFAULT_EXCLUDES + args.exclude

    raw = subprocess.run([args.git, "ls-files", "-z"], cwd=root,
                         capture_output=True, check=True).stdout
    paths = [p.decode("utf-8", "replace") for p in raw.split(b"\0") if p]
    keep = []
    for p in paths:
        if any(e.rstrip("/") + "/" in p or p.startswith(e.rstrip("/") + "/")
               for e in ex):
            continue
        if os.path.splitext(p)[1].lower() in BIN_EXT:
            continue
        if os.path.isfile(os.path.join(root, p)):
            keep.append(p)

    def work(p):
        full = os.path.join(root, p)
        try:
            return p, sha12(full), os.path.getsize(full)
        except OSError:
            return p, "UNREADABLE", 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        rows = list(pool.map(work, keep))

    total = sum(r[2] for r in rows)
    lines = ["# Project File Index", "",
             f"Repository: `{root}`", f"Files (tracked source): {len(rows)}",
             f"Bytes: {total}", "",
             "Generated gates, build objects, binaries and caches are excluded.",
             "Devil's Advocate findings: `DEVILS_ADVOCATE.md`, `STEPLOG.md`.", ""]
    lines += [f"- `{p}` [{d}]" for p, d, _ in rows]
    out = os.path.abspath(args.out)
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    print(f"project index: {len(rows)} files / {total} bytes -> {out} "
          f"(from {len(paths)} tracked)")


if __name__ == "__main__":
    sys.exit(main())
