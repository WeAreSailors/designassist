# Decisions (this project)

> Append-only log of real decisions in this project. Never edit past entries —
> if a decision is reversed, add a NEW entry that supersedes it.
> Format: `## YYYY-MM-DD — title` then what + why (1-3 lines).

## 2026-10-17 — Same engine shape as editassist
The model reasons, picks and writes JSON; a Python CLI (`da`) renders and prints JSON back. Skills are the
recipes; Codex uses the same repo via AGENTS.md. Proven in editassist; a colleague can run both the same way.

## 2026-10-17 — Own design.json, exports derived from it
A small layered format (artboards, layers, tokens) the model can read and edit by hand, with units (px/mm)
and bleed for print. PNG/PDF/SVG/PSD/Illustrator/Photoshop are all generated from it, so one edit updates
every deliverable.

## 2026-10-17 — Own text engine (HarfBuzz + fontTools), text outlined in previews
Line breaking, autofit and glyph positions are computed once (`text.py`) and reused by the PNG preview,
PDF, outlined SVG and the Adobe scripts. Previews never depend on system fonts or resvg's font matching, so a
design renders the same on every OS; editable exports carry the same positions as live text.

## 2026-10-17 — resvg for raster, reportlab for PDF, no browser in the core
resvg-py ships wheels for macOS/Windows/Linux and renders fast without a browser; reportlab writes CMYK,
boxes and outlined text for print. A headless Chromium (whatever the machine has: Chrome/Edge/Brave) is only
needed for `da web` screenshots of HTML.

## 2026-10-17 — Adobe apps through ExtendScript, not a UXP panel
Illustrator and Photoshop both run .jsx via `do javascript` (macOS AppleScript) and `DoJavaScriptFile`
(Windows COM), with no plugin to install; scripts build native text/shapes so the file stays editable.
editassist needed a UXP panel only because Premiere's scripting is UXP-only.

## 2026-10-17 — Memory: memory-os, two tiers; brand kits are private
Codebase knowledge in `.claude/_memory/` (shared). The user's design taste and every client's brand kit
(colours, fonts, logos, rules) live in the private memory-os global tier (`<global>/designassist/`), shared
across their Claude accounts; client fonts and logos are the client's business and never enter the repo.
memory-os is vendored in `vendor/memory-os/` (`da memory --install`, no download).

## 2026-10-19 — Affinity first, built live through its AI connector
The owner asked for Affinity before anything else (Illustrator was uninstalled). Affinity's formats are
closed, so `da affinity open` sends a generated SDK script through the app's own MCP endpoint and the document
is built natively inside Affinity (live text, shapes, curves, named layers), then rendered back and compared
with our preview. Our text engine's positions stay the reference: frames are nudged to the preview's ink top.
SVG artwork svgflat can't flatten becomes a bitmap layer rather than failing. Pull diffs against a snapshot
taken at build time, like the Illustrator path.
