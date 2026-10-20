# designassist

An AI designer that runs inside Claude Code (or Codex). You describe the piece, drop the photos, logos and
brief in a folder, and the agent writes the copy, lays it out, picks or generates the images, checks it, and
hands you finished files — PNG/JPG/WebP, SVG, PDF, a **print-ready CMYK PDF with bleed and crop marks** — or an
editable document built live in **Affinity** (live text, shapes, curves, named layers), **Illustrator** or **Photoshop**.

Social media pieces, carousels and ad sets · logos, palettes, type and brand guides · landing pages and app
screens · business cards, flyers and posters.

```
 brief + photos + logos
        │
        ▼
 ┌─────────────── the engine ───────────────┐
 │  Claude Code / Codex  (reads CLAUDE.md)  │
 │        │ follows                         │      ┌─ PNG · JPG · WebP · SVG
 │        ▼                                 │      │
 │  skills  (.claude/skills/*, 33 recipes)  │      ├─ PDF (screen) · print PDF (CMYK, bleed, marks)
 │        │ calls                           │ ───► │
 │        ▼                                 │      ├─ Affinity (native document, built live) · Illustrator
 │  `da` CLI  ── text engine · resvg ·      │      │
 │              reportlab · Higgsfield ·    │      ├─ Photoshop (text layers + smart objects) · PSD
 │              Pexels/Unsplash · Lucide    │      │
 │        │                                 │      └─ HTML/CSS screens · design tokens · ASE swatches
 │        ▼                                 │
 │  projects/<name>/ design.json            │
 └──────────────────────────────────────────┘
        ▲                     │
        └── memory ◄── your feedback (taste, client brand kits, named styles)
```

The agent looks at every render before showing it to you (it can read images), runs automatic checks
(overflow, contrast, safe zones, print dpi and bleed), and learns your taste and each client's brand as you
correct it.

Works on **macOS, Windows and Linux** (CI runs the test suite on all three).

## Setup

You need [Claude Code](https://claude.com/claude-code) (or Codex). The setup script installs the rest (uv and
the Python dependencies).

**macOS / Linux**
```bash
git clone https://github.com/edunascimentt/designassist.git && cd designassist
./setup.sh
```

**Windows** (PowerShell)
```powershell
git clone https://github.com/edunascimentt/designassist.git; cd designassist
powershell -ExecutionPolicy Bypass -File setup.ps1
```

**Easiest: let the agent do it.** Open Claude Code in the folder (`claude`) and say "configura o designassist".
The `designassist-setup` skill installs what's missing (asking first), collects and validates your API keys
without exposing them, checks Illustrator/Photoshop, fonts and the CMYK profile, records your design
preferences and runs the self-test.

Keys (all optional) go in `.env`:

| Key | For | Where |
|---|---|---|
| `HF_API_KEY_ID` + `HF_API_KEY_SECRET` | AI images (photoreal, illustration, text-in-image, vector style, edits) | console.higgsfield.ai |
| `PEXELS_API_KEY` | stock photos (free) | pexels.com/api |
| `UNSPLASH_ACCESS_KEY` | stock photos (free) | unsplash.com/developers |
| `DA_CMYK_ICC` | your print shop's CMYK profile (default: Coated FOGRA39 when Creative Cloud is installed) | your print shop |

Check everything with `uv run da doctor` and `uv run da keys --check`. `uv run da selftest` runs the tests.

## Affinity

Affinity (by Canva, free, 3.2+) is the main editable target. It has no file format anyone else can write, so
designassist builds the document **inside the running app** through Affinity's own AI connector:

1. In Affinity: **Settings > AI connector** on (only you can switch it on; it turns off when Affinity restarts
   or updates).
2. `uv run da affinity open <project>` (or just ask: "abre no Affinity"). Social artboards become one
   document with artboards; print pieces become documents in mm with bleed. Text stays live (same fonts,
   leading, tracking and line breaks as the preview), shapes/curves/gradients are native, every layer is
   named after its design id. The `.af` is saved in `~/Desktop/designassist-affinity/<project>/` and copied to
   `output/affinity/`.
3. Edit in Affinity, then "puxa as mudanças" (`uv run da affinity pull <project>`): moves, resizes, text and
   colours come back into `design.json`.

`.mcp.json` also registers the connector as the `affinity` MCP server, so Claude Code can call Affinity's SDK
tools directly. Scripts may only touch the Desktop, which is why images are staged there.

## Using it

```bash
claude            # inside the designassist folder
```

> Novo projeto "promo-outubro" pro cliente Vulcano. Post 4:5 e story anunciando 30% off em pneus até
> dia 31, com a foto que está no input. Usa a marca deles.

> Cria uma logo pra uma cafeteria chamada "Grão Norte": aconchegante, artesanal, funciona pequena.
> Me mostra 3 caminhos.

> Cartão de visita 9x5 frente e verso pra Ana Souza, arquivo pra gráfica.

> Carrossel de 7 slides pro LinkedIn: "5 erros ao precificar freelas", exporta em PDF.

> Landing page pro curso, desktop e mobile, nas cores da marca.

The agent creates `projects/<name>/`, tells you where to drop files, asks only what's missing from the brief,
shows renders with a short rationale and applies your notes. Anything you correct twice ("logo maior",
"nunca degradê") becomes the default next time — for that client or for everything.

## Memory

designassist ships with [memory-os](https://github.com/edunascimentt/memory-os) in `vendor/memory-os/`: two
tiers split by who may read them.

| | where | holds | shared? |
|---|---|---|---|
| **Your design taste + client brand kits** | memory-os global tier, `~/.memory-os/memory/designassist/` | preferences, named styles, per-client preferences, brand kits (colours with CMYK/Pantone, fonts, logos, rules), delivery log | private: yours only, every Claude account you use, never committed |
| **Project knowledge** | `.claude/_memory/` in this repo | how the code works, gotchas, decisions, what's unverified | committed: everyone who clones gets it |

Install your private tier once with `uv run da memory --install` (copies `vendor/memory-os` to `~/.memory-os`, no
download); a session-start notice reminds you if it's missing. Without it, your taste is kept in the gitignored
`memory/` folder and `da memory --init` migrates it later.

## Skills

| Stage | Skill | What it does |
|---|---|---|
| Brief | `brief` | objective, audience, formats, copy, mandatory elements; 2-3 concepts when open |
| | `moodboard` | references → board + palette strip + written direction |
| | `copywriting` | headlines, CTAs, carousel scripts, post captions (pt-BR default) |
| Craft | `layout` | grid, hierarchy, type scale, scrims, the build → render → look loop |
| Social | `social-post` | feed posts, stories, Reels covers, pins |
| | `carousel` | hook → content → CTA systems; PNGs or LinkedIn PDF |
| | `thumbnail` | YouTube thumbnails readable at 168 px, A/B variants |
| | `ad-set` | one master → every ad size (`da resize`) |
| | `batch-series` | many pieces from a table (menus, price lists, team cards) |
| Identity | `logo` | routes, vector construction, small-size and one-colour tests |
| | `palette` | extract, harmonies, scales, contrast, CMYK |
| | `typography` | choose, pair, get Google fonts, install for Adobe, set type |
| | `brand-kit` | client kit in the private memory: colours, fonts, logos, rules, logo pack |
| | `brand-guide` | manual de marca as PDF from the kit |
| | `mockup` | feed / phone / poster / card mockups, or your own scene photo |
| UI / web | `ui-design` | landing pages, screens, emails in HTML/CSS, desktop + mobile screenshots |
| | `design-system` | tokens, scales, component sheet; CSS / Tailwind / JSON / ASE |
| Print | `print-ready` | mm, 300 dpi, bleed, margins, CMYK, rich black, crop marks, preflight |
| Images | `stock-photo` | Pexels / Unsplash search with contact sheets, credits kept |
| | `image-gen` | Higgsfield images with cost estimate first |
| | `photo-edit` | smart crop, cut-outs, duotone/tint/B&W, upscale, print-dpi check |
| | `vectorize` | raster logo → clean SVG |
| | `icons` | Lucide icons, consistent stroke and size |
| Delivery | `export` | the right format per destination (Instagram, LinkedIn, web, print shop, Canva, Affinity, Adobe) |
| | `affinity` | build a native Affinity document live, render it back, pull manual edits |
| | `adobe` | open live in Illustrator / Photoshop, pull manual edits back |
| | `handoff` | package + spec sheet + delivery message, logged |
| Setup | `designassist-setup` | guided install, keys (validated, never echoed), apps, fonts, self-test |
| Meta | `qa` | overflow, glyphs, contrast, safe zones, dpi, bleed, fonts, alignment |
| | `review` | apply feedback on a version, learn from it |
| | `style-profile` | maintain the memory: preferences, client files, named styles |
| | `preferences-quiz` | short questionnaire that fills your design preferences |
| | `sync` | two-way team sync with GitHub |

## CLI

The agent drives these, but you can run them yourself (`uv run da <command> -h` for options):

```
da new <name> [--client <Name>] [--preset ig-post ig-story]      da presets [--kind social|print|web|identity]
da info <p>    da validate <p>    da layout <p> <artboard> <layer>    da artboard <p> add|duplicate|remove
da render <p> [--artboard ...] [--scale 2] [--bleed]             da qa <p> [--strict]
da version <p> save|list|restore                                  da resize <p> --from <ab> --to <presets...>
da batch <p> --template <ab> --data rows.csv [--render]
da export <p> --to png jpg webp svg svg-outlined pdf print psd affinity illustrator photoshop [--scale] [--quality]
da package <p> [--zip]
da affinity status | open|script|pull|close <p> | render | read | run <file.js> | docs [topic|dump]
da adobe status | script|open <p> --app illustrator|photoshop | read --app ... | pull <p> --app ...
da color contrast|palette|scale|harmony|cmyk|check ...            da tokens <p> --to css scss tailwind json ase
da fonts list|find|get|install|pair ...                           da icon search|get ...
da stock <p> "<query>" [--download 1,3]                           da hf models|schema|estimate|generate|fetch ...
da image info|crop|remove-bg|upscale|vectorize|faces ...          da mockup <p> --art <ab> --builtin ...|--scene ...
da board <p> <refs...>                                            da web new|shot ...
da client list|new|set|show    da brand show|set|logo|logo-pack|guide ...
da memory [--init|--install]   da keys [--check] | da keys set NAME   da doctor   da selftest
```

## Project folder

```
projects/<name>/
  input/          your photos, logos, brief, references (never modified)
  work/           image cache, previews, stock/generated images, versions/, credits.json
  design.json     the design (simple JSON, documented in src/designassist/design.py)
  output/         renders and deliverables: png/jpg/webp/svg/pdf, print/, adobe/, package/
```

`projects/`, your design memory and client brand kits are never committed.

## Development

```bash
uv sync
uv run pytest -q -m "not network"     # synthetic images, no API keys needed
```

The Illustrator/Photoshop scripts are tested against DOM mocks in `tests/*_mock.js` (needs Node).

## Limits worth knowing

- Rendering never uses system fonts: text is shaped and outlined by designassist's own engine (HarfBuzz +
  fontTools), so a design looks the same everywhere. Illustrator/Photoshop need the fonts installed
  (`da fonts install`).
- Emoji and colour fonts aren't rendered (the glyph is reported missing).
- Print PDFs are CMYK with bleed, marks and boxes, but not certified PDF/X; ask the print shop if they require it.
- Affinity builds need the AI connector switched on in the app; SVG artwork with gradients, masks or text is
  placed as a bitmap layer instead of curves.
- Photoshop builds were tested against a mock only (no Photoshop on the dev machine).
- Background removal needs the optional `bg` extra (onnxruntime + a ~170 MB model).

## Licenses

- Code: MIT (`LICENSE`).
- `assets/fonts/`: SIL Open Font License (`assets/fonts/OFL*.txt`).
- `assets/models/` YuNet face detector: MIT (opencv_zoo).
- Lucide icons (downloaded on use): ISC.
