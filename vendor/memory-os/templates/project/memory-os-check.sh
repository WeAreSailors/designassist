#!/usr/bin/env bash
# Committed with this repo. Runs at the start of a Claude Code session and tells a
# first-time contributor how to install memory-os if this machine doesn't have it.
#
# It is deliberately trivial and read-only: it tests whether a file exists and prints
# a message. It installs nothing, downloads nothing, and sends nothing anywhere.
# Delete this file and the SessionStart hook in .claude/settings.json to turn it off.
set -u

CONFIG_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"

# Already installed (canonical path, or symlinked into this account's config dir)? Say nothing.
[ -f "$HOME/.memory-os/CLAUDE.md" ] && exit 0
[ -f "$CONFIG_DIR/memory-os/CLAUDE.md" ] && exit 0

REPO="https://github.com/edunascimentt/memory-os"

USER_MSG="This repo uses memory-os, and it isn't installed on this machine.

The project memory in .claude/_memory/ already works without it — Claude reads it either
way. Installing adds your own private layer on top (who you are, how you like to work,
your accounts) that follows you across repos and is never committed:

  git clone $REPO.git ~/.memory-os && ~/.memory-os/install.sh

Ask Claude to walk you through it, or ignore this — nothing here is blocked."

MODEL_CTX="memory-os is NOT installed on this machine (~/.memory-os is missing), so only
this repo's project tier (.claude/_memory/) is available — there is no global tier to read.
Do not go looking for ~/.memory-os/memory/ files; they do not exist here.
If the user asks about it, the install is: git clone $REPO.git ~/.memory-os && ~/.memory-os/install.sh
Do not run that yourself unless they ask you to. Full docs: $REPO"

# JSON-encode without depending on jq: escape backslashes and quotes, fold newlines.
esc() {
  printf '%s' "$1" \
    | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g' \
    | awk 'NR>1{printf "\\n"} {printf "%s", $0}'
}

printf '{"systemMessage":"%s","hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"%s"}}\n' \
  "$(esc "$USER_MSG")" "$(esc "$MODEL_CTX")"
exit 0
