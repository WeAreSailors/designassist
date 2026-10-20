---
name: layout
description: How to compose a piece in design.json well: grid, margins, hierarchy, type scale, spacing, layering photos and scrims, and the build-render-look loop. The craft base every layout skill (social-post, carousel, thumbnail, print-ready, logo, brand-guide) builds on. Use whenever you place layers on an artboard or the user says "melhora o layout", "tá poluído", "tá sem hierarquia", "alinha isso".
---
# layout

## The loop (never skip a step)
1. Plan on paper first (in your head / a short list): the ONE message, the reading order (1st, 2nd,
   3rd), the grid (columns, margins = artboard `safe` or print `margin`), where the photo/focal element sits.
2. Write layers into `design.json` (format at the top of `src/designassist/design.py`), bottom to top:
   background → photo → scrim/shapes → text → logo/CTA. Use tokens (`$primary`, `$display`), not raw values.
3. `uv run da validate <p>` then `uv run da render <p> [--artboard id]`.
4. LOOK at the PNG with your image reading tool. Also look at it small (the contact sheet, or imagine
   it at 300 px wide: a feed thumbnail). Ask: what do I see first? Is the headline readable small? Is
   anything touching an edge by accident? Does it look intentional?
5. Measure instead of guessing: `uv run da layout <p> <artboard> <layer>` → lines, final size after
   autofit, content height. Place the next element at `y + content height + gap`.
6. Fix, re-render, look again. Then `uv run da qa <p>`. Only then show the user.

## Grid and spacing
- Pick a base unit (social 1080 wide: 8 px; print: 1 mm) and make every gap a multiple of it. Typical
  social margins 60-96 px; gaps: label→headline 24, headline→body 32-48, body→CTA 48-64.
- 12-column thinking on wide formats, 4-6 on posts. Left-aligned text blocks share ONE x. Centred
  layouts centre everything on the same axis.
- Keep text, logos and CTAs inside `safe` (stories: big top/bottom zones are covered by the app UI).
- Breathing room > filling space. If it feels crowded, remove an element before shrinking things.

## Hierarchy and type scale
- Three levels max: headline (biggest, heaviest), support (≈ 0.35-0.5x headline), detail/CTA. Use a
  ratio (1.25 / 1.333 / 1.5 / 1.618) and stick to it within a piece and across a set.
- Headlines: `line_height` 0.95-1.1, `tracking` -10..-30 on display weights; labels: uppercase,
  small, `tracking` 100-250. Body: 1.3-1.5 leading, 45-75 characters per line (`w`).
- `autofit: true` with `w` and `h` boxes for headlines whose copy may change; `max_lines` to cap.
- Accent ONE phrase with `**markup**` (colour or highlight), not five.

## Photos and legibility
- `fit: "cover"` + `focus: "face"` (or a point `[fx, fy]`) so crops keep the subject.
- Text over photo: a gradient scrim rect (`fill` linear, `$ink/0` → `$ink/85`) under the text area, or put
  the text on a solid block. Check `da qa` contrast.
- Duotone/tint (`filters`) to unify mismatched photos in a set.

## Layering tricks that look designed
- Shapes that bleed off the edge (negative x/y) feel bolder than shapes floating inside.
- Overlap: headline partly over the photo, a circle badge over a corner (`rotation` -8..8 for stickers).
- Repetition: same corner radius, same stroke width, same shadow everywhere (or none).
- `group` for anything that moves together (CTA pill = rect + text + icon).

## Effects (use sparingly, one per piece)
- `texture` on heavy type = ink bleed / photocopy edge (`{"spread": 2.6, "size": 4, "rough": 1}`): one word, not a paragraph.
- `noise` layer over everything = film grain (`opacity` 0.15-0.35; `mode: "overlay"` on saturated colour).
- `blur` on a big shape = soft glow / gradient sphere; stack a blurred halo + a denser core under text, and check
  contrast with `da qa`.
- People in a scene (tiny walkers on an isometric floor, someone facing a big object): `svg` layer with
  `src: "figure:<pose>"` (`da figure list`: stand, stand-back, walk, pocket, point, phone; `-left` mirrors), `h` = the
  height, `w` = h x aspect, bottom of the box = the feet. Add `cast` for the long low-sun shadow
  (`{"angle": 24, "length": 1.35, "width": 0.62, "blur": 1, "color": "$ink/90"}`). Small reads better: 60-140 px
  on a 1080 post. Never draw people by hand from rectangles: it looks like a stick figure.
- `cast` works on any layer (a cube, a logo, a photo cut-out): the shadow starts at the artwork's bottom edge.
- Annotated screens / "computer vision" tracking boxes: `from designassist import annotate as A` (`A.crop` places
  a region of a screenshot and returns `at()` to map UI coordinates; `A.track` = box + solid label; `A.tag`;
  `A.around(text, ctx)` = box hugging a text layer's ink, to track words of a headline). Zoomed UI text needs
  `da web shot --scale 8` captures or `max` resolution drops (no image upscaled past 1.25x).
- Isometric bands, tiles, tables, cubes: `from designassist import iso` in a build script (`iso.tile`,
  `iso.band` + `iso.prism`, `iso.on_top` for where feet / objects go). They come out as `path` layers (editable
  curves in Affinity). Colour the faces top / left / right with 3 tones of the palette (light, mid, dark), draw
  what is behind first.
- A reference = its aesthetic (palette, type, texture, motifs), not its layouts: compose each slide for its own
  message. Copying the reference's compositions was rejected (2026-10-19).

## Before showing
`da qa` clean of errors; everything aligned to something; nothing within 1-6 px of an edge or of another
element's edge (near-misses look like mistakes); consistent radius/shadow; copy proofread (accents, typos).
