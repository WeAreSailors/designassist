---
name: qa
description: Automatic quality checks before showing or delivering a design: text overflow and missing glyphs, font fallbacks, contrast (WCAG), safe zones, off-canvas elements, tiny text, widows (a lone last word), upscaled/low-dpi images, print margin/bleed, fonts missing for Adobe exports, too many fonts, off-brand colours, alignment near-misses. Use before every preview you hand over and before export.
---
# qa

`uv run da qa <p> [--artboard ids] [--strict]`

- `error`: fix before anything else. `warn`: fix unless intentional (say so). `info`: mention.
- Overflow: enlarge the box, shorten the copy, or `autofit: true`; check with `uv run da layout`.
- Missing glyphs / fallback font: the font lacks the character (accents, symbols) or isn't found
  (`uv run da fonts get "<Family>"`).
- Contrast: darker scrim, solid block behind text, or swap colours; recheck with `da color contrast`.
- Safe zone: move text/logo/CTA inside `safe` (platform UI covers the rest).
- Low dpi / upscaled: a bigger source, a smaller placement, or tell the user it will look soft.
- Print margin/bleed: content ≥ `margin` from trim; edge elements extended to the bleed.
- Alignment near-miss: snap the edges to the same value.
- Fonts not installed (Adobe exports): `uv run da fonts install "<Family>"`.

QA can't judge taste: always LOOK at the renders yourself too (hierarchy, balance, does it read small, does
it look like the brand).
