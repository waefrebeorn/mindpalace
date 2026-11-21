#!/usr/bin/env python3
"""Verify the palace: skills, docs, referenced paths, secret scan."""
import re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / ".hermes" / "skills"
PALACE = ROOT / ".hermes" / "mind-palace"
REQUIRED = [
    PALACE / "README.md", PALACE / "slate.md", PALACE / "INDEX.md",
    PALACE / "DEVILS_ADVOCATE.md", PALACE / "ROADMAP.md",
    PALACE / "PRESTIGE.md", PALACE / "STEPLOG.md",
    SKILLS / "mp" / "SKILL.md", ROOT / "LICENSE", ROOT / "README.md",
]
SECRET = re.compile(r"(gh[pousr]_[A-Za-z0-9]{30,}|hf_[A-Za-z0-9]{30,}|"
                    r"AKIA[0-9A-Z]{16}|"
                    r"-----BEGIN [A-Z ]*PRIVATE KEY-----)")

fail = 0
for p in REQUIRED:
    if not p.is_file():
        print(f"FAIL missing required file: {p.relative_to(ROOT)}")
        fail += 1

skill_files = sorted(SKILLS.rglob("SKILL.md"))
print(f"skills: {len(skill_files)}")
if len(skill_files) < 2:
    print("FAIL too few skills aggregated")
    fail += 1
for p in skill_files:
    text = p.read_text(errors="replace")
    if not text.startswith("---"):
        print(f"WARN no frontmatter: {p.relative_to(ROOT)}")
        continue
    m = re.search(r"^description:\s*(.+)$", text, re.M)
    if not m:
        print(f"WARN no description: {p.relative_to(ROOT)}")
    elif len(m.group(1).strip().strip('"')) > 60:
        print(f"WARN description >60 chars: {p.relative_to(ROOT)}")
    if not re.search(r"^##\s+when", text, re.I | re.M):
        print(f"WARN no When-to-Use: {p.relative_to(ROOT)}")

# Every backticked .md/.py/.sh path named in palace docs must exist.
for doc in list(PALACE.glob("*.md")) + [ROOT / "README.md"]:
    for raw in re.findall(r"`([^`]+\.(?:md|py|sh|SKILL))`", doc.read_text()):
        raw = raw.strip()
        if "://" in raw or "$" in raw or "*" in raw:
            continue
        ref = raw.split()[-1] if " " in raw else raw
        ref = ref.strip("<>").strip("`")
        candidates = [ROOT / ref, PALACE / ref, ROOT / "tools" / Path(ref).name]
        if any(c.exists() for c in candidates):
            continue
        if list(ROOT.rglob(Path(ref).name)):
            continue
        print(f"FAIL dead path in {doc.name}: {ref}")
        fail += 1

for p in ROOT.rglob("*"):
    if p.is_file() and ".git/" not in p.as_posix() and p.suffix in {".md", ".py", ".sh", ".yaml", ".yml"}:
        if SECRET.search(p.read_text(errors="replace")):
            print(f"FAIL possible secret: {p.relative_to(ROOT)}")
            fail += 1

print("VERIFY_MIND_PALACE: " + ("PASS" if fail == 0 else f"FAIL ({fail})"))
sys.exit(1 if fail else 0)
