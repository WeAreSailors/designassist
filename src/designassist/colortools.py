"""`da color`: colour tools for the designer — contrast, palettes from images, OKLCH scales,
harmonies, CMYK, and a contrast check of every text layer against what's actually behind it.

OKLab/OKLCH (Björn Ottosson) is used for palettes and scales: perceptually even steps, so a
50-950 scale reads evenly and k-means groups colours the way the eye does.
"""
from __future__ import annotations

import math

from . import colors as C

# --- OKLab ---------------------------------------------------------------------------------


def _srgb_to_lin(v):
    import numpy as np

    v = np.asarray(v, dtype=float) / 255.0
    return np.where(v <= 0.04045, v / 12.92, ((v + 0.055) / 1.055) ** 2.4)


def _lin_to_srgb(v):
    import numpy as np

    v = np.asarray(v, dtype=float)
    out = np.where(v <= 0.0031308, 12.92 * v, 1.055 * np.clip(v, 0, None) ** (1 / 2.4) - 0.055)
    return np.clip(out * 255.0, 0, 255)


_M1 = [[0.4122214708, 0.5363325363, 0.0514459929],
       [0.2119034982, 0.6806995451, 0.1073969566],
       [0.0883024619, 0.2817188376, 0.6299787005]]
_M2 = [[0.2104542553, 0.7936177850, -0.0040720468],
       [1.9779984951, -2.4285922050, 0.4505937099],
       [0.0259040371, 0.7827717662, -0.8086757660]]


def rgb_to_oklab(rgb):
    """(..., 3) sRGB 0-255 -> (..., 3) OKLab."""
    import numpy as np

    lin = _srgb_to_lin(rgb)
    lms = lin @ np.array(_M1).T
    return np.cbrt(lms) @ np.array(_M2).T


def oklab_to_rgb(lab):
    """(..., 3) OKLab -> (..., 3) sRGB 0-255 (clipped)."""
    import numpy as np

    lms_ = np.asarray(lab, dtype=float) @ np.linalg.inv(np.array(_M2)).T
    lin = (lms_ ** 3) @ np.linalg.inv(np.array(_M1)).T
    return _lin_to_srgb(lin)


def _in_gamut(lab) -> bool:
    import numpy as np

    lms_ = np.asarray(lab, dtype=float) @ np.linalg.inv(np.array(_M2)).T
    lin = (lms_ ** 3) @ np.linalg.inv(np.array(_M1)).T
    return bool(np.all(lin >= -1e-4) and np.all(lin <= 1 + 1e-4))


def to_oklch(c: C.Color) -> tuple[float, float, float]:
    L, a, b = rgb_to_oklab([c.r, c.g, c.b])
    return float(L), float(math.hypot(a, b)), float(math.degrees(math.atan2(b, a)) % 360)


def from_oklch(L: float, Ch: float, h: float) -> C.Color:
    """OKLCH -> Color; chroma reduced until the colour fits in sRGB (keeps hue and lightness)."""
    hr = math.radians(h)
    lo, hi = 0.0, Ch
    lab = [L, Ch * math.cos(hr), Ch * math.sin(hr)]
    if not _in_gamut(lab):
        for _ in range(24):
            mid = (lo + hi) / 2
            if _in_gamut([L, mid * math.cos(hr), mid * math.sin(hr)]):
                lo = mid
            else:
                hi = mid
        lab = [L, lo * math.cos(hr), lo * math.sin(hr)]
    r, g, b = oklab_to_rgb(lab)
    return C.Color(int(round(float(r))), int(round(float(g))), int(round(float(b))))


# --- contrast ------------------------------------------------------------------------------


def contrast_report(fg: str, bg: str, tokens: dict | None = None) -> dict:
    f, b = C.parse(fg, tokens), C.parse(bg, tokens)
    if f is None or b is None:
        raise SystemExit("contrast needs two solid colours")
    ratio = C.contrast(f, b)
    return {"fg": f.hex, "bg": b.hex, "ratio": ratio, "normal_text": C.wcag(ratio, False),
            "large_text": C.wcag(ratio, True), "ui_graphics": "AA" if ratio >= 3 else "fail"}


# --- palette from an image -------------------------------------------------------------------


def palette(image_path, n: int = 6, seed: int = 0) -> list[dict]:
    """Dominant colours by k-means (k-means++ init) in OKLab, sorted by share, with a suggested role."""
    import numpy as np
    from PIL import Image

    im = Image.open(image_path)
    im = im.convert("RGBA")
    im.thumbnail((200, 200))
    arr = np.asarray(im).reshape(-1, 4)
    arr = arr[arr[:, 3] > 128][:, :3].astype(float)
    if len(arr) == 0:
        raise SystemExit("image has no opaque pixels")
    lab = rgb_to_oklab(arr)
    rng = np.random.default_rng(seed)
    k = min(n, len(np.unique(arr, axis=0)))
    centers = [lab[rng.integers(len(lab))]]
    for _ in range(1, k):
        d = np.min(((lab[:, None, :] - np.array(centers)[None]) ** 2).sum(-1), axis=1)
        p = d / d.sum() if d.sum() > 0 else None
        centers.append(lab[rng.choice(len(lab), p=p)])
    centers = np.array(centers)
    for _ in range(30):
        lbl = np.argmin(((lab[:, None, :] - centers[None]) ** 2).sum(-1), axis=1)
        new = np.array([lab[lbl == i].mean(0) if np.any(lbl == i) else centers[i] for i in range(k)])
        if np.allclose(new, centers, atol=1e-5):
            break
        centers = new
    lbl = np.argmin(((lab[:, None, :] - centers[None]) ** 2).sum(-1), axis=1)
    out = []
    for i in range(k):
        share = float(np.mean(lbl == i))
        if share == 0:
            continue
        r, g, b = oklab_to_rgb(centers[i])
        col = C.Color(int(round(float(r))), int(round(float(g))), int(round(float(b))))
        L, Ch, h = to_oklch(col)
        out.append({"hex": col.hex, "share": round(share, 3), "L": round(L, 3), "chroma": round(Ch, 3),
                    "hue": round(h, 1)})
    out.sort(key=lambda e: -e["share"])
    _roles(out)
    return out


def _roles(pal: list[dict]) -> None:
    """ink = darkest low-chroma-ish, paper = lightest, primary = most chromatic with real share,
    accent = most chromatic remaining with a different hue."""
    if not pal:
        return
    ink = min(pal, key=lambda e: e["L"])
    paper = max(pal, key=lambda e: e["L"])
    ink["role"] = "ink"
    if paper is not ink:
        paper["role"] = "paper"
    rest = [e for e in pal if "role" not in e]
    rest.sort(key=lambda e: -(e["chroma"] * (0.3 + e["share"])))
    if rest:
        rest[0]["role"] = "primary"
        for e in rest[1:]:
            dh = abs((e["hue"] - rest[0]["hue"] + 180) % 360 - 180)
            if dh > 30 and e["chroma"] > 0.04:
                e["role"] = "accent"
                break
    for e in pal:
        e.setdefault("role", "support")


# --- scales and harmonies ---------------------------------------------------------------------

STEPS = [50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 950]
_L_TARGET = {50: 0.975, 100: 0.945, 200: 0.89, 300: 0.81, 400: 0.71, 500: 0.62, 600: 0.53, 700: 0.45,
             800: 0.37, 900: 0.30, 950: 0.22}
_C_FACTOR = {50: 0.12, 100: 0.25, 200: 0.45, 300: 0.7, 400: 0.9, 500: 1.0, 600: 0.95, 700: 0.85, 800: 0.72,
             900: 0.6, 950: 0.5}


def scale(base: str | C.Color, tokens: dict | None = None) -> dict:
    """Tailwind-like 50-950 scale in OKLCH. The base colour itself sits at 500 (lightness steps are
    shifted so 500 = base L; chroma eases off toward the ends)."""
    c = C.parse(base, tokens) if not isinstance(base, C.Color) else base
    L0, Ch0, h = to_oklch(c)
    shift = L0 - _L_TARGET[500]
    out = {}
    for s in STEPS:
        if s == 500:
            out[str(s)] = c.hex
            continue
        t = _L_TARGET[s]
        # blend the shift out toward the extremes so 50 stays near white and 950 near black
        w = 1 - abs(s - 500) / 500 if s < 500 else 1 - (s - 500) / 450
        L = min(0.985, max(0.12, t + shift * max(0.0, w)))
        out[str(s)] = from_oklch(L, Ch0 * _C_FACTOR[s], h).hex
    return out


HARMONIES = {"complementary": [0, 180], "analogous": [-30, 0, 30], "triadic": [0, 120, 240],
             "split": [0, 150, 210], "tetradic": [0, 90, 180, 270]}


def harmony(base: str, kind: str = "complementary", tokens: dict | None = None) -> list[str]:
    c = C.parse(base, tokens)
    L, Ch, h = to_oklch(c)
    if kind == "monochrome":
        return [from_oklch(min(0.97, max(0.15, L + d)), Ch, h).hex for d in (-0.3, -0.15, 0, 0.15, 0.3)]
    if kind not in HARMONIES:
        raise SystemExit(f"kind must be one of {', '.join(list(HARMONIES) + ['monochrome'])}")
    return [c.hex if d == 0 else from_oklch(L, Ch, h + d).hex for d in HARMONIES[kind]]


NAMES = {"black": "#000000", "white": "#FFFFFF", "gray": "#808080", "silver": "#C0C0C0", "charcoal": "#36454F",
         "red": "#E32222", "crimson": "#DC143C", "maroon": "#800000", "orange": "#FF8C00", "coral": "#FF7F50",
         "peach": "#FFCBA4", "gold": "#FFD700", "yellow": "#FFE600", "mustard": "#E1AD01", "olive": "#808000",
         "lime": "#9ACD32", "green": "#2E9E44", "forest green": "#228B22", "mint": "#98FF98", "teal": "#008080",
         "turquoise": "#40E0D0", "cyan": "#00B7EB", "sky blue": "#87CEEB", "blue": "#1F4FE0", "navy": "#0B1F4D",
         "indigo": "#4B0082", "purple": "#7E3FBF", "violet": "#8F5BD7", "lavender": "#C8B6E2", "magenta": "#D6168B",
         "pink": "#FF8FB8", "rose": "#E8507A", "brown": "#7B4A2D", "chocolate": "#5C3317", "tan": "#D2B48C",
         "beige": "#EFE3C8", "cream": "#FFFAE6", "ivory": "#FFFFF0", "sand": "#D8C8A8", "slate": "#5A6B7B"}


def nearest_name(hex_: str) -> dict:
    import numpy as np

    c = C.parse(hex_)
    lab = rgb_to_oklab([c.r, c.g, c.b])
    best = min(NAMES.items(), key=lambda kv: float(np.sum((rgb_to_oklab(list(C.parse(kv[1]).rgba[:3])) - lab) ** 2)))
    return {"hex": c.hex, "name": best[0], "reference": best[1]}


# --- contrast check of a design ----------------------------------------------------------------


def check(project, artboards: list[str] | None = None) -> dict:
    """For every visible text layer: render the artboard WITHOUT that text, sample the pixels under
    the text's glyph box, and compare the text colour against the median and the worst background."""
    import numpy as np

    from . import design as D
    from . import render as R
    from . import text as T

    d = D.load(project)
    ctx = D.context(project, d)
    rows, fails, seen = [], 0, set()
    for ab in d["artboards"]:
        if artboards and ab["id"] not in artboards:
            continue
        unit, dpi = ab.get("unit", "px"), float(ab.get("dpi", 72))
        ppu = D.px_per_unit(ab)
        sc = min(1.0, 1200 / max(ab["width"] * ppu, ab["height"] * ppu))
        texts = [(l, ox, oy) for l, ox, oy in D.walk(ab.get("layers", [])) if l.get("type") == "text"]
        if not texts:
            continue
        for l, ox, oy in texts:
            hidden = _without(ab, l["id"])  # glyphs transparent, highlight boxes kept
            im, _ = R.render_artboard(ctx, hidden, scale=sc)
            arr = np.asarray(im.convert("RGB"), dtype=float)
            lay = T.layout(l, ctx, unit, dpi, ox, oy)
            k = ppu * sc
            for ln in lay.lines:
                for r in ln.runs:
                    if not r.text.strip() or r.style.color is None:
                        continue
                    f = T.font(r.style.ref)
                    top = ln.baseline - f.asc / f.upem * r.style.size
                    bot = ln.baseline - f.desc / f.upem * r.style.size
                    x0, x1 = int(max(0, r.x * k)), int(min(arr.shape[1], (r.x + r.width) * k))
                    y0, y1 = int(max(0, top * k)), int(min(arr.shape[0], bot * k))
                    if x1 <= x0 or y1 <= y0:
                        continue
                    patch = arr[y0:y1, x0:x1].reshape(-1, 3)
                    med = np.median(patch, axis=0)
                    fg = r.style.color
                    bg_med = C.Color(*[int(v) for v in med])
                    lums = patch @ np.array([0.2126, 0.7152, 0.0722])
                    worst_px = patch[np.argmin(np.abs(lums - (fg.r * .2126 + fg.g * .7152 + fg.b * .0722)))]
                    bg_worst = C.Color(*[int(v) for v in worst_px])
                    ratio, worst = C.contrast(fg, bg_med), C.contrast(fg, bg_worst)
                    pt = r.style.size * 0.75 if unit == "px" else r.style.size / D.UNITS_PER_INCH[unit] * 72
                    large = pt >= 18 or (pt >= 14 and r.style.ref.weight >= 700)
                    grade = C.wcag(ratio, large)
                    key = (ab["id"], l["id"], fg.hex, bg_med.hex)
                    if key in seen:
                        continue
                    seen.add(key)
                    fails += grade == "fail"
                    rows.append({"artboard": ab["id"], "layer": l["id"], "text": r.text.strip()[:40],
                                 "fg": fg.hex, "bg_median": bg_med.hex, "ratio": ratio, "worst_ratio": worst,
                                 "large": large, "grade": grade})
    return {"checked": len(rows), "fails": fails, "rows": rows}


def _without(ab: dict, layer_id: str) -> dict:
    import copy

    ab2 = copy.deepcopy(ab)

    def strip(layers):
        out = []
        for l in layers:
            if l.get("id") == layer_id:
                acc = {**(l.get("accent") or {}), "color": "#0000"}
                acc.pop("stroke", None)
                out.append({**l, "color": "#0000", "fill": "#0000", "stroke": None, "accent": acc})
                continue
            if l.get("type") == "group":
                l = {**l, "layers": strip(l.get("layers", []))}
            out.append(l)
        return out

    ab2["layers"] = strip(ab2.get("layers", []))
    return ab2


# --- CLI -----------------------------------------------------------------------------------


def cmd_color(a):
    if a.action == "contrast":
        return contrast_report(a.args[0], a.args[1])
    if a.action == "palette":
        return palette(a.args[0], a.n)
    if a.action == "scale":
        return {"base": C.parse(a.args[0]).hex, "scale": scale(a.args[0])}
    if a.action == "harmony":
        return {"base": C.parse(a.args[0]).hex, "kind": a.kind, "colors": harmony(a.args[0], a.kind)}
    if a.action == "cmyk":
        prof = C.cmyk_profile()
        return {"profile": str(prof) if prof else "formula (no ICC profile found; set DA_CMYK_ICC)",
                "colors": [{"hex": C.parse(h).hex, "cmyk": list(C.to_cmyk(C.parse(h)))} for h in a.args]}
    if a.action == "name":
        return [nearest_name(h) for h in a.args]
    if a.action == "check":
        from .project import Project

        return check(Project(a.args[0]), a.artboard)
    raise SystemExit(a.action)


def register(sub) -> None:
    p = sub.add_parser("color", help="contrast, palette from image, OKLCH scale, harmony, cmyk, name, check <p>")
    p.add_argument("action", choices=["contrast", "palette", "scale", "harmony", "cmyk", "name", "check"])
    p.add_argument("args", nargs="+", help="colours (#hex), an image path (palette) or a project (check)")
    p.add_argument("--n", type=int, default=6, help="palette size")
    p.add_argument("--kind", default="complementary", help="harmony kind")
    p.add_argument("--artboard", nargs="*", help="check: only these artboards")
    p.set_defaults(func=cmd_color)
