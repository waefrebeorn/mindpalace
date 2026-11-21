# ============ PS-STYLE SHELL SETUP (auto-config) ============
# Clipboard: Ctrl+C = copy (selection) / Ctrl+V = paste is set in the
# terminal emulator's keybinding settings, NOT via .bashrc.

# Tools live in ~/.local/bin (installed without sudo)
[ -d "$HOME/.local/bin" ] && PATH="$HOME/.local/bin:$PATH"

# fzf fuzzy finder:  Ctrl+R = fuzzy history,  Ctrl+T = fuzzy files,  Alt+C = cd anywhere
[ -x "$HOME/.local/bin/fzf" ] && eval "$("$HOME/.local/bin/fzf" --bash)"

# zoxide smart cd:  "z docs" jumps to your most-used dir matching "docs"
[ -x "$HOME/.local/bin/zoxide" ] && eval "$("$HOME/.local/bin/zoxide" init bash)"

# Windows-ish aliases
alias cls='clear'
alias c='clear'
if [ -x "$HOME/.local/bin/bat" ]; then alias cat="$HOME/.local/bin/bat --paging=never --theme=ansi"; fi

# case-insensitive tab completion, like Windows/PSReadLine
bind "set completion-ignore-case on" 2>/dev/null

# git-aware prompt (posh-git style)
GIT_PS1_SHOWDIRTYSTATE=1
GIT_PS1_SHOWUNTRACKEDFILES=1
GIT_PS1_SHOWUPSTREAM="auto"
GIT_PS1_SHOWCOLORHINTS=1
[ -r /usr/lib/git-core/git-sh-prompt ] && . /usr/lib/git-core/git-sh-prompt

if command -v __git_ps1 >/dev/null 2>&1; then
  __ps1() {
    local last=$? _err=""
    [ "$last" -ne 0 ] && _err="\[\e[1;31m\] $last\[\e[0m\]"
    __git_ps1 "\[\e[1;32m\]\u@\h\[\e[0m\]:\[\e[1;34m\]\w\[\e[0m\]" "${_err}\n\\\$ " 2>/dev/null
  }
  PROMPT_COMMAND=__ps1
fi
# ============ END PS-STYLE SHELL SETUP ============
