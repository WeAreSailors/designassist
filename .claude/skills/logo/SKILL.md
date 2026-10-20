---
name: logo
description: Design logos and visual marks: discovery, concept routes (wordmark, lettermark, symbol + wordmark, emblem), vector construction directly in SVG/design.json paths, optional AI-generated sketches vectorised, testing at small sizes and in one colour, and delivering the variations. Use for "cria uma logo", "logotipo", "marca nova", "redesenho da logo", "símbolo".
---
# logo

A logo is a system of decisions, not a picture. Vector from the start.

## 1. Discovery (brief skill + these)
Name and what it does, 3 personality adjectives, audience, competitors (to differ from), where it will live
(app icon? embroidery? façade?), must-haves/no-gos, colour preferences. Moodboard if they have references.

## 2. Routes (show 3, one line each, then build)
- **Wordmark**: the name in a chosen/customised typeface (tracking, a modified letter, ligature).
- **Lettermark / monogram**: initials, for long names or app icons.
- **Symbol + wordmark**: an icon built from a simple idea (initial + meaning), lockups horizontal & stacked.
- **Emblem/badge**: text inside a shape (cafés, breweries, sports).

## 3. Build in vector
- Artboards `logo` / `logo-wide` (`uv run da artboard <p> add --preset logo --id logo-a`). Build with
  `path` layers (write SVG path data yourself: geometric construction on a grid, circles/rects, arcs),
  `ellipse`, `rect`, and `text` for wordmarks (try several fonts: `uv run da fonts find <style>`,
  `uv run da fonts get "<Family>"`; `da fonts pair` for a tagline).
- Wordmark refinement: tracking, size the symbol to the cap height (`da layout` gives metrics), optical
  alignment (round letters overshoot).
- AI sketches only as inspiration or when the user asks: image-gen skill (vector-style models), then
  `uv run da image vectorize <file> -p <p> --mode logo --colors 2` and clean it; never ship a raw trace.
- Avoid: thin hairlines, gradients as the only version, more than 2-3 colours, generic clip-art
  (lightbulbs for "ideas"), anything that resembles a known brand (check and tell the user).

## 4. Test (render and LOOK)
- Small: duplicate an artboard at 32x32 / 64x64 px (`favicon` preset scaled) — still recognisable?
- One colour: black on white and white on the brand colour (`color` on an svg layer, or duplicate with
  fills changed). The mark must work in 1 colour.
- In context: `uv run da mockup <p> --art logo-a --builtin card` (and a social avatar with `avatar` preset).

## 5. Deliver
Export the final as SVG (editable + outlined) and PDF: `uv run da export <p> --to svg svg-outlined pdf`,
Illustrator file for the client (`--to illustrator`). Save it into the brand kit
(`uv run da brand logo <slug> add output/<logo>.svg --name logo`) and run `uv run da brand logo-pack <slug>`.
Then brand-guide skill when they want the manual.
