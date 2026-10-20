#!/usr/bin/env bash
# memory-os installer — idempotent, safe to re-run.
#   git clone https://github.com/edunascimentt/memory-os.git ~/.memory-os
#   ~/.memory-os/install.sh
set -euo pipefail

ROOT="$(cd -P "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="$HOME/.local/bin"

bold() { printf '\033[1m%s\033[0m\n' "$1"; }
ok()   { printf '  \033[32m✓\033[0m %s\n' "$1"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$1"; }

bold "memory-os install"
echo "store: $ROOT"
echo

# 1. private global memory — created from templates only if absent, NEVER overwritten
bold "global tier (private)"
if [ -d "$ROOT/memory" ]; then
  ok "memory/ already exists — left untouched"
else
  mkdir -p "$ROOT/memory/journal"
  cp "$ROOT/templates/global/"*.md "$ROOT/memory/"
  mv "$ROOT/memory/log.md" "$ROOT/memory/journal/log.md"
  ok "memory/ seeded from templates (gitignored — it never leaves this machine)"
fi
echo

# 2. one profile across every account
bold "accounts"
"$ROOT/bin/memory-os" link | tail -n +2
echo

# 3. wire each account's SessionStart hook so memory follows you across logins.
#    claude-accounts copies settings.json into new accounts, so this propagates itself.
bold "account hooks"
"$ROOT/bin/memory-os" accounts >/dev/null 2>&1 || true
"$ROOT/bin/memory-os" wire-accounts
echo

# 4. the CLI on PATH
bold "cli"
mkdir -p "$BIN_DIR"
ln -sfn "$ROOT/bin/memory-os" "$BIN_DIR/memory-os"
ok "$BIN_DIR/memory-os"
case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *) warn "$BIN_DIR is not on your PATH — add this to ~/.zshrc:"
     echo "        export PATH=\"\$HOME/.local/bin:\$PATH\"" ;;
esac
echo

bold "done"
cat <<EOF
  Fill in who you are:   \$EDITOR $ROOT/memory/me.md
  Add memory to a repo:  cd <repo> && memory-os init
  Check before sharing:  memory-os check
EOF
