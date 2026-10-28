# Facts (this project)

> Durable project facts: conventions, endpoints, gotchas, where-things-live.
> One fact per line. Uncertain = `~` prefix.
>
> SHARED — written for the whole team. NO secrets/keys/tokens (env or a password manager),
> no personal emails, and no absolute paths from anyone's machine: write paths relative to
> the repo root. A key that is public BY DESIGN (already shipped in client code) is fine —
> say why it's public on the same line.

## Where things live
- `src/designassist/`: one module per command group; a module that defines `def register(sub)` at top level adds its own `da` subcommands (cli.py finds it by scanning the source text, then imports it). Keep heavy imports inside functions so `da` starts fast.
- Core pipeline: `design.py` (format + validation + tokens/brand context) → `text.py` (layout) → `svg.py` (one Builder for preview/outlined/editable SVG) → `render.py` (resvg PNG, contact sheets). `images.py` crops/filters bitmaps once for every renderer (cache in `work/cache/`).
- Bundled assets: `assets/fonts/` (Montserrat, Caveat, Cinzel, Pinyon Script; OFL) and `assets/models/face_detection_yunet_2023mar.onnx` (MIT). `assets/user-fonts/` is gitignored.
- Per-project data: `projects/<name>/{input,work,output}` + `design.json` + `project.json`.
- Design memory (user taste + client brand kits) is NOT in this repo: `uv run da memory` prints its folder.

## Conventions
- Every `da` command prints JSON (or short text); errors are `SystemExit` with a human message.
- Paths inside json are project-relative and POSIX (`Project.rel`).
- Lengths in design.json are in the artboard unit; strings with units ("12pt", "3mm") are converted (`design.length`).
- Text line box = Figma model: glyph box centred in `size * line_height`; tracking in 1/1000 em, none after a line's last glyph.
- Colours: `$token`, `$token/40` (alpha), hex with alpha; token values may carry authored `cmyk`/`pantone` used by print exports.

## Gotchas
- fontTools `getBestCmap()` maps codepoints to glyph NAMES; HarfBuzz returns glyph IDs. Convert with `getGlyphID` (justify spacing looked for the wrong glyph until fixed, 2026-10-17).
- resvg loads the system font database slowly; previews pass `skip_system_fonts=True` because text is already outlined.
- YuNet face detection is the slow step of image prep (~seconds per call): `images.cached_focus` caches the focus point per source file + mtime, so @2x / print / PSD outputs don't re-detect (2026-10-17).
- `da export --to print` without `--artboard` skips px artboards when the project also has mm/in artboards (a feed post next to a business card shouldn't become a print PDF).

## Gotchas from the first build (2026-10-17)
- Illustrator 30.8: area text first baseline pinned with `FirstBaselineType.BASELINEFIXED` (the documented `FIXED` is invalid); SVG filters are dropped on import, so shadows are a live Drop Shadow effect (coloured shadows come out black).
- Illustrator builds record a read-back (`output/adobe/<p>-illustrator-built.json`); `da adobe pull` diffs the user's document against it, so moves/resizes map back for every layer type.
- A document mixing screen and print artboards becomes CMYK in Illustrator; pass `--artboard` for an RGB one.
- Photoshop: accent spans apply to the whole text layer; rotated/highlighted/stroked text goes in as pixels.
- Brave's headless mode hangs with no output on macOS: `web.find_browser` tries Chrome, Chromium, Edge, Playwright's headless shell, Brave last; `DA_BROWSER` overrides.
- psd-tools' stored composite ignores layer opacity/blend (Photoshop rebuilds it from the layers).
- PDF print: transparent bitmaps placed as CMYK pixels + SMask; left in RGB they showed a visible band over rich black.
- Higgsfield docs pages open with a docs-index blockquote; the model summary parser skips it (editassist's copy still has this bug as of 2026-10-17).

## Affinity (2026-10-19, Affinity 3.3.1 on macOS; built + verified live)
- Automation = Affinity's AI connector: MCP over SSE at `http://localhost:6767/sse` (IPv6 `::1` only), on only while the user enables Settings > AI connector; it was OFF again after Affinity auto-updated 3.2.3 -> 3.3.1 and restarted. No file format, no AppleScript, no CLI.
- `execute_script` returns only console.log output; the session must read the `preamble` doc topic first. Scripts touch files only under ~/Desktop (images staged in `~/Desktop/designassist-affinity/<p>/`, .af saved there and copied to output/affinity/).
- Node coordinates are document PIXELS at the doc dpi even when the document unit is mm; `NewDocumentOptions.bleed` = LTRB in the document unit (mm). `getPageBoundingBox(BleedBox)` reports the trim even with bleed set; check with `spread.getSpreadExtents({includeBleed: true})`.
- After `AddChildNodesCommandBuilder.createCommand(true)` the new node is `doc.selection.nodes.toArray()[0]` (with `false` the selection is empty). Artboards are ShapeNodes in the spread's children; insert into them by `setInsertionTarget(node)`.
- Fonts: set `StoryDelta.createPostscriptName(ps)` (`createWeight` on a variable family gave Thin). Size = `GlyphAttDoubleType.Height` in px; tracking = `CharacterSpacing` as a fraction of em (our tracking / 1000) — matches our engine to 0.1 px; leading `ParagraphLeadingType.ExactlyAbsolute` + `AbsoluteLeading` px.
- Affinity's first baseline sits ~0.742 x size below the frame top (Montserrat), higher than our Figma-style line box: the builder measures `getExactSpreadVisibleBox` after creating each frame and moves it so the ink top matches the preview.
- Rounded rects: `corner.cornerType = ShapeCornerType.Round` BEFORE `setRadius` (radius stays 0 otherwise), with `setAbsoluteSizes(true, w, h)`.
- Gradient fill transform maps the unit line (0,0)-(1,0) to spread coordinates; Transform methods apply in call order (scale, rotate, translate).
- Node definitions take a `LineStyleDescriptor`, not a `LineStyle`. The JS wrapper `PolyCurveNodeDefinition.create` takes (curve, brush, lineFill, lineStyle, transparency) in 3.3.1 while the docs list lineStyle before lineFill: the runtime reads the wrapper's own argument names (`PEN_FIRST`).
- Outer shadow: `setOuterShadowLayerEffectOffsetAngle(sel, distance, angleRadians, ...)` (pi/2 = down); its radius ~ the whole visible blur (≈1.2x our `blur`), not the SVG sigma.
- `doc.close()` discards without asking: close only documents you created, by `sessionUuid` (an unsaved build is titled "<Untitled>", not the project name).
- Affinity lists variable-font instances without PostScript names as `<default>_<Style>` (`Outfit-Thin_ExtraBold`, `Inter-Regular_Bold`, `SpaceGrotesk-Light_Bold`); the runtime maps our PostScript name via `font_requests` (family + style) when the exact name is missing (2026-10-19).
- Affinity loads fonts only at launch: `da fonts install` needs a quit/reopen, which also turns the AI connector off.
- A "\n" in our text becomes a paragraph break; Affinity's default frame style adds space before/after paragraphs, so the runtime sets SpaceBefore/SpaceAfter to 0 (second lines sat lower until then).
- `render_spread` squeezes the whole spread into 1024 px (7 carousel slides = 146 px each) and `render_selection` keeps the spread canvas; per-artboard renders use `doc.export(path, FileExportOptions.createWithPresetName("PNG"), FileExportArea.createForArtboard(node.artboardInterface))` into the Desktop stage.
- `FileExportOptions.allPresetNames` (3.3.1) includes PNG/JPEG/WebP/TIFF CMYK, "PDF (press ready)", PDF/X-1a/3/4, "PSD (preserve editability)", SVG, EPS and "Canva Design"; `da affinity export` wraps them.
- The connector sometimes answers "File not found" for the preamble while Affinity is busy (e.g. right after fonts were installed); the client retries.
- Web fonts (.woff/.woff2, e.g. taken from a client's site) are indexed by decompressing to `.cache/fonts/web/` (needs `brotli`); check `name` ID 13 for trial licences before using a font found on a website (trial = not for commercial pieces).
- `optical: true` on a text layer puts each left-aligned line's first ink at x (numbers like "1"/"4" have wide side bearings); `da qa` compares text by ink, with a 3 px tolerance between letters.

## Effects (2026-10-19)
- `texture` = ink bleed: blur SourceAlpha, add fractal noise to alpha, threshold, flood with the layer colour (solid core, rough edge; white type stays white). A plain feDisplacementMap looked like spray paint.
- feTurbulence at a whole-number baseFrequency samples only Perlin lattice points and renders FLAT (size 1 grain showed nothing): `svg.noise_freq` nudges it off integers. resvg's fractal noise has a tiny amplitude (std ~0.04): speckle grain maps it to alpha with gain 8.
- `noise` default mode "speckle" (sparse dark/light specks, alpha only) keeps the tone; "overlay" mode is vivid on saturated colour but invisible on cream.
- `da qa` contrast median-filters the background crop (5 px) so grain specks don't count as background.
- Affinity: texture/blur/noise layers become bitmaps; their opacity/blend stay live on the Affinity layer (baking them too made grain half as strong), grain is rendered 1:1 (a 2x bitmap averages away), and Affinity reads PNG alpha as STRAIGHT (premultiplying gave dark halos).
- `da web shot` takes URLs (pages with absolute asset paths need a server, e.g. `python3 -m http.server` in the site's public folder); full-page measuring still needs a local file.
- Instagram posts: the logged-out page only has a square-cropped og:image; `/p/<code>/embed/captioned/` carries every carousel image as `display_url` in `edge_sidecar_to_children` (JSON escaped 2-3 levels).

## Figures + cast shadows (2026-10-19)
- People = `figure:<pose>` svg sources (figures.py): skeleton with IK legs (feet locked to the ground), tapered limbs, drawn at 2x, unioned + softened as a raster, traced by vtracer into ONE outline; cached in `.cache/figures/v<VERSION>-<pose>.svg` (bump VERSION when the drawing changes). Hand-built figures from separate rects/paths looked like stick figures with white seams; the owner rejected them.
- Clothed proportions matter at 60-140 px: thick legs (half-width 56 at the hip), deep torso, head ~1/7 of the height. Thin limbs read as a stick man.
- `cast` (cast.py): a TRUE ground projection keeps only sin(angle) of the width (a thin line), so the body is widened across the light, smoothly from the feet (k = 1 at h = 0) so the feet stay attached. Earlier a constant affine across-vector detached the shadow from the feet.
- Vector art gets the shadow as geometry (`<id>-cast` path, nonlinear map of the bezier points); other layers use an affine matrix in the SVG. Affinity: the cast is a curve with a live Gaussian blur layer effect (`doc.setGaussianBlurLayerEffectRadius(sel, r, true)`; measured: r = 1.17 x blur x ppu - 2 doc px, the effect adds ~2 px of softness itself; matches for small blurs (shadows), blurs of 8+ units stay ~25% sharper than the preview ~).
- `cast: {}` means defaults: check `is not None and is not False`, never truthiness.
- A pure ground projection keeps -u*sin(angle) across: at angle ~0 the shadow vanished. cast eases the across offset from that (feet) to `width` x u (body).
- Isometric scenes: `iso.py` (2:1 dimetric, R=(1,0.5), L=(-1,0.5)); prism draws only side faces whose outward normal points down the screen, coloured left/right by its x sign. Draw order is the script's job (things behind first).

## Resolution (2026-10-19)
- `settings.py`: `<memory>/settings.json` holds tool knobs (resolution max|1x|2k|4k|8k; max = long side up to 3840 px, capped so photos aren't upscaled past 1.25x). `da export` without --scale obeys it; Affinity docs stay artboard size with bitmaps at the setting. `plan(doc_scale=k)` can build bigger docs (Converter.ppu = px_per_unit x k, recorded per layer for pull). Previews/QA stay 1x.
- ~ A doc_scale 2.84 Affinity build (4 artboards side by side, ~13000 px wide) lost artboards 3-5 ("artboard slide-3 not found after creation"): untested past that, see focus.md.

## Highlights, boards, deps (2026-10-19)
- Text `highlight.pad` numbers are FRACTIONS of the font size ([14, 2] made a box ~14x the size, over the whole artboard); `da validate` now warns on pad > 1.5. Strings are lengths ("12px").
- Highlight box geometry lives in `text.highlight_box` (svg, pdf, affinity_build and adobe all call it): cap height + 0.18 em, grown to the ink of every run sharing that highlight, so Ã/É/Ç stay inside and all lines keep one height. Before, the tilde of "SUBMISSÃO" sat on the background (navy on navy = read "SUBMISSAO").
- `da board` names files `board-<title slug>.jpg`; it used to always write `board.jpg` and each board overwrote the previous one.
- pytest is in `[dependency-groups] dev`, not an extra: `uv sync --extra bg` removes every extra it isn't given, so the old `dev` extra (pytest) vanished after installing background removal. Plain `uv sync` installs the dev group.
- `da image remove-bg` verified 2026-10-19 on 1080p podcast frames (rembg): clean people, some ghosts (blurred mics, mugs) as separate blobs; keep the largest connected component per person.
- Affinity layer names are bare design ids (readable in the Layers panel) and repeat across artboards. Since 2026-10-19 the reader keys its snapshot "<artboard>/<layer>" (an artboard = a node whose `artboardInterface.isArtboardEnabled` is true; `artboardInterface` itself exists on every shape node), the build's layer map and text records use the same keys, and print documents (no artboard node) get their one artboard prefixed in Python (`scoped`). Before that, `da affinity export` of 16 thumbs wrote 2 files and `pull` would have written one artboard's text edit into all 16. `pull` refuses older builds: rebuild with `da affinity open`.

## Identity work (2026-10-20)
- `colors.parse` read rgb() percentages as 0-255 values (pdftocairo/Illustrator write rgb(0%, 29%, 67%)): fixed, they scale by 2.55.
- `da brand logo <c> add logo.pdf [--page N]` extracts the vector with pdftocairo -> svgflat, drops shapes covering >=90% of the page (artboard background), crops the viewBox.
- `da web shot --root <public/>` serves the folder on a throwaway port so root-relative assets load; file:// shots of such pages were blank (the result now warns).
- `annotate.py` (crop + track + tag) = the CV-annotation look; crop regions stay in the capture's grid (`src_size`), so a 4x recapture keeps the layout.
- `da export` with `max`: artboards of the same size share the smallest scale (a carousel with one photo-limited slide came out in mixed pixel sizes).
- `A.around(text_layer, ctx, pad)` = the box of a text layer's ink (not its line box): tracking boxes around headline words (2026-10-20).
- Screen crops (group clip + oversized "fill" image) are trimmed to the visible window before resampling (`svg.trim_to_clip`, also in the PDF path): with 8x captures one export took >10 min, now ~35 s. Affinity keeps the whole image (the crop stays editable there) (2026-10-20).
- Magnified UI crops limit `max` (no image upscaled >1.25x): text zoomed ~1.2-1.9x per capture unit needs 8x captures (`da web shot --scale 8`, 10240x6880) to reach 3072x3840 (2026-10-20).

## Product carousel (2026-10-20)
- `da image extend` (imagetools.extend): push-pull fill from the photo's edges + Gaussian blur + feathered seam + matched grain; a 889x445 WhatsApp render extended to 1080x1350 with no visible seam. Product renders on a studio sweep only.
- Affinity radial fills: the gradient transform takes a non-uniform scale (rx, ry) = SVG objectBoundingBox radial; it used max(w, h) as a circle, so a wide scrim showed a hard top edge. PDF radial now squashes the CTM the same way.
- Logos extracted from PDFs end paths with "Z M x y": a subpath without segments makes Affinity's `createCurve` throw INVALID_OP and the whole logo op fails. svgflat drops lone movetos; the JS runtime skips them too.
- Instagram embed (`/p/<code>/embed/captioned/`): fetch with UA `facebookexternalhit/1.1`; a desktop Chrome UA gets the app shell with no media. Single-image posts have `"isSidecar":false` and only the EmbeddedMediaImage; carousels carry `display_url` in contextJSON. `?img_index=N` does not change the embed.
- A designer's logo PDF can hold several versions on one page (positive on white over negative on grey): `da brand logo add` keeps them all in one svg; split by fill colour by hand (see focus.md).
- Affinity 3.3.1 opened with the AI connector already on (2026-10-20): `open -a Affinity` then poll `da affinity status`.
- `da qa` warns `widow` when a wrapped paragraph (3+ lines) ends in 1-2 words under 40% of the widest line; hand-made "
" breaks are trusted (2026-10-20).
- `da affinity close --discard` refuses while `pull --dry-run` finds edits (prints them; `--force` to drop): a rebuild once discarded a document whose dry-run listed a changed layer, and Affinity keeps no backup of a discarded build (2026-10-20).
- `da image remove-bg --keep largest [--haze 190]` keeps only the biggest solid blob: drops heads and half-transparent ghosts of people standing behind a product (rembg u2net keeps them).
- A pasted Finder file shows up as a generic "PNG" icon image, not the file: the real file is usually the newest one in ~/Downloads (match the timestamp).
- Affinity text colour: `node.storyInterface.story.getGlyphAtts(0).brushFill.fill.colour.rgba8` (frames have no brushFillDescriptor). The reader records it as `text_fill`; pull compares it to the design colour (old snapshots lack it) and maps it to a token. A layer pasted onto another artboard keeps its name: pull adds it there as a copy (2026-10-20).
- `da affinity open` never saves over a .af that is open in another Affinity document (the user may be editing it): it saves `<name>-v2.af`, `-v3`... and reports that path (2026-10-20).
- `da resize` moves stacked text layers (one layer per headline line, gap <= 6% of height) as one block, and keeps the aspect of hand-placed cut-outs (role photo bigger than the canvas or fit fill/contain, scaled by sqrt(sx*sy) around the centre). Before 2026-10-21 square→story piled the lower lines onto the bottom safe edge and stretched cut-outs over the canvas. Bottom scrims/bands still keep their share of the height: for stories, end the scrim opaque above the cut-out's lower edge by hand.
- Highlight boxes (`text.highlight_box`, shared by svg, pdf, Affinity and Adobe) are centred on the capitals: the ink that pokes out of baseline..cap height (accents, Q tail, Ç, descenders) grows both sides equally. Before 2026-10-21 the box ran cap height to baseline + 0.18 em, so all-caps words sat high (~7 px above vs 23 px below at 100 px).
- `da settings set output_dir <folder>` sends deliverables to `<folder>/<project>/`: `Project.path("output", ...)` resolves there for everything except `output/preview` (previews stay in the project). Unset = `projects/<p>/output` as before (2026-10-21).
- tests/test_affinity.py staged bitmaps in the real `~/Desktop/designassist-affinity/sample/` (Affinity's sandbox folder) until 2026-10-21; an autouse fixture now points `Path.home` at tmp unless DA_AFFINITY_LIVE=1.
- `da qa` safe-zone/margin checks measure text by its INK edges: an `optical: true` line's pen origin sits left of its ink (side bearing), so a 560 px "01" with ink on the 80 px margin was flagged outside the 60 px safe zone (2026-10-23).
- `setup.sh` installs Node whenever Homebrew is present; `DA_SKIP_NODE=1 ./setup.sh` skips it (only the Adobe .jsx tests need Node) (2026-10-28).
