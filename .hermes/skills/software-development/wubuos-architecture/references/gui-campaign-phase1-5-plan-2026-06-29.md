# GUI Campaign Phase 1-5 Plan — 2026-06-29

## Overview
Next session priority order from BATTLESHIP.md, verified against current codebase state.

## Phase 1: GUI Campaign - Terminal (term.c) — 23 REAL_GAPs

### Current State
- PTY fork+exec: **IMPLEMENTED** (posix_openpt/grantpt/unlockpt/ptsname/fork/execvp)
- VT100 ANSI parser: **PARTIAL** - CSI sequences, SGR (8/16/256-color), cursor save/restore, scrolling, erase
- Scrollback buffer: **IMPLEMENTED** (10,000 lines circular)
- Copy/paste: **IMPLEMENTED** (selection with Shift+arrows, Ctrl+Shift+C/V)
- Tab management: **IMPLEMENTED** (16 tabs, drag-reorder, close, new)

### REAL_GAPs to Close (23 identified)
| Line | Function | Gap | Fix |
|------|----------|-----|-----|
| 786 | term_handle_key_pty | `(void)mods;` | Use mods for Ctrl/Shift/Alt key combos |
| 824 | term_handle_key_holyc | `(void)mods;` | Wire HolyC REPL key handling |
| 855 | term_handle_mouse_tab_bar | `(void)y;` | Use y for multi-row tab bar |
| 911 | term_handle_mouse_content | 5 params void'd | Implement selection drag, click-to-position |
| 967 | term_render_tab_bar | fb_w/fb_h void'd | Use for bounds checking |
| 1021 | term_render_content | fb_w/fb_h void'd | Use for bounds checking |
| 1048 | term_render_pty_session | fb/w/h void'd | Use for clipping/scissor |
| 1106 | term_render_holyc_session | all params void'd | Implement HolyC REPL rendering |
| 1042 | term_render_content | Container stub | Implement via wubu_container + VSL |
| 827 | term_holyc_eval | Delegates to WM, no-op | Wire to HolycTerm from wm |
| 202 | term_spawn_container | Returns idx, no PTY | Spawn container shell via VSL |
| 1208 | term_copy_selection | Scrollback only | Also copy from screen buffer |
| 1195 | term_scroll | Bounds fix | Clamp scrollback_view correctly |
| - | ANSI parser | Missing sequences | OSC (title), bracketed paste, mouse reporting |
| - | SGR | 24-bit RGB | Add 38;2;r;g;b / 48;2;r;g;b support |
| - | DEC private modes | Missing | DECCKM, DECAWM, DECOM, DECTCEM |
| - | Search | Partial | Highlight matches, next/prev |
| - | Tab drag-drop | Started | Complete visual feedback |
| - | URL detection | Missing | Regex + Ctrl+click |
| - | Bell | No-op | Visual flash / system beep |
| - | Selection word/line | Missing | Double/triple click |
| - | Resize handling | Basic | Preserve scrollback, cursor |

### Verification
```bash
make test_term  # 4/4 PASS currently, expand to 20+ tests
```

---

## Phase 2: GUI Campaign - WM (wm.c) — 22 REAL_GAPs

### Current State
- GAAD snap: **IMPLEMENTED** (snap_window_to_gaad, 9 regions)
- Virtual desktops: **IMPLEMENTED** (9 desktops, Ctrl+Alt+arrows)
- Focus stack: **PARTIAL** (Alt+Tab, taskbar buttons)

### REAL_GAPs to Close (22 identified)
| Line | Function | Gap | Fix |
|------|----------|-----|-----|
| 934 | wm_handle_mouse | border_width() void'd | Use for resize edge detection |
| 1165 | systray_add | on_click void'd | Wire click handlers |
| 1181 | systray_add | on_right_click void'd | Wire right-click handlers |
| 1238 | taskbar_render | fb void'd | Use for rendering (already draws to vbe) |
| 1499 | wm_render_desktop | fb void'd | Use for rendering |
| 1888 | ctx_menu_render | fb/fb_w/fb_h void'd | Use for bounds/clipping |
| 1953 | ctx_action_open | Stub | Execute icon target |
| 1960 | ctx_action_rename | Stub (notify only) | Inline rename with input field |
| 1967 | ctx_action_delete | Stub | Confirm dialog + remove |
| 1976 | ctx_action_properties | Stub (notify only) | Properties window |
| 1986 | ctx_action_create_shortcut | Stub (notify only) | New shortcut wizard |
| 1990 | ctx_action_view_desktop | Stub | View options dialog |
| 1994 | ctx_action_sort_by_name | Empty | Sort icons by name |
| 1998 | ctx_action_refresh | Notify only | Re-read desktop |
| - | Window resize | Missing | 8-edge drag resize |
| - | Modal dialogs | Stub | Block input to parent, center |
| - | Window maximize | Toggle only | Full screen logic |
| - | Window minimize | Flag only | Hide from taskbar/alt-tab |
| - | Focus stack | Partial | MRU tracking, click-to-focus |
| - | Icon grid snap | On drag end | Show ghost, snap on release |
| - | Desktop context menu | New/Folder/Text | Create file/folder |
| - | Taskbar clock | Updates | 1-minute timer |
| - | Virtual desktop switch | Ctrl+Alt+L/R | Wrap, indicator |

### Verification
```bash
make test_wm  # 16/16 PASS currently
```

---

## Phase 3: Runtime - VSL Syscalls (wubu_vsl.c) — 347 REAL_GAPs

### Current State
- ~200 syscalls implemented via host delegation
- All use `(void)a; (void)b; ...` pattern for unused params

### REAL_GAPs to Close (347+ void casts across ~150 syscalls)
**Strategy:** Replace each `(void)param;` with actual usage where needed. Most syscalls already delegate correctly — the void casts are just for parameters not used by that specific syscall. True gaps are:
- Missing syscalls: `io_uring_setup`, `io_uring_enter`, `io_uring_register`, `pidfd_open`, `pidfd_send_signal`, `pidfd_getfd`
- `clone3` returns ENOSYS (stub at line 1069)
- `vsl_sys_nosys` for unimplemented syscalls (line  (line 130)
- Signal stack: `sigaltstack`, `rt_sigaction` SA_SIGINFO handling
- `vsl_get_host_fd` helper needs expansion for all fd types
- Container fd mapping for Styx/9P namespace

### Verification
```bash
make test_vsl  # 52/52 PASS
```

---

## Phase 4: Bear RL - Vulkan (bear_vulkan.c) — 33 REAL_GAPs

### Current State
- Instance/device creation: **IMPLEMENTED**
- Memory allocation: **IMPLEMENTED**
- Pipeline cache: **IMPLEMENTED**
- Tensor ops: **STUBS** (matmul, add, relu, etc. return early)

### REAL_GAPs to Close (33 identified via `(void)` casts)
| Line | Function | Gap |
|------|----------|-----|
| 720 | bear_vulkan_tensor_create | `(void)name;` — tensor naming |
| 845 | bear_vulkan_tensor_free | `(void)arena;` — arena allocator integration |
| 1076 | bear_vulkan_dispatch | All params void'd — dispatch compute |
| 1144 | bear_vulkan_dispatch_pipeline | net/temp_arena void'd |
| 1231 | bear_vulkan_compute | temp_arena void'd |
| 1237 | bear_vulkan_train_step | ctx/t/cfg void'd |
| 1296 | bear_vulkan_eval | rng_seed void'd |
| 1302 | bear_vulkan_act | ctx/env/actions void'd |
| 1385 | bear_vulkan_ppo_update | All params void'd |

### Verification
```bash
# No dedicated test yet - need to create bear_vulkan_test.c
```

---

## Phase 5: Audio - Architectural (wubu_audio.c) — 0 Implemented

### Current State
- 67,994 lines but **ALL STUBS** — returns 0, `(void)` params, empty implementations
- Furnace tracker structs defined but no render loop
- TinySoundFont structs defined but no synthesis
- Ardour mixer structs defined but no mixing

### Architecture to Implement (from scratch)
```
MIDI Input (USB/evdev) → Furnace Tracker → Chip Sound (NES/GB/YM2612/SN76489/SID/SAA1099/VRC6/N163)
                          → TinySoundFont → Sample Synth
                          → Ardour Mixer → Master Bus (EQ, Compressor, Limiter)
                          → ALSA/JACK/PipeWire → Speakers
                          → AI Plugin Container → DSP on any track
```

### REAL_GAPs = Entire Implementation
1. Audio thread (lock-free ring buffer)
2. ALSA/PipeWire output backend
3. MIDI input (evdev + ALSA seq)
4. Furnace tracker render loop (chip emulations)
5. TinySoundFont SF2 loading + synthesis
6. Ardour-style mixer (tracks, sends, inserts, automation)
7. Master bus processing
8. AI plugin container (VST3/CLAP via VSL)
9. DAW timeline (patterns, arrangement)
10. Project save/load (.wubu audio container)

### Verification
```bash
make test_audio  # Currently 11 tests, all stubs - need real tests
```

---

## Execution Order
1. **Phase 1** — Terminal (user-facing, blocks GUI completeness)
2. **Phase 2** — WM (user-facing, modal dialogs needed for apps)
3. **Phase 3** — VSL (largest, enables Linux app compat)
4. **Phase 4** — Vulkan (enables GPU compute for Bear RL)
5. **Phase 5** — Audio (new subsystem, start from scratch)

## Gap Closure Methodology
For each gap:
```bash
# 1. Verify current state GREEN
make test_<target>

# 2. Edit ONE file - replace void casts / implement stubs
#    Use parameter, wire to real implementation

# 3. Verify still GREEN
make test_<target>

# 4. Clean build
make all

# 5. Next gap
```

## Success Criteria
- All 5 phases: **747+ tests remain green**
- New tests added for each phase
- Zero `system()` calls remaining
- Zero `return -1` without work
- Zero `{} ` empty success paths
- Zero "stub"/"TODO"/"placeholder" in success paths