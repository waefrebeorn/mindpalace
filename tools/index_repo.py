#!/usr/bin/env python3
"""Build INDEX.md: every file in the repo, hashed and summarized."""
import argparse, hashlib, re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / ".hermes" / "mind-palace" / "INDEX.md"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()[:12]


def skill_info(path: Path) -> str:
    text = path.read_text(errors="replace")
    desc = re.search(r"^description:\s*(.+)$", text, re.M)
    ver = re.search(r"^version:\s*(.+)$", text, re.M)
    bits = []
    if desc:
        bits.append(desc.group(1).strip().strip('"'))
    if ver:
        bits.append("v" + ver.group(1).strip())
    return " -- " + "; ".join(bits) if bits else ""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="write INDEX.md")
    args = ap.parse_args()
    rows = []
    for p in sorted(ROOT.rglob("*")):
        rel = p.relative_to(ROOT).as_posix()
        if rel.startswith(".git/") or p.is_dir():
            continue
        note = skill_info(p) if p.name == "SKILL.md" else ""
        rows.append(f"- `{rel}` [{sha256(p)}]{note}")
    body = "# Mind Palace Index\n\n"
    body += f"Files: {len(rows)}\n\n" + "\n".join(rows) + "\n"
    body += "\nRegenerate: `python3 tools/index_repo.py --write`.\n"
    if args.write:
        OUT.write_text(body)
        print(f"wrote {OUT} ({len(rows)} files)")
    else:
        print(body)


if __name__ == "__main__":
    main()
