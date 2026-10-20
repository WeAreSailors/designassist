---
name: mockup
description: Show designs in context for approval and portfolios: Instagram feed frame, phone screen, poster on a wall, business card, or the user's own scene photo (perspective placement; green-screen auto detection). Use for "mockup", "mostra aplicado", "como fica no celular", "apresentação pro cliente", "coloca no cartaz".
---
# mockup

- Built-in (no photo needed): `uv run da mockup <p> --art <artboard> --builtin post-feed|phone|poster|card`
  → `output/mockups/`.
- Real scene: the user's photo (or a stock/generated one) with a flat surface:
  `uv run da mockup <p> --art <artboard> --scene input/parede.jpg --corners x1,y1,x2,y2,x3,y3,x4,y4`
  (corners clockwise from top-left, in scene pixels: open the photo with your image reader and estimate,
  then check the result and adjust).
- Green-screen scenes: `--auto` finds a flat bright green quad and replaces it. To generate one: image-gen
  skill, prompt "... holding a blank poster, the poster is solid pure green #00FF00, flat, evenly lit".
- Stock scenes: stock-photo skill ("blank poster wall", "hand holding phone", "business card mockup").

LOOK at the result: perspective right, no green fringe, lighting believable. Mockups are for presentation —
the deliverable is still the exported file.
