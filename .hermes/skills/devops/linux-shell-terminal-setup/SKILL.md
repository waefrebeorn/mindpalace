---
name: linux-shell-terminal-setup
description: "Customize Linux terminal/shell: keybindings, tools, prompt."
version: 1.0.0
author: Hermes Agent
license: CC-BY-4.0
metadata:
  hermes:
    tags: [linux, terminal, shell, prompt, clipboard, fzf]
    related_skills: [hermes-agent]
---

# Linux desktop terminal & shell setup

## When to Use

Use when the user asks to get a Linux desktop terminal/shell to work or look a certain way — fix Ctrl+C/V clip/paste, add a modern CLI-toolkit, build a PowerShell-style (posh-git) prompt, or make a Windows transplant feel at home. Trigger words: "make my terminal like Windows/PowerShell", "copy/paste doesn't work in my terminal", "set up a cool terminal".

Scope: making a Linux desktop's terminal/shell behave how a specific user wants it (Windows/PowerShell transplants are common). Covers keybindings, modern CLI tools, and a git-aware prompt. Apply the user's stated preferences; default to safe, reversible changes. a Linux desktop's terminal/shell behave how a specific user wants it (Windows/PowerShell transplants are common). Covers keybindings, modern CLI tools, and a git-aware prompt. Apply the user's stated preferences; default to safe, reversible changes.

## Procedure

1. **Detect the environment before touching anything.**
   `echo $SHELL $TERM; echo "$DISPLAY $WAYLAND_DISPLAY $XDG_SESSION_TYPE"`; and `ps -e -o comm` filtered for the desktop + terminal emulator (gnome-terminal, konsole, kitty…) and for tmux. Clipboard tooling differs by display server: X11 = xclip/xsel, Wayland = wl-copy/wl-paste. The clipboard fix is a *terminal-emulator keybinding*, not a shell setting.

2. **Fix Ctrl+C/V clipboard for GNOME Terminal** (X11/Linux Mint; the common case). `org.gnome.Terminal.Legacy.Keybindings` is a RELOCATABLE schema — you must pass the path explicitly or gsettings errors `Schema ... is relocatable (path must be specified)`.
   ```
   export K=/org/gnome/terminal/legacy/keybindings/
   gsettings set org.gnome.Terminal.Legacy.Keybindings:$K copy '<Primary>c'
   gsettings set org.gnome.Terminal.Legacy.Keybindings:$K paste '<Primary>v'
   gsettings get org.gnome.Terminal.Legacy.Keybindings:$K copy   # verify it stuck
   ```
   Binding copy to bare Ctrl+C keeps SIGINT when nothing is selected — GNOME Terminal only captures the key when a selection exists. Tell the user this explicitly so they don't panic that Ctrl+C no longer stops commands.

3. **Set up the shell.** Append one clearly-marked block to `~/.bashrc` (heredoc, `cat >> ~/.bashrc <<'EOF'`) — never overwrite the file. See `templates/ps-style-bashrc.sh` for a copy-and-modify starting point.

## Tool install — user-level, no sudo

When sudo needs a password, install CLI tools into `~/.local/bin` from GitHub releases instead of apt, and prepend it to PATH in .bashrc. Worked set: fzf, bat, fd, zoxide (+ ripgrep already present).

Pitfalls that cost real time on this path:
- **Read `releases/latest` asset names before guessing a URL** — zoxide ships NO x86_64 gnu build, only `zoxide-<ver>-x86_64-unknown-linux-musl.tar.gz`; guessing the gnu name returns an HTML error and tar fails with `not in gzip format`. Query `https://api.github.com/repos/<owner>/<repo>/releases/latest` and grep `browser_download_url` for the right arch/build.
- **bat/fd tarballs nest the binary in a version dir** (`bat-<ver>-x86_64-...-linux-gnu/bat`). A bare `mv bat ...` fails. After `tar xzf`, locate the binary with `find . -type f -name <binary>` and copy that.
- Confirm every binary with `<tool> --version` before moving on.

## Prompt / wiring pitfalls (worth encoding)

- Source the git prompt helper EXPLICITLY in .bashrc: `[ -r /usr/lib/git-core/git-sh-prompt ] && . /usr/lib/git-core/git-sh-prompt`. It is loaded by `/etc/bash_completion.d/git-prompt`, but completion init order is not guaranteed; explicit sourcing makes `__git_ps1` reliably available.
- `__git_ps1 "prefix" "postfix"` (two-arg form) sets `PS1 = prefix + git-status + postfix` and works with `GIT_PS1_SHOWCOLORHINTS=1`. Use it inside a PROMPT_COMMAND function that also prepends a red errno when the last command failed (capture `$?` at the top of the function).
- **`__git_ps1` leaves `${__git_ps1_branch_name}` unevaluated inside PS1 on purpose** — bash expands it at prompt-render time. So grepping the PS1 string for the branch name returns nothing; that is normal, not a bug. Verify branch detection by echoing `${__git_ps1_branch_name}` after invoking your prompt function.
- **Non-tty bash never runs PROMPT_COMMAND.** Testing a prompt via `bash -ic 'echo $PS1'` with piped stdout shows the default/static PS1, not your rendered prompt. To exercise the prompt function directly, clear it and call it: `bash -ic 'PROMPT_COMMAND=; __ps1; ...'`. To see the true rendered multi-line colored prompt, fake a tty with `script -qec 'TERM=xterm-256color bash -ic "..."' /dev/null`.

## Rules for this user (Linux Mint box, no passwordless sudo)

- Never guess/assume sudo; if `sudo -n true` fails, go the ~/.local/bin route (user-level, reversible). Leaving system config untouched is preferred anyway.
- Every shell change goes into one removable, marked block so the user can revert by deleting one section. Report: files changed, what was verified, the one-line revert path, and the Ctrl+C/V semantic tradeoff (Ctrl+V no longer does bash `quoted-insert` / vim block-visual select).
- Deliver a `source ~/.bashrc` (or new tab) note so the user can activate without logging out.

Templates:
- `templates/ps-style-bashrc.sh` — ready-to-append PowerShell-style bash block (fzf/zoxide/PATH/aliases/git prompt).
