---
name: brand-guide
description: Produce a brand guide / manual de identidade visual from a client's brand kit: cover, logo versions, clear space and minimum size, colour palette with HEX/RGB/CMYK/Pantone, typography, applications, do's and don'ts; delivered as a PDF (and PNG boards). Use for "manual da marca", "brand book", "guia de identidade", "apresentação da marca pro cliente".
---
# brand-guide

1. The kit must be complete first (brand-kit skill): logos (SVG), colour roles (+ CMYK/Pantone if known),
   fonts, rules. Missing pieces: ask or mark them "a definir".
2. Generate the draft: `uv run da brand guide <slug> --project <p>` → `brand-board` artboards in
   `projects/<p>/design.json` (cover, logo, clear space, colours, typography, do/don't).
3. Make it the client's: render, LOOK, then refine like any layout (layout skill): use the brand's own
   colours and fonts on the pages, real applications (mockups: `uv run da mockup <p> --art <id> --builtin card|phone|poster`
   placed as image layers), the brand story/positioning in 2-3 sentences (copywriting skill).
4. Pages worth adding when relevant: logo on photos, social media templates, iconography style,
   photography direction (moodboard), stationery (card, letterhead), signage.
5. `uv run da qa <p>`, then `uv run da export <p> --to pdf png`. The PDF is the deliverable (one page per
   artboard); give PNGs for quick sharing. Optional editable: `--to illustrator`.
