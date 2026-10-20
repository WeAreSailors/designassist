---
name: typography
description: Choose and set type: font selection and pairing, getting Google fonts, installing fonts for Adobe apps, type scales, leading/tracking, specimens, fixing text that looks off (orphans, rivers, bad breaks). Use for "qual fonte usar", "combina fontes", "a tipografia tá feia", "instala essa fonte", "baixa a fonte X".
---
# typography

## Find and get fonts
- `uv run da fonts list [--bundled]`, `uv run da fonts find "<query>"` (installed + bundled + downloaded).
- Google fonts (free, OFL): `uv run da fonts get "Inter"` → `assets/user-fonts/google/`. Usable in renders at
  once. For Illustrator/Photoshop: `uv run da fonts install "Inter"` (then restart the app).
- Pairing ideas: `uv run da fonts pair "<Family>"` (suggestions; judge them by rendering).
- Client fonts (licensed): into the brand kit's `fonts/` folder (brand-kit skill). Never commit them.

## Choosing
- Display face carries personality (grotesk = modern/neutral, geometric = friendly/tech, serif = editorial/
  premium, slab = sturdy, script = only for 1-3 words). Text face must be boring and legible.
- Max 2 families; get contrast from weight and size before adding a family.
- Portuguese: check accents (ã, ç, é) in the chosen font — `da render` reports missing glyphs.
- Make a specimen to decide: an artboard with the headline/body set in 2-3 candidates, render, LOOK, show.

## Setting
- Scale: pick a ratio (1.25 for UI/print body-heavy, 1.333-1.5 for social, 1.618 for posters) from the
  body size; round to the 4/8 px grid.
- Leading (`line_height`): display 0.9-1.1, subheads 1.15-1.25, body 1.35-1.5. Long lines need more.
- Tracking (1/1000 em): big display -10..-40; body 0; small caps/labels +80..+200; never track lowercase body.
- Measure: body 45-75 characters per line (set `w`). Avoid single-word last lines (widows) in headlines:
  rebalance with `\n` or adjust `w`; check with `uv run da layout <p> <ab> <layer>`. Keep words together
  ("12 horas", "R$ 14", "de verão") with a non-breaking space (` ` in the JSON string): lines only
  break at normal spaces.
- Case: `case: "upper"` for labels; avoid all-caps paragraphs.
- Numbers in prices: big number, small currency and cents (separate text layers or `**accent**` with `scale`).
