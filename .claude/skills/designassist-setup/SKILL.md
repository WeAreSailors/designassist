---
name: designassist-setup
description: Guided first-time setup (or repair) of designassist on this machine. Installs dependencies and memory-os, collects and validates API keys (Higgsfield, Pexels, Unsplash) without exposing them, checks Illustrator/Photoshop, the headless browser for UI screenshots, CMYK profile and fonts; captures the user's design preferences; ends with a self-test and a status table. Use for "configura", "set it up", "instalar", "first time", "add my key", "my key doesn't work", or when `da doctor` / `da keys` shows something missing that a request needs.
---
# designassist-setup

Goal: the user leaves with what they want working, verified, and knows what is off and how to turn it on.
Re-runnable: jump to the one step they asked for ("adiciona minha chave do Pexels").
Talk in the user's language. One group of questions at a time (AskUserQuestion), never a wall.

## First run
`.claude/first-run-check.sh` (SessionStart hook) asks you to start this skill on the first message of a
machine's first session. One line to open, offer to skip, respect a skip (`uv run da setup-done --skipped`).
After a skip or a partial setup, still do what the user asked.

## 0. Where are we
`uv run da doctor`, `uv run da keys --check`, `uv run da memory`. No `uv`: step 1. Note the OS. Summarise in
3-5 lines: ready / missing.

## 1. System dependencies (ask before installing)
- macOS/Linux: `./setup.sh` (uv, then Python deps; it also installs Node via Homebrew when brew exists:
  `DA_SKIP_NODE=1 ./setup.sh` when they don't want it; Node only runs the Adobe script tests).
- Windows: `powershell -ExecutionPolicy Bypass -File setup.ps1` (winget: uv). A NEW terminal may be needed
  for PATH.
Re-run `uv run da doctor` until required rows are ok.

## 2. memory-os (their private memory across repos and Claude accounts)
If `~/.memory-os` is missing: one line on what it gives (their taste and client brand kits follow them; the
project memory in `.claude/_memory/` works without it) and offer `uv run da memory --install` (from
`vendor/memory-os`, no download). Suggest they fill `~/.memory-os/memory/me.md`; don't write it for them.

## 3. API keys (only for the features they want; multi-select)
| Feature | Keys | Where |
|---|---|---|
| AI images (photos, illustrations, edits) | `HF_API_KEY_ID` + `HF_API_KEY_SECRET` | console.higgsfield.ai > API keys (pay per image; ask their per-image cap → `DA_HF_MAX_USD`) |
| Stock photos | `PEXELS_API_KEY` | pexels.com/api (free, instant) |
| Stock photos (editorial) | `UNSPLASH_ACCESS_KEY` | unsplash.com/developers > New application > Access Key |
Collect safest first: they paste into `.env` (created from `.env.example`) themselves and say "pronto". If
they paste a key in chat: say once it is now in this conversation's history, then
`printf '%s' '<value>' | uv run da keys set NAME` (PowerShell: `'<value>' | uv run da keys set NAME`).
Always validate: `uv run da keys --check --only NAME`. Never repeat a key, never put one in memory, a commit
or a log; `.env` must be gitignored (`da keys` reports it).

## 4. Design apps and fonts
- Ask which they use: Affinity / Illustrator / Photoshop / Canva / only final files.
- Affinity (3.2+): `uv run da affinity status`; if `connector: false`, they switch on **Settings > AI connector**
  in Affinity (only they can; it turns off again when Affinity restarts or updates). Test build:
  `uv run da new teste-setup --preset ig-post`, add a text layer, `uv run da affinity open teste-setup`, LOOK at
  `work/affinity/*.jpg`, then close that document. Approve the `affinity` MCP server when Claude Code asks.
- Illustrator/Photoshop: `uv run da adobe status`; a test build: `uv run da new teste-setup --preset ig-post`,
  add a text layer, `uv run da adobe open teste-setup --app illustrator` (close that document after).
  Windows: the apps must have been opened once (COM registration).
- Fonts they use often: `uv run da fonts get "<Family>"` + `uv run da fonts install "<Family>"`.
- Print: `da doctor` shows the CMYK profile found (Coated FOGRA39 comes with Creative Cloud). Their print
  shop uses another? Put its .icc path in `DA_CMYK_ICC` in `.env`.
- UI work: `da doctor` must find a Chromium browser (Chrome, Edge, Brave) for `da web shot`.
- Background removal (optional, ~200 MB): `uv sync --extra bg`.

## 5. Design preferences (skippable)
preferences-quiz skill in **Quick** mode; offer the Full quiz now or later.

## 6. Verify and hand off
- `uv run da selftest`, `uv run da doctor`, `uv run da keys --check`.
- Final table: feature → ready / off (+ the one step to turn it on). Suggest a first task: "cria um post de
  teste pra marca X" or "põe uma foto em projects/teste/input e pede um post de promoção".
- `uv run da setup-done` (stops the first-run prompt; `--reset` brings it back).
