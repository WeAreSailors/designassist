---
name: vectorize
description: Convert raster logos, icons, signatures and flat illustrations to clean SVG vectors (vtracer), with colour reduction and clean-up, ready for print, Illustrator and the brand kit. Use for "vetoriza essa logo", "preciso da logo em vetor", "transforma em SVG", "a logo só tem em PNG/JPG".
---
# vectorize

1. Best source available: the largest, sharpest file; ask the client for the original (AI/EPS/PDF/SVG)
   first — a trace is a reconstruction.
2. `uv run da image vectorize input/<logo>.png -p <p> --mode logo --colors <n>` (n = the logo's real colours,
   e.g. 2) → `work/vector/<name>.svg`. Flat illustrations: `--mode illustration --colors 6-12`.
3. Check: render it big (an artboard with an `svg` layer at 2000 px) and LOOK: wobbly curves, lost corners,
   specks, merged letters. Text in logos traces badly — when you can identify the typeface
   (`uv run da fonts find`), rebuild the wordmark as live text / outlined text instead.
4. Fix colours to the brand's exact values (edit the fills in the SVG to the token hex) and remove the
   background shape if the trace added one.
5. Show the user side by side (original vs vector) before saving it to the brand kit
   (`uv run da brand logo <slug> add work/vector/<name>.svg --name logo`).
