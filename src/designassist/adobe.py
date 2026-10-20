"""Photoshop and Illustrator: build an editable document from design.json, run it in the open
app, read the open document back, and pull the designer's changes into design.json.

The builders are ExtendScript (`jsx/`): adobe.py precomputes everything (coordinates in the
app's units, text layout from our engine, per-layer bitmaps/SVGs) and writes one self-contained
.jsx = common.jsx + `var DA = {...}` + the app runtime. Run it with `da adobe open`, or by hand
(Illustrator: File > Scripts > Other Script; Photoshop: File > Scripts > Browse).

Illustrator: one document, one artboard + layer per design artboard, swatches from the tokens,
text as live area/point text (first baseline pinned to ours), rects/ellipses/lines as native
paths, images placed and embedded, everything else (gradients, paths, svg logos, icons, shadows)
imported from a per-layer SVG. Photoshop: one document per artboard, text layers native, every
other layer a placed smart object of its own trimmed PNG. Items are named with the design layer
id, which is how `da adobe pull` maps changes back.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from . import design as D
from .project import Project

JSX = Path(__file__).parent / "jsx"
APPS = {
    "illustrator": {"bundle": "com.adobe.illustrator", "com": "Illustrator.Application", "glob": "Adobe Illustrator*",
                    "exe": "Illustrator.exe", "proc": "Adobe Illustrator"},
    "photoshop": {"bundle": "com.adobe.Photoshop", "com": "Photoshop.Application", "glob": "Adobe Photoshop*",
                  "exe": "Photoshop.exe", "proc": "Adobe Photoshop"},
}
PT_PER_UNIT = {"px": 1.0, "pt": 1.0, "in": 72.0, "mm": 72 / 25.4, "cm": 72 / 2.54}
AB_GAP_PT = 72.0


class AdobeError(RuntimeError):
    pass


def pt_per_unit(ab: dict) -> float:
    """Illustrator points per artboard unit (Illustrator treats 1 px as 1 pt)."""
    return PT_PER_UNIT[ab.get("unit", "px")]


def _posix(p: Path) -> str:
    return Path(p).resolve().as_posix()


def _color(ctx, c) -> dict | None:
    """Color -> {rgb, cmyk, spot, alpha} for the runtimes."""
    from . import colors as C

    if c is None:
        return None
    spot = None
    if c.name:
        raw = ctx.colors.get(c.name)
        if isinstance(raw, dict) and raw.get("pantone"):
            spot = f"PANTONE {raw['pantone']}" if not str(raw["pantone"]).upper().startswith("PANTONE") else raw["pantone"]
    return {"rgb": [c.r, c.g, c.b], "cmyk": [round(v, 2) for v in C.to_cmyk(c)], "spot": spot, "alpha": round(c.a, 4)}


def _is_solid(v) -> bool:
    return v is None or isinstance(v, str) or (isinstance(v, dict) and "stops" not in v)


def _abs_layer(l: dict, ox: float, oy: float) -> dict:
    """Copy of a layer with its position made absolute (for rendering it alone)."""
    out = dict(l)
    out["x"] = float(l.get("x", 0) or 0) + ox
    out["y"] = float(l.get("y", 0) or 0) + oy
    if l.get("type") == "line":
        out["x2"] = float(l.get("x2", 0) or 0) + ox
        out["y2"] = float(l.get("y2", 0) or 0) + oy
    return out


def _solo(ab: dict, layer_abs: dict) -> dict:
    return {**ab, "layers": [layer_abs], "background": None}


def _plain_text(l: dict) -> tuple[str, list[tuple[int, int]]]:
    """Contents without markup (case applied, "\\n" -> "\\r") and the accent ranges in it."""
    from . import text as T

    s, ranges = "", []
    for piece, acc in T.parse_markup(T.apply_case(l.get("text", ""), l.get("case"))):
        if acc:
            ranges.append((len(s), len(piece)))
        s += piece
    return s.replace("\n", "\r"), ranges


def _styles(ctx, l: dict, lay) -> tuple[dict, dict]:
    """Base and accent character styles of a laid-out text layer (same rules as text.layout)."""
    from . import fonts as F

    spec = ctx.font_spec(l)
    accent = l.get("accent") or {}
    acc_spec = ctx.font_spec({"font": accent.get("font", l.get("font", "$body")),
                              "weight": accent.get("weight", spec["weight"]), "italic": accent.get("italic", spec["italic"])})
    dirs = ctx.font_dirs()
    color = ctx.color(l.get("color", l.get("fill", "$ink")))
    acc_color = ctx.color(accent["color"]) if "color" in accent else (ctx.color("$accent") if "accent" in ctx.colors else color)
    base = {"ref": F.resolve_or_fallback(spec["family"], float(spec["weight"]), bool(spec["italic"]), dirs),
            "size": lay.size, "tracking": float(l.get("tracking", 0)), "color": color, "stroke": l.get("stroke")}
    acc = {"ref": F.resolve_or_fallback(acc_spec["family"], float(acc_spec["weight"]), bool(acc_spec["italic"]), dirs),
           "size": lay.size * float(accent.get("scale", 1)), "tracking": float(accent.get("tracking", l.get("tracking", 0))),
           "color": acc_color, "stroke": accent.get("stroke", l.get("stroke"))}
    return base, acc


def _highlight_rects(b, l: dict, lay) -> list[dict]:
    """Highlight boxes (layer highlight + accent highlight) as rect geometry + colour value."""
    from . import text as T

    out = []
    all_runs, hl_runs = T.highlight_runs(lay)
    for ln in lay.lines:
        if l.get("highlight") and ln.runs:
            out.append((l["highlight"], b._highlight(l["highlight"], ln.x, ln.baseline, ln.width, lay.size,
                                                     ln.runs[0].style.ref, all_runs)))
        for r in ln.runs:
            if r.style.highlight:
                out.append((r.style.highlight, b._highlight(r.style.highlight, r.x, ln.baseline, r.width,
                                                            r.style.size, r.style.ref, hl_runs)))
    rects = []
    for hl, s in out:
        g = dict(re.findall(r'(x|y|width|height|rx)="([-\d.]+)"', s))
        rects.append({"x": float(g["x"]), "y": float(g["y"]), "w": float(g["width"]), "h": float(g["height"]),
                      "r": float(g.get("rx", 0)), "color": hl.get("color", "$primary")})
    return rects


# --- Illustrator ------------------------------------------------------------------------------

class _AI:
    def __init__(self, pr: Project, ctx, out_dir: Path):
        self.pr, self.ctx, self.out = pr, ctx, out_dir
        self.assets = out_dir / "assets"
        self.notes: list[str] = []
        self.fonts: set = set()
        self.n_assets = 0

    def board(self, ab: dict, left: float) -> dict:
        from . import svg as S

        self.ab, self.k, self.left = ab, pt_per_unit(ab), left
        self.unit, self.dpi = ab.get("unit", "px"), float(ab.get("dpi", 72))
        self.b = S.Builder(self.ctx, ab, "outlined")
        W, H = float(ab["width"]) * self.k, float(ab["height"]) * self.k
        items = []
        bg = ab.get("background")
        if bg not in (None, "none"):
            bleed = self.L(ab.get("bleed", 0))
            bgl = {"id": "background", "type": "rect", "x": -bleed, "y": -bleed, "w": float(ab["width"]) + 2 * bleed,
                   "h": float(ab["height"]) + 2 * bleed, "fill": bg, "role": "background"}
            items += self.layer(bgl, 0.0, 0.0)
        for l in ab.get("layers", []):
            items += self.layer(l, 0.0, 0.0)
        return {"id": ab["id"], "rect": [left, 0.0, left + W, -H], "items": items}

    def L(self, v) -> float:
        return D.length(v, self.unit, self.dpi) if v is not None else 0.0

    def X(self, u: float) -> float:
        return round(self.left + u * self.k, 4)

    def Y(self, u: float) -> float:
        return round(-u * self.k, 4)

    def common(self, l: dict) -> dict:
        d = {"name": l.get("id", ""), "opacity": l.get("opacity"), "blend": l.get("blend"),
             "rotation": l.get("rotation") or 0}
        if l.get("shadow"):
            s = l["shadow"]
            c = self.ctx.color(s.get("color", "#00000040"))
            d["shadow"] = {"x": round(self.L(s.get("x", 0)) * self.k, 3), "y": round(self.L(s.get("y", 4)) * self.k, 3),
                           "blur": round(self.L(s.get("blur", 12)) * self.k, 3), "opacity": round(c.a if c else 0.25, 3)}
            if c is not None and (c.r, c.g, c.b) != (0, 0, 0):
                self.notes.append(f"{l.get('id')}: coloured shadow drawn black (Illustrator script limit); recolour it in Appearance")
        return d

    def stroke(self, s: dict | None) -> dict | None:
        if not s:
            return None
        c = self.ctx.color(s.get("color", "$ink"))
        return {"color": _color(self.ctx, c), "width": round(self.L(s.get("width", 1)) * self.k, 4),
                "dash": [round(self.L(x) * self.k, 3) for x in s["dash"]] if s.get("dash") else None}

    def layer(self, l: dict, ox: float, oy: float) -> list[dict]:
        if l.get("hidden"):
            return []
        t = l["type"]
        x, y = ox + self.L(l.get("x")), oy + self.L(l.get("y"))
        w, h = self.L(l.get("w")), self.L(l.get("h"))
        com = self.common(l)
        if t == "text":
            return self.text(l, ox, oy, com)
        if t == "group":
            items = []
            for c in l.get("layers", []):
                items += self.layer(c, x, y)
            g = {"kind": "group", "items": items, **com}
            if l.get("clip") and w and h:
                g["clip"] = {"left": self.X(x), "top": self.Y(y), "w": w * self.k, "h": h * self.k}
            return [g]
        if t in ("rect", "ellipse") and _is_solid(l.get("fill", "$ink")) and not isinstance(l.get("radius"), list):
            fill = self.ctx.color(l.get("fill", "$ink"))
            d = {"kind": t, "left": self.X(x), "top": self.Y(y), "w": round(w * self.k, 4), "h": round(h * self.k, 4),
                 "fill": _color(self.ctx, fill), "stroke": self.stroke(l.get("stroke")), **com}
            if fill is not None and fill.a < 1:  # Illustrator colours carry no alpha
                d["opacity"] = (com["opacity"] if com["opacity"] is not None else 1) * fill.a
            if t == "rect" and l.get("radius"):
                d["radius"] = round(min(self.L(l["radius"]), w / 2, h / 2) * self.k, 4)
            return [d]
        if t == "line":
            x2, y2 = ox + self.L(l.get("x2")), oy + self.L(l.get("y2"))
            return [{"kind": "line", "points": [[self.X(x), self.Y(y)], [self.X(x2), self.Y(y2)]], "fill": None,
                     "stroke": self.stroke(l.get("stroke") or {"color": "$ink", "width": 1}), **com, "rotation": 0}]
        if t == "image" and not str(l.get("src", "")).lower().endswith(".svg"):
            return [self.image(l, x, y, w, h, com)]
        return [self.svg_item(l, ox, oy)]

    def image(self, l, x, y, w, h, com) -> dict:
        from . import images as I
        from .design import px_per_unit

        src = self.ctx.src(l["src"])
        scale = 2.0 if self.unit == "px" else 1.0  # crisp at 144 ppi for screen designs; print at its dpi
        ppu = px_per_unit(self.ab) * scale
        r = l.get("radius", 0)
        rpx = [self.L(v) * ppu for v in r] if isinstance(r, list) else self.L(r) * ppu
        prep = I.prepare(l, src, w * ppu, h * ppu, self.pr.path("work", "cache"), self.ctx, rpx)
        self.assets.mkdir(parents=True, exist_ok=True)
        dst = self.assets / f"{self.ab['id']}-{l.get('id')}{prep.path.suffix}"
        shutil.copy2(prep.path, dst)
        self.n_assets += 1
        return {"kind": "image", "file": _posix(dst), "left": self.X(x), "top": self.Y(y), "w": round(w * self.k, 4),
                "h": round(h * self.k, 4), "embed": True, **com}

    def svg_item(self, l: dict, ox: float, oy: float) -> dict:
        from . import svg as S

        la = _abs_layer(l, ox, oy)
        la.pop("shadow", None)  # Illustrator drops SVG filters; the shadow is applied as a live effect instead
        svg, rep = S.artboard_svg(self.ctx, _solo(self.ab, la), "outlined", 1.0, bleed=True, background=False)
        bleed = self.L(self.ab.get("bleed", 0))
        W, H = float(self.ab["width"]) + 2 * bleed, float(self.ab["height"]) + 2 * bleed
        # size the canvas in points, and add an unpainted frame so the imported group's bounds = the canvas
        svg = re.sub(r'(<svg[^>]*?) width="[^"]*" height="[^"]*"', rf'\1 width="{W * self.k:.4f}" height="{H * self.k:.4f}"', svg, count=1)
        frame = f'<rect id="daframe" x="{-bleed}" y="{-bleed}" width="{W}" height="{H}" fill="none" stroke="none"/>'
        svg = re.sub(r"(<svg[^>]*>)", r"\1" + frame.replace("\\", "\\\\"), svg, count=1)
        self.assets.mkdir(parents=True, exist_ok=True)
        dst = self.assets / f"{self.ab['id']}-{l.get('id')}.svg"
        dst.write_text(svg, encoding="utf-8")
        self.n_assets += 1
        # opacity and rotation are in the svg; blend modes don't survive SVG import, shadows are a live effect
        return {"kind": "svg", "file": _posix(dst), "left": self.X(-bleed), "top": self.Y(-bleed), "name": l.get("id", ""),
                "blend": l.get("blend"), "shadow": self.common(l).get("shadow")}

    def style(self, st: dict) -> dict:
        return {"font": st["ref"].postscript, "size": round(st["size"] * self.k, 4), "tracking": st["tracking"],
                "color": _color(self.ctx, st["color"]), "stroke": self.stroke(st["stroke"])}

    def text(self, l: dict, ox: float, oy: float, com: dict) -> list[dict]:
        from . import text as T

        lay = T.layout(l, self.ctx, self.unit, self.dpi, ox, oy)
        self.fonts.update(lay.fonts)
        items = []
        for i, r in enumerate(_highlight_rects(self.b, l, lay)):
            c = self.ctx.color(r["color"])
            items.append({"kind": "rect", "name": f"{l.get('id')}-highlight-{i + 1}", "left": self.X(r["x"]),
                          "top": self.Y(r["y"]), "w": r["w"] * self.k, "h": r["h"] * self.k,
                          "radius": r["r"] * self.k, "fill": _color(self.ctx, c), "stroke": None, "opacity": None,
                          "blend": None, "rotation": 0})
        contents, ranges = _plain_text(l)
        base, acc = (self.style(st) for st in _styles(self.ctx, l, lay))
        x, y, bw, bh = lay.box
        leading = lay.size * float(l.get("line_height", 1.2)) * self.k
        d = {"kind": "text", "contents": contents, "base": base, "leading": round(leading, 4),
             "align": l.get("align", "left"), "lines": len(lay.lines),
             "ranges": [{"start": s, "len": n, **acc} for s, n in ranges], **com}
        first = lay.lines[0].baseline if lay.lines else y
        if l.get("w"):
            # small slack so Illustrator's composer never pushes the last line out of the frame
            h_used = max(bh, lay.content_h) + lay.size * 0.35
            d.update(area=True, left=self.X(x), top=self.Y(y), w=round(bw * 1.004 * self.k, 4),
                     h=round(h_used * self.k, 4), first_baseline=round((first - y) * self.k, 4))
        else:
            ax = x + {"center": bw / 2, "right": bw}.get(l.get("align", "left"), 0)
            d.update(area=False, anchor=[self.X(ax), self.Y(first)])
        items.append(d)
        return items


def _illustrator(pr: Project, d: dict, ctx, abs_: list[dict], out_dir: Path) -> tuple[dict, _AI]:
    ai = _AI(pr, ctx, out_dir)
    print_doc = any(ab.get("unit", "px") != "px" for ab in abs_)
    boards, left = [], 0.0
    for i, ab in enumerate(abs_):
        k = pt_per_unit(ab)
        bleed = D.length(ab.get("bleed", 0), ab.get("unit", "px"), float(ab.get("dpi", 72))) * k
        if i:
            left += AB_GAP_PT + bleed  # keep bleeds of neighbouring artboards apart
        boards.append(ai.board(ab, left))
        left += float(ab["width"]) * k + bleed
    swatches = []
    for name in ctx.colors:
        try:
            c = ctx.color("$" + name)
        except Exception:
            continue
        if c is None:
            continue
        cs = _color(ctx, c)
        swatches.append({"name": name, "rgb": cs["rgb"], "cmyk": cs["cmyk"], "spot": cs["spot"]})
    bleed_pt = max((D.length(ab.get("bleed", 0), ab.get("unit", "px"), float(ab.get("dpi", 72))) * pt_per_unit(ab)
                    for ab in abs_), default=0)
    if print_doc and any(ab.get("unit", "px") == "px" for ab in abs_):
        ai.notes.append("document is CMYK because it includes a print artboard; open screen artboards on their own "
                        "(--artboard) for an RGB document")
    data = {"doc": {"name": d.get("name") or pr.name, "mode": "CMYK" if print_doc else "RGB",
                    "bleed": round(bleed_pt, 4) if print_doc else 0,
                    "swatch_group": d.get("brand") or d.get("name") or pr.name, "swatches": swatches},
            "artboards": boards, "save": _posix(out_dir / f"{pr.name}.ai")}
    return data, ai


# --- Photoshop --------------------------------------------------------------------------------

class _PS:
    def __init__(self, pr: Project, ctx, out_dir: Path):
        self.pr, self.ctx, self.out = pr, ctx, out_dir
        self.assets = out_dir / "assets"
        self.notes: list[str] = []
        self.fonts: set = set()
        self.n_assets = 0

    def doc(self, ab: dict) -> dict:
        from .design import px_per_unit

        self.ab = ab
        self.unit, self.dpi = ab.get("unit", "px"), float(ab.get("dpi", 72))
        self.ppu = px_per_unit(ab)
        self.print = self.unit != "px"
        self.bleed = D.length(ab.get("bleed", 0), self.unit, self.dpi) if self.print else 0.0
        W = round((float(ab["width"]) + 2 * self.bleed) * self.ppu)
        H = round((float(ab["height"]) + 2 * self.bleed) * self.ppu)
        bg = ab.get("background")
        background = None
        if isinstance(bg, (str, dict)) and _is_solid(bg) and self.ctx.color(bg) is not None and self.ctx.color(bg).a == 1:
            c = self.ctx.color(bg)
            background = {"solid": [c.r, c.g, c.b]}
        elif bg not in (None, "none"):
            f = self.png({"id": "background", "type": "rect", "x": -self.bleed, "y": -self.bleed,
                          "w": float(ab["width"]) + 2 * self.bleed, "h": float(ab["height"]) + 2 * self.bleed, "fill": bg},
                         0.0, 0.0)
            background = {"file": f["file"]} if f else None
        layers = []
        for l in ab.get("layers", []):
            layers += self.layer(l, 0.0, 0.0)
        dpi = self.dpi if self.print else 72
        return {"id": ab["id"], "w": W, "h": H, "dpi": dpi, "background": background, "layers": layers,
                "save": _posix(self.out / f"{self.pr.name}-{ab['id']}.psd")}

    def P(self, u: float) -> float:
        return round((u + self.bleed) * self.ppu, 3)

    def png(self, l: dict, ox: float, oy: float) -> dict | None:
        from .render import render_artboard

        la = _abs_layer(l, ox, oy)
        im, _ = render_artboard(self.ctx, _solo(self.ab, la), 1.0, bleed=self.print, background=False)
        box = im.getchannel("A").getbbox()
        if not box:
            return None
        self.assets.mkdir(parents=True, exist_ok=True)
        dst = self.assets / f"ps-{self.ab['id']}-{l.get('id')}.png"
        im.crop(box).save(dst)
        self.n_assets += 1
        return {"file": _posix(dst), "left": box[0], "top": box[1], "w": box[2] - box[0], "h": box[3] - box[1]}

    def layer(self, l: dict, ox: float, oy: float) -> list[dict]:
        from . import text as T

        if l.get("hidden"):
            return []
        t = l["type"]
        com = {"name": l.get("id", ""), "opacity": l.get("opacity"), "blend": l.get("blend")}
        if t == "group":
            x, y = ox + D.length(l.get("x"), self.unit, self.dpi), oy + D.length(l.get("y"), self.unit, self.dpi)
            kids = []
            for c in l.get("layers", []):
                kids += self.layer(c, x, y)
            return [{"kind": "group", "layers": kids, **com}]
        if t == "text" and not l.get("rotation") and not l.get("highlight") and not l.get("stroke"):
            lay = T.layout(l, self.ctx, self.unit, self.dpi, ox, oy)
            self.fonts.update(lay.fonts)
            contents, ranges = _plain_text(l)
            if ranges:
                self.notes.append(f"{l.get('id')}: accent colour/weight applies to the whole layer in Photoshop; restyle the accent words")
            if l.get("shadow"):
                self.notes.append(f"{l.get('id')}: text shadow not carried (add a Drop Shadow layer style)")
            if not lay.lines:
                return []
            base, _ = _styles(self.ctx, l, lay)
            f = T.font(base["ref"])
            asc = f.asc / f.upem * lay.size
            x, y, bw, bh = lay.box
            first = lay.lines[0].baseline
            c = base["color"]
            d = {"kind": "text", "contents": contents, "font": base["ref"].postscript, "size": round(lay.size * self.ppu, 3),
                 "leading": round(lay.size * float(l.get("line_height", 1.2)) * self.ppu, 3), "tracking": base["tracking"],
                 "color": [c.r, c.g, c.b] if c else [0, 0, 0], "align": l.get("align", "left"), **com}
            if c is not None and c.a < 1:
                d["opacity"] = (com["opacity"] if com["opacity"] is not None else 1) * c.a
            if l.get("w"):
                # Photoshop puts the first baseline about one ascent below the paragraph box top
                top = first - asc
                h = max(bh, lay.content_h) + lay.size * 0.35 + (y - top if top < y else 0)
                d["box"] = [self.P(x), self.P(top), round(bw * 1.004 * self.ppu, 3), round(h * self.ppu, 3)]
            else:
                ax = x + {"center": bw / 2, "right": bw}.get(l.get("align", "left"), 0)
                d["point"] = [self.P(ax), self.P(first)]
            return [d]
        if t == "text":
            self.notes.append(f"{l.get('id')}: rotated/highlighted/stroked text placed as pixels")
        f = self.png({k: v for k, v in l.items() if k not in ("opacity", "blend")}, ox, oy)
        if not f:
            return []
        return [{"kind": "image", "file": f["file"], "left": f["left"], "top": f["top"], **com}]


def _photoshop(pr: Project, d: dict, ctx, abs_: list[dict], out_dir: Path) -> tuple[dict, _PS]:
    ps = _PS(pr, ctx, out_dir)
    return {"docs": [ps.doc(ab) for ab in abs_]}, ps


# --- script writing ---------------------------------------------------------------------------

def compose(app: str, data: dict) -> str:
    runtime = {"illustrator": "illustrator.jsx", "photoshop": "photoshop.jsx"}[app]
    body = (JSX / "common.jsx").read_text(encoding="utf-8") + "\n"
    body += "var DA = " + json.dumps(data, ensure_ascii=True, indent=1) + ";\n"
    body += (JSX / runtime).read_text(encoding="utf-8")
    return f"#target {app}\n" + body


def write_script(project: Project, app: str, artboards: list[str] | None = None) -> dict:
    if app not in APPS:
        raise SystemExit(f"app must be one of {', '.join(APPS)}")
    d = D.load(project)
    ctx = D.context(project, d)
    check = D.validate(d, ctx)
    if check["errors"]:
        raise SystemExit("design.json has errors:\n  " + "\n  ".join(check["errors"]))
    abs_ = [ab for ab in d["artboards"] if not artboards or ab["id"] in artboards]
    if not abs_:
        raise SystemExit(f"no artboard matched {artboards}")
    out_dir = project.path("output", "adobe")
    out_dir.mkdir(parents=True, exist_ok=True)
    data, b = (_illustrator if app == "illustrator" else _photoshop)(project, d, ctx, abs_, out_dir)
    script = out_dir / f"{project.name}-{app}.jsx"
    script.write_text("\ufeff" + compose(app, data), encoding="utf-8")  # BOM: ExtendScript reads it as UTF-8
    missing = sorted({f"{r.family} {r.weight}{' italic' if r.italic else ''} ({r.postscript})"
                      for r in b.fonts if not r.installed or r.fallback})
    notes = list(dict.fromkeys(b.notes))
    if missing:
        notes.append("fonts not installed on this machine: Adobe apps substitute them; `da fonts install <family>`")
    return {"script": project.rel(script), "app": app, "artboards": [ab["id"] for ab in abs_], "assets": b.n_assets,
            "notes": notes, "fonts_missing": missing,
            "saves_to": [project.rel(Path(x)) for x in ([data["save"]] if app == "illustrator" else [x["save"] for x in data["docs"]])]}


# --- running in the app -----------------------------------------------------------------------

def installed(app: str) -> list[str]:
    a = APPS[app]
    if sys.platform == "darwin":
        return sorted(str(p) for p in Path("/Applications").glob(a["glob"]) if p.is_dir())
    if os.name == "nt":
        hits = []
        for base in (os.environ.get("ProgramFiles", "C:/Program Files"), os.environ.get("ProgramFiles(x86)", "")):
            if base:
                hits += [str(p) for p in Path(base, "Adobe").glob(a["glob"]) if p.is_dir()]
        return sorted(hits)
    return []


def running(app: str) -> bool:
    a = APPS[app]
    try:
        if sys.platform == "darwin":
            r = subprocess.run(["osascript", "-e", f'application id "{a["bundle"]}" is running'],
                               capture_output=True, text=True, timeout=10)
            return r.stdout.strip() == "true"
        if os.name == "nt":
            r = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {a['exe']}"], capture_output=True, text=True, timeout=10)
            return a["exe"].lower() in r.stdout.lower()
    except (OSError, subprocess.SubprocessError):
        return False
    return False


def status() -> dict:
    return {app: {"installed": installed(app), "running": running(app)} for app in APPS}


def run_script(app: str, script: Path, timeout: int = 900) -> str:
    """Execute a .jsx in the app (launching it if needed) and return what the script returns."""
    a = APPS[app]
    script = Path(script).resolve()
    if sys.platform == "darwin":
        if not installed(app):
            raise AdobeError(f"{app} is not installed in /Applications")
        cmd = ["osascript", "-e", "on run argv",
               "-e", f"with timeout of {timeout} seconds",
               "-e", f'tell application id "{a["bundle"]}" to do javascript ((POSIX file (item 1 of argv)) as alias)',
               "-e", "end timeout", "-e", "end run", str(script)]
    elif os.name == "nt":
        ps = (f"$a = New-Object -ComObject {a['com']}; "
              f"$r = $a.DoJavaScriptFile('{str(script).replace(chr(39), chr(39) * 2)}'); "
              "[Console]::OutputEncoding = [Text.Encoding]::UTF8; Write-Output $r")
        cmd = ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps]
    else:
        raise AdobeError("Photoshop/Illustrator scripting needs macOS or Windows")
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=timeout + 30)
    except subprocess.TimeoutExpired:
        raise AdobeError(f"{app} did not answer in {timeout}s (a dialog open in the app?)")
    if r.returncode != 0:
        raise AdobeError(r.stderr.strip()[-600:] or f"{app} script failed")
    return r.stdout.strip()


def _parse(out: str):
    try:
        return json.loads(out)
    except ValueError:
        return {"raw": out}


def open_in(project: Project, app: str, artboards: list[str] | None = None) -> dict:
    res = write_script(project, app, artboards)
    out = run_script(app, project.path(res["script"]))
    res["result"] = _parse(out)
    if app == "illustrator" and isinstance(res["result"], dict) and res["result"].get("document"):
        try:  # what was built, so `pull` can tell the designer's moves from our layout
            built_path(project).write_text(json.dumps(read(app), ensure_ascii=False), encoding="utf-8")
        except AdobeError as e:
            res["notes"].append(f"build record not saved: {e}")
    return res


def read(app: str = "illustrator") -> dict:
    if app != "illustrator":
        raise SystemExit("read supports illustrator (Photoshop read-back isn't built yet)")
    import tempfile

    code = "#target illustrator\n" + (JSX / "common.jsx").read_text(encoding="utf-8") + "\n" + \
           (JSX / "illustrator_read.jsx").read_text(encoding="utf-8")
    with tempfile.NamedTemporaryFile("w", suffix=".jsx", delete=False, encoding="utf-8") as fh:
        fh.write("\ufeff" + code)
        tmp = Path(fh.name)
    try:
        return _parse(run_script(app, tmp, timeout=120))
    finally:
        tmp.unlink(missing_ok=True)


# --- pull: Illustrator changes -> design.json ---------------------------------------------------

def _hex_of(cs: dict | None, mode: str) -> str | None:
    if not cs:
        return None
    if "rgb" in cs:
        r, g, b = (round(float(v)) for v in cs["rgb"])
        return f"#{r:02X}{g:02X}{b:02X}"
    if "cmyk" in cs:
        c, m, y, k = (float(v) / 100 for v in cs["cmyk"])
        return "#{:02X}{:02X}{:02X}".format(*(round(255 * (1 - v) * (1 - k)) for v in (c, m, y)))
    if "gray" in cs:
        v = round(255 * (1 - float(cs["gray"]) / 100))
        return f"#{v:02X}{v:02X}{v:02X}"
    return None


def built_path(project: Project) -> Path:
    return project.path("output", "adobe", f"{project.name}-illustrator-built.json")


def _box(it: dict) -> list[float] | None:
    return it.get("area") or it.get("bounds")


def _index(dump: dict) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for it in dump.get("items", []):
        if it.get("name"):
            out.setdefault(it["name"], []).append(it)
    return out


def _pick(by_name: dict, lid: str, board: str) -> tuple[dict | None, str | None]:
    hits = [h for h in by_name.get(lid, []) if h.get("layer") in (board, None)] or by_name.get(lid, [])
    if len(hits) > 1:  # svg imports nest an item named like its group: keep the outermost
        hits = [h for h in hits if h.get("parent") != lid] or hits
    if len(hits) > 1:
        return None, f"{len(hits)} items share that name"
    return (hits[0], None) if hits else (None, None)


def pull(project: Project, dump: dict, tolerance: float = 0.5, dry_run: bool = False, base: dict | None = None) -> dict:
    """Apply a `read` dump to design.json: text contents, positions/sizes, flat fill colours.
    Items are matched by name = design layer id. Geometry is the change against `base` (the read
    taken right after `da adobe open` built the document, output/adobe/<p>-illustrator-built.json),
    which works for every layer type; without it only boxes that equal the item bounds are pulled
    (rects, ellipses, cover images, area text)."""
    from . import colors as C
    from .text import apply_case, parse_markup

    if base is None and built_path(project).exists():
        base = json.loads(built_path(project).read_text(encoding="utf-8"))
    if base is not None and base.get("document") != dump.get("document"):
        base = None
    d = D.load(project)
    ctx = D.context(project, d)
    boards = {b["name"]: b["rect"] for b in dump.get("artboards", [])}
    by_name, base_by = _index(dump), _index(base or {})
    changes, skipped = [], []
    mode = dump.get("mode", "RGB")

    def change(l, where, key, val):
        changes.append({"layer": where, "field": key, "from": l.get(key), "to": val})
        if not dry_run:
            l[key] = val

    for ab in d.get("artboards", []):
        rect = boards.get(ab["id"])
        if rect is None:
            skipped.append(f"{ab['id']}: no Illustrator artboard with that name")
            continue
        k = pt_per_unit(ab)
        left, top = float(rect[0]), float(rect[1])
        for l, ox, oy in D.walk(ab.get("layers", []), include_hidden=True):
            lid, t = l.get("id"), l.get("type")
            where = f"{ab['id']}/{lid}"
            it, why = _pick(by_name, lid, ab["id"])
            if why:
                skipped.append(f"{where}: {why}")
            if it is None:
                continue
            if t == "text" and it.get("type") == "TextFrame" and it.get("contents") is not None:
                new = it["contents"].replace("\r", "\n").replace("\u0003", "\n")
                plain = "".join(p for p, _ in parse_markup(l.get("text", "")))
                if new != apply_case(plain, l.get("case")) and new != plain:
                    change(l, where, "text", new)
                    if not dry_run:
                        l.pop("case", None)
            b1 = _box(it)
            b0 = _box(_pick(base_by, lid, ab["id"])[0] or {}) if base else None
            if b1 and b0:
                sx = (b1[2] - b1[0]) / max(1e-9, b0[2] - b0[0])
                sy = (b1[1] - b1[3]) / max(1e-9, b0[1] - b0[3])
                if l.get("rotation"):
                    sx = sy = 1.0
                # the layer box may be larger than what's drawn (contain fit, text slack): keep the
                # box-to-content offset, scaled with the content
                for key, d1, d0, sv in (("x", (b1[0] - left) / k - ox, (b0[0] - left) / k - ox, sx),
                                        ("y", (top - b1[1]) / k - oy, (top - b0[1]) / k - oy, sy)):
                    cur = l.get(key, 0)
                    if not isinstance(cur, (int, float)):
                        continue
                    val = d1 - (d0 - float(cur)) * sv
                    if abs(val - float(cur)) > tolerance:
                        change(l, where, key, round(val, 2))
                if not l.get("rotation"):
                    for key, sv in (("w", sx), ("h", sy)):
                        if isinstance(l.get(key), (int, float)) and abs(sv - 1) > 0.003:
                            change(l, where, key, round(l[key] * sv, 2))
            elif b1 and not l.get("rotation") and not l.get("stroke") and (
                    t in ("rect", "ellipse") or (t == "image" and l.get("fit", "cover") != "contain")
                    or (t == "text" and it.get("area") and l.get("w"))):
                geo = {"x": (b1[0] - left) / k - ox, "y": (top - b1[1]) / k - oy, "w": (b1[2] - b1[0]) / k}
                if t != "text":
                    geo["h"] = (b1[1] - b1[3]) / k
                for key, val in geo.items():
                    cur = l.get(key, 0)
                    slack = float(cur) * 0.006 if key == "w" and t == "text" else 0  # area text is built 0.4% wider
                    if isinstance(cur, (int, float)) and abs(val - float(cur)) > max(tolerance, slack):
                        change(l, where, key, round(val, 2))
            elif b1 and t not in ("text", "line"):
                skipped.append(f"{where}: geometry not pulled (no build record; rebuild with `da adobe open`)")
            if t in ("rect", "ellipse") and it.get("type") == "PathItem" and _is_solid(l.get("fill", "$ink")):
                new_hex = _hex_of(it.get("fill"), mode) if it.get("filled") else None
                try:
                    cur = ctx.color(l.get("fill", "$ink"))
                except C.ColorError:
                    cur = None
                if mode == "CMYK" and it.get("fill") and "cmyk" in it["fill"] and cur is not None:
                    same = all(abs(a - b) <= 1.5 for a, b in zip(it["fill"]["cmyk"], C.to_cmyk(cur)))
                else:
                    same = new_hex == (cur.hex if cur else None)
                if not same:
                    change(l, where, "fill", new_hex or "none")
    if changes and not dry_run:
        D.save(project, d)
    return {"changes": changes, "skipped": skipped, "applied": bool(changes) and not dry_run,
            "base": "build record" if base else None}


# --- cli --------------------------------------------------------------------------------------

def cmd_adobe(a):
    try:
        if a.action == "status":
            return status()
        if a.action == "read":
            res = read(a.app)
            if a.out:
                Path(a.out).write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
                return {"written": a.out, "items": len(res.get("items", []))}
            return res
        if not a.project:
            raise SystemExit(f"da adobe {a.action} needs a project")
        pr = Project(a.project)
        if a.action == "script":
            return write_script(pr, a.app, a.artboard)
        if a.action == "open":
            return open_in(pr, a.app, a.artboard)
        if a.action == "pull":
            dump = json.loads(Path(a.dump).read_text(encoding="utf-8")) if a.dump else read(a.app)
            return pull(pr, dump, dry_run=a.dry_run)
    except AdobeError as e:
        raise SystemExit(f"{a.app}: {e}")
    raise SystemExit(a.action)


def register(sub) -> None:
    p = sub.add_parser("adobe", help="Illustrator / Photoshop: build editable documents, run them live, read changes back")
    p.add_argument("action", choices=["script", "open", "status", "read", "pull"],
                   help="script = write the .jsx; open = write + run it in the app; read = dump the open document; "
                        "pull = apply the open document's changes to design.json")
    p.add_argument("project", nargs="?")
    p.add_argument("--app", choices=list(APPS), default="illustrator")
    p.add_argument("--artboard", nargs="*")
    p.add_argument("--out", help="read: write the dump to this file")
    p.add_argument("--dump", help="pull: use a saved read dump instead of the live document")
    p.add_argument("--dry-run", action="store_true", help="pull: list changes without writing design.json")
    p.set_defaults(func=cmd_adobe)
