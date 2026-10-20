---
name: icons
description: Find and use icons (Lucide, 1,500+ open-source line icons) consistently in posts, carousels, infographics and UI; recolour, size and stroke them to match the type. Use for "coloca ícones", "ícone de...", "infográfico", "lista com ícones".
---
# icons

- Search (English keywords): `uv run da icon search "delivery truck"` → names + tags.
- Use in design.json: `{"id": "ic1", "type": "icon", "name": "truck", "x": 80, "y": 400, "w": 64, "h": 64,
  "color": "$primary", "stroke_width": 2}`. For HTML: `uv run da icon get truck --project <p>` → svg file.
- Consistency: one icon set per piece, one stroke width (match the text weight: 1.5 for regular text, 2-2.5
  next to bold), one size per role, optical alignment with the first line of text (centre on the x-height).
- Icons in containers (circle/rounded square behind) look finished: same container for all.
- An icon is not a logo: client and third-party logos come from them (brand kit), never from an icon set.
