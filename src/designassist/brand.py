"""Client brand kits, kept in the private design memory (never in the repo):

<memory>/clients/<slug>/
  preferences.md        how this client likes things (tone, do/don't, approvals) — read on their projects
  brand/brand.json      tokens + logos, used by design.json "brand": "<slug>"
  brand/logo*.svg|png   logo files referenced by brand.json "logos"
  brand/fonts/          the client's licensed fonts (searched before everything else)

brand.json:
{
  "name": "Vulcano Motors",
  "colors": {"primary": {"hex": "#E30613", "cmyk": [0, 100, 95, 0], "pantone": "485 C"}, "ink": "#141414", "paper": "#FFFFFF"},
  "fonts": {"display": {"family": "Montserrat", "weight": 800}, "body": {"family": "Montserrat", "weight": 400}},
  "logos": {"logo": "logo.svg", "logo-white": "logo-white.svg", "symbol": "symbol.svg"},
  "rules": ["logo always top-left or bottom-centre", "never red text on black"]
}
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date
from pathlib import Path

from .project import ROOT, Project, memory_dir, read_json, write_json


def client_slug(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    if not s:
        raise SystemExit(f"can't make a folder name from {name!r}")
    return s


def clients_dir() -> Path:
    return memory_dir() / "clients"


def client_dir(slug: str) -> Path:
    return clients_dir() / slug


def brand_dir(slug: str) -> Path:
    return client_dir(slug) / "brand"


def all_clients() -> list[str]:
    d = clients_dir()
    return sorted(p.name for p in d.iterdir() if p.is_dir() and not p.name.startswith("_")) if d.is_dir() else []


def load(slug: str) -> dict | None:
    return read_json(brand_dir(slug) / "brand.json")


def save(slug: str, kit: dict) -> None:
    write_json(brand_dir(slug) / "brand.json", kit)


def create(name: str) -> dict:
    """Client folder with preferences.md (from the template) and an empty brand kit."""
    slug = client_slug(name)
    d = client_dir(slug)
    created = not d.exists()
    d.mkdir(parents=True, exist_ok=True)
    prefs = d / "preferences.md"
    if not prefs.exists():
        tpl = memory_dir() / "clients" / "_template" / "preferences.md"
        if not tpl.exists():
            tpl = ROOT / "memory.template" / "clients" / "_template" / "preferences.md"
        text = tpl.read_text(encoding="utf-8") if tpl.exists() else "# {name}\n"
        prefs.write_text(text.replace("{name}", name).replace("{date}", date.today().isoformat()), encoding="utf-8")
    if load(slug) is None:
        save(slug, {"name": name, "colors": {}, "fonts": {}, "logos": {}, "rules": []})
    (brand_dir(slug) / "fonts").mkdir(parents=True, exist_ok=True)
    return {"client": slug, "dir": str(d), "created": created, "brand": str(brand_dir(slug) / "brand.json")}


def client_of(project: Project) -> str | None:
    c = project.settings.get("client")
    if c:
        return client_slug(c)
    d = read_json(project.path("design.json"), {}) or {}
    return d.get("brand")


def show(project: Project) -> dict:
    """What to read before working on a project, in order (later overrides earlier)."""
    mem = memory_dir()
    files = [mem / "preferences.md"]
    slug = client_of(project)
    if slug:
        files += [client_dir(slug) / "preferences.md", brand_dir(slug) / "brand.json"]
    return {"client": slug, "read_in_order": [str(f) for f in files if f.exists()],
            "missing": [str(f) for f in files if not f.exists()]}


# --- editing the kit -------------------------------------------------------------------------

def _require(slug: str) -> dict:
    kit = load(slug)
    if kit is None:
        raise SystemExit(f"no brand kit for {slug!r} (`da client new \"<Name>\"` creates it)")
    return kit


def _pairs(items: list[str] | None, what: str) -> list[tuple[str, str]]:
    out = []
    for it in items or []:
        if "=" not in it:
            raise SystemExit(f"--{what} wants name=value, got {it!r}")
        k, v = it.split("=", 1)
        out.append((k.strip(), v.strip()))
    return out


def set_values(slug: str, colors: list[str] | None = None, cmyk: list[str] | None = None,
               pantone: list[str] | None = None, fonts: list[str] | None = None, rules: list[str] | None = None,
               name: str | None = None) -> dict:
    """Update tokens: colours (hex, + authored CMYK / Pantone), fonts ("Family:weight[:italic]"), rules."""
    from . import colors as C

    kit = _require(slug)
    cols = kit.setdefault("colors", {})

    def entry(k: str) -> dict:
        v = cols.get(k)
        return dict(v) if isinstance(v, dict) else ({"hex": v} if v else {})

    for k, v in _pairs(colors, "color"):
        c = C.parse(v, cols)
        e = entry(k)
        e["hex"] = c.hex if c.a == 1 else v
        cols[k] = e if len(e) > 1 else e["hex"]
    for k, v in _pairs(cmyk, "cmyk"):
        vals = [float(x) for x in re.split(r"[,\s]+", v) if x]
        if len(vals) != 4 or not all(0 <= x <= 100 for x in vals):
            raise SystemExit(f"--cmyk {k}: four numbers 0-100, got {v!r}")
        e = entry(k)
        if "hex" not in e:
            raise SystemExit(f"--cmyk {k}: set the colour first (--color {k}=#...)")
        e["cmyk"] = vals
        cols[k] = e
    for k, v in _pairs(pantone, "pantone"):
        e = entry(k)
        if "hex" not in e:
            raise SystemExit(f"--pantone {k}: set the colour first (--color {k}=#...)")
        e["pantone"] = v
        cols[k] = e
    for k, v in _pairs(fonts, "font"):
        parts = v.split(":")
        spec: dict = {"family": parts[0].strip()}
        if len(parts) > 1 and parts[1].strip():
            spec["weight"] = int(parts[1])
        if len(parts) > 2 and parts[2].strip().lower() in ("italic", "i", "1", "true"):
            spec["italic"] = True
        kit.setdefault("fonts", {})[k] = spec
    for r in rules or []:
        if r not in kit.setdefault("rules", []):
            kit["rules"].append(r)
    if name:
        kit["name"] = name
    save(slug, kit)
    return {"client": slug, "brand": kit}


def describe(slug: str) -> dict:
    kit = _require(slug)
    d = brand_dir(slug)
    files = sorted(p.relative_to(d).as_posix() for p in d.rglob("*") if p.is_file() and p.name != "brand.json")
    missing = [f"{k}: {v}" for k, v in kit.get("logos", {}).items() if not (d / v).exists()]
    return {"client": slug, "dir": str(d), "brand": kit, "files": files, "missing_logo_files": missing,
            "preferences": str(client_dir(slug) / "preferences.md")}


def svgflat_unsupported():
    from .svgflat import Unsupported

    return Unsupported


def pdf_logo_svg(pdf: Path, page: int = 1) -> str:
    """A vector logo out of a PDF page (Illustrator exports, a designer's logo.pdf): the page's shapes as one
    flat SVG, the full-page background dropped and the viewBox cropped to the artwork. Needs poppler's
    pdftocairo; gradients or text left as text raise svgflat.Unsupported (keep the PDF and ask for an SVG)."""
    import shutil
    import subprocess
    import tempfile
    import xml.etree.ElementTree as ET

    from . import svgflat

    exe = shutil.which("pdftocairo")
    if not exe:
        raise SystemExit("reading a PDF logo needs poppler's pdftocairo (macOS: brew install poppler; "
                         "Linux: apt install poppler-utils; Windows: choco install poppler)")
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "page.svg"
        r = subprocess.run([exe, "-svg", "-f", str(page), "-l", str(page), str(pdf), str(out)], capture_output=True, text=True)
        if r.returncode or not out.exists():
            raise SystemExit(f"{pdf.name} page {page}: {(r.stderr or 'pdftocairo failed').strip()[-300:]}")
        text = out.read_text(encoding="utf-8")
    vb = svgflat.viewbox(ET.fromstring(text))
    shapes = svgflat.flatten_file(text, vb[0], vb[1], vb[2], vb[3], "fill")
    page_area = vb[2] * vb[3]
    keep = []
    for sh in shapes:
        pts = [(seg[i], seg[i + 1]) for sp in sh.subpaths for seg in sp for i in range(1, len(seg), 2)]
        if not pts:
            continue
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        if (max(xs) - min(xs)) * (max(ys) - min(ys)) >= 0.9 * page_area:  # the page background
            continue
        keep.append((sh, min(xs), min(ys), max(xs), max(ys)))
    if not keep:
        raise SystemExit(f"{pdf.name} page {page}: no artwork besides the background")
    x0, y0 = min(k[1] for k in keep), min(k[2] for k in keep)
    x1, y1 = max(k[3] for k in keep), max(k[4] for k in keep)
    paths = []
    for sh, *_ in keep:
        d = " ".join("Z" if seg[0] == "Z" else seg[0] + " ".join(f"{v:.2f}" for v in seg[1:]) for sp in sh.subpaths for seg in sp)
        fill = "none"
        if sh.fill:
            r_, g_, b_, a_ = sh.fill
            fill = f"#{r_:02X}{g_:02X}{b_:02X}" + (f'" fill-opacity="{a_:g}' if a_ < 1 else "")
        stroke = ""
        if sh.stroke:
            r_, g_, b_, a_ = sh.stroke
            stroke = f' stroke="#{r_:02X}{g_:02X}{b_:02X}" stroke-width="{sh.stroke_width:g}"'
        rule = ' fill-rule="evenodd"' if sh.evenodd else ""
        paths.append(f'<path d="{d}" fill="{fill}"{rule}{stroke}/>')
    w, h = x1 - x0, y1 - y0
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{x0:.2f} {y0:.2f} {w:.2f} {h:.2f}" width="{w:.0f}" '
            f'height="{h:.0f}">{"".join(paths)}</svg>')


def add_logo(slug: str, file: Path, name: str | None = None, page: int | None = None) -> dict:
    import shutil

    kit = _require(slug)
    file = Path(file).expanduser().resolve()
    if not file.is_file():
        raise SystemExit(f"not found: {file}")
    if file.suffix.lower() not in (".svg", ".png", ".jpg", ".jpeg", ".webp", ".pdf", ".ai", ".eps"):
        raise SystemExit(f"{file.name}: logos are svg (best) or png")
    name = name or re.sub(r"[^a-z0-9-]+", "-", file.stem.lower()).strip("-") or "logo"
    if file.suffix.lower() in (".pdf", ".ai"):  # .ai files from Illustrator carry a PDF inside
        try:
            svg = pdf_logo_svg(file, page or 1)
        except svgflat_unsupported() as e:
            svg, why = None, str(e)
        if svg:
            target = brand_dir(slug) / f"{name}.svg"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(svg, encoding="utf-8")
            kit.setdefault("logos", {})[name] = target.name
            save(slug, kit)
            return {"client": slug, "logo": name, "file": str(target), "use_as": f"brand:{name}",
                    "from": f"{file.name} page {page or 1}",
                    "note": "vector extracted; other pages/versions: --page N --name <name>; recolour with the layer's color"}
    target = brand_dir(slug) / f"{name}{file.suffix.lower()}"
    target.parent.mkdir(parents=True, exist_ok=True)
    if file != target:
        shutil.copy2(file, target)
    kit.setdefault("logos", {})[name] = target.name
    save(slug, kit)
    res = {"client": slug, "logo": name, "file": str(target), "use_as": f"brand:{name}"}
    if target.suffix in (".pdf", ".ai", ".eps"):
        res["note"] = "kept for reference; layers need an svg or png version"
    return res


# --- logo pack -------------------------------------------------------------------------------

def _recolor_svg(text: str, hex_: str) -> str:
    """Every fill/stroke/stop colour that isn't none -> hex_ (monochrome logo)."""
    import xml.etree.ElementTree as ET

    ET.register_namespace("", "http://www.w3.org/2000/svg")
    ET.register_namespace("xlink", "http://www.w3.org/1999/xlink")
    root = ET.fromstring(text)
    painted = False
    for el in root.iter():
        for k in ("fill", "stroke", "stop-color"):
            v = el.get(k)
            if v is not None and v != "none" and not v.startswith("url("):
                el.set(k, hex_)
                painted = True
        st = el.get("style")
        if st:
            el.set("style", re.sub(r"(fill|stroke|stop-color)\s*:\s*(?!none|url)[^;]+", lambda m: f"{m.group(1)}:{hex_}", st))
            painted = True
    if not painted or root.get("fill") is None:  # shapes without a fill paint black by default
        tag = root.tag.split("}")[-1]
        if tag == "svg":
            root.set("fill", hex_)
    return ET.tostring(root, encoding="unicode")


def svg_size(text: str) -> tuple[float, float]:
    m = re.search(r'viewBox\s*=\s*"([^"]+)"', text)
    if m:
        v = [float(x) for x in re.split(r"[,\s]+", m.group(1).strip())]
        return v[2], v[3]
    w = re.search(r'\swidth\s*=\s*"([\d.]+)', text)
    h = re.search(r'\sheight\s*=\s*"([\d.]+)', text)
    return (float(w.group(1)) if w else 100.0), (float(h.group(1)) if h else 100.0)


def _svg_png(text: str, width: int, resources: Path):
    """Rasterise an svg at `width` px (height from its aspect), transparent background."""
    import io

    from PIL import Image

    from .render import svg_to_png_bytes

    vw, vh = svg_size(text)
    h = max(1, round(width * vh / vw))
    t = re.sub(r"(<svg\b[^>]*?)\s(width|height)\s*=\s*\"[^\"]*\"", r"\1", text, count=2)
    t = re.sub(r"(<svg\b[^>]*?)\s(width|height)\s*=\s*\"[^\"]*\"", r"\1", t, count=2)
    if "viewBox" not in t:
        t = t.replace("<svg", f'<svg viewBox="0 0 {vw} {vh}"', 1)
    t = t.replace("<svg", f'<svg width="{width}" height="{h}"', 1)
    return Image.open(io.BytesIO(svg_to_png_bytes(t, resources))).convert("RGBA")


def _mono_png(im, rgb: tuple[int, int, int]):
    from PIL import Image, ImageOps

    im = im.convert("RGBA")
    a = im.getchannel("A")
    if a.getextrema()[0] == 255:  # no transparency: use darkness as the mask
        a = ImageOps.invert(im.convert("L"))
    out = Image.new("RGBA", im.size, rgb + (255,))
    out.putalpha(a)
    return out


def _on_background(logo, bg: tuple[int, int, int], size=(1600, 1000), frac=0.6):
    from PIL import Image

    canvas = Image.new("RGB", size, bg)
    lg = logo.copy()
    lg.thumbnail((int(size[0] * frac), int(size[1] * frac)), Image.LANCZOS)
    canvas.paste(lg, ((size[0] - lg.width) // 2, (size[1] - lg.height) // 2), lg)
    return canvas


def _square(logo, size: int, pad: float = 0.1, bg=None):
    from PIL import Image

    canvas = Image.new("RGBA", (size, size), (bg + (255,)) if bg else (0, 0, 0, 0))
    inner = max(1, round(size * (1 - 2 * pad)))
    lg = logo.copy()
    lg.thumbnail((inner, inner), Image.LANCZOS)
    canvas.paste(lg, ((size - lg.width) // 2, (size - lg.height) // 2), lg)
    return canvas


def logo_pack(slug: str, logo: str = "logo", out: Path | None = None, symbol: str | None = None) -> dict:
    """Every variation a client needs from one master logo (svg preferred, else a large png)."""
    from PIL import Image

    from . import colors as C

    kit = _require(slug)
    logos = kit.get("logos", {})
    if logo not in logos:
        raise SystemExit(f"brand {slug} has no logo {logo!r} (have: {', '.join(logos) or 'none'}; `da brand logo {slug} add <file>`)")
    bdir = brand_dir(slug)
    src = bdir / logos[logo]
    out = Path(out) if out else bdir / "pack" / logo
    out.mkdir(parents=True, exist_ok=True)
    files, notes = [], []

    def colour(name: str, default: str):
        try:
            return C.parse(f"${name}", kit.get("colors", {})) or C.parse(default)
        except C.ColorError:
            return C.parse(default)

    primary = colour("primary", "#111111")
    paper = colour("paper", "#FFFFFF")
    ink = colour("ink", "#111111")

    is_svg = src.suffix.lower() == ".svg"
    if is_svg:
        text = src.read_text(encoding="utf-8")
        if "<text" in text:
            notes.append("logo svg contains live <text>: outline it (Illustrator: Type > Create Outlines) so it renders everywhere")
        variants = {"": text, "-black": _recolor_svg(text, "#000000"), "-white": _recolor_svg(text, "#FFFFFF")}
        for suf, t in variants.items():
            p = out / f"{logo}{suf}.svg"
            p.write_text(t, encoding="utf-8")
            files.append(p)
        master = _svg_png(text, 2048, bdir)
        black = _svg_png(variants["-black"], 2048, bdir)
        white = _svg_png(variants["-white"], 2048, bdir)
    elif src.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
        master = Image.open(src).convert("RGBA")
        if max(master.size) < 2048:
            notes.append(f"png master is {master.width}x{master.height}: sizes above it are upscaled; an svg gives sharper results")
        black, white = _mono_png(master, (0, 0, 0)), _mono_png(master, (255, 255, 255))
        notes.append("no vector source: run `da image vectorize` (if available) or ask the client for the svg/ai")
    else:
        raise SystemExit(f"{src.name}: logo-pack needs an svg or png master")

    for size in (512, 1024, 2048):
        for suf, im in (("", master), ("-black", black), ("-white", white)):
            p = out / f"{logo}{suf}-{size}.png"
            k = size / max(im.size)  # longest side = size (svg masters are 2048 wide, so no real upscale)
            im.resize((max(1, round(im.width * k)), max(1, round(im.height * k))), Image.LANCZOS).save(p)
            files.append(p)
    # print-friendly PDF (raster at 2048 px; vector PDFs come from `da export --to pdf` of the brand guide)
    p = out / f"{logo}.pdf"
    flat = Image.new("RGB", master.size, (255, 255, 255))
    flat.paste(master, mask=master.getchannel("A"))
    flat.save(p, "PDF", resolution=300)
    files.append(p)
    # on brand backgrounds
    for name, lg, bg in (("on-paper", master, paper), ("on-primary", white, primary), ("on-ink", white, ink)):
        p = out / f"{logo}-{name}.png"
        _on_background(lg, (bg.r, bg.g, bg.b)).save(p)
        files.append(p)
    # favicons from the symbol when there is one
    sym_name = symbol or ("symbol" if "symbol" in logos else None)
    fav_src = master
    if sym_name and sym_name in logos and sym_name != logo:
        sp = bdir / logos[sym_name]
        fav_src = _svg_png(sp.read_text(encoding="utf-8"), 1024, bdir) if sp.suffix.lower() == ".svg" else Image.open(sp).convert("RGBA")
    fav = out / "favicon"
    fav.mkdir(exist_ok=True)
    big = _square(fav_src, 512, 0.08)
    big.save(fav / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])
    _square(fav_src, 180, 0.12, (paper.r, paper.g, paper.b)).convert("RGB").save(fav / "apple-touch-icon.png")
    for s in (192, 512):
        _square(fav_src, s, 0.08).save(fav / f"icon-{s}.png")
    _square(fav_src, 32, 0.04).save(fav / "favicon-32.png")
    manifest = {"name": kit.get("name", slug), "icons": [
        {"src": "/icon-192.png", "sizes": "192x192", "type": "image/png"},
        {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png"}],
        "theme_color": primary.hex, "background_color": paper.hex, "display": "standalone"}
    (fav / "site.webmanifest").write_text(__import__("json").dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (fav / "head.html").write_text(
        '<link rel="icon" href="/favicon.ico" sizes="any">\n<link rel="icon" type="image/png" sizes="32x32" href="/favicon-32.png">\n'
        '<link rel="apple-touch-icon" href="/apple-touch-icon.png">\n<link rel="manifest" href="/site.webmanifest">\n'
        f'<meta name="theme-color" content="{primary.hex}">\n', encoding="utf-8")
    files += sorted(fav.iterdir())
    return {"client": slug, "logo": logo, "out": str(out), "files": [p.relative_to(out).as_posix() for p in files],
            "notes": notes}


# --- brand guide -----------------------------------------------------------------------------

LABELS = {
    "pt": {"guide": "Manual de marca", "logo": "Logotipo", "clear": "Área de proteção: x = altura do símbolo / 4",
           "min": "Tamanho mínimo: 24 px digital · 15 mm impresso", "colors": "Cores", "type": "Tipografia",
           "rules": "Uso da marca", "do": "Faça", "dont": "Evite", "pangram": "Zebras caolhas do pântano querem fugir já"},
    "en": {"guide": "Brand guidelines", "logo": "Logo", "clear": "Clear space: x = symbol height / 4",
           "min": "Minimum size: 24 px digital · 15 mm print", "colors": "Colours", "type": "Typography",
           "rules": "Brand usage", "do": "Do", "dont": "Don't", "pangram": "The quick brown fox jumps over the lazy dog"},
}


def _logo_aspect(path: Path) -> float:
    if path.suffix.lower() == ".svg":
        w, h = svg_size(path.read_text(encoding="utf-8"))
        return w / h if h else 1.0
    from PIL import Image

    with Image.open(path) as im:
        return im.width / im.height


def guide_design(slug: str, lang: str = "pt") -> dict:
    """A design.json (brand-board artboards) that renders the brand guide."""
    from . import colors as C
    from . import design as D

    kit = _require(slug)
    L = LABELS["en" if lang.lower().startswith("en") else "pt"]
    name = kit.get("name", slug)
    cols = kit.get("colors", {})
    logos = kit.get("logos", {})
    bdir = brand_dir(slug)
    d = D.empty(f"{slug}-brand-guide", slug)
    W, H = 1920, 1080

    def logo_layer(lid: str, which: str, cx: float, cy: float, max_w: float, max_h: float, color=None):
        f = bdir / logos[which]
        ar = _logo_aspect(f)
        w, h = (max_w, max_w / ar) if max_w / ar <= max_h else (max_h * ar, max_h)
        lay = {"id": lid, "type": "svg" if f.suffix.lower() == ".svg" else "image", "src": f"brand:{which}",
               "x": round(cx - w / 2, 1), "y": round(cy - h / 2, 1), "w": round(w, 1), "h": round(h, 1), "role": "logo"}
        if lay["type"] == "image":
            lay["fit"] = "contain"
        elif color:
            lay["color"] = color
        return lay

    has = lambda k: k in cols  # noqa: E731
    bg_cover = "$primary" if has("primary") else "$ink"
    main = "logo" if "logo" in logos else (next(iter(logos)) if logos else None)
    white = "logo-white" if "logo-white" in logos else None

    def title(t: str) -> dict:
        return {"id": "title", "type": "text", "text": t, "x": 120, "y": 90, "w": 1200, "font": "$display",
                "size": 64, "color": "$ink", "role": "headline"}

    # 1 cover
    cover = D.new_artboard("brand-board", "cover", background=bg_cover)
    if main:
        cover["layers"].append(logo_layer("logo", white or main, W / 2, H / 2 - 60, 760, 340,
                                          None if white else "$paper"))
    else:
        cover["layers"].append({"id": "logo", "type": "text", "text": name, "x": 160, "y": 380, "w": 1600,
                                "align": "center", "font": "$display", "size": 140, "color": "$paper"})
    cover["layers"].append({"id": "sub", "type": "text", "text": f"{name} · {L['guide']}", "x": 160, "y": 900,
                            "w": 1600, "align": "center", "font": "$body", "size": 32, "tracking": 80,
                            "case": "upper", "color": "$paper"})
    d["artboards"].append(cover)

    # 2 logo + clear space + minimum size
    if main:
        ab = D.new_artboard("brand-board", "logo")
        ab["layers"].append(title(L["logo"]))
        lg = logo_layer("logo", main, W / 2, H / 2 + 20, 900, 420)
        x = lg["h"] / 4
        ab["layers"].append({"id": "clear", "type": "rect", "x": round(lg["x"] - x, 1), "y": round(lg["y"] - x, 1),
                             "w": round(lg["w"] + 2 * x, 1), "h": round(lg["h"] + 2 * x, 1), "fill": "none",
                             "stroke": {"color": "$muted", "width": 2, "dash": [12, 8]}})
        ab["layers"].append(lg)
        ab["layers"].append({"id": "clear-note", "type": "text", "text": L["clear"], "x": 120, "y": 930, "w": 900,
                             "size": 26, "color": "$muted"})
        ab["layers"].append({"id": "min-note", "type": "text", "text": L["min"], "x": 1000, "y": 930, "w": 800,
                             "size": 26, "color": "$muted", "align": "right"})
        d["artboards"].append(ab)

    # 3 colours
    if cols:
        ab = D.new_artboard("brand-board", "colors")
        ab["layers"].append(title(L["colors"]))
        names = list(cols)[:8]
        n = len(names)
        gap, x0, top = 24, 120, 220
        sw = (W - 2 * x0 - gap * (n - 1)) / n
        for i, k in enumerate(names):
            c = C.parse(f"${k}", cols)
            if c is None:
                continue
            fg = "#FFFFFF" if C.contrast(C.parse("#FFFFFF"), c) >= C.contrast(C.parse("#111111"), c) else "#111111"
            cm = C.to_cmyk(c)
            v = cols[k]
            lines = [k, c.hex, f"RGB {c.r} {c.g} {c.b}", "CMYK " + " ".join(str(round(x)) for x in cm)]
            if isinstance(v, dict) and v.get("pantone"):
                lines.append(f"Pantone {v['pantone']}")
            x = round(x0 + i * (sw + gap), 1)
            ab["layers"].append({"id": f"sw-{k}", "type": "rect", "x": x, "y": top, "w": round(sw, 1), "h": 760,
                                 "radius": 16, "fill": c.hex, "stroke": {"color": "#00000022", "width": 1}})
            ab["layers"].append({"id": f"sw-{k}-tx", "type": "text", "text": "\n".join(lines), "x": x + 24,
                                 "y": top + 760 - 24 - 40 * len(lines), "w": round(sw - 48, 1), "size": 28,
                                 "line_height": 1.4, "color": fg, "autofit": True, "h": 40 * len(lines) + 4})
        d["artboards"].append(ab)

    # 4 typography
    fonts = {**D.DEFAULT_FONTS, **(kit.get("fonts") or {})}  # display + body at least, as the design sees them
    ab = D.new_artboard("brand-board", "type")
    ab["layers"].append(title(L["type"]))
    items = list(fonts.items())[:3]
    colw = (W - 240) / max(1, len(items))
    for i, (k, spec) in enumerate(items):
        spec = spec if isinstance(spec, dict) else {"family": spec}
        x = round(120 + i * colw, 1)
        fam, wt = spec.get("family", "Montserrat"), spec.get("weight", 400)
        ab["layers"] += [
            {"id": f"ty-{k}-aa", "type": "text", "text": "Aa", "x": x, "y": 220, "font": f"${k}", "size": 220,
             "line_height": 1.0, "color": "$ink"},
            {"id": f"ty-{k}-name", "type": "text", "text": f"{fam} {wt} — ${k}", "x": x, "y": 480, "w": round(colw - 60, 1),
             "size": 28, "font": "$body", "weight": 700, "color": "$ink"},
            {"id": f"ty-{k}-abc", "type": "text", "text": "ABCDEFGHIJKLMNOPQRSTUVWXYZ\nabcdefghijklmnopqrstuvwxyz\n0123456789 !?&@%",
             "x": x, "y": 540, "w": round(colw - 60, 1), "size": 30, "line_height": 1.4, "font": f"${k}", "color": "$ink"},
            {"id": f"ty-{k}-pan", "type": "text", "text": L["pangram"], "x": x, "y": 760, "w": round(colw - 60, 1),
             "h": 200, "autofit": True, "size": 48, "line_height": 1.15, "font": f"${k}", "color": "$muted"}]
    d["artboards"].append(ab)

    # 5 rules
    rules = kit.get("rules") or []
    if rules:
        ab = D.new_artboard("brand-board", "rules")
        ab["layers"].append(title(L["rules"]))
        dont = [r for r in rules if re.match(r"\s*(never|nunca|não|nao|don'?t|evite|avoid)\b", r, re.I)]
        do = [r for r in rules if r not in dont]
        for j, (head, items_, col) in enumerate(((L["do"], do, "$ink"), (L["dont"], dont, "$muted"))):
            x = 120 + j * 860
            ab["layers"].append({"id": f"r{j}-h", "type": "text", "text": head, "x": x, "y": 220, "size": 40,
                                 "font": "$display", "color": col})
            ab["layers"].append({"id": f"r{j}-t", "type": "text", "text": "\n".join(f"• {r}" for r in items_) or "—",
                                 "x": x, "y": 300, "w": 780, "h": 680, "autofit": True, "size": 32,
                                 "line_height": 1.45, "color": "$ink"})
        d["artboards"].append(ab)
    return d


def guide(slug: str, project: str | None = None, lang: str = "pt") -> dict:
    from . import design as D

    d = guide_design(slug, lang)
    name = project or f"{slug}-brand-guide"
    from . import project as P

    pr = Project(name) if (P.PROJECTS / name).exists() else Project.create(name, client=(load(slug) or {}).get("name"),
                                                                            purpose="identity")
    if D.path(pr).exists():
        from .project import write_json

        write_json(pr.path("work", "versions", "before-brand-guide.json"), D.load(pr))
    D.save(pr, d)
    check = D.validate(d, D.context(pr, d))
    return {"project": pr.name, "design": str(D.path(pr)), "artboards": [a["id"] for a in d["artboards"]],
            "errors": check["errors"], "next": f"uv run da render {pr.name}  (then `da export {pr.name} --to pdf`)"}


# --- CLI -------------------------------------------------------------------------------------

def cmd_brand(a):
    slug = client_slug(a.client)
    if a.action == "show":
        return describe(slug)
    if a.action == "set":
        return set_values(slug, a.color, a.cmyk, a.pantone, a.font, a.rule, a.name)
    if a.action == "logo":
        if a.op == "add":
            if not a.file:
                raise SystemExit("usage: da brand logo <client> add <file> [--name logo-white] [--page N for a PDF]")
            return add_logo(slug, Path(a.file), a.name, a.page)
        if a.op == "list":
            return describe(slug)["brand"].get("logos", {})
        if a.op == "remove":
            kit = _require(slug)
            kit.get("logos", {}).pop(a.name or "", None)
            save(slug, kit)
            return kit.get("logos", {})
        raise SystemExit("logo ops: add | list | remove")
    if a.action == "logo-pack":
        return logo_pack(slug, a.logo, Path(a.out) if a.out else None, a.symbol)
    if a.action == "guide":
        return guide(slug, a.project, a.lang)
    raise SystemExit(a.action)


def register(sub) -> None:
    p = sub.add_parser("brand", help="client brand kits: show | set | logo | logo-pack | guide")
    p.add_argument("action", choices=["show", "set", "logo", "logo-pack", "guide"])
    p.add_argument("client", help="client name or slug")
    p.add_argument("op", nargs="?", help="logo: add | list | remove")
    p.add_argument("file", nargs="?", help="logo add: the file")
    p.add_argument("--color", action="append", help="name=#hex (repeatable)")
    p.add_argument("--cmyk", action="append", help="name=c,m,y,k authored for print")
    p.add_argument("--pantone", action="append", help='name="485 C"')
    p.add_argument("--font", action="append", help='name="Family:weight[:italic]"')
    p.add_argument("--rule", action="append", help="brand rule, e.g. \"never red text on black\"")
    p.add_argument("--name", help="set: display name; logo: logo name")
    p.add_argument("--logo", default="logo", help="logo-pack: which logo")
    p.add_argument("--page", type=int, help="logo add from a PDF/AI: which page (default 1)")
    p.add_argument("--symbol", help="logo-pack: logo to use for favicons (default `symbol` when present)")
    p.add_argument("--out", help="logo-pack: output folder (default brand/pack/<logo>)")
    p.add_argument("--project", help="guide: project to write (default <client>-brand-guide)")
    p.add_argument("--lang", default="pt", help="guide: pt | en")
    p.set_defaults(func=cmd_brand)
