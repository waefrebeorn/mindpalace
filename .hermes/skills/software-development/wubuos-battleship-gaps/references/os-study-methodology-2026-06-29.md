# OS Study Methodology for Gap Analysis
**Session**: 2026-06-29
**Purpose**: Document how to create and maintain OS study files that feed into the Triple DA Wiki

---

## Study File Structure

Each OS gets a study file at: `os-studies/<os>/<os>_study.md`

### Required Sections

1. **Architecture Overview** — Core philosophy, component diagram
2. **Subsystem Feature Tables** — For each major subsystem:
   - Reference OS features (specifics, not generalities)
   - WuBuOS current status
   - Gap assessment
3. **Platform Services** — What the OS provides that WuBuOS lacks entirely
4. **Component Parity Tables** — Widgets, tools, services
5. **Key Gaps for WuBuOS** — Categorized as MUST/SHOULD/NICE
6. **Implementation Priority** — Phase, Component, File, Estimated Sessions

---

## Study Files Created This Session

| OS | File | Size | Key Focus Areas |
|----|------|------|-----------------|
| GNOME 46+ | `gnome/gnome_study.md` | 17KB | Mutter, GTK4, libadwaita, D-Bus, systemd, PipeWire, Flatpak, GVfs, Tracker, a11y |
| SteamOS 3.x | `steamos/steamos_study.md` | 20KB | gamescope, Proton, DXVK/VKD3D, Pressure Vessel, Steam Input/Networking |
| TempleOS/ZealOS | `templeos/templeos_study.md` | 17KB | HolyC JIT, Doc/DolDoc, RedSea FS, Ring-0, VGA/VESA, PC Speaker |
| Arch Linux | `arch/arch_study.md` | 19KB | pacman/alpm, AUR, ABS/makepkg, systemd, mkinitcpio, NetworkManager |

---

## How to Use Studies in Gap Analysis

### 1. Extract Features
For each subsystem in the study, list specific features (not general capabilities):
- ❌ "Window management"
- ✅ "Dynamic workspaces (auto create/destroy), window snapping (edge/quarter), overview mode (Activities), window animations (genie/minimize)"

### 2. Map to WuBuOS Files
Each feature maps to a specific WuBuOS file or NEW FILE:
- "Dynamic workspaces" → `gui/wm.c` (extend)
- "Window snapping" → `gui/wm.c` (extend)
- "PipeWire audio graph" → `audio/wubu_audio.c` (NEW)

### 3. Estimate REAL_GAPs
Count void casts, stubs, system() calls needed:
- Reference implementation complexity + WuBuOS current state = REAL_GAP estimate
- Verified by: `grep -n "void.*param;\|TODO\|stub\|system(" src/<file>.c`

### 4. Assign Priority
| Priority | Meaning |
|----------|---------|
| 0 | Blocking (required for other gaps) |
| 1 | Critical (SteamOS gaming / GNOME desktop parity) |
| 2 | High (major subsystem) |
| 3 | Medium (feature complete) |
| 4 | Low (polish) |

### 5. Estimate Sessions
Based on historical velocity:
- ~10-20 void casts/session for simple implementations
- ~5-10 void casts/session for complex protocols (Wayland, Vulkan, D-Bus)
- New files: 2-8 sessions depending on scope

---

## Integration with Triple DA Wiki

The study files feed into:
1. **`triple_da_wiki.md`** — Parity matrix, conflicting requirements, roadmap
2. **`gap_analysis_wiki.md`** — Actionable Feature → File → REAL_GAPs → Priority table

When adding a new reference OS:
1. Create study file
2. Add column to parity matrix
3. Add conflicting requirements analysis
4. Add tier gaps to gap_analysis_wiki.md
5. Update roadmap session estimates

---

## Quality Standards for Study Files

- **Specificity over generality** — "WiFi with WPA3, captive portal, MAC randomization" not "WiFi support"
- **Reference actual source** — Kernel code, official docs, spec RFCs
- **Quantify gaps** — "200+ void casts", "15 system() calls", "5 missing syscalls"
- **Actionable mapping** — Every row has a WuBuOS file or "NEW FILE"
- **Session estimates** — Based on team velocity, not optimism

---

## Maintenance

- Update studies when new OS versions release (GNOME 47, SteamOS 3.6, etc.)
- Add findings from gap closure work (implementation details, patterns)
- Cross-reference with BATTLESHIP.md gap counts
- Version with date in header

---

*This methodology ensures the OS studies remain the raw intelligence that feeds the processed analysis in the Triple DA Wiki.*