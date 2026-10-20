"""design.json: the single source of truth for a project's pieces. Small enough to read and
edit by hand; every render and export is derived from it.

{
  "version": 1,
  "name": "promo-outubro",
  "brand": "vulcano",                    # optional client brand kit (<memory>/clients/<slug>/brand/brand.json):
                                         #   its colours/fonts become tokens, its logos `brand:<name>` sources
  "tokens": {                            # project tokens, override the brand kit
    "colors": {"primary": "#E30613", "ink": "#111111", "paper": {"hex": "#FFFFFF", "cmyk": [0, 0, 0, 0]}},
    "fonts":  {"display": {"family": "Montserrat", "weight": 800}, "body": {"family": "Montserrat", "weight": 400}}
  },
  "artboards": [
    {
      "id": "post-1",                    # unique, used in file names (output/post-1.png)
      "preset": "ig-post",               # optional, see presets.py (`da presets`)
      "width": 1080, "height": 1350,     # trim size in `unit`
      "unit": "px",                      # px | mm | in | pt
      "dpi": 72,                         # pixels per inch on export (print: 300)
      "bleed": 0,                        # print bleed in `unit` (presets set 3 mm)
      "safe": [60, 60, 60, 60],          # optional safe zone [top, right, bottom, left]; qa keeps text/logos inside
      "background": "$paper",            # any fill (colour or gradient); extends into the bleed
      "layers": [ ...bottom to top... ]
    }
  ]
}

Lengths are numbers in the artboard unit, or strings with a unit: "12pt", "3mm", "40px", "0.5in".
Layers (all take: id, type, name, x, y, w, h, rotation (deg, about the centre), opacity 0-1,
blend (multiply|screen|overlay|darken|lighten|soft-light|...), hidden, shadow {x, y, blur, color},
role (background|photo|headline|body|cta|logo|decoration), anchor (for `da resize`:
fill|center|top|bottom|left|right|top-left|top-right|bottom-left|bottom-right)):

  rect     fill, stroke {color, width, dash: [on, off]}, radius (number or [tl, tr, br, bl])
  ellipse  fill, stroke                         (x, y, w, h = bounding box)
  line     x, y, x2, y2, stroke
  path     d (SVG path data in its own box `viewbox` [minx, miny, w, h], scaled to x, y, w, h), fill, stroke
  image    src, fit (cover|contain|fill), focus (center|face|top|bottom|left|right|[fx, fy] 0-1),
           radius, mask ("circle"), filters {grayscale, blur, brightness, contrast, saturation (1 = same),
           duotone: [dark, light], tint: colour}
  svg      src (.svg file), color (recolour every fill: monochrome logos), fit contain
  icon     name (Lucide icon, `da icon search`), color, stroke_width
  text     text (`**word**` = accent span, "\n" = line break), font ("$display" or a family name),
           weight, italic, size, line_height (x size, default 1.2), tracking (1/1000 em), color,
           align (left|center|right|justify; justify_all also spreads the last line), valign (top|middle|bottom), case (upper|lower|title),
           w (wrap width; omit = one line), h (box height; omit = grows), max_lines, optical (left-aligned
           lines start at the first letter's ink instead of its side bearing: big numbers/headlines),
           autofit (shrink to fit w x h down to min_size), accent {color, weight, font, italic, highlight},
           highlight {color, pad: [x, y], radius} (box behind each line; pad numbers are FRACTIONS of the
           font size, e.g. [0.15, 0.05]; strings are lengths: ["12px", "4px"]), stroke {color, width}
  group    layers (coordinates relative to the group's x, y), clip (bool, clips to w x h)
  noise    film grain over x, y, w, h: size (grain, default 1.2), seed, opacity (strength); mode "speckle"
           (default: sparse dark/light specks, tone unchanged) or "overlay" (contrast 6, blend overlay: vivid on colour)

Effects on any layer: blur (Gaussian, in units), texture {spread: 2.8, size: 4, rough: 1.0, seed, color}
(ink bleed / photocopied edges on bold type and stamps: solid core, rough edge), shadow. Exports that can't express them place that layer as a
bitmap (PDF, Affinity, Adobe). cast {angle: 25, length: 1.4, width: 0.6, blur, color, opacity}: long ground shadow
from the artwork's bottom edge (cast.py; `{}` = defaults), vector in the preview and Affinity, bitmap in PDF.

Fills: colour (see colors.py) or {"type": "linear", "angle": 180, "stops": [[0, "$primary"], [1, "#0000"]]}
or {"type": "radial", "cx": 0.5, "cy": 0.5, "r": 0.7, "stops": [...]}. Angle 0 = left to right, 90 = top to bottom.
Sources: project-relative path ("input/foto.jpg"), "brand:<logo name>", "figure:<pose>" (a person silhouette,
figures.py, `da figure list`), or an absolute path.
"""
from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import colors as C
from .project import Project, read_json, write_json

UNITS_PER_INCH = {"px": None, "in": 1.0, "mm": 25.4, "pt": 72.0, "cm": 2.54}
LAYER_TYPES = {"rect", "ellipse", "line", "path", "image", "svg", "icon", "text", "group", "noise"}
DEFAULT_COLORS = {"ink": "#111111", "paper": "#FFFFFF", "primary": "#2B59FF", "accent": "#FF5A1F", "muted": "#6B7280"}
DEFAULT_FONTS = {"display": {"family": "Montserrat", "weight": 800}, "body": {"family": "Montserrat", "weight": 400}}
BLENDS = {"normal", "multiply", "screen", "overlay", "darken", "lighten", "color-dodge", "color-burn",
          "hard-light", "soft-light", "difference", "exclusion", "hue", "saturation", "color", "luminosity"}


# --- units ---------------------------------------------------------------------------------

def px_per_unit(ab: dict) -> float:
    """Output pixels per artboard unit at scale 1."""
    unit = ab.get("unit", "px")
    if unit == "px":
        return 1.0
    return float(ab.get("dpi", 300)) / UNITS_PER_INCH[unit]


def length(v, unit: str, dpi: float = 72) -> float:
    """A length from design.json in the artboard's unit."""
    if v is None:
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    m = re.fullmatch(r"\s*(-?[\d.]+)\s*(px|mm|cm|in|pt)?\s*", str(v))
    if not m:
        raise ValueError(f"bad length {v!r}")
    num, u = float(m.group(1)), m.group(2) or unit
    if u == unit:
        return num
    inches = num / dpi if u == "px" else num / UNITS_PER_INCH[u]
    return inches * dpi if unit == "px" else inches * UNITS_PER_INCH[unit]


# --- load / save -----------------------------------------------------------------------------

def path(project: Project) -> Path:
    return project.path("design.json")


def load(project: Project) -> dict:
    d = read_json(path(project))
    if d is None:
        raise SystemExit(f"{project.name} has no design.json yet (create one with `da new` or `da artboard add`)")
    return d


def save(project: Project, d: dict) -> None:
    write_json(path(project), d)


def empty(name: str, brand: str | None = None) -> dict:
    return {"version": 1, "name": name, "brand": brand, "tokens": {"colors": {}, "fonts": {}}, "artboards": []}


def new_artboard(preset_name: str | None, ab_id: str, width=None, height=None, unit=None, background="$paper") -> dict:
    from . import presets

    ab: dict = {"id": ab_id}
    if preset_name:
        p = presets.get(preset_name)
        ab.update(preset=preset_name, width=p["width"], height=p["height"], unit=p["unit"], dpi=p["dpi"],
                  bleed=p.get("bleed", 0))
        if p.get("safe"):
            ab["safe"] = p["safe"]
        if p.get("margin"):
            ab["margin"] = p["margin"]
    if width:
        ab["width"] = width
    if height:
        ab["height"] = height
    if unit:
        ab["unit"] = unit
    ab.setdefault("unit", "px")
    ab.setdefault("dpi", 300 if ab["unit"] != "px" else 72)
    ab.setdefault("bleed", 0)
    if "width" not in ab or "height" not in ab:
        raise SystemExit("artboard needs a preset or --width and --height")
    ab["background"] = background
    ab["layers"] = []
    return ab


def artboard(d: dict, ab_id: str | None) -> dict:
    abs_ = d.get("artboards", [])
    if not abs_:
        raise SystemExit("design.json has no artboards")
    if ab_id is None:
        return abs_[0]
    for ab in abs_:
        if ab["id"] == ab_id:
            return ab
    raise SystemExit(f"no artboard {ab_id!r} (have: {', '.join(a['id'] for a in abs_)})")


def find_layer(layers: list, layer_id: str) -> dict | None:
    for l in layers:
        if l.get("id") == layer_id:
            return l
        if l.get("type") == "group":
            hit = find_layer(l.get("layers", []), layer_id)
            if hit:
                return hit
    return None


def walk(layers: list, ox: float = 0.0, oy: float = 0.0, include_hidden: bool = False):
    """Yield (layer, absolute x offset, absolute y offset) for every layer, groups expanded
    after the group itself. Offsets are the parent group's origin."""
    for l in layers:
        if l.get("hidden") and not include_hidden:
            continue
        yield l, ox, oy
        if l.get("type") == "group":
            yield from walk(l.get("layers", []), ox + float(l.get("x", 0)), oy + float(l.get("y", 0)), include_hidden)


# --- context: tokens, brand, sources ---------------------------------------------------------

@dataclass
class Context:
    project: Project
    design: dict
    colors: dict = field(default_factory=dict)
    fonts: dict = field(default_factory=dict)
    brand_dir: Path | None = None
    logos: dict = field(default_factory=dict)
    warnings: list = field(default_factory=list)

    def color(self, v) -> C.Color | None:
        return C.parse(v, self.colors)

    def font_spec(self, layer: dict) -> dict:
        """{family, weight, italic} for a text layer (or accent span), tokens resolved."""
        f = layer.get("font", "$body")
        spec: dict = {}
        if isinstance(f, str) and f.startswith("$"):
            tok = self.fonts.get(f[1:])
            if tok is None:
                raise SystemExit(f"unknown font token {f} (define it in tokens.fonts or the brand kit)")
            spec = dict(tok) if isinstance(tok, dict) else {"family": tok}
        elif isinstance(f, dict):
            spec = dict(f)
        else:
            spec = {"family": f}
        if "weight" in layer:
            spec["weight"] = layer["weight"]
        if "italic" in layer:
            spec["italic"] = layer["italic"]
        spec.setdefault("weight", 400)
        spec.setdefault("italic", False)
        return spec

    def font_dirs(self) -> list[Path]:
        dirs = []
        if self.brand_dir and (self.brand_dir / "fonts").is_dir():
            dirs.append(self.brand_dir / "fonts")
        if self.project.path("input").is_dir():
            dirs.append(self.project.path("input"))
        return dirs

    def src(self, s: str) -> Path:
        if s.startswith("figure:"):
            from .figures import figure_file

            return figure_file(s[7:])
        if s.startswith("brand:"):
            name = s[6:]
            if not self.brand_dir:
                raise SystemExit(f"{s}: this design has no brand kit (set \"brand\" in design.json)")
            f = self.logos.get(name)
            if not f:
                raise SystemExit(f"{s}: brand kit has no logo {name!r} (have: {', '.join(self.logos) or 'none'})")
            return (self.brand_dir / f).resolve()
        p = Path(s)
        return p if p.is_absolute() else self.project.abs(s)


def context(project: Project, d: dict | None = None) -> Context:
    d = d if d is not None else load(project)
    ctx = Context(project, d)
    colors = dict(DEFAULT_COLORS)
    fonts = copy.deepcopy(DEFAULT_FONTS)
    if d.get("brand"):
        from . import brand

        kit = brand.load(d["brand"])
        if kit is None:
            ctx.warnings.append(f"brand kit {d['brand']!r} not found (`da brand new`); using defaults")
        else:
            ctx.brand_dir = brand.brand_dir(d["brand"])
            colors.update(kit.get("colors", {}))
            fonts.update(kit.get("fonts", {}))
            ctx.logos = kit.get("logos", {})
    colors.update(d.get("tokens", {}).get("colors", {}))
    fonts.update(d.get("tokens", {}).get("fonts", {}))
    ctx.colors, ctx.fonts = colors, fonts
    return ctx


# --- validation ------------------------------------------------------------------------------

def validate(d: dict, ctx: Context | None = None) -> dict:
    """Structural check. Returns {"errors": [...], "warnings": [...]}; errors block rendering."""
    errors, warnings = [], []
    if d.get("version") != 1:
        errors.append("version must be 1")
    seen_ab = set()
    for ab in d.get("artboards", []):
        aid = ab.get("id")
        if not aid or aid in seen_ab:
            errors.append(f"artboard id missing or duplicated: {aid!r}")
        seen_ab.add(aid)
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", str(aid)):
            errors.append(f"artboard id {aid!r}: use letters, digits, - _ . (it names files)")
        for k in ("width", "height"):
            if not isinstance(ab.get(k), (int, float)) or ab[k] <= 0:
                errors.append(f"{aid}: {k} must be a positive number")
        if ab.get("unit", "px") not in UNITS_PER_INCH:
            errors.append(f"{aid}: unit must be one of {', '.join(UNITS_PER_INCH)}")
        ids = set()
        for l, _, _ in walk(ab.get("layers", []), include_hidden=True):
            lid, t = l.get("id"), l.get("type")
            where = f"{aid}/{lid}"
            if not lid:
                errors.append(f"{aid}: a {t} layer has no id")
            elif lid in ids:
                errors.append(f"{where}: duplicated layer id")
            ids.add(lid)
            if t not in LAYER_TYPES:
                errors.append(f"{where}: unknown type {t!r}")
                continue
            if t == "text" and not isinstance(l.get("text"), str):
                errors.append(f"{where}: text layer needs \"text\"")
            if t in ("image", "svg") and not l.get("src"):
                errors.append(f"{where}: {t} layer needs \"src\"")
            if t == "icon" and not l.get("name"):
                errors.append(f"{where}: icon layer needs \"name\"")
            if t == "path" and not l.get("d"):
                errors.append(f"{where}: path layer needs \"d\"")
            if t in ("rect", "ellipse", "image", "svg", "icon", "path", "noise") and (not l.get("w") or not l.get("h")):
                errors.append(f"{where}: {t} needs w and h")
            if t == "text":
                for hl in (l.get("highlight"), (l.get("accent") or {}).get("highlight")):
                    pad = hl.get("pad") if isinstance(hl, dict) else None
                    if isinstance(pad, list) and any(isinstance(v, (int, float)) and v > 1.5 for v in pad):
                        warnings.append(f"{where}: highlight pad {pad} is in fractions of the font size "
                                        f"({pad[0]} = {pad[0]}x the size); use e.g. [0.15, 0.05] or \"12px\"")
            if l.get("blend") and l["blend"] not in BLENDS:
                errors.append(f"{where}: blend {l['blend']!r} unknown")
            if ctx:
                for key in ("fill", "color"):
                    v = l.get(key)
                    if isinstance(v, (str, dict)) and not (isinstance(v, dict) and "stops" in v):
                        try:
                            ctx.color(v)
                        except C.ColorError as e:
                            errors.append(f"{where}: {e}")
                if t in ("image", "svg") and l.get("src"):
                    try:
                        p = ctx.src(l["src"])
                        if not p.exists():
                            errors.append(f"{where}: source not found: {l['src']}")
                    except SystemExit as e:
                        errors.append(f"{where}: {e}")
    if not d.get("artboards"):
        warnings.append("no artboards yet")
    return {"errors": errors, "warnings": warnings}
