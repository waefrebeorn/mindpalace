---
name: wubuos-macos-leg-proof
description: How to prove the WuBuOS macOS/Metal execution leg with "confirmed full hardware usage" parity to the ELF+PE vkcube legs — without the darling dead-end. Covers metal2vulkan (Metal AIR -> SPIR-V), the wubu_exec_macho VSL-native path, and running a translated Metal compute shader through a real Vulkan pipeline. Use when the macOS/Mach-O demo leg is needed or the darling build is stuck.
---

# WuBuOS macOS-Leg Proof (no darling)

## Context
"All three" demos = Linux ELF + Windows PE + macOS Mach-O, each through WuBuOS's own exec path
with confirmed full (Vulkan) hardware usage. ELF/PE are done (vkcube via wubu_exec_linux_elf /
wubu_exec_win_pe, rendered on llvmpipe, proof PNGs committed). The macOS leg was blocked by darling:
darling-ref is source-only, building it dies in objc4 `-Werror` macro-redefinition fights, and the
host has no Metal GPU anyway. The crash session left `darling-ref/build/` configured but with 0
compiled `.o` files.

## Pivot (the real macOS leg on this host)
WuBuOS already wires `wubu_ct_macho()` to set `WUBU_METAL2VULKAN=1` and route Metal shaders
through `metal2vulkan` (a Rust crate that translates Metal AIR/LLVM bitcode `.ll` → Vulkan
SPIR-V natively, no llvm `llc`). So the honest, achievable macOS leg is: **translate a Metal
compute kernel to SPIR-V and execute it through a real Vulkan pipeline** — same "confirmed full
hardware usage" bar as the vkcube legs.

## Free macOS verify loop (no Mac purchase, no human in the loop)

The standing constraint: the owner's only Mac is a 2012 iMac; no debt, no
payment plans, no telephone-tag services — remote macOS must be
agent-drivable or nothing. The working answer is GitHub Actions:

- **macOS runners are FREE and UNLIMITED on public repos** (Intel
  `macos-15-intel`/`macos-26-intel`, Apple Silicon `macos-15`/`macos-26`).
  Verify repo publicness with anonymous `git ls-remote` before relying on it.
- LIVE workflow: `wubucompositor/.github/workflows/macos-verify.yml` —
  compiles the Apple branches (`_NSGetExecutablePath` in wcc_spawn.c and
  the guest's buddy launcher) on both architectures and runs the headless
  spawn gate. Phase 2 (full compositor via MacPorts wayland + epoll-shim)
  is commented until the Quartz backend lands.
- Agent loop: push (or `gh workflow run`) → `gh run watch --exit-status`
  → `gh run view --log-failed` → fix → push. gh unauthenticated? Set
  GH_TOKEN from the stored git credential (see waefrebeorn-repo-creation);
  never print the token. Long runs: background watch, poll the jobs API
  for step status (`gh api repos/.../actions/jobs/<id>`).
- **Make test assertions machine-conditional**: CI runners have no sibling
  wubuos checkout, so "derived guest path is executable" fails there while
  the derivation is correct. Assert the portable shape everywhere; check
  machine properties only when present.
- The full dossier (essay, stub inventory, Quartz skeleton, dated research
  incl. free-tier matrix and the dead ends) lives in
  `wubuos/buy-wubu-a-mac/`. Cirrus CI is DEAD (jobs stopped mid-2026) —
  old tutorials still recommend it; don't.
- **libwayland builds on macOS** via epoll-shim (kqueue; MacPorts carries
  wayland + epoll-shim + xkbcommon; wayland-os.c is already Darwin-aware).
  The Quartz port is one library recipe + replacing the host-bound leaves
  (wcc_gpu/wcc_present/wcc_x11/wcc_monitors), not a protocol rewrite.
- 2012 iMac fallback: OCLP supports iMac13,x past Catalina; a GitHub
  self-hosted runner needs macOS 11+ (OCLP first); plain SSH loop works on
  any version. Apple hardware is also the only LEGAL macOS VM host.

## Steps (metal2vulkan shader leg)
1. **metal2vulkan build** (root-owned tree from a crash session blocks uid 1000; copy to a
   wubu-owned dir or take ownership first — see wubuos-gpu-shim / takeown procedure):
   `cd metal2vulkan && cargo build` (Rust installed via `sh https://sh.rustup.rs -y` user-local;
   do NOT use sudo). Binary: `target/debug/metal2vulkan`.
2. **Translate a Metal AIR fixture**:
   `cargo run -q --example translate_native -- validation/fixtures/public/kernel_store_const.ll kernel out.spv`
   → prints `PASS spirv-val (...)` and writes `out.spv`. The fixture is
   `define void @store_const(ptr addrspace(1) %out){ store i32 42, ...; ret void }` with
   `!air.kernel` metadata (storage buffer, set 0 binding 0).
3. **Validate**: `spirv-val --target-env vulkan1.3 out.spv` → must pass.
4. **Execute through a real Vulkan compute pipeline** (harness `/tmp/m2v_host.c`):
   entry point name is **`main`** (metal2vulkan canonical), pipeline layout MUST include the
   storage-buffer `VkDescriptorSetLayout`, memory type HOST_VISIBLE|COHERENT. Run with the
   GPU shim env. Expect `buffer[0] == 42` → "RESULT: PASS".
   (Full struct-hygiene rules in wubuos-gpu-shim.)

## What is NOT claimed
- We do NOT run a full Mach-O binary under darling. `wubu_exec_macho()` has a VSL-native Mach-O
  loader (covered by `test_vsl_macho`: parse + entry point) but full process execution still shells to
  darling, which is the dead-end. The macOS *graphics/shader* leg is proven via metal2vulkan.
- No Metal GPU exists on this WSL2 box; "full hardware usage" = real Vulkan pipeline on the live
  ICD (llvmpipe software, apiVersion 1.4.x), exactly the bar used for ELF/PE.

## Verification
- `test_vsl_macho` and `test_vsl_mac` must stay green — they exercise the VSL
  Mach-O loader and macOS syscall/BSD/Mach-trap tables.
- metal2vulkan translate + spirv-val + the m2v_host compute dispatch returning 42 is the macOS-leg
  proof artifact.

## Pitfalls
- Locate the metal2vulkan crate on the CURRENT box before re-running the
  proof (`find ~ -maxdepth 4 -type d -name metal2vulkan`); it has lived on
  different hosts and the proof artifacts below are recorded, not
  re-verified every session. Say plainly when a leg is skill-recorded vs
  freshly run.
- metal2vulkan crate checked into the tree was created as root by a crashed root session → uid 1000
  cannot build it in place. Fix ownership (takeown) or build from a wubu-owned copy under /tmp.
- cargo clippy is `-D warnings` per the crate's AGENTS.md; keep edits warning-clean.
- Don't fake a render. If darling can't build and no Metal GPU exists, the Metal-shader→Vulkan
  path is the honest substitute, not a stub.
