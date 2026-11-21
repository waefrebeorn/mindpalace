# Auditing against a reference OS surface (Windows 11, Linux Mint, ...)

Use when the ask is "find the gaps versus <reference OS>" rather than "how
does this desktop feel". The QoL steps 1-12 audit THIS tree; this mode audits the
tree against an outside surface it is trying to slerm past.

## Method

1. **Build the checklist as (feature, [regex]) pairs.** One entry per visible
   shell/desktop surface the reference OS has. Keep the regexes matched
   against IMPLEMENTING symbols and filenames in `.c`/`.h`, excluding
   `third_party/` and submodules. Doc mentions do not count as evidence.
2. **Ship the scanner with the repo.** A one-file Python script
   (`tools/gap_audit.py`) that walks the tree, reports
   `present N / absent M`, and prints the absent list. Re-runnable is the whole
   point: the numbers in a hand-written doc go stale the next commit.
3. **A hit is evidence, not proof.** A symbol can exist and be unwired, or be a
   stub. State that in the report; do not present the count as a scorecard.
4. **Report in priority order, not alphabetical.** Rank by what the user can
   SEE and REACH: a taskbar button outranks a settings page, which outranks a
   driver-manager dialog. Split "not yet built (UI can be written today)" from
   "blocked on missing infrastructure" -- the second cannot be closed by
   writing UI and must be reported as a prerequisite.
5. **Close with what already works** so the next session does not rebuild it.

## Worked example (Windows 11 + Linux Mint Cinnamon)

The shipped tool checks 56 Win11 surfaces and 35 Mint surfaces. Representative
absent list: run dialog, taskbar search button, power-user menu, maximize hover
flyout, taskbar progress badges, night light, focus assist, startup-apps UI,
archive manager, image viewer, PDF reader, driver manager, hot corners,
presentation mode, backup tool.

## Pitfalls

- **A self-test that asserts a specific theme palette breaks on every theme
  change** and reads as a render regression. Accept either shipped theme, or
  weaken to "not mono + enough distinct colours". (The compositor's
  `wcc_test.sh` asserted the retired Win98 grey/navy pair and stayed red through
  the dark-theme switch.)
- **Grep for a symbol that would implement the feature, not for its user-visible
  label.** A feature can be present under an unfamiliar API name -- the audit
  skill's step 8 makes the same point from the other direction.
- **Do not report a gap from the checklist alone.** Before writing it up, open
  one implementing file for the "absent" item's neighbours to confirm the
  surface really is missing and not named unexpectedly.
