# Battlefield Cleanup Patterns (2026-07-03)

## Summary
Complete removal of all timeframe semantics from WuBuOS documentation — dates, sessions, phases, "next session", "this session", "Phase N" language. Converted to pure tier-based structure (Critical/High/Medium/Low/Strategic).

## Files Modified (14 total)

| File | Key Changes |
|------|-------------|
| `BATTLESHIP.md` | Removed all dates, "Next 6 Sessions", "Sessions 7-15", "Sessions 16-30", "COMPLETED 2026-06-28/29/30" markers. Clean tier headers (CRITICAL TIER, HIGH TIER, MEDIUM TIER). Updated gap count 1562. |
| `STATE.md` | Removed "Session 06-28/06-29" headers, "Phase 17" date. Compressed to current state + archived foundations. |
| `slate.md` | Removed "Next 6 Sessions" constraint. Active work item + priority queue only. |
| `WUBUOS_DISTRO_ROADMAP.md` | **7 Phases → 6 Tiers**: Foundation → Critical×2 → High×3 → Medium → Strategic. No phase numbers, cell ranges, dates. |
| `goal-paste.md` | Updated 412→1562 gaps. Removed "Update BATTLESHIP.md when gap closed" instruction. |
| `OS_BIBLE.md` | Removed "Phase 21" date, "Phase 4-9" sections. Clean tier-based future roadmap. |
| `Makefile` | **Phase 1-6 test targets → Tier-based**: `test_critical_runtime`, `test_critical_kernel`, `test_high_bridge`, `test_high_gui`, `test_high_bear`, `test_medium_other`. |
| `README.md` | Test commands updated to tier names. |
| `index.md` | Removed dead links (BATTLEFIELD.md, DESIGN_BIBLE.md, etc.). |
| `dist/doc/architecture.md` | Phase A-F → Tier 1-6. No dates. |
| Wiki files | "NEXT SESSION PICK LIST" → "PICK LIST". Gap count 1434→1562. Removed session timestamps. |

## Pattern: Timeframe Removal Checklist

When cleaning documentation of temporal language:

1. **Remove dates**: `2026-06-28`, `2026-06-29`, `2026-06-30`, `2026-07-02`
2. **Remove session references**: "Session 06-28", "This session's fix", "Next session", "Previous session"
3. **Remove phase numbers**: "Phase 1", "Phase 2", "PHASE 1:", "Phase 3-5"
4. **Remove cell ranges**: "Cells 426-480", "Cells 200-425"
5. **Convert to tiers**: CRITICAL / HIGH / MEDIUM / LOW / STRATEGIC / FOUNDATION
6. **Preserve metrics**: gap counts, test counts, file counts, LOC
7. **Keep DA methodology**: "Rewriting from scratch in C" = the work
8. **Verify test commands still work**: update Makefile targets and README

## Tier Mapping (Phases → Tiers)

| Old Phase | New Tier | Components |
|-----------|----------|------------|
| Phase 0 (Foundation) | FOUNDATION | All completed work |
| Phase 1 (Runtime) | CRITICAL — Runtime | wubu_oci, network, snapshot, vsl, holyd, proton |
| Phase 2 (Kernel) | CRITICAL — Kernel | interrupt, fat32, txfs, ahci, drm, vulkan |
| Phase 3 (Bridge) | HIGH — Bridge | syscall bridge, DOS flip |
| Phase 4 (GUI) | HIGH — GUI | WM, desktop, startmenu, explorer, terminal, clipboard |
| Phase 5 (Bear RL) | HIGH — Bear RL | JIT, memory, tasking, HolyC, PTX |
| Phase 6 (Apps) | MEDIUM — Apps/Tools | WorldSim, Audio, Containers, etc. |
| Phase 7 (Arch) | STRATEGIC | Audio Engine, SteamOS, Ubuntu/Arch, TempleOS |

## Verification

```bash
# All tier test targets pass
make test_critical_runtime   # 14/14 ✅
make test_critical_kernel    # 4/4 ✅
make test_high_bridge        # 5/5 ✅
make test_high_gui           # all GUI targets ✅
make test_high_bear          # 9/9 ✅
make test_medium_other       # all remaining ✅

# Full suite
make test                    # "All tests passed (all tiers)" ✅
```

## Key Principle

> **We are an AI foundation — time is irrelevant.**

No deadlines, no sessions, no phases. Only:
- REAL_GAPs to close (1562, triple DA verified)
- Tier structure (Critical → Strategic)
- Perpetual gap-closer loop: pick → implement → test → commit → repeat