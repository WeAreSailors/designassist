"""Vector PDF export (reportlab).

screen  RGB, one page per artboard, page = trim. Social carousels (LinkedIn), proofs, Canva import.
print   CMYK (authored token `cmyk` first, then the ICC profile, see colors.to_cmyk), one artboard per
        file, page = trim + bleed + slug with crop marks; MediaBox/BleedBox/TrimBox set so print
        shops and Acrobat preflight read the right sizes. Images are converted to CMYK JPEGs.

Text is always drawn as outlined glyph paths from our text engine, so any font prints and the
PDF matches the PNG preview. What PDF operators can't express exactly (drop shadows, blend
modes, svg/icon artwork, gradients with transparent stops) is rasterized: that one layer is
rendered alone by resvg at the output resolution and placed as an image. Everything is drawn in
artboard units with a y-down transform, the same space as design.json.
"""
from __future__ import annotations

import io
import math
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from . import colors as C
from . import design as D
from . import images as I
from . import text as T

MM = 72 / 25.4
SLUG_MM = 10.0  # space outside the bleed for crop marks and the slug line (print mode)
MARK_GAP_MM = 1.0  # crop marks start this far outside the bleed edge
MARK_LEN_MM = 6.0


@dataclass
class Preflight:
    images: list = field(default_factory=list)  # {artboard, layer, effective_dpi, verdict}
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    rasterized: list = field(default_factory=list)  # layers placed as bitmaps
    converted: set = field(default_factory=set)  # print: RGB colours converted (no authored CMYK)

    def to_json(self) -> dict:
        out = {"errors": self.errors, "warnings": self.warnings, "images": self.images, "rasterized": self.rasterized}
        if self.converted:
            prof = C.cmyk_profile()
            out["cmyk_converted"] = {"colors": sorted(self.converted),
                                     "via": prof.name if prof else "formula (no ICC profile found; set DA_CMYK_ICC)",
                                     "tip": "give brand colours an authored cmyk in the tokens for exact print values"}
        return out


def pt_per_unit(ab: dict) -> float:
    unit = ab.get("unit", "px")
    if unit == "px":
        return 72.0 / float(ab.get("dpi", 72))
    return 72.0 / D.UNITS_PER_INCH[unit]


def units_per_inch(ab: dict) -> float:
    unit = ab.get("unit", "px")
    return float(ab.get("dpi", 72)) if unit == "px" else D.UNITS_PER_INCH[unit]


# --- SVG path data -> reportlab path ---------------------------------------------------------

_TOK = re.compile(r"[MLHVCSQTAZmlhvcsqtaz]|-?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")


def _arc_to_cubics(x1, y1, rx, ry, phi, large, sweep, x2, y2):
    """SVG elliptical arc -> list of cubic segments (c1, c2, end), per the SVG implementation notes."""
    if rx == 0 or ry == 0 or (x1 == x2 and y1 == y2):
        return [((x1, y1), (x2, y2), (x2, y2))]
    rx, ry = abs(rx), abs(ry)
    cp, sp = math.cos(math.radians(phi)), math.sin(math.radians(phi))
    dx, dy = (x1 - x2) / 2, (y1 - y2) / 2
    x1p, y1p = cp * dx + sp * dy, -sp * dx + cp * dy
    lam = x1p ** 2 / rx ** 2 + y1p ** 2 / ry ** 2
    if lam > 1:
        rx, ry = rx * math.sqrt(lam), ry * math.sqrt(lam)
    num = rx ** 2 * ry ** 2 - rx ** 2 * y1p ** 2 - ry ** 2 * x1p ** 2
    den = rx ** 2 * y1p ** 2 + ry ** 2 * x1p ** 2
    co = math.sqrt(max(0.0, num / den)) if den else 0.0
    if large == sweep:
        co = -co
    cxp, cyp = co * rx * y1p / ry, -co * ry * x1p / rx
    cx, cy = cp * cxp - sp * cyp + (x1 + x2) / 2, sp * cxp + cp * cyp + (y1 + y2) / 2

    def ang(ux, uy, vx, vy):
        a = math.atan2(ux * vy - uy * vx, ux * vx + uy * vy)
        return a

    t1 = ang(1, 0, (x1p - cxp) / rx, (y1p - cyp) / ry)
    dt = ang((x1p - cxp) / rx, (y1p - cyp) / ry, (-x1p - cxp) / rx, (-y1p - cyp) / ry)
    if not sweep and dt > 0:
        dt -= 2 * math.pi
    elif sweep and dt < 0:
        dt += 2 * math.pi
    n = max(1, math.ceil(abs(dt) / (math.pi / 2)))
    step = dt / n
    k = 4 / 3 * math.tan(step / 4)
    out = []
    for i in range(n):
        a1, a2 = t1 + i * step, t1 + (i + 1) * step
        e1 = (math.cos(a1), math.sin(a1))
        e2 = (math.cos(a2), math.sin(a2))
        p1 = (e1[0] - k * e1[1], e1[1] + k * e1[0])
        p2 = (e2[0] + k * e2[1], e2[1] - k * e2[0])

        def tr(p):
            px, py = p[0] * rx, p[1] * ry
            return (cp * px - sp * py + cx, sp * px + cp * py + cy)

        out.append((tr(p1), tr(p2), tr(e2)))
    return out


def svg_path_to(path, d: str) -> None:
    """Append SVG path data (any command, absolute or relative) to a reportlab path object."""
    toks = _TOK.findall(d)
    i, cmd = 0, None
    cx = cy = sx = sy = 0.0
    last_c2 = last_q = None
    started = False

    def num():
        nonlocal i
        v = float(toks[i])
        i += 1
        return v

    while i < len(toks):
        if toks[i].isalpha():
            cmd = toks[i]
            i += 1
            if cmd in "Zz":
                if started:
                    path.close()
                cx, cy = sx, sy
                last_c2 = last_q = None
                continue
        if cmd is None:
            raise ValueError("path data must start with a command")
        rel = cmd.islower()
        c = cmd.upper()
        ox, oy = (cx, cy) if rel else (0.0, 0.0)
        if c == "M":
            cx, cy = num() + ox, num() + oy
            sx, sy = cx, cy
            path.moveTo(cx, cy)
            started = True
            cmd = "l" if rel else "L"  # implicit lineto after the first pair
            last_c2 = last_q = None
        elif c == "L":
            cx, cy = num() + ox, num() + oy
            path.lineTo(cx, cy)
            last_c2 = last_q = None
        elif c == "H":
            cx = num() + ox
            path.lineTo(cx, cy)
            last_c2 = last_q = None
        elif c == "V":
            cy = num() + (cy if rel else 0.0)
            path.lineTo(cx, cy)
            last_c2 = last_q = None
        elif c in "CS":
            if c == "C":
                x1, y1 = num() + ox, num() + oy
            else:
                x1, y1 = (2 * cx - last_c2[0], 2 * cy - last_c2[1]) if last_c2 else (cx, cy)
            x2, y2 = num() + ox, num() + oy
            x, y = num() + ox, num() + oy
            path.curveTo(x1, y1, x2, y2, x, y)
            last_c2, last_q = (x2, y2), None
            cx, cy = x, y
        elif c in "QT":
            if c == "Q":
                qx, qy = num() + ox, num() + oy
            else:
                qx, qy = (2 * cx - last_q[0], 2 * cy - last_q[1]) if last_q else (cx, cy)
            x, y = num() + ox, num() + oy
            path.curveTo(cx + 2 / 3 * (qx - cx), cy + 2 / 3 * (qy - cy), x + 2 / 3 * (qx - x), y + 2 / 3 * (qy - y), x, y)
            last_q, last_c2 = (qx, qy), None
            cx, cy = x, y
        elif c == "A":
            rx, ry, phi = num(), num(), num()
            large, sweep = int(num()), int(num())
            x, y = num() + ox, num() + oy
            for c1, c2, e in _arc_to_cubics(cx, cy, rx, ry, phi, large, sweep, x, y):
                path.curveTo(c1[0], c1[1], c2[0], c2[1], e[0], e[1])
            cx, cy = x, y
            last_c2 = last_q = None
        else:
            raise ValueError(f"unsupported path command {cmd}")


class _CMYKAlpha:
    """ImageReader for a CMYK image with an alpha channel: reportlab writes the alpha as an SMask
    (its own reader only does that for RGBA)."""

    def __new__(cls, cmyk, alpha):
        from reportlab.lib.utils import ImageReader

        class Reader(ImageReader):
            def getRGBData(self):
                data = super().getRGBData()
                self._dataA = ImageReader(alpha)
                return data

        return Reader(cmyk)


# --- painter ---------------------------------------------------------------------------------

class Painter:
    def __init__(self, canvas, ctx: D.Context, ab: dict, mode: str, scale: float, pf: Preflight, tmp: Path):
        self.c, self.ctx, self.ab, self.mode, self.pf, self.tmp = canvas, ctx, ab, mode, pf, tmp
        self.unit, self.dpi = ab.get("unit", "px"), float(ab.get("dpi", 72))
        self.print = mode == "print"
        self.bleed = self.L(ab.get("bleed", 0)) if self.print else 0.0
        ppu = D.px_per_unit(ab)
        if self.print:  # bitmaps at >= 300 dpi of print size
            target = max(300.0, self.dpi if self.unit != "px" else 300.0)
            self.px_per_unit = target / units_per_inch(ab)
        else:
            self.px_per_unit = ppu * scale
        self.raster_scale = self.px_per_unit / ppu
        self.alpha = 1.0

    def L(self, v, d=0.0):
        return D.length(v, self.unit, self.dpi) if v is not None else d

    # colour ----------------------------------------------------------------------------------
    def _rl_color(self, col: C.Color):
        from reportlab.lib.colors import CMYKColor, Color

        if self.print:
            self._note(col)
            cm = C.to_cmyk(col)
            return CMYKColor(*(v / 100 for v in cm))
        return Color(col.r / 255, col.g / 255, col.b / 255)

    def _note(self, col: C.Color) -> None:
        if not col.cmyk and (col.r, col.g, col.b) != (0, 0, 0):
            self.pf.converted.add(f"${col.name}" if col.name else col.hex)

    def set_fill(self, col: C.Color) -> None:
        if self.print:
            self._note(col)
            self.c.setFillColorCMYK(*(v / 100 for v in C.to_cmyk(col)))
        else:
            self.c.setFillColorRGB(col.r / 255, col.g / 255, col.b / 255)
        self.c.setFillAlpha(col.a * self.alpha)

    def set_stroke(self, s: dict) -> bool:
        col = self.ctx.color(s.get("color", "$ink"))
        if col is None:
            return False
        if self.print:
            self._note(col)
            self.c.setStrokeColorCMYK(*(v / 100 for v in C.to_cmyk(col)))
        else:
            self.c.setStrokeColorRGB(col.r / 255, col.g / 255, col.b / 255)
        self.c.setStrokeAlpha(col.a * self.alpha)
        self.c.setLineWidth(self.L(s.get("width", 1)))
        self.c.setDash([self.L(x) for x in s["dash"]] if s.get("dash") else [])
        self.c.setLineCap({"butt": 0, "round": 1, "square": 2}.get(s.get("cap", "butt"), 0))
        self.c.setLineJoin({"miter": 0, "round": 1, "bevel": 2}.get(s.get("join", "miter"), 0))
        return True

    @staticmethod
    def is_gradient(v) -> bool:
        return isinstance(v, dict) and "stops" in v

    def gradient_ok(self, v) -> bool:
        """PDF shadings carry no alpha: gradients with transparent stops get rasterized."""
        return all((self.ctx.color(col) or C.Color(0, 0, 0, 0)).a >= 0.999 for _, col in v["stops"])

    def fill_shape(self, fill, path, bbox, stroke: dict | None = None) -> None:
        """Fill (colour or gradient) and stroke a reportlab path whose bbox is (x, y, w, h)."""
        c = self.c
        if self.is_gradient(fill):
            c.saveState()
            c.clipPath(path, stroke=0, fill=0)
            x, y, w, h = bbox
            cols = [self._rl_color(self.ctx.color(col)) for _, col in fill["stops"]]
            pos = [float(o) for o, _ in fill["stops"]]
            if fill.get("type", "linear") == "radial":
                # elliptical like the SVG preview (objectBoundingBox): circle of r*w, squashed to the box height
                c.translate(x + float(fill.get("cx", .5)) * w, y + float(fill.get("cy", .5)) * h)
                c.scale(1, h / w if w else 1)
                c.radialGradient(0, 0, float(fill.get("r", 0.5)) * w, cols, pos)
            else:
                a = math.radians(float(fill.get("angle", 90)))
                c.linearGradient(x + (0.5 - math.cos(a) / 2) * w, y + (0.5 - math.sin(a) / 2) * h,
                                 x + (0.5 + math.cos(a) / 2) * w, y + (0.5 + math.sin(a) / 2) * h, cols, pos)
            c.restoreState()
            if stroke and self.set_stroke(stroke):
                c.drawPath(path, stroke=1, fill=0)
            return
        col = self.ctx.color(fill) if fill is not None else None
        do_fill = col is not None
        if do_fill:
            self.set_fill(col)
        do_stroke = bool(stroke) and self.set_stroke(stroke)
        if do_fill or do_stroke:
            c.drawPath(path, stroke=1 if do_stroke else 0, fill=1 if do_fill else 0)

    # raster fallback ------------------------------------------------------------------------
    def raster_layer(self, l: dict, ox: float, oy: float, why: str) -> None:
        from .render import render_artboard

        wrapped = {"id": "__raster__", "type": "group", "x": ox, "y": oy, "layers": [l]}
        tmp_ab = {**self.ab, "layers": [wrapped]}
        im, _ = render_artboard(self.ctx, tmp_ab, self.raster_scale, bleed=self.bleed > 0, only=["__raster__"],
                                background=False)
        box = im.getchannel("A").getbbox()
        if not box:
            return
        crop = im.crop(box)
        ppu = self.px_per_unit
        x0, y0 = box[0] / ppu - self.bleed, box[1] / ppu - self.bleed
        self.pf.rasterized.append({"layer": l.get("id"), "why": why})
        self.place(crop, x0 - ox, y0 - oy, crop.width / ppu, crop.height / ppu, l.get("id"))

    def place(self, im, x: float, y: float, w: float, h: float, lid) -> None:
        """Draw a PIL image at x, y, w, h (current group space)."""
        from reportlab.lib.utils import ImageReader

        c = self.c
        has_alpha = im.mode == "RGBA" and im.getchannel("A").getextrema()[0] < 255
        c.saveState()
        c.translate(x, y + h)
        c.scale(1, -1)
        if self.print and not has_alpha:
            self.tmp.mkdir(parents=True, exist_ok=True)
            f = self.tmp / f"{self.ab['id']}-{lid}-{len(list(self.tmp.glob('*.jpg')))}.jpg"
            C.rgb_image_to_cmyk(im).save(f, quality=95)
            c.drawImage(str(f), 0, 0, w, h)
        elif self.print:  # CMYK pixels + soft mask, so transparent bitmaps match the vector inks
            c.drawImage(_CMYKAlpha(C.rgb_image_to_cmyk(im.convert("RGB")), im.getchannel("A")), 0, 0, w, h, mask="auto")
        else:
            buf = io.BytesIO()
            (im if has_alpha else im.convert("RGB")).save(buf, format="PNG")
            buf.seek(0)
            c.drawImage(ImageReader(buf), 0, 0, w, h, mask="auto" if has_alpha else None)
        c.restoreState()

    # layers -----------------------------------------------------------------------------------
    def needs_raster(self, l: dict) -> str | None:
        t = l["type"]
        if l.get("shadow"):
            return "drop shadow"
        if l.get("texture") or l.get("blur") or t == "noise":
            return "texture/blur/grain effect"
        if l.get("cast") is not None and l.get("cast") is not False:
            return "cast shadow"
        if l.get("blend") and l["blend"] != "normal":
            return f"blend mode {l['blend']}"
        if t in ("svg", "icon"):
            return f"{t} artwork"
        if t == "image" and str(l.get("src", "")).lower().endswith(".svg"):
            return "svg image"
        if t == "group" and l.get("opacity", 1) != 1:
            return "group opacity"
        if self.is_gradient(l.get("fill")) and not self.gradient_ok(l["fill"]):
            return "gradient with transparency"
        return None

    def layer(self, l: dict, ox: float, oy: float) -> None:
        if l.get("hidden"):
            return
        why = self.needs_raster(l)
        if why:
            self.raster_layer(l, ox, oy, why)
            return
        c = self.c
        t = l["type"]
        x, y, w, h = self.L(l.get("x")), self.L(l.get("y")), self.L(l.get("w")), self.L(l.get("h"))
        prev_alpha = self.alpha
        self.alpha *= float(l.get("opacity", 1))
        c.saveState()
        if l.get("rotation"):
            if t == "line":
                x2, y2 = self.L(l.get("x2")), self.L(l.get("y2"))
                cx, cy = (x + x2) / 2, (y + y2) / 2
            elif t == "text":
                lay = T.layout(l, self.ctx, self.unit, self.dpi)
                bx, by, bw, bh = lay.box
                cx, cy = bx + bw / 2, by + bh / 2
            else:
                cx, cy = x + w / 2, y + h / 2
            c.translate(cx, cy)
            c.rotate(float(l["rotation"]))
            c.translate(-cx, -cy)
        try:
            if t == "rect":
                p = c.beginPath()
                r = l.get("radius", 0)
                radii = [self.L(v) for v in r] if isinstance(r, list) else [self.L(r)] * 4
                if any(radii):
                    from .svg import rounded_rect_path

                    svg_path_to(p, rounded_rect_path(x, y, w, h, radii))
                else:
                    p.rect(x, y, w, h)
                self.fill_shape(l.get("fill", "$ink"), p, (x, y, w, h), l.get("stroke"))
            elif t == "ellipse":
                p = c.beginPath()
                p.ellipse(x, y, w, h)
                self.fill_shape(l.get("fill", "$ink"), p, (x, y, w, h), l.get("stroke"))
            elif t == "line":
                x2, y2 = self.L(l.get("x2")), self.L(l.get("y2"))
                if self.set_stroke(l.get("stroke") or {"color": "$ink", "width": 1}):
                    c.line(x, y, x2, y2)
            elif t == "path":
                vb = l.get("viewbox") or [0, 0, w, h]
                sx, sy = w / float(vb[2]), h / float(vb[3])
                c.translate(x, y)
                c.scale(sx, sy)
                c.translate(-float(vb[0]), -float(vb[1]))
                p = c.beginPath()
                try:
                    svg_path_to(p, l["d"])
                except (ValueError, IndexError):
                    c.restoreState()
                    self.alpha = prev_alpha
                    self.raster_layer(l, ox, oy, "path data not understood")
                    return
                st = l.get("stroke")
                if st:
                    st = {**st, "width": self.L(st.get("width", 1)) / max(1e-9, (sx + sy) / 2)}
                self.fill_shape(l.get("fill", "$ink"), p, (float(vb[0]), float(vb[1]), float(vb[2]), float(vb[3])), st)
            elif t == "image":
                self.image(l, x, y, w, h)
            elif t == "text":
                self.text(l, ox, oy)
            elif t == "group":
                c.translate(x, y)
                if l.get("clip") and w and h:
                    p = c.beginPath()
                    p.rect(0, 0, w, h)
                    c.clipPath(p, stroke=0, fill=0)
                kids = l.get("layers", [])
                if l.get("clip") and w and h:
                    from .svg import trim_to_clip

                    kids = [trim_to_clip(ch, w, h, self.L) for ch in kids]
                for ch in kids:
                    self.layer(ch, ox + x, oy + y)
        finally:
            c.restoreState()
            self.alpha = prev_alpha

    def image(self, l: dict, x: float, y: float, w: float, h: float) -> None:
        src = self.ctx.src(l["src"])
        if not src.exists():
            self.pf.errors.append(f"{self.ab['id']}/{l.get('id')}: missing image {l['src']}")
            return
        ppu = self.px_per_unit
        r = l.get("radius", 0)
        circle = l.get("mask") == "circle"
        clip_vector = self.print and (r or circle)  # keep CMYK: clip with a path instead of baking alpha
        rpx = 0 if clip_vector else ([self.L(v) * ppu for v in r] if isinstance(r, list) else self.L(r) * ppu)
        layer = {k: v for k, v in l.items() if not (clip_vector and k == "mask")}
        prep = I.prepare(layer, src, w * ppu, h * ppu, self.ctx.project.path("work", "cache"), self.ctx, rpx)
        inches = w / units_per_inch(self.ab)
        eff = prep.source_px[0] / inches if inches else 0
        verdict = "ok"
        if self.print:
            if eff < 150:
                verdict = "too low"
                self.pf.errors.append(f"{self.ab['id']}/{l.get('id')}: image is {eff:.0f} dpi at print size (needs 300)")
            elif eff < 300:
                verdict = "low"
                self.pf.warnings.append(f"{self.ab['id']}/{l.get('id')}: image is {eff:.0f} dpi at print size (300 recommended)")
        self.pf.images.append({"artboard": self.ab["id"], "layer": l.get("id"), "effective_dpi": round(eff),
                               "verdict": verdict})
        from PIL import Image

        im = Image.open(prep.path)
        im.load()
        c = self.c
        c.saveState()
        if clip_vector:
            p = c.beginPath()
            if circle:
                p.ellipse(x, y, w, h)
            else:
                from .svg import rounded_rect_path

                radii = [self.L(v) for v in r] if isinstance(r, list) else [self.L(r)] * 4
                svg_path_to(p, rounded_rect_path(x, y, w, h, radii))
            c.clipPath(p, stroke=0, fill=0)
        if self.alpha < 1:
            c.setFillAlpha(self.alpha)
        self.place(im.convert("RGBA") if prep.alpha else im.convert("RGB"), x, y, w, h, l.get("id"))
        c.restoreState()

    def text(self, l: dict, ox: float, oy: float) -> None:
        lay = T.layout(l, self.ctx, self.unit, self.dpi)
        c = self.c
        if lay.overflow:
            self.pf.warnings.append(f"{self.ab['id']}/{l.get('id')}: text overflows its box")
        if lay.missing_glyphs:
            self.pf.errors.append(f"{self.ab['id']}/{l.get('id')}: missing glyphs {''.join(lay.missing_glyphs)}")
        self._near_trim(l, lay, ox, oy)
        hl = l.get("highlight")
        all_runs, hl_runs = T.highlight_runs(lay)
        for ln in lay.lines:
            boxes = []
            if hl and ln.runs:
                boxes.append((hl, ln.x, ln.width, lay.size, ln.runs[0].style.ref, all_runs))
            boxes += [(r.style.highlight, r.x, r.width, r.style.size, r.style.ref, hl_runs)
                      for r in ln.runs if r.style.highlight]
            for h_, x_, w_, size, ref, ink_runs in boxes:
                bx, top, bw, bh = T.highlight_box(h_, x_, ln.baseline, w_, size, ref, ink_runs, self.L)
                p = c.beginPath()
                rad = self.L(h_.get("radius", 0))
                if rad:
                    p.roundRect(bx, top, bw, bh, rad)
                else:
                    p.rect(bx, top, bw, bh)
                self.fill_shape(h_.get("color", "$primary"), p, (bx, top, bw, bh))
        for ln in lay.lines:
            for r in ln.runs:
                if not r.glyphs or not r.text.strip():
                    continue
                d = T.run_path(r)
                if not d:
                    continue
                p = c.beginPath()
                svg_path_to(p, d)
                if r.style.stroke and self.set_stroke({"join": "round", **r.style.stroke}):
                    c.drawPath(p, stroke=1, fill=0, fillMode=1)  # stroke first: paint-order stroke
                if r.style.color is not None:
                    self.set_fill(r.style.color)
                    c.drawPath(p, stroke=0, fill=1, fillMode=1)  # nonzero winding, like the SVG preview

    def _near_trim(self, l: dict, lay, ox: float, oy: float) -> None:
        if not self.print:
            return
        margin = self.L(self.ab.get("margin", "3mm"))
        W, H = float(self.ab["width"]), float(self.ab["height"])
        for ln in lay.lines:
            if not ln.runs:
                continue
            top = oy + ln.baseline - lay.size * 0.8
            bottom = oy + ln.baseline + lay.size * 0.2
            left, right = ox + ln.x, ox + ln.x + ln.width
            d = min(left, top, W - right, H - bottom)
            if d < margin:
                where = "outside the trim" if d < 0 else f"{d:.1f} {self.unit} from the trim (margin {margin:g})"
                self.pf.warnings.append(f"{self.ab['id']}/{l.get('id')}: text {where}")
                return

    def check_bleed(self) -> None:
        if not self.print or self.bleed <= 0:
            return
        W, H = float(self.ab["width"]), float(self.ab["height"])
        eps = 0.5 if self.unit == "px" else 0.2
        for l in self.ab.get("layers", []):
            if l.get("hidden") or l["type"] in ("text", "line", "group"):
                continue
            x, y, w, h = self.L(l.get("x")), self.L(l.get("y")), self.L(l.get("w")), self.L(l.get("h"))
            edges = []
            for name, at_edge, past in (("left", abs(x) < eps, x <= -self.bleed + eps),
                                        ("top", abs(y) < eps, y <= -self.bleed + eps),
                                        ("right", abs(x + w - W) < eps, x + w >= W + self.bleed - eps),
                                        ("bottom", abs(y + h - H) < eps, y + h >= H + self.bleed - eps)):
                if at_edge and not past:
                    edges.append(name)
            if edges:
                self.pf.warnings.append(f"{self.ab['id']}/{l.get('id')}: reaches the {'/'.join(edges)} trim but stops "
                                        f"there; extend it {self.bleed:g} {self.unit} into the bleed")

    def background(self) -> None:
        bg = self.ab.get("background")
        if bg in (None, "none"):
            return
        W, H, b = float(self.ab["width"]), float(self.ab["height"]), self.bleed
        if self.is_gradient(bg) and not self.gradient_ok(bg):
            self.raster_layer({"id": "background", "type": "rect", "x": -b, "y": -b, "w": W + 2 * b, "h": H + 2 * b,
                               "fill": bg}, 0, 0, "gradient with transparency")
            return
        p = self.c.beginPath()
        p.rect(-b, -b, W + 2 * b, H + 2 * b)
        self.fill_shape(bg, p, (-b, -b, W + 2 * b, H + 2 * b))


def _crop_marks(c, x0, y0, tw, th, bleed_pt) -> None:
    """Registration-colour crop marks outside the bleed, at the trim lines (PDF points, y up)."""
    gap, ln = bleed_pt + MARK_GAP_MM * MM, MARK_LEN_MM * MM
    c.saveState()
    c.setStrokeColorCMYK(1, 1, 1, 1)  # registration
    c.setLineWidth(0.25)
    for tx in (x0, x0 + tw):
        for ty, sgn in ((y0, -1), (y0 + th, 1)):
            c.line(tx, ty + sgn * gap, tx, ty + sgn * (gap + ln))  # vertical mark
    for ty in (y0, y0 + th):
        for tx, sgn in ((x0, -1), (x0 + tw, 1)):
            c.line(tx + sgn * gap, ty, tx + sgn * (gap + ln), ty)  # horizontal mark
    c.restoreState()


def write(project, out: Path, artboards: list[dict], mode: str = "screen", scale: float = 2.0) -> dict:
    """Write one PDF with a page per artboard. mode = screen | print."""
    from reportlab import rl_config
    from reportlab.pdfgen import canvas as rl

    rl_config.useA85 = 0  # binary Flate streams: ~25% smaller than reportlab's ASCII85 default
    d = D.load(project)
    ctx = D.context(project, d)
    pf = Preflight()
    out.parent.mkdir(parents=True, exist_ok=True)
    c = rl.Canvas(str(out), pageCompression=1)
    c.setTitle(d.get("name", project.name))
    c.setCreator("designassist")
    tmp = project.path("work", "cache", "pdf")
    pages = []
    for ab in artboards:
        k = pt_per_unit(ab)
        W, H = float(ab["width"]), float(ab["height"])
        p = Painter(c, ctx, ab, mode, scale, pf, tmp)
        b_pt = p.bleed * k
        slug = SLUG_MM * MM if mode == "print" else 0.0
        off = b_pt + slug
        pw, ph = W * k + 2 * off, H * k + 2 * off
        c.setPageSize((pw, ph))
        if mode == "print":
            c.setTrimBox((off, off, off + W * k, off + H * k))
            c.setBleedBox((slug, slug, pw - slug, ph - slug))
            if ab.get("unit", "px") == "px":
                pf.warnings.append(f"{ab['id']}: artboard is in px; print size = px / {ab.get('dpi', 72)} dpi")
            if p.bleed <= 0:
                pf.warnings.append(f"{ab['id']}: no bleed set (print shops usually want 3 mm)")
        c.saveState()
        c.translate(off, ph - off)
        c.scale(k, -k)
        p.background()
        for l in ab.get("layers", []):
            p.layer(l, 0.0, 0.0)
        p.check_bleed()
        c.restoreState()
        if mode == "print":
            _crop_marks(c, off, off, W * k, H * k, b_pt)
            c.saveState()
            c.setFillColorCMYK(0, 0, 0, 1)
            c.setFont("Helvetica", 6)
            c.drawString(off, slug * 0.35, f"{d.get('name', project.name)} · {ab['id']} · {W:g}x{H:g} {ab.get('unit', 'px')}"
                                           f" · bleed {p.bleed:g} · {date.today().isoformat()}")
            c.restoreState()
        c.showPage()
        pages.append({"artboard": ab["id"], "page_pt": [round(pw, 2), round(ph, 2)],
                      "trim_pt": [round(W * k, 2), round(H * k, 2)]})
    c.save()
    return {"file": project.rel(out), "mode": mode, "pages": pages, "preflight": pf.to_json()}
