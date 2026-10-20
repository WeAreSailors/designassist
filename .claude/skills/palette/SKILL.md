---
name: palette
description: Build or analyse colour palettes: extract from a photo/logo/reference, generate harmonies and tint/shade scales, assign roles (primary, accent, ink, paper), check contrast pairs, and give HEX/RGB/CMYK. Use for "paleta de cores", "quais cores combinam", "extrai as cores dessa imagem", "cores da marca", "esse contraste tá ok?".
---
# palette

Commands (all print JSON):
- `uv run da color palette <image> --n 6` — dominant colours with share and a suggested role.
- `uv run da color harmony <hex> --kind analogous|complementary|triadic|split|tetradic|monochrome`
- `uv run da color scale <hex>` — 50…950 steps (OKLCH, perceptually even) for UI states and tints.
- `uv run da color contrast <fg> <bg>` — ratio + WCAG grade; `uv run da color check <p>` for every text in a design.
- `uv run da color cmyk <hex>...` — print values (says which ICC profile was used).

## Method
1. Start from meaning and context (brief): category conventions (finance blues, food warm), what
   competitors use (differ), the audience.
2. Pick ONE hero colour (primary), then a neutral pair (ink = near-black tinted towards the hero, paper =
   off-white or white), then ONE accent for CTAs/highlights. Optional secondary. 3-5 colours total.
3. Proportions ≈ 60 neutral / 30 primary / 10 accent. Don't use the accent for large areas.
4. Check: ink on paper ≥ 7:1, primary as text background with white/ink ≥ 4.5:1 (else it's for shapes
   only), accent visible on both paper and primary.
5. Show it: render a palette board (a `brand-board` artboard with swatch rects + labels HEX/RGB/CMYK), LOOK,
   and present roles + where each is used.
6. Save as tokens: project `tokens.colors` or the client kit (`uv run da brand set <slug> --color role=#hex`).
   Export for the user's apps: `uv run da tokens <p> --to ase css tailwind` (ASE imports into
   Illustrator/Photoshop swatches).
