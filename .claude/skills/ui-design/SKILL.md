---
name: ui-design
description: Design UI and web: landing pages, website sections, app screens, dashboards, email layouts, link-in-bio pages — built as real HTML/CSS with the brand tokens and screenshotted at desktop and mobile sizes for review. Use for "landing page", "tela do app", "layout do site", "protótipo", "email marketing", "página de vendas".
---
# ui-design

UI is built in HTML/CSS (the medium it ships in), not in design.json. Static mockups of a screen for a
social post can still be design.json (`desktop` / `mobile` presets).

## Setup
`uv run da web new <p> <name> --kind landing|screen|email` → `projects/<p>/web/<name>/index.html` +
`tokens.css` generated from the project/brand tokens (CSS variables + @font-face for the fonts used).
Always use the variables (`var(--primary)`), never raw hex in components.

## Build
- Structure first (sections in order: hero with one clear CTA, social proof, benefits, how it works,
  pricing, FAQ, final CTA, footer) — write the copy (copywriting skill) before styling.
- Layout: CSS grid/flex, max content width 1120-1200 px, 8 px spacing scale, mobile-first media queries,
  generous section padding (80-120 px desktop, 48-64 mobile).
- Type scale with `clamp()`; body 16-18 px; line-height 1.5; headings tight.
- Components consistent: one button style per role (primary/secondary/ghost), one radius, one shadow scale.
- Images: real/stock/generated files copied next to index.html; `alt` text; `object-fit: cover`.
- Icons: inline SVG from `uv run da icon get <name> --project <p>`.
- Accessibility: contrast AA (`uv run da color contrast`), focus styles, semantic tags, labels on inputs.
- Email: tables + inline styles, 600 px wide, web-safe font fallbacks, no JS, bulletproof buttons.

## Review
`uv run da web shot <p> projects/<p>/web/<name>/index.html --sizes 1440x900,390x844 --full-page` → PNGs;
LOOK at both (desktop and mobile), fix, repeat. Pages from a real site that load root-relative assets
(`/css/app.css`) come out blank from a file: add `--root <the site's public folder>` (the JSON warns). For product
screens used inside a piece, shoot at `--scale 4` so `max` resolution exports stay sharp. Show the user the screenshots and the file path (they can
open index.html in a browser). For hand-off to developers: the HTML/CSS is the spec; add a `README.md`
in the page folder with tokens, fonts and breakpoints.
