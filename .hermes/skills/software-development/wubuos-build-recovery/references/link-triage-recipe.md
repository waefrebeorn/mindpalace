# Link-Error Triage Recipe (copy-paste)

Run from repo root `/home/wubu/.hermes/profiles/mind-palace/home/myseed/`.

## 1. Reproduce, grab FIRST error
```bash
make <target> 2>&1 | tail -20
# First "undefined reference" / "multiple definition" / "No rule to make target" is the root cause.
```

## 2. Stray line-continuation (crash artifact)
```bash
# Find a '\' at end of a PREREQ line (not a recipe line) or '\ ' with trailing space.
sed -n '139p' Makefile | cat -A          # show exact bytes of a suspect line
sed -n '139p' Makefile | od -c | tail -3  # confirm trailing '\' / spaces
# Fix: delete the stray trailing '\' (and any trailing spaces before it).
```

## 3. Map undefined symbol to defining .o
```bash
nm src/**/*.o 2>/dev/null | grep -wE "T <sym>"      # T = defined text symbol
# or for one file:
nm src/runtime/wubu_ct_isolate_cgroup.o 2>/dev/null | grep -w wubu_ct_cgroup_attach
```
Then add that `.o` (or its variable, e.g. `$(RT)/wubu_ct_isolate_cgroup.o`) to
the link.

## 4. Introspect a Make variable (don't trust the file view)
```bash
# Does the REAL link command contain the object?
make -n <target> 2>/dev/null | grep -oE "wubu_compat_db\.o"
make -n <target> 2>/dev/null | grep -c "wubu_container.o"   # count duplicates

# Print a fully-expanded variable:
make -s --eval='p:; @echo $(APP_RT_OBJS)' p | tr ' ' '\n' | grep -E "wubu_session|wubu_compat"
```
CAUTION: long backslash-continued vars can *appear* to drop tokens in
`make -p` / `--eval` dumps. Trust `make -n <target>` (the actual link cmd)
over a `$(VAR)` echo when they disagree.

## 5. Bisect: pre-existing vs introduced?

NEVER `git stash` / `git stash pop` for this. The repo carries PRE-EXISTING
stashes belonging to other work, and `git stash pop` pops the most recent one
regardless of what you pushed -- it has already pulled unrelated `wubugrep`
conflicts into a session here. Recovering meant committing first, then
`git reset --hard HEAD`.

Use a throwaway worktree at the parent commit instead; it leaves every stash
untouched:

```bash
git worktree add /tmp/wt_prev HEAD~1
make -C /tmp/wt_prev <target> 2>&1 | tail -5   # pristine build
git worktree remove /tmp/wt_prev
```

If pristine also fails → bit-rot, not your edit (look for OTHER causes like
the proton double-def or hosted-only symbols).

## 6. Repeat until linked, then run the gate
```bash
make runtime && make hosted && make paint && make doom
make test        # GATE must exit 0: "All tests passed (all tiers)"
```

## Quick "main already defined" decoder
- `multiple definition of 'main'` from `wubu_archd.o` / `wubu_holyd_lifecycle.o`
  → you linked `$(RT_OBJS)` into a standalone binary. Switch to `APP_RT_OBJS`.
- `multiple definition of 'wubu_container.o'` (same file cited twice) → the
  object is listed twice in the link (e.g. duplicated in `HOSTED_OBJS`). De-dup.
- `undefined reference to 'wm_get_hosted_state'` / `g_primary_selection_manager`
  → hosted-only symbol; add `src/gui/standalone_hosted_shim.o` to the link.
- `undefined reference to 'vkGetPhysicalDeviceMemoryProperties'` → add `-lvulkan`.
- `undefined reference to 'json_object_put'` → add `-ljson-c`.
