---
name: export
description: Export final files in the right formats: PNG/JPG/WebP at scale, SVG (editable or outlined), multi-page PDF, print PDF (CMYK, bleed, crop marks), layered PSD, Illustrator/Photoshop scripts; with the right choice per destination (Instagram, LinkedIn PDF, web, print shop, Canva, client hand-off). Use for "exporta", "manda o arquivo final", "PNG em alta", "PDF", "arquivo pra gráfica", "PSD", "SVG", "pra subir no Canva".
---
# export

Always `uv run da qa <p>` first; fix errors.

Resolution comes from the user's setting (`uv run da settings`; `set resolution max|4k|2k|1x|8k`): with no `--scale`,
PNG/JPG/WebP/PSD and the screen PDF are made at it (max = as big as stays sharp: long side up to 3840 px, capped so
no photo is upscaled past 1.25x; a photo-less 1080x1350 post comes out 3072x3840, named plainly `slide-1.png`). Never pass `--scale 1` to save time on a deliverable.
Print artboards (mm/in) keep their dpi. Artboards of the same size share one scale (a carousel's slides come out
the same pixel size, capped by the most limiting photo).

| Destination | Command | Notes |
|---|---|---|
| Instagram / Facebook / X | `--to png` (or `jpg --quality 90` for photos) | at the resolution setting (the platform downsizes on upload) |
| LinkedIn carousel | `--to pdf` | one multi-page PDF in artboard order |
| Web / site | `--to webp png` | resolution setting (at least 2x for retina); webp is ~30% smaller |
| Print shop | `--to print` | CMYK, bleed, crop marks, text outlined; read the preflight |
| Canva | `--to png` for images; `--to svg-outlined` for vector elements; `--to pdf` imports as an editable-ish design | Canva can't read PSD layers well |
| Affinity | `--to affinity` (native document built live; script when the connector is off) | affinity skill |
| Illustrator | `--to illustrator` (script) or `--to svg` (live text) | adobe skill to open it live |
| Photoshop | `--to psd` (layered pixels) or `--to photoshop` (script: live text layers) | |
| Affinity (files only) | `--to svg` or `--to psd` or `--to pdf` | when the AI connector can't be used |
| Client approval | `--to pdf png` + mockups | |

`uv run da export <p> --to <targets...> [--artboard ids] [--scale N overrides the setting] [--quality 90]` → files in `output/`.
Read the JSON: files, warnings (missing fonts for Adobe, low dpi, RGB in print).
Bundle everything for the client: handoff skill (`uv run da package <p> --zip`).
