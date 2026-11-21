#!/usr/bin/env python3
"""verify_mindpalace.py -- hard gate for the palace: paths, SHAs, skills."""
import argparse, hashlib, os, re, sys

REQUIRED = [
    "README.md", "INDEX.md", "DEVILS_ADVOCATE.md", "ROADMAP.md",
    "PRESTIGE.md", "slate.md", "STEPLOG.md", "skills/mp/SKILL.md",
    "tools/index_repo.py", "tools/verify_mindpalace.py",
    "tools/review_1000.py", "commands/mp", "docs/mind-palace.md",
    "docs/stage-system.md", "docs/devil-advocate.md", "docs/slate.md",
    "docs/phase-plane.md", "docs/review-1000.md",
]
PATH_RE = re.compile(r"`([.A-Za-z0-9_][.A-Za-z0-9_./-]*/[.A-Za-z0-9_./-]+)`")
EXTERNAL = (".hermes/memory", "http", "git@", "C:")
PLACEHOLDER = ("path/to/", "<", "{", "N/S", "path/to/file")
PREFIX = ".hermes/mindpalace/"


def resolve(token, doc_dir, root):
    """Resolve a doc path: relative to doc, palace root, or project-prefixed."""
    t = token.rstrip("/.,;:")
    if t.startswith(EXTERNAL) or t.startswith(PLACEHOLDER):
        return True
    if t == ".hermes/mindpalace":
        return True
    cands = [os.path.join(doc_dir, t), os.path.join(root, t),
             os.path.join(root, "..", "..", t)]  # <repo>/.hermes/mindpalace -> repo root
    if t.startswith(PREFIX):
        cands.append(os.path.join(root, t[len(PREFIX):]))
    return any(os.path.exists(c) for c in cands)
SHA_RE = re.compile(r"^- `([^`]+)` \[([0-9a-f]{12})\]$", re.M)


def sha12(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:12]


def main():
    ap = argparse.ArgumentParser()
    here = os.path.dirname(os.path.abspath(__file__))
    ap.add_argument("--root", default=os.path.dirname(here))
    ap.add_argument("--strict-paths", action="store_true")
    args = ap.parse_args()
    root = os.path.abspath(args.root)
    errors, checked = [], 0

    for rel in REQUIRED:
        checked += 1
        if not os.path.exists(os.path.join(root, rel)):
            errors.append(f"MISSING required file: {rel}")

    # every path-like token in docs must exist
    dead = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in (".git", ".locks")]
        for name in filenames:
            if not name.endswith(".md"):
                continue
            p = os.path.join(dirpath, name)
            try:
                text = open(p, encoding="utf-8", errors="replace").read()
            except OSError:
                continue
            doc_dir = os.path.dirname(p)
            for token in PATH_RE.findall(text):
                t = token.rstrip("/.,;:")
                checked += 1
                if not resolve(t, doc_dir, root):
                    dead.append((os.path.relpath(p, root).replace(os.sep, "/"), t))

    # INDEX SHA provenance
    idx = os.path.join(root, "INDEX.md")
    sha_checked = sha_bad = 0
    if os.path.exists(idx):
        for rel, want in SHA_RE.findall(open(idx, encoding="utf-8", errors="replace").read()):
            if rel == "INDEX.md":
                continue  # self-referential: index cannot hash itself
            p = os.path.join(root, rel)
            sha_checked += 1
            if not os.path.exists(p):
                errors.append(f"INDEX dead path: {rel}")
            elif sha12(p) != want:
                sha_bad += 1
                if args.strict_paths:
                    errors.append(f"INDEX stale SHA: {rel}")

    # skill frontmatter contract
    skills = []
    sd = os.path.join(root, "skills")
    if os.path.isdir(sd):
        for dirpath, dirnames, filenames in os.walk(sd):
            if "SKILL.md" in filenames:
                p = os.path.join(dirpath, "SKILL.md")
                skills.append(os.path.relpath(dirpath, sd).replace(os.sep, "/"))
                txt = open(p, encoding="utf-8", errors="replace").read()
                m = re.search(r'^description:\s*(.+)$', txt, re.M)
                if not m:
                    errors.append(f"SKILL missing description: {p}")
                elif len(m.group(1).strip()) > 60:
                    errors.append(f"SKILL description >60 chars: {p}")
                if "## When to Use" not in txt:
                    errors.append(f"SKILL missing When to Use: {p}")

    print(f"verify_mindpalace root={root}")
    print(f"required files: {len(REQUIRED)} | path tokens checked: {checked - len(REQUIRED)}")
    print(f"dead doc paths: {len(dead)}")
    for src, t in dead[:20]:
        print(f"  DEAD {src} -> {t}")
    if dead:
        errors.append(f"{len(dead)} dead doc path(s)")
    print(f"INDEX SHA entries: {sha_checked} | stale: {sha_bad}")
    print(f"skills found ({len(skills)}): {', '.join(sorted(skills))}")
    if errors:
        print(f"FAIL ({len(errors)} errors)")
        for e in errors[:30]:
            print("  " + e)
        return 1
    print("PASS — palace structure, paths, skill contract clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
