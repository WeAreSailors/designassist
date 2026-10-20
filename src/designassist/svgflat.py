"""Flatten simple SVG artwork (logos, icons, path layers) into absolute cubic paths with plain
fills and strokes, for exporters that build native vectors (Affinity).

Supported: path, rect (rx/ry), circle, ellipse, line, polyline, polygon, g, nested svg without
viewBox changes; transforms (matrix, translate, scale, rotate, skewX, skewY); presentation
attributes and inline style for fill, stroke, stroke-width, opacity, fill-opacity, stroke-opacity,
fill-rule, stroke-linecap, stroke-linejoin, color/currentColor.
Anything else that paints (gradients, patterns, clip paths, masks, filters, text, images, <use>)
raises Unsupported, and the caller falls back to placing the layer as a rendered bitmap.
"""
from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

Matrix = tuple[float, float, float, float, float, float]  # a b c d e f (SVG order)
IDENTITY: Matrix = (1, 0, 0, 1, 0, 0)
PAINTED = {"path", "rect", "circle", "ellipse", "line", "polyline", "polygon"}
IGNORED = {"title", "desc", "metadata", "defs", "style"}  # defs alone are fine if nothing references them


class Unsupported(ValueError):
    pass


@dataclass
class Shape:
    subpaths: list = field(default_factory=list)  # [[("M", x, y), ("L", x, y), ("C", x1, y1, x2, y2, x, y), ("Z",)]]
    fill: tuple | None = None  # (r, g, b, a 0-1)
    stroke: tuple | None = None
    stroke_width: float = 0.0  # in output units
    linecap: str = "butt"
    linejoin: str = "miter"
    evenodd: bool = False

    def to_json(self) -> dict:
        return {"subpaths": [[list(s) for s in sp] for sp in self.subpaths], "fill": list(self.fill) if self.fill else None,
                "stroke": list(self.stroke) if self.stroke else None,
                "stroke_width": self.stroke_width, "linecap": self.linecap, "linejoin": self.linejoin,
                "evenodd": self.evenodd}


def mul(m: Matrix, n: Matrix) -> Matrix:
    """m then... SVG composition: result = m x n (apply n first, then m)."""
    a, b, c, d, e, f = m
    A, B, C, D, E, F = n
    return (a * A + c * B, b * A + d * B, a * C + c * D, b * C + d * D, a * E + c * F + e, b * E + d * F + f)


def apply(m: Matrix, x: float, y: float) -> tuple[float, float]:
    a, b, c, d, e, f = m
    return a * x + c * y + e, b * x + d * y + f


def scale_of(m: Matrix) -> float:
    a, b, c, d, _, _ = m
    return math.sqrt(abs(a * d - b * c))


def parse_transform(s: str | None) -> Matrix:
    m = IDENTITY
    if not s:
        return m
    for name, args in re.findall(r"(\w+)\s*\(([^)]*)\)", s):
        v = [float(x) for x in re.findall(r"-?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?", args)]
        if name == "matrix" and len(v) == 6:
            t = tuple(v)
        elif name == "translate":
            t = (1, 0, 0, 1, v[0], v[1] if len(v) > 1 else 0)
        elif name == "scale":
            t = (v[0], 0, 0, v[1] if len(v) > 1 else v[0], 0, 0)
        elif name == "rotate":
            r = math.radians(v[0])
            t = (math.cos(r), math.sin(r), -math.sin(r), math.cos(r), 0, 0)
            if len(v) == 3:
                t = mul(mul((1, 0, 0, 1, v[1], v[2]), t), (1, 0, 0, 1, -v[1], -v[2]))
        elif name == "skewX":
            t = (1, 0, math.tan(math.radians(v[0])), 1, 0, 0)
        elif name == "skewY":
            t = (1, math.tan(math.radians(v[0])), 0, 1, 0, 0)
        else:
            raise Unsupported(f"transform {name}")
        m = mul(m, t)
    return m


class _Recorder:
    """Path sink for pdf.svg_path_to: collects absolute cubic subpaths through a matrix."""

    def __init__(self, m: Matrix):
        self.m, self.subpaths, self.cur = m, [], None

    def moveTo(self, x, y):
        self.cur = [("M", *apply(self.m, x, y))]
        self.subpaths.append(self.cur)

    def lineTo(self, x, y):
        self.cur.append(("L", *apply(self.m, x, y)))

    def curveTo(self, x1, y1, x2, y2, x, y):
        self.cur.append(("C", *apply(self.m, x1, y1), *apply(self.m, x2, y2), *apply(self.m, x, y)))

    def close(self):
        if self.cur is not None:
            self.cur.append(("Z",))


def _num(v, default=0.0) -> float:
    if v is None:
        return default
    m = re.match(r"\s*(-?[\d.]+(?:[eE][-+]?\d+)?)", str(v))
    return float(m.group(1)) if m else default


def _color(v: str | None, current: str | None, opacity: float):
    from . import colors as C

    if v is None or v.strip() in ("none", "transparent"):
        return None
    v = v.strip()
    if v.startswith("url("):
        raise Unsupported("gradient/pattern paint")
    if v == "currentColor":
        v = current or "#000000"
    try:
        c = C.parse(v)
    except C.ColorError:
        named = {"black": "#000", "white": "#fff", "red": "#f00", "blue": "#00f", "green": "#008000", "gray": "#808080",
                 "grey": "#808080", "yellow": "#ff0", "orange": "#ffa500"}
        if v.lower() in named:
            c = C.parse(named[v.lower()])
        else:
            raise Unsupported(f"colour {v}")
    if c is None:
        return None
    return (c.r, c.g, c.b, round(c.a * opacity, 4))


def _style(el, parent: dict) -> dict:
    st = dict(parent)
    st["opacity"] = 1.0  # opacity doesn't inherit; it multiplies
    for k in ("fill", "stroke", "stroke-width", "fill-opacity", "stroke-opacity", "fill-rule", "stroke-linecap",
              "stroke-linejoin", "color", "opacity", "display", "visibility"):
        if el.get(k) is not None:
            st[k] = el.get(k)
    for part in (el.get("style") or "").split(";"):
        if ":" in part:
            k, v = part.split(":", 1)
            st[k.strip()] = v.strip()
    st["_alpha"] = parent.get("_alpha", 1.0) * _num(st.get("opacity"), 1.0)
    return st


def _shape_d(el, tag: str) -> str:
    g = lambda k: _num(el.get(k))  # noqa: E731
    if tag == "path":
        return el.get("d") or ""
    if tag == "rect":
        x, y, w, h = g("x"), g("y"), g("width"), g("height")
        rx, ry = el.get("rx"), el.get("ry")
        rx = _num(rx if rx is not None else ry)
        ry = _num(ry if ry is not None else el.get("rx"))
        rx, ry = min(rx, w / 2), min(ry, h / 2)
        if rx <= 0 or ry <= 0:
            return f"M{x} {y}H{x + w}V{y + h}H{x}Z"
        return (f"M{x + rx} {y}H{x + w - rx}A{rx} {ry} 0 0 1 {x + w} {y + ry}V{y + h - ry}"
                f"A{rx} {ry} 0 0 1 {x + w - rx} {y + h}H{x + rx}A{rx} {ry} 0 0 1 {x} {y + h - ry}"
                f"V{y + ry}A{rx} {ry} 0 0 1 {x + rx} {y}Z")
    if tag in ("circle", "ellipse"):
        cx, cy = g("cx"), g("cy")
        rx = g("r") if tag == "circle" else g("rx")
        ry = g("r") if tag == "circle" else g("ry")
        return (f"M{cx - rx} {cy}A{rx} {ry} 0 1 0 {cx + rx} {cy}A{rx} {ry} 0 1 0 {cx - rx} {cy}Z")
    if tag == "line":
        return f"M{g('x1')} {g('y1')}L{g('x2')} {g('y2')}"
    if tag in ("polyline", "polygon"):
        pts = [float(v) for v in re.findall(r"-?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?", el.get("points") or "")]
        if len(pts) < 4:
            return ""
        d = f"M{pts[0]} {pts[1]}" + "".join(f"L{pts[i]} {pts[i + 1]}" for i in range(2, len(pts) - 1, 2))
        return d + ("Z" if tag == "polygon" else "")
    return ""


def flatten_tree(root, m: Matrix, base_style: dict | None = None) -> list[Shape]:
    from .pdf import svg_path_to

    out: list[Shape] = []

    def walk(el, mtx: Matrix, style: dict):
        tag = el.tag.split("}")[-1]
        if tag in IGNORED:
            return
        st = _style(el, style)
        if st.get("display") == "none" or st.get("visibility") == "hidden":
            return
        if el.get("clip-path") or el.get("mask") or el.get("filter") or st.get("clip-path") or st.get("mask") or st.get("filter"):
            raise Unsupported("clip-path/mask/filter")
        mtx = mul(mtx, parse_transform(el.get("transform")))
        if tag in ("g", "svg", "a", "switch"):
            if tag == "svg" and el is not root and el.get("viewBox"):
                raise Unsupported("nested svg with its own viewBox")
            for c in el:
                walk(c, mtx, st)
            return
        if tag not in PAINTED:
            raise Unsupported(f"<{tag}>")
        d = _shape_d(el, tag)
        if not d.strip():
            return
        alpha = st["_alpha"]
        fill = _color("none" if tag == "line" else st.get("fill", "#000000"), st.get("color"),
                      alpha * _num(st.get("fill-opacity"), 1.0))
        stroke = _color(st.get("stroke"), st.get("color"), alpha * _num(st.get("stroke-opacity"), 1.0))
        if fill is None and stroke is None:
            return
        rec = _Recorder(mtx)
        svg_path_to(rec, d)
        # drop lone movetos ("Z M x y" closing PDF-extracted paths): editors reject curves without segments
        subpaths = [sp for sp in rec.subpaths if any(seg[0] in "LC" for seg in sp)]
        if not subpaths:
            return
        out.append(Shape(subpaths, fill, stroke, _num(st.get("stroke-width"), 1.0) * scale_of(mtx),
                         st.get("stroke-linecap", "butt"), st.get("stroke-linejoin", "miter"),
                         st.get("fill-rule") == "evenodd"))

    for c in root:
        walk(c, m, _style(root, base_style or {}))
    return out


def viewbox(root) -> tuple[float, float, float, float]:
    vb = root.get("viewBox")
    if vb:
        v = [float(x) for x in re.split(r"[,\s]+", vb.strip())]
        return v[0], v[1], v[2], v[3]
    return 0.0, 0.0, _num(root.get("width"), 100), _num(root.get("height"), 100)


def fit_matrix(vb, x, y, w, h, fit: str = "contain") -> Matrix:
    """viewBox -> layer box (preserveAspectRatio xMidYMid meet, or none for fit=fill)."""
    vx, vy, vw, vh = vb
    if fit == "fill":
        sx, sy = w / vw, h / vh
        return (sx, 0, 0, sy, x - vx * sx, y - vy * sy)
    s = min(w / vw, h / vh)
    ox, oy = x + (w - vw * s) / 2, y + (h - vh * s) / 2
    return (s, 0, 0, s, ox - vx * s, oy - vy * s)


def flatten_file(text: str, x: float, y: float, w: float, h: float, fit: str = "contain",
                 recolor: tuple | None = None, icon_stroke: dict | None = None) -> list[Shape]:
    root = ET.fromstring(text)
    m = fit_matrix(viewbox(root), x, y, w, h, fit)
    base = {}
    if icon_stroke:  # Lucide: stroke=currentColor on the root, stroke-width override
        base = {"color": icon_stroke["color"]}
        if icon_stroke.get("width"):
            root.set("stroke-width", str(icon_stroke["width"]))
    shapes = flatten_tree(root, m, base)
    if recolor:
        for s in shapes:
            if s.fill:
                s.fill = (*recolor[:3], round(recolor[3] * s.fill[3], 4))
            if s.stroke:
                s.stroke = (*recolor[:3], round(recolor[3] * s.stroke[3], 4))
    return shapes
