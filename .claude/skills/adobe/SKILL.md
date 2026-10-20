---
name: adobe
description: Open designs as editable documents in Adobe Illustrator or Photoshop (native text, shapes, swatches, named layers), run them live in the open app, read the user's manual changes back into design.json, and fix font issues. Use for "abre no Illustrator", "manda pro Photoshop", "quero o arquivo editável", "ajustei no Illustrator, puxa as mudanças", "AI/PSD editável".
---
# adobe

- Status: `uv run da adobe status` (installed / running apps).
- Fonts first: Adobe apps only use INSTALLED fonts. The export lists `fonts_missing`; install them with
  `uv run da fonts install "<Family>"` and restart the app, or the text falls back to another font.
- Build live: `uv run da adobe open <p> --app illustrator [--artboard ids]` → a new document in the running
  app (launches it if needed). Photoshop: `--app photoshop` (one document per artboard, text layers live,
  other layers as smart objects).
- Script only (for another machine): `uv run da export <p> --to illustrator photoshop` → `output/adobe/*.jsx`
  (File > Scripts > Other Script…). Assets are referenced by absolute path, so run it on this machine or
  re-export there.
- Layers/items are named with the design layer ids. Never close or modify the user's other open documents.
- Pull manual changes back: after the user edits in Illustrator, `uv run da adobe pull <p> --app illustrator`
  updates design.json (texts, positions/sizes, shape colours of items still named with layer ids) and reports
  what changed; then `da render` and LOOK. To just inspect: `uv run da adobe read --app illustrator`.
- Illustrator first-baseline and Photoshop text boxes can differ by a pixel or two from the preview;
  compare an exported PNG from the app with `da render` when precision matters.
Learn from their manual edits: if they always nudge the same thing (bigger logo, tighter leading), save it as
a preference (style-profile skill).
