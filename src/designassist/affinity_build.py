"""design.json -> a native, editable Affinity document, built live through the AI connector.

Mapping (everything converted to document pixels at the artboard's dpi):
  px artboards        one document, one Affinity artboard each, side by side (names = artboard ids)
  mm/in artboards     one print document each (trim size, dpi, bleed; background runs into the bleed)
  rect / ellipse      native shapes (corner radii, solid or gradient fill, stroke)
  path / line / svg / icon   native curves (svgflat.py); artwork it can't flatten is placed as a bitmap
  image               the prepared bitmap (crop, focus, filters, radius baked) as an image layer
  text                live frame text: font by PostScript name, size, exact leading, tracking, colour,
                      alignment, accent runs, stroke; moved so its ink top matches the preview
  group               an Affinity layer (container) holding its children
  opacity / blend / rotation / shadow (outer shadow layer effect) on every layer
Every layer is named with its design id, so `da affinity pull` can map edits back.
Scripts can only touch the Desktop, so bitmaps and the saved .af go through
~/Desktop/designassist-affinity/<project>/; the .af is copied into output/affinity/.
"""
from __future__ import annotations

import copy
import json
import math
import shutil
from pathlib import Path

from . import colors as C
from . import design as D
from . import images as I
from . import svgflat
from . import text as T
from .project import Project, write_json

RUNTIME = Path(__file__).parent / "jsx" / "affinity.js"
READER = Path(__file__).parent / "jsx" / "affinity_read.js"
GAP = 100  # px between artboards in the Affinity document
ALIGN = {"left": "Left", "center": "Centre", "right": "Right", "justify": "JustifyLeft"}


def _rgba(c: C.Color | None):
    return None if c is None else [c.r, c.g, c.b, round(c.a, 4)]


def blend_key(b: str | None) -> str | None:
    if not b or b == "normal":
        return None
    return b.replace("-", "").replace("color", "colour")


STYLE = {100: "Thin", 200: "ExtraLight", 300: "Light", 400: "Regular", 500: "Medium", 600: "SemiBold",
         700: "Bold", 800: "ExtraBold", 900: "Black"}


PREMULTIPLY = False  # Affinity reads straight alpha (premultiplying gave dark halos, 2026-10-19)


def affinity_png(im):
    """RGBA bitmap as Affinity reads it: colour premultiplied by alpha (straight-alpha PNGs come out with light,
    spread-out soft edges: blurred shapes, shadows, anti-aliasing)."""
    if not PREMULTIPLY or im.mode != "RGBA":
        return im
    import numpy as np
    from PIL import Image

    a = np.asarray(im, dtype=np.float32)
    a[..., :3] *= a[..., 3:4] / 255.0
    return Image.fromarray(a.round().astype("uint8"), "RGBA")


def font_request(ref) -> dict:
    style = STYLE.get(int(round(ref.weight / 100.0) * 100), "Regular")
    if ref.italic:
        style = "Italic" if style == "Regular" else style + " Italic"
    return {"family": ref.family, "style": style}


class Converter:
    def __init__(self, ctx: D.Context, ab: dict, ox: float, oy: float, stage: Path, px_scale: float, doc_scale: float = 1.0):
        self.ctx, self.ab = ctx, ab
        self.unit, self.dpi = ab.get("unit", "px"), float(ab.get("dpi", 72))
        self.ppu = D.px_per_unit(ab) * doc_scale  # document px per design unit (4k: a 1080 post is built 3072 wide)
        self.doc_scale = doc_scale
        self.ox, self.oy = ox, oy  # artboard origin in document px
        self.stage = stage
        self.px_scale = px_scale  # bitmap resolution multiplier for px artboards
        self.ops: list[dict] = []
        self.notes: list[str] = []
        self.fonts: dict = {}  # postscript -> {family, style} (Affinity names variable instances its own way)
        self.fallback: list[str] = []
        self.parent0 = None

    def L(self, v, d=0.0) -> float:
        return D.length(v, self.unit, self.dpi) if v is not None else d

    def X(self, u: float) -> float:
        return self.ox + u * self.ppu

    def Y(self, u: float) -> float:
        return self.oy + u * self.ppu

    def fill(self, v, box) -> dict | None:
        if v is None:
            return None
        if isinstance(v, dict) and "stops" in v:
            bx, by, bw, bh = box
            stops = [[float(o), _rgba(self.ctx.color(c) or C.Color(0, 0, 0, 0))] for o, c in v["stops"]]
            if v.get("type", "linear") == "radial":
                r = float(v.get("r", .5))  # fraction of the box on each axis, like the SVG preview
                return {"gradient": {"radial": True, "stops": stops, "cx": bx + float(v.get("cx", .5)) * bw,
                                     "cy": by + float(v.get("cy", .5)) * bh, "rx": r * bw, "ry": r * bh}}
            a = math.radians(float(v.get("angle", 90)))
            return {"gradient": {"stops": stops, "x1": bx + (0.5 - math.cos(a) / 2) * bw, "y1": by + (0.5 - math.sin(a) / 2) * bh,
                                 "x2": bx + (0.5 + math.cos(a) / 2) * bw, "y2": by + (0.5 + math.sin(a) / 2) * bh}}
        c = self.ctx.color(v)
        return None if c is None else {"rgba": _rgba(c)}

    def stroke(self, s) -> dict | None:
        if not s:
            return None
        c = self.ctx.color(s.get("color", "$ink"))
        return None if c is None else {"rgba": _rgba(c), "width": self.L(s.get("width", 1)) * self.ppu,
                                       "cap": (s.get("cap") or "butt").capitalize(), "join": (s.get("join") or "miter").capitalize()}

    def common(self, l: dict, box_px: tuple, parent) -> dict:
        x, y, w, h = box_px
        op = {"id": l["id"], "parent": parent}
        if l.get("opacity", 1) != 1:
            op["opacity"] = float(l["opacity"])
        if blend_key(l.get("blend")):
            op["blend"] = blend_key(l["blend"])
        if l.get("rotation"):
            op["rotation"], op["cx"], op["cy"] = float(l["rotation"]), x + w / 2, y + h / 2
        if l.get("shadow"):
            s = l["shadow"]
            c = self.ctx.color(s.get("color", "#00000040"))
            op["shadow"] = {"rgba": _rgba(c), "blur": self.L(s.get("blur", 12)) * self.ppu * 1.2,  # Affinity radius ~ the whole blur, not sigma
                            "dx": self.L(s.get("x", 0)) * self.ppu, "dy": self.L(s.get("y", 4)) * self.ppu}
        return op

    # --- layers -----------------------------------------------------------------------------
    def layers(self, layers: list, gx: float = 0.0, gy: float = 0.0, parent=None) -> None:
        for l in layers:
            if l.get("hidden"):
                continue
            try:
                self.layer(l, gx, gy, parent)
            except svgflat.Unsupported as e:
                self.raster(l, gx, gy, parent, f"placed as a bitmap ({e})")

    def layer(self, l: dict, gx: float, gy: float, parent) -> None:
        t = l["type"]
        if l.get("texture") or l.get("blur") or t == "noise":
            raise svgflat.Unsupported("texture/blur/grain effect")
        if l.get("cast") is not None and l.get("cast") is not False:
            self.cast(l, gx, gy, parent)
            return self.layer({**l, "cast": None}, gx, gy, parent)
        x, y = gx + self.L(l.get("x")), gy + self.L(l.get("y"))
        w, h = self.L(l.get("w")), self.L(l.get("h"))
        box = (self.X(x), self.Y(y), w * self.ppu, h * self.ppu)
        if t == "text":
            return self.text(l, gx, gy, parent)
        if t == "group":
            self.ops.append({**self.common(l, box, parent), "op": "group"})
            return self.layers(l.get("layers", []), x, y, l["id"])
        if t in ("rect", "ellipse"):
            r = l.get("radius", 0)
            rad = [self.L(v) * self.ppu for v in r] if isinstance(r, list) else [self.L(r) * self.ppu] * 4
            rad = [min(v, box[2] / 2, box[3] / 2) for v in rad]
            self.ops.append({**self.common(l, box, parent), "op": t, "x": box[0], "y": box[1], "w": box[2], "h": box[3],
                             "radius": rad if t == "rect" else None, "fill": self.fill(l.get("fill", "$ink"), box),
                             "stroke": self.stroke(l.get("stroke"))})
            return
        if t == "line":
            x2, y2 = gx + self.L(l.get("x2")), gy + self.L(l.get("y2"))
            st = self.stroke(l.get("stroke") or {"color": "$ink", "width": 1})
            sh = svgflat.Shape([[("M", self.X(x), self.Y(y)), ("L", self.X(x2), self.Y(y2))]], None, st["rgba"],
                               st["width"], (l.get("stroke") or {}).get("cap", "butt"))
            bx = (min(self.X(x), self.X(x2)), min(self.Y(y), self.Y(y2)), abs(x2 - x) * self.ppu, abs(y2 - y) * self.ppu)
            self.ops.append({**self.common(l, bx, parent), "op": "curves", "shapes": [sh.to_json()]})
            return
        if t == "path":
            from .pdf import svg_path_to

            vb = l.get("viewbox") or [0, 0, w, h]
            sx, sy = box[2] / float(vb[2]), box[3] / float(vb[3])
            m = (sx, 0, 0, sy, box[0] - float(vb[0]) * sx, box[1] - float(vb[1]) * sy)
            rec = svgflat._Recorder(m)
            svg_path_to(rec, l["d"])
            st = self.stroke(l.get("stroke"))
            fill = self.fill(l.get("fill", "$ink"), box)
            sh = svgflat.Shape(rec.subpaths, None, st["rgba"] if st else None, st["width"] if st else 0)
            js = sh.to_json()
            js["fill_desc"] = fill
            self.ops.append({**self.common(l, box, parent), "op": "curves", "shapes": [js]})
            return
        if t in ("svg", "icon") or (t == "image" and str(l.get("src", "")).lower().endswith(".svg")):
            if t == "icon":
                from .icons import icon_file

                c = self.ctx.color(l.get("color", "$ink"))
                shapes = svgflat.flatten_file(icon_file(l["name"]).read_text(encoding="utf-8"), *box,
                                              icon_stroke={"color": c.hex, "width": l.get("stroke_width")})
                for s in shapes:
                    s.stroke = (*s.stroke[:3], round(s.stroke[3] * c.a, 4)) if s.stroke else None
            else:
                c = self.ctx.color(l["color"]) if l.get("color") else None
                shapes = svgflat.flatten_file(self.ctx.src(l["src"]).read_text(encoding="utf-8"), *box,
                                              fit=l.get("fit", "contain"), recolor=_rgba(c) if c else None)
            if not shapes:
                return
            self.ops.append({**self.common(l, box, parent), "op": "curves", "shapes": [s.to_json() for s in shapes]})
            return
        if t == "image":
            src = self.ctx.src(l["src"])
            r = l.get("radius", 0)
            cache = self.ctx.project.path("work", "cache")

            def prepared(scale):
                rpx = [self.L(v) * self.ppu * scale for v in r] if isinstance(r, list) else self.L(r) * self.ppu * scale
                return I.prepare(l, src, box[2] * scale, box[3] * scale, cache, self.ctx, rpx)

            prep = prepared(1.0)
            if self.unit == "px" and self.px_scale > 1:
                # more pixels than the artboard needs only when the source has them (no upscaling)
                room = min(prep.source_px[0] / max(1, box[2]), prep.source_px[1] / max(1, box[3]))
                s = min(self.px_scale, room)
                if s > 1.05:
                    prep = prepared(s)
            staged = self.stage / prep.path.name
            if not staged.exists():
                shutil.copy2(prep.path, staged)
            self.ops.append({**self.common(l, box, parent), "op": "image", "file": staged.as_posix(),
                             "x": box[0], "y": box[1], "w": box[2], "h": box[3]})
            if prep.upscaled > 1.25:
                self.notes.append(f"{l['id']}: image upscaled {prep.upscaled:.2f}x")
            return
        self.notes.append(f"{l.get('id')}: unknown layer type {t}")

    def text(self, l: dict, gx: float, gy: float, parent) -> None:
        lay = T.layout(l, self.ctx, self.unit, self.dpi, gx, gy)
        if not lay.lines or not lay.styles:
            return
        self.fallback += lay.fallback_fonts
        base, acc = lay.styles
        x, y, bw, bh = lay.box
        ppu = self.ppu
        # highlight boxes (line or accent) as shapes under the text, same geometry as svg.py
        hl = l.get("highlight")
        all_runs, hl_runs = T.highlight_runs(lay)
        n = 0
        for ln in lay.lines:
            targets = [(hl, ln.x, ln.width, lay.size, ln.runs[0].style.ref if ln.runs else None, all_runs)] if hl else []
            targets += [(r.style.highlight, r.x, r.width, r.style.size, r.style.ref, hl_runs)
                        for r in ln.runs if r.style.highlight]
            for spec, hx, hw, size, ref, ink_runs in targets:
                n += 1
                hx0, top, hw0, hh = T.highlight_box(spec, hx, ln.baseline, hw, size, ref, ink_runs, self.L)
                bx = (self.X(hx0), self.Y(top), hw0 * ppu, hh * ppu)
                rr = self.L(spec.get("radius", 0)) * ppu
                self.ops.append({"id": f"{l['id']}-highlight-{n}", "parent": parent, "op": "rect", "x": bx[0], "y": bx[1],
                                 "w": bx[2], "h": bx[3], "radius": [rr] * 4,
                                 "fill": self.fill(spec.get("color", "$primary"), bx), "stroke": None})
        paragraphs = []
        for para in lay.text.split("\n"):
            runs = []
            for t_, is_acc in T.parse_markup(para):
                st = acc if is_acc else base
                self.fonts[st.ref.postscript] = font_request(st.ref)
                run = {"text": t_, "ps": st.ref.postscript, "size": st.size * ppu, "tracking": st.tracking / 1000,
                       "rgba": _rgba(st.color) or [0, 0, 0, 0]}
                if st.stroke:
                    sc = self.ctx.color(st.stroke.get("color", "$ink"))
                    run["stroke"] = {"rgba": _rgba(sc), "width": self.L(st.stroke.get("width", 1)) * ppu}
                runs.append(run)
            paragraphs.append(runs or [{"text": "", "ps": base.ref.postscript, "size": base.size * ppu,
                                        "tracking": 0, "rgba": _rgba(base.color) or [0, 0, 0, 1]}])
        ink = T.ink_box(lay)
        wrap = l.get("w") is not None
        fw = (bw * ppu + 0.5) if wrap else (lay.content_w * ppu * 1.08 + base.size * ppu)
        fx = self.X(x)
        if not wrap and l.get("align") in ("center", "right"):
            fx = self.X(lay.lines[0].x) - (fw - lay.content_w * ppu) * (0.5 if l["align"] == "center" else 1.0)
        fh = max(bh, lay.content_h) * ppu + base.size * ppu
        box = (fx, self.Y(y), fw, fh)
        op = {**self.common(l, (self.X(x), self.Y(y), bw * ppu, bh * ppu), parent), "op": "text",
              "x": fx, "y": self.Y(y), "w": fw, "h": fh, "leading": lay.size * float(l.get("line_height", 1.2)) * ppu,
              "align": ALIGN.get(l.get("align", "left"), "Left"), "paragraphs": paragraphs,
              "ink": [self.X(ink[0]), self.Y(ink[1]), self.X(ink[2]), self.Y(ink[3])] if ink else [box[0], box[1], box[0], box[1]],
              "lines": len(lay.lines)}
        if lay.overflow:
            self.notes.append(f"{l['id']}: text overflows its box in the design")
        if not l.get("w") and l.get("align") == "justify":
            op["align"] = "Left"
        elif l.get("align") == "justify" and l.get("justify_all"):
            op["align"] = "JustifyAll"  # last line spread too
        self.ops.append(op)

    def cast(self, l: dict, gx: float, gy: float, parent) -> None:
        """Ground shadow as its own layer under the art: an editable curve with a live Gaussian blur for vector
        art, a bitmap of the projected layer otherwise."""
        from . import cast as CS

        x, y = gx + self.L(l.get("x")), gy + self.L(l.get("y"))
        sub = CS.outline(self.ctx, l, x, y, self.L(l.get("w")), self.L(l.get("h")))
        if not sub:
            return self.raster({**l, "_cast_only": True, "id": l["id"] + "-cast"}, gx, gy, parent, "cast shadow placed as a bitmap")
        _, y0, _, y1 = CS._bounds(sub)
        p = CS.params(l, y1 - y0, self.L)
        px = [[seg if seg[0] == "Z" else (seg[0], *[self.X(v) if i % 2 == 0 else self.Y(v) for i, v in enumerate(seg[1:])])
               for seg in sp] for sp in CS.project(sub, p)]
        js = svgflat.Shape(px).to_json()
        js["fill_desc"] = {"rgba": _rgba(self.ctx.color(p["color"]))}
        op = {"id": l["id"] + "-cast", "parent": parent, "op": "curves", "shapes": [js]}
        alpha = p["opacity"] * float(l.get("opacity", 1))
        if alpha != 1:
            op["opacity"] = alpha
        # Affinity's blur radius vs our blur, measured on edge widths: it scales ~1.17x and the effect adds
        # ~2 doc px of softness of its own, so small blurs need less (or none)
        r = 1.17 * p["blur"] * self.ppu - 2.0
        if r > 0.5:
            op["blur"] = r
        self.ops.append(op)

    def raster(self, l: dict, gx: float, gy: float, parent, why: str) -> None:
        """Fallback: render this one layer (with its group offset) to a bitmap and place it."""
        from .render import render_artboard

        lay = copy.deepcopy(l)
        lay["x"] = gx + self.L(l.get("x"))
        lay["y"] = gy + self.L(l.get("y"))
        # opacity and blend stay live on the Affinity layer, so the bitmap is rendered without them
        # (applying them in both places made grain twice as faint)
        default_op = (0.35 if l.get("mode") == "overlay" else 0.5) if l["type"] == "noise" else 1.0
        default_blend = ("overlay" if l.get("mode") == "overlay" else "normal") if l["type"] == "noise" else "normal"
        live = {**l, "opacity": float(l.get("opacity", default_op)), "blend": l.get("blend", default_blend)}
        lay["opacity"], lay["blend"] = 1, "normal"
        ab = {**self.ab, "layers": [lay], "bleed": 0}
        # grain is defined in output pixels: render it 1:1 (a 2x bitmap gets averaged away when Affinity scales it)
        scale = max(self.px_scale, self.doc_scale) if self.unit == "px" and l["type"] != "noise" else self.doc_scale
        im, _ = render_artboard(self.ctx, ab, scale, False, None, False)
        bbox = im.getchannel("A").getbbox()
        if not bbox:
            return
        crop = im.crop(bbox)
        f = self.stage / f"raster-{self.ab['id']}-{l['id']}.png"
        affinity_png(crop).save(f)
        s = D.px_per_unit(self.ab) * scale  # render px per unit
        x0, y0 = bbox[0] / s, bbox[1] / s
        box = (self.X(x0), self.Y(y0), crop.width / s * self.ppu, crop.height / s * self.ppu)
        op = {**self.common({**live, "rotation": None, "shadow": None}, box, parent), "op": "image", "file": f.as_posix(),
              "x": box[0], "y": box[1], "w": box[2], "h": box[3]}
        self.ops.append(op)
        self.notes.append(f"{l['id']}: {why}")


# --- build ----------------------------------------------------------------------------------

def plan(project: Project, artboards: list[str] | None = None, stage: Path | None = None, px_scale: float = 2.0,
         doc_scale: float | None = None) -> dict:
    """The DA spec the runtime executes (also used by tests, without Affinity). doc_scale: build px documents
    bigger than the artboards (default 1: artboard size); bitmap layers are rendered at the resolution setting."""
    from . import settings as ST

    d = D.load(project)
    ctx = D.context(project, d)
    check = D.validate(d, ctx)
    if check["errors"]:
        raise SystemExit("design.json has errors:\n  " + "\n  ".join(check["errors"]))
    abs_ = [ab for ab in d["artboards"] if not artboards or ab["id"] in artboards]
    if not abs_:
        raise SystemExit(f"no artboard matched {artboards}")
    stage = stage or (Path.home() / "Desktop" / "designassist-affinity" / project.name)
    stage.mkdir(parents=True, exist_ok=True)
    docs, notes, fonts, fallback = [], [], {}, []
    layers: dict = {}  # "<artboard>/<layer>" -> where it lives in Affinity (for pull); layer ids repeat across artboards

    def record(ab: dict, ox: float, oy: float, k: float = 1.0) -> None:
        ppu = D.px_per_unit(ab) * k
        for l, gx, gy in D.walk(ab.get("layers", [])):
            layers[f"{ab['id']}/{l['id']}"] = {"artboard": ab["id"], "type": l["type"], "ppu": ppu, "origin": [ox, oy],
                               "text": l.get("text"), "rotated": bool(l.get("rotation"))}

    def background(cv: Converter, ab: dict, bleed_u: float) -> None:
        bg = ab.get("background")
        if bg in (None, "none"):
            return
        b = bleed_u * cv.ppu
        box = (cv.ox - b, cv.oy - b, float(ab["width"]) * cv.ppu + 2 * b, float(ab["height"]) * cv.ppu + 2 * b)
        cv.ops.append({"id": f"{ab['id']}-background", "parent": cv.parent0, "op": "rect", "x": box[0], "y": box[1],
                       "w": box[2], "h": box[3], "radius": None, "fill": cv.fill(bg, box), "stroke": None})

    px = [ab for ab in abs_ if ab.get("unit", "px") == "px"]
    if px:
        # the document stays at artboard size (vector) unless asked; its bitmaps go in at the resolution setting
        k = float(doc_scale) if doc_scale is not None else 1.0
        px_scale = max(px_scale, max(ST.scale_for(ab, ctx) for ab in px))
        x = 0.0
        spec_abs, ops = [], []
        for ab in px:
            spec_abs.append({"id": ab["id"], "x": x, "y": 0.0, "w": float(ab["width"]) * k, "h": float(ab["height"]) * k})
            cv = Converter(ctx, ab, x, 0.0, stage, px_scale, k)
            cv.parent0 = ab["id"]
            record(ab, x, 0.0, k)
            background(cv, ab, 0)
            cv.layers(ab.get("layers", []), parent=ab["id"])
            for o in cv.ops:
                o["ab"] = ab["id"]  # the runtime keys its text records "<artboard>/<id>"
            ops += cv.ops
            notes += [f"{ab['id']}: {n}" for n in cv.notes]
            fonts.update(cv.fonts)
            fallback += cv.fallback
            x += (float(ab["width"]) + GAP) * k
        name = project.name if len(px) > 1 or len(abs_) == 1 else f"{project.name}-{px[0]['id']}"
        docs.append({"name": name, "units": "px", "dpi": 72, "doc_w": spec_abs[0]["w"], "doc_h": spec_abs[0]["h"],
                     "bleed": 0, "artboards": spec_abs, "ab_ids": [a["id"] for a in px], "ops": ops,
                     "save": (stage / f"{name}.af").as_posix()})
    for ab in abs_:
        if ab.get("unit", "px") == "px":
            continue
        cv = Converter(ctx, ab, 0.0, 0.0, stage, px_scale)
        cv.parent0 = None
        record(ab, 0.0, 0.0)
        bleed = float(ab.get("bleed", 0))
        background(cv, ab, bleed)
        cv.layers(ab.get("layers", []), parent=None)
        notes += [f"{ab['id']}: {n}" for n in cv.notes]
        fonts.update(cv.fonts)
        fallback += cv.fallback
        name = f"{project.name}-{ab['id']}"
        docs.append({"name": name, "units": ab["unit"], "dpi": float(ab.get("dpi", 300)), "doc_w": float(ab["width"]),
                     "doc_h": float(ab["height"]), "bleed": bleed, "artboards": None, "ab_ids": [ab["id"]], "ops": cv.ops,
                     "save": (stage / f"{name}.af").as_posix()})
    return {"spec": {"docs": docs, "fonts": sorted(fonts), "font_requests": fonts}, "notes": notes, "fallback_fonts": sorted(set(fallback)),
            "stage": str(stage), "layers": layers}


def script(spec: dict) -> str:
    return ("const DA = " + json.dumps(spec, ensure_ascii=False) + ";\n" + READER.read_text(encoding="utf-8") + "\n"
            + RUNTIME.read_text(encoding="utf-8"))


def build(project: Project, artboards: list[str] | None = None, live: bool = True, save: bool = True) -> dict:
    from . import affinity as A

    p = plan(project, artboards)
    spec = p["spec"]
    if not save:
        for doc in spec["docs"]:
            doc["save"] = None
    out_dir = project.path("output", "affinity")
    out_dir.mkdir(parents=True, exist_ok=True)
    js = script(spec)
    (out_dir / f"{project.name}-affinity.js").write_text(js, encoding="utf-8")
    res: dict = {"script": project.rel(out_dir / f"{project.name}-affinity.js"), "documents": [d["name"] for d in spec["docs"]],
                 "notes": p["notes"]}
    if p["fallback_fonts"]:
        res["notes"].append(f"fonts not found, preview used Montserrat: {', '.join(p['fallback_fonts'])}")
    if not live:
        res["next"] = "run it with `da affinity open` (connector on), or paste it into Affinity's Scripts panel"
        return res
    c = A.session(300)
    try:
        out = c.run_json(js, 300)
        rendered = []
        specs = {d["name"]: d for d in spec["docs"]}
        for doc in out.get("docs", []):
            abs_ = (specs.get(doc["name"]) or {}).get("artboards")
            try:
                if abs_ and len(abs_) > 1:  # one image per artboard: a spread render is capped at 1024 px
                    stage = Path(p["stage"]) / "renders"
                    for ab in abs_:
                        tmp = c.export(doc["uuid"], stage / f"{ab['id']}.png", "PNG", ab["id"])
                        f = project.path("work", "affinity", f"{ab['id']}.png")
                        f.parent.mkdir(parents=True, exist_ok=True)
                        shutil.move(str(tmp), f)
                        rendered.append(project.rel(f))
                else:
                    f = project.path("work", "affinity", f"{doc['name']}.jpg")
                    c.render(f, 0, doc["uuid"])
                    rendered.append(project.rel(f))
            except A.AffinityError as e:
                res["notes"].append(f"render {doc['name']}: {e}")
    finally:
        c.close()
    files = []
    for doc in out.get("docs", []):
        if doc.get("saved") and Path(doc["saved"]).exists():
            dst = out_dir / Path(doc["saved"]).name
            shutil.copy2(doc["saved"], dst)
            files.append(project.rel(dst))
    # line-count check: Affinity wraps text itself; a different ink height means different breaks
    mism = []
    ops = {(f"{o['ab']}/" if o.get("ab") else "") + o["id"]: o for d in spec["docs"] for o in d["ops"] if o["op"] == "text"}
    for doc in out.get("docs", []):
        for tid, t in (doc.get("texts") or {}).items():
            o = ops.get(tid)
            if not o or o["lines"] < 1:
                continue
            want = o["ink"][3] - o["ink"][1]
            got = t["ink"][3] - t["ink"][1]
            if abs(got - want) > 0.5 * o["leading"]:
                mism.append(f"{tid}: Affinity broke the lines differently (ink height {got:.0f}px vs {want:.0f}px)")
    ab_ids = {d["name"]: d["ab_ids"] for d in spec["docs"]}
    write_json(out_dir / f"{project.name}-affinity-built.json", {
        "docs": [{"name": d["name"], "uuid": d["uuid"], "saved": d.get("saved"), "artboards": ab_ids.get(d["name"], []),
                  "snapshot": scoped(d.get("snapshot", {}), ab_ids.get(d["name"], []))}
                 for d in out.get("docs", [])],
        "layers": p["layers"]})
    res.update({"open_in_affinity": [d["name"] for d in out.get("docs", [])], "uuids": [d["uuid"] for d in out.get("docs", [])],
                "saved": files,
                "live_file": [d.get("saved") for d in out.get("docs", [])], "renders": rendered,
                "nodes": out.get("nodes"), "missing_fonts": out.get("missing_fonts", []),
                "warnings": out.get("warnings", []) + mism})
    if out.get("missing_fonts"):
        res["warnings"].append("Affinity doesn't have these fonts (it substituted them): "
                               + ", ".join(out["missing_fonts"]) + " — `da fonts install` and restart Affinity")
    return res


def read_docs(uuids: list[str] | None = None) -> dict:
    from . import affinity as A

    c = A.session(120)
    try:
        return c.run_json("const DA_READ = " + json.dumps({"uuids": uuids or []}) + ";\n" + READER.read_text(encoding="utf-8"))
    finally:
        c.close()


def scoped(snap: dict, ab_ids: list[str]) -> dict:
    """Snapshot keys as "<artboard>/<layer>". The reader scopes layers inside artboards itself; a print document
    has no artboard node, so its bare names belong to its one artboard."""
    if len(ab_ids) != 1:
        return snap
    a = ab_ids[0]
    return {k if "/" in k or k == a else f"{a}/{k}": v for k, v in snap.items()}


def read_current() -> dict:
    return read_docs(None)


def remark(old: str, new: str) -> tuple[str, list[str]]:
    """Affinity text has no ** markup: wrap the old accent phrases again where they still appear.
    Returns the new text and the accent phrases that are gone."""
    lost = []
    for phrase, is_acc in T.parse_markup(old):
        if not is_acc:
            continue
        if phrase in new and f"**{phrase}**" not in new:
            new = new.replace(phrase, f"**{phrase}**", 1)
        elif phrase not in new:
            lost.append(phrase)
    return new, lost


def _token_or_hex(rgba, ctx) -> str:
    """A colour read from Affinity as the design token it matches (within 2/255), else hex."""
    for name, v in ctx.colors.items():
        try:
            c = ctx.color("$" + name)
        except Exception:
            continue
        if c is not None and max(abs(a - b) for a, b in zip(rgba[:3], (c.r, c.g, c.b))) <= 2:
            return "$" + name
    return "#{:02X}{:02X}{:02X}".format(*[int(round(v)) for v in rgba[:3]])


def _copied_layers(d: dict, meta: dict, before: dict, after: dict, abs_of: dict, dry_run: bool) -> list:
    """Layers the user copied onto another artboard in Affinity (they keep their name, e.g. the logo
    pasted on the cover): added to that artboard as a copy of the design layer, at the new place/size."""
    import copy

    out = []
    by_id = {}
    for ab in d["artboards"]:
        for l in ab.get("layers", []):
            by_id.setdefault(l["id"], (ab, l))
    ab_ids = {ab["id"]: ab for ab in d["artboards"]}
    for key, rec in after.items():
        if key in before or "/" not in key:
            continue
        ab_id, lid = key.split("/", 1)
        ab = ab_ids.get(ab_id)
        if ab is None or lid not in by_id or any(l["id"] == lid for l in ab.get("layers", [])):
            continue
        src_ab, src = by_id[lid]
        src_key = f"{src_ab['id']}/{lid}"
        if src_key not in before or src_key not in meta or ab_id not in after or src_ab["id"] not in before:
            continue
        ppu = meta[src_key]["ppu"]
        sb, nb = before[src_key]["box"], rec["box"]
        sab, nab = before[src_ab["id"]]["box"], after[ab_id]["box"]
        k = nb[2] / sb[2] if sb[2] else 1.0
        new = copy.deepcopy(src)
        unit, dpi = ab.get("unit", "px"), ab.get("dpi", 72)
        for kk in ("w", "h"):
            if new.get(kk) is not None:
                new[kk] = round(D.length(new[kk], unit, dpi) * k, 3)
        # the ink box moved by (new - source) relative to each artboard; scale about the box's top-left
        new["x"] = round(D.length(src.get("x", 0), unit, dpi) + ((nb[0] - nab[0]) - (sb[0] - sab[0])) / ppu, 3)
        new["y"] = round(D.length(src.get("y", 0), unit, dpi) + ((nb[1] - nab[1]) - (sb[1] - sab[1])) / ppu, 3)
        if not dry_run:
            ab.setdefault("layers", []).append(new)
        out.append({"layer": key, "added": f"copy of {src_key}", "at": [new["x"], new["y"]]})
    return out


def pull(project: Project, dry_run: bool = False) -> dict:
    """Bring manual edits made in Affinity back into design.json: moves and resizes of layers named
    with design ids, text content, solid fill colours. Compares the live document with the snapshot
    taken right after `da affinity open` built it."""
    from .project import read_json

    built = read_json(project.path("output", "affinity", f"{project.name}-affinity-built.json"))
    if not built:
        raise SystemExit("no Affinity build recorded for this project: run `da affinity open` first")
    live = read_docs([d["uuid"] for d in built["docs"]])
    if not live["docs"]:
        raise SystemExit("the documents built for this project aren't open in Affinity any more "
                         f"(open {', '.join(str(d.get('saved')) for d in built['docs'])} and retry)")
    meta = built["layers"]
    if meta and not any("/" in k for k in meta):
        raise SystemExit("this Affinity build predates artboard-scoped layer names (layer ids repeat across artboards, "
                         "so edits could land on the wrong artboard): rebuild with `da affinity open`, redo the edits")
    abs_of = {d["uuid"]: d.get("artboards") or [] for d in built["docs"]}
    before, after = {}, {}
    for d in built["docs"]:
        before.update(scoped(d.get("snapshot") or {}, abs_of[d["uuid"]]))
    for d in live["docs"]:
        after.update(scoped(d["layers"], abs_of.get(d["uuid"], [])))
    d = D.load(project)
    ctx = D.context(project, d)
    changes, skipped = [], []

    def center_delta(i):
        b, a = before[i]["box"], after[i]["box"]
        return (a[0] + a[2] / 2) - (b[0] + b[2] / 2), (a[1] + a[3] / 2) - (b[1] + b[3] / 2)

    # moves of a group carry its children: subtract the parent's move
    parent_of = {}
    for ab in d["artboards"]:
        for l, _, _ in D.walk(ab.get("layers", [])):
            if l.get("type") == "group":
                for c in l.get("layers", []):
                    parent_of[f"{ab['id']}/{c['id']}"] = f"{ab['id']}/{l['id']}"
    for ab in d["artboards"]:
        for l, _, _ in D.walk(ab.get("layers", [])):
            i = f"{ab['id']}/{l['id']}"
            if i not in meta or i not in before:
                continue
            if i not in after:
                skipped.append(f"{i}: not found in Affinity (renamed or deleted there); left as is")
                continue
            m = meta[i]
            ppu = m["ppu"]
            dx, dy = center_delta(i)
            p = parent_of.get(i)
            if p and p in before and p in after:
                pdx, pdy = center_delta(p)
                dx, dy = dx - pdx, dy - pdy
            b, a = before[i]["box"], after[i]["box"]
            dw, dh = a[2] - b[2], a[3] - b[3]
            entry = {"layer": i}
            if l["type"] == "text":
                if after[i].get("text") is not None and before[i].get("text") is not None and after[i]["text"] != before[i]["text"]:
                    new = after[i]["text"].replace("\r", "\n").replace("\u2029", "\n").rstrip("\n")
                    new, lost = remark(l.get("text") or "", new)
                    entry["text"] = [l.get("text"), new]
                    if lost:
                        entry["note"] = f"accent words no longer in the text: {', '.join(lost)} (re-mark with **)"
                    l["text"] = new
                if abs(dw) > 0.5 and l.get("w"):
                    l["w"] = round(float(D.length(l["w"], ab.get("unit", "px"), ab.get("dpi", 72))) + dw / ppu, 3)
                    entry["w"] = l["w"]
            elif not m["rotated"] and l["type"] != "group" and (abs(dw) > 0.5 or abs(dh) > 0.5) and l.get("w") and l.get("h"):
                unit, dpi = ab.get("unit", "px"), ab.get("dpi", 72)
                l["w"] = round(D.length(l["w"], unit, dpi) + dw / ppu, 3)
                l["h"] = round(D.length(l["h"], unit, dpi) + dh / ppu, 3)
                entry["size"] = [l["w"], l["h"]]
            if l["type"] == "line" and (abs(dx) > 0.5 or abs(dy) > 0.5):
                for kx, ky in (("x", "y"), ("x2", "y2")):
                    l[kx] = round(float(l.get(kx, 0)) + dx / ppu, 3)
                    l[ky] = round(float(l.get(ky, 0)) + dy / ppu, 3)
                entry["moved"] = [round(dx / ppu, 3), round(dy / ppu, 3)]
            elif abs(dx) > 0.5 or abs(dy) > 0.5 or "size" in entry:
                # keep the centre where Affinity has it
                unit, dpi = ab.get("unit", "px"), ab.get("dpi", 72)
                ddx = dx - (dw / 2 if "size" in entry else 0)
                ddy = dy - (dh / 2 if "size" in entry else 0)
                l["x"] = round(D.length(l.get("x", 0), unit, dpi) + ddx / ppu, 3)
                l["y"] = round(D.length(l.get("y", 0), unit, dpi) + ddy / ppu, 3)
                entry["moved"] = [round(ddx / ppu, 3), round(ddy / ppu, 3)]
            fb, fa = before[i].get("fill"), after[i].get("fill")
            if fa and fb and [round(v, 3) for v in fa] != [round(v, 3) for v in fb] and l["type"] in ("rect", "ellipse", "path", "svg"):
                hexv = "#{:02X}{:02X}{:02X}".format(*fa[:3]) + ("" if fa[3] >= 0.999 else "{:02X}".format(round(fa[3] * 255)))
                key = "color" if l["type"] == "svg" else "fill"
                entry["fill"] = [l.get(key), hexv]
                l[key] = hexv
            if l["type"] == "text" and after[i].get("text_fill"):
                # against the design's own colour, so builds whose snapshot predates text colours still count
                want = ctx.color(l.get("color", "$ink"))
                got = after[i]["text_fill"]
                if want is not None and max(abs(a_ - b_) for a_, b_ in zip(got[:3], (want.r, want.g, want.b))) > 2:
                    entry["color"] = [l.get("color"), _token_or_hex(got, ctx)]
                    l["color"] = entry["color"][1]
            if len(entry) > 1:
                changes.append(entry)
    changes += _copied_layers(d, meta, before, after, abs_of, dry_run)
    if changes and not dry_run:
        from . import design as Dm

        Dm.save(project, d)
        # the live state is the new baseline, so pulling twice doesn't apply a move twice
        snap = {x["uuid"]: x["layers"] for x in live["docs"]}
        for doc in built["docs"]:
            if doc["uuid"] in snap:
                doc["snapshot"] = scoped(snap[doc["uuid"]], abs_of[doc["uuid"]])
        write_json(project.path("output", "affinity", f"{project.name}-affinity-built.json"), built)
    return {"changes": changes, "skipped": skipped, "saved": bool(changes) and not dry_run,
            "next": "da render <p> and look; if the change should stick for this client or in general, save the preference"}


PRESETS = {"png": "PNG", "jpg": "JPEG (Best quality)", "pdf": "PDF (digital - high quality)", "print": "PDF (press ready)",
           "pdfx4": "PDF/X-4", "psd": "PSD (preserve editability)", "svg": "SVG (for export)", "canva": "Canva Design",
           "webp": "WebP (High Quality)", "tiff-cmyk": "TIFF CMYK"}
EXT = {"PNG": ".png", "JPEG": ".jpg", "PDF": ".pdf", "PSD": ".psd", "SVG": ".svg", "Canva": ".canva", "WebP": ".webp",
       "TIFF": ".tiff"}


def export(project: Project, preset: str, artboards: list[str] | None = None) -> dict:
    """Affinity's own exporter on the documents `da affinity open` built (they must be open)."""
    from . import affinity as A
    from .project import read_json

    name = PRESETS.get(preset, preset)
    ext = next((e for k, e in EXT.items() if name.startswith(k)), ".bin")
    built = read_json(project.path("output", "affinity", f"{project.name}-affinity-built.json"))
    if not built:
        raise SystemExit("run `da affinity open <p>` first: Affinity exports the documents it has open")
    # artboard ids come from design.json: builds before 2026-10-19 keyed built["layers"] by bare layer id, which
    # repeat across artboards (every thumb has a "guest"), so it only remembered the last artboard of each id
    abs_by_doc = {ab["id"] for ab in D.load(project).get("artboards", [])}
    stage = Path.home() / "Desktop" / "designassist-affinity" / project.name / "export"
    out_dir = project.path("output", "affinity", "export")
    out_dir.mkdir(parents=True, exist_ok=True)
    files = []
    c = A.session(300)
    try:
        open_now = {d["uuid"] for d in read_docs([d["uuid"] for d in built["docs"]])["docs"]}
        for doc in built["docs"]:
            if doc["uuid"] not in open_now:
                raise SystemExit(f"{doc['name']} isn't open in Affinity any more (open {doc.get('saved')} and retry)")
            ids = [i for i in (doc.get("snapshot") or {}) if i in abs_by_doc]
            per_ab = [i for i in ids if not artboards or i in artboards]
            if len(ids) > 1 and per_ab:
                targets = [(i, f"{i}{ext}") for i in per_ab]
            else:
                targets = [(None, f"{doc['name']}{ext}")]
            for ab_id, fname in targets:
                tmp = c.export(doc["uuid"], stage / fname, name, ab_id)
                dst = out_dir / fname
                shutil.move(str(tmp), dst)
                files.append(project.rel(dst))
    finally:
        c.close()
    return {"preset": name, "files": files}
