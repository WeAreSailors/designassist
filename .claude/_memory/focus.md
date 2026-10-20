# Focus (this project)

> What matters right now in THIS project. Dates ABSOLUTE (YYYY-MM-DD).
> Finished goals get pruned or moved to decisions.md, not left rotting.

## Active priorities

1. Affinity is the main editable target (2026-10-19): first real client job built in Affinity end to end, then a self-improvement pass.
1b. Affinity next: picture frames for images (keep the full photo croppable instead of a pre-cropped bitmap), `da affinity export` via `doc.export` presets (Affinity's own PDF/X), Windows check of the connector.
2. Keep CI green on ubuntu/macos/windows.

## Not yet verified (as of 2026-10-17)

- Windows and Linux runs (CI only).
- Photoshop export (no Photoshop on the dev machine; jsx tested against a node mock only; `da adobe pull` is Illustrator-only).
- Illustrator verified live on macOS (Illustrator 30.8.2, 2026-10-17: build, PNG export vs `da render`, read + pull); Windows COM route untested.
- `setup.ps1` and Windows font/browser paths.
- Print PDFs at a real print shop (preflight is our own; no PDF/X validation).
- Live Higgsfield / Pexels / Unsplash calls without keys on the dev machine.
- Idea: plain `blur` on vector shapes could use Affinity's live Gaussian blur layer effect (as `cast` does) instead of a bitmap.
- More `figure:` poses when a piece needs them (sitting, at a desk, group of two); poses are data in figures.POSES.
- Affinity docs built bigger than the artboards (`plan(doc_scale)`): at 2.84x only 2 of 5 artboards were created ("artboard ... not found after creation"); investigate before exposing it as a flag.
- yt-thumb preset `safe` is [40, 220, 90, 40]: it reserves the whole right strip for the duration badge, which only covers the bottom-right ~220x90. Add a `keepout` rect list to artboards (qa checks text/logos against it) and set the preset to safe 40 + keepout bottom-right (2026-10-19; worked around with safe 40 and keeping that corner free by hand).
- `da image people <cutout>`: split a multi-person cut-out into one PNG per face (face boxes give the split columns, keep the largest blob per person) so host and guest can be scaled apart; done with a one-off script on a podcast client's thumbs (2026-10-19).
- `da ref instagram <url|@profile>`: download a post's images (embed trick in facts.md) into work/refs/ + caption, and a profile's recent posts; done by hand with curl on 2026-10-20.
- `da brand logo add --split`: a PDF page with several logo versions on coloured panels (positive/negative) should become one logo per panel (`logo`, `logo-white`, `symbol`); split by hand on 2026-10-20.
- `da board --labels`: number + file name under each tile so input photos can be told apart (one-off sheet script on 2026-10-20).
