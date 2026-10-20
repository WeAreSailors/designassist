"""design.json artboard -> SVG. Every other output starts here or reuses its pieces.

Modes:
  preview   text as outlines (our text engine), images linked from work/cache. Rendered to PNG by resvg.
  outlined  text as outlines, images embedded: self-contained, prints/uploads anywhere (Canva, browsers).
  editable  text as <text> elements (one per line run, exact positions), images embedded: opens in
            Illustrator / Inkscape / Affinity with live text (fonts must be installed there).
"""
from __future__ import annotations

import base64
import math
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

from . import colors as C
from . import images as I
from . import text as T
from .design import Context, length, px_per_unit

SVG_NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG_NS)
ET.register_namespace("xlink", "http://www.w3.org/1999/xlink")


def trim_to_clip(l: dict, cw: float, ch: float, L) -> dict:
    """A "fill" image child of a clipping group, cut down to the part the clip shows (`_src_box` = the source
    fractions to keep). A screenshot crop places the whole 10k px capture several times the slide's size and lets the
    clip hide the rest: resampling and embedding all of it made one export take minutes."""
    if (l.get("type") != "image" or l.get("fit", "cover") != "fill" or l.get("hidden") or l.get("rotation")
            or l.get("radius") or l.get("mask") or "blur" in (l.get("filters") or {})
            or str(l.get("src", "")).lower().endswith(".svg")):
        return l
    x, y, w, h = L(l.get("x")), L(l.get("y")), L(l.get("w")), L(l.get("h"))
    if not (w and h):
        return l
    x0, y0, x1, y1 = max(x, 0.0), max(y, 0.0), min(x + w, cw), min(y + h, ch)
    if x1 <= x0 or y1 <= y0 or (x0, y0, x1, y1) == (x, y, x + w, y + h):
        return l
    a0, b0, a1, b1 = l.get("_src_box", (0.0, 0.0, 1.0, 1.0))
    fx = lambda v: a0 + (a1 - a0) * (v - x) / w  # noqa: E731
    fy = lambda v: b0 + (b1 - b0) * (v - y) / h  # noqa: E731
    return {**l, "x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0, "_src_box": [fx(x0), fy(y0), fx(x1), fy(y1)]}


@dataclass
class Report:
    texts: dict = field(default_factory=dict)  # layer id -> TextLayout.to_json()
    images: dict = field(default_factory=dict)  # layer id -> {source_px, upscaled, file}
    warnings: list = field(default_factory=list)
    fonts: set = field(default_factory=set)  # FontRefs used

    def to_json(self) -> dict:
        return {"texts": self.texts, "images": self.images, "warnings": self.warnings,
                "fonts": sorted({f"{r.family} {r.weight}{' italic' if r.italic else ''}" for r in self.fonts})}


def _f(v: float) -> str:
    s = f"{v:.3f}".rstrip("0").rstrip(".")
    return s if s not in ("-0", "") else "0"


class Builder:
    def __init__(self, ctx: Context, ab: dict, mode: str = "preview", scale: float = 1.0):
        self.ctx, self.ab, self.mode, self.scale = ctx, ab, mode, scale
        self.unit, self.dpi = ab.get("unit", "px"), float(ab.get("dpi", 72))
        self.ppu = px_per_unit(ab) * scale
        self.defs: list[str] = []
        self.n = 0
        self.report = Report()
        self.cache = ctx.project.path("work", "cache")

    def L(self, v, d=0.0) -> float:
        return length(v, self.unit, self.dpi) if v is not None else d

    def uid(self, p: str) -> str:
        self.n += 1
        return f"{p}{self.n}"

    # --- paint --------------------------------------------------------------------------
    def paint(self, v, attr: str = "fill") -> str:
        """fill="..." fill-opacity="..." for a colour or gradient value."""
        if v is None:
            return f'{attr}="none"'
        if isinstance(v, dict) and "stops" in v:
            gid = self.uid("g")
            stops = []
            for off, col in v["stops"]:
                c = self.ctx.color(col) or C.Color(0, 0, 0, 0)
                stops.append(f'<stop offset="{_f(float(off))}" stop-color="{c.hex}" stop-opacity="{_f(c.a)}"/>')
            if v.get("type", "linear") == "radial":
                self.defs.append(f'<radialGradient id="{gid}" cx="{_f(v.get("cx", .5))}" cy="{_f(v.get("cy", .5))}" '
                                 f'r="{_f(v.get("r", .5))}">{"".join(stops)}</radialGradient>')
            else:
                a = math.radians(float(v.get("angle", 90)))
                x1, y1 = 0.5 - math.cos(a) / 2, 0.5 - math.sin(a) / 2
                x2, y2 = 0.5 + math.cos(a) / 2, 0.5 + math.sin(a) / 2
                self.defs.append(f'<linearGradient id="{gid}" x1="{_f(x1)}" y1="{_f(y1)}" x2="{_f(x2)}" y2="{_f(y2)}">'
                                 f'{"".join(stops)}</linearGradient>')
            return f'{attr}="url(#{gid})"'
        c = self.ctx.color(v)
        if c is None:
            return f'{attr}="none"'
        return f'{attr}="{c.hex}"' + (f' {attr}-opacity="{_f(c.a)}"' if c.a < 1 else "")

    def stroke(self, s: dict | None) -> str:
        if not s:
            return ""
        out = self.paint(s.get("color", "$ink"), "stroke") + f' stroke-width="{_f(self.L(s.get("width", 1)))}"'
        if s.get("dash"):
            out += f' stroke-dasharray="{" ".join(_f(self.L(x)) for x in s["dash"])}"'
        if s.get("cap"):
            out += f' stroke-linecap="{s["cap"]}"'
        if s.get("join"):
            out += f' stroke-linejoin="{s["join"]}"'
        return out

    def common(self, l: dict, x: float, y: float, w: float, h: float) -> str:
        """opacity / rotation / blend / shadow attributes for a layer's outer element."""
        a = []
        if l.get("opacity", 1) != 1:
            a.append(f'opacity="{_f(float(l["opacity"]))}"')
        if l.get("rotation"):
            a.append(f'transform="rotate({_f(float(l["rotation"]))} {_f(x + w / 2)} {_f(y + h / 2)})"')
        if l.get("blend") and l["blend"] != "normal":
            a.append(f'style="mix-blend-mode:{l["blend"]}"')
        prims = self.filter_primitives(l)
        if prims:
            fid = self.uid("f")
            self.defs.append(f'<filter id="{fid}" x="-50%" y="-50%" width="200%" height="200%" '
                             f'color-interpolation-filters="sRGB">{prims}</filter>')
            a.append(f'filter="url(#{fid})"')
        return " ".join(a)

    def filter_primitives(self, l: dict) -> str:
        """texture (ink-eroded edges) -> blur -> drop shadow, chained in one filter."""
        out, src = [], "SourceGraphic"
        tx = l.get("texture")
        if tx:
            # ink bleed: soften the shape's alpha, add noise, threshold -> solid letters with rough edges,
            # then fill with the layer's colour (keeps white type white)
            tx = tx if isinstance(tx, dict) else {}
            spread = self.L(tx.get("spread", 2.8))  # how far the ink bleeds (units)
            size = self.L(tx.get("size", 4))  # grain of the roughness (units)
            rough = float(tx.get("rough", 1.0))
            col = self.ctx.color(tx.get("color") or l.get("color") or (l.get("fill") if isinstance(l.get("fill"), str) else None)
                                 or "$ink")
            out.append(f'<feGaussianBlur in="SourceAlpha" stdDeviation="{_f(spread)}" result="tb"/>'
                       f'<feTurbulence type="fractalNoise" baseFrequency="{_f(noise_freq(size))}" numOctaves="2" '
                       f'seed="{int(tx.get("seed", 7))}" result="tn"/>'
                       f'<feColorMatrix in="tn" type="matrix" values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  1 0 0 0 0" result="ta"/>'
                       f'<feComposite in="tb" in2="ta" operator="arithmetic" k1="0" k2="1" k3="{_f(rough)}" k4="{_f(-rough / 2)}" result="tm"/>'
                       f'<feComponentTransfer in="tm" result="tt"><feFuncA type="table" tableValues="0 0 0 1 1"/></feComponentTransfer>'
                       f'<feFlood flood-color="{col.hex}" flood-opacity="{_f(col.a)}"/><feComposite in2="tt" operator="in" result="tx"/>')
            src = "tx"
        if l.get("blur"):
            out.append(f'<feGaussianBlur in="{src}" stdDeviation="{_f(self.L(l["blur"]) / 2)}" result="bl"/>')
            src = "bl"
        if l.get("shadow"):
            s = l["shadow"]
            c = self.ctx.color(s.get("color", "#00000040"))
            out.append(f'<feDropShadow in="{src}" dx="{_f(self.L(s.get("x", 0)))}" dy="{_f(self.L(s.get("y", 4)))}" '
                       f'stdDeviation="{_f(self.L(s.get("blur", 12)) / 2)}" flood-color="{c.hex}" flood-opacity="{_f(c.a)}"/>')
        return "".join(out)

    # --- layers -------------------------------------------------------------------------
    def layer(self, l: dict, ox: float = 0.0, oy: float = 0.0) -> str:
        if l.get("hidden"):
            return ""
        if l.get("cast") is not None and l.get("cast") is not False:
            # cast shadow: the layer's own silhouette laid on the ground behind it
            body = "" if l.get("_cast_only") else self.layer({**l, "cast": None}, ox, oy)
            return f"<g>{self.cast(l, ox, oy)}{body}</g>"
        t = l["type"]
        x, y = self.L(l.get("x")), self.L(l.get("y"))
        w, h = self.L(l.get("w")), self.L(l.get("h"))
        lid = quoteattr(str(l.get("id", "")))
        if t == "text":
            return self.text(l, lid, ox, oy)
        if t == "line":
            x2, y2 = self.L(l.get("x2")), self.L(l.get("y2"))
            com = self.common(l, min(x, x2), min(y, y2), abs(x2 - x), abs(y2 - y))
            return (f'<line id={lid} x1="{_f(x)}" y1="{_f(y)}" x2="{_f(x2)}" y2="{_f(y2)}" '
                    f'{self.stroke(l.get("stroke") or {"color": "$ink", "width": 1})} {com}/>')
        com = self.common(l, x, y, w, h)
        if t == "rect":
            r = l.get("radius", 0)
            if isinstance(r, list):
                d = rounded_rect_path(x, y, w, h, [self.L(v) for v in r])
                return f'<path id={lid} d="{d}" {self.paint(l.get("fill", "$ink"))} {self.stroke(l.get("stroke"))} {com}/>'
            rx = f' rx="{_f(min(self.L(r), w / 2, h / 2))}"' if r else ""
            return (f'<rect id={lid} x="{_f(x)}" y="{_f(y)}" width="{_f(w)}" height="{_f(h)}"{rx} '
                    f'{self.paint(l.get("fill", "$ink"))} {self.stroke(l.get("stroke"))} {com}/>')
        if t == "noise":
            # film grain over the box. mode "speckle" (default): sparse dark + light specks with alpha only, so the
            # tone underneath doesn't shift; mode "overlay": contrasty grey noise blended (strong on saturated colours)
            size = self.L(l.get("size", 1.2))
            nid = self.uid("n")
            turb = (f'<feTurbulence type="fractalNoise" baseFrequency="{_f(noise_freq(size))}" numOctaves="3" '
                    f'seed="{int(l.get("seed", 3))}" stitchTiles="stitch" result="n"/>')
            if l.get("mode", "speckle") == "overlay":
                k = float(l.get("contrast", 6))
                body = (turb + '<feColorMatrix type="matrix" values="0.33 0.33 0.33 0 0  0.33 0.33 0.33 0 0  0.33 0.33 0.33 0 0  0 0 0 0 1"/>'
                        f'<feComponentTransfer><feFuncR type="linear" slope="{_f(k)}" intercept="{_f(-(k - 1) / 2)}"/>'
                        f'<feFuncG type="linear" slope="{_f(k)}" intercept="{_f(-(k - 1) / 2)}"/>'
                        f'<feFuncB type="linear" slope="{_f(k)}" intercept="{_f(-(k - 1) / 2)}"/></feComponentTransfer>')
                default_blend, default_op = "overlay", 0.35
            else:
                # alpha from the noise's distance to mid-grey: low values -> black specks, high -> white specks
                body = (turb +
                        '<feColorMatrix in="n" type="matrix" values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  -8 0 0 0 3.4" result="dk"/>'
                        '<feColorMatrix in="n" type="matrix" values="0 0 0 0 1  0 0 0 0 1  0 0 0 0 1  8 0 0 0 -4.6" result="lt"/>'
                        '<feMerge><feMergeNode in="dk"/><feMergeNode in="lt"/></feMerge>')
                default_blend, default_op = "normal", 0.5
            self.defs.append(f'<filter id="{nid}" x="0" y="0" width="100%" height="100%" color-interpolation-filters="sRGB">'
                             f'{body}<feComposite in2="SourceGraphic" operator="in"/></filter>')
            noise_l = {**l, "blend": l.get("blend", default_blend), "opacity": l.get("opacity", default_op)}
            com = self.common(noise_l, x, y, w, h)
            return (f'<rect id={lid} x="{_f(x)}" y="{_f(y)}" width="{_f(w)}" height="{_f(h)}" fill="#808080" '
                    f'filter="url(#{nid})" {com}/>')
        if t == "ellipse":
            return (f'<ellipse id={lid} cx="{_f(x + w / 2)}" cy="{_f(y + h / 2)}" rx="{_f(w / 2)}" ry="{_f(h / 2)}" '
                    f'{self.paint(l.get("fill", "$ink"))} {self.stroke(l.get("stroke"))} {com}/>')
        if t == "path":
            vb = l.get("viewbox") or [0, 0, w, h]
            sx, sy = w / float(vb[2]), h / float(vb[3])
            st = l.get("stroke")
            stroke = ""
            if st:
                st = {**st, "width": self.L(st.get("width", 1)) / max(1e-9, (sx + sy) / 2)}
                stroke = self.stroke(st)
            return (f'<g id={lid} {com}><g transform="translate({_f(x)} {_f(y)}) scale({_f(sx)} {_f(sy)}) '
                    f'translate({_f(-float(vb[0]))} {_f(-float(vb[1]))})"><path d={quoteattr(l["d"])} '
                    f'{self.paint(l.get("fill", "$ink"))} {stroke}/></g></g>')
        if t == "image":
            return self.image(l, lid, x, y, w, h, com)
        if t in ("svg", "icon"):
            return self.inline_svg(l, lid, x, y, w, h, com)
        if t == "group":
            kids = l.get("layers", [])
            if l.get("clip") and w and h:
                kids = [trim_to_clip(c, w, h, self.L) for c in kids]
            inner = "".join(self.layer(c, ox + x, oy + y) for c in kids)
            clip = ""
            if l.get("clip") and w and h:
                cid = self.uid("c")
                self.defs.append(f'<clipPath id="{cid}"><rect x="0" y="0" width="{_f(w)}" height="{_f(h)}"/></clipPath>')
                clip = f' clip-path="url(#{cid})"'
            return f'<g id={lid} {com}><g transform="translate({_f(x)} {_f(y)})"{clip}>{inner}</g></g>'
        self.report.warnings.append(f"{l.get('id')}: unknown layer type {t}")
        return ""

    def ground(self, l: dict) -> tuple[float, float, float, float]:
        """The box the layer's artwork actually fills (svg art is contain-fitted inside x, y, w, h)."""
        x, y, w, h = self.L(l.get("x")), self.L(l.get("y")), self.L(l.get("w")), self.L(l.get("h"))
        svgart = l["type"] in ("svg", "icon") or (l["type"] == "image" and str(l.get("src", "")).lower().endswith(".svg"))
        if svgart and l.get("fit", "contain") != "fill":
            from . import svgflat

            try:
                if l["type"] == "icon":
                    from .icons import icon_file

                    path = icon_file(l["name"])
                else:
                    path = self.ctx.src(l["src"])
                vb = svgflat.viewbox(ET.fromstring(path.read_text(encoding="utf-8")))
                m = svgflat.fit_matrix(vb, x, y, w, h)
                return m[4] + vb[0] * m[0], m[5] + vb[1] * m[3], vb[2] * m[0], vb[3] * m[3]
            except (OSError, ET.ParseError, SystemExit):
                pass
        return x, y, w, h

    def cast(self, l: dict, ox: float, oy: float) -> str:
        """Long ground shadow behind the layer (cast.py): real geometry for vector art; for anything else the
        layer itself is redrawn through an affine ground projection (feet fixed, head slid along the light)."""
        from . import cast as CS

        gx, gy, gw, gh = self.ground(l)
        p = CS.params(l, gh, self.L)
        col = self.ctx.color(p["color"])
        fid = self.uid("cs")
        blur = f'<feGaussianBlur stdDeviation="{_f(p["blur"] / 2)}"/>' if p["blur"] > 0 else ""
        op = p["opacity"] * float(l.get("opacity", 1))
        opa = f' opacity="{_f(op)}"' if op != 1 else ""
        sub = CS.outline(self.ctx, l, self.L(l.get("x")), self.L(l.get("y")), self.L(l.get("w")), self.L(l.get("h")))
        if sub:
            if blur:
                self.defs.append(f'<filter id="{fid}" x="-20%" y="-20%" width="140%" height="140%">{blur}</filter>')
            return (f'<path id={quoteattr(str(l.get("id", "")) + "-cast")} d="{CS.path_d(CS.project(sub, p))}" '
                    f'fill="{col.hex}" fill-opacity="{_f(col.a)}"{opa}' + (f' filter="url(#{fid})"' if blur else "") + "/>")
        lx, ly = p["n"] * math.cos(p["a"]), p["n"] * math.sin(p["a"])
        g = gy + gh
        mat = f"matrix(1 0 {_f(-lx)} {_f(-ly)} {_f(lx * g)} {_f(g * (1 + ly))})"
        self.defs.append(f'<filter id="{fid}" x="-20%" y="-20%" width="140%" height="140%" color-interpolation-filters="sRGB">'
                         f'<feFlood flood-color="{col.hex}" flood-opacity="{_f(col.a)}"/>'
                         f'<feComposite in2="SourceAlpha" operator="in"/>{blur}</filter>')
        sil = {**l, "cast": None, "_cast_only": None, "shadow": None, "texture": None, "blur": None, "opacity": 1,
               "blend": "normal", "rotation": None, "id": f"{l.get('id', '')}-cast"}
        return f'<g filter="url(#{fid})"{opa}><g transform="{mat}">{self.layer(sil, ox, oy)}</g></g>'

    def image(self, l, lid, x, y, w, h, com) -> str:
        src = self.ctx.src(l["src"])
        if not src.exists():
            self.report.warnings.append(f"{l.get('id')}: missing image {l['src']}")
            return f'<rect id={lid} x="{_f(x)}" y="{_f(y)}" width="{_f(w)}" height="{_f(h)}" fill="#FF00FF" opacity="0.5"/>'
        r = l.get("radius", 0)
        rpx = [self.L(v) * self.ppu for v in r] if isinstance(r, list) else self.L(r) * self.ppu
        if src.suffix.lower() == ".svg":
            return self.inline_svg({**l, "fit": l.get("fit", "contain")}, lid, x, y, w, h, com)
        prep = I.prepare(l, src, w * self.ppu, h * self.ppu, self.cache, self.ctx, rpx)
        self.report.images[l.get("id")] = {"source_px": list(prep.source_px), "upscaled": prep.upscaled,
                                           "out_px": [prep.width, prep.height], "file": prep.path.name}
        if self.mode == "preview":
            href = self.ctx.project.rel(prep.path)
        else:
            mime = "image/png" if prep.path.suffix == ".png" else "image/jpeg"
            href = f"data:{mime};base64," + base64.b64encode(prep.path.read_bytes()).decode()
        return (f'<image id={lid} x="{_f(x)}" y="{_f(y)}" width="{_f(w)}" height="{_f(h)}" '
                f'preserveAspectRatio="none" href={quoteattr(href)} {com}/>')

    def inline_svg(self, l, lid, x, y, w, h, com) -> str:
        if l["type"] == "icon":
            from .icons import icon_file

            path = icon_file(l["name"])
        else:
            path = self.ctx.src(l["src"])
        try:
            root = ET.fromstring(path.read_text(encoding="utf-8"))
        except ET.ParseError as e:
            self.report.warnings.append(f"{l.get('id')}: unreadable svg {path.name}: {e}")
            return ""
        vb = root.get("viewBox")
        if not vb:
            vw = float(re.sub(r"[^\d.]", "", root.get("width", "100")) or 100)
            vh = float(re.sub(r"[^\d.]", "", root.get("height", "100")) or 100)
            vb = f"0 0 {_f(vw)} {_f(vh)}"
        color = self.ctx.color(l["color"]) if l.get("color") else None
        # unique ids inside so two copies of the same logo don't clash
        prefix = self.uid("i") + "-"
        for el in root.iter():
            if el.get("id"):
                el.set("id", prefix + el.get("id"))
            for k, v in list(el.attrib.items()):
                if "url(#" in v:
                    el.set(k, v.replace("url(#", "url(#" + prefix))
                if k.endswith("href") and v.startswith("#"):
                    el.set(k, "#" + prefix + v[1:])
            if color is not None and l["type"] == "svg":
                for k in ("fill", "stroke"):
                    if el.get(k) not in (None, "none") and not str(el.get(k)).startswith("url("):
                        el.set(k, color.hex)
                st = el.get("style")
                if st:
                    el.set("style", re.sub(r"(fill|stroke)\s*:\s*(?!none)[^;]+", lambda m: f"{m.group(1)}:{color.hex}", st))
        if l["type"] == "icon":
            root.set("stroke", (color or self.ctx.color("$ink")).hex)
            if l.get("stroke_width"):
                root.set("stroke-width", str(l["stroke_width"]))
        inner = "".join(ET.tostring(c, encoding="unicode") for c in root)
        inner = re.sub(r'\s?xmlns(:\w+)?="[^"]+"', "", inner)
        keep = {k: v for k, v in root.attrib.items() if k in ("fill", "stroke", "stroke-width", "stroke-linecap",
                                                                "stroke-linejoin", "style", "color")}
        if color is not None and l["type"] == "svg" and keep.get("fill") not in (None, "none"):
            keep["fill"] = color.hex
        attrs = " ".join(f"{k}={quoteattr(v)}" for k, v in keep.items())
        par = "none" if l.get("fit") == "fill" else "xMidYMid meet"
        return (f'<g id={lid} {com}><svg x="{_f(x)}" y="{_f(y)}" width="{_f(w)}" height="{_f(h)}" viewBox="{vb}" '
                f'preserveAspectRatio="{par}" overflow="visible" {attrs}>{inner}</svg></g>')

    def text(self, l, lid, ox, oy) -> str:
        lay = T.layout(l, self.ctx, self.unit, self.dpi)  # local coords: groups are translated
        self.report.texts[l.get("id")] = lay.to_json()
        self.report.fonts.update(lay.fonts)
        x, y, w, h = lay.box
        com = self.common(l, x, y, w, h)
        parts = []
        hl = l.get("highlight")
        all_runs, hl_runs = T.highlight_runs(lay)
        for ln in lay.lines:
            if hl:
                parts.append(self._highlight(hl, ln.x, ln.baseline, ln.width, lay.size,
                                             ln.runs[0].style.ref if ln.runs else None, all_runs))
            for r in ln.runs:
                if r.style.highlight:
                    parts.append(self._highlight(r.style.highlight, r.x, ln.baseline, r.width, r.style.size,
                                                 r.style.ref, hl_runs))
        for ln in lay.lines:
            for r in ln.runs:
                if not r.glyphs or not r.text.strip():
                    continue
                fill = self.paint(r.style.color)
                stroke = ""
                if r.style.stroke:
                    stroke = self.stroke(r.style.stroke) + ' paint-order="stroke" stroke-linejoin="round"'
                if self.mode == "editable":
                    ref = r.style.ref
                    style = f"font-family:{quoteattr(ref.family)[1:-1]};font-weight:{ref.weight};" + (
                        "font-style:italic;" if ref.italic else "")
                    ls = f' letter-spacing="{_f(r.style.track)}"' if r.style.track else ""
                    parts.append(f'<text x="{_f(r.x)}" y="{_f(ln.baseline)}" font-size="{_f(r.style.size)}" '
                                 f'style="{style}" xml:space="preserve"{ls} {fill} {stroke}>{escape(r.text)}</text>')
                else:
                    d = T.run_path(r)
                    if d:
                        parts.append(f'<path d="{d}" {fill} {stroke}/>')
        return f'<g id={lid} {com}>{"".join(parts)}</g>'

    def _highlight(self, hl: dict, x: float, baseline: float, width: float, size: float, ref, runs=()) -> str:
        bx, by, bw, bh = T.highlight_box(hl, x, baseline, width, size, ref, runs, self.L)
        r = self.L(hl.get("radius", 0))
        return (f'<rect x="{_f(bx)}" y="{_f(by)}" width="{_f(bw)}" height="{_f(bh)}" '
                f'rx="{_f(r)}" {self.paint(hl.get("color", "$primary"))}/>')

    # --- document -----------------------------------------------------------------------
    def build(self, bleed: bool = False, only: list[str] | None = None, background: bool = True) -> str:
        W, H = float(self.ab["width"]), float(self.ab["height"])
        b = self.L(self.ab.get("bleed", 0)) if bleed else 0.0
        body = []
        if background and self.ab.get("background") not in (None, "none"):
            body.append(f'<rect x="{_f(-b)}" y="{_f(-b)}" width="{_f(W + 2 * b)}" height="{_f(H + 2 * b)}" '
                        f'{self.paint(self.ab["background"])}/>')
        for l in self.ab.get("layers", []):
            if only is not None and l.get("id") not in only:
                continue
            body.append(self.layer(l))
        pw, ph = (W + 2 * b) * self.ppu, (H + 2 * b) * self.ppu
        defs = f"<defs>{''.join(self.defs)}</defs>" if self.defs else ""
        return (f'<svg xmlns="{SVG_NS}" xmlns:xlink="http://www.w3.org/1999/xlink" width="{_f(pw)}" height="{_f(ph)}" '
                f'viewBox="{_f(-b)} {_f(-b)} {_f(W + 2 * b)} {_f(H + 2 * b)}">{defs}{"".join(body)}</svg>')


def noise_freq(size: float) -> float:
    """feTurbulence frequency for a grain of `size` units. Perlin noise is zero on its lattice, so a whole-number
    frequency (size 1 -> 1.0) samples only lattice points and renders flat grey: nudge it off the integers."""
    f = 1 / max(size, 0.01)
    if abs(f - round(f)) < 0.06:
        f += 0.0731
    return f


def rounded_rect_path(x, y, w, h, r) -> str:
    tl, tr, br, bl = (max(0.0, min(v, w / 2, h / 2)) for v in (list(r) + [0, 0, 0, 0])[:4])
    return (f"M{_f(x + tl)} {_f(y)}H{_f(x + w - tr)}A{_f(tr)} {_f(tr)} 0 0 1 {_f(x + w)} {_f(y + tr)}"
            f"V{_f(y + h - br)}A{_f(br)} {_f(br)} 0 0 1 {_f(x + w - br)} {_f(y + h)}H{_f(x + bl)}"
            f"A{_f(bl)} {_f(bl)} 0 0 1 {_f(x)} {_f(y + h - bl)}V{_f(y + tl)}A{_f(tl)} {_f(tl)} 0 0 1 {_f(x + tl)} {_f(y)}Z")


def artboard_svg(ctx: Context, ab: dict, mode: str = "preview", scale: float = 1.0, bleed: bool = False,
                 only: list[str] | None = None, background: bool = True) -> tuple[str, Report]:
    b = Builder(ctx, ab, mode, scale)
    s = b.build(bleed, only, background)
    return s, b.report
