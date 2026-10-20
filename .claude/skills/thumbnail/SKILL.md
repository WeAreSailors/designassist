---
name: thumbnail
description: Design YouTube thumbnails and video covers that read at tiny sizes: face + emotion, 2-4 word hook, high contrast, cut-out subject, A/B variants. Use for "thumb", "thumbnail", "capa do vídeo", "miniatura do YouTube". Video frames can come from editassist exports or the user's photos.
---
# thumbnail

Preset `yt-thumb` (1280x720). The bottom-right corner (≈ 220x90 px) is covered by the duration badge:
keep it empty (the preset's `safe`).

## Recipe
1. Subject: a face with a clear emotion, or the product/object, BIG (40-60% of the frame). Cut it out:
   `uv run da image remove-bg input/<photo> -p <p>` (needs `uv sync --extra bg`), place the PNG over the
   background; add a thick outline or glow (`shadow` with blur 0-6 and an offset 0, light colour) to
   separate it.
2. Hook text: 2-4 words, heaviest weight, size so it reads at 160 px wide (headline ≥ 110 px tall),
   `stroke` or a solid `highlight` box for contrast. Never repeat the video title; complement it.
3. Background: simple, contrasting with the subject (saturated colour, blurred scene `filters.blur`,
   or a gradient). One accent colour.
4. Optional: an arrow/circle pointing at something (icons `arrow-big-right`, ellipse with stroke).

## Check small
Render, then look at the contact sheet AND imagine it at 168x94 (YouTube sidebar): can you read the words
and see the face? `uv run da qa <p>` (contrast, safe zone).

## Variants for A/B
Make 2-3 artboards that differ in ONE thing (text, colour, expression):
`uv run da artboard <p> duplicate thumb --id thumb-b`. Export all: `uv run da export <p> --to jpg --quality 92`
(YouTube limit 2 MB; jpg q90 is usually ~300 KB).
