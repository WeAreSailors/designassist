# Project

> What this project is. Read first — orients every answer about this repo.
> One fact per line. Uncertain = `~` prefix.
>
> SHARED — committed and read by the whole team. Paths relative to the repo root,
> never `/Users/<someone>/…` or `C:\Users\<someone>\…`.

**Name:** designassist
**What it is / goal:** AI designer. Claude Code (or Codex) is the engine: it follows `CLAUDE.md` + `.claude/skills/*` and drives the `da` CLI; output is finished files (PNG/JPG/WebP/SVG/PDF, print-ready CMYK PDF with bleed) or editable Illustrator / Photoshop documents.
**Scope:** social media pieces (posts, carousels, stories, thumbnails, ads), visual identity (logo, palette, type, brand guide, mockups), UI / web (HTML screens and landing pages, design tokens), print (cards, flyers, posters).
**Stack:** Python 3.12 via uv (`src/designassist/`, CLI `da`); HarfBuzz (uharfbuzz) + fontTools text engine; resvg (resvg-py) for PNG; reportlab for PDF; psd-tools for layered PSD; vtracer for vectorising; OpenCV YuNet for face-aware crops; Lucide icons from jsDelivr; Higgsfield / Pexels / Unsplash APIs; ExtendScript (.jsx) for Illustrator/Photoshop.
**Sibling:** editassist (same author, same architecture, for video). Shared ideas: engine = agent + CLI printing JSON, memory-os tiers, per-client preferences, self-improvement loop (CLAUDE.md step 7).
**Run / build:** `./setup.sh` (macOS/Linux) or `setup.ps1` (Windows); then `claude` in the repo. Tools: `uv run da <command>`; check: `uv run da doctor`.
**Tests:** `uv sync --extra dev && uv run pytest -q -m "not network"` (synthetic images, no keys); CI on ubuntu/macos/windows in `.github/workflows/ci.yml`.
**Repo / hosting:** github.com/edunascimentt/designassist (public).
**Constraints:** must run the same on macOS and Windows; user projects (`projects/`) and personal design memory / client brand kits are never committed; paid APIs (Higgsfield) need user confirmation before spending.

## Context that doesn't fit above

- 2026-10-17: Project built from an empty repo, modelled on editassist.
- Source of truth for a piece is `projects/<name>/design.json` (format documented at the top of `src/designassist/design.py`); everything else is derived from it.
