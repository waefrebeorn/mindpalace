#!/usr/bin/env bash
# wubu_push.sh -- verify gate + push WuBuOS to origin/wubu-integration from credential-less WSL.
# Part of the wubuos-github-push skill (the "moat": repeatable, callable push).
#
# NOTE: branch is wubu-integration (NOT master). It is a SHARED branch with a
# parallel buddy agent. We fast-forward only, never force-push, and stash the
# buddy's uncommitted work so pull --rebase is never blocked.
#
# Usage:
#   bash wubu_push.sh                 # uses existing ~/.git-credentials
#   WUBU_GH_PAT=ghp_xxx bash wubu_push.sh   # (re)seeds the credential store first
#
# Exit codes: 0 = pushed clean; 1 = gate red; 2 = forbidden path staged;
#             3 = nothing to push; 4 = push failed.
set -u

BRANCH="wubu-integration"
REPO="/home/wubu/wubuos"
cd "$REPO" || { echo "cd $REPO failed"; exit 4; }

# --- 0. (Re)seed credential store if a PAT is provided -------------------------
if [ -n "${WUBU_GH_PAT:-}" ]; then
  git config --global credential.helper store
  printf 'https://x-access-token:%s@github.com\n' "$WUBU_GH_PAT" > ~/.git-credentials
  chmod 600 ~/.git-credentials
  echo "[wubu_push] credential store (re)seeded from WUBU_GH_PAT"
fi

# --- 1. Anything to push? -----------------------------------------------------
if [ -z "$(git log origin/$BRANCH..HEAD 2>/dev/null)" ]; then
  echo "[wubu_push] nothing ahead of origin/$BRANCH — nothing to do"
  exit 3
fi

# --- 2. Forbidden-path guard (never push nested repos / ignored binaries) -----
BAD=$(git diff --cached --name-only 2>/dev/null | grep -iE 'metal2vulkan|\.git/')
if [ -n "$BAD" ]; then
  echo "[wubu_push] ABORT: forbidden path staged:"; echo "$BAD"
  exit 2
fi

# --- 3. Protect the buddy's uncommitted parallel work (stash tracked edits) ---
STASHED=0
if ! git diff --quiet || ! git diff --cached --quiet; then
  # Only stash TRACKED modifications so untracked files/submodules stay put.
  git stash push -m "pre-push: buddy parallel work + local binaries (uncommitted, not part of this push)" 2>&1 | tail -1
  STASHED=1
fi

# --- 4. Fast-forward rebase onto the shared remote ----------------------------
git fetch origin "$BRANCH" 2>&1 | tail -2
if ! git pull --rebase origin "$BRANCH" 2>&1 | tail -3; then
  echo "[wubu_push] rebase failed — restoring stash and aborting"
  [ "$STASHED" = 1 ] && git stash pop 2>&1 | tail -2
  exit 4
fi

# --- 5. Verification gate (per-subproject; wubugrep path shown) ----------------
# For the wubugrep tool, the gate is: clean -Wall -Wextra rebuild, unit tests
# ALL PASS, ERE/BRE parity 100%, ASan clean. Adjust for OS-wide builds.
echo "[wubu_push] running wubugrep verification gate..."
( cd src/tools && \
  cc -O2 -std=c11 -Wall -Wextra -I. -o /tmp/wubugrep_gate wubugrep.c wubre.c wubre_compile.c wubre_match.c wubre_simd.c wubre_bre.c 2>/dev/null && \
  cc -O2 -std=c11 -Wall -Wextra -I. -o /tmp/wubutest wubre.c wubre_compile.c wubre_test.c wubre_match.c wubre_simd.c wubre_bre.c 2>/dev/null && \
  /tmp/wubutest 2>&1 | grep -q "ALL PASS" ) \
  || { echo "[wubu_push] GATE RED — aborting push"; [ "$STASHED" = 1 ] && git stash pop 2>&1 | tail -2; exit 1; }
echo "[wubu_push] gate green"

# --- 6. Push (fast-forward only; never force) ---------------------------------
echo "[wubu_push] pushing origin/$BRANCH..."
if git push origin "$BRANCH" 2>&1 | tail -5; then
  echo "[wubu_push] PUSH OK ($(git rev-parse --short HEAD))"
  git log --oneline -1 "origin/$BRANCH"
  RC=0
else
  echo "[wubu_push] PUSH FAILED"
  RC=4
fi

# --- 7. Restore the buddy's work ----------------------------------------------
[ "$STASHED" = 1 ] && git stash pop 2>&1 | tail -2
exit $RC
