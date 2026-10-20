---
name: stock-photo
description: Find and license-check free stock photos (Pexels, Unsplash) for a piece: search with good queries, look at a numbered contact sheet, download the chosen ones and keep the credits. Use for "procura uma foto de...", "foto de banco de imagem", "imagem pra usar no post", or when a layout needs a photo the user didn't provide.
---
# stock-photo

Order of preference: the client's own photos (always ask first: authentic beats stock) > stock > generated.

1. Query in English, concrete, with the mood and composition you need: "woman laughing coffee shop warm
   light", "empty desk top view minimal", "copy space left". Orientation matching the frame:
   `uv run da stock <p> "<query>" --orientation portrait --n 12` (Pexels; `--source unsplash` for more editorial).
2. LOOK at `work/stock/<query>/sheet.jpg` (numbered). Choose for: space for text where the layout needs it,
   subject direction (facing into the layout), lighting/colour fitting the palette, not cliché (no
   handshake-in-suit), diversity that fits the audience. Several queries are normal.
3. Download: `uv run da stock <p> "<query>" --download 3,7` → `work/stock/…`, credits in `work/credits.json`.
4. Use as an image layer (`fit: cover`, `focus`), unify with `filters` (duotone/tint/saturation) when mixing
   sources.
Licences: Pexels and Unsplash allow commercial use without attribution, but not reselling the photo as is,
implying endorsement by people shown, or trademark use. Mention the credit when the client asks.
Keys: PEXELS_API_KEY / UNSPLASH_ACCESS_KEY (designassist-setup skill).
