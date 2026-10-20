---
name: print-ready
description: Design and deliver printed pieces correctly: business cards, flyers, folders/brochures, posters, banners/lonas, stickers, letterheads, envelopes, menus, invitations. Handles mm units, 300 dpi, bleed, safety margin, CMYK conversion (authored CMYK/Pantone when the brand has it), rich black, crop marks and a preflight. Use for "cartão de visita", "flyer pra gráfica", "arquivo pra impressão", "PDF com sangria", "lona", "adesivo", "papel timbrado".
---
# print-ready

## Setup
- Presets in mm with bleed: `uv run da presets --kind print` (`card-br` 90x50, `a5`, `a4`, `a3`, `dl`,
  `poster-50x70`, `banner-80x120`, `sticker-5`, `letterhead`, `envelope-c5`…). Odd size:
  `uv run da artboard <p> add --id peca --width 200 --height 100 --unit mm` then set `"bleed": 3, "dpi": 300, "margin": 5`.
- Ask the print shop's specs when the user has them (bleed 2/3/5 mm, profile, PDF/X, max ink). Default
  here: 3 mm bleed, 300 dpi (150 for large banners viewed from afar), Coated FOGRA39 when installed.
- Double-sided pieces: one artboard per side (`frente`, `verso`), same size.

## Design rules for print
- Everything that touches the trim edge must EXTEND into the bleed (background, photos, shapes): position
  them from `-bleed` to `width + bleed`. Background `background` already extends automatically.
- Text, logos and important content stay inside `margin` (≥ 3-5 mm from trim; cards 4 mm).
- Minimum sizes: body text ≥ 7 pt (6 pt absolute minimum, legal lines), thin strokes ≥ 0.25 pt. Sizes in
  print are easier as strings: `"size": "9pt"`.
- Colours: use the brand's authored CMYK when it exists (`{"hex": ..., "cmyk": [...]}` tokens); vivid RGB
  greens/blues/oranges shift in CMYK: warn the user. Big black areas: rich black token
  `{"hex": "#111111", "cmyk": [60, 40, 40, 100]}`; small black TEXT stays 100% K (default for #000000).
- Photos need ≥ 300 effective dpi at placed size (`da qa` reports it). Upscaling a phone photo to an A3
  poster won't be sharp: say so.
- QR codes: ≥ 2 cm, quiet zone, dark on light, test it.

## Deliver
1. `uv run da render <p> --bleed` and LOOK (bleed area visible): nothing important near the edge.
2. `uv run da qa <p>` → fix print errors (dpi, margin, bleed reach).
3. `uv run da export <p> --to print` → `output/print/<artboard>-print.pdf`: CMYK, bleed, crop marks,
   TrimBox/BleedBox, text outlined (no font problems at the shop). Read the preflight in the JSON.
4. Also give a screen PDF/PNG for approval (`--to pdf png`) and an editable file if they want
   (`--to illustrator`, adobe skill).
Tell the user plainly what the shop must know: final size, bleed, colour profile used.
