---
name: image-gen
description: Generate images with Higgsfield (80+ models: photoreal, illustration, text-in-image, vector-style, image edit/reference, product shots, backgrounds, mockup scenes) with cost estimates before spending. Use for "gera uma imagem", "cria uma ilustração", "fundo pro post", "foto de produto com IA", "edita essa foto com IA", or when neither the client's photos nor stock fit.
---
# image-gen

Paid: say what you'll generate and the estimated cost before generating more than a couple of images;
reuse files in `work/generated/`. Above `DA_HF_MAX_USD` (default $2) the command needs `--yes` after the
user's OK.

1. Pick a model: `uv run da hf models --kind image` (cached docs from docs.higgsfield.ai). Rough guide:
   photoreal people/products → soul / seedream-like photo models; text inside the image (signs, packaging)
   → ideogram; flat/vector-style illustration and icons → recraft; edit an existing photo (change
   background, add object, restyle) → an edit/reference endpoint with `--file image_url=input/<photo>`.
2. Read its parameters: `uv run da hf schema <endpoint>`; write `work/hf/<name>.json` args (prompt,
   aspect ratio matching the artboard, count 2-4 for choice).
3. Prompt like an art director: subject, action, setting, lighting, lens/angle, palette (use the brand
   colours by name/hex), style, composition ("subject on the right third, empty space on the left for text"),
   and what to avoid. Never ask for real people's likeness, logos or trademarks of others.
4. `uv run da hf estimate <endpoint> --args work/hf/<name>.json` → tell the user → `uv run da hf generate <p> <endpoint> --args ...`.
   Long jobs: `uv run da hf fetch <p> <request_id>`.
5. LOOK at every result; check hands, text, artefacts, faces. Upscale only when needed for print
   (`uv run da image upscale`, or a Higgsfield upscaler when available). Vector-style results for logos/icons:
   vectorize skill.
Record what worked (model + prompt pattern) in `<memory>/preferences.md` when the user likes it.
