---
name: photo-edit
description: Prepare photos for layouts: inspect resolution/print size, smart crop to an aspect around faces, remove backgrounds (cut-outs), upscale, colour treatments (duotone, tint, B&W, brightness/contrast/saturation, blur) applied non-destructively in design.json. Use for "recorta a pessoa", "tira o fundo", "deixa preto e branco", "melhora essa foto", "essa foto serve pra impressão?".
---
# photo-edit

Non-destructive first: most treatments are layer properties, so the original in `input/` never changes.

- Inspect: `uv run da image info input/<file>` (px, faces, effective size at 300 dpi). Print needs ≥ 300 dpi
  at the placed size; social needs ≥ the artboard px.
- Crop in the layout: `fit: "cover"` + `focus: "face"` | `"top"` | `[fx, fy]` on the image layer. A separate
  cropped file when needed elsewhere: `uv run da image crop input/<file> -p <p> --aspect 4:5 --focus face`.
- Treatments (image layer `filters`): `{"grayscale": true}`, `{"duotone": ["$ink", "$primary"]}`,
  `{"tint": "$primary/30"}`, `{"brightness": 1.1, "contrast": 1.15, "saturation": 0.9}`, `{"blur": 12}` for
  backgrounds. Mixed photos in a set: the same duotone/tint unifies them.
- Shapes: `radius`, `mask: "circle"` for avatars.
- Cut-out: `uv run da image remove-bg input/<file> -p <p>` → `work/cutouts/<name>.png` (needs `uv sync --extra bg`
  the first time; downloads a model ~170 MB). Check edges (hair) with your image reader at 100%.
- Upscale: `uv run da image upscale <file> -p <p> --x 2` (classic resampling, not AI; for real detail use an
  image-gen upscaler and say it's generated detail).
- Extend (outpaint a studio shot to a new aspect, no AI): `uv run da image extend <file> -p <p> --aspect 4:5
  --width 1080 --x 1.2 --place 0.5,0.62` → `work/extended/`. The background continues from the photo's own edge
  colours, seam feathered, grain matched. For wide product renders on plain/sweep backgrounds that must fill a
  4:5 post with room for type; LOOK at the seams zoomed. Busy backgrounds (rooms, people) need image-gen instead.
- Retouching beyond this (skin, object removal): image-gen edit endpoints, or tell the user it's a Photoshop
  job and export the file there (adobe skill).
