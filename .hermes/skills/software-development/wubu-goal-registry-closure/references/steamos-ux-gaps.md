# SteamOS / Steam Deck UX gap map (wubuwizard side)

The platform layer already exists in the wubuos repo and passes its gates:
`wubu_ct_steamos` (container preset), `wubu_proton2` (Wine/Proton orchestration),
`wubu_proton2_gamescope` (Deck UX cmd builder), `wubu_proton2_gpu`,
`wubu_proton2_device` (HID/USB), `wubu_steamrt` (sniper env), `wubu_steaminput`,
`wubu_dxvk_conf`, `wubu_wine_env`, `wubu_compat_db`, `wubu_gamelib`,
`wubu_notify`, `wubu_screenshot`. Do NOT rebuild these.

## SteamOS UX: COMPLETE (#372-#383, all closed in wubuwizard)
- #372 `wubu_steam_overlay` — Quick Access overlay (Shift+Tab): pause/resume,
  panel stack, friends+unread, achievements, screenshots.
- #373 `wubu_steam_power` — Deck power: 4 TDP profiles, temp fan curve,
  >=95C thermal clamp, battery-saver auto-clamp gated by lock+charging.
- #374 `wubu_gamepad_nav` — virtual cursor + snap-to-focus, radial menu,
  6x10 on-screen keyboard (space/backspace/done).
- #375 `wubu_steam_cloud` — Cloud Saves: 6 sync states, conflict resolution
  (newer/keep-local/keep-cloud), quota, per-game auto-sync, offline gating.
- #376 `wubu_steam_update` — update channels (stable/beta/preview), version
  queue -> download -> install, rollback snapshot, auto-download.
- #377 `wubu_steam_workshop` — Workshop mods: subscribe/unsubscribe, download
  state + retry, enable/disable, explicit load order, file-conflict detection,
  dependencies.
- #378 `wubu_steam_offline` — offline mode: installed + cached entitlement +
  not-always-online gating, playable count, blocked-launch tracking.
- #379 `wubu_steam_sharing` — Family Sharing: borrower auth + limit, lender
  exclusivity lock, per-game concurrency limit, revoke kicks active session.
- #380 `wubu_steam_replay` — background recording: 30fps ring buffer, save-
  last-N slice, manual record, frame aging-out.
- #381 `wubu_steam_remote` — Remote Play: host/client streaming session,
  bandwidth+GPU capability clamp, adaptive frame drop, rolling input RTT.
- #382 `wubu_steam_shader` — shader pre-caching: priority-ordered compile queue,
  rate-limited worker, fail+skip, stopped-worker refuse.
- #383 `wubu_steam_bigpicture` — Big Picture 10-foot grid: grid-aware D-pad
  move, detail panel, confirm-opens-detail vs launch.
Reassess before adding more; no documented SteamOS gap remains.

## Win98/XP UX: COMPLETE
- #384 `wubu_volmixer` — per-app volume mixer: master + per-channel volume/mute,
  effective = master*channel/100, overall = max.
- #385 `wubu_charmap` — Character Map: 12-block Unicode grid, grid-aware nav,
  UTF-8 encoder (1-4 byte + surrogate/range reject), select-to-clipboard.
- #386 `wubu_fontview` — Font viewer: catalog (family/style/size/mono), preview
  sample + size, active font selection.
- #387 `wubu_calendar` — Calendar: YYYYMMDD appointments, daily/weekly/monthly
  recurrence, reminder window, day lookup.
- #388 `wubu_contacts` — Address Book: name/phone/email, case-insensitive find
  + substring search, partial update, remove.
- #389 `wubu_sheet` — Spreadsheet: A1 grid, ref formulas (+-*/), dependency-
  ordered recalc, circular + div/0 detection, set-time syntax validation.
- #390 `wubu_wordproc` — Word processor: styled char runs, cursor insert/delete,
  selection replace, bold/italic/underline, word/char count, dirty flag.
- #391 `wubu_browser` — tabbed Web browser: per-tab back/forward history,
  independent tabs, switch, bookmarks, last-tab guard.
- #392 `wubu_mail` — Email client: 4 folders, read/unread, move/delete, counts.
- #393 `wubu_diskclean` — Disk Cleanup: 6 categories, safe-only default,
  reclaimable-by-selection, per-category bytes+counts.

## Already covered by the wubuos repo — do NOT rebuild
- Add/Remove Programs = `wubu_pkgmgr` (install/remove/list_installed).
- Music/media player = `apps/music.c` (playlist scan, play/stop/next/prev).
- Defrag = obsolete on btrfs/SSD; drive management is `explorer_drives.c`
  + `wubu_snapshot` (btrfs subvolume snapshot/rollback).
- Other utilities already present: controlpanel, service_mgr,
  regedit, taskmgr, term, wubu_settings, wubu_sound, wubu_waveosc,
  wubu_theme, wubu_wallpaper, wubu_notify, wubu_screenshot, wubu_trash.

## UX surfaces still OPEN (no code yet) — reassess before building
- Steam gamepad haptics/rumble; Steam achievements global tracker UI.
- Any new app beyond the Win98/XP + SteamOS accessory set above.
