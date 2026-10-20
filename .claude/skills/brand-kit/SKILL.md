---
name: brand-kit
description: Create or update a client's brand kit in the private design memory (colours with HEX/CMYK/Pantone, fonts, logo files and variations, rules), so every piece for that client uses it automatically via `"brand": "<client>"`. Use for "cadastra a marca do cliente", "essas são as cores da marca", "salva o logo", "usa a identidade da X", or when a client project has no kit yet.
---
# brand-kit

Kits live in `<memory>/clients/<slug>/brand/` (private, never in the repo). design.json `"brand": "<slug>"`
makes the kit's colours/fonts tokens and its logos `brand:<name>` sources.

## Create / fill
1. `uv run da client new "<Client Name>"` (or `da new <p> --client "<Name>"`).
2. Colours — from the client's manual if they have one (ask for the file: PDF or images in `input/`; read
   it), else from the logo: `uv run da color palette input/logo.png`. Name by ROLE, not hue:
   `primary`, `secondary`, `accent`, `ink` (text), `paper` (background), `muted`:
   `uv run da brand set <slug> --color primary=#E30613 --cmyk primary=0,100,95,0 --pantone primary="485 C"`.
   Only record CMYK/Pantone the client gave you; never invent Pantone matches.
3. Fonts: `uv run da brand set <slug> --font display="Montserrat:800" --font body="Inter:400"`. Licensed
   client fonts: copy the files into `<memory>/clients/<slug>/brand/fonts/` (they're found automatically).
   Google fonts: `uv run da fonts get "<Family>"`.
4. Logos: `uv run da brand logo <slug> add input/logo.svg --name logo` (+ `logo-white`, `symbol`,
   `logo-horizontal`…). SVG beats PNG. A designer's `logo.pdf` / `.ai` goes in directly: the page's vector is
   extracted, the artboard background dropped and the box cropped (`--page N` for the other versions; needs
   poppler's `pdftocairo`). Only a raster logo? Vectorise it (vectorize skill) and confirm with
   the user that the trace is faithful.
5. Rules: `uv run da brand set <slug> --rule "logo sempre no canto superior esquerdo"` — clear space,
   minimum size, forbidden combos, tone of voice notes.
6. Variations for the client: `uv run da brand logo-pack <slug> --logo logo` (SVG/PDF/PNG sizes, mono,
   white, favicon set).
7. `uv run da brand show <slug>` and summarise it to the user.

Client taste that isn't a token (likes minimal layouts, hates gradients, approvals go through Maria) goes to
`<memory>/clients/<slug>/preferences.md` (style-profile skill).
