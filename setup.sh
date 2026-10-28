#!/usr/bin/env bash
# designassist setup for macOS / Linux. Safe to re-run.
set -euo pipefail
cd "$(dirname "$0")"

have() { command -v "$1" >/dev/null 2>&1; }

if ! have uv; then
  echo "installing uv ..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi
# node is optional: only the Adobe-script tests run .jsx against mocks with it (DA_SKIP_NODE=1 skips it)
if ! have node && [[ "${DA_SKIP_NODE:-0}" != "1" ]]; then
  if have brew; then brew install node || true
  else echo "node not found (optional: only needed to run the Adobe-script tests)"; fi
fi

uv sync

uv run da memory --init >/dev/null  # memory-os global tier if installed, else gitignored memory/
[[ -f .env ]] || cp .env.example .env

# design apps: nothing to install, exports are files (+ live open on macOS/Windows)
for app in "/Applications/Adobe Illustrator"* "/Applications/Adobe Photoshop"*; do
  [[ -d "$app" ]] && echo "found: $(basename "$app") — designassist can open its exports there"
done

uv run da doctor || true
echo
echo "Done. Open this folder in Claude Code (\`claude\`) or Codex and describe the piece you want."
