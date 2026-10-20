---
name: moodboard
description: Collect and analyse visual references before designing: the user's references, the client's existing material, stock searches; produces a moodboard sheet with a palette strip and a written direction (type, colour, imagery, composition). Use for "referências", "moodboard", "quero algo nessa linha", "olha esse perfil/site", or before a logo/identity/campaign.
---
# moodboard

1. Gather: files in `projects/<p>/input/` (screenshots, prints of profiles, photos), links the user sends
   (screenshot pages with `uv run da web shot` when it's a site; for social profiles ask for screenshots),
   stock searches for mood (`uv run da stock <p> "<mood words>" --n 12`, look at the sheet, download a few).
   Put references under `input/refs/` or `work/refs/`.
2. Build the sheet: `uv run da board <p> input/refs work/stock --title "<project>"` → `work/board/board.jpg`
   (+ `output/board.jpg` for the client), with the extracted palette.
3. LOOK at every reference and write the direction in `projects/<p>/brief.md` under "Direção visual":
   - type (serif/sans, weight, case, tight/loose),
   - colour (temperature, saturation, contrast, the palette strip),
   - imagery (photo vs illustration, lighting, crop, people or product),
   - composition (centred/asymmetric, density, whitespace, grids),
   - what to avoid (things in the refs the user doesn't want).
4. Confirm the direction with the user in 4-6 bullets before designing. Never copy a reference: extract
   principles.
