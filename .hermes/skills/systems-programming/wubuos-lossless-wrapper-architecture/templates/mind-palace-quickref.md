# Mind Palace Quick-Reference Structure

## File Layout (WuBuOS mind palace)

```
~/.hermes/profiles/mind-palace/
├── AGENTS.md           # Agent bootstrap protocol
├── SOUL.md             # Identity banner
├── index.md            # Main index + recent entries
├── slate.md            # Active context (CURRENT SESSION)
├── wubuos-architecture.md  # Architecture cross-reference
├── skills/
│   └── systems-programming/
│       ├── fable-windowing-agent-port/
│       │   ├── SKILL.md
│       │   ├── references/
│       │   │   └── 2026-06-16-port-session.md
│       │   ├── templates/
│       │   │   └── os-component-port-template.h
│       │   ├── scripts/
│       │   │   └── verify-dosgui-wm.sh
│       └── wubuos-lossless-wrapper-architecture/
│           ├── SKILL.md
│           ├── references/
│           │   └── 2026-06-16-architecture-session.md
│           └── templates/
│               └── architecture-session-entry.md
```

## Key Commands

```bash
# View current slate
cat ~/.hermes/profiles/mind-palace/slate.md

# View architecture cross-ref
cat ~/.hermes/profiles/mind-palace/wubuos-architecture.md

# List skills
ls ~/.hermes/profiles/mind-palace/skills/systems-programming/

# View skill
skill_view name=<skill-name>

# Run DosGui WM verification
~/.hermes/profiles/mind-palace/skills/systems-programming/fable-windowing-agent-port/scripts/verify-dosgui-wm.sh
```

## Session Start Protocol

1. Read `slate.md` for active context
2. Read `wubuos-architecture.md` for architecture
3. Load relevant skills via `skill_view`
4. Continue from `slate.md` "Next Actions"