#!/usr/bin/env bash
# Committed with this repo. Runs at the start of every Claude Code session.
# First time on a machine (no .designassist/setup.json yet), it tells Claude to start the guided
# setup on the user's first message. Read-only: it tests for one file and prints a message.
# The designassist-setup skill writes the file when it finishes (or when the user skips it).
# Re-trigger: `uv run da setup-done --reset` (or delete .designassist/setup.json).
set -u
ROOT="${CLAUDE_PROJECT_DIR:-.}"
[ -f "$ROOT/.designassist/setup.json" ] && exit 0

USER_MSG="designassist: first session on this machine — the guided setup will start with your first message (you can skip it)."
MODEL_CTX="FIRST RUN of designassist on this machine (.designassist/setup.json is missing). On the user's FIRST message in this session, before doing what they asked, invoke the designassist-setup skill. Open with one short line in the user's language saying this looks like the first time here and you'll set things up (dependencies, fonts, API keys, Photoshop/Illustrator, design preferences), and offer to skip. If they skip, run: uv run da setup-done --skipped (if uv isn't installed yet, create .designassist/setup.json with {\"status\":\"skipped\"} yourself). Then continue with their request."

esc() { printf '%s' "$1" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g' | awk 'NR>1{printf "\\n"} {printf "%s", $0}'; }
printf '{"systemMessage":"%s","hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"%s"}}\n' \
  "$(esc "$USER_MSG")" "$(esc "$MODEL_CTX")"
exit 0
