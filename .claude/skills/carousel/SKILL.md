---
name: carousel
description: Design multi-slide carousels (Instagram, LinkedIn document posts) and story sequences with a consistent system, a hook slide, continuity across slides, and a CTA slide; exports PNG per slide or one PDF for LinkedIn. Use for "carrossel", "post em várias telas", "conteúdo educativo em slides", "sequência de stories".
---
# carousel

Read first: layout skill. A carousel is a system, not N separate posts.

## Structure (adapt to the content)
1. **Hook** (slide 1): the promise or the provocative question; biggest type; no body text. It decides
   whether anyone swipes.
2. **Content** (2..n-1): one idea per slide, numbered if it is a list ("01/05"), same position for title,
   body and number on every slide.
3. **CTA** (last): save / share / follow / link / comment keyword; logo and @handle.
5-10 slides; ≤ 30-40 words per content slide. Write the copy for all slides first (copywriting skill),
show it to the user when it's a lot of text, then design.

## Build
- Artboards `slide-01` … `slide-NN`, preset `carousel` (or `li-carousel`):
  `uv run da artboard <p> add --preset carousel --id slide-01`, then design slide-01 + one content slide
  until approved, and DUPLICATE (`uv run da artboard <p> duplicate slide-02 --id slide-03`) so the system
  stays identical; change only the text/visual.
- Continuity tricks: a shape or photo that crosses the slide edge and continues on the next (place it at
  x = width - overlap on slide N and x = -overlap on slide N+1); a progress bar or page counter; an arrow
  "→" on the hook.
- Series from a table (many similar slides): batch-series skill (`uv run da batch`).
- Keep text away from the bottom ~100 px (dots indicator) and inside `safe`.

## Check
`uv run da render <p>` → LOOK at the contact sheet (`work/preview/sheet.jpg`): rhythm, same grid, same
type sizes, nothing jumping between slides. `uv run da qa <p>`.

## Deliver
Instagram: `uv run da export <p> --to png` (one file per slide, upload in order).
LinkedIn: `uv run da export <p> --to pdf` (one multi-page PDF, artboard order).
