---
name: wubuos-reference-os-harvest
description: Mine a reference OS image (SteamOS) for WuBuOS.
---
# WuBuOS reference-OS harvest (SteamOS is the current judge)

When the user makes an external OS the judge for WuBuOS (currently SteamOS, after
"meticulously take from SteamOS; drivers, kernel, all aspects"), the job is: obtain the
real OS, extract its actual files, and turn them into a spec-able sell-map for
WuBuOS — never a paraphrase from memory. All streets below were walked once and work.

## Procedure

1. **Locate the build**, not just a name. SteamOS images live under
   `https://steamdeck-images.steamos.cloud/steamdeck/<buildid>/`. Index the date-desc
   build dirs (`?C=M&O=D`) and read each candidate's
   `steamdeck-<build>-<ver>.manifest.json` to pin the REAL version (e.g. `20261113.100`
   is `3.10.0`). Download the update bundle too: `steamdeck-<build>-<ver>.raucb` is a
   Squashfs whose inner `manifest.raucm` is the authoritative version/compatible truth.

2. **Preview builds ship OTA-only — there is often NO ISO or full image.** Probe
   `/recovery/`, `/preview/`, and the `/steamdeck/` build tree before concluding an
   image doesn't exist. A preview build's dir holds only `.raucb` (Squashfs containing
   a casync `rootfs.img.caibx` index) + manifests; the newest FULL installable image is
   the stable one a slot behind, same desktop lineage. Pull the preview's
   `manifest.pacman` (the authoritative package list) and treat the newest full image
   as the concrete desktop assets.

3. **Download verified.** `curl -L -C - --retry 8 --retry-delay 5 -o <name> <url>` in a
   background session; on completion verify BOTH the byte size (from a prior `curl -sI`
   `Content-Length`) and `zstd -t <file>` before trusting anything.

4. **Decompress and mine WITHOUT root.** Hermes blocks shell-piped `sudo -S` (the
   askpass brute-force guard), so do not plan around passwordless mount. Instead:
   `zstd -d -k` → `file` (GPT disk) → `fdisk -l` for partition geometry → `dd` the
   rootfs partition out: `dd if=img of=rootfs-part.bin bs=512 skip=<sector> count=<n>`
   (offset = start_sector x 512) → `file rootfs-part.bin` → if BTRFS,
   `btrfs restore -i -x rootfs-part.bin ./rootfs_x` extracts the WHOLE filesystem
   unprivileged. (EXT4 would use `debugfs -R`.) ~6.4 GiB from a 3.1 GiB .zst, no mount.

5. **Harvest the desktop theme**: `usr/share/plasma/look-and-feel/` (SteamOS desktop =
   `com.valve.vapor.desktop`, game-mode = `com.valve.vapor.deck.desktop`), the Breeze
   button palette from `usr/share/color-schemes/BreezeDark.colors` `[Colors:Button]`
   (BackgroundNormal/ForegroundNormal/DecorationFocus — these are the exact
   "buttons look wrong" numbers), `usr/share/plasma/desktoptheme/`, `usr/share/wallpapers/`
   (the default wallpaper), `usr/share/icons/{breeze,breeze-dark,breeze_cursors}`. The
   default PANEL LAYOUT (`plasma-org.kde.plasma.desktop-appletsrc`) is NOT in a packaged
   rootfs — it is generated at first login from plasma-desktop's bundled defaults, so
   the FolderView spec lives in the plasma-desktop source, not the image.

6. **Harvest the whole OS** ("drivers, kernel, all aspects"): kernel
   `boot/vmlinuz-*` + version `usr/lib/modules/<ver>/` (+ module count), the NT
   primitive `ntsync.ko`, controller drivers (`hid-steam`, `xpad`, `psxpad-spi`),
   `uinput`; the ATOM updater (`usr/lib/steamos-atomupd` = casync+RAUC A/B), factory
   reset, `steamos-encrypt-home`, `steamos-log-submitter`; udev rules
   (`usr/lib/udev/rules.d/`, incl. Valve's `70-steamos-power-button.*` + hwdb); the
   fixed-UID sysusers contract (`usr/lib/sysusers.d/01-steamos-enforce-UID-GID.conf`).

7. **Deliver a sell-map, not a dump**: table SteamOS aspect → WuBuOS counterpart → the
   take, with the concrete files/values extracted, and name the highest-value first
   implementation. Do NOT stop to ask which slice to start — scope ALL aspects, then
   drive whichever is smallest and highest-value (the user says "drivers, kernel, all
   aspects" to kill exactly that stall). No large unverifiable GUI change ships, per the
   standing rule; the sell-map's first move should be the smallest verifiable one.

## Pitfalls

- **`pkill -f "<literal>"` self-matches your own shell.** The literal you are matching
  is in your own command line, so pkill SIGTERMs the shell running it. Kill the
  background download by PID captured at launch; never `pkill -f` with the literal you
  are also typing.
- **Never launch a second resumable download to the same path.** Two `curl -C -`
  processes writing one file interleave and corrupt it. If you restarted, delete and
  re-pull once, or verify the finished file with `zstd -t` (the definitive check) before
  trusting it.
- **Hermes blocks `sudo -S` password piping** (`echo pw | sudo -S ...` is refused as a
  brute-force vector). For disk images, `btrfs restore` / `debugfs` read the image
  directly with NO root — prefer them over any mount plan.
- **Chunk/CAS paths for preview OTA images are not directly fetchable** — the
  `chunks_details.json` ids do not map to `castr/<shard>/` paths. Do not pursue image
  reconstruction from the public CAS; use the manifest + nearest full image instead.
- **`os-release` is usr-merged**: `usr/lib/os-release`, not `/etc/os-release`. A missing
  `/etc/os-release` is not a damaged image.
