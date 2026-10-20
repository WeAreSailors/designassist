---
name: affinity
description: Open designs as native, editable documents in Affinity (by Canva, 3.2+): live text, shapes, curves, gradients, image layers, named layers, artboards, print documents with bleed; built live through Affinity's AI connector, rendered back to compare with the preview, and manual edits pulled back into design.json. Use for "abre no Affinity", "manda pro Affinity", "quero editar no Affinity", "arquivo .af", "ajustei no Affinity, puxa as mudanças", or whenever the user's editor is Affinity.
---
# affinity

The user's main editor (see `<memory>/preferences.md`). Affinity has no file format we can write; the
document is built INSIDE the app by a script sent through its AI connector (MCP at
`http://localhost:6767/sse`, also registered in `.mcp.json` as `affinity`).

## 0. Connector
`uv run da affinity status` → `connector: true`? If not: ask the user to open Affinity and switch on
**Settings > AI connector** (only they can; it can't be enabled from outside). It turns off when Affinity
restarts or updates: ask again then. `environment.permissions.fileSystem` must be true (scripts read the
staged images and save the .af on the Desktop).

## 1. Build
`uv run da affinity open <p> [--artboard ids]`
- px artboards → one document with one artboard each, at artboard size (vector; bitmap layers inside are rendered
  at the user's resolution setting, so scaling up on export in Affinity stays sharp); mm/in artboards → one print document each (trim
  size, dpi, bleed set; backgrounds run into the bleed).
- Text is live frame text (font by PostScript name, size, exact leading, tracking, colour, alignment, accent
  runs); shapes, gradients, curves (paths, svg logos, Lucide icons) and image layers are native; every layer
  is named with its design id. Opacity, blend modes, rotation and drop shadows (outer shadow effect) too.
- Saved as `~/Desktop/designassist-affinity/<p>/<doc>.af` (the document stays open there) and copied to
  `output/affinity/`. `--no-save` leaves it unsaved.
- Layers with `texture`, `blur` or `noise` go in as bitmaps (Affinity has no equivalent live filter here);
  everything else stays editable. Tell the user which ones.
- `cast` shadows of vector art (paths, svg, `figure:` people) are their own curve layer `<id>-cast` under the art,
  with a live Gaussian blur layer effect; on other layers the shadow is a bitmap.
- Read the JSON: `warnings` (a layer that failed), `missing_fonts` (Affinity substituted them:
  `uv run da fonts install "<Family>"`, restart Affinity), notes (layers placed as bitmaps: SVGs with
  gradients/masks/text, which svgflat can't turn into curves).
- LOOK at Affinity's own render (`work/affinity/<artboard>.png`, exported at full size per artboard; a
  single print document gives `work/affinity/<doc>.jpg`) next to `output/preview/<artboard>.png`. Text
  lines should break the same way; if a warning says "broke the lines differently", widen the text box a
  little in design.json or add a `\n`, and rebuild.

Script only (Affinity on another machine, or the connector off): `uv run da affinity script <p>` →
`output/affinity/<p>-affinity.js`; paste it in Affinity's Scripts panel. Images are referenced from the
Desktop stage folder, so run it where it was generated.

Fonts: Affinity only loads fonts at launch. After `uv run da fonts install "<Family>"` the user must quit
Affinity, reopen it and switch the AI connector on again (it turns off on restart).

## Export from Affinity
`uv run da affinity export <p> --preset png|jpg|pdf|print|pdfx4|psd|svg|canva|webp|tiff-cmyk` (or any Affinity
preset name, e.g. "PDF/X-1a:2003") → `output/affinity/export/`, one file per artboard for social documents.
`print` = Affinity's "PDF (press ready)"; `canva` = a Canva Design file the user can import into Canva.

## 2. Pull the user's edits back
After the user changes things in Affinity: `uv run da affinity pull <p> [--dry-run]` → moves, resizes, text
edits (accent `**markup**` re-applied when the words are still there) and solid fill colours of layers that
still carry their design id; group moves are applied once to the group; text colours (read from the first glyph, mapped back to a brand token when it matches); layers copied onto another artboard (same name, e.g. the logo pasted on the cover) are added there as copies. Then `uv run da render <p>`, LOOK.
Layers renamed or deleted in Affinity are reported and left alone. Repeated manual fixes = a preference
(style-profile skill).

## 3. Other things
- `uv run da affinity render <p> [--spread N]` renders the current document.
- `uv run da affinity read` dumps the named layers of the current document (boxes, text, fills).
- `uv run da affinity run <file.js>` runs any SDK script (only console.log comes back). The SDK docs for the
  installed version: `uv run da affinity docs dump` → `.cache/affinity/sdk-docs/` (read `preamble` first).
  With the `affinity` MCP server approved, its tools are also available directly (execute_script,
  render_spread, read_sdk_documentation_topic, search_sdk_hints).
- Never close or modify documents you didn't create. `uv run da affinity close <p>` closes only the documents
  built for that project (saves edits first when the document has a file; `--discard` drops them).
- Final deliverables still come from `da export` (PNG/PDF/print); Affinity can also export its own PDF/X from
  the document if the user prefers (File > Export).
