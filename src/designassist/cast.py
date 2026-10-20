"""`cast`: a long ground shadow laid behind a layer (figures on a floor, objects in low sun).

    "cast": {"angle": 25, "length": 1.4, "width": 0.6, "blur": 1.2, "color": "$ink/85", "opacity": 1}

angle: direction the shadow falls (deg, 0 = right, 90 = down); length: shadow length / artwork height;
width: how much of the artwork's width the shadow keeps across (a true projection keeps only sin(angle) of it,
which reads as a thin line, so the body is widened away from the feet); blur: edge softness (units, default
1.2% of the height). The feet = the bottom of the artwork (svg art is contain-fitted inside the box).

Vector layers (path, svg, icon, figure:) get the shadow as real geometry, so Affinity keeps it as an editable
curve with a live Gaussian blur; other layers fall back to an affine projection in the SVG renderer.
"""
from __future__ import annotations

import math
import xml.etree.ElementTree as ET

from . import svgflat


def on(l: dict) -> bool:
    """`cast: {}` / `cast: true` = defaults; absent, null or false = no shadow."""
    return l.get("cast") is not None and l.get("cast") is not False


def params(l: dict, gh: float, L=lambda v: float(v)) -> dict:
    c = l["cast"] if isinstance(l["cast"], dict) else {}
    a = math.radians(float(c.get("angle", 25)))
    return {"a": a, "n": float(c.get("length", 1.4)), "width": float(c.get("width", 0.6)),
            "blur": L(c["blur"]) if c.get("blur") is not None else gh * 0.012,
            "color": c.get("color", "$ink"), "opacity": float(c.get("opacity", 1))}


def outline(ctx, l: dict, x: float, y: float, w: float, h: float) -> list | None:
    """The layer's artwork as absolute cubic subpaths in artboard units, or None when it isn't vector art."""
    t = l["type"]
    if t == "path":
        from .pdf import svg_path_to

        vb = l.get("viewbox") or [0, 0, w, h]
        sx, sy = w / float(vb[2]), h / float(vb[3])
        rec = svgflat._Recorder((sx, 0, 0, sy, x - float(vb[0]) * sx, y - float(vb[1]) * sy))
        svg_path_to(rec, l["d"])
        return rec.subpaths
    if t in ("svg", "icon") or (t == "image" and str(l.get("src", "")).lower().endswith(".svg")):
        if t == "icon":
            from .icons import icon_file

            path = icon_file(l["name"])
            shapes = svgflat.flatten_file(path.read_text(encoding="utf-8"), x, y, w, h,
                                          icon_stroke={"color": "#000", "width": l.get("stroke_width")})
        else:
            try:
                shapes = svgflat.flatten_file(ctx.src(l["src"]).read_text(encoding="utf-8"), x, y, w, h,
                                              l.get("fit", "contain"))
            except (svgflat.Unsupported, ET.ParseError):
                return None
        if any(s.stroke and not s.fill for s in shapes):
            return None  # stroked line art: its shadow needs the stroke outline, use the raster projection
        return [sp for s in shapes if s.fill for sp in s.subpaths]
    return None


def _bounds(subpaths) -> tuple[float, float, float, float]:
    xs = [v for sp in subpaths for seg in sp for v in seg[1::2]]
    ys = [v for sp in subpaths for seg in sp for v in seg[2::2]]
    return min(xs), min(ys), max(xs), max(ys)


def project(subpaths: list, p: dict) -> list:
    """Lay the outline on the ground: height above the feet becomes distance along the light, and the body is
    widened across the light (smoothly from the feet up, so the feet stay attached)."""
    x0, y0, x1, y1 = _bounds(subpaths)
    gy, cx, gh = y1, (x0 + x1) / 2, max(y1 - y0, 1e-6)
    a = p["a"]
    lx, ly = p["n"] * math.cos(a), p["n"] * math.sin(a)
    ca, sa = math.cos(a), math.sin(a)
    side = 1.0 if sa >= 0 else -1.0  # keeps the shadow's left/right the same way round as the artwork

    def f(x, y):
        hgt = max(0.0, gy - y)
        u = x - cx
        # in the light's frame a point's width offset u splits into along (u cos a) and across (-u sin a).
        # Across, ease from the true projection at the feet (they stay attached) to `width` of the artwork
        # above it: a true projection alone collapses to a line when the light is nearly horizontal.
        s = min(1.0, hgt / (0.18 * gh))
        s = s * s * (3 - 2 * s)
        d = -u * sa * (1 - s) - u * p["width"] * side * s
        return (cx + hgt * lx + u * ca * ca - d * sa, gy + hgt * ly + u * ca * sa + d * ca)

    out = []
    for sp in subpaths:
        nsp = []
        for seg in sp:
            if seg[0] == "Z":
                nsp.append(("Z",))
            else:
                pts = [f(seg[i], seg[i + 1]) for i in range(1, len(seg), 2)]
                nsp.append((seg[0], *[v for pt in pts for v in pt]))
        out.append(nsp)
    return out


def path_d(subpaths: list) -> str:
    return " ".join("Z" if seg[0] == "Z" else seg[0] + " ".join(f"{v:.2f}" for v in seg[1:]) for sp in subpaths for seg in sp)
